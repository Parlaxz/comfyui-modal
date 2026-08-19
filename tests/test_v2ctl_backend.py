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
from dataclasses import dataclass, field
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.v2_control.backend import (  # noqa: E402
    ArtifactSet,
    BackendRegistry,
    BackendResult,
    BackendRunner,
    BackendSpec,
    detect_crash_loop,
)
from tools.v2_control.environment import EnvironmentBuilder  # noqa: E402
from tools.v2_control.errors import BackendError  # noqa: E402


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


def test_discover_artifacts_picks_newest(tmp_path):
    exp = _make_experiments_dir(tmp_path)
    old = exp / "run_001_validation.json"
    new = exp / "run_002_validation.json"
    old.write_text("{}", encoding="utf-8")
    new.write_text("{}", encoding="utf-8")
    import time as _time

    _time.sleep(0.05)
    new.touch()
    runner = BackendRunner(tmp_path, EnvironmentBuilder())
    result = runner.discover_artifacts(_Config(), "")
    assert result.run_artifact is not None
    assert result.run_artifact.name == "run_002_validation.json"


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
