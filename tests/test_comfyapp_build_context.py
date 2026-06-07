import importlib.util
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"


def _make_modal_stub():
    stub = types.ModuleType("modal")
    stub.Image = MagicMock()
    stub.Image.debian_slim.return_value.apt_install.return_value.pip_install.return_value.run_commands.return_value = MagicMock()
    stub.App = MagicMock()
    stub.App.return_value.function = lambda **kw: (lambda f: f)
    stub.App.return_value.cls = lambda **kw: (lambda c: c)
    stub.Volume = MagicMock()
    stub.Volume.from_name.return_value = MagicMock()
    stub.Secret = MagicMock()
    stub.Secret.from_name.return_value = MagicMock()
    stub.web_server = lambda *a, **kw: (lambda f: f)
    stub.enter = lambda **kw: (lambda f: f)
    stub.exit = lambda: (lambda f: f)
    stub.method = lambda *a, **kw: (lambda f: f)
    stub.concurrent = lambda **kw: (lambda c: c)
    return stub


def load_module():
    original_modal = sys.modules.pop("modal", None)
    module_name = f"comfyapp_build_ctx_{uuid.uuid4().hex}"
    sys.modules["modal"] = _make_modal_stub()
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(COMFYAPP_PATH))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if original_modal is not None:
            sys.modules["modal"] = original_modal
        else:
            sys.modules.pop("modal", None)
        sys.modules.pop(module_name, None)


class ComfyAppBuildContextTests(unittest.TestCase):
    def test_prepare_requirements_build_context_copies_only_requirements_files(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp) / "custom_nodes"
            target_root = Path(tmp) / "requirements_ctx"

            node_a = source_root / "node-a"
            node_b = source_root / "node-b"
            ignored = source_root / "__pycache__"
            node_a.mkdir(parents=True)
            node_b.mkdir(parents=True)
            ignored.mkdir(parents=True)

            (node_a / "requirements.txt").write_text("numpy\n", encoding="utf-8")
            (node_a / "nodes.py").write_text("print('hi')\n", encoding="utf-8")
            (node_b / "requirements.txt").write_text("torch\n", encoding="utf-8")
            (ignored / "requirements.txt").write_text("should-not-copy\n", encoding="utf-8")

            module._prepare_custom_node_requirements_build_context(str(source_root), str(target_root))

            self.assertTrue((target_root / "node-a" / "requirements.txt").is_file())
            self.assertTrue((target_root / "node-b" / "requirements.txt").is_file())
            self.assertFalse((target_root / "node-a" / "nodes.py").exists())
            self.assertFalse((target_root / "__pycache__").exists())
            self.assertEqual((target_root / "node-a" / "requirements.txt").read_text(encoding="utf-8"), "numpy\n")
            self.assertEqual((target_root / "node-b" / "requirements.txt").read_text(encoding="utf-8"), "torch\n")

    def test_prepare_requirements_build_context_copies_local_path_dependencies(self):
        """Local path deps (e.g. ./src/sam3) in requirements.txt are copied
        alongside requirements.txt so pip install resolves correctly."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp) / "custom_nodes"
            target_root = Path(tmp) / "requirements_ctx"

            node = source_root / "comfyui_sam3"
            local_src = node / "src" / "sam3"
            local_src.mkdir(parents=True)
            (local_src / "__init__.py").write_text("print('sam3')\n", encoding="utf-8")
            (node / "requirements.txt").write_text("numpy\n./src/sam3\n", encoding="utf-8")

            module._prepare_custom_node_requirements_build_context(str(source_root), str(target_root))

            # requirements.txt copied
            self.assertTrue((target_root / "comfyui_sam3" / "requirements.txt").is_file())
            # Local path dep directory copied
            self.assertTrue((target_root / "comfyui_sam3" / "src" / "sam3" / "__init__.py").is_file())
            # Non-requirements files from other imaginary nodes NOT copied
            self.assertFalse((target_root / "comfyui_sam3" / "__pycache__").exists())


if __name__ == "__main__":
    unittest.main()
