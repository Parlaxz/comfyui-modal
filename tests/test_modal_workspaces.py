import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "modal_workspaces.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("modal_workspaces.py missing")
    spec = importlib.util.spec_from_file_location("modal_workspaces", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ModalWorkspaceRegistryTests(unittest.TestCase):
    def test_save_and_reload_preserves_active_workspace(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".modal_workspaces.json"
            saved = module.upsert_workspace(
                path,
                label="Studio A",
                token_id="ak-studio-a",
                token_secret="as-studio-a",
                set_active=True,
            )
            loaded = module.load_workspace_registry(path)

        self.assertEqual(saved["active_workspace_id"], loaded["active_workspace_id"])
        self.assertEqual(len(loaded["workspaces"]), 1)
        self.assertEqual(loaded["workspaces"][0]["label"], "Studio A")

    def test_workspace_summary_masks_secret(self):
        module = load_module()
        summary = module.workspace_summary({
            "id": "ws_1",
            "label": "Studio A",
            "token_id": "ak-1234567890",
            "token_secret": "as-abcdefghijklmnopqrstuvwxyz",
            "last_used_at": None,
            "last_deploy_status": "idle",
            "notes": "",
        })

        self.assertEqual(summary["token_id_masked"], "ak-1234…7890")
        self.assertTrue(summary["token_secret_masked"].startswith("as-"))
        self.assertNotIn("token_secret", summary)

    def test_set_active_workspace_updates_last_used(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".modal_workspaces.json"
            first = module.upsert_workspace(path, "Studio A", "ak-a", "as-a", set_active=False)
            second = module.upsert_workspace(path, "Studio B", "ak-b", "as-b", set_active=False)
            second_id = second["workspaces"][1]["id"]

            updated = module.set_active_workspace(path, second_id)
            active = module.get_active_workspace(updated)

        self.assertEqual(active["label"], "Studio B")
        self.assertEqual(updated["active_workspace_id"], second_id)
        self.assertIsNotNone(active["last_used_at"])

    def test_invalid_token_prefix_is_rejected(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".modal_workspaces.json"
            with self.assertRaises(ValueError):
                module.upsert_workspace(path, "Bad", "token-id", "secret", set_active=False)


if __name__ == "__main__":
    unittest.main()
