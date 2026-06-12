import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
UI_PATH = REPO_ROOT / "web" / "modal-settings.js"


class ModalWorkspaceUiAstTests(unittest.TestCase):
    def test_workspace_controls_are_present(self):
        source = UI_PATH.read_text(encoding="utf-8")
        self.assertIn("Swap Workspace", source)
        self.assertIn("Manifest Repair", source)
        self.assertIn("Export Workflow Manifest", source)
        self.assertIn("Import Workflow Manifest", source)
        self.assertIn("Install from Manifest", source)

    def test_workspace_routes_are_called(self):
        source = UI_PATH.read_text(encoding="utf-8")
        self.assertIn("MODAL_PREFIX}/workspaces", source)
        self.assertIn("MODAL_PREFIX}/workspaces/swap", source)
        self.assertIn("MODAL_PREFIX}/manifest/repair/scan", source)
        self.assertIn("MODAL_PREFIX}/manifest/repair/apply", source)
        self.assertIn("MODAL_PREFIX}/manifest/install", source)
        self.assertIn("MODAL_PREFIX}/workflow-manifest/export", source)
        self.assertIn("MODAL_PREFIX}/workflow-manifest/import", source)

    def test_swap_review_does_not_rewrite_body_with_innerhtml_append(self):
        source = UI_PATH.read_text(encoding="utf-8")
        self.assertNotIn("body.innerHTML +=", source)

    def test_swap_review_confirm_preserves_prompt_interrupt_approval(self):
        source = UI_PATH.read_text(encoding="utf-8")
        self.assertIn("confirm_prompt_interrupt: !!data.confirm_prompt_interrupt", source)


if __name__ == "__main__":
    unittest.main()
