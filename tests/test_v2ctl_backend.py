"""Agent B tests: tools/v2_control/backend.py (Batch E32).

Covers (contract §21 subset):
- BackendRegistry canonical / deploy_only / run_only / by_name / available;
- backend argv/env and exit propagation via a tiny fake backend created in
  tmp_path (win32: a .cmd file; posix: an executable python shebang script);
- child env passed to the fake backend (echo an env var);
- stdout captured, exit code propagated;
- artifact discovery (fake run_001_validation.json + campaign_manifest.json
  in tmp .comfymodal_experiments; empty -> ArtifactSet all None);
- build_command_line quoting (pure function).

Python 3.11 stdlib + pytest only; no network, no modal/deploy invocations.
"""

from __future__ import annotations

import os
import sys
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.v2_control.backend as backend_module  # noqa: E402
from tools.v2_control.backend import (  # noqa: E402
    ArtifactSet,
    BackendRegistry,
    BackendResult,
    BackendRunner,
    BackendSpec,
    detect_crash_loop,
)
from tools.v2_control.environment import EnvironmentBuilder  # noqa: E402
from tools.v2_control.errors import BackendError, ProvenanceError  # noqa: E402
from tools.v2_control.fingerprints import FingerprintEngine  # noqa: E402
from tools.v2_control.validation import (  # noqa: E402
    ExpectedOutputShaValidator,
    build_run_record_from_result,
)


# ---------------------------------------------------------------------------
# Minimal ResolvedConfig duck-type
# ---------------------------------------------------------------------------


@dataclass
class _Target:
    app: str = "stable-modal-comfy-v2-restore-only-shadow"
    class_name: str = "ModalRuntimeEntrypointV2"
    method: str = "run_plan_stream"


@dataclass
class _Resources:
    gpu: str = "rtx-pro-6000"
    cpu: int = 12
    memory_mb: int = 32768
    min_containers: int = 0
    scaledown_window: int = 4


@dataclass
class _Workload:
    fresh_required: bool = True
    conditioning_cache: str = "forced_miss"
    expected_output_sha: str = ""
    run_count: int = 10
    gap_seconds: float = 35.0
    nonce: str = "test-nonce"


@dataclass
class _Git:
    head: str = "0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997"
    branch: str = "main"
    dirty: bool = False
    dirty_hashes: dict = field(default_factory=dict)


@dataclass
class _Flag:
    name: str
    value: str
    source: str = "profile:production"
    registered: bool = True
    consumed_at: str = "request"
    change_requires: str = "run"
    type: str = "bool"
    description: str = ""


@dataclass
class _Config:
    profile_name: str = "production"
    owner: str = "v2-core"
    target: _Target = field(default_factory=_Target)
    resources: _Resources = field(default_factory=_Resources)
    workload: _Workload = field(default_factory=_Workload)
    flags: list = field(default_factory=list)
    unregistered: list = field(default_factory=list)
    runtime_override_policy: str = "forbid"
    git: _Git = field(default_factory=_Git)


def _host_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items()}


# ---------------------------------------------------------------------------
# Fake backend helpers
# ---------------------------------------------------------------------------


def _write_fake_backend(tmp_path: Path) -> Path:
    """Create a tiny backend that echoes an env var and exits with a code.

    The exit code defaults to 3 and can be overridden through the
    FAKE_BACKEND_EXIT env var.  On win32 a .cmd file is created; on posix an
    executable python shebang script.  Returns the backend path.
    """
    fake_dir = tmp_path / "fake_backend"
    fake_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path = fake_dir / "fake_backend.cmd"
        content = (
            "@echo off\r\n"
            "echo VAR=%FAKE_BACKEND_VAR%\r\n"
            "echo INVOCATION=%COMFYMODAL_V2CTL_INVOCATION_ID%\r\n"
            "echo ARGS=%*\r\n"
            "if defined FAKE_BACKEND_EXIT exit /b %FAKE_BACKEND_EXIT%\r\n"
            "exit /b 3\r\n"
        )
        path.write_text(content, encoding="ascii")
    else:
        path = fake_dir / "fake_backend.sh"
        path.write_text(
            "#!/bin/sh\n"
            'echo "VAR=$FAKE_BACKEND_VAR"\n'
            'echo "INVOCATION=$COMFYMODAL_V2CTL_INVOCATION_ID"\n'
            'echo "ARGS=$*"\n'
            'exit "${FAKE_BACKEND_EXIT:-3}"\n',
            encoding="ascii",
        )
        path.chmod(0o755)
    return path


def _fake_spec(tmp_path: Path) -> BackendSpec:
    return BackendSpec(
        name="fake_backend",
        bat_path=_write_fake_backend(tmp_path),
        kind="test_fake",
        description="tiny fake backend for tests",
    )


def _clean_env() -> dict[str, str]:
    """Minimal host env: only required host vars, no ambient COMFYMODAL_*."""
    env = _host_env()
    for key in [k for k in env if k.startswith(("COMFYMODAL_", "V2_", "FAKE_BACKEND_"))]:
        env.pop(key)
    return env


def test_runner_never_leaks_ambient_experimental_env(monkeypatch, tmp_path):
    """Ambient COMFYMODAL_V2_*/V2_* from the caller shell must not reach the
    child backend env; only explicitly-passed extra_env vars do."""
    spec = _fake_spec(tmp_path)
    # strip ambient experimental vars (keep required host vars like COMSPEC)
    for key in list(os.environ):
        if key.startswith(("COMFYMODAL_", "V2_", "FAKE_BACKEND_")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("COMFYMODAL_V2_SOMETHING", "1")
    monkeypatch.setenv("V2_X", "2")
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    result = runner.run(
        spec,
        config=_Config(),
        extra_env={"FAKE_BACKEND_VAR": "only-this", "FAKE_BACKEND_EXIT": "0"},
    )
    assert result.exit_code == 0
    assert "VAR=only-this" in result.stdout
    # ambient experimental values never reach the child env
    assert "COMFYMODAL_V2_SOMETHING" not in result.stdout
    assert "V2_X" not in result.stdout


# ---------------------------------------------------------------------------
# BackendRegistry
# ---------------------------------------------------------------------------


def test_registry_canonical_spec(tmp_path):
    registry = BackendRegistry(tmp_path)
    spec = registry.canonical()
    assert spec.name == "deploy_and_run_v2_single"
    assert spec.bat_path == tmp_path / "deploy_and_run_v2_single.bat"
    assert spec.kind == "combined"
    assert spec.deploy_only_env == {}


def test_registry_deploy_only_spec(tmp_path):
    registry = BackendRegistry(tmp_path)
    spec = registry.deploy_only()
    assert spec.name == "deploy_and_run_v2_single_deploy_only"
    assert spec.kind == "deploy_only_via_env"
    assert spec.deploy_only_env == {"COMFYMODAL_DEPLOY_ONLY": "1"}


def test_registry_run_only_spec(tmp_path):
    registry = BackendRegistry(tmp_path)
    spec = registry.run_only()
    assert spec.name == "run_v2_single"
    assert spec.bat_path == tmp_path / "run_v2_single.bat"
    assert spec.kind == "run"


def test_registry_by_name(tmp_path):
    registry = BackendRegistry(tmp_path)
    assert registry.by_name("deploy_and_run_v2_single").kind == "combined"
    assert registry.by_name("run_v2_single").kind == "run"
    with pytest.raises(KeyError):
        registry.by_name("no_such_backend")


def test_registry_available_empty_when_bats_missing(tmp_path):
    # tmp_path has no BAT files -> available() returns []
    assert BackendRegistry(tmp_path).available() == []


# ---------------------------------------------------------------------------
# build_command_line (pure)
# ---------------------------------------------------------------------------


def test_build_command_line_win32_quotes_bat_and_args():
    spec = BackendSpec(name="x", bat_path=Path(r"C:\some dir\run_v2_single.bat"))
    if os.name == "nt":
        line = BackendRunner.build_command_line(spec, ["--run-count", "3", "--set", "A=B C"])
        assert line.startswith('"C:\\some dir\\run_v2_single.bat" ')
        assert "--run-count" in line
        assert '"A=B C"' in line
    else:
        line = BackendRunner.build_command_line(spec, ["--run-count", "3"])
        assert line.startswith("/some dir/run_v2_single.bat") or line.startswith("C:\\some dir\\run_v2_single.bat")


def test_build_command_line_executable_list():
    spec = BackendSpec(name="x", executable=[sys.executable, "-c", "pass"])
    line = BackendRunner.build_command_line(spec, ["--foo"])
    assert "--foo" in line
    assert line  # non-empty


def test_build_command_line_is_pure():
    spec = BackendSpec(name="x", bat_path=Path("a b.bat"))
    a = BackendRunner.build_command_line(spec, ["--x", "1"])
    b = BackendRunner.build_command_line(spec, ["--x", "1"])
    assert a == b
    assert "--x" in a and "1" in a


@pytest.mark.parametrize("selector", ["E31_VALIDATION", "E28_VALIDATION"])
def test_windows_bat_invocation_preserves_selector(monkeypatch, tmp_path, selector):
    """Windows BAT calls use cmd.exe argv, keeping the selector positional."""
    spec = BackendSpec(
        name="validation",
        bat_path=tmp_path / "deploy_and_run_v2_single.bat",
    )
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    # Patch the backend module's platform view without changing the process
    # global os.name used by pathlib and pytest.
    monkeypatch.setattr(
        backend_module,
        "os",
        SimpleNamespace(name="nt", environ=os.environ),
    )
    monkeypatch.setattr(backend_module.subprocess, "run", fake_run)

    result = BackendRunner(tmp_path, EnvironmentBuilder()).run(
        spec,
        config=_Config(),
        extra_args=[selector],
        timeout_seconds=12,
    )

    assert result.command == f'"{spec.bat_path}" {selector}'
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == (
        ["cmd.exe", "/d", "/c", "call", str(spec.bat_path), selector],
    )
    assert kwargs["shell"] is False
    assert kwargs["cwd"] == str(tmp_path)
    assert kwargs["timeout"] == 12
    assert kwargs["capture_output"] is True
    assert kwargs["env"]["COMFYMODAL_V2CTL_PROFILE"] == "production"


# ---------------------------------------------------------------------------
# BackendRunner end-to-end with fake backend (argv/env/exit propagation)
# ---------------------------------------------------------------------------


def test_runner_passes_env_and_captures_stdout(tmp_path):
    spec = _fake_spec(tmp_path)
    config = _Config(flags=[_Flag(name="COMFYMODAL_V2_UNET_FASTSAFETENSORS", value="1")])
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    result = runner.run(
        spec,
        config=config,
        extra_args=["--run-count", "3"],
        extra_env={"FAKE_BACKEND_VAR": "hello world", "FAKE_BACKEND_EXIT": "3"},
    )
    assert result.exit_code == 3
    assert "VAR=hello world" in result.stdout
    assert "--run-count" in result.stdout and "3" in result.stdout
    assert result.command  # non-empty command line
    assert result.started_at and result.ended_at
    assert result.elapsed_seconds >= 0.0
    assert result.artifacts is not None
    assert result.v2ctl_invocation_id
    assert f"INVOCATION={result.v2ctl_invocation_id}" in result.stdout


def test_runner_propagates_zero_exit(tmp_path):
    spec = _fake_spec(tmp_path)
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    result = runner.run(
        spec,
        config=_Config(),
        extra_env={"FAKE_BACKEND_VAR": "v", "FAKE_BACKEND_EXIT": "0"},
    )
    assert result.exit_code == 0
    assert result.ok()


def test_runner_propagates_nonzero_exit(tmp_path):
    spec = _fake_spec(tmp_path)
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    result = runner.run(
        spec,
        config=_Config(),
        extra_env={"FAKE_BACKEND_VAR": "v", "FAKE_BACKEND_EXIT": "7"},
    )
    assert result.exit_code == 7
    assert not result.ok()


def test_strict_artifact_failure_keeps_redacted_bounded_child_output(monkeypatch, tmp_path):
    """Strict discovery diagnostics retain both streams without leaking secrets."""
    spec = BackendSpec(name="diagnostic", executable=[sys.executable, "-c", "pass"])
    stdout = "stdout-head\n" + ("x" * 9000) + "\nstdout-tail"
    stderr = "stderr-head api_key=stderr-secret\n"

    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=stdout.encode("utf-8"),
            stderr=stderr.encode("utf-8"),
        )

    monkeypatch.setattr(backend_module.subprocess, "run", fake_run)
    with pytest.raises(ProvenanceError) as raised:
        BackendRunner(tmp_path, EnvironmentBuilder()).run(
            spec,
            config=_Config(),
            extra_env={"CUSTOM_TOKEN": "child-secret"},
            strict_canonical_discovery=True,
            invocation_id="diagnostic-invocation",
        )

    message = str(raised.value)
    assert "no canonical run artifact" in message
    assert "captured stdout (redacted, bounded):" in message
    assert "captured stderr (redacted, bounded):" in message
    assert "stdout-head" in message and "stdout-tail" in message
    assert "<redacted>" in message
    assert "child-secret" not in message
    assert "stderr-secret" not in message
    assert "diagnostic output truncated" in message


def test_runner_merges_spec_deploy_only_env(tmp_path):
    spec = _fake_spec(tmp_path)
    spec.deploy_only_env = {"COMFYMODAL_DEPLOY_ONLY": "1"}
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    result = runner.run(
        spec,
        config=_Config(),
        extra_env={"FAKE_BACKEND_VAR": "v", "FAKE_BACKEND_EXIT": "0"},
    )
    assert result.exit_code == 0


def test_runner_child_env_contains_config_flag(tmp_path):
    """The config flag must be visible to the fake backend as an env var."""
    spec = _fake_spec(tmp_path)
    # backend echoes a flag value placed by EnvironmentBuilder
    flag_path = tmp_path / "echo_flag.cmd" if os.name == "nt" else tmp_path / "echo_flag.sh"
    if os.name == "nt":
        flag_path.write_text(
            "@echo off\r\n"
            "echo FLAG=%COMFYMODAL_V2_UNET_FASTSAFETENSORS%\r\n"
            "exit /b 0\r\n",
            encoding="ascii",
        )
    else:
        flag_path.write_text("#!/bin/sh\necho \"FLAG=$COMFYMODAL_V2_UNET_FASTSAFETENSORS\"\nexit 0\n", encoding="ascii")
        flag_path.chmod(0o755)
    flag_spec = BackendSpec(name="echo_flag", bat_path=flag_path, kind="test_fake")
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    result = runner.run(
        flag_spec,
        config=_Config(flags=[_Flag(name="COMFYMODAL_V2_UNET_FASTSAFETENSORS", value="1")]),
        extra_env={},
    )
    assert result.exit_code == 0
    assert "FLAG=1" in result.stdout


def test_runner_receipt_identity_override_wins_over_local_fingerprints(monkeypatch, tmp_path):
    """A receipt-bound call must not be rewritten with local deploy identity."""
    spec = BackendSpec(name="identity", executable=[sys.executable, "-c", "pass"])
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(backend_module.subprocess, "run", fake_run)
    BackendRunner(tmp_path, EnvironmentBuilder()).run(
        spec,
        config=_Config(),
        canonical_identity={
            "profile": "golden_p1",
            "profile_config_fingerprint": "receipt-profile",
            "deploy_fingerprint": "receipt-deploy",
            "run_fingerprint": "current-request",
        },
    )
    env = calls[0]["env"]
    assert env["COMFYMODAL_V2CTL_PROFILE"] == "golden_p1"
    assert env["COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT"] == "receipt-profile"
    assert env["COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT"] == "receipt-deploy"
    assert env["COMFYMODAL_V2CTL_RUN_FINGERPRINT"] == "current-request"


# ---------------------------------------------------------------------------
# Artifact discovery
# ---------------------------------------------------------------------------


def _make_experiments_dir(tmp_path: Path, name: str = ".comfymodal_experiments") -> Path:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_discover_artifacts_finds_run_and_manifest(tmp_path):
    exp = _make_experiments_dir(tmp_path)
    (exp / "run_001_validation.json").write_text("{}", encoding="utf-8")
    (exp / "campaign_manifest.json").write_text("{}", encoding="utf-8")
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    result = runner.discover_artifacts(_Config(), "")
    assert result.run_artifact is not None
    assert result.run_artifact.name == "run_001_validation.json"
    assert result.run_artifact.parent == exp
    assert result.campaign_manifest is not None
    assert result.campaign_manifest.name == "campaign_manifest.json"
    assert result.output_dir == exp
    assert result.summary_artifact is None
    assert result.console_capture is None


def test_discover_artifacts_binds_exact_invocation_not_newest_mtime(tmp_path):
    exp = _make_experiments_dir(tmp_path)
    old = exp / "run_001_validation.json"
    new = exp / "run_002_validation.json"
    fp = FingerprintEngine(_Config()).profile_config_fingerprint()
    old.write_text(json.dumps({"v2ctl_invocation_id": "old", "profile": "production",
                               "profile_config_fingerprint": fp, "request_id": "old"}), encoding="utf-8")
    new.write_text(json.dumps({"v2ctl_invocation_id": "current", "profile": "production",
                               "profile_config_fingerprint": fp, "request_id": "current"}), encoding="utf-8")
    # Make the unrelated artifact newer: canonical selection must not care.
    old.touch()
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    result = runner.discover_artifacts(_Config(), "", invocation_id="current", strict_canonical=True)
    assert result.run_artifact is not None
    assert result.run_artifact.name == "run_002_validation.json"
    assert result.request_id == "current"




def test_discover_artifacts_only_unbound_artifacts_still_fail(tmp_path):
    exp = _make_experiments_dir(tmp_path)
    (exp / "run_historical.json").write_text(
        json.dumps({"profile": "production"}), encoding="utf-8"
    )
    with pytest.raises(ProvenanceError, match="no canonical run artifact"):
        BackendRunner(tmp_path, EnvironmentBuilder()).discover_artifacts(
            _Config(), "", invocation_id="current", strict_canonical=True,
        )


def test_discover_artifacts_collapses_equivalent_raw_and_sample_projection(tmp_path):
    exp = _make_experiments_dir(tmp_path)
    fp = FingerprintEngine(_Config()).profile_config_fingerprint()
    output_sha = "a" * 64
    ledger = {
        "endpoint_status": "ok",
        "serial_ledger": {"zero_gap": True},
    }
    common = {
        "v2ctl_invocation_id": "current",
        "profile": "production",
        "profile_config_fingerprint": fp,
        "request_id": "same-request",
        "canonical_ledger_status": "ok",
        "canonical_ledger": ledger,
    }
    raw = exp / "run_0.json"
    raw.write_text(
        json.dumps({**common, "result": {"images": [{"asset_id": output_sha, "generation": "generation-1"}]}}),
        encoding="utf-8",
    )
    sample = exp / "run_001_sample.json"
    sample.write_text(
        json.dumps({**common, "output_descriptor": [{"asset_id": output_sha, "generation": "generation-1"}]}),
        encoding="utf-8",
    )

    result = BackendRunner(tmp_path, EnvironmentBuilder()).discover_artifacts(
        _Config(),
        "request_id=same-request\n",
        invocation_id="current",
        strict_canonical=True,
    )

    assert result.run_artifact == sample
    assert result.run_artifacts == [raw, sample]
    record = build_run_record_from_result(
        SimpleNamespace(exit_code=0, stdout="", artifacts=result),
        _Config(workload=_Workload(expected_output_sha=output_sha)),
        "d" * 64,
        "r" * 64,
    )
    assert record.output_sha == output_sha
    assert ExpectedOutputShaValidator().validate(record, _Config(workload=_Workload(expected_output_sha=output_sha))) == []


@pytest.mark.parametrize("different_field", ["output", "generation"])
def test_discover_artifacts_non_equivalent_same_request_remains_ambiguous(
    tmp_path, different_field
):
    exp = _make_experiments_dir(tmp_path)
    fp = FingerprintEngine(_Config()).profile_config_fingerprint()
    common = {
        "v2ctl_invocation_id": "current",
        "profile": "production",
        "profile_config_fingerprint": fp,
        "request_id": "same-request",
        "canonical_ledger_status": "ok",
        "canonical_ledger": {"endpoint_status": "ok"},
    }
    sample_sha = "b" * 64 if different_field == "output" else "a" * 64
    sample_generation = "generation-2" if different_field == "generation" else "generation-1"
    (exp / "run_0.json").write_text(
        json.dumps({**common, "result": {"images": [{"asset_id": "a" * 64, "generation": "generation-1"}]}}),
        encoding="utf-8",
    )
    (exp / "run_001_sample.json").write_text(
        json.dumps({**common, "output_descriptor": [{"asset_id": sample_sha, "generation": sample_generation}]}),
        encoding="utf-8",
    )

    with pytest.raises(ProvenanceError, match="ambiguous canonical run artifacts"):
        BackendRunner(tmp_path, EnvironmentBuilder()).discover_artifacts(
            _Config(),
            "request_id=same-request\n",
            invocation_id="current",
            strict_canonical=True,
        )


def test_discover_artifacts_no_matching_invocation_fails(tmp_path):
    exp = _make_experiments_dir(tmp_path)
    fp = FingerprintEngine(_Config()).profile_config_fingerprint()
    (exp / "run_001_validation.json").write_text(
        json.dumps({"v2ctl_invocation_id": "stale", "profile": "production",
                    "profile_config_fingerprint": fp}), encoding="utf-8"
    )
    with pytest.raises(ProvenanceError, match="no canonical run artifact"):
        BackendRunner(tmp_path, EnvironmentBuilder()).discover_artifacts(
            _Config(), "", invocation_id="current", strict_canonical=True
        )


def test_discover_artifacts_duplicate_matching_request_ids_fail(tmp_path):
    exp = _make_experiments_dir(tmp_path)
    fp = FingerprintEngine(_Config()).profile_config_fingerprint()
    for name, request_id in (("run_a.json", "a"), ("run_b.json", "b")):
        (exp / name).write_text(json.dumps({
            "v2ctl_invocation_id": "current", "profile": "production",
            "profile_config_fingerprint": fp, "request_id": request_id,
        }), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="conflicting request IDs"):
        BackendRunner(tmp_path, EnvironmentBuilder()).discover_artifacts(
            _Config(), "", invocation_id="current", strict_canonical=True,
        )


def test_discover_artifacts_same_invocation_binds_each_request_without_mtime(tmp_path):
    exp = _make_experiments_dir(tmp_path)
    fp = FingerprintEngine(_Config()).profile_config_fingerprint()
    artifacts = {}
    for name, request_id in (("run_a.json", "request-a"), ("run_b.json", "request-b")):
        path = exp / name
        path.write_text(json.dumps({
            "v2ctl_invocation_id": "current",
            "profile": "production",
            "profile_config_fingerprint": fp,
            "request_id": request_id,
        }), encoding="utf-8")
        artifacts[request_id] = path

    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    for request_id in ("request-a", "request-b"):
        result = runner.discover_artifacts(
            _Config(),
            f"request_id={request_id}\n",
            invocation_id="current",
            strict_canonical=True,
            allow_multiple_run_artifacts=True,
        )
        assert result.run_artifact == artifacts[request_id]
        assert result.request_id == request_id


def test_discover_artifacts_same_invocation_without_request_identity_is_ambiguous(tmp_path):
    exp = _make_experiments_dir(tmp_path)
    fp = FingerprintEngine(_Config()).profile_config_fingerprint()
    for name, request_id in (("run_a.json", "request-a"), ("run_b.json", "request-b")):
        (exp / name).write_text(json.dumps({
            "v2ctl_invocation_id": "current",
            "profile": "production",
            "profile_config_fingerprint": fp,
            "request_id": request_id,
        }), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="conflicting request IDs|ambiguous"):
        BackendRunner(tmp_path, EnvironmentBuilder()).discover_artifacts(
            _Config(), "", invocation_id="current", strict_canonical=True,
            allow_multiple_run_artifacts=True,
        )


def test_discover_artifacts_same_invocation_rejects_request_mismatch(tmp_path):
    exp = _make_experiments_dir(tmp_path)
    fp = FingerprintEngine(_Config()).profile_config_fingerprint()
    for name, request_id in (("run_a.json", "request-a"), ("run_b.json", "request-b")):
        (exp / name).write_text(json.dumps({
            "v2ctl_invocation_id": "current",
            "profile": "production",
            "profile_config_fingerprint": fp,
            "request_id": request_id,
        }), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="does not match"):
        BackendRunner(tmp_path, EnvironmentBuilder()).discover_artifacts(
            _Config(), "request_id=request-c\n", invocation_id="current",
            strict_canonical=True, allow_multiple_run_artifacts=True,
        )


def test_discover_artifacts_wrong_profile_fails_and_malformed_is_ignored(tmp_path):
    exp = _make_experiments_dir(tmp_path)
    (exp / "run_bad.json").write_text("{not json", encoding="utf-8")
    fp = FingerprintEngine(_Config()).profile_config_fingerprint()
    (exp / "run_wrong.json").write_text(json.dumps({
        "v2ctl_invocation_id": "current", "profile": "other",
        "profile_config_fingerprint": fp,
    }), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="wrong profile"):
        BackendRunner(tmp_path, EnvironmentBuilder()).discover_artifacts(
            _Config(), "", invocation_id="current", strict_canonical=True,
        )


def test_discover_artifacts_previous_filename_shape_cannot_select(tmp_path):
    exp = _make_experiments_dir(tmp_path)
    (exp / "artifact.json").write_text(json.dumps({"v2ctl_invocation_id": "current"}), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="no canonical run artifact"):
        BackendRunner(tmp_path, EnvironmentBuilder()).discover_artifacts(
            _Config(), "", invocation_id="current", strict_canonical=True,
        )


def test_discover_artifacts_finds_summary(tmp_path):
    exp = _make_experiments_dir(tmp_path)
    (exp / "summary.json").write_text("{}", encoding="utf-8")
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    result = runner.discover_artifacts(_Config(), "")
    assert result.summary_artifact is not None
    assert result.summary_artifact.name == "summary.json"


def test_discover_artifacts_empty(tmp_path):
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    result = runner.discover_artifacts(_Config(), "")
    assert result.output_dir is None
    assert result.run_artifact is None
    assert result.summary_artifact is None
    assert result.campaign_manifest is None
    assert result.console_capture is None


def test_discover_artifacts_output_dir_from_stdout(tmp_path):
    exp = _make_experiments_dir(tmp_path, "custom_outputs")
    (exp / "run_010_validation.json").write_text("{}", encoding="utf-8")
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    stdout = "some log\noutput dir: custom_outputs\nmore log\n"
    result = runner.discover_artifacts(_Config(), stdout)
    assert result.run_artifact is not None
    assert result.run_artifact.parent == exp
    assert result.output_dir == exp


def test_discover_artifacts_ignores_non_json(tmp_path):
    exp = _make_experiments_dir(tmp_path)
    (exp / "notes.txt").write_text("hi", encoding="utf-8")
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    result = runner.discover_artifacts(_Config(), "")
    assert result.run_artifact is None
    assert result.summary_artifact is None
    assert result.campaign_manifest is None
    # no recognized artifacts anywhere -> every field stays None
    assert result.output_dir is None
    assert result.console_capture is None


def test_discover_artifacts_absolute_output_dir_line(tmp_path):
    exp = _make_experiments_dir(tmp_path, "abs_out")
    (exp / "run_001_validation.json").write_text("{}", encoding="utf-8")
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    stdout = f"output_dir={exp}\n"
    result = runner.discover_artifacts(_Config(), stdout)
    assert result.run_artifact is not None
    assert result.run_artifact.parent == exp


def test_discover_artifacts_nested_output_studio(tmp_path):
    exp = _make_experiments_dir(tmp_path, "output")
    studio = exp / "studio"
    studio.mkdir(parents=True, exist_ok=True)
    (studio / "run_001_validation.json").write_text("{}", encoding="utf-8")
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    result = runner.discover_artifacts(_Config(), "")
    assert result.run_artifact is not None
    assert result.run_artifact.name == "run_001_validation.json"
    assert result.run_artifact.parent == studio


def test_discover_artifacts_binds_current_golden_cohort_not_external_run(tmp_path):
    """Golden stdout is the invocation binding; generic archive files are ignored."""
    config = _Config(
        profile_name="golden_p1",
        target=_Target(
            app="stable-modal-comfy-v2-golden-p1",
            method="run_golden_serial_stream",
        ),
        workload=_Workload(
            expected_output_sha="a" * 64,
            fresh_required=True,
            run_count=1,
        ),
    )
    golden_dir = tmp_path / "artifacts" / "phase_p1_serial_golden_v1" / "cohort_current"
    golden_dir.mkdir(parents=True)
    request_id = "golden-p1-0-current"
    (golden_dir / "attempt_0_events.json").write_text("[]", encoding="utf-8")
    (golden_dir / "summary.json").write_text(
        json.dumps({"v2ctl_invocation_id": "current-invocation"}), encoding="utf-8"
    )
    (golden_dir / "attempt_0.json").write_text(
        json.dumps({
            "request_id": request_id,
            "v2ctl_invocation_id": "current-invocation",
        }), encoding="utf-8"
    )
    (golden_dir / "manifest.json").write_text(
        json.dumps({
            "mode": "golden_p1_serial",
            "method": "run_golden_serial_stream",
            "v2ctl_invocation_id": "current-invocation",
            "profile": "golden_p1",
            "profile_config_fingerprint": "placeholder",
            "target": {
                "app_name": config.target.app,
                "class_name": config.target.class_name,
                "gpu": config.resources.gpu,
            },
            "attempts": [{"request_id": request_id}],
        }),
        encoding="utf-8",
    )
    # This is the stale shape that previously won by mtime.
    external = _make_experiments_dir(tmp_path)
    (external / "run_001_sample.json").write_text(
        json.dumps({"v2ctl_invocation_id": "stale"}), encoding="utf-8"
    )
    fp = FingerprintEngine(config).profile_config_fingerprint()
    manifest_data = json.loads((golden_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest_data["profile_config_fingerprint"] = fp
    (golden_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")
    stdout = json.dumps({
        "output_dir": str(golden_dir),
        "manifest": str(golden_dir / "manifest.json"),
        "request_id": request_id,
    })

    result = BackendRunner(tmp_path, EnvironmentBuilder()).discover_artifacts(
        config,
        stdout,
        invocation_id="current-invocation",
        strict_canonical=True,
        expected_profile="golden_p1",
        expected_profile_config_fingerprint=fp,
    )

    assert result.output_dir == golden_dir.resolve()
    assert result.run_artifact == golden_dir / "attempt_0.json"
    assert result.campaign_manifest == golden_dir / "manifest.json"
    assert result.request_id == request_id
    assert result.v2ctl_invocation_id == "current-invocation"
    assert result.provenance_validation_status == "validated"


# ---------------------------------------------------------------------------
# BackendResult.ok / ArtifactSet defaults
# ---------------------------------------------------------------------------


def test_backend_result_ok():
    assert BackendResult(exit_code=0, stdout="", stderr="", command="",
                         started_at="", ended_at="", elapsed_seconds=0.0).ok()
    assert not BackendResult(exit_code=1, stdout="", stderr="", command="",
                             started_at="", ended_at="", elapsed_seconds=0.0).ok()


# ── Crash-loop detection ──────────────────────────────────────────────────

_CRASHLOOP_OUTPUT = (
    "Deploying app...\n"
    "Traceback (most recent call last):\n"
    '  File "/pkg/modal/_runtime/container_io_manager.py", line 904, in handle_user_exception\n'
    "    yield\n"
    "UnboundLocalError: cannot access local variable '_span_restore_early'\n"
    "Runner failed with exception: UnboundLocalError\n"
    "Retrying (1/5)...\n"
    "Traceback (most recent call last):\n"
    '  File "/pkg/modal/_runtime/container_io_manager.py", line 904, in handle_user_exception\n'
    "    yield\n"
    "UnboundLocalError: cannot access local variable '_span_restore_early'\n"
    "Runner failed with exception: UnboundLocalError\n"
    "Retrying (2/5)...\n"
    "Traceback (most recent call last):\n"
    '  File "/pkg/modal/_runtime/container_io_manager.py", line 904, in handle_user_exception\n'
    "    yield\n"
    "UnboundLocalError: cannot access local variable '_span_restore_early'\n"
    "Runner failed with exception: UnboundLocalError\n"
)

_SINGLE_TRACEBACK_OUTPUT = (
    "Deploying app...\n"
    "Traceback (most recent call last):\n"
    '  File "/x.py", line 1, in f\n'
    "ValueError: boom\n"
)


def test_detect_crash_loop_flags_repeated_identical_traceback():
    hit = detect_crash_loop(_CRASHLOOP_OUTPUT)
    assert hit is not None
    assert hit["exception_type"].startswith("UnboundLocalError")
    assert int(hit["count"]) >= 3


def test_detect_crash_loop_none_for_single_traceback():
    assert detect_crash_loop(_SINGLE_TRACEBACK_OUTPUT) is None


def test_detect_crash_loop_none_for_empty():
    assert detect_crash_loop("") is None
    assert detect_crash_loop("no tracebacks here") is None


def test_artifact_set_all_none_by_default():
    artifacts = ArtifactSet()
    assert artifacts.output_dir is None
    assert artifacts.run_artifact is None
    assert artifacts.summary_artifact is None
    assert artifacts.campaign_manifest is None
    assert artifacts.console_capture is None
