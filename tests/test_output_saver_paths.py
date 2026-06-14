import tempfile
import unittest

import output_saver


class OutputSaverPathTests(unittest.TestCase):
    def test_normalize_save_folder_legacy_and_relative_values(self):
        cases = {
            "": "",
            "output/modal": "output/modal",
            "output/modal/": "output/modal",
            "ComfyUI/output/modal": "output/modal",
            "ComfyUI/output/modal/": "output/modal",
            "ComfyUI\\output\\modal\\": "output/modal",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(getattr(output_saver, "_normalize_save_folder")(raw), expected)

    def test_resolve_save_folder_preserves_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            absolute = output_saver._resolve_save_folder(tmp, "C:/comfy")
            self.assertEqual(absolute, tmp)

    def test_resolve_save_folder_defaults_under_comfyui_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            resolved = output_saver._resolve_save_folder("ComfyUI/output/modal/", tmp)
            self.assertEqual(resolved, output_saver.os.path.join(tmp, "output", "modal"))
