"""Scheduling-denominator regression tests for the V2 waterfall.

The V2 scheduling fix introduced ``scheduling_ms`` / ``total_wall_ms`` /
``command_response_ms`` on ``WaterfallReport``.  ``total_wall_ms`` is the
command->response wall MINUS Modal scheduling; stage percentages and bars use
``total_wall`` when it is available, while reconciliation stays against the
full command->response ``total_ms``.  A huge Modal scheduling delay must no
longer dilute the sampling-stage percentage (the core regression: sampling %
used to be computed against the full wall).

NOTE on fixture numbers: the real-run fixture's non-scheduling, non-sampling
stages sum to ``TOTAL_MS - SCHEDULING_MS - SAMPLING_MS`` (~16.37 s), so with
``scheduling_ms=200000`` the total wall is that fixed sum plus sampling.  The
tests therefore choose ``sampling_ms`` equal to that fixed sum, making the
sampling stage EXACTLY 50% of the total wall — the same percentage claim the
task requires — while keeping the chain tiling exact so reconciliation stays
OK.  Under the OLD denominator (full command->response total) the same run
reports ~7%, so the regression is still proven.
"""

from __future__ import annotations

import pytest

from comfymodal_runtime.v2_waterfall import (
    build_waterfall,
    render_waterfall,
    waterfall_to_dict,
)
from tests.v2_waterfall_reconciliation_fixtures import (
    SAMPLING_MS,
    SCHEDULING_MS,
    TOTAL_MS,
    build_real_run_result,
    chain_total_ms,
    command_start_ms,
    response_ns_for,
)


def _report(result, total_ms=None, **kwargs):
    return build_waterfall(
        result=result,
        timing={},
        wall_ms=None,
        command_start_unix_ms=command_start_ms(),
        response_received_unix_ns=response_ns_for(
            total_ms if total_ms is not None else result["wall_ms"]
        ),
        **kwargs,
    )


def _stages(report):
    return {stage.key: stage for stage in report.stages}


def _fixed_sum() -> float:
    """Sum of the fixture's non-scheduling, non-sampling stage durations."""
    return TOTAL_MS - SCHEDULING_MS - SAMPLING_MS


# ── 1. Extreme scheduling does not poison the denominator ──────────────────
def test_extreme_scheduling_denominator():
    """With a 200 s scheduling delay the report still separates the walls:
    total_wall = total - scheduling, sampling is 50% of total_wall (NOT ~7%
    of total), scheduling shows no percentage, and the full wall still
    reconciles."""
    scheduling = 200000.0
    sampling = _fixed_sum()  # => sampling is exactly 50% of the total wall
    total = chain_total_ms(scheduling_ms=scheduling, sampling_ms=sampling)
    result = build_real_run_result(scheduling_ms=scheduling, sampling_ms=sampling)
    report = _report(result, total_ms=total)

    # command->response total == scheduling + total_wall.
    assert report.total_ms == pytest.approx(total)
    assert report.scheduling_ms == pytest.approx(scheduling)
    assert report.total_wall_ms == pytest.approx(total - scheduling)
    assert report.command_response_ms == pytest.approx(total)
    assert report.total_ms == pytest.approx(report.scheduling_ms + report.total_wall_ms)

    stages = _stages(report)
    sampling_stage = stages["sampling"]
    assert sampling_stage.duration_ms == pytest.approx(sampling)
    # The regression: percentage is computed against total_wall, so sampling
    # is ~50% — under the OLD total-denominator it would be ~7%.
    assert sampling_stage.percentage == pytest.approx(50.0, abs=0.5)
    old_denominator_pct = sampling / report.total_ms * 100.0
    assert sampling_stage.percentage > old_denominator_pct * 2

    # Reconciliation compares the exclusive top-level sum to the non-scheduling
    # wall (command->response minus scheduling time).
    assert report.reconciliation_status == "OK"
    assert report.accounted_ms is not None
    assert abs(report.accounted_ms - report.non_scheduling_ms) < 25.0
    # Scheduling is informational: it never appears as a numbered table row.
    rendered = render_waterfall(report, terminal_columns=132)
    assert not any(
        "Modal scheduling" in line and "|" in line and line.strip()[:1].isdigit()
        for line in rendered.splitlines()
    )
    # The scheduling window is summarized exactly once, in the conclusive
    # "Scheduling time:" footer line.
    assert "| SCHEDULING" not in rendered
    assert rendered.count("Scheduling time:") == 1


# ── 2. Scheduling is informational: no table row, no % / bar ───────────────
def test_scheduling_row_no_percent_no_bar():
    scheduling = 200000.0
    sampling = _fixed_sum()
    total = chain_total_ms(scheduling_ms=scheduling, sampling_ms=sampling)
    result = build_real_run_result(scheduling_ms=scheduling, sampling_ms=sampling)
    report = _report(result, total_ms=total)

    rendered = render_waterfall(report, terminal_columns=132)
    for expected in (
        "COMMAND -> RESPONSE:",
        "Command (without scheduling) -> Response:",
        "Scheduling time:",
    ):
        assert expected in rendered, f"conclusive footer missing {expected!r}"
    assert "TOTAL WALL" not in rendered

    # No numbered table row mentions scheduling; the scheduling window is
    # summarized exactly once in the conclusive "Scheduling time:" footer line.
    table_rows = [
        line for line in rendered.splitlines()
        if line.strip()[:1].isdigit() and "|" in line
    ]
    assert not any("SCHEDULING" in line for line in table_rows)
    footer_rows = [line for line in rendered.splitlines() if "| SCHEDULING" in line]
    assert len(footer_rows) == 0
    scheduling_lines = [line for line in rendered.splitlines() if line.startswith("Scheduling time:")]
    assert len(scheduling_lines) == 1
    assert "%" not in scheduling_lines[0]
    assert "#" not in scheduling_lines[0]


# ── 3. Core regression: sampling % uses total_wall, not total ──────────────
def test_sampling_percentage_uses_total_wall():
    """Sampling is 50% of the total wall; the old denominator (full command->
    response total) would dilute it to ~7%.  This is the scheduling-
    denominator regression the fix landed for."""
    scheduling = 200000.0
    sampling = _fixed_sum()
    total = chain_total_ms(scheduling_ms=scheduling, sampling_ms=sampling)
    result = build_real_run_result(scheduling_ms=scheduling, sampling_ms=sampling)
    report = _report(result, total_ms=total)

    stages = _stages(report)
    percentage = stages["sampling"].percentage
    assert percentage == pytest.approx(50.0, abs=0.5)
    # Clearly not the total-denominator value.
    assert abs(percentage - (sampling / report.total_ms * 100.0)) > 5.0


# ── 4. Remote/partial vs final reconciled artifacts ────────────────────────
def test_final_reconciled_vs_remote_partial():
    """A result missing the submission boundary and the Modal restore-begin
    boundary renders as a REMOTE/PARTIAL waterfall; the full final artifact is
    complete and the new fields round-trip through waterfall_to_dict."""
    partial = build_real_run_result(boundaries=False, restore_begin=False)
    partial_report = _report(partial)
    assert partial_report.partial_waterfall is True
    assert "missing_submission" in partial_report.partial_flags
    assert "missing_modal_restore_begin" in partial_report.partial_flags

    partial_render = render_waterfall(partial_report, terminal_columns=132)
    assert "V2 COLD WATERFALL - REMOTE/PARTIAL (awaiting host reconciliation)" in partial_render
    assert "PENDING_HOST_RECONCILIATION" in partial_render
    # Partial renders a REAL boxed table of the remotely-measured stages: same
    # geometry as the reconciled table, but no percentages, no '#' bars and no
    # scheduling values (unknown remotely; the conclusive footer lines carry
    # the intermediate pending token and the host produces the final table).
    assert "+-----+" in partial_render
    assert "|   # | Stage" in partial_render
    assert "COMMAND -> RESPONSE:" in partial_render
    pending_footer = [
        line for line in partial_render.splitlines()
        if line.startswith("Command (without scheduling) -> Response:")
        or line.startswith("Scheduling time:")
    ]
    assert len(pending_footer) == 2
    assert all("awaiting host reconciliation" in line for line in pending_footer)
    numbered = [
        line for line in partial_render.splitlines()
        if line.startswith("| ") and line.split("|")[1].strip().isdigit()
    ]
    assert numbered, "expected numbered stage rows in the partial table"
    for line in numbered:
        parts = line.split("|")
        assert parts[3].strip() != "-", line   # duration present
        assert parts[4].strip() != "-", line   # cumulative present
        assert parts[5].strip() == "-", line   # '%' column renders '-' (never a number)
        assert parts[6].strip() == "", line    # bar column blank
        assert "#" not in line and "%" not in line, line
    assert partial_render.count("#") == 1  # only the '#' column-header label
    # Boxed footer rows inside the table, then the closing border.  No boxed
    # SCHEDULING row: the scheduling window is summarized in the conclusive
    # lines below.
    assert "|     | SCHEDULING" not in partial_render
    assert "|     | RECONCILIATION" in partial_render
    assert "|     | STATUS" in partial_render

    final = build_real_run_result()
    final_report = _report(final, run_label="remote normal run")
    assert final_report.partial_waterfall is False
    assert final_report.partial_flags == ()
    final_render = render_waterfall(final_report, terminal_columns=132)
    assert "REMOTE/PARTIAL" not in final_render
    # Both tables share byte-identical border rules so container logs align.
    partial_rules = [line for line in partial_render.splitlines() if line.startswith("+-----+")]
    final_rules = [line for line in final_render.splitlines() if line.startswith("+-----+")]
    assert partial_rules and final_rules
    assert partial_rules[0] == final_rules[0]
    assert len(partial_rules) == len(final_rules)

    # waterfall_to_dict round-trips the new fields.
    data = waterfall_to_dict(final_report)
    assert data["scheduling_ms"] == final_report.scheduling_ms
    assert data["total_wall_ms"] == final_report.total_wall_ms
    assert data["command_response_ms"] == final_report.command_response_ms
    assert data["partial_waterfall"] is False
    assert data["partial_flags"] == []
    # The serialized dict re-parses and re-renders (frontend contract).
    assert "V2 COLD WATERFALL" in render_waterfall(data)


# ── 5. Extreme values still reconcile ──────────────────────────────────────
def test_extreme_values_still_reconcile():
    """scheduling 300 s, pre-Python 20 s and restore 5 s still tile the wall:
    accounted == the non-scheduling wall within 25 ms, status OK,
    total_wall (internal) == total - placement."""
    scheduling, pre_python, restore = 300000.0, 20000.0, 5000.0
    total = chain_total_ms(
        scheduling_ms=scheduling, pre_python_ms=pre_python, restore_ms=restore
    )
    result = build_real_run_result(
        scheduling_ms=scheduling, pre_python_ms=pre_python, restore_ms=restore
    )
    report = _report(result, total_ms=total)

    assert report.reconciliation_status == "OK"
    assert report.scheduling_ms == pytest.approx(scheduling)
    assert report.total_wall_ms == pytest.approx(report.total_ms - scheduling)
    assert report.accounted_ms is not None
    assert report.non_scheduling_ms is not None
    assert abs(report.accounted_ms - report.non_scheduling_ms) <= 25.0


# ── 6. Missing local receipt flags the partial waterfall ──────────────────
def test_missing_local_receipt_flags_partial():
    """Deleting the local final_result_received / local_result_received events
    from an otherwise-complete artifact flags missing_local_result_receipt."""
    result = build_real_run_result()
    result["trace"]["events"] = [
        event
        for event in result["trace"]["events"]
        if not (
            event.get("process") == "local"
            and event.get("name") in ("final_result_received", "local_result_received")
        )
    ]
    report = _report(result)
    assert report.partial_waterfall is True
    assert "missing_local_result_receipt" in report.partial_flags
    # The other boundaries are still present.
    assert "missing_submission" not in report.partial_flags
    assert "missing_modal_restore_begin" not in report.partial_flags
