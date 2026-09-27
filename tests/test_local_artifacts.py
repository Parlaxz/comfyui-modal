"""
Focused tests for local_artifacts resolver, deployment_guard, and
tools/migrate_local_artifacts.

Does not run real migration or modify actual data.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


# ── local_artifacts tests ──────────────────────────────────────────────────

class LocalArtifactsResolverTests(unittest.TestCase):
    """Test the side-effect-free resolver."""

    def setUp(self):
        # Fresh import each time to reset caches
        for mod in list(sys.modules.keys()):
            if 'local_artifacts' in mod:
                del sys.modules[mod]
        if 'local_artifacts' in sys.modules:
            del sys.modules['local_artifacts']

    def _import(self):
        import local_artifacts
        return local_artifacts

    def test_resolver_import_is_side_effect_free(self):
        """Importing local_artifacts must not create any directories.

        Uses a COMFYMODAL_LOCAL_DATA_DIR override so the test remains valid
        even when the real default ``comfymodal-data`` directory already exists.
        Verifies that importing and resolving the path does NOT create it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp).resolve()
            override = tmp_path / "nonexistent-data"
            old = os.environ.get("COMFYMODAL_LOCAL_DATA_DIR")
            try:
                os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = str(override)
                # Fresh import picks up the overridden env var
                la = self._import()
                data_root = la.get_local_data_root()
                self.assertFalse(
                    data_root.exists(),
                    f"get_local_data_root() would create dir: {data_root}",
                )
            finally:
                if old is not None:
                    os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = old
                else:
                    os.environ.pop("COMFYMODAL_LOCAL_DATA_DIR", None)

    def test_resolver_env_override(self):
        """COMFYMODAL_LOCAL_DATA_DIR overrides the default root."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp).resolve()
            override = tmp_path / "my custom path with spaces"
            try:
                old = os.environ.get("COMFYMODAL_LOCAL_DATA_DIR")
                os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = str(override)
                la = self._import()
                la._reset_caches_for_testing()
                # re-import fresh
                for mod in list(sys.modules.keys()):
                    if 'local_artifacts' in mod:
                        del sys.modules[mod]
                # set env var again after re-import
                os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = str(override)
                la2 = self._import()
                self.assertEqual(la2.get_local_data_root(), override.resolve())
            finally:
                if old is not None:
                    os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = old
                else:
                    os.environ.pop("COMFYMODAL_LOCAL_DATA_DIR", None)

    def test_resolver_default_root_is_under_comfyui(self):
        """Default data root is <ComfyUI root>/comfymodal-data."""
        la = self._import()
        data_root = la.get_local_data_root()
        comfyui_root = la.get_comfyui_root()
        self.assertEqual(data_root, comfyui_root / "comfymodal-data")

    def test_resolver_category_paths_are_absolute(self):
        """All category path functions return absolute paths."""
        la = self._import()
        for fn_name in [
            "get_outputs_dir", "get_studio_outputs_dir", "get_modal_outputs_dir",
            "get_playwright_test_results_dir", "get_playwright_report_dir",
            "get_playwright_mcp_dir", "get_experiments_dir", "get_run_history_dir",
            "get_benchmark_runs_dir", "get_benchmark_logs_dir", "get_optimization_logs_dir",
        ]:
            with self.subTest(fn=fn_name):
                path = getattr(la, fn_name)()
                self.assertTrue(path.is_absolute(), f"{fn_name} returned {path} (not absolute)")

    def test_resolver_plugin_root_is_this_dir(self):
        """get_plugin_root returns the directory containing local_artifacts.py."""
        la = self._import()
        plugin_root = la.get_plugin_root()
        this_file = Path(__file__).resolve().parent.parent / "local_artifacts.py"
        self.assertTrue(this_file.is_file(),
                        f"local_artifacts.py not found at {this_file}")
        self.assertEqual(plugin_root, this_file.parent)

    def test_category_mapping_has_all_legacy_keys(self):
        """The flat CATEGORY_MAP covers all legacy source dirs."""
        la = self._import()
        for legacy_key in [
            "output", "test-results", "playwright-report",
            ".playwright-mcp", ".experiments", ".run_history",
            "benchmark_runs", "benchmark_logs", "optimization_logs",
        ]:
            with self.subTest(key=legacy_key):
                self.assertIn(legacy_key, la.CATEGORY_MAP)


# ── deployment_guard tests ─────────────────────────────────────────────────

class DeploymentGuardTests(unittest.TestCase):
    """Test the pre-deploy guard."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin_root = Path(self._tmp.name).resolve()
        # Create a minimal plugin-like structure
        (self.plugin_root / "__init__.py").write_text("")
        (self.plugin_root / "local_artifacts.py").write_text("")

    def tearDown(self):
        self._tmp.cleanup()

    def test_guard_passes_with_no_generated_dirs(self):
        """Guard succeeds when no generated directories have files."""
        # Set env var to use our temp dir
        old = os.environ.get("COMFYMODAL_LOCAL_DATA_DIR")
        try:
            os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = str(self.plugin_root / "data")
            # Need a proper local_artifacts mock — we'll test via deployment_guard
            from deployment_guard import _scan_generated_dirs
            result = _scan_generated_dirs(self.plugin_root)
            self.assertEqual(result, {})
        finally:
            if old is not None:
                os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = old
            else:
                os.environ.pop("COMFYMODAL_LOCAL_DATA_DIR", None)

    def test_guard_detects_test_results(self):
        """Guard detects a file in test-results/."""
        test_results = self.plugin_root / "test-results"
        test_results.mkdir(parents=True)
        (test_results / "result.json").write_text("{}")

        from deployment_guard import _scan_generated_dirs
        result = _scan_generated_dirs(self.plugin_root)
        self.assertIn("test-results", result)
        self.assertGreater(result["test-results"], 0)

    def test_guard_raises_on_generated_data(self):
        """guard_generated_artifacts raises SystemExit when generated data found."""
        test_results = self.plugin_root / "test-results"
        test_results.mkdir(parents=True)
        (test_results / "output.txt").write_text("data")

        old = os.environ.get("COMFYMODAL_LOCAL_DATA_DIR")
        try:
            os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = str(self.plugin_root / "data")
            from deployment_guard import guard_generated_artifacts
            with self.assertRaises(SystemExit):
                guard_generated_artifacts(str(self.plugin_root))
        finally:
            if old is not None:
                os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = old
            else:
                os.environ.pop("COMFYMODAL_LOCAL_DATA_DIR", None)

    def test_guard_message_contains_migration_command(self):
        """Guard error message mentions the migration tool."""
        test_results = self.plugin_root / "test-results"
        test_results.mkdir(parents=True)
        (test_results / "log.txt").write_text("log")

        old = os.environ.get("COMFYMODAL_LOCAL_DATA_DIR")
        try:
            os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = str(self.plugin_root / "data")
            import io
            from deployment_guard import guard_generated_artifacts
            stderr = io.StringIO()
            sys.stderr, old_stderr = stderr, sys.stderr
            try:
                with self.assertRaises(SystemExit):
                    guard_generated_artifacts(str(self.plugin_root))
                output = stderr.getvalue()
                self.assertIn("migrate_local_artifacts", output)
                self.assertIn("test-results", output)
            finally:
                sys.stderr = old_stderr
        finally:
            if old is not None:
                os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = old
            else:
                os.environ.pop("COMFYMODAL_LOCAL_DATA_DIR", None)


    def test_hidden_dir_included_in_source_size(self):
        """Hidden dirs (like .config) are NOT excluded from source-size walking."""
        config_dir = self.plugin_root / ".config"
        config_dir.mkdir(parents=True)
        (config_dir / "settings.json").write_text("{}")

        from deployment_guard import _iter_source_files
        files = _iter_source_files(self.plugin_root)
        self.assertTrue(
            any(f.name == "settings.json" for f in files),
            "Expected .config/settings.json to be included in source files"
        )

    def test_source_context_size_handles_relative_path(self):
        """_compute_source_context_size normalizes a relative Path internally."""
        (self.plugin_root / "source.py").write_text("x = 1")
        from deployment_guard import _compute_source_context_size

        cwd = Path.cwd()
        try:
            os.chdir(str(self.plugin_root.parent))
            rel = Path(self.plugin_root.name)
            total, count, dirs = _compute_source_context_size(rel)
            self.assertGreater(total, 0)
            self.assertGreater(count, 0)
        finally:
            os.chdir(str(cwd))

    def test_generated_dir_symlink_not_scanned(self):
        """A symlinked known generated dir is not followed by the guard."""
        real_dir = Path(self._tmp.name) / "real_output"
        real_dir.mkdir(parents=True, exist_ok=True)
        (real_dir / "data.txt").write_text("real_data")

        link_path = self.plugin_root / "output"
        try:
            os.symlink(real_dir, link_path, target_is_directory=True)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("Symlink not supported on this platform")

        from deployment_guard import _scan_generated_dirs
        result = _scan_generated_dirs(self.plugin_root)
        self.assertNotIn("output", result)


# ── migrate_local_artifacts tests ──────────────────────────────────────────

class MigrateLocalArtifactsTests(unittest.TestCase):
    """Test the migration tool logic."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin_root = Path(self._tmp.name).resolve()
        self.data_root = self.plugin_root / "data_root"
        self.data_root.mkdir(parents=True)
        # Set env var for local_artifacts
        self._old_env = os.environ.get("COMFYMODAL_LOCAL_DATA_DIR")
        os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = str(self.data_root)

    def tearDown(self):
        if self._old_env is not None:
            os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = self._old_env
        else:
            os.environ.pop("COMFYMODAL_LOCAL_DATA_DIR", None)
        self._tmp.cleanup()

    def _make_source_file(self, rel_path: str, content: str = "test") -> Path:
        full = self.plugin_root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        return full

    def test_dry_run_makes_no_changes(self):
        """--dry-run must not create or remove any files."""
        self._make_source_file("output/test.png", "fake_png")
        self._make_source_file("test-results/report.xml", "<xml/>")

        # Run dry-run migration
        from tools.migrate_local_artifacts import migrate_category, MigrationStats
        stats = MigrationStats()
        migrate_category("output", self.plugin_root, self.data_root, dry_run=True, stats=stats)
        migrate_category("test-results", self.plugin_root, self.data_root, dry_run=True, stats=stats)

        # Check source untouched
        self.assertTrue((self.plugin_root / "output" / "test.png").is_file())
        self.assertTrue((self.plugin_root / "test-results" / "report.xml").is_file())
        # Check destination does NOT exist
        self.assertFalse((self.data_root / "outputs" / "test.png").is_file())
        self.assertFalse((self.data_root / "playwright" / "test-results" / "report.xml").is_file())
        # Stats should be set
        self.assertEqual(stats.total_files, 2)

    def test_real_migration_copies_and_removes(self):
        """Real migration copies files to destination, verifies, then removes source."""
        self._make_source_file("output/img1.png", "pngdata1")
        self._make_source_file("output/img2.png", "pngdata2")
        self._make_source_file("benchmark_runs/run1/log.txt", "logdata")

        from tools.migrate_local_artifacts import migrate_category, MigrationStats
        stats = MigrationStats()
        migrate_category("output", self.plugin_root, self.data_root, dry_run=False, stats=stats)
        migrate_category("benchmark_runs", self.plugin_root, self.data_root, dry_run=False, stats=stats)

        # Check destination
        dst_output = self.data_root / "outputs"
        dst_bench = self.data_root / "benchmarks" / "runs"
        self.assertTrue((dst_output / "img1.png").is_file())
        self.assertTrue((dst_output / "img2.png").is_file())
        self.assertTrue((dst_bench / "run1" / "log.txt").is_file())

        # Check source removed
        self.assertFalse((self.plugin_root / "output" / "img1.png").is_file())
        self.assertFalse((self.plugin_root / "output").exists())
        self.assertFalse((self.plugin_root / "benchmark_runs" / "run1" / "log.txt").is_file())
        self.assertFalse((self.plugin_root / "benchmark_runs").exists())

        # Check stats
        self.assertEqual(stats.total_files, 3)

    def test_idempotent_rerun(self):
        """Re-running migration after source is already gone is safe."""
        self._make_source_file("output/f.png", "data")
        from tools.migrate_local_artifacts import migrate_category, MigrationStats
        stats1 = MigrationStats()
        migrate_category("output", self.plugin_root, self.data_root, dry_run=False, stats=stats1)
        self.assertEqual(stats1.total_files, 1)

        # Rerun
        stats2 = MigrationStats()
        migrate_category("output", self.plugin_root, self.data_root, dry_run=False, stats=stats2)
        # Source already gone, nothing to migrate
        self.assertEqual(stats2.total_files, 0)

    def test_conflict_preserves_both_files(self):
        """When destination has a different file with the same name, both are preserved."""
        self._make_source_file("output/conflict.txt", "source_version")
        # Pre-create destination with different content
        dst_dir = self.data_root / "outputs"
        dst_dir.mkdir(parents=True, exist_ok=True)
        (dst_dir / "conflict.txt").write_text("destination_version")

        from tools.migrate_local_artifacts import migrate_category, MigrationStats
        stats = MigrationStats()
        migrate_category("output", self.plugin_root, self.data_root, dry_run=False, stats=stats)

        # Both files should exist
        self.assertTrue((dst_dir / "conflict.txt").is_file())
        self.assertEqual((dst_dir / "conflict.txt").read_text(), "destination_version")
        # Source version should have a conflict suffix
        conflict_files = list(dst_dir.glob("conflict_*.txt"))
        self.assertEqual(len(conflict_files), 1)
        self.assertIn("source_version", conflict_files[0].read_text())
        # Source directory should be gone
        self.assertFalse((self.plugin_root / "output").exists())

    def test_identical_file_merge_no_change(self):
        """Real migration when dest already has identical content succeeds (no crash)."""
        self._make_source_file("output/f1.txt", "hello")
        dst = self.data_root / "outputs" / "f1.txt"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("hello")

        from tools.migrate_local_artifacts import migrate_category, MigrationStats
        stats = MigrationStats()
        migrate_category("output", self.plugin_root, self.data_root, dry_run=False, stats=stats)

        # Source directory removed
        self.assertFalse((self.plugin_root / "output").exists())
        # Destination preserved
        self.assertTrue(dst.is_file())
        self.assertEqual(dst.read_text(), "hello")

    def test_identical_file_merge_multiple_files(self):
        """Multiple identical files across subdirectories merge without error."""
        pairs = [
            ("output/a.txt", "aaa"),
            ("output/sub/b.txt", "bbb"),
            ("output/sub/deep/c.txt", "ccc"),
        ]
        for rel, content in pairs:
            self._make_source_file(rel, content)
            d = self.data_root / "outputs" / rel[len("output/"):]
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_text(content)

        from tools.migrate_local_artifacts import migrate_category, MigrationStats
        stats = MigrationStats()
        migrate_category("output", self.plugin_root, self.data_root, dry_run=False, stats=stats)

        self.assertFalse((self.plugin_root / "output").exists())
        for rel, content in pairs:
            d = self.data_root / "outputs" / rel[len("output/"):]
            self.assertTrue(d.is_file(), f"Missing {d}")
            self.assertEqual(d.read_text(), content)

    def test_dry_run_no_change_with_identical_dest(self):
        """Dry-run when dest has identical content makes no changes to source or dest."""
        self._make_source_file("output/f1.txt", "data")
        dst = self.data_root / "outputs" / "f1.txt"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("data")

        from tools.migrate_local_artifacts import migrate_category, MigrationStats
        stats = MigrationStats()
        migrate_category("output", self.plugin_root, self.data_root, dry_run=True, stats=stats)

        self.assertTrue((self.plugin_root / "output" / "f1.txt").is_file())
        self.assertTrue(dst.is_file())
        self.assertEqual(stats.total_files, 1)

    def test_migration_skips_symlinked_file(self):
        """Symlinked files within source dir are skipped but migration succeeds."""
        self._make_source_file("output/real.txt", "real")
        link_file = self.plugin_root / "output" / "link.txt"
        try:
            os.symlink("real.txt", link_file)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("Symlink not supported on this platform")

        from tools.migrate_local_artifacts import migrate_category, MigrationStats
        stats = MigrationStats()
        migrate_category("output", self.plugin_root, self.data_root, dry_run=False, stats=stats)

        self.assertFalse((self.plugin_root / "output").exists())
        dst = self.data_root / "outputs" / "real.txt"
        self.assertTrue(dst.is_file())
        self.assertEqual(dst.read_text(), "real")


if __name__ == "__main__":
    unittest.main()
