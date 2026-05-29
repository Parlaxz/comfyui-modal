import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"


class ComfyAppPackagingTests(unittest.TestCase):
    def test_comfyapp_does_not_import_sibling_custom_node_sync_module(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("from custom_node_sync import", source)


if __name__ == "__main__":
    unittest.main()
