"""Flag-gated single-iteration CUDA profiling hooks (Ideogram steady state).

Minimal, observe-only, request-local instrumentation for ONE steady-state
Ideogram sampler iteration (cond + uncond + CFG/guider/sampler).  Disabled by
default; armed only around actual Golden sampling (``golden_sampling``), so
CLIP/load stages before it and VAE/teardown after it stay outside capture.

Flags (registered in ``config/v2/flag_registry.toml`` + ``config_authority``):
  COMFYMODAL_V2_IDEOGRAM_CUDA_PROFILE              off|torch|nsys (default off)
  COMFYMODAL_V2_IDEOGRAM_CUDA_PROFILE_ITERATION    zero-based index (default 3)
  COMFYMODAL_V2_IDEOGRAM_CUDA_PROFILE_BLOCK_RANGES 0|1 (default 0)

Backends:
  torch -- Kineto capture re-scoped to the single iteration (CPU+CUDA,
           record_shapes=False, profile_memory=False, with_stack=False).
  nsys  -- NVTX ranges only (``torch.cuda.nvtx`` push/pop); never starts a
           Torch/Kineto profiler, so Torch/Kineto + nsys CUDA collection are
           never run simultaneously.

Ordering model (completed-step callbacks follow step work, matching stock
ComfyUI / the Golden ``callback`` wrapper): the target iteration's forwards
fall between callback(target-1) and callback(target).  The completed-step
callback may precede the final sampler update, so the span is always reported
as partial with the reason recorded.  No count-based fallback: without step
callbacks (and target > 0) the iteration is reported unresolved, never
fabricated from alternating forward counts.

Forward labels come from actual conditioning metadata only:
  - both cond-ish and uncond-ish markers in one call -> BATCHED_FORWARD
    (batched CFG handled honestly, not split by alternation).
  - ``transformer_options["cond_or_uncond"]`` all-1 / all-0 -> CONDITIONAL /
    UNCONDITIONAL; mixed -> BATCHED.
  - one-sided explicit markers only -> CONDITIONAL / UNCONDITIONAL.
  - shared keys (e.g. ``context`` identical on both calls) or no markers ->
    UNKNOWN (values are never inspected: observe-only, no sync/copies).
  - a lone forward in the iteration (skipped CFG / non-CFG step) is reported
    as-is, not as an error.

CFG_GUIDER_SAMPLER is the parent range enclosing the iteration's forwards;
it marks non-forward work only via exclusive time (parent minus children),
computed offline.

Observe-only contract: no ``.item()``/copies/dtype changes/new streams/
allocator cleanup, no sync inside blocks/attention/quant/GEMMs, no cross-stage
prefetch/overlap; Golden Serial is preserved.  All failures degrade to a
``skipped``/``unresolved`` artifact; nothing here ever raises into sampling.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import contextvars
import os
import tempfile
import threading
import time
from typing import Any

SCHEMA_VERSION = 1
EVENT_NAME = "ideogram_cuda_profile"

FLAG_BACKEND = "COMFYMODAL_V2_IDEOGRAM_CUDA_PROFILE"
FLAG_ITERATION = "COMFYMODAL_V2_IDEOGRAM_CUDA_PROFILE_ITERATION"
FLAG_BLOCK_RANGES = "COMFYMODAL_V2_IDEOGRAM_CUDA_PROFILE_BLOCK_RANGES"
# Export dir override (container os.environ read; explicit value always wins).
FLAG_PROFILE_DIR = "COMFYMODAL_V2_IDEOGRAM_CUDA_PROFILE_DIR"

# Already-mounted persistent volumes, used as the default export base so the
# Chrome trace is retrievable off-container.  Keep in sync with
# ``modal_app.PROFILE_PATH`` / ``modal_app.RUNTIME_STATE_PATH`` (duplicated,
# not imported: this module must stay import-light for FAST_UNIT).
# NOTE: the profile volume is mounted only when V2 full-trace is enabled;
# the runtime-state volume is always mounted.
PROFILE_MOUNT_PATH = "/mnt/comfymodal_profiles"
RUNTIME_STATE_MOUNT_PATH = "/mnt/comfymodal_runtime_state"
EXPORT_SUBDIR = "ideogram_cuda_profile"

BACKEND_OFF = "off"
BACKEND_TORCH = "torch"
BACKEND_NSYS = "nsys"
_VALID_BACKENDS = frozenset({BACKEND_OFF, BACKEND_TORCH, BACKEND_NSYS})

DEFAULT_ITERATION = 3  # 4th of 16, after stabilization
MAX_BLOCK_RANGES = 68  # 34 COND + 34 UNCOND ceiling; no per-op flood
FINALIZE_TIMEOUT_S = 30.0  # bounded export; Kineto stalls documented
_MAX_RANGE_STACK = 8
_MAX_STEPS_SEEN = 32

_CALLBACK_NAMES = frozenset({"callback", "callback_function"})
_WRAPPED_MARKER = "_comfymodal_ideogram_profile_wrapped"

# Conditioning metadata markers (exact lowercase kwarg-key match).
_COND_KEYS = frozenset({
    "cond", "conditioning", "positive", "prompt_embeds", "text_embeds",
    "encoder_hidden_states", "clip_embeds", "cond_emb",
})
_UNCOND_KEYS = frozenset({
    "uncond", "unconditional", "negative", "neg_embeds",
    "negative_prompt_embeds",
})

# Stable shared DiT block containers probed in order; first stable hit wins.
_BLOCK_CONTAINERS = (
    "transformer_blocks", "double_blocks", "single_blocks", "blocks",
    "layers", "dit_blocks", "transformer_layers",
)


def _resolve_backend(raw: Any) -> tuple[str, str | None]:
    selected = str(raw if raw is not None else BACKEND_OFF).strip().lower()
    if selected in _VALID_BACKENDS:
        return selected, None
    return BACKEND_OFF, f"invalid_backend_fallback_to_off:{str(raw)[:32]}"


def _resolve_iteration(raw: Any) -> tuple[int, str | None]:
    try:
        value = int(str(raw).strip(), 10)
    except (TypeError, ValueError, AttributeError):
        return DEFAULT_ITERATION, f"invalid_iteration_fallback_to_default:{str(raw)[:32]}"
    if isinstance(raw, bool) or value < 0:
        return DEFAULT_ITERATION, f"invalid_iteration_fallback_to_default:{str(raw)[:32]}"
    return value, None


def _resolve_bool(raw: Any) -> bool:
    return str(raw if raw is not None else "").strip().lower() in {
        "1", "true", "yes", "on",
    }


class _IdeogramCapture:
    """One request's single-iteration capture state (never shared)."""

    __slots__ = (
        "request_id", "backend", "iteration", "block_ranges",
        "armed_thread_id", "armed_monotonic_ns",
        "capturing", "done", "pending_late", "anchor", "last_callback",
        "steps_seen", "unknown_callbacks",
        "iteration_open_ns", "close_reason",
        "cur_forward_label", "forward_ordinal",
        "cond_count", "uncond_count", "batched_count", "unknown_count",
        "kwarg_key_sets", "ranges_emitted", "ranges_forced_closed",
        "range_stack", "stack_mismatches",
        "block_supported", "block_reason", "block_containers",
        "block_range_count", "block_handles", "block_capped",
        "forward_notifications", "callback_notifications",
        "torch_profiler", "torch_started", "torch_start_thread",
        "torch_skip_reason", "torch_stop_ms", "torch_export_ms",
        "torch_export_path", "torch_export_timeout", "torch_export_volume",
        "torch_export_commit",
        "warnings", "finalized",
    )

    def __init__(
        self, request_id: str, backend: str, iteration: int, block_ranges: bool
    ) -> None:
        self.request_id = request_id
        self.backend = backend
        self.iteration = iteration
        self.block_ranges = block_ranges
        self.armed_thread_id = threading.get_ident()
        self.armed_monotonic_ns = time.monotonic_ns()
        self.capturing = False
        self.done = False
        self.pending_late = False
        self.anchor: Any = None
        self.last_callback: Any = None
        self.steps_seen: list[Any] = []
        self.unknown_callbacks = 0
        self.iteration_open_ns: int | None = None
        self.close_reason: str | None = None
        self.cur_forward_label = "UNKNOWN"
        self.forward_ordinal = 0
        self.cond_count = 0
        self.uncond_count = 0
        self.batched_count = 0
        self.unknown_count = 0
        self.kwarg_key_sets: list[str] = []
        self.ranges_emitted: list[str] = []
        self.ranges_forced_closed = 0
        self.range_stack: list[tuple[str, Any]] = []
        self.stack_mismatches = 0
        self.block_supported = False
        self.block_reason = "not_probed"
        self.block_containers: list[str] = []
        self.block_range_count = 0
        self.block_handles: list[Any] = []
        self.block_capped = False
        self.forward_notifications = 0
        self.callback_notifications = 0
        self.torch_profiler: Any = None
        self.torch_started = False
        self.torch_start_thread: int | None = None
        self.torch_skip_reason: str | None = None
        self.torch_stop_ms: float | None = None
        self.torch_export_ms: float | None = None
        self.torch_export_path: str | None = None
        self.torch_export_timeout = False
        self.torch_export_volume: str | None = None
        self.torch_export_commit: str | None = None
        self.warnings: list[str] = []
        self.finalized = False


_ACTIVE: contextvars.ContextVar[_IdeogramCapture | None] = contextvars.ContextVar(
    "comfymodal_ideogram_cuda_profile", default=None
)


def get_active() -> _IdeogramCapture | None:
    """Return the request-local capture, or None when disabled/unset."""
    try:
        return _ACTIVE.get()
    except Exception:
        return None


def _warn(cap: _IdeogramCapture, message: str) -> None:
    if len(cap.warnings) < 16:
        cap.warnings.append(str(message)[:160])


# ── NVTX / record_function ranges (backend-selected) ──────────────────────────

# Bound the distinct kwarg-key evidence kept on the capture.
_MAX_KWARG_SETS = 4


@contextlib.contextmanager
def _backend_range(name: str, backend: str):
    """Yield a closeable range handle for *backend* (never raises)."""
    if backend == BACKEND_NSYS:
        try:
            import torch as _torch  # type: ignore[import-not-found]

            _nvtx = getattr(getattr(_torch, "cuda", None), "nvtx", None)
            if _nvtx is not None:
                _nvtx.range_push(str(name))
                try:
                    yield
                finally:
                    try:
                        _nvtx.range_pop()
                    except Exception:
                        pass
                return
        except Exception:
            pass
        yield
        return
    if backend == BACKEND_TORCH:
        try:
            import torch.profiler as _profiler  # type: ignore[import-not-found]

            with _profiler.record_function(str(name)):
                yield
            return
        except Exception:
            pass
        yield
        return
    yield


def _open_range(cap: _IdeogramCapture, name: str) -> None:
    """Enter one backend range, tracked on the capture stack (bounded)."""
    while len(cap.range_stack) >= _MAX_RANGE_STACK:
        _label, _exiter = cap.range_stack.pop(0)
        try:
            _exiter()
        except Exception:
            pass
        cap.ranges_forced_closed += 1
        _warn(cap, f"range_stack_overflow_forced_close:{_label}")
    try:
        _cm = _backend_range(str(name), cap.backend)
        _exiter = _cm.__enter__()
    except Exception:
        _warn(cap, f"range_open_failed:{name}")
        return
    cap.range_stack.append((str(name), _cm.__exit__))
    if len(cap.ranges_emitted) < 96:
        cap.ranges_emitted.append(str(name))


def _close_range(cap: _IdeogramCapture) -> None:
    """Close the most recently opened range (LIFO; mismatch-safe)."""
    if not cap.range_stack:
        cap.stack_mismatches += 1
        return
    _label, _exiter = cap.range_stack.pop()
    try:
        _exiter(None, None, None)
    except Exception:
        _warn(cap, f"range_close_failed:{_label}")


def _close_all_ranges(cap: _IdeogramCapture, reason: str) -> None:
    while cap.range_stack:
        _close_range(cap)
    if reason and len(cap.warnings) < 16:
        pass


# ── Conditioning classification (metadata only, never values) ────────────────

def _cond_or_uncond_marker(args: tuple, kwargs: dict) -> Any | None:
    """Return the ``cond_or_uncond`` marker list when present, else None."""
    try:
        _opts = kwargs.get("transformer_options")
        if isinstance(_opts, dict) and "cond_or_uncond" in _opts:
            return _opts["cond_or_uncond"]
        for _arg in args:
            if isinstance(_arg, dict) and "cond_or_uncond" in _arg:
                return _arg["cond_or_uncond"]
    except Exception:
        pass
    return None


def classify_conditioning(args: tuple, kwargs: dict | None) -> tuple[str, dict]:
    """Classify one diffusion-model forward from conditioning metadata.

    Returns ``(label, detail)`` with label in CONDITIONAL / UNCONDITIONAL /
    BATCHED / UNKNOWN.  Never inspects tensor values (observe-only).
    """
    _kwargs = kwargs if isinstance(kwargs, dict) else {}
    try:
        _keys = {str(k).lower() for k in _kwargs.keys()}
    except Exception:
        _keys = set()
    _has_cond = bool(_keys & _COND_KEYS)
    _has_uncond = bool(_keys & _UNCOND_KEYS)
    if _has_cond and _has_uncond:
        return "BATCHED", {"reason": "cond_and_uncond_keys_one_call"}
    _marker = _cond_or_uncond_marker(args, _kwargs)
    if _marker is not None:
        try:
            _flags = [int(v) for v in list(_marker)]
        except Exception:
            _flags = []
        if _flags and all(v == 1 for v in _flags):
            return "CONDITIONAL", {"reason": "cond_or_uncond_all_1"}
        if _flags and all(v == 0 for v in _flags):
            return "UNCONDITIONAL", {"reason": "cond_or_uncond_all_0"}
        if _flags:
            return "BATCHED", {"reason": "cond_or_uncond_mixed"}
    if _has_cond:
        return "CONDITIONAL", {"reason": "explicit_cond_keys"}
    if _has_uncond:
        return "UNCONDITIONAL", {"reason": "explicit_uncond_keys"}
    _batch: Any = None
    try:
        _x = args[0] if args else None
        _shape = getattr(_x, "shape", None)
        if _shape is not None:
            _batch = int(list(_shape)[0])
    except Exception:
        _batch = None
    return "UNKNOWN", {
        "reason": "shared_or_absent_markers_values_not_inspected",
        "batch": _batch,
    }


# ── Arm / step / forward seams ───────────────────────────────────────────────

def _resolve_diffusion_model(patcher: Any) -> Any | None:
    try:
        from comfymodal_runtime.unet_forward_probe import (
            resolve_diffusion_model as _resolve,
        )

        _, _dm = _resolve(patcher)
        return _dm
    except Exception:
        return None


def arm_ideogram_profile(request_id: str, patcher: Any = None) -> Any | None:
    """Arm the single-iteration capture for this request (never raises).

    Returns the capture, or None when disabled.  Reads flags once at the
    request boundary; disabled by default.
    """
    try:
        backend, _backend_warn = _resolve_backend(os.environ.get(FLAG_BACKEND))
        iteration, _iter_warn = _resolve_iteration(os.environ.get(FLAG_ITERATION))
        block_ranges = _resolve_bool(os.environ.get(FLAG_BLOCK_RANGES))
        if backend == BACKEND_OFF:
            return None
        if get_active() is not None:
            return get_active()
        cap = _IdeogramCapture(
            request_id=str(request_id or ""),
            backend=backend,
            iteration=int(iteration),
            block_ranges=bool(block_ranges),
        )
        if _backend_warn:
            _warn(cap, _backend_warn)
        if _iter_warn:
            _warn(cap, _iter_warn)
        if block_ranges:
            _install_block_hooks(cap, _resolve_diffusion_model(patcher))
        else:
            cap.block_reason = "flag_disabled"
        _ACTIVE.set(cap)
        return cap
    except Exception:
        return None


def notify_sampler_step(index: Any) -> None:
    """Record one completed-step callback index (never raises)."""
    try:
        cap = get_active()
        if cap is None or cap.done:
            return
        cap.callback_notifications += 1
        if not isinstance(index, int) or isinstance(index, bool):
            cap.unknown_callbacks += 1
            return
        if index != cap.last_callback and len(cap.steps_seen) < _MAX_STEPS_SEEN:
            cap.steps_seen.append(int(index))
        cap.last_callback = int(index)
        if cap.capturing:
            # Completed-step callback for the target (or later) step: the
            # iteration's forwards are done; close (span stays partial: a
            # trailing sampler update may extend beyond this boundary).
            if int(index) >= int(cap.iteration):
                end_iteration("completed_step_callback")
        else:
            if int(index) == int(cap.iteration):
                # Late-open fallback (forwards missed the anchor, e.g. hooks
                # attached after sampling began); the span is partial.
                cap.pending_late = True
    except Exception:
        pass


def notify_step_index(value: Any) -> None:
    """Notify from a raw sampler-callback index value (never raises).

    Applies the same int extraction the sampler seams use (``args[0]`` is
    the completed-step index; bools / non-ints count as unknown).  Exists
    so the PromptExecutor-compatible SAMPLER_SAMPLE wrapper can feed step
    indices without duplicating the extraction rule.
    """
    try:
        notify_sampler_step(
            value if isinstance(value, int) and not isinstance(value, bool) else None
        )
    except Exception:
        pass


def _should_begin(cap: _IdeogramCapture) -> tuple[bool, Any, bool]:
    """Return ``(begin, anchor, late)`` for the current forward."""
    if cap.pending_late:
        return True, cap.last_callback, True
    if cap.last_callback is None and int(cap.iteration) == 0:
        return True, -1, False
    if cap.last_callback is not None and int(cap.last_callback) == int(cap.iteration) - 1:
        return True, int(cap.last_callback), False
    return False, None, False


def _start_torch_profiler(cap: _IdeogramCapture) -> None:
    """Start the re-scoped Kineto profiler (torch backend only, never raises)."""
    try:
        import torch as _torch  # type: ignore[import-not-found]
        import torch.profiler as _profiler  # type: ignore[import-not-found]
    except Exception:
        cap.torch_skip_reason = "torch_unavailable"
        return
    try:
        from torch._C._profiler import _kineto_profiler_running  # type: ignore[import-not-found]

        if _kineto_profiler_running():
            cap.torch_skip_reason = (
                "kineto_conflict:never_run_torch_kineto_and_nsys_simultaneously"
            )
            _warn(cap, str(cap.torch_skip_reason))
            return
    except Exception:
        pass
    try:
        _activities = [_profiler.ProfilerActivity.CPU]
        try:
            if _torch.cuda.is_available():
                _activities.append(_profiler.ProfilerActivity.CUDA)
            else:
                _warn(cap, "cuda_unavailable_cpu_only")
        except Exception:
            _warn(cap, "cuda_availability_probe_failed")
        cap.torch_profiler = _profiler.profile(
            activities=_activities,
            record_shapes=False,
            profile_memory=False,
            with_stack=False,
            with_modules=False,
        )
        cap.torch_profiler.__enter__()
        cap.torch_started = True
        cap.torch_start_thread = threading.get_ident()
    except Exception as exc:
        cap.torch_profiler = None
        cap.torch_skip_reason = f"torch_start_failed:{type(exc).__name__}"
        _warn(cap, str(cap.torch_skip_reason))


def begin_iteration() -> bool:
    """Open IDEOGRAM_ITERATION + CFG_GUIDER_SAMPLER (never raises)."""
    try:
        cap = get_active()
        if cap is None or cap.capturing or cap.done:
            return False
        cap.capturing = True
        cap.iteration_open_ns = time.monotonic_ns()
        if cap.backend == BACKEND_TORCH:
            _start_torch_profiler(cap)
        _open_range(cap, "IDEOGRAM_ITERATION")
        _open_range(cap, "CFG_GUIDER_SAMPLER")
        return True
    except Exception:
        return False


def end_iteration(reason: str) -> None:
    """Close the iteration ranges; profiler stop/export happens in finalize."""
    try:
        cap = get_active()
        if cap is None or not cap.capturing or cap.done:
            return
        cap.capturing = False
        cap.done = True
        cap.close_reason = str(reason or "unknown")
        _close_all_ranges(cap, str(reason or ""))
        if cap.pending_late:
            _warn(cap, "opened_late_span_partial")
    except Exception:
        pass


def observe_forward_pre(module: Any, args: tuple, kwargs: dict | None) -> None:
    """Observe one diffusion-model forward entry (never raises, returns None)."""
    try:
        cap = get_active()
        if cap is None:
            return
        cap.forward_notifications += 1
        if cap.done:
            return
        if not cap.capturing:
            _begin, _anchor, _late = _should_begin(cap)
            if not _begin:
                return
            cap.anchor = _anchor
            cap.pending_late = bool(_late)
            begin_iteration()
            if not cap.capturing:
                return
        label, detail = classify_conditioning(tuple(args or ()), kwargs)
        cap.cur_forward_label = str(label)
        cap.forward_ordinal += 1
        if label == "CONDITIONAL":
            cap.cond_count += 1
        elif label == "UNCONDITIONAL":
            cap.uncond_count += 1
        elif label == "BATCHED":
            cap.batched_count += 1
        else:
            cap.unknown_count += 1
        try:
            _keys = sorted(str(k).lower() for k in (kwargs or {}).keys())[:12]
            _sig = ",".join(_keys)
            if _sig and _sig not in cap.kwarg_key_sets and len(cap.kwarg_key_sets) < _MAX_KWARG_SETS:
                cap.kwarg_key_sets.append(_sig)
        except Exception:
            pass
        _open_range(cap, f"{label}_FORWARD")
    except Exception:
        pass


def observe_forward_post(module: Any = None) -> None:
    """Close the most recent forward range (never raises)."""
    try:
        cap = get_active()
        if cap is None:
            return
        _close_range(cap)
    except Exception:
        pass


# ── Optional per-DiT-block ranges (stable seam only, capped) ──────────────────

def _iter_block_modules(dm: Any) -> tuple[list[tuple[str, Any]], str | None]:
    """Collect hookable block submodules (bounded); ``None`` reason if none."""
    if dm is None:
        return [], "diffusion_model_unavailable"
    _found: list[tuple[str, Any]] = []
    _containers: list[str] = []
    for _name in _BLOCK_CONTAINERS:
        try:
            _seq = getattr(dm, _name, None)
        except Exception:
            continue
        if _seq is None:
            continue
        try:
            _items = list(_seq)
        except Exception:
            continue
        if not _items or len(_items) > MAX_BLOCK_RANGES:
            continue
        if not all(callable(getattr(_m, "register_forward_pre_hook", None)) for _m in _items):
            continue
        _containers.append(str(_name))
        for _idx, _mod in enumerate(_items):
            if len(_found) >= MAX_BLOCK_RANGES:
                break
            _found.append((f"{_name}[{_idx}]", _mod))
        if len(_found) >= MAX_BLOCK_RANGES:
            break
    if not _found:
        return [], "no_stable_dit_block_seam"
    return _found, None


def _install_block_hooks(cap: _IdeogramCapture, dm: Any) -> None:
    """Install bounded per-block pre/post ranges (never raises)."""
    try:
        _blocks, _reason = _iter_block_modules(dm)
        if not _blocks:
            cap.block_supported = False
            cap.block_reason = str(_reason or "unknown")
            return
        cap.block_supported = True
        cap.block_reason = "installed"
        cap.block_containers = sorted({str(n).split("[")[0] for n, _ in _blocks})
        if len(_blocks) >= MAX_BLOCK_RANGES:
            cap.block_capped = True

        def _make_pre(block_index: int):
            def _pre(module: Any, args: tuple, kwargs: dict | None = None) -> None:
                try:
                    _cap = get_active()
                    if _cap is None or not _cap.capturing or not _cap.block_ranges:
                        return
                    _short = {
                        "CONDITIONAL": "COND",
                        "UNCONDITIONAL": "UNCOND",
                        "BATCHED": "BATCHED",
                    }.get(str(_cap.cur_forward_label), "UNKNOWN")
                    _open_range(_cap, f"{_short}_BLOCK_{block_index:02d}")
                    _cap.block_range_count += 1
                except Exception:
                    pass

            return _pre

        def _make_post():
            def _post(module: Any, args: tuple, output: Any) -> None:
                try:
                    _cap = get_active()
                    if _cap is None or not _cap.capturing:
                        return
                    _close_range(_cap)
                except Exception:
                    pass

            return _post

        for _idx, (_label, _mod) in enumerate(_blocks):
            try:
                _pre_register = getattr(_mod, "register_forward_pre_hook", None)
                _post_register = getattr(_mod, "register_forward_hook", None)
                if not callable(_pre_register) or not callable(_post_register):
                    continue
                try:
                    cap.block_handles.append(_pre_register(_make_pre(_idx), with_kwargs=True))
                except TypeError:
                    cap.block_handles.append(_pre_register(_make_pre(_idx)))
                cap.block_handles.append(_post_register(_make_post()))
            except Exception:
                continue
    except Exception as exc:
        cap.block_supported = False
        cap.block_reason = f"install_failed:{type(exc).__name__}"


def _remove_block_hooks(cap: _IdeogramCapture) -> None:
    for _handle in cap.block_handles:
        try:
            _remove = getattr(_handle, "remove", None)
            if callable(_remove):
                _remove()
        except Exception:
            pass
    cap.block_handles = []


# ── Sampler-callback wrap (independent of diagnostics) ────────────────────────

def maybe_wrap_sampler_callback(inputs: dict) -> dict:
    """Wrap an already-present sampler callback with the step notifier.

    Returns *inputs* unchanged when profiling is off/armed-absent; absent
    callbacks stay absent; never changes sampler inputs or order.
    """
    try:
        cap = get_active()
        if cap is None or not isinstance(inputs, dict):
            return inputs
        wrapped = dict(inputs)
        for _key, _value in list(wrapped.items()):
            if str(_key).lower() not in _CALLBACK_NAMES:
                continue
            if callable(_value):
                wrapped[_key] = _wrap_callback(_value)
            elif isinstance(_value, list) and len(_value) == 1 and callable(_value[0]):
                wrapped[_key] = [_wrap_callback(_value[0])]
        return wrapped
    except Exception:
        return inputs


def _wrap_callback(callback: Any) -> Any:
    try:
        if getattr(callback, _WRAPPED_MARKER, False):
            return callback
    except Exception:
        return callback

    def _notifying(*args: Any, **kwargs: Any) -> Any:
        try:
            _idx = args[0] if args else kwargs.get("i", kwargs.get("step", None))
            notify_sampler_step(
                _idx if isinstance(_idx, int) and not isinstance(_idx, bool) else None
            )
        except Exception:
            pass
        return callback(*args, **kwargs)

    try:
        setattr(_notifying, _WRAPPED_MARKER, True)
    except Exception:
        pass
    return _notifying


# ── Finalize (once, outside the iteration wall, bounded export) ───────────────

# ── Export placement + volume commit (retrieval) ────────────────────────────

def _resolve_export_base() -> tuple[str, str]:
    """Return ``(directory, volume_kind)`` for the Chrome trace export.

    Precedence: explicit ``COMFYMODAL_V2_IDEOGRAM_CUDA_PROFILE_DIR`` env,
    then the already-mounted profile volume (read by
    ``tools/golden_profile_pipeline.py``), then the always-mounted
    runtime-state volume, then the local tempdir (unreachable off-container,
    last resort).  Flag semantics unchanged: this only runs for an armed
    (flag-on) capture.
    """
    try:
        _explicit = str(os.environ.get(FLAG_PROFILE_DIR, "") or "").strip()
    except Exception:
        _explicit = ""
    if _explicit:
        return _explicit, "explicit_env"
    for _mount, _kind in (
        (PROFILE_MOUNT_PATH, "profile"),
        (RUNTIME_STATE_MOUNT_PATH, "runtime_state"),
    ):
        try:
            if os.path.isdir(_mount):
                return os.path.join(_mount, EXPORT_SUBDIR), _kind
        except Exception:
            continue
    return os.path.join(tempfile.gettempdir(), EXPORT_SUBDIR), "local_temp"


def _commit_export_volume(export_path: str | None, volume_kind: str | None) -> str:
    """Best-effort sync commit of the volume holding the export (never raises).

    Reuses the existing ``modal_app._MODAL_RESOURCES`` volume handle (no new
    Modal infrastructure).  Runs post-sampling only, for flag-on captures.
    Returns a short status string recorded on the artifact.
    """
    try:
        if not export_path or volume_kind not in ("profile", "runtime_state"):
            return "skipped_no_volume_handle"
        try:
            from comfymodal_runtime import modal_app as _modal_app
        except Exception:
            return "skipped_no_volume_handle"
        _resources = getattr(_modal_app, "_MODAL_RESOURCES", None)
        _volume = None
        try:
            _volume = (_resources or {}).get(
                "profile_volume" if volume_kind == "profile" else "runtime_state_volume"
            )
        except Exception:
            _volume = None
        _commit = getattr(_volume, "commit", None)
        if not callable(_commit):
            return "skipped_no_volume_handle"
        _started = time.perf_counter()
        _commit()
        return f"committed_{round((time.perf_counter() - _started) * 1000, 3)}ms"
    except Exception as exc:
        return f"commit_failed:{type(exc).__name__}"


def _stop_and_export_torch(cap: _IdeogramCapture) -> None:
    """Stop the Kineto profiler on the finalize thread; bounded export."""
    _profiler = cap.torch_profiler
    cap.torch_profiler = None
    if _profiler is None or not cap.torch_started:
        return
    _stop_thread = threading.get_ident()
    _same_thread = cap.torch_start_thread is not None and (
        cap.torch_start_thread == _stop_thread
    )
    if not _same_thread:
        _warn(
            cap,
            f"torch_stop_thread_mismatch:start={cap.torch_start_thread}:stop={_stop_thread}",
        )
    _started = time.perf_counter()
    try:
        _profiler.__exit__(None, None, None)
        cap.torch_stop_ms = round((time.perf_counter() - _started) * 1000, 3)
    except Exception as exc:
        cap.torch_skip_reason = f"torch_stop_failed:{type(exc).__name__}"
        _warn(cap, str(cap.torch_skip_reason))
        return
    try:
        _base, _volume_kind = _resolve_export_base()
        cap.torch_export_volume = str(_volume_kind)
        os.makedirs(_base, exist_ok=True)
        _name = f"ideogram_iter{int(cap.iteration)}_{str(cap.request_id or 'norequest')[:24]}_torch_trace.json"
        _path = os.path.join(_base, _name)

        def _export() -> None:
            _profiler.export_chrome_trace(_path)

        _export_started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
            _future = _pool.submit(_export)
            try:
                _future.result(timeout=FINALIZE_TIMEOUT_S)
                cap.torch_export_ms = round((time.perf_counter() - _export_started) * 1000, 3)
                cap.torch_export_path = str(_path)
                cap.torch_export_commit = _commit_export_volume(
                    cap.torch_export_path, cap.torch_export_volume
                )
            except concurrent.futures.TimeoutError:
                cap.torch_export_timeout = True
                _warn(cap, f"torch_export_timeout_s:{FINALIZE_TIMEOUT_S}")
    except Exception as exc:
        _warn(cap, f"torch_export_failed:{type(exc).__name__}")


def finalize_ideogram_profile(cap: Any | None, attention: dict | None = None) -> dict:
    """Stop, export (bounded), and build the artifact (never raises)."""
    try:
        if cap is None or not isinstance(cap, _IdeogramCapture):
            return {
                "schema_version": SCHEMA_VERSION,
                "event": EVENT_NAME,
                "status": "disabled",
                "hook_fired": False,
            }
        if cap.finalized:
            return {"schema_version": SCHEMA_VERSION, "event": EVENT_NAME,
                    "status": "already_finalized", "hook_fired": bool(cap.iteration_open_ns)}
        cap.finalized = True
        if cap.capturing:
            # Unclosed at sampling end (e.g. target was the last step): close
            # here and mark partial; the trailing-update caveat applies.
            end_iteration("sampling_end_unclosed")
        _remove_block_hooks(cap)
        _close_all_ranges(cap, "")
        if cap.backend == BACKEND_TORCH:
            _stop_and_export_torch(cap)
        _attention = attention if isinstance(attention, dict) else {}
        _scope_state = _attention.get("scope_state")
        _selected, _calls = "", 0
        if isinstance(_scope_state, dict):
            try:
                _selected = str(_scope_state.get("selected_callable", "") or "")
            except Exception:
                _selected = ""
            try:
                _calls = int(_scope_state.get("calls", 0) or 0)
            except Exception:
                _calls = 0
        _hook_fired = cap.iteration_open_ns is not None
        _forwards_inside = int(cap.cond_count + cap.uncond_count + cap.batched_count + cap.unknown_count)
        if _hook_fired and _forwards_inside == 0:
            _status = "empty_capture"
        elif _hook_fired:
            _status = "captured"
        else:
            _status = "unresolved"
        _reason = None
        if not _hook_fired:
            if cap.callback_notifications == 0 and int(cap.iteration) > 0:
                _reason = ("no_step_callback_observed:refusing_count_based_fallback; "
                           "target_iteration_unresolved")
            elif cap.callback_notifications == 0:
                _reason = "no_step_callback_and_no_anchor_forward_observed"
            else:
                _reason = "iteration_window_never_opened"
        _artifact = {
            "schema_version": SCHEMA_VERSION,
            "event": EVENT_NAME,
            "status": _status,
            "unresolved_reason": _reason,
            # Effective values (what actually ran, not what was requested).
            "backend_effective": cap.backend,
            "iteration_effective": int(cap.iteration),
            "block_ranges_effective": bool(cap.block_ranges),
            "request_id": str(cap.request_id),
            # Hook verification (do not rely on the SAMPLER_SAMPLE wrapper:
            # Golden direct node invocation can bypass it; this proves the
            # direct-path hooks fired instead).
            "hook_fired": bool(_hook_fired),
            "iteration_hook": "IDEOGRAM_ITERATION",
            "forwards_inside_iteration": _forwards_inside,
            "forward_notifications_total": int(cap.forward_notifications),
            "callback_notifications_total": int(cap.callback_notifications),
            # Branch counts from actual conditioning metadata (never
            # alternating counts; batched/skipped CFG reported honestly).
            "conditional_forwards": int(cap.cond_count),
            "unconditional_forwards": int(cap.uncond_count),
            "batched_forwards": int(cap.batched_count),
            "unknown_forwards": int(cap.unknown_count),
            "observed_kwarg_key_sets": list(cap.kwarg_key_sets),
            "single_forward_note": ("one_forward_in_iteration means skipped/absent "
                                    "CFG or a non-CFG step, not an error"),
            # Guider/sampler + block attribution (one aggregate, not per-call;
            # CFG_GUIDER_SAMPLER marks non-forward work only via exclusive
            # time: parent range minus enclosed forwards, computed offline).
            "guider_range": "CFG_GUIDER_SAMPLER",
            "guider_semantics": "exclusive_time_parent_minus_enclosed_forwards",
            "block_ranges_supported": bool(cap.block_supported),
            "block_ranges_reason": str(cap.block_reason),
            "block_containers": list(cap.block_containers),
            "block_range_count": int(cap.block_range_count),
            "block_range_cap": int(MAX_BLOCK_RANGES),
            "block_ranges_capped": bool(cap.block_capped),
            "attention_requested_backend": str(_attention.get("requested_backend") or ""),
            "attention_selected_callable": _selected,
            "attention_calls": int(_calls),
            "attention_note": ("one aggregate from the shared attention scope "
                               "(golden_generic_loaders); prefer existing "
                               "full_trace_report total_cuda_ms for attribution"),
            # Span completeness + boundaries.
            "anchor_callback": cap.anchor,
            "close_reason": cap.close_reason,
            "span_partial": True,
            "span_partial_reason": ("completed-step callback may precede the final "
                                    "sampler update; ordering not verified from "
                                    "these seams, so the span is partial"),
            "steps_seen": list(cap.steps_seen),
            "unknown_callbacks": int(cap.unknown_callbacks),
            # Torch lifecycle (re-scoped single iteration; shapes/memory/
            # stacks off, same-thread start/stop, exception-safe).
            "torch_profiler_started": bool(cap.torch_started),
            "torch_start_thread": cap.torch_start_thread,
            "torch_skip_reason": cap.torch_skip_reason,
            "torch_stop_ms": cap.torch_stop_ms,
            "torch_export_ms": cap.torch_export_ms,
            "torch_export_path": cap.torch_export_path,
            "torch_export_timeout": bool(cap.torch_export_timeout),
            "torch_export_volume": cap.torch_export_volume,
            "torch_export_commit": cap.torch_export_commit,
            "torch_finalize_timeout_s": float(FINALIZE_TIMEOUT_S),
            # GPU tail + teardown disclosure.
            "gpu_tail_note": ("async GPU tail via the existing safe completion "
                              "boundary only (sampler_call_end/sampling_end); "
                              "no drain added"),
            "teardown_note": "keep COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN=1 for profiling runs",
            "ranges_emitted": list(cap.ranges_emitted),
            "ranges_forced_closed": int(cap.ranges_forced_closed),
            "stack_mismatches": int(cap.stack_mismatches),
            "warnings": list(cap.warnings),
        }
        try:
            _ACTIVE.set(None)
        except Exception:
            pass
        return _artifact
    except Exception as exc:
        try:
            _ACTIVE.set(None)
        except Exception:
            pass
        return {
            "schema_version": SCHEMA_VERSION,
            "event": EVENT_NAME,
            "status": "finalize_failed",
            "hook_fired": False,
            "error": type(exc).__name__,
        }


# ── PromptExecutor-path finalize (SAMPLER_SAMPLE wrapper seam) ────────────────

def finalize_sampler_profile(
    cap: Any | None,
    trace: Any | None,
    *,
    owned: bool,
    attention: dict | None = None,
) -> dict | None:
    """Finalize an owned capture and emit the artifact event (never raises).

    Called from the production SAMPLER_SAMPLE wrapper's ``finally`` so the
    run_plan_stream/PromptExecutor path gets the same bounded stop+export as
    the Golden path.  Single-owner rule: only the seam that armed the
    capture passes ``owned=True`` (it observed no active capture before
    arming); a seam that found an existing capture passes ``owned=False``
    and never finalizes.  Returns the artifact, or None when there is
    nothing to do (flag off / unowned).  The emitted ``ideogram_cuda_profile``
    trace event flows back in the result trace, carrying the Chrome trace
    volume path for off-container retrieval.
    """
    try:
        if cap is None or not owned:
            return None
        artifact = finalize_ideogram_profile(cap, attention=attention)
        try:
            _emit = getattr(trace, "emit", None)
            if callable(_emit):
                _emit(EVENT_NAME, phase="execution", metadata=dict(artifact))
        except Exception:
            pass
        return artifact
    except Exception:
        return None


# ── Post-restore kitchen GPU backend repair: compat wrapper (Part A4) ──
# Canonical implementation relocated to ``gpu_restore`` (single
# implementation).  This entrypoint delegates so existing callers keep
# working; it carries no logic of its own.
_repair_done = False  # legacy guard; the canonical once-guard lives in gpu_restore


def repair_kitchen_gpu_backends_after_restore() -> dict:
    """Compat wrapper: delegate to the canonical ``gpu_restore`` provider.

    Never raises.  Returns the provider result dict (legacy
    ``repaired``/``reason``/``cuda``/``triton`` keys plus ``outcome``).
    """
    try:
        from .gpu_restore import _repair_kitchen_gpu_backends as _canonical
    except Exception:
        try:
            from comfymodal_runtime.gpu_restore import (
                _repair_kitchen_gpu_backends as _canonical,
            )
        except Exception:
            return {
                "provider": "kitchen_gpu_backends",
                "outcome": "error",
                "repaired": False,
                "reason": "gpu_restore_unavailable",
                "cuda": None,
                "triton": None,
            }
    try:
        return _canonical()
    except Exception as exc:  # never raise into restore/execution seams
        return {
            "provider": "kitchen_gpu_backends",
            "outcome": "error",
            "repaired": False,
            "reason": f"wrapper_failed:{type(exc).__name__}",
            "cuda": None,
            "triton": None,
        }


# ── Kitchen INT8 backend proof (measurement-only) ──────────────────────
# Answers "which backend serves int8_linear and why" from inside the serving
# container, where the registry state (CUDA ext import, cublasLt dlopen,
# disabled flags) cannot be observed offline.  Observe-only: tiny synthetic
# tensors, no model weights touched, never raises into sampling.
PROOF_TAG = "[v2.kitchen_backend_proof]"
_proof_emitted = False
_selection_wrap_installed = False
_selection_counts: dict = {}


def _cuda_runtime_identity() -> dict:
    """Read the live CUDA identity without allocating or synchronizing."""
    identity = {
        "visible": False,
        "device_index": None,
        "name": None,
        "compute_capability": None,
    }
    try:
        import torch as _torch
        identity["visible"] = bool(_torch.cuda.is_available())
        if not identity["visible"]:
            return identity
        identity["device_index"] = int(_torch.cuda.current_device())
        try:
            identity["name"] = str(_torch.cuda.get_device_name(identity["device_index"]))
        except Exception:
            pass
        try:
            identity["compute_capability"] = tuple(
                int(value) for value in _torch.cuda.get_device_capability(identity["device_index"])
            )
        except Exception:
            pass
    except Exception:
        pass
    return identity


def emit_kitchen_backend_proof() -> dict:
    """Log once-per-process which kitchen backend serves Ideogram INT8.

    Reports kitchen version, CUDA ext availability (+import error),
    ``HAS_CUBLASLT``, per-backend ``int8_linear`` eligibility for
    Ideogram-shaped kwargs (bf16 act, int8 weight, fp32 scale, convrot),
    and the registry's actual dispatch winner.  Returns the proof dict
    (empty when already emitted or kitchen is unimportable).
    """
    global _proof_emitted
    if _proof_emitted:
        return {}
    _proof_emitted = True
    proof: dict = {}
    proof["cuda_runtime"] = _cuda_runtime_identity()
    proof["cuda_visible"] = proof["cuda_runtime"]["visible"]
    proof["cuda_device_index"] = proof["cuda_runtime"]["device_index"]
    proof["gpu_name"] = proof["cuda_runtime"]["name"]
    proof["actual_compute_capability"] = proof["cuda_runtime"]["compute_capability"]
    try:
        import comfy_kitchen as _ck
    except Exception as exc:
        print(f"{PROOF_TAG} kitchen_import=failed error={type(exc).__name__}", flush=True)
        proof["kitchen_import"] = False
        return proof
    try:
        from importlib import metadata as _md
        proof["kitchen_version"] = _md.version("comfy-kitchen")
    except Exception:
        proof["kitchen_version"] = getattr(_ck, "__version__", "unknown")
    try:
        from comfy_kitchen.backends import cuda as _ck_cuda
        proof["cuda_ext_available"] = bool(getattr(_ck_cuda, "_EXT_AVAILABLE", False))
        proof["cuda_ext_error"] = str(getattr(_ck_cuda, "_EXT_ERROR", None))
        _c = getattr(_ck_cuda, "_C", None)
        proof["has_cublaslt"] = bool(getattr(_c, "HAS_CUBLASLT", False)) if _c is not None else False
    except Exception as exc:
        proof["cuda_ext_available"] = False
        proof["cuda_ext_error"] = f"backend_import_failed:{type(exc).__name__}"
        proof["has_cublaslt"] = False
    backends: dict = {}
    try:
        backends = _ck.registry.list_backends()
    except Exception:
        backends = {}
    for _name in ("cuda", "triton", "eager"):
        _b = backends.get(_name, {}) if isinstance(backends, dict) else {}
        _caps = _b.get("capabilities", []) if isinstance(_b, dict) else []
        proof[f"{_name}"] = {
            "available": bool(_b.get("available", False)) if isinstance(_b, dict) else False,
            "disabled": bool(_b.get("disabled", False)) if isinstance(_b, dict) else False,
            "reason": _b.get("unavailable_reason") if isinstance(_b, dict) else None,
            "int8_linear": "int8_linear" in list(_caps),
        }
    # Synthetic Ideogram-shaped call through the REAL dispatch (tiny tensors,
    # freed immediately; mirrors bf16 act + int8 weight + fp32 scale + convrot).
    proof["synth_dispatched"] = None
    proof["synth_detail"] = {}
    try:
        import torch as _torch
        if _torch.cuda.is_available():
            _dev = _torch.device("cuda", _torch.cuda.current_device())
            _kwargs = {
                "x": _torch.zeros((16, 1024), dtype=_torch.bfloat16, device=_dev),
                "weight": _torch.zeros((2048, 1024), dtype=_torch.int8, device=_dev),
                "weight_scale": _torch.ones((), dtype=_torch.float32, device=_dev),
                "bias": None,
                "out_dtype": _torch.bfloat16,
                "convrot": True,
                "convrot_groupsize": 256,
                "input_act": "swiglu",
                "input_act_weight": None,
                "input_act_eps": 0.0,
                "residual": None,
                "residual_scale": None,
            }
            for _name in ("cuda", "triton", "eager"):
                try:
                    _r = _ck.registry.validate_backend_for_call(_name, "int8_linear", _kwargs)
                    proof["synth_detail"][_name] = (
                        "ok" if _r.success
                        else f"{_r.failed_param}: {_r.failure_reason}"
                    )
                except Exception as exc:
                    proof["synth_detail"][_name] = f"validate_error:{type(exc).__name__}"
            try:
                proof["synth_dispatched"] = _ck.registry.get_capable_backend("int8_linear", _kwargs)
            except Exception as exc:
                proof["synth_dispatched"] = f"none:{type(exc).__name__}"
            del _kwargs
        else:
            proof["synth_dispatched"] = "skipped:no_cuda"
    except Exception as exc:
        proof["synth_dispatched"] = f"skipped:{type(exc).__name__}"
    try:
        _cc = None
        try:
            _cc = _ck.registry._compute_capability  # cached_property, no driver init beyond query
        except Exception:
            _cc = None
        proof["registry_compute_capability"] = _cc
        print(
            f"{PROOF_TAG} kitchen={proof.get('kitchen_version')} "
            f"ext_available={proof.get('cuda_ext_available')} "
            f"ext_error={proof.get('cuda_ext_error')} "
            f"HAS_CUBLASLT={proof.get('has_cublaslt')} "
            f"cuda_visible={proof.get('cuda_visible')} "
            f"gpu_name={proof.get('gpu_name')} "
            f"actual_cc={proof.get('actual_compute_capability')} "
            f"registry_cc={_cc}",
            flush=True,
        )
        for _name in ("cuda", "triton", "eager"):
            _b = proof.get(_name, {})
            print(
                f"{PROOF_TAG} backend={_name} available={_b.get('available')} "
                f"disabled={_b.get('disabled')} reason={_b.get('reason')} "
                f"int8_linear={_b.get('int8_linear')} "
                f"synth={proof.get('synth_detail', {}).get(_name)}",
                flush=True,
            )
        print(f"{PROOF_TAG} dispatch_winner=int8_linear->{proof.get('synth_dispatched')}", flush=True)
    except Exception:
        pass
    return proof


def install_int8_selection_counter() -> bool:
    """Count live ``int8_linear`` registry selections (measurement-only).

    Wraps ``registry.get_capable_backend`` once per process; the wrapper only
    increments a counter for ``func_name == "int8_linear"`` and always calls
    through.  Totals are read via :func:`int8_selection_totals`.
    """
    global _selection_wrap_installed
    if _selection_wrap_installed:
        return True
    try:
        import comfy_kitchen as _ck
        _reg = _ck.registry
        _orig = _reg.get_capable_backend

        def _counting(func_name: str, kwargs: Any = None) -> Any:
            try:
                _backend = _orig(func_name, kwargs)
            except Exception:
                raise
            try:
                if func_name == "int8_linear":
                    _selection_counts[_backend] = _selection_counts.get(_backend, 0) + 1
            except Exception:
                pass
            return _backend

        _reg.get_capable_backend = _counting  # type: ignore[method-assign]
        _selection_wrap_installed = True
        return True
    except Exception:
        return False


def int8_selection_totals() -> dict:
    """Live ``int8_linear`` selection counts + total (measurement-only)."""
    try:
        _counts = dict(_selection_counts)
        _counts["total"] = sum(v for v in _counts.values() if isinstance(v, int))
        return _counts
    except Exception:
        return {}
