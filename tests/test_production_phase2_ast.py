import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "__init__.py"
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"


class ProductionPhase2InitPyAstTests(unittest.TestCase):
    """Source-level tests for __init__.py phase-2 production changes."""

    def test_normalize_production_options_imported(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("normalize_production_options", source)

    def test_compile_production_workflow_imported(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("compile_production_workflow", source)

    def test_modal_prompt_contains_production_compilation(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("production_options = normalize_production_options(modal_options_raw)", source)
        self.assertIn("compile_production_workflow", source)

    def test_modal_prompt_uses_execution_workflow_for_stack_extract(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("execution_workflow", source)
        self.assertIn("workflow_hash = prompt_sha256(execution_workflow)", source)
        self.assertIn("summarize_prompt_fields(execution_workflow)", source)
        self.assertIn("extract_model_stack(execution_workflow)", source)

    def test_modal_prompt_stores_production_report_in_extra_data(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("production_report", source)
        self.assertIn("execution_workflow", source)
        self.assertIn("copy.deepcopy", source)

    def test_execute_job_uses_execution_workflow(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("execution_workflow = extra_data.get", source)

    def test_execute_job_warmup_uses_execution_workflow(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        # The warmup profile preparation now delegates to shared helper
        self.assertIn("prepare_active_next_profile(", source)
        self.assertIn("execution_workflow", source)
        self.assertIn("prompt_hash", source)

    def test_execute_job_run_prompt_uses_execution_workflow(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("run_prompt_stream(\n            execution_workflow,", source)

    def test_execute_job_hash_uses_execution_workflow(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("prompt_sha256(execution_workflow)", source)

    def test_execute_job_validation_uses_execution_workflow(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("assert_valid_api_prompt_structure(execution_workflow)", source)
        self.assertIn("for _spec in execution_workflow.values():", source)

    def test_execute_job_input_collection_uses_execution_workflow(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("workflow_needs_local_input_files(execution_workflow)", source)
        self.assertIn("_collect_input_images(execution_workflow)", source)


class ProductionPhase2ComfyappPyAstTests(unittest.TestCase):
    """Source-level tests for comfyapp.py phase-2 production changes."""

    def test_production_workflow_in_local_sources(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("production_workflow", source)
        self.assertIn('"production_workflow",', source)


if __name__ == "__main__":
    unittest.main()
