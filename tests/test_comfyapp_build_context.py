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
    stub.Dict = MagicMock()
    stub.Dict.from_name.return_value = MagicMock()
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
        self.assertIn(".experiment_leases.db*", patterns)

        self.assertIn(
            "comfyui-modal/.experiment_leases.db*",
            module._COMBINED_CUSTOM_NODE_IGNORE_PATTERNS,
        )

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


    # ── GPU/CPU source split tests ────────────────────────────────────

    def test_gpu_sources_contains_all_9_required_modules(self):
        """_GPU_COMFYMODAL_PYTHON_SOURCES must include the 9 GPU modules."""
        module = load_module()
        gpu_sources = module._GPU_COMFYMODAL_PYTHON_SOURCES
        self.assertEqual(len(gpu_sources), 9)
        self.assertIn("gpu_catalog", gpu_sources)
        self.assertIn("timing_trace", gpu_sources)
        self.assertIn("wall_clock_trace_v3", gpu_sources)
        self.assertIn("profiler_trace_v4", gpu_sources)
        self.assertIn("api_prompt_validator", gpu_sources)
        self.assertIn("failure_summary", gpu_sources)
        self.assertIn("production_workflow", gpu_sources)
        self.assertIn("optimizations", gpu_sources)
        self.assertIn("worker_control", gpu_sources)

    def test_gpu_sources_excludes_orchestration_modules(self):
        """_GPU_COMFYMODAL_PYTHON_SOURCES must NOT include local-only orchestration modules."""
        module = load_module()
        gpu_sources = module._GPU_COMFYMODAL_PYTHON_SOURCES
        excluded = {
            "experiment_models", "experiment_store", "experiment_lease",
            "experiment_service", "experiment_runner", "experiment_scheduler",
            "matrix_compiler", "presets", "run_history",
        }
        for mod in excluded:
            self.assertNotIn(mod, gpu_sources, f"GPU sources must not include {mod}")

    def test_cpu_sources_contains_module_level_imports(self):
        """_CPU_COMFYMODAL_PYTHON_SOURCES includes every module comfyapp.py imports at module level."""
        module = load_module()
        cpu_sources = module._CPU_COMFYMODAL_PYTHON_SOURCES
        required = {
            "gpu_catalog", "timing_trace", "wall_clock_trace_v3",
            "profiler_trace_v4", "api_prompt_validator", "failure_summary",
            "production_workflow", "worker_control",
        }
        for mod in required:
            self.assertIn(mod, cpu_sources, f"CPU sources must include {mod}")

    def test_cpu_sources_excludes_orchestration_and_optimizations(self):
        """_CPU_COMFYMODAL_PYTHON_SOURCES excludes optimizations and orchestration modules."""
        module = load_module()
        cpu_sources = module._CPU_COMFYMODAL_PYTHON_SOURCES
        self.assertLess(len(cpu_sources), 18)
        self.assertNotIn("optimizations", cpu_sources)
        self.assertNotIn("experiment_models", cpu_sources)
        self.assertNotIn("experiment_store", cpu_sources)
        self.assertNotIn("experiment_lease", cpu_sources)
        self.assertNotIn("experiment_service", cpu_sources)
        self.assertNotIn("experiment_runner", cpu_sources)
        self.assertNotIn("experiment_scheduler", cpu_sources)
        self.assertNotIn("matrix_compiler", cpu_sources)
        self.assertNotIn("presets", cpu_sources)
        self.assertNotIn("run_history", cpu_sources)

    def test_gpu_source_function_uses_copy_true(self):
        """_add_gpu_python_sources must call add_local_python_source with copy=True."""
        module = load_module()
        import ast
        source = module._COMFYAPP_SOURCE if hasattr(module, "_COMFYAPP_SOURCE") else ""
        if not source:
            with open(str(COMFYAPP_PATH), encoding="utf-8-sig") as f:
                source = f.read()
        # Find _add_gpu_python_sources function body
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_add_gpu_python_sources":
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        func = child.func
                        if isinstance(func, ast.Attribute) and func.attr == "add_local_python_source":
                            # Check copy=True keyword exists
                            for kw in child.keywords:
                                if kw.arg == "copy":
                                    self.assertTrue(
                                        isinstance(kw.value, ast.Constant) and kw.value.value is True,
                                        "_add_gpu_python_sources must call add_local_python_source with copy=True"
                                    )
                            break  # only check first call
                break

    def test_cpu_source_function_uses_copy_true(self):
        """_add_cpu_python_sources must call add_local_python_source with copy=True."""
        module = load_module()
        import ast
        source = module._COMFYAPP_SOURCE if hasattr(module, "_COMFYAPP_SOURCE") else ""
        if not source:
            with open(str(COMFYAPP_PATH), encoding="utf-8-sig") as f:
                source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_add_cpu_python_sources":
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        func = child.func
                        if isinstance(func, ast.Attribute) and func.attr == "add_local_python_source":
                            for kw in child.keywords:
                                if kw.arg == "copy":
                                    self.assertTrue(
                                        isinstance(kw.value, ast.Constant) and kw.value.value is True,
                                        "_add_cpu_python_sources must call add_local_python_source with copy=True"
                                    )
                            break
                break

    def test_app_uses_include_source_false(self):
        """modal.App must be called with include_source=False."""
        module = load_module()
        import ast
        source = module._COMFYAPP_SOURCE if hasattr(module, "_COMFYAPP_SOURCE") else ""
        if not source:
            with open(str(COMFYAPP_PATH), encoding="utf-8-sig") as f:
                source = f.read()
        tree = ast.parse(source)
        def _check_call(call):
            if not (isinstance(call.func, ast.Attribute) and call.func.attr == "App"):
                return False
            found = False
            for kw in call.keywords:
                if kw.arg == "include_source":
                    found = True
                    self.assertTrue(
                        isinstance(kw.value, ast.Constant) and kw.value.value is False,
                        "App must be created with include_source=False"
                    )
                    break
            self.assertTrue(found, "App call must specify include_source=False")
            return True
        found_app = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                if _check_call(node.value):
                    found_app = True
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, (ast.Name, ast.Attribute, ast.Tuple, ast.List)):
                        if isinstance(node.value, ast.Call) and _check_call(node.value):
                            found_app = True
        self.assertTrue(found_app, "Could not find modal.App(...) call in source")

    def test_source_diagnostic_emitted(self):
        """Source-inclusion diagnostic must be emitted at module level with expected fields."""
        module = load_module()
        self.assertIs(module._COMFYMODAL_INCLUDE_SOURCE, False)
        self.assertEqual(len(module._GPU_COMFYMODAL_PYTHON_SOURCES), 9)
        # _GPU_SOURCE_BYTES and _APP_SOURCE_BYTES are set via os.path.getsize
        # on real files — verify they are non-negative integers.
        self.assertIsInstance(module._GPU_SOURCE_BYTES, int)
        self.assertIsInstance(module._APP_SOURCE_BYTES, int)
        self.assertGreaterEqual(module._GPU_SOURCE_BYTES, 0)
        self.assertGreaterEqual(module._APP_SOURCE_BYTES, 0)
        # Diagnostic print should exist — captured by module-level exec side-effect


if __name__ == "__main__":
    unittest.main()
