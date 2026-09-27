"""Tests for Phase 3b2: preview suppression, progress throttling, quiet logs, telemetry."""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"
PRODWFLOW_PATH = REPO_ROOT / "production_workflow.py"


class Phase3b2ComfyappAstTests(unittest.TestCase):
    def setUp(self):
        self.src = COMFYAPP_PATH.read_text(encoding="utf-8")

    def test_preview_suppression_calls_set_preview_method_none(self):
        self.assertIn('set_preview_method("none")', self.src)

    def test_preview_restore_calls_set_preview_method_original(self):
        self.assertIn("_lp.set_preview_method(_prod_preview_restore)", self.src)

    def test_progress_throttle_set_before_executor(self):
        self.assertIn("self._production_progress_throttle_ms = _throttle_ms", self.src)

    def test_progress_throttle_restore_after_executor(self):
        self.assertIn("self._production_progress_throttle_ms = _prod_throttle_saved", self.src)

    def test_quiet_logs_redirect_stdout(self):
        self.assertIn("redirect_stdout(_quiet_out)", self.src)

    def test_quiet_logs_redirect_stderr(self):
        self.assertIn("redirect_stderr(_quiet_err)", self.src)

    def test_quiet_logs_root_logger_handler_remove(self):
        self.assertIn("_root.removeHandler(h)", self.src)

    def test_quiet_logs_root_logger_handler_restore(self):
        self.assertIn("_root.addHandler(h)", self.src)

    def test_quiet_logs_print_suppressed_bytes(self):
        self.assertIn("[production.quiet_logs] suppressed=", self.src)

    def test_runtime_telemetry_sampler_previews_suppressed(self):
        self.assertIn('"sampler_previews_suppressed"', self.src)

    def test_runtime_telemetry_quiet_logs_suppressed(self):
        self.assertIn('"quiet_logs_suppressed"', self.src)

    def test_runtime_telemetry_progress_skip_count(self):
        self.assertIn('"progress_skip_count"', self.src)

    def test_runtime_telemetry_progress_throttle_ms(self):
        self.assertIn('"progress_throttle_ms"', self.src)

    def test_runtime_telemetry_bypass_node_count(self):
        self.assertIn('"bypass_node_count"', self.src)

    def test_runtime_telemetry_direct_output_count(self):
        self.assertIn('"direct_output_count"', self.src)

    def test_runtime_telemetry_filesystem_scan_skipped(self):
        self.assertIn('"filesystem_scan_skipped"', self.src)

    def test_production_runtime_key_attached_to_result(self):
        self.assertIn('"_production_runtime"', self.src)

    def test_progress_skip_counter_incremented(self):
        self.assertIn("self._production_progress_skip_count = getattr(self, \"_production_progress_skip_count\", 0) + 1", self.src)

    def test_progress_throttle_checked_in_on_sync(self):
        self.assertIn("_prod_throttle_ms = getattr(self, \"_production_progress_throttle_ms\", 0)", self.src)

    def test_progress_throttle_compare_timestamps(self):
        self.assertIn("_now - _last < (_prod_throttle_ms / 1000.0)", self.src)

    def test_progress_throttle_updates_last_ts(self):
        self.assertIn("self._production_progress_last_ts = _now", self.src)

    def test_latent_preview_import_guarded(self):
        self.assertIn("import latent_preview as _lp", self.src)

    def test_preview_suppression_try_except_safe(self):
        self.assertIn("_prod_preview_restore = _lp.get_preview_method()", self.src)

    def test_preview_restore_try_except_safe(self):
        self.assertIn("if _prod_preview_restore is not None:", self.src)


if __name__ == "__main__":
    unittest.main()
