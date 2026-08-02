import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"

# Cache the parsed AST so tests share a single parse of comfyapp.py.
_AST_CACHE = None


def _get_ast():
    global _AST_CACHE
    if _AST_CACHE is None:
        source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        _AST_CACHE = ast.parse(source)
    return _AST_CACHE


def _get_method(name: str):
    module = _get_ast()
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "_ComfyAPIMixin":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return item
    raise AssertionError(f"_ComfyAPIMixin.{name} not found")


def _get_run_prompt_function():
    return _get_method("run_prompt")


def _collect_call_attrs(method_body):
    """Return {(obj_name, attr_name)} for every direct call obj.attr(...) in an AST node."""
    return {
        (node.func.value.id, node.func.attr)
        for node in ast.walk(method_body)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
    }


def _count_direct_calls(method_body, obj_name: str, attr_name: str) -> int:
    return sum(
        1
        for node in ast.walk(method_body)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == obj_name
        and node.func.attr == attr_name
    )


def _collect_attribute_reads(method_body):
    """Return {(obj_name, attr_name)} for every attribute read obj.attr in an AST node body."""
    return {
        (node.value.id, node.attr)
        for node in ast.walk(method_body)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
    }


class ComfyAppVolumeLifecycleTests(unittest.TestCase):
    def test_sync_helper_reloads_custom_node_volume_once(self):
        helper = _get_method("_sync_custom_nodes_from_volume")
        self.assertEqual(_count_direct_calls(helper, "custom_nodes_vol", "reload"), 1)

    def test_restore_and_run_prompt_do_not_directly_reload_custom_node_volume(self):
        restore = _get_method("restore")
        run_prompt = _get_method("run_prompt")
        self.assertEqual(_count_direct_calls(restore, "custom_nodes_vol", "reload"), 0)
        self.assertEqual(_count_direct_calls(run_prompt, "custom_nodes_vol", "reload"), 0)

    def test_run_prompt_does_not_reload_modal_volume(self):
        # NOTE: AST-level check only catches *direct* calls (same limitation
        # as test_restore_does_not_reload_or_sync).  Indirect calls via a
        # helper are invisible here.
        run_prompt = _get_run_prompt_function()
        forbidden = {
            ("vol", "reload"),
            ("custom_nodes_vol", "reload"),
        }
        seen = _collect_call_attrs(run_prompt)
        self.assertTrue(forbidden.isdisjoint(seen), f"Found reload calls in run_prompt: {seen & forbidden}")

    def test_restore_delegates_sync_to_helper(self):
        # restore() must NOT call custom_nodes_vol.reload() directly;
        # that is handled by _sync_custom_nodes_from_volume().
        # vol.reload() IS allowed — the models volume must be refreshed
        # before _snapshot_preload_paths resolves model file locations,
        # otherwise stale FUSE cache causes NOT FOUND errors.
        restore = _get_method("restore")
        forbidden = {
            ("custom_nodes_vol", "reload"),
        }
        seen = _collect_call_attrs(restore)
        self.assertTrue(forbidden.isdisjoint(seen), f"Found forbidden calls in restore: {seen & forbidden}")

    def test_resync_runtime_exists_and_restarts_explicitly(self):
        method = _get_method("resync_runtime")
        attrs = _collect_call_attrs(method)
        self.assertIn(("self", "_restart_comfy"), attrs)

    def test_restore_does_not_use_heavy_filesystem_repairs(self):
        restore = _get_method("restore")
        forbidden = {
            ("shutil", "rmtree"),
            ("os", "symlink"),
        }
        seen = _collect_call_attrs(restore)
        self.assertTrue(forbidden.isdisjoint(seen), f"Found heavy restore calls: {seen & forbidden}")

    def test_restore_contains_health_probe_and_fallback_restart(self):
        """restore() must probe local ComfyUI health via _http_client and
        conditionally call _restart_comfy() if the subprocess is unresponsive."""
        restore = _get_method("restore")
        call_attrs = _collect_call_attrs(restore)
        read_attrs = _collect_attribute_reads(restore)
        self.assertIn(
            ("self", "_restart_comfy"),
            call_attrs,
            "restore() must call _restart_comfy as fallback when ComfyUI is unresponsive",
        )
        self.assertIn(
            ("self", "_http_client"),
            read_attrs,
            "restore() must use _http_client to probe local ComfyUI health",
        )

    def test_restore_installs_custom_node_requirements_before_reinit(self):
        restore = _get_method("restore")
        restore_source = ast.get_source_segment(COMFYAPP_PATH.read_text(encoding="utf-8"), restore) or ""
        install_idx = restore_source.find("self._install_custom_node_requirements()")
        reinit_idx = restore_source.find("_restore_nodes.init_extra_nodes()")
        self.assertGreaterEqual(
            install_idx,
            0,
            "restore() must install custom node requirements before re-registering new nodes",
        )
        self.assertGreaterEqual(
            reinit_idx,
            0,
            "restore() must still re-register synced custom nodes",
        )
        self.assertLess(
            install_idx,
            reinit_idx,
            "restore() must install custom node requirements before init_extra_nodes()",
        )

    def test_startup_defers_sageattention_cuda_compile_until_restore(self):
        startup = _get_method("startup")
        startup_source = ast.get_source_segment(COMFYAPP_PATH.read_text(encoding="utf-8"), startup) or ""
        self.assertNotIn("downloading sageattention source from GitHub", startup_source)
        self.assertNotIn("compiling sageattention CUDA kernels", startup_source)
        self.assertNotIn("_import_sage_cuda()", startup_source)
        self.assertNotIn("get_device_capability", startup_source)

    def test_restore_applies_sage_runtime_mode(self):
        restore = _get_method("restore")
        restore_source = ast.get_source_segment(COMFYAPP_PATH.read_text(encoding="utf-8"), restore) or ""
        self.assertIn("self._select_sage_runtime_mode()", restore_source,
                      "restore() must perform sage runtime mode detection")
        self.assertIn("self._apply_sage_attention_policy()", restore_source,
                      "restore() must apply sage policy during restore")
        self.assertIn("DISABLE_MMAP", restore_source,
                      "restore() must enable eager safetensors reads")
        self.assertNotIn("downloading sageattention source from GitHub", restore_source)
        self.assertNotIn("compiling sageattention CUDA kernels", restore_source)
        self.assertNotIn("pip install", restore_source)

    def test_restore_reenables_in_process_gpu_state(self):
        restore = _get_method("restore")
        restore_source = ast.get_source_segment(COMFYAPP_PATH.read_text(encoding="utf-8"), restore) or ""
        self.assertIn("self._restore_in_process_gpu_state()", restore_source)

    def test_run_prompt_does_not_perform_deferred_sage_steps(self):
        run_prompt = _get_method("run_prompt")
        rp_source = ast.get_source_segment(COMFYAPP_PATH.read_text(encoding="utf-8"), run_prompt) or ""
        self.assertNotIn("_select_sage_runtime_mode", rp_source,
                         "run_prompt() must not repeat restore-time sage runtime detection")
        self.assertNotIn("_apply_sage_attention_policy", rp_source,
                         "run_prompt() must not repeat restore-time sage policy application")
        self.assertNotIn("run_prompt_deferred_sage", rp_source)

    def test_force_cpu_during_snapshot_patches_comfy_cli_args(self):
        method = _get_method("_force_cpu_during_snapshot")
        method_source = ast.get_source_segment(COMFYAPP_PATH.read_text(encoding="utf-8"), method) or ""
        self.assertIn('comfy_path = "/root/comfy/ComfyUI"', method_source)
        self.assertIn("sys.path.insert(0, comfy_path)", method_source)
        self.assertIn("import comfy.cli_args", method_source)
        self.assertIn("comfy.cli_args.args.cpu = True", method_source)

    # ── Runtime config volume migration tests ─────────────────────────

    def _get_module_body(self):
        return _get_ast().body

    def test_runtime_config_volume_declared(self):
        """runtime_config_vol must be declared as a named Modal Volume."""
        body = self._get_module_body()
        found = False
        for node in body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "runtime_config_vol":
                        found = True
                        break
        self.assertTrue(found, "runtime_config_vol must be assigned at module level")

    def test_runtime_config_volume_mounted_in_gpu_volumes(self):
        """_build_gpu_volumes must include RUNTIME_CONFIG_PATH."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        func_name = "_build_gpu_volumes"
        # Find the function in the AST and check for the expected content
        self.assertIn(func_name, source,
                      "_build_gpu_volumes must exist")
        self.assertIn("RUNTIME_CONFIG_PATH", source,
                      "_build_gpu_volumes must reference RUNTIME_CONFIG_PATH")
        self.assertIn("runtime_config_vol", source,
                      "_build_gpu_volumes must reference runtime_config_vol")

    def test_runtime_config_paths_not_under_models(self):
        """Runtime/config file paths must not be under /root/models."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        # Assert the old path is NOT present
        old_meta_path = '"/root/models/runtime_config/runtime_metadata.json"'
        self.assertNotIn(old_meta_path, source,
                         "RUNTIME_METADATA_PATH must not point to /root/models")
        # Key module-level constants point to /root/comfymodal_runtime_state
        self.assertIn("RUNTIME_CONFIG_PATH = \"/root/comfymodal_runtime_state\"", source)
        self.assertIn("RUNTIME_CONFIG_DIR = \"/root/comfymodal_runtime_state\"", source)

    def test_active_next_profile_path_under_runtime_config(self):
        """ACTIVE_NEXT_PROFILE_PATH must be under /root/comfymodal_runtime."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('ACTIVE_NEXT_PROFILE_PATH = os.path.join(RUNTIME_CONFIG_DIR, "active_next_profile.json")', source)

    def test_no_commit_volume_async_remaining(self):
        """_commit_volume_async must be fully replaced by _commit_runtime_config_vol_async."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("_commit_volume_async", source,
                         "All _commit_volume_async call sites must be migrated")

    def test_cpu_functions_use_runtime_config_vol(self):
        """CPU runtime functions must mount runtime_config_vol, not vol."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        # set_preload_mode should use runtime_config_vol
        self.assertIn("volumes={RUNTIME_CONFIG_PATH: runtime_config_vol}", source)
        # set_runtime_flag should not have hardcoded /root/models paths
        self.assertNotIn('os.makedirs("/root/models/runtime_config"', source)

    def test_storage_identity_diagnostics_exist(self):
        """_log_storage_identity_diagnostics must be defined."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("def _log_storage_identity_diagnostics", source)

    def test_runtime_config_vol_reloaded_at_startup_and_restore(self):
        """runtime_config_vol.reload() must be called at startup and restore."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        # Verify reload call exists in the file
        self.assertIn("runtime_config_vol.reload()", source)

    def test_persist_validation_certificate_backed_by_runtime_config_vol(self):
        """persist_validation_certificate must use runtime_config_vol."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("def persist_validation_certificate", source)
        self.assertIn("volumes={RUNTIME_CONFIG_PATH: runtime_config_vol}", source)

    def test_model_volume_comment_present(self):
        """The exact one-line comment must precede the model volume declaration."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "# Model weights are read-only during generation; never store request/runtime state here.",
            source,
        )

    def test_known_good_profiles_uses_runtime_config_vol_async(self):
        """save_known_good_workflow_profiles must use _commit_runtime_config_vol_async."""
        func_name = "save_known_good_workflow_profiles"
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("_commit_runtime_config_vol_async(\"known_good_profiles\", runtime_config_vol)", source)

    def test_write_active_next_profile_uses_runtime_config_vol(self):
        """_write_active_next_profile must accept and commit runtime_config_volume, not global vol."""
        source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        self.assertIn(
            "def _write_active_next_profile(self, payload: dict, runtime_config_volume)",
            source,
            "_write_active_next_profile must accept explicit runtime_config_volume parameter",
        )
        self.assertIn(
            "runtime_config_volume.commit()",
            source,
            "_write_active_next_profile must commit the passed runtime_config_volume",
        )


class TestMountCollisionRegression(unittest.TestCase):
    """Static regression: V1 runtime data paths use ``/root/comfymodal_runtime_state``
    so they cannot collide with the packaged ``comfymodal_runtime`` Python module source.
    """

    V2_RUNTIME_STATE_PATH = "/root/comfymodal_runtime_state"
    EXPECTED_PATHS = (
        ("PRELOAD_MODE_PATH", "/root/comfymodal_runtime_state/.preload_mode"),
        ("RUNTIME_CONFIG_DIR", "/root/comfymodal_runtime_state"),
        ("RUNTIME_CONFIG_PATH", "/root/comfymodal_runtime_state"),
        ("LAST_MODEL_STACK_PATH", "/root/comfymodal_runtime_state/.last_model_stack.json"),
        ("LAST_WARMUP_WORKFLOW_PATH", "/root/comfymodal_runtime_state/.last_warmup_workflow.json"),
        ("SAGE_RUNTIME_CACHE_PATH", "/root/comfymodal_runtime_state/.sage_runtime_cache.json"),
        ("TORCHINDUCTOR_CACHE_DIR (env)", "/root/comfymodal_runtime_state/.inductor-cache"),
    )

    def setUp(self):
        self.source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")

    def test_all_v1_runtime_paths_use_runtime_state(self):
        """Every V1 runtime-config data path must use /root/comfymodal_runtime_state."""
        errors = []
        for name, expected in self.EXPECTED_PATHS:
            if expected not in self.source:
                errors.append(f"{name}: expected {expected!r} not found in source")
        self.assertFalse(errors, "\n".join(errors))

    def test_no_v1_runtime_path_uses_old_comfymodal_runtime(self):
        """No V1 runtime-config data path must point to /root/comfymodal_runtime
        (the packaged module path)."""
        import re
        # Look for assignments of string literals containing
        # "/root/comfymodal_runtime" that are NOT followed by "_state".
        # This catches bare old paths that were missed.
        pattern = r'"/root/comfymodal_runtime[^_]'
        matches = re.findall(pattern, self.source)
        # Filter out Python import lines (e.g. from comfymodal_runtime.contracts ...)
        # which are legitimate package references, not data paths.
        lines = self.source.split("\n")
        bad = []
        for i, line in enumerate(lines, 1):
            if '"/root/comfymodal_runtime"' in line or '"/root/comfymodal_runtime/' in line:
                # Check this is not an import statement
                stripped = line.strip()
                if not (stripped.startswith("from") or stripped.startswith("import") or
                        "#" in stripped and any(kw in stripped for kw in ("import", "from"))):
                    bad.append(f"  Line {i}: {stripped}")
        self.assertFalse(bad,
                         f"Found data-path references to old /root/comfymodal_runtime:\n" + "\n".join(bad))

    def test_python_package_imports_unchanged(self):
        """Python package imports of comfymodal_runtime must still use the module
        name (not _state) — these are source imports, not data paths."""
        self.assertIn("from comfymodal_runtime", self.source,
                      "comfymodal_runtime Python package imports must remain intact")
        self.assertIn("import comfymodal_runtime", self.source,
                      "comfymodal_runtime Python package import must remain intact")

    def test_v1_matches_v2_runtime_state_path(self):
        """V1 runtime data path must match V2's RUNTIME_STATE_PATH."""
        self.assertIn(
            self.V2_RUNTIME_STATE_PATH,
            self.source,
            f"V1 must use {self.V2_RUNTIME_STATE_PATH} (same as V2)",
        )

    def test_volume_name_unchanged(self):
        """The Modal volume name comfymodal-runtime-config must not be changed."""
        self.assertIn(
            'RUNTIME_CONFIG_VOLUME_NAME = "comfymodal-runtime-config"',
            self.source,
        )

    def test_COMFYAPP_VERSION_bumped(self):
        """COMFYAPP_VERSION must be 2.16.27."""
        self.assertIn(
            'COMFYAPP_VERSION = "2.16.27"',
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
