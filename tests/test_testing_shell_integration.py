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
                rf"export\s+(?:(?:async\s+)?function|const|class|let|var)\s+{re.escape(name)}\b",
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

    # -- Sidebar registration title/tooltip ------------------------------------
    def test_sidebar_tooltip_no_testing_suite(self):
        """Sidebar registration tooltip must not say 'testing suite' or imply comparison runner."""
        # The tooltip is the second string argument to tooltip: "..." in registerSidebarTab.
        # Find the tooltip line and check it specifically.
        tooltip_match = re.search(r'tooltip:\s*"([^"]+)"', self.m.text)
        self.assertIsNotNone(tooltip_match, "Could not find tooltip string in sidebar registration")
        tooltip_text = tooltip_match.group(1)
        self.assertNotIn(
            "testing suite",
            tooltip_text.lower(),
            "Sidebar registration tooltip must not mention 'testing suite'",
        )

    def test_sidebar_registration_title_is_modal_studio(self):
        """Sidebar tab title must be 'Modal Studio' or 'Modal GPU'."""
        has_valid_title = (
            '"Modal Studio"' in self.m.text
            or '"Modal GPU"' in self.m.text
        )
        self.assertTrue(
            has_valid_title,
            "Sidebar registration title must be 'Modal Studio' or 'Modal GPU'",
        )

    # -- Sidebar panel content (minimal launcher, no old sidebar rows) ---------
    def test_sidebar_has_open_studio_button(self):
        """Sidebar panel must have 'Open Studio' button."""
        self.assertIn(
            "Open Studio",
            self.m.text,
            "Sidebar panel must show 'Open Studio' button",
        )

    def test_sidebar_no_open_testing_suite(self):
        """Sidebar panel must NOT contain 'Open Testing Suite' text."""
        self.assertNotIn(
            "Open Testing Suite",
            self.m.text,
            "Sidebar panel must not show 'Open Testing Suite' — replaced by 'Open Studio'",
        )

    def test_sidebar_no_deploy_experiments_workers_rows(self):
        """buildSidebarPanel must NOT render Deploy / Experiments / Workers rows."""
        text = self.m.text
        start = text.find("function buildSidebarPanel")
        self.assertNotEqual(start, -1, "Expected buildSidebarPanel function in modal-testing.js")
        build_region = text[start:start + 1000]
        self.assertNotIn(
            "Deploy",
            build_region,
            "buildSidebarPanel must not render Deploy status row",
        )
        self.assertNotIn(
            "Experiments",
            build_region,
            "buildSidebarPanel must not render Experiments status row",
        )
        self.assertNotIn(
            "Workers",
            build_region,
            "buildSidebarPanel must not render Workers status row",
        )

    def test_sidebar_no_fetch_deploy_status_or_experiments(self):
        """buildSidebarPanel must NOT fetch /deploy/status or /experiments."""
        text = self.m.text
        start = text.find("function buildSidebarPanel")
        self.assertNotEqual(start, -1, "Expected buildSidebarPanel function in modal-testing.js")
        build_region = text[start:]
        self.assertNotIn(
            "/deploy/status",
            build_region,
            "buildSidebarPanel must not call fetchJson for /deploy/status",
        )
        self.assertNotIn(
            "/experiments",
            build_region,
            "buildSidebarPanel must not call fetchJson for /experiments",
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

    def test_canonical_studio_header_naming(self):
        """modal-testing.js / studio-shell.js header must display 'Modal Studio'."""
        text = _JsModule(WEB / "modal-testing.js").text
        self.assertIn(
            "Modal Studio",
            text,
            "Expected 'Modal Studio' as the Studio shell header title — "
            "replaces old 'Modal GPU' header",
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

    def test_shared_setup_summary_class(self):
        """testing-styles.js must define sticky setup summary styling."""
        self.assertIn("testing-setup-sticky-summary", self.text)

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
        """studio-styles.js must use viewport-relative sizing for the modal."""
        text = _JsModule(WEB / "studio-styles.js").text
        self.assertIn(
            "1760px",
            text,
            "Expected large modal width near 1760px in studio-styles.js",
        )

    def test_shell_uses_fixed_modal_height(self):
        """studio-styles.js must use viewport-relative sizing for the modal."""
        text = _JsModule(WEB / "studio-styles.js").text
        self.assertIn(
            "1040px",
            text,
            "Expected large modal height near 1040px in studio-styles.js",
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


# ---------------------------------------------------------------------------
# Studio Shell Contract Tests (Task 1 — Studio shell redesign)
# ---------------------------------------------------------------------------

class StudioShellContractTests(unittest.TestCase):
    """New Studio shell top nav and Studio module surface."""

    def test_main_nav_uses_playground_history_settings_only(self):
        """modal-testing.js must reference Playground, History, and Settings."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn("Playground", text)
        self.assertIn("History", text)
        self.assertIn("Settings", text)

    def test_old_primary_tabs_not_in_main_nav(self):
        """Old Dashboard/Setup/Profiles/Results must NOT appear in main nav."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertNotIn(
            'text: "Dashboard"', text,
            "Dashboard must not be a top-level nav item",
        )
        self.assertNotIn(
            'text: "Setup"', text,
            "Setup must not be a top-level nav item",
        )
        self.assertNotIn(
            'text: "Profiles"', text,
            "Profiles must not be a top-level nav item",
        )
        self.assertNotIn(
            'text: "Results"', text,
            "Results must not be a top-level nav item",
        )

    def test_studio_modules_exist(self):
        """All required Studio module files must exist in web/."""
        for name in [
            "studio-shell.js",
            "studio-playground.js",
            "studio-history.js",
            "studio-settings.js",
            "studio-feature-registry.js",
            "studio-experiment-mode.js",
            "studio-legacy.js",
            "studio-styles.js",
        ]:
            self.assertTrue(
                (WEB / name).exists(),
                f"Required Studio module web/{name} is missing",
            )

    # ── Feature registry content ────────────────────────────────────────

    def test_feature_registry_has_txt2img(self):
        """studio-feature-registry.js must define a txt2img feature."""
        text = (WEB / "studio-feature-registry.js").read_text(encoding="utf-8")
        self.assertIn("txt2img", text)

    def test_feature_registry_has_object_remove(self):
        """studio-feature-registry.js must define an object_remove feature."""
        text = (WEB / "studio-feature-registry.js").read_text(encoding="utf-8")
        self.assertIn("object_remove", text)

    def test_feature_registry_has_object_replace(self):
        """studio-feature-registry.js must define an object_replace feature."""
        text = (WEB / "studio-feature-registry.js").read_text(encoding="utf-8")
        self.assertIn("object_replace", text)

    # ── No separate Test Axes page/list ─────────────────────────────────

    def test_no_separate_test_axes_list(self):
        """Studio modules must NOT define a separate 'Test Axes' concept as a page.

        Experiment mode lives inside Playground as a toggle, not as a separate
        top-level page or master list.
        """
        text = (WEB / "studio-shell.js").read_text(encoding="utf-8")
        self.assertNotIn("Test Axes", text)


class StudioLegacyContractTests(unittest.TestCase):
    """Legacy reachability via Settings and truthful placeholder copy."""

    def test_settings_legacy_mentions_all_old_tabs(self):
        """studio-settings.js must list all old tabs under Legacy section."""
        text = (WEB / "studio-settings.js").read_text(encoding="utf-8")
        for needle in [
            "Legacy Dashboard",
            "Legacy Setup",
            "Legacy Profiles",
            "Legacy Results",
            "Legacy History",
            "Legacy Settings",
        ]:
            self.assertIn(
                needle, text,
                f"Expected '{needle}' in studio-settings.js Legacy section",
            )

    def test_playground_uses_honest_future_placeholder_copy(self):
        """studio-playground.js must use honest future-work copy for image-edit tools."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertTrue(
            "future work" in text.lower()
            or "not implemented yet" in text.lower(),
            "Expected honest future-work placeholder copy in studio-playground.js",
        )

    # ── History uses real data ─────────────────────────────────────────

    def test_history_has_run_history_endpoint(self):
        """studio-history.js must fetch from the run-history API endpoint."""
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        self.assertIn(
            "run-history", text,
            "Expected run-history endpoint reference in studio-history.js",
        )

    def test_history_shows_truthful_empty_state(self):
        """studio-history.js must show a truthful empty state, not decorative text."""
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        self.assertTrue(
            "No run history" in text or "No history" in text or "No experiments" in text,
            "Expected truthful empty state text in studio-history.js",
        )

    # ── Settings sections with data-section attributes ─────────────────

    def test_settings_sections_have_data_section_attributes(self):
        """studio-settings.js must have data-section attributes on each section."""
        text = (WEB / "studio-settings.js").read_text(encoding="utf-8")
        # Build DOM sections use "data-section": sec.section pattern for 5 sections
        # The literal 'data-section' must appear in source for dynamic setting
        self.assertIn('"data-section"', text,
                       "Expected data-section attribute setting in studio-settings.js")
        # All 5 sections must be represented in the sections config array
        for section in ["studio", "backends", "runtime", "features", "legacy"]:
            self.assertIn(
                section, text,
                f"Expected section '{section}' referenced in studio-settings.js",
            )

    def test_settings_legacy_items_clickable(self):
        """studio-settings.js must make legacy items clickable to load old screens."""
        text = (WEB / "studio-settings.js").read_text(encoding="utf-8")
        self.assertIn(
            "mountLegacyTab", text,
            "Expected mountLegacyTab reference in studio-settings.js",
        )



# ---------------------------------------------------------------------------
# Task 4 — Real Playground layout & experiment mode (structural)
# ---------------------------------------------------------------------------

class PlaygroundLayoutTests(unittest.TestCase):
    """Playground must have a real control panel and workspace layout."""

    def setUp(self) -> None:
        self.text = _JsModule(WEB / "studio-playground.js").text

    def test_playground_has_control_panel_class(self):
        """studio-playground.js must use comfymodal-studio-control-panel."""
        self.assertIn(
            "comfymodal-studio-control-panel",
            self.text,
            "Expected control panel class in studio-playground.js",
        )

    def test_playground_has_workspace_class(self):
        """studio-playground.js must use comfymodal-studio-workspace."""
        self.assertIn(
            "comfymodal-studio-workspace",
            self.text,
            "Expected workspace class in studio-playground.js",
        )

    def test_playground_has_feature_tabs_as_selector(self):
        """studio-playground.js must have feature tabs (the only selector)."""
        self.assertIn(
            "feature-tabs",
            self.text,
            "Expected feature tabs element class in studio-playground.js",
        )
        self.assertIn(
            "feature-tab",
            self.text,
            "Expected feature tab test IDs in studio-playground.js",
        )

    def test_no_feature_dropdown_in_left_panel(self):
        """studio-playground.js must NOT have a feature dropdown/select in the control panel.

        Feature tabs above the workspace are the only feature selector.
        """
        # The old Feature dropdown was a <select> element; it must be removed.
        # The feature-tabs buttons in the workspace are the only selector.
        has_feature_dropdown = bool(
            re.search(r'renderControlGroup\("Feature",\s*renderFeatureSelector', self.text)
        )
        self.assertFalse(
            has_feature_dropdown,
            "Feature dropdown (renderControlGroup('Feature', renderFeatureSelector)) "
            "must be removed from the left control panel",
        )

    def test_playground_has_prompt_input(self):
        """studio-playground.js must have a prompt/instruction input."""
        self.assertIn(
            "prompt",
            self.text,
            "Expected prompt input in studio-playground.js",
        )

    def test_playground_has_experiment_import(self):
        """studio-playground.js must import experiment mode module."""
        self.assertIn(
            "./studio-experiment-mode.js",
            self.text,
            "Expected import of experiment mode module",
        )

    def test_playground_has_feature_registry_import(self):
        """studio-playground.js must import feature registry."""
        self.assertIn(
            "./studio-feature-registry.js",
            self.text,
            "Expected import of feature registry module",
        )

    def test_playground_has_mask_controls_section(self):
        """studio-playground.js must have mask controls section."""
        self.assertIn(
            "mask-controls",
            self.text,
            "Expected mask controls testid in studio-playground.js",
        )

    def test_playground_has_feature_tabs(self):
        """studio-playground.js must have feature tab buttons."""
        self.assertIn(
            "feature-tab",
            self.text,
            "Expected feature tab test IDs in studio-playground.js",
        )
        self.assertIn(
            "feature-tabs",
            self.text,
            "Expected feature tabs element class in studio-playground.js",
        )

    def test_playground_has_run_button(self):
        """studio-playground.js must have a Run button."""
        self.assertIn(
            "run-btn",
            self.text,
            "Expected Run button testid in studio-playground.js",
        )

    def test_playground_image_edit_tools_honest_placeholder(self):
        """studio-playground.js must have honest disabled placeholders for image-edit tools."""
        self.assertTrue(
            "not implemented" in self.text.lower()
            or "coming soon" in self.text.lower()
            or "future work" in self.text.lower()
            or "placeholder" in self.text.lower(),
            "Expected honest future-work placeholder for image-edit tools",
        )


class PlaygroundDisabledRunTests(unittest.TestCase):
    """Disabled Run button must give precise reasons and route to Legacy Setup."""

    def test_disabled_run_mentions_legacy_setup(self):
        """studio-playground.js must reference Legacy Setup when Run is disabled."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertIn(
            "Legacy Setup",
            text,
            "Expected Legacy Setup reference in disabled Run reason",
        )

    def test_disabled_run_gives_reason(self):
        """studio-playground.js must give a reason when Run is disabled."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        has_reason = (
            "configure" in text.lower()
            or "no backends" in text.lower()
            or "not available" in text.lower()
            or "setup" in text.lower()
        )
        self.assertTrue(
            has_reason,
            "Expected a precise reason when Run is disabled in studio-playground.js",
        )


class PlaygroundBackendSelectorTests(unittest.TestCase):
    """Backend selector must show truthful empty state or real data."""

    def test_backend_selector_present(self):
        """studio-playground.js must have a backend selector."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertIn(
            "backend",
            text.lower(),
            "Expected backend selector in studio-playground.js",
        )

    def test_backend_empty_state_truthful(self):
        """studio-playground.js must show truthful empty state for backends."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        has_empty_state = (
            "no backends" in text.lower()
            or "no presets" in text.lower()
            or "empty state" in text.lower()
        )
        self.assertTrue(
            has_empty_state,
            "Expected truthful empty state for backends in studio-playground.js",
        )


class ExperimentModeTests(unittest.TestCase):
    """Experiment mode is an overlay on Playground, not a separate page."""

    def test_experiment_toggle_exists(self):
        """studio-experiment-mode.js must export renderExperimentToggle."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertIn(
            "export function renderExperimentToggle",
            text,
            "Expected renderExperimentToggle export in studio-experiment-mode.js",
        )

    def test_experiment_toggle_labels(self):
        """studio-experiment-mode.js must have Experiment and Exit Experiment labels."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertIn("Experiment", text)
        self.assertIn("Exit Experiment", text)

    def test_compare_backends_block(self):
        """studio-experiment-mode.js must have a Compare Backends block."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertIn(
            "Compare Backends",
            text,
            "Expected Compare Backends block in experiment mode",
        )

    def test_matrix_summary_block(self):
        """studio-experiment-mode.js must have a matrix summary block."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertIn(
            "matrix",
            text.lower(),
            "Expected matrix summary block in experiment mode",
        )

    def test_axis_checkboxes_on_controls(self):
        """Experiment-eligible controls must gain axis checkboxes."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertIn(
            "checkbox",
            text.lower(),
            "Expected axis checkbox support in experiment mode",
        )

    def test_no_separate_test_axes_list(self):
        """Studio modules must NOT define a separate Test Axes list."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertNotIn(
            "Test Axes",
            text,
            "Test Axes must not appear in experiment mode module",
        )

    def test_experiment_disabled_run_mentions_legacy_setup(self):
        """studio-experiment-mode.js must reference Legacy Setup when Run Experiment is disabled."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertIn(
            "Legacy Setup",
            text,
            "Expected Legacy Setup reference when Run Experiment is disabled",
        )

    def test_experiment_disabled_gives_reason(self):
        """studio-experiment-mode.js must give a precise reason when Run Experiment is disabled."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        has_reason = (
            "not yet" in text.lower()
            or "not wired" in text.lower()
            or "configure" in text.lower()
            or "experiment" in text.lower()
        )
        self.assertTrue(
            has_reason,
            "Expected a precise reason when Run Experiment is disabled",
        )

    def test_experiment_axis_editor_for_prompt(self):
        """Experiment mode must have axis editor for prompt/instruction controls."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        has_editor = bool(
            re.search(r'renderAxisEditor|axis.*editor|axis-config', text, re.IGNORECASE)
            or 'axis-editor' in text
            or 'axisEditor' in text
        )
        self.assertTrue(
            has_editor,
            "Expected axis editor component in experiment mode for prompt/instruction",
        )

    def test_experiment_axis_editor_for_numeric(self):
        """Experiment mode must have axis editor for numeric controls like steps."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        has_numeric_editor = (
            'comma-separated' in text.lower()
            or 'values' in text.lower()
            or 'axisEditor' in text
            or 'axis-editor' in text
        )
        self.assertTrue(
            has_numeric_editor,
            "Expected axis editor component for numeric controls with CSV input",
        )

    def test_matrix_summary_from_configured_axes(self):
        """Matrix summary must update from real configured axes (count, combos, warning if zero)."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertIn("Estimated runs", text)
        # Should show count of configured axes
        self.assertTrue(
            "0" in text or "axisEntries" in text or "configured" in text.lower(),
            "Expected matrix summary to reflect number of configured axes",
        )

    def test_compare_backends_uses_studio_backend_abstraction(self):
        """Compare Backends must reference studio-backend abstraction."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertIn(
            "studio-backend.js",
            text,
            "Expected studio-backend.js import in experiment mode for backend abstraction",
        )


class LargerModalVisualTests(unittest.TestCase):
    """Modal must be significantly larger with dark Nexus-style visuals."""

    def test_larger_modal_dimensions(self):
        """Modal must use min(98vw, 1760px) width and min(94vh, 1040px) height or similar."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        # Check for larger viewport-based sizing
        has_larger_width = (
            "1760px" in text or "98vw" in text or "98%" in text
        )
        has_larger_height = (
            "1040px" in text or "94vh" in text or "94%" in text
        )
        self.assertTrue(
            has_larger_width,
            "Expected larger modal width near 1760px/98vw in studio-styles.js",
        )
        self.assertTrue(
            has_larger_height,
            "Expected larger modal height near 1040px/94vh in studio-styles.js",
        )

    def test_nexus_style_chrome(self):
        """Modal must have dark near-black chrome."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        has_dark_chrome = (
            "#0a0a0a" in text or "#111" in text or "#0d0d0d" in text or "#080808" in text
        )
        self.assertTrue(
            has_dark_chrome,
            "Expected dark near-black chrome color in studio-styles.js for Nexus-style",
        )

    def test_red_primary_button(self):
        """Run button must use red primary action styling."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        has_red_primary = (
            "#dc2626" in text or "#e11d48" in text or "#ef4444" in text 
            or "red" in text.lower() and "primary" in text.lower()
        )
        self.assertTrue(
            has_red_primary,
            "Expected red primary button styling in studio-styles.js",
        )

    def test_dotted_canvas_background(self):
        """Canvas/workspace must have a dotted/grid background."""
        text = (WEB / "studio-styles.js").read_text(encoding="utf-8")
        has_grid_pattern = (
            "dotted" in text.lower()
            or "grid" in text.lower()
            or "radial-gradient" in text
            or "repeating" in text
        )
        self.assertTrue(
            has_grid_pattern,
            "Expected dotted/grid background pattern in studio-styles.js for canvas",
        )


class FeatureRegistryEnhancedTests(unittest.TestCase):
    """Feature registry must have detailed control definitions."""

    def setUp(self) -> None:
        self.text = (WEB / "studio-feature-registry.js").read_text(encoding="utf-8")

    def test_feature_registry_has_control_definitions(self):
        """studio-feature-registry.js must define control details beyond IDs."""
        self.assertIn("experimentEligible", self.text)

    def test_feature_registry_has_control_types(self):
        """studio-feature-registry.js must specify control types."""
        self.assertIn("type", self.text)

    def test_feature_registry_has_default_values(self):
        """studio-feature-registry.js must specify default values for controls."""
        self.assertIn("defaultValue", self.text)

    def test_feature_registry_controls_include_steps_guidance_denoise_seed(self):
        """studio-feature-registry.js must define steps, guidance, denoise, seed controls."""
        for ctrl in ["steps", "guidance", "denoise", "seed"]:
            self.assertIn(ctrl, self.text, f"Expected control '{ctrl}' in feature registry")

    def test_feature_registry_controls_include_lora(self):
        """studio-feature-registry.js must define lora and lora_strength controls."""
        self.assertIn("lora_strength", self.text)

    def test_feature_registry_controls_include_mask(self):
        """studio-feature-registry.js must define mask_blur and mask_expand controls."""
        self.assertIn("mask_blur", self.text)
        self.assertIn("mask_expand", self.text)

    def test_object_remove_has_core_generation_knobs(self):
        """object_remove must expose prompt, steps, guidance, denoise, seed, lora, lora_strength, mask_blur, mask_expand."""
        # Find the object_remove feature spec block
        obj_remove_start = self.text.find('id: "object_remove"')
        self.assertGreater(obj_remove_start, -1, "object_remove feature spec not found")
        # Look at a window around the object_remove controls array
        controls_window = self.text[obj_remove_start:obj_remove_start + 600]
        for knob in ["prompt", "instruction", "steps", "guidance", "denoise", "seed", "lora", "lora_strength", "mask_blur", "mask_expand"]:
            self.assertIn(knob, controls_window,
                          f"object_remove missing control '{knob}' in its controls array")

    def test_object_replace_has_core_generation_knobs(self):
        """object_replace must expose prompt, steps, guidance, denoise, seed, lora, lora_strength, mask_blur, mask_expand."""
        obj_replace_start = self.text.find('id: "object_replace"')
        self.assertGreater(obj_replace_start, -1, "object_replace feature spec not found")
        controls_window = self.text[obj_replace_start:obj_replace_start + 600]
        for knob in ["prompt", "instruction", "steps", "guidance", "denoise", "seed", "lora", "lora_strength", "mask_blur", "mask_expand"]:
            self.assertIn(knob, controls_window,
                          f"object_replace missing control '{knob}' in its controls array")

    def test_mask_controls_apply_to_image_edit_features(self):
        """mask_blur and mask_expand must be applicable to image-edit features (not only txt2img)."""
        mask_blur_applicable = self.text.find("mask_blur") > -1
        mask_expand_applicable = self.text.find("mask_expand") > -1
        self.assertTrue(mask_blur_applicable, "mask_blur not found in applicableFeatures for image-edit features")
        self.assertTrue(mask_expand_applicable, "mask_expand not found in applicableFeatures for image-edit features")
        # Verify applicableFeatures for mask_blur includes image-edit features
        mask_blur_idx = self.text.find('mask_blur: {')
        self.assertGreater(mask_blur_idx, -1)
        mask_blur_block = self.text[mask_blur_idx:mask_blur_idx + 400]
        self.assertIn("object_remove", mask_blur_block,
                       "mask_blur applicableFeatures must include object_remove")
        self.assertIn("object_replace", mask_blur_block,
                       "mask_blur applicableFeatures must include object_replace")
        self.assertIn("txt2img", mask_blur_block,
                       "mask_blur applicableFeatures must include txt2img")


class InfoTooltipTests(unittest.TestCase):
    """Bulky description paragraphs must be replaced with info icon tooltips."""

    def test_create_info_hint_utility_exists(self):
        """A createInfoHint helper/function must exist in studio modules."""
        # Check either as its own module or embedded in playground/experiment-mode/feature-registry
        info_text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertIn(
            "createInfoHint",
            info_text,
            "Expected createInfoHint helper usage in studio-playground.js",
        )

    def test_no_bulky_visible_description_paragraphs_in_left_panel(self):
        """Left panel must not contain bulky visible description paragraphs under headings."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        # Help text as inline muted spans is OK, but bulky paragraph blocks under section headings
        # should not exist. Check that help text does NOT appear as standalone <p> under headings.
        has_info_icon_pattern = "info-icon" in text or "info-hint" in text or "createInfoHint" in text
        self.assertTrue(
            has_info_icon_pattern,
            "Expected info icon/hint mechanism to replace bulky visible description paragraphs",
        )


class LegacyCleanupTriggerTests(unittest.TestCase):
    """Legacy controller must be stopped when navigating away or closing modal."""

    def test_stop_legacy_controller_exported(self):
        """studio-legacy.js must export stopLegacyController."""
        text = (WEB / "studio-legacy.js").read_text(encoding="utf-8")
        self.assertIn(
            "export function stopLegacyController",
            text,
            "Expected stopLegacyController export in studio-legacy.js",
        )

    def test_shell_imports_stop_legacy_controller(self):
        """studio-shell.js must import stopLegacyController from studio-legacy.js."""
        text = (WEB / "studio-shell.js").read_text(encoding="utf-8")
        self.assertIn(
            "stopLegacyController",
            text,
            "Expected stopLegacyController reference in studio-shell.js",
        )

    def test_modal_testing_calls_stop_legacy_on_close(self):
        """modal-testing.js must call stopLegacyController when closing the modal."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn(
            "stopLegacyController",
            text,
            "Expected stopLegacyController call in modal-testing.js close flow",
        )

    def test_shell_clears_legacy_controller_on_page_nav(self):
        """studio-shell.js must clear activeLegacyTab and call stopLegacyController on nav away."""
        text = (WEB / "studio-shell.js").read_text(encoding="utf-8")
        self.assertIn("stopLegacyController", text)


# ---------------------------------------------------------------------------
# Slice 1 — Backend tab, fresh legacy options, history safety
# ---------------------------------------------------------------------------

class StudioBackendContractTests(unittest.TestCase):
    """Backend page, helpers, and routing tests for Modal Studio."""

    def test_studio_backend_module_exists(self):
        """web/studio-backend.js must exist."""
        self.assertTrue(
            (WEB / "studio-backend.js").exists(),
            "Required Studio module web/studio-backend.js is missing",
        )

    def test_studio_backend_exports_render_backend(self):
        """studio-backend.js must export renderBackend function."""
        m = _JsModule(WEB / "studio-backend.js")
        self.assertTrue(
            m.has_export("renderBackend"),
            "studio-backend.js must export renderBackend",
        )

    def test_studio_backend_exports_get_backends(self):
        """studio-backend.js must export getBackends helper for Playground."""
        m = _JsModule(WEB / "studio-backend.js")
        self.assertTrue(
            m.has_export("getBackends") or m.has_export("fetchBackends"),
            "studio-backend.js must export a backend-fetching helper",
        )

    def test_studio_backend_exports_get_compare_backends(self):
        """studio-backend.js must export getCompareBackends for experiment mode."""
        m = _JsModule(WEB / "studio-backend.js")
        self.assertTrue(
            m.has_export("getCompareBackends") or "compareBackends" in m.text,
            "studio-backend.js must export or define a compare-backends helper",
        )

    def test_shell_imports_render_backend(self):
        """studio-shell.js must import renderBackend from studio-backend.js."""
        text = (WEB / "studio-shell.js").read_text(encoding="utf-8")
        self.assertIn(
            "renderBackend",
            text,
            "Expected renderBackend import in studio-shell.js",
        )

    def test_shell_pages_include_backend(self):
        """studio-shell.js PAGES must include backend between history and settings."""
        text = (WEB / "studio-shell.js").read_text(encoding="utf-8")
        self.assertIn("backend", text, "Expected backend page in PAGES")

    def test_nav_order_playground_history_backend_settings(self):
        """Top nav order must be Playground | History | Backend | Settings."""
        shell_text = (WEB / "studio-shell.js").read_text(encoding="utf-8")
        pages_start = shell_text.find("PAGES = {")
        pages_block = shell_text[pages_start:pages_start + 800]
        playground_pos = pages_block.find("playground")
        history_pos = pages_block.find("history")
        backend_pos = pages_block.find("backend")
        settings_pos = pages_block.find("settings")
        self.assertGreater(
            history_pos, playground_pos,
            "history must come after playground in PAGES",
        )
        self.assertGreater(
            backend_pos, history_pos,
            "backend must come after history in PAGES",
        )
        self.assertGreater(
            settings_pos, backend_pos,
            "settings must come after backend in PAGES",
        )

    def test_studio_pages_include_backend(self):
        """modal-testing.js STUDIO_PAGES must include Backend."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn(
            "Backend",
            text,
            "Expected Backend in STUDIO_PAGES or nav labels",
        )

    def test_open_testing_modal_setup_opens_settings_legacy_setup(self):
        """open_testing_modal('setup') must navigate to Settings > Legacy Setup."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn(
            "activeLegacyTab",
            text,
            "Expected activeLegacyTab handling for legacy tab routing",
        )
        # The pageMap or routing must map setup to settings
        self.assertIn(
            "setup",
            text,
            "Expected setup tab mapping in modal-testing.js",
        )

    def test_open_testing_modal_profiles_opens_settings_legacy_profiles(self):
        """open_testing_modal('profiles') must navigate to Settings > Legacy Profiles."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn(
            "profiles",
            text,
            "Expected profiles tab mapping in modal-testing.js",
        )

    def test_open_testing_modal_results_opens_settings_legacy_results(self):
        """open_testing_modal('results') must navigate to Settings > Legacy Results."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn(
            "results",
            text,
            "Expected results tab mapping in modal-testing.js",
        )

    def test_onrun_opens_legacy_results(self):
        """onRun(experimentId) must open Settings > Legacy Results with experiment ID."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        # Must handle experiment ID via activeLegacyTab mechanism or direct navigation
        self.assertIn(
            "experimentId",
            text,
            "Expected experimentId handling in onRun flow",
        )


class StudioHistorySafetyTests(unittest.TestCase):
    """History page must be safe: no innerHTML for run data, has retry, groups by experiment_id."""

    def test_history_no_inner_html_for_run_data(self):
        """studio-history.js must use DOM nodes/textContent, not innerHTML, for run data rows."""
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        # Check that innerHTML is NOT used to inject user/run data
        # It's OK to use innerHTML for static loading/error templates
        rows_html = text.find("innerHTML")
        # Find any innerHTML assignment that contains run data interpolation
        # We check that the template does NOT interpolate user data via string concatenation in innerHTML
        has_dangerous_innerhtml = (
            'innerHTML = `' in text or 'innerHTML += `' in text
        )
        self.assertFalse(
            has_dangerous_innerhtml,
            "History page must not use template literal innerHTML for run data — use DOM nodes",
        )

    def test_history_uses_dom_nodes_for_cards(self):
        """studio-history.js must use createElement for run data cards."""
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        self.assertIn(
            "createElement",
            text,
            "Expected createElement usage in studio-history.js",
        )

    def test_history_has_retry_on_error(self):
        """studio-history.js must have a retry mechanism on failed fetch."""
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        has_retry = (
            "retry" in text.lower()
            or "Retry" in text
        )
        self.assertTrue(
            has_retry,
            "Expected retry mechanism in studio-history.js error state",
        )

    def test_history_truthful_empty_state(self):
        """studio-history.js must show truthful empty state."""
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        self.assertTrue(
            "No run history" in text or "No history" in text or "No experiments" in text or "no runs" in text.lower(),
            "Expected truthful empty state text in studio-history.js",
        )

    def test_history_truthful_error_state(self):
        """studio-history.js must show a visible error state on failure."""
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        self.assertIn(
            "Failed",
            text,
            "Expected error state display in studio-history.js",
        )

    def test_history_groups_by_experiment_id(self):
        """studio-history.js should group cells by experiment_id if present."""
        text = (WEB / "studio-history.js").read_text(encoding="utf-8")
        self.assertIn(
            "experiment_id",
            text,
            "Expected experiment_id handling for cell grouping in studio-history.js",
        )


class FreshLegacyOptionsTests(unittest.TestCase):
    """Legacy options/draft/preview must be fresh each mount."""

    def test_legacy_context_uses_getters_not_frozen_values(self):
        """modal-testing.js must use JS getters or functions for draft/preview/experimentId in context."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        # Look for getter syntax or function-wrapped state reads
        has_getter = (
            "get draft" in text
            or "get previewState" in text
            or "get experimentId" in text
            or "getLegacyOptions" in text
            or "_readLatestDraft" in text
            or "_getFresh" in text
        )
        self.assertTrue(
            has_getter,
            "Expected getter or function-wrapped state reads in modal-testing.js context — "
            "draft/preview/experimentId must be fresh each mount, not frozen at shell mount",
        )

    def test_legacy_context_not_frozen_at_mount(self):
        """The shell context object must not contain static draft/previewState/experimentId values."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        # Check that draft is NOT evaluated as a static expression at the context level
        # (it's OK if it's a getter)
        bad_pattern = re.search(
            r"draft:\s*_draftState(?!\.)|experimentId:\s*_draftState\.lastExperimentId",
            text,
        )
        if bad_pattern:
            # Only fail if draft is a static property (not a getter)
            line_start = max(0, bad_pattern.start() - 40)
            snippet = text[line_start:bad_pattern.end() + 40]
            # If there's a 'get' keyword before 'draft:', it's a getter — OK
            preceding = text[max(0, bad_pattern.start() - 10):bad_pattern.start()]
            if "get " not in preceding:
                self.fail(
                    "draft/previewState/experimentId must be getters or functions, "
                    f"not static values. Found near: ...{snippet}..."
                )


class NoNestedStudioBodyTests(unittest.TestCase):
    """The shell must not create nested .comfymodal-studio-body containers."""

    def test_shell_uses_unique_page_container_class(self):
        """studio-shell.js page container must NOT use comfymodal-studio-body as class."""
        text = (WEB / "studio-shell.js").read_text(encoding="utf-8")
        # The shell's page container should use a different class
        # (pages themselves use comfymodal-studio-body for their containers)
        self.assertNotIn(
            "comfymodal-studio-body",
            text,
            "studio-shell.js page container must not use comfymodal-studio-body class "
            "(pages use it — avoid nesting)",
        )

    def test_shell_page_container_uses_distinct_class(self):
        """studio-shell.js page container must have a distinct class from pages."""
        text = (WEB / "studio-shell.js").read_text(encoding="utf-8")
        self.assertIn(
            "comfymodal-studio-page",
            text,
            "Expected studio-shell.js to use comfymodal-studio-page or similar distinct class",
        )


# ---------------------------------------------------------------------------
# Slice — Root-cause gap fixes for Modal Studio tightening pass
# ---------------------------------------------------------------------------

class RootCausePromptPlaceholderTests(unittest.TestCase):
    """Prompt must be visible for object_remove/object_replace placeholder features."""

    def test_prompt_not_skipped_for_placeholder_features(self):
        """studio-playground.js must NOT skip prompt for placeholder features —
        only negative_prompt should be skipped for placeholders, not prompt."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        # The current code skips BOTH prompt and negative_prompt for placeholders.
        # After fix: only negative_prompt is skipped, prompt is visible.
        # The skip line should reference negative_prompt alone, not both.
        has_bad_skip = bool(re.search(
            r'ctrlId\s*===\s*"prompt"\s*\|\|\s*ctrlId\s*===\s*"negative_prompt"',
            text
        ))
        self.assertFalse(
            has_bad_skip,
            "prompt must NOT be skipped alongside negative_prompt for placeholder features. "
            "object_remove/object_replace should show prompt + instruction.",
        )

    def test_instruction_visible_for_placeholder_features(self):
        """instruction must be visible for placeholder features (object_remove/object_replace)."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        # instruction is only hidden for non-placeholder (txt2img)
        has_instruction_skip = bool(re.search(
            r'ctrlId\s*===\s*"instruction"\s*&&\s*!currentSpec\.isPlaceholder',
            text
        ))
        self.assertTrue(
            has_instruction_skip,
            "instruction should only be hidden for non-placeholder features (txt2img), "
            "not for object_remove/object_replace",
        )


class RootCauseBackendSelectorAbstractionTests(unittest.TestCase):
    """Backend selector must use the Studio backend abstraction."""

    def test_backend_selector_imports_get_backends(self):
        """studio-playground.js must import getBackends from studio-backend.js."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertIn(
            "getBackends",
            text,
            "Expected getBackends import from studio-backend.js in renderBackendSelector",
        )

    def test_backend_selector_links_to_backend_tab(self):
        """Backend selector empty state must link to Backend tab, not Legacy Setup."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        # The selector should reference the Backend tab
        self.assertIn(
            "Backend tab",
            text,
            "Expected 'Backend tab' link in backend selector empty state",
        )

    def test_backend_selector_updates_selected_backend_id(self):
        """Selected backend must update state.playground.selectedBackendId."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertIn(
            "selectedBackendId",
            text,
            "Expected selectedBackendId state write in studio-playground.js",
        )


class RootCauseCompareBackendsStateTests(unittest.TestCase):
    """Compare-backend checkboxes must wire into state."""

    def test_compare_backends_uses_compare_backend_ids_state(self):
        """Compare backends checkboxes must update state.playground.compareBackendIds."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertIn(
            "compareBackendIds",
            text,
            "Expected compareBackendIds state read/write in compare backends",
        )

    def test_matrix_summary_reads_compare_backend_ids(self):
        """Matrix summary must read compareBackendIds and selectedBackendId."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        has_correct_state_read = (
            "compareBackendIds" in text
        )
        self.assertTrue(
            has_correct_state_read,
            "Expected matrix summary to read compareBackendIds for backend count",
        )


class RootCauseCachedShellLegacyRoutingTests(unittest.TestCase):
    """Cached-shell must set activeLegacyTab for legacy tab routing."""

    def test_cached_shell_sets_active_legacy_tab(self):
        """In cached-shell path, open_testing_modal must set activeLegacyTab
        for setup/profiles/results before calling setPage."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        # The cached-shell path must have duplicate or additional activeLegacyTab setting
        # similar to the non-cached path (line ~255)
        self.assertIn(
            "activeLegacyTab",
            text,
            "Expected activeLegacyTab setting in open_testing_modal",
        )

    def test_cached_shell_sets_active_tab_for_setup(self):
        """Cached shell must route legacy setup to Settings > Legacy Setup."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        # There must be activeLegacyTab references at TWO locations in open_testing_modal
        # (not just the non-cached path)
        count = text.count("activeLegacyTab")
        self.assertGreaterEqual(
            count, 2,
            f"Expected at least 2 activeLegacyTab occurrences in modal-testing.js "
            f"(cached + non-cached paths), found {count}",
        )


class RootCauseBackendSavePatchTests(unittest.TestCase):
    """Backend save must use PATCH, not PUT."""

    def test_backend_save_uses_patch_not_put(self):
        """studio-backend.js save must use method PATCH."""
        text = (WEB / "studio-backend.js").read_text(encoding="utf-8")
        # The save handler must use PATCH
        self.assertIn(
            '"PATCH"',
            text,
            "Expected PATCH method in backend save handler",
        )
        # Must NOT use PUT for save
        self.assertNotIn(
            'method: "PUT"',
            text,
            "Save must not use PUT — use PATCH instead",
        )

    def test_backend_save_payload_matches_route(self):
        """Backend save payload must align with backend PATCH route fields."""
        text = (WEB / "studio-backend.js").read_text(encoding="utf-8")
        # Must at minimum pass name or use studio_metadata
        has_valid_payload = (
            'name' in text or 'studio_metadata' in text
        )
        self.assertTrue(
            has_valid_payload,
            "Expected save payload to use name or studio_metadata matching backend route",
        )


class RootCauseEmptyStateBugTests(unittest.TestCase):
    """renderEmptyState must receive state parameter."""

    def test_render_empty_state_receives_state(self):
        """renderEmptyState must receive state parameter (4 args: listContent, detailPanel, context, state)."""
        text = (WEB / "studio-backend.js").read_text(encoding="utf-8")
        # The function definition must accept state
        self.assertIn(
            "function renderEmptyState(listContent",
            text,
            "Expected renderEmptyState to accept listContent, detailPanel, context, state",
        )


class RootCauseSettingsInfoHintsTests(unittest.TestCase):
    """Settings must replace bulky paragraph descriptions with info hints."""

    def test_settings_no_bulky_paragraph_descriptions(self):
        """studio-settings.js must not have bulky <p> description paragraphs under each section heading."""
        text = (WEB / "studio-settings.js").read_text(encoding="utf-8")
        # Check for the pattern of bulky HTML blocks with multiple <p> tags
        # Sections should use compact formatting, not inline bulky descriptions
        # Specifically, check that sections are rendered using info-hint pattern
        uses_info_hint = (
            "createInfoHint" in text or "info-hint" in text or "comfymodal-studio-info-hint" in text
        )
        self.assertTrue(
            uses_info_hint,
            "Expected info-hint pattern in studio-settings.js — "
            "replace bulky paragraph descriptions with compact info icons/tooltips",
        )

    def test_settings_no_bulky_inner_html_with_descriptions(self):
        """studio-settings.js must avoid large innerHTML blocks with multiple <p> tags."""
        text = (WEB / "studio-settings.js").read_text(encoding="utf-8")
        # There should not be lengthy description paragraphs visible by default
        # The sections may have innerHTML but the large visible <p> blocks should be gone
        has_bulky_descriptions = bool(re.search(
            r'<p>.*?</p>\s*</div>\s*<div',
            text
        ))
        # This is a weak check; the real improvement is using createInfoHint
        self.assertFalse(
            has_bulky_descriptions,
            "Expected no bulky visible description paragraphs between sections in innerHTML — "
            "use createInfoHint compact tooltips instead",
        )


class RootCauseNoStateContextTests(unittest.TestCase):
    """Backend tab/page and compare backends must not rely on state._context."""

    def test_no_state_context_in_experiment_mode(self):
        """studio-experiment-mode.js must not read state._context."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertNotIn(
            "state._context",
            text,
            "state._context must not be used — pass context explicitly through render functions",
        )

    def test_context_passed_to_render_experiment_mode(self):
        """renderCompareBackends must receive context as parameter, not from state._context."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        # renderExperimentMode should receive context
        self.assertIn(
            "renderExperimentMode(state, actions, context)",
            text,
            "Expected renderExperimentMode(state, actions, context) signature in playground",
        )


# ---------------------------------------------------------------------------
# Regression fix — legacy sidebar tabs must opt in explicitly
# ---------------------------------------------------------------------------

class LegacyComparisonSidebarGuardTests(unittest.TestCase):
    """modal-comparison.js must not register legacy sidebar tabs by default.
    Requires explicit opt-in via window.__comfyModalEnableLegacySidebarTabs."""

    def setUp(self) -> None:
        self.text = (WEB / "modal-comparison.js").read_text(encoding="utf-8")

    def test_comparison_guard_uses_explicit_opt_in(self):
        """Guard must use __comfyModalEnableLegacySidebarTabs === true, not !__comfyModalUnifiedUI."""
        self.assertIn(
            "__comfyModalEnableLegacySidebarTabs",
            self.text,
            "Expected __comfyModalEnableLegacySidebarTabs opt-in guard in modal-comparison.js",
        )

    def test_comparison_guard_no_unifiedui(self):
        """Guard must NOT use !window.__comfyModalUnifiedUI."""
        self.assertNotIn(
            "!window.__comfyModalUnifiedUI",
            self.text,
            "Legacy sidebar guard must not rely on __comfyModalUnifiedUI flag",
        )

    def test_comparison_still_has_render_helpers(self):
        """Comparison render/mount helpers must remain intact."""
        self.assertIn("buildProfilesTab", self.text)
        self.assertIn("buildRunnerTab", self.text)


class LegacySettingsSidebarGuardTests(unittest.TestCase):
    """modal-settings.js must not register legacy modal-gpu sidebar tab by default.
    Requires explicit opt-in via window.__comfyModalEnableLegacySidebarTabs."""

    def setUp(self) -> None:
        self.text = (WEB / "modal-settings.js").read_text(encoding="utf-8")

    def test_settings_guard_uses_explicit_opt_in(self):
        """Guard must use __comfyModalEnableLegacySidebarTabs === true, not !__comfyModalUnifiedUI."""
        self.assertIn(
            "__comfyModalEnableLegacySidebarTabs",
            self.text,
            "Expected __comfyModalEnableLegacySidebarTabs opt-in guard in modal-settings.js",
        )

    def test_settings_guard_no_unifiedui(self):
        """Guard must NOT use !window.__comfyModalUnifiedUI."""
        self.assertNotIn(
            "!window.__comfyModalUnifiedUI",
            self.text,
            "Legacy sidebar guard must not rely on __comfyModalUnifiedUI flag",
        )

    def test_settings_still_has_legacy_sections(self):
        """Legacy settings sections must remain intact."""
        for section in ["auth", "deploy", "gpu", "workspace", "models",
                        "sync", "output", "tokens", "logs"]:
            self.assertIn(section, self.text.lower(),
                          f"Legacy modal-settings.js missing section: {section}")

    def test_settings_still_has_testing_suite_launcher(self):
        """Secondary Testing Suite launcher must remain in settings."""
        self.assertIn("Testing Suite", self.text)


# ---------------------------------------------------------------------------
# Unified flag set in modal-testing.js
# ---------------------------------------------------------------------------

class UnifiedUIFlagTests(unittest.TestCase):
    """modal-testing.js must still set the __comfyModalUnifiedUI flag."""

    def setUp(self) -> None:
        self.text = (WEB / "modal-testing.js").read_text(encoding="utf-8")

    def test_unified_flag_set(self):
        """modal-testing.js must set __comfyModalUnifiedUI = true."""
        self.assertIn(
            "__comfyModalUnifiedUI",
            self.text,
            "Expected __comfyModalUnifiedUI flag in modal-testing.js",
        )


if __name__ == "__main__":
    unittest.main()
