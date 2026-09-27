"""Behavior tests for the Studio Model Library (model_library.py)."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tests import _test_env  # noqa: F401  (hide real ComfyUI from sys.path)

from model_library import (
    MODEL_TYPES,
    ModelLibraryError,
    ModelLibraryService,
)

CONTENT_A = b"contentA"
CONTENT_B = b"contentB-much-longer"


class ModelLibraryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.comfyui_root = self.base / "comfyui"
        self.node_dir = self.base / "node"
        self.service = ModelLibraryService(str(self.node_dir), str(self.comfyui_root))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ── helpers ──────────────────────────────────────────────────────────

    def _models_dir(self) -> Path:
        return self.comfyui_root / "models"

    def _write(self, folder: str, filename: str, content: bytes) -> Path:
        path = self._models_dir() / folder / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _first_record(self) -> dict:
        return self.service.store.list_records()[0]

    def _by_hash(self) -> dict:
        return {m["hash"]: m for m in self.service.list_models()}

    # ── 1. detect an installed model ─────────────────────────────────────

    def test_detect_installed_model(self):
        path = self._write("checkpoints", "krea_model.safetensors", CONTENT_A)
        summary = self.service.rescan()
        self.assertEqual(summary["added"], 1)
        models = self.service.list_models()
        self.assertEqual(len(models), 1)
        record = models[0]
        self.assertTrue(record["installed"])
        self.assertEqual(record["hash"], hashlib.sha256(CONTENT_A).hexdigest())
        self.assertEqual(record["size"], len(CONTENT_A))
        self.assertEqual(record["local_path"], str(path))
        self.assertEqual(record["model_type"], "checkpoint")
        self.assertEqual(record["display_name"], "krea_model")

    # ── 2. same filename + different hash → distinct records ─────────────

    def test_same_filename_different_hash_distinct_identity(self):
        self._write("checkpoints", "krea_model.safetensors", CONTENT_A)
        self.service.rescan()
        records = self.service.store.list_records()
        self.assertEqual(len(records), 1)
        first_id = records[0]["model_id"]

        self._write("checkpoints", "krea_model.safetensors", CONTENT_B)
        self.service.rescan()
        records = self.service.store.list_records()
        self.assertEqual(len(records), 2)
        self.assertEqual({r["folder"] for r in records}, {"checkpoints"})
        self.assertEqual({r["filename"] for r in records}, {"krea_model.safetensors"})
        self.assertNotEqual(records[0]["model_id"], records[1]["model_id"])

        by_hash = self._by_hash()
        old = by_hash[hashlib.sha256(CONTENT_A).hexdigest()]
        new = by_hash[hashlib.sha256(CONTENT_B).hexdigest()]
        self.assertEqual(old["model_id"], first_id)
        self.assertFalse(old["installed"])
        self.assertTrue(new["installed"])

    # ── 3. model_type classification across folders ──────────────────────

    def test_model_types(self):
        folders = [
            "unet", "diffusion_models", "clip", "text_encoders",
            "vae", "loras", "controlnet", "upscale_models", "embeddings",
        ]
        expected = [
            "unet", "unet", "clip", "clip",
            "vae", "lora", "controlnet", "upscaler", "other",
        ]
        for i, folder in enumerate(folders):
            self._write(folder, f"m{i}.safetensors", f"content-{i}".encode())
        self.service.rescan()
        models = self.service.list_models()
        self.assertEqual(len(models), 9)
        by_file = {m["filename"]: m["model_type"] for m in models}
        for i, folder in enumerate(folders):
            self.assertEqual(by_file[f"m{i}.safetensors"], expected[i], msg=folder)

    # ── 4. search / type / state filtering ───────────────────────────────

    def test_search_and_type_filtering(self):
        self._write("loras", "style_lora.safetensors", b"lora-a")
        self._write("checkpoints", "photoreal.safetensors", b"ckpt-a")
        self._write("controlnet", "depth_cn.safetensors", b"cn-a")
        self.service.rescan()

        # search matches display_name / filename / folder / tags.
        self.assertEqual(len(self.service.list_models(search="lora")), 1)
        self.assertEqual(len(self.service.list_models(search="Lora")), 1)
        self.assertEqual(len(self.service.list_models(search="depth")), 1)
        self.assertEqual(len(self.service.list_models(search="controlnet")), 1)
        self.assertEqual(len(self.service.list_models(search="zzz-nowhere")), 0)

        # model_type filter.
        self.assertEqual(len(self.service.list_models(model_type="lora")), 1)
        self.assertEqual(len(self.service.list_models(model_type="checkpoint")), 1)
        self.assertEqual(len(self.service.list_models(model_type="controlnet")), 1)

        # state filter: all installed.
        self.assertEqual(len(self.service.list_models(state="installed")), 3)
        self.assertEqual(len(self.service.list_models(state="missing")), 0)

        # tags participate in search.
        target = self.service.list_models(search="lora")[0]
        self.service.update_metadata(target["model_id"], {"tags": ["portrait"]})
        self.assertEqual(len(self.service.list_models(search="portrait")), 1)

        # Deleting the file flips the DERIVED installed flag (no rescan).
        (self._models_dir() / "loras" / "style_lora.safetensors").unlink()
        missing = self.service.list_models(state="missing")
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["filename"], "style_lora.safetensors")
        self.assertFalse(missing[0]["installed"])

    # ── 5. no rehash for unchanged files ─────────────────────────────────

    def test_no_rehash_unchanged(self):
        for i in range(3):
            self._write("checkpoints", f"m{i}.safetensors", f"content-{i}".encode())
        first = self.service.rescan()
        self.assertEqual(first["added"], 3)
        self.assertEqual(first["hashed"], 3)
        second = self.service.rescan()
        self.assertEqual(second["hashed"], 0)
        self.assertEqual(second["unchanged"], 3)
        self.assertEqual(second["total"], 3)

    # ── 6. zero-byte files are placeholders ──────────────────────────────

    def test_zero_byte_placeholder(self):
        self._write("checkpoints", "empty.safetensors", b"")
        summary = self.service.rescan()
        self.assertEqual(summary["placeholders"], 1)
        record = self._first_record()
        self.assertTrue(record["is_placeholder"])
        self.assertEqual(record["hash"], "")
        models = self.service.list_models()
        self.assertEqual(len(models), 1)
        self.assertFalse(models[0]["installed"])

    # ── 7. update_metadata: allowed keys persist, others rejected ────────

    def test_update_metadata_allowed_and_rejects_others(self):
        self._write("checkpoints", "krea_model.safetensors", CONTENT_A)
        self.service.rescan()
        model_id = self._first_record()["model_id"]
        updated = self.service.update_metadata(
            model_id,
            {
                "display_name": "Krea Model",
                "notes": "a note",
                "tags": ["krea", "portrait"],
                "source_urls": ["https://huggingface.co/org/repo"],
                "provider": "huggingface",
                "revision": "abc123",
            },
        )
        self.assertEqual(updated["display_name"], "Krea Model")
        self.assertEqual(updated["notes"], "a note")
        self.assertEqual(updated["tags"], ["krea", "portrait"])
        self.assertEqual(updated["source_urls"], ["https://huggingface.co/org/repo"])
        self.assertEqual(updated["provider"], "huggingface")
        self.assertEqual(updated["revision"], "abc123")
        self.assertTrue(updated["installed"])

        stored = self.service.store.get_record(model_id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored["notes"], "a note")
        self.assertEqual(stored["tags"], ["krea", "portrait"])

        with self.assertRaises(ModelLibraryError):
            self.service.update_metadata(model_id, {"hash": "tampered"})
        with self.assertRaises(ModelLibraryError):
            self.service.update_metadata(model_id, {"tags": "not-a-list"})
        with self.assertRaises(ModelLibraryError):
            self.service.update_metadata(model_id, {"source_urls": ["ok", 5]})
        with self.assertRaises(ModelLibraryError):
            self.service.update_metadata("ml_ghost", {"notes": "x"})

    # ── 8. install_request validation ────────────────────────────────────

    def test_install_request_validation(self):
        req = self.service.install_request(
            "checkpoints",
            "krea_model.safetensors",
            "https://huggingface.co/org/repo/resolve/main/model.safetensors",
        )
        self.assertTrue(req["approved"])
        self.assertEqual(req["source_kind"], "huggingface")
        self.assertTrue(req["requires_hf_token"])
        self.assertFalse(req["requires_civitai_token"])

        with self.assertRaises(ModelLibraryError):
            self.service.install_request("bogus_folder", "a.safetensors", "https://x.com/a")
        with self.assertRaises(ModelLibraryError):
            self.service.install_request("checkpoints", "../evil.safetensors", "https://x.com/a")
        with self.assertRaises(ModelLibraryError):
            self.service.install_request("checkpoints", "sub/a.safetensors", "https://x.com/a")
        with self.assertRaises(ModelLibraryError):
            self.service.install_request("checkpoints", "a.safetensors", "ftp://x.com/a")
        with self.assertRaises(ModelLibraryError):
            self.service.install_request("checkpoints", "C:/evil.safetensors", "https://x.com/a")

    # ── 9. no implicit scan on the generation path ───────────────────────

    def test_scan_never_runs_implicitly(self):
        self._write("checkpoints", "a.safetensors", CONTENT_A)
        models = self.service.list_models()
        self.assertEqual(models, [])
        store_path = self.node_dir / ".studio_model_library.json"
        self.assertFalse(store_path.exists())
        self.assertEqual(self.service.store.list_records(), [])
        self.assertEqual(MODEL_TYPES[0], "checkpoint")

    # ── 10. UTF-8 BOM stores are tolerated on read ───────────────────────

    def test_store_read_tolerates_utf8_bom(self):
        self._write("checkpoints", "krea_model.safetensors", CONTENT_A)
        self.service.rescan()
        records = self.service.store.list_records()
        self.assertEqual(len(records), 1)

        # Rewrite the store with a UTF-8 BOM prefix (some editors write one).
        store_path = self.node_dir / ".studio_model_library.json"
        bom_payload = b"\xef\xbb\xbf" + json.dumps(records).encode("utf-8")
        store_path.write_bytes(bom_payload)
        mtime_before = store_path.stat().st_mtime_ns

        models = self.service.list_models()
        self.assertEqual(
            [m["model_id"] for m in models],
            [r["model_id"] for r in records],
        )
        self.assertEqual(models[0]["filename"], "krea_model.safetensors")

        # The read must not rewrite the file: content and mtime are unchanged.
        self.assertEqual(store_path.read_bytes(), bom_payload)
        self.assertEqual(store_path.stat().st_mtime_ns, mtime_before)

    # ── 11. list_models is a pure read: never scans, never rewrites ──────

    def test_list_never_rewrites_or_scans(self):
        store_path = self.node_dir / ".studio_model_library.json"

        # No store and nothing on disk: list is a read, never a scan.
        self.assertEqual(self.service.list_models(), [])
        self.assertFalse(store_path.exists())
        self.assertEqual(self.service.list_models(), [])
        self.assertFalse(store_path.exists())

        # With a store present, list never rewrites the file bytes.
        self._write("checkpoints", "krea_model.safetensors", CONTENT_A)
        self.service.rescan()
        before = store_path.read_bytes()
        self.assertEqual(len(self.service.list_models()), 1)
        self.assertEqual(store_path.read_bytes(), before)
        self.assertEqual(len(self.service.list_models()), 1)
        self.assertEqual(store_path.read_bytes(), before)

    # ── 12. installed derives from the real nonzero file on disk ─────────

    def test_record_is_installed_requires_nonzero_disk_file(self):
        from model_library import record_is_installed

        real = self._write("checkpoints", "real.safetensors", CONTENT_A)
        self.assertTrue(
            record_is_installed(
                {"local_path": str(real), "size": len(CONTENT_A), "fingerprint": None}
            )
        )

        empty = self._write("checkpoints", "empty.safetensors", b"")
        # Zero-byte file is a placeholder: never installed, even when a stale
        # record claimed a positive size.
        self.assertFalse(
            record_is_installed(
                {"local_path": str(empty), "size": 0, "fingerprint": None}
            )
        )
        self.assertFalse(
            record_is_installed(
                {"local_path": str(empty), "size": 12345, "fingerprint": None}
            )
        )
        # Stored size disagrees with the real file: content was replaced.
        self.assertFalse(
            record_is_installed(
                {
                    "local_path": str(real),
                    "size": len(CONTENT_A) + 1,
                    "fingerprint": None,
                }
            )
        )

    # ── 13. models/unet legacy folder is reconciled ──────────────────────

    def test_scan_represents_unet_folder(self):
        self._write("unet", "krea2_turbo_bf16.safetensors", CONTENT_A)
        summary = self.service.rescan()
        self.assertEqual(summary["added"], 1)
        records = [
            r
            for r in self.service.list_models()
            if r["filename"] == "krea2_turbo_bf16.safetensors"
        ]
        self.assertEqual(len(records), 1, "one physical file must yield one record")
        self.assertEqual(records[0]["model_type"], "unet")
        self.assertTrue(records[0]["installed"])

    # ── 14. registry-driven coverage + alias dedup ───────────────────────

    def test_folder_paths_map_covers_registry_and_dedups_alias_dirs(self):
        import sys
        import types
        from unittest import mock

        unet_dir = self._models_dir() / "unet"
        unet_dir.mkdir(parents=True, exist_ok=True)
        diff_dir = self._models_dir() / "diffusion_models"
        diff_dir.mkdir(parents=True, exist_ok=True)
        patches_dir = self._models_dir() / "model_patches"
        patches_dir.mkdir(parents=True, exist_ok=True)

        fake = types.ModuleType("folder_paths")
        setattr(
            fake,
            "folder_names_and_paths",
            {
                # ``unet`` is an alias directory inside diffusion_models; a
                # registry-only bucket (model_patches) must also be picked up.
                "diffusion_models": ([str(unet_dir), str(diff_dir)], set()),
                "model_patches": ([str(patches_dir)], set()),
                "custom_nodes": ([str(self.comfyui_root / "custom_nodes")], set()),
            },
        )
        with mock.patch.dict(sys.modules, {"folder_paths": fake}):
            mapping = self.service.discovery.folder_paths_map(str(self.comfyui_root))

        self.assertEqual(
            mapping.get("diffusion_models"), [str(unet_dir), str(diff_dir)]
        )
        # The same tree merged from the on-disk unet bucket must not create a
        # second bucket (that would duplicate every record).
        self.assertNotIn("unet", mapping)
        self.assertEqual(mapping.get("model_patches"), [str(patches_dir)])
        self.assertNotIn("custom_nodes", mapping)


if __name__ == "__main__":
    unittest.main()
