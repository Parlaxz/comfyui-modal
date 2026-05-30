import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"


class ComfyAppPackagingTests(unittest.TestCase):
    def test_comfyapp_does_not_import_sibling_custom_node_sync_module(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("from custom_node_sync import", source)

    def test_comfyapp_does_not_top_level_import_httpx(self):
        tree = ast.parse(COMFYAPP_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertNotIn("httpx", imported)

    def test_all_modal_images_include_gpu_catalog_source(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count('add_local_python_source("gpu_catalog")'), 6)


if __name__ == "__main__":
    unittest.main()
