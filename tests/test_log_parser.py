"""
Tests for tools/compare_model_read_ab.py log parser.

Tests parsing of structured diagnostic lines from cold-start runs,
including the supplied good and bad runs.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.compare_model_read_ab import (
    _parse_log_file,
    _median,
    RE_CRITICAL_PATH_FLAGS,
    RE_COORDINATOR_SUMMARY,
    RE_CRITICAL_PATH_OBSERVED,
)


# ── Synthetic log content ─────────────────────────────────────────────────

_GOOD_RUN_LOG = """\
[critical_path.flags] critical_path=1 unet_phase=1 validation_phase=1 coordinator=0 coordinator_diag=1 source=module_import
[exact_prefill.remote] enabled=1 source=env
[restore.preload.strategy] role=clip strategy=read_bytes file=clip.safetensors
[waterfall] OK    app_restore_total            1920.0  app
[active_read] registered owner=restore_preload key=/models/clip.safetensors
[active_read] completed owner=restore_preload key=/models/clip.safetensors
[active_read] registered owner=restore_background_unet key=/models/unet.safetensors
[active_read] completed owner=restore_background_unet key=/models/unet.safetensors
[model_read_coordinator] event=acquired owner=restore_background_unet loader=UNET path_digest=abc123 wait_ms=0.0 hold_ms=0.0 degraded=0 contention=0 thread_id=1234
[model_read_coordinator] event=released owner=restore_background_unet loader=UNET path_digest=abc123 wait_ms=0.0 hold_ms=20660.0 degraded=0 contention=0 thread_id=1234
[model_read_coordinator.summary] enabled=1 acquisitions=1 waited=0 total_wait_ms=0.0 total_hold_ms=20660.0 peak_wait_ms=0.0 timeout_fail_open=0 production_unet_hold_ms=20660.0 graph_vae_wait_ms=0.0 graph_vae_hold_ms=0.0
[waterfall] SUM    known_nonoverlap_total        20660.0  --
[waterfall] OK    full_wall_ms            32000.0  app
"""


_COLLAPSED_RUN_2_LOG = """\
[critical_path.flags] critical_path=1 unet_phase=1 validation_phase=1 coordinator=0 coordinator_diag=1 source=module_import
[exact_prefill.remote] enabled=1 source=env
[waterfall] OK    app_restore_total            4940.0  app
[active_read] registered owner=restore_preload key=/models/clip.safetensors
[active_read] completed owner=restore_preload key=/models/clip.safetensors
[active_read] registered owner=restore_background_unet key=/models/unet.safetensors
[active_read] registered owner=graph_vae key=/models/vae.safetensors
[active_read] completed owner=restore_background_unet key=/models/unet.safetensors
[active_read] completed owner=graph_vae key=/models/vae.safetensors
[model_read_coordinator.summary] enabled=1 acquisitions=1 waited=1 total_wait_ms=0.0 total_hold_ms=31950.0 peak_wait_ms=0.0 timeout_fail_open=0 production_unet_hold_ms=31950.0 graph_vae_wait_ms=0.0 graph_vae_hold_ms=0.0
[waterfall] SUM    known_nonoverlap_total        31950.0  --
[waterfall] OK    full_wall_ms            45000.0  app
"""


_MINIMAL_INCOMPLETE_LOG = """\
[critical_path.flags] critical_path=1 unet_phase=1 validation_phase=1 coordinator=0 coordinator_diag=0 source=module_import
"""


class LogParserTests(unittest.TestCase):
    """Tests for the log parser used in A/B comparison."""

    def _write_temp_log(self, content: str) -> str:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        )
        tmp.write(content)
        tmp.close()
        return tmp.name

    def test_parse_good_run(self):
        path = self._write_temp_log(_GOOD_RUN_LOG)
        result = _parse_log_file(path)
        os.unlink(path)
        # Not all required fields are present in synthetic log,
        # so check specific parsed values instead of full validity.
        self.assertEqual(result.get("user_visible_wall_ms"), 32000.0)
        self.assertEqual(result.get("restore_ms"), 1920.0)
        self.assertEqual(result.get("known_non_overlap_ms"), 20660.0)

    def test_parse_collapsed_run(self):
        path = self._write_temp_log(_COLLAPSED_RUN_2_LOG)
        result = _parse_log_file(path)
        os.unlink(path)
        self.assertEqual(result.get("user_visible_wall_ms"), 45000.0)
        self.assertEqual(result.get("restore_ms"), 4940.0)
        self.assertEqual(result.get("known_non_overlap_ms"), 31950.0)

    def test_flags_parsed(self):
        path = self._write_temp_log(_GOOD_RUN_LOG)
        result = _parse_log_file(path)
        os.unlink(path)
        self.assertEqual(result.get("_coordinator"), "0")
        self.assertEqual(result.get("_critical_path"), "1")

    def test_incomplete_run_rejected(self):
        path = self._write_temp_log(_MINIMAL_INCOMPLETE_LOG)
        result = _parse_log_file(path)
        os.unlink(path)
        self.assertFalse(result.get("valid"))
        self.assertIn("missing_fields", result.get("invalid_reason", ""))

    def test_missing_file(self):
        result = _parse_log_file("/nonexistent/path.log")
        self.assertFalse(result.get("valid"))
        self.assertIn("file not found", result.get("invalid_reason", ""))

    def test_missing_fields_are_null_not_zero(self):
        """Missing timestamps must remain None, not silently substituted with 0."""
        path = self._write_temp_log(_MINIMAL_INCOMPLETE_LOG)
        result = _parse_log_file(path)
        os.unlink(path)
        # All metric columns should be None (not 0) for an incomplete run
        has_any_value = False
        for k in ("restore_ms", "user_visible_wall_ms", "known_non_overlap_ms"):
            if result.get(k) is not None:
                has_any_value = True
                break
        self.assertFalse(has_any_value,
                         "incomplete run should have no metric values")

    def test_coordinator_summary_parsed(self):
        path = self._write_temp_log(_GOOD_RUN_LOG)
        result = _parse_log_file(path)
        os.unlink(path)
        cs = result.get("_coord_summary", {})
        self.assertEqual(cs.get("enabled"), "1")
        self.assertEqual(cs.get("acquisitions"), "1")
        self.assertEqual(cs.get("production_unet_hold_ms"), 20660.0)

    def test_no_causality_in_parser(self):
        """Parser must not declare a winner or claim causality."""
        import inspect
        source = inspect.getsource(sys.modules["tools.compare_model_read_ab"])
        # Check main() and _print_* functions for causal claims.
        # The docstring may mention the constraint (which is fine).
        forbidden = ["prevented_collapse", "saved_ms",
                     "contention_caused", "improvement"]
        for word in forbidden:
            self.assertNotIn(word, source.lower(),
                             f"parser source should not contain '{word}'")
        # Check that main() does not declare a winner.
        # The docstring mentions the constraint, which is acceptable.
        self.assertIn("does not declare a winner", source.lower())

    def test_overlap_parsed_from_intervals(self):
        log = """\
[critical_path.observed.intervals] validation_duration_ms=100.0 exact_prefill_seed_duration_ms=null graph_clip_lookup_duration_ms=null unet_future_total_ms=500.0 graph_unet_wait_duration_ms=50.0 validation_unet_observed_overlap_ms=200.0 exact_prefill_unet_observed_overlap_ms=null
"""
        path = self._write_temp_log(log)
        result = _parse_log_file(path)
        os.unlink(path)
        self.assertEqual(result.get("unet_vae_observed_overlap_ms"), 200.0)

    def test_median(self):
        self.assertEqual(_median([1.0, 2.0, 3.0]), 2.0)
        self.assertEqual(_median([1.0, 2.0]), 1.5)
        self.assertIsNone(_median([]))
        self.assertEqual(_median([None, 5.0, None]), 5.0)

    def test_active_reads_tracked(self):
        log = """\
[active_read] registered owner=restore_preload key=/models/a.safetensors
[active_read] registered owner=restore_background_unet key=/models/b.safetensors
[active_read] completed owner=restore_background_unet key=/models/b.safetensors
"""
        path = self._write_temp_log(log)
        result = _parse_log_file(path)
        os.unlink(path)
        reads = result.get("_active_reads", [])
        self.assertEqual(len(reads), 2)
        self.assertEqual(reads[0]["owner"], "restore_preload")


if __name__ == "__main__":
    unittest.main()
