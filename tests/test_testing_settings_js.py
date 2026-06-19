"""Phase 11 — Settings tab structural tests."""
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

    def contains(self, s: str) -> bool:
        return s in self.text


class SettingsTabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "testing-settings.js")
        if not self.m.text:
            self.skipTest("web/testing-settings.js missing")

    def test_exports_settings_tab_render(self):
        self.assertTrue(self.m.has_export("settings_tab_render"))

    def test_contains_all_sections(self):
        # 9 sections per parent plan §16
        for section in (
            "Connection & credentials",
            "Deployment & runtime",
            "GPU",
            "Workspace",
            "Models",
            "Custom nodes & sync",
            "Output defaults",
            "Tokens",
            "Logs & diagnostics",
        ):
            with self.subTest(section=section):
                self.assertIn(section, self.m.text)

    def test_emits_comfymodal_open_section_event(self):
        # The bridge: clicking a section dispatches a custom event
        # the legacy modal-settings.js listens for.
        self.assertIn("comfymodal.open-section", self.m.text)

    def test_no_framework_imports(self):
        for forbidden in ("from 'react'", 'from "react"', "from 'preact'",
                          "from 'vue'", "from 'svelte'"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.m.text)


class ModalShellSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "modal-testing.js")
        if not self.m.text:
            self.skipTest("web/modal-testing.js missing")

    def test_dispatches_to_settings_tab(self):
        # The shell should have a mountSettingsTab function or call the
        # settings module.
        self.assertIn("mountSettingsTab", self.m.text)
        self.assertIn("TAB_SETTINGS", self.m.text)

    def test_settings_tab_no_longer_shows_placeholder_message(self):
        # Phase 11 wires up the settings tab; the old placeholder
        # message should be gone.
        self.assertNotIn("Settings tab is wired in Phase 11", self.m.text)




class LegacySettingsIntegrationTests(unittest.TestCase):
    """Tests for embedded settings mount hooks and the secondary Testing Suite launcher.

    These are failing structural tests for Task 1: they assert patterns that
    don't exist yet in the legacy modal-settings.js but will be added in
    Tasks 2–4 of the visible-modal-testing-suite plan.
    """

    def test_embedded_mount_hooks_in_modal_settings(self):
        """modal-settings.js must expose reusable mount/open helpers."""
        text = _JsModule(REPO_ROOT / "web" / "modal-settings.js").text
        self.assertIn(
            "mountSettingsPanel",
            text,
            "Expected mountSettingsPanel export from modal-settings.js "
            "for embedded reuse in the testing suite",
        )

    def test_secondary_launcher_in_modal_settings(self):
        """modal-settings.js must include a 'Testing Suite' secondary launcher."""
        text = _JsModule(REPO_ROOT / "web" / "modal-settings.js").text
        self.assertIn(
            "Testing Suite",
            text,
            "Expected a 'Testing Suite' button/action inside the legacy modal-settings.js",
        )

    def test_modal_testing_handles_comfymodal_open_section(self):
        """modal-testing.js must listen for comfymodal.open-section to bridge settings."""
        m = _JsModule(REPO_ROOT / "web" / "modal-testing.js")
        if not m.text:
            self.skipTest("web/modal-testing.js missing")
        self.assertIn(
            "comfymodal.open-section",
            m.text,
            "Expected comfymodal.open-section event listener in modal-testing.js",
        )


# ---------------------------------------------------------------------------
# Visual redesign: wrapper/nav active-state hooks
# ---------------------------------------------------------------------------

class SettingsNavActiveStateTests(unittest.TestCase):
    """Settings nav active-state and responsive wrapper hooks."""

    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "testing-settings.js")
        if not self.m.text:
            self.skipTest("web/testing-settings.js missing")

    def test_settings_wrapper_class_hook(self):
        """testing-settings.js must use comfymodal-settings-wrapper."""
        self.assertIn(
            "comfymodal-settings-wrapper",
            self.m.text,
            "Expected comfymodal-settings-wrapper class",
        )

    def test_settings_nav_btn_active_class(self):
        """testing-settings.js must reference shared nav active class."""
        self.assertIn(
            "comfymodal-nav-btn-active",
            self.m.text,
            "Expected comfymodal-nav-btn-active class for active nav state",
        )

    def test_settings_responsive_wrapper_hook(self):
        """testing-settings.js must have a responsive wrapper or breakpoint class."""
        text = self.m.text
        has_responsive = (
            "comfymodal-settings-responsive" in text
            or "@media" in text
            or "collapse" in text.lower() and "nav" in text.lower()
        )
        self.assertTrue(
            has_responsive,
            "Expected responsive handling hook in testing-settings.js",
        )


if __name__ == "__main__":
    unittest.main()
