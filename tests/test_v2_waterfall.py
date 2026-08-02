from __future__ import annotations

import copy

from tools.v2_waterfall import (
    build_waterfall,
    render_comparison,
    render_waterfall,
    waterfall_to_dict,
)


def _event(name: str, wall_ms: int, mono_ms: int, process: str, **metadata):
    return {
        "name": name,
        "process": process,
        "wall_unix_ns": wall_ms * 1_000_000,
        "monotonic_ns": mono_ms * 1_000_000,
        "metadata": metadata,
    }


def _complete_result() -> dict:
    events = [
        _event("worker_start", 1000, 1000, "local"),
        _event("transport_entry", 1001, 1001, "local"),
        _event("modal_handle_lookup_start", 1001, 1001, "local"),
        _event("modal_submission_attempt", 1010, 1010, "local"),
        _event("remote_method_entry", 5100, 1100, "remote_method"),
        _event("prompt_executor_invoke_start", 5200, 1200, "remote"),
        _event("sampling_start", 6900, 2900, "remote"),
        _event("sampling_end", 10900, 6900, "remote"),
        _event("vae_decode_start", 10900, 6900, "remote"),
        _event("vae_decode_end", 11400, 7400, "remote"),
        _event("output_encode_start", 11400, 7400, "remote"),
        _event("output_encode_end", 11600, 7600, "remote"),
        _event("output_persist_start", 11600, 7600, "remote"),
        _event("output_persist_end", 12300, 8300, "remote"),
        _event("final_result_received", 13100, 13100, "local"),
        {
            "name": "prompt_executor_milestones",
            "process": "remote",
            "wall_unix_ns": 5_300_000_000,
            "monotonic_ns": 1_300_000_000,
            "metadata": {
                "executor_call_to_first_node_ms": 800,
                "invoke_to_execution_start_ms": 100,
                "execution_start_to_cached_ms": 200,
                "cached_to_first_node_ms": 100,
                "first_node_to_clip_ms": 300,
                "clip_to_sampler_node_ms": 400,
                "sampler_node_to_sampler_start_ms": 200,
                "output_encode_ms": 200,
                "output_commit_ms": 100,
            },
        },
    ]
    return {
        "request_id": "request-1",
        "identity": {
            "app_name": "stable-modal-comfy-v2-shadow",
            "class_name": "ModalRuntimeEntrypointV2",
            "gpu": "rtx-pro-6000",
            "restored_instance_id": "instance-1",
            "restore_count": 1,
            "request_count": 1,
        },
        "_restore_timing": {
            "remote_python_resume_wall_unix_ns": 4_000_000_000,
            "remote_python_resume_mono_ns": 0,
            "restore_method_start_wall_unix_ns": 4_000_000_000,
            "restore_method_start_mono_ns": 0,
            "restore_method_end_wall_unix_ns": 5_000_000_000,
            "restore_method_end_mono_ns": 1_000_000_000,
            "restore_total_ms": 1000,
        },
        "trace": {"events": events, "metadata": {}},
    }


def test_complete_trace_has_required_non_overlapping_rows_and_reconciles():
    result = _complete_result()
    report = build_waterfall(
        result=result,
        timing={"wall_ms": 12100},
        wall_ms=12100,
        command_start_unix_ms=1000,
        response_received_unix_ns=13100 * 1_000_000,
        run_label="run 1",
    )
    assert [stage.key for stage in report.stages] == [
        "local_preparation", "modal_handle_submission", "modal_scheduling",
        "application_restore", "restore_to_method_entry", "remote_method_setup",
        "prompt_executor_cache_setup", "first_node_to_clip", "clip_to_sampler_node",
        "sampler_node_to_sampling", "sampling", "post_sampling_transition", "vae", "output_persistence",
        "remote_return_handoff", "remote_local_return",
    ]
    assert all(not stage.overlaps for stage in report.stages)
    assert report.reconciliation_ms is not None
    assert report.total_ms is not None
    assert abs(report.reconciliation_ms) <= max(50, report.total_ms * 0.005)
    assert report.identity["fresh"] is True


def test_missing_values_are_unavailable_not_zero():
    report = build_waterfall(result={"trace": {"events": []}}, timing={}, wall_ms=100)
    assert all(stage.duration_ms is None for stage in report.stages if stage.key != "captured_timeline_gap")
    assert next(stage for stage in report.stages if stage.key == "captured_timeline_gap").duration_ms == 100.0
    output = render_waterfall(report, terminal_columns=132)
    assert "-" in output
    assert "Captured timeline gaps / residual" in output


def test_cross_process_uses_wall_and_same_process_uses_monotonic():
    result = _complete_result()
    result["trace"]["events"] = [
        _event("sampling_start", 1000, 9000, "local"),
        _event("sampling_end", 1700, 100, "remote"),
    ]
    report = build_waterfall(result=result, timing={}, wall_ms=700, command_start_unix_ms=1000, response_received_unix_ns=1700 * 1_000_000)
    sampling = next(stage for stage in report.stages if stage.key == "sampling")
    assert sampling.duration_ms == 700


def test_negative_duration_and_overlap_are_flagged():
    result = _complete_result()
    result["trace"]["events"] = [event for event in result["trace"]["events"] if event["name"] not in {"sampling_start", "sampling_end"}]
    result["trace"]["events"] += [
        _event("sampling_start", 8000, 8000, "remote"),
        _event("sampling_end", 7000, 7000, "remote"),
    ]
    result["_restore_timing"]["restore_method_start_wall_unix_ns"] = 3500 * 1_000_000
    report = build_waterfall(result=result, timing={}, wall_ms=12100, command_start_unix_ms=1000, response_received_unix_ns=13100 * 1_000_000)
    assert any(stage.status == "invalid" for stage in report.stages)
    assert any("negative" in warning or "overlap" in warning for warning in report.warnings)


def test_impossible_stage_larger_than_total_is_flagged():
    result = _complete_result()
    for event in result["trace"]["events"]:
        if event["name"] == "prompt_executor_milestones":
            event["metadata"]["executor_call_to_first_node_ms"] = 20_000
    report = build_waterfall(
        result=result,
        timing={},
        wall_ms=100,
        command_start_unix_ms=1000,
        response_received_unix_ns=1100 * 1_000_000,
    )
    stage = next(stage for stage in report.stages if stage.key == "prompt_executor_cache_setup")
    assert stage.status == "invalid"
    assert any("exceeds command-to-response" in warning for warning in report.warnings)


def test_reconciliation_warning_and_tolerance():
    result = _complete_result()
    for event in result["trace"]["events"]:
        if event["name"] == "prompt_executor_milestones":
            event["metadata"]["executor_call_to_first_node_ms"] = 1000
    report = build_waterfall(result=result, timing={}, wall_ms=1, command_start_unix_ms=1000, response_received_unix_ns=14100 * 1_000_000)
    assert report.reconciliation_ms is not None
    assert report.warnings
    assert "reconciliation exceeds tolerance" in " ".join(report.warnings)


def test_widths_long_labels_details_and_comparison():
    report = build_waterfall(result=_complete_result(), timing={}, wall_ms=12100, command_start_unix_ms=1000, response_received_unix_ns=13100 * 1_000_000, run_label="a very long run label")
    for width in (90, 110, 132, 180, 220):
        rendered = render_waterfall(report, terminal_columns=width)
        assert "V2 COLD WATERFALL" in rendered
        assert "PromptExecutor/cache setup" in rendered
        assert "detail:" in rendered
    comparison = render_comparison([report, report, report])
    assert "THREE-RUN COLD COMPARISON" in comparison
    assert "Median:" in comparison


def test_waterfall_is_additive_and_does_not_mutate_result_or_trace():
    result = _complete_result()
    before = copy.deepcopy(result)
    report = build_waterfall(result=result, timing={"wall_ms": 10}, wall_ms=10)
    waterfall_to_dict(report)
    render_waterfall(report, terminal_columns=132)
    assert result == before


def test_structured_report_contains_details_excluded_from_totals():
    report = build_waterfall(result=_complete_result(), timing={}, wall_ms=12100, command_start_unix_ms=1000, response_received_unix_ns=13100 * 1_000_000)
    data = waterfall_to_dict(report)
    assert data["stages"]
    assert data["details"]
    assert all(detail["included_in_total"] is False for detail in data["details"])


def test_serialized_report_render_keeps_detail_rows():
    report = build_waterfall(result=_complete_result(), timing={}, wall_ms=12100, command_start_unix_ms=1000, response_received_unix_ns=13100 * 1_000_000)
    rendered = render_waterfall(waterfall_to_dict(report), terminal_columns=132)
    assert rendered.count("detail:") == len(report.details)


def test_request_origin_and_residual_close_accounting_gap():
    result = _complete_result()
    result["trace"]["metadata"] = {
        "request_origin_info": {
            "ui_run_triggered_wall_unix_ms": 1000,
            "local_receive_wall_ns": 1001 * 1_000_000,
            "modal_submission_attempt_wall_unix_ns": 1010 * 1_000_000,
        }
    }
    result["_restore_timing"].update({
        "remote_python_resume_wall_unix_ns": 4000 * 1_000_000,
        "remote_python_resume_mono_ns": 0,
    })
    report = build_waterfall(
        result=result,
        timing={},
        wall_ms=12100,
        command_start_unix_ms=1000,
        response_received_unix_ns=30000 * 1_000_000,
    )
    stages = {stage.key: stage for stage in report.stages}
    assert stages["local_preparation"].duration_ms == 1.0
    assert stages["modal_handle_submission"].duration_ms == 9.0
    assert stages["modal_scheduling"].duration_ms == 2990.0
    residual_report = build_waterfall(
        result={"trace": {"events": []}},
        timing={},
        wall_ms=0,
        command_start_unix_ms=1000,
        response_received_unix_ns=30000 * 1_000_000,
    )
    residual_stages = {stage.key: stage for stage in residual_report.stages}
    assert residual_stages["captured_timeline_gap"].duration_ms == 29000.0
    # The generic residual is the UNATTRIBUTED gap, not a measured stage:
    # it must NOT be folded into the accounted total or fabricated into a
    # perfect reconciliation (accounted == total, reconciliation == 0).
    assert residual_report.accounted_ms != residual_report.total_ms
    assert residual_report.reconciliation_ms != 0.0
    assert any("reconciliation" in warning or "unaccounted" in warning for warning in residual_report.warnings)


def test_structured_diagnostics_are_rendered_as_nested_detail_rows():
    result = _complete_result()
    result["pre_sampler_structured_report"] = {
        "cpu_owner_records": [{"operation": "CLIP.encode", "role": "CLIP", "wall_ms": 123.4}],
        "per_node_timings": [{"node_id": "42", "class_type": "CLIPTextEncode", "duration_ms": 234.5}],
        "active_read_records": [{"owner": "graph_loader", "path_hash": "abcdef1234567890", "wall_ms": 345.6}],
    }
    rendered = render_waterfall(build_waterfall(result=result, timing={}, wall_ms=1000), terminal_columns=180)
    assert "CPU owner: CLIP.encode [CLIP]" in rendered
    assert "Node: CLIPTextEncode" in rendered
    assert "Model read: graph_loader" in rendered


def test_rendered_waterfall_is_plain_ascii():
    report = build_waterfall(
        result=_complete_result(),
        timing={},
        wall_ms=12100,
        command_start_unix_ms=1000,
        response_received_unix_ns=13100 * 1_000_000,
    )
    rendered = render_waterfall(report, terminal_columns=132)
    assert all(ord(character) < 128 for character in rendered)


def test_submission_and_scheduling_populated_from_timing_fields_with_source_fields_and_no_overlap():
    result = {
        "request_id": "request-timing-fields",
        "trace": {"events": []},
        "local_timing": {
            "local_receive_to_actual_submission_ms": 42.0,
            "handle_lookup_ms": 20.0,
            "payload_serialize_ms": 12.0,
        },
        "dispatch_to_modal_entry_ms": 3120.0,
        "restore_total_ms": 1000.0,
        "restore_end_to_modal_method_ms": 100.0,
    }
    report = build_waterfall(result=result, timing={}, wall_ms=5000)
    stages = {stage.key: stage for stage in report.stages}
    submission = stages["modal_handle_submission"]
    assert submission.duration_ms == 42.0
    assert submission.status == "derived"
    assert submission.source_fields == ("local_receive_to_actual_submission_ms",)
    scheduling = stages["modal_scheduling"]
    assert scheduling.duration_ms == 2020.0
    assert scheduling.source_fields == (
        "dispatch_to_modal_entry_ms",
        "restore_total_ms",
        "restore_end_to_modal_method_ms",
    )
    # Non-overlapping top-level rows: none may flag another row.
    assert all(not stage.overlaps for stage in report.stages)


def test_negative_derived_stage_is_rejected():
    result = {
        "trace": {"events": []},
        "dispatch_to_modal_entry_ms": 500.0,
        "restore_total_ms": 800.0,
        "restore_end_to_modal_method_ms": 50.0,
    }
    report = build_waterfall(result=result, timing={}, wall_ms=1000)
    stage = next(item for item in report.stages if item.key == "modal_scheduling")
    assert stage.status == "invalid"
    assert stage.duration_ms is None
    assert any("negative" in warning for warning in report.warnings)
    # The rejected derived stage must not fabricate accounted time.
    assert report.reconciliation_ms is not None


def test_generic_residual_reflects_real_gap_not_perfect_reconciliation():
    result = {
        "trace": {"events": []},
        "local_timing": {"local_receive_to_actual_submission_ms": 40.0},
        "restore_total_ms": 1000.0,
        "sampler_ms": 2000.0,
    }
    report = build_waterfall(
        result=result,
        timing={},
        wall_ms=10000,
        command_start_unix_ms=1000,
        response_received_unix_ns=11000 * 1_000_000,
    )
    assert report.total_ms == 10000.0
    stages = {stage.key: stage for stage in report.stages}
    assert stages["captured_timeline_gap"].duration_ms is not None
    assert report.accounted_ms is not None
    assert report.accounted_ms != report.total_ms
    assert report.reconciliation_ms is not None
    accounted_ms = report.accounted_ms
    total_ms = report.total_ms
    reconciliation_ms = report.reconciliation_ms
    assert isinstance(accounted_ms, float)
    assert isinstance(total_ms, float)
    assert isinstance(reconciliation_ms, float)
    assert abs(reconciliation_ms - stages["captured_timeline_gap"].duration_ms) < 1e-6
    assert abs(reconciliation_ms - (total_ms - accounted_ms)) < 1e-6
    assert any("reconciliation exceeds tolerance" in warning for warning in report.warnings)
