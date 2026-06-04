import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODAL_CLIENT_PATH = REPO_ROOT / "modal_client.py"
INIT_PATH = REPO_ROOT / "__init__.py"


class ModalRuntimeRoutesASTTests(unittest.TestCase):
    """AST-level tests ensuring the wiring of resync_runtime and
    runtime_state references are present in the expected files."""

    def test_resync_runtime_defined_in_modal_client(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        funcs = {
            n.name
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef)
        }
        self.assertIn("resync_runtime", funcs)

    def test_get_runtime_state_defined_in_modal_client(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        funcs = {
            n.name
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef)
        }
        self.assertIn("get_runtime_state", funcs)

    def test_set_active_warmup_profile_defined_in_modal_client(self):
        source = MODAL_CLIENT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)}
        self.assertIn("set_active_warmup_profile", funcs)

    def _find_route_strings(self, source: str, method: str) -> set[str]:
        """Return set of route strings registered via @_server.routes.{method}(...)."""
        import re
        pattern = rf"@_server\.routes\.{method}\(\"(/comfymodal/[^\"]+)\""
        return set(re.findall(pattern, source))

    def test_resync_route_registered_in_init(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        routes = self._find_route_strings(source, "post")
        self.assertIn("/comfymodal/runtime/resync", routes)

    def test_runtime_state_route_registered_in_init(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        routes = self._find_route_strings(source, "get")
        self.assertIn("/comfymodal/runtime/state", routes)

    def test_benchmark_workflow_get_route_registered_in_init(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        routes = self._find_route_strings(source, "get")
        self.assertIn("/comfymodal/benchmark/workflow", routes)

    def test_benchmark_workflow_post_route_registered_in_init(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        routes = self._find_route_strings(source, "post")
        self.assertIn("/comfymodal/benchmark/workflow", routes)

    def test_config_get_route_exposes_available_gpus_and_default_gpu(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn('"available_gpus"', source)
        self.assertIn('"default_gpu"', source)

    def test_config_post_route_handles_invalid_gpu(self):
        source = INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("except ValueError", source)
        self.assertIn("Unsupported GPU", source)


if __name__ == "__main__":
    unittest.main()
