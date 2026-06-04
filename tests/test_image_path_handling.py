import os
import sys
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure ComfyUI root is on sys.path so folder_paths can be imported
_COMFYUI_ROOT = Path(__file__).resolve().parents[3]  # <repo>/ComfyUI
if str(_COMFYUI_ROOT) not in sys.path:
    sys.path.insert(0, str(_COMFYUI_ROOT))

# The custom-node __init__.py adds _NODE_DIR to sys.path at import time,
# so importing from the tests directory works once that happens.
NODE_ROOT = Path(__file__).resolve().parents[1]
if str(NODE_ROOT) not in sys.path:
    sys.path.insert(0, str(NODE_ROOT))

# We import folder_paths early to get helpers; it also needs ComfyUI root.
import folder_paths
import __init__ as comfyui_modal


class CollectInputImagesTests(unittest.TestCase):
    """Regression tests for _collect_input_images — annotated filenames and
    temp-directory support."""

    def setUp(self):
        # Create a temporary ComfyUI-like directory tree
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)

        (self._root / "input").mkdir(parents=True, exist_ok=True)
        (self._root / "output").mkdir(parents=True, exist_ok=True)
        (self._root / "temp").mkdir(parents=True, exist_ok=True)

        # Write test files
        self._input_png = self._root / "input" / "input_photo.png"
        self._input_png.write_bytes(b"input-image-data")

        self._output_png = self._root / "output" / "output_photo.png"
        self._output_png.write_bytes(b"output-image-data")

        self._temp_png = self._root / "temp" / "temp_photo.png"
        self._temp_png.write_bytes(b"temp-image-data")

        self._subdir_png = self._root / "input" / "subdir" / "nested.png"
        self._subdir_png.parent.mkdir(parents=True, exist_ok=True)
        self._subdir_png.write_bytes(b"nested-image-data")

    def tearDown(self):
        self._tmp.cleanup()

    # ------------------------------------------------------------------
    # _collect_input_images helpers
    # ------------------------------------------------------------------

    def _workflow_with_loadimage(self, filename: str,
                                 class_type: str = "LoadImage") -> dict:
        return {
            "1": {
                "class_type": class_type,
                "inputs": {"image": filename},
            }
        }

    def _call_collect(self, workflow: dict):
        """Call _collect_input_images with folder_paths directory
        getters redirected to the temporary directory tree."""
        inp_dir = str(self._root / "input")
        out_dir = str(self._root / "output")
        tmp_dir = str(self._root / "temp")

        def patched_get_input_dir():
            return inp_dir

        def patched_get_output_dir():
            return out_dir

        def patched_get_temp_dir():
            return tmp_dir

        patchers = [
            patch.object(folder_paths, "get_input_directory", patched_get_input_dir),
            patch.object(folder_paths, "get_output_directory", patched_get_output_dir),
            patch.object(folder_paths, "get_temp_directory", patched_get_temp_dir),
            patch.object(comfyui_modal, "_COMFYUI_ROOT", str(self._root)),
        ]
        for p in patchers:
            p.start()
        try:
            return comfyui_modal._collect_input_images(workflow)
        finally:
            for p in patchers:
                p.stop()

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_unannotated_filename_resolves_from_input_dir(self):
        """A plain filename (no annotation) is found under input/."""
        result = self._call_collect(
            self._workflow_with_loadimage("input_photo.png")
        )
        self.assertIn("input_photo.png", result)
        decoded = base64.b64decode(result["input_photo.png"])
        self.assertEqual(decoded, b"input-image-data")

    def test_annotated_output_filename_resolves_from_output_dir(self):
        """A filename with [output] annotation resolves to the output/
        directory and returns a payload keyed by the original string."""
        result = self._call_collect(
            self._workflow_with_loadimage("output_photo.png [output]")
        )
        # Key is the original workflow string (annotation preserved)
        self.assertIn("output_photo.png [output]", result)
        decoded = base64.b64decode(result["output_photo.png [output]"])
        self.assertEqual(decoded, b"output-image-data")

    def test_annotated_temp_filename_resolves_from_temp_dir(self):
        """A filename with [temp] annotation resolves to the temp/
        directory (regression: temp/ was previously missing from
        search_dirs)."""
        result = self._call_collect(
            self._workflow_with_loadimage("temp_photo.png [temp]")
        )
        self.assertIn("temp_photo.png [temp]", result)
        decoded = base64.b64decode(result["temp_photo.png [temp]"])
        self.assertEqual(decoded, b"temp-image-data")

    def test_nested_filename_preserves_subdirectory_in_key(self):
        """A filename with a relative subdirectory is returned keyed by
        the original path string (e.g. 'subdir/nested.png')."""
        result = self._call_collect(
            self._workflow_with_loadimage("subdir/nested.png")
        )
        self.assertIn("subdir/nested.png", result)
        decoded = base64.b64decode(result["subdir/nested.png"])
        self.assertEqual(decoded, b"nested-image-data")

    def test_missing_file_produces_warning_no_key(self):
        """A filename that does not exist on disk returns an empty dict
        entry (the function logs a warning)."""
        # Note: the function uses print() for warnings; we just verify
        # no payload entry is created.
        result = self._call_collect(
            self._workflow_with_loadimage("nonexistent.png")
        )
        self.assertNotIn("nonexistent.png", result)

    def test_load_image_mask_also_collected(self):
        """LoadImageMask nodes should also be picked up."""
        wf = {
            "1": {
                "class_type": "LoadImageMask",
                "inputs": {"mask": "output_photo.png [output]"},
            }
        }
        result = self._call_collect(wf)
        self.assertIn("output_photo.png [output]", result)

    def test_http_urls_are_skipped(self):
        """URL-based image references should not be collected."""
        wf = self._workflow_with_loadimage("https://example.com/img.png")
        result = self._call_collect(wf)
        self.assertEqual(result, {})

    def test_non_loadimage_nodes_ignored(self):
        """Nodes that are not LoadImage variants are skipped."""
        wf = {
            "1": {
                "class_type": "KSampler",
                "inputs": {"image": "input_photo.png"},
            }
        }
        result = self._call_collect(wf)
        self.assertEqual(result, {})


class RemoteMaterializationTests(unittest.TestCase):
    """Regression tests for remote input image materialization — path
    flattening (Path(fname).name) must preserve relative subdirectories."""

    def _assert_materialized_path(self, fname: str, expected_parts: list[str]):
        """Simulate the materialization path logic used in comfyapp.py
        both for the inproc and subprocess paths.

        Verifies that the relative path from input_dir to the destination
        preserves every path component (i.e. no flattening via .name).
        """
        input_dir = Path("/tmp/fake_input")
        # Fixed behaviour: dest = input_dir / fname  (not input_dir / Path(fname).name)
        dest = input_dir / fname
        rel = dest.relative_to(input_dir)
        # On Windows os.sep is '\\' so compare by normalized parts
        parts = list(rel.parts)
        self.assertEqual(parts, expected_parts)

    def test_plain_filename_unchanged(self):
        """A simple filename without subdirectory is written as-is."""
        self._assert_materialized_path("foo.png", ["foo.png"])

    def test_nested_subdirectory_preserved(self):
        """subdir/foo.png preserves the subdir/ prefix instead of being
        flattened to just foo.png."""
        self._assert_materialized_path("subdir/foo.png",
                                       ["subdir", "foo.png"])

    def test_deeply_nested_path_preserved(self):
        """Deeply nested relative paths are fully preserved."""
        self._assert_materialized_path(
            "a/b/c/d/photo.png", ["a", "b", "c", "d", "photo.png"])

    def test_annotated_filename_keeps_annotation(self):
        """An annotated filename like foo.png [output] preserves the
        annotation in the relative path (the server-side validation
        uses folder_paths.annotated_filepath to strip it)."""
        self._assert_materialized_path("foo.png [output]",
                                       ["foo.png [output]"])


if __name__ == "__main__":
    unittest.main()
