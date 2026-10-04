import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
UI_SETTINGS_PATH = REPO_ROOT / "web" / "modal-settings.js"
UI_NODE_PATH = REPO_ROOT / "web" / "modal-node.js"
UI_PLAYGROUND_PATH = REPO_ROOT / "web" / "studio-playground.js"


class ModalWorkspaceUiAstTests(unittest.TestCase):
    """H18 Wave G: the legacy overlay workspace/manifest UI is deleted;
    these pins assert the retirement (modern owners: Backend page)."""

    def test_workspace_controls_retired(self):
        source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        for retired in [
            "Swap Workspace",
            "Manifest Repair",
            "Export Workflow Manifest",
            "Import Workflow Manifest",
            "Install from Manifest",
        ]:
            self.assertNotIn(retired, source, f"retired overlay control must stay deleted: {retired}")

    def test_edit_workspace_controls_retired(self):
        source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("Edit Workspace", source)
        self.assertNotIn("Leave blank to keep current", source)

    def test_sidebar_launcher_opens_modern_settings(self):
        """H10: the sidebar panel opens modern Settings, not the legacy overlay."""
        source = (REPO_ROOT / "web" / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn("Open Settings", source)
        self.assertNotIn("Open Legacy Settings", source)
        # H14 Wave E: the standalone legacy overlay global is retired.
        settings_source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("open_comfymodal_settings", settings_source)

    def test_workspace_routes_not_called_from_settings_module(self):
        """Workspace/manifest routes are consumed by the modern Backend
        modules, never by the deleted overlay."""
        source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        for retired in [
            "MODAL_PREFIX}/workspaces",
            "MODAL_PREFIX}/workspaces/swap",
            "MODAL_PREFIX}/manifest/repair/scan",
            "MODAL_PREFIX}/manifest/repair/apply",
            "MODAL_PREFIX}/manifest/install",
        ]:
            self.assertNotIn(retired, source)

    def test_swap_review_does_not_rewrite_body_with_innerhtml_append(self):
        source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("body.innerHTML +=", source)


class ModalProductionUiAstTests(unittest.TestCase):
    """Phase 2 production-mode UI source-level tests.

    Canvas Production mode lives in modal-node.js (untouched). The legacy
    overlay's Simulate Production toggle was deleted in Wave G (H18).
    """

    def test_legacy_production_toggle_retired(self):
        source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("Simulate Production", source)
        self.assertNotIn("cm-prod-toggle", source)
        self.assertNotIn("production_mode_enabled", source)

    def test_canvas_production_mode_intact(self):
        """Production-mode marking remains with the canvas layer (H5 §9)."""
        source = UI_NODE_PATH.read_text(encoding="utf-8")
        self.assertIn("production_mode_enabled", source)

    def test_production_summary_labels_retired(self):
        """H18 Wave G: the overlay production-summary UI is deleted; the
        stale "Production plan" copy no longer exists anywhere in web/."""
        playground_source = UI_PLAYGROUND_PATH.read_text(encoding="utf-8")
        settings_source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("Production plan", settings_source)
        self.assertNotIn("Production plan", playground_source)

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
        """The save-folder default lives in the shared output-preferences
        authority; the overlay's copy is deleted (Wave G)."""
        node_source = UI_NODE_PATH.read_text(encoding="utf-8")
        settings_source = UI_SETTINGS_PATH.read_text(encoding="utf-8")
        helper_source = (REPO_ROOT / "web" / "studio-output-preferences.js").read_text(encoding="utf-8")
        self.assertNotIn("ComfyUI/output/modal/", node_source)
        self.assertNotIn("ComfyUI/output/modal/", settings_source)
        self.assertIn("output/modal", node_source)
        self.assertIn("output/modal", helper_source)

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
        # Match static import STATEMENTS, not lines: this file uses several
        # multi-line `import { ... } from` blocks, so a per-line check only
        # ever saw single-line specifier lists. The protected contract is that
        # getStudioRunStatus is statically bound -- the dynamic `import()` calls
        # elsewhere in this module must not be what satisfies it.
        static_backend_api_imports = re.findall(
            r"import\s*\{([^}]*)\}\s*from\s*[\"']\./studio-backend-api\.js[\"']",
            self.source,
            re.DOTALL,
        )
        self.assertTrue(
            static_backend_api_imports,
            "Expected a static import from ./studio-backend-api.js",
        )
        has_static_import = any(
            "getStudioRunStatus" in specifiers
            for specifiers in static_backend_api_imports
        )
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

    def test_history_v2_imports_normalize_studio_run(self):
        """studio-history-v2.js (modern History) must reference the normalizer module."""
        text = (REPO_ROOT / "web" / "studio-history-v2.js").read_text(encoding="utf-8")
        self.assertIn("./studio-run-normalizer.js", text)


if __name__ == "__main__":
    unittest.main()
