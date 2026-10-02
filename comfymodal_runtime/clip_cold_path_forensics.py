"""Generic CLIP cold-path forensics for text-encoder load/encode.

Batch D2: decompose the conditioning-cache-miss text-encoder critical path
into (A) becoming GPU-ready and (B) actual text encoding, without any
model-family-specific knowledge.  Everything here is capability-based and
works for any ComfyUI CLIP abstraction (safetensors text encoders included):
the wrappers only read generic attributes (``patcher.load_device``,
``patcher.is_clip``, ``model.model_loaded_weight_memory``, ...) and never
branch on model names or family-specific layer logic.

Design constraints (mirror the project telemetry conventions):

* Gated: ``COMFYMODAL_V2_CLIP_COLD_FORENSICS`` env flag AND the active
  observability mode via :func:`observability_gate`.  When disabled,
  ``install_forensics_if_enabled`` installs nothing and the class methods
  short-circuit, so overhead is zero on the hot path.
* Per-op accounting (``ModelPatcher.patch_weight_to_device``) and legacy
  synchronize totals are sub-flag gated.  The CUDA operation wrappers used by
  the neutral model-management decomposition remain installed under the main
  gate so an existing synchronize is measured without adding one.
  (``COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST`` /
  ``COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA``).
* JSON-safe: every event metadata dict contains only str/int/float/bool/
  None/dict/list values.  No tensors, no models, no paths as objects.
* Fail-closed: no accounting path may raise or mask the wrapped result.
* Testable standalone: the module imports neither ``comfy`` nor ``torch``
  at import time; ``install()`` accepts injected fake targets so tests run
  with synthetic torch modules / mocked ModelPatcher paths.
"""

from __future__ import annotations

import functools
import os
import time
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping

from comfymodal_runtime.env import env_flag, observability_gate

_SENTINEL = "_comfymodal_clip_cold_forensics"
"""Attribute stamped on every installed wrapper for idempotence."""

_CORE_GPU_SENTINEL = "_comfy_modal_gpu_wrapper"
"""Core model_preload GPU wrapper sentinel (``_SENTINEL_GPU``).

When a *shared* target (``load_models_gpu``, ``free_memory``,
``soft_empty_cache``, ``ModelPatcher.patch_weight_to_device``,
``CLIP.load_model``) already carries this attribute, the core wrapper
machinery owns that function — skip installation to avoid nested double
instrumentation.  The core installers carry the matching symmetric guard
(``_comfymodal_clip_cold_forensics``) so exactly one wrapper wins
regardless of install order."""

_MAIN_FLAG = "COMFYMODAL_V2_CLIP_COLD_FORENSICS"
_CAST_FLAG = "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST"
_SYNC_FLAG = "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA"

_EVENT_LIMIT = 512
_ENCODE_RECORD_LIMIT = 64
_RESIDENCY_LIMIT = 32

# Histogram buckets (bytes) for per-op transfer size distribution.
_BUCKETS: tuple[tuple[str, int], ...] = (
    ("tiny", 1 << 20),        # < 1 MiB
    ("small", 16 << 20),      # 1-16 MiB
    ("medium", 128 << 20),    # 16-128 MiB
    ("large", 1 << 62),       # >= 128 MiB
)


def forensics_enabled() -> bool:
    """Main gate: env flag AND observability mode allows the feature."""
    return observability_gate(_MAIN_FLAG, "clip_cold_forensics")


def cast_accounting_enabled() -> bool:
    """Sub-gate: per-op transfer accounting (hot; off by default)."""
    return env_flag(_CAST_FLAG)


def sync_cuda_enabled() -> bool:
    """Sub-gate: synchronize wrapping + CUDA-event realize (off by default)."""
    return env_flag(_SYNC_FLAG)


# ── ContextVars (single-instance assumption, matching model_preload) ──────

_ACTIVE_REQUEST: ContextVar[Any] = ContextVar(
    "comfymodal_clip_cold_active_request", default=None
)
_PAT_LOAD_DEPTH: ContextVar[int] = ContextVar(
    "comfymodal_clip_cold_pat_load_depth", default=0
)
_PAT_LOAD_STACK: ContextVar[tuple[str, ...]] = ContextVar(
    "comfymodal_clip_cold_pat_load_stack", default=()
)
_FWD_DEPTH: ContextVar[int] = ContextVar(
    "comfymodal_clip_cold_fwd_depth", default=0
)
_TOK_DEPTH: ContextVar[int] = ContextVar(
    "comfymodal_clip_cold_tok_depth", default=0
)
_ENC_DEPTH: ContextVar[int] = ContextVar(
    "comfymodal_clip_cold_enc_depth", default=0
)
_GPU_WAIT_DEPTH: ContextVar[int] = ContextVar(
    "comfymodal_clip_cold_gpu_wait_depth", default=0
)
_MODEL_MANAGEMENT_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "comfymodal_model_management_context", default=None
)
_SOFT_CACHE_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "comfymodal_soft_cache_context", default=None
)


def _ms(start_ns: int, end_ns: int) -> float:
    return round((end_ns - start_ns) / 1_000_000, 3)


def _resolve_dotted(obj: Any, dotted: str) -> Any:
    for part in str(dotted).split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


class ClipColdPathForensics:
    """Collects generic CLIP load/encode telemetry for one request.

    Install once (idempotent), then ``begin_request``/``end_request`` per
    request.  When ``enabled=False`` every wrapper short-circuits and
    ``install``/``uninstall`` are no-ops (zero-overhead contract).
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        trace: Any = None,
        request_id: str = "",
        cast_accounting: bool | None = None,
        sync_cuda: bool | None = None,
    ) -> None:
        self._enabled = bool(enabled)
        self._trace = trace
        self._request_id = str(request_id)
        # Constructor kwargs override env flags (used by tests).
        self._cast_accounting = (
            bool(cast_accounting)
            if cast_accounting is not None
            else cast_accounting_enabled()
        )
        self._sync_cuda = (
            bool(sync_cuda)
            if sync_cuda is not None
            else sync_cuda_enabled()
        )
        self._installed: list[tuple[Any, str, Any]] = []
        self._forward_wrapper_installed: set[int] = set()
        self.reset()

    # ── Request lifecycle ────────────────────────────────────────────────

    def reset(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._encode_calls: list[dict[str, Any]] = []
        self._load_calls: list[dict[str, Any]] = []
        self._residency: dict[str, list[dict[str, Any]]] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_decisions: list[str] = []
        self._sync_count = 0
        self._sync_ms = 0.0
        self._load_wall_ms_total = 0.0
        self._forward_wall_ms_total = 0.0
        self._encode_wall_ms_total = 0.0
        self._tokenize_wall_ms_total = 0.0
        self._h2d_bytes_total = 0
        self._transfer_ops_total = 0
        self._histogram: dict[str, dict[str, int]] = {
            bucket: {"count": 0, "bytes": 0} for bucket, _ in _BUCKETS
        }
        self._pinned_count = 0
        self._pageable_count = 0
        self._resident_patchers: set[str] = set()
        self._last_forward_ms: float | None = None
        self._last_forward_end_mono_ns: int | None = None
        self._last_encode_end_mono_ns: int | None = None
        self._load_account: dict[str, Any] | None = None
        self._load_account_meta: dict[str, Any] = {}
        self._sync_cuda_allowed = self._sync_cuda

    def begin_request(self, request_id: str, trace: Any = None) -> None:
        self.reset()
        if trace is not None:
            self._trace = trace
        if request_id:
            self._request_id = str(request_id)
        _ACTIVE_REQUEST.set(self)

    def end_request(self) -> dict[str, Any]:
        try:
            _ACTIVE_REQUEST.set(None)
            return self.request_summary()
        except Exception:
            return {"request_id": self._request_id, "enabled": self._enabled}

    def _resolve_request_id(self) -> str:
        if self._request_id:
            return self._request_id
        try:
            from comfymodal_runtime.model_preload import get_active_request_id

            value = get_active_request_id()
            if value:
                self._request_id = str(value)
        except Exception:
            pass
        return self._request_id

    # ── Event emission (JSON-safe, fail-closed) ──────────────────────────

    def _emit(
        self,
        name: str,
        *,
        wall_unix_ns: int | None = None,
        monotonic_ns: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "name": str(name),
            "process": "runtime",
            "phase": "execution",
            "wall_unix_ns": int(
                wall_unix_ns if wall_unix_ns is not None else time.time_ns()
            ),
            "monotonic_ns": int(
                monotonic_ns if monotonic_ns is not None else time.monotonic_ns()
            ),
            "request_id": self._resolve_request_id(),
            "metadata": dict(metadata or {}),
        }
        self._events.append(event)
        if len(self._events) > _EVENT_LIMIT:
            del self._events[:-_EVENT_LIMIT]
        if self._trace is not None:
            try:
                self._trace.emit_at(
                    event["name"],
                    wall_unix_ns=event["wall_unix_ns"],
                    monotonic_ns=event["monotonic_ns"],
                    phase="execution",
                    metadata=event["metadata"],
                )
            except Exception:
                pass
        return event

    def _span(
        self,
        name: str,
        *,
        start_wall_ns: int,
        start_mono_ns: int,
        end_wall_ns: int | None = None,
        end_mono_ns: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self._emit(
            f"{name}_start",
            wall_unix_ns=start_wall_ns,
            monotonic_ns=start_mono_ns,
            metadata={"span": name},
        )
        self._emit(
            f"{name}_end",
            wall_unix_ns=end_wall_ns if end_wall_ns is not None else time.time_ns(),
            monotonic_ns=end_mono_ns if end_mono_ns is not None else time.monotonic_ns(),
            metadata=metadata,
        )

    # ── Identity capture (generic / capability-based only) ───────────────

    def _clip_identity(self, patcher: Any, model: Any = None) -> dict[str, Any]:
        model = model if model is not None else getattr(patcher, "model", None)
        info: dict[str, Any] = {
            "patcher_id": str(id(patcher)),
            "model_id": str(id(model)) if model is not None else "",
            "clip_role": "clip" if bool(getattr(patcher, "is_clip", False)) else "unknown",
            "model_class": (
                f"{type(model).__module__}.{type(model).__name__}"
                if model is not None
                else ""
            ),
            "load_device": str(getattr(patcher, "load_device", "")),
            "offload_device": str(getattr(patcher, "offload_device", "")),
            "current_device": (
                str(getattr(model, "device", "")) if model is not None else ""
            ),
            "patcher_dynamic": False,
            "stored_dtypes": {},
            "device_distribution": {},
            "capabilities": {},
            "source_files": [],
            "checkpoint_bytes": None,
            "recreatable_from_cpu_snapshot": bool(
                getattr(patcher, "cached_patcher_init", None) is not None
            ),
        }
        try:
            is_dynamic = getattr(patcher, "is_dynamic", None)
            info["patcher_dynamic"] = bool(is_dynamic()) if callable(is_dynamic) else False
        except Exception:
            pass
        # One combined scan for stored dtype + current device distribution.
        try:
            if model is not None and hasattr(model, "parameters"):
                dtypes: dict[str, int] = {}
                devices: dict[str, int] = {}
                for param in model.parameters():
                    dtype = str(param.dtype)
                    dtypes[dtype] = dtypes.get(dtype, 0) + 1
                    device = str(param.device)
                    devices[device] = devices.get(device, 0) + 1
                info["stored_dtypes"] = dtypes
                info["device_distribution"] = devices
        except Exception:
            pass
        # Source checkpoint file(s) + total bytes where recoverable.
        try:
            cached_init = getattr(patcher, "cached_patcher_init", None)
            if (
                isinstance(cached_init, tuple)
                and len(cached_init) == 2
                and isinstance(cached_init[1], (tuple, list))
                and cached_init[1]
                and isinstance(cached_init[1][0], (tuple, list))
            ):
                paths = [str(p) for p in cached_init[1][0]]
                info["source_files"] = [Path(p).name for p in paths]
                total = 0
                for path in paths:
                    try:
                        total += os.path.getsize(path)
                    except Exception:
                        pass
                info["checkpoint_bytes"] = total
        except Exception:
            pass
        # Quant / custom-op presence as capabilities, not family names.
        try:
            weight_dtype = getattr(patcher, "weight_dtype", None)
            info["capabilities"] = {
                "manual_cast_dtype": bool(getattr(patcher, "manual_cast_dtype", None)),
                "force_cast_weights": bool(getattr(patcher, "force_cast_weights", False)),
                "model_lowvram": (
                    bool(getattr(model, "model_lowvram", False))
                    if model is not None
                    else False
                ),
                "loaded_mem_bytes": (
                    int(getattr(model, "model_loaded_weight_memory", 0) or 0)
                    if model is not None
                    else 0
                ),
                "weight_dtype": (
                    str(weight_dtype())
                    if callable(weight_dtype)
                    else str(getattr(patcher, "weight_dtype", ""))
                ),
            }
        except Exception:
            pass
        return info

    # ── Histogram / accounting helpers ───────────────────────────────────

    def _histogram_add(self, nbytes: int) -> None:
        for bucket, limit in _BUCKETS:
            if nbytes < limit:
                entry = self._histogram[bucket]
                entry["count"] += 1
                entry["bytes"] += nbytes
                return

    def _record_transfer_op(self, weight: Any, device_to: Any) -> None:
        try:
            nbytes = int(weight.numel() * weight.element_size())
        except Exception:
            return
        self._h2d_bytes_total += nbytes
        self._transfer_ops_total += 1
        self._histogram_add(nbytes)
        try:
            pinned = bool(weight.is_pinned())
        except Exception:
            pinned = False
        if pinned:
            self._pinned_count += 1
        else:
            self._pageable_count += 1
        account = self._load_account
        if account is not None:
            account["transfer_ops"] += 1
            account["bytes"] += nbytes
            account["histogram"][
                next(
                    bucket
                    for bucket, limit in _BUCKETS
                    if nbytes < limit
                )
            ]["count"] += 1
            account["pinned"] += 1 if pinned else 0
            account["pageable"] += 0 if pinned else 1

    def _record_sync(self, start_ns: int, end_ns: int) -> None:
        wall_ms = _ms(start_ns, end_ns)
        self._sync_count += 1
        self._sync_ms += wall_ms
        account = self._load_account
        if account is not None:
            account["sync_count"] += 1
            account["sync_ms"] += wall_ms

    @staticmethod
    def _model_classes(models: Any) -> list[str]:
        result: list[str] = []
        if not isinstance(models, (list, tuple)):
            return result
        for patcher in models:
            target = patcher
            for _ in range(2):
                model = getattr(target, "model", None)
                if model is None or model is target:
                    break
                target = model
            try:
                result.append(
                    f"{type(target).__module__}.{type(target).__qualname__}"
                )
            except Exception:
                result.append(type(target).__name__)
        return result

    @staticmethod
    def _loaded_model_snapshot(mm: Any) -> dict[int, int] | None:
        try:
            loaded = getattr(mm, "current_loaded_models", None)
            if loaded is None:
                return None
            result: dict[int, int] = {}
            for entry in loaded:
                patcher = getattr(entry, "model", entry)
                size = 0
                size_fn = getattr(patcher, "model_memory", None)
                if callable(size_fn):
                    try:
                        raw_size = size_fn()
                        if isinstance(raw_size, (int, float)):
                            size = int(raw_size)
                    except Exception:
                        size = 0
                if not size:
                    model = getattr(patcher, "model", None)
                    raw_size = getattr(model, "model_loaded_weight_memory", 0)
                    if isinstance(raw_size, (int, float)):
                        size = int(raw_size)
                result[id(patcher)] = max(0, size)
            return result
        except Exception:
            return None

    @staticmethod
    def _memory_snapshot(torch_mod: Any) -> dict[str, int | None]:
        result: dict[str, int | None] = {
            "allocated": None,
            "reserved": None,
        }
        try:
            cuda = getattr(torch_mod, "cuda", None)
            owner = cuda if cuda is not None else torch_mod
            for key, name in (("allocated", "memory_allocated"), ("reserved", "memory_reserved")):
                fn = getattr(owner, name, None)
                if callable(fn):
                    value = fn()
                    if isinstance(value, (int, float)):
                        result[key] = int(value)
        except Exception:
            pass
        return result

    @staticmethod
    def _free_memory_snapshot(mm: Any, device: Any) -> int | None:
        try:
            fn = getattr(mm, "get_free_memory", None)
            if callable(fn):
                value = fn(device)
                return int(value) if isinstance(value, (int, float)) else None
        except Exception:
            pass
        return None

    @classmethod
    def _infer_model_management_context(cls) -> dict[str, Any]:
        """Recover generic loader locals when another wrapper owns loading."""
        result: dict[str, Any] = {}
        frame = None
        try:
            import inspect

            frame = inspect.currentframe()
            while frame is not None:
                locals_ = frame.f_locals
                name = frame.f_code.co_name
                if name == "free_memory":
                    result.setdefault("free_memory_required", locals_.get("memory_required"))
                    result.setdefault("device", str(locals_.get("device", "")))
                    result.setdefault("caller", "model_management.free_memory")
                    result.setdefault("reason", "model_management_free_memory")
                elif name == "load_models_gpu":
                    models = locals_.get("models_to_load", locals_.get("models"))
                    if isinstance(models, (list, tuple)):
                        result.setdefault("models", models)
                        result.setdefault("model_count", len(models))
                        result.setdefault("model_classes", cls._model_classes(models))
                    result.setdefault("caller", "model_management.load_models_gpu")
                    result.setdefault("reason", "model_management_load_models_gpu")
                frame = frame.f_back
        except Exception:
            pass
        finally:
            del frame
        return result

    def _soft_cache_metadata(
        self,
        context: dict[str, Any],
        *,
        status: str,
        end_memory: dict[str, int | None] | None = None,
        total_end_ns: int | None = None,
    ) -> dict[str, Any]:
        operations = context.get("operations", {})
        total_end_ns = total_end_ns or time.monotonic_ns()
        start_ns = int(context.get("start_mono_ns", total_end_ns))
        sync = operations.get("synchronize")
        empty = operations.get("empty_cache")
        ipc = operations.get("ipc_collect")
        last_end = max(
            [int(value.get("end_ns", 0)) for value in operations.values() if isinstance(value, dict)]
            or [start_ns]
        )
        loaded_before = context.get("loaded_before")
        loaded_after = self._loaded_model_snapshot(context.get("mm"))
        unloaded_count: int | None = None
        bytes_unloaded: int | None = None
        if isinstance(loaded_before, dict) and isinstance(loaded_after, dict):
            removed = set(loaded_before) - set(loaded_after)
            unloaded_count = len(removed)
            bytes_unloaded = sum(int(loaded_before.get(key, 0) or 0) for key in removed)
        before_memory = context.get("memory_before") or {}
        after_memory = end_memory or {}
        return {
            "status": status,
            "reason": context.get("reason", "model_management_soft_empty_cache"),
            "caller": context.get("caller", "model_management.soft_empty_cache"),
            "model_count": context.get("model_count"),
            "model_classes": list(context.get("model_classes", [])),
            "required_memory": context.get("required_memory"),
            "free_memory_before": context.get("free_memory_before"),
            "allocated_before": before_memory.get("allocated"),
            "reserved_before": before_memory.get("reserved"),
            "allocated_after": after_memory.get("allocated"),
            "reserved_after": after_memory.get("reserved"),
            "models_unloaded_count": unloaded_count,
            "bytes_unloaded": bytes_unloaded,
            "single_use": env_flag("COMFYMODAL_V2_SINGLE_USE_CONTAINERS"),
            "request_id": self._resolve_request_id(),
            "pre_sync_ms": _ms(start_ns, int(sync["start_ns"])) if sync else None,
            "cuda_synchronize_ms": _ms(int(sync["start_ns"]), int(sync["end_ns"])) if sync else None,
            "empty_cache_ms": _ms(int(empty["start_ns"]), int(empty["end_ns"])) if empty else None,
            "ipc_collect_ms": _ms(int(ipc["start_ns"]), int(ipc["end_ns"])) if ipc else None,
            "post_cleanup_ms": _ms(last_end, total_end_ns),
            "soft_empty_cache_total_ms": _ms(start_ns, total_end_ns),
        }

    def _soft_operation_end(
        self,
        operation: str,
        start_ns: int,
        end_ns: int,
        status: str,
    ) -> None:
        context = _SOFT_CACHE_CONTEXT.get()
        if context is None:
            return
        context.setdefault("operations", {})[operation] = {
            "start_ns": start_ns,
            "end_ns": end_ns,
            "status": status,
        }
        event_name = {
            "synchronize": "model_management_cuda_sync_end",
            "empty_cache": "model_management_empty_cache_end",
            "ipc_collect": "model_management_ipc_collect_end",
        }.get(operation)
        if event_name is not None:
            self._emit(
                event_name,
                monotonic_ns=end_ns,
                metadata={
                    **self._soft_cache_metadata(
                        context, status=status, total_end_ns=end_ns,
                    ),
                    "operation": operation,
                    "operation_wall_ms": _ms(start_ns, end_ns),
                },
            )

    # ── Wrapper factories ────────────────────────────────────────────────

    def _make_patcher_load_wrapper(
        self, span_name: str, original: Callable[..., Any]
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(patcher: Any, *args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(patcher, *args, **kwargs)
            depth = _PAT_LOAD_DEPTH.get()
            _PAT_LOAD_DEPTH.set(depth + 1)
            emit = depth == 0
            patcher_id = str(id(patcher))
            start_wall = time.time_ns()
            start_mono = time.monotonic_ns()
            start_thread = time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
            start_proc = time.process_time_ns() if hasattr(time, "process_time_ns") else 0
            resident_before = False
            already_resident_bytes = 0
            stack = _PAT_LOAD_STACK.get()
            if emit:
                stack = stack + (patcher_id,)
                _PAT_LOAD_STACK.set(stack)
                self._load_account = {
                    "transfer_ops": 0,
                    "bytes": 0,
                    "histogram": {
                        bucket: {"count": 0, "bytes": 0} for bucket, _ in _BUCKETS
                    },
                    "pinned": 0,
                    "pageable": 0,
                    "sync_count": 0,
                    "sync_ms": 0.0,
                }
                model = getattr(patcher, "model", None)
                try:
                    if model is not None:
                        load_device = getattr(patcher, "load_device", None)
                        resident_before = (
                            load_device is not None
                            and str(getattr(model, "device", "")) == str(load_device)
                        )
                        if resident_before:
                            already_resident_bytes = int(
                                getattr(model, "model_loaded_weight_memory", 0) or 0
                            )
                except Exception:
                    pass
                self._load_account_meta = {
                    "resident_before": resident_before,
                    "already_resident_bytes": already_resident_bytes,
                }
                self._emit(
                    f"{span_name}_start",
                    wall_unix_ns=start_wall,
                    monotonic_ns=start_mono,
                    metadata={"patcher_id": patcher_id, "span": span_name},
                )
                # ── D6 restore-side lifecycle checkpoint (default-OFF) ──
                # ModelPatcher.load/partially_load entry: record the patcher's
                # model when it is CLIP-like.  Lazy import avoids any import
                # cycle (wiring only imports cfh/env; this module is imported
                # by model_preload, never by wiring).  Trace is unavailable in
                # the wrapper; clip_state_checkpoint falls back to _ACTIVE_TRACE.
                try:
                    from comfymodal_runtime.clip_fast_hydration_wiring import (
                        clip_state_checkpoint,
                    )
                    clip_state_checkpoint(
                        None,
                        "modelpatcher_load_entry",
                        getattr(patcher, "is_clip", False)
                        or getattr(patcher, "model", None),
                    )
                except Exception:
                    pass
            status = "ok"
            full_load = bool(
                kwargs.get("full_load", args[3] if len(args) > 3 else False)
            )
            try:
                if emit and self._sync_cuda:
                    result = self._cuda_interval_run(
                        lambda: original(patcher, *args, **kwargs), patcher_id
                    )
                else:
                    result = original(patcher, *args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                end_wall = time.time_ns()
                end_mono = time.monotonic_ns()
                end_thread = (
                    time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
                )
                end_proc = (
                    time.process_time_ns() if hasattr(time, "process_time_ns") else 0
                )
                _PAT_LOAD_DEPTH.set(_PAT_LOAD_DEPTH.get() - 1)
                if emit:
                    try:
                        self._finish_patcher_load(
                            patcher,
                            span_name,
                            start_wall=start_wall,
                            start_mono=start_mono,
                            end_wall=end_wall,
                            end_mono=end_mono,
                            start_thread=start_thread,
                            end_thread=end_thread,
                            start_proc=start_proc,
                            end_proc=end_proc,
                            status=status,
                            full_load=full_load,
                        )
                    finally:
                        _PAT_LOAD_STACK.set(stack)
                        self._load_account = None
                        self._load_account_meta = {}
            return result
        return wrapper

    def _cuda_interval_run(self, run: Callable[[], Any], patcher_id: str) -> Any:
        self._cuda_interval_ms_meta = None
        if not self._sync_cuda:
            return run()
        try:
            import torch  # noqa: PLC0415

            if not torch.cuda.is_available() or not torch.cuda.is_initialized():
                return run()
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)
            start_event.record()
            result = run()
            end_event.record()
            torch.cuda.synchronize()
            self._cuda_interval_ms_meta = (
                round(float(start_event.elapsed_time(end_event)), 3),
                True,
            )
            return result
        except Exception:
            return run()

    def _finish_patcher_load(
        self,
        patcher: Any,
        span_name: str,
        *,
        start_wall: int,
        start_mono: int,
        end_wall: int,
        end_mono: int,
        start_thread: int,
        end_thread: int,
        start_proc: int,
        end_proc: int,
        status: str,
        full_load: bool = False,
    ) -> None:
        model = getattr(patcher, "model", None)
        meta = self._clip_identity(patcher, model=model)
        meta.update(
            {
                "status": status,
                "wall_ms": _ms(start_mono, end_mono),
                "thread_cpu_ms": _ms(start_thread, end_thread),
                "process_cpu_ms": _ms(start_proc, end_proc),
                "lowvram": (
                    bool(getattr(model, "model_lowvram", False))
                    if model is not None
                    else False
                ),
                "full_load": bool(full_load),
                "bytes_transferred": (
                    int(getattr(model, "model_loaded_weight_memory", 0) or 0)
                    if model is not None
                    else 0
                ),
                "offload_buffer_bytes": (
                    int(getattr(model, "model_offload_buffer_memory", 0) or 0)
                    if model is not None
                    else 0
                ),
                "total_model_bytes": (
                    int(patcher.model_size())
                    if callable(getattr(patcher, "model_size", None))
                    else None
                ),
                "model_ready_wall_unix_ns": end_wall,
            }
        )
        meta.update(self._load_account_meta)
        account = self._load_account
        if account is not None:
            meta.update(
                {
                    "transfer_ops": account["transfer_ops"],
                    "histogram": account["histogram"],
                    "pinned_count": account["pinned"],
                    "pageable_count": account["pageable"],
                    "sync_count": account["sync_count"],
                    "sync_ms": round(account["sync_ms"], 3),
                }
            )
        cuda_meta = getattr(self, "_cuda_interval_ms_meta", None)
        if cuda_meta is not None:
            meta["cuda_event_ms"], meta["cuda_event_realized"] = cuda_meta
        else:
            meta["cuda_event_ms"] = None
            meta["cuda_event_realized"] = False
        self._load_wall_ms_total += meta["wall_ms"]
        self._resident_patchers.add(meta["patcher_id"])
        self._residency.setdefault(meta["patcher_id"], []).append(
            {
                "event": "load",
                "wall_unix_ns": end_wall,
                "span": span_name,
            }
        )
        self._emit(
            f"{span_name}_end",
            wall_unix_ns=end_wall,
            monotonic_ns=end_mono,
            metadata=meta,
        )
        self._load_calls.append(meta)
        if len(self._load_calls) > _ENCODE_RECORD_LIMIT:
            del self._load_calls[:-_ENCODE_RECORD_LIMIT]

    # ── Install / uninstall ──────────────────────────────────────────────

    def _target_module(self, name: str) -> Any:
        try:
            import sys

            return sys.modules.get(name)
        except Exception:
            return None

    def _install_callable(
        self,
        owner: Any,
        attr: str,
        wrapper: Callable[..., Any],
        component: str,
        core_sentinel: str | None = None,
    ) -> str:
        original = getattr(owner, attr, None)
        if not callable(original):
            return "unavailable"
        if getattr(original, _SENTINEL, False):
            return "already_installed"
        if core_sentinel is not None and getattr(original, core_sentinel, False):
            # Another module (model_preload core wrapper machinery) owns this
            # shared target already; wrapping again would double-instrument it.
            return "skipped_core_wrapper_present"
        setattr(wrapper, _SENTINEL, True)
        setattr(owner, attr, wrapper)
        self._installed.append((owner, attr, original))
        return "installed"

    def install(self, targets: Any = None) -> dict[str, str]:
        """Install wrappers; returns ``{component: status}``.

        *targets* is an optional object with attrs ``mm_module``,
        ``mp_class``, ``sd_clip_class``, ``torch_module``, ``cache_class``.
        Missing attrs / None fall back to lazy sys.modules resolution.
        Never raises.

        Statuses per component: ``"installed"``, ``"already_installed"``
        (idempotent re-install), ``"unavailable"`` (symbol absent),
        ``"gated_off"`` (sub-flag disabled), or
        ``"skipped_core_wrapper_present"`` — the latter only for the five
        shared targets (``load_models_gpu``, ``free_memory``,
        ``soft_empty_cache``, ``patch_weight_to_device``, ``load_model``)
        when the core model_preload wrapper machinery already owns the
        function (cross-sentinel guard against double instrumentation).
        """
        if not self._enabled:
            return {"status": "disabled"}
        result: dict[str, str] = {}
        try:
            if targets is None:
                targets = SimpleNamespace()
            mm = getattr(targets, "mm_module", None)
            if mm is None:
                mm = self._target_module("comfy.model_management")
            self._model_management_module = mm
            mp_cls = getattr(targets, "mp_class", None)
            if mp_cls is None:
                mp_cls = self._target_module("comfy.model_patcher")
                if mp_cls is not None:
                    mp_cls = getattr(mp_cls, "ModelPatcher", None)
            sd_clip = getattr(targets, "sd_clip_class", None)
            if sd_clip is None:
                sd_mod = self._target_module("comfy.sd")
                if sd_mod is not None:
                    sd_clip = getattr(sd_mod, "CLIP", None)
            torch_mod = getattr(targets, "torch_module", None)
            if torch_mod is None:
                torch_mod = self._target_module("torch")
            cache_cls = getattr(targets, "cache_class", None)
            if cache_cls is None:
                cache_mod = self._target_module(
                    "comfymodal_runtime.clip_conditioning_cache"
                )
                if cache_mod is not None:
                    cache_cls = getattr(cache_mod, "ExactConditioningCache", None)

            if mm is not None:
                result["load_models_gpu"] = self._install_callable(
                    mm,
                    "load_models_gpu",
                    self._make_load_models_gpu_wrapper(getattr(mm, "load_models_gpu")),
                    "load_models_gpu",
                    core_sentinel=_CORE_GPU_SENTINEL,
                )
                result["free_memory"] = self._install_callable(
                    mm,
                    "free_memory",
                    self._make_free_memory_wrapper(
                        getattr(mm, "free_memory"), mm,
                    ),
                    "free_memory",
                    core_sentinel=_CORE_GPU_SENTINEL,
                )
                result["soft_empty_cache"] = self._install_callable(
                    mm,
                    "soft_empty_cache",
                    self._make_soft_empty_cache_wrapper(
                        getattr(mm, "soft_empty_cache"), mm, torch_mod,
                    ),
                    "soft_empty_cache",
                    core_sentinel=_CORE_GPU_SENTINEL,
                )
            if mp_cls is not None:
                result["patcher_load"] = self._install_callable(
                    mp_cls,
                    "load",
                    self._make_patcher_load_wrapper(
                        "clip_cold_patcher_load", getattr(mp_cls, "load")
                    ),
                    "patcher_load",
                )
                result["patcher_partial_load"] = self._install_callable(
                    mp_cls,
                    "partially_load",
                    self._make_patcher_load_wrapper(
                        "clip_cold_patcher_partial_load",
                        getattr(mp_cls, "partially_load"),
                    ),
                    "patcher_partial_load",
                )
                result["patcher_partial_unload"] = self._install_callable(
                    mp_cls,
                    "partially_unload",
                    self._make_unload_wrapper(getattr(mp_cls, "partially_unload")),
                    "patcher_partial_unload",
                )
                result["patcher_detach"] = self._install_callable(
                    mp_cls,
                    "detach",
                    self._make_detach_wrapper(getattr(mp_cls, "detach")),
                    "patcher_detach",
                )
                if self._cast_accounting:
                    result["patch_weight_to_device"] = self._install_callable(
                        mp_cls,
                        "patch_weight_to_device",
                        self._make_patch_weight_wrapper(
                            getattr(mp_cls, "patch_weight_to_device")
                        ),
                        "patch_weight_to_device",
                        core_sentinel=_CORE_GPU_SENTINEL,
                    )
                else:
                    result["patch_weight_to_device"] = "gated_off"
            if sd_clip is not None:
                result["clip_tokenize"] = self._install_callable(
                    sd_clip,
                    "tokenize",
                    self._make_clip_tokenize_wrapper(getattr(sd_clip, "tokenize")),
                    "clip_tokenize",
                )
                result["clip_load_model"] = self._install_callable(
                    sd_clip,
                    "load_model",
                    self._make_clip_load_model_wrapper(getattr(sd_clip, "load_model")),
                    "clip_load_model",
                    core_sentinel=_CORE_GPU_SENTINEL,
                )
                result["clip_encode"] = self._install_callable(
                    sd_clip,
                    "encode_from_tokens",
                    self._make_clip_encode_wrapper(
                        "clip_cold_encode", getattr(sd_clip, "encode_from_tokens")
                    ),
                    "clip_encode",
                )
                result["clip_encode_scheduled"] = self._install_callable(
                    sd_clip,
                    "encode_from_tokens_scheduled",
                    self._make_clip_encode_wrapper(
                        "clip_cold_scheduled_encode",
                        getattr(sd_clip, "encode_from_tokens_scheduled"),
                    ),
                    "clip_encode_scheduled",
                )
            if torch_mod is not None:
                cuda_mod = getattr(torch_mod, "cuda", None)
                for operation, result_key in (
                    ("synchronize", "torch_cuda_synchronize"),
                    ("empty_cache", "torch_cuda_empty_cache"),
                    ("ipc_collect", "torch_cuda_ipc_collect"),
                ):
                    owner = (
                        cuda_mod
                        if cuda_mod is not None and callable(getattr(cuda_mod, operation, None))
                        else torch_mod
                    )
                    original_operation = getattr(owner, operation, None)
                    if not callable(original_operation):
                        result[result_key] = "gated_off" if operation == "synchronize" else "unavailable"
                        continue
                    result[result_key] = self._install_callable(
                        owner,
                        operation,
                        self._make_cuda_operation_wrapper(operation, original_operation),
                        result_key,
                    )
            if cache_cls is not None:
                result["cache_lookup_many"] = self._install_callable(
                    cache_cls,
                    "lookup_many",
                    self._make_cache_lookup_wrapper(
                        getattr(cache_cls, "lookup_many")
                    ),
                    "cache_lookup_many",
                )
        except Exception:
            pass
        return result

    def uninstall(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for owner, attr, original in reversed(self._installed):
            try:
                current = getattr(owner, attr, None)
                if current is not None and getattr(current, _SENTINEL, False):
                    setattr(owner, attr, original)
                    result[f"{attr}"] = "restored"
            except Exception:
                pass
        self._installed.clear()
        return result

    # ── Component wrappers ───────────────────────────────────────────────

    def _make_load_models_gpu_wrapper(
        self, original: Callable[..., Any]
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(*args, **kwargs)
            models = args[0] if args else kwargs.get("models", [])
            start_wall = time.time_ns()
            start_mono = time.monotonic_ns()
            start_thread = (
                time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
            )
            start_proc = (
                time.process_time_ns() if hasattr(time, "process_time_ns") else 0
            )
            context = dict(_MODEL_MANAGEMENT_CONTEXT.get() or {})
            context.update({
                "mm": getattr(self, "_model_management_module", None),
                "operation": "load_models_gpu",
                "caller": "model_management.load_models_gpu",
                "reason": "model_management_load_models_gpu",
                "models": models,
                "model_count": len(models) if isinstance(models, (list, tuple)) else None,
                "model_classes": self._model_classes(models),
                "required_memory": kwargs.get(
                    "memory_required", args[1] if len(args) > 1 else 0
                ),
            })
            context["loaded_before"] = self._loaded_model_snapshot(context["mm"])
            context_token = _MODEL_MANAGEMENT_CONTEXT.set(context)
            self._emit(
                "clip_cold_load_models_gpu_start",
                wall_unix_ns=start_wall,
                monotonic_ns=start_mono,
                metadata={"span": "clip_cold_load_models_gpu"},
            )
            status = "ok"
            try:
                result = original(*args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                _MODEL_MANAGEMENT_CONTEXT.reset(context_token)
                end_wall = time.time_ns()
                end_mono = time.monotonic_ns()
                end_thread = (
                    time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
                )
                end_proc = (
                    time.process_time_ns() if hasattr(time, "process_time_ns") else 0
                )
                try:
                    clip_count = 0
                    if isinstance(models, (tuple, list)):
                        for model in models:
                            if bool(getattr(model, "is_clip", False)):
                                clip_count += 1
                    self._emit(
                        "clip_cold_load_models_gpu_end",
                        wall_unix_ns=end_wall,
                        monotonic_ns=end_mono,
                        metadata={
                            "status": status,
                            "model_count": (
                                len(models)
                                if isinstance(models, (tuple, list))
                                else None
                            ),
                            "clip_patcher_count": clip_count,
                            "memory_required": kwargs.get(
                                "memory_required", args[1] if len(args) > 1 else 0
                            ),
                            "wall_ms": _ms(start_mono, end_mono),
                            "thread_cpu_ms": _ms(start_thread, end_thread),
                            "process_cpu_ms": _ms(start_proc, end_proc),
                        },
                    )
                except Exception:
                    pass
            return result
        return wrapper

    def _make_free_memory_wrapper(
        self, original: Callable[..., Any], mm: Any,
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(*args, **kwargs)
            parent = _MODEL_MANAGEMENT_CONTEXT.get()
            context = dict(parent or {})
            memory_required = args[0] if args else kwargs.get("memory_required")
            device = args[1] if len(args) > 1 else kwargs.get("device")
            context.update({
                "mm": mm,
                "operation": "free_memory",
                "caller": (
                    "model_management.load_models_gpu.free_memory"
                    if parent is not None
                    else "model_management.free_memory"
                ),
                "reason": "model_management_free_memory",
                "free_memory_required": memory_required,
                "device": str(device) if device is not None else "",
            })
            context_token = _MODEL_MANAGEMENT_CONTEXT.set(context)
            start_mono = time.monotonic_ns()
            status = "ok"
            try:
                return original(*args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                _MODEL_MANAGEMENT_CONTEXT.reset(context_token)
                self._emit(
                    "clip_cold_free_memory",
                    monotonic_ns=time.monotonic_ns(),
                    metadata={
                        "memory_required": memory_required,
                        "device": str(device) if device is not None else "",
                        "status": status,
                        "wall_ms": _ms(start_mono, time.monotonic_ns()),
                    },
                )

        return wrapper

    def _make_soft_empty_cache_wrapper(
        self, original: Callable[..., Any], mm: Any, torch_mod: Any,
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(*args, **kwargs)
            parent = dict(_MODEL_MANAGEMENT_CONTEXT.get() or {})
            inferred = self._infer_model_management_context()
            for key, value in inferred.items():
                if key not in parent or parent.get(key) in (None, "", []):
                    parent[key] = value
            device = parent.get("device") or ""
            if not device:
                try:
                    device_fn = getattr(mm, "get_torch_device", None)
                    device = str(device_fn()) if callable(device_fn) else ""
                except Exception:
                    device = ""
            parent.update({
                "mm": mm,
                "device": device,
                "start_mono_ns": time.monotonic_ns(),
                "operations": {},
                "memory_before": self._memory_snapshot(torch_mod),
                "free_memory_before": self._free_memory_snapshot(mm, device),
                "required_memory": parent.get(
                    "free_memory_required", parent.get("required_memory")
                ),
                "model_count": parent.get("model_count"),
                "model_classes": list(parent.get("model_classes", [])),
                "caller": parent.get(
                    "caller", "model_management.soft_empty_cache"
                ),
                "reason": parent.get(
                    "reason", "model_management_soft_empty_cache"
                ),
            })
            context_token = _SOFT_CACHE_CONTEXT.set(parent)
            start_mono = int(parent["start_mono_ns"])
            self._emit(
                "model_management_soft_empty_cache_start",
                monotonic_ns=start_mono,
                metadata=self._soft_cache_metadata(
                    parent, status="running", total_end_ns=start_mono,
                ),
            )
            status = "ok"
            try:
                return original(*args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                end_mono = time.monotonic_ns()
                end_memory = self._memory_snapshot(torch_mod)
                self._emit(
                    "model_management_soft_empty_cache_end",
                    monotonic_ns=end_mono,
                    metadata=self._soft_cache_metadata(
                        parent,
                        status=status,
                        end_memory=end_memory,
                        total_end_ns=end_mono,
                    ),
                )
                self._emit(
                    "clip_cold_soft_empty_cache",
                    monotonic_ns=end_mono,
                    metadata={
                        "status": status,
                        "wall_ms": _ms(start_mono, end_mono),
                    },
                )
                _SOFT_CACHE_CONTEXT.reset(context_token)

        return wrapper

    def _make_cuda_operation_wrapper(
        self, operation: str, original: Callable[..., Any],
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(*args, **kwargs)
            start_ns = time.monotonic_ns()
            status = "ok"
            try:
                return original(*args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                end_ns = time.monotonic_ns()
                if operation == "synchronize" and self._sync_cuda:
                    self._record_sync(start_ns, end_ns)
                self._soft_operation_end(operation, start_ns, end_ns, status)

        setattr(wrapper, _SENTINEL, True)
        return wrapper

    def _make_mark_wrapper(
        self,
        event_name: str,
        original: Callable[..., Any],
        meta_fn: Callable[..., dict[str, Any]],
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(*args, **kwargs)
            start_wall = time.time_ns()
            start_mono = time.monotonic_ns()
            status = "ok"
            try:
                result = original(*args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                try:
                    meta = dict(meta_fn(original, *args, **kwargs))
                except Exception:
                    meta = {}
                meta["status"] = status
                meta["wall_ms"] = _ms(start_mono, time.monotonic_ns())
                self._emit(
                    event_name,
                    wall_unix_ns=time.time_ns(),
                    monotonic_ns=time.monotonic_ns(),
                    metadata=meta,
                )
            return result
        return wrapper

    def _make_patch_weight_wrapper(
        self, original: Callable[..., Any]
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(patcher: Any, key: Any, *args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(patcher, key, *args, **kwargs)
            if not _PAT_LOAD_STACK.get():
                return original(patcher, key, *args, **kwargs)
            device_to = kwargs.get("device_to", args[0] if args else None)
            try:
                weight = _resolve_dotted(getattr(patcher, "model", None), key)
                if weight is not None:
                    self._record_transfer_op(weight, device_to)
            except Exception:
                pass
            return original(patcher, key, *args, **kwargs)

        return wrapper

    def _make_synchronize_wrapper(
        self, original: Callable[..., Any]
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(*args, **kwargs)
            start = time.monotonic_ns()
            try:
                return original(*args, **kwargs)
            finally:
                try:
                    self._record_sync(start, time.monotonic_ns())
                except Exception:
                    pass

        return wrapper

    def _make_unload_wrapper(
        self, original: Callable[..., Any]
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(patcher: Any, *args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(patcher, *args, **kwargs)
            start_wall = time.time_ns()
            start_mono = time.monotonic_ns()
            status = "ok"
            try:
                result = original(patcher, *args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                try:
                    meta = self._clip_identity(patcher)
                    meta.update(
                        {
                            "status": status,
                            "kind": "partial_unload",
                            "device_to": str(
                                kwargs.get(
                                    "device_to", args[0] if args else ""
                                )
                            ),
                            "memory_to_free": kwargs.get(
                                "memory_to_free", args[1] if len(args) > 1 else 0
                            ),
                            "wall_ms": _ms(start_mono, time.monotonic_ns()),
                        }
                    )
                    self._residency.setdefault(meta["patcher_id"], []).append(
                        {
                            "event": "partial_unload",
                            "wall_unix_ns": time.time_ns(),
                        }
                    )
                    self._emit(
                        "clip_cold_unload",
                        wall_unix_ns=time.time_ns(),
                        monotonic_ns=time.monotonic_ns(),
                        metadata=meta,
                    )
                except Exception:
                    pass
            return result
        return wrapper

    def _make_detach_wrapper(
        self, original: Callable[..., Any]
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(patcher: Any, *args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(patcher, *args, **kwargs)
            status = "ok"
            try:
                result = original(patcher, *args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                try:
                    meta = self._clip_identity(patcher)
                    meta["status"] = status
                    meta["kind"] = "detach"
                    meta["unpatch_weights"] = bool(
                        kwargs.get(
                            "unpatch_weights", args[0] if args else True
                        )
                    )
                    self._residency.setdefault(meta["patcher_id"], []).append(
                        {"event": "detach", "wall_unix_ns": time.time_ns()}
                    )
                    self._emit(
                        "clip_cold_detach",
                        wall_unix_ns=time.time_ns(),
                        monotonic_ns=time.monotonic_ns(),
                        metadata=meta,
                    )
                except Exception:
                    pass
            return result
        return wrapper

    def _make_clip_tokenize_wrapper(
        self, original: Callable[..., Any]
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(clip: Any, *args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(clip, *args, **kwargs)
            depth = _TOK_DEPTH.get()
            _TOK_DEPTH.set(depth + 1)
            start_wall = time.time_ns()
            start_mono = time.monotonic_ns()
            start_thread = (
                time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
            )
            start_proc = (
                time.process_time_ns() if hasattr(time, "process_time_ns") else 0
            )
            if depth == 0:
                self._emit(
                    "clip_cold_tokenize_start",
                    wall_unix_ns=start_wall,
                    monotonic_ns=start_mono,
                    metadata={"span": "clip_cold_tokenize"},
                )
            status = "ok"
            try:
                result = original(clip, *args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                end_wall = time.time_ns()
                end_mono = time.monotonic_ns()
                end_thread = (
                    time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
                )
                end_proc = (
                    time.process_time_ns() if hasattr(time, "process_time_ns") else 0
                )
                _TOK_DEPTH.set(_TOK_DEPTH.get() - 1)
                if depth == 0:
                    try:
                        text = args[0] if args else kwargs.get("text", "")
                        meta = {
                            "status": status,
                            "wall_ms": _ms(start_mono, end_mono),
                            "thread_cpu_ms": _ms(start_thread, end_thread),
                            "process_cpu_ms": _ms(start_proc, end_proc),
                            "text_len": len(str(text)) if text is not None else None,
                        }
                        self._tokenize_wall_ms_total += meta["wall_ms"]
                        self._emit(
                            "clip_cold_tokenize_end",
                            wall_unix_ns=end_wall,
                            monotonic_ns=end_mono,
                            metadata=meta,
                        )
                    except Exception:
                        pass
            return result
        return wrapper

    def _make_clip_load_model_wrapper(
        self, original: Callable[..., Any]
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(clip: Any, *args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(clip, *args, **kwargs)
            depth = _GPU_WAIT_DEPTH.get()
            _GPU_WAIT_DEPTH.set(depth + 1)
            start_wall = time.time_ns()
            start_mono = time.monotonic_ns()
            start_thread = (
                time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
            )
            start_proc = (
                time.process_time_ns() if hasattr(time, "process_time_ns") else 0
            )
            if depth == 0:
                self._emit(
                    "clip_cold_gpu_wait_start",
                    wall_unix_ns=start_wall,
                    monotonic_ns=start_mono,
                    metadata={"span": "clip_cold_gpu_wait"},
                )
            status = "ok"
            try:
                result = original(clip, *args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                end_wall = time.time_ns()
                end_mono = time.monotonic_ns()
                end_thread = (
                    time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
                )
                end_proc = (
                    time.process_time_ns() if hasattr(time, "process_time_ns") else 0
                )
                _GPU_WAIT_DEPTH.set(_GPU_WAIT_DEPTH.get() - 1)
                if depth == 0:
                    try:
                        patcher = getattr(clip, "patcher", None)
                        meta = (
                            self._clip_identity(patcher)
                            if patcher is not None
                            else {}
                        )
                        meta.update(
                            {
                                "status": status,
                                "wall_ms": _ms(start_mono, end_mono),
                                "thread_cpu_ms": _ms(start_thread, end_thread),
                                "process_cpu_ms": _ms(start_proc, end_proc),
                            }
                        )
                        self._emit(
                            "clip_cold_gpu_wait_end",
                            wall_unix_ns=end_wall,
                            monotonic_ns=end_mono,
                            metadata=meta,
                        )
                    except Exception:
                        pass
            return result
        return wrapper

    def _ensure_forward_wrapper(self, clip: Any) -> str:
        csm = getattr(clip, "cond_stage_model", None)
        if csm is None:
            return "unavailable"
        cls = type(csm)
        cls_id = id(cls)
        if cls_id in self._forward_wrapper_installed:
            return "already_installed"
        original = getattr(cls, "encode_token_weights", None)
        if not callable(original):
            return "unavailable"
        status = self._install_callable(
            cls,
            "encode_token_weights",
            self._make_forward_wrapper(original),
            "encode_token_weights",
        )
        if status == "installed":
            self._forward_wrapper_installed.add(cls_id)
        return status

    def _make_forward_wrapper(
        self, original: Callable[..., Any]
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(*args, **kwargs)
            depth = _FWD_DEPTH.get()
            _FWD_DEPTH.set(depth + 1)
            start_wall = time.time_ns()
            start_mono = time.monotonic_ns()
            start_thread = (
                time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
            )
            start_proc = (
                time.process_time_ns() if hasattr(time, "process_time_ns") else 0
            )
            if depth == 0:
                self._emit(
                    "clip_cold_forward_start",
                    wall_unix_ns=start_wall,
                    monotonic_ns=start_mono,
                    metadata={"span": "clip_cold_forward"},
                )
            status = "ok"
            try:
                result = original(*args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                end_wall = time.time_ns()
                end_mono = time.monotonic_ns()
                end_thread = (
                    time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
                )
                end_proc = (
                    time.process_time_ns() if hasattr(time, "process_time_ns") else 0
                )
                _FWD_DEPTH.set(_FWD_DEPTH.get() - 1)
                if depth == 0:
                    try:
                        wall_ms = _ms(start_mono, end_mono)
                        self._last_forward_ms = wall_ms
                        self._last_forward_end_mono_ns = end_mono
                        self._forward_wall_ms_total += wall_ms
                        self._emit(
                            "clip_cold_forward_end",
                            wall_unix_ns=end_wall,
                            monotonic_ns=end_mono,
                            metadata={
                                "status": status,
                                "wall_ms": wall_ms,
                                "thread_cpu_ms": _ms(start_thread, end_thread),
                                "process_cpu_ms": _ms(start_proc, end_proc),
                            },
                        )
                    except Exception:
                        pass
            return result
        return wrapper

    def _make_clip_encode_wrapper(
        self, span_name: str, original: Callable[..., Any]
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(clip: Any, *args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(clip, *args, **kwargs)
            depth = _ENC_DEPTH.get()
            _ENC_DEPTH.set(depth + 1)
            start_wall = time.time_ns()
            start_mono = time.monotonic_ns()
            start_thread = (
                time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
            )
            start_proc = (
                time.process_time_ns() if hasattr(time, "process_time_ns") else 0
            )
            if depth == 0:
                try:
                    self._ensure_forward_wrapper(clip)
                except Exception:
                    pass
                self._emit(
                    f"{span_name}_start",
                    wall_unix_ns=start_wall,
                    monotonic_ns=start_mono,
                    metadata={"span": span_name},
                )
            status = "ok"
            try:
                result = original(clip, *args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                end_wall = time.time_ns()
                end_mono = time.monotonic_ns()
                end_thread = (
                    time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
                )
                end_proc = (
                    time.process_time_ns() if hasattr(time, "process_time_ns") else 0
                )
                _ENC_DEPTH.set(_ENC_DEPTH.get() - 1)
                if depth == 0:
                    try:
                        self._finish_encode(
                            clip,
                            span_name,
                            args,
                            kwargs,
                            start_wall=start_wall,
                            start_mono=start_mono,
                            end_wall=end_wall,
                            end_mono=end_mono,
                            start_thread=start_thread,
                            end_thread=end_thread,
                            start_proc=start_proc,
                            end_proc=end_proc,
                            status=status,
                        )
                    except Exception:
                        pass
            return result
        return wrapper

    def _finish_encode(
        self,
        clip: Any,
        span_name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        start_wall: int,
        start_mono: int,
        end_wall: int,
        end_mono: int,
        start_thread: int,
        end_thread: int,
        start_proc: int,
        end_proc: int,
        status: str,
    ) -> None:
        tokens = args[0] if args else kwargs.get("tokens", {})
        token_count, batch_count = _count_tokens(tokens)
        forward_ms = self._last_forward_ms
        post_forward_ms: float | None = None
        if (
            self._last_forward_end_mono_ns is not None
            and end_mono >= self._last_forward_end_mono_ns
        ):
            post_forward_ms = round(
                (end_mono - self._last_forward_end_mono_ns) / 1_000_000, 3
            )
        patcher = getattr(clip, "patcher", None)
        identity = self._clip_identity(patcher) if patcher is not None else {}
        wall_ms = _ms(start_mono, end_mono)
        self._encode_wall_ms_total += wall_ms
        self._last_encode_end_mono_ns = end_mono
        encode_index = len(self._encode_calls) + 1
        record = {
            "span": span_name,
            "status": status,
            "wall_ms": wall_ms,
            "forward_wall_ms": forward_ms,
            "post_forward_ms": post_forward_ms,
            "token_count": token_count,
            "batch_count": batch_count,
            "encode_index": encode_index,
            "thread_cpu_ms": _ms(start_thread, end_thread),
            "process_cpu_ms": _ms(start_proc, end_proc),
        }
        record.update(identity)
        self._encode_calls.append(record)
        if len(self._encode_calls) > _ENCODE_RECORD_LIMIT:
            del self._encode_calls[:-_ENCODE_RECORD_LIMIT]
        self._resident_patchers.update(_PAT_LOAD_STACK.get())
        self._emit(
            f"{span_name}_end",
            wall_unix_ns=end_wall,
            monotonic_ns=end_mono,
            metadata=record,
        )

    def _make_cache_lookup_wrapper(
        self, original: Callable[..., Any]
    ) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(cache_self: Any, *args: Any, **kwargs: Any) -> Any:
            if not self._enabled:
                return original(cache_self, *args, **kwargs)
            start_wall = time.time_ns()
            start_mono = time.monotonic_ns()
            status = "ok"
            result = None
            try:
                result = original(cache_self, *args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                try:
                    hit_count, miss_count = _parse_lookup_result(result)
                    if hit_count + miss_count > 0:
                        if miss_count == 0:
                            decision = "hit"
                        elif hit_count == 0:
                            decision = "miss"
                        else:
                            decision = "partial"
                    else:
                        decision = "miss" if status == "ok" else "error"
                    self._cache_hits += hit_count
                    self._cache_misses += miss_count
                    self._cache_decisions.append(decision)
                    if len(self._cache_decisions) > _ENCODE_RECORD_LIMIT:
                        del self._cache_decisions[:-_ENCODE_RECORD_LIMIT]
                    self._emit(
                        "clip_cold_cache_lookup",
                        wall_unix_ns=time.time_ns(),
                        monotonic_ns=time.monotonic_ns(),
                        metadata={
                            "status": status,
                            "hit_count": hit_count,
                            "miss_count": miss_count,
                            "decision": decision,
                            "wall_ms": _ms(start_mono, time.monotonic_ns()),
                        },
                    )
                except Exception:
                    pass
            return result
        return wrapper

    # ── Summary / flush ──────────────────────────────────────────────────

    def request_summary(self) -> dict[str, Any]:
        multi_load: list[str] = []
        for patcher_id, seq in self._residency.items():
            load_count = sum(1 for entry in seq if entry["event"] == "load")
            if load_count > 1:
                multi_load.append(patcher_id)
        summary: dict[str, Any] = {
            "request_id": self._resolve_request_id(),
            "enabled": self._enabled,
            "encode_calls": len(self._encode_calls),
            "load_calls": len(self._load_calls),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_decisions": list(self._cache_decisions),
            "multi_load_patchers": sorted(multi_load),
            "moved_more_than_once": bool(multi_load),
            "total_h2d_bytes": self._h2d_bytes_total,
            "total_transfer_ops": self._transfer_ops_total,
            "histogram": {
                bucket: dict(entry) for bucket, entry in self._histogram.items()
            },
            "pinned_count": self._pinned_count,
            "pageable_count": self._pageable_count,
            "total_sync_count": self._sync_count,
            "total_sync_ms": round(self._sync_ms, 3),
            "load_wall_ms_total": round(self._load_wall_ms_total, 3),
            "forward_wall_ms_total": round(self._forward_wall_ms_total, 3),
            "encode_wall_ms_total": round(self._encode_wall_ms_total, 3),
            "tokenize_wall_ms_total": round(self._tokenize_wall_ms_total, 3),
            "resident_at_last_encode": sorted(self._resident_patchers),
            "events": [dict(event) for event in self._events],
        }
        return summary

    def flush(self) -> None:
        if not self._enabled:
            return
        try:
            summary = self.request_summary()
            parts = [f"request_id={summary['request_id']}"]
            for key in (
                "encode_calls",
                "load_calls",
                "cache_hits",
                "cache_misses",
                "multi_load_patchers",
                "moved_more_than_once",
                "total_h2d_bytes",
                "total_transfer_ops",
                "total_sync_count",
                "total_sync_ms",
                "load_wall_ms_total",
                "forward_wall_ms_total",
                "encode_wall_ms_total",
                "tokenize_wall_ms_total",
                "resident_at_last_encode",
            ):
                value = summary.get(key)
                if isinstance(value, float):
                    parts.append(f"{key}={value:.3f}")
                else:
                    parts.append(f"{key}={value}")
            print(f"[v2.clip_cold_forensics] {' '.join(parts)}", flush=True)
        except Exception:
            pass


def _count_tokens(tokens: Any) -> tuple[int, int]:
    token_count = 0
    batch_count = 1
    try:
        if isinstance(tokens, Mapping):
            for value in tokens.values():
                if isinstance(value, (list, tuple)):
                    batch_count = max(batch_count, len(value))
                    for inner in value:
                        if isinstance(inner, (list, tuple)):
                            token_count += len(inner)
        elif isinstance(tokens, (list, tuple)):
            batch_count = max(batch_count, len(tokens))
            token_count = len(tokens)
    except Exception:
        pass
    return token_count, batch_count


def _parse_lookup_result(result: Any) -> tuple[int, int]:
    if isinstance(result, tuple) and len(result) >= 4:
        hit_count = result[2]
        miss_count = result[3]
    elif isinstance(result, tuple) and len(result) == 2:
        hits, misses = result[0], result[1]
        hit_count = len(hits) if isinstance(hits, (dict, list)) else 0
        miss_count = len(misses) if isinstance(misses, (list, tuple)) else 0
    else:
        return 0, 0
    try:
        return int(hit_count), int(miss_count)
    except Exception:
        return 0, 0


_INSTANCE: ClipColdPathForensics | None = None


def install_forensics_if_enabled(trace: Any = None) -> dict[str, str]:
    """Idempotent module-level install; inert unless the flag is set."""
    global _INSTANCE
    if not forensics_enabled():
        return {"status": "disabled"}
    if _INSTANCE is None:
        _INSTANCE = ClipColdPathForensics()
    if trace is not None:
        _INSTANCE._trace = trace
    return _INSTANCE.install()
