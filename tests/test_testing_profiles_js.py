"""H18 Wave G — retirement contract for web/testing-profiles.js.

The Comparison Profiles editor was retired in Wave E (H14, H5 §7/R1) and
the module file was deleted in Wave G (H18). Stored comparison-profile
data and the server-side READ_COMPAT routes survive independently. These
tests pin the retirement: the file is gone and nothing in production
references it.
"""
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web"
RETIRED_NAME = "testing-profiles.js"


def _code(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )


class RetiredProfilesModuleContractTests(unittest.TestCase):
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

    def test_no_comparison_editor_resurrection(self):
        """The profiles alias must never mount a recreated Comparison editor."""
        text = (WEB / "modal-testing.js").read_text(encoding="utf-8")
        self.assertIn('profiles: "playground"', text)
        self.assertIn(
            "Comparison Profiles have retired",
            text,
            "Truthful deprecation copy must remain for the profiles alias",
        )
        code = _code(text)
        self.assertNotIn("mountComparisonProfiles", code)


if __name__ == "__main__":
    unittest.main()
