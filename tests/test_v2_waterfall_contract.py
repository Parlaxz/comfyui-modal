"""V2 waterfall accounting/rendering contract suite.

Implements the 18 mandated synthetic scenarios (parametrized where possible)
plus a golden exact-console-format test, against the REAL implementation in
``comfymodal_runtime.v2_waterfall`` using the shared real-run fixture
(``tests/v2_waterfall_reconciliation_fixtures.py``).

Contract under test:
  - NON-SCHEDULING wall = command->response - scheduling time
    (scheduling time = command -> enqueue + Modal placement).
  - The whole scheduling window (``local_preparation`` /
    ``modal_handle_submission`` / ``modal_scheduling``) is informational:
    never a numbered stage, never accounted/cumulative/%/bar; summarized once
    in the conclusive "Scheduling time:" footer line.
  - Top-level rows are the mutually exclusive chronological intervals; only
    ``accounting_role == "top_level"`` affects cumulative/%/bar/accounted.
    Detail / overlap_detail / informational never do.
  - Reconciliation compares the exclusive top-level sum to the non-scheduling
    wall.  No fake residual stage.  Hard acceptance <= 50 ms; the <= 10 ms
    target is a warning (never hidden), 10-50 ms never silently passes as
    perfect.
  - ONE ASCII table.  No Expanded/secondary sections.  Inline indented detail
    rows (duration only, blank number/Cum/%/bar) under their parents.
  - Minimal boxed footer: Reconciliation / Status (+ TARGET 10MS when missed),
    followed by three conclusive plain lines: COMMAND -> RESPONSE,
    Command (without scheduling) -> Response, Scheduling time.
  - Bars are '#' only, fixed 40 wide, top-level only, non-scheduling
    denominator.
  - Optional unavailable details are omitted; required missing top-level
    boundaries produce explicit flags, never fake values.
  - No H2D-as-checkpoint-read substitution: without an active-read record the
    checkpoint detail is omitted and ``checkpoint_read_unavailable`` is flagged.
  - Partial (remote) waterfalls render a REAL boxed table of the remotely-
    measured stages: no percentages ('-' column), no '#' bars, scheduling
    values pending ("awaiting host reconciliation"); the host produces the
    final reconciled table.
"""

from __future__ import annotations

import pytest

from comfymodal_runtime.v2_waterfall import (
    INVALID,
    _detail_is_useful,
    attach_waterfall,
    build_waterfall,
    render_waterfall,
    _report_from_value,
    waterfall_to_dict,
)
from tests.v2_waterfall_reconciliation_fixtures import (
    LOCAL_RETURN_MS,
    build_real_run_result,
    command_start_ms,
    response_ns_for,
)

CMD_START = command_start_ms()

GOLDEN_RENDER = """\
V2 COLD WATERFALL - run 20260812-142808
Request:   req-20260812-142808 | Instance: ri-realrun-01 | Fresh: YES
Platform:  aws/us-east-1

+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (non-scheduling)           |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Modal pre-Python snapshot restoration          |     7.330s |     7.330s |  40.466% | ################                         |
|   2 | Python/application restore                     | 549.000 ms |     7.879s |   3.031% | #                                        |
|   3 | Restore-to-method entry                        |  91.123 ms |     7.970s |   0.503% | #                                        |
|   4 | Remote method setup                            |     3.970s |    11.940s |  21.917% | #########                                |
|   5 | PromptExecutor/cache setup                     |     1.227s |    13.167s |   6.774% | ###                                      |
|     |   execution to cached                          | 999.000 ms |            |          |                                          |
|     |   cached to first node                         | 227.000 ms |            |          |                                          |
|   6 | Pre-sampler execution                          | 700.000 ms |    13.867s |   3.864% | ##                                       |
|     |   Checkpoint read                              |     1.047s |            |          |                                          |
|     |   Read end -> construction done                | 271.000 ms |            |          |                                          |
|     |   UNET get_model                               | 121.000 ms |            |          |                                          |
|     |   Bind                                         | 158.000 ms |            |          |                                          |
|     |   Synchronized H2D (5.6 GB/s)                  |     2.214s |            |          |                                          |
|     |   H2D end -> UNET ready                        |     2.650s |            |          |                                          |
|     |   UNET ready -> sampler demand                 |     2.187s |            |          |                                          |
|     |   Sampler demand -> join complete              | 230.000 ms |            |          |                                          |
|     |   Join complete -> sampling                    |  40.000 ms |            |          |                                          |
|   7 | Sampler graph-join wait                        | 230.000 ms |    14.097s |   1.270% | #                                        |
|   8 | Sampler node to sampling                       |  40.000 ms |    14.137s |   0.221% | #                                        |
|   9 | Sampling                                       |     1.767s |    15.904s |   9.753% | ####                                     |
|  10 | Post-sampling / VAE transition                 | 916.400 ms |    16.820s |   5.059% | ##                                       |
|  11 | VAE decode                                     | 388.000 ms |    17.208s |   2.142% | #                                        |
|     |   VAE load/H2D                                 | 870.900 ms |            |          |                                          |
|  12 | Output encode / descriptor                     | 596.000 ms |    17.804s |   3.290% | #                                        |
|     |   PNG encode                                   | 280.000 ms |            |          |                                          |
|     |   Descriptor/materialization                   | 316.000 ms |            |          |                                          |
|  13 | Remote result handoff                          | 140.000 ms |    17.944s |   0.773% | #                                        |
|     |   Deferred persistence after yield             | 100.000 ms |            |          |                                          |
|  14 | Local result handling / caller return          | 170.000 ms |    18.114s |   0.938% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | RECONCILIATION                                 |   0.000 ms |            |          |                                          |
|     | STATUS                                         |         OK |            |          |                                          |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
COMMAND -> RESPONSE:                     21.994s
Command (without scheduling) -> Response:   18.114s
Scheduling time:                          3.880s
"""


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


def _numbered_rows(rendered):
    """Rows with a numbered first column (the top-level table rows)."""
    return [
        line for line in rendered.splitlines()
        if line.startswith("| ") and line.split("|")[1].strip().isdigit()
    ]


def _inline_detail_rows(rendered):
    """Indented inline detail rows: blank number column, 2-space indented
    label (excludes the full-width footer rows, which have no indent)."""
    rows = []
    for line in rendered.splitlines():
        if not line.startswith("| "):
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        if parts[1].strip() == "" and parts[2].startswith("  "):
            rows.append(line)
    return rows


def _reconciled_fixture():
    return _report(build_real_run_result())


def _local_prep_missing_report():
    """Remove the local-preparation boundaries only -> a ~1 ms unaccounted gap.

    ``local_receive_to_actual_submission_ms`` keeps the submission span
    accounted (derived), so only local_preparation's 1 ms is excluded.
    """
    result = build_real_run_result()
    result["trace"]["events"] = [
        e for e in result["trace"]["events"]
        if e["name"] not in ("worker_start", "transport_entry", "modal_handle_lookup_start")
    ]
    origin = result["trace"]["metadata"]["request_origin_info"]
    for key in ("ui_run_triggered_wall_unix_ms", "local_receive_wall_ns", "local_receive_mono_ns"):
        origin.pop(key, None)
    result["local_timing"] = {"local_receive_to_actual_submission_ms": 19.0}
    return _report(result)


def _sampler_node_missing_report():
    """Remove the sampler lane-wait boundary -> a ~40 ms gap (10-50 band)."""
    result = build_real_run_result()
    result["trace"]["events"] = [
        e for e in result["trace"]["events"]
        if e["name"] != "sampler_lane_wait_start"
    ]
    return _report(result)


def _cache_setup_missing_report():
    """Remove the prompt-executor boundaries -> a large (>50 ms) gap."""
    result = build_real_run_result()
    result["trace"]["events"] = [
        e for e in result["trace"]["events"]
        if e["name"] not in ("prompt_executor_invoke_start", "graph_first_node")
    ]
    return _report(result)


def _ascii(label):
    return label.encode("ascii", "replace").decode("ascii")


# ── 1. One ASCII table only ────────────────────────────────────────────────
def test_render_is_one_table_only():
    report = _reconciled_fixture()
    rendered = render_waterfall(report, terminal_columns=132)
    assert "V2 COLD WATERFALL" in rendered
    assert "Expanded diagnostics" not in rendered
    assert "detail:" not in rendered
    assert rendered.count("V2 COLD WATERFALL") == 1


# ── 2. Scheduling absent from the table ────────────────────────────────────
def test_scheduling_informational_not_in_table_accounting_cum_pct_bar():
    report = _reconciled_fixture()
    rendered = render_waterfall(report, terminal_columns=132)
    assert not any("Modal scheduling" in line for line in _numbered_rows(rendered))
    scheduling = next(s for s in report.stages if s.key == "modal_scheduling")
    assert scheduling.accounting_role == "informational"
    assert scheduling.included_in_total is False
    assert scheduling.percentage is None
    assert scheduling.cumulative_ms is None
    # NON-SCHEDULING wall = command->response - scheduling time (enqueue +
    # placement), and accounted == the non-scheduling wall.
    assert report.non_scheduling_ms is not None
    assert report.non_scheduling_ms == pytest.approx(
        report.total_ms - report.scheduling_time_ms
    )
    assert report.accounted_ms == pytest.approx(report.non_scheduling_ms, abs=1e-6)


# ── 3. Scheduling shown exactly once in the footer ─────────────────────────
def test_scheduling_shown_exactly_once_in_footer():
    """The scheduling window is NOT a boxed footer row anymore: it is
    summarized exactly once in the conclusive 'Scheduling time:' line."""
    report = _reconciled_fixture()
    rendered = render_waterfall(report, terminal_columns=132)
    footer_rows = [line for line in rendered.splitlines() if "| SCHEDULING" in line]
    assert len(footer_rows) == 0
    scheduling_lines = [
        line for line in rendered.splitlines() if line.startswith("Scheduling time:")
    ]
    assert len(scheduling_lines) == 1
    assert "%" not in scheduling_lines[0]
    assert "#" not in scheduling_lines[0]


# ── 4. Exclusive top-level sum == NON-SCHEDULING wall ───────────────────────
def test_exclusive_top_level_sum_equals_total_wall():
    report = _reconciled_fixture()
    exclusive = sum(
        s.duration_ms for s in report.stages
        if s.accounting_role == "top_level"
        and not s.concurrent
        and s.duration_ms is not None
        and s.status != INVALID
    )
    assert exclusive == pytest.approx(report.accounted_ms, abs=1e-6)
    assert report.non_scheduling_ms is not None
    assert exclusive == pytest.approx(report.non_scheduling_ms, abs=0.02)


# ── 5. Accounted never exceeds the non-scheduling wall ─────────────────────
def test_accounted_never_exceeds_total_wall():
    report = _reconciled_fixture()
    assert report.accounted_ms is not None
    assert report.non_scheduling_ms is not None
    assert report.accounted_ms <= report.non_scheduling_ms + 1e-6
    assert report.reconciliation_ms == pytest.approx(report.non_scheduling_ms - report.accounted_ms)


# ── 6. Details never alter accounting ──────────────────────────────────────
def test_details_never_alter_accounting():
    plain = _reconciled_fixture()
    changed = _report(build_real_run_result(missing_children=True))
    assert _details(plain)["cached_to_first_node"].duration_ms == pytest.approx(227.0)
    assert _details(changed)["cached_to_first_node"].duration_ms == pytest.approx(226.0)
    assert plain.accounted_ms == changed.accounted_ms
    assert plain.total_wall_ms == changed.total_wall_ms


# ── 7. No H2D substitution for the checkpoint read ─────────────────────────
def test_no_h2d_substitution_when_active_read_missing():
    result = build_real_run_result()
    result["pre_sampler_structured_report"]["active_read_records"] = []
    report = _report(result)
    assert "unet_checkpoint_read" not in _details(report)
    assert "checkpoint_read_unavailable" in report.data_flags
    # H2D stays independent (metadata-derived), never reused as the read.
    h2d = _details(report)["unet_synchronized_h2d"]
    assert h2d.duration_ms == pytest.approx(2214.0)
    assert report.accounted_ms == pytest.approx(report.non_scheduling_ms, abs=1e-6)


# ── 8. Small gap inside the scheduling window is OK ─────────────────────────
def test_1ms_reconciliation_is_ok():
    """Removing the local-preparation boundaries leaves a ~1 ms gap that now
    sits INSIDE the informational scheduling window (the whole enqueue window
    is excluded from accounted), so this scenario reconciles to ~0 and status
    stays OK.  A genuine small non-scheduling gap (10-50 ms) is still surfaced
    as a warning while remaining OK under the hard ceiling."""
    report = _local_prep_missing_report()
    assert report.non_scheduling_ms is not None
    assert report.reconciliation_ms == pytest.approx(0.0, abs=1e-6)
    assert report.reconciliation_status == "OK"
    assert not any("exceeds" in w for w in report.warnings)
    mid = _sampler_node_missing_report()  # ~40 ms non-scheduling gap
    assert mid.reconciliation_status == "OK"
    assert any("exceeds" in w for w in mid.warnings)


# ── 9. 100+ ms reconciliation fails hard ───────────────────────────────────
def test_100ms_reconciliation_fails():
    report = _cache_setup_missing_report()
    assert report.reconciliation_status == "EXCEEDS_TOLERANCE"
    assert report.reconciliation_hard_ms == 50.0
    assert abs(report.reconciliation_ms) > 50.0
    assert any("reconciliation exceeds tolerance" in w for w in report.warnings)


# ── 10. Output transport / local handling stages ───────────────────────────
def test_output_transport_local_stages_present():
    report = _reconciled_fixture()
    stages = _stages(report)
    assert stages["remote_return_handoff"].duration_ms == pytest.approx(140.0)
    # Local result handling / caller return = local receipt -> caller return.
    assert stages["remote_local_return"].duration_ms == pytest.approx(LOCAL_RETURN_MS)
    details = _details(report)
    assert details["output_png_encode"].duration_ms == pytest.approx(280.0)
    assert details["output_descriptor"].duration_ms == pytest.approx(316.0)
    assert stages["vae"].duration_ms == pytest.approx(388.0)


# ── 11. No INVALID / residual aggregates in the console ────────────────────
def test_no_invalid_global_residual_residual_pct_in_console():
    report = _reconciled_fixture()
    rendered = render_waterfall(report, terminal_columns=132)
    assert "INVALID" not in rendered
    assert "GLOBAL RESIDUAL" not in rendered
    assert "RESIDUAL %" not in rendered
    assert "TOP-LEVEL ACCOUNTED" not in rendered
    assert "CONTROLLABLE" not in rendered
    assert "PLATFORM" not in rendered


# ── 12. Unavailable optional details omitted from the render ───────────────
def test_unavailable_optional_details_omitted_from_render():
    result = build_real_run_result()
    result["trace"]["events"] = [
        e for e in result["trace"]["events"]
        if not e["name"].startswith(("output_", "deferred_commit", "remote_"))
    ]
    report = _report(result)
    # Removing the output/return events makes many optional details
    # unavailable/invalid — but they never leak into the console.
    unavailable = [
        d for d in report.details
        if d.duration_ms is None or d.status in ("unavailable", "invalid")
    ]
    assert unavailable, "expected some unavailable optional details"
    rendered = render_waterfall(report, terminal_columns=132)
    inline_rows = _inline_detail_rows(rendered)
    for detail in unavailable:
        label = _ascii(detail.label)
        assert not any(label in row for row in inline_rows), (
            f"unavailable detail {label!r} leaked into the console"
        )
    # Every inline detail row carries a duration (no blank/useless rows).
    for row in inline_rows:
        parts = [part.strip() for part in row.split("|")]
        assert parts[3] not in ("", "-"), row  # duration present
        assert parts[4] == "" and parts[5] == "", row  # Cum/% blank
        assert parts[6] == "", row  # bar blank


# ── 13. Partial render is a real table without bars/percentages/wall ───────
def test_partial_render_is_real_table_without_bars_percent_wall():
    report = build_waterfall(
        result={"trace": {"events": []}}, timing={}, wall_ms=None,
        command_start_unix_ms=1000, response_received_unix_ns=13000 * 1_000_000,
    )
    assert report.partial_waterfall is True
    rendered = render_waterfall(report, terminal_columns=132)
    assert rendered.count("\n") > 0  # a real multi-line table, not a status line
    assert "REMOTE/PARTIAL" in rendered
    assert "PENDING_HOST_RECONCILIATION" in rendered
    assert "missing=" in rendered
    assert "+-----+" in rendered
    assert "|   # | Stage" in rendered
    # No fake TOTAL WALL number; scheduling values are pending remotely and
    # render the intermediate diagnostic token on the conclusive footer lines.
    assert "TOTAL WALL" not in rendered
    pending_footer = [
        line for line in rendered.splitlines()
        if line.startswith("Command (without scheduling) -> Response:")
        or line.startswith("Scheduling time:")
    ]
    assert len(pending_footer) == 2
    assert all("awaiting host reconciliation" in line for line in pending_footer)
    assert "COMMAND -> RESPONSE:" in rendered  # remote can measure its own window
    assert "|     | SCHEDULING" not in rendered
    assert "|     | RECONCILIATION" in rendered
    assert "|     | STATUS" in rendered
    reconciliation_footer = next(
        line for line in rendered.splitlines() if "| RECONCILIATION" in line
    )
    assert reconciliation_footer.split("|")[3].strip() == "-"
    status_footer = next(
        line for line in rendered.splitlines() if "| STATUS" in line
    )
    # The short 'PENDING' token fits the footer cell; the full token lives on
    # a post-table plain line so it never overflows the boxed border.
    assert status_footer.split("|")[3].strip() == "PENDING"
    assert "status=PENDING_HOST_RECONCILIATION" in rendered
    # The only '#' is the column-header label; no bars anywhere.
    assert rendered.count("#") == 1
    # The '%' column exists but no percentage number appears in any row.
    assert "%" in rendered
    for line in rendered.splitlines():
        if not line.startswith("| ") or line.split("|")[2].strip() == "Stage":
            continue
        assert "%" not in line, line


# ── 14. Bars are '#' only, 40 wide, top-level only, non-scheduling denominator ─
def test_bars_hash_only_fixed_width_top_level_tw_denominator():
    report = _reconciled_fixture()
    rendered = render_waterfall(report, terminal_columns=132)
    tw = report.non_scheduling_ms
    assert tw is not None and tw > 0
    for line in _numbered_rows(rendered):
        parts = line.split("|")
        # parts: ["", " n ", " label ", " dur ", " cum ", " pct ", " bar ", ""]
        bar = parts[6][1:-1]  # drop the 1-space padding around the 40-char bar
        assert len(bar) == 40, line
        assert set(bar) <= {"#", " "}, line
        # Duration present -> bar length matches duration/non-scheduling*40.
        assert parts[3].strip() != "-"
        label = parts[2].strip()
        stage = next(
            s for s in report.stages
            if s.label == label or ("~ " + s.label) == label
        )
        expected_units = max(1, round(stage.duration_ms / tw * 40))
        assert bar.count("#") == expected_units, line


# ── 15. Detail rows are duration-only (blank number/Cum/%/bar) ─────────────
def test_detail_rows_duration_only_blank_cum_pct_bar_number():
    report = _reconciled_fixture()
    rendered = render_waterfall(report, terminal_columns=132)
    inline = _inline_detail_rows(rendered)
    assert inline, "expected inline detail rows"
    for row in inline:
        parts = [part.strip() for part in row.split("|")]
        assert parts[1] == "", row  # blank number
        assert parts[3] not in ("", "-"), row  # duration present
        assert parts[4] == "" and parts[5] == "" and parts[6] == "", row


# ── 16. Inline details grouped under their parent rows ─────────────────────
def test_inline_details_grouped_under_parents():
    report = _reconciled_fixture()
    rendered = render_waterfall(report, terminal_columns=132)
    lines = rendered.splitlines()
    # Every inline detail row follows its parent stage row.
    parents = {s.key: s.label for s in report.stages}
    parent_indices = {}
    for index, line in enumerate(lines):
        if not line.startswith("| "):
            continue
        parts = line.split("|")
        if not parts[1].strip().isdigit():
            continue
        label_part = parts[2].strip()
        for key, label in parents.items():
            if key == "modal_scheduling":
                continue
            if label_part == label or label_part == "~ " + label:
                parent_indices[key] = index
    for detail in report.details:
        if not _detail_is_useful(detail):
            continue
        parent = detail.parent_key
        assert parent in parent_indices, f"parent {parent!r} not in table"
        # Find the detail's rendered row (ASCII label, like the console) and
        # confirm it comes after the parent row.
        detail_line = next(
            (i for i, line in enumerate(lines)
             if line.startswith("| ") and line.split("|")[1].strip() == ""
             and _ascii(detail.label) in line),
            None,
        )
        assert detail_line is not None, f"detail {detail.key!r} not rendered"
        assert detail_line > parent_indices[parent], (
            f"detail {detail.key!r} rendered before its parent {parent!r}"
        )


# ── 17. Minimal footer only ────────────────────────────────────────────────
def test_footer_minimal_scheduling_reconciliation_status():
    report = _reconciled_fixture()
    rendered = render_waterfall(report, terminal_columns=132)
    # Boxed footer rows are the full-width rows with a blank number column and
    # a NON-indented Stage label (RECONCILIATION/STATUS), unlike the indented
    # detail rows (2-space indent) and numbered stage rows.  No boxed
    # SCHEDULING row: the scheduling window is summarized once in the
    # conclusive "Scheduling time:" line.
    footer_labels = [
        line for line in rendered.splitlines()
        if line.startswith("| ")
        and line.split("|")[1].strip() == ""
        and line.split("|")[2].strip()
        and not line.split("|")[2].startswith("  ")
    ]
    assert len(footer_labels) == 2
    assert not any("SCHEDULING" in line for line in footer_labels)
    assert any("RECONCILIATION" in line for line in footer_labels)
    assert any("STATUS" in line for line in footer_labels)
    assert not any("ACCOUNTED" in line for line in footer_labels)
    assert not any("RESIDUAL" in line for line in footer_labels)
    assert not any("WALL" in line for line in footer_labels)
    scheduling_lines = [
        line for line in rendered.splitlines() if line.startswith("Scheduling time:")
    ]
    assert len(scheduling_lines) == 1


# ── 18. Reconciliation status thresholds (parametrized) ────────────────────
@pytest.mark.parametrize(
    "make_report, expected_status, expect_warning",
    [
        (_reconciled_fixture, "OK", False),                    # ~0 ms gap
        (_local_prep_missing_report, "OK", False),             # 1 ms gap
        (_sampler_node_missing_report, "OK", True),            # 40 ms (10-50 band)
        (_cache_setup_missing_report, "EXCEEDS_TOLERANCE", True),  # > 50 ms
    ],
)
def test_reconciliation_status_thresholds(make_report, expected_status, expect_warning):
    report = make_report()
    assert report.reconciliation_status == expected_status
    has_exceeds = any("exceeds" in w for w in report.warnings)
    assert has_exceeds is expect_warning


# ── 19. Serialized artifact stays exhaustive ───────────────────────────────
def test_serialized_artifact_exhaustive():
    report = _reconciled_fixture()
    data = waterfall_to_dict(report)
    for key in (
        "residual_ms", "residual_pct", "controllable_wall_ms", "platform_wall_ms",
        "boundary_flags", "partial_waterfall", "partial_flags",
        "pre_python_interval_ms", "pre_python_interval_classification",
        "data_flags", "reconciliation_target_ms", "reconciliation_hard_ms",
    ):
        assert key in data, key
    # The console hides aggregates but the artifact preserves every detail row
    # (including unavailable ones) and every stage's accounting_role.
    assert len(data["details"]) == len(report.details)
    assert all("accounting_role" in s for s in data["stages"])
    assert data["reconciliation_target_ms"] == 10.0
    assert data["reconciliation_hard_ms"] == 50.0
    assert data["diagnostic_status"] == report.diagnostic_status


def test_legacy_validation_status_is_tolerated_on_parse():
    report = _reconciled_fixture()
    legacy = waterfall_to_dict(report)
    legacy["validation_status"] = legacy.pop("diagnostic_status")
    parsed = _report_from_value(legacy)
    assert parsed.diagnostic_status == report.diagnostic_status
    assert "validation_status" not in waterfall_to_dict(parsed)


# ── 20. Golden exact console format ────────────────────────────────────────
def test_golden_console_format_exact():
    result = build_real_run_result()
    # Show the required UNET get_model independently and the H2D throughput
    # from exact byte metadata (real producers emit these).
    for event in result["trace"]["events"]:
        if event["name"] == "unet_fast_disk_complete":
            event["metadata"]["get_model_ms"] = 121.0
            event["metadata"]["parameter_bytes"] = 12_310_000_000
    report = _report(result, run_label="run 20260812-142808")
    rendered = render_waterfall(report, terminal_columns=132)
    assert rendered == GOLDEN_RENDER.rstrip("\n"), (
        "\n--- actual ---\n" + rendered + "\n--- expected ---\n" + GOLDEN_RENDER
    )
    # ── Golden visual contract ─────────────────────────────────────────────
    # Compact header: Platform (cloud/region) present, request/instance kept,
    # Fresh YES, and the three conclusive footer lines at the very bottom.
    assert "Platform:  aws/us-east-1" in rendered
    assert "Request:   req-20260812-142808" in rendered
    assert "Instance: ri-realrun-01" in rendered
    assert "Fresh: YES" in rendered
    assert "COMMAND -> RESPONSE:" in rendered
    assert "Command (without scheduling) -> Response:" in rendered
    assert "Scheduling time:" in rendered
    assert "TOTAL WALL" not in rendered
    # One boxed table, no Expanded/secondary sections.
    assert rendered.startswith("V2 COLD WATERFALL")
    assert "+-----+" in rendered
    assert "|   # | Stage" in rendered
    assert "Expanded diagnostics" not in rendered
    assert "detail:" not in rendered
    # The boxed footer (Reconciliation/Status, closed by a border identical to
    # the opening rule) is followed by the three conclusive plain lines — the
    # final lines of the render.
    footer_tail = rendered.rstrip().splitlines()
    assert footer_tail[-1].startswith("Scheduling time:")
    assert footer_tail[-2].startswith("Command (without scheduling) -> Response:")
    assert footer_tail[-3].startswith("COMMAND -> RESPONSE:")
    assert "|     | SCHEDULING" not in rendered
    assert "|     | RECONCILIATION" in rendered
    assert "|     | STATUS" in rendered
    # Mixed ms/s formatting: sub-second values print ms, seconds stay seconds.
    assert "|   1 | Modal pre-Python snapshot restoration" in rendered
    assert "999.000 ms" in rendered
    assert "|     | RECONCILIATION" in rendered and "0.000 ms" in rendered
    assert "7.330s" in rendered and "2.214s" in rendered
    # H2D throughput shown compactly on the H2D detail label.
    assert "Synchronized H2D (5.6 GB/s)" in rendered
    # Requested readable stage labels.
    assert "Pre-sampler execution" in rendered
    assert "Post-sampling / VAE transition" in rendered
    assert "VAE decode" in rendered
    assert "Output encode / descriptor" in rendered
    assert "Remote result handoff" in rendered
    assert "Local result handling / caller return" in rendered
    # Pre-sampler consolidation: no redundant split rows.
    assert "First node to CLIP" not in rendered
    assert "CLIP to sampler node" not in rendered
    # Required curated UNET details present; sub-ms clutter absent.
    assert "UNET get_model" in rendered
    assert "Read end -> construction done" in rendered
    assert "runtime configuration" not in rendered
    assert "legacy runtime resolution" not in rendered


# ═══════════════════════════════════════════════════════════════════════════
# Pre-deployment audit blockers
# ═══════════════════════════════════════════════════════════════════════════


# ── Host final rebuild: a remote partial is never the final report ─────────
def test_host_rebuild_replaces_remote_partial():
    """attach_waterfall with replace_partial=True rebuilds over a serialized
    REMOTE partial artifact; without it the partial is preserved."""
    partial_result = build_real_run_result(boundaries=False, restore_begin=False)
    remote_partial = waterfall_to_dict(build_waterfall(
        result=partial_result, timing={}, wall_ms=None,
        command_start_unix_ms=CMD_START,
        response_received_unix_ns=response_ns_for(partial_result["wall_ms"]),
    ))
    assert remote_partial["partial_waterfall"] is True

    # Final host result carries ALL boundaries; the host rebuild replaces the
    # remote raw partial and renders one full table.
    full_result = build_real_run_result()
    full_result["waterfall"] = remote_partial
    attach_waterfall(
        full_result,
        timing={}, wall_ms=None,
        command_start_unix_ms=CMD_START,
        response_received_unix_ns=response_ns_for(full_result["wall_ms"]),
        run_label="host rebuilt",
        modal_restore_begin_wall_unix_ns=full_result["modal_restore_begin_wall_unix_ns"],
        replace_partial=True,
        print_render=False,
    )
    rebuilt = full_result["waterfall"]
    assert rebuilt is not remote_partial
    assert rebuilt["partial_waterfall"] is False
    rendered = render_waterfall(rebuilt, terminal_columns=132)
    assert "REMOTE/PARTIAL" not in rendered
    assert "V2 COLD WATERFALL" in rendered
    assert "|" in rendered  # one full table, not a status line

    # Without replace_partial the generic preserve-first behavior keeps it.
    preserved = build_real_run_result()
    preserved["waterfall"] = remote_partial
    attach_waterfall(
        preserved, timing={}, wall_ms=None,
        command_start_unix_ms=CMD_START,
        response_received_unix_ns=response_ns_for(preserved["wall_ms"]),
        print_render=False,
    )
    assert preserved["waterfall"] is remote_partial


def test_reconcile_waterfall_local_sets_full_report_and_replaces_partial():
    """The host benchmark rebuild stores waterfall_local (full) and replaces a
    remote partial in ``result["waterfall"]``."""
    from tools.benchmark_v2_direct import reconcile_waterfall_local  # lazy: heavy module

    partial_result = build_real_run_result(boundaries=False, restore_begin=False)
    remote_partial = waterfall_to_dict(build_waterfall(
        result=partial_result, timing={}, wall_ms=None,
        command_start_unix_ms=CMD_START,
        response_received_unix_ns=response_ns_for(partial_result["wall_ms"]),
    ))
    assert remote_partial["partial_waterfall"] is True

    full_result = build_real_run_result()
    full_result["waterfall"] = remote_partial
    rebuilt = reconcile_waterfall_local(
        full_result,
        {},
        command_start_unix_ms=CMD_START,
        response_received_unix_ns=response_ns_for(full_result["wall_ms"]),
        wall_ms=None,
        run_label="host reconcile",
        existing_waterfall=remote_partial,
    )
    assert rebuilt is not None
    assert full_result["waterfall_local"] == rebuilt
    assert rebuilt["partial_waterfall"] is False
    # The remote partial was replaced by the full host-reconciled report.
    assert full_result["waterfall"] == rebuilt
    rendered = render_waterfall(rebuilt, terminal_columns=132)
    assert "REMOTE/PARTIAL" not in rendered
    assert "|" in rendered


# ── Direct output-return boundaries ────────────────────────────────────────
def test_direct_output_return_boundaries_accounted():
    """Output ends at direct completion; handoff = remote emit -> local
    receipt; caller return = local receipt -> execute_plan_return.  All
    intervals account into the non-scheduling wall and stay chronological."""
    result = build_real_run_result()
    events = result["trace"]["events"]
    persist = next(e for e in events if e["name"] == "output_persist_end")
    emit = dict(persist)
    emit["name"] = "remote_result_emit"
    emit["wall_unix_ns"] = emit["wall_unix_ns"] + 3_000_000
    emit["monotonic_ns"] = emit["monotonic_ns"] + 3_000_000
    receipt = next(e for e in events if e["name"] == "local_result_received")
    ret = dict(receipt)
    ret["name"] = "execute_plan_return"
    ret["wall_unix_ns"] = ret["wall_unix_ns"] + 5_000_000
    ret["monotonic_ns"] = ret["monotonic_ns"] + 5_000_000
    events.append(emit)
    events.append(ret)

    report = _report(result)
    stages = _stages(report)
    # Output encode/descriptor ends at the direct completion (emit).
    assert stages["output_persistence"].status == "measured"
    assert stages["output_persistence"].duration_ms == pytest.approx(599.0, abs=1e-6)
    # Remote result handoff = remote emit -> local receipt (140 - 3).
    assert stages["remote_return_handoff"].status == "measured"
    assert stages["remote_return_handoff"].duration_ms == pytest.approx(137.0, abs=1e-6)
    # Local result handling / caller return = receipt -> execute_plan_return.
    assert stages["remote_local_return"].duration_ms == pytest.approx(5.0, abs=1e-6)
    # Never remote pre-yield build time as caller return: TOTAL ends at the
    # execute_plan_return event, not the remote persist/emit span.
    assert report.total_ms == pytest.approx(21829.0, abs=1e-6)
    assert report.accounted_ms == pytest.approx(report.non_scheduling_ms, abs=1e-6)
    assert abs(report.reconciliation_ms) <= 25.0


# ── Active-read matching ───────────────────────────────────────────────────
def test_active_read_never_chooses_foreign_or_clip_read():
    """A CLIP read or a read from another request must never be selected; the
    checkpoint detail is omitted and checkpoint_read_unavailable is flagged."""
    result = build_real_run_result()
    structured = result["pre_sampler_structured_report"]
    read = structured["active_read_records"][0]
    structured["active_read_records"] = [
        {"owner": "clip", "path_hash": "aabbccddeeff", "wall_ms": 50.0,
         "start_wall_unix_ns": read["start_wall_unix_ns"],
         "end_wall_unix_ns": read["end_wall_unix_ns"]},
        {"owner": "unet", "path_hash": "foreign", "request_id": "other-request",
         "start_wall_unix_ns": read["start_wall_unix_ns"],
         "end_wall_unix_ns": read["end_wall_unix_ns"]},
    ]
    report = _report(result)
    assert "unet_checkpoint_read" not in _details(report)
    assert "checkpoint_read_unavailable" in report.data_flags
    # Required data missing -> validation cannot be declared complete.
    assert report.diagnostic_status == "INCOMPLETE"


def test_active_read_safe_match_selected_over_foreign():
    """The record matching this request is selected even when a foreign read
    is also present."""
    result = build_real_run_result()
    structured = result["pre_sampler_structured_report"]
    read = structured["active_read_records"][0]
    structured["active_read_records"] = [
        {"owner": "unet", "path_hash": "foreign", "request_id": "other-request",
         "start_wall_unix_ns": read["start_wall_unix_ns"],
         "end_wall_unix_ns": read["end_wall_unix_ns"]},
        dict(read),
    ]
    report = _report(result)
    detail = _details(report)["unet_checkpoint_read"]
    assert detail.duration_ms == pytest.approx(1047.0)
    assert "checkpoint_read_unavailable" not in report.data_flags
    assert report.diagnostic_status == "COMPLETE"


# ── Visibility: 10-50 ms target + required-data flags ──────────────────────
def test_10_50ms_reconciliation_renders_target_warning():
    """10-50 ms: status stays OK under the hard ceiling but the missed 10 ms
    target is rendered explicitly (never hidden)."""
    report = _sampler_node_missing_report()  # ~40 ms gap
    assert report.reconciliation_status == "OK"
    rendered = render_waterfall(report, terminal_columns=132)
    target_row = next(
        line for line in rendered.splitlines() if "| TARGET 10MS" in line
    )
    assert "MISSED" in target_row
    status_row = next(line for line in rendered.splitlines() if "| STATUS" in line)
    assert "OK" in status_row


def test_required_data_flag_renders_compact_and_validation_incomplete():
    """checkpoint_read_unavailable renders as compact 'Required data:' and the
    validation status is INCOMPLETE even when reconciliation is OK."""
    result = build_real_run_result()
    result["pre_sampler_structured_report"]["active_read_records"] = []
    report = _report(result)
    assert report.data_flags == ("checkpoint_read_unavailable",)
    assert report.diagnostic_status == "INCOMPLETE"
    rendered = render_waterfall(report, terminal_columns=132)
    assert "Required data: checkpoint_read_unavailable" in rendered
    assert "VALIDATION: INCOMPLETE" in rendered


# ── No H2D substitution ────────────────────────────────────────────────────
def test_h2d_pair_never_substituted_for_checkpoint_read():
    """Even with the H2D pair available, the checkpoint detail is NEVER
    substituted with it; the H2D row stays independent and distinct."""
    result = build_real_run_result()
    result["pre_sampler_structured_report"]["active_read_records"] = []
    report = _report(result)
    details = _details(report)
    assert "unet_checkpoint_read" not in details
    assert "checkpoint_read_unavailable" in report.data_flags
    h2d = details["unet_synchronized_h2d"]
    assert h2d.duration_ms == pytest.approx(2214.0)
    # With a valid active read the read span is NOT the H2D span (distinct).
    full = _report(build_real_run_result())
    read = _details(full)["unet_checkpoint_read"]
    assert read.duration_ms == pytest.approx(1047.0)
    assert read.duration_ms != h2d.duration_ms
    assert read.source_fields == ()  # measured from the active-read boundaries


# ── Live-iteration 1 corrections ───────────────────────────────────────────
def test_unavailable_top_level_rows_not_rendered():
    """Never render unavailable top-level rows (live bad rows: UNET claim,
    sampler graph-join wait).  A required unavailable boundary surfaces only
    via Required data / reconciliation status, not a blank table row."""
    result = build_real_run_result()
    # Remove the graph-join metadata so sampler_graph_join_wait is unavailable.
    result["trace"]["events"] = [
        e for e in result["trace"]["events"] if e["name"] != "unet_graph_join"
    ]
    result["pre_sampler_structured_report"]["active_read_records"] = []
    report = _report(result)
    stages = _stages(report)
    assert stages["sampler_graph_join_wait"].status == "unavailable"
    rendered = render_waterfall(report, terminal_columns=132)
    assert "Sampler graph-join wait" not in rendered
    assert "Method entry to UNET ownership claim" not in rendered
    assert "UNET claim to ready" not in rendered
    # The unavailable stage is honestly excluded from accounted (honest gap),
    # never rendered as a blank row.
    assert report.accounted_ms == pytest.approx(report.non_scheduling_ms - 230.0, abs=1e-6)


def test_pre_sampler_consolidation_preserves_accounted():
    """First node -> sampler node is ONE mutually-exclusive top-level
    'Pre-sampler execution'; CLIP/UNET/cache timings are inline details.  The
    consolidated duration equals the sum it replaces, so the accounted total
    is byte-identical."""
    report = _reconciled_fixture()
    stages = _stages(report)
    assert "first_node_to_clip" not in stages
    assert "clip_to_sampler_node" not in stages
    pre = stages["pre_sampler_execution"]
    assert pre.status in ("measured", "derived")
    assert pre.duration_ms == pytest.approx(400.0 + 300.0, abs=1e-6)
    assert pre.included_in_total is True
    assert pre.accounting_role == "top_level"
    # Unchanged accounted: exclusive top-level sum == the non-scheduling wall.
    assert report.accounted_ms == pytest.approx(report.non_scheduling_ms, abs=1e-6)
    assert abs(report.reconciliation_ms) <= 1e-6
    # CLIP/UNET/cache details live under Pre-sampler execution.
    rendered = render_waterfall(report, terminal_columns=132)
    pre_row_index = next(
        i for i, line in enumerate(rendered.splitlines())
        if line.startswith("| ") and "Pre-sampler execution" in line
    )
    for detail_key in ("unet_checkpoint_read", "unet_synchronized_h2d"):
        detail = _details(report)[detail_key]
        detail_index = next(
            i for i, line in enumerate(rendered.splitlines())
            if line.startswith("| ") and line.split("|")[1].strip() == ""
            and _ascii(detail.label) in line
        )
        assert detail_index > pre_row_index, detail_key
    # get_model stays in the exhaustive artifact (a real producer supplies it).
    assert "unet_get_model" in _details(report)
    assert "First node to CLIP" not in rendered
    assert "CLIP to sampler node" not in rendered


def test_subms_clutter_omitted_from_render():
    """0.000/0.001/0.002/0.003 optional rows (runtime config, legacy
    resolution, repair/setup, sampler lane wait, VAE schedule/ready gaps) are
    never printed; curated details stay in the serialized artifact."""
    result = build_real_run_result()
    # Inject a realistic set of tiny optional timings the live run produced.
    result["local_timing"] = {
        "runtime_configuration_ms": 0.0,
        "legacy_runtime_resolution_ms": 0.0,
        "preload_check_ms": 3.0,
        "missing_node_repair_ms": 0.0,
        "executor_reset_ms": 0.0,
        "sampler_lane_wait_ms": 0.0,
    }
    report = _report(result)
    rendered = render_waterfall(report, terminal_columns=132)
    for label in (
        "runtime configuration", "legacy runtime resolution", "preload check",
        "missing-node repair", "executor reset", "sampler lane wait",
        "VAE scheduled -> worker/load start", "VAE ready -> consumed",
        "Sampling end -> VAE scheduled", "Consumed -> decode start",
    ):
        assert label not in rendered, f"sub-ms clutter leaked: {label!r}"
    # The exhaustive artifact still carries them.
    all_labels = " | ".join(_ascii(d.label) for d in report.details)
    assert "runtime configuration" in all_labels


# ── Cache observability fidelity (live iteration 3 / run 4) ────────────────
def _run4_cache_events():
    """Exact event sequence from the run-4 artifact: an authoritative
    ``exact_hit`` (prefill encoded_count=0) followed by a no-op
    ``miss_not_stored`` (zero encode / zero store / zero miss entries)."""
    request_id = "req-20260812-142808"
    return [
        {
            "name": "clip_conditioning_cache_decision", "process": "remote",
            "wall_unix_ns": 100, "monotonic_ns": 100,
            "metadata": {
                "decision": "exact_hit", "key_hash": "e2405962",
                "identity_status": "valid", "encode_calls": 0,
                "schema_version": 1, "validation_scope": "wf",
                "entry_count": 1, "request_id": request_id,
            },
        },
        {
            "name": "clip_conditioning_cache_lookup", "process": "remote",
            "wall_unix_ns": 101, "monotonic_ns": 101,
            "metadata": {
                "hit_count": 1, "miss_count": 0, "entry_count": 1,
                "lookup_wall_ms": 12.3, "request_id": request_id,
            },
        },
        {
            "name": "clip_conditioning_cache_decision", "process": "remote",
            "wall_unix_ns": 102, "monotonic_ns": 102,
            "metadata": {
                "decision": "miss_not_stored", "encode_calls": 0,
                "encode_loop_wall_ms": 0.0, "cache_store_calls": 0,
                "cache_store_wall_ms": 0.0, "entry_count": 0,
                "reason": "noop", "request_id": request_id,
            },
        },
    ]


def test_cache_exact_hit_not_overridden_by_noop_miss_not_stored():
    """Run-4 fidelity: a real exact_hit followed by a no-op miss_not_stored
    must render as exact_hit, never a contradictory miss label."""
    result = build_real_run_result()
    result["trace"]["events"] = result["trace"]["events"] + _run4_cache_events()
    report = _report(result)
    detail = _details(report)["conditioning_cache_lookup"]
    assert "exact_hit" in detail.label
    assert "miss_not_stored" not in detail.label
    assert "hit=1" not in detail.label  # no contradictory counts on a hit
    assert detail.duration_ms == pytest.approx(12.3, abs=1e-6)
    assert detail.accounting_role == "child"
    assert detail.included_in_total is False

    rendered = render_waterfall(report, terminal_columns=132)
    assert "Conditioning cache exact_hit" in rendered
    assert "miss_not_stored" not in rendered
    assert "CLIP encode skipped (cache hit)" in rendered
    # No fake CLIP-encode duration: the skipped row is status text only.
    assert "CLIP encode (" not in rendered.replace("CLIP encode skipped", "")
    # Accounted unchanged: cache details never affect the exclusive sum.
    assert report.accounted_ms == pytest.approx(report.non_scheduling_ms, abs=1e-6)


def test_cache_real_miss_stored_still_renders_miss():
    """A real miss_stored (encode/store work performed) keeps the miss label."""
    result = build_real_run_result()
    result["trace"]["events"] = result["trace"]["events"] + [
        {
            "name": "clip_conditioning_cache_lookup", "process": "remote",
            "wall_unix_ns": 100, "monotonic_ns": 100,
            "metadata": {
                "hit_count": 0, "miss_count": 1, "entry_count": 1,
                "lookup_wall_ms": 8.1, "request_id": "req-20260812-142808",
            },
        },
        {
            "name": "clip_conditioning_cache_decision", "process": "remote",
            "wall_unix_ns": 101, "monotonic_ns": 101,
            "metadata": {
                "decision": "miss_stored", "encode_calls": 3,
                "cache_store_calls": 1, "entry_count": 1,
                "request_id": "req-20260812-142808",
            },
        },
    ]
    report = _report(result)
    detail = _details(report)["conditioning_cache_lookup"]
    assert "miss_stored" in detail.label
    assert "exact_hit" not in detail.label
    rendered = render_waterfall(report, terminal_columns=132)
    assert "miss_stored" in rendered
    assert report.accounted_ms == pytest.approx(report.non_scheduling_ms, abs=1e-6)
