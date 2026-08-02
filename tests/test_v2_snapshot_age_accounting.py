from __future__ import annotations

import inspect

from tools.v2_waterfall import build_waterfall, waterfall_to_dict

_SNAPSHOT_AGE_FIELDS = (
    "snapshot_callback_age_at_restore_ms",
    "snapshot_callback_to_command_start_ms",
    "command_start_to_restore_start_ms",
)


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


def test_callback_age_fields_are_informational_only():
    """The snapshot-age fields are retained but informational: they never
    become waterfall stages and never contribute to the accounted total."""
    result = {
        "snapshot_callback_age_at_restore_ms": 304000.0,
        "snapshot_callback_to_command_start_ms": 302000.0,
        "command_start_to_restore_start_ms": 1631.935,
        "request_latency_included": 0,
        "dispatch_to_modal_entry_ms": 27096.038,
        "restore_total_ms": 1631.935,
        "restore_end_to_modal_method_ms": 104.897,
        "sampler_ms": 20000.0,
        "trace": {"events": []},
    }
    report = build_waterfall(result=result, timing={}, wall_ms=30000.0)
    # No stage/source-field carries any snapshot-age field.
    for stage in report.stages:
        assert not any(field in stage.source_fields for field in _SNAPSHOT_AGE_FIELDS)
        assert stage.key not in _SNAPSHOT_AGE_FIELDS
    # The callback age must not be mistaken for platform or restore time.
    stage_map = {stage.key: stage for stage in report.stages}
    assert stage_map["application_restore"].duration_ms == 1631.935
    assert stage_map["modal_scheduling"].duration_ms == 25359.206
    # Serialization retains the raw fields on the result (not as stages).
    data = waterfall_to_dict(report)
    assert all(stage["key"] not in _SNAPSHOT_AGE_FIELDS for stage in data["stages"])
    assert all("request_latency_included" not in stage["source_fields"] for stage in data["stages"])


def test_snapshot_timing_line_marks_request_latency_included_zero():
    """modal_app's [v2.snapshot_timing] one-liner emits the three callback-age
    fields with request_latency_included=0 and never references the obsolete
    platform_snapshot_capture_or_resume_gap marker."""
    import comfymodal_runtime.modal_app as modal_app
    source = inspect.getsource(modal_app.ModalRuntimeEntrypoint.restore)
    assert "[v2.snapshot_timing]" in source
    assert "snapshot_callback_age_at_restore_ms" in source
    assert "snapshot_callback_to_command_start_ms" in source
    assert "command_start_to_restore_start_ms" in source
    assert "request_latency_included=0" in source
    assert "platform_snapshot_capture_or_resume_gap" not in source
    assert "platform_snapshot_capture_or_resume_gap" not in inspect.getsource(modal_app)

