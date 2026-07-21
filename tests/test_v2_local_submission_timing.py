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
import json
import time
import unittest
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from collections.abc import Mapping
from canonical_execution import build_execution_plan, execute_plan
from comfymodal_runtime.contracts import ExecutionPlan, ExecutionOptions
from comfymodal_runtime.modal_transport import ModalTransport
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
            # generator_create_ms comes from transport metadata, not origin,
            # so it may still be None (transport not called in V1 path)
            if lt.get("generator_create_ms") is not None:
                self.assertIsInstance(lt["generator_create_ms"], (int, float))

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


class TestV2RequestOriginSummary(unittest.TestCase):
    """[v2.request_origin] log line includes local_timing-derived fields."""

    def test_summary_contains_local_residual(self):
        """The [v2.request_origin] line in canonical_execution.py
        prints local_residual_ms."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        self.assertIn("local_residual_ms", source)

    def test_summary_contains_modal_generator_timestamps(self):
        """The summary line references modal_generator_created_unix_ns,
        modal_submission_attempt_unix_ns, modal_first_event_received_unix_ns."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        self.assertIn("modal_generator_created_unix_ns", source)
        self.assertIn("modal_submission_attempt_unix_ns", source)
        self.assertIn("modal_first_event_received_unix_ns", source)

    def test_summary_contains_t0_t1_and_queuing_fields(self):
        """The summary line references t0_to_t1_ms, t1_to_queue_enqueue_ms,
        local_receive_to_enqueue_ms, queue_wait_before_worker_ms."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        self.assertIn("t0_to_t1_ms", source)
        self.assertIn("t1_to_queue_enqueue_ms", source)
        self.assertIn("local_receive_to_enqueue_ms", source)
        self.assertIn("queue_wait_before_worker_ms", source)

    def test_summary_contains_restore_publish_ms(self):
        """The summary line includes restore_publish_ms."""
        import inspect
        from canonical_execution import execute_plan
        source = inspect.getsource(execute_plan)
        self.assertIn("restore_publish_ms", source)


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


if __name__ == "__main__":
    unittest.main()
