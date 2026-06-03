import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "__init__.py"
WEB_PATH = REPO_ROOT / "web" / "modal-node.js"
BENCHMARK_SCRIPT_PATH = REPO_ROOT / "benchmark_modal.py"


class BenchmarkHarnessASTTests(unittest.TestCase):
    def test_benchmark_script_exists(self):
        self.assertTrue(BENCHMARK_SCRIPT_PATH.is_file(), f"Missing benchmark script: {BENCHMARK_SCRIPT_PATH}")

    def test_init_persists_latest_benchmark_workflow_file(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("latest_benchmark_workflow.json", source)

    def test_init_stores_trace_in_history_meta_for_benchmark_polling(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn('result["trace"] = _merged_trace', source)
        self.assertIn('"trace"', source)
        self.assertIn('"meta"', source)

    def test_web_hook_posts_prompt_payload_to_benchmark_snapshot_route(self):
        source = WEB_PATH.read_text(encoding="utf-8")
        self.assertIn("/comfymodal/benchmark/workflow", source)
        self.assertIn("route === \"/prompt\"", source)
        self.assertIn("options.body", source)

    def test_benchmark_script_uses_snapshot_and_local_prompt_routes(self):
        source = BENCHMARK_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("/comfymodal/benchmark/workflow", source)
        self.assertIn("/comfymodal/prompt", source)
        self.assertIn("/history/", source)

    def test_benchmark_script_references_saved_workflows_folder(self):
        source = BENCHMARK_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("saved workflows", source)
        self.assertIn("flux_2-klein-9b(2).json", source)

    def test_benchmark_script_references_redeploy_batch_and_output_folder(self):
        source = BENCHMARK_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("redeploy_modal_and_run_comfyui.bat", source)
        self.assertIn("benchmark_runs", source)

    def test_benchmark_script_has_utf8_deploy_fallback_and_direct_launcher(self):
        source = BENCHMARK_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("PYTHONIOENCODING", source)
        self.assertIn("python_embeded", source)
        self.assertIn("ComfyUI\\main.py", source)

    def test_benchmark_script_targets_only_local_comfyui_main_processes(self):
        source = BENCHMARK_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("ComfyUI\\main.py", source)
        self.assertIn("python.exe", source)


if __name__ == "__main__":
    unittest.main()
