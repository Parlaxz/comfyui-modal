"""Synthetic P2-3 contracts for the offline Golden observability harness."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from tools import golden_observability as go


SHA = "a" * 64


def artifact(*, instance: str = "container-1", profiler_total: float = 999999.0,
             proof: dict | None = None, qd: bool = False,
             stage_duration_ns: int = 100) -> dict:
    stages = []
    cursor = 1_000_000_000
    for name in go.STAGE_ORDER + (go.TEARDOWN_STAGE,):
        stages.append({"name": name, "entry_wall_ns": cursor,
                       "end_wall_ns": cursor + stage_duration_ns,
                       "ok": True, "ready_monotonic_ns": cursor + stage_duration_ns})
        cursor += 200
    events = [
        {"name": "output_encoded", "wall_ns": 1_000_002_310,
         "fields": {"sha256": SHA}},
        {"name": "file_written", "wall_ns": 1_000_002_320,
         "fields": {"sha256": SHA}},
        {"name": "volume_commit_start", "wall_ns": 1_000_002_330, "fields": {}},
        {"name": "volume_commit_complete", "wall_ns": 1_000_002_340, "fields": {}},
        {"name": "durable_reopen_verified", "wall_ns": 1_000_002_350,
         "fields": {"ok": True, "sha256": SHA, "byte_count": 12}},
        {"name": "true_first_durable_result", "wall_ns": 1_000_002_360,
         "fields": {"sha256": SHA}},
        {"name": "RESULT_ASSEMBLED", "wall_ns": 1_000_002_365, "fields": {}},
        {"name": "TEARDOWN_COMPLETE", "wall_ns": 1_000_002_550, "fields": {}},
        {"name": "remote_return", "wall_ns": 1_000_002_560, "fields": {}},
        {"name": "client_receipt", "wall_ns": 1_000_002_570, "fields": {}},
    ]
    if qd:
        events.append({"name": "qd_child_worker_0", "wall_ns": 1_000_000_050})
    return {
        "attempt_number": 1,
        "output_sha": SHA,
        "profiler_totals": {"duration_ms": profiler_total, "output_sha": "wrong"},
        "identity": {
            "deployment_combined_hash": "deploy-hash", "combined_hash": "source-hash",
            "snapshot_id": "snap-1", "workflow_sha256": "workflow-hash",
            "clip_name": go.CANONICAL_CLIP_NAME, "unet_name": go.CANONICAL_UNET_NAME,
            "vae_name": go.CANONICAL_VAE_NAME, "gpu": "gpu-a", "profile": "golden_p1",
            "fresh": "Fresh:YES", "instance_id": instance, "config_hash": "config-hash",
        },
        "identity_frozen": True,
        "snapshot_proof": proof or {
            "roles": {
                "clip": {"model_bytes": 0},
                "unet": {"model_bytes": 0},
                "vae": {"model_bytes": 0},
            },
            "qd_owner_count": 0, "qd_reader_count": 0,
            "model_preload_worker_count": 0, "future_count": 0,
            "pre_capture": {"status": "PASS"},
        },
        "execution": {
            "fallback": {"pin_fallback": 0, "alignment_tensor_count": 0},
            "source_lifecycle_by_model": {
                "clip": {"count": 1}, "unet": {"count": 1}, "vae": {"count": 1},
            },
            "stage_boundary_quiescence": {
                stage: {"unresolved_worker_count": 0, "futures_at_boundary": 0}
                for stage in go.PRIMARY_STAGE_ORDER + (go.TEARDOWN_STAGE,)
            },
            "duplicate_model_sized_h2d": 0,
            "real_clip_forward": True,
        },
        "telemetry": {"schema": "golden_p1_telemetry_v1", "stages": stages,
                       "events": events, "seriality": {"ok": True, "count": 0},
                       "telemetry_persistence": {"telemetry_persisted": True},
                       "external_restore": {
                           "restore_method_start_wall_unix_ns": 999_999_800,
                           "restore_method_end_wall_unix_ns": 999_999_900,
                       }},
        "boundaries": {
            "command_start": 900_000_000, "python_resume": 950_000_000,
            "process_exit": 4_000_000_090,
        },
        "raw_log_ref": "raw.log",
    }


def expected() -> dict:
    return {"deployment_hash": "deploy-hash", "source_hash": "source-hash",
            "snapshot_id": "snap-1", "workflow_sha256": "workflow-hash", "output_sha256": SHA,
            "gpu": "gpu-a", "profile": "golden_p1"}


def test_golden_walls_are_authoritative_and_profiler_is_ignored():
    result = go.validate_attempt(artifact(), expected())
    assert result.valid
    assert tuple(result.stage_walls) == go.PRIMARY_STAGE_ORDER
    assert result.stage_walls["actual_restore"].duration_ms == pytest.approx(0.0001)
    assert result.metrics["golden_stage_sum_ms"] == pytest.approx(0.0012)
    assert result.metrics.get("duration_ms") is None


def test_exact_wall_extraction_normalizes_restore_without_using_profiler_fields():
    walls = go.extract_exact_stage_walls(artifact(profiler_total=1.0))
    assert walls["actual_restore"].entry_ns == 999_999_800
    assert walls["actual_restore"].end_ns == 999_999_900
    assert "golden_restore" not in walls
    assert walls["golden_clip_load"].entry_ns == 1_000_000_400


def test_primary_function_table_has_exact_order_and_golden_wall_durations():
    result = go.validate_attempt(artifact(profiler_total=1.0), expected())
    rows = go.primary_function_table(result)
    assert [row["function"] for row in rows] == [
        "actual_restore", "golden_request_setup()", "golden_clip_load()",
        "golden_clip_forward()", "golden_unet_load()", "golden_sampler_prepare()",
        "golden_vae_load()", "golden_sampling()", "golden_sampler_tail()",
        "golden_vae_decode()", "golden_output()", "golden_durable_commit()",
        "golden_teardown()",
    ]
    assert all(row["wall_ms"] == pytest.approx(0.0001) for row in rows)
    assert go.render_primary_function_table(result).splitlines()[2].startswith("actual_restore")
    result.artifact["profiler_totals"]["duration_ms"] = 123456.0
    assert go.primary_function_table(result)[0]["wall_ms"] == pytest.approx(0.0001)


def test_boundaries_are_distinct_and_gantt_uses_solid_blocks_without_fake_qd():
    result = go.validate_attempt(artifact(), expected())
    assert set(result.boundaries) == set(go.BOUNDARY_NAMES)
    gantt = go.render_golden_gantt(result, width=30)
    assert go.GANTT_BLOCK in gantt
    assert "QD child detail" not in gantt
    with_qd = go.validate_attempt(artifact(qd=True), expected())
    assert "QD child detail" in go.render_golden_gantt(with_qd)


def test_gantt_scales_wall_timestamps_and_uses_only_solid_blocks():
    result = go.validate_attempt(artifact(), expected())
    lines = go.render_golden_gantt(result, width=30).splitlines()
    request = next(line for line in lines if line.startswith("golden_request_setup"))
    restore = next(line for line in lines if line.startswith("actual_restore"))
    request_bar = request[29:]
    restore_bar = restore[29:]
    assert request_bar[2] == go.GANTT_BLOCK
    assert restore_bar[0] == go.GANTT_BLOCK
    assert set(request_bar) <= {" ", go.GANTT_BLOCK}
    assert set(restore_bar) <= {" ", go.GANTT_BLOCK}
    assert "#" not in "\n".join(lines)


def test_boundary_metrics_keep_every_transport_edge_distinct():
    result = go.validate_attempt(artifact(), expected())
    metrics = result.metrics
    assert metrics["command_start_to_python_resume_ms"] == pytest.approx(50.0)
    assert metrics["python_resume_to_true_first_durable_result_ms"] == pytest.approx(50.00236)
    assert metrics["true_first_durable_result_to_result_assembled_ms"] == pytest.approx(0.000005)
    assert metrics["result_assembled_to_teardown_complete_ms"] == pytest.approx(0.000185)
    assert metrics["teardown_complete_to_remote_return_ms"] == pytest.approx(0.00001)
    assert metrics["true_first_durable_result_to_remote_return_ms"] == pytest.approx(0.0002)
    assert metrics["remote_return_to_client_receipt_ms"] == pytest.approx(0.00001)
    assert metrics["command_start_to_client_receipt_ms"] == pytest.approx(100.00257)
    assert metrics["true_first_durable_result_to_client_receipt_ms"] == pytest.approx(0.00021)
    assert metrics["post_durable_tail_ms"] == metrics["true_first_durable_result_to_remote_return_ms"]
    assert metrics["post_durable_tail_ms"] != metrics["true_first_durable_result_to_client_receipt_ms"]


def test_generic_result_does_not_prove_remote_return():
    bad = artifact()
    bad["telemetry"]["events"] = [
        event for event in bad["telemetry"]["events"] if event["name"] != "remote_return"
    ]
    bad["telemetry"]["events"].append({"name": "result", "wall_ns": 4_000_000_070})
    assert "remote_return" not in go.extract_boundaries(bad)
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert "boundary missing remote_return" in result.reasons


@pytest.mark.parametrize("alias", ["output_branch_executed", "output_assembled"])
def test_result_assembled_requires_explicit_semantic_event(alias: str):
    bad = artifact()
    bad["telemetry"]["events"] = [
        {**event, "name": alias}
        if event["name"] == "RESULT_ASSEMBLED" else event
        for event in bad["telemetry"]["events"]
    ]
    boundaries = go.extract_boundaries(bad)
    assert "result_assembled" not in boundaries
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert "boundary missing result_assembled" in result.reasons


def test_first_durable_result_alias_is_not_accepted():
    bad = artifact()
    bad["telemetry"]["events"] = [
        {**event, "name": "first_durable_result"}
        if event["name"] == "true_first_durable_result" else event
        for event in bad["telemetry"]["events"]
    ]
    assert "true_first_durable_result" not in go.extract_boundaries(bad)


def test_golden_restore_observation_cannot_supply_actual_restore_wall():
    bad = artifact()
    bad["telemetry"].pop("external_restore")
    with pytest.raises(ValueError, match="missing Golden stage intervals: actual_restore"):
        go.extract_stage_walls(bad)


def test_process_exit_is_optional_but_teardown_complete_and_persistence_are_not():
    good = artifact()
    good["boundaries"].pop("process_exit")
    assert go.validate_attempt(good, expected()).valid

    bad = artifact()
    bad["telemetry"]["events"] = [
        event for event in bad["telemetry"]["events"] if event["name"] != "TEARDOWN_COMPLETE"
    ]
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("TEARDOWN_COMPLETE" in reason for reason in result.reasons)

    bad = artifact()
    bad["telemetry"].pop("telemetry_persistence")
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("persistence" in reason for reason in result.reasons)


def test_actual_adapter_artifact_projects_terminal_and_restore_metadata_boundaries():
    actual = artifact()
    telemetry = actual.pop("telemetry")
    actual["golden_telemetry"] = telemetry
    telemetry["events"] = [
        event for event in telemetry["events"]
        if event["name"] not in {"remote_return", "client_receipt"}
    ]
    actual["boundaries"].pop("command_start")
    actual["boundaries"].pop("python_resume")
    actual["submission_wall_unix_ns"] = 900_000_000
    telemetry["external_restore"] = {
        "remote_python_resume_wall_unix_ns": 950_000_000,
    }
    actual["terminal"] = {
        "return_wall_unix_ns": 4_000_000_070,
        "yield_wall_unix_ns": 4_000_000_075,
    }
    actual["terminal_timing"] = dict(actual["terminal"])

    boundaries = go.extract_boundaries(actual)
    assert boundaries["remote_return"].timestamp_ns == 4_000_000_070
    assert boundaries["python_resume"].timestamp_ns == 950_000_000
    assert "client_receipt" not in boundaries

    result = go.validate_attempt(actual, expected())
    assert not result.valid
    assert "boundary missing client_receipt" in result.reasons


def test_serial_ordering_is_required_for_boundaries_and_stage_walls():
    bad = artifact()
    bad["boundaries"]["python_resume"] = 800_000_000
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("serial" in reason for reason in result.reasons)

    bad = artifact()
    stages = bad["telemetry"]["stages"]
    stages[2], stages[3] = stages[3], stages[2]
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("stage order" in reason for reason in result.reasons)


def test_snapshot_and_execution_proof_fail_closed():
    bad = artifact()
    bad["snapshot_proof"]["roles"]["clip"]["model_bytes"] = 1
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("model_bytes" in reason for reason in result.reasons)
    bad = artifact()
    bad["execution"]["source_lifecycle_by_model"].pop("unet")
    result = go.validate_attempt(bad, expected())
    assert any("source lifecycle" in reason for reason in result.reasons)


@pytest.mark.parametrize("field", ["fallback", "duplicate_model_sized_h2d"])
def test_fallback_and_duplicate_h2d_are_zero(field: str):
    bad = artifact()
    if field == "fallback":
        bad["execution"][field]["pin_fallback"] = 1
    else:
        bad["execution"][field] = 1
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("fallback" in reason or "H2D" in reason for reason in result.reasons)


@pytest.mark.parametrize("role", ["clip", "unet", "vae"])
def test_each_snapshot_model_role_is_required(role: str):
    bad = artifact()
    bad["snapshot_proof"]["roles"].pop(role)
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("model_bytes" in reason for reason in result.reasons)


def test_snapshot_pre_capture_and_all_zero_fields_are_explicit():
    bad = artifact()
    bad["snapshot_proof"].pop("pre_capture")
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("pre-capture PASS" in reason for reason in result.reasons)

@pytest.mark.parametrize("field, label", [
    ("qd_owner_count", "QD owners"),
    ("qd_reader_count", "QD readers"),
    ("model_preload_worker_count", "model preload workers"),
    ("future_count", "futures"),
])
def test_each_snapshot_zero_field_is_required(field: str, label: str):
    bad = artifact()
    bad["snapshot_proof"][field] = 1
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any(label in reason for reason in result.reasons)


@pytest.mark.parametrize("role", ["clip", "unet", "vae"])
def test_per_model_lifecycle_must_be_exactly_one(role: str):
    bad = artifact()
    bad["execution"]["source_lifecycle_by_model"][role]["count"] = 2
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any(role in reason and "lifecycle" in reason for reason in result.reasons)


def test_quiescence_is_required_at_every_stage_boundary():
    bad = artifact()
    bad["execution"]["stage_boundary_quiescence"].pop("golden_sampling")
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("quiescence" in reason for reason in result.reasons)

    bad = artifact()
    bad["execution"]["stage_boundary_quiescence"] = {"ok": True}
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("quiescence" in reason for reason in result.reasons)


def test_source_lifecycle_requires_direct_per_model_records():
    bad = artifact()
    bad["execution"]["source_lifecycle_by_model"] = {"ok": True}
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("source lifecycle" in reason for reason in result.reasons)


def test_real_clip_forward_must_be_explicitly_true():
    bad = artifact()
    bad["execution"]["real_clip_forward"] = False
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("CLIP forward" in reason for reason in result.reasons)


def test_durability_requires_commit_reopen_proof_before_first_durable():
    bad = artifact()
    next(event for event in bad["telemetry"]["events"]
         if event["name"] == "durable_reopen_verified")["fields"]["sha256"] = "b" * 64
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("reopen hash mismatch" in reason for reason in result.reasons)

    bad = artifact()
    next(event for event in bad["telemetry"]["events"]
         if event["name"] == "true_first_durable_result")["wall_ns"] = 1_000_002_345
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("TRUE_FIRST_DURABLE_RESULT precedes" in reason for reason in result.reasons)

    bad = artifact()
    next(event for event in bad["telemetry"]["events"]
         if event["name"] == "RESULT_ASSEMBLED")["wall_ns"] = 1_000_002_355
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("strict: true_first_durable_result < result_assembled" in reason
               for reason in result.reasons)

    bad = artifact()
    next(event for event in bad["telemetry"]["events"]
         if event["name"] == "TEARDOWN_COMPLETE")["wall_ns"] = 1_000_002_365
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("strict: result_assembled < teardown_complete" in reason
               for reason in result.reasons)


def test_invalid_attempt_keeps_phase_exception_and_raw_references():
    bad = artifact()
    bad["phase"] = "golden_clip_load"
    bad["exception"] = "RuntimeError: boom"
    bad["raw_artifact_refs"] = ["events.json"]
    bad["execution"]["duplicate_model_sized_h2d"] = 1
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert result.phase == "golden_clip_load"
    assert result.exception == "RuntimeError: boom"
    assert "events.json" in result.raw_artifact_refs
    assert any("duplicate model-sized" in reason for reason in result.reasons)


def test_five_run_stats_are_exactly_valid_runs_and_untrimmed():
    inputs = [artifact(instance=f"container-{i}", stage_duration_ns=100 + i * 10)
              for i in range(5)]
    cohort = go.build_five_run_cohort(inputs, expected())
    assert cohort.valid and len(cohort.valid_attempts) == 5
    stats = go.compute_stats([1, 2, 3, 4, 5])
    assert stats["n"] == 5
    assert stats["p90"] == pytest.approx(4.6)
    assert stats["min"] == 1 and stats["max"] == 5 and stats["range"] == 4
    assert stats["stdev"] == pytest.approx(math.sqrt(2.5))
    assert "no trimming" in stats["method"]
    assert cohort.stats["actual_restore"]["n"] == 5
    assert cohort.stats["remote_python_resume_to_true_first_durable_result_ms"]["n"] == 5
    assert cohort.stats["restore_ms"]["n"] == 5
    assert cohort.stats["post_durable_tail_ms"]["n"] == 5
    assert cohort.stats["command_to_result_ms"]["n"] == 5
    for name in (
        "command_start_to_python_resume_ms",
        "python_resume_to_true_first_durable_result_ms",
        "true_first_durable_result_to_remote_return_ms",
        "remote_return_to_client_receipt_ms",
        "command_start_to_client_receipt_ms",
        "true_first_durable_result_to_client_receipt_ms",
    ):
        assert cohort.stats[name]["n"] == 5


def test_fresh_yes_and_frozen_config_identity_are_cohort_requirements():
    assert artifact()["identity"]["fresh"] == "Fresh:YES"

    bad = artifact()
    bad["identity"]["fresh"] = "Fresh:NO"
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("Fresh:YES" in reason for reason in result.reasons)

    bad = artifact()
    bad["identity"].pop("config_hash")
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("config identity" in reason for reason in result.reasons)

    bad = artifact()
    bad["identity_frozen"] = False
    result = go.validate_attempt(bad, expected())
    assert not result.valid
    assert any("frozen identity proof" in reason for reason in result.reasons)

    inputs = [artifact(instance=f"container-{i}") for i in range(5)]
    inputs[4]["identity"]["config_hash"] = "different-config"
    cohort = go.build_five_run_cohort(inputs, expected())
    assert not cohort.valid
    assert any("frozen identity" in reason for reason in cohort.reasons)


def test_duplicate_fresh_instance_does_not_feed_cohort_stats():
    inputs = [artifact(instance=f"container-{i}") for i in range(4)] + [artifact(instance="container-3")]
    cohort = go.build_five_run_cohort(inputs, expected())
    assert not cohort.valid
    assert len(cohort.invalid_attempts) == 1
    assert not cohort.stats
    assert any("distinct instance" in reason for reason in cohort.reasons)


def test_report_regeneration_from_json_paths_is_json_serializable(tmp_path: Path):
    paths = []
    for i in range(5):
        path = tmp_path / f"attempt_{i}.json"
        path.write_text(json.dumps(artifact(instance=f"container-{i}")), encoding="utf-8")
        paths.append(path)
    report_path = tmp_path / "report.json"
    report = go.regenerate_report(paths, expected(), output_path=report_path)
    assert report["valid"] is True
    assert report_path.is_file()
    assert len(report["primary_function_tables"]) == 5
    assert report["attempts"][0]["primary_function_table"][0]["function"] == "actual_restore"
    assert len(report["gantt"]) == 5
    assert report["stats"]["remote_return_to_client_receipt_ms"]["n"] == 5
    json.dumps(report)


def test_source_preflight_refuses_arbitrary_changed_files(monkeypatch, tmp_path: Path):
    class Completed:
        returncode = 0
        stdout = " M unrelated.py\n?? arbitrary.txt\n"

    monkeypatch.setattr(go.subprocess, "run", lambda *args, **kwargs: Completed())
    result = go.preflight_source_tree(tmp_path)
    assert not result.ok
    assert result.changed_files == ("unrelated.py", "arbitrary.txt")
    assert "changed files" in result.reason
    report = go.run_structural(artifact(), expected(), source_root=tmp_path)
    assert report["valid"] is False
    assert report["reasons"][0].startswith("source preflight refused:")


def test_source_preflight_refuses_digest_mismatch_and_unverified_isolated_tree(
    monkeypatch, tmp_path: Path
):
    class Clean:
        returncode = 0
        stdout = ""

    monkeypatch.setattr(go.subprocess, "run", lambda *args, **kwargs: Clean())
    result = go.preflight_source_tree(tmp_path, expected_digest="0" * 64)
    assert not result.ok
    assert "digest mismatch" in result.reason

    result = go.preflight_source_tree(tmp_path, isolated_root=tmp_path)
    assert not result.ok
    assert "digest required" in result.reason
