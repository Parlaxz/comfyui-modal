"""Tests for tools/v2_control/validation.py (design sections 17 & 18).

Covers contract section 21 gate/confirm coverage: exactly one gate invocation
with V2_BENCHMARK_RUNS=1 + --run-count 1, manifest persisted valid AND
invalid, confirm refusing invalid/stale/missing gates, confirm running
exactly ``runs`` times on a valid gate, confirmation manifest persisted, and
the structural/expected-sha validators.

Uses the duck-typed fakes from tests.v2ctl_fakes only -- no dependency on
Agent B's backend/fingerprints/environment modules.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from tools.v2_control.errors import GateError
from tools.v2_control.validation import (
    CanonicalLedgerValidator,
    ConfirmRunner,
    E31ForensicsValidator,
    ExpectedOutputShaValidator,
    GoldenCohortValidator,
    GateRunner,
    RunRecord,
    StructuralValidator,
    Validator,
    build_run_record_from_result,
    extract_output_sha,
    mark_runtime_health_verified,
    parse_telemetry,
)

from tests.v2ctl_fakes import (
    OK_GATE_STDOUT,
    FakeArtifactSet,
    FakeBackendRunner,
    FakeConfig,
    FakeFingerprints,
    FakeFlag,
    FakeSpec,
)

SHA_20B1 = "20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260"
GOLDEN_EXPECTED_SHA = "c" * 64
GOLDEN_OBSERVED_SHA = "d" * 64


def make_validator() -> Validator:
    validator = Validator()
    validator.register(StructuralValidator())
    validator.register(ExpectedOutputShaValidator())
    return validator


def make_gate_runner(tmp_path, fingerprints=None, backend=None, validator=None):
    fingerprints = fingerprints or FakeFingerprints(
        inputs={
            "git_head": "0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997",
            "target": {"app": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypointV2", "method": "run_plan_stream"},
            "resources": {"gpu": "rtx-pro-6000"},
            "profile": "production",
            "deploy_flags": {"COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0"},
        }
    )
    backend = backend or FakeBackendRunner(stdout=OK_GATE_STDOUT)
    validator = validator or make_validator()
    return GateRunner(
        repo_root=tmp_path,
        fingerprints=fingerprints,
        validators=validator,
        backend_runner=backend,
        env_builder=object(),  # unused by GateRunner/ConfirmRunner
    )


def make_confirm_runner(tmp_path, fingerprints=None, backend=None, validator=None):
    fingerprints = fingerprints or FakeFingerprints(
        inputs={
            "git_head": "0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997",
            "target": {"app": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypointV2", "method": "run_plan_stream"},
            "resources": {"gpu": "rtx-pro-6000"},
            "profile": "production",
            "deploy_flags": {"COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0"},
        }
    )
    backend = backend or FakeBackendRunner(stdout=OK_GATE_STDOUT)
    validator = validator or make_validator()
    return ConfirmRunner(
        repo_root=tmp_path,
        fingerprints=fingerprints,
        validators=validator,
        backend_runner=backend,
        env_builder=object(),
    )


def _golden_cohort_record(tmp_path: Path, *, include_warning: bool = True,
                          include_sha: bool = True) -> RunRecord:
    """Build the smallest immutable Golden cohort accepted by the validator."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    attempt_path = tmp_path / "attempt_0.json"
    manifest_path = tmp_path / "manifest.json"
    request_id = "golden-request-1"
    validation = {
        "observed_output_shas": [GOLDEN_OBSERVED_SHA] if include_sha else [],
        "observed_flags": {},
    }
    if include_warning:
        validation["output_sha_warning"] = {
            "expected": GOLDEN_EXPECTED_SHA,
            "observed": GOLDEN_OBSERVED_SHA,
        }
    attempt = {
        "request_id": request_id,
        "v2ctl_invocation_id": "invocation",
        "attention_backend": "pytorch",
        "mode": "golden_p1_serial",
        "method": "run_golden_serial_stream",
        "valid": True,
        "dnf": False,
        "failures": [],
        "validation": validation,
        "golden_telemetry": {
            "schema": "golden_p1_telemetry_v1",
            "true_durable_marked": True,
            "reopen_verified": True,
        },
        "seriality": {"ok": True, "count": 0},
    }
    attempt_path.write_text(json.dumps(attempt), encoding="utf-8")
    target = {
        "app_name": "golden-test-app",
        "class_name": "ModalRuntimeEntrypointV2",
        "method": "run_golden_serial_stream",
        "gpu": "rtx-pro-6000",
    }
    manifest = {
        "v2ctl_invocation_id": "invocation",
        "profile": "golden_p1",
        "profile_config_fingerprint": "profile-fingerprint",
        "attention_backend": "pytorch",
        "mode": "golden_p1_serial",
        "method": "run_golden_serial_stream",
        "target": target,
        "expected_output_sha": GOLDEN_EXPECTED_SHA,
        "workflow": {"workflow_hash": "workflow", "prompt_sha256": "prompt"},
        "run_count_requested": 1,
        "attempt_count": 1,
        "valid_count": 1,
        "invalid_count": 0,
        "dnf_count": 0,
        "attempts": [{"request_id": request_id}],
        "artifact_file_hashes": {
            attempt_path.name: hashlib.sha256(attempt_path.read_bytes()).hexdigest(),
        },
    }
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps({
        "v2ctl_invocation_id": "invocation",
        "request_id": request_id,
        "attention_backend": "pytorch",
        "mode": "golden_p1_serial",
    }), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    config = FakeConfig(profile_name="golden_p1")
    config.target.app = target["app_name"]
    config.target.class_name = target["class_name"]
    config.target.method = target["method"]
    config.workload.expected_output_sha = GOLDEN_EXPECTED_SHA
    artifacts = FakeArtifactSet(
        run_artifact=attempt_path,
        summary_artifact=summary_path,
        campaign_manifest=manifest_path,
        request_id=request_id,
    )
    return RunRecord(
        run_fingerprint="a" * 64,
        deploy_fingerprint="b" * 64,
        profile="golden_p1",
        target_app=target["app_name"],
        target_class=target["class_name"],
        fresh_required=True,
        expected_output_sha=GOLDEN_EXPECTED_SHA,
        artifacts=artifacts,
        backend_ok=True,
        telemetry={},
        output_sha=GOLDEN_OBSERVED_SHA if include_sha else None,
        request_id=request_id,
        v2ctl_invocation_id="invocation",
        profile_config_fingerprint="profile-fingerprint",
        provenance_validation_status="validated",
        expected_deploy_id=DEPLOY_ID,
        deploy_id=DEPLOY_ID,
    )


def _golden_config(record: RunRecord) -> FakeConfig:
    config = FakeConfig(profile_name="golden_p1")
    config.target.app = record.target_app
    config.target.class_name = record.target_class
    config.target.method = "run_golden_serial_stream"
    config.resources.gpu = "rtx-pro-6000"
    config.workload.expected_output_sha = GOLDEN_EXPECTED_SHA
    return config


# The one deployment identity. Structural acceptance compares the expected value
# with the value the serving interpreter reported.
DEPLOY_ID = "d" * 64


class TestParsing:
    def test_parse_telemetry(self):
        telemetry = parse_telemetry("request_id=abc\ncorrelation_id=xyz\n12:34:56 fresh=1\njunk line\n")
        assert telemetry["request_id"] == "abc"
        assert telemetry["correlation_id"] == "xyz"
        assert telemetry["fresh"] == "1"

    def test_extract_output_sha(self):
        assert extract_output_sha("output_sha=abc123\n") == "abc123"
        assert extract_output_sha("OUTPUT_SHA = \"def456\"") == "def456"
        assert extract_output_sha("no sha here") is None


class TestValidators:
    def test_structural_valid_pass(self, tmp_path):
        artifact = tmp_path / "run_1.json"
        artifact.write_text("{}", encoding="utf-8")
        record = RunRecord(
            run_fingerprint="a" * 64,
            deploy_fingerprint="b" * 64,
            profile="production",
            target_app="app",
            target_class="cls",
            fresh_required=True,
            expected_output_sha="",
            artifacts=FakeArtifactSet(run_artifact=artifact),
            backend_ok=True,
            telemetry={
                "request_id": "r1",
                "correlation_id": "c1",
                "fresh": "1",
                "deploy_id": DEPLOY_ID,
            },
            expected_deploy_id=DEPLOY_ID,
        )
        assert StructuralValidator().validate(record, FakeConfig()) == []


    def test_structural_valid_failures(self, tmp_path):
        record = RunRecord(
            run_fingerprint="a" * 64,
            deploy_fingerprint="b" * 64,
            profile="production",
            target_app="app",
            target_class="cls",
            fresh_required=True,
            expected_output_sha="",
            artifacts=FakeArtifactSet(run_artifact=tmp_path / "missing.json"),
            backend_ok=False,
            telemetry={},
        )
        failures = StructuralValidator().validate(record, FakeConfig())
        text = "\n".join(failures)
        assert "backend" in text
        assert "run artifact missing" in text
        assert "request_id" in text
        assert "correlation_id" in text
        assert "fresh" in text

    def test_output_sha_validator(self):
        config = FakeConfig()
        config.workload.expected_output_sha = SHA_20B1
        record = RunRecord(
            run_fingerprint="a" * 64,
            deploy_fingerprint="b" * 64,
            profile="production",
            target_app="app",
            target_class="cls",
            fresh_required=False,
            expected_output_sha=SHA_20B1,
            artifacts=None,
            backend_ok=True,
            telemetry={},
            output_sha=SHA_20B1,
        )
        assert ExpectedOutputShaValidator().validate(record, config) == []
        record.output_sha = "deadbeef"
        assert ExpectedOutputShaValidator().validate(record, config) != []
        record.output_sha = None
        failures = ExpectedOutputShaValidator().validate(record, config)
        assert any("unavailable" in f for f in failures)

    def test_output_sha_not_required_when_unset(self):
        config = FakeConfig()  # expected_output_sha == ""
        record = RunRecord(
            run_fingerprint="a" * 64,
            deploy_fingerprint="b" * 64,
            profile="production",
            target_app="app",
            target_class="cls",
            fresh_required=False,
            expected_output_sha="",
            artifacts=None,
            backend_ok=True,
            telemetry={},
            output_sha=None,
        )
        assert ExpectedOutputShaValidator().validate(record, config) == []

    def test_golden_cohort_accepts_explicit_output_sha_mismatch_warning(self, tmp_path):
        record = _golden_cohort_record(tmp_path)

        assert GoldenCohortValidator().validate(record, _golden_config(record)) == []

    def test_golden_cohort_rejects_missing_sha_or_warning(self, tmp_path):
        missing_sha = _golden_cohort_record(tmp_path / "missing_sha", include_sha=False)
        failures = GoldenCohortValidator().validate(
            missing_sha, _golden_config(missing_sha)
        )
        assert any("output SHA proof is missing" in failure for failure in failures)

        missing_warning = _golden_cohort_record(
            tmp_path / "missing_warning", include_warning=False
        )
        failures = GoldenCohortValidator().validate(
            missing_warning, _golden_config(missing_warning)
        )
        assert any("lacks explicit warning evidence" in failure for failure in failures)

    @pytest.mark.parametrize("artifact_name", ["summary.json", "attempt_0.json"])
    def test_golden_cohort_requires_invocation_id_in_summary_and_attempt(
        self, tmp_path, artifact_name
    ):
        record = _golden_cohort_record(tmp_path)
        artifact_path = tmp_path / artifact_name
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        del data["v2ctl_invocation_id"]
        artifact_path.write_text(json.dumps(data), encoding="utf-8")

        failures = GoldenCohortValidator().validate(record, _golden_config(record))

        assert any(
            f"Golden {'summary' if artifact_name.startswith('summary') else 'attempt'} invocation ID is missing"
            in failure
            for failure in failures
        )


class TestGateRunner:
    @staticmethod
    def _deployment_manifest(tmp_path, config, fingerprints, **overrides):
        path = tmp_path / ".v2ctl" / "deployments" / "deploy_0001.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "deploy_fingerprint": fingerprints.deploy_fingerprint(),
            "target": {
                "app": config.target.app,
                "class": config.target.class_name,
                "method": config.target.method,
            },
            "runtime_health_status": "unverified",
            **overrides,
        }
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_successful_validated_gate_marks_matching_deployment_healthy(self, tmp_path):
        config = FakeConfig()
        artifact = tmp_path / "run.json"
        artifact.write_text("{}", encoding="utf-8")
        runner = make_gate_runner(
            tmp_path,
            backend=FakeBackendRunner(
                stdout=OK_GATE_STDOUT,
                artifacts=FakeArtifactSet(run_artifact=artifact),
            ),
        )
        manifest = self._deployment_manifest(tmp_path, config, runner._fingerprints)

        result = runner.run_gate(config, FakeSpec())

        assert result.valid is True
        assert json.loads(manifest.read_text(encoding="utf-8"))["runtime_health_status"] == "verified"

    def test_failed_gate_does_not_mark_deployment_healthy(self, tmp_path):
        config = FakeConfig()
        backend = FakeBackendRunner(mode="fail", exit_code=1)
        runner = make_gate_runner(tmp_path, backend=backend)
        manifest = self._deployment_manifest(tmp_path, config, runner._fingerprints)

        result = runner.run_gate(config, FakeSpec())

        assert result.valid is False
        assert json.loads(manifest.read_text(encoding="utf-8"))["runtime_health_status"] == "unverified"

    @pytest.mark.parametrize("overrides", [
        {"target": {"app": "wrong-app", "class": "ModalRuntimeEntrypointV2", "method": "run_plan_stream"}},
        {"deploy_fingerprint": "stale-fingerprint"},
    ])
    def test_gate_health_transition_requires_matching_target_and_fingerprint(
        self, tmp_path, overrides
    ):
        config = FakeConfig()
        artifact = tmp_path / "run.json"
        artifact.write_text("{}", encoding="utf-8")
        runner = make_gate_runner(
            tmp_path,
            backend=FakeBackendRunner(
                stdout=OK_GATE_STDOUT,
                artifacts=FakeArtifactSet(run_artifact=artifact),
            ),
        )
        manifest = self._deployment_manifest(
            tmp_path, config, runner._fingerprints, **overrides
        )

        result = runner.run_gate(config, FakeSpec())

        assert result.valid is True
        assert json.loads(manifest.read_text(encoding="utf-8"))["runtime_health_status"] == "unverified"

    def test_health_helper_preserves_source_identity_status(self, tmp_path):
        config = FakeConfig()
        runner = make_gate_runner(tmp_path)
        manifest = self._deployment_manifest(
            tmp_path, config, runner._fingerprints, source_identity_status="verified"
        )

        assert mark_runtime_health_verified(
            tmp_path,
            config,
            runner._fingerprints,
            runner._fingerprints.deploy_fingerprint(),
        ) == manifest
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert data["runtime_health_status"] == "verified"
        assert data["source_identity_status"] == "verified"

    def test_fingerprint_change_during_backend_does_not_promote_health(self, tmp_path):
        config = FakeConfig()
        fingerprints = FakeFingerprints()
        artifact = tmp_path / "run.json"
        artifact.write_text("{}", encoding="utf-8")

        class RedeployingBackend(FakeBackendRunner):
            def run(self, *args, **kwargs):
                result = super().run(*args, **kwargs)
                fingerprints.deploy_salt = "redeployed"
                return result

        backend = RedeployingBackend(
            stdout=OK_GATE_STDOUT,
            artifacts=FakeArtifactSet(run_artifact=artifact),
        )
        runner = make_gate_runner(
            tmp_path,
            fingerprints=fingerprints,
            backend=backend,
        )
        manifest = self._deployment_manifest(tmp_path, config, fingerprints)

        result = runner.run_gate(config, FakeSpec())

        assert result.valid is True
        assert json.loads(manifest.read_text(encoding="utf-8"))["runtime_health_status"] == "unverified"

    def test_arbitrary_target_method_is_rejected_before_backend(self, tmp_path):
        config = FakeConfig()
        config.target.method = "arbitrary_method"
        backend = FakeBackendRunner(stdout=OK_GATE_STDOUT)
        runner = make_gate_runner(tmp_path, backend=backend)
        with pytest.raises(GateError, match="non-Golden profiles"):
            runner.run_gate(config, FakeSpec())
        assert backend.invocation_count == 0

    def test_golden_target_uses_dedicated_harness_selector(self, tmp_path):
        config = FakeConfig(profile_name="golden_p1")
        config.target.app = "stable-modal-comfy-v2-golden-p1"
        config.target.method = "run_golden_serial_stream"
        artifact = tmp_path / "run_1.json"
        artifact.write_text("{}", encoding="utf-8")
        backend = FakeBackendRunner(
            stdout=OK_GATE_STDOUT,
            artifacts=FakeArtifactSet(run_artifact=artifact),
        )
        runner = make_gate_runner(tmp_path, backend=backend)

        result = runner.run_gate(config, FakeSpec())

        assert result.valid is True
        invocation = backend.invocations[0]
        assert invocation["config"] is config
        assert invocation["extra_args"] == ["--run-count", "1"]

    def test_exactly_one_invocation_with_benchmark_env(self, tmp_path):
        artifact = tmp_path / "run_1.json"
        artifact.write_text("{}", encoding="utf-8")
        backend = FakeBackendRunner(
            stdout=OK_GATE_STDOUT,
            artifacts=FakeArtifactSet(run_artifact=artifact),
        )
        runner = make_gate_runner(tmp_path, backend=backend)
        config = FakeConfig()
        config.workload.expected_output_sha = SHA_20B1
        result = runner.run_gate(config, FakeSpec())

        assert backend.invocation_count == 1
        invocation = backend.invocations[0]
        assert invocation["extra_env"].get("V2_BENCHMARK_RUNS") == "1"
        assert invocation["extra_args"] == ["--run-count", "1"]
        assert result.valid is True
        assert result.reasons == []
        assert result.manifest_path is not None and result.manifest_path.is_file()
        assert result.run is not None
        assert result.run.backend_ok is True
        assert result.run.output_sha == SHA_20B1

    def test_gate_propagates_resolved_canonical_identity(self, tmp_path):
        artifact = tmp_path / "run_1.json"
        artifact.write_text("{}", encoding="utf-8")
        backend = FakeBackendRunner(
            stdout=OK_GATE_STDOUT,
            artifacts=FakeArtifactSet(run_artifact=artifact),
        )
        config = FakeConfig()
        runner = make_gate_runner(tmp_path, backend=backend)

        runner.run_gate(config, FakeSpec())

        env = backend.invocations[0]["extra_env"]
        assert env["COMFYMODAL_V2_APP_NAME"] == config.target.app
        assert env["COMFYMODAL_V2_CLASS_NAME"] == config.target.class_name
        assert env["COMFYMODAL_V2_GPU"] == config.resources.gpu
        assert env["COMFYMODAL_V2_MEMORY_MB"] == str(config.resources.memory_mb)
        assert env["COMFYMODAL_V2_CPU_REQUEST"] == str(config.resources.cpu)
        assert env["COMFYMODAL_V2_BASELINE_MEMORY_REQUEST"] == str(config.resources.memory_mb)
        assert env["COMFYMODAL_V2_BASELINE_CPU_REQUEST"] == str(config.resources.cpu)

    def test_golden_identity_mismatch_fails_before_backend(self, tmp_path):
        config = FakeConfig(profile_name="golden_p1")
        config.target.app = "p4-n-golden-truecold"
        config.target.class_name = "WrongEntrypoint"
        config.target.method = "run_golden_serial_stream"
        backend = FakeBackendRunner(stdout=OK_GATE_STDOUT)
        runner = make_gate_runner(tmp_path, backend=backend)

        with pytest.raises(GateError, match="target.class_name"):
            runner.run_gate(config, FakeSpec())
        assert backend.invocation_count == 0

    def test_golden_identity_allows_explicit_experimental_app(self, tmp_path):
        config = FakeConfig(profile_name="golden_p1")
        config.target.app = "p4-n-golden-truecold"
        config.target.method = "run_golden_serial_stream"
        artifact = tmp_path / "run_1.json"
        artifact.write_text("{}", encoding="utf-8")
        backend = FakeBackendRunner(
            stdout=OK_GATE_STDOUT,
            artifacts=FakeArtifactSet(run_artifact=artifact),
        )
        runner = make_gate_runner(tmp_path, backend=backend)

        result = runner.run_gate(config, FakeSpec())

        assert result.valid is True
        assert backend.invocations[0]["extra_env"]["COMFYMODAL_V2_APP_NAME"] == "p4-n-golden-truecold"

    def test_manifest_persisted_even_when_invalid(self, tmp_path):
        backend = FakeBackendRunner(
            stdout="request_id=r1\ncorrelation_id=c1\n",
            artifacts=FakeArtifactSet(run_artifact=tmp_path / "missing-run.json"),
            mode="fail",
            exit_code=1,
        )
        runner = make_gate_runner(tmp_path, backend=backend)
        result = runner.run_gate(FakeConfig(), FakeSpec())
        assert result.valid is False
        assert result.reasons
        assert result.manifest_path is not None and result.manifest_path.is_file()
        data = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        assert data["gate_valid"] is False
        assert data["reasons"]
        assert data["schema_version"] == 1
        assert "config_snapshot" in data
        assert data["config_snapshot"]["deploy_fingerprint"] == runner._fingerprints.deploy_fingerprint()
        assert data["run"]["backend_ok"] is False

    def test_backend_failure_without_artifact_reports_exit_code(self, tmp_path):
        backend = FakeBackendRunner(
            stderr="argparse: missing --conditioning-cache-nonce",
            artifacts=FakeArtifactSet(),
            mode="fail",
            exit_code=2,
        )
        runner = make_gate_runner(tmp_path, backend=backend)
        result = runner.run_gate(FakeConfig(), FakeSpec())
        reasons = "\n".join(result.reasons)
        assert "without producing a persisted run artifact" in reasons
        assert "exit code 2" in reasons
        assert "persisted run artifact missing" in reasons

    def test_manifest_shape(self, tmp_path):
        artifact = tmp_path / "run_1.json"
        artifact.write_text("{}", encoding="utf-8")
        backend = FakeBackendRunner(stdout=OK_GATE_STDOUT, artifacts=FakeArtifactSet(run_artifact=artifact))
        runner = make_gate_runner(tmp_path, backend=backend)
        result = runner.run_gate(FakeConfig(), FakeSpec())
        data = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        assert set(data) >= {"schema_version", "gate_valid", "reasons", "run", "config_snapshot", "created_at"}
        snapshot = data["config_snapshot"]
        assert set(snapshot) >= {"profile", "git_head", "target", "resources", "deploy_fingerprint", "run_fingerprint"}

    def test_backend_failure_raises_gate_error(self, tmp_path):
        backend = FakeBackendRunner(mode="raise")
        runner = make_gate_runner(tmp_path, backend=backend)
        with pytest.raises(GateError):
            runner.run_gate(FakeConfig(), FakeSpec())

    def test_latest_gate_returns_newest(self, tmp_path):
        runner = make_gate_runner(tmp_path)
        assert runner.latest_gate() is None
        result = runner.run_gate(FakeConfig(), FakeSpec())
        assert runner.latest_gate() == result.manifest_path


class TestConfirmRunner:
    def _run_valid_gate(self, tmp_path):
        artifact = tmp_path / "run_1.json"
        artifact.write_text("{}", encoding="utf-8")
        backend = FakeBackendRunner(stdout=OK_GATE_STDOUT, artifacts=FakeArtifactSet(run_artifact=artifact))
        fingerprints = FakeFingerprints(
            inputs={
                "git_head": "0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997",
                "target": {"app": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypointV2", "method": "run_plan_stream"},
                "resources": {"gpu": "rtx-pro-6000"},
                "profile": "production",
                "deploy_flags": {"COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0"},
            }
        )
        gate = make_gate_runner(tmp_path, fingerprints=fingerprints, backend=backend)
        config = FakeConfig()
        config.workload.expected_output_sha = SHA_20B1
        gate_result = gate.run_gate(config, FakeSpec())
        assert gate_result.valid is True
        return fingerprints, config, gate_result.manifest_path

    def test_confirm_runs_exactly_runs_times_on_valid_gate(self, tmp_path):
        fingerprints, config, manifest = self._run_valid_gate(tmp_path)
        artifact = tmp_path / "run_1.json"
        backend = FakeBackendRunner(stdout=OK_GATE_STDOUT, artifacts=FakeArtifactSet(run_artifact=artifact))
        confirm = make_confirm_runner(tmp_path, fingerprints=fingerprints, backend=backend)
        result = confirm.confirm(manifest, config, FakeSpec(), runs=3)
        assert backend.invocation_count == 3
        for invocation in backend.invocations:
            assert invocation["extra_env"].get("V2_BENCHMARK_RUNS") == "1"
            assert invocation["extra_args"] == ["--run-count", "1"]
        assert result.valid is True
        assert result.manifest_path is not None and result.manifest_path.is_file()
        data = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        assert data["confirm_runs"] == 3
        assert data["gate_manifest"] == str(Path(manifest))

    def test_confirm_propagates_resolved_canonical_identity(self, tmp_path):
        fingerprints, config, manifest = self._run_valid_gate(tmp_path)
        backend = FakeBackendRunner(
            stdout=OK_GATE_STDOUT,
            artifacts=FakeArtifactSet(run_artifact=tmp_path / "run_1.json"),
        )
        confirm = make_confirm_runner(tmp_path, fingerprints=fingerprints, backend=backend)

        confirm.confirm(manifest, config, FakeSpec(), runs=2)

        for invocation in backend.invocations:
            env = invocation["extra_env"]
            assert env["COMFYMODAL_V2_APP_NAME"] == config.target.app
            assert env["COMFYMODAL_V2_CLASS_NAME"] == config.target.class_name
            assert env["COMFYMODAL_V2_GPU"] == config.resources.gpu
            assert env["COMFYMODAL_V2_MEMORY_MB"] == str(config.resources.memory_mb)
            assert env["COMFYMODAL_V2_CPU_REQUEST"] == str(config.resources.cpu)
            assert env["COMFYMODAL_V2_BASELINE_MEMORY_REQUEST"] == str(config.resources.memory_mb)
            assert env["COMFYMODAL_V2_BASELINE_CPU_REQUEST"] == str(config.resources.cpu)

    def test_confirm_rejects_missing_golden_identity_before_backend(self, tmp_path):
        config = FakeConfig(profile_name="golden_p1")
        config.target.app = "stable-modal-comfy-v2-golden-p1"
        config.target.method = "run_golden_serial_stream"
        artifact = tmp_path / "run_1.json"
        artifact.write_text("{}", encoding="utf-8")
        fingerprints = FakeFingerprints()
        gate_backend = FakeBackendRunner(
            stdout=OK_GATE_STDOUT,
            artifacts=FakeArtifactSet(run_artifact=artifact),
        )
        gate = make_gate_runner(tmp_path, fingerprints=fingerprints, backend=gate_backend)
        gate_result = gate.run_gate(config, FakeSpec())
        assert gate_result.valid is True
        manifest = gate_result.manifest_path
        assert manifest is not None

        config.resources.gpu = ""
        confirm_backend = FakeBackendRunner(stdout=OK_GATE_STDOUT)
        confirm = make_confirm_runner(
            tmp_path, fingerprints=fingerprints, backend=confirm_backend
        )
        with pytest.raises(GateError, match="canonical identity"):
            confirm.confirm(manifest, config, FakeSpec())
        assert confirm_backend.invocation_count == 0

    def test_e28_selector_and_nonce_are_forwarded_to_gate_and_confirm(self, tmp_path):
        config = FakeConfig()
        config.flags.append(FakeFlag(name="V2_E28_VALIDATION", value="1"))
        config.workload.nonce = "e28-test-nonce"
        artifact = tmp_path / "run_1.json"
        artifact.write_text("{}", encoding="utf-8")
        backend = FakeBackendRunner(
            stdout=OK_GATE_STDOUT,
            artifacts=FakeArtifactSet(run_artifact=artifact),
        )
        fingerprints = FakeFingerprints()
        gate = make_gate_runner(tmp_path, fingerprints=fingerprints, backend=backend)
        gate_result = gate.run_gate(config, FakeSpec())
        assert gate_result.valid is True
        gate_call = backend.invocations[0]
        expected_args = [
            "E28_VALIDATION", "--run-count", "1",
            "--conditioning-cache-nonce", "e28-test-nonce",
        ]
        assert gate_call["extra_args"] == expected_args
        assert gate_call["extra_env"]["V2_E28_CONDITIONING_NONCE"] == "e28-test-nonce"

        backend.invocations.clear()
        confirm = make_confirm_runner(tmp_path, fingerprints=fingerprints, backend=backend)
        confirm.confirm(gate_result.manifest_path, config, FakeSpec())
        assert backend.invocations[0]["extra_args"] == expected_args
        assert backend.invocations[0]["extra_env"]["V2_E28_CONDITIONING_NONCE"] == "e28-test-nonce"

    def test_confirm_runs_are_single_run_even_with_e28_selector(self, tmp_path):
        fingerprints, config, manifest = self._run_valid_gate(tmp_path)
        config.flags.append(FakeFlag(name="V2_E28_VALIDATION", value="1"))
        config.workload.nonce = "e28-test-nonce"
        backend = FakeBackendRunner(
            stdout=OK_GATE_STDOUT,
            artifacts=FakeArtifactSet(run_artifact=tmp_path / "run_1.json"),
        )
        confirm = make_confirm_runner(tmp_path, fingerprints=fingerprints, backend=backend)
        # The gate manifest is valid, but the selector is resolved from the
        # current config and every confirmation remains a one-run invocation.
        result = confirm.confirm(manifest, config, FakeSpec(), runs=3)
        assert result.valid is True
        assert len(backend.invocations) == 3
        assert all(call["extra_env"]["V2_BENCHMARK_RUNS"] == "1" for call in backend.invocations)
        assert all(call["extra_args"][1:3] == ["--run-count", "1"] for call in backend.invocations)

    def test_confirm_refuses_snapshot_restore_only_mode(self, tmp_path):
        config = FakeConfig()
        config.flags.append(FakeFlag(name="V2_BENCHMARK_MODE", value="snapshot_restore_only"))
        confirm = make_confirm_runner(tmp_path)
        with pytest.raises(GateError, match="snapshot_restore_only"):
            confirm.confirm(tmp_path / "missing-gate.json", config, FakeSpec())

    def test_confirm_default_runs_once(self, tmp_path):
        fingerprints, config, manifest = self._run_valid_gate(tmp_path)
        artifact = tmp_path / "run_1.json"
        backend = FakeBackendRunner(stdout=OK_GATE_STDOUT, artifacts=FakeArtifactSet(run_artifact=artifact))
        confirm = make_confirm_runner(tmp_path, fingerprints=fingerprints, backend=backend)
        result = confirm.confirm(manifest, config, FakeSpec())
        assert backend.invocation_count == 1
        assert result.valid is True

    def test_confirm_refuses_missing_manifest(self, tmp_path):
        confirm = make_confirm_runner(tmp_path)
        with pytest.raises(GateError):
            confirm.confirm(tmp_path / "nope.json", FakeConfig(), FakeSpec())

    def test_confirm_refuses_invalid_gate_manifest(self, tmp_path):
        fingerprints, config, manifest = self._run_valid_gate(tmp_path)
        data = json.loads(Path(manifest).read_text(encoding="utf-8"))
        data["gate_valid"] = False
        invalid_path = tmp_path / "invalid_gate.json"
        invalid_path.write_text(json.dumps(data), encoding="utf-8")
        confirm = make_confirm_runner(tmp_path, fingerprints=fingerprints)
        with pytest.raises(GateError) as excinfo:
            confirm.confirm(invalid_path, config, FakeSpec())
        assert "invalid" in str(excinfo.value).lower()



    def test_confirm_refuses_wrong_schema(self, tmp_path):
        fingerprints, config, manifest = self._run_valid_gate(tmp_path)
        data = json.loads(Path(manifest).read_text(encoding="utf-8"))
        data["schema_version"] = 99
        bad = tmp_path / "bad_schema.json"
        bad.write_text(json.dumps(data), encoding="utf-8")
        confirm = make_confirm_runner(tmp_path, fingerprints=fingerprints)
        with pytest.raises(GateError):
            confirm.confirm(bad, config, FakeSpec())


class TestBuildRunRecord:
    def test_build_from_result(self, tmp_path):
        artifact = tmp_path / "run_1.json"
        artifact.write_text("{}", encoding="utf-8")
        result = FakeBackendRunner(
            stdout=OK_GATE_STDOUT, artifacts=FakeArtifactSet(run_artifact=artifact)
        ).run(FakeSpec(), config=FakeConfig())
        config = FakeConfig()
        config.workload.expected_output_sha = SHA_20B1
        record = build_run_record_from_result(result, config, "d" * 64, "r" * 64)
        assert record.backend_ok is True
        assert record.profile == "production"
        assert record.fresh_required is True
        assert record.output_sha == SHA_20B1
        assert record.telemetry["request_id"] == "req-0001"
        assert record.run_fingerprint == "r" * 64
        assert record.deploy_fingerprint == "d" * 64


class TestCanonicalLedgerValidator:
    """E29: the canonical ledger is the authoritative payload; a run with a
    missing/errored ledger must never pass the tracer gate, and the validator
    must NOT require ledger events inside ordinary trace.events."""

    def _config_with_ledger_on(self) -> FakeConfig:
        config = FakeConfig()
        config.flags.append(FakeFlag(name="COMFYMODAL_V2_CRITICAL_PATH_LEDGER", value="1"))
        return config

    def _record(self, artifact_data: dict, tmp_path: Path) -> RunRecord:
        artifact = tmp_path / "run_1.json"
        artifact.write_text(json.dumps(artifact_data), encoding="utf-8")
        result = FakeBackendRunner(
            stdout="request_id=req-0001\ncorrelation_id=corr-0001\nfresh=1\nrestored=0\n",
            artifacts=FakeArtifactSet(run_artifact=artifact),
        ).run(FakeSpec(), config=FakeConfig())
        return build_run_record_from_result(result, FakeConfig(), "d" * 64, "r" * 64)

    def test_missing_ledger_fails(self, tmp_path):
        record = self._record({"request_id": "req-0001"}, tmp_path)
        failures = CanonicalLedgerValidator().validate(record, self._config_with_ledger_on())
        assert any("canonical ledger missing" in f for f in failures)

    def test_error_status_fails(self, tmp_path):
        record = self._record(
            {"canonical_ledger_status": "error", "canonical_ledger_error": {"stage": "finalize"}},
            tmp_path,
        )
        failures = CanonicalLedgerValidator().validate(record, self._config_with_ledger_on())
        assert any("errored" in f for f in failures)

    def test_missing_endpoints_fails(self, tmp_path):
        record = self._record(
            {
                "canonical_ledger_status": "ok",
                "canonical_ledger": {"endpoint_status": "missing", "serial_ledger": None},
            },
            tmp_path,
        )
        failures = CanonicalLedgerValidator().validate(record, self._config_with_ledger_on())
        assert any("endpoint_status" in f for f in failures)

    def test_zero_gap_false_fails(self, tmp_path):
        record = self._record(
            {
                "canonical_ledger_status": "ok",
                "canonical_ledger": {
                    "endpoint_status": "ok",
                    "serial_ledger": {"zero_gap": False},
                },
            },
            tmp_path,
        )
        failures = CanonicalLedgerValidator().validate(record, self._config_with_ledger_on())
        assert any("zero-gap" in f for f in failures)

    def test_ok_ledger_passes(self, tmp_path):
        record = self._record(
            {
                "canonical_ledger_status": "ok",
                "canonical_ledger": {
                    "endpoint_status": "ok",
                    "serial_ledger": {"zero_gap": True},
                },
            },
            tmp_path,
        )
        failures = CanonicalLedgerValidator().validate(record, self._config_with_ledger_on())
        assert failures == []

    def test_ledger_off_profile_passes_without_ledger(self, tmp_path):
        # Ledger flag OFF → validator must NOT fail on a missing ledger.
        record = self._record({"request_id": "req-0001"}, tmp_path)
        config = FakeConfig()  # no flag → off
        failures = CanonicalLedgerValidator().validate(record, config)
        assert failures == []

    def test_does_not_require_ledger_events_in_trace_events(self, tmp_path):
        # The E29 ledger lives in data["canonical_ledger"], NOT in
        # trace.events — a passing artifact must not need modal_restore_entry
        # etc. inside ordinary RuntimeTrace events.
        record = self._record(
            {
                "canonical_ledger_status": "ok",
                "canonical_ledger": {
                    "endpoint_status": "ok",
                    "serial_ledger": {"zero_gap": True},
                },
                "trace": {"events": []},  # ordinary trace has NO ledger events
            },
            tmp_path,
        )
        failures = CanonicalLedgerValidator().validate(record, self._config_with_ledger_on())
        assert failures == []


class TestE31ForensicsValidator:
    """The E31 control-plane gate consumes canonical, not hydration, proof."""

    def _config(self, cast_once: str = "0") -> FakeConfig:
        config = FakeConfig(profile_name="e31-clip-fp32-fastsafe-arm-a")
        config.workload.expected_output_sha = SHA_20B1
        config.workload.conditioning_cache = "forced_miss"
        config.flags.extend(
            [
                FakeFlag(name="COMFYMODAL_V2_E31_FORENSICS", value="1"),
                FakeFlag(name="COMFYMODAL_V2_CLIP_FP32_CAST_ONCE", value=cast_once),
            ]
        )
        return config

    def _record(self, tmp_path: Path, config: FakeConfig, *, on: bool = False,
                canonical_events: list[dict] | None = None,
                trace_events: list[dict] | None = None) -> RunRecord:
        artifact_data = {
            "canonical_ledger_status": "ok",
            "canonical_ledger": {
                "endpoint_status": "ok",
                "serial_ledger": {"zero_gap": True},
                "events": canonical_events or [],
            },
            "trace": {"events": trace_events or []},
            "output_sha": SHA_20B1,
            "request_id": "req-0001",
        }
        artifact = tmp_path / ("e31_on.json" if on else "e31_off.json")
        artifact.write_text(json.dumps(artifact_data), encoding="utf-8")
        result = FakeBackendRunner(
            stdout=(
                "request_id=req-0001\ncorrelation_id=corr-0001\nfresh=1\n"
                f"output_sha={SHA_20B1}\n"
            ),
            artifacts=FakeArtifactSet(run_artifact=artifact),
        ).run(FakeSpec(), config=config)
        return build_run_record_from_result(result, config, "d" * 64, "r" * 64)

    @staticmethod
    def _canonical(summary: dict) -> list[dict]:
        return [
            {"name": "clip_gpu_event_start", "mono_ns": 1},
            {"name": "clip_gpu_event_end", "mono_ns": 2},
            {"name": "clip_forward_cast_summary", "metadata": summary},
        ]

    @staticmethod
    def _cache_events() -> list[dict]:
        return [
            {
                "name": "clip_conditioning_cache_lookup",
                "metadata": {"miss_count": 1, "hit_count": 0},
            },
            {
                "name": "clip_conditioning_cache_decision",
                "metadata": {"decision": "miss"},
            },
        ]

    def test_missing_authoritative_e31_evidence_fails_closed(self, tmp_path):
        config = self._config()
        record = self._record(tmp_path, config, trace_events=self._cache_events())
        failures = E31ForensicsValidator().validate(record, config)
        assert any("canonical ledger" in failure for failure in failures)

    def test_valid_off_requires_real_bf16_fp32_count_and_bytes(self, tmp_path):
        config = self._config("0")
        record = self._record(
            tmp_path,
            config,
            canonical_events=self._canonical({
                "real_conversions": 2,
                "real_conversion_bytes": 128,
                "source_dtypes": {"torch.bfloat16": 2},
                "dest_dtypes": {"torch.float32": 2},
            }),
            trace_events=self._cache_events(),
        )
        assert E31ForensicsValidator().validate(record, config) == []

    def test_valid_on_requires_bind_residency_and_stable_forward(self, tmp_path):
        config = self._config("1")
        generation = 7
        trace = self._cache_events() + [
            {
                "name": "clip_fh_cast_once_bind_proof",
                "metadata": {
                    "ok": True,
                    "phase": "post_bind",
                    "generation": generation,
                    "count_by_dtype": {"torch.float32": 2},
                    "device_counts": {"cuda:0": 2},
                },
            },
            {
                "name": "clip_fh_cast_once_applied",
                "metadata": {"generation": generation, "fp32_params": 2},
            },
            {
                "name": "clip_fh_cast_once_forward_check",
                "metadata": {
                    "forward_observed": True,
                    "forward_actually_observed": True,
                    "bind_generation": generation,
                    "post_forward_generation": generation,
                    "storage_stable": True,
                    "post_forward_stability": {"storage_stable": True},
                },
            },
        ]
        record = self._record(
            tmp_path,
            config,
            on=True,
            canonical_events=self._canonical({
                "real_conversions": 0,
                "real_conversion_bytes": 0,
            }),
            trace_events=trace,
        )
        assert E31ForensicsValidator().validate(record, config) == []

    @pytest.mark.parametrize("bind_generation", [None, 0, 2])
    def test_on_rejects_missing_or_stale_bind_generation(self, tmp_path, bind_generation):
        config = self._config("1")
        bind = {
            "ok": True,
            "count_by_dtype": {"torch.float32": 398},
            "device_counts": {"cuda:0": 398},
        }
        if bind_generation is not None:
            bind["generation"] = bind_generation
        trace = self._cache_events() + [
            {"name": "clip_fh_cast_once_bind_proof", "metadata": bind},
            {
                "name": "clip_fh_cast_once_applied",
                "metadata": {"generation": 1, "fp32_params": 398},
            },
            {
                "name": "clip_fh_cast_once_forward_check",
                "metadata": {
                    "forward_observed": True,
                    "forward_actually_observed": True,
                    "bind_generation": 1,
                    "post_forward_generation": 1,
                    "storage_stable": True,
                    "post_forward_stability": {"storage_stable": True},
                },
            },
        ]
        record = self._record(
            tmp_path,
            config,
            on=True,
            canonical_events=self._canonical({
                "real_conversions": 0,
                "real_conversion_bytes": 0,
            }),
            trace_events=trace,
        )

        failures = E31ForensicsValidator().validate(record, config)
        assert any("generation/bind proof" in failure for failure in failures)

    def test_hydration_zero_conversion_is_not_forward_proof(self, tmp_path):
        config = self._config("0")
        record = self._record(
            tmp_path,
            config,
            canonical_events=self._canonical({"conversion_count": 0}),
            trace_events=self._cache_events() + [
                {"name": "clip_fh_cast_once_forward_check",
                 "metadata": {"conversion_count": 0, "conversion_bytes": 0}},
            ],
        )
        failures = E31ForensicsValidator().validate(record, config)
        assert any("real BF16->FP32" in failure for failure in failures)
