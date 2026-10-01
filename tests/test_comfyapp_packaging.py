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
        tree = ast.parse(COMFYAPP_PATH.read_text(encoding="utf-8-sig"))
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
        self.assertIn('_GPU_COMFYMODAL_PYTHON_SOURCES', source)
        self.assertIn('_CPU_COMFYMODAL_PYTHON_SOURCES', source)

    def test_all_modal_images_include_timing_trace_source(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        # timing_trace is added via the loop in _add_comfymodal_local_python_sources
        self.assertIn('"timing_trace"', source)
        self.assertIn('_GPU_COMFYMODAL_PYTHON_SOURCES', source)
        self.assertIn('_CPU_COMFYMODAL_PYTHON_SOURCES', source)

    def test_warmup_profile_image_helpers_include_comfyapp(self):
        tree = ast.parse(COMFYAPP_PATH.read_text(encoding="utf-8-sig"))
        helper_names = {"_add_gpu_python_sources", "_add_cpu_python_sources"}
        found = {name: False for name in helper_names}
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name not in helper_names:
                continue
            for call in ast.walk(node):
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                    continue
                if call.func.attr != "add_local_dir" or len(call.args) < 2:
                    continue
                destination = call.args[1]
                copy_ok = any(
                    keyword.arg == "copy"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in call.keywords
                )
                if (isinstance(destination, ast.Constant)
                        and destination.value == "/root" and copy_ok):
                    found[node.name] = True
        self.assertEqual(found, {name: True for name in helper_names})

    def test_image_helpers_explicitly_mount_comfyapp_module(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        # Assert the user-visible destination/content contract, rather than
        # preserving separate add_local_python_source/add_local_file calls.
        self.assertIn('files: dict[str, Path] = {"comfyapp.py": Path(__file__)}', source)
        self.assertIn('"/root"', source)
        self.assertIn('"comfyapp.py"', source)

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

    def test_image_uses_per_node_requirements_add_local_dir(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("_LOCAL_CUSTOM_NODE_REQUIREMENTS_DIR", source)
        self.assertIn("_add_custom_node_requirement_layers", source)
        self.assertIn("_custom_node_requirement_context_hash", source)

    def test_image_uses_independent_requirements_install_layers(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("_pip_node", source)
        self.assertNotIn('for d in /root/comfy-build/custom_node_requirements/*/; do', source)
        self.assertIn("CUSTOM_NODE_PREREQ_UNSATISFIED node=", source)
        self.assertIn("force_build=True", source)

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
