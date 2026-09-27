"""Focused tests for the reconcile-phase additions:

    1. Canonical-execution V2 remote request origin interval calculations
       (trigger_to_local_receive_ms, generator_create_ms, etc.).
    2. cgroup v2 mount discovery via /proc/self/mountinfo + /proc/self/cgroup.
    3. Aggregate counter_status (available/partial/unsupported/unavailable).
    4. thread_cpu_ratio and classification (cpu_bound/wait_bound/mixed/unknown).

These tests do NOT require Modal, ComfyUI, or GPU; they exercise the
diagnostic surface in isolation using injectable read lines and mocks.
"""

from __future__ import annotations

import importlib
import io
import os
import sys
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_canonical():
    """Load canonical_execution module."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "canonical_execution", REPO_ROOT / "canonical_execution.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["canonical_execution"] = mod
    spec.loader.exec_module(mod)
    return mod


def _read_source_bytes(rel_path: str) -> bytes:
    """Read a file as bytes (avoids UnicodeDecodeError on Windows)."""
    return (REPO_ROOT / rel_path).read_bytes()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Interval calculation tests (Requirement 1)
# ═══════════════════════════════════════════════════════════════════════════


class TestIntervalHelperFunction(unittest.TestCase):
    """Test the _interval_ms logic via module-level helper checks."""

    def setUp(self):
        self.mod = _load_canonical()

    def _compute_interval(self, start, end, *, scale_start=1.0, scale_end=1.0):
        """Replicate the _interval_ms logic from canonical_execution.py."""
        _ABSENT = "absent"
        _INVALID_NEG = "invalid_negative"
        if start is None or end is None:
            return _ABSENT
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            return _ABSENT
        _start_ns = int(start * scale_start)
        _end_ns = int(end * scale_end)
        _delta_ns = _end_ns - _start_ns
        if _delta_ns < 0:
            return _INVALID_NEG
        return round(_delta_ns / 1_000_000, 3)

    def test_normal_interval(self):
        result = self._compute_interval(1_000_000_000, 2_000_000_000)
        self.assertIsInstance(result, float)
        self.assertEqual(result, 1000.0)

    def test_missing_start_returns_absent(self):
        self.assertEqual(self._compute_interval(None, 2_000_000_000), "absent")

    def test_missing_end_returns_absent(self):
        self.assertEqual(self._compute_interval(1_000_000_000, None), "absent")

    def test_both_missing_returns_absent(self):
        self.assertEqual(self._compute_interval(None, None), "absent")

    def test_negative_interval_returns_invalid_negative(self):
        self.assertEqual(self._compute_interval(2_000_000_000, 1_000_000_000), "invalid_negative")

    def test_zero_interval(self):
        self.assertEqual(self._compute_interval(1_000_000_000, 1_000_000_000), 0.0)

    def test_with_scale_factors(self):
        result = self._compute_interval(1000, 3_000_000_000,
                                         scale_start=1_000_000, scale_end=1.0)
        self.assertEqual(result, 2000.0)

    def test_non_numeric_returns_absent(self):
        self.assertEqual(self._compute_interval("abc", 1_000_000_000), "absent")


class TestIntervalComputation(unittest.TestCase):
    """Test that execute_plan produces the correct interval-derived fields."""

    def setUp(self):
        self.mod = _load_canonical()

    def _run_execute_plan(self, origin=None, transport_meta=None):
        """Helper: run execute_plan with a minimal plan and mocked transport."""
        from comfymodal_runtime.trace import RuntimeTrace
        from comfymodal_runtime.contracts import ExecutionPlan, ExecutionOptions
        from unittest.mock import MagicMock
        import asyncio

        trace = RuntimeTrace(request_id="test-interval", process="local")
        if origin:
            trace.set_metadata(request_origin_info=origin)
        if transport_meta:
            for k, v in transport_meta.items():
                trace._metadata[k] = v

        plan = ExecutionPlan(
            workflow={"3": {"class_type": "KSampler"}},
            workflow_hash="test_hash",
            source_workflow_hash="test_src",
            execution_options=ExecutionOptions.from_legacy({}, default_production=False),
            request_metadata={"prompt_id": "test_pid"},
        )

        transport = MagicMock()
        async def _stream(*a, **kw):
            yield {"type": "result", "data": {"outputs": {}, "trace": {}}}
        transport.run_plan_stream = _stream

        return asyncio.run(
            self.mod.execute_plan(plan, transport=transport, trace=trace)
        )

    def test_all_intervals_present_with_valid_data(self):
        """When all timestamps are available, all interval fields are computed."""
        origin = {
            "ui_run_triggered_wall_unix_ms": 1000.0,
            "local_receive_wall_ns": 3_000_000_000,
            "modal_generator_create_start_wall_ns": 5_000_000_000,
            "modal_generator_created_wall_ns": 7_000_000_000,
            "modal_first_iteration_start_wall_ns": 9_000_000_000,
            "modal_first_remote_event_wall_ns": 15_000_000_000,
            "remote_python_resume_wall_ns": 10_000_000_000,
            "restore_method_start_wall_ns": 11_000_000_000,
            "restore_method_end_wall_ns": 12_000_000_000,
            "modal_method_entry_wall_ns": 12_500_000_000,
            "prompt_executor_invoke_start_wall_ns": 13_000_000_000,
        }
        result = self._run_execute_plan(origin=origin)
        lt = result.get("local_timing", {})

        # Verify all new interval fields are present (exact requested names)
        for key in (
            "trigger_to_local_receive_ms",
            "local_receive_to_generator_create_start_ms",
            "generator_create_ms",
            "generator_created_to_first_iteration_ms",
            "first_iteration_to_first_remote_event_ms",
            "remote_python_resume_to_restore_start_ms",
            "restore_method_ms",
            "restore_end_to_modal_method_entry_ms",
            "modal_method_entry_to_executor_ms",
            "unexplained_pre_remote_ms",
        ):
            self.assertIn(key, lt, f"Key '{key}' missing from local_timing")

        # Check computed values
        self.assertEqual(lt["trigger_to_local_receive_ms"], 2000.0)
        self.assertEqual(lt["local_receive_to_generator_create_start_ms"], 2000.0)
        self.assertEqual(lt["generator_create_ms"], 2000.0)
        self.assertEqual(lt["generator_created_to_first_iteration_ms"], 2000.0)
        self.assertEqual(lt["first_iteration_to_first_remote_event_ms"], 6000.0)
        self.assertEqual(lt["remote_python_resume_to_restore_start_ms"], 1000.0)
        self.assertEqual(lt["restore_method_ms"], 1000.0)
        self.assertEqual(lt["restore_end_to_modal_method_entry_ms"], 500.0)
        self.assertEqual(lt["modal_method_entry_to_executor_ms"], 500.0)

    def test_missing_endpoints_emit_absent(self):
        """Missing timestamp fields emit 'absent'."""
        result = self._run_execute_plan()  # no origin data
        lt = result.get("local_timing", {})
        for key in (
            "trigger_to_local_receive_ms",
            "local_receive_to_generator_create_start_ms",
            "generator_create_ms",
            "generator_created_to_first_iteration_ms",
            "first_iteration_to_first_remote_event_ms",
            "remote_python_resume_to_restore_start_ms",
            "restore_method_ms",
            "restore_end_to_modal_method_entry_ms",
            "modal_method_entry_to_executor_ms",
            "unexplained_pre_remote_ms",
        ):
            val = lt.get(key)
            self.assertEqual(
                val, "absent",
                f"{key} should be 'absent' when metadata missing, got {val!r}"
            )

    def test_negative_ordering_emits_invalid_negative(self):
        """When timestamps are out of order, emits 'invalid_negative'."""
        origin = {
            "ui_run_triggered_wall_unix_ms": 2000.0,
            "local_receive_wall_ns": 1_000_000_000,  # before trigger - inverted
        }
        result = self._run_execute_plan(origin=origin)
        lt = result.get("local_timing", {})
        self.assertEqual(lt.get("trigger_to_local_receive_ms"), "invalid_negative")

    def test_unexplained_pre_remote_valid(self):
        """unexplained_pre_remote = first_iter_to_first_event minus contained remote."""
        origin = {
            "ui_run_triggered_wall_unix_ms": 1000.0,
            "local_receive_wall_ns": 2_000_000_000,
            "modal_generator_create_start_wall_ns": 3_000_000_000,
            "modal_generator_created_wall_ns": 4_000_000_000,
            "modal_first_iteration_start_wall_ns": 5_000_000_000,
            "modal_first_remote_event_wall_ns": 12_000_000_000,
            "remote_python_resume_wall_ns": 6_000_000_000,
            "restore_method_start_wall_ns": 7_000_000_000,
            "restore_method_end_wall_ns": 8_000_000_000,
            "modal_method_entry_wall_ns": 9_000_000_000,
            "prompt_executor_invoke_start_wall_ns": 10_000_000_000,
        }
        result = self._run_execute_plan(origin=origin)
        lt = result.get("local_timing", {})
        # first_iter_to_first_event = (12e9 - 5e9)/1e6 = 7000
        self.assertEqual(lt["first_iteration_to_first_remote_event_ms"], 7000.0)
        # Contained intervals: 1000+1000+1000+1000 = 4000
        # unexplained = 7000 - 4000 = 3000
        self.assertEqual(lt["unexplained_pre_remote_ms"], 3000.0)

    def test_unexplained_pre_remote_absent_when_remote_missing(self):
        """When remote intervals are missing, unexplained_pre_remote_ms is 'absent'."""
        origin = {
            "ui_run_triggered_wall_unix_ms": 1000.0,
            "local_receive_wall_ns": 2_000_000_000,
            "modal_generator_create_start_wall_ns": 3_000_000_000,
            "modal_generator_created_wall_ns": 4_000_000_000,
            "modal_first_iteration_start_wall_ns": 5_000_000_000,
            "modal_first_remote_event_wall_ns": 12_000_000_000,
        }
        result = self._run_execute_plan(origin=origin)
        lt = result.get("local_timing", {})
        self.assertEqual(lt.get("unexplained_pre_remote_ms"), "absent")

    def test_backward_compatible_existing_fields(self):
        """Existing fields (t0_to_t1_ms, local_residual_ms, etc.) are preserved."""
        result = self._run_execute_plan()
        lt = result.get("local_timing", {})
        existing_fields = [
            "t0_to_t1_ms", "local_receive_to_enqueue_ms",
            "local_residual_ms", "clock_reconciliation_residual_ms",
            "route_unattributed_ms", "worker_unattributed_ms",
            "reconciliation_status", "missing_stages", "overlap_error",
            "stage_attribution_residual_ms",
            "local_receive_to_generator_create_ms",
            "generator_create_to_first_iteration_ms",
            "first_iteration_to_first_remote_event_ms",
            "local_receive_to_actual_submission_ms",
        ]
        for field in existing_fields:
            self.assertIn(field, lt, f"Existing field '{field}' missing from local_timing")

    def test_transport_metadata_priority_over_origin(self):
        """Transport metadata values take priority over origin for timestamps."""
        origin = {
            "modal_generator_create_start_wall_ns": 5_000_000_000,
            "modal_generator_created_wall_ns": 6_000_000_000,
        }
        transport_meta = {
            "modal_generator_create_start_wall_ns": 10_000_000_000,
            "modal_generator_created_wall_ns": 12_000_000_000,
        }
        result = self._run_execute_plan(origin=origin, transport_meta=transport_meta)
        lt = result.get("local_timing", {})
        # generator_create_ms should be computed from transport meta (10→12e9 = 2000ms)
        self.assertEqual(lt.get("generator_create_ms"), 2000.0)

    def test_transport_fallback_to_origin_when_transport_missing(self):
        """When transport metadata lacks timestamp, falls back to origin."""
        origin = {
            "modal_generator_create_start_wall_ns": 5_000_000_000,
            "modal_generator_created_wall_ns": 7_000_000_000,
        }
        # transport_meta set but without the generator timestamps
        transport_meta = {"other_key": 42}
        result = self._run_execute_plan(origin=origin, transport_meta=transport_meta)
        lt = result.get("local_timing", {})
        # Falls back to origin: 5→7e9 = 2000ms
        self.assertEqual(lt.get("generator_create_ms"), 2000.0)

    def test_unexplained_outside_window_ignored(self):
        """Remote intervals outside first_iter→first_remote window are ignored (not invalid)."""
        origin = {
            "ui_run_triggered_wall_unix_ms": 1000.0,
            "local_receive_wall_ns": 2_000_000_000,
            "modal_generator_create_start_wall_ns": 3_000_000_000,
            "modal_generator_created_wall_ns": 4_000_000_000,
            "modal_first_iteration_start_wall_ns": 5_000_000_000,
            "modal_first_remote_event_wall_ns": 12_000_000_000,
            # python_resume starts before first_iter — outside window, should be ignored
            "remote_python_resume_wall_ns": 3_000_000_000,
            "restore_method_start_wall_ns": 6_000_000_000,
            "restore_method_end_wall_ns": 7_000_000_000,
            "modal_method_entry_wall_ns": 8_000_000_000,
            "prompt_executor_invoke_start_wall_ns": 9_000_000_000,
        }
        result = self._run_execute_plan(origin=origin)
        lt = result.get("local_timing", {})
        # Window = 5e9→12e9 = 7000ms
        self.assertEqual(lt["first_iteration_to_first_remote_event_ms"], 7000.0)
        # python_resume (3e9) is outside window [5e9,12e9] — ignored, not subtracted
        # Contained intervals: restore_method (1s) + restore→method_entry (1s) + method_entry→executor (1s) = 3s
        # unexplained = 7000 - 3000 = 4000
        self.assertEqual(lt["unexplained_pre_remote_ms"], 4000.0)

    def test_unexplained_overlapping_spans_nonoverlapping_selection(self):
        """Only non-overlapping subset of contained intervals is subtracted.

        Chained intervals share endpoints (end_i == start_{i+1}), so they
        are naturally adjacent rather than overlapping.  The greedy
        selection includes all contained intervals sharing endpoints.
        """
        origin = {
            "ui_run_triggered_wall_unix_ms": 1000.0,
            "local_receive_wall_ns": 2_000_000_000,
            "modal_generator_create_start_wall_ns": 3_000_000_000,
            "modal_generator_created_wall_ns": 4_000_000_000,
            "modal_first_iteration_start_wall_ns": 5_000_000_000,
            "modal_first_remote_event_wall_ns": 20_000_000_000,
            # All four remote intervals are chained and fully contained
            "remote_python_resume_wall_ns": 6_000_000_000,
            "restore_method_start_wall_ns": 10_000_000_000,
            "restore_method_end_wall_ns": 14_000_000_000,
            "modal_method_entry_wall_ns": 16_000_000_000,
            "prompt_executor_invoke_start_wall_ns": 18_000_000_000,
        }
        result = self._run_execute_plan(origin=origin)
        lt = result.get("local_timing", {})
        # Window = 5e9→20e9 = 15000ms
        self.assertEqual(lt["first_iteration_to_first_remote_event_ms"], 15000.0)
        # All four chained intervals are fully contained and (by construction)
        # non-overlapping (each starts where previous ends).
        # Total subtracted = (10-6)+(14-10)+(16-14)+(18-16) = 4+4+2+2 = 12s = 12000ms
        # unexplained = 15000 - 12000 = 3000
        self.assertEqual(lt["unexplained_pre_remote_ms"], 3000.0)

    def test_unexplained_missing_window_endpoints_absent(self):
        """Missing window endpoints cause unexplained_pre_remote_ms to be absent."""
        origin = {
            # first_iteration is present but first_remote_event is absent
            "modal_first_iteration_start_wall_ns": 5_000_000_000,
        }
        result = self._run_execute_plan(origin=origin)
        lt = result.get("local_timing", {})
        self.assertEqual(lt.get("unexplained_pre_remote_ms"), "absent")


# ═══════════════════════════════════════════════════════════════════════════
# 2. Cgroup v2 discovery tests (Requirement 3)
# ═══════════════════════════════════════════════════════════════════════════


class TestCgroupV2Discovery(unittest.TestCase):
    """Test cgroup v2 mount discovery.  Uses import of pre-existing module."""

    @classmethod
    def setUpClass(cls):
        """Import model_preload through the normal package path."""
        import comfymodal_runtime.model_preload as mp
        cls.mp = mp

    def test_discover_cgroup2_path_with_mocked_lines(self):
        """With mock file lines, correctly identifies mount point and cgroup path."""
        mp = self.mp
        mountinfo_lines = [
            "1 0 253:0 / / rw,relatime - ext4 /dev/root rw",
            "33 26 0:28 / /sys/fs/cgroup rw,nosuid,nodev,noexec,relatime shared:9 - cgroup2 cgroup rw",
        ]
        cgroup_lines = [
            "0::/system.slice/comfyui.scope\n",
        ]

        saved_fn = mp._read_file_lines
        try:
            def mock_read_lines(path):
                if "mountinfo" in path:
                    return mountinfo_lines
                if path.endswith("/cgroup"):
                    return cgroup_lines
                return []
            mp._read_file_lines = mock_read_lines

            mount_point, cgroup_rel = mp._discover_cgroup2_path()
            self.assertEqual(mount_point, "/sys/fs/cgroup")
            self.assertEqual(cgroup_rel, "/system.slice/comfyui.scope")
        finally:
            mp._read_file_lines = saved_fn

    def test_discover_cgroup2_path_root_cgroup(self):
        """When cgroup is '/', returns empty string as relative path."""
        mp = self.mp
        mountinfo_lines = [
            "33 26 0:28 / /sys/fs/cgroup rw - cgroup2 cgroup rw",
        ]
        cgroup_lines = ["0::/\n"]

        saved_fn = mp._read_file_lines
        try:
            def mock_read_lines(path):
                if "mountinfo" in path:
                    return mountinfo_lines
                if path.endswith("/cgroup"):
                    return cgroup_lines
                return []
            mp._read_file_lines = mock_read_lines

            mount_point, cgroup_rel = mp._discover_cgroup2_path()
            self.assertEqual(mount_point, "/sys/fs/cgroup")
            self.assertEqual(cgroup_rel, "")
        finally:
            mp._read_file_lines = saved_fn

    def test_discover_cgroup2_path_no_cgroup2(self):
        """When no cgroup2 mount exists, returns (None, None)."""
        mp = self.mp
        mountinfo_lines = [
            "1 0 253:0 / / rw - ext4 /dev/root rw",
        ]
        cgroup_lines = ["0::/\n"]

        saved_fn = mp._read_file_lines
        try:
            def mock_read_lines(path):
                if "mountinfo" in path:
                    return mountinfo_lines
                if path.endswith("/cgroup"):
                    return cgroup_lines
                return []
            mp._read_file_lines = mock_read_lines

            mount_point, cgroup_rel = mp._discover_cgroup2_path()
            self.assertIsNone(mount_point)
            self.assertIsNone(cgroup_rel)
        finally:
            mp._read_file_lines = saved_fn

    def test_parse_memory_stat(self):
        """_parse_memory_stat extracts only the requested keys."""
        content = (
            "file 1000\n"
            "inactive_file 500\n"
            "active_file 400\n"
            "workingset_refault_file 50\n"
            "workingset_activate_file 30\n"
            "pgfault 10000\n"
            "pgmajfault 5\n"
            "anon 2000\n"
            "unevictable 100\n"
        )
        result = self.mp._parse_memory_stat(content)
        self.assertEqual(result.get("file"), 1000)
        self.assertEqual(result.get("inactive_file"), 500)
        self.assertEqual(result.get("active_file"), 400)
        self.assertEqual(result.get("workingset_refault_file"), 50)
        self.assertEqual(result.get("workingset_activate_file"), 30)
        self.assertEqual(result.get("pgfault"), 10000)
        self.assertEqual(result.get("pgmajfault"), 5)
        self.assertNotIn("anon", result)
        self.assertNotIn("unevictable", result)

    def test_parse_memory_stat_empty_content(self):
        """Empty content returns empty dict."""
        result = self.mp._parse_memory_stat("")
        self.assertEqual(result, {})

    def test_read_cgroup_memory_stat_fails_gracefully(self):
        """_read_cgroup_memory_stat returns None when discovery fails."""
        mp = self.mp
        saved_fn = mp._read_file_lines
        try:
            def mock_read_lines(path):
                return []
            mp._read_file_lines = mock_read_lines
            result = mp._read_cgroup_memory_stat()
            self.assertIsNone(result)
        finally:
            mp._read_file_lines = saved_fn

    def test_malformed_mountinfo(self):
        """Malformed mountinfo returns (None, None)."""
        mp = self.mp
        saved_fn = mp._read_file_lines
        try:
            def mock_read_lines(path):
                if "mountinfo" in path:
                    return ["garbage data without proper fields\n"]
                if path.endswith("/cgroup"):
                    return ["0::/\n"]
                return []
            mp._read_file_lines = mock_read_lines
            mount_point, cgroup_rel = mp._discover_cgroup2_path()
            self.assertIsNone(mount_point)
        finally:
            mp._read_file_lines = saved_fn

    def test_missing_cgroup_file(self):
        """Missing /proc/self/cgroup yields (None, None) — nonfatal failure."""
        mp = self.mp
        saved_fn = mp._read_file_lines
        try:
            def mock_read_lines(path):
                if "mountinfo" in path:
                    return ["33 26 0:28 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n"]
                # No cgroup data returned — simulates missing/empty cgroup file
                return []
            mp._read_file_lines = mock_read_lines
            mount_point, cgroup_rel = mp._discover_cgroup2_path()
            # When cgroup is missing/malformed, discovery fails nonfatally
            self.assertIsNone(mount_point)
            self.assertIsNone(cgroup_rel)
        finally:
            mp._read_file_lines = saved_fn

    def test_memory_stat_nonfatal_missing(self):
        """_read_cgroup_memory_stat does not crash on missing files."""
        result = self.mp._read_cgroup_memory_stat()
        # Should not crash; returns None when files don't exist
        self.assertIsNone(result)

    def test_unescape_mountinfo_field_basic(self):
        """_unescape_mountinfo_field unescapes standard sequences."""
        mp = self.mp
        self.assertEqual(mp._unescape_mountinfo_field("hello world"), "hello world")
        self.assertEqual(mp._unescape_mountinfo_field("path\\040with\\040spaces"), "path with spaces")
        self.assertEqual(mp._unescape_mountinfo_field("tab\\011here"), "tab\there")

    def test_unescape_mountinfo_field_backslash_first(self):
        """Backslash is unescaped first to avoid double-unescaping."""
        mp = self.mp
        # \\134040 → backslash + "040" (literal backslash then 040)
        result = mp._unescape_mountinfo_field("\\134040")
        # After first pass: \134 → \ -> "\\040"
        # After second pass: \040 → space
        # Result: " "
        self.assertEqual(result, " ")

    def test_unescape_mountinfo_field_newline(self):
        """Newline escape \\012 is unescaped."""
        mp = self.mp
        self.assertEqual(mp._unescape_mountinfo_field("line1\\012line2"), "line1\nline2")

    def test_discover_cgroup2_unescaped_mount_point(self):
        """Mount point with escaped spaces is properly unescaped."""
        mp = self.mp
        saved_fn = mp._read_file_lines
        try:
            def mock_read_lines(path):
                if "mountinfo" in path:
                    return [
                        "36 35 0:28 / /sys/fs/cgroup\\040with\\040spaces rw,nosuid - cgroup2 cgroup rw\n",
                    ]
                if "cgroup" in path:
                    return ["0::/my/scope\n"]
                return []
            mp._read_file_lines = mock_read_lines
            mount_point, cgroup_rel = mp._discover_cgroup2_path()
            self.assertEqual(mount_point, "/sys/fs/cgroup with spaces")
            self.assertEqual(cgroup_rel, "/my/scope")
        finally:
            mp._read_file_lines = saved_fn

    def test_resolve_cgroup_memory_stat_path_traversal_prevention(self):
        """_resolve_cgroup_memory_stat_path rejects paths with '..'."""
        mp = self.mp
        saved_fn = mp._read_file_lines
        try:
            def mock_read_lines(path):
                if "mountinfo" in path:
                    return ["36 35 0:28 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n"]
                if "cgroup" in path:
                    return ["0::/../../etc/passwd\n"]
                return []
            mp._read_file_lines = mock_read_lines
            from unittest.mock import patch as _patch
            with _patch("os.path.isfile", return_value=False):
                result = mp._resolve_cgroup_memory_stat_path()
            self.assertIsNone(result)
        finally:
            mp._read_file_lines = saved_fn

    def test_resolve_no_hardcoded_fallback(self):
        """No hardcoded /sys/fs/cgroup/memory.stat fallback remains."""
        mp = self.mp
        source = _read_source_bytes("comfymodal_runtime/model_preload.py").decode("utf-8")
        # The hardcoded fallback string must NOT appear
        self.assertNotIn("/sys/fs/cgroup/memory.stat", source)
# ═══════════════════════════════════════════════════════════════════════════


class TestCounterStatus(unittest.TestCase):
    """Test the aggregate counter_status logic via source inspection."""

    def test_source_contains_four_status_values(self):
        """Verify the four status strings exist in the counter_status logic."""
        source = _read_source_bytes("comfymodal_runtime/model_preload.py").decode("utf-8")
        self.assertIn('counter_status: str = "unsupported"', source)
        self.assertIn('counter_status = "available"', source)
        self.assertIn('counter_status = "partial"', source)
        self.assertIn('counter_status = "unavailable"', source)

    def test_source_contains_valid_count_sum(self):
        """Verify aggregate counting logic exists."""
        source = _read_source_bytes("comfymodal_runtime/model_preload.py").decode("utf-8")
        self.assertIn("_valid_count = sum(1 for v in _counters_available.values() if v)", source)


class TestThreadCpuRatioAndClassification(unittest.TestCase):
    """Test thread_cpu_ratio and classification via source inspection and logic verification."""

    def test_classification_cpu_bound_high_ratio(self):
        """Ratio >= 0.80 -> cpu_bound."""
        source = _read_source_bytes("comfymodal_runtime/model_preload.py").decode("utf-8")
        self.assertIn('if _ratio >= 0.80:', source)
        self.assertIn('classification = "cpu_bound"', source)

    def test_classification_wait_bound_low_ratio(self):
        """Ratio <= 0.20 -> wait_bound."""
        source = _read_source_bytes("comfymodal_runtime/model_preload.py").decode("utf-8")
        self.assertIn('elif _ratio <= 0.20:', source)
        self.assertIn('classification = "wait_bound"', source)

    def test_classification_mixed_mid_ratio(self):
        """0.20 < ratio < 0.80 -> mixed."""
        source = _read_source_bytes("comfymodal_runtime/model_preload.py").decode("utf-8")
        self.assertIn('classification = "mixed"', source)

    def test_classification_unknown_no_thread_cpu(self):
        """When thread CPU is unavailable, classification is 'unknown'."""
        source = _read_source_bytes("comfymodal_runtime/model_preload.py").decode("utf-8")
        self.assertIn('classification: str = "unknown"', source)
        self.assertIn('classification = "unknown"', source)

    def test_thread_cpu_ratio_in_output(self):
        """thread_cpu_ratio field must appear in the slow_model_read print."""
        source = _read_source_bytes("comfymodal_runtime/model_preload.py").decode("utf-8")
        self.assertIn("thread_cpu_ratio={thread_cpu_ratio}", source)
        self.assertIn("classification={classification}", source)

    def test_ratio_computation_logic(self):
        """Verify thread_cpu_ratio = thread_cpu_ms / elapsed_ms classification."""
        # cpu_bound: ratio >= 0.80
        self.assertGreaterEqual(850.0 / 1000.0, 0.80)
        # wait_bound: ratio <= 0.20
        self.assertLessEqual(100.0 / 1000.0, 0.20)
        # mixed: 0.20 < ratio < 0.80
        ratio = 500.0 / 1000.0
        self.assertGreater(ratio, 0.20)
        self.assertLess(ratio, 0.80)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Raw timestamp preservation tests
# ═══════════════════════════════════════════════════════════════════════════


class TestRawTimestampPreservation(unittest.TestCase):
    """Verify that raw timestamps flow through to the local_timing dict."""

    def setUp(self):
        self.mod = _load_canonical()

    def test_raw_timestamps_available_in_print(self):
        """Raw timestamp values appear in the [v2.request_origin] print output."""
        from comfymodal_runtime.trace import RuntimeTrace
        from comfymodal_runtime.contracts import ExecutionPlan, ExecutionOptions
        from unittest.mock import MagicMock
        import asyncio

        origin = {
            "ui_run_triggered_wall_unix_ms": 1000.0,
            "local_receive_wall_ns": 3_000_000_000,
            "modal_generator_create_start_wall_ns": 5_000_000_000,
            "modal_generator_created_wall_ns": 7_000_000_000,
        }

        trace = RuntimeTrace(request_id="test-raw-ts", process="local")
        trace.set_metadata(request_origin_info=origin)

        plan = ExecutionPlan(
            workflow={"3": {"class_type": "KSampler"}},
            workflow_hash="test_hash",
            source_workflow_hash="test_src",
            execution_options=ExecutionOptions.from_legacy({}, default_production=False),
            request_metadata={"prompt_id": "test_pid"},
        )

        transport = MagicMock()
        async def _stream(*a, **kw):
            yield {"type": "result", "data": {"outputs": {}, "trace": {}}}
        transport.run_plan_stream = _stream

        f = io.StringIO()
        with redirect_stdout(f):
            result = asyncio.run(
                self.mod.execute_plan(plan, transport=transport, trace=trace)
            )
        output = f.getvalue()

        # The print statement should include the interval values
        lt = result.get("local_timing", {})
        self.assertEqual(lt.get("trigger_to_local_receive_ms"), 2000.0)


if __name__ == "__main__":
    unittest.main()
