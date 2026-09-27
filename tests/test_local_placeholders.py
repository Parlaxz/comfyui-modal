import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "local_placeholders.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("local_placeholders.py missing")
    spec = importlib.util.spec_from_file_location("local_placeholders", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LocalPlaceholderTests(unittest.TestCase):
    def test_creates_exact_filename_zero_byte_placeholder(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            result = module.create_local_placeholder(tmp, "text_encoders", "qwen_3_8b_fp8mixed.safetensors")
            self.assertTrue(result["created"])
            self.assertFalse(result["existed"])
            self.assertEqual(result["folder"], "text_encoders")
            self.assertEqual(result["filename"], "qwen_3_8b_fp8mixed.safetensors")
            self.assertEqual(result["size"], 0)
            self.assertTrue(result["is_placeholder"])
            self.assertFalse(result["is_real_file"])
            self.assertEqual(
                Path(result["local_path"]),
                Path(tmp) / "models" / "text_encoders" / "qwen_3_8b_fp8mixed.safetensors",
            )

    def test_preserves_existing_non_empty_file(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "models" / "vae"
            target.mkdir(parents=True)
            file_path = target / "flux2-vae.safetensors"
            file_path.write_bytes(b"real-model")

            result = module.create_local_placeholder(tmp, "vae", "flux2-vae.safetensors")

            self.assertFalse(result["created"])
            self.assertTrue(result["existed"])
            self.assertEqual(result["size"], len(b"real-model"))
            self.assertFalse(result["is_placeholder"])
            self.assertTrue(result["is_real_file"])
            self.assertEqual(file_path.read_bytes(), b"real-model")

    def test_reports_existing_zero_byte_placeholder(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "models" / "diffusion_models"
            target.mkdir(parents=True)
            file_path = target / "flux-2-klein-9b-fp8.safetensors"
            file_path.write_bytes(b"")

            result = module.create_local_placeholder(tmp, "diffusion_models", "flux-2-klein-9b-fp8.safetensors")

            self.assertFalse(result["created"])
            self.assertTrue(result["existed"])
            self.assertEqual(result["size"], 0)
            self.assertTrue(result["is_placeholder"])
            self.assertFalse(result["is_real_file"])

    def test_rejects_path_traversal_and_absolute_paths(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            invalid_cases = [
                ("text_encoders", "../evil.safetensors"),
                ("text_encoders", "..\\evil.safetensors"),
                ("text_encoders", "C:\\Users\\parla\\evil.safetensors"),
                ("text_encoders", "/etc/passwd"),
                ("folder/subfolder", "name.safetensors"),
                ("text_encoders", "nested/name.safetensors"),
            ]

            for folder, filename in invalid_cases:
                with self.subTest(folder=folder, filename=filename):
                    with self.assertRaises(ValueError):
                        module.create_local_placeholder(tmp, folder, filename)

    def test_batch_creation_supports_requested_examples(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            results = module.create_local_placeholders(
                tmp,
                [
                    {"folder": "text_encoders", "filename": "qwen_3_8b_fp8mixed.safetensors"},
                    {"folder": "diffusion_models", "filename": "flux-2-klein-9b-fp8.safetensors"},
                    {"folder": "vae", "filename": "flux2-vae.safetensors"},
                ],
            )

            self.assertEqual(len(results), 3)
            self.assertTrue(all(item["size"] == 0 for item in results))
            self.assertTrue(all(item["created"] for item in results))
            self.assertEqual(results[0]["filename"], "qwen_3_8b_fp8mixed.safetensors")
            self.assertEqual(results[1]["filename"], "flux-2-klein-9b-fp8.safetensors")
            self.assertEqual(results[2]["filename"], "flux2-vae.safetensors")


if __name__ == "__main__":
    unittest.main()
