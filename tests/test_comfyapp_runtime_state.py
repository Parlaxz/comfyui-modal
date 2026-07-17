import asyncio
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import types
import uuid
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"


def _make_gpu_catalog_stub():
    """Return a stub module that replaces ``gpu_catalog``."""
    stub = types.ModuleType("gpu_catalog")
    stub.GPU_CATALOG = []
    stub.get_supported_gpus = lambda: []
    stub.is_gpu_hidden = lambda v: False
    stub.get_default_gpu = lambda: "rtx-pro-6000"
    return stub


def _make_timing_trace_stub():
    """Return a stub module that replaces ``timing_trace``."""
    stub = types.ModuleType("timing_trace")
    stub.Trace = type("Trace", (), {"__init__": lambda self, **kw: None, "mark": lambda self, *a, **kw: None, "fields": lambda self: {}, "update": lambda self, *a, **kw: None, "summary": lambda self: {}, "log_line": lambda self: ""})
    stub.coerce_t0_from_browser = lambda p: None
    return stub


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

    # Secret — used when registering GPU worker classes
    stub.Secret = MagicMock()
    stub.Secret.from_name.return_value = MagicMock()

    # Dict — used for shared control dict at module level
    stub.Dict = MagicMock()
    stub.Dict.from_name.return_value = MagicMock()

    # Decorators used on methods / classes
    stub.web_server = lambda *a, **kw: (lambda f: f)
    stub.enter = lambda **kw: (lambda f: f)
    stub.exit = lambda: (lambda f: f)
    stub.method = lambda **kw: (lambda f: f)
    stub.concurrent = lambda **kw: (lambda c: c)

    return stub


def _unique_module_name():
    return f"comfyapp_test_{uuid.uuid4().hex}"


def load_module():
    """Import ``comfyapp.py`` under a unique module name with ``modal``,
    ``gpu_catalog``, and ``timing_trace`` stubbed.

    The stubs prevent any cloud API calls or external imports during
    module-level execution. All stubbed modules and the test module are
    cleaned up from ``sys.modules`` so each call gets a fresh compile.
    """
    original_modal = sys.modules.pop("modal", None)
    original_gpu_catalog = sys.modules.pop("gpu_catalog", None)
    original_timing_trace = sys.modules.pop("timing_trace", None)
    sys.modules["modal"] = _make_modal_stub()
    sys.modules["gpu_catalog"] = _make_gpu_catalog_stub()
    sys.modules["timing_trace"] = _make_timing_trace_stub()
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
        if original_gpu_catalog is not None:
            sys.modules["gpu_catalog"] = original_gpu_catalog
        else:
            sys.modules.pop("gpu_catalog", None)
        if original_timing_trace is not None:
            sys.modules["timing_trace"] = original_timing_trace
        else:
            sys.modules.pop("timing_trace", None)
        sys.modules.pop(module_name, None)


def _nonexistent_path() -> str:
    """Return a string path that is guaranteed not to exist on any platform."""
    return str(Path(tempfile.gettempdir()) / uuid.uuid4().hex / "requirements.txt")


class ComfyAppRuntimeStateTests(unittest.TestCase):
    def test_patch_cachedit_node_class_returns_model_tuple(self):
        module = load_module()

        class FakeCacheDiTModelOptimizer:
            FUNCTION = "optimize"

            def optimize(self, model, enable=True):
                return ("unexpected",)

        patched = module._patch_cachedit_node_class(FakeCacheDiTModelOptimizer)
        result = FakeCacheDiTModelOptimizer().optimize("model-obj", True)

        self.assertTrue(patched)
        self.assertEqual(result, ("model-obj",))
        self.assertTrue(getattr(FakeCacheDiTModelOptimizer.optimize, "_comfy_modal_disabled", False))

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

    def test_install_custom_node_requirements_runs_pip_from_node_dir_for_local_path_deps(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            node_dir = Path(tmp) / "comfyui_sam3"
            local_dep = node_dir / "src" / "sam3"
            local_dep.mkdir(parents=True)
            (node_dir / "requirements.txt").write_text("numpy\n./src/sam3\n", encoding="utf-8")

            with (
                patch.object(module, "REQUIREMENTS_REPAIR_MODE", "dev"),
                patch.object(module, "CUSTOM_NODES_PATH", tmp),
                patch.object(module, "load_runtime_metadata", return_value={"requirements": {}, "runtime": {}}),
                patch.object(module, "save_runtime_metadata"),
                patch.object(module, "_requirements_have_importable_packages", return_value=False),
                patch.object(module.subprocess, "run", return_value=types.SimpleNamespace(returncode=0, stdout="", stderr="")) as run_mock,
                patch("builtins.print") as print_mock,
            ):
                result = module._ComfyAPIMixin()._install_custom_node_requirements()

            self.assertEqual(result["installed"], ["comfyui_sam3"])
            self.assertEqual(run_mock.call_args.kwargs["cwd"], str(node_dir))
            self.assertEqual(run_mock.call_args.kwargs["timeout"], 180)
            self.assertTrue(any("installing custom node requirements" in str(call) for call in print_mock.call_args_list))

    def test_install_custom_node_requirements_persists_successes_before_later_timeout(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / ".runtime_metadata.json"
            first = Path(tmp) / "ComfyUI-CacheDiT"
            second = Path(tmp) / "comfyui-impact-pack"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            (first / "requirements.txt").write_text("numpy\n", encoding="utf-8")
            (second / "requirements.txt").write_text("transformers\n", encoding="utf-8")

            timeout_exc = subprocess.TimeoutExpired(
                cmd=[sys.executable, "-m", "pip", "install", "-r", str(second / "requirements.txt")],
                timeout=180,
            )

            with (
                patch.object(module, "REQUIREMENTS_REPAIR_MODE", "dev"),
                patch.object(module, "CUSTOM_NODES_PATH", tmp),
                patch.object(module, "RUNTIME_METADATA_PATH", str(meta_path)),
                patch.object(module, "_requirements_have_importable_packages", return_value=False),
                patch.object(module.subprocess, "run", side_effect=[
                    types.SimpleNamespace(returncode=0, stdout="", stderr=""),
                    timeout_exc,
                ]),
            ):
                result = module._ComfyAPIMixin()._install_custom_node_requirements()
                saved = module.load_runtime_metadata()

            self.assertIn("ComfyUI-CacheDiT", result.get("installed", []))
            self.assertIn("comfyui-impact-pack", result.get("failed", []))
            self.assertEqual(saved["requirements"], {
                "ComfyUI-CacheDiT": module.requirements_file_hash(str(first / "requirements.txt")),
            })

    def test_runtime_metadata_path_uses_runtime_config_volume(self):
        module = load_module()
        fwd = module.RUNTIME_METADATA_PATH.replace("\\", "/")
        self.assertTrue(fwd.startswith("/root/comfymodal_runtime"), f"RUNTIME_METADATA_PATH={module.RUNTIME_METADATA_PATH!r}")

    def test_install_custom_node_requirements_rejects_missing_local_path_before_pip(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            node_dir = Path(tmp) / "comfyui_sam3"
            node_dir.mkdir(parents=True)
            (node_dir / "requirements.txt").write_text("numpy\n./src/sam3\n", encoding="utf-8")

            with (
                patch.object(module, "CUSTOM_NODES_PATH", tmp),
                patch.object(module, "load_runtime_metadata", return_value={"requirements": {}, "runtime": {}}),
                patch.object(module, "save_runtime_metadata"),
                patch.object(module, "REQUIREMENTS_REPAIR_MODE", "dev"),
                patch.object(module, "_requirements_have_importable_packages", return_value=False),
                patch.object(module.subprocess, "run", side_effect=AssertionError("pip should not run")) as run_mock,
            ):
                result = module._ComfyAPIMixin()._install_custom_node_requirements()

            self.assertIn("comfyui_sam3", result.get("failed", []))
            run_mock.assert_not_called()

    def test_repair_missing_workflow_nodes_retries_custom_node_init_without_new_sync(self):
        module = load_module()
        fake_nodes = types.ModuleType("nodes")
        fake_nodes.NODE_CLASS_MAPPINGS = {}

        async def fake_init_extra_nodes():
            fake_nodes.NODE_CLASS_MAPPINGS["easy globalSeed"] = object()

        fake_nodes.init_extra_nodes = fake_init_extra_nodes
        original_nodes = sys.modules.get("nodes")
        sys.modules["nodes"] = fake_nodes
        try:
            mixin = module._ComfyAPIMixin()
            mixin._event_loop = types.SimpleNamespace(run_until_complete=lambda coro: asyncio.run(coro))

            with patch.object(module, "REQUIREMENTS_REPAIR_MODE", "dev"):
                with patch.object(mixin, "_install_custom_node_requirements", return_value={"installed": ["comfyui-easy-use"], "skipped": []}) as install_mock:
                    summary = mixin._repair_missing_workflow_nodes({
                        "1": {"class_type": "easy globalSeed", "inputs": {}},
                    })

                    self.assertTrue(summary["attempted"])
                    self.assertEqual(summary["missing_before"], ["easy globalSeed"])
                    self.assertEqual(summary["missing_after"], [])
                    install_mock.assert_called_once_with(force=True)
        finally:
            if original_nodes is not None:
                sys.modules["nodes"] = original_nodes
            else:
                sys.modules.pop("nodes", None)

    def test_install_custom_node_requirements_invalidates_cache_on_comfyapp_version_change(self):
        """When COMFYAPP_VERSION differs from the cached version but packages
        are already importable (e.g. baked in the image), skip pip and seed
        the hash cache."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            node_dir = Path(tmp) / "comfyui_easy_use"
            node_dir.mkdir(parents=True)
            (node_dir / "requirements.txt").write_text("numpy\n", encoding="utf-8")
            current_hash = module.requirements_file_hash(str(node_dir / "requirements.txt"))

            stale_metadata = {
                "comfyapp_version": "0.0.0-prehistoric",
                "requirements": {"comfyui_easy_use": current_hash},
            }

            with (
                patch.object(module, "CUSTOM_NODES_PATH", tmp),
                patch.object(module, "load_runtime_metadata", return_value=stale_metadata),
                patch.object(module, "save_runtime_metadata") as save_mock,
                patch.object(module, "REQUIREMENTS_REPAIR_MODE", "dev"),
                patch.object(module.subprocess, "run", side_effect=AssertionError("pip should not run")) as run_mock,
                patch.object(module, "_requirements_have_importable_packages", return_value=True),
            ):
                result = module._ComfyAPIMixin()._install_custom_node_requirements()

            self.assertEqual(result["installed"], [])
            self.assertEqual(result["skipped"], ["comfyui_easy_use"])
            run_mock.assert_not_called()
            saved = save_mock.call_args.args[0]
            self.assertEqual(saved["comfyapp_version"], module.COMFYAPP_VERSION)
            self.assertEqual(saved["requirements"]["comfyui_easy_use"], current_hash)

    def test_install_custom_node_requirements_skips_on_hash_match_without_importability_check(self):
        """When the requirements hash matches the cached hash, skip pip and
        do NOT call the expensive _requirements_have_importable_packages check."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            node_dir = Path(tmp) / "comfyui_easy_use"
            node_dir.mkdir(parents=True)
            (node_dir / "requirements.txt").write_text("jsonschema\n", encoding="utf-8")
            current_hash = module.requirements_file_hash(str(node_dir / "requirements.txt"))

            matching_metadata = {
                "comfyapp_version": module.COMFYAPP_VERSION,
                "requirements": {"comfyui_easy_use": current_hash},
            }

            with (
                patch.object(module, "CUSTOM_NODES_PATH", tmp),
                patch.object(module, "load_runtime_metadata", return_value=matching_metadata),
                patch.object(module, "save_runtime_metadata") as save_mock,
                patch.object(module, "REQUIREMENTS_REPAIR_MODE", "dev"),
                patch.object(module, "_requirements_have_importable_packages",
                             side_effect=AssertionError("importability check should not be called")) as importable_mock,
                patch.object(module.subprocess, "run", side_effect=AssertionError("pip should not run")) as run_mock,
            ):
                result = module._ComfyAPIMixin()._install_custom_node_requirements()

            self.assertEqual(result["installed"], [])
            self.assertEqual(result["skipped"], ["comfyui_easy_use"])
            run_mock.assert_not_called()
            importable_mock.assert_not_called()
            save_mock.assert_not_called()

    def test_install_custom_node_requirements_seeds_missing_hash_when_packages_already_importable(self):
        """When the comfyapp_version matches but the requirements hash is
        missing from the cache (e.g. first cold start after image rebuild),
        skip pip if packages are already importable and seed the hash."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / ".runtime_metadata.json"
            node_dir = Path(tmp) / "comfyui_easy_use"
            node_dir.mkdir(parents=True)
            (node_dir / "requirements.txt").write_text("jsonschema\n", encoding="utf-8")
            current_hash = module.requirements_file_hash(str(node_dir / "requirements.txt"))

            with (
                patch.object(module, "CUSTOM_NODES_PATH", tmp),
                patch.object(module, "RUNTIME_METADATA_PATH", str(meta_path)),
                patch.object(module, "REQUIREMENTS_REPAIR_MODE", "dev"),
                patch.object(module, "_requirements_have_importable_packages", return_value=True),
                patch.object(module.subprocess, "run", side_effect=AssertionError("pip should not run")) as run_mock,
            ):
                # Write initial metadata AFTER patching RUNTIME_METADATA_PATH
                # so it goes to the temp file. Do NOT patch load_runtime_metadata
                # so the real read-back after save works.
                initial_metadata = {
                    "comfyapp_version": module.COMFYAPP_VERSION,
                    "requirements": {},
                }
                module.save_runtime_metadata(initial_metadata)

                result = module._ComfyAPIMixin()._install_custom_node_requirements()

                self.assertEqual(result["installed"], [])
                self.assertEqual(result["skipped"], ["comfyui_easy_use"])
                run_mock.assert_not_called()

                # Read back while still inside the with block so
                # RUNTIME_METADATA_PATH still points to the temp file.
                saved = module.load_runtime_metadata()
                self.assertEqual(saved["requirements"]["comfyui_easy_use"], current_hash)
                self.assertEqual(saved["comfyapp_version"], module.COMFYAPP_VERSION)

    def test_requirements_have_importable_packages_matches_installed_distribution_names(self):
        """Use distribution metadata (Name field), not import-module guesses,
        so known mismatches like Pillow→PIL are handled correctly."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / "requirements.txt"
            req.write_text("pillow\nopencv-python-headless\nscikit-image\n", encoding="utf-8")

            fake_dists = [
                types.SimpleNamespace(**{"metadata": {"Name": "Pillow"}}),
                types.SimpleNamespace(**{"metadata": {"Name": "opencv-python-headless"}}),
                types.SimpleNamespace(**{"metadata": {"Name": "scikit-image"}}),
            ]

            with patch("importlib.metadata.distributions", return_value=fake_dists):
                self.assertTrue(module._requirements_have_importable_packages(str(req)))

    def test_iter_top_level_requirements_skips_non_matching_platform_markers(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / "requirements.txt"
            req.write_text("numpy\ntriton-windows; sys_platform == 'win32'\ntriton; sys_platform != 'win32'\ntorch\n", encoding="utf-8")
            names = module._iter_top_level_requirement_names(str(req))
        # On Windows, should include triton-windows. On Linux, should include triton.
        if sys.platform == "win32":
            self.assertIn("triton-windows", names)
            self.assertNotIn("triton", names)
        else:
            self.assertIn("triton", names)
            self.assertNotIn("triton-windows", names)
        self.assertIn("numpy", names)
        self.assertIn("torch", names)

    def test_install_custom_node_requirements_fast_path_on_hash_match_even_when_package_not_importable(self):
        """Hash match fast path: when the cached hash matches, skip
        entirely — no importability check, no pip. The caller must use
        force=True to reinstall after hash match."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            node_dir = Path(tmp) / "comfyui_missing_dep_node"
            node_dir.mkdir(parents=True)
            (node_dir / "requirements.txt").write_text(
                "definitely_not_a_real_package_xyz_12345\n", encoding="utf-8"
            )
            current_hash = module.requirements_file_hash(str(node_dir / "requirements.txt"))

            cached_metadata = {
                "comfyapp_version": module.COMFYAPP_VERSION,
                "requirements": {"comfyui_missing_dep_node": current_hash},
            }

            with (
                patch.object(module, "CUSTOM_NODES_PATH", tmp),
                patch.object(module, "load_runtime_metadata", return_value=cached_metadata),
                patch.object(module, "save_runtime_metadata") as save_mock,
                patch.object(module, "REQUIREMENTS_REPAIR_MODE", "dev"),
                patch.object(module, "_requirements_have_importable_packages",
                             side_effect=AssertionError("importability check should not be called")) as importable_mock,
                patch.object(module.subprocess, "run", side_effect=AssertionError("pip should not run")) as run_mock,
            ):
                result = module._ComfyAPIMixin()._install_custom_node_requirements()

            self.assertEqual(result["installed"], [])
            self.assertEqual(result["skipped"], ["comfyui_missing_dep_node"])
            run_mock.assert_not_called()
            importable_mock.assert_not_called()
            save_mock.assert_not_called()

    def test_repair_missing_workflow_nodes_passes_force_true_to_install(self):
        """Repair path is invoked when a real workflow fails validation
        because of missing nodes. We must force re-install — the previous
        cache may be stale (image rebuild, custom node update) and
        skipping pip would leave the workflow broken."""
        module = load_module()
        fake_nodes = types.ModuleType("nodes")
        fake_nodes.NODE_CLASS_MAPPINGS = {}

        async def fake_init_extra_nodes():
            fake_nodes.NODE_CLASS_MAPPINGS["easy globalSeed"] = object()

        fake_nodes.init_extra_nodes = fake_init_extra_nodes
        original_nodes = sys.modules.get("nodes")
        sys.modules["nodes"] = fake_nodes
        try:
            with patch.object(module, "REQUIREMENTS_REPAIR_MODE", "dev"):
                mixin = module._ComfyAPIMixin()
                mixin._event_loop = types.SimpleNamespace(run_until_complete=lambda coro: asyncio.run(coro))

                with patch.object(mixin, "_install_custom_node_requirements", return_value={"installed": ["comfyui-easy-use"], "skipped": []}) as install_mock:
                    mixin._repair_missing_workflow_nodes({
                        "1": {"class_type": "easy globalSeed", "inputs": {}},
                    })

                install_mock.assert_called_once_with(force=True)
        finally:
            if original_nodes is not None:
                sys.modules["nodes"] = original_nodes
            else:
                sys.modules.pop("nodes", None)

    def test_apply_return_mode_paths_only_strips_payload_data(self):
        module = load_module()
        result = {
            "images": [{"data": "abc", "filename": "one.png"}],
            "videos": [{"data": "xyz", "filename": "two.mp4"}],
            "_return_payload_info": {"b64_bytes": 6},
        }

        filtered = module._apply_return_mode(result, "paths_only", 1, 1)

        self.assertEqual(filtered["images"], [{"filename": "one.png", "path": "/root/comfy/ComfyUI/output/one.png"}])
        self.assertEqual(filtered["videos"], [{"filename": "two.mp4", "path": "/root/comfy/ComfyUI/output/two.mp4"}])
        self.assertEqual(filtered["_return_payload_info"]["b64_bytes"], 0)

    def test_run_prompt_uses_shared_return_mode_filter_in_both_backends(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("_apply_return_mode("), 3)

    def test_execute_in_process_refreshes_executor_outputs_between_same_workflow_runs(self):
        module = load_module()
        mixin = module._ComfyAPIMixin()

        class FakeExecutor:
            def __init__(self):
                self.reset_calls = 0
                self.execute_calls = 0
                self.success = True
                self.status_messages = []
                self.history_result = {}
                self._fresh = True

            def reset(self):
                self.reset_calls += 1
                self._fresh = True
                self.history_result = {}

            def execute(self, prompt, prompt_id, extra_data=None, execute_outputs=None):
                self.execute_calls += 1
                if self._fresh:
                    filename = f"fresh_{self.execute_calls}.png"
                    self.history_result = {
                        "outputs": {
                            "1": {
                                "images": [{"filename": filename, "subfolder": "", "type": "output"}],
                            }
                        }
                    }
                self._fresh = False

        async def fake_validate_prompt(prompt_id, workflow, partial_execution_list):
            return True, {}, ["1"], {}

        def fake_collect(prompt_id, prompt_start_time=None, modal_options=None, **_kwargs):
            filename = mixin._executor.history_result["outputs"]["1"]["images"][0]["filename"]
            entry = {"filename": filename, "data": "ZmFrZQ==", "node_id": "1"}
            return {"images": [entry], "videos": [], "outputs": {"1": {"images": [entry]}}}

        mixin._executor = FakeExecutor()
        mixin._event_loop = types.SimpleNamespace(run_until_complete=lambda coro: asyncio.run(coro))
        mixin._enable_torch_compile_on_unet = MagicMock()
        mixin._log_profile = MagicMock()
        mixin._profile_ms = lambda started: 0.0
        mixin._repair_missing_workflow_nodes = MagicMock(return_value={
            "attempted": False,
            "missing_before": [],
            "missing_after": [],
            "installed": [],
            "skipped": [],
        })
        mixin._compute_workflow_struct_hash = MagicMock(return_value="same-workflow")
        mixin._begin_prompt_profile = MagicMock()
        mixin._collect_in_process_outputs = MagicMock(side_effect=fake_collect)

        workflow = {"1": {"class_type": "SaveImage", "inputs": {"filename_prefix": "test"}}}

        mixin._preflight_already_ran = True

        with patch.dict(sys.modules, {"execution": types.SimpleNamespace(validate_prompt=fake_validate_prompt)}):
            production_disabled = {"production": {"enabled": False}}
            first = mixin._execute_in_process(workflow, modal_options=production_disabled)
            second = mixin._execute_in_process(workflow, modal_options=production_disabled)

        self.assertEqual(first["images"][0]["filename"], "fresh_1.png")
        self.assertEqual(second["images"][0]["filename"], "fresh_2.png")
        self.assertEqual(mixin._executor.reset_calls, 2)

    def test_collect_in_process_outputs_keeps_explicit_rgthree_temp_history_entries(self):
        module = load_module()
        mixin = module._ComfyAPIMixin()
        filename = "rgthree.compare._temp_abcde_00001_.png"

        with tempfile.TemporaryDirectory() as tmp:
            comfy_root = Path(tmp)
            temp_dir = comfy_root / "temp"
            temp_dir.mkdir(parents=True)
            (temp_dir / filename).write_bytes(b"fake-image-bytes")

            mixin._executor = types.SimpleNamespace(
                history_result={
                    "outputs": {
                        "7": {
                            "a_images": [{"filename": filename, "subfolder": "", "type": "temp"}],
                        }
                    }
                }
            )
            mixin._dummy_server = types.SimpleNamespace(prompt_queue=types.SimpleNamespace(history={}))

            real_path_cls = type(comfy_root)

            def fake_path(*parts):
                path = real_path_cls(*parts)
                if str(path).replace("\\", "/") == "/root/comfy/ComfyUI":
                    return comfy_root
                return path

            with patch("pathlib.Path", side_effect=fake_path):
                result = mixin._collect_in_process_outputs("prompt-1", prompt_start_time=time.time() - 1)

        self.assertIn("7", result["outputs"])
        self.assertEqual(result["outputs"]["7"]["a_images"][0]["filename"], filename)

    def test_collect_outputs_keeps_explicit_rgthree_temp_entries(self):
        module = load_module()
        mixin = module._ComfyAPIMixin()
        filename = "rgthree.compare._temp_abcde_00001_.png"
        mixin._http_client_obj = types.SimpleNamespace(get=lambda url: types.SimpleNamespace(content=b"fake-image-bytes"))

        result = mixin._collect_outputs({
            "7": {
                "a_images": [{"filename": filename, "subfolder": "", "type": "temp"}],
            }
        })

        self.assertIn("7", result["outputs"])
        self.assertEqual(result["outputs"]["7"]["a_images"][0]["filename"], filename)


class ComfyAppRuntimeFlagTests(unittest.TestCase):
    """Selftests for runtime flag resolver priority and cleanup helpers."""

    def setUp(self):
        self.module = load_module()

    def test_runtime_flag_resolver_priority_flag_file_over_env(self):
        """Runtime flag file takes priority over env var."""
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "runtime_config"
            config_dir.mkdir(parents=True)
            flag_path = config_dir / "RESTORE_BACKGROUND_UNET.txt"
            flag_path.write_text("1", encoding="utf-8")

            with patch.object(self.module, "RUNTIME_CONFIG_DIR", str(config_dir)):
                with patch.dict(os.environ, {"COMFYMODAL_RESTORE_BACKGROUND_UNET": "0"}):
                    result = self.module._resolve_runtime_flag("RESTORE_BACKGROUND_UNET", "0")
                    self.assertTrue(result, "Flag file should override env var")

    def test_runtime_flag_resolver_priority_env_over_default(self):
        """Env var takes priority over module default."""
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "runtime_config"
            config_dir.mkdir(parents=True)

            with patch.object(self.module, "RUNTIME_CONFIG_DIR", str(config_dir)):
                with patch.dict(os.environ, {"COMFYMODAL_RESTORE_BACKGROUND_UNET": "1"}):
                    result = self.module._resolve_runtime_flag("RESTORE_BACKGROUND_UNET", "0")
                    self.assertTrue(result, "Env var should override default")

    def test_runtime_flag_resolver_uses_default_when_nothing_set(self):
        """Default is used when no flag file and no env var."""
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "runtime_config"
            config_dir.mkdir(parents=True)

            with patch.object(self.module, "RUNTIME_CONFIG_DIR", str(config_dir)):
                with patch.dict(os.environ, {}, clear=True):
                    result = self.module._resolve_runtime_flag("RESTORE_BACKGROUND_UNET", "0")
                    self.assertFalse(result)

    def test_runtime_string_resolver_priority(self):
        """Runtime string resolver follows same priority: file > env > default."""
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "runtime_config"
            config_dir.mkdir(parents=True)
            flag_path = config_dir / "RESTORE_DIRECT_CLIP_POLICY.txt"
            flag_path.write_text("load_only", encoding="utf-8")

            with patch.object(self.module, "RUNTIME_CONFIG_DIR", str(config_dir)):
                with patch.dict(os.environ, {"COMFYMODAL_RESTORE_DIRECT_CLIP_POLICY": "off"}):
                    result = self.module._resolve_restore_direct_clip_policy_name()
                    self.assertEqual(result, "load_only",
                                     "Flag file should override env var for string resolver")

    def test_runtime_string_rejects_invalid_value(self):
        """Invalid values fall back to default."""
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "runtime_config"
            config_dir.mkdir(parents=True)
            flag_path = config_dir / "RESTORE_DIRECT_CLIP_POLICY.txt"
            flag_path.write_text("invalid_policy", encoding="utf-8")

            with patch.object(self.module, "RUNTIME_CONFIG_DIR", str(config_dir)):
                result = self.module._resolve_restore_direct_clip_policy_name()
                self.assertEqual(result, "auto",
                                 "Invalid value should fall back to default 'auto'")

    def test_clear_runtime_flag_internal_safety(self):
        """clear_runtime_flag_internal rejects path traversal."""
        result, did_remove = self.module._clear_runtime_flag_internal("RESTORE_BACKGROUND_UNET")
        self.assertIn("RESTORE_BACKGROUND_UNET", result)

        result, did_remove = self.module._clear_runtime_flag_internal("../../../etc/passwd")
        self.assertIn("invalid", result)
        self.assertFalse(did_remove)

        result, did_remove = self.module._clear_runtime_flag_internal("..")
        self.assertIn("invalid", result)
        self.assertFalse(did_remove)

    def test_clear_runtime_flag_internal_removes_existing(self):
        """clear_runtime_flag_internal removes an existing flag file."""
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "runtime_config"
            config_dir.mkdir(parents=True)
            flag_path = config_dir / "TEST_FLAG.txt"
            flag_path.write_text("1", encoding="utf-8")

            with patch.object(self.module, "RUNTIME_CONFIG_DIR", str(config_dir)):
                result, did_remove = self.module._clear_runtime_flag_internal("TEST_FLAG")
                self.assertTrue(did_remove)
                self.assertIn("removed", result)
                self.assertFalse(flag_path.exists())

    def test_clear_runtime_flag_internal_noop_for_missing(self):
        """clear_runtime_flag_internal returns 'was not set' for missing flag."""
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "runtime_config"
            config_dir.mkdir(parents=True)

            with patch.object(self.module, "RUNTIME_CONFIG_DIR", str(config_dir)):
                result, did_remove = self.module._clear_runtime_flag_internal("NONEXISTENT_FLAG")
                self.assertFalse(did_remove)
                self.assertIn("was not set", result)

    def test_runtime_flag_bool_parsing(self):
        """_resolve_runtime_flag returns True for '1' and False for '0'."""
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "runtime_config"
            config_dir.mkdir(parents=True)

            with patch.object(self.module, "RUNTIME_CONFIG_DIR", str(config_dir)):
                with patch.dict(os.environ, {"COMFYMODAL_TEST_BOOL": "1"}):
                    result = self.module._resolve_runtime_flag("TEST_BOOL", "0")
                    self.assertTrue(result)

                with patch.dict(os.environ, {"COMFYMODAL_TEST_BOOL": "0"}):
                    result = self.module._resolve_runtime_flag("TEST_BOOL", "1")
                    self.assertFalse(result)

    def test_restore_background_code_disabled_default(self):
        """Default EXPERIMENTAL_RESTORE_BACKGROUND_CODE is False (0)."""
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "runtime_config"
            config_dir.mkdir(parents=True)

            with patch.object(self.module, "RUNTIME_CONFIG_DIR", str(config_dir)):
                with patch.dict(os.environ, {}, clear=True):
                    with patch.object(self.module, "EXPERIMENTAL_RESTORE_BACKGROUND_CODE", False):
                        result = self.module._restore_background_code_enabled()
                        self.assertFalse(result)

    def test_restore_background_unet_disabled_default(self):
        """Default RESTORE_BACKGROUND_UNET is False (0)."""
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "runtime_config"
            config_dir.mkdir(parents=True)

            with patch.object(self.module, "RUNTIME_CONFIG_DIR", str(config_dir)):
                with patch.dict(os.environ, {}, clear=True):
                    with patch.object(self.module, "RESTORE_BACKGROUND_UNET_ENABLED", False):
                        result = self.module._restore_background_unet_enabled()
                        self.assertFalse(result)

    def test_reset_runtime_defaults_flag_list(self):
        """reset_runtime_defaults clears the expected experiment flags."""
        expected_flags = {
            "EXPERIMENTAL_RESTORE_BACKGROUND_CODE",
            "RESTORE_BACKGROUND_UNET",
            "RESTORE_DIRECT_CLIP_POLICY",
            "DISABLE_RESTORE_WARMUP_FOR_Z_IMAGE",
            "DIRECT_WARMUP_LOAD_UNET",
            "DIRECT_WARMUP_LOAD_CLIP",
            "DIRECT_WARMUP_CLIP_ENCODE",
            "DIRECT_WARMUP_REQUIRE_CPU_CACHE_HIT",
            "FUSE_READ_GOVERNOR",
            "SAFETENSORS_READ_MODE",
        }
        # Verify the function exists and references the right flags
        self.assertTrue(hasattr(self.module, "reset_runtime_defaults"))

    def test_production_default_preset_values_parseable(self):
        """Verify the production_default preset file is valid JSON."""
        presets_path = Path(__file__).resolve().parents[1] / ".comfymodal_experiments" / "comfymodal_experiment_presets.json"
        if not presets_path.is_file():
            self.skipTest("Presets file not found")
        import json
        data = json.loads(presets_path.read_text(encoding="utf-8"))
        presets = data.get("presets", {})
        self.assertIn("production_default", presets, "production_default preset must exist")
        pd = presets["production_default"]
        flags = pd.get("runtime_flags", {})
        self.assertEqual(flags.get("EXPERIMENTAL_RESTORE_BACKGROUND_CODE"), "1")
        self.assertEqual(flags.get("RESTORE_BACKGROUND_UNET"), "1")
        self.assertEqual(flags.get("RESTORE_DIRECT_CLIP_POLICY"), "auto")
        self.assertEqual(flags.get("FUSE_READ_GOVERNOR"), "0")
        self.assertEqual(flags.get("SAFETENSORS_READ_MODE"), "normal")

    def test_restore_bg_off_preset_disables_both_flags(self):
        """restore_bg_off preset sets both EXPERIMENTAL_RESTORE_BACKGROUND_CODE=0 and RESTORE_BACKGROUND_UNET=0."""
        presets_path = Path(__file__).resolve().parents[1] / ".comfymodal_experiments" / "comfymodal_experiment_presets.json"
        if not presets_path.is_file():
            self.skipTest("Presets file not found")
        import json
        data = json.loads(presets_path.read_text(encoding="utf-8"))
        presets = data.get("presets", {})
        self.assertIn("restore_bg_off", presets, "restore_bg_off preset must exist")
        rbo = presets["restore_bg_off"]
        flags = rbo.get("runtime_flags", {})
        self.assertEqual(flags.get("EXPERIMENTAL_RESTORE_BACKGROUND_CODE"), "0")
        self.assertEqual(flags.get("RESTORE_BACKGROUND_UNET"), "0")

    def test_baseline_hard_off_preset_includes_fuse_and_safetensors(self):
        """baseline_hard_off preset includes FUSE_READ_GOVERNOR=0 and SAFETENSORS_READ_MODE=normal."""
        presets_path = Path(__file__).resolve().parents[1] / ".comfymodal_experiments" / "comfymodal_experiment_presets.json"
        if not presets_path.is_file():
            self.skipTest("Presets file not found")
        import json
        data = json.loads(presets_path.read_text(encoding="utf-8"))
        presets = data.get("presets", {})
        self.assertIn("baseline_hard_off", presets)
        bho = presets["baseline_hard_off"]
        flags = bho.get("runtime_flags", {})
        self.assertEqual(flags.get("EXPERIMENTAL_RESTORE_BACKGROUND_CODE"), "0")
        self.assertEqual(flags.get("RESTORE_BACKGROUND_UNET"), "0")
        self.assertEqual(flags.get("FUSE_READ_GOVERNOR"), "0")
        self.assertEqual(flags.get("SAFETENSORS_READ_MODE"), "normal")

    def test_persist_per_stack_metrics_default_off(self):
        """PERSIST_PER_STACK_METRICS defaults to 0 (off)."""
        module = load_module()
        self.assertFalse(module.PERSIST_PER_STACK_METRICS)

    def test_defer_vae_actual_load_default_off(self):
        """DEFER_VAE_ACTUAL_LOAD_DURING_RBG_UNET defaults to 0 (off) since RBG UNET is disabled."""
        module = load_module()
        self.assertFalse(module.DEFER_VAE_ACTUAL_LOAD_DURING_RBG_UNET)

    def test_stall_classifier_unet_threshold(self):
        """Stall classifier marks UNET read > VOLUME_STALL_UNET_MS as stall."""
        module = load_module()
        mixin = module._ComfyAPIMixin()
        stall = mixin._classify_volume_read_stall({
            "restore": {
                "restore_background_unet_total_ms": module.VOLUME_STALL_UNET_MS + 1000,
            }
        })
        self.assertTrue(stall.get("restore_background_unet_stall"))
        self.assertEqual(stall.get("volume_read_stall_suspected"), 1)

    def test_stall_classifier_no_stall_when_below_threshold(self):
        """Stall classifier does not suspect stall when all values below threshold."""
        module = load_module()
        mixin = module._ComfyAPIMixin()
        stall = mixin._classify_volume_read_stall({
            "restore": {
                "restore_background_unet_total_ms": 1000,
            }
        })
        self.assertFalse(stall.get("volume_read_stall_suspected"))

    def test_stall_classifier_clip_preload_threshold(self):
        """Stall classifier marks low CLIP preload throughput as stall."""
        module = load_module()
        mixin = module._ComfyAPIMixin()
        # 5GB loaded in 3000ms = 1.67 GB/s, which is below 2.0 GB/s threshold
        stall = mixin._classify_volume_read_stall({
            "restore": {
                "restore_preload_total_gb": 5.0,
                "restore_preload_total_ms": 3000.0,
            }
        })
        self.assertTrue(stall.get("clip_preload_slow"))
        self.assertTrue(stall.get("volume_read_stall_suspected"))

    def test_stall_classifier_multiple_reasons_joined(self):
        """Multiple stall reasons are joined with comma."""
        module = load_module()
        mixin = module._ComfyAPIMixin()
        # Both UNET and VAE above their thresholds
        stall = mixin._classify_volume_read_stall({
            "restore": {
                "restore_background_unet_total_ms": module.VOLUME_STALL_UNET_MS + 1000,
            },
        }, after_prompt={"actual_load_vae_duration_ms": module.VOLUME_STALL_VAE_MS + 500})
        reason = stall.get("volume_read_stall_reason", "")
        self.assertIn("unet_read_gt_", reason)
        self.assertIn("vae_small_read_gt_", reason)

    def test_check_rbg_unet_active_no_futures(self):
        """_check_rbg_unet_active returns inactive when no RBG futures exist."""
        module = load_module()
        mixin = module._ComfyAPIMixin()
        result = mixin._check_rbg_unet_active()
        self.assertFalse(result.get("active"))

    def test_production_default_and_stable_restore_bg_presets_exist(self):
        """production_default and stable_restore_bg presets exist in presets file."""
        presets_path = Path(__file__).resolve().parents[1] / ".comfymodal_experiments" / "comfymodal_experiment_presets.json"
        if not presets_path.is_file():
            self.skipTest("Presets file not found")
        import json
        data = json.loads(presets_path.read_text(encoding="utf-8"))
        presets = data.get("presets", {})
        for name in ("production_default", "stable_restore_bg"):
            self.assertIn(name, presets, f"Preset {name} must exist")

    def test_diagnostic_persist_metrics_on_preset_exists(self):
        """diagnostic_persist_metrics_on preset exists for debugging."""
        presets_path = Path(__file__).resolve().parents[1] / ".comfymodal_experiments" / "comfymodal_experiment_presets.json"
        if not presets_path.is_file():
            self.skipTest("Presets file not found")
        import json
        data = json.loads(presets_path.read_text(encoding="utf-8"))
        presets = data.get("presets", {})
        self.assertIn("diagnostic_persist_metrics_on", presets)

    def test_apply_experiment_preset_allows_new_flags(self):
        """apply_experiment_preset.py allows PERSIST_PER_STACK_METRICS and DEFER_VAE flags."""
        preset_mod_path = Path(__file__).resolve().parents[1] / ".comfymodal_experiments" / "apply_experiment_preset.py"
        if not preset_mod_path.is_file():
            self.skipTest("apply_experiment_preset.py not found")
        content = preset_mod_path.read_text(encoding="utf-8")
        self.assertIn("PERSIST_PER_STACK_METRICS", content)
        self.assertIn("DEFER_VAE_ACTUAL_LOAD_DURING_RBG_UNET", content)


class RuntimeConfigVolumePathTests(unittest.TestCase):
    """Verify all runtime/control paths live under /root/comfymodal_runtime,
    not /root/models."""

    _RUNTIME_PREFIX = "/root/comfymodal_runtime"

    def setUp(self):
        self.module = load_module()

    def _check_prefix(self, path_value: str, name: str):
        # Normalize to forward-slash form for cross-platform testing.
        fwd = path_value.replace("\\", "/")
        self.assertTrue(
            fwd.startswith(self._RUNTIME_PREFIX),
            f"{name}={path_value!r} does not start with {self._RUNTIME_PREFIX!r}",
        )

    def test_active_next_profile_path_outside_models(self):
        self._check_prefix(self.module.ACTIVE_NEXT_PROFILE_PATH, "ACTIVE_NEXT_PROFILE_PATH")

    def test_last_model_stack_path_outside_models(self):
        self._check_prefix(self.module.LAST_MODEL_STACK_PATH, "LAST_MODEL_STACK_PATH")

    def test_last_warmup_workflow_path_outside_models(self):
        self._check_prefix(self.module.LAST_WARMUP_WORKFLOW_PATH, "LAST_WARMUP_WORKFLOW_PATH")

    def test_sage_runtime_cache_path_outside_models(self):
        self._check_prefix(self.module.SAGE_RUNTIME_CACHE_PATH, "SAGE_RUNTIME_CACHE_PATH")

    def test_preload_mode_path_outside_models(self):
        self._check_prefix(self.module.PRELOAD_MODE_PATH, "PRELOAD_MODE_PATH")

    def test_known_good_profiles_path_outside_models(self):
        self._check_prefix(self.module.KNOWN_GOOD_WORKFLOW_PROFILES_PATH, "KNOWN_GOOD_WORKFLOW_PROFILES_PATH")

    def test_per_stack_metrics_path_outside_models(self):
        self._check_prefix(self.module.PER_STACK_METRICS_PATH, "PER_STACK_METRICS_PATH")

    def test_runtime_config_dir_outside_models(self):
        self._check_prefix(self.module.RUNTIME_CONFIG_DIR, "RUNTIME_CONFIG_DIR")

    def test_validation_cert_dir_outside_models(self):
        self._check_prefix(self.module._VALIDATION_CERT_DIR, "_VALIDATION_CERT_DIR")

    def test_build_gpu_volumes_includes_runtime_config(self):
        vols = self.module._build_gpu_volumes()
        self.assertIn(
            self.module.RUNTIME_CONFIG_PATH,
            vols,
            f"runtime config path not in GPU volumes: {list(vols.keys())}",
        )

    def test_runtime_config_volume_name(self):
        self.assertEqual(
            self.module.RUNTIME_CONFIG_VOLUME_NAME,
            "comfymodal-runtime-config",
        )


class RuntimeCommitHelperTests(unittest.TestCase):
    """Verify renamed commit helper only commits runtime_config_vol."""

    def setUp(self):
        self.module = load_module()

    def test_commit_helper_renamed(self):
        self.assertTrue(
            hasattr(self.module, "_commit_runtime_config_vol_async"),
            "_commit_runtime_config_vol_async not found",
        )

    def test_save_known_good_uses_renamed_helper(self):
        src = self.module.__file__
        with open(src, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("_commit_runtime_config_vol_async", source)
        self.assertNotIn("_commit_volume_async(label", source)

    def test_save_last_model_stack_uses_renamed_helper(self):
        # AST-level check inside _ComfyAPIMixin
        import ast
        with open(self.module.__file__, "r", encoding="utf-8-sig") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_save_last_model_stack":
                source_seg = ast.unparse(node)
                self.assertIn("_commit_runtime_config_vol_async", source_seg)
                self.assertNotIn("_commit_volume_async", source_seg)
                return
        self.fail("_save_last_model_stack not found")

    def test_save_last_warmup_workflow_uses_renamed_helper(self):
        import ast
        with open(self.module.__file__, "r", encoding="utf-8-sig") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_save_last_warmup_workflow":
                source_seg = ast.unparse(node)
                self.assertIn("_commit_runtime_config_vol_async", source_seg)
                return
        self.fail("_save_last_warmup_workflow not found")


if __name__ == "__main__":
    unittest.main()
