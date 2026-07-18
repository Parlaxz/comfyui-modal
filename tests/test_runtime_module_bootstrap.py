"""Ensure the v2 package has no import-time dependency cycle."""

from __future__ import annotations

import importlib
import unittest


MODULES = (
    "contracts",
    "deployment_spec",
    "deployment_service",
    "runtime_state",
    "restore_plan",
    "modal_transport",
    "modal_app",
    "runtime_bootstrap",
    "model_preload",
    "runtime_executor",
    "output_delivery",
    "result_delivery",
    "playground_service",
    "trace",
    "compatibility",
)


class TestRuntimeModuleBootstrap(unittest.TestCase):
    def test_all_runtime_modules_import(self):
        for module in MODULES:
            with self.subTest(module=module):
                self.assertIsNotNone(importlib.import_module(f"comfymodal_runtime.{module}"))


if __name__ == "__main__":
    unittest.main()
