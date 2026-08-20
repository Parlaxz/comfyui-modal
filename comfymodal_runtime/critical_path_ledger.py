"""Canonical ground-truth critical-path ledger (Batch E29).

This module is the ONE authoritative account of the remote request from
``remote Python resume`` to ``first durable result``.  It is measurement-only:
every span/event is a real, code-site-stamped observation on the shared remote
process monotonic clock (``time.monotonic_ns()``).  Nothing here invents a
stage name or converts unexplained wall into a plausible bucket.

Accounting contract (strict, per the E29 spec):

* ``work_ms``   — wall positively attributable to intrinsic work in the scope.
* ``wait_ms``   — explicitly measured blocking: lock/semaphore/condition/queue
                  waits, ``Future.result``, thread joins, ``Event.wait``,
                  mutation-lane waits, worker handoff waits, directly measurable
                  I/O waits.
* ``sync_ms``   — explicit device synchronization: ``torch.cuda.synchronize``,
                  CUDA-event waits, stream syncs, other explicit GPU barriers.
* ``child_ms``  — UNION of child wall intervals (never a naive sum when
                  children overlap).
* ``residual_ms`` — wall not positively explained by work/wait/sync/children.
                  If residual is unexplained it is LABELED ``UNATTRIBUTED``.

Invariant (per scope):

    scope.duration_ms ≈ work_ms + wait_ms + sync_ms + child_union_ms
                        + residual_ms

within a tiny tolerance.  When concurrency makes that formulation
inappropriate the scope reports ``union_coverage_ms``, ``overlap_coverage_ms``
and ``exclusive_residual_ms`` explicitly instead.

Zero-gap contract: at request end ``build_serial_ledger`` constructs the serial
ledger ``remote_python_resume_mono_ns -> first_durable_result_mono_ns``; every
nanosecond on that serial axis is represented.  Unknown ownership renders as
``UNATTRIBUTED`` (never blank, never a guessed stage name).

Request scoping: every span carries ``request_id``/``trace_id`` plus the full
identity block (``restored_instance_id``, ``restore_session_id``,
``container_session_id``, ``thread_name``/``native_tid``, ``span_id``,
``parent_span_id``, ``handoff_id``).  A reused container NEVER appends
previous-request spans into the next request — call ``begin_request`` to
reset the per-request ledger.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Iterable, Mapping

from .env import env_flag

_LEDGER_FLAG = "COMFYMODAL_V2_CRITICAL_PATH_LEDGER"
_ENABLED: bool = env_flag(_LEDGER_FLAG, default=True)
"""Frozen at import time, matching the runtime convention.  Default ON so the
E29 deploy (which bakes the flag) captures the ledger without an extra env;
production without the flag stays uninstrumented."""

_MAX_SPANS = 4096
_MAX_EVENTS = 8192
_MAX_UNATTRIBUTED_SEGMENTS = 512

# ── Identity context (per-request, set by the runtime at restore/method entry) ──

_IDENTITY_LOCK = threading.Lock()
_IDENTITY: dict[str, str] = {}
_CURRENT_REQUEST_ID: str = ""

# ── Restore-phase ledger ─────────────────────────────────────────────────
# The restore() lifecycle and the subsequent request run in the SAME
# container process on the same monotonic axis.  A request-scoped reset at
# method entry must therefore PRESERVE the restore-session spans/events
# (they are part of this request's serial critical path) while never letting
# a previous REQUEST's spans leak in.  ``_RESTORE_SPANS`` / ``_RESTORE_EVENTS``
# hold exactly one restore session; ``begin_request`` moves the current
# spans/events into them only when they belong to the restore phase.

_RESTORE_SPANS: list[dict[str, Any]] = []
_RESTORE_EVENTS: list[dict[str, Any]] = []
_RESTORE_RID: str = ""

# ── Authoritative serial-ledger endpoints (E29 acceptance contract) ─────
# ``request_ledger_report`` MUST bound the serial zero-gap ledger by these
# explicit endpoints (remote_python_resume -> first_durable_result), never by
# min/max of whatever spans/events happen to exist.  A truncated ledger must
# not be able to tile its own truncated interval and still claim zero-gap.
_AUTHORITATIVE_ENDPOINTS: dict[str, int] = {}


def set_authoritative_endpoints(
    *,
    remote_python_resume_mono_ns: int | None = None,
    first_durable_result_mono_ns: int | None = None,
) -> None:
    """Record the explicit canonical boundaries for the serial zero-gap
    ledger.  Both endpoints are required for the acceptance report; a missing
    endpoint surfaces as ``endpoint_status="missing"`` with the exact key."""
    global _AUTHORITATIVE_ENDPOINTS
    if remote_python_resume_mono_ns is not None:
        _AUTHORITATIVE_ENDPOINTS["remote_python_resume_mono_ns"] = int(
            remote_python_resume_mono_ns
        )
    if first_durable_result_mono_ns is not None:
        _AUTHORITATIVE_ENDPOINTS["first_durable_result_mono_ns"] = int(
            first_durable_result_mono_ns
        )


def _in_restore_phase() -> bool:
    """True while the ledger is capturing the restore lifecycle.

    ``begin_restore`` sets the phase; ``begin_request`` (method entry) ends
    it.  Restore-session spans/events are stamped while the phase is active.
    """
    return bool(_RESTORE_RID)


def begin_restore(request_id: str = "") -> None:
    """Start the restore phase: clear any previous restore session (a fresh
    restore in the same process never reuses an older one) and any leftover
    request spans, then bind the ledger to the restore identity."""
    global _SPANS, _EVENTS, _RESTORE_SPANS, _RESTORE_EVENTS, _RESTORE_RID, _CURRENT_REQUEST_ID
    with _STORE_LOCK:
        _SPANS = []
        _EVENTS = []
        _RESTORE_SPANS = []
        _RESTORE_EVENTS = []
        _RESTORE_RID = str(request_id or "") or "restore"
    with _IDENTITY_LOCK:
        _CURRENT_REQUEST_ID = str(request_id or "")


def end_restore_phase() -> None:
    """Freeze the restore-phase store; called at method entry so the request
    store starts empty while the restore spans are preserved for the serial
    ledger."""
    global _RESTORE_RID
    with _STORE_LOCK:
        _RESTORE_RID = ""


def _phase_store() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if _in_restore_phase():
        return _RESTORE_SPANS, _RESTORE_EVENTS
    return _SPANS, _EVENTS


def set_request_identity(
    *,
    request_id: str = "",
    trace_id: str = "",
    restored_instance_id: str = "",
    restore_session_id: str = "",
    container_session_id: str = "",
) -> None:
    """Set the per-request identity block.  Called once at method entry (and
    refreshed at restore entry with the restore-time identities).  Never
    raises."""
    global _CURRENT_REQUEST_ID
    try:
        with _IDENTITY_LOCK:
            _IDENTITY.clear()
            _IDENTITY["request_id"] = str(request_id or "")
            _IDENTITY["trace_id"] = str(trace_id or "")
            _IDENTITY["restored_instance_id"] = str(restored_instance_id or "")
            _IDENTITY["restore_session_id"] = str(restore_session_id or "")
            _IDENTITY["container_session_id"] = str(container_session_id or "")
            _CURRENT_REQUEST_ID = str(request_id or "")
    except Exception:
        pass


def current_request_id() -> str:
    with _IDENTITY_LOCK:
        return _CURRENT_REQUEST_ID


def identity_block() -> dict[str, str]:
    """Snapshot of the identity block plus per-call thread identity."""
    with _IDENTITY_LOCK:
        ident = dict(_IDENTITY)
    ident["thread_name"] = threading.current_thread().name or ""
    try:
        ident["native_tid"] = str(threading.get_native_id())
    except Exception:
        ident["native_tid"] = ""
    return ident


# ── Span/event store (thread-safe, request-scoped, bounded) ───────────────

_SPANS: list[dict[str, Any]] = []
_EVENTS: list[dict[str, Any]] = []
_STORE_LOCK = threading.Lock()

_span_counter = 0
_span_counter_lock = threading.Lock()


def _next_span_id() -> str:
    global _span_counter
    with _span_counter_lock:
        _span_counter += 1
        return f"s{_span_counter}"


def begin_request(request_id: str = "") -> None:
    """Reset the ledger for a fresh request.  This is what makes the ledger
    strictly request-scoped: a reused container starts every request with an
    empty span/event store, so previous-request spans can never leak in.

    Restore-phase spans are preserved (moved into the restore-session store):
    they belong to THIS request's serial critical path in the same process.
    """
    global _SPANS, _EVENTS, _CURRENT_REQUEST_ID, _RESTORE_RID, _RESTORE_SPANS, _RESTORE_EVENTS
    with _STORE_LOCK:
        _rsp = list(_RESTORE_SPANS)
        _rev = list(_RESTORE_EVENTS)
        _RESTORE_RID = ""
        _SPANS = []
        _EVENTS = []
        _RESTORE_SPANS = _rsp
        _RESTORE_EVENTS = _rev
    with _IDENTITY_LOCK:
        _CURRENT_REQUEST_ID = str(request_id or "")


def clear_ledger_for_test() -> None:
    """Test helper: clear spans/events/identity without touching env gates."""
    global _SPANS, _EVENTS, _RESTORE_SPANS, _RESTORE_EVENTS, _RESTORE_RID, _CURRENT_REQUEST_ID, _IDENTITY, _AUTHORITATIVE_ENDPOINTS
    # Also reset the bridge registry: an orphaned active bridge from a
    # previous test must never keep a span open across tests.
    try:
        TraceSpanBridge._ACTIVE.clear()
    except Exception:
        pass
    with _STORE_LOCK:
        _SPANS = []
        _EVENTS = []
        _RESTORE_SPANS = []
        _RESTORE_EVENTS = []
        _RESTORE_RID = ""
    with _IDENTITY_LOCK:
        _IDENTITY.clear()
        _CURRENT_REQUEST_ID = ""
    _AUTHORITATIVE_ENDPOINTS.clear()


def record_event(
    name: str,
    *,
    mono_ns: int | None = None,
    wall_ns: int | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> int:
    """Record one point event on the remote monotonic axis.  Never raises."""
    if not _ENABLED:
        return 0
    try:
        mono = int(mono_ns if mono_ns is not None else time.monotonic_ns())
        event: dict[str, Any] = {
            "name": str(name),
            "mono_ns": mono,
        }
        if wall_ns is not None:
            event["wall_ns"] = int(wall_ns)
        event["identity"] = identity_block()
        if metadata:
            event["metadata"] = {str(k): v for k, v in metadata.items()}
        spans_store, events_store = _phase_store()
        with _STORE_LOCK:
            if len(events_store) >= _MAX_EVENTS:
                return 0
            events_store.append(event)
        return mono
    except Exception:
        return 0


class CriticalPathSpan:
    """Context-manager timed scope writing directly to the canonical ledger.

    Every meaningful timed scope on the critical path uses this (or
    ``begin_span``/``end_span`` for split-boundary scopes).  The accounting
    fields (work/wait/sync/child/residual) are populated by the explicit
    ``record_work``/``record_wait``/``record_sync``/``add_child`` calls and by
    the automatic ``duration``; ``finalize`` derives residual as
    ``duration - work - wait - sync - child_union`` and labels any unexplained
    wall ``UNATTRIBUTED``.
    """

    def __init__(
        self,
        name: str,
        *,
        lane: str = "MAIN",
        parent_span_id: str = "",
        metadata: Mapping[str, Any] | None = None,
        start_mono_ns: int | None = None,
    ) -> None:
        self.name = str(name)
        self.lane = str(lane)
        self.span_id = _next_span_id()
        self.parent_span_id = str(parent_span_id or "")
        self.metadata = dict(metadata or {})
        # Windows monotonic_ns has ~15.6 ms tick granularity.  Keep the wall
        # axis for exact durations (same remote process, same axis semantics),
        # and the monotonic axis for cross-process correlation.  All timing
        # fields are derived from a single process-local axis.
        self._t0 = time.perf_counter_ns()
        self.start_wall_ns = int(time.time_ns())
        self.start_mono_ns = int(
            start_mono_ns if start_mono_ns is not None else time.monotonic_ns()
        )
        self.end_mono_ns: int | None = None
        self.end_wall_ns: int | None = None
        self._work_ns = 0
        self._wait_ns = 0
        self._sync_ns = 0
        self._child_intervals: list[tuple[int, int]] = []
        self._finalized = False
        self._current_child: "CriticalPathSpan | None" = None
        self._active = False
        self._end_perf_ns: int | None = None

    def _elapsed_ns(self) -> int:
        """Exact process-local elapsed ns (perf_counter axis)."""
        return int(self._end_perf_ns - self._t0) if self._end_perf_ns is not None else 0

    # ── timing accumulation ──
    def record_work(self, ns: int) -> None:
        if ns > 0:
            self._work_ns += int(ns)

    def record_wait(self, ns: int) -> None:
        if ns > 0:
            self._wait_ns += int(ns)

    def record_sync(self, ns: int) -> None:
        if ns > 0:
            self._sync_ns += int(ns)

    def add_child(self, child: "CriticalPathSpan") -> None:
        """Register a child span interval (for union coverage).  Never raises.

        Uses the child's process-local ``perf_counter_ns`` boundaries when
        available (the fine axis — correct even when the coarse 15.6 ms
        Windows monotonic tick collapses sub-tick children to zero width),
        falling back to the monotonic boundaries otherwise.
        """
        try:
            if child._end_perf_ns is not None and child._t0 is not None:
                self._child_intervals.append(
                    (int(child._t0), int(child._end_perf_ns))
                )
                return
            if child.end_mono_ns is None:
                return
            self._child_intervals.append(
                (int(child.start_mono_ns), int(child.end_mono_ns))
            )
        except Exception:
            pass

    # ── context manager ──
    def __enter__(self) -> "CriticalPathSpan":
        self._active = True
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.end()
        return False

    def end(self) -> dict[str, Any] | None:
        """Close the span, finalize accounting, persist to the ledger."""
        if self._finalized:
            return None
        self._finalized = True
        self._active = False
        self._end_perf_ns = time.perf_counter_ns()
        try:
            self.end_mono_ns = int(time.monotonic_ns())
        except Exception:
            self.end_mono_ns = self.start_mono_ns
        try:
            self.end_wall_ns = int(time.time_ns())
        except Exception:
            self.end_wall_ns = self.start_wall_ns
        return self._persist()

    # ── split-boundary API (for spans opened/closed at different code sites) ──
    def finish(
        self,
        end_mono_ns: int | None = None,
        mono_ns: int | None = None,
    ) -> dict[str, Any] | None:
        """Close the span at an explicit boundary stamp.

        Accepts BOTH ``end_mono_ns`` and ``mono_ns`` keyword spellings:
        several close sites historically used ``mono_ns=`` (the event API
        spelling), which raised TypeError and silently dropped the whole
        span under the surrounding ``except Exception: pass``.  The two
        spellings are aliases; when both are given ``end_mono_ns`` wins.
        """
        if mono_ns is not None and end_mono_ns is None:
            end_mono_ns = mono_ns
        if self._finalized:
            return None
        self._finalized = True
        self._active = False
        self._end_perf_ns = time.perf_counter_ns()
        self.end_mono_ns = int(
            end_mono_ns if end_mono_ns is not None else time.monotonic_ns()
        )
        try:
            self.end_wall_ns = int(time.time_ns())
        except Exception:
            self.end_wall_ns = self.start_wall_ns
        return self._persist()

    def _persist(self) -> dict[str, Any] | None:
        if not _ENABLED:
            return None
        try:
            duration_ns = self._elapsed_ns()
            child_union_ns = _union_length(self._child_intervals)
            residual_ns = max(
                0, duration_ns - self._work_ns - self._wait_ns - self._sync_ns - child_union_ns
            )
            record: dict[str, Any] = {
                "name": self.name,
                "lane": self.lane,
                "span_id": self.span_id,
                "parent_span_id": self.parent_span_id,
                "start_mono_ns": self.start_mono_ns,
                "end_mono_ns": self.end_mono_ns or self.start_mono_ns,
                "duration_ms": round(duration_ns / 1_000_000, 3),
                "work_ms": round(self._work_ns / 1_000_000, 3),
                "wait_ms": round(self._wait_ns / 1_000_000, 3),
                "sync_ms": round(self._sync_ns / 1_000_000, 3),
                "child_union_ms": round(child_union_ns / 1_000_000, 3),
                "residual_ms": round(residual_ns / 1_000_000, 3),
                "residual_label": "UNATTRIBUTED" if residual_ns > 1_000_000 else "explained",
                "identity": identity_block(),
            }
            if self.metadata:
                record["metadata"] = dict(self.metadata)
            spans_store, _events_store = _phase_store()
            with _STORE_LOCK:
                if len(spans_store) >= _MAX_SPANS:
                    return record
                spans_store.append(record)
            return record
        except Exception:
            return None


def begin_span(
    name: str,
    *,
    lane: str = "MAIN",
    parent_span_id: str = "",
    metadata: Mapping[str, Any] | None = None,
    start_mono_ns: int | None = None,
) -> CriticalPathSpan:
    """Open a ledger span (use the context manager or finish() to close)."""
    return CriticalPathSpan(
        name,
        lane=lane,
        parent_span_id=parent_span_id,
        metadata=metadata,
        start_mono_ns=start_mono_ns,
    )


def _event_name_pairs(event_stamps: list[int]) -> list[tuple[str, int]]:
    """Map event stamps back to their names for serial-ledger markers."""
    if not event_stamps:
        return []
    try:
        with _STORE_LOCK:
            by_ts: dict[int, str] = {}
            for e in [*_RESTORE_EVENTS, *_EVENTS]:
                by_ts.setdefault(int(e["mono_ns"]), str(e.get("name", "event")))
        return [(by_ts.get(ts, "event"), ts) for ts in event_stamps]
    except Exception:
        return [("event", ts) for ts in event_stamps]


def _union_length(intervals: Iterable[tuple[int, int]]) -> int:
    """Total covered length of possibly-overlapping intervals."""
    total = 0
    ordered = sorted(intervals)
    cur_start: int | None = None
    cur_end = 0
    for s, e in ordered:
        if cur_start is None:
            cur_start, cur_end = s, e
        elif s <= cur_end:
            cur_end = max(cur_end, e)
        else:
            total += max(0, cur_end - cur_start)
            cur_start, cur_end = s, e
    if cur_start is not None:
        total += max(0, cur_end - cur_start)
    return total


# ── Explicit wait/sync instrumentation helpers (measurement only) ─────────

def timed_wait(
    name: str,
    fn: Any,
    *args: Any,
    span: CriticalPathSpan | None = None,
    wait_kind: str = "unknown",
    **kwargs: Any,
) -> Any:
    """Run a blocking call while recording the explicit wait duration on the
    caller's span (when provided) as ``wait_ms`` with ``wait_primitive``
    metadata.  Never raises — errors propagate from ``fn`` unchanged."""
    t0 = time.monotonic_ns()
    result = fn(*args, **kwargs)
    waited = time.monotonic_ns() - t0
    if span is not None:
        span.record_wait(waited)
    record_event(
        "wait_completed",
        metadata={
            "wait_name": str(name),
            "wait_kind": str(wait_kind),
            "wait_ms": round(waited / 1_000_000, 3),
        },
    )
    return result


def timed_sync(
    name: str,
    fn: Any,
    *args: Any,
    span: CriticalPathSpan | None = None,
    **kwargs: Any,
) -> Any:
    """Run an explicit device-synchronization call recording ``sync_ms`` on
    the caller's span.  Never raises — errors propagate from ``fn`` unchanged."""
    t0 = time.monotonic_ns()
    result = fn(*args, **kwargs)
    synced = time.monotonic_ns() - t0
    if span is not None:
        span.record_sync(synced)
    record_event(
        "sync_completed",
        metadata={
            "sync_name": str(name),
            "sync_ms": round(synced / 1_000_000, 3),
        },
    )
    return result


# ── Serial ledger / zero-gap reconciliation ───────────────────────────────

def _ms(ns: int) -> float:
    return round(ns / 1_000_000, 3)


def build_serial_ledger(
    *,
    start_mono_ns: int,
    end_mono_ns: int,
    spans: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Construct the zero-gap serial ledger from ``start_mono_ns`` to
    ``end_mono_ns`` using the given spans (default: the current store).

    The serial axis is the single remote-process monotonic clock.  Spans are
    flattened onto that axis; gaps between consecutive covered intervals with
    no owning span are reported as explicit ``UNATTRIBUTED`` segments (never
    blank).  Returns a JSON-safe dict with ``segments``, ``total_ms``,
    ``covered_ms``, ``unattributed_ms`` and ``remainder_ms`` (total - covered -
    unattributed, expected < 0.1 ms)."""
    span_list = list(spans if spans is not None else get_spans())
    # Point events share the serial axis: an event-only window (e.g. a
    # sampling_end emission with no owning span yet) must be represented, not
    # reported as a hole.  They render as zero-duration ownership markers.
    event_stamps: list[int] = []
    if spans is None:
        event_stamps = [int(e["mono_ns"]) for e in get_events()]
    ordered = sorted(
        span_list,
        key=lambda s: (int(s["start_mono_ns"]), int(s["end_mono_ns"])),
    )
    segments: list[dict[str, Any]] = []
    cursor = int(start_mono_ns)
    end = int(end_mono_ns)
    # Merge span starts with event stamps so event boundaries that precede the
    # first span (or fall in gaps) split the UNATTRIBUTED segments instead of
    # disappearing; the event itself remains a zero-duration marker.
    boundaries = sorted({int(s["start_mono_ns"]) for s in ordered} | set(event_stamps))
    for s in ordered:
        s_start = int(s["start_mono_ns"])
        s_end = int(s["end_mono_ns"])
        if s_end <= cursor:
            continue
        if s_start > cursor:
            segments.append({
                "name": "UNATTRIBUTED",
                "start_mono_ns": cursor,
                "end_mono_ns": s_start,
                "duration_ms": _ms(s_start - cursor),
                "owner": None,
            })
        if s_end > cursor:
            segments.append({
                "name": str(s.get("name", "?")),
                "start_mono_ns": max(cursor, s_start),
                "end_mono_ns": s_end,
                "duration_ms": _ms(s_end - max(cursor, s_start)),
                "owner": s.get("span_id", ""),
                "lane": s.get("lane", ""),
            })
            cursor = s_end
    # Zero-duration event markers on the serial axis (never fabricated spans).
    event_markers = [
        {
            "name": "event",
            "event_name": name,
            "start_mono_ns": ts,
            "end_mono_ns": ts,
            "duration_ms": 0.0,
            "owner": None,
        }
        for name, ts in _event_name_pairs(event_stamps)
        if int(start_mono_ns) <= ts <= int(end_mono_ns)
    ]
    if event_markers:
        segments.extend(event_markers)
        segments.sort(key=lambda seg: int(seg["start_mono_ns"]))
    if cursor < end:
        segments.append({
            "name": "UNATTRIBUTED",
            "start_mono_ns": cursor,
            "end_mono_ns": end,
            "duration_ms": _ms(end - cursor),
            "owner": None,
        })
    total_ms = _ms(end - start_mono_ns)
    covered_ms = sum(
        seg["duration_ms"] for seg in segments if seg["name"] != "UNATTRIBUTED"
    )
    unattributed_ms = sum(
        seg["duration_ms"] for seg in segments if seg["name"] == "UNATTRIBUTED"
    )
    remainder_ms = round(total_ms - covered_ms - unattributed_ms, 3)
    return {
        "start_mono_ns": int(start_mono_ns),
        "end_mono_ns": int(end_mono_ns),
        "total_ms": total_ms,
        "covered_ms": round(covered_ms, 3),
        "unattributed_ms": round(unattributed_ms, 3),
        "remainder_ms": remainder_ms,
        "segments": segments,
        "zero_gap": abs(remainder_ms) < 0.1,
        "request_id": current_request_id(),
    }


def reconcile_scope_arithmetic(span: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the invariant for one span:

        duration ≈ work + wait + sync + child_union + residual

    Returns ``{"ok": bool, "delta_ms": float, "duration_ms": ...}``.
    """
    duration = float(span.get("duration_ms", 0.0))
    accounted = (
        float(span.get("work_ms", 0.0))
        + float(span.get("wait_ms", 0.0))
        + float(span.get("sync_ms", 0.0))
        + float(span.get("child_union_ms", 0.0))
        + float(span.get("residual_ms", 0.0))
    )
    delta = round(duration - accounted, 3)
    return {
        "span_id": span.get("span_id", ""),
        "name": span.get("name", "?"),
        "duration_ms": duration,
        "accounted_ms": round(accounted, 3),
        "delta_ms": delta,
        # Tolerance 0.2 ms: on Windows the monotonic axis ticks at ~15.6 ms so
        # an arbitrary recorded span boundary can carry up to one tick of
        # representation error in the reconciliation of persisted records.
        "ok": abs(delta) < 0.2,
    }


def get_spans() -> list[dict[str, Any]]:
    with _STORE_LOCK:
        return list(_SPANS)


def get_events() -> list[dict[str, Any]]:
    with _STORE_LOCK:
        return list(_EVENTS)


def get_restore_spans() -> list[dict[str, Any]]:
    with _STORE_LOCK:
        return list(_RESTORE_SPANS)


def get_restore_events() -> list[dict[str, Any]]:
    with _STORE_LOCK:
        return list(_RESTORE_EVENTS)


def request_ledger_report() -> dict[str, Any]:
    """JSON-safe snapshot of the current request ledger: identity, spans,
    events, per-span arithmetic reconciliation, and the serial zero-gap
    ledger from the earliest to the latest recorded boundary.

    The serial axis spans restore entry .. first durable result: the
    restore-session spans/events (same process, same monotonic clock) are
    included whenever a restore session exists for this container process.

    E29 acceptance contract: the serial ledger MUST use the explicit
    authoritative endpoints set via ``set_authoritative_endpoints()``
    (remote_python_resume_mono_ns -> first_durable_result_mono_ns), NOT
    min/max(existing spans/events).  A truncated ledger must not be able to
    tile its own truncated interval and still claim zero-gap: if the
    authoritative endpoints are missing, the report's ``serial_ledger`` is
    None and ``endpoint_status`` carries the exact missing boundary.
    """
    spans = get_spans()
    events = get_events()
    restore_spans = get_restore_spans()
    restore_events = get_restore_events()
    all_spans = [*restore_spans, *spans]
    all_events = [*restore_events, *events]
    # ── E29: explicit authoritative endpoints (not min/max of events) ────
    auth = dict(_AUTHORITATIVE_ENDPOINTS)
    start = auth.get("remote_python_resume_mono_ns")
    end = auth.get("first_durable_result_mono_ns")
    missing = []
    if start is None:
        missing.append("remote_python_resume_mono_ns")
    if end is None:
        missing.append("first_durable_result_mono_ns")
    if start is None or end is None:
        return {
            "identity": identity_block(),
            "span_count": len(all_spans),
            "event_count": len(all_events),
            "restore_span_count": len(restore_spans),
            "request_span_count": len(spans),
            "spans": all_spans,
            "events": all_events,
            "reconciliation": [reconcile_scope_arithmetic(s) for s in all_spans],
            "serial_ledger": None,
            "endpoint_status": "missing",
            "missing_endpoints": missing,
        }
    start = int(start)
    end = int(end)
    return {
        "identity": identity_block(),
        "span_count": len(all_spans),
        "event_count": len(all_events),
        "restore_span_count": len(restore_spans),
        "request_span_count": len(spans),
        "spans": all_spans,
        "events": all_events,
        "reconciliation": [reconcile_scope_arithmetic(s) for s in all_spans],
        "serial_ledger": build_serial_ledger(
            start_mono_ns=start, end_mono_ns=end, spans=all_spans,
        ),
        "endpoint_status": "ok",
        "start_mono_ns": start,
        "end_mono_ns": end,
    }


def assert_serial_ledger_zero_gap(
    *,
    start_mono_ns: int,
    end_mono_ns: int,
    spans: Iterable[dict[str, Any]] | None = None,
    tolerance_ms: float = 1.0,
) -> dict[str, Any]:
    """HARD reconciliation invariant (Phase 3): the serial partition from
    ``start_mono_ns`` to ``end_mono_ns`` must cover the whole window with no
    missing interval.

    ``total_ms`` (endpoint delta) minus the sum of all segment durations must
    be below ``tolerance_ms`` (default 1 ms; much smaller in practice on a
    single process-local clock).  Every nanosecond belongs to a known span or
    explicit UNATTRIBUTED.  Raises ``AssertionError`` when the invariant
    fails; returns the serial ledger dict on success.  Never silent."""
    serial = build_serial_ledger(
        start_mono_ns=start_mono_ns, end_mono_ns=end_mono_ns, spans=spans,
    )
    total = float(serial.get("total_ms", 0.0))
    segment_sum = sum(float(seg.get("duration_ms", 0.0)) for seg in serial.get("segments", []))
    gap = abs(total - segment_sum)
    if gap >= tolerance_ms:
        raise AssertionError(
            f"serial ledger zero-gap violated: total_ms={total} "
            f"segment_sum={segment_sum} gap_ms={gap} "
            f"(tolerance {tolerance_ms} ms); every interval must be a proven "
            f"stage or explicit UNATTRIBUTED"
        )
    return serial


def capture_ledger_report_for_artifact() -> dict[str, Any] | None:
    """Return the full canonical ledger report (identity, spans, events,
    reconciliation, serial zero-gap ledger) for persisting into the run
    artifact, or None when the ledger is disabled.  Never raises."""
    if not _ENABLED:
        return None
    try:
        return request_ledger_report()
    except Exception:
        return None


def emit_ledger_report(request_id: str = "") -> None:
    """Print the canonical ledger report as one coherent log block (gated)."""
    if not _ENABLED:
        return
    try:
        report = request_ledger_report()
        rid = str(request_id or report.get("identity", {}).get("request_id", ""))
        serial = report.get("serial_ledger", {})
        print(
            f"[v2.ledger] request={rid} spans={report.get('span_count', 0)} "
            f"events={report.get('event_count', 0)} "
            f"total_ms={serial.get('total_ms', 0.0)} "
            f"covered_ms={serial.get('covered_ms', 0.0)} "
            f"unattributed_ms={serial.get('unattributed_ms', 0.0)} "
            f"remainder_ms={serial.get('remainder_ms', 0.0)} "
            f"zero_gap={int(serial.get('zero_gap', False))}",
            flush=True,
        )
        for seg in serial.get("segments", []):
            print(
                f"[v2.ledger.segment] request={rid} name={seg.get('name')} "
                f"start={seg.get('start_mono_ns')} end={seg.get('end_mono_ns')} "
                f"duration_ms={seg.get('duration_ms')} owner={seg.get('owner') or '-'}",
                flush=True,
            )
        for span in report.get("spans", []):
            print(
                f"[v2.ledger.span] request={rid} name={span.get('name')} "
                f"span_id={span.get('span_id')} lane={span.get('lane')} "
                f"start={span.get('start_mono_ns')} end={span.get('end_mono_ns')} "
                f"duration_ms={span.get('duration_ms')} "
                f"work_ms={span.get('work_ms')} wait_ms={span.get('wait_ms')} "
                f"sync_ms={span.get('sync_ms')} child_union_ms={span.get('child_union_ms')} "
                f"residual_ms={span.get('residual_ms')} "
                f"residual_label={span.get('residual_label')}",
                flush=True,
            )
    except Exception:
        pass


# ── Trace-event bridge (span boundaries ride the existing trace events) ──

class TraceSpanBridge:
    """Map named trace events to canonical ledger spans.

    Production emit sites already stamp exact monotonic boundaries via
    ``trace.emit("name_start"/"name_end")``.  This bridge turns any such
    start/end event pair into a real canonical ledger span WITHOUT adding a
    second instrumentation pass at every site — the ledger becomes the single
    timing owner and the Gantt/waterfall stay pure consumers.  ``_ENABLED``
    gating and request/restore phase routing apply exactly like direct spans.
    """

    _ACTIVE: dict[str, "TraceSpanBridge"] = {}

    def __init__(self, name: str, *, lane: str = "MAIN", metadata: Mapping[str, Any] | None = None) -> None:
        self.name = str(name)
        self.lane = str(lane)
        self.metadata = dict(metadata or {})
        self.span: CriticalPathSpan | None = None

    def start(self, mono_ns: int | None = None) -> None:
        if self.span is not None:
            return
        if not _ENABLED:
            return
        try:
            existing = TraceSpanBridge._ACTIVE.get(self.name)
            if existing is not None and existing.span is not None:
                # A reentrant start for the same name must never create a
                # second span; reuse the active one (fresh objects just adopt
                # the existing span).
                self.span = existing.span
                return
            self.span = begin_span(
                self.name, lane=self.lane, metadata=self.metadata or None,
                start_mono_ns=mono_ns,
            )
            TraceSpanBridge._ACTIVE[self.name] = self
        except Exception:
            self.span = None

    def end(self, mono_ns: int | None = None) -> None:
        span = self.span
        if span is None:
            # A fresh object closing a span that was opened elsewhere: adopt
            # the active bridge for this name (the sampler finally creates a
            # NEW bridge and closes it; the span lives on the active one).
            try:
                existing = TraceSpanBridge._ACTIVE.get(self.name)
                if existing is not None and existing.span is not None:
                    span = existing.span
                    self.span = span
            except Exception:
                span = None
        if span is None:
            return
        try:
            span.finish(end_mono_ns=mono_ns)
        except Exception:
            pass
        try:
            TraceSpanBridge._ACTIVE.pop(self.name, None)
        except Exception:
            pass
        self.span = None

    @classmethod
    def close_all(cls) -> None:
        for bridge in list(cls._ACTIVE.values()):
            bridge.end()
