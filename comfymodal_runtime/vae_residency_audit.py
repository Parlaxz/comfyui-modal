"""Audit-only VAE residency probe for the Golden VAE load/decode pair.

WHY THIS EXISTS
---------------
The P9 optimization pass left one unexplained cost on the post-sampling
critical path.  Inside ``VAE.decode`` (``comfy/sd.py:1220``) upstream ComfyUI
calls ``model_management.load_models_gpu([self.patcher], ...)``, and in the
P9 traces that call measured 73.0 ms (GOOD fastest) / 78.1 ms (GOOD healthy)
/ 110.7 ms (BAD), with ``ModelPatcherDynamic.partially_load`` nested *inside*
it at 65.5 / 69.5 / 100.1 ms.  The open question is whether that work repeats
what ``golden_vae_load`` already did, or whether it is the first and only
DynamicVRAM activation of the VAE patcher.

The static audit answered the mechanism; what it could not answer from the
committed artifacts is the *measured* residency state at each boundary.  This
module supplies that measurement without changing any behaviour.

CONTRACT
--------
* Default OFF.  Nothing runs, nothing is imported, nothing is recorded unless
  ``COMFYMODAL_VAE_RESIDENCY_AUDIT`` is truthy ("1"/"true"/"yes"/"on").
* Strictly read-only.  Every value is read through an existing ComfyUI or
  ``ModelPatcherDynamic`` accessor (``model_size``, ``loaded_size``,
  ``model_loaded_weight_memory``, ``dynamic_pins``, ``model_management.
  current_loaded_models``, ``torch.cuda`` counters).  It never calls
  ``load``, ``partially_load``, ``partially_unload``, ``load_models_gpu``,
  ``free_memory``, ``detach``, ``unpatch_model``, ``empty_cache`` or any
  ``setattr`` on a model, module or patcher.
* ``torch``, ``comfy.*`` and ``comfy_aimdo`` are imported lazily inside the
  probe, so this module is import-safe with none of them present.  That is what
  makes it unit-testable on a developer machine.
* ``record()`` never raises.  Telemetry must not be able to fail a request.

This module is diagnostics only.  It does not bypass, reorder, cache or
short-circuit ``load_models_gpu``, ``partially_load`` or DynamicVRAM, and it is
not on any correctness path.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Optional

GATE_ENV = "COMFYMODAL_VAE_RESIDENCY_AUDIT"

EVENT_NAME = "vae_residency_audit"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def enabled(env: Optional[dict] = None) -> bool:
    """Return True only when the audit gate is explicitly truthy.

    Absent or unrecognised values are False.  This is the single place the gate
    is decided so a test can pin the default-OFF behaviour.
    """
    source = os.environ if env is None else env
    raw = source.get(GATE_ENV)
    if raw is None:
        return False
    return str(raw).strip().lower() in _TRUTHY


def _safe(fn: Callable[[], Any], default: Any = None) -> Any:
    """Call a read-only accessor, swallowing any failure.

    Probes run inside a live request against pinned ComfyUI internals whose
    exact shape varies by patcher class.  A probe that cannot read a field must
    report "unknown", never perturb the request.
    """
    try:
        return fn()
    except BaseException:  # noqa: BLE001 - diagnostics must never fail a request
        return default


def _param_residency(module: Any, target_device: str) -> dict:
    """Summarise where a module's parameters actually live, in bytes."""
    summary = {
        "param_count": 0,
        "param_bytes_total": 0,
        "param_bytes_on_target_device": 0,
        "param_bytes_on_cpu": 0,
        "param_bytes_other_device": 0,
        "target_device": target_device,
    }
    if module is None:
        return summary
    try:
        params = list(module.parameters())
    except BaseException:  # noqa: BLE001
        return summary
    summary["param_count"] = len(params)
    for tensor in params:
        try:
            nbytes = int(tensor.numel()) * int(tensor.element_size())
            dev = str(tensor.device)
        except BaseException:  # noqa: BLE001
            continue
        summary["param_bytes_total"] += nbytes
        if dev == summary["target_device"]:
            summary["param_bytes_on_target_device"] += nbytes
        elif dev == "cpu":
            summary["param_bytes_on_cpu"] += nbytes
        else:
            summary["param_bytes_other_device"] += nbytes
    return summary


def _pin_state(patcher: Any) -> dict:
    """Read the per-load-device AIMDO DynamicVRAM pin state verbatim.

    ``hostbufs_initialized`` and ``active`` are the two flags that distinguish
    "this patcher has never been dynamically loaded" from "it has".  They are
    the smallest existing state that proves whether ``partially_load`` at decode
    is first-time activation or a repeat.
    """
    out: dict[str, Any] = {"devices": {}}
    pins = _safe(lambda: getattr(patcher.model, "dynamic_pins", None))
    if not isinstance(pins, dict):
        return out
    for device, state in pins.items():
        if not isinstance(state, dict):
            continue
        entry: dict[str, Any] = {}
        for key in (
            "hostbufs_initialized",
            "active",
            "failed",
            "current_prompt",
        ):
            entry[key] = state.get(key)
        for key in ("weights", "weights-loaded"):
            # The tuple shape is ComfyUI-internal
            # ``(HostBuffer, offsets, [-1], [0], [0], {})``; only the buffer's
            # presence is readable here, and presence is exactly the fact that
            # distinguishes "never dynamically loaded" from "loaded".  Report no
            # byte count rather than guessing at one.
            buffer_tuple = state.get(key)
            entry[f"{key}_buffer_present"] = bool(
                isinstance(buffer_tuple, tuple) and buffer_tuple and buffer_tuple[0] is not None
            )
        out["devices"][str(device)] = entry
    return out


def _vbar_state(patcher: Any) -> dict:
    """Read the AIMDO virtual-bar staging state for the load device."""
    out: dict[str, Any] = {
        "vbar_present": False,
        "vbar_loaded_bytes": None,
        "vbar_capacity_bytes": None,
    }
    vbars = _safe(lambda: getattr(patcher.model, "dynamic_vbars", None))
    device = _safe(lambda: getattr(patcher, "load_device", None))
    if not isinstance(vbars, dict):
        return out
    vbar = vbars.get(device)
    if vbar is None:
        return out
    out["vbar_present"] = True
    out["vbar_loaded_bytes"] = _safe(lambda: int(vbar.loaded_size()))
    out["vbar_capacity_bytes"] = _safe(lambda: int(vbar.size))
    return out


def _module_markers(module: Any) -> dict:
    """Count the DynamicVRAM markers ``ModelPatcherDynamic.load`` installs.

    ``_v`` is the vbar block a module was staged into; ``weight_function`` /
    ``lowvram_function`` are installed by ``setup_param``/``move_weight_
    functions``.  All three are absent on a patcher that has never been loaded,
    which is what makes the pre-decode state unambiguous.
    """
    out = {
        "module_count": 0,
        "modules_with_vbar_block": 0,
        "modules_with_weight_function_attr": 0,
        "modules_with_lowvram_function_attr": 0,
    }
    if module is None:
        return out
    try:
        modules = list(module.modules())
    except BaseException:  # noqa: BLE001
        return out
    out["module_count"] = len(modules)
    for mod in modules:
        if hasattr(mod, "_v"):
            out["modules_with_vbar_block"] += 1
        if hasattr(mod, "weight_function"):
            out["modules_with_weight_function_attr"] += 1
        if hasattr(mod, "weight_lowvram_function"):
            out["modules_with_lowvram_function_attr"] += 1
    return out


def _registry_state(patcher: Any) -> dict:
    """Report whether model management already tracks this patcher.

    ``load_models_gpu`` inserts a ``LoadedModel`` at
    ``model_management.py:1026``.  Presence there is what makes a model part of
    memory accounting and eviction policy; its absence is the concrete
    consequence of skipping the decode-time load.
    """
    out = {"registry_checked": False, "registry_present": False, "registry_size": None}
    try:
        import comfy.model_management as model_management
    except BaseException:  # noqa: BLE001
        return out
    out["registry_checked"] = True
    loaded = _safe(lambda: list(model_management.current_loaded_models))
    if loaded is None:
        return out
    out["registry_size"] = len(loaded)
    for entry in loaded:
        if _safe(lambda e=entry: e.model) is patcher:
            out["registry_present"] = True
            break
    return out


def _cuda_state() -> dict:
    """Allocator counters, so a reader can see residency without inferring it."""
    out: dict[str, Any] = {}
    try:
        import torch
    except BaseException:  # noqa: BLE001
        return out
    if not _safe(lambda: bool(torch.cuda.is_available()), False):
        return out
    out["cuda_allocated_bytes"] = _safe(
        lambda: int(torch.cuda.memory_allocated())
    )
    out["cuda_reserved_bytes"] = _safe(lambda: int(torch.cuda.memory_reserved()))
    out["cuda_max_allocated_bytes"] = _safe(
        lambda: int(torch.cuda.max_memory_allocated())
    )
    return out


def probe(label: str, vae: Any) -> dict:
    """Return a read-only residency snapshot of *vae* at *label*.

    Every field is best-effort.  A field that cannot be read is ``None`` or
    absent rather than an exception, so a probe can never fail a request.
    """
    snapshot: dict[str, Any] = {
        "schema_version": 1,
        "label": str(label),
        "monotonic_ns": time.monotonic_ns(),
        "vae_object_id": str(id(vae)) if vae is not None else "",
        "vae_class": type(vae).__name__ if vae is not None else "",
    }
    patcher = _safe(lambda: getattr(vae, "patcher", None))
    if patcher is None:
        snapshot["patcher_present"] = False
        return snapshot
    snapshot["patcher_present"] = True
    snapshot["patcher_object_id"] = str(id(patcher))
    snapshot["patcher_class"] = type(patcher).__name__
    model = _safe(lambda: getattr(patcher, "model", None))
    snapshot["model_object_id"] = str(id(model)) if model is not None else ""
    snapshot["model_class"] = type(model).__name__ if model is not None else ""

    load_device = _safe(lambda: getattr(patcher, "load_device", None))
    snapshot["load_device"] = str(load_device) if load_device is not None else None
    snapshot["offload_device"] = str(
        _safe(lambda: getattr(patcher, "offload_device", None))
    )
    snapshot["is_dynamic"] = _safe(lambda: bool(patcher.is_dynamic()), None)
    snapshot["model_device_attr"] = str(
        _safe(lambda: getattr(model, "device", None))
    )
    snapshot["current_weight_patches_uuid"] = str(
        _safe(
            lambda: getattr(
                getattr(model, "current_weight_patches_uuid", None), "hex", lambda: None
            )()
        )
        or ""
    )

    # Residency accounting, in bytes, from the patcher's own API.
    snapshot["model_size_bytes"] = _safe(lambda: int(patcher.model_size()))
    snapshot["loaded_size_bytes"] = _safe(lambda: int(patcher.loaded_size()))
    snapshot["model_loaded_weight_memory"] = _safe(
        lambda: int(getattr(model, "model_loaded_weight_memory", 0))
    )
    snapshot["offloaded_size_bytes"] = _safe(
        lambda: int(patcher.model_size()) - int(patcher.loaded_size())
    )
    snapshot["backup_weight_count"] = len(
        _safe(lambda: getattr(patcher, "backup", None), {}) or {}
    )
    snapshot["backup_buffer_count"] = len(
        _safe(lambda: getattr(patcher, "backup_buffers", None), {}) or {}
    )

    first_stage = _safe(lambda: getattr(vae, "first_stage_model", None))
    snapshot["first_stage_params"] = _param_residency(
        first_stage, snapshot["load_device"] or ""
    )
    snapshot["module_markers"] = _module_markers(first_stage)
    snapshot["dynamic_pins"] = _pin_state(patcher)
    snapshot["aimdo"] = _vbar_state(patcher)
    snapshot["model_management"] = _registry_state(patcher)
    snapshot["cuda"] = _cuda_state()
    return snapshot


def record(recorder: Any, label: str, vae: Any) -> Optional[dict]:
    """Emit one probe onto *recorder* when the gate is on; else do nothing.

    Returns the snapshot when it was recorded, ``None`` when the gate is off or
    the emit failed.  Never raises: a diagnostics failure must not be able to
    fail, delay or alter the request being measured.
    """
    if not enabled():
        return None
    try:
        snapshot = probe(label, vae)
    except BaseException:  # noqa: BLE001
        return None
    try:
        if recorder is not None:
            recorder.event(EVENT_NAME, **snapshot)
    except BaseException:  # noqa: BLE001
        return snapshot
    return snapshot


__all__ = [
    "EVENT_NAME",
    "GATE_ENV",
    "enabled",
    "probe",
    "record",
]