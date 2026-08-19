"""Focused offline checks for the E16 source-I/O harness and wrappers."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

import e16_source_io as e16


def _write_shard(path: Path) -> None:
    header = {
        "a": {"dtype": "F16", "shape": [4], "data_offsets": [0, 8]},
        "b": {"dtype": "F16", "shape": [2], "data_offsets": [8, 12]},
    }
    raw = json.dumps(header, separators=(",", ":")).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"abcdefghijkl")


class E16HarnessTests(unittest.TestCase):
    def test_header_parse_does_not_require_payload_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weights.safetensors"
            _write_shard(path)
            manifest = e16.parse_safetensors_header(path)
        self.assertEqual(manifest["tensor_count"], 2)
        self.assertEqual(manifest["tensor_bytes"], 12)
        self.assertEqual(manifest["gap_bytes"], 0)
        self.assertNotIn("sha256", manifest)

    def test_model_plan_resolution_is_data_driven(self):
        plan = {
            "restore_plan": {
                "model_spec": {
                    "loaders": {
                        "clip": [{"clip_name": "clip.safetensors"}],
                        "unet": [{"unet_name": "unet.safetensors"}],
                    }
                }
            }
        }
        requests = e16.model_requests_from_plan(plan)
        self.assertEqual(
            requests,
            [
                {"role": "CLIP", "filename": "clip.safetensors", "folder": "text_encoders"},
                {"role": "UNET", "filename": "unet.safetensors", "folder": "diffusion_models"},
            ],
        )

    def test_contiguous_regions_preserve_gaps(self):
        manifest = {
            "tensors": [
                {"begin": 10, "end": 14},
                {"begin": 14, "end": 18},
                {"begin": 20, "end": 22},
            ]
        }
        self.assertEqual(e16.contiguous_regions(manifest), [(10, 18), (20, 22)])

    def test_range_and_mmap_arms_validate_identical_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weights.safetensors"
            _write_shard(path)
            manifest = e16.manifest_for_path(path, "CLIP")
            expected = e16.payload_digest(manifest)
            current = e16.run_current_range(manifest, expected_digest=expected, range_bytes=4)
            mapped = e16.run_mmap(manifest, expected_digest=expected, block_bytes=4)
            staged = e16.run_tmp_stage([manifest], expected_digest=expected, block_bytes=4, temp_root=directory)
        self.assertEqual(current["status"], "ok")
        self.assertEqual(mapped["status"], "ok")
        self.assertTrue(current["digest_match"])
        self.assertTrue(mapped["digest_match"])
        self.assertEqual(current["source_bytes_read"], 12)
        self.assertEqual(mapped["source_bytes_read"], 12)
        self.assertEqual(staged["status"], "ok")
        self.assertEqual(staged["wall_ms"], staged["combined_ms"])
        self.assertEqual(staged["process_cpu_ms"], staged["temp_copy_cpu_ms"] + staged["temp_reread_cpu_ms"])

    def test_tmp_capacity_unknown_for_missing_path(self):
        result = e16.inspect_tmp("C:\\path-that-does-not-exist", 1)
        self.assertEqual(result["capacity"], "UNKNOWN")


class E16WrapperTests(unittest.TestCase):
    def test_deploy_wrapper_is_dedicated(self):
        text = Path("deploy_e16_source_benchmark.bat").read_text(encoding="utf-8")
        self.assertIn("deploy -m e16_source_io_modal", text)
        self.assertNotIn("deploy_and_run_v2_single.bat", text)
        self.assertIn("COMFYMODAL_E16_SOURCE_BENCHMARK=1", text)

    def test_run_wrapper_uses_modal_run_and_crossover(self):
        text = Path("run_e16_source_benchmark.bat").read_text(encoding="utf-8")
        self.assertIn("run -m e16_source_io_modal", text)
        self.assertIn("CLIP_CURRENT_FIRST", text)
        self.assertIn("CLIP_SOURCE_FIRST", text)
        self.assertNotIn("python e16_source_io_modal.py", text)

    def test_volume_creation_guard_is_e16_only(self):
        text = Path("comfyapp.py").read_text(encoding="utf-8")
        self.assertIn("COMFYMODAL_E16_SOURCE_BENCHMARK", text)
        self.assertIn("_VOLUME_CREATE_IF_MISSING", text)
        self.assertIn("not _E16_READ_ONLY_VOLUME_LOOKUP", text)


if __name__ == "__main__":
    unittest.main()
