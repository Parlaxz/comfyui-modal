import importlib.util
import os
import sys
import tempfile
import types
import uuid
import unittest
from pathlib import Path
from unittest.mock import MagicMock


REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"


def _make_modal_stub():
    """Return a stub module that replaces ``modal`` so ``comfyapp.py`` can be
    imported without cloud credentials or live Modal API calls."""
    stub = types.ModuleType("modal")

    # Image builder — chained .apt_install().pip_install().run_commands()
    stub.Image = MagicMock()
    stub.Image.debian_slim.return_value.apt_install.return_value.pip_install\
        .return_value.run_commands.return_value = MagicMock()

    # App — used as @app.function / @app.cls decorators at module level
    stub.App = MagicMock()
    stub.App.return_value.function = lambda **kw: (lambda f: f)
    stub.App.return_value.cls = lambda **kw: (lambda c: c)

    # Volume — .from_name should not reach the cloud
    stub.Volume = MagicMock()
    stub.Volume.from_name.return_value = MagicMock()

    # Decorators used on methods / classes
    stub.web_server = lambda *a, **kw: (lambda f: f)
    stub.enter = lambda **kw: (lambda f: f)
    stub.exit = lambda: (lambda f: f)
    stub.method = lambda: (lambda f: f)
    stub.concurrent = lambda **kw: (lambda c: c)

    return stub


def _unique_module_name():
    return f"comfyapp_test_{uuid.uuid4().hex}"


def load_module():
    """Import ``comfyapp.py`` under a unique module name with ``modal`` stubbed.

    The stub prevents any cloud API calls during module-level execution.
    The real ``modal`` module and the test module are both cleaned up from
    ``sys.modules`` so each call gets a fresh compile.
    """
    original_modal = sys.modules.pop("modal", None)
    sys.modules["modal"] = _make_modal_stub()
    module_name = _unique_module_name()
    try:
        spec = importlib.util.spec_from_file_location(
            module_name, str(COMFYAPP_PATH),
        )
        assert spec is not None, f"Could not create spec for {COMFYAPP_PATH}"
        assert spec.loader is not None, f"Spec for {COMFYAPP_PATH} has no loader"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if original_modal is not None:
            sys.modules["modal"] = original_modal
        else:
            sys.modules.pop("modal", None)
        sys.modules.pop(module_name, None)


def _nonexistent_path() -> str:
    """Return a string path that is guaranteed not to exist on any platform."""
    return str(Path(tempfile.gettempdir()) / uuid.uuid4().hex / "requirements.txt")


class ComfyAppRuntimeStateTests(unittest.TestCase):
    def test_requirements_hash_changes_with_file_contents(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / "requirements.txt"
            req.write_text("xformers==0.0.29\n", encoding="utf-8")
            before = module.requirements_file_hash(str(req))
            req.write_text("xformers==0.0.30\n", encoding="utf-8")
            after = module.requirements_file_hash(str(req))
            self.assertNotEqual(before, after)

    def test_missing_requirements_hash_is_none(self):
        module = load_module()
        self.assertIsNone(module.requirements_file_hash(_nonexistent_path()))


if __name__ == "__main__":
    unittest.main()
