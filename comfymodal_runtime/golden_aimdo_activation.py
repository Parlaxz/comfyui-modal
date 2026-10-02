"""Official-equivalent DynamicVRAM activation for the isolated Golden P1 worker.

The Modal runtime imports ``comfyapp`` directly and NEVER executes upstream
``ComfyUI/main.py``, so the CLI ``--enable-dynamic-vram`` sequence never runs
in the Golden worker. This module reproduces that upstream sequence exactly,
as verified against the installed sources:

    main.py L42/L45:   import comfy_aimdo.control ; comfy_aimdo.control.init()
    main.py L221:      comfy_aimdo.control.init_devices(
                           d.index for d in
                           comfy.model_management.get_all_torch_devices())
    main.py L233:      comfy.model_patcher.CoreModelPatcher = \
                           comfy.model_patcher.ModelPatcherDynamic
    main.py L234:      comfy.memory_management.aimdo_enabled = True

Contract:
- Gated by env var ``COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM`` (truthy values:
  "1"/"true"/"yes"/"on", case-insensitive). When absent/falsy nothing is
  touched and a telemetry dict with ``reason="gate_not_set"`` is returned.
- Safe to call exactly once per process; a second call returns the first
  successful result with ``already_activated=True``. Ordering relative to
  Golden model construction is enforced by callers, not here.
- Fail closed: any import/init/verification problem raises ``RuntimeError``
  carrying the marker ``golden_aimdo_activation_failed:<reason>``. Nothing is
  restored or unwound (see caveats below).
- No project-local imports: stdlib only at module scope; upstream ``comfy.*``
  and ``comfy_aimdo`` are imported lazily inside the activation call.
- No logging side effects; the caller persists the returned telemetry dict.

Caveats / unavoidable residual state on failure:
- Once ``comfy_aimdo.control.init()`` runs, the native aimdo DLL stays loaded
  in the process; it cannot be unloaded.
- The alias rebind and the ``aimdo_enabled`` flag happen immediately before
  their respective verifications. If the ALIAS verification fails, the
  ``aimdo_enabled`` flag may already be True; if the FLAG verification fails,
  ``CoreModelPatcher`` is already rebound. Per the fail-closed contract these
  residuals are NOT restored -- a process hitting either marker must be
  treated as failed end-to-end.
"""

from __future__ import annotations

import os
import sys
import threading
import time

GATE_ENV_DEFAULT = "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM"
PROFILE_ENV = "COMFYMODAL_V2_ENV_PROFILE"

_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})
_FAILURE_MARKER = "golden_aimdo_activation_failed:"

_TELEMETRY_KEYS = (
    "activated",
    "already_activated",
    "gate_env",
    "pid",
    "profile",
    "aimdo_import_version_or_none",
    "init_devices_ok",
    "device_indices",
    "patcher_class_module",
    "patcher_class_name",
    "is_dynamic_alias",
    "aimdo_enabled",
    "activated_monotonic_ns",
    "reason",
)

_lock = threading.Lock()
# First successful activation result; reused (with already_activated=True) on
# subsequent calls. Never caches gate_not_set results or failures.
_success_result: dict | None = None
_early_init_done = False


def _base_telemetry(gate_env: str, gate_value: str | None) -> dict:
    """Uniform JSON-safe telemetry skeleton shared by every return path."""
    return {
        "activated": False,
        "already_activated": False,
        "gate_env": {"name": gate_env, "value": gate_value},
        "pid": os.getpid(),
        "profile": os.environ.get(PROFILE_ENV),
        "aimdo_import_version_or_none": None,
        "init_devices_ok": False,
        "device_indices": [],
        "patcher_class_module": None,
        "patcher_class_name": None,
        "is_dynamic_alias": False,
        "aimdo_enabled": False,
        "activated_monotonic_ns": None,
        "reason": None,
    }


def _fail(reason: str, telemetry: dict, cause: BaseException | None) -> RuntimeError:
    """Build the fail-closed error; attach telemetry for caller persistence."""
    err = RuntimeError(_FAILURE_MARKER + reason)
    err.golden_activation_telemetry = dict(telemetry)  # type: ignore[attr-defined]
    if cause is not None:
        err.__cause__ = cause
    return err


def _aimdo_version() -> str | None:
    module = sys.modules.get("comfy_aimdo")
    if module is None:
        try:
            import importlib

            module = importlib.import_module("comfy_aimdo")
        except Exception:
            return None
    version = getattr(module, "__version__", None)
    return version if isinstance(version, str) else None


def ensure_golden_aimdo_early_init(
    *, enabled_env: str = GATE_ENV_DEFAULT
) -> bool:
    """Initialize AIMDO before ComfyUI imports modules that capture its state.

    Upstream ``main.py`` performs ``comfy_aimdo.control.init()`` before
    importing ``comfy.model_management`` and ``comfy.model_patcher``.  The
    in-process Modal backend does not execute ``main.py``, so ``comfyapp`` calls
    this helper immediately before those imports.  The request-time activator
    also calls it as a safe fallback for direct/unit-test entry.
    """
    global _early_init_done
    gate_value = os.environ.get(enabled_env)
    if gate_value is None or gate_value.strip().lower() not in _TRUTHY_VALUES:
        return False
    with _lock:
        if _early_init_done:
            return True
        try:
            import comfy_aimdo.control as aimdo_control
        except Exception as exc:
            telemetry = _base_telemetry(enabled_env, gate_value)
            raise _fail("import_failed", telemetry, exc) from exc
        try:
            aimdo_control.init()
        except Exception as exc:
            telemetry = _base_telemetry(enabled_env, gate_value)
            raise _fail("aimdo_init_failed", telemetry, exc) from exc
        _early_init_done = True
        return True


def _activate(telemetry: dict) -> dict:
    """Run the upstream sequence. Raises fail-closed RuntimeErrors only."""
    # Lazy imports: upstream comfy + comfy_aimdo, never project-local modules.
    try:
        import comfy.memory_management as memory_management
        import comfy.model_management as model_management
        import comfy.model_patcher as model_patcher
        import comfy_aimdo.control as aimdo_control
    except Exception as exc:  # pragma: no cover - exercised via fakes in tests
        raise _fail("import_failed", telemetry, exc) from exc

    telemetry["aimdo_import_version_or_none"] = _aimdo_version()

    # Upstream main.py L221: init_devices over every torch device index.
    try:
        devices = list(model_management.get_all_torch_devices())
        device_indices = [int(d.index) for d in devices]
        init_devices_ok = bool(aimdo_control.init_devices(iter(device_indices)))
    except Exception as exc:
        raise _fail("init_devices_failed", telemetry, exc) from exc

    telemetry["init_devices_ok"] = init_devices_ok
    telemetry["device_indices"] = device_indices
    if not init_devices_ok:
        raise _fail("init_devices_failed", telemetry, None)

    dynamic_cls = model_patcher.ModelPatcherDynamic
    telemetry["patcher_class_module"] = getattr(dynamic_cls, "__module__", None)
    telemetry["patcher_class_name"] = getattr(dynamic_cls, "__name__", None)

    # Upstream main.py L233-234, then identity verification (fail closed).
    model_patcher.CoreModelPatcher = dynamic_cls
    memory_management.aimdo_enabled = True

    if model_patcher.CoreModelPatcher is not dynamic_cls:
        raise _fail("alias_rebind_verification_failed", telemetry, None)
    if memory_management.aimdo_enabled is not True:
        raise _fail("aimdo_flag_verification_failed", telemetry, None)

    telemetry["is_dynamic_alias"] = True
    telemetry["aimdo_enabled"] = True
    telemetry["activated_monotonic_ns"] = time.monotonic_ns()
    telemetry["activated"] = True
    return telemetry


def activate_golden_dynamic_vram(
    *, enabled_env: str = GATE_ENV_DEFAULT
) -> dict:
    """Activate official-equivalent DynamicVRAM for the Golden P1 worker.

    Returns a JSON-safe telemetry dict with exactly the keys in
    ``_TELEMETRY_KEYS``. On failure paths raises ``RuntimeError`` with marker
    ``golden_aimdo_activation_failed:<reason>`` and the telemetry dict
    attached as ``golden_activation_telemetry``.
    """
    global _success_result

    gate_value = os.environ.get(enabled_env)
    telemetry = _base_telemetry(enabled_env, gate_value)

    if gate_value is None or gate_value.strip().lower() not in _TRUTHY_VALUES:
        telemetry["reason"] = "gate_not_set"
        return telemetry

    # Initialize AIMDO before entering the success-cache section: the helper
    # acquires _lock itself, so calling it while holding _lock would deadlock.
    ensure_golden_aimdo_early_init(enabled_env=enabled_env)

    with _lock:
        if _success_result is not None:
            repeat = dict(_success_result)
            repeat["already_activated"] = True
            return repeat
        try:
            result = _activate(telemetry)
        except RuntimeError:
            raise
        except Exception as exc:  # defensive: never leak foreign exception types
            raise _fail("unexpected_error", telemetry, exc) from exc
        _success_result = dict(result)
        return result


__all__ = [
    "activate_golden_dynamic_vram",
    "ensure_golden_aimdo_early_init",
]
