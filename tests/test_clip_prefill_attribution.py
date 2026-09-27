"""Focused tests for CLIP execution-prefill attribution (Phase B diagnostics).

Verifies, using fake coordinator/loaders/encode callbacks and a real
``RuntimeTrace`` (no Modal, no GPU, no ComfyUI imports):
  - exactly one prefill future and one encode callback per request
  - all phase markers: submission, worker start, readiness, encode,
    completion, graph wait, and the single reconciliation record
  - reconciliation arithmetic: ``prefill_total = queue + readiness +
    encode + completion + unattributed`` with ``|unattributed| <= 50ms``
    when complete
  - truthful ``None`` values when a boundary is absent (never fabricated)
  - real coordinator queue depth / pending lane count at submission and
    worker start, without altering execution
  - Linux-native counter capture (thread/process CPU, faults, context
    switches, io, native thread count, torch intraop/interop) reports
    truthfully when unavailable
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any, Mapping

import comfymodal_runtime.model_preload as mp
from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
from comfymodal_runtime.trace import RuntimeTrace


# ── Helpers ────────────────────────────────────────────────────────────


def _build_bridge(
    *,
    unet_loader: Any = None,
    clip_loader: Any = None,
    invoke_original: Any = None,
    max_workers: int = 3,
) -> mp.V2LoaderBridge:
    """Build a V2LoaderBridge with mocked internals suitable for attribution
    tests.  All callables default to safe pass-throughs."""
    bridge = mp.V2LoaderBridge(max_workers=max_workers)
    bridge.install = lambda nodes=None, trace=None: True
    bridge._request_list = lambda bucket: [{"clip_name": "clip_l.safetensors"}]
    bridge._model_spec = {
        "loaders": {
            "unet": [{"unet_name": "unet.safetensors"}],
            "clip": [{"clip_name": "clip_l.safetensors"}],
        }
    }
    bridge.coordinator.clip_loader = clip_loader or (lambda key: SimpleNamespace())
    bridge.coordinator.unet_loader = unet_loader or (lambda key: "unet-done")
    bridge._invoke_original = invoke_original or (
        lambda class_name, kwargs: (f"conditioning:{kwargs['text']}",)
    )
    return bridge


def _make_plan(
    unet_identity: str = "unet.safetensors",
    clip_identity: str = "clip_l.safetensors",
    text: str = "a happy cat",
    role: str = "positive",
) -> RestorePlan:
    """Minimal RestorePlan with a single critical-role encode entry."""
    model_key = ModelRestoreKey(
        unet_identity=unet_identity,
        clip_identity=clip_identity,
        clip_type="stable_diffusion",
    )
    prefill_key = PrefillKey(
        model_key=model_key,
        prompt_bundle_hash="hash-attr",
        encode_options={
            "eligible": True,
            "encodes": [
                {
                    "node_id": "6",
                    "text": text,
                    "role": role,
                }
            ],
        },
    )
    return RestorePlan(model_key=model_key, prefill_key=prefill_key)


def _wait_future(fut: Any, timeout: float = 5.0) -> Any:
    if fut is None:
        return None
    return fut.result(timeout=timeout)


def _event_meta(trace: RuntimeTrace, name: str) -> list[dict[str, Any]]:
    return [dict(e.metadata) for e in trace.events if e.name == name]


def _event_names(trace: RuntimeTrace) -> set[str]:
    return {e.name for e in trace.events}


# ── Phase marker / reconciliation flow tests ───────────────────────────


class TestClipPrefillAttributionFlow:
    """Full happy-path flow through the bridge: one future, one encode,
    all phase markers, one reconciliation record with exact arithmetic."""

    def test_happy_path_markers_one_future_one_encode(self):
        encode_calls: list[str] = []

        def tracking_encode(class_name: str, kwargs: dict[str, Any]) -> tuple[str, ...]:
            encode_calls.append(kwargs.get("text", ""))
            return (f"conditioning:{kwargs['text']}",)

        clip_obj = SimpleNamespace(patcher=SimpleNamespace())
        bridge = _build_bridge(
            clip_loader=lambda key: clip_obj,
            invoke_original=tracking_encode,
            max_workers=2,
        )
        trace = RuntimeTrace(request_id="attr-happy", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)

        prep = bridge._preparation
        assert prep is not None
        # No prefill future yet (deferred to execution phase).
        assert prep.prefill_future is None

        # ── Schedule exactly once; idempotent second call reuses it ──
        assert bridge.schedule_execution_prefill(trace=trace) is True
        fut_a = prep.prefill_future
        assert fut_a is not None
        assert bridge.schedule_execution_prefill(trace=trace) is True
        assert prep.prefill_future is fut_a, "second schedule must not create a new future"

        results = _wait_future(fut_a)
        assert results is not None and len(results) == 1

        # ── One encode, exactly ──
        assert encode_calls == ["a happy cat"], (
            f"expected exactly one encode, got {encode_calls}"
        )

        # ── Graph consumption uses the cached result (no re-encode) ──
        consumed = bridge._consume_prefill((), {"clip": clip_obj, "text": "a happy cat"})
        assert consumed is not None and consumed is not mp._LOADER_MISS
        assert encode_calls == ["a happy cat"], (
            "graph consumption must NOT re-encode (cache hit)"
        )

        # ── All phase markers present ──
        names = _event_names(trace)
        for marker in (
            mp._EVENT_SUBMISSION,      # execution_prefill_scheduled
            mp._EVENT_WORKER_START,     # execution_prefill_submitted
            mp._EVENT_READINESS_START,
            mp._EVENT_READINESS_END,
            mp._EVENT_ENCODE_START,
            mp._EVENT_ENCODE_END,
            mp._EVENT_COMPLETED,
            "graph_prefill_demand",
            "graph_prefill_wait_start",
            "graph_prefill_wait_end",
            "graph_prefill_consumed",
            mp._EVENT_RECONCILIATION,
        ):
            assert marker in names, f"missing marker {marker}"

        # ── Exactly one reconciliation record per request ──
        records = _event_meta(trace, mp._EVENT_RECONCILIATION)
        assert len(records) == 1, f"expected 1 reconciliation, got {len(records)}"
        record = records[0]

        # ── Reconciliation arithmetic (complete, error <= 50ms) ──
        assert record["outcome"] == "consumed"
        assert record["reconciliation_status"] == "complete", record
        for field in (
            "prefill_total_ms", "queue_ms", "readiness_ms", "encode_ms",
            "completion_ms", "request_wait_ms", "measured_children_ms",
            "unattributed_ms",
        ):
            assert record[field] is not None, f"{field} must be present when complete"
        assert record["encoded_count"] == 1
        assert record["terminal_event"] == mp._EVENT_COMPLETED

        children = (
            record["queue_ms"] + record["readiness_ms"]
            + record["encode_ms"] + record["completion_ms"]
        )
        assert abs(children - record["measured_children_ms"]) < 0.01
        total = record["prefill_total_ms"]
        assert abs(total - children - record["unattributed_ms"]) < 0.01, (
            "unattributed must equal total - measured children"
        )
        assert abs(record["unattributed_ms"]) <= 50.0, (
            f"unattributed {record['unattributed_ms']}ms exceeds 50ms tolerance"
        )
        assert record["queue_ms"] >= 0
        assert record["request_wait_ms"] >= 0

        # ── Worker-side counter metadata is truthful ──
        assert isinstance(record["worker_native_tid"], int)
        assert isinstance(record["worker_native_thread_count"], int)
        assert isinstance(record["torch_available"], bool)
        for phase_key in ("readiness", "encode"):
            phase = record[phase_key]
            assert isinstance(phase, Mapping), f"{phase_key} must be a mapping"
            # wall_ms always present in-snapshot; thread/process CPU present
            # on this platform when both snapshots exist in the same thread.
            assert "wall_ms" in phase

        bridge.coordinator.close()

    def test_second_consume_does_not_emit_second_reconciliation(self):
        """Two CLIPTextEncode nodes with identical text: one record total."""
        clip_obj = SimpleNamespace(patcher=SimpleNamespace())
        bridge = _build_bridge(
            clip_loader=lambda key: clip_obj,
            max_workers=2,
        )
        trace = RuntimeTrace(request_id="attr-dedupe", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)
        prep = bridge._preparation
        assert prep is not None
        bridge.schedule_execution_prefill(trace=trace)
        _wait_future(prep.prefill_future)

        r1 = bridge._consume_prefill((), {"clip": clip_obj, "text": "a happy cat"})
        r2 = bridge._consume_prefill((), {"clip": clip_obj, "text": "a happy cat"})
        assert r1 is not mp._LOADER_MISS
        assert r2 is not mp._LOADER_MISS

        records = _event_meta(trace, mp._EVENT_RECONCILIATION)
        assert len(records) == 1, (
            f"exactly one reconciliation per request, got {len(records)}"
        )
        bridge.coordinator.close()

    def test_cache_hit_publication_never_precedes_terminal_events(self):
        """Regression: a successful prefill cache-hit can never emit
        ``clip_prefill_reconciliation`` before ``execution_prefill_encode_end``
        / ``execution_prefill_completed``.

        The worker publishes ``_prefill_results`` only AFTER the terminal
        events have been emitted.  The publishing dict asserts that invariant
        at the exact moment the results become visible to a graph consumer."""
        clip_obj = SimpleNamespace(patcher=SimpleNamespace())

        class _ResultPublishingDict(dict):
            def __init__(self, trace: RuntimeTrace) -> None:
                super().__init__()
                self._trace = trace
                self._update_count = 0

            def update(self, *args, **kwargs):
                names = {e.name for e in self._trace.events}
                assert mp._EVENT_ENCODE_END in names, (
                    "prefill results published before execution_prefill_encode_end"
                )
                assert mp._EVENT_COMPLETED in names, (
                    "prefill results published before execution_prefill_completed"
                )
                self._update_count += 1
                super().update(*args, **kwargs)

        bridge = _build_bridge(
            clip_loader=lambda key: clip_obj,
            max_workers=2,
        )
        trace = RuntimeTrace(request_id="attr-race", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)
        prep = bridge._preparation
        assert prep is not None

        bridge._prefill_results = _ResultPublishingDict(trace)
        assert bridge.schedule_execution_prefill(trace=trace) is True
        _wait_future(prep.prefill_future)

        # Graph cache-hit consume: the result is already published, so the
        # reconciliation must be built AFTER the terminal events are present.
        consumed = bridge._consume_prefill((), {"clip": clip_obj, "text": "a happy cat"})
        assert consumed is not mp._LOADER_MISS
        assert bridge._prefill_results._update_count == 1

        records = _event_meta(trace, mp._EVENT_RECONCILIATION)
        assert len(records) == 1
        record = records[0]
        assert record["reconciliation_status"] == "complete", record
        assert record["terminal_event"] == mp._EVENT_COMPLETED
        # Event ORDER: the terminal boundaries precede the reconciliation
        # record on the trace, so the record can never be built before them.
        names = [e.name for e in trace.events]
        assert names.index(mp._EVENT_ENCODE_END) < names.index(mp._EVENT_RECONCILIATION)
        assert names.index(mp._EVENT_COMPLETED) < names.index(mp._EVENT_RECONCILIATION)
        bridge.coordinator.close()

    def test_fallback_unavailable_emits_reconciliation_with_incomplete_status(self):
        """Worker failure (no_clip) → graph falls back and the record is
        emitted with truthful None for absent boundaries."""
        bridge = _build_bridge(max_workers=1)
        bridge.coordinator.clip_loader = lambda key: None  # no CLIP

        trace = RuntimeTrace(request_id="attr-fallback", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)
        prep = bridge._preparation
        assert prep is not None
        bridge.schedule_execution_prefill(trace=trace)
        _wait_future(prep.prefill_future)

        clip_obj = SimpleNamespace()
        consumed = bridge._consume_prefill((), {"clip": clip_obj, "text": "a happy cat"})
        assert consumed is mp._LOADER_MISS, "no prefill result must fall back"

        records = _event_meta(trace, mp._EVENT_RECONCILIATION)
        assert len(records) == 1
        record = records[0]
        assert record["outcome"] == "fallback_unavailable"
        assert record["terminal_event"] == mp._EVENT_FAILED
        # The worker failed before readiness/encode boundaries existed:
        # these must be truthful None, never fabricated zeros.
        assert record["readiness_ms"] is None
        assert record["encode_ms"] is None
        assert record["completion_ms"] is None
        assert record["prefill_total_ms"] is not None  # submission→failure exists
        assert record["queue_ms"] is not None          # submission→worker start exists
        assert record["reconciliation_status"] == "incomplete"
        bridge.coordinator.close()


# ── Pure reconciliation builder tests ──────────────────────────────────


class _FakeEvent:
    def __init__(self, name: str, mono_ns: int, metadata: dict[str, Any] | None = None) -> None:
        self.name = name
        self.monotonic_ns = mono_ns
        self.metadata = metadata or {}


class _FakeTrace:
    def __init__(self, events: list[_FakeEvent]) -> None:
        self.events = events


class TestReconciliationBuilder:
    """build_clip_prefill_reconciliation is a pure function over trace
    events: complete flows reconcile within 50ms, missing boundaries are
    None, and negative accounting is surfaced as ``overlap``."""

    def test_complete_flow_reconciles_within_50ms(self):
        trace = RuntimeTrace(request_id="builder-complete", process="remote")
        trace.emit(mp._EVENT_SUBMISSION, phase="execution")
        time.sleep(0.01)
        trace.emit(mp._EVENT_WORKER_START, phase="execution", metadata={"counters": {}})
        time.sleep(0.01)
        trace.emit(mp._EVENT_READINESS_START, phase="execution", metadata={"counters": {}})
        time.sleep(0.01)
        trace.emit(mp._EVENT_READINESS_END, phase="execution", metadata={"counters": {}})
        time.sleep(0.01)
        trace.emit(mp._EVENT_ENCODE_START, phase="execution", metadata={"counters": {}})
        time.sleep(0.01)
        trace.emit(mp._EVENT_ENCODE_END, phase="execution", metadata={"counters": {}})
        time.sleep(0.01)
        trace.emit(mp._EVENT_COMPLETED, phase="execution", metadata={"encoded_count": 1})
        # Request-side graph wait (emitted on the request thread, after the
        # worker completes) so request_wait_ms is bounded too.
        trace.emit("graph_prefill_wait_start", phase="execution")
        trace.emit("graph_prefill_wait_end", phase="execution", metadata={"status": "ok"})

        record = mp.build_clip_prefill_reconciliation(
            trace, outcome="consumed", request_id="builder-complete"
        )
        assert record["reconciliation_status"] == "complete", record
        assert record["outcome"] == "consumed"
        assert record["request_id"] == "builder-complete"
        assert record["encoded_count"] == 1
        for field in (
            "prefill_total_ms", "queue_ms", "readiness_ms", "encode_ms",
            "completion_ms", "request_wait_ms", "unattributed_ms",
        ):
            assert record[field] is not None, f"{field} must be present"
        assert abs(record["unattributed_ms"]) <= 50.0, record
        children = (
            record["queue_ms"] + record["readiness_ms"]
            + record["encode_ms"] + record["completion_ms"]
        )
        assert abs(record["prefill_total_ms"] - children - record["unattributed_ms"]) < 0.01

    def test_required_fields_present(self):
        record = mp.build_clip_prefill_reconciliation(
            _FakeTrace([]), outcome="unknown", request_id="req"
        )
        required = {
            "request_id", "outcome", "prefill_total_ms", "queue_ms",
            "readiness_ms", "encode_ms", "completion_ms", "request_wait_ms",
            "measured_children_ms", "unattributed_ms", "reconciliation_status",
            "encoded_count", "terminal_event", "worker_native_tid",
            "worker_native_thread_count", "torch_available",
            "torch_intraop_threads", "torch_interop_threads", "readiness",
            "encode",
        }
        assert required <= set(record.keys()), f"missing: {required - set(record.keys())}"
        # Empty trace → all boundaries absent → truthful None + incomplete.
        assert record["reconciliation_status"] == "incomplete"
        assert record["prefill_total_ms"] is None
        assert record["queue_ms"] is None
        assert record["readiness_ms"] is None
        assert record["encode_ms"] is None
        assert record["completion_ms"] is None
        assert record["request_wait_ms"] is None
        assert record["unattributed_ms"] is None
        assert record["encoded_count"] is None
        assert record["terminal_event"] is None
        assert record["torch_available"] is False

    def test_missing_boundaries_are_truthful_none(self):
        # Submission + worker start only: worker never completed.
        # mono_ns values are in nanoseconds (1_000_000 ns == 1 ms).
        trace = _FakeTrace([
            _FakeEvent(mp._EVENT_SUBMISSION, 1_000_000),
            _FakeEvent(mp._EVENT_WORKER_START, 2_000_000),
        ])
        record = mp.build_clip_prefill_reconciliation(
            trace, outcome="fallback_unavailable", request_id="partial"
        )
        assert record["prefill_total_ms"] is None     # no terminal event
        assert record["queue_ms"] == 1.0              # submission→worker start exists
        assert record["readiness_ms"] is None         # never reached
        assert record["encode_ms"] is None
        assert record["completion_ms"] is None
        assert record["reconciliation_status"] == "incomplete"

    def test_overlap_detected_when_children_exceed_total(self):
        # Deliberately overlapping stage boundaries: encode spans across
        # readiness; the computed accounting error is negative and surfaced.
        # Values in nanoseconds (1_000_000 == 1ms).
        trace = _FakeTrace([
            _FakeEvent(mp._EVENT_SUBMISSION, 0),
            _FakeEvent(mp._EVENT_WORKER_START, 0),
            _FakeEvent(mp._EVENT_READINESS_START, 1_000_000),
            _FakeEvent(mp._EVENT_READINESS_END, 100_000_000),
            _FakeEvent(mp._EVENT_ENCODE_START, 2_000_000),
            _FakeEvent(mp._EVENT_ENCODE_END, 200_000_000),
            _FakeEvent(mp._EVENT_COMPLETED, 210_000_000, {"encoded_count": 1}),
        ])
        record = mp.build_clip_prefill_reconciliation(
            trace, outcome="consumed", request_id="overlap"
        )
        assert record["reconciliation_status"] == "overlap", record
        assert record["unattributed_ms"] is not None and record["unattributed_ms"] < -50.0

    def test_queue_ms_is_wall_only_cross_thread(self):
        """Queue phase crosses threads: thread CPU is truthfully None."""
        counters = mp._capture_phase_counters()
        counters["native_tid"] = 111  # request thread snapshot
        trace = _FakeTrace([
            _FakeEvent(mp._EVENT_SUBMISSION, 1_000_000),
            _FakeEvent(mp._EVENT_WORKER_START, 2_000_000, {"counters": counters}),
            _FakeEvent(mp._EVENT_COMPLETED, 3_000_000, {"encoded_count": 0}),
        ])
        record = mp.build_clip_prefill_reconciliation(trace, outcome="consumed")
        # worker_native_tid reflects the worker-side snapshot (no fabricated 0).
        assert record["worker_native_tid"] == 111
        # Queue is measured by wall clock only; readiness/encode never started.
        assert record["queue_ms"] == 1.0


# ── Coordinator queue depth / pending lane count ───────────────────────


class TestCoordinatorLaneCounters:
    """Real queue depth / pending lane count at submission and worker
    start — read-only observability that never alters execution."""

    def test_counters_start_at_zero_and_drain_to_zero(self):
        bridge = mp.V2LoaderBridge(max_workers=1)
        assert bridge.coordinator.queue_depth() == 0
        assert bridge.coordinator.pending_lane_count() == 0
        bridge.coordinator.close()
        assert bridge.coordinator.queue_depth() == 0
        assert bridge.coordinator.pending_lane_count() == 0

    def test_queue_depth_does_not_alter_execution(self):
        unet_gate = threading.Event()
        encode_calls: list[str] = []

        def slow_unet(key: Any) -> str:
            unet_gate.wait(timeout=5)
            return "unet-done"

        def tracking_encode(class_name: str, kwargs: dict[str, Any]) -> tuple[str, ...]:
            encode_calls.append(kwargs.get("text", ""))
            return (f"conditioning:{kwargs['text']}",)

        bridge = _build_bridge(
            unet_loader=slow_unet,
            invoke_original=tracking_encode,
            max_workers=1,  # unet blocks the only worker → clip+prefill queue
        )
        trace = RuntimeTrace(request_id="attr-queue-depth", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)
        prep = bridge._preparation
        assert prep is not None

        time.sleep(0.2)  # let unet occupy the single worker
        # Real counters reflect the blocked state.
        assert bridge.coordinator.pending_lane_count() >= 2
        assert bridge.coordinator.queue_depth() >= 1

        # Scheduling prefill into a deep queue must still succeed.
        assert bridge.schedule_execution_prefill(trace=trace) is True
        assert prep.prefill_future is not None

        # Release the gate: everything drains and prefill completes.
        unet_gate.set()
        results = _wait_future(prep.prefill_future, timeout=5)
        assert results is not None and len(results) == 1
        assert encode_calls == ["a happy cat"]

        # All lanes drained back to zero.
        assert bridge.coordinator.queue_depth() == 0
        assert bridge.coordinator.pending_lane_count() == 0

        # Submission event carries real integer counters.
        submitted = _event_meta(trace, "preload_submitted")
        ep_submitted = [
            m for m in submitted if m.get("lane") == "execution_prefill"
        ]
        assert len(ep_submitted) == 1
        assert isinstance(ep_submitted[0].get("queue_depth"), int)
        assert isinstance(ep_submitted[0].get("pending_lane_count"), int)

        # Worker-start event carries real integer counters.
        worker_started = _event_meta(trace, "preload_worker_started")
        ep_ws = [m for m in worker_started if m.get("lane") == "execution_prefill"]
        assert len(ep_ws) >= 1
        assert isinstance(ep_ws[0].get("queue_depth"), int)
        assert isinstance(ep_ws[0].get("pending_lane_count"), int)

        bridge.coordinator.close()

    def test_diagnostic_snapshot_exposes_real_pending_lane_count(self):
        unet_gate = threading.Event()

        def slow_unet(key: Any) -> str:
            unet_gate.wait(timeout=5)
            return "unet-done"

        bridge = _build_bridge(unet_loader=slow_unet, max_workers=1)
        trace = RuntimeTrace(request_id="attr-snapshot", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)
        time.sleep(0.2)

        snap = bridge.diagnostic_snapshot()
        assert snap["executor_exists"] is True
        # pending_lane_count is now the real tracked value (>= 1 while unet
        # is blocked), never the old unconditional None.
        assert isinstance(snap["pending_lane_count"], int)
        assert snap["pending_lane_count"] >= 1

        unet_gate.set()
        prep = bridge._preparation
        assert prep is not None
        _wait_future(prep.unet_future, timeout=5)
        _wait_future(prep.clip_future, timeout=5)
        time.sleep(0.1)
        snap2 = bridge.diagnostic_snapshot()
        assert snap2["pending_lane_count"] == 0
        bridge.coordinator.close()


# ── Phase counter capture / deltas ─────────────────────────────────────


class TestPhaseCounterCapture:
    """_capture_phase_counters / _phase_counter_deltas reuse the existing
    RUSAGE_THREAD and /proc helpers and report truthfully when unavailable."""

    def test_snapshot_has_all_keys(self):
        snap = mp._capture_phase_counters()
        for key in (
            "mono_ns", "thread_time_ns", "process_time_ns", "native_tid",
            "native_thread_count", "rusage", "io", "torch",
        ):
            assert key in snap, f"missing {key}"
        assert isinstance(snap["mono_ns"], int)
        assert isinstance(snap["native_tid"], int)
        assert isinstance(snap["native_thread_count"], int)
        # torch counts are best-effort: bool availability flag + None counts
        # when torch is absent (tests must not need GPU/torch).
        assert isinstance(snap["torch"]["torch_available"], bool)
        assert snap["torch"].get("torch_intraop_threads") is None or isinstance(
            snap["torch"].get("torch_intraop_threads"), int
        )
        assert snap["torch"].get("torch_interop_threads") is None or isinstance(
            snap["torch"].get("torch_interop_threads"), int
        )

    def test_same_thread_deltas(self):
        before = mp._capture_phase_counters()
        time.sleep(0.02)
        after = mp._capture_phase_counters()
        deltas = mp._phase_counter_deltas(before, after)
        assert deltas["wall_ms"] is not None and deltas["wall_ms"] > 0
        # Same native thread → thread CPU is a number (may be tiny for sleep).
        assert deltas["thread_cpu_ms"] is not None
        assert isinstance(deltas["thread_cpu_ms"], float)
        assert isinstance(deltas["process_cpu_ms"], float)
        # Linux-native rusage deltas are present when the platform supports
        # RUSAGE_THREAD; otherwise truthful None — never fabricated zeros.
        assert "minor_faults" in deltas
        assert "voluntary_context_switches" in deltas
        assert "involuntary_context_switches" in deltas

    def test_cross_thread_thread_cpu_is_none(self):
        before = mp._capture_phase_counters()
        before["native_tid"] = 1000
        after = mp._capture_phase_counters()
        after["native_tid"] = 2000
        deltas = mp._phase_counter_deltas(before, after)
        assert deltas["wall_ms"] is not None
        assert deltas["thread_cpu_ms"] is None, (
            "thread-bounded counters must be None across threads"
        )
        assert deltas["minor_faults"] is None
        assert deltas["voluntary_context_switches"] is None

    def test_missing_snapshots_yield_empty_deltas(self):
        assert mp._phase_counter_deltas(None, None) == {}
        assert mp._phase_counter_deltas(mp._capture_phase_counters(), None) == {}
