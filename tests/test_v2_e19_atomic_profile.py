from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.benchmark_v2_direct as benchmark
from comfymodal_runtime import fast_cold_orchestration as fco
from comfymodal_runtime.modal_app import unet_snapshot_execution_contract
from comfymodal_runtime.trace import RuntimeTrace


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy_and_run_v2_single.bat"
RUN = ROOT / "run_v2_single.bat"
PROFILE_KEYS = tuple(benchmark.E19_FINAL_COLD_LOADER_PROFILE)
SELECTOR_KEYS = (
    benchmark.E19_FINAL_COLD_LOADER_SELECTOR,
    "V2_D6_FASTPATH_VALIDATION",
    "V2_D10_INTEGRATION_VALIDATION",
    "V2_E10_BUCKET_FIRST_VALIDATION",
)


def _activate(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    for key in PROFILE_KEYS + SELECTOR_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(benchmark.E19_FINAL_COLD_LOADER_SELECTOR, "1")
    for key, value in benchmark.E19_FINAL_COLD_LOADER_PROFILE.items():
        monkeypatch.setenv(key, overrides.get(key, value))


def test_e19_exact_profile_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _activate(monkeypatch)
    ok, details = benchmark.verify_e19_final_cold_loader_profile()

    assert ok is True
    assert details["profile"] == benchmark.E19_FINAL_COLD_LOADER_PROFILE_NAME
    assert details["validation"] == "PASS"
    for key, expected in benchmark.E19_FINAL_COLD_LOADER_PROFILE.items():
        assert details[key] == expected


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET", "0"),
        ("COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT", "0"),
        ("COMFYMODAL_V2_EVICT_RETAIN_ROLE", "none"),
        ("COMFYMODAL_V2_ENV_PROFILE", "production"),
        ("COMFYMODAL_V2_FAST_COLD_ORCHESTRATION", "0"),
        ("COMFYMODAL_V2_CHECKPOINT_PREWARM", "0"),
        ("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "0"),
        ("COMFYMODAL_V2_CRITICAL_GPU_COORDINATION", "0"),
        ("COMFYMODAL_V2_SCOPED_CUDA_READINESS", "0"),
        ("COMFYMODAL_V2_STAGED_SAFETENSORS", "1"),
        ("COMFYMODAL_V2_STAGED_SOURCE_ORDER", "1"),
        ("COMFYMODAL_V2_CLIP_STAGED_HYDRATION", "1"),
        ("COMFYMODAL_V2_C9QD_EXTRAS", "1"),
    ],
)
def test_e19_profile_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    _activate(monkeypatch, **{key: value})
    ok, details = benchmark.verify_e19_final_cold_loader_profile()

    assert ok is False
    assert details["validation"] == "FAIL"
    assert details[key] == value


def test_e19_profile_rejects_other_atomic_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    _activate(monkeypatch)
    monkeypatch.setenv("V2_D10_INTEGRATION_VALIDATION", "1")
    ok, details = benchmark.verify_e19_final_cold_loader_profile()

    assert ok is False
    assert "V2_D10_INTEGRATION_VALIDATION" in details["error"]


def test_existing_d6_and_d10_profiles_still_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    for selector, profile in (
        ("V2_D6_FASTPATH_VALIDATION", benchmark.D6_FASTPATH_PROFILE),
        ("V2_D10_INTEGRATION_VALIDATION", benchmark.D10_FASTPATH_PROFILE),
    ):
        for key in PROFILE_KEYS + SELECTOR_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv(selector, "1")
        for key, value in profile.items():
            monkeypatch.setenv(key, value)
        ok, details = benchmark.verify_d6_fastpath_profile()
        assert ok is True
        assert details["validation"] == "PASS"


def test_local_e19_preflight_emits_identity_and_deploy_path() -> None:
    env = dict(os.environ)
    for key in PROFILE_KEYS + SELECTOR_KEYS:
        env.pop(key, None)
    env[benchmark.E19_FINAL_COLD_LOADER_SELECTOR] = "1"
    env.update(benchmark.E19_FINAL_COLD_LOADER_PROFILE)
    result = subprocess.run(
        [sys.executable, "tools/benchmark_v2_direct.py", "--verify-d6-profile"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=240,
    )

    assert result.returncode == 0, result.stdout[-4000:]
    assert "ATOMIC_PROFILE=E19_FINAL_COLD_LOADER" in result.stdout
    assert "PROFILE ACCEPTED" in result.stdout
    assert "DEPLOY COMMAND CONSTRUCTED" in result.stdout
    assert "DEPLOY_COMMAND=modal deploy -m comfymodal_runtime.modal_app" in result.stdout
    assert "EPHEMERAL_PATH_USED=NO" in result.stdout


def test_canonical_wrappers_use_deployed_app_path_and_emit_profile() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")
    run = RUN.read_text(encoding="utf-8")
    combined = (deploy + run).lower()

    for source in (deploy, run):
        assert "V2_E19_FINAL_COLD_LOADER_ACTIVE" in source
        assert "COMFYMODAL_V2_ATOMIC_PROFILE" in source
        assert "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1" in source
        assert "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1" in source
        assert "COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae" in source
        assert "ATOMIC_PROFILE=!COMFYMODAL_V2_ATOMIC_PROFILE!" in source
        assert "python tools\\benchmark_v2_direct.py --verify-d6-profile" in source
    assert 'set "MODAL_CLI=modal"' in deploy
    assert "deploy -m comfymodal_runtime.modal_app" in deploy
    assert "modal run" not in combined
    assert "app.run(" not in combined


def test_stale_deployed_state_cannot_satisfy_e19_proof() -> None:
    assert benchmark._deployment_state_atomic_profile_matches(
        {}, benchmark.E19_FINAL_COLD_LOADER_PROFILE_NAME
    ) is False
    assert benchmark._deployment_state_atomic_profile_matches(
        {"atomic_profile": "stable-modal-comfy-v2-restore-only-staged-shadow"},
        benchmark.E19_FINAL_COLD_LOADER_PROFILE_NAME,
    ) is False
    assert benchmark._deployment_state_atomic_profile_matches(
        {"atomic_profile": benchmark.E19_FINAL_COLD_LOADER_PROFILE_NAME},
        benchmark.E19_FINAL_COLD_LOADER_PROFILE_NAME,
    ) is True

    # A live state file is allowed to match after the real E19 deployment.
    # The stale-state cases above are the deterministic unit-test contract.


def test_identity_record_requires_remote_atomic_profile_match() -> None:
    source = (ROOT / "tools" / "record_deployment_identity.py").read_text(
        encoding="utf-8"
    )
    assert "atomic_profile_mismatch" in source
    assert '"atomic_profile": deployed_atomic_profile or requested_atomic_profile' in source


def test_e19_snapshot_contract_requires_absent_unet_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "1")
    absent = SimpleNamespace(unet=None, unet_meta=object())
    contract = unet_snapshot_execution_contract(absent)
    assert contract["snapshot_unet_weights_present"] is False
    assert contract["snapshot_unet_weights_absent"] is True
    assert contract["meta_skeleton_present"] is True
    assert contract["fastsafe_first_demand_eligible"] is True
    assert contract["expected_unet_execution_identity"] == "fastsafetensors"
    assert contract["cpu_snapshot_execution_allowed_for_e19"] is False


def test_e19_snapshot_contract_rejects_present_unet_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "1")
    contract = unet_snapshot_execution_contract(SimpleNamespace(unet=object()))
    assert contract["snapshot_unet_weights_present"] is True
    assert contract["fastsafe_first_demand_eligible"] is False
    assert contract["expected_unet_execution_identity"] == "cpu_snapshot"
    assert contract["cpu_snapshot_execution_allowed_for_e19"] is True


def _valid_e19_evidence() -> dict[str, object]:
    return {
        "atomic_profile": benchmark.E19_FINAL_COLD_LOADER_PROFILE_NAME,
        "snapshot_unet_weights_present": False,
        "fresh_restore": True,
        "clip_loader_execution_identity": "fastsafetensors_direct_gpu",
        "unet_loader_execution_identity": "fastsafetensors",
        "clip_fallback_count": 0,
        "unet_fallback_count": 0,
        "clip_source_fence_valid": True,
        "unet_source_fence_valid": True,
        "clip_workers_alive_at_demand_start": 0,
        "unet_workers_alive_at_demand_start": 0,
        "prefetch_and_demand_overlap_detected": False,
        "unet_gpu_overlap_with_clip_critical": False,
        "unet_gpu_overlap_with_clip_critical_ms": 0,
        "clip_copy_event_recorded": True,
        "clip_copy_event_waited": True,
        "unet_copy_event_recorded": True,
        "unet_copy_event_waited": True,
        "clip_ready_at": 10.0,
        "unet_ready_at": 11.0,
        "model_readiness_status": "KNOWN",
        "model_readiness_gate_ms": 11.0,
        "canonical_output_sha_match": True,
    }


def test_e19_execution_gate_rejects_enabled_flag_with_cpu_snapshot() -> None:
    evidence = _valid_e19_evidence()
    evidence.update(
        snapshot_unet_weights_present=True,
        unet_loader_execution_identity="cpu_snapshot",
    )
    result = benchmark.evaluate_e19_structural_gate(evidence)
    assert result["valid"] is False
    assert "snapshot_unet_weights_absent" in result["failures"]
    assert "unet_execution_identity" in result["failures"]


def test_e19_execution_gate_accepts_real_fastsafe_evidence() -> None:
    result = benchmark.evaluate_e19_structural_gate(_valid_e19_evidence())
    assert result["valid"] is True
    assert result["enabled_flag_counts_as_execution_proof"] is False


def test_e19_execution_gate_rejects_missing_unet_readiness() -> None:
    evidence = _valid_e19_evidence()
    evidence.update(unet_ready_at=None, model_readiness_status="UNKNOWN", model_readiness_gate_ms=None)
    result = benchmark.evaluate_e19_structural_gate(evidence)
    assert result["valid"] is False
    assert "unet_ready_emitted" in result["failures"]
    assert "model_readiness_gate_emitted" in result["failures"]


def test_e19_clip_raw_lifecycle_reconciles_with_normalized_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(fco.MASTER_FLAG, "1")
    fco.reset_for_tests()
    trace = RuntimeTrace(request_id="trace-request", process="remote")
    fco.begin_request("context-request")
    fco.begin_request("context-request", trace=trace)
    trace.emit("clip_fh_hydration_start", phase="execution", metadata={"mode": "fastsafetensors_direct_gpu"})
    fco.record_fastsafe("clip", "start", trace=trace)
    fco.record_copy_event("clip", trace=trace)
    fco.record_copy_event_wait("clip", trace=trace)
    fco.mark_clip_forward_start(trace=trace)
    fco.mark_clip_forward_end(trace=trace)
    fco.record_fastsafe("clip", "end", trace=trace, event_recorded=True)
    fco.record_loader_execution_identity(
        "clip", "fastsafetensors_direct_gpu", trace=trace
    )
    fco.record_unet_ready(trace=trace)
    trace.emit("clip_fh_hydration_end", phase="execution", metadata={"success": True})
    record = fco.finalize_request("context-request", trace=trace)
    assert record is not None
    assert record["clip_fastsafe_start_at"] is not None
    assert record["clip_fastsafe_done_at"] is not None
    assert record["clip_copy_event_recorded"] is True
    assert record["clip_copy_event_waited"] is True
    assert record["clip_targeted_event_sync_count"] == 1
    assert record["clip_forward_start_at"] is not None
    assert record["clip_forward_end_at"] is not None
    assert record["clip_ready_at"] is not None
    assert record["clip_loader_execution_identity"] == "fastsafetensors_direct_gpu"
    assert record["model_readiness_status"] == "KNOWN"
    fco.reset_for_tests()


def test_e19_overlap_helper_is_exact() -> None:
    assert fco.interval_overlap_ms(1.0, 5.0, 6.0, 8.0) == 0.0
    assert fco.interval_overlap_ms(1.0, 5.0, 4.0, 8.0) == 1_000.0
    assert fco.interval_overlap_ms(1.0, 5.0, 2.0, 4.0) == 2_000.0
    assert fco.interval_overlap_ms(1.0, 5.0, None, 4.0) is None


# ── E22 causal A/B arm tests ────────────────────────────────────────────

def _e22_activate(monkeypatch: pytest.MonkeyPatch, arm: str = "off") -> None:
    """Activate E22 arm: E19 base + E22 arm selector + override CHECKPOINT_PREWARM."""
    for key in PROFILE_KEYS + SELECTOR_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv(benchmark.E22_PREFETCH_OFF_SELECTOR, raising=False)
    monkeypatch.delenv(benchmark.E22_PREFETCH_ON_SELECTOR, raising=False)
    monkeypatch.setenv(benchmark.E19_FINAL_COLD_LOADER_SELECTOR, "1")
    for key, value in benchmark.E19_FINAL_COLD_LOADER_PROFILE.items():
        monkeypatch.setenv(key, value)
    if arm == "off":
        monkeypatch.setenv(benchmark.E22_PREFETCH_OFF_SELECTOR, "1")
        monkeypatch.setenv("COMFYMODAL_V2_CHECKPOINT_PREWARM", "0")
    elif arm == "on":
        monkeypatch.setenv(benchmark.E22_PREFETCH_ON_SELECTOR, "1")
        monkeypatch.setenv("COMFYMODAL_V2_CHECKPOINT_PREWARM", "1")


def test_e22_prefetch_off_arm_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _e22_activate(monkeypatch, arm="off")
    ok, details = benchmark.verify_e22_arm_profile()
    assert ok is True
    assert details["profile"] == benchmark.E19_FINAL_COLD_LOADER_PROFILE_NAME
    assert details["validation"] == "PASS"
    assert details["e22_arm"] == "off"
    assert details.get("COMFYMODAL_V2_CHECKPOINT_PREWARM") == "0"


def test_e22_prefetch_on_arm_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _e22_activate(monkeypatch, arm="on")
    ok, details = benchmark.verify_e22_arm_profile()
    assert ok is True
    assert details["profile"] == benchmark.E19_FINAL_COLD_LOADER_PROFILE_NAME
    assert details["validation"] == "PASS"
    assert details["e22_arm"] == "on"
    assert details.get("COMFYMODAL_V2_CHECKPOINT_PREWARM") == "1"


def test_e22_same_atomic_profile_both_arms(monkeypatch: pytest.MonkeyPatch) -> None:
    for arm in ("off", "on"):
        _e22_activate(monkeypatch, arm=arm)
        ok, details = benchmark.verify_e22_arm_profile()
        assert ok is True, f"arm={arm} should pass"
        assert details.get("COMFYMODAL_V2_ATOMIC_PROFILE") == benchmark.E19_FINAL_COLD_LOADER_PROFILE_NAME


def test_e22_behavioral_diff_is_prewarm_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prove the only env difference between arms is CHECKPOINT_PREWARM."""
    envs = {}
    for arm in ("off", "on"):
        _e22_activate(monkeypatch, arm=arm)
        ok, details = benchmark.verify_e22_arm_profile()
        assert ok is True
        envs[arm] = {k: details.get(k) for k in benchmark.E19_FINAL_COLD_LOADER_PROFILE}
    diffs = {k for k in envs["off"] if envs["off"][k] != envs["on"][k]}
    assert diffs == {"COMFYMODAL_V2_CHECKPOINT_PREWARM"}, f"unexpected diffs: {diffs}"


def test_e22_request_override_cannot_change_prewarm(monkeypatch: pytest.MonkeyPatch) -> None:
    """CHECKPOINT_PREWARM is NOT in _REQUEST_DIAGNOSTIC_ENV_ALLOWLIST."""
    from comfymodal_runtime.modal_app import _REQUEST_DIAGNOSTIC_ENV_ALLOWLIST
    keys = {entry[0] for entry in _REQUEST_DIAGNOSTIC_ENV_ALLOWLIST}
    assert "COMFYMODAL_V2_CHECKPOINT_PREWARM" not in keys


def test_e22_wrapper_prefetch_off_resolves_correct_env() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")
    assert "V2_E22_PREFETCH_OFF" in deploy
    assert "V2_E22_PREFETCH_ON" in deploy
    assert "E22_PREFETCH_OFF" in deploy
    assert "E22_PREFETCH_ON" in deploy
    assert "COMFYMODAL_V2_CHECKPOINT_PREWARM=0" in deploy
    assert "COMFYMODAL_V2_CHECKPOINT_PREWARM=1" in deploy


def test_e22_wrapper_fail_closed_before_modal() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")
    assert "V2_E19_FINAL_COLD_LOADER_ACTIVE" in deploy
    assert "verify-d6-profile" in deploy or "verify-e22-arm-profile" in deploy


def test_e22_prefetch_off_not_in_allowlist() -> None:
    from comfymodal_runtime.modal_app import _REQUEST_DIAGNOSTIC_ENV_ALLOWLIST
    keys = {entry[1] for entry in _REQUEST_DIAGNOSTIC_ENV_ALLOWLIST}
    assert "COMFYMODAL_V2_CHECKPOINT_PREWARM" not in keys


def test_e22_arm_requires_e19_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    """E22 arm without E19 selector must fail."""
    for key in PROFILE_KEYS + SELECTOR_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv(benchmark.E22_PREFETCH_OFF_SELECTOR, raising=False)
    monkeypatch.delenv(benchmark.E22_PREFETCH_ON_SELECTOR, raising=False)
    monkeypatch.setenv(benchmark.E22_PREFETCH_OFF_SELECTOR, "1")
    ok, details = benchmark.verify_e22_arm_profile()
    assert ok is False
    assert details["validation"] == "FAIL"


def test_e22_arm_mutual_exclusion_enforced() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")
    assert "mutually exclusive" in deploy.lower() or "mutually exclusive" in deploy
