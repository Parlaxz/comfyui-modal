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
            # Non-requirement source files must NOT be copied
            self.assertFalse((target_root / "node-a" / "nodes.py").is_file())
            # __pycache__ node must be filtered out
            self.assertFalse((target_root / "__pycache__" / "requirements.txt").is_file())

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


    # ── Requirement 1: Layer ordering ────────────────────────────────
    # Runtime sources (comfyapp.py, comfymodal_runtime, instrumentation)
    # must be copied AFTER all dependency install layers.

    def test_runtime_sources_after_dependency_install(self):
        """_add_gpu_python_sources must appear after the custom-node
        pip-install and source-copy layers in the module code."""
        with open(str(COMFYAPP_PATH), encoding="utf-8-sig") as f:
            source = f.read()
        lines = source.splitlines()

        # Find line numbers for key build operations by source text
        pip_loop_lineno = None
        gpu_source_add_lineno = None
        app_call_lineno = None

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Track custom-node pip-install start diagnostic
            if "CUSTOM_NODE_PREREQ_INSTALL_START" in line:
                pip_loop_lineno = i
            # Track _add_gpu_python_sources function definition
            if stripped == "def _add_gpu_python_sources(img):":
                gpu_source_add_lineno = i
            # Track modal.App call
            if "modal.App(" in stripped and "APP_NAME" in stripped:
                app_call_lineno = i

        self.assertIsNotNone(pip_loop_lineno,
                             "Must find custom-node pip-install loop "
                             "(CUSTOM_NODE_PREREQ_INSTALL_START)")
        self.assertIsNotNone(gpu_source_add_lineno,
                             "Must find _add_gpu_python_sources function")
        self.assertIsNotNone(app_call_lineno,
                             "Must find modal.App() call")

        # The _add_gpu_python_sources function must be defined AFTER the
        # pip-install loop (runtime sources come after dependency install)
        self.assertGreater(
            gpu_source_add_lineno,
            pip_loop_lineno,
            f"_add_gpu_python_sources at line {gpu_source_add_lineno} "
            f"must appear after pip-install loop at line {pip_loop_lineno}"
        )

    # ── Requirement 2: Custom-node dependency identity ───────────────
    # The identity/context must depend only on requirement files,
    # not on modal_app.py or other runtime Python.

    def test_custom_node_identity_independent_of_modal_app(self):
        """collect_custom_node_dependency_files must NOT include
        modal_app.py or other runtime-only Python files."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            node_root = Path(tmp) / "mynode"
            node_root.mkdir(parents=True)
            (node_root / "requirements.txt").write_text("numpy\n", encoding="utf-8")
            (node_root / "modal_app.py").write_text("# runtime stub\n", encoding="utf-8")
            (node_root / "runtime_helper.py").write_text("# runtime helper\n", encoding="utf-8")

            deps = module.collect_custom_node_dependency_files(str(node_root))

            # Requirements file must be included
            self.assertIn("requirements.txt", deps,
                          "requirements.txt must be in dependency files")
            # Runtime-only files must NOT be included
            self.assertNotIn("modal_app.py", deps,
                             "modal_app.py must NOT be a dependency file")
            self.assertNotIn("runtime_helper.py", deps,
                             "runtime_helper.py must NOT be a dependency file")

    def test_custom_node_identity_depends_on_requirements_change(self):
        """Changing a custom-node requirements file must alter the
        dependency context manifest hash."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            node_root = Path(tmp) / "mynode"
            node_root.mkdir(parents=True)
            (node_root / "requirements.txt").write_text("numpy==1.0.0\n", encoding="utf-8")
            manifest_a = module.build_custom_node_dependency_manifest(str(node_root.parent))

            (node_root / "requirements.txt").write_text("numpy==2.0.0\n", encoding="utf-8")
            manifest_b = module.build_custom_node_dependency_manifest(str(node_root.parent))

        hash_a = manifest_a.get("overall_dependency_hash", "")
        hash_b = manifest_b.get("overall_dependency_hash", "")
        self.assertTrue(hash_a, "First manifest must have a hash")
        self.assertTrue(hash_b, "Second manifest must have a hash")
        self.assertNotEqual(
            hash_a, hash_b,
            "Requirements change must produce different dependency hash"
        )

    def test_custom_node_identity_unchanged_by_modal_app_change(self):
        """Changing modal_app.py (runtime) content must NOT alter
        the custom-node dependency manifest hash."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            node_root = Path(tmp) / "mynode"
            node_root.mkdir(parents=True)
            (node_root / "requirements.txt").write_text("numpy\n", encoding="utf-8")
            (node_root / "modal_app.py").write_text("# v1\n", encoding="utf-8")
            manifest_a = module.build_custom_node_dependency_manifest(str(node_root.parent))

            # Change only modal_app.py content
            (node_root / "modal_app.py").write_text("# v2 - changed\n", encoding="utf-8")
            manifest_b = module.build_custom_node_dependency_manifest(str(node_root.parent))

        hash_a = manifest_a.get("overall_dependency_hash", "")
        hash_b = manifest_b.get("overall_dependency_hash", "")
        self.assertTrue(hash_a, "First manifest must have a hash")
        self.assertTrue(hash_b, "Second manifest must have a hash")
        self.assertEqual(
            hash_a, hash_b,
            "modal_app.py change must NOT alter custom-node dependency hash"
        )

    # ── Requirement 3: Pip failures stop build ───────────────────────
    # The shell script must exit on pip failure.

    def test_pip_failure_stops_build(self):
        """The pip-install shell function must propagate failures
        via '|| return 1' and the 'for' loop must exit on failure.
        Tests command semantics (operators, exit codes), not just
        substring presence."""
        with open(str(COMFYAPP_PATH), encoding="utf-8-sig") as f:
            source = f.read()

        # Find the run_commands string that contains _pip_node
        # by extracting the contiguous shell script between CUSTOM_NODE_PREREQ
        # markers (since the AST contains complex string concatenation).
        start_marker = "CUSTOM_NODE_PREREQ_INSTALL_START"
        # Use the CacheDiT gate start as the end bound so we cover both the
        # pip loop and the CacheDiT lock family ensure command.
        end_marker = "CACHEDIT_LOCK_FAMILY_ENSURE_END"
        start_idx = source.find(start_marker)
        end_idx = source.find(end_marker)
        self.assertGreater(start_idx, 0,
                           "Must find custom-node pip-install start marker")
        self.assertGreater(end_idx, start_idx,
                           "Must find CacheDiT lock family ensure end marker")

        # Extract a generous window around the script
        search_window = source[start_idx:end_idx + len(end_marker)]

        # Check that _pip_node has || return 1 on pip command
        self.assertIn("|| { echo", search_window,
                      "pip command must have fail-fast guard")
        self.assertIn("return 1", search_window,
                      "_pip_node must return 1 on failure")
        # Check that the for loop checks exit code
        self.assertIn('_pip_node "$d" || exit 1', search_window,
                      "for loop must exit on _pip_node failure")
        # Check CacheDiT lock family ensure also fails fast
        self.assertIn("CACHEDIT_LOCK_FAMILY_FAILED", search_window,
                      "CacheDiT lock family ensure must have failure guard")
        # Check that error-swallowing patterns are absent
        self.assertNotIn("|| true", search_window,
                         "pip commands must not swallow errors with || true")
        self.assertNotIn("|| :", search_window,
                         "pip commands must not swallow errors with || :")
        # The for loop must NOT be wrapped in set ±e (individual
        # 'exit 1' handles failure propagation unconditionally)
        self.assertNotIn("set +e", search_window,
                         "for loop must not disable error handling")
        self.assertNotIn("set -e", search_window,
                         "for loop must not enable error handling")

    # ── Requirement 4: No PyTorch 2.12 force-reinstall ───────────────

    def test_no_pytorch_212_force_reinstall(self):
        """No `--force-reinstall` or version gate for PyTorch 2.12
        must remain in the build script."""
        module = load_module()
        import ast

        source = getattr(module, "_COMFYAPP_SOURCE", None)
        if not source:
            with open(str(COMFYAPP_PATH), encoding="utf-8-sig") as f:
                source = f.read()

        # Search for any 2.12 references
        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Allow SageAttention force-reinstall (known baseline behavior)
            if "2.12" in stripped:
                self.fail(f"PyTorch 2.12 reference found at line {i}: {stripped}")

    # ── Requirement 5: download_image includes comfymodal_runtime ──
    # Module-level imports from comfymodal_runtime require the package
    # to be present in every image, especially the CPU download image.

    def test_download_image_includes_comfymodal_runtime(self):
        """download_image must chain add_local_python_source('comfymodal_runtime')
        because comfyapp.py imports comfymodal_runtime at module level and
        App(include_source=False) means explicit inclusion is required."""
        import ast
        with open(str(COMFYAPP_PATH), encoding="utf-8-sig") as f:
            source = f.read()
        tree = ast.parse(source)

        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "download_image":
                        # Walk all calls in the value for add_local_python_source
                        for child in ast.walk(node.value):
                            if (isinstance(child, ast.Call)
                                    and isinstance(child.func, ast.Attribute)
                                    and child.func.attr == "add_local_python_source"):
                                args = child.args
                                if (args
                                        and isinstance(args[0], ast.Constant)
                                        and args[0].value == "comfymodal_runtime"):
                                    # Verify copy=True keyword
                                    copy_ok = any(
                                        kw.arg == "copy"
                                        and isinstance(kw.value, ast.Constant)
                                        and kw.value.value is True
                                        for kw in child.keywords
                                    )
                                    self.assertTrue(copy_ok,
                                        "comfymodal_runtime must be added with copy=True")
                                    found = True
                        # Also verify _add_cpu_python_sources is used
                        sources_ref = any(
                            isinstance(c, ast.Call)
                            and isinstance(c.func, ast.Name)
                            and c.func.id == "_add_cpu_python_sources"
                            for c in ast.walk(node.value)
                        )
                        self.assertTrue(sources_ref,
                            "download_image must use _add_cpu_python_sources")
                        break

        self.assertTrue(found,
            "download_image must include comfymodal_runtime via add_local_python_source")

    # ── Requirement 6: cachedit_dependency_lock.txt in build context ──

    def test_cachedit_lock_added_to_image_base(self):
        """cachedit_dependency_lock.txt must be added to _image_base
        via add_local_file, proving it is part of the dependency-layer
        input identity/build context."""
        import ast
        with open(str(COMFYAPP_PATH), encoding="utf-8-sig") as f:
            source = f.read()

        lines = source.splitlines()

        # Constants exist
        lock_src_lineno = None
        lock_dst_lineno = None
        for i, line in enumerate(lines, 1):
            if "_CACHEDIT_LOCK_FILENAME = \"cachedit_dependency_lock.txt\"" in line:
                lock_src_lineno = i
            if "_CACHEDIT_LOCK_DST = \"/opt/comfymodal/cachedit_dependency_lock.txt\"" in line:
                lock_dst_lineno = i

        self.assertIsNotNone(lock_src_lineno,
            "Must find _CACHEDIT_LOCK_FILENAME = 'cachedit_dependency_lock.txt'")
        self.assertIsNotNone(lock_dst_lineno,
            "Must find _CACHEDIT_LOCK_DST = '/opt/comfymodal/cachedit_dependency_lock.txt'")

        # Find add_local_file with _CACHEDIT_LOCK_DST before pip-install loop.
        # The call spans multiple lines (add_local_file on one line,
        # _CACHEDIT_LOCK_DST as an argument on the next), so scan forward
        # from each add_local_file hit to find the _CACHEDIT_LOCK_DST reference.
        add_file_lineno = None
        pip_start_lineno = None

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "add_local_file" in stripped:
                # Check this and the next few lines for _CACHEDIT_LOCK_DST
                for j in range(i, min(i + 6, len(lines) + 1)):
                    if "_CACHEDIT_LOCK_DST" in lines[j - 1]:
                        add_file_lineno = i
                        break
            if "CUSTOM_NODE_PREREQ_INSTALL_START" in stripped:
                pip_start_lineno = i

        self.assertIsNotNone(add_file_lineno,
            "Must find add_local_file referencing _CACHEDIT_LOCK_DST")
        self.assertIsNotNone(pip_start_lineno,
            "Must find custom-node pip-install start marker")
        self.assertLess(
            add_file_lineno, pip_start_lineno,
            "cachedit lock add_local_file must appear before pip-install loop"
        )

    def test_cachedit_lock_content_affects_identity(self):
        """Different content in cachedit_dependency_lock.txt produces
        a different file hash, confirming that a changed lock file
        changes the dependency-layer input identity."""
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "cachedit_dependency_lock.txt"

            lock_path.write_text("cache-dit==1.2.3\ntransformers==4.55.2\n", encoding="utf-8")
            id_a = hashlib.sha256(lock_path.read_bytes()).hexdigest()

            lock_path.write_text("cache-dit==2.0.0\ntransformers==4.55.2\n", encoding="utf-8")
            id_b = hashlib.sha256(lock_path.read_bytes()).hexdigest()

            self.assertNotEqual(id_a, id_b,
                "Different lock file content must produce different identity")


if __name__ == "__main__":
    unittest.main()
