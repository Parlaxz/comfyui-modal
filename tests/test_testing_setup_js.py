"""H18 Wave G — retirement contract for web/testing-setup.js.

The legacy Setup tab (Comparison profile CRUD residual + inert form
sections + retired Experiment creator notice) was unmounted in Wave E
(H14) and the module file was deleted in Wave G (H18). These tests pin
the retirement: the file is gone and nothing in production references it.
"""
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web"
RETIRED_NAME = "testing-setup.js"


def _code(text: str) -> str:
    """Strip // line comments so documentation may name retired symbols
    while code-level absence is still asserted."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )


class RetiredSetupModuleContractTests(unittest.TestCase):
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

    def test_no_registry_or_loader_reference(self):
        """No product registry/loader may reference the retired module."""
        for name in ["modal-testing.js", "studio-shell.js", "studio-settings.js"]:
            text = _code((WEB / name).read_text(encoding="utf-8"))
            self.assertNotIn(RETIRED_NAME, text, f"{name} must not reference {RETIRED_NAME}")

    def test_legacy_setup_surface_unreachable(self):
        """No route back to legacy Setup: no alias mounts it, no global
        reopens it, and the alias map lands setup on Playground (H10)."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn('setup: "playground"', text)
        code = _code(text)
        for retired in ["mountLegacyTab", "activeLegacyTab", "LEGACY_MODULES"]:
            self.assertNotIn(retired, code)


if __name__ == "__main__":
    unittest.main()
