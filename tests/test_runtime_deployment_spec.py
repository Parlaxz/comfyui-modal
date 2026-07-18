"""Focused tests for deployment_spec: manifest builder and exclusion rules."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from comfymodal_runtime.deployment_spec import (
    ALLOWED_SOURCE_EXTENSIONS,
    EXCLUDED_DIRS,
    EXCLUDED_EXTENSIONS,
    EXCLUDED_FILENAMES,
    EXCLUDED_INFIXES,
    EXCLUDED_PREFIXES,
    GENERATED_JSON_PREFIXES,
    build_deployment_identity,
    compute_aggregate_hash,
    compute_file_hashes,
    compute_source_bytes,
    is_excluded_name,
)


class TestExclusionPredicate(unittest.TestCase):
    """Pure-function tests for ``is_excluded_name`` — no filesystem access."""

    def test_allowed_py_file(self):
        self.assertFalse(is_excluded_name("main.py"))

    def test_allowed_js_file(self):
        self.assertFalse(is_excluded_name("app.js"))
        self.assertFalse(is_excluded_name("module.mjs"))

    def test_excluded_extension_pyc(self):
        self.assertTrue(is_excluded_name("module.pyc"))

    def test_excluded_extension_pyo(self):
        self.assertTrue(is_excluded_name("module.pyo"))

    def test_excluded_extension_md(self):
        self.assertTrue(is_excluded_name("README.md"))

    def test_excluded_extension_tmp(self):
        self.assertTrue(is_excluded_name("scratch.tmp"))

    def test_excluded_extension_ref(self):
        self.assertTrue(is_excluded_name("reference.ref"))

    def test_excluded_extension_log(self):
        self.assertTrue(is_excluded_name("output.log"))

    def test_excluded_prefix_before_v2(self):
        self.assertTrue(is_excluded_name("before_v2_16_20_full.patch"))

    def test_excluded_infix_backup(self):
        self.assertTrue(is_excluded_name("comfyapp.py.v21610_backup"))

    def test_excluded_exact_gitignore(self):
        self.assertTrue(is_excluded_name(".gitignore"))

    def test_excluded_exact_deploy_log(self):
        self.assertTrue(is_excluded_name(".deploy_log"))

    def test_excluded_exact_modal_logs(self):
        self.assertTrue(is_excluded_name("modal_logs.txt"))

    def test_excluded_generated_json_temp(self):
        self.assertTrue(is_excluded_name("temp_result.json"))

    def test_excluded_generated_json_last_trace(self):
        self.assertTrue(is_excluded_name("_last_trace_result.json"))

    def test_excluded_generated_json_studio(self):
        self.assertTrue(is_excluded_name("studio-run-completed.json"))

    def test_excluded_generated_json_clean(self):
        self.assertTrue(is_excluded_name("clean_workflow.json"))

    def test_excluded_generated_json_latest_benchmark(self):
        self.assertTrue(is_excluded_name("latest_benchmark_workflow.json"))

    def test_excluded_generated_json_modal_dot(self):
        self.assertTrue(is_excluded_name(".modal_settings.json"))
        self.assertTrue(is_excluded_name(".model_manifest.json"))
        self.assertTrue(is_excluded_name(".profile_config.json"))

    def test_excluded_screenshot_png(self):
        self.assertTrue(is_excluded_name("studio-validation-desktop.png"))
        self.assertTrue(is_excluded_name("screenshot-result.png"))

    def test_excluded_allowed_runtime_json(self):
        # Runtime state JSON should NOT be excluded (no matching prefix)
        self.assertFalse(is_excluded_name("runtime_state.json"))
        self.assertFalse(is_excluded_name("deployment_state.json"))

    def test_included_python_file(self):
        self.assertFalse(is_excluded_name("nodes.py"))
        self.assertFalse(is_excluded_name("__init__.py"))

    def test_included_js_file(self):
        self.assertFalse(is_excluded_name("index.js"))
        self.assertFalse(is_excluded_name("worker.mjs"))

    def test_case_sensitivity_md(self):
        # Extension matching should be case-insensitive
        self.assertTrue(is_excluded_name("README.MD"))
        self.assertTrue(is_excluded_name("readme.Md"))


class TestBuildDeploymentIdentity(unittest.TestCase):
    """Integration tests for the full manifest builder with temp directories."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rel: str, content: str = "content") -> Path:
        """Create a file at *rel* under the temp root."""
        path = self.tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    # ── No-op manifest ───────────────────────────────────────────────

    def test_empty_runtime_root_yields_empty_identity(self):
        """An empty runtime root produces an identity with empty hashes."""
        identity = build_deployment_identity(self.tmp_path)
        # SHA-256 of empty input is deterministic (empty dict produces it)
        self.assertEqual(len(identity.runtime_hash), 64)
        self.assertEqual(identity.custom_node_hash, "")
        self.assertEqual(identity.dependency_hash, "")
        self.assertEqual(identity.source_bytes, 0)
        self.assertEqual(identity.file_hashes, {})

    # ── Required module inclusion ────────────────────────────────────

    def test_py_files_are_included_in_hash(self):
        self._write("contracts.py", "class DeploymentIdentity: pass")
        identity = build_deployment_identity(self.tmp_path)
        self.assertNotEqual(identity.runtime_hash, "")
        self.assertIn("contracts.py", identity.file_hashes)
        self.assertGreater(identity.source_bytes, 0)

    def test_multiple_py_files_are_all_included(self):
        self._write("a.py", "x = 1")
        self._write("b.py", "y = 2")
        identity = build_deployment_identity(self.tmp_path)
        self.assertIn("a.py", identity.file_hashes)
        self.assertIn("b.py", identity.file_hashes)

    def test_non_source_extensions_are_excluded(self):
        self._write("main.py", "code")
        self._write("readme.md", "# Docs")
        self._write("data.tmp", "temp")
        self._write("output.log", "log content")
        identity = build_deployment_identity(self.tmp_path)
        self.assertIn("main.py", identity.file_hashes)
        self.assertNotIn("readme.md", identity.file_hashes)
        self.assertNotIn("data.tmp", identity.file_hashes)
        self.assertNotIn("output.log", identity.file_hashes)

    # ── Excluded artifact change — must NOT alter identity ───────────

    def test_excluded_artifact_change_does_not_alter_hash(self):
        self._write("core.py", "fixed")
        h1 = build_deployment_identity(self.tmp_path).combined_hash

        # Add an excluded artifact
        self._write("README.md", "new docs")
        h2 = build_deployment_identity(self.tmp_path).combined_hash

        self.assertEqual(h1, h2)

    def test_excluded_dir_content_does_not_affect_identity(self):
        self._write("core.py", "fixed")
        h1 = build_deployment_identity(self.tmp_path).combined_hash

        # Files inside excluded directories should be invisible
        self._write("docs/guide.md", "guide")
        self._write("tests/test_a.py", "test")
        self._write("reference/old.py", "old")
        self._write("node_modules/pkg/index.js", "pkg")
        h2 = build_deployment_identity(self.tmp_path).combined_hash

        self.assertEqual(h1, h2)

    def test_backup_file_does_not_affect_identity(self):
        self._write("core.py", "fixed")
        h1 = build_deployment_identity(self.tmp_path).combined_hash

        self._write("main.py.v21610_backup", "backup")
        h2 = build_deployment_identity(self.tmp_path).combined_hash

        self.assertEqual(h1, h2)

    def test_before_v2_patch_does_not_affect_identity(self):
        self._write("core.py", "fixed")
        h1 = build_deployment_identity(self.tmp_path).combined_hash

        self._write("before_v2_16_20_full.patch", "diff")
        h2 = build_deployment_identity(self.tmp_path).combined_hash

        self.assertEqual(h1, h2)

    def test_generated_json_does_not_affect_identity(self):
        self._write("core.py", "fixed")
        h1 = build_deployment_identity(self.tmp_path).combined_hash

        self._write("temp_result.json", '{"key": "value"}')
        self._write("_last_trace_result.json", '{"trace": []}')
        h2 = build_deployment_identity(self.tmp_path).combined_hash

        self.assertEqual(h1, h2)

    # ── Source-only custom-node change — MUST alter identity ─────────

    def test_source_change_alters_identity(self):
        self._write("core.py", "fixed")
        h1 = build_deployment_identity(self.tmp_path).combined_hash

        # Wait for different mtime (not needed; we change content)
        self._write("core.py", "changed content")
        h2 = build_deployment_identity(self.tmp_path).combined_hash

        self.assertNotEqual(h1, h2)

    def test_custom_node_py_change_alters_custom_node_hash(self):
        self._write("runtime.py", "runtime code")
        identity_no_custom = build_deployment_identity(self.tmp_path)

        custom_dir = self.tmp_path / "_custom_nodes"
        custom_dir.mkdir()
        (custom_dir / "node.py").write_text("node v1", encoding="utf-8")

        identity_v1 = build_deployment_identity(
            self.tmp_path, custom_node_paths=[custom_dir]
        )
        self.assertNotEqual(identity_v1.custom_node_hash, "")

        # Change custom-node source
        (custom_dir / "node.py").write_text("node v2", encoding="utf-8")
        identity_v2 = build_deployment_identity(
            self.tmp_path, custom_node_paths=[custom_dir]
        )
        self.assertNotEqual(identity_v1.custom_node_hash, identity_v2.custom_node_hash)

    def test_custom_node_js_change_alters_identity(self):
        self._write("runtime.py", "runtime code")
        custom_dir = self.tmp_path / "_custom_nodes"
        custom_dir.mkdir()
        (custom_dir / "ui.js").write_text("console.log('v1')", encoding="utf-8")

        id1 = build_deployment_identity(
            self.tmp_path, custom_node_paths=[custom_dir]
        )
        (custom_dir / "ui.js").write_text("console.log('v2')", encoding="utf-8")
        id2 = build_deployment_identity(
            self.tmp_path, custom_node_paths=[custom_dir]
        )
        self.assertNotEqual(id1.combined_hash, id2.combined_hash)

    # ── Dependency-only change ───────────────────────────────────────

    def test_dependency_hash_is_carried_through(self):
        id1 = build_deployment_identity(
            self.tmp_path, dependency_hash="dep-v1"
        )
        id2 = build_deployment_identity(
            self.tmp_path, dependency_hash="dep-v2"
        )
        self.assertEqual(id1.runtime_hash, id2.runtime_hash)
        self.assertNotEqual(id1.combined_hash, id2.combined_hash)

    # ── Determinism ──────────────────────────────────────────────────

    def test_identical_source_produces_identical_identity(self):
        self._write("a.py", "x = 1")
        id1 = build_deployment_identity(self.tmp_path)
        id2 = build_deployment_identity(self.tmp_path)
        self.assertEqual(id1.combined_hash, id2.combined_hash)
        self.assertEqual(id1.to_dict(), id2.to_dict())


class TestComputeHelpers(unittest.TestCase):
    """Tests for the lower-level hash/size computation functions."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rel: str, content: str = "data") -> Path:
        path = self.tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_compute_source_bytes_counts_only_allowed(self):
        self._write("a.py", "hello")
        self._write("b.md", "world")  # excluded extension
        total = compute_source_bytes(self.tmp_path)
        self.assertGreater(total, 0)
        # Only a.py contributes
        self.assertLess(total, 6)  # 'hello' is 5 bytes, plus maybe BOM

    def test_compute_file_hashes_excludes_non_source(self):
        self._write("a.py", "content")
        self._write("b.md", "content")
        hashes = compute_file_hashes(self.tmp_path)
        self.assertIn("a.py", hashes)
        self.assertNotIn("b.md", hashes)

    def test_compute_aggregate_hash_is_deterministic(self):
        h1 = compute_aggregate_hash({"a.py": "abc", "b.py": "def"})
        h2 = compute_aggregate_hash({"b.py": "def", "a.py": "abc"})
        self.assertEqual(h1, h2)

    def test_compute_aggregate_hash_empty(self):
        # SHA-256 of empty input (no paths fed into the hasher)
        empty_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        self.assertEqual(compute_aggregate_hash({}), empty_hash)


if __name__ == "__main__":
    unittest.main()
