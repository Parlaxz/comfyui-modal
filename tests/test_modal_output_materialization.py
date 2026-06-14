import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_input_image_paths import _load_init_module


def _entry(filename: str, payload: bytes, *, node_id: str = "107", output_key: str, comparison_side: str, output_index: int):
    return {
        "filename": filename,
        "data": base64.b64encode(payload).decode("ascii"),
        "node_id": node_id,
        "output_key": output_key,
        "comparison_side": comparison_side,
        "mime_type": "image/png",
        "file_ext": ".png",
        "output_index": output_index,
        "format": "png",
        "width": 64,
        "height": 64,
    }


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
