"""Structural/source tests for the Studio Backend redesign.

Tests cover:
- Backend page structure (tabs, sections)
- Take Snapshot button
- Snapshot data model shape
- Backend Preset data model shape
- Compatible features chip grid
- Settings page content rows
- Legacy links preservation
- Non-runnable status labels
- Top nav order
- No feature dropdown
- Feature tab switching
- Experiment axis editor
- History safe rendering
- Legacy routing
"""

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web"


class _JsModule:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.text = path.read_text(encoding="utf-8") if path.exists() else ""

    def contains(self, s: str) -> bool:
        return s in self.text

    def has_export(self, name: str) -> bool:
        return bool(
            re.search(
                rf"export\s+(?:(?:async\s+)?function|const|class|let|var)\s+{re.escape(name)}\b",
                self.text,
            )
        )


# ---------------------------------------------------------------------------
# Studio Backend page — tabs and sections
# ---------------------------------------------------------------------------

class StudioBackendTabTests(unittest.TestCase):
    """Backend page must have Snapshots and Backend Presets tabs."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-backend.js")

    def test_backend_has_snapshots_tab(self):
        """Backend page must reference Snapshots as a section/tab."""
        self.assertIn("snapshots", self.m.text.lower())

    def test_backend_has_presets_tab(self):
        """Backend page must reference Backend Presets as a section/tab."""
        self.assertIn("presets", self.m.text.lower())

    def test_backend_has_tab_switching(self):
        """Backend page must have a tab switching mechanism."""
        self.assertIn("switchTab", self.m.text) or self.assertIn("activeTab", self.m.text)

    def test_backend_tab_class_names(self):
        """Backend tabs should use comfymodal-studio-backend-tab classes."""
        self.assertIn("comfymodal-studio-backend-tab", self.m.text)


class StudioSnapshotsTests(unittest.TestCase):
    """Snapshot data model and list/detail rendering."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-backend-snapshots.js")

    def test_take_snapshot_button_exists(self):
        """Backend page must have a 'Take Snapshot' button."""
        self.assertIn("Take Snapshot", self.m.text)

    def test_snapshot_api_calls_present(self):
        """Backend page must have snapshot CRUD API calls in the API module."""
        text = (WEB / "studio-backend-api.js").read_text(encoding="utf-8")
        self.assertIn("studio/snapshots", text)

    def test_snapshot_list_renderer_exists(self):
        """Backend page must have a snapshot list renderer function."""
        self.assertIn("renderSnapshotsList", self.m.text)

    def test_snapshot_detail_renderer_exists(self):
        """Backend page must have a snapshot detail renderer function."""
        self.assertIn("renderSnapshotDetail", self.m.text)

    def test_snapshot_has_take_snapshot_function(self):
        """Capture logic lives in studio-backend-capture.js."""
        text = (WEB / "studio-backend-capture.js").read_text(encoding="utf-8")
        self.assertIn("takeSnapshotOfCurrentGraph", text)

    def test_snapshot_has_status_badge(self):
        """Snapshot detail must use status badges for runnable/needs-bindings."""
        text = (WEB / "studio-ui.js").read_text(encoding="utf-8")
        self.assertIn("status-badge", text)

    def test_snapshot_non_runnable_status(self):
        """Snapshot must show 'Needs bindings' or 'Needs API prompt' status for non-runnable."""
        self.assertTrue(
            "Needs bindings" in self.m.text or "Needs API prompt" in self.m.text
        )


class StudioPresetsTests(unittest.TestCase):
    """Backend Preset data model and list/detail rendering."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-backend-presets.js")

    def test_preset_has_new_preset_button(self):
        """Presets page must have a 'New Preset' button."""
        self.assertIn("New Preset", self.m.text)

    def test_preset_api_calls_present(self):
        """Backend page must have preset CRUD API calls in the API module."""
        text = (WEB / "studio-backend-api.js").read_text(encoding="utf-8")
        self.assertIn("studio/presets", text)

    def test_preset_list_renderer_exists(self):
        """Backend page must have a preset list renderer function."""
        self.assertIn("renderPresetsList", self.m.text)

    def test_preset_detail_renderer_exists(self):
        """Backend page must have a preset detail renderer function."""
        self.assertIn("renderPresetDetail", self.m.text)

    def test_preset_has_snapshot_id_field(self):
        """Preset detail must reference snapshotId for linking."""
        self.assertIn("snapshotId", self.m.text)

    def test_preset_has_form_renderer(self):
        """Backend page must have a preset form renderer for new presets."""
        self.assertIn("renderPresetForm", self.m.text)


class CompatibleFeaturesChipGridTests(unittest.TestCase):
    """Compatible features must use compact grouped chip/grid control."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-backend.js")

    def test_features_chip_grid_function_exists(self):
        """Backend page must have a renderFeaturesChipGrid function."""
        self.assertIn("renderFeaturesChipGrid", self.m.text)

    def test_features_chip_grid_has_txt2img(self):
        """Chip grid must include Txt2Img."""
        self.assertIn("Txt2Img", self.m.text)

    def test_features_chip_grid_has_object_remove(self):
        """Chip grid must include Object Remove."""
        self.assertIn("Object Remove", self.m.text)

    def test_features_chip_grid_has_object_replace(self):
        """Chip grid must include Object Replace."""
        self.assertIn("Object Replace", self.m.text)

    def test_features_chip_grid_class_exists(self):
        """Chip grid must use comfymodal-studio-features-chip-grid class."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn("comfymodal-studio-features-chip-grid", text)

    def test_features_chip_class_exists(self):
        """Features chip must use comfymodal-studio-feature-chip class."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn("comfymodal-studio-feature-chip", text)

    def test_features_chip_uses_semantic_button(self):
        """Feature chips must be semantic toggle buttons, not div-based state."""
        self.assertIn('button", {', self.m.text)
        self.assertIn('type: "button"', self.m.text)
        self.assertIn('aria-pressed', self.m.text)

    def test_features_chip_grid_uses_set_for_state(self):
        """Chip grid must use a Set in closure, not an array, for state tracking."""
        self.assertIn("new Set(", self.m.text)
        self.assertIn("selectedSet", self.m.text)
        self.assertIn("syncChip", self.m.text)

    def test_features_chip_grid_does_not_query_dom_for_state(self):
        """Click handler must not query DOM to reconstruct selected features."""
        self.assertNotIn("grid.querySelectorAll", self.m.text)


class BackendModuleSplitTests(unittest.TestCase):
    """Backend page logic should be split into focused modules."""

    def test_backend_page_imports_api_module(self):
        text = (WEB / "studio-backend.js").read_text(encoding="utf-8")
        self.assertIn("./studio-backend-api.js", text)

    def test_backend_page_imports_capture_module(self):
        text = (WEB / "studio-backend.js").read_text(encoding="utf-8")
        self.assertIn("./studio-backend-capture.js", text)

    def test_backend_page_imports_snapshots_module(self):
        text = (WEB / "studio-backend.js").read_text(encoding="utf-8")
        self.assertIn("./studio-backend-snapshots.js", text)

    def test_backend_page_imports_presets_module(self):
        text = (WEB / "studio-backend.js").read_text(encoding="utf-8")
        self.assertIn("./studio-backend-presets.js", text)

    def test_backend_page_imports_shared_ui_module(self):
        text = (WEB / "studio-backend.js").read_text(encoding="utf-8")
        self.assertIn("./studio-ui.js", text)

    def test_backend_page_no_longer_contains_capture_business_logic(self):
        text = (WEB / "studio-backend.js").read_text(encoding="utf-8")
        self.assertNotIn("takeSnapshotOfCurrentGraph", text)


class PresetOnlySelectorTests(unittest.TestCase):
    """Playground and Experiment must consume presets-only runtime selectors."""

    def test_playground_uses_preset_runtime_helper(self):
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertIn("getRuntimePresets", text)
        self.assertNotIn("getBackends(", text)

    def test_experiment_uses_preset_runtime_helper(self):
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertIn("getRuntimePresets", text)
        self.assertNotIn("getBackends(", text)


class BackendSelectorApiBaseTests(unittest.TestCase):
    """Backend selector must derive apiBase from context, not hardcode it."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-playground.js").read_text(encoding="utf-8")

    def test_backend_selector_receives_context(self):
        """renderControlPanel must pass context to renderBackendSelector."""
        self.assertIn("renderBackendSelector(state, actions, context)", self.text)

    def test_backend_selector_signature_accepts_context(self):
        """renderBackendSelector must accept a context parameter."""
        self.assertIn("function renderBackendSelector(state, actions, context) {", self.text)

    def test_backend_selector_derives_api_base_from_context(self):
        """renderBackendSelector must use context.apiBase with fallback."""
        self.assertIn("context.apiBase", self.text)
        self.assertNotIn('const apiBase = "/comfymodal"', self.text)


# ---------------------------------------------------------------------------
# Snapshot data model shape
# ---------------------------------------------------------------------------

class SnapshotDataModelTests(unittest.TestCase):
    """Snapshot object must include all required fields."""

    def test_snapshot_routes_exist_in_backend(self):
        """__init__.py must have snapshot route registrations."""
        text = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("/comfymodal/studio/snapshots", text)

    def test_snapshot_fields_in_backend(self):
        """Backend snapshot model must include all required fields."""
        text = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8")
        # Core fields
        for field in ["id", "name", "description", "createdAt", "updatedAt",
                      "compatibleFeatures", "graphJson", "apiPromptJson",
                      "nodeBindings", "outputNodeId", "modelSummary",
                      "source", "archived", "disabledReason"]:
            self.assertIn(f'"{field}"', text, f"Snapshot model missing field: {field}")

    def test_preset_fields_in_backend(self):
        """Backend preset model must include all required fields."""
        text = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8")
        for field in ["id", "label", "description", "snapshotId",
                      "compatibleFeatures", "defaults", "sourceType",
                      "sourceId", "disabledReason", "archived"]:
            self.assertIn(f'"{field}"', text, f"Preset model missing field: {field}")

    def test_known_feature_ids_defined(self):
        """Backend must have _KNOWN_FEATURE_IDS validation."""
        text = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("_KNOWN_FEATURE_IDS", text)
        self.assertIn("txt2img", text)
        self.assertIn("object_remove", text)
        self.assertIn("object_replace", text)

    def test_snapshot_validation_functions(self):
        """Backend must have validation/normalization functions."""
        text = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("_normalize_label", text)
        self.assertIn("_sanitize_description", text)
        self.assertIn("_validate_feature_ids", text)

    def test_snapshot_persistence_paths(self):
        """Backend must define snapshot and preset persistence paths."""
        text = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("_STUDIO_SNAPSHOTS_PATH", text)
        self.assertIn("_STUDIO_PRESETS_PATH", text)

    def test_snapshot_deduplicate_route(self):
        """Backend must have snapshot duplicate route."""
        text = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("snapshots/{snapshot_id}/duplicate", text)

    def test_preset_duplicate_route(self):
        """Backend must have preset duplicate route."""
        text = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("presets/{preset_id}/duplicate", text)


# ---------------------------------------------------------------------------
# Settings page — content rows and sections
# ---------------------------------------------------------------------------

class SettingsContentTests(unittest.TestCase):
    """Settings page must have real content rows, not just headings."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-settings.js").read_text(encoding="utf-8")

    def test_settings_studio_section_default_page(self):
        """Studio section must display 'Default page: Playground'."""
        self.assertIn("Default page", self.text)

    def test_settings_studio_topnav_pages(self):
        """Studio section must display top nav pages."""
        self.assertIn("Top nav pages", self.text)
        self.assertIn("Playground | History | Backend | Settings", self.text)

    def test_settings_studio_theme(self):
        """Studio section must display theme info."""
        self.assertIn("Nexus-inspired", self.text)

    def test_settings_studio_modal_size(self):
        """Studio section must display modal size."""
        self.assertIn("Modal size", self.text)

    def test_settings_studio_reset_button(self):
        """Studio section must have a reset UI preferences button."""
        self.assertIn("Reset UI preferences", self.text)

    def test_settings_backends_section(self):
        """Settings must have Backends/Presets section with stats."""
        self.assertIn("Backends / Presets", self.text)
        self.assertIn("Open Backend tab", self.text)

    def test_settings_runtime_section(self):
        """Settings must have Modal/Runtime section with deploy/token/gpu info."""
        self.assertIn("Modal / Runtime", self.text)
        self.assertIn("Deploy state", self.text)
        self.assertIn("Modal token", self.text)
        self.assertIn("GPU", self.text)

    def test_settings_runtime_legacy_link(self):
        """Runtime section must link to Legacy Settings."""
        self.assertIn("Open Legacy Settings", self.text)

    def test_settings_features_section(self):
        """Settings must have Features section with statuses."""
        self.assertIn("Txt2Img", self.text)
        self.assertIn("Enabled", self.text)
        self.assertIn("Object Remove", self.text)
        self.assertIn("Future: image-edit tooling", self.text)
        self.assertIn("Object Replace", self.text)

    def test_settings_legacy_section(self):
        """Settings must have Legacy section with links."""
        self.assertIn("Legacy Dashboard", self.text)
        self.assertIn("Legacy Setup", self.text)
        self.assertIn("Legacy Profiles", self.text)
        self.assertIn("Legacy Results", self.text)
        self.assertIn("Legacy History", self.text)
        self.assertIn("Legacy Settings", self.text)

    def test_settings_row_class(self):
        """Settings must use comfymodal-studio-settings-row class."""
        style_text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn("comfymodal-studio-settings-row", style_text)

    def test_settings_stat_card_class(self):
        """Settings must use comfymodal-studio-stat-card class."""
        style_text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn("comfymodal-studio-stat-card", style_text)


class SettingsCountsTests(unittest.TestCase):
    """Settings must show backend/preset/snapshot counts."""

    def test_settings_counts_referenced(self):
        """Settings must reference snapshots, presets, and backends for counts."""
        text = (WEB / "studio-settings.js").read_text(encoding="utf-8")
        self.assertIn("snapshots", text)
        self.assertIn("runnable", text)
        self.assertIn("presets", text)
        self.assertIn("need binding", text)


# ---------------------------------------------------------------------------
# Modal scrolling/layout
# ---------------------------------------------------------------------------

class ScrollingLayoutTests(unittest.TestCase):
    """Modal scrolling and layout ownership fixes."""

    def test_body_overflow_hidden(self):
        """Body must be overflow:hidden when modal is open."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn("overflow: hidden", text)

    def test_modal_overflow_hidden(self):
        """Modal must have overflow:hidden to prevent scroll."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn(".comfymodal-studio-modal", text)
        self.assertIn("overflow: hidden", text)

    def test_pagecontainer_scroll(self):
        """Page container must scroll and not be a scroll trap."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn("overflow-y: auto", text)

    def test_playground_internal_scroll(self):
        """Playground containers must scroll internally."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn("comfymodal-studio-control-panel", text)
        self.assertIn("overflow-y: auto", text)

    def test_modal_body_flex(self):
        """Studio body must be a flex container with overflow hidden."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn(".comfymodal-studio-body", text)


# ---------------------------------------------------------------------------
# Top nav and page structure
# ---------------------------------------------------------------------------

class TopNavStructureTests(unittest.TestCase):
    """Top nav order and structure."""

    def test_nav_order_playground_history_backend_settings(self):
        """Top nav must be Playground | History | Backend | Settings in that order."""
        text = (WEB / "studio-shell.js").read_text(encoding="utf-8")
        pages_start = text.find("PAGES = {")
        pages_block = text[pages_start:pages_start + 800]
        playground_pos = pages_block.find("playground")
        history_pos = pages_block.find("history")
        backend_pos = pages_block.find("backend")
        settings_pos = pages_block.find("settings")
        self.assertGreater(history_pos, playground_pos)
        self.assertGreater(backend_pos, history_pos)
        self.assertGreater(settings_pos, backend_pos)

    def test_no_feature_dropdown(self):
        """Must not have feature dropdown in control panel."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        has_feature_dropdown = bool(
            re.search(r'renderControlGroup\("Feature",\s*renderFeatureSelector', text)
        )
        self.assertFalse(has_feature_dropdown)

    def test_feature_tabs_in_workspace(self):
        """Feature tabs must be in the workspace, not control panel."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertIn("feature-tabs", text)
        self.assertIn("feature-tab", text)

    def test_feature_tab_switching(self):
        """Feature tabs must have onclick handlers that switch features."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertIn("featureId", text)
        self.assertIn("feature-tab", text)


# ---------------------------------------------------------------------------
# Experiment mode axis editor
# ---------------------------------------------------------------------------

class AxisEditorTests(unittest.TestCase):
    """Experiment axis editor behavior."""

    def test_axis_editor_present(self):
        """Experiment mode must have axis editor."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertIn("renderAxisEditor", text)

    def test_axis_checkboxes_attached(self):
        """Experiment-eligible controls must gain axis checkboxes."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertIn("axis-checkbox", text)

    def test_axis_editor_for_textarea(self):
        """Axis editor must support textarea for prompt variants."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertIn("textarea", text)


# ---------------------------------------------------------------------------
# History safe rendering
# ---------------------------------------------------------------------------

class HistorySafeRenderingTests(unittest.TestCase):
    """History must use safe DOM rendering, no innerHTML."""

    def test_history_no_inner_html(self):
        """History must not use template literal innerHTML for run data."""
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        has_dangerous = ('innerHTML = `' in text or 'innerHTML += `' in text)
        self.assertFalse(has_dangerous)

    def test_history_uses_create_element(self):
        """History must use createElement for run data cards."""
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        self.assertIn("createElement", text)

    def test_history_failed_state(self):
        """History must show error state on failure."""
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        self.assertIn("Failed", text)


# ---------------------------------------------------------------------------
# Legacy routing
# ---------------------------------------------------------------------------

class LegacyRoutingTests(unittest.TestCase):
    """open_testing_modal must route correctly to legacy tabs."""

    def test_open_testing_modal_routes_setup(self):
        """open_testing_modal('setup') must navigate to Settings > Legacy Setup."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn("activeLegacyTab", text)
        self.assertIn("setup", text)

    def test_open_testing_modal_routes_profiles(self):
        """open_testing_modal('profiles') must navigate to Settings > Legacy Profiles."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn("profiles", text)

    def test_open_testing_modal_routes_results(self):
        """open_testing_modal('results') must navigate to Settings > Legacy Results."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn("results", text)

    def test_legacy_modules_referenced(self):
        """Legacy modules must still be reachable from settings."""
        text = (WEB / "studio-settings.js").read_text(encoding="utf-8")
        self.assertIn("mountLegacyTab", text)


# ---------------------------------------------------------------------------
# Preset Wizard structural tests
# ---------------------------------------------------------------------------

class PresetWizardModuleTests(unittest.TestCase):
    """Preset wizard module must exist and export required symbols."""

    def test_wizard_module_exists(self):
        """web/studio-preset-wizard.js must exist."""
        self.assertTrue(
            (WEB / "studio-preset-wizard.js").exists(),
            "studio-preset-wizard.js missing",
        )

    def test_wizard_exports_open_close(self):
        """Wizard must export openPresetWizard and closePresetWizard."""
        text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")
        self.assertIn("export function openPresetWizard", text)
        self.assertIn("export function closePresetWizard", text)

    def test_wizard_has_feature_definitions(self):
        """Wizard must define features with required bindings."""
        text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")
        self.assertIn("txt2img", text)
        self.assertIn("object_remove", text)
        self.assertIn("object_replace", text)

    def test_wizard_bindings_defined(self):
        """Wizard must define required bindings per feature."""
        text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")
        # txt2img
        self.assertIn('"prompt"', text)
        self.assertIn('"output"', text)
        # object_remove
        self.assertIn('"source_image"', text)
        self.assertIn('"mask"', text)
        self.assertIn('"instruction"', text)
        # object_replace
        self.assertIn('"replacement_prompt"', text)

    def test_wizard_calls_capture_and_api(self):
        """Wizard must import captureCurrentComfyGraph and createSnapshot/createPreset."""
        text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")
        self.assertIn("captureCurrentComfyGraph", text)
        self.assertIn("createSnapshot", text)
        self.assertIn("createPreset", text)

    def test_wizard_imports_graph_binding(self):
        """Wizard must import from studio-graph-binding.js."""
        text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")
        self.assertIn("./studio-graph-binding.js", text)
        self.assertIn("beginGraphBindingCapture", text)

    def test_wizard_has_steps(self):
        """Wizard must have feature steps."""
        text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")
        self.assertIn('"features"', text)
        self.assertIn('"bindings"', text)
        self.assertIn('"details"', text)

    def test_wizard_no_client_status_in_save_payload(self):
        """Wizard must NOT send client-owned status or disabledReason in save payloads."""
        text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")
        # The snapshotPayload and presetPayload should not include status or disabledReason
        # Check snapshot payload keys
        self.assertNotIn('"status"', text)
        self.assertNotIn('"disabledReason"', text)


class GraphBindingModuleTests(unittest.TestCase):
    """Graph binding module must exist and export required symbols."""

    def test_graph_binding_module_exists(self):
        """web/studio-graph-binding.js must exist."""
        self.assertTrue(
            (WEB / "studio-graph-binding.js").exists(),
            "studio-graph-binding.js missing",
        )

    def test_graph_binding_exports(self):
        """Module must export key functions."""
        text = (WEB / "studio-graph-binding.js").read_text(encoding="utf-8")
        self.assertIn("export function getComfyGraphContext", text)
        self.assertIn("export function beginGraphBindingCapture", text)
        self.assertIn("export function cancelGraphBinding", text)
        self.assertIn("export function extractNodeCandidates", text)
        self.assertIn("export function isGraphAvailable", text)

    def test_graph_binding_safe_before_init(self):
        """Module must never access graph before init."""
        text = (WEB / "studio-graph-binding.js").read_text(encoding="utf-8")
        # No top-level graph access
        self.assertNotIn("window.__comfymodal_comfy_app.graph", text)
        self.assertNotIn("window.app.graph", text)

    def test_graph_binding_esc_cancels_capture(self):
        """Capture mode must handle Escape to cancel."""
        text = (WEB / "studio-graph-binding.js").read_text(encoding="utf-8")
        self.assertIn("Escape", text)
        self.assertIn("onCancel", text)

    def test_extract_node_candidates(self):
        """extractNodeCandidates must extract widget/input/output candidates."""
        text = (WEB / "studio-graph-binding.js").read_text(encoding="utf-8")
        self.assertIn("extractNodeCandidates", text)
        self.assertIn("widgets", text)
        self.assertIn("inputs", text)
        self.assertIn("outputs", text)


class BindingKeyTests(unittest.TestCase):
    """Binding keys must be consistent between wizard, models, and routes."""

    def test_model_binding_keys_updated(self):
        """studio_models.py must use the updated binding keys."""
        text = (REPO_ROOT / "studio_models.py").read_text(encoding="utf-8")
        # Updated keys (not legacy object_remove_image / object_replace_image)
        self.assertIn('"source_image"', text)
        self.assertIn('"mask"', text)
        self.assertIn('"instruction"', text)
        self.assertIn('"replacement_prompt"', text)
        # Legacy keys must NOT be in FEATURE_BINDING_KEYS anymore
        # (they can still appear in docstrings or comments)
        binding_keys_section_start = text.find("_FEATURE_BINDING_KEYS")
        binding_keys_section = text[binding_keys_section_start:binding_keys_section_start + 600]
        self.assertNotIn("object_remove_image", binding_keys_section)
        self.assertNotIn("object_replace_image", binding_keys_section)
        self.assertNotIn("object_remove_mask", binding_keys_section)
        self.assertNotIn("object_replace_mask", binding_keys_section)

    def test_wizard_binding_keys_match_model(self):
        """Wizard binding keys must match the model's _FEATURE_BINDING_KEYS."""
        wizard_text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")
        model_text = (REPO_ROOT / "studio_models.py").read_text(encoding="utf-8")
        # Both use the same binding key identifiers
        for key in ["prompt", "source_image", "mask", "instruction", "replacement_prompt"]:
            self.assertIn(key, wizard_text, f"Wizard missing binding key: {key}")
            self.assertIn(key, model_text, f"Model missing binding key: {key}")


class CaptureModuleTests(unittest.TestCase):
    """Capture module must export captureCurrentComfyGraph."""

    def test_capture_current_comfy_graph_exported(self):
        """studio-backend-capture.js must export captureCurrentComfyGraph."""
        text = (WEB / "studio-backend-capture.js").read_text(encoding="utf-8")
        self.assertIn("captureCurrentComfyGraph", text)

    def test_capture_returns_structured_result(self):
        """captureCurrentComfyGraph must return structured {ok, graphJson, ...}."""
        text = (WEB / "studio-backend-capture.js").read_text(encoding="utf-8")
        self.assertIn("ok", text)
        self.assertIn("graphJson", text)
        self.assertIn("warnings", text)

    def test_capture_no_fake_status(self):
        """captureCurrentComfyGraph must NOT fabricate status or success."""
        text = (WEB / "studio-backend-capture.js").read_text(encoding="utf-8")
        # The captureCurrentComfyGraph function must not contain "runnable"
        # Find just the captureCurrentComfyGraph function body
        fn_start = text.find("captureCurrentComfyGraph")
        fn_end = text.find("\nexport async function takeSnapshotOfCurrentGraph")
        if fn_start >= 0 and fn_end > fn_start:
            fn_text = text[fn_start:fn_end]
            self.assertNotIn('"runnable"', fn_text,
                             "captureCurrentComfyGraph must not fabricate status")
        # The legacy takeSnapshotOfCurrentGraph still uses "runnable" — that's OK

    def test_wizard_awaits_graph_capture(self):
        """Wizard save flow must await captureCurrentComfyGraph."""
        text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")
        self.assertIn("await captureCurrentComfyGraph()", text)


class PresetWizardStylingTests(unittest.TestCase):
    """Wizard must have proper CSS class names in styles."""

    def test_wizard_mode_class_in_styles(self):
        """studio-styles.js must define .comfymodal-studio-wizard-mode."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn("comfymodal-studio-wizard-mode", text)

    def test_wizard_overlay_class_in_styles(self):
        """studio-styles.js must define .comfymodal-studio-wizard-overlay."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn("comfymodal-studio-wizard-overlay", text)

    def test_wizard_panel_class_in_styles(self):
        """studio-styles.js must define .comfymodal-studio-wizard-panel."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn("comfymodal-studio-wizard-panel", text)

    def test_wizard_binding_row_class(self):
        """studio-styles.js must define .comfymodal-studio-wizard-binding-row."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn("comfymodal-studio-wizard-binding-row", text)

    def test_wizard_feature_list_class(self):
        """studio-styles.js must define .comfymodal-studio-wizard-feature-list."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn("comfymodal-studio-wizard-feature-list", text)

    def test_backend_action_bar_class(self):
        """studio-styles.js must define .comfymodal-studio-backend-action-bar."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn("comfymodal-studio-backend-action-bar", text)

    def test_wizard_step_classes(self):
        """studio-styles.js must define wizard step indicator classes."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        self.assertIn("comfymodal-studio-wizard-step-dot", text)
        self.assertIn("comfymodal-studio-wizard-step-label", text)


class StudioBackendMakePresetTests(unittest.TestCase):
    """Backend page must have the Make Preset action."""

    def test_backend_has_make_preset(self):
        """studio-backend.js must reference 'Make Preset'."""
        text = (WEB / "studio-backend.js").read_text(encoding="utf-8")
        self.assertIn("Make Preset", text)

    def test_backend_launches_wizard(self):
        """studio-backend.js must import studio-preset-wizard.js."""
        text = (WEB / "studio-backend.js").read_text(encoding="utf-8")
        self.assertIn("./studio-preset-wizard.js", text)
        self.assertIn("openPresetWizard", text)

    def test_backend_no_large_wizard_logic(self):
        """studio-backend.js must keep wizard logic glue-only."""
        text = (WEB / "studio-backend.js").read_text(encoding="utf-8")
        # It should NOT contain the actual wizard render functions
        self.assertNotIn("renderFeaturesStep", text)
        self.assertNotIn("renderBindingsStep", text)
        self.assertNotIn('"features"', text)  # The state step values belong in the wizard


if __name__ == "__main__":
    unittest.main()
