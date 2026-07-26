"""UNET forward probe: weak registry, always-on first-CUDA timing, optional diagnostics.

Always-on (lightweight):
  - ``register_unet_forward_probe(unet, source)`` -- register at snapshot/normal-loader
  - ``install_nextdit_forward_pre_hook()`` / ``install_registered_unet_forward_hooks()``
  - ``set_unet_gpu_demand_start(request_id, monotonic_ns)`` -- called by load_models_gpu wrapper
  - ``reset_first_cuda_dedup()`` -- called at start of each request
  - First forward with CUDA input emits ``unet_first_cuda_op`` with real elapsed

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
from contextvars import ContextVar
from typing import Any

from .cpu_snapshot_models import collect_unet_forward_probe_state

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
    return os.environ.get(_DIAG_ENV_KEY, "") == "1"

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


def set_unet_gpu_demand_start(request_id: str, monotonic_ns: int) -> None:
    """Record demand start for UNET GPU first forward timing.

    Called from the outermost ``load_models_gpu`` wrapper when the model
    list contains a registered UNET.  Thread-safe.
    """
    with _unet_gpu_demand_lock:
        # Only record the *first* demand start per request.
        if request_id not in _unet_gpu_demand_start:
            _unet_gpu_demand_start[request_id] = monotonic_ns


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
    """Register *unet* (a ModelPatcher) for forward-probe diagnostics
    and always-on first-CUDA timing.

    Idempotent: duplicate registrations for the same diffusion-model
    object are silently ignored.

    Must be called after the UNET's diffusion_model is populated and
    before ``load_models_gpu`` / ``NextDiT.forward``.

    Always active (not gated by COMFYMODAL_V2_UNET_FORWARD_DIAG).

    After registration, automatically installs forward pre-hooks on the
    diffusion model so ``_forward_pre_hook`` fires on the first forward.
    """
    model = getattr(unet, "model", None)
    if model is None:
        return
    dm = getattr(model, "diffusion_model", None)
    if dm is None:
        dm = getattr(unet, "diffusion_model", None)
    if dm is None:
        return
    dm_id = id(dm)
    with _registry_lock:
        if dm_id in _registry:
            return  # duplicate
        _registry[dm_id] = _ProbeEntry(unet, source)
    # Auto-clean when the diffusion_model is garbage collected.
    weakref.finalize(dm, _cleanup_registry_entry, dm_id)
    # Install forward pre-hook on this specific diffusion model immediately.
    # This ensures the hook is in place before load_models_gpu or forward.
    try:
        import torch
        # Skip NextDiT (handled by install_nextdit_forward_pre_hook)
        if "NextDiT" in type(dm).__name__:
            return
        handle = dm.register_forward_pre_hook(_forward_pre_hook, with_kwargs=True)
        _installed_hook_handles.append(handle)
        global _unet_forward_hooks_installed
        _unet_forward_hooks_installed = True
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
    """
    for model in models:
        m = getattr(model, "model", None)
        if m is None:
            dm = getattr(model, "diffusion_model", None)
        else:
            dm = getattr(m, "diffusion_model", None)
            if dm is None:
                dm = getattr(model, "diffusion_model", None)
        if dm is None:
            continue
        if _lookup_entry(dm) is not None:
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

# Separate dedup for unet_first_cuda_op (one per request)
_first_cuda_dedup: set[str] = set()
_first_cuda_dedup_lock = threading.RLock()


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
    # first forward does not prevent a later CUDA forward from emitting.
    _first_cuda_emitted = False
    with _first_cuda_dedup_lock:
        if request_id not in _first_cuda_dedup:
            x_device = str(x.device) if x is not None else ""
            if x_device.startswith("cuda"):
                _first_cuda_dedup.add(request_id)
                _first_cuda_emitted = True

                # Compute elapsed from demand start.
                demand_ns = _get_demand_start_ns(request_id)
                demand_present = 1 if demand_ns is not None else 0
                if demand_ns is not None:
                    elapsed_ns = time.monotonic_ns() - demand_ns
                    elapsed_ms = round(elapsed_ns / 1_000_000, 3)
                else:
                    elapsed_ms = "absent"

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

                # Clean up demand start storage (no longer needed for this request)
                _clear_demand_start_ns(request_id)

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

    state = collect_unet_forward_probe_state(unet, diffusion_model=module)

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
            _forward_pre_hook(self, args)
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
        m = getattr(model, "model", None)
        if m is None:
            dm = getattr(model, "diffusion_model", None)
        else:
            dm = getattr(m, "diffusion_model", None)
            if dm is None:
                dm = getattr(model, "diffusion_model", None)
        if dm is None:
            continue

        entry = _lookup_entry(dm)
        if entry is None:
            continue
        unet, source, schema_version = entry

        state = collect_unet_forward_probe_state(unet, diffusion_model=dm)

        metadata: dict[str, Any] = {
            "schema_version": schema_version,
            "source": source,
            "request_id": request_id,
            "stage": "post_load_models_gpu",
            "gpu_call_index": gpu_call_index,
            "caller_classification": caller,
            "diffusion_model_object_id": str(id(dm)),
            "patcher_object_id": str(id(unet)),
            "model_object_id": str(id(m)),
        }
        metadata.update(state)

        request_trace.emit("unet_forward_probe", metadata=metadata)
