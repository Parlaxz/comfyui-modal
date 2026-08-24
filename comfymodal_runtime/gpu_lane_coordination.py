"""Request-scoped exclusion between CLIP and UNET GPU materialization."""

from __future__ import annotations

import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from .env import env_flag


COORDINATION_FLAG = "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION"
SCOPED_CUDA_READINESS_FLAG = "COMFYMODAL_V2_SCOPED_CUDA_READINESS"
CLIP_GPU_CRITICAL_ACTIVE = "CLIP_GPU_CRITICAL_ACTIVE"
_MAX_STATES = 64

# ── D15 additive hook: clip-critical-end callbacks ─────────────────────────
# Registered zero-arg callables are invoked inside end_clip_critical() AFTER
# the CLIP critical state has been released (outer boundary only).  Each
# callback is individually guarded: a raising callback NEVER propagates into
# the critical path.  With nothing registered, behavior is unchanged.
_CLIP_CRITICAL_END_CALLBACKS: list[Any] = []
_CLIP_CRITICAL_END_CALLBACKS_LOCK = threading.Lock()


def register_clip_critical_end_callback(cb: Any) -> None:
    """Register a callback fired when the CLIP GPU-critical section fully
    ends (D15 structural boundary).  Callers must register once (no
    deduplication).  Never raises."""
    if not callable(cb):
        return
    with _CLIP_CRITICAL_END_CALLBACKS_LOCK:
        _CLIP_CRITICAL_END_CALLBACKS.append(cb)


def _fire_clip_critical_end_callbacks() -> None:
    """Invoke registered clip-critical-end callbacks; never raises."""
    try:
        with _CLIP_CRITICAL_END_CALLBACKS_LOCK:
            callbacks = tuple(_CLIP_CRITICAL_END_CALLBACKS)
    except Exception:
        return
    for cb in callbacks:
        try:
            cb()
        except Exception:
            pass


@dataclass
class _RequestState:
    request_id: str
    started_ns: int
    condition: threading.Condition = field(
        default_factory=lambda: threading.Condition(threading.RLock()),
        repr=False,
    )
    clip_owner_tid: int | None = None
    clip_depth: int = 0
    unet_owner_tid: int | None = None
    unet_active: bool = False
    unet_waiters: int = 0
    clip_ready_ns: int | None = None
    unet_ready_ns: int | None = None
    readiness_emitted: bool = False


@dataclass
class _ClipToken:
    state: _RequestState | None
    request_id: str
    trace: Any
    acquired: bool
    outer: bool
    started_ns: int
    cache_state: str
    released: bool = False


@dataclass
class _HydrationToken:
    frame: "_ClipFrame | None"
    clip_token: _ClipToken | None
    request_id: str
    trace: Any
    started_ns: int
    cache_state: str
    standalone: bool
    ended: bool = False


@dataclass
class _ClipFrame:
    request_id: str
    trace: Any
    encode_depth: int = 0
    hydration_depth: int = 0
    hydration_started_ns: int = 0
    hydration_cache_state: str = "cache_miss"
    forward_started_ns: int | None = None
    critical_token: _ClipToken | None = None
    context_token: Any = None


@dataclass
class _EncodeToken:
    frame: _ClipFrame | None
    request_id: str
    trace: Any
    active: bool
    started_ns: int
    ended: bool = False


_STATES: dict[str, _RequestState] = {}
_STATES_LOCK = threading.RLock()
_CLIP_FRAME: ContextVar[_ClipFrame | None] = ContextVar(
    "comfymodal_clip_gpu_critical_frame", default=None
)


def enabled() -> bool:
    return env_flag(COORDINATION_FLAG, default=False)


def scoped_cuda_readiness_enabled() -> bool:
    return env_flag(SCOPED_CUDA_READINESS_FLAG, default=False)


def _torch_api() -> Any:
    import torch

    return torch


def _record_orchestration_copy_event(role: str, trace: Any) -> None:
    try:
        from . import fast_cold_orchestration as _fco

        _fco.record_copy_event(role, trace=trace)
    except Exception:
        pass


def _record_orchestration_copy_wait(role: str, trace: Any) -> None:
    try:
        from . import fast_cold_orchestration as _fco

        _fco.record_copy_event_wait(role, trace=trace)
    except Exception:
        pass


def _record_orchestration_unet_interval(
    start_ns: int, end_ns: int, trace: Any, identity: str
) -> None:
    try:
        from . import fast_cold_orchestration as _fco

        _fco.record_unet_gpu_interval(
            start_ns / 1_000_000_000.0,
            end_ns / 1_000_000_000.0,
            identity,
            trace=trace,
        )
    except Exception:
        pass


def record_device_wide_sync(role: str, trace: Any = None) -> None:
    try:
        from . import fast_cold_orchestration as _fco

        _fco.record_device_wide_sync(role, trace=trace)
    except Exception:
        pass


def record_copy_event(role: str, trace: Any = None, *, stream: Any = None) -> Any:
    if not scoped_cuda_readiness_enabled():
        return None
    try:
        torch = _torch_api()
        if not torch.cuda.is_available():
            return None
        producer = stream if stream is not None else torch.cuda.current_stream()
        try:
            event = torch.cuda.Event(enable_timing=False)
        except TypeError:
            event = torch.cuda.Event()
        event.record(producer)
    except Exception:
        return None
    _record_orchestration_copy_event(role, trace)
    _emit(
        trace,
        "cuda_copy_event_recorded",
        _request_id("", trace),
        role=str(role),
        observation="host_event_record_call",
    )
    return event


def wait_copy_event(role: str, event: Any, trace: Any = None, *, stream: Any = None) -> bool:
    if not scoped_cuda_readiness_enabled() or event is None:
        return False
    try:
        torch = _torch_api()
        consumer = stream if stream is not None else torch.cuda.current_stream()
        consumer.wait_event(event)
    except Exception:
        return False
    _record_orchestration_copy_wait(role, trace)
    _emit(
        trace,
        "cuda_copy_event_waited",
        _request_id("", trace),
        role=str(role),
        observation="host_wait_event_enqueue",
    )
    return True


def synchronize_copy_event(role: str, event: Any, trace: Any = None) -> bool:
    if not scoped_cuda_readiness_enabled() or event is None:
        return False
    try:
        event.synchronize()
    except Exception:
        return False
    _record_orchestration_copy_wait(role, trace)
    return True


def _trace_from_runtime() -> Any:
    try:
        from . import model_preload

        lane = model_preload._ACTIVE_LANE_TRACE.get()
        if lane is not None:
            trace = getattr(lane, "_trace", None)
            if trace is not None:
                return trace
        return model_preload._ACTIVE_REQUEST_TRACE.get()
    except Exception:
        return None


def _resolve_trace(trace: Any = None) -> Any:
    return _trace_from_runtime() or trace


def _request_id(request_id: str = "", trace: Any = None) -> str:
    if request_id:
        return str(request_id)
    trace = _resolve_trace(trace)
    return str(getattr(trace, "request_id", "") or "")


def _emit(trace: Any, name: str, request_id: str, **metadata: Any) -> None:
    trace = _resolve_trace(trace)
    if trace is None:
        return
    payload = dict(metadata)
    payload.setdefault("request_id", request_id)
    payload.setdefault("coordination", CLIP_GPU_CRITICAL_ACTIVE)
    try:
        trace.emit(name, phase="execution", metadata=payload)
    except Exception:
        pass


def _state(request_id: str, *, create: bool = True) -> _RequestState | None:
    if not request_id:
        return None
    with _STATES_LOCK:
        current = _STATES.get(request_id)
        if current is None and create:
            current = _RequestState(request_id=request_id, started_ns=time.monotonic_ns())
            _STATES[request_id] = current
        if len(_STATES) > _MAX_STATES:
            for old_id, old in list(_STATES.items()):
                if old_id == request_id:
                    continue
                with old.condition:
                    if (
                        old.clip_owner_tid is None
                        and not old.unet_active
                        and old.unet_waiters == 0
                    ):
                        _STATES.pop(old_id, None)
                        break
        return current


def start_request(request_id: str, trace: Any = None) -> None:
    if not enabled():
        return
    _state(_request_id(request_id, trace))


def _readiness(state: _RequestState, trace: Any, *, reason: str) -> None:
    with state.condition:
        if state.readiness_emitted:
            return
        clip_ready = state.clip_ready_ns
        unet_ready = state.unet_ready_ns
        if clip_ready is None or unet_ready is None:
            return
        state.readiness_emitted = True
    gate_ns = max(clip_ready, unet_ready)
    if clip_ready > unet_ready:
        gated_by = "CLIP"
    elif unet_ready > clip_ready:
        gated_by = "UNET"
    else:
        gated_by = "TIE"
    _emit(
        trace,
        "model_readiness_gate",
        state.request_id,
        reason=reason,
        CLIP_READY_AT=clip_ready,
        UNET_READY_AT=unet_ready,
        MODEL_READINESS_GATE_AT=gate_ns,
        SAMPLER_GATED_BY=gated_by,
        READINESS_GATED_BY=gated_by,
        MODEL_READINESS_GATE_MS=round(
            max(0, gate_ns - state.started_ns) / 1_000_000, 3
        ),
        EXPOSED_MODEL_READINESS_MS=round(
            max(0, gate_ns - state.started_ns) / 1_000_000, 3
        ),
    )


def record_clip_ready(
    request_id: str, trace: Any = None, *, cache_state: str = "cache_miss"
) -> None:
    if not enabled():
        return
    trace = _resolve_trace(trace)
    rid = _request_id(request_id, trace)
    state = _state(rid)
    if state is None:
        return
    ready_ns = time.monotonic_ns()
    with state.condition:
        state.clip_ready_ns = ready_ns
    _readiness(state, trace, reason=f"clip_ready:{cache_state}")


def record_unet_ready(request_id: str, trace: Any = None, *, reason: str = "ready") -> None:
    if not enabled():
        return
    trace = _resolve_trace(trace)
    rid = _request_id(request_id, trace)
    state = _state(rid)
    if state is None:
        return
    ready_ns = time.monotonic_ns()
    with state.condition:
        state.unet_ready_ns = ready_ns
    _emit(trace, "unet_ready", rid, reason=reason, ready_at_ns=ready_ns)
    _readiness(state, trace, reason=reason)


def begin_clip_critical(
    request_id: str = "", trace: Any = None, *, reason: str = "clip_encode", cache_state: str = "cache_miss"
) -> _ClipToken:
    trace = _resolve_trace(trace)
    rid = _request_id(request_id, trace)
    if not enabled() or not rid:
        return _ClipToken(None, rid, trace, False, False, 0, cache_state)
    state = _state(rid)
    assert state is not None
    tid = threading.get_ident()
    wait_start = time.monotonic_ns()
    with state.condition:
        while state.unet_active and state.unet_owner_tid != tid:
            state.condition.wait()
        outer = state.clip_owner_tid is None
        if outer:
            state.clip_owner_tid = tid
        state.clip_depth += 1
    acquired_ns = time.monotonic_ns()
    if outer:
        _emit(
            trace,
            "clip_gpu_critical_enter",
            rid,
            reason=reason,
            wait_ms=round((acquired_ns - wait_start) / 1_000_000, 3),
            cache_state=cache_state,
            state=CLIP_GPU_CRITICAL_ACTIVE,
        )
        try:
            from .fast_cold_orchestration import notify_clip_critical

            notify_clip_critical(rid, trace, True)
        except Exception:
            pass
    return _ClipToken(state, rid, trace, True, outer, acquired_ns, cache_state)


def end_clip_critical(token: _ClipToken, *, success: bool = True, reason: str = "clip_encode") -> None:
    if token.released or not token.acquired or token.state is None:
        token.released = True
        return
    state = token.state
    outer = False
    with state.condition:
        if state.clip_depth > 0:
            state.clip_depth -= 1
        if state.clip_depth == 0:
            state.clip_owner_tid = None
            outer = True
            state.condition.notify_all()
    token.released = True
    if outer:
        ended_ns = time.monotonic_ns()
        _emit(
            token.trace,
            "clip_gpu_critical_exit",
            token.request_id,
            reason=reason,
            cache_state=token.cache_state,
            success=bool(success),
            active_ms=round((ended_ns - token.started_ns) / 1_000_000, 3),
            state=CLIP_GPU_CRITICAL_ACTIVE,
        )
        try:
            from .fast_cold_orchestration import notify_clip_critical

            notify_clip_critical(token.request_id, token.trace, False)
        except Exception:
            pass
        if success:
            record_clip_ready(
                token.request_id, token.trace, cache_state=token.cache_state
            )
        # ── D15 additive hook: fire registered clip-critical-end callbacks
        # after state release + readiness recording.  Guarded per callback;
        # never raises into the critical path.
        _fire_clip_critical_end_callbacks()


def begin_clip_encode(
    request_id: str = "", trace: Any = None, *, cache_state: str = "cache_miss"
) -> _EncodeToken:
    trace = _resolve_trace(trace)
    rid = _request_id(request_id, trace)
    if not enabled() or not rid:
        return _EncodeToken(None, rid, trace, False, 0)
    frame = _CLIP_FRAME.get()
    if frame is None or frame.request_id != rid:
        clip_token = begin_clip_critical(rid, trace, cache_state=cache_state)
        frame = _ClipFrame(
            request_id=rid,
            trace=trace,
            critical_token=clip_token,
            context_token=None,
        )
        frame.context_token = _CLIP_FRAME.set(frame)
    else:
        begin_clip_critical(rid, trace, cache_state=cache_state)
    frame.encode_depth += 1
    return _EncodeToken(frame, rid, trace, True, time.monotonic_ns())


def end_clip_encode(token: _EncodeToken, *, success: bool = True) -> None:
    if token.ended or not token.active or token.frame is None:
        token.ended = True
        return
    frame = token.frame
    frame.encode_depth = max(0, frame.encode_depth - 1)
    if frame.encode_depth == 0:
        end_ns = time.monotonic_ns()
        _emit(
            frame.trace,
            "clip_forward_end",
            frame.request_id,
            success=bool(success),
            forward_started=frame.forward_started_ns is not None,
            forward_ms=(
                round((end_ns - frame.forward_started_ns) / 1_000_000, 3)
                if frame.forward_started_ns is not None
                else 0.0
            ),
            cache_state="cache_miss",
        )
        if frame.critical_token is not None:
            end_clip_critical(frame.critical_token, success=success)
        _CLIP_FRAME.reset(frame.context_token)
    else:
        if frame.critical_token is not None:
            end_clip_critical(
                _ClipToken(
                    frame.critical_token.state,
                    frame.request_id,
                    frame.trace,
                    frame.critical_token.acquired,
                    False,
                    token.started_ns,
                    "cache_miss",
                ),
                success=success,
            )
    token.ended = True


def begin_clip_hydration(
    request_id: str = "", trace: Any = None, *, cache_state: str = "cache_miss"
) -> _HydrationToken:
    trace = _resolve_trace(trace)
    rid = _request_id(request_id, trace)
    if not enabled() or not rid:
        return _HydrationToken(None, None, rid, trace, 0, cache_state, False)
    frame = _CLIP_FRAME.get()
    if frame is not None and frame.request_id == rid:
        frame.hydration_depth += 1
        if frame.hydration_depth == 1:
            frame.hydration_started_ns = time.monotonic_ns()
            frame.hydration_cache_state = cache_state
            _emit(
                trace,
                "clip_hydration_gpu_start",
                rid,
                reason="clip_load_model",
                cache_state=cache_state,
            )
        return _HydrationToken(
            frame, None, rid, trace, frame.hydration_started_ns, cache_state, False
        )
    clip_token = begin_clip_critical(
        rid, trace, reason="clip_hydration", cache_state=cache_state
    )
    started_ns = time.monotonic_ns()
    _emit(
        trace,
        "clip_hydration_gpu_start",
        rid,
        reason="clip_load_model",
        cache_state=cache_state,
    )
    return _HydrationToken(
        None, clip_token, rid, trace, started_ns, cache_state, True
    )


def end_clip_hydration(token: _HydrationToken, *, success: bool = True) -> None:
    if token.ended:
        return
    token.ended = True
    if token.frame is not None:
        frame = token.frame
        frame.hydration_depth = max(0, frame.hydration_depth - 1)
        if frame.hydration_depth == 0:
            end_ns = time.monotonic_ns()
            _emit(
                token.trace,
                "clip_hydration_gpu_end",
                token.request_id,
                reason="clip_load_model",
                success=bool(success),
                cache_state=token.cache_state,
                duration_ms=round((end_ns - token.started_ns) / 1_000_000, 3),
            )
            if success and frame.encode_depth > 0 and frame.forward_started_ns is None:
                frame.forward_started_ns = end_ns
                _emit(
                    token.trace,
                    "clip_forward_start",
                    token.request_id,
                    reason="after_clip_hydration",
                    cache_state=token.cache_state,
                )
        return
    if token.standalone:
        end_ns = time.monotonic_ns()
        _emit(
            token.trace,
            "clip_hydration_gpu_end",
            token.request_id,
            reason="clip_load_model",
            success=bool(success),
            cache_state=token.cache_state,
            duration_ms=round((end_ns - token.started_ns) / 1_000_000, 3),
        )
        if token.clip_token is not None:
            end_clip_critical(token.clip_token, success=success, reason="clip_hydration")


def bind_wait_start(trace: Any = None, *, reason: str = "clip_bind_completion") -> int:
    started_ns = time.monotonic_ns()
    if enabled():
        resolved = _resolve_trace(trace)
        rid = _request_id("", resolved)
        _emit(resolved, "clip_bind_wait_start", rid, reason=reason)
    return started_ns


def bind_wait_end(
    trace: Any = None,
    started_ns: int = 0,
    *,
    success: bool = True,
    reason: str = "clip_bind_completion",
) -> None:
    if not enabled():
        return
    resolved = _resolve_trace(trace)
    rid = _request_id("", resolved)
    _emit(
        resolved,
        "clip_bind_wait_end",
        rid,
        reason=reason,
        success=bool(success),
        wait_ms=round(max(0, time.monotonic_ns() - started_ns) / 1_000_000, 3),
    )


@dataclass
class _UnetToken:
    state: _RequestState | None
    request_id: str
    trace: Any
    acquired: bool
    outer: bool
    started_ns: int
    released: bool = False


def begin_unet_gpu_phase(
    request_id: str = "", trace: Any = None, *, reason: str = "clip_gpu_critical_active"
) -> _UnetToken:
    trace = _resolve_trace(trace)
    rid = _request_id(request_id, trace)
    if not enabled() or not rid:
        return _UnetToken(None, rid, trace, False, False, 0)
    state = _state(rid)
    assert state is not None
    tid = threading.get_ident()
    wait_start = time.monotonic_ns()
    _emit(
        trace,
        "unet_gpu_gate_wait_start",
        rid,
        reason=reason,
        cache_state="not_applicable",
    )
    with state.condition:
        if state.clip_owner_tid == tid:
            raise RuntimeError("unet_gpu_during_clip_critical")
        while (
            (state.clip_owner_tid is not None and state.clip_owner_tid != tid)
            or (state.unet_active and state.unet_owner_tid != tid)
        ):
            state.unet_waiters += 1
            try:
                state.condition.wait()
            finally:
                state.unet_waiters = max(0, state.unet_waiters - 1)
        outer = not state.unet_active
        if outer:
            state.unet_owner_tid = tid
            state.unet_active = True
    acquired_ns = time.monotonic_ns()
    _emit(
        trace,
        "unet_gpu_gate_wait_end",
        rid,
        reason=reason,
        wait_ms=round((acquired_ns - wait_start) / 1_000_000, 3),
        cache_state="not_applicable",
    )
    return _UnetToken(state, rid, trace, True, outer, acquired_ns)


def end_unet_gpu_phase(token: _UnetToken, *, success: bool = True) -> None:
    if token.released or not token.acquired or token.state is None:
        token.released = True
        return
    state = token.state
    if token.outer:
        with state.condition:
            state.unet_active = False
            state.unet_owner_tid = None
            state.condition.notify_all()
    token.released = True


def unet_transfer_start(token: _UnetToken, *, reason: str = "direct_gpu_fastsafetensors") -> int:
    started_ns = time.monotonic_ns()
    _emit(
        token.trace,
        "unet_gpu_transfer_start",
        token.request_id,
        reason=reason,
        cache_state="not_applicable",
    )
    return started_ns


def unet_transfer_end(
    token: _UnetToken,
    started_ns: int,
    *,
    success: bool = True,
    reason: str = "direct_gpu_fastsafetensors",
) -> None:
    _emit(
        token.trace,
        "unet_gpu_transfer_end",
        token.request_id,
        reason=reason,
        success=bool(success),
        cache_state="not_applicable",
        transfer_ms=round(max(0, time.monotonic_ns() - started_ns) / 1_000_000, 3),
    )
    end_ns = time.monotonic_ns()
    identity = "staged" if reason == "staged_transport" else "fastsafetensors"
    _record_orchestration_unet_interval(
        started_ns, end_ns, token.trace, identity
    )


def request_end(request_id: str, trace: Any = None) -> None:
    if not enabled():
        return
    rid = _request_id(request_id, trace)
    if not rid:
        return
    with _STATES_LOCK:
        state = _STATES.pop(rid, None)
    if state is not None:
        with state.condition:
            state.condition.notify_all()


def reset_for_tests() -> None:
    with _STATES_LOCK:
        _STATES.clear()
    _CLIP_FRAME.set(None)


def active_request_ids() -> tuple[str, ...]:
    with _STATES_LOCK:
        return tuple(_STATES)


def clip_critical_active(request_id: str = "", trace: Any = None) -> bool:
    """Non-blocking: is the CLIP critical (GPU) section active for this
    request?

    Used by the proven-ready GPU-load fast return so it can NEVER skip a
    UNET GPU phase while CLIP owns the critical GPU section (D15 strict: no
    UNET GPU activation/mutation/H2D may occur while CLIP owns the critical
    phase).  A fast return is a pure bookkeeping skip with no GPU work, so it
    is safe only when no CLIP critical section is active.  Fail-closed: any
    error -> True (conservative: do not fast-return)."""
    try:
        trace = _resolve_trace(trace)
        rid = _request_id(request_id, trace)
        if not enabled() or not rid:
            return False
        state = _state(rid)
        if state is None:
            return False
        with state.condition:
            return state.clip_owner_tid is not None
    except Exception:
        return True
