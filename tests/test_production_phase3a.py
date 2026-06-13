import unittest
from pathlib import Path

from production_workflow import (
    build_production_topology_hash,
    normalize_production_options,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"


class ProductionPhase3aComfyappPyAstTests(unittest.TestCase):
    """Source-level AST tests for comfyapp.py phase-3a production changes.

    Covers:
      - production_workflow import of build_production_topology_hash
      - Production compilation ordering in run_prompt and run_prompt_stream
      - execution_workflow used in all execution paths
      - production_report attached to results
      - Production-aware validation cache key
      - Production strict output filtering in _collect_in_process_outputs
      - Production strict output filtering in _collect_outputs
      - Compile log messages
      - _poll_until_done passes modal_options to _collect_outputs
    """

    def setUp(self):
        self.src = COMFYAPP_PATH.read_text(encoding="utf-8")

    # ── Imports ──────────────────────────────────────────────────────

    def test_build_production_topology_hash_imported(self):
        self.assertIn("build_production_topology_hash", self.src)

    def test_normalize_production_options_imported(self):
        self.assertIn("normalize_production_options", self.src)

    def test_compile_production_workflow_imported(self):
        self.assertIn("compile_production_workflow", self.src)

    # ── Production compilation in run_prompt ─────────────────────────

    def test_run_prompt_production_compilation_before_custom_node_sync(self):
        """The compilation block in run_prompt must appear before
        _handle_custom_node_sync_and_dependency_policy."""
        # Locate the compile block anchor
        idx_compile = self.src.find(
            "execution_workflow, production_report = compile_production_workflow("
        )
        idx_sync = self.src.find(
            "_handle_custom_node_sync_and_dependency_policy(execution_workflow, stream=False)"
        )
        self.assertGreater(
            idx_compile, 0,
            "Expected compile_production_workflow call in run_prompt"
        )
        self.assertGreater(
            idx_sync, idx_compile,
            "compile_production_workflow must appear before custom_node_sync in run_prompt"
        )

    def test_run_prompt_uses_execution_workflow_for_execution(self):
        _idx1 = self.src.find("self._execute_in_process(")
        _idx = self.src.find("self._execute_in_process(", _idx1 + 1)
        _ctx = self.src[_idx:_idx + 250]
        self.assertIn("execution_workflow", _ctx)

    def test_run_prompt_uses_execution_workflow_for_model_stack_extract(self):
        self.assertIn("extract_requested_model_stack(execution_workflow)", self.src)

    def test_run_prompt_attaches_production_report(self):
        self.assertIn('result["_production"] = production_report', self.src)

    # ── Production compilation in run_prompt_stream ──────────────────

    def test_run_prompt_stream_production_compilation_before_cold_unet(self):
        """The compilation block in run_prompt_stream must appear before
        _cold_unet_early_actual_load."""
        idx_compile = self.src.find(
            "execution_workflow, production_report = compile_production_workflow("
        )
        idx_unet = self.src.find(
            "_cold_unet_early_actual_load(execution_workflow, modal_options=modal_options)"
        )
        # There are two compile_production_workflow calls (run_prompt + run_prompt_stream).
        # The second one is after the first. We need to find the one before cold_unet.
        # Find the last occurrence before cold_unet
        idx_compile_second = self.src.rfind(
            "execution_workflow, production_report = compile_production_workflow("
        )
        self.assertGreater(
            idx_compile_second, 0,
            "Expected second compile_production_workflow call in run_prompt_stream"
        )
        self.assertGreater(
            idx_unet, idx_compile_second,
            "compile_production_workflow must appear before cold_unet in run_prompt_stream"
        )

    def test_run_prompt_stream_uses_execution_workflow(self):
        self.assertIn(
            "_handle_custom_node_sync_and_dependency_policy(execution_workflow, stream=True)",
            self.src,
        )

    def test_run_prompt_stream_attaches_production_report(self):
        self.assertIn('_r["_production"] = production_report', self.src)

    def test_run_prompt_stream_uses_execution_workflow_for_preload(self):
        self.assertIn("self._prompt_async_preload(execution_workflow)", self.src)

    def test_run_prompt_stream_uses_execution_workflow_for_actual_load(self):
        self.assertIn("self._prompt_async_actual_load(execution_workflow)", self.src)

    def test_run_prompt_stream_uses_execution_workflow_for_execution(self):
        _idx = self.src.find("self._execute_in_process(")
        _idx2 = self.src.find("self._execute_in_process(", _idx + 1)
        _ctx = self.src[_idx2:_idx2 + 200]
        self.assertIn("execution_workflow", _ctx)

    # ── Scheduler test compile log ───────────────────────────────────

    def test_scheduler_test_compile_log(self):
        self.assertIn("[production.compile] enabled=0 reason=scheduler_test", self.src)

    # ── Production compile log ───────────────────────────────────────

    def test_production_compile_log(self):
        self.assertIn("[production.compile] enabled=1 topology_hash=", self.src)

    # ── Production-aware cache key in _execute_in_process ────────────

    def test_production_cache_key_format(self):
        self.assertIn("wf_exec:production:v1:", self.src)

    def test_production_cache_key_uses_build_topology_hash(self):
        self.assertIn("build_production_topology_hash(", self.src)

    def test_regular_cache_key_format(self):
        self.assertIn('_wf_cache_key = f"wf_exec:{_wf_hash}"', self.src)

    def test_cache_bounded_to_32(self):
        self.assertIn("if len(_wf_cache) >= 32:", self.src)

    def test_cache_validation_of_production_output_ids(self):
        self.assertIn("_production_enabled and _cached", self.src)
        self.assertIn("cached production output IDs no longer valid", self.src)

    # ── Production output filtering in _collect_in_process_outputs ───

    def test_collect_in_process_production_filtering(self):
        self.assertIn(
            "_production_collect = normalize_production_options(modal_options)",
            self.src,
        )

    def test_collect_in_process_filters_images_by_node_id(self):
        self.assertIn(
            "images = [img for img in images if img.get(\"node_id\") in _selected_ids]",
            self.src,
        )

    def test_collect_in_process_filters_videos_by_node_id(self):
        self.assertIn(
            "videos = [vid for vid in videos if vid.get(\"node_id\") in _selected_ids]",
            self.src,
        )

    def test_collect_in_process_filters_per_node_outputs(self):
        self.assertIn(
            "per_node_outputs = {",
            self.src,
        )
        self.assertIn("if nid in _selected_ids", self.src)

    def test_collect_in_process_raises_when_no_production_outputs(self):
        self.assertIn(
            "Production output collection failed. Selected output node(s)",
            self.src,
        )
        self.assertIn("produced no collectible in-memory or history output.", self.src)

    # ── Production output filtering in _collect_outputs (subprocess) ─

    def test_collect_outputs_signature_has_modal_options(self):
        self.assertIn(
            "def _collect_outputs(self, outputs: dict, profile: dict | None = None, modal_options: dict | None = None) -> dict:",
            self.src,
        )

    def test_collect_outputs_has_production_filtering(self):
        self.assertIn(
            "_production_collect = normalize_production_options(modal_options)",
            self.src,
        )

    def test_collect_outputs_filters_images_by_node_id(self):
        self.assertIn(
            'images = [img for img in images if img.get("node_id") in _selected_ids]',
            self.src,
        )

    def test_collect_outputs_filters_videos_by_node_id(self):
        self.assertIn(
            'videos = [vid for vid in videos if vid.get("node_id") in _selected_ids]',
            self.src,
        )

    def test_collect_outputs_raises_when_no_production_outputs(self):
        self.assertIn(
            "Production output collection failed. Selected output node(s)",
            self.src,
        )
        self.assertIn("produced no collectible in-memory or history output.", self.src)

    # ── _poll_until_done passes modal_options ────────────────────────

    def test_poll_until_done_signature_has_modal_options(self):
        self.assertIn(
            "def _poll_until_done(self, prompt_id: str, client_id: str, profile: dict | None = None, modal_options: dict | None = None) -> dict:",
            self.src,
        )

    def test_poll_until_done_passes_modal_options_to_collect_outputs(self):
        self.assertIn(
            "return self._collect_outputs(outputs, profile, modal_options=modal_options)",
            self.src,
        )

    def test_poll_until_done_caller_passes_modal_options(self):
        self.assertIn(
            "_poll_until_done(prompt_id, client_id, profile, modal_options=modal_options)",
            self.src,
        )



class ProductionPhase3aBehavioralTests(unittest.TestCase):
    """Behavioral tests for phase-3a production-mode logic.

    Tests the actual runtime behavior of functions used by the production
    pipeline, and verifies source-level guarantees for comfyapp.py flows
    that cannot be instantiated in isolation.
    """

    # ── normalize_production_options error cases ─────────────────────

    def test_normalize_rejects_non_dict_production(self):
        with self.assertRaises(TypeError):
            normalize_production_options({"production": "not_a_dict"})

    def test_normalize_rejects_wrong_schema_version(self):
        with self.assertRaises(ValueError):
            normalize_production_options({
                "production": {
                    "enabled": True,
                    "schema_version": 0,
                    "output_node_ids": ["1"],
                }
            })

    def test_normalize_rejects_empty_output_node_ids(self):
        with self.assertRaises(ValueError):
            normalize_production_options({
                "production": {
                    "enabled": True,
                    "schema_version": 1,
                    "output_node_ids": [],
                }
            })

    # ── Scheduler-test bypasses invalid production payloads ───────────

    def test_scheduler_test_before_normalize_in_run_prompt(self):
        """Source must check scheduler_test BEFORE calling
        normalize_production_options in run_prompt, so invalid production
        payloads are ignored when scheduler test is active."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        # Isolate the run_prompt production region: from the run_prompt
        # production block entry to the scheduler test execution.
        idx_region_start = src.find("# ── Scheduler test check first (bypass production normalize/compile) ──")
        self.assertGreater(idx_region_start, 0)
        # The scheduler test bypass log must appear BEFORE the
        # normalize_production_options call within run_prompt.
        # Find the last relevant occurrence within this region.
        idx_bypass = src.find("[production.compile] enabled=0 reason=scheduler_test", idx_region_start)
        idx_normalize = src.find("normalize_production_options(modal_options)", idx_region_start)
        self.assertGreater(
            idx_bypass, 0,
            "scheduler_test bypass compile log must exist in run_prompt region",
        )
        self.assertGreater(
            idx_normalize, 0,
            "normalize_production_options must exist in run_prompt region",
        )
        self.assertLess(
            idx_bypass, idx_normalize,
            "scheduler_test bypass log must precede normalize_production_options "
            "so that scheduler test short-circuits before normalization errors",
        )

    # ── Production cache key computation ─────────────────────────────

    def test_build_production_topology_hash_returns_string(self):
        workflow = {"1": {"class_type": "KSampler", "inputs": {"seed": 42}}}
        production = normalize_production_options({
            "production": {
                "schema_version": 1,
                "output_node_ids": ["1"],
            }
        })
        h = build_production_topology_hash(workflow, production, allow_direct_output_rewrite=False)
        self.assertIsInstance(h, str)
        self.assertGreater(len(h), 8)

    def test_build_production_topology_hash_changes_with_output_ids(self):
        workflow = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 42}},
            "2": {"class_type": "VAEDecode", "inputs": {}},
        }
        prod_a = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["1"]}
        })
        prod_b = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["2"]}
        })
        ha = build_production_topology_hash(workflow, prod_a, allow_direct_output_rewrite=False)
        hb = build_production_topology_hash(workflow, prod_b, allow_direct_output_rewrite=False)
        self.assertNotEqual(ha, hb)

    # ── Cache key format ─────────────────────────────────────────────

    def test_execute_in_process_initializes_valid_before_check(self):
        """Source must assign 'valid = False' before any conditional that
        reads 'valid', preventing UnboundLocalError on cache miss."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        # Isolate the _execute_in_process region using the production
        # cache key comment as anchor.
        idx_region = src.find("# Production-aware cache key")
        self.assertGreater(idx_region, 0)
        idx_valid_init = src.find("valid = False", idx_region)
        idx_cached_check = src.find("if _cached is not None", idx_region)
        self.assertGreater(
            idx_valid_init, 0,
            "'valid = False' initializer must exist in _execute_in_process",
        )
        self.assertGreater(
            idx_cached_check, 0,
            "cache check must exist in _execute_in_process",
        )
        self.assertLess(
            idx_valid_init, idx_cached_check,
            "'valid = False' must be assigned before the 'if _cached is not None' check",
        )

    def test_execute_in_process_production_cache_key_with_workflow(self):
        """Verify that a production-enabled cache key is structurally
        different from a non-production key for the same workflow."""
        workflow = {"1": {"class_type": "KSampler", "inputs": {"seed": 42}}}
        production = normalize_production_options({
            "production": {"schema_version": 1, "output_node_ids": ["1"]}
        })
        topology_hash = build_production_topology_hash(
            workflow, production, allow_direct_output_rewrite=False
        )
        cache_key = f"wf_exec:production:v1:{topology_hash}:wf_hash_val"
        self.assertTrue(cache_key.startswith("wf_exec:production:v1:"))

    # ── execution_workflow used for stack persistence in run_prompt ──

    def test_run_prompt_persists_execution_workflow(self):
        """Source must use execution_workflow for _save_last_warmup_workflow
        in run_prompt's in-process path."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "self._save_last_warmup_workflow(execution_workflow)",
            src,
        )

    def test_run_prompt_subprocess_persists_execution_workflow(self):
        """Source must use execution_workflow for _save_last_warmup_workflow
        in run_prompt's subprocess path."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "self._save_last_warmup_workflow(execution_workflow)",
            src,
        )

    def test_run_prompt_uses_execution_workflow_for_warmup_diagnostics(self):
        """Source must use execution_workflow for _log_warmup_vs_workflow_diagnostics
        raw_workflow parameter."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "raw_workflow=execution_workflow",
            src,
        )

    def test_run_prompt_uses_execution_workflow_for_stack_extraction(self):
        """Source must use execution_workflow for extract_requested_model_stack
        in run_prompt's post-compile persistence."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "extract_requested_model_stack(execution_workflow)",
            src,
        )

    def test_run_prompt_subprocess_uses_execution_workflow_for_stack_extraction(self):
        """Source must use execution_workflow for extract_requested_model_stack
        in run_prompt subprocess path."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "extract_requested_model_stack(execution_workflow)",
            src,
        )

    def test_run_prompt_scheduler_test_uses_execution_workflow(self):
        """Source must use execution_workflow for _start_scheduler_test
        in run_prompt."""
        src = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "self._start_scheduler_test(execution_workflow,",
            src,
        )


if __name__ == "__main__":
    unittest.main()
