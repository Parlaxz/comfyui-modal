"""Host-side submission/startup timeline breakdown (V2 pass 2, instrumentation).

``tools/benchmark_v2_direct.py`` emits a single-line
``[v2.host_submission_breakdown]`` record per completed run decomposing the
proven ~17s ``local_receive → modal_submission_attempt`` registry-init cost
(benchmark-only) plus the Modal scheduling interval.  The line is built by the
pure ``build_host_submission_breakdown_line(...)`` function so it is fully
unit-testable offline.

Covered here (all synthetic, no Modal / no network):
  1. Every field renders with sane values when all stamps exist.
  2. Missing stamps render ``absent`` (never 0, never a crash).
  3. A missing ``COMFYMODAL_COMMAND_START_UNIX_MS`` (command_start=None)
     makes only the command→python-first-line field absent.
  4. The submission boundary source is documented as ``first_anext``.
  5. All three scheduling-source values round-trip.
  6. The segment chain reconciles to ``local_receive_to_submission_ms``.
  7. A run where ``_ensure_full_node_registry`` never ran (no registry
     stamps) degrades to ``absent`` registry fields without raising.
  8. Event-derived fallbacks fill gaps the existing local_timing lacks.
"""

import unittest
from typing import Any

from tools.benchmark_v2_direct import (
    _HOST_SUBMISSION_BOUNDARY_SOURCE,
    build_host_submission_breakdown_line,
)

_REQ = "req-host-submission-1"
_NS_PER_MS = 1_000_000
# Fixed epoch-ns base so absolute wall timestamps are deterministic.
_BASE_NS = 1_700_000_000_000_000_000
# command_start_unix_ms must equal _BASE_NS in epoch-ms terms so the formatter's
# ``command_start_ns = command_start_unix_ms * 1_000_000`` lands exactly on
# _BASE_NS.
_COMMAND_START_UNIX_MS = _BASE_NS // _NS_PER_MS

# Offset timeline (ms relative to _BASE_NS):
#   command_start           0
#   python_first_line       200        → command_start_to_python_first_line 200
#   local_receive           250        → python_first_line_to_local_receive  50
#   node_registry_start    1250        → local_receive_to_registry_start    1000
#   node_registry_end     18250        → node_registry_init                17000
#   worker_start          18280        → registry_end_to_worker_start        30
#   plan_build_call_start 18290        → worker_start_to_plan_build_start    10
#   execute_plan_call_start 18353      → plan_build                          63
#   transport_entry        18358       → plan_build_to_transport_entry        5
#   handle_lookup_end      18360       → handle_lookup                        2
#   payload_serialize_end  18361       → payload_serialize                    1
#   modal_submission_attempt 18361     → local_receive_to_submission      18111
#   modal_first_remote_event 23681     → first_remote_signal               5320
_OFFSETS = {
    "python_first_line": 200,
    "local_receive": 250,
    "node_registry_start": 1250,
    "node_registry_end": 18250,
    "worker_start": 18280,
    "plan_build_call_start": 18290,
    "execute_plan_call_start": 18353,
    "transport_entry": 18358,
    "handle_lookup_end": 18360,
    "payload_serialize_end": 18361,
    "modal_submission_attempt": 18361,
    "modal_first_remote_event": 23681,
}

_LOCAL_TIMING = {
    "worker_start_to_plan_build_ms": 10.0,
    "plan_build_ms": 63.0,
    "transport_entry_to_handle_lookup_ms": 0.0,
    "handle_lookup_ms": 2.0,
    "payload_serialize_ms": 1.0,
    "generator_create_ms": 0.0,
    "generator_created_to_first_iteration_ms": 0.0,
    "local_receive_to_actual_submission_ms": 18111.0,
    "first_iteration_to_first_remote_event_ms": 5320.0,
}


def _wall(offset_ms: int) -> int:
    return _BASE_NS + offset_ms * _NS_PER_MS


def _event(name: str, offset_ms: int) -> dict:
    return {"name": name, "wall_unix_ns": _wall(offset_ms)}


def _events() -> list[dict]:
    return [
        _event("worker_start", _OFFSETS["worker_start"]),
        _event("build_execution_plan_call_start", _OFFSETS["plan_build_call_start"]),
        _event("execute_plan_call_start", _OFFSETS["execute_plan_call_start"]),
        _event("transport_entry", _OFFSETS["transport_entry"]),
        _event("modal_handle_lookup_start", _OFFSETS["transport_entry"]),
        _event("modal_handle_lookup_end", _OFFSETS["handle_lookup_end"]),
        _event("modal_payload_serialize_start", _OFFSETS["handle_lookup_end"]),
        _event("modal_payload_serialize_end", _OFFSETS["payload_serialize_end"]),
        _event("modal_generator_create_start", _OFFSETS["payload_serialize_end"]),
        _event("modal_generator_created", _OFFSETS["payload_serialize_end"]),
        _event("modal_submission_attempt", _OFFSETS["modal_submission_attempt"]),
        _event("modal_first_remote_event", _OFFSETS["modal_first_remote_event"]),
    ]


def _artifact(events=None, local_timing: Any | None = None) -> dict:
    """Raw ``_run_one`` artifact layout: trace under result.trace, existing
    measured values under result.local_timing."""
    if events is None:
        events = _events()
    if local_timing is None:
        local_timing = dict(_LOCAL_TIMING)
    return {
        "request_id": _REQ,
        "result": {
            "trace": {"events": list(events)},
            "local_timing": dict(local_timing),
        },
    }


def _full_kwargs() -> dict:
    """Every stamp present — the synthetic equivalent of a completed run where
    the bat set COMFYMODAL_COMMAND_START_UNIX_MS and the registry init ran."""
    return {
        "command_start_unix_ms": _COMMAND_START_UNIX_MS,
        "python_first_line_ns": _wall(_OFFSETS["python_first_line"]),
        "local_receive_wall_ns": _wall(_OFFSETS["local_receive"]),
        "node_registry_start_ns": _wall(_OFFSETS["node_registry_start"]),
        "node_registry_end_ns": _wall(_OFFSETS["node_registry_end"]),
        "scheduling_ms": 1596.0,
        "scheduling_source": "result_carried",
    }


def _parse(line):
    assert line is not None
    return dict(part.split("=", 1) for part in line.split(" ") if "=" in part)


class TestHostSubmissionBreakdownLine(unittest.TestCase):
    def test_all_fields_present_with_sane_values(self):
        """Every field renders a genuine value when all stamps exist."""
        line = build_host_submission_breakdown_line(
            _artifact(), **_full_kwargs()
        )
        self.assertTrue(str(line).startswith("[v2.host_submission_breakdown]"))
        parts = _parse(line)
        self.assertEqual(parts["request_id"], _REQ)
        self.assertEqual(parts["command_start_to_python_first_line_ms"], "200.0")
        self.assertEqual(parts["python_first_line_to_local_receive_ms"], "50.0")
        self.assertEqual(parts["local_receive_to_registry_start_ms"], "1000.0")
        self.assertEqual(parts["node_registry_init_ms"], "17000.0")
        self.assertEqual(parts["registry_end_to_worker_start_ms"], "30.0")
        self.assertEqual(parts["worker_start_to_plan_build_start_ms"], "10.0")
        self.assertEqual(parts["plan_build_ms"], "63.0")
        self.assertEqual(parts["plan_build_to_transport_entry_ms"], "5.0")
        self.assertEqual(parts["transport_entry_to_handle_lookup_ms"], "0.0")
        self.assertEqual(parts["handle_lookup_ms"], "2.0")
        self.assertEqual(parts["payload_serialize_ms"], "1.0")
        self.assertEqual(parts["generator_create_ms"], "0.0")
        self.assertEqual(parts["generator_created_to_submission_ms"], "0.0")
        self.assertEqual(parts["local_receive_to_submission_ms"], "18111.0")
        self.assertEqual(parts["submission_boundary_source"], "first_anext")
        self.assertEqual(parts["first_remote_signal_ms"], "5320.0")
        self.assertEqual(parts["scheduling_ms"], "1596.0")
        self.assertEqual(parts["scheduling_source"], "result_carried")

    def test_missing_stamps_render_absent_not_zero(self):
        """Missing python-first-line / registry stamps → ``absent`` (never 0)."""
        line = build_host_submission_breakdown_line(
            _artifact(),
            command_start_unix_ms=_COMMAND_START_UNIX_MS,
            python_first_line_ns=None,
            local_receive_wall_ns=None,
            node_registry_start_ns=None,
            node_registry_end_ns=None,
        )
        parts = _parse(line)
        self.assertEqual(parts["command_start_to_python_first_line_ms"], "absent")
        self.assertEqual(parts["python_first_line_to_local_receive_ms"], "absent")
        self.assertEqual(parts["local_receive_to_registry_start_ms"], "absent")
        self.assertEqual(parts["node_registry_init_ms"], "absent")
        self.assertEqual(parts["registry_end_to_worker_start_ms"], "absent")
        # Existing measured values still render (never faked to zero).
        self.assertEqual(parts["plan_build_ms"], "63.0")
        self.assertEqual(parts["local_receive_to_submission_ms"], "18111.0")
        self.assertEqual(parts["scheduling_source"], "unavailable")

    def test_command_start_env_missing_only_that_field_absent(self):
        """No COMFYMODAL_COMMAND_START_UNIX_MS (command_start=None) → only the
        command→python-first-line interval is absent."""
        kwargs = _full_kwargs()
        kwargs["command_start_unix_ms"] = None
        parts = _parse(build_host_submission_breakdown_line(_artifact(), **kwargs))
        self.assertEqual(parts["command_start_to_python_first_line_ms"], "absent")
        # Everything downstream of python-first-line is unaffected.
        self.assertEqual(parts["python_first_line_to_local_receive_ms"], "50.0")
        self.assertEqual(parts["node_registry_init_ms"], "17000.0")
        self.assertEqual(parts["local_receive_to_submission_ms"], "18111.0")

    def test_submission_boundary_source_documented_as_first_anext(self):
        """submission_boundary_source is the constant 'first_anext' — the
        modal_submission_attempt event is captured at the first __anext__ of
        the lazy remote generator (the TRUE Modal submit boundary)."""
        self.assertEqual(_HOST_SUBMISSION_BOUNDARY_SOURCE, "first_anext")
        parts = _parse(build_host_submission_breakdown_line(
            _artifact(), **_full_kwargs()
        ))
        self.assertEqual(parts["submission_boundary_source"], "first_anext")

    def test_scheduling_source_values(self):
        """All three scheduling-source values round-trip; scheduling_ms absent
        when the source is unavailable."""
        for source, sched_ms in (
            ("result_carried", 1596.0),
            ("modal_app_log", 1596.0),
            ("unavailable", None),
        ):
            kwargs = _full_kwargs()
            kwargs["scheduling_source"] = source
            kwargs["scheduling_ms"] = sched_ms
            parts = _parse(build_host_submission_breakdown_line(_artifact(), **kwargs))
            self.assertEqual(parts["scheduling_source"], source)
            if source == "unavailable":
                self.assertEqual(parts["scheduling_ms"], "absent")
            else:
                self.assertEqual(parts["scheduling_ms"], "1596.0")

    def test_segments_reconcile_to_local_receive_to_submission(self):
        """local_receive→registry_start + registry_init + registry_end→worker +
        worker→plan + plan_build + plan→transport + transport→handle +
        handle + payload + generator + generator→submission ≈
        local_receive_to_submission_ms (within rounding)."""
        parts = _parse(build_host_submission_breakdown_line(
            _artifact(), **_full_kwargs()
        ))
        chain = (
            "local_receive_to_registry_start_ms",
            "node_registry_init_ms",
            "registry_end_to_worker_start_ms",
            "worker_start_to_plan_build_start_ms",
            "plan_build_ms",
            "plan_build_to_transport_entry_ms",
            "transport_entry_to_handle_lookup_ms",
            "handle_lookup_ms",
            "payload_serialize_ms",
            "generator_create_ms",
            "generator_created_to_submission_ms",
        )
        total = sum(float(parts[key]) for key in chain)
        self.assertAlmostEqual(
            total, float(parts["local_receive_to_submission_ms"]), delta=0.5
        )

    def test_no_registry_init_run_degrades_gracefully(self):
        """A run where ``_ensure_full_node_registry`` never ran (start/end
        stamps are None, as in a fresh import) renders the registry fields as
        absent and never raises."""
        kwargs = _full_kwargs()
        kwargs["node_registry_start_ns"] = None
        kwargs["node_registry_end_ns"] = None
        line = build_host_submission_breakdown_line(_artifact(), **kwargs)
        parts = _parse(line)
        self.assertEqual(parts["local_receive_to_registry_start_ms"], "absent")
        self.assertEqual(parts["node_registry_init_ms"], "absent")
        self.assertEqual(parts["registry_end_to_worker_start_ms"], "absent")
        # Non-registry segments still render.
        self.assertEqual(parts["worker_start_to_plan_build_start_ms"], "10.0")
        self.assertEqual(parts["local_receive_to_submission_ms"], "18111.0")

    def test_event_derived_fallbacks_fill_local_timing_gaps(self):
        """When local_timing lacks a covered interval, the merged trace events
        provide the value (existing values reused; gaps computed)."""
        local_timing = dict(_LOCAL_TIMING)
        for key in (
            "worker_start_to_plan_build_ms",
            "transport_entry_to_handle_lookup_ms",
            "handle_lookup_ms",
            "payload_serialize_ms",
            "generator_create_ms",
            "generator_created_to_first_iteration_ms",
            "first_iteration_to_first_remote_event_ms",
        ):
            local_timing.pop(key, None)
        parts = _parse(build_host_submission_breakdown_line(
            _artifact(local_timing=local_timing), **_full_kwargs()
        ))
        self.assertEqual(parts["worker_start_to_plan_build_start_ms"], "10.0")
        self.assertEqual(parts["transport_entry_to_handle_lookup_ms"], "0.0")
        self.assertEqual(parts["handle_lookup_ms"], "2.0")
        self.assertEqual(parts["payload_serialize_ms"], "1.0")
        self.assertEqual(parts["generator_create_ms"], "0.0")
        self.assertEqual(parts["generator_created_to_submission_ms"], "0.0")
        self.assertEqual(parts["first_remote_signal_ms"], "5320.0")

    def test_invalid_existing_values_render_absent(self):
        """Existing local_timing values such as 'invalid_negative' degrade to
        absent (they are not genuine measurements) and never surface a bogus
        number; when the event-derived interval is also non-genuine (negative
        wall delta, as in the real runs where the monotonic ordering was
        flagged) the field stays absent."""
        local_timing = dict(_LOCAL_TIMING)
        local_timing["generator_created_to_first_iteration_ms"] = "invalid_negative"  # type: ignore[assignment]
        # generator_created lands AFTER modal_submission_attempt → the wall
        # interval is negative → genuinely non-measurable → absent.
        events = [
            (dict(evt) if evt.get("name") != "modal_generator_created"
             else _event("modal_generator_created", _OFFSETS["modal_submission_attempt"] + 1))
            for evt in _events()
        ]
        parts = _parse(build_host_submission_breakdown_line(
            _artifact(events=events, local_timing=local_timing), **_full_kwargs()
        ))
        self.assertEqual(parts["generator_created_to_submission_ms"], "absent")
        # The rest of the line is unaffected.
        self.assertEqual(parts["local_receive_to_submission_ms"], "18111.0")

    def test_never_raises_on_garbage(self):
        """Malformed artifacts / None inputs never raise."""
        line = build_host_submission_breakdown_line(None)
        self.assertTrue(str(line).startswith("[v2.host_submission_breakdown]"))
        parts = _parse(line)
        self.assertEqual(parts["request_id"], "")
        self.assertEqual(parts["node_registry_init_ms"], "absent")
        line2 = build_host_submission_breakdown_line(
            {"request_id": _REQ, "result": {"trace": {"events": ["junk", 42]}}}
        )
        parts2 = _parse(line2)
        self.assertEqual(parts2["request_id"], _REQ)
        self.assertEqual(parts2["local_receive_to_submission_ms"], "absent")


if __name__ == "__main__":
    unittest.main()
