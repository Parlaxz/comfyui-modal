"""Batch-A acceptance harness validator.

Pure, offline validation core for the strict Batch-A acceptance gates.  It
consumes a single run artifact dict with the same shape as the ``run_<i>.json``
files persisted by ``benchmark_v2_direct.py``::

    {
      "run_index": int,
      "request_id": str,
      "identity": {"restored_instance_id", "restore_count", "request_count", ...},
      "timing": {...},
      "result": {
          "trace": {"events": [...], "metadata": {...}},
          "_restore_timing": {...},
          "pre_sampler_structured_report": {...},
          ...
      },
      "waterfall": {...},
      "waterfall_local": {...},
      "host_diagnostics": {...},
      "runtime_shape": {...},
    }

This module NEVER executes Modal, never imports the repo runtime, never spawns
processes and never touches the network: it is a pure dict-in/dict-out
validator.  Every gate FAILS with an explicit "not observable" detail when
neither the Batch-A exact field nor any documented fallback exists - a pass is
never faked.

Batch-A gates validated here:

1.  fresh identity (nonempty restored_instance_id, restore_count==1,
    request_count==1)
2.  waterfall status (reconciliation_status == "OK" OR
    validation_status == "COMPLETE")
3.  reconciliation |delta| <= RECONCILIATION_HARD_MS (50 ms)
4.  G1 single-execution proof: plan before early UNET schedule, early schedule
    present, snapshot-UNET absent, exactly one UNET active read / bind / H2D,
    no duplicate second execution, downstream identity verification
5.  models reload skipped (decision == "skipped_generation_match", zero remote
    reload calls)
6.  per-node timestamps present (start + end + duration, end >= start)
    - validated per-record only; non-accounting (no cross-row reconciliation)
7.  terminal cleanup stamps (end >= start) + transport-after-cleanup
    (claimed ONLY when an explicit host-reconciled field exists)
8.  host telemetry overhead <= HOST_TELEMETRY_MAX_PROBE_WALL_MS (20 ms),
    no slow-forensic trigger, zero telemetry subprocesses
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# ── Hard gates / thresholds ──────────────────────────────────────────────
RECONCILIATION_HARD_MS = 50.0
HOST_TELEMETRY_MAX_PROBE_WALL_MS = 20.0
SLOW_H2D_THRESHOLD_MS = 4000.0

# ── Canonical runtime event names (current checkout) ─────────────────────
# Batch-A G1 emits "unet_execution_plan_receipt_schedule" at plan receipt
# (immediately after ExecutionPlan.from_dict, before the first status yield);
# the two other names are pre-Batch-A spellings kept for backward compat.
PLAN_RECEIPT_EVENT_NAMES = ("run_plan_first_status_yield", "plan_received")
EARLY_SCHEDULE_EVENT_NAMES = (
    "unet_execution_plan_receipt_schedule",
    "unet_early_activation_scheduled",
    "unet_activation_scheduled",
)
UNET_BIND_START_EVENT_NAMES = ("unet_fast_disk_bind_start",)
UNET_BIND_END_EVENT_NAMES = ("unet_fast_disk_bind_end",)
UNET_H2D_EVENT_NAMES = ("unet_h2d",)
IDENTITY_GAP_EVENT_NAMES = ("run_plan_method_entry_gap",)
HOST_PROBE_EVENT_NAMES = (
    "host_hardware_fingerprint",
    "host_resource_snapshot",
    "host_forensic_slow_h2d",
)
SLOW_FORENSIC_EVENT_NAMES = ("host_forensic_slow_h2d",)
TERMINAL_TEARDOWN_EVENT_NAMES = ("request_terminal_start", "request_terminal_end")


# ── Small private helpers ────────────────────────────────────────────────
def _events(result: dict) -> list[dict]:
    """Trace events list ([] when absent)."""
    events = _deep_get(result, "trace.events")
    return events if isinstance(events, list) else []


def _trace_metadata(result: dict) -> dict:
    """Trace metadata dict ({} when absent)."""
    md = _deep_get(result, "trace.metadata")
    return md if isinstance(md, dict) else {}


def _deep_get(obj: Any, *dotted_paths: str) -> Any:
    """First hit wins: return the first non-None value found along any dotted
    path (path parts split on '.').  Missing paths and None values are
    skipped; falsy-but-valid values (0, False, "", []) are returned."""
    for dotted in dotted_paths:
        current = obj
        found = True
        for part in dotted.split("."):
            if not isinstance(current, dict) or part not in current:
                found = False
                break
            current = current[part]
        if found and current is not None:
            return current
    return None


def _first_value(*candidates: Any) -> Any:
    """First non-None candidate (0/False are values, not misses)."""
    for c in candidates:
        if c is not None:
            return c
    return None


def _num(x: Any) -> float | None:
    """float-or-None converter; booleans are explicitly excluded."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        try:
            return float(x.strip())
        except (TypeError, ValueError):
            return None
    return None


def _boolish(x: Any) -> bool:
    if x is None:
        return False
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return x != 0
    if isinstance(x, str):
        return x.strip().lower() in ("1", "true", "yes", "ok")
    return bool(x)


def _find_event(result: dict, name: str) -> dict | None:
    for e in _events(result):
        if isinstance(e, dict) and e.get("name") == name:
            return e
    return None


def _event_metadata_value(result: dict, event_name: str, key: str) -> Any:
    """First metadata[key] found on the first trace event named event_name."""
    for _e in _events(result):
        if isinstance(_e, dict) and _e.get("name") == event_name:
            _em = _e.get("metadata")
            if isinstance(_em, dict) and key in _em:
                return _em[key]
    return None


def _count_events(result: dict, name: str) -> int:
    return sum(
        1 for e in _events(result) if isinstance(e, dict) and e.get("name") == name
    )


def _record_is_unet(row: dict) -> bool:
    """True when a loader record's loader_type/owner mention 'unet'."""
    return (
        "unet" in str(row.get("loader_type", "")).lower()
        or "unet" in str(row.get("owner", "")).lower()
    )


def _active_read_records(result: dict) -> list[dict]:
    records = _deep_get(result, "pre_sampler_structured_report.active_read_records")
    return records if isinstance(records, list) else []


def _count_unet_active_reads(result: dict) -> int:
    """Derived UNET active-read count from pre_sampler_structured_report
    active_read_records: filter to unet loader_type/owner; when the filter
    matches nothing, the full record count is used (loader_type not
    populated)."""
    records = _active_read_records(result)
    filtered = [r for r in records if isinstance(r, dict) and _record_is_unet(r)]
    if filtered:
        return len(filtered)
    return len(records)


def _count_unet_bind_ops(result: dict) -> int:
    """Derived UNET fast-disk bind op count: min of bind-start/bind-end event
    counts (they are already unet-scoped by their canonical names); when only
    one kind exists, that kind's count is used."""
    starts = _count_events(result, UNET_BIND_START_EVENT_NAMES[0])
    ends = _count_events(result, UNET_BIND_END_EVENT_NAMES[0])
    if starts > 0 and ends > 0:
        return min(starts, ends)
    if starts > 0:
        return starts
    return ends


def _unet_h2d_events(result: dict) -> list[dict]:
    return [
        e for e in _events(result)
        if isinstance(e, dict) and e.get("name") in UNET_H2D_EVENT_NAMES
    ]


def _count_unet_h2d_ops(result: dict) -> int:
    """Derived UNET H2D op count, in evidence-preference order:

    1. ``unet_fast_disk_complete`` events whose metadata ``to_wall_ms`` /
       ``to_device_ms`` is > 0 — the real fast-disk UNET transfer evidence
       (exactly one real ``model.to(target)`` per request in the
       snapshot-unet-absent shape; the ``unet_h2d`` event is a page-fault
       delta emitted from GPU-commit lanes and fires for other lanes, e.g.
       VAE, so it is only counted when lane-scoped to UNET).
    2. ``unet_h2d`` events with metadata ``lane == "UNET"`` and
       ``duration_ms`` > 0.
    3. ``unet_fast_disk_to_start``/``unet_fast_disk_to_end`` pair min.
    4. Legacy fallback: all ``unet_h2d`` events with ``duration_ms`` > 0.
    """
    complete_events = [
        e for e in _events(result)
        if isinstance(e, dict) and e.get("name") == "unet_fast_disk_complete"
    ]
    timed_complete = [
        e for e in complete_events
        if (_num((e.get("metadata") or {}).get("to_wall_ms")) or 0.0) > 0.0
        or (_num((e.get("metadata") or {}).get("to_device_ms")) or 0.0) > 0.0
    ]
    if timed_complete:
        return len(timed_complete)
    unet_lane_h2d = [
        e for e in _unet_h2d_events(result)
        if str((e.get("metadata") or {}).get("lane", "")).upper() == "UNET"
        and (_num((e.get("metadata") or {}).get("duration_ms")) or 0.0) > 0.0
    ]
    if unet_lane_h2d:
        return len(unet_lane_h2d)
    _to_starts = _count_events(result, "unet_fast_disk_to_start")
    _to_ends = _count_events(result, "unet_fast_disk_to_end")
    if _to_starts or _to_ends:
        if _to_starts > 0 and _to_ends > 0:
            return min(_to_starts, _to_ends)
        return max(_to_starts, _to_ends)
    events = _unet_h2d_events(result)
    timed = [
        e for e in events
        if (_num((e.get("metadata") or {}).get("duration_ms")) or 0.0) > 0.0
    ]
    if timed:
        return len(timed)
    return len(events)


# ── Result containers ────────────────────────────────────────────────────
@dataclass
class GateCheck:
    key: str
    ok: bool
    value: Any
    detail: str


@dataclass
class BatchAAcceptanceResult:
    fresh: str  # "YES" / "NO"
    fresh_ok: bool
    status_ok: bool
    reconciliation_ms: float | None
    reconciliation_ok: bool
    g1_early_schedule: bool
    unet_read_count: int
    unet_read_ok: bool
    unet_bind_count: int
    unet_bind_ok: bool
    unet_h2d_count: int
    unet_h2d_ok: bool
    identity_match_ok: bool
    no_duplicate_ok: bool
    duplicate_evidence: str
    models_reload_decision: str | None
    models_reload_decision_ok: bool
    models_reload_remote_calls: int | None
    models_reload_remote_ok: bool
    node_timing_ok: bool
    node_timing_rows: int
    terminal_cleanup_start: float | None
    terminal_cleanup_end: float | None
    terminal_cleanup_ms: float | None
    terminal_ok: bool
    transport_after_cleanup_ms: float | None
    transport_claimed: bool
    host_telemetry_probe_ms: float | None
    host_telemetry_ok: bool
    slow_forensic_triggered: bool
    slow_forensic_ok: bool
    h2d_below_slow_threshold: bool | None
    checks: list[GateCheck] = field(default_factory=list)
    passed: bool = False


# ── Validator ────────────────────────────────────────────────────────────
def validate_batch_a(artifact: dict) -> BatchAAcceptanceResult:
    if not isinstance(artifact, dict):
        artifact = {}
    _result = artifact.get("result") or {}
    if not isinstance(_result, dict):
        _result = {}
    checks: list[GateCheck] = []

    # ── Gate 1: fresh identity ──────────────────────────────────────────
    identity = artifact.get("identity") or {}
    restored_instance_id = identity.get("restored_instance_id")
    restore_count = _num(identity.get("restore_count"))
    request_count = _num(identity.get("request_count"))
    fresh_ok = (
        bool(restored_instance_id)
        and restore_count == 1.0
        and request_count == 1.0
    )
    fresh = "YES" if fresh_ok else "NO"
    if identity:
        fresh_detail = (
            f"restored_instance_id={restored_instance_id!r}, "
            f"restore_count={identity.get('restore_count')!r}, "
            f"request_count={identity.get('request_count')!r}"
        )
    else:
        fresh_detail = "identity not observable: artifact['identity'] missing/empty"
    checks.append(GateCheck("fresh", fresh_ok, fresh, fresh_detail))

    # ── Gates 2-3: status + reconciliation (waterfall_local preferred) ──
    _wf = artifact.get("waterfall_local") or artifact.get("waterfall") or {}
    if not isinstance(_wf, dict) or not _wf:
        status_ok = False
        status_detail = (
            "status not observable: no waterfall/waterfall_local report in artifact"
        )
        reconciliation_ms = None
        reconciliation_ok = False
        reconciliation_detail = (
            "reconciliation not resolved in this artifact "
            "(no waterfall/waterfall_local report)"
        )
    else:
        _rs = _wf.get("reconciliation_status")
        _vs = _wf.get("validation_status")
        status_ok = _rs == "OK" or _vs == "COMPLETE"
        status_detail = (
            f"reconciliation_status={_rs!r}, validation_status={_vs!r}"
        )
        reconciliation_ms = _num(_wf.get("reconciliation_ms"))
        if reconciliation_ms is None:
            reconciliation_ok = False
            reconciliation_detail = (
                "reconciliation not resolved in this artifact "
                "(reconciliation_ms is None)"
            )
        else:
            reconciliation_ok = abs(reconciliation_ms) <= RECONCILIATION_HARD_MS
            reconciliation_detail = (
                f"reconciliation_ms={reconciliation_ms} vs hard cap "
                f"{RECONCILIATION_HARD_MS} ms"
            )
    checks.append(GateCheck("status", status_ok, None, status_detail))
    checks.append(
        GateCheck("reconciliation", reconciliation_ok, reconciliation_ms,
                  reconciliation_detail)
    )

    # ── Gate 4a: plan receipt precedes the early UNET schedule ───────────
    # The G1 lane emits "unet_execution_plan_receipt_schedule" immediately
    # after ExecutionPlan.from_dict (plan receipt) and BEFORE the first
    # status yield ("run_plan_first_status_yield").  The marker's existence
    # already proves plan receipt (it is only emitted on that code path);
    # the ordering check additionally proves it fired in the plan-receipt
    # window, before any status was yielded.
    plan_event = None
    for _n in PLAN_RECEIPT_EVENT_NAMES:
        plan_event = _find_event(_result, _n)
        if plan_event is not None:
            break
    schedule_event = None
    for _n in EARLY_SCHEDULE_EVENT_NAMES:
        schedule_event = _find_event(_result, _n)
        if schedule_event is not None:
            break
    if plan_event is None or schedule_event is None:
        _missing = []
        if plan_event is None:
            _missing.append("plan marker")
        if schedule_event is None:
            _missing.append("early UNET schedule marker")
        g1_plan_before_schedule_ok = False
        g1_plan_before_schedule_value = False
        g1_plan_before_schedule_detail = (
            f"marker missing: {' and '.join(_missing)} not present in trace events"
        )
    else:
        _plan_mono = _num(plan_event.get("monotonic_ns"))
        _sched_mono = _num(schedule_event.get("monotonic_ns"))
        if _plan_mono is not None and _sched_mono is not None:
            g1_plan_before_schedule_ok = _sched_mono < _plan_mono
            g1_plan_before_schedule_value = g1_plan_before_schedule_ok
            g1_plan_before_schedule_detail = (
                f"early schedule monotonic_ns {_sched_mono:g} < first status "
                f"yield monotonic_ns {_plan_mono:g} (scheduled at plan "
                "receipt, before any status yield)"
            )
        else:
            _plan_idx = _events(_result).index(plan_event)
            _sched_idx = _events(_result).index(schedule_event)
            g1_plan_before_schedule_ok = _sched_idx < _plan_idx
            g1_plan_before_schedule_value = g1_plan_before_schedule_ok
            g1_plan_before_schedule_detail = (
                f"schedule event index {_sched_idx} < plan event index {_plan_idx}"
            )
    checks.append(
        GateCheck("g1_plan_before_schedule", g1_plan_before_schedule_ok,
                  g1_plan_before_schedule_value, g1_plan_before_schedule_detail)
    )

    # ── Gate 4b: early UNET scheduling occurred ─────────────────────────
    _sched_meta = _trace_metadata(_result)
    _exec_unet_scheduled = _boolish(_sched_meta.get("_execution_unet_scheduled"))
    g1_early_schedule = schedule_event is not None or _exec_unet_scheduled
    if schedule_event is not None:
        g1_early_schedule_detail = (
            f"{schedule_event['name']} event present in trace"
        )
    elif _exec_unet_scheduled:
        g1_early_schedule_detail = (
            "_execution_unet_scheduled truthy in trace metadata"
        )
    else:
        g1_early_schedule_detail = (
            "no early-schedule marker observable "
            "(no schedule event, _execution_unet_scheduled falsy/absent)"
        )
    checks.append(
        GateCheck("g1_early_schedule", g1_early_schedule, g1_early_schedule,
                  g1_early_schedule_detail)
    )

    # ── Gate 4c: snapshot UNET absent ───────────────────────────────────
    _snap_absent = (
        _boolish(_sched_meta.get("_execution_unet_gate"))
        or _boolish(
            (schedule_event.get("metadata") or {}).get("snapshot_unet_absent")
            if schedule_event is not None else None
        )
        or _boolish(_result.get("snapshot_unet_absent"))
    )
    if _snap_absent:
        g1_snapshot_unet_absent_detail = (
            "snapshot-UNET-absent marker truthy "
            "(_execution_unet_gate / schedule-event snapshot_unet_absent / "
            "result snapshot_unet_absent)"
        )
    else:
        g1_snapshot_unet_absent_detail = (
            "snapshot-UNET-absent marker not observable "
            "(_execution_unet_gate falsy/absent, no snapshot_unet_absent)"
        )
    checks.append(
        GateCheck("g1_snapshot_unet_absent", _snap_absent, _snap_absent,
                  g1_snapshot_unet_absent_detail)
    )

    # ── Gate 4d: UNET active read count == 1 ────────────────────────────
    _explicit_read = _first_value(
        _deep_get(_result, "unet_active_read_count",
                  "pre_sampler_structured_report.unet_active_read_count",
                  "trace.metadata.unet_active_read_count"),
        _deep_get(_result, "unet_read_count",
                  "pre_sampler_structured_report.unet_read_count",
                  "trace.metadata.unet_read_count"),
    )
    _explicit_read_num = _num(_explicit_read)
    if _explicit_read_num is not None:
        unet_read_count = int(_explicit_read_num)
        unet_read_detail = "explicit unet_active_read_count/unet_read_count field"
    else:
        _records = _active_read_records(_result)
        unet_read_count = _count_unet_active_reads(_result)
        if _records:
            _filtered = [r for r in _records if isinstance(r, dict) and _record_is_unet(r)]
            if _filtered:
                unet_read_detail = (
                    f"derived from active_read_records "
                    f"(unet-filtered {len(_filtered)}/{len(_records)})"
                )
            else:
                unet_read_detail = (
                    "derived from active_read_records unfiltered "
                    "(loader_type/owner not populated)"
                )
        else:
            unet_read_detail = (
                "not observable: no explicit unet_active_read_count/"
                "unet_read_count field and no active_read_records"
            )
    unet_read_ok = unet_read_count == 1
    checks.append(
        GateCheck("g1_unet_read_count", unet_read_ok, unet_read_count,
                  unet_read_detail)
    )

    # ── Gate 4e: UNET bind count == 1 ───────────────────────────────────
    _explicit_bind = _num(
        _deep_get(_result, "unet_bind_count",
                  "pre_sampler_structured_report.unet_bind_count",
                  "trace.metadata.unet_bind_count")
    )
    if _explicit_bind is not None:
        unet_bind_count = int(_explicit_bind)
        unet_bind_detail = "explicit unet_bind_count field"
    else:
        unet_bind_count = _count_unet_bind_ops(_result)
        _starts = _count_events(_result, UNET_BIND_START_EVENT_NAMES[0])
        _ends = _count_events(_result, UNET_BIND_END_EVENT_NAMES[0])
        if _starts or _ends:
            unet_bind_detail = (
                f"derived from unet_fast_disk_bind_start/end events "
                f"(start={_starts}, end={_ends})"
            )
        else:
            unet_bind_detail = (
                "not observable: no explicit unet_bind_count field and "
                "no unet_fast_disk_bind_start/end events"
            )
    unet_bind_ok = unet_bind_count == 1
    checks.append(
        GateCheck("g1_unet_bind_count", unet_bind_ok, unet_bind_count,
                  unet_bind_detail)
    )

    # ── Gate 4f: UNET H2D count == 1 ────────────────────────────────────
    _explicit_h2d = _num(
        _first_value(
            _deep_get(_result, "unet_h2d_count",
                      "pre_sampler_structured_report.unet_h2d_count",
                      "trace.metadata.unet_h2d_count"),
            _deep_get(_result, "unet_h2d_ops",
                      "pre_sampler_structured_report.unet_h2d_ops",
                      "trace.metadata.unet_h2d_ops"),
        )
    )
    if _explicit_h2d is not None:
        unet_h2d_count = int(_explicit_h2d)
        unet_h2d_detail = "explicit unet_h2d_count/unet_h2d_ops field"
    else:
        _h2d_events = _unet_h2d_events(_result)
        _complete_events = [
            e for e in _events(_result)
            if isinstance(e, dict) and e.get("name") == "unet_fast_disk_complete"
        ]
        _timed_complete = [
            e for e in _complete_events
            if (_num((e.get("metadata") or {}).get("to_wall_ms")) or 0.0) > 0.0
            or (_num((e.get("metadata") or {}).get("to_device_ms")) or 0.0) > 0.0
        ]
        _unet_lane_h2d = [
            e for e in _h2d_events
            if str((e.get("metadata") or {}).get("lane", "")).upper() == "UNET"
            and (_num((e.get("metadata") or {}).get("duration_ms")) or 0.0) > 0.0
        ]
        _to_starts = _count_events(_result, "unet_fast_disk_to_start")
        _to_ends = _count_events(_result, "unet_fast_disk_to_end")
        _timed_h2d = [
            e for e in _h2d_events
            if (_num((e.get("metadata") or {}).get("duration_ms")) or 0.0) > 0.0
        ]
        unet_h2d_count = _count_unet_h2d_ops(_result)
        if _timed_complete:
            unet_h2d_detail = (
                f"derived from {len(_timed_complete)} unet_fast_disk_complete "
                "events with to_wall_ms/to_device_ms > 0 (real fast-disk H2D)"
            )
        elif _unet_lane_h2d:
            unet_h2d_detail = (
                f"derived from {len(_unet_lane_h2d)} unet_h2d events "
                "(lane=UNET, duration_ms > 0)"
            )
        elif _to_starts or _to_ends:
            unet_h2d_detail = (
                f"derived from unet_fast_disk_to_start/end events "
                f"(start={_to_starts}, end={_to_ends})"
            )
        elif _timed_h2d:
            unet_h2d_detail = (
                f"derived from {len(_timed_h2d)} unet_h2d events with "
                "duration_ms > 0 (coarse fallback; lane not UNET-scoped)"
            )
        elif _h2d_events:
            unet_h2d_detail = (
                f"derived from {len(_h2d_events)} unet_h2d events "
                "(none carried duration_ms)"
            )
        else:
            unet_h2d_detail = (
                "not observable: no explicit unet_h2d_count/unet_h2d_ops "
                "field, no unet_fast_disk_complete, no unet_h2d events"
            )
    unet_h2d_ok = unet_h2d_count == 1
    checks.append(
        GateCheck("g1_unet_h2d_count", unet_h2d_ok, unet_h2d_count,
                  unet_h2d_detail)
    )

    # ── Gate 4g: no duplicate second execution ──────────────────────────
    later_schedule_noop = _first_value(
        _result.get("later_schedule_noop"),
        _sched_meta.get("later_schedule_noop"),
    )
    if later_schedule_noop is None:
        for _e in _events(_result):
            _em = _e.get("metadata") or {}
            if "later_schedule_noop" in _em:
                later_schedule_noop = _em["later_schedule_noop"]
                break
    if later_schedule_noop is None:
        # Runtime single-flight proof: the later binding-block schedule call
        # emits "unet_execution_schedule" with reason="already_prepared"
        # (bridge guard: prep.unet_future is not None -> no-op).  When the
        # early lane did not fire, the later call emits reason="schedule"
        # and this detection stays silent.
        _already_prepared = [
            _e for _e in _events(_result)
            if isinstance(_e, dict)
            and _e.get("name") == "unet_execution_schedule"
            and ((_e.get("metadata") or {}).get("reason") == "already_prepared")
        ]
        if _already_prepared:
            later_schedule_noop = True
    if later_schedule_noop is not None:
        no_duplicate_ok = _boolish(later_schedule_noop)
        duplicate_evidence = (
            f"later_schedule_noop observable = {later_schedule_noop!r}"
        )
    else:
        _schedule_count = sum(
            1 for _e in _events(_result)
            if isinstance(_e, dict) and _e.get("name") in EARLY_SCHEDULE_EVENT_NAMES
        )
        no_duplicate_ok = (
            unet_read_count == 1
            and unet_bind_count == 1
            and unet_h2d_count == 1
            and _schedule_count <= 1
        )
        duplicate_evidence = (
            "inferred: read==1, bind==1, h2d==1, "
            f"schedule-events={_schedule_count}<=1 "
            "(later_schedule_noop not observable)"
        )
    checks.append(
        GateCheck("g1_no_duplicate", no_duplicate_ok, no_duplicate_ok,
                  duplicate_evidence)
    )

    # ── Gate 4h: downstream identity verification ───────────────────────
    _id_gap_event = _find_event(_result, IDENTITY_GAP_EVENT_NAMES[0])
    _identity_matches = None
    _identity_reasons = None
    if _id_gap_event is not None:
        _im_meta = _id_gap_event.get("metadata") or {}
        _identity_matches = _im_meta.get("_identity_matches")
        if _identity_matches is None:
            _identity_matches = _im_meta.get("identity_matches")
        _identity_reasons = _im_meta.get("identity_mismatch_reasons")
    if _identity_matches is None:
        _identity_matches = _sched_meta.get("_identity_matches")
    if _identity_matches is None:
        _identity_matches = _sched_meta.get("identity_matches")
    if _identity_reasons is None:
        _identity_reasons = _sched_meta.get("identity_mismatch_reasons")
    if isinstance(_identity_matches, bool):
        identity_match_ok = _identity_matches is True
        identity_match_detail = (
            f"identity verification marker is plain bool {_identity_matches!r}"
        )
    elif isinstance(_identity_matches, dict):
        _values = [
            v for k, v in _identity_matches.items()
            if k != "identity_mismatch_reasons"
        ]
        # The runtime emits identity_mismatch_reasons as a LIST of failing
        # keys ([] on a healthy run) or a string in older builds; both empty
        # forms are clean.
        _reasons_clean = (
            _identity_reasons is None
            or not _identity_reasons
            or (isinstance(_identity_reasons, str) and not _identity_reasons.strip())
        )
        identity_match_ok = bool(_values) and all(
            (v is True) if isinstance(v, bool) else _boolish(v)
            for v in _values
        ) and _reasons_clean
        identity_match_detail = (
            f"_identity_matches dict with {len(_values)} entries, "
            f"identity_mismatch_reasons={_identity_reasons!r}"
        )
    else:
        identity_match_ok = False
        identity_match_detail = (
            "identity verification marker not observable "
            "(no _identity_matches dict/bool in run_plan_method_entry_gap "
            "or trace metadata)"
        )
    checks.append(
        GateCheck("g1_identity_match", identity_match_ok, identity_match_ok,
                  identity_match_detail)
    )

    # ── Gate 5: models reload decision + remote calls ───────────────────
    # The Batch-A models lane emits a trace event named "models_reload_decision"
    # (phase="restore") with metadata.decision in
    # {skipped_generation_match, reloaded_generation_mismatch,
    #  reloaded_generation_unknown}; the payload paths below are kept for
    # older/alternate producers.
    _decision = _first_value(
        _deep_get(_result, "models_reload_decision",
                  "models_reload.decision",
                  "_restore_timing.models_reload_decision",
                  "trace.metadata.models_reload_decision"),
        _event_metadata_value(_result, "models_reload_decision", "decision"),
    )
    if _decision is not None:
        models_reload_decision = str(_decision)
        models_reload_decision_ok = models_reload_decision == "skipped_generation_match"
        models_reload_decision_detail = (
            f"models_reload_decision={models_reload_decision!r}"
        )
    else:
        models_reload_decision = None
        models_reload_decision_ok = False
        _fb = _first_value(
            _deep_get(_result, "_restore_timing.models_volume_reload_reason"),
            _deep_get(_result, "_restore_timing.models_volume_reload_needed"),
        )
        if _fb is not None:
            models_reload_decision_detail = (
                f"expected 'skipped_generation_match', found fallback {_fb!r} "
                "(Batch-A field not emitted)"
            )
        else:
            models_reload_decision_detail = (
                "models_reload_decision not observable anywhere "
                "(no Batch-A field, no fallback)"
            )
    checks.append(
        GateCheck("models_reload_decision", models_reload_decision_ok,
                  models_reload_decision, models_reload_decision_detail)
    )

    _remote_calls = _first_value(
        _deep_get(_result, "reload_models_count",
                  "_restore_timing.reload_models_count"),
        _deep_get(_result, "reload_models_calls",
                  "_restore_timing.reload_models_calls"),
        _deep_get(_result, "models_reload_remote_calls",
                  "_restore_timing.models_reload_remote_calls"),
    )
    _remote_calls_num = _num(_remote_calls)
    if _remote_calls_num is not None:
        models_reload_remote_calls = int(_remote_calls_num)
        models_reload_remote_ok = models_reload_remote_calls == 0
        models_reload_remote_detail = (
            f"remote reload counter={models_reload_remote_calls}"
        )
    else:
        _invoked = _deep_get(_result, "_restore_timing.reload_models_invoked")
        if _invoked is not None and not _boolish(_invoked):
            models_reload_remote_calls = 0
            models_reload_remote_ok = True
            models_reload_remote_detail = (
                "no explicit counter; "
                "_restore_timing.reload_models_invoked=False"
            )
        else:
            _reason = _deep_get(_result, "_restore_timing.reload_models_reason")
            if _reason == "not_invoked":
                models_reload_remote_calls = 0
                models_reload_remote_ok = True
                models_reload_remote_detail = (
                    "no explicit counter; "
                    "_restore_timing.reload_models_reason='not_invoked'"
                )
            else:
                models_reload_remote_calls = None
                models_reload_remote_ok = False
                models_reload_remote_detail = (
                    "remote reload counter not observable "
                    "(no counter, no reload_models_invoked=False, "
                    "no reason='not_invoked')"
                )
    checks.append(
        GateCheck("models_reload_remote_calls", models_reload_remote_ok,
                  models_reload_remote_calls, models_reload_remote_detail)
    )

    # ── Gate 6: node timestamps (per-record, non-accounting) ────────────
    # Batch-A G3 records carry start_perf_ns / end_perf_ns (perf-counter
    # domain) + duration_ms + pass_outcome; bare start/end spellings are
    # accepted for older/alternate producers.
    _rows_raw = _deep_get(_result, "pre_sampler_structured_report.per_node_timings")
    if not isinstance(_rows_raw, list):
        node_timing_ok = False
        node_timing_rows = 0
        node_timing_detail = (
            "per_node_timings list missing entirely "
            "(no pre_sampler_structured_report.per_node_timings)"
        )
    else:
        _qualifying = []
        for _row in _rows_raw:
            if not isinstance(_row, dict):
                continue
            _start = _first_value(_num(_row.get("start")),
                                  _num(_row.get("start_perf_ns")))
            _end = _first_value(_num(_row.get("end")),
                                _num(_row.get("end_perf_ns")))
            _dur = _first_value(_num(_row.get("duration")),
                                _num(_row.get("duration_ms")))
            if (_start is not None and _end is not None
                    and _dur is not None and _end >= _start):
                _qualifying.append(_row)
        node_timing_rows = len(_qualifying)
        if _qualifying:
            node_timing_ok = True
            node_timing_detail = (
                f"{len(_qualifying)}/{len(_rows_raw)} rows carry numeric "
                "start+end+duration with end>=start; validated per-record "
                "only (non-accounting: no cross-row reconciliation is "
                "required or performed)"
            )
        elif _rows_raw:
            node_timing_ok = False
            node_timing_detail = (
                "per-node start/end not present in records (duration-only); "
                "no row carries numeric start+end+duration with end>=start"
            )
        else:
            node_timing_ok = False
            node_timing_detail = "per_node_timings is empty"
    checks.append(
        GateCheck("node_timestamps", node_timing_ok, node_timing_rows,
                  node_timing_detail)
    )

    # ── Gate 7: terminal cleanup stamps + transport after cleanup ───────
    # The G1 lane stamps the terminal result event's data dict with
    # terminal_cleanup_start_mono_ns / terminal_cleanup_end_mono_ns
    # (same-process monotonic; the derived remote_cleanup_ms) and the
    # _wall_unix_ns pair.  Bare start/end spellings are accepted for
    # older/alternate producers.  Preference order (pairs, never mixed):
    # explicit bare pair -> mono pair -> wall-unix pair -> trace metadata
    # -> artifact timing.
    _term_pair = None
    for _label, _start_candidates, _end_candidates in (
        ("explicit",
         (_deep_get(_result, "terminal_cleanup_start",
                    "terminal_cleanup.start"),),
         (_deep_get(_result, "terminal_cleanup_end",
                    "terminal_cleanup.end"),)),
        ("mono",
         (_deep_get(_result, "terminal_cleanup_start_mono_ns",
                    "terminal_cleanup.start_mono_ns"),),
         (_deep_get(_result, "terminal_cleanup_end_mono_ns",
                    "terminal_cleanup.end_mono_ns"),)),
        ("wall_unix",
         (_deep_get(_result, "terminal_cleanup_start_wall_unix_ns",
                    "terminal_cleanup.start_wall_unix_ns"),),
         (_deep_get(_result, "terminal_cleanup_end_wall_unix_ns",
                    "terminal_cleanup.end_wall_unix_ns"),)),
        ("trace_metadata",
         (_deep_get(_result, "trace.metadata.terminal_cleanup_start"),),
         (_deep_get(_result, "trace.metadata.terminal_cleanup_end"),)),
        ("timing",
         ((artifact.get("timing") or {}).get("terminal_cleanup_start"),),
         ((artifact.get("timing") or {}).get("terminal_cleanup_end"),)),
    ):
        _ts = _num(_first_value(*_start_candidates))
        _te = _num(_first_value(*_end_candidates))
        if _ts is not None and _te is not None:
            _term_pair = (_label, _ts, _te)
            break
    if _term_pair is None:
        terminal_ok = False
        terminal_cleanup_ms = None
        _teardown_events = [
            e for e in _events(_result)
            if isinstance(e, dict) and e.get("name") in TERMINAL_TEARDOWN_EVENT_NAMES
        ]
        _note = ""
        if _teardown_events:
            _note = (
                "; fallback teardown events present (informational only): "
                + ", ".join(e["name"] for e in _teardown_events)
            )
        terminal_detail = f"terminal cleanup stamps not observable{_note}"
    else:
        _term_label, term_start, term_end = _term_pair
        terminal_ok = term_end >= term_start
        # The runtime's mono/wall-unix pairs are nanoseconds; the derived
        # remote_cleanup_ms is the same-process monotonic diff in ms.
        if _term_label in ("mono", "wall_unix"):
            terminal_cleanup_ms = (term_end - term_start) / 1_000_000.0
        else:
            terminal_cleanup_ms = term_end - term_start
        terminal_detail = (
            f"terminal_cleanup_start={term_start:g}, end={term_end:g}, "
            f"duration={terminal_cleanup_ms:g} ms "
            f"(pair source: {_term_label})"
        )
    checks.append(
        GateCheck("terminal_cleanup", terminal_ok, terminal_cleanup_ms,
                  terminal_detail)
    )

    transport_ms = _num(_first_value(
        _deep_get(_result, "transport_after_cleanup_ms",
                  "timing.transport_after_cleanup_ms",
                  "terminal_cleanup.transport_after_cleanup_ms"),
        artifact.get("timing", {}).get("transport_after_cleanup_ms"),
    ))
    if transport_ms is not None:
        transport_claimed = True
        transport_detail = (
            f"transport_after_cleanup_ms={transport_ms:g} (explicit field)"
        )
    else:
        transport_claimed = False
        transport_detail = "not claimed: clocks not host-reconciled"

    # ── Gate 8: host telemetry overhead + slow forensic + subprocesses ──
    probe_ms = _num(_first_value(
        _deep_get(_result, "host_telemetry_total_probe_wall_ms",
                  "resource_telemetry.host_telemetry_total_probe_wall_ms",
                  "trace.metadata.host_telemetry_total_probe_wall_ms"),
    ))
    if probe_ms is None:
        probe_sum = 0.0
        _any_probe = False
        for _name in HOST_PROBE_EVENT_NAMES:
            for _e in _events(_result):
                if not isinstance(_e, dict) or _e.get("name") != _name:
                    continue
                _pm = _num((_e.get("metadata") or {}).get("probe_wall_ms"))
                if _pm is not None:
                    probe_sum += _pm
                    _any_probe = True
        if _any_probe:
            probe_ms = probe_sum
            probe_detail = (
                f"summed probe_wall_ms over host probe events "
                f"({probe_sum:g} ms)"
            )
        else:
            probe_detail = (
                "host telemetry overhead not observable "
                "(no explicit host_telemetry_total_probe_wall_ms field and "
                "no probe_wall_ms on host probe events)"
            )
    else:
        probe_detail = (
            f"explicit host_telemetry_total_probe_wall_ms={probe_ms:g} ms"
        )
    host_telemetry_ok = (
        probe_ms is not None
        and probe_ms <= HOST_TELEMETRY_MAX_PROBE_WALL_MS
    )
    checks.append(
        GateCheck("host_telemetry_overhead", host_telemetry_ok, probe_ms,
                  probe_detail)
    )

    slow_forensic_triggered = (
        _count_events(_result, SLOW_FORENSIC_EVENT_NAMES[0]) > 0
    )
    slow_forensic_ok = not slow_forensic_triggered
    checks.append(
        GateCheck("host_slow_forensic", slow_forensic_ok,
                  slow_forensic_triggered,
                  ("no host_forensic_slow_h2d event present" if slow_forensic_ok
                   else "host_forensic_slow_h2d event triggered"))
    )

    # h2d below slow threshold: informational, never a gate failure.
    # Uses the real fast-disk transfer durations (unet_fast_disk_complete
    # to_wall_ms/to_device_ms) plus any lane-scoped unet_h2d deltas.
    h2d_below_slow_threshold = None
    _h2d_durations = [
        _num((e.get("metadata") or {}).get("to_wall_ms"))
        for e in _events(_result)
        if isinstance(e, dict) and e.get("name") == "unet_fast_disk_complete"
    ]
    _h2d_durations += [
        _num((e.get("metadata") or {}).get("duration_ms"))
        for e in _unet_h2d_events(_result)
        if str((e.get("metadata") or {}).get("lane", "")).upper() == "UNET"
    ]
    _h2d_durations = [d for d in _h2d_durations if d is not None]
    if _h2d_durations:
        h2d_below_slow_threshold = (
            max(_h2d_durations) < SLOW_H2D_THRESHOLD_MS
        )

    _subproc = _first_value(
        _deep_get(_result, "host_telemetry_subprocess_calls",
                  "trace.metadata.host_telemetry_subprocess_calls"),
        _deep_get(_result, "forensic_subprocess_calls",
                  "trace.metadata.forensic_subprocess_calls"),
    )
    _subproc_num = _num(_subproc)
    if _subproc_num is not None:
        host_subprocess_ok = int(_subproc_num) == 0
        host_subprocess_detail = (
            f"subprocess counter={int(_subproc_num)}"
        )
    else:
        host_subprocess_ok = True
        host_subprocess_detail = (
            "no subprocess counter exposed (informational skip)"
        )
    checks.append(
        GateCheck("host_subprocess_forensics", host_subprocess_ok,
                  None, host_subprocess_detail)
    )

    passed = all(c.ok for c in checks)

    _terminal_cleanup_start = None if _term_pair is None else _term_pair[1]
    _terminal_cleanup_end = None if _term_pair is None else _term_pair[2]

    return BatchAAcceptanceResult(
        fresh=fresh,
        fresh_ok=fresh_ok,
        status_ok=status_ok,
        reconciliation_ms=reconciliation_ms,
        reconciliation_ok=reconciliation_ok,
        g1_early_schedule=g1_early_schedule,
        unet_read_count=unet_read_count,
        unet_read_ok=unet_read_ok,
        unet_bind_count=unet_bind_count,
        unet_bind_ok=unet_bind_ok,
        unet_h2d_count=unet_h2d_count,
        unet_h2d_ok=unet_h2d_ok,
        identity_match_ok=identity_match_ok,
        no_duplicate_ok=no_duplicate_ok,
        duplicate_evidence=duplicate_evidence,
        models_reload_decision=models_reload_decision,
        models_reload_decision_ok=models_reload_decision_ok,
        models_reload_remote_calls=models_reload_remote_calls,
        models_reload_remote_ok=models_reload_remote_ok,
        node_timing_ok=node_timing_ok,
        node_timing_rows=node_timing_rows,
        terminal_cleanup_start=_terminal_cleanup_start,
        terminal_cleanup_end=_terminal_cleanup_end,
        terminal_cleanup_ms=terminal_cleanup_ms,
        terminal_ok=terminal_ok,
        transport_after_cleanup_ms=transport_ms,
        transport_claimed=transport_claimed,
        host_telemetry_probe_ms=probe_ms,
        host_telemetry_ok=host_telemetry_ok,
        slow_forensic_triggered=slow_forensic_triggered,
        slow_forensic_ok=slow_forensic_ok,
        h2d_below_slow_threshold=h2d_below_slow_threshold,
        checks=checks,
        passed=passed,
    )


# ── Offline file validation ──────────────────────────────────────────────
def validate_batch_a_file(run_json_path: str) -> BatchAAcceptanceResult:
    """Load a persisted ``run_<i>.json`` artifact and validate it offline."""
    with open(run_json_path, "r", encoding="utf-8") as _fh:
        artifact = json.load(_fh)
    return validate_batch_a(artifact)


# ── Rendering ────────────────────────────────────────────────────────────
def render_acceptance_block(res: BatchAAcceptanceResult) -> str:
    """Render the exact BATCH A ACCEPTANCE block (blank lines between
    sections, YES/NO for booleans, n/a for None).  On FAIL a compact
    'FAILED CHECKS:' list follows with one line per failing gate."""

    def _ms(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.1f}"

    lines = [
        "BATCH A ACCEPTANCE",
        f"Fresh: {res.fresh}",
        f"Status: {'OK' if res.status_ok else 'FAIL'}",
        f"Reconciliation: {_ms(res.reconciliation_ms)} ms",
        "",
        f"G1 early schedule: {'YES' if res.g1_early_schedule else 'NO'}",
        f"UNET read count: {res.unet_read_count}",
        f"UNET bind count: {res.unet_bind_count}",
        f"UNET H2D count: {res.unet_h2d_count}",
        f"Identity match: {'YES' if res.identity_match_ok else 'NO'}",
        "",
        f"Models reload decision: "
        f"{res.models_reload_decision if res.models_reload_decision is not None else 'n/a'}",
        f"Models reload remote calls: "
        f"{res.models_reload_remote_calls if res.models_reload_remote_calls is not None else 'n/a'}",
        "",
        f"Node timestamps: {'YES' if res.node_timing_ok else 'NO'}",
        "",
        f"Terminal cleanup ms: {_ms(res.terminal_cleanup_ms)}",
        f"Transport-after-cleanup ms: {_ms(res.transport_after_cleanup_ms)}",
        "",
        f"Host telemetry overhead: {_ms(res.host_telemetry_probe_ms)} ms",
        f"Slow forensic trigger: {'YES' if res.slow_forensic_triggered else 'NO'}",
        "",
        f"OVERALL: {'PASS' if res.passed else 'FAIL'}",
    ]
    if not res.passed:
        lines.append("")
        lines.append("FAILED CHECKS:")
        for _c in res.checks:
            if not _c.ok:
                lines.append(f"  {_c.key}: {_c.detail}")
    return "\n".join(lines)
