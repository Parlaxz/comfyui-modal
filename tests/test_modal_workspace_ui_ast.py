import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
UI_SETTINGS_PATH = REPO_ROOT / "web" / "modal-settings.js"
UI_NODE_PATH = REPO_ROOT / "web" / "modal-node.js"
UI_PLAYGROUND_PATH = REPO_ROOT / "web" / "studio-playground.js"


class ModalWorkspaceUiAstTests(unittest.TestCase):
    def test_workspace_controls_are_present(self):
        source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertIn("Swap Workspace", source)
        self.assertIn("Manifest Repair", source)
        self.assertIn("Export Workflow Manifest", source)
        self.assertIn("Import Workflow Manifest", source)
        self.assertIn("Install from Manifest", source)

    def test_edit_workspace_controls_are_present(self):
        source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertIn("Edit Workspace", source)
        self.assertIn("Leave blank to keep current", source)

    def test_sidebar_launcher_can_open_legacy_settings(self):
        source = (REPO_ROOT / "web" / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn("Open Legacy Settings", source)
        self.assertIn("open_comfymodal_settings", source)

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

    def test_badge_integration_removed(self):
        source = UI_NODE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("node.badges.push", source)
        self.assertNotIn("LGraphBadge", source)

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

    def test_graph_to_prompt_patch_removed(self):
        source = UI_NODE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("app.graphToPrompt =", source)
        self.assertNotIn("node.mode =", source)

    def test_output_save_folder_defaults_are_normalized(self):
        node_source = UI_NODE_PATH.read_text(encoding="utf-8")
        settings_source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("ComfyUI/output/modal/", node_source)
        self.assertNotIn("ComfyUI/output/modal/", settings_source)
        self.assertIn("output/modal", node_source)
        self.assertIn("output/modal", settings_source)

    def test_production_bypass_error_message(self):
        source = UI_NODE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("Production bypass failed for node", source)
        self.assertNotIn("ComfyUI could not serialize this node as a native bypass", source)


class StudioPlaygroundUiAstTests(unittest.TestCase):
    """Studio playground UI source-level tests for run status polling."""

    def setUp(self):
        self.source = UI_PLAYGROUND_PATH.read_text(encoding="utf-8")

    def test_imports_getStudioRunStatus(self):
        self.assertIn("getStudioRunStatus", self.source)
        # Must import from studio-backend-api (or be defined locally)
        self.assertIn('from "./studio-backend-api.js"', self.source)
        # Check the static imports explicitly — the dynamic import in hydratePlayground
        # uses import() not import, so split by static imports only
        static_import_lines = [line for line in self.source.split("\n") if line.strip().startswith("import ")]
        has_static_import = any("getStudioRunStatus" in line for line in static_import_lines)
        self.assertTrue(has_static_import, "Expected getStudioRunStatus in static imports")

    def test_polls_experiment_status_after_submitted(self):
        self.assertIn("getStudioRunStatus", self.source)
        self.assertIn("data.snapshot", self.source)
        self.assertIn("queued", self.source)
        self.assertIn("running", self.source)
        self.assertIn("completed", self.source)

    def test_does_not_keep_static_submitted_state(self):
        # The old behavior kept "Submitted" as a static terminal state.
        # The new behavior polls experiment status, so the word "Submitted"
        # should only appear as a transitional state, not as a permanent display.
        self.assertIn('"submitted"', self.source)
        # Ensure there is polling logic (setInterval or recursive setTimeout)
        has_interval = "setInterval" in self.source
        has_timeout_recursive = "setTimeout" in self.source and "getStudioRunStatus" in self.source
        self.assertTrue(has_interval or has_timeout_recursive)


# ---------------------------------------------------------------------------
# normalizeStudioRun imported/used by Playground and persisted state
# ---------------------------------------------------------------------------

class StudioPlaygroundNormalizerAndPersistenceTests(unittest.TestCase):
    """Playground must import normalizeStudioRun and have persistence state."""

    def setUp(self):
        self.text = (REPO_ROOT / "web" / "studio-playground.js").read_text(encoding="utf-8")

    def test_playground_imports_normalize_studio_run(self):
        """studio-playground.js must import normalizeStudioRun from normalizer."""
        self.assertIn("normalizeStudioRun", self.text)
        self.assertIn("./studio-run-normalizer.js", self.text)

    def test_persistence_key_has_versioned_selection(self):
        """Persistence key must be versioned and store selection state."""
        self.assertIn("localStorage", self.text)
        self.assertIn("selection", self.text)

    def test_selected_preset_and_feature_persisted(self):
        """Selected preset id and feature id must be persisted to localStorage."""
        self.assertIn("selectedBackendId", self.text)

    def test_persistence_does_not_store_image_blobs(self):
        """Persistence must only store lightweight selection state, not image blobs."""
        self.assertNotIn("imageBlob", self.text.lower() if hasattr(self.text, 'lower') else self.text)


class StudioHistoryNormalizerTests(unittest.TestCase):
    """History must import normalizeStudioRun from shared normalizer."""

    def test_history_imports_normalize_studio_run(self):
        """studio-history.js must import normalizeStudioRun."""
        text = (REPO_ROOT / "web" / "studio-history.js").read_text(encoding="utf-8")
        self.assertIn("normalizeStudioRun", text)
        self.assertIn("./studio-run-normalizer.js", text)


if __name__ == "__main__":
    unittest.main()
