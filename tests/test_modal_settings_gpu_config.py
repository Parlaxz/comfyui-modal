import unittest
from pathlib import Path


SETTINGS_PATH = Path(__file__).resolve().parents[1] / "web" / "modal-settings.js"


class ModalSettingsGpuConfigTests(unittest.TestCase):
    def test_frontend_fetches_config_before_setting_gpu_options(self):
        source = SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertIn("available_gpus", source)
        self.assertIn("default_gpu", source)
        self.assertNotIn("const GPU_OPTIONS = [", source)

    def test_frontend_populates_dropdown_from_backend_options(self):
        source = SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertIn("setGpuOptions", source)
        self.assertIn("pickInitialGpu", source)


if __name__ == "__main__":
    unittest.main()
