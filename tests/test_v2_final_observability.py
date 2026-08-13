"""Final observability verification suite for the V2 waterfall + restore arm.

Covers the 29 mandated scenarios against the REAL implementation functions in
``comfymodal_runtime.v2_waterfall`` (``build_waterfall`` / ``render_waterfall``
/ ``waterfall_to_dict``) and ``comfymodal_runtime.restore_memory_arm``, using
the shared real-run reconstruction fixture
(``tests/v2_waterfall_reconciliation_fixtures.py``) in the same style as
``tests/test_waterfall_reconciliation.py``:

  - Waterfall accounting (11): REMOTE/PARTIAL rendering, scheduling-row
    invariants, residual-is-footer-metadata-not-a-stage, the TOTAL WALL
    percentage denominator, child/overlap accounting isolation, exclusive
    top-level reconciliation to TOTAL WALL, and pre-Python interval
    classification.
  - UNET diagnostics (4): active-read vs H2D span distinction, the
    ``overlap_diagnostic`` fallback path, bind/construction validity.
  - Output (5): remote yield, local receipt, caller return, deferred
    persistence exclusion, missing/negative boundary rendering.
  - Presentation (4): node-row filtering bounds, strategic-node retention,
    full-data artifact preservation.
  - Restore memory arm (5): frozen-path resolution + runtime env, construction
    write, consume / no-file fallback / corrupt / env-off semantics.
"""

from __future__ import annotations

import json
import os
import re

import pytest

from comfymodal_runtime.v2_waterfall import (
    DERIVED,
    INVALID,
    MEASURED,
    UNAVAILABLE,
    build_waterfall,
    render_waterfall,
    waterfall_to_dict,
)
from tests.v2_waterfall_reconciliation_fixtures import (
    LOCAL_RETURN_MS,
    build_real_run_result,
    command_start_ms,
    response_ns_for,
)

CMD_START = command_start_ms()

_STAGE_ROW_RE = re.compile(r"^\s+\d+\s+\| ")


def _report(result, total_ms=None, **kwargs):
    return build_waterfall(
        result=result,
        timing={},
        wall_ms=None,
        command_start_unix_ms=CMD_START,
        response_received_unix_ns=response_ns_for(
            total_ms if total_ms is not None else result["wall_ms"]
        ),
        **kwargs,
    )


def _stages(report):
    return {stage.key: stage for stage in report.stages}


def _details(report):
    return {detail.key: detail for detail in report.details}


def _partial_report(**overrides):
    """A REMOTE/PARTIAL waterfall (no submission / restore-begin boundaries)."""
    result = {"trace": {"events": []}}
    result.update(overrides)
    return build_waterfall(
        result=result,
        timing={},
        wall_ms=None,
        command_start_unix_ms=1000,
        response_received_unix_ns=13000 * 1_000_000,
    )


def _stage_rows(rendered):
    """Numbered main-table rows (only ``accounting_role == "top_level"``)."""
    return [line for line in rendered.splitlines() if _STAGE_ROW_RE.match(line)]


def _scheduling_row(rendered):
    for line in rendered.splitlines():
        if "Modal scheduling" in line and "|" in line:
            return line
    raise AssertionError("Modal scheduling row not found in render")


def _reset_restore_arm_logs(rma):
    rma._FREEZE_LOGGED = False
    rma._APPLY_FALLBACK_LOGGED = False
    rma._APPLY_FROZEN_LOGGED = False


# ═══════════════════════════════════════════════════════════════════════════
# Waterfall accounting (11)
# ═══════════════════════════════════════════════════════════════════════════


def test_01_remote_partial_stage_rows_have_no_percentage():
    """REMOTE/PARTIAL (total_wall unknown): every stage row renders '%' as '-'."""
    report = _partial_report()
    assert report.partial_waterfall is True
    assert report.total_wall_ms is None
    rendered = render_waterfall(report, terminal_columns=132)
    rows = _stage_rows(rendered)
    assert len(rows) == len([s for s in report.stages if s.accounting_role == "top_level"])
    for row in rows:
        parts = [part.strip() for part in row.split("|")]
        assert "%" not in row, row
        assert parts[4] == "-", row  # percentage column is '-', never a number


def test_02_remote_partial_unresolved_platform_interval_has_no_bar():
    """REMOTE/PARTIAL: the scheduling / pre-Python rows carry no '#/'=' bar."""
    report = _partial_report()
    rendered = render_waterfall(report, terminal_columns=132)
    for row in _stage_rows(rendered):
        parts = [part.strip() for part in row.split("|")]
        assert parts[5] == "", row  # bar region blank
        assert "#" not in row and "=" not in row, row
    # The fused unresolved platform row is explicitly flagged and the
    # awaiting-host-reconciliation state is visible in the title.
    sched = _scheduling_row(rendered)
    assert "Modal scheduling + pre-Python restore" in sched
    assert "awaiting host reconciliation" in rendered
    parts = [part.strip() for part in sched.split("|")]
    assert parts[5] == ""


def test_03_scheduling_row_never_has_percentage():
    """The scheduling row renders '-' in the % column in BOTH modes."""
    row_p = _scheduling_row(render_waterfall(_partial_report(), terminal_columns=132))
    parts_p = [part.strip() for part in row_p.split("|")]
    assert parts_p[4] == "-"
    full = _report(build_real_run_result())
    row_f = _scheduling_row(render_waterfall(full, terminal_columns=132))
    parts_f = [part.strip() for part in row_f.split("|")]
    assert parts_f[4] == "-"
    assert parts_f[1].startswith("Modal scheduling")


def test_04_scheduling_row_never_has_bar():
    """Even when reconciled, the scheduling row's bar region stays blank."""
    full = _report(build_real_run_result())
    assert full.total_wall_ms is not None
    rendered = render_waterfall(full, terminal_columns=132)
    row = _scheduling_row(rendered)
    parts = [part.strip() for part in row.split("|")]
    assert parts[5] == "", row
    assert "#" not in row and "=" not in row, row


def test_05_reconciliation_residual_not_a_numbered_stage():
    """Residual lives only in report fields + footer, never a numbered stage."""
    report = _report(build_real_run_result())
    assert "residual" not in {stage.key for stage in report.stages}
    assert report.residual_ms is not None
    rendered = render_waterfall(report, terminal_columns=132)
    assert "Residual (unattributed)" not in rendered
    assert "GLOBAL RESIDUAL" in rendered
    assert not any("Residual" in row for row in _stage_rows(rendered))


def test_06_reconciled_percentage_uses_total_wall_denominator():
    """With total_wall known, stage % equals duration / total_wall."""
    report = _report(build_real_run_result())
    assert report.total_wall_ms is not None and report.total_wall_ms > 0
    assert report.total_wall_ms == pytest.approx(report.total_ms - report.scheduling_ms)
    stages = _stages(report)
    for key in ("sampling", "vae", "prompt_executor_cache_setup", "output_persistence"):
        stage = stages[key]
        assert stage.duration_ms is not None
        assert stage.percentage == pytest.approx(
            stage.duration_ms / report.total_wall_ms * 100.0, abs=1e-9
        )
    # The serialized dict carries the same percentage, and the render shows it.
    data = waterfall_to_dict(report)
    sampling = stages["sampling"]
    sampling_dict = next(s for s in data["stages"] if s["key"] == "sampling")
    assert sampling_dict["percentage"] == sampling.percentage
    rendered = render_waterfall(report, terminal_columns=132)
    row = next(
        line for line in rendered.splitlines()
        if "Sampling" in line and "|" in line
    )
    assert f"{sampling.percentage:7.3f}%" in row


def test_07_child_durations_do_not_change_accounted():
    """Details are children: changing a detail duration never moves accounted_ms."""
    full = _report(build_real_run_result())
    changed = _report(build_real_run_result(missing_children=True))
    assert _details(full)["cached_to_first_node"].duration_ms == pytest.approx(227.0)
    assert _details(changed)["cached_to_first_node"].duration_ms == pytest.approx(226.0)
    assert full.total_ms == changed.total_ms
    assert full.accounted_ms == changed.accounted_ms
    assert full.residual_ms == changed.residual_ms


def test_08_overlap_diagnostic_rows_excluded_from_accounting():
    """The H2D-pair fallback read row is overlap_diagnostic and never counted."""
    result = build_real_run_result()
    result["pre_sampler_structured_report"]["active_read_records"] = []
    report = _report(result)
    details = _details(report)
    read = details["unet_checkpoint_read"]
    assert read.accounting_role == "overlap_diagnostic"
    assert read.overlaps == ("unet_synchronized_h2d",)
    assert read.label == "Checkpoint read (overlap: H2D span fallback)"
    assert read.included_in_total is False
    # Excluded from the accounted sum: the report still tiles to the wall.
    assert report.accounted_ms == pytest.approx(report.total_ms, abs=1e-6)
    assert abs(report.residual_ms) <= max(25.0, report.total_ms * 0.0025)
    # Rendered as an 'overlap' diagnostic marker, never a numbered stage row.
    rendered = render_waterfall(report, terminal_columns=132)
    assert "overlap: Checkpoint read" in rendered
    assert not any("Checkpoint read" in row for row in _stage_rows(rendered))


def test_09_exclusive_top_level_reconciles_to_total_wall():
    """Exclusive (non-concurrent, non-scheduling) top-level sum + residual
    reconciles to TOTAL WALL within tolerance."""
    report = _report(build_real_run_result())
    tolerance = max(25.0, report.total_ms * 0.0025)
    assert report.residual_ms is not None
    assert abs(report.residual_ms) <= tolerance
    exclusive = [
        stage.duration_ms
        for stage in report.stages
        if stage.accounting_role == "top_level"
        and stage.included_in_total
        and not stage.concurrent
        and stage.duration_ms is not None
        and stage.status != INVALID
    ]
    assert abs(sum(exclusive) - report.accounted_ms) < 1e-6
    # Drop the platform scheduling row: the remaining exclusive top-level wall
    # plus the residual equals TOTAL WALL (accounted+residual==total, and
    # total_wall==total-scheduling).
    exclusive_wall = sum(exclusive) - (report.scheduling_ms or 0.0)
    assert abs((exclusive_wall + report.residual_ms) - report.total_wall_ms) <= tolerance


def test_10_huge_pre_python_interval_not_generic_residual():
    """A huge unresolved pre-Python interval is footer metadata with a
    'Pending host reconciliation' line — never a 'Residual' stage or the
    generic residual."""
    report = _partial_report(command_start_to_restore_start_ms=5285.381)
    assert report.partial_waterfall is True
    assert report.pre_python_interval_ms == 5285.381
    assert report.residual_ms != 5285.381
    rendered = render_waterfall(report, terminal_columns=132)
    assert (
        "Pending host reconciliation: command start -> Python resume = 5285.381 ms"
        in rendered
    )
    assert (
        "classification = scheduling + pre-Python restore (unresolved platform interval)"
        in rendered
    )
    assert "Residual (unattributed)" not in rendered
    assert "residual" not in {stage.key for stage in report.stages}


def test_11_unresolved_pre_python_interval_classification():
    """The classification is exact while partial and suppressed when reconciled."""
    expected = "scheduling + pre-Python restore (unresolved platform interval)"
    partial = _partial_report(command_start_to_restore_start_ms=1234.5)
    assert partial.pre_python_interval_ms == 1234.5
    assert partial.pre_python_interval_classification == expected
    full = _report(build_real_run_result())
    assert full.pre_python_interval_ms is None
    assert full.pre_python_interval_classification == ""


# ═══════════════════════════════════════════════════════════════════════════
# UNET diagnostics (4)
# ═══════════════════════════════════════════════════════════════════════════


def test_12_checkpoint_read_not_h2d_by_accidental_boundary_reuse():
    """With active-read timestamps present, the checkpoint-read row equals the
    ACTIVE-READ span (1047 ms) — not a boundary-reused copy of the H2D row."""
    report = _report(build_real_run_result())
    details = _details(report)
    read = details["unet_checkpoint_read"]
    h2d = details["unet_synchronized_h2d"]
    assert read.status == MEASURED
    assert read.duration_ms == pytest.approx(1047.0)
    assert h2d.duration_ms == pytest.approx(2214.0)
    assert read.duration_ms != h2d.duration_ms
    assert read.accounting_role == "child"
    assert read.overlaps == ()


def test_13_active_read_span_distinct_from_h2d():
    """Both diagnostic rows exist and carry distinct durations."""
    report = _report(build_real_run_result())
    details = _details(report)
    read = details["unet_checkpoint_read"]
    h2d = details["unet_synchronized_h2d"]
    assert read.key == "unet_checkpoint_read"
    assert h2d.key == "unet_synchronized_h2d"
    assert read.duration_ms is not None
    assert h2d.duration_ms is not None
    assert read.duration_ms == pytest.approx(1047.0)
    assert h2d.duration_ms == pytest.approx(2214.0)


def test_14_overlapping_read_h2d_not_double_counted():
    """Without active-read timestamps the read row is a flagged overlap
    diagnostic of the H2D span; accounted is untouched by both rows."""
    result = build_real_run_result()
    result["pre_sampler_structured_report"]["active_read_records"] = []
    report = _report(result)
    details = _details(report)
    read = details["unet_checkpoint_read"]
    assert read.accounting_role == "overlap_diagnostic"
    assert read.overlaps == ("unet_synchronized_h2d",)
    h2d = details["unet_synchronized_h2d"]
    assert h2d.accounting_role == "child"
    assert h2d.duration_ms == pytest.approx(2214.0)
    assert read.duration_ms == pytest.approx(1047.0)
    overlap_sum = sum(
        (d.duration_ms or 0.0) for d in report.details
        if d.accounting_role == "overlap_diagnostic"
    )
    assert overlap_sum == pytest.approx(1047.0)
    assert report.accounted_ms == pytest.approx(report.total_ms, abs=1e-6)
    assert abs(report.residual_ms) <= max(25.0, report.total_ms * 0.0025)


def test_15_bind_and_construction_boundaries_remain_valid():
    """unet_bind is MEASURED from its own boundary pair; the construction row
    is derived from the authoritative complete-event metadata — both positive
    and never unavailable/invalid."""
    report = _report(build_real_run_result())
    details = _details(report)
    bind = details["unet_bind"]
    construction = details["unet_read_to_construction"]
    assert bind.status == MEASURED
    assert bind.duration_ms == pytest.approx(158.0)
    assert bind.duration_ms > 0
    assert construction.duration_ms == pytest.approx(271.0)
    assert construction.duration_ms > 0
    assert construction.status in (MEASURED, DERIVED)
    assert construction.status not in (UNAVAILABLE, INVALID)


# ═══════════════════════════════════════════════════════════════════════════
# Output (5)
# ═══════════════════════════════════════════════════════════════════════════


def test_16_remote_yield_handoff_boundary_present():
    """The remote yield boundary (remote_return_handoff) is a measured
    top-level row in the reconciled fixture."""
    report = _report(build_real_run_result())
    stages = _stages(report)
    handoff = stages["remote_return_handoff"]
    assert handoff.status == MEASURED
    assert handoff.duration_ms == pytest.approx(140.0)


def test_17_local_receipt_boundary_present():
    """local_receipt_to_return appears when the local receipt event AND the
    response boundary exist."""
    report = _report(build_real_run_result())
    details = _details(report)
    receipt = details["local_receipt_to_return"]
    assert receipt.status == MEASURED
    assert receipt.duration_ms is not None
    assert receipt.parent_key == "remote_local_return"
    assert receipt.included_in_total is False


def test_18_caller_return_boundary_expected_duration():
    """The row spanning local receipt -> caller return carries the fixture
    duration (LOCAL_RETURN_MS)."""
    report = _report(build_real_run_result())
    receipt = _details(report)["local_receipt_to_return"]
    assert receipt.duration_ms == pytest.approx(LOCAL_RETURN_MS)
    assert receipt.duration_ms > 0


def test_19_deferred_persistence_excluded_from_critical_path():
    """output_deferred_commit is a child (included_in_total=False) and never
    affects accounted_ms / TOTAL WALL."""
    report = _report(build_real_run_result())
    deferred = _details(report)["output_deferred_commit"]
    assert deferred.status == MEASURED
    assert deferred.duration_ms == pytest.approx(100.0)
    assert deferred.included_in_total is False
    assert deferred.accounting_role == "child"
    assert deferred.parent_key == "remote_return_handoff"
    # Critical path untouched: accounted still equals the command->response wall.
    assert report.accounted_ms == pytest.approx(report.total_ms, abs=1e-6)
    assert abs(report.residual_ms) <= max(25.0, report.total_ms * 0.0025)


def test_20_missing_optional_boundary_renders_dash_not_invalid():
    """Missing/negative child boundary pairs render '-' (UNAVAILABLE), never
    INVALID; a top-level negative interval still renders INVALID."""
    # (a) Missing child pair -> localized UNAVAILABLE.
    result = build_real_run_result()
    result["trace"]["events"] = [
        e for e in result["trace"]["events"] if not e["name"].startswith("deferred_commit")
    ]
    report = _report(result)
    deferred = _details(report)["output_deferred_commit"]
    assert deferred.status == UNAVAILABLE
    assert deferred.duration_ms is None
    assert deferred.status != INVALID
    rendered = render_waterfall(report, terminal_columns=132)
    assert "INVALID" not in rendered
    assert "Deferred persistence" in rendered  # row still listed with '-'

    # (b) Negative child pair -> downgraded to UNAVAILABLE + negative_interval.
    result_neg = build_real_run_result()
    for event in result_neg["trace"]["events"]:
        if event["name"] == "deferred_commit_end":
            event["wall_unix_ns"] = event["wall_unix_ns"] - 500_000_000
            event["monotonic_ns"] = event["monotonic_ns"] - 500_000_000
    report_neg = _report(result_neg)
    deferred_neg = _details(report_neg)["output_deferred_commit"]
    assert deferred_neg.status == UNAVAILABLE
    assert deferred_neg.duration_ms is None
    assert "negative_interval" in deferred_neg.source_fields
    assert "INVALID" not in render_waterfall(report_neg, terminal_columns=132)

    # (c) Top-level negative interval -> INVALID (never silent).
    result_top = build_real_run_result()
    sampling_start_ns = next(
        event["wall_unix_ns"]
        for event in result_top["trace"]["events"]
        if event["name"] == "sampling_start"
    )
    for event in result_top["trace"]["events"]:
        if event["name"] == "sampling_end":
            event["wall_unix_ns"] = sampling_start_ns - 500_000_000
            event["monotonic_ns"] = event["wall_unix_ns"] - 700_000_000_000
    report_top = _report(result_top)
    assert _stages(report_top)["sampling"].status == INVALID
    assert "INVALID" in render_waterfall(report_top, terminal_columns=132)


# ═══════════════════════════════════════════════════════════════════════════
# Presentation (4)
# ═══════════════════════════════════════════════════════════════════════════


def test_21_default_waterfall_node_count_bounded():
    """30 tiny non-strategic nodes contribute ZERO node rows to the render."""
    result = build_real_run_result()
    result["pre_sampler_structured_report"]["per_node_timings"] = [
        {"node_id": f"n{i}", "class_type": "CheckpointLoaderSimple", "duration_ms": 3.0}
        for i in range(30)
    ]
    report = _report(result)
    rendered = render_waterfall(report, terminal_columns=132)
    assert rendered.count("Node:") == 0
    assert len([d for d in report.details if d.source == "node_timing"]) == 0


def test_22_tiny_nodes_filtered_from_render():
    """A 3 ms non-strategic node is absent from the render output."""
    result = build_real_run_result()
    result["pre_sampler_structured_report"]["per_node_timings"] = [
        {"node_id": "n1", "class_type": "CheckpointLoaderSimple", "duration_ms": 3.0}
    ]
    report = _report(result)
    rendered = render_waterfall(report, terminal_columns=132)
    assert "Node: CheckpointLoaderSimple" not in rendered


def test_23_strategic_tiny_nodes_retained():
    """A tiny strategic node (VAEDecode / UNETLoader) IS retained even under
    the 25 ms threshold."""
    result = build_real_run_result()
    result["pre_sampler_structured_report"]["per_node_timings"] = [
        {"node_id": "n2", "class_type": "VAEDecode", "duration_ms": 5.0},
        {"node_id": "n3", "class_type": "UNETLoader", "duration_ms": 7.0},
    ]
    report = _report(result)
    rendered = render_waterfall(report, terminal_columns=132)
    assert "Node: VAEDecode" in rendered
    assert "Node: UNETLoader" in rendered


def test_24_full_per_node_timings_preserved_in_artifact():
    """The source artifact keeps ALL per_node_timings entries; only the render
    (and serialized diagnostics) filter them."""
    result = build_real_run_result()
    result["pre_sampler_structured_report"]["per_node_timings"] = (
        [
            {"node_id": f"tiny{i}", "class_type": "CheckpointLoaderSimple", "duration_ms": 3.0}
            for i in range(30)
        ]
        + [
            {"node_id": "strat", "class_type": "VAEDecode", "duration_ms": 5.0},
            {"node_id": "big1", "class_type": "LoraLoader", "duration_ms": 40.0},
            {"node_id": "big2", "class_type": "LoraLoader", "duration_ms": 30.0},
        ]
    )
    report = _report(result)
    # build_waterfall never mutates the input: all 33 entries survive.
    assert len(result["pre_sampler_structured_report"]["per_node_timings"]) == 33
    # The filtered subset (>=25ms or strategic) reaches the diagnostics ...
    node_rows = [d for d in report.details if d.source == "node_timing"]
    assert len(node_rows) == 3
    data = waterfall_to_dict(report)
    assert sum(1 for d in data["details"] if d["source"] == "node_timing") == 3
    # ... and the render.
    rendered = render_waterfall(report, terminal_columns=132)
    assert rendered.count("Node:") == 3
    for key in ("tiny0", "tiny29", "strat", "big1", "big2"):
        assert any(
            record.get("node_id") == key
            for record in result["pre_sampler_structured_report"]["per_node_timings"]
        )


# ═══════════════════════════════════════════════════════════════════════════
# Restore memory arm (5)
# ═══════════════════════════════════════════════════════════════════════════


def test_25_frozen_path_resolves_and_runtime_env_contains_root(monkeypatch, tmp_path):
    """frozen_capacity_path() resolves under COMFYMODAL_V2_STATE_VOLUME_ROOT and
    the container runtime env carries the same mounted state root."""
    import comfymodal_runtime.restore_memory_arm as rma
    from comfymodal_runtime.modal_app import RUNTIME_STATE_PATH, _runtime_env

    monkeypatch.setenv("COMFYMODAL_V2_STATE_VOLUME_ROOT", str(tmp_path))
    assert rma.frozen_capacity_path() == os.path.join(
        str(tmp_path), "gpu_capacity_frozen.json"
    )
    env = _runtime_env()
    assert env.get("COMFYMODAL_V2_STATE_VOLUME_ROOT") == RUNTIME_STATE_PATH


def test_26_construction_writes_capacity_file(monkeypatch, tmp_path, capsys):
    """maybe_freeze_snapshot_gpu_capacity parses nvidia-smi and atomically
    writes the frozen capacity file with valid total_vram_mib / gpu_name."""
    import comfymodal_runtime.restore_memory_arm as rma

    class _FakeProc:
        returncode = 0
        stdout = "49152, NVIDIA RTX PRO 6000\n"

    monkeypatch.setenv("COMFYMODAL_V2_STATE_VOLUME_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "comfymodal_runtime.restore_memory_arm.subprocess.run",
        lambda *args, **kwargs: _FakeProc(),
    )
    _reset_restore_arm_logs(rma)
    rma.maybe_freeze_snapshot_gpu_capacity()

    path = rma.frozen_capacity_path()
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["total_vram_mib"] == 49152
    assert payload["gpu_name"] == "NVIDIA RTX PRO 6000"
    assert payload["source"] == "nvidia-smi"
    out = capsys.readouterr().out
    assert "[restore_memory_arm] freeze" in out
    assert "vram_mib=49152" in out


def test_27_restore_consumes_frozen_capacity(monkeypatch, tmp_path, capsys):
    """Valid file + arm on -> apply_frozen_total_vram_or_none returns the
    frozen float and reports effective=optimized frozen_capacity_used=1."""
    import comfymodal_runtime.restore_memory_arm as rma

    monkeypatch.setenv("COMFYMODAL_V2_STATE_VOLUME_ROOT", str(tmp_path))
    monkeypatch.setenv("COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN", "1")
    path = rma.frozen_capacity_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"gpu_name": "NVIDIA RTX PRO 6000", "total_vram_mib": 49152}, f)
    _reset_restore_arm_logs(rma)
    assert rma.apply_frozen_total_vram_or_none() == 49152.0
    out = capsys.readouterr().out
    assert "[v2.restore_memory_arm] requested=optimized" in out
    assert "effective=optimized" in out
    assert "frozen_capacity_used=1" in out


def test_28_fallback_explicit_when_file_absent(monkeypatch, tmp_path, capsys):
    """Arm on + no frozen file -> None with effective=baseline
    fallback=no_frozen_capacity."""
    import comfymodal_runtime.restore_memory_arm as rma

    monkeypatch.setenv("COMFYMODAL_V2_STATE_VOLUME_ROOT", str(tmp_path))
    monkeypatch.setenv("COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN", "1")
    _reset_restore_arm_logs(rma)
    assert rma.apply_frozen_total_vram_or_none() is None
    out = capsys.readouterr().out
    assert "[v2.restore_memory_arm] requested=optimized" in out
    assert "effective=baseline" in out
    assert "fallback=no_frozen_capacity" in out


def test_29_corrupt_file_and_env_off(monkeypatch, tmp_path, capsys):
    """Corrupt file + arm on -> None with an explicit fallback line; arm off ->
    None with NO [v2.restore_memory_arm] requested line at all."""
    import comfymodal_runtime.restore_memory_arm as rma

    monkeypatch.setenv("COMFYMODAL_V2_STATE_VOLUME_ROOT", str(tmp_path))
    path = rma.frozen_capacity_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json")

    monkeypatch.setenv("COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN", "1")
    _reset_restore_arm_logs(rma)
    assert rma.apply_frozen_total_vram_or_none() is None
    out = capsys.readouterr().out
    assert "[v2.restore_memory_arm] requested=optimized" in out
    assert "effective=baseline fallback=no_frozen_capacity" in out

    monkeypatch.delenv("COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN", raising=False)
    _reset_restore_arm_logs(rma)
    assert rma.apply_frozen_total_vram_or_none() is None
    out = capsys.readouterr().out
    assert "[v2.restore_memory_arm] requested=optimized" not in out
