"""RED behavioural tests: Studio live progress — LocalRemoteInvoker stream_event_sink → scheduler wiring.

Fixtures use the ACTUAL ``comfyapp.run_prompt_stream`` event schema:

  - status:  ``{type: 'status', phase: 'restore', message: 'Restoring container'}`` (flat)
  - node:    ``{type: 'progress', event: 'executing', data: {node: '7', prompt_id: '...'}}``
  - sampler: ``{type: 'progress', event: 'progress', data: {value: 5, max: 20, ...}}``
  - error:   ``{type: 'error', message: '...'}`` (flat)
  - result:  ``{type: 'result', data: {...}}``

All tests MUST fail against current production code (RED stage).
Do NOT modify production code or existing tests.
"""

import asyncio
import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Test infrastructure helpers
# ---------------------------------------------------------------------------

def _load_module(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel_path)
    assert spec is not None, f"Could not find spec for {rel_path}"
    assert spec.loader is not None, f"Could not find loader for {rel_path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures — ACTUAL comfyapp.run_prompt_stream event schema
# ---------------------------------------------------------------------------

def _default_status_sequence():
    """Return a realistic sequence matching the actual run_prompt_stream yield points.

    Actual comfyapp.py yields (see run_prompt_stream lines 20114–20564):
      - status flat:  ``{'type': 'status', 'phase': '...', 'message': '...'}``
      - progress sub: ``{'type': 'progress', 'event': <ev>, 'data': {...}}``
      - error flat:   ``{'type': 'error', 'message': '...'}``
      - result:       ``{'type': 'result', 'data': {...}}``
    """
    return [
        # Flat status — no "data" wrapper (actual schema!)
        {"type": "status", "phase": "restore", "message": "Restoring container"},
        # Progress sub-event for executing node
        {"type": "progress", "event": "executing", "data": {"node": "7", "prompt_id": "p_abc"}},
        # Progress sub-event for sampler step
        {"type": "progress", "event": "progress", "data": {"value": 5, "max": 20, "prompt_id": "p_abc", "node": "7"}},
        # Another status (warmup phase)
        {"type": "status", "phase": "warmup", "message": "Warming up..."},
        # Result
        {
            "type": "result",
            "data": {
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "output.png", "data": "cHJvZ3Jlc3NfdGVzdF9pbWFnZV9kYXRh"}
                        ]
                    }
                },
                "trace": {
                    "deltas_ms": {"sampler": 6400.0, "clip_encode": 800.0},
                    "derived_ms": {"sampler_ms": 6400.0},
                    "stages": {"t6_sampler_start": 1_000_000.0},
                    "trace_version": "2.0.0",
                },
            },
        },
    ]


def _default_status_sequence_with_unrelated():
    """Like _default_status_sequence but includes unrelated events
    (execution_start, execution_cached) that the mapper MUST skip."""
    seq = _default_status_sequence()
    # Insert unrelated events between status and executing
    seq.insert(1, {"type": "progress", "event": "execution_start", "data": {"prompt_id": "p_abc"}})
    seq.insert(3, {"type": "progress", "event": "execution_cached", "data": {"nodes": ["3", "5"], "prompt_id": "p_abc"}})
    return seq


def _workflow_node_count(workflow: dict) -> int:
    """Return the number of runnable nodes in a workflow dict (excludes
    group nodes, reroute nodes, and nodes without class_type)."""
    return sum(1 for v in workflow.values()
               if isinstance(v, dict) and v.get("class_type"))


class FakeRunPromptStream:
    """Async generator yielding ACTUAL run_prompt_stream event schema."""

    def __init__(self, sequence: list | None = None):
        self._sequence = sequence or _default_status_sequence()

    async def __call__(self, **kwargs):
        for event in self._sequence:
            yield event


class FakeRunPromptStreamWithUnrelated(FakeRunPromptStream):
    """Like FakeRunPromptStream but includes unrelated execution_start and
    execution_cached events that should be skipped."""

    def __init__(self):
        super().__init__(_default_status_sequence_with_unrelated())


class FakeRunPromptStreamWithError:
    """Terminates with a flat error (actual schema), no data wrapper."""

    def __init__(self):
        self._sequence = [
            {"type": "status", "phase": "restore", "message": "Restoring container"},
            {"type": "progress", "event": "executing", "data": {"node": "7", "prompt_id": "p_abc"}},
            {"type": "progress", "event": "progress", "data": {"value": 3, "max": 20, "prompt_id": "p_abc", "node": "7"}},
            {"type": "error", "message": "CUDA out of memory"},  # flat error, no data wrapper
        ]

    async def __call__(self, **kwargs):
        for event in self._sequence:
            yield event


# ---------------------------------------------------------------------------
# Placeholder mapper stub — currently no-op, must fail RED
# ---------------------------------------------------------------------------

def _desired_map_stream_message(msg: dict, context: dict) -> dict | None:
    """Placeholder — RED stub returning None for everything.

    This SHOULD map ACTUAL comfyapp.run_prompt_stream event shapes to
    experiment.worker.progress / experiment.event payloads, but currently
    returns None (no-op) so all mapping tests fail.
    """
    return None


# ---------------------------------------------------------------------------
# 1. LocalRemoteInvoker stream_event_sink contract
# ---------------------------------------------------------------------------

_FAKE_WORKFLOW = {
    "3": {"class_type": "KSampler", "inputs": {"seed": 42}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
    "9": {"class_type": "SaveImage", "inputs": {"images": []}},
}
_FAKE_WORKFLOW_NODE_COUNT = _workflow_node_count(_FAKE_WORKFLOW)  # 3


class LocalRemoteInvokerStreamSinkTests(unittest.TestCase):
    """RED: LocalRemoteInvoker must relay non-terminal events through
    stream_event_sink using the ACTUAL comfyapp event schema."""

    def setUp(self):
        self.runner_mod = _load_module("experiment_runner", "experiment_runner.py")

    # ── Test 1: all nonterminal events relayed ─────────────────────────

    def test_stream_event_sink_receives_nonterminal_events(self):
        """RED: status (flat), progress/executing, progress/progress events
        are relayed through the sink using actual schema shapes."""
        received: list[dict] = []

        async def sink(event: dict):
            received.append(event)

        stream = FakeRunPromptStream()
        invoker = self.runner_mod.LocalRemoteInvoker(
            stream,
            experiment_id="exp_live_1",
            stream_event_sink=sink,
        )
        cell = {
            "cell_key": "cell_live_1",
            "checkpoint_id": "ck_live_1",
            "attempt_id": "a_live_1",
            "_resolved_workflow": dict(_FAKE_WORKFLOW),
            "trace": {"t0_client_press": 1000.0},
        }
        result = _run(invoker.run_cell("w_1", cell))

        # 2 status + 1 cell.executing + 1 sampler.step = 4 nonterminal events
        status_events = [e for e in received if e.get("type") == "status"]
        executing_events = [e for e in received if e.get("type") == "cell.executing"]
        step_events = [e for e in received if e.get("type") == "sampler.step"]

        self.assertGreaterEqual(len(status_events), 2,
                                "Status events must be relayed through sink")
        self.assertEqual(len(executing_events), 1,
                         "cell.executing event must be relayed through sink")
        self.assertEqual(len(step_events), 1,
                         "sampler.step event must be relayed through sink")

        # Status events carry phase and message from flat status payload
        for ev in status_events:
            self.assertIn("phase", ev,
                          "Status event must carry phase from flat status")
            self.assertIn("message", ev,
                          "Status event must carry message from flat status")

        # Executing event carries node from progress/executing data
        self.assertEqual(executing_events[0].get("node"), "7",
                         "cell.executing must carry node ID")

        # Sampler.step event carries value→step and max
        self.assertEqual(step_events[0].get("step"), 5,
                         "sampler.step must map value→step")
        self.assertEqual(step_events[0].get("max"), 20,
                         "sampler.step must carry max")

        # All events get context
        for ev in received:
            self.assertIn("experiment_id", ev)
            self.assertIn("checkpoint_id", ev)
            self.assertIn("cell_key", ev)
            self.assertIn("attempt_id", ev)

    # ── Test 2: unrelated events skipped ───────────────────────────────

    def test_unrelated_events_skipped(self):
        """RED: execution_start, execution_cached (progress sub-events)
        must NOT appear in the sink — only status, executing, progress."""
        received: list[dict] = []

        async def sink(event: dict):
            received.append(event)

        stream = FakeRunPromptStreamWithUnrelated()
        invoker = self.runner_mod.LocalRemoteInvoker(
            stream,
            experiment_id="exp_live_1b",
            stream_event_sink=sink,
        )
        cell = {
            "cell_key": "cell_live_1b",
            "checkpoint_id": "ck_live_1b",
            "attempt_id": "a_live_1b",
            "_resolved_workflow": dict(_FAKE_WORKFLOW),
        }
        result = _run(invoker.run_cell("w_1", cell))

        # No event should carry execution_start or execution_cached
        for ev in received:
            self.assertNotEqual(ev.get("type"), "execution_start",
                                "execution_start must NOT appear in sink")
            self.assertNotEqual(ev.get("type"), "execution_cached",
                                "execution_cached must NOT appear in sink")
            # Also check sub-event field isn't leaked
            self.assertNotIn("event", ev,
                             "Raw sub-event field must not leak into sink")

        # Still get the real events
        self.assertGreaterEqual(len(received), 4,
                                "Real events must still be relayed despite unrelated noise")

    # ── Test 3: result NOT forwarded ───────────────────────────────────

    def test_result_not_in_sink(self):
        """RED: The 'result' message must NOT reach the sink."""
        received: list[dict] = []

        async def sink(event: dict):
            received.append(event)

        stream = FakeRunPromptStream()
        invoker = self.runner_mod.LocalRemoteInvoker(
            stream,
            experiment_id="exp_live_2",
            stream_event_sink=sink,
        )
        cell = {
            "cell_key": "cell_live_2",
            "checkpoint_id": "ck_live_2",
            "attempt_id": "a_live_2",
            "_resolved_workflow": dict(_FAKE_WORKFLOW),
            "trace": {"t0_client_press": 1000.0},
        }
        result = _run(invoker.run_cell("w_1", cell))

        result_in_sink = [e for e in received if e.get("type") == "result"]
        self.assertEqual(len(result_in_sink), 0,
                         "'result' must NOT appear in stream_event_sink")
        self.assertEqual(result.get("status"), "completed")
        self.assertIn("output_paths", result)
        self.assertIn("timing_payload", result)

    # ── Test 4: no base64 in sink ──────────────────────────────────────

    def test_sink_does_not_journal_base64(self):
        """RED: No base64-encoded image data reaches the sink."""
        received: list[dict] = []

        async def sink(event: dict):
            received.append(event)

        stream = FakeRunPromptStream()
        invoker = self.runner_mod.LocalRemoteInvoker(
            stream,
            experiment_id="exp_live_3",
            stream_event_sink=sink,
        )
        cell = {
            "cell_key": "cell_live_3",
            "checkpoint_id": "ck_live_3",
            "attempt_id": "a_live_3",
            "_resolved_workflow": dict(_FAKE_WORKFLOW),
        }
        result = _run(invoker.run_cell("w_1", cell))

        import re
        b64_pattern = re.compile(r'^[A-Za-z0-9+/=]{20,}$')

        def _check_no_base64(obj, path=""):
            if isinstance(obj, str):
                if len(obj) > 20 and b64_pattern.match(obj):
                    self.fail(f"Base64 found in sink at {path}: {obj[:30]}...")
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    _check_no_base64(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    _check_no_base64(v, f"{path}[{i}]")

        for ev in received:
            _check_no_base64(ev)

        if result.get("result") and result["result"].get("outputs"):
            outputs_str = json.dumps(result["result"]["outputs"])
            self.assertIn("cHJvZ3Jlc3NfdGVzdF9pbWFnZV9kYXRh", outputs_str,
                          "Base64 must be preserved in result dict")

    # ── Test 5: sequence numbers monotonic ────────────────────────────

    def test_sink_events_have_sequence_hint(self):
        """RED: Each sink event carries a monotonic sequence integer."""
        received: list[dict] = []

        async def sink(event: dict):
            received.append(event)

        stream = FakeRunPromptStream()
        invoker = self.runner_mod.LocalRemoteInvoker(
            stream,
            experiment_id="exp_live_4",
            stream_event_sink=sink,
        )
        cell = {
            "cell_key": "cell_live_4",
            "checkpoint_id": "ck_live_4",
            "attempt_id": "a_live_4",
            "_resolved_workflow": dict(_FAKE_WORKFLOW),
        }
        result = _run(invoker.run_cell("w_1", cell))

        for i, ev in enumerate(received):
            self.assertIn("sequence", ev,
                          f"Sink event {i} must carry sequence")
            self.assertIsInstance(ev["sequence"], int,
                                  f"Sink event {i} sequence must be int")
        sequences = [e["sequence"] for e in received]
        self.assertEqual(sequences, sorted(sequences),
                         "Sink event sequences must be monotonic")

    # ── Test 6: total_nodes in worker payload ──────────────────────────

    def test_sink_events_carry_total_nodes(self):
        """RED: Each sink event carries a ``total_nodes`` field derived
        from the resolved workflow's runnable node count."""
        received: list[dict] = []

        async def sink(event: dict):
            received.append(event)

        stream = FakeRunPromptStream()
        invoker = self.runner_mod.LocalRemoteInvoker(
            stream,
            experiment_id="exp_live_tn",
            stream_event_sink=sink,
        )
        cell = {
            "cell_key": "cell_live_tn",
            "checkpoint_id": "ck_live_tn",
            "attempt_id": "a_live_tn",
            "_resolved_workflow": dict(_FAKE_WORKFLOW),
        }
        result = _run(invoker.run_cell("w_1", cell))

        self.assertGreater(len(received), 0,
                           "Sink must receive events")
        for ev in received:
            self.assertIn("total_nodes", ev,
                          "Each sink event must carry total_nodes")
            self.assertEqual(ev["total_nodes"], _FAKE_WORKFLOW_NODE_COUNT,
                             f"total_nodes should be {_FAKE_WORKFLOW_NODE_COUNT}, "
                             f"got {ev.get('total_nodes')}")


# ---------------------------------------------------------------------------
# 2. Studio adapter / scheduler wiring
# ---------------------------------------------------------------------------

class StudioSchedulerWiringTests(unittest.TestCase):
    """RED: _schedule_and_start wires a stream_event_sink that broadcasts."""

    def setUp(self):
        self.adapter = _load_module("studio_run_adapter", "studio_run_adapter.py")
        self.runner_mod = _load_module("experiment_runner", "experiment_runner.py")

    # ── Test 7: sink wired in source ───────────────────────────────────

    def test_schedule_and_start_wires_stream_event_sink(self):
        """RED: _schedule_and_start source contains stream_event_sink wiring."""
        import inspect
        source = inspect.getsource(self.adapter._schedule_and_start)
        self.assertIn(
            "stream_event_sink",
            source,
            "_schedule_and_start MUST pass stream_event_sink to LocalRemoteInvoker",
        )

    # ── Test 8: experiment.worker.progress referenced in source ─────────

    def test_experiment_worker_progress_referenced(self):
        """RED: _schedule_and_start source references experiment.worker.progress."""
        import inspect
        source = inspect.getsource(self.adapter._schedule_and_start)
        self.assertIn(
            "experiment.worker.progress",
            source,
            "_schedule_and_start must broadcast experiment.worker.progress",
        )

    # ── Test 9: sink produces correct event types ──────────────────────

    def test_sink_maps_status_to_experiment_worker_progress(self):
        """RED: With actual schema events, the sink chain produces
        experiment.worker.progress for status/cell.executing/sampler.step."""
        broadcaster_events: list[tuple[str, dict]] = []

        async def fake_broadcaster(event_type: str, detail: dict):
            broadcaster_events.append((event_type, detail))

        async def sink(event: dict):
            msg_type = event.get("type", "")
            if msg_type == "status":
                await fake_broadcaster("experiment.worker.progress", {
                    "experiment_id": event.get("experiment_id", ""),
                    "type": "status",
                    "phase": event.get("phase", ""),
                    "message": event.get("message", ""),
                })
            elif msg_type == "cell.executing":
                await fake_broadcaster("experiment.worker.progress", {
                    "experiment_id": event.get("experiment_id", ""),
                    "type": "cell.executing",
                    "node": event.get("node", ""),
                })
            elif msg_type == "sampler.step":
                await fake_broadcaster("experiment.worker.progress", {
                    "experiment_id": event.get("experiment_id", ""),
                    "type": "sampler.step",
                    "step": event.get("step"),
                    "max": event.get("max"),
                })

        invoker = self.runner_mod.LocalRemoteInvoker(
            FakeRunPromptStream(),
            experiment_id="exp_wiring_1",
            stream_event_sink=sink,
        )
        cell = {
            "cell_key": "cell_wiring_1",
            "checkpoint_id": "ck_wiring_1",
            "attempt_id": "a_wiring_1",
            "_resolved_workflow": dict(_FAKE_WORKFLOW),
        }
        result = _run(invoker.run_cell("w_1", cell))

        event_types = [et for et, _ in broadcaster_events]
        self.assertIn("experiment.worker.progress", event_types,
                      "Broadcaster must receive experiment.worker.progress")
        self.assertGreaterEqual(len(broadcaster_events), 4,
                                "Expected at least 4 UI events")

        status_events = [(et, d) for et, d in broadcaster_events if d.get("type") == "status"]
        self.assertGreaterEqual(len(status_events), 2)
        for _, d in status_events:
            self.assertIn("phase", d)
            self.assertIn("message", d)

        executing_events = [(et, d) for et, d in broadcaster_events if d.get("type") == "cell.executing"]
        self.assertEqual(len(executing_events), 1)
        self.assertEqual(executing_events[0][1].get("node"), "7")

        progress_events = [(et, d) for et, d in broadcaster_events if d.get("type") == "sampler.step"]
        self.assertEqual(len(progress_events), 1)
        self.assertEqual(progress_events[0][1].get("step"), 5)
        self.assertEqual(progress_events[0][1].get("max"), 20)

    # ── Test 10: lifecycle-only experiment.event ────────────────────────

    def test_experiment_event_for_durable_lifecycle_only(self):
        """RED: experiment.event is separate from stream_event_sink."""
        import inspect
        adapter_source = inspect.getsource(self.adapter._schedule_and_start)
        self.assertIn("experiment.worker.progress", adapter_source)
        sink_count = adapter_source.count("stream_event_sink")
        self.assertGreater(
            sink_count, 0,
            "_schedule_and_start must wire a stream_event_sink",
        )


# ---------------------------------------------------------------------------
# 3. Failure test — progress then flat error
# ---------------------------------------------------------------------------

class LocalRemoteInvokerFailureProgressTests(unittest.TestCase):
    """RED: Flat error from actual schema preserves partial timing."""

    def setUp(self):
        self.runner_mod = _load_module("experiment_runner", "experiment_runner.py")

    # ── Test 11: flat error still fails ────────────────────────────────

    def test_flat_error_preserves_failure(self):
        """RED: A flat error (actual schema: no data wrapper) still
        produces a failed result, not a completion."""
        stream = FakeRunPromptStreamWithError()
        invoker = self.runner_mod.LocalRemoteInvoker(
            stream,
            experiment_id="exp_fail_1",
        )
        cell = {
            "cell_key": "cell_fail_1",
            "checkpoint_id": "ck_fail_1",
            "attempt_id": "a_fail_1",
            "_resolved_workflow": dict(_FAKE_WORKFLOW),
        }
        result = _run(invoker.run_cell("w_1", cell))

        self.assertEqual(result.get("status"), "failed",
                         "Flat error must yield failed result")
        self.assertIn("error", result,
                      "Failed result must carry error message")
        # The actual schema error message is flat: msg.get("message")
        # Current code checks msg.get("data",{}).get("message") which
        # won't match — so this assertion will demonstrate the schema gap.
        self.assertEqual(result.get("error"), "CUDA out of memory",
                         "Flat error message must be preserved verbatim")

    # ── Test 12: flat error with partial timing ─────────────────────────

    def test_flat_error_retains_partial_timing_if_available(self):
        """RED: If the flat error carries timing data, it is preserved."""
        async def stream_with_partial_timing(**kwargs):
            yield {"type": "status", "phase": "restore", "message": "Starting..."}
            yield {"type": "progress", "event": "executing", "data": {"node": "7", "prompt_id": "p_abc"}}
            yield {"type": "progress", "event": "progress", "data": {"value": 3, "max": 20}}
            # Flat error with partial timing payload (actual schema puts
            # timing on the error at top level or in a trace sub-payload)
            yield {"type": "error", "message": "Sampler crashed"}

        invoker = self.runner_mod.LocalRemoteInvoker(
            stream_with_partial_timing,
            experiment_id="exp_fail_2",
        )
        cell = {
            "cell_key": "cell_fail_2",
            "checkpoint_id": "ck_fail_2",
            "attempt_id": "a_fail_2",
            "_resolved_workflow": dict(_FAKE_WORKFLOW),
        }
        result = _run(invoker.run_cell("w_1", cell))

        self.assertEqual(result.get("status"), "failed")
        # Flat error message must be preserved
        self.assertIn("error", result)
        self.assertNotEqual(result.get("error"), "")
        self.assertNotIn("output_paths", result,
                         "Failed result must NOT include output_paths")

    # ── Test 13: flat error-only stream ─────────────────────────────────

    def test_flat_error_does_not_fabricate_completion(self):
        """RED: Flat error must not fabricate a completion."""
        async def error_only_stream(**kwargs):
            yield {"type": "error", "message": "Immediate failure"}

        invoker = self.runner_mod.LocalRemoteInvoker(
            error_only_stream,
            experiment_id="exp_fail_3",
        )
        cell = {
            "cell_key": "cell_fail_3",
            "checkpoint_id": "ck_fail_3",
            "attempt_id": "a_fail_3",
            "_resolved_workflow": dict(_FAKE_WORKFLOW),
        }
        result = _run(invoker.run_cell("w_1", cell))

        self.assertEqual(result.get("status"), "failed")
        self.assertNotIn("output_paths", result)
        self.assertIn("error", result)
        # Flat error means msg["message"] directly, not nested
        self.assertEqual(result.get("error"), "Immediate failure",
                         "Flat error message must be preserved verbatim")


# ---------------------------------------------------------------------------
# 4. Normaliser contract — ACTUAL schema shapes
# ---------------------------------------------------------------------------

class RemoteStreamNormaliserContractTests(unittest.TestCase):
    """RED: _desired_map_stream_message must map ACTUAL event shapes."""

    def setUp(self):
        import experiment_runner as _er
        self._map = _er._desired_map_stream_message

    # ── Test 14: flat status → experiment.worker.progress ─────────────

    def test_maps_flat_status_to_worker_progress(self):
        """RED: Flat status (actual schema) maps to experiment.worker.progress."""
        context = {
            "experiment_id": "exp_map_1",
            "checkpoint_id": "ck_map_1",
            "cell_key": "cell_map_1",
            "attempt_id": "a_map_1",
        }
        # Actual schema: flat, no "data" wrapper
        msg = {"type": "status", "phase": "restore", "message": "Restoring container"}
        result = self._map(msg, context)

        self.assertIsNotNone(result,
                             "Flat status must map to a UI event (not None)")
        self.assertEqual(result.get("event"), "experiment.worker.progress",
                         "Status must produce experiment.worker.progress")
        detail = result.get("detail", {})
        self.assertEqual(detail.get("type"), "status")
        self.assertEqual(detail.get("phase"), "restore")
        self.assertEqual(detail.get("message"), "Restoring container")
        for k, v in context.items():
            self.assertEqual(detail.get(k), v)

    # ── Test 15: progress/executing → cell.executing ──────────────────

    def test_maps_progress_executing_to_cell_executing(self):
        """RED: progress/executing (actual schema) maps to cell.executing."""
        context = {
            "experiment_id": "exp_map_2",
            "checkpoint_id": "ck_map_2",
            "cell_key": "cell_map_2",
            "attempt_id": "a_map_2",
        }
        # Actual schema: type=progress, event=executing, data.node
        msg = {
            "type": "progress",
            "event": "executing",
            "data": {"node": "7", "prompt_id": "p_abc"},
        }
        result = self._map(msg, context)

        self.assertIsNotNone(result,
                             "progress/executing must map to UI event")
        self.assertEqual(result.get("event"), "experiment.worker.progress",
                         "progress/executing must produce experiment.worker.progress")
        detail = result.get("detail", {})
        self.assertEqual(detail.get("type"), "cell.executing",
                         "Must map to cell.executing type")
        self.assertEqual(detail.get("node"), "7",
                         "Node must be extracted from data.node")

    # ── Test 16: progress/progress → sampler.step ─────────────────────

    def test_maps_progress_progress_to_sampler_step(self):
        """RED: progress/progress (actual schema) maps value→step/max."""
        context = {
            "experiment_id": "exp_map_3",
            "checkpoint_id": "ck_map_3",
            "cell_key": "cell_map_3",
            "attempt_id": "a_map_3",
        }
        # Actual schema: type=progress, event=progress, data.value
        msg = {
            "type": "progress",
            "event": "progress",
            "data": {"value": 5, "max": 20, "prompt_id": "p_abc", "node": "7"},
        }
        result = self._map(msg, context)

        self.assertIsNotNone(result,
                             "progress/progress must map to UI event")
        self.assertEqual(result.get("event"), "experiment.worker.progress")
        detail = result.get("detail", {})
        self.assertEqual(detail.get("type"), "sampler.step")
        # value mapped to step, max preserved
        self.assertEqual(detail.get("step"), 5,
                         "data.value must map to step")
        self.assertEqual(detail.get("max"), 20,
                         "data.max must be preserved")

    # ── Test 17: progress/execution_start → None (skipped) ─────────────

    def test_maps_execution_start_to_none(self):
        """RED: progress/execution_start must return None (unrelated)."""
        context = {"experiment_id": "exp_map_es", "checkpoint_id": "", "cell_key": "", "attempt_id": ""}
        msg = {"type": "progress", "event": "execution_start", "data": {"prompt_id": "p_abc"}}
        result = self._map(msg, context)
        self.assertIsNone(result,
                          "execution_start must NOT produce any UI event")

    # ── Test 18: progress/execution_cached → None (skipped) ────────────

    def test_maps_execution_cached_to_none(self):
        """RED: progress/execution_cached must return None (unrelated)."""
        context = {"experiment_id": "exp_map_ec", "checkpoint_id": "", "cell_key": "", "attempt_id": ""}
        msg = {"type": "progress", "event": "execution_cached", "data": {"nodes": ["3", "5"]}}
        result = self._map(msg, context)
        self.assertIsNone(result,
                          "execution_cached must NOT produce any UI event")

    # ── Test 19: flat error → cell.failed experiment.event ─────────────

    def test_maps_flat_error_to_cell_failed(self):
        """RED: Flat error (actual schema) maps to experiment.event
        with type=cell.failed, preserving the exact message."""
        context = {
            "experiment_id": "exp_map_5",
            "checkpoint_id": "ck_map_5",
            "cell_key": "cell_map_5",
            "attempt_id": "a_map_5",
        }
        # Actual schema: flat, no data wrapper
        msg = {"type": "error", "message": "CUDA out of memory"}
        result = self._map(msg, context)

        self.assertIsNotNone(result,
                             "Flat error must map to UI event")
        self.assertEqual(result.get("event"), "experiment.event",
                         "Error must produce experiment.event")
        detail = result.get("detail", {})
        self.assertEqual(detail.get("type"), "cell.failed",
                         "Error must map to cell.failed")
        self.assertEqual(detail.get("message"), "CUDA out of memory",
                         "Flat error message must be preserved verbatim")

    # ── Test 20: result → None ────────────────────────────────────────

    def test_maps_result_to_none(self):
        """RED: result message returns None (not forwarded)."""
        msg = {"type": "result", "data": {"outputs": {}}}
        result = self._map(msg, {})
        self.assertIsNone(result)

    # ── Test 21: unknown type → None ──────────────────────────────────

    def test_maps_unknown_type_to_none(self):
        """RED: Unknown message type returns None (graceful skip)."""
        msg = {"type": "unknown_event_type", "data": {}}
        result = self._map(msg, {})
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# 5. Constructor contract
# ---------------------------------------------------------------------------

class StreamEventSinkConstructorTests(unittest.TestCase):
    """RED: LocalRemoteInvoker must accept stream_event_sink kwarg."""

    def setUp(self):
        self.runner_mod = _load_module("experiment_runner", "experiment_runner.py")

    def test_local_remote_invoker_accepts_stream_event_sink_kwarg(self):
        """RED: Constructor signature includes stream_event_sink."""
        import inspect
        sig = inspect.signature(self.runner_mod.LocalRemoteInvoker.__init__)
        self.assertIn("stream_event_sink", sig.parameters,
                      "LocalRemoteInvoker.__init__ must accept stream_event_sink kwarg")

    def test_stream_event_sink_defaults_to_none(self):
        """RED: stream_event_sink defaults to None (backward compat)."""
        invoker = self.runner_mod.LocalRemoteInvoker(
            lambda **kw: iter([]),
            experiment_id="exp_def",
        )
        self.assertIsNone(invoker._stream_event_sink,
                          "stream_event_sink must default to None")


if __name__ == "__main__":
    unittest.main()
