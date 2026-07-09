"""Regression tests for _log_cold_start_waterfall UnboundLocalError bug.

The variable ``submit2entry_raw`` is only assigned inside the
``if t2 is not None and t3 is not None:`` block (comfyapp.py ~line 1666),
but is referenced later at lines 1739 and 1773 even when that branch was
never entered (t2 or t3 missing).  This set of tests exercises every
combination to prevent a recurrence.
"""

import os
import sys
import unittest
from pathlib import Path

# Ensure tests/ is importable so we can reuse load_module from the sibling
_tests_dir = Path(__file__).resolve().parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))

from test_comfyapp_runtime_state import load_module


# Module-level skip: the waterfull helper prints a lot; suppress for clean
# test output.  We also block COMFYMODAL_DISABLE_WATERFALL so the function
# actually runs.
os.environ.pop("COMFYMODAL_DISABLE_WATERFALL", None)


def _make_summary(stages=None, deltas=None, restore=None):
    """Build a dict shaped like a trace ``summary()``."""
    return {
        "stages": stages or {},
        "deltas_ms": deltas or {},
        "restore": restore or {},
        "derived_ms": {},
        "prompt_id": "test-prompt-00001",
    }


class ColdStartWaterfallUnboundLocalTests(unittest.TestCase):
    """Every test should execute without raising UnboundLocalError."""

    def setUp(self):
        self.mod = load_module()
        # Ensure printing is suppressed so test output stays clean
        # (the function prints directly, but we just verify no crash)
        self._old_disable = os.environ.get("COMFYMODAL_DISABLE_WATERFALL")

    def tearDown(self):
        if self._old_disable is not None:
            os.environ["COMFYMODAL_DISABLE_WATERFALL"] = self._old_disable
        else:
            os.environ.pop("COMFYMODAL_DISABLE_WATERFALL", None)

    # ── both t2 and t3 present (happy path) ──────────────────────────

    def test_both_t2_t3_present(self):
        """submit2entry_raw is assigned — no crash."""
        s = _make_summary(
            stages={"t2_local_dispatch": 1000.0, "t3_modal_entry": 1500.0},
            deltas={"t2_to_t3": 500.0},
        )
        # Should not raise
        self.mod._log_cold_start_waterfall(s, label="test")

    def test_both_t2_t3_with_restore_included(self):
        """restore_incl_in_submit2entry=True with both timestamps — no crash."""
        s = _make_summary(
            stages={"t2_local_dispatch": 1000.0, "t3_modal_entry": 2000.0},
            restore={"restore_total_ms": 300.0, "restore_incl_in_submit2entry": True},
        )
        self.mod._log_cold_start_waterfall(s, label="test")

    # ── missing t2 only ──────────────────────────────────────────────

    def test_missing_t2(self):
        """t2 is None → submit2entry_raw never assigned — must not crash."""
        s = _make_summary(
            stages={"t3_modal_entry": 1500.0},
            deltas={"t2_to_t3": 500.0},
        )
        self.mod._log_cold_start_waterfall(s, label="test")

    def test_missing_t2_with_restore(self):
        """t2 is None + restore data — must not crash on submit2entry_raw ref."""
        s = _make_summary(
            stages={"t3_modal_entry": 1500.0},
            restore={"restore_total_ms": 300.0, "restore_incl_in_submit2entry": True},
        )
        self.mod._log_cold_start_waterfall(s, label="test")

    # ── missing t3 only ──────────────────────────────────────────────

    def test_missing_t3(self):
        """t3 is None → submit2entry_raw never assigned — must not crash."""
        s = _make_summary(
            stages={"t2_local_dispatch": 1000.0},
            deltas={"t2_to_t3": 500.0},
        )
        self.mod._log_cold_start_waterfall(s, label="test")

    def test_missing_t3_with_restore(self):
        """t3 is None + restore data — must not crash."""
        s = _make_summary(
            stages={"t2_local_dispatch": 1000.0},
            restore={"restore_total_ms": 300.0, "restore_incl_in_submit2entry": True},
        )
        self.mod._log_cold_start_waterfall(s, label="test")

    # ── missing both t2 and t3 ───────────────────────────────────────

    def test_missing_both_t2_and_t3(self):
        """Both t2 and t3 are None — variable never assigned — must not crash."""
        s = _make_summary(deltas={"t2_to_t3": 500.0})
        self.mod._log_cold_start_waterfall(s, label="test")

    def test_missing_both_with_restore(self):
        """Both t2 and t3 are None + restore data — must not crash."""
        s = _make_summary(
            restore={"restore_total_ms": 300.0, "restore_incl_in_submit2entry": True},
        )
        self.mod._log_cold_start_waterfall(s, label="test")

    # ── failure-label path with incomplete timestamps ────────────────

    def test_failure_label_missing_t2(self):
        """Failure-path label with t2 missing — must not crash."""
        s = _make_summary(
            stages={"t3_modal_entry": 2000.0},
        )
        self.mod._log_cold_start_waterfall(s, label="run_prompt_stream_in_process_failure")

    def test_failure_label_missing_t3(self):
        """Failure-path label with t3 missing — must not crash."""
        s = _make_summary(
            stages={"t2_local_dispatch": 1000.0},
        )
        self.mod._log_cold_start_waterfall(s, label="run_prompt_stream_in_process_failure")

    def test_failure_label_missing_both(self):
        """Failure-path label with both t2 and t3 missing — must not crash."""
        s = _make_summary(
            stages={"t0_client_press": 500.0},
        )
        self.mod._log_cold_start_waterfall(s, label="run_prompt_stream_in_process_failure")

    # ── empty / degenerate inputs ────────────────────────────────────

    def test_empty_summary(self):
        """Empty summary dict — must not crash."""
        self.mod._log_cold_start_waterfall({}, label="test")

    def test_non_dict_input(self):
        """Non-dict input (e.g. None) — function returns early, no crash."""
        self.mod._log_cold_start_waterfall(None, label="test")
        self.mod._log_cold_start_waterfall("string", label="test")
        self.mod._log_cold_start_waterfall(42, label="test")


if __name__ == "__main__":
    unittest.main()
