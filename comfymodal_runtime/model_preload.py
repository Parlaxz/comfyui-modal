"""UNET/CLIP/VAE restore preparation with prefill filtering and execution-phase overlap.

Controls:
  COMFYMODAL_V2_PREFILL_LANES — critical|all|none (default critical)
  COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET — legacy barrier (default off)
  COMFYMODAL_V2_DEEP_MODEL_DIAG=1 — enable deep /proc, faults, open/mmap/safetensors
"""

from __future__ import annotations

import enum
import functools
import math
import os
import platform
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Condition, RLock
from collections.abc import Mapping
from typing import Any, Callable, Iterator

from .contracts import ModelRestoreKey, PrefillKey, stable_hash
from .cpu_snapshot_models import (
    collect_unet_runtime_state,
)
from .trace import RuntimeTrace
from .unet_forward_probe import (
    emit_post_load_models_gpu_event,
    install_nextdit_forward_pre_hook,
    register_unet_forward_probe,
    set_unet_gpu_demand_start,
    _has_registered_unet_in_models,
)

# ── Prefill lane mode ─────────────────────────────────────────────────
# Controls which CLIPTextEncode entries are pre-encoded during restore.
#   "critical": only role=positive/negative
#   "all":      encode all entries (previous behavior)
#   "none":     skip prefill entirely
_PREFILL_LANE_MODE: str = os.environ.get(
    "COMFYMODAL_V2_PREFILL_LANES", "critical"
).strip().lower()
# Validate: only "critical", "all", "none" are accepted.  Anything else
# is treated as a safe default ("critical") so that invalid env values
# never bypass the safety gate.
if _PREFILL_LANE_MODE not in ("critical", "all", "none"):
    _PREFILL_LANE_MODE = "critical"
_PREFILL_CRITICAL_ROLES: frozenset[str] = frozenset({"positive", "negative"})

# ── Page-fault delta tracking for model-path instrumentation ─────
# Uses resource.getrusage (RUSAGE_SELF) to measure major/minor page
# faults around actual first access to restored CLIP/UNET CPU state.
# Deliberately wraps the OUTERMOST invocation of each operation so
# inner nested calls do not double-count.

_PAGEFAULT_TRACKING: bool = (
    os.environ.get("COMFYMODAL_V2_PAGEFAULT_TRACKING", "1") == "1"
)


@dataclass
class _PageFaultSnapshot:
    """Snapshot of process page-fault counters at a given moment.
    Uses resource.getrusage (Linux-only; returns zeros on other platforms).
    """
    major: int = 0
    minor: int = 0

    @classmethod
    def now(cls) -> "_PageFaultSnapshot":
        try:
            import resource as _r
            ru = _r.getrusage(_r.RUSAGE_SELF)
            return cls(major=ru.ru_majflt, minor=ru.ru_minflt)
        except Exception:
            return cls()


def _pagefault_delta(before: _PageFaultSnapshot, after: _PageFaultSnapshot) -> dict[str, int]:
    """Return major/minor fault deltas from two snapshots."""
    return {
        "major_faults": max(0, after.major - before.major),
        "minor_faults": max(0, after.minor - before.minor),
    }


# ── V2 prefill overlap: wait-for-UNET policy ─────────────────────
# Default behaviour (recommended): prefill waits for CLIP only and
# begins encoding without blocking on UNET.  The UNET restore runs
# in parallel and its GPU commit is serialised through the mutation
# lane — safe because ``load_models_gpu`` acquires the lane before
# touching GPU memory.
#
# Set to ``1`` / ``true`` / ``yes`` to restore the old barrier that
# waits for UNET *before* CLIP, putting 5.7-6.3s Qwen-encode on the
# critical path (useful for debugging or regression isolation).
_V2_PREFILL_WAIT_FOR_UNET: bool = os.environ.get(
    "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET", ""
).strip().lower() in ("1", "true", "yes")


# ── Canonical lane vocabulary ─────────────────────────────────────────

_LANE_TO_CANONICAL: dict[str, str] = {
    "unet": "UNET",
    "clip": "CLIP",
    "vae": "VAE",
    "prefill": "prefill",
    "execution_prefill": "prefill",
}
"""Maps internal ``_submit`` lane names to canonical identifiers."""

# ── V2 restore correlation identity ──────────────────────────────────
_LATEST_RESTORED_INSTANCE_ID: str = ""
_LATEST_RESTORE_SESSION_ID: str = ""
"""Module-level latest restored_instance_id.  Set by restore() after
snapshot restoration; read by background worker and graph-entry paths."""

_LATEST_RESTORE_RETURN_MARKER: dict[str, Any] | None = None
"""Set immediately before ``restore()`` returns with wall/monotonic time,
both restore IDs, MODAL_TASK_ID, and PID.  Read by ``run_plan_stream`` method
entry for method-entry-gap computation."""

_DIAGNOSTIC_FLAG: bool = (
    os.environ.get("COMFYMODAL_V2_DEEP_MODEL_DIAG", "0") == "1"
)
"""Controls deep diagnostics (proc/pagefault/open/mmap/safetensors detail).
``False`` by default — when disabled, only lightweight identity, restore
total, CLIP read/ready, background submitted/ready, graph demand/wait,
and method gaps are reported."""

# ── Slow model-read threshold ─────────────────────────────────────────
# When a CLIP load_torch_file or background-UNET active read exceeds this
# wall-time threshold (ms), a detailed ``[v2.slow_model_read]`` diagnostic
# line is emitted with counter deltas, /proc/meminfo, and cgroup stats.
# Invalid/negative/non-finite values fall back safely to 3000.


def _parse_slow_read_threshold() -> float:
    """Parse COMFYMODAL_V2_SLOW_READ_THRESHOLD_MS with safe fallback to 3000."""
    try:
        _val = os.environ.get("COMFYMODAL_V2_SLOW_READ_THRESHOLD_MS", "3000")
        _parsed = float(_val)
        if _parsed >= 0 and math.isfinite(_parsed):
            return _parsed
    except Exception:
        pass
    return 3000.0


_SLOW_READ_THRESHOLD_MS: float = _parse_slow_read_threshold()

# ── Per-worker lane context (set around worker callback) ─────────────

_ACTIVE_LANE_TRACE: ContextVar["ModelLaneTrace | None"] = ContextVar(
    "comfymodal_active_lane_trace", default=None
)
_ACTIVE_REQUEST_TRACE: ContextVar["RuntimeTrace | None"] = ContextVar(
    "comfymodal_active_request_trace", default=None
)
"""Set to the active ``ModelLaneTrace`` while a worker callback runs.
Reset to ``None`` after the callback completes."""

# ── Background UNET diagnostics store ────────────────────────────────
# Thread-safe mapping from canonical key -> completed RuntimeTrace events
# list for background UNET worker.  Written by the worker thread, read
# (and drained) by the graph cache patcher.
_BG_UNET_DIAG_STORE: dict[str, list] = {}
_BG_UNET_DIAG_LOCK = RLock()

# ── ComfyUI core dispatch wrappers (installed once globally) ─────────
# Wrappers target the *live* module objects already loaded by ComfyUI's
# ``nodes.py`` at startup, resolving via ``sys.modules`` rather than a
# fresh ``import`` (which can fail on optional dependencies such as
# ``comfy_aimdo``).  Each component is tracked independently.

_SENTINEL_READ = "_comfy_modal_read_wrapper"
_SENTINEL_GPU = "_comfy_modal_gpu_wrapper"
_SENTINEL_SD = "_comfy_modal_sd_wrapper"
_SENTINEL_SUBFN = "_comfy_modal_subfn_wrapper"
_SENTINEL_DEEP_ST = "_comfy_modal_deep_st_wrapper"
_SENTINEL_DEEP_TL = "_comfy_modal_deep_tl_wrapper"
_SENTINEL_CLIP = "_comfy_modal_clip_wrapper"
_SENTINEL_CLIP_SUBFN = "_comfy_modal_clip_subfn_wrapper"
_SENTINEL_UNET_SUBFN = "_comfy_modal_unet_subfn_wrapper"
_SENTINEL_SHARED_COQ = "_comfy_modal_shared_convert_old_quants"
_SENTINEL_MODEL_PATCHER = "_comfy_modal_model_patcher_wrapper"
_SENTINEL_MODEL_TO = "_comfy_modal_model_to_wrapper"
_SENTINEL_CLIP_CONSTRUCTOR = "_comfy_modal_clip_constructor_wrapper"
_SENTINEL_CLIP_LOAD_SD = "_comfy_modal_clip_load_sd_wrapper"
_SENTINEL_MODEL_PATCHER_LOAD = "_comfy_modal_model_patcher_load_wrapper"
_SENTINEL_MODEL_PATCHER_LOAD_LIST = "_comfy_modal_model_patcher_load_list_wrapper"
_SENTINEL_MODEL_PATCHER_PATCH_WEIGHT = "_comfy_modal_model_patcher_patch_weight_wrapper"
_SENTINEL_CAST_TO_DEVICE = "_comfy_modal_cast_to_device_wrapper"

_read_wrapper_installed: bool = False
_gpu_wrapper_installed: bool = False
_sd_wrapper_installed: bool = False
_subfn_wrappers_installed: bool = False
_deep_diag_wrappers_installed: bool = False
_clip_wrapper_installed: bool = False
_clip_constructor_wrapper_installed: bool = False
_clip_load_sd_wrapper_installed: bool = False
_wrappers_lock = RLock()

# Reentrancy guards — per-thread via ContextVar default=0.
_torch_file_depth: ContextVar[int] = ContextVar("_torch_file_depth", default=0)
_gpu_depth: ContextVar[int] = ContextVar("_gpu_depth", default=0)
_sd_depth: ContextVar[int] = ContextVar("_sd_depth", default=0)
_deep_st_depth: ContextVar[int] = ContextVar("_deep_st_depth", default=0)
_deep_tl_depth: ContextVar[int] = ContextVar("_deep_tl_depth", default=0)
_clip_depth: ContextVar[int] = ContextVar("_clip_depth", default=0)
_clip_subfn_depth: ContextVar[int] = ContextVar("_clip_subfn_depth", default=0)
_clip_constructor_depth: ContextVar[int] = ContextVar("_clip_constructor_depth", default=0)

# ModelPatcher.load aggregate-timing breakdown contexts
_model_patcher_load_depth: ContextVar[int] = ContextVar("_model_patcher_load_depth", default=0)
# Breakdown accumulator dict set only during outer ModelPatcher.load under request trace.
# Keys: outer_start_ns, outer_thread_start_ns, outer_process_start_ns,
#       load_list_wall_ns, load_list_process_start_ns, load_list_process_end_ns,
#       patch_weight_count, patch_weight_wall_ns, patch_weight_process_ns,
#       cast_count, cast_wall_ns, cast_process_ns
_model_patcher_breakdown: ContextVar[dict | None] = ContextVar("_model_patcher_breakdown", default=None)

# ── Deep-diagnostic target path (thread-local) ──────────────────────
# Set by the background UNET worker before the load body; used by the
# deep diag wrappers to filter: only emit stage events when the current
# thread's *target_path* matches the file being accessed AND deep diag
# is enabled.  Avoids logging unrelated model loads.
_DEEP_TARGET_PATH: ContextVar[str] = ContextVar("_deep_target_path", default="")

# Residual tracking — list of child duration_ms collected during an SD outer call.
_child_durations: ContextVar[list[float] | list[tuple[str, float]] | None] = ContextVar("_child_durations", default=None)

# CLIP CPU prepare child durations.
_clip_cpu_prepare_children: ContextVar[list[tuple[str, float]] | None] = ContextVar("_clip_cpu_prepare_children", default=None)

# GPU request-local invocation count (ContextVar for per-thread safety).
_gpu_request_call_count_var: ContextVar[int] = ContextVar("_gpu_request_call_count", default=0)

# UNET subfn nesting depth — tracks cross-function nesting for non-overlapping measured children.
_unet_subfn_nesting_depth: ContextVar[int] = ContextVar("_unet_subfn_nesting_depth", default=0)

# Accumulator for "not_observed" GPU wrapper calls (no lane/request scope).
_not_observed_gpu_calls: int = 0

# ── UNET effective-dtype resolver (shared by snapshot and normal paths) ──
# Resolution strategy depends on context:
#
#   1. Normal (GPU) load path — uses the real CUDA hardware via ComfyUI's
#      model_management.unet_dtype() auto-detection.  The "default" string
#      is passed through to UNETLoader.load_unet which leaves model_options
#      empty, letting ComfyUI probe the real GPU.  This works because CUDA
#      is available.
#
#   2. CPU snapshot construction path — there is NO GPU available (Modal's
#      CPU snapshot builder).  CUDA APIs cannot be called.  The effective
#      dtype must be resolved from the *configured* target GPU(s) via the
#      target-GPU policy in gpu_catalog.gpu_supports_bf16().
#
# The resolve_unet_effective_dtype() function accepts an optional
# *target_gpus* parameter.  When provided (snapshot path), it uses
# the pure static lookup.  When absent (normal path), it falls back
# to the real GPU probe path.
#
# DO NOT cache a false CUDA capability result from the CPU snapshot builder.
# DO NOT call torch.cuda.* APIs from code that runs during snapshot
# construction.

# ── CPU-snapshot native-BF16 compute policy ─────────────────────────────
# Contextmanager that temporarily patches comfy.model_management.unet_manual_cast
# during snapshot UNET construction on CPU so native BF16 compute is used.
# Without this patch, unet_manual_cast gets CPU as inference_device and falls
# through to torch.float32, building the model with fp32 compute even though
# weights are bfloat16.
#
# Thread-safety: the dedicated lock is held across the entire patched interval
# (install + yield + restore).  The patched wrapper uses a thread-identity
# ContextVar so unrelated callers on other threads always delegate to the
# original function.

_CPU_SNAPSHOT_UNET_COMPUTE_POLICY_LOCK: RLock = RLock()

_CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD: ContextVar[int] = ContextVar(
    "_cpu_snapshot_unet_policy_active_thread", default=0
)

_CPU_SNAPSHOT_UNET_MANUAL_CAST_OVERRIDE: ContextVar[str] = ContextVar(
    "_cpu_snapshot_unet_manual_cast_override", default=""
)


@contextmanager
def cpu_snapshot_unet_compute_policy(
    *,
    effective_weight_dtype: Any,
    target_gpus: tuple[str, ...],
) -> Iterator[None]:
    import sys as _sys
    import torch as _torch
    import threading
    from gpu_catalog import gpu_supports_bf16

    # Primary GPU semantics: only the first target GPU determines BF16 capability,
    # consistent with resolve_unet_effective_dtype and _resolve_compute_policy.
    _primary_gpu = target_gpus[0] if target_gpus else ""
    _should_patch = (
        effective_weight_dtype is not None
        and effective_weight_dtype == _torch.bfloat16
        and _primary_gpu
        and gpu_supports_bf16(_primary_gpu)
    )

    if not _should_patch:
        yield
        return

    _tid = threading.get_ident()
    _current = _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD.get()
    if _current != 0 and _current == _tid:
        raise RuntimeError(
            "cpu_snapshot_unet_compute_policy is not reentrant: "
            "a policy context is already active on this thread"
        )

    _mm = None
    _orig_fn = None
    _installed = False
    try:
        with _CPU_SNAPSHOT_UNET_COMPUTE_POLICY_LOCK:
            if _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD.get() != 0:
                yield
                return

            _mm = _sys.modules.get("comfy.model_management")
            if _mm is None:
                yield
                return

            _orig_fn = getattr(_mm, "unet_manual_cast", None)
            if _orig_fn is None:
                yield
                return

            _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD.set(_tid)
            _CPU_SNAPSHOT_UNET_MANUAL_CAST_OVERRIDE.set("none")

            def _policy_wrapper(
                weight_dtype: Any,
                inference_device: Any,
                supported_dtypes: list | None = None,
            ) -> Any:
                if _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD.get() == threading.get_ident():
                    _mode = _CPU_SNAPSHOT_UNET_MANUAL_CAST_OVERRIDE.get()
                    if _mode == "none" and weight_dtype is _torch.bfloat16:
                        return None
                if _orig_fn is not None:
                    if supported_dtypes is not None:
                        return _orig_fn(weight_dtype, inference_device, supported_dtypes)
                    return _orig_fn(weight_dtype, inference_device)
                return None

            setattr(_mm, "unet_manual_cast", _policy_wrapper)
            _installed = True

            # Yield INSIDE the lock — lock covers install + yield + restore
            yield

    finally:
        if _installed and _mm is not None and _orig_fn is not None:
            # Restore under the same lock acquisition; re-read the live
            # module to handle edge cases where model_management was
            # reloaded between yield and finally.
            # ContextVars are reset in a nested try/finally so they are
            # cleared even if the module attribute restore raises.
            with _CPU_SNAPSHOT_UNET_COMPUTE_POLICY_LOCK:
                _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD.set(0)
                _CPU_SNAPSHOT_UNET_MANUAL_CAST_OVERRIDE.set("")
                _installed = False
                # Restore the original function — if this raises, the
                # ContextVars above have already been reset so subsequent
                # operations are not permanently broken.
                restore_target = _sys.modules.get("comfy.model_management")
                if restore_target is not None:
                    setattr(restore_target, "unet_manual_cast", _orig_fn)


def resolve_unet_effective_dtype(
    weight_dtype_str: str = "default",
    *,
    target_gpus: tuple[str, ...] | None = None,
) -> tuple[Any, str]:
    """Resolve a weight_dtype string to the *effective* torch dtype.

    Returns ``(effective_dtype, resolved_label)`` where *effective_dtype* is
    the ``torch.dtype`` the configured GPU load path would use for this
    string, and *resolved_label* is a short diagnostic label.

    **target_gpus** (tuple of canonical Modal GPU names, optional):
      When provided (CPU snapshot construction), the effective dtype is
      determined from the *configured* target GPU(s) via a pure name-based
      lookup — no CUDA API calls.  The primary (first) GPU in the tuple
      is used.
      When ``None`` (normal runtime path), the function falls through to
      let ComfyUI's normal runtime policy apply (``"default"`` passes
      through as-is, returning ``(None, "default")``).

    Decision order:
      1. CLI flags override everything (``--fp32-unet``, ``--bf16-unet``, …).
      2. Explicit fp8/e4m3fn/e5m2 strings -> corresponding torch dtype.
      3. ``"default"`` with *target_gpus* -> target-GPU policy lookup.
      4. ``"default"`` without *target_gpus* -> ``(None, "default")``
         (let ComfyUI auto-detect at load time).

    Both the snapshot construction path (``_cpu_load_unet``) and the normal
    loader path (``V2LoaderBridge._load_unet``) use this function so they
    cannot drift.

    Returns
    -------
    effective_dtype
        The resolved ``torch.dtype``, or ``None`` for unrecognised strings
        / pass-through values.
    resolved_label
        Short string for diagnostic logging.
    """
    # Import torch lazily — may not be available at parse time in all contexts.
    import torch as _torch
    import comfy.cli_args as _ca

    # 1. CLI flags (work in both normal and CPU-snapshot contexts)
    if getattr(_ca.args, "fp32_unet", False):
        return (_torch.float32, "float32")
    if getattr(_ca.args, "fp64_unet", False):
        return (_torch.float64, "float64")
    if getattr(_ca.args, "bf16_unet", False):
        return (_torch.bfloat16, "bfloat16")
    if getattr(_ca.args, "fp16_unet", False):
        return (_torch.float16, "float16")

    # 2. Explicit fp8 strings (float8 types may not exist in older PyTorch)
    _float8_e4m3fn = getattr(_torch, "float8_e4m3fn", None)
    _float8_e5m2 = getattr(_torch, "float8_e5m2", None)
    if weight_dtype_str in ("fp8_e4m3fn", "fp8_e4m3fn_fast"):
        if _float8_e4m3fn is not None:
            return (_float8_e4m3fn, weight_dtype_str)
        return (None, weight_dtype_str)
    if weight_dtype_str == "fp8_e5m2":
        if _float8_e5m2 is not None:
            return (_float8_e5m2, weight_dtype_str)
        return (None, weight_dtype_str)

    # 3. Recognised non-"default" string without a type override
    if weight_dtype_str != "default":
        return (None, weight_dtype_str)

    # 4. "default" with target_gpus — snapshot construction path.
    #    Use the configured target GPU(s), not the local CUDA state.
    if target_gpus is not None:
        from gpu_catalog import gpu_supports_bf16
        # Use the primary (first) target GPU for capability check
        _primary = target_gpus[0] if target_gpus else ""
        if _primary and gpu_supports_bf16(_primary):
            return (_torch.bfloat16, "bfloat16")
        return (_torch.float32, "float32")

    # 5. "default" without target_gpus — normal runtime path.
    #    Let ComfyUI auto-detect at load time by returning None.
    return (None, "default")

# Submission correlation counter
_SUBMISSION_COUNTER: int = 0
_SUBMISSION_COUNTER_LOCK = RLock()

def _next_submission_id() -> str:
    global _SUBMISSION_COUNTER
    with _SUBMISSION_COUNTER_LOCK:
        _SUBMISSION_COUNTER += 1
        return f"s{_SUBMISSION_COUNTER:04d}"


def _get_live_module(mod_name: str) -> Any | None:
    """Return an already-loaded module from sys.modules (never triggers import)."""
    import sys
    return sys.modules.get(mod_name)


# ── Wrapper factories ───────────────────────────────────────────────


def _make_torch_file_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``comfy.utils.load_torch_file`` to emit ``read_start/read_end``.

    Reentrancy-safe: nested calls from within the same thread do not
    duplicate outer events.
    """

    @functools.wraps(original)
    def wrapper(ckpt, safe_load=False, device=None, return_metadata=False):
        before = _torch_file_depth.get()
        _torch_file_depth.set(before + 1)
        _slow_read_state: _SlowReadBeforeState | None = None
        _slow_ru_before: dict[str, Any] | None = None
        _slow_io_before: dict[str, int] | None = None
        _read_outer_ns: int = 0
        _pf_before: _PageFaultSnapshot | None = None
        if before == 0:
            lane = _ACTIVE_LANE_TRACE.get()
            if lane is not None:
                _read_outer_ns = time.monotonic_ns()
                # Capture page-fault snapshot before actual read (CLIP/UNET page-in)
                if _PAGEFAULT_TRACKING and lane._lane in ("CLIP", "UNET"):
                    _pf_before = _PageFaultSnapshot.now()
                lane.read_start()
                if lane._lane == "CLIP":
                    _slow_read_state = _capture_slow_read_before()
                    _slow_ru_before, _slow_io_before = _collect_rusage_and_io_snapshots()
                if lane._lane == "UNET":
                    lane._trace.emit(
                        "unet_load_torch_file_start",
                        phase=lane._phase,
                        metadata={"lane": lane._lane, "path_hash": stable_hash(str(ckpt))[:16]},
                    )
        try:
            return original(ckpt, safe_load=safe_load, device=device, return_metadata=return_metadata)
        finally:
            after = _torch_file_depth.get()
            _torch_file_depth.set(after - 1)
            if before == 0:
                lane = _ACTIVE_LANE_TRACE.get()
                if lane is not None:
                    lane.read_end()
                    _read_dur_ms = round((time.monotonic_ns() - _read_outer_ns) / 1_000_000, 3) if _read_outer_ns else 0.0
                    lane._on_read_completed(read_duration_ms=_read_dur_ms)
                    if lane._lane == "CLIP" and _slow_read_state is not None:
                        _after_mono = time.monotonic_ns()
                        _after_tt = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
                        _after_pt = time.process_time_ns() if hasattr(time, "process_time_ns") else None
                        _after_tid = _capture_tid()
                        _elapsed = round((_after_mono - _slow_read_state.mono_ns) / 1_000_000, 3)
                        if _elapsed >= _SLOW_READ_THRESHOLD_MS:
                            _slow_ru_after, _slow_io_after = _collect_rusage_and_io_snapshots()
                            _request_trace = _ACTIVE_REQUEST_TRACE.get()
                            _emit_slow_read_line(
                                owner="CLIP",
                                loader_type="load_torch_file",
                                path_str=str(ckpt) if ckpt else "",
                                request_id=str(_request_trace.request_id) if _request_trace is not None else "",
                                restore_session_id=_LATEST_RESTORE_SESSION_ID,
                                restored_instance_id=_LATEST_RESTORED_INSTANCE_ID,
                                before=_slow_read_state,
                                after_mono_ns=_after_mono,
                                after_thread_time_ns=_after_tt,
                                after_process_time_ns=_after_pt,
                                after_tid=_after_tid,
                                before_rusage=_slow_ru_before,
                                after_rusage=_slow_ru_after,
                                before_io=_slow_io_before,
                                after_io=_slow_io_after,
                            )
                    if lane._lane == "UNET":
                        lane._trace.emit(
                            "unet_load_torch_file_end",
                            phase=lane._phase,
                            metadata={"lane": lane._lane, "path_hash": stable_hash(str(ckpt))[:16]},
                        )
                    # Emit page-fault deltas for CLIP/UNET page-in after first access
                    if _pf_before is not None and lane._lane in ("CLIP", "UNET"):
                        _pf_after = _PageFaultSnapshot.now()
                        _delta = _pagefault_delta(_pf_before, _pf_after)
                        _metric_name = "clip_snapshot_pagein_ms" if lane._lane == "CLIP" else "unet_snapshot_pagein_ms"
                        lane._trace.emit(
                            _metric_name.replace("_ms", ""),
                            phase=lane._phase,
                            metadata={
                                "lane": lane._lane,
                                "major_faults": _delta["major_faults"],
                                "minor_faults": _delta["minor_faults"],
                                "duration_ms": _read_dur_ms if _read_outer_ns else 0.0,
                            },
                        )
    wrapper._comfy_modal_read_wrapper = True  # sentinel for idempotence
    return wrapper


def _make_gpu_loader_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``comfy.model_management.load_models_gpu`` to emit commit events.

    Reentrancy-safe.  Emits ``gpu_lane_wait_start/end`` using the real
    ``_MUTATION_LANE`` (non-zero when contention exists) so Phase-2
    wait durations are truthful.  ``gpu_commit_start/end`` bracket the
    actual call with full metadata (restore IDs, model identity,
    caller classification, wall/thread CPU durations).
    """

    @functools.wraps(original)
    def wrapper(models, memory_required=0, force_patch_weights=False,
                minimum_memory_required=None, force_full_load=False):
        before = _gpu_depth.get()
        _gpu_depth.set(before + 1)
        _graph_start_ns = 0
        _graph_thread_start_ns = None
        _caller = "not_observed"
        _wrapper_status = "installed"
        _lane_start_ns = 0
        _lane_thread_start_ns = None
        _model_identity_hash = ""
        _pf_h2d_before: _PageFaultSnapshot | None = None
        _h2d_metric_name: str = ""
        if before == 0:
            count = _gpu_request_call_count_var.get()
            _gpu_request_call_count_var.set(count + 1)
            lane = _ACTIVE_LANE_TRACE.get()
            request_trace = _ACTIVE_REQUEST_TRACE.get()
            _graph_start_ns = time.monotonic_ns()
            _graph_thread_start_ns = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
            if lane is not None and lane._lane == "UNET":
                _caller = "background_unet_preparation"
            elif lane is not None and lane._lane == "CLIP":
                _caller = "restore_clip_preparation"
            elif lane is not None and lane._lane == "VAE":
                _caller = "restore_vae_preparation"
            elif lane is None and request_trace is not None:
                try:
                    import inspect as _inspect
                    _frames = " ".join(frame.function.lower() for frame in _inspect.stack(context=0)[:12])
                    if "sampler" in _frames:
                        _caller = "sampler_setup"
                    else:
                        _caller = "graph_model_loading"
                except Exception:
                    _caller = "graph_model_loading"
                _model_identity_hash = stable_hash([type(model).__module__ + "." + type(model).__qualname__ for model in models])[:16]
                request_trace.emit("graph_gpu_load_start", phase="execution", metadata={
                    "model_identity_hash": _model_identity_hash,
                    "memory_required": memory_required,
                    "force_patch_weights": force_patch_weights,
                    "force_full_load": force_full_load,
                    "caller_classification": _caller,
                    "gpu_wrapper_status": _wrapper_status,
                    "gpu_request_invocation_count": _gpu_request_call_count_var.get(),
                    "restore_session_id": _LATEST_RESTORE_SESSION_ID,
                    "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
                })
            # Always-on UNET first-CUDA demand start:
            # Record the monotonic_ns when load_models_gpu is first called
            # for a registered UNET in this request, regardless of lane state.
            # Previously this was inside `elif lane is None` so lane-owned
            # calls (e.g. background restore) or any non-None lane during
            # request execution would skip demand tracking.
            # Must stay inside `if before == 0:` scope.
            if request_trace is not None and _has_registered_unet_in_models(models):
                set_unet_gpu_demand_start(request_trace.request_id, time.monotonic_ns())
                request_trace.emit("unet_gpu_demand_start", metadata={
                    "request_id": request_trace.request_id,
                    "caller_classification": _caller,
                })
            if lane is None and request_trace is None:
                # Installed wrapper called outside any lane/request scope
                _caller = "not_observed"
                global _not_observed_gpu_calls
                _not_observed_gpu_calls += 1
            if lane is not None:
                lane._on_gpu_commit_about_to_start()
                _get_mutation_lane().acquire(lane._lane if lane else None)
                lane.gpu_lane_wait_start()
                lane.gpu_lane_wait_end()
                # Capture page-fault snapshot before H2D commit
                if _PAGEFAULT_TRACKING:
                    _pf_h2d_before = _PageFaultSnapshot.now()
                    _h2d_metric_name = "clip_h2d_ms" if lane._lane == "CLIP" else "unet_h2d_ms"
                # Compute metadata for lane-owned commit events
                _lane_start_ns = time.monotonic_ns()
                _lane_thread_start_ns = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
                _model_identity_hash = stable_hash([type(model).__module__ + "." + type(model).__qualname__ for model in models])[:16]
                lane.gpu_commit_start(
                    request_id=str(request_trace.request_id) if request_trace is not None else "",
                    restore_session_id=_LATEST_RESTORE_SESSION_ID,
                    restored_instance_id=_LATEST_RESTORED_INSTANCE_ID,
                    model_identity_hash=_model_identity_hash,
                    memory_required=memory_required,
                    force_patch_weights=force_patch_weights,
                    force_full_load=force_full_load,
                    caller_classification=_caller,
                    gpu_wrapper_status=_wrapper_status,
                    gpu_request_invocation_count=_gpu_request_call_count_var.get(),
                )
        _diag_ok = False
        try:
            _retval = original(models, memory_required=memory_required,
                               force_patch_weights=force_patch_weights,
                               minimum_memory_required=minimum_memory_required,
                               force_full_load=force_full_load)
            _diag_ok = True
            return _retval
        finally:
            after = _gpu_depth.get()
            _gpu_depth.set(after - 1)
            if before == 0:
                lane = _ACTIVE_LANE_TRACE.get()
                request_trace = _ACTIVE_REQUEST_TRACE.get()
                if lane is not None:
                    _lane_end_ns = time.monotonic_ns()
                    _lane_thread_end_ns = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
                    # Emit H2D page-fault deltas for lane-owned GPU commits
                    if _pf_h2d_before is not None and _h2d_metric_name:
                        _pf_h2d_after = _PageFaultSnapshot.now()
                        _delta = _pagefault_delta(_pf_h2d_before, _pf_h2d_after)
                        lane._trace.emit(
                            _h2d_metric_name.replace("_ms", ""),
                            phase=lane._phase,
                            metadata={
                                "lane": lane._lane,
                                "major_faults": _delta["major_faults"],
                                "minor_faults": _delta["minor_faults"],
                                "duration_ms": round((_lane_end_ns - _lane_start_ns) / 1_000_000, 3),
                                "caller_classification": _caller,
                            },
                        )
                    lane.gpu_commit_end(
                        host_wall_duration_ms=round((_lane_end_ns - _lane_start_ns) / 1_000_000, 3),
                        thread_cpu_duration_ms=round((_lane_thread_end_ns - _lane_thread_start_ns) / 1_000_000, 3) if _lane_thread_end_ns is not None and _lane_thread_start_ns is not None else None,
                        request_id=str(request_trace.request_id) if request_trace is not None else "",
                        restore_session_id=_LATEST_RESTORE_SESSION_ID,
                        restored_instance_id=_LATEST_RESTORED_INSTANCE_ID,
                        model_identity_hash=_model_identity_hash,
                        memory_required=memory_required,
                        force_patch_weights=force_patch_weights,
                        force_full_load=force_full_load,
                        caller_classification=_caller,
                        gpu_wrapper_status=_wrapper_status,
                        gpu_request_invocation_count=_gpu_request_call_count_var.get(),
                    )
                    _get_mutation_lane().release(lane._lane if lane else None)
                elif request_trace is not None:
                    _thread_end_ns = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
                    request_trace.emit("graph_gpu_load_end", phase="execution", metadata={
                        "host_wall_duration_ms": round((time.monotonic_ns() - _graph_start_ns) / 1_000_000, 3),
                        "thread_cpu_duration_ms": round((_thread_end_ns - _graph_thread_start_ns) / 1_000_000, 3) if _thread_end_ns is not None and _graph_thread_start_ns is not None else None,
                        "caller_classification": _caller,
                        "gpu_wrapper_status": _wrapper_status,
                        "gpu_request_invocation_count": _gpu_request_call_count_var.get(),
                        "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
                        "restore_session_id": _LATEST_RESTORE_SESSION_ID,
                        "model_identity_hash": _model_identity_hash,
                        "memory_required": memory_required,
                        "force_patch_weights": force_patch_weights,
                        "force_full_load": force_full_load,
                    })
                if _diag_ok:
                    emit_post_load_models_gpu_event(models)
                    # load_models_gpu duration measurement (complementary to the
                    # forward-probe-based unet_first_cuda_op emitted from the
                    # actual diffusion model forward).
                    if _caller in ("graph_model_loading", "sampler_setup"):
                        _op_duration_ms: float | None = None
                        if _lane_start_ns:
                            _op_duration_ms = round((time.monotonic_ns() - _lane_start_ns) / 1_000_000, 3)
                        elif _graph_start_ns:
                            _op_duration_ms = round((time.monotonic_ns() - _graph_start_ns) / 1_000_000, 3)
                        if _op_duration_ms is not None:
                            _rt = _ACTIVE_REQUEST_TRACE.get()
                            if _rt is not None:
                                _rt.emit(
                                    "load_models_gpu_duration",
                                    phase="execution",
                                    metadata={
                                        "caller_classification": _caller,
                                        "duration_ms": _op_duration_ms,
                                        "gpu_request_invocation_count": _gpu_request_call_count_var.get(),
                                        "model_identity_hash": _model_identity_hash,
                                        "memory_required": memory_required,
                                    },
                                )
    wrapper._comfy_modal_gpu_wrapper = True
    return wrapper


# ── Deep-diagnostic safetensors/torch.load decomposition wrappers ───
# Only active when:
#   1. _DIAGNOSTIC_FLAG is True
#   2. The calling thread's _DEEP_TARGET_PATH is non-empty AND matches
#      the file being accessed (avoid logging unrelated model loads)
#   3. The active lane trace is UNET
# These are globally installed but filtered by thread-local path, so
# unrelated file activity is never logged.


class _SafeOpenProxy:
    """Delegating proxy for safetensors.safe_open that wraps get_tensor
    for aggregate diagnostics without mutating the native C-extension object.
    _orig_gt(k) is called exactly once per requested tensor key.
    """
    def __init__(self, wrapped, orig_gt, count_agg, bytes_agg):
        object.__setattr__(self, "_wrapped", wrapped)
        object.__setattr__(self, "_orig_gt", orig_gt)
        object.__setattr__(self, "_count_agg", count_agg)
        object.__setattr__(self, "_bytes_agg", bytes_agg)

    def __getattr__(self, name):
        if name == "get_tensor":
            return lambda k: self._proxy_get_tensor(k)
        return getattr(self._wrapped, name)

    def _proxy_get_tensor(self, k):
        lane2 = _ACTIVE_LANE_TRACE.get()
        _start_ns = 0
        if lane2 is not None and lane2._lane == "UNET" and _DIAGNOSTIC_FLAG:
            _start_ns = time.monotonic_ns()
        tensor = self._orig_gt(k)
        if lane2 is not None and lane2._lane == "UNET" and _DIAGNOSTIC_FLAG and _start_ns:
            self._count_agg[0] += 1
            try:
                self._bytes_agg[0] += tensor.numel() * tensor.element_size()
            except Exception:
                pass
        return tensor

    def __enter__(self):
        try:
            return self._wrapped.__enter__()
        except AttributeError:
            return self

    def __exit__(self, *exc):
        lane2 = _ACTIVE_LANE_TRACE.get()
        if lane2 is not None:
            lane2._trace.emit("unet_tensor_materialize_aggregated", phase="restore", metadata={
                "tensor_count": self._count_agg[0],
                "total_bytes": self._bytes_agg[0],
            })
        return self._wrapped.__exit__(*exc) if hasattr(self._wrapped, "__exit__") else None

    def keys(self):
        return self._wrapped.keys()


def _make_safetensors_open_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``safetensors.safe_open`` to emit open/parse/materialize stages.

    Uses a reentrancy guard and thread-local path filtering.  Emits:
    - ``unet_safetensors_open_start/end`` for the ``safe_open()`` call itself
    - ``unet_safetensors_parse_start/end`` for the ``f.keys()`` header parse
    - ``unet_tensor_materialize_start/end`` around ``f.get_tensor()`` calls
    When the safetensors library does not expose separable boundaries, emits
    ``unet_safetensors_load_combined_start/end`` with ``stage_split_available=false``.
    """

    @functools.wraps(original)
    def wrapper(file, framework="pt", device="cpu", **kwargs):
        before = _deep_st_depth.get()
        _deep_st_depth.set(before + 1)
        lane = _ACTIVE_LANE_TRACE.get()
        target_path = _DEEP_TARGET_PATH.get()
        _outer = (before == 0)
        _eligible = (_outer and _DIAGNOSTIC_FLAG and lane is not None
                     and lane._lane == "UNET" and target_path
                     and (isinstance(file, str) and target_path in file))
        _result = None
        if _eligible:
            lane._trace.emit("unet_safetensors_open_start", phase="restore",
                             metadata={"path": str(file)[-80:]})
        try:
            _result = original(file, framework=framework, device=device, **kwargs)
            if _eligible and _outer:
                lane._trace.emit("unet_safetensors_open_end", phase="restore")
                # Check if the safetensors object has separable keys()
                _stage_split = (_result is not None
                                and callable(getattr(_result, "keys", None))
                                and callable(getattr(_result, "get_tensor", None)))
                if _stage_split:
                    lane._trace.emit("unet_safetensors_parse_start", phase="restore")
                    try:
                        _keys = list(_result.keys())
                        lane._trace.emit("unet_safetensors_parse_end", phase="restore",
                                         metadata={"tensor_count": len(_keys),
                                                   "stage_split_available": True})
                    except Exception:
                        lane._trace.emit("unet_safetensors_parse_end", phase="restore",
                                         metadata={"stage_split_available": False})
                    # Return a delegating proxy instead of mutating the native
                    # safe_open object (C-extension — attributes are read-only).
                    _tensor_count_agg = [0]
                    _tensor_bytes_agg = [0]
                    _orig_get_tensor = _result.get_tensor

                    _result = _SafeOpenProxy(_result, _orig_get_tensor,
                                             _tensor_count_agg, _tensor_bytes_agg)
                else:
                    lane._trace.emit("unet_safetensors_load_combined_start", phase="restore",
                                     metadata={"stage_split_available": False})
                    lane._trace.emit("unet_safetensors_load_combined_end", phase="restore")
            return _result
        finally:
            after = _deep_st_depth.get()
            _deep_st_depth.set(after - 1)
    wrapper._comfy_modal_deep_st_wrapper = True
    return wrapper


def _make_torch_load_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``torch.load`` to emit combined load event for non-safetensors files.

    Thread-local path filtering.  Emits ``unet_load_torch_file_start/end``.
    """

    @functools.wraps(original)
    def wrapper(f, map_location=None, weights_only=True, **kwargs):
        before = _deep_tl_depth.get()
        _deep_tl_depth.set(before + 1)
        lane = _ACTIVE_LANE_TRACE.get()
        target_path = _DEEP_TARGET_PATH.get()
        _outer = (before == 0)
        _file_str = str(getattr(f, "name", f)) if not isinstance(f, str) else str(f)
        _eligible = (_outer and _DIAGNOSTIC_FLAG and lane is not None
                     and lane._lane == "UNET" and target_path
                     and target_path in _file_str)
        if _eligible:
            lane._trace.emit("unet_load_torch_file_start", phase="restore",
                             metadata={"path": _file_str[-80:]})
        try:
            return original(f, map_location=map_location, weights_only=weights_only, **kwargs)
        finally:
            after = _deep_tl_depth.get()
            _deep_tl_depth.set(after - 1)
            if _eligible and _outer:
                lane._trace.emit("unet_load_torch_file_end", phase="restore")
    wrapper._comfy_modal_deep_tl_wrapper = True
    return wrapper


def _make_clip_load_wrapper(original):
    import functools as _ft
    @_ft.wraps(original)
    def wrapper(*args, **kwargs):
        before = _clip_depth.get()
        _clip_depth.set(before + 1)
        lane = _ACTIVE_LANE_TRACE.get()
        emit = (before == 0 and lane is not None and lane._lane == "CLIP")
        _outer_start_ns = time.monotonic_ns() if emit else 0
        _prior_children = _clip_cpu_prepare_children.get()
        _result = None
        if emit:
            _clip_cpu_prepare_children.set([])
            lane._trace.emit("clip_load_call_start", phase="restore", metadata={
                "lane": lane._lane,
            })
        try:
            _result = original(*args, **kwargs)
            return _result
        finally:
            after = _clip_depth.get()
            _clip_depth.set(after - 1)
            if emit:
                _outer_dur_ms = round((time.monotonic_ns() - _outer_start_ns) / 1_000_000, 3)
                _children = _clip_cpu_prepare_children.get() or []
                _children_total = round(sum(c[1] for c in _children), 3)
                # Signed residual — allow negative when children exceed total
                _residual = round(_outer_dur_ms - _children_total, 3)
                # Determine status from read count match
                _mismatch = (lane._actual_read_count != lane.expected_read_count
                             if lane.expected_read_count > 0 else False)
                _end_status = "read_count_mismatch" if _mismatch else "ok"
                if _children_total > _outer_dur_ms:
                    _end_status = "overlap_error"
                # ── Cache publication observation ────────────────
                if _result is not None:
                    _patcher = getattr(_result, "patcher", None)
                    if _patcher is not None:
                        _cpi = getattr(_patcher, "cached_patcher_init", None)
                        if _cpi is not None:
                            lane._trace.emit("clip_cache_publish", phase="restore", metadata={
                                "cache_type": "cached_patcher_init",
                                "clip_cpu_prepare_total_ms": _outer_dur_ms,
                            })
                _clip_cpu_prepare_children.set(_prior_children)
                # clip_file_read_total_ms from per-lane read-duration accumulator.
                _clip_read_raw = lane._clip_read_total_ms
                _clip_file_read = round(_clip_read_raw, 3) if _clip_read_raw else None
                _clip_post_read_cpu = (round(max(0.0, _outer_dur_ms - _clip_read_raw), 3)
                                       if _clip_read_raw else None)
                lane._trace.emit("clip_load_call_end", phase="restore", metadata={
                    "lane": lane._lane,
                    "clip_load_call_total_ms": _outer_dur_ms,
                    "clip_file_read_total_ms": _clip_file_read,
                    "clip_post_read_cpu_total_ms": _clip_post_read_cpu,
                    "status": _end_status,
                })
                # post_read_total is None when _on_read_completed never fired
                _post_read_total = _outer_dur_ms if lane._cpu_prepare_started else None
                lane._trace.emit("clip_cpu_prepare_end", phase="restore", metadata={
                    "lane": lane._lane,
                    "clip_cpu_prepare_total_ms": _post_read_total,
                    "children": [(name, dur) for name, dur in _children],
                    "clip_cpu_prepare_measured_children_ms": _children_total,
                    "clip_cpu_prepare_residual_ms": _residual,
                    "clip_file_read_total_ms": _clip_file_read,
                    "status": _end_status,
                })
                # Extract named children from trace events for the summary
                _evts = lane._trace.events
                _named_map: dict[str, float] = {}
                for _ev in _evts:
                    _en = _ev.name
                    _meta = getattr(_ev, "metadata", None) or {}
                    _dur = _meta.get("duration_ms")
                    if _dur is None:
                        continue
                    # Match clip_*_end events, handling double prefix
                    if _en.endswith("_end") and "clip_" in _en:
                        # Extract base name after clip_ prefix(es)
                        _base = _en.replace("clip_clip_", "clip_", 1)
                        if _base.startswith("clip_"):
                            _short = _base[len("clip_"):-len("_end")]
                        else:
                            _short = _base[:-len("_end")]
                        _named_map[_short] = (_named_map.get(_short, 0) or 0) + _dur
                    # Also match clip_clip_ double-prefix (already handled above)
                # Map to named fields
                _known_fields = {
                    "load_text_encoder_state_dicts": "load_text_encoder_state_dicts_ms",
                    "detect_te_model": "detect_te_model_ms",
                    "text_transformers_convert": "state_dict_conversion_ms",
                    "clip_text_transformers_convert": "state_dict_conversion_ms",
                    "constructor": "clip_constructor_ms",
                    "model_patcher_constructor": "model_patcher_ms",
                    "cond_stage_model_init": "cond_stage_model_init_ms",
                    "tokenizer_init": "tokenizer_init_ms",
                    "load_sd_weights": "load_sd_weights_ms",
                }
                _s = lambda k: _named_map.get(k)
                # double-prefix variant also maps to state_dict_conversion
                _sd_contrib = 0.0
                for _k in ("text_transformers_convert", "clip_text_transformers_convert", "convert_old_quants"):
                    _sd_contrib += _named_map.get(_k, 0) or 0
                if _sd_contrib:
                    _named_map["state_dict_conversion"] = _sd_contrib
                # ── Compute constructor residual ────────────────────
                _ctor_ms = _named_map.get("constructor")
                _csm_init = _named_map.get("cond_stage_model_init")
                _tok_init = _named_map.get("tokenizer_init")
                _lsd_w = _named_map.get("load_sd_weights")
                _mp_ms = _named_map.get("model_patcher_constructor")
                _ctor_residual: float | None = None
                if _ctor_ms is not None:
                    _known_ctor = [v for v in (_csm_init, _tok_init, _lsd_w, _mp_ms) if v is not None]
                    _ctor_residual = round(_ctor_ms - sum(_known_ctor), 3) if _known_ctor else None
                _emit_clip_cpu_children_summary(
                    post_read_total_ms=_post_read_total,
                    file_read_total_ms=_clip_file_read,
                    children=_children,
                    load_text_encoder_state_dicts_ms=_named_map.get("load_text_encoder_state_dicts"),
                    detect_te_model_ms=_named_map.get("detect_te_model"),
                    state_dict_conversion_ms=_named_map.get("state_dict_conversion"),
                    clip_constructor_ms=_named_map.get("constructor"),
                    cond_stage_model_init_ms=_named_map.get("cond_stage_model_init"),
                    tokenizer_init_ms=_named_map.get("tokenizer_init"),
                    load_sd_weights_ms=_named_map.get("load_sd_weights"),
                    model_patcher_ms=_named_map.get("model_patcher_constructor"),
                    constructor_residual_ms=_ctor_residual,
                    cache_publish_ms=_named_map.get("cache_publish"),
                    measured_children_ms=_children_total,
                    residual_ms=_residual,
                    status=_end_status,
                )
    wrapper._comfy_modal_clip_wrapper = True
    return wrapper


def _make_clip_subfn_wrapper(short_name, original, category):
    import functools as _ft
    @_ft.wraps(original)
    def wrapper(*args, **kwargs):
        lane = _ACTIVE_LANE_TRACE.get()
        emit = (lane is not None and lane._lane == "CLIP")
        _fn_start_ns = time.monotonic_ns() if emit else 0
        if emit:
            lane._trace.emit("clip_" + short_name + "_start", phase="restore", metadata={"category": category})
        _before_depth = _clip_subfn_depth.get()
        _clip_subfn_depth.set(_before_depth + 1)
        try:
            return original(*args, **kwargs)
        finally:
            _after_depth = _clip_subfn_depth.get()
            _clip_subfn_depth.set(_after_depth - 1)
            if emit:
                _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
                lane._trace.emit("clip_" + short_name + "_end", phase="restore", metadata={
                    "category": category, "duration_ms": _dur_ms})
                # Only direct children (depth=0 before call) contribute to measured sum
                if _before_depth == 0:
                    _children = _clip_cpu_prepare_children.get()
                    if _children is not None:
                        _children.append((short_name, _dur_ms))
    setattr(wrapper, _SENTINEL_CLIP_SUBFN, True)
    return wrapper


class _ClipTargetProxy:
    """Shallow proxy around a CLIP target that intercepts ``.clip`` and
    ``.tokenizer`` attribute access, wrapping the retrieved callables with
    timing instrumentation.  All other attribute access passes through to
    the original target unchanged, preserving behavior.

    Only created when a CLIP constructor wrapper is active and the lane
    is CLIP.  A non-functional proxy (``copy.copy`` unavailable) falls
    back to the original target without failing the load.
    """

    def __init__(self, original_target: Any, lane_trace: Any) -> None:
        object.__setattr__(self, "_original_target", original_target)
        # Accept ModelLaneTrace or RuntimeTrace; extract _trace for emit()
        object.__setattr__(self, "_trace",
                           getattr(lane_trace, "_trace", lane_trace))

    def __getattr__(self, name: str) -> Any:
        if name == "clip":
            return self._wrap_clip()
        elif name == "tokenizer":
            return self._wrap_tokenizer()
        return getattr(self._original_target, name)

    def _wrap_clip(self) -> Any:
        orig_clip = self._original_target.clip
        trace = self._trace

        @functools.wraps(orig_clip)
        def _timed_clip(*args: Any, **kwargs: Any) -> Any:
            trace.emit("clip_cond_stage_model_init_start", phase="restore")
            _start_ns = time.monotonic_ns()
            try:
                return orig_clip(*args, **kwargs)
            finally:
                _dur = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
                trace.emit("clip_cond_stage_model_init_end", phase="restore",
                           metadata={"duration_ms": _dur})
        return _timed_clip

    def _wrap_tokenizer(self) -> Any:
        orig_tokenizer = self._original_target.tokenizer
        trace = self._trace

        @functools.wraps(orig_tokenizer)
        def _timed_tokenizer(*args: Any, **kwargs: Any) -> Any:
            trace.emit("clip_tokenizer_init_start", phase="restore")
            _start_ns = time.monotonic_ns()
            try:
                return orig_tokenizer(*args, **kwargs)
            finally:
                _dur = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
                trace.emit("clip_tokenizer_init_end", phase="restore",
                           metadata={"duration_ms": _dur})
        return _timed_tokenizer


def _make_clip_load_sd_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``comfy.sd.CLIP.load_sd`` with timing instrumentation.

    Only emits ``clip_load_sd_weights_start/end`` events when a CLIP
    constructor wrapper is active (``_clip_constructor_depth > 0``) AND
    the active lane is CLIP.  Outside the constructor, the wrapper
    transparently forwards with zero overhead.

    Sentinel-guarded for idempotent global install.
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self: Any, sd: Any, full_model: bool = False) -> Any:
        lane = _ACTIVE_LANE_TRACE.get()
        emit = (lane is not None and lane._lane == "CLIP"
                and _clip_constructor_depth.get() > 0)
        _start_ns = time.monotonic_ns() if emit else 0
        if emit:
            lane._trace.emit("clip_load_sd_weights_start", phase="restore")
        try:
            return original(self, sd, full_model=full_model)
        finally:
            if emit:
                _dur = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
                lane._trace.emit("clip_load_sd_weights_end", phase="restore",
                                 metadata={"duration_ms": _dur})
    setattr(wrapper, _SENTINEL_CLIP_LOAD_SD, True)
    return wrapper


def _make_clip_constructor_wrapper(original):
    """Wrap ``comfy.sd.CLIP.__init__`` to emit ``clip_constructor_start/end``
    and proxy ``target.clip`` / ``target.tokenizer`` + ``self.load_sd`` for
    truthful live child attribution (``clip_cond_stage_model_init``,
    ``clip_tokenizer_init``, ``clip_load_sd_weights``).

    Only active when ``_ACTIVE_LANE_TRACE`` is set AND the current lane
    is ``CLIP``.  Reentrancy-safe via ``_clip_constructor_depth``.
    Emitted spans are NOT recorded into ``_clip_cpu_prepare_children`` —
    they are nested inside ``load_text_encoder_state_dicts`` which is the
    direct measured owner.
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, *args: Any, **kwargs: Any) -> None:
        before = _clip_constructor_depth.get()
        _clip_constructor_depth.set(before + 1)
        lane = _ACTIVE_LANE_TRACE.get()
        emit = (before == 0 and lane is not None and lane._lane == "CLIP")
        _fn_start_ns = time.monotonic_ns() if emit else 0

        if emit:
            # ── Proxy target.clip / target.tokenizer ──────────────
            _original_target = args[0] if args else kwargs.get("target")
            if _original_target is not None:
                try:
                    import copy as _copy
                    _proxy = _ClipTargetProxy(_original_target, lane)
                    if args:
                        _new_args = list(args)
                        _new_args[0] = _proxy
                        args = tuple(_new_args)
                    else:
                        kwargs = dict(kwargs)
                        kwargs["target"] = _proxy
                except Exception:
                    pass  # Fall back to original target without failing
            lane._trace.emit("clip_constructor_start", phase="restore")
        try:
            return original(self, *args, **kwargs)
        finally:
            after = _clip_constructor_depth.get()
            _clip_constructor_depth.set(after - 1)
            if emit:
                _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
                lane._trace.emit("clip_constructor_end", phase="restore", metadata={
                    "duration_ms": _dur_ms,
                })
                # NOT recorded into _clip_cpu_prepare_children — nested inside
                # load_text_encoder_state_dicts which is the direct measured owner.
    setattr(wrapper, _SENTINEL_CLIP_CONSTRUCTOR, True)
    return wrapper


# ── Shared convert_old_quants wrapper ───────────────────────────────
# Lane-aware wrapper installed once for comfy.utils.convert_old_quants.
# Emits either clip_convert_old_quants_* or unet_convert_old_quants_*
# depending on the active lane.  Children are recorded into the
# appropriate per-lane list for residual/non-overlap computation.

_shared_convert_old_quants_installed: bool = False


def _make_convert_old_quants_wrapper(original):
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        lane = _ACTIVE_LANE_TRACE.get()
        if lane is None:
            return original(*args, **kwargs)
        _fn_start_ns = time.monotonic_ns()
        if lane._lane == "CLIP":
            lane._trace.emit("clip_convert_old_quants_start", phase="restore", metadata={"category": "utils"})
        elif lane._lane == "UNET":
            lane._trace.emit("unet_convert_old_quants_start", phase="restore", metadata={"category": "utils"})
        try:
            return original(*args, **kwargs)
        finally:
            _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
            if lane._lane == "CLIP":
                lane._trace.emit("clip_convert_old_quants_end", phase="restore", metadata={
                    "category": "utils", "duration_ms": _dur_ms})
                # Only direct children (depth=0) contribute to measured sum
                if _clip_subfn_depth.get() == 0:
                    _children = _clip_cpu_prepare_children.get()
                    if _children is not None:
                        _children.append(("convert_old_quants", _dur_ms))
            elif lane._lane == "UNET":
                lane._trace.emit("unet_convert_old_quants_end", phase="restore", metadata={
                    "category": "utils", "duration_ms": _dur_ms})
                # Only direct children (nesting depth 0) contribute to measured sum
                if _unet_subfn_nesting_depth.get() == 0:
                    _children = _child_durations.get()
                    if _children is not None:
                        _children.append(("convert_old_quants", _dur_ms))
    setattr(wrapper, _SENTINEL_SHARED_COQ, True)
    return wrapper


def _install_shared_convert_old_quants_wrapper() -> str:
    """Install lane-aware wrapper on comfy.utils.convert_old_quants once."""
    global _shared_convert_old_quants_installed
    if _shared_convert_old_quants_installed:
        return "already_installed"
    mod = _get_live_module("comfy.utils")
    if mod is None:
        return "unavailable"
    original = getattr(mod, "convert_old_quants", None)
    if not callable(original):
        return "unavailable"
    if getattr(original, _SENTINEL_SHARED_COQ, False):
        _shared_convert_old_quants_installed = True
        return "already_installed"
    with _wrappers_lock:
        if _shared_convert_old_quants_installed:
            return "already_installed"
        if getattr(mod.convert_old_quants, _SENTINEL_SHARED_COQ, False):
            _shared_convert_old_quants_installed = True
            return "already_installed"
        mod.convert_old_quants = _make_convert_old_quants_wrapper(mod.convert_old_quants)
        _shared_convert_old_quants_installed = True
    return "installed"


# ── UNET model construction wrappers ────────────────────────────────
# Wrap ModelPatcher/CoreModelPatcher constructors and model.to() so
# model-construction children are captured in measured_direct_children_ms.


def _make_model_patcher_constructor_wrapper(original):
    """Wrap ``model_patcher.ModelPatcher().__init__`` (or subclass) with lane guard.

    Extends the existing UNET-only instrumentation to also emit named
    ``clip_model_patcher_constructor_start/end`` events when the active
    lane is CLIP.  CLIP-lane spans are NOT recorded into
    ``_clip_cpu_prepare_children`` — they are nested inside
    ``load_text_encoder_state_dicts`` which is the direct measured owner.
    UNET-lane spans are recorded into ``_child_durations`` as before.
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, *args: Any, **kwargs: Any) -> None:
        lane = _ACTIVE_LANE_TRACE.get()
        emit_unet = (lane is not None and lane._lane == "UNET")
        emit_clip = (lane is not None and lane._lane == "CLIP")
        _fn_start_ns = time.monotonic_ns() if (emit_unet or emit_clip) else 0
        if emit_unet:
            lane._trace.emit("unet_model_patcher_constructor_start", phase="restore")
        elif emit_clip:
            lane._trace.emit("clip_model_patcher_constructor_start", phase="restore")
        try:
            result = original(self, *args, **kwargs)
            # Install SAMPLER_SAMPLE wrapper via the shared helper.
            # The helper itself emits a concise exception-type line and returns
            # False on failure — never silently swallows installation failure.
            if hasattr(self, "model_options"):
                from comfymodal_runtime.runtime_executor import ensure_sampling_timing_wrapper
                ensure_sampling_timing_wrapper(self)
            # Register every ModelPatcher for UNET first-CUDA timing.
            # Idempotent: duplicate registrations for the same diffusion_model
            # are silently ignored by register_unet_forward_probe.
            try:
                from comfymodal_runtime.unet_forward_probe import register_unet_forward_probe as _reg_unet
                _reg_unet(self, source="model_patcher_constructor")
            except Exception:
                pass
            return result
        finally:
            if emit_unet:
                _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
                lane._trace.emit("unet_model_patcher_constructor_end", phase="restore", metadata={
                    "duration_ms": _dur_ms})
                _children = _child_durations.get()
                if _children is not None:
                    _children.append(("model_patcher_constructor", _dur_ms))
            elif emit_clip:
                _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
                lane._trace.emit("clip_model_patcher_constructor_end", phase="restore", metadata={
                    "duration_ms": _dur_ms})
                # NOT recorded into _clip_cpu_prepare_children — nested inside
                # load_text_encoder_state_dicts which is the direct measured owner.
    setattr(wrapper, _SENTINEL_MODEL_PATCHER, True)
    return wrapper


def _make_model_to_wrapper(original):
    """Wrap ``model.to(...)`` with UNET-lane guard for direct ownership measurement."""
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        lane = _ACTIVE_LANE_TRACE.get()
        emit = (lane is not None and lane._lane == "UNET")
        _fn_start_ns = time.monotonic_ns() if emit else 0
        if emit:
            lane._trace.emit("unet_model_to_start", phase="restore")
        try:
            return original(self, *args, **kwargs)
        finally:
            if emit:
                _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
                lane._trace.emit("unet_model_to_end", phase="restore", metadata={
                    "duration_ms": _dur_ms})
                _children = _child_durations.get()
                if _children is not None:
                    _children.append(("model_to", _dur_ms))
    setattr(wrapper, _SENTINEL_MODEL_TO, True)
    return wrapper


# ── ModelPatcher.load aggregate-timing wrappers (narrow timers) ──────
# Four narrow wrappers installed alongside existing core/model_patcher
# wrappers.  Only active during an active request trace AND outer
# ModelPatcher.load scope.  Produce one summary event on outer exit:
#   model_patcher_load_breakdown
# with wall_ms, thread_cpu_ms, process_cpu_ms for total, plus traversal,
# patch_weight (count/wall/process), cast (count/wall/process), and
# residual wall/process.


def _make_model_patcher_load_wrapper(original):
    """Wrap ModelPatcher.load / ModelPatcherDynamic.load with breakdown timing.

    Only emits ``model_patcher_load_breakdown`` when ``_ACTIVE_REQUEST_TRACE``
    is set and this is the outermost invocation.  Sets up a thread-local
    ``_model_patcher_breakdown`` dict consumed by the inner _load_list,
    patch_weight_to_device, and cast_to_device wrappers.
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, *args, **kwargs):
        before = _model_patcher_load_depth.get()
        _model_patcher_load_depth.set(before + 1)
        request_trace = _ACTIVE_REQUEST_TRACE.get()
        emit = (before == 0 and request_trace is not None)
        _breakdown = None
        if emit:
            _breakdown = {
                "outer_start_ns": time.monotonic_ns(),
                "outer_thread_start_ns": time.thread_time_ns() if hasattr(time, "thread_time_ns") else None,
                "outer_process_start_ns": time.process_time_ns() if hasattr(time, "process_time_ns") else None,
                "load_list_wall_ns": 0,
                "load_list_process_start_ns": None,
                "load_list_process_end_ns": None,
                "patch_weight_count": 0,
                "patch_weight_wall_ns": 0,
                "patch_weight_process_ns": 0,
                "cast_count": 0,
                "cast_wall_ns": 0,
                "cast_process_ns": 0,
            }
            _model_patcher_breakdown.set(_breakdown)
        try:
            return original(self, *args, **kwargs)
        finally:
            after = _model_patcher_load_depth.get()
            _model_patcher_load_depth.set(after - 1)
            if emit and _breakdown is not None:
                _outer_end_ns = time.monotonic_ns()
                _outer_thread_end_ns = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
                _outer_process_end_ns = time.process_time_ns() if hasattr(time, "process_time_ns") else None
                _wall_ms = round((_outer_end_ns - _breakdown["outer_start_ns"]) / 1_000_000, 3)
                _thread_ms = round((_outer_thread_end_ns - _breakdown["outer_thread_start_ns"]) / 1_000_000, 3) if _breakdown.get("outer_thread_start_ns") is not None and _outer_thread_end_ns is not None else None
                _process_ms = round((_outer_process_end_ns - _breakdown["outer_process_start_ns"]) / 1_000_000, 3) if _breakdown.get("outer_process_start_ns") is not None and _outer_process_end_ns is not None else None
                # Traversal (_load_list)
                _traversal_wall = round(_breakdown["load_list_wall_ns"] / 1_000_000, 3) if _breakdown["load_list_wall_ns"] else 0.0
                _traversal_process: float | None = None
                if _breakdown["load_list_process_start_ns"] is not None and _breakdown["load_list_process_end_ns"] is not None:
                    _traversal_process = round((_breakdown["load_list_process_end_ns"] - _breakdown["load_list_process_start_ns"]) / 1_000_000, 3)
                # Patch-weight aggregate
                _pw_wall = round(_breakdown["patch_weight_wall_ns"] / 1_000_000, 3) if _breakdown["patch_weight_wall_ns"] else 0.0
                _pw_process: float | None = None
                if _breakdown["patch_weight_process_ns"]:
                    _pw_process = round(_breakdown["patch_weight_process_ns"] / 1_000_000, 3)
                # Cast aggregate
                _cast_wall = round(_breakdown["cast_wall_ns"] / 1_000_000, 3) if _breakdown["cast_wall_ns"] else 0.0
                _cast_process: float | None = None
                if _breakdown["cast_process_ns"]:
                    _cast_process = round(_breakdown["cast_process_ns"] / 1_000_000, 3)
                # Residual
                _residual_wall = round(max(0.0, _wall_ms - _traversal_wall - _pw_wall), 3)
                _residual_process: float | None = None
                if _process_ms is not None and _traversal_process is not None and _pw_process is not None:
                    _residual_process = round(max(0.0, _process_ms - _traversal_process - _pw_process), 3)
                request_trace.emit("model_patcher_load_breakdown", phase="execution", metadata={
                    "request_id": str(request_trace.request_id),
                    "wall_ms": _wall_ms,
                    "thread_cpu_ms": _thread_ms,
                    "process_cpu_ms": _process_ms,
                    "traversal_wall_ms": _traversal_wall,
                    "traversal_process_cpu_ms": _traversal_process,
                    "patch_weight_count": _breakdown["patch_weight_count"],
                    "patch_weight_wall_ms": _pw_wall,
                    "patch_weight_process_cpu_ms": _pw_process,
                    "cast_count": _breakdown["cast_count"],
                    "cast_wall_ms": _cast_wall,
                    "cast_process_cpu_ms": _cast_process,
                    "residual_wall_ms": _residual_wall,
                    "residual_process_cpu_ms": _residual_process,
                })
                _model_patcher_breakdown.set(None)

    setattr(wrapper, _SENTINEL_MODEL_PATCHER_LOAD, True)
    return wrapper


def _make_model_patcher_load_list_wrapper(original):
    """Wrap ``ModelPatcher._load_list`` with wall/process timing.

    Only accumulates when ``_model_patcher_breakdown`` is set (inside outer
    ModelPatcher.load under request trace).
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, *args, **kwargs):
        _bd = _model_patcher_breakdown.get()
        if _bd is not None:
            _bd["load_list_process_start_ns"] = time.process_time_ns() if hasattr(time, "process_time_ns") else None
            _load_list_start_ns = time.monotonic_ns()
        try:
            return original(self, *args, **kwargs)
        finally:
            if _bd is not None:
                _bd["load_list_wall_ns"] = time.monotonic_ns() - _load_list_start_ns
                _bd["load_list_process_end_ns"] = time.process_time_ns() if hasattr(time, "process_time_ns") else None

    setattr(wrapper, _SENTINEL_MODEL_PATCHER_LOAD_LIST, True)
    return wrapper


def _make_model_patcher_patch_weight_wrapper(original):
    """Wrap ``ModelPatcher.patch_weight_to_device`` with count/wall/process aggregation.

    Accumulates into ``_model_patcher_breakdown`` when set (inside outer
    ModelPatcher.load under request trace).
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(self, key, device_to=None, inplace_update=False, return_weight=False, force_cast=False):
        _bd = _model_patcher_breakdown.get()
        if _bd is not None:
            _pw_start = time.monotonic_ns()
            _pw_process_start = time.process_time_ns() if hasattr(time, "process_time_ns") else None
        try:
            return original(self, key, device_to=device_to, inplace_update=inplace_update, return_weight=return_weight, force_cast=force_cast)
        finally:
            if _bd is not None:
                _bd["patch_weight_count"] += 1
                _bd["patch_weight_wall_ns"] += time.monotonic_ns() - _pw_start
                if _pw_process_start is not None:
                    _bd["patch_weight_process_ns"] += time.process_time_ns() - _pw_process_start

    setattr(wrapper, _SENTINEL_MODEL_PATCHER_PATCH_WEIGHT, True)
    return wrapper


def _make_cast_to_device_wrapper(original):
    """Wrap ``comfy.model_management.cast_to_device`` with count/wall/process aggregation.

    Only accumulates when ``_model_patcher_breakdown`` is set (inside outer
    ModelPatcher.load under request trace).  Installed on the live
    ``comfy.model_management`` module.
    """
    import functools as _ft

    @_ft.wraps(original)
    def wrapper(tensor, device, dtype, copy=False):
        _bd = _model_patcher_breakdown.get()
        if _bd is not None:
            _cast_start = time.monotonic_ns()
            _cast_process_start = time.process_time_ns() if hasattr(time, "process_time_ns") else None
        try:
            return original(tensor, device, dtype, copy=copy)
        finally:
            if _bd is not None:
                _bd["cast_count"] += 1
                _bd["cast_wall_ns"] += time.monotonic_ns() - _cast_start
                if _cast_process_start is not None:
                    _bd["cast_process_ns"] += time.process_time_ns() - _cast_process_start

    setattr(wrapper, _SENTINEL_CAST_TO_DEVICE, True)
    return wrapper


# ── Model patcher wrapper installer ─────────────────────────────────

_model_patcher_wrappers_installed: bool = False


def _install_model_patcher_wrappers(trace: RuntimeTrace | None = None) -> dict[str, str]:
    """Install constructor and model.to wrappers on live comfy.model_patcher module.

    Targets ModelPatcher and CoreModelPatcher constructors plus model.to().
    Idempotent via per-sentinel flags.
    """
    global _model_patcher_wrappers_installed
    if _model_patcher_wrappers_installed:
        return {}
    result: dict[str, str] = {}
    mp_mod = _get_live_module("comfy.model_patcher")
    if mp_mod is None:
        return {"model_patcher_wrappers": "unavailable"}

    # Wrap ModelPatcher.__init__
    _ModelPatcher_cls = getattr(mp_mod, "ModelPatcher", None)
    if _ModelPatcher_cls is not None:
        _orig_init = getattr(_ModelPatcher_cls, "__init__", None)
        if callable(_orig_init) and not getattr(_orig_init, _SENTINEL_MODEL_PATCHER, False):
            setattr(_ModelPatcher_cls, "__init__", _make_model_patcher_constructor_wrapper(_orig_init))
            result["ModelPatcher.__init__"] = "installed"
        else:
            result["ModelPatcher.__init__"] = "already_installed" if _orig_init else "unavailable"
    else:
        result["ModelPatcher.__init__"] = "unavailable"

    # Wrap CoreModelPatcher.__init__
    _CoreMP_cls = getattr(mp_mod, "CoreModelPatcher", None)
    if _CoreMP_cls is not None:
        _orig_init = getattr(_CoreMP_cls, "__init__", None)
        if callable(_orig_init) and not getattr(_orig_init, _SENTINEL_MODEL_PATCHER, False):
            setattr(_CoreMP_cls, "__init__", _make_model_patcher_constructor_wrapper(_orig_init))
            result["CoreModelPatcher.__init__"] = "installed"
        else:
            result["CoreModelPatcher.__init__"] = "already_installed" if _orig_init else "unavailable"

    # Wrap model.to() — installed on torch.nn.Module so it catches any model.to() call.
    _torch_mod = _get_live_module("torch")
    if _torch_mod is not None:
        _nn_mod = getattr(_torch_mod, "nn", None)
        if _nn_mod is not None:
            _Module_cls = getattr(_nn_mod, "Module", None)
            if _Module_cls is not None:
                _orig_to = getattr(_Module_cls, "to", None)
                if callable(_orig_to) and not getattr(_orig_to, _SENTINEL_MODEL_TO, False):
                    setattr(_Module_cls, "to", _make_model_to_wrapper(_orig_to))
                    result["nn.Module.to"] = "installed"
                else:
                    result["nn.Module.to"] = "already_installed" if _orig_to else "unavailable"

    # Wrap ModelPatcher.load (aggregate-timing breakdown)
    if _ModelPatcher_cls is not None:
        _orig_load = getattr(_ModelPatcher_cls, "load", None)
        if callable(_orig_load) and not getattr(_orig_load, _SENTINEL_MODEL_PATCHER_LOAD, False):
            setattr(_ModelPatcher_cls, "load", _make_model_patcher_load_wrapper(_orig_load))
            result["ModelPatcher.load"] = "installed"
        else:
            result["ModelPatcher.load"] = "already_installed" if _orig_load else "unavailable"

    # Wrap ModelPatcherDynamic.load
    _MPDynamic_cls = getattr(mp_mod, "ModelPatcherDynamic", None)
    if _MPDynamic_cls is not None:
        _orig_dyn_load = getattr(_MPDynamic_cls, "load", None)
        if callable(_orig_dyn_load) and not getattr(_orig_dyn_load, _SENTINEL_MODEL_PATCHER_LOAD, False):
            setattr(_MPDynamic_cls, "load", _make_model_patcher_load_wrapper(_orig_dyn_load))
            result["ModelPatcherDynamic.load"] = "installed"
        else:
            result["ModelPatcherDynamic.load"] = "already_installed" if _orig_dyn_load else "unavailable"

    # Wrap ModelPatcher._load_list (traversal aggregate)
    if _ModelPatcher_cls is not None:
        _orig_load_list = getattr(_ModelPatcher_cls, "_load_list", None)
        if callable(_orig_load_list) and not getattr(_orig_load_list, _SENTINEL_MODEL_PATCHER_LOAD_LIST, False):
            setattr(_ModelPatcher_cls, "_load_list", _make_model_patcher_load_list_wrapper(_orig_load_list))
            result["ModelPatcher._load_list"] = "installed"
        else:
            result["ModelPatcher._load_list"] = "already_installed" if _orig_load_list else "unavailable"

    # Wrap ModelPatcher.patch_weight_to_device (aggregate)
    if _ModelPatcher_cls is not None:
        _orig_pw = getattr(_ModelPatcher_cls, "patch_weight_to_device", None)
        if callable(_orig_pw) and not getattr(_orig_pw, _SENTINEL_MODEL_PATCHER_PATCH_WEIGHT, False):
            setattr(_ModelPatcher_cls, "patch_weight_to_device", _make_model_patcher_patch_weight_wrapper(_orig_pw))
            result["ModelPatcher.patch_weight_to_device"] = "installed"
        else:
            result["ModelPatcher.patch_weight_to_device"] = "already_installed" if _orig_pw else "unavailable"

    if trace:
        for comp, status in result.items():
            trace.emit("model_patcher_wrapper_install", phase="restore",
                       metadata={"component": comp, "status": status})
    _model_patcher_wrappers_installed = True
    return result


def _install_clip_load_sd_wrapper(sd_mod, trace=None):
    """Install CLIP.load_sd wrapper on live comfy.sd.CLIP class.

    Idempotent via sentinel.  Only emits ``clip_load_sd_weights_start/end``
    while a CLIP constructor is active (``_clip_constructor_depth > 0``).
    """
    global _clip_load_sd_wrapper_installed
    if _clip_load_sd_wrapper_installed:
        return "already_installed"
    CLIP_cls = getattr(sd_mod, "CLIP", None)
    if CLIP_cls is None:
        return "unavailable"
    _orig_load_sd = getattr(CLIP_cls, "load_sd", None)
    if not callable(_orig_load_sd):
        return "unavailable"
    if getattr(_orig_load_sd, _SENTINEL_CLIP_LOAD_SD, False):
        _clip_load_sd_wrapper_installed = True
        return "already_installed"
    with _wrappers_lock:
        if _clip_load_sd_wrapper_installed:
            return "already_installed"
        _check_load_sd = getattr(CLIP_cls, "load_sd", None)
        if getattr(_check_load_sd, _SENTINEL_CLIP_LOAD_SD, False):
            _clip_load_sd_wrapper_installed = True
            return "already_installed"
        setattr(CLIP_cls, "load_sd", _make_clip_load_sd_wrapper(_check_load_sd))
        _clip_load_sd_wrapper_installed = True
    if trace:
        trace.emit("clip_load_sd_wrapper_install", phase="restore",
                   metadata={"status": "installed"})
    return "installed"


def _install_clip_constructor_wrapper(sd_mod, trace=None):
    """Install CLIP.__init__ wrapper on live comfy.sd.CLIP class.

    Idempotent via sentinel.  Emits ``clip_constructor_start/end``
    named events that are NOT recorded into ``_clip_cpu_prepare_children``.
    Also installs the load_sd wrapper for child weight-load attribution.
    """
    global _clip_constructor_wrapper_installed
    if _clip_constructor_wrapper_installed:
        return "already_installed"
    CLIP_cls = getattr(sd_mod, "CLIP", None)
    if CLIP_cls is None:
        return "unavailable"
    _orig_init = getattr(CLIP_cls, "__init__", None)
    if not callable(_orig_init):
        return "unavailable"
    if getattr(_orig_init, _SENTINEL_CLIP_CONSTRUCTOR, False):
        _clip_constructor_wrapper_installed = True
        return "already_installed"
    with _wrappers_lock:
        if _clip_constructor_wrapper_installed:
            return "already_installed"
        _check_init = getattr(CLIP_cls, "__init__", None)
        if getattr(_check_init, _SENTINEL_CLIP_CONSTRUCTOR, False):
            _clip_constructor_wrapper_installed = True
            return "already_installed"
        setattr(CLIP_cls, "__init__", _make_clip_constructor_wrapper(_check_init))
        _clip_constructor_wrapper_installed = True
        # Also install load_sd wrapper for child weight-load attribution.
        _install_clip_load_sd_wrapper(sd_mod, trace=trace)
    if trace:
        trace.emit("clip_constructor_wrapper_install", phase="restore",
                   metadata={"status": "installed"})
    return "installed"


def _install_clip_wrapper(trace=None):
    global _clip_wrapper_installed
    if _clip_wrapper_installed:
        return "already_installed"
    sd_mod = _get_live_module("comfy.sd")
    if sd_mod is None:
        return "unavailable"
    original_fn = getattr(sd_mod, "load_clip", None)
    if not callable(original_fn):
        return "unavailable"
    if getattr(original_fn, _SENTINEL_CLIP, False):
        _clip_wrapper_installed = True
        return "already_installed"
    from threading import RLock as _RLock
    _cw_lock = _RLock()
    with _cw_lock:
        if _clip_wrapper_installed:
            return "already_installed"
        if getattr(sd_mod.load_clip, _SENTINEL_CLIP, False):
            _clip_wrapper_installed = True
            return "already_installed"
        sd_mod.load_clip = _make_clip_load_wrapper(sd_mod.load_clip)
        _clip_wrapper_installed = True
        _install_clip_subfn_wrappers(sd_mod)
        _install_clip_constructor_wrapper(sd_mod, trace=trace)
    if trace:
        trace.emit("clip_wrapper_install", phase="restore", metadata={"status": "installed"})
    return "installed"


_CLIP_DECOMPOSE_TARGETS = {
    "detect_te_model": ("comfy.sd", "detect_te_model", "sd"),
    "load_text_encoder_state_dicts": ("comfy.sd", "load_text_encoder_state_dicts", "sd"),
    "clip_text_transformers_convert": ("comfy.utils", "clip_text_transformers_convert", "utils"),
    # NOTE: convert_old_quants is installed via the shared lane-aware
    # _install_shared_convert_old_quants_wrapper so both CLIP and UNET
    # attribution remain active on the same live function.
}


def _install_clip_subfn_wrappers(sd_mod):
    result = {}
    # Install shared lane-aware convert_old_quants wrapper first.
    result["convert_old_quants"] = _install_shared_convert_old_quants_wrapper()
    for short_name, (mod_name, func_name, category) in _CLIP_DECOMPOSE_TARGETS.items():
        mod = _get_live_module(mod_name) if mod_name != "comfy.sd" else sd_mod
        if mod is None:
            result[short_name] = "unavailable"
            continue
        original = getattr(mod, func_name, None)
        if not callable(original):
            result[short_name] = "unavailable"
            continue
        if getattr(original, _SENTINEL_CLIP_SUBFN, False):
            result[short_name] = "already_installed"
            continue
        wrapper = _make_clip_subfn_wrapper(short_name, original, category)
        setattr(wrapper, _SENTINEL_CLIP_SUBFN, True)
        setattr(mod, func_name, wrapper)
        result[short_name] = "installed"
    return result


def _install_deep_diag_wrappers(*, safe_open_fn: Any = None, torch_load_fn: Any = None,
                                 trace: RuntimeTrace | None = None) -> dict[str, str]:
    """Install deep diagnostic wrappers on safetensors.safe_open and torch.load.

    Idempotent via sentinel flags.  Installs the wrapper onto the *live module
    object in sys.modules* so the wrapper intercepts real callers.  Thread-local
    ``_DEEP_TARGET_PATH`` + ``_ACTIVE_LANE_TRACE`` filtering ensures unrelated
    file activity is never logged.

    Returns ``{component: status}`` dict.  Only meaningful when
    ``_DIAGNOSTIC_FLAG`` is True at install time, but the wrappers themselves
    check the flag and path filter at call time.
    """
    global _deep_diag_wrappers_installed
    if _deep_diag_wrappers_installed:
        return {}
    result: dict[str, str] = {}
    if safe_open_fn is not None and callable(safe_open_fn):
        if not getattr(safe_open_fn, _SENTINEL_DEEP_ST, False):
            _wrapped = _make_safetensors_open_wrapper(safe_open_fn)
            # Install onto the live safetensors module in sys.modules
            _st_mod = _get_live_module("safetensors")
            if _st_mod is not None:
                setattr(_st_mod, "safe_open", _wrapped)
                result["safetensors.safe_open"] = "installed"
            else:
                result["safetensors.safe_open"] = "unavailable"
        else:
            result["safetensors.safe_open"] = "already_installed"
    if torch_load_fn is not None and callable(torch_load_fn):
        if not getattr(torch_load_fn, _SENTINEL_DEEP_TL, False):
            _wrapped = _make_torch_load_wrapper(torch_load_fn)
            # Install onto the live torch module in sys.modules
            _torch_mod = _get_live_module("torch")
            if _torch_mod is not None:
                setattr(_torch_mod, "load", _wrapped)
                result["torch.load"] = "installed"
            else:
                result["torch.load"] = "unavailable"
        else:
            result["torch.load"] = "already_installed"
    if trace:
        for comp, status in result.items():
            trace.emit("deep_diag_wrapper_install", phase="restore",
                       metadata={"component": comp, "status": status})
    _deep_diag_wrappers_installed = True
    return result


# ── Independent per-component installation ──────────────────────────


def _install_read_wrapper(*, utils_module: Any, trace: RuntimeTrace | None = None) -> str:
    """Install the ``load_torch_file`` wrapper on *utils_module*.

    Returns status ``"installed"``, ``"already_installed"``, or
    ``"unavailable"``.
    """
    global _read_wrapper_installed
    if _read_wrapper_installed:
        return "already_installed"
    func = getattr(utils_module, "load_torch_file", None)
    if not callable(func):
        return "unavailable"
    if getattr(func, _SENTINEL_READ, False):
        _read_wrapper_installed = True
        return "already_installed"
    with _wrappers_lock:
        if _read_wrapper_installed:
            return "already_installed"
        if getattr(utils_module.load_torch_file, _SENTINEL_READ, False):
            _read_wrapper_installed = True
            return "already_installed"
        utils_module.load_torch_file = _make_torch_file_wrapper(utils_module.load_torch_file)
        _read_wrapper_installed = True
    return "installed"


def _install_gpu_wrapper(*, mm_module: Any, trace: RuntimeTrace | None = None) -> str:
    """Install the ``load_models_gpu`` wrapper on *mm_module*.

    Returns status ``"installed"``, ``"already_installed"``, or
    ``"unavailable"``.
    """
    global _gpu_wrapper_installed
    if _gpu_wrapper_installed:
        return "already_installed"
    func = getattr(mm_module, "load_models_gpu", None)
    if not callable(func):
        return "unavailable"
    if getattr(func, _SENTINEL_GPU, False):
        _gpu_wrapper_installed = True
        return "already_installed"
    with _wrappers_lock:
        if _gpu_wrapper_installed:
            return "already_installed"
        if getattr(mm_module.load_models_gpu, _SENTINEL_GPU, False):
            _gpu_wrapper_installed = True
            return "already_installed"
        mm_module.load_models_gpu = _make_gpu_loader_wrapper(mm_module.load_models_gpu)
        _gpu_wrapper_installed = True
    return "installed"


_cast_to_device_wrapper_installed: bool = False


def _install_cast_to_device_wrapper(*, mm_module: Any, trace: RuntimeTrace | None = None) -> str:
    """Install the ``cast_to_device`` wrapper on *mm_module* (comfy.model_management).

    Idempotent via sentinel.  Wrapper aggregates count + wall/process time
    into ``_model_patcher_breakdown`` when set (inside outer ModelPatcher.load
    under request trace).  Returns status string.
    """
    global _cast_to_device_wrapper_installed
    if _cast_to_device_wrapper_installed:
        return "already_installed"
    func = getattr(mm_module, "cast_to_device", None)
    if not callable(func):
        return "unavailable"
    if getattr(func, _SENTINEL_CAST_TO_DEVICE, False):
        _cast_to_device_wrapper_installed = True
        return "already_installed"
    with _wrappers_lock:
        if _cast_to_device_wrapper_installed:
            return "already_installed"
        if getattr(mm_module.cast_to_device, _SENTINEL_CAST_TO_DEVICE, False):
            _cast_to_device_wrapper_installed = True
            return "already_installed"
        mm_module.cast_to_device = _make_cast_to_device_wrapper(mm_module.cast_to_device)
        _cast_to_device_wrapper_installed = True
    return "installed"


def _ensure_core_wrappers(trace: RuntimeTrace | None = None) -> dict[str, str]:
    """Idempotent per-component installation using live modules.

    Resolves ``comfy.utils`` and ``comfy.model_management`` via
    ``sys.modules`` (already loaded by ``nodes.py`` at startup) so that
    optional-dependency import failures in ``comfy.memory_management``
    cannot block the read wrapper.

    Also installs deep-diagnostic wrappers (``safetensors.safe_open``,
    ``torch.load``) when COMFYMODAL_V2_DEEP_MODEL_DIAG=1.  These wrappers
    are globally installed but filtered at call time by thread-local
    ``_DEEP_TARGET_PATH`` so unrelated file activity is never logged.

    Returns a ``{component: status}`` dict suitable for trace diagnostics.
    """
    result: dict[str, str] = {}

    utils_mod = _get_live_module("comfy.utils")
    if utils_mod is not None:
        result["load_torch_file"] = _install_read_wrapper(utils_module=utils_mod, trace=trace)
    else:
        result["load_torch_file"] = "unavailable"

    mm_mod = _get_live_module("comfy.model_management")
    if mm_mod is not None:
        result["load_models_gpu"] = _install_gpu_wrapper(mm_module=mm_mod, trace=trace)
        result["cast_to_device"] = _install_cast_to_device_wrapper(mm_module=mm_mod, trace=trace)
    else:
        result["load_models_gpu"] = "unavailable"
        result["cast_to_device"] = "unavailable"

    result.update(_install_model_patcher_wrappers(trace=trace))

    # ── Install deep diag wrappers (idempotent, path-filtered) ────
    if _DIAGNOSTIC_FLAG:
        import safetensors as _st
        import torch as _torch
        _st_mod = _get_live_module("safetensors")
        _st_open_fn = getattr(_st_mod, "safe_open", None) if _st_mod else None
        _deep_install_result = _install_deep_diag_wrappers(
            safe_open_fn=_st_open_fn,
            torch_load_fn=getattr(_torch, "load", None),
            trace=trace,
        )
        result.update(_deep_install_result)

    # Install CLIP wrapper.
    _clip_result = _install_clip_wrapper(trace=trace)
    result["comfy.sd.load_clip"] = _clip_result

    # Emit diagnostic events when a trace is available.
    if trace is not None:
        for component, status in result.items():
            trace.emit(
                "core_wrapper_install",
                phase="restore",
                metadata={
                    "component": component,
                    "status": status,
                },
            )

    # Install NextDiT forward pre-hook for forward-probe diagnostics.
    result["nextdit_forward_pre_hook"] = "installed" if install_nextdit_forward_pre_hook() else "unavailable"

    return result


# ── UNET post-read subfunction wrappers (Section B) ─────────────────
# Installed idempotently on the live sys.modules; skip absent modules
# without breaking loading.  Only active when _ACTIVE_LANE_TRACE is UNET.

_UNET_DECOMPOSE_TARGETS: dict[str, tuple[str, str, str]] = {
    # NOTE: load_diffusion_model_state_dict is handled by a dedicated
    # wrapper (_make_sd_state_dict_wrapper) so it is intentionally absent.
    # NOTE: convert_old_quants is installed via the shared lane-aware
    # _install_shared_convert_old_quants_wrapper so both CLIP and UNET
    # attribution remain active on the same live function.
    "state_dict_prefix_replace": ("comfy.utils", "state_dict_prefix_replace", "utils"),
    "calculate_parameters": ("comfy.utils", "calculate_parameters", "utils"),
    "weight_dtype": ("comfy.utils", "weight_dtype", "utils"),
    "model_config_from_unet": ("comfy.model_detection", "model_config_from_unet", "model_detection"),
    "unet_dtype": ("comfy.model_management", "unet_dtype", "model_management"),
    "unet_manual_cast": ("comfy.model_management", "unet_manual_cast", "model_management"),
    "unet_prefix_from_state_dict": ("comfy.model_detection", "unet_prefix_from_state_dict", "model_detection"),
    "convert_diffusers_mmdit": ("comfy.model_detection", "convert_diffusers_mmdit", "model_detection"),
    "model_config_from_diffusers_unet": ("comfy.model_detection", "model_config_from_diffusers_unet", "model_detection"),
    "unet_to_diffusers": ("comfy.utils", "unet_to_diffusers", "utils"),
    "unet_offload_device": ("comfy.model_management", "unet_offload_device", "model_management"),
}
"""Maps short name -> (module_name, function_name, diagnostic_category)."""


def _install_unet_decompose_wrappers(trace: RuntimeTrace | None = None) -> dict[str, str]:
    """Install UNET post-read decomposition wrappers idempotently.

    Global flag ``_subfn_wrappers_installed`` avoids duplicate trace
    events.  Each wrapper is installed on its live ``sys.modules`` entry
    using a sentinel for idempotence.  If a module or symbol is absent
    the entry is recorded as ``"unavailable"`` and loading continues.
    Returns ``{short_name: status}``.
    """
    global _subfn_wrappers_installed
    if _subfn_wrappers_installed:
        return {}
    result: dict[str, str] = {}
    # Install shared lane-aware convert_old_quants wrapper first.
    result["convert_old_quants"] = _install_shared_convert_old_quants_wrapper()
    # Install model patcher construction wrappers.
    result.update(_install_model_patcher_wrappers(trace=trace))
    for short_name, (mod_name, func_name, category) in _UNET_DECOMPOSE_TARGETS.items():
        mod = _get_live_module(mod_name)
        if mod is None:
            result[short_name] = "unavailable"
            continue
        original = getattr(mod, func_name, None)
        if not callable(original):
            result[short_name] = "unavailable"
            continue
        if getattr(original, _SENTINEL_UNET_SUBFN, False):
            result[short_name] = "already_installed"
            continue
        wrapper = _make_unet_subfn_wrapper(short_name, original, category)
        setattr(wrapper, _SENTINEL_UNET_SUBFN, True)
        setattr(mod, func_name, wrapper)
        result[short_name] = "installed"
    if trace:
        for name, status in result.items():
            trace.emit("unet_decompose_install", phase="restore", metadata={
                "function": name, "status": status,
            })
    _subfn_wrappers_installed = True
    return result


def _make_unet_subfn_wrapper(
    short_name: str,
    original: Callable[..., Any],
    category: str,
) -> Callable[..., Any]:
    """Wrap a UNET post-read subfunction to emit start/end events.

    Only active when ``_ACTIVE_LANE_TRACE`` is set AND the current lane
    is ``UNET``.  Reentrancy-safe via a per-function ContextVar depth
    counter.  Records duration into ``_child_durations`` for residual
    computation by the outer SD state dict wrapper.
    """
    _UNET_SUBFN_DEPTH: ContextVar[int] = ContextVar(f"_sd_depth_{short_name}", default=0)

    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        before = _UNET_SUBFN_DEPTH.get()
        _UNET_SUBFN_DEPTH.set(before + 1)
        lane = _ACTIVE_LANE_TRACE.get()
        _outer = (before == 0)
        emit = (_outer and lane is not None and lane._lane == "UNET")
        _nest_before = _unet_subfn_nesting_depth.get()
        _unet_subfn_nesting_depth.set(_nest_before + 1)
        _fn_start_ns = time.monotonic_ns() if emit else 0
        if emit:
            lane._trace.emit(f"unet_{short_name}_start", phase="restore", metadata={
                "category": category,
            })
        try:
            result = original(*args, **kwargs)
            if emit and short_name == "model_config_from_unet" and result is not None:
                _instrument_unet_model_config(result, lane)
            return result
        finally:
            after = _UNET_SUBFN_DEPTH.get()
            _UNET_SUBFN_DEPTH.set(after - 1)
            _unet_subfn_nesting_depth.set(_nest_before)
            if emit and _outer:
                _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
                lane._trace.emit(f"unet_{short_name}_end", phase="restore", metadata={
                    "category": category,
                    "duration_ms": _dur_ms,
                })
                # Record for outer SD residual computation (only direct children)
                if _nest_before == 0:
                    _children = _child_durations.get()
                    if _children is not None:
                        _children.append((short_name, _dur_ms))
    return wrapper


def _instrument_unet_model_config(model_config: Any, lane: "ModelLaneTrace") -> None:
    get_model = getattr(model_config, "get_model", None)
    if not callable(get_model) or getattr(get_model, _SENTINEL_SUBFN, False):
        return

    @functools.wraps(get_model)
    def wrapped_get_model(*args: Any, **kwargs: Any) -> Any:
        started_ns = time.monotonic_ns()
        lane._trace.emit("unet_model_config_get_model_start", phase="restore")
        _nest_before = _unet_subfn_nesting_depth.get()
        _unet_subfn_nesting_depth.set(_nest_before + 1)
        try:
            model = get_model(*args, **kwargs)
            _instrument_unet_model_weights(model, lane)
            return model
        finally:
            _unet_subfn_nesting_depth.set(_nest_before)
            duration_ms = round((time.monotonic_ns() - started_ns) / 1_000_000, 3)
            lane._trace.emit("unet_model_config_get_model_end", phase="restore", metadata={"duration_ms": duration_ms})
            children = _child_durations.get()
            if _nest_before == 0 and children is not None:
                children.append(("model_config_get_model", duration_ms))

    setattr(wrapped_get_model, _SENTINEL_SUBFN, True)
    try:
        model_config.get_model = wrapped_get_model
    except Exception:
        lane._trace.emit("unet_model_config_get_model_unavailable", phase="restore")


def _instrument_unet_model_weights(model: Any, lane: "ModelLaneTrace") -> None:
    load_weights = getattr(model, "load_model_weights", None)
    if not callable(load_weights) or getattr(load_weights, _SENTINEL_SUBFN, False):
        return

    @functools.wraps(load_weights)
    def wrapped_load_weights(*args: Any, **kwargs: Any) -> Any:
        started_ns = time.monotonic_ns()
        lane._trace.emit("unet_load_model_weights_start", phase="restore")
        _nest_before = _unet_subfn_nesting_depth.get()
        _unet_subfn_nesting_depth.set(_nest_before + 1)
        try:
            return load_weights(*args, **kwargs)
        finally:
            _unet_subfn_nesting_depth.set(_nest_before)
            duration_ms = round((time.monotonic_ns() - started_ns) / 1_000_000, 3)
            lane._trace.emit("unet_load_model_weights_end", phase="restore", metadata={"duration_ms": duration_ms})
            children = _child_durations.get()
            if _nest_before == 0 and children is not None:
                children.append(("load_model_weights", duration_ms))

    setattr(wrapped_load_weights, _SENTINEL_SUBFN, True)
    try:
        model.load_model_weights = wrapped_load_weights
    except Exception:
        lane._trace.emit("unet_load_model_weights_unavailable", phase="restore")


_SD_WRAPPER_INSTANCE: Any = None
"""Holds the ``sd.load_diffusion_model_state_dict`` wrapper to capture
both the full span and the residual computation."""


def _make_sd_state_dict_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``comfy.sd.load_diffusion_model_state_dict`` with UNET-lane guard.

    Emits:
    - ``unet_load_diffusion_model_state_dict_start/end`` span
    - ``unet_post_read_uninstrumented_residual`` with whole/child/residual ms.

    Reentrancy-safe via ``_sd_depth``.  Child durations are accumulated
    in a thread-local list via ``_child_durations``, populated by the
    sub-function wrappers in ``_make_unet_subfn_wrapper``.
    """
    global _SD_WRAPPER_INSTANCE

    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        before = _sd_depth.get()
        _sd_depth.set(before + 1)
        lane = _ACTIVE_LANE_TRACE.get()
        emit = (before == 0 and lane is not None and lane._lane == "UNET")
        _sd_start_ns = time.monotonic_ns() if emit else 0
        # Set up child duration tracking for this outer invocation.
        _prior_children = _child_durations.get()
        if emit:
            _child_durations.set([])
            lane._trace.emit("unet_load_diffusion_model_state_dict_start", phase="restore")
        try:
            return original(*args, **kwargs)
        finally:
            after = _sd_depth.get()
            _sd_depth.set(after - 1)
            if emit:  # before was 0, so we are the outermost invocation
                _children_raw = _child_durations.get() or []
                # Separate into legacy numeric and named tuples
                _legacy_durs: list[float] = []
                _named_children: list[tuple[str, float]] = []
                for _entry in _children_raw:
                    if isinstance(_entry, tuple):
                        _named_children.append(_entry)
                        _legacy_durs.append(_entry[1])
                    else:
                        _legacy_durs.append(_entry)
                _child_total = round(sum(_legacy_durs), 3)
                _whole_ms = round((time.monotonic_ns() - _sd_start_ns) / 1_000_000, 3)
                # Signed residual — allow negative when children exceed total
                _residual_ms = round(_whole_ms - _child_total, 3)
                _sd_status = "overlap_error" if _residual_ms < 0 else "ok"
                # Restore prior before emitting (children list snapshot taken)
                _child_durations.set(_prior_children)
                lane._trace.emit("unet_load_diffusion_model_state_dict_end", phase="restore", metadata={
                    "duration_ms": _whole_ms,
                    "model_construction_total_ms": _whole_ms,
                    "measured_child_total_ms": _child_total,
                    "measured_direct_children_ms": _child_total,
                    "measured_child_count": len(_named_children),
                    "measured_children": _legacy_durs,
                    "measured_named_children": _named_children,
                    "residual_ms": _residual_ms,
                    "model_construction_residual_ms": _residual_ms,
                    "status": _sd_status,
                    "classification": "residual_not_causal_owner",
                })

    setattr(wrapper, _SENTINEL_SD, True)
    _SD_WRAPPER_INSTANCE = wrapper
    return wrapper


def _install_sd_state_dict_wrapper(trace: RuntimeTrace | None = None) -> str:
    """Install the ``load_diffusion_model_state_dict`` wrapper on
    ``comfy.sd`` (live module in sys.modules).  Idempotent via sentinel."""
    global _sd_wrapper_installed
    if _sd_wrapper_installed:
        return "already_installed"
    mod = _get_live_module("comfy.sd")
    if mod is None:
        return "unavailable"
    original = getattr(mod, "load_diffusion_model_state_dict", None)
    if not callable(original):
        return "unavailable"
    if getattr(original, _SENTINEL_SD, False):
        _sd_wrapper_installed = True
        return "already_installed"
    with _wrappers_lock:
        if _sd_wrapper_installed:
            return "already_installed"
        if getattr(mod.load_diffusion_model_state_dict, _SENTINEL_SD, False):
            _sd_wrapper_installed = True
            return "already_installed"
        mod.load_diffusion_model_state_dict = _make_sd_state_dict_wrapper(
            mod.load_diffusion_model_state_dict
        )
        _sd_wrapper_installed = True
    if trace:
        trace.emit("unet_sd_wrapper_install", phase="restore", metadata={"status": "installed"})
    return "installed"


_UNET_DECOMPOSE_ENSURE_LOCK = RLock()
_unet_decompose_ensure_done: bool = False

def _ensure_unet_decompose_wrappers(trace: RuntimeTrace | None = None) -> dict[str, str]:
    """Install both the SD state dict wrapper and all subfunction wrappers.

    Returns combined ``{short_name: status}`` dict.  Global lock ensures
    exactly one full install attempt across all worker threads.
    """
    global _unet_decompose_ensure_done
    if _unet_decompose_ensure_done:
        return {}
    with _UNET_DECOMPOSE_ENSURE_LOCK:
        if _unet_decompose_ensure_done:
            return {}
        result: dict[str, str] = {}
        result["load_diffusion_model_state_dict"] = _install_sd_state_dict_wrapper(trace=trace)
        subfn_result = _install_unet_decompose_wrappers(trace=trace)
        result.update(subfn_result)
        _unet_decompose_ensure_done = True
        return result


# ── Phase 1-2: state machine and mutation lane ──────────────────────


class ModelLoadState(enum.Enum):
    """Single-flight state for one exact model identity.

    Transitions:
      PENDING → READING → CPU_READY → GPU_COMMITTING → READY
      any → FAILED
    """
    PENDING = "PENDING"
    READING = "READING"
    CPU_READY = "CPU_READY"
    GPU_COMMITTING = "GPU_COMMITTING"
    READY = "READY"
    FAILED = "FAILED"


_MUTATION_LANE_INSTANCE: "MutationLane | None" = None
_MUTATION_LANE_LOCK = RLock()


def _get_mutation_lane() -> "MutationLane":
    """Return the process-singleton mutation lane (lazy-init)."""
    global _MUTATION_LANE_INSTANCE
    if _MUTATION_LANE_INSTANCE is None:
        with _MUTATION_LANE_LOCK:
            if _MUTATION_LANE_INSTANCE is None:
                _MUTATION_LANE_INSTANCE = MutationLane()
    return _MUTATION_LANE_INSTANCE


class MutationLane:
    """FIFO serialization of GPU/cache mutation — does NOT preempt.

    Only one caller may hold the lane at a time.  Acquire blocks until
    the lane is free; release hands ownership to the next waiter (plain
    FIFO, no priority preemption).  Exception-safe via context manager.
    """

    _MUTEX_PRIORITY: dict[str, int] = {
        "UNET": 0, "CLIP": 1, "prefill": 2, "VAE": 3, "sampler": 4,
    }
    # NOTE: _MUTEX_PRIORITY is defined for documentation / forward
    # compatibility only.  The current implementation is plain FIFO —
    # priority does NOT preempt.

    def __init__(self) -> None:
        self._lock = RLock()
        self._owner: str | None = None
        self._cond = Condition(self._lock)

    def acquire(self, owner: str | None, timeout: float | None = None) -> bool:
        """Block until the lane is acquired — plain FIFO, no preemption."""
        if owner is None:
            return True  # no tracking for anonymous callers
        with self._cond:
            while self._owner is not None:
                # Priority: higher-priority waiters can preempt when current
                # owner releases. For now, simple FIFO with priority ordering
                # on acquire.
                if timeout is not None:
                    remaining = timeout
                self._cond.wait(timeout=timeout)
            self._owner = owner
        return True

    def release(self, owner: str | None) -> None:
        """Release the lane.  *owner* must match or be None."""
        if owner is None:
            return
        with self._cond:
            if self._owner == owner:
                self._owner = None
                self._cond.notify_all()

    @property
    def owner(self) -> str | None:
        with self._lock:
            return self._owner

    @contextmanager
    def lane_scope(self, owner: str) -> Iterator[None]:
        """Acquire on enter, release on exit (exception-safe)."""
        self.acquire(owner)
        try:
            yield
        finally:
            self.release(owner)


# ── ModelLaneTrace ───────────────────────────────────────────────────


class ModelLaneTrace:
    """Canonical per-lane event vocabulary for model-loading tracing.

    Provides standardised ``submitted``, ``read_start/read_end``,
    ``cpu_prepare_start/cpu_prepare_end``,
    ``gpu_lane_wait_start/gpu_lane_wait_end``,
    ``gpu_commit_start/gpu_commit_end``, ``ready/failed``, and
    ``graph_demand`` / ``graph_wait_start`` / ``graph_wait_end``
    events for UNET, CLIP, and (future) VAE lanes.

    All existing legacy events continue to be emitted unchanged.
    ``read_start/read_end`` fire from the ``comfy.utils.load_torch_file``
    wrapper.  ``gpu_commit_start/end`` fire from the
    ``comfy.model_management.load_models_gpu`` wrapper.
    ``cpu_prepare_start`` fires after the last expected ``read_end``;
    ``cpu_prepare_end`` fires before ``gpu_commit_start`` or at
    ``ready/failed``, whichever comes first.

    **expected_read_count**
        UNET normally performs one ``load_torch_file`` call (1).
        Single CLIP is 1; DualCLIP is 2.  When the observed read count
        differs from expected, ``cpu_prepare_start`` carries
        ``status="read_count_mismatch"``.

    **UNET-specific stages** (only emitted when ``_lane == "UNET"`` and
    ``_DIAGNOSTIC_FLAG`` is enabled):
        unet_file_stat_start/end, unet_file_open_start/end,
        unet_mmap_create_start/end, unet_load_torch_file_start/end,
        unet_safetensors_open_start/end, unet_safetensors_parse_start/end,
        unet_tensor_materialize_start/end or unet_safetensors_load_combined_start/end.
    """

    def __init__(
        self,
        trace: RuntimeTrace,
        lane: str,
        phase: str = "restore",
        *,
        expected_read_count: int = 1,
    ) -> None:
        self._trace = trace
        self._lane = lane
        self._phase = phase
        self.expected_read_count = max(0, int(expected_read_count))
        self._actual_read_count: int = 0
        self._cpu_prepare_started: bool = False
        self._cpu_prepare_ended: bool = False
        self._gpu_commit_started: bool = False
        # ── Worker queue/publication tracking ────────────────────
        self._submitted_at_ns: int = 0
        self._worker_started_at_ns: int = 0
        self._worker_ended_at_ns: int = 0
        self._cache_publish_started: bool = False
        self._cache_publish_completed: bool = False
        self._done_event_set: bool = False
        # Accumulated CLIP file-read wall time (ms).  Updated by
        # _on_read_completed(read_duration_ms=...) so _make_clip_load_wrapper
        # can avoid an O(n) event scan.  Only meaningful for CLIP lane.
        self._clip_read_total_ms: float = 0.0
        self._clip_read_started_ns: int = 0
        self._clip_pending_read_duration_ms: float | None = None

    # ── Internal lifecycle hooks (called by wrappers) ────────────────

    def _on_read_completed(self, read_duration_ms: float | None = None) -> None:
        """Called by the ``load_torch_file`` wrapper after each read_end.

        *read_duration_ms* — wall-time of the outer read_start..read_end
        interval.  When provided for CLIP lane, accumulated into
        ``_clip_read_total_ms`` so ``_make_clip_load_wrapper`` can avoid
        an O(n) event scan.
        """
        self._actual_read_count += 1
        if self._lane == "CLIP":
            if read_duration_ms is None:
                read_duration_ms = self._clip_pending_read_duration_ms
            self._clip_pending_read_duration_ms = None
            if read_duration_ms is not None:
                self._clip_read_total_ms += read_duration_ms
        if self._actual_read_count >= self.expected_read_count and not self._cpu_prepare_started:
            self._cpu_prepare_started = True
            if self.expected_read_count > 0 and self._actual_read_count != self.expected_read_count:
                self.cpu_prepare_start(status="read_count_mismatch",
                                       expected_read_count=self.expected_read_count,
                                       actual_read_count=self._actual_read_count)
                if self._lane == "CLIP":
                    self._trace.emit("clip_cpu_prepare_start", phase=self._phase, metadata={
                        "lane": self._lane,
                        "expected_read_count": self.expected_read_count,
                        "actual_read_count": self._actual_read_count,
                        "status": "read_count_mismatch",
                    })
            else:
                self.cpu_prepare_start(expected_read_count=self.expected_read_count,
                                       actual_read_count=self._actual_read_count)
                if self._lane == "CLIP":
                    self._trace.emit("clip_cpu_prepare_start", phase=self._phase, metadata={
                        "lane": self._lane,
                        "expected_read_count": self.expected_read_count,
                        "actual_read_count": self._actual_read_count,
                    })

    def _on_gpu_commit_about_to_start(self) -> None:
        """Called by the ``load_models_gpu`` wrapper before commit events."""
        if not self._cpu_prepare_ended:
            self._close_cpu_prepare(status="ok")
        self._gpu_commit_started = True

    def _close_cpu_prepare(self, status: str = "ok") -> None:
        """Emit ``cpu_prepare_end`` if ``cpu_prepare_start`` was emitted."""
        if self._cpu_prepare_started and not self._cpu_prepare_ended:
            self._cpu_prepare_ended = True
            self.cpu_prepare_end(status=status)

    # ── Producer-side lifecycle ──────────────────────────────────────

    def submitted(self, **metadata: Any) -> None:
        self._submitted_at_ns = time.monotonic_ns()
        self._trace.emit("submitted", phase=self._phase, metadata={"lane": self._lane, **metadata})

    def worker_start(self, **metadata: Any) -> None:
        self._worker_started_at_ns = time.monotonic_ns()
        # Capture thread and process CPU start for summary computation
        _tt = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
        _pt = time.process_time_ns() if hasattr(time, "process_time_ns") else None
        if _tt is not None:
            metadata["thread_time_ns"] = _tt
        if _pt is not None:
            metadata["process_time_ns"] = _pt
        self._trace.emit("background_unet_worker_start", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def worker_end(self, **metadata: Any) -> None:
        self._worker_ended_at_ns = time.monotonic_ns()
        # Capture thread and process CPU end for summary computation
        _tt = time.thread_time_ns() if hasattr(time, "thread_time_ns") else None
        _pt = time.process_time_ns() if hasattr(time, "process_time_ns") else None
        if _tt is not None:
            metadata["thread_time_ns"] = _tt
        if _pt is not None:
            metadata["process_time_ns"] = _pt
        self._trace.emit("background_unet_worker_end", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def worker_failed(self, **metadata: Any) -> None:
        self._trace.emit("background_unet_worker_failed", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def read_start(self, **metadata: Any) -> None:
        if self._lane == "CLIP":
            self._clip_read_started_ns = time.monotonic_ns()
        self._trace.emit("read_start", phase=self._phase, metadata={"lane": self._lane, **metadata})

    def read_end(self, **metadata: Any) -> None:
        if self._lane == "CLIP" and self._clip_read_started_ns:
            ended_ns = time.monotonic_ns()
            self._clip_pending_read_duration_ms = max(
                0.0, (ended_ns - self._clip_read_started_ns) / 1_000_000
            )
            self._clip_read_started_ns = 0
        self._trace.emit("read_end", phase=self._phase, metadata={"lane": self._lane, **metadata})

    def cpu_prepare_start(self, **metadata: Any) -> None:
        self._trace.emit("cpu_prepare_start", phase=self._phase, metadata={"lane": self._lane, **metadata})

    def cpu_prepare_end(self, **metadata: Any) -> None:
        self._trace.emit("cpu_prepare_end", phase=self._phase, metadata={"lane": self._lane, **metadata})

    def gpu_lane_wait_start(self, **metadata: Any) -> None:
        self._trace.emit("gpu_lane_wait_start", phase=self._phase, metadata={
            "lane": self._lane, "status": "unlocked", **metadata})
        # Also emit UNET-specific name
        if self._lane == "UNET":
            self._trace.emit("unet_gpu_lane_wait_start", phase=self._phase, metadata={
                "lane": self._lane, **metadata})

    def gpu_lane_wait_end(self, **metadata: Any) -> None:
        self._trace.emit("gpu_lane_wait_end", phase=self._phase, metadata={
            "lane": self._lane, "status": "unlocked", **metadata})
        if self._lane == "UNET":
            self._trace.emit("unet_gpu_lane_wait_end", phase=self._phase, metadata={
                "lane": self._lane, **metadata})

    def gpu_commit_start(self, **metadata: Any) -> None:
        self._trace.emit("gpu_commit_start", phase=self._phase, metadata={"lane": self._lane, **metadata})
        if self._lane == "UNET":
            self._trace.emit("unet_gpu_commit_start", phase=self._phase, metadata={
                "lane": self._lane, **metadata})

    def gpu_commit_end(self, **metadata: Any) -> None:
        self._trace.emit("gpu_commit_end", phase=self._phase, metadata={"lane": self._lane, **metadata})
        if self._lane == "UNET":
            self._trace.emit("unet_gpu_commit_end", phase=self._phase, metadata={
                "lane": self._lane, **metadata})

    def cache_publish_start(self, **metadata: Any) -> None:
        self._cache_publish_started = True
        self._trace.emit("unet_cache_publish_start", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def cache_object_store(self, **metadata: Any) -> None:
        self._trace.emit("unet_cache_object_store", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def cache_metadata_store(self, **metadata: Any) -> None:
        self._trace.emit("unet_cache_metadata_store", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def done_event_set(self, **metadata: Any) -> None:
        self._done_event_set = True
        self._trace.emit("unet_done_event_set", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def cache_publish_end(self, **metadata: Any) -> None:
        self._cache_publish_completed = True
        self._trace.emit("unet_cache_publish_end", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def ready(self, **metadata: Any) -> None:
        self._close_cpu_prepare(status="ok")
        # Only set ready after cache publication is complete
        self._trace.emit("ready", phase=self._phase, metadata={
            "lane": self._lane,
            "cache_publish_completed": self._cache_publish_completed,
            "done_event_set": self._done_event_set,
            **metadata,
        })

    def failed(self, **metadata: Any) -> None:
        self._close_cpu_prepare(status="error")
        self._trace.emit("failed", phase=self._phase, metadata={"lane": self._lane, **metadata})

    # ── UNET-specific file/safetensors stage methods ────────────────
    # Only meaningful for UNET lane with deep diag enabled.  These
    # mirror the deep diagnostic wrappers above.

    def unet_file_stat(self, **metadata: Any) -> None:
        self._trace.emit("unet_file_stat_start", phase=self._phase, metadata={"lane": self._lane, **metadata})
        self._trace.emit("unet_file_stat_end", phase=self._phase, metadata={"lane": self._lane})

    def unet_file_open(self, **metadata: Any) -> None:
        # INTENTIONALLY UNCALLED — the live safetensors/torch.load
        # implementations do not expose a separable Python-callable
        # file-open boundary.  This method exists only for forward
        # compatibility and the bg_unet_io summary correctly reports
        # it as None/absent.
        self._trace.emit("unet_file_open_start", phase=self._phase, metadata={"lane": self._lane, **metadata})
        self._trace.emit("unet_file_open_end", phase=self._phase, metadata={"lane": self._lane})

    def unet_mmap_create(self, **metadata: Any) -> None:
        self._trace.emit("unet_mmap_create_start", phase=self._phase, metadata={"lane": self._lane, **metadata})
        self._trace.emit("unet_mmap_create_end", phase=self._phase, metadata={"lane": self._lane})

    def unet_load_torch_file(self, **metadata: Any) -> None:
        self._trace.emit("unet_load_torch_file_start", phase=self._phase, metadata={"lane": self._lane, **metadata})
        self._trace.emit("unet_load_torch_file_end", phase=self._phase, metadata={"lane": self._lane})

    def post_load_cleanup(self, **metadata: Any) -> None:
        """Emit a truthful zero-duration post-load cleanup boundary.

        ComfyUI has no separable post-load cleanup call; this method emits
        start/end events at the same instant so the duration is truthfully
        0.0 rather than fabricating elapsed work or inferring it from a
        broad aggregate span.
        """
        _now_ns = time.monotonic_ns()
        self._trace.emit(
            "unet_post_load_cleanup_start", phase=self._phase,
            metadata={"lane": self._lane, **metadata},
        )
        self._trace.emit(
            "unet_post_load_cleanup_end", phase=self._phase,
            metadata={"lane": self._lane, "duration_ms": 0.0, **metadata},
        )

    # ── Consumer-side (graph demand) lifecycle ───────────────────────

    def graph_demand(self, **metadata: Any) -> None:
        self._trace.emit("graph_demand", phase="execution", metadata={"lane": self._lane, **metadata})

    def graph_wait_start(self, **metadata: Any) -> None:
        self._trace.emit("graph_wait_start", phase="execution", metadata={"lane": self._lane, **metadata})

    def graph_wait_end(self, **metadata: Any) -> None:
        self._trace.emit("graph_wait_end", phase="execution", metadata={"lane": self._lane, **metadata})


# ── External (legacy background UNET) lane scope ─────────────────────

@contextmanager
def external_model_lane_scope(
    trace: RuntimeTrace,
    *,
    lane: str = "UNET",
    phase: str = "restore",
    expected_read_count: int = 1,
) -> Iterator[ModelLaneTrace]:
    """Context manager for legacy background UNET thread lane tracing.

    Creates a dedicated ``ModelLaneTrace``, sets ``_ACTIVE_LANE_TRACE``,
    and ensures terminal ``ready()`` or ``failed()`` is emitted exactly
    once.  The *trace* must be a **dedicated** RuntimeTrace (not shared
    with the request/restore trace) — this manager never appends to a
    shared cross-thread list.

    On success the lane's events are stored into the module-level
    ``_BG_UNET_DIAG_STORE`` keyed by ``(lane, diagnostic_id)`` for
    later draining by the graph cache patcher.

    Usage::

        bg_trace = RuntimeTrace(process="remote_background_unet", ...)
        with external_model_lane_scope(bg_trace, lane="UNET", ...) as lane_trace:
            lane_trace.submitted()
            # ... worker body ...
    """
    lane_trace = ModelLaneTrace(trace, lane, phase=phase, expected_read_count=expected_read_count)
    # Emit background_unet_submitted immediately when scope opens
    _canonical_key_str = str(trace._metadata.get("canonical_key", "")) if hasattr(trace, "_metadata") else ""
    _diag_id_val = str(trace._metadata.get("diagnostic_id", "")) if hasattr(trace, "_metadata") else ""
    _resolved_path_val = str(trace._metadata.get("resolved_path", "")) if hasattr(trace, "_metadata") else ""
    lane_trace.submitted(canonical_key=_canonical_key_str, diagnostic_id=_diag_id_val)
    trace.emit("background_unet_submitted", phase=phase, metadata={
        "lane": lane, "canonical_key": _canonical_key_str, "diagnostic_id": _diag_id_val,
        "expected_read_count": expected_read_count,
    })
    # Set path filtering for deep diag wrappers
    _deep_path_token = None
    if _DIAGNOSTIC_FLAG:
        if _resolved_path_val:
            _deep_path_token = _DEEP_TARGET_PATH.set(_resolved_path_val)
    # NOTE: active-read before/after deltas are NOT sampled here.
    # Active-read delta computation is owned entirely by the exact
    # comfyapp _register_active_model_read / _complete_active_model_read
    # interval.  The background worker scope only owns its own
    # deep-diagnostic file-stat / safetensors boundaries.

    # Emit unet_file_stat from actual os.stat of the resolved path
    if _DIAGNOSTIC_FLAG and _resolved_path_val:
        try:
            _st = os.stat(_resolved_path_val)
            lane_trace.unet_file_stat(
                path_hash=_resolved_path_val[-48:],
                size=_st.st_size,
                st_dev=_st.st_dev,
                st_ino=_st.st_ino,
            )
        except OSError:
            lane_trace.unet_file_stat(path_hash=_resolved_path_val[-48:], size=None)

    # Install core dispatch + deep diag wrappers idempotently in the
    # real background worker thread so safetensors/torch.load boundaries
    # are instrumented under COMFYMODAL_V2_DEEP_MODEL_DIAG=1.
    _ensure_core_wrappers(trace=trace)

    # Install UNET decomposition wrappers (model_config_get_model,
    # load_model_weights, model_to, model_patcher_constructor, etc.)
    # idempotently so the background UNET trace emits the full set of
    # model-construction child stages.
    _ensure_unet_decompose_wrappers(trace=trace)

    token = _ACTIVE_LANE_TRACE.set(lane_trace)
    lane_trace.worker_start(canonical_key=_canonical_key_str)
    try:
        yield lane_trace
        lane_trace.worker_end()
        # Post-load cleanup boundary — truthfully 0.0 since ComfyUI has
        # no separable finalization call between model construction and
        # cache publication.  Placed after worker_end so the boundary
        # captures the explicit handoff point; called before ready() so
        # the cleanup stage precedes the terminal ready event.
        lane_trace.post_load_cleanup()
        # ready() is called AFTER cache publication completes — the
        # caller is responsible for calling cache_publish_start(),
        # cache_object_store(), cache_metadata_store(), done_event_set(),
        # cache_publish_end() before this scope exits.
        lane_trace.ready()
    except BaseException as exc:
        lane_trace.worker_end()
        lane_trace.post_load_cleanup(error_category=type(exc).__name__)
        lane_trace.worker_failed(error_category=type(exc).__name__)
        lane_trace.failed(error_category=type(exc).__name__)
        raise
    finally:
        _ACTIVE_LANE_TRACE.reset(token)
        if _deep_path_token is not None:
            _DEEP_TARGET_PATH.reset(_deep_path_token)

        # ── Emit bg_unet summaries from the worker's actual trace ──
        _emit_bg_unet_io_summary(trace, canonical_key=_canonical_key_str, force=True)
        _emit_bg_unet_stages_summary(trace, canonical_key=_canonical_key_str,
                                      weight_dtype=trace._metadata.get("weight_dtype", "") if hasattr(trace, "_metadata") else "",
                                      force=True)

        # Store completed events into the diagnostic store for later
        # draining by graph cache consumer.  Use a composite key that
        # includes diagnostic_id from the trace metadata when available.
        _store_key = f"{lane}:{_diag_id_val}" if _diag_id_val else lane
        with _BG_UNET_DIAG_LOCK:
            # Append (do not overwrite) to avoid losing previously stored events
            _existing = _BG_UNET_DIAG_STORE.setdefault(_store_key, [])
            _existing.extend(trace.events)


# ── Restore-return marker helpers ────────────────────────────────────


def set_restore_return_marker(
    restored_instance_id: str,
    restore_session_id: str,
    legacy_container_session_id: str,
    modal_task_id: str = "",
    pid: int = 0,
) -> None:
    """Set ``_LATEST_RESTORE_RETURN_MARKER`` immediately before restore return."""
    global _LATEST_RESTORE_RETURN_MARKER
    _LATEST_RESTORE_RETURN_MARKER = {
        **_capture_host_info(),
        "wall_unix_ns": int(time.time() * 1_000_000_000),
        "monotonic_ns": time.monotonic_ns(),
        "restored_instance_id": restored_instance_id,
        "restore_session_id": restore_session_id,
        "legacy_container_session_id": legacy_container_session_id,
        "modal_task_id": modal_task_id,
        "pid": pid,
    }


def get_restore_return_marker() -> dict[str, Any] | None:
    marker = _LATEST_RESTORE_RETURN_MARKER
    return dict(marker) if marker else None


def set_model_load_identity(restored_instance_id: str, restore_session_id: str) -> None:
    global _LATEST_RESTORED_INSTANCE_ID, _LATEST_RESTORE_SESSION_ID
    _LATEST_RESTORED_INSTANCE_ID = restored_instance_id
    _LATEST_RESTORE_SESSION_ID = restore_session_id


@contextmanager
def request_execution_trace_scope(trace: RuntimeTrace) -> Iterator[None]:
    _gpu_request_call_count_var.set(0)
    token = _ACTIVE_REQUEST_TRACE.set(trace)
    try:
        yield
    finally:
        _ACTIVE_REQUEST_TRACE.reset(token)


def reset_gpu_call_count() -> None:
    _gpu_request_call_count_var.set(0)


def gpu_wrapper_is_installed() -> bool:
    return _gpu_wrapper_installed


def gpu_call_count() -> int:
    return _gpu_request_call_count_var.get()


def gpu_not_observed_summary() -> dict[str, Any]:
    """Return request-scope GPU wrapper diagnostic summary.

    When a request makes zero ``load_models_gpu`` calls, this accessor
    reports ``caller_classification="not_observed"`` (wrapper installed)
    or ``"wrapper_unavailable"`` (wrapper not installed), together with
    the request ID, wrapper status, and invocation count.

    Preserves the installed/unavailable distinction and request-local
    invocation count.  No side effects on lane/request events.
    """
    wrapper_installed = _gpu_wrapper_installed
    request_id = get_active_request_id()
    cnt = _gpu_request_call_count_var.get()
    if wrapper_installed:
        return {
            "caller_classification": "not_observed" if cnt == 0 else "observed",
            "request_id": request_id,
            "wrapper_status": "installed",
            "count": cnt,
        }
    return {
        "caller_classification": "wrapper_unavailable",
        "request_id": request_id,
        "wrapper_status": "unavailable",
        "count": 0,
    }


def get_active_request_id() -> str:
    trace = _ACTIVE_REQUEST_TRACE.get()
    return str(trace.request_id) if trace is not None else ""


# ── Deep diagnostic helpers (guarded by COMFYMODAL_V2_DEEP_MODEL_DIAG) ──


def _capture_tid() -> int:
    """Return native thread ID (cross-platform)."""
    try:
        import threading
        return threading.get_native_id()
    except Exception:
        return 0


def _capture_host_info() -> dict[str, Any]:
    """Capture hostname, pid, and Linux boot_id when available."""
    info: dict[str, Any] = {
        "pid": os.getpid(),
        "native_tid": _capture_tid(),
        "hostname": platform.node(),
    }
    if platform.system() == "Linux":
        try:
            with open("/proc/sys/kernel/random/boot_id") as _f:
                info["boot_id"] = _f.read().strip()
        except Exception:
            pass
    return info


def _capture_rusage_thread_delta() -> dict[str, Any] | None:
    """Return RUSAGE_THREAD values.  Only on Linux with deep diag enabled."""
    if not _DIAGNOSTIC_FLAG:
        return None
    if platform.system() != "Linux":
        return None
    try:
        import resource
        ru = resource.getrusage(resource.RUSAGE_THREAD)
        return {
            "utime_ms": round(ru.ru_utime * 1000, 3),
            "stime_ms": round(ru.ru_stime * 1000, 3),
            "minflt": ru.ru_minflt,
            "majflt": ru.ru_majflt,
            "inblock": ru.ru_inblock,
            "oublock": ru.ru_oublock,
            "nvcsw": ru.ru_nvcsw,
            "nivcsw": ru.ru_nivcsw,
        }
    except Exception:
        return None


def _capture_rusage_thread_snapshot() -> dict[str, Any] | None:
    """Return a raw RUSAGE_THREAD snapshot for before/after delta computation.
    Requires Linux.  Does NOT require COMFYMODAL_V2_DEEP_MODEL_DIAG.
    Returns flat dict of ints.  The caller must compute deltas externally."""
    if platform.system() != "Linux":
        return None
    try:
        import resource
        ru = resource.getrusage(resource.RUSAGE_THREAD)
        return {
            "utime_us": round(ru.ru_utime * 1_000_000),
            "stime_us": round(ru.ru_stime * 1_000_000),
            "minflt": ru.ru_minflt,
            "majflt": ru.ru_majflt,
            "inblock": ru.ru_inblock,
            "oublock": ru.ru_oublock,
            "nvcsw": ru.ru_nvcsw,
            "nivcsw": ru.ru_nivcsw,
        }
    except Exception:
        return None


def _capture_proc_tid_io_snapshot() -> dict[str, int] | None:
    """Read /proc/self/task/<tid>/io for delta-capable counters.
    Only on Linux with deep diag enabled.  Returns dict of raw ints.
    The caller must compute deltas externally."""
    if not _DIAGNOSTIC_FLAG or platform.system() != "Linux":
        return None
    try:
        tid = _capture_tid()
        with open(f"/proc/self/task/{tid}/io") as _f:
            lines = _f.readlines()
        result: dict[str, int] = {}
        for line in lines:
            for prefix in ("rchar", "wchar", "syscr", "syscw",
                           "read_bytes", "write_bytes", "cancelled_write_bytes"):
                if line.startswith(prefix + ":"):
                    parts = line.strip().split(":")
                    if len(parts) == 2:
                        result[prefix] = int(parts[1].strip())
        return result
    except Exception:
        return None


def classify_active_read_dims(
    *,
    deep_diag: bool,
    before_tid: int | None = None,
    after_tid: int | None = None,
    has_thread_cpu: bool = False,
    has_process_cpu: bool = False,
    has_rusage: bool = False,
    has_io: bool = False,
    has_cgroup: bool = False,
    os_supports_thread_cpu: bool = True,
    os_supports_process_cpu: bool = True,
    os_supports_rusage: bool = True,
    os_supports_io: bool = True,
    os_supports_cgroup: bool = True,
) -> dict[str, str]:
    """Classify per-dimension active-read counter statuses using native thread IDs.

    Each dimension is classified independently.  Missing is not zero: a
    dimension whose before *or* after snapshot is missing gets a string status
    rather than a numeric zero.  A valid zero delta is only possible when both
    snapshots exist.

    Status vocabulary:
      ``available`` — data captured and valid for this dimension.
      ``unsupported`` — deep_diag is disabled; this OS class is not instrumented.
      ``unavailable`` — deep_diag enabled but the OS does not support this
          counter (e.g. ``resource.RUSAGE_THREAD`` on non-Linux).
      ``thread_changed`` — thread-bounded dimension whose before/after
          measurement spans different native threads; delta would be meaningless.
      ``not_observed_in_this_thread`` — deep_diag + same thread, the OS
          supports this counter, but no before-snapshot was captured for
          this dimension in this thread.
      ``no_before_snapshot`` — deep_diag enabled, OS supports, but before
          snapshot was not captured (e.g. late registration).
      ``aggregate_available`` — (cgroup) aggregate memory.stat values
          are present and merged from multiple dimensions.
      ``aggregate_partial`` — (cgroup) some but not all cgroup dimensions
          are available.
      ``aggregate_unavailable`` — (cgroup) no cgroup data at all, preventing
          aggregate status.

    Returns a dict keyed by dimension name with string status values.
    """
    _same_tid: bool = (before_tid is not None and after_tid is not None
                       and before_tid == after_tid)

    # ── Dimension definitions with per-dimension metadata ───────────
    _DIMS: list[tuple[str, bool]] = [
        ("thread_cpu", True),       # thread-bounded
        ("process_cpu", False),     # process-wide (not thread-bounded)
        ("io_deltas", True),        # thread-bounded
        ("page_faults", True),      # thread-bounded (RUSAGE_THREAD minflt/majflt)
        ("block_input", True),      # thread-bounded (RUSAGE_THREAD inblock/oublock)
        ("context_switches", True), # thread-bounded (RUSAGE_THREAD nvcsw/nivcsw)
        ("cgroup_memory", False),   # process-wide cgroup v2 memory.stat
    ]
    # ── Per-dimension data-captured flag mapping ────────────────────
    _HAS_MAP: dict[str, bool] = {
        "thread_cpu": has_thread_cpu,
        "process_cpu": has_process_cpu,
        "io_deltas": has_io,
        "page_faults": has_rusage,
        "block_input": has_rusage,
        "context_switches": has_rusage,
        "cgroup_memory": has_cgroup,
    }
    # ── Per-dimension OS-support flag mapping ───────────────────────
    _OS_SUPPORTS_MAP: dict[str, bool] = {
        "thread_cpu": os_supports_thread_cpu,
        "process_cpu": os_supports_process_cpu,
        "io_deltas": os_supports_io,
        "page_faults": os_supports_rusage,
        "block_input": os_supports_rusage,
        "context_switches": os_supports_rusage,
        "cgroup_memory": os_supports_cgroup,
    }

    result: dict[str, str] = {}
    if not deep_diag:
        for dim, _ in _DIMS:
            result[dim] = "unsupported"
        return result

    for dim, thread_bounded in _DIMS:
        has_data = _HAS_MAP[dim]
        os_supports = _OS_SUPPORTS_MAP[dim]
        if thread_bounded and not _same_tid:
            result[dim] = "thread_changed"
        elif not has_data:
            if not os_supports:
                result[dim] = "unavailable"
            else:
                result[dim] = "not_observed_in_this_thread"
        else:
            result[dim] = "available"

    # ── Cgroup aggregate status ─────────────────────────────────────
    cg_avail = has_cgroup
    if not deep_diag:
        result["cgroup_aggregate"] = "unsupported"
    elif not os_supports_cgroup:
        result["cgroup_aggregate"] = "unavailable"
    elif not cg_avail:
        result["cgroup_aggregate"] = "unavailable"
    else:
        result["cgroup_aggregate"] = "available"
    return result


def _compute_rusage_deltas(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compute rusage deltas (after - before). Both must share the same keys."""
    if not before or not after:
        return None
    result = {}
    for key in before:
        if key in after and isinstance(before[key], (int, float)) and isinstance(after[key], (int, float)):
            result[key] = max(0, after[key] - before[key])
    return result


def _compute_io_deltas(before: dict[str, int] | None, after: dict[str, int] | None) -> dict[str, int] | None:
    """Compute /proc/self/io deltas (after - before)."""
    if not before or not after:
        return None
    result = {}
    for key in before:
        if key in after and isinstance(before[key], int) and isinstance(after[key], int):
            result[key] = max(0, after[key] - before[key])
    return result


def _capture_proc_tid_io() -> dict[str, Any] | None:
    """Read /proc/self/task/<tid>/io for delta-capable counters.
    Only on Linux with deep diag enabled.  Returns raw values (not deltas)."""
    if not _DIAGNOSTIC_FLAG or platform.system() != "Linux":
        return None
    try:
        tid = _capture_tid()
        with open(f"/proc/self/task/{tid}/io") as _f:
            lines = _f.readlines()
        result: dict[str, int] = {}
        for line in lines:
            for prefix in ("rchar", "wchar", "syscr", "syscw",
                           "read_bytes", "write_bytes", "cancelled_write_bytes"):
                if line.startswith(prefix + ":"):
                    parts = line.strip().split(":")
                    if len(parts) == 2:
                        result[prefix] = int(parts[1].strip())
        return result
    except Exception:
        return None


def _capture_file_identity(path: str) -> dict[str, Any]:
    """Capture stat info for the file at *path*: st_dev, st_ino, size, mtime."""
    result: dict[str, Any] = {"path_hash": stable_hash(path or "")}
    if not path:
        return result
    try:
        st = os.stat(path)
        result["st_dev"] = st.st_dev
        result["st_ino"] = st.st_ino
        result["size"] = st.st_size
        result["st_mtime"] = round(st.st_mtime, 3)
        if _DIAGNOSTIC_FLAG and platform.system() == "Linux":
            try:
                # Attempt mount/filesystem identity via stat
                result["st_dev_major"] = os.major(st.st_dev)
                result["st_dev_minor"] = os.minor(st.st_dev)
            except Exception:
                pass
    except OSError:
        pass
    return result


# ── Slow model-read diagnostic helpers (threshold-gated) ──────────────
# Lightweight before-state (only wall/thread/process time + native TID)
# is captured before every CLIP load_torch_file call and every
# background-UNET active read.  Expensive diagnostics (/proc/meminfo,
# cgroup memory.stat) are only collected when elapsed >= threshold.


@dataclass
class _SlowReadBeforeState:
    """Inexpensive before-state captured before a model read.
    No /proc, cgroup, rusage, tensor, or module inspection allowed here."""
    mono_ns: int
    thread_time_ns: int | None
    process_time_ns: int | None
    tid: int


def _capture_slow_read_before() -> _SlowReadBeforeState:
    """Inexpensive before-state capturing only timing + native TID."""
    return _SlowReadBeforeState(
        mono_ns=time.monotonic_ns(),
        thread_time_ns=time.thread_time_ns() if hasattr(time, "thread_time_ns") else None,
        process_time_ns=time.process_time_ns() if hasattr(time, "process_time_ns") else None,
        tid=_capture_tid(),
    )


def _unescape_mountinfo_field(field: str) -> str:
    """Unescape mountinfo(5) escaped characters in a single field.

    Mountinfo encodes spaces as ``\\040``, tabs as ``\\011``, newlines as
    ``\\012``, and backslashes as ``\\134``.  Must unescape backslash first
    to avoid double-unescaping ``\\134040`` → ``\\040`` → `` ``.
    """
    field = field.replace("\\134", "\\")
    field = field.replace("\\011", "\t")
    field = field.replace("\\012", "\n")
    field = field.replace("\\040", " ")
    return field


def _discover_cgroup2_path() -> tuple[str | None, str | None]:
    """Discover the cgroup v2 mount path and the process's cgroup relative path.

    Uses ``/proc/self/mountinfo`` to find the cgroup2 mount point (not assuming
    ``/sys/fs/cgroup``) and ``/proc/self/cgroup`` to find the process's cgroup
    relative path.  Returns ``(mount_point, cgroup_relative_path)`` on success,
    ``(None, None)`` on any error.

    Injectable via ``_read_file_lines`` for testing.
    """
    try:
        # Find cgroup2 mount point
        mount_lines = _read_file_lines("/proc/self/mountinfo")
        mount_point: str | None = None
        for line in mount_lines:
            clean = line.strip()
            # Split on " - " to separate pre-separator fields from fs_type/post fields
            if " - " not in clean:
                continue
            pre_part, post_part = clean.split(" - ", 1)
            pre_parts = pre_part.split()
            post_fields = post_part.split()
            # mountinfo format (pre-separator):
            #   id parent_id major:minor root mount_point options ...
            # root is index 3, mount_point is index 4
            if len(pre_parts) >= 5 and len(post_fields) >= 1:
                fs_type = post_fields[0]
                if fs_type == "cgroup2":
                    raw_root = pre_parts[3]
                    raw_mount = pre_parts[4]
                    # Unescape escaped characters in root and mount_point
                    mount_point = _unescape_mountinfo_field(raw_mount)
                    # Also unescape root for safety (not directly used here)
                    break
        if mount_point is None:
            return None, None

        # Read /proc/self/cgroup for the cgroup relative path
        cgroup_lines = _read_file_lines("/proc/self/cgroup")
        cgroup_rel: str | None = None
        for line in cgroup_lines:
            line = line.strip()
            if not line:
                continue
            # Format: hierarchy-ID:controller-list:cgroup-path
            # For cgroupv2, hierarchy-ID is 0, controller-list is empty
            parts = line.split(":", 2)
            if len(parts) == 3 and parts[0] == "0" and parts[1] == "":
                cgroup_rel = parts[2]
                break
            # Fallback: any line with a path (some systems vary)
            if len(parts) == 3 and parts[1] == "" and parts[2]:
                cgroup_rel = parts[2]

        if cgroup_rel is None:
            # /proc/self/cgroup missing or malformed — nonfatal failure
            return None, None
        if cgroup_rel == "/":
            # Process is in root cgroup — memory.stat at mount_point directly
            return mount_point, ""

        return mount_point, cgroup_rel
    except Exception:
        return None, None


def _resolve_cgroup_memory_stat_path() -> str | None:
    """Resolve the actual path to the cgroup v2 memory.stat file.

    Returns the discovered path or ``None`` when cgroup v2 is unavailable
    or discovery fails.  Uses only the mount point discovered from
    ``/proc/self/mountinfo`` (no hardcoded fallback).
    Guards against relative-path traversal in the cgroup relative path.
    """
    mount_point, cgroup_rel = _discover_cgroup2_path()
    if mount_point is None:
        return None
    # Normalise and validate the cgroup relative path
    rel = cgroup_rel.lstrip("/") if cgroup_rel else ""
    # Prevent relative-path traversal: reject paths containing ".." segments
    if rel:
        _segments = rel.replace("\\", "/").split("/")
        if ".." in _segments:
            return None
        memory_stat_path = os.path.join(mount_point, rel, "memory.stat")
    else:
        memory_stat_path = os.path.join(mount_point, "memory.stat")
    if os.path.isfile(memory_stat_path):
        return memory_stat_path
    return None


def _read_file_lines(path: str) -> list[str]:
    """Read all lines from *path*.  Injectable for testing.

    Returns empty list on any error.
    """
    try:
        with open(path) as _f:
            return _f.readlines()
    except Exception:
        return []


def _parse_memory_stat(content: str) -> dict[str, int]:
    """Parse memory.stat content into a dict of ints.

    Extracts: file, inactive_file, active_file, workingset_refault_file,
    workingset_activate_file, pgfault, pgmajfault.
    """
    result: dict[str, int] = {}
    _TARGET_KEYS = frozenset({
        "file", "inactive_file", "active_file",
        "workingset_refault_file", "workingset_activate_file",
        "pgfault", "pgmajfault",
    })
    for line in content.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[0] in _TARGET_KEYS:
            try:
                result[parts[0]] = int(parts[1])
            except ValueError:
                pass
    return result


def _read_cgroup_memory_stat() -> dict[str, int] | None:
    """Read cgroup v2 memory.stat using discovered path.

    Uses ``_discover_cgroup2_path`` to find the actual cgroup v2 mount
    and process cgroup.  Returns parsed dict or ``None`` on any error.
    """
    try:
        path = _resolve_cgroup_memory_stat_path()
        if path is None:
            return None
        content_lines = _read_file_lines(path)
        if not content_lines:
            return None
        return _parse_memory_stat("".join(content_lines))
    except Exception:
        return None


def _read_proc_meminfo_cached_available() -> dict[str, int | None] | None:
    """Read Cached and MemAvailable from /proc/meminfo.
    Only called after threshold exceeded.  Returns None on any error."""
    try:
        _cached: int | None = None
        _avail: int | None = None
        with open("/proc/meminfo") as _f:
            for _line in _f:
                if _line.startswith("Cached:"):
                    _cached = int(_line.split()[1])
                elif _line.startswith("MemAvailable:"):
                    _avail = int(_line.split()[1])
        return {"cached_kb": _cached, "mem_available_kb": _avail}
    except Exception:
        return None


def _capture_proc_self_io() -> dict[str, int] | None:
    """Read ``/proc/self/io`` for process-wide ``rchar`` and ``read_bytes``.

    Does NOT require ``COMFYMODAL_V2_DEEP_MODEL_DIAG``.  Returns ``None`` on
    any error or unsupported platform.  Missing files and unsupported platforms
    do not raise.  Unsupported/unavailable counters are represented truthfully,
    never invented zeroes.
    """
    if platform.system() != "Linux":
        return None
    try:
        result: dict[str, int] = {}
        with open("/proc/self/io") as _f:
            for _line in _f:
                for _prefix in ("rchar", "read_bytes"):
                    if _line.startswith(_prefix + ":"):
                        _parts = _line.strip().split(":")
                        if len(_parts) == 2:
                            result[_prefix] = int(_parts[1].strip())
        return result if result else None
    except Exception:
        return None


def _collect_rusage_and_io_snapshots() -> tuple[dict[str, Any] | None, dict[str, int] | None]:
    """Capture RUSAGE_THREAD and /proc/self/io snapshots
    for delta computation.  Dies silently on unsupported platforms."""
    _ru = None
    _io = None
    if platform.system() == "Linux":
        try:
            import resource
            _ru_raw = resource.getrusage(resource.RUSAGE_THREAD)
            _ru = {
                "minflt": _ru_raw.ru_minflt,
                "majflt": _ru_raw.ru_majflt,
                "inblock": _ru_raw.ru_inblock,
                "nvcsw": _ru_raw.ru_nvcsw,
                "nivcsw": _ru_raw.ru_nivcsw,
            }
        except Exception:
            pass
        try:
            _io = _capture_proc_self_io()
        except Exception:
            pass
    return _ru, _io


def _compute_rusage_deltas_simple(before: dict[str, Any] | None,
                                  after: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compute rusage deltas (after - before). Both must share the same keys."""
    if not before or not after:
        return None
    result = {}
    for key in before:
        if key in after and isinstance(before[key], (int, float)) and isinstance(after[key], (int, float)):
            result[key] = max(0, after[key] - before[key])
    return result


def _compute_io_deltas_simple(before: dict[str, int] | None,
                              after: dict[str, int] | None) -> dict[str, int] | None:
    """Compute /proc/self/io deltas (after - before)."""
    if not before or not after:
        return None
    result = {}
    for key in before:
        if key in after and isinstance(before[key], int) and isinstance(after[key], int):
            result[key] = max(0, after[key] - before[key])
    return result


def _emit_slow_read_line(
    *,
    owner: str,
    loader_type: str,
    path_str: str,
    request_id: str,
    restore_session_id: str,
    restored_instance_id: str,
    before: _SlowReadBeforeState,
    after_mono_ns: int,
    after_thread_time_ns: int | None,
    after_process_time_ns: int | None,
    after_tid: int,
    before_rusage: dict[str, Any] | None = None,
    after_rusage: dict[str, Any] | None = None,
    before_io: dict[str, int] | None = None,
    after_io: dict[str, int] | None = None,
    active_read_entry: dict[str, Any] | None = None,
) -> None:
    """Collect all diagnostics and emit exactly one ``[v2.slow_model_read]`` line.
    Called only when elapsed >= threshold.  Missing/unsupported counters use
    ``None`` (printed as ``None``), never invented zeros.

    When *active_read_entry* is provided (UNET path), its pre-computed delta
    fields are used instead of recalculating from before/after snapshots.
    """
    # ── Elapsed wall time ───────────────────────────────────────────
    if active_read_entry is not None:
        elapsed_ms = active_read_entry.get("active_read_wall_ms")
    else:
        elapsed_ms = round((after_mono_ns - before.mono_ns) / 1_000_000, 3)

    # ── Path hash (normalized, never raw user path) ─────────────────
    path_hash = stable_hash(path_str or "")[:16]

    # ── File identity (stat inline) ─────────────────────────────────
    file_size: Any = None
    st_dev: Any = None
    st_ino: Any = None
    if active_read_entry is not None:
        file_size = active_read_entry.get("active_read_file_size")
        st_dev = active_read_entry.get("active_read_st_dev")
        st_ino = active_read_entry.get("active_read_st_ino")
    elif path_str:
        try:
            _st = os.stat(path_str)
            file_size = _st.st_size
            st_dev = _st.st_dev
            st_ino = _st.st_ino
        except OSError:
            pass

    # ── Thread / process CPU ────────────────────────────────────────
    _same_tid = bool(before.tid and before.tid == after_tid)
    _has_thread_cpu = before.thread_time_ns is not None and after_thread_time_ns is not None
    _has_process_cpu = before.process_time_ns is not None and after_process_time_ns is not None

    thread_cpu_ms: Any = None
    if active_read_entry is not None:
        thread_cpu_ms = active_read_entry.get("active_read_thread_cpu_ms")
    elif _has_thread_cpu and _same_tid:
        thread_cpu_ms = round((after_thread_time_ns - before.thread_time_ns) / 1_000_000, 3)

    process_cpu_ms: Any = None
    if active_read_entry is not None:
        process_cpu_ms = active_read_entry.get("active_read_process_cpu_ms")
    elif _has_process_cpu:
        process_cpu_ms = round((after_process_time_ns - before.process_time_ns) / 1_000_000, 3)

    # ── Counter deltas (rusage + io) ────────────────────────────────
    rchar_delta: Any = None
    read_bytes_delta: Any = None
    minor_faults_delta: Any = None
    major_faults_delta: Any = None
    inblock_delta: Any = None
    voluntary_cs_delta: Any = None
    involuntary_cs_delta: Any = None

    if active_read_entry is not None:
        rchar_delta = active_read_entry.get("active_read_rchar_delta")
        read_bytes_delta = active_read_entry.get("active_read_read_bytes_delta")
        major_faults_delta = active_read_entry.get("active_read_major_faults_delta")
        minor_faults_delta = active_read_entry.get("active_read_minor_faults_delta")
        inblock_delta = active_read_entry.get("active_read_inblock_delta")
        voluntary_cs_delta = active_read_entry.get("active_read_voluntary_context_switches_delta")
        involuntary_cs_delta = active_read_entry.get("active_read_involuntary_context_switches_delta")
    elif _same_tid and before_rusage is not None and after_rusage is not None:
        _rd = _compute_rusage_deltas_simple(before_rusage, after_rusage)
        if _rd:
            minor_faults_delta = _rd.get("minflt")
            major_faults_delta = _rd.get("majflt")
            inblock_delta = _rd.get("inblock")
            voluntary_cs_delta = _rd.get("nvcsw")
            involuntary_cs_delta = _rd.get("nivcsw")
    if _same_tid and before_io is not None and after_io is not None:
        _iod = _compute_io_deltas_simple(before_io, after_io)
        if _iod:
            rchar_delta = _iod.get("rchar")
            read_bytes_delta = _iod.get("read_bytes")

    # ── /proc/meminfo (threshold-gated) ─────────────────────────────
    _meminfo = _read_proc_meminfo_cached_available()
    cached_kb: Any = _meminfo.get("cached_kb") if _meminfo else None
    mem_available_kb: Any = _meminfo.get("mem_available_kb") if _meminfo else None

    # ── Cgroup v2 memory.stat (threshold-gated) ──────────────────────
    _cgroup = _read_cgroup_memory_stat()
    memory_file_bytes: Any = _cgroup.get("file") if _cgroup else None
    inactive_file_bytes: Any = _cgroup.get("inactive_file") if _cgroup else None
    active_file_bytes: Any = _cgroup.get("active_file") if _cgroup else None
    workingset_refault_file: Any = _cgroup.get("workingset_refault_file") if _cgroup else None
    workingset_activate_file: Any = _cgroup.get("workingset_activate_file") if _cgroup else None
    pgfault: Any = _cgroup.get("pgfault") if _cgroup else None
    pgmajfault: Any = _cgroup.get("pgmajfault") if _cgroup else None

    # ── Modal identity ──────────────────────────────────────────────
    modal_task_id = os.environ.get("MODAL_TASK_ID", "")
    modal_image_id = os.environ.get("MODAL_IMAGE_ID", "")
    cloud = os.environ.get("MODAL_CLOUD_PROVIDER", "")
    region = os.environ.get("MODAL_REGION", "")

    # ── Per-dimension independent status ────────────────────────────
    # Each dimension is classified independently using classify_active_read_dims.
    _is_linux = platform.system() == "Linux"
    _dim_statuses = classify_active_read_dims(
        deep_diag=True,
        before_tid=before.tid,
        after_tid=after_tid,
        has_thread_cpu=bool(_has_thread_cpu and _same_tid and thread_cpu_ms is not None),
        has_process_cpu=bool(_has_process_cpu and process_cpu_ms is not None),
        has_rusage=bool(_same_tid and any(v is not None for v in (
            minor_faults_delta, major_faults_delta, inblock_delta,
            voluntary_cs_delta, involuntary_cs_delta,
        ))),
        has_io=bool(_same_tid and any(v is not None for v in (
            rchar_delta, read_bytes_delta,
        ))),
        has_cgroup=bool(_cgroup is not None and memory_file_bytes is not None),
        os_supports_thread_cpu=_is_linux,
        os_supports_process_cpu=_is_linux,
        os_supports_rusage=_is_linux,
        os_supports_io=_is_linux,
        os_supports_cgroup=_is_linux,
    )

    # ── Aggregate counter_status (backward-compatible) ──────────────
    _counters_available = {k: v == "available" for k, v in _dim_statuses.items()
                           if k not in ("cgroup_aggregate",)}
    _valid_count = sum(1 for v in _counters_available.values() if v)
    _total_count = len(_counters_available) if _counters_available else 0

    if not _is_linux:
        counter_status: str = "unsupported"
    elif _valid_count == _total_count:
        counter_status = "available"
    elif _valid_count > 0:
        counter_status = "partial"
    else:
        counter_status = "unavailable"

    # ── thread_cpu_ratio and classification ─────────────────────────
    # Ratio = valid thread CPU delta / elapsed wall duration (both in ms).
    # classification: cpu_bound >= 0.80, wait_bound <= 0.20, mixed otherwise,
    # unknown when thread CPU unavailable.
    thread_cpu_ratio: float | str | None = None
    classification: str = "unknown"
    if elapsed_ms is not None and elapsed_ms > 0 and thread_cpu_ms is not None:
        _ratio = thread_cpu_ms / elapsed_ms
        thread_cpu_ratio = round(_ratio, 4)
        if _ratio >= 0.80:
            classification = "cpu_bound"
        elif _ratio <= 0.20:
            classification = "wait_bound"
        else:
            classification = "mixed"
    elif not _dim_statuses.get("thread_cpu", "") == "available":
        classification = "unknown"
    elif elapsed_ms is not None and elapsed_ms > 0 and thread_cpu_ms is not None:
        classification = "unknown"
    else:
        classification = "unknown"

    pid = os.getpid()
    native_thread_id = after_tid

    print(
        f"[v2.slow_model_read] "
        f"owner={owner} "
        f"loader_type={loader_type} "
        f"path_hash={path_hash} "
        f"file_size={file_size} "
        f"st_dev={st_dev} "
        f"st_ino={st_ino} "
        f"request_id={request_id} "
        f"restore_session_id={restore_session_id} "
        f"restored_instance_id={restored_instance_id} "
        f"modal_task_id={modal_task_id} "
        f"modal_image_id={modal_image_id} "
        f"cloud={cloud} "
        f"region={region} "
        f"pid={pid} "
        f"native_thread_id={native_thread_id} "
        f"elapsed_ms={elapsed_ms} "
        f"thread_cpu_ms={thread_cpu_ms} "
        f"process_cpu_ms={process_cpu_ms} "
        f"thread_cpu_ratio={thread_cpu_ratio} "
        f"classification={classification} "
        f"rchar_delta={rchar_delta} "
        f"read_bytes_delta={read_bytes_delta} "
        f"minor_faults_delta={minor_faults_delta} "
        f"major_faults_delta={major_faults_delta} "
        f"inblock_delta={inblock_delta} "
        f"voluntary_cs_delta={voluntary_cs_delta} "
        f"involuntary_cs_delta={involuntary_cs_delta} "
        f"memory_file_bytes={memory_file_bytes} "
        f"inactive_file_bytes={inactive_file_bytes} "
        f"active_file_bytes={active_file_bytes} "
        f"workingset_refault_file={workingset_refault_file} "
        f"workingset_activate_file={workingset_activate_file} "
        f"pgfault={pgfault} "
        f"pgmajfault={pgmajfault} "
        f"cached_kb={cached_kb} "
        f"mem_available_kb={mem_available_kb} "
        f"counter_status={counter_status} "
        f"dim_thread_cpu={_dim_statuses.get('thread_cpu', 'unknown')} "
        f"dim_process_cpu={_dim_statuses.get('process_cpu', 'unknown')} "
        f"dim_io_deltas={_dim_statuses.get('io_deltas', 'unknown')} "
        f"dim_page_faults={_dim_statuses.get('page_faults', 'unknown')} "
        f"dim_block_input={_dim_statuses.get('block_input', 'unknown')} "
        f"dim_context_switches={_dim_statuses.get('context_switches', 'unknown')} "
        f"dim_cgroup_memory={_dim_statuses.get('cgroup_memory', 'unknown')} "
        f"cgroup_aggregate={_dim_statuses.get('cgroup_aggregate', 'unknown')}",
        flush=True,
    )


# ── Background UNET diagnostic helpers ─────────────────────────────


def _make_bg_unet_diag_context(
    *,
    canonical_key: str,
    diagnostic_id: str,
    restored_instance_id: str,
    restore_session_id: str,
    modal_task_id: str = "",
) -> dict[str, Any]:
    """Return a metadata dict shared across all background UNET diagnostic events."""
    return {
        "canonical_key": canonical_key,
        "diagnostic_id": diagnostic_id,
        "restored_instance_id": restored_instance_id,
        "restore_session_id": restore_session_id,
        "modal_task_id": modal_task_id,
        "pid": os.getpid(),
        "native_tid": _capture_tid(),
        "hostname": platform.node(),
    }


# ── Summary emission helpers (one-line compact summaries) ──────────


def _collect_restore_events_for_summary(
    trace: RuntimeTrace,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Scan trace events for restore-breakdown and CLIP-stage timestamps.

    Returns ``(breakdown_dict, clip_stages_dict)``.  Missing stages are
    reported as ``None``; absent lanes as ``"absent"``.
    """
    breakdown: dict[str, Any] = {}
    clip: dict[str, Any] = {}
    # Iterate events and capture timestamps
    for evt in trace.events:
        if evt.name == "v2_bootstrap_restore_start":
            breakdown["bootstrap_start_ns"] = evt.monotonic_ns
        elif evt.name == "v2_bootstrap_restore_end":
            breakdown["bootstrap_end_ns"] = evt.monotonic_ns
        elif evt.name == "v2_unet_cache_patch_start":
            breakdown["unet_cache_patch_start_ns"] = evt.monotonic_ns
        elif evt.name == "v2_unet_cache_patch_end":
            breakdown["unet_cache_patch_end_ns"] = evt.monotonic_ns
        elif evt.name == "v2_clip_prepare_submit_start":
            breakdown["clip_prepare_submit_start_ns"] = evt.monotonic_ns
        elif evt.name == "v2_clip_prepare_submit_end":
            breakdown["clip_prepare_submit_end_ns"] = evt.monotonic_ns
        elif evt.name == "v2_clip_worker_wait_start":
            breakdown["clip_worker_wait_start_ns"] = evt.monotonic_ns
            clip["worker_wait_start_ns"] = evt.monotonic_ns
        elif evt.name == "v2_clip_worker_wait_end":
            breakdown["clip_worker_wait_end_ns"] = evt.monotonic_ns
            clip["worker_wait_end_ns"] = evt.monotonic_ns
        elif evt.name == "v2_clip_ready":
            clip["ready_ns"] = evt.monotonic_ns
        elif evt.name == "v2_unet_spec_extract_start":
            breakdown["unet_spec_extract_start_ns"] = evt.monotonic_ns
        elif evt.name == "v2_unet_spec_extract_end":
            breakdown["unet_spec_extract_end_ns"] = evt.monotonic_ns
        elif evt.name == "v2_background_unet_submit_start":
            breakdown["bg_unet_submit_start_ns"] = evt.monotonic_ns
        elif evt.name == "v2_background_unet_submit_end":
            breakdown["bg_unet_submit_end_ns"] = evt.monotonic_ns
        elif evt.name == "v2_restore_finalize_start":
            breakdown["restore_finalize_start_ns"] = evt.monotonic_ns
        elif evt.name == "v2_restore_finalize_end":
            breakdown["restore_finalize_end_ns"] = evt.monotonic_ns

    # Convert to ms where pairs exist
    result_breakdown: dict[str, Any] = {}
    _PAIRS = [
        ("bootstrap_ms", "bootstrap_start_ns", "bootstrap_end_ns"),
        ("unet_cache_patch_ms", "unet_cache_patch_start_ns", "unet_cache_patch_end_ns"),
        ("clip_prepare_submit_ms", "clip_prepare_submit_start_ns", "clip_prepare_submit_end_ns"),
        ("clip_worker_wait_ms", "clip_worker_wait_start_ns", "clip_worker_wait_end_ns"),
        ("unet_spec_extract_ms", "unet_spec_extract_start_ns", "unet_spec_extract_end_ns"),
        ("bg_unet_submit_ms", "bg_unet_submit_start_ns", "bg_unet_submit_end_ns"),
        ("restore_finalize_ms", "restore_finalize_start_ns", "restore_finalize_end_ns"),
    ]
    for key, start_key, end_key in _PAIRS:
        s = breakdown.get(start_key)
        e = breakdown.get(end_key)
        result_breakdown[key] = round((e - s) / 1_000_000, 3) if (s and e) else None

    # CLIP stages
    result_clip: dict[str, Any] = {
        "worker_queue_ms": None,
        "load_torch_file_ms": None,
        "read_to_ready_ms": None,
        "post_read_cpu_prepare_ms": None,
        "gpu_wait_ms": None,
        "gpu_commit_ms": None,
        "read_end_to_ready_ms": None,
        "worker_total_ms": None,
        "worker_close_wait_ms": result_breakdown.get("clip_worker_wait_ms"),
        "restore_finalization_ms": result_breakdown.get("restore_finalize_ms"),
    }
    for evt in trace.events:
        _meta = evt.metadata if hasattr(evt, "metadata") else {}
        if evt.name == "read_start" and _meta.get("lane") == "CLIP":
            clip["read_start_ns"] = evt.monotonic_ns
        elif evt.name == "read_end" and _meta.get("lane") == "CLIP":
            clip["read_end_ns"] = evt.monotonic_ns
        elif evt.name == "cpu_prepare_start" and _meta.get("lane") == "CLIP":
            clip["cpu_prepare_start_ns"] = evt.monotonic_ns
        elif evt.name == "cpu_prepare_end" and _meta.get("lane") == "CLIP":
            clip["cpu_prepare_end_ns"] = evt.monotonic_ns
        elif evt.name == "gpu_lane_wait_start" and _meta.get("lane") == "CLIP":
            clip["gpu_wait_start_ns"] = evt.monotonic_ns
        elif evt.name == "gpu_lane_wait_end" and _meta.get("lane") == "CLIP":
            clip["gpu_wait_end_ns"] = evt.monotonic_ns
        elif evt.name == "gpu_commit_start" and _meta.get("lane") == "CLIP":
            clip["gpu_commit_start_ns"] = evt.monotonic_ns
        elif evt.name == "gpu_commit_end" and _meta.get("lane") == "CLIP":
            clip["gpu_commit_end_ns"] = evt.monotonic_ns
        elif evt.name == "submitted" and _meta.get("lane") == "CLIP":
            clip["submitted_ns"] = evt.monotonic_ns
        elif evt.name == "preload_worker_started" and _meta.get("lane") == "clip":
            clip["worker_start_ns"] = evt.monotonic_ns
        elif evt.name == "clip_prepare_start":
            clip["worker_body_start_ns"] = evt.monotonic_ns
        elif evt.name == "clip_prepare_end":
            clip["worker_body_end_ns"] = evt.monotonic_ns

    rs = clip.get("read_start_ns")
    re = clip.get("read_end_ns")
    cps = clip.get("cpu_prepare_start_ns")
    cpe = clip.get("cpu_prepare_end_ns")
    gws = clip.get("gpu_wait_start_ns")
    gwe = clip.get("gpu_wait_end_ns")
    gcs = clip.get("gpu_commit_start_ns")
    gce = clip.get("gpu_commit_end_ns")
    rdy = clip.get("ready_ns")
    wws = clip.get("worker_wait_start_ns")
    wwe = clip.get("worker_wait_end_ns")

    if rs and rdy:
        result_clip["read_to_ready_ms"] = round((rdy - rs) / 1_000_000, 3)
    if cps and cpe:
        result_clip["post_read_cpu_prepare_ms"] = round((cpe - cps) / 1_000_000, 3)
    if gws and gwe:
        result_clip["gpu_wait_ms"] = round((gwe - gws) / 1_000_000, 3)
    if gcs and gce:
        result_clip["gpu_commit_ms"] = round((gce - gcs) / 1_000_000, 3)
    if re and rdy:
        result_clip["read_end_to_ready_ms"] = round((rdy - re) / 1_000_000, 3)
    if wws and wwe:
        result_clip["worker_close_wait_ms"] = round((wwe - wws) / 1_000_000, 3)
    if rs and re:
        result_clip["load_torch_file_ms"] = round((re - rs) / 1_000_000, 3)
    if clip.get("submitted_ns") and clip.get("worker_start_ns"):
        result_clip["worker_queue_ms"] = round((clip["worker_start_ns"] - clip["submitted_ns"]) / 1_000_000, 3)
    if clip.get("worker_body_start_ns") and clip.get("worker_body_end_ns"):
        result_clip["worker_total_ms"] = round((clip["worker_body_end_ns"] - clip["worker_body_start_ns"]) / 1_000_000, 3)

    return result_breakdown, result_clip


# ── CLIP CPU children compact summary ────────────────────────────────


def _emit_clip_cpu_children_summary(
    *,
    post_read_total_ms: float | None = None,
    file_read_total_ms: float | None = None,
    children: list[tuple[str, float]] | None = None,
    load_text_encoder_state_dicts_ms: float | None = None,
    detect_te_model_ms: float | None = None,
    state_dict_conversion_ms: float | None = None,
    clip_constructor_ms: float | None = None,
    model_patcher_ms: float | None = None,
    cache_publish_ms: float | None = None,
    cond_stage_model_init_ms: float | None = None,
    tokenizer_init_ms: float | None = None,
    load_sd_weights_ms: float | None = None,
    constructor_residual_ms: float | None = None,
    measured_children_ms: float = 0.0,
    residual_ms: float = 0.0,
    status: str = "ok",
) -> None:
    """Emit a compact [v2.clip_cpu_children] diagnostic line.

    Named stage fields are printed as-is (None when unavailable).
    *children* is rendered as an inline dict for compactness.

    Phase 3 fields:
      cond_stage_model_init_ms — time spent in ``target.clip(...)``
      tokenizer_init_ms — time spent in ``target.tokenizer(...)``
      load_sd_weights_ms — time spent in ``self.load_sd(...)``
      constructor_residual_ms — unattributed time inside CLIP.__init__
        after subtracting known children: clip_constructor_ms minus
        (cond_stage_model_init_ms + tokenizer_init_ms +
         load_sd_weights_ms + model_patcher_ms).  None when
        clip_constructor_ms is unavailable.
    """
    _children_dict: dict[str, float] = {}
    if children:
        for _name, _dur in children:
            _children_dict[_name] = round(_dur, 3)

    print(
        f"[v2.clip_cpu_children] "
        f"post_read_total_ms={post_read_total_ms} "
        f"file_read_total_ms={file_read_total_ms} "
        f"measured_children_ms={measured_children_ms} "
        f"residual_ms={residual_ms} "
        f"load_text_encoder_state_dicts_ms={load_text_encoder_state_dicts_ms} "
        f"detect_te_model_ms={detect_te_model_ms} "
        f"state_dict_conversion_ms={state_dict_conversion_ms} "
        f"clip_constructor_ms={clip_constructor_ms} "
        f"cond_stage_model_init_ms={cond_stage_model_init_ms} "
        f"tokenizer_init_ms={tokenizer_init_ms} "
        f"load_sd_weights_ms={load_sd_weights_ms} "
        f"model_patcher_ms={model_patcher_ms} "
        f"constructor_residual_ms={constructor_residual_ms} "
        f"cache_publish_ms={cache_publish_ms} "
        f"children={_children_dict} "
        f"status={status}",
        flush=True,
    )


# ── Background UNET IO/stages summary emission ──────────────────────


def _emit_bg_unet_io_summary(trace: RuntimeTrace, *, canonical_key: str = "",
                               target_path: str = "", force: bool = False) -> None:
    """Emit a compact [v2.bg_unet_io] line from trace events.

    Summarises file stat, open, mmap, safetensors open/parse/header,
    tensor enumeration, tensor materialization, dtype_conversion,
    state_dict_assembly, model_config, model_construction,
    load_model_weights, post_load_cleanup, cache_publish durations.
    Missing stages → None.  Only emits when deep diag produced
    events or *force* is True.

    Each stage reports wall_ms, thread_cpu_ms, process_cpu_ms,
    thread_cpu_ratio, tensor_count, materialized_bytes, source_dtype,
    and destination_dtype where applicable from trace event metadata.

    NOTE: file_open and mmap_create are always None/absent because the real
    safetensors/torch.load implementations do not expose separable Python-callable
    boundaries for these stages.  They are listed only for forward compatibility
    — do not emit synthetic values.
    """
    if not force and not _DIAGNOSTIC_FLAG:
        return
    stages: dict[str, Any] = {
        "file_stat_ms": None, "file_open_ms": None,
        "mmap_create_ms": None, "safetensors_open_ms": None,
        "safetensors_parse_ms": None, "header_parse_ms": None,
        "tensor_enumeration_ms": None,
        "tensor_materialization_ms": None,
        "dtype_conversion_ms": None,
        "state_dict_assembly_ms": None,
        "model_config_ms": None, "model_construction_ms": None,
        "load_model_weights_ms": None,
        "post_load_cleanup_ms": None, "cache_publish_ms": None,
        "safetensors_combined_ms": None,
        "load_torch_file_ms": None, "stage_split_available": None,
        "wall_ms": None, "thread_cpu_ms": None, "process_cpu_ms": None,
        "thread_cpu_ratio": None,
        "tensor_count": None, "materialized_bytes": None,
        "source_dtype": None, "destination_dtype": None,
    }
    _worker_wall_start_ns = 0
    _worker_wall_end_ns = 0
    _worker_thread_start_ns = 0
    _worker_thread_end_ns = 0
    _worker_proc_start_ns = 0
    _worker_proc_end_ns = 0
    events = trace.events
    for i, evt in enumerate(events):
        _meta = evt.metadata if hasattr(evt, "metadata") else {}
        if evt.name == "background_unet_worker_start":
            _worker_wall_start_ns = evt.monotonic_ns
            _worker_thread_start_ns = _meta.get("thread_time_ns", 0) if _meta else 0
            _worker_proc_start_ns = _meta.get("process_time_ns", 0) if _meta else 0
        elif evt.name == "background_unet_worker_end":
            _worker_wall_end_ns = evt.monotonic_ns
            _worker_thread_end_ns = _meta.get("thread_time_ns", 0) if _meta else 0
            _worker_proc_end_ns = _meta.get("process_time_ns", 0) if _meta else 0
        # unet_file_stat_start -> unet_file_stat_end
        if evt.name == "unet_file_stat_start":
            for j in range(i + 1, min(i + 20, len(events))):
                if events[j].name == "unet_file_stat_end":
                    stages["file_stat_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_file_open_start":
            for j in range(i + 1, min(i + 20, len(events))):
                if events[j].name == "unet_file_open_end":
                    stages["file_open_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_mmap_create_start":
            for j in range(i + 1, min(i + 20, len(events))):
                if events[j].name == "unet_mmap_create_end":
                    stages["mmap_create_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_safetensors_open_start":
            for j in range(i + 1, min(i + 80, len(events))):
                if events[j].name == "unet_safetensors_open_end":
                    stages["safetensors_open_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_safetensors_parse_start":
            for j in range(i + 1, min(i + 40, len(events))):
                if events[j].name == "unet_safetensors_parse_end":
                    stages["safetensors_parse_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    stages["stage_split_available"] = _meta.get("stage_split_available", False)
                    stages["tensor_count"] = _meta.get("tensor_count", stages["tensor_count"])
                    break
        elif evt.name == "unet_header_parse_start":
            for j in range(i + 1, min(i + 40, len(events))):
                if events[j].name == "unet_header_parse_end":
                    stages["header_parse_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    stages["source_dtype"] = _meta.get("source_dtype", stages["source_dtype"])
                    stages["destination_dtype"] = _meta.get("destination_dtype", stages["destination_dtype"])
                    break
        elif evt.name == "unet_tensor_enumeration_start":
            for j in range(i + 1, min(i + 200, len(events))):
                if events[j].name == "unet_tensor_enumeration_end":
                    stages["tensor_enumeration_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    stages["tensor_count"] = _meta.get("tensor_count", stages["tensor_count"])
                    break
        elif evt.name == "unet_tensor_materialize_aggregated":
            stages["tensor_count"] = _meta.get("tensor_count", stages["tensor_count"])
            stages["materialized_bytes"] = _meta.get("total_bytes", stages["materialized_bytes"])
        elif evt.name == "unet_tensor_materialize_start":
            for j in range(i + 1, min(i + 200, len(events))):
                if events[j].name == "unet_tensor_materialize_end":
                    _prev = stages.get("tensor_materialization_ms", 0) or 0
                    stages["tensor_materialization_ms"] = round(
                        _prev + (events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_dtype_conversion_start":
            for j in range(i + 1, min(i + 100, len(events))):
                if events[j].name == "unet_dtype_conversion_end":
                    stages["dtype_conversion_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    stages["source_dtype"] = _meta.get("source_dtype", stages["source_dtype"])
                    stages["destination_dtype"] = _meta.get("destination_dtype", stages["destination_dtype"])
                    break
        elif evt.name == "unet_state_dict_assembly_start":
            for j in range(i + 1, min(i + 100, len(events))):
                if events[j].name == "unet_state_dict_assembly_end":
                    stages["state_dict_assembly_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_model_config_start":
            for j in range(i + 1, min(i + 100, len(events))):
                if events[j].name == "unet_model_config_end":
                    stages["model_config_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_load_diffusion_model_state_dict_start":
            for j in range(i + 1, min(i + 300, len(events))):
                if events[j].name == "unet_load_diffusion_model_state_dict_end":
                    stages["model_construction_ms"] = events[j].metadata.get("duration_ms", 0) if hasattr(events[j], "metadata") else 0
                    break
        elif evt.name == "unet_load_model_weights_end":
            stages["load_model_weights_ms"] = _meta.get("duration_ms", stages["load_model_weights_ms"])
        elif evt.name == "unet_post_load_cleanup_start":
            for j in range(i + 1, min(i + 50, len(events))):
                if events[j].name == "unet_post_load_cleanup_end":
                    stages["post_load_cleanup_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_cache_publish_start":
            for j in range(i + 1, min(i + 100, len(events))):
                if events[j].name == "unet_cache_publish_end":
                    stages["cache_publish_ms"] = round((events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_safetensors_load_combined_start":
            for j in range(i + 1, min(i + 200, len(events))):
                if events[j].name == "unet_safetensors_load_combined_end":
                    stages["safetensors_combined_ms"] = round(
                        (events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    stages["stage_split_available"] = False
                    break
        elif evt.name == "unet_load_torch_file_start":
            for j in range(i + 1, min(i + 200, len(events))):
                if events[j].name == "unet_load_torch_file_end":
                    stages["load_torch_file_ms"] = round(
                        (events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break

    # ── Worker wall, thread CPU, process CPU, ratio ─────────────────
    if _worker_wall_start_ns and _worker_wall_end_ns:
        _wall_ms = round((_worker_wall_end_ns - _worker_wall_start_ns) / 1_000_000, 3)
        stages["wall_ms"] = _wall_ms
        if _worker_thread_start_ns and _worker_thread_end_ns:
            _tcpu = round((_worker_thread_end_ns - _worker_thread_start_ns) / 1_000_000, 3)
            stages["thread_cpu_ms"] = _tcpu
            if _wall_ms > 0:
                stages["thread_cpu_ratio"] = round(_tcpu / _wall_ms, 4)
        if _worker_proc_start_ns and _worker_proc_end_ns:
            stages["process_cpu_ms"] = round((_worker_proc_end_ns - _worker_proc_start_ns) / 1_000_000, 3)

    print(
        f"[v2.bg_unet_io] "
        f"file_stat_ms={stages['file_stat_ms']} "
        f"file_open_ms={stages['file_open_ms']} "
        f"mmap_create_ms={stages['mmap_create_ms']} "
        f"safetensors_open_ms={stages['safetensors_open_ms']} "
        f"safetensors_parse_ms={stages['safetensors_parse_ms']} "
        f"header_parse_ms={stages['header_parse_ms']} "
        f"tensor_enumeration_ms={stages['tensor_enumeration_ms']} "
        f"tensor_materialization_ms={stages['tensor_materialization_ms']} "
        f"dtype_conversion_ms={stages['dtype_conversion_ms']} "
        f"state_dict_assembly_ms={stages['state_dict_assembly_ms']} "
        f"model_config_ms={stages['model_config_ms']} "
        f"model_construction_ms={stages['model_construction_ms']} "
        f"load_model_weights_ms={stages['load_model_weights_ms']} "
        f"post_load_cleanup_ms={stages['post_load_cleanup_ms']} "
        f"cache_publish_ms={stages['cache_publish_ms']} "
        f"safetensors_combined_ms={stages['safetensors_combined_ms']} "
        f"load_torch_file_ms={stages['load_torch_file_ms']} "
        f"stage_split_available={stages['stage_split_available']} "
        f"wall_ms={stages['wall_ms']} "
        f"thread_cpu_ms={stages['thread_cpu_ms']} "
        f"process_cpu_ms={stages['process_cpu_ms']} "
        f"thread_cpu_ratio={stages['thread_cpu_ratio']} "
        f"tensor_count={stages['tensor_count']} "
        f"materialized_bytes={stages['materialized_bytes']} "
        f"source_dtype={stages['source_dtype']} "
        f"destination_dtype={stages['destination_dtype']} "
        f"canonical_key={canonical_key[-32:] if canonical_key else ''}",
        flush=True,
    )


def _emit_bg_unet_stages_summary(trace: RuntimeTrace, *, canonical_key: str = "",
                                   weight_dtype: str = "", force: bool = False) -> None:
    """Emit compact [v2.bg_unet_stages] line from trace events.

    Summarises worker queue, model construction subfunction durations, GPU commit,
    and cache publication.  Missing stages → None.
    Zero-valued stages (e.g. post_load_cleanup_ms) are reported as 0.0, not None.
    """
    if not force and not _DIAGNOSTIC_FLAG:
        return
    stages: dict[str, Any] = {
        "submission_to_worker_start_ms": None,
        "worker_wall_ms": None, "worker_thread_cpu_ms": None,
        "model_construction_total_ms": None,
        "measured_direct_children_ms": None,
        "model_construction_residual_ms": None,
        "model_config_get_model_ms": None,
        "load_model_weights_ms": None,
        "load_torch_file_ms": None,
        "convert_old_quants_ms": None,
        "model_patcher_constructor_ms": None,
        "model_to_ms": None,
        "state_dict_prefix_replace_ms": None,
        "post_load_cleanup_ms": None,
        "fast_children_le_1ms": 0.0,
        "gpu_lane_wait_ms": None, "gpu_commit_ms": None,
        "cache_publish_ms": None,
        "background_gpu_transfer_present": False,
        "thread_cpu_ms": None, "process_cpu_ms": None,
        "thread_cpu_ratio": None,
        "weight_dtype": weight_dtype,
    }
    events = trace.events
    _submitted_ns = 0
    _worker_start_ns = 0
    _worker_end_ns = 0
    _worker_thread_start_ns = 0
    _worker_thread_end_ns = 0
    _worker_proc_start_ns = 0
    _worker_proc_end_ns = 0
    _gpu_wait_start = 0
    _gpu_wait_end = 0
    _gpu_commit_start = 0
    _gpu_commit_end = 0
    _cache_pub_start = 0
    _cache_pub_end = 0
    _sd_total = 0.0
    _children_total = 0.0
    _sd_found = False

    for i, evt in enumerate(events):
        _meta = evt.metadata if hasattr(evt, "metadata") else {}
        if evt.name == "background_unet_submitted":
            _submitted_ns = evt.monotonic_ns
        elif evt.name == "background_unet_worker_start":
            _worker_start_ns = evt.monotonic_ns
            _worker_thread_start_ns = _meta.get("thread_time_ns", 0)
            _worker_proc_start_ns = _meta.get("process_time_ns", 0)
        elif evt.name == "background_unet_worker_end":
            _worker_end_ns = evt.monotonic_ns
            _worker_thread_end_ns = _meta.get("thread_time_ns", 0)
            _worker_proc_end_ns = _meta.get("process_time_ns", 0)
        elif evt.name == "unet_gpu_lane_wait_start":
            _gpu_wait_start = evt.monotonic_ns
        elif evt.name == "unet_gpu_lane_wait_end":
            _gpu_wait_end = evt.monotonic_ns
        elif evt.name == "unet_gpu_commit_start":
            _gpu_commit_start = evt.monotonic_ns
        elif evt.name == "unet_gpu_commit_end":
            _gpu_commit_end = evt.monotonic_ns
        elif evt.name == "unet_cache_publish_start":
            _cache_pub_start = evt.monotonic_ns
        elif evt.name == "unet_cache_publish_end":
            _cache_pub_end = evt.monotonic_ns
        elif evt.name == "unet_load_diffusion_model_state_dict_start":
            _sd_start = evt.monotonic_ns
            for j in range(i + 1, min(i + 300, len(events))):
                if events[j].name == "unet_load_diffusion_model_state_dict_end":
                    _sd_found = True
                    _sd_total = events[j].metadata.get("duration_ms", 0) if hasattr(events[j], "metadata") else 0
                    _children_total = events[j].metadata.get("measured_child_total_ms", 0) if hasattr(events[j], "metadata") else 0
                    break
        elif evt.name == "unet_model_config_get_model_end":
            _val = evt.metadata.get("duration_ms")
            if _val is not None:
                stages["model_config_get_model_ms"] = (stages["model_config_get_model_ms"] or 0) + _val
        elif evt.name == "unet_load_model_weights_end":
            _val = evt.metadata.get("duration_ms")
            if _val is not None:
                stages["load_model_weights_ms"] = (stages["load_model_weights_ms"] or 0) + _val
        elif evt.name == "unet_state_dict_prefix_replace_end":
            _val = evt.metadata.get("duration_ms")
            if _val is not None:
                stages["state_dict_prefix_replace_ms"] = (stages["state_dict_prefix_replace_ms"] or 0) + _val
        elif evt.name == "unet_convert_old_quants_end":
            _val = evt.metadata.get("duration_ms")
            if _val is not None:
                stages["convert_old_quants_ms"] = (stages["convert_old_quants_ms"] or 0) + _val
        elif evt.name == "unet_model_patcher_constructor_end":
            _val = evt.metadata.get("duration_ms")
            if _val is not None:
                stages["model_patcher_constructor_ms"] = (stages["model_patcher_constructor_ms"] or 0) + _val
        elif evt.name == "unet_model_to_end":
            _val = evt.metadata.get("duration_ms")
            if _val is not None:
                stages["model_to_ms"] = (stages["model_to_ms"] or 0) + _val
        elif evt.name == "unet_load_torch_file_start":
            for j in range(i + 1, min(i + 200, len(events))):
                if events[j].name == "unet_load_torch_file_end":
                    stages["load_torch_file_ms"] = round(
                        (events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
                    break
        elif evt.name == "unet_post_load_cleanup_end":
            _dur = _meta.get("duration_ms")
            if _dur is not None:
                stages["post_load_cleanup_ms"] = round(_dur, 3)

    if _submitted_ns and _worker_start_ns:
        stages["submission_to_worker_start_ms"] = round((_worker_start_ns - _submitted_ns) / 1_000_000, 3)
    if _worker_start_ns and _worker_end_ns:
        _wall_ms = round((_worker_end_ns - _worker_start_ns) / 1_000_000, 3)
        stages["worker_wall_ms"] = _wall_ms
        # Thread CPU from worker_start/end metadata (captured via thread_time_ns)
        if _worker_thread_start_ns and _worker_thread_end_ns:
            _tcpu = round((_worker_thread_end_ns - _worker_thread_start_ns) / 1_000_000, 3)
            stages["thread_cpu_ms"] = _tcpu
            if _wall_ms > 0:
                stages["thread_cpu_ratio"] = round(_tcpu / _wall_ms, 4)
        # Process CPU
        if _worker_proc_start_ns and _worker_proc_end_ns:
            stages["process_cpu_ms"] = round((_worker_proc_end_ns - _worker_proc_start_ns) / 1_000_000, 3)
    if _gpu_wait_start and _gpu_wait_end:
        stages["gpu_lane_wait_ms"] = round((_gpu_wait_end - _gpu_wait_start) / 1_000_000, 3)
        stages["background_gpu_transfer_present"] = True
    if _gpu_commit_start and _gpu_commit_end:
        stages["gpu_commit_ms"] = round((_gpu_commit_end - _gpu_commit_start) / 1_000_000, 3)
        stages["background_gpu_transfer_present"] = True
    if _cache_pub_start and _cache_pub_end:
        stages["cache_publish_ms"] = round((_cache_pub_end - _cache_pub_start) / 1_000_000, 3)

    # Fix falsy-zero bug: when the SD wrapper event was found (even with 0.0),
    # report the literal value; when absent, report None.
    if _sd_found:
        stages["model_construction_total_ms"] = round(_sd_total, 3)
        stages["measured_direct_children_ms"] = round(_children_total, 3)
        stages["model_construction_residual_ms"] = round(_sd_total - _children_total, 3)

    # Separate children >1ms from fast (≤1ms) ones
    _other_named: dict[str, float] = {}
    _fast_total = 0.0
    for _nkey, _nms in (
        ("model_config_get_model", stages["model_config_get_model_ms"]),
        ("load_model_weights", stages["load_model_weights_ms"]),
        ("convert_old_quants", stages["convert_old_quants_ms"]),
        ("state_dict_prefix_replace", stages["state_dict_prefix_replace_ms"]),
        ("model_patcher_constructor", stages["model_patcher_constructor_ms"]),
        ("model_to", stages["model_to_ms"]),
    ):
        if _nms is not None:
            if _nms > 1.0:
                _other_named[_nkey] = round(_nms, 3)
            else:
                _fast_total += _nms
    stages["fast_children_le_1ms"] = round(_fast_total, 3)

    print(
        f"[v2.bg_unet_stages] "
        f"submission_to_worker_start_ms={stages['submission_to_worker_start_ms']} "
        f"worker_wall_ms={stages['worker_wall_ms']} "
        f"model_construction_total_ms={stages['model_construction_total_ms']} "
        f"measured_direct_children_ms={stages['measured_direct_children_ms']} "
        f"model_construction_residual_ms={stages['model_construction_residual_ms']} "
        + " ".join(f"{k}={v}" for k, v in sorted(_other_named.items()))
        + f" gpu_lane_wait_ms={stages['gpu_lane_wait_ms']} "
        f"gpu_commit_ms={stages['gpu_commit_ms']} "
        f"cache_publish_ms={stages['cache_publish_ms']} "
        f"background_gpu_transfer_present={stages['background_gpu_transfer_present']} "
        f"load_torch_file_ms={stages['load_torch_file_ms']} "
        f"post_load_cleanup_ms={stages['post_load_cleanup_ms']} "
        f"thread_cpu_ms={stages['thread_cpu_ms']} "
        f"process_cpu_ms={stages['process_cpu_ms']} "
        f"thread_cpu_ratio={stages['thread_cpu_ratio']} "
        f"fast_children_le_1ms={stages['fast_children_le_1ms']} "
        f"weight_dtype={stages['weight_dtype']} "
        f"canonical_key={canonical_key[-32:] if canonical_key else ''}",
        flush=True,
    )


@dataclass
class PreparationDiagnostics:
    unet_started_at: float = 0.0
    unet_completed_at: float = 0.0
    clip_started_at: float = 0.0
    clip_completed_at: float = 0.0
    vae_started_at: float = 0.0
    vae_completed_at: float = 0.0
    prefill_started_at: float = 0.0
    prefill_completed_at: float = 0.0
    unet_demanded_at: float = 0.0
    clip_demanded_at: float = 0.0
    vae_demanded_at: float = 0.0
    prefill_demanded_at: float = 0.0
    unet_wait_ms: float = 0.0
    clip_wait_ms: float = 0.0
    vae_wait_ms: float = 0.0
    prefill_wait_ms: float = 0.0
    unet_work_completed_before_demand_ms: float = 0.0
    clip_work_completed_before_demand_ms: float = 0.0
    vae_work_completed_before_demand_ms: float = 0.0
    prefill_work_completed_before_demand_ms: float = 0.0
    unet_actual_graph_wait_ms: float = 0.0
    clip_actual_graph_wait_ms: float = 0.0
    vae_actual_graph_wait_ms: float = 0.0
    prefill_actual_graph_wait_ms: float = 0.0
    useful_overlap_ms: float = 0.0
    unused_speculation: bool = False
    unet_error: str = ""
    clip_error: str = ""
    vae_error: str = ""
    prefill_error: str = ""
    prefill_lane_mode: str = ""
    prefill_total_encodes: int = 0
    prefill_skipped_encodes: int = 0
    prefill_skipped_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        for key in (
            "unet_wait_ms", "clip_wait_ms", "vae_wait_ms", "prefill_wait_ms",
            "unet_work_completed_before_demand_ms",
            "clip_work_completed_before_demand_ms",
            "vae_work_completed_before_demand_ms",
            "prefill_work_completed_before_demand_ms",
            "unet_actual_graph_wait_ms",
            "clip_actual_graph_wait_ms",
            "vae_actual_graph_wait_ms",
            "prefill_actual_graph_wait_ms",
            "useful_overlap_ms",
        ):
            data[key] = round(float(data[key]), 3)
        return data


@dataclass
class RestorePreparation:
    model_key: ModelRestoreKey
    prefill_key: PrefillKey
    unet_future: Future[Any] | None = None
    clip_future: Future[Any] | None = None
    vae_future: Future[Any] | None = None
    prefill_future: Future[Any] | None = None
    diagnostics: PreparationDiagnostics = field(default_factory=PreparationDiagnostics)


class ModelPreloadCoordinator:
    """Direct coordinator for restore-time UNET/CLIP/VAE work with mutation lane."""

    def __init__(
        self,
        *,
        unet_loader: Callable[[ModelRestoreKey], Any] | None = None,
        clip_loader: Callable[[ModelRestoreKey], Any] | None = None,
        vae_loader: Callable[[ModelRestoreKey], Any] | None = None,
        prefill_loader: Callable[[PrefillKey, Any], Any] | None = None,
        max_workers: int = 2,
    ) -> None:
        self.unet_loader = unet_loader
        self.clip_loader = clip_loader
        self.vae_loader = vae_loader
        self.prefill_loader = prefill_loader
        self._max_workers = max(1, min(int(max_workers), 3))
        self._pool: ThreadPoolExecutor | None = None
        self._pool_lock = RLock()
        self._active: RestorePreparation | None = None
        self.mutation_lane = _get_mutation_lane()

    def prepare(
        self,
        model_key: ModelRestoreKey,
        prefill_key: PrefillKey,
        *,
        exact_prefill: bool = True,
        prepare_unet: bool = True,
        prepare_clip: bool = True,
        prepare_vae: bool = True,
        trace: RuntimeTrace | None = None,
        expected_read_counts: dict[str, int] | None = None,
    ) -> RestorePreparation:
        """Start restore preparation.

        Submits UNET, CLIP, and (when requested) VAE preparation to the
        worker pool.  Physical reads and CPU‑side model construction run
        in parallel.  GPU/cache mutations are serialised through the
        coordinator-owned ``mutation_lane``.

        *expected_read_counts* — optional per-lane overrides for the
        number of ``load_torch_file`` calls predicted for that lane.
        """
        preparation = RestorePreparation(model_key=model_key, prefill_key=prefill_key)
        self._active = preparation
        _erc = expected_read_counts or {}

        if prepare_unet and self.unet_loader is not None:
            preparation.unet_future = self._submit("unet", lambda: self.unet_loader(model_key), preparation, trace,
                                                    expected_read_count=_erc.get("unet", 1))
        if prepare_clip and self.clip_loader is not None:
            preparation.clip_future = self._submit("clip", lambda: self.clip_loader(model_key), preparation, trace,
                                                    expected_read_count=_erc.get("clip", 2))
        if prepare_vae and self.vae_loader is not None and model_key.vae_identity:
            preparation.vae_future = self._submit("vae", lambda: self.vae_loader(model_key), preparation, trace,
                                                   expected_read_count=_erc.get("vae", 1))
        if exact_prefill and self.prefill_loader is not None and prefill_key.prompt_bundle_hash:
            def prefill() -> Any:
                clip = self.wait_clip(preparation, trace=trace, demand_source="prefill")
                return self.prefill_loader(prefill_key, clip)
            preparation.prefill_future = self._submit("prefill", prefill, preparation, trace,
                                                      expected_read_count=0)
        else:
            preparation.diagnostics.unused_speculation = bool(exact_prefill and self.prefill_loader is None)
        return preparation

    def extend(
        self,
        preparation: RestorePreparation,
        *,
        prepare_unet: bool = True,
        prepare_vae: bool = True,
        trace: RuntimeTrace | None = None,
    ) -> RestorePreparation:
        """Submit only missing lanes on an existing preparation.

        Never resubmits a lane whose future is already present.  The
        existing preparation (model_key, prefill_key, diagnostics, and
        any completed futures) is kept intact.  The thread pool is
        recreated on demand if it was previously closed via ``close()``.
        """
        if preparation is None:
            raise RuntimeError("cannot extend a None preparation")
        self._active = preparation
        submitted: list[str] = []

        if prepare_unet and preparation.unet_future is None and self.unet_loader is not None:
            preparation.unet_future = self._submit(
                "unet", lambda: self.unet_loader(preparation.model_key),
                preparation, trace,
                expected_read_count=1,
            )
            submitted.append("unet")
        if prepare_vae and preparation.vae_future is None and self.vae_loader is not None:
            if preparation.model_key.vae_identity:
                preparation.vae_future = self._submit(
                    "vae", lambda: self.vae_loader(preparation.model_key),
                    preparation, trace,
                    expected_read_count=1,
                )
                submitted.append("vae")

        if trace and submitted:
            trace.emit(
                "preload_extension_submitted",
                phase="restore",
                metadata={"submitted_lanes": submitted},
            )
        elif trace and not submitted:
            trace.emit(
                "preload_extension_skipped",
                phase="restore",
                metadata={"reason": "all_requested_lanes_already_present"},
            )
        return preparation

    def wait_unet(
        self,
        preparation: RestorePreparation | None = None,
        *,
        trace: RuntimeTrace | None = None,
        demand_source: str = "graph",
    ) -> Any:
        prep = preparation or self._require_active()
        return self._wait(prep, "unet", prep.unet_future, trace, demand_source=demand_source)

    def wait_clip(
        self,
        preparation: RestorePreparation | None = None,
        *,
        trace: RuntimeTrace | None = None,
        demand_source: str = "graph",
    ) -> Any:
        prep = preparation or self._require_active()
        return self._wait(prep, "clip", prep.clip_future, trace, demand_source=demand_source)

    def wait_vae(
        self,
        preparation: RestorePreparation | None = None,
        *,
        trace: RuntimeTrace | None = None,
        demand_source: str = "graph",
    ) -> Any:
        prep = preparation or self._require_active()
        return self._wait(prep, "vae", prep.vae_future, trace, demand_source=demand_source)

    def wait_prefill(self, preparation: RestorePreparation | None = None, *, trace: RuntimeTrace | None = None) -> Any:
        prep = preparation or self._require_active()
        return self._wait(prep, "prefill", prep.prefill_future, trace, demand_source="graph")

    def diagnostics(self, preparation: RestorePreparation | None = None) -> dict[str, Any]:
        return (preparation or self._require_active()).diagnostics.to_dict()

    def schedule_prefill(
        self,
        callback: Callable[[], Any],
        preparation: RestorePreparation | None = None,
        *,
        trace: RuntimeTrace | None = None,
    ) -> Future[Any] | None:
        """Schedule execution-phase prefill work.

        Public API: atomically checks whether
        ``preparation.prefill_future`` is already set and, only when None,
        submits *callback* to the worker pool (idempotent).  The critical
        section is minimised to the check-and-set so the non-reentrant
        thread-pool code path never runs while holding the lock.

        The callback typically waits for UNET and CLIP preparation futures
        before doing GPU work.  Returns the future (new or existing), or
        None when no active preparation exists.
        """
        prep = preparation or self._require_active()
        # Atomic check-and-set — lock scope is minimal, never held across
        # the *submit* call (which itself may try to reacquire the lock
        # via _ensure_pool).
        with self._pool_lock:
            if prep.prefill_future is not None:
                return prep.prefill_future
            prep.prefill_future = self._submit(
                "execution_prefill", callback, prep, trace,
                phase="execution", expected_read_count=0,
            )
            return prep.prefill_future

    def close(self) -> None:
        with self._pool_lock:
            pool = self._pool
            self._pool = None
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=False)

    def _ensure_pool(self) -> ThreadPoolExecutor:
        with self._pool_lock:
            if self._pool is None:
                self._pool = ThreadPoolExecutor(
                    max_workers=self._max_workers,
                    thread_name_prefix="comfymodal-restore",
                )
            return self._pool

    def _submit(
        self,
        name: str,
        callback: Callable[[], Any],
        preparation: RestorePreparation,
        trace: RuntimeTrace | None,
        *,
        phase: str = "restore",
        diag_name: str | None = None,
        expected_read_count: int = 1,
        submission_id: str = "",
    ) -> Future[Any]:
        # Normalise diagnostic attribute namespace so execution-preﬁll work
        # uses the static *preﬁll_started_at/completed_at/error* ﬁelds.
        effective_diag = diag_name or name
        if effective_diag == "execution_prefill":
            effective_diag = "prefill"

        # Generate submission identity used in both pre- and post-pool events.
        sid = submission_id or _next_submission_id()

        # Build canonical lane trace (additive — existing events unchanged).
        canonical_lane = _LANE_TO_CANONICAL.get(name, name.upper())
        lane_trace: ModelLaneTrace | None = None
        if trace:
            trace.emit(
                "preload_submitted",
                phase=phase,
                metadata={
                    "lane": name,
                    "submission_id": sid,
                },
            )
            lane_trace = ModelLaneTrace(
                trace, canonical_lane, phase=phase,
                expected_read_count=expected_read_count,
            )
            lane_trace.submitted()

        # Capture monotonic clock just before pool handoff for queue delay.
        _submit_started_ns = time.monotonic_ns()

        def run() -> Any:
            nonlocal callback
            started = time.time()
            _queue_wait_ms = round((time.monotonic_ns() - _submit_started_ns) / 1_000_000, 3)
            setattr(preparation.diagnostics, f"{effective_diag}_started_at", started)
            # ── Activate per-worker lane context ────────────────
            ctx_token = None
            if lane_trace is not None:
                ctx_token = _ACTIVE_LANE_TRACE.set(lane_trace)
            try:
                if trace:
                    trace.emit(f"{name}_prepare_start", phase=phase)
                    trace.emit(
                        "preload_worker_started",
                        phase=phase,
                        metadata={
                            "lane": name,
                            "submission_id": sid,
                            "queue_wait_ms": _queue_wait_ms,
                        },
                    )
                # Install core dispatch wrappers (idempotent per-component,
                # resolves live sys.modules so partial comfy imports cannot
                # block the read wrapper).
                # Skip for execution prefill — wrappers already installed
                # during restore (model-loading lanes).
                if effective_diag != 'prefill':
                    _ensure_core_wrappers(trace=trace)
                # Install UNET post-read decomposition wrappers (Section B).
                # Only active when _ACTIVE_LANE_TRACE is UNET; absent
                # symbols are skipped without breaking loading.
                # UNET-only — execution prefill does not need these.
                if effective_diag == 'unet':
                    _ensure_unet_decompose_wrappers(trace=trace)

                try:
                    result = callback()
                finally:
                    callback = None
                completed = time.time()
                setattr(preparation.diagnostics, f"{effective_diag}_completed_at", completed)
                if trace:
                    trace.emit(f"{name}_prepare_end", phase=phase)
                    trace.emit(
                        "preload_worker_finished",
                        phase=phase,
                        metadata={
                            "lane": name,
                            "worker_duration_ms": round((completed - started) * 1000, 3),
                        },
                    )
                # ── Terminal event (success) ────────────────────
                if lane_trace is not None:
                    lane_trace.ready(
                        worker_duration_ms=round((completed - started) * 1000, 3),
                    )
                return result
            except Exception as exc:
                completed = time.time()
                setattr(preparation.diagnostics, f"{effective_diag}_error", str(exc))
                setattr(preparation.diagnostics, f"{effective_diag}_completed_at", completed)
                if trace:
                    trace.emit(f"{name}_prepare_end", phase=phase, metadata={"error": str(exc)[:200]})
                    trace.emit(
                        "preload_worker_failed",
                        phase=phase,
                        metadata={
                            "lane": name,
                            "error_category": type(exc).__name__,
                            "worker_duration_ms": round((completed - started) * 1000, 3),
                        },
                    )
                # ── Terminal event (failure) ────────────────────
                if lane_trace is not None:
                    lane_trace.failed(
                        error_category=type(exc).__name__,
                        worker_duration_ms=round((completed - started) * 1000, 3),
                    )
                raise
            finally:
                if ctx_token is not None:
                    _ACTIVE_LANE_TRACE.reset(ctx_token)
        return self._ensure_pool().submit(run)

    def _wait(
        self,
        preparation: RestorePreparation,
        name: str,
        future: Future[Any] | None,
        trace: RuntimeTrace | None,
        *,
        demand_source: str = "graph",
    ) -> Any:
        demanded = time.time()
        if demand_source == "graph":
            setattr(preparation.diagnostics, f"{name}_demanded_at", demanded)
        if future is None:
            return None
        wait_started = time.time()
        wait_phase = "execution" if demand_source in {"graph", "execution_prefill"} else "restore"
        if trace:
            trace.emit(
                f"{name}_wait_start",
                phase=wait_phase,
                metadata={"demand_source": demand_source},
            )
        result = future.result()
        completed = getattr(preparation.diagnostics, f"{name}_completed_at")
        wait_ms = max(0.0, (time.time() - wait_started) * 1000.0)
        completed_before_demand_ms = max(0.0, (demanded - completed) * 1000.0)
        setattr(preparation.diagnostics, f"{name}_wait_ms", wait_ms)
        if demand_source == "graph":
            setattr(preparation.diagnostics, f"{name}_actual_graph_wait_ms", wait_ms)
            setattr(
                preparation.diagnostics,
                f"{name}_work_completed_before_demand_ms",
                completed_before_demand_ms,
            )
        if trace:
            trace.emit(
                f"{name}_wait_end",
                phase=wait_phase,
                metadata={
                    "demand_source": demand_source,
                    "wait_ms": round(wait_ms, 3),
                    "completed_before_demand_ms": round(completed_before_demand_ms, 3),
                },
            )
        if name == "unet":
            clip_start = preparation.diagnostics.clip_started_at
            if clip_start and preparation.diagnostics.unet_completed_at:
                preparation.diagnostics.useful_overlap_ms = max(0.0, (preparation.diagnostics.unet_completed_at - clip_start) * 1000.0)
        return result

    def _require_active(self) -> RestorePreparation:
        if self._active is None:
            raise RuntimeError("no active restore preparation")
        return self._active


_ACTIVE_V2_LOADER_BRIDGE: ContextVar["V2LoaderBridge | None"] = ContextVar(
    "comfymodal_active_v2_loader_bridge",
    default=None,
)
_LOADER_MISS = object()


def current_v2_loader_bridge() -> "V2LoaderBridge | None":
    """Return the bridge active for the current graph-execution context."""
    return _ACTIVE_V2_LOADER_BRIDGE.get()


class V2LoaderBridge:
    """Connect restore preparation to ComfyUI's real loader node methods.

    The bridge wraps the already-loaded node classes instead of replacing
    ComfyUI's loader implementation. A matching prepared result is returned;
    every mismatch, missing plan, or failed future falls through to the
    original loader. The context variable isolates v2 from legacy requests.
    """

    _NODE_METHODS = {
        "UNETLoader": "load_unet",
        "CLIPLoader": "load_clip",
        "DualCLIPLoader": "load_clip",
        "VAELoader": "load_vae",
        "CLIPTextEncode": "encode",
    }

    def __init__(self, *, max_workers: int = 3) -> None:
        self.coordinator = ModelPreloadCoordinator(
            unet_loader=self._load_unet,
            clip_loader=self._load_clip,
            vae_loader=self._load_vae,
            prefill_loader=self._prefill,
            max_workers=max_workers,
        )
        self._nodes: Any | None = None
        self._original_methods: dict[str, Callable[..., Any]] = {}
        self._node_classes: dict[str, Any] = {}
        self._model_key: ModelRestoreKey | None = None
        self._prefill_key: PrefillKey | None = None
        self._model_spec: Mapping[str, Any] = {}
        self._preparation: RestorePreparation | None = None
        self._trace: RuntimeTrace | None = None
        self._preparation_trace: RuntimeTrace | None = None
        """Snapshot of the trace at ``prepare()`` return for late event drain."""
        self._preparation_event_cursor: int = 0
        """Number of events on ``_preparation_trace`` when ``prepare()`` returned."""
        self._prefill_results: dict[tuple[int, str], Any] = {}
        self._prefill_lock = RLock()

    def install(self, nodes_module: Any | None = None, *, trace: RuntimeTrace | None = None) -> bool:
        """Install wrappers on the live ComfyUI node classes once.

        Also triggers global core dispatch wrapper installation
        (``comfy.utils.load_torch_file`` and
        ``comfy.model_management.load_models_gpu``) because
        ``nodes.py`` has already imported these modules at startup,
        making them resolvable via ``sys.modules``.
        """
        if nodes_module is None:
            import nodes as nodes_module  # type: ignore[no-redef]
        mappings = getattr(nodes_module, "NODE_CLASS_MAPPINGS", {})
        if not isinstance(mappings, Mapping):
            return False
        self._nodes = nodes_module
        # Live comfy modules are already in sys.modules (loaded by nodes.py).
        # Install wrappers here rather than relying on a fresh import which
        # can fail on optional dependencies (e.g. comfy_aimdo).
        _ensure_core_wrappers(trace=trace)
        installed = False
        for class_name, method_name in self._NODE_METHODS.items():
            node_class = mappings.get(class_name)
            method = getattr(node_class, method_name, None) if node_class else None
            if not callable(method):
                continue
            key = f"{class_name}.{method_name}"
            self._node_classes[class_name] = node_class
            if getattr(method, "_comfy_modal_v2_loader_bridge", False):
                original = getattr(method, "_comfy_modal_v2_original", None)
                if callable(original):
                    self._original_methods[key] = original
                continue
            self._original_methods[key] = method
            wrapper = self._make_wrapper(class_name, method_name, method)
            setattr(wrapper, "_comfy_modal_v2_loader_bridge", True)
            setattr(wrapper, "_comfy_modal_v2_original", method)
            setattr(node_class, method_name, wrapper)
            installed = True
        return installed or bool(self._original_methods)

    def prepare(
        self,
        plan: Any,
        *,
        trace: RuntimeTrace | None = None,
        prepare_unet: bool | None = None,
        prepare_clip: bool | None = None,
        prepare_vae: bool | None = None,
    ) -> RestorePreparation | None:
        """Start actual restore-time UNET/CLIP work for one RestorePlan.

        *prepare_unet* / *prepare_clip* / *prepare_vae* — optional per-lane
        overrides.  When ``None`` the value is derived from the plan's model
        key (current behaviour).  Pass ``False`` to skip a lane so the
        original (patched) loader handles it at graph time (e.g. V1-style
        background UNET future).
        """
        self._model_key = plan.model_key
        self._prefill_key = plan.prefill_key
        self._model_spec = plan.model_spec if isinstance(plan.model_spec, Mapping) else {}
        self._trace = trace
        with self._prefill_lock:
            self._prefill_results.clear()
        self._preparation = None
        if not self._model_key or not (
            self._model_key.unet_identity or self._model_key.clip_identity
        ):
            if trace:
                trace.emit("preload_schedule_end", phase="restore", metadata={"status": "no_model_key"})
            return None
        self.install(self._nodes, trace=trace)
        # NOTE: when prepare_unet is False (V2 CLIP-only fast path), UNET is
        # owned entirely by the production background cache published during
        # restore.  The V2LoaderBridge intentionally does NOT prepare UNET
        # here; a bridge miss at graph time is expected and non-fatal — the
        # original (patched) loader handles it via _start_production_restore_unet
        # and _cached_unet_load.  See modal_app.py restore() for the fast-path
        # handoff that sets prepare_unet=False.
        prepare_unet = self._resolve_lane_override(
            prepare_unet,
            bool(self._model_key.unet_identity and self._request_list("unet")),
        )
        prepare_clip = self._resolve_lane_override(
            prepare_clip,
            bool(self._model_key.clip_identity and self._request_list("clip")),
        )
        # Restore schedules only UNET and CLIP preparation.  CLIPTextEncode
        # (prefill) is deferred to execution-phase single-flight via
        # schedule_execution_prefill() called after graph_execution_start.
        exact_prefill = False
        if trace:
            trace.emit(
                "preload_schedule_start",
                phase="restore",
                metadata={
                    "unet_identity": self._model_key.unet_identity,
                    "clip_identity": self._model_key.clip_identity,
                    "exact_prefill": exact_prefill,
                    "prefill_deferred_to_execution": True,
                    "prepare_unet": prepare_unet,
                    "prepare_clip": prepare_clip,
                    "prepare_vae": prepare_vae,
                },
            )
        # Derive exact expected read counts from the actual model requests.
        _erc: dict[str, int] = {}
        _erc["unet"] = 1
        _erc["clip"] = self._compute_clip_expected_read_count()
        _erc["vae"] = 1 if self._model_key.vae_identity else 0
        prepare_vae = self._resolve_lane_override(
            prepare_vae,
            bool(self._model_key.vae_identity and self._request_list("vae")),
        )

        self._preparation = self.coordinator.prepare(
            self._model_key,
            self._prefill_key or PrefillKey(model_key=self._model_key),
            exact_prefill=exact_prefill,
            prepare_unet=prepare_unet,
            prepare_clip=prepare_clip,
            prepare_vae=prepare_vae,
            trace=trace,
            expected_read_counts=_erc,
        )
        if trace:
            trace.emit(
                "preload_schedule_end",
                phase="restore",
                metadata={
                    "status": "started",
                    "unet_future": bool(self._preparation.unet_future),
                    "clip_future": bool(self._preparation.clip_future),
                    "vae_future": bool(self._preparation.vae_future),
                    "prefill_future": bool(self._preparation.prefill_future),
                    "prefill_deferred_to_execution": True,
                },
            )
        # Record trace cursor after all synchronous prepare() events so
        # late worker events (read/cpu/gpu/ready) can be drained into the
        # execution trace without duplicating the restore prefix.
        if trace is not None:
            self._preparation_trace = trace
            self._preparation_event_cursor = len(trace.events)
        return self._preparation

    @contextmanager
    def request_scope(self) -> Iterator[None]:
        """Make this bridge visible only while the v2 graph is executing."""
        token = _ACTIVE_V2_LOADER_BRIDGE.set(self)
        try:
            yield
        finally:
            _ACTIVE_V2_LOADER_BRIDGE.reset(token)

    def diagnostics(self) -> dict[str, Any]:
        if self._preparation is None:
            return {}
        return self.coordinator.diagnostics(self._preparation)

    def schedule_execution_prefill(self, *, trace: RuntimeTrace | None = None) -> bool:
        """Schedule execution-phase CLIP prefill single-flight.

        Called after ``graph_execution_start`` in ``_run_in_process``.

        **V2 prefill overlap (default):** waits for the CLIP preparation
        future only, then begins encoding *without* waiting for UNET.
        The UNET restore runs in parallel and its GPU commit is serialised
        through the mutation lane — safe because ``load_models_gpu``
        acquires the lane before touching GPU memory.  This removes
        ~5.7–6.3 s of Qwen-encode from the critical path on cold starts.

        **Legacy barrier (env ``COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET=1``):**
        waits for UNET first (old behaviour), putting the encode on the
        critical path behind UNET.

        Idempotent: subsequent calls are no-ops when
        ``preparation.prefill_future`` is already set.

        Returns True when prefill was scheduled (or was already scheduled),
        False when skipped (lane ``none``, missing preparation, or no
        eligible entries).

        Lane mode (``COMFYMODAL_V2_PREFILL_LANES``):
          * ``critical`` (default): only role=positive/negative entries
          * ``all``: all non-empty-text entries
          * ``none``: hard disable — skip scheduling entirely

        On missing/ineligible plan, no CLIP, failed future, or no matching
        cached result, the graph falls back to the original CLIPTextEncode
        via ``_consume_prefill`` returning ``_LOADER_MISS``.
        """
        lane_mode = _PREFILL_LANE_MODE
        if lane_mode == "none":
            if trace:
                trace.emit("execution_prefill_skip", phase="execution",
                           metadata={"reason": "lane_mode=none"})
            return False

        prep = self._preparation
        if prep is None or self._prefill_key is None:
            if trace:
                trace.emit("execution_prefill_skip", phase="execution",
                           metadata={"reason": "missing_preparation"})
            return False

        if prep.prefill_future is not None:
            if trace:
                trace.emit("execution_prefill_skip", phase="execution",
                           metadata={"reason": "already_scheduled"})
            return True  # already scheduled (from restore or earlier call)

        if not self._prefill_key.prompt_bundle_hash:
            if trace:
                trace.emit("execution_prefill_skip", phase="execution",
                           metadata={"reason": "no_prompt_bundle_hash"})
            return False

        options = self._prefill_key.encode_options
        entries = options.get("encodes", []) if isinstance(options, Mapping) else []
        filtered, skipped_count, skipped_reasons = self._filter_prefill_entries(
            entries, lane_mode
        )

        if not filtered:
            if trace:
                trace.emit("execution_prefill_skip", phase="execution",
                           metadata={"reason": "no_eligible_entries",
                                     "total": len(entries),
                                     "skipped": skipped_count})
            return False

        wait_for_unet = _V2_PREFILL_WAIT_FOR_UNET

        if trace:
            trace.emit("execution_prefill_scheduled", phase="execution",
                       metadata={"filtered_entries": len(filtered),
                                 "total_entries": len(entries),
                                 "lane_mode": lane_mode,
                                 "skipped": skipped_count,
                                 "wait_for_unet": wait_for_unet,
                                 "unet_future_exists": prep.unet_future is not None})

        def _execution_prefill() -> dict[tuple[int, str], Any] | None:
            """Internal prefill callback — runs in coordinator's worker pool.

            V2 prefill overlap (default): waits for CLIP only, begins
            encoding without blocking on UNET.  Legacy barrier
            (``COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET=1``): waits for UNET
            first (old behaviour).  Populates _prefill_results so graph
            nodes consume them.
            """
            nonlocal wait_for_unet
            if trace:
                trace.emit("execution_prefill_submitted", phase="execution",
                           metadata={"lane_mode": lane_mode,
                                     "total_entries": len(entries),
                                     "filtered": len(filtered),
                                     "wait_for_unet": wait_for_unet,
                                     "unet_future_exists": prep.unet_future is not None})
            # ── Legacy barrier: wait for UNET before CLIP ──────────
            if wait_for_unet:
                try:
                    if prep.unet_future is not None:
                        self.coordinator.wait_unet(
                            prep,
                            trace=trace,
                            demand_source="execution_prefill",
                        )
                except Exception as exc:
                    if trace:
                        trace.emit("execution_prefill_failed", phase="execution",
                                   metadata={"error": str(exc)[:200],
                                              "phase": "wait_unet"})
                    return None
            # ── Wait for CLIP ──────────────────────────────────────
            # In default mode this is the only pre-encode wait.
            # In legacy mode UNET has already resolved above.
            try:
                clip = self.coordinator.wait_clip(
                    prep, trace=trace, demand_source="execution_prefill"
                )
            except Exception as exc:
                if trace:
                    trace.emit("execution_prefill_failed", phase="execution",
                               metadata={"error": str(exc)[:200],
                                          "phase": "wait_clip"})
                return None
            if clip is None:
                if trace:
                    trace.emit("execution_prefill_failed", phase="execution",
                               metadata={"reason": "no_clip"})
                return None

            # ── UNET status when prefill is about to start encoding ──
            # Record whether UNET was skipped (no future), pending
            # (future not yet resolved), or already completed — useful
            # for diagnosing overlap in cold-trace analysis.
            if not wait_for_unet:
                unet_skipped = prep.unet_future is None
                unet_pending = (
                    not unet_skipped and not prep.unet_future.done()
                ) if prep.unet_future is not None else False
                if trace:
                    trace.emit("execution_prefill_unet_status",
                               phase="execution",
                               metadata={
                                   "wait_for_unet": False,
                                   "unet_skipped": unet_skipped,
                                   "unet_pending": unet_pending,
                                   "unet_resolved": not unet_skipped and not unet_pending,
                               })

            # Encode eligible entries using original CLIPTextEncode
            results: dict[tuple[int, str], Any] = {}
            for entry in filtered:
                text = str(entry.get("text", ""))
                try:
                    result = self._invoke_original(
                        "CLIPTextEncode", {"clip": clip, "text": text}
                    )
                    results[(id(clip), text)] = result
                except Exception as exc:
                    if trace:
                        trace.emit("execution_prefill_encode_error",
                                   phase="execution",
                                   metadata={"error": str(exc)[:200],
                                             "text_length": len(text)})

            # Store results for graph consumption
            with self._prefill_lock:
                self._prefill_results.update(results)

            if trace:
                unet_skipped = prep.unet_future is None
                unet_pending = (
                    not unet_skipped and not prep.unet_future.done()
                ) if prep.unet_future is not None else False
                trace.emit("execution_prefill_completed", phase="execution",
                           metadata={"encoded_count": len(results),
                                     "filtered_entries": len(filtered),
                                     "total_entries": len(entries),
                                     "wait_for_unet": wait_for_unet,
                                     "unet_skipped": unet_skipped,
                                     "unet_pending": unet_pending,
                                     "unet_resolved": not unet_skipped and not unet_pending})
            return results

        # Use the coordinator's scheduler to submit (idempotent via
        # schedule_prefill checking prefill_future).  The callback waits
        # for CLIP (and optionally UNET when the legacy barrier is active)
        # futures which were submitted during restore.
        # Deadlock analysis (V2 overlap / default):
        #   max_workers=2: UNET (thread A) + CLIP (thread B) compete in
        #     parallel.  Prefill callback waits for CLIP only (default) or
        #     UNET first (legacy).  In default mode the CLIP thread picks
        #     up the callback, resolves immediately (CLIP is already done
        #     or finishes soon), and begins encoding while UNET is still
        #     loading — the mutation lane serialises any GPU commit.
        #   max_workers=1: single thread runs UNET -> CLIP -> prefill
        #     sequentially; both futures complete before prefill starts.
        #   In both cases the preload barrier has NOT been waited yet
        #   (it runs later inside _execute_v2_prompt_executor), but the
        #   callback's direct future.wait() is safe because the futures
        #   were submitted to the same pool and are in-flight or done.
        #   GPU safety: ``load_models_gpu`` wrapper acquires the mutation
        #   lane (priority ``UNET > CLIP > prefill > VAE > sampler``), so
        #   concurrent UNET GPU commits are serialised through the lane.
        self.coordinator.schedule_prefill(_execution_prefill, prep, trace=trace)
        return True

    @staticmethod
    def _resolve_lane_override(override: bool | None, computed: bool) -> bool:
        """Return *override* when not None, else *computed*."""
        return override if override is not None else computed

    def close_workers(self) -> None:
        """Wait for submitted restore futures and shut down the coordinator pool.
        Swallows worker exceptions so existing loader fallback behavior remains.
        The coordinator recreates a pool on the next _submit call."""
        prep = self._preparation
        if prep is not None:
            _cw_start_ns = time.monotonic_ns()
            _present = 0
            _done = 0
            _failed = 0
            for future in (prep.unet_future, prep.clip_future, prep.vae_future):
                if future is not None:
                    _present += 1
                    if future.done():
                        _done += 1
                        if future.exception() is not None:
                            _failed += 1
                    try:
                        future.result()
                    except Exception:
                        _failed += 1
            _cw_wait_ms = round((time.monotonic_ns() - _cw_start_ns) / 1_000_000, 3)
            if self._trace:
                self._trace.emit("close_workers_start", phase="restore", metadata={
                    "present": _present,
                    "done_before_wait": _done,
                    "failed": _failed,
                })
                self._trace.emit("close_workers_end", phase="restore", metadata={
                    "wait_ms": _cw_wait_ms,
                    "present": _present,
                    "done_final": _present,
                })
        self.coordinator.close()

    def extend_preparation(
        self,
        *,
        prepare_unet: bool = True,
        prepare_vae: bool = True,
        trace: RuntimeTrace | None = None,
    ) -> RestorePreparation | None:
        """Extend the current preparation with missing lanes (no clear+re-prepare).

        Delegates to ``ModelPreloadCoordinator.extend()`` which never
        resubmits a lane whose future is already present.  The existing
        ``clip_future`` (submitted during a prior clip-only prepare) is
        preserved, and the thread pool is recreated on demand if it was
        closed.  Returns None when no preparation exists.
        """
        if self._preparation is None or self._model_key is None:
            return None
        return self.coordinator.extend(
            self._preparation,
            prepare_unet=prepare_unet,
            prepare_vae=prepare_vae,
            trace=trace,
        )

    def _init_ready_preparation(
        self,
        *,
        model_key: ModelRestoreKey,
        prefill_key: PrefillKey,
        model_spec: Mapping[str, Any],
        unet: Any = _LOADER_MISS,
        clip: Any = _LOADER_MISS,
        trace: RuntimeTrace | None = None,
    ) -> RestorePreparation:
        self._model_key = model_key
        self._prefill_key = prefill_key
        self._model_spec = dict(model_spec) if isinstance(model_spec, Mapping) else {}
        self._trace = trace

        if not self.install(self._nodes, trace=trace):
            raise RuntimeError(
                "V2LoaderBridge: install() could not establish "
                "loader wrappers; bridge is not ready to serve snapshot models"
            )

        with self._prefill_lock:
            self._prefill_results.clear()

        prep = RestorePreparation(model_key=model_key, prefill_key=prefill_key)
        _now = time.time()

        # Set completed futures BEFORE publishing the preparation,
        # so graph-time consumers never observe an incomplete state.
        if unet is not _LOADER_MISS:
            # Register snapshot UNET for first-CUDA timing and install
            # forward pre-hook on its diffusion model.
            register_unet_forward_probe(unet, source="cpu_snapshot")
            unet_future: Future[Any] = Future()
            unet_future.set_result(unet)
            prep.unet_future = unet_future
            prep.diagnostics.unet_started_at = _now
            prep.diagnostics.unet_completed_at = _now

        if clip is not _LOADER_MISS:
            clip_future: Future[Any] = Future()
            clip_future.set_result(clip)
            prep.clip_future = clip_future
            prep.diagnostics.clip_started_at = _now
            prep.diagnostics.clip_completed_at = _now

        # Publish only after all ready futures are assigned.
        self._preparation = prep
        self.coordinator._active = prep

        if trace is not None:
            self._preparation_trace = trace
            self._preparation_event_cursor = len(trace.events)

        return prep

    def use_ready_models(
        self,
        *,
        model_key: ModelRestoreKey,
        prefill_key: PrefillKey,
        model_spec: Mapping[str, Any],
        unet: Any,
        clip: Any,
        trace: RuntimeTrace | None = None,
    ) -> RestorePreparation:
        return self._init_ready_preparation(
            model_key=model_key, prefill_key=prefill_key,
            model_spec=model_spec, unet=unet, clip=clip, trace=trace,
        )

    def use_ready_clip(
        self,
        *,
        model_key: ModelRestoreKey,
        prefill_key: PrefillKey,
        model_spec: Mapping[str, Any],
        clip: Any,
        trace: RuntimeTrace | None = None,
    ) -> RestorePreparation:
        return self._init_ready_preparation(
            model_key=model_key, prefill_key=prefill_key,
            model_spec=model_spec, clip=clip, trace=trace,
        )

    def clear(self) -> None:
        """Disable consumption when a restore has no authoritative plan."""
        self._model_key = None
        self._prefill_key = None
        self._model_spec = {}
        self._preparation = None
        self._trace = None
        self._preparation_trace = None
        self._preparation_event_cursor = 0
        self.coordinator._active = None
        with self._prefill_lock:
            self._prefill_results.clear()

    def drain_worker_events(self, target_trace: RuntimeTrace | None = None) -> int:
        """Wait for all preparation futures and drain late events to *target_trace*.

        Restore-time ``prepare()`` returns before background workers finish
        emitting events (``read_start/end``, ``cpu_prepare_*``, ``ready``,
        and graph demand/wait).  This method blocks until every submitted
        future is terminal, then copies new events (those appended after the
        cursor recorded at ``prepare()`` return) from the preparation trace
        into *target_trace*.

        Returns the number of events drained, or 0 if no trace/futures.
        Thread-safe: waits for futures, then drains under no further mutation.
        """
        source = self._preparation_trace
        if source is None or target_trace is None:
            return 0
        prep = self._preparation
        if prep is None:
            return 0
        # Wait for all submitted futures to become terminal.
        for future in (prep.unet_future, prep.clip_future, prep.vae_future, prep.prefill_future):
            if future is not None:
                try:
                    future.result()
                except Exception:
                    pass
        # Drain events appended since the cursor.
        cursor = self._preparation_event_cursor
        all_events = source.events
        if len(all_events) > cursor:
            new_events = all_events[cursor:]
            target_trace.extend(new_events)
            self._preparation_event_cursor = len(all_events)
            return len(new_events)
        return 0

    def _make_wrapper(self, class_name: str, method_name: str, original: Callable[..., Any]) -> Callable[..., Any]:
        if class_name == "UNETLoader":
            def wrapped(node: Any, *args: Any, **kwargs: Any) -> Any:
                active = current_v2_loader_bridge()
                if active is not None:
                    result = active._consume_unet(args, kwargs)
                    if result is not _LOADER_MISS:
                        return result
                return original(node, *args, **kwargs)
        elif class_name in {"CLIPLoader", "DualCLIPLoader"}:
            def wrapped(node: Any, *args: Any, **kwargs: Any) -> Any:
                active = current_v2_loader_bridge()
                if active is not None:
                    result = active._consume_clip(class_name, args, kwargs)
                    if result is not _LOADER_MISS:
                        return result
                return original(node, *args, **kwargs)
        elif class_name == "VAELoader":
            def wrapped(node: Any, *args: Any, **kwargs: Any) -> Any:
                active = current_v2_loader_bridge()
                if active is not None:
                    result = active._consume_vae(args, kwargs)
                    if result is not _LOADER_MISS:
                        return result
                return original(node, *args, **kwargs)
        else:
            def wrapped(node: Any, *args: Any, **kwargs: Any) -> Any:
                active = current_v2_loader_bridge()
                if active is not None:
                    result = active._consume_prefill(args, kwargs)
                    if result is not _LOADER_MISS:
                        return result
                return original(node, *args, **kwargs)
        return wrapped

    def _request_list(self, bucket: str) -> list[dict[str, Any]]:
        loaders = self._model_spec.get("loaders", self._model_spec)
        values = loaders.get(bucket, []) if isinstance(loaders, Mapping) else []
        return [dict(value) for value in values if isinstance(value, Mapping)]

    def _compute_clip_expected_read_count(self) -> int:
        """Derive the exact expected ``load_torch_file`` count for the CLIP lane.

        CLIPLoader: one read (single ``clip_name``).
        DualCLIPLoader: two reads (``clip_name1`` + ``clip_name2``).
        Falls back to 1 when the request cannot be resolved.
        """
        if not self._model_key or not self._model_key.clip_identity:
            return 1
        request = self._find_request("clip", self._model_key.clip_identity)
        if request is None:
            return 1
        loader_class = str(request.get("loader_class", ""))
        if loader_class == "DualCLIPLoader":
            return 2
        return 1

    def _find_request(self, bucket: str, identity: str) -> dict[str, Any] | None:
        for request in self._request_list(bucket):
            if bucket == "vae":
                vae_name = str(request.get("vae_name", "") or "")
                if identity and identity == vae_name:
                    return request
            values = (
                request.get("unet_name"),
                request.get("clip_name"),
                request.get("clip_name1"),
            )
            if identity and identity in {str(value) for value in values if value}:
                return request
            if bucket == "clip" and request.get("clip_name1") and request.get("clip_name2"):
                if identity == f"{request['clip_name1']}||{request['clip_name2']}":
                    return request
        return None

    def _load_unet(self, model_key: ModelRestoreKey) -> Any:
        request = self._find_request("unet", model_key.unet_identity)
        if request is None:
            raise RuntimeError(f"v2 UNET loader request is absent for {model_key.unet_identity!r}")
        kwargs = {
            "unet_name": request.get("unet_name", model_key.unet_identity),
            "weight_dtype": request.get("weight_dtype", "default"),
        }
        _req_wd = request.get("weight_dtype", "default")
        # Resolve effective dtype for diagnostic logging (shared resolver)
        _eff_dtype, _eff_label = resolve_unet_effective_dtype(_req_wd)
        result = self._invoke_original("UNETLoader", kwargs)
        unet = result[0] if isinstance(result, (tuple, list)) and result else result

        # ── Emit normal_loader_ready state (print + trace) ──────────────
        _normal_state: dict[str, Any] = {}
        try:
            # Safely import model_management for loaded_models comparability
            _mgmt = None
            try:
                import comfy.model_management as _comfy_mm
                _mgmt = _comfy_mm
            except Exception:
                _mgmt = None

            _normal_state = collect_unet_runtime_state(
                unet, model_management=_mgmt,
            )
        except Exception:
            _normal_state = collect_unet_runtime_state(unet, model_management=None)

        try:
            _state_json = __import__("json").dumps(
                _normal_state, default=str, separators=(",", ":"), sort_keys=True,
            )
            print(
                f"[v2.unet_runtime_state] "
                f"stage=normal_loader_ready "
                f"unet_identity={model_key.unet_identity} "
                f"requested_weight_dtype={_req_wd} "
                f"effective_weight_dtype={_eff_label} "
                f"state={_state_json}",
                flush=True,
            )
        except Exception:
            pass

        try:
            # Trace event — prefer request trace, fallback to bridge trace
            _target_trace = _ACTIVE_REQUEST_TRACE.get() or self._trace
            if _target_trace is not None:
                _target_trace.emit(
                    "unet_runtime_state",
                    metadata={
                        "stage": "normal_loader_ready",
                        "unet_identity": model_key.unet_identity,
                        "requested_weight_dtype": _req_wd,
                        "effective_weight_dtype": _eff_label,
                        "request_id": str(getattr(_target_trace, "request_id", None) or ""),
                        "restored_instance_id": _LATEST_RESTORED_INSTANCE_ID,
                        "restore_session_id": _LATEST_RESTORE_SESSION_ID,
                        "state": _normal_state,
                    },
                )
        except Exception:
            pass

        register_unet_forward_probe(unet, source="normal_loader")
        return unet

    def _load_clip(self, model_key: ModelRestoreKey) -> Any:
        request = self._find_request("clip", model_key.clip_identity)
        if request is None:
            raise RuntimeError(f"v2 CLIP loader request is absent for {model_key.clip_identity!r}")
        class_name = str(request.get("loader_class", "CLIPLoader"))
        kwargs = dict(request)
        kwargs.pop("node_id", None)
        kwargs.pop("loader_class", None)
        kwargs.setdefault("type", model_key.clip_type or "stable_diffusion")
        kwargs.setdefault("device", "default")
        result = self._invoke_original(class_name, kwargs)
        return result[0] if isinstance(result, (tuple, list)) and result else result

    def _load_vae(self, model_key: ModelRestoreKey) -> Any:
        request = self._find_request("vae", model_key.vae_identity)
        if request is None:
            raise RuntimeError(f"v2 VAE loader request is absent for {model_key.vae_identity!r}")
        kwargs = {
            "vae_name": request.get("vae_name", model_key.vae_identity),
        }
        result = self._invoke_original("VAELoader", kwargs)
        return result[0] if isinstance(result, (tuple, list)) and result else result

    @staticmethod
    def _filter_prefill_entries(
        entries: list[dict[str, Any]],
        lane_mode: str,
    ) -> tuple[list[dict[str, Any]], int, list[str]]:
        """Filter *entries* according to *lane_mode*.

        Returns ``(filtered, skipped_count, skipped_reasons)``.

        * **critical**: keep entries with a role in ``_PREFILL_CRITICAL_ROLES``
          and non-empty text.
        * **all**: keep everything (non-empty text is still required).
        * **none**: skip everything (return empty).

        Empty-text entries are always skipped regardless of lane mode
        since they produce no useful prefill work.
        """
        if lane_mode == "none":
            return [], len(entries), ["lane_mode=none"]
        kept: list[dict[str, Any]] = []
        skipped = 0
        reasons: list[str] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                skipped += 1
                reasons.append("non_mapping_entry")
                continue
            text = str(entry.get("text", "") or "")
            if not text:
                skipped += 1
                reasons.append(
                    f"node_id={entry.get('node_id', '?')} empty_text"
                )
                continue
            if lane_mode == "all":
                kept.append(entry)
                continue
            # lane_mode == "critical" (default)
            role = str(entry.get("role", "") or "").lower()
            if role in _PREFILL_CRITICAL_ROLES:
                kept.append(entry)
            else:
                skipped += 1
                reasons.append(
                    f"node_id={entry.get('node_id', '?')} role={role!r}"
                )
        return kept, skipped, reasons

    def _prefill(self, prefill_key: PrefillKey, clip: Any) -> dict[tuple[int, str], Any]:
        lane_mode = _PREFILL_LANE_MODE
        options = prefill_key.encode_options
        entries = options.get("encodes", []) if isinstance(options, Mapping) else []
        results: dict[tuple[int, str], Any] = {}
        filtered, skipped_count, skipped_reasons = self._filter_prefill_entries(
            entries, lane_mode
        )
        for entry in filtered:
            text = str(entry.get("text", ""))
            result = self._invoke_original(
                "CLIPTextEncode",
                {"clip": clip, "text": text},
            )
            results[(id(clip), text)] = result
        if self._preparation is not None:
            self._preparation.diagnostics.prefill_lane_mode = lane_mode
            self._preparation.diagnostics.prefill_total_encodes = len(entries)
            self._preparation.diagnostics.prefill_skipped_encodes = skipped_count
            self._preparation.diagnostics.prefill_skipped_reasons = skipped_reasons
        return results

    def _consume_unet(self, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
        identity = kwargs.get("unet_name", args[0] if args else "")
        return self._consume_model_impl(
            lane="UNET",
            loader_class="UNETLoader",
            diagnostics_prefix="unet",
            requested_identity=str(identity),
            planned_identity=self._model_key.unet_identity if self._model_key else "",
            wait_fn=self.coordinator.wait_unet,
            demand_metadata={"unet_name": str(identity), "lane": "UNET", "loader_class": "UNETLoader"},
        )

    def _consume_clip(self, class_name: str, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
        if class_name == "DualCLIPLoader":
            from .restore_plan import _build_dual_clip_identity
            clip_a = kwargs.get("clip_name1", args[0] if args else "")
            clip_b = kwargs.get("clip_name2", args[1] if len(args) > 1 else "")
            identity = _build_dual_clip_identity(clip_a, clip_b)
        else:
            identity = str(kwargs.get("clip_name", args[0] if args else ""))
        return self._consume_model_impl(
            lane="CLIP",
            loader_class=class_name,
            diagnostics_prefix="clip",
            requested_identity=identity,
            planned_identity=self._model_key.clip_identity if self._model_key else "",
            wait_fn=self.coordinator.wait_clip,
            demand_metadata={"clip_identity": identity},
        )

    def _consume_vae(self, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
        identity = str(kwargs.get("vae_name", args[0] if args else ""))
        return self._consume_model_impl(
            lane="VAE",
            loader_class="VAELoader",
            diagnostics_prefix="vae",
            requested_identity=identity,
            planned_identity=self._model_key.vae_identity if self._model_key else "",
            wait_fn=self.coordinator.wait_vae,
            demand_metadata={"vae_name": identity, "lane": "VAE"},
            emit_consumed_on_error=False,
            skip_loader_class=True,
        )

    def _consume_model_impl(
        self,
        *,
        lane: str,
        loader_class: str,
        diagnostics_prefix: str,
        requested_identity: str,
        planned_identity: str,
        wait_fn: Callable[[RestorePreparation], Any],
        demand_metadata: Mapping[str, Any],
        emit_consumed_on_error: bool = True,
        skip_loader_class: bool = False,
    ) -> Any:
        """Shared model-consumption implementation for UNET/CLIP/VAE lanes.

        Each public ``_consume_*`` method extracts the lane-specific identity
        then delegates here.  Parameters map directly to observable event
        differences between lanes — no implicit behaviour.

        *lane*, *loader_class*, *diagnostics_prefix* — lane identity strings.
        *requested_identity* — the identity extracted from the graph call.
        *planned_identity* — the expected identity from ``ModelRestoreKey``.
        *wait_fn* — coordinator method to wait for the prepared future.
        *demand_metadata* — metadata dict for the ``graph_{prefix}_demand`` event
          (unique shape per lane).
        *emit_consumed_on_error* — when True emits ``graph_{prefix}_consumed``
          in the exception path (UNET/CLIP). VAE omits this event on error.
        *skip_loader_class* — when True omits ``loader_class`` from
          ``graph_model_demand``, ``future_failed``, ``future_unavailable``,
          and canonical ``graph_demand`` (VAE divergence).
        """
        key = self._model_key
        preparation = self._preparation

        # --- Missing spec check ---
        if key is None or preparation is None:
            if self._trace:
                self._trace.emit(
                    "request_spec_missing",
                    phase="execution",
                    metadata={
                        "lane": lane,
                        "loader_class": loader_class,
                        "hashed_requested_identity": stable_hash(requested_identity),
                        "terminal_outcome": "fallback_missing_spec",
                    },
                )
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": lane, "reason": "missing_spec",
                })
            return _LOADER_MISS

        # --- Identity mismatch check ---
        if requested_identity != planned_identity:
            if self._trace:
                self._trace.emit(
                    "identity_mismatch",
                    phase="execution",
                    metadata={
                        "lane": lane,
                        "loader_class": loader_class,
                        "hashed_planned_identity": stable_hash(planned_identity),
                        "hashed_requested_identity": stable_hash(requested_identity),
                        "terminal_outcome": "fallback_identity_mismatch",
                    },
                )
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": lane, "reason": "identity_mismatch",
                })
            return _LOADER_MISS

        # --- Graph demand and wait ---
        if self._trace:
            self._trace.emit(f"graph_{diagnostics_prefix}_demand", phase="execution",
                             metadata=dict(demand_metadata))
            model_demand_meta: dict[str, Any] = {"lane": lane}
            if not skip_loader_class:
                model_demand_meta["loader_class"] = loader_class
            self._trace.emit("graph_model_demand", phase="execution", metadata=model_demand_meta)
            self._trace.emit(f"graph_{diagnostics_prefix}_wait_start", phase="execution")
            self._trace.emit("graph_wait_started", phase="execution", metadata={"lane": lane})
            # ── Canonical consumer events (Phase 0, additive) ──
            canonical_demand_meta: dict[str, Any] = {"lane": lane}
            if not skip_loader_class:
                canonical_demand_meta["loader_class"] = loader_class
            self._trace.emit("graph_demand", phase="execution", metadata=canonical_demand_meta)
            self._trace.emit("graph_wait_start", phase="execution", metadata={"lane": lane})
        try:
            result = wait_fn(preparation)
        except Exception as exc:
            if self._trace:
                self._trace.emit(f"graph_{diagnostics_prefix}_wait_end", phase="execution",
                                 metadata={"status": "error"})
                if emit_consumed_on_error:
                    self._trace.emit(f"graph_{diagnostics_prefix}_consumed", phase="execution", metadata={
                        "status": "fallback", "error": str(exc)[:200],
                    })
                self._trace.emit("graph_wait_finished", phase="execution", metadata={
                    "lane": lane, "status": "error",
                })
                ff_meta: dict[str, Any] = {
                    "lane": lane,
                    "error_category": type(exc).__name__,
                    "hashed_planned_identity": stable_hash(planned_identity or ""),
                    "terminal_outcome": "fallback_future_error",
                }
                if not skip_loader_class:
                    ff_meta["loader_class"] = loader_class
                self._trace.emit("future_failed", phase="execution", metadata=ff_meta)
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": lane, "reason": "future_error",
                })
                # ── Canonical consumer end (error) ──
                self._trace.emit("graph_wait_end", phase="execution", metadata={
                    "lane": lane, "status": "error",
                })
            return _LOADER_MISS
        if result is None:
            if self._trace:
                self._trace.emit(f"graph_{diagnostics_prefix}_wait_end", phase="execution",
                                 metadata={"status": "unavailable"})
                self._trace.emit("graph_wait_finished", phase="execution", metadata={
                    "lane": lane, "status": "unavailable",
                })
                fu_meta: dict[str, Any] = {
                    "lane": lane,
                    "hashed_planned_identity": stable_hash(planned_identity or ""),
                    "terminal_outcome": "fallback_unavailable",
                }
                if not skip_loader_class:
                    fu_meta["loader_class"] = loader_class
                self._trace.emit("future_unavailable", phase="execution", metadata=fu_meta)
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": lane, "reason": "result_none",
                })
                # ── Canonical consumer end (unavailable) ──
                self._trace.emit("graph_wait_end", phase="execution", metadata={
                    "lane": lane, "status": "unavailable",
                })
            return _LOADER_MISS
        if self._trace:
            self._trace.emit(f"graph_{diagnostics_prefix}_wait_end", phase="execution",
                             metadata={"status": "ok"})
            self._trace.emit(f"graph_{diagnostics_prefix}_consumed", phase="execution",
                             metadata={"status": "prepared"})
            self._trace.emit("graph_wait_finished", phase="execution", metadata={
                "lane": lane, "status": "ok",
            })
            # ── Canonical consumer end (success) ──
            self._trace.emit("graph_wait_end", phase="execution", metadata={
                "lane": lane, "status": "ok",
            })
            completed_before = getattr(
                preparation.diagnostics, f"{diagnostics_prefix}_work_completed_before_demand_ms", 0.0
            )
            graph_wait_ms = getattr(
                preparation.diagnostics, f"{diagnostics_prefix}_actual_graph_wait_ms", 0.0
            )
            self._trace.emit(
                "prepared_result_consumed",
                phase="execution",
                metadata={
                    "lane": lane,
                    "loader_class": loader_class,
                    "hashed_planned_identity": stable_hash(planned_identity),
                    "terminal_outcome": "prepared",
                    "completed_before_demand_ms": round(completed_before, 3),
                    "graph_wait_duration_ms": round(graph_wait_ms, 3),
                },
            )
        return (result,)

    def _consume_prefill(self, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
        preparation = self._preparation
        # Extract clip/text early so hashed_requested_identity is available
        # for every terminal event without changing preload behavior.
        clip = kwargs.get("clip", args[0] if args else None)
        text = str(kwargs.get("text", args[1] if len(args) > 1 else ""))

        # --- Missing spec check ---
        if preparation is None or self._prefill_key is None or not self._prefill_key.prompt_bundle_hash:
            if self._trace:
                self._trace.emit(
                    "request_spec_missing",
                    phase="execution",
                    metadata={
                        "lane": "prefill",
                        "loader_class": "CLIPTextEncode",
                        "hashed_requested_identity": stable_hash(text) if text else "",
                        "terminal_outcome": "fallback_missing_spec",
                    },
                )
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": "prefill", "reason": "missing_spec",
                })
            return _LOADER_MISS

        if clip is None or not text:
            if self._trace:
                self._trace.emit(
                    "request_spec_missing",
                    phase="execution",
                    metadata={
                        "lane": "prefill",
                        "loader_class": "CLIPTextEncode",
                        "hashed_requested_identity": stable_hash(text) if text else "",
                        "terminal_outcome": "fallback_missing_spec",
                        "reason": "clip_or_text_missing",
                    },
                )
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": "prefill", "reason": "clip_or_text_missing",
                })
            return _LOADER_MISS

        # --- Graph demand and wait ---
        if self._trace:
            self._trace.emit("graph_prefill_demand", phase="execution", metadata={
                "text_length": len(text),
                "lane": "prefill",
                "loader_class": "CLIPTextEncode",
            })
            self._trace.emit("graph_model_demand", phase="execution", metadata={
                "lane": "prefill",
                "loader_class": "CLIPTextEncode",
            })
            self._trace.emit("graph_prefill_wait_start", phase="execution")
            self._trace.emit("graph_wait_started", phase="execution", metadata={"lane": "prefill"})
            # ── Canonical consumer events (Phase 0, additive) ──
            self._trace.emit("graph_demand", phase="execution", metadata={
                "lane": "prefill", "loader_class": "CLIPTextEncode",
            })
            self._trace.emit("graph_wait_start", phase="execution", metadata={"lane": "prefill"})
        try:
            cache_key = (id(clip), text)
            with self._prefill_lock:
                result = self._prefill_results.get(cache_key, _LOADER_MISS)
            if result is _LOADER_MISS:
                # Never hold the cache lock while waiting for the restore
                # future. This keeps parallel CLIPTextEncode nodes from
                # deadlocking and makes the blocking interval measurable.
                values = self.coordinator.wait_prefill(preparation)
                with self._prefill_lock:
                    if isinstance(values, Mapping):
                        self._prefill_results.update(values)
                    result = self._prefill_results.get(cache_key, _LOADER_MISS)
        except Exception as exc:
            if self._trace:
                self._trace.emit("graph_prefill_wait_end", phase="execution", metadata={"status": "error"})
                self._trace.emit("graph_prefill_consumed", phase="execution", metadata={
                    "status": "fallback", "error": str(exc)[:200],
                })
                self._trace.emit("graph_wait_finished", phase="execution", metadata={
                    "lane": "prefill", "status": "error",
                })
                self._trace.emit(
                    "future_failed",
                    phase="execution",
                    metadata={
                        "lane": "prefill",
                        "loader_class": "CLIPTextEncode",
                        "hashed_requested_identity": stable_hash(text),
                        "error_category": type(exc).__name__,
                        "terminal_outcome": "fallback_future_error",
                    },
                )
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": "prefill", "reason": "future_error",
                })
                # ── Canonical consumer end (error) ──
                self._trace.emit("graph_wait_end", phase="execution", metadata={
                    "lane": "prefill", "status": "error",
                })
            return _LOADER_MISS
        if result is _LOADER_MISS:
            if self._trace:
                self._trace.emit("graph_prefill_wait_end", phase="execution", metadata={"status": "unavailable"})
                self._trace.emit("graph_wait_finished", phase="execution", metadata={
                    "lane": "prefill", "status": "unavailable",
                })
                self._trace.emit(
                    "future_unavailable",
                    phase="execution",
                    metadata={
                        "lane": "prefill",
                        "loader_class": "CLIPTextEncode",
                        "hashed_requested_identity": stable_hash(text),
                        "terminal_outcome": "fallback_unavailable",
                    },
                )
                self._trace.emit("original_loader_fallback", phase="execution", metadata={
                    "lane": "prefill", "reason": "future_unavailable",
                })
                # ── Canonical consumer end (unavailable) ──
                self._trace.emit("graph_wait_end", phase="execution", metadata={
                    "lane": "prefill", "status": "unavailable",
                })
            return _LOADER_MISS
        if self._trace:
            self._trace.emit("graph_prefill_wait_end", phase="execution", metadata={"status": "ok"})
            self._trace.emit("graph_prefill_consumed", phase="execution", metadata={"status": "prepared"})
            self._trace.emit("graph_wait_finished", phase="execution", metadata={
                "lane": "prefill", "status": "ok",
            })
            # ── Canonical consumer end (success) ──
            self._trace.emit("graph_wait_end", phase="execution", metadata={
                "lane": "prefill", "status": "ok",
            })
            completed_before = getattr(
                preparation.diagnostics, "prefill_work_completed_before_demand_ms", None
            )
            graph_wait_ms = getattr(
                preparation.diagnostics, "prefill_actual_graph_wait_ms", None
            )
            self._trace.emit(
                "prepared_result_consumed",
                phase="execution",
                metadata={
                    "lane": "prefill",
                    "loader_class": "CLIPTextEncode",
                    "hashed_requested_identity": stable_hash(text),
                    "terminal_outcome": "prepared",
                    "completed_before_demand_ms": round(completed_before, 3) if completed_before is not None else None,
                    "graph_wait_duration_ms": round(graph_wait_ms, 3) if graph_wait_ms is not None else None,
                },
            )
        return result

    def _invoke_original(self, class_name: str, kwargs: Mapping[str, Any]) -> Any:
        method_name = self._NODE_METHODS[class_name]
        method = self._original_methods.get(f"{class_name}.{method_name}")
        node_class = self._node_classes.get(class_name)
        if not callable(method) or node_class is None:
            if self._trace:
                self._trace.emit("loader_invoke_error", phase="restore", metadata={
                    "lane": class_name,
                    "error": "original_unavailable",
                })
            raise RuntimeError(f"original ComfyUI loader is unavailable: {class_name}.{method_name}")
        _invoke_lane = class_name
        _start_ns = time.monotonic_ns()
        if self._trace:
            self._trace.emit("loader_invoke_start", phase="restore", metadata={
                "lane": _invoke_lane,
                "loader_class": class_name,
            })
        try:
            result = method(node_class(), **dict(kwargs))
            _dur_ms = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
            if self._trace:
                self._trace.emit("loader_invoke_end", phase="restore", metadata={
                    "lane": _invoke_lane,
                    "loader_class": class_name,
                    "duration_ms": _dur_ms,
                })
            return result
        except Exception as exc:
            _dur_ms = round((time.monotonic_ns() - _start_ns) / 1_000_000, 3)
            if self._trace:
                self._trace.emit("loader_invoke_error", phase="restore", metadata={
                    "lane": _invoke_lane,
                    "loader_class": class_name,
                    "duration_ms": _dur_ms,
                    "error": str(exc)[:200],
                })
            raise
