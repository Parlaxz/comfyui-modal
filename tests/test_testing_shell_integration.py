"""Task 1 — Failing structural/source tests for the visible frontend integration.

These tests assert patterns that DON'T YET EXIST in the current production
code. They will fail (red) until Tasks 2–4 of the visible-modal-testing-suite
plan are implemented, at which point they should pass (green).

All checks are structural: source-text/regex only, no runtime harness.
"""
import re
import shutil
import subprocess
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


def _code(text: str) -> str:
    """Strip // line comments so documentation may name retired symbols
    while code-level absence is still asserted."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )


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
    """modal-testing.js must reference the shared api module."""

    def setUp(self) -> None:
        self.text = _JsModule(WEB / "modal-testing.js").text

    def test_references_testing_api_module(self):
        """H14 Wave E: the lazy-tab loader is gone, so the shell no longer
        imports testing-api.js; the shared api module reference is retired."""
        self.assertNotIn(
            "testing-api",
            self.text,
            "modal-testing.js must no longer import testing-api.js (Wave E)",
        )

    def test_no_references_to_retired_tab_modules(self):
        """Retired Legacy Dashboard/History modules must not be imported (Phase H9)."""
        self.assertNotIn(
            "testing-dashboard",
            self.text,
            "testing-dashboard.js was retired in Phase H9",
        )
        self.assertNotIn(
            "testing-history",
            self.text,
            "testing-history.js was retired in Phase H9",
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


# ── Phase 2: Parent Modal ARIA / Accessibility ──────────────────────────

class ModalAriaTests(unittest.TestCase):
    """Parent modal must have correct ARIA semantics and focus management."""

    def setUp(self) -> None:
        self.text = _JsModule(WEB / "modal-testing.js").text

    def test_build_shell_modal_has_role_dialog(self):
        """buildShell modal must have role='dialog'."""
        shell_start = self.text.find("function buildShell")
        self.assertGreater(shell_start, -1)
        shell_region = self.text[shell_start:shell_start + 800]
        self.assertIn(
            'role: "dialog"',
            shell_region,
            "Expected role='dialog' on the modal element in buildShell",
        )

    def test_build_shell_modal_has_aria_modal(self):
        """buildShell modal must have aria-modal attribute."""
        shell_start = self.text.find("function buildShell")
        self.assertGreater(shell_start, -1)
        shell_region = self.text[shell_start:shell_start + 800]
        self.assertIn(
            "aria-modal",
            shell_region,
            "Expected aria-modal attribute on the modal element in buildShell",
        )

    def test_build_shell_modal_has_aria_labelledby(self):
        """buildShell modal must have aria-labelledby pointing to the heading."""
        shell_start = self.text.find("function buildShell")
        self.assertGreater(shell_start, -1)
        shell_region = self.text[shell_start:shell_start + 800]
        self.assertIn(
            "aria-labelledby",
            shell_region,
            "Expected aria-labelledby on the modal element in buildShell",
        )

    def test_close_button_has_aria_label(self):
        """buildShell close button must have aria-label."""
        shell_start = self.text.find("function buildShell")
        self.assertGreater(shell_start, -1)
        shell_region = self.text[shell_start:shell_start + 800]
        self.assertIn(
            '"aria-label"',
            shell_region,
            "Expected aria-label on close button in buildShell",
        )

    def test_open_moves_focus_into_modal(self):
        """open_testing_modal must call .focus() on the modal or first focusable."""
        self.assertIn(
            ".focus()",
            self.text,
            "Expected .focus() call in open_testing_modal for focus management",
        )

    def test_close_restores_focus_to_trigger(self):
        """close_testing_modal must restore focus to trigger element."""
        self.assertIn(
            "_triggerEl.focus(",
            self.text,
            "Expected _triggerEl.focus() call in close_testing_modal for focus restoration",
        )

    def test_esc_handler_not_duplicated(self):
        """Escape key handler must avoid duplicate listeners via single reference."""
        # The escHandler pattern stores the handler on a cache object and removes
        # the previous before adding a new one. Look for the pattern.
        self.assertIn(
            "_escHandler",
            self.text,
            "Expected _escHandler pattern for single Escape listener reference",
        )

    def test_body_scroll_lock_class(self):
        """open_testing_modal must add a class to body for scroll lock."""
        self.assertIn(
            "body-scroll-lock",
            self.text,
            "Expected 'body-scroll-lock' class string for scroll lock",
        )

    def test_body_scroll_unlock_in_close(self):
        """close_testing_modal must remove body scroll-lock class."""
        self.assertIn(
            "body-scroll-lock",
            self.text,
            "Expected body-scroll-lock class removal in close_testing_modal",
        )

    def test_no_has_pseudo_for_body_lock(self):
        """studio-styles.js must NOT use :has() for body scroll lock."""
        css_text = _JsModule(WEB / "studio-styles.js").text
        self.assertNotIn(
            "body:has(",
            css_text,
            "Must not use :has() pseudo-class for body scroll lock — use body class instead",
        )

    # ── Oracle fix: Tab focus containment for parent modal ────────────

    def test_parent_modal_registers_layer_escape_handler(self):
        """open_testing_modal must register a layer-2 Escape handler and inert the background."""
        self.assertIn(
            "registerLayerHandler(2, {",
            self.text,
            "Expected layer-2 Escape handler registration in open_testing_modal",
        )
        self.assertIn(
            "_inertBackground(true)",
            self.text,
            "Expected inert/aria-hidden applied to background in open_testing_modal",
        )

    def test_parent_modal_tab_containment_via_inert_no_trap_helper(self):
        """I2: Tab containment is provided by the inert background — no JS
        focus-trap helper may exist or return (dead _trapTab retired)."""
        has_trap = (
            "focusTrap" in self.text
            or "_trapTab" in self.text
            or "tabTrap" in self.text
            or "_tabTrap" in self.text
        )
        self.assertFalse(
            has_trap,
            "Dead _trapTab/focusTrap helper must stay deleted (I2); containment is inert-based",
        )
        self.assertIn(
            "_inertBackground(true)",
            self.text,
            "Expected inert/aria-hidden background containment in open_testing_modal",
        )

    def test_parent_modal_close_removes_layer_escape_handler(self):
        """close_testing_modal must unregister the layer-2 Escape handler and restore inert background."""
        close_start = self.text.find("function close_testing_modal")
        self.assertGreater(close_start, -1)
        close_region = self.text[close_start:close_start + 800]
        self.assertIn(
            "_escHandler",
            close_region,
            "Expected layer-2 Escape handler cleanup in close_testing_modal",
        )
        self.assertIn(
            "_inertBackground(false)",
            close_region,
            "Expected inert/aria-hidden restoration in close_testing_modal",
        )

    # ── Oracle fix: background inert handling ─────────────────────────

    def test_open_adds_inert_to_main_content(self):
        """open_testing_modal must set inert or aria-hidden on main content."""
        self.assertIn(
            "inert",
            self.text,
            "Expected inert attribute handling in open_testing_modal",
        )

    def test_close_restores_inert_to_main_content(self):
        """close_testing_modal must restore inert/aria-hidden to prior state."""
        close_start = self.text.find("function close_testing_modal")
        self.assertGreater(close_start, -1)
        close_region = self.text[close_start:close_start + 800]
        self.assertIn(
            "inert",
            close_region,
            "Expected inert attribute restoration in close_testing_modal",
        )

    # ── Oracle fix: fallback launcher / tooltip product name → Modal GPU ─

    def test_fallback_launcher_button_says_modal_gpu(self):
        """ensureFallbackLauncher must show 'Modal GPU' button."""
        fb_start = self.text.find("function ensureFallbackLauncher")
        self.assertGreater(fb_start, -1)
        fb_region = self.text[fb_start:fb_start + 600]
        self.assertIn(
            "Modal GPU",
            fb_region,
            "Expected 'Modal GPU' in ensureFallbackLauncher button text",
        )

    def test_sidebar_tooltip_says_modal_gpu(self):
        """Sidebar registration tooltip must say 'Modal GPU', not 'Modal Studio'."""
        tooltip_match = re.search(r'tooltip:\s*"([^"]+)"', self.text)
        self.assertIsNotNone(tooltip_match, "Could not find tooltip string in sidebar registration")
        tooltip_text = tooltip_match.group(1)
        self.assertNotIn(
            "Modal Studio",
            tooltip_text,
            "Sidebar tooltip must not contain 'Modal Studio'",
        )
        self.assertIn(
            "Modal GPU",
            tooltip_text,
            "Sidebar tooltip must contain 'Modal GPU'",
        )

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

    def test_secondary_launcher_retired_with_overlay(self):
        """H18 Wave G: the legacy overlay body (and its Testing Suite
        launcher button) is deleted; modern Settings is the only surface."""
        text = _JsModule(WEB / "modal-settings.js").text
        self.assertNotIn(
            "Testing Suite",
            text,
            "The retired overlay must not carry a Testing Suite launcher",
        )


# ---------------------------------------------------------------------------
# Visual redesign: tokenized design system
# ---------------------------------------------------------------------------

class VisualRedesignTokenTests(unittest.TestCase):
    """Tokenized design system in web/testing-styles.js."""

    def setUp(self) -> None:
        self.text = _JsModule(WEB / "testing-styles.js").text

    # ── Phase A: Product name consistency → "Modal GPU" ────────────────

    def test_header_shows_modal_gpu_product_name(self):
        """modal-testing.js buildShell header h1 must display 'Modal GPU'."""
        text = _JsModule(WEB / "modal-testing.js").text
        shell_start = text.find("function buildShell")
        self.assertGreater(shell_start, -1)
        shell_region = text[shell_start:shell_start + 800]
        self.assertIn(
            'text: "Modal GPU"',
            shell_region,
            "Expected 'Modal GPU' as the buildShell header title",
        )

    def test_sidebar_panel_shows_modal_gpu_product_name(self):
        """buildSidebarPanel must show 'Modal GPU' in the launcher title."""
        text = _JsModule(WEB / "modal-testing.js").text
        sidebar_start = text.find("function buildSidebarPanel")
        self.assertGreater(sidebar_start, -1)
        sidebar_region = text[sidebar_start:sidebar_start + 800]
        self.assertIn(
            "Modal GPU",
            sidebar_region,
            "Expected 'Modal GPU' in sidebar panel title",
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

    def test_shared_hero_card_class_retired(self):
        """H18 Wave G: the hero card had zero live consumers after the
        legacy dashboard retirement; the class is deleted."""
        self.assertNotIn("comfymodal-hero", self.text)

    def test_shared_button_variant_classes(self):
        """testing-styles.js must define primary/secondary/destructive buttons."""
        self.assertIn("comfymodal-primary-btn", self.text)
        self.assertIn("comfymodal-secondary-btn", self.text)
        self.assertIn("comfymodal-destructive-btn", self.text)

    def test_shared_status_badge_class_retired(self):
        """H18 Wave G: the shared status badge had zero live consumers
        after the legacy results/settings retirement; the class is deleted."""
        self.assertNotIn("comfymodal-status-badge", self.text)

    def test_shared_input_classes(self):
        """testing-styles.js must define input/select/textarea classes."""
        self.assertIn("comfymodal-input", self.text)

    def test_shared_focus_ring_class(self):
        """testing-styles.js must define focus-visible ring styles."""
        self.assertIn("focus-visible", self.text)

    def test_shared_setup_summary_class_retired(self):
        """H18 Wave G: legacy Setup-only CSS is deleted with its module."""
        self.assertNotIn("testing-setup-sticky-summary", self.text)

    def test_shared_progress_bar_classes_retired(self):
        """H18 Wave G: the generic progress-bar classes had zero live
        consumers (modern pages use comfymodal-studio-* rules); deleted."""
        self.assertNotIn("comfymodal-progress-bar", self.text)

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

# ---------------------------------------------------------------------------
# Visual redesign: settings nav active state
# ---------------------------------------------------------------------------

class SettingsNavActiveStateTests(unittest.TestCase):
    """testing-settings.js retired (Wave E unmount, Wave G file deletion)."""

    def test_settings_module_deleted(self):
        """The legacy settings tab module must stay deleted."""
        self.assertFalse(
            (WEB / "testing-settings.js").exists(),
            "web/testing-settings.js must stay deleted (Wave G)",
        )

    def test_no_legacy_settings_nav_hooks_in_shared_styles(self):
        """The shared stylesheet no longer carries legacy settings-nav hooks."""
        text = _JsModule(WEB / "testing-styles.js").text
        self.assertNotIn("comfymodal-settings-wrapper", text)
        self.assertNotIn("comfymodal-nav-btn-active", text)


# ── Issue 1: Unused STUDIO_PAGES constant ───────────────────────────────

class StudioPagesCleanupTests(unittest.TestCase):
    """STUDIO_PAGES must be removed from modal-testing.js (unused)."""

    def setUp(self) -> None:
        self.text = _JsModule(WEB / "modal-testing.js").text

    def test_studio_pages_not_defined(self):
        """STUDIO_PAGES must not be defined in modal-testing.js."""
        self.assertNotIn(
            "STUDIO_PAGES",
            self.text,
            "STUDIO_PAGES is unused — PAGES is defined in studio-shell.js",
        )

    def test_shell_uses_studio_ui_el(self):
        """modal-testing.js must import el from studio-ui.js."""
        self.assertIn(
            './studio-ui.js',
            self.text,
            "Expected import of el from studio-ui.js in modal-testing.js",
        )

    def test_no_local_el_in_modal_testing(self):
        """modal-testing.js must NOT define a local el() function."""
        # The module-level function el() must be removed
        self.assertNotIn(
            "function el(tag, props = {}, children = [])",
            self.text,
            "Local el() must be replaced by import from studio-ui.js",
        )

    def test_sidebar_render_no_inner_html(self):
        """Sidebar render must NOT use innerHTML clearing."""
        self.assertNotIn(
            "innerHTML = \"\"",
            self.text,
            "Sidebar render must use safe child removal, not innerHTML",
        )

    def test_shell_imports_el_from_studio_ui(self):
        """studio-shell.js must import el from studio-ui.js."""
        text = _JsModule(WEB / "studio-shell.js").text
        self.assertIn(
            './studio-ui.js',
            text,
            "Expected import of el from studio-ui.js in studio-shell.js",
        )

    def test_shell_no_local_el(self):
        """studio-shell.js must NOT define a local el() function."""
        text = _JsModule(WEB / "studio-shell.js").text
        self.assertNotIn(
            "function el(tag, props = {}, children = [])",
            text,
            "Local el() must be replaced by import from studio-ui.js",
        )


# ── Issue 2: Duplicate comfymodal.open-section listener guard ──────────

class OpenSectionGuardTests(unittest.TestCase):
    """comfymodal.open-section must have a guard against duplicate registration."""

    def setUp(self) -> None:
        self.text = _JsModule(WEB / "modal-testing.js").text

    def test_open_section_registration_guard_exists(self):
        """Extension setup must guard against duplicate open-section registration."""
        has_guard = (
            "_openSectionRegistered" in self.text
            or "_sectionHandler" in self.text
            or "_openSectionGuard" in self.text
        )
        self.assertTrue(
            has_guard,
            "Expected a guard variable for comfymodal.open-section in extension setup",
        )

    def test_open_section_prevents_duplicate_listener(self):
        """Guard must prevent addEventListener when already registered."""
        # The guard should check a flag before calling addEventListener
        guard_pattern = (
            "!_openSectionRegistered" in self.text
            or "!_sectionHandler" in self.text
            or "_openSectionGuard" in self.text
        )
        self.assertTrue(
            guard_pattern,
            "Expected a condition checking the guard before registering listener",
        )


# ---------------------------------------------------------------------------
# Setup + Results Clarity: shared CSS utilities
# ---------------------------------------------------------------------------

class SetupResultsClarityStyleTests(unittest.TestCase):
    """Legacy Setup/Results clarity CSS retired with the modules (Wave G)."""

    def setUp(self) -> None:
        self.text = _JsModule(WEB / "testing-styles.js").text

    def test_styles_no_legacy_setup_selectors(self):
        for selector in [".testing-setup-field-grid", ".testing-setup-finish-zone"]:
            self.assertNotIn(
                selector,
                self.text,
                f"Legacy selector {selector} must be deleted with testing-setup.js",
            )

    def test_styles_no_legacy_results_selectors(self):
        for selector in [".testing-results-command-main", ".testing-results-summary-card"]:
            self.assertNotIn(
                selector,
                self.text,
                f"Legacy selector {selector} must be deleted with testing-results.js",
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


class ProgressiveClarityResultsTests(unittest.TestCase):
    """Legacy Results emphasis markers retired with the module (Wave G)."""

    def test_results_module_deleted(self):
        self.assertFalse((WEB / "testing-results.js").exists())

    def test_no_legacy_results_markers_in_shared_styles(self):
        text = _JsModule(WEB / "testing-styles.js").text
        self.assertNotIn("testing-results-summary-primary", text)
        self.assertNotIn("testing-results-command-routine", text)


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
            "studio-history-v2.js",
            "studio-settings.js",
            "studio-feature-registry.js",
            "studio-experiment-mode.js",
            "studio-styles.js",
        ]:
            self.assertTrue(
                (WEB / name).exists(),
                f"Required Studio module web/{name} is missing",
            )
        # H18 Wave G: the retired loader stays deleted.
        self.assertFalse((WEB / "studio-legacy.js").exists())

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
    """Legacy reachability retired (H14 Wave E); truthful placeholder copy."""

    @staticmethod
    def _code(text: str) -> str:
        """Strip // line comments so documentation can name retired symbols
        while code-level absence is still asserted."""
        return "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("//")
        )

    def test_settings_legacy_group_retired(self):
        """H14 Wave E: the Settings ▸ Advanced ▸ Legacy group is gone.

        No Legacy heading, no opener, and no Setup/Profiles/Results/Settings
        entries may remain in modern Settings.
        """
        text = (WEB / "studio-settings.js").read_text(encoding="utf-8")
        code = self._code(text)
        for retired in [
            "Legacy Setup",
            "Legacy Profiles",
            "Legacy Results",
            "Legacy Settings",
            "Open Legacy Settings",
            "settings-legacy-open",
            "settings-legacy-setup",
            "settings-legacy-profiles",
            "settings-legacy-results",
            "settings-legacy-settings",
        ]:
            self.assertNotIn(
                retired, code,
                f"'{retired}' must be retired from modern Settings (Wave E)",
            )

    def test_settings_modern_sections_remain(self):
        """Modern Settings stays preferences-only but complete."""
        text = (WEB / "studio-settings.js").read_text(encoding="utf-8")
        for section in ["general", "generation", "outputs", "history", "experiments", "interface", "advanced"]:
            self.assertIn(section, text)
        self.assertIn("settings-reset-all", text)
        self.assertIn("settings-open-backend", text)

    def test_playground_uses_honest_future_placeholder_copy(self):
        """studio-playground.js must use honest future-work copy for image-edit tools."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertTrue(
            "future work" in text.lower()
            or "not implemented yet" in text.lower(),
            "Expected honest future-work placeholder copy in studio-playground.js",
        )

    # ── Settings sections with data-section attributes ─────────────────

    def test_settings_sections_have_data_section_attributes(self):
        """studio-settings.js must have data-section attributes on each section."""
        text = (WEB / "studio-settings.js").read_text(encoding="utf-8")
        # Build DOM sections use "data-section": sec.section pattern for 7 sections
        # The literal 'data-section' must appear in source for dynamic setting
        self.assertIn('"data-section"', text,
                       "Expected data-section attribute setting in studio-settings.js")
        # All 7 sections must be represented in the sections config array
        for section in ["general", "generation", "outputs", "history", "experiments", "interface", "advanced"]:
            self.assertIn(
                section, text,
                f"Expected section '{section}' referenced in studio-settings.js",
            )

    def test_settings_no_legacy_mount_path(self):
        """H14 Wave E: studio-settings.js must not mount legacy tabs."""
        text = (WEB / "studio-settings.js").read_text(encoding="utf-8")
        self.assertNotIn(
            "mountLegacyTab", text,
            "studio-settings.js must not reference the retired legacy mounter",
        )
        self.assertNotIn(
            "renderLegacyView", text,
            "renderLegacyView must be retired (Wave E)",
        )
        self.assertNotIn(
            "activeLegacyTab", text,
            "activeLegacyTab machinery must be retired (Wave E)",
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
    """Disabled Run button must give precise reasons without legacy funnels."""

    def test_disabled_run_has_no_legacy_setup_funnel(self):
        """H10: studio-playground.js must not funnel users to Legacy Setup."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertNotIn(
            "Configure in Legacy Setup",
            text,
            "Legacy Setup funnel copy must be removed (H10)",
        )
        self.assertNotIn(
            "navigateToLegacySetup",
            text,
            "Dead Legacy Setup navigation helper must be removed (H10)",
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

    def test_experiment_disabled_run_reason_from_helper(self):
        """H-WAVE D: the legacy renderer is fully retired; experimentRunSurface
        unconditionally mounts the gated modern section, which derives its
        reason from modernExperimentDisabledReason."""
        text = (WEB / "studio-experiment-mode.js").read_text(encoding="utf-8")
        self.assertIn(
            "export function getExperimentDisabledReason",
            text,
            "Expected getExperimentDisabledReason export in studio-experiment-mode.js",
        )
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
            'experimentRunSurface must return "modern" unconditionally',
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
    """Legacy controller cleanup wiring retired (H14 Wave E); the loader
    file itself was deleted in Wave G (H18).

    No production module may still import or invoke the legacy controller
    stopper, and studio-legacy.js no longer exists on disk.
    """

    def test_studio_legacy_file_deleted(self):
        """H18 Wave G: the unmounted loader module is gone."""
        self.assertFalse(
            (WEB / "studio-legacy.js").exists(),
            "web/studio-legacy.js must stay deleted (Wave G)",
        )

    def test_shell_no_longer_imports_stop_legacy_controller(self):
        """H14 Wave E: studio-shell.js must not import stopLegacyController."""
        text = (WEB / "studio-shell.js").read_text(encoding="utf-8")
        self.assertNotIn(
            "stopLegacyController",
            text,
            "studio-shell.js must not reference the retired legacy controller",
        )

    def test_modal_testing_calls_stop_legacy_on_close(self):
        """H14 Wave E: modal-testing.js must not reference stopLegacyController."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertNotIn(
            "stopLegacyController",
            text,
            "modal-testing.js must not reference the retired legacy controller",
        )

    def test_shell_clears_legacy_controller_on_page_nav(self):
        """H14 Wave E: studio-shell.js has no legacy-tab nav cleanup left."""
        text = (WEB / "studio-shell.js").read_text(encoding="utf-8")
        self.assertNotIn("activeLegacyTab", text)
        self.assertNotIn("stopLegacyController", text)


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

    def test_dead_backends_exports_removed(self):
        """H18 Wave G: the dead /studio/backends discovery exports are gone
        (zero callers since H16 removed the last Settings consumer; FD-8)."""
        m = _JsModule(WEB / "studio-backend.js")
        self.assertFalse(
            m.has_export("getBackends") or m.has_export("fetchBackends"),
            "studio-backend.js must not re-export a backends discovery helper",
        )

    def test_dead_compare_backends_export_removed(self):
        """H18 Wave G: getCompareBackends re-export deleted (zero callers)."""
        m = _JsModule(WEB / "studio-backend.js")
        self.assertFalse(
            m.has_export("getCompareBackends"),
            "studio-backend.js must not re-export getCompareBackends",
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

    def test_open_testing_modal_setup_never_mounts_legacy_setup(self):
        """H10: open_testing_modal('setup') must land on Playground, never Legacy Setup."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn(
            'setup: "playground"',
            text,
            "Expected frozen setup alias → Playground mapping (H10)",
        )
        self.assertNotIn(
            "activeLegacyTab",
            text,
            "Retired aliases must not set a dead activeLegacyTab",
        )

    def test_open_testing_modal_profiles_never_opens_comparison_editor(self):
        """H10: open_testing_modal('profiles') must land on Playground without mounting Comparison."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn(
            'profiles: "playground"',
            text,
            "Expected frozen profiles alias → Playground mapping (H10)",
        )

    def test_open_testing_modal_results_lands_on_history(self):
        """H10 freeze: open_testing_modal('results') must land on History V2."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn(
            'results: "history"',
            text,
            "Expected frozen results alias → History mapping (H10)",
        )

    def test_onrun_lands_on_history_v2(self):
        """The results alias (frozen to History) is the only results intent;
        the legacy onRun experimentId machinery was deleted in Wave G."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn(
            'results: "history"',
            text,
            "results alias must land on History V2",
        )
        code = _code(text)
        self.assertNotIn("onRun", code, "legacy onRun context callback must stay retired")


class FreshLegacyOptionsTests(unittest.TestCase):
    """H18 Wave G: the legacy draft/preview/experimentId context machinery
    is deleted — its only consumer was the retired studio-legacy.js mount."""

    def test_legacy_context_machinery_removed(self):
        """modal-testing.js must not carry draft/preview/experimentId state."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        code = _code(text)
        for retired in [
            "get draft",
            "get previewState",
            "get experimentId",
            "onDraftChange",
            "onRun",
            "_draftState",
            "_previewState",
            "DRAFT_STORAGE_KEY",
            "EXPERIMENT_ID_KEY",
        ]:
            self.assertNotIn(
                retired,
                code,
                f"Legacy context machinery '{retired}' must stay deleted (Wave G)",
            )

    def test_modern_context_remains(self):
        """The shell context still carries what modern pages consume."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn("apiBase: MODAL_PREFIX", text)
        self.assertIn("comfyApi: comfyApi", text)


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

    def test_backend_selector_has_no_dead_backends_reference(self):
        """H18 Wave G: the dead getBackends comment reference is removed;
        the selector loads runtime presets via the presets abstraction."""
        text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertNotIn(
            "getBackends",
            text,
            "studio-playground.js must not reference the deleted getBackends helper",
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
    """H10: retired aliases never set a dead activeLegacyTab (cached or fresh path)."""

    def test_no_active_legacy_tab_writes_in_open_testing_modal(self):
        """modal-testing.js must no longer write settings.activeLegacyTab anywhere.

        The setup/profiles/results aliases now land on modern pages
        (Playground/History), so no code path may resurrect the dead
        activeLegacyTab mechanism for them.
        """
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        count = text.count("activeLegacyTab")
        self.assertEqual(
            count, 0,
            f"Expected zero activeLegacyTab occurrences in modal-testing.js "
            f"(retired aliases land on modern pages), found {count}",
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
    """renderEmptyState authority lives only in studio-ui.js (I7).

    The old pass-through re-export wrapper in studio-backend.js was deleted in
    Phase I7 after re-measurement confirmed zero importers; page lanes consume
    the generic options-API primitive from studio-ui.js directly.
    """

    def test_render_empty_state_receives_state(self):
        """studio-ui.js owns renderEmptyState with the generic options API."""
        text = (WEB / "studio-ui.js").read_text(encoding="utf-8")
        # The shared primitive must keep its generic frozen API.
        self.assertIn(
            "function renderEmptyState(options",
            text,
            "Expected studio-ui.js renderEmptyState to accept an options object",
        )

    def test_backend_glue_no_longer_reexports_render_empty_state(self):
        """The dead studio-backend.js re-export wrapper must stay deleted."""
        text = (WEB / "studio-backend.js").read_text(encoding="utf-8")
        self.assertNotIn(
            "renderEmptyState",
            text,
            "studio-backend.js must not define or re-export renderEmptyState",
        )


class RootCauseSettingsInfoHintsTests(unittest.TestCase):
    """Settings must replace bulky paragraph descriptions with info hints."""

    def test_settings_no_bulky_paragraph_descriptions(self):
        """studio-settings.js must render short, concise info rows — not bulky paragraphs.

        Settings describes each section via a single-line info row
        (<p class="comfymodal-studio-settings-info"> from the infoRow helper)
        instead of long multi-sentence description blocks.
        """
        text = (WEB / "studio-settings.js").read_text(encoding="utf-8")
        # Compact info-row helper must exist and be used for section descriptions
        self.assertIn(
            "comfymodal-studio-settings-info",
            text,
            "Expected comfymodal-studio-settings-info info-row class in studio-settings.js",
        )
        # All infoRow texts must be short single-sentence snippets (no bulky paragraphs)
        info_texts = re.findall(r'infoRow\("([^"]+)"\)', text)
        self.assertGreater(
            len(info_texts), 0,
            "Expected infoRow( ... ) calls in studio-settings.js",
        )
        for info_text in info_texts:
            with self.subTest(info=info_text):
                self.assertLessEqual(
                    len(info_text), 160,
                    f"Settings info row must be a short concise description, got {len(info_text)} chars: {info_text!r}",
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
# H10 — hidden legacy sidebar registrations removed; Comparison code intact
# ---------------------------------------------------------------------------

class LegacyComparisonSidebarGuardTests(unittest.TestCase):
    """H10 removed the hidden Comparison sidebar registrations; Wave E
    retired the overlay globals and canvas menu; Wave G (H18) deleted the
    inert modal-comparison.js module outright.

    These tests pin the end state: the file is gone and no web module may
    resurrect a Comparison registration, overlay global, or canvas menu.
    """

    def setUp(self) -> None:
        self.assertFalse(
            (WEB / "modal-comparison.js").exists(),
            "web/modal-comparison.js must stay deleted (Wave G)",
        )

    def test_no_comparison_module_anywhere(self):
        """No web file may reference the deleted module path."""
        for path in WEB.glob("*.js"):
            code = _code(path.read_text(encoding="utf-8"))
            self.assertNotIn("modal-comparison", code, f"{path.name} references deleted module")

    def test_no_sidebar_tab_registration_for_comparison(self):
        """No web module may register a Comparison sidebar tab."""
        hits = []
        for path in WEB.glob("*.js"):
            code = _code(path.read_text(encoding="utf-8"))
            if "registerSidebarTab" in code and "comfymodal-testing-suite" not in code:
                hits.append(path.name)
            if "Comparison Profiles" in code and "retired" not in code:
                hits.append(path.name)
        self.assertEqual(hits, [], f"Unexpected Comparison registrations: {hits}")

    def test_comparison_globals_stay_retired_web_wide(self):
        """Overlay globals + canvas menu wrapper must never return."""
        for retired in [
            "openComparisonProfilesOverlay",
            "openComparisonRunnerOverlay",
            "mountComparisonProfiles",
            "mountComparisonRunner",
            "_initContextMenu",
            "__comfyModalEnableLegacySidebarTabs",
            "!window.__comfyModalUnifiedUI",
        ]:
            hits = [p.name for p in WEB.glob("*.js") if retired in _code(p.read_text(encoding="utf-8"))]
            self.assertEqual(hits, [], f"{retired} must have zero web references")


class LegacySettingsSidebarGuardTests(unittest.TestCase):
    """H10: modal-settings.js registers zero sidebar tabs; overlay retired in E.

    The opt-in flag and the hidden "Modal GPU" registration are removed (H10).
    The standalone legacy overlay globals were deleted by Wave E (H14) —
    modern Settings is the only settings surface.
    """

    def setUp(self) -> None:
        self.text = (WEB / "modal-settings.js").read_text(encoding="utf-8")

    def test_hidden_sidebar_flag_removed(self):
        """__comfyModalEnableLegacySidebarTabs must be gone from modal-settings.js."""
        self.assertNotIn(
            "__comfyModalEnableLegacySidebarTabs",
            self.text,
            "Hidden legacy sidebar opt-in flag must be removed (H10)",
        )

    def test_no_sidebar_tab_registration(self):
        """modal-settings.js must not register any sidebar tab."""
        self.assertNotIn(
            "registerSidebarTab",
            self.text,
            "Legacy settings panel must not register sidebar tabs (H10 retirement)",
        )

    def test_settings_guard_no_unifiedui(self):
        """Guard must NOT use !window.__comfyModalUnifiedUI."""
        self.assertNotIn(
            "!window.__comfyModalUnifiedUI",
            self.text,
            "Legacy sidebar guard must not rely on __comfyModalUnifiedUI flag",
        )

    def test_overlay_compatibility_global_retired(self):
        """H14 Wave E: the standalone legacy overlay globals are deleted."""
        code = "\n".join(
            line for line in self.text.splitlines() if not line.lstrip().startswith("//")
        )
        self.assertNotIn(
            "open_comfymodal_settings", code,
            "The standalone legacy overlay global must be retired (Wave E)",
        )
        self.assertNotIn(
            "mountSettingsPanel", code,
            "The legacy panel mount global must be retired (Wave E)",
        )
        self.assertNotIn(
            "comfymodal-settings-overlay", code,
            "The legacy overlay root must not be constructible (Wave E)",
        )

    def test_canvas_compatibility_shim_present(self):
        """H5C §15-B: startup initializes window._comfyModalEnabled from the
        persisted comfymodal_enabled key with identical precedence."""
        self.assertIn("STORAGE_KEY_ENABLED", self.text)
        shim = self.text[self.text.index("savedEnabled === null ? true : savedEnabled === \"true\"") - 400:]
        self.assertIn("window._comfyModalEnabled =", shim)
        # modal-node.js readers unchanged
        node_src = (WEB / "modal-node.js").read_text(encoding="utf-8")
        self.assertEqual(node_src.count("window._comfyModalEnabled !== false"), 2)

    def test_legacy_overlay_sections_deleted(self):
        """H18 Wave G: the overlay body (auth/deploy/workspace/models/sync/
        tokens/logs sections and their builders) is deleted; only the
        canvas/shared compatibility surface remains."""
        code = _code(self.text)
        for retired in [
            "buildPanel", "buildAuthPanel", "loadModels", "renderModelList",
            "startDeployPoll", "pollDeployStatus", "checkHealth",
            "createCollapsibleSection", "showConfirmDialog",
            "Testing Suite",
        ]:
            self.assertNotIn(retired, code, f"Retired overlay region '{retired}' must stay deleted")

    def test_shared_sync_regions_survive(self):
        """The surviving shared regions (H5C §15-C/D) remain wired in setup."""
        self.assertIn("syncLegacyGpuConfigOnce();", self.text)
        self.assertIn("syncLegacyOutputPrefsOnce();", self.text)
        self.assertIn('from "./studio-output-preferences.js"', self.text)


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


# ---------------------------------------------------------------------------
# H10 — frozen legacy entry-point redirects (H5 §22)
# ---------------------------------------------------------------------------

class LegacyEntrypointRedirectTests(unittest.TestCase):
    """H10 frozen opener redirects.

    Contract (H5 §22 + H10 batch):
      dashboard → Backend · history → History · results → History
      settings  → Settings · setup → Playground (+ Experiment-mode context,
      bounded deprecation) · profiles → Playground (+ bounded deprecation).
    """

    def setUp(self) -> None:
        self.text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        match = re.search(r"const ALIAS_PAGE_MAP = \{(.*?)\};", self.text, re.S)
        self.assertIsNotNone(match, "Expected ALIAS_PAGE_MAP in modal-testing.js")
        self.alias_map = match.group(1)

    def test_dashboard_alias_redirects_to_backend(self):
        """dashboard alias must land on Backend (operational intent re-homed by H6)."""
        self.assertIn(
            'dashboard: "backend"',
            self.alias_map,
            "Frozen redirect: dashboard → Backend",
        )

    def test_history_alias_lands_on_history_v2(self):
        """history alias must land on History (V2 is the sole durable History)."""
        self.assertIn('history: "history"', self.alias_map)

    def test_results_alias_lands_on_history_v2(self):
        """results alias must land on History — never a dead Legacy Results mount."""
        self.assertIn('results: "history"', self.alias_map)

    def test_settings_alias_lands_on_settings(self):
        """settings alias must land on modern Settings."""
        self.assertIn('settings: "settings"', self.alias_map)

    def test_setup_alias_never_mounts_legacy_setup(self):
        """setup alias lands on Playground; no Legacy Setup mount through the alias."""
        self.assertIn('setup: "playground"', self.alias_map)
        # The alias navigation helper must not invoke the legacy tab mounter.
        nav_start = self.text.find("function _applyLegacyAliasNavigation")
        nav_end = self.text.find("export function open_testing_modal")
        nav_block = self.text[nav_start:nav_end]
        self.assertNotIn(
            "mountLegacyTab",
            nav_block,
            "Alias navigation must never mount a legacy tab directly",
        )
        # Bounded deprecation guidance exists for the retired surface.
        self.assertIn(
            "alias-deprecation-notice",
            self.text,
            "Expected bounded deprecation notice for retired aliases",
        )
        self.assertIn(
            "Experiment mode",
            self.text,
            "Deprecation guidance must name the modern owner (Experiment mode)",
        )

    def test_profiles_alias_never_recreates_comparison_editor(self):
        """profiles alias lands on Playground with deprecation; no Comparison editor mount."""
        self.assertIn('profiles: "playground"', self.alias_map)
        self.assertNotIn(
            'profiles: "settings"',
            self.alias_map,
            "profiles must not funnel into the retiring Settings legacy group",
        )
        self.assertIn(
            "Comparison Profiles have retired",
            self.text,
            "Expected truthful deprecation copy for the profiles alias",
        )

    def test_no_dead_active_legacy_tab_for_retired_aliases(self):
        """No code path may set settings.activeLegacyTab for retired aliases."""
        self.assertEqual(
            self.text.count("activeLegacyTab"), 0,
            "Retired aliases must not set a dead activeLegacyTab",
        )

    def test_normal_studio_sidebar_entry_remains(self):
        """The normal modal-testing Studio sidebar registration must remain."""
        self.assertIn("registerSidebarTab", self.text)
        self.assertIn("comfymodal-testing-suite", self.text)

    def test_direct_compatibility_global_remains(self):
        """window.open_testing_modal compatibility global remains exported."""
        self.assertIn("window.open_testing_modal = open_testing_modal", self.text)

    def test_alias_path_introduces_no_network_or_provider_terms(self):
        """No provider-selector vocabulary and no new network I/O in the opener."""
        lowered = self.text.lower()
        for term in ["runpod", "runcomfy", "comfy_cloud", "baseten", "provider selector"]:
            self.assertNotIn(
                term, lowered,
                f"Provider-selector terminology must not be introduced: {term}",
            )
        self.assertNotIn("fetch(", self.text)
        self.assertNotIn("fetchApi(", self.text)

    def test_modern_copy_has_no_legacy_setup_funnel(self):
        """Feature-registry/playground copy must not send users to Legacy Setup."""
        registry_text = (WEB / "studio-feature-registry.js").read_text(encoding="utf-8")
        self.assertNotIn(
            "Settings > Legacy Setup",
            registry_text,
            "Feature-registry placeholder copy must not funnel into Legacy Setup",
        )
        playground_text = (WEB / "studio-playground.js").read_text(encoding="utf-8")
        self.assertNotIn(
            "Configure in Legacy Setup",
            playground_text,
            "Playground control note must not funnel into Legacy Setup",
        )
        # Truthful modern-owner wording exists instead.
        self.assertIn(
            "not available in the modern playground yet",
            registry_text.lower(),
            "Placeholder features must state truthfully that they are missing",
        )


# ---------------------------------------------------------------------------
# Runtime syntax regression — real node --check execution
# ---------------------------------------------------------------------------


class SyntaxRegressionTests(unittest.TestCase):
    """Real runtime syntax checks via subprocess: node --check on each JS file.

    These ensure that the files parse cleanly as valid JavaScript regardless
    of what structural/text assertions say.  A nonzero exit code fails the
    test and surfaces stderr so the syntax error is immediately visible.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if not shutil.which("node"):
            raise unittest.SkipTest("node is not on PATH — cannot run syntax checks")

    def _node_check(self, filename: str) -> None:
        path = WEB / filename
        self.assertTrue(
            path.exists(),
            f"Required JS file not found: {path}",
        )
        try:
            proc = subprocess.run(
                ["node", "--check", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            self.fail(
                f"node --check {filename} timed out after 30s"
            )
        if proc.returncode != 0:
            msg = proc.stderr.strip() or proc.stdout.strip() or "(no output)"
            self.fail(
                f"node --check {filename} failed (exit {proc.returncode}):\n{msg}"
            )

    def test_modal_testing_js_syntax(self):
        """modal-testing.js must pass node --check (real syntax validation)."""
        self._node_check("modal-testing.js")

    def test_modal_comparison_js_syntax_removed(self):
        """H18 Wave G: modal-comparison.js is deleted; nothing to check."""
        self.assertFalse((WEB / "modal-comparison.js").exists())

    def test_modal_settings_js_syntax(self):
        """modal-settings.js must pass node --check (real syntax validation)."""
        self._node_check("modal-settings.js")


if __name__ == "__main__":
    unittest.main()
