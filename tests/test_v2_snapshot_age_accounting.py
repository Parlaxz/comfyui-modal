from __future__ import annotations

from tools.v2_waterfall import build_waterfall, waterfall_to_dict


def test_snapshot_callback_age_is_informational_and_not_a_request_stage():
    result = {
        "snapshot_callback_age_at_restore_ms": 304000.0,
        "snapshot_callback_to_command_start_ms": 302000.0,
        "command_start_to_restore_start_ms": 1631.935,
        "trace": {"events": []},
    }
    report = build_waterfall(
        result=result,
        timing={},
        wall_ms=56251.0,
        command_start_unix_ms=1000,
        response_received_unix_ns=57_251_000_000,
    )
    assert all(stage.key not in {
        "snapshot_callback_age_at_restore_ms",
        "snapshot_callback_to_command_start_ms",
    } for stage in report.stages)
    data = waterfall_to_dict(report)
    assert data["total_ms"] == 56251.0


def test_platform_stage_uses_non_overlapping_dispatch_components():
    result = {
        "dispatch_to_modal_entry_ms": 27096.038,
        "restore_total_ms": 1631.935,
        "restore_end_to_modal_method_ms": 104.897,
        "trace": {"events": []},
    }
    report = build_waterfall(result=result, timing={}, wall_ms=56251.0)
    stage = next(item for item in report.stages if item.key == "modal_scheduling")
    assert stage.duration_ms == 25359.206
    assert stage.source_fields == (
        "dispatch_to_modal_entry_ms",
        "restore_total_ms",
        "restore_end_to_modal_method_ms",
    )
