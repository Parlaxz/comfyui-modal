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
  _repair_model_management_derived_state -- recomputes the small set of
      import-time GPU-derived ``model_management`` globals that the fake-CUDA
      snapshot import froze wrong (``MIN_WEIGHT_MEMORY_RATIO``,
      ``ENABLE_PYTORCH_ATTENTION``, ``NUM_STREAMS``, and the
      ``Fp16Accumulation`` branch when that flag is present), mirroring the
      exact upstream conditions so results equal a fresh-GPU import.
      Explicit user flags always win; values only move toward the
      fresh-import result, never away from explicit policy.
  _repair_attention_backend_selection   -- re-probes the Kitchen INT8
      attention flag with live CUDA, fills newly-available registry entries,
      and re-runs the exact upstream selection sequence into the
      ``optimized_attention`` / ``optimized_attention_masked`` module
      globals.  Honors explicit backend flags and never forces a backend
      (an enabled-but-unavailable Kitchen flag reports error instead of the
      upstream ``exit(-1)``).
  _repair_comfy_attention_device_limits -- repairs the snapshot-stale
      ``SDP_BATCH_LIMIT`` (2**31) back to the NVIDIA serving value (2**15) on
      NVIDIA devices only.  Already-correct values and nonstandard overrides
      are preserved untouched (terminal completion).  Inert (deferred) while
      ``model_management.cpu_state`` is still CPU-state, so the minimal
      Golden restore completes it after logical GPU reattach.

Known debt (deliberately OUT of scope here, do not implement in this module):
  - model_management orchestration state beyond the logical reattach owned
    by ``modal_app`` (placement, VRAM totals, allocator/caches),
  - Sage/Flash package re-imports (owned by the existing Sage policy and
    deferred custom-node retry; this module never imports attention
    packages),
  - direct from-import references captured during snapshot import (e.g. a
    model module holding the old ``optimized_attention_masked`` object keeps
    it; in-module ``CrossAttention`` callers and future imports observe the
    repaired globals),
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
_MM_KEY = "model_management_derived_state"
_ATTN_SELECT_KEY = "attention_backend_selection"
_ATTENTION_KEY = "comfy_attention_device_limits"

_TERMINAL_OUTCOMES = ("complete", "not-applicable")

# Per-provider once-guard.  Only terminal outcomes (complete /
# not-applicable) set these; CUDA-invisible / deferred / error passes never
# consume the guard so a later boundary with real CUDA visible retries.
_provider_done: dict[str, bool] = {
    _KITCHEN_KEY: False,
    _MM_KEY: False,
    _ATTN_SELECT_KEY: False,
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
    mm: Any = sys.modules.get("comfy.model_management")
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


def _mm_flag(args: Any, name: str) -> bool:
    """Read a CLI/policy flag without importing anything (never raises)."""
    try:
        return bool(getattr(args, name, False)) if args is not None else False
    except Exception:
        return False


def _repair_model_management_derived_state() -> dict[str, Any]:
    """Recompute import-time GPU-derived ``model_management`` globals.

    Mirrors the exact upstream conditions (``model_management.py`` 458-475,
    553-559, 1372-1385) so repaired values equal a fresh-GPU import:
    ``MIN_WEIGHT_MEMORY_RATIO`` (0.0 on NVIDIA), the
    ``ENABLE_PYTORCH_ATTENTION`` NVIDIA/auto branch, ``NUM_STREAMS`` (2 on
    NVIDIA/AMD), and the ``Fp16Accumulation`` branch when that flag is
    present.  Explicit user flags always win; values only move toward the
    fresh-import result, never away from explicit policy.  Inert while
    CPU-state or CUDA invisible.  Never raises; never touches placement,
    VRAM totals, allocator state, SDPA backend enables, or quant_ops.
    """
    result: dict[str, Any] = {
        "provider": _MM_KEY,
        "outcome": "deferred",
        "repaired": False,
        "reason": "",
        "changes": {},
    }
    cuda_mod, visible = _cuda_visibility()
    if cuda_mod is None:
        result["reason"] = "torch_unavailable"
        return result
    if not visible:
        result["reason"] = "cuda_not_visible"
        return result
    mm: Any = sys.modules.get("comfy.model_management")
    if mm is None:
        result["reason"] = "model_management_unavailable"
        return result
    try:
        cpu_state = getattr(mm, "cpu_state", None)
        cpu_state_cls = getattr(mm, "CPUState", None)
        cpu_val = getattr(cpu_state_cls, "CPU", None) if cpu_state_cls is not None else "CPU"
        if cpu_state is not None and cpu_val is not None and cpu_state == cpu_val:
            result["reason"] = "cpu_state"
            return result
    except Exception:
        pass
    try:
        cli = sys.modules.get("comfy.cli_args")
        args = getattr(cli, "args", None) if cli is not None else None
    except Exception:
        args = None
    if args is None:
        result["reason"] = "cli_args_unavailable"
        return result
    try:
        is_nvidia_fn = getattr(mm, "is_nvidia", None)
        is_amd_fn = getattr(mm, "is_amd", None)
        is_nvidia = bool(is_nvidia_fn()) if callable(is_nvidia_fn) else False
        try:
            is_amd = bool(is_amd_fn()) if callable(is_amd_fn) else False
        except Exception:
            is_amd = False
    except Exception as exc:
        result["outcome"] = "error"
        result["reason"] = f"predicate_failed:{type(exc).__name__}"
        return result
    changes: dict[str, list[Any]] = {}
    try:
        want_ratio = 0.0 if is_nvidia else 0.4
        current_ratio = getattr(mm, "MIN_WEIGHT_MEMORY_RATIO", None)
        if current_ratio != want_ratio:
            mm.MIN_WEIGHT_MEMORY_RATIO = want_ratio
            changes["MIN_WEIGHT_MEMORY_RATIO"] = [current_ratio, want_ratio]
        enabled = bool(getattr(mm, "ENABLE_PYTORCH_ATTENTION", False))
        if _mm_flag(args, "use_pytorch_cross_attention"):
            if not enabled:
                mm.ENABLE_PYTORCH_ATTENTION = True
                changes["ENABLE_PYTORCH_ATTENTION"] = [enabled, True]
            try:
                if getattr(mm, "XFORMERS_IS_AVAILABLE", True):
                    mm.XFORMERS_IS_AVAILABLE = False
                    changes["XFORMERS_IS_AVAILABLE"] = [True, False]
            except Exception:
                pass
        elif not enabled:
            auto = False
            try:
                tvn = getattr(mm, "torch_version_numeric", None)
                split = _mm_flag(args, "use_split_cross_attention")
                quad = _mm_flag(args, "use_quad_cross_attention")
                if (
                    is_nvidia
                    and tvn is not None
                    and tvn[0] >= 2
                    and not split
                    and not quad
                ):
                    auto = True
                elif not split and not quad:
                    for probe_name in (
                        "is_intel_xpu",
                        "is_ascend_npu",
                        "is_mlu",
                        "is_ixuca",
                    ):
                        probe = getattr(mm, probe_name, None)
                        try:
                            if callable(probe) and probe():
                                auto = True
                                break
                        except Exception:
                            continue
            except Exception:
                auto = False
            if auto:
                mm.ENABLE_PYTORCH_ATTENTION = True
                changes["ENABLE_PYTORCH_ATTENTION"] = [enabled, True]
        explicit_streams = getattr(args, "async_offload", None)
        if explicit_streams is not None:
            want_streams: Any | None = int(explicit_streams)
        elif _mm_flag(args, "disable_async_offload"):
            want_streams = 0
        elif is_nvidia or is_amd:
            want_streams = 2
        else:
            want_streams = None
        if want_streams is not None:
            current_streams = getattr(mm, "NUM_STREAMS", None)
            if current_streams != want_streams:
                mm.NUM_STREAMS = want_streams
                changes["NUM_STREAMS"] = [current_streams, want_streams]
        try:
            fast = getattr(args, "fast", None) or ()
            wants_fp16 = any(
                v == "fp16_accumulation"
                or getattr(v, "value", None) == "fp16_accumulation"
                or str(v) == "fp16_accumulation"
                for v in fast
            )
        except Exception:
            wants_fp16 = False
        if wants_fp16 and (is_nvidia or is_amd):
            try:
                torch_mod = sys.modules.get("torch")
                matmul = getattr(
                    getattr(torch_mod, "backends", None), "cuda", None
                )
                matmul = getattr(matmul, "matmul", None)
                if matmul is not None and hasattr(matmul, "allow_fp16_accumulation"):
                    matmul.allow_fp16_accumulation = True
                if not bool(getattr(mm, "PRIORITIZE_FP16", False)):
                    mm.PRIORITIZE_FP16 = True
                    changes["PRIORITIZE_FP16"] = [False, True]
            except Exception:
                pass
    except Exception as exc:
        result["outcome"] = "error"
        result["reason"] = f"recompute_failed:{type(exc).__name__}"
        return result
    result["changes"] = changes
    result["repaired"] = True
    result["outcome"] = "complete"
    if not changes:
        result["reason"] = "already_correct"
    try:
        print(
            f"[gpu_restore.model_management] changes={changes}",
            flush=True,
        )
    except Exception:
        pass
    return result


def _repair_attention_backend_selection() -> dict[str, Any]:
    """Re-probe Kitchen attention availability and re-run backend selection.

    Mirrors the exact upstream import-time sequence (``attention.py``
    891-919 for selection, 925-937 for registry fill): explicit backend
    flags win, then live predicates, then the split/sub_quad fallback; a
    Kitchen request without availability reports error instead of the
    upstream ``exit(-1)``.  Rebinds the ``optimized_attention`` /
    ``optimized_attention_masked`` module globals so in-module
    ``CrossAttention`` callers and future imports observe the repaired
    selection.  Direct from-import references captured during snapshot
    import keep their old binding (documented limitation, not silently
    fixed).  Never raises; never imports attention packages; never forces
    a backend.
    """
    result: dict[str, Any] = {
        "provider": _ATTN_SELECT_KEY,
        "outcome": "deferred",
        "repaired": False,
        "reason": "",
        "before": None,
        "after": None,
        "kitchen_available": None,
        "registered_added": [],
    }
    cuda_mod, visible = _cuda_visibility()
    if cuda_mod is None:
        result["reason"] = "torch_unavailable"
        return result
    if not visible:
        result["reason"] = "cuda_not_visible"
        return result
    mm: Any = sys.modules.get("comfy.model_management")
    if mm is None:
        result["reason"] = "model_management_unavailable"
        return result
    try:
        cpu_state = getattr(mm, "cpu_state", None)
        cpu_state_cls = getattr(mm, "CPUState", None)
        cpu_val = getattr(cpu_state_cls, "CPU", None) if cpu_state_cls is not None else "CPU"
        if cpu_state is not None and cpu_val is not None and cpu_state == cpu_val:
            result["reason"] = "cpu_state"
            return result
    except Exception:
        pass
    attn_mod: Any = sys.modules.get("comfy.ldm.modules.attention")
    if attn_mod is None:
        result["reason"] = "attention_module_unavailable"
        return result
    try:
        cli = sys.modules.get("comfy.cli_args")
        args = getattr(cli, "args", None) if cli is not None else None
    except Exception:
        args = None
    if args is None:
        result["reason"] = "cli_args_unavailable"
        return result
    try:
        before_fn = getattr(attn_mod, "optimized_attention", None)
        result["before"] = getattr(before_fn, "__name__", None)
    except Exception:
        result["before"] = None
    try:
        ck = sys.modules.get("comfy_kitchen")
        probe = getattr(ck, "int8_attention_is_available", None) if ck is not None else None
        old_kitchen = bool(getattr(attn_mod, "COMFY_KITCHEN_INT8_ATTENTION_IS_AVAILABLE", False))
        if callable(probe):
            try:
                new_kitchen = bool(probe())
            except Exception as exc:
                result["kitchen_probe_error"] = type(exc).__name__
                new_kitchen = old_kitchen
            if new_kitchen != old_kitchen:
                try:
                    attn_mod.COMFY_KITCHEN_INT8_ATTENTION_IS_AVAILABLE = new_kitchen
                except Exception as exc:
                    result["outcome"] = "error"
                    result["reason"] = f"kitchen_flag_write_failed:{type(exc).__name__}"
                    return result
            kitchen_flag = new_kitchen
        else:
            kitchen_flag = old_kitchen
        result["kitchen_available"] = kitchen_flag
        register_fn = getattr(attn_mod, "register_attention_function", None)
        registry = getattr(attn_mod, "REGISTERED_ATTENTION_FUNCTIONS", None)
        added: list[str] = []
        if callable(register_fn) and isinstance(registry, dict):
            xfon_fn = getattr(mm, "xformers_enabled", None)
            try:
                xfon = bool(xfon_fn()) if callable(xfon_fn) else False
            except Exception:
                xfon = False
            candidates = [
                ("comfy_kitchen_int8", getattr(attn_mod, "attention_comfy_kitchen_int8", None), kitchen_flag),
                ("sage", getattr(attn_mod, "attention_sage", None), bool(getattr(attn_mod, "SAGE_ATTENTION_IS_AVAILABLE", False))),
                ("sage3", getattr(attn_mod, "attention3_sage", None), bool(getattr(attn_mod, "SAGE_ATTENTION3_IS_AVAILABLE", False))),
                ("flash", getattr(attn_mod, "attention_flash", None), bool(getattr(attn_mod, "FLASH_ATTENTION_IS_AVAILABLE", False))),
                ("xformers", getattr(attn_mod, "attention_xformers", None), xfon),
                ("pytorch", getattr(attn_mod, "attention_pytorch", None), True),
                ("sub_quad", getattr(attn_mod, "attention_sub_quad", None), True),
                ("split", getattr(attn_mod, "attention_split", None), True),
            ]
            for name, fn, available in candidates:
                if available and fn is not None and name not in registry:
                    try:
                        register_fn(name, fn)
                    except Exception:
                        continue
                    if name in registry:
                        added.append(name)
        result["registered_added"] = added
        try:
            xfon_live = bool(mm.xformers_enabled()) if callable(getattr(mm, "xformers_enabled", None)) else False
        except Exception:
            xfon_live = False
        selected_name: str | None = None
        selected_fn: Any | None = None
        if _mm_flag(args, "use_sage_attention"):
            selected_name, selected_fn = "sage", getattr(attn_mod, "attention_sage", None)
        elif _mm_flag(args, "use_flash_attention"):
            selected_name, selected_fn = "flash", getattr(attn_mod, "attention_flash", None)
        elif xfon_live:
            selected_name, selected_fn = "xformers", getattr(attn_mod, "attention_xformers", None)
        elif bool(getattr(mm, "ENABLE_PYTORCH_ATTENTION", False)):
            selected_name, selected_fn = "pytorch", getattr(attn_mod, "attention_pytorch", None)
        elif _mm_flag(args, "use_split_cross_attention"):
            selected_name, selected_fn = "split", getattr(attn_mod, "attention_split", None)
        else:
            selected_name, selected_fn = "sub_quad", getattr(attn_mod, "attention_sub_quad", None)
        if _mm_flag(args, "use_ck_attention"):
            if kitchen_flag:
                selected_name, selected_fn = (
                    "comfy_kitchen_int8",
                    getattr(attn_mod, "attention_comfy_kitchen_int8", None),
                )
            else:
                result["outcome"] = "error"
                result["reason"] = "kitchen_requested_unavailable"
                return result
        if selected_fn is None:
            result["outcome"] = "error"
            result["reason"] = f"selection_missing:{selected_name}"
            return result
        attn_mod.optimized_attention = selected_fn
        attn_mod.optimized_attention_masked = selected_fn
        result["after"] = selected_name
        result["repaired"] = True
        result["outcome"] = "complete"
        try:
            print(
                f"[gpu_restore.attention] before={result['before']} "
                f"after={selected_name} kitchen={kitchen_flag} "
                f"registered_added={added}",
                flush=True,
            )
        except Exception:
            pass
        return result
    except Exception as exc:
        result["outcome"] = "error"
        result["reason"] = f"selection_failed:{type(exc).__name__}"
        return result


# Fixed ordered provider chain: kitchen backends first, derived
# model-management state second (attention selection reads its predicates),
# attention selection third, attention device limits last (inert until logical
# GPU reattach, so it naturally completes on the post-reattach pass).
_PROVIDERS: tuple[Any, ...] = (
    _repair_kitchen_gpu_backends,
    _repair_model_management_derived_state,
    _repair_attention_backend_selection,
    _repair_comfy_attention_device_limits,
)
_PROVIDER_KEY: dict[str, str] = {
    "_repair_kitchen_gpu_backends": _KITCHEN_KEY,
    "_repair_model_management_derived_state": _MM_KEY,
    "_repair_attention_backend_selection": _ATTN_SELECT_KEY,
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
