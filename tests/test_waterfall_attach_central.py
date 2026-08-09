"""Focused tests for the central default waterfall behavior.

Covers the shared idempotent finalizer (``attach_waterfall``), the
async-generator / plain-method wrapper defaults in ``_build_decorated_v2_class``
(source contract), and the local ``canonical_execution`` execute-boundary
fallbacks (source contract + functional).
"""

import unittest
from pathlib import Path
from unittest import mock

import asyncio

from comfymodal_runtime.v2_waterfall import (
    NON_APPLICABLE,
    attach_waterfall,
    build_waterfall,
    graph_result_from_event,
    is_graph_result,
    mark_waterfall_non_applicable,
)
from modal_client import _attach_waterfall_for_graph

REPO_ROOT = Path(__file__).resolve().parents[1]
MODAL_APP = (REPO_ROOT / "comfymodal_runtime" / "modal_app.py").read_text(encoding="utf-8")
CANONICAL = (REPO_ROOT / "canonical_execution.py").read_text(encoding="utf-8")
MODAL_CLIENT = (REPO_ROOT / "modal_client.py").read_text(encoding="utf-8")
MODAL_TRANSPORT = (REPO_ROOT / "comfymodal_runtime" / "modal_transport.py").read_text(encoding="utf-8")


async def _collect_stream(agen):
    return [item async for item in agen]


class AttachWaterfallIdempotenceTests(unittest.TestCase):
    def test_attach_preserves_existing_valid_waterfall(self):
        result = {"trace": {"events": []}}
        attach_waterfall(result, wall_ms=100.0, run_label="first")
        first = result["waterfall"]
        self.assertIn("stages", first)
        with mock.patch(
            "comfymodal_runtime.v2_waterfall.render_waterfall",
            side_effect=AssertionError("must not re-render"),
        ) as _rf:
            attach_waterfall(result, wall_ms=200.0, run_label="second")
        _rf.assert_not_called()
        self.assertIs(result["waterfall"], first)

    def test_attach_builds_when_remote_omitted(self):
        result = {"request_id": "req-1", "trace": {"events": []}}
        attach_waterfall(result, wall_ms=50.0, run_label="fallback")
        self.assertIn("waterfall", result)
        self.assertEqual(result["waterfall"]["request_id"], "req-1")
        self.assertIn("stages", result["waterfall"])

    def test_attach_serializes_prebuilt_report(self):
        result = {}
        report = build_waterfall(
            result={"trace": {"events": []}}, timing={}, wall_ms=10.0,
            run_label="prebuilt",
        )
        attach_waterfall(result, report=report)
        self.assertEqual(result["waterfall"]["run_label"], "prebuilt")
        self.assertIn("stages", result["waterfall"])

    def test_attach_error_attaches_marker_never_raises(self):
        result = {}
        with mock.patch(
            "comfymodal_runtime.v2_waterfall.build_waterfall",
            side_effect=ValueError("boom"),
        ):
            attach_waterfall(result, wall_ms=10.0)
        self.assertEqual(result["waterfall"]["status"], "error")
        self.assertEqual(result["waterfall"]["error_type"], "ValueError")

    def test_attach_non_dict_returns_none(self):
        self.assertIsNone(attach_waterfall(None))
        self.assertIsNone(attach_waterfall("not-a-dict"))

    def test_non_applicable_marker_is_not_preserved(self):
        # A lifecycle/probe marker must not be mistaken for a real report;
        # an idempotent finalizer replaces it with a real report when asked.
        result = {"waterfall": {"status": NON_APPLICABLE, "method": "startup"}}
        with mock.patch(
            "comfymodal_runtime.v2_waterfall.render_waterfall", return_value="",
        ):
            attach_waterfall(result, wall_ms=5.0)
        self.assertIn("stages", result["waterfall"])

    def test_round_trip_shape(self):
        result = {"trace": {"events": []}}
        attach_waterfall(result, wall_ms=25.0, run_label="r")
        data = result["waterfall"]
        self.assertEqual(data["total_ms"], 25.0)
        self.assertEqual(data["run_label"], "r")
        self.assertIsInstance(data["stages"], list)


class ModalWrapperSourceContractTests(unittest.TestCase):
    def test_asyncgen_wrapper_finalizes_graph_result_events_only(self):
        self.assertIn("graph_result_from_event(item)", MODAL_APP)
        self.assertIn("attach_waterfall(", MODAL_APP)
        self.assertIn("is_graph_result(_gres)", MODAL_APP)
        self.assertIn('run_label=f"modal {orig_method.__name__} stream"', MODAL_APP)

    def test_plain_wrapper_default_finalizes_graph_like(self):
        self.assertIn("orig_method.__name__ in _NON_WORKFLOW_METHODS", MODAL_APP)
        self.assertIn('run_label=f"modal {orig_method.__name__}"', MODAL_APP)

    def test_plain_wrapper_marks_exempted_methods_non_applicable(self):
        self.assertIn("mark_waterfall_non_applicable(", MODAL_APP)

    def test_non_workflow_methods_exempted(self):
        self.assertIn('"startup", "restore", "exit"', MODAL_APP)
        self.assertIn('"read_output_asset"', MODAL_APP)
        self.assertIn('"publish_restore_plan"', MODAL_APP)

    def test_shared_helper_imported(self):
        self.assertIn("attach_waterfall", MODAL_APP)

    def test_inline_path_delegates_to_helper(self):
        self.assertIn("attach_waterfall(data, report=_waterfall, run_label=_run_label)", MODAL_APP)


class AsyncgenTerminalEventFunctionalTests(unittest.TestCase):
    async def _drain(self, events):
        collected = []
        for item in events:
            if isinstance(item, dict) and item.get("type") == "result":
                data = item.get("data")
                if isinstance(data, dict):
                    attach_waterfall(data, run_label="stream-test")
            collected.append(item)
        return collected

    def test_terminal_result_event_gets_waterfall(self):
        import asyncio
        events = [{"type": "progress", "data": {}},
                  {"type": "result", "data": {"request_id": "r", "trace": {"events": []}}}]
        out = asyncio.run(self._drain(events))
        self.assertIn("waterfall", out[1]["data"])
        self.assertIn("stages", out[1]["data"]["waterfall"])

    def test_terminal_result_idempotent_with_existing(self):
        import asyncio
        data = {"request_id": "r", "trace": {"events": []}}
        attach_waterfall(data, wall_ms=10.0, run_label="first")
        first = data["waterfall"]
        out = asyncio.run(self._drain([{"type": "result", "data": data}]))
        self.assertIs(out[0]["data"]["waterfall"], first)


class NonApplicableMarkerTests(unittest.TestCase):
    def test_marks_non_applicable_with_method(self):
        result = {}
        marker = mark_waterfall_non_applicable(result, method="run_env_probe")
        self.assertEqual(marker["status"], NON_APPLICABLE)
        self.assertEqual(marker["method"], "run_env_probe")
        self.assertEqual(result["waterfall"], marker)

    def test_preserves_existing_valid_waterfall(self):
        result = {"trace": {"events": []}}
        attach_waterfall(result, wall_ms=10.0, run_label="real")
        first = result["waterfall"]
        mark_waterfall_non_applicable(result, method="startup")
        self.assertIs(result["waterfall"], first)
        self.assertIn("stages", first)

    def test_non_dict_returns_none(self):
        self.assertIsNone(mark_waterfall_non_applicable(None))
        self.assertIsNone(mark_waterfall_non_applicable("x"))


class IsGraphResultTests(unittest.TestCase):
    def test_graph_result_true(self):
        self.assertTrue(is_graph_result({"trace": {"events": []}}))
        self.assertTrue(is_graph_result({"timing": {"wall_ms": 1.0}}))
        self.assertTrue(is_graph_result({"images": []}))
        self.assertTrue(is_graph_result({"outputs": {}}))
        self.assertTrue(is_graph_result({"generation_wall_ms": 12.0}))

    def test_non_graph_false(self):
        self.assertFalse(is_graph_result({"status": "ok"}))
        self.assertFalse(is_graph_result({"checkpoint": "summary"}))
        self.assertFalse(is_graph_result(None))
        self.assertFalse(is_graph_result("x"))
        self.assertFalse(is_graph_result({}))


class ModalClientFallbackTests(unittest.TestCase):
    def test_attach_for_graph_result(self):
        result = {"request_id": "r", "images": [{"data": "x"}]}
        _attach_waterfall_for_graph(result, run_label="modal_client run_prompt")
        self.assertIn("waterfall", result)

    def test_skip_non_graph_result(self):
        result = {"status": "ok", "health": True}
        with mock.patch(
            "comfymodal_runtime.v2_waterfall.attach_waterfall",
            side_effect=AssertionError("must not attach"),
        ):
            _attach_waterfall_for_graph(result, run_label="x")
        self.assertNotIn("waterfall", result)

    def test_run_prompt_direct_fallback_present(self):
        self.assertIn(
            '_attach_waterfall_for_graph(_result, run_label="modal_client run_prompt")',
            MODAL_CLIENT,
        )

    def test_run_prompt_stream_terminal_fallback_present(self):
        self.assertIn('msg.get("type") == "result"', MODAL_CLIENT)
        self.assertIn(
            'run_label="modal_client run_prompt_stream"',
            MODAL_CLIENT,
        )

    def test_run_checkpoint_stream_graph_only(self):
        self.assertIn(
            'run_label="modal_client run_checkpoint_stream"',
            MODAL_CLIENT,
        )
        # Non-graph payloads must not receive fabricated stages: the helper
        # guard is applied (is_graph_result inside _attach_waterfall_for_graph).
        self.assertIn("is_graph_result(result)", MODAL_CLIENT)


class CanonicalExecuteFallbackTests(unittest.TestCase):
    def test_execute_plan_local_fallback_present(self):
        self.assertIn('attach_waterfall(result, run_label="canonical execute_plan")', CANONICAL)
        self.assertIn("result[\"trace\"] = remote_trace", CANONICAL)

    def test_execute_modal_prompt_local_fallback_present(self):
        self.assertIn(
            'attach_waterfall(result, run_label="canonical execute_modal_prompt")',
            CANONICAL,
        )

    def test_local_fallback_is_idempotent(self):
        # Simulate exactly what execute_plan does: the remote already attached a
        # valid waterfall, so the local fallback must leave it unchanged.
        result = {"trace": {"events": []}}
        attach_waterfall(result, wall_ms=40.0, run_label="remote")
        original = dict(result["waterfall"])
        # Re-apply the same finalization the boundary performs.
        attach_waterfall(result, run_label="canonical execute_plan")
        self.assertEqual(result["waterfall"], original)


class ModalTransportFallbackTests(unittest.TestCase):
    def _transport(self, fn):
        from comfymodal_runtime.modal_transport import ModalTransport
        return ModalTransport(prompt_stream_fn=fn)

    def _run(self, transport):
        from comfymodal_runtime.contracts import ExecutionPlan
        return asyncio.run(_collect_stream(transport.run_plan_stream(ExecutionPlan())))

    def _result_data(self, events):
        result = next(e for e in events if isinstance(e, dict) and e.get("type") == "result")
        return result.get("data") or {}

    def test_non_stream_dict_graph_result_gets_waterfall(self):
        events = self._run(self._transport(lambda **kw: {"request_id": "r", "images": [{"data": "x"}]}))
        data = self._result_data(events)
        self.assertIn("waterfall", data)
        self.assertIn("stages", data["waterfall"])

    def test_non_stream_dict_non_graph_skipped(self):
        events = self._run(self._transport(lambda **kw: {"status": "ok"}))
        data = self._result_data(events)
        self.assertNotIn("waterfall", data)

    def test_stream_graph_result_event_gets_waterfall(self):
        async def _gen(**kw):
            yield {"type": "progress", "data": {"p": 0.5}}
            yield {"type": "result", "data": {"request_id": "r", "outputs": {}}}
        events = self._run(self._transport(_gen))
        data = self._result_data(events)
        self.assertIn("waterfall", data)

    def test_stream_first_event_graph_result_gets_waterfall(self):
        # The transport's first yield may itself be the terminal result;
        # graph-like first-event data must be finalized before yielding.
        async def _gen(**kw):
            yield {"type": "result", "data": {"request_id": "r", "images": [{"data": "x"}]}}
        events = self._run(self._transport(_gen))
        data = self._result_data(events)
        self.assertIn("waterfall", data)
        self.assertIn("stages", data["waterfall"])

    def test_stream_non_graph_result_skipped(self):
        async def _gen(**kw):
            yield {"type": "status", "message": "start"}
            yield {"type": "result", "data": {"status": "ok"}}
        events = self._run(self._transport(_gen))
        data = self._result_data(events)
        self.assertNotIn("waterfall", data)

    def test_transport_source_contract_uses_shared_helper(self):
        self.assertIn("is_graph_result", MODAL_TRANSPORT)
        self.assertIn("attach_waterfall", MODAL_TRANSPORT)
        self.assertIn('run_label="modal_transport run_prompt_stream"', MODAL_TRANSPORT)

    def test_asyncgen_wrapper_handles_nested_cell_results(self):
        self.assertIn("graph_result_from_event(item)", MODAL_APP)


class GraphResultFromEventTests(unittest.TestCase):
    def test_terminal_result_data(self):
        self.assertEqual(
            graph_result_from_event({"type": "result", "data": {"images": []}}),
            {"images": []},
        )

    def test_nested_cell_completed_data(self):
        self.assertEqual(
            graph_result_from_event({
                "type": "cell.completed", "data": {"result": {"outputs": {}}},
            }),
            {"outputs": {}},
        )

    def test_nested_cell_failed_payload_schema(self):
        self.assertEqual(
            graph_result_from_event({
                "type": "cell.failed",
                "payload": {"result": {"trace": {"events": []}}},
            }),
            {"trace": {"events": []}},
        )

    def test_summary_or_metadata_returns_none(self):
        self.assertIsNone(
            graph_result_from_event({"type": "checkpoint.completed", "data": {"summary": True}})
        )
        self.assertIsNone(
            graph_result_from_event({"type": "cell.completed", "data": {"cell_key": "c1"}})
        )
        self.assertIsNone(graph_result_from_event({"type": "progress", "data": {}}))

    def test_non_dict_returns_none(self):
        self.assertIsNone(graph_result_from_event(None))
        self.assertIsNone(graph_result_from_event("x"))


class ModalTransportCheckpointFallbackTests(unittest.TestCase):
    def _transport(self, fn):
        from comfymodal_runtime.modal_transport import ModalTransport
        return ModalTransport(checkpoint_stream_fn=fn)

    async def _run(self, transport):
        return [e async for e in transport.run_checkpoint_stream()]

    def test_stream_nested_cell_completed_graph_result(self):
        async def _gen(**kw):
            yield {"type": "cell.completed", "data": {
                "cell_key": "c1", "result": {"request_id": "r", "images": [{"data": "x"}]},
            }}
        events = asyncio.run(self._run(self._transport(_gen)))
        nested = events[0]["data"]["result"]
        self.assertIn("waterfall", nested)
        self.assertIn("stages", nested["waterfall"])

    def test_stream_nested_cell_failed_partial_graph(self):
        async def _gen(**kw):
            yield {"type": "cell.failed", "data": {
                "cell_key": "c1", "result": {"request_id": "r", "outputs": {}},
            }}
        events = asyncio.run(self._run(self._transport(_gen)))
        self.assertIn("waterfall", events[0]["data"]["result"])

    def test_stream_summary_and_metadata_skipped(self):
        async def _gen(**kw):
            yield {"type": "cell.completed", "data": {"cell_key": "c1", "status": "ok"}}
            yield {"type": "checkpoint.completed", "data": {"summary": True}}
        events = asyncio.run(self._run(self._transport(_gen)))
        for e in events:
            inner = e.get("data", {})
            self.assertNotIn("waterfall", inner)
            if isinstance(inner.get("result"), dict):
                self.assertNotIn("waterfall", inner["result"])

    def test_non_stream_dict_graph_fallback(self):
        transport = self._transport(lambda **kw: {"request_id": "r", "images": [{"data": "x"}]})
        events = asyncio.run(self._run(transport))
        self.assertEqual(events[0]["type"], "result")
        self.assertIn("waterfall", events[0]["data"])


if __name__ == "__main__":
    unittest.main()
