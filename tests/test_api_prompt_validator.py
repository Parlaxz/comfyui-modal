"""Tests for api_prompt_validator.py (PART 1) and failure_summary.py (PART 8)."""

import unittest
import json
from api_prompt_validator import (
    assert_valid_api_prompt_structure,
    validate_api_prompt_structure,
    validate_class_types_exist,
)
from failure_summary import FailureSummary


VALID_PROMPT = {
    "3": {"class_type": "KSampler", "inputs": {"seed": 7, "steps": 20}},
    "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux.safetensors"}},
    "11": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors"}},
}

MISSING_CLASS_TYPE_PROMPT = {
    "454": {"inputs": {}},
    "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux.safetensors"}},
}

MISSING_INPUTS_PROMPT = {
    "5": {"class_type": "KSampler"},
    "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux.safetensors"}},
}

EMPTY_CLASS_TYPE_PROMPT = {
    "7": {"class_type": "", "inputs": {}},
    "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux.safetensors"}},
}

NON_DICT_NODE_VALUE_PROMPT = {
    "1": "just a string",
    "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux.safetensors"}},
}

UI_ONLY_CLASS_TYPE_PROMPT = {
    "8": {"class_type": "Reroute", "inputs": {}},
    "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux.safetensors"}},
}

NOTE_NODE_PROMPT = {
    "9": {"class_type": "Note", "inputs": {}},
    "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux.safetensors"}},
}

EMPTY_PROMPT = {}

NON_DICT_PROMPT = [1, 2, 3]


class ApiPromptValidatorTests(unittest.TestCase):
    """PART 1: Bridge-side API prompt preflight validation."""

    def test_valid_prompt_returns_no_errors(self):
        errors = validate_api_prompt_structure(VALID_PROMPT)
        self.assertEqual(errors, [])

    def test_node_missing_class_type(self):
        errors = validate_api_prompt_structure(MISSING_CLASS_TYPE_PROMPT)
        self.assertEqual(len(errors), 1)
        self.assertIn("class_type", errors[0].lower())
        self.assertIn("454", errors[0])

    def test_node_missing_inputs(self):
        errors = validate_api_prompt_structure(MISSING_INPUTS_PROMPT)
        self.assertEqual(len(errors), 1)
        self.assertIn("inputs", errors[0].lower())
        self.assertIn("5", errors[0])

    def test_empty_class_type(self):
        errors = validate_api_prompt_structure(EMPTY_CLASS_TYPE_PROMPT)
        self.assertEqual(len(errors), 1)
        self.assertIn("empty", errors[0].lower())

    def test_non_dict_node_value(self):
        errors = validate_api_prompt_structure(NON_DICT_NODE_VALUE_PROMPT)
        self.assertEqual(len(errors), 1)

    def test_reroute_node_detected(self):
        errors = validate_api_prompt_structure(UI_ONLY_CLASS_TYPE_PROMPT)
        # Valid API prompt - Reroute is a valid class_type in API format
        self.assertEqual(len(errors), 0)

    def test_note_node_detected(self):
        errors = validate_api_prompt_structure(NOTE_NODE_PROMPT)
        # Valid API prompt - Note is a valid class_type in API format
        self.assertEqual(len(errors), 0)

    def test_ui_workflow_json_rejected(self):
        """UI workflow JSON (nodes/links at top level) must be rejected."""
        ui_workflow = {
            "nodes": [{"id": 1, "type": "KSampler", "pos": [0, 0]}],
            "links": [],
        }
        errors = validate_api_prompt_structure(ui_workflow)
        self.assertGreater(len(errors), 0)
        self.assertIn("UI workflow JSON", " ".join(errors))

    def test_ui_node_with_pos_no_class_type_rejected(self):
        """Node with pos/size but no class_type is detected as UI node."""
        prompt = {"1": {"pos": [0, 0], "size": [200, 100]}}
        errors = validate_api_prompt_structure(prompt)
        self.assertGreater(len(errors), 0)
        combined = " ".join(errors).lower()
        self.assertIn("pos", combined)
        self.assertIn("class_type", combined)

    def test_assert_valid_api_prompt_raises_on_invalid(self):
        with self.assertRaises(RuntimeError) as ctx:
            assert_valid_api_prompt_structure({"454": {"inputs": {}}})
        self.assertIn("454", str(ctx.exception))

    def test_assert_valid_api_prompt_passes_on_valid(self):
        assert_valid_api_prompt_structure(VALID_PROMPT)  # should not raise

    def test_empty_prompt_returns_error(self):
        errors = validate_api_prompt_structure(EMPTY_PROMPT)
        self.assertGreater(len(errors), 0)

    def test_non_dict_prompt_returns_error(self):
        errors = validate_api_prompt_structure(NON_DICT_PROMPT)
        self.assertGreater(len(errors), 0)
        self.assertIn("dict", errors[0].lower())

    def test_failing_node_454_case(self):
        """Regression: the exact failure pattern from the bug report."""
        payload = {"454": {"inputs": {}}}
        errors = validate_api_prompt_structure(payload)
        self.assertEqual(len(errors), 1)
        self.assertIn("454", errors[0])
        self.assertIn("class_type", errors[0])

    def test_failing_node_454_with_valid_nodes(self):
        """Corrupted prompt with both good and bad nodes."""
        payload = {
            "3": {"class_type": "KSampler", "inputs": {"seed": 7}},
            "454": {"inputs": {}},
        }
        errors = validate_api_prompt_structure(payload)
        self.assertEqual(len(errors), 1)
        self.assertIn("454", errors[0])

    def test_validates_class_types_against_available_set(self):
        available = {"KSampler", "UNETLoader", "CLIPLoader"}
        missing = validate_class_types_exist(VALID_PROMPT, available)
        self.assertEqual(missing, [])

    def test_detects_missing_class_types(self):
        available = {"KSampler", "CLIPLoader"}
        missing = validate_class_types_exist(VALID_PROMPT, available)
        self.assertIn("UNETLoader", missing)


class FailureSummaryTests(unittest.TestCase):
    """PART 8: Structured failure summaries."""

    def test_preflight_summary_format(self):
        summary = FailureSummary(phase="preflight")
        summary.fatal_error = "node 454 missing class_type"
        summary.modal_invoked = False
        output = summary.format()
        self.assertIn("run_failed_phase=preflight", output)
        self.assertIn("fatal_error=", output)
        self.assertIn("modal_invoked=0", output)

    def test_execution_summary_with_wasted_time(self):
        summary = FailureSummary(phase="validation")
        summary.fatal_error = "node 454 missing class_type"
        summary.modal_invoked = True
        summary.wasted_restore_ms = 132881
        summary.wasted_requirements_ms = 115658
        output = summary.format()
        self.assertIn("wasted_restore_ms", output)
        self.assertIn("132881", output)
        self.assertIn("115658", output)

    def test_recommendation_included(self):
        summary = FailureSummary(phase="preflight")
        summary.fatal_error = "bad node"
        summary.recommendation = "Fix the workflow"
        output = summary.format()
        self.assertIn("recommendation=", output)
        self.assertIn("Fix the workflow", output)


if __name__ == "__main__":
    unittest.main()
