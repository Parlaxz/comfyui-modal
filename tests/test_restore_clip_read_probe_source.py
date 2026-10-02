from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from comfymodal_runtime import modal_app


class RestoreClipReadProbeSourceTests(unittest.TestCase):
    def test_default_source_selection_uses_models_volume(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(modal_app._RESTORE_CLIP_PROBE_SOURCE_ENV, None)
            source = modal_app._prepare_restore_clip_probe_source()

        self.assertEqual(source["source_mode"], "models_volume")
        self.assertEqual(
            source["path"],
            os.path.join("/root/models", "text_encoders", "qwen_3_4b.safetensors"),
        )
        self.assertEqual(source["staging_status"], "not_required")

    def test_source_selector_is_deploy_baked(self):
        with patch.dict(
            os.environ,
            {modal_app._RESTORE_CLIP_PROBE_SOURCE_ENV: "local_cache"},
        ):
            self.assertEqual(
                modal_app._runtime_env()[modal_app._RESTORE_CLIP_PROBE_SOURCE_ENV],
                "local_cache",
            )

    def test_local_source_selection_stages_and_validates_exact_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "source.safetensors"
            staged_path = root / "cache" / "qwen_3_4b.safetensors"
            payload = b"restore-clip-probe"
            source_path.write_bytes(payload)

            with patch.dict(
                os.environ,
                {modal_app._RESTORE_CLIP_PROBE_SOURCE_ENV: "local_cache"},
            ):
                source = modal_app._prepare_restore_clip_probe_source(
                    source_path=str(source_path),
                    staged_path=str(staged_path),
                )

            self.assertEqual(source["source_mode"], "local_cache")
            self.assertEqual(source["path"], str(staged_path))
            self.assertEqual(source["staging_status"], "ready")
            self.assertEqual(staged_path.read_bytes(), payload)
            validated = modal_app._validate_restore_clip_probe_staging(source)
            self.assertEqual(validated["staging_validation"], "ready")

    def test_local_source_missing_staged_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "source.safetensors"
            staged_path = root / "cache" / "qwen_3_4b.safetensors"
            source_path.write_bytes(b"source")
            source = modal_app._prepare_restore_clip_probe_source(
                "local_cache",
                source_path=str(source_path),
                staged_path=str(staged_path),
            )
            staged_path.unlink()

            with self.assertRaisesRegex(RuntimeError, "staged source is unavailable"):
                modal_app._validate_restore_clip_probe_staging(source)

    def test_local_source_size_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "source.safetensors"
            staged_path = root / "cache" / "qwen_3_4b.safetensors"
            source_path.write_bytes(b"source")
            source = modal_app._prepare_restore_clip_probe_source(
                "local_cache",
                source_path=str(source_path),
                staged_path=str(staged_path),
            )
            staged_path.write_bytes(b"mismatch")

            with self.assertRaisesRegex(RuntimeError, "staged size mismatch"):
                modal_app._validate_restore_clip_probe_staging(source)


if __name__ == "__main__":
    unittest.main()
