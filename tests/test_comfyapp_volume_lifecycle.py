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
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
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


def _collect_attribute_reads(method_body):
    """Return {(obj_name, attr_name)} for every attribute read obj.attr in an AST node body."""
    return {
        (node.value.id, node.attr)
        for node in ast.walk(method_body)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
    }


class ComfyAppVolumeLifecycleTests(unittest.TestCase):
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

    def test_restore_does_not_reload_or_sync(self):
        # NOTE: This AST-level check only catches *direct* calls within the
        # restore() method body.  Calls hidden behind delegation (e.g.
        # _sync_custom_nodes_from_volume → custom_nodes_vol.reload) are
        # NOT visible to this parser.  The intent is to enforce that
        # restore() stays trivially lightweight at the source level so
        # snapshot restore is nearly free.
        restore = _get_method("restore")
        forbidden = {
            ("vol", "reload"),
            ("custom_nodes_vol", "reload"),
            ("self", "_sync_custom_nodes_from_volume"),
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


if __name__ == "__main__":
    unittest.main()
