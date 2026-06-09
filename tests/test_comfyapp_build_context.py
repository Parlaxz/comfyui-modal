import importlib.util
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, call, patch

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
    def test_comfyui_modal_node_ignores_generated_deploy_artifacts(self):
        module = load_module()

        patterns = module._custom_node_image_ignore_patterns("comfyui-modal")

        self.assertIn(".deploy_log", patterns)
        self.assertIn(".custom_node_requirements/", patterns)
        self.assertIn(".deployed_state.json", patterns)
        self.assertIn(".hf_token", patterns)
        self.assertIn(".civitai_token", patterns)
        self.assertIn("latest_benchmark_workflow.json", patterns)

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
            self.assertTrue((target_root / "sharedlib" / "pyproject.toml").is_file())

    def test_prepare_requirements_build_context_copies_included_requirement_files(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp) / "custom_nodes"
            target_root = Path(tmp) / "requirements_ctx"

            node = source_root / "node-a"
            local_src = node / "src" / "sam3"
            local_src.mkdir(parents=True)
            (local_src / "__init__.py").write_text("print('sam3')\n", encoding="utf-8")
            (node / "requirements.txt").write_text("-r extras.txt\n", encoding="utf-8")
            (node / "extras.txt").write_text("./src/sam3\n", encoding="utf-8")

            module._prepare_custom_node_requirements_build_context(str(source_root), str(target_root))

            files = [str(p.relative_to(target_root)) for p in target_root.rglob("*") if p.is_file()]
            if not (target_root / "node-a" / "requirements.txt").is_file():
                import sys
                print(f"DEBUG: files in target_root: {sorted(files)}", flush=True)
            self.assertTrue((target_root / "node-a" / "requirements.txt").is_file())
            self.assertTrue((target_root / "node-a" / "extras.txt").is_file())
            self.assertTrue((target_root / "node-a" / "src" / "sam3" / "__init__.py").is_file())

    def test_prepare_requirements_build_context_does_not_rewrite_unchanged_nodes(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp) / "custom_nodes"
            target_root = Path(tmp) / "requirements_ctx"
            node = source_root / "node-a"
            node.mkdir(parents=True)
            (node / "requirements.txt").write_text("numpy\n", encoding="utf-8")

            module._prepare_custom_node_requirements_build_context(str(source_root), str(target_root))

            with patch.object(module, "_rmtree_robust") as rmtree_mock:
                module._prepare_custom_node_requirements_build_context(str(source_root), str(target_root))

        rmtree_mock.assert_not_called()

    def test_prepare_requirements_build_context_rewrites_only_changed_node(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp) / "custom_nodes"
            target_root = Path(tmp) / "requirements_ctx"
            node_a = source_root / "node-a"
            node_b = source_root / "node-b"
            node_a.mkdir(parents=True)
            node_b.mkdir(parents=True)
            (node_a / "requirements.txt").write_text("numpy\n", encoding="utf-8")
            (node_b / "requirements.txt").write_text("torch\n", encoding="utf-8")

            module._prepare_custom_node_requirements_build_context(str(source_root), str(target_root))
            (node_a / "requirements.txt").write_text("numpy==2.0.0\n", encoding="utf-8")

            with patch.object(module, "_rmtree_robust", wraps=module._rmtree_robust) as rmtree_mock:
                module._prepare_custom_node_requirements_build_context(str(source_root), str(target_root))

        rmtree_mock.assert_has_calls([call(str(target_root / "node-a"))])
        self.assertEqual(rmtree_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
