"""Post-snapshot GPU capability repair coordinator (Part A4).

Snapshot capture happens while ComfyUI is forced into CPU mode, so any
capability decision evaluated at import/snapshot time observes
``torch.cuda.is_available() == False`` and that dead state is baked into the
serving container.  This module re-runs the *state-only* re-registration
steps with real CUDA visible.  It performs no math, touches no weights,
allocates nothing, synchronizes nothing, and spawns no background retries:
each public entry runs one bounded pass and reports a structured outcome.

Outcomes (per provider and overall):
  complete       -- terminal success (including policy-preserved skips).
  not-applicable -- terminal no-op (nothing to repair on this device/build).
  deferred       -- not done yet; a later boundary may retry (CUDA invisible,
                    CPU-state, backend genuinely unavailable, ...).  Deferred
                    never consumes the once-guard.
  error          -- an unexpected exception escaped the provider; reported in
                    ``reason``, never swallowed, never raised.

Providers (fixed ordered tuple ``_PROVIDERS``):
  _repair_kitchen_gpu_backends          -- relocated here from
      ``ideogram_cuda_profile.repair_kitchen_gpu_backends_after_restore``
      (single implementation; the old location keeps a thin delegating
      wrapper for compat).  Fixes the known bug where an
      intentionally-disabled backend reran registration and then failed the
      post-registration availability check forever: disabled backends are now
      skipped up front and count as terminal policy-preserved completion.
  _repair_comfy_attention_device_limits -- repairs the snapshot-stale
      ``SDP_BATCH_LIMIT`` (2**31) back to the NVIDIA serving value (2**15) on
      NVIDIA devices only.  Already-correct values and nonstandard overrides
      are preserved untouched.  Inert (deferred) while
      ``model_management.cpu_state`` is still CPU-state, so the minimal
      Golden restore completes it after logical GPU reattach.

Known debt (deliberately OUT of scope here, do not implement in this module):
  - model_management full refresh (device/orchestration state beyond the
    logical reattach owned by ``modal_app``),
  - attention backend rebinding / availability-flag recomputation,
  - quant_ops replay (this coordinator never imports or touches quant_ops).

Import contract: stdlib-only imports at module load.  All heavy components
(torch, comfy_kitchen, comfy.model_management) are resolved per call via
``sys.modules.get`` so this module stays import-light for FAST_UNIT and can
never create an import cycle with the runtime entrypoint.
"""

from __future__ import annotations

import sys
from typing import Any

# Snapshot-stale vs serving value for the attention device limit.
_STALE_SDP_BATCH_LIMIT = 2**31
_REPAIRED_SDP_BATCH_LIMIT = 2**15

# Log tag shared with the legacy repair site (duplicated, not imported: this
# module must stay import-light).
_REPAIR_TAG = "[v2.kitchen_backend_proof]"

_KITCHEN_KEY = "kitchen_gpu_backends"
_ATTENTION_KEY = "comfy_attention_device_limits"

_TERMINAL_OUTCOMES = ("complete", "not-applicable")

# Per-provider once-guard.  Only terminal outcomes (complete /
# not-applicable) set these; CUDA-invisible / deferred / error passes never
# consume the guard so a later boundary with real CUDA visible retries.
_provider_done: dict[str, bool] = {
    _KITCHEN_KEY: False,
    _ATTENTION_KEY: False,
}
_provider_reports: dict[str, dict[str, Any]] = {}


def _cuda_visibility() -> tuple[Any | None, bool]:
    """Return ``(cuda_module, visible)`` without importing anything.

    ``torch`` is resolved via ``sys.modules.get`` only.  Missing torch or an
    uncallable/unavailable ``is_available`` probe reads as not visible (never
    raises); the caller maps that to ``deferred`` without consuming the guard.
    """
    try:
        torch_mod = sys.modules.get("torch")
        cuda_mod = getattr(torch_mod, "cuda", None) if torch_mod is not None else None
        probe = getattr(cuda_mod, "is_available", None) if cuda_mod is not None else None
        if not callable(probe):
            return None, False
        return cuda_mod, bool(probe())
    except Exception:
        return None, False


def _repair_kitchen_gpu_backends() -> dict[str, Any]:
    """Re-run kitchen GPU backend registration with real CUDA visible.

    State-only: clears the registry's possibly-stale cached compute
    capability, re-runs the existing native ``_register()`` routines for
    backends that are not explicitly disabled, then restores user/backend
    policy state (``_disabled`` / ``_priority``) and inspects the
    post-registration state before reporting success.  Disabled backends are
    skipped up front (never enabled) and count as terminal policy-preserved
    completion.  Never raises.
    """
    result: dict[str, Any] = {
        "provider": _KITCHEN_KEY,
        "outcome": "deferred",
        "repaired": False,
        "reason": "",
        "cuda": None,
        "triton": None,
    }
    cuda_mod, visible = _cuda_visibility()
    if cuda_mod is None:
        result["reason"] = "torch_unimportable"
        return result
    if not visible:
        # CUDA-invisible: do NOT consume the once-guard; a later boundary
        # (CUDA-init callback, execution entry) retries with real visibility.
        result["reason"] = "cuda_not_visible"
        return result
    try:
        ck = sys.modules.get("comfy_kitchen")
        reg = getattr(ck, "registry", None) if ck is not None else None
    except Exception:
        ck, reg = None, None
    if reg is None:
        result["reason"] = "kitchen_unimportable:Missing"
        return result
    # Stale GPU-derived cache: ``_compute_capability`` may have been evaluated
    # (as None) while CUDA was mocked away during snapshot build.  Drop it so
    # the next validation recomputes lazily.
    try:
        reg.__dict__.pop("_compute_capability", None)
    except Exception:
        pass
    try:
        disabled_before = set(getattr(reg, "_disabled", set()) or set())
        priority_before = list(getattr(reg, "_priority", []) or [])
    except Exception:
        disabled_before = None
        priority_before = None

    def _backend_module(name: str) -> Any | None:
        module = sys.modules.get(f"comfy_kitchen.backends.{name}")
        if module is not None:
            return module
        try:
            __import__(f"comfy_kitchen.backends.{name}")
        except Exception:
            return None
        return sys.modules.get(f"comfy_kitchen.backends.{name}")

    try:
        # CUDA: an intentionally-disabled cuda backend is policy, not damage --
        # skip it and count it as terminal completion (the fixed bug).
        try:
            if disabled_before is not None and "cuda" in disabled_before:
                result["cuda"] = "skipped:disabled"
            else:
                cuda_backend = _backend_module("cuda")
                if cuda_backend is None:
                    result["cuda"] = "failed:Missing"
                else:
                    cuda_backend._register()
                    result["cuda"] = "rerun"
        except Exception as exc:
            result["cuda"] = f"failed:{type(exc).__name__}"
        try:
            disabled_now = (
                disabled_before
                if disabled_before is not None
                else (getattr(reg, "_disabled", set()) or set())
            )
            if "triton" in disabled_now:
                result["triton"] = "skipped:disabled"
            else:
                triton_backend = _backend_module("triton")
                if triton_backend is None:
                    result["triton"] = "failed:Missing"
                else:
                    triton_backend._register()
                    result["triton"] = "rerun"
        except Exception as exc:
            result["triton"] = f"failed:{type(exc).__name__}"
    finally:
        # Native registration owns capabilities/unavailable state, but it must
        # not rewrite user/backend policy state.
        try:
            if disabled_before is not None:
                reg._disabled.clear()
                reg._disabled.update(disabled_before)
        except Exception:
            pass
        try:
            if priority_before is not None:
                reg._priority[:] = priority_before
        except Exception:
            pass
    complete = result["cuda"] in {"rerun", "skipped:disabled"} and result[
        "triton"
    ] in {"rerun", "skipped:disabled"}
    try:
        infos = reg.list_backends()
    except Exception:
        infos = None
    if isinstance(infos, dict):
        try:
            disabled_check = set(getattr(reg, "_disabled", set()) or set())
        except Exception:
            disabled_check = set()

        def _available(name: str) -> bool:
            info = infos.get(name)
            if not isinstance(info, dict):
                return False
            if name in disabled_check or bool(info.get("disabled")):
                return False
            return bool(info.get("available"))

        cuda_ok = result["cuda"] == "skipped:disabled" or (
            result["cuda"] == "rerun" and _available("cuda")
        )
        if result["triton"] == "skipped:disabled":
            triton_ok = True
        else:
            triton_ok = result["triton"] == "rerun" and _available("triton")
        complete = bool(cuda_ok and triton_ok)
        if not complete and not result["reason"]:
            result["reason"] = "backend_unavailable"
    result["repaired"] = complete
    result["outcome"] = "complete" if complete else "deferred"
    try:
        print(
            f"{_REPAIR_TAG} repair_after_restore cuda={result['cuda']} "
            f"triton={result['triton']}",
            flush=True,
        )
    except Exception:
        pass
    return result


def _repair_comfy_attention_device_limits() -> dict[str, Any]:
    """Repair the snapshot-stale attention device batch limit on NVIDIA.

    Rewrites a stale ``SDP_BATCH_LIMIT`` of 2**31 to the serving value 2**15
    when (and only when) CUDA is visible, ``model_management`` has left
    CPU-state, and the device is NVIDIA.  Already-correct values and
    nonstandard overrides are preserved untouched (terminal completion).
    Never raises; never touches quant_ops, backend selection flags, or any
    ``model_management`` state besides the stale limit itself.
    """
    result: dict[str, Any] = {
        "provider": _ATTENTION_KEY,
        "outcome": "deferred",
        "repaired": False,
        "reason": "",
        "limit_before": None,
        "limit_after": None,
    }
    cuda_mod, visible = _cuda_visibility()
    if cuda_mod is None:
        result["reason"] = "torch_unavailable"
        return result
    if not visible:
        result["reason"] = "cuda_not_visible"
        return result
    mm = sys.modules.get("comfy.model_management")
    if mm is None:
        result["outcome"] = "not-applicable"
        result["reason"] = "model_management_unavailable"
        return result
    try:
        cpu_state = getattr(mm, "cpu_state", None)
        cpu_state_cls = getattr(mm, "CPUState", None)
        cpu_val = getattr(cpu_state_cls, "CPU", None) if cpu_state_cls is not None else "CPU"
        if cpu_state is not None and cpu_val is not None and cpu_state == cpu_val:
            # Still CPU-state (snapshot restore has not reattached logical GPU
            # state yet): stay inert so the post-reattach boundary completes us.
            result["reason"] = "cpu_state"
            return result
    except Exception:
        pass
    try:
        get_name = getattr(cuda_mod, "get_device_name", None)
        device_name = str(get_name(0)) if callable(get_name) else ""
    except Exception:
        result["reason"] = "device_name_unavailable"
        return result
    if "nvidia" not in device_name.lower():
        result["outcome"] = "not-applicable"
        result["reason"] = "non_nvidia_device"
        result["device_name"] = device_name
        return result
    holder: Any | None = None
    for candidate in (
        "comfy.model_management",
        "comfy.ops",
        "comfy.ldm.modules.attention",
        "ldm.modules.attention",
    ):
        module = sys.modules.get(candidate)
        if module is not None and hasattr(module, "SDP_BATCH_LIMIT"):
            holder = module
            break
    if holder is None:
        result["outcome"] = "not-applicable"
        result["reason"] = "limit_absent"
        return result
    try:
        current = holder.SDP_BATCH_LIMIT
    except Exception as exc:
        result["outcome"] = "error"
        result["reason"] = f"limit_read_failed:{type(exc).__name__}"
        return result
    result["limit_before"] = current
    if current == _STALE_SDP_BATCH_LIMIT:
        try:
            holder.SDP_BATCH_LIMIT = _REPAIRED_SDP_BATCH_LIMIT
        except Exception as exc:
            result["outcome"] = "error"
            result["reason"] = f"limit_write_failed:{type(exc).__name__}"
            return result
        result["limit_after"] = holder.SDP_BATCH_LIMIT
        result["repaired"] = True
        result["outcome"] = "complete"
        return result
    # Preserve existing NVIDIA values and nonstandard overrides untouched:
    # intentional configuration, not snapshot damage.
    result["limit_after"] = current
    if current == _REPAIRED_SDP_BATCH_LIMIT:
        result["repaired"] = True
        result["reason"] = "already_correct"
    else:
        result["reason"] = "preserved_override"
    result["outcome"] = "complete"
    return result


# Fixed ordered provider chain: kitchen backends first, attention limits after
# (the attention repair is inert until logical GPU reattach, so it naturally
# completes on the post-reattach pass).
_PROVIDERS: tuple[Any, ...] = (
    _repair_kitchen_gpu_backends,
    _repair_comfy_attention_device_limits,
)
_PROVIDER_KEY: dict[str, str] = {
    "_repair_kitchen_gpu_backends": _KITCHEN_KEY,
    "_repair_comfy_attention_device_limits": _ATTENTION_KEY,
}


def begin_gpu_restore() -> dict[str, Any]:
    """Reset repair bookkeeping at the outer restore entry.

    Starts a fresh restore lifecycle: every provider becomes pending again so
    a new restore never inherits the previous lifecycle's completion.  Pure
    bookkeeping -- performs no CUDA calls and never raises.
    """
    try:
        for key in _provider_done:
            _provider_done[key] = False
        _provider_reports.clear()
        return {"reset": True, "pending": sorted(_provider_done)}
    except Exception:
        return {"reset": False, "pending": sorted(_provider_done)}


def _overall_outcome() -> tuple[str, list[str], list[str]]:
    pending = sorted(key for key, done in _provider_done.items() if not done)
    completed = sorted(key for key, done in _provider_done.items() if done)
    if not pending:
        return "complete", pending, completed
    return "", pending, completed


def repair_gpu_capabilities_after_restore() -> dict[str, Any]:
    """Run every eligible unfinished provider once; return a structured report.

    Eligible means not already terminally complete: finished providers are
    skipped (never re-run), pending ones run in ``_PROVIDERS`` order.  One
    bounded pass, no background retries.  Never raises.
    """
    report: dict[str, Any] = {
        "outcome": "complete",
        "providers": {},
        "pending": [],
        "completed": [],
    }
    try:
        if all(_provider_done.values()):
            report["outcome"] = "complete"
            report["reason"] = "already_done"
            report["pending"] = []
            report["completed"] = sorted(_provider_done)
            return report
        ran: dict[str, dict[str, Any]] = {}
        for provider in _PROVIDERS:
            key = _PROVIDER_KEY.get(getattr(provider, "__name__", ""), "")
            if not key or _provider_done.get(key):
                continue
            try:
                provider_result = provider()
            except Exception as exc:  # reported, never swallowed silently
                provider_result = {
                    "provider": key,
                    "outcome": "error",
                    "repaired": False,
                    "reason": f"unexpected:{type(exc).__name__}",
                }
            if not isinstance(provider_result, dict):
                provider_result = {
                    "provider": key,
                    "outcome": "error",
                    "repaired": False,
                    "reason": "invalid_provider_result",
                }
            _provider_reports[key] = provider_result
            ran[key] = provider_result
            report["providers"][key] = provider_result
            if provider_result.get("outcome") in _TERMINAL_OUTCOMES:
                _provider_done[key] = True
        _, pending, completed = _overall_outcome()
        report["pending"] = pending
        report["completed"] = completed
        if not pending:
            outcomes = {
                str((_provider_reports.get(key) or {}).get("outcome", "complete"))
                for key in _provider_done
            }
            report["outcome"] = (
                "not-applicable" if outcomes == {"not-applicable"} else "complete"
            )
            return report
        pending_outcomes = {
            str((_provider_reports.get(key) or {}).get("outcome", "deferred"))
            for key in pending
        }
        if "error" in pending_outcomes:
            report["outcome"] = "error"
        else:
            report["outcome"] = "deferred"
            if not report.get("reason"):
                first = next(iter(pending))
                reason = str(
                    (_provider_reports.get(first) or {}).get("reason", "")
                )
                if reason:
                    report["reason"] = reason
        return report
    except Exception as exc:  # coordinator itself never raises
        report["outcome"] = "error"
        report["reason"] = f"coordinator_failed:{type(exc).__name__}"
        _, pending, completed = _overall_outcome()
        report["pending"] = pending
        report["completed"] = completed
        return report


def ensure_gpu_capabilities_repaired_before_execution() -> dict[str, Any]:
    """Retry-once pending GPU-capability repair at the execution boundary.

    Single bounded repair pass when any provider is still pending; returns the
    terminal ``already_done`` report when everything completed during
    restore.  Placed before any pre-execution readiness early-return so a fast
    ready path cannot bypass pending repair.  Never raises.
    """
    try:
        if all(_provider_done.values()):
            return {
                "outcome": "complete",
                "reason": "already_done",
                "providers": {},
                "pending": [],
                "completed": sorted(_provider_done),
            }
        return repair_gpu_capabilities_after_restore()
    except Exception as exc:
        _, pending, completed = _overall_outcome()
        return {
            "outcome": "error",
            "reason": f"ensure_failed:{type(exc).__name__}",
            "providers": {},
            "pending": pending,
            "completed": completed,
        }
