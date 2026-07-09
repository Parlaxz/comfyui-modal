import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_input_image_paths import _load_init_module


def _entry(filename: str, payload: bytes, *, node_id: str = "107", output_key: str, comparison_side: str, output_index: int, mime_type: str = "image/png"):
    return {
        "filename": filename,
        "data": base64.b64encode(payload).decode("ascii"),
        "node_id": node_id,
        "output_key": output_key,
        "comparison_side": comparison_side,
        "mime_type": mime_type,
        "file_ext": ".png",
        "output_index": output_index,
        "format": "png",
        "width": 64,
        "height": 64,
    }


def _exp_result_entry(filename: str, payload: bytes, *, node_id: str = "7", output_key: str = "images", comparison_side: str = "", mime_type: str = "image/png"):
    return {
        "filename": filename,
        "data": base64.b64encode(payload).decode("ascii"),
        "node_id": node_id,
        "output_key": output_key,
        "comparison_side": comparison_side,
        "mime_type": mime_type,
        "file_ext": ".png",
        "output_index": 0,
        "format": "png",
        "width": 64,
        "height": 64,
    }


def _make_png_bytes(r: int = 128, g: int = 128, b: int = 128) -> bytes:
    """Build a minimal valid PNG with a single pixel at the given colour."""
    import struct
    import zlib
    def _chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = zlib.compress(struct.pack(">B", 0) + bytes([r, g, b]))
    idat = _chunk(b"IDAT", raw)
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _make_jpeg_bytes() -> bytes:
    """Build a minimal valid JPEG."""
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00\x43\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f"
        b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
        b"\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x11\x04\x12!1\x06\x13Qa\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz"
        b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xd5\xcf\x00\xff\xd9"
    )


class ModalOutputMaterializationTests(unittest.TestCase):
    def test_materialize_modal_outputs_preserves_a_b_and_emits_single_event(self):
        module = _load_init_module()
        a_bytes = b"image-a"
        b_bytes = b"image-b"
        a_entry = _entry("compare_a.png", a_bytes, output_key="a_images", comparison_side="a", output_index=0)
        b_entry = _entry("compare_b.png", b_bytes, output_key="b_images", comparison_side="b", output_index=1)
        result = {
            "images": [a_entry, b_entry],
            "outputs": {"107": {"a_images": [a_entry], "b_images": [b_entry]}},
        }
        events = []
        with tempfile.TemporaryDirectory() as tmp:
            summary = module._materialize_modal_outputs(
                result,
                output_dir=tmp,
                prompt_id="prompt-123",
                client_id="client-abc",
                send_event=lambda event, payload: events.append((event, payload)),
            )

            self.assertEqual(summary["image_count"], 2)
            self.assertEqual(len(summary["written_files"]), 2)
            self.assertEqual((Path(tmp) / "compare_a.png").read_bytes(), a_bytes)
            self.assertEqual((Path(tmp) / "compare_b.png").read_bytes(), b_bytes)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0][0], "executed")
            self.assertEqual(sorted(events[0][1]["output"].keys()), ["a_images", "b_images"])
            self.assertEqual(len(events[0][1]["output"]["a_images"]), 1)
            self.assertEqual(len(events[0][1]["output"]["b_images"]), 1)
            self.assertEqual(summary["primary_output"]["output_key"], "b_images")
            self.assertEqual(summary["primary_output"]["comparison_side"], "b")
            self.assertEqual(summary["primary_output"]["path"], str(Path(tmp) / "compare_b.png"))

    def test_materialize_modal_outputs_autosaves_primary_only(self):
        module = _load_init_module()
        a_entry = _entry("compare_a.png", b"image-a", output_key="a_images", comparison_side="a", output_index=0)
        b_entry = _entry("compare_b.png", b"image-b", output_key="b_images", comparison_side="b", output_index=1)
        result = {
            "images": [a_entry, b_entry],
            "outputs": {"107": {"a_images": [a_entry], "b_images": [b_entry]}},
            "_conversion_meta": [],
        }
        save_calls = []

        def _fake_save_output_image(image_bytes, **kwargs):
            save_calls.append((image_bytes, kwargs))
            return {"saved": True, "path": kwargs["save_folder"], "metadata_path": "", "error": None}

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(module, "save_output_image", side_effect=_fake_save_output_image):
                summary = module._materialize_modal_outputs(
                    result,
                    output_dir=tmp,
                    prompt_id="prompt-123",
                    client_id="client-abc",
                    send_event=lambda *_: None,
                    auto_save_local=True,
                    save_folder="ComfyUI/output/modal/",
                    save_metadata_sidecar=True,
                    workflow_hash="hash123",
                    workflow_name="",
                    seed="7",
                    width=64,
                    height=64,
                    comfyui_root=tmp,
                )

            self.assertEqual(len(save_calls), 1)
            saved_bytes, saved_kwargs = save_calls[0]
            self.assertEqual(saved_bytes, b"image-b")
            self.assertEqual(saved_kwargs["extra_meta"]["output_key"], "b_images")
            self.assertEqual(saved_kwargs["extra_meta"]["comparison_side"], "b")
            self.assertEqual(saved_kwargs["extra_meta"]["node_id"], "107")
            self.assertEqual(summary["primary_output"]["output_key"], "b_images")

    def test_select_primary_result_entry_prefers_b_side(self):
        module = _load_init_module()
        a_entry = _entry("compare_a.png", b"image-a", output_key="a_images", comparison_side="a", output_index=0)
        b_entry = _entry("compare_b.png", b"image-b", output_key="b_images", comparison_side="b", output_index=1)
        selected = module._select_primary_result_entry({
            "images": [a_entry, b_entry],
            "outputs": {"107": {"a_images": [a_entry], "b_images": [b_entry]}},
        })
        self.assertIsNotNone(selected)
        self.assertEqual(selected["comparison_side"], "b")
        self.assertEqual(selected["output_key"], "b_images")


class ExperimentOutputMaterializationTests(unittest.TestCase):
    """Tests for _materialize_experiment_output correctness."""

    def setUp(self):
        self.module = _load_init_module()

    # ── Asset ID uniqueness ────────────────────────────────────────────

    def test_identical_bytes_produce_distinct_asset_ids(self):
        """Goal 1: identical image bytes → different, globally unique asset IDs."""
        same_bytes = b"exactly-the-same-bytes"
        result_data = {
            "outputs": {
                "7": {
                    "images": [
                        _exp_result_entry("img_a.png", same_bytes, node_id="7", output_key="images"),
                    ],
                },
                "8": {
                    "images": [
                        _exp_result_entry("img_b.png", same_bytes, node_id="8", output_key="images"),
                    ],
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            mat = self.module._materialize_experiment_output(
                result_data, str(Path(tmp) / "out"), cell_key="c1", attempt_id="a1",
            )
            self.assertGreaterEqual(len(mat["assets"]), 2)
            ids = list(mat["assets"].keys())
            self.assertEqual(len(set(ids)), len(ids), "asset IDs must be unique")
            self.assertNotEqual(ids[0], ids[1],
                                "identical content must NOT produce same asset ID")

    def test_asset_id_not_content_hash(self):
        """Goal 1: asset IDs must NOT be derived from content hash."""
        data = b"some-image-data"
        result_data = {
            "outputs": {"7": {"images": [_exp_result_entry("img.png", data, node_id="7")]}},
        }
        content_hash = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            mat = self.module._materialize_experiment_output(
                result_data, str(Path(tmp) / "out"), cell_key="c1", attempt_id="a1",
            )
            for aid, info in mat["assets"].items():
                self.assertNotEqual(aid, content_hash[:32],
                                    "asset ID must not be content-hash-prefix")
                self.assertIsNotNone(aid)
                self.assertGreater(len(aid), 8)

    def test_content_hash_present_as_metadata(self):
        """Goal 1: content_hash must be kept as metadata on the asset."""
        data = b"content-for-hash-check"
        result_data = {
            "outputs": {"7": {"images": [_exp_result_entry("img.png", data, node_id="7")]}},
        }
        expected_hash = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            mat = self.module._materialize_experiment_output(
                result_data, str(Path(tmp) / "out"), cell_key="c1", attempt_id="a1",
            )
            for info in mat["assets"].values():
                self.assertEqual(info.get("content_hash"), expected_hash)

    # ── Thumbnail first-class asset ────────────────────────────────────

    def test_thumbnail_is_first_class_asset(self):
        """Goal 2: thumbnail has its own unique ID and MIME image/webp."""
        png_bytes = _make_png_bytes(200, 100, 50)
        result_data = {
            "outputs": {"7": {"images": [_exp_result_entry("img.png", png_bytes, node_id="7")]}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            mat = self.module._materialize_experiment_output(
                result_data, str(Path(tmp) / "out"), cell_key="c1", attempt_id="a1",
            )
            assets = mat["assets"]
            self.assertGreaterEqual(len(assets), 2,
                                    "must have at least original + thumbnail")
            variants = {info["variant"] for info in assets.values()}
            self.assertIn("original", variants)
            self.assertIn("thumbnail", variants)
            thumb_ids = [aid for aid, info in assets.items() if info["variant"] == "thumbnail"]
            orig_ids = [aid for aid, info in assets.items() if info["variant"] == "original"]
            self.assertEqual(len(thumb_ids), 1, "exactly one thumbnail")
            self.assertEqual(len(orig_ids), 1, "exactly one original")
            self.assertNotEqual(thumb_ids[0], orig_ids[0],
                                "thumbnail and original must have distinct IDs")
            thumb_info = assets[thumb_ids[0]]
            self.assertEqual(thumb_info["mime_type"], "image/webp")
            orig_info = assets[orig_ids[0]]
            self.assertEqual(orig_info["mime_type"], "image/png")

    def test_thumbnail_from_png_is_valid_webp(self):
        """Goal 2: PNG original produces a valid (decodable) WebP thumbnail."""
        png_bytes = _make_png_bytes(100, 150, 200)
        result_data = {
            "outputs": {"7": {"images": [_exp_result_entry("img.png", png_bytes, node_id="7")]}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            mat = self.module._materialize_experiment_output(
                result_data, str(Path(tmp) / "out"), cell_key="c1", attempt_id="a1",
            )
            thumb_info = next(
                info for info in mat["assets"].values() if info["variant"] == "thumbnail"
            )
            thumb_path = thumb_info["path"]
            self.assertTrue(Path(thumb_path).exists())
            thumb_bytes = Path(thumb_path).read_bytes()
            self.assertTrue(thumb_bytes.startswith(b"RIFF"),
                            f"WebP should start with RIFF, got {thumb_bytes[:4]}")
            self.assertIn(b"WEBP", thumb_bytes[:12],
                          "WebP container should contain WEBP marker")
            self.assertEqual(thumb_info["mime_type"], "image/webp")
            self.assertGreater(thumb_info["byte_size"], 0)

    def test_thumbnail_from_jpeg_is_valid_webp(self):
        """Goal 2: JPEG original also produces a valid WebP thumbnail
        (or falls back gracefully when PIL unavailable)."""
        jpeg_bytes = _make_jpeg_bytes()
        result_data = {
            "outputs": {"7": {"images": [
                _exp_result_entry("img.jpg", jpeg_bytes, node_id="7", mime_type="image/jpeg"),
            ]}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            mat = self.module._materialize_experiment_output(
                result_data, str(Path(tmp) / "out"), cell_key="c1", attempt_id="a1",
            )
            thumb_info = next(
                info for info in mat["assets"].values() if info["variant"] == "thumbnail"
            )
            thumb_path = thumb_info["path"]
            self.assertTrue(Path(thumb_path).exists())
            # When PIL succeeds: mime_type should be image/webp and file starts with RIFF.
            # When PIL is unavailable: _make_thumbnail falls back to copying the original,
            # so the "thumbnail" will inherit the original's MIME.
            self.assertIn(thumb_info["mime_type"], ("image/webp", "image/jpeg"),
                          "thumbnail mime should be webp on success, or fallback to original")
            if thumb_info["mime_type"] == "image/webp":
                thumb_bytes = Path(thumb_path).read_bytes()
                self.assertTrue(thumb_bytes.startswith(b"RIFF"),
                                f"JPEG→WebP thumbnail should be RIFF, got {thumb_bytes[:4]}")

    # ── Primary selection ──────────────────────────────────────────────

    def test_primary_selection_prefers_b_side(self):
        """Goal 4: primary selection uses select_primary_output preferring B side."""
        data_a = b"image-a-data"
        data_b = b"image-b-data"
        result_data = {
            "outputs": {
                "107": {
                    "a_images": [
                        _exp_result_entry("a.png", data_a, node_id="107", output_key="a_images", comparison_side="a"),
                    ],
                    "b_images": [
                        _exp_result_entry("b.png", data_b, node_id="107", output_key="b_images", comparison_side="b"),
                    ],
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            mat = self.module._materialize_experiment_output(
                result_data, str(Path(tmp) / "out"), cell_key="c1", attempt_id="a1",
            )
            self.assertIsNotNone(mat["primary_output"])
            self.assertEqual(mat["primary_output"]["comparison_side"], "b")
            self.assertEqual(mat["primary_output"]["output_key"], "b_images")

    def test_primary_selection_falls_back_to_images_key(self):
        """Goal 4: when no b side, primary falls back to ordinary images key."""
        data = b"regular-image"
        result_data = {
            "outputs": {
                "3": {
                    "images": [
                        _exp_result_entry("out.png", data, node_id="3", output_key="images"),
                    ],
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            mat = self.module._materialize_experiment_output(
                result_data, str(Path(tmp) / "out"), cell_key="c1", attempt_id="a1",
            )
            self.assertIsNotNone(mat["primary_output"])
            self.assertEqual(mat["primary_output"]["output_key"], "images")

    def test_primary_selection_a_side_as_last_resort(self):
        """Goal 4: when only a side, primary still selects it."""
        data = b"a-image"
        result_data = {
            "outputs": {
                "5": {
                    "a_images": [
                        _exp_result_entry("a.png", data, node_id="5", output_key="a_images", comparison_side="a"),
                    ],
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            mat = self.module._materialize_experiment_output(
                result_data, str(Path(tmp) / "out"), cell_key="c1", attempt_id="a1",
            )
            self.assertIsNotNone(mat["primary_output"])
            self.assertEqual(mat["primary_output"]["comparison_side"], "a")

    # ── Multiple outputs ───────────────────────────────────────────────

    def test_multiple_outputs_all_registered(self):
        """All output images are registered as assets."""
        data1 = b"image-one"
        data2 = b"image-two"
        result_data = {
            "outputs": {
                "1": {
                    "images": [
                        _exp_result_entry("out1.png", data1, node_id="1"),
                        _exp_result_entry("out2.png", data2, node_id="1"),
                    ],
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            mat = self.module._materialize_experiment_output(
                result_data, str(Path(tmp) / "out"), cell_key="c1", attempt_id="a1",
            )
            self.assertEqual(mat["output_count"], 2)
            # 2 originals + 2 thumbnails = 4 total entries
            self.assertGreaterEqual(len(mat["assets"]), 4)
            original_ids = [aid for aid, info in mat["assets"].items() if info["variant"] == "original"]
            self.assertEqual(len(original_ids), 2)

    # ── Output count ───────────────────────────────────────────────────

    def test_output_count_zero_for_empty_result(self):
        """Empty result produces zero output count."""
        result_data = {"outputs": {}}
        with tempfile.TemporaryDirectory() as tmp:
            mat = self.module._materialize_experiment_output(
                result_data, str(Path(tmp) / "out"), cell_key="c1", attempt_id="a1",
            )
            self.assertEqual(mat["output_count"], 0)
            self.assertEqual(len(mat["assets"]), 0)
            self.assertIsNone(mat["primary_output"])
            self.assertEqual(mat["primary_asset_id"], "")
