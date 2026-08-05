"""UNET forward probe: weak registry, always-on first-CUDA timing, optional diagnostics.

Always-on (lightweight):
  - ``register_unet_forward_probe(unet, source)`` -- register at snapshot/normal-loader
  - ``install_nextdit_forward_pre_hook()`` / ``install_registered_unet_forward_hooks()``
  - ``set_unet_gpu_demand_start(request_id, monotonic_ns)`` -- called by load_models_gpu wrapper
  - ``reset_first_cuda_dedup()`` -- called at start of each request
  - First forward with CUDA input emits ``unet_first_cuda_op`` with real elapsed
  - ``resolve_diffusion_model(model)`` -- shared resolution helper (Fix 4)
  - ``ensure_sampling_timing_wrapper(model_patcher)`` -- install SAMPLER_SAMPLE wrapper (Fix 4)

Diagnostic-only (gated by COMFYMODAL_V2_UNET_FORWARD_DIAG=1):
  - ``emit_post_load_models_gpu_event(models)``
  - Full ``unet_forward_probe`` events with model state

Safety: read-only, no CUDA synchronize, no tensor mutation, no dtype/device transfer.
"""

from __future__ import annotations

import os
import threading
import time
import weakref

from .env import env_flag, observability_allows
from contextvars import ContextVar
from typing import Any

from .cpu_snapshot_models import collect_unet_forward_probe_state

# ── Shared model resolution helper (Fix 4) ──────────────────────────────────


def resolve_diffusion_model(model: Any) -> tuple[Any | None, Any | None]:
    """Resolve *model* to ``(model_patcher_or_None, diffusion_model_or_None)``.

    Handles four shapes:

    * **ModelPatcher** (has ``model_options``) — walks ``.model.diffusion_model``
      then falls back to ``.diffusion_model``; returns ``(patcher, dm)``.
    * **LoadedModel** — the ``.model`` attribute is itself a ``ModelPatcher``;
      unwrapped recursively to return the inner ``(patcher, dm)``.
    * **BaseModel** (has ``.diffusion_model``, no ``model_options``) —
      returned as ``(None, diffusion_model)``.
    * **Raw diffusion model** (has ``forward``, no ``model_options``, no
      ``diffusion_model`` attribute) — returned as ``(None, model)``.
    """
    if model is None:
        return None, None

    # LoadedModel: .model is a ModelPatcher
    inner = getattr(model, "model", None)
    if inner is not None and hasattr(inner, "model_options"):
        return resolve_diffusion_model(inner)

    # ModelPatcher path: walk .model.diffusion_model, then .diffusion_model
    m = getattr(model, "model", None)
    if m is not None:
        dm = getattr(m, "diffusion_model", None)
        if dm is not None:
            return model, dm
    dm = getattr(model, "diffusion_model", None)
    if dm is not None:
        # If model has model_options it is a ModelPatcher; otherwise BaseModel-like
        if hasattr(model, "model_options"):
            return model, dm
        return None, dm

    # ModelPatcher found but no diffusion_model yet
    if hasattr(model, "model_options"):
        return model, None

    # Raw diffusion model (has forward, is itself the model)
    if hasattr(model, "forward"):
        return None, model

    return None, None


# ``ensure_sampling_timing_wrapper`` lives in ``runtime_executor`` (neutral module).
# Imported lazily inside register_unet_forward_probe to avoid circular import
# (runtime_executor -> model_preload -> unet_forward_probe -> runtime_executor).

# ── Diagnostic gate ──────────────────────────────────────────────────────────
# Disabled by default; set COMFYMODAL_V2_UNET_FORWARD_DIAG=1 to enable.
# Checked at call time (not import time) so test files can set the env var
# before importing.
_DIAG_ENV_KEY = "COMFYMODAL_V2_UNET_FORWARD_DIAG"


def _is_enabled() -> bool:
    """Return True when COMFYMODAL_V2_UNET_FORWARD_DIAG=1.

    Checked at call time so test files can set the env var between
    test file imports.
    """
    return env_flag(_DIAG_ENV_KEY) and observability_allows("unet_forward_diagnostics")

# ── Lazy-resolved ContextVar references ──────────────────────────────────────
# Resolved at first use (not at import) to avoid circular imports.
_ACTIVE_REQUEST_TRACE: ContextVar | None = None
_ACTIVE_LANE_TRACE: ContextVar | None = None
_GPU_REQUEST_CALL_COUNT_VAR: ContextVar | None = None


def _ensure_context_vars() -> None:
    """Resolve ContextVars from model_preload lazily."""
    global _ACTIVE_REQUEST_TRACE, _ACTIVE_LANE_TRACE, _GPU_REQUEST_CALL_COUNT_VAR
    if _ACTIVE_REQUEST_TRACE is not None:
        return
    from .model_preload import (
        _ACTIVE_REQUEST_TRACE as _ART,
        _ACTIVE_LANE_TRACE as _ALT,
        _gpu_request_call_count_var as _GRC,
    )
    _ACTIVE_REQUEST_TRACE = _ART
    _ACTIVE_LANE_TRACE = _ALT
    _GPU_REQUEST_CALL_COUNT_VAR = _GRC


# ── Always-on GPU demand start (first-CUDA timing) ──────────────────────────
# Map: request_id -> monotonic_ns of when load_models_gpu was first called
# for a registered UNET in this request.
_unet_gpu_demand_start: dict[str, int] = {}
_unet_gpu_demand_lock = threading.RLock()

# Bounded: the demand-start map can never grow without bound, even for
# request ids that never consume their entry (the normal cleanup is
# _clear_demand_start_ns after the first CUDA forward).
_UNET_GPU_DEMAND_MAX = 256


def set_unet_gpu_demand_start(request_id: str, monotonic_ns: int) -> None:
    """Record demand start for UNET GPU first forward timing.

    Called from the outermost ``load_models_gpu`` wrapper when the model
    list contains a registered UNET.  Thread-safe.

    Preserves first-demand semantics: a request id already present in the
    map is never overwritten.  The map is insertion-ordered, so when the
    fixed maximum is exceeded the OLDEST request ids are evicted first.
    """
    with _unet_gpu_demand_lock:
        # Only record the *first* demand start per request.
        if request_id not in _unet_gpu_demand_start:
            _unet_gpu_demand_start[request_id] = monotonic_ns
            if len(_unet_gpu_demand_start) > _UNET_GPU_DEMAND_MAX:
                _excess = len(_unet_gpu_demand_start) - _UNET_GPU_DEMAND_MAX
                for _stale in list(_unet_gpu_demand_start.keys())[:_excess]:
                    del _unet_gpu_demand_start[_stale]


def _get_demand_start_ns(request_id: str) -> int | None:
    """Return the demand start monotonic_ns for *request_id*, or None."""
    with _unet_gpu_demand_lock:
        return _unet_gpu_demand_start.get(request_id)


def _clear_demand_start_ns(request_id: str) -> None:
    """Clean up demand start after consumption."""
    with _unet_gpu_demand_lock:
        _unet_gpu_demand_start.pop(request_id, None)


# ── Weak registry ────────────────────────────────────────────────────────────
# Maps id(diffusion_model) -> _ProbeEntry.
# Entries auto-clean when the diffusion_model is garbage collected via finalizer.
# Always active (not gated by _ENABLED) so first-CUDA timing works.
_registry: dict[int, Any] = {}
_registry_lock = threading.RLock()


class _ProbeEntry:
    """Weakly-held registration entry for a diffusion model."""
    __slots__ = ("unet_ref", "source", "schema_version")

    def __init__(self, unet: Any, source: str, schema_version: int = 1) -> None:
        self.unet_ref = weakref.ref(unet)
        self.source = source
        self.schema_version = schema_version


def register_unet_forward_probe(unet: Any, source: str = "cpu_snapshot") -> None:
    """Register *unet* for forward-probe diagnostics and always-on
    first-CUDA timing.  Also installs the authoritative SAMPLER_SAMPLE
    timing wrapper via ``ensure_sampling_timing_wrapper``.

    *unet* may be a ``ModelPatcher``, ``LoadedModel``, or raw diffusion
    model — resolved via ``resolve_diffusion_model``.

    Idempotent: duplicate registrations for the same diffusion-model
    object are silently ignored.

    Must be called after the UNET's diffusion_model is populated and
    before ``load_models_gpu`` / ``NextDiT.forward``.

    Always active (not gated by COMFYMODAL_V2_UNET_FORWARD_DIAG).

    After registration, automatically installs forward pre-hooks on the
    diffusion model so ``_forward_pre_hook`` fires on the first forward.
    """
    patcher, dm = resolve_diffusion_model(unet)
    if dm is None:
        return
    dm_id = id(dm)
    with _registry_lock:
        if dm_id in _registry:
            return  # duplicate
        _registry[dm_id] = _ProbeEntry(unet, source)
    # Auto-clean when the diffusion_model is garbage collected.
    weakref.finalize(dm, _cleanup_registry_entry, dm_id)

    # Install SAMPLER_SAMPLE timing wrapper on the model patcher (Fix 4).
    if patcher is not None:
        from comfymodal_runtime.runtime_executor import ensure_sampling_timing_wrapper
        ensure_sampling_timing_wrapper(patcher)

    # Install forward pre-hook and post-hook on this specific diffusion model.
    # This ensures the hooks are in place before load_models_gpu or forward.
    try:
        import torch
        # Skip NextDiT (handled by install_nextdit_forward_pre_hook)
        if "NextDiT" in type(dm).__name__:
            return
        pre_handle = dm.register_forward_pre_hook(_forward_pre_hook, with_kwargs=True)
        _installed_hook_handles.append(pre_handle)
        global _unet_forward_hooks_installed
        _unet_forward_hooks_installed = True
        # The forward post-hook is OPTIONAL: lightweight objects (probe
        # stubs, minimal probes) may not implement ``register_forward_hook``.
        # A missing or failing post-hook must never roll back the
        # already-installed pre-hook or raise a hook_install_failed path.
        # Production torch modules implement both hooks.
        try:
            _post_register = getattr(dm, "register_forward_hook", None)
            if callable(_post_register):
                _installed_hook_handles.append(_post_register(_forward_post_hook))
        except Exception:
            pass
    except Exception as _hook_exc:
        print(f"[unet_probe] hook_install_failed dm_type={type(dm).__name__} "
              f"error={str(_hook_exc)[:120]}", flush=True)


def _cleanup_registry_entry(dm_id: int) -> None:
    with _registry_lock:
        _registry.pop(dm_id, None)


def _lookup_entry(dm: Any) -> tuple[Any, str, int] | None:
    """Return ``(unet, source, schema_version)`` for *dm* or ``None``."""
    dm_id = id(dm)
    with _registry_lock:
        entry = _registry.get(dm_id)
    if entry is None:
        return None
    unet = entry.unet_ref()
    if unet is None:
        with _registry_lock:
            _registry.pop(dm_id, None)
        return None
    return unet, entry.source, entry.schema_version


def _has_registered_unet_in_models(models: list[Any]) -> bool:
    """Check if any model in *models* has a registered diffusion_model.

    Always-on helper for the load_models_gpu wrapper.
    Uses ``resolve_diffusion_model`` for uniform resolution.
    """
    for model in models:
        _, dm = resolve_diffusion_model(model)
        if dm is not None and _lookup_entry(dm) is not None:
            return True
    return False


# ── Forward pre-hook ─────────────────────────────────────────────────────────
_nextdit_hook_installed: bool = False
# Track whether PyTorch forward pre-hooks have been installed on registered
# diffusion models (non-NextDiT UNET architectures).
_unet_forward_hooks_installed: bool = False
# Store installed hook handles for cleanup
_installed_hook_handles: list[Any] = []

# Bounded dedup: ``(request_id, str(dm_id)) -> True``.
_dedup: dict[tuple[str, str], bool] = {}
_dedup_lock = threading.RLock()
_DEDUP_MAX = 1024

# Bounded dedup for unet_first_cuda_op (one emit per request).
# Dict preserves insertion order so the OLDEST request ids are evicted first
# when the bound is reached — the set can never grow without bound, even for
# requests that never pass through the request-start reset path
# (reset_first_cuda_dedup).  Membership checks and .clear() behave exactly as
# before (the reset path is the primary cleanup).
_first_cuda_dedup: dict[str, bool] = {}
_first_cuda_dedup_lock = threading.RLock()
_FIRST_CUDA_DEDUP_MAX = 1024
# ── Forward post hook registry ─────────────────────────────────────────────
# A single post-hook handle is stored so we can remove/replace it.
_forward_post_handle: Any = None


def _forward_post_hook(module: Any, args: tuple[Any, ...], output: Any) -> None:
    """Instance-level forward post-hook on diffusion model.

    Completes the first CUDA forward record: captures wall/thread/process/faults,
    GPU alloc/reserved before+after, and emits ``unet_first_cuda_forward_complete``.
    Only the first matching CUDA forward produces a record (one per request).
    Uses active diagnostics state['first_forward'] instead of module-global.
    """
    _ensure_context_vars()
    request_trace = _ACTIVE_REQUEST_TRACE.get() if _ACTIVE_REQUEST_TRACE is not None else None
    if request_trace is None:
        return
    request_id = request_trace.request_id
    with _first_cuda_dedup_lock:
        if request_id not in _first_cuda_dedup:
            return  # pre-hook didn't mark this request_id yet

    from .model_preload import _ACTIVATION_DIAGNOSTIC_STATE, _RESIDENCY_SAMPLER_CALLBACK
    _diag = _ACTIVATION_DIAGNOSTIC_STATE.get()
    if _diag is None:
        return
    _state = _diag.get("first_forward")
    if not isinstance(_state, dict) or not _state.get("enter_monotonic_ns"):
        return

    # Compute post-forward deltas
    end_wall_ns = time.monotonic_ns()
    end_thread_ns = time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0
    end_process_ns = time.process_time_ns() if hasattr(time, "process_time_ns") else 0
    end_minor_faults = 0
    end_major_faults = 0
    try:
        import resource as _r
        _end_ru = _r.getrusage(_r.RUSAGE_SELF)
        end_minor_faults = _end_ru.ru_minflt
        end_major_faults = _end_ru.ru_majflt
    except Exception:
        pass

    begin_wall = _state["enter_monotonic_ns"]
    begin_thread = _state.get("thread_enter_ns", 0) or 0
    begin_process = _state.get("process_enter_ns", 0) or 0
    faults_before = _state.get("faults_before") or {}
    begin_minor = faults_before.get("minor_faults", 0) or 0
    begin_major = faults_before.get("major_faults", 0) or 0

    wall_ms = round((end_wall_ns - begin_wall) / 1_000_000, 3)
    thread_ms = round((end_thread_ns - begin_thread) / 1_000_000, 3)
    process_ms = round((end_process_ns - begin_process) / 1_000_000, 3)
    minor_faults = max(0, end_minor_faults - begin_minor)
    major_faults = max(0, end_major_faults - begin_major)

    try:
        from .model_preload import record_activation_receipt
        record_activation_receipt(
            "unet_forward",
            status="completed",
            role="UNET",
            started_ns=begin_wall,
            completed_ns=end_wall_ns,
            metadata={"wall_ms": wall_ms},
        )
    except Exception:
        pass

    # GPU alloc/reserved after
    _gpu_alloc_after = 0
    _gpu_reserved_after = 0
    try:
        import torch as _torch2
        if _torch2.cuda.is_available():
            _gpu_alloc_after = _torch2.cuda.memory_allocated()
            _gpu_reserved_after = _torch2.cuda.memory_reserved()
    except Exception:
        pass

    metadata: dict[str, Any] = {
        "wall_ms": wall_ms,
        "thread_cpu_ms": thread_ms,
        "process_cpu_ms": process_ms,
        "minor_faults": minor_faults,
        "major_faults": major_faults,
        "gpu_allocated_before": _state.get("gpu_allocated_before"),
        "gpu_reserved_before": _state.get("gpu_reserved_before"),
        "gpu_allocated_after": _gpu_alloc_after,
        "gpu_reserved_after": _gpu_reserved_after,
        "x_device": _state.get("x_device", ""),
        "x_dtype": _state.get("x_dtype", ""),
        "enter_monotonic_ns": begin_wall,
        "exit_monotonic_ns": end_wall_ns,
    }
    request_trace.emit(
        "unet_first_cuda_forward_complete", phase="execution", metadata=metadata
    )

    # Finalize first_forward in activation diagnostics
    _diag["first_forward"] = dict(metadata)

    # ── Residency sampler: first_unet_forward ──
    _res_cb = _RESIDENCY_SAMPLER_CALLBACK.get()
    if _res_cb is not None:
        try:
            _res_cb("first_unet_forward", request_trace)
        except Exception:
            pass


def _forward_pre_hook(module: Any, args: tuple[Any, ...], kwargs: dict[str, Any] | None = None) -> None:
    """Instance-level forward pre-hook on diffusion model.

    Always-on behavior (not gated by ``_ENABLED``):
      - Emits ``unet_first_cuda_op`` once per request with elapsed-from-demand
        timing when the input is on a CUDA device.

    Diagnostic-only (gated by ``_ENABLED``):
      - Emits ``unet_forward_probe`` with full model state metadata.

    Returns ``None`` and never modifies inputs.  Works for any registered
    diffusion model (not just NextDiT) when installed via
    ``nn.Module.register_forward_pre_hook``.
    """
    _ensure_context_vars()

    request_trace = _ACTIVE_REQUEST_TRACE.get() if _ACTIVE_REQUEST_TRACE is not None else None
    if request_trace is None:
        return None

    entry = _lookup_entry(module)
    if entry is None:
        return None
    unet, source, schema_version = entry

    request_id = request_trace.request_id
    dm_id = str(id(module))

    # Primary input tensor (1st positional arg) - used by both always-on and diagnostic paths.
    x = args[0] if args else None

    # ── Always-on: unet_first_cuda_op once per request ─────────────────
    # Only consumes the dedup slot when the input is CUDA, so a non-CUDA
    # first forward does NOT consume the dedup (CPU pre must not consume).
    _first_cuda_emitted = False
    with _first_cuda_dedup_lock:
        if request_id not in _first_cuda_dedup:
            x_device = str(x.device) if x is not None else ""
            if x_device.startswith("cuda"):
                _first_cuda_dedup[request_id] = True
                # Bounded: evict the oldest request ids when the bound is hit
                # so this per-request/global structure never grows without
                # bound (primary cleanup remains reset_first_cuda_dedup).
                if len(_first_cuda_dedup) > _FIRST_CUDA_DEDUP_MAX:
                    excess = len(_first_cuda_dedup) - _FIRST_CUDA_DEDUP_MAX
                    for _stale in list(_first_cuda_dedup.keys())[:excess]:
                        del _first_cuda_dedup[_stale]
                _first_cuda_emitted = True

                # Compute elapsed from demand start.
                demand_ns = _get_demand_start_ns(request_id)
                demand_present = 1 if demand_ns is not None else 0
                if demand_ns is not None:
                    elapsed_ns = time.monotonic_ns() - demand_ns
                    elapsed_ms = round(elapsed_ns / 1_000_000, 3)
                else:
                    elapsed_ms = "absent"

                # Capture begin timestamps for post-hook completion, store in activation diagnostics
                _first_forward_state = {
                    "enter_monotonic_ns": time.monotonic_ns(),
                    "thread_enter_ns": time.thread_time_ns() if hasattr(time, "thread_time_ns") else 0,
                    "process_enter_ns": time.process_time_ns() if hasattr(time, "process_time_ns") else 0,
                    "faults_before": {"minor_faults": 0, "major_faults": 0},
                    "request_id": request_id,
                    "x_device": x_device,
                    "x_dtype": str(x.dtype) if x is not None else "",
                    "demand_elapsed_ms": elapsed_ms,
                    "gpu_allocated_before": None,
                    "gpu_reserved_before": None,
                }
                try:
                    import resource as _r
                    _start_ru = _r.getrusage(_r.RUSAGE_SELF)
                    _first_forward_state["faults_before"] = {
                        "minor_faults": _start_ru.ru_minflt,
                        "major_faults": _start_ru.ru_majflt,
                    }
                except Exception:
                    pass
                try:
                    import torch as _torch
                    if _torch.cuda.is_available():
                        _first_forward_state["gpu_allocated_before"] = int(_torch.cuda.memory_allocated())
                        _first_forward_state["gpu_reserved_before"] = int(_torch.cuda.memory_reserved())
                except Exception:
                    pass
                # Store in activation diagnostics state['first_forward'] instead of module-global
                from .model_preload import _ACTIVATION_DIAGNOSTIC_STATE
                _ad_state = _ACTIVATION_DIAGNOSTIC_STATE.get()
                if _ad_state is not None:
                    _ad_state["first_forward"] = dict(_first_forward_state)

                metadata: dict[str, Any] = {
                    "event_semantics": "first_unet_forward_with_cuda_input",
                    "demand_start_present": demand_present,
                    "elapsed_ms": elapsed_ms,
                    "x_device": x_device,
                    "x_dtype": str(x.dtype) if x is not None else "",
                    "diffusion_model_object_id": dm_id,
                    "patcher_object_id": str(id(unet)),
                    "model_object_id": str(id(getattr(unet, "model", None))),
                    "model_identity": source,
                }
                request_trace.emit("unet_first_cuda_op", metadata=metadata)

                # ── Authoritative first-UNET-forward boundary ──
                # Marks the one-shot stall watchdog (no-op when unarmed) and
                # emits a one-line diagnostic.  No tensor contents.
                try:
                    from comfymodal_runtime.model_preload import mark_first_unet_forward
                    mark_first_unet_forward(request_id)
                except Exception:
                    pass
                print(
                    f"[v2.unet_forward_boundary] event=first_unet_forward "
                    f"request_id={request_id} "
                    f"diffusion_model_object_id={dm_id} "
                    f"patcher_object_id={str(id(unet))} "
                    f"model_object_id={str(id(getattr(unet, 'model', None)))} "
                    f"x_device={x_device} "
                    f"x_dtype={str(x.dtype) if x is not None else ''} "
                    f"elapsed_ms={elapsed_ms}",
                    flush=True,
                )
                try:
                    _parity_model = getattr(unet, "model", None)
                    _parity_weight_dtype = None
                    _parity_model_dtype = getattr(unet, "model_dtype", None)
                    if callable(_parity_model_dtype):
                        try:
                            _parity_weight_dtype = _parity_model_dtype()
                        except Exception:
                            _parity_weight_dtype = None
                    if _parity_weight_dtype is None:
                        try:
                            _parity_parameter = next(module.parameters(), None)
                            _parity_weight_dtype = getattr(_parity_parameter, "dtype", None)
                        except Exception:
                            _parity_weight_dtype = None
                    _parity_manual_cast = getattr(_parity_model, "manual_cast_dtype", None)
                    _parity_cache_config = getattr(module, "_cache_dit_config", None)
                    _parity_original_forward = getattr(module, "_original_forward", None)
                    _parity_active_forward = getattr(module, "forward", None)
                    _parity_attached = (
                        isinstance(_parity_cache_config, dict)
                        and _parity_original_forward is not None
                        and _parity_active_forward is not _parity_original_forward
                    )
                    print(
                        f"[v2.sampler_parity] "
                        f"UNET weight_dtype={_parity_weight_dtype} "
                        f"UNET compute_dtype={str(x.dtype) if x is not None else 'unknown'} "
                        f"manual_cast_dtype={_parity_manual_cast if _parity_manual_cast is not None else 'None'} "
                        f"CacheDiT target={type(module).__name__} "
                        f"CacheDiT attachment_count={1 if _parity_attached else 0} "
                        f"CacheDiT fallback={0 if _parity_attached else 1}",
                        flush=True,
                    )
                except Exception:
                    print(
                        f"[v2.sampler_parity] "
                        f"UNET weight_dtype=unknown "
                        f"UNET compute_dtype={str(x.dtype) if x is not None else 'unknown'} "
                        f"manual_cast_dtype=unknown "
                        f"CacheDiT target={type(module).__name__} "
                        f"CacheDiT attachment_count=0 CacheDiT fallback=1",
                        flush=True,
                    )

                # Clean up demand start storage (no longer needed for this request)
                _clear_demand_start_ns(request_id)

    # CPU input: do NOT consume the dedup slot.  Return None so forward proceeds.
    # The CUDA-capable forward will consume the slot later if it arrives.
    if _first_cuda_emitted is False:
        return None

    # ── Diagnostic-only: unet_forward_probe (gated by COMFYMODAL_V2_UNET_FORWARD_DIAG) ────────
    if not _is_enabled():
        return None

    # Dedup: once per (request_id, dm_id).
    dedup_key = (request_id, dm_id)
    with _dedup_lock:
        if dedup_key in _dedup:
            return None
        _dedup[dedup_key] = True
        if len(_dedup) > _DEDUP_MAX:
            excess = len(_dedup) - _DEDUP_MAX
            for k in list(_dedup.keys())[:excess]:
                del _dedup[k]

    try:
        state = collect_unet_forward_probe_state(unet, diffusion_model=module)
    except Exception as _state_exc:
        # Observer failure must never break inference: report and continue
        # with an empty diagnostic state.
        print(f"[unet_probe] diagnostic state collection failed: "
              f"{type(_state_exc).__name__}: {str(_state_exc)[:120]}", flush=True)
        state = {}

    diag_metadata: dict[str, Any] = {
        "schema_version": schema_version,
        "source": source,
        "request_id": request_id,
        "stage": "first_nextdit_forward" if "NextDiT" in type(module).__name__ else "first_unet_forward",
        "diffusion_model_object_id": dm_id,
        "patcher_object_id": str(id(unet)),
        "model_object_id": str(id(getattr(unet, "model", None))),
        "x_shape": list(x.shape) if x is not None else [],
        "x_device": str(x.device) if x is not None else "",
        "x_dtype": str(x.dtype) if x is not None else "",
    }
    diag_metadata.update(state)

    request_trace.emit("unet_forward_probe", metadata=diag_metadata)
    return None


def install_nextdit_forward_pre_hook() -> bool:
    """Install the ``NextDiT.forward`` pre-hook once (idempotent).

    Always installed (not gated by ``_ENABLED``) so first-CUDA timing works.
    Returns ``True`` if installed or already installed, ``False`` if
    ``NextDiT`` is unavailable.
    """
    import functools

    global _nextdit_hook_installed
    if _nextdit_hook_installed:
        return True
    try:
        from comfy.ldm.lumina.model import NextDiT  # type: ignore[import-untyped]
        _orig_forward = NextDiT.forward

        @functools.wraps(_orig_forward)
        def _patched_forward(self, *args: object, **kwargs: object) -> object:
            # The probe is an observer: a probe failure must never break
            # inference, so report it and always call the original forward.
            try:
                _forward_pre_hook(self, args)
            except Exception as _probe_exc:
                print(f"[unet_probe] nextdit pre-hook error: "
                      f"{type(_probe_exc).__name__}: {str(_probe_exc)[:120]}", flush=True)
            return _orig_forward(self, *args, **kwargs)

        NextDiT.forward = _patched_forward
        _nextdit_hook_installed = True
        return True
    except (ImportError, AttributeError):
        return False


def install_registered_unet_forward_hooks() -> int:
    """Install PyTorch ``register_forward_pre_hook`` on all currently
    registered UNET diffusion models.

    Always installed (not gated by ``_ENABLED``) so first-CUDA timing works.
    This covers non-NextDiT UNET architectures (e.g. Flux, SD3, SDXL, SD1.5).

    Returns the number of hooks installed.
    """
    import torch
    global _unet_forward_hooks_installed
    _count = 0
    with _registry_lock:
        for dm_id, entry in list(_registry.items()):
            unet = entry.unet_ref()
            if unet is None:
                continue
            model = getattr(unet, "model", None)
            if model is None:
                continue
            dm = getattr(model, "diffusion_model", None)
            if dm is None:
                continue
            if id(dm) != dm_id:
                continue
            # Skip NextDiT (handled by install_nextdit_forward_pre_hook)
            if "NextDiT" in type(dm).__name__:
                continue
            try:
                handle = dm.register_forward_pre_hook(_forward_pre_hook, with_kwargs=True)
                _installed_hook_handles.append(handle)
                _count += 1
            except Exception:
                pass
    if _count > 0:
        _unet_forward_hooks_installed = True
    return _count


def reset_first_cuda_dedup() -> None:
    """Clear the per-request dedup for ``unet_first_cuda_op``.

    Must be called at the start of each new request so the next forward
    pass emits ``unet_first_cuda_op`` again.
    """
    global _first_cuda_dedup
    _first_cuda_dedup.clear()


# ── post_load_models_gpu event (diagnostic-only) ────────────────────────────

def emit_post_load_models_gpu_event(models: list[Any]) -> None:
    """Emit ``unet_forward_probe`` / ``post_load_models_gpu`` for registered UNETs.

    Called from the GPU loader outer wrapper after ``original()`` succeeds
    (outermost reentrancy level only).  Iterates the ``models`` list and
    emits one event per registered (matched) diffusion model.

    Gated by COMFYMODAL_V2_UNET_FORWARD_DIAG=1 (diagnostic-only).
    """
    if not _is_enabled():
        return
    _ensure_context_vars()

    request_trace = _ACTIVE_REQUEST_TRACE.get() if _ACTIVE_REQUEST_TRACE is not None else None
    if request_trace is None:
        return

    request_id = request_trace.request_id

    gpu_call_index = 0
    if _GPU_REQUEST_CALL_COUNT_VAR is not None:
        gpu_call_index = _GPU_REQUEST_CALL_COUNT_VAR.get()

    # Determine caller classification.
    caller = "not_observed"
    lane_trace = _ACTIVE_LANE_TRACE.get() if _ACTIVE_LANE_TRACE is not None else None
    if lane_trace is not None:
        lane_name = getattr(lane_trace, "_lane", "")
        if lane_name:
            caller = f"background_{lane_name.lower()}_preparation"
    elif request_trace is not None:
        caller = "graph_model_loading"

    for model in models:
        patcher, dm = resolve_diffusion_model(model)
        if dm is None:
            continue

        entry = _lookup_entry(dm)
        if entry is None:
            continue
        unet, source, schema_version = entry

        try:
            state = collect_unet_forward_probe_state(unet, diffusion_model=dm)
        except Exception as _state_exc:
            # Observer failure must never break the GPU loader: report and
            # continue with an empty diagnostic state.
            print(f"[unet_probe] diagnostic state collection failed: "
                  f"{type(_state_exc).__name__}: {str(_state_exc)[:120]}", flush=True)
            state = {}

        m = getattr(patcher, "model", None) if patcher is not None else None
        metadata: dict[str, Any] = {
            "schema_version": schema_version,
            "source": source,
            "request_id": request_id,
            "stage": "post_load_models_gpu",
            "gpu_call_index": gpu_call_index,
            "caller_classification": caller,
            "diffusion_model_object_id": str(id(dm)),
            "patcher_object_id": str(id(patcher)) if patcher is not None else str(id(unet)),
            "model_object_id": str(id(m)) if m is not None else "",
        }
        metadata.update(state)

        request_trace.emit("unet_forward_probe", metadata=metadata)
