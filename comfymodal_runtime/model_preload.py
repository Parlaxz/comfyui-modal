"""UNET/CLIP/VAE restore preparation with prefill filtering and execution-phase overlap.

Controls:
  COMFYMODAL_V2_PREFILL_LANES — critical|all|none (default critical)
  COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET — legacy barrier (default off)
  COMFYMODAL_V2_DEEP_MODEL_DIAG=1 — enable deep /proc, faults, open/mmap/safetensors
"""

from __future__ import annotations

import enum
import functools
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
from .trace import RuntimeTrace

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

# ── Per-worker lane context (set around worker callback) ─────────────

_ACTIVE_LANE_TRACE: ContextVar["ModelLaneTrace | None"] = ContextVar(
    "comfymodal_active_lane_trace", default=None
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

_read_wrapper_installed: bool = False
_gpu_wrapper_installed: bool = False
_sd_wrapper_installed: bool = False
_subfn_wrappers_installed: bool = False
_deep_diag_wrappers_installed: bool = False
_wrappers_lock = RLock()

# Reentrancy guards — per-thread via ContextVar default=0.
_torch_file_depth: ContextVar[int] = ContextVar("_torch_file_depth", default=0)
_gpu_depth: ContextVar[int] = ContextVar("_gpu_depth", default=0)
_sd_depth: ContextVar[int] = ContextVar("_sd_depth", default=0)
_deep_st_depth: ContextVar[int] = ContextVar("_deep_st_depth", default=0)
_deep_tl_depth: ContextVar[int] = ContextVar("_deep_tl_depth", default=0)

# ── Deep-diagnostic target path (thread-local) ──────────────────────
# Set by the background UNET worker before the load body; used by the
# deep diag wrappers to filter: only emit stage events when the current
# thread's *target_path* matches the file being accessed AND deep diag
# is enabled.  Avoids logging unrelated model loads.
_DEEP_TARGET_PATH: ContextVar[str] = ContextVar("_deep_target_path", default="")

# Residual tracking — list of child duration_ms collected during an SD outer call.
_child_durations: ContextVar[list[float] | None] = ContextVar("_child_durations", default=None)

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
        if before == 0:
            lane = _ACTIVE_LANE_TRACE.get()
            if lane is not None:
                lane.read_start()
                if lane._lane == "UNET" and _DIAGNOSTIC_FLAG:
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
                    lane._on_read_completed()
                    if lane._lane == "UNET" and _DIAGNOSTIC_FLAG:
                        lane._trace.emit(
                            "unet_load_torch_file_end",
                            phase=lane._phase,
                            metadata={"lane": lane._lane, "path_hash": stable_hash(str(ckpt))[:16]},
                        )
    wrapper._comfy_modal_read_wrapper = True  # sentinel for idempotence
    return wrapper


def _make_gpu_loader_wrapper(original: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``comfy.model_management.load_models_gpu`` to emit commit events.

    Reentrancy-safe.  Emits ``gpu_lane_wait_start/end`` using the real
    ``_MUTATION_LANE`` (non-zero when contention exists) so Phase-2
    wait durations are truthful.  ``gpu_commit_start/end`` bracket the
    actual call.
    """

    @functools.wraps(original)
    def wrapper(models, memory_required=0, force_patch_weights=False,
                minimum_memory_required=None, force_full_load=False):
        before = _gpu_depth.get()
        _gpu_depth.set(before + 1)
        if before == 0:
            lane = _ACTIVE_LANE_TRACE.get()
            if lane is not None:
                lane._on_gpu_commit_about_to_start()
                # Acquire mutation lane (real wait when contended).
                # _get_mutation_lane is a lazy getter so there is no
                # circular-dependency issue with the MutationLane class.
                _get_mutation_lane().acquire(lane._lane if lane else None)
                lane.gpu_lane_wait_start()
                lane.gpu_lane_wait_end()
                lane.gpu_commit_start()
        try:
            return original(models, memory_required=memory_required,
                            force_patch_weights=force_patch_weights,
                            minimum_memory_required=minimum_memory_required,
                            force_full_load=force_full_load)
        finally:
            after = _gpu_depth.get()
            _gpu_depth.set(after - 1)
            if before == 0:
                lane = _ACTIVE_LANE_TRACE.get()
                if lane is not None:
                    lane.gpu_commit_end()
                    _get_mutation_lane().release(lane._lane if lane else None)
    wrapper._comfy_modal_gpu_wrapper = True  # sentinel for idempotence
    return wrapper


# ── Deep-diagnostic safetensors/torch.load decomposition wrappers ───
# Only active when:
#   1. _DIAGNOSTIC_FLAG is True
#   2. The calling thread's _DEEP_TARGET_PATH is non-empty AND matches
#      the file being accessed (avoid logging unrelated model loads)
#   3. The active lane trace is UNET
# These are globally installed but filtered by thread-local path, so
# unrelated file activity is never logged.


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

                    class _SafeOpenProxy:
                        """Delegating wrapper that preserves the full safe_open
                        interface (keys, get_tensor, metadata, context manager)
                        while wrapping get_tensor for aggregate diagnostics."""
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
                            try:
                                return self._orig_gt(k)
                            finally:
                                if lane2 is not None and lane2._lane == "UNET" and _DIAGNOSTIC_FLAG and _start_ns:
                                    self._count_agg[0] += 1
                                    try:
                                        _t = self._orig_gt(k)
                                        self._bytes_agg[0] += _t.numel() if hasattr(_t, "numel") else 0
                                    except Exception:
                                        pass

                        def __enter__(self):
                            return self

                        def __exit__(self, *exc):
                            return self._wrapped.__exit__(*exc) if hasattr(self._wrapped, "__exit__") else None

                        def keys(self):
                            return self._wrapped.keys()

                    _result = _SafeOpenProxy(_result, _orig_get_tensor,
                                             _tensor_count_agg, _tensor_bytes_agg)
                    lane._trace.emit("unet_tensor_materialize_aggregated", phase="restore",
                                     metadata={"tensor_count": _tensor_count_agg[0],
                                               "total_bytes": _tensor_bytes_agg[0]})
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
    else:
        result["load_models_gpu"] = "unavailable"

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

    return result


# ── UNET post-read subfunction wrappers (Section B) ─────────────────
# Installed idempotently on the live sys.modules; skip absent modules
# without breaking loading.  Only active when _ACTIVE_LANE_TRACE is UNET.

_UNET_DECOMPOSE_TARGETS: dict[str, tuple[str, str, str]] = {
    # NOTE: load_diffusion_model_state_dict is handled by a dedicated
    # wrapper (_make_sd_state_dict_wrapper) so it is intentionally absent.
    "convert_old_quants": ("comfy.utils", "convert_old_quants", "utils"),
    "state_dict_prefix_replace": ("comfy.utils", "state_dict_prefix_replace", "utils"),
    "calculate_parameters": ("comfy.utils", "calculate_parameters", "utils"),
    "weight_dtype": ("comfy.utils", "weight_dtype", "utils"),
    "model_config_from_unet": ("comfy.model_detection", "model_config_from_unet", "model_detection"),
    "unet_dtype": ("comfy.model_management", "unet_dtype", "model_management"),
    "unet_manual_cast": ("comfy.model_management", "unet_manual_cast", "model_management"),
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
    for short_name, (mod_name, func_name, category) in _UNET_DECOMPOSE_TARGETS.items():
        mod = _get_live_module(mod_name)
        if mod is None:
            result[short_name] = "unavailable"
            continue
        original = getattr(mod, func_name, None)
        if not callable(original):
            result[short_name] = "unavailable"
            continue
        if getattr(original, _SENTINEL_SUBFN, False):
            result[short_name] = "already_installed"
            continue
        wrapper = _make_unet_subfn_wrapper(short_name, original, category)
        setattr(wrapper, _SENTINEL_SUBFN, True)
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
        _fn_start_ns = time.monotonic_ns() if emit else 0
        if emit:
            lane._trace.emit(f"unet_{short_name}_start", phase="restore", metadata={
                "category": category,
            })
        try:
            return original(*args, **kwargs)
        finally:
            after = _UNET_SUBFN_DEPTH.get()
            _UNET_SUBFN_DEPTH.set(after - 1)
            if emit and _outer:
                _dur_ms = round((time.monotonic_ns() - _fn_start_ns) / 1_000_000, 3)
                lane._trace.emit(f"unet_{short_name}_end", phase="restore", metadata={
                    "category": category,
                    "duration_ms": _dur_ms,
                })
                # Record for outer SD residual computation
                _children = _child_durations.get()
                if _children is not None:
                    _children.append(_dur_ms)
    return wrapper


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
                _children = _child_durations.get() or []
                _child_total = round(sum(_children), 3)
                _whole_ms = round((time.monotonic_ns() - _sd_start_ns) / 1_000_000, 3)
                _residual_ms = round(max(0.0, _whole_ms - _child_total), 3)
                # Restore prior before emitting (children list snapshot taken)
                _child_durations.set(_prior_children)
                lane._trace.emit("unet_load_diffusion_model_state_dict_end", phase="restore", metadata={
                    "duration_ms": _whole_ms,
                    "measured_child_total_ms": _child_total,
                    "measured_child_count": len(_children),
                    "measured_children": _children,
                    "residual_ms": _residual_ms,
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
    """Coordinator-owned deterministic serialization of GPU/cache mutation.

    Only one caller may hold the lane at a time.  Priority order:
    ``UNET → CLIP → prefill → VAE → sampler``.  Acquire blocks until
    the lane is free; release hands ownership to the next waiter.
    Exception-safe via context manager.
    """

    _MUTEX_PRIORITY: dict[str, int] = {
        "UNET": 0, "CLIP": 1, "prefill": 2, "VAE": 3, "sampler": 4,
    }

    def __init__(self) -> None:
        self._lock = RLock()
        self._owner: str | None = None
        self._cond = Condition(self._lock)

    def acquire(self, owner: str | None, timeout: float | None = None) -> bool:
        """Block until the lane is acquired for *owner*."""
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

    # ── Internal lifecycle hooks (called by wrappers) ────────────────

    def _on_read_completed(self) -> None:
        """Called by the ``load_torch_file`` wrapper after each read_end."""
        self._actual_read_count += 1
        if self._actual_read_count >= self.expected_read_count and not self._cpu_prepare_started:
            self._cpu_prepare_started = True
            if self.expected_read_count > 0 and self._actual_read_count != self.expected_read_count:
                self.cpu_prepare_start(status="read_count_mismatch",
                                       expected=self.expected_read_count,
                                       actual=self._actual_read_count)
            else:
                self.cpu_prepare_start()

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
        self._trace.emit("background_unet_worker_start", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def worker_end(self, **metadata: Any) -> None:
        self._worker_ended_at_ns = time.monotonic_ns()
        self._trace.emit("background_unet_worker_end", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def worker_failed(self, **metadata: Any) -> None:
        self._trace.emit("background_unet_worker_failed", phase=self._phase,
                         metadata={"lane": self._lane, **metadata})

    def read_start(self, **metadata: Any) -> None:
        self._trace.emit("read_start", phase=self._phase, metadata={"lane": self._lane, **metadata})

    def read_end(self, **metadata: Any) -> None:
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

    token = _ACTIVE_LANE_TRACE.set(lane_trace)
    lane_trace.worker_start(canonical_key=_canonical_key_str)
    try:
        yield lane_trace
        lane_trace.worker_end()
        # ready() is called AFTER cache publication completes — the
        # caller is responsible for calling cache_publish_start(),
        # cache_object_store(), cache_metadata_store(), done_event_set(),
        # cache_publish_end() before this scope exits.
        lane_trace.ready()
    except BaseException as exc:
        lane_trace.worker_end()
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
        "wall_unix_ns": int(time.time() * 1_000_000_000),
        "monotonic_ns": time.monotonic_ns(),
        "restored_instance_id": restored_instance_id,
        "restore_session_id": restore_session_id,
        "legacy_container_session_id": legacy_container_session_id,
        "modal_task_id": modal_task_id,
        "pid": pid,
    }


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
    if _DIAGNOSTIC_FLAG and platform.system() == "Linux":
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
    Only on Linux with deep diag enabled.  Returns flat dict of ints.
    The caller must compute deltas externally."""
    if not _DIAGNOSTIC_FLAG:
        return None
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
    """Compute /proc/self/task/<tid>/io deltas (after - before)."""
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
        "read_to_ready_ms": None,
        "cpu_prepare_ms": None,
        "gpu_wait_ms": None,
        "gpu_commit_ms": None,
        "read_end_to_ready_ms": None,
        "worker_total_ms": None,
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
        result_clip["cpu_prepare_ms"] = round((cpe - cps) / 1_000_000, 3)
    if gws and gwe:
        result_clip["gpu_wait_ms"] = round((gwe - gws) / 1_000_000, 3)
    if gcs and gce:
        result_clip["gpu_commit_ms"] = round((gce - gcs) / 1_000_000, 3)
    if re and rdy:
        result_clip["read_end_to_ready_ms"] = round((rdy - re) / 1_000_000, 3)
    if wws and wwe:
        result_clip["worker_total_ms"] = round((wwe - wws) / 1_000_000, 3)

    return result_breakdown, result_clip


# ── Background UNET IO/stages summary emission ──────────────────────


def _emit_bg_unet_io_summary(trace: RuntimeTrace, *, canonical_key: str = "",
                               target_path: str = "", force: bool = False) -> None:
    """Emit a compact [v2.bg_unet_io] line from trace events.

    Summarises file stat, open, mmap, safetensors parse, tensor materialization
    durations.  Missing stages → None.  Only emits when deep diag produced
    events or *force* is True.

    NOTE: file_open and mmap_create are always None/absent because the real
    safetensors/torch.load implementations do not expose separable Python-callable
    boundaries for these stages.  They are listed only for forward compatibility
    — do not emit synthetic values.
    """
    if not force and not _DIAGNOSTIC_FLAG:
        return
    stages: dict[str, Any] = {"file_stat_ms": None, "file_open_ms": None,
                               "mmap_create_ms": None, "safetensors_open_ms": None,
                               "safetensors_parse_ms": None,
                               "tensor_materialization_ms": None,
                               "safetensors_combined_ms": None,
                               "load_torch_file_ms": None, "stage_split_available": None}
    events = trace.events
    for i, evt in enumerate(events):
        _meta = evt.metadata if hasattr(evt, "metadata") else {}
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
                    break
        elif evt.name == "unet_tensor_materialize_start":
            for j in range(i + 1, min(i + 200, len(events))):
                if events[j].name == "unet_tensor_materialize_end":
                    _prev = stages.get("tensor_materialization_ms", 0) or 0
                    stages["tensor_materialization_ms"] = round(
                        _prev + (events[j].monotonic_ns - evt.monotonic_ns) / 1_000_000, 3)
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
    print(
        f"[v2.bg_unet_io] "
        f"file_stat_ms={stages['file_stat_ms']} "
        f"file_open_ms={stages['file_open_ms']} "
        f"mmap_create_ms={stages['mmap_create_ms']} "
        f"safetensors_open_ms={stages['safetensors_open_ms']} "
        f"safetensors_parse_ms={stages['safetensors_parse_ms']} "
        f"tensor_materialization_ms={stages['tensor_materialization_ms']} "
        f"safetensors_combined_ms={stages['safetensors_combined_ms']} "
        f"load_torch_file_ms={stages['load_torch_file_ms']} "
        f"stage_split_available={stages['stage_split_available']} "
        f"canonical_key={canonical_key[-32:] if canonical_key else ''}",
        flush=True,
    )


def _emit_bg_unet_stages_summary(trace: RuntimeTrace, *, canonical_key: str = "",
                                   weight_dtype: str = "", force: bool = False) -> None:
    """Emit compact [v2.bg_unet_stages] line from trace events.

    Summarises worker queue, model construction subfunction durations, GPU commit,
    and cache publication.  Missing stages → None.
    """
    if not force and not _DIAGNOSTIC_FLAG:
        return
    stages: dict[str, Any] = {
        "submission_to_worker_start_ms": None,
        "worker_wall_ms": None, "worker_thread_cpu_ms": None,
        "model_construction_total_ms": None,
        "measured_children_ms": None,
        "unattributed_residual_ms": None,
        "gpu_lane_wait_ms": None, "gpu_commit_ms": None,
        "cache_publish_ms": None,
        "background_gpu_transfer_present": False,
        "weight_dtype": weight_dtype,
    }
    events = trace.events
    _submitted_ns = 0
    _worker_start_ns = 0
    _worker_end_ns = 0
    _gpu_wait_start = 0
    _gpu_wait_end = 0
    _gpu_commit_start = 0
    _gpu_commit_end = 0
    _cache_pub_start = 0
    _cache_pub_end = 0
    _sd_total = 0.0
    _children_total = 0.0

    for i, evt in enumerate(events):
        if evt.name == "background_unet_submitted":
            _submitted_ns = evt.monotonic_ns
        elif evt.name == "background_unet_worker_start":
            _worker_start_ns = evt.monotonic_ns
        elif evt.name == "background_unet_worker_end":
            _worker_end_ns = evt.monotonic_ns
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
                    _sd_total = events[j].metadata.get("duration_ms", 0) if hasattr(events[j], "metadata") else 0
                    _children_total = events[j].metadata.get("measured_child_total_ms", 0) if hasattr(events[j], "metadata") else 0
                    break

    if _submitted_ns and _worker_start_ns:
        stages["submission_to_worker_start_ms"] = round((_worker_start_ns - _submitted_ns) / 1_000_000, 3)
    if _worker_start_ns and _worker_end_ns:
        stages["worker_wall_ms"] = round((_worker_end_ns - _worker_start_ns) / 1_000_000, 3)
    if _gpu_wait_start and _gpu_wait_end:
        stages["gpu_lane_wait_ms"] = round((_gpu_wait_end - _gpu_wait_start) / 1_000_000, 3)
        stages["background_gpu_transfer_present"] = True
    if _gpu_commit_start and _gpu_commit_end:
        stages["gpu_commit_ms"] = round((_gpu_commit_end - _gpu_commit_start) / 1_000_000, 3)
        stages["background_gpu_transfer_present"] = True
    if _cache_pub_start and _cache_pub_end:
        stages["cache_publish_ms"] = round((_cache_pub_end - _cache_pub_start) / 1_000_000, 3)

    stages["model_construction_total_ms"] = round(_sd_total, 3) if _sd_total else None
    stages["measured_children_ms"] = round(_children_total, 3) if _children_total else None
    if _sd_total and _children_total:
        stages["unattributed_residual_ms"] = round(max(0.0, _sd_total - _children_total), 3)
    elif _sd_total:
        stages["unattributed_residual_ms"] = None  # no children measured → residual classification N/A

    print(
        f"[v2.bg_unet_stages] "
        f"submission_to_worker_start_ms={stages['submission_to_worker_start_ms']} "
        f"worker_wall_ms={stages['worker_wall_ms']} "
        f"model_construction_total_ms={stages['model_construction_total_ms']} "
        f"measured_children_ms={stages['measured_children_ms']} "
        f"unattributed_residual_ms={stages['unattributed_residual_ms']} "
        f"gpu_lane_wait_ms={stages['gpu_lane_wait_ms']} "
        f"gpu_commit_ms={stages['gpu_commit_ms']} "
        f"cache_publish_ms={stages['cache_publish_ms']} "
        f"background_gpu_transfer_present={stages['background_gpu_transfer_present']} "
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
                _ensure_core_wrappers(trace=trace)
                # Install UNET post-read decomposition wrappers (Section B).
                # Only active when _ACTIVE_LANE_TRACE is UNET; absent
                # symbols are skipped without breaking loading.
                _ensure_unet_decompose_wrappers(trace=trace)

                result = callback()
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

    def clear(self) -> None:
        """Disable consumption when a restore has no authoritative plan."""
        self._model_key = None
        self._prefill_key = None
        self._model_spec = {}
        self._preparation = None
        self._trace = None
        self._preparation_trace = None
        self._preparation_event_cursor = 0
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
        result = self._invoke_original("UNETLoader", kwargs)
        return result[0] if isinstance(result, (tuple, list)) and result else result

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
            clip_a = kwargs.get("clip_name1", args[0] if args else "")
            clip_b = kwargs.get("clip_name2", args[1] if len(args) > 1 else "")
            identity = f"{clip_a}||{clip_b}"
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
