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

    def test_resolve_save_folder_empty_goes_to_external(self):
        """Empty/default save_folder now resolves to external <data-root>/outputs/modal."""
        with tempfile.TemporaryDirectory() as tmp:
            # empty → external data root
            resolved = output_saver._resolve_save_folder("", tmp)
            expected = str(output_saver._resolve_modal_output_dir())
            self.assertEqual(resolved, expected)

    def test_resolve_save_folder_legacy_modal_goes_to_external(self):
        """Legacy 'ComfyUI/output/modal' paths now resolve to external data root."""
        with tempfile.TemporaryDirectory() as tmp:
            resolved = output_saver._resolve_save_folder("ComfyUI/output/modal/", tmp)
            expected = str(output_saver._resolve_modal_output_dir())
            self.assertEqual(resolved, expected)

    def test_resolve_save_folder_other_relative_under_comfyui_root(self):
        """Other explicit relative paths still resolve under comfyui_root."""
        with tempfile.TemporaryDirectory() as tmp:
            resolved = output_saver._resolve_save_folder("custom_output/experiment1", tmp)
            self.assertEqual(resolved, output_saver.os.path.join(tmp, "custom_output", "experiment1"))
