"""V2 waterfall scheduling-contract regression tests (NEW timing contract).

Scheduling time = (command -> Modal enqueue) + (Modal scheduling / placement).
Everything else is NON-scheduling, derived as total - scheduling_time.  The
invariant COMMAND->RESPONSE == scheduling + non-scheduling holds by
construction; display drift is rounding only.

Implements the ten mandated scenarios (A-J) against the REAL implementation
(``comfymodal_runtime.v2_waterfall``) and the shared real-run fixtures
(``tests/v2_waterfall_reconciliation_fixtures.py``):

  A. Reference-run arithmetic is exact (enqueue 19158.0, placement 854.266,
     total 35168.0 -> scheduling_time 20012.266, non_scheduling 15155.734).
  B. Startup changes affect ONLY non-scheduling.
  C. Enqueue delay changes ONLY scheduling.
  D. Placement changes ONLY scheduling.
  E. Rendered footer values reconcile within display rounding.
  F. command_response_ms equals the authoritative outer wall.
  G. Full hardware header renders every telemetry segment.
  H. Missing telemetry is never fabricated (no fake zeros, lines omitted).
  I. A REMOTE partial upgrades to a conclusive final render on the host.
  J. No "TOTAL WALL" heading anywhere in either renderer.
"""

from __future__ import annotations

import pytest

from comfymodal_runtime.v2_waterfall import (
    attach_waterfall,
    build_waterfall,
    render_waterfall,
    waterfall_to_dict,
)
from tests.v2_waterfall_reconciliation_fixtures import (
    LOCAL_PREP_MS,
    SUBMISSION_MS,
    attach_host_telemetry,
    build_real_run_result,
    build_reference_run_result,
    command_start_ms,
    response_ns_for,
)

REFERENCE_ENQUEUE_MS = 19158.0
REFERENCE_PLACEMENT_MS = 854.266
REFERENCE_TOTAL_MS = 35168.0

_FOOTER_LABELS = (
    "COMMAND -> RESPONSE:",
    "Command (without scheduling) -> Response:",
    "Scheduling time:",
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


def _footer_values(rendered) -> dict[str, float]:
    """Parse the three conclusive footer lines (seconds) from a render."""
    values: dict[str, float] = {}
    for line in rendered.splitlines():
        for label in _FOOTER_LABELS:
            if line.startswith(label):
                values[label] = float(line[len(label):].strip().rstrip("s"))
    assert set(values) == set(_FOOTER_LABELS), values
    return values


def _footer_pending_lines(rendered) -> list[str]:
    return [
        line for line in rendered.splitlines()
        if line.startswith(_FOOTER_LABELS)
    ]


# ── A. Reference-run arithmetic is exact ────────────────────────────────────
def test_a_reference_run_arithmetic_exact():
    """The reference fixture yields scheduling_time == enqueue + placement and
    non_scheduling == total - scheduling_time, and the rendered footer shows
    the exact 35.168 / 15.156 / 20.012 display values."""
    report = _report(build_reference_run_result())
    assert report.command_to_enqueue_ms == pytest.approx(REFERENCE_ENQUEUE_MS, abs=0.01)
    assert report.scheduling_ms == pytest.approx(REFERENCE_PLACEMENT_MS, abs=0.01)
    assert report.scheduling_time_ms == pytest.approx(20012.266, abs=0.01)
    assert report.non_scheduling_ms == pytest.approx(15155.734, abs=0.01)
    assert report.total_ms == pytest.approx(REFERENCE_TOTAL_MS, abs=0.01)

    rendered = render_waterfall(report)
    assert "35.168s" in rendered
    assert "15.156s" in rendered
    assert "20.012s" in rendered
    values = _footer_values(rendered)
    # Display invariant: 15.156 + 20.012 == 35.168 within rounding.
    assert abs(
        values["Command (without scheduling) -> Response:"]
        + values["Scheduling time:"]
        - values["COMMAND -> RESPONSE:"]
    ) <= 0.002


# ── B. Startup changes affect ONLY non-scheduling ───────────────────────────
def test_b_startup_changes_non_scheduling_only():
    """Growing the startup (pre-Python restore) window must never move the
    scheduling numbers: scheduling_time stays put while non-scheduling and the
    total grow by exactly 5000 ms."""
    base = _report(build_reference_run_result())
    shifted = _report(build_reference_run_result(post_restore_shift_ms=5000.0))
    assert shifted.command_to_enqueue_ms == pytest.approx(base.command_to_enqueue_ms, abs=0.01)
    assert shifted.scheduling_ms == pytest.approx(base.scheduling_ms, abs=0.01)
    assert shifted.scheduling_time_ms == pytest.approx(base.scheduling_time_ms, abs=0.01)
    assert shifted.non_scheduling_ms == pytest.approx(base.non_scheduling_ms + 5000.0, abs=0.01)
    assert shifted.total_ms == pytest.approx(base.total_ms + 5000.0, abs=0.01)
    # The pre-Python span itself grew by 5000; other post-restore stages kept
    # their exact durations.
    base_stages = _stages(base)
    shifted_stages = _stages(shifted)
    assert shifted_stages["pre_python_snapshot_restore"].duration_ms == pytest.approx(
        base_stages["pre_python_snapshot_restore"].duration_ms + 5000.0, abs=0.01
    )
    for key in ("application_restore", "sampling", "vae", "remote_local_return"):
        assert shifted_stages[key].duration_ms == pytest.approx(
            base_stages[key].duration_ms, abs=0.01
        )


# ── C. Enqueue delay changes ONLY scheduling ────────────────────────────────
def test_c_enqueue_delay_changes_scheduling_only():
    """A 3000 ms delay before the Modal enqueue lands entirely in scheduling:
    command_to_enqueue and scheduling_time grow by 3000, placement is
    unchanged, and non-scheduling stays put when the total shifts with the
    delay."""
    base = _report(build_reference_run_result())
    delayed = _report(build_reference_run_result(
        enqueue_ms=REFERENCE_ENQUEUE_MS + 3000.0,
        total_ms=REFERENCE_TOTAL_MS + 3000.0,
    ))
    assert delayed.command_to_enqueue_ms == pytest.approx(base.command_to_enqueue_ms + 3000.0, abs=0.01)
    assert delayed.scheduling_time_ms == pytest.approx(base.scheduling_time_ms + 3000.0, abs=0.01)
    assert delayed.scheduling_ms == pytest.approx(base.scheduling_ms, abs=0.01)
    assert delayed.non_scheduling_ms == pytest.approx(base.non_scheduling_ms, abs=0.01)
    base_stages = _stages(base)
    delayed_stages = _stages(delayed)
    for key in ("pre_python_snapshot_restore", "application_restore", "sampling"):
        assert delayed_stages[key].duration_ms == pytest.approx(
            base_stages[key].duration_ms, abs=0.01
        )


# ── D. Placement changes ONLY scheduling ────────────────────────────────────
def test_d_placement_changes_scheduling_only():
    """A 2000 ms longer placement lands entirely in scheduling: scheduling_ms
    (placement) and scheduling_time_ms grow by 2000 while non-scheduling and
    every post-restore stage stay put (the total shifts with the placement)."""
    base = _report(build_reference_run_result())
    changed = _report(build_reference_run_result(
        placement_ms=REFERENCE_PLACEMENT_MS + 2000.0,
        total_ms=REFERENCE_TOTAL_MS + 2000.0,
    ))
    assert changed.scheduling_ms == pytest.approx(base.scheduling_ms + 2000.0, abs=0.01)
    assert changed.scheduling_time_ms == pytest.approx(base.scheduling_time_ms + 2000.0, abs=0.01)
    assert changed.command_to_enqueue_ms == pytest.approx(base.command_to_enqueue_ms, abs=0.01)
    assert changed.non_scheduling_ms == pytest.approx(base.non_scheduling_ms, abs=0.01)
    base_stages = _stages(base)
    changed_stages = _stages(changed)
    for key in ("pre_python_snapshot_restore", "application_restore", "sampling"):
        assert changed_stages[key].duration_ms == pytest.approx(
            base_stages[key].duration_ms, abs=0.01
        )


# ── E. Footer values reconcile within rounding ──────────────────────────────
def test_e_footer_values_reconcile_within_rounding():
    """Across several scheduling compositions the three rendered footer lines
    satisfy |scheduling + non-scheduling - total| <= 0.002 s, and each parsed
    value equals the report field formatted to 3 decimals."""
    variants = [
        build_reference_run_result(),
        build_reference_run_result(
            enqueue_ms=REFERENCE_ENQUEUE_MS + 3000.0,
            total_ms=REFERENCE_TOTAL_MS + 3000.0,
        ),
        build_reference_run_result(
            placement_ms=REFERENCE_PLACEMENT_MS + 2000.0,
            total_ms=REFERENCE_TOTAL_MS + 2000.0,
        ),
        build_reference_run_result(post_restore_shift_ms=5000.0),
        build_real_run_result(),
        build_real_run_result(enqueue_ms=LOCAL_PREP_MS + SUBMISSION_MS + 1500.0),
        build_real_run_result(scheduling_ms=12000.0),
    ]
    for result in variants:
        report = _report(result)
        rendered = render_waterfall(report)
        values = _footer_values(rendered)
        assert abs(
            values["Scheduling time:"]
            + values["Command (without scheduling) -> Response:"]
            - values["COMMAND -> RESPONSE:"]
        ) <= 0.002
        assert values["COMMAND -> RESPONSE:"] == float(f"{report.total_ms / 1000.0:.3f}")
        assert values["Command (without scheduling) -> Response:"] == float(
            f"{report.non_scheduling_ms / 1000.0:.3f}"
        )
        assert values["Scheduling time:"] == float(f"{report.scheduling_time_ms / 1000.0:.3f}")


# ── F. command_response_ms is the exact outer wall ──────────────────────────
def test_f_command_response_exact_outer_wall():
    """total_ms equals the authoritative command_start -> caller_return boundary
    delta (the fixture's response offset / wall_ms) exactly, regardless of how
    the scheduling components vary, and command_response_ms mirrors it."""
    results = [
        build_real_run_result(),
        build_real_run_result(scheduling_ms=12000.0),
        build_real_run_result(enqueue_ms=1520.0),
        build_real_run_result(pre_python_ms=20000.0),
        build_reference_run_result(),
    ]
    for result in results:
        report = _report(result)
        assert report.total_ms == pytest.approx(result["wall_ms"], abs=1e-6)
        assert report.command_response_ms == report.total_ms


# ── G. Hardware header: every segment renders ───────────────────────────────
def test_g_hardware_header_all_fields():
    """The canonical telemetry fixture renders the full 4-line compact header:
    GPU trimmed, VRAM thousands-separated, CUDA/CC, CPU identity + runtime, and
    the Telemetry line (CPU peak, RSS chain, maxRSS)."""
    result = attach_host_telemetry(build_real_run_result())
    report = _report(result)
    rendered = render_waterfall(report)
    lines = rendered.splitlines()
    request_line = lines[1]
    assert request_line.startswith("Request:   ")
    assert "req-20260812-142808" in request_line
    assert "Instance: ri-realrun-01" in request_line
    assert "Fresh: YES" in request_line

    platform_line = next(line for line in lines if line.startswith("Platform:  "))
    assert "aws/us-east-1" in platform_line
    assert "GPU: RTX PRO 6000 Blackwell" in platform_line
    assert "VRAM 97,250 MiB" in platform_line
    assert "CUDA 13.0" in platform_line
    assert "CC 12.0" in platform_line

    cpu_line = next(line for line in lines if line.startswith("CPU:       "))
    assert "AMD Family 191 Model 2" in cpu_line
    assert "visible=28" in cpu_line
    assert "requested=12" in cpu_line
    assert "Torch=12/14" in cpu_line
    assert "native=53" in cpu_line

    telemetry_line = next(line for line in lines if line.startswith("Telemetry: "))
    assert "CPU peak=7.13 cores" in telemetry_line
    assert ">16 cores=0ms" in telemetry_line  # measured zero is real data
    assert f"RSS {9888 / 1024.0:.2f} -> {23572 / 1024.0:.2f} -> {13466 / 1024.0:.2f} GiB" in telemetry_line
    assert f"maxRSS={36612 / 1024.0:.2f} GiB" in telemetry_line


def test_g_positive_above_16_cores_segment_renders():
    """The '>16 cores' segment is a real measured value: a positive value must
    appear verbatim, and a measured zero renders as '0ms' (real data — only a
    MISSING measurement is omitted, never fabricated)."""
    result = attach_host_telemetry(build_real_run_result(), above_16_ms=1250)
    rendered = render_waterfall(_report(result))
    telemetry_line = next(line for line in rendered.splitlines() if line.startswith("Telemetry: "))
    assert ">16 cores=1250ms" in telemetry_line
    # With the default measured 0 the segment still renders (reference-run
    # header shows ">16 cores=0ms").
    default = render_waterfall(_report(attach_host_telemetry(build_real_run_result())))
    assert ">16 cores=0ms" in default
    # A MISSING measurement (None) is omitted — never a fabricated value.
    absent = render_waterfall(_report(attach_host_telemetry(build_real_run_result(), above_16_ms=None)))
    assert ">16 cores" not in absent


# ── H. Missing telemetry is never fabricated ────────────────────────────────
def test_h_missing_optional_telemetry_not_fabricated():
    """A fixture WITHOUT any telemetry renders only the always-emitted header
    lines (Request/Instance/Fresh and Platform); every optional segment and the
    CPU/Telemetry lines are omitted — no fake zeros, no '0.00' for maxRSS."""
    result = build_real_run_result()
    report = _report(result)
    rendered = render_waterfall(report)
    lines = rendered.splitlines()
    assert lines[1].startswith("Request:   ")
    assert "Instance: ri-realrun-01" in lines[1]
    assert lines[2].startswith("Platform:  ")
    assert "aws/us-east-1" in lines[2]
    for token in (
        "VRAM", "CUDA", "CC ", "visible=", "Torch=", "native=",
        "CPU peak", "RSS", "maxRSS",
    ):
        assert token not in rendered, f"fabricated/missing telemetry leaked: {token!r}"
    assert not any(line.startswith("CPU:") for line in lines)
    assert not any(line.startswith("Telemetry:") for line in lines)
    # The header region (before the boxed table) must never fabricate a zero
    # for missing data (the stage table may legitimately show 0.000 ms rows).
    header_region = rendered.split("+-----+")[0]
    assert "0.00" not in header_region
    assert "0ms" not in header_region


def test_h_partial_telemetry_gpu_only():
    """With ONLY gpu_allocation present, the Platform line carries the GPU/
    VRAM/CUDA/CC segments while the CPU and Telemetry lines are omitted."""
    result = build_real_run_result()
    result["gpu_allocation"] = {
        "gpu_requested_order": "a10g",
        "torch_version": "2.9.0",
        "gpu_actual_name": "NVIDIA L4",
        "gpu_compute_capability": "8.9",
        "gpu_vram_total_mib": 22934,
        "cuda_version": "12.4",
    }
    rendered = render_waterfall(_report(result))
    lines = rendered.splitlines()
    platform_line = next(line for line in lines if line.startswith("Platform:  "))
    assert "GPU: L4" in platform_line
    assert "VRAM 22,934 MiB" in platform_line
    assert "CUDA 12.4" in platform_line
    assert "CC 8.9" in platform_line
    assert not any(line.startswith("CPU:") for line in lines)
    assert not any(line.startswith("Telemetry:") for line in lines)


# ── I. Partial upgrades to a conclusive final render ────────────────────────
def test_i_partial_upgrades_to_conclusive_final():
    """A REMOTE partial render carries the intermediate 'awaiting host
    reconciliation' token on the footer lines it cannot resolve; the host
    rebuild (attach_waterfall with replace_partial=True) produces a final
    render with NO pending token and real footer values."""
    partial_result = build_real_run_result(boundaries=False, restore_begin=False)
    partial_report = _report(partial_result)
    assert partial_report.partial_waterfall is True
    partial_render = render_waterfall(partial_report)
    pending_lines = _footer_pending_lines(partial_render)
    assert len(pending_lines) == 3
    # Scheduling components are unknown remotely -> pending token; the command
    # -> response window IS measurable -> a real value.
    assert "awaiting host reconciliation" in partial_render
    assert "awaiting host reconciliation" in pending_lines[1]
    assert "awaiting host reconciliation" in pending_lines[2]
    assert "awaiting host reconciliation" not in pending_lines[0]

    # Host rebuild replaces the partial with the conclusive final report.
    full_result = build_real_run_result()
    full_result["waterfall"] = waterfall_to_dict(partial_report)
    attach_waterfall(
        full_result,
        timing={}, wall_ms=None,
        command_start_unix_ms=command_start_ms(),
        response_received_unix_ns=response_ns_for(full_result["wall_ms"]),
        modal_restore_begin_wall_unix_ns=full_result["modal_restore_begin_wall_unix_ns"],
        replace_partial=True,
        print_render=False,
    )
    final_report = full_result["waterfall"]
    assert final_report["partial_waterfall"] is False
    final_render = render_waterfall(final_report)
    assert "awaiting host reconciliation" not in final_render
    final_values = _footer_values(final_render)
    assert final_values["COMMAND -> RESPONSE:"] > 0.0
    assert final_values["Command (without scheduling) -> Response:"] > 0.0
    assert final_values["Scheduling time:"] > 0.0


# ── J. No TOTAL WALL heading in either renderer ─────────────────────────────
def test_j_no_total_wall_heading_in_final():
    """The user-facing contract has no TOTAL WALL anywhere: not in the
    reconciled final render and not in the REMOTE/PARTIAL render."""
    full_render = render_waterfall(_report(build_real_run_result()))
    assert "TOTAL WALL" not in full_render
    assert "total wall" not in full_render.lower()

    partial_render = render_waterfall(
        _report(build_real_run_result(boundaries=False, restore_begin=False))
    )
    assert "TOTAL WALL" not in partial_render
    assert "total wall" not in partial_render.lower()
