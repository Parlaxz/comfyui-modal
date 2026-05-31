import importlib
import os
import sys
import unittest
from types import ModuleType, SimpleNamespace

from gpu_catalog import _clear_hidden_cache


class ModalClientGpuConfigTests(unittest.TestCase):
    _ENV_KEY = "COMFYMODAL_HIDE_GPUS"

    def setUp(self):
        self._old_modal = sys.modules.get("modal")
        self._old_module = sys.modules.get("modal_client")
        self._old_env = os.environ.get(self._ENV_KEY)

    def tearDown(self):
        _clear_hidden_cache()
        if self._old_modal is None:
            sys.modules.pop("modal", None)
        else:
            sys.modules["modal"] = self._old_modal
        if self._old_module is None:
            sys.modules.pop("modal_client", None)
        else:
            sys.modules["modal_client"] = self._old_module
        if self._old_env is None:
            os.environ.pop(self._ENV_KEY, None)
        else:
            os.environ[self._ENV_KEY] = self._old_env

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

    # ── hidden GPU behaviour ─────────────────────────────────────────
    def test_hidden_gpu_rejected_by_set_gpu(self):
        os.environ[self._ENV_KEY] = "t4"
        _clear_hidden_cache()
        mod = self.load_module()
        with self.assertRaises(ValueError):
            mod.set_gpu("t4")
        mod.set_gpu("a10g")

    def test_hidden_gpu_excluded_from_apis(self):
        os.environ[self._ENV_KEY] = "l4,l40s"
        _clear_hidden_cache()
        mod = self.load_module()
        self.assertNotIn("l4", mod._apis)
        self.assertNotIn("l40s", mod._apis)
        self.assertIn("a10g", mod._apis)

    def test_hidden_gpu_excluded_from_available_gpus(self):
        os.environ[self._ENV_KEY] = "h100"
        _clear_hidden_cache()
        mod = self.load_module()
        gpus = mod.get_available_gpus()
        self.assertNotIn("h100", [g["value"] for g in gpus])

    def test_hidden_gpu_excluded_from_supported_gpus(self):
        os.environ[self._ENV_KEY] = "b200"
        _clear_hidden_cache()
        mod = self.load_module()
        self.assertNotIn("b200", mod.get_supported_gpus())


if __name__ == "__main__":
    unittest.main()
