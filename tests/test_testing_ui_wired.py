"""Structural AST tests for the testing-suite JS modules.

These tests verify the public API of each web/*.js file matches what
the routes in __init__.py and the modal shell expect, without
requiring a browser DOM.
"""
import os
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web"


class _JsTestBase(unittest.TestCase):
    def _read(self, name: str) -> str:
        path = WEB / name
        if not path.exists():
            raise AssertionError(f"web/{name} missing")
        return path.read_text(encoding="utf-8")


class TestingShellTests(_JsTestBase):
    def test_modal_testing_exports_open_testing_modal(self):
        text = self._read("modal-testing.js")
        self.assertIn("export function open_testing_modal", text)
        self.assertIn("open_testing_modal", text)
        # The shell must register a sidebar entry point (registerSidebarTab).
        self.assertIn("registerSidebarTab", text)

    # ── Task 1: failing tests for new frontend integration ──────────────────

    def test_uses_app_register_extension(self):
        """Fails until modal-testing.js switches to app.registerExtension()."""
        text = self._read("modal-testing.js")
        self.assertIn(
            "app.registerExtension(",
            text,
            "modal-testing.js must use app.registerExtension for the new integration",
        )

    def test_extension_name_comfymodal_testing_suite(self):
        """Fails until stable extension name 'comfymodal.testing-suite' is present."""
        text = self._read("modal-testing.js")
        self.assertIn(
            "comfymodal.testing-suite",
            text,
            "Expected stable extension name 'comfymodal.testing-suite'",
        )


class TestingSetupTests(_JsTestBase):
    def test_setup_exports_render(self):
        text = self._read("testing-setup.js")
        self.assertIn("export function setup_tab_render", text)
        # The setup must call the real backend routes.
        self.assertIn("experiments/compile", text)
        self.assertIn("experiments", text)
        self.assertIn("comparison/profiles", text)
        self.assertIn("presets/prompts", text)
        self.assertIn("presets/images", text)
        # All 5 spec sections per the five-section restructure.
        for section in ["Generation Type", "What Changes?", "Workflows", "Test Values", "Review & Run"]:
            self.assertIn(section, text, f"missing section label: {section}")

    def test_pick_main_triple_object_slots(self):
        """pickMainTriple must handle profile.slots as object dict."""
        text = self._read("testing-setup.js")
        self.assertIn("Object.keys(rawSlots)", text,
                       "expected Object.keys iteration for dict-format slots")
        self.assertIn("rawSlots[key]", text,
                       "expected bracket-access for dict slot values")

    def test_validate_spec_function_present(self):
        """validateSpec must be defined for pre-compile validation."""
        text = self._read("testing-setup.js")
        self.assertIn("function validateSpec", text)
        self.assertIn("file path is required", text)
        self.assertIn("Select at least one workflow profile", text)

    def test_multi_lora_strength_csv_fields_wired(self):
        """LoRA rows must have wired model_strength and clip_strength CSV editors."""
        text = self._read("testing-setup.js")
        self.assertIn("model_strength", text)
        self.assertIn("clip_strength", text)
        self.assertIn("onEntryChange", text,
                       "expected model_strength/clip_strength input wiring via onEntryChange")

    def test_multi_lora_per_entry_editor(self):
        """LoRA selections must support multiple per-index entries with add/remove."""
        text = self._read("testing-setup.js")
        self.assertIn("makeLoraEntryRow", text,
                       "expected per-index entry row factory")
        self.assertIn("+ Add LoRA entry", text,
                       "expected add-entry button")
        self.assertIn("testing-setup-lora-entry-remove", text,
                       "expected remove button per entry")
        self.assertIn("updatedLoras.splice(idx", text,
                       "expected splice removal of lora entries")

    def test_no_lora_toggle_present(self):
        """Explicit No LoRA toggle must exist as selection entry."""
        text = self._read("testing-setup.js")
        self.assertIn("L_no", text)


class TestingResultsTests(_JsTestBase):
    def test_results_exports_render_and_polls(self):
        text = self._read("testing-results.js")
        self.assertIn("export function results_tab_render", text)
        # The results must call the real backend routes.
        self.assertIn("/comfymodal/experiments/", text)
        self.assertIn("/events", text)
        # The control bar must call pause/stop/resume/run-missing routes.
        for verb in ["pause", "stop-after-current", "stop-now", "resume", "run-missing"]:
            self.assertIn(verb, text, f"missing control verb: {verb}")
        # A/B comparison slot must use the slider module.
        self.assertIn("testing-ab-slider.js", text)
        # Selection model: two-selection cap.
        self.assertIn("SELECTION_LIMIT = 2", text)

    def test_total_count_uses_experiment_started_total_cells(self):
        """Progress total must use total_cells from events, not terminal sum."""
        text = self._read("testing-results.js")
        self.assertIn("getTotalCells", text)
        self.assertIn("experiment.started", text)
        self.assertIn("total_cells", text)

    def test_ab_guards_missing_asset_id_no_cell_key_fallback(self):
        """A/B comparison must guard missing asset_id, never fall back to cell_key."""
        text = self._read("testing-results.js")
        self.assertIn("!a.asset_id || !b.asset_id", text,
                       "expected guard when either asset_id missing")
        self.assertIn("wait for completion", text,
                       "expected explanatory message for missing assets")
        # Must NOT fall back to cell_key in URL construction
        self.assertNotIn('"|| a.cell_key"', text,
                          "no cell_key fallback for A src")
        self.assertNotIn('"|| b.cell_key"', text,
                          "no cell_key fallback for B src")

    def test_fullscreen_guards_missing_asset_id(self):
        """Fullscreen must require both asset_ids."""
        text = self._read("testing-results.js")
        self.assertIn("selection[0].asset_id && selection[1].asset_id", text,
                       "expected fullscreen guard for both asset_ids")

    def test_thumbnail_asset_urls_use_asset_id(self):
        """Cell card thumbnails must use /assets/{assetId} URL."""
        text = self._read("testing-results.js")
        self.assertIn("/assets/", text)
        self.assertIn("testing-results-cell-img", text)

    def test_worker_progress_cards_present(self):
        """Checkpoint list must render progress cards per checkpoint."""
        text = self._read("testing-results.js")
        self.assertIn("testing-results-checkpoint-card", text)
        self.assertIn("testing-results-checkpoint-cells", text)
        self.assertIn("checkpoint-list", text)


class TestingAbSliderTests(_JsTestBase):
    def test_ab_slider_exports(self):
        text = self._read("testing-ab-slider.js")
        self.assertIn("export function ab_slider_render", text)
        self.assertIn("export function ab_slider_open_fullscreen", text)
        # Fullscreen must support zoom, pan, swap, fit, close, actual.
        for feature in ["zoomIn", "zoomOut", "swap", "fit", "actual", "close"]:
            self.assertIn(feature, text, f"missing fullscreen feature: {feature}")


class TestingSettingsTests(_JsTestBase):
    def test_settings_exports_render(self):
        text = self._read("testing-settings.js")
        self.assertIn("export function settings_tab_render", text)
        # The settings tab must bridge to the legacy modal-settings.js
        # via the comfymodal.open-section custom event.
        self.assertIn("comfymodal.open-section", text)
        self.assertIn("open_comfymodal_settings", text)
        for section in [
            "credentials", "deployment", "gpu", "workspace", "models",
            "sync", "output", "tokens", "logs",
        ]:
            self.assertIn(section, text, f"missing settings section: {section}")


class ModalNodeTests(_JsTestBase):
    """Verify the modal-node.js sidebar integration has not regressed."""

    def test_modal_node_patches_api(self):
        text = self._read("modal-node.js")
        # modal-node.js patches the comfyui fetch to route prompt
        # requests to /comfymodal/prompt via MODAL_PREFIX.
        self.assertIn("MODAL_PREFIX", text)
        self.assertIn("/prompt", text)
        self.assertIn("install", text)


class ModalSettingsTests(_JsTestBase):
    """Verify the legacy modal-settings.js still has the sections
    required by the new testing modal's settings tab."""

    def test_legacy_sections_present(self):
        text = self._read("modal-settings.js")
        for needle in [
            "auth", "deploy", "gpu", "workspace", "models",
            "sync", "output", "tokens", "logs",
        ]:
            self.assertTrue(
                needle in text.lower(),
                f"legacy modal-settings.js missing section: {needle}",
            )


# ---------------------------------------------------------------------------
# Visual redesign tests
# ---------------------------------------------------------------------------

class VisualRedesignTests(_JsTestBase):
    """Structural tests for the Modal GPU visual redesign."""

    def test_canonical_modal_gpu_naming(self):
        """modal-testing.js must display 'Modal GPU' as the header title."""
        text = self._read("modal-testing.js")
        self.assertIn("Modal GPU", text,
                       "Expected 'Modal GPU' visible header title")

    def test_dashboard_new_experiment_cta(self):
        """testing-dashboard.js must have 'New Experiment' as primary CTA."""
        text = self._read("testing-dashboard.js")
        self.assertIn("New Experiment", text,
                       "Expected 'New Experiment' primary CTA in dashboard")

    def test_dashboard_hero_marker(self):
        """testing-dashboard.js must use comfymodal-hero class."""
        text = self._read("testing-dashboard.js")
        self.assertIn("comfymodal-hero", text,
                       "Expected comfymodal-hero for blocked/deploy state")

    def test_dashboard_removes_deploy_strip(self):
        """testing-dashboard.js must NOT use comfymodal-deploy-strip."""
        text = self._read("testing-dashboard.js")
        self.assertNotIn("comfymodal-deploy-strip", text,
                          "comfymodal-deploy-strip must be removed")

    def test_history_row_class(self):
        """testing-history.js must have testing-history-row class."""
        text = self._read("testing-history.js")
        self.assertIn("testing-history-row", text,
                       "Expected testing-history-row list item class")

    def test_history_metadata_fields(self):
        """testing-history.js must have status, time, and duration markers."""
        text = self._read("testing-history.js")
        self.assertIn("testing-history-status", text)
        self.assertIn("testing-history-time", text)
        self.assertIn("testing-history-duration", text)

    def test_settings_wrapper_hook(self):
        """testing-settings.js must use comfymodal-settings-wrapper."""
        text = self._read("testing-settings.js")
        self.assertIn("comfymodal-settings-wrapper", text,
                       "Expected comfymodal-settings-wrapper class")

    def test_results_three_layers(self):
        """testing-results.js must have data-section for command-bar/summary/progress/grid."""
        text = self._read("testing-results.js")
        self.assertIn('"data-section": "command-bar"', text)
        self.assertIn('"data-section": "summary"', text)
        self.assertIn('"data-section": "progress"', text)
        self.assertIn('"data-section": "grid"', text)


# ---------------------------------------------------------------------------
# Setup + Results Clarity tests
# ---------------------------------------------------------------------------

class SetupClarityUiWiredTests(_JsTestBase):
    """Setup navigation and structure clarity hooks."""

    def test_setup_finish_zone_marker(self):
        """testing-setup.js must have testing-setup-finish-zone."""
        text = self._read("testing-setup.js")
        self.assertIn("testing-setup-finish-zone", text)

    def test_setup_field_grid_marker(self):
        """testing-setup.js must have testing-setup-field-grid."""
        text = self._read("testing-setup.js")
        self.assertIn("testing-setup-field-grid", text)


class ResultsClarityUiWiredTests(_JsTestBase):
    """Results operational zone clarity hooks."""

    def test_results_command_bar_section(self):
        """testing-results.js must have command-bar data-section marker."""
        text = self._read("testing-results.js")
        self.assertIn('"data-section": "command-bar"', text)

    def test_results_summary_section(self):
        """testing-results.js must have summary data-section marker."""
        text = self._read("testing-results.js")
        self.assertIn('"data-section": "summary"', text)

    def test_results_command_main_danger_groups(self):
        """testing-results.js must have command-main and command-danger groups."""
        text = self._read("testing-results.js")
        self.assertIn("testing-results-command-main", text)
        self.assertIn("testing-results-command-danger", text)

    def test_results_summary_card(self):
        """testing-results.js must have testing-results-summary-card."""
        text = self._read("testing-results.js")
        self.assertIn("testing-results-summary-card", text)

    def test_results_gallery_marker(self):
        """testing-results.js must have testing-results-gallery."""
        text = self._read("testing-results.js")
        self.assertIn("testing-results-gallery", text)

    def test_results_compare_workspace_marker(self):
        """testing-results.js must have testing-results-compare-workspace."""
        text = self._read("testing-results.js")
        self.assertIn("testing-results-compare-workspace", text)

    def test_results_empty_state_marker(self):
        """testing-results.js must have testing-results-empty-state."""
        text = self._read("testing-results.js")
        self.assertIn("testing-results-empty-state", text)


# ---------------------------------------------------------------------------
# Progressive Clarity tests
# ---------------------------------------------------------------------------

class ProgressiveClarityShellUiWiredTests(_JsTestBase):
    """Shell fixed sizing and header cleanup."""

    def test_shell_fixed_modal_dimensions(self):
        """testing-styles.js must have fixed width/height for modal."""
        text = self._read("testing-styles.js")
        self.assertIn("width: 1200px", text)
        self.assertIn("height: 780px", text)

    def test_shell_no_cloud_subtitle(self):
        """modal-testing.js must not contain cloud subtitle."""
        text = self._read("modal-testing.js")
        self.assertNotIn("Cloud execution and testing", text)


class ProgressiveClarityDashboardUiWiredTests(_JsTestBase):
    """Dashboard emphasis markers."""

    def test_dashboard_primary_actions_group(self):
        """testing-dashboard.js must have testing-dashboard-primary-actions."""
        text = self._read("testing-dashboard.js")
        self.assertIn("testing-dashboard-primary-actions", text)

    def test_dashboard_metric_primary(self):
        """testing-dashboard.js must have testing-dashboard-metric-primary."""
        text = self._read("testing-dashboard.js")
        self.assertIn("testing-dashboard-metric-primary", text)

    def test_dashboard_no_deploy_strip(self):
        """testing-dashboard.js must not have comfymodal-deploy-strip."""
        text = self._read("testing-dashboard.js")
        self.assertNotIn("comfymodal-deploy-strip", text)


class ProgressiveClaritySetupUiWiredTests(_JsTestBase):
    """Setup progressive-collapse markers."""

    def test_setup_collapsible_section(self):
        """testing-setup.js must have testing-setup-section-collapsible and data-collapsed."""
        text = self._read("testing-setup.js")
        self.assertIn("testing-setup-section-collapsible", text)
        self.assertIn("data-collapsed", text)

    def test_setup_advanced_axes(self):
        """testing-setup.js must have testing-setup-advanced-toggle."""
        text = self._read("testing-setup.js")
        self.assertIn("testing-setup-advanced-toggle", text)

class ProgressiveClarityResultsUiWiredTests(_JsTestBase):
    """Results emphasis markers."""

    def test_results_summary_primary(self):
        """testing-results.js must have testing-results-summary-primary."""
        text = self._read("testing-results.js")
        self.assertIn("testing-results-summary-primary", text)

    def test_results_command_routine(self):
        """testing-results.js must have testing-results-command-routine."""
        text = self._read("testing-results.js")
        self.assertIn("testing-results-command-routine", text)


class ProgressiveClarityHistoryUiWiredTests(_JsTestBase):
    """History two-line row markers."""

    def test_history_row_main(self):
        """testing-history.js must have testing-history-row-main."""
        text = self._read("testing-history.js")
        self.assertIn("testing-history-row-main", text)

    def test_history_row_meta(self):
        """testing-history.js must have testing-history-row-meta."""
        text = self._read("testing-history.js")
        self.assertIn("testing-history-row-meta", text)


if __name__ == "__main__":
    unittest.main()
