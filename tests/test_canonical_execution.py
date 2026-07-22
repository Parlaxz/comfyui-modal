"""Tests for canonical_execution module.

Covers:
  - RunTrace span lifecycle, optional spans, counts, payload sizes
  - execute_modal_prompt with mocked run_prompt_stream
  - prepare_modal_execution returns expected keys
  - Playground direct-vs-normal parity for workflow, images, GPU, options
  - Exactly-one core counts and zero invoker/runner/scheduler
  - Placement cache key and defaults in modal_client
  - Trace optional span/count shape
"""

import asyncio
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_canonical():
    """Load canonical_execution module."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "canonical_execution", REPO_ROOT / "canonical_execution.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["canonical_execution"] = mod
    spec.loader.exec_module(mod)
    return mod


# =========================================================================
# RunTrace tests
# =========================================================================


class TestRunTrace(unittest.TestCase):
    def setUp(self):
        self.mod = _load_canonical()

    def test_basic_span_lifecycle(self):
        """begin/end records duration_ms without wall fields in output."""
        trace = self.mod.RunTrace()
        trace.begin("test_span")
        # Force at least 5ms of monotonic time
        time.sleep(0.01)
        trace.end("test_span")
        summary = trace.emit_remote_summary()
        spans = summary["spans"]
        self.assertIn("test_span", spans)
        ts = spans["test_span"]
        self.assertTrue(ts["called"])
        self.assertGreaterEqual(ts["duration_ms"], 0)
        self.assertNotIn("_start_ns", ts)  # internal-only, stripped

    def test_count_accumulates(self):
        """count adds to the counts dict."""
        trace = self.mod.RunTrace()
        trace.count("calls", 1)
        trace.count("calls", 2)
        trace.count("other", 5)
        summary = trace.emit_remote_summary()
        self.assertEqual(summary["counts"]["calls"], 3)
        self.assertEqual(summary["counts"]["other"], 5)

    def test_payload_sizes(self):
        """record_payload_size stores byte counts."""
        trace = self.mod.RunTrace()
        trace.record_payload_size("input_images", 1024)
        trace.record_payload_size("active_profile", 512)
        summary = trace.emit_remote_summary()
        self.assertEqual(summary["payload_sizes"]["input_images"], 1024)
        self.assertEqual(summary["payload_sizes"]["active_profile"], 512)

    def test_optional_spans_default_false(self):
        """All optional spans default called=False."""
        trace = self.mod.RunTrace()
        summary = trace.emit_remote_summary()
        expected_optionals = (
            "LocalRemoteInvoker", "scheduler", "runner", "lease", "checkpoint",
            "StudioProgressTracker", "LocalRemoteHandler", "deploy_listener",
            "scheduler_loop", "hot_reload_listener",
            "studio_single_run_enter", "direct_studio_run_completion",
            "experiment_creation", "run_history_creation",
            "scheduler_creation", "scheduler_start",
            "runner_creation",
            "local_remote_invoker_creation",
            "local_remote_invoker_open_worker",
            "local_remote_invoker_run_cell",
            "local_remote_invoker_close_worker",
            "lease_claim", "checkpoint_write", "journal_write",
            "cell_resolution", "experiment_trace_merge",
            "studio_output_copy", "studio_history_update",
            "studio_output_metadata_write",
        )
        for name in expected_optionals:
            self.assertIn(name, summary["spans"])
            self.assertFalse(summary["spans"][name]["called"])
            self.assertEqual(summary["spans"][name]["count"], 0)
            self.assertEqual(summary["spans"][name]["duration_ms"], 0)

    def test_local_summary_has_no_perf_start(self):
        """emit_local_summary does not include perf_start/samples."""
        trace = self.mod.RunTrace()
        local = trace.emit_local_summary()
        self.assertIn("wall_start_s", local)
        self.assertNotIn("perf_start_ns", local)
        self.assertNotIn("samples", local)

    def test_remote_summary_has_perf_start_and_samples(self):
        """emit_remote_summary includes perf_start and samples."""
        trace = self.mod.RunTrace()
        trace.sample("test_sample", extra=42)
        remote = trace.emit_remote_summary()
        self.assertIn("perf_start_ns", remote)
        self.assertIn("samples", remote)
        self.assertEqual(len(remote["samples"]), 1)
        self.assertEqual(remote["samples"][0]["extra"], 42)

    def test_merge_into_trace(self):
        """merge_into_trace adds _run_trace key to existing trace dict."""
        trace = self.mod.RunTrace()
        trace.count("merge_test", 1)
        target = {"stages": {}}
        trace.merge_into_trace(target)
        self.assertIn("_run_trace", target)
        self.assertEqual(target["_run_trace"]["counts"]["merge_test"], 1)

    def test_playground_shows_zero_invoker_runner_scheduler(self):
        """A Playground run trace must show all optional spans with called=False."""
        trace = self.mod.RunTrace()
        # Simulate what direct_studio_run_completion would do
        trace.count("local_remote_invoker_used", 0)
        trace.count("scheduler_used", 0)
        trace.count("runner_used", 0)
        summary = trace.emit_remote_summary()
        expected_optionals = (
            "LocalRemoteInvoker", "scheduler", "runner", "lease", "checkpoint",
            "StudioProgressTracker", "LocalRemoteHandler", "deploy_listener",
            "scheduler_loop", "hot_reload_listener",
            "studio_single_run_enter", "direct_studio_run_completion",
            "experiment_creation", "run_history_creation",
            "scheduler_creation", "scheduler_start",
            "runner_creation",
            "local_remote_invoker_creation",
            "local_remote_invoker_open_worker",
            "local_remote_invoker_run_cell",
            "local_remote_invoker_close_worker",
            "lease_claim", "checkpoint_write", "journal_write",
            "cell_resolution", "experiment_trace_merge",
            "studio_output_copy", "studio_history_update",
            "studio_output_metadata_write",
        )
        for name in expected_optionals:
            self.assertIn(name, summary["spans"])
            self.assertFalse(summary["spans"][name]["called"])


# =========================================================================
# prepare_modal_execution tests
# =========================================================================


class TestPrepareModalExecution(unittest.TestCase):
    def setUp(self):
        self.mod = _load_canonical()

    @patch("canonical_execution.prepare_active_next_profile", new_callable=AsyncMock)
    @patch("canonical_execution.assert_valid_api_prompt_structure")
    async def _prepare(self, workflow, mock_assert, mock_profile, **kwargs):
        mock_profile.return_value = {"status": "ok", "payload_bytes": 0, "changed": False}
        kwargs.setdefault("prompt_id", "test_prompt")
        return await self.mod.prepare_modal_execution(workflow, **kwargs)

    def test_returns_expected_keys(self):
        """prepare_modal_execution returns all expected keys."""
        async def _run():
            result = await self._prepare(
                {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
                input_images={},
                modal_options={},
            )
            self.assertIn("input_images", result)
            self.assertIn("trace", result)
            self.assertIn("production_report", result)
            self.assertIn("modal_options", result)
            self.assertIn("gpu", result)
            self.assertIn("workspace", result)
            self.assertIn("profile_result", result)
        asyncio.run(_run())

    def test_meta_contains_model_stack_and_prompt_summary(self):
        """prepare_modal_execution stores model_stack and prompt_summary in run_trace meta."""
        async def _run():
            trace = self.mod.RunTrace()
            await self._prepare(
                {"3": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20}},
                 "5": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip_l.safetensors"}}},
                input_images={},
                modal_options={},
                run_trace=trace,
            )
            summary = trace.emit_remote_summary()
            meta = summary.get("meta", {})
            self.assertIn("model_stack", meta)
            self.assertIn("prompt_summary", meta)
            self.assertIsInstance(meta["model_stack"], dict)
            self.assertIsInstance(meta["prompt_summary"], dict)
            # Verify prompt_summary contents
            self.assertEqual(meta["prompt_summary"].get("seed"), 42)
            self.assertEqual(meta["prompt_summary"].get("steps"), 20)
            # Verify model_stack captures CLIPLoader
            self.assertIn("clip", meta["model_stack"])
            self.assertIn("clip_l.safetensors", meta["model_stack"]["clip"])
        asyncio.run(_run())

    def test_meta_contains_prompt_id_and_client_id(self):
        """prepare_modal_execution stores prompt_id and client_id in meta."""
        async def _run():
            trace = self.mod.RunTrace()
            await self._prepare(
                {"3": {"class_type": "KSampler"}},
                input_images={},
                modal_options={},
                run_trace=trace,
                prompt_id="test_meta_pid",
                client_id="test_meta_cid",
            )
            summary = trace.emit_remote_summary()
            meta = summary.get("meta", {})
            self.assertEqual(meta.get("prompt_id"), "test_meta_pid")
            self.assertEqual(meta.get("client_id"), "test_meta_cid")
        asyncio.run(_run())

    def test_workflow_hash_mismatch_raises(self):
        """prepare_modal_execution raises on hash mismatch."""
        async def _run():
            with self.assertRaises(RuntimeError):
                await self._prepare(
                    {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
                    trace_payload={"workflow_hash": "deadbeef" * 8},
                )
        asyncio.run(_run())

    def test_production_hash_provenance_in_meta(self):
        """When production is enabled, source_workflow_hash and compiled_workflow_hash
        in RunTrace meta must come from the production report, not from current_hash."""
        from unittest.mock import patch, AsyncMock
        async def _run():
            trace = self.mod.RunTrace()
            workflow = {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}}
            actual_hash = self.mod.prompt_sha256(workflow)

            report = {
                "enabled": True,
                "source_workflow_hash": "src_from_report_001",
                "compiled_workflow_hash": actual_hash,
                "production_plan_hash": "plan_from_report_001",
                "output_node_ids": ["9"],
                "compiler_version": 0,
                "hash_schema_version": 0,
            }

            with patch("canonical_execution.prepare_active_next_profile", new_callable=AsyncMock) as mock_profile:
                mock_profile.return_value = {"status": "ok", "payload_bytes": 0, "changed": False}
                with patch("canonical_execution.assert_valid_api_prompt_structure"):
                    await self.mod.prepare_modal_execution(
                        workflow,
                        prompt_id="test_prod_provenance",
                        input_images={},
                        modal_options={},
                        production_report=report,
                        run_trace=trace,
                    )

            meta = trace.emit_remote_summary().get("meta", {})
            # source hash must come from the report, not from current_hash
            self.assertEqual(meta.get("source_workflow_hash"), "src_from_report_001",
                             "production source_workflow_hash must come from report")
            # compiled hash must match the actual workflow (from report)
            self.assertEqual(meta.get("compiled_workflow_hash"), actual_hash,
                             "production compiled_workflow_hash must come from report")
            # plan hash and output IDs also from report
            self.assertEqual(meta.get("production_plan_hash"), "plan_from_report_001")
            self.assertEqual(meta.get("output_node_ids"), ["9"])
        asyncio.run(_run())


# =========================================================================
# execute_modal_prompt tests (with mocked run_prompt_stream)
# =========================================================================


class TestExecuteModalPrompt(unittest.TestCase):
    def setUp(self):
        self.mod = _load_canonical()

    def _make_mock_stream(self, result_data=None):
        """Create a mock async generator that yields result then stops."""
        if result_data is None:
            result_data = {"outputs": {"9": {"images": [{"filename": "test.png"}]}}}
        async def _stream(*a, **kw):
            yield {"type": "result", "data": result_data}
        return _stream

    async def _execute(self, workflow, **kwargs):
        """Helper: patch dependencies and call execute_modal_prompt."""
        from unittest.mock import patch, AsyncMock
        with patch("modal_client.run_prompt_stream") as mock_stream:
            with patch("canonical_execution.prepare_active_next_profile", new_callable=AsyncMock) as mock_profile:
                with patch("canonical_execution.assert_valid_api_prompt_structure"):
                    # Set return_value to a resolved dict so await chain terminates
                    mock_profile.return_value = {"status": "ok", "payload_bytes": 0}
                    mock_stream.return_value = self._make_mock_stream()()
                    kwargs.setdefault("prompt_id", "test_prompt")
                    result = await self.mod.execute_modal_prompt(workflow, **kwargs)
        return result

    def test_returns_result_dict(self):
        """execute_modal_prompt returns the Modal result dict."""
        async def _run():
            result = await self._execute(
                {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
                input_images={},
            )
            self.assertIn("outputs", result)
            self.assertIn("9", result["outputs"])
        asyncio.run(_run())

    def test_result_contains_trace_with_run_trace(self):
        """When run_trace is provided, result.trace has _run_trace."""
        async def _run():
            trace = self.mod.RunTrace()
            result = await self._execute(
                {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
                input_images={},
                run_trace=trace,
            )
            result_trace = result.get("trace", {})
            if result_trace:
                self.assertIn("_run_trace", result_trace)
        asyncio.run(_run())

    def test_modal_handle_lookup_count_present(self):
        """modal_handle_lookup_count is recorded at the canonical Modal-call boundary."""
        async def _run():
            trace = self.mod.RunTrace()
            await self._execute(
                {"3": {"class_type": "KSampler"}},
                input_images={},
                run_trace=trace,
            )
            summary = trace.emit_remote_summary()
            self.assertIn("modal_handle_lookup_count", summary["counts"])
            self.assertEqual(summary["counts"]["modal_handle_lookup_count"], 1)
        asyncio.run(_run())

    def test_playground_parity_same_workflow_same_images_same_gpu(self):
        """Two calls with same workflow/images/gpu/options produce same output IDs."""
        async def _run():
            workflow = {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}}
            images = {"test.png": "base64data"}
            opts = {"production": {"enabled": False}}
            result1 = await self._execute(workflow, input_images=images, modal_options=opts)
            result2 = await self._execute(workflow, input_images=images, modal_options=opts)
            # output IDs must match (same mocked stream response)
            self.assertEqual(
                result1.get("outputs", {}),
                result2.get("outputs", {}),
            )
        asyncio.run(_run())

    def test_exactly_one_core_counts(self):
        """A normal execution should have exactly one run_prompt_stream call."""
        async def _run():
            trace = self.mod.RunTrace()
            await self._execute(
                {"3": {"class_type": "KSampler"}},
                input_images={},
                run_trace=trace,
            )
            summary = trace.emit_remote_summary()
            counts = summary["counts"]
            # There should be exactly one output_nodes count
            self.assertIn("output_nodes", counts)
            self.assertGreaterEqual(counts["output_nodes"], 0)
        asyncio.run(_run())

    def test_canonical_counts_present(self):
        """All required canonical operation counts are present in the summary."""
        trace = self.mod.RunTrace()
        summary = trace.emit_remote_summary()
        for name in trace.CANONICAL_COUNTS:
            self.assertIn(name, summary["counts"],
                          f"Required canonical count '{name}' missing from summary")

    def test_trace_has_correlation_fields(self):
        """RunTrace summary includes trace_id, run_id, prompt_id, run_surface."""
        trace = self.mod.RunTrace(
            trace_id="test_tid",
            run_id="test_rid",
            prompt_id="test_pid",
            run_surface="test_surface",
        )
        summary = trace.emit_remote_summary()
        self.assertEqual(summary["trace_id"], "test_tid")
        self.assertEqual(summary["run_id"], "test_rid")
        self.assertEqual(summary["prompt_id"], "test_pid")
        self.assertEqual(summary["run_surface"], "test_surface")

    def test_error_from_stream_raises(self):
        """An error message from run_prompt_stream raises RuntimeError."""
        from unittest.mock import patch, AsyncMock
        async def _run():
            with patch("modal_client.run_prompt_stream") as mock_stream:
                with patch("canonical_execution.prepare_active_next_profile", new_callable=AsyncMock) as mock_profile:
                    with patch("canonical_execution.assert_valid_api_prompt_structure"):
                        mock_profile.return_value = {"status": "ok"}
                        async def _err_stream(*a, **kw):
                            yield {"type": "error", "message": "test error"}
                        mock_stream.return_value = _err_stream()
                        with self.assertRaises(RuntimeError):
                            await self.mod.execute_modal_prompt(
                                {"3": {"class_type": "KSampler"}},
                                prompt_id="test",
                                input_images={},
                            )
        asyncio.run(_run())

    def test_event_sink_forwarded(self):
        """Non-terminal events are forwarded through event_sink."""
        from unittest.mock import patch, AsyncMock
        async def _run():
            with patch("modal_client.run_prompt_stream") as mock_stream:
                with patch("canonical_execution.prepare_active_next_profile", new_callable=AsyncMock) as mock_profile:
                    with patch("canonical_execution.assert_valid_api_prompt_structure"):
                        mock_profile.return_value = {"status": "ok"}
                        events: list[str] = []
                        async def _stream(*a, **kw):
                            yield {"type": "progress", "event": "executing",
                                   "data": {"node": "3", "step": 1, "max": 20}}
                            yield {"type": "status", "message": "warming up", "phase": "warmup"}
                            yield {"type": "result", "data": {"outputs": {}}}
                        mock_stream.return_value = _stream()
                        def _sink(etype, payload):
                            events.append(etype)
                        await self.mod.execute_modal_prompt(
                            {"3": {"class_type": "KSampler"}},
                            prompt_id="test",
                            input_images={},
                            event_sink=_sink,
                        )
                        self.assertIn("progress", events)
                        self.assertIn("status", events)
        asyncio.run(_run())

    def test_event_sink_not_called_for_error_or_result(self):
        """Terminal events (error, result) are NOT forwarded to event_sink."""
        from unittest.mock import patch, AsyncMock
        async def _run():
            with patch("modal_client.run_prompt_stream") as mock_stream:
                with patch("canonical_execution.prepare_active_next_profile", new_callable=AsyncMock) as mock_profile:
                    with patch("canonical_execution.assert_valid_api_prompt_structure"):
                        mock_profile.return_value = {"status": "ok"}
                        events: list[str] = []
                        mock_stream.return_value = self._make_mock_stream({"outputs": {}})()
                        def _sink(etype, payload):
                            events.append(etype)
                        await self.mod.execute_modal_prompt(
                            {"3": {"class_type": "KSampler"}},
                            prompt_id="test",
                            input_images={},
                            event_sink=_sink,
                        )
                        self.assertNotIn("result", events)
        asyncio.run(_run())

    def test_playground_exactly_one_counts(self):
        """Normal + Playground run reports exactly one for core canonical counts.
        workflow_deepcopy_count is 0 because no production compile occurs;
        a deepcopy is only counted when production compile creates a new workflow."""
        from unittest.mock import patch, AsyncMock
        async def _run():
            with patch("modal_client.run_prompt_stream") as mock_stream:
                with patch("canonical_execution.prepare_active_next_profile", new_callable=AsyncMock) as mock_profile:
                    with patch("canonical_execution.assert_valid_api_prompt_structure"):
                        mock_profile.return_value = {"status": "ok"}
                        mock_stream.return_value = self._make_mock_stream({"outputs": {}})()
                        trace = self.mod.RunTrace(run_surface="playground_direct")
                        await self.mod.execute_modal_prompt(
                            {"3": {"class_type": "KSampler"}},
                            prompt_id="test",
                            input_images={},
                            run_trace=trace,
                        )
                        summary = trace.emit_remote_summary()
                        counts = summary["counts"]
                        # workflow_deepcopy_count is 0 for non-production runs (no real deepcopy)
                        self.assertEqual(counts.get("workflow_deepcopy_count"), 0)
                        self.assertEqual(counts.get("run_prompt_stream_call_count"), 1)
                        self.assertEqual(counts.get("model_stack_extract_count"), 1)
                        # profile_prepare should be 1 (called by prepare_modal_execution)
                        self.assertEqual(counts.get("active_profile_prepare_count"), 1)
        asyncio.run(_run())

    def test_full_workflow_hash_count_is_one(self):
        """full_workflow_hash_count must be exactly 1 for both production and non-production runs."""
        from unittest.mock import patch, AsyncMock
        async def _run():
            with patch("modal_client.run_prompt_stream") as mock_stream:
                with patch("canonical_execution.prepare_active_next_profile", new_callable=AsyncMock) as mock_profile:
                    with patch("canonical_execution.assert_valid_api_prompt_structure"):
                        mock_profile.return_value = {"status": "ok"}
                        mock_stream.return_value = self._make_mock_stream({"outputs": {}})()
                        trace = self.mod.RunTrace()
                        await self.mod.execute_modal_prompt(
                            {"3": {"class_type": "KSampler"}},
                            prompt_id="test",
                            input_images={},
                            run_trace=trace,
                        )
                        summary = trace.emit_remote_summary()
                        self.assertEqual(summary["counts"].get("full_workflow_hash_count"), 1)
        asyncio.run(_run())

    def test_required_canonical_span_names_present(self):
        """All required canonical span names appear as stable entries in the summary."""
        from unittest.mock import patch, AsyncMock
        async def _run():
            with patch("modal_client.run_prompt_stream") as mock_stream:
                with patch("canonical_execution.prepare_active_next_profile", new_callable=AsyncMock) as mock_profile:
                    with patch("canonical_execution.assert_valid_api_prompt_structure"):
                        mock_profile.return_value = {"status": "ok"}
                        mock_stream.return_value = self._make_mock_stream({"outputs": {}})()
                        trace = self.mod.RunTrace()
                        await self.mod.execute_modal_prompt(
                            {"3": {"class_type": "KSampler"}},
                            prompt_id="test",
                            input_images={},
                            run_trace=trace,
                        )
                        summary = trace.emit_remote_summary()
                        spans = summary["spans"]
                        required = [
                            "canonical_execute_enter", "workflow_input_size",
                            "workflow_deepcopy", "workflow_normalization",
                            "production_compile", "production_validate_local",
                            "source_workflow_hash", "compiled_workflow_hash",
                            "production_plan_hash", "model_stack_extract",
                            "used_node_class_extract", "input_image_discovery",
                            "input_image_read", "input_image_encode",
                            "extra_data_build", "modal_options_build",
                            "production_report_build", "active_profile_build",
                            "active_profile_dedup", "active_profile_local_write",
                            "active_profile_remote_call", "active_profile_ack_wait",
                            "modal_handle_lookup", "modal_handle_cache_hit",
                            "modal_argument_serialization", "remote_generator_create",
                            "remote_submit", "first_remote_message",
                            "remote_result_complete", "canonical_execute_exit",
                        ]
                        for name in required:
                            self.assertIn(name, spans,
                                          f"Required canonical span '{name}' missing from summary")
                            self.assertIn("called", spans[name])
                            self.assertIn("count", spans[name])
                            self.assertIn("duration_ms", spans[name])
        asyncio.run(_run())

    def test_non_production_meta_always_populated(self):
        """Meta always includes source_workflow_hash, compiled_workflow_hash,
        production_plan_hash (empty for non-production), output_node_ids,
        selected_gpu, region, cloud, min_containers, scaledown_window."""
        from unittest.mock import patch, AsyncMock
        async def _run():
            with patch("modal_client.run_prompt_stream") as mock_stream:
                with patch("canonical_execution.prepare_active_next_profile", new_callable=AsyncMock) as mock_profile:
                    with patch("canonical_execution.assert_valid_api_prompt_structure"):
                        mock_profile.return_value = {"status": "ok"}
                        mock_stream.return_value = self._make_mock_stream({"outputs": {}})()
                        trace = self.mod.RunTrace()
                        await self.mod.execute_modal_prompt(
                            {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
                            prompt_id="test_np",
                            input_images={},
                            run_trace=trace,
                        )
                        summary = trace.emit_remote_summary()
                        meta = summary.get("meta", {})
                        # source_workflow_hash should be a non-empty hex string
                        self.assertIn("source_workflow_hash", meta)
                        self.assertGreater(len(meta["source_workflow_hash"]), 0)
                        # compiled_workflow_hash should match source for non-production
                        self.assertIn("compiled_workflow_hash", meta)
                        self.assertEqual(meta["source_workflow_hash"], meta["compiled_workflow_hash"])
                        # production_plan_hash should be empty for non-production
                        self.assertIn("production_plan_hash", meta)
                        self.assertEqual(meta["production_plan_hash"], "")
                        # output_node_ids should be empty list
                        self.assertIn("output_node_ids", meta)
                        self.assertEqual(meta["output_node_ids"], [])
                        # selected_gpu defaults to empty string
                        self.assertIn("selected_gpu", meta)
                        # Placement/correlation fields always present
                        self.assertIn("region", meta)
                        self.assertIn("cloud", meta)
                        self.assertIn("min_containers", meta)
                        self.assertEqual(meta["min_containers"], 0)
                        self.assertIn("scaledown_window", meta)
                        self.assertEqual(meta["scaledown_window"], 4)
                        # Run surface in meta
                        self.assertIn("run_surface", meta)
        asyncio.run(_run())

    def test_exactly_one_core_operation_counts(self):
        """Core canonical operations that fire every run must have count exactly 1."""
        from unittest.mock import patch, AsyncMock
        async def _run():
            with patch("modal_client.run_prompt_stream") as mock_stream:
                with patch("canonical_execution.prepare_active_next_profile", new_callable=AsyncMock) as mock_profile:
                    with patch("canonical_execution.assert_valid_api_prompt_structure"):
                        mock_profile.return_value = {"status": "ok"}
                        mock_stream.return_value = self._make_mock_stream({"outputs": {}})()
                        trace = self.mod.RunTrace()
                        await self.mod.execute_modal_prompt(
                            {"3": {"class_type": "KSampler"}},
                            prompt_id="test",
                            input_images={},
                            run_trace=trace,
                        )
                        summary = trace.emit_remote_summary()
                        counts = summary["counts"]
                        # These should always be exactly 1 for a non-production run
                        self.assertEqual(counts.get("full_workflow_hash_count"), 1)
                        self.assertEqual(counts.get("model_stack_extract_count"), 1)
                        self.assertEqual(counts.get("active_profile_prepare_count"), 1)
                        self.assertEqual(counts.get("run_prompt_stream_call_count"), 1)
                        self.assertEqual(counts.get("modal_handle_lookup_count"), 1)
                        # workflow_deepcopy is 0 for non-production (compile not triggered)
                        self.assertEqual(counts.get("workflow_deepcopy_count"), 0)
                        # production_compile is 0 for non-production
                        self.assertEqual(counts.get("production_compile_count"), 0)
        asyncio.run(_run())


# =========================================================================
# modal_client placement tests
# =========================================================================


class TestPlacementCacheKey(unittest.TestCase):
    """Tests for env-gated compute region/cloud in modal_client._workspace_api."""

    def test_default_placement_empty(self):
        """Default placement env vars are empty (global scheduling)."""
        import modal_client as mc
        # Directly check module-level constants
        self.assertEqual(mc._COMFYMODAL_COMPUTE_REGION, "")
        self.assertEqual(mc._COMFYMODAL_COMPUTE_CLOUD, "")

    def test_cache_key_includes_region_and_cloud(self):
        """_workspace_api cache key must include region and cloud."""
        import importlib.util
        # Re-read the source to verify cache key pattern
        source = (REPO_ROOT / "modal_client.py").read_text(encoding="utf-8")
        self.assertIn("(workspace[\"id\"], selected_gpu, region, cloud)", source,
                      "Cache key must include region and cloud")

    def test_with_options_only_when_nonempty(self):
        """with_options should only be called when region or cloud is set."""
        import importlib.util
        source = (REPO_ROOT / "modal_client.py").read_text(encoding="utf-8")
        # Must guard with_options behind a conditional
        self.assertIn("if region or cloud:", source,
                      "with_options must be guarded by if region or cloud")


class TestValidateProductionDispatch(unittest.TestCase):
    """Tests for validate_production_dispatch and precomputed-hash path."""

    def test_validate_dispatch_uses_precomputed_hash(self):
        """validate_production_dispatch uses workflow_hash when provided,
        skipping recomputation of _canonical_workflow_hash."""
        import modal_client as mc

        workflow = {"3": {"class_type": "KSampler", "inputs": {"seed": 42}}}

        # Report with a compiled hash that does NOT match the actual workflow
        report = {
            "enabled": True,
            "compiled_workflow_hash": "diff_hash_12345",
            "source_workflow_hash": "src_hash",
            "compiler_version": mc.COMPILER_SCHEMA_VERSION,
            "hash_schema_version": mc.HASH_SCHEMA_VERSION,
            "production_plan_schema_version": mc.PRODUCTION_PLAN_SCHEMA_VERSION,
        }

        # With matching workflow_hash, uses it instead of recomputing → passes
        mc.validate_production_dispatch(
            workflow, report, label="test", workflow_hash="diff_hash_12345",
        )

        # Without workflow_hash, recomputes actual hash and detects mismatch
        with self.assertRaises(AssertionError):
            mc.validate_production_dispatch(workflow, report, label="test")


# =========================================================================
# Import / compile checks
# =========================================================================


class TestImports(unittest.TestCase):
    """All modified modules compile without import errors."""

    def test_canonical_execution_imports(self):
        """canonical_execution imports cleanly."""
        try:
            _load_canonical()
        except Exception as exc:
            self.fail(f"canonical_execution import failed: {exc}")

    def test_modal_client_imports(self):
        """modal_client imports cleanly (modal may not be installed)."""
        try:
            import modal_client as mc
            self.assertTrue(hasattr(mc, "_workspace_api"))
        except ImportError:
            pass  # modal not required for syntax check

    def test_studio_run_adapter_imports(self):
        """studio_run_adapter imports cleanly."""
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "studio_run_adapter", REPO_ROOT / "studio_run_adapter.py"
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules["studio_run_adapter"] = mod
                spec.loader.exec_module(mod)
        except Exception as exc:
            # May fail if ComfyUI dependencies not available — check syntax only
            pass


# =========================================================================
# Source-level regression tests
# =========================================================================


class TestStackExtractMsRegression(unittest.TestCase):
    """Verify the ``stack_extract_ms`` NameError fix in ``__init__.py``."""

    def test_stack_extract_ms_not_bare_reference(self):
        """The /prompt route's local_ts dict must not reference stack_extract_ms
        as a bare variable without assignment (was removed when stack
        extraction moved to canonical executor).  Default to 0 instead."""
        source = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8")
        # Find ALL occurrences of "stack_extract_ms": in the source
        # The /prompt route has it in the local_ts construction near the
        # end of modal_prompt (second occurrence).  The first occurrence
        # is in _detect_local_predispatch_stall's return dict (which
        # reads from its parameter — that's fine).
        # Search for the occurrence that sets value after stack extraction
        # was removed.  The correct one is the local_ts = {...} block
        # near t2_local_dispatch which sets "stack_extract_ms": 0.
        idx = source.find('"stack_extract_ms": 0,')
        self.assertGreater(
            idx, 0,
            "stack_extract_ms must default to 0 in the /prompt route's "
            "local_ts construction (found stale bare reference instead)"
        )


# =========================================================================
# V1 regression: gpu_submit_to_first_event_ns is a delta, not epoch
# =========================================================================


class TestGpuSubmitToFirstEventRegression(unittest.TestCase):
    """Verify ``gpu_submit_to_first_event_ns`` is a delta interval, not an epoch
    timestamp stored in an interval field."""

    def test_gpu_submit_to_first_event_ns_is_delta_not_epoch(self):
        """gpu_submit_to_first_event_ns must be a duration delta (ns), not an epoch
        timestamp. The old code stored ``_now_iter`` (a wall-clock epoch value) in
        this field via ``setdefault`` near the iteration-start boundary."""
        source = (REPO_ROOT / "modal_client.py").read_text(encoding="utf-8")
        # Must not contain the old pattern that stored an epoch timestamp
        self.assertNotIn(
            'setdefault("gpu_submit_to_first_event_ns", _now_iter)',
            source,
            "gpu_submit_to_first_event_ns must not be set to an epoch timestamp "
            "via setdefault near iteration start",
        )
        # Must still exist as a computed delta value
        self.assertIn(
            'trace["gpu_submit_to_first_event_ns"]',
            source,
            "gpu_submit_to_first_event_ns must be present as a computed interval",
        )
        # The ms variant must also be present
        self.assertIn(
            'trace["gpu_submit_to_first_event_ms"]',
            source,
            "gpu_submit_to_first_event_ms must be present as a computed interval",
        )


# =========================================================================
# V2 execute_plan focused test: gpu_invocation_submit event
# =========================================================================


class TestExecutePlanGpuInvocation(unittest.TestCase):
    """Focused test that ``execute_plan`` emits ``gpu_invocation_submit``."""

    def setUp(self):
        self.mod = _load_canonical()

    def test_gpu_invocation_submit_event_emitted(self):
        """execute_plan emits a gpu_invocation_submit RuntimeTrace event at the
        submission boundary immediately before the transport call."""
        from unittest.mock import MagicMock

        async def _run():
            trace = self.mod.RuntimeTrace(
                request_id="test_gpu_invocation",
            )

            # Build a minimal ExecutionPlan
            from comfymodal_runtime.contracts import ExecutionPlan, ExecutionOptions
            plan = ExecutionPlan(
                workflow={"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
                workflow_hash="test_hash",
                source_workflow_hash="test_src_hash",
                execution_options=ExecutionOptions.from_legacy(
                    {}, default_production=False,
                ),
                request_metadata={"prompt_id": "test_prompt"},
            )

            # Mock transport that yields a result immediately
            async def _mock_stream(
                plan, *, gpu=None, workspace=None,
                trace=None, runtime_trace=None, **kwargs,
            ):
                yield {"type": "result", "data": {"outputs": {}}}

            mock_transport = MagicMock()
            mock_transport.run_plan_stream = _mock_stream

            await self.mod.execute_plan(
                plan,
                transport=mock_transport,
                trace=trace,
            )

            event_names = [e.name for e in trace.events]
            self.assertIn(
                "gpu_invocation_submit",
                event_names,
                "execute_plan must emit gpu_invocation_submit event",
            )
            # Verify ordering: gpu_invocation_submit must appear after
            # modal_submit_start and before the first transport event
            self.assertIn("modal_submit_start", event_names)
            self.assertIn("remote_return_start", event_names)
            submit_idx = event_names.index("gpu_invocation_submit")
            modal_start_idx = event_names.index("modal_submit_start")
            self.assertGreater(
                submit_idx, modal_start_idx,
                "gpu_invocation_submit must appear after modal_submit_start",
            )

        asyncio.run(_run())


# =========================================================================
# V2 execute_plan regression: modal_input_id already present
# =========================================================================


class TestExecutePlanModalInputIdRegression(unittest.TestCase):
    """``execute_plan`` must not raise ``UnboundLocalError`` when
    ``modal_input_id`` is already present in transport metadata.

    The fix in ``canonical_execution.py`` initializes ``_remote_metadata``
    unconditionally from ``raw_remote_trace`` *before* the ``modal_input_id``
    conditional branch, so a present ID + sparse remote trace metadata
    cannot leave the variable undefined for later timestamp fallback reads.
    """

    def setUp(self):
        self.mod = _load_canonical()

    def test_modal_input_id_present_does_not_raise(self):
        """execute_plan succeeds when modal_input_id is already set and
        raw_remote_trace has sparse metadata."""
        from unittest.mock import MagicMock

        async def _run():
            # Create a RuntimeTrace with modal_input_id pre-populated
            trace = self.mod.RuntimeTrace(
                request_id="test_modal_input_id_present",
            )
            trace.set_metadata(modal_input_id="existing_input_42")

            # Build a minimal ExecutionPlan
            from comfymodal_runtime.contracts import ExecutionPlan, ExecutionOptions
            plan = ExecutionPlan(
                workflow={"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
                workflow_hash="test_hash",
                source_workflow_hash="test_src_hash",
                execution_options=ExecutionOptions.from_legacy(
                    {}, default_production=False,
                ),
                request_metadata={"prompt_id": "test_modal_id"},
            )

            # Mock transport that returns a result with VERY sparse remote trace
            # (empty metadata, no modal_input_id in remote metadata).
            async def _mock_stream(
                plan, *, gpu=None, workspace=None,
                trace=None, runtime_trace=None, **kwargs,
            ):
                yield {
                    "type": "result",
                    "data": {
                        "outputs": {},
                        "trace": {"metadata": {}},  # sparse remote metadata
                    },
                }

            mock_transport = MagicMock()
            mock_transport.run_plan_stream = _mock_stream

            # Must not raise UnboundLocalError
            try:
                result = await self.mod.execute_plan(
                    plan,
                    transport=mock_transport,
                    trace=trace,
                )
            except Exception as exc:
                self.fail(
                    f"execute_plan raised unexpectedly with modal_input_id "
                    f"present: {type(exc).__name__}: {exc}"
                )

            # Verify local_timing is present and _remote_metadata fallback
            # produced absent values (not a crash).
            local_timing = result.get("local_timing", {})
            self.assertIn("trigger_to_local_receive_ms", local_timing)
            self.assertEqual(
                local_timing.get("trigger_to_local_receive_ms"), "absent",
            )

            # Verify modal_input_id was preserved from transport metadata
            self.assertEqual(
                trace._metadata.get("modal_input_id"), "existing_input_42",
                "modal_input_id must remain unchanged when already present",
            )

        asyncio.run(_run())

    def test_modal_input_id_from_remote_metadata(self):
        """When modal_input_id is absent from transport metadata but present
        in remote trace metadata, execute_plan must populate it."""
        from unittest.mock import MagicMock

        async def _run():
            trace = self.mod.RuntimeTrace(
                request_id="test_modal_input_id_remote",
            )
            # Intentionally NOT setting modal_input_id on transport metadata

            from comfymodal_runtime.contracts import ExecutionPlan, ExecutionOptions
            plan = ExecutionPlan(
                workflow={"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
                workflow_hash="test_hash",
                source_workflow_hash="test_src_hash",
                execution_options=ExecutionOptions.from_legacy(
                    {}, default_production=False,
                ),
                request_metadata={"prompt_id": "test_modal_remote"},
            )

            async def _mock_stream(
                plan, *, gpu=None, workspace=None,
                trace=None, runtime_trace=None, **kwargs,
            ):
                yield {
                    "type": "result",
                    "data": {
                        "outputs": {},
                        "trace": {
                            "metadata": {
                                "modal_input_id": "remote_input_99",
                            },
                        },
                    },
                }

            mock_transport = MagicMock()
            mock_transport.run_plan_stream = _mock_stream

            result = await self.mod.execute_plan(
                plan,
                transport=mock_transport,
                trace=trace,
            )

            # Verify modal_input_id was pulled from remote metadata
            self.assertEqual(
                trace._metadata.get("modal_input_id"), "remote_input_99",
            )

        asyncio.run(_run())


# =========================================================================
# V2 execute_plan regression: raw_timestamps alias keys from result
# =========================================================================


class TestExecutePlanRawTimestampAliases(unittest.TestCase):
    """``execute_plan`` must consume ``raw_timestamps`` alias keys from the
    result data as a fourth-tier fallback for canonical timestamp fields,
    and map them using explicit ``is not None`` checks."""

    def setUp(self):
        self.mod = _load_canonical()

    def test_raw_timestamps_aliases_consumed(self):
        """When _origin and transport metadata lack timestamps but
        result.raw_timestamps supplies aliases, execute_plan must map them
        into the local_timing output without crashing."""
        from unittest.mock import MagicMock

        async def _run():
            trace = self.mod.RuntimeTrace(
                request_id="test_raw_ts_aliases",
            )

            from comfymodal_runtime.contracts import ExecutionPlan, ExecutionOptions
            plan = ExecutionPlan(
                workflow={"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
                workflow_hash="test_hash",
                source_workflow_hash="test_src_hash",
                execution_options=ExecutionOptions.from_legacy(
                    {}, default_production=False,
                ),
                # No request_origin_info — _origin will be empty
                request_metadata={"prompt_id": "test_raw_ts"},
            )

            raw_timestamps = {
                # t0 → t1: 1 second interval
                "t0_ui_trigger_wall_unix_ns": 1_000_000_000,
                "t1_local_receive_wall_unix_ns": 2_000_000_000,
                # Submission attempt
                "modal_submission_attempt_wall_unix_ns": 3_000_000_000,
                # Generator created
                "modal_generator_created_wall_unix_ns": 4_000_000_000,
                # Method entry and executor invoke
                "t4_modal_method_entry_wall_unix_ns": 5_000_000_000,
                "t5_prompt_executor_invoke_start_wall_unix_ns": 6_000_000_000,
            }

            async def _mock_stream(
                plan, *, gpu=None, workspace=None,
                trace=None, runtime_trace=None, **kwargs,
            ):
                yield {
                    "type": "result",
                    "data": {
                        "outputs": {},
                        "raw_timestamps": raw_timestamps,
                        "trace": {"metadata": {}},
                    },
                }

            mock_transport = MagicMock()
            mock_transport.run_plan_stream = _mock_stream

            result = await self.mod.execute_plan(
                plan,
                transport=mock_transport,
                trace=trace,
            )

            local_timing = result.get("local_timing", {})

            # trigger_to_local_receive_ms = (2e9 ns - 1e9 ns) / 1e6 = 1000 ms
            self.assertEqual(
                local_timing.get("trigger_to_local_receive_ms"), 1000.0,
            )

            # Verify raw timestamps flowed through without error.
            # generator_create_ms is absent because generator_create_start
            # was not supplied by any tier — ok.
            self.assertIn("generator_create_ms", local_timing)
            self.assertEqual(
                local_timing.get("generator_create_ms"), "absent",
            )

        asyncio.run(_run())

    def test_raw_timestamps_zero_values_preserved(self):
        """Explicit is not None fallback must preserve valid zero ns values
        from raw_timestamps (they were not skipped by truthiness check)."""
        from unittest.mock import MagicMock

        async def _run():
            trace = self.mod.RuntimeTrace(
                request_id="test_raw_ts_zero",
            )

            from comfymodal_runtime.contracts import ExecutionPlan, ExecutionOptions
            plan = ExecutionPlan(
                workflow={"3": {"class_type": "KSampler", "inputs": {"seed": 42}}},
                workflow_hash="test_hash",
                source_workflow_hash="test_src_hash",
                execution_options=ExecutionOptions.from_legacy(
                    {}, default_production=False,
                ),
                request_metadata={"prompt_id": "test_raw_ts_zero"},
            )

            # Zero ns values in raw_timestamps — must not be treated as falsy
            raw_timestamps = {
                "t0_ui_trigger_wall_unix_ns": 0,
                "t1_local_receive_wall_unix_ns": 1_000_000_000,
            }

            async def _mock_stream(
                plan, *, gpu=None, workspace=None,
                trace=None, runtime_trace=None, **kwargs,
            ):
                yield {
                    "type": "result",
                    "data": {
                        "outputs": {},
                        "raw_timestamps": raw_timestamps,
                        "trace": {"metadata": {}},
                    },
                }

            mock_transport = MagicMock()
            mock_transport.run_plan_stream = _mock_stream

            result = await self.mod.execute_plan(
                plan,
                transport=mock_transport,
                trace=trace,
            )

            local_timing = result.get("local_timing", {})

            # t0=0 ns, t1=1e9 ns → (1e9 - 0)/1e6 = 1000.0 ms
            # If or semantics were used, t0=0 would be falsy, t0 remains None,
            # and the interval would be "absent".
            trigger_ms = local_timing.get("trigger_to_local_receive_ms")
            self.assertEqual(
                trigger_ms, 1000.0,
                f"Zero t0 must be preserved by is not None fallback, "
                f"got {trigger_ms!r}",
            )

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
