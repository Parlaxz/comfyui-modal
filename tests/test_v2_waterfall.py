from __future__ import annotations

import copy

from tests.v2_baseline_fixtures import BASELINE_EXPECTED, BASELINE_ROWS
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


def _build_baseline_report(row: dict):
    result = {key: value for key, value in row.items() if key not in {
        "command_start_unix_ms", "response_received_unix_ns",
    }}
    return build_waterfall(
        result=result,
        timing={},
        wall_ms=None,
        command_start_unix_ms=row["command_start_unix_ms"],
        response_received_unix_ns=row["response_received_unix_ns"],
        run_label=row["request_id"],
    )


def test_three_baseline_rows_reconcile_within_tolerance():
    """Each sanitized baseline row reconciles within max(50ms, 0.5% total) with
    the platform row populated, restore counted exactly once, and restore-to-
    method-entry separate.  Fixture totals and exact supplied source values are
    asserted verbatim — not merely self-consistency."""
    assert len(BASELINE_ROWS) == len(BASELINE_EXPECTED) == 3
    for row, expected in zip(BASELINE_ROWS, BASELINE_EXPECTED):
        dispatch = row["dispatch_to_modal_entry_ms"]
        restore_total = row["restore_total_ms"]
        restore_to_method = row["restore_end_to_modal_method_ms"]
        expected_platform = dispatch - restore_total - restore_to_method
        assert expected_platform > 0, "fixture platform duration must be positive"
        # Fixture fields carry the exact supplied values.
        assert dispatch == expected["dispatch_to_modal_entry_ms"]
        assert restore_total == expected["restore_total_ms"]
        assert restore_to_method == expected["restore_end_to_modal_method_ms"]
        assert abs(expected_platform - expected["platform_ms"]) < 1e-9

        report = _build_baseline_report(row)
        stages = {stage.key: stage for stage in report.stages}

        # Total from the local command->response span equals the supplied total.
        assert report.total_ms is not None
        assert report.total_ms > 0
        assert abs(report.total_ms - expected["total_ms"]) < 1e-9, (
            f"{row['request_id']}: total {report.total_ms}ms != "
            f"supplied {expected['total_ms']}ms"
        )
        # Each row reconciles within tolerance (platform is accounted, not
        # leaked into the generic residual).
        assert report.reconciliation_ms is not None
        assert abs(report.reconciliation_ms) <= max(50.0, report.total_ms * 0.005), (
            f"{row['request_id']}: reconciliation {report.reconciliation_ms}ms "
            f"exceeds tolerance for total {report.total_ms}ms"
        )

        # Platform row: request-matched, derived exactly, group=platform.
        platform = stages["modal_scheduling"]
        assert platform.duration_ms is not None
        assert abs(platform.duration_ms - expected_platform) < 1e-9
        assert platform.status == "derived"
        assert platform.group == "platform"
        assert platform.source_fields == (
            "dispatch_to_modal_entry_ms",
            "restore_total_ms",
            "restore_end_to_modal_method_ms",
        )
        assert platform.included_in_total is True

        # Application restore is accounted exactly once: the restore stage is a
        # single row whose duration equals restore_total_ms.  The platform row
        # lists restore_total_ms among its source_fields (it is one of the
        # three derivation inputs) but SUBTRACTS it — restore is never
        # double-counted, which the within-tolerance reconciliation proves.
        restore_stages = [s for s in report.stages if s.key == "application_restore"]
        assert len(restore_stages) == 1, (
            f"{row['request_id']}: application_restore must be a single row, "
            f"got {len(restore_stages)}"
        )
        assert abs(restore_stages[0].duration_ms - restore_total) < 1e-9
        assert stages["restore_to_method_entry"].duration_ms is not None
        assert abs(stages["restore_to_method_entry"].duration_ms - restore_to_method) < 1e-9

        # Provider/region placement is preserved on the identity.
        assert stages and report.identity.get("cloud") == expected["cloud"]
        assert report.identity.get("region") == expected["region"]

        # Local handle lookup stays a separate row from the platform row.
        assert stages["modal_handle_submission"].duration_ms is not None
        assert stages["modal_handle_submission"].duration_ms > 0
        assert "dispatch_to_modal_entry_ms" not in stages["modal_handle_submission"].source_fields

        # Known platform time is never assigned to the generic residual.
        residual = stages.get("captured_timeline_gap")
        if residual is not None and residual.duration_ms is not None:
            assert abs(residual.duration_ms - expected_platform) > 1e-9


def test_baseline_rows_assert_exact_supplied_source_values():
    """The fixture rows are the verbatim supplied runs: total, dispatch,
    restore, restore-to-method, and placement are asserted exactly on the
    report stages, not derived from fixture self-consistency alone."""
    for row, expected in zip(BASELINE_ROWS, BASELINE_EXPECTED):
        report = _build_baseline_report(row)
        stages = {stage.key: stage for stage in report.stages}
        assert abs(report.total_ms - expected["total_ms"]) < 1e-9
        assert abs(stages["modal_scheduling"].duration_ms - expected["platform_ms"]) < 1e-9
        assert abs(stages["application_restore"].duration_ms - expected["restore_total_ms"]) < 1e-9
        assert abs(
            stages["restore_to_method_entry"].duration_ms - expected["restore_end_to_modal_method_ms"]
        ) < 1e-9
        # Exact supplied dispatch flows only through the derived platform row.
        assert abs(
            expected["dispatch_to_modal_entry_ms"]
            - expected["restore_total_ms"]
            - expected["restore_end_to_modal_method_ms"]
            - stages["modal_scheduling"].duration_ms
        ) < 1e-9


def test_baseline_negative_derived_platform_rejected():
    """A baseline row whose derived platform duration is negative is rejected
    explicitly (status=invalid + warning), never fabricated into a value or
    into the generic residual."""
    row = dict(BASELINE_ROWS[0])
    row["dispatch_to_modal_entry_ms"] = 27096.038
    row["restore_total_ms"] = 30000.0  # makes dispatch - restore - method < 0
    row["restore_end_to_modal_method_ms"] = 104.897
    report = _build_baseline_report(row)
    stage = next(item for item in report.stages if item.key == "modal_scheduling")
    assert stage.status == "invalid"
    assert stage.duration_ms is None
    assert any("negative" in warning for warning in report.warnings)
    # The rejected value is not re-used as a fabricated positive value anywhere.
    assert all(
        abs(s.duration_ms - (row["dispatch_to_modal_entry_ms"] - row["restore_total_ms"] - row["restore_end_to_modal_method_ms"])) > 1e-9
        for s in report.stages
        if s.duration_ms is not None
    )


# ═══════════════════════════════════════════════════════════════════════
# Step 3 seed-detail fallback + cross-process return-stage guards
# ═══════════════════════════════════════════════════════════════════════


def _seed_result(events):
    return {"request_id": "seed-detail", "trace": {"events": events}}


def test_seed_validate_detail_measured_from_boundary_pair():
    """When both snapshot seed validate start/end events exist on the remote
    process, the validate detail is MEASURED from the monotonic pair — the
    authoritative metadata is only the fallback."""
    events = [
        _event("snapshot_graph_seed_validate_start", 1000, 1000, "remote", budget_ms=25),
        _event("snapshot_graph_seed_validate_end", 1001, 1100, "remote", decision="match", schema=2),
        _event("snapshot_graph_seed_apply_start", 1001, 1100, "remote", decision="match", schema=2),
        _event("snapshot_graph_seed_apply_end", 1002, 1150, "remote",
               decision="match", schema=2,
               validate_ms=0.4, apply_ms=0.03, total_ms=0.47),
    ]
    report = build_waterfall(result=_seed_result(events), timing={}, wall_ms=1000)
    details = {detail.key: detail for detail in report.details}
    validate = details["snapshot_graph_seed_validate"]
    assert validate.duration_ms == 100.0        # (1100 - 1000)ms monotonic
    assert validate.status == "measured"
    assert validate.clock_scope == "monotonic:remote"
    assert validate.source_fields == ("snapshot_graph_seed_validate_start", "snapshot_graph_seed_validate_end")
    apply_detail = details["snapshot_graph_seed_apply"]
    assert apply_detail.duration_ms == 50.0     # (1150 - 1100)ms monotonic
    assert apply_detail.status == "measured"
    # Detail rows stay excluded from the accounted total.
    assert all(detail.included_in_total is False for detail in report.details)


def test_seed_validate_detail_falls_back_to_apply_end_metadata():
    """snapshot_graph_seed_validate_end carries only the decision, so when the
    validate start event is missing the validate duration is DERIVED from the
    authoritative apply-end metadata (validate_ms) instead of 'unavailable'."""
    events = [
        _event("snapshot_graph_seed_validate_end", 1000, 1000, "remote", decision="match", schema=2),
        _event("snapshot_graph_seed_apply_end", 1001, 1001, "remote",
               decision="match", schema=2,
               validate_ms=0.394, apply_ms=0.029, total_ms=0.471),
    ]
    report = build_waterfall(result=_seed_result(events), timing={}, wall_ms=1000)
    details = {detail.key: detail for detail in report.details}
    validate = details["snapshot_graph_seed_validate"]
    assert validate.duration_ms == 0.394
    assert validate.status == "derived"
    assert validate.source_fields == ("validate_ms",)
    apply_detail = details["snapshot_graph_seed_apply"]
    # apply_ms is preferred; total_ms is the broader fallback only.
    assert apply_detail.duration_ms == 0.029
    assert apply_detail.status == "derived"
    assert apply_detail.source_fields == ("apply_ms",)


def test_seed_apply_detail_falls_back_to_total_ms():
    """When apply_ms is absent the apply detail preserves the authoritative
    total_ms rather than becoming unavailable."""
    events = [
        _event("snapshot_graph_seed_apply_end", 1001, 1001, "remote",
               decision="match", schema=2, validate_ms=0.4, total_ms=0.47),
    ]
    report = build_waterfall(result=_seed_result(events), timing={}, wall_ms=1000)
    apply_detail = next(d for d in report.details if d.key == "snapshot_graph_seed_apply")
    assert apply_detail.duration_ms == 0.47
    assert apply_detail.status == "derived"
    assert apply_detail.source_fields == ("total_ms",)


def test_seed_validate_detail_falls_back_to_executor_seed_apply_marker():
    """executor_seed_apply_end.seed_apply.validate_ms is the authoritative Step 3
    fallback when the snapshot-graph events are entirely absent."""
    events = [{
        "name": "executor_seed_apply_end",
        "process": "remote",
        "wall_unix_ns": 0,
        "monotonic_ns": 0,
        "metadata": {
            "seed_apply": {
                "decision": "match", "schema": 2,
                "validate_ms": 0.394, "apply_ms": 0.029, "total_ms": 0.471,
            },
        },
    }]
    report = build_waterfall(result=_seed_result(events), timing={}, wall_ms=1000)
    details = {detail.key: detail for detail in report.details}
    validate = details["snapshot_graph_seed_validate"]
    assert validate.duration_ms == 0.394
    assert validate.status == "derived"
    assert validate.source_fields == ("executor_seed_apply_end.seed_apply.validate_ms",)
    apply_detail = details["snapshot_graph_seed_apply"]
    assert apply_detail.duration_ms == 0.029
    assert apply_detail.source_fields == ("executor_seed_apply_end.seed_apply.apply_ms",)


def test_cross_process_clock_skew_return_stages_unavailable_not_negative():
    """Mirrors the production three-run artifact: the local wall clock runs
    ~0.6s behind the remote clock, so remote output_collect_end appears after
    the local final_result_received.  The remote_return_handoff (cross-process
    wall) must be unavailable/derived — never a negative measured duration and
    never subtracted into reconciliation.  The local return hop is the same
    instant (~0ms), not a fabricated negative."""
    events = [
        _event("output_persist_start", 11600, 7600, "remote"),
        _event("output_persist_end", 12300, 8300, "remote"),
        _event("output_collect_start", 12301, 8301, "remote"),
        _event("output_collect_end", 12302, 8302, "remote"),
        # Local clock is behind: the local receive wall time is EARLIER than
        # the remote completion wall time, which is impossible on one clock.
        _event("remote_return_start", 12200, 12200, "local"),
        _event("final_result_received", 12200, 12201, "local"),
    ]
    report = build_waterfall(
        result=_seed_result(events),
        timing={},
        wall_ms=2000,
        command_start_unix_ms=10000,
        response_received_unix_ns=12200 * 1_000_000,
    )
    stages = {stage.key: stage for stage in report.stages}
    for key in ("remote_return_handoff", "remote_local_return"):
        stage = stages[key]
        assert stage.status != "invalid"
        assert stage.duration_ms is None or stage.duration_ms >= 0
    # The cross-process handoff span is unreliable under clock skew: it must
    # not be reported as a measured (negative or absurd) value.
    assert stages["remote_return_handoff"].duration_ms is None
    # No phantom negative duration warnings for the skewed return segments.
    assert not any("negative duration" in warning for warning in report.warnings)


def test_return_stages_measure_with_valid_response_boundaries():
    """With a trace that has valid (same-clock) response boundaries, the return
    stages are measured non-negative instead of being dropped as unavailable,
    and reconciliation is still reported."""
    events = [
        _event("output_persist_start", 11600, 7600, "remote"),
        _event("output_persist_end", 12300, 8300, "remote"),
        _event("output_collect_end", 12350, 8350, "remote"),
        _event("remote_return_start", 13100, 13100, "local"),
        _event("final_result_received", 13100, 13101, "local"),
    ]
    report = build_waterfall(
        result=_seed_result(events),
        timing={},
        wall_ms=15000,
        command_start_unix_ms=1000,
        response_received_unix_ns=13100 * 1_000_000,
    )
    stages = {stage.key: stage for stage in report.stages}
    handoff = stages["remote_return_handoff"]
    assert handoff.status != "invalid"
    assert handoff.duration_ms is None or handoff.duration_ms >= 0
    ret = stages["remote_local_return"]
    assert ret.duration_ms is not None and ret.duration_ms >= 0
    assert ret.status != "invalid"
    assert report.reconciliation_ms is not None
    assert not any("negative duration" in warning for warning in report.warnings)
