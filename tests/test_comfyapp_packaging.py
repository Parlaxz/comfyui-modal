import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"


class ComfyAppPackagingTests(unittest.TestCase):
    def test_comfyapp_does_not_import_sibling_custom_node_sync_module(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("from custom_node_sync import", source)

    def test_comfyapp_does_not_top_level_import_httpx(self):
        tree = ast.parse(COMFYAPP_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertNotIn("httpx", imported)

    def test_all_modal_images_include_gpu_catalog_source(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        # gpu_catalog is added via the loop in _add_comfymodal_local_python_sources
        self.assertIn('"gpu_catalog"', source)
        self.assertIn('_COMFYMODAL_LOCAL_PYTHON_SOURCES', source)

    def test_all_modal_images_include_timing_trace_source(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        # timing_trace is added via the loop in _add_comfymodal_local_python_sources
        self.assertIn('"timing_trace"', source)
        self.assertIn('_COMFYMODAL_LOCAL_PYTHON_SOURCES', source)

    def test_image_pins_sageattention_220(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("git+https://github.com/thu-ml/SageAttention.git@v2.2.0", source)

    def test_image_verifies_compiled_sageattention_artifacts(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("glob('*.so')", source)
        self.assertIn("import sageattention._fused", source)

    def test_image_fused_verification_command_uses_safe_quotes(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("print('sageattention._fused ok')", source)

    def test_image_build_uses_dedicated_requirements_path(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("/root/comfy-build/custom_node_requirements", source)

    def test_image_uses_combined_requirements_add_local_dir(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("_LOCAL_CUSTOM_NODE_REQUIREMENTS_DIR", source)
        self.assertNotIn("_custom_node_requirements_context_dir(_node_name)", source)

    def test_image_uses_monolithic_requirements_install_loop(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("_pip_node", source)
        self.assertIn('for d in /root/comfy-build/custom_node_requirements/*/; do', source)

    def test_image_uses_per_node_add_local_dir_not_monolithic(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        # The monolithic add_local_dir for _LOCAL_CUSTOM_NODES must be gone.
        # The f-string pattern (with the "f" prefix before the opening quote)
        # is the new per-node form, which should be present.
        self.assertNotIn("add_local_dir(\n        _LOCAL_CUSTOM_NODES,", source)
        self.assertIn("_iter_syncable_custom_node_dirs", source)
        self.assertIn('f"/root/comfy/ComfyUI/custom_nodes/{_node_name}"', source)

    def test_per_node_add_local_dir_uses_custom_ignore_helper(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("ignore=_custom_node_image_ignore_patterns(_node_name)", source)


if __name__ == "__main__":
    unittest.main()
