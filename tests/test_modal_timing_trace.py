import ast
import unittest
from pathlib import Path

from timing_trace import Trace, coerce_t0_from_browser, extract_remote_timing_payload

from comfymodal_runtime.contracts import TraceEvent
from comfymodal_runtime.trace import RuntimeTrace, merge_runtime_traces


REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "__init__.py"
MODAL_CLIENT_PATH = REPO_ROOT / "modal_client.py"


class TimingTraceUnitTests(unittest.TestCase):
    def test_coerce_t0_from_browser_prefers_queue_prompt_start_ms(self):
        """queue_prompt_start_ms (epoch ms) must be preferred over legacy fields."""
        value = coerce_t0_from_browser({
            "queue_prompt_start_ms": 5000000,
            "t0_client_press": 9999.0,
            "t0_client_press_ms": 9999000,
        })
        self.assertIsNotNone(value)
        self.assertEqual(value, 5000.0)

    def test_coerce_t0_from_browser_falls_back_when_queue_missing(self):
        """Without queue_prompt_start_ms, falls back to t0_client_press."""
        value = coerce_t0_from_browser({"t0_client_press": 1234.0})
        self.assertEqual(value, 1234.0)

    def test_coerce_t0_from_browser_falls_back_to_ms_when_both_missing(self):
        value = coerce_t0_from_browser({"t0_client_press_ms": 12345})
        self.assertEqual(value, 12.345)

    def test_coerce_t0_from_browser_none_on_empty(self):
        self.assertIsNone(coerce_t0_from_browser({}))
        self.assertIsNone(coerce_t0_from_browser(None))

    def test_coerce_t0_from_browser_ignores_non_numeric_queue(self):
        """Non-numeric queue_prompt_start_ms must be ignored (not crash)."""
        value = coerce_t0_from_browser({
            "queue_prompt_start_ms": "not-a-number",
            "t0_client_press": 500.0,
        })
        self.assertEqual(value, 500.0)  # falls through to t0_client_press

    def test_coerce_t0_from_browser_rejects_bool(self):
        """bool values must be rejected in ALL numeric t0 branches."""
        # queue_prompt_start_ms is bool True
        self.assertIsNone(coerce_t0_from_browser({"queue_prompt_start_ms": True}))
        # t0_client_press is bool False
        self.assertIsNone(coerce_t0_from_browser({"t0_client_press": False,
                                                    "t0_client_press_ms": True}))
        # t0_client_press_ms is bool True
        self.assertIsNone(coerce_t0_from_browser({"t0_client_press_ms": True}))
        # t0_perf_ms + t0_perf_now_ms are bool
        self.assertIsNone(coerce_t0_from_browser({"t0_perf_ms": True,
                                                    "t0_perf_now_ms": False}))
        # All-numeric payload must still work when bools are also present
        value = coerce_t0_from_browser({
            "queue_prompt_start_ms": True,  # rejected
            "t0_client_press": False,        # rejected
            "t0_client_press_ms": 50000,     # accepted
        })
        self.assertEqual(value, 50.0)

    def test_coerce_t0_from_browser_top_level_queue_wins_over_nested_legacy(self):
        """Top-level body queue_prompt_start_ms must beat a nested
        body["trace"]["t0_client_press"] (simulating the route handler's
        (coerce_t0_from_browser(body) or coerce_t0_from_browser(body["trace"]))
        pattern)."""
        body = {
            "queue_prompt_start_ms": 6000000,     # top-level: 6000.0 s
            "trace": {"t0_client_press": 9999.0},  # nested legacy: 9999.0 s
        }
        # Simulate the route-handler two-arg call order (body first)
        t0 = coerce_t0_from_browser(body) or coerce_t0_from_browser(body.get("trace", {}))
        self.assertEqual(t0, 6000.0,
                         "top-level queue_prompt_start_ms must win over nested t0")

        # When top-level lacks queue_prompt_start_ms, nested t0 wins
        body2 = {
            "trace": {"t0_client_press": 7777.0},
        }
        t0b = coerce_t0_from_browser(body2) or coerce_t0_from_browser(body2.get("trace", {}))
        self.assertEqual(t0b, 7777.0,
                         "nested t0_client_press must win when top-level has no queue timestamp")

    def test_summary_computes_stage_deltas(self):
        trace = Trace(prompt_id="abc", t0=100.0)
        trace.mark("t0_client_press", 100.0)
        trace.mark("t1_local_recv", 100.010)
        trace.mark("t2_local_dispatch", 100.020)
        trace.mark("t3_modal_entry", 100.120)
        trace.mark("t3b_validate_done", 100.140)
        trace.mark("t4_clip_load_start", 100.140)
        trace.mark("t4_clip_load_end", 100.190)
        trace.mark("t5_text_encode_start", 100.190)
        trace.mark("t5_text_encode_end", 100.220)
        trace.mark("t6_sampler_start", 100.220)
        trace.mark("t6_sampler_end", 100.520)
        trace.mark("t7_vae_decode_start", 100.520)
        trace.mark("t7_vae_decode_end", 100.580)
        trace.mark("t8_image_written", 100.600)
        trace.mark("t8b_outputs_collected", 100.640)
        trace.mark("t9_modal_return", 100.650)
        trace.mark("t10_browser_recv", 100.660)

        summary = trace.summary()
        self.assertEqual(summary["prompt_id"], "abc")
        self.assertEqual(summary["deltas_ms"]["t0_to_t1"], 10.0)
        self.assertEqual(summary["deltas_ms"]["clip_load"], 50.0)
        self.assertEqual(summary["deltas_ms"]["sampler"], 300.0)
        self.assertEqual(summary["deltas_ms"]["image_io"], 40.0)
        self.assertEqual(summary["deltas_ms"]["t9_to_t10"], 10.0)

    def test_summary_supports_fast_restore_without_build_stage(self):
        trace = Trace(prompt_id="abc", t0=100.0)
        trace.mark("t2_local_dispatch", 100.020)
        trace.mark("t3_modal_entry", 102.900)
        summary = trace.summary()
        self.assertEqual(summary["deltas_ms"]["t2_to_t3"], 2880.0)

    def test_summary_reports_modal_to_return_without_browser_t10(self):
        trace = Trace(prompt_id="abc", t0=100.0)
        trace.mark("t2_local_dispatch", 100.020)
        trace.mark("t9_modal_return", 100.650)
        summary = trace.summary()
        self.assertEqual(summary["deltas_ms"]["modal_to_return"], 630.0)
        self.assertNotIn("modal_to_browser", summary["deltas_ms"])

    def test_summary_falls_back_to_local_materialized_when_browser_t10_missing(self):
        trace = Trace(prompt_id="abc", t0=100.0)
        trace.mark("t2_local_dispatch", 100.020)
        trace.mark("t9_modal_return", 100.650)
        trace.mark("t10_local_materialized", 100.660)
        summary = trace.summary()
        self.assertEqual(summary["deltas_ms"]["t9_to_t10"], 10.0)
        self.assertEqual(summary["deltas_ms"]["modal_to_browser"], 640.0)

    def test_extract_remote_timing_payload_carries_waterfall(self):
        result = {
            "trace": {"stages": {}},
            "waterfall": {"status": "measured", "stages": [], "total_ms": 12.0},
            "outputs": {"9": [{"data": "aGVsbG8="}]},  # base64 must be excluded
        }
        payload = extract_remote_timing_payload(result)
        self.assertIn("waterfall", payload)
        self.assertEqual(payload["waterfall"]["total_ms"], 12.0)
        self.assertNotIn("outputs", payload)

    def test_extract_remote_timing_payload_absent_waterfall_omitted(self):
        payload = extract_remote_timing_payload({"trace": {"stages": {}}})
        self.assertNotIn("waterfall", payload)


class TimingTraceWiringTests(unittest.TestCase):
    def test_modal_client_run_prompt_accepts_trace_argument(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        run_prompt = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_prompt"
        )
        arg_names = [arg.arg for arg in run_prompt.args.args]
        self.assertEqual(arg_names, ["workflow", "input_images", "trace", "production_report", "gpu", "modal_options", "workspace"])
        self.assertIn("trace or {}", source)

    def test_init_tracks_local_and_browser_trace_stamps(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        for token in (
            "t1_local_recv",
            "t2_local_dispatch",
            "t10_local_materialized",
            "client_generate_clicked_or_request_start",
            "client_modal_call_start",
            "client_first_remote_log_seen",
            "client_remote_result_received",
            "client_result_decode_start",
            "client_result_decode_done",
            "client_file_write_start",
            "client_file_write_done",
            "client_comfy_notify_start",
            "client_comfy_notify_done",
            "trace.fields()",
            'result.get("trace")',
        ):
            self.assertIn(token, source)
        self.assertNotIn(
            'trace.mark("t10_browser_recv")',
            source,
            "__init__.py must not claim the browser received the response before it actually does",
        )

    def test_comfyapp_stage_capture_not_gated_by_profiling_flag(self):
        comfyapp_path = REPO_ROOT / "comfyapp.py"
        source = comfyapp_path.read_text(encoding="utf-8")
        self.assertIn("def _on_sync(event, data, sid):", source)
        self.assertIn("self._begin_profiled_node(node, now)", source)
        self.assertIn("self._finish_profiled_node(now)", source)
        self.assertIn("self._note_progress_event(data)", source)
        self.assertNotIn("def _on_sync(event, data, sid):\n            if not PROFILING_ENABLED:\n                return", source)

    def test_comfyapp_sampler_trace_uses_progress_window(self):
        comfyapp_path = REPO_ROOT / "comfyapp.py"
        source = comfyapp_path.read_text(encoding="utf-8")
        self.assertIn('windows[stage]["start"] = first', source)
        self.assertIn('windows[stage]["end"] = last or first', source)
        self.assertIn('windows[stage]["progress_start"] = first', source)
        self.assertIn('windows[stage]["progress_end"] = last or first', source)

    def test_comfyapp_sampler_trace_does_not_lock_first_sampler_node(self):
        comfyapp_path = REPO_ROOT / "comfyapp.py"
        source = comfyapp_path.read_text(encoding="utf-8")
        self.assertIn('stage != "sampler" and "start" not in windows[stage]', source)
        self.assertIn('windows[stage]["source"] = "progress"', source)
        self.assertIn('windows[stage]["source"] = "node_duration"', source)

    def test_browser_timing_fields_sent_through_fourfield_chain(self):
        """The four browser timing fields must be extracted in the route handler
        and flow through trace._t → extra_data → execution_success."""
        source = INIT_PATH.read_text(encoding="utf-8")
        # Route handler must reference all four fields in a loop or individually
        for _f in ("queue_prompt_start_ms", "prompt_fetch_start_ms",
                    "queue_to_prompt_fetch_ms", "serialized_prompt_bytes"):
            self.assertIn(
                _f, source,
                f"__init__.py must reference {_f} for browser timing propagation",
            )
        # MustNOT call mark() with these (they are durations/byte counts)
        self.assertNotIn(
            'trace.mark("queue_to_prompt_fetch_ms"',
            source,
            "queue_to_prompt_fetch_ms must not be passed to trace.mark()",
        )
        self.assertNotIn(
            'trace.mark("serialized_prompt_bytes"',
            source,
            "serialized_prompt_bytes must not be passed to trace.mark()",
        )
        # Must coerce numeric defensively
        self.assertIn("_coerce_numeric", source)

    def test_browser_timing_fields_survive_in_final_trace(self):
        """Fields set directly on trace._t appear in trace.fields() and
        survive a round-trip through Trace construction + update."""
        t = Trace(prompt_id="test-1", t0=1000.0)
        t._t["queue_prompt_start_ms"] = 5000000.0
        t._t["prompt_fetch_start_ms"] = 5000100.0
        t._t["queue_to_prompt_fetch_ms"] = 100.0
        t._t["serialized_prompt_bytes"] = 2048.0

        # fields() must carry them
        fields = t.fields()
        self.assertEqual(fields.get("queue_prompt_start_ms"), 5000000.0)
        self.assertEqual(fields.get("prompt_fetch_start_ms"), 5000100.0)
        self.assertEqual(fields.get("queue_to_prompt_fetch_ms"), 100.0)
        self.assertEqual(fields.get("serialized_prompt_bytes"), 2048.0)

        # summary() must include them in stages
        summary = t.summary()
        stages = summary.get("stages", {})
        self.assertEqual(stages.get("queue_prompt_start_ms"), 5000000.0)
        # They must NOT affect timing_quality (not required fields)
        self.assertIn("timing_quality", summary)

        # Round-trip via update()
        t2 = Trace(prompt_id="test-2", t0=2000.0)
        t2.update(fields)
        self.assertEqual(t2.fields().get("queue_prompt_start_ms"), 5000000.0)
        self.assertEqual(t2.fields().get("serialized_prompt_bytes"), 2048.0)

    def test_browser_timing_fields_defensive_numeric_coercion(self):
        """The inline _coerce_numeric logic must reject non-numeric and
        bool values."""
        def _coerce_numeric(v):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
            return None

        self.assertEqual(_coerce_numeric(5000), 5000.0)
        self.assertEqual(_coerce_numeric(3.14), 3.14)
        self.assertIsNone(_coerce_numeric("not-a-number"))
        self.assertIsNone(_coerce_numeric(None))
        self.assertIsNone(_coerce_numeric(True))
        self.assertIsNone(_coerce_numeric(False))
        self.assertIsNone(_coerce_numeric([1, 2, 3]))
        self.assertIsNone(_coerce_numeric({"a": 1}))
# merge_runtime_traces behavior
# ---------------------------------------------------------------------------


class TestMergeRuntimeTraces(unittest.TestCase):
    """Direct behavior tests for merge_runtime_traces."""

    def test_remote_events_survive(self):
        local = RuntimeTrace(process="local")
        local.emit("local_step", phase="test")
        remote = RuntimeTrace(process="remote")
        remote.emit("remote_step", phase="test")
        merged = merge_runtime_traces(local, remote)
        names = {e.name for e in merged.events}
        self.assertIn("local_step", names)
        self.assertIn("remote_step", names)

    def test_exact_duplicates_removed(self):
        trace = RuntimeTrace(process="local")
        trace.emit("event_a", phase="test")
        trace.emit("event_b", phase="test")
        merged = merge_runtime_traces(trace, trace)
        self.assertEqual(len(merged.events), 2,
                         "Exact duplicates should be removed")

    def test_cross_process_sorted_by_wall_time(self):
        local_trace = RuntimeTrace(process="local")
        local_trace._events.append(TraceEvent(
            name="later_local", process="local", phase="test",
            wall_unix_ns=2000, monotonic_ns=0,
        ))
        remote_trace = RuntimeTrace(process="remote")
        remote_trace._events.append(TraceEvent(
            name="earlier_remote", process="remote", phase="test",
            wall_unix_ns=1000, monotonic_ns=0,
        ))
        merged = merge_runtime_traces(local_trace, remote_trace)
        wall_times = [e.wall_unix_ns for e in merged.events]
        self.assertEqual(wall_times, sorted(wall_times))
        self.assertEqual(merged.events[0].name, "earlier_remote")

    def test_restore_and_execution_traces_coexist(self):
        restore = RuntimeTrace(process="remote")
        restore.emit("restore_start", phase="restore")
        exec_trace = RuntimeTrace(process="remote")
        exec_trace.emit("execution_done", phase="execution")
        merged = merge_runtime_traces(restore, exec_trace)
        phases = {e.phase for e in merged.events}
        self.assertIn("restore", phases)
        self.assertIn("execution", phases)
        self.assertEqual(len(merged.events), 2)

    def test_mixed_none_values_ignored(self):
        t = RuntimeTrace(process="local")
        t.emit("a", phase="test")
        merged = merge_runtime_traces(t, None, t)
        self.assertEqual(len(merged.events), 1)

    def test_metadata_merged_in_input_order(self):
        t1 = RuntimeTrace(process="local")
        t1.set_metadata(keep="me", version="first")
        t2 = RuntimeTrace(process="remote")
        t2.set_metadata(version="second")
        merged = merge_runtime_traces(t1, t2)
        self.assertEqual(merged._metadata.get("keep"), "me")
        self.assertEqual(merged._metadata.get("version"), "second")

    def test_mapping_input_normalized(self):
        t = RuntimeTrace(process="local")
        t.emit("mapped_event", phase="test")
        as_dict = t.to_dict()
        merged = merge_runtime_traces(as_dict)
        self.assertEqual(len(merged.events), 1)
        self.assertEqual(merged.events[0].name, "mapped_event")

    def test_request_id_uses_first_non_empty(self):
        t1 = RuntimeTrace(process="local", request_id="req-001")
        t2 = RuntimeTrace(process="remote", request_id="req-002")
        merged = merge_runtime_traces(t1, t2)
        self.assertEqual(merged.request_id, "req-001")


class TestContainerEntryStageMapping(unittest.TestCase):
    """container_entry event maps to t3_modal_entry in legacy timing
    and lifecycle remote_method_entry cannot masquerade as container_entry."""

    def test_container_entry_maps_to_t3_modal_entry(self):
        t = RuntimeTrace(process="remote")
        t.emit("container_entry", phase="execution")
        legacy = t.to_legacy_timing()
        stages = legacy.get("stages", {})
        self.assertIn("t3_modal_entry", stages,
                      "container_entry must map to t3_modal_entry in legacy stages")

    def test_lifecycle_remote_method_entry_not_mapped_to_t3_modal_entry(self):
        t = RuntimeTrace(process="remote")
        t.emit("remote_method_entry", phase="lifecycle", metadata={
            "method_name": "startup", "container_session_id": "cid-1",
        })
        legacy = t.to_legacy_timing()
        stages = legacy.get("stages", {})
        self.assertNotIn("t3_modal_entry", stages,
                         "lifecycle remote_method_entry must NOT produce t3_modal_entry")

    def test_remote_method_entry_shares_name_with_lifecycle(self):
        """Both lifecycle and execution use remote_method_entry; only
        container_entry produces t3_modal_entry."""
        lifecycle = RuntimeTrace(process="remote")
        lifecycle.emit("remote_method_entry", phase="lifecycle", metadata={"method_name": "restore"})
        execution = RuntimeTrace(process="remote")
        execution.emit("remote_method_entry", phase="method", metadata={"method_name": "run_plan_stream"})
        execution.emit("container_entry", phase="execution")
        merged = merge_runtime_traces(lifecycle, execution)
        legacy = merged.to_legacy_timing()
        stages = legacy.get("stages", {})
        self.assertIn("t3_modal_entry", stages,
                      "merged trace with container_entry must include t3_modal_entry")
        # Both remote_method_entry events survive but don't map to legacy stages
        counts = {}
        for e in merged.events:
            counts[e.name] = counts.get(e.name, 0) + 1
        self.assertEqual(counts.get("remote_method_entry"), 2,
                         "Both lifecycle and execution remote_method_entry must survive merge")

    def test_container_entry_timestamp_carries_through_merge(self):
        """The wall-clock timestamp of the container_entry event is preserved
        through merge_runtime_traces."""
        import time
        fake_wall_ns = int(1_500_000_000_000)  # 2027-ish fixed timestamp
        exec_trace = RuntimeTrace(process="remote")
        exec_trace.emit("container_entry", phase="execution")
        # Replace the auto-generated wall time with our known value
        ce_event = [e for e in exec_trace.events if e.name == "container_entry"][0]
        import dataclasses
        ce_event = dataclasses.replace(ce_event, wall_unix_ns=fake_wall_ns)
        exec_trace._events = [ce_event if e.name == "container_entry" else e for e in exec_trace._events]

        lc = RuntimeTrace(process="remote")
        lc.emit("remote_lifecycle_start", phase="lifecycle")
        merged = merge_runtime_traces(lc, exec_trace)
        legacy = merged.to_legacy_timing()
        self.assertAlmostEqual(legacy["stages"]["t3_modal_entry"], 1500.0, places=2)


if __name__ == "__main__":
    unittest.main()
