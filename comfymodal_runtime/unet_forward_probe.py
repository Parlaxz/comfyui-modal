"""Diagnostic-only UNET forward probe: weak registry, GPU event, forward pre-hook.

Disabled by default.  Enable with ``COMFYMODAL_V2_UNET_FORWARD_DIAG=1``.

Provides:
  register_unet_forward_probe(unet, source)  -- registration at snapshot/normal-loader points
  install_nextdit_forward_pre_hook()          -- install NextDiT forward pre-hook (once)
  emit_post_load_models_gpu_event(models)     -- emit after outermost load_models_gpu success

Safety: read-only, no CUDA synchronize, no tensor mutation, no dtype/device transfer.
"""

from __future__ import annotations

import os
import weakref
from contextvars import ContextVar
from threading import RLock
from typing import Any

from .cpu_snapshot_models import collect_unet_forward_probe_state

# ── Diagnostic gate ──────────────────────────────────────────────────────────
# Disabled by default; set COMFYMODAL_V2_UNET_FORWARD_DIAG=1 to enable.
_ENABLED: bool = os.environ.get("COMFYMODAL_V2_UNET_FORWARD_DIAG", "") == "1"

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


# ── Weak registry ────────────────────────────────────────────────────────────
# Maps id(diffusion_model) -> _ProbeEntry.
# Entries auto-clean when the diffusion_model is garbage collected via finalizer.
_registry: dict[int, Any] = {}
_registry_lock = RLock()


class _ProbeEntry:
    """Weakly-held registration entry for a diffusion model."""
    __slots__ = ("unet_ref", "source", "schema_version")

    def __init__(self, unet: Any, source: str, schema_version: int = 1) -> None:
        self.unet_ref = weakref.ref(unet)
        self.source = source
        self.schema_version = schema_version


def register_unet_forward_probe(unet: Any, source: str = "cpu_snapshot") -> None:
    """Register *unet* (a ModelPatcher) for forward-probe diagnostics.

    Idempotent: duplicate registrations for the same diffusion-model
    object are silently ignored.

    Must be called after the UNET's diffusion_model is populated and
    before ``load_models_gpu`` / ``NextDiT.forward``.
    """
    if not _ENABLED:
        return
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


# ── Forward pre-hook ─────────────────────────────────────────────────────────
_nextdit_hook_installed: bool = False

# Bounded dedup: ``(request_id, str(dm_id)) -> True``.
_dedup: dict[tuple[str, str], bool] = {}
_dedup_lock = RLock()
_DEDUP_MAX = 1024


def _forward_pre_hook(module: Any, args: tuple[Any, ...]) -> None:
    """Instance-level forward pre-hook on NextDiT.

    Emits ``unet_forward_probe`` / ``first_nextdit_forward`` once per
    ``(request_id, diffusion_model_object_id)``.  Returns ``None`` and
    never modifies inputs.
    """
    if not _ENABLED:
        return None
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

    # Primary input tensor (1st positional arg).
    x = args[0] if args else None

    state = collect_unet_forward_probe_state(unet, diffusion_model=module)

    metadata: dict[str, Any] = {
        "schema_version": schema_version,
        "source": source,
        "request_id": request_id,
        "stage": "first_nextdit_forward",
        "diffusion_model_object_id": dm_id,
        "patcher_object_id": str(id(unet)),
        "model_object_id": str(id(getattr(unet, "model", None))),
        "x_shape": list(x.shape) if x is not None else [],
        "x_device": str(x.device) if x is not None else "",
        "x_dtype": str(x.dtype) if x is not None else "",
    }
    metadata.update(state)

    request_trace.emit("unet_forward_probe", metadata=metadata)
    return None


def install_nextdit_forward_pre_hook() -> bool:
    """Install the ``NextDiT.forward`` pre-hook once (idempotent).

    Patches ``NextDiT.forward`` at the class level so every instance
    runs the diagnostic pre-hook before its forward pass.  This is
    necessary because ``register_forward_pre_hook`` is an instance
    method on ``nn.Module`` and cannot be called on the class itself.

    Returns ``True`` if installed or already installed, ``False`` if
    ``NextDiT`` is unavailable or diagnostics are disabled.
    """
    import functools

    global _nextdit_hook_installed
    if _nextdit_hook_installed:
        return True
    if not _ENABLED:
        return False
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


# ── post_load_models_gpu event ───────────────────────────────────────────────

def emit_post_load_models_gpu_event(models: list[Any]) -> None:
    """Emit ``unet_forward_probe`` / ``post_load_models_gpu`` for registered UNETs.

    Called from the GPU loader outer wrapper after ``original()`` succeeds
    (outermost reentrancy level only).  Iterates the ``models`` list and
    emits one event per registered (matched) diffusion model.
    """
    if not _ENABLED:
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
