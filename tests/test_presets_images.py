import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "presets.py"


def load_module():
    spec = importlib.util.spec_from_file_location("presets", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _callable(module, name):
    fn = getattr(module, name, None)
    if fn is None:
        raise AssertionError(f"presets.py missing public function: {name}")
    return fn


def _png_bytes() -> bytes:
    # 1x1 transparent PNG (smallest valid PNG)
    return (b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\rIDATx\x9cc\xfc\xff\xff?\x03\x00\x05\xfe\x02\xfe\xa3z\xea\xc8"
            b"\x00\x00\x00\x00IEND\xaeB`\x82")


class ImagePresetCRUDTests(unittest.TestCase):
    def test_create_image_preset(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            preset = m.create_image_preset(root=tmp, name="Pack A")
            self.assertEqual(preset["name"], "Pack A")
            self.assertEqual(preset["items"], [])

    def test_add_image_creates_blob(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            preset = m.create_image_preset(root=tmp, name="Pack")
            data = _png_bytes()
            h = m.hash_image_bytes(data)
            m.add_image_to_preset(
                root=tmp, preset_id=preset["id"],
                label="A", original_filename="a.png",
                mime_type="image/png", width=1, height=1,
                content_hash=h, file_ext=".png", data=data,
            )
            blob = m.blob_path_for(root=tmp, content_hash=h, file_ext=".png")
            self.assertTrue(blob.exists())
            self.assertEqual(blob.read_bytes(), data)

    def test_add_image_reuses_blob_with_same_hash(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            preset = m.create_image_preset(root=tmp, name="Pack")
            data = _png_bytes()
            h = m.hash_image_bytes(data)
            m.add_image_to_preset(
                root=tmp, preset_id=preset["id"],
                label="A", original_filename="a.png",
                mime_type="image/png", width=1, height=1,
                content_hash=h, file_ext=".png", data=data,
            )
            mtime_before = m.blob_path_for(root=tmp, content_hash=h, file_ext=".png").stat().st_mtime_ns
            m.add_image_to_preset(
                root=tmp, preset_id=preset["id"],
                label="A-dup", original_filename="a.png",
                mime_type="image/png", width=1, height=1,
                content_hash=h, file_ext=".png", data=data,
            )
            mtime_after = m.blob_path_for(root=tmp, content_hash=h, file_ext=".png").stat().st_mtime_ns
            self.assertEqual(mtime_before, mtime_after)
            # preset now has 2 items with the same hash
            refreshed = m.get_image_preset(root=tmp, preset_id=preset["id"])
            self.assertEqual(len(refreshed["items"]), 2)

    def test_detect_duplicates_within_preset(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            preset = m.create_image_preset(root=tmp, name="Pack")
            data = _png_bytes()
            h = m.hash_image_bytes(data)
            for label in ("a", "b", "c"):
                m.add_image_to_preset(
                    root=tmp, preset_id=preset["id"],
                    label=label, original_filename="a.png",
                    mime_type="image/png", width=1, height=1,
                    content_hash=h, file_ext=".png", data=data,
                )
            groups = m.detect_image_duplicates_in_preset(root=tmp, preset_id=preset["id"])
            self.assertEqual(len(groups), 1)
            self.assertEqual(len(groups[0]), 3)


class ReferenceSafeDeleteTests(unittest.TestCase):
    def test_delete_preset_keeps_blob(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            p1 = m.create_image_preset(root=tmp, name="A")
            data = _png_bytes()
            h = m.hash_image_bytes(data)
            m.add_image_to_preset(root=tmp, preset_id=p1["id"],
                                  label="A", original_filename="a.png",
                                  mime_type="image/png", width=1, height=1,
                                  content_hash=h, file_ext=".png", data=data)
            blob = m.blob_path_for(root=tmp, content_hash=h, file_ext=".png")
            self.assertTrue(blob.exists())
            m.delete_image_preset(root=tmp, preset_id=p1["id"])
            # blob survives
            self.assertTrue(blob.exists())

    def test_remove_item_keeps_blob(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            p1 = m.create_image_preset(root=tmp, name="A")
            data = _png_bytes()
            h = m.hash_image_bytes(data)
            m.add_image_to_preset(root=tmp, preset_id=p1["id"],
                                  label="A", original_filename="a.png",
                                  mime_type="image/png", width=1, height=1,
                                  content_hash=h, file_ext=".png", data=data)
            refreshed = m.get_image_preset(root=tmp, preset_id=p1["id"])
            item_id = refreshed["items"][0]["id"]
            m.remove_image_item(root=tmp, preset_id=p1["id"], item_id=item_id)
            blob = m.blob_path_for(root=tmp, content_hash=h, file_ext=".png")
            self.assertTrue(blob.exists())

    def test_cleanup_orphan_blobs_removes_unreferenced(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            # no presets, just an orphan blob
            orphan = m.blob_path_for(root=tmp, content_hash="a" * 64, file_ext=".png")
            orphan.write_bytes(_png_bytes())
            deleted = m.cleanup_orphan_blobs(root=tmp)
            self.assertEqual(deleted, 1)
            self.assertFalse(orphan.exists())

    def test_cleanup_orphan_blobs_keeps_referenced(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            preset = m.create_image_preset(root=tmp, name="Pack")
            data = _png_bytes()
            h = m.hash_image_bytes(data)
            m.add_image_to_preset(root=tmp, preset_id=preset["id"],
                                  label="A", original_filename="a.png",
                                  mime_type="image/png", width=1, height=1,
                                  content_hash=h, file_ext=".png", data=data)
            # also drop an unrelated orphan
            orphan = m.blob_path_for(root=tmp, content_hash="b" * 64, file_ext=".png")
            orphan.write_bytes(_png_bytes())
            deleted = m.cleanup_orphan_blobs(root=tmp)
            self.assertEqual(deleted, 1)
            self.assertTrue(m.blob_path_for(root=tmp, content_hash=h, file_ext=".png").exists())
            self.assertFalse(orphan.exists())


class ReorderTests(unittest.TestCase):
    def test_reorder_image_items(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            preset = m.create_image_preset(root=tmp, name="Pack")
            data = _png_bytes()
            hashes = []
            for i in range(3):
                d = data + bytes([i])  # unique bytes
                h = m.hash_image_bytes(d)
                hashes.append((h, d))
                m.add_image_to_preset(root=tmp, preset_id=preset["id"],
                                      label=f"img{i}", original_filename=f"a{i}.png",
                                      mime_type="image/png", width=1, height=1,
                                      content_hash=h, file_ext=".png", data=d)
            refreshed = m.get_image_preset(root=tmp, preset_id=preset["id"])
            ids = [it["id"] for it in refreshed["items"]]
            new_order = list(reversed(ids))
            m.reorder_image_items(root=tmp, preset_id=preset["id"], new_order=new_order)
            refreshed = m.get_image_preset(root=tmp, preset_id=preset["id"])
            self.assertEqual([it["id"] for it in refreshed["items"]], new_order)


if __name__ == "__main__":
    unittest.main()
