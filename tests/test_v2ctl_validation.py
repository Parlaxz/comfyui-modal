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
from pathlib import Path

import pytest

from tools.v2_control.errors import GateError
from tools.v2_control.validation import (
    ConfirmRunner,
    ExpectedOutputShaValidator,
    GateRunner,
    RunRecord,
    StructuralValidator,
    Validator,
    build_run_record_from_result,
    extract_output_sha,
    parse_telemetry,
)

from tests.v2ctl_fakes import (
    OK_GATE_STDOUT,
    FakeArtifactSet,
    FakeBackendRunner,
    FakeConfig,
    FakeFingerprints,
    FakeSpec,
)

SHA_20B1 = "20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260"


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
            telemetry={"request_id": "r1", "correlation_id": "c1", "fresh": "1"},
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


class TestGateRunner:
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
            assert invocation["extra_env"].get("V2_BENCHMARK_RUNS") == "3"
            assert invocation["extra_args"] == ["--run-count", "3"]
        assert result.valid is True
        assert result.manifest_path is not None and result.manifest_path.is_file()
        data = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        assert data["confirm_runs"] == 3
        assert data["gate_manifest"] == str(Path(manifest))

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

    def test_confirm_refuses_stale_fingerprint_listing_changed_inputs(self, tmp_path):
        fingerprints, config, manifest = self._run_valid_gate(tmp_path)
        # change a deploy-relevant flag -> deploy fingerprint changes
        changed = FakeFingerprints(
            inputs={
                "git_head": "0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997",
                "target": {"app": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypointV2", "method": "run_plan_stream"},
                "resources": {"gpu": "rtx-pro-6000"},
                "profile": "production",
                "deploy_flags": {"COMFYMODAL_V2_UNET_FASTSAFETENSORS": "1"},  # changed 0 -> 1
            }
        )
        assert changed.deploy_fingerprint() != fingerprints.deploy_fingerprint()
        confirm = make_confirm_runner(tmp_path, fingerprints=changed)
        with pytest.raises(GateError) as excinfo:
            confirm.confirm(manifest, config, FakeSpec())
        message = str(excinfo.value)
        assert "changed" in message.lower()
        assert "COMFYMODAL_V2_UNET_FASTSAFETENSORS" in message

    def test_confirm_refuses_git_head_change(self, tmp_path):
        fingerprints, config, manifest = self._run_valid_gate(tmp_path)
        changed_head = FakeFingerprints(
            inputs={
                "git_head": "ffffffffffffffffffffffffffffffffffffffff",
                "target": {"app": "stable-modal-comfy-v2-restore-only-shadow", "class_name": "ModalRuntimeEntrypointV2", "method": "run_plan_stream"},
                "resources": {"gpu": "rtx-pro-6000"},
                "profile": "production",
                "deploy_flags": {"COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0"},
            }
        )
        confirm = make_confirm_runner(tmp_path, fingerprints=changed_head)
        with pytest.raises(GateError) as excinfo:
            confirm.confirm(manifest, config, FakeSpec())
        assert "git" in str(excinfo.value).lower()

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
