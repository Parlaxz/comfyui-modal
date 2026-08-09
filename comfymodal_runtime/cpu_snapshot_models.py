"""CPU snapshot model loading, validation, and retargeting.

This module produces a validated CpuSnapshotModels struct from a warmup
profile (mode=split only).  It loads CLIP, UNET, and (when the profile
declares one) VAE sequentially with gc.collect barriers, emits trace
events, and supports validation and device retargeting against the live
ComfyUI model_management module.
"""

from __future__ import annotations

import gc
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .contracts import (
    C5_IMPL_VERSION,
    ModelRestoreKey,
    VAE_POLICY_VERSION,
    VAE_PREFETCH_MODES,
    build_vae_policy_metadata,
    capture_c5_runtime_metadata,
    resolve_vae_policy,
    vae_prefetch_mode,
)
from .runtime_shape import runtime_shape_config
from .trace import RuntimeTrace

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelFileFact:
    role: str  # "unet", "clip1", "clip2", "vae"
    path: str
    size_bytes: int
    mtime_ns: int


# Current policy version â€” increment when compute-policy semantics change
# so that old snapshots with stale/legacy defaults are rejected.
CPU_SNAPSHOT_UNET_POLICY_VERSION: int = 2
_SNAPSHOT_CONSTRUCTION_ORDERS: dict[str, tuple[str, ...]] = {
    "O0": ("clip", "unet", "vae"),
    "O1": ("unet", "vae", "clip"),
    "O2": ("unet", "clip", "vae"),
    "O3": ("clip", "vae", "unet"),
}


def snapshot_construction_order(order: str) -> tuple[str, ...]:
    try:
        return _SNAPSHOT_CONSTRUCTION_ORDERS[order]
    except KeyError as exc:
        raise RuntimeError(f"unsupported snapshot model order: {order}") from exc


def _policy_identity(
    version: int,
    effective_weight_dtype: str,
    effective_compute_dtype: str,
    manual_cast_policy: str,
) -> str:
    """Deterministic identity derived from version and effective policies."""
    return (
        f"v{version}:"
        f"weight={effective_weight_dtype}:"
        f"compute={effective_compute_dtype}:"
        f"manual={manual_cast_policy}"
    )


@dataclass
class CpuSnapshotModels:
    model_key: ModelRestoreKey
    model_spec: dict[str, Any]
    normalized_profile: dict[str, Any]
    file_facts: tuple[ModelFileFact, ...]
    unet: Any = None
    clip: Any = None
    vae: Any = None
    load_timings_ms: dict[str, float] = field(default_factory=dict)
    compute_policy: str = "default"
    policy_version: int = CPU_SNAPSHOT_UNET_POLICY_VERSION
    target_gpus: tuple[str, ...] = ()
    construction_order: str = "O0"
    vae_policy_version: int = VAE_POLICY_VERSION
    # Production-facing VAE defaults align to the native BF16 policy (v1):
    # weight bfloat16, compute bfloat16_native, memory format contiguous,
    # prefetch off.  Policy-aware construction overrides these from
    # resolve_vae_policy(); v0 (float32/float32/contiguous) remains available as
    # an explicit FP32 control/fail-closed fallback in contracts.py.
    vae_weight_dtype: str = "bfloat16"
    vae_compute_dtype: str = "bfloat16_native"
    vae_memory_format: str = "contiguous"
    vae_policy_mode: str = "v1"
    vae_policy_metadata: dict[str, Any] = field(default_factory=dict)
    vae_validation_metadata: dict[str, Any] = field(default_factory=dict)
    vae_storage_registry: StorageRegistry | None = None


# ---------------------------------------------------------------------------
# CPU storage registry (deduplicated, mincore-based residency sampling)
# ---------------------------------------------------------------------------
# Uses ctypes mincore syscall on Linux to report pages resident in RAM.
# Unsupported/error-safe: returns empty result on non-Linux or failure.


@dataclass(frozen=True)
class StorageRange:
    """A page-aligned byte range for one storage object."""
    address: int    # page-aligned start address
    length: int     # total bytes (may span multiple pages)


@dataclass
class StorageRegistry:
    """Deduplicated registry of CPU storage ranges for one model.

    ``ranges`` — tuple of ``StorageRange`` for each unique merged storage
    interval (aliases/overlaps merged into a disjoint union).
    ``total_bytes`` — total unique bytes across ``ranges`` (the union).
    ``unique_storage_count`` — distinct storage objects scanned (supported).
    ``raw_byte_count`` — sum of unique interval lengths before overlap merge.
    ``alias_count`` — duplicate storage identities / exact ranges skipped.
    ``overlap_count`` — overlapping intervals absorbed into an existing union.
    ``overlap_bytes`` — ``raw_byte_count - total_bytes`` (>= 0).
    ``unsupported_entries`` — per-entry JSON-safe reports for tensors that are
      not CPU/dense/backed (meta/empty/sparse/quantized/non-CPU/unknown), so an
      unfamiliar shape is reported, never run-fatal.
    """
    ranges: tuple[StorageRange, ...] = ()
    total_bytes: int = 0
    unique_storage_count: int = 0
    raw_byte_count: int = 0
    alias_count: int = 0
    overlap_count: int = 0
    overlap_bytes: int = 0
    unsupported_count: int = 0
    unsupported_entries: tuple[dict[str, Any], ...] = ()


def _tensor_support_class(tensor: Any) -> tuple[bool, str]:
    """Classify *tensor* for CPU-storage scanning.

    Returns ``(True, "")`` for a supported CPU dense non-empty tensor, or
    ``(False, reason)`` for an unsupported entry (meta/empty/sparse/quantized/
    mkldnn/non-CPU/unknown).  Never raises; reports per-entry so an unfamiliar
    shape is not run-fatal.
    """
    try:
        _dev = getattr(tensor, "device", None)
        if isinstance(_dev, str):
            _dev_str = _dev.lower()
        else:
            _dev_type = getattr(_dev, "type", None)
            _dev_str = str(_dev_type() if callable(_dev_type) else (_dev_type or "")).lower()
    except Exception:
        _dev_str = "unknown"
    if _dev_str and _dev_str not in ("cpu", ""):
        return False, f"device:{_dev_str}"
    if getattr(tensor, "is_meta", False):
        return False, "meta"
    try:
        _numel_fn = getattr(tensor, "numel", None)
        if _numel_fn is not None and int(_numel_fn()) == 0:
            return False, "empty"
    except Exception:
        pass
    for _attr, _label in (("is_sparse", "sparse"), ("is_quantized", "quantized"),
                          ("is_mkldnn", "mkldnn"), ("is_nested", "nested")):
        try:
            if getattr(tensor, _attr, False):
                return False, _label
        except Exception:
            pass
    return True, ""


def _merge_overlapping_intervals(
    intervals: list[tuple[int, int]],
) -> tuple[list[tuple[int, int]], int, int]:
    """Merge overlapping/contained ``[address, address+length)`` intervals.

    Returns ``(merged, overlap_count, overlap_bytes)``.  ``overlap_count`` is
    the number of intervals absorbed by an existing segment; ``overlap_bytes``
    is ``raw_sum - union_len`` (bytes double-counted before merge, >= 0).
    """
    if not intervals:
        return [], 0, 0
    _segs: list[tuple[int, int]] = []
    for _addr, _len in sorted(intervals, key=lambda it: (it[0], it[1])):
        _start = _addr
        _end = _addr + _len
        if _segs and _start <= _segs[-1][1]:
            _prev_start, _prev_end = _segs[-1]
            _segs[-1] = (_prev_start, max(_prev_end, _end))
        else:
            _segs.append((_start, _end))
    _merged = [(_s, _e - _s) for _s, _e in _segs]
    _raw_sum = sum(_len for _, _len in intervals)
    _union_len = sum(_len for _, _len in _merged)
    _overlap_count = max(0, len(intervals) - len(_merged))
    _overlap_bytes = max(0, _raw_sum - _union_len)
    return _merged, _overlap_count, _overlap_bytes


def _resolve_inner_model(model: Any) -> Any:
    """Resolve the inner torch.nn.Module from a ModelPatcher wrapper or raw model.

    Inspects ``model.model.diffusion_model`` (ModelPatcher pattern),
    ``model.model`` (wrapper pattern), then falls back to ``model`` directly.
    Does NOT mutate or import.
    """
    _inner = getattr(model, "model", None)
    if _inner is not None:
        _dm = getattr(_inner, "diffusion_model", None)
        if _dm is not None:
            return _dm
        return _inner
    if hasattr(model, "diffusion_model"):
        return model.diffusion_model
    return model


def _dedupe_storage_target_modules(modules: list[Any]) -> list[Any]:
    """Return identity-unique modules from *modules*, preserving order.

    ``id()`` deduplication prevents a CLIP wrapper resolving to the same
    module more than once (e.g. ``cond_stage_model`` reached both directly
    and through ``patcher.model``).
    """
    seen: set[int] = set()
    result: list[Any] = []
    for module in modules:
        if module is None:
            continue
        if id(module) in seen:
            continue
        seen.add(id(module))
        result.append(module)
    return result


def _resolve_storage_target_modules(model: Any) -> list[Any]:
    """Resolve the concrete ``torch.nn.Module``(s) owning retained CPU storage.

    CLIP wrapper shape (``comfy.sd.CLIP``): the wrapper itself is NOT an
    ``nn.Module``; its weights live in ``cond_stage_model`` (and its
    ``clip_l``/``clip_g`` submodules) or in ``patcher.model``.  A module
    passed directly (the ``cond_stage_model`` or ``patcher.model``) is
    scanned itself plus any ``clip_l``/``clip_g`` leaf submodules so its
    own parameters are never skipped.  UNET patchers and every other object
    fall back to ``_resolve_inner_model`` so existing UNET resolution is
    unchanged (``model.diffusion_model``).  Returns identity-unique
    modules.  Never mutates, never moves, never copies.
    """
    targets: list[Any] = []
    first_stage = getattr(model, "first_stage_model", None)
    if _is_module_like(first_stage):
        return [first_stage]
    collected = _collect_clip_modules(model)
    if collected:
        targets.extend(module for _, module in collected)
        # A directly-passed module that the collector resolved to leaf
        # submodules only must include itself so parameters held directly on
        # the module (outside clip_l/clip_g) are scanned too.  Identity-dedup
        # makes this safe when the module was already collected.
        if _is_module_like(model) and all(module is not model for _, module in collected):
            targets.insert(0, model)
    elif _is_module_like(model):
        targets.append(model)
    else:
        inner = _resolve_inner_model(model)
        if inner is not None:
            targets.append(inner)
    return _dedupe_storage_target_modules(targets)


def build_unique_storage_registry(model: Any) -> StorageRegistry:
    """Build a deduplicated ``StorageRegistry`` from *model* parameters and buffers.

    Iterates all parameters/buffers across the exact retained module(s):
    CLIP wrappers resolve to ``cond_stage_model`` / ``patcher.model`` (and
    their ``clip_l``/``clip_g`` submodules) while UNET patchers resolve to
    the diffusion model as before.  Reads ``untyped_storage().data_ptr()``
    and ``nbytes()`` (fallback to ``storage().data_ptr()`` /
    ``numel() * element_size()``).  Deduplicates by storage identity
    (``id(storage)``) and identical byte ranges ACROSS all resolved
    modules.  CPU-only, non-meta, nonzero usable tensors only.
    No reads/copy/contiguous/cpu/numpy.  Catches per tensor, not whole
    enumeration.  When no resolved module can be inspected at all, raises
    (so ``advise_storage_pages_willneed`` reports a truthful error rather
    than inventing an empty registry).
    Returns ``StorageRegistry`` with page-aligned ``StorageRange`` entries.
    """
    _target_modules = _resolve_storage_target_modules(model)
    _ranges: list[StorageRange] = []
    _total_bytes: int = 0
    seen_ids: set[int] = set()
    seen_ranges: set[tuple[int, int]] = set()
    _inspection_failures = 0
    _raw_intervals: list[tuple[int, int]] = []
    _unique_storage_count = 0
    _raw_byte_count = 0
    _alias_count = 0
    _unsupported_entries: list[dict[str, Any]] = []
    _unsupported_ids: set[int] = set()

    def _record_tensor(tensor: Any, kind: str) -> None:
        nonlocal _unique_storage_count, _raw_byte_count, _alias_count
        try:
            _ok, _reason = _tensor_support_class(tensor)
            if not _ok:
                _oid = id(tensor)
                if _oid not in _unsupported_ids:
                    _unsupported_ids.add(_oid)
                    _unsupported_entries.append({
                        "kind": kind,
                        "reason": _reason,
                        "object_id": str(_oid),
                        "type": type(tensor).__module__ + "." + type(tensor).__qualname__,
                    })
                return
            _st = tensor.untyped_storage() if hasattr(tensor, "untyped_storage") else tensor.storage()
            _sid = id(_st)
            if _sid in seen_ids:
                _alias_count += 1
                return
            seen_ids.add(_sid)
            _ptr = _st.data_ptr()
            _nbytes = _st.nbytes() if hasattr(_st, "nbytes") else int(tensor.numel() * tensor.element_size())
            if _nbytes <= 0:
                return
            _key = (_ptr, _nbytes)
            if _key in seen_ranges:
                _alias_count += 1
                return
            seen_ranges.add(_key)
            _unique_storage_count += 1
            _raw_byte_count += _nbytes
            _raw_intervals.append((_ptr, _nbytes))
        except Exception:
            pass

    for _target in _target_modules:
        # Iterate parameters (per-tensor try/except)
        try:
            _parameters = _target.parameters()
        except Exception:
            _inspection_failures += 1
            _parameters = ()
        for _p in _parameters:
            try:
                _record_tensor(_p, "parameter")
            except Exception:
                continue

        # Iterate buffers (per-tensor try/except)
        try:
            _buffers = _target.buffers()
        except Exception:
            _inspection_failures += 1
            _buffers = ()
        for _b in _buffers:
            try:
                _record_tensor(_b, "buffer")
            except Exception:
                continue

    if _inspection_failures == len(_target_modules) and not _raw_intervals and _target_modules:
        # Every resolved module was uninspectable: surface truthfully instead
        # of pretending the model has no storage.
        raise RuntimeError(
            "model exposes no inspectable parameters/buffers "
            f"({len(_target_modules)} resolved module(s))"
        )

    _merged, _overlap_count, _overlap_bytes = _merge_overlapping_intervals(_raw_intervals)
    _ranges = [StorageRange(address=_addr, length=_len) for _addr, _len in _merged]
    _total_bytes = sum(_len for _, _len in _merged)
    return StorageRegistry(
        ranges=tuple(_ranges),
        total_bytes=_total_bytes,
        unique_storage_count=_unique_storage_count,
        raw_byte_count=_raw_byte_count,
        alias_count=_alias_count,
        overlap_count=_overlap_count,
        overlap_bytes=_overlap_bytes,
        unsupported_count=len(_unsupported_entries),
        unsupported_entries=tuple(_unsupported_entries),
    )


def sample_storage_residency(registry: StorageRegistry) -> dict[str, Any]:
    """Sample Linux mincore for all ranges in *registry*.

    Uses ``ctypes`` ``mincore()`` syscall.  Returns a dict with exact keys:
      status, storage_count, total_bytes, total_pages, resident_pages,
      resident_bytes, resident_percent, duration_ms.

    ``total_pages`` is the page count over PAGE-ALIGNED ranges: each range
    start is aligned down and end aligned up to the page size before
    sampling, so ``total_pages * page_size`` (the aligned coverage) may
    exceed the raw storage ``total_bytes``.

    Non-posix or unavailable mincore => status="unsupported".
    Syscall/pointer errors => status="error" (not "unsupported").
    Do not return invented zero for unsupported/error (None acceptable).
    No reads/copies.
    """
    _start_mono = time.monotonic_ns()
    import os as _os
    if _os.name != "posix":
        return {
            "status": "unsupported",
            "storage_count": len(registry.ranges),
            "total_bytes": registry.total_bytes,
            "total_pages": None,
            "resident_pages": None,
            "resident_bytes": None,
            "resident_percent": None,
            "duration_ms": round((time.monotonic_ns() - _start_mono) / 1_000_000, 3),
        }
    try:
        import ctypes as _ctypes
        _libc = _ctypes.CDLL("libc.so.6", use_errno=True)
        _mincore_fn = _libc.mincore
        _mincore_fn.argtypes = [_ctypes.c_void_p, _ctypes.c_size_t, _ctypes.POINTER(_ctypes.c_ubyte)]
        _mincore_fn.restype = _ctypes.c_int

        page_size = _os.sysconf("SC_PAGE_SIZE")
        if page_size <= 0:
            page_size = 4096

        total_pages = 0
        resident_pages = 0
        storage_count = 0

        for _range in registry.ranges:
            # Sample aligns down/start and up/end for mincore
            _start_aligned = _range.address & ~(page_size - 1)
            _end = _range.address + _range.length
            _end_aligned = (_end + page_size - 1) & ~(page_size - 1)
            _aligned_length = _end_aligned - _start_aligned
            n_pages = _aligned_length // page_size
            if n_pages <= 0:
                continue
            vec = (_ctypes.c_ubyte * n_pages)()
            _ret = _mincore_fn(
                _ctypes.c_void_p(_start_aligned),
                _ctypes.c_size_t(_aligned_length),
                vec,
            )
            if _ret == 0:
                storage_count += 1
                total_pages += n_pages
                resident_pages += sum(1 for b in vec if b & 0x01)
            elif _ret != 0:
                # syscall error -> return error status
                return {
                    "status": "error",
                    "storage_count": len(registry.ranges),
                    "total_bytes": registry.total_bytes,
                    "total_pages": None,
                    "resident_pages": None,
                    "resident_bytes": None,
                    "resident_percent": None,
                    "duration_ms": round((time.monotonic_ns() - _start_mono) / 1_000_000, 3),
                }

        _resident_percent = round(resident_pages / total_pages * 100, 2) if total_pages > 0 else 0.0
        return {
            "status": "ok",
            "storage_count": storage_count,
            "total_bytes": registry.total_bytes,
            "total_pages": total_pages,
            "resident_pages": resident_pages,
            "resident_bytes": resident_pages * page_size,
            "resident_percent": _resident_percent,
            "duration_ms": round((time.monotonic_ns() - _start_mono) / 1_000_000, 3),
        }
    except Exception:
        return {
            "status": "error",
            "storage_count": len(registry.ranges),
            "total_bytes": registry.total_bytes,
            "total_pages": None,
            "resident_pages": None,
            "resident_bytes": None,
            "resident_percent": None,
            "duration_ms": round((time.monotonic_ns() - _start_mono) / 1_000_000, 3),
        }


# ---------------------------------------------------------------------------
# Native page-readiness (synchronous MADV_WILLNEED advisory)
# ---------------------------------------------------------------------------
# Phase B consistency candidate: retained anonymous CPU tensor storage is
# synchronously advised via libc madvise(MADV_WILLNEED) immediately before
# the CLIP prefill encode loop and immediately before the first
# request-scoped graph UNET activation.  Gated by
# ``COMFYMODAL_V2_PAGE_READINESS_MODE=willneed`` (off by default — current
# production behavior is unchanged until explicitly tested).  Uses the
# deduplicated ``StorageRegistry`` / ``build_unique_storage_registry`` above.
# No tensor element loop, no copies, no CUDA sync, no model mutation.
# Synchronous only — never hidden in a future.
#
# TRUTHFULNESS: ``madvise(MADV_WILLNEED)`` is an ADVISORY syscall.  A return
# of 0 means the kernel *accepted* the advice for the range; it does NOT
# guarantee the physical pages are resident.  ``status="ok"`` therefore means
# the advisory was accepted for every range — never that the pages were
# populated.  Reported counts are ``advised_*`` (bytes/pages/percent covered
# by accepted advice), never ``populated_*``.

_PAGE_READINESS_ENV_KEY: str = "COMFYMODAL_V2_PAGE_READINESS_MODE"
_PAGE_READINESS_MODE_WILLNEED: str = "willneed"
# Linux madvise(2) flag value for MADV_WILLNEED (kernel should prefault).
_MADV_WILLNEED: int = 3


def page_readiness_mode() -> str:
    """Return the normalized page-readiness mode from the environment.

    ``COMFYMODAL_V2_PAGE_READINESS_MODE=willneed`` enables the synchronous
    native page-readiness candidate; any other value (including absent)
    returns ``"off"`` so current production behavior is unchanged until
    explicitly tested.  Read at call time so tests can set the env var
    between imports.
    """
    raw = os.environ.get(_PAGE_READINESS_ENV_KEY, "").strip().lower()
    if raw == _PAGE_READINESS_MODE_WILLNEED:
        return _PAGE_READINESS_MODE_WILLNEED
    return "off"


def _is_posix() -> bool:
    """True on POSIX platforms (Linux).  Split out for focused tests."""
    return os.name == "posix"


def _page_size() -> int:
    """Best-effort system page size (fallback 4096).  Split out for tests."""
    try:
        size = os.sysconf("SC_PAGE_SIZE")
        return int(size) if size and int(size) > 0 else 4096
    except Exception:
        return 4096


def _page_fault_counters() -> dict[str, Any]:
    """Best-effort process page-fault counters (major/minor) or None each."""
    try:
        import resource as _r
        _ru = _r.getrusage(_r.RUSAGE_SELF)
        return {"major_faults": int(_ru.ru_majflt), "minor_faults": int(_ru.ru_minflt)}
    except Exception:
        return {"major_faults": None, "minor_faults": None}


def _fault_deltas(before: Mapping[str, Any] | None) -> tuple[int | None, int | None]:
    """Non-negative major/minor fault deltas from a before snapshot (or None)."""
    if not before:
        return None, None
    after = _page_fault_counters()
    _major_b = before.get("major_faults")
    _minor_b = before.get("minor_faults")
    _major_delta: int | None = None
    _minor_delta: int | None = None
    if _major_b is not None and after["major_faults"] is not None:
        _major_delta = max(0, int(after["major_faults"]) - int(_major_b))
    if _minor_b is not None and after["minor_faults"] is not None:
        _minor_delta = max(0, int(after["minor_faults"]) - int(_minor_b))
    return _major_delta, _minor_delta


def _libc_madvise_willneed() -> Any | None:
    """Resolve libc ``madvise`` with ``MADV_WILLNEED`` support.

    Returns a callable ``fn(address: int, length: int) -> (ret, errno)``
    (raw syscall return code plus errno, errno ``None`` on success) or
    ``None`` when unavailable (non-POSIX or missing libc symbol).  Never
    raises.  Split out for focused tests that mock the syscall without
    requiring Linux.
    """
    if not _is_posix():
        return None
    try:
        import ctypes as _ctypes
        _libc = _ctypes.CDLL("libc.so.6", use_errno=True)
        _fn = getattr(_libc, "madvise", None)
        if _fn is None:
            return None
        _fn.argtypes = [_ctypes.c_void_p, _ctypes.c_size_t, _ctypes.c_int]
        _fn.restype = _ctypes.c_int

        def _call(address: int, length: int) -> tuple[int, int | None]:
            _ret = _fn(
                _ctypes.c_void_p(address),
                _ctypes.c_size_t(length),
                _MADV_WILLNEED,
            )
            _errno = _ctypes.get_errno() if _ret != 0 else None
            return int(_ret), _errno

        return _call
    except Exception:
        return None


def advise_storage_pages_willneed(model_or_registry: Any) -> dict[str, Any]:
    """Synchronously advise the kernel to prefault retained anonymous CPU storage.

    Builds the deduplicated registry from *model_or_registry* (a model
    object or an existing ``StorageRegistry``), then calls libc
    ``madvise(MADV_WILLNEED)`` on page-aligned ranges.  Synchronous only —
    never hidden in a future.

    Truthfulness contract (advisory semantics — never invent residency):
      * ``status="unsupported"`` when the syscall is unavailable (non-Linux
        or missing symbol) — never invents success.
      * ``status="empty"`` when the registry has no ranges.
      * ``status="ok"`` when every range's advisory was ACCEPTED (ret == 0).
        This means the kernel accepted the advice — NOT that the physical
        pages are resident.
      * ``status="partial"`` when some ranges were accepted and some failed.
      * ``status="error"`` when every range failed (or the registry build
        raised) — per-range error reason is included.

    No tensor element loop, no copies, no CUDA sync, no model mutation.
    Returns a flat JSON-safe dict:
      status, mode, storage_count, range_count, total_bytes, total_pages,
      advised_pages, advised_bytes, advised_percent, major_faults,
      minor_faults, duration_ms, error_reason, ranges (per-range records).

    ``total_pages`` / ``advised_pages`` are page counts over PAGE-ALIGNED
    ranges: each range start is aligned down and end aligned up to the page
    size before the advisory (``madvise`` operates on whole pages), so the
    aligned byte coverage (``total_pages * page_size`` /
    ``advised_pages * page_size``) may exceed the raw storage
    ``total_bytes``.  ``advised_bytes`` likewise reflects the aligned
    (rounded-up) coverage, not raw storage bytes.
    """
    _start_ns = time.monotonic_ns()
    _faults_before = _page_fault_counters()

    if isinstance(model_or_registry, StorageRegistry):
        registry = model_or_registry
    else:
        try:
            registry = build_unique_storage_registry(model_or_registry)
        except Exception as exc:
            return {
                "status": "error",
                "mode": _PAGE_READINESS_MODE_WILLNEED,
                "storage_count": None,
                "range_count": None,
                "total_bytes": None,
                "total_pages": None,
                "advised_pages": None,
                "advised_bytes": None,
                "advised_percent": None,
                "major_faults": None,
                "minor_faults": None,
                "duration_ms": round((time.monotonic_ns() - _start_ns) / 1_000_000, 3),
                "error_reason": f"{type(exc).__name__}: {str(exc)[:200]}",
                "ranges": [],
            }

    _range_count = len(registry.ranges)
    _base: dict[str, Any] = {
        "status": "unsupported",
        "mode": _PAGE_READINESS_MODE_WILLNEED,
        "storage_count": _range_count,
        "range_count": _range_count,
        "total_bytes": registry.total_bytes,
        "total_pages": None,
        "advised_pages": None,
        "advised_bytes": None,
        "advised_percent": None,
        "major_faults": None,
        "minor_faults": None,
        "duration_ms": round((time.monotonic_ns() - _start_ns) / 1_000_000, 3),
        "error_reason": "",
        "ranges": [],
    }
    _major_delta, _minor_delta = _fault_deltas(_faults_before)
    _base["major_faults"] = _major_delta
    _base["minor_faults"] = _minor_delta

    if not registry.ranges:
        _base["status"] = "empty"
        return _base

    _madvise = _libc_madvise_willneed()
    if _madvise is None:
        return _base  # status=unsupported (syscall unavailable — never invent success)

    page_size = _page_size()
    total_pages = 0
    advised_pages = 0
    failed_count = 0
    range_records: list[dict[str, Any]] = []
    error_reason = ""
    for _r in registry.ranges:
        _start_aligned = _r.address & ~(page_size - 1)
        _end = _r.address + _r.length
        _end_aligned = (_end + page_size - 1) & ~(page_size - 1)
        _aligned_length = _end_aligned - _start_aligned
        _n_pages = _aligned_length // page_size
        if _n_pages <= 0:
            continue
        total_pages += _n_pages
        _ret, _errno = _madvise(_start_aligned, _aligned_length)
        _record: dict[str, Any] = {
            "address": _start_aligned,
            "length": _aligned_length,
            "pages": _n_pages,
            "ret": _ret,
            "errno": _errno,
        }
        if _ret == 0:
            advised_pages += _n_pages
            _record["status"] = "ok"
        else:
            failed_count += 1
            _record["status"] = "error"
            if not error_reason:
                error_reason = (
                    f"madvise(MADV_WILLNEED) failed errno={_errno} "
                    f"at address={hex(_start_aligned)}"
                )
        range_records.append(_record)

    if failed_count == 0:
        status = "ok"
    elif advised_pages > 0:
        status = "partial"
    else:
        status = "error"

    _major_after, _minor_after = _fault_deltas(_faults_before)
    _advised_bytes = advised_pages * page_size
    return {
        "status": status,
        "mode": _PAGE_READINESS_MODE_WILLNEED,
        "storage_count": _range_count,
        "range_count": len(range_records),
        "total_bytes": registry.total_bytes,
        "total_pages": total_pages,
        "advised_pages": advised_pages,
        "advised_bytes": _advised_bytes,
        "advised_percent": round(advised_pages / total_pages * 100, 2) if total_pages else 0.0,
        "major_faults": _major_after,
        "minor_faults": _minor_after,
        "duration_ms": round((time.monotonic_ns() - _start_ns) / 1_000_000, 3),
        "error_reason": error_reason,
        "ranges": range_records,
    }


# ---------------------------------------------------------------------------
# CPU VAE page prefetch
# ---------------------------------------------------------------------------

_VAE_PREFETCH_MODES = VAE_PREFETCH_MODES
_MADV_POPULATE_READ = 22
_VAE_PREFETCH_MAX_TOUCH_PAGES = 131072


def _libc_madvise_flag(flag: int) -> Any | None:
    if not _is_posix():
        return None
    try:
        import ctypes as _ctypes
        _libc = _ctypes.CDLL("libc.so.6", use_errno=True)
        _fn = getattr(_libc, "madvise", None)
        if _fn is None:
            return None
        _fn.argtypes = [_ctypes.c_void_p, _ctypes.c_size_t, _ctypes.c_int]
        _fn.restype = _ctypes.c_int

        def _call(address: int, length: int) -> tuple[int, int | None]:
            _ret = _fn(_ctypes.c_void_p(address), _ctypes.c_size_t(length), int(flag))
            return int(_ret), (_ctypes.get_errno() if _ret != 0 else None)

        return _call
    except Exception:
        return None


def prefetch_vae_storage(
    registry: StorageRegistry,
    *,
    mode: str | None = None,
    max_touch_pages: int = _VAE_PREFETCH_MAX_TOUCH_PAGES,
) -> dict[str, Any]:
    """Prefetch a prebuilt VAE CPU-storage registry without Torch or CUDA."""
    _start_ns = time.monotonic_ns()
    _thread_start_ns = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
    _faults_before = _page_fault_counters()
    _mode = str(mode or vae_prefetch_mode()).strip().lower()
    if _mode not in _VAE_PREFETCH_MODES:
        _mode = "off"
    _base: dict[str, Any] = {
        "mode": _mode,
        "vae_prefetch_mode": _mode,
        "status": "off" if _mode == "off" else "pending",
        "storage_count": len(registry.ranges),
        "total_bytes": registry.total_bytes,
        "total_pages": 0,
        "prefetch_pages": 0,
        "prefetch_bytes": 0,
        "prefetch_percent": 0.0,
        "major_faults": None,
        "minor_faults": None,
        "prefetch_cpu_ms": None,
        "duration_ms": 0.0,
        "error_reason": "",
        # ── Bounded prefetch metric contract ─────────────────────────
        "start_ms": round(time.time() * 1000, 3),
        "end_ms": None,
        "start_mono_ns": _start_ns,
        "end_mono_ns": None,
        "wall_ms": 0.0,
        "process_cpu_ms": None,
        "effective_cores": 1.0,
        "bytes": 0,
        "page_count": 0,
        "ready_before_sampling_end": False,
        "overlap_with_sampling_ms": 0.0,
        "error": "",
    }
    if _mode == "off":
        _base["end_ms"] = round(time.time() * 1000, 3)
        _base["end_mono_ns"] = time.monotonic_ns()
        _base["wall_ms"] = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
        _base["duration_ms"] = _base["wall_ms"]
        _base["bytes"] = 0
        _base["page_count"] = 0
        return _base
    if not registry.ranges:
        _base["status"] = "empty"
        _base["end_ms"] = round(time.time() * 1000, 3)
        _base["end_mono_ns"] = time.monotonic_ns()
        _base["wall_ms"] = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
        _base["duration_ms"] = _base["wall_ms"]
        _base["bytes"] = 0
        _base["page_count"] = 0
        return _base

    page_size = _page_size()
    ranges: list[tuple[int, int, int]] = []
    for item in registry.ranges:
        start_aligned = item.address & ~(page_size - 1)
        end_aligned = (item.address + item.length + page_size - 1) & ~(page_size - 1)
        pages = max(0, (end_aligned - start_aligned) // page_size)
        if pages:
            ranges.append((start_aligned, end_aligned - start_aligned, pages))
    total_pages = sum(item[2] for item in ranges)
    _base["total_pages"] = total_pages
    try:
        if _mode in {"madvise_willneed", "madvise_populate_read"}:
            flag = _MADV_WILLNEED if _mode == "madvise_willneed" else _MADV_POPULATE_READ
            advise = _libc_madvise_flag(flag)
            if advise is None:
                _base["status"] = "unsupported"
                _base["error_reason"] = "madvise_unavailable"
            else:
                failed = 0
                for address, length, pages in ranges:
                    ret, errno_value = advise(address, length)
                    if ret == 0:
                        _base["prefetch_pages"] += pages
                    else:
                        failed += 1
                        if not _base["error_reason"]:
                            _base["error_reason"] = f"madvise_failed_errno={errno_value}"
                if failed == 0:
                    _base["status"] = "ok"
                elif _base["prefetch_pages"]:
                    _base["status"] = "partial"
                else:
                    _base["status"] = "error"
        elif _mode == "bounded_native_touch":
            import ctypes as _ctypes
            page_budget = max(0, min(int(max_touch_pages), total_pages))
            touched = 0
            for address, _length, pages in ranges:
                for page_index in range(min(pages, page_budget - touched)):
                    _ctypes.c_ubyte.from_address(address + page_index * page_size).value
                    touched += 1
                    if touched >= page_budget:
                        break
                if touched >= page_budget:
                    break
            _base["prefetch_pages"] = touched
            _base["status"] = "ok" if touched == total_pages else "bounded"
            if touched < total_pages:
                _base["error_reason"] = "page_budget_reached"
        _base["prefetch_bytes"] = int(_base["prefetch_pages"]) * page_size
        _base["prefetch_percent"] = round(
            int(_base["prefetch_pages"]) / total_pages * 100, 2
        ) if total_pages else 0.0
    except Exception as exc:
        _base["status"] = "error"
        _base["error_reason"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    _faults_after = _page_fault_counters()
    _base["major_faults"] = (
        max(0, _faults_after["major_faults"] - _faults_before["major_faults"])
        if _faults_after["major_faults"] is not None and _faults_before["major_faults"] is not None
        else None
    )
    _base["minor_faults"] = (
        max(0, _faults_after["minor_faults"] - _faults_before["minor_faults"])
        if _faults_after["minor_faults"] is not None and _faults_before["minor_faults"] is not None
        else None
    )
    _thread_end_ns = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
    _base["prefetch_cpu_ms"] = (
        round(max(0, _thread_end_ns - _thread_start_ns) / 1_000_000, 3)
        if isinstance(_thread_start_ns, int) and isinstance(_thread_end_ns, int)
        else None
    )
    _base["duration_ms"] = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
    _end_ns = time.monotonic_ns()
    _end_wall_ms = round(time.time() * 1000, 3)
    _base["end_ms"] = _end_wall_ms
    _base["end_mono_ns"] = _end_ns
    _base["wall_ms"] = _base["duration_ms"]
    _base["process_cpu_ms"] = _base["prefetch_cpu_ms"]
    _base["effective_cores"] = 1.0 if _base["status"] not in {"off", "empty"} else 0.0
    _base["bytes"] = int(_base["prefetch_bytes"])
    _base["page_count"] = int(_base["prefetch_pages"])
    _base["error"] = _base["error_reason"]
    return _base


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_LOADER_KEYS = frozenset({"mode", "unet", "clip1", "clip2", "vae", "clip_type", "weight_dtype"})


def _normalize_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Return only restore-relevant identity fields for mode=split.

    The field policy comes from the repository's canonical warmup-profile
    normalizer; this helper only projects its restore fields for Plan A.
    """
    raw = dict(profile) if isinstance(profile, Mapping) else {}
    if raw.get("clip2") is None:
        raw["clip2"] = ""
    from warmup_profile import _normalize_stable_profile

    stable = _normalize_stable_profile(raw)
    normalized: dict[str, Any] = {
        key: stable.get(key, "")
        for key in ("mode", "unet", "clip1", "clip2", "vae", "clip_type")
    }
    if raw.get("clip2") and normalized["clip2"] != raw["clip2"]:
        normalized["clip2"] = raw["clip2"].strip()
    if "weight_dtype" in stable:
        normalized["weight_dtype"] = stable["weight_dtype"]
    _vae_policy = resolve_vae_policy(raw.get("vae_policy_mode"))
    for _key in (
        "vae_policy_version", "vae_weight_dtype", "vae_compute_dtype", "vae_memory_format",
    ):
        _value = raw.get(_key, _vae_policy[_key])
        normalized[_key] = _value
    normalized["vae_policy_mode"] = str(raw.get("vae_policy_mode", _vae_policy["vae_policy_mode"]) or _vae_policy["vae_policy_mode"])
    _vae_full = build_vae_policy_metadata(normalized, include_runtime_versions=False)
    for _key in ("vae_policy_provenance", "vae_prefetch_mode", "c5_impl_version", "arch_identifier"):
        normalized[_key] = _vae_full[_key]
    return normalized


def _build_model_key(normalized: dict[str, Any]) -> ModelRestoreKey:
    from .restore_plan import _build_dual_clip_identity

    clip1 = normalized["clip1"]
    clip2 = normalized.get("clip2", "")
    clip = _build_dual_clip_identity(clip1, clip2) if clip2 else clip1
    return ModelRestoreKey(
        unet_identity=normalized["unet"],
        clip_identity=clip,
        vae_identity=normalized.get("vae", ""),
        clip_type=normalized["clip_type"],
        vae_policy_version=normalized.get("vae_policy_version", VAE_POLICY_VERSION),
        vae_weight_dtype=normalized.get("vae_weight_dtype", "float32"),
        vae_compute_dtype=normalized.get("vae_compute_dtype", "float32"),
        vae_memory_format=normalized.get("vae_memory_format", "contiguous"),
        vae_policy_metadata=build_vae_policy_metadata(
            normalized, include_runtime_versions=False,
        ),
    )


# â”€â”€ Compute policy identity field â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# This field in model_spec distinguishes the compute/manual-cast policy
# used during snapshot construction so that a snapshot built with one
# policy cannot match an identity that requested a different policy.
#   "default"  â€” no explicit override (legacy / non-BF16).
#   "bf16_native" â€” manual_cast_dtype=None, native BF16 compute.
_COMPUTE_POLICY_DEFAULT = "default"
_COMPUTE_POLICY_BF16_NATIVE = "bf16_native"


def _resolve_compute_policy(
    weight_dtype_str: str,
    *,
    target_gpus: tuple[str, ...] | None = None,
) -> str:
    """Determine the compute policy label for snapshot identity.

    Returns ``"bf16_native"`` when the effective dtype resolves to BF16
    AND the primary target GPU supports BF16 (so the model is built with
    native BF16 compute, no manual cast).  Uses primary target semantics
    consistently with ``resolve_unet_effective_dtype`` â€” fallback GPUs
    are NOT considered for policy resolution.

    Returns ``"default"`` otherwise.
    """
    from gpu_catalog import gpu_supports_bf16
    _primary = target_gpus[0] if target_gpus else ""
    if not _primary:
        return _COMPUTE_POLICY_DEFAULT
    # "default" weight_dtype on a BF16-capable primary â†’ native
    if weight_dtype_str == "default" and gpu_supports_bf16(_primary):
        return _COMPUTE_POLICY_BF16_NATIVE
    # Explicit bf16 on a BF16-capable primary â†’ native
    import torch as _torch
    _is_explicit_bf16 = (
        weight_dtype_str == "bfloat16"
        or weight_dtype_str == "bf16"
        or weight_dtype_str == str(_torch.bfloat16)
    )
    if _is_explicit_bf16 and gpu_supports_bf16(_primary):
        return _COMPUTE_POLICY_BF16_NATIVE
    return _COMPUTE_POLICY_DEFAULT


def _build_model_spec(normalized: dict[str, Any]) -> dict[str, Any]:
    """Build loaders from the normalized profile.

    Matches restore_plan.py shape: weight_dtype always present
    in the UNET loader ("default" when absent from profile).
    No node IDs, prompt fields, or hashes.

    NOTE: compute policy identity is stored separately on
    CpuSnapshotModels.compute_policy, NOT in model_spec.
    """
    unet_loader: dict[str, Any] = {
        "loader_class": "UNETLoader",
        "unet_name": normalized["unet"],
        "weight_dtype": normalized.get("weight_dtype", "default"),
    }
    clip_type = normalized.get("clip_type") or "stable_diffusion"
    if normalized.get("clip2"):
        clip_loader: dict[str, Any] = {
            "loader_class": "DualCLIPLoader",
            "clip_name1": normalized["clip1"],
            "clip_name2": normalized["clip2"],
            "type": clip_type,
            "device": "default",
        }
    else:
        clip_loader = {
            "loader_class": "CLIPLoader",
            "clip_name": normalized["clip1"],
            "type": clip_type,
            "device": "default",
        }
    vae_loaders: list[dict[str, Any]] = []
    vae_name = normalized.get("vae", "")
    if vae_name:
        vae_loaders.append({
            "loader_class": "VAELoader",
            "vae_name": vae_name,
            "vae_policy_version": normalized.get("vae_policy_version", VAE_POLICY_VERSION),
            "vae_weight_dtype": normalized.get("vae_weight_dtype", "float32"),
            "vae_compute_dtype": normalized.get("vae_compute_dtype", "float32"),
            "vae_memory_format": normalized.get("vae_memory_format", "contiguous"),
            "vae_prefetch_mode": normalized.get("vae_prefetch_mode", "off"),
            "c5_impl_version": normalized.get("c5_impl_version", C5_IMPL_VERSION),
        })
    return {
        "loaders": {
            "unet": [unet_loader],
            "clip": [clip_loader],
            "vae": vae_loaders,
        },
    }


def _stat_file(role: str, filename: str, *, resolve_path: Callable[[str, str], str]) -> ModelFileFact:
    """Stat one model file through the resolve_path callback.

    Never reads or hashes file content â€” stat only.
    """
    resolved = resolve_path(role, filename)
    st = os.stat(resolved)
    return ModelFileFact(
        role=role,
        path=resolved,
        size_bytes=st.st_size,
        mtime_ns=int(st.st_mtime_ns if hasattr(st, "st_mtime_ns") else st.st_mtime * 1_000_000_000),
    )


# ---------------------------------------------------------------------------
# Tensor / shape validation helpers (private)
# ---------------------------------------------------------------------------


def _tensor_device_type(tensor: Any) -> str | None:
    """Return the lower-case device type of *tensor*, or None if not inspectable."""
    dev = getattr(tensor, "device", None)
    if dev is None:
        return None
    if isinstance(dev, str):
        return dev.strip().lower().split(":")[0]
    # torch.device or duck-typed
    dt = getattr(dev, "type", None)
    if dt is None:
        return str(dev).strip().lower().split(":")[0]
    return str(dt).strip().lower()


def _check_tensor_devices(module: Any, context: str = "") -> tuple[bool, str]:
    """Enumerate parameters and buffers from *module*; reject CUDA/meta tensors.

    Returns (True, "") if all tensors are safe, (False, reason) otherwise.
    Does NOT call torch.cuda APIs.
    """
    def check_collection(method_name: str, label: str) -> tuple[bool, str]:
        method = getattr(module, method_name, None)
        if not callable(method):
            return False, f"{context}{method_name} is not inspectable"
        try:
            try:
                values: Any = method(recurse=True)
            except TypeError:
                values = method()
            for entry in values:
                if isinstance(entry, tuple) and len(entry) == 2:
                    name, tensor = entry
                else:
                    name, tensor = "<unnamed>", entry
                if getattr(tensor, "is_meta", False):
                    return False, f"{context}{label} {name} is meta"
                dt = _tensor_device_type(tensor)
                if dt is not None and (dt.startswith("cuda") or dt == "meta"):
                    return False, f"{context}{label} {name} on {dt}"
        except Exception as exc:
            return False, f"{context}{method_name} could not be inspected: {exc}"
        return True, ""

    ok, reason = check_collection("named_parameters", "parameter")
    if not ok:
        return False, reason
    ok, reason = check_collection("named_buffers", "buffer")
    if not ok:
        return False, reason

    return True, ""


def _is_module_like(obj: Any) -> bool:
    """Check if *obj* looks like a torch.nn.Module (duck-typing)."""
    if obj is None:
        return False
    return (hasattr(obj, "named_parameters") and callable(obj.named_parameters)
            and hasattr(obj, "named_buffers") and callable(obj.named_buffers))


def _collect_unet_modules(obj: Any) -> list[tuple[str, Any]]:
    """Collect inspectable torch-like modules from a UNET wrapper."""
    result: list[tuple[str, Any]] = []
    model = getattr(obj, "model", None)
    if model is not None and _is_module_like(model):
        result.append(("model", model))
        dm = getattr(model, "diffusion_model", None)
        if dm is not None and _is_module_like(dm) and dm is not model:
            result.append(("model.diffusion_model", dm))
    elif model is not None:
        # model itself isn't a module â€” try diffusion_model directly
        dm = getattr(model, "diffusion_model", None)
        if dm is not None and _is_module_like(dm):
            result.append(("model.diffusion_model", dm))
    dm = getattr(obj, "diffusion_model", None)
    if dm is not None and _is_module_like(dm) and all(module is not dm for _, module in result):
        result.append(("diffusion_model", dm))
    return result


def _collect_clip_modules(obj: Any) -> list[tuple[str, Any]]:
    """Collect inspectable torch-like modules from a CLIP wrapper."""
    result: list[tuple[str, Any]] = []
    csm = getattr(obj, "cond_stage_model", None)
    if csm is not None and _is_module_like(csm):
        result.append(("cond_stage_model", csm))
        for sub_attr in ("clip_l", "clip_g"):
            sub = getattr(csm, sub_attr, None)
            if sub is not None and _is_module_like(sub) and sub is not csm:
                result.append((f"cond_stage_model.{sub_attr}", sub))
    elif csm is not None:
        for sub_attr in ("clip_l", "clip_g"):
            sub = getattr(csm, sub_attr, None)
            if sub is not None and _is_module_like(sub):
                result.append((f"cond_stage_model.{sub_attr}", sub))
    if not result:
        # Try clip_l / clip_g directly on obj
        for sub_attr in ("clip_l", "clip_g"):
            sub = getattr(obj, sub_attr, None)
            if sub is not None and _is_module_like(sub):
                result.append((sub_attr, sub))
    if not result:
        # Fallback to patcher.model
        patcher = getattr(obj, "patcher", None)
        if patcher is not None:
            pm = getattr(patcher, "model", None)
            if pm is not None and _is_module_like(pm):
                result.append(("patcher.model", pm))
    return result


def _is_valid_unet_patcher(obj: Any) -> tuple[bool, str]:
    """Validate UNET patcher shape and tensor devices.

    Returns (True, "") on success, (False, reason) on failure.
    """
    if not hasattr(obj, "model"):
        return False, "unet missing .model attribute"
    if not hasattr(obj, "load_device"):
        return False, "unet missing .load_device attribute"
    if not hasattr(obj, "offload_device"):
        return False, "unet missing .offload_device attribute"

    modules = _collect_unet_modules(obj)
    if not modules:
        return False, "unet cannot locate inspectable torch module"

    for name, mod in modules:
        ok, reason = _check_tensor_devices(mod, f"unet.{name}.")
        if not ok:
            return False, reason

    # Also verify load_device/offload_device strings are not CUDA/meta
    for attr_name in ("load_device", "offload_device"):
        dev = getattr(obj, attr_name, None)
        if dev is not None:
            dt = _tensor_device_type_of_value(dev)
            if dt is not None and (dt.startswith("cuda") or dt == "meta"):
                return False, f"unet.{attr_name} is {dt}"

    return True, ""


def _is_valid_clip_patcher(obj: Any) -> tuple[bool, str]:
    """Validate CLIP patcher shape and tensor devices.

    Returns (True, "") on success, (False, reason) on failure.
    """
    patcher = getattr(obj, "patcher", None)
    if patcher is None:
        return False, "clip missing .patcher attribute"
    if not hasattr(patcher, "load_device"):
        return False, "clip.patcher missing .load_device attribute"
    if not hasattr(patcher, "offload_device"):
        return False, "clip.patcher missing .offload_device attribute"

    tokenizer = getattr(obj, "tokenizer", None)
    if tokenizer is None:
        return False, "clip missing .tokenizer attribute"

    modules = _collect_clip_modules(obj)
    if not modules:
        return False, "clip cannot locate inspectable torch module"

    for name, mod in modules:
        ok, reason = _check_tensor_devices(mod, f"clip.{name}.")
        if not ok:
            return False, reason

    # Also verify load_device/offload_device strings
    for attr_name in ("load_device", "offload_device"):
        dev = getattr(patcher, attr_name, None)
        if dev is not None:
            dt = _tensor_device_type_of_value(dev)
            if dt is not None and (dt.startswith("cuda") or dt == "meta"):
                return False, f"clip.patcher.{attr_name} is {dt}"

    return True, ""


def _is_valid_vae(obj: Any) -> tuple[bool, str]:
    """Validate VAE wrapper shape and tensor devices.

    A ComfyUI ``comfy.sd.VAE`` exposes ``.patcher`` (a ModelPatcher with
    ``load_device``/``offload_device``) and ``.first_stage_model`` (the
    concrete torch module holding the weights).

    Returns (True, "") on success, (False, reason) on failure.
    """
    if not hasattr(obj, "patcher"):
        return False, "vae missing .patcher attribute"
    patcher = getattr(obj, "patcher", None)
    if not hasattr(patcher, "load_device"):
        return False, "vae.patcher missing .load_device attribute"
    if not hasattr(patcher, "offload_device"):
        return False, "vae.patcher missing .offload_device attribute"

    first_stage = getattr(obj, "first_stage_model", None)
    if first_stage is None or not _is_module_like(first_stage):
        return False, "vae cannot locate inspectable first_stage_model module"

    ok, reason = _check_tensor_devices(first_stage, "vae.first_stage_model.")
    if not ok:
        return False, reason

    # Also verify load_device/offload_device strings are not CUDA/meta
    for attr_name in ("load_device", "offload_device"):
        dev = getattr(patcher, attr_name, None)
        if dev is not None:
            dt = _tensor_device_type_of_value(dev)
            if dt is not None and (dt.startswith("cuda") or dt == "meta"):
                return False, f"vae.patcher.{attr_name} is {dt}"

    return True, ""


def _tensor_device_type_of_value(val: Any) -> str | None:
    """Extract device type string from a device value (string or torch.device)."""
    if val is None:
        return None
    if isinstance(val, str):
        return val.strip().lower().split(":")[0]
    dt = getattr(val, "type", None)
    if dt is None:
        return str(val).strip().lower().split(":")[0]
    return str(dt).strip().lower()


def _vae_policy_from_model_key(model_key: ModelRestoreKey) -> dict[str, Any]:
    return {
        "vae_policy_version": int(getattr(model_key, "vae_policy_version", VAE_POLICY_VERSION) or 0),
        "vae_weight_dtype": str(getattr(model_key, "vae_weight_dtype", "float32") or ""),
        "vae_compute_dtype": str(getattr(model_key, "vae_compute_dtype", "float32") or ""),
        "vae_memory_format": str(getattr(model_key, "vae_memory_format", "contiguous") or ""),
        "vae_prefetch_mode": str(getattr(model_key, "vae_policy_metadata", {}).get("vae_prefetch_mode", "") if isinstance(getattr(model_key, "vae_policy_metadata", {}), Mapping) else ""),
        "c5_impl_version": str(getattr(model_key, "vae_policy_metadata", {}).get("c5_impl_version", "") if isinstance(getattr(model_key, "vae_policy_metadata", {}), Mapping) else ""),
    }


def _vae_module(vae: Any) -> Any:
    module = getattr(vae, "first_stage_model", None) if vae is not None else None
    return module if _is_module_like(module) else None


def _vae_supports_channels_last(torch: Any) -> bool:
    """Best-effort capability probe for channels_last (no CUDA init).

    Returns True only when a 4-D tensor can actually be materialized in
    channels_last memory format on the current torch build.  Used to keep
    channels-last latent handling explicit only when supported — unsupported
    tensors are never forced.
    """
    if not hasattr(torch, "channels_last"):
        return False
    try:
        probe = torch.zeros(1, 4, 8, 8)
        converted = probe.contiguous(memory_format=torch.channels_last)
        return bool(converted.is_contiguous(memory_format=torch.channels_last))
    except Exception:
        return False


def _validate_vae_policy_metadata(
    vae: Any,
    policy: Mapping[str, Any],
    *,
    storage_registry: StorageRegistry | None = None,
    context: str = "",
) -> tuple[dict[str, Any], StorageRegistry]:
    """Convert and validate one VAE once during CPU snapshot construction."""
    import torch

    module = _vae_module(vae)
    if module is None:
        raise RuntimeError(f"{context}VAE first_stage_model is not inspectable")
    weight_dtype_name = str(policy.get("vae_weight_dtype", "float32"))
    if weight_dtype_name == "bfloat16":
        expected_dtype = torch.bfloat16
    elif weight_dtype_name == "float32":
        expected_dtype = torch.float32
    else:
        raise RuntimeError(
            f"{context}unsupported VAE weight dtype {weight_dtype_name!r}"
        )

    for tensor in tuple(module.parameters()) + tuple(module.buffers()):
        if getattr(tensor, "is_floating_point", lambda: False)():
            tensor.data = tensor.data.to(dtype=expected_dtype)

    memory_format = str(policy.get("vae_memory_format", "contiguous"))
    channels_last_supported = False
    if memory_format == "channels_last":
        channels_last_supported = _vae_supports_channels_last(torch)
        if not channels_last_supported:
            raise RuntimeError(
                f"{context}channels_last memory format requested but unsupported "
                "for this torch/build; refusing to force unsupported tensors"
            )
        for tensor in tuple(module.parameters()) + tuple(module.buffers()):
            if getattr(tensor, "ndim", 0) == 4:
                tensor.data = tensor.data.contiguous(memory_format=torch.channels_last)
    elif memory_format != "contiguous":
        raise RuntimeError(f"{context}unsupported VAE memory format {memory_format!r}")

    if hasattr(vae, "vae_dtype"):
        vae.vae_dtype = expected_dtype
    policy_marker = dict(policy)
    policy_marker.setdefault("vae_prefetch_mode", vae_prefetch_mode())
    policy_marker.setdefault("c5_impl_version", C5_IMPL_VERSION)
    policy_marker.setdefault("vae_policy_provenance", "")
    try:
        from types import MappingProxyType
        vae._comfy_modal_vae_policy = MappingProxyType(policy_marker)
    except Exception:
        vae._comfy_modal_vae_policy = policy_marker
    vae._comfy_modal_vae_autocast_enabled = (
        str(policy.get("vae_compute_dtype", "")) == "bfloat16_autocast"
    )
    vae._comfy_modal_vae_memory_format = memory_format
    vae._comfy_modal_vae_latent_channels_last_required = (
        memory_format == "channels_last" and channels_last_supported
    )

    registry = storage_registry or build_unique_storage_registry(vae)
    floating_parameter_count = 0
    floating_buffer_count = 0
    mismatched_count = 0
    floating_parameter_numel = 0
    floating_buffer_numel = 0
    for tensor in module.parameters():
        if tensor.is_floating_point():
            floating_parameter_count += 1
            floating_parameter_numel += int(tensor.numel())
            _mismatch = tensor.dtype != expected_dtype or _tensor_device_type(tensor) != "cpu"
            if memory_format == "channels_last" and tensor.ndim == 4 and not tensor.is_contiguous(memory_format=torch.channels_last):
                _mismatch = True
            if memory_format == "contiguous" and not tensor.is_contiguous():
                _mismatch = True
            if _mismatch:
                mismatched_count += 1
    for tensor in module.buffers():
        if tensor.is_floating_point():
            floating_buffer_count += 1
            floating_buffer_numel += int(tensor.numel())
            _mismatch = tensor.dtype != expected_dtype or _tensor_device_type(tensor) != "cpu"
            if memory_format == "channels_last" and tensor.ndim == 4 and not tensor.is_contiguous(memory_format=torch.channels_last):
                _mismatch = True
            if memory_format == "contiguous" and not tensor.is_contiguous():
                _mismatch = True
            if _mismatch:
                mismatched_count += 1
    if floating_parameter_count + floating_buffer_count == 0:
        raise RuntimeError(f"{context}VAE has no floating parameters or buffers")
    if mismatched_count:
        raise RuntimeError(
            f"{context}VAE policy validation failed: mismatched_parameter_buffer_count={mismatched_count}"
        )
    metadata = {
        **policy_marker,
        "object_id": str(id(vae)),
        "weight_dtype": weight_dtype_name,
        "compute_dtype": str(policy.get("vae_compute_dtype", "")),
        "memory_format": memory_format,
        "channels_last_supported": channels_last_supported,
        "latent_channels_last_required": bool(
            memory_format == "channels_last" and channels_last_supported
        ),
        "vae_prefetch_mode": policy_marker.get("vae_prefetch_mode", vae_prefetch_mode()),
        "c5_impl_version": policy_marker.get("c5_impl_version", C5_IMPL_VERSION),
        **capture_c5_runtime_metadata(),
        "total_storage_bytes": registry.total_bytes,
        "floating_parameter_count": floating_parameter_count,
        "floating_buffer_count": floating_buffer_count,
        "floating_parameter_numel": floating_parameter_numel,
        "floating_buffer_numel": floating_buffer_numel,
        "mismatched_parameter_buffer_count": mismatched_count,
    }
    if hasattr(vae, "size"):
        vae.size = registry.total_bytes
    patcher = getattr(vae, "patcher", None)
    if patcher is not None and hasattr(patcher, "size"):
        try:
            patcher.size = registry.total_bytes
        except Exception:
            pass
    vae._comfy_modal_vae_validation_metadata = dict(metadata)
    vae._comfy_modal_vae_storage_registry = registry
    return metadata, registry


# ---------------------------------------------------------------------------
# BF16-native validation
# ---------------------------------------------------------------------------


def _build_detail_str(
    requested_weight_dtype: str = "",
    effective_weight_dtype: Any = None,
    effective_compute_dtype: Any = None,
    target_gpus: tuple[str, ...] | None = None,
) -> str:
    _parts: list[str] = []
    if requested_weight_dtype:
        _parts.append(f"requested_weight_dtype={requested_weight_dtype}")
    if effective_weight_dtype is not None:
        _parts.append(f"effective_weight_dtype={effective_weight_dtype}")
    if effective_compute_dtype is not None:
        _parts.append(f"effective_compute_dtype={effective_compute_dtype}")
    if target_gpus:
        _parts.append(f"target_gpus={','.join(target_gpus)}")
    return " ".join(_parts) + " " if _parts else ""


def validate_snapshot_unet_bf16_native(
    unet: Any,
    *,
    context: str = "",
    target_gpus: tuple[str, ...] | None = None,
    requested_weight_dtype: str = "",
    effective_weight_dtype: Any = None,
    effective_compute_dtype: Any = None,
    param_distribution: dict[str, Any] | None = None,
) -> None:
    """Strict post-construction validation for BF16-native compute policy.

    Resolves the real diffusion model via ``unet.model.diffusion_model``
    (ComfyUI ModelPatcher structure), then verifies:
      - ``manual_cast_dtype`` on the inner BaseModel is ``None`` (absent)
      - ``model_dtype()`` on the patcher returns bfloat16
      - All floating-point parameters are CPU bfloat16 (no CUDA/meta/fp32/mixed)
      - Non-zero floating parameters (detects uninspected state)

    Uses ``inspect_and_validate_snapshot_params`` with
    ``expected_dtype=None, require_cpu=False`` to capture the full parameter
    distribution first, then evaluates all invariants.

    Every failure includes all metadata fields.  Does not fail before
    distribution is obtained except when the diffusion model is uninspectable
    (distribution shows ``"unavailable"``).

    When *param_distribution* is provided (pre-computed), it is included
    directly rather than re-inspecting.
    """
    import torch as _torch

    _detail_str = _build_detail_str(
        requested_weight_dtype, effective_weight_dtype,
        effective_compute_dtype, target_gpus,
    )

    if unet is None:
        raise RuntimeError(
            f"{context}BF16-native validation failed: unet is None. "
            f"{_detail_str}"
        )

    # â”€â”€ Resolve the actual diffusion model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _model = getattr(unet, "model", None)
    if _model is None:
        raise RuntimeError(
            f"{context}BF16-native validation failed: unet missing .model attribute. "
            f"{_detail_str}"
        )
    _dm = getattr(_model, "diffusion_model", _model)

    # â”€â”€ Read manual_cast_dtype from inner BaseModel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _manual = getattr(_model, "manual_cast_dtype", None)
    _manual_str = str(_manual) if _manual is not None else "none"

    # â”€â”€ Read model_dtype() from patcher â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _md_fn = getattr(unet, "model_dtype", None)
    _model_dtype_str: str = "absent"
    if callable(_md_fn):
        try:
            _md_val = _md_fn()
            _model_dtype_str = str(_md_val)
        except Exception:
            _model_dtype_str = "error"

    # â”€â”€ Capture parameter distribution (full, no early raise) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _distribution: dict[str, Any] | str = "unavailable"
    if param_distribution is not None:
        _distribution = param_distribution
    else:
        try:
            _distribution = inspect_and_validate_snapshot_params(
                _dm,
                expected_dtype=None,
                require_cpu=False,
                context=f"{context}dist:",
            )
        except Exception:
            _distribution = "unavailable"

    # â”€â”€ Build full metadata string for all error messages â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _full_msg(checks: list[str]) -> str:
        _parts = [f"{context}BF16-native validation failed"]
        if checks:
            _parts.append("; ".join(checks))
        _parts.append(
            f"{_detail_str}"
            f"model_dtype={_model_dtype_str} "
            f"manual_cast_dtype={_manual_str} "
            f"param_distribution={_distribution}"
        )
        return " ".join(_parts)

    # â”€â”€ Invariant 1: manual_cast_dtype must be None â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if _manual is not None:
        raise RuntimeError(_full_msg([
            f"manual_cast_dtype is {_manual!r}, expected None",
        ]))

    # â”€â”€ Invariant 2: model_dtype() must be bfloat16 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if _model_dtype_str not in (str(_torch.bfloat16), "torch.bfloat16"):
        raise RuntimeError(_full_msg([
            f"model_dtype={_model_dtype_str}, expected bfloat16",
        ]))

    # â”€â”€ Invariant 3: non-zero floating params, all BF16 on CPU â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if isinstance(_distribution, str) and _distribution == "unavailable":
        raise RuntimeError(_full_msg([
            "diffusion model is uninspectable (no parameters accessible)",
        ]))

    _dist_count = _distribution.get("param_count", 0)
    _fp_dist = _distribution.get("param_dev_dtype_numel", {})
    _total_fp_numel = sum(_fp_dist.values())
    _bf16_cpu_numel = _fp_dist.get("cpu|torch.bfloat16", 0)
    _non_bf16 = {k: v for k, v in _fp_dist.items() if k != "cpu|torch.bfloat16"}
    _non_cpu = {k: v for k, v in _fp_dist.items()
                if not k.startswith("cpu|")}

    if _total_fp_numel == 0:
        raise RuntimeError(_full_msg([
            "zero floating-point parameters found (model state not inspected)",
            f"param_count={_dist_count}",
        ]))

    _checks: list[str] = []
    if _non_cpu:
        _checks.append(f"non-CPU devices: {dict(list(_non_cpu.items())[:10])}")
    if _non_bf16:
        _checks.append(f"non-BF16 floating params: {dict(list(_non_bf16.items())[:10])}")
    if _bf16_cpu_numel != _total_fp_numel:
        missing = _total_fp_numel - _bf16_cpu_numel
        _checks.append(
            f"bf16_numel={_bf16_cpu_numel}/{_total_fp_numel} "
            f"({missing} numel non-BF16 on CPU)"
        )

    if _checks:
        raise RuntimeError(_full_msg(_checks))


# ---------------------------------------------------------------------------
# Parameter distribution / validation helper
# ---------------------------------------------------------------------------


def inspect_and_validate_snapshot_params(
    model: Any,
    *,
    expected_dtype: Any = None,
    require_cpu: bool = True,
    context: str = "",
) -> dict[str, Any]:
    """Inspect ALL parameters of *model*, report distribution, and validate.

    Iterates every parameter in the model (not just the first), collecting
    device and dtype metadata across all parameters.  For floating-point
    parameters, also reports count/numel grouped by ``device|dtype``.

    Returns a dict with:
      - ``param_count``: total number of parameters.
      - ``total_param_numel``: total number of elements across all params.
      - ``param_dev_dtype_count``: ``{device|dtype: count}`` across all
        floating-point parameters.
      - ``param_dev_dtype_numel``: ``{device|dtype: numel}`` across all
        floating-point parameters.
      - ``param_distribution_hash``: SHA-256 of sorted ``(device, dtype,
        numel)`` tuples for deterministic change detection.

    Raises ``RuntimeError`` when:
      - *require_cpu* is True and any parameter's device type is not ``cpu``.
      - *expected_dtype* is not None and any floating-point parameter has a
        different dtype (stale-FP32 snapshot detection).

    This helper uses ``model.parameters()`` which returns ALL parameters
    including those nested in submodules.  It never mutates the model or
    calls CUDA synchronisation.
    """
    import hashlib
    _param_count = 0
    _total_param_numel = 0
    _fp_dev_dtype_count: dict[str, int] = {}
    _fp_dev_dtype_numel: dict[str, int] = {}
    _param_tuples: list[tuple[str, str, int]] = []
    _any_non_cpu: list[str] = []
    _total_fp = 0
    _fp_of_expected_dtype = 0

    try:
        for _p in model.parameters():
            _param_count += 1
            _numel = _p.numel()
            _total_param_numel += _numel
            _dev_str = str(_p.device)
            _dtype_str = str(_p.dtype)
            if _p.is_floating_point():
                _key = f"{_dev_str}|{_dtype_str}"
                _fp_dev_dtype_count[_key] = _fp_dev_dtype_count.get(_key, 0) + 1
                _fp_dev_dtype_numel[_key] = _fp_dev_dtype_numel.get(_key, 0) + _numel
                _param_tuples.append((_dev_str, _dtype_str, _numel))
                _total_fp += _numel
                if expected_dtype is not None and _p.dtype == expected_dtype:
                    _fp_of_expected_dtype += _numel
            if require_cpu:
                _dev_type = _dev_str.strip().lower().split(":")[0]
                if _dev_type != "cpu":
                    _any_non_cpu.append(_dev_str)
    except Exception as exc:
        raise RuntimeError(f"{context}parameter inspection failed: {exc}") from exc

    _param_tuples.sort(key=lambda _x: (_x[0], _x[1], _x[2]))
    _param_h = hashlib.sha256()
    for _dev, _dt, _n in _param_tuples:
        _param_h.update(f"{_dev}|{_dt}|{_n}\n".encode())

    result: dict[str, Any] = {
        "param_count": _param_count,
        "total_param_numel": _total_param_numel,
        "param_dev_dtype_count": dict(_fp_dev_dtype_count),
        "param_dev_dtype_numel": dict(_fp_dev_dtype_numel),
        "param_distribution_hash": _param_h.hexdigest(),
    }

    if _any_non_cpu:
        raise RuntimeError(
            f"{context}non-CPU parameters found: {_any_non_cpu[:5]}... "
            f"({len(_any_non_cpu)} total)"
        )

    if expected_dtype is not None and _total_fp > 0 and _fp_of_expected_dtype != _total_fp:
        raise RuntimeError(
            f"{context}floating-point parameter dtype mismatch: "
            f"expected {expected_dtype}, matching_numel={_fp_of_expected_dtype}, "
            f"total_floating_numel={_total_fp}. "
            f"Distribution: {dict(_fp_dev_dtype_count)}"
        )

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# â”€â”€ Object-ID keys excluded from semantic diff â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_OBJECT_ID_KEYS: frozenset[str] = frozenset({
    "patcher_object_id",
    "model_object_id",
    "diffusion_model_object_id",
})

# ---------------------------------------------------------------------------
# UNET runtime-state collector, differ, and rehydration helper
# ---------------------------------------------------------------------------


def _first_tensor_info(iterator_fn: Callable[..., Any]) -> tuple[str, str]:
    """Inspect exactly the first item from *iterator_fn(recurse=True)*.

    Uses ``next(iter(...), None)`` â€” never calls ``list()``, never inspects
    a second tensor.  Returns ``(device_str, dtype_str)`` or
    ``("absent", "absent")`` on any failure.
    """
    try:
        it = iterator_fn(recurse=True)
        if it is None:
            return ("absent", "absent")
        entry = next(iter(it), None)
        if entry is None:
            return ("absent", "absent")
        if isinstance(entry, tuple) and len(entry) == 2:
            _name, tensor = entry
        else:
            tensor = entry
        _dev = str(getattr(tensor, "device", "absent"))
        _dtype = str(getattr(tensor, "dtype", "absent"))
        return (_dev, _dtype)
    except Exception:
        return ("absent", "absent")


def _safe_str(val: Any) -> str:
    """Return ``str(val)`` when *val* is not callable and not ``None``.

    Returns ``"absent"`` for callable objects, ``None``, or any exception.
    """
    if val is None:
        return "absent"
    if callable(val):
        return "absent"
    try:
        return str(val)
    except Exception:
        return "absent"


def _safe_str_of_attr(obj: Any, attr: str) -> str:
    """Safely stringify *getattr(obj, attr, None)*.

    Returns ``"absent"`` when the attribute is missing, callable, or
    cannot be converted to string.
    """
    val = getattr(obj, attr, None)
    return _safe_str(val)


def collect_unet_runtime_state(
    unet: Any,
    *,
    model_management: Any = None,
) -> dict[str, Any]:
    """Capture the current runtime state of a ComfyUI ModelPatcher for UNET.

    Returns a flat dict with the fields specified in the comfymodal
    runtime-state comparison protocol.  Inspects at most one parameter
    and one buffer (``next(iter(...))`` â€” never ``list()``).  No mutation,
    no CUDA synchronisation, no tensor content.

    For a real ``comfy.model_patcher.ModelPatcher``:

    * ``model_dtype`` is a **method** â€” called safely.
    * ``manual_cast_dtype`` / ``device`` / ``model_loaded_weight_memory`` /
      ``model_lowvram`` / ``lowvram_patch_counter`` live on ``.model``
      (patches a long-standing bug where the previous code read them
      from the wrong object).
    * ``transformer_options`` is nested under ``model_options``.
    * ``diffusion_model`` (on ``.model``) owns ``forward``.
    * ``loaded_models`` is a **function** call.
    """
    state: dict[str, Any] = {}

    _model = getattr(unet, "model", None)
    _dm = None
    if _model is not None:
        _dm = getattr(_model, "diffusion_model", None)
    elif hasattr(unet, "diffusion_model"):
        _dm = getattr(unet, "diffusion_model", None)

    _MISSING = object()

    # â”€â”€ Type identities â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    state["patcher_type"] = type(unet).__qualname__ if not isinstance(unet, (int, float, bool, str, bytes)) else type(unet).__name__
    state["model_type"] = type(_model).__qualname__ if _model is not None else "absent"
    state["diffusion_model_type"] = type(_dm).__qualname__ if _dm is not None else "absent"

    # â”€â”€ Object identities (included in raw records, excluded from diff) â”€
    state["patcher_object_id"] = str(id(unet))
    state["model_object_id"] = str(id(_model)) if _model is not None else "absent"
    state["diffusion_model_object_id"] = str(id(_dm)) if _dm is not None else "absent"

    # â”€â”€ Device attributes (on patcher) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    state["load_device"] = _safe_str_of_attr(unet, "load_device")
    state["offload_device"] = _safe_str_of_attr(unet, "offload_device")

    # â”€â”€ current_device = model.device (not from first parameter) â”€â”€â”€â”€â”€â”€â”€
    state["current_device"] = _safe_str(getattr(_model, "device", None)) if _model is not None else "absent"

    # â”€â”€ First parameter / first buffer (diffusion_model first, model fallback) â”€
    _inspect_module = _dm if _dm is not None else _model
    if _inspect_module is not None:
        _fp_dev, _fp_dtype = _first_tensor_info(_inspect_module.named_parameters)
        _fb_dev, _fb_dtype = _first_tensor_info(_inspect_module.named_buffers)
    else:
        _fp_dev, _fp_dtype = ("absent", "absent")
        _fb_dev, _fb_dtype = ("absent", "absent")
    state["first_parameter_device"] = _fp_dev
    state["first_parameter_dtype"] = _fp_dtype
    state["first_buffer_device"] = _fb_dev
    state["first_buffer_dtype"] = _fb_dtype

    # â”€â”€ Model dtype fields â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # model_dtype is a method on the patcher; call it safely.
    _md_fn = getattr(unet, "model_dtype", None)
    if callable(_md_fn):
        try:
            state["model_dtype"] = str(_md_fn())
        except Exception:
            state["model_dtype"] = "absent"
    else:
        state["model_dtype"] = "absent"

    state["manual_cast_dtype"] = _safe_str_of_attr(_model, "manual_cast_dtype") if _model is not None else "absent"
    state["weight_dtype"] = _safe_str_of_attr(unet, "weight_dtype")

    # â”€â”€ Options â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _mo = getattr(unet, "model_options", _MISSING)
    if _mo is _MISSING:
        state["model_options_keys"] = "absent"
    elif isinstance(_mo, dict):
        state["model_options_keys"] = sorted(str(k) for k in _mo.keys())
    else:
        state["model_options_keys"] = "absent"
    # transformer_options is nested under model_options
    if isinstance(_mo, dict):
        _to = _mo.get("transformer_options", _MISSING)
        if isinstance(_to, dict):
            state["transformer_options_keys"] = sorted(str(k) for k in _to.keys())
        else:
            state["transformer_options_keys"] = "absent"
    else:
        state["transformer_options_keys"] = "absent"

    # â”€â”€ Patch counters â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _patches = getattr(unet, "patches", _MISSING)
    if _patches is _MISSING:
        state["patch_count"] = "absent"
    elif isinstance(_patches, dict):
        state["patch_count"] = len(_patches)
    else:
        state["patch_count"] = "absent"
    _obj_patches = getattr(unet, "object_patches", _MISSING)
    if _obj_patches is _MISSING:
        state["object_patch_count"] = "absent"
    elif isinstance(_obj_patches, dict):
        state["object_patch_count"] = len(_obj_patches)
    else:
        state["object_patch_count"] = "absent"

    # â”€â”€ Model-level memory / lowvram (on .model) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    state["model_loaded_weight_memory"] = _safe_str_of_attr(_model, "model_loaded_weight_memory") if _model is not None else "absent"
    state["model_lowvram"] = _safe_str_of_attr(_model, "model_lowvram") if _model is not None else "absent"
    state["model_lowvram_patch_counter"] = _safe_str_of_attr(_model, "lowvram_patch_counter") if _model is not None else "absent"

    # â”€â”€ Forward function (from diffusion_model, not patcher) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if _dm is not None:
        _forward = getattr(_dm, "forward", None)
    else:
        _forward = getattr(_model, "forward", None) if _model is not None else None
    if _forward is not None:
        _self = getattr(_forward, "__self__", None)
        state["forward_module"] = type(_self).__qualname__ if _self is not None else "absent"
        state["forward_qualname"] = str(getattr(_forward, "__qualname__", "absent"))
    else:
        state["forward_module"] = "absent"
        state["forward_qualname"] = "absent"

    # â”€â”€ loaded_models membership (function call) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _loaded = "absent"
    if model_management is not None:
        try:
            _lm_fn = getattr(model_management, "loaded_models", None)
            if callable(_lm_fn):
                _lm = _lm_fn()
                if isinstance(_lm, (list, tuple)):
                    _present = any(_item is unet for _item in _lm)
                    _loaded = str(int(_present))
                else:
                    _loaded = "absent"
            else:
                _loaded = "absent"
        except Exception:
            _loaded = "absent"
    state["loaded_models_member"] = _loaded

    return state


def _two_lane_read_residency(unet: Any) -> dict[str, Any]:
    """Read the ComfyUI residency fields for the graph early-exit proof.

    ComfyUI's ``ModelPatcher.partially_load`` early-exits (returns ``0``
    without transferring weights) when ``model_lowvram is False`` and
    ``model_loaded_weight_memory > 0`` — the patcher metadata claims the
    full model is already resident.  In the pinned parent ComfyUI both
    fields live on ``ModelPatcher.model`` (the **BaseModel**), not on the
    patcher wrapper itself and not on the inner diffusion model.

    This proof reads both fields from a deduplicated candidate list
    ``[patcher, patcher.model, patcher.model.diffusion_model]`` — the
    BaseModel is the always-checked, preferred target — and synthesizes a
    JSON-safe, fail-closed verdict: it never claims the model is resident
    unless the fields are actually present and readable.  Never raises.
    """
    _candidates: list[Any] = []
    _seen: set[int] = set()

    def _add(obj: Any) -> None:
        if obj is None:
            return
        _oid = id(obj)
        if _oid in _seen:
            return
        _seen.add(_oid)
        _candidates.append(obj)

    _patcher = unet
    _add(_patcher)
    _base = getattr(_patcher, "model", None)
    _add(_base)
    # Safely useful nested target: the BaseModel's inner diffusion model.
    if _base is not None:
        _add(getattr(_base, "diffusion_model", None))

    def _read(attr: str):
        # The always-checked BaseModel is authoritative first.
        if _base is not None:
            _val = getattr(_base, attr, None)
            if _val is not None and not callable(_val):
                return _val
        for _cand in _candidates:
            _val = getattr(_cand, attr, None)
            if _val is None or callable(_val):
                continue
            return _val
        return None

    _lowvram = _read("model_lowvram")
    _mem = _read("model_loaded_weight_memory")

    out: dict[str, Any] = {
        "candidate_count": len(_candidates),
        "base_model_present": _base is not None,
        "model_lowvram": "absent",
        "model_loaded_weight_memory": "absent",
        "source": "none",
        "resident": False,
        "ok": False,
        "reason": "fields_unavailable",
    }
    if _lowvram is None or _mem is None:
        return out

    try:
        _lowvram_bool = bool(_lowvram)
    except Exception:  # noqa: BLE001
        _lowvram_bool = False
    try:
        _mem_num = float(_mem)
    except Exception:  # noqa: BLE001
        _mem_num = 0.0

    _resident = (_lowvram_bool is False) and (_mem_num > 0)
    out["model_lowvram"] = _lowvram_bool
    out["model_loaded_weight_memory"] = _mem_num
    out["source"] = "base_model" if _base is not None else "candidate"
    out["resident"] = bool(_resident)
    out["ok"] = True
    out["reason"] = "resident" if _resident else "not_resident"
    return out


def diff_unet_runtime_states(
    snapshot_state: dict[str, Any],
    normal_state: dict[str, Any],
) -> dict[str, Any]:
    """Return only semantically meaningful differing fields.

    **Excludes** machine-local object IDs (``patcher_object_id``,
    ``model_object_id``, ``diffusion_model_object_id``) that are
    never meaningful across processes.

    Keys present in both dicts whose string values differ are included.
    Keys present in only one dict are included with their value from the
    dict that has them.  Returns an empty dict when states are identical.
    """
    diff: dict[str, Any] = {}
    all_keys = set(snapshot_state.keys()) | set(normal_state.keys())
    for key in sorted(all_keys):
        if key in _OBJECT_ID_KEYS:
            continue
        sv = snapshot_state.get(key, "<missing>")
        nv = normal_state.get(key, "<missing>")
        if str(sv) != str(nv):
            diff[key] = {"snapshot": sv, "normal": nv}
    return diff


def collect_unet_forward_probe_state(
    unet: Any,
    *,
    diffusion_model: Any = None,
) -> dict[str, Any]:
    """Collect read-only diagnostic state from a UNET patcher and its
    diffusion model **immediately before** ``NextDiT.forward`` is called.

    The caller has already called ``load_models_gpu``.  This helper
    records identity, model-state fields, parameter/buffer distribution,
    forward-callable structure, and collector timing.

    **Safety (enforced by caller convention â€” never guaranteed at
    runtime)**: this function never calls ``.cpu()``, ``.cuda()``,
    ``.to()``, ``.item()``, ``.clone()``, ``.numpy()``,
    ``torch.cuda.synchronize()``, or ``load_models_gpu()``.  It never
    mutates models or tensors.

    Parameters
    ----------
    unet
        A ComfyUI ``ModelPatcher`` (or duck-typed equivalent) for a UNET.
    diffusion_model
        Optional explicit reference to the diffusion model (the
        ``torch.nn.Module`` that owns ``forward``).  When omitted the
        collector resolves it as ``unet.model.diffusion_model`` (then
        ``unet.diffusion_model`` as fallback).

    Returns
    -------
    dict[str, Any]
        Flat dictionary of probe fields (see module doctest or
        ``collect_unet_forward_probe_state`` tests for the full
        field list).
    """
    import hashlib
    import time

    _start_ns = time.monotonic_ns()

    state: dict[str, Any] = {}

    # â”€â”€ Resolve diffusion_model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _model = getattr(unet, "model", None)
    _dm: Any = diffusion_model
    if _dm is None:
        if _model is not None:
            _dm = getattr(_model, "diffusion_model", None)
        if _dm is None:
            _dm = getattr(unet, "diffusion_model", None)

    # â”€â”€ 1. Identity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    state["patcher_object_id"] = str(id(unet))
    state["patcher_type"] = type(unet).__qualname__

    state["model_object_id"] = str(id(_model)) if _model is not None else "absent"
    state["model_type"] = type(_model).__qualname__ if _model is not None else "absent"

    state["diffusion_model_object_id"] = str(id(_dm)) if _dm is not None else "absent"
    state["diffusion_model_type"] = type(_dm).__qualname__ if _dm is not None else "absent"

    # â”€â”€ 2. Model state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    state["load_device"] = _safe_str_of_attr(unet, "load_device")
    state["offload_device"] = _safe_str_of_attr(unet, "offload_device")

    _model_device = getattr(_model, "device", None) if _model is not None else None
    state["model_device"] = _safe_str(_model_device)

    # model_dtype() â€” callable method on patcher
    _md_fn = getattr(unet, "model_dtype", None)
    if callable(_md_fn):
        try:
            state["model_dtype"] = str(_md_fn())
        except Exception:
            state["model_dtype"] = "absent"
    else:
        state["model_dtype"] = "absent"

    state["manual_cast_dtype"] = (
        _safe_str_of_attr(_model, "manual_cast_dtype") if _model is not None else "absent"
    )
    state["model_loaded_weight_memory"] = (
        _safe_str_of_attr(_model, "model_loaded_weight_memory") if _model is not None else "absent"
    )
    state["model_lowvram"] = (
        _safe_str_of_attr(_model, "model_lowvram") if _model is not None else "absent"
    )
    state["lowvram_patch_counter"] = (
        _safe_str_of_attr(_model, "lowvram_patch_counter") if _model is not None else "absent"
    )

    # â”€â”€ 3. Parameter distribution â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _param_count = 0
    _total_param_numel = 0
    _param_dev_dtype_count: dict[str, int] = {}
    _param_dev_dtype_numel: dict[str, int] = {}
    _param_tuples: list[tuple[str, str, int]] = []

    if _dm is not None:
        try:
            for _p in _dm.parameters():
                _param_count += 1
                _numel = _p.numel()
                _total_param_numel += _numel
                _key = f"{_p.device}|{_p.dtype}"
                _param_dev_dtype_count[_key] = _param_dev_dtype_count.get(_key, 0) + 1
                _param_dev_dtype_numel[_key] = _param_dev_dtype_numel.get(_key, 0) + _numel
                _param_tuples.append((str(_p.device), str(_p.dtype), _numel))
        except Exception:
            pass

    _param_tuples.sort(key=lambda _x: (_x[0], _x[1], _x[2]))
    _param_h = hashlib.sha256()
    for _dev, _dt, _n in _param_tuples:
        _param_h.update(f"{_dev}|{_dt}|{_n}\n".encode())

    state["param_count"] = _param_count
    state["total_param_numel"] = _total_param_numel
    state["param_dev_dtype_count"] = dict(_param_dev_dtype_count)
    state["param_dev_dtype_numel"] = dict(_param_dev_dtype_numel)
    state["param_distribution_hash"] = _param_h.hexdigest()

    # â”€â”€ 4. Buffer distribution â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _buffer_count = 0
    _total_buffer_numel = 0
    _buf_dev_dtype_count: dict[str, int] = {}
    _buf_dev_dtype_numel: dict[str, int] = {}
    _buf_tuples: list[tuple[str, str, int]] = []

    if _dm is not None:
        try:
            for _b in _dm.buffers():
                _buffer_count += 1
                _numel = _b.numel()
                _total_buffer_numel += _numel
                _key = f"{_b.device}|{_b.dtype}"
                _buf_dev_dtype_count[_key] = _buf_dev_dtype_count.get(_key, 0) + 1
                _buf_dev_dtype_numel[_key] = _buf_dev_dtype_numel.get(_key, 0) + _numel
                _buf_tuples.append((str(_b.device), str(_b.dtype), _numel))
        except Exception:
            pass

    _buf_tuples.sort(key=lambda _x: (_x[0], _x[1], _x[2]))
    _buf_h = hashlib.sha256()
    for _dev, _dt, _n in _buf_tuples:
        _buf_h.update(f"{_dev}|{_dt}|{_n}\n".encode())

    state["buffer_count"] = _buffer_count
    state["total_buffer_numel"] = _total_buffer_numel
    state["buffer_dev_dtype_count"] = dict(_buf_dev_dtype_count)
    state["buffer_dev_dtype_numel"] = dict(_buf_dev_dtype_numel)
    state["buffer_distribution_hash"] = _buf_h.hexdigest()

    # â”€â”€ 5. Forward callable structure â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _forward_fn = getattr(_dm, "forward", None) if _dm is not None else None
    if _forward_fn is not None:
        _self = getattr(_forward_fn, "__self__", None)
        state["forward_module"] = type(_self).__qualname__ if _self is not None else "absent"
        state["forward_qualname"] = str(getattr(_forward_fn, "__qualname__", "absent"))

        # Wrapper chain via __wrapped__ (max depth 8)
        _wrapper_chain: list[str] = []
        _seen: set[int] = set()
        _fn = _forward_fn
        for _ in range(8):
            _wrapped = getattr(_fn, "__wrapped__", None)
            if _wrapped is None:
                break
            _wrapped_id = id(_wrapped)
            if _wrapped_id in _seen:
                break
            _seen.add(_wrapped_id)
            _wq = str(getattr(_wrapped, "__qualname__", ""))
            _wrapper_chain.append(_wq)
            _fn = _wrapped

        _wc_h = hashlib.sha256()
        for _entry in _wrapper_chain:
            _wc_h.update(f"{_entry}\n".encode())

        state["wrapper_chain"] = list(_wrapper_chain)
        state["wrapper_chain_hash"] = _wc_h.hexdigest()
    else:
        state["forward_module"] = "absent"
        state["forward_qualname"] = "absent"
        state["wrapper_chain"] = []
        state["wrapper_chain_hash"] = hashlib.sha256().hexdigest()

    # â”€â”€ 6. Collector metadata â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _elapsed_ms = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
    state["collector_duration_ms"] = _elapsed_ms

    return state


def rehydrate_cpu_snapshot_unet(
    unet: Any,
    *,
    model_management: Any,
    trace: Any = None,
) -> tuple[bool, str]:
    """Validate and re-target device attributes of a CPU-snapshot UNET.

    For this patch the helper must only:

    1. Validate that *unet* has ``.model``, ``.load_device``, and
       ``.offload_device`` attributes.
    2. Assign ``model_management.get_torch_device()`` to
       ``unet.load_device`` and ``model_management.unet_offload_device()``
       to ``unet.offload_device``.
    3. Emit pre/post runtime state when *trace* is provided.

    Returns ``(True, "ok")`` or ``(False, reason_string)``.

    Does **not** modify ``current_device``, change dtype/manual-cast
    fields, clear CacheDiT, call ``load_models_gpu``, reconstruct or
    reload the UNET, or copy state from another object.
    """
    # â”€â”€ Pre-state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _pre_state = collect_unet_runtime_state(unet, model_management=model_management)

    # â”€â”€ Validate shape â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not hasattr(unet, "model"):
        return False, "unet missing .model attribute"
    if not hasattr(unet, "load_device"):
        return False, "unet missing .load_device attribute"
    if not hasattr(unet, "offload_device"):
        return False, "unet missing .offload_device attribute"

    # â”€â”€ Validate required model_management functions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _gt = getattr(model_management, "get_torch_device", None)
    _uo = getattr(model_management, "unet_offload_device", None)
    if not callable(_gt):
        return False, "model_management.get_torch_device is not callable"
    if not callable(_uo):
        return False, "model_management.unet_offload_device is not callable"

    # â”€â”€ Assign devices â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        unet.load_device = _gt()
        unet.offload_device = _uo()
    except Exception as exc:
        return False, f"device assignment failed: {exc}"

    # â”€â”€ Post-state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _post_state = collect_unet_runtime_state(unet, model_management=model_management)

    # Emit pre/post trace when available
    if trace is not None:
        try:
            _pre_state_safe = {k: str(v) for k, v in _pre_state.items()}
            _post_state_safe = {k: str(v) for k, v in _post_state.items()}
            _diff = diff_unet_runtime_states(_pre_state, _post_state)
            trace.emit(
                "unet_rehydrate_pre_state",
                metadata={"state": _pre_state_safe},
            )
            trace.emit(
                "unet_rehydrate_post_state",
                metadata={"state": _post_state_safe},
            )
            if _diff:
                _diff_safe = {
                    k: {"snapshot": str(v.get("snapshot", "")), "normal": str(v.get("normal", ""))}
                    for k, v in _diff.items()
                }
                trace.emit(
                    "unet_rehydrate_diff",
                    metadata={"diff": _diff_safe, "changed_fields": sorted(_diff.keys())},
                )
        except Exception:
            pass

    return True, "ok"


def identity_from_profile(
    profile: Mapping[str, Any],
    *,
    resolve_path: Callable[[str, str], str],
) -> tuple[ModelRestoreKey, dict[str, Any], tuple[ModelFileFact, ...]]:
    """Build a ModelRestoreKey, model_spec, and file facts from a warmup profile.

    NOTE: compute policy identity is NOT included in model_spec; it is
    stored separately on CpuSnapshotModels.compute_policy.

    Returns
    -------
    (ModelRestoreKey, model_spec_dict, file_facts_tuple)

    Raises
    ------
    ValueError
        When the profile is missing required fields, has an unsupported
        mode, or contains malformed configuration.
    """
    if not isinstance(profile, Mapping):
        raise ValueError("profile must be a Mapping")

    raw = dict(profile)
    mode_value = raw.get("mode", "")
    if not isinstance(mode_value, str) or not mode_value.strip():
        raise ValueError("profile mode is required and must be a non-empty string")
    mode = mode_value.strip()
    if mode != "split":
        raise ValueError(f"unsupported profile mode: {mode!r}; only 'split' is supported")

    def required_text(key: str) -> str:
        value = raw.get(key, "")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"profile {key} is required and must be a non-empty string")
        return value.strip()

    unet = required_text("unet")
    clip1 = required_text("clip1")
    clip_type = required_text("clip_type")
    clip2 = raw.get("clip2", "")
    if clip2 is not None and not isinstance(clip2, str):
        raise ValueError("profile clip2 must be a string when provided")

    normalized = _normalize_profile(profile)
    model_key = _build_model_key(normalized)
    model_spec = _build_model_spec(normalized)

    # Stat files in deterministic role order: unet, clip1, clip2 (only when unique),
    # then vae (only when the profile declares one).
    facts: list[ModelFileFact] = [
        _stat_file("unet", normalized["unet"], resolve_path=resolve_path),
        _stat_file("clip1", normalized["clip1"], resolve_path=resolve_path),
    ]
    if normalized.get("clip2") and normalized["clip2"] != normalized["clip1"]:
        facts.append(_stat_file("clip2", normalized["clip2"], resolve_path=resolve_path))
    if normalized.get("vae"):
        facts.append(_stat_file("vae", normalized["vae"], resolve_path=resolve_path))

    return (model_key, model_spec, tuple(facts))


def load_cpu_snapshot_models(
    profile: Mapping[str, Any],
    *,
    load_unet: Callable[..., Any],
    load_clip: Callable[..., Any],
    load_vae: Callable[..., Any] | None = None,
    resolve_path: Callable[[str, str], str],
    trace: RuntimeTrace | None = None,
    target_gpus: tuple[str, ...] | None = None,
) -> CpuSnapshotModels:
    """Load CLIP, UNET, and (when the profile declares one) VAE from the
    given profile and return a validated snapshot.

    When *target_gpus* is provided (snapshot construction path), the
    returned ``CpuSnapshotModels`` carries a ``compute_policy`` attribute
    that distinguishes the compute/manual-cast policy so stale snapshots
    built with a different policy cannot match.  The model_spec does NOT
    contain compute_policy — matching uses the separate field.

    Load order is selected by ``COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER`` and is
    one of O0 through O3. All loading happens under torch.no_grad() with a
    gc.collect barrier after each role.

    Callback invocation shapes:
      load_clip(name, type, device)           -- single CLIP
      load_clip(name1, name2, type, device)   -- dual CLIP
      load_unet(name, weight_dtype)            -- UNET
      load_vae(name)                           -- VAE (only when profile declares one)
    """
    import torch

    start_ns = time.monotonic_ns()
    model_key_hash = ""
    normalized: dict[str, Any] = {}
    clip_obj: Any = None
    unet_obj: Any = None
    vae_obj: Any = None
    vae_policy: dict[str, Any] = resolve_vae_policy()
    vae_validation_metadata: dict[str, Any] = {}
    vae_storage_registry: StorageRegistry | None = None
    timings: dict[str, float] = {}
    active_object_type = ""
    active_basename = ""
    construction_order = runtime_shape_config().snapshot_model_order

    def _bounded_model_management_state() -> dict[str, Any]:
        if os.environ.get("COMFYMODAL_V2_SNAPSHOT_ORDER_DIAGNOSTICS", "").strip() != "1":
            return {}
        try:
            import sys
            management = sys.modules.get("comfy.model_management")
            loaded = getattr(management, "current_loaded_models", None)
            return {
                "current_loaded_models_count": len(loaded) if loaded is not None else None,
                "loaded_models_count": (
                    len(management.loaded_models())
                    if management is not None and callable(getattr(management, "loaded_models", None))
                    else None
                ),
            }
        except Exception as exc:
            return {"state_error": type(exc).__name__}

    def _load_role(role: str) -> Any:
        nonlocal active_object_type, active_basename
        active_basename = os.path.basename(
            normalized.get("clip1", "") if role == "clip"
            else normalized.get(role, "")
        )
        if trace:
            trace.emit(
                f"cpu_snapshot_{role}_load_start",
                phase="restore",
                metadata={
                    "model_key_hash": model_key_hash,
                    "basename": active_basename,
                    "construction_order": construction_order,
                },
            )
        role_start = time.monotonic_ns()
        obj: Any = None
        try:
            with torch.no_grad():
                if role == "clip":
                    if normalized.get("clip2"):
                        obj = load_clip(
                            normalized["clip1"], normalized["clip2"],
                            normalized.get("clip_type", "stable_diffusion"), "default",
                        )
                    else:
                        obj = load_clip(
                            normalized["clip1"],
                            normalized.get("clip_type", "stable_diffusion"), "default",
                        )
                elif role == "unet":
                    obj = load_unet(normalized["unet"], normalized.get("weight_dtype", "default"))
                elif role == "vae":
                    if load_vae is None:
                        raise RuntimeError(
                            "profile declares a VAE but no load_vae callback was provided"
                        )
                    obj = load_vae(normalized["vae"])
                else:
                    raise RuntimeError(f"unsupported snapshot model role: {role}")
            active_object_type = type(obj).__name__
            duration_ms = round((time.monotonic_ns() - role_start) / 1_000_000, 2)
            timings[f"{role}_load_ms"] = duration_ms
            gc.collect()
            state = _bounded_model_management_state()
            if trace:
                trace.emit(
                    f"cpu_snapshot_{role}_load_end",
                    phase="restore",
                    metadata={
                        "model_key_hash": model_key_hash,
                        "object_type": type(obj).__name__,
                        "basename": active_basename,
                        "duration_ms": duration_ms,
                        "gc_barrier": "complete",
                        "construction_order": construction_order,
                        **state,
                    },
                )
            return obj
        except BaseException as exc:
            if trace:
                trace.emit(
                    f"cpu_snapshot_{role}_load_end",
                    phase="restore",
                    metadata={
                        "model_key_hash": model_key_hash,
                        "object_type": active_object_type,
                        "basename": active_basename,
                        "duration_ms": round((time.monotonic_ns() - role_start) / 1_000_000, 2),
                        "gc_barrier": "failed",
                        "construction_order": construction_order,
                        "status": "error",
                        "reason": str(exc)[:200],
                    },
                )
            raise

    try:
        normalized = _normalize_profile(profile) if isinstance(profile, Mapping) else {}
        vae_policy = {
            key: normalized.get(key, value)
            for key, value in resolve_vae_policy(normalized.get("vae_policy_mode")).items()
            if key != "vae_policy_mode"
        }
        vae_policy["vae_policy_mode"] = normalized.get(
            "vae_policy_mode", resolve_vae_policy().get("vae_policy_mode", "v0")
        )
        model_key, model_spec, facts = identity_from_profile(
            profile, resolve_path=resolve_path,
        )
        model_key_hash = model_key.stable_hash[:16]

        for role in snapshot_construction_order(construction_order):
            if role == "vae" and not normalized.get("vae"):
                continue
            loaded = _load_role(role)
            if role == "clip":
                clip_obj = loaded
            elif role == "unet":
                unet_obj = loaded
            else:
                vae_obj = loaded

        if vae_obj is not None:
            vae_validation_metadata, vae_storage_registry = _validate_vae_policy_metadata(
                vae_obj,
                vae_policy,
                context="snapshot construction: ",
            )
            if trace:
                trace.emit(
                    "cpu_snapshot_vae_policy_ready",
                    phase="restore",
                    metadata=dict(vae_validation_metadata),
                )
            gc.collect()

        # Derive compute policy from target_gpus (snapshot identity)
        _cp = _COMPUTE_POLICY_DEFAULT
        if target_gpus:
            _wd = normalized.get("weight_dtype", "default")
            _cp = _resolve_compute_policy(_wd, target_gpus=target_gpus)

        models = CpuSnapshotModels(
            model_key=model_key,
            model_spec=model_spec,
            normalized_profile=normalized,
            file_facts=facts,
            unet=unet_obj,
            clip=clip_obj,
            vae=vae_obj,
            load_timings_ms=timings,
            compute_policy=_cp,
            policy_version=CPU_SNAPSHOT_UNET_POLICY_VERSION,
            target_gpus=target_gpus or (),
            construction_order=construction_order,
            vae_policy_version=int(vae_policy.get("vae_policy_version", VAE_POLICY_VERSION)),
            vae_weight_dtype=str(vae_policy.get("vae_weight_dtype", "float32")),
            vae_compute_dtype=str(vae_policy.get("vae_compute_dtype", "float32")),
            vae_memory_format=str(vae_policy.get("vae_memory_format", "contiguous")),
            vae_policy_mode=str(vae_policy.get("vae_policy_mode", "v0")),
            vae_policy_metadata=build_vae_policy_metadata(
                vae_policy, include_runtime_versions=False,
            ),
            vae_validation_metadata=vae_validation_metadata,
            vae_storage_registry=vae_storage_registry,
        )

        ok, reason = validate_cpu_snapshot_models(
            models,
            expected_key=model_key,
            expected_spec=model_spec,
            resolve_path=resolve_path,
        )
        if not ok:
            raise RuntimeError(f"snapshot validation failed: {reason}")

        total_ms = round((time.monotonic_ns() - start_ns) / 1_000_000, 2)
        if trace:
            trace.emit(
                "cpu_snapshot_models_ready",
                phase="restore",
                metadata={
                    "model_key_hash": model_key_hash,
                    "object_type": type(models).__name__,
                    "basename": active_basename,
                    "status": "ok",
                    "duration_ms": total_ms,
                    "construction_order": construction_order,
                },
            )

        return models

    except BaseException as exc:
        elapsed_ms = round((time.monotonic_ns() - start_ns) / 1_000_000, 2)
        if trace:
            obj_type = type(unet_obj).__name__ if unet_obj is not None else (
                type(clip_obj).__name__ if clip_obj is not None else active_object_type
            )
            trace.emit(
                "cpu_snapshot_models_failed",
                phase="restore",
                metadata={
                    "duration_ms": elapsed_ms,
                    "model_key_hash": model_key_hash,
                    "object_type": obj_type,
                    "basename": active_basename,
                    "status": "error",
                    "reason": str(exc),
                    "construction_order": construction_order,
                },
            )
        raise


def validate_cpu_snapshot_models(
    models: CpuSnapshotModels,
    *,
    expected_key: ModelRestoreKey,
    expected_spec: Mapping[str, Any],
    resolve_path: Callable[[str, str], str],
) -> tuple[bool, str]:
    """Validate a loaded CpuSnapshotModels struct.

    Compares all model_key fields, verifies model_spec structurally,
    confirms split-mode in normalized_profile, re-resolves and re-stats
    each file fact, and validates UNET/CLIP/VAE object shape and tensor
    safety (VAE only when the profile declares one).

    Returns (True, 'ok') on success or (False, reason_string) on failure.
    """
    _effective_order = runtime_shape_config().snapshot_model_order
    _stored_order = getattr(models, "construction_order", "")
    if _stored_order != _effective_order:
        return (
            False,
            f"construction_order mismatch: stored={_stored_order!r} "
            f"current={_effective_order!r}",
        )

    # Identity check â€” all fields
    if models.model_key != expected_key:
        for field_name in (
            "unet_identity",
            "clip_identity",
            "vae_identity",
            "clip_type",
            "loader_configuration",
            "model_volume_generation",
            "optimization_loader_options",
            "vae_policy_version",
            "vae_weight_dtype",
            "vae_compute_dtype",
            "vae_memory_format",
        ):
            actual = getattr(models.model_key, field_name)
            expected = getattr(expected_key, field_name)
            if actual != expected:
                label = field_name.replace("_", " ")
                return (False, f"{label} mismatch: {actual!r} != {expected!r}")
        return (False, "model_key mismatch")

    # Model spec structural check
    if models.model_spec != dict(expected_spec):
        return (False, "model_spec mismatch")

    # Normalized profile check
    norm = models.normalized_profile
    if not isinstance(norm, Mapping):
        return (False, "normalized_profile is not a mapping")
    if norm.get("mode") != "split":
        return (False, f"normalized_profile mode is not 'split': {norm.get('mode')!r}")
    for field_name in ("unet", "clip1", "clip_type"):
        value = norm.get(field_name)
        if not isinstance(value, str) or not value.strip():
            return (False, f"normalized_profile {field_name} is not a non-empty string")
    from .restore_plan import _build_dual_clip_identity

    clip2 = norm.get("clip2", "")
    if clip2 is None:
        clip2 = ""
    if not isinstance(clip2, str):
        return (False, "normalized_profile clip2 is not a string")
    if clip2:
        normalized_clip_identity = _build_dual_clip_identity(norm["clip1"], clip2)
    else:
        normalized_clip_identity = norm["clip1"]
    if models.model_key.unet_identity != norm["unet"]:
        return (False, "normalized_profile unet does not match model_key")
    if models.model_key.clip_identity != normalized_clip_identity:
        return (False, "normalized_profile clips do not match model_key")
    normalized_vae_identity = str(norm.get("vae", "") or "")
    if models.model_key.vae_identity != normalized_vae_identity:
        return (False, "normalized_profile vae does not match model_key")

    # Verify exact single/dual loader structure when clip loaders are present.
    clip_loaders = models.model_spec.get("loaders", {}).get("clip", [])
    if clip_loaders:
        first = clip_loaders[0]
        if clip2:
            if first.get("loader_class") != "DualCLIPLoader":
                return (False, "model_spec should use DualCLIPLoader when clip2 supplied")
            if first.get("clip_name1") != norm["clip1"]:
                return (False, "model_spec clip_name1 mismatch")
            if first.get("clip_name2") != norm["clip2"]:
                return (False, "model_spec clip_name2 mismatch")
            if first.get("type") != norm.get("clip_type", ""):
                return (False, "model_spec clip type mismatch")
            if first.get("device") != "default":
                return (False, "model_spec clip device should be 'default'")
        else:
            if first.get("loader_class") != "CLIPLoader":
                return (False, "model_spec should use CLIPLoader when no clip2 supplied")
            if first.get("clip_name") != norm["clip1"]:
                return (False, "model_spec clip_name mismatch")

    vae_loaders = models.model_spec.get("loaders", {}).get("vae", [])
    if normalized_vae_identity:
        if len(vae_loaders) != 1:
            return (False, "model_spec should contain one VAELoader when vae supplied")
        vae_loader = vae_loaders[0]
        if vae_loader.get("loader_class") != "VAELoader":
            return (False, "model_spec should use VAELoader when vae supplied")
        if vae_loader.get("vae_name") != normalized_vae_identity:
            return (False, "model_spec vae_name mismatch")
    elif vae_loaders:
        return (False, "model_spec contains VAELoader without vae profile identity")

    # Unique file facts: only include clip2 when different from clip1;
    # include vae only when the profile declares one.
    expected_roles: list[str] = ["unet", "clip1"]
    if clip2 and clip2 != norm.get("clip1"):
        expected_roles.append("clip2")
    if norm.get("vae"):
        expected_roles.append("vae")
    expected_roles_tuple = tuple(expected_roles)
    actual_roles = tuple(fact.role for fact in models.file_facts)
    if actual_roles != expected_roles_tuple:
        return (False, f"file fact roles mismatch: {actual_roles!r} != {expected_roles_tuple!r}")

    # Re-resolve and re-stat each file fact
    for fact in models.file_facts:
        role = fact.role
        if role == "unet":
            filename = norm.get("unet")
        elif role == "clip1":
            filename = norm.get("clip1")
        elif role == "clip2":
            filename = norm.get("clip2")
        elif role == "vae":
            filename = norm.get("vae")
        else:
            continue

        if not filename:
            return (False, f"role {role} has no filename in normalized_profile")

        try:
            current_path = resolve_path(role, filename)
        except Exception as e:
            return (False, f"resolve_path failed for {role}:{filename}: {e}")

        if not os.path.exists(current_path):
            return (False, f"resolved path does not exist: {current_path}")

        try:
            st = os.stat(current_path)
        except OSError as e:
            return (False, f"cannot stat {current_path}: {e}")

        if current_path != fact.path:
            return (False, f"resolved path mismatch for {role}: {current_path} != {fact.path}")

        if st.st_size != fact.size_bytes:
            return (False, f"file size mismatch for {role}: stored {fact.size_bytes} != current {st.st_size}")

        current_mtime = int(st.st_mtime_ns if hasattr(st, "st_mtime_ns") else st.st_mtime * 1_000_000_000)
        if fact.mtime_ns != 0 and current_mtime != 0 and fact.mtime_ns != current_mtime:
            return (False, f"file mtime mismatch for {role}")

    # Object non-None check
    if models.unet is None:
        return (False, "unet is None")
    if models.clip is None:
        return (False, "clip is None")
    expected_vae = bool(models.model_key.vae_identity)
    if expected_vae and models.vae is None:
        return (False, "vae is None but model_key declares vae_identity")
    if not expected_vae and models.vae is not None:
        return (False, "vae present but model_key declares no vae_identity")

    # Shape and tensor safety
    ok, reason = _is_valid_unet_patcher(models.unet)
    if not ok:
        return (False, reason)

    ok, reason = _is_valid_clip_patcher(models.clip)
    if not ok:
        return (False, reason)

    if expected_vae:
        ok, reason = _is_valid_vae(models.vae)
        if not ok:
            return (False, reason)

        _expected_vae_policy = _vae_policy_from_model_key(expected_key)
        _actual_vae_policy = {
            "vae_policy_version": models.vae_policy_version,
            "vae_weight_dtype": models.vae_weight_dtype,
            "vae_compute_dtype": models.vae_compute_dtype,
            "vae_memory_format": models.vae_memory_format,
            "vae_prefetch_mode": str(models.vae_policy_metadata.get("vae_prefetch_mode", "")) if isinstance(models.vae_policy_metadata, Mapping) else "",
            "c5_impl_version": str(models.vae_policy_metadata.get("c5_impl_version", "")) if isinstance(models.vae_policy_metadata, Mapping) else "",
        }
        if _actual_vae_policy != _expected_vae_policy:
            return (
                False,
                "VAE policy fields mismatch: "
                f"stored={_actual_vae_policy!r} expected={_expected_vae_policy!r}",
            )
        _metadata = models.vae_validation_metadata
        if not isinstance(_metadata, Mapping):
            return (False, "VAE validation metadata is missing")
        for _field_name, _field_value in _expected_vae_policy.items():
            if str(_metadata.get(_field_name, "")) != str(_field_value):
                return (False, f"VAE validation metadata {_field_name} mismatch")
        if str(_metadata.get("object_id", "")) != str(id(models.vae)):
            return (False, "VAE validation metadata object identity mismatch")
        if int(_metadata.get("mismatched_parameter_buffer_count", -1)) != 0:
            return (False, "VAE validation metadata reports mismatched parameters/buffers")
        if models.vae_storage_registry is None:
            return (False, "VAE storage registry is missing")

    # Policy version/identity validation â€” reject legacy/stale snapshots
    if models.policy_version == 0:
        return (False, "policy_version is 0 (legacy/unset); current version is "
                f"{CPU_SNAPSHOT_UNET_POLICY_VERSION}")
    if models.policy_version != CPU_SNAPSHOT_UNET_POLICY_VERSION:
        return (False, f"policy_version mismatch: stored={models.policy_version} "
                f"current={CPU_SNAPSHOT_UNET_POLICY_VERSION}")
    # Verify policy identity is consistent with resolved policy metadata
    _wd = models.normalized_profile.get("weight_dtype", "default")
    _tg = models.target_gpus
    _resolved_cp = models.compute_policy
    if _tg:
        _resolved_cp = _resolve_compute_policy(_wd, target_gpus=_tg)
        if _resolved_cp != models.compute_policy:
            return (False, f"compute_policy mismatch: stored={models.compute_policy} "
                    f"resolved={_resolved_cp} from weight_dtype={_wd} target_gpus={_tg}")

    # BF16-native compute policy validation (from models.compute_policy)
    if models.compute_policy == _COMPUTE_POLICY_BF16_NATIVE:
        try:
            validate_snapshot_unet_bf16_native(
                models.unet,
                context="validate_cpu_snapshot_models.",
                target_gpus=_tg or None,
                requested_weight_dtype=_wd,
                effective_weight_dtype=_resolved_cp,
                effective_compute_dtype=_resolved_cp,
            )
        except RuntimeError as _exc:
            return (False, str(_exc))

    return (True, "ok")


def retarget_cpu_snapshot_models(
    models: CpuSnapshotModels,
    *,
    model_management: Any,
) -> tuple[bool, str]:
    """Retarget model device attributes using ComfyUI's model_management.

    Sets load_device/offload_device on UNET, CLIP, and (when present) VAE
    patchers.  Never transfers model weights or selects hardcoded devices.

    Returns (True, 'ok') or (False, reason).
    """
    # Validate all required functions exist and are callable
    required_funcs = [
        "get_torch_device",
        "unet_offload_device",
        "text_encoder_device",
        "text_encoder_offload_device",
    ]
    if models.vae is not None:
        required_funcs.extend(["vae_device", "vae_offload_device"])
    for func_name in required_funcs:
        func = getattr(model_management, func_name, None)
        if not callable(func):
            return (False, f"missing_model_management_function:{func_name}")

    # Pre-check all shapes before making any assignments
    ok_unet, _ = _is_valid_unet_patcher(models.unet)
    if not ok_unet:
        return (False, "unsupported_unet_shape")

    ok_clip, _ = _is_valid_clip_patcher(models.clip)
    if not ok_clip:
        return (False, "unsupported_clip_shape")

    if models.vae is not None:
        ok_vae, _ = _is_valid_vae(models.vae)
        if not ok_vae:
            return (False, "unsupported_vae_shape")

    # Verify patcher fields exist for assignment
    if not hasattr(models.unet, "load_device") or not hasattr(models.unet, "offload_device"):
        return (False, "unsupported_unet_shape")

    clip_patcher = getattr(models.clip, "patcher", None)
    if clip_patcher is None:
        return (False, "unsupported_clip_shape")
    if not hasattr(clip_patcher, "load_device") or not hasattr(clip_patcher, "offload_device"):
        return (False, "unsupported_clip_shape")

    if models.vae is not None:
        vae_patcher = getattr(models.vae, "patcher", None)
        if vae_patcher is None:
            return (False, "unsupported_vae_shape")
        if not hasattr(vae_patcher, "load_device") or not hasattr(vae_patcher, "offload_device"):
            return (False, "unsupported_vae_shape")

    # All checks passed - make device-policy assignments only.
    # UNET: delegate to rehydrate_cpu_snapshot_unet for instrumentation.
    ok_rehydrate, reason_rehydrate = rehydrate_cpu_snapshot_unet(
        models.unet, model_management=model_management,
    )
    if not ok_rehydrate:
        return (False, f"unet_rehydration_failed:{reason_rehydrate}")

    clip_patcher.load_device = model_management.text_encoder_device()
    clip_patcher.offload_device = model_management.text_encoder_offload_device()

    if models.vae is not None:
        vae_patcher.load_device = model_management.vae_device()
        vae_patcher.offload_device = model_management.vae_offload_device()
        # The VAE wrapper's own .device mirrors patcher.load_device and is
        # used directly by encode/decode lambdas.
        if hasattr(models.vae, "device"):
            try:
                models.vae.device = model_management.vae_device()
            except Exception:
                pass

    return (True, "ok")


# ---------------------------------------------------------------------------
# Post-load GPU residency proof (evidence, no tensor contents)
# ---------------------------------------------------------------------------


def prove_unet_gpu_residency(
    unet: Any,
    *,
    model_management: Any = None,
    request_id: str = "",
) -> dict[str, Any]:
    """Collect post-load GPU-activation evidence for *unet* using only
    primitive facts â€” parameter device distribution, patcher load/current
    device, diffusion-model current device, model-cache membership, and GPU
    memory.  Never transfers or mutates tensors; never returns tensor data.

    Returns a dict with:
      ``status`` â€” ``gpu_resident`` | ``partially_gpu`` | ``cpu_resident`` |
        ``meta`` | ``unknown`` | ``no_params`` | ``absent``
      ``unet_object_id``, ``parameter_count``, ``gpu_parameter_count``,
      ``cpu_parameter_count``, ``meta_parameter_count``,
      ``unknown_parameter_count``, ``gpu_parameter_fraction``, ``load_device``,
      ``current_device``, ``diffusion_model_current_device``,
      ``model_cache_size``, ``unet_in_model_cache``, ``gpu_allocated_bytes``,
      ``gpu_reserved_bytes``.

    Meta/unknown device parameters are classified as ``meta``/``unknown``
    (NOT CPU-resident) so CPU-only, dynamic/offload, and meta/unknown paths
    remain compatible and report diagnostic status instead of failing.
    """
    evidence: dict[str, Any] = {
        "status": "absent",
        "unet_object_id": int(id(unet)) if unet is not None else 0,
    }
    if unet is None:
        return evidence
    try:
        import torch
    except Exception:
        return evidence

    dm = _resolve_inner_model(unet)

    # 1. Parameter device distribution (floating-point params only)
    gpu_params = 0
    cpu_params = 0
    meta_params = 0
    unknown_params = 0
    total = 0
    try:
        for p in dm.parameters():
            dev = str(getattr(p, "device", ""))
            total += 1
            if dev.startswith("cuda"):
                gpu_params += 1
            elif dev == "cpu":
                cpu_params += 1
            elif dev == "meta":
                meta_params += 1
            else:
                unknown_params += 1
    except Exception:
        pass
    evidence["parameter_count"] = total
    evidence["gpu_parameter_count"] = gpu_params
    evidence["cpu_parameter_count"] = cpu_params
    evidence["meta_parameter_count"] = meta_params
    evidence["unknown_parameter_count"] = unknown_params
    evidence["gpu_parameter_fraction"] = round(gpu_params / total, 4) if total else 0.0

    # 2. Patcher device fields
    load_device = getattr(unet, "load_device", None)
    current_device = getattr(unet, "current_device", None)
    evidence["load_device"] = str(load_device) if load_device is not None else "absent"
    evidence["current_device"] = (
        str(current_device) if current_device is not None else "absent"
    )
    dm_current = getattr(dm, "current_device", None)
    evidence["diffusion_model_current_device"] = (
        str(dm_current) if dm_current is not None else "absent"
    )

    # 3. Model-cache membership
    in_cache = False
    cache_size = 0
    try:
        if model_management is None:
            from comfy import model_management as _mmg
            model_management = _mmg
        _clm = getattr(model_management, "current_loaded_models", None)
        if _clm is not None:
            cache_size = len(_clm)
            for _lm in _clm:
                _m = getattr(_lm, "model", None)
                if _m is not None and id(_m) == id(unet):
                    in_cache = True
                    break
    except Exception:
        pass
    evidence["model_cache_size"] = cache_size
    evidence["unet_in_model_cache"] = int(in_cache)

    # 4. GPU memory (totals only, no tensor contents)
    try:
        if torch.cuda.is_available():
            evidence["gpu_allocated_bytes"] = int(torch.cuda.memory_allocated())
            evidence["gpu_reserved_bytes"] = int(torch.cuda.memory_reserved())
    except Exception:
        pass

    # 5. Overall status
    # Meta/unknown device params are NOT CPU-residency evidence: they are
    # reported as meta/unknown (partial/unknown), never as CPU-resident.
    if total == 0:
        evidence["status"] = "no_params"
    elif gpu_params == total:
        evidence["status"] = "gpu_resident"
    elif gpu_params > 0:
        evidence["status"] = "partially_gpu"
    elif meta_params or unknown_params:
        evidence["status"] = "unknown"
    elif cpu_params == total:
        evidence["status"] = "cpu_resident"
    else:
        evidence["status"] = "unknown"
    return evidence


def verify_unet_gpu_residency(
    unet: Any,
    *,
    model_management: Any = None,
    request_id: str = "",
    context: str = "",
    enforce: bool = False,
) -> dict[str, Any]:
    """Prove GPU activation with post-load evidence; emit a one-line
    ``[v2.unet_gpu_residency]`` diagnostic.

    Raises RuntimeError ONLY when *enforce* is True AND the model HAS
    parameters and NONE of them are on a CUDA device (status=cpu_resident) â€”
    the classic CPU-snapshot stall signature.  Enforcement is gated by the
    caller to the production CPU-snapshot path sampling the exact retained
    snapshot/bridge object.  All other paths (normal non-snapshot, CPU-only,
    dynamic/offload, meta/unknown, no-parameter stubs) report diagnostic
    status instead of raising.
    """
    evidence = prove_unet_gpu_residency(
        unet, model_management=model_management, request_id=request_id
    )
    _fields = " ".join(f"{k}={v}" for k, v in evidence.items())
    print(
        f"[v2.unet_gpu_residency] {context or 'check'} "
        f"request_id={request_id or 'absent'} enforce={int(bool(enforce))} {_fields}",
        flush=True,
    )
    if enforce and evidence.get("status") == "cpu_resident":
        raise RuntimeError(
            f"{context or 'UNET'} is CPU-resident with parameters; "
            "GPU activation was not proven before sampling "
            f"(gpu_parameters={evidence.get('gpu_parameter_count')}/"
            f"{evidence.get('parameter_count')} "
            f"load_device={evidence.get('load_device')} "
            f"current_device={evidence.get('current_device')})"
        )
    return evidence
