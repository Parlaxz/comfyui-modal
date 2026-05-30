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


if __name__ == "__main__":
    unittest.main()
