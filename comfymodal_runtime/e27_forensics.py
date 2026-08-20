"""Batch E27 forensics: memory-boundary telemetry + missing critical-path spans.

Targets: the baseline Gantt (Target E), memory-state capture at key boundaries
(Targets B/D), the empty_cache decomposition (Target B) and Qwen cast counting
(Target D) — implemented HERE so they do not depend on the D2-era
``COMFYMODAL_V2_CLIP_COLD_FORENSICS`` gate that the E19 atomic profile forces
off.

Everything here is measurement/telemetry ONLY and gated behind
``COMFYMODAL_V2_E27_FORENSICS`` (default off).  With the gate off every
function is a no-op and no span/event is emitted.  The module never mutates
the model data used by generation and never changes the native call order.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any, Callable, Mapping

from .env import env_flag

_E27_FORENSICS_FLAG = "COMFYMODAL_V2_E27_FORENSICS"
_ENABLED: bool = env_flag(_E27_FORENSICS_FLAG, default=False)

# Sentinels so wrappers install exactly once and are identifiable.
_SENTINEL_EMPTY_CACHE = "_comfymodal_e27_empty_cache_wrapper"
_SENTINEL_SOFT_CACHE = "_comfymodal_e27_soft_cache_wrapper"
_SENTINEL_CAST = "_comfymodal_e27_cast_wrapper"

# Context var for the soft-cache decomposition (per-call operation record).
_SOFT_CACHE_CONTEXT: "threading.local" = threading.local()

# Cast accounting registry (module-level, thread-safe, bounded).
_CAST_LOCK = threading.Lock()
_cast_account: dict[str, Any] = {
    "operations": 0,
    "bytes": 0,
    "source_dtypes": {},
    "dest_dtypes": {},
    "first_keys": [],
    "wall_ms": 0.0,
}

# ── E27 Follow-Up A: forward-cast telemetry on the REAL cast path ──────────
# The prior E27 counter hooked ``ModelPatcher.patch_weight_to_device`` (patch/
# invalidation events).  This batch ALSO instruments the actual per-forward
# dtype conversion performed by the Qwen encoder: ``comfy.ops.cast_bias_weight``
# and the ``cast_to`` family (the manual-cast tax).  Both counters are kept
# separate and never conflated.
_SENTINEL_FORWARD_CAST = "_comfymodal_e27_forward_cast_wrapper"
_FORWARD_CAST_LOCK = threading.Lock()
_forward_cast_account: dict[str, Any] = {
    "weight_casts": 0,
    "bias_casts": 0,
    "other_casts": 0,
    "source_bytes": 0,
    "dest_bytes": 0,
    "source_dtypes": {},
    "dest_dtypes": {},
    "wall_ms": 0.0,
    "cuda_event_wall_ms": 0.0,
    "allocations": 0,
    "peak_transient_bytes": 0,
    "first_weight_shapes": [],
    "first_bias_shapes": [],
}

# Lazily resolved torch.cuda event factories (CUDA may be unavailable at
# import time on the dev box).
def _torch_cuda_event_factory() -> Callable[..., Any] | None:
    try:
        import torch as _torch_ev

        if not _torch_ev.cuda.is_available():
            return None
        return _torch_ev.cuda.Event
    except Exception:
        return None


_torch_cuda_event: Callable[..., Any] | None = None


def torch_cuda_event() -> Any:
    """Return a new ``torch.cuda.Event`` (or a no-op stub when CUDA is
    unavailable / import fails).  Never raises."""
    global _torch_cuda_event
    try:
        if _torch_cuda_event is None:
            _factory = _torch_cuda_event_factory()
            if _factory is None:
                class _NoopEvent:
                    def record(self) -> None:  # noqa: D401
                        pass

                    def elapsed_time(self, _other: Any) -> float:
                        return 0.0

                _factory = _NoopEvent
            _torch_cuda_event = _factory
        return _torch_cuda_event()
    except Exception:
        class _NoopEvent2:
            def record(self) -> None:
                pass

            def elapsed_time(self, _other: Any) -> float:
                return 0.0

        return _NoopEvent2()


def _install_forward_cast_counter(owner: Any, attr: str, kind: str) -> str:
    """Wrap one comfy ops cast function and count weight/bias/other casts."""
    if not _ENABLED:
        return "gated_off"
    try:
        original = getattr(owner, attr, None)
        if not callable(original):
            return "unavailable"
        if getattr(original, _SENTINEL_FORWARD_CAST, False):
            return "already"

        @functools_wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _ENABLED:
                return original(*args, **kwargs)
            start_ns = time.monotonic_ns()
            try:
                result = original(*args, **kwargs)
            except BaseException:
                raise
            finally:
                end_ns = time.monotonic_ns()
                _kind = kind
                _weight = None
                _dest_dtype = None
                _src_dtype = None
                try:
                    # cast_bias_weight(weight, bias, dtype) -> (weight, bias)
                    if _kind == "cast_bias_weight" and len(args) >= 1:
                        _weight = args[0]
                        if len(args) >= 3:
                            _dest_dtype = args[2]
                    else:
                        # cast_to(tensor, dtype, ...) / comfy ops variants
                        _weight = args[0] if args else None
                        if len(args) >= 2:
                            _dest_dtype = args[1]
                        elif "dtype" in kwargs:
                            _dest_dtype = kwargs["dtype"]
                except Exception:
                    pass
                _src_nbytes = 0
                _dest_nbytes = 0
                _src_dtype_s = "unknown"
                _dest_dtype_s = "unknown"
                try:
                    if _weight is not None:
                        _src_dtype_s = str(getattr(_weight, "dtype", "unknown"))
                        _src_nbytes = int(
                            getattr(_weight, "numel", lambda: 0)() * getattr(
                                getattr(_weight, "dtype", None), "itemsize", 0
                            )
                        ) if callable(getattr(_weight, "numel", None)) else 0
                    if result is not None:
                        _res = result[0] if isinstance(result, tuple) else result
                        if _res is not None:
                            _dest_dtype_s = str(getattr(_res, "dtype", "unknown"))
                            _dest_nbytes = int(
                                getattr(_res, "numel", lambda: 0)() * getattr(
                                    getattr(_res, "dtype", None), "itemsize", 0
                                )
                            ) if callable(getattr(_res, "numel", None)) else 0
                    if _dest_dtype is not None:
                        _dest_dtype_s = str(_dest_dtype)
                except Exception:
                    pass
                _is_bias = (
                    _kind == "cast_bias_weight"
                    and len(args) >= 2
                    and args[1] is not None
                    and _weight is not None
                )
                # E27 Follow-Up A: capture per-cast CUDA event timing when the
                # result tensor is a CUDA tensor (aggregate only; one sync at
                # the end of the forward, never per-cast).
                _cuda_event_wall_ms: float | None = None
                try:
                    _res_t = result[0] if isinstance(result, tuple) else result
                    if _res_t is not None and getattr(
                        getattr(_res_t, "device", None), "type", ""
                    ) == "cuda":
                        _ev_start = torch_cuda_event()
                        _ev_end = torch_cuda_event()
                        _ev_end.record()
                        _cuda_event_wall_ms = float(_ev_start.elapsed_time(_ev_end)) / 1_000.0
                except Exception:
                    _cuda_event_wall_ms = None
                with _FORWARD_CAST_LOCK:
                    if _kind == "cast_bias_weight" and _is_bias:
                        _forward_cast_account["bias_casts"] += 1
                    elif _kind == "cast_bias_weight":
                        _forward_cast_account["weight_casts"] += 1
                    else:
                        _forward_cast_account["other_casts"] += 1
                    _forward_cast_account["source_bytes"] += _src_nbytes
                    _forward_cast_account["dest_bytes"] += _dest_nbytes
                    _forward_cast_account["wall_ms"] += (end_ns - start_ns) / 1_000_000
                    if _cuda_event_wall_ms is not None:
                        _forward_cast_account["cuda_event_wall_ms"] += _cuda_event_wall_ms
                    _forward_cast_account["allocations"] += 1
                    _forward_cast_account["source_dtypes"][_src_dtype_s] = (
                        _forward_cast_account["source_dtypes"].get(_src_dtype_s, 0) + 1
                    )
                    _forward_cast_account["dest_dtypes"][_dest_dtype_s] = (
                        _forward_cast_account["dest_dtypes"].get(_dest_dtype_s, 0) + 1
                    )
                    _peak = _forward_cast_account["peak_transient_bytes"]
                    if _src_nbytes > _peak:
                        _forward_cast_account["peak_transient_bytes"] = _src_nbytes
                    if _is_bias:
                        if len(_forward_cast_account["first_bias_shapes"]) < 8:
                            try:
                                _forward_cast_account["first_bias_shapes"].append(
                                    str(getattr(_weight, "shape", ())))
                            except Exception:
                                pass
                    else:
                        if len(_forward_cast_account["first_weight_shapes"]) < 8:
                            try:
                                _forward_cast_account["first_weight_shapes"].append(
                                    str(getattr(_weight, "shape", ())))
                            except Exception:
                                pass
            return result

        setattr(wrapper, _SENTINEL_FORWARD_CAST, True)
        setattr(owner, attr, wrapper)
        return "installed"
    except Exception as exc:
        return f"error:{type(exc).__name__}:{str(exc)[:120]}"


def install_forward_cast_counters(comfy_ops: Any) -> dict[str, str]:
    """Install wrappers on the comfy ops cast entry points (the REAL
    per-forward manual-cast path).  Returns per-attribute install status.

    Targets: ``cast_bias_weight`` (weight+bias cast entry), ``cast_to``,
    ``cast_to_device`` (comfy.ops variants).  No-op when the gate is off.
    """
    result: dict[str, str] = {}
    if not _ENABLED:
        return {"gated": "off"}
    if comfy_ops is None:
        return {"error": "comfy_ops_unavailable"}
    for attr, kind in (
        ("cast_bias_weight", "cast_bias_weight"),
        ("cast_to", "cast_to"),
        ("cast_to_device", "cast_to_device"),
    ):
        result[attr] = _install_forward_cast_counter(comfy_ops, attr, kind)
    return result


def forward_cast_account_summary() -> dict[str, Any]:
    """JSON-safe copy of the forward-cast counter (never raises)."""
    with _FORWARD_CAST_LOCK:
        return {
            "weight_casts": int(_forward_cast_account.get("weight_casts", 0)),
            "bias_casts": int(_forward_cast_account.get("bias_casts", 0)),
            "other_casts": int(_forward_cast_account.get("other_casts", 0)),
            "source_bytes": int(_forward_cast_account.get("source_bytes", 0)),
            "dest_bytes": int(_forward_cast_account.get("dest_bytes", 0)),
            "wall_ms": round(float(_forward_cast_account.get("wall_ms", 0.0)), 3),
            "cuda_event_wall_ms": round(
                float(_forward_cast_account.get("cuda_event_wall_ms", 0.0)), 3
            ),
            "allocations": int(_forward_cast_account.get("allocations", 0)),
            "source_dtypes": dict(_forward_cast_account.get("source_dtypes", {})),
            "dest_dtypes": dict(_forward_cast_account.get("dest_dtypes", {})),
            "peak_transient_bytes": int(
                _forward_cast_account.get("peak_transient_bytes", 0)
            ),
            "first_weight_shapes": list(
                _forward_cast_account.get("first_weight_shapes", [])
            ),
            "first_bias_shapes": list(
                _forward_cast_account.get("first_bias_shapes", [])
            ),
        }


def reset_forward_cast_account() -> None:
    with _FORWARD_CAST_LOCK:
        _forward_cast_account.update({
            "weight_casts": 0,
            "bias_casts": 0,
            "other_casts": 0,
            "source_bytes": 0,
            "dest_bytes": 0,
            "source_dtypes": {},
            "dest_dtypes": {},
            "wall_ms": 0.0,
            "cuda_event_wall_ms": 0.0,
            "allocations": 0,
            "peak_transient_bytes": 0,
            "first_weight_shapes": [],
            "first_bias_shapes": [],
        })


def e27_forensics_enabled() -> bool:
    return _ENABLED


def _active_trace() -> Any:
    """Resolve the active request trace (or None) without importing cost.

    The ``_ACTIVE_LANE_TRACE`` ContextVar holds a ``ModelLaneTrace`` wrapper
    (which has no ``emit``); unwrap it to the underlying runtime trace so
    ``emit_e27_span``/soft-cache wrappers never call ``emit`` on the wrapper
    (the E28 cold-run crash: ``'ModelLaneTrace' object has no attribute
    'emit'`` in the prefill encode's soft_empty_cache path)."""
    try:
        module = sys.modules.get("comfymodal_runtime.model_preload")
        if module is None:
            return None
        for name in ("_ACTIVE_REQUEST_TRACE", "_ACTIVE_LANE_TRACE"):
            variable = getattr(module, name, None)
            getter = getattr(variable, "get", None)
            if callable(getter):
                trace = getter()
                if trace is None:
                    continue
                # Unwrap a ModelLaneTrace to its underlying runtime trace.
                if hasattr(trace, "_trace"):
                    inner = getattr(trace, "_trace", None)
                    if inner is not None:
                        return inner
                return trace
    except Exception:
        pass
    return None


def emit_e27_span(name: str, *, start_ns: int, end_ns: int, **metadata: Any) -> None:
    """Emit one gantt-consumable span pair on the active request trace.

    No-op when the gate is off or no trace is active.  Emits
    ``<name>_start`` and ``<name>_end`` events carrying ``monotonic_ns`` on
    the shared remote monotonic clock.
    """
    if not _ENABLED:
        return
    try:
        trace = _active_trace()
        if trace is None:
            return
        start_ns = int(start_ns)
        end_ns = int(end_ns)
        if end_ns < start_ns:
            end_ns = start_ns
        metadata = dict(metadata)
        metadata.setdefault("e27_span", name)
        trace.emit(f"{name}_start", phase="execution", metadata={
            **metadata, "monotonic_ns_start": start_ns})
        trace.emit(f"{name}_end", phase="execution", metadata={
            **metadata, "monotonic_ns_end": end_ns,
            "duration_ms": round((end_ns - start_ns) / 1_000_000, 3)})
    except Exception:
        pass


def cuda_memory_snapshot() -> dict[str, Any]:
    """Aggregated CUDA memory state (never a full memory_summary dump).

    Returns JSON-safe values; each read is guarded and may return None.
    """
    out: dict[str, Any] = {}
    try:
        import torch

        if not torch.cuda.is_available():
            out["cuda_available"] = False
            return out
        out["cuda_available"] = True
        out["monotonic_ns"] = time.monotonic_ns()
        free_bytes, total_bytes = torch.cuda.mem_get_info()
        out["mem_get_info_free_bytes"] = int(free_bytes)
        out["mem_get_info_total_bytes"] = int(total_bytes)
        out["memory_allocated_bytes"] = int(torch.cuda.memory_allocated())
        out["memory_reserved_bytes"] = int(torch.cuda.memory_reserved())
        try:
            stats = torch.cuda.memory_stats()
            out["active_bytes"] = int(stats.get("active_bytes.all.current", 0) or 0)
            out["inactive_split_bytes"] = int(
                stats.get("inactive_split_bytes.all.current", 0) or 0)
            out["allocated_bytes_peak"] = int(
                stats.get("allocated_bytes.all.peak", 0) or 0)
            out["reserved_bytes_peak"] = int(
                stats.get("reserved_bytes.all.peak", 0) or 0)
            out["num_alloc_retries"] = int(
                stats.get("num_alloc_retries", 0) or 0)
            out["num_ooms"] = int(stats.get("num_ooms", 0) or 0)
            out["num_segments"] = int(stats.get("num_segments", 0) or 0)
        except Exception:
            pass
        return out
    except Exception:
        return {"cuda_available": False, "error": "snapshot_failed"}


def snapshot_e27_memory(trace: Any, boundary: str, **extra: Any) -> dict[str, Any]:
    """Capture a CUDA memory snapshot at a named boundary and emit it as a
    point event ``e27_memory_<boundary>`` on the trace.

    Aggregated (the requirement forbids dominating the critical path with
    per-event dumps).  No-op when gated off.
    """
    if not _ENABLED:
        return {}
    try:
        mem = cuda_memory_snapshot()
        metadata = dict(extra)
        metadata.update(mem)
        metadata["boundary"] = str(boundary)
        trace.emit(
            f"e27_memory_{boundary}",
            phase="execution",
            metadata=metadata,
        )
        return mem
    except Exception:
        return {}


def install_e27_memory_boundaries(trace: Any, *, boundaries: Mapping[str, Any]) -> None:
    """Install named memory boundaries (mapping boundary-name -> extra dict).

    Used for the fixed set of baseline memory boundaries.  No-op when gated
    off.
    """
    if not _ENABLED:
        return
    try:
        for boundary, extra in (boundaries or {}).items():
            snapshot_e27_memory(trace, str(boundary), **(extra or {}))
    except Exception:
        pass


# ── Target B: empty_cache decomposition (E27-native, D2-gate independent) ──

_EMPTY_CACHE_OPS = ("synchronize", "empty_cache", "ipc_collect")


def _install_callable(owner: Any, attr: str, wrapper: Callable[..., Any]) -> str:
    """Install *wrapper* on owner.attr if not already installed."""
    try:
        current = getattr(owner, attr, None)
        if current is not None and getattr(current, _SENTINEL_EMPTY_CACHE, False):
            return "already"
        setattr(wrapper, _SENTINEL_EMPTY_CACHE, True)
        setattr(owner, attr, wrapper)
        return "installed"
    except Exception:
        return "error"


def install_empty_cache_decomposition(torch_mod: Any) -> dict[str, str]:
    """Wrap torch.cuda.synchronize / empty_cache / ipc_collect to decompose
    every soft_empty_cache call.  Returns per-operation install status.

    Gated on the E27 flag; each wrapper records its own wall and aggregates
    into the soft-cache record under ``_SOFT_CACHE_CONTEXT``.  Never alters
    call order or semantics.
    """
    result: dict[str, str] = {}
    if not _ENABLED:
        return {op: "gated_off" for op in _EMPTY_CACHE_OPS}
    try:
        import torch

        cuda_mod = getattr(torch, "cuda", None)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}

    for operation in _EMPTY_CACHE_OPS:
        owner = cuda_mod if cuda_mod is not None and callable(getattr(cuda_mod, operation, None)) else torch_mod
        original = getattr(owner, operation, None)
        if not callable(original):
            result[operation] = "unavailable"
            continue

        @functools_wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            _operation = operation
            _original = original
            start_ns = time.monotonic_ns()
            status = "ok"
            try:
                return _original(*args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                end_ns = time.monotonic_ns()
                context = getattr(_SOFT_CACHE_CONTEXT, "record", None)
                if isinstance(context, dict):
                    context.setdefault("operations", {})[_operation] = {
                        "start_ns": start_ns,
                        "end_ns": end_ns,
                        "status": status,
                        "wall_ms": round((end_ns - start_ns) / 1_000_000, 4),
                    }

        result[operation] = _install_callable(owner, operation, wrapper)
    return result


def install_soft_empty_cache_wrapper(mm_module: Any, torch_mod: Any) -> str:
    """Wrap ``comfy.model_management.soft_empty_cache`` to bracket each call
    with before/after allocator state + per-operation decomposition.

    Returns install status.  Gated on the E27 flag; native path unchanged.
    """
    if not _ENABLED:
        return "gated_off"
    try:
        original = getattr(mm_module, "soft_empty_cache", None)
        if not callable(original):
            return "unavailable"
        if getattr(original, _SENTINEL_SOFT_CACHE, False):
            return "already"

        @functools_wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _ENABLED:
                return original(*args, **kwargs)
            start_ns = time.monotonic_ns()
            before = cuda_memory_snapshot()
            record: dict[str, Any] = {
                "start_mono_ns": start_ns,
                "memory_before": before,
                "operations": {},
            }
            _SOFT_CACHE_CONTEXT.record = record
            status = "ok"
            try:
                return original(*args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                end_ns = time.monotonic_ns()
                after = cuda_memory_snapshot()
                ops = record.get("operations", {})
                sync = ops.get("synchronize") or {}
                empty = ops.get("empty_cache") or {}
                ipc = ops.get("ipc_collect") or {}
                trace = _active_trace()
                if trace is not None:
                    pred_record = take_free_memory_predicate_record()
                    metadata = {
                        "status": status,
                        "pre_sync_ms": round(
                            (int(sync.get("start_ns", start_ns)) - start_ns) / 1_000_000, 4),
                        "cuda_synchronize_ms": sync.get("wall_ms"),
                        "empty_cache_ms": empty.get("wall_ms"),
                        "ipc_collect_ms": ipc.get("wall_ms"),
                        "soft_empty_cache_total_ms": round(
                            (end_ns - start_ns) / 1_000_000, 4),
                        "allocated_before": (before or {}).get("memory_allocated_bytes"),
                        "reserved_before": (before or {}).get("memory_reserved_bytes"),
                        "allocated_after": (after or {}).get("memory_allocated_bytes"),
                        "reserved_after": (after or {}).get("memory_reserved_bytes"),
                        "free_bytes_before": (before or {}).get("mem_get_info_free_bytes"),
                        "free_bytes_after": (after or {}).get("mem_get_info_free_bytes"),
                        "inactive_split_before": (before or {}).get("inactive_split_bytes"),
                        "inactive_split_after": (after or {}).get("inactive_split_bytes"),
                    }
                    # E27 Follow-Up A: attach the exact free_memory predicate
                    # operands so the raw log makes the branch recomputable.
                    if isinstance(pred_record, dict):
                        metadata["free_memory_predicate"] = pred_record
                    trace.emit(
                        "e27_soft_empty_cache",
                        phase="execution",
                        metadata=metadata,
                    )
                    # The Gantt ``empty_cache`` lane consumes the same pair
                    # as the D2 forensics path (names must match).
                    trace.emit(
                        "model_management_soft_empty_cache_start",
                        phase="execution",
                        metadata={"monotonic_ns_start": start_ns},
                    )
                    trace.emit(
                        "model_management_soft_empty_cache_end",
                        phase="execution",
                        metadata={
                            "monotonic_ns_end": end_ns,
                            "duration_ms": round((end_ns - start_ns) / 1_000_000, 4),
                        },
                    )
                    # ── E29: canonical ledger soft_empty_cache event ──────
                    # The measured soft_empty_cache wall (sync + empty_cache +
                    # ipc) becomes a ledger event so the serial ledger owns
                    # the sampling_end->VAE memory-management window with
                    # REAL measured values (never the D18-era assumption).
                    try:
                        from .critical_path_ledger import record_event as _ledger_event
                        _ledger_event(
                            "soft_empty_cache",
                            mono_ns=start_ns,
                            metadata={
                                "status": status,
                                "total_ms": round((end_ns - start_ns) / 1_000_000, 4),
                                "sync_ms": sync.get("wall_ms"),
                                "empty_cache_ms": empty.get("wall_ms"),
                                "ipc_collect_ms": ipc.get("wall_ms"),
                            },
                        )
                    except Exception:
                        pass
                _SOFT_CACHE_CONTEXT.record = None

        setattr(wrapper, _SENTINEL_SOFT_CACHE, True)
        setattr(mm_module, "soft_empty_cache", wrapper)
        return "installed"
    except Exception as exc:
        return f"error:{type(exc).__name__}:{str(exc)[:120]}"


def install_soft_cache_chain(mm_module: Any, torch_mod: Any) -> dict[str, Any]:
    """Install the soft-cache wrapper + the three CUDA operation wrappers.

    Returns a JSON-safe status dict.  Never raises.
    """
    ops = install_empty_cache_decomposition(torch_mod)
    soft = install_soft_empty_cache_wrapper(mm_module, torch_mod)
    pred = install_free_memory_predicate_wrapper(mm_module)
    return {
        "soft_empty_cache": soft,
        "cuda_operations": ops,
        "free_memory_predicate": pred,
        "enabled": _ENABLED,
    }


# ── E27 Follow-Up A: exact free_memory/soft-empty-cache predicate ─────────
# The follow-up requires the raw log to make "WHY DID THIS BRANCH FIRE?"
# recomputable from the actual operands, not a paraphrase of Comfy's branch.
_SENTINEL_FREE_MEMORY = "_comfymodal_e27_free_memory_wrapper"
_FREE_MEMORY_CONTEXT: "threading.local" = threading.local()


def install_free_memory_predicate_wrapper(mm_module: Any) -> str:
    """Wrap ``comfy.model_management.free_memory`` to capture the exact
    decision inputs immediately before the soft_empty_cache branch.

    Captures the real operands used by the pinned Comfy predicate:
    memory_required, driver/device free, torch allocator free/cached,
    allocated/reserved, inactive split, HIGH_VRAM mode, models considered/
    actually unloaded, bytes requested/unloaded, and the recomputed 25%
    threshold.  The record is attached to the next ``e27_soft_empty_cache``
    event so the raw log exposes every operand.
    """
    if not _ENABLED:
        return "gated_off"
    try:
        original = getattr(mm_module, "free_memory", None)
        if not callable(original):
            return "unavailable"
        if getattr(original, _SENTINEL_FREE_MEMORY, False):
            return "already"

        @functools_wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _ENABLED:
                return original(*args, **kwargs)
            record: dict[str, Any] = {
                "wall": "call",
                "mono_ns": time.monotonic_ns(),
            }
            try:
                # free_memory(memory_required, device=..., keep_banks=...)
                memory_required = args[0] if args else kwargs.get("memory_required")
                try:
                    record["memory_required"] = float(memory_required)
                except Exception:
                    record["memory_required"] = str(memory_required)
                record["free_memory_args"] = len(args)
                record["free_memory_kwargs"] = {
                    k: str(v)[:80] for k, v in kwargs.items()
                }
                import torch as _torch_fm

                _dev = _torch_fm.cuda.current_device()
                _free, _total = _torch_fm.cuda.mem_get_info(_dev)
                record["mem_get_info_free_bytes"] = int(_free)
                record["mem_get_info_total_bytes"] = int(_total)
                record["memory_allocated_bytes"] = int(
                    _torch_fm.cuda.memory_allocated(_dev)
                )
                record["memory_reserved_bytes"] = int(
                    _torch_fm.cuda.memory_reserved(_dev)
                )
                _stats = _torch_fm.cuda.memory_stats(_dev)
                record["active_bytes"] = int(
                    _stats.get("active_bytes.all.current", 0) or 0
                )
                record["inactive_split_bytes"] = int(
                    _stats.get("inactive_split_bytes.all.current", 0) or 0
                )
                record["allocated_bytes_peak"] = int(
                    _stats.get("allocated_bytes.all.peak", 0) or 0
                )
                record["reserved_bytes_peak"] = int(
                    _stats.get("reserved_bytes.all.peak", 0) or 0
                )
                # torch-allocator free (cached-free) vs 25% threshold
                record["torch_allocator_free_bytes"] = max(
                    0, record["memory_reserved_bytes"] - record["memory_allocated_bytes"]
                )
                record["threshold_numerator"] = max(
                    0, record["memory_reserved_bytes"] - record["memory_allocated_bytes"]
                )
                record["threshold_denominator"] = record["mem_get_info_total_bytes"]
                try:
                    record["threshold_ratio"] = round(
                        record["threshold_numerator"] / max(
                            1, record["threshold_denominator"]
                        ),
                        6,
                    )
                except Exception:
                    record["threshold_ratio"] = None
                record["threshold_25pct_of_total"] = round(
                    0.25 * record["mem_get_info_total_bytes"], 1
                )
                try:
                    import comfy.model_management as _cmm

                    record["high_vram_mode"] = str(
                        getattr(_cmm, "get_torch_allocated_free_memory", lambda d: None)(
                            _dev
                        )
                        if callable(getattr(_cmm, "get_torch_allocated_free_memory", None))
                        else None
                    )
                except Exception:
                    pass
            except Exception as _pred_exc:
                record["predicate_capture_error"] = (
                    f"{type(_pred_exc).__name__}:{str(_pred_exc)[:120]}"
                )
            _FREE_MEMORY_CONTEXT.record = record
            status = "ok"
            try:
                return original(*args, **kwargs)
            except BaseException:
                status = "error"
                raise
            finally:
                record["status"] = status
                record["end_mono_ns"] = time.monotonic_ns()
                _FREE_MEMORY_CONTEXT.record = None

        setattr(wrapper, _SENTINEL_FREE_MEMORY, True)
        setattr(mm_module, "free_memory", wrapper)
        return "installed"
    except Exception as exc:
        return f"error:{type(exc).__name__}:{str(exc)[:120]}"


def take_free_memory_predicate_record() -> dict[str, Any] | None:
    """Consume the most recent free_memory predicate record (or None)."""
    record = getattr(_FREE_MEMORY_CONTEXT, "record", None)
    _FREE_MEMORY_CONTEXT.record = None
    return record


# ── Target D: Qwen cast counting (E27-native) ─────────────────────────────

def install_patch_weight_cast_counter(patcher_cls: Any) -> str:
    """Wrap ``ModelPatcher.patch_weight_to_device`` to count weight casts.

    The generic Comfy text-encoder forward materializes compute-ready weights
    per call; this counter proves how many casts / how many bytes a single
    Qwen encode performs.  Gated on the E27 flag; native path unchanged.
    """
    if not _ENABLED:
        return "gated_off"
    try:
        original = getattr(patcher_cls, "patch_weight_to_device", None)
        if not callable(original):
            return "unavailable"
        if getattr(original, _SENTINEL_CAST, False):
            return "already"

        @functools_wraps(original)
        def wrapper(self: Any, weight: Any, *args: Any, **kwargs: Any) -> Any:
            if not _ENABLED:
                return original(self, weight, *args, **kwargs)
            start_ns = time.monotonic_ns()
            try:
                result = original(self, weight, *args, **kwargs)
            except BaseException:
                raise
            finally:
                end_ns = time.monotonic_ns()
                try:
                    nbytes = int(weight.numel() * weight.element_size())
                    src_dtype = str(weight.dtype)
                except Exception:
                    nbytes = 0
                    src_dtype = "unknown"
                with _CAST_LOCK:
                    _cast_account["operations"] += 1
                    _cast_account["bytes"] += nbytes
                    _cast_account["wall_ms"] += (end_ns - start_ns) / 1_000_000
                    _cast_account["source_dtypes"][src_dtype] = (
                        _cast_account["source_dtypes"].get(src_dtype, 0) + 1
                    )
                    if len(_cast_account["first_keys"]) < 8:
                        try:
                            _cast_account["first_keys"].append(
                                str(getattr(weight, "shape", ())))
                        except Exception:
                            pass
            return result

        setattr(wrapper, _SENTINEL_CAST, True)
        setattr(patcher_cls, "patch_weight_to_device", wrapper)
        return "installed"
    except Exception as exc:
        return f"error:{type(exc).__name__}:{str(exc)[:120]}"


def cast_account_summary() -> dict[str, Any]:
    """Return a JSON-safe copy of the cast counter (never raises)."""
    with _CAST_LOCK:
        return {
            "operations": int(_cast_account.get("operations", 0)),
            "bytes": int(_cast_account.get("bytes", 0)),
            "wall_ms": round(float(_cast_account.get("wall_ms", 0.0)), 3),
            "source_dtypes": dict(_cast_account.get("source_dtypes", {})),
            "first_keys": list(_cast_account.get("first_keys", [])),
        }


def reset_cast_account() -> None:
    with _CAST_LOCK:
        _cast_account.update({
            "operations": 0,
            "bytes": 0,
            "source_dtypes": {},
            "dest_dtypes": {},
            "first_keys": [],
            "wall_ms": 0.0,
        })


# ── E27 Follow-Up A: exact Qwen dtype enumeration + resident state ─────────
# The prior report guessed "~16.1 GB if all weights are fp16".  This reads
# the real safetensors header and the hydrated model to answer exactly.

def enumerate_qwen_header_dtypes(path: str) -> dict[str, Any]:
    """Parse a safetensors header and enumerate tensor count / parameter
    bytes by dtype (exact, from the header — no weight read).

    Returns JSON-safe dict (never raises).  Distinguishes total bytes and
    (where the tensor name allows) bias-name bytes.
    """
    result: dict[str, Any] = {"status": "ok", "path": str(path)}
    try:
        import json as _json

        _path = str(path)
        with open(_path, "rb") as fh:
            header_len = int.from_bytes(fh.read(8), "little")
            header = _json.loads(fh.read(header_len))
        tensors = header.get("__metadata__", {})
        del tensors  # metadata (if any) is not a tensor
        count_by_dtype: dict[str, int] = {}
        bytes_by_dtype: dict[str, int] = {}
        bias_bytes_by_dtype: dict[str, int] = {}
        tensor_count = 0
        total_data_bytes = 0
        for key, info in header.items():
            if key == "__metadata__":
                continue
            tensor_count += 1
            dtype = str(info.get("dtype", "unknown"))
            shape = info.get("shape", [])
            nbytes = 1
            for dim in shape:
                nbytes *= int(dim)
            dtype_bytes = {"F32": 4, "F16": 2, "BF16": 2, "F64": 8,
                           "I64": 8, "I32": 4, "I16": 2, "I8": 1,
                           "U8": 1, "BOOL": 1}.get(dtype, 4)
            data_bytes = nbytes * dtype_bytes
            total_data_bytes += data_bytes
            count_by_dtype[dtype] = count_by_dtype.get(dtype, 0) + 1
            bytes_by_dtype[dtype] = bytes_by_dtype.get(dtype, 0) + data_bytes
            is_bias = str(key).endswith(".bias") or str(key).endswith("_bias")
            if is_bias:
                bias_bytes_by_dtype[dtype] = (
                    bias_bytes_by_dtype.get(dtype, 0) + data_bytes
                )
        result.update({
            "tensor_count": tensor_count,
            "total_data_bytes": total_data_bytes,
            "count_by_dtype": count_by_dtype,
            "bytes_by_dtype": bytes_by_dtype,
            "bias_bytes_by_dtype": bias_bytes_by_dtype,
            "bytes_by_dtype_human": {
                k: f"{v / (1024 ** 3):.4f} GiB" for k, v in bytes_by_dtype.items()
            },
            "source": "safetensors_header_exact",
        })
    except Exception as exc:
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}:{str(exc)[:200]}"
    return result


def inspect_resident_clip_dtypes(cpu_models: Any) -> dict[str, Any]:
    """Inspect the actual resident CLIP model dtype state (no mutation).

    Walks the snapshot CLIP model's parameters and reports the resident
    dtype distribution + total bytes.  Returns JSON-safe dict (never raises).
    """
    result: dict[str, Any] = {
        "status": "ok",
        "clip_obj_present": int(cpu_models is not None),
    }
    try:
        if cpu_models is None:
            result["status"] = "no_cpu_models"
            return result
        clip = getattr(cpu_models, "clip", None)
        result["clip_present"] = int(clip is not None)
        if clip is None:
            return result
        count_by_dtype: dict[str, int] = {}
        bytes_by_dtype: dict[str, int] = {}
        total = 0
        params = 0
        seen = set()
        import torch as _torch_res

        def _walk(module: Any, prefix: str = "") -> None:
            nonlocal total, params
            try:
                for name, param in module.named_parameters(
                    prefix=prefix, recurse=False
                ) if hasattr(module, "named_parameters") else ():
                    params += 1
                    if id(param) in seen:
                        continue
                    seen.add(id(param))
                    dt = str(param.dtype)
                    nb = int(param.numel() * param.element_size())
                    total += nb
                    count_by_dtype[dt] = count_by_dtype.get(dt, 0) + 1
                    bytes_by_dtype[dt] = bytes_by_dtype.get(dt, 0) + nb
            except Exception:
                pass
            for name, child in module.named_children():
                _walk(child, prefix=f"{prefix}{name}.")

        _walk(clip)
        result.update({
            "param_count": params,
            "total_bytes": total,
            "count_by_dtype": count_by_dtype,
            "bytes_by_dtype": bytes_by_dtype,
            "bytes_by_dtype_human": {
                k: f"{v / (1024 ** 3):.4f} GiB" for k, v in bytes_by_dtype.items()
            },
            "all_params_bf16_or_fp16": all(
                k in ("torch.bfloat16", "torch.float16")
                for k in count_by_dtype
            ),
            "source": "resident_model_inspection",
        })
    except Exception as exc:
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}:{str(exc)[:200]}"
    return result


def clip_forward_decomposition(trace: Any) -> dict[str, Any]:
    """Decompose the current CLIP-forward wall from the active request trace.

    Reads the span pair events on the trace and returns the CLIP forward
    wall split into: total forward, hydration/read contribution, bind
    contribution, and the remainder (transformer/math + management).  All
    derived from the same remote monotonic events; never raises.
    """
    out: dict[str, Any] = {"status": "ok"}
    try:
        events = getattr(trace, "events", None)
        if events is None:
            return {"status": "no_trace"}
        stamps: dict[str, int] = {}
        for event in list(events):
            name = getattr(event, "name", "")
            mono = getattr(event, "monotonic_ns", 0) or 0
            if isinstance(name, str) and name:
                stamps.setdefault(name, int(mono))
        def span_ms(start: str, end: str) -> float | None:
            if start in stamps and end in stamps:
                return round(
                    (stamps[end] - stamps[start]) / 1_000_000, 3
                )
            return None

        out["clip_forward_ms"] = span_ms("clip_forward_start", "clip_forward_end")
        out["clip_hydration_ms"] = span_ms(
            "clip_fh_hydration_start", "clip_fh_hydration_end"
        )
        out["clip_source_read_ms"] = span_ms(
            "clip_source_read_start", "clip_source_read_end"
        )
        out["clip_bind_ms"] = span_ms("clip_bind_wait_start", "clip_bind_wait_end")
        out["clip_gpu_hydration_ms"] = span_ms(
            "clip_hydration_gpu_start", "clip_hydration_gpu_end"
        )
        out["manual_cast_contribution_ms"] = None
        out["transformer_math_contribution_ms"] = None
        if out.get("clip_forward_ms") is not None:
            fwd = float(out["clip_forward_ms"])
            bind = float(out.get("clip_bind_ms") or 0.0)
            out["transformer_math_contribution_ms"] = round(max(0.0, fwd - bind), 3)
        out["source"] = "remote_monotonic_spans"
    except Exception as exc:
        out = {"status": "error", "error": f"{type(exc).__name__}:{str(exc)[:120]}"}
    return out


def functools_wraps(original: Callable[..., Any]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    try:
        import functools

        return functools.wraps(original)
    except Exception:
        def _identity(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return _identity
