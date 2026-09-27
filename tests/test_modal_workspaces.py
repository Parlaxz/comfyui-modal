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

    def test_update_workspace_preserves_existing_tokens_when_left_blank(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".modal_workspaces.json"
            initial = module.upsert_workspace(path, "Studio A", "ak-original", "as-original", set_active=True)
            workspace_id = initial["workspaces"][0]["id"]

            updated = module.upsert_workspace(
                path,
                label="Studio A Renamed",
                token_id="",
                token_secret="",
                workspace_id=workspace_id,
                set_active=False,
            )

        self.assertEqual(updated["workspaces"][0]["label"], "Studio A Renamed")
        self.assertEqual(updated["workspaces"][0]["token_id"], "ak-original")
        self.assertEqual(updated["workspaces"][0]["token_secret"], "as-original")

    def test_update_workspace_by_id_does_not_create_duplicate_entry(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".modal_workspaces.json"
            initial = module.upsert_workspace(path, "Studio A", "ak-original", "as-original", set_active=True)
            workspace_id = initial["workspaces"][0]["id"]

            updated = module.upsert_workspace(
                path,
                label="Studio A Renamed",
                token_id="ak-updated",
                token_secret="as-updated",
                workspace_id=workspace_id,
                set_active=False,
            )

        self.assertEqual(len(updated["workspaces"]), 1)
        self.assertEqual(updated["workspaces"][0]["id"], workspace_id)
        self.assertEqual(updated["workspaces"][0]["label"], "Studio A Renamed")

    # ── Legacy ~/.modal.toml migration ────────────────────────────────

    def test_migrate_from_legacy_toml_creates_workspace(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / ".modal_workspaces.json"
            toml_path = Path(tmp) / ".modal.toml"
            toml_path.write_text(
                '[default]\ntoken_id = "ak-legacy-token"\ntoken_secret = "as-legacy-secret"\n',
                encoding="utf-8",
            )
            registry = module.migrate_from_legacy_toml(registry_path, toml_path)
            self.assertEqual(len(registry["workspaces"]), 1)
            self.assertEqual(registry["workspaces"][0]["label"], "Legacy Modal Token")
            self.assertEqual(registry["workspaces"][0]["token_id"], "ak-legacy-token")
            self.assertEqual(registry["workspaces"][0]["token_secret"], "as-legacy-secret")
            self.assertIsNotNone(registry["active_workspace_id"])

    def test_migrate_from_legacy_toml_skips_when_registry_not_empty(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / ".modal_workspaces.json"
            toml_path = Path(tmp) / ".modal.toml"
            # Pre-populate registry
            module.upsert_workspace(registry_path, "Existing", "ak-existing", "as-existing", set_active=True)
            toml_path.write_text(
                '[default]\ntoken_id = "ak-other"\ntoken_secret = "as-other"\n',
                encoding="utf-8",
            )
            registry = module.migrate_from_legacy_toml(registry_path, toml_path)
            self.assertEqual(len(registry["workspaces"]), 1)
            self.assertEqual(registry["workspaces"][0]["label"], "Existing")

    def test_migrate_from_legacy_toml_skips_when_toml_missing(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / ".modal_workspaces.json"
            toml_path = Path(tmp) / ".modal.toml"  # does not exist
            registry = module.migrate_from_legacy_toml(registry_path, toml_path)
            self.assertEqual(len(registry["workspaces"]), 0)
            self.assertIsNone(registry["active_workspace_id"])

    def test_migrate_from_legacy_toml_skips_when_toml_missing_token_fields(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / ".modal_workspaces.json"
            toml_path = Path(tmp) / ".modal.toml"
            toml_path.write_text('[default]\nother_key = "value"\n', encoding="utf-8")
            registry = module.migrate_from_legacy_toml(registry_path, toml_path)
            self.assertEqual(len(registry["workspaces"]), 0)

    def test_migrate_from_legacy_toml_skips_invalid_token_prefixes(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / ".modal_workspaces.json"
            toml_path = Path(tmp) / ".modal.toml"
            toml_path.write_text(
                '[default]\ntoken_id = "bad-token"\ntoken_secret = "bad-secret"\n',
                encoding="utf-8",
            )
            registry = module.migrate_from_legacy_toml(registry_path, toml_path)
            self.assertEqual(len(registry["workspaces"]), 0)
            self.assertIsNone(registry["active_workspace_id"])

    # ── Sole workspace is active even without active_workspace_id ─────

    def test_get_active_workspace_returns_sole_workspace_when_no_active_id(self):
        module = load_module()
        # Build a registry directly with a single workspace and no active_workspace_id
        registry = {
            "version": 1,
            "active_workspace_id": None,
            "workspaces": [
                {"id": "ws_solo", "label": "Solo", "token_id": "ak-solo", "token_secret": "as-solo",
                 "last_used_at": None, "last_deploy_status": "idle", "notes": ""},
            ],
            "deploy_state_by_workspace": {},
        }
        active = module.get_active_workspace(registry)
        self.assertIsNotNone(active)
        self.assertEqual(active["label"], "Solo")

    def test_get_active_workspace_returns_none_when_multiple_no_active_id(self):
        module = load_module()
        # Build a registry directly with two workspaces and no active_workspace_id
        registry = {
            "version": 1,
            "active_workspace_id": None,
            "workspaces": [
                {"id": "ws_a", "label": "A", "token_id": "ak-a", "token_secret": "as-a",
                 "last_used_at": None, "last_deploy_status": "idle", "notes": ""},
                {"id": "ws_b", "label": "B", "token_id": "ak-b", "token_secret": "as-b",
                 "last_used_at": None, "last_deploy_status": "idle", "notes": ""},
            ],
            "deploy_state_by_workspace": {},
        }
        active = module.get_active_workspace(registry)
        self.assertIsNone(active)


if __name__ == "__main__":
    unittest.main()
