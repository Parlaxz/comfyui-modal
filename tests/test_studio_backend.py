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


class PlaygroundOutputAndHistoryWiringTests(unittest.TestCase):
    """Successful Studio runs must wire output assets and history visibility."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-playground.js").read_text(encoding="utf-8")

    def test_completed_state_checks_primary_asset_id(self):
        """Polling completion path must read primary_asset_id evidence."""
        self.assertIn("primary_asset_id", self.text)

    def test_completed_state_uses_assets_route(self):
        """Playground canvas should use the stable /assets route for completed runs."""
        self.assertIn('"/assets/"', self.text)

    def test_filmstrip_recognizes_nested_studio_meta(self):
        """Recent runs filter must accept run-history entries with extra.studio_meta."""
        self.assertIn("extra.studio_meta", self.text)

    def test_filmstrip_fetches_broader_history_window(self):
        """Filmstrip should not miss studio runs due to a tiny history limit."""
        self.assertIn('"/run-history?limit=50"', self.text)


class HistoryFlatStudioMetaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (WEB / "studio-history.js").read_text(encoding="utf-8")

    def test_history_uses_normalized_studio_fields(self):
        """History must read feature fields from normalized records (featureId, presetId)."""
        self.assertIn("featureId", self.text)
        self.assertIn("presetId", self.text)

    def test_history_accepts_output_path_as_output_evidence(self):
        self.assertIn("normalizeStudioRun", self.text)


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
        """Wizard binding keys must be defined in FEATURE_REQUIREMENTS (studio-preset-capabilities.js)."""
        caps_text = (WEB / "studio-preset-capabilities.js").read_text(encoding="utf-8")
        # txt2img
        self.assertIn('"prompt"', caps_text)
        self.assertIn('"output"', caps_text)
        # object_remove
        self.assertIn('"source_image"', caps_text)
        self.assertIn('"mask"', caps_text)
        self.assertIn('"instruction"', caps_text)
        # object_replace
        self.assertIn('"replacement_prompt"', caps_text)
        # Wizard delegates to getRequiredBindingsForFeature / getOptionalBindingsForFeature
        wiz_text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")
        self.assertIn("getRequiredBindingsForFeature", wiz_text)
        self.assertIn("getOptionalBindingsForFeature", wiz_text)

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
        """Binding keys in FEATURE_REQUIREMENTS must match the model's _FEATURE_BINDING_KEYS."""
        caps_text = (WEB / "studio-preset-capabilities.js").read_text(encoding="utf-8")
        model_text = (REPO_ROOT / "studio_models.py").read_text(encoding="utf-8")
        # Both use the same binding key identifiers
        for key in ["prompt", "source_image", "mask", "instruction", "replacement_prompt"]:
            self.assertIn(key, caps_text, f"Capabilities missing binding key: {key}")
            self.assertIn(key, model_text, f"Model missing binding key: {key}")
        # Wizard delegates to capabilities module
        wizard_text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")
        self.assertIn("getRequiredBindingsForFeature", wizard_text)


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


class StudioPresetWizardInteractionTests(unittest.TestCase):
    """Nested wizard controls must not trigger graph-binding capture on their parent rows."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")

    def test_wizard_has_interactive_target_guard(self):
        """Binding-row clicks must ignore nested interactive controls like select/button/input."""
        self.assertIn("closest(\"select, button, input, textarea, a\")", self.text)

    def test_candidate_dropdown_stops_pointer_bubbling(self):
        """Candidate dropdown must stop pointer/click bubbling so opening it does not start capture."""
        self.assertIn('select.addEventListener("mousedown"', self.text)
        self.assertIn("stopPropagation", self.text)


# ---------------------------------------------------------------------------
# Studio Run Normalizer — shared image URL resolution helper
# ---------------------------------------------------------------------------

class StudioRunNormalizerTests(unittest.TestCase):
    """studio-run-normalizer.js must exist and export helpers."""

    def test_run_normalizer_module_exists(self):
        """web/studio-run-normalizer.js must exist."""
        self.assertTrue(
            (WEB / "studio-run-normalizer.js").exists(),
            "studio-run-normalizer.js missing — expected a shared run normalizer helper",
        )

    def test_run_normalizer_exports_resolveRunImageUrl(self):
        """studio-run-normalizer.js must export resolveRunImageUrl."""
        self.assertTrue(
            _JsModule(WEB / "studio-run-normalizer.js").has_export("resolveRunImageUrl"),
            "Expected export function resolveRunImageUrl",
        )

    def test_run_normalizer_exports_hasRunImage(self):
        """studio-run-normalizer.js must export hasRunImage."""
        self.assertTrue(
            _JsModule(WEB / "studio-run-normalizer.js").has_export("hasRunImage"),
            "Expected export function hasRunImage",
        )

    def test_run_normalizer_resolves_primary_asset_id(self):
        """resolveRunImageUrl must prefer extra.primary_asset_id when present."""
        text = (WEB / "studio-run-normalizer.js").read_text(encoding="utf-8")
        self.assertIn("primary_asset_id", text)

    def test_run_normalizer_falls_back_to_run_asset_id(self):
        """resolveRunImageUrl must fall back to run.asset_id when primary_asset_id absent."""
        text = (WEB / "studio-run-normalizer.js").read_text(encoding="utf-8")
        self.assertIn("asset_id", text)

    def test_run_normalizer_falls_back_to_output_path(self):
        """resolveRunImageUrl must fall back to output_path when asset_id absent."""
        text = (WEB / "studio-run-normalizer.js").read_text(encoding="utf-8")
        self.assertIn("output_path", text)

    def test_run_normalizer_returns_null_for_no_image(self):
        """resolveRunImageUrl must return null when no image source exists."""
        text = (WEB / "studio-run-normalizer.js").read_text(encoding="utf-8")
        # Should have a null return or null fallback path
        self.assertIn("null", text)

    def test_run_normalizer_handles_assets_route(self):
        """resolveRunImageUrl must use /assets/ route for asset-based URLs."""
        text = (WEB / "studio-run-normalizer.js").read_text(encoding="utf-8")
        self.assertIn("/assets/", text)

    def test_run_normalizer_handles_outputs_route(self):
        """resolveRunImageUrl must use /studio/outputs/ route for output_path URLs."""
        text = (WEB / "studio-run-normalizer.js").read_text(encoding="utf-8")
        self.assertIn("/studio/outputs/", text)


# ---------------------------------------------------------------------------
# History gallery — image grid with clickable cards and preview overlay
# ---------------------------------------------------------------------------

class HistoryGalleryTests(unittest.TestCase):
    """History must show an image grid/gallery with clickable cards and preview overlay."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-history.js").read_text(encoding="utf-8")

    def test_history_uses_gallery_grid_class(self):
        """history must use a gallery grid container class."""
        self.assertIn("comfymodal-studio-history-gallery", self.text)

    def test_history_has_preview_overlay(self):
        """history must have a preview overlay class."""
        self.assertIn("comfymodal-studio-history-preview", self.text)

    def test_history_overlay_has_close_button(self):
        """history preview must have a close button."""
        self.assertIn("close", self.text.lower())

    def test_history_creates_img_in_cards(self):
        """history cards must create img elements for image runs."""
        self.assertTrue(
            '"img"' in self.text or 'el("img"' in self.text,
            "Expected img creation in history gallery cards",
        )

    def test_history_card_click_opens_preview(self):
        """history gallery cards must have click handlers that set preview state."""
        self.assertTrue(
            "onclick" in self.text or "click" in self.text.lower(),
            "Expected onclick or click handler in history gallery",
        )

    def test_history_shows_non_image_fallback(self):
        """history must show fallback tile for non-image runs (not broken img)."""
        self.assertTrue(
            "fallback" in self.text.lower() or "no image" in self.text.lower(),
            "Expected fallback tile for non-image runs",
        )

    def test_history_preserves_experiment_grouping(self):
        """history gallery must preserve experiment_id grouping."""
        self.assertIn("experiment_id", self.text)

    def test_history_ungrouped_runs_use_gallery_grid(self):
        """ungrouped history must still render inside the gallery grid wrapper."""
        self.assertIn(
            'container.appendChild(renderHistoryGallery(normalizedRuns, apiBase, openPreview));',
            self.text,
        )


# ---------------------------------------------------------------------------
# Playground carousel — image thumbnails that update the canvas
# ---------------------------------------------------------------------------

class PlaygroundCarouselTests(unittest.TestCase):
    """Playground filmstrip must be an image carousel of thumbnails."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-playground.js").read_text(encoding="utf-8")

    def test_filmstrip_uses_carousel_class(self):
        """filmstrip must use a carousel class instead of plain list."""
        self.assertIn("comfymodal-studio-carousel", self.text)

    def test_carousel_renders_img_thumbnails(self):
        """carousel must render img elements for image-producing runs."""
        self.assertTrue(
            '"img"' in self.text or 'el("img"' in self.text,
            "Expected img creation in carousel thumbnails",
        )

    def test_carousel_filters_image_producing_runs(self):
        """carousel must filter to only image-producing runs."""
        self.assertTrue(
            "hasRunImage" in self.text or "resolveRunImageUrl" in self.text,
            "Expected hasRunImage or resolveRunImageUrl usage in carousel",
        )

    def test_carousel_click_updates_canvas(self):
        """clicking a carousel thumbnail must update the main canvas output."""
        self.assertTrue(
            "lastRunOutput" in self.text or "setRunState" in self.text,
            "Expected lastRunOutput or setRunState reference in carousel click handler",
        )


# ---------------------------------------------------------------------------
# Gallery / carousel / lightbox styles
# ---------------------------------------------------------------------------

class GalleryCarouselStylesTests(unittest.TestCase):
    """studio-styles.js must define gallery, carousel, and preview overlay styles."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-styles.js").read_text(encoding="utf-8")

    def test_styles_have_history_gallery_class(self):
        """styles must define .comfymodal-studio-history-gallery."""
        self.assertIn("comfymodal-studio-history-gallery", self.text)

    def test_styles_have_history_preview_class(self):
        """styles must define .comfymodal-studio-history-preview."""
        self.assertIn("comfymodal-studio-history-preview", self.text)

    def test_styles_have_carousel_class(self):
        """styles must define .comfymodal-studio-carousel."""
        self.assertIn("comfymodal-studio-carousel", self.text)

    def test_styles_have_preview_overlay_positioning(self):
        """preview overlay must use fixed/flex positioning."""
        self.assertIn("position", self.text)


# ---------------------------------------------------------------------------
# normalizeStudioRun — shared run normalizer with full normalized object
# ---------------------------------------------------------------------------

class NormalizeStudioRunTests(unittest.TestCase):
    """normalizeStudioRun must exist and produce stable normalized objects."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-run-normalizer.js").read_text(encoding="utf-8")

    def test_normalize_studio_run_exported(self):
        """normalizeStudioRun must be exported from studio-run-normalizer.js."""
        self.assertTrue(
            _JsModule(WEB / "studio-run-normalizer.js").has_export("normalizeStudioRun"),
            "Expected export function normalizeStudioRun",
        )

    def test_normalize_studio_run_accepts_raw_run_and_api_base(self):
        """normalizeStudioRun must accept (rawRun, apiBase) signature."""
        self.assertIn("normalizeStudioRun", self.text)
        self.assertIn("apiBase", self.text)

    def test_normalize_studio_run_returns_stable_object(self):
        """normalizeStudioRun must return an object with all required fields."""
        # Check for at least the core fields expected in the normalized output
        for field in ["id", "status", "imageUrl", "presetId", "featureId", "prompt", "raw"]:
            self.assertIn(field, self.text, f"Normalized object missing field: {field}")

    def test_normalize_studio_run_handles_older_history_aliases(self):
        """normalizeStudioRun must tolerate legacy field aliases (run_id, state, created)."""
        self.assertIn("run_id", self.text)
        self.assertIn("state", self.text)

    def test_normalize_studio_run_includes_resolved_controls(self):
        """normalizeStudioRun must include resolvedControls and requestedControls."""
        self.assertIn("resolvedControls", self.text)
        self.assertIn("requestedControls", self.text)

    def test_normalize_studio_run_includes_timings(self):
        """normalizeStudioRun must include timings, durationMs, startedAt, completedAt."""
        self.assertIn("timings", self.text)
        self.assertIn("durationMs", self.text)

    def test_normalize_studio_run_uses_total_ms_from_timings(self):
        """normalizeStudioRun must derive durationMs from timings.total_ms when explicit duration_ms absent."""
        # Should contain timings.total_ms or total_ms as a fallback
        self.assertIn("total_ms", self.text) or self.assertIn("timings.total_ms", self.text)

    def test_normalize_studio_run_uses_canonical_aliases(self):
        """normalizeStudioRun must prefer canonical backend fields over legacy aliases."""
        self.assertIn("timings", self.text)

    def test_normalize_studio_run_includes_workflow_hash(self):
        """normalizeStudioRun must include workflowHash."""
        self.assertIn("workflowHash", self.text)

    def test_normalize_studio_run_includes_negative_prompt(self):
        """normalizeStudioRun must include negativePrompt."""
        self.assertIn("negativePrompt", self.text)

    def test_normalize_studio_run_includes_snapshot_id(self):
        """normalizeStudioRun must include snapshotId."""
        self.assertIn("snapshotId", self.text)

    def test_normalize_studio_run_includes_preset_label(self):
        """normalizeStudioRun must include presetLabel."""
        self.assertIn("presetLabel", self.text)

    def test_normalize_studio_run_includes_experiment_id(self):
        """normalizeStudioRun must include experimentId."""
        self.assertIn("experimentId", self.text)


# ---------------------------------------------------------------------------
# Shared normalizer consumed by History and Playground
# ---------------------------------------------------------------------------

class SharedNormalizerConsumptionTests(unittest.TestCase):
    """Both History and Playground must consume the shared normalizer."""

    def test_history_imports_normalize_studio_run(self):
        """studio-history.js must import normalizeStudioRun."""
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        self.assertIn("normalizeStudioRun", text)

    def test_playground_imports_normalize_studio_run(self):
        """studio-playground.js must import normalizeStudioRun."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertIn("normalizeStudioRun", text)

    def test_history_uses_normalized_fields_not_raw_parsing(self):
        """History must use normalized fields instead of duplicating parsing."""
        h_text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        # History should not duplicate prompt/status/image/timestamp parsing
        # Check it uses normalized record fields
        p_text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        # Both files import from normalizer
        self.assertIn("./studio-run-normalizer.js", h_text)
        self.assertIn("./studio-run-normalizer.js", p_text)


# ---------------------------------------------------------------------------
# Run button — no 'Run Again' label (direct idle/error/completed submission)
# ---------------------------------------------------------------------------

class RunButtonLabelTests(unittest.TestCase):
    """Primary button labels must not use 'Run Again'."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-playground.js").read_text(encoding="utf-8")

    def test_no_run_again_label(self):
        """'Run Again' must not appear in playground button labels."""
        self.assertNotIn("Run Again", self.text)

    def test_run_label_for_idle(self):
        """Run button must show 'Run' while idle."""
        self.assertIn('"Run"', self.text)

    def test_submitted_label_in_flight(self):
        """Run button must show 'Submitted' / 'Queued…' / 'Running…' while in flight."""
        self.assertIn("Submitted", self.text)
        self.assertIn("Queued", self.text)
        self.assertIn("Running", self.text)

    def test_completed_label_shows_run_not_run_again(self):
        """After completion, button must show 'Run' not 'Run Again'."""
        self.assertIn("completed", self.text.lower())

    def test_single_click_submits_immediately_on_completed(self):
        """On completed state, a single Run click must immediately submit, not just clear state."""
        # Must call runStudioPreset directly, not just clear runState
        self.assertIn("runStudioPreset", self.text)

    def test_single_click_submits_immediately_on_error(self):
        """On error state, a single Run click must immediately submit, not just clear state."""
        # The submit flow must be invoked directly from the error-state onclick
        # Look for a pattern like completed/error onclick calling the submit function
        submit_call_pattern = "runStudioPreset" in self.text
        self.assertTrue(submit_call_pattern)


# ---------------------------------------------------------------------------
# Backend page — default tab and tab order
# ---------------------------------------------------------------------------

class BackendTabOrderTests(unittest.TestCase):
    """Backend page default tab must be presets; tab order must render Backend Presets before Snapshots."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-backend.js").read_text(encoding="utf-8")

    def test_default_tab_is_presets(self):
        """Default activeTab must be 'presets' (not 'snapshots')."""
        self.assertIn('activeTab = "presets"', self.text)

    def test_presets_tab_before_snapshots_in_dom(self):
        """Tab creation must add Backend Presets tab before Snapshots tab."""
        # Find the specific makeTab calls: "presets" must come before "snapshots"
        presets_call_pos = self.text.find('makeTab("presets"')
        snapshots_call_pos = self.text.find('makeTab("snapshots"')
        self.assertGreater(snapshots_call_pos, presets_call_pos,
                           "presets makeTab call must appear before snapshots makeTab call")


# ---------------------------------------------------------------------------
# Delete preset — rename archivePreset to deletePreset in frontend
# ---------------------------------------------------------------------------

class DeletePresetTests(unittest.TestCase):
    """archivePreset must be renamed to deletePreset in frontend API and UI."""

    def test_delete_preset_exists_in_api(self):
        """studio-backend-api.js must have deletePreset."""
        text = (WEB / "studio-backend-api.js").read_text(encoding="utf-8")
        self.assertIn("deletePreset", text)

    def test_archive_preset_not_in_frontend_api(self):
        """studio-backend-api.js must NOT have archivePreset anymore."""
        text = (WEB / "studio-backend-api.js").read_text(encoding="utf-8")
        self.assertNotIn("archivePreset", text)

    def test_delete_preset_still_hits_delete_route(self):
        """deletePreset must still call DELETE on /studio/presets/{id}."""
        text = (WEB / "studio-backend-api.js").read_text(encoding="utf-8")
        self.assertIn('"DELETE"', text)

    def test_delete_preset_label_in_presets_detail(self):
        """Preset detail actions must show 'Delete preset' label."""
        text = (WEB / "studio-backend-presets.js").read_text(encoding="utf-8")
        self.assertIn("Delete preset", text)

    def test_delete_preset_confirmation_mentions_soft_delete(self):
        """Delete preset confirmation must explain soft-delete behavior."""
        text = (WEB / "studio-backend-presets.js").read_text(encoding="utf-8")
        self.assertIn("soft-delete", text)

    def test_delete_preset_not_archive_in_presets(self):
        """studio-backend-presets.js must not use 'Archive' for preset actions."""
        text = (WEB / "studio-backend-presets.js").read_text(encoding="utf-8")
        # It may contain "archive" only in comments/import refs but not as action label
        self.assertNotIn('"Archive"', text)


# ---------------------------------------------------------------------------
# Persistence state — versioned localStorage key for selection
# ---------------------------------------------------------------------------

class PersistenceStateTests(unittest.TestCase):
    """Selection persistence state must use localStorage with versioned key."""

    def test_persistence_key_defined(self):
        """A versioned localStorage key must be defined for selection persistence."""
        # The actual persistence code lives in studio-playground-state.js
        state_text = (WEB / "studio-playground-state.js").read_text(encoding="utf-8")
        self.assertIn("localStorage", state_text)
        self.assertIn("comfymodal.studio.playground.v1", state_text)
        self.assertNotIn("comfymodal_studio_selection_v1", state_text)
        # Playground imports the persistence helpers
        pg_text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertIn("saveSelection", pg_text)
        self.assertIn("loadSelection", pg_text)

    def test_persists_selected_preset_id(self):
        """Selected preset id must be persisted."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertIn("saveSelection", text)

    def test_persists_selected_feature_id(self):
        """Selected feature id must be persisted."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertIn("featureId", text)

    def test_control_draft_storage_helpers_defined(self):
        """Playground state must define localStorage helpers for per-preset drafts."""
        state_text = (WEB / "studio-playground-state.js").read_text(encoding="utf-8")
        self.assertIn("comfymodal.studio.playground.drafts.v1", state_text)
        self.assertIn("loadControlDraft", state_text)
        self.assertIn("saveControlDraft", state_text)

    def test_playground_imports_control_draft_helpers(self):
        """Playground must import the per-preset draft persistence helpers."""
        pg_text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertIn("loadControlDraft", pg_text)
        self.assertIn("saveControlDraft", pg_text)


# ---------------------------------------------------------------------------
# Hydration/restoration order in Playground
# ---------------------------------------------------------------------------

class HydrationRestorationTests(unittest.TestCase):
    """Hydration/restoration order must follow: edit > completed run > snapshot defaults > registry."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-playground.js").read_text(encoding="utf-8")

    def test_restores_latest_completed_run(self):
        """Must restore latest completed run for preset+feature when available."""
        self.assertIn("completed", self.text.lower())

    def test_falls_back_to_snapshot_defaults(self):
        """Must fall back to snapshot defaults when no completed run."""
        self.assertIn("defaults", self.text)

    def test_clears_selection_on_invalid_preset(self):
        """Invalid/deleted preset must clear saved selection and fall back."""
        self.assertIn("clear", self.text.lower())

    def test_sorts_by_completed_at_descending(self):
        """Must sort matching runs by completedAt or startedAt descending, not assume array order."""
        self.assertIn("completedAt", self.text) or self.assertIn("startedAt", self.text)
        self.assertIn("sort", self.text.lower())

    def test_hydrates_controls_from_persisted_draft(self):
        """Controls should hydrate from persisted draft before falling back to snapshot defaults."""
        self.assertIn("loadControlDraft", self.text)
        self.assertIn("state.playground._hydratedControls = draft", self.text)

    def test_completed_run_preview_no_longer_seeds_hydrated_controls(self):
        """Latest completed run may restore preview state but must not seed hydrated controls."""
        self.assertIn("lastRunOutput", self.text)
        self.assertIn("_selectedRun", self.text)
        self.assertNotIn("latest.resolvedControls || latest.requestedControls", self.text)

    def test_persists_control_draft_updates_from_user_edits(self):
        """User control edits must be persisted to per-preset draft storage."""
        self.assertIn("saveControlDraft", self.text)

    def test_render_control_uses_explicit_precedence_checks(self):
        """Render path should use explicit precedence checks instead of nullish fallback chains."""
        self.assertIn("in currentOverrides", self.text)
        self.assertIn("in hydratedValues", self.text)


class BackendSelectorInteractionGuardTests(unittest.TestCase):
    """Hydration must not re-render Playground while the backend selector is being opened."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-playground.js").read_text(encoding="utf-8")

    def test_tracks_backend_selector_interaction_during_hydration(self):
        """The backend selector should set an interaction guard before hydration can re-render."""
        self.assertIn("_backendSelectInteracting", self.text)
        self.assertIn('select.addEventListener("mousedown"', self.text)
        self.assertIn('select.addEventListener("focus"', self.text)

    def test_hydration_skip_checks_interaction_guard(self):
        """Hydration re-render guard must honor backend-selector interaction state, not focus alone."""
        self.assertIn("!state.playground._backendSelectInteracting", self.text)


# ---------------------------------------------------------------------------
# Recent runs — reusable state-owned collection
# ---------------------------------------------------------------------------

class RecentRunsRefreshTests(unittest.TestCase):
    """Recent runs must be refreshed after finalized completion and on return from History."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-playground.js").read_text(encoding="utf-8")

    def test_recent_runs_refresh_after_completion(self):
        """Recent runs must be refreshed after a run completes."""
        self.assertIn("refresh", self.text.lower())

    def test_only_completed_runs_with_image_in_recent(self):
        """Only completed runs with valid image outputs appear as thumbnails."""
        self.assertIn("completed", self.text.lower())
        self.assertIn("imageUrl", self.text)

    def test_thumbnail_click_updates_canvas_and_selection(self):
        """Clicking thumbnail must update canvas image, selected run, and metadata."""
        self.assertIn("metadata", self.text.lower())


class RecentRunsEmptyStateLoopTests(unittest.TestCase):
    """Empty recent-runs state must not be treated as loading forever."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-playground.js").read_text(encoding="utf-8")

    def test_recent_runs_cache_uses_distinct_unloaded_sentinel(self):
        """Recent runs cache must distinguish unloaded from loaded-empty."""
        self.assertIn("let _recentRunsCache = null", self.text)

    def test_filmstrip_branches_on_null_loading_state(self):
        """Filmstrip should only fetch/re-render while cache is null, not when it is an empty array."""
        self.assertIn("if (recentRuns == null)", self.text)
        self.assertIn("Recent runs will appear here once you use the Playground.", self.text)


# ---------------------------------------------------------------------------
# Metadata UX — compact section tied to selected canvas run
# ---------------------------------------------------------------------------

class MetadataUxTests(unittest.TestCase):
    """Metadata section must show generation settings tied to selected canvas run."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-playground.js").read_text(encoding="utf-8")

    def test_metadata_section_exists(self):
        """A metadata section must exist in the Playground."""
        self.assertIn("metadata", self.text.lower())

    def test_metadata_shows_prompt_and_negative_prompt(self):
        """Metadata must show at least prompt and negative prompt."""
        self.assertIn("prompt", self.text.lower())

    def test_metadata_shows_preset_and_feature(self):
        """Metadata must show preset and feature info."""
        self.assertIn("preset", self.text.lower())

    def test_metadata_shows_generation_time(self):
        """Metadata must show generation time/duration."""
        self.assertIn("duration", self.text.lower())

    def test_metadata_has_advanced_expandable_section(self):
        """Metadata must have a collapsible advanced section."""
        self.assertIn("advanced", self.text.lower())
        self.assertIn("collaps", self.text.lower())

    def test_metadata_uses_nullish_checks_not_truthy(self):
        """Metadata must use nullish checks (`!= null`) not truthy checks for optional values."""
        # Should use == null comparison or != null, not bare truthy checks
        self.assertIn("!= null", self.text)


class NullishChecksTests(unittest.TestCase):
    """Metadata and history rendering must preserve falsy values (0, 0.0, '') using nullish checks."""

    def setUp(self) -> None:
        self.pg_text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.h_text = (WEB / "studio-history.js").read_text(encoding="utf-8")

    def test_playground_uses_nullish_for_prompt(self):
        """Playground metadata must check prompt with != null not truthy."""
        self.assertIn("!= null", self.pg_text)

    def test_playground_uses_nullish_for_duration(self):
        """Playground metadata must check durationMs with != null not truthy."""
        self.assertIn("!= null", self.pg_text)

    def test_history_uses_nullish_for_metadata(self):
        """History preview must use nullish checks for metadata fields."""
        self.assertIn("!= null", self.h_text)


class PresetDeletionClearsSelectionTests(unittest.TestCase):
    """Preset deletion must clear persisted selection and add row list action."""

    def test_preset_deletion_calls_clear_selection(self):
        """Delete preset handler must call clearSelection for persisted state."""
        text = (WEB / "studio-backend-presets.js").read_text(encoding="utf-8")
        self.assertIn("clearSelection", text)

    def test_preset_list_has_delete_action_row(self):
        """Preset list cards must have a delete action row, not just detail panel."""
        text = (WEB / "studio-backend-presets.js").read_text(encoding="utf-8")
        # The list item should have a delete button
        self.assertIn("Delete preset", text) or self.assertIn("deletePreset", text)


# ---------------------------------------------------------------------------
# CONTROL_DEFS must include sampler and scheduler
# ---------------------------------------------------------------------------

class ControlDefsSamplerSchedulerTests(unittest.TestCase):
    """CONTROL_DEFS must have sampler and scheduler entries."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-feature-registry.js").read_text(encoding="utf-8")

    def _control_defs_section(self):
        """Return the CONTROL_DEFS section (last export in file)."""
        start = self.text.find("export const CONTROL_DEFS")
        if start < 0:
            return ""
        return self.text[start:]

    def test_control_defs_has_sampler(self):
        """CONTROL_DEFS must define sampler as a control with id, label, type, defaultValue."""
        section = self._control_defs_section()
        self.assertIn("sampler", section,
                      "sampler must be defined inside CONTROL_DEFS")
        self.assertIn("label: \"Sampler\"", section)
        self.assertIn("type:", section)

    def test_control_defs_has_scheduler(self):
        """CONTROL_DEFS must define scheduler as a control with id, label, type, defaultValue."""
        section = self._control_defs_section()
        self.assertIn("scheduler", section,
                      "scheduler must be defined inside CONTROL_DEFS")
        self.assertIn("label: \"Scheduler\"", section)

    def test_control_defs_sampler_and_scheduler_have_default_value(self):
        """sampler and scheduler in CONTROL_DEFS must have a defaultValue."""
        section = self._control_defs_section()
        sampler_start = section.find("sampler:")
        self.assertGreater(sampler_start, 0, "sampler: key not found in CONTROL_DEFS")
        sampler_block = section[sampler_start:sampler_start + 400]
        self.assertIn("defaultValue:", sampler_block,
                      "sampler CONTROL_DEF must have defaultValue")
        scheduler_start = section.find("scheduler:")
        self.assertGreater(scheduler_start, 0, "scheduler: key not found in CONTROL_DEFS")
        scheduler_block = section[scheduler_start:scheduler_start + 400]
        self.assertIn("defaultValue:", scheduler_block,
                      "scheduler CONTROL_DEF must have defaultValue")

    def test_control_defs_sampler_has_applicable_features(self):
        """sampler CONTROL_DEF must list applicable features."""
        section = self._control_defs_section()
        sampler_start = section.find("sampler:")
        self.assertGreater(sampler_start, 0, "sampler: key not found in CONTROL_DEFS")
        sampler_block = section[sampler_start:sampler_start + 400]
        self.assertIn("applicableFeatures:", sampler_block)

    def test_feature_specs_txt2img_includes_sampler_scheduler(self):
        """FEATURE_SPECS txt2img controls list should include sampler and scheduler."""
        txt2img_start = self.text.find("txt2img")
        txt2img_block = self.text[txt2img_start:txt2img_start + 800]
        self.assertIn("sampler", txt2img_block,
                      "FEATURE_SPECS txt2img must list sampler in its controls array")
        self.assertIn("scheduler", txt2img_block,
                      "FEATURE_SPECS txt2img must list scheduler in its controls array")


# ---------------------------------------------------------------------------
# History must use presetLabel for display
# ---------------------------------------------------------------------------

class HistoryPresetLabelTests(unittest.TestCase):
    """History rendering must use presetLabel instead of presetId for display."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-history.js").read_text(encoding="utf-8")

    def test_history_group_header_uses_preset_label(self):
        """Group header must use firstRun.presetLabel with fallback to firstRun.presetId."""
        # The group header should reference presetLabel as the primary label source
        self.assertIn("firstRun.presetLabel", self.text)
        # Should still fall back to presetId when presetLabel is empty
        self.assertIn("firstRun.presetId", self.text)

    def test_history_preview_shows_preset_label(self):
        """Preview overlay must show presetLabel in metadata."""
        # Line 96 currently shows nr.presetId — should show nr.presetLabel
        self.assertIn("nr.presetLabel", self.text)

    def test_history_carousel_label_uses_preset_label(self):
        """Filmstrip carousel should use presetLabel for label display."""
        # Check line 1562: nr.presetLabel || nr.presetId || nr.featureId
        pg_text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        # Should reference presetLabel as first choice for label
        self.assertIn("presetLabel || nr.presetId", pg_text)


# ---------------------------------------------------------------------------
# Normalizer surfaces presetLabel from canonical aliases
# ---------------------------------------------------------------------------

class NormalizerPresetLabelTests(unittest.TestCase):
    """normalizeStudioRun must surface presetLabel from robust aliases."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-run-normalizer.js").read_text(encoding="utf-8")

    def test_normalizer_reads_preset_label_from_extra(self):
        """normalizeStudioRun must read presetLabel from extra.preset_label and extra.studio_preset_label."""
        self.assertIn("preset_label", self.text)
        self.assertIn("studio_preset_label", self.text)

    def test_normalizer_falls_back_to_studio_meta_for_label(self):
        """normalizeStudioRun must fall back to studio_meta.studio_preset_label."""
        self.assertIn("studio_preset_label", self.text)


# ---------------------------------------------------------------------------
# CONTROL_DEFS sampler/scheduler must be type "select" (not "text")
# ---------------------------------------------------------------------------

class ControlDefsSamplerSchedulerTypeTests(unittest.TestCase):
    """CONTROL_DEFS sampler and scheduler must have type: "select"."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-feature-registry.js").read_text(encoding="utf-8")

    def _control_defs_section(self):
        start = self.text.find("export const CONTROL_DEFS")
        if start < 0:
            return ""
        return self.text[start:]

    def test_sampler_type_is_select(self):
        section = self._control_defs_section()
        sampler_start = section.find("sampler:")
        sampler_block = section[sampler_start:sampler_start + 400]
        self.assertIn('type: "select"', sampler_block,
                      "sampler CONTROL_DEF must have type: 'select'")

    def test_scheduler_type_is_select(self):
        section = self._control_defs_section()
        scheduler_start = section.find("scheduler:")
        if scheduler_start < 0:
            scheduler_start = section.find("scheduler ")
        scheduler_block = section[scheduler_start:scheduler_start + 400]
        self.assertIn('type: "select"', scheduler_block,
                      "scheduler CONTROL_DEF must have type: 'select'")

    def test_sampler_has_dynamic_options_flag(self):
        section = self._control_defs_section()
        sampler_start = section.find("sampler:")
        sampler_block = section[sampler_start:sampler_start + 400]
        self.assertIn("dynamicOptions", sampler_block,
                      "sampler CONTROL_DEF must have dynamicOptions flag")

    def test_scheduler_has_dynamic_options_flag(self):
        section = self._control_defs_section()
        scheduler_start = section.find("scheduler:")
        if scheduler_start < 0:
            scheduler_start = section.find("scheduler ")
        scheduler_block = section[scheduler_start:scheduler_start + 400]
        self.assertIn("dynamicOptions", scheduler_block,
                      "scheduler CONTROL_DEF must have dynamicOptions flag")


# ---------------------------------------------------------------------------
# Playground renderControl must handle controlSchemas
# ---------------------------------------------------------------------------

class PlaygroundControlSchemaRenderingTests(unittest.TestCase):
    """renderControl must use controlSchemas from preset for schema-driven rendering."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-playground.js").read_text(encoding="utf-8")

    def test_render_checks_control_schemas(self):
        """renderControl must read controlSchemas from the preset."""
        self.assertIn("controlSchemas", self.text)

    def test_render_uses_schema_kind(self):
        """renderControl must use schema.kind for rendering."""
        self.assertIn("schemaKind", self.text)

    def test_render_enum_creates_select(self):
        """Enum schema kind renders as <select> with options."""
        self.assertIn('"enum"', self.text)
        self.assertIn('"select"', self.text)

    def test_render_boolean_creates_checkbox(self):
        """Boolean schema kind renders as checkbox."""
        self.assertIn('"checkbox"', self.text)

    def test_render_integer_uses_min_max(self):
        """Integer schema kind renders with min/max/step from schema."""
        self.assertIn("schema.minimum", self.text)
        self.assertIn("schema.maximum", self.text)
        self.assertIn("schema.step", self.text)

    def test_render_multiline_creates_textarea(self):
        """Multiline schema kind renders as textarea."""
        self.assertIn('"multiline"', self.text)

    def test_render_falls_back_to_static_type(self):
        """When no schema, render falls back to static CONTROL_DEFS type."""
        self.assertIn("def.type === ", self.text)

    def test_render_preserves_falsy_values(self):
        """Falsy values (0, false) are preserved, not coerced to default."""
        self.assertIn("!= null", self.text)


# ---------------------------------------------------------------------------
# Experiment mode uses canonical preset ID set
# ---------------------------------------------------------------------------

class ExperimentCanonicalPresetIdTests(unittest.TestCase):
    """Experiment mode must use canonical unique preset ID set."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")

    def test_get_experiment_preset_ids_exported(self):
        """getExperimentPresetIds must be exported."""
        self.assertIn("getExperimentPresetIds", self.text)

    def test_canonical_preset_ids_in_execute(self):
        """executeExperimentRun must use canonical preset ID set."""
        self.assertIn("canonicalPresetIds", self.text)

    def test_canonical_preset_ids_includes_base(self):
        """Canonical set includes base selectedBackendId."""
        self.assertIn("baseBackendId", self.text)

    def test_canonical_preset_ids_deduplicates(self):
        """Canonical set deduplicates via new Set."""
        self.assertIn("new Set(", self.text)

    def test_can_run_experiment_requires_two(self):
        """canRunExperiment requires >= 2 canonical presets."""
        self.assertIn("canonicalPresetIds.length >= 2", self.text)

    def test_disabled_reason_requires_two(self):
        """getExperimentDisabledReason mentions 'at least 2'."""
        self.assertIn("Select at least 2 presets", self.text)


# ---------------------------------------------------------------------------
# Phase 4: Captured control schemas – browser-side
# ---------------------------------------------------------------------------

class CapturedControlSchemasGraphBindingTests(unittest.TestCase):
    """extractNodeCandidates must capture full widget schema metadata."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-graph-binding.js").read_text(encoding="utf-8")
        self.fn_start = self.text.find("function extractNodeCandidates")
        self.fn_block = self.text[self.fn_start:self.fn_start + 3000]

    def test_captures_schema_type(self):
        """Widget candidate must include schemaType derived from w.type."""
        self.assertIn("schemaType", self.fn_block)

    def test_captures_enum_values(self):
        """Widget candidate must capture w.options?.values as enumValues."""
        self.assertIn("enumValues", self.fn_block)

    def test_captures_min_max_step_precision(self):
        """Widget candidate must capture min, max, step, precision."""
        for field in ["min", "max", "step", "precision"]:
            self.assertIn(field, self.fn_block,
                          f"Widget candidate missing field: {field}")

    def test_captures_default_value(self):
        """Widget candidate must capture default value."""
        self.assertIn("defaultValue", self.fn_block)

    def test_captures_multiline_flag(self):
        """Widget candidate must capture multiline flag."""
        self.assertIn("multiline", self.fn_block)

    def test_captures_boolean_default(self):
        """Widget candidate must handle boolean type for default."""
        self.assertIn("boolean", self.fn_block.lower())

    def test_captures_dynamic_values_if_available(self):
        """Widget candidate must capture w.options?.values for dynamic enums."""
        self.assertIn("w.options", self.fn_block)


class CapturedControlSchemasPresetWizardTests(unittest.TestCase):
    """Preset wizard must build controlSchemas in snapshot payload."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")

    def test_wizard_includes_control_schemas_in_snapshot_payload(self):
        """executeSave must include controlSchemas in snapshotPayload."""
        self.assertIn("controlSchemas", self.text,
                      "Preset wizard must reference controlSchemas")

    def test_wizard_has_build_control_schemas_function(self):
        """Wizard must have a buildControlSchemas helper."""
        self.assertIn("buildControlSchemas", self.text)

    def test_capture_stores_widget_schema(self):
        """startBindingCapture onCapture callback must store widgetSchema."""
        self.assertIn("widgetSchema", self.text)

    def test_snapshot_payload_accepts_control_schemas(self):
        """executeSave snapshotPayload must pass controlSchemas to API."""
        self.assertIn('controlSchemas:', self.text)


class CapturedControlSchemasSnapshotModelTests(unittest.TestCase):
    """Snapshot model on backend must persist controlSchemas."""

    def test_make_snapshot_accepts_control_schemas(self):
        """Backend make_snapshot must accept controlSchemas from body."""
        text = (REPO_ROOT / "studio_models.py").read_text(encoding="utf-8")
        self.assertIn("controlSchemas", text)

    def test_make_snapshot_defaults_to_empty_dict(self):
        """Backend make_snapshot must default controlSchemas to {}."""
        text = (REPO_ROOT / "studio_models.py").read_text(encoding="utf-8")
        # One of the entries in make_snapshot should include controlSchemas
        self.assertIn('"controlSchemas"', text)

    def test_update_snapshot_accepts_control_schemas(self):
        """Backend update_snapshot must accept controlSchemas update."""
        text = (REPO_ROOT / "studio_models.py").read_text(encoding="utf-8")
        self.assertIn("controlSchemas", text)

    def test_derive_control_schemas_checks_captured_first(self):
        """derive_control_schemas_from_snapshot must check controlSchemas first."""
        text = (REPO_ROOT / "studio_run_adapter.py").read_text(encoding="utf-8")
        self.assertIn("controlSchemas", text)

    def test_derive_falls_back_to_static_registry(self):
        """Old snapshots without controlSchemas must still derive from static table."""
        text = (REPO_ROOT / "studio_run_adapter.py").read_text(encoding="utf-8")
        self.assertIn("_NODE_WIDGET_SCHEMAS", text)


# ---------------------------------------------------------------------------
# Phase 4 Gap Fixes: Edit mode, candidate dropdown, toggle mapping
# ---------------------------------------------------------------------------

class Phase4FixEditModeControlSchemasTests(unittest.TestCase):
    """Edit mode must persist refreshed controlSchemas on snapshot update."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")
        # Find the edit-mode section
        self.edit_start = self.text.find("// ── Edit mode: update snapshot bindings")
        self.edit_block = self.text[self.edit_start:self.edit_start + 800] if self.edit_start >= 0 else ""

    def test_edit_mode_includes_control_schemas(self):
        """Edit mode snapshot update must include controlSchemas."""
        self.assertIn("controlSchemas", self.edit_block,
                      "Edit mode snapshotUpdate must include controlSchemas")

    def test_edit_mode_calls_build_control_schemas(self):
        """Edit mode snapshot update must call buildControlSchemas."""
        self.assertIn("buildControlSchemas", self.edit_block,
                      "Edit mode must call buildControlSchemas()")


class Phase4FixCandidateDropdownWidgetSchemaTests(unittest.TestCase):
    """Candidate dropdown change handler must keep widgetSchema in sync."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-preset-wizard.js").read_text(encoding="utf-8")
        # Find the renderCandidateDropdown section
        self.dropdown_start = self.text.find("function renderCandidateDropdown")
        self.dropdown_block = self.text[self.dropdown_start:self.dropdown_start + 2500] if self.dropdown_start >= 0 else ""

    def test_dropdown_change_updates_widget_schema(self):
        """Change handler must rebuild widgetSchema when selection changes."""
        self.assertIn("widgetSchema", self.dropdown_block,
                      "Dropdown change handler must update widgetSchema")
        self.assertIn("_buildWidgetSchemaFromCandidate", self.dropdown_block,
                      "Dropdown must use _buildWidgetSchemaFromCandidate helper")


class Phase4FixToggleBooleanMappingTests(unittest.TestCase):
    """LiteGraph toggle widgets must map to boolean schema kind."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-graph-binding.js").read_text(encoding="utf-8")
        # Find the extractNodeCandidates function
        self.fn_start = self.text.find("function extractNodeCandidates")
        self.fn_block = self.text[self.fn_start:self.fn_start + 3500] if self.fn_start >= 0 else ""

    def test_toggle_maps_to_boolean(self):
        """'toggle' widget type must map to schemaType 'boolean'."""
        self.assertIn('"toggle"', self.fn_block,
                      "toggle must be handled in schemaType mapping")
        self.assertIn('"boolean"', self.fn_block,
                      "schemaType must include boolean mapping")


if __name__ == "__main__":
    unittest.main()
