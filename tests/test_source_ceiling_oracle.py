"""Focused tests for Experiment 04's fixed source-only contract."""

from __future__ import annotations

import asyncio
import json
import struct
from types import SimpleNamespace

from comfymodal_runtime import source_ceiling_oracle as oracle
from tools import run_exp04_source_ceiling as runner


def test_fixed_arm_dimensions():
    assert oracle.QD_PRODUCERS == 4
    assert oracle.QD_BLOCK_BYTES == 256 * 1024 * 1024
    assert oracle.QD_H2D_TARGET_BYTES == oracle.QD_BLOCK_BYTES
    assert oracle.FASTSAFE_THREADS == 8
    assert oracle.FASTSAFE_BBUF_KB == 512 * 1024
    assert oracle.FASTSAFE_BLOCK_BYTES == {
        "clip": 64 * 1024 * 1024,
        "unet": 256 * 1024 * 1024,
    }


def test_sample_keys_are_bounded_and_deterministic():
    header = {f"k{index}": {} for index in range(10)}
    assert oracle._sample_keys(header) == ["k0", "k1", "k8", "k9"]


def test_invalid_request_is_json_safe():
    result = oracle.run_source_ceiling_oracle("bad", "model.safetensors", "qd256")
    assert result["status"] == "error"
    assert result["model_construction"] is False


def _model_file(root, role="clip", name="model.safetensors", payload=b"01234567"):
    folder = root / ("text_encoders" if role == "clip" else "diffusion_models")
    folder.mkdir(parents=True)
    header = json.dumps({"x": {"dtype": "U8", "shape": [len(payload)], "data_offsets": [0, len(payload)]}}, separators=(",", ":")).encode()
    path = folder / name
    path.write_bytes(struct.pack("<Q", len(header)) + header + payload)
    return path


def test_source_only_has_no_h2d_or_torch_path(tmp_path, monkeypatch):
    path = _model_file(tmp_path)
    monkeypatch.setattr(oracle, "MODELS_ROOT", tmp_path)

    result = oracle.run_source_ceiling_oracle("clip", path.name, "source_only", qd=2, block_bytes=32 * 1024 * 1024)

    assert result["status"] == "ok"
    assert result["source_only"] is True
    assert result["torch_imported"] is False
    assert result["cuda_used"] is False
    assert result["h2d_used"] is False
    assert result["metrics"]["H2D_WALL_MS"] is None
    assert result["coverage"]["ok"] is True
    assert result["effective_GBps"] is not None
    assert result["resolved_path"] == str(path)
    assert result["identity"]["cpu_request"] == result["identity"]["cpu"]
    assert result["identity"]["cpu_allocation"]["cpu_request"] == result["identity"]["cpu_request"]
    assert result["cpu_request"] == result["identity"]["cpu_request"]
    assert result["cpu_allocation"]["cpu_request"] == result["cpu_request"]
    assert result["configured_source_qd"] == 2
    assert result["configured_source_capacity"] == oracle.SOURCE_CAPACITY == 8
    assert result["source_qd_timeline"]
    assert result["achieved_source_qd_timeline"] == result["source_qd_timeline"]
    assert result["h2d_submission_count"] == 0
    assert result["h2d_transfer_event_count"] == 0
    assert result["cuda_transfer_event_count"] == 0
    assert result["h2d_dispatcher_participation"] is False
    assert result["gpu_ready_dependency_controlling_source_slot_release"] is False
    assert result["source_only_proof"]["all"] is True
    assert result["source_only_proof"]["absence_predicates"] == {
        "no_gpu_ready_dependency_controlling_source_slot_release": True,
    }
    assert result["source_only_proof"]["source_workers_release_solely_from_source_completion"] is True
    assert result["source_only_proof"]["source_workers_terminate_solely_from_source_completion"] is True
    assert result["source_only_proof"]["source_qd_independent_of_h2d_or_staging_depth"] is True
    assert result["E27_SOURCE_MECHANISM_PROVEN"] == "NO"
    assert result["e27_source_mechanism_failed_predicates"] == ["source_only_no_h2d_mechanism"]


def test_source_only_proof_all_ignores_expected_negative_absence_field():
    proof = {key: True for key in oracle.SOURCE_ONLY_POSITIVE_PROOF_KEYS}
    proof["gpu_ready_dependency_controlling_source_slot_release"] = False

    assert oracle._source_only_proof_all(proof) is True


def test_source_only_proof_all_fails_when_positive_predicate_fails():
    proof = {key: True for key in oracle.SOURCE_ONLY_POSITIVE_PROOF_KEYS}
    proof["zero_cuda_h2d_submissions"] = False

    assert oracle._source_only_proof_all(proof) is False


def test_cpu_provenance_exposes_declared_and_observed_mismatch(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_E04_DECLARED_CPU", "4")
    monkeypatch.setattr(
        oracle,
        "runtime_shape_config",
        lambda: SimpleNamespace(cpu_request=16, runtime_shape_fingerprint="shape-16"),
    )

    allocation = oracle._identity()["cpu_allocation"]

    assert allocation["declared_modal_function_cpu"] == 4
    assert allocation["observed_runtime_shape_cpu_request"] == 16
    assert allocation["allocation_match"] is False
    assert allocation["allocation_match_classification"] == "mismatch"
    assert allocation["strict_allocation_match"] is False
    assert allocation["strict_allocation_classification"] == "mismatch"
    assert allocation["production_relevant"] is False


def test_source_only_preserves_selected_qd_when_capacity_is_eight(tmp_path, monkeypatch):
    path = _model_file(tmp_path, payload=b"abcdefgh")
    monkeypatch.setattr(oracle, "MODELS_ROOT", tmp_path)

    result = oracle.run_source_only(
        "clip", path.name, qd=1, block_bytes=32 * 1024 * 1024, source_capacity=8
    )

    assert result["status"] == "ok"
    assert result["configured_source_qd"] == 1
    assert result["configured_source_capacity"] == 8
    assert result["fixed_config"]["configured_source_qd"] == 1
    assert result["fixed_config"]["configured_source_capacity"] == 8


def test_source_only_preserves_requested_and_returned_bytes_for_short_reads(tmp_path, monkeypatch):
    path = _model_file(tmp_path, payload=b"abcdefgh")
    monkeypatch.setattr(oracle, "MODELS_ROOT", tmp_path)
    if hasattr(oracle.os, "preadv"):
        original = getattr(oracle.os, "preadv")

        def short_preadv(fd, buffers, offset):
            requested = len(buffers[0])
            return original(fd, [buffers[0][: max(1, requested // 2)]], offset)
        monkeypatch.setattr(oracle.os, "preadv", short_preadv)
    elif hasattr(oracle.os, "pread"):
        original = getattr(oracle.os, "pread")

        def short_pread(fd, requested, offset):
            return original(fd, max(1, requested // 2), offset)
        monkeypatch.setattr(oracle.os, "pread", short_pread)
    else:
        original = oracle.os.read

        def short_os_read(fd, requested):
            return original(fd, max(1, requested // 2))
        monkeypatch.setattr(oracle.os, "read", short_os_read)
    result = oracle.run_source_ceiling_oracle("clip", path.name, "source_only", qd=1, block_bytes=32 * 1024 * 1024)

    events = result["physical_syscall_telemetry"]
    assert result["coverage"]["ok"] is True
    assert len(events) >= 2
    pairs = [(event["requested_bytes"], event["returned_bytes"]) for event in events]
    assert pairs[0] == (8, 4)
    assert all(returned <= requested for requested, returned in pairs)
    assert sum(returned for _, returned in pairs) == 8


def test_phase_2_schedule_is_round_major_and_exactly_320_observations():
    schedule = runner.campaign_schedule(1, 10)
    assert len(schedule) == 320
    assert schedule[0]["round"] == 1
    assert schedule[0]["cell_id"] == "clip_b32_qd1"
    assert schedule[1]["cell_id"] == "unet_b32_qd1"
    assert schedule[31]["round"] == 1
    assert schedule[32]["round"] == 2
    assert schedule[-1]["cell_id"] == "unet_b256_qd8"
    assert len({item["cell_id"] for item in schedule}) == 32


def test_phase_2_resume_accepts_only_a_valid_source_artifact(tmp_path):
    out_dir = tmp_path / "runs"
    out_dir.mkdir()
    artifact_path = out_dir / "clip_b32_qd1_R1.json"
    artifact_path.write_text(json.dumps({
        "attempt_id": "clip_b32_qd1_R1",
        "role": "clip",
        "model_name": "qwen_3_4b.safetensors",
        "arm": "source_only",
        "status": "ok",
        "classification": "ELIGIBLE",
        "source_only": True,
        "model_construction": False,
        "cuda_used": False,
        "h2d_used": False,
        "FILE_TO_CUDA_WALL_MS": None,
        "fixed_config": {
            "execution_arm": "source_only", "configured_qd": 1, "producer_count": 1,
            "source_block_bytes": 32 * 1024 * 1024, "h2d_target_bytes": None,
            "aggregation_enabled": False, "cuda_used": False, "h2d_used": False,
            "model_construction": False,
        },
        "byte_validation": {"ok": True},
        "coverage": {"ok": True},
        "physical_syscall_telemetry": [{"requested_bytes": 1, "returned_bytes": 1}],
        "metrics": {"H2D_WALL_MS": None},
    }), encoding="utf-8")
    state_path = tmp_path / "state.json"

    results = asyncio.run(runner._run_campaign(
        "unused-for-resume-test", out_dir, 1, 1,
        roles=("clip",), qd_values=(1,), block_mib_values=(32,), state_path=state_path,
    ))

    assert len(results) == 1
    assert results[0]["attempt_id"] == "clip_b32_qd1_R1"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    cell = next(item for item in state["ledger"]["cells"] if item["cell_id"] == "clip_b32_qd1")
    assert cell["status"] == "COMPLETE"
    assert [item["status"] for item in cell["attempts"]] == ["COMPLETE"]
