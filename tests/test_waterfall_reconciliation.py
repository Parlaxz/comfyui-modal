"""V2 waterfall reconciliation verification suite.

Proves the waterfall now accounts for the FULL command->response wall using a
real-run fixture reconstructed from the quoted facts of run 20260812-142808
(the original pasted log was never attached; see
``tests/v2_waterfall_reconciliation_fixtures.py``) plus the 16 synthetic
scenarios from the task spec.

Key regression numbers (reconstruction):
  - command -> response wall   = 21994.0 ms (quoted 21.994 s)
  - modal scheduling           = 3859.877 ms (quoted 3.88 s)
  - pre-Python snapshot restore = 7330.0 ms (quoted ~7.33 s)
  - Python restore             = 549.0 ms (quoted ~0.549 s)
  - OLD accounting (deficient artifact, no submission boundary / no
    restore-begin input)      -> residual == 11208.877 ms
    (the quoted old residual was 10.731 s; the ~0.48 s drift comes from
    real-run stage values we cannot reproduce without the original log —
    the qualitative claim is identical: the residual IS the pre-Python
    window and the new model eliminates it)
  - NEW accounting (full fixture) -> residual == 0 (<= 25 ms target)
"""

from __future__ import annotations

import copy

from comfymodal_runtime.v2_waterfall import (
    DERIVED,
    INVALID,
    MEASURED,
    UNAVAILABLE,
)
from tests.v2_waterfall_reconciliation_fixtures import (
    BASE_NS,
    EXPECTED,
    PRE_PYTHON_MS,
    SCHEDULING_MS,
    build_real_run_result,
    chain_total_ms,
    command_start_ms,
    response_ns_for,
)
from tools.v2_waterfall import (
    build_waterfall,
    render_waterfall,
    waterfall_to_dict,
)

EXPECTED_STAGE_KEYS = [
    "local_preparation",
    "modal_handle_submission",
    "modal_scheduling",
    "pre_python_snapshot_restore",
    "application_restore",
    "restore_to_method_entry",
    "remote_method_setup",
    "prompt_executor_cache_setup",
    "pre_sampler_execution",
    "sampler_graph_join_wait",
    "sampler_node_to_sampling",
    "sampling",
    "post_sampling_transition",
    "vae",
    "output_persistence",
    "remote_return_handoff",
    "remote_local_return",
]


def _report(result, total_ms=None, **kwargs):
    return build_waterfall(
        result=result,
        timing={},
        wall_ms=None,
        command_start_unix_ms=command_start_ms(),
        response_received_unix_ns=response_ns_for(total_ms if total_ms is not None else result["wall_ms"]),
        **kwargs,
    )


def _stages(report):
    return {stage.key: stage for stage in report.stages}


def _detail_keys(report):
    return {detail.key: detail for detail in report.details}


def _dur(stage) -> float:
    assert stage.duration_ms is not None
    return stage.duration_ms


def _assert_tiles(report, total_ms, atol=0.02):
    """The exclusive top-level sum reconciles to the NON-SCHEDULING wall
    (command->response minus scheduling time = enqueue + placement), and
    residual/reconciliation are ~0."""
    assert report.total_ms is not None
    assert abs(report.total_ms - total_ms) < 1e-6
    assert report.non_scheduling_ms is not None
    accounted = sum(
        _dur(stage)
        for stage in report.stages
        if stage.accounting_role == "top_level" and not stage.concurrent
        and stage.duration_ms is not None and stage.status != INVALID
    )
    assert abs(accounted - report.non_scheduling_ms) < atol, (
        f"accounted {accounted} != non-scheduling wall {report.non_scheduling_ms}"
    )
    assert abs(accounted - report.accounted_ms) < 1e-6
    assert report.residual_ms is not None
    assert abs(report.residual_ms) <= atol, f"residual {report.residual_ms} exceeds {atol}ms"


# ── 1. Normal snapshot-restored run ────────────────────────────────────────
def test_normal_snapshot_restored_run_reconciles():
    result = build_real_run_result()
    report = _report(result)
    assert [stage.key for stage in report.stages] == EXPECTED_STAGE_KEYS
    stages = _stages(report)
    assert abs(_dur(stages["modal_scheduling"]) - SCHEDULING_MS) < 1e-6
    assert abs(_dur(stages["pre_python_snapshot_restore"]) - PRE_PYTHON_MS) < 1e-6
    assert abs(_dur(stages["application_restore"]) - EXPECTED["restore_ms"]) < 1e-6
    assert stages["pre_python_snapshot_restore"].provenance == "modal_app_log"
    _assert_tiles(report, EXPECTED["total_ms"])
    assert report.reconciliation_status == "OK"
    assert report.boundary_flags == ()


# ── 2. Huge scheduling delay ───────────────────────────────────────────────
def test_huge_scheduling_delay_reconciles():
    scheduling = 12000.0
    result = build_real_run_result(scheduling_ms=scheduling)
    total = chain_total_ms(scheduling_ms=scheduling)
    report = _report(result, total_ms=total)
    stages = _stages(report)
    assert abs(_dur(stages["modal_scheduling"]) - scheduling) < 1e-6
    assert stages["modal_scheduling"].status == MEASURED
    _assert_tiles(report, total)


# ── 3. Huge pre-Python restore ─────────────────────────────────────────────
def test_huge_pre_python_restore_reconciles():
    pre_python = 20000.0
    result = build_real_run_result(pre_python_ms=pre_python)
    total = chain_total_ms(pre_python_ms=pre_python)
    report = _report(result, total_ms=total)
    stages = _stages(report)
    assert abs(_dur(stages["pre_python_snapshot_restore"]) - pre_python) < 1e-6
    _assert_tiles(report, total)


# ── 4. Missing Modal restore-start event ───────────────────────────────────
def test_missing_modal_restore_start_flag_and_combined_interval():
    result = build_real_run_result(restore_begin=False)
    report = _report(result)
    assert "modal_restore_begin_unavailable" in report.boundary_flags
    stages = _stages(report)
    # Combined interval: submission -> python_resume = scheduling + pre-Python.
    assert abs(_dur(stages["modal_scheduling"]) - (SCHEDULING_MS + PRE_PYTHON_MS)) < 1e-6
    assert stages["modal_scheduling"].source_fields == ("submission_to_python_resume_ms",)
    assert stages["pre_python_snapshot_restore"].status == UNAVAILABLE
    # The combined scheduling interval is informational (excluded from
    # accounted), so accounted still equals the non-scheduling wall: nothing is
    # inflated.
    _assert_tiles(report, EXPECTED["total_ms"])


# ── 5. Cache-hit run ───────────────────────────────────────────────────────
def test_cache_hit_run_reconciles():
    restore = 50.0
    result = build_real_run_result(restore_ms=restore)
    total = chain_total_ms(restore_ms=restore)
    report = _report(result, total_ms=total)
    stages = _stages(report)
    assert abs(_dur(stages["application_restore"]) - restore) < 1e-6
    _assert_tiles(report, total)


# ── 6. Cache-miss run ──────────────────────────────────────────────────────
def test_cache_miss_run_reconciles():
    restore = 5000.0
    result = build_real_run_result(restore_ms=restore)
    total = chain_total_ms(restore_ms=restore)
    report = _report(result, total_ms=total)
    stages = _stages(report)
    assert abs(_dur(stages["application_restore"]) - restore) < 1e-6
    _assert_tiles(report, total)


# ── 7. UNET fast-disk load details ─────────────────────────────────────────
def test_unet_fast_disk_load_details_no_double_count():
    result = build_real_run_result()
    report = _report(result)
    details = _detail_keys(report)
    assert abs(_dur(details["unet_checkpoint_read"]) - 1047.0) < 1e-6
    assert abs(_dur(details["unet_read_to_construction"]) - 271.0) < 1e-6
    assert abs(_dur(details["unet_bind"]) - 158.0) < 1e-6
    assert abs(_dur(details["unet_synchronized_h2d"]) - 2214.0) < 1e-6
    assert abs(_dur(details["unet_demand_to_join"]) - 230.0) < 1e-6
    assert abs(_dur(details["unet_join_to_sampling"]) - 40.0) < 1e-6
    for detail in details.values():
        assert detail.included_in_total is False
    # Accounted unchanged by the children: still tiles exactly.
    _assert_tiles(report, EXPECTED["total_ms"])


# ── 8. VAE early activation details ────────────────────────────────────────
def test_vae_early_activation_details_no_double_count():
    result = build_real_run_result()
    report = _report(result)
    details = _detail_keys(report)
    assert abs(_dur(details["vae_sampling_end_to_scheduled"]) - 2.0) < 1e-6
    assert abs(_dur(details["vae_scheduled_to_load"]) - 5.0) < 1e-6
    assert abs(_dur(details["vae_load"]) - 870.9) < 1e-6
    assert abs(_dur(details["vae_ready_to_consumed"]) - 37.5) < 1e-6
    assert abs(_dur(details["vae_consumed_to_decode"]) - 1.0) < 1e-6
    for detail in details.values():
        assert detail.included_in_total is False
    _assert_tiles(report, EXPECTED["total_ms"])


# ── 9. Result yield before deferred persistence ────────────────────────────
def test_yield_before_deferred_persistence_renders_child():
    result = build_real_run_result()
    report = _report(result)
    details = _detail_keys(report)
    assert abs(_dur(details["output_deferred_commit"]) - 100.0) < 1e-6
    assert details["output_deferred_commit"].parent_key == "remote_return_handoff"
    _assert_tiles(report, EXPECTED["total_ms"])


# ── 10. All major events present ───────────────────────────────────────────
def test_all_events_present_residual_within_25ms():
    result = build_real_run_result()
    report = _report(result)
    assert report.total_ms is not None
    tolerance = max(25.0, report.total_ms * 0.0025)
    assert report.residual_ms is not None
    assert abs(report.residual_ms) <= tolerance
    assert abs(report.residual_ms) <= 25.0
    assert report.reconciliation_status == "OK"


# ── 11. Nested spans do not double-count ───────────────────────────────────
def test_nested_spans_never_double_count():
    result = build_real_run_result()
    report = _report(result)
    top_sum = sum(
        _dur(stage)
        for stage in report.stages
        if stage.accounting_role == "top_level" and not stage.concurrent
        and stage.duration_ms is not None and stage.status != INVALID
    )
    assert report.accounted_ms is not None
    assert abs(top_sum - report.accounted_ms) < 1e-6
    assert abs(top_sum - report.non_scheduling_ms) < 1e-6
    detail_sum = sum((detail.duration_ms or 0.0) for detail in report.details)
    assert abs(top_sum + detail_sum - report.non_scheduling_ms) > 1.0  # details overlap the top level


# ── 12. Overlapping UNET/prefill spans do not double-count ─────────────────
def test_overlapping_unet_prefill_no_double_count():
    result = build_real_run_result()
    report = _report(result)
    overlap_warnings = [w for w in report.warnings if "overlaps" in w]
    assert overlap_warnings == []
    for stage in report.stages:
        assert stage.status != INVALID
    _assert_tiles(report, EXPECTED["total_ms"])


# ── 13. No negative interval accepted silently ─────────────────────────────
def test_negative_interval_rejected_not_silent():
    result = build_real_run_result()
    # Invert the same-process sampling pair (remote mono, >= 2ms negative).
    sampling_start_ns = next(
        event["wall_unix_ns"] for event in result["trace"]["events"] if event["name"] == "sampling_start"
    )
    for event in result["trace"]["events"]:
        if event["name"] == "sampling_end":
            event["wall_unix_ns"] = sampling_start_ns - 500_000_000
            event["monotonic_ns"] = event["wall_unix_ns"] - 700_000_000_000
    report = _report(result)
    stages = _stages(report)
    assert stages["sampling"].status == INVALID
    assert any("negative duration" in w for w in report.warnings)
    # The invalid stage is excluded from accounted; residual reflects the gap.
    assert report.residual_ms is not None and report.residual_ms > 1000.0


# ── 14. Clock/domain mismatch detected ─────────────────────────────────────
def test_clock_domain_mismatch_detected():
    result = build_real_run_result()
    # Response BEFORE command start: total would be negative -> detected.
    report = build_waterfall(
        result=result,
        timing={},
        wall_ms=None,
        command_start_unix_ms=command_start_ms(),
        response_received_unix_ns=BASE_NS - 1_000_000,
    )
    assert report.total_ms is None
    assert any("command-to-response duration is negative" in w for w in report.warnings)


# ── 15. Missing child creates localized residual, not global residual ──────
def test_missing_child_localized_not_global():
    result = build_real_run_result(missing_children=True)
    report = _report(result)
    details = _detail_keys(report)
    assert details["prompt_executor_internal"].status == DERIVED
    assert abs(_dur(details["prompt_executor_internal"]) - 1.0) < 1e-6
    # Global residual unchanged: still tiles to the wall.
    _assert_tiles(report, EXPECTED["total_ms"])


# ── 16. Command->response exactly reconciles ───────────────────────────────
def test_command_response_exactly_reconciles():
    result = build_real_run_result()
    report = _report(result)
    assert report.accounted_ms is not None
    assert report.non_scheduling_ms is not None
    assert abs(report.accounted_ms - report.non_scheduling_ms) < 0.02
    assert report.residual_ms is not None
    assert abs(report.residual_ms) < 0.02
    assert report.reconciliation_status == "OK"


# ── OLD vs NEW accounting regression ───────────────────────────────────────
def test_old_vs_new_accounting():
    # NEW: full fixture -> exclusive top-level sum == non-scheduling wall,
    # residual ~0.
    result_new = build_real_run_result()
    report_new = _report(result_new)
    assert report_new.accounted_ms is not None
    assert report_new.non_scheduling_ms is not None
    assert abs(report_new.accounted_ms - report_new.non_scheduling_ms) < 25.0
    assert report_new.residual_ms is not None
    assert abs(report_new.residual_ms) <= 25.0

    # OLD: deficient artifact (no submission boundary, no restore-begin input)
    # reproduces the quoted failure mode: the pre-Python window is unaccounted
    # and the accounting gap stays honestly unresolved (no fake residual).
    result_old = build_real_run_result(boundaries=False, restore_begin=False)
    report_old = _report(result_old)
    assert "modal_restore_begin_unavailable" in report_old.boundary_flags
    assert "submission_boundary_unavailable" in report_old.boundary_flags
    stages_old = _stages(report_old)
    assert stages_old["modal_scheduling"].status == UNAVAILABLE
    assert stages_old["pre_python_snapshot_restore"].status == UNAVAILABLE
    assert report_old.total_wall_ms is None
    assert report_old.reconciliation_ms is None
    assert report_old.reconciliation_status == "UNRESOLVED"
    # Qualitative claim: the quoted old residual (10.731 s) IS the unaccounted
    # pre-Python window (~11.2 s in this reconstruction); the NEW model removes
    # it entirely once the host supplies the platform boundaries.
    assert report_old.total_ms is not None
    assert report_old.accounted_ms is not None
    assert (report_old.total_ms - report_old.accounted_ms) > 10000.0
    assert (report_old.total_ms - report_old.accounted_ms) < 12000.0


# ── Extra invariants ───────────────────────────────────────────────────────
def test_build_waterfall_does_not_mutate_inputs():
    result = build_real_run_result()
    before = copy.deepcopy(result)
    _report(result)
    assert result == before


def test_restore_begin_from_result_dict_honored():
    # kwarg None + dict key present -> split still happens.
    result = build_real_run_result()
    report = _report(result, modal_restore_begin_wall_unix_ns=None)
    stages = _stages(report)
    assert abs(_dur(stages["modal_scheduling"]) - SCHEDULING_MS) < 1e-6
    assert abs(_dur(stages["pre_python_snapshot_restore"]) - PRE_PYTHON_MS) < 1e-6
    assert report.boundary_flags == ()


def test_restore_begin_kwarg_wins_over_dict():
    result = build_real_run_result(restore_begin=False)
    wrong = BASE_NS + int(round((20.0 + 100.0) * 1_000_000))
    report = build_waterfall(
        result=result,
        timing={},
        wall_ms=None,
        command_start_unix_ms=command_start_ms(),
        response_received_unix_ns=response_ns_for(result["wall_ms"]),
        modal_restore_begin_wall_unix_ns=wrong,
    )
    stages = _stages(report)
    assert abs(_dur(stages["modal_scheduling"]) - 100.0) < 1e-6
    assert report.boundary_flags == ()


def test_render_footer_contains_walls_and_reconciliation():
    result = build_real_run_result()
    report = _report(result)
    rendered = render_waterfall(report)
    # One table + minimal boxed footer (Reconciliation / Status), plus the
    # three conclusive footer lines: COMMAND -> RESPONSE, Command (without
    # scheduling) -> Response, Scheduling time.  No user-facing TOTAL WALL.
    for expected in (
        "COMMAND -> RESPONSE:",
        "Command (without scheduling) -> Response:",
        "Scheduling time:",
        "RECONCILIATION",
        "STATUS",
    ):
        assert expected in rendered
    assert "TOTAL WALL" not in rendered
    # Successful console output never prints these accounting aggregates.
    for absent in (
        "TOP-LEVEL ACCOUNTED",
        "GLOBAL RESIDUAL",
        "RESIDUAL %",
        "RECONCILIATION STATUS",
        "CONTROLLABLE APPLICATION WALL",
        "PLATFORM/MODAL WALL",
    ):
        assert absent not in rendered
    assert report.controllable_wall_ms is not None
    assert report.platform_wall_ms is not None
    # Platform wall == scheduling + pre-Python restore only.
    assert abs(report.platform_wall_ms - (SCHEDULING_MS + PRE_PYTHON_MS)) < 1e-6
    # Controllable wall == total - platform - the scheduling-window local stages
    # (the whole enqueue window is informational under the new contract).
    assert abs(
        report.controllable_wall_ms
        - (EXPECTED["total_ms"] - report.platform_wall_ms - report.command_to_enqueue_ms)
    ) < 1e-6


def test_waterfall_to_dict_round_trip_preserves_reconciliation():
    result = build_real_run_result()
    report = _report(result)
    data = waterfall_to_dict(report)
    assert data["residual_ms"] == report.residual_ms
    assert data["residual_pct"] == report.residual_pct
    assert data["reconciliation_status"] == report.reconciliation_status
    assert data["controllable_wall_ms"] == report.controllable_wall_ms
    assert data["platform_wall_ms"] == report.platform_wall_ms
    assert data["boundary_flags"] == list(report.boundary_flags)
    stage = data["stages"][0]
    assert "provenance" in stage


def test_missing_boundaries_flag_both_when_deficient():
    result = build_real_run_result(boundaries=False, restore_begin=False)
    report = _report(result)
    assert set(report.boundary_flags) == {"modal_restore_begin_unavailable", "submission_boundary_unavailable"}
