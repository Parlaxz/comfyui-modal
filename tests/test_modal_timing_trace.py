import ast
import unittest
from pathlib import Path

from timing_trace import Trace, coerce_t0_from_browser


REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "__init__.py"
MODAL_CLIENT_PATH = REPO_ROOT / "modal_client.py"


class TimingTraceUnitTests(unittest.TestCase):
    def test_coerce_t0_from_browser_prefers_epoch_ms(self):
        value = coerce_t0_from_browser({"t0_client_press_ms": 12345})
        self.assertEqual(value, 12.345)

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


class TimingTraceWiringTests(unittest.TestCase):
    def test_modal_client_run_prompt_accepts_trace_argument(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        run_prompt = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_prompt"
        )
        arg_names = [arg.arg for arg in run_prompt.args.args]
        self.assertEqual(arg_names, ["workflow", "input_images", "trace"])
        self.assertIn("run_prompt.remote(workflow, input_images or {}, trace or {})", source)

    def test_init_tracks_local_and_browser_trace_stamps(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        for token in (
            "t1_local_recv",
            "t2_local_dispatch",
            "t10_local_materialized",
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


if __name__ == "__main__":
    unittest.main()
