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


class RetiredTestingModulesContractTests(_JsTestBase):
    """H18 Wave G: the retired legacy testing UI modules are deleted and
    nothing in production references them."""

    RETIRED = [
        "testing-setup.js",
        "testing-profiles.js",
        "testing-results.js",
        "testing-settings.js",
        "testing-ab-slider.js",
        "testing-setup-adapter.js",
        "testing-api.js",
    ]

    def test_retired_files_absent(self):
        for name in self.RETIRED:
            with self.subTest(name=name):
                self.assertFalse((WEB / name).exists(), f"web/{name} must stay deleted")

    def test_no_production_importer(self):
        importers = []
        for path in WEB.glob("*.js"):
            text = path.read_text(encoding="utf-8")
            for name in self.RETIRED:
                if name in text:
                    importers.append(f"{path.name}->{name}")
        self.assertEqual(importers, [], f"Unexpected references to retired modules: {importers}")

    def test_legacy_experiment_surfaces_unreachable(self):
        """No creator/controls notice may render anywhere (modules deleted)."""
        for path in WEB.glob("*.js"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("legacy-experiment-creator-retired", text)
            self.assertNotIn("legacy-experiment-controls-retired", text)


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
    """H18 Wave G: modal-settings.js is the minimal canvas/shared
    compatibility module; the overlay sections are deleted."""

    @staticmethod
    def _code(text: str) -> str:
        return "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("//")
        )

    def test_legacy_overlay_sections_absent(self):
        code = self._code(self._read("modal-settings.js"))
        for needle in [
            "buildPanel", "buildAuthPanel", "loadModels", "renderModelList",
            "startDeployPoll", "checkHealth", "showConfirmDialog",
        ]:
            self.assertNotIn(needle, code, f"retired overlay region must stay deleted: {needle}")

    def test_canvas_compat_surface_present(self):
        text = self._read("modal-settings.js")
        self.assertIn('const STORAGE_KEY_ENABLED = "comfymodal_enabled"', text)
        self.assertIn("window._comfyModalEnabled =", text)
        self.assertIn("syncLegacyGpuConfigOnce();", text)
        self.assertIn("syncLegacyOutputPrefsOnce();", text)


# ---------------------------------------------------------------------------
# Visual redesign tests
# ---------------------------------------------------------------------------

class VisualRedesignTests(_JsTestBase):
    """Structural tests for the Modal GPU visual redesign."""

    def test_canonical_studio_header_naming(self):
        """modal-testing.js / studio-shell.js must display 'Modal GPU' as header."""
        text = self._read("modal-testing.js")
        self.assertIn("Modal GPU", text,
                       "Expected 'Modal GPU' visible header title — "
                       "consistent product name")

    def test_retired_settings_module_deleted(self):
        """H18 Wave G: testing-settings.js stays deleted."""
        self.assertFalse((WEB / "testing-settings.js").exists())

    def test_retired_results_module_deleted(self):
        """H18 Wave G: testing-results.js stays deleted."""
        self.assertFalse((WEB / "testing-results.js").exists())


# ---------------------------------------------------------------------------
# Setup + Results Clarity tests — retired with the modules (Wave G)
# ---------------------------------------------------------------------------

class SetupResultsClarityRetiredTests(_JsTestBase):
    """Legacy clarity hooks died with their modules; shared styles carry
    none of them anymore."""

    def test_no_legacy_clarity_markers_in_shared_styles(self):
        text = self._read("testing-styles.js")
        for marker in [
            "testing-setup-finish-zone",
            "testing-setup-field-grid",
            "testing-results-command-bar",
            "testing-results-summary-card",
            "testing-results-gallery",
            "testing-results-compare-workspace",
            "testing-results-empty-state",
        ]:
            self.assertNotIn(marker, text, f"legacy clarity marker must stay deleted: {marker}")


# ---------------------------------------------------------------------------
# Progressive Clarity tests
# ---------------------------------------------------------------------------

class ProgressiveClarityShellUiWiredTests(_JsTestBase):
    """Shell fixed sizing and header cleanup."""

    def test_shell_fixed_modal_dimensions(self):
        """studio-styles.js must have larger viewport-relative modal dimensions."""
        text = self._read("studio-styles.js")
        self.assertIn("1760px", text)
        self.assertIn("1040px", text)

    def test_shell_no_cloud_subtitle(self):
        """modal-testing.js must not contain cloud subtitle."""
        text = self._read("modal-testing.js")
        self.assertNotIn("Cloud execution and testing", text)


class ProgressiveClarityRetiredUiWiredTests(_JsTestBase):
    """Progressive-clarity markers retired with the legacy modules (Wave G)."""

    def test_retired_modules_deleted(self):
        for name in ["testing-setup.js", "testing-results.js"]:
            self.assertFalse((WEB / name).exists(), f"{name} must stay deleted")

    def test_no_legacy_progressive_markers_in_shared_styles(self):
        text = self._read("testing-styles.js")
        self.assertNotIn("testing-setup-section-collapsible", text)
        self.assertNotIn("testing-setup-advanced-toggle", text)
        self.assertNotIn("testing-results-summary-primary", text)
        self.assertNotIn("testing-results-command-routine", text)


# ---------------------------------------------------------------------------
# Studio Shell Wired Tests (Task 1 — Studio shell redesign API contract)
# ---------------------------------------------------------------------------

class StudioShellContextTests(_JsTestBase):
    """Shell context must include actions and comfyApi for pages."""

    def test_modal_testing_passes_comfy_api_in_context(self):
        """modal-testing.js must pass comfyApi in the shell context."""
        text = self._read("modal-testing.js")
        self.assertIn("comfyApi", text,
                       "Expected comfyApi reference in modal-testing.js context")

    def test_modal_testing_does_not_pass_mount_legacy_tab(self):
        """H14 Wave E: the shell context no longer carries a legacy tab mounter."""
        text = self._read("modal-testing.js")
        self.assertNotIn(
            "mountLegacyTab", text,
            "mountLegacyTab must be retired from modal-testing.js (Wave E)",
        )

    def test_studio_shell_has_data_section_handling(self):
        """modal-testing.js must handle comfymodal.open-section with real section targets."""
        text = self._read("modal-testing.js")
        self.assertIn("data-section", text,
                       "Expected data-section attribute handling in modal-testing.js")


class StudioShellWiredTests(_JsTestBase):
    """Studio shell module export/API contract tests."""

    def test_studio_shell_exports_mount_studio_shell(self):
        """studio-shell.js must export mountStudioShell function."""
        text = self._read("studio-shell.js")
        self.assertIn("export function mountStudioShell", text)

    def test_studio_shell_returns_shell_api(self):
        """studio-shell.js must return an object with destroy and setPage."""
        text = self._read("studio-shell.js")
        self.assertIn("destroy", text)
        self.assertIn("setPage", text)

    def test_modal_testing_imports_studio_shell(self):
        """modal-testing.js must import from studio-shell.js."""
        text = self._read("modal-testing.js")
        self.assertIn("./studio-shell.js", text)

    def test_modal_testing_imports_studio_styles(self):
        """modal-testing.js must import from studio-styles.js."""
        text = self._read("modal-testing.js")
        self.assertIn("./studio-styles.js", text)

    # ── Feature registry content ────────────────────────────────────────

    def test_feature_registry_has_txt2img(self):
        """studio-feature-registry.js must define a txt2img feature."""
        text = self._read("studio-feature-registry.js")
        self.assertIn("txt2img", text)

    def test_feature_registry_has_object_remove(self):
        """studio-feature-registry.js must define an object_remove feature."""
        text = self._read("studio-feature-registry.js")
        self.assertIn("object_remove", text)

    def test_feature_registry_has_object_replace(self):
        """studio-feature-registry.js must define an object_replace feature."""
        text = self._read("studio-feature-registry.js")
        self.assertIn("object_replace", text)

    def test_feature_registry_exports_FEATURE_SPECS(self):
        """studio-feature-registry.js must export FEATURE_SPECS array."""
        text = self._read("studio-feature-registry.js")
        self.assertIn("export const FEATURE_SPECS", text)

    # ── No separate Test Axes page/list ─────────────────────────────────

    def test_no_separate_test_axes_list_in_modules(self):
        """New Studio modules must NOT define a separate 'Test Axes' list/page.

        Experiment mode is an overlay on Playground controls, not a separate page.
        """
        text = self._read("studio-shell.js")
        self.assertNotIn("Test Axes", text)


# ---------------------------------------------------------------------------
# Studio Preset Execution Wired Tests
# ---------------------------------------------------------------------------

class StudioPresetExecutionUiWiredTests(_JsTestBase):
    """Frontend wiring tests for Studio preset execution."""

    def test_studio_backend_api_exports_run_studio_preset(self):
        """studio-backend-api.js must export runStudioPreset helper."""
        text = self._read("studio-backend-api.js")
        self.assertIn("export async function runStudioPreset", text)

    def test_studio_backend_exports_run_studio_experiment_retired(self):
        """H18 Wave G: the dead legacy-creator API helper is deleted
        (zero importers since Wave D; POST /studio/experiment is retired)."""
        text = self._read("studio-backend-api.js")
        self.assertNotIn(
            "export async function runStudioExperiment",
            text,
            "runStudioExperiment helper must stay deleted (Wave G)",
        )

    def test_studio_backend_api_exports_get_studio_run_status(self):
        """studio-backend-api.js must export getStudioRunStatus helper."""
        text = self._read("studio-backend-api.js")
        self.assertIn("export async function getStudioRunStatus", text)

    def test_playground_imports_run_studio_preset(self):
        """studio-playground.js must import runStudioPreset from api module."""
        text = self._read("studio-playground.js")
        self.assertIn("runStudioPreset", text)
        self.assertIn("./studio-backend-api.js", text)

    def test_playground_imports_experiment_run_helpers(self):
        """studio-playground.js must import run helpers from ./studio-playground-run.js."""
        text = self._read("studio-playground.js")
        self.assertIn("./studio-playground-run.js", text,
                       "Expected import from ./studio-playground-run.js")
        for name in ["createPlaygroundRunController", "projectRunToLegacy", "LEGACY_TERMINAL_STATUSES"]:
            self.assertIn(name, text,
                          f"Expected {name} import in studio-playground.js")

    def test_playground_run_button_uses_run_studio_preset(self):
        """The Run button handler must call runStudioPreset."""
        text = self._read("studio-playground.js")
        self.assertIn("runStudioPreset(", text)

    def test_playground_run_button_disabled_no_preset_message(self):
        """Disabled Run reason must show 'Select or create a Backend Preset.'"""
        text = self._read("studio-playground.js")
        self.assertIn("Select or create a Backend Preset.", text)

    def test_playground_run_button_shows_server_derived_reason(self):
        """Disabled Run must display server-derived disabledReason from preset."""
        text = self._read("studio-playground.js")
        self.assertIn("disabledReason", text)
        self.assertIn("This preset is archived.", text)

    def test_playground_run_state_running_shown(self):
        """Run button must show 'Running...' state during submission."""
        text = self._read("studio-playground.js")
        self.assertIn("Running\\u2026", text)

    def test_playground_run_state_submitted_view_history(self):
        """Submitted run state must show 'View in History' link."""
        text = self._read("studio-playground.js")
        self.assertIn("View in History", text)

    def test_playground_run_state_error_dismiss(self):
        """Error run state must have Dismiss button."""
        text = self._read("studio-playground.js")
        self.assertIn("Run Failed", text)

    def test_experiment_mode_imports_run_studio_experiment(self):
        """H-WAVE D: the legacy runStudioExperiment import is retired; the
        modern V2 API module remains imported."""
        text = self._read("studio-experiment-mode.js")
        self.assertNotIn(
            "runStudioExperiment",
            text,
            "runStudioExperiment must be retired in Wave D",
        )
        self.assertIn("./studio-backend-api.js", text)

    def test_experiment_mode_uses_run_studio_experiment(self):
        """H-WAVE D: no legacy creator call remains anywhere."""
        text = self._read("studio-experiment-mode.js")
        self.assertNotIn(
            "runStudioExperiment(",
            text,
            "runStudioExperiment( must be retired in Wave D",
        )

    def test_experiment_mode_can_run_function(self):
        """Experiment mode must export canRunExperiment and getExperimentDisabledReason;
        the legacy executeExperimentRun export is retired (H-WAVE D)."""
        text = self._read("studio-experiment-mode.js")
        self.assertIn("export function canRunExperiment", text)
        self.assertIn("export function getExperimentDisabledReason", text)
        self.assertNotIn(
            "export async function executeExperimentRun",
            text,
            "executeExperimentRun must be retired in Wave D",
        )

    def test_experiment_compare_presets_uses_only_compare_ids(self):
        """executeExperimentRun must iterate compare preset IDs only."""
        text = self._read("studio-experiment-mode.js")
        self.assertIn("compareBackendIds", text)

    def test_experiment_compare_presets_disabled_reason_shown(self):
        """Disabled/non-runnable presets must show reason in compare list."""
        text = self._read("studio-experiment-mode.js")
        self.assertIn("Not runnable", text)
        self.assertIn("Not compatible with", text)
        self.assertIn("Archived", text)

    def test_experiment_disabled_presets_not_submitted(self):
        """Disabled presets must be disabled in the compare list."""
        text = self._read("studio-experiment-mode.js")
        self.assertIn("cb.disabled = true", text)

    def test_backend_detail_checklist_and_status_banner(self):
        """Preset detail must show status banner and runnable checklist."""
        text = self._read("studio-backend-presets.js")
        self.assertIn("Runnable Checklist", text)
        self.assertIn("Snapshot linked", text)
        self.assertIn("Compatible features assigned", text)
        self.assertIn("API prompt available", text)

    def test_backend_detail_checklist_semantic_list(self):
        """Runnable Checklist must use semantic <ul> with <li> items."""
        text = self._read("studio-backend-presets.js")
        self.assertIn('el("ul"', text,
                       "Expected el('ul', ...) element for Runnable Checklist")
        self.assertIn('el("li"', text,
                       "Expected el('li', ...) items inside Runnable Checklist")

    def test_backend_detail_checklist_tokens(self):
        """Checklist status colors use CSS variables, not hardcoded hex."""
        text = self._read("studio-backend-presets.js")
        # Must reference CSS variables in checklist status styling
        self.assertIn("var(--color-success", text)
        self.assertIn("var(--color-danger", text)

    def test_backend_detail_uses_status_banner(self):
        """Preset detail must have status-banner style with variant classes."""
        text = self._read("studio-backend-presets.js")
        self.assertIn("status-banner", text)
        self.assertIn('" runnable"', text)
        self.assertIn('" archived"', text)
        self.assertIn('" not-runnable"', text)
        self.assertIn("Not Runnable", text)

    def test_backend_preset_detail_css_classes_in_styles(self):
        """studio-styles.js must define status banner and checklist CSS classes."""
        text = self._read("studio-styles.js")
        self.assertIn("comfymodal-studio-status-banner.runnable", text)
        self.assertIn("comfymodal-studio-status-banner.archived", text)
        self.assertIn("comfymodal-studio-checklist", text)
        self.assertIn("comfymodal-studio-checklist-item", text)

    def test_backend_capability_no_hardcoded_hex(self):
        """Capability summary uses CSS var() tokens, not bare status hex colors."""
        text = self._read("studio-backend-presets.js")
        # These ternary patterns appear in hardcoded capability summary rows.
        # After tokenization they become var(--color-... so the bare ? "hex" vanishes.
        self.assertNotIn('? "#4ade80"', text,
                          "Replace ? '#4ade80' with var(--color-success... in capability summary")
        self.assertNotIn('? "#f87171"', text,
                          "Replace ? '#f87171' with var(--color-danger... in capability summary")
        self.assertNotIn('? "#fbbf24"', text,
                          "Replace ? '#fbbf24' with var(--color-warning... in capability summary")
        self.assertNotIn('color:#4ade80', text,
                          "Replace color:#4ade80 with var(--color-success... in optional controls")
        # Must reference all three semantic tokens somewhere
        self.assertIn("var(--color-warning", text,
                       "Expected var(--color-warning reference in capability summary status")

    def test_graph_binding_cleanup_guard(self):
        """graph-binding cleanup must have reentrancy guard and hint removal."""
        text = self._read("studio-graph-binding.js")
        self.assertIn("_cleanupCalled", text)
        self.assertIn("_removeCaptureHints", text)

    def test_graph_binding_cancel_cleanup_hints(self):
        """cancelGraphBinding must call _removeCaptureHints."""
        text = self._read("studio-graph-binding.js")
        self.assertIn("_removeCaptureHints", text)

    def test_preset_wizard_cancels_binding_on_navigate(self):
        """Wizard must cancel active binding capture when navigating steps."""
        text = self._read("studio-preset-wizard.js")
        self.assertIn("cancelGraphBinding", text)
        self.assertIn("navigateStep", text)

    def test_no_legacy_sidebar_reintroduction(self):
        """Playground must not import stopLegacyController or sidebar classes."""
        text = self._read("studio-playground.js")
        self.assertNotIn("stopLegacyController", text)
        self.assertNotIn("comfymodal-sidebar", text)
        self.assertNotIn("comfymodal-studio-legacy", text)

    def test_experiment_mode_no_legacy_sidebar(self):
        """Experiment mode should not reference legacy sidebar patterns directly."""
        text = self._read("studio-experiment-mode.js")
        self.assertNotIn("comfymodal-sidebar", text)
        self.assertNotIn("stopLegacyController", text)
        self.assertNotIn("comfymodal-studio-legacy", text)


class StudioLegacyWiredTests(_JsTestBase):
    """Legacy wrapper module deleted (H18 Wave G)."""

    def test_studio_legacy_deleted(self):
        """studio-legacy.js must stay deleted; no module may reference it."""
        self.assertFalse((WEB / "studio-legacy.js").exists())
        for path in WEB.glob("*.js"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("mountLegacyTab", text, f"{path.name} references retired mounter")
            self.assertNotIn("stopLegacyController", text, f"{path.name} references retired stopper")




# ---------------------------------------------------------------------------
# Task 4 — Playground layout, experiment mode & legacy cleanup (wired)
# ---------------------------------------------------------------------------

class PlaygroundWiredTests(_JsTestBase):
    """Playground wired export and structural tests."""

    def test_playground_exports_render_playground(self):
        """studio-playground.js must export renderPlayground function."""
        text = self._read("studio-playground.js")
        self.assertIn("export function renderPlayground", text)

    def test_playground_uses_feature_registry(self):
        """studio-playground.js must import from studio-feature-registry.js."""
        text = self._read("studio-playground.js")
        self.assertIn(
            "./studio-feature-registry.js",
            text,
            "Expected import from studio-feature-registry.js",
        )

    def test_playground_uses_experiment_mode(self):
        """studio-playground.js must import from studio-experiment-mode.js."""
        text = self._read("studio-playground.js")
        self.assertIn(
            "./studio-experiment-mode.js",
            text,
            "Expected import from studio-experiment-mode.js",
        )

    def test_playground_has_control_panel_and_workspace(self):
        """Playground must have left control panel and right workspace."""
        text = self._read("studio-playground.js")
        self.assertIn("comfymodal-studio-control-panel", text)
        self.assertIn("comfymodal-studio-workspace", text)

    def test_playground_feature_tabs(self):
        """Playground must have feature tab buttons referencing all three features."""
        text = self._read("studio-playground.js")
        self.assertIn("comfymodal-studio-feature-tab", text)
        self.assertIn("feature-tab-", text)
        self.assertIn("FEATURE_SPECS", text)

    def test_playground_disabled_run_reason(self):
        """Disabled Run must have a data-testid or reason element."""
        text = self._read("studio-playground.js")
        self.assertIn("disabled", text.lower())

    def test_playground_has_canvas_region(self):
        """Playground workspace must have a canvas region."""
        text = self._read("studio-playground.js")
        self.assertIn("comfymodal-studio-canvas", text)

    def test_playground_has_filmstrip(self):
        """Playground workspace must have a filmstrip/recent-runs strip (carousel)."""
        text = self._read("studio-playground.js")
        # The filmstrip renders as a carousel with comfymodal-studio-carousel class
        self.assertIn("comfymodal-studio-carousel", text)

    def test_playground_does_not_import_stop_legacy_controller(self):
        """studio-playground.js must NOT import stopLegacyController — cleanup is
        handled by the shell (studio-shell.js) and modal close handler (modal-testing.js),
        not by individual pages."""
        text = self._read("studio-playground.js")
        self.assertNotIn("stopLegacyController", text,
                         "stopLegacyController was dead code in playground; "
                         "cleanup belongs in studio-shell.js and modal-testing.js")


class ExperimentModeWiredTests(_JsTestBase):
    """Experiment mode wired export and structure."""

    def test_experiment_mode_exports(self):
        """studio-experiment-mode.js must export renderExperimentMode."""
        text = self._read("studio-experiment-mode.js")
        self.assertIn("export function renderExperimentMode", text)

    def test_experiment_mode_imports_feature_registry(self):
        """studio-experiment-mode.js must import from studio-feature-registry.js."""
        text = self._read("studio-experiment-mode.js")
        self.assertIn(
            "./studio-feature-registry.js",
            text,
            "Expected import from studio-feature-registry.js",
        )

    def test_experiment_compare_backends_block(self):
        """Experiment mode must have a Compare Backends block."""
        text = self._read("studio-experiment-mode.js")
        self.assertIn("Compare Backends", text)

    def test_experiment_matrix_summary(self):
        """Experiment mode must have a matrix summary section."""
        text = self._read("studio-experiment-mode.js")
        self.assertIn("matrix", text.lower())

    def test_experiment_axis_checkbox_eligible_controls(self):
        """Experiment mode must handle axis checkboxes for eligible controls."""
        text = self._read("studio-experiment-mode.js")
        self.assertIn("axis-checkbox", text)
        self.assertIn("toggleExperimentAxis", text)

    def test_experiment_disabled_run_experiment_reason(self):
        """H-WAVE D: the legacy renderer (renderExperimentRunButton /
        buildExperimentClickHandler) is fully retired; experimentRunSurface
        unconditionally mounts the gated modern section, which derives its
        reason from modernExperimentDisabledReason."""
        text = self._read("studio-experiment-mode.js")
        # The preset-based eligibility helper remains exported.
        self.assertIn("export function getExperimentDisabledReason", text)
        # H-WAVE D: no legacy run-button renderer or creator handler remains.
        self.assertNotIn(
            "function renderExperimentRunButton",
            text,
            "renderExperimentRunButton must be retired in Wave D",
        )
        self.assertNotIn(
            "buildExperimentClickHandler",
            text,
            "buildExperimentClickHandler must be retired in Wave D",
        )
        # The surface selection is unconditional: every state mounts modern.
        self.assertIn(
            'return "modern";',
            text,
            "experimentRunSurface must return \"modern\" unconditionally",
        )
        self.assertNotIn(
            'return "legacy";',
            text,
            "The legacy surface branch must be retired in Wave D",
        )
        # The gated modern section renders the reason under its Run button.
        self.assertIn(
            'data-testid="modern-experiment-reason"',
            text,
            "Expected the modern section's visible gating reason element",
        )
        self.assertIn(
            "modernExperimentDisabledReason(state)",
            text[text.find("function _syncExperimentMount"):],
            "Expected the modern mount sync to render the gating reason",
        )

    def test_experiment_no_separate_axes_page(self):
        """Experiment mode must NOT have a separate Test Axes page."""
        text = self._read("studio-experiment-mode.js")
        # "Test Axes" capitalized as a page name is forbidden
        self.assertNotIn('"Test Axes"', text)
        self.assertNotIn("'Test Axes'", text)


class FeatureRegistryDetailWiredTests(_JsTestBase):
    """Feature registry must have detailed control metadata."""

    def test_registry_exports_CONTROL_DEFS(self):
        """studio-feature-registry.js must export CONTROL_DEFS map."""
        text = self._read("studio-feature-registry.js")
        self.assertIn("export const CONTROL_DEFS", text)

    def test_registry_control_defs_have_types(self):
        """Each control def must have a type property."""
        text = self._read("studio-feature-registry.js")
        self.assertIn("type:", text)

    def test_registry_control_defs_have_default_values(self):
        """Each control def must have a defaultValue."""
        text = self._read("studio-feature-registry.js")
        self.assertIn("defaultValue", text)

    def test_registry_control_defs_have_experiment_eligible(self):
        """Each control def must have experimentEligible."""
        text = self._read("studio-feature-registry.js")
        self.assertIn("experimentEligible", text)

    def test_registry_controls_contain_all_required(self):
        """Required controls must all be defined."""
        text = self._read("studio-feature-registry.js")
        required = ["steps", "guidance", "denoise", "seed", "lora_strength", "mask_blur", "mask_expand"]
        for ctrl in required:
            self.assertIn(ctrl, text, f"Missing control definition: {ctrl}")


class LegacyCleanupWiredTests(_JsTestBase):
    """Legacy controller cleanup wiring retired (H14 Wave E); the loader
    file deleted in Wave G (H18). No production module may still import or
    invoke it."""

    def test_legacy_loader_file_deleted(self):
        self.assertFalse((WEB / "studio-legacy.js").exists())

    def test_shell_imports_and_calls_stop_legacy(self):
        """H14 Wave E: studio-shell.js must not reference stopLegacyController."""
        text = self._read("studio-shell.js")
        self.assertNotIn("stopLegacyController", text)

    def test_modal_testing_calls_stop_on_close(self):
        """H14 Wave E: modal-testing.js must not reference stopLegacyController."""
        text = self._read("modal-testing.js")
        self.assertNotIn("stopLegacyController", text)


# ---------------------------------------------------------------------------
# Slice 1 — Backend tab, history safety, fresh legacy options
# ---------------------------------------------------------------------------

class StudioBackendWiredTests(_JsTestBase):
    """Backend page wired tests."""

    def test_studio_backend_module_exists(self):
        """web/studio-backend.js must exist."""
        self.assertTrue(
            (WEB / "studio-backend.js").exists(),
            "studio-backend.js missing",
        )

    def test_studio_backend_exports_render_backend(self):
        """studio-backend.js must export renderBackend."""
        text = self._read("studio-backend.js")
        self.assertIn("export function renderBackend", text)

    def test_studio_backend_exports_backend_helpers(self):
        """H18 Wave G: the dead backends-discovery exports are deleted
        (zero callers; FD-8). The live presets/run helpers remain."""
        text = self._read("studio-backend-api.js")
        code = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("//")
        )
        self.assertNotIn("getBackends", code)
        self.assertNotIn("getCompareBackends", code)
        self.assertIn("export async function listPresets", text)

    def test_studio_backend_dead_run_history_helpers_deleted(self):
        """H18 Wave G: listExperiments/listRunHistory/listUnifiedHistory are
        deleted (zero importers since the H13 History-V2 migration)."""
        text = self._read("studio-backend-api.js")
        for retired in ["listExperiments", "listRunHistory", "listUnifiedHistory"]:
            self.assertNotIn(f"export async function {retired}", text)

    def test_backend_presets_exports_render_preset_form(self):
        """studio-backend-presets.js must export renderPresetForm for glue import."""
        text = self._read("studio-backend-presets.js")
        self.assertIn(
            "export function renderPresetForm",
            text,
            "Expected studio-backend-presets.js to export renderPresetForm for studio-backend.js",
        )

    def test_shell_pages_include_backend(self):
        """studio-shell.js must reference backend page."""
        text = self._read("studio-shell.js")
        self.assertIn("backend", text)

    def test_nav_order_correct(self):
        """PAGES order must be playground, history, backend, settings."""
        text = self._read("studio-shell.js")
        pages_start = text.find("PAGES = {")
        pages_block = text[pages_start:pages_start + 600]
        self.assertGreater(
            pages_block.find("history"),
            pages_block.find("playground"),
        )
        self.assertGreater(
            pages_block.find("backend"),
            pages_block.find("history"),
        )
        self.assertGreater(
            pages_block.find("settings"),
            pages_block.find("backend"),
        )

    def test_modal_testing_routes_setup_to_modern_playground(self):
        """H10: modal-testing.js must map the setup alias to Playground (never Legacy Setup)."""
        text = self._read("modal-testing.js")
        self.assertIn('setup: "playground"', text)
        # Retired aliases must not set a dead activeLegacyTab
        self.assertNotIn("activeLegacyTab", text)

    def test_modal_testing_legacy_state_machinery_deleted(self):
        """H18 Wave G: the draft/preview/experimentId context machinery is
        deleted (its only consumer was the retired studio-legacy.js)."""
        text = self._read("modal-testing.js")
        has_getter_pattern = (
            "get draft" in text
            or "get previewState" in text
            or "get experimentId" in text
            or "_draftState" in text
        )
        self.assertFalse(
            has_getter_pattern,
            "Legacy draft/preview/experimentId context machinery must stay deleted",
        )

    def test_shell_no_nested_studio_body(self):
        """studio-shell.js must not use comfymodal-studio-body class on page container."""
        text = self._read("studio-shell.js")
        self.assertNotIn("comfymodal-studio-body", text)


# ── Phase 4: Blue-Charcoal Token System ────────────────────────────────

class TokenSystemTests(_JsTestBase):
    """Studio styles must use blue-charcoal token system with --color-* vars."""

    def setUp(self) -> None:
        self.studio_text = self._read("studio-styles.js")

    def test_studio_uses_color_token_for_active_tab(self):
        """Active/focus states must use --color-accent not hardcoded red."""
        # Active tab should reference a --color-* variable or blue accent
        has_accent_ref = (
            "--color-accent" in self.studio_text
            or "--color-border-focus" in self.studio_text
        )
        self.assertTrue(
            has_accent_ref,
            "studio-styles.js must reference --color-accent or --color-border-focus "
            "for active/focus states instead of hardcoded red",
        )

    def test_studio_primary_button_uses_accent_not_red(self):
        """Primary button (Run) should use accent, not #dc2626."""
        # Find the .comfymodal-primary-btn in studio-styles
        btn_start = self.studio_text.find(".comfymodal-primary-btn")
        if btn_start < 0:
            btn_start = self.studio_text.find('.comfymodal-run-section .comfymodal-primary-btn')
        self.assertGreater(
            btn_start, -1,
            "Expected .comfymodal-primary-btn in studio-styles.js",
        )
        btn_block = self.studio_text[btn_start:btn_start + 800]
        # Primary non-destructive buttons should NOT use red
        has_var_ref = "var(--color-accent)" in btn_block or "var(--color-info" in btn_block
        # Also check if it's not directly #dc2626 (which is red)
        if "#dc2626" in btn_block:
            # Check if it's a destructive/hover variant, not the primary background
            is_only_destructive = "destructive" in btn_block or "danger" in btn_block
            self.assertTrue(
                is_only_destructive,
                "Primary non-destructive button must use --color-accent, not #dc2626",
            )

    def test_destructive_button_uses_red_or_danger_token(self):
        """Destructive buttons must use --color-danger or #dc2626."""
        # Find the main rule (has background: property, not in media query)
        dest_start = self.studio_text.find(".comfymodal-destructive-btn {\n  background:")
        if dest_start < 0:
            # Fallback: try with var(--color-danger-bg as the background value
            dest_start = self.studio_text.find(".comfymodal-destructive-btn {\n  background: var(")
        self.assertGreater(dest_start, -1)
        dest_block = self.studio_text[dest_start:dest_start + 500]
        uses_red = (
            "var(--color-danger)" in dest_block
            or "#dc2626" in dest_block
            or "#ef4444" in dest_block
        )
        self.assertTrue(
            uses_red,
            "Destructive buttons must use red/danger color (--color-danger or similar)",
        )

    def test_no_transition_all(self):
        """studio-styles.js must not use 'transition: all'."""
        # Check for transition: all (case-insensitive)
        import re
        has_transition_all = bool(re.search(
            r'transition[^;{]*\ball\b',
            self.studio_text,
            re.IGNORECASE,
        ))
        self.assertFalse(
            has_transition_all,
            "studio-styles.js must not use 'transition: all' — specify properties explicitly",
        )

    def test_focus_visible_outlines_present(self):
        """studio-styles.js must define :focus-visible styles for interactive elements."""
        has_focus_visible = (
            ":focus-visible" in self.studio_text
        )
        self.assertTrue(
            has_focus_visible,
            "Expected :focus-visible style definitions in studio-styles.js",
        )

    def test_safe_area_support(self):
        """studio-styles.js must include safe-area-inset env() variables."""
        has_safe_area = (
            "safe-area-inset" in self.studio_text
            or "env(safe-area-inset" in self.studio_text
        )
        self.assertTrue(
            has_safe_area,
            "Expected safe-area-inset env() support in studio-styles.js",
        )

    def test_reduced_motion_present(self):
        """studios-styles or testing-styles must have prefers-reduced-motion."""
        testing_text = self._read("testing-styles.js")
        combined = self.studio_text + testing_text
        self.assertIn(
            "prefers-reduced-motion",
            combined,
            "Expected prefers-reduced-motion media query in styles",
        )


# ── Final review: progress bar color, Playground note header, el import ──

class FinalReviewTests(_JsTestBase):
    """Resolve review findings: progress bar, note label, el consolidation."""

    # ── 1. Progress bar fill color ─────────────────────────────────────

    def test_progress_bar_fill_uses_accent(self):
        """studio-playground.js progress bar fill must use --color-accent."""
        text = self._read("studio-playground.js")
        # Find the progress bar fill inline style
        fill_idx = text.find("background:#dc2626")
        if fill_idx < 0:
            fill_idx = text.find("background: #dc2626")
        self.assertLess(
            fill_idx, 0,
            "Progress bar fill must not use hardcoded #dc2626",
        )
        # Must reference --color-accent
        self.assertIn(
            "--color-accent",
            text,
            "Expected --color-accent reference in progress bar fill",
        )

    # ── 2. Playground note editor header ───────────────────────────────

    def test_playground_note_editor_has_header(self):
        """Playground renderNoteEditor must have a 'Note' header like History."""
        text = self._read("studio-playground.js")
        note_start = text.find("function renderNoteEditor")
        self.assertGreater(note_start, -1)
        note_end = text.find("return container;", note_start)
        if note_end < 0:
            note_end = note_start + 2000
        note_region = text[note_start:note_end]
        self.assertIn(
            '"Note"',
            note_region,
            "Expected 'Note' header text in Playground renderNoteEditor",
        )
        self.assertIn(
            "uppercase",
            note_region,
            "Expected uppercase styling on Playground note header",
        )

    # ── 3. Playground el consolidation ─────────────────────────────────

    def test_playground_imports_el_from_studio_ui(self):
        """studio-playground.js must import el from studio-ui.js."""
        text = self._read("studio-playground.js")
        self.assertIn(
            "./studio-ui.js",
            text,
            "Expected import of el from studio-ui.js in studio-playground.js",
        )

    def test_playground_no_local_el(self):
        """studio-playground.js must NOT define a local el() function."""
        text = self._read("studio-playground.js")
        self.assertNotIn(
            "function el(tag, props = {}, children = [])",
            text,
            "Local el() must be replaced by import from studio-ui.js",
        )


# ── Keyboard/accessibility: favorite star → button, carousel → button ──

class KeyboardA11yButtonTests(_JsTestBase):
    """Favorite stars and carousel items must be semantic <button> elements."""

    def test_history_favorite_star_is_button(self):
        """studio-history-v2.js renderFavoriteStar must produce a <button>.

        (Assertion moved from the retired studio-history.js to the modern
        History V2 implementation in Phase H9 — same invariant.)
        """
        text = self._read("studio-history-v2.js")
        fav_start = text.find("function renderFavoriteStar")
        self.assertGreater(fav_start, -1)
        fav_block = text[fav_start:fav_start + 800]
        self.assertIn(
            'type: "button"',
            fav_block,
            "Expected type='button' on history favorite star",
        )
        self.assertIn(
            "aria-pressed",
            fav_block,
            "Expected aria-pressed on history favorite star",
        )

    def test_playground_favorite_star_is_button(self):
        """studio-playground.js renderFavoriteStar must produce a <button>."""
        text = self._read("studio-playground.js")
        fav_start = text.find("function renderFavoriteStar")
        self.assertGreater(fav_start, -1)
        fav_block = text[fav_start:fav_start + 800]
        self.assertIn(
            'type: "button"',
            fav_block,
            "Expected type='button' on playground favorite star",
        )
        self.assertIn(
            "aria-pressed",
            fav_block,
            "Expected aria-pressed on playground favorite star",
        )

    def test_carousel_item_is_button(self):
        """studio-playground.js renderFilmstrip carousel items must be <button>."""
        text = self._read("studio-playground.js")
        carousel_start = text.find("function renderFilmstrip")
        self.assertGreater(carousel_start, -1)
        carousel_block = text[carousel_start:]
        # The carousel item is built with el("button", { type: "button", ... })
        # and carries the comfymodal-studio-carousel-item class.
        self.assertIn(
            'el("button", {',
            carousel_block,
            "Expected carousel items to be <button> elements in renderFilmstrip",
        )
        self.assertIn(
            'type: "button"',
            carousel_block,
            "Expected type='button' on carousel items",
        )
        self.assertIn(
            "comfymodal-studio-carousel-item",
            carousel_block,
            "Expected comfymodal-studio-carousel-item class on carousel items",
        )

    def test_carousel_item_has_aria_label(self):
        """Carousel items must have a descriptive aria-label."""
        text = self._read("studio-playground.js")
        self.assertIn(
            '"aria-label"',
            text,
            "Expected aria-label on carousel items in renderFilmstrip",
        )

    def test_carousel_button_chrome_reset(self):
        """studio-styles.js must reset native button chrome on carousel-item."""
        css = self._read("studio-styles.js")
        carousel_item_section = css.find(".comfymodal-studio-carousel-item")
        self.assertGreater(carousel_item_section, -1)
        item_block = css[carousel_item_section:carousel_item_section + 400]
        self.assertIn(
            "background: none",
            item_block,
            "Expected background:none to reset native button chrome on carousel-item",
        )
        self.assertIn(
            "padding: 0",
            item_block,
            "Expected padding:0 on carousel-item button reset",
        )

    def test_favorite_star_focus_visible(self):
        """studio-styles.js must have :focus-visible for favorite-star."""
        css = self._read("studio-styles.js")
        has_fav_fv = (
            "favorite-star:focus-visible" in css
            or "favorite-star:focus" in css
        )
        self.assertTrue(
            has_fav_fv,
            "Expected :focus-visible style for .comfymodal-studio-favorite-star",
        )

    def test_carousel_item_focus_visible(self):
        """studio-styles.js must have :focus-visible for carousel-item."""
        css = self._read("studio-styles.js")
        self.assertIn(
            "carousel-item:focus-visible",
            css,
            "Expected :focus-visible for .comfymodal-studio-carousel-item",
        )


# ── Phase 3: History Preview as Nested Accessible Dialog ────────────────

class HistoryPreviewDialogTests(_JsTestBase):
    """History preview overlay must behave as an accessible nested dialog."""

    def test_preview_overlay_has_role_dialog(self):
        """studio-history-v2-detail.js overlay must have role='dialog'."""
        text = self._read("studio-history-v2-detail.js")
        self.assertIn(
            'role: "dialog"',
            text,
            "Expected role='dialog' on the history-v2 detail overlay",
        )

    def test_preview_overlay_has_aria_modal(self):
        """studio-history-v2-detail.js overlay must have aria-modal='true'."""
        text = self._read("studio-history-v2-detail.js")
        self.assertIn(
            '"aria-modal": "true"',
            text,
            "Expected aria-modal='true' on the history-v2 detail overlay",
        )

    def test_preview_escape_closes_only_preview(self):
        """Escape in the history-v2 detail overlay must close only the overlay (layer 3)."""
        text = self._read("studio-history-v2-detail.js")
        # Layer-based Escape via registerLayerHandler(3, ...) scopes Escape
        # to the overlay so it never bubbles to the parent modal
        self.assertIn(
            "registerLayerHandler(3,",
            text,
            "Expected layer-3 Escape handler in studio-history-v2-detail.js for overlay close",
        )
        self.assertIn(
            "escape: function ()",
            text,
            "Expected Escape handler in studio-history-v2-detail.js",
        )

    # ── Oracle fix: Tab focus containment for history preview ────────

    def test_preview_tab_trap_keydown_handler(self):
        """The history-v2 detail overlay has NO tab trap — Escape (layer 3) is the close contract."""
        text = self._read("studio-history-v2-detail.js")
        # No onkeydown Tab containment — close is layer-3 Escape based
        self.assertNotIn("onkeydown", text,
                         "History-v2 detail overlay must not use onkeydown Tab trap")
        self.assertIn(
            "registerLayerHandler(3,",
            text,
            "Expected layer-3 Escape registration as the close contract",
        )

    # ── Issue 3: Backdrop click reliable close ─────────────────────────

    def test_preview_backdrop_click_closes(self):
        """Click on backdrop must close the history-v2 detail overlay via its backdrop class."""
        text = self._read("studio-history-v2-detail.js")
        self.assertIn(
            "comfymodal-studio-history-v2-overlay-backdrop",
            text,
            "Expected backdrop element in the history-v2 detail overlay",
        )
        self.assertIn(
            'backdrop.addEventListener("click", function () { close(); });',
            text,
            "Expected backdrop click handler to close the overlay",
        )


class CanonicalElTests(_JsTestBase):
    """Canonical el() in studio-ui.js must support all required semantics."""

    def test_canonical_el_supports_dataset(self):
        """studio-ui.js el() must support 'dataset' property."""
        text = self._read("studio-ui.js")
        self.assertIn(
            "dataset",
            text,
            "Expected 'dataset' handling in studio-ui.js el()",
        )

    def test_canonical_el_exports_el(self):
        """studio-ui.js must export the el function."""
        text = self._read("studio-ui.js")
        self.assertIn(
            "export function el",
            text,
            "Expected export function el in studio-ui.js",
        )


# ── Mobile touch-target correction (44px min for interactive) ──────────

class MobileTouchTargetTests(_JsTestBase):
    """At <=480px, interactive controls must have 44px minimum touch targets."""

    def setUp(self) -> None:
        self.css = self._read("studio-styles.js")
        # Locate the 480px media query block
        media_start = self.css.find("@media (max-width: 480px)")
        if media_start >= 0:
            # Find opening brace first, then count nested braces
            block_open = self.css.find("{", media_start)
            if block_open >= 0:
                brace_depth = 1
                i = block_open + 1
                while i < len(self.css):
                    if self.css[i] == "{": brace_depth += 1
                    elif self.css[i] == "}":
                        brace_depth -= 1
                        if brace_depth == 0:
                            self._media_block = self.css[media_start:i + 1]
                            break
                    i += 1
                else:
                    self._media_block = ""
            else:
                self._media_block = ""
        else:
            self._media_block = ""

        self._media_text = (self._media_block or "")

    def test_media_480_exists(self):
        """@media (max-width: 480px) block must exist in studio-styles.js."""
        self.assertIn("@media (max-width: 480px)", self.css,
                       "Expected 480px responsive block in studio-styles.js")

    def test_close_button_min_size(self):
        """.comfymodal-testing-close must have min-width 44px and min-height 44px at <=480px."""
        if not self._media_text:
            self.fail("No @media (max-width: 480px) block found")
        # Find the close button rule inside the media block
        self.assertIn(
            "comfymodal-testing-close",
            self._media_text,
            "Expected .comfymodal-testing-close touch-target rule at <=480px",
        )

    def test_feature_tab_min_height(self):
        """.comfymodal-studio-feature-tab must have min-height 44px at <=480px."""
        if not self._media_text:
            self.fail("No @media (max-width: 480px) block found")
        self.assertIn(
            "comfymodal-studio-feature-tab",
            self._media_text,
            "Expected .comfymodal-studio-feature-tab min-height at <=480px",
        )

    def test_primary_btn_min_height(self):
        """.comfymodal-primary-btn must have min-height 44px at <=480px."""
        if not self._media_text:
            self.fail("No @media (max-width: 480px) block found")
        self.assertIn(
            "comfymodal-primary-btn",
            self._media_text,
            "Expected .comfymodal-primary-btn min-height at <=480px",
        )

    def test_secondary_btn_min_height(self):
        """.comfymodal-secondary-btn must have min-height 44px at <=480px."""
        if not self._media_text:
            self.fail("No @media (max-width: 480px) block found")
        self.assertIn(
            "comfymodal-secondary-btn",
            self._media_text,
            "Expected .comfymodal-secondary-btn min-height at <=480px",
        )

    def test_destructive_btn_min_height(self):
        """.comfymodal-destructive-btn must have min-height 44px at <=480px."""
        if not self._media_text:
            self.fail("No @media (max-width: 480px) block found")
        self.assertIn(
            "comfymodal-destructive-btn",
            self._media_text,
            "Expected .comfymodal-destructive-btn min-height at <=480px",
        )

    def test_input_select_min_height(self):
        """Number inputs and selects must have min-height 44px at <=480px."""
        if not self._media_text:
            self.fail("No @media (max-width: 480px) block found")
        self.assertIn(
            "comfymodal-studio-number-input",
            self._media_text,
            "Expected .comfymodal-studio-number-input min-height at <=480px",
        )
        self.assertIn(
            "comfymodal-studio-select",
            self._media_text,
            "Expected .comfymodal-studio-select min-height at <=480px",
        )

    def test_reset_link_min_height(self):
        """.comfymodal-studio-reset-link must have min-height 44px at <=480px."""
        if not self._media_text:
            self.fail("No @media (max-width: 480px) block found")
        self.assertIn(
            "comfymodal-studio-reset-link",
            self._media_text,
            "Expected .comfymodal-studio-reset-link min-height at <=480px",
        )

    def test_history_preview_close_min_size(self):
        """History-v2 detail overlay must offer reliable click-to-close targets.

        The overlay's close button (comfymodal-studio-history-v2-overlay-close)
        and the full-viewport backdrop click both dismiss the overlay — the
        backdrop spans the whole screen so it always provides a large touch area.
        """
        detail_text = self._read("studio-history-v2-detail.js")
        self.assertIn(
            "comfymodal-studio-history-v2-overlay-close",
            detail_text,
            "Expected history-v2 detail overlay close button class",
        )
        self.assertIn(
            'backdrop.addEventListener("click", function () { close(); });',
            detail_text,
            "Expected backdrop click-to-close on the history-v2 detail overlay",
        )


# ── Phase 5: Responsive Improvements ───────────────────────────────────

class ResponsiveTests(_JsTestBase):
    """Responsive/mobile adaptations in CSS and JS."""

    def test_no_horizontal_overflow_at_320px(self):
        """studio-styles.js must have max-width rules preventing overflow at 320px."""
        css_text = self._read("studio-styles.js")
        has_overflow_protection = (
            "100vw" in css_text or "max-width" in css_text
        )
        self.assertTrue(
            has_overflow_protection,
            "Expected viewport-relative max-width rules in studio-styles.js",
        )

    def test_studio_nav_scrolls_on_small_screens(self):
        """Top nav must have overflow-x:auto or flex-wrap for small screens."""
        css_text = self._read("studio-styles.js")
        nav_section = css_text.find(".comfymodal-studio-topnav")
        if nav_section >= 0:
            nav_css = css_text[nav_section:nav_section + 800]
            has_scroll = (
                "overflow-x" in nav_css or "flex-wrap" in nav_css
            )
        else:
            has_scroll = False
        self.assertTrue(
            has_scroll,
            "Studio top nav must handle small screen overflow via overflow-x or flex-wrap",
        )

    def test_playground_stacks_below_768px(self):
        """studio-styles.js must have @media (max-width:768px) query for playground stacking."""
        css_text = self._read("studio-styles.js")
        has_768px_media = "768px" in css_text
        self.assertTrue(
            has_768px_media,
            "Expected a media query targeting 768px or below in studio-styles.js",
        )

    def test_fixed_width_control_panel_does_not_clip(self):
        """Control panel fixed width must be handled at small screens."""
        css_text = self._read("studio-styles.js")
        control_panel_section = css_text.find(".comfymodal-studio-control-panel")
        self.assertGreater(control_panel_section, -1)
        control_css = css_text[control_panel_section:control_panel_section + 600]
        self.assertIn(
            "min-width",
            control_css,
            "Control panel must have a min-width (to check responsive overrides)",
        )


class RemainingTokenTests(_JsTestBase):
    """All remaining non-destructive #dc2626 must be tokenized in studio-styles.js."""

    def test_number_input_focus_uses_token(self):
        """studio-styles.js number-input:focus must use --color-border-focus."""
        css = self._read("studio-styles.js")
        nf_idx = css.find(".comfymodal-studio-number-input:focus")
        self.assertGreater(nf_idx, -1, "Expected .comfymodal-studio-number-input:focus")
        focus_block = css[nf_idx:nf_idx + 200]
        self.assertNotIn(
            "#dc2626", focus_block,
            "number-input:focus must use --color-border-focus, not #dc2626",
        )

    def test_axis_editor_focus_uses_token(self):
        """axis-editor-values textarea/input:focus must use --color-border-focus."""
        css = self._read("studio-styles.js")
        ae_idx = css.find(".comfymodal-studio-axis-editor-values textarea:focus")
        self.assertGreater(ae_idx, -1, "Expected axis-editor-values focus rule")
        focus_block = css[ae_idx:ae_idx + 300]
        self.assertNotIn(
            "#dc2626", focus_block,
            "axis-editor-values:focus must use --color-border-focus, not #dc2626",
        )

    def test_backend_active_tab_uses_token(self):
        """Backend tab.active must use --color-accent."""
        css = self._read("studio-styles.js")
        bt_idx = css.find(".comfymodal-studio-backend-tab.active")
        self.assertGreater(bt_idx, -1, "Expected .comfymodal-studio-backend-tab.active")
        tab_block = css[bt_idx:bt_idx + 200]
        self.assertNotIn(
            "#dc2626", tab_block,
            "Backend active tab must use --color-accent, not #dc2626",
        )

    def test_input_override_focus_uses_token(self):
        """studio input/select focus override must use --color-border-focus."""
        css = self._read("studio-styles.js")
        ov_idx = css.find(".comfymodal-studio-select:focus")
        self.assertGreater(ov_idx, -1, "Expected .comfymodal-studio-select:focus override")
        override_block = css[ov_idx:ov_idx + 200]
        self.assertNotIn(
            "#dc2626", override_block,
            "Input focus override must use --color-border-focus, not #dc2626",
        )

    def test_wizard_step_dot_active_uses_token(self):
        """wizard-step-dot.active must use --color-accent."""
        css = self._read("studio-styles.js")
        wiz_idx = css.find(".comfymodal-studio-wizard-step-dot.active")
        self.assertGreater(wiz_idx, -1, "Expected .comfymodal-studio-wizard-step-dot.active")
        wiz_block = css[wiz_idx:wiz_idx + 200]
        self.assertNotIn(
            "#dc2626", wiz_block,
            "Wizard step dot active must use --color-accent, not #dc2626",
        )

    def test_destructive_button_color_tokenized(self):
        """Destructive button color must use --color-danger."""
        css = self._read("studio-styles.js")
        # Find the main rule (has background: property, not in media query)
        dest_idx = css.find(".comfymodal-destructive-btn {\n  background:")
        if dest_idx < 0:
            dest_idx = css.find(".comfymodal-destructive-btn {\n  background: var(")
        self.assertGreater(dest_idx, -1, "Expected .comfymodal-destructive-btn")
        dest_block = css[dest_idx:dest_idx + 300]
        self.assertIn(
            "--color-danger",
            dest_block,
            "Destructive button must reference --color-danger token",
        )


# ---------------------------------------------------------------------------
# Regression: Wizard interaction mode must release graph/background inertness
# on wizard opening and restore it when the wizard closes.
# Root cause: commit 0e1c8a9 introduced _inertBackground(true) in
# open_testing_modal (modal-testing.js:222) which blocks the preset wizard's
# graph binding capture (beginGraphBindingCapture needs the graph clickable).
# ---------------------------------------------------------------------------

class WizardInertInteractionTests(_JsTestBase):
    """Regression tests: wizard interaction mode must release background
    inertness on wizard opening and restore it when the wizard closes."""

    def test_wizard_opening_dispatches_custom_event(self):
        """openPresetWizard must dispatch a custom DOM event so the
        modal can release background inertness."""
        text = self._read("studio-preset-wizard.js")
        self.assertIn(
            "comfymodal:wizard-opening",
            text,
            "openPresetWizard must dispatch comfymodal:wizard-opening "
            "so modal-testing.js can release inert on background elements",
        )

    def test_wizard_closing_dispatches_custom_event(self):
        """closePresetWizard must dispatch a custom DOM event so the
        modal can restore background inertness (if parent modal remains open)."""
        text = self._read("studio-preset-wizard.js")
        self.assertIn(
            "comfymodal:wizard-closed",
            text,
            "closePresetWizard must dispatch comfymodal:wizard-closed "
            "so modal-testing.js can re-apply inert on background elements",
        )

    def test_modal_wizard_opening_handler_calls_sync_modal_wizard_state(self):
        """modal-testing.js wizard-opening handler body must call
        _syncModalWizardState() (not bare _inertBackground)."""
        text = self._read("modal-testing.js")
        idx = text.find('"comfymodal:wizard-opening"')
        self.assertGreater(
            idx, -1,
            "modal-testing.js must addEventListener for comfymodal:wizard-opening",
        )
        # Extract handler body: from the event name up to 120 chars
        body = text[idx:idx + 120]
        self.assertIn(
            "_syncModalWizardState()",
            body,
            "wizard-opening handler body must call _syncModalWizardState()",
        )

    def test_modal_wizard_closed_handler_calls_sync_modal_wizard_state(self):
        """modal-testing.js wizard-closed handler body must call
        _syncModalWizardState() (not bare _inertBackground)."""
        text = self._read("modal-testing.js")
        idx = text.find('"comfymodal:wizard-closed"')
        self.assertGreater(
            idx, -1,
            "modal-testing.js must addEventListener for comfymodal:wizard-closed",
        )
        body = text[idx:idx + 120]
        self.assertIn(
            "_syncModalWizardState()",
            body,
            "wizard-closed handler body must call _syncModalWizardState()",
        )


# ---------------------------------------------------------------------------
# Oracle-identified lifecycle failures: invariant between wizard overlay
# presence and background inert + aria-modal state.
# HIGH: cached reopen ignores wizard → leaves inert, initial open with
# wizard → inert, and while wizard permits outside clicks aria-modal
# stays "true" (semantic contradiction).
# ---------------------------------------------------------------------------

class WizardInertAriaInvariantTests(_JsTestBase):
    """Invariant: active wizard overlay => graph background non-inert
    and parent dialog NOT aria-modal; no wizard + open parent modal =>
    background inert and aria-modal="true".  Handles first open and
    cached reopen."""

    def test_sync_modal_wizard_state_defines_invariant_helper(self):
        """modal-testing.js must define _syncModalWizardState that
        queries for .comfymodal-studio-wizard-overlay and toggles
        inert + aria-modal to enforce the invariant."""
        text = self._read("modal-testing.js")
        self.assertIn(
            "function _syncModalWizardState",
            text,
            "Expected _syncModalWizardState() helper in modal-testing.js",
        )
        self.assertIn(
            "comfymodal-studio-wizard-overlay",
            text,
            "_syncModalWizardState must query for wizard overlay",
        )

    def test_open_testing_modal_calls_sync_in_both_paths(self):
        """open_testing_modal must call _syncModalWizardState() in
        both the initial-open and cached-reopen paths so wizard
        overlay is respected on first open and on re-show."""
        text = self._read("modal-testing.js")
        count = text.count("_syncModalWizardState()")
        self.assertGreaterEqual(
            count, 2,
            f"Expected at least 2 calls to _syncModalWizardState() "
            f"(initial open + cached reopen), found {count}",
        )

    def test_wizard_opening_handler_calls_sync(self):
        """comfymodal:wizard-opening listener must call
        _syncModalWizardState to release inert + remove aria-modal."""
        text = self._read("modal-testing.js")
        idx = text.find("wizard-opening")
        if idx < 0:
            self.fail("comfymodal:wizard-opening listener not found")
        block = text[idx:idx + 200]
        self.assertIn(
            "_syncModalWizardState",
            block,
            "wizard-opening handler must call _syncModalWizardState",
        )

    def test_wizard_closed_handler_calls_sync(self):
        """comfymodal:wizard-closed listener must call
        _syncModalWizardState to restore inert + aria-modal."""
        text = self._read("modal-testing.js")
        idx = text.find("wizard-closed")
        if idx < 0:
            self.fail("comfymodal:wizard-closed listener not found")
        block = text[idx:idx + 200]
        self.assertIn(
            "_syncModalWizardState",
            block,
            "wizard-closed handler must call _syncModalWizardState",
        )

    def test_sync_removes_aria_modal_when_wizard_active(self):
        """_syncModalWizardState must removeAttribute('aria-modal')
        on .comfymodal-studio-modal when wizard overlay exists."""
        text = self._read("modal-testing.js")
        self.assertIn(
            'removeAttribute("aria-modal"',
            text,
            "_syncModalWizardState must remove aria-modal when wizard active",
        )

    def test_sync_sets_aria_modal_when_wizard_absent_modal_open(self):
        """_syncModalWizardState must setAttribute('aria-modal','true')
        on .comfymodal-studio-modal when no wizard overlay and modal
        is open."""
        text = self._read("modal-testing.js")
        self.assertIn(
            'setAttribute("aria-modal"',
            text,
            "_syncModalWizardState must restore aria-modal when wizard absent",
        )


if __name__ == "__main__":
    unittest.main()
