from __future__ import annotations

import json
import os
import sys
import inspect
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from comfymodal_runtime.phase2_audit_control import (
    CONTROL_OPERATION_TIMEOUT_SECONDS,
    INTEGRATED_ARM,
    SOURCE_CAPACITY,
    SOURCE_ONLY_ARM,
    build_source_only_matrix_plan,
    build_source_only_matrix_schedule,
    STAGING_BUFFER_ALLOCATION_IDENTITY,
    _decoupled_environment,
    _run_source_only,
    _run_integrated,
    build_plan,
    build_schedule,
    classify_artifact,
    control_identity,
    run_phase2_audit_request,
    summarize_artifacts,
    validate_artifact,
)
from comfymodal_runtime.preplanned_extent_transport import (
    PreplannedExtentTransport,
    plan_preplanned_extents,
)

pytestmark = pytest.mark.fast_unit


def test_source_only_shared_path_has_no_dispatcher_and_releases_on_source_completion():
    data = b"0123456789abcdef"
    transport = PreplannedExtentTransport(
        source_qd=2,
        source_block_bytes=4,
        h2d_copy_bytes=8,
        h2d_inflight_depth=2,
        source_capacity=2,
        buffers=[bytearray(8), bytearray(8)],
    )
    result = transport.execute_source_only(
        plan_preplanned_extents(len(data), 4, 8),
        lambda offset, length: data[offset : offset + min(3, length)],
        total_bytes=len(data),
    )
    telemetry = result["telemetry"]
    assert telemetry["execution_mode"] == "source_only"
    assert telemetry["h2d_dispatcher_started"] is False
    assert telemetry["h2d_dispatcher_participation"] is False
    assert telemetry["h2d_copy_count"] == 0
    assert all(item["returned_bytes"] <= item["requested_bytes"] for item in telemetry["physical_reads"])
    assert telemetry["source_returned_bytes"] == len(data)


def test_phase2_schedule_is_exactly_24_and_arm_interleaved():
    schedule = build_schedule()
    assert len(schedule) == 24
    assert schedule[0]["geometry_id"] == "clip_b256_qd2"
    assert [row["arm"] for row in schedule[:4]] == [
        SOURCE_ONLY_ARM, INTEGRATED_ARM, SOURCE_ONLY_ARM, INTEGRATED_ARM,
    ]
    assert schedule[-1]["geometry_id"] == "unet_b256_qd8"
    assert {row["repetition"] for row in schedule} == {1, 2, 3}
    assert len({row["attempt_id"] for row in schedule}) == 24


def test_source_only_matrix_schedule_is_96_fresh_serial_requests():
    schedule = build_source_only_matrix_schedule()

    assert len(schedule) == 96
    assert {row["role"] for row in schedule} == {"clip", "unet"}
    assert {row["block_mib"] for row in schedule} == {32, 64, 128, 256}
    assert {row["qd"] for row in schedule} == {1, 2, 4, 8}
    assert {row["repetition"] for row in schedule} == {1, 2, 3}
    assert {row["arm"] for row in schedule} == {SOURCE_ONLY_ARM}
    assert all(row["serial"] is True for row in schedule)
    assert len({row["attempt_id"] for row in schedule}) == 96
    assert all(
        row["attempt_id"] == f"{row['geometry_id']}_{SOURCE_ONLY_ARM}_R{row['repetition']}"
        for row in schedule
    )


def test_source_only_matrix_plan_uses_existing_endpoint_without_deploy():
    plan = build_source_only_matrix_plan()

    assert plan["mode"] == "source-only-matrix"
    assert plan["request_count"] == 96
    assert plan["cell_count"] == 32
    assert plan["eligible_runs_per_cell"] == 3
    assert "modal deploy" not in plan["remote_command"]
    assert "--mode source-only-matrix" in plan["remote_command"]


def test_endpoint_accepts_full_matrix_only_for_source_only_arm(tmp_path):
    source_only = run_phase2_audit_request(
        "clip",
        "qwen_3_4b.safetensors",
        SOURCE_ONLY_ARM,
        1,
        32 * 1024 * 1024,
        "matrix-fixture",
        models_root=tmp_path,
    )
    integrated = run_phase2_audit_request(
        "clip",
        "qwen_3_4b.safetensors",
        "decoupled_integrated_control",
        1,
        32 * 1024 * 1024,
        "integrated-fixture",
        models_root=tmp_path,
    )

    assert source_only["classification"] == "FAILED"
    assert "FileNotFoundError" in source_only["error"]
    assert integrated["classification"] == "INVALID"


def test_runner_mode_paths_are_deterministic_without_changing_control_defaults():
    import tools.phase2_audit_control as runner

    matrix_out, matrix_state = runner._paths(Namespace(), "source-only-matrix")
    control_out, control_state = runner._paths(Namespace(), "control")

    assert matrix_out == Path("phase2_source_only_matrix_runs")
    assert matrix_state == Path("phase2_source_only_matrix_runs/ledger.json")
    assert control_out == Path("phase2_audit_runs")
    assert control_state == Path("phase2_audit_runs/ledger.json")


def test_plan_has_exact_control_identity_and_is_zero_spend():
    plan = build_plan()
    assert plan["request_count"] == 24
    assert plan["remote_calls"] is False
    assert plan["deployment"] is False
    assert plan["identity"] == control_identity()
    assert plan["identity"]["phase_3_status"] == "stopped"
    assert plan["identity"]["models_mount_read_only"] is True


def test_control_transport_timeout_is_explicitly_bounded_and_recorded():
    assert CONTROL_OPERATION_TIMEOUT_SECONDS > 1.0
    identity = control_identity()
    assert identity["control_operation_timeout_seconds"] == CONTROL_OPERATION_TIMEOUT_SECONDS
    assert identity["transport_cleanup_timeout_seconds"] == CONTROL_OPERATION_TIMEOUT_SECONDS

    plan = build_plan()
    assert plan["identity"]["control_operation_timeout_seconds"] == CONTROL_OPERATION_TIMEOUT_SECONDS


def test_source_control_records_timeout_and_transport_rejects_invalid_deadlines(tmp_path):
    header = json.dumps({
        "tensor": {"dtype": "U8", "shape": [4], "data_offsets": [0, 4]},
    }, separators=(",", ":")).encode("utf-8")
    path = tmp_path / "control.safetensors"
    path.write_bytes(len(header).to_bytes(8, "little") + header + b"data")

    result = _run_source_only(
        path, role="clip", qd=2, block_bytes=4, attempt_id="timeout-control",
    )
    assert result["transport_telemetry"]["control_operation_timeout_seconds"] == CONTROL_OPERATION_TIMEOUT_SECONDS
    assert result["transport_telemetry"]["transport_cleanup_timeout_seconds"] == CONTROL_OPERATION_TIMEOUT_SECONDS
    assert result["control_operation_timeout_seconds"] == CONTROL_OPERATION_TIMEOUT_SECONDS

    with pytest.raises(ValueError, match="cleanup_timeout must be positive"):
        PreplannedExtentTransport(
            source_qd=1,
            source_block_bytes=1,
            h2d_copy_bytes=1,
            h2d_inflight_depth=1,
            source_capacity=1,
            cleanup_timeout=0,
        )


def test_source_only_control_delegates_physical_read_to_golden_serial_helper(tmp_path, monkeypatch):
    header = json.dumps({
        "tensor": {"dtype": "U8", "shape": [8], "data_offsets": [0, 8]},
    }, separators=(",", ":")).encode("utf-8")
    path = tmp_path / "shared-reader.safetensors"
    path.write_bytes(len(header).to_bytes(8, "little") + header + b"12345678")

    import comfymodal_runtime.golden_serial as golden_serial

    calls = []
    original = golden_serial._read_at

    def read_at(*args, **kwargs):
        calls.append((args[0], args[2]))
        return original(*args, **kwargs)

    monkeypatch.setattr(golden_serial, "_read_at", read_at)
    result = _run_source_only(
        path, role="clip", qd=2, block_bytes=4, attempt_id="shared-reader",
    )

    assert result["status"] == "ok"
    assert calls
    assert result["physical_read_provenance"] == "golden_serial._read_at"
    assert "preadv" not in inspect.getsource(
        __import__("comfymodal_runtime.phase2_audit_control", fromlist=["_PositionedReader"])._PositionedReader
    )


def test_source_only_control_uses_integrated_pinned_staging_contract(tmp_path):
    header = json.dumps({
        "tensor": {"dtype": "U8", "shape": [8], "data_offsets": [0, 8]},
    }, separators=(",", ":")).encode("utf-8")
    path = tmp_path / "pinned-staging.safetensors"
    path.write_bytes(len(header).to_bytes(8, "little") + header + b"12345678")

    result = _run_source_only(
        path, role="clip", qd=2, block_bytes=4, attempt_id="pinned-staging",
    )

    staging = result["staging_buffer"]
    assert staging == {
        "kind": "torch_cpu_uint8_pinned_contiguous_arena",
        "dtype": "torch.uint8",
        "device": "cpu",
        "pinned": True,
        "contiguous": True,
        "shape": [8],
        "extent_shape": [4],
        "extent_count": 2,
        "arena_bytes": 8,
        "physical_allocation_count": 1,
        "allocation_identity": STAGING_BUFFER_ALLOCATION_IDENTITY,
    }
    telemetry = result["transport_telemetry"]
    assert telemetry["staging_buffer"] == staging
    assert telemetry["staging_buffer_kind"] == staging["kind"]
    assert telemetry["staging_buffer_shape"] == staging["shape"]
    assert telemetry["staging_buffer_extent_shape"] == staging["extent_shape"]
    assert telemetry["staging_buffer_pinned"] is True
    assert telemetry["staging_buffer_allocation_count"] == 1
    assert result["staging_buffer_arena_bytes"] == 8
    assert result["staging_buffer_physical_allocation_count"] == 1
    valid, failures = validate_artifact(result, {
        "attempt_id": "pinned-staging",
        "role": "clip",
        "model_name": path.name,
        "arm": SOURCE_ONLY_ARM,
        "qd": 2,
        "block_bytes": 4,
        "source_qd": 2,
        "source_capacity": SOURCE_CAPACITY,
    })
    assert valid is True, failures
    assert result["strict_e27_proof"]["proven"] is True
    assert result["strict_e27_proof"]["predicates"]["pinned_cpu_uint8_staging"] is True
    assert result["strict_e27_proof"]["predicates"]["staging_buffer_geometry"] is True
    assert result["strict_e27_proof"]["predicates"]["shared_positioned_read_helper"] is True
    assert result["strict_e27_proof"]["predicates"]["writable_byte_view_contract"] is True
    assert telemetry["h2d_dispatcher_started"] is False
    assert telemetry["h2d_dispatcher_participation"] is False
    assert telemetry["h2d_copy_count"] == 0
    assert telemetry["h2d_submitted_bytes"] == telemetry["h2d_completed_bytes"] == 0


def test_integrated_control_retains_golden_serial_physical_read_provenance(tmp_path, monkeypatch):
    path = tmp_path / "integrated-reader.safetensors"
    path.write_bytes(b"fixture")
    physical = [{
        "source_offset": 8,
        "destination_offset": 0,
        "requested_bytes": 8,
        "returned_bytes": 8,
    }]
    fake = {
        "owner": None,
        "stats": {
            "source_base": 8,
            "file_bytes": 8,
            "actual_source": {
                "actual_source_events": physical,
                "physical_syscall_provenance": "golden_serial._read_at",
                "h2d_submitted_bytes": 8,
                "h2d_completed_bytes": 8,
            },
            "pipeline_telemetry": {
                "source_worker_timing": {"0": {"joined": True}},
                "configured_source_capacity": SOURCE_CAPACITY,
                "physical_read_provenance": "golden_serial._read_at",
            },
            "pinned_bytes": 8,
            "pinned_arena_physical_allocation_count": 1,
        },
    }
    import comfymodal_runtime.golden_serial as golden_serial
    calls = {}

    def read_file_qd_gpu(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return fake

    monkeypatch.setattr(golden_serial, "read_file_qd_gpu", read_file_qd_gpu)

    result = _run_integrated(
        path, role="clip", qd=2, block_bytes=4, attempt_id="integrated-reader",
    )

    assert result["physical_read_provenance"] == "golden_serial._read_at"
    assert result["physical_syscall_provenance"] == "golden_serial._read_at"
    assert result["physical_read_telemetry"][0]["requested_bytes"] == 8
    assert result["physical_read_telemetry"][0]["returned_bytes"] == 8
    assert result["status"] == "ok"
    assert result["strict_e27_proof"]["proven"] is True
    assert result["staging_buffer"]["kind"] == "torch_cpu_uint8_pinned_contiguous_arena"
    assert result["staging_buffer"]["shape"] == [8]
    assert result["staging_buffer"]["extent_shape"] == [4]
    assert result["staging_buffer"]["extent_count"] == 2
    assert result["staging_buffer"]["allocation_identity"] == STAGING_BUFFER_ALLOCATION_IDENTITY
    assert result["staging_buffer"] == result["transport_telemetry"].get("staging_buffer", result["staging_buffer"])
    assert calls["kwargs"] == {
        "role": "clip",
        "device": "cuda:0",
        "qd": 2,
        "block_bytes": 4,
        "diagnostics": True,
        "transport_arm": "decoupled",
    }


def test_proof_no_is_fail_closed():
    expected = {
        "attempt_id": "a", "role": "clip", "model_name": "m.safetensors",
        "arm": SOURCE_ONLY_ARM, "qd": 2, "block_bytes": 256 * 1024 * 1024,
    }
    artifact = {
        **expected,
        "status": "ok",
        "classification": "proof-NO",
        "strict_e27_proof": {"strict": True, "proven": False, "classification": "proof-NO"},
        "physical_syscall_telemetry": [{"requested_bytes": 8, "returned_bytes": 8}],
        "payload_reconciliation": {"ok": True},
    }
    assert classify_artifact(artifact, expected) == "proof-NO"
    valid, failures = validate_artifact(artifact, expected)
    assert valid is False
    assert "strict_e27_proof_NO" in failures


def test_report_reads_only_explicit_artifacts_and_keeps_byte_counts(tmp_path):
    path = tmp_path / "run.json"
    path.write_text(json.dumps({
        "attempt_id": "a", "role": "clip", "arm": SOURCE_ONLY_ARM,
        "qd": 2, "block_bytes": 256 * 1024 * 1024, "status": "ok",
        "classification": "ELIGIBLE", "SOURCE_WALL_MS": 12.5,
        "payload_reconciliation": {"requested_bytes": 12, "returned_bytes": 10},
        "strict_e27_proof": {"classification": "PROVEN", "proven": True},
        "identity": {"provider": "p", "region": "r"},
    }), encoding="utf-8")
    report = summarize_artifacts([path])
    assert report["artifact_count"] == 1
    assert report["rows"][0]["requested_bytes"] == 12
    assert report["rows"][0]["returned_bytes"] == 10


def test_source_capacity_is_fixed_independently_of_source_qd():
    for qd in (2, 8):
        with _decoupled_environment(qd, 256 * 1024 * 1024):
            assert os.environ["COMFYMODAL_GOLDEN_SOURCE_QD"] == str(qd)
            assert os.environ["COMFYMODAL_GOLDEN_SOURCE_CAPACITY"] == str(SOURCE_CAPACITY)


def test_remote_runner_binds_active_workspace_client_and_environment(monkeypatch, tmp_path):
    import tools.phase2_audit_control as runner

    workspace = {
        "id": "testing7",
        "token_id": "ak-test-redacted",
        "token_secret": "as-test-redacted",
        "environment": "testing7",
    }
    monkeypatch.setattr(runner, "_load_active_workspace", lambda: workspace)
    monkeypatch.setenv("MODAL_TOKEN_ID", "old-id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "old-secret")
    calls = {}

    class FakeClient:
        @classmethod
        def from_credentials(cls, token_id, token_secret):
            calls["credentials"] = (token_id, token_secret)
            return cls()

    class FakeFunction:
        @classmethod
        def from_name(cls, app, name, **kwargs):
            calls["function"] = (app, name, kwargs)
            return cls()

        def remote(self, *args):
            return {"status": "error", "classification": "FAILED", "error": "fixture"}

    monkeypatch.setitem(sys.modules, "modal", SimpleNamespace(Client=FakeClient, Function=FakeFunction))
    args = Namespace(
        app="phase2-test",
        out_dir=str(tmp_path / "artifacts"),
        state=str(tmp_path / "ledger.json"),
    )
    assert runner._execute_remote(args) == 0
    assert calls["credentials"] == (workspace["token_id"], workspace["token_secret"])
    app, name, options = calls["function"]
    assert (app, name) == ("phase2-test", "run_phase2_audit")
    assert options["client"] is not None
    assert options["environment_name"] == "testing7"
    assert os.environ["MODAL_TOKEN_ID"] == workspace["token_id"]
    assert os.environ["MODAL_TOKEN_SECRET"] == workspace["token_secret"]


def test_remote_runner_source_only_matrix_is_bounded_and_fresh(monkeypatch, tmp_path):
    import tools.phase2_audit_control as runner

    workspace = {
        "id": "testing7",
        "token_id": "ak-test-redacted",
        "token_secret": "as-test-redacted",
        "environment": "testing7",
    }
    monkeypatch.setattr(runner, "_load_active_workspace", lambda: workspace)
    calls = []

    class FakeClient:
        @classmethod
        def from_credentials(cls, token_id, token_secret):
            return cls()

    class FakeFunction:
        @classmethod
        def from_name(cls, app, name, **kwargs):
            return cls()

        def remote(self, *args):
            calls.append(args)
            return {"status": "error", "classification": "FAILED", "error": "fixture"}

    monkeypatch.setitem(sys.modules, "modal", SimpleNamespace(Client=FakeClient, Function=FakeFunction))
    out_dir = tmp_path / "matrix-artifacts"
    state = tmp_path / "matrix-ledger.json"
    args = Namespace(
        mode="source-only-matrix",
        app="phase2-test",
        out_dir=str(out_dir),
        state=str(state),
    )

    assert runner._execute_remote(args) == 0
    assert len(calls) == 96
    assert all(call[2] == SOURCE_ONLY_ARM for call in calls)
    assert calls[0][0:2] == ("clip", "qwen_3_4b.safetensors")
    assert calls[-1][0:2] == ("unet", "z_image_turbo_bf16.safetensors")
    ledger = json.loads(state.read_text(encoding="utf-8"))
    assert ledger["mode"] == "source-only-matrix"
    assert ledger["request_count"] == 96
    assert ledger["fresh_serial_requests"] is True
    assert len(ledger["attempts"]) == 96
