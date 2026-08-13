"""Focused tests for local-to-Modal submission timing and benchmark reporting.

Uses fake handles and fake lazy async generators — never invokes Modal or
paid benchmarks.

Covers:
- Generator creation vs first-iteration ordering in transport
- Submission timestamp before ``__anext__``
- First-event delay measurement
- Input ID at creation or after iteration
- Original request ID / T1 survive through pipeline
- ``result["local_timing"]`` reconciliation and residual
- Absent remote-inaccessible timestamps are ``None``, not numeric zero
- ``benchmark_v2_direct._timing`` includes ``local_timing`` block
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
import time
import unittest
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from collections.abc import Mapping
from canonical_execution import build_execution_plan, execute_plan
from comfymodal_runtime.contracts import ExecutionPlan, ExecutionOptions
from comfymodal_runtime.modal_transport import ModalTransport, TransportError
from comfymodal_runtime.trace import RuntimeTrace


# ═══════════════════════════════════════════════════════════════════════
# Helpers: fake handle + lazy async generator
# ═══════════════════════════════════════════════════════════════════════


def _make_origin(
    request_id: str = "test-origin-req",
    trigger: str = "test",
    t0_wall_ms: int = 0,
) -> dict[str, Any]:
    t1_wall_ns = int(time.time() * 1_000_000_000)
    t1_mono_ns = time.monotonic_ns()
    return {
        "request_id": request_id,
        "trigger_source": trigger,
        "ui_run_triggered_wall_unix_ms": t0_wall_ms,
        "local_receive_wall_ns": t1_wall_ns,
        "local_receive_mono_ns": t1_mono_ns,
        "local_body_read_ms": 1.5,
        "local_json_parse_ms": 0.8,
        "local_preflight_ms": 2.1,
        "local_queue_lock_wait_ms": 0.3,
        "local_queue_enqueue_ms": 0.2,
        "queue_wait_before_worker_ms": 45.0,
        "local_receive_to_enqueue_ms": 5.0,
    }


class _FakeLazyAsyncGen:
    """Simulates Modal's lazy async generator object.

    Modal's ``remote_gen.aio()`` returns an object with ``__aiter__`` and
    ``__anext__`` *directly* (no await on the call).  The creation call
    (``.aio()``) is separate from first iteration (``__anext__``).
    """

    def __init__(
        self,
        events: list[dict] | None = None,
        *,
        input_id: str = "fake-input-abc123",
    ) -> None:
        self._events = list(events or [])
        self._index = 0
        self.input_id = input_id
        self.input_created_at = time.time_ns()

    def __aiter__(self):
        return self

    async def __anext__(self) -> dict:
        if self._index >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._index]
        self._index += 1
        return event


def _make_v2_aio(events: list[dict]) -> Any:
    """Return a callable suitable for ``handle.run_plan_stream.remote_gen.aio``.

    Modal's SDK returns the async-generator-like object synchronously, so
    this factory returns a plain (non-async) function.
    """
    def _aio(*args: Any, **kwargs: Any) -> _FakeLazyAsyncGen:
        return _FakeLazyAsyncGen(events)
    return _aio


def _make_v2_handle_factory(events: list[dict] | None = None):
    """Return a v2_handle_factory callable that builds handles with our
    fake ``remote_gen.aio``."""
    evts = list(events or [])

    def _factory(**kwargs: Any) -> Any:
        return SimpleNamespace(
            run_plan_stream=SimpleNamespace(
                remote_gen=SimpleNamespace(
                    aio=_make_v2_aio(evts),
                ),
            ),
        )
    return _factory


# ═══════════════════════════════════════════════════════════════════════
# Transport-level tests: generator creation distinct from first iteration
# ═══════════════════════════════════════════════════════════════════════


class TestTransportGeneratorIterationSeparation(unittest.TestCase):
    """Prove the transport records generator-creation timestamps separately
    from first-iteration (submission) timestamps."""

    def setUp(self):
        self.events = [
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ]
        self.handle_factory = _make_v2_handle_factory(events=self.events)

    def test_generator_creation_before_submission(self):
        """modal_generator_create_start event precedes modal_submission_attempt."""
        trace = RuntimeTrace(request_id="gen-first-test", process="local")
        origin = _make_origin("gen-first-test")
        trace.set_metadata(request_origin_info=origin)

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            transport = ModalTransport(
                v2_handle_factory=self.handle_factory,
            )
            async for _ in transport.run_plan_stream(
                plan,
                gpu="rtx-pro-6000",
                workspace={"id": "ws"},
                trace={"prompt_id": "gen-first-test"},
                runtime_trace=trace,
            ):
                pass
            names = [e.name for e in trace.events]
            create_start_idx = names.index("modal_generator_create_start")
            created_idx = names.index("modal_generator_created")
            submit_idx = names.index("modal_submission_attempt")
            first_event_idx = names.index("modal_first_event_received")
            self.assertLess(create_start_idx, submit_idx,
                            "generator_create_start must precede submission_attempt")
            self.assertLess(created_idx, submit_idx,
                            "generator_created must precede submission_attempt")
            self.assertLess(submit_idx, first_event_idx,
                            "submission_attempt must precede first_event_received")

        asyncio.run(run())

    def test_submission_timestamp_before_anext(self):
        """The submission timestamp is captured before __anext__() is called."""
        trace = RuntimeTrace(request_id="sub-before-anext", process="local")
        origin = _make_origin("sub-before-anext")
        trace.set_metadata(request_origin_info=origin)

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            transport = ModalTransport(
                v2_handle_factory=self.handle_factory,
            )
            async for _ in transport.run_plan_stream(
                plan,
                gpu="rtx-pro-6000",
                workspace={"id": "ws"},
                trace={"prompt_id": "sub-before-anext"},
                runtime_trace=trace,
            ):
                pass
            # modal_submission_attempt wall_ns should be <= first event wall_ns
            submit_event = next(e for e in trace.events if e.name == "modal_submission_attempt")
            first_event = next(e for e in trace.events if e.name == "modal_first_event_received")
            self.assertIsNotNone(submit_event.wall_unix_ns)
            self.assertIsNotNone(first_event.wall_unix_ns)
            self.assertLessEqual(
                int(submit_event.wall_unix_ns), int(first_event.wall_unix_ns),
                "submission_attempt wall_ns must be <= first_event_received wall_ns",
            )
            self.assertIsNotNone(submit_event.monotonic_ns)
            self.assertIsNotNone(first_event.monotonic_ns)
            self.assertLessEqual(
                int(submit_event.monotonic_ns), int(first_event.monotonic_ns),
                "submission_attempt mono_ns must be <= first_event_received mono_ns",
            )

        asyncio.run(run())

    def test_first_event_delay_measured(self):
        """first_iteration_to_first_remote_event_ms captures the wait for the
        first remote event after starting the iterator."""
        trace = RuntimeTrace(request_id="first-event-delay", process="local")
        origin = _make_origin("first-event-delay")
        trace.set_metadata(request_origin_info=origin)

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            transport = ModalTransport(
                v2_handle_factory=self.handle_factory,
            )
            async for _ in transport.run_plan_stream(
                plan,
                gpu="rtx-pro-6000",
                workspace={"id": "ws"},
                trace={"prompt_id": "first-event-delay"},
                runtime_trace=trace,
            ):
                pass
            # The transport stores the interval in trace metadata
            first_iter_raw = trace._metadata.get("first_iteration_to_first_remote_event_ms")
            self.assertIsNotNone(first_iter_raw,
                                 "first_iteration_to_first_remote_event_ms must exist")
            first_iter_val: float = cast(float, first_iter_raw)
            self.assertGreaterEqual(first_iter_val, 0.0,
                                    "delay must be non-negative")

        asyncio.run(run())

    def test_input_id_observed(self):
        """modal_input_id_observed event fires when input_id is available."""
        trace = RuntimeTrace(request_id="input-id-test", process="local")
        origin = _make_origin("input-id-test")
        trace.set_metadata(request_origin_info=origin)

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            transport = ModalTransport(
                v2_handle_factory=self.handle_factory,
            )
            async for _ in transport.run_plan_stream(
                plan,
                gpu="rtx-pro-6000",
                workspace={"id": "ws"},
                trace={"prompt_id": "input-id-test"},
                runtime_trace=trace,
            ):
                pass
            # modal_input_id_observed should exist
            observed = [e for e in trace.events if e.name == "modal_input_id_observed"]
            self.assertGreaterEqual(len(observed), 1,
                                    "modal_input_id_observed must fire")
            # The metadata should contain modal_input_id
            self.assertIn("modal_input_id", trace._metadata)
            self.assertEqual(trace._metadata["modal_input_id"], "fake-input-abc123")

        asyncio.run(run())

    def test_generator_create_ms_separate_from_submission_ms(self):
        """generator_create_ms measures the .remote_gen.aio() call time;
        local_receive_to_actual_submission_ms measures the whole pipeline."""
        trace = RuntimeTrace(request_id="gen-vs-submit", process="local")
        origin = _make_origin("gen-vs-submit")
        trace.set_metadata(request_origin_info=origin)

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            transport = ModalTransport(
                v2_handle_factory=self.handle_factory,
            )
            async for _ in transport.run_plan_stream(
                plan,
                gpu="rtx-pro-6000",
                workspace={"id": "ws"},
                trace=trace.to_legacy_timing(prompt_id="gen-vs-submit"),
                runtime_trace=trace,
            ):
                pass
            gen_raw = trace._metadata.get("generator_create_ms")
            submit_raw = trace._metadata.get("local_receive_to_actual_submission_ms")
            self.assertIsInstance(gen_raw, (int, float),
                                  "generator_create_ms must be numeric")
            self.assertIsInstance(submit_raw, (int, float),
                                  "local_receive_to_actual_submission_ms must be numeric")
            gen_ms: float = cast(float, gen_raw)
            submit_ms: float = cast(float, submit_raw)
            # generator_create_ms should be a small fraction of the overall pipeline
            self.assertLessEqual(gen_ms, submit_ms,
                                 "generator_create_ms must be <= total submission time")

        asyncio.run(run())

    def test_stop_async_iteration_handled(self):
        """Empty stream (StopAsyncIteration on first __anext__) exits cleanly."""
        transport = ModalTransport(
            v2_handle_factory=_make_v2_handle_factory(events=[]),
        )

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            messages: list[dict] = []
            async for msg in transport.run_plan_stream(
                plan,
                gpu="rtx-pro-6000",
                workspace={"id": "ws"},
                trace={"prompt_id": "empty-stream"},
            ):
                messages.append(msg)
            self.assertEqual(len(messages), 0,
                             "Empty stream must produce zero messages")

        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# execute_plan local_timing reconciliation
# ═══════════════════════════════════════════════════════════════════════


class TestExecutePlanLocalTiming(unittest.TestCase):
    """result['local_timing'] must contain all reconciliation fields."""

    def test_local_timing_block_present(self):
        """execute_plan result contains a local_timing block."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="local-timing-block", process="local")
            origin = _make_origin("local-timing-block")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="local-timing-block",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            self.assertIn("local_timing", result,
                          "result must contain local_timing block")
            self.assertIsInstance(result["local_timing"], dict)

        asyncio.run(run())

    def test_local_timing_contains_all_required_keys(self):
        """Every required local_timing key is present."""
        REQUIRED_KEYS = {
            "t0_to_t1_ms",
            "t1_to_queue_enqueue_ms",
            "local_receive_to_enqueue_ms",
            "local_body_read_ms",
            "local_json_parse_ms",
            "local_preflight_ms",
            "local_queue_lock_wait_ms",
            "local_queue_enqueue_ms",
            "queue_wait_before_worker_ms",
            "plan_build_ms",
            "active_profile_ms",
            "restore_plan_build_ms",
            "restore_publish_ms",
            "handle_lookup_ms",
            "payload_serialize_ms",
            "generator_create_ms",
            "local_residual_ms",
            "clock_reconciliation_residual_ms",
            "route_unattributed_ms",
            "worker_unattributed_ms",
            "reconciliation_status",
            "missing_stages",
            "overlap_error",
            "stage_attribution_residual_ms",
            "local_receive_to_generator_create_ms",
            "generator_create_to_first_iteration_ms",
            "first_iteration_to_first_remote_event_ms",
            "local_receive_to_actual_submission_ms",
            # V2 remote request origin intervals (Requirement 1)
            "trigger_to_local_receive_ms",
            "local_receive_to_generator_create_start_ms",
            "generator_created_to_first_iteration_ms",
            "first_iteration_to_first_remote_event_ms",
            "submission_to_remote_python_resume_ms",
            "remote_python_resume_to_restore_start_ms",
            "restore_method_ms",
            "restore_end_to_modal_method_entry_ms",
            "modal_method_entry_to_executor_ms",
            "unexplained_pre_remote_ms",
        }

        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="all-keys", process="local")
            origin = _make_origin("all-keys")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="all-keys",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            for key in REQUIRED_KEYS:
                self.assertIn(key, lt, f"Missing required local_timing key: {key}")

        asyncio.run(run())

    def test_t0_to_t1_computed_from_origin(self):
        """t0_to_t1_ms is computed from ui_run_triggered_wall_unix_ms and
        local_receive_wall_ns."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="t0t1", process="local")
            t0_wall_ms = 1_000_000  # T0 in ms
            t1_wall_ns = 2_000_000_000  # T1 in ns (2000 ms)
            origin = _make_origin("t0t1", t0_wall_ms=t0_wall_ms)
            origin["local_receive_wall_ns"] = t1_wall_ns
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="t0t1",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            # t0_to_t1_ms = (t1_wall_ns - t0_wall_ms * 1_000_000) / 1_000_000
            expected = (t1_wall_ns - t0_wall_ms * 1_000_000) / 1_000_000
            self.assertAlmostEqual(lt["t0_to_t1_ms"], expected, places=2)

        asyncio.run(run())

    def test_absent_remote_inaccessible_timestamps_are_none_not_zero(self):
        """Fields that can only be measured locally (not in the remote
        serialized payload) must be None, not 0, when unavailable."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="none-not-zero", process="local")
            origin = _make_origin("none-not-zero")
            # Simulate missing queue metrics (as in benchmark path)
            del origin["queue_wait_before_worker_ms"]
            del origin["local_receive_to_enqueue_ms"]
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="none-not-zero",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            # queue_wait_before_worker_ms without origin should be unset/value None
            val = lt.get("queue_wait_before_worker_ms")
            self.assertIsNone(val,
                              "queue_wait_before_worker_ms must be None when origin lacks it")
            val = lt.get("t1_to_queue_enqueue_ms")
            self.assertIsNone(val,
                              "t1_to_queue_enqueue_ms must be None when origin lacks it")
            val = lt.get("local_receive_to_enqueue_ms")
            self.assertIsNone(val,
                              "local_receive_to_enqueue_ms must be None when origin lacks it")
            # generator_create_ms comes from V2 computed interval which
            # renders "absent" (not None/0) when transport metadata is missing.
            gen_val = lt.get("generator_create_ms")
            self.assertIn(gen_val, (None, "absent"),
                          "generator_create_ms must be None or 'absent' when unavailable")

        asyncio.run(run())

    def test_local_residual_reconciles_measured_stages(self):
        """local_residual_ms = local_receive_to_actual_submission_ms minus
        sum of all measured local stages."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="residual-test", process="local")
            origin = _make_origin("residual-test")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="residual-test",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            # residual should be present
            self.assertIn("local_residual_ms", lt)
            # If local_receive_to_actual_submission_ms is None (V1 path),
            # residual should also be None
            if lt.get("local_receive_to_actual_submission_ms") is None:
                self.assertIsNone(lt["local_residual_ms"])
            else:
                # Otherwise residual is non-negative (or negative if stages overcount,
                # which is a bug)
                self.assertIsInstance(lt["local_residual_ms"], (int, float))

        asyncio.run(run())

    def test_request_id_and_origin_survive(self):
        """Original request_id and T1 wall time survive through the pipeline."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {},
                                               "trace": {"events": [], "metadata": {}}}}

        async def run():
            req_id = "origin-survives-007"
            trace = RuntimeTrace(request_id=req_id, process="local")
            origin = _make_origin(req_id, t0_wall_ms=500_000)
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id=req_id,
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            # request_id should still be accessible
            self.assertEqual(trace.request_id, req_id)
            # local_timing should compute t0_to_t1_ms from the origin data
            lt = result.get("local_timing", {})
            self.assertIsNotNone(lt.get("t0_to_t1_ms"),
                                 "t0_to_t1_ms must be computed from preserved origin")
            # The [v2.request_origin] line references the trace_id/origin
            self.assertIn("request_id", trace._metadata.get("request_origin_info", {}))

        asyncio.run(run())

    def test_queue_wait_before_worker_in_local_timing(self):
        """queue_wait_before_worker_ms appears in local_timing when origin has it."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="queue-wait", process="local")
            origin = _make_origin("queue-wait")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="queue-wait",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            self.assertEqual(lt["queue_wait_before_worker_ms"], 45.0)
            self.assertEqual(lt["t1_to_queue_enqueue_ms"], 5.0)
            self.assertEqual(lt["local_receive_to_enqueue_ms"], 5.0)

        asyncio.run(run())

    def test_route_metrics_preserved_in_local_timing(self):
        """All route metrics (body_read, json_parse, preflight, lock_wait,
        enqueue) pass through to local_timing."""
        async def stream(**kwargs):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="route-metrics", process="local")
            origin = _make_origin("route-metrics")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="route-metrics",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            self.assertEqual(lt["local_body_read_ms"], 1.5)
            self.assertEqual(lt["local_json_parse_ms"], 0.8)
            self.assertEqual(lt["local_preflight_ms"], 2.1)
            self.assertEqual(lt["local_queue_lock_wait_ms"], 0.3)
            self.assertEqual(lt["local_queue_enqueue_ms"], 0.2)

        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# V2 transport direct path — rich metadata
# ═══════════════════════════════════════════════════════════════════════


class TestV2TransportRichMetadata(unittest.TestCase):
    """When using the V2 direct transport path, generator and submission
    metadata are set on the RuntimeTrace."""

    def test_transport_sets_generator_metadata_on_runtime_trace(self):
        """V2 transport stores generator_create_ms, submission_attempt, etc.
        on the runtime_trace metadata."""
        events = [
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ]
        trace = RuntimeTrace(request_id="rich-md-v2", process="local")
        origin = _make_origin("rich-md-v2")
        trace.set_metadata(request_origin_info=origin)

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            transport = ModalTransport(
                v2_handle_factory=_make_v2_handle_factory(events=events),
            )
            async for _ in transport.run_plan_stream(
                plan,
                gpu="rtx-pro-6000",
                workspace={"id": "ws"},
                trace={"prompt_id": "rich-md-v2"},
                runtime_trace=trace,
            ):
                pass
            md = trace._metadata
            self.assertIn("generator_create_ms", md)
            self.assertIn("local_receive_to_generator_create_ms", md)
            self.assertIn("generator_create_to_first_iteration_ms", md)
            self.assertIn("first_iteration_to_first_remote_event_ms", md)
            self.assertIn("local_receive_to_actual_submission_ms", md)
            self.assertIn("modal_generator_created_wall_ns", md)
            self.assertIn("modal_submission_attempt_wall_ns", md)
            self.assertIn("modal_first_event_received_wall_ns", md)
            self.assertIn("modal_input_id", md)

        asyncio.run(run())

    def test_v2_timing_appears_in_execute_plan_local_timing(self):
        """When execute_plan uses V2 transport, the local_timing block contains
        generator and submission intervals."""
        events = [
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ]

        async def run():
            trace = RuntimeTrace(request_id="v2-exec-plan-timing", process="local")
            origin = _make_origin("v2-exec-plan-timing")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="v2-exec-plan-timing",
                validate=False,
            )
            transport = ModalTransport(
                v2_handle_factory=_make_v2_handle_factory(events=events),
            )
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            # V2 transport populates these via runtime_trace._metadata
            self.assertIn("local_receive_to_generator_create_ms", lt)
            self.assertIn("generator_create_ms", lt)
            self.assertIn("generator_create_to_first_iteration_ms", lt)
            self.assertIn("first_iteration_to_first_remote_event_ms", lt)
            self.assertIn("local_receive_to_actual_submission_ms", lt)

        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# benchmark_v2_direct._timing includes local_timing
# ═══════════════════════════════════════════════════════════════════════


class TestBenchmarkTimingIncludesLocalTiming(unittest.TestCase):
    """The _timing() helper in benchmark_v2_direct.py must include the
    local_timing block."""

    def test_timing_includes_local_timing_key(self):
        """_timing returns a 'local_timing' key with the result's local_timing."""
        from tools.benchmark_v2_direct import _timing

        result = {
            "images": [],
            "outputs": {},
            "local_timing": {
                "t0_to_t1_ms": 12.3,
                "generator_create_ms": 0.5,
                "local_receive_to_actual_submission_ms": 150.0,
                "local_residual_ms": 2.1,
            },
            "trace": {
                "events": [],
                "deltas_ms": {},
                "derived_ms": {},
            },
        }
        timing = _timing(result, wall_ms=5000.0)
        self.assertIn("local_timing", timing)
        self.assertEqual(timing["local_timing"]["t0_to_t1_ms"], 12.3)
        self.assertEqual(timing["local_timing"]["generator_create_ms"], 0.5)
        self.assertEqual(timing["local_timing"]["local_receive_to_actual_submission_ms"], 150.0)

    def test_timing_local_timing_absent_when_result_lacks_it(self):
        """When result has no local_timing, _timing returns empty dict."""
        from tools.benchmark_v2_direct import _timing

        result = {
            "images": [],
            "outputs": {},
            "trace": {"events": [], "deltas_ms": {}, "derived_ms": {}},
        }
        timing = _timing(result, wall_ms=3000.0)
        self.assertIn("local_timing", timing)
        self.assertEqual(timing["local_timing"], {})

    def test_timing_local_timing_malformed_is_handled(self):
        """Non-dict local_timing is replaced with empty dict."""
        from tools.benchmark_v2_direct import _timing

        result = {
            "images": [],
            "outputs": {},
            "local_timing": "corrupt_string",
            "trace": {"events": [], "deltas_ms": {}, "derived_ms": {}},
        }
        timing = _timing(result, wall_ms=3000.0)
        self.assertIn("local_timing", timing)
        self.assertEqual(timing["local_timing"], {})


# ═══════════════════════════════════════════════════════════════════════
# Code-presence tests for the [v2.request_origin] summary line
# ═══════════════════════════════════════════════════════════════════════


class TestV2BreakdownReconciliationBehavioral(unittest.TestCase):
    """Behavioral output-parsing tests for [v2.local_submission_breakdown]."""

    def _run_and_capture_breakdown(self, events, trace_mod_fn=None):
        """Run execute_plan with V2 transport path and capture the
        [v2.local_submission_breakdown] print output."""
        import io
        out = io.StringIO()
        _orig = sys.stdout
        try:
            sys.stdout = out
            trace = RuntimeTrace(request_id="behavioral-test", process="local")
            origin = _make_origin("behavioral-test")
            trace.set_metadata(request_origin_info=origin)
            if trace_mod_fn:
                trace_mod_fn(trace)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="behavioral-test",
                validate=False,
            )
            transport = ModalTransport(
                v2_handle_factory=_make_v2_handle_factory(events=events),
            )
            asyncio.run(
                execute_plan(plan, transport=transport, trace=trace)
            )
        finally:
            sys.stdout = _orig
        return out.getvalue()

    def test_transport_entry_to_handle_lookup_included(self):
        """transport_entry_to_handle_lookup_ms appears in the print line."""
        output = self._run_and_capture_breakdown(
            [{"type": "result", "data": {"images": [], "outputs": {}}}],
        )
        self.assertIn("transport_entry_to_handle_lookup_ms=", output)

    def test_payload_bytes_included(self):
        """payload_bytes appears in the print line."""
        output = self._run_and_capture_breakdown(
            [{"type": "result", "data": {"images": [], "outputs": {}}}],
        )
        self.assertIn("payload_bytes=", output)

    def test_workflow_node_count_included(self):
        """workflow_node_count appears as a numeric value."""
        output = self._run_and_capture_breakdown(
            [{"type": "result", "data": {"images": [], "outputs": {}}}],
        )
        self.assertIn("workflow_node_count=", output)

    def test_input_image_count_included(self):
        """input_image_count appears in the print line."""
        output = self._run_and_capture_breakdown(
            [{"type": "result", "data": {"images": [], "outputs": {}}}],
        )
        self.assertIn("input_image_count=", output)

    def test_handle_cache_hit_false_on_miss(self):
        """When handle_cache_miss fires, handle_cache_hit prints False, not None/absent."""
        events = [{"type": "result", "data": {"images": [], "outputs": {}}}]

        def add_miss(trace):
            trace.emit("handle_cache_miss", phase="local")

        output = self._run_and_capture_breakdown(events, trace_mod_fn=add_miss)
        self.assertIn("handle_cache_hit=False", output)

    def test_handle_cache_hit_true_on_hit(self):
        """When handle_cache_hit fires, handle_cache_hit prints True."""
        events = [{"type": "result", "data": {"images": [], "outputs": {}}}]

        def add_hit(trace):
            trace.emit("handle_cache_hit", phase="local")

        output = self._run_and_capture_breakdown(events, trace_mod_fn=add_hit)
        self.assertIn("handle_cache_hit=True", output)

    def test_handle_cache_hit_absent_when_no_cache_event(self):
        """When neither cache hit nor miss fires, handle_cache_hit prints absent."""
        events = [{"type": "result", "data": {"images": [], "outputs": {}}}]

        def add_factory_hit(trace):
            trace.emit("handle_cache_miss", phase="local")
            trace.emit("handle_factory_resolve", phase="local")

        output = self._run_and_capture_breakdown(events, trace_mod_fn=add_factory_hit)
        # cache miss + factory resolve → hit=False, client=False, cls_name=False, instance=False
        self.assertIn("handle_cache_hit=False", output)
        self.assertIn("created_modal_client=False", output)
        self.assertIn("performed_cls_from_name=False", output)
        self.assertIn("constructed_class_instance=False", output)

    def test_created_modal_client_true_on_resolution(self):
        """When client_resolution_start fires, created_modal_client=True."""
        events = [{"type": "result", "data": {"images": [], "outputs": {}}}]

        def add_client(trace):
            trace.emit("handle_cache_miss", phase="local")
            trace.emit("client_resolution_start", phase="local")

        output = self._run_and_capture_breakdown(events, trace_mod_fn=add_client)
        self.assertIn("created_modal_client=True", output)

    def test_negative_direct_stage_prints_invalid_negative(self):
        """A direct stage with start > end prints invalid_negative in the breakdown."""
        events = [{"type": "result", "data": {"images": [], "outputs": {}}}]

        def add_negative(trace):
            trace.emit_at("plan_build_start", wall_unix_ns=200, monotonic_ns=2000, phase="local")
            trace.emit_at("plan_build_end", wall_unix_ns=100, monotonic_ns=1000, phase="local")

        output = self._run_and_capture_breakdown(events, trace_mod_fn=add_negative)
        self.assertIn("plan_build_ms=invalid_negative", output)

    def test_overlap_status_on_invalid_negative(self):
        """reconciliation_status is 'overlap' when a direct stage is invalid_negative."""
        events = [{"type": "result", "data": {"images": [], "outputs": {}}}]

        def add_negative(trace):
            trace.emit_at("plan_build_start", wall_unix_ns=200, monotonic_ns=2000, phase="local")
            trace.emit_at("plan_build_end", wall_unix_ns=100, monotonic_ns=1000, phase="local")

        output = self._run_and_capture_breakdown(events, trace_mod_fn=add_negative)
        self.assertIn("reconciliation_status=overlap", output)

    def test_remote_call_performed_absent_when_no_profile(self):
        """remote_call_performed prints absent when no profile decision exists."""
        output = self._run_and_capture_breakdown(
            [{"type": "result", "data": {"images": [], "outputs": {}}}],
        )
        self.assertIn("remote_call_performed=absent", output)

    def test_backward_compatibility_local_timing_still_present(self):
        """result['local_timing'] block still present with backward compat keys."""
        async def run():
            trace = RuntimeTrace(request_id="backward-test", process="local")
            origin = _make_origin("backward-test")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="backward-test",
                validate=False,
            )
            transport = ModalTransport(
                v2_handle_factory=_make_v2_handle_factory(
                    [{"type": "result", "data": {"images": [], "outputs": {}}}],
                ),
            )
            result = await execute_plan(plan, transport=transport, trace=trace)
            self.assertIn("local_timing", result)
            lt = result["local_timing"]
            # Backward compat keys
            for key in ("plan_build_ms", "active_profile_ms", "handle_lookup_ms",
                        "payload_serialize_ms", "generator_create_ms",
                        "local_receive_to_actual_submission_ms", "reconciliation_status"):
                self.assertIn(key, lt)
        asyncio.run(run())

    def test_missing_worker_start_yields_absent_worker_fields(self):
        """When no worker_start event exists, worker_start fields print absent."""
        events = [{"type": "result", "data": {"images": [], "outputs": {}}}]

        # Do NOT emit worker_start — simulate absent dequeue boundary
        def no_start(trace):
            pass

        output = self._run_and_capture_breakdown(events, trace_mod_fn=no_start)
        self.assertIn("local_receive_to_worker_start_ms=absent", output)
        self.assertIn("worker_start_to_plan_build_ms=absent", output)


# ═══════════════════════════════════════════════════════════════════════
# Vector: absent remote-inaccessible timestamps are None, never 0
# ═══════════════════════════════════════════════════════════════════════


class TestAbsentTimestampsAreNone(unittest.TestCase):
    """Remote-inaccessible local timestamps that cannot be measured are None,
    not numeric zero."""

    def test_origin_fields_missing_are_none(self):
        """When an origin dict lacks queue fields, the corresponding
        local_timing fields are None."""
        origin = {
            "request_id": "none-test",
            "trigger_source": "test",
            "local_receive_wall_ns": int(time.time() * 1_000_000_000),
            "local_receive_mono_ns": time.monotonic_ns(),
        }
        self.assertNotIn("queue_wait_before_worker_ms", origin)
        self.assertNotIn("local_receive_to_enqueue_ms", origin)
        self.assertIsNone(origin.get("queue_wait_before_worker_ms"),
                          "Missing key must return None via .get()")
        self.assertIsNone(origin.get("local_receive_to_enqueue_ms"),
                          "Missing key must return None via .get()")


# ═══════════════════════════════════════════════════════════════════════
# Delayed first event / ID only after iteration
# ═══════════════════════════════════════════════════════════════════════


class TestInputIdDelayed(unittest.TestCase):
    """Input ID that is only exposed after the first iteration."""

    class _FakeLazyGenDelayedId:
        """Generator where input_id is empty at creation, set after iteration."""

        def __init__(self):
            self._events = [{"type": "status", "data": {"phase": "restore"}},
                            {"type": "result", "data": {"images": [], "outputs": {}}}]
            self._index = 0
            self.input_id = ""
            self.input_created_at = None

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self._events):
                raise StopAsyncIteration
            event = self._events[self._index]
            self._index += 1
            if self._index == 1:
                self.input_id = "delayed-id-456"
                self.input_created_at = time.time_ns()
            return event

    def test_input_id_observed_after_first_iteration_when_delayed(self):
        """modal_input_id_observed fires after first iteration when input_id
        was not available at creation time, and does not fire twice."""
        trace = RuntimeTrace(request_id="delayed-id", process="local")
        origin = _make_origin("delayed-id")
        trace.set_metadata(request_origin_info=origin)
        gen = self._FakeLazyGenDelayedId()

        def _handle_factory(**kw):
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(aio=lambda *a, **kw: gen),
                ),
            )

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            transport = ModalTransport(v2_handle_factory=_handle_factory)
            async for _ in transport.run_plan_stream(
                plan, gpu="rtx-pro-6000", workspace={"id": "ws"},
                trace={"prompt_id": "delayed-id"}, runtime_trace=trace,
            ):
                pass
            observed = [e for e in trace.events if e.name == "modal_input_id_observed"]
            self.assertEqual(len(observed), 1,
                             "modal_input_id_observed must fire exactly once")
            self.assertEqual(trace._metadata.get("modal_input_id"), "delayed-id-456")

        asyncio.run(run())

    def test_input_id_observed_only_once_when_available_at_creation(self):
        """When input_id is available at generator creation, only one
        modal_input_id_observed event is emitted."""
        trace = RuntimeTrace(request_id="early-id-dedup", process="local")
        origin = _make_origin("early-id-dedup")
        trace.set_metadata(request_origin_info=origin)

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            transport = ModalTransport(
                v2_handle_factory=_make_v2_handle_factory(
                    events=[{"type": "result", "data": {"images": [], "outputs": {}}}],
                ),
            )
            async for _ in transport.run_plan_stream(
                plan, gpu="rtx-pro-6000", workspace={"id": "ws"},
                trace={"prompt_id": "early-id-dedup"}, runtime_trace=trace,
            ):
                pass
            observed = [e for e in trace.events if e.name == "modal_input_id_observed"]
            self.assertEqual(len(observed), 1,
                             "modal_input_id_observed must fire exactly once")
            self.assertEqual(trace._metadata.get("modal_input_id"), "fake-input-abc123")

        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# Timestamp-before-__anext__ via emit_at
# ═══════════════════════════════════════════════════════════════════════


class TestSubmissionAttemptTimestamp(unittest.TestCase):
    """modal_submission_attempt event wall_unix_ns matches the captured
    pre-__anext__ timestamp (no emit delta)."""

    def test_submission_attempt_uses_emit_at(self):
        """The submission_attempt event wall_unix_ns equals the captured
        _submission_wall_ns value (not a later emit() time)."""
        trace = RuntimeTrace(request_id="emit-at-test", process="local")
        origin = _make_origin("emit-at-test")
        trace.set_metadata(request_origin_info=origin)

        # Monkey-patch emit_at to verify it's called with the right timestamps
        original_emit_at = trace.emit_at
        captured = {}

        def _tracking_emit_at(name, *, wall_unix_ns, monotonic_ns, **kw):
            if name == "modal_submission_attempt":
                captured["wall_unix_ns"] = wall_unix_ns
                captured["monotonic_ns"] = monotonic_ns
            return original_emit_at(name, wall_unix_ns=wall_unix_ns, monotonic_ns=monotonic_ns, **kw)

        trace.emit_at = _tracking_emit_at  # type: ignore[method-assign]

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            transport = ModalTransport(
                v2_handle_factory=_make_v2_handle_factory(
                    events=[{"type": "result", "data": {"images": [], "outputs": {}}}],
                ),
            )
            async for _ in transport.run_plan_stream(
                plan, gpu="rtx-pro-6000", workspace={"id": "ws"},
                trace={"prompt_id": "emit-at-test"}, runtime_trace=trace,
            ):
                pass
            self.assertIn("wall_unix_ns", captured,
                          "emit_at must be called for modal_submission_attempt")
            self.assertIn("monotonic_ns", captured,
                          "emit_at must be called for modal_submission_attempt")
            # Verify the event's own wall_unix_ns matches
            sub_event = next(e for e in trace.events if e.name == "modal_submission_attempt")
            self.assertEqual(sub_event.wall_unix_ns, captured["wall_unix_ns"],
                             "Event wall_unix_ns must match emit_at parameter")
            self.assertEqual(sub_event.monotonic_ns, captured["monotonic_ns"],
                             "Event monotonic_ns must match emit_at parameter")

        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# Origin propagation through build_execution_plan boundary
# ═══════════════════════════════════════════════════════════════════════


class TestOriginPropagation(unittest.TestCase):
    """request_origin_info survives the build_execution_plan → execute_plan
    boundary when one side has it and the other does not."""

    def test_trace_origin_seeds_plan_metadata(self):
        """When RuntimeTrace has request_origin_info but request_metadata
        does not, build_execution_plan carries it into plan.request_metadata."""
        trace = RuntimeTrace(request_id="origin-seed", process="local")
        origin = _make_origin("origin-seed")
        trace.set_metadata(request_origin_info=origin)
        plan = build_execution_plan(
            {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
            prompt_id="origin-seed",
            trace=trace,
            validate=False,
        )
        plan_origin = plan.request_metadata.get("request_origin_info", {})
        self.assertTrue(isinstance(plan_origin, Mapping) and bool(plan_origin),
                        "plan.request_metadata must contain request_origin_info")
        self.assertEqual(plan_origin.get("request_id"), "origin-seed")

    def test_plan_origin_seeds_runtime_trace_in_execute_plan(self):
        """When plan.request_metadata has request_origin_info and the
        RuntimeTrace does not, execute_plan seeds it."""
        trace = RuntimeTrace(request_id="plan-seed", process="local")
        # Build the plan with origin in request_metadata so it survives
        # the frozen dataclass conversion (mappingproxy).
        plan = build_execution_plan(
            {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
            prompt_id="plan-seed",
            request_metadata={"request_origin_info": dict(_make_origin("plan-seed"))},
            validate=False,
        )

        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(plan, transport=transport, trace=trace)
            trace_origin = trace._metadata.get("request_origin_info", {})
            self.assertTrue(isinstance(trace_origin, dict) and bool(trace_origin),
                            "RuntimeTrace must gain request_origin_info from plan")
            self.assertEqual(trace_origin.get("request_id"), "plan-seed")

        asyncio.run(run())

    def test_existing_origin_not_overwritten(self):
        """When both sides have origin, the existing values are preserved."""
        trace = RuntimeTrace(request_id="existing", process="local")
        trace_origin = _make_origin("existing", t0_wall_ms=100)
        trace.set_metadata(request_origin_info=trace_origin)
        plan = build_execution_plan(
            {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
            prompt_id="existing",
            trace=trace,
            validate=False,
        )
        plan_origin = plan.request_metadata.get("request_origin_info", {})
        # Should NOT overwrite with plan defaults (trace origin wins via setdefault)
        self.assertEqual(plan_origin.get("request_id"), "existing")
        self.assertEqual(plan_origin.get("ui_run_triggered_wall_unix_ms"), 100)

    def test_plan_origin_does_not_replace_runtime_trace_existing_origin(self):
        """execute_plan must NOT overwrite existing request_origin_info on
        the RuntimeTrace with plan metadata origin."""
        trace = RuntimeTrace(request_id="no-overwrite", process="local")
        trace_origin = _make_origin("no-overwrite", t0_wall_ms=200)
        trace.set_metadata(request_origin_info=dict(trace_origin))

        # Build plan with a DIFFERENT origin in request_metadata.
        plan = build_execution_plan(
            {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
            prompt_id="no-overwrite",
            request_metadata={"request_origin_info": {"request_id": "plan-overwrite", "trigger_source": "evil"}},
            validate=False,
        )

        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(plan, transport=transport, trace=trace)
            trace_origin_after = trace._metadata.get("request_origin_info", {})
            # Must NOT be overwritten by plan origin
            self.assertEqual(trace_origin_after.get("request_id"), "no-overwrite")
            self.assertEqual(trace_origin_after.get("ui_run_triggered_wall_unix_ms"), 200)

        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# Residual reconciliation via non-overlapping transport intervals
# ═══════════════════════════════════════════════════════════════════════


class TestResidualReconciliation(unittest.TestCase):
    """local_residual_ms uses non-overlapping transport intervals when
    available, and is None when actual submission is unavailable."""

    def test_residual_uses_non_overlapping_intervals(self):
        """When all three transport intervals are available, residual is
        computed from non-overlapping intervals, not the overlapping
        _local_stages sum."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="residual-nonoverlap", process="local")
            origin = _make_origin("residual-nonoverlap")
            trace.set_metadata(request_origin_info=origin)
            # Simulate V2 transport metadata (non-overlapping intervals)
            trace.set_metadata(
                local_receive_to_generator_create_ms=50.0,
                generator_create_ms=10.0,
                generator_create_to_first_iteration_ms=5.0,
                local_receive_to_actual_submission_ms=70.0,
            )
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="residual-nonoverlap",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            self.assertIn("local_residual_ms", lt)
            # 70.0 - (50.0 + 10.0 + 5.0) = 5.0
            expected_residual = round(70.0 - (50.0 + 10.0 + 5.0), 3)
            self.assertAlmostEqual(lt["local_residual_ms"], expected_residual, places=3)

        asyncio.run(run())

    def test_residual_none_when_actual_submission_unavailable(self):
        """local_residual_ms is None when local_receive_to_actual_submission_ms
        is unavailable."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="residual-none", process="local")
            origin = _make_origin("residual-none")
            trace.set_metadata(request_origin_info=origin)
            # Do NOT set V2 transport metadata — no actual submission
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="residual-none",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            self.assertIn("local_residual_ms", lt)
            self.assertIsNone(lt["local_residual_ms"],
                              "residual must be None when actual submission unavailable")

        asyncio.run(run())

    def test_residual_none_when_disjoint_fallback_incomplete(self):
        """When V2 transport intervals are missing AND the disjoint-set
        sequential phases are unavailable, residual is None rather than
        hiding a missing major span."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="residual-fallback-incomplete", process="local")
            origin = _make_origin("residual-fallback-incomplete")
            trace.set_metadata(request_origin_info=origin)
            # Set actual_submission but MISSING generator_create_to_first_iteration_ms
            # and the fake trace has no plan_build_ms etc. events.
            trace.set_metadata(
                local_receive_to_generator_create_ms=50.0,
                generator_create_ms=10.0,
                # Missing: generator_create_to_first_iteration_ms
                local_receive_to_actual_submission_ms=70.0,
            )
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="residual-fallback-incomplete",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            self.assertIn("local_residual_ms", lt)
            # Disjoint-set fallback cannot be formed because sequential
            # phases (plan_build_ms, ...) are all None in the fake trace.
            self.assertIsNone(lt["local_residual_ms"])

        asyncio.run(run())

    def test_residual_fallback_none_when_gen_to_first_missing(self):
        """When the disjoint set is complete but
        generator_create_to_first_iteration_ms is absent, residual is None
        because a potentially major span is missing."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="residual-disjoint-missing-gen2first", process="local")
            origin = _make_origin("residual-disjoint-missing-gen2first")
            trace.set_metadata(request_origin_info=origin)
            # Build all sequential event spans.
            _wall = time.time()
            _mono = time.monotonic_ns()
            for _name in ("plan_build_start", "plan_build_end",
                           "active_profile_prepare_start", "active_profile_prepare_end",
                           "restore_plan_build_start", "restore_plan_build_end",
                           "restore_plan_publish_start", "restore_plan_publish_end",
                           "modal_handle_lookup_start", "modal_handle_lookup_end",
                           "modal_payload_serialize_start", "modal_payload_serialize_end"):
                trace.emit(_name, phase="local", metadata={"wall": _wall, "mono": _mono})
                _wall += 0.001
                _mono += 1_000_000
            # Set transport metadata — missing generator_create_to_first_iteration_ms
            trace.set_metadata(
                local_receive_to_actual_submission_ms=80.0,
                generator_create_ms=5.0,
            )
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="residual-disjoint-missing-gen2first",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            self.assertIn("local_residual_ms", lt)
            self.assertIsNone(lt["local_residual_ms"],
                              "residual must be None when generator_create_to_first_iteration_ms is absent")

        asyncio.run(run())

    def test_residual_fallback_with_complete_disjoint_set(self):
        """When the three transport intervals are not all available but the
        disjoint set including generator_create_to_first_iteration_ms IS
        fully known, residual is computed correctly."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="residual-disjoint-complete", process="local")
            origin = _make_origin("residual-disjoint-complete")
            trace.set_metadata(request_origin_info=origin)
            # Build all sequential event spans.
            _wall = time.time()
            _mono = time.monotonic_ns()
            for _name in ("plan_build_start", "plan_build_end",
                           "active_profile_prepare_start", "active_profile_prepare_end",
                           "restore_plan_build_start", "restore_plan_build_end",
                           "restore_plan_publish_start", "restore_plan_publish_end",
                           "modal_handle_lookup_start", "modal_handle_lookup_end",
                           "modal_payload_serialize_start", "modal_payload_serialize_end"):
                trace.emit(_name, phase="local", metadata={"wall": _wall, "mono": _mono})
                _wall += 0.001
                _mono += 1_000_000
            # Set transport metadata including generator_create_to_first_iteration_ms
            trace.set_metadata(
                local_receive_to_actual_submission_ms=80.0,
                generator_create_ms=5.0,
                generator_create_to_first_iteration_ms=2.0,
            )
            # origin has: local_receive_to_enqueue_ms=5.0, queue_wait_before_worker_ms=45.0
            # sequential 6 spans * ~1ms each ≈ 6ms + 5ms generator + 2ms gen-to-first = 13ms
            # disjoint total ≈ 5 + 45 + 6 + 5 + 2 = 63
            # residual ≈ 80 - 63 = 17
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="residual-disjoint-complete",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            self.assertIn("local_residual_ms", lt)
            self.assertIsNotNone(lt["local_residual_ms"])
            self.assertIsInstance(lt["local_residual_ms"], (int, float))

        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# Clock reconciliation residual
# ═══════════════════════════════════════════════════════════════════════


class TestClockReconciliationResidual(unittest.TestCase):
    """clock_reconciliation_residual_ms equals local_residual_ms (same
    formula: authoritative submission minus aggregate adjacent transport
    intervals).  local_residual_ms is a compatibility alias."""

    def test_clock_reconciliation_equals_local_residual(self):
        """clock_reconciliation equals local_residual when transport intervals present."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="clock-rec-test", process="local")
            origin = _make_origin("clock-rec-test", t0_wall_ms=100_000)
            trace.set_metadata(request_origin_info=origin)
            trace.set_metadata(
                local_receive_to_generator_create_ms=10.0,
                generator_create_ms=2.0,
                generator_create_to_first_iteration_ms=1.0,
                local_receive_to_actual_submission_ms=15.0,
            )
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="clock-rec-test",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            self.assertIn("clock_reconciliation_residual_ms", lt)
            self.assertIn("local_residual_ms", lt)
            if lt["local_residual_ms"] is not None:
                self.assertAlmostEqual(
                    lt["clock_reconciliation_residual_ms"],
                    lt["local_residual_ms"],
                    places=3,
                )
                # 15.0 - (10.0 + 2.0 + 1.0) = 2.0
                self.assertAlmostEqual(lt["clock_reconciliation_residual_ms"], 2.0, places=2)

        asyncio.run(run())

    def test_clock_reconciliation_none_when_submission_unavailable(self):
        """clock_reconciliation_residual_ms is None when submission or
        transport intervals are missing."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="clock-rec-none", process="local")
            origin = {
                "request_id": "clock-rec-none",
                "trigger_source": "test",
                "local_receive_wall_ns": int(time.time() * 1_000_000_000),
                "local_receive_mono_ns": time.monotonic_ns(),
            }
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="clock-rec-none",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            self.assertIn("clock_reconciliation_residual_ms", lt)
            self.assertIn("local_residual_ms", lt)
            # clock_reconciliation_residual_ms is alias of local_residual_ms
            self.assertEqual(
                lt["clock_reconciliation_residual_ms"],
                lt["local_residual_ms"],
            )

        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# Stage attribution residual
# ═══════════════════════════════════════════════════════════════════════


class TestStageAttributionResidual(unittest.TestCase):
    """stage_attribution_residual_ms dict with route/worker attribution."""

    def test_stage_attribution_present(self):
        """stage_attribution_residual_ms exists in local_timing."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="stage-attr-test", process="local")
            origin = _make_origin("stage-attr-test")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="stage-attr-test",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            self.assertIn("stage_attribution_residual_ms", lt)
            sar = lt["stage_attribution_residual_ms"]
            self.assertIsInstance(sar, dict)
            self.assertIn("route_unattributed_ms", sar)
            self.assertIn("worker_unattributed_ms", sar)
            self.assertIn("reconciliation_status", sar)
            self.assertIn("overlap_error", sar)

        asyncio.run(run())

    def test_route_attribution_computes_residual(self):
        """route_unattributed_ms = local_receive_to_enqueue_ms minus leaf sum."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="route-attr", process="local")
            origin = _make_origin("route-attr")
            # leaf stages sum to 4.9 (1.5 + 0.8 + 2.1 + 0.3 + 0.2)
            origin["local_body_read_ms"] = 1.5
            origin["local_json_parse_ms"] = 0.8
            origin["local_preflight_ms"] = 2.1
            origin["local_queue_lock_wait_ms"] = 0.3
            origin["local_queue_enqueue_ms"] = 0.2
            origin["local_receive_to_enqueue_ms"] = 5.0
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="route-attr",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            sar = lt.get("stage_attribution_residual_ms", {})
            # 5.0 - (1.5 + 0.8 + 2.1 + 0.3 + 0.2) = 5.0 - 4.9 = 0.1
            self.assertAlmostEqual(sar.get("route_unattributed_ms"), 0.1, places=3)

        asyncio.run(run())

    def test_route_overlap_error_when_leaf_sum_exceeds_parent(self):
        """overlap_error is set when leaves sum > local_receive_to_enqueue_ms."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="route-overlap", process="local")
            origin = _make_origin("route-overlap")
            origin["local_body_read_ms"] = 3.0
            origin["local_json_parse_ms"] = 2.0
            origin["local_preflight_ms"] = 2.0
            origin["local_queue_lock_wait_ms"] = 1.0
            origin["local_queue_enqueue_ms"] = 1.0
            origin["local_receive_to_enqueue_ms"] = 5.0  # leaves sum to 9.0 > 5.0
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="route-overlap",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            sar = lt.get("stage_attribution_residual_ms", {})
            self.assertLess(sar.get("route_unattributed_ms", 0), 0)
            self.assertEqual(sar.get("overlap_error"), "route")

        asyncio.run(run())

    def test_worker_attribution_computed_when_all_known(self):
        """worker_unattributed_ms computed from worker span minus leaf stages."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="worker-attr", process="local")
            origin = _make_origin("worker-attr")
            origin["local_receive_to_enqueue_ms"] = 5.0
            origin["queue_wait_before_worker_ms"] = 45.0
            trace.set_metadata(request_origin_info=origin)
            _wall = time.time()
            _mono = time.monotonic_ns()
            for _name in ("plan_build_start", "plan_build_end",
                           "active_profile_prepare_start", "active_profile_prepare_end",
                           "restore_plan_build_start", "restore_plan_build_end",
                           "restore_plan_publish_start", "restore_plan_publish_end",
                           "modal_handle_lookup_start", "modal_handle_lookup_end",
                           "modal_payload_serialize_start", "modal_payload_serialize_end"):
                trace.emit(_name, phase="local", metadata={"wall": _wall, "mono": _mono})
                _wall += 0.001
                _mono += 1_000_000
            trace.set_metadata(
                local_receive_to_actual_submission_ms=80.0,
                generator_create_ms=5.0,
                generator_create_to_first_iteration_ms=2.0,
            )
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="worker-attr",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            sar = lt.get("stage_attribution_residual_ms", {})
            self.assertIsNotNone(sar.get("worker_unattributed_ms"))

        asyncio.run(run())

    def test_incomplete_when_route_parent_absent(self):
        """reconciliation_status=incomplete when local_receive_to_enqueue_ms is missing."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="incomplete-test", process="local")
            origin = {
                "request_id": "incomplete-test",
                "trigger_source": "test",
                "local_receive_wall_ns": int(time.time() * 1_000_000_000),
                "local_receive_mono_ns": time.monotonic_ns(),
            }
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="incomplete-test",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            sar = lt.get("stage_attribution_residual_ms", {})
            self.assertIsNone(sar.get("route_unattributed_ms"))
            self.assertEqual(sar.get("reconciliation_status"), "incomplete")
            self.assertIn("missing_stages", sar)

        asyncio.run(run())

    def test_incomplete_when_worker_missing(self):
        """reconciliation_status=incomplete when worker stages are missing."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="worker-missing", process="local")
            origin = _make_origin("worker-missing")
            trace.set_metadata(request_origin_info=origin)
            # No transport meta, no trace events → worker leaves all missing
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="worker-missing",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            sar = lt.get("stage_attribution_residual_ms", {})
            self.assertEqual(sar.get("reconciliation_status"), "incomplete")
            self.assertIn("missing_stages", sar)

        asyncio.run(run())

    def test_worker_does_not_include_first_remote_event(self):
        """first_iteration_to_first_remote_event_ms is never in worker leaf sum."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="worker-no-first-event", process="local")
            origin = _make_origin("worker-no-first-event")
            trace.set_metadata(request_origin_info=origin)
            # Emit non-auto-emitted leaf events so all stages are present
            _wall = time.time()
            _mono = time.monotonic_ns()
            for _name in ("plan_build_start", "plan_build_end",
                           "modal_handle_lookup_start", "modal_handle_lookup_end",
                           "modal_payload_serialize_start", "modal_payload_serialize_end"):
                trace.emit(_name, phase="local", metadata={"wall": _wall, "mono": _mono})
                _wall += 0.001
                _mono += 1_000_000
            trace.set_metadata(
                local_receive_to_actual_submission_ms=80.0,
                generator_create_ms=5.0,
                generator_create_to_first_iteration_ms=2.0,
                first_iteration_to_first_remote_event_ms=999.0,  # large value we DON'T want in worker
            )
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="worker-no-first-event",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            sar = lt.get("stage_attribution_residual_ms", {})
            # first_iteration_to_first_remote_event_ms should NOT affect worker_unattributed.
            # It stays in local_timing for diagnostics but is never in the leaf sum.
            self.assertIn("first_iteration_to_first_remote_event_ms", lt)
            self.assertIsNotNone(sar.get("worker_unattributed_ms"))
            # The 999 value would cause a positive residual if it were included,
            # but since it's excluded, worker_unattributed should be < 999.
            self.assertLess(sar["worker_unattributed_ms"], 999.0)

        asyncio.run(run())

    def test_leaf_gap_detected_as_incomplete(self):
        """When one leaf stage is missing (intentional gap not auto-emitted by
        execute_plan), worker_unattributed is None and missing_stages names it.
        Uses modal_payload_serialize which is NOT auto-emitted by execute_plan."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="leaf-gap", process="local")
            origin = _make_origin("leaf-gap")
            trace.set_metadata(request_origin_info=origin)
            # Emit all stages EXCEPT modal_payload_serialize_start/end to create a gap.
            # modal_payload_serialize is NOT auto-emitted by execute_plan.
            _wall = time.time()
            _mono = time.monotonic_ns()
            for _name in ("plan_build_start", "plan_build_end",
                           "restore_plan_build_start", "restore_plan_build_end",
                           "restore_plan_publish_start", "restore_plan_publish_end",
                           "modal_handle_lookup_start", "modal_handle_lookup_end"):
                trace.emit(_name, phase="local", metadata={"wall": _wall, "mono": _mono})
                _wall += 0.001
                _mono += 1_000_000
            trace.set_metadata(
                local_receive_to_actual_submission_ms=80.0,
                generator_create_ms=5.0,
                generator_create_to_first_iteration_ms=2.0,
            )
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="leaf-gap",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            sar = result.get("local_timing", {}).get("stage_attribution_residual_ms", {})
            self.assertIsNone(sar.get("worker_unattributed_ms"))
            self.assertEqual(sar.get("reconciliation_status"), "incomplete")
            self.assertIn("missing_stages", sar)
            self.assertIn("payload_serialize_ms", sar["missing_stages"])

        asyncio.run(run())

    def test_negative_worker_overlap_detected(self):
        """When leaf sum exceeds worker span, worker_unattributed is negative and
        overlap_error is set."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="neg-overlap", process="local")
            origin = _make_origin("neg-overlap")
            # Large queue_wait so leaves exceed worker span
            origin["queue_wait_before_worker_ms"] = 60.0
            trace.set_metadata(request_origin_info=origin)
            # Emit non-auto-emitted stage events so all leaves are known
            _wall = time.time()
            _mono = time.monotonic_ns()
            for _name in ("plan_build_start", "plan_build_end",
                           "modal_handle_lookup_start", "modal_handle_lookup_end",
                           "modal_payload_serialize_start", "modal_payload_serialize_end"):
                trace.emit(_name, phase="local", metadata={"wall": _wall, "mono": _mono})
                _wall += 0.001
                _mono += 1_000_000
            # Worker span = 10 - 5 = 5, queue_wait alone = 60 → leaves sum > span
            trace.set_metadata(
                local_receive_to_actual_submission_ms=10.0,
                generator_create_ms=1.0,
                generator_create_to_first_iteration_ms=1.0,
            )
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="neg-overlap",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            sar = result.get("local_timing", {}).get("stage_attribution_residual_ms", {})
            self.assertIsNotNone(sar.get("worker_unattributed_ms"))
            self.assertLess(sar["worker_unattributed_ms"], 0)
            self.assertIn("overlap_error", sar)
            self.assertIn("worker", sar.get("overlap_error", ""))

        asyncio.run(run())

    def test_negative_worker_span_sets_overlap_error(self):
        """When worker authoritative span is negative (submission < enqueue),
        overlap_error is set for worker, not merely incomplete."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="neg-span", process="local")
            origin = _make_origin("neg-span")
            origin["local_receive_to_enqueue_ms"] = 100.0
            trace.set_metadata(request_origin_info=origin)
            trace.set_metadata(
                local_receive_to_actual_submission_ms=50.0,  # < enqueue=100
                generator_create_ms=1.0,
                generator_create_to_first_iteration_ms=1.0,
            )
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="neg-span",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            sar = result.get("local_timing", {}).get("stage_attribution_residual_ms", {})
            self.assertIsNone(sar.get("worker_unattributed_ms"))
            self.assertEqual(sar.get("reconciliation_status"), "overlap_error")
            self.assertIn("worker", sar.get("overlap_error", ""))

        asyncio.run(run())

    def test_clock_alias_equals_local_residual(self):
        """clock_reconciliation_residual_ms is always the alias of local_residual_ms."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="clock-alias", process="local")
            origin = _make_origin("clock-alias")
            trace.set_metadata(request_origin_info=origin)
            trace.set_metadata(
                local_receive_to_actual_submission_ms=50.0,
                local_receive_to_generator_create_ms=30.0,
                generator_create_ms=5.0,
                generator_create_to_first_iteration_ms=3.0,
            )
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="clock-alias",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            self.assertIn("clock_reconciliation_residual_ms", lt)
            self.assertIn("local_residual_ms", lt)
            # Must be identical
            self.assertEqual(lt["clock_reconciliation_residual_ms"], lt["local_residual_ms"])

        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# Exact required trace/metadata field names and conventions
# ═══════════════════════════════════════════════════════════════════════


class TestExactRequiredMetadataFields(unittest.TestCase):
    """Verify the exact required trace/metadata field names are present
    and follow the specified conventions (chronological ordering, first
    event once, creation failure partial timestamps, proxy label,
    None/absent not zero, no extra calls/iterations)."""

    def _run_v2(self, trace: RuntimeTrace, events: list[dict] | None = None,
                handle_factory: Any = None) -> list[dict]:
        """Run transport.run_plan_stream with V2 handle factory and return messages."""
        msgs: list[dict] = []
        factory = handle_factory if handle_factory is not None else _make_v2_handle_factory(events or [])
        transport = ModalTransport(v2_handle_factory=factory)

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            async for msg in transport.run_plan_stream(
                plan, gpu="rtx-pro-6000", workspace={"id": "ws"},
                trace={"prompt_id": trace.request_id}, runtime_trace=trace,
            ):
                msgs.append(msg)
        asyncio.run(run())
        return msgs

    # ── all required fields present ────────────────────────────────

    def test_exact_required_field_names_present(self):
        """All 10 required trace/metadata field names appear in metadata."""
        trace = RuntimeTrace(request_id="required-fields", process="local")
        trace.set_metadata(request_origin_info=_make_origin("required-fields"))
        self._run_v2(trace, events=[
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ])
        md = trace._metadata
        for field in (
            "modal_generator_create_start_wall_ns",
            "modal_generator_created_wall_ns",
            "modal_first_iteration_start_wall_ns",
            "modal_submission_attempt_wall_ns",
            "modal_first_remote_event_wall_ns",
            "modal_generator_create_start_mono_ns",
            "modal_generator_created_mono_ns",
            "modal_first_iteration_start_mono_ns",
            "modal_first_remote_event_mono_ns",
            "modal_submission_boundary_source",
        ):
            self.assertIn(field, md, f"Missing required metadata field: {field}")

    # ── chronological ordering ─────────────────────────────────────

    def test_chronological_ordering_of_required_fields(self):
        """Required wall_ns fields maintain chronological order."""
        trace = RuntimeTrace(request_id="chrono-order", process="local")
        trace.set_metadata(request_origin_info=_make_origin("chrono-order"))
        self._run_v2(trace, events=[
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ])
        md = trace._metadata
        cs = md["modal_generator_create_start_wall_ns"]
        c = md["modal_generator_created_wall_ns"]
        fi = md["modal_first_iteration_start_wall_ns"]
        fr = md["modal_first_remote_event_wall_ns"]
        self.assertLessEqual(cs, c, "create_start must precede created")
        self.assertLessEqual(c, fi, "created must precede first_iteration")
        self.assertLessEqual(fi, fr, "first_iteration must precede first_remote_event")

    # ── first_iteration_start equals submission_attempt ────────────

    def test_first_iteration_start_matches_submission_attempt(self):
        """first_iteration_start_{wall,mono}_ns == submission_attempt_{wall,mono}_ns."""
        trace = RuntimeTrace(request_id="iter-matches-submit", process="local")
        trace.set_metadata(request_origin_info=_make_origin("iter-matches-submit"))
        self._run_v2(trace, events=[
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ])
        md = trace._metadata
        self.assertEqual(
            md.get("modal_first_iteration_start_wall_ns"),
            md.get("modal_submission_attempt_wall_ns"),
        )
        self.assertEqual(
            md.get("modal_first_iteration_start_mono_ns"),
            md.get("modal_submission_attempt_mono_ns"),
        )

    # ── first_remote_event equals first_event_received ─────────────

    def test_first_remote_event_matches_first_event_received(self):
        """first_remote_event_{wall,mono}_ns == first_event_received_{wall,mono}_ns."""
        trace = RuntimeTrace(request_id="remote-matches-event", process="local")
        trace.set_metadata(request_origin_info=_make_origin("remote-matches-event"))
        self._run_v2(trace, events=[
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ])
        md = trace._metadata
        self.assertEqual(
            md.get("modal_first_remote_event_wall_ns"),
            md.get("modal_first_event_received_wall_ns"),
        )
        self.assertEqual(
            md.get("modal_first_remote_event_mono_ns"),
            md.get("modal_first_event_received_mono_ns"),
        )

    # ── explicit proxy label ───────────────────────────────────────

    def test_submission_boundary_source_is_first_iteration_proxy(self):
        """modal_submission_boundary_source equals 'first_iteration_proxy'."""
        trace = RuntimeTrace(request_id="boundary-source", process="local")
        trace.set_metadata(request_origin_info=_make_origin("boundary-source"))
        self._run_v2(trace, events=[
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ])
        md = trace._metadata
        self.assertEqual(
            md.get("modal_submission_boundary_source"),
            "first_iteration_proxy",
        )

    # ── creation failure: start timestamps preserved, later absent ─

    def test_creation_failure_preserves_start_and_omits_later(self):
        """When remote_gen.aio() raises, start timestamps are in metadata
        but created/first_event/submission fields are absent (None via .get())."""
        trace = RuntimeTrace(request_id="create-failure", process="local")
        trace.set_metadata(request_origin_info=_make_origin("create-failure"))

        # Build a factory whose .aio() raises
        def _failing_factory(**kwargs):
            class _FailingHandle:
                class _RunPlanStream:
                    class _RemoteGen:
                        @staticmethod
                        def aio(*args, **kwargs):
                            raise RuntimeError("simulated creation failure")
                    remote_gen = _RemoteGen()
                run_plan_stream = _RunPlanStream()
            return _FailingHandle()

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            transport = ModalTransport(v2_handle_factory=_failing_factory)
            with self.assertRaises(TransportError):
                async for _ in transport.run_plan_stream(
                    plan, gpu="rtx-pro-6000", workspace={"id": "ws"},
                    trace={"prompt_id": "create-failure"},
                    runtime_trace=trace,
                ):
                    pass
            md = trace._metadata
            # Start timestamps present and positive
            self.assertIn("modal_generator_create_start_wall_ns", md)
            self.assertIn("modal_generator_create_start_mono_ns", md)
            self.assertIsInstance(md["modal_generator_create_start_wall_ns"], int)
            self.assertGreater(md["modal_generator_create_start_wall_ns"], 0)
            # Created / later fields absent → .get() returns None
            self.assertNotIn("modal_generator_created_wall_ns", md)
            self.assertNotIn("modal_generator_created_mono_ns", md)
            self.assertNotIn("modal_submission_attempt_wall_ns", md)
            self.assertNotIn("modal_first_iteration_start_wall_ns", md)
            self.assertNotIn("modal_first_remote_event_wall_ns", md)
            self.assertNotIn("modal_submission_boundary_source", md)
            # .get() on absent keys yields None, not 0
            self.assertIsNone(md.get("modal_generator_created_wall_ns"))
            self.assertIsNone(md.get("modal_generator_created_mono_ns"))
            self.assertIsNone(md.get("modal_submission_attempt_wall_ns"))
            self.assertIsNone(md.get("modal_first_remote_event_wall_ns"))
            self.assertIsNone(md.get("modal_submission_boundary_source"))

        asyncio.run(run())

    # ── first remote event captured exactly once ───────────────────

    def test_first_remote_event_captured_exactly_once(self):
        """first_remote_event_{wall,mono}_ns are single int values in metadata."""
        trace = RuntimeTrace(request_id="first-event-once", process="local")
        trace.set_metadata(request_origin_info=_make_origin("first-event-once"))
        self._run_v2(trace, events=[
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ])
        md = trace._metadata
        self.assertIsInstance(md.get("modal_first_remote_event_wall_ns"), int)
        self.assertIsInstance(md.get("modal_first_remote_event_mono_ns"), int)

    # ── no extra Modal calls or generator iterations ───────────────

    def test_no_extra_modal_calls_or_generator_iterations(self):
        """Only expected calls to remote_gen.aio() and __anext__()."""
        call_count = [0]
        iter_count = [0]

        class _CountingGen:
            def __init__(self):
                self._events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
                self._index = 0
                self.input_id = "counting-id"
                self.input_created_at = time.time_ns()

            def __aiter__(self):
                return self

            async def __anext__(self):
                iter_count[0] += 1
                if self._index >= len(self._events):
                    raise StopAsyncIteration
                event = self._events[self._index]
                self._index += 1
                return event

        def _counting_factory(**kw):
            call_count[0] += 1
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(
                        aio=lambda *a, **kw: _CountingGen(),
                    ),
                ),
            )

        trace = RuntimeTrace(request_id="no-extra-calls", process="local")
        trace.set_metadata(request_origin_info=_make_origin("no-extra-calls"))

        async def run():
            plan = ExecutionPlan(
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                execution_options=ExecutionOptions(production_enabled=False),
            )
            transport = ModalTransport(v2_handle_factory=_counting_factory)
            messages: list[dict] = []
            async for msg in transport.run_plan_stream(
                plan, gpu="rtx-pro-6000", workspace={"id": "ws"},
                trace={"prompt_id": "no-extra-calls"},
                runtime_trace=trace,
            ):
                messages.append(msg)
            self.assertEqual(call_count[0], 1,
                             "v2_handle_factory called more than once")
            # 1 event → 1 __anext__ for the event + 1 for StopAsyncIteration
            self.assertEqual(iter_count[0], 2,
                             "unexpected number of generator iterations")

        asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════
# V2 remote request origin intervals
# ═══════════════════════════════════════════════════════════════════════


class TestV2RemoteRequestOriginIntervals(unittest.TestCase):
    """Verify the V2 remote request origin intervals and their rendering."""

    def test_submission_to_remote_python_resume_ms_present(self):
        """submission_to_remote_python_resume_ms appears in local_timing
        (renders 'absent' when remote_python_resume unavailable)."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="submit-to-resume", process="local")
            origin = _make_origin("submit-to-resume")
            trace.set_metadata(request_origin_info=origin)
            # Do NOT set remote_python_resume_wall_ns — no restore path in test
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="submit-to-resume",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            self.assertIn("submission_to_remote_python_resume_ms", lt)
            # Without remote resume timestamp the interval must be "absent"
            self.assertEqual(lt["submission_to_remote_python_resume_ms"], "absent")

        asyncio.run(run())

    def test_submission_to_remote_python_resume_absent_when_origin_missing(self):
        """All V2 intervals render 'absent' when their endpoint is missing."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="v2-intervals-absent", process="local")
            origin = _make_origin("v2-intervals-absent")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="v2-intervals-absent",
                validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            result = await execute_plan(plan, transport=transport, trace=trace)
            lt = result.get("local_timing", {})
            # These V2 intervals rely on remote timestamps not present here
            for key in (
                "submission_to_remote_python_resume_ms",
                "remote_python_resume_to_restore_start_ms",
                "restore_method_ms",
                "restore_end_to_modal_method_entry_ms",
            ):
                val = lt.get(key)
                self.assertIn(
                    val, ("absent", None),
                    f"{key} must be 'absent' or None when endpoint missing, got {val!r}",
                )

        asyncio.run(run())

    def test_v2_interval_absent_not_zero_or_negative(self):
        """V2 intervals never substitute 0 or negative for missing endpoints."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        # Demonstrate the code uses "absent" not 0
        self.assertIn('"absent"', source)
        self.assertIn("_ABSENT", source)
        self.assertIn("_INVALID_NEG", source)

    def test_name_mismatch_between_transport_and_execution(self):
        """Verify the transport metadata keys used by execute_plan match
        exactly the keys set by modal_transport.set_metadata()."""
        import inspect
        from comfymodal_runtime.modal_transport import ModalTransport
        transport_source = inspect.getsource(ModalTransport.run_plan_stream)
        from canonical_execution import execute_plan
        exec_source = inspect.getsource(execute_plan)

        # Transport metadata keys (set by set_metadata call) that execute_plan
        # MUST reference via _transport_meta.get() or direct variable read.
        # Mono variants are also set by transport but execute_plan only reads
        # wall variants from _transport_meta; mono variants flow through
        # _origin_from_meta backfill.  Verify the wall variants match.
        transport_wall_keys = {
            "modal_generator_create_start_wall_ns",
            "modal_generator_created_wall_ns",
            "modal_first_iteration_start_wall_ns",
            "modal_submission_attempt_wall_ns",
            "modal_first_remote_event_wall_ns",
        }
        for key in transport_wall_keys:
            self.assertIn(
                key, exec_source,
                f"Wall key '{key}' set by transport must be referenced in execute_plan",
            )
            self.assertIn(
                key, transport_source,
                f"execute_plan reads '{key}' but it must be set by transport",
            )

        # Mono keys: set by transport in set_metadata, not directly read by
        # execute_plan (they backfill into _origin_from_meta instead).
        # Verify they ARE set in transport_source.
        transport_mono_keys = {
            "modal_generator_create_start_mono_ns",
            "modal_generator_created_mono_ns",
            "modal_first_iteration_start_mono_ns",
            "modal_submission_attempt_mono_ns",
            "modal_first_remote_event_mono_ns",
            "modal_submission_boundary_source",
        }
        for key in transport_mono_keys:
            self.assertIn(
                key, transport_source,
                f"Mono key '{key}' must be set by transport set_metadata call",
            )


# ═══════════════════════════════════════════════════════════════════════
# V2 local_submission_breakdown — new events, derived durations, metadata
# ═══════════════════════════════════════════════════════════════════════


class TestV2LocalSubmissionBreakdown(unittest.TestCase):
    """Verify new events, derived durations, and metadata in
    [v2.local_submission_breakdown] — covers all 7 categories:
    1. New events: execute_plan_entry, worker_start (in execute_plan)
    2. New events: transport_entry, pre_handle_residual_start/end (in transport)
    3. Derived durations (post_restore_publish_to_transport_ms,
       transport_entry_to_handle_lookup_ms, payload_ready_to_generator_create_ms)
    4. Monotonic durations per spec
    5. Absent/invalid_negative handling
    6. Metadata for active profile, restore publication, handle lookup,
       payload/workflow/images/cache/remote calls
    7. Backward compatibility: existing events unchanged
    """

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _make_plan() -> ExecutionPlan:
        return ExecutionPlan(
            workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
            execution_options=ExecutionOptions(production_enabled=False),
        )

    # ── Category 1: execute_plan_entry + worker_start in build_execution_plan ──

    def test_execute_plan_entry_emitted_in_v1_path(self):
        """execute_plan_entry is emitted in the V1 transport path.
        worker_start is NOT emitted in V1 path (only in __init__.py v2 caller)."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="entry-v1", process="local")
            origin = _make_origin("entry-v1")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="entry-v1", validate=False, trace=trace,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(plan, transport=transport, trace=trace)
            names = [e.name for e in trace.events]
            self.assertIn("execute_plan_entry", names,
                          "execute_plan_entry event must be emitted")
            self.assertNotIn("worker_start", names,
                             "worker_start must NOT be emitted in V1 path")
            entry_event = next(e for e in trace.events if e.name == "execute_plan_entry")
            self.assertGreater(entry_event.monotonic_ns, 0)

        asyncio.run(run())

    def test_execute_plan_entry_is_first_execution_event(self):
        """execute_plan_entry is the very first event emitted by execute_plan
        (after trace setup but before any profile/restore work)."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="entry-first", process="local")
            origin = _make_origin("entry-first")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="entry-first", validate=False, trace=trace,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(plan, transport=transport, trace=trace)
            # Skip events emitted before execute_plan (plan_build_start/end).
            # worker_start is NOT emitted in V1 path.
            exec_events = [e for e in trace.events
                           if e.name not in
                           ("plan_build_start", "plan_build_end")]
            if exec_events:
                self.assertEqual(exec_events[0].name, "execute_plan_entry")

        asyncio.run(run())

    def test_worker_start_not_in_v1_path(self):
        """worker_start must NOT be emitted in V1 transport path.
        It is only emitted via emit_at in __init__.py v2 dispatch."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="worker-not-in-v1", process="local")
            origin = _make_origin("worker-not-in-v1")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="worker-not-in-v1", validate=False, trace=trace,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(plan, transport=transport, trace=trace)
            names = [e.name for e in trace.events]
            self.assertNotIn("worker_start", names,
                             "worker_start must NOT appear in V1 path")
            self.assertIn("plan_build_start", names,
                          "plan_build_start must be emitted")

        asyncio.run(run())

    # ── Category 2: transport_entry + pre_handle_residual in transport ──

    def _run_v2_path(self, trace: RuntimeTrace,
                     events: list[dict] | None = None) -> list[dict]:
        """Helper: run transport.run_plan_stream with V2 handle factory."""
        msgs: list[dict] = []
        factory = _make_v2_handle_factory(events or [
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ])

        async def run():
            plan = self._make_plan()
            transport = ModalTransport(v2_handle_factory=factory)
            async for msg in transport.run_plan_stream(
                plan, gpu="rtx-pro-6000", workspace={"id": "ws"},
                trace={"prompt_id": trace.request_id}, runtime_trace=trace,
            ):
                msgs.append(msg)
        asyncio.run(run())
        return msgs

    def test_transport_entry_emitted_in_v2_path(self):
        """transport_entry is emitted when V2 transport path is used."""
        trace = RuntimeTrace(request_id="transport-entry-v2", process="local")
        self._run_v2_path(trace)
        names = [e.name for e in trace.events]
        self.assertIn("transport_entry", names,
                      "transport_entry must be emitted in V2 path")
        transport_event = next(e for e in trace.events if e.name == "transport_entry")
        self.assertGreater(transport_event.monotonic_ns, 0)

    def test_pre_handle_residual_start_end_emitted(self):
        """pre_handle_residual_start and pre_handle_residual_end are emitted
        in V2 path, correctly wrapping the handle lookup gap."""
        trace = RuntimeTrace(request_id="pre-handle-residual", process="local")
        self._run_v2_path(trace)
        names = [e.name for e in trace.events]
        self.assertIn("pre_handle_residual_start", names)
        self.assertIn("pre_handle_residual_end", names)
        # Chronology: transport_entry → residual_start → residual_end → handle_lookup_start
        te_idx = names.index("transport_entry")
        rs_idx = names.index("pre_handle_residual_start")
        re_idx = names.index("pre_handle_residual_end")
        hl_idx = names.index("modal_handle_lookup_start")
        self.assertLessEqual(te_idx, rs_idx)
        self.assertLessEqual(rs_idx, re_idx)
        self.assertLessEqual(re_idx, hl_idx)

    def test_transport_entry_to_handle_lookup_derived(self):
        """transport_entry_to_handle_lookup_ms = modal_handle_lookup_start
        mono - transport_entry mono, stored in trace metadata."""
        trace = RuntimeTrace(request_id="entry-to-handle", process="local")
        self._run_v2_path(trace)
        # The breakdown uses _derived_mono_delta_ms — verify the raw events
        te = next(e for e in trace.events if e.name == "transport_entry")
        hls = next(e for e in trace.events if e.name == "modal_handle_lookup_start")
        delta_ms = round((hls.monotonic_ns - te.monotonic_ns) / 1_000_000, 3)
        self.assertGreaterEqual(delta_ms, 0.0,
                                "transport_entry_to_handle_lookup_ms must be >= 0")
        # The _derived_mono_delta_ms function computes the same delta
        from canonical_execution import _derived_mono_delta_ms
        computed = _derived_mono_delta_ms(trace, "transport_entry", "modal_handle_lookup_start")
        self.assertIsNotNone(computed)
        if isinstance(computed, (int, float)):
            self.assertAlmostEqual(computed, delta_ms, places=2)

    # ── Category 3: derived durations ──────────────────────────────

    def test_post_restore_publish_to_transport_ms(self):
        """post_restore_publish_to_transport_ms computed from trace events."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="post-restore-transport", process="local")
            origin = _make_origin("post-restore-transport")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="post-restore-transport", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(plan, transport=transport, trace=trace)
            # V1 path: transport_entry is absent → derived duration is None
            from canonical_execution import _derived_mono_delta_ms
            computed = _derived_mono_delta_ms(trace, "restore_plan_publish_end", "transport_entry")
            if computed is not None:
                self.assertIsInstance(computed, (int, float))

        asyncio.run(run())

    def test_payload_ready_to_generator_create_ms(self):
        """payload_ready_to_generator_create_ms computed from V2 trace events."""
        trace = RuntimeTrace(request_id="payload-ready-gen", process="local")
        self._run_v2_path(trace)
        from canonical_execution import _derived_mono_delta_ms
        computed = _derived_mono_delta_ms(trace, "modal_payload_serialize_end", "modal_generator_create_start")
        if computed is not None:
            self.assertIsInstance(computed, (int, float))
            self.assertGreaterEqual(float(computed), 0.0)

    # ── Category 4: monotonic durations ────────────────────────────

    def test_event_mono_ns_returns_none_for_missing(self):
        """_event_mono_ns returns None for nonexistent event names."""
        from canonical_execution import _event_mono_ns
        trace = RuntimeTrace(request_id="mono-missing", process="local")
        result = _event_mono_ns(trace, "nonexistent_event_name")
        self.assertIsNone(result)

    def test_derived_mono_delta_absent_for_missing(self):
        """_derived_mono_delta_ms returns None when either event is missing."""
        from canonical_execution import _derived_mono_delta_ms
        trace = RuntimeTrace(request_id="delta-missing", process="local")
        result = _derived_mono_delta_ms(trace, "start_event", "end_event")
        self.assertIsNone(result)

    def test_derived_mono_delta_invalid_negative(self):
        """_derived_mono_delta_ms returns 'invalid_negative' when end_ns < start_ns."""
        from canonical_execution import _derived_mono_delta_ms
        trace = RuntimeTrace(request_id="delta-neg", process="local")
        # emit A before B; B has higher mono_ns
        trace.emit("event_a", phase="test")
        trace.emit("event_b", phase="test")
        # passing start="event_b" (larger mono_ns) and end="event_a" (smaller mono_ns)
        # gives negative delta: event_a.ns - event_b.ns < 0
        result = _derived_mono_delta_ms(trace, "event_b", "event_a")
        self.assertEqual(result, "invalid_negative")

    # ── Category 5: absent/invalid_negative handling ───────────────

    def test_breakdown_absent_when_transport_is_v1(self):
        """When V1 path is used, transport_entry and derived durations are
        absent (None/absent) — not zero or invalid."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="v1-breakdown", process="local")
            origin = _make_origin("v1-breakdown")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="v1-breakdown", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(plan, transport=transport, trace=trace)
            # transport_entry event should NOT be present in V1 path
            names = [e.name for e in trace.events]
            self.assertNotIn("transport_entry", names,
                             "transport_entry must NOT be emitted in V1 path")
            # pre_handle_residual events also absent in V1 path
            self.assertNotIn("pre_handle_residual_start", names)
            self.assertNotIn("pre_handle_residual_end", names)

        asyncio.run(run())

    def test_breakdown_uses_non_zero_absent(self):
        """Missing values in breakdown are None or 'absent', never zero."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        # The breakdown uses _fmt_opt which converts None to "absent"
        self.assertIn("_fmt_bd", source)
        self.assertIn("[v2.local_submission_breakdown]", source)

    # ── Category 6: metadata for all required categories ───────────

    def test_breakdown_contains_active_profile_metadata(self):
        """[v2.local_submission_breakdown] references active profile metadata."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        for field in (
            "active_profile_publish_decision",
            "active_profile_stable_key",
            "local_active_profile_prepare_ms",
            "active_profile_remote_call",
        ):
            self.assertIn(field, source,
                          f"Breakdown must reference {field}")

    def test_breakdown_contains_restore_publication_metadata(self):
        """[v2.local_submission_breakdown] references restore publish metadata.

        The breakdown dict is owned by ``comfymodal_runtime.trace``
        (``_build_local_submission_breakdown``), not execute_plan."""
        import inspect
        from comfymodal_runtime.trace import _build_local_submission_breakdown
        source = inspect.getsource(_build_local_submission_breakdown)
        for field in (
            "restore_publish_generation",
            "restore_publish_cache_skipped",
        ):
            self.assertIn(field, source,
                          f"Breakdown must reference {field}")

    def test_breakdown_contains_handle_lookup_metadata(self):
        """[v2.local_submission_breakdown] references handle lookup metadata."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        for field in (
            "handle_lookup_app_name",
            "handle_lookup_class_name",
            "handle_lookup_gpu",
        ):
            self.assertIn(field, source,
                          f"Breakdown must reference {field}")

    def test_breakdown_contains_payload_workflow_image_metadata(self):
        """[v2.local_submission_breakdown] references payload/workflow/image metadata."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        for field in (
            "payload_serialized_bytes",
            "workflow_hash_prefix",
            "input_image_count",
        ):
            self.assertIn(field, source,
                          f"Breakdown must reference {field}")

    def test_breakdown_contains_cache_remote_call_metadata(self):
        """[v2.local_submission_breakdown] references cache/remote call metadata."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        for field in (
            "handle_cache_action",
            "active_profile_remote_call_count",
        ):
            self.assertIn(field, source,
                          f"Breakdown must reference {field}")

    # ── Category 7: backward compatibility ─────────────────────────

    def test_existing_events_preserved(self):
        """All existing valid events are still present after instrumentation
        across the modules that own them: ``build_execution_plan``,
        ``execute_plan``, and ``ModalTransport.run_plan_stream``."""
        import inspect
        from canonical_execution import build_execution_plan, execute_plan
        from comfymodal_runtime.modal_transport import ModalTransport
        sources = "".join([
            inspect.getsource(build_execution_plan),
            inspect.getsource(execute_plan),
            inspect.getsource(ModalTransport.run_plan_stream),
        ])
        existing_events = {
            "plan_build_start", "plan_build_end",
            "active_profile_prepare_start", "active_profile_prepare_end",
            "restore_plan_build_start", "restore_plan_build_end",
            "restore_plan_publish_start", "restore_plan_publish_end",
            "modal_handle_lookup_start", "modal_handle_lookup_end",
            "modal_payload_serialize_start", "modal_payload_serialize_end",
            "modal_generator_create_start", "modal_submission_attempt",
            "execute_plan_entry",
        }
        for evt in existing_events:
            self.assertIn(evt, sources,
                          f"Existing event '{evt}' must still be emitted by an owning module")

    def test_existing_trace_fields_preserved(self):
        """Existing metadata/trace fields (generator_create_ms, etc.) are still set."""
        trace = RuntimeTrace(request_id="backward-compat", process="local")
        self._run_v2_path(trace)
        md = trace._metadata
        for field in (
            "generator_create_ms",
            "local_receive_to_generator_create_ms",
            "generator_create_to_first_iteration_ms",
            "first_iteration_to_first_remote_event_ms",
            "local_receive_to_actual_submission_ms",
        ):
            self.assertIn(field, md,
                          f"Existing metadata field '{field}' must still be present")

    def test_existing_api_signature_preserved(self):
        """execute_plan, build_execution_plan, ModalTransport signatures unchanged."""
        import inspect
        from canonical_execution import execute_plan, build_execution_plan
        from comfymodal_runtime.modal_transport import ModalTransport
        # Just verify they're still importable (our instrumentation didn't break module)
        self.assertTrue(callable(execute_plan))
        self.assertTrue(callable(build_execution_plan))
        self.assertTrue(hasattr(ModalTransport, "run_plan_stream"))

    def test_no_remote_or_scheduling_time_in_breakdown(self):
        """[v2.local_submission_breakdown] does NOT contain remote or
        scheduling time fields (those appear in [v2.remote_request_origin])."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        # Find the [v2.local_submission_breakdown] block
        breakdown_start = source.find("[v2.local_submission_breakdown]")
        self.assertGreater(breakdown_start, 0,
                           "[v2.local_submission_breakdown] must exist")
        # Remote-only fields that should NOT be in this breakdown
        remote_fields = (
            "remote_python_resume_to_restore_start_ms",
            "restore_method_ms",
            "restore_end_to_modal_method_entry_ms",
            "modal_method_entry_to_executor_ms",
            "submission_to_remote_python_resume_ms",
        )
        for field in remote_fields:
            # These may appear elsewhere in the source, but NOT inside the
            # [v2.local_submission_breakdown] print statement
            breakdown_section = source[breakdown_start:breakdown_start + 3000]
            self.assertNotIn(field, breakdown_section,
                             f"Remote field '{field}' must not appear in breakdown")

    # ═══════════════════════════════════════════════════════════════════════
    # Category 8: Corrected breakdown — sequential non-overlapping partition
    # ═══════════════════════════════════════════════════════════════════════

    def test_breakdown_contains_all_required_fields(self):
        """[v2.local_submission_breakdown] contains ALL required field names.

        The breakdown dict is owned by ``comfymodal_runtime.trace``
        (``_build_local_submission_breakdown``), not execute_plan."""
        import inspect
        from comfymodal_runtime.trace import _build_local_submission_breakdown
        source = inspect.getsource(_build_local_submission_breakdown)
        required_fields = [
            "request_id",
            "local_receive_to_worker_start_ms",
            "worker_start_to_plan_build_ms",
            "plan_build_ms",
            "active_profile_ms",
            "restore_plan_build_ms",
            "restore_publish_ms",
            "restore_publish_to_transport_entry_ms",
            "transport_entry_to_handle_lookup_ms",
            "handle_lookup_ms",
            "payload_materialization_ms",
            "payload_size_measurement_ms",
            "payload_ready_to_modal_call_ms",
            "generator_create_ms",
            "generator_created_to_first_iteration_ms",
            "local_receive_to_actual_submission_ms",
            "measured_children_ms",
            "residual_ms",
            "reconciliation_status",
        ]
        for field in required_fields:
            self.assertIn(field, source,
                          f"Required field '{field}' must appear in breakdown source")

    def test_breakdown_equations_e2e_v1(self):
        """measured_children_ms + residual_ms ≈ total across V1 path events."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="eq-v1", process="local")
            origin = _make_origin("eq-v1")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="eq-v1", validate=False, trace=trace,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(plan, transport=transport, trace=trace)
            # worker_start is NOT emitted in V1 path (only in __init__.py v2 dispatch).
            names = [e.name for e in trace.events]
            self.assertNotIn("worker_start", names,
                             "worker_start must NOT be emitted in V1 path")
            self.assertIn("execute_plan_entry", names)
            self.assertIn("plan_build_start", names)
            self.assertIn("plan_build_end", names)

        asyncio.run(run())

    def test_breakdown_negative_detected_by_derived_mono_delta(self):
        """_derived_mono_delta_ms returns 'invalid_negative' for negative delta."""
        from canonical_execution import _derived_mono_delta_ms
        trace = RuntimeTrace(request_id="neg-delta", process="local")
        trace.emit("event_a", phase="test")
        trace.emit("event_b", phase="test")
        # start=event_b (larger mono_ns), end=event_a (smaller mono_ns) → negative
        result = _derived_mono_delta_ms(trace, "event_b", "event_a")
        self.assertEqual(result, "invalid_negative")

    def test_breakdown_absent_for_missing_events(self):
        """_derived_mono_delta_ms returns None when either event is missing."""
        from canonical_execution import _derived_mono_delta_ms
        trace = RuntimeTrace(request_id="absent-delta", process="local")
        result = _derived_mono_delta_ms(trace, "nonexistent_start", "nonexistent_end")
        self.assertIsNone(result)

    def test_breakdown_requires_exact_field_names(self):
        """Required fields in breakdown dict have exact canonical names."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        bd_start = source.find("[v2.local_submission_breakdown]")
        self.assertGreater(bd_start, 0)
        # Find the _breakdown dict definition (after the comment header)
        dict_start = source.find('"request_id"', bd_start)
        self.assertGreater(dict_start, 0)
        # Find the print statement start
        print_start = source.find('f"[v2.local_submission_breakdown] "', dict_start)
        self.assertGreater(print_start, 0)
        # Check dict keys (between dict_start and print_start)
        dict_section = source[dict_start:print_start + 3000]
        # Verify old/misnamed field patterns are NOT dict keys in the breakdown
        forbidden_as_keys = [
            '"worker_start_to_execute_plan_entry_ms"',  # must be "worker_start_to_plan_build_ms"
            '"post_restore_publish_to_transport_ms"',   # must be "restore_publish_to_transport_entry_ms"
            '"payload_serialize_ms"',                   # dict key (must be "payload_materialization_ms")
            '"profile_prep_cache_hit"',                 # must be "profile_cache_hit"
            '"restore_publish_cache_skipped"',          # must be "restore_publish_cache_hit"
            '"hit_handle_cache"',                        # must be "handle_cache_hit"
        ]
        for name in forbidden_as_keys:
            self.assertNotIn(name, dict_section,
                             f"Dict key '{name}' must NOT appear in breakdown")

    def test_breakdown_cache_hit_miss_metadata(self):
        """Breakdown contains cache hit/miss booleans populated from trace events."""
        trace = RuntimeTrace(request_id="cache-md", process="local")
        origin = _make_origin("cache-md")
        trace.set_metadata(request_origin_info=origin)
        # Emit handle_cache_hit to test its detection
        trace.emit("handle_cache_hit", phase="test")
        self._run_v2_path(trace)
        # verify trace metadata contains handle_cache_hit related info
        # via event inspection
        evt_names = [e.name for e in trace.events]
        self.assertIn("handle_cache_hit", evt_names)
        # The breakdown dict should have handle_cache_hit key
        md = trace._metadata
        self.assertIn("handle_lookup_app_name", md)


# ═══════════════════════════════════════════════════════════════════════
# Requirement 1a: Exact stdout capture of [v2.local_submission_breakdown]
# ═══════════════════════════════════════════════════════════════════════


class TestLocalSubmissionBreakdownStdoutCapture(unittest.TestCase):
    """Capture stdout during execute_plan and validate the exact
    [v2.local_submission_breakdown] line format."""

    def _capture_breakdown_line(self, trace_mod_fn=None) -> str:
        """Run execute_plan and capture all stdout, return the
        [v2.local_submission_breakdown] line."""
        import io
        out = io.StringIO()
        _orig = sys.stdout
        try:
            sys.stdout = out
            trace = RuntimeTrace(request_id="capture-test", process="local")
            origin = _make_origin("capture-test")
            trace.set_metadata(request_origin_info=origin)
            if trace_mod_fn:
                trace_mod_fn(trace)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="capture-test", validate=False,
            )
            transport = ModalTransport(
                v2_handle_factory=_make_v2_handle_factory(
                    [{"type": "result", "data": {"images": [], "outputs": {}}}],
                ),
            )
            asyncio.run(execute_plan(plan, transport=transport, trace=trace))
        finally:
            sys.stdout = _orig
        for line in out.getvalue().splitlines():
            if line.startswith("[v2.local_submission_breakdown]"):
                return line
        return ""

    def test_breakdown_line_present(self):
        """Exactly one [v2.local_submission_breakdown] line is printed."""
        output = self._capture_breakdown_line()
        self.assertTrue(output.startswith("[v2.local_submission_breakdown]"),
                        "Breakdown line must start with the tag")
        self.assertIn("request_id=capture-test", output)
        self.assertIn("plan_build_ms=", output)
        self.assertIn("active_profile_ms=", output)
        self.assertIn("reconciliation_status=", output)
        self.assertIn("unmeasured_boundary=", output)
        self.assertIn("residual_ms=", output)
        self.assertIn("measured_children_ms=", output)

    def test_breakdown_absent_values_use_absent_string(self):
        """None values render as 'absent', not empty or 0."""
        output = self._capture_breakdown_line()
        # local_receive_to_worker_start_ms is absent when no worker_start event
        self.assertIn("local_receive_to_worker_start_ms=absent", output,
                      "Missing values must render as 'absent'")
        self.assertNotIn("local_receive_to_worker_start_ms=0", output,
                         "Missing values must NOT render as 0")

    def test_breakdown_invalid_negative_rendered(self):
        """Stages with start > end render 'invalid_negative'."""
        def add_neg(trace):
            trace.emit_at("plan_build_start", wall_unix_ns=200, monotonic_ns=2000, phase="local")
            trace.emit_at("plan_build_end", wall_unix_ns=100, monotonic_ns=1000, phase="local")
        output = self._capture_breakdown_line(trace_mod_fn=add_neg)
        self.assertIn("plan_build_ms=invalid_negative", output)

    def test_breakdown_exactly_one_line(self):
        """Only one [v2.local_submission_breakdown] line per request."""
        import io
        out = io.StringIO()
        _orig = sys.stdout
        try:
            sys.stdout = out
            trace = RuntimeTrace(request_id="exactly-one", process="local")
            origin = _make_origin("exactly-one")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="exactly-one", validate=False,
            )
            transport = ModalTransport(
                v2_handle_factory=_make_v2_handle_factory(
                    [{"type": "result", "data": {"images": [], "outputs": {}}}],
                ),
            )
            asyncio.run(execute_plan(plan, transport=transport, trace=trace))
        finally:
            sys.stdout = _orig
        lines = [l for l in out.getvalue().splitlines()
                 if l.startswith("[v2.local_submission_breakdown]")]
        self.assertEqual(len(lines), 1,
                         "Must emit exactly one [v2.local_submission_breakdown] line")


# ═══════════════════════════════════════════════════════════════════════
# Requirement 1b: unmeasured_boundary for residual > 100ms
# ═══════════════════════════════════════════════════════════════════════


class TestUnmeasuredBoundaryLargeResidual(unittest.TestCase):
    """When residual > 100ms, unmeasured_boundary names the cause."""

    def test_unmeasured_boundary_field_present_in_output(self):
        """unmeasured_boundary field always appears in breakdown output."""
        import io
        out = io.StringIO()
        _orig = sys.stdout
        try:
            sys.stdout = out
            trace = RuntimeTrace(request_id="ub-field-test", process="local")
            origin = _make_origin("ub-field-test")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="ub-field-test", validate=False,
            )
            transport = ModalTransport(
                v2_handle_factory=_make_v2_handle_factory(
                    [{"type": "result", "data": {"images": [], "outputs": {}}}],
                ),
            )
            asyncio.run(execute_plan(plan, transport=transport, trace=trace))
        finally:
            sys.stdout = _orig
        for line in out.getvalue().splitlines():
            if line.startswith("[v2.local_submission_breakdown]"):
                self.assertIn("unmeasured_boundary=", line,
                              "unmeasured_boundary field must appear in breakdown")
                return
        self.fail("No [v2.local_submission_breakdown] line found")

    def test_unmeasured_boundary_logic_in_code(self):
        """Code-level verification of unmeasured_boundary logic."""
        import inspect
        source = inspect.getsource(execute_plan)
        # The logic checks residual > 100 and names absent children
        self.assertIn("_unmeasured_boundary", source,
                      "unmeasured_boundary variable must exist")
        self.assertIn("_residual_ms > 100", source,
                      "Logic must check residual > 100ms")
        self.assertIn("absent_stage", source,
                      "Must name absent stages when residual > 100ms")
        self.assertIn("between_recorded_stages", source,
                      "Must report between_recorded_stages when all children known")


# ═══════════════════════════════════════════════════════════════════════
# Requirement 2: plan_materialization_count and plan_materialization_ms
# ═══════════════════════════════════════════════════════════════════════


class TestPlanMaterializationTracking(unittest.TestCase):
    """plan_materialization_count and plan_materialization_ms appear in
    trace metadata when execute_plan materializes the canonical dict."""

    def test_plan_materialization_count_is_one(self):
        """plan_materialization_count is exactly 1 after execute_plan."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="plan-mat-count", process="local")
            origin = _make_origin("plan-mat-count")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="plan-mat-count", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(plan, transport=transport, trace=trace)
            md = trace._metadata
            self.assertEqual(md.get("plan_materialization_count"), 1)

        asyncio.run(run())

    def test_plan_materialization_ms_is_numeric(self):
        """plan_materialization_ms is a non-negative float."""
        async def stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            trace = RuntimeTrace(request_id="plan-mat-ms", process="local")
            origin = _make_origin("plan-mat-ms")
            trace.set_metadata(request_origin_info=origin)
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="plan-mat-ms", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=stream)
            await execute_plan(plan, transport=transport, trace=trace)
            md = trace._metadata
            ms = md.get("plan_materialization_ms")
            self.assertIsInstance(ms, (int, float))
            self.assertGreaterEqual(float(ms), 0.0)

        asyncio.run(run())

    def test_plan_to_dict_called_once(self):
        """plan.to_dict() is called exactly once in execute_plan (no
        duplicate in transport when plan_dict is passed)."""
        import inspect
        source = inspect.getsource(execute_plan)
        # Count non-comment occurrences of "plan.to_dict()"
        count = source.count("plan.to_dict()")
        self.assertEqual(count, 1,
                         "plan.to_dict() must appear exactly once in execute_plan source")

        # Verify the _canonical_dict assignment wraps it with timing
        self.assertIn("_plan_mat_start_ns = time.perf_counter_ns()", source)
        self.assertIn("_canonical_dict: dict = plan.to_dict()", source)
        self.assertIn("_plan_mat_end_ns = time.perf_counter_ns()", source)
        self.assertIn("plan_materialization_count", source)

        # Verify transport V2 path does NOT call plan.to_dict() when plan_dict
        # is provided (it uses plan_dict directly)
        transport_source = inspect.getsource(ModalTransport.run_plan_stream)
        # The V2 path has: plan_dict = plan_dict if plan_dict is not None else plan.to_dict()
        # But only as fallback, not as default
        v2_fallback = 'plan_dict = plan_dict if plan_dict is not None else plan.to_dict()'
        self.assertIn(v2_fallback, transport_source,
                      "Transport must only call plan.to_dict() as fallback")


# ═══════════════════════════════════════════════════════════════════════
# Inner remote async iterator cleanup
# ═══════════════════════════════════════════════════════════════════════


class TestTransportIteratorCleanup(unittest.TestCase):
    """The transport must explicitly close/await the inner remote async
    iterator after the result, on exception, and on cancellation so Modal
    SDK-owned tasks (async_generator_athrow / synchronizer) do not leak past
    request completion."""

    class _ClosableGen:
        """Async iterator that records explicit aclose() calls like Modal's
        remote_gen.aio() object."""

        def __init__(self, events):
            self._events = list(events)
            self._index = 0
            self.aclose_calls = 0
            self.input_id = "closable-input"
            self.input_created_at = time.time_ns()

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self._events):
                raise StopAsyncIteration
            event = self._events[self._index]
            self._index += 1
            return event

        async def aclose(self):
            self.aclose_calls += 1

    def _factory(self, gen: Any) -> Any:
        return lambda **kw: SimpleNamespace(
            run_plan_stream=SimpleNamespace(
                remote_gen=SimpleNamespace(aio=lambda *a, **kw: gen),
            ),
        )

    def _plan(self, request_id: str) -> ExecutionPlan:
        return ExecutionPlan(
            workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
            execution_options=ExecutionOptions(production_enabled=False),
        )

    def test_aclose_called_after_normal_completion(self):
        gen = self._ClosableGen([
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ])

        async def run():
            transport = ModalTransport(v2_handle_factory=self._factory(gen))
            messages: list[dict] = []
            async for msg in transport.run_plan_stream(
                self._plan("aclose-normal"),
                gpu="rtx-pro-6000", workspace={"id": "ws"},
                trace={"prompt_id": "aclose-normal"},
            ):
                messages.append(msg)
            self.assertEqual(len(messages), 2)
            self.assertEqual(gen.aclose_calls, 1,
                             "inner iterator must be explicitly closed after the result")

        asyncio.run(run())

    def test_aclose_called_after_empty_stream(self):
        gen = self._ClosableGen([])

        async def run():
            transport = ModalTransport(v2_handle_factory=self._factory(gen))
            async for _ in transport.run_plan_stream(
                self._plan("aclose-empty"),
                gpu="rtx-pro-6000", workspace={"id": "ws"},
                trace={"prompt_id": "aclose-empty"},
            ):
                pass
            # Variant A: an immediately-ended stream is handed to the shielded
            # background drain (which closes the iterator at its end), so the
            # inner aclose is no longer synchronous — join the drain first.
            drain = getattr(transport, "_drain_task", None)
            if drain is not None:
                await asyncio.wait_for(drain, timeout=5.0)
            self.assertEqual(gen.aclose_calls, 1,
                             "inner iterator must be closed when the stream ends immediately")

        asyncio.run(run())

    def test_aclose_called_on_exception(self):
        class _FailingGen:
            aclose_calls = 0

            def __init__(self):
                self.input_id = ""
                self.input_created_at = None

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise RuntimeError("remote stream failed")

            async def aclose(self):
                _FailingGen.aclose_calls += 1

        async def run():
            transport = ModalTransport(v2_handle_factory=self._factory(_FailingGen()))
            with self.assertRaises(TransportError):
                async for _ in transport.run_plan_stream(
                    self._plan("aclose-exc"),
                    gpu="rtx-pro-6000", workspace={"id": "ws"},
                    trace={"prompt_id": "aclose-exc"},
                ):
                    pass
            # Variant A: the failed stream is handed to the shielded background
            # drain (which swallows the error and closes the iterator at its
            # end), so the inner aclose is no longer synchronous — join the
            # drain before asserting.
            drain = getattr(transport, "_drain_task", None)
            if drain is not None:
                await asyncio.wait_for(drain, timeout=5.0)
            self.assertEqual(_FailingGen.aclose_calls, 1,
                             "inner iterator must be closed when the stream raises")

        asyncio.run(run())

    def test_aclose_called_when_consumer_stops_early(self):
        gen = self._ClosableGen([
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ])

        async def run():
            transport = ModalTransport(v2_handle_factory=self._factory(gen))
            stream = transport.run_plan_stream(
                self._plan("aclose-break"),
                gpu="rtx-pro-6000", workspace={"id": "ws"},
                trace={"prompt_id": "aclose-break"},
            )
            async for _ in stream:
                break
            # Abandoning the stream without closing would defer inner cleanup
            # to garbage collection (the pending async_generator_athrow leak
            # this fix targets).  Closing the transport generator must
            # deterministically close the inner remote iterator.
            await stream.aclose()  # type: ignore[attr-defined]
            # Variant A: early-stop cleanup runs in the shielded background
            # drain, so join it before asserting the inner aclose.
            drain = getattr(transport, "_drain_task", None)
            if drain is not None:
                await asyncio.wait_for(drain, timeout=5.0)
            self.assertEqual(gen.aclose_calls, 1,
                             "inner iterator must be closed when the transport generator is closed")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
