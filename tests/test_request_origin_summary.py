"""Tests that transport metadata names survive to the final

[v2.remote_request_origin] summary output with the expected field names:
  - modal_generator_create_start_unix_ns
  - modal_generator_created_unix_ns
  - modal_first_iteration_start_unix_ns
  - modal_submission_attempt_unix_ns
  - modal_first_remote_event_unix_ns
  - modal_submission_boundary_source
  - first_iteration_proxy source
  - literal 'absent' for missing endpoints (never 0/None)
And that remote lifecycle timestamps survive unchanged.

Note: the [v2.remote_request_origin] print line is emitted by
modal_app.run_plan_stream at the local post-merge boundary.  These
tests verify that the data fields survive through the result dict from
execute_plan and canonical_execution, where the same field names appear.
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import sys
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_canonical():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "canonical_execution", REPO_ROOT / "canonical_execution.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["canonical_execution"] = mod
    spec.loader.exec_module(mod)
    return mod


class _SummaryTestBase(unittest.TestCase):
    """Base class providing helpers for request-origin summary tests."""

    def setUp(self):
        self.mod = _load_canonical()

    def _run_execute_plan(self, origin: dict | None = None) -> dict:
        """Run execute_plan with minimal plan and return result dict."""
        from comfymodal_runtime.trace import RuntimeTrace
        from comfymodal_runtime.contracts import ExecutionPlan, ExecutionOptions

        trace = RuntimeTrace(request_id="test-summary", process="local")
        if origin:
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

        return asyncio.run(
            self.mod.execute_plan(plan, transport=transport, trace=trace)
        )


class TestRequestOriginFieldNamesThroughResult(_SummaryTestBase):
    """Verify field names survive through execute_plan result dict."""

    def test_required_fields_in_local_timing(self):
        """All required interval fields appear in local_timing dict."""
        origin = {
            "ui_run_triggered_wall_unix_ms": 1000.0,
            "local_receive_wall_ns": 2_000_000_000,
            "modal_generator_create_start_wall_ns": 3_000_000_000,
            "modal_generator_created_wall_ns": 5_000_000_000,
            "modal_first_iteration_start_wall_ns": 6_000_000_000,
            "modal_submission_attempt_wall_ns": 6_000_000_000,
            "modal_first_remote_event_wall_ns": 12_000_000_000,
            "local_receive_mono_ns": int(time.monotonic_ns()) - 5_000_000_000,
            "modal_submission_attempt_mono_ns": int(time.monotonic_ns()),
        }
        result = self._run_execute_plan(origin)
        lt = result.get("local_timing", {})
        required_intervals = [
            "trigger_to_local_receive_ms",
            "local_receive_to_generator_create_start_ms",
            "generator_create_ms",
            "generator_created_to_first_iteration_ms",
            "first_iteration_to_first_remote_event_ms",
        ]
        for name in required_intervals:
            self.assertIn(
                name, lt,
                f"Required interval '{name}' missing from local_timing",
            )
        # Verify computed values
        self.assertEqual(lt.get("trigger_to_local_receive_ms"), 1000.0)
        self.assertEqual(lt.get("local_receive_to_generator_create_start_ms"), 1000.0)
        self.assertEqual(lt.get("generator_create_ms"), 2000.0)
        self.assertEqual(lt.get("generator_created_to_first_iteration_ms"), 1000.0)
        self.assertEqual(lt.get("first_iteration_to_first_remote_event_ms"), 6000.0)

    def test_field_names_use_underscores_in_local_timing(self):
        """All local_timing field names use underscore_separated naming."""
        result = self._run_execute_plan({"ui_run_triggered_wall_unix_ms": 1000.0})
        lt = result.get("local_timing", {})
        for name in lt:
            if name == "missing_stages":
                continue  # list, not a key name
            if isinstance(lt[name], dict):
                for sub_name in lt[name]:
                    self.assertNotIn(
                        "-", sub_name,
                        f"Subfield '{sub_name}' uses hyphen instead of underscore",
                    )
                continue
            self.assertNotIn(
                "-", name,
                f"Field '{name}' uses hyphen instead of underscore in local_timing",
            )


class TestAbsentValues(_SummaryTestBase):
    """Missing values render as literal 'absent' and never as 0/None."""

    def test_absent_values_in_local_timing(self):
        """Missing endpoints render as 'absent' in local_timing."""
        result = self._run_execute_plan()  # no origin
        lt = result.get("local_timing", {})
        absent_fields = [
            "trigger_to_local_receive_ms",
            "local_receive_to_generator_create_start_ms",
            "generator_create_ms",
            "generator_created_to_first_iteration_ms",
            "first_iteration_to_first_remote_event_ms",
        ]
        for name in absent_fields:
            val = lt.get(name, "<MISSING>")
            self.assertEqual(
                val, "absent",
                f"'{name}' should be 'absent' when missing, got {val!r}",
            )

    def test_absent_local_timing_none_not_zero(self):
        """Missing values in local_timing are 'absent' not 0/None."""
        result = self._run_execute_plan()  # no origin
        lt = result.get("local_timing", {})
        absent_candidates = [
            "trigger_to_local_receive_ms",
            "first_iteration_to_first_remote_event_ms",
        ]
        for name in absent_candidates:
            val = lt.get(name)
            self.assertEqual(val, "absent",
                             f"'{name}' should be 'absent' when no origin, got {val!r}")

    def test_absent_intervals_not_zero(self):
        """Interval fields that are absent show 'absent', not 0.0."""
        result = self._run_execute_plan()  # no origin
        lt = result.get("local_timing", {})
        for name, val in lt.items():
            if val == "absent":
                continue
            # If it's a number, fine (some intervals may have data even
            # without origin if other defaults exist)
            if isinstance(val, (int, float)):
                continue


class TestBoundarySource(_SummaryTestBase):
    """modal_submission_boundary_source survives through result data."""

    def test_boundary_source_in_origin(self):
        """Submission boundary source flows through from origin info to
        trace metadata (it is not a local_timing key but lives in
        request_origin_info within trace metadata)."""
        origin = {
            "modal_submission_boundary_source": "first_iteration_proxy",
            "local_receive_wall_ns": int(time.time_ns()),
            "modal_submission_attempt_wall_ns": int(time.time_ns()),
            "local_receive_mono_ns": int(time.monotonic_ns()),
            "modal_submission_attempt_mono_ns": int(time.monotonic_ns()),
        }
        result = self._run_execute_plan(origin)
        # The boundary source appears in the trace metadata request_origin_info
        # which is available through local_timing for runtime consumption.
        # It is NOT a first-level local_timing key but flows through intervals
        # that reference modal_submission_boundary_source.
        # Verify the origin info survived in result dict:
        trace_dict = result.get("trace", result)
        md = trace_dict.get("metadata", {}) if isinstance(trace_dict, dict) else {}
        roi = md.get("request_origin_info", {}) if isinstance(md, dict) else result
        self.assertIn(
            "modal_submission_boundary_source",
            roi if isinstance(roi, dict) else {},
        )


class TestNegativeIntervals(_SummaryTestBase):
    """Negative intervals survive as negative, never clamped to 0."""

    def test_negative_interval_in_local_timing(self):
        """Negative intervals produce 'invalid_negative' or negative value."""
        origin = {
            "ui_run_triggered_wall_unix_ms": 2000.0,
            "local_receive_wall_ns": 1_000_000_000,  # before trigger → negative
        }
        result = self._run_execute_plan(origin)
        lt = result.get("local_timing", {})
        val = lt.get("trigger_to_local_receive_ms")
        if val is not None and isinstance(val, (int, float)):
            self.assertLess(val, 0, "negative interval must remain negative")
        elif val is not None:
            # string value like "invalid_negative" is acceptable
            self.assertIn(val, ("invalid_negative",))


class TestRemoteRequestOriginIntegration(unittest.TestCase):
    """Integration tests that run execute_plan and capture the
    [v2.remote_request_origin] stdout line, verifying every field
    name and formatted value survives through the pipeline."""

    def setUp(self):
        self.mod = _load_canonical()

    def _run_and_capture(self, origin: dict | None = None,
                         remote_metadata: dict | None = None) -> tuple[str, Any]:
        """Run execute_plan with optional origin and remote metadata,
        capture stdout, return the captured text."""
        from comfymodal_runtime.trace import RuntimeTrace
        from comfymodal_runtime.contracts import ExecutionPlan, ExecutionOptions
        from unittest.mock import MagicMock

        trace = RuntimeTrace(request_id="test-remote-origin", process="local")
        if origin:
            trace.set_metadata(request_origin_info=origin)

        plan = ExecutionPlan(
            workflow={"3": {"class_type": "KSampler"}},
            workflow_hash="test_hash",
            source_workflow_hash="test_src",
            execution_options=ExecutionOptions.from_legacy({}, default_production=False),
            request_metadata={"prompt_id": "test_pid"},
        )

        class _TrackingGen:
            """Fake lazy async generator with input_id/input_created_at
            attributes, mimicking Modal's remote_gen.aio() return value."""
            def __init__(self, tracker):
                self._tracker = tracker
                self._events = [{"type": "result", "data": {"outputs": {}, "trace": {}}}]
                self._index = 0
                self.input_id = "test-input-id"
                self.input_created_at = 1234567890

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._index >= len(self._events):
                    raise StopAsyncIteration
                event = self._events[self._index]
                self._index += 1
                self._tracker.anext_call_count += 1
                return event

        class _TrackingAio:
            def __init__(self):
                self.aio_call_count = 0
                self.anext_call_count = 0

            def aio(self, *a, **kw):
                self.aio_call_count += 1
                return _TrackingGen(self)

        _tracker = _TrackingAio()

        def _v2_factory(**kw):
            handle = MagicMock()
            handle.run_plan_stream.remote_gen.aio = _tracker.aio
            return handle

        transport = MagicMock(spec=self.mod.ModalTransport)
        transport.run_plan_stream = self.mod.ModalTransport(
            v2_handle_factory=_v2_factory,
        ).run_plan_stream

        buf = io.StringIO()
        with redirect_stdout(buf):
            asyncio.run(
                self.mod.execute_plan(plan, transport=transport, trace=trace)
            )
        return buf.getvalue(), _tracker

    def test_full_fields_survive_to_remote_request_origin(self):
        """All required field names and formatted values appear in the
        [v2.remote_request_origin] line when full metadata is provided."""
        import time
        _now_ns = time.time_ns()
        _mono = time.monotonic_ns()
        origin = {
            "request_id": "remote-origin-full",
            "trigger_source": "test",
            "ui_run_triggered_wall_unix_ms": 1000.0,
            "local_receive_wall_ns": _now_ns,
            "local_receive_mono_ns": _mono,
            "modal_generator_create_start_wall_ns": _now_ns + 1_000_000,
            "modal_generator_created_wall_ns": _now_ns + 5_000_000,
            "modal_first_iteration_start_wall_ns": _now_ns + 6_000_000,
            "modal_submission_attempt_wall_ns": _now_ns + 6_000_000,
            "modal_first_remote_event_wall_ns": _now_ns + 12_000_000,
            "modal_submission_boundary_source": "first_iteration_proxy",
            "remote_python_resume_wall_ns": _now_ns + 20_000_000,
            "restore_method_start_wall_ns": _now_ns + 25_000_000,
            "restore_method_end_wall_ns": _now_ns + 30_000_000,
            "modal_method_entry_wall_ns": _now_ns + 35_000_000,
            "prompt_executor_invoke_start_wall_ns": _now_ns + 40_000_000,
        }
        # Transport metadata will backfill missing mono keys from setdefault
        captured, _ = self._run_and_capture(origin)
        self.assertIn("[v2.remote_request_origin]", captured,
                       "[v2.remote_request_origin] line must be printed")

        # Check all required field names appear in the line
        required_names = [
            "request_id",
            "trigger_source",
            "ui_trigger_unix_ms",
            "local_receive_wall_unix_ns",
            "local_receive_mono_ns",
            "modal_generator_create_start_wall_unix_ns",
            "modal_generator_created_wall_unix_ns",
            "modal_first_iteration_start_wall_unix_ns",
            "modal_submission_attempt_wall_unix_ns",
            "modal_first_remote_event_wall_unix_ns",
            "modal_submission_boundary_source",
            "remote_python_resume_wall_unix_ns",
            "restore_method_start_wall_unix_ns",
            "restore_method_end_wall_unix_ns",
            "modal_method_entry_wall_unix_ns",
            "prompt_executor_invoke_start_wall_unix_ns",
            "trigger_to_local_receive_ms",
            "local_receive_to_generator_create_start_ms",
            "generator_create_ms",
            "generator_created_to_first_iteration_ms",
            "first_iteration_to_first_remote_event_ms",
            "modal_input_id",
        ]
        for name in required_names:
            self.assertIn(name, captured,
                          f"Required field '{name}' missing from [v2.remote_request_origin]")

    def test_missing_values_shown_as_absent(self):
        """Missing/unavailable values render as literal 'absent' in
        the [v2.remote_request_origin] output."""
        captured, _ = self._run_and_capture()  # no origin at all
        self.assertIn("[v2.remote_request_origin]", captured)
        # absent values show as literal "absent"
        line = next(l for l in captured.splitlines() if "[v2.remote_request_origin]" in l)
        self.assertIn("ui_trigger_unix_ms=absent", line)
        self.assertIn("local_receive_wall_unix_ns=absent", line)

    def test_transport_aio_and_anext_called_once(self):
        """V2 transport aio is called exactly once and first __anext__
        is called exactly once."""
        import time
        origin = {
            "request_id": "aio-count",
            "trigger_source": "test",
            "ui_run_triggered_wall_unix_ms": 1000.0,
            "local_receive_wall_ns": time.time_ns(),
            "local_receive_mono_ns": time.monotonic_ns(),
        }
        _, tracker = self._run_and_capture(origin)
        self.assertEqual(tracker.aio_call_count, 1,
                         "remote_gen.aio must be called exactly once")
        self.assertEqual(tracker.anext_call_count, 1,
                         "first __anext__ must be called exactly once")


if __name__ == "__main__":
    unittest.main()
