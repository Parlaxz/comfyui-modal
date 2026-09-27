"""Batch D5 wait attribution.

Consume-only: this module reads a completed run result and derives wait
classification for per-node timings plus top-level reconciliations. It never
mutates the result and never fabricates a measurement where events are missing.
It deliberately knows nothing about ComfyUI and is import-safe (it imports only
from comfymodal_runtime.v2_waterfall, which itself has no side effects), so it
is synthetic-testable in isolation.

Clock scope: all wait-window math lives in the CLOCK_MONOTONIC domain shared by
time.perf_counter_ns()/time.monotonic_ns() on the Modal/Linux runtime.
start_perf_ns/end_perf_ns on node records and monotonic_ns on trace events are
directly comparable. Wall-clock values are never mixed into windows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

# Lazy imports: v2_waterfall imports back from this module at its top level
# (classify_node_wait / extract_wait_windows hooks). A top-level import of
# v2_waterfall here would leave that circular reference pointing at a partially
# initialized module and silently disable the hooks in every import order.
def _as_mapping(value: Any) -> Mapping[str, Any]:
    from comfymodal_runtime.v2_waterfall import _as_mapping as _impl
    return _impl(value)


def _events(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    from comfymodal_runtime.v2_waterfall import _events as _impl
    return _impl(result)


def _metadata_events(result: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    from comfymodal_runtime.v2_waterfall import _metadata_events as _impl
    return _impl(result, name)


def _number(value: Any) -> int | None:
    from comfymodal_runtime.v2_waterfall import _number as _impl
    return _impl(value)

WAIT_LOADER = "loader_wait"
WAIT_ASYNC_MODEL_FUTURE = "async_model_future_wait"
WAIT_MUTATION_LANE = "mutation_lane_wait"
WAIT_SAMPLER_LANE = "sampler_lane_wait"
WAIT_OTHER = "other_wait"

# Attribution order when windows overlap: higher priority claims the interval
# first; lower-priority windows only count time the higher-priority ones left
# uncovered.
_WAIT_PRIORITY = (
    WAIT_SAMPLER_LANE,
    WAIT_MUTATION_LANE,
    WAIT_LOADER,
    WAIT_ASYNC_MODEL_FUTURE,
    WAIT_OTHER,
)


@dataclass(frozen=True)
class WaitWindow:
    kind: str
    start_mono_ns: int
    end_mono_ns: int
    source: str  # event name(s) that produced it
    priority: int  # higher = attributed first when windows overlap


def _round3(value: float) -> float:
    return round(value, 3)


def _ms_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _event_mono(event: Mapping[str, Any]) -> int | None:
    value = event.get("monotonic_ns")
    if value is None:
        metadata = _as_mapping(event.get("metadata"))
        value = metadata.get("monotonic_ns")
        if value is None:
            value = metadata.get("mono_ns")
    number = _number(value)
    if number is not None and number <= 0:
        return None
    return number


def _first_mono(events: Sequence[Mapping[str, Any]], name: str) -> int | None:
    for event in events:
        if event.get("name") == name:
            mono = _event_mono(event)
            if mono is not None:
                return mono
    return None


def _first_mono_priority(
    events: Sequence[Mapping[str, Any]], names: Sequence[str]
) -> tuple[int | None, str | None]:
    for name in names:
        mono = _first_mono(events, name)
        if mono is not None:
            return mono, name
    return None, None


def _last_mono(events: Sequence[Mapping[str, Any]], name: str) -> int | None:
    found: int | None = None
    for event in events:
        if event.get("name") == name:
            mono = _event_mono(event)
            if mono is not None:
                found = mono
    return found


def _pair_windows(
    events: Sequence[Mapping[str, Any]],
    start_name: str,
    end_name: str,
    kind: str,
    priority: int,
    source: str,
) -> list[WaitWindow]:
    starts = [event for event in events if event.get("name") == start_name]
    ends = [event for event in events if event.get("name") == end_name]
    windows: list[WaitWindow] = []
    for start, end in zip(starts, ends):
        start_mono = _event_mono(start)
        end_mono = _event_mono(end)
        if start_mono is not None and end_mono is not None:
            windows.append(WaitWindow(kind, start_mono, end_mono, source=source, priority=priority))
    return windows


def extract_wait_windows(result: Mapping[str, Any]) -> list[WaitWindow]:
    """Scan trace events for wait windows.

    Events carrying a positive monotonic_ns only; remote-process events are
    preferred when any exist, otherwise any process is accepted.
    """
    events = [event for event in _events(result) if _event_mono(event) is not None]
    remote = [event for event in events if str(event.get("process") or "") == "remote"]
    if remote:
        events = remote

    windows: list[WaitWindow] = []

    # Loader: canonical graph_wait_start->graph_wait_end brackets
    # future.result(); fall back to graph_unet_demand->graph_unet_wait_end.
    loader = _pair_windows(
        events, "graph_wait_start", "graph_wait_end", WAIT_LOADER, 3,
        "graph_wait_start->graph_wait_end",
    )
    if not loader:
        loader = _pair_windows(
            events, "graph_unet_demand", "graph_unet_wait_end", WAIT_LOADER, 3,
            "graph_unet_demand->graph_unet_wait_end",
        )
    windows.extend(loader)

    # Async model future: sampler-boundary join window comes from metadata
    # (never fabricated from the duration-only join_wait_ms); quiesce wait uses
    # event boundaries.
    for metadata in _metadata_events(result, "unet_graph_join"):
        start = _number(metadata.get("join_start_mono_ns"))
        end = _number(metadata.get("join_completed_mono_ns"))
        if start is not None and start > 0 and end is not None and end > 0 and end >= start:
            windows.append(WaitWindow(
                WAIT_ASYNC_MODEL_FUTURE, start, end,
                source="unet_graph_join.metadata", priority=2,
            ))
    windows.extend(_pair_windows(
        events, "unet_quiesce_wait_start", "unet_quiesce_wait_end",
        WAIT_ASYNC_MODEL_FUTURE, 2, "unet_quiesce_wait_start->unet_quiesce_wait_end",
    ))

    # Mutation lane: pair start/end by shared name prefix, sequentially.
    for prefix in ("unet_gpu_lane_wait", "gpu_lane_wait", "unet_early_activation_lane_wait"):
        windows.extend(_pair_windows(
            events, prefix + "_start", prefix + "_end",
            WAIT_MUTATION_LANE, 4, prefix + "_start/_end",
        ))

    # Sampler lane.
    windows.extend(_pair_windows(
        events, "sampler_lane_wait_start", "sampler_lane_wait_end",
        WAIT_SAMPLER_LANE, 5, "sampler_lane_wait_start->sampler_lane_wait_end",
    ))

    windows = [w for w in windows if w.end_mono_ns > w.start_mono_ns]
    windows.sort(key=lambda w: (-w.priority, w.start_mono_ns))
    return windows


def _subtract_covered(interval: tuple[int, int], covered: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    start, end = interval
    pieces: list[tuple[int, int]] = [(start, end)]
    for cover_start, cover_end in covered:
        remaining: list[tuple[int, int]] = []
        for piece_start, piece_end in pieces:
            if piece_end <= cover_start or piece_start >= cover_end:
                remaining.append((piece_start, piece_end))
            else:
                if piece_start < cover_start:
                    remaining.append((piece_start, cover_start))
                if piece_end > cover_end:
                    remaining.append((cover_end, piece_end))
        pieces = remaining
        if not pieces:
            break
    return pieces


def classify_node_wait(node_record: Mapping[str, Any], windows: Sequence[WaitWindow]) -> dict[str, Any]:
    """Attribute wait windows to a node window.

    Attribution is disjoint: windows are applied in priority order and an
    interval already covered by a higher-priority window is never recounted.
    dependency_wait_wall (already attributed at capture time, disjoint by
    design) is subtracted first as covered. Residual time after all attributed
    waits is absorbed by node_non_wait_wall (canonical): it is NOT proven
    compute — it may still contain unknown/unclassified wait, so it is never
    labeled compute. node_compute_wall is retained as a backward-compatible
    alias carrying the identical clamped value; if over-attribution ever
    exceeds the node wall it is clamped to zero rather than reported negative.
    """
    unavailable = {
        "total_node_wall": None,
        "node_non_wait_wall": None,
        "node_compute_wall": None,
        "dependency_wait_wall": None,
        WAIT_ASYNC_MODEL_FUTURE: None,
        WAIT_LOADER: None,
        WAIT_MUTATION_LANE: None,
        WAIT_SAMPLER_LANE: None,
        WAIT_OTHER: None,
        "wait_total": None,
        "wait_kinds": (),
        "available": False,
    }

    node_start = _number(node_record.get("start_perf_ns"))
    node_end = _number(node_record.get("end_perf_ns"))
    if node_start is None or node_end is None or node_end < node_start:
        return unavailable

    total_ns = node_end - node_start
    covered: list[tuple[int, int]] = []

    dependency_ms = _ms_or_none(node_record.get("dependency_wait_wall"))
    if dependency_ms is not None and dependency_ms > 0:
        dep_ns = int(dependency_ms * 1_000_000)
        dep_end = min(node_end, node_start + dep_ns)
        if dep_end > node_start:
            covered.append((node_start, dep_end))

    attributed = {kind: 0 for kind in _WAIT_PRIORITY}
    for window in sorted(windows, key=lambda w: (-w.priority, w.start_mono_ns)):
        start = max(window.start_mono_ns, node_start)
        end = min(window.end_mono_ns, node_end)
        if end <= start:
            continue
        pieces = _subtract_covered((start, end), covered)
        for piece_start, piece_end in pieces:
            attributed[window.kind] += piece_end - piece_start
        covered.extend(pieces)

    total_node_wall = _round3(total_ns / 1_000_000)
    waits = {kind: _round3(ns / 1_000_000) for kind, ns in attributed.items()}
    dependency_wait_wall = _round3(dependency_ms) if dependency_ms is not None else 0.0
    wait_total = _round3(sum(waits.values()) + dependency_wait_wall)
    node_non_wait_wall = _round3(total_node_wall - wait_total)
    if node_non_wait_wall < 0:
        node_non_wait_wall = 0.0
    wait_kinds = tuple(kind for kind in _WAIT_PRIORITY if waits[kind] > 0.0)

    return {
        "total_node_wall": total_node_wall,
        "node_non_wait_wall": node_non_wait_wall,
        "node_compute_wall": node_non_wait_wall,
        "dependency_wait_wall": dependency_wait_wall,
        WAIT_ASYNC_MODEL_FUTURE: waits[WAIT_ASYNC_MODEL_FUTURE],
        WAIT_LOADER: waits[WAIT_LOADER],
        WAIT_MUTATION_LANE: waits[WAIT_MUTATION_LANE],
        WAIT_SAMPLER_LANE: waits[WAIT_SAMPLER_LANE],
        WAIT_OTHER: waits[WAIT_OTHER],
        "wait_total": wait_total,
        "wait_kinds": wait_kinds,
        "available": True,
    }


def build_node_wait_report(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Per-node wait classification from pre_sampler_structured_report."""
    structured = _as_mapping(result.get("pre_sampler_structured_report"))
    per_node = structured.get("per_node_timings")
    records = [value for value in per_node if isinstance(value, Mapping)] if isinstance(per_node, (list, tuple)) else []
    windows = extract_wait_windows(result)
    report: list[dict[str, Any]] = []
    for record in records:
        row = {"node_id": record.get("node_id"), "class_type": record.get("class_type")}
        row.update(classify_node_wait(record, windows))
        report.append(row)
    return report


def unet_first_consumer(result: Mapping[str, Any]) -> dict[str, Any]:
    """UNET first-consumer record for the task graph's critical path.

    Every value is optional: when the underlying events are missing the field
    is None (never a fabricated zero).
    """
    events = _events(result)

    ready_mono, ready_source = _first_mono_priority(
        events, ("unet_early_activation_terminal", "unet_fast_disk_complete", "ready")
    )

    start_mono, start_source = _first_mono_priority(events, ("graph_unet_demand",))
    if start_mono is None:
        start_mono, start_source = _first_mono_priority(events, ("graph_wait_start",))

    end_mono, end_source = _first_mono_priority(events, ("graph_unet_wait_end",))
    if end_mono is None:
        end_mono, end_source = _first_mono_priority(events, ("graph_wait_end",))
    if end_mono is None:
        end_mono, end_source = _first_mono_priority(events, ("prepared_result_consumed",))

    duration_ms: float | None = None
    duration_source: str | None = None
    if start_mono is not None and end_mono is not None and end_mono >= start_mono:
        duration_ms = _round3((end_mono - start_mono) / 1_000_000)
        duration_source = f"computed:{start_source}->{end_source}"
    else:
        values = [
            _ms_or_none(_as_mapping(event.get("metadata")).get("graph_wait_duration_ms"))
            for event in events
            if event.get("name") == "prepared_result_consumed"
        ]
        values = [value for value in values if value is not None]
        if values:
            duration_ms = _round3(values[-1])
            duration_source = "prepared_result_consumed.metadata.graph_wait_duration_ms"

    loader_total_ms: float | None = None
    loader_source: str | None = None
    loader_starts: list[tuple[int, str]] = []
    for name in ("unet_early_activation_scheduled", "unet_activation_load_start", "unet_fast_disk_to_start"):
        for event in events:
            if event.get("name") == name:
                mono = _event_mono(event)
                if mono is not None:
                    loader_starts.append((mono, name))
    if loader_starts and ready_mono is not None:
        earliest, earliest_name = min(loader_starts, key=lambda item: item[0])
        if ready_mono >= earliest:
            loader_total_ms = _round3((ready_mono - earliest) / 1_000_000)
            loader_source = f"{earliest_name}->{ready_source}"

    exposed_ms = duration_ms
    hidden_ms: float | None = None
    if loader_total_ms is not None and exposed_ms is not None:
        hidden_value = loader_total_ms - exposed_ms
        if hidden_value >= 0:
            hidden_ms = _round3(hidden_value)

    return {
        "unet_future_ready_mono_ns": ready_mono,
        "first_consumer_wait_start_mono_ns": start_mono,
        "consumer_wait_end_mono_ns": end_mono,
        "consumer_wait_duration_ms": duration_ms,
        "unet_loader_total_ms": loader_total_ms,
        "unet_exposed_on_critical_path_ms": exposed_ms,
        "unet_hidden_under_other_work_ms": hidden_ms,
        "ready_available": ready_mono is not None,
        "consumer_available": duration_ms is not None,
        "sources": {
            "unet_future_ready_mono_ns": ready_source,
            "first_consumer_wait_start_mono_ns": start_source,
            "consumer_wait_end_mono_ns": end_source,
            "consumer_wait_duration_ms": duration_source,
            "unet_loader_total_ms": loader_source,
            "unet_exposed_on_critical_path_ms": duration_source,
            "unet_hidden_under_other_work_ms": loader_source,
        },
    }


def _segment(key: str, label: str, start: int | None, end: int | None) -> dict[str, Any]:
    """Top-level accounting segment: measured only when both boundaries exist."""
    if start is not None and end is not None and end >= start:
        return {
            "key": key,
            "label": label,
            "ms": _round3((end - start) / 1_000_000),
            "status": "measured",
        }
    return {"key": key, "label": label, "ms": None, "status": "unavailable"}


def _nested(
    key: str,
    label: str,
    category: str,
    start: int | None,
    end: int | None,
    parent: str,
) -> dict[str, Any]:
    """Nested explanatory stage: NON-ACCOUNTING, may overlap its parent and peers."""
    row: dict[str, Any] = {"key": key, "label": label, "category": category, "parent": parent}
    if start is not None and end is not None and end >= start:
        row["ms"] = _round3((end - start) / 1_000_000)
        row["status"] = "measured"
    else:
        row["ms"] = None
        row["status"] = "unavailable"
    row["non_accounting"] = True
    return row


def _residual_row(
    key: str,
    label: str,
    parent_ms: float | None,
    nested_children: Sequence[Mapping[str, Any]],
    parent: str,
) -> dict[str, Any]:
    """Interior residual row: explains one segment without affecting top-level
    residual. Derived when the parent segment is measured; unavailable when the
    parent boundary pair is missing."""
    row: dict[str, Any] = {"key": key, "label": label, "category": "residual", "parent": parent}
    if parent_ms is not None:
        measured_sum = sum(
            child["ms"] for child in nested_children
            if child.get("status") == "measured" and isinstance(child.get("ms"), (int, float))
        )
        row["ms"] = _round3(parent_ms - measured_sum)
        row["status"] = "derived"
    else:
        row["ms"] = None
        row["status"] = "unavailable"
    row["non_accounting"] = True
    return row


def _request_schedule_nested(result: Mapping[str, Any]) -> dict[str, Any]:
    """Request-schedule nested row from remote_setup_schedule metadata: the mono
    window when present (measured); else schedule_ms as derived; else unavailable."""
    row: dict[str, Any] = {
        "key": "request_schedule",
        "label": "Request schedule",
        "category": "waiting",
        "parent": "entry_to_plan_first_status",
    }
    schedule_start: int | None = None
    schedule_end: int | None = None
    for metadata in _metadata_events(result, "remote_setup_schedule"):
        start = _number(metadata.get("schedule_start_mono_ns"))
        end = _number(metadata.get("schedule_end_mono_ns"))
        if start is not None and start > 0 and end is not None and end > 0:
            schedule_start, schedule_end = start, end
            break
    if schedule_start is not None and schedule_end is not None and schedule_end >= schedule_start:
        row["ms"] = _round3((schedule_end - schedule_start) / 1_000_000)
        row["status"] = "measured"
    else:
        schedule_ms_values = [
            _ms_or_none(metadata.get("schedule_ms"))
            for metadata in _metadata_events(result, "remote_setup_schedule")
        ]
        schedule_ms = next((value for value in schedule_ms_values if value is not None), None)
        if schedule_ms is not None:
            row["ms"] = _round3(schedule_ms)
            row["status"] = "derived"
            row["source"] = "remote_setup_schedule.metadata.schedule_ms"
        else:
            row["ms"] = None
            row["status"] = "unavailable"
    row["non_accounting"] = True
    return row


def build_remote_setup_reconciliation(result: Mapping[str, Any]) -> dict[str, Any]:
    """Task A: reconcile the remote setup span against its children.

    Top-level accounting is disjoint and tiles the total: the two top-level
    segments (remote_method_entry -> run_plan_first_status_yield and
    run_plan_first_status_yield -> prompt_executor_invoke_start) are
    non-overlapping and sum to the full remote setup span whenever both
    boundary pairs exist. Nested details are NON-ACCOUNTING: they may overlap
    their parent AND each other (e.g. graph_start_to_invoke contains plan_proof)
    and are never subtracted from each other; they explain the segment without
    contributing to accounting_children_sum. Interior residual rows explain
    each segment without affecting the top-level residual, so residual_ms is
    only nonzero when a boundary is missing (degraded truth), never fabricated.
    """
    events = _events(result)

    setup_start = _last_mono(events, "remote_method_entry")
    yield_mono = _first_mono(events, "run_plan_first_status_yield")
    invoke_end = _first_mono(events, "prompt_executor_invoke_start")

    total_ms: float | None = None
    if setup_start is not None and invoke_end is not None:
        total_ms = _round3((invoke_end - setup_start) / 1_000_000)

    plan_proof_start = _first_mono(events, "plan_proof_start")
    if plan_proof_start is None:
        plan_proof_start = _first_mono(events, "plan_validation_payload")

    # Top-level segments: non-overlapping; they tile the total when all
    # boundaries exist.
    seg1 = _segment("entry_to_plan_first_status", "Entry to plan first status",
                    setup_start, yield_mono)
    seg2 = _segment("plan_first_status_to_executor", "Plan first status to executor",
                    yield_mono, invoke_end)
    top_level_segments = [seg1, seg2]

    # Nested explanatory stages (NON-ACCOUNTING; may overlap parent and peers).
    nested_seg1 = [
        _nested("identity_capture", "Identity capture", "cpu",
                _first_mono(events, "run_plan_identity_capture_start"),
                _first_mono(events, "run_plan_identity_capture_end"),
                "entry_to_plan_first_status"),
        _nested("plan_decode", "Plan decode", "cpu",
                _first_mono(events, "run_plan_deserialize_start"),
                _first_mono(events, "run_plan_deserialize_end"),
                "entry_to_plan_first_status"),
        _request_schedule_nested(result),
        _nested("trace_setup", "Trace setup", "cpu",
                _first_mono(events, "run_plan_trace_setup_start"),
                _first_mono(events, "run_plan_trace_setup_end"),
                "entry_to_plan_first_status"),
    ]
    nested_seg2 = [
        _nested("runtime_configuration", "Runtime configuration", "cpu",
                _first_mono(events, "runtime_config_start"),
                _first_mono(events, "runtime_config_end"),
                "plan_first_status_to_executor"),
        _nested("legacy_runtime_load", "Legacy runtime load", "cpu",
                _first_mono(events, "legacy_runtime_load_start"),
                _first_mono(events, "legacy_runtime_load_end"),
                "plan_first_status_to_executor"),
        _nested("execution_prefill_schedule", "Execution prefill schedule", "cpu",
                _first_mono(events, "execution_prefill_schedule_start"),
                _first_mono(events, "execution_prefill_schedule_end"),
                "plan_first_status_to_executor"),
        _nested("plan_proof", "Plan proof", "cpu",
                plan_proof_start, _first_mono(events, "plan_proof_decision"),
                "plan_first_status_to_executor"),
        _nested("graph_start_to_invoke", "Graph start to invoke", "cpu",
                _first_mono(events, "graph_execution_start"), invoke_end,
                "plan_first_status_to_executor"),
    ]

    residual_within_plan_receipt = _residual_row(
        "residual_within_plan_receipt", "Residual within plan receipt",
        seg1["ms"], nested_seg1, "entry_to_plan_first_status",
    )
    residual_after_plan_receipt = _residual_row(
        "residual_after_plan_receipt", "Residual after plan receipt",
        seg2["ms"], nested_seg2, "plan_first_status_to_executor",
    )

    nested_details = (
        list(nested_seg1) + [residual_within_plan_receipt]
        + list(nested_seg2) + [residual_after_plan_receipt]
    )

    accounting_children_sum = _round3(sum(
        segment["ms"] for segment in top_level_segments
        if segment.get("status") == "measured" and isinstance(segment.get("ms"), (int, float))
    ))
    measured_children_ms = accounting_children_sum

    waiting_ms = _round3(sum(
        row["ms"] for row in nested_details
        if row.get("category") == "waiting" and isinstance(row.get("ms"), (int, float))
    ))
    cpu_ms = _round3(sum(
        row["ms"] for row in nested_details
        if row.get("category") == "cpu" and isinstance(row.get("ms"), (int, float))
    ))

    residual_ms: float | None = None
    if total_ms is not None:
        residual_ms = _round3(total_ms - accounting_children_sum)

    if total_ms is None:
        status = "unavailable"
    elif residual_ms is not None and abs(residual_ms) <= 10.0:
        status = "closed"
    elif residual_ms is not None and abs(residual_ms) <= 50.0:
        status = "warning"
    else:
        status = "open"

    return {
        "remote_setup_total_ms": total_ms,
        "available": total_ms is not None,
        "top_level_segments": top_level_segments,
        "children": top_level_segments,
        "accounting_children_sum": accounting_children_sum,
        "measured_children_ms": measured_children_ms,
        "residual_ms": residual_ms,
        "nested_details": nested_details,
        "residual_classification": "unclassified",
        "category_summary": {
            "waiting_ms": waiting_ms,
            "cpu_ms": cpu_ms,
            "lock_future_join_ms": 0.0,
            "io_ms": 0.0,
        },
        "status": status,
        "reconciliation_target_ms": 10.0,
        "reconciliation_hard_ms": 50.0,
    }


def build_wait_reconciliation(result: Mapping[str, Any]) -> dict[str, Any]:
    """Task D: reconcile pre-sampler wall against node walls and waits.

    Node walls are sequential/disjoint by capture design and per-node waits are
    subsets of node walls; the aggregate resolve wait (future_wait_ms) is
    measured outside node windows, so outside-node future wait is the aggregate
    minus what per-node dependency_wait_wall already accounts for. residual_ms
    is reported as-is when negative (never clamped) with status "negative".
    """
    node_report = build_node_wait_report(result)
    structured = _as_mapping(result.get("pre_sampler_structured_report"))
    pre_sampler_total_ms = _ms_or_none(structured.get("pre_sampler_total_ms"))
    future_wait_aggregate_ms = _ms_or_none(structured.get("future_wait_ms"))

    def _sum_field(key: str) -> float:
        return _round3(sum(
            row[key] for row in node_report
            if isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool)
        ))

    node_wall_sum = _sum_field("total_node_wall")
    node_non_wait_sum = _sum_field("node_non_wait_wall")
    node_compute_sum = node_non_wait_sum
    dependency_wait_sum = _sum_field("dependency_wait_wall")
    async_model_future_sum = _sum_field(WAIT_ASYNC_MODEL_FUTURE)
    loader_wait_sum = _sum_field(WAIT_LOADER)
    mutation_lane_wait_sum = _sum_field(WAIT_MUTATION_LANE)
    sampler_lane_wait_sum = _sum_field(WAIT_SAMPLER_LANE)
    other_wait_sum = _sum_field(WAIT_OTHER)
    lane_wait_sum = _round3(mutation_lane_wait_sum + sampler_lane_wait_sum)

    future_wait_outside_nodes_ms = _round3(max(
        0.0, (future_wait_aggregate_ms or 0.0) - dependency_wait_sum
    ))
    accounted_ms = _round3(node_wall_sum + future_wait_outside_nodes_ms)

    residual_ms: float | None = None
    if pre_sampler_total_ms is not None:
        residual_ms = _round3(pre_sampler_total_ms - accounted_ms)

    if pre_sampler_total_ms is None:
        status = "unavailable"
    elif residual_ms is not None and residual_ms < 0:
        status = "negative"
    elif residual_ms is not None and residual_ms <= 50.0:
        status = "closed"
    else:
        status = "open"

    return {
        "pre_sampler_total_ms": pre_sampler_total_ms,
        "node_wall_sum": node_wall_sum,
        "node_non_wait_sum": node_non_wait_sum,
        "node_compute_sum": node_compute_sum,
        "dependency_wait_sum": dependency_wait_sum,
        "async_model_future_sum": async_model_future_sum,
        "loader_wait_sum": loader_wait_sum,
        "mutation_lane_wait_sum": mutation_lane_wait_sum,
        "sampler_lane_wait_sum": sampler_lane_wait_sum,
        "other_wait_sum": other_wait_sum,
        "lane_wait_sum": lane_wait_sum,
        "future_wait_aggregate_ms": future_wait_aggregate_ms,
        "future_wait_outside_nodes_ms": future_wait_outside_nodes_ms,
        "accounted_ms": accounted_ms,
        "residual_ms": residual_ms,
        "status": status,
    }
