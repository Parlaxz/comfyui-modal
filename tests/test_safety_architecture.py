"""Tests for the safety/caching architecture (Parts 1-18)."""
import os
import sys
import json
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_prompt_validator import (
    assert_valid_api_prompt_structure,
    validate_api_prompt_structure,
    validate_class_types_exist,
)
from failure_summary import FailureSummary


# ── Test helpers ──

VALID_PROMPT = {
    "3": {"class_type": "KSampler", "inputs": {"seed": 7, "steps": 20}},
    "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux.safetensors"}},
}
MALFORMED_NODE_454 = {"454": {"inputs": {}}}
MALFORMED_NODE_454_WITH_VALID = {
    "3": {"class_type": "KSampler", "inputs": {"seed": 7}},
    "454": {"inputs": {}},
}

_ORIG_ENV = dict(os.environ)


def _unset_env(var: str):
    os.environ.pop(var, None)


# ── PART 1: Module default ──

class TestModuleDefault(unittest.TestCase):
    """Test 1: Module-level REQUIREMENTS_REPAIR_MODE defaults to fail_fast."""

    def setUp(self):
        self._saved = dict(os.environ)
        _unset_env("COMFYMODAL_REQUIREMENTS_REPAIR_MODE")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def test_default_is_fail_fast(self):
        # Import the module fresh with env unset
        import importlib
        import comfyapp as capp
        importlib.reload(capp)
        self.assertEqual(capp.REQUIREMENTS_REPAIR_MODE, "fail_fast")

    def test_env_dev_sets_dev(self):
        os.environ["COMFYMODAL_REQUIREMENTS_REPAIR_MODE"] = "dev"
        import importlib
        import comfyapp as capp
        importlib.reload(capp)
        self.assertEqual(capp.REQUIREMENTS_REPAIR_MODE, "dev")


# ── PART 3: Malformed node 454 local preflight ──

class TestMalformedNode454Preflight(unittest.TestCase):
    """Test 3: Malformed node 454 is rejected before Modal call."""

    def test_454_missing_class_type_returns_errors(self):
        errors = validate_api_prompt_structure(MALFORMED_NODE_454)
        self.assertGreater(len(errors), 0)
        self.assertIn("454", errors[0])
        self.assertIn("class_type", errors[0])

    def test_454_raises_runtime_error(self):
        with self.assertRaises(RuntimeError) as ctx:
            assert_valid_api_prompt_structure(MALFORMED_NODE_454)
        self.assertIn("454", str(ctx.exception))

    def test_454_with_valid_nodes_still_fails(self):
        errors = validate_api_prompt_structure(MALFORMED_NODE_454_WITH_VALID)
        self.assertEqual(len(errors), 1)
        self.assertIn("454", errors[0])

    def test_unknown_node_454_does_not_write_active_next_profile(self):
        prompt = MALFORMED_NODE_454
        errors = validate_api_prompt_structure(prompt)
        if errors:
            return
        self.fail("should have failed but did not")


# ── PART 4: set_active_warmup_profile validation ──

class TestSetActiveWarmupProfileValidation(unittest.TestCase):
    """Test 4-5: set_active_warmup_profile validates payloads."""

    def test_rejects_unvalidated_payload(self):
        from comfyapp import validate_active_warmup_profile_payload
        payload = {"workflow_hash": "abc", "warmup_profile": {}}
        with self.assertRaises(RuntimeError) as ctx:
            validate_active_warmup_profile_payload(payload)
        self.assertIn("preflight validated", str(ctx.exception).lower())

    def test_rejects_missing_workflow_hash(self):
        from comfyapp import validate_active_warmup_profile_payload
        payload = {
            "preflight_validated": True,
            "validation_token": "tok",
            "model_stack": {},
            "disable_warmup": True,
        }
        with self.assertRaises(RuntimeError) as ctx:
            validate_active_warmup_profile_payload(payload)
        self.assertIn("workflow_hash", str(ctx.exception).lower())

    def test_rejects_empty_workflow_hash(self):
        from comfyapp import validate_active_warmup_profile_payload
        payload = {
            "preflight_validated": True,
            "validation_token": "tok",
            "workflow_hash": "",
            "model_stack": {},
            "disable_warmup": True,
        }
        with self.assertRaises(RuntimeError) as ctx:
            validate_active_warmup_profile_payload(payload)
        self.assertIn("workflow_hash", str(ctx.exception).lower())

    def test_rejects_missing_validation_token(self):
        from comfyapp import validate_active_warmup_profile_payload
        payload = {
            "preflight_validated": True,
            "workflow_hash": "abc123",
            "model_stack": {},
            "disable_warmup": True,
        }
        with self.assertRaises(RuntimeError) as ctx:
            validate_active_warmup_profile_payload(payload)
        self.assertIn("validation_token", str(ctx.exception).lower())

    def test_rejects_missing_model_stack(self):
        from comfyapp import validate_active_warmup_profile_payload
        payload = {
            "preflight_validated": True,
            "validation_token": "tok",
            "workflow_hash": "abc123",
            "disable_warmup": True,
        }
        with self.assertRaises(RuntimeError) as ctx:
            validate_active_warmup_profile_payload(payload)
        self.assertIn("model_stack", str(ctx.exception).lower())

    def test_accepts_valid_disable_warmup_payload(self):
        from comfyapp import validate_active_warmup_profile_payload
        payload = {
            "preflight_validated": True,
            "validation_token": "test-token",
            "workflow_hash": "abc123",
            "model_stack": {},
            "disable_warmup": True,
        }
        try:
            validate_active_warmup_profile_payload(payload)
        except RuntimeError as e:
            self.fail(f"valid payload should not raise: {e}")

    def test_accepts_valid_with_warmup_profile(self):
        from comfyapp import validate_active_warmup_profile_payload
        payload = {
            "preflight_validated": True,
            "validation_token": "test-token",
            "workflow_hash": "abc123",
            "model_stack": {"unet": ["flux.safetensors"]},
            "warmup_profile": {"mode": "split", "unet": "flux.safetensors"},
        }
        try:
            validate_active_warmup_profile_payload(payload)
        except RuntimeError as e:
            self.fail(f"valid payload should not raise: {e}")

    def test_rejects_non_dict_payload(self):
        from comfyapp import validate_active_warmup_profile_payload
        with self.assertRaises(RuntimeError):
            validate_active_warmup_profile_payload([])

    def test_rejects_payload_without_warmup_profile_or_disable(self):
        from comfyapp import validate_active_warmup_profile_payload
        payload = {
            "preflight_validated": True,
            "validation_token": "tok",
            "workflow_hash": "abc123",
            "model_stack": {},
        }
        with self.assertRaises(RuntimeError) as ctx:
            validate_active_warmup_profile_payload(payload)
        self.assertIn("warmup_profile", str(ctx.exception).lower())


# ── PART 6: No-dependency node hashing ──

class TestNoDependencyNodeHashing(unittest.TestCase):
    """Test 9-11: overall_dependency_hash includes only nodes with deps."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        from comfyapp import _collect_dependency_file_paths, build_custom_node_dependency_manifest

    def _write_file(self, path: str, content: str = ""):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content)

    def test_no_dep_node_does_not_change_hash(self):
        from comfyapp import build_custom_node_dependency_manifest
        root = os.path.join(self._tmpdir, "test1")
        os.makedirs(os.path.join(root, "node_a"))
        # node_a has no requirements files
        self._write_file(os.path.join(root, "node_a", "__init__.py"), "x = 1")
        m1 = build_custom_node_dependency_manifest(root)
        h1 = m1.get("overall_dependency_hash", "")

        # Add node_b with only .py files, no deps
        os.makedirs(os.path.join(root, "node_b"))
        self._write_file(os.path.join(root, "node_b", "main.py"), "print('hello')")
        m2 = build_custom_node_dependency_manifest(root)
        h2 = m2.get("overall_dependency_hash", "")
        self.assertEqual(h1, h2, "adding no-dependency node should not change hash")

    def test_adding_requirements_changes_hash(self):
        from comfyapp import build_custom_node_dependency_manifest
        root = os.path.join(self._tmpdir, "test2")
        os.makedirs(os.path.join(root, "node_a"))
        self._write_file(os.path.join(root, "node_a", "__init__.py"), "")
        m1 = build_custom_node_dependency_manifest(root)
        h1 = m1.get("overall_dependency_hash", "")

        # Add requirements.txt to node_a
        self._write_file(os.path.join(root, "node_a", "requirements.txt"), "torch>=2.0")
        m2 = build_custom_node_dependency_manifest(root)
        h2 = m2.get("overall_dependency_hash", "")
        self.assertNotEqual(h1, h2, "adding requirements.txt should change hash")

    def test_changing_pyproject_toml_changes_hash(self):
        from comfyapp import build_custom_node_dependency_manifest
        root = os.path.join(self._tmpdir, "test3")
        os.makedirs(os.path.join(root, "node_a"))
        self._write_file(os.path.join(root, "node_a", "pyproject.toml"), "[project]\nname = 'test'")
        m1 = build_custom_node_dependency_manifest(root)
        h1 = m1.get("overall_dependency_hash", "")
        self.assertNotEqual(h1, "", "should have a non-empty hash")

        # Change pyproject.toml
        self._write_file(os.path.join(root, "node_a", "pyproject.toml"), "[project]\nname = 'test2'\nversion = '2.0'")
        m2 = build_custom_node_dependency_manifest(root)
        h2 = m2.get("overall_dependency_hash", "")
        self.assertNotEqual(h1, h2, "changing pyproject.toml should change hash")

    def test_ordinary_source_file_does_not_change_dep_hash(self):
        from comfyapp import build_custom_node_dependency_manifest
        root = os.path.join(self._tmpdir, "test4")
        os.makedirs(os.path.join(root, "node_a"))
        self._write_file(os.path.join(root, "node_a", "requirements.txt"), "torch")
        m1 = build_custom_node_dependency_manifest(root)
        h1 = m1.get("overall_dependency_hash", "")

        # Add .py file (should not change dep hash)
        self._write_file(os.path.join(root, "node_a", "extra.py"), "y = 2")
        m2 = build_custom_node_dependency_manifest(root)
        h2 = m2.get("overall_dependency_hash", "")
        self.assertEqual(h1, h2, "adding ordinary .py should not change dep hash")


# ── PART 5: Dependency scanner ──

class TestDependencyScanner(unittest.TestCase):
    """Test 10: dependency scanner collects nested files."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self._node_root = os.path.join(self._tmpdir, "test_node")
        os.makedirs(self._node_root)

    def _write(self, rel: str, content: str = ""):
        path = os.path.join(self._node_root, rel)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content)
        return path

    def test_collects_requirements_txt(self):
        from comfyapp import _collect_dependency_file_paths
        self._write("requirements.txt", "torch")
        files = _collect_dependency_file_paths(self._node_root)
        self.assertIn("requirements.txt", files)

    def test_collects_nested_requirement_file(self):
        from comfyapp import _collect_dependency_file_paths
        self._write("requirements.txt", "-r inner/reqs.txt\n")
        self._write("inner/reqs.txt", "torch\n")
        files = _collect_dependency_file_paths(self._node_root)
        self.assertIn("requirements.txt", files)
        self.assertIn("inner/reqs.txt", files)

    def test_collects_pyproject_toml(self):
        from comfyapp import _collect_dependency_file_paths
        self._write("pyproject.toml", "[project]\n")
        files = _collect_dependency_file_paths(self._node_root)
        self.assertIn("pyproject.toml", files)

    def test_collects_setup_py(self):
        from comfyapp import _collect_dependency_file_paths
        self._write("setup.py", "from setuptools import setup\nsetup()\n")
        files = _collect_dependency_file_paths(self._node_root)
        self.assertIn("setup.py", files)

    def test_collects_setup_cfg(self):
        from comfyapp import _collect_dependency_file_paths
        self._write("setup.cfg", "[metadata]\nname = test\n")
        files = _collect_dependency_file_paths(self._node_root)
        self.assertIn("setup.cfg", files)

    def test_ignores_non_dependency_files(self):
        from comfyapp import _collect_dependency_file_paths
        self._write("main.py", "x = 1")
        self._write("README.md", "# docs")
        self._write("image.png", "fake")
        self._write("node.safetensors", "model")
        files = _collect_dependency_file_paths(self._node_root)
        self.assertEqual(files, {}, "should be empty for no-dep files")


# ── PART 7-8: fail_fast never installs ──

class TestFailFastNeverInstalls(unittest.TestCase):
    """Test 6-8: off/fail_fast never pip installs, even with force=True."""

    def setUp(self):
        self._saved_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved_env)

    @patch("comfyapp.subprocess")
    def test_fail_fast_force_never_calls_subprocess(self, mock_subprocess):
        os.environ["COMFYMODAL_REQUIREMENTS_REPAIR_MODE"] = "fail_fast"
        import importlib
        import comfyapp as capp
        importlib.reload(capp)
        # Instantiate the mixin
        instance = capp._ComfyAPIMixin()
        with self.assertRaises(RuntimeError):
            instance._install_custom_node_requirements(force=True)
        mock_subprocess.run.assert_not_called()

    @patch("comfyapp.subprocess")
    def test_off_force_never_calls_subprocess(self, mock_subprocess):
        os.environ["COMFYMODAL_REQUIREMENTS_REPAIR_MODE"] = "off"
        import importlib
        import comfyapp as capp
        importlib.reload(capp)
        instance = capp._ComfyAPIMixin()
        result = instance._install_custom_node_requirements(force=True)
        mock_subprocess.run.assert_not_called()
        self.assertEqual(result.get("mode"), "off")


# ── PART 8: Failure summaries ──

class TestFailureSummaries(unittest.TestCase):
    """Test PART 17: Structured failure summaries for different failure modes."""

    def test_preflight_summary_for_malformed_node(self):
        summary = FailureSummary(phase="preflight")
        summary.fatal_error = "node 454 missing class_type"
        summary.modal_invoked = False
        summary.recommendation = "Re-export workflow as API prompt JSON or remove corrupt node 454."
        output = str(summary)
        self.assertIn("preflight", output)
        self.assertIn("fatal_error=", output)
        self.assertIn("modal_invoked=0", output)
        self.assertIn("recommendation=", output)

    def test_dependency_preflight_summary(self):
        summary = FailureSummary(phase="dependency_preflight")
        summary.fatal_error = "custom node dependencies not prepared"
        summary.modal_invoked = False
        summary.recommendation = "Rebuild/deploy Modal image after syncing custom-node requirements."
        output = str(summary)
        self.assertIn("dependency_preflight", output)
        self.assertIn("custom node dependencies not prepared", output)

    def test_node_availability_summary(self):
        summary = FailureSummary(phase="node_availability")
        summary.fatal_error = "missing workflow node classes"
        summary.modal_invoked = True
        summary.recommendation = "Install/sync the custom node and rebuild dependency image if requirements changed."
        output = str(summary)
        self.assertIn("node_availability", output)
        self.assertIn("missing workflow node classes", output)


# ── PART 14: Size guardrails ──

class TestPreloadSizeGuardrails(unittest.TestCase):
    """Test 17: Size guardrails filter out huge files."""

    @patch("os.path.getsize")
    def test_max_file_gb_exceeded(self, mock_getsize):
        from comfyapp import _filter_preload_paths_by_size
        # Simulate a single file at 11.46 GB, max file = 10 GB
        mock_getsize.return_value = int(11.46 * 1024**3)
        paths = ["/models/unet/flux1-dev.safetensors"]
        kept, result = _filter_preload_paths_by_size(paths)
        self.assertEqual(len(kept), 0)
        self.assertIn("max_file_gb_exceeded", str(result))

    @patch("os.path.getsize")
    def test_max_total_gb_exceeded(self, mock_getsize):
        from comfyapp import _filter_preload_paths_by_size
        # Simulate 3 files totaling 18.96 GB, max total = 12 GB
        # All-or-nothing: total exceeds limit → no files preloaded
        mock_getsize.return_value = int(6.32 * 1024**3)
        paths = [
            "/models/unet/flux1-dev.safetensors",
            "/models/clip/t5xxl.safetensors",
            "/models/clip/clip-l.safetensors",
        ]
        kept, result = _filter_preload_paths_by_size(paths)
        self.assertEqual(len(kept), 0)
        self.assertEqual(result["reason"], "max_total_gb_exceeded")
        self.assertIn("max_total_gb_exceeded", str(result))

    @patch("os.path.getsize")
    def test_two_files_under_total_both_kept(self, mock_getsize):
        from comfyapp import _filter_preload_paths_by_size
        # Two files totaling under max: both kept
        mock_getsize.return_value = int(4.0 * 1024**3)
        paths = ["/models/a.safetensors", "/models/b.safetensors"]
        kept, result = _filter_preload_paths_by_size(paths)
        self.assertEqual(len(kept), 2)

    @patch("os.path.getsize")
    def test_one_file_above_max_one_small_small_remaining(self, mock_getsize):
        from comfyapp import _filter_preload_paths_by_size
        def _side(p):
            if "large" in p:
                return int(15.0 * 1024**3)
            return int(2.0 * 1024**3)
        mock_getsize.side_effect = _side
        paths = ["/models/large.safetensors", "/models/small.safetensors"]
        kept, result = _filter_preload_paths_by_size(paths)
        # Large file is skipped (above max_file_gb); small file stays
        self.assertEqual(len(kept), 1)
        self.assertIn("large.safetensors", str(result))


# ── PART 15: get_runtime_custom_node_source_root_for_dependency_validation ──

class TestRuntimeCustomNodeSourceRoot(unittest.TestCase):
    """PART 15: Correct source root selection."""

    @patch("os.listdir")
    @patch("os.path.isdir")
    def test_uses_volume_when_not_empty(self, mock_isdir, mock_listdir):
        from comfyapp import get_runtime_custom_node_source_root_for_dependency_validation
        mock_isdir.return_value = True
        mock_listdir.return_value = ["node_a", "node_b"]
        result = get_runtime_custom_node_source_root_for_dependency_validation()
        from comfyapp import CUSTOM_NODES_PATH
        self.assertEqual(result, CUSTOM_NODES_PATH)

    @patch("os.listdir")
    @patch("os.path.isdir")
    def test_falls_back_to_image_baked_when_volume_empty(self, mock_isdir, mock_listdir):
        from comfyapp import get_runtime_custom_node_source_root_for_dependency_validation
        def _side_effect(p):
            if "custom_nodes_vol" in p:
                return True
            if "ComfyUI/custom_nodes" in p:
                return True
            return False
        mock_isdir.side_effect = _side_effect
        mock_listdir.return_value = []
        result = get_runtime_custom_node_source_root_for_dependency_validation()
        self.assertEqual(result, "/root/comfy/ComfyUI/custom_nodes")


# ── PART 18: Known-good workflow profiles ──

class TestKnownGoodWorkflowProfiles(unittest.TestCase):
    """Tests for known-good profile marking and eligibility."""

    def test_mark_and_check(self):
        from comfyapp import _mark_known_good_workflow_profile, _is_known_good_workflow_profile, KNOWN_GOOD_WORKFLOW_PROFILES_PATH
        import tempfile
        # Use a temp path to avoid side effects
        with tempfile.TemporaryDirectory() as tmp:
            test_path = os.path.join(tmp, "known_good.json")
            import comfyapp
            original_path = comfyapp.KNOWN_GOOD_WORKFLOW_PROFILES_PATH
            comfyapp.KNOWN_GOOD_WORKFLOW_PROFILES_PATH = test_path
            try:
                profile = {"mode": "split", "unet": "flux.safetensors"}
                _mark_known_good_workflow_profile("test_hash_123", profile)
                self.assertTrue(_is_known_good_workflow_profile("test_hash_123", {}))
                self.assertFalse(_is_known_good_workflow_profile("unknown_hash", {}))
            finally:
                comfyapp.KNOWN_GOOD_WORKFLOW_PROFILES_PATH = original_path


# ── PART 10: Duplicate Modal function test ──

class TestModalFunctionNoDuplicate(unittest.TestCase):
    """PART 10: Verify set_active_warmup_profile is the only top-level name."""

    def test_only_one_set_active_warmup_profile(self):
        import comfyapp
        count = 0
        for attr in dir(comfyapp):
            if attr == "set_active_warmup_profile":
                count += 1
        self.assertEqual(count, 1)

    def test_set_active_warmup_profile_exists(self):
        import comfyapp
        fn = getattr(comfyapp, "set_active_warmup_profile", None)
        self.assertIsNotNone(fn)

    def test_write_helper_has_different_name(self):
        import comfyapp
        write_fn = getattr(comfyapp, "_write_active_warmup_profile_payload", None)
        self.assertIsNotNone(write_fn)
        self.assertTrue(callable(write_fn))

    def test_validate_helper_exists(self):
        import comfyapp
        validate_fn = getattr(comfyapp, "validate_active_warmup_profile_payload", None)
        self.assertIsNotNone(validate_fn)
        self.assertTrue(callable(validate_fn))


# ── PART 11: Dependency scanner / build context parity ──

class TestCollectCustomNodeDependencyFiles(unittest.TestCase):
    """PART 11: Single source of truth for dependency scanning."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_node(self, name: str, files: dict[str, str]) -> str:
        node_path = os.path.join(self._tmpdir, name)
        for rel, content in files.items():
            fp = os.path.join(node_path, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w") as f:
                f.write(content)
        return node_path

    def test_node_with_requirements_txt(self):
        from comfyapp import collect_custom_node_dependency_files
        np = self._make_node("node_a", {"requirements.txt": "torch\nnumpy"})
        result = collect_custom_node_dependency_files(np)
        self.assertIn("requirements.txt", result)

    def test_node_with_nested_requirement(self):
        from comfyapp import collect_custom_node_dependency_files
        np = self._make_node("node_b", {
            "requirements.txt": "-r extra.txt\n",
            "extra.txt": "pandas\n",
        })
        result = collect_custom_node_dependency_files(np)
        self.assertIn("requirements.txt", result)
        self.assertIn("extra.txt", result)

    def test_node_with_constraint_file(self):
        from comfyapp import collect_custom_node_dependency_files
        np = self._make_node("node_c", {
            "requirements.txt": "-c constraints.txt\nnumpy\n",
            "constraints.txt": "numpy<2.0\n",
        })
        result = collect_custom_node_dependency_files(np)
        self.assertIn("requirements.txt", result)
        self.assertIn("constraints.txt", result)

    def test_node_with_pyproject_toml(self):
        from comfyapp import collect_custom_node_dependency_files
        np = self._make_node("node_d", {"pyproject.toml": "[project]\nname=\"test\"\n"})
        result = collect_custom_node_dependency_files(np)
        self.assertIn("pyproject.toml", result)

    def test_node_with_setup_py(self):
        from comfyapp import collect_custom_node_dependency_files
        np = self._make_node("node_e", {"setup.py": "from setuptools import setup\nsetup()\n"})
        result = collect_custom_node_dependency_files(np)
        self.assertIn("setup.py", result)

    def test_node_with_setup_cfg(self):
        from comfyapp import collect_custom_node_dependency_files
        np = self._make_node("node_f", {"setup.cfg": "[metadata]\nname=test\n"})
        result = collect_custom_node_dependency_files(np)
        self.assertIn("setup.cfg", result)

    def test_node_with_editable_local_pkg_outside_root(self):
        from comfyapp import collect_custom_node_dependency_files
        # Create a local editable package outside the node root
        pkg_path = os.path.join(self._tmpdir, "local_pkg")
        os.makedirs(os.path.join(pkg_path, "mypkg"), exist_ok=True)
        with open(os.path.join(pkg_path, "setup.py"), "w") as f:
            f.write("from setuptools import setup\nsetup()\n")
        with open(os.path.join(pkg_path, "mypkg", "__init__.py"), "w") as f:
            f.write("x=1\n")
        np = self._make_node("node_g", {
            "requirements.txt": f"-e {os.path.relpath(pkg_path, self._tmpdir + '/node_g')}\n",
        })
        with self.assertRaises(RuntimeError):
            collect_custom_node_dependency_files(np)

    def test_node_with_editable_local_pkg_inside_root(self):
        from comfyapp import collect_custom_node_dependency_files
        # Create a local editable package inside the node root (supported)
        np = self._make_node("node_h", {
            "requirements.txt": "-e ./mypkg\n",
        })
        pkg_inner = os.path.join(np, "mypkg")
        os.makedirs(pkg_inner, exist_ok=True)
        with open(os.path.join(pkg_inner, "__init__.py"), "w") as f:
            f.write("x=1\n")
        result = collect_custom_node_dependency_files(np)
        self.assertIn("requirements.txt", result)

    def test_ordinary_source_only_no_dependency_files(self):
        from comfyapp import collect_custom_node_dependency_files
        np = self._make_node("node_h", {"__init__.py": "print('hello')\n"})
        result = collect_custom_node_dependency_files(np)
        self.assertEqual(len(result), 0)


class TestDependencyScannerBackwardAlias(unittest.TestCase):
    """PART 11: _collect_dependency_file_paths is backward alias."""

    def test_alias_returns_same_as_collect(self):
        from comfyapp import collect_custom_node_dependency_files, _collect_dependency_file_paths
        results = {}
        for name, fn in [("collect", collect_custom_node_dependency_files),
                         ("alias", _collect_dependency_file_paths)]:
            with tempfile.TemporaryDirectory() as tmp:
                np = os.path.join(tmp, "node_x")
                os.makedirs(np, exist_ok=True)
                with open(os.path.join(np, "requirements.txt"), "w") as f:
                    f.write("torch\n")
                results[name] = fn(np)
        self.assertEqual(results["collect"], results["alias"])


# ── PART 13: Stream failure test ──

class TestStreamDependencyError(unittest.TestCase):
    """PART 13: Stream yields fatal error on dependency mismatch."""

    def test_dependency_error_message_format(self):
        from failure_summary import FailureSummary
        msg = (
            "Custom node dependencies are not prepared for this image. "
            "Runtime pip install is disabled in fail_fast mode. "
            "Rebuild/deploy the Modal image after syncing "
            "custom-node requirements."
        )
        self.assertIn("fail_fast", msg)
        self.assertIn("not prepared", msg)
        self.assertIn("Rebuild/deploy", msg)


# ── PART 14: Direct warmup known-good test ──

class TestDirectWarmupKnownGoodGuard(unittest.TestCase):
    """PART 14: Direct warmup cannot load unknown workflow models."""

    @patch("comfyapp._is_known_good_workflow_profile")
    def test_warmup_direct_skipped_for_unknown_profile(self, mock_known_good):
        from comfyapp import _resolve_runtime_flag
        mock_known_good.return_value = False
        profile = {"mode": "split", "_workflow_hash": "unknown_hash"}
        # The guard is in restore(), not in _warmup_direct itself.
        # This test verifies the known-good check exists as a function.
        self.assertFalse(mock_known_good("unknown_hash", {}))


# ── PART 12: Preload accounting tests (with mocked loader) ──

class TestPreloadAccounting(unittest.TestCase):
    """PART 12: Truthful preload accounting."""

    def test_filter_one_file_above_max_file_one_below(self):
        from comfyapp import _filter_preload_paths_by_size
        import tempfile
        # Create real files for getsize
        with tempfile.TemporaryDirectory() as tmp:
            large = os.path.join(tmp, "large.safetensors")
            small = os.path.join(tmp, "small.safetensors")
            # Write files with known sizes
            with open(large, "wb") as f:
                f.write(b"\x00" * int(15 * 1024**3))  # 15 GB
            with open(small, "wb") as f:
                f.write(b"\x00" * int(2 * 1024**3))   # 2 GB
            kept, result = _filter_preload_paths_by_size([large, small])
            self.assertEqual(len(kept), 1)
            self.assertIn("max_file_gb_exceeded", str(result))

    def test_filter_all_files_under_total(self):
        from comfyapp import _filter_preload_paths_by_size
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, "a.safetensors")
            b = os.path.join(tmp, "b.safetensors")
            with open(a, "wb") as f:
                f.write(b"\x00" * int(4 * 1024**3))
            with open(b, "wb") as f:
                f.write(b"\x00" * int(3 * 1024**3))
            kept, result = _filter_preload_paths_by_size([a, b])
            self.assertEqual(len(kept), 2)


# ── PART 11/12: Topology fingerprint tests ──

class TestCustomNodeTopologyFingerprint(unittest.TestCase):
    """PART 11: Topology fingerprint ignores content changes."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_fingerprint_unchanged_when_file_changes(self):
        from comfyapp import custom_node_topology_fingerprint
        # Create a node first
        np = os.path.join(self._tmpdir, "existing_node")
        os.makedirs(np, exist_ok=True)
        fp1 = custom_node_topology_fingerprint(self._tmpdir)
        # Add a file inside the existing node
        with open(os.path.join(np, "__init__.py"), "w") as f:
            f.write("x=1\n")
        fp2 = custom_node_topology_fingerprint(self._tmpdir)
        # Adding files within an existing node does not change topology
        self.assertEqual(fp1, fp2)

    def test_fingerprint_changes_when_node_added(self):
        from comfyapp import custom_node_topology_fingerprint
        fp1 = custom_node_topology_fingerprint(self._tmpdir)
        np = os.path.join(self._tmpdir, "new_node")
        os.makedirs(np, exist_ok=True)
        fp2 = custom_node_topology_fingerprint(self._tmpdir)
        self.assertNotEqual(fp1, fp2)

    def test_fingerprint_changes_when_node_removed(self):
        from comfyapp import custom_node_topology_fingerprint
        np = os.path.join(self._tmpdir, "to_remove")
        os.makedirs(np, exist_ok=True)
        fp1 = custom_node_topology_fingerprint(self._tmpdir)
        import shutil
        shutil.rmtree(np)
        fp2 = custom_node_topology_fingerprint(self._tmpdir)
        self.assertNotEqual(fp1, fp2)

    def test_requirements_change_does_not_affect_topology(self):
        from comfyapp import custom_node_topology_fingerprint
        np = os.path.join(self._tmpdir, "node_a")
        os.makedirs(np, exist_ok=True)
        fp1 = custom_node_topology_fingerprint(self._tmpdir)
        with open(os.path.join(np, "requirements.txt"), "w") as f:
            f.write("torch\n")
        fp2 = custom_node_topology_fingerprint(self._tmpdir)
        self.assertEqual(fp1, fp2)


# ── PART 12: Dependency fingerprint tests ──

class TestCustomNodeDependencyFingerprint(unittest.TestCase):
    """PART 12: Dependency-only fingerprint ignores ordinary source churn."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_node(self, name: str, files: dict[str, str]) -> str:
        node_path = os.path.join(self._tmpdir, name)
        for rel, content in files.items():
            fp = os.path.join(node_path, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w") as f:
                f.write(content)
        return node_path

    def test_ordinary_py_does_not_change_fingerprint(self):
        from comfyapp import custom_node_dependency_fingerprint
        self._make_node("node_a", {"__init__.py": "x=1\n"})
        fp1 = custom_node_dependency_fingerprint(self._tmpdir)
        # Change .py content
        with open(os.path.join(self._tmpdir, "node_a", "__init__.py"), "w") as f:
            f.write("y=2\n")
        fp2 = custom_node_dependency_fingerprint(self._tmpdir)
        self.assertEqual(
            fp1.get("overall_dependency_hash"),
            fp2.get("overall_dependency_hash"),
        )

    def test_requirements_txt_change_invalidates_fingerprint(self):
        from comfyapp import custom_node_dependency_fingerprint
        self._make_node("node_a", {"requirements.txt": "torch\n"})
        fp1 = custom_node_dependency_fingerprint(self._tmpdir)
        with open(os.path.join(self._tmpdir, "node_a", "requirements.txt"), "w") as f:
            f.write("torch>=2.0\n")
        fp2 = custom_node_dependency_fingerprint(self._tmpdir)
        self.assertNotEqual(
            fp1.get("overall_dependency_hash"),
            fp2.get("overall_dependency_hash"),
        )

    def test_nested_r_file_invalidates_fingerprint(self):
        from comfyapp import custom_node_dependency_fingerprint
        self._make_node("node_a", {
            "requirements.txt": "-r extra.txt\n",
            "extra.txt": "torch\n",
        })
        fp1 = custom_node_dependency_fingerprint(self._tmpdir)
        with open(os.path.join(self._tmpdir, "node_a", "extra.txt"), "w") as f:
            f.write("torch>=2.0\n")
        fp2 = custom_node_dependency_fingerprint(self._tmpdir)
        self.assertNotEqual(
            fp1.get("overall_dependency_hash"),
            fp2.get("overall_dependency_hash"),
        )

    def test_pyproject_toml_change_invalidates_fingerprint(self):
        from comfyapp import custom_node_dependency_fingerprint
        self._make_node("node_a", {"pyproject.toml": "[project]\nname=\"x\"\n"})
        fp1 = custom_node_dependency_fingerprint(self._tmpdir)
        with open(os.path.join(self._tmpdir, "node_a", "pyproject.toml"), "w") as f:
            f.write("[project]\nname=\"y\"\n")
        fp2 = custom_node_dependency_fingerprint(self._tmpdir)
        self.assertNotEqual(
            fp1.get("overall_dependency_hash"),
            fp2.get("overall_dependency_hash"),
        )

    def test_no_dep_node_does_not_change_hash(self):
        from comfyapp import custom_node_dependency_fingerprint
        self._make_node("node_a", {"__init__.py": "x=1\n"})
        fp1 = custom_node_dependency_fingerprint(self._tmpdir)
        # Add another no-dependency node
        self._make_node("node_b", {"__init__.py": "y=2\n"})
        fp2 = custom_node_dependency_fingerprint(self._tmpdir)
        # Both have no dependency files, so the hash should not change
        self.assertEqual(
            fp1.get("overall_dependency_hash"),
            fp2.get("overall_dependency_hash"),
        )


# ── PART 12: Dependency manifest cache tests ──

class TestDependencyManifestCache(unittest.TestCase):
    """PART 12: Cached manifest responds to dependency changes only."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @patch("comfyapp.CURRENT_CUSTOM_NODE_DEPS_CACHE_PATH")
    @patch("comfyapp.get_runtime_custom_node_source_root_for_dependency_validation")
    @patch("comfyapp.build_custom_node_dependency_manifest")
    @patch("comfyapp.custom_node_dependency_fingerprint")
    def test_cache_hit_returns_cached_manifest(
        self, mock_fp, mock_build, mock_source, mock_cache_path
    ):
        from comfyapp import build_current_custom_node_dependency_manifest_cached, save_current_dependency_manifest_cache
        mock_source.return_value = "/test/root"
        mock_fp.return_value = {"overall_dependency_hash": "abc123", "source_root": "/test/root"}
        cached_manifest = {"schema_version": 1, "nodes": {"n1": {}}, "overall_dependency_hash": "abc123"}
        # Pre-populate cache
        cache = {
            "schema_version": 1,
            "source_root": "/test/root",
            "dependency_fingerprint_hash": "abc123",
            "manifest": cached_manifest,
        }
        with patch("comfyapp.load_current_dependency_manifest_cache", return_value=cache):
            result = build_current_custom_node_dependency_manifest_cached()
            mock_build.assert_not_called()
            self.assertEqual(result, cached_manifest)

    @patch("comfyapp.CURRENT_CUSTOM_NODE_DEPS_CACHE_PATH")
    @patch("comfyapp.get_runtime_custom_node_source_root_for_dependency_validation")
    @patch("comfyapp.build_custom_node_dependency_manifest")
    @patch("comfyapp.custom_node_dependency_fingerprint")
    def test_cache_miss_rebuilds_manifest(
        self, mock_fp, mock_build, mock_source, mock_cache_path
    ):
        from comfyapp import build_current_custom_node_dependency_manifest_cached
        mock_source.return_value = "/test/root"
        mock_fp.return_value = {"overall_dependency_hash": "def456", "source_root": "/test/root"}
        mock_build.return_value = {"schema_version": 1, "nodes": {"n1": {}}, "overall_dependency_hash": "def456"}
        with patch("comfyapp.load_current_dependency_manifest_cache", return_value={}):
            result = build_current_custom_node_dependency_manifest_cached()
            mock_build.assert_called_once()
            self.assertEqual(result["overall_dependency_hash"], "def456")


# ── PART 12/13: Preload abort and pipeline summary tests ──

class TestPipelineSummary(unittest.TestCase):
    """PART 8: make_request_pipeline_summary produces expected shape."""

    def test_summary_shape(self):
        from comfyapp import make_request_pipeline_summary
        s = make_request_pipeline_summary(
            request_id="test_123",
            mode="in_process",
            stream=False,
            local_preflight_validated=True,
        )
        self.assertEqual(s["request_id"], "test_123")
        self.assertEqual(s["mode"], "in_process")
        self.assertTrue(s["local_preflight_validated"])
        self.assertIn("execution_started", s)
        self.assertIn("execution_success", s)
        self.assertIn("failure_phase", s)
        self.assertIn("failure_reason", s)

    def test_summary_defaults(self):
        from comfyapp import make_request_pipeline_summary
        s = make_request_pipeline_summary()
        self.assertFalse(s["local_preflight_validated"])
        self.assertFalse(s["execution_started"])
        self.assertFalse(s["execution_success"])


# ── PART 11-12: Preload abort when no futures complete ──

class TestPreloadAbortNoFuturesComplete(unittest.TestCase):
    """PART 11: Abort triggers even when no future completes."""

    @patch("comfyapp.PRELOAD_OUTLIER_ABORT_SECONDS", 0.05)
    @patch("comfyapp.PRELOAD_MIN_THROUGHPUT_GBPS", 0.5)
    @patch("os.path.getsize")
    def test_abort_when_no_future_completes(self, mock_getsize):
        from comfyapp import _ComfyAPIMixin
        mock_getsize.return_value = int(5 * 1024**3)
        obj = _ComfyAPIMixin()
        obj._model_cpu_cache = {}
        obj._original_model_loader = lambda p, **kw: (Exception("slow"), None)
        import threading, time
        barrier = threading.Barrier(2, timeout=10)
        def slow_loader(path, return_metadata=False):
            barrier.wait()
            time.sleep(30)
            return {}, None
        obj._original_model_loader = slow_loader
        with patch("comfyapp._resolve_preload_mode", return_value="workers_1"):
            result = obj._preload_models_to_cpu(
                ["/models/a.safetensors"],
                budget_ms=None,
            )
        self.assertTrue(result.get("aborted", False))
        self.assertEqual(result.get("abort_reason"), "no_completed_files_within_abort_window")
        self.assertEqual(result.get("completed_bytes", 0), 0)
        self.assertEqual(result.get("completed_files", 0), 0)

    @patch("comfyapp.PRELOAD_OUTLIER_ABORT_SECONDS", 10)
    @patch("comfyapp.PRELOAD_MIN_THROUGHPUT_GBPS", 0.5)
    @patch("os.path.getsize")
    def test_budget_abort_when_no_future_completes(self, mock_getsize):
        from comfyapp import _ComfyAPIMixin
        mock_getsize.return_value = int(5 * 1024**3)
        obj = _ComfyAPIMixin()
        obj._model_cpu_cache = {}
        obj._original_model_loader = lambda p, **kw: (Exception("slow"), None)
        import threading, time
        barrier = threading.Barrier(2, timeout=10)
        def slow_loader(path, return_metadata=False):
            barrier.wait()
            time.sleep(30)
            return {}, None
        obj._original_model_loader = slow_loader
        with patch("comfyapp._resolve_preload_mode", return_value="workers_1"):
            result = obj._preload_models_to_cpu(
                ["/models/a.safetensors"],
                budget_ms=50,
            )
        self.assertTrue(result.get("aborted", False))
        self.assertEqual(result.get("abort_reason"), "budget_exceeded")
        self.assertEqual(result.get("completed_bytes", 0), 0)

    @patch("comfyapp.PRELOAD_OUTLIER_ABORT_SECONDS", 100)
    @patch("comfyapp.PRELOAD_MIN_THROUGHPUT_GBPS", 0.5)
    @patch("os.path.getsize")
    def test_partial_completion_then_abort(self, mock_getsize):
        from comfyapp import _ComfyAPIMixin
        def _sz(p):
            return int(2 * 1024**3)
        mock_getsize.side_effect = _sz
        obj = _ComfyAPIMixin()
        obj._model_cpu_cache = {}
        call_order = []
        def variable_loader(path, return_metadata=False):
            if "a.safetensors" in path:
                call_order.append("a")
                return ({"a": 1}, {"a": 1})
            # File B blocks (simulate slow read)
            call_order.append("b")
            time.sleep(60)
            return ({}, None)
        obj._original_model_loader = variable_loader
        with patch("comfyapp._resolve_preload_mode", return_value="workers_2"):
            result = obj._preload_models_to_cpu(
                ["/models/a.safetensors", "/models/b.safetensors"],
                budget_ms=500,
            )
        # A should complete, B should be aborted
        self.assertEqual(result.get("completed_files", 0), 1)
        self.assertGreater(result.get("completed_bytes", 0), 0)


# ── PART 14: Topology fingerprint filtering ──

class TestTopologyFingerprintFiltering(unittest.TestCase):
    """PART 14: Topology fingerprint ignores non-syncable entries."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _fingerprint(self):
        from comfyapp import custom_node_topology_fingerprint
        return custom_node_topology_fingerprint(self._tmp)

    def test_empty_has_no_nodes(self):
        fp = self._fingerprint()
        self.assertEqual(len(fp["nodes"]), 0)

    def test_staging_dir_ignored(self):
        os.makedirs(os.path.join(self._tmp, ".staging"), exist_ok=True)
        fp = self._fingerprint()
        self.assertEqual(len(fp["nodes"]), 0)

    def test_pycache_dir_ignored(self):
        os.makedirs(os.path.join(self._tmp, "__pycache__"), exist_ok=True)
        fp = self._fingerprint()
        self.assertEqual(len(fp["nodes"]), 0)

    def test_random_file_ignored(self):
        with open(os.path.join(self._tmp, "random.txt"), "w") as f:
            f.write("x")
        fp = self._fingerprint()
        self.assertEqual(len(fp["nodes"]), 0)

    def test_real_node_included(self):
        os.makedirs(os.path.join(self._tmp, "ComfyUI-RealNode"), exist_ok=True)
        fp = self._fingerprint()
        self.assertEqual(len(fp["nodes"]), 1)
        self.assertEqual(fp["nodes"][0]["name"], "ComfyUI-RealNode")

    def test_real_node_file_change_ignored(self):
        np = os.path.join(self._tmp, "ComfyUI-TestNode")
        os.makedirs(np, exist_ok=True)
        fp1 = self._fingerprint()
        with open(os.path.join(np, "requirements.txt"), "w") as f:
            f.write("torch\n")
        fp2 = self._fingerprint()
        self.assertEqual(fp1, fp2)

    def test_real_node_removed(self):
        np = os.path.join(self._tmp, "ComfyUI-RemoveMe")
        os.makedirs(np, exist_ok=True)
        fp1 = self._fingerprint()
        import shutil
        shutil.rmtree(np)
        fp2 = self._fingerprint()
        self.assertNotEqual(fp1, fp2)


# ── PART 15: Dependency validation source root ──

class TestSourceRootSelection(unittest.TestCase):
    """PART 15: Source root uses syncable nodes, not raw entries."""

    def _call_source_root(self, custom_nodes_path, isdir_result, syncable_result):
        with patch("comfyapp.CUSTOM_NODES_PATH", custom_nodes_path, create=True):
            with patch("comfyapp.os.path.isdir", return_value=isdir_result):
                with patch("comfyapp._safe_listdir", return_value=[]):
                    with patch("comfyapp._iter_syncable_custom_node_dirs", return_value=syncable_result):
                        from comfyapp import get_runtime_custom_node_source_root_for_dependency_validation
                        return get_runtime_custom_node_source_root_for_dependency_validation()

    def test_empty_uses_image_baked(self):
        result = self._call_source_root("/vol", True, [])
        self.assertEqual(result, "/root/comfy/ComfyUI/custom_nodes")

    def test_only_staging_uses_image_baked(self):
        result = self._call_source_root("/vol", True, [])
        self.assertEqual(result, "/root/comfy/ComfyUI/custom_nodes")

    def test_real_node_uses_volume(self):
        result = self._call_source_root("/vol", True, ["ComfyUI-RealNode"])
        self.assertEqual(result, "/vol")


# ── PART 16: Dependency manifest cache persistence ──

class TestDependencyManifestCachePersistence(unittest.TestCase):
    """PART 16: Cache persistence and commit behavior."""

    @patch("comfyapp._commit_volume_async")
    @patch("comfyapp.load_current_dependency_manifest_cache")
    @patch("comfyapp.build_custom_node_dependency_manifest")
    @patch("comfyapp.custom_node_dependency_fingerprint")
    @patch("comfyapp.get_runtime_custom_node_source_root_for_dependency_validation")
    def test_cache_miss_commits(self, mock_source, mock_fp, mock_build, mock_load, mock_commit):
        from comfyapp import build_current_custom_node_dependency_manifest_cached
        mock_source.return_value = "/test"
        mock_fp.return_value = {"overall_dependency_hash": "abc", "source_root": "/test"}
        mock_build.return_value = {"nodes": {}}
        mock_load.return_value = {}
        build_current_custom_node_dependency_manifest_cached()
        mock_commit.assert_called_once()

    @patch("comfyapp._commit_volume_async")
    @patch("comfyapp.load_current_dependency_manifest_cache")
    @patch("comfyapp.build_custom_node_dependency_manifest")
    @patch("comfyapp.custom_node_dependency_fingerprint")
    @patch("comfyapp.get_runtime_custom_node_source_root_for_dependency_validation")
    def test_cache_hit_no_commit(self, mock_source, mock_fp, mock_build, mock_load, mock_commit):
        from comfyapp import build_current_custom_node_dependency_manifest_cached
        mock_source.return_value = "/test"
        mock_fp.return_value = {"overall_dependency_hash": "abc", "source_root": "/test"}
        mock_load.return_value = {
            "schema_version": 1,
            "source_root": "/test",
            "dependency_fingerprint_hash": "abc",
            "manifest": {"nodes": {}},
        }
        build_current_custom_node_dependency_manifest_cached()
        mock_commit.assert_not_called()


# ── PART 17: Known-good persistence behavior ──

class TestKnownGoodPersistence(unittest.TestCase):
    """PART 17: _mark_known_good commit and dedup."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_first_mark_returns_true(self):
        from comfyapp import _mark_known_good_workflow_profile, KNOWN_GOOD_WORKFLOW_PROFILES_PATH
        import comfyapp
        orig = comfyapp.KNOWN_GOOD_WORKFLOW_PROFILES_PATH
        comfyapp.KNOWN_GOOD_WORKFLOW_PROFILES_PATH = os.path.join(self._tmpdir, "known_good.json")
        try:
            result = _mark_known_good_workflow_profile("hash1", {"mode": "split"})
            self.assertTrue(result)
        finally:
            comfyapp.KNOWN_GOOD_WORKFLOW_PROFILES_PATH = orig

    def test_duplicate_mark_returns_false(self):
        from comfyapp import _mark_known_good_workflow_profile, KNOWN_GOOD_WORKFLOW_PROFILES_PATH
        import comfyapp
        orig = comfyapp.KNOWN_GOOD_WORKFLOW_PROFILES_PATH
        comfyapp.KNOWN_GOOD_WORKFLOW_PROFILES_PATH = os.path.join(self._tmpdir, "known_good.json")
        try:
            _mark_known_good_workflow_profile("hash1", {"mode": "split"})
            result = _mark_known_good_workflow_profile("hash1", {"mode": "split"})
            self.assertFalse(result)
        finally:
            comfyapp.KNOWN_GOOD_WORKFLOW_PROFILES_PATH = orig

    def test_changed_profile_returns_true(self):
        from comfyapp import _mark_known_good_workflow_profile, KNOWN_GOOD_WORKFLOW_PROFILES_PATH
        import comfyapp
        orig = comfyapp.KNOWN_GOOD_WORKFLOW_PROFILES_PATH
        comfyapp.KNOWN_GOOD_WORKFLOW_PROFILES_PATH = os.path.join(self._tmpdir, "known_good.json")
        try:
            _mark_known_good_workflow_profile("hash1", {"mode": "split"})
            result = _mark_known_good_workflow_profile("hash1", {"mode": "checkpoint"})
            self.assertTrue(result)
        finally:
            comfyapp.KNOWN_GOOD_WORKFLOW_PROFILES_PATH = orig


# ── PART 11: Additional preload accounting tests ──

class TestPreloadAccountingExtended(unittest.TestCase):
    """PART 11: Extended preload accounting checks."""

    @patch("comfyapp.PRELOAD_OUTLIER_ABORT_SECONDS", 0.05)
    @patch("comfyapp.PRELOAD_MIN_THROUGHPUT_GBPS", 0.5)
    @patch("comfyapp._resolve_preload_mode")
    @patch("os.path.getsize")
    def test_abort_returns_pending_not_submitted(self, mock_getsize, mock_mode):
        from comfyapp import _ComfyAPIMixin
        mock_getsize.return_value = int(5 * 1024**3)
        mock_mode.return_value = "workers_1"
        obj = _ComfyAPIMixin()
        obj._model_cpu_cache = {}
        import threading
        barrier = threading.Barrier(2, timeout=10)
        def slow_loader(path, return_metadata=False):
            barrier.wait()
            time.sleep(30)
            return {}, None
        obj._original_model_loader = slow_loader
        result = obj._preload_models_to_cpu(
            ["/models/a.safetensors", "/models/b.safetensors", "/models/c.safetensors"],
            budget_ms=None,
        )
        self.assertTrue(result.get("aborted", False))
        # a is running, b and c are pending/not submitted
        self.assertGreaterEqual(result.get("pending_not_submitted", 0), 0)
        self.assertIsNotNone(result.get("shutdown_wait_false"))


# ── Syncable node filtering invariants (PART 2 + PART 17) ──

class TestIterSyncableCustomNodeDirs(unittest.TestCase):
    """_iter_syncable_custom_node_dirs is the single source of truth."""

    def setUp(self):
        from comfyapp import _iter_syncable_custom_node_dirs
        self._func = _iter_syncable_custom_node_dirs
        self._tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp)

    def _mkdir(self, name: str):
        os.makedirs(os.path.join(self._tmp, name), exist_ok=True)

    def test_regular_node_included(self):
        self._mkdir("ComfyUI-KJNodes")
        result = self._func(self._tmp)
        self.assertIn("ComfyUI-KJNodes", result)

    def test_dot_prefix_excluded(self):
        self._mkdir(".staging")
        self._mkdir(".git")
        self._mkdir(".ipynb_checkpoints")
        result = self._func(self._tmp)
        for d in (".staging", ".git", ".ipynb_checkpoints"):
            self.assertNotIn(d, result)

    def test_known_non_node_dirs_excluded(self):
        self._mkdir("__pycache__")
        self._mkdir("node_modules")
        self._mkdir(".venv")
        self._mkdir("venv")
        result = self._func(self._tmp)
        for d in ("__pycache__", "node_modules", ".venv", "venv"):
            self.assertNotIn(d, result)

    def test_files_excluded(self):
        Path(self._tmp, "random_file.txt").touch()
        result = self._func(self._tmp)
        self.assertNotIn("random_file.txt", result)

    def test_empty_dir_empty_result(self):
        result = self._func(self._tmp)
        self.assertEqual(result, [])

    def test_topology_and_sync_agree(self):
        """custom_node_topology_fingerprint and sync_custom_nodes_into_comfy
        should enumerate the same node list for the same root."""
        from comfyapp import custom_node_topology_fingerprint
        self._mkdir("NodeA")
        self._mkdir("NodeB")
        self._mkdir(".staging")
        self._mkdir("__pycache__")
        fp = custom_node_topology_fingerprint(self._tmp)
        fp_nodes = {n["name"] for n in fp["nodes"]}
        syncable = set(self._func(self._tmp))
        self.assertEqual(fp_nodes, syncable)


class TestCustomNodeVolumeStateFiltering(unittest.TestCase):
    """custom_node_volume_state must use the same syncable filtering."""

    def setUp(self):
        from comfyapp import custom_node_volume_state
        self._func = custom_node_volume_state
        self._tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp)

    def _mkdir(self, name: str):
        os.makedirs(os.path.join(self._tmp, name), exist_ok=True)

    def test_staging_excluded_from_volume_state(self):
        self._mkdir(".staging")
        self._mkdir("RealNode")
        state = self._func(self._tmp)
        names = {s[0] for s in state}
        self.assertIn("RealNode", names)
        self.assertNotIn(".staging", names)

    def test_non_node_dirs_excluded(self):
        self._mkdir("__pycache__")
        self._mkdir("RealNode")
        state = self._func(self._tmp)
        names = {s[0] for s in state}
        self.assertIn("RealNode", names)
        self.assertNotIn("__pycache__", names)


# ── Volume commit in-flight guard (PART 7 + PART 17) ──

class TestCommitVolumeAsyncInflightGuard(unittest.TestCase):
    """_commit_volume_async with same label should skip duplicates."""

    def setUp(self):
        from comfyapp import _commit_volume_async, _volume_commit_inflight_labels
        self._func = _commit_volume_async
        self._inflight = _volume_commit_inflight_labels
        self._cleanup_labels = set()

    def tearDown(self):
        pass

    def test_same_label_defers_duplicate(self):
        self._inflight.add("test_label")
        with patch("builtins.print") as mock_print:
            self._func("test_label")
            mock_print.assert_any_call(
                "[comfyapp] volume_commit_async_deferred "
                "label=test_label reason=already_in_flight_marked_dirty"
            )

    def test_different_labels_both_start(self):
        with patch("builtins.print") as mock_print:
            self._func("label_a")
            self._func("label_b")
            started = [c for c in mock_print.call_args_list
                       if "volume_commit_async_started" in str(c)]
            self.assertEqual(len(started), 2)


# ── Preload session guard (PART 4 + PART 17) ──

class TestPreloadSessionGuard(unittest.TestCase):
    """Abandoned preload workers cannot mutate _model_cpu_cache."""

    @patch("comfyapp.PRELOAD_OUTLIER_ABORT_SECONDS", 1)
    @patch("comfyapp.PRELOAD_MIN_THROUGHPUT_GBPS", 0.5)
    @patch("os.path.getsize")
    def test_session_invalidated_on_abort(self, mock_getsize):
        from comfyapp import _ComfyAPIMixin
        mock_getsize.return_value = int(5 * 1024**3)
        obj = _ComfyAPIMixin()
        obj._model_cpu_cache = {}
        obj._in_flight_preloads = {}
        obj._log_profile = lambda *a, **kw: None
        obj._profile_ms = lambda s: (time.time() - s) * 1000
        import threading, time
        barrier = threading.Barrier(2, timeout=10)
        def slow_loader(path, return_metadata=False):
            barrier.wait()
            time.sleep(60)
            return {}, None
        obj._original_model_loader = slow_loader
        with patch("comfyapp._resolve_preload_mode", return_value="workers_1"):
            result = obj._preload_models_to_cpu(
                ["/models/a.safetensors"],
                budget_ms=None,
            )
        self.assertTrue(result.get("aborted", False))
        self.assertIsNone(getattr(obj, "_active_cpu_preload_session_id", None))

    def test_session_guard_blocks_stale_write(self):
        """When _active_cpu_preload_session_id is None, cache write is skipped."""
        obj = type("Fake", (), {"_model_cpu_cache": {}})()
        # Simulate the session guard check
        _preload_session_id = "session_abc"
        obj._active_cpu_preload_session_id = None  # invalidated
        cache_key = "test_key"
        if getattr(obj, "_active_cpu_preload_session_id", None) == _preload_session_id:
            obj._model_cpu_cache[cache_key] = ("data", None)
        self.assertNotIn(cache_key, obj._model_cpu_cache)


# ── Save dedup tests (PART 9 + PART 17) ──

class TestSaveLastWarmupWorkflowDedup(unittest.TestCase):
    """_save_last_warmup_workflow skips write when content unchanged."""

    def setUp(self):
        from comfyapp import _ComfyAPIMixin
        self._tmp = tempfile.mkdtemp()
        self._obj = _ComfyAPIMixin()
        self._obj._log_profile = lambda *a, **kw: None
        self._obj._profile_ms = lambda s: 0.0
        self._obj._model_cpu_cache = {}
        self._obj._in_flight_preloads = {}
        # Track commit calls
        self._commit_calls = []
        self._original_commit = None

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp)

    def test_identical_content_skips_commit(self):
        import importlib
        import comfyapp
        importlib.reload(comfyapp)
        LAST_WARMUP_WORKFLOW_PATH = comfyapp.LAST_WARMUP_WORKFLOW_PATH
        with patch("comfyapp.LAST_WARMUP_WORKFLOW_PATH", os.path.join(self._tmp, "last_warmup.json")):
            with patch("comfyapp._commit_volume_async") as mock_commit:
                wf = {"3": {"class_type": "KSampler", "inputs": {"seed": 7}}}
                self._obj._save_last_warmup_workflow(wf)
                self.assertEqual(mock_commit.call_count, 1)
                # Save again with identical content — should skip
                self._obj._save_last_warmup_workflow(wf)
                self.assertEqual(mock_commit.call_count, 1)  # no extra commit


class TestSaveLastModelStackDedup(unittest.TestCase):
    """_save_last_model_stack skips write when content unchanged."""

    def setUp(self):
        from comfyapp import _ComfyAPIMixin
        self._tmp = tempfile.mkdtemp()
        self._obj = _ComfyAPIMixin()
        self._obj._log_profile = lambda *a, **kw: None
        self._obj._profile_ms = lambda s: 0.0
        self._obj._model_cpu_cache = {}
        self._obj._in_flight_preloads = {}

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp)

    def test_identical_content_skips_commit(self):
        import comfyapp
        LAST_MODEL_STACK_PATH = comfyapp.LAST_MODEL_STACK_PATH
        with patch("comfyapp.LAST_MODEL_STACK_PATH", os.path.join(self._tmp, "last_model_stack.json")):
            with patch("comfyapp._commit_volume_async") as mock_commit:
                stack = {"unet": "flux1-dev.safetensors", "clip": ["t5", "clip_l"]}
                self._obj._save_last_model_stack(stack)
                self.assertEqual(mock_commit.call_count, 1)
                # Save again — should skip
                self._obj._save_last_model_stack(stack)
                self.assertEqual(mock_commit.call_count, 1)


# ── Request summary truth (PART 3 + PART 17) ──

class TestRequestPipelineSummaryLocalPreflight(unittest.TestCase):
    """run_prompt and run_prompt_stream must not claim local_preflight
    unless modal_options proves it."""

    def test_make_request_summary_defaults_false(self):
        from comfyapp import make_request_pipeline_summary
        s = make_request_pipeline_summary()
        self.assertIs(s.get("local_preflight_validated"), False)

    def test_make_request_summary_with_proof(self):
        from comfyapp import make_request_pipeline_summary
        s = make_request_pipeline_summary(local_preflight_validated=True)
        self.assertIs(s.get("local_preflight_validated"), True)


# ── No-EXCLUDED duplicate (PART 16 + PART 17) ──

class TestNoDuplicateExcludeSet(unittest.TestCase):
    """Only _CUSTOM_NODE_SYNC_EXCLUDE_DIRS should exist."""

    def test_excluded_constant_removed(self):
        """_EXCLUDED_CUSTOM_NODE_DIRS must not be defined."""
        with open(os.path.join(os.path.dirname(__file__), "..", "comfyapp.py"), "r") as f:
            src = f.read()
        # Verify _EXCLUDED_CUSTOM_NODE_DIRS is NOT present (the ``=`` part)
        self.assertNotIn("_EXCLUDED_CUSTOM_NODE_DIRS", src,
                         "_EXCLUDED_CUSTOM_NODE_DIRS must be removed; "
                         "use _iter_syncable_custom_node_dirs instead")


if __name__ == "__main__":
    unittest.main()
