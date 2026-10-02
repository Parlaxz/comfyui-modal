"""H18 Wave G — retirement contract for web/testing-settings.js.

The legacy Settings tab (embedder for the retired standalone overlay)
was retired in Wave E (H14, H5C §11/FC-11) and the module file was
deleted in Wave G (H18). Modern Settings is the only settings surface.
These tests pin the retirement and the surviving modern-owner invariants.
"""
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web"
RETIRED_NAME = "testing-settings.js"


def _code(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )


class RetiredSettingsModuleContractTests(unittest.TestCase):
    def test_file_is_absent(self):
        self.assertFalse(
            (WEB / RETIRED_NAME).exists(),
            f"web/{RETIRED_NAME} must stay deleted (Wave G)",
        )

    def test_no_production_importer(self):
        importers = []
        for path in WEB.glob("*.js"):
            code = _code(path.read_text(encoding="utf-8"))
            if RETIRED_NAME in code or f"./{RETIRED_NAME}" in code:
                importers.append(path.name)
        self.assertEqual(importers, [], f"Unexpected importers of {RETIRED_NAME}: {importers}")

    def test_standalone_overlay_stays_unreachable(self):
        """The overlay globals retired in Wave E must never return."""
        code = _code((WEB / "modal-settings.js").read_text(encoding="utf-8"))
        for retired in ["open_comfymodal_settings", "mountSettingsPanel", "buildPanel"]:
            self.assertNotIn(retired, code)

    def test_open_section_redirect_survives(self):
        """comfymodal.open-section still lands on modern Settings."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn("comfymodal.open-section", text)
        self.assertIn('settings: "settings"', text)


if __name__ == "__main__":
    unittest.main()
