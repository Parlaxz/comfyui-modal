import ast
import importlib
import os
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "__init__.py"
WEB_PATH = REPO_ROOT / "web" / "modal-node.js"
BENCHMARK_SCRIPT_PATH = REPO_ROOT / "benchmark_modal.py"
BENCHMARK_DIRECT_PATH = REPO_ROOT / "tools" / "benchmark_v2_direct.py"


def _find_func(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _func_body(source: str, tree: ast.Module, name: str) -> str:
    """Return the source text of the named top-level function (or '')."""
    node = _find_func(tree, name)
    if node is None:
        return ""
    return ast.get_source_segment(source, node) or ""


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

    def test_benchmark_script_references_redeploy_batch_and_uses_external_runs_dir(self):
        source = BENCHMARK_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("redeploy_modal_and_run_comfyui.bat", source)
        self.assertIn("get_benchmark_runs_dir", source)
        self.assertIn("_BENCHMARK_RUNS_DIRNAME", source)

    def test_benchmark_script_has_utf8_deploy_fallback_and_direct_launcher(self):
        source = BENCHMARK_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("PYTHONIOENCODING", source)
        self.assertIn("python_embeded", source)
        self.assertIn("ComfyUI\\main.py", source)

    def test_benchmark_script_targets_only_local_comfyui_main_processes(self):
        source = BENCHMARK_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("ComfyUI\\main.py", source)
        self.assertIn("python.exe", source)


class BenchmarkV2PolicyMetadataASTTests(unittest.TestCase):
    """AST-level proofs for the VAE policy / provenance metadata in
    ``tools/benchmark_v2_direct.py``.

    These assert the *source structure* without invoking Modal or importing
    the heavy runtime: requested metadata is environment-derived, applied
    metadata is trace-derived and fail-closed, and no per-request cast or
    conversion is introduced.
    """

    def setUp(self):
        self.source = BENCHMARK_DIRECT_PATH.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def test_requested_policy_and_prefetch_constants_are_environment_derived(self):
        self.assertIn('_VAE_POLICY_ENV_KEY = "COMFYMODAL_V2_VAE_POLICY"', self.source)
        self.assertIn(
            '_VAE_PREFETCH_ENV_KEY = "COMFYMODAL_V2_VAE_PREFETCH_MODE"', self.source
        )
        self.assertIn('_VAE_POLICY_DEFAULT = "v0"', self.source)
        self.assertIn('_VAE_PREFETCH_DEFAULT = "off"', self.source)

    def test_requested_metadata_helpers_read_environment(self):
        policy_body = _func_body(self.source, self.tree, "_requested_vae_policy")
        self.assertIn("os.environ.get", policy_body)
        self.assertIn("_VAE_POLICY_DEFAULT", policy_body)

        prefetch_body = _func_body(self.source, self.tree, "_requested_vae_prefetch_mode")
        self.assertIn("os.environ.get", prefetch_body)
        self.assertIn("_VAE_PREFETCH_DEFAULT", prefetch_body)

    def test_applied_policy_is_trace_derived_and_fail_closed(self):
        helper_body = _func_body(self.source, self.tree, "_extract_applied_vae_policy")
        self.assertIn("cpu_snapshot_vae_policy_ready", helper_body)
        self.assertIn('"events"', helper_body)
        self.assertIn("trace", helper_body)
        # Fail-closed: an explicit None is returned when evidence is absent.
        self.assertIn("return None", helper_body)
        self.assertNotIn("_VAE_POLICY_DEFAULT", helper_body)

    def test_no_per_request_vae_policy_conversion_or_validation_introduced(self):
        # The benchmark must never run policy conversion/validation per request.
        self.assertNotIn("_validate_vae_policy_metadata", self.source)
        # The applied-policy helper must only read trace metadata, never cast.
        helper_body = _func_body(self.source, self.tree, "_extract_applied_vae_policy")
        self.assertNotIn("torch", helper_body)
        self.assertNotIn(".cast(", helper_body)
        self.assertNotIn(".to(", helper_body)
        self.assertNotIn("torch.bfloat16", helper_body)

    def test_run_one_embeds_vae_policy_and_provenance_metadata(self):
        body = _func_body(self.source, self.tree, "_run_one")
        self.assertIn('"vae_policy"', body)
        self.assertIn('"requested_policy"', body)
        self.assertIn('"requested_prefetch_mode"', body)
        self.assertIn('"applied_policy"', body)
        self.assertIn('"provenance"', body)
        self.assertIn('"workflow_hash"', body)
        self.assertIn('"source_sha"', body)


class BenchmarkV2PolicyMetadataUnitTests(unittest.TestCase):
    """Functional proofs for the environment/trace-derived helpers."""

    @classmethod
    def setUpClass(cls):
        cls.mod = importlib.import_module("tools.benchmark_v2_direct")

    def _set_env(self, key: str, value: str | None) -> str | None:
        previous = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
        return previous

    def test_requested_policy_defaults_to_v0(self):
        previous = self._set_env("COMFYMODAL_V2_VAE_POLICY", None)
        try:
            self.assertEqual(self.mod._requested_vae_policy(), "v0")
        finally:
            self._set_env("COMFYMODAL_V2_VAE_POLICY", previous)

    def test_requested_policy_reads_environment(self):
        previous = self._set_env("COMFYMODAL_V2_VAE_POLICY", "v1")
        try:
            self.assertEqual(self.mod._requested_vae_policy(), "v1")
        finally:
            self._set_env("COMFYMODAL_V2_VAE_POLICY", previous)

    def test_requested_prefetch_defaults_to_off(self):
        previous = self._set_env("COMFYMODAL_V2_VAE_PREFETCH_MODE", None)
        try:
            self.assertEqual(self.mod._requested_vae_prefetch_mode(), "off")
        finally:
            self._set_env("COMFYMODAL_V2_VAE_PREFETCH_MODE", previous)

    def test_requested_prefetch_reads_environment(self):
        previous = self._set_env("COMFYMODAL_V2_VAE_PREFETCH_MODE", "full")
        try:
            self.assertEqual(self.mod._requested_vae_prefetch_mode(), "full")
        finally:
            self._set_env("COMFYMODAL_V2_VAE_PREFETCH_MODE", previous)

    def test_applied_policy_fail_closed_when_trace_evidence_absent(self):
        self.assertIsNone(self.mod._extract_applied_vae_policy({}))
        self.assertIsNone(
            self.mod._extract_applied_vae_policy(
                {"trace": {"events": [{"name": "unrelated_event"}]}}
            )
        )

    def test_applied_policy_recovered_from_trace_event(self):
        result = {
            "trace": {
                "events": [
                    {"name": "other", "metadata": {"policy": "v0"}},
                    {"name": "cpu_snapshot_vae_policy_ready", "metadata": {"policy": "v1"}},
                ]
            }
        }
        self.assertEqual(self.mod._extract_applied_vae_policy(result), "v1")

    def test_workflow_hash_is_stable_and_deterministic(self):
        wf = {"nodes": [{"id": 1}], "links": [{"a": 1}]}
        self.assertEqual(
            self.mod._workflow_hash(wf), self.mod._workflow_hash(wf)
        )
        self.assertNotEqual(
            self.mod._workflow_hash(wf), self.mod._workflow_hash({"nodes": [{"id": 2}]})
        )

    def test_workflow_source_sha_fail_closed_when_absent(self):
        self.assertEqual(self.mod._workflow_source_sha({"nodes": []}), "absent")


if __name__ == "__main__":
    unittest.main()
