import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "model_manifest.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("model_manifest.py missing")
    spec = importlib.util.spec_from_file_location("model_manifest", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ModelManifestTests(unittest.TestCase):
    def test_upsert_manifest_entry_persists_folder_filename_and_url(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".model_manifest.json"
            saved = module.upsert_manifest_entry(path, {
                "folder": "vae",
                "filename": "flux2-vae.safetensors",
                "url": "https://huggingface.co/acme/flux2-vae/resolve/main/flux2-vae.safetensors",
                "source_kind": "huggingface",
                "requires_hf_token": False,
                "requires_civitai_token": False,
            })

        self.assertEqual(saved["entries"][0]["folder"], "vae")
        self.assertEqual(saved["entries"][0]["filename"], "flux2-vae.safetensors")
        self.assertEqual(saved["entries"][0]["url"], "https://huggingface.co/acme/flux2-vae/resolve/main/flux2-vae.safetensors")

    def test_scan_manifest_issues_flags_missing_url_duplicate_and_invalid_folder(self):
        module = load_module()
        payload = {
            "manifest_version": 1,
            "entries": [
                {"folder": "vae", "filename": "a.safetensors", "url": "", "source_kind": "huggingface"},
                {"folder": "vae", "filename": "b.safetensors", "url": "https://x", "source_kind": ""},
                {"folder": "bad-folder", "filename": "c.safetensors", "url": "https://x", "source_kind": "direct"},
                {"folder": "vae", "filename": "dup.safetensors", "url": "https://one", "source_kind": "direct"},
                {"folder": "vae", "filename": "dup.safetensors", "url": "https://two", "source_kind": "direct"},
            ],
        }
        issues = module.scan_manifest_issues(payload)
        issue_kinds = {item["kind"] for item in issues}

        self.assertEqual(issue_kinds, {"missing_url", "missing_source_kind", "invalid_folder", "duplicate_key"})

    def test_build_swap_plan_separates_present_missing_and_unresolved(self):
        module = load_module()
        manifest = {
            "manifest_version": 1,
            "entries": [
                {"folder": "vae", "filename": "flux2-vae.safetensors", "url": "https://example/vae", "source_kind": "direct"},
                {"folder": "loras", "filename": "detail.safetensors", "url": "", "source_kind": "direct"},
            ],
        }
        remote_models = [{"folder": "vae", "name": "flux2-vae.safetensors"}]
        plan = module.build_workspace_swap_plan(manifest, remote_models)

        self.assertEqual(plan["already_present"], [{"folder": "vae", "filename": "flux2-vae.safetensors"}])
        self.assertEqual(plan["to_install"], [])
        self.assertEqual(plan["unresolved"][0]["filename"], "detail.safetensors")

    def test_merge_workflow_manifest_returns_conflicts_instead_of_overwriting(self):
        module = load_module()
        local_payload = {
            "manifest_version": 1,
            "entries": [
                {"folder": "vae", "filename": "flux2-vae.safetensors", "url": "https://local", "source_kind": "direct"},
            ],
        }
        imported_payload = {
            "manifest_version": 1,
            "models": [
                {"folder": "vae", "filename": "flux2-vae.safetensors", "url": "https://remote", "source_kind": "direct"},
            ],
        }
        result = module.merge_workflow_manifest(local_payload, imported_payload)

        self.assertEqual(result["added"], [])
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(result["conflicts"][0]["filename"], "flux2-vae.safetensors")

    def test_apply_manifest_repairs_updates_missing_url(self):
        module = load_module()
        payload = {
            "manifest_version": 1,
            "entries": [
                {"folder": "vae", "filename": "flux2-vae.safetensors", "url": "", "source_kind": ""},
            ],
        }
        repaired = module.apply_manifest_repairs(payload, [{
            "folder": "vae",
            "filename": "flux2-vae.safetensors",
            "url": "https://example/flux2-vae.safetensors",
            "source_kind": "direct",
        }])

        self.assertEqual(repaired["entries"][0]["url"], "https://example/flux2-vae.safetensors")
        self.assertEqual(repaired["entries"][0]["source_kind"], "direct")

    def test_merge_workflow_manifest_applies_explicit_resolution(self):
        module = load_module()
        local_payload = {
            "manifest_version": 1,
            "entries": [
                {"folder": "vae", "filename": "flux2-vae.safetensors", "url": "https://local", "source_kind": "direct"},
            ],
        }
        imported_payload = {
            "manifest_version": 1,
            "models": [
                {"folder": "vae", "filename": "flux2-vae.safetensors", "url": "https://remote", "source_kind": "direct"},
            ],
        }
        result = module.merge_workflow_manifest(
            local_payload,
            imported_payload,
            resolutions={"vae/flux2-vae.safetensors": "use_imported"},
        )

        self.assertEqual(result["conflicts"], [])
        self.assertEqual(result["entries"][0]["url"], "https://remote")

    def test_scan_local_models_issues_finds_placeholders_missing_from_manifest(self):
        module = load_module()
        manifest = {"manifest_version": 1, "entries": []}
        with tempfile.TemporaryDirectory() as tmp:
            placeholder_dir = Path(tmp) / "models" / "vae"
            placeholder_dir.mkdir(parents=True)
            (placeholder_dir / "flux2-vae.safetensors").write_bytes(b"")
            issues = module.scan_local_models_issues(tmp, manifest)

        self.assertIn("missing_from_manifest", {i["kind"] for i in issues})
        missing = [i for i in issues if i["kind"] == "missing_from_manifest"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["filename"], "flux2-vae.safetensors")

    def test_scan_local_models_issues_skips_non_zero_byte_files(self):
        module = load_module()
        manifest = {"manifest_version": 1, "entries": []}
        with tempfile.TemporaryDirectory() as tmp:
            placeholder_dir = Path(tmp) / "models" / "vae"
            placeholder_dir.mkdir(parents=True)
            (placeholder_dir / "real-model.safetensors").write_bytes(b"real-data")
            issues = module.scan_local_models_issues(tmp, manifest)

        missing = [i for i in issues if i["kind"] == "missing_from_manifest"]
        self.assertEqual(len(missing), 0)

    def test_scan_local_models_issues_skips_put_xxx_here_hint_files(self):
        module = load_module()
        manifest = {"manifest_version": 1, "entries": []}
        with tempfile.TemporaryDirectory() as tmp:
            models_dir = Path(tmp) / "models" / "checkpoints"
            models_dir.mkdir(parents=True)
            (models_dir / "put_checkpoints_here.txt").write_bytes(b"")
            (models_dir / "put_audio_encoder_models_here.txt").write_bytes(b"")
            (models_dir / "real_ckpt.safetensors").write_bytes(b"")
            issues = module.scan_local_models_issues(tmp, manifest)

        missing = [i for i in issues if i["kind"] == "missing_from_manifest"]
        missing_names = [i["filename"] for i in missing]
        self.assertEqual(missing_names, ["real_ckpt.safetensors"])

    def test_scan_local_models_issues_ignores_tracked_placeholders(self):
        module = load_module()
        manifest = {"manifest_version": 1, "entries": [
            {"folder": "vae", "filename": "flux2-vae.safetensors", "url": "https://example", "source_kind": "direct"},
        ]}
        with tempfile.TemporaryDirectory() as tmp:
            placeholder_dir = Path(tmp) / "models" / "vae"
            placeholder_dir.mkdir(parents=True)
            (placeholder_dir / "flux2-vae.safetensors").write_bytes(b"")
            issues = module.scan_local_models_issues(tmp, manifest)

        missing = [i for i in issues if i["kind"] == "missing_from_manifest"]
        self.assertEqual(len(missing), 0)

    def test_apply_manifest_repairs_creates_new_entry_for_missing_model(self):
        module = load_module()
        payload = {"manifest_version": 1, "entries": []}
        updates = [{"folder": "vae", "filename": "flux2-vae.safetensors", "url": "https://example", "source_kind": "direct"}]
        repaired = module.apply_manifest_repairs(payload, updates)

        self.assertEqual(len(repaired["entries"]), 1)
        self.assertEqual(repaired["entries"][0]["url"], "https://example")

    def test_apply_manifest_repairs_can_mark_existing_entry_for_remove_and_update_fields(self):
        module = load_module()
        payload = {
            "manifest_version": 1,
            "entries": [
                {"folder": "vae", "filename": "flux2-vae.safetensors", "url": "https://old", "source_kind": "direct"},
            ],
        }
        repaired = module.apply_manifest_repairs(payload, [{
            "folder": "vae",
            "filename": "flux2-vae.safetensors",
            "url": "https://new",
            "source_kind": "huggingface",
            "remove": True,
        }])

        self.assertEqual(repaired["entries"][0]["url"], "https://new")
        self.assertEqual(repaired["entries"][0]["source_kind"], "huggingface")
        self.assertTrue(repaired["entries"][0]["remove_on_swap"])

    def test_remove_only_entries_do_not_require_url_and_only_populate_to_remove(self):
        module = load_module()
        repaired = module.apply_manifest_repairs({"manifest_version": 1, "entries": []}, [{
            "folder": "loras",
            "filename": "old.safetensors",
            "source_kind": "unknown",
            "remove": True,
        }])

        self.assertEqual(module.scan_manifest_issues(repaired), [])
        plan = module.build_workspace_swap_plan(repaired, [{"folder": "loras", "name": "old.safetensors"}])
        self.assertEqual(plan["to_remove"], [{"folder": "loras", "filename": "old.safetensors"}])
        self.assertEqual(plan["already_present"], [])
        self.assertEqual(plan["to_install"], [])
        self.assertEqual(plan["unresolved"], [])


if __name__ == "__main__":
    unittest.main()
