"""H18 Wave G — retirement contract for web/testing-results.js and
web/testing-ab-slider.js.

The legacy Results tab (read-only legacy Experiment display + Comparison
selection/A-B workspace) was retired in Wave E (H14) and both module
files were deleted in Wave G (H18). History V2 is the sole durable
History; the A/B slider remains a Phase-I capability (never a reason to
retain Comparison). Classes below that target modal-testing.js /
studio-shell.js pin surviving invariants of the modern owners.
"""
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web"
RETIRED_NAMES = ["testing-results.js", "testing-ab-slider.js"]


def _code(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )


class _JsModule:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.text = path.read_text(encoding="utf-8") if path.exists() else ""

    def has_export(self, name: str) -> bool:
        import re
        return bool(
            re.search(
                rf"export\s+(?:(?:async\s+)?function|const|class|let|var)\s+{re.escape(name)}\b",
                self.text,
            )
        )


class RetiredResultsModuleContractTests(unittest.TestCase):
    def test_files_are_absent(self):
        for name in RETIRED_NAMES:
            with self.subTest(name=name):
                self.assertFalse(
                    (WEB / name).exists(),
                    f"web/{name} must stay deleted (Wave G)",
                )

    def test_no_production_importer(self):
        importers = []
        for path in WEB.glob("*.js"):
            code = _code(path.read_text(encoding="utf-8"))
            for name in RETIRED_NAMES:
                if name in code or f"./{name}" in code:
                    importers.append(f"{path.name}->{name}")
        self.assertEqual(importers, [], f"Unexpected importers: {importers}")

    def test_ab_slider_not_mounted_by_production(self):
        """Phase I owns any future compare experience; no live module may
        reference the retired slider."""
        for ep in ["modal-testing.js", "studio-shell.js", "studio-playground.js", "studio-history-v2.js"]:
            self.assertNotIn("testing-ab-slider", _read_web(ep))


def _read_web(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


class ModalShellTests(unittest.TestCase):
    """Surviving-owner invariants (moved with the retirement)."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "modal-testing.js")

    def test_exports_open_testing_modal(self):
        self.assertTrue(self.m.has_export("open_testing_modal"))

    def test_five_modern_pages(self):
        """The Studio shell exposes exactly the five modern pages."""
        shell = _JsModule(WEB / "studio-shell.js")
        for page in ("playground", "history", "workflows", "backend", "settings"):
            with self.subTest(page=page):
                self.assertIn(page, shell.text)

    def test_imports_comfyui_app(self):
        self.assertIn('from "../../scripts/app.js"', self.m.text)


class ShellIntegrationDiagnosticsTests(unittest.TestCase):
    """Diagnostics keys that belong in modal-testing.js (surviving owner)."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "modal-testing.js")

    def test_diagnostics_last_frontend_error_key(self):
        self.assertIn("lastFrontendError", self.m.text)

    def test_diagnostics_supports_frontend_version_or_source_hash(self):
        self.assertTrue(
            "frontendVersion" in self.m.text or "sourceHash" in self.m.text,
            "Expected frontendVersion or sourceHash in modal-testing.js diagnostics",
        )


if __name__ == "__main__":
    unittest.main()
