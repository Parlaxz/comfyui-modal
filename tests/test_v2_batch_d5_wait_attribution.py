"""Synthetic test suite for Batch D5 wait attribution.

Covers the public API of comfymodal_runtime.wait_attribution:
extract_wait_windows / classify_node_wait / build_node_wait_report /
unet_first_consumer / build_remote_setup_reconciliation /
build_wait_reconciliation. All fixtures are fully synthetic — plain dicts with
one shared monotonic clock domain (node start_perf_ns/end_perf_ns and event
monotonic_ns are directly comparable, exactly as on the Modal/Linux runtime).
No Comfy remote, no Modal, no deploy.
"""

from __future__ import annotations

import pytest

from comfymodal_runtime.wait_attribution import (
    WAIT_ASYNC_MODEL_FUTURE,
    WAIT_LOADER,
    WAIT_MUTATION_LANE,
    WAIT_OTHER,
    WAIT_SAMPLER_LANE,
    WaitWindow,
    build_node_wait_report,
    build_remote_setup_reconciliation,
    build_wait_reconciliation,
    classify_node_wait,
    extract_wait_windows,
    unet_first_consumer,
)

# Shared monotonic clock base (ns); offsets below are in ms on top of it.
BASE_MONO_NS = 1_000_000_000_000


def _ms_ns(offset_ms: float) -> int:
    return BASE_MONO_NS + int(offset_ms * 1_000_000)


def _event(name: str, offset_ms: float, process: str = "remote", metadata: dict | None = None) -> dict:
    mono = _ms_ns(offset_ms)
    return {
        "name": name,
        "process": process,
        "wall_unix_ns": mono,
        "monotonic_ns": mono,
        "metadata": dict(metadata or {}),
    }


def _node(node_id: str, class_type: str, start_ms: float, end_ms: float, duration_ms: float | None = None, **extra) -> dict:
    record = {
        "node_id": node_id,
        "class_type": class_type,
        "duration_ms": duration_ms if duration_ms is not None else round(end_ms - start_ms, 3),
        "start_perf_ns": _ms_ns(start_ms),
        "end_perf_ns": _ms_ns(end_ms),
        "pass_outcome": "success",
    }
    record.update(extra)
    return record


def _make_result(events: list[dict], node_records: list[dict] | None = None, report_extra: dict | None = None) -> dict:
    report = {"per_node_timings": list(node_records or [])}
    report.update(report_extra or {})
    return {
        "trace": {"events": list(events), "metadata": {}},
        "pre_sampler_structured_report": report,
    }


def test_extract_wait_windows_kinds():
    result = _make_result([
        _event("graph_wait_start", 1000),
        _event("graph_wait_end", 1200),
        _event("unet_graph_join", 1300, metadata={
            "join_start_mono_ns": _ms_ns(1100),
            "join_completed_mono_ns": _ms_ns(1150),
        }),
        # Duration-only metadata must NOT fabricate a window.
        _event("unet_graph_join", 1400, metadata={"join_wait_ms": 50}),
        _event("unet_quiesce_wait_start", 1500),
        _event("unet_quiesce_wait_end", 1550),
        _event("sampler_lane_wait_start", 2000),
        _event("sampler_lane_wait_end", 2050),
        _event("unet_gpu_lane_wait_start", 2500),
        _event("unet_gpu_lane_wait_end", 2550),
    ])
    windows = extract_wait_windows(result)

    assert [w.kind for w in windows] == [
        WAIT_SAMPLER_LANE,
        WAIT_MUTATION_LANE,
        WAIT_LOADER,
        WAIT_ASYNC_MODEL_FUTURE,
        WAIT_ASYNC_MODEL_FUTURE,
    ]
    assert [w.priority for w in windows] == [5, 4, 3, 2, 2]
    assert windows[0].start_mono_ns == _ms_ns(2000)
    assert windows[0].end_mono_ns == _ms_ns(2050)
    assert windows[1].source == "unet_gpu_lane_wait_start/_end"
    assert windows[2].source == "graph_wait_start->graph_wait_end"
    assert windows[3].source == "unet_graph_join.metadata"
    assert windows[3].start_mono_ns == _ms_ns(1100)
    assert windows[4].source == "unet_quiesce_wait_start->unet_quiesce_wait_end"

    async_windows = [w for w in windows if w.kind == WAIT_ASYNC_MODEL_FUTURE]
    assert len(async_windows) == 2  # join metadata + quiesce; nothing from join_wait_ms
    assert not any(w.start_mono_ns == _ms_ns(1400) for w in async_windows)


def test_extract_wait_windows_degenerate_dropped():
    result = _make_result([
        _event("sampler_lane_wait_start", 1000),
        _event("sampler_lane_wait_end", 1000),  # end == start
        _event("sampler_lane_wait_start", 1100),
        _event("sampler_lane_wait_end", 1050),  # end < start
        _event("sampler_lane_wait_start", 1200),  # unpaired start
        _event("unet_gpu_lane_wait_start", 2000),  # unpaired start
        _event("graph_wait_start", 3000),
        _event("graph_wait_end", 3100),
    ])
    windows = extract_wait_windows(result)

    assert len(windows) == 1
    assert windows[0].kind == WAIT_LOADER
    assert windows[0].start_mono_ns == _ms_ns(3000)
    assert windows[0].end_mono_ns == _ms_ns(3100)


def test_classify_impact_switch_misattribution():
    """The headline D5 scenario: a 2s ImpactSwitch that really waited 1.9s for
    UNET must be classified as wait, not compute."""
    result = _make_result(
        events=[
            _event("graph_wait_start", 400),
            _event("graph_wait_end", 2300),
        ],
        node_records=[
            _node("1", "UNETLoader", 0, 300, duration_ms=300.0),
            _node("2", "ImpactSwitch", 300, 2300, duration_ms=2000.0),
        ],
    )
    windows = extract_wait_windows(result)
    unet = classify_node_wait(result["pre_sampler_structured_report"]["per_node_timings"][0], windows)
    impact = classify_node_wait(result["pre_sampler_structured_report"]["per_node_timings"][1], windows)

    assert unet["loader_wait"] == pytest.approx(0.0, abs=0.01)
    assert unet["node_non_wait_wall"] == pytest.approx(300.0, abs=0.01)
    assert unet["node_compute_wall"] == unet["node_non_wait_wall"]

    assert impact["total_node_wall"] == pytest.approx(2000.0, abs=0.01)
    assert impact["loader_wait"] == pytest.approx(1900.0, abs=0.01)
    assert impact["node_non_wait_wall"] == pytest.approx(100.0, abs=0.01)
    assert impact["node_compute_wall"] == impact["node_non_wait_wall"]
    assert impact["wait_total"] == pytest.approx(1900.0, abs=0.01)
    assert impact["wait_kinds"] == (WAIT_LOADER,)
    assert impact["available"] is True


def test_classify_no_double_count_overlap():
    result = _make_result(
        events=[
            _event("sampler_lane_wait_start", 200),
            _event("sampler_lane_wait_end", 800),
            _event("graph_wait_start", 400),
            _event("graph_wait_end", 900),
        ],
        node_records=[
            _node("1", "KSampler", 0, 1000, duration_ms=1000.0),
        ],
    )
    windows = extract_wait_windows(result)
    classified = classify_node_wait(result["pre_sampler_structured_report"]["per_node_timings"][0], windows)

    # sampler (priority 5) wins [200,800]; loader only gets the uncovered
    # [800,900] slice: union covered length is 700ms, never double counted.
    assert classified[WAIT_SAMPLER_LANE] == pytest.approx(600.0, abs=0.01)
    assert classified[WAIT_LOADER] == pytest.approx(100.0, abs=0.01)
    assert classified["wait_total"] == pytest.approx(700.0, abs=0.01)
    assert classified["total_node_wall"] == pytest.approx(1000.0, abs=0.01)
    assert classified["node_non_wait_wall"] == pytest.approx(300.0, abs=0.01)
    assert classified["node_compute_wall"] == classified["node_non_wait_wall"]
    assert classified["wait_kinds"] == (WAIT_SAMPLER_LANE, WAIT_LOADER)
    assert classified["wait_total"] <= classified["total_node_wall"]


def test_classify_dependency_wait_field():
    result = _make_result(
        events=[
            _event("graph_wait_start", 100),
            _event("graph_wait_end", 200),
        ],
        node_records=[
            _node("1", "UNETLoader", 0, 500, duration_ms=500.0, dependency_wait_wall=50.0),
        ],
    )
    windows = extract_wait_windows(result)
    classified = classify_node_wait(result["pre_sampler_structured_report"]["per_node_timings"][0], windows)

    assert classified["dependency_wait_wall"] == pytest.approx(50.0, abs=0.01)
    assert classified[WAIT_LOADER] == pytest.approx(100.0, abs=0.01)
    assert classified["wait_total"] == pytest.approx(150.0, abs=0.01)
    assert classified["node_non_wait_wall"] == pytest.approx(350.0, abs=0.01)
    assert classified["node_compute_wall"] == classified["node_non_wait_wall"]
    assert classified["total_node_wall"] == pytest.approx(500.0, abs=0.01)

    # Overlap variant: dependency is subtracted first as covered, so the loader
    # window only counts the portion outside the dependency interval.
    overlapped = classify_node_wait(
        _node("2", "UNETLoader", 0, 500, duration_ms=500.0, dependency_wait_wall=150.0),
        windows,
    )
    assert overlapped["dependency_wait_wall"] == pytest.approx(150.0, abs=0.01)
    assert overlapped[WAIT_LOADER] == pytest.approx(50.0, abs=0.01)
    assert overlapped["wait_total"] == pytest.approx(200.0, abs=0.01)
    assert overlapped["node_non_wait_wall"] == pytest.approx(300.0, abs=0.01)
    assert overlapped["node_compute_wall"] == overlapped["node_non_wait_wall"]


def test_classify_unavailable():
    assert classify_node_wait({}, [])["available"] is False
    assert classify_node_wait(_node("1", "X", 500, 100), [])["available"] is False  # end < start

    unavailable = classify_node_wait({"node_id": "1", "class_type": "X"}, [])
    assert unavailable["available"] is False
    assert unavailable["total_node_wall"] is None
    assert unavailable["node_non_wait_wall"] is None
    assert unavailable["node_compute_wall"] is None
    assert unavailable["wait_total"] is None
    assert unavailable["wait_kinds"] == ()

    report = build_node_wait_report({"pre_sampler_structured_report": {
        "per_node_timings": [
            "garbage",
            42,
            {"node_id": "1", "class_type": "X", "start_perf_ns": None, "end_perf_ns": None},
        ],
    }})
    assert len(report) == 1
    assert report[0]["node_id"] == "1"
    assert report[0]["available"] is False


def test_unet_first_consumer():
    result = _make_result([
        _event("unet_early_activation_scheduled", 800),
        _event("unet_early_activation_terminal", 1000),
        _event("graph_unet_demand", 1500),
        _event("graph_unet_wait_end", 1900),
    ])
    rec = unet_first_consumer(result)

    assert rec["unet_future_ready_mono_ns"] == _ms_ns(1000)
    assert rec["first_consumer_wait_start_mono_ns"] == _ms_ns(1500)
    assert rec["consumer_wait_end_mono_ns"] == _ms_ns(1900)
    assert rec["consumer_wait_duration_ms"] == pytest.approx(400.0, abs=0.01)
    assert rec["unet_loader_total_ms"] == pytest.approx(200.0, abs=0.01)
    assert rec["unet_exposed_on_critical_path_ms"] == pytest.approx(400.0, abs=0.01)
    # loader_total (200) < exposed (400): the module reports None (">= 0, else
    # None" per its spec) rather than clamping to 0 — see summary.
    assert rec["unet_hidden_under_other_work_ms"] is None
    assert rec["ready_available"] is True
    assert rec["consumer_available"] is True
    assert rec["sources"]["unet_future_ready_mono_ns"] == "unet_early_activation_terminal"
    assert rec["sources"]["first_consumer_wait_start_mono_ns"] == "graph_unet_demand"
    assert rec["sources"]["consumer_wait_end_mono_ns"] == "graph_unet_wait_end"
    assert rec["sources"]["consumer_wait_duration_ms"] == "computed:graph_unet_demand->graph_unet_wait_end"
    assert rec["sources"]["unet_loader_total_ms"] == "unet_early_activation_scheduled->unet_early_activation_terminal"

    # Variant: demand BEFORE the UNET is ready (exposed wait longer than load).
    early = unet_first_consumer(_make_result([
        _event("unet_early_activation_scheduled", 800),
        _event("unet_early_activation_terminal", 1000),
        _event("graph_unet_demand", 500),
        _event("graph_unet_wait_end", 1400),
    ]))
    assert early["unet_future_ready_mono_ns"] == _ms_ns(1000)
    assert early["first_consumer_wait_start_mono_ns"] == _ms_ns(500)
    assert early["consumer_wait_duration_ms"] == pytest.approx(900.0, abs=0.01)
    assert early["unet_exposed_on_critical_path_ms"] == pytest.approx(900.0, abs=0.01)
    assert early["unet_hidden_under_other_work_ms"] is None  # 200 - 900 < 0

    # Positive hidden path: load (1000ms) longer than the exposed wait (100ms).
    hidden = unet_first_consumer(_make_result([
        _event("unet_early_activation_scheduled", 0),
        _event("unet_early_activation_terminal", 1000),
        _event("graph_unet_demand", 1100),
        _event("graph_unet_wait_end", 1200),
    ]))
    assert hidden["consumer_wait_duration_ms"] == pytest.approx(100.0, abs=0.01)
    assert hidden["unet_loader_total_ms"] == pytest.approx(1000.0, abs=0.01)
    assert hidden["unet_exposed_on_critical_path_ms"] == pytest.approx(100.0, abs=0.01)
    assert hidden["unet_hidden_under_other_work_ms"] == pytest.approx(900.0, abs=0.01)


def test_unet_first_consumer_missing_events():
    rec = unet_first_consumer({})

    assert rec["unet_future_ready_mono_ns"] is None
    assert rec["first_consumer_wait_start_mono_ns"] is None
    assert rec["consumer_wait_end_mono_ns"] is None
    assert rec["consumer_wait_duration_ms"] is None
    assert rec["unet_loader_total_ms"] is None
    assert rec["unet_exposed_on_critical_path_ms"] is None
    assert rec["unet_hidden_under_other_work_ms"] is None
    assert rec["ready_available"] is False
    assert rec["consumer_available"] is False
    assert all(source is None for source in rec["sources"].values())


_REMOTE_SETUP_EVENTS = [
    _event("remote_method_entry", 0),
    _event("run_plan_identity_capture_start", 10),
    _event("run_plan_identity_capture_end", 15),
    _event("run_plan_deserialize_start", 15),
    _event("run_plan_deserialize_end", 25),
    _event("remote_setup_schedule", 700, metadata={
        "schedule_start_mono_ns": _ms_ns(25),
        "schedule_end_mono_ns": _ms_ns(95),
        "schedule_ms": 70,
    }),
    _event("run_plan_trace_setup_start", 95),
    _event("run_plan_trace_setup_end", 120),
    _event("run_plan_first_status_yield", 600),
    _event("runtime_config_start", 610),
    _event("runtime_config_end", 650),
    _event("legacy_runtime_load_start", 650),
    _event("legacy_runtime_load_end", 660),
    _event("execution_prefill_schedule_start", 660),
    _event("execution_prefill_schedule_end", 665),
    _event("plan_proof_start", 1015),
    _event("plan_validation_payload", 1020),
    _event("plan_proof_decision", 1025),
    _event("graph_execution_start", 1010),
    _event("prompt_executor_invoke_start", 1100),
]

_TOP_LEVEL_KEYS = [
    "entry_to_plan_first_status",
    "plan_first_status_to_executor",
]

_NESTED_DETAIL_KEYS = [
    # Segment 1 (entry -> first status yield) nested stages, then its residual.
    "identity_capture",
    "plan_decode",
    "request_schedule",
    "trace_setup",
    "residual_within_plan_receipt",
    # Segment 2 (first status yield -> invoke) nested stages, then its residual.
    "runtime_configuration",
    "legacy_runtime_load",
    "execution_prefill_schedule",
    "plan_proof",
    "graph_start_to_invoke",
    "residual_after_plan_receipt",
]


def _setup_reconciliation_result() -> dict:
    return build_remote_setup_reconciliation(_make_result(_REMOTE_SETUP_EVENTS))


def test_remote_setup_reconciliation_non_overlapping_segments():
    """Top-level segments tile the total: seg1 (entry->yield) = 600ms and
    seg2 (yield->invoke) = 500ms, so remote_setup_total_ms = 1100ms. Nested
    stages live INSIDE their parents and overlap (identity_capture 5ms inside
    seg1, plan_decode 10ms overlapping identity, request_schedule 70ms
    overlapping both, graph_start_to_invoke 90ms CONTAINING plan_proof 10ms)
    but are NON-ACCOUNTING and never affect accounting_children_sum."""
    rec = _setup_reconciliation_result()

    assert rec["remote_setup_total_ms"] == pytest.approx(1100.0, abs=0.001)
    assert rec["available"] is True
    assert [seg["key"] for seg in rec["top_level_segments"]] == _TOP_LEVEL_KEYS
    assert [seg["ms"] for seg in rec["top_level_segments"]] == [600.0, 500.0]
    assert all(seg["status"] == "measured" for seg in rec["top_level_segments"])

    # children is the backward-compat alias of top_level_segments.
    assert rec["children"] is rec["top_level_segments"]

    # Accounting sums ONLY the two disjoint top-level segments.
    assert rec["accounting_children_sum"] == pytest.approx(1100.0, abs=0.001)
    assert rec["measured_children_ms"] == pytest.approx(1100.0, abs=0.001)
    assert rec["measured_children_ms"] == rec["accounting_children_sum"]
    assert rec["accounting_children_sum"] == pytest.approx(
        sum(seg["ms"] for seg in rec["top_level_segments"]), abs=0.001
    )

    # Every nested_details row is non-accounting; the measured nested stages sum
    # to 265ms (not 1100ms) and neither add to nor subtract from the 1100ms
    # accounting_children_sum.
    assert [row["key"] for row in rec["nested_details"]] == _NESTED_DETAIL_KEYS
    assert all(row["non_accounting"] is True for row in rec["nested_details"])
    nested_stage_sum = sum(
        row["ms"] for row in rec["nested_details"]
        if row.get("category") != "residual" and isinstance(row["ms"], (int, float))
    )
    assert nested_stage_sum == pytest.approx(265.0, abs=0.001)
    assert nested_stage_sum != rec["accounting_children_sum"]

    assert rec["residual_ms"] == pytest.approx(0.0, abs=0.001)
    assert rec["residual_ms"] == pytest.approx(
        rec["remote_setup_total_ms"] - rec["accounting_children_sum"], abs=0.001
    )
    assert rec["status"] == "closed"
    assert rec["reconciliation_target_ms"] == 10.0
    assert rec["reconciliation_hard_ms"] == 50.0
    assert rec["residual_classification"] == "unclassified"


def test_remote_setup_nested_overlap_residual_exact():
    """Interior residual rows subtract each measured nested child from its OWN
    parent segment: residual_within_plan_receipt = 600 - (5+10+70+25) = 490.0
    and residual_after_plan_receipt = 500 - (40+10+5+10+90) = 345.0 exactly.
    Overlapping nested rows (graph_start_to_invoke vs plan_proof) each subtract
    from the parent but never from each other."""
    rec = _setup_reconciliation_result()
    by_key = {row["key"]: row for row in rec["nested_details"]}

    assert by_key["identity_capture"]["ms"] == pytest.approx(5.0, abs=0.01)
    assert by_key["plan_decode"]["ms"] == pytest.approx(10.0, abs=0.01)
    assert by_key["request_schedule"]["ms"] == pytest.approx(70.0, abs=0.01)
    assert by_key["trace_setup"]["ms"] == pytest.approx(25.0, abs=0.01)
    assert by_key["runtime_configuration"]["ms"] == pytest.approx(40.0, abs=0.01)
    assert by_key["legacy_runtime_load"]["ms"] == pytest.approx(10.0, abs=0.01)
    assert by_key["execution_prefill_schedule"]["ms"] == pytest.approx(5.0, abs=0.01)
    # Plan proof comes from plan_proof_start (1015), not the validation_payload
    # fallback (1020).
    assert by_key["plan_proof"]["ms"] == pytest.approx(10.0, abs=0.01)
    assert by_key["graph_start_to_invoke"]["ms"] == pytest.approx(90.0, abs=0.01)

    assert by_key["residual_within_plan_receipt"]["ms"] == round(600.0 - (5 + 10 + 70 + 25), 3)
    assert by_key["residual_within_plan_receipt"]["ms"] == 490.0
    assert by_key["residual_after_plan_receipt"]["ms"] == round(500.0 - (40 + 10 + 5 + 10 + 90), 3)
    assert by_key["residual_after_plan_receipt"]["ms"] == 345.0
    assert by_key["residual_within_plan_receipt"]["status"] == "derived"
    assert by_key["residual_after_plan_receipt"]["status"] == "derived"
    assert by_key["residual_within_plan_receipt"]["category"] == "residual"
    assert by_key["residual_after_plan_receipt"]["category"] == "residual"


def test_remote_setup_reconciliation_status_ladder():
    # Closed: both segments measured -> residual ~0 under exact tiling.
    closed = _setup_reconciliation_result()
    assert closed["status"] == "closed"
    assert closed["residual_ms"] == pytest.approx(0.0, abs=0.001)

    # Note: under exact tiling the "warning" band (10 < abs(residual) <= 50) is
    # unreachable because the residual is 0 whenever both segments are measured.
    # The thresholds remain for future non-tiling cases (e.g. a partial total
    # from degraded boundary coverage).

    # Open: missing run_plan_first_status_yield -> BOTH top-level segments
    # unavailable -> accounting_children_sum 0.0 -> residual == total > 50.
    open_events = [event for event in _REMOTE_SETUP_EVENTS if event["name"] != "run_plan_first_status_yield"]
    open_rec = build_remote_setup_reconciliation(_make_result(open_events))
    assert open_rec["remote_setup_total_ms"] == pytest.approx(1100.0, abs=0.01)
    assert all(seg["status"] == "unavailable" for seg in open_rec["top_level_segments"])
    assert open_rec["accounting_children_sum"] == pytest.approx(0.0, abs=0.01)
    assert open_rec["residual_ms"] == pytest.approx(1100.0, abs=0.01)
    assert open_rec["status"] == "open"

    # Unavailable: missing remote_method_entry -> no total at all (seg2 may
    # still be measurable, but without the entry boundary there is no total).
    no_entry_events = [event for event in _REMOTE_SETUP_EVENTS if event["name"] != "remote_method_entry"]
    unavailable = build_remote_setup_reconciliation(_make_result(no_entry_events))
    assert unavailable["remote_setup_total_ms"] is None
    assert unavailable["available"] is False
    assert unavailable["residual_ms"] is None
    assert unavailable["status"] == "unavailable"


def test_remote_setup_residual_never_negative():
    """With both top-level segments measured the residual is exactly 0 and the
    interior residual rows are non-negative: nested children never subtract
    from each other, so a parent segment can never be driven negative."""
    rec = _setup_reconciliation_result()
    assert rec["residual_ms"] == 0.0
    by_key = {row["key"]: row for row in rec["nested_details"]}
    assert by_key["residual_within_plan_receipt"]["ms"] == 490.0
    assert by_key["residual_after_plan_receipt"]["ms"] == 345.0
    assert by_key["residual_within_plan_receipt"]["ms"] >= 0.0
    assert by_key["residual_after_plan_receipt"]["ms"] >= 0.0


def test_wait_reconciliation():
    result = _make_result(
        events=[
            _event("graph_wait_start", 100),
            _event("graph_wait_end", 300),
            _event("graph_wait_start", 400),
            _event("graph_wait_end", 2300),
        ],
        node_records=[
            _node("1", "UNETLoader", 0, 300, duration_ms=300.0),
            _node("2", "ImpactSwitch", 300, 2300, duration_ms=2000.0),
            _node("3", "CLIPLoader", 2300, 2350, duration_ms=50.0, dependency_wait_wall=50.0),
        ],
        report_extra={"pre_sampler_total_ms": 2600.0, "future_wait_ms": 50.0},
    )

    rows = {row["node_id"]: row for row in build_node_wait_report(result)}
    assert rows["1"][WAIT_LOADER] == pytest.approx(200.0, abs=0.01)
    assert rows["1"]["node_non_wait_wall"] == pytest.approx(100.0, abs=0.01)
    assert rows["1"]["node_compute_wall"] == rows["1"]["node_non_wait_wall"]
    assert rows["2"][WAIT_LOADER] == pytest.approx(1900.0, abs=0.01)
    assert rows["2"]["node_non_wait_wall"] == pytest.approx(100.0, abs=0.01)
    assert rows["2"]["node_compute_wall"] == rows["2"]["node_non_wait_wall"]
    assert rows["3"]["dependency_wait_wall"] == pytest.approx(50.0, abs=0.01)
    assert rows["3"]["node_non_wait_wall"] == pytest.approx(0.0, abs=0.01)
    assert rows["3"]["node_compute_wall"] == rows["3"]["node_non_wait_wall"]

    rec = build_wait_reconciliation(result)
    assert rec["node_wall_sum"] == pytest.approx(2350.0, abs=0.01)
    assert rec["node_non_wait_sum"] == pytest.approx(200.0, abs=0.01)
    assert rec["node_compute_sum"] == rec["node_non_wait_sum"]
    assert rec["dependency_wait_sum"] == pytest.approx(50.0, abs=0.01)
    assert rec["async_model_future_sum"] == pytest.approx(0.0, abs=0.01)
    assert rec["loader_wait_sum"] == pytest.approx(2100.0, abs=0.01)
    assert rec["mutation_lane_wait_sum"] == pytest.approx(0.0, abs=0.01)
    assert rec["sampler_lane_wait_sum"] == pytest.approx(0.0, abs=0.01)
    assert rec["other_wait_sum"] == pytest.approx(0.0, abs=0.01)
    assert rec["lane_wait_sum"] == pytest.approx(0.0, abs=0.01)
    assert rec["future_wait_aggregate_ms"] == pytest.approx(50.0, abs=0.01)
    # The per-node dependency wait fully accounts for the 50ms aggregate resolve
    # wait, so nothing remains outside the node windows.
    assert rec["future_wait_outside_nodes_ms"] == pytest.approx(0.0, abs=0.01)
    assert rec["accounted_ms"] == pytest.approx(2350.0, abs=0.01)
    assert rec["accounted_ms"] == pytest.approx(
        rec["node_wall_sum"] + rec["future_wait_outside_nodes_ms"], abs=0.01
    )
    assert rec["residual_ms"] == pytest.approx(250.0, abs=0.01)
    assert rec["status"] == "open"

    closed_result = _make_result(
        events=[
            _event("graph_wait_start", 100),
            _event("graph_wait_end", 300),
            _event("graph_wait_start", 400),
            _event("graph_wait_end", 2300),
        ],
        node_records=[
            _node("1", "UNETLoader", 0, 300, duration_ms=300.0),
            _node("2", "ImpactSwitch", 300, 2300, duration_ms=2000.0),
        ],
        report_extra={"pre_sampler_total_ms": 2400.0, "future_wait_ms": 50.0},
    )
    closed = build_wait_reconciliation(closed_result)
    assert closed["node_wall_sum"] == pytest.approx(2300.0, abs=0.01)
    assert closed["residual_ms"] == pytest.approx(50.0, abs=0.01)
    assert closed["status"] == "closed"


def test_empty_result_no_fabrication():
    remote = build_remote_setup_reconciliation({})
    assert remote["remote_setup_total_ms"] is None
    assert remote["available"] is False
    assert remote["residual_ms"] is None
    assert remote["status"] == "unavailable"
    assert len(remote["top_level_segments"]) == 2
    assert all(seg["ms"] is None and seg["status"] == "unavailable" for seg in remote["top_level_segments"])
    assert remote["accounting_children_sum"] == pytest.approx(0.0, abs=0.01)
    assert remote["measured_children_ms"] == remote["accounting_children_sum"]
    # Nested details degrade to unavailable (never fabricated): all rows carry
    # ms None and every nested row is explicitly non-accounting.
    assert len(remote["nested_details"]) == 11
    assert all(row["ms"] is None for row in remote["nested_details"])
    assert all(row["non_accounting"] is True for row in remote["nested_details"])
    assert all(row["status"] == "unavailable" for row in remote["nested_details"])

    wait = build_wait_reconciliation({})
    assert wait["pre_sampler_total_ms"] is None
    assert wait["status"] == "unavailable"
    assert wait["node_wall_sum"] == pytest.approx(0.0, abs=0.01)
    assert wait["accounted_ms"] == pytest.approx(0.0, abs=0.01)
    assert wait["residual_ms"] is None
    assert wait["future_wait_aggregate_ms"] is None
    assert wait["future_wait_outside_nodes_ms"] == pytest.approx(0.0, abs=0.01)

    assert build_node_wait_report({}) == []
