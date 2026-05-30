import importlib
import sys
import unittest
from types import ModuleType, SimpleNamespace


class ModalClientGpuConfigTests(unittest.TestCase):
    def setUp(self):
        self._old_modal = sys.modules.get("modal")
        self._old_module = sys.modules.get("modal_client")

    def tearDown(self):
        if self._old_modal is None:
            sys.modules.pop("modal", None)
        else:
            sys.modules["modal"] = self._old_modal
        if self._old_module is None:
            sys.modules.pop("modal_client", None)
        else:
            sys.modules["modal_client"] = self._old_module

    def load_module(self):
        fake_modal = ModuleType("modal")
        setattr(fake_modal, "Cls", SimpleNamespace(from_name=lambda app, cls: lambda: f"{app}:{cls}"))
        setattr(fake_modal, "Function", SimpleNamespace(from_name=lambda app, fn: f"{app}:{fn}"))
        sys.modules["modal"] = fake_modal
        sys.modules.pop("modal_client", None)
        return importlib.import_module("modal_client")

    def test_set_gpu_accepts_supported_value(self):
        mod = self.load_module()
        mod.set_gpu("L4")
        self.assertEqual(mod.get_gpu(), "l4")

    def test_set_gpu_rejects_unsupported_value(self):
        mod = self.load_module()
        with self.assertRaises(ValueError):
            mod.set_gpu("bogus")

    def test_available_gpus_come_from_catalog(self):
        mod = self.load_module()
        self.assertIn("h200", mod.get_supported_gpus())

    def test_available_gpu_options_expose_label_and_value(self):
        mod = self.load_module()
        self.assertIn({"value": "b200", "label": "B200"}, mod.get_available_gpus())


if __name__ == "__main__":
    unittest.main()
