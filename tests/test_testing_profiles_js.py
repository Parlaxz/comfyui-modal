"""Profiles tab structural tests."""
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


class ProfilesTabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _JsModule(REPO_ROOT / "web" / "testing-profiles.js")
        if not self.m.path.exists():
            raise AssertionError("web/testing-profiles.js missing")

    def test_exports_profiles_tab_render(self):
        self.assertTrue(self.m.has_export("profiles_tab_render"))

    def test_contains_create_from_canvas_controls(self):
        self.assertIn("Create from Canvas", self.m.text)
        self.assertIn("Profile name", self.m.text)

    def test_contains_saved_profiles_workspace_markers(self):
        self.assertIn("testing-profiles-list", self.m.text)
        self.assertIn("testing-profiles-editor", self.m.text)

    def test_contains_profile_lifecycle_actions(self):
        for label in ("Edit", "Validate", "Duplicate", "Delete"):
            with self.subTest(label=label):
                self.assertIn(label, self.m.text)

    def test_contains_mapping_assistant_markers(self):
        self.assertIn("Mapping Assistant", self.m.text)
        self.assertIn("Save Mappings", self.m.text)

    def test_contains_mapping_slot_keys(self):
        for key in ("prompt", "negative_prompt", "seed", "steps", "guidance", "width", "height", "input_image"):
            with self.subTest(key=key):
                self.assertIn(key, self.m.text)

    def test_uses_comparison_profile_create_api(self):
        self.assertIn("/comparison/profiles", self.m.text)
        self.assertIn("detect-slots", self.m.text)


if __name__ == "__main__":
    unittest.main()
