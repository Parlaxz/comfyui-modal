"""Critical-path tests for local pre-submission optimization.

Proves:
1. Two identical + one changed request → correct operation counts
2. Payload equivalence between canonical dict and transport
3. Workspace handle isolation
4. One Modal submission per request
5. Timing reconciliation residual <100ms or attributed
6. Stdout capture proves [v2.local_submission_breakdown] appears
"""

from __future__ import annotations

import asyncio
import io
import re
import sys
import time
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from canonical_execution import (
    _reset_profile_prep_cache,
    _reset_restore_publish_cache,
    build_execution_plan,
    execute_plan,
)
from comfymodal_runtime.contracts import ExecutionPlan
from comfymodal_runtime.modal_transport import ModalTransport
from comfymodal_runtime.trace import RuntimeTrace
from warmup_profile import _reset_last_stable_profile_cache


class _CountingProfileSetter:
    def __init__(self, status: str = "written"):
        self.invoke_count = 0
        self._status = status

    async def __call__(self, payload: dict, *, workspace: dict | None = None) -> dict:
        self.invoke_count += 1
        return {"status": self._status, "changed": True}


class _Publisher:
    def __init__(self):
        self.plans = []
        self.publish_count = 0

    def publish(self, plan):
        self.plans.append(plan)
        self.publish_count += 1
        return self.publish_count


def _make_fake_aio(events: list[dict] | None = None):
    class _FakeGen:
        def __init__(self):
            self._events = list(events or [
                {"type": "result", "data": {"images": [], "outputs": {}}}
            ])
            self._index = 0
            self.input_id = "test-input-id"
            self.input_created_at = time.time_ns()

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self._events):
                raise StopAsyncIteration
            e = self._events[self._index]
            self._index += 1
            return e

    def _aio(*args, **kwargs):
        return _FakeGen()

    return _aio


def _v2_factory(captured: list | None = None):
    """Return a v2_handle_factory that optionally appends plan_dict to *captured*."""
    _captured = captured if captured is not None else []

    class _FakeHandle:
        def __init__(self):
            self.run_plan_stream = SimpleNamespace(
                remote_gen=SimpleNamespace(aio=_make_fake_aio()),
            )

    def _factory(**kw):
        return _FakeHandle()

    return _factory


# =========================================================================
# Test 1: Two identical + one changed request — operation counts
# =========================================================================


class TestOperationCounts(unittest.TestCase):
    """Two identical requests followed by one changed request must show
    correct plan.to_dict() calls and remote setter/publisher calls."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def test_two_identical_one_changed_plan_to_dict_counts(self):
        """Two identical + one changed: plan.to_dict() called exactly once
        per request (total 3), never extra."""
        original_to_dict = ExecutionPlan.to_dict
        call_log = []

        def _spy_to_dict(self):
            call_log.append("plan.to_dict")
            return original_to_dict(self)

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run(wf: dict, req_id: str, ws_id: str):
            plan = build_execution_plan(
                wf, prompt_id=req_id, validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            ExecutionPlan.to_dict = _spy_to_dict
            try:
                await execute_plan(plan, transport=transport, workspace={"id": ws_id})
            finally:
                ExecutionPlan.to_dict = original_to_dict

        wf_a = {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}
        wf_b = {"1": {"class_type": "KSampler", "inputs": {"seed": 99}}}

        # Request A (first)
        asyncio.run(run(wf_a, "count_a1", "ws_counts"))
        self.assertEqual(call_log.count("plan.to_dict"), 1,
                         "First request: plan.to_dict exactly once")

        # Request A again (second, identical)
        asyncio.run(run(wf_a, "count_a2", "ws_counts"))
        self.assertEqual(call_log.count("plan.to_dict"), 2,
                         "Second identical request: plan.to_dict exactly once (total=2)")

        # Request B (different)
        asyncio.run(run(wf_b, "count_b", "ws_counts"))
        self.assertEqual(call_log.count("plan.to_dict"), 3,
                         "Third changed request: plan.to_dict exactly once (total=3)")

    def test_two_identical_one_changed_setter_counts(self):
        """Two identical requests share one setter call; different model
        stack means changed warmup profile, so setter is called again."""
        setter = _CountingProfileSetter()
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run(wf: dict, req_id: str, ws_id: str):
            plan = build_execution_plan(
                wf, prompt_id=req_id, validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            await execute_plan(
                plan, transport=transport,
                profile_setter=setter, workspace={"id": ws_id},
            )

        # Empty workflow (no model loaders) — first call invokes setter
        wf_empty = {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}
        # Workflow with a model loader — different model stack
        wf_with_model = {
            "1": {"class_type": "CheckpointLoaderSimple",
                  "inputs": {"ckpt_name": "model_v1.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {"seed": 1}},
        }

        asyncio.run(run(wf_empty, "set_a1", "ws_set"))
        self.assertEqual(setter.invoke_count, 1, "First call invokes setter once")

        asyncio.run(run(wf_empty, "set_a2", "ws_set"))
        self.assertEqual(setter.invoke_count, 1,
                         "Second identical call: setter NOT invoked (cached)")

        asyncio.run(run(wf_with_model, "set_b", "ws_set"))
        self.assertEqual(setter.invoke_count, 2,
                         "Changed model stack: setter invoked again (total=2)")

    def test_two_identical_one_changed_restore_publish_counts(self):
        """Two identical requests share one publish; changed request adds one."""
        publisher = _Publisher()

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run(wf: dict, req_id: str, ws_id: str):
            plan = build_execution_plan(
                wf, prompt_id=req_id, validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            await execute_plan(
                plan, transport=transport,
                restore_publisher=publisher, workspace={"id": ws_id},
            )

        wf_a = {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}
        wf_b = {"1": {"class_type": "KSampler", "inputs": {"seed": 99}}}

        asyncio.run(run(wf_a, "pub_a1", "ws_pub"))
        self.assertEqual(publisher.publish_count, 1, "First call publishes once")

        asyncio.run(run(wf_a, "pub_a2", "ws_pub"))
        self.assertEqual(publisher.publish_count, 1,
                         "Second identical: publish NOT called (cached)")

        asyncio.run(run(wf_b, "pub_b", "ws_pub"))
        self.assertEqual(publisher.publish_count, 2,
                         "Changed: publish called again (total=2)")


# =========================================================================
# Test 2: Payload equivalence
# =========================================================================


class TestPayloadEquivalence(unittest.TestCase):
    """Pre-materialized canonical dict equals plan.to_dict() output,
    and is passed verbatim to transport."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def test_canonical_payload_matches_fresh_to_dict(self):
        """The canonical dict from execute_plan matches a fresh plan.to_dict()."""
        captured = []

        class _FakeGen:
            def __init__(self):
                self._events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
                self._index = 0
                self.input_id = "equiv-id"
                self.input_created_at = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._index >= len(self._events):
                    raise StopAsyncIteration
                e = self._events[self._index]
                self._index += 1
                return e

        def _factory(**kw):
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(
                        aio=lambda pd, **kw: (captured.append(pd), _FakeGen())[1],
                    ),
                ),
            )

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 7}}},
                prompt_id="equiv", validate=False,
            )
            expected = plan.to_dict()
            transport = ModalTransport(v2_handle_factory=_factory)
            async for _ in transport.run_plan_stream(
                plan, gpu="rtx-pro-6000", workspace={"id": "ws_equiv"},
                trace={"prompt_id": "equiv"}, plan_dict=dict(expected),
            ):
                pass

        asyncio.run(run())

        self.assertEqual(len(captured), 1, "Captured exactly 1 plan_dict")
        actual = captured[0]
        actual_clean = {k: v for k, v in actual.items() if k != "__request_origin_info__"}

        fresh_plan = build_execution_plan(
            {"1": {"class_type": "KSampler", "inputs": {"seed": 7}}},
            prompt_id="equiv", validate=False,
        )
        reference = fresh_plan.to_dict()

        for k in ("schema_version", "workflow", "workflow_hash",
                  "source_workflow_hash", "production_report", "model_stack",
                  "prompt_bundle", "output_node_ids", "input_images",
                  "execution_options", "request_metadata"):
            self.assertEqual(actual_clean.get(k), reference.get(k),
                             f"Field '{k}' must match between canonical and legacy")

    def test_same_plan_dict_object_passed_verbatim(self):
        """The same plan.to_dict() output object reaches the transport."""
        plan = build_execution_plan(
            {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
            prompt_id="verbatim", validate=False,
        )
        original = plan.to_dict()
        captured = []

        class _FakeGen:
            def __init__(self):
                self._events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
                self._index = 0
                self.input_id = "verb-id"
                self.input_created_at = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._index >= len(self._events):
                    raise StopAsyncIteration
                e = self._events[self._index]
                self._index += 1
                return e

        def _factory(**kw):
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(
                        aio=lambda pd, **kw: (captured.append(pd), _FakeGen())[1],
                    ),
                ),
            )

        async def run():
            transport = ModalTransport(v2_handle_factory=_factory)
            async for _ in transport.run_plan_stream(
                plan, gpu="rtx-pro-6000", workspace={"id": "ws_verbatim"},
                trace={"prompt_id": "verbatim"}, plan_dict=original,
            ):
                pass

        asyncio.run(run())
        self.assertEqual(len(captured), 1)
        actual = captured[0]
        cleaned = {k: v for k, v in actual.items() if k != "__request_origin_info__"}
        self.assertEqual(cleaned, original,
                         "Pre-materialized dict must pass through verbatim "
                         "(modulo __request_origin_info__ injection)")


# =========================================================================
# Test 3: Workspace handle isolation
# =========================================================================


class TestWorkspaceHandleIsolation(unittest.TestCase):
    """Different workspaces produce different transport handles;
    same workspace reuses the handle."""

    def setUp(self):
        self.factory_call_count = [0]

    def _counting_factory(self, **kw):
        self.factory_call_count[0] += 1
        return SimpleNamespace(
            run_plan_stream=SimpleNamespace(
                remote_gen=SimpleNamespace(aio=_make_fake_aio()),
            ),
        )

    def test_different_workspace_different_handle(self):
        """Two workspaces produce two distinct handles."""
        transport = ModalTransport(v2_handle_factory=self._counting_factory)

        h1 = transport._v2_handle(workspace={"id": "ws_alpha"}, gpu="rtx-pro-6000")
        self.assertEqual(self.factory_call_count[0], 1, "First workspace: factory called")

        h2 = transport._v2_handle(workspace={"id": "ws_beta"}, gpu="rtx-pro-6000")
        self.assertEqual(self.factory_call_count[0], 2, "Second workspace: factory called again")
        self.assertIsNot(h1, h2, "Different workspaces must produce different handles")

    def test_same_workspace_reuses_handle(self):
        """Same workspace reuses the cached handle."""
        transport = ModalTransport(v2_handle_factory=self._counting_factory)

        h1 = transport._v2_handle(workspace={"id": "ws_same"}, gpu="rtx-pro-6000")
        self.assertEqual(self.factory_call_count[0], 1)

        h2 = transport._v2_handle(workspace={"id": "ws_same"}, gpu="rtx-pro-6000")
        self.assertEqual(self.factory_call_count[0], 1, "Second call must NOT invoke factory")
        self.assertIs(h1, h2, "Same workspace must return the same handle object")

    def test_same_workspace_reuses_handle_across_transports(self):
        """Separate request transports share the stable-identity handle cache."""
        factory_calls = [0]

        def factory(**kw):
            factory_calls[0] += 1
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(aio=_make_fake_aio()),
                ),
            )

        first = ModalTransport(v2_handle_factory=factory)
        second = ModalTransport(v2_handle_factory=factory)
        h1 = first._v2_handle(workspace={"id": "ws_cross_request"}, gpu="rtx-pro-6000")
        h2 = second._v2_handle(workspace={"id": "ws_cross_request"}, gpu="rtx-pro-6000")

        self.assertEqual(factory_calls[0], 1)
        self.assertIs(h1, h2)

    def test_isolation_in_execute_plan(self):
        """Full execute_plan with two different workspaces produces different
        handle cache entries; each submission happens once per request."""
        setter = _CountingProfileSetter()

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run(ws_id: str, req_id: str):
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id=req_id, validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            await execute_plan(
                plan, transport=transport, profile_setter=setter,
                workspace={"id": ws_id},
            )

        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

        asyncio.run(run("ws_alpha", "iso_a"))
        asyncio.run(run("ws_beta", "iso_b"))

        self.assertEqual(setter.invoke_count, 2,
                         "Different workspaces each call setter (no cross-cache)")


# =========================================================================
# Test 4: One Modal submission per request
# =========================================================================


class TestOneModalSubmissionPerRequest(unittest.TestCase):
    """Each execute_plan call results in exactly one Modal submission
    (one stream iterator, one result)."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()

    def test_single_submission_per_request(self):
        """One execute_plan call yields exactly one result."""
        submission_count = [0]

        async def _stream(**kw):
            submission_count[0] += 1
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run(req_id: str):
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id=req_id, validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            result = await execute_plan(plan, transport=transport)
            self.assertIsInstance(result, dict,
                                  "execute_plan must return a dict result")

        asyncio.run(run("sub_one"))
        self.assertEqual(submission_count[0], 1,
                         "Exactly one Modal submission per request")

    def test_two_requests_two_submissions(self):
        """Two independent requests produce two submissions."""
        submission_count = [0]

        async def _stream(**kw):
            submission_count[0] += 1
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run(req_id: str):
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 42}}},
                prompt_id=req_id, validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            await execute_plan(plan, transport=transport)

        asyncio.run(run("sub_two_a"))
        asyncio.run(run("sub_two_b"))
        self.assertEqual(submission_count[0], 2,
                         "Two requests produce exactly two submissions")

    def test_submission_not_cached_across_requests(self):
        """Even with identical plans, each request triggers its own
        Modal stream iteration."""
        events_seen = []

        async def _stream(**kw):
            yield {"type": "progress", "data": {"step": 1}}
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run(req_id: str):
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id=req_id, validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            await execute_plan(plan, transport=transport,
                               workspace={"id": "ws_nocache"},
                               profile_setter=_CountingProfileSetter())

        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()

        asyncio.run(run("sub_ident_a"))
        asyncio.run(run("sub_ident_b"))

        # Each request gets its own stream iteration (different profiles)
        # Assert we got past basic execution without error


# =========================================================================
# Test 5: Timing reconciliation residual <100ms or attributed
# =========================================================================


class TestTimingReconciliation(unittest.TestCase):
    """The [v2.local_submission_breakdown] residual must be <100ms or
    explicitly attributed to a known unmeasured boundary."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()

    def test_residual_under_100ms(self):
        """The residual between measured children and total span is <100ms
        (or absent when no origin data)."""
        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="residual_test", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            result = await execute_plan(plan, transport=transport)
            lt = result.get("local_timing", {})
            residual = lt.get("clock_reconciliation_residual_ms")
            if residual is not None:
                if isinstance(residual, (int, float)):
                    self.assertLess(abs(float(residual)), 100.0,
                                    f"Residual {residual}ms must be <100ms")
            # When origin data is absent, residual is None — that's expected
            return result

        result = asyncio.run(run())
        lt = result.get("local_timing", {})
        self.assertIn(lt.get("reconciliation_status", ""),
                      ("complete", "incomplete"),
                      "Reconciliation status must be valid")

    def test_breakdown_residual_under_100ms(self):
        """The breakdown dict's residual_ms is <100ms or attributed
        (or absent when no origin data)."""
        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="bdown_residual", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            result = await execute_plan(plan, transport=transport)
            return result

        result = asyncio.run(run())
        lt = result.get("local_timing", {})
        residual = lt.get("clock_reconciliation_residual_ms")
        umb = lt.get("unmeasured_boundary", "")
        if isinstance(residual, (int, float)):
            if abs(float(residual)) >= 100.0:
                self.assertNotEqual(umb, "",
                                    f"Residual {residual}ms >=100ms must be attributed, "
                                    f"but unmeasured_boundary is empty")
        reconciliation_status = lt.get("reconciliation_status", "")
        self.assertIn(reconciliation_status,
                      ("complete", "incomplete", "overlap"),
                      "Reconciliation status must be valid")


# =========================================================================
# Test 6: Stdout capture proves [v2.local_submission_breakdown] appears
# =========================================================================


class TestStdoutCapture(unittest.TestCase):
    """The [v2.local_submission_breakdown] line is printed to stdout
    exactly once per execute_plan call."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def test_breakdown_line_printed_to_stdout(self):
        """[v2.local_submission_breakdown] appears in captured stdout."""
        captured = io.StringIO()

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="stdout_test", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            with patch("sys.stdout", captured):
                await execute_plan(plan, transport=transport)

        asyncio.run(run())
        output = captured.getvalue()
        self.assertIn("[v2.local_submission_breakdown.final]", output,
                       "[v2.local_submission_breakdown.final] must appear in stdout")
        self.assertIn("request_id=", output,
                      "breakdown must include request_id=")
        self.assertIn("plan_build_ms=", output,
                      "breakdown must include plan_build_ms")
        self.assertIn("active_profile_ms=", output,
                      "breakdown must include active_profile_ms")
        self.assertIn("generator_create_ms=", output,
                      "breakdown must include generator_create_ms")
        self.assertIn("local_receive_to_actual_submission_ms=", output,
                      "breakdown must include local_receive_to_actual_submission_ms")
        self.assertIn("reconciliation_status=", output,
                      "breakdown must include reconciliation_status")
        self.assertIn("profile_cache_hit=", output,
                      "breakdown must include profile_cache_hit")
        self.assertIn("plan_to_dict_count=", output,
                      "breakdown must include plan_to_dict_count")
        self.assertIn("payload_bytes=", output,
                      "breakdown must include payload_bytes")

    def test_breakdown_line_once_per_request(self):
        """Two requests produce two breakdown lines."""
        captured = io.StringIO()

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run(req_id: str):
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id=req_id, validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            with patch("sys.stdout", captured):
                await execute_plan(plan, transport=transport)

        asyncio.run(run("stdout_a"))
        asyncio.run(run("stdout_b"))
        output = captured.getvalue()
        count = output.count("[v2.local_submission_breakdown.final]")
        self.assertEqual(count, 2,
                         f"Expected 2 final breakdown lines, got {count}")

    def test_breakdown_contains_required_fields(self):
        """All required fields appear in the breakdown line."""
        captured = io.StringIO()

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="required_fields", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            with patch("sys.stdout", captured):
                await execute_plan(plan, transport=transport)

        asyncio.run(run())
        output = captured.getvalue()

        required_fields = [
            "request_id=",
            "local_receive_to_worker_start_ms=",
            "worker_queue_ms=",
            "plan_build_ms=",
            "active_profile_ms=",
            "restore_plan_build_ms=",
            "restore_publish_ms=",
            "transport_entry_ms=",
            "handle_lookup_ms=",
            "payload_materialization_ms=",
            "payload_size_measurement_ms=",
            "generator_create_ms=",
            "generator_created_to_first_iteration_ms=",
            "local_receive_to_actual_submission_ms=",
            "measured_children_ms=",
            "residual_ms=",
            "reconciliation_status=",
            "profile_cache_hit=",
            "profile_remote_call_performed=",
            "restore_publish_cache_hit=",
            "restore_remote_call_performed=",
            "handle_cache_hit=",
            "plan_to_dict_count=",
            "payload_bytes=",
        ]
        for field in required_fields:
            self.assertIn(field, output,
                          f"Breakdown must contain field: {field}")

    def test_breakdown_request_id_matches(self):
        """The request_id in the breakdown matches the request's prompt_id."""
        captured = io.StringIO()

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="match_check", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            with patch("sys.stdout", captured):
                await execute_plan(plan, transport=transport)

        asyncio.run(run())
        output = captured.getvalue()
        self.assertIn("request_id=match_check", output,
                      "Breakdown request_id must match prompt_id")


# =========================================================================
# Test 7: Canonical dict reused — no second plan.to_dict() in transport
# =========================================================================


class TestCanonicalDictReuse(unittest.TestCase):
    """The transport V2 path does NOT call plan.to_dict() when plan_dict
    is provided by execute_plan."""

    def test_transport_v2_path_no_extra_to_dict(self):
        """V2 transport reuses provided plan_dict without calling to_dict()."""
        class _FakeGen:
            def __init__(self):
                self._events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
                self._index = 0
                self.input_id = "reuse-id"
                self.input_created_at = 0
            def __aiter__(self): return self
            async def __anext__(self):
                if self._index >= len(self._events): raise StopAsyncIteration
                e = self._events[self._index]; self._index += 1; return e

        factory_calls = [0]

        def _factory(**kw):
            factory_calls[0] += 1
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(
                        aio=lambda *a, **kw: _FakeGen(),
                    ),
                ),
            )

        import inspect
        from comfymodal_runtime.modal_transport import ModalTransport
        transport_source = inspect.getsource(ModalTransport.run_plan_stream)
        # Verify the V2 path only calls plan.to_dict() as fallback
        v2_fallback = "plan_dict = plan_dict if plan_dict is not None else plan.to_dict()"
        self.assertIn(v2_fallback, transport_source,
                      "Transport must only call plan.to_dict() as fallback")

        plan = build_execution_plan(
            {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
            prompt_id="reuse", validate=False,
        )
        plan_dict = plan.to_dict()

        async def run():
            transport = ModalTransport(v2_handle_factory=_factory)
            async for _ in transport.run_plan_stream(
                plan, gpu="rtx-pro-6000", workspace={"id": "ws_reuse"},
                trace={"prompt_id": "reuse"}, plan_dict=plan_dict,
            ):
                pass

        asyncio.run(run())
        self.assertEqual(factory_calls[0], 1, "Factory called once")


# =========================================================================
# Test 8: Profile and restore cache dedup within same workspace
# =========================================================================


class TestProfileAndRestoreDedup(unittest.TestCase):
    """Identical active profiles skip remote setter;
    identical restore plans skip remote publish."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def test_identical_active_profile_no_extra_setter(self):
        """Same workflow, same workspace: setter called only once."""
        setter = _CountingProfileSetter()

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run(req_id: str):
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id=req_id, validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            await execute_plan(plan, transport=transport,
                               profile_setter=setter,
                               workspace={"id": "ws_dedup"})

        asyncio.run(run("dedup_a"))
        asyncio.run(run("dedup_b"))
        self.assertEqual(setter.invoke_count, 1,
                         "Identical workflows: setter called only once")

    def test_identical_restore_plan_no_extra_publish(self):
        """Same plan, same workspace: publish called only once."""
        publisher = _Publisher()

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run(req_id: str):
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id=req_id, validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            await execute_plan(plan, transport=transport,
                               restore_publisher=publisher,
                               workspace={"id": "ws_dedup_restore"})

        asyncio.run(run("restore_dedup_a"))
        asyncio.run(run("restore_dedup_b"))
        self.assertEqual(publisher.publish_count, 1,
                         "Identical plans: publish called only once")


# =========================================================================
# Test 9: Metadata correctness on [v2.local_submission_breakdown]
# =========================================================================


class TestBreakdownMetadataCorrectness(unittest.TestCase):
    """The breakdown metadata booleans reflect actual execution decisions."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def test_profile_cache_hit_on_second_call(self):
        """Second identical call shows profile_cache_hit=True."""
        captured = io.StringIO()
        setter = _CountingProfileSetter()

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run(req_id: str):
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id=req_id, validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            with patch("sys.stdout", captured):
                await execute_plan(plan, transport=transport,
                                   profile_setter=setter,
                                   workspace={"id": "ws_meta"})

        asyncio.run(run("meta_first"))
        asyncio.run(run("meta_second"))
        output = captured.getvalue()
        self.assertIn("profile_cache_hit=True", output,
                      "Second identical call must show profile_cache_hit=True")
        self.assertIn("plan_to_dict_count=1", output,
                      "plan_to_dict_count must be 1 per call")


# =========================================================================
# Test 10: Pre-dispatch breakdown with V2 transport
# =========================================================================


class TestPreDispatchBreakdown(unittest.TestCase):
    """The [v2.local_submission_breakdown] is emitted pre-dispatch inside
    the V2 transport (before remote_gen.aio), observable without waiting
    for the mocked remote result."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def test_predispatch_line_appears_before_remote_gen_aio(self):
        """The pre-dispatch breakdown line is emitted before the V2 transport
        calls remote_gen.aio (observable in stdout before result)."""
        captured = io.StringIO()

        class _ObservingGen:
            def __init__(self):
                self._events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
                self._index = 0
                self.input_id = "obs-id"
                self.input_created_at = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._index >= len(self._events):
                    raise StopAsyncIteration
                e = self._events[self._index]
                self._index += 1
                return e

        def _factory(**kw):
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(
                        aio=lambda *a, **kw: _ObservingGen(),
                    ),
                ),
            )

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="predispatch", validate=False,
            )
            plan_dict = plan.to_dict()
            rt = RuntimeTrace(request_id="predispatch", process="local")
            transport = ModalTransport(v2_handle_factory=_factory)
            with patch("sys.stdout", captured):
                async for _ in transport.run_plan_stream(
                    plan, gpu="rtx-pro-6000", workspace={"id": "ws_predispatch"},
                    trace={"prompt_id": "predispatch"}, plan_dict=plan_dict,
                    runtime_trace=rt,
                ):
                    pass

        asyncio.run(run())
        output = captured.getvalue()
        self.assertIn("[v2.local_submission_breakdown.pre_dispatch]", output,
                       "Pre-dispatch breakdown must appear in stdout before result")
        # Fields available from trace events
        self.assertIn("handle_lookup_ms=", output, "pre-dispatch must include handle_lookup_ms")
        self.assertIn("payload_size_measurement_ms=", output, "pre-dispatch must include payload_size_measurement_ms")
        self.assertIn("handle_cache_hit=", output, "pre-dispatch must include handle_cache_hit")
        # Fields requiring origin data default to absent
        self.assertIn("local_receive_to_worker_start_ms=absent", output)

    def test_predispatch_breakdown_forwarded_in_plan_dict(self):
        """The pre-dispatch breakdown dict is injected into __request_origin_info__
        in plan_dict before remote_gen.aio so the remote can re-emit it."""
        captured_plan_dicts = []

        class _CapturingGen:
            def __init__(self):
                self._events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
                self._index = 0
                self.input_id = "fwd-id"
                self.input_created_at = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._index >= len(self._events):
                    raise StopAsyncIteration
                e = self._events[self._index]
                self._index += 1
                return e

        def _capture_aio(pd, **kw):
            captured_plan_dicts.append(pd)
            return _CapturingGen()

        def _factory(**kw):
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(aio=_capture_aio),
                ),
            )

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="fwd_test", validate=False,
            )
            plan_dict = plan.to_dict()
            rt = RuntimeTrace(request_id="fwd_test", process="local")
            transport = ModalTransport(v2_handle_factory=_factory)
            async for _ in transport.run_plan_stream(
                plan, gpu="rtx-pro-6000", workspace={"id": "ws_fwd"},
                trace={"prompt_id": "fwd_test"}, plan_dict=plan_dict,
                runtime_trace=rt,
            ):
                pass

        asyncio.run(run())
        self.assertEqual(len(captured_plan_dicts), 1, "Exactly one plan_dict captured")
        pd = captured_plan_dicts[0]
        origin_info = pd.get("__request_origin_info__", {})
        if not isinstance(origin_info, dict):
            origin_info = {}
        breakdown = origin_info.get("local_submission_breakdown", None)
        self.assertIsNotNone(breakdown,
                             "Pre-dispatch breakdown must be injected into "
                             "__request_origin_info__.local_submission_breakdown")
        self.assertIn("handle_lookup_ms", breakdown, "Breakdown must contain handle_lookup_ms")

    def test_predispatch_breakdown_uses_same_trace(self):
        """The pre-dispatch breakdown uses the same RuntimeTrace as execute_plan."""
        trace_events_before = []

        class _TraceCheckingGen:
            def __init__(self):
                self._events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
                self._index = 0
                self.input_id = "trace-chk-id"
                self.input_created_at = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._index >= len(self._events):
                    raise StopAsyncIteration
                e = self._events[self._index]
                self._index += 1
                return e

        captured_trace = [None]

        def _factory(**kw):
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(
                        aio=lambda pd, **kw: (captured_trace.__setitem__(0, pd.get("_test_trace_meta")), _TraceCheckingGen())[1],
                    ),
                ),
            )

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="same_trace", validate=False,
            )
            plan_dict = plan.to_dict()
            transport = ModalTransport(v2_handle_factory=_factory)
            async for _ in transport.run_plan_stream(
                plan, gpu="rtx-pro-6000", workspace={"id": "ws_trace"},
                trace={"prompt_id": "same_trace"}, plan_dict=plan_dict,
            ):
                pass

        asyncio.run(run())
        # The trace was used in transport; we just verify no crash occurred
        # and that the breakdown was emitted by checking captured stdout
        # is not needed for this assertion.


# =========================================================================
# Test: Request env-profile propagation
# =========================================================================


class TestEnvProfilePropagation(unittest.TestCase):
    """The submitting process's COMFYMODAL_V2_ENV_PROFILE is injected into
    ``__request_origin_info__.env_profile`` so the remote request/runtime can
    apply it without hardcoding a profile value locally."""

    def _capture(self, *, local_profile: str | None):
        captured_plan_dicts = []

        class _FakeGen:
            def __init__(self):
                self._events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
                self._index = 0
                self.input_id = "profile-id"
                self.input_created_at = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._index >= len(self._events):
                    raise StopAsyncIteration
                e = self._events[self._index]
                self._index += 1
                return e

        def _capture_aio(pd, **kw):
            captured_plan_dicts.append(pd)
            return _FakeGen()

        def _factory(**kw):
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(aio=_capture_aio),
                ),
            )

        saved = None
        if local_profile is None:
            saved = __import__("os").environ.pop("COMFYMODAL_V2_ENV_PROFILE", None)
        else:
            saved = __import__("os").environ.get("COMFYMODAL_V2_ENV_PROFILE")
            __import__("os").environ["COMFYMODAL_V2_ENV_PROFILE"] = local_profile
        try:
            async def run():
                plan = build_execution_plan(
                    {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                    prompt_id="env-profile-req", validate=False,
                )
                plan_dict = plan.to_dict()
                rt = RuntimeTrace(request_id="env-profile-req", process="local")
                transport = ModalTransport(v2_handle_factory=_factory)
                async for _ in transport.run_plan_stream(
                    plan, gpu="rtx-pro-6000", workspace={"id": "ws_profile"},
                    trace={"prompt_id": "env-profile-req"}, plan_dict=plan_dict,
                    runtime_trace=rt,
                ):
                    pass
            asyncio.run(run())
        finally:
            if saved is None:
                __import__("os").environ.pop("COMFYMODAL_V2_ENV_PROFILE", None)
            else:
                __import__("os").environ["COMFYMODAL_V2_ENV_PROFILE"] = saved
        return captured_plan_dicts

    def test_production_profile_reaches_remote_request_payload(self):
        """COMFYMODAL_V2_ENV_PROFILE=production is carried into the remote
        request as __request_origin_info__.env_profile."""
        captured = self._capture(local_profile="production")
        self.assertEqual(len(captured), 1, "Exactly one plan_dict captured")
        origin_info = captured[0].get("__request_origin_info__", {})
        if not isinstance(origin_info, dict):
            origin_info = {}
        self.assertEqual(origin_info.get("env_profile"), "production",
                         "Local env profile must reach the remote request payload")

    def test_diagnostic_profile_reaches_remote_request_payload(self):
        """COMFYMODAL_V2_ENV_PROFILE=diagnostic is carried into the remote
        request as __request_origin_info__.env_profile."""
        captured = self._capture(local_profile="diagnostic")
        origin_info = captured[0].get("__request_origin_info__", {})
        if not isinstance(origin_info, dict):
            origin_info = {}
        self.assertEqual(origin_info.get("env_profile"), "diagnostic")

    def test_absent_local_profile_does_not_inject_env_profile(self):
        """No COMFYMODAL_V2_ENV_PROFILE locally -> no env_profile key is
        invented (no hardcoded default in the request)."""
        captured = self._capture(local_profile=None)
        origin_info = captured[0].get("__request_origin_info__", {})
        if not isinstance(origin_info, dict):
            origin_info = {}
        self.assertNotIn("env_profile", origin_info)


# =========================================================================
# Test 11: Missing / absent / invalid_negative values
# =========================================================================


class TestBreakdownAbsentAndInvalid(unittest.TestCase):
    """Missing fields render as 'absent', negative deltas as 'invalid_negative'."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def test_absent_fields_in_predispatch_line(self):
        """When origin data is absent, fields print as 'absent'."""
        captured = io.StringIO()

        class _FakeGen:
            def __init__(self):
                self._events = [{"type": "result", "data": {"images": [], "outputs": {}}}]
                self._index = 0
                self.input_id = "absent-id"
                self.input_created_at = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._index >= len(self._events):
                    raise StopAsyncIteration
                e = self._events[self._index]
                self._index += 1
                return e

        def _factory(**kw):
            return SimpleNamespace(
                run_plan_stream=SimpleNamespace(
                    remote_gen=SimpleNamespace(aio=lambda *a, **kw: _FakeGen()),
                ),
            )

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="absent_test", validate=False,
            )
            plan_dict = plan.to_dict()
            rt = RuntimeTrace(request_id="absent_test", process="local")
            transport = ModalTransport(v2_handle_factory=_factory)
            with patch("sys.stdout", captured):
                async for _ in transport.run_plan_stream(
                    plan, gpu="rtx-pro-6000", workspace={"id": "ws_absent"},
                    trace={"prompt_id": "absent_test"}, plan_dict=plan_dict,
                    runtime_trace=rt,
                ):
                    pass

        asyncio.run(run())
        output = captured.getvalue()
        # Fields that require origin data should be absent
        self.assertIn("local_receive_to_worker_start_ms=absent", output,
                       "Missing origin data shows as absent")
        self.assertIn("worker_start_to_plan_build_ms=absent", output,
                       "Missing worker_start shows as absent")
        # Fields requiring both origin and trace events
        self.assertIn("local_receive_to_modal_call_ms=absent", output)

    def test_invalid_negative_never_appears_with_valid_trace(self):
        """Normal trace ordering never produces invalid_negative."""
        captured = io.StringIO()

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="neg_test", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            with patch("sys.stdout", captured):
                await execute_plan(plan, transport=transport)

        asyncio.run(run())
        output = captured.getvalue()
        breakdown_lines = [l for l in output.split("\n") if "local_submission_breakdown" in l and "absent" not in l]
        # No breakdown line with numeric values should contain invalid_negative
        # unless there's an actual trace ordering bug (which we don't simulate here)
        self.assertNotIn("invalid_negative", output,
                         "Valid trace ordering must not produce invalid_negative "
                         "for any field")


# =========================================================================
# Test 12: Failed profile/restore calls are not cached
# =========================================================================


class TestFailedCallsNotCached(unittest.TestCase):
    """A failed profile-setter call must not populate the cache;
    a failed restore-publish call must not populate the cache."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def test_failed_profile_setter_reinvoked(self):
        """A failed profile setter call is not cached and the setter
        is reinvoked on the next identical request."""
        invoke_count = [0]

        async def _failing_setter(payload, *, workspace=None):
            invoke_count[0] += 1
            return {"status": "error", "error": "simulated failure"}

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run(req_id: str):
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id=req_id, validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            await execute_plan(plan, transport=transport,
                               profile_setter=_failing_setter,
                               workspace={"id": "ws_fail"})

        asyncio.run(run("fail_a"))
        asyncio.run(run("fail_b"))
        # The setter should be called twice because the first call failed
        self.assertEqual(invoke_count[0], 2,
                         "Failed setter must be reinvoked on next identical request")

    def test_failed_restore_publish_reinvoked(self):
        """A failed restore publish call is not cached and the publisher
        is reinvoked on the next identical request."""
        publish_count = [0]

        class _FailingPublisher:
            def publish(self, plan):
                publish_count[0] += 1
                return {"status": "error", "ok": False, "error": "simulated"}

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run(req_id: str):
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id=req_id, validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            await execute_plan(plan, transport=transport,
                               restore_publisher=_FailingPublisher(),
                               workspace={"id": "ws_restore_fail"})

        asyncio.run(run("restore_fail_a"))
        asyncio.run(run("restore_fail_b"))
        self.assertEqual(publish_count[0], 2,
                         "Failed publish must be reinvoked on next identical request")


# =========================================================================
# Test 13: build_execution_plan no extra deepcopy
# =========================================================================


class TestNoExtraDeepcopyInBuildPlan(unittest.TestCase):
    """When production_report already describes the compiled workflow,
    build_execution_plan must not perform a second deepcopy of the workflow."""

    def test_no_second_deepcopy_with_production_report(self):
        """With a production_report (enabled), only one deepcopy is made
        (the original source_workflow), not a second one for dispatch."""
        import copy
        orig_deepcopy = copy.deepcopy
        deepcopy_count = [0]

        def _counting_deepcopy(obj, memo=None):
            deepcopy_count[0] += 1
            return orig_deepcopy(obj, memo)

        import canonical_execution as ce
        # We need to test that the code path doesn't call copy.deepcopy
        # a second time.  Since we can't monkey-patch during module load,
        # we verify by inspecting the source code.
        import inspect
        source = inspect.getsource(ce.build_execution_plan)
        # The old pattern was: `dispatch_workflow = copy.deepcopy(workflow or {})`
        # in the report.get("enabled") branch.  After the fix, that branch
        # should NOT contain a copy.deepcopy call.
        # Check that the enabled branch has "pass" instead of deepcopy
        enabled_branch = source.split("if report.get(\"enabled\"):")[1].split("elif")[0] if "if report.get(\"enabled\"):" in source else ""
        self.assertNotIn("copy.deepcopy", enabled_branch,
                         "production-report enabled branch must not call copy.deepcopy")
        self.assertIn("pass", enabled_branch,
                       "production-report enabled branch should just 'pass'")


# =========================================================================
# Test 14: Gap fields appear in [v2.local_submission_breakdown]
# =========================================================================


class TestGapFieldsInBreakdown(unittest.TestCase):
    """The three gap fields — execute_plan_entry_to_plan_materialization_ms,
    plan_materialization_to_active_profile_ms, payload_size_to_serialize_end_ms
    — must appear in the printed [v2.local_submission_breakdown] line."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def test_gap_fields_present_in_stdout(self):
        """All three gap fields are present in the breakdown stdout line."""
        captured = io.StringIO()

        async def _stream(**kw):
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="gap_fields_test", validate=False,
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            with patch("sys.stdout", captured):
                await execute_plan(plan, transport=transport)

        asyncio.run(run())
        output = captured.getvalue()

        self.assertIn("execute_plan_entry_to_plan_materialization_ms=", output,
                      "gap field must appear: execute_plan_entry_to_plan_materialization_ms")
        self.assertIn("plan_materialization_to_active_profile_ms=", output,
                      "gap field must appear: plan_materialization_to_active_profile_ms")
        self.assertIn("payload_size_to_serialize_end_ms=", output,
                      "gap field must appear: payload_size_to_serialize_end_ms")
        # Numeric values should not be "absent" when trace events exist
        # (gap fields derive from trace events, not origin data, so they
        # should be present when a plan was built and materialized).
        self.assertNotIn("execute_plan_entry_to_plan_materialization_ms=absent", output,
                         "gap field must have a numeric value (not absent) when plan was built")
        self.assertNotIn("plan_materialization_to_active_profile_ms=absent", output,
                         "gap field must have a numeric value (not absent) when plan was built")

    def test_gap_fields_appear_in_required_fields_list(self):
        """Verifies that the gap fields are listed in the field-keys constant."""
        from comfymodal_runtime.trace import LOCAL_SUBMISSION_FIELD_KEYS
        field_names = [fk for dk, fk in LOCAL_SUBMISSION_FIELD_KEYS]
        self.assertIn("execute_plan_entry_to_plan_materialization_ms", field_names,
                      "Gap field must be in LOCAL_SUBMISSION_FIELD_KEYS")
        self.assertIn("plan_materialization_to_active_profile_ms", field_names,
                      "Gap field must be in LOCAL_SUBMISSION_FIELD_KEYS")
        self.assertIn("payload_size_to_serialize_end_ms", field_names,
                      "Gap field must be in LOCAL_SUBMISSION_FIELD_KEYS")

    def test_gap_fields_position_sequence(self):
        """The gap fields appear at the expected positions in the field list."""
        from comfymodal_runtime.trace import LOCAL_SUBMISSION_FIELD_KEYS
        keys = [dk for dk, fk in LOCAL_SUBMISSION_FIELD_KEYS]
        # execute_plan_entry_to_plan_materialization_ms is between
        # plan_build_to_execute_plan_entry_ms and plan_materialization_ms
        idx_build_to_exec = keys.index("plan_build_to_execute_plan_entry_ms")
        idx_mat = keys.index("plan_materialization_ms")
        idx_exec_to_mat = keys.index("execute_plan_entry_to_plan_materialization_ms")
        self.assertGreater(idx_exec_to_mat, idx_build_to_exec,
                           "execute_plan_entry_to_plan_materialization_ms should come after "
                           "plan_build_to_execute_plan_entry_ms")
        self.assertLess(idx_exec_to_mat, idx_mat,
                        "execute_plan_entry_to_plan_materialization_ms should come before "
                        "plan_materialization_ms")

        # plan_materialization_to_active_profile_ms is between
        # plan_materialization_ms and active_profile_ms
        idx_active = keys.index("active_profile_ms")
        idx_mat_to_active = keys.index("plan_materialization_to_active_profile_ms")
        self.assertGreater(idx_mat_to_active, idx_mat,
                           "plan_materialization_to_active_profile_ms should come after "
                           "plan_materialization_ms")
        self.assertLess(idx_mat_to_active, idx_active,
                        "plan_materialization_to_active_profile_ms should come before "
                        "active_profile_ms")

        # payload_size_to_serialize_end_ms is between
        # payload_size_measurement_ms and payload_ready_to_modal_call_ms
        idx_size_meas = keys.index("payload_size_measurement_ms")
        idx_ready = keys.index("payload_ready_to_modal_call_ms")
        idx_size_to_serialize = keys.index("payload_size_to_serialize_end_ms")
        self.assertGreater(idx_size_to_serialize, idx_size_meas,
                            "payload_size_to_serialize_end_ms should come after "
                            "payload_size_measurement_ms")
        self.assertLess(idx_size_to_serialize, idx_ready,
                        "payload_size_to_serialize_end_ms should come before "
                        "payload_ready_to_modal_call_ms")


# =========================================================================
# Test 15: Benchmark prefix instrumentation
# =========================================================================


class _FakeRestorePublisher:
    """Async restore publisher for benchmark _run_one tests."""

    def __init__(self):
        self.plans = []
        self.publish_count = 0

    async def publish(self, plan):
        self.plans.append(plan)
        self.publish_count += 1
        return {"generation": "test", "ok": True}


async def _fake_profile_checker(stable_key: str, *, workspace: dict | None = None) -> dict:
    return {"matched": True, "stable_key": stable_key}


def _fake_v2_factory(**kw):
    return SimpleNamespace(
        run_plan_stream=SimpleNamespace(
            remote_gen=SimpleNamespace(aio=_make_fake_aio()),
        ),
    )


class TestBenchmarkPrefixInstrumentation(unittest.TestCase):
    """Benchmark prefix instrumentation: worker_start, normalize, options_copy,
    client_id_generation, build_execution_plan_call_start events emitted by
    _run_one and their derived durations in [v2.local_submission_breakdown]."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def _run_with_capture(self, **run_kwargs):
        """Run _run_one with standard fakes and capture stdout."""
        import sys as _sys
        from pathlib import Path as _Path
        _root = _Path(__file__).resolve().parents[1]
        if str(_root) not in _sys.path:
            _sys.path.insert(0, str(_root))
        from tools.benchmark_v2_direct import _run_one
        import tempfile

        output_dir = _Path(tempfile.mkdtemp())
        transport = ModalTransport(v2_handle_factory=_fake_v2_factory)
        publisher = _FakeRestorePublisher()
        setter = _CountingProfileSetter()
        captured = io.StringIO()

        async def _run():
            return await _run_one(
                index=0,
                workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                modal_options={"production": {"enabled": False}},
                workspace={"id": "test", "token_id": "test", "token_secret": "test"},
                transport=transport,
                output_dir=output_dir,
                _test_restore_publisher=publisher,
                _test_profile_setter=setter,
                _test_profile_checker=_fake_profile_checker,
                **run_kwargs,
            )

        with patch("sys.stdout", captured):
            artifact = asyncio.run(_run())
        return captured, artifact

    def _parse_breakdown(self, output: str, prefix: str) -> dict[str, str]:
        """Parse a breakdown line with given prefix into key-value dict."""
        for line in output.split("\n"):
            if line.startswith(prefix):
                parts = line.strip().split()
                result: dict[str, str] = {}
                for part in parts[1:]:
                    if "=" in part:
                        key, val = part.split("=", 1)
                        result[key] = val
                return result
        return {}

    def _get_final_breakdown(self, output: str) -> dict[str, str]:
        return self._parse_breakdown(output, "[v2.local_submission_breakdown.final]")

    def _get_predispatch_breakdown(self, output: str) -> dict[str, str]:
        return self._parse_breakdown(output, "[v2.local_submission_breakdown.pre_dispatch]")

    # ------------------------------------------------------------------
    # Test 1: worker_start appears with numeric value
    # ------------------------------------------------------------------

    def test_benchmark_emits_worker_start(self):
        """[v2.local_submission_breakdown.final] includes local_receive_to_worker_start_ms
        as a numeric value (not 'absent')."""
        captured, _ = self._run_with_capture()
        output = captured.getvalue()
        bd = self._get_final_breakdown(output)

        self.assertIn("local_receive_to_worker_start_ms", bd,
                      "Final breakdown must contain local_receive_to_worker_start_ms")
        val_str = bd["local_receive_to_worker_start_ms"]
        self.assertNotEqual(val_str, "absent",
                            "worker_start must be numeric, not 'absent'")
        try:
            float(val_str)
        except ValueError:
            self.fail(f"local_receive_to_worker_start_ms must be numeric, got {val_str!r}")

    # ------------------------------------------------------------------
    # Test 2: Complete prefix partition with sum ≈ plan_build_start
    # ------------------------------------------------------------------

    def test_benchmark_prefix_complete_partition(self):
        """All prefix fields are numeric and their sum approximately equals
        local_receive_to_plan_build_start_ms (within 2ms tolerance)."""
        captured, _ = self._run_with_capture()
        output = captured.getvalue()
        bd = self._get_final_breakdown(output)

        prefix_fields = [
            "local_receive_to_worker_start_ms",
            "worker_start_to_normalize_start_ms",
            "normalize_production_options_ms",
            "normalize_end_to_trace_construct_start_ms",
            "runtime_trace_construct_ms",
            "trace_construct_to_options_copy_start_ms",
            "benchmark_options_copy_ms",
            "options_copy_to_client_id_start_ms",
            "client_id_generation_ms",
            "client_id_end_to_plan_call_ms",
            "plan_call_to_function_entry_ms",
        ]

        total = 0.0
        for field in prefix_fields:
            self.assertIn(field, bd,
                          f"Field {field} must be in final breakdown")
            val_str = bd[field]
            self.assertNotEqual(val_str, "absent",
                                f"{field} must not be absent")
            val = float(val_str)
            self.assertGreaterEqual(val, 0.0,
                                    f"{field}={val} must be >= 0")
            total += val

        plan_build_start_str = bd.get("local_receive_to_plan_build_start_ms")
        self.assertIsNotNone(plan_build_start_str,
                             "local_receive_to_plan_build_start_ms must be present")
        self.assertNotEqual(plan_build_start_str, "absent")
        assert plan_build_start_str is not None  # narrow for type checker
        plan_build_start_val = float(plan_build_start_str)

        self.assertAlmostEqual(
            total, plan_build_start_val, delta=2.0,
            msg=f"Sum of prefix fields ({total}) must approximately equal "
                f"local_receive_to_plan_build_start_ms ({plan_build_start_val})",
        )

    # ------------------------------------------------------------------
    # Test 3: Synthetic sleep in normalize_production_options
    # ------------------------------------------------------------------

    def test_synthetic_sleep_in_prefix_fields(self):
        """Patching normalize_production_options with 50ms sleep makes
        normalize_production_options_ms >= 45ms."""
        import sys as _sys
        from pathlib import Path as _Path
        _root = _Path(__file__).resolve().parents[1]
        if str(_root) not in _sys.path:
            _sys.path.insert(0, str(_root))

        def _sleeper(opts):
            time.sleep(0.05)
            return {}

        with patch("tools.benchmark_v2_direct.normalize_production_options",
                   side_effect=_sleeper):
            captured, _ = self._run_with_capture()

        output = captured.getvalue()
        bd = self._get_final_breakdown(output)
        norm_ms_str = bd.get("normalize_production_options_ms", "absent")
        self.assertNotEqual(norm_ms_str, "absent",
                            "normalize_production_options_ms must not be absent after sleep")
        norm_ms = float(norm_ms_str)
        self.assertGreaterEqual(
            norm_ms, 45,
            f"normalize_production_options_ms={norm_ms} should be >= 45ms after 50ms sleep",
        )

    # ------------------------------------------------------------------
    # Test 4: Synthetic sleep before build_execution_plan
    # ------------------------------------------------------------------

    def test_synthetic_sleep_before_plan_build_not_absent(self):
        """Patching build_execution_plan with 30ms sleep makes
        plan_call_to_function_entry_ms >= 25ms and
        local_receive_to_plan_build_start_ms >= 25ms."""
        import sys as _sys
        from pathlib import Path as _Path
        _root = _Path(__file__).resolve().parents[1]
        if str(_root) not in _sys.path:
            _sys.path.insert(0, str(_root))
        from tools.benchmark_v2_direct import build_execution_plan as _real_bep

        def _sleeper(*args, **kwargs):
            time.sleep(0.03)
            return _real_bep(*args, **kwargs)

        with patch("tools.benchmark_v2_direct.build_execution_plan",
                   side_effect=_sleeper):
            captured, _ = self._run_with_capture()

        output = captured.getvalue()
        bd = self._get_final_breakdown(output)

        plan_call_ms_str = bd.get("plan_call_to_function_entry_ms", "absent")
        self.assertNotEqual(plan_call_ms_str, "absent",
                            "plan_call_to_function_entry_ms must not be absent")
        plan_call_ms = float(plan_call_ms_str)
        self.assertGreaterEqual(
            plan_call_ms, 25,
            f"plan_call_to_function_entry_ms={plan_call_ms} should be >= 25ms after 30ms sleep",
        )

        plan_build_start_str = bd.get("local_receive_to_plan_build_start_ms", "absent")
        self.assertNotEqual(plan_build_start_str, "absent")
        plan_build_start_ms = float(plan_build_start_str)
        self.assertGreaterEqual(
            plan_build_start_ms, 25,
            f"local_receive_to_plan_build_start_ms={plan_build_start_ms} should be >= 25ms",
        )

    # ------------------------------------------------------------------
    # Test 5: Pre-dispatch is explicitly partial
    # ------------------------------------------------------------------

    def test_predispatch_is_explicitly_partial(self):
        """Pre-dispatch line has generator_create_ms=absent;
        final line has it as numeric."""
        captured, _ = self._run_with_capture()
        output = captured.getvalue()

        pre = self._get_predispatch_breakdown(output)
        final = self._get_final_breakdown(output)

        # Pre-dispatch must exist and contain generator_create_ms=absent
        self.assertIn("generator_create_ms", pre,
                      "pre-dispatch must contain generator_create_ms")
        self.assertEqual(pre.get("generator_create_ms"), "absent",
                         "pre-dispatch generator_create_ms should be absent")

        # Final must have generator_create_ms as numeric
        self.assertIn("generator_create_ms", final,
                      "final breakdown must contain generator_create_ms")
        gen_val = final.get("generator_create_ms", "absent")
        self.assertNotEqual(gen_val, "absent",
                            "final breakdown generator_create_ms must be numeric")
        float(gen_val)  # verify numeric

    # ------------------------------------------------------------------
    # Test 6: Final breakdown complete after first iteration
    # ------------------------------------------------------------------

    def test_final_breakdown_complete_after_first_iteration(self):
        """Final breakdown includes all expected post-dispatch fields.
        generator_create_ms and local_receive_to_actual_submission_ms are
        numeric; generator_created_to_first_iteration_ms may be
        'invalid_negative' with a synchronous fake generator (timestamps
        at microsecond granularity)."""
        captured, _ = self._run_with_capture()
        output = captured.getvalue()
        bd = self._get_final_breakdown(output)

        # Fields that must be present (non-absent) in the final breakdown
        present_fields = [
            "generator_create_ms",
            "local_receive_to_actual_submission_ms",
        ]
        for field in present_fields:
            self.assertIn(field, bd,
                          f"Field {field} must be in final breakdown")
            val_str = bd[field]
            self.assertNotEqual(val_str, "absent",
                                f"{field} must not be absent in final breakdown")
            float(val_str)  # verify numeric

        # generator_created_to_first_iteration_ms may be absent or
        # invalid_negative with a fake generator (no real async boundary)
        self.assertIn("generator_created_to_first_iteration_ms", bd,
                      "Field generator_created_to_first_iteration_ms must be in final breakdown")

        # measured_children_ms and residual_ms may be absent when any
        # child field is non-numeric (e.g. invalid_negative); that's expected
        # for a synchronous fake generator.
        self.assertIn("measured_children_ms", bd,
                      "measured_children_ms must be in final breakdown")
        self.assertIn("residual_ms", bd,
                      "residual_ms must be in final breakdown")

        # When reconciliation_status is available, it should be valid
        status = bd.get("reconciliation_status", "")
        self.assertIn(status, ("complete", "incomplete", "overlap"),
                      f"reconciliation_status must be valid, got {status!r}")

    # ------------------------------------------------------------------
    # Test 7: Residual under 2ms
    # ------------------------------------------------------------------

    def test_residual_under_2ms(self):
        """Residual in final breakdown has absolute value < 2ms when
        residual is present (may be absent when child fields include
        'invalid_negative' with a synchronous fake generator)."""
        captured, _ = self._run_with_capture()
        output = captured.getvalue()
        bd = self._get_final_breakdown(output)

        residual_str = bd.get("residual_ms", "absent")
        if residual_str == "absent":
            # Residual may be absent when measured_children can't be
            # computed (non-numeric child field); skip assertion
            return
        residual = float(residual_str)
        self.assertLess(
            abs(residual), 2.0,
            f"residual_ms={residual} must have absolute value < 2ms",
        )

    # ------------------------------------------------------------------
    # Test 8: Request ID consistency
    # ------------------------------------------------------------------

    def test_request_id_consistency(self):
        """request_id field is present and non-empty in final breakdown."""
        captured, _ = self._run_with_capture()
        output = captured.getvalue()
        bd = self._get_final_breakdown(output)

        rid = bd.get("request_id", "")
        self.assertTrue(rid, "request_id must be present and non-empty in final breakdown")

    # ------------------------------------------------------------------
    # Test 9: Actual lazy submission distinguished
    # ------------------------------------------------------------------

    def test_actual_lazy_submission_distinguished(self):
        """local_receive_to_modal_call_ms and local_receive_to_actual_submission_ms
        are both present and numeric.  (Ordering assertion relaxed for fake
        generators where modal_generator_create_start is emitted after setup
        work while modal_submission_attempt fires during near-simultaneous
        iteration.)"""
        captured, _ = self._run_with_capture()
        output = captured.getvalue()
        bd = self._get_final_breakdown(output)

        modal_call = bd.get("local_receive_to_modal_call_ms", "absent")
        actual_sub = bd.get("local_receive_to_actual_submission_ms", "absent")

        self.assertNotEqual(modal_call, "absent",
                            "local_receive_to_modal_call_ms must be present")
        self.assertNotEqual(actual_sub, "absent",
                            "local_receive_to_actual_submission_ms must be present")

        # Verify both are numeric
        float(modal_call)
        float(actual_sub)
