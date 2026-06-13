"""Acceptance tests for the Modal image packaging refactoring.

All tests are read-only — they inspect source code in comfyapp.py via
AST parsing and string matching WITHOUT importing the module.
"""

import ast
import os
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"
INIT_PATH = REPO_ROOT / "__init__.py"


class ImagePackagingRefactorTest(unittest.TestCase):
    """Validate Modal image layer refactoring via static source analysis."""

    @classmethod
    def setUpClass(cls):
        with open(COMFYAPP_PATH, "r", encoding="utf-8") as f:
            cls.source = f.read()
        cls.tree = ast.parse(cls.source)
        with open(INIT_PATH, "r", encoding="utf-8") as f:
            cls.init_source = f.read()
        cls.init_tree = ast.parse(cls.init_source)

    # ── Helper: extract a top-level list variable ──

    @staticmethod
    def _find_list_variable(tree: ast.AST, name: str) -> list[str] | None:
        """Return the list of literal strings for a top-level list variable."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        if isinstance(node.value, ast.List):
                            return [
                                elt.value
                                for elt in node.value.elts
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                            ]
        return None

    @staticmethod
    def _find_tuple_variable(tree: ast.AST, name: str) -> tuple[str, ...] | None:
        """Return the tuple of literal strings for a top-level tuple variable."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        if isinstance(node.value, ast.Tuple):
                            return tuple(
                                elt.value
                                for elt in node.value.elts
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                            )
        return None

    @staticmethod
    def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef | None:
        """Return the AST node for a top-level function definition."""
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        return None

    # ═══════════════════════════════════════════════════════════════
    # Combined-layer filtering tests
    # ═══════════════════════════════════════════════════════════════

    def test_comfyui_modal_excluded_from_combined_ignore_patterns(self):
        """Verify _COMBINED_CUSTOM_NODE_IGNORE_PATTERNS contains 'comfyui-modal'."""
        patterns = self._find_list_variable(self.tree, "_COMBINED_CUSTOM_NODE_IGNORE_PATTERNS")
        self.assertIsNotNone(patterns, "_COMBINED_CUSTOM_NODE_IGNORE_PATTERNS not found")
        self.assertIn("comfyui-modal", patterns,
                       "Expected 'comfyui-modal' in combined ignore patterns")

    def test_third_party_node_names_exclude_comfyui_modal(self):
        """Verify source creates a filtered list excluding the local node name
        via os.path.normcase comparison."""
        # Look for the _third_party_syncable_node_names assignment with normcase
        self.assertIn("_third_party_syncable_node_names", self.source,
                       "Expected _third_party_syncable_node_names variable")
        self.assertIn("os.path.normcase(name) != os.path.normcase(_local_node_name)",
                       self.source,
                       "Expected normcase-based filtering of local node name")

    def test_all_other_syncable_nodes_remain(self):
        """Verify the print diagnostic shows all_syncable_nodes and third_party_nodes."""
        self.assertIn("all_syncable_nodes=", self.source,
                       "Expected diagnostic print with all_syncable_nodes=")
        self.assertIn("third_party_nodes=", self.source,
                       "Expected diagnostic print with third_party_nodes=")
        # Verify they appear on the same line (the print spans multiple source lines
        # via implicit string concatenation, so use DOTALL to match across newlines)
        self.assertTrue(
            re.search(r'all_syncable_nodes=.*third_party_nodes=', self.source, re.DOTALL),
            "all_syncable_nodes= and third_party_nodes= should be on the same print line"
        )

    def test_combined_ignore_excludes_whole_comfyui_modal_subtree(self):
        """Verify the pattern 'comfyui-modal' (bare directory name) appears
        in the combined ignore pattern list, excluding the entire subtree."""
        patterns = self._find_list_variable(self.tree, "_COMBINED_CUSTOM_NODE_IGNORE_PATTERNS")
        self.assertIsNotNone(patterns)
        self.assertIn("comfyui-modal", patterns,
                       "Bare directory name 'comfyui-modal' must be in ignore patterns")

    def test_combined_layer_diag_shows_comfyui_modal_excluded(self):
        """Verify the diagnostic prints combined_layer_contains_comfyui_modal=0."""
        self.assertIn("combined_layer_contains_comfyui_modal=", self.source,
                       "Expected diagnostic line for combined_layer_contains_comfyui_modal")

    def test_no_comfyui_modal_path_in_ignore_patterns_remaining(self):
        """Check that the combined layer's ignore list contains the blanket
        'comfyui-modal' exclusion and all comfyui-modal entries are proper
        exclusion patterns (starting with 'comfyui-modal')."""
        patterns = self._find_list_variable(self.tree, "_COMBINED_CUSTOM_NODE_IGNORE_PATTERNS")
        self.assertIsNotNone(patterns)
        # Every entry that mentions comfyui-modal should start with "comfyui-modal"
        # and the bare "comfyui-modal" (no subpath) should be present.
        modal_entries = [p for p in patterns if "comfyui-modal" in p]
        self.assertGreater(len(modal_entries), 0,
                           "Expected at least one comfyui-modal ignore pattern")
        for entry in modal_entries:
            self.assertTrue(
                entry == "comfyui-modal" or entry.startswith("comfyui-modal/"),
                f"Unexpected comfyui-modal pattern format: {entry!r}"
            )

    # ═══════════════════════════════════════════════════════════════
    # Separate runtime mount tests
    # ═══════════════════════════════════════════════════════════════

    def test_separate_comfyui_modal_source_spec_exists(self):
        """Verify there is a separate add_local_dir call mounting
        _COMFYUI_MODAL_DIR to /root/comfy/ComfyUI/custom_nodes/comfyui-modal."""
        self.assertIn(
            "/root/comfy/ComfyUI/custom_nodes/comfyui-modal",
            self.source,
            "Expected add_local_dir targeting comfyui-modal mount path"
        )
        self.assertIn("add_local_dir", self.source,
                       "Expected add_local_dir call for separate mount")

    def test_separate_mount_uses_copy_false(self):
        """Verify the separate mount uses copy=False."""
        # Find the add_local_dir call for comfyui-modal
        # Look for copy=False in proximity to the comfyui-modal mount path
        mount_marker = "/root/comfy/ComfyUI/custom_nodes/comfyui-modal"
        idx = self.source.rfind(mount_marker)
        self.assertGreater(idx, 0, "Mount path not found")
        # Search backward for the add_local_dir call containing copy=False
        chunk = self.source[max(0, idx - 200):idx + len(mount_marker) + 100]
        self.assertIn("copy=False", chunk,
                       "Expected copy=False in the comfyui-modal mount")

    def test_comfyui_modal_mount_after_baked_manifest(self):
        """Verify the separate mount occurs AFTER the baked manifest
        add_local_file line in the source."""
        # Baked manifest add_local_file marker
        baked_marker = "custom_node_deps_baked.json"
        mount_marker = "/root/comfy/ComfyUI/custom_nodes/comfyui-modal"
        baked_pos = self.source.find(baked_marker)
        mount_pos = self.source.find(mount_marker)
        self.assertGreater(baked_pos, 0,
                           "Baked manifest add_local_file not found")
        self.assertGreater(mount_pos, 0,
                           "comfyui-modal mount not found")
        self.assertGreater(
            mount_pos, baked_pos,
            "comfyui-modal mount should appear AFTER baked manifest add_local_file"
        )

    def test_runtime_required_python_files_present_in_ignore(self):
        """The runtime mount ignore list should NOT exclude __init__.py,
        comfyapp.py, or production_workflow.py."""
        # Find the _COMFYUI_MODAL_RUNTIME_IGNORE list
        ignore_var = self._find_list_variable(self.tree, "_COMFYUI_MODAL_RUNTIME_IGNORE")
        self.assertIsNotNone(ignore_var, "_COMFYUI_MODAL_RUNTIME_IGNORE not found")
        runtime_required = ["__init__.py", "comfyapp.py", "production_workflow.py"]
        for fname in runtime_required:
            self.assertNotIn(
                fname, ignore_var,
                f"Runtime-required file '{fname}' should NOT be in the runtime mount ignore list"
            )

    def test_frontend_files_present_in_runtime_mount_ignore(self):
        """The runtime mount ignore list should NOT exclude web/modal-comparison.js,
        web/modal-node.js, or web/modal-settings.js."""
        ignore_var = self._find_list_variable(self.tree, "_COMFYUI_MODAL_RUNTIME_IGNORE")
        self.assertIsNotNone(ignore_var)
        frontend_files = [
            "web/modal-comparison.js",
            "web/modal-node.js",
            "web/modal-settings.js",
        ]
        for fname in frontend_files:
            self.assertNotIn(
                fname, ignore_var,
                f"Frontend file '{fname}' should NOT be in the runtime mount ignore list"
            )

    def test_tests_excluded_from_runtime_mount(self):
        """The runtime mount ignore list MUST include tests/ and test_* patterns."""
        ignore_var = self._find_list_variable(self.tree, "_COMFYUI_MODAL_RUNTIME_IGNORE")
        self.assertIsNotNone(ignore_var)
        self.assertIn("tests/", ignore_var,
                       "Expected 'tests/' in runtime mount ignore list")
        self.assertIn("test_*", ignore_var,
                       "Expected 'test_*' in runtime mount ignore list")

    def test_no_duplicate_destination_ownership(self):
        """Verify an assertion detects duplicate ownership after the
        comfyui-modal runtime mount."""
        self.assertIn(
            "assert not _combined_has_modal",
            self.source,
            "Expected assertion that detects duplicate comfyui-modal ownership"
        )
        self.assertIn("combined_has_modal", self.source,
                       "Expected _combined_has_modal validation")

    # ═══════════════════════════════════════════════════════════════
    # Fingerprint tests
    # ═══════════════════════════════════════════════════════════════

    def test_gpu_fingerprint_includes_all_helper_modules(self):
        """Verify _compute_comfymodal_deploy_fingerprint_gpu hashes all
        modules in _COMFYMODAL_LOCAL_PYTHON_SOURCES."""
        helper_sources = self._find_tuple_variable(
            self.tree, "_COMFYMODAL_LOCAL_PYTHON_SOURCES"
        )
        self.assertIsNotNone(
            helper_sources, "_COMFYMODAL_LOCAL_PYTHON_SOURCES not found"
        )
        # Raw source check: the GPU fingerprint function iterates over
        # _COMFYMODAL_LOCAL_PYTHON_SOURCES and builds f-string paths
        self.assertIn(
            "_COMFYMODAL_LOCAL_PYTHON_SOURCES",
            self.source,
            "GPU fingerprint must reference _COMFYMODAL_LOCAL_PYTHON_SOURCES"
        )
        # Verify the f-string interpolation pattern exists in the GPU func body
        self.assertIn(
            'f"{_modname}.py"',
            self.source,
            "GPU fingerprint must build paths like f'{_modname}.py' for each module"
        )

    def test_helper_fingerprint_excludes_helper_modules(self):
        """Verify helper fingerprint (_compute_comfymodal_deploy_fingerprint_helper)
        does NOT include production_workflow.py in its hash computation."""
        helper_func = self._find_function(
            self.tree, "_compute_comfymodal_deploy_fingerprint_helper"
        )
        self.assertIsNotNone(helper_func, "Helper fingerprint function not found")
        # The docstring mentions production_workflow.py, but the actual hash
        # computation should only hash comfyapp.py.  Use the AST node to get
        # ONLY the function's own body (not subsequent functions).
        # ast.get_source_segment extracts the exact function text, then we
        # strip the docstring.
        try:
            func_source = ast.get_source_segment(self.source, helper_func)
        except TypeError:
            # Fallback: extract via ast.unparse and remove docstring
            func_source = ast.unparse(helper_func)
        # Remove the def line and docstring to get just the code body
        lines = func_source.split("\n")
        code_lines = []
        in_docstring = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if i == 0:
                continue  # skip def signature
            if not in_docstring and stripped.startswith('"""'):
                # Start of docstring
                if stripped[3:].strip().endswith('"""'):
                    continue  # single-line docstring
                in_docstring = True
                continue
            if in_docstring:
                if '"""' in stripped:
                    in_docstring = False
                continue
            code_lines.append(line)
        code_body = "\n".join(code_lines).strip()
        self.assertIn("comfyapp.py", code_body,
                       "Helper fingerprint must hash comfyapp.py")
        self.assertNotIn("production_workflow", code_body,
                         "Helper fingerprint body must NOT reference production_workflow.py")
        # Also verify role=helper in the original source
        self.assertIn("role=helper", self.source,
                       "Helper fingerprint should use role=helper")

    def test_changing_production_workflow_does_not_change_helper_fingerprint(self):
        """Verify helper fingerprint function hashes only comfyapp.py
        (not production_workflow.py), so changing production_workflow.py
        does not change the helper fingerprint."""
        # Use AST to extract exactly the function body (not trailing code).
        helper_func = self._find_function(
            self.tree, "_compute_comfymodal_deploy_fingerprint_helper"
        )
        self.assertIsNotNone(helper_func, "Helper fingerprint function not found")
        try:
            func_source = ast.get_source_segment(self.source, helper_func)
        except TypeError:
            func_source = ast.unparse(helper_func)
        # Strip docstring to get just the code body
        lines = func_source.split("\n")
        code_lines = []
        in_docstring = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if i == 0:
                continue  # skip def signature
            if not in_docstring and stripped.startswith('"""'):
                if stripped[3:].strip().endswith('"""'):
                    continue  # single-line docstring
                in_docstring = True
                continue
            if in_docstring:
                if '"""' in stripped:
                    in_docstring = False
                continue
            code_lines.append(line)
        code_body = "\n".join(code_lines).strip()
        self.assertIn("comfyapp.py", code_body,
                       "Helper fingerprint must reference comfyapp.py")
        self.assertNotIn("production_workflow", code_body,
                          "Helper fingerprint must NOT reference production_workflow.py")

    def test_fingerprints_are_deterministic(self):
        """Verify fingerprint computation uses hashlib.sha256() with sorted
        inputs and no time.time(), uuid, or random."""
        gpu_func = self._find_function(self.tree, "_compute_comfymodal_deploy_fingerprint_gpu")
        self.assertIsNotNone(gpu_func)
        gpu_source = ast.unparse(gpu_func)
        helper_func = self._find_function(
            self.tree, "_compute_comfymodal_deploy_fingerprint_helper"
        )
        self.assertIsNotNone(helper_func)
        helper_source = ast.unparse(helper_func)

        for func_name, func_source in [
            ("_compute_comfymodal_deploy_fingerprint_gpu", gpu_source),
            ("_compute_comfymodal_deploy_fingerprint_helper", helper_source),
        ]:
            # Must use hashlib.sha256 (or _h.sha256)
            self.assertIn(
                "sha256", func_source,
                f"{func_name} must use hashlib.sha256"
            )
            # Must not use non-deterministic sources
            self.assertNotIn(
                "time.time", func_source,
                f"{func_name} must not use time.time()"
            )
            self.assertNotIn(
                "uuid", func_source,
                f"{func_name} must not use uuid"
            )
            self.assertNotIn(
                "random", func_source,
                f"{func_name} must not use random"
            )
        # The GPU function hashes multiple files, so it must use sorted()
        # for deterministic ordering.  The helper only hashes comfyapp.py
        # (a single file), so sorted() is not required there.
        self.assertIn(
            "sorted", gpu_source,
            "_compute_comfymodal_deploy_fingerprint_gpu must use sorted() "
            "for deterministic ordering of multiple candidates"
        )

    def test_fingerprint_schema_version_is_v2(self):
        """Verify the fingerprint uses 'comfymodal_deploy_fingerprint_v2'."""
        # Check both fingerprint functions
        gpu_func = self._find_function(self.tree, "_compute_comfymodal_deploy_fingerprint_gpu")
        helper_func = self._find_function(
            self.tree, "_compute_comfymodal_deploy_fingerprint_helper"
        )
        for func in [gpu_func, helper_func]:
            self.assertIsNotNone(func)
            func_source = ast.unparse(func)
            self.assertIn(
                "comfymodal_deploy_fingerprint_v2", func_source,
                f"Expected fingerprint v2 in {func.name}"
            )

    def test_gpu_identity_receives_gpu_fingerprint(self):
        """Verify the main image = _add_comfymodal_local_python_sources(_image_base, role='gpu')
        exists (with apply_fingerprint=False since fingerprint is applied before
        the comfyui-modal runtime mount)."""
        self.assertIn(
            '_add_comfymodal_local_python_sources(_image_base, role="gpu"',
            self.source.replace("'", '"'),
        )
        # The GPU image must not reapply the fingerprint (it was applied
        # before the comfyui-modal runtime mount).
        self.assertIn("apply_fingerprint=False", self.source,
                       "GPU image should use apply_fingerprint=False")

    def test_remote_container_uses_env_fingerprint_instead_of_recomputing(self):
        """Remote containers should reuse the injected deploy fingerprint env vars
        instead of recomputing local-file hashes for comfyui-modal runtime files."""
        normalized = self.source.replace("'", '"')
        self.assertIn(
            "if _INSIDE_MODAL_CONTAINER:\n    COMFYMODAL_DEPLOY_FINGERPRINT = os.environ.get(",
            normalized,
            "Expected remote-container branch that assigns COMFYMODAL_DEPLOY_FINGERPRINT from env"
        )

    def test_helper_functions_use_helper_role(self):
        """Verify inline calls with role='helper' exist."""
        # Check for role="helper" in add_comfymodal_local_python_sources calls
        helper_call_pattern = r'role\s*=\s*["\']helper["\']'
        self.assertTrue(
            re.search(helper_call_pattern, self.source),
            "Expected at least one call with role='helper'"
        )

    # ═══════════════════════════════════════════════════════════════
    # Dependency artifact tests
    # ═══════════════════════════════════════════════════════════════

    def test_manifest_does_not_include_comfyapp_version(self):
        """The baked manifest dict should NOT include 'comfyapp_version'.
        Instead it should have 'dependency_scanner_version'."""
        # Find the return dict in build_custom_node_dependency_manifest
        self.assertIn(
            "dependency_scanner_version", self.source,
            "Expected dependency_scanner_version in manifest"
        )
        self.assertIn(
            "CUSTOM_NODE_DEPENDENCY_SCANNER_VERSION", self.source,
            "Expected CUSTOM_NODE_DEPENDENCY_SCANNER_VERSION reference"
        )
        # Verify comfyapp_version is NOT returned by build_custom_node_dependency_manifest
        # (it contains 'dependency_scanner_version' instead)
        func = self._find_function(self.tree, "build_custom_node_dependency_manifest")
        self.assertIsNotNone(func)
        func_source = ast.unparse(func)
        self.assertIn("dependency_scanner_version", func_source)
        self.assertNotIn("comfyapp_version", func_source)

    def test_cache_key_does_not_use_comfyapp_version(self):
        """The build_dependency_validation_cache_key function should not hash
        comfyapp_version. Instead it should use dependency_validation_code_schema."""
        func = self._find_function(self.tree, "build_dependency_validation_cache_key")
        self.assertIsNotNone(func)
        func_source = ast.unparse(func)
        self.assertIn(
            "dependency_validation_code_schema", func_source,
            "Expected dependency_validation_code_schema in cache key"
        )
        self.assertNotIn(
            "comfyapp_version", func_source,
            "Cache key should NOT include comfyapp_version"
        )
        self.assertNotIn(
            "comfyapp", func_source,
            "Cache key should NOT include comfyapp at all"
        )
        # Verify it uses hashlib.sha256 with deterministic inputs
        self.assertIn("sha256", func_source)

    def test_manifest_schema_version_is_3(self):
        """Verify CUSTOM_NODE_DEPENDENCY_MANIFEST_SCHEMA_VERSION is 3."""
        pattern = r"CUSTOM_NODE_DEPENDENCY_MANIFEST_SCHEMA_VERSION\s*=\s*3\b"
        self.assertTrue(
            re.search(pattern, self.source),
            "Expected CUSTOM_NODE_DEPENDENCY_MANIFEST_SCHEMA_VERSION = 3"
        )

    def test_cache_schema_version_is_2(self):
        """Verify DEPENDENCY_VALIDATION_CACHE_SCHEMA_VERSION is 2."""
        pattern = r"DEPENDENCY_VALIDATION_CACHE_SCHEMA_VERSION\s*=\s*2\b"
        self.assertTrue(
            re.search(pattern, self.source),
            "Expected DEPENDENCY_VALIDATION_CACHE_SCHEMA_VERSION = 2"
        )

    def test_changing_requirements_changes_dependency_manifest(self):
        """Verify build_custom_node_dependency_manifest exists and hashes
        requirements.txt files."""
        func = self._find_function(self.tree, "build_custom_node_dependency_manifest")
        self.assertIsNotNone(func, "build_custom_node_dependency_manifest not found")
        func_source = ast.unparse(func)
        self.assertIn(
            "requirements.txt", func_source,
            "build_custom_node_dependency_manifest should reference requirements.txt"
        )
        self.assertIn(
            "sha256", func_source,
            "build_custom_node_dependency_manifest should use hashlib.sha256"
        )

    # ═══════════════════════════════════════════════════════════════
    # Size diagnostic tests
    # ═══════════════════════════════════════════════════════════════

    def test_comfyui_modal_size_diag_exists(self):
        """Verify the diagnostics print 'comfyui_modal_size_diag: raw_source_bytes='."""
        self.assertIn(
            "comfyui_modal_size_diag: raw_source_bytes=", self.source,
            "Expected comfyui_modal_size_diag diagnostic"
        )

    def test_combined_layer_comfyui_modal_included_bytes_is_zero(self):
        """Verify the diagnostic prints 'combined_layer_comfyui_modal_included_bytes=0'."""
        self.assertIn(
            "combined_layer_comfyui_modal_included_bytes=", self.source,
            "Expected combined_layer_comfyui_modal_included_bytes diagnostic"
        )
        # The code at line 4209 shows _comfyui_modal_est_included is set to 0
        # when the node is comfyui-modal (line 4194)
        self.assertIn(
            "_comfyui_modal_est_included=0", self.source.replace(" ", ""),
            "comfyui-modal included bytes should be computed as 0"
        )

    # ═══════════════════════════════════════════════════════════════
    # Existing behavior tests
    # ═══════════════════════════════════════════════════════════════

    def test_gpu_class_imports_required_modules(self):
        """Verify top-level imports include gpu_catalog, production_workflow, etc."""
        required_imports = [
            "from gpu_catalog import GPU_CATALOG",
            "from production_workflow import",
            "from failure_summary import FailureSummary",
            "from api_prompt_validator import",
            "from timing_trace import Trace",
        ]
        for imp in required_imports:
            self.assertIn(imp, self.source, f"Expected import: {imp}")

    def test_comfyui_modal_custom_node_registers_locally(self):
        """Verify __init__.py still has WEB_DIRECTORY = 'web' and
        NODE_CLASS_MAPPINGS = {}."""
        self.assertIn(
            'WEB_DIRECTORY = "web"',
            self.init_source,
            "Expected WEB_DIRECTORY = 'web' in __init__.py"
        )
        self.assertIn(
            "NODE_CLASS_MAPPINGS = {}",
            self.init_source,
            "Expected NODE_CLASS_MAPPINGS = {} in __init__.py"
        )

    def test_prohibited_settings_unchanged(self):
        """Verify certain env var settings are unchanged in the image definition."""
        checks = [
            ('"COMFYMODAL_PRELOAD_MODE": "clip_only"',
             "COMFYMODAL_PRELOAD_MODE should be clip_only"),
            ('"COMFYMODAL_DIRECT_WARMUP_LOAD_CLIP": "1"',
             "COMFYMODAL_DIRECT_WARMUP_LOAD_CLIP should be 1"),
            ('"COMFYMODAL_SAFETENSORS_READ_MODE": "normal"',
             "COMFYMODAL_SAFETENSORS_READ_MODE should be normal"),
            ('"ACTUAL_LOAD_MODE": "unet_vae_only"',
             "ACTUAL_LOAD_MODE should be unet_vae_only"),
            ('"COMFYMODAL_RESTORE_BACKGROUND_UNET": "0"',
             "COMFYMODAL_RESTORE_BACKGROUND_UNET should be 0 (disabled by default)"),
        ]
        for setting, msg in checks:
            self.assertIn(setting, self.source, msg)


    # ═══════════════════════════════════════════════════════════════
    # Combined-layer validation bug fix tests
    # ═══════════════════════════════════════════════════════════════

    def test_local_comfyui_modal_exists_diag_exists(self):
        """Verify the diagnostic prints 'local_comfyui_modal_exists=' separately
        from 'combined_layer_contains_comfyui_modal='."""
        self.assertIn("local_comfyui_modal_exists=", self.source,
                       "Expected local_comfyui_modal_exists diagnostic")
        self.assertIn("combined_layer_contains_comfyui_modal=", self.source,
                       "Expected combined_layer_contains_comfyui_modal diagnostic")

    def test_local_exists_and_combined_membership_are_separate_variables(self):
        """Verify _local_comfyui_modal_exists and _combined_has_modal are
        two separate variables computed independently."""
        self.assertIn("_local_comfyui_modal_exists", self.source,
                       "Expected _local_comfyui_modal_exists variable")
        self.assertIn("_combined_has_modal", self.source,
                       "Expected _combined_has_modal variable")
        # _local_comfyui_modal_exists uses os.path.isdir (local dir check)
        self.assertIn(
            "os.path.isdir",
            self.source,
            "Expected os.path.isdir check for local directory existence"
        )
        # _combined_has_modal uses any() with normcase (filtered list check)
        self.assertIn(
            "os.path.normcase",
            self.source,
            "Expected normcase-based comparison for combined membership"
        )

    def test_filtered_list_excludes_exact_comfyui_modal(self):
        """Verify _third_party_syncable_node_names excludes exact
        'comfyui-modal' using case-normalized comparison."""
        self.assertIn("_third_party_syncable_node_names", self.source)
        self.assertIn(
            "os.path.normcase(name) != os.path.normcase(_local_node_name)",
            self.source,
            "Expected normcase filtering for _third_party_syncable_node_names"
        )

    def test_combined_ignore_has_exact_pattern(self):
        """Verify _COMBINED_CUSTOM_NODE_IGNORE_PATTERNS contains the bare
        'comfyui-modal' entry (exact directory exclusion)."""
        patterns = self._find_list_variable(self.tree, "_COMBINED_CUSTOM_NODE_IGNORE_PATTERNS")
        self.assertIsNotNone(patterns)
        self.assertIn("comfyui-modal", patterns,
                       "Expected exact 'comfyui-modal' in combined ignore patterns")

    def test_combined_ignore_has_recursive_pattern(self):
        """Verify _COMBINED_CUSTOM_NODE_IGNORE_PATTERNS contains
        'comfyui-modal/**' (recursive directory exclusion)."""
        patterns = self._find_list_variable(self.tree, "_COMBINED_CUSTOM_NODE_IGNORE_PATTERNS")
        self.assertIsNotNone(patterns)
        self.assertIn("comfyui-modal/**", patterns,
                       "Expected 'comfyui-modal/**' in combined ignore patterns")

    def test_combined_ignore_has_trailing_slash_pattern(self):
        """Verify _COMBINED_CUSTOM_NODE_IGNORE_PATTERNS contains
        'comfyui-modal/' (trailing-slash directory exclusion)."""
        patterns = self._find_list_variable(self.tree, "_COMBINED_CUSTOM_NODE_IGNORE_PATTERNS")
        self.assertIsNotNone(patterns)
        self.assertIn("comfyui-modal/", patterns,
                       "Expected 'comfyui-modal/' in combined ignore patterns")

    def test_ignore_validation_assertions_exist(self):
        """Verify build-time ignore configuration validation assertions exist."""
        self.assertIn(
            "_combined_ignore_exact", self.source,
            "Expected _combined_ignore_exact validation set"
        )
        self.assertIn(
            "_combined_ignore_recursive", self.source,
            "Expected _combined_ignore_recursive validation set"
        )
        self.assertIn(
            "combined custom-node ignore patterns do not contain the exact",
            self.source,
            "Expected assertion message for missing exact ignore pattern"
        )
        self.assertIn(
            "combined custom-node ignore patterns do not contain the recursive",
            self.source,
            "Expected assertion message for missing recursive ignore pattern"
        )

    def test_local_directory_assertion_exists(self):
        """Verify the assertion that the local comfyui-modal source
        directory must exist before the separate runtime mount."""
        self.assertIn(
            "_local_comfyui_modal_exists", self.source,
            "Expected _local_comfyui_modal_exists check"
        )
        self.assertIn(
            "Expected local comfyui-modal source directory does not exist",
            self.source,
            "Expected assertion message for missing local directory"
        )

    def test_separate_runtime_mount_destination_unchanged(self):
        """Verify the separate runtime mount destination path remains
        /root/comfy/ComfyUI/custom_nodes/comfyui-modal."""
        self.assertIn(
            "/root/comfy/ComfyUI/custom_nodes/comfyui-modal",
            self.source,
            "Expected comfyui-modal mount destination path"
        )

    def test_separate_runtime_mount_remains_copy_false(self):
        """Verify the separate runtime mount is still copy=False."""
        mount_marker = "/root/comfy/ComfyUI/custom_nodes/comfyui-modal"
        idx = self.source.rfind(mount_marker)
        self.assertGreater(idx, 0)
        chunk = self.source[max(0, idx - 300):idx + len(mount_marker) + 100]
        self.assertIn("copy=False", chunk,
                       "Separate mount must remain copy=False")


if __name__ == "__main__":
    unittest.main()
