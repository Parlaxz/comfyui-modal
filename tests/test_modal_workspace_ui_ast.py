import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
UI_SETTINGS_PATH = REPO_ROOT / "web" / "modal-settings.js"
UI_NODE_PATH = REPO_ROOT / "web" / "modal-node.js"


class ModalWorkspaceUiAstTests(unittest.TestCase):
    def test_workspace_controls_are_present(self):
        source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertIn("Swap Workspace", source)
        self.assertIn("Manifest Repair", source)
        self.assertIn("Export Workflow Manifest", source)
        self.assertIn("Import Workflow Manifest", source)
        self.assertIn("Install from Manifest", source)

    def test_workspace_routes_are_called(self):
        source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertIn("MODAL_PREFIX}/workspaces", source)
        self.assertIn("MODAL_PREFIX}/workspaces/swap", source)
        self.assertIn("MODAL_PREFIX}/manifest/repair/scan", source)
        self.assertIn("MODAL_PREFIX}/manifest/repair/apply", source)
        self.assertIn("MODAL_PREFIX}/manifest/install", source)
        self.assertIn("MODAL_PREFIX}/workflow-manifest/export", source)
        self.assertIn("MODAL_PREFIX}/workflow-manifest/import", source)

    def test_swap_review_does_not_rewrite_body_with_innerhtml_append(self):
        source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("body.innerHTML +=", source)

    def test_swap_review_confirm_preserves_prompt_interrupt_approval(self):
        source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertIn("confirm_prompt_interrupt: !!data.confirm_prompt_interrupt", source)


class ModalProductionUiAstTests(unittest.TestCase):
    """Phase 2 production-mode UI source-level tests."""

    def test_simulate_production_checkbox_present(self):
        source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertIn("Simulate Production", source)

    def test_production_mode_enabled_persisted(self):
        source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertIn("production_mode_enabled", source)

    def test_production_summary_labels(self):
        source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertIn("Production plan", source)
        self.assertIn("Sampler previews: disabled", source)

    def test_context_menu_mark_output(self):
        source = UI_NODE_PATH.read_text(encoding="utf-8")
        self.assertIn("Mark as Production Output", source)
        self.assertIn("Unmark Production Output", source)

    def test_context_menu_bypass(self):
        source = UI_NODE_PATH.read_text(encoding="utf-8")
        self.assertIn("Bypass in Production", source)
        self.assertIn("Do Not Bypass in Production", source)

    def test_node_flags_in_properties(self):
        source = UI_NODE_PATH.read_text(encoding="utf-8")
        self.assertIn("comfymodal_production_output", source)
        self.assertIn("comfymodal_bypass_in_production", source)

    def test_node_badges(self):
        source = UI_NODE_PATH.read_text(encoding="utf-8")
        self.assertIn("PROD OUT", source)
        self.assertIn("PROD BYPASS", source)

    def test_production_payload_keys(self):
        source = UI_NODE_PATH.read_text(encoding="utf-8")
        payload_keys = [
            "schema_version",
            "output_node_ids",
            "bypass_node_ids",
            "disable_sampler_previews",
            "quiet_execution_logs",
            "progress_min_interval_ms",
            "strict_output_collection",
            "direct_output_sink",
            "metadata_mode",
        ]
        for key in payload_keys:
            with self.subTest(key=key):
                self.assertIn(key, source)

    def test_graph_to_prompt_patch(self):
        source = UI_NODE_PATH.read_text(encoding="utf-8")
        self.assertIn("graphToPrompt", source)
        self.assertIn("app.graphToPrompt =", source)

    def test_production_bypass_error_message(self):
        source = UI_NODE_PATH.read_text(encoding="utf-8")
        self.assertIn("Production bypass failed for node", source)
        self.assertIn("ComfyUI could not serialize this node as a native bypass", source)


if __name__ == "__main__":
    unittest.main()
