"""Phase 9 — Results UI and comparison structural tests.

Verifies the public APIs and key surface area of the new JS modules:
- web/testing-results.js (results_tab_render)
- web/testing-ab-slider.js (ab_slot_render)
- web/modal-testing.js (open_testing_modal)
"""
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class _JsModule:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.text = path.read_text(encoding="utf-8") if path.exists() else ""

    def has_export(self, name: str) -> bool:
        return bool(re.search(rf"export\s+(?:function|const|class)\s+{re.escape(name)}\b", self.text))

    def has_function(self, name: str) -> bool:
        return bool(re.search(rf"function\s+{re.escape(name)}\s*\(", self.text))

    def contains(self, s: str) -> bool:
        return s in self.text


class ResultsUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "testing-results.js")
        if not self.m.text:
            self.skipTest("web/testing-results.js missing")

    def test_exports_results_tab_render(self):
        self.assertTrue(self.m.has_export("results_tab_render"))

    def test_has_control_buttons(self):
        for label in ("Pause", "Stop after current", "Stop now", "Resume"):
            with self.subTest(label=label):
                self.assertIn(label, self.m.text)

    def test_has_progress_section(self):
        self.assertIn("progress", self.m.text)

    def test_has_grid_section(self):
        self.assertIn("grid", self.m.text)

    def test_has_comparison_section(self):
        self.assertIn("compare", self.m.text)

    def test_no_framework_imports(self):
        for forbidden in ("from 'react'", 'from "react"', "from 'preact'",
                          "from 'vue'", "from 'svelte'"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.m.text)

    def test_total_uses_total_cells_from_events(self):
        """Total progress count must use experiment.started.total_cells, not terminal sum."""
        self.assertIn("total_cells", self.m.text,
                       "expected total_cells lookup in progress calculation")
        self.assertIn("getTotalCells", self.m.text,
                       "expected getTotalCells helper for accurate total count")

    def test_asset_id_in_selection(self):
        """Selection entries must include asset_id for A/B URL resolution."""
        self.assertIn("asset_id", self.m.text,
                       "expected asset_id field in selection entries")
        self.assertIn("primary_asset_id", self.m.text,
                       "expected primary_asset_id fallback in getAssetId")

    def test_ab_guards_missing_image(self):
        """A/B comparison must NOT render slider when image_url missing (no asset or output path)."""
        text = self.m.text
        self.assertIn('"One or both cells have no image yet', text,
                       "expected guard message when image_url missing")
        self.assertIn("!a.image_url || !b.image_url", text,
                       "expected guard against missing image_url")

    def test_ab_urls_use_image_url(self):
        """A/B comparison URLs must use image_url (pre-resolved from asset_id or output_path)."""
        text = self.m.text
        # After the guard, URLs use image_url which is pre-resolved
        self.assertIn("a.image_url", text,
                       "expected image_url for A src")

    def test_fullscreen_guards_missing_image(self):
        """Fullscreen viewer must guard against missing image_url."""
        text = self.m.text
        self.assertIn("selection[0].image_url && selection[1].image_url", text,
                       "expected fullscreen guard for both image_urls")

    def test_checkpoint_cards_have_detail(self):
        """Worker progress cards must show cell counts per checkpoint."""
        self.assertIn("testing-results-checkpoint-cells", self.m.text,
                       "expected cell count span in checkpoint cards")
        self.assertIn("cellByCk", self.m.text,
                       "expected per-checkpoint cell counting")

    def test_t_thumbnail_shows_img_when_asset_id(self):
        """Cell cards must show img thumbnail when asset_id is available."""
        self.assertIn("testing-results-cell-img", self.m.text,
                       "expected img element for cell thumbnails when asset_id present")

    def test_selection_cap_remains_2(self):
        """Selection limit must stay at 2."""
        self.assertIn("SELECTION_LIMIT = 2", self.m.text)

    def test_resolve_cell_image_url_function(self):
        """Cell cards must use resolveCellImageUrl for image URL resolution including output_paths."""
        self.assertTrue(self.m.has_function("resolveCellImageUrl"),
                        "expected resolveCellImageUrl helper function")

    def test_cell_thumbnail_uses_image_url(self):
        """Cell cards must show img src from resolveCellImageUrl, not just assetId."""
        text = self.m.text
        self.assertIn("resolveCellImageUrl", text,
                       "expected resolveCellImageUrl call in renderCellCard")

    def test_output_path_fallback_in_url_resolution(self):
        """resolveCellImageUrl must fall back to output_paths array when no asset IDs present."""
        text = self.m.text
        self.assertIn("output_paths", text,
                       "expected output_paths array fallback in resolveCellImageUrl")
        self.assertIn("output_path", text,
                       "expected output_path string fallback in resolveCellImageUrl")

    def test_studio_outputs_route_in_resolve(self):
        """resolveCellImageUrl must use /studio/outputs/ route for output_path based URLs."""
        text = self.m.text
        self.assertIn("/studio/outputs/", text,
                       "expected /studio/outputs/ route for output_path images")

    def test_selection_includes_image_url(self):
        """Cell selection entries must include pre-resolved image_url for comparison workspace."""
        text = self.m.text
        self.assertIn("image_url: imageUrl", text,
                       "expected image_url in selection entries")

    def test_cell_thumbnail_shows_placeholder_when_no_image(self):
        """Cell cards must show placeholder when neither asset_id nor output_path is available."""
        text = self.m.text
        self.assertIn("testing-results-cell-thumb-placeholder", text,
                       "expected placeholder element when no image source available")


class ABSliderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "testing-ab-slider.js")
        if not self.m.text:
            self.skipTest("web/testing-ab-slider.js missing")

    def test_exports_ab_slot_render(self):
        self.assertTrue(self.m.has_export("ab_slot_render"))

    def test_selection_limit_is_2(self):
        self.assertIn("SELECTION_LIMIT = 2", self.m.text)

    def test_zero_selected_text(self):
        self.assertIn("Right-click two images to compare them here", self.m.text)

    def test_one_selected_text(self):
        self.assertIn("Right-click a second image to compare", self.m.text)


class ModalShellTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "modal-testing.js")
        if not self.m.text:
            self.skipTest("web/modal-testing.js missing")

    def test_exports_open_testing_modal(self):
        self.assertTrue(self.m.has_export("open_testing_modal"))

    def test_three_tabs(self):
        for tab in ("Dashboard", "Setup", "Profiles", "Results", "History", "Settings"):
            with self.subTest(tab=tab):
                self.assertIn(tab, self.m.text)

    def test_imports_comfyui_app(self):
        # Should import from ../../scripts/app.js for sidebar registration
        self.assertIn('from "../../scripts/app.js"', self.m.text)




class ShellIntegrationDiagnosticsTests(unittest.TestCase):
    """Failing structural tests: diagnostics keys that belong in modal-testing.js.

    These assertions will fail until the new frontend integration (Task 2–4)
    adds shared diagnostics tracking to modal-testing.js.
    """

    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "modal-testing.js")
        if not self.m.text:
            self.skipTest("web/modal-testing.js missing")

    def test_diagnostics_last_frontend_error_key(self):
        """Results-related diagnostic key lastFrontendError must exist."""
        self.assertIn(
            "lastFrontendError",
            self.m.text,
            "Expected lastFrontendError diagnostic key in modal-testing.js",
        )

    def test_diagnostics_supports_frontend_version_or_source_hash(self):
        """Diagnostics must record frontendVersion or sourceHash for cache busting."""
        self.assertTrue(
            "frontendVersion" in self.m.text or "sourceHash" in self.m.text,
            "Expected frontendVersion or sourceHash in modal-testing.js diagnostics",
        )


# ---------------------------------------------------------------------------
# Visual redesign: three-layer hierarchy and card density
# ---------------------------------------------------------------------------

class ResultsVisualLayersTests(unittest.TestCase):
    """Results must have three visually distinct layers."""

    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "testing-results.js")
        if not self.m.text:
            self.skipTest("web/testing-results.js missing")

    def test_controls_totals_layer_marker(self):
        """Results must have a command-bar section class."""
        self.assertIn(
            "testing-results-command-bar",
            self.m.text,
            "Expected testing-results-command-bar for the controls+totals layer",
        )

    def test_active_progress_layer_marker(self):
        """Results must have a progress/checkpoints section class."""
        self.assertIn(
            "testing-results-progress",
            self.m.text,
            "Expected testing-results-progress for the active workers layer",
        )

    def test_completed_grid_layer_marker(self):
        """Results must have a completed grid section class."""
        self.assertIn(
            "testing-results-grid",
            self.m.text,
            "Expected testing-results-grid for the completed results layer",
        )

    def test_layer_distinct_classes(self):
        """Each layer must have a unique data-section marker."""
        self.assertIn('"data-section": "command-bar"', self.m.text)
        self.assertIn('"data-section": "summary"', self.m.text)
        self.assertIn('"data-section": "progress"', self.m.text)
        self.assertIn('"data-section": "grid"', self.m.text)


class ResultCardMetadataTests(unittest.TestCase):
    """Result cards must show limited metadata on the card face."""

    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "testing-results.js")
        if not self.m.text:
            self.skipTest("web/testing-results.js missing")

    def test_card_shows_model_short_name(self):
        """Result cards must display model short name."""
        self.assertIn(
            "testing-results-cell-model",
            self.m.text,
            "Expected testing-results-cell-model for model short name on card",
        )

    def test_card_shows_runtime(self):
        """Result cards must display runtime."""
        self.assertIn(
            "testing-results-cell-runtime",
            self.m.text,
            "Expected testing-results-cell-runtime for run duration on card",
        )

    def test_card_shows_attempt_badge(self):
        """Result cards must display an attempt badge."""
        self.assertIn(
            "testing-results-cell-attempt",
            self.m.text,
            "Expected testing-results-cell-attempt for attempt number badge",
        )

    def test_card_keeps_thumbnail_seed_prompt(self):
        """Result cards must keep existing thumbnail, seed, and prompt fields."""
        self.assertIn("testing-results-cell-thumb", self.m.text)
        self.assertIn("testing-results-cell-seed", self.m.text)
        self.assertIn("testing-results-cell-prompt", self.m.text)


class ControlBarSemanticsTests(unittest.TestCase):
    """Control bar buttons must have distinct styling hooks."""

    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "testing-results.js")
        if not self.m.text:
            self.skipTest("web/testing-results.js missing")

    def test_pause_has_secondary_amber_styling(self):
        """Pause button must have secondary styling hook."""
        self.assertIn(
            "testing-results-btn-pause",
            self.m.text,
            "Expected testing-results-btn-pause for pause button styling",
        )

    def test_resume_has_primary_accent_styling(self):
        """Resume button must have primary styling hook."""
        self.assertIn(
            "testing-results-btn-resume",
            self.m.text,
            "Expected testing-results-btn-resume for resume button styling",
        )

    def test_stop_now_has_destructive_styling(self):
        """Stop now button must have destructive styling hook."""
        self.assertIn(
            "testing-results-btn-stop-now",
            self.m.text,
            "Expected testing-results-btn-stop-now for destructive stop styling",
        )

    def test_stop_after_current_has_amber_outlined(self):
        """Stop after current must have amber outlined styling hook."""
        self.assertIn(
            "testing-results-btn-stop-after",
            self.m.text,
            "Expected testing-results-btn-stop-after for stop-after styling",
        )


# ---------------------------------------------------------------------------
# Results Clarity: command-bar groups, summary zone, gallery, workspace
# ---------------------------------------------------------------------------

class ResultsClarityCommandBarTests(unittest.TestCase):
    """Results command bar must have structured groups."""

    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "testing-results.js")
        if not self.m.text:
            self.skipTest("web/testing-results.js missing")

    def test_results_contains_command_bar_section(self):
        """Results must have a command-bar section with data-section marker."""
        self.assertIn(
            '"data-section": "command-bar"',
            self.m.text,
            "Expected command-bar section with data-section marker",
        )

    def test_results_contains_command_main_group(self):
        """Results must have a testing-results-command-main group."""
        self.assertIn(
            "testing-results-command-main",
            self.m.text,
            "Expected testing-results-command-main for routine controls",
        )

    def test_results_contains_command_danger_group(self):
        """Results must have a testing-results-command-danger group."""
        self.assertIn(
            "testing-results-command-danger",
            self.m.text,
            "Expected testing-results-command-danger for destructive controls",
        )


class ResultsClaritySummaryTests(unittest.TestCase):
    """Results must have a dedicated run summary zone."""

    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "testing-results.js")
        if not self.m.text:
            self.skipTest("web/testing-results.js missing")

    def test_results_contains_summary_section(self):
        """Results must have a summary section with data-section marker."""
        self.assertIn(
            '"data-section": "summary"',
            self.m.text,
            "Expected summary section with data-section marker",
        )

    def test_results_contains_summary_card(self):
        """Results must have a testing-results-summary-card class."""
        self.assertIn(
            "testing-results-summary-card",
            self.m.text,
            "Expected testing-results-summary-card for run status summary",
        )


class ResultsClarityGalleryWorkspaceTests(unittest.TestCase):
    """Results must have a gallery and comparison workspace."""

    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "testing-results.js")
        if not self.m.text:
            self.skipTest("web/testing-results.js missing")

    def test_results_contains_gallery_marker(self):
        """Results must have a testing-results-gallery class."""
        self.assertIn(
            "testing-results-gallery",
            self.m.text,
            "Expected testing-results-gallery for the results gallery",
        )

    def test_results_contains_compare_workspace_marker(self):
        """Results must have a testing-results-compare-workspace class."""
        self.assertIn(
            "testing-results-compare-workspace",
            self.m.text,
            "Expected testing-results-compare-workspace for the comparison area",
        )

    def test_results_contains_empty_state_marker(self):
        """Results must have a testing-results-empty-state class."""
        self.assertIn(
            "testing-results-empty-state",
            self.m.text,
            "Expected testing-results-empty-state for guided empty states",
        )


# ---------------------------------------------------------------------------
# Progressive Clarity: summary emphasis, routine vs danger command groups
# ---------------------------------------------------------------------------

class ResultsProgressiveClarityTests(unittest.TestCase):
    """Results summary primary and command-routine markers."""

    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "testing-results.js")
        if not self.m.text:
            self.skipTest("web/testing-results.js missing")

    def test_results_uses_emphasized_summary_primary(self):
        """Results must have testing-results-summary-primary for dominant value."""
        self.assertIn(
            "testing-results-summary-primary",
            self.m.text,
            "Expected testing-results-summary-primary for emphasized run state",
        )

    def test_results_uses_command_routine_marker(self):
        """Results must have testing-results-command-routine for routine controls."""
        self.assertIn(
            "testing-results-command-routine",
            self.m.text,
            "Expected testing-results-command-routine for routine control group",
        )


# ---------------------------------------------------------------------------
# Results grouping adapter: workflow/model-stack/lora dimensions
# and technical view fallback.
# ---------------------------------------------------------------------------

class ResultsGroupingAdapterTests(unittest.TestCase):
    """Results grouping adapter markers for workflow / model stack / lora
    dimensions and technical view fallback."""

    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "testing-results.js")
        if not self.m.text:
            self.skipTest("web/testing-results.js missing")

    def test_grouping_adapter_marker(self):
        """Results must reference a grouping adapter for dimension-based grouping."""
        self.assertIn(
            "testing-results-grouping-adapter",
            self.m.text,
            "Expected testing-results-grouping-adapter for dimension-based grouping",
        )

    def test_workflow_dimension_marker(self):
        """Grouping adapter must support workflow dimension."""
        text = self.m.text
        has_workflow_dim = (
            "group-by-workflow" in text
            or "workflow-dim" in text
            or "workflow_group" in text
        )
        self.assertTrue(
            has_workflow_dim,
            "Expected workflow grouping dimension (group-by-workflow / workflow_dim) in testing-results.js",
        )

    def test_model_stack_dimension_marker(self):
        """Grouping adapter must support model stack dimension."""
        text = self.m.text
        has_model_stack_dim = (
            "group-by-model-stack" in text
            or "model-stack-dim" in text
            or "model_stack_group" in text
        )
        self.assertTrue(
            has_model_stack_dim,
            "Expected model stack grouping dimension (group-by-model-stack / model_stack_dim) in testing-results.js",
        )

    def test_lora_dimension_marker(self):
        """Grouping adapter must support LoRA dimension."""
        text = self.m.text
        has_lora_dim = (
            "group-by-lora" in text
            or "lora-dim" in text
            or "lora_group" in text
        )
        self.assertTrue(
            has_lora_dim,
            "Expected LoRA grouping dimension (group-by-lora / lora_dim) in testing-results.js",
        )

    def test_technical_view_fallback(self):
        """Results must have a technical view fallback marker."""
        text = self.m.text
        has_tech_fallback = (
            "testing-results-technical" in text
            or "technical-view" in text
            or "tech-fallback" in text
        )
        self.assertTrue(
            has_tech_fallback,
            "Expected technical view fallback (testing-results-technical / technical-view) in testing-results.js",
        )


if __name__ == "__main__":
    unittest.main()
