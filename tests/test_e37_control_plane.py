"""Focused offline source/profile/control-plane checks for E37."""

from __future__ import annotations

import json
from pathlib import Path

from tools.v2_control.profiles import Profiles
from tools.v2_control.validation import (
    E37CleanLaneProofValidator,
    E37StrictProofValidator,
    RunRecord,
)
from tests.v2ctl_fakes import FakeArtifactSet, FakeConfig, FakeFlag


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SHA = "20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260"
PROFILES = Profiles(ROOT / "config" / "v2" / "profiles")


def test_e37_lane_starts_only_after_modal_restore_exit():
    source = (ROOT / "comfymodal_runtime" / "modal_app.py").read_text(encoding="utf-8")
    exit_pos = source.index('"modal_restore_exit"')
    lane_pos = source.index("start_restore_time_clip_lane(")
    assert exit_pos < lane_pos
    assert source.count("start_restore_time_clip_lane(") == 1
    assert "restore-time lane skipped" not in source
    assert "post-restore lane skipped" in source


def test_minimal_restore_is_profile_forwarded_and_allowlisted():
    modal_source = (ROOT / "comfymodal_runtime" / "modal_app.py").read_text(encoding="utf-8")
    comfyapp_source = (ROOT / "comfyapp.py").read_text(encoding="utf-8")
    assert '"COMFYMODAL_MINIMAL_RESTORE"' in modal_source
    assert '"COMFYMODAL_MINIMAL_RESTORE": os.environ.get(' in modal_source
    assert 'MINIMAL_RESTORE_DEFAULT = True' in comfyapp_source
    for name in ("e37-clip-qd4", "e37-clip-fastsafe"):
        resolved = PROFILES.resolve(name)
        assert resolved.environment["COMFYMODAL_MINIMAL_RESTORE"] == "1"
        assert resolved.environment["COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH"] == "1"


def test_e37_profiles_share_contract_and_only_qd_reader_differs():
    qd = PROFILES.resolve("e37-clip-qd4")
    fastsafe = PROFILES.resolve("e37-clip-fastsafe")
    assert qd.owner == fastsafe.owner == "E37"
    assert qd.target == fastsafe.target
    assert qd.resources == fastsafe.resources
    assert qd.workload == fastsafe.workload
    assert qd.workload["fresh_required"] is True
    assert qd.workload["conditioning_cache"] == "forced_miss"
    assert qd.workload["expected_output_sha"] == fastsafe.workload["expected_output_sha"] == EXPECTED_SHA
    assert qd.workload["run_count"] == fastsafe.workload["run_count"] == 1
    assert qd.runtime_overrides == fastsafe.runtime_overrides == {"policy": "forbid"}
    assert qd.environment["COMFYMODAL_V2_CLIP_QD_READER"] == "1"
    assert fastsafe.environment["COMFYMODAL_V2_CLIP_QD_READER"] == "0"
    for profile in (qd, fastsafe):
        assert profile.environment["COMFYMODAL_V2_CLIP_QD_QD"] == "4"
        assert profile.environment["COMFYMODAL_V2_CLIP_QD_BLOCK_MIB"] == "32"
        assert profile.environment["COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY"] == "after_restore_sensitive_phase"
        assert profile.environment["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] == "0"
        assert profile.environment["COMFYMODAL_V2_E31_FORENSICS"] == "0"
        assert profile.environment["COMFYMODAL_V2_E31_FORWARD_PROFILE"] == "0"


def _e37_record(
    tmp_path: Path,
    *,
    reason: object = "",
    include_cache: bool = True,
    source_identity: dict | None = None,
    effective_env: dict | None = None,
) -> RunRecord:
    events = [
        {"name": "plan_proof_decision", "metadata": {
            "decision": "plan_validation_fast_path", "consumed": True, "reason": reason,
        }},
    ]
    if include_cache:
        events.append({"name": "clip_conditioning_cache_lookup", "metadata": {"miss_count": 1}})
    artifact_data = {
        "output_sha": EXPECTED_SHA,
        "trace": {"events": events},
        "canonical_ledger_status": "ok",
        "canonical_ledger": {
            "endpoint_status": "ok",
            "end_mono_ns": 20,
            "serial_ledger": {"zero_gap": True},
            "events": [{"name": "first_durable_result", "mono_ns": 20}],
        },
    }
    if source_identity is not None:
        artifact_data["source_identity"] = source_identity
    if effective_env is not None:
        artifact_data["effective_env"] = effective_env
    path = tmp_path / "run_1.json"
    path.write_text(json.dumps(artifact_data), encoding="utf-8")
    config = FakeConfig(profile_name="e37-clip-qd4")
    config.workload.expected_output_sha = EXPECTED_SHA
    config.workload.conditioning_cache = "forced_miss"
    config.flags.append(FakeFlag("COMFYMODAL_V2_E37_STRICT_PROOF", "1"))
    return RunRecord(
        run_fingerprint="r" * 64,
        deploy_fingerprint="d" * 64,
        profile=config.profile_name,
        target_app=config.target.app,
        target_class=config.target.class_name,
        fresh_required=True,
        expected_output_sha=EXPECTED_SHA,
        artifacts=FakeArtifactSet(run_artifact=path),
        backend_ok=True,
        telemetry={},
        output_sha=EXPECTED_SHA,
    )


def test_e37_strict_validator_requires_real_proof_and_cache_miss(tmp_path):
    record = _e37_record(tmp_path, source_identity={"combined_hash": "source-hash"})
    config = FakeConfig(profile_name="e37-clip-qd4")
    config.workload.expected_output_sha = EXPECTED_SHA
    config.workload.conditioning_cache = "forced_miss"
    config.flags.append(FakeFlag("COMFYMODAL_V2_E37_STRICT_PROOF", "1"))
    assert E37StrictProofValidator().validate(record, config) == []

    missing = _e37_record(tmp_path, reason="fallback", include_cache=False)
    failures = E37StrictProofValidator().validate(missing, config)
    text = "\n".join(failures)
    assert "reason must be explicitly empty" in text
    assert "conditioning-cache miss evidence" in text


def test_e37_strict_validator_accepts_persisted_effective_env_deployment_hash(tmp_path):
    record = _e37_record(
        tmp_path,
        source_identity=None,
        effective_env={
            "COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH": "deployment-combined-hash",
            "COMFYMODAL_V2_ENV_PROFILE": "production",
        },
    )
    config = FakeConfig(profile_name="e37-clip-qd4")
    config.workload.expected_output_sha = EXPECTED_SHA
    config.workload.conditioning_cache = "forced_miss"
    config.flags.append(FakeFlag("COMFYMODAL_V2_E37_STRICT_PROOF", "1"))

    assert E37StrictProofValidator().validate(record, config) == []


def test_e37_strict_validator_rejects_ids_without_deployment_or_source_hash(tmp_path):
    record = _e37_record(
        tmp_path,
        source_identity={"profile": "e37-clip-qd4", "request_id": "request-1"},
        effective_env={"COMFYMODAL_V2_ENV_PROFILE": "production"},
    )
    config = FakeConfig(profile_name="e37-clip-qd4")
    config.workload.expected_output_sha = EXPECTED_SHA
    config.workload.conditioning_cache = "forced_miss"
    config.flags.append(FakeFlag("COMFYMODAL_V2_E37_STRICT_PROOF", "1"))

    failures = E37StrictProofValidator().validate(record, config)
    assert "E37 source identity proof missing" in failures


def test_e37_clean_lane_profile_is_explicit_and_qd4():
    resolved = PROFILES.resolve("e37-clean-lane-qd4")
    assert resolved.environment["COMFYMODAL_V2_E37_CLEAN_LANE"] == "1"
    assert resolved.environment["COMFYMODAL_V2_CLEAN_LANE"] == "1"
    assert resolved.environment["COMFYMODAL_V2_CLIP_QD_READER"] == "1"
    assert resolved.environment["COMFYMODAL_V2_CLIP_QD_QD"] == "4"
    assert resolved.environment["COMFYMODAL_V2_CLIP_QD_BLOCK_MIB"] == "32"
    assert resolved.environment["COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY"] == "clean_lane_post_restore"
    assert resolved.environment["COMFYMODAL_V2_PREFILL_LANES"] == "none"


def test_clean_lane_suppresses_restore_launch_and_plan_workers(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_V2_E37_CLEAN_LANE", "1")
    from comfymodal_runtime.speculative_clip_hydration import (
        start_restore_time_clip_lane,
    )

    assert start_restore_time_clip_lane(clip=None, cpu_models=None) is None
    source = (ROOT / "comfymodal_runtime" / "modal_app.py").read_text(encoding="utf-8")
    assert "plan_time_unet_source_h2d" in source
    assert "execution_prefill" in source


def test_clean_lane_demand_path_uses_synchronous_qd_before_bind():
    source = (ROOT / "comfymodal_runtime" / "clip_fast_hydration_wiring.py").read_text(
        encoding="utf-8"
    )
    qd_branch = source.index("CLEAN_LANE deliberately has no restore-time speculative read")
    qd_call = source.index("_sd_raw, _loader, _fb = clip_qd_load(", qd_branch)
    bind_call = source.index("cfh.hydrate_clip_bind(", qd_call)
    assert qd_call < bind_call
    assert "qd=_qd_value" in source[qd_branch:bind_call]
    assert "block_mib=_qd_block_mib" in source[qd_branch:bind_call]
    assert "launch_policy=_qd_launch_policy" in source[qd_branch:bind_call]
    assert "trace=trace" in source[qd_branch:bind_call]
    assert "CLEAN_LANE_QD_NOT_QUIESCENT_BEFORE_BIND" in source[qd_branch:bind_call]


def test_clean_lane_proof_validator_fails_closed_for_fallback_and_quiescence(tmp_path):
    artifact = tmp_path / "run.json"
    artifact.write_text(json.dumps({
        "trace": {"events": [{"name": "clean_lane_proof", "metadata": {
            "mode": "E37_CLEAN_LANE", "proof_version": 1,
            "qd": {"configured_qd": 4, "actual_inflight": 4, "mode": "QD4",
                   "fallback": True, "stats_status": "ok",
                   "source_errors": [], "reconciliation_240_240": True,
                   "h2d_host_issue_ms": 1.0, "h2d_cuda_event_ms": 1.0},
            "ordering": {}, "phase_intervals": {}, "volume_reads": [],
            "quiescence": {}, "thread_state": {},
        }}]},
    }), encoding="utf-8")
    config = FakeConfig(profile_name="e37-clean-lane-qd4")
    record = RunRecord(
        run_fingerprint="r" * 64, deploy_fingerprint="d" * 64,
        profile=config.profile_name, target_app=config.target.app,
        target_class=config.target.class_name, fresh_required=True,
        expected_output_sha=EXPECTED_SHA,
        artifacts=FakeArtifactSet(run_artifact=artifact), backend_ok=True,
        telemetry={}, output_sha=EXPECTED_SHA,
    )
    failures = E37CleanLaneProofValidator().validate(record, config)
    assert "CLEAN_LANE QD proof shows FASTSAFE fallback" in failures
    assert "CLEAN_LANE lifecycle ordering proof incomplete" in failures


def test_clean_lane_restore_child_classifications_keep_banner_separate():
    from comfymodal_runtime.clean_lane import RESTORE_CHILD_CLASSIFICATIONS

    assert RESTORE_CHILD_CLASSIFICATIONS["identity_capture"] == "MUST_BE_IN_RESTORE"
    assert RESTORE_CHILD_CLASSIFICATIONS["clip_qd_source_read"] == "MOVE_AFTER_RESTORE"
    assert RESTORE_CHILD_CLASSIFICATIONS["modal_banner_to_first_python"] == "DIAGNOSTIC_ONLY"


def test_clean_lane_forced_miss_evidence_is_explicit_and_non_persistent(monkeypatch):
    from comfymodal_runtime import model_preload as mp
    from comfymodal_runtime.trace import RuntimeTrace

    monkeypatch.setenv("COMFYMODAL_V2_E37_CLEAN_LANE", "1")
    monkeypatch.setattr(mp, "_PREFILL_LANE_MODE", "none")
    trace = RuntimeTrace(request_id="clean-request", process="test")
    clip = object()

    mp._emit_clean_lane_forced_miss_evidence(
        trace,
        clip=clip,
        text="a cat",
        reason="cache_service_disabled_or_unavailable",
    )

    lookup = [e for e in trace.events if e.name == "clip_conditioning_cache_lookup"][-1]
    decision = [e for e in trace.events if e.name == "clip_conditioning_cache_decision"][-1]
    assert lookup.metadata["hit"] is False
    assert lookup.metadata["miss_count"] == 1
    assert lookup.metadata["real_encode_request"] is True
    assert decision.metadata["decision"] == "miss_not_stored"
    assert decision.metadata["persisted_count"] == 0
    assert decision.metadata["persistence"] == "disabled"

    monkeypatch.delenv("COMFYMODAL_V2_E37_CLEAN_LANE")
    monkeypatch.delenv("COMFYMODAL_V2_CLEAN_LANE", raising=False)
    normal_trace = RuntimeTrace(request_id="normal-request", process="test")
    mp._emit_clean_lane_forced_miss_evidence(
        normal_trace, clip=clip, text="a cat", reason="not-clean"
    )
    assert not [
        e for e in normal_trace.events
        if e.name.startswith("clip_conditioning_cache_")
    ]


def test_gpu_qd_source_proof_seams_are_before_submit_and_include_identity():
    source = (ROOT / "comfymodal_runtime" / "clip_qd_reader.py").read_text(
        encoding="utf-8"
    )
    gpu = source[source.index("def read_file_qd_gpu("):]
    assert "stats[\"source_identity\"] = {" in gpu
    assert "clean_lane.mark_qd_start(trace, path=str(path))" in gpu
    assert gpu.index("clean_lane.mark_qd_start(") < gpu.index("emit_qd_event(trace, EVT_SUBMIT_START")
