import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"


class ComfyappAstTests(unittest.TestCase):
    def test_deprecated_warmup_secret_is_not_hardcoded(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("comfyui-warmup-dev", source)


if __name__ == "__main__":
    unittest.main()
