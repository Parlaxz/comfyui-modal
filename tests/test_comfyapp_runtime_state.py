import asyncio
import importlib.util
import os
import subprocess
import sys
import tempfile
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
                patch.object(module, "CUSTOM_NODES_PATH", tmp),
                patch.object(module, "RUNTIME_METADATA_PATH", str(meta_path)),
                patch.object(module.subprocess, "run", side_effect=[
                    types.SimpleNamespace(returncode=0, stdout="", stderr=""),
                    timeout_exc,
                ]),
            ):
                with self.assertRaises(RuntimeError) as exc:
                    module._ComfyAPIMixin()._install_custom_node_requirements()
                saved = module.load_runtime_metadata()

            self.assertIn("timed out after 180s", str(exc.exception))
            self.assertEqual(saved["requirements"], {
                "ComfyUI-CacheDiT": module.requirements_file_hash(str(first / "requirements.txt")),
            })

    def test_runtime_metadata_path_uses_models_volume(self):
        module = load_module()
        self.assertTrue(module.RUNTIME_METADATA_PATH.startswith(module.MODELS_PATH + "/"))

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
                patch.object(module.subprocess, "run", side_effect=AssertionError("pip should not run")) as run_mock,
            ):
                with self.assertRaises(RuntimeError) as exc:
                    module._ComfyAPIMixin()._install_custom_node_requirements()

            self.assertIn("Missing local requirement path", str(exc.exception))
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


if __name__ == "__main__":
    unittest.main()
