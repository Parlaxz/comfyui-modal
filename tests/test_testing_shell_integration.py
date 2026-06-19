"""Task 1 — Failing structural/source tests for the visible frontend integration.

These tests assert patterns that DON'T YET EXIST in the current production
code. They will fail (red) until Tasks 2–4 of the visible-modal-testing-suite
plan are implemented, at which point they should pass (green).

All checks are structural: source-text/regex only, no runtime harness.
"""
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web"


class _JsModule:
    """Helper to read and inspect a JS source file structually."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.text = path.read_text(encoding="utf-8") if path.exists() else ""

    def contains(self, s: str) -> bool:
        return s in self.text

    def has_export(self, name: str) -> bool:
        return bool(
            re.search(
                rf"export\s+(?:function|const|class|let|var)\s+{re.escape(name)}\b",
                self.text,
            )
        )

    def has_function(self, name: str) -> bool:
        return bool(re.search(rf"(?:function\s+{re.escape(name)}|{re.escape(name)}\s*[=:]\s*(?:async\s+)?function)\s*\(",
                              self.text))


# ---------------------------------------------------------------------------
# Extension registration & sidebar integration
# ---------------------------------------------------------------------------

class ShellRegistrationTests(unittest.TestCase):
    """app.registerExtension usage, stable extension name, no extensionMenu."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "modal-testing.js")

    # -- app.registerExtension -------------------------------------------------
    def test_uses_app_register_extension(self):
        """modal-testing.js must call app.registerExtension(...)."""
        self.assertIn(
            "app.registerExtension(",
            self.m.text,
            "Expected app.registerExtension call — the new frontend integration "
            "uses the ComfyUI 1.x extension API instead of manual sidebar patching.",
        )

    def test_extension_name_comfymodal_testing_suite(self):
        """Extension name must be the stable identifier 'comfymodal.testing-suite'."""
        self.assertIn(
            "comfymodal.testing-suite",
            self.m.text,
            "Expected stable extension name 'comfymodal.testing-suite' in modal-testing.js",
        )

    # -- No app.extensionMenu dependency ---------------------------------------
    def test_no_extension_menu_dependency(self):
        """Primary registration must NOT rely on the deprecated app.extensionMenu."""
        self.assertNotIn(
            "app.extensionMenu",
            self.m.text,
            "app.extensionMenu must not be used for primary registration — "
            "use app.registerExtension instead.",
        )

    # -- Sidebar registration path ---------------------------------------------
    def test_sidebar_registration_path(self):
        """Shell must register a sidebar tab via registerSidebarTab (ComfyUI 1.x API)."""
        self.assertIn(
            "registerSidebarTab",
            self.m.text,
            "Expected registerSidebarTab call for the new sidebar entry point",
        )

    def test_old_register_sidebar_removed(self):
        """The legacy registerSidebar function must be removed."""
        self.assertNotIn(
            "function registerSidebar",
            self.m.text,
            "Legacy registerSidebar function must be replaced by registerSidebarTab",
        )

    # -- Fallback launcher -----------------------------------------------------
    def test_fallback_launcher_named_artifact(self):
        """Shell must have a dedicated fallback launcher function or named artifact."""
        text = self.m.text
        self.assertTrue(
            "fallbackLauncher" in text
            or "ensureFallbackLauncher" in text
            or "ensureLauncher" in text,
            "Expected a named fallback-launcher function in modal-testing.js",
        )


# ---------------------------------------------------------------------------
# Diagnostics keys
# ---------------------------------------------------------------------------

class DiagnosticsKeyTests(unittest.TestCase):
    """Every diagnostic key the plan defines must appear in modal-testing.js."""

    _MANDATORY_KEYS = [
        "moduleLoaded",
        "extensionRegistered",
        "setupCompleted",
        "sidebarApiAvailable",
        "sidebarRegistered",
        "secondaryLauncherRegistered",
        "fallbackLauncherVisible",
        "modalHostMounted",
        "modalOpen",
        "activeTab",
        "stylesLoaded",
        "apiBootstrapStatus",
        "eventConnectionStatus",
        "lastFrontendError",
    ]

    def setUp(self) -> None:
        self.text = _JsModule(WEB / "modal-testing.js").text

    def test_diagnostic_key_moduleLoaded(self):
        self.assertIn("moduleLoaded", self.text)

    def test_diagnostic_key_extensionRegistered(self):
        self.assertIn("extensionRegistered", self.text)

    def test_diagnostic_key_setupCompleted(self):
        self.assertIn("setupCompleted", self.text)

    def test_diagnostic_key_sidebarApiAvailable(self):
        self.assertIn("sidebarApiAvailable", self.text)

    def test_diagnostic_key_sidebarRegistered(self):
        self.assertIn("sidebarRegistered", self.text)

    def test_diagnostic_key_secondaryLauncherRegistered(self):
        self.assertIn("secondaryLauncherRegistered", self.text)

    def test_diagnostic_key_fallbackLauncherVisible(self):
        self.assertIn("fallbackLauncherVisible", self.text)

    def test_diagnostic_key_modalHostMounted(self):
        self.assertIn("modalHostMounted", self.text)

    def test_diagnostic_key_modalOpen(self):
        self.assertIn("modalOpen", self.text)

    def test_diagnostic_key_activeTab(self):
        self.assertIn("activeTab", self.text)

    def test_diagnostic_key_stylesLoaded(self):
        self.assertIn("stylesLoaded", self.text)

    def test_diagnostic_key_apiBootstrapStatus(self):
        self.assertIn("apiBootstrapStatus", self.text)

    def test_diagnostic_key_eventConnectionStatus(self):
        self.assertIn("eventConnectionStatus", self.text)

    def test_diagnostic_key_lastFrontendError(self):
        self.assertIn("lastFrontendError", self.text)

    def test_diagnostic_frontend_version_or_source_hash(self):
        """Diagnostics must include frontendVersion or sourceHash/source_hash."""
        self.assertTrue(
            "frontendVersion" in self.text or "sourceHash" in self.text or "source_hash" in self.text,
            "Expected frontendVersion or sourceHash diagnostic field in modal-testing.js",
        )


# ---------------------------------------------------------------------------
# Module references (dashboard / history / API)
# ---------------------------------------------------------------------------

class ModuleReferenceTests(unittest.TestCase):
    """modal-testing.js must reference the shared dashboard/history/api modules."""

    def setUp(self) -> None:
        self.text = _JsModule(WEB / "modal-testing.js").text

    def test_references_testing_api_module(self):
        """Shell must reference the shared api module (testing-api.js)."""
        self.assertIn(
            "testing-api",
            self.text,
            "Expected reference to testing-api.js in modal-testing.js",
        )

    def test_references_testing_dashboard_module(self):
        """Shell must reference the dashboard module (testing-dashboard.js)."""
        self.assertIn(
            "testing-dashboard",
            self.text,
            "Expected reference to testing-dashboard.js in modal-testing.js",
        )

    def test_references_testing_history_module(self):
        """Shell must reference the history module (testing-history.js)."""
        self.assertIn(
            "testing-history",
            self.text,
            "Expected reference to testing-history.js in modal-testing.js",
        )


# ---------------------------------------------------------------------------
# Persistent host / open-close behavior
# ---------------------------------------------------------------------------

class PersistentHostTests(unittest.TestCase):
    """Modal shell must create a persistent host element with open/close markers."""

    def setUp(self) -> None:
        self.text = _JsModule(WEB / "modal-testing.js").text

    def test_persistent_host_element_marker(self):
        """Shell must use a persistent host class or data attribute."""
        has_marker = (
            "testing-host" in self.text
            or "testing-shell-host" in self.text
            or "data-persistent" in self.text
            or "data-testing-host" in self.text
            or "testing-persist" in self.text
        )
        self.assertTrue(
            has_marker,
            "Expected a persistent host marker class/data-attribute in modal-testing.js",
        )

    def test_dedicated_close_function(self):
        """Shell must have a dedicated function to close/destroy the host."""
        self.assertTrue(
            "close_testing_modal" in self.text
            or "destroyHost" in self.text
            or "unmountHost" in self.text,
            "Expected a dedicated close/destroy function for the testing host",
        )


# ---------------------------------------------------------------------------
# Embedded settings mount hooks & secondary launcher
# ---------------------------------------------------------------------------

class SettingsMountTests(unittest.TestCase):
    """Embedded settings mount hooks from modal-settings.js and secondary launcher."""

    def test_embedded_settings_mount_hooks_in_shell(self):
        """modal-testing.js must handle comfymodal.open-section for embedded settings."""
        text = _JsModule(WEB / "modal-testing.js").text
        self.assertIn(
            "comfymodal.open-section",
            text,
            "Expected comfymodal.open-section event handling in modal-testing.js "
            "for embedded settings mount hooks",
        )

    def test_secondary_launcher_in_legacy_modal_settings(self):
        """modal-settings.js must include a secondary Testing Suite launcher."""
        text = _JsModule(WEB / "modal-settings.js").text
        self.assertIn(
            "Testing Suite",
            text,
            "Expected 'Testing Suite' launcher inside the legacy modal-settings.js",
        )


# ---------------------------------------------------------------------------
# Visual redesign: tokenized design system
# ---------------------------------------------------------------------------

class VisualRedesignTokenTests(unittest.TestCase):
    """Tokenized design system in web/testing-styles.js."""

    def setUp(self) -> None:
        self.text = _JsModule(WEB / "testing-styles.js").text

    def test_canonical_modal_gpu_naming_in_header(self):
        """modal-testing.js header must display 'Modal GPU'."""
        text = _JsModule(WEB / "modal-testing.js").text
        self.assertIn(
            "Modal GPU",
            text,
            "Expected 'Modal GPU' as the visible header title",
        )

    def test_tokenized_color_tokens_present(self):
        """testing-styles.js must include surface/text/accent color tokens."""
        self.assertIn("--color-bg-base", self.text)
        self.assertIn("--color-bg-surface", self.text)
        self.assertIn("--color-accent", self.text)
        self.assertIn("--color-text-primary", self.text)
        self.assertIn("--color-text-secondary", self.text)

    def test_tokenized_semantic_color_tokens(self):
        """testing-styles.js must include semantic color tokens."""
        self.assertIn("--color-success", self.text)
        self.assertIn("--color-warning", self.text)
        self.assertIn("--color-danger", self.text)

    def test_tokenized_spacing_tokens_present(self):
        """testing-styles.js must include spacing tokens."""
        self.assertIn("--space-xs", self.text)
        self.assertIn("--space-lg", self.text)
        self.assertIn("--space-2xl", self.text)

    def test_tokenized_radius_tokens_present(self):
        """testing-styles.js must include border-radius tokens."""
        self.assertIn("--radius-sm", self.text)
        self.assertIn("--radius-md", self.text)
        self.assertIn("--radius-lg", self.text)

    def test_tokenized_typography_tokens_present(self):
        """testing-styles.js must include font-size and font-weight tokens."""
        self.assertIn("--font-size-xs", self.text)
        self.assertIn("--font-size-base", self.text)
        self.assertIn("--font-weight-normal", self.text)
        self.assertIn("--font-weight-semibold", self.text)

    def test_tokenized_dimension_tokens(self):
        """testing-styles.js must include dimension tokens."""
        self.assertIn("--control-height-md", self.text)
        self.assertIn("--header-height", self.text)

    def test_tokenized_motion_tokens_present(self):
        """testing-styles.js must include motion tokens."""
        self.assertIn("--duration-fast", self.text)
        self.assertIn("--duration-normal", self.text)
        self.assertIn("--ease-standard", self.text)

    def test_shared_hero_card_class(self):
        """testing-styles.js must define a hero card class."""
        self.assertIn("comfymodal-hero", self.text)

    def test_shared_button_variant_classes(self):
        """testing-styles.js must define primary/secondary/destructive buttons."""
        self.assertIn("comfymodal-primary-btn", self.text)
        self.assertIn("comfymodal-secondary-btn", self.text)
        self.assertIn("comfymodal-destructive-btn", self.text)

    def test_shared_status_badge_class(self):
        """testing-styles.js must define a status badge class."""
        self.assertIn("comfymodal-status-badge", self.text)

    def test_shared_input_classes(self):
        """testing-styles.js must define input/select/textarea classes."""
        self.assertIn("comfymodal-input", self.text)

    def test_shared_focus_ring_class(self):
        """testing-styles.js must define focus-visible ring styles."""
        self.assertIn("focus-visible", self.text)

    def test_shared_step_rail_class(self):
        """testing-styles.js must define a step rail class."""
        self.assertIn("comfymodal-step-rail", self.text)

    def test_shared_progress_bar_classes(self):
        """testing-styles.js must define progress bar classes."""
        self.assertIn("comfymodal-progress-bar", self.text)

    def test_shared_scrollbar_styles(self):
        """testing-styles.js must style thin scrollbars."""
        # Look for scrollbar thumb/track styling or thin scrollbar pattern
        has_scrollbar_styles = (
            "scrollbar" in self.text.lower()
            or "scrollbar-width" in self.text
            or "scrollbar-thumb" in self.text
            or "scrollbar-track" in self.text
            or "comfymodal-scrollbar" in self.text
        )
        self.assertTrue(
            has_scrollbar_styles,
            "Expected scrollbar styling rules in testing-styles.js",
        )


# ---------------------------------------------------------------------------
# Visual redesign: dashboard hierarchy
# ---------------------------------------------------------------------------

class DashboardHierarchyTests(unittest.TestCase):
    """Dashboard blocked vs healthy state hierarchy tests."""

    def setUp(self) -> None:
        self.text = _JsModule(WEB / "testing-dashboard.js").text

    def test_dashboard_new_experiment_primary_cta(self):
        """testing-dashboard.js must include 'New Experiment' as primary CTA."""
        self.assertIn(
            "New Experiment",
            self.text,
            "Expected 'New Experiment' primary CTA in testing-dashboard.js",
        )

    def test_dashboard_deployment_hero_card(self):
        """testing-dashboard.js must use comfymodal-hero for blocked state."""
        self.assertIn(
            "comfymodal-hero",
            self.text,
            "Expected comfymodal-hero class for blocked/unhealthy deploy state",
        )

    def test_dashboard_removes_healthy_deploy_strip(self):
        """testing-dashboard.js must NOT include comfymodal-deploy-strip (removed)."""
        self.assertNotIn(
            "comfymodal-deploy-strip",
            self.text,
            "comfymodal-deploy-strip must be removed from healthy dashboard",
        )

    def test_dashboard_utility_toolbar_class(self):
        """testing-dashboard.js must include testing-dashboard-utility-toolbar."""
        self.assertIn(
            "testing-dashboard-utility-toolbar",
            self.text,
            "Expected testing-dashboard-utility-toolbar for secondary actions",
        )


# ---------------------------------------------------------------------------
# Visual redesign: history row layout
# ---------------------------------------------------------------------------

class HistoryRowLayoutTests(unittest.TestCase):
    """History row/list layout and metadata markers."""

    def setUp(self) -> None:
        self.text = _JsModule(WEB / "testing-history.js").text

    def test_history_row_class(self):
        """testing-history.js must have a row class for list items."""
        self.assertIn(
            "testing-history-row",
            self.text,
            "Expected testing-history-row class for each run record",
        )

    def test_history_thumbnail_marker(self):
        """testing-history.js must have a thumbnail element class."""
        self.assertIn(
            "testing-history-thumb",
            self.text,
            "Expected testing-history-thumb class for type icon/thumbnail",
        )

    def test_history_row_main_field(self):
        """testing-history.js must have a row-main marker."""
        self.assertIn(
            "testing-history-row-main",
            self.text,
            "Expected testing-history-row-main class for main row line",
        )

    def test_history_status_dot_and_label(self):
        """testing-history.js must have a status dot/label area."""
        has_status_marker = (
            "testing-history-status" in self.text
            or "testing-history-status-dot" in self.text
        )
        self.assertTrue(
            has_status_marker,
            "Expected testing-history-status marker for status dot + label",
        )

    def test_history_datetime_field(self):
        """testing-history.js must have a date/time marker."""
        self.assertIn(
            "testing-history-time",
            self.text,
            "Expected testing-history-time class for date/time display",
        )

    def test_history_duration_field(self):
        """testing-history.js must have a duration marker."""
        self.assertIn(
            "testing-history-duration",
            self.text,
            "Expected testing-history-duration class for run duration",
        )

    def test_history_model_field(self):
        """testing-history.js must have a model/profile short label."""
        self.assertIn(
            "testing-history-model",
            self.text,
            "Expected testing-history-model class for model/profile label",
        )


# ---------------------------------------------------------------------------
# Visual redesign: settings nav active state
# ---------------------------------------------------------------------------

class SettingsNavActiveStateTests(unittest.TestCase):
    """Settings wrapper/nav active-state styling hooks."""

    def test_settings_uses_wrapper_class(self):
        """testing-settings.js must use a comfymodal-settings-wrapper class."""
        text = _JsModule(WEB / "testing-settings.js").text
        self.assertIn(
            "comfymodal-settings-wrapper",
            text,
            "Expected comfymodal-settings-wrapper class in testing-settings.js",
        )

    def test_settings_nav_btn_active_uses_design_tokens(self):
        """testing-settings.js nav active btn must reference shared token class."""
        text = _JsModule(WEB / "testing-settings.js").text
        self.assertIn(
            "comfymodal-nav-btn-active",
            text,
            "Expected comfymodal-nav-btn-active class reference in settings nav",
        )


# ---------------------------------------------------------------------------
# Setup + Results Clarity: shared CSS utilities
# ---------------------------------------------------------------------------

class SetupResultsClarityStyleTests(unittest.TestCase):
    """testing-styles.js must include clarity-specific utility classes."""

    def setUp(self) -> None:
        self.text = _JsModule(WEB / "testing-styles.js").text

    def test_styles_include_testing_setup_field_grid(self):
        """testing-styles.js must define .testing-setup-field-grid."""
        self.assertIn(
            ".testing-setup-field-grid",
            self.text,
            "Expected .testing-setup-field-grid in testing-styles.js",
        )

    def test_styles_include_testing_setup_finish_zone(self):
        """testing-styles.js must define .testing-setup-finish-zone."""
        self.assertIn(
            ".testing-setup-finish-zone",
            self.text,
            "Expected .testing-setup-finish-zone in testing-styles.js",
        )

    def test_styles_include_testing_results_command_main(self):
        """testing-styles.js must define .testing-results-command-main."""
        self.assertIn(
            ".testing-results-command-main",
            self.text,
            "Expected .testing-results-command-main in testing-styles.js",
        )

    def test_styles_include_testing_results_summary_card(self):
        """testing-styles.js must define .testing-results-summary-card."""
        self.assertIn(
            ".testing-results-summary-card",
            self.text,
            "Expected .testing-results-summary-card in testing-styles.js",
        )


# ---------------------------------------------------------------------------
# Progressive Clarity: shell, dashboard, results, history
# ---------------------------------------------------------------------------

class ProgressiveClarityShellTests(unittest.TestCase):
    """Fixed shell sizing and header cleanup."""

    def test_shell_uses_fixed_modal_width(self):
        """testing-styles.js must use fixed width 1200px for the modal."""
        text = _JsModule(WEB / "testing-styles.js").text
        self.assertIn(
            "width: 1200px",
            text,
            "Expected fixed modal width 1200px in testing-styles.js",
        )

    def test_shell_uses_fixed_modal_height(self):
        """testing-styles.js must use fixed height 780px for the modal."""
        text = _JsModule(WEB / "testing-styles.js").text
        self.assertIn(
            "height: 780px",
            text,
            "Expected fixed modal height 780px in testing-styles.js",
        )

    def test_modal_header_does_not_render_cloud_subtitle(self):
        """modal-testing.js must NOT contain 'Cloud execution and testing' subtitle."""
        text = _JsModule(WEB / "modal-testing.js").text
        self.assertNotIn(
            "Cloud execution and testing",
            text,
            "Header subtitle must be removed from modal-testing.js",
        )


class ProgressiveClarityDashboardTests(unittest.TestCase):
    """Dashboard hierarchy markers."""

    def test_dashboard_uses_primary_cta_group_marker(self):
        """testing-dashboard.js must use testing-dashboard-primary-actions."""
        text = _JsModule(WEB / "testing-dashboard.js").text
        self.assertIn(
            "testing-dashboard-primary-actions",
            text,
            "Expected testing-dashboard-primary-actions marker",
        )

    def test_dashboard_uses_metric_primary_marker(self):
        """testing-dashboard.js must use testing-dashboard-metric-primary for Experiments."""
        text = _JsModule(WEB / "testing-dashboard.js").text
        self.assertIn(
            "testing-dashboard-metric-primary",
            text,
            "Expected testing-dashboard-metric-primary for experiments card",
        )


class ProgressiveClarityResultsTests(unittest.TestCase):
    """Results emphasis and command grouping."""

    def test_results_uses_emphasized_summary_primary(self):
        """testing-results.js must use testing-results-summary-primary."""
        text = _JsModule(WEB / "testing-results.js").text
        self.assertIn(
            "testing-results-summary-primary",
            text,
            "Expected testing-results-summary-primary for dominant run state",
        )

    def test_results_uses_command_routine_marker(self):
        """testing-results.js must use testing-results-command-routine."""
        text = _JsModule(WEB / "testing-results.js").text
        self.assertIn(
            "testing-results-command-routine",
            text,
            "Expected testing-results-command-routine for routine controls",
        )


class ProgressiveClarityHistoryTests(unittest.TestCase):
    """History two-line row layout."""

    def test_history_uses_two_line_row_main_marker(self):
        """testing-history.js must use testing-history-row-main."""
        text = _JsModule(WEB / "testing-history.js").text
        self.assertIn(
            "testing-history-row-main",
            text,
            "Expected testing-history-row-main for top line of row",
        )

    def test_history_uses_two_line_row_meta_marker(self):
        """testing-history.js must use testing-history-row-meta."""
        text = _JsModule(WEB / "testing-history.js").text
        self.assertIn(
            "testing-history-row-meta",
            text,
            "Expected testing-history-row-meta for bottom line of row",
        )


if __name__ == "__main__":
    unittest.main()
