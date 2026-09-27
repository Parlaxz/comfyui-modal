"""E31 CLIP forward forensics: synchronized GPU timing + cast classification.

Batch E31 ownership: CLIP-forward variance and correct FP32 cast-once
mechanics/measurement.  This module is E31-owned and self-contained; it adds
NO hooks to E29-owned files (``modal_app.py``, ``runtime_bootstrap.py``,
``runtime_executor.py``, ``gantt_telemetry.py``, ``v2_waterfall.py``, the
benchmark harness) and does NOT edit E30's CLIP source-loader files.

Motivation (why E28's ``cuda_event_wall_ms = 0.0`` is not proof):

* E28's forward-cast counter wrapped ``comfy.ops.cast_bias_weight`` but
  parsed the arguments as ``(weight, bias, dtype)`` while the real signature
  is ``(s, input=None, dtype=None, ...)`` — so ``source_dtypes`` came back
  all ``unknown`` and the shapes as ``()``.  The cast count and destination
  bytes therefore could not be trusted, and the GPU time of those
  conversions was never actually measured.
* The old per-call event measurement recorded start and end events back-to-
  back on the default stream *after* the cast had already been enqueued and
  computed ``elapsed_time`` immediately — events with no work between them
  and no synchronize → 0.0 ms regardless of the real GPU conversion time.
* Python ``.to()``/``cast_to`` enqueue async GPU work; host submission wall
  is not GPU conversion wall.  The correct measurement is event pairs on the
  REAL stream, with ONE synchronize after the whole forward, then read.

Design (all default OFF):

* ``COMFYMODAL_V2_E31_FORENSICS=1`` — synchronized whole-forward CUDA timing
  + corrected cast classification + per-cast structured evidence.
* ``COMFYMODAL_V2_E31_FORWARD_PROFILE=1`` — opt-in torch.profiler pass over
  one forward (explicit, one-shot, never in production).
* ``COMFYMODAL_V2_CLIP_FP32_CAST_ONCE=1`` — E28's compute-ready FP32
  cast-once (retained; see ``clip_fp32_cast_once.py``).

With the gate OFF every function here is a no-op, no wrapper is installed,
and no CUDA work is performed at import time.

Measurement protocol (Phase 2):

* ``ForwardTimer`` — one start event + one end event recorded on
  ``torch.cuda.current_stream()`` bracketing the whole forward; a single
  ``end_event.synchronize()`` after forward; then
  ``start_event.elapsed_time(end_event)``.  Reports host wall, GPU elapsed,
  and host-only residual (wall - gpu, clamped >= 0).  The GPU value is the
  raw CUDA event interval; no per-request calibration bracket or extra
  synchronization is performed.
* Per-cast diagnosis records event pairs WITHOUT synchronizing per call and
  WITHOUT reading elapsed_time at call time (a pre-sync read is the E28
  ``0.0 ms`` bug).  The pairs are queued and resolved once, after the single
  post-forward sync, by :func:`resolve_pending_cast_events` (called from
  :meth:`ForwardTimer.end`).  Values are only reported for pairs recorded on
  the stream that is current at resolution time.

Cast classification (Phase 3):

For every call through the wrapped cast entry points
(``comfy.ops.cast_bias_weight`` and ``comfy.model_management.cast_to`` /
``cast_to_device``) we classify the outcome:

* REAL_CONVERSION          — dtype changed AND a new tensor/storage was
                            produced (or an in-place dtype mutation).
* REAL_COPY_NO_DTYPE_CHANGE— new storage, same dtype (device or copy move).
* VIEW_ALIAS               — result aliases the source (same storage,
                            different tensor object, e.g. non-copy same
                            dtype/device).
* NOOP_SAME_TENSOR         — result is the identical tensor object.
* NOOP_SAME_STORAGE        — different object, same storage, no dtype change.
* OTHER                    — anything unclassifiable (non-tensor, exception).

Aggregates: real conversions count + real bytes converted (union of
destination bytes for REAL_CONVERSION), same-storage noops, new allocations,
and the synchronized GPU conversion milliseconds (sum of per-call event
deltas after the single forward sync).  Structured per-call evidence is kept
in a bounded ring (``COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT``, default 1024) and
never dumped to logs by default.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any, Callable, Optional

from .env import env_flag

_E31_FORENSICS_FLAG = "COMFYMODAL_V2_E31_FORENSICS"
_E31_PROFILE_FLAG = "COMFYMODAL_V2_E31_FORWARD_PROFILE"
_E31_CAST_SAMPLE_LIMIT = "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT"

# E29 ledger integration surface: the canonical request-scoped event store
# (COMFYMODAL_V2_CRITICAL_PATH_LEDGER, default ON).  E31 events are emitted
# ONLY when the E31 forensics gate is also on, so a non-E31 run never pays
# for them; when both gates are on, the E31 events appear on the canonical
# axis with the request identity block (no competing timeline).
_LEDGER_EVENT_NAMES = (
    "clip_forward_start",
    "clip_forward_end",
    "clip_gpu_event_start",
    "clip_gpu_event_end",
    "clip_forward_gpu_ms",
    "clip_cast_once_start",
    "clip_cast_once_end",
    "clip_cast_once_gpu_ms",
    "clip_forward_cast_summary",
    "clip_profiler_start",
    "clip_profiler_end",
)

_ENABLED: bool = env_flag(_E31_FORENSICS_FLAG, default=False)
_PROFILE_ENABLED: bool = env_flag(_E31_PROFILE_FLAG, default=False)


def sync_e31_gates() -> dict[str, bool]:
    """Refresh E31 gates from the effective runtime environment.

    E31 is imported during image/bootstrap setup, while a request can apply
    its effective environment profile later.  Do not let the import-time
    value decide whether the real-forward wrappers are installed.  This
    helper is deliberately defensive: a malformed environment must leave the
    existing state intact and must never break request startup.
    """
    global _ENABLED, _PROFILE_ENABLED
    try:
        enabled = env_flag(_E31_FORENSICS_FLAG, default=False)
        profile_enabled = env_flag(_E31_PROFILE_FLAG, default=False)
    except Exception:
        return {"forensics": bool(_ENABLED), "forward_profile": bool(_PROFILE_ENABLED)}
    _ENABLED = bool(enabled)
    _PROFILE_ENABLED = bool(profile_enabled)
    return {"forensics": _ENABLED, "forward_profile": _PROFILE_ENABLED}

_SENTINEL_CAST = "_comfymodal_e31_cast_wrapper"
_SENTINEL_PROFILE = "_comfymodal_e31_profile_wrapper"

# Classification result strings (Phase 3 taxonomy).
REAL_CONVERSION = "REAL_CONVERSION"
REAL_COPY_NO_DTYPE_CHANGE = "REAL_COPY_NO_DTYPE_CHANGE"
VIEW_ALIAS = "VIEW_ALIAS"
NOOP_SAME_TENSOR = "NOOP_SAME_TENSOR"
NOOP_SAME_STORAGE = "NOOP_SAME_STORAGE"
OTHER = "OTHER"


# ── stream- and event helpers (never touch CUDA at import time) ──────────

def _current_stream() -> Any:
    """Return the current CUDA stream object (or None when unavailable)."""
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        return torch.cuda.current_stream()
    except Exception:
        return None


def _make_event() -> Any:
    """Create a CUDA timing event (or a no-op stub when CUDA is unavailable)."""
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.Event(enable_timing=True)
    except Exception:
        pass

    class _NoopEvent:
        def record(self, stream: Any = None) -> None:
            pass

        def synchronize(self) -> None:
            pass

        def elapsed_time(self, _other: Any) -> float:
            return 0.0

    return _NoopEvent()


def _ledger_enabled() -> bool:
    """Whether the E29 canonical ledger store is live (never raises)."""
    try:
        from . import critical_path_ledger as _cpl

        return bool(getattr(_cpl, "_ENABLED", False))
    except Exception:
        return False


def emit_ledger_event(name: str, *, mono_ns: int | None = None, **metadata: Any) -> None:
    """Emit one E31 event on the E29 canonical ledger axis.

    No-op when the E31 forensics gate is off or the ledger is unavailable.
    The event name must be in :data:`_LEDGER_EVENT_NAMES` (the E29-integration
    contract) — anything else is dropped so a typo cannot silently create a
    competing timeline.  Never raises.
    """
    if not _ENABLED:
        return
    if name not in _LEDGER_EVENT_NAMES:
        return
    try:
        from . import critical_path_ledger as _cpl

        _cpl.record_event(
            name,
            mono_ns=mono_ns,
            metadata=dict(metadata),
        )
    except Exception:
        pass


def _module_path_prefix(module: Any, max_len: int = 96) -> str:
    """Best-effort module path prefix (``module_path`` attr or class name)."""
    try:
        path = getattr(module, "module_path", "") or ""
        if path:
            return str(path)[:max_len]
    except Exception:
        pass
    try:
        return type(module).__name__[:max_len]
    except Exception:
        return "?"


class ForwardTimer:
    """Synchronized whole-forward CUDA timing (host wall + GPU elapsed).

    Usage::

        timer = ForwardTimer()
        timer.start()          # records start event on the real stream
        forward(...)           # the actual forward, unchanged
        timer.end()            # records end event, ONE synchronize, reads
                               # elapsed_time — never raises

    ``end()`` reports ``host_wall_ms``, ``gpu_elapsed_ms``,
    ``host_only_residual_ms`` (wall - gpu, clamped >= 0), and a ``None``
    ``event_overhead_ms`` compatibility field.  With CUDA unavailable the GPU
    fields are ``None`` — never a fabricated 0.0.
    """

    def __init__(self) -> None:
        self._start_event: Any = None
        self._end_event: Any = None
        self._start_wall: float | None = None
        self._end_wall: float | None = None
        self._start_mono_ns: int | None = None
        self._end_mono_ns: int | None = None
        self._forward_observed = False
        self._forward_cast_calls: dict[str, int] = {}
        self._result: dict[str, Any] | None = None

    def mark_forward_observed(self) -> None:
        """Mark that the real CLIP forward has been entered.

        ``ForwardTimer`` is also useful in offline tests, where it may be
        used without a forward call.  Keeping this bit explicit prevents a
        timer-only record from being mistaken for real-forward evidence.
        """
        self._forward_observed = True

    def start(self) -> None:
        sync_e31_gates()
        self._result = None
        self._forward_observed = False
        _begin_forward_cast_scope()
        stream = _current_stream()
        self._start_wall = time.perf_counter()
        self._start_mono_ns = time.monotonic_ns()
        emit_ledger_event("clip_forward_start", mono_ns=self._start_mono_ns)
        emit_ledger_event("clip_gpu_event_start", mono_ns=self._start_mono_ns)
        if stream is None:
            self._start_event = None
            self._end_event = None
            return
        try:
            self._start_event = _make_event()
            self._end_event = _make_event()
            self._start_event.record(stream)
        except Exception:
            self._start_event = None
            self._end_event = None

    def end(self) -> dict[str, Any]:
        if self._result is not None:
            return dict(self._result)
        stream = _current_stream()
        self._end_wall = time.perf_counter()
        self._end_mono_ns = time.monotonic_ns()
        emit_ledger_event("clip_forward_end", mono_ns=self._end_mono_ns)
        emit_ledger_event("clip_gpu_event_end", mono_ns=self._end_mono_ns)
        host_wall_ms = (
            (self._end_wall - self._start_wall) * 1000.0
            if self._start_wall is not None
            else None
        )
        if stream is None or self._start_event is None or self._end_event is None:
            # CPU/fake-stream paths still need the authoritative forward
            # summary.  The old early return made the summary event depend on
            # CUDA being available and silently dropped zero-conversion proof.
            resolve_pending_cast_events()
            emit_cast_summary_ledger(
                mono_ns=self._end_mono_ns,
                summary=_forward_cast_scope_summary(),
                forward_observed=self._forward_observed,
            )
            record = {
                "host_wall_ms": None if host_wall_ms is None else round(host_wall_ms, 3),
                "gpu_elapsed_ms": None,
                "host_only_residual_ms": None,
                "event_overhead_ms": None,
                "cuda_available": False,
            }
            return self._finish_record(record)
        try:
            self._end_event.record(stream)
            # The single synchronization — this is the entire sync budget of
            # the measurement; it also makes every recorded cast event pair
            # readable.
            self._end_event.synchronize()
            gpu_ms = float(self._start_event.elapsed_time(self._end_event))
            # Now that the forward's work has completed on the stream, read
            # every queued per-cast event pair (deferred, never per-call).
            resolve_pending_cast_events()
        except Exception:
            gpu_ms = None
        # Emit even when CUDA timing itself failed.  The forward conversion
        # account is independent evidence and must not disappear with a
        # timing/event error.
        emit_cast_summary_ledger(
            mono_ns=self._end_mono_ns,
            summary=_forward_cast_scope_summary(),
            forward_observed=self._forward_observed,
        )
        residual = None
        if host_wall_ms is not None and gpu_ms is not None:
            residual = max(0.0, host_wall_ms - gpu_ms)
        if gpu_ms is not None:
            emit_ledger_event(
                "clip_forward_gpu_ms",
                mono_ns=self._end_mono_ns,
                gpu_ms=round(gpu_ms, 3),
            )
        record = {
            "host_wall_ms": None if host_wall_ms is None else round(host_wall_ms, 3),
            "gpu_elapsed_ms": None if gpu_ms is None else round(gpu_ms, 3),
            "host_only_residual_ms": None if residual is None else round(residual, 3),
            "event_overhead_ms": None,
            "cuda_available": stream is not None,
        }
        return self._finish_record(record)

    def _finish_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Add the real-forward evidence envelope to a timer result."""
        scoped_summary = _forward_cast_scope_summary()
        scoped_summary["forward_evidence"] = bool(self._forward_observed)
        self._forward_cast_calls = _end_forward_cast_scope()
        record.update({
            "forward_observed": bool(self._forward_observed),
            "forward_actually_observed": bool(self._forward_observed),
            "clip_forward_start": self._start_mono_ns,
            "clip_forward_end": self._end_mono_ns,
            "cast_summary": cast_forensics_summary(),
            # This is deliberately scoped to this timer's real outer forward,
            # rather than inferred from the process-global cast totals.  A
            # zero-conversion success is only meaningful when this evidence is
            # positive.
            "canonical_cast_calls": dict(self._forward_cast_calls),
            "canonical_cast_call_count": sum(self._forward_cast_calls.values()),
            # This is the forward-scoped account.  It intentionally does not
            # reuse hydration/bind conversion counters or process-global cast
            # totals, so a zero-conversion forward remains distinguishable
            # from a forward that was never observed.
            "forward_cast_summary": scoped_summary,
            "forward_conversion_count": int(scoped_summary.get("real_conversions", 0) or 0),
        })
        record["timing"] = {
            key: record.get(key)
            for key in (
                "host_wall_ms", "gpu_elapsed_ms", "host_only_residual_ms",
                "cuda_available",
            )
        }
        record_forward_evidence(record)
        self._result = dict(record)
        return dict(self._result)


# ── cast classification (Phase 3) ─────────────────────────────────────────

def _tensor_facts(t: Any) -> dict[str, Any]:
    """Collect classification facts about a tensor-like object (never raises)."""
    if t is None:
        return {"is_tensor": False}
    try:
        import torch

        if not isinstance(t, torch.Tensor):
            return {"is_tensor": False, "type": type(t).__name__}
    except Exception:
        return {"is_tensor": False, "type": type(t).__name__}
    try:
        return {
            "is_tensor": True,
            "dtype": str(t.dtype),
            "device": str(t.device),
            "data_ptr": int(t.data_ptr()) if not t.is_meta else None,
            "numel": int(t.numel()),
            "element_size": int(t.element_size()),
            "bytes": int(t.numel() * t.element_size()),
            "contiguous": bool(t.is_contiguous()),
            "storage_data_ptr": (
                int(t.untyped_storage().data_ptr()) if not t.is_meta else None
            ),
        }
    except Exception:
        return {"is_tensor": True, "error": "facts_failed"}


def classify_cast(source: Any, result: Any) -> tuple[str, dict[str, Any]]:
    """Classify one cast call's outcome.

    Returns ``(classification, evidence)`` where *evidence* carries the
    source/result facts plus the classification reason.  Never raises.
    """
    src = _tensor_facts(source)
    dst = _tensor_facts(result)
    if not src.get("is_tensor") or not dst.get("is_tensor"):
        return OTHER, {"reason": "non_tensor", "source": src, "dest": dst}
    if source is result:
        return NOOP_SAME_TENSOR, {"reason": "identical_object", "source": src, "dest": dst}
    if src.get("storage_data_ptr") == dst.get("storage_data_ptr"):
        if src.get("data_ptr") == dst.get("data_ptr"):
            return VIEW_ALIAS, {"reason": "same_storage_same_ptr_alias", "source": src, "dest": dst}
        return NOOP_SAME_STORAGE, {"reason": "same_storage", "source": src, "dest": dst}
    if src.get("dtype") != dst.get("dtype"):
        return REAL_CONVERSION, {"reason": "dtype_changed", "source": src, "dest": dst}
    return REAL_COPY_NO_DTYPE_CHANGE, {"reason": "new_storage_same_dtype", "source": src, "dest": dst}


# ── corrected cast wrapper (the E28 ``unknown``-dtype bug fix) ────────────

_CAST_LOCK = threading.Lock()
# A real Comfy cast surface is layered: ``cast_bias_weight`` may call
# ``cast_to`` for each parameter and ``cast_to_device`` may delegate to
# ``cast_to``.  Keep this guard per thread so the outermost wrapped call owns
# the conversion record and event interval.  This is deliberately local to
# these wrappers; torch itself is never patched.
_CAST_NESTING = threading.local()
_FORWARD_CAST_SCOPE = threading.local()
_cast_account: dict[str, Any] = {
    "weight_casts": 0,
    "bias_casts": 0,
    "other_casts": 0,
    "classifications": {},
    "real_conversions": 0,
    "real_conversion_bytes": 0,
    "same_storage_noops": 0,
    "new_allocations": 0,
    "host_wall_ms": 0.0,
    "gpu_event_ms": 0.0,
    "source_dtypes": {},
    "dest_dtypes": {},
    "first_weight_shapes": [],
    "first_bias_shapes": [],
    "module_paths": {},
}
_cast_samples: deque[dict[str, Any]] = deque(maxlen=1024)
_installation_evidence: list[dict[str, Any]] = []
_last_forward_evidence: dict[str, Any] = {}
# Per-call CUDA event pairs are NOT read at call time (that would be the
# E28 bug: reading elapsed_time before the work completed).  They are queued
# here and resolved after the ONE post-forward synchronize in
# ForwardTimer.end().  `_pending_ev_ts` records the stream the pair was
# recorded on (torch.cuda.current_stream() at call time), so the deferred
# read can re-check the current stream before trusting the value.
_cast_pending_events: deque[tuple[Any, Any, Any]] = deque()
_CAST_DEFER_MAX = 8192


def _empty_forward_cast_summary() -> dict[str, Any]:
    """Return a JSON-safe account for one outer real forward."""
    return {
        "weight_casts": 0,
        "bias_casts": 0,
        "other_casts": 0,
        "classifications": {},
        "real_conversions": 0,
        "real_conversion_bytes": 0,
        "same_storage_noops": 0,
        "new_allocations": 0,
        "host_wall_ms": 0.0,
        "gpu_event_ms": 0.0,
        "forward_evidence": True,
    }


def _begin_forward_cast_scope() -> None:
    """Start cast-call evidence for one real outer CLIP forward."""
    _FORWARD_CAST_SCOPE.calls = {}
    _FORWARD_CAST_SCOPE.summary = _empty_forward_cast_summary()


def _note_forward_cast_call(kind: str) -> None:
    """Record a call through a canonical wrapped cast surface, if active."""
    calls = getattr(_FORWARD_CAST_SCOPE, "calls", None)
    if not isinstance(calls, dict):
        return
    calls[kind] = int(calls.get(kind, 0) or 0) + 1


def _end_forward_cast_scope() -> dict[str, int]:
    calls = getattr(_FORWARD_CAST_SCOPE, "calls", None)
    try:
        result = {str(key): int(value) for key, value in (calls or {}).items()}
    except Exception:
        result = {}
    try:
        del _FORWARD_CAST_SCOPE.calls
    except AttributeError:
        pass
    try:
        del _FORWARD_CAST_SCOPE.summary
    except AttributeError:
        pass
    return result


def _forward_cast_scope_summary() -> dict[str, Any]:
    """Return the current forward-only cast account without ending the scope."""
    summary = getattr(_FORWARD_CAST_SCOPE, "summary", None)
    if not isinstance(summary, dict):
        result = _empty_forward_cast_summary()
        result["forward_evidence"] = False
        return result
    with _CAST_LOCK:
        return {
            "weight_casts": int(summary.get("weight_casts", 0) or 0),
            "bias_casts": int(summary.get("bias_casts", 0) or 0),
            "other_casts": int(summary.get("other_casts", 0) or 0),
            "classifications": dict(summary.get("classifications", {})),
            "real_conversions": int(summary.get("real_conversions", 0) or 0),
            "real_conversion_bytes": int(summary.get("real_conversion_bytes", 0) or 0),
            "same_storage_noops": int(summary.get("same_storage_noops", 0) or 0),
            "new_allocations": int(summary.get("new_allocations", 0) or 0),
            "host_wall_ms": round(float(summary.get("host_wall_ms", 0.0) or 0.0), 3),
            "gpu_event_ms": round(float(summary.get("gpu_event_ms", 0.0) or 0.0), 3),
            "forward_evidence": bool(summary.get("forward_evidence", True)),
        }


def _note_forward_cast_record(
    *, kind: str, role: str | None, classification: str,
    host_wall_ms: float, dest_bytes: int,
) -> None:
    """Add one cast record to the active outer-forward account only."""
    summary = getattr(_FORWARD_CAST_SCOPE, "summary", None)
    if not isinstance(summary, dict):
        return
    if role == "bias":
        summary["bias_casts"] += 1
    elif kind == "cast_bias_weight":
        summary["weight_casts"] += 1
    else:
        summary["other_casts"] += 1
    classifications = summary["classifications"]
    classifications[classification] = classifications.get(classification, 0) + 1
    summary["host_wall_ms"] += float(host_wall_ms or 0.0)
    if classification == REAL_CONVERSION:
        summary["real_conversions"] += 1
        summary["real_conversion_bytes"] += int(dest_bytes or 0)
    elif classification == NOOP_SAME_STORAGE:
        summary["same_storage_noops"] += 1
    elif classification == REAL_COPY_NO_DTYPE_CHANGE:
        summary["new_allocations"] += 1


def _pending_event_capacity() -> int:
    try:
        return max(64, min(int(os.environ.get(_E31_CAST_SAMPLE_LIMIT, "1024")) * 8, _CAST_DEFER_MAX))
    except Exception:
        return _CAST_DEFER_MAX


def _enter_cast_scope() -> tuple[int, bool]:
    """Enter one wrapped cast scope and return ``(depth, is_outermost)``."""
    depth = int(getattr(_CAST_NESTING, "depth", 0) or 0)
    _CAST_NESTING.depth = depth + 1
    return depth, depth == 0


def _leave_cast_scope(depth: int) -> None:
    """Restore the caller's cast nesting depth, never leaking thread state."""
    if depth:
        _CAST_NESTING.depth = depth
    else:
        try:
            del _CAST_NESTING.depth
        except AttributeError:
            pass


def _queue_cast_events(ev_start: Any, ev_end: Any, ev_stream: Any) -> None:
    """Queue a per-cast event pair for the deferred post-forward read."""
    if ev_start is None or ev_end is None:
        return
    with _CAST_LOCK:
        if len(_cast_pending_events) >= _pending_event_capacity():
            return
        _cast_pending_events.append((ev_start, ev_end, ev_stream))


def resolve_pending_cast_events() -> None:
    """Read every queued per-cast event pair (call ONCE after the single
    post-forward synchronize).  Each pair's stream is re-checked against the
    current stream; a mismatch means the events could not have completed on
    this stream and the value is discarded (never fabricated).  Aggregates
    into the account; the queue is drained.  Never raises.
    """
    if not _ENABLED:
        return
    pairs: list[tuple[Any, Any, Any]] = []
    with _CAST_LOCK:
        pairs = list(_cast_pending_events)
        _cast_pending_events.clear()
    if not pairs:
        return
    try:
        import torch as _t

        cur_stream = _t.cuda.current_stream() if _t.cuda.is_available() else None
    except Exception:
        cur_stream = None
    total_ms = 0.0
    for ev_start, ev_end, ev_stream in pairs:
        try:
            if cur_stream is None or ev_stream is None or cur_stream != ev_stream:
                continue
            total_ms += float(ev_start.elapsed_time(ev_end))
        except Exception:
            continue
    if total_ms:
        with _CAST_LOCK:
            _cast_account["gpu_event_ms"] += total_ms


def _module_label(module: Any) -> str:
    """Short stable label for a cast source module (``<path>.<attr>``)."""
    try:
        prefix = _module_path_prefix(module)
        attr = ""
        for name in ("weight", "bias"):
            if getattr(module, name, None) is not None:
                attr = f".{name}"
                break
        return f"{prefix}{attr}"
    except Exception:
        return "?"


def _cast_sample_limit() -> int:
    try:
        return max(1, int(os.environ.get(_E31_CAST_SAMPLE_LIMIT, "1024")))
    except Exception:
        return 1024


def _install_cast_wrapper(owner: Any, attr: str, kind: str) -> str:
    """Wrap one comfy cast entry point with correct arg parsing + event pairs."""
    if not _ENABLED:
        return "gated_off"
    try:
        original = getattr(owner, attr, None)
        if not callable(original):
            return "unavailable"
        if getattr(original, _SENTINEL_CAST, False):
            return "already"

        @functools_wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _ENABLED:
                return original(*args, **kwargs)
            # Count entry through the live canonical surface before invoking
            # the original.  This proves instrumentation was actually used by
            # the same real forward; aggregate conversion totals alone cannot.
            _note_forward_cast_call(kind)
            start_ns = time.monotonic_ns()
            start_wall = time.perf_counter()
            # Parse the REAL signatures:
            #   cast_bias_weight(s, input=None, dtype=None, device=None, ...)
            #   cast_to(weight, dtype=None, device=None, ...)
            #   cast_to_device(tensor, device, dtype, ...)
            s = args[0] if args else None
            is_module = hasattr(s, "weight") or hasattr(s, "bias") or hasattr(s, "comfy_cast_weights")
            if kind == "cast_bias_weight" and is_module:
                # First arg is the module; the cast source is its weight.
                source = getattr(s, "weight", None)
                bias_source = getattr(s, "bias", None)
                dest_dtype = None
                if len(args) >= 3:
                    dest_dtype = args[2]
                elif "dtype" in kwargs:
                    dest_dtype = kwargs["dtype"]
            else:
                source = args[0] if args else None
                dest_dtype = None
                if kind == "cast_to_device" and len(args) >= 3:
                    dest_dtype = args[2]
                elif kind != "cast_to_device" and len(args) >= 2:
                    dest_dtype = args[1]
                elif "dtype" in kwargs:
                    dest_dtype = kwargs["dtype"]
            # Enter only after argument inspection, so even an unusual
            # user-supplied object that raises from ``hasattr``/``getattr``
            # cannot strand the thread-local nesting state.
            call_depth, outermost = _enter_cast_scope()
            ev_start = None
            ev_end = None
            ev_stream = None
            if outermost:
                try:
                    import torch as _t

                    if _t.cuda.is_available():
                        ev_stream = _t.cuda.current_stream()
                        ev_start = _t.cuda.Event(enable_timing=True)
                        ev_end = _t.cuda.Event(enable_timing=True)
                        ev_start.record(ev_stream)
                except Exception:
                    ev_start = ev_end = ev_stream = None
            result: Any = None
            error: BaseException | None = None
            try:
                result = original(*args, **kwargs)
            except BaseException as _exc:
                error = _exc
                raise
            finally:
                # The guarded scope is the original call itself.  Release it
                # before any bookkeeping so an unexpected bookkeeping error
                # cannot poison a later independent cast on this thread.
                _leave_cast_scope(call_depth)
                end_ns = time.monotonic_ns()
                end_wall = time.perf_counter()
                if outermost and ev_end is not None and ev_stream is not None:
                    try:
                        import torch as _t2

                        ev_end.record(ev_stream)
                        # NO per-call synchronize and NO elapsed_time read
                        # here: the pair is queued and resolved after the
                        # single post-forward sync in
                        # ForwardTimer.end()/resolve_pending_cast_events().
                        _queue_cast_events(ev_start, ev_end, ev_stream)
                    except Exception:
                        pass
                # NEVER return from this finally (that would swallow a
                # propagating exception); the recording below only runs when
                # the original call succeeded.
                if outermost and error is None:
                    # cast_bias_weight returns (weight, bias) OR, with
                    # offloadable=True, (weight, bias, offload_stream).
                    # Record each returned tensor separately so weight vs
                    # bias accounting matches the real conversion count —
                    # the third element is never a bias.
                    if kind == "cast_bias_weight" and isinstance(result, tuple):
                        _w_res = result[0]
                        _b_res = result[1] if len(result) >= 2 else None
                        _w_src = getattr(s, "weight", None) if is_module else None
                        _b_src = getattr(s, "bias", None) if is_module else None
                        _record_cast(
                            kind="cast_bias_weight",
                            source=_w_src,
                            result=_w_res,
                            dest_dtype=dest_dtype,
                            host_wall_ms=(end_wall - start_wall) * 1000.0,
                            gpu_event_ms=None,
                            wall_ms=(end_ns - start_ns) / 1_000_000,
                            role="weight",
                            module=s if is_module else None,
                        )
                        if _b_src is not None and _b_res is not None:
                            _record_cast(
                                kind="cast_bias_weight",
                                source=_b_src,
                                result=_b_res,
                                dest_dtype=dest_dtype,
                                host_wall_ms=0.0,
                                gpu_event_ms=None,
                                wall_ms=0.0,
                                role="bias",
                                module=s if is_module else None,
                            )
                    else:
                        _record_cast(
                            kind=kind,
                            source=source,
                            result=result,
                            dest_dtype=dest_dtype,
                            host_wall_ms=(end_wall - start_wall) * 1000.0,
                            gpu_event_ms=None,
                            wall_ms=(end_ns - start_ns) / 1_000_000,
                            role=None,
                            module=s if is_module else None,
                        )
            return result

        setattr(wrapper, _SENTINEL_CAST, True)
        setattr(owner, attr, wrapper)
        return "installed"
    except Exception as exc:
        return f"error:{type(exc).__name__}:{str(exc)[:120]}"


def torch_Tensor() -> type:
    """Return ``torch.Tensor`` (imported lazily; never at module import)."""
    import torch

    return torch.Tensor


def _record_cast(
    *,
    kind: str,
    source: Any,
    result: Any,
    dest_dtype: Any,
    host_wall_ms: float,
    gpu_event_ms: float | None,
    wall_ms: float,
    role: str | None = None,
    module: Any = None,
) -> None:
    """Aggregate one cast call into the account + bounded sample ring."""
    classification, evidence = classify_cast(source, result)
    is_bias = role == "bias"
    src_dtype = str(getattr(source, "dtype", "unknown"))
    dst_facts = _tensor_facts(result[0] if isinstance(result, tuple) else result)
    dst_dtype = dst_facts.get("dtype", "unknown")
    label = _module_label(module) if module is not None else None
    with _CAST_LOCK:
        if label:
            _cast_account["module_paths"][label] = (
                _cast_account["module_paths"].get(label, 0) + 1
            )
        if is_bias:
            _cast_account["bias_casts"] += 1
            if len(_cast_account["first_bias_shapes"]) < 8:
                try:
                    _cast_account["first_bias_shapes"].append(str(getattr(source, "shape", ())))
                except Exception:
                    pass
        elif kind == "cast_bias_weight":
            _cast_account["weight_casts"] += 1
            if len(_cast_account["first_weight_shapes"]) < 8:
                try:
                    _cast_account["first_weight_shapes"].append(str(getattr(source, "shape", ())))
                except Exception:
                    pass
        else:
            _cast_account["other_casts"] += 1
        _cast_account["classifications"][classification] = (
            _cast_account["classifications"].get(classification, 0) + 1
        )
        _cast_account["source_dtypes"][src_dtype] = (
            _cast_account["source_dtypes"].get(src_dtype, 0) + 1
        )
        _cast_account["dest_dtypes"][dst_dtype] = (
            _cast_account["dest_dtypes"].get(dst_dtype, 0) + 1
        )
        _cast_account["host_wall_ms"] += host_wall_ms
        if classification == REAL_CONVERSION:
            _cast_account["real_conversions"] += 1
            _bytes = dst_facts.get("bytes") or 0
            _cast_account["real_conversion_bytes"] += _bytes
        elif classification == NOOP_SAME_STORAGE:
            _cast_account["same_storage_noops"] += 1
        elif classification in (REAL_COPY_NO_DTYPE_CHANGE,):
            _cast_account["new_allocations"] += 1
        sample = {
            "kind": kind,
            "classification": classification,
            "reason": evidence.get("reason"),
            "source_dtype": src_dtype,
            "dest_dtype": dst_dtype,
            "source_bytes": evidence.get("source", {}).get("bytes"),
            "dest_bytes": evidence.get("dest", {}).get("bytes"),
            "host_wall_ms": round(host_wall_ms, 3),
            "gpu_event_ms": None,
            "module": label,
        }
        _cast_samples.append(sample)
        # Keep a second account scoped to the active real outer forward.  The
        # process-global account above may also contain bind/hydration calls;
        # it is not sufficient evidence for a particular forward.
        _note_forward_cast_record(
            kind=kind,
            role=role,
            classification=classification,
            host_wall_ms=host_wall_ms,
            dest_bytes=int(dst_facts.get("bytes") or 0),
        )


def _callable_identity(fn: Any) -> int:
    """Stable-for-this-process identity of the callable, not its display name."""
    # Keep an existing non-E31 instrumentation wrapper in the call chain.
    # Callable identity means the live callable object actually stored on the
    # surface; unwrapping ``functools.wraps`` here could replace another
    # subsystem's wrapper with a raw function and silently lose its evidence.
    base = fn
    # Accessing an instance method creates a fresh bound-method object on
    # every attribute read.  Its function+self pair is the callable identity;
    # using id(bound_method) would miss aliases on lightweight test doubles
    # and on modules that publish bound helper methods.
    function = getattr(base, "__func__", None)
    owner = getattr(base, "__self__", None)
    if function is not None and owner is not None:
        return hash((id(owner), id(function)))
    return id(base)


def _surface_label(owner: Any, fallback: str) -> str:
    try:
        name = getattr(owner, "__name__", None)
        if name:
            return str(name)
    except Exception:
        pass
    return fallback


def _installation_record(
    *,
    module: str,
    attr: str,
    original: Any,
    wrapped: bool,
    duplicate_alias: bool,
    status: str,
) -> dict[str, Any]:
    identity = _callable_identity(original) if callable(original) else None
    return {
        "module": module,
        "attribute": attr,
        "callable_identity": identity,
        # Short alias retained for consumers that used the early E31 draft.
        "callable_id": identity,
        "wrapped": bool(wrapped),
        "duplicate_alias": bool(duplicate_alias),
        "status": status,
    }


def install_cast_forensics(comfy_ops: Any, model_management: Any) -> dict[str, Any]:
    """Audit and wrap every known CLIP cast surface, default OFF → no-op.

    The real CLIP path uses the three named entry points below.  Both live
    modules are audited (rather than stopping at the first match), because a
    deployment can expose aliases on both surfaces.  Aliases are installed as
    references to the one E31 wrapper for their underlying callable, so one
    call cannot be counted twice.  No torch operation is ever monkey-patched.
    """
    # This is also a direct entry point in tests and in late-loaded Comfy
    # modules, so do not rely solely on modal_app's lifecycle sync.
    sync_e31_gates()
    result: dict[str, Any] = {"enabled": _ENABLED, "installed": {}}
    if not _ENABLED:
        return result

    targets = (
        ("cast_bias_weight", "cast_bias_weight"),
        ("cast_to", "cast_to"),
        ("cast_to_device", "cast_to_device"),
    )
    surfaces = (
        ("comfy.ops", comfy_ops),
        ("comfy.model_management", model_management),
    )
    # Maps underlying callable identity -> the E31 wrapper installed for it.
    # This is deliberately local to one audit: an already-sentinel-wrapped
    # callable is detected below and remains idempotent across audits.
    wrappers_by_identity: dict[int, Any] = {}
    evidence: list[dict[str, Any]] = []
    for surface_name, owner in surfaces:
        if owner is None:
            continue
        module_name = _surface_label(owner, surface_name)
        # Include public aliases published by the same surface.  Looking only
        # at the canonical names would leave e.g. ``ops.cast_alias`` pointing
        # at the uninstrumented function.  The alias is relevant precisely
        # because it has the same callable identity as a canonical target.
        surface_targets = list(targets)
        identity_kinds: dict[int, str] = {}
        for attr, kind in targets:
            candidate = getattr(owner, attr, None)
            if callable(candidate):
                identity_kinds.setdefault(_callable_identity(candidate), kind)
        try:
            for alias, candidate in vars(owner).items():
                if alias in {name for name, _kind in targets} or not callable(candidate):
                    continue
                alias_kind = identity_kinds.get(_callable_identity(candidate))
                if alias_kind is not None:
                    surface_targets.append((str(alias), alias_kind))
        except Exception:
            pass
        for attr, kind in surface_targets:
            original = getattr(owner, attr, None)
            if not callable(original):
                result["installed"].setdefault(f"{module_name}.{attr}", "unavailable")
                result["installed"].setdefault(attr, "unavailable")
                evidence.append(_installation_record(
                    module=module_name,
                    attr=attr,
                    original=None,
                    wrapped=False,
                    duplicate_alias=False,
                    status="unavailable",
                ))
                continue
            identity = _callable_identity(original)
            duplicate_alias = identity in wrappers_by_identity
            status: str
            if duplicate_alias:
                wrapper = wrappers_by_identity[identity]
                try:
                    # Point every alias at the same wrapper.  This avoids
                    # nested E31 wrappers while preserving the owner's API.
                    setattr(owner, attr, wrapper)
                    status = "alias"
                except Exception as exc:
                    status = f"error:{type(exc).__name__}:{str(exc)[:120]}"
            else:
                status = _install_cast_wrapper(owner, attr, kind)
                wrapper = getattr(owner, attr, None)
                if callable(wrapper) and getattr(wrapper, _SENTINEL_CAST, False):
                    wrappers_by_identity[identity] = wrapper
                else:
                    wrapper = None
            wrapped = callable(getattr(owner, attr, None)) and bool(
                getattr(getattr(owner, attr, None), _SENTINEL_CAST, False)
            )
            evidence.append(_installation_record(
                module=module_name,
                attr=attr,
                original=original,
                wrapped=wrapped,
                duplicate_alias=duplicate_alias,
                status=status,
            ))
            result["installed"][f"{module_name}.{attr}"] = status
            # Keep the original short-key API for callers that only need the
            # canonical target status; detailed per-surface truth is in the
            # evidence list above.
            if result["installed"].get(attr) == "unavailable":
                result["installed"][attr] = status
            else:
                result["installed"].setdefault(attr, status)

    with _CAST_LOCK:
        _installation_evidence[:] = evidence
    result["installation_evidence"] = [dict(entry) for entry in evidence]
    return result


def cast_installation_evidence() -> list[dict[str, Any]]:
    """Return the most recent cast-surface audit evidence."""
    with _CAST_LOCK:
        return [dict(entry) for entry in _installation_evidence]


def reset_cast_installation_evidence() -> None:
    """Clear installation evidence without unpatching live callables."""
    with _CAST_LOCK:
        _installation_evidence.clear()


def cast_forensics_summary() -> dict[str, Any]:
    """JSON-safe copy of the E31 cast account (never raises)."""
    with _CAST_LOCK:
        return {
            "weight_casts": int(_cast_account.get("weight_casts", 0)),
            "bias_casts": int(_cast_account.get("bias_casts", 0)),
            "other_casts": int(_cast_account.get("other_casts", 0)),
            "classifications": dict(_cast_account.get("classifications", {})),
            "real_conversions": int(_cast_account.get("real_conversions", 0)),
            "real_conversion_bytes": int(_cast_account.get("real_conversion_bytes", 0)),
            "same_storage_noops": int(_cast_account.get("same_storage_noops", 0)),
            "new_allocations": int(_cast_account.get("new_allocations", 0)),
            "host_wall_ms": round(float(_cast_account.get("host_wall_ms", 0.0)), 3),
            "gpu_event_ms": round(float(_cast_account.get("gpu_event_ms", 0.0)), 3),
            "source_dtypes": dict(_cast_account.get("source_dtypes", {})),
            "dest_dtypes": dict(_cast_account.get("dest_dtypes", {})),
            "first_weight_shapes": list(_cast_account.get("first_weight_shapes", [])),
            "first_bias_shapes": list(_cast_account.get("first_bias_shapes", [])),
            "module_paths": dict(_cast_account.get("module_paths", {})),
            "installation_evidence": [dict(entry) for entry in _installation_evidence],
            "pending_event_pairs": len(_cast_pending_events),
        }


def emit_cast_summary_ledger(
    mono_ns: int | None = None,
    *,
    summary: dict[str, Any] | None = None,
    forward_observed: bool | None = None,
) -> None:
    """Push the current cast summary onto the canonical ledger axis.

    No-op when the E31 gate is off or the ledger is unavailable.  Emits the
    ``clip_forward_cast_summary`` event carrying the aggregated counts and
    classification totals (per-call evidence stays in the bounded ring, never
    on the ledger).
    """
    if not _ENABLED:
        return
    try:
        aggregate = cast_forensics_summary()
        scoped = dict(summary) if isinstance(summary, dict) else aggregate
        emit_ledger_event(
            "clip_forward_cast_summary",
            mono_ns=mono_ns,
            weight_casts=scoped.get("weight_casts", 0),
            bias_casts=scoped.get("bias_casts", 0),
            other_casts=scoped.get("other_casts", 0),
            real_conversions=scoped.get("real_conversions", 0),
            real_conversion_bytes=scoped.get("real_conversion_bytes", 0),
            same_storage_noops=scoped.get("same_storage_noops", 0),
            new_allocations=scoped.get("new_allocations", 0),
            host_wall_ms=scoped.get("host_wall_ms", 0.0),
            gpu_event_ms=scoped.get("gpu_event_ms", 0.0),
            source_dtypes=aggregate.get("source_dtypes", {}),
            dest_dtypes=aggregate.get("dest_dtypes", {}),
            classifications=scoped.get("classifications", {}),
            forward_evidence=(
                bool(forward_observed)
                if forward_observed is not None
                else bool(scoped.get("forward_evidence", False))
            ),
            forward_conversion_count=scoped.get("real_conversions", 0),
        )
    except Exception:
        pass


def cast_sample_evidence(limit: int = 64) -> list[dict[str, Any]]:
    """Return the most recent bounded per-call cast evidence (never raises)."""
    with _CAST_LOCK:
        return list(_cast_samples)[-max(1, min(limit, 4096)):]


def record_forward_evidence(evidence: dict[str, Any]) -> None:
    """Publish the latest evidence for the real CLIP-forward boundary."""
    if not isinstance(evidence, dict):
        return
    with _CAST_LOCK:
        _last_forward_evidence.clear()
        _last_forward_evidence.update(dict(evidence))


def forward_forensics_evidence() -> dict[str, Any]:
    """Return the latest real-forward evidence envelope, or an honest default."""
    with _CAST_LOCK:
        if _last_forward_evidence:
            return dict(_last_forward_evidence)
    return {
        "forward_observed": False,
        "forward_actually_observed": False,
        "clip_forward_start": None,
        "clip_forward_end": None,
        "host_wall_ms": None,
        "gpu_elapsed_ms": None,
        "host_only_residual_ms": None,
        "timing": {
            "host_wall_ms": None,
            "gpu_elapsed_ms": None,
            "host_only_residual_ms": None,
            "cuda_available": False,
        },
        "cast_summary": cast_forensics_summary(),
        "forward_cast_summary": {
            **_empty_forward_cast_summary(),
            "forward_evidence": False,
        },
        "forward_conversion_count": 0,
    }


# Descriptive aliases for integrations that use the E31 terminology directly.
real_forward_evidence = forward_forensics_evidence
get_forward_evidence = forward_forensics_evidence
forward_evidence_summary = forward_forensics_evidence


def reset_cast_forensics() -> None:
    with _CAST_LOCK:
        _cast_account.update({
            "weight_casts": 0,
            "bias_casts": 0,
            "other_casts": 0,
            "classifications": {},
            "real_conversions": 0,
            "real_conversion_bytes": 0,
            "same_storage_noops": 0,
            "new_allocations": 0,
            "host_wall_ms": 0.0,
            "gpu_event_ms": 0.0,
            "source_dtypes": {},
            "dest_dtypes": {},
            "first_weight_shapes": [],
            "first_bias_shapes": [],
            "module_paths": {},
        })
        _cast_samples.clear()
        _cast_pending_events.clear()
        _last_forward_evidence.clear()


def e31_enabled() -> bool:
    sync_e31_gates()
    return _ENABLED


def e31_profile_enabled() -> bool:
    sync_e31_gates()
    return _PROFILE_ENABLED


# ── Phase 5: opt-in one-shot forward profiler (explicit, default OFF) ─────

class ForwardProfiler:
    """Bracket one forward with torch.profiler (one-shot, explicit).

    Usage::

        with ForwardProfiler() as prof:
            forward(...)
        record = prof.record()   # JSON-safe aggregate + sorted op table

    Default OFF; never enabled in production.  When CUDA/GPU is available the
    profiler uses ``activities=[CPU, CUDA]`` and exports the key table.
    """

    def __init__(self, enabled: bool | None = None) -> None:
        if enabled is None:
            sync_e31_gates()
        self._enabled = _PROFILE_ENABLED if enabled is None else enabled
        self._prof: Any = None
        self._record: dict[str, Any] = {"enabled": self._enabled}

    def __enter__(self) -> "ForwardProfiler":
        if not self._enabled:
            return self
        try:
            import torch

            activities = [torch.profiler.ProfilerActivity.CPU]
            if torch.cuda.is_available():
                activities.append(torch.profiler.ProfilerActivity.CUDA)
            self._prof = torch.profiler.profile(
                activities=activities,
                record_shapes=False,
                with_stack=False,
            )
            self._prof.__enter__()
            emit_ledger_event("clip_profiler_start", mono_ns=time.monotonic_ns())
        except Exception as exc:
            self._record["error"] = f"{type(exc).__name__}:{str(exc)[:160]}"
            self._prof = None
        return self

    def __exit__(self, *exc_info: Any) -> None:
        if self._prof is not None:
            try:
                self._prof.__exit__(*exc_info)
            except Exception:
                pass

    def record(self) -> dict[str, Any]:
        if self._prof is None:
            self._record["status"] = "not_run" if self._record.get("error") is None else "error"
            return self._record
        try:
            import torch

            self._record["status"] = "ok"
            table = self._prof.key_averages().table(sort_by="cuda_time_total", row_limit=40)
            self._record["key_table"] = str(table)
            totals = self._prof.key_averages()
            cpu_total = 0.0
            cuda_total = 0.0
            ops: list[dict[str, Any]] = []
            for row in totals:
                cpu_ms = float(getattr(row, "self_cpu_time_total", 0) or 0) / 1000.0
                cuda_ms = float(getattr(row, "cuda_time_total", 0) or 0) / 1000.0
                ops.append({
                    "key": str(row.key),
                    "count": int(row.count),
                    "cpu_ms": round(cpu_ms, 3),
                    "cuda_ms": round(cuda_ms, 3),
                })
                cpu_total += float(getattr(row, "self_cpu_time_total", 0) or 0)
                cuda_total += float(getattr(row, "cuda_time_total", 0) or 0)
            ops.sort(key=lambda r: -(r["cuda_ms"] + r["cpu_ms"]))
            self._record["op_count"] = len(ops)
            self._record["cpu_self_total_ms"] = round(cpu_total / 1000.0, 3)
            self._record["cuda_self_total_ms"] = round(cuda_total / 1000.0, 3)
            self._record["ops_top"] = ops[:40]
            emit_ledger_event(
                "clip_profiler_end",
                mono_ns=time.monotonic_ns(),
                status=self._record["status"],
                op_count=self._record["op_count"],
                cpu_self_total_ms=self._record["cpu_self_total_ms"],
                cuda_self_total_ms=self._record["cuda_self_total_ms"],
            )
        except Exception as exc:
            self._record["status"] = "error"
            self._record["error"] = f"{type(exc).__name__}:{str(exc)[:160]}"
        return self._record


def functools_wraps(original: Callable[..., Any]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    try:
        import functools

        return functools.wraps(original)
    except Exception:
        def _identity(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return _identity
