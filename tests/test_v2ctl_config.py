"""Tests for tools/v2_control/config.py (Batch E32, Agent A).

Stdlib only; uses the real config/v2 trees plus tmp git repositories.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.v2_control.config import (
    DEPLOY_RELEVANT_PATHS,
    ConfigResolver,
    GitState,
    ResolvedConfig,
    ResolvedFlag,
    compute_git_state,
)
from tools.v2_control.errors import FlagError
from tools.v2_control.profiles import Profiles
from tools.v2_control.registry import FlagRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "config" / "v2" / "flag_registry.toml"
PROFILES_DIR = REPO_ROOT / "config" / "v2" / "profiles"


@pytest.fixture(scope="module")
def registry() -> FlagRegistry:
    return FlagRegistry(REGISTRY_PATH)


@pytest.fixture(scope="module")
def profiles() -> Profiles:
    return Profiles(PROFILES_DIR)


@pytest.fixture(scope="module")
def resolver(registry, profiles) -> ConfigResolver:
    return ConfigResolver(REPO_ROOT, profiles, registry)


# ── helpers ────────────────────────────────────────────────────────────────


def _env_flags(config: ResolvedConfig) -> dict[str, str]:
    return {f.name: f.value for f in config.flags}


def _flag(config: ResolvedConfig, name: str) -> ResolvedFlag | None:
    return config.flag(name)


# ── basic resolve (production) ─────────────────────────────────────────────


def test_resolve_production_defaults(resolver):
    config = resolver.resolve(profile_name="production")
    assert config.profile_name == "production"
    assert config.owner == "v2-core"
    assert config.target.app == "stable-modal-comfy-v2-restore-only-shadow"
    assert config.resources.cpu == 12
    assert config.resources.memory_mb == 32768
    assert config.workload.fresh_required is True
    assert config.workload.run_count == 10
    assert config.workload.gap_seconds == 35.0
    assert config.runtime_override_policy == "forbid"
    # Production profile env surfaced as profile-sourced flags.
    flag = _flag(config, "COMFYMODAL_V2_CPU_REQUEST")
    assert flag is not None
    assert flag.value == "12"
    assert flag.source == "profile:production"
    assert flag.registered is True


def test_default_flags_present_with_default_source(resolver):
    config = resolver.resolve(profile_name="production")
    flag = _flag(config, "COMFYMODAL_V2_PNG_COMPRESS_LEVEL")
    assert flag is not None
    assert flag.source == "default"
    assert flag.value == "3"
    assert flag.consumed_at == "request"
    assert flag.change_requires == "run"


def test_flags_sorted(resolver):
    config = resolver.resolve(profile_name="production")
    names = [f.name for f in config.flags]
    assert names == sorted(names)


# ── precedence: defaults < parent < child < cli < inherit < set ────────────


def test_precedence_profile_chain(resolver):
    base = _env_flags(resolver.resolve(profile_name="production"))
    e31a = _env_flags(
        resolver.resolve(profile_name="e31-clip-fp32-fastsafe-arm-a")
    )
    e31b = _env_flags(
        resolver.resolve(profile_name="e31-clip-fp32-fastsafe-arm-b")
    )
    # The canonical E31 arms inherit the production/E29 loader settings and
    # differ only in the FP32 cast-once experiment bit.
    assert base["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] == "0"
    assert e31a["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] == "0"
    assert e31b["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] == "1"
    assert e31a["COMFYMODAL_V2_CLIP_FASTSAFE_THREADS"] == "8"
    assert e31b["COMFYMODAL_V2_CLIP_FASTSAFE_THREADS"] == "8"
    # And inherits production's untouched values.
    assert e31a["COMFYMODAL_V2_CPU_REQUEST"] == base["COMFYMODAL_V2_CPU_REQUEST"] == "12"
    assert e31b["COMFYMODAL_V2_CPU_REQUEST"] == base["COMFYMODAL_V2_CPU_REQUEST"] == "12"


def test_cli_overrides_profile(resolver):
    config = resolver.resolve(
        profile_name="production",
        cli_options={
            "resources.cpu": "24",
            "resources.memory_mb": "65536",
            "workload.run_count": "3",
            "owner": "cli-owner",
        },
    )
    assert config.resources.cpu == 24
    assert config.resources.memory_mb == 65536
    assert config.workload.run_count == 3
    assert config.owner == "cli-owner"
    assert _flag(config, "COMFYMODAL_V2_CPU_REQUEST").value == "12"  # env untouched


def test_inherit_beats_cli(resolver):
    config = resolver.resolve(
        profile_name="production",
        cli_options={"resources.cpu": "24"},
        inherits=["V2_OVERRIDE_MEMORY"],
        inherit_from={"V2_OVERRIDE_MEMORY": "9999"},
    )
    assert config.workload.run_count == 10
    assert _flag(config, "V2_OVERRIDE_MEMORY") is not None
    assert _flag(config, "V2_OVERRIDE_MEMORY").source == "inherit"


def test_set_beats_inherit_and_profile(resolver):
    config = resolver.resolve(
        profile_name="production",
        inherits=["COMFYMODAL_V2_UNET_FASTSAFETENSORS"],
        inherit_from={"COMFYMODAL_V2_UNET_FASTSAFETENSORS": "1"},
        sets=[("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "0")],
    )
    flag = _flag(config, "COMFYMODAL_V2_UNET_FASTSAFETENSORS")
    assert flag is not None
    assert flag.value == "0"
    assert flag.source == "set"


def test_set_overrides_profile_env(resolver):
    config = resolver.resolve(
        profile_name="e31-clip-fp32-fastsafe-arm-b",
        sets=[("COMFYMODAL_V2_CLIP_FP32_CAST_ONCE", "0")],
    )
    assert _flag(config, "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE").value == "0"


def test_ambient_env_never_merges(resolver):
    config = resolver.resolve(
        profile_name="production",
        inherit_from={"SOME_AMBIENT_VAR": "ignored"},
    )
    # Ambient vars are never merged; only explicit --inherit/set participate.
    assert _flag(config, "SOME_AMBIENT_VAR") is None


def test_inherit_missing_raises_flag_error(resolver):
    with pytest.raises(FlagError, match="inherit"):
        resolver.resolve(
            profile_name="production",
            inherits=["NOT_IN_ENV"],
            inherit_from={},
        )


def test_inherit_from_none_raises(resolver):
    with pytest.raises(FlagError, match="inherit"):
        resolver.resolve(profile_name="production", inherits=["X"])


def test_ambient_never_flows_without_explicit_inherit(resolver):
    config = resolver.resolve(profile_name="production", cli_options={"owner": "me"})
    assert _flag(config, "COMFYMODAL_V2_SOMETHING_FROM_SHELL") is None


# ── registered type validation at resolve time ─────────────────────────────


def test_registered_type_validation_failure_raises(resolver):
    with pytest.raises(FlagError, match="integer"):
        resolver.resolve(
            profile_name="production",
            sets=[("COMFYMODAL_V2_PNG_COMPRESS_LEVEL", "not-a-number")],
        )


def test_bool_normalized_at_resolve(resolver):
    config = resolver.resolve(
        profile_name="production",
        sets=[("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "true")],
    )
    assert _flag(config, "COMFYMODAL_V2_UNET_FASTSAFETENSORS").value == "1"


def test_enum_validation_at_resolve(resolver):
    with pytest.raises(FlagError, match="enum"):
        resolver.resolve(
            profile_name="production",
            sets=[("V2_BENCHMARK_MODE", "not_a_mode")],
        )


def test_nonce_regex_at_resolve(resolver):
    with pytest.raises(FlagError, match="does not match"):
        resolver.resolve(
            profile_name="production",
            sets=[("V2_E28_CONDITIONING_NONCE", "bad nonce!")],
        )
    config = resolver.resolve(
        profile_name="production",
        sets=[("V2_E28_CONDITIONING_NONCE", "abc-123")],
    )
    assert _flag(config, "V2_E28_CONDITIONING_NONCE").value == "abc-123"


def test_min_max_at_resolve(resolver):
    with pytest.raises(FlagError, match="below minimum"):
        resolver.resolve(
            profile_name="production",
            sets=[("COMFYMODAL_V2_PNG_COMPRESS_LEVEL", "0")],
        )
    with pytest.raises(FlagError, match="above maximum"):
        resolver.resolve(
            profile_name="production",
            sets=[("COMFYMODAL_V2_PNG_COMPRESS_LEVEL", "9")],
        )


# ── unregistered flags flow through ────────────────────────────────────────


def test_unregistered_set_recorded(resolver):
    config = resolver.resolve(
        profile_name="production",
        sets=[("COMFYMODAL_V2_FUTURE_EXPERIMENT", "1")],
    )
    assert len(config.unregistered) == 1
    flag = config.unregistered[0]
    assert flag.name == "COMFYMODAL_V2_FUTURE_EXPERIMENT"
    assert flag.value == "1"
    assert flag.source == "set"
    assert flag.registered is False
    assert flag.change_requires == "unknown"
    # It is also reachable through flag().
    assert config.flag("COMFYMODAL_V2_FUTURE_EXPERIMENT") is flag


def test_unregistered_inherit_recorded(resolver):
    config = resolver.resolve(
        profile_name="production",
        inherits=["V2_MYSTERY"],
        inherit_from={"V2_MYSTERY": "42"},
    )
    assert len(config.unregistered) == 1
    assert config.unregistered[0].source == "inherit"
    assert config.unregistered[0].value == "42"


def test_profile_unknown_env_keys_recorded_as_unregistered(resolver):
    # e30 sets env keys that are not in the registry; they must flow through
    # resolve and be recorded, not rejected.
    config = resolver.resolve(profile_name="e30-clip-qd")
    unreg_names = {f.name for f in config.unregistered}
    # The real E30 QD flags ARE registered; nothing in the e30 profile should
    # be unregistered (CLIP_FAST_HYDRATION / CLIP_COLD_FORENSICS are also
    # registered).  Keep an explicit assertion that no stale key leaks.
    assert "COMFYMODAL_V2_CLIP_QD_IO" not in unreg_names
    assert "COMFYMODAL_V2_CLIP_QD_READER" not in unreg_names
    # e29 sets its own keys when that profile is selected; the canonical
    # tracer flag is registered (module-import lifecycle, deploy-baked), so
    # the e29 profile must have ZERO unregistered keys.
    config_e29 = resolver.resolve(profile_name="e29-tracer")
    e29_unreg = {f.name for f in config_e29.unregistered}
    assert "COMFYMODAL_V2_E29_CRITICAL_PATH" not in e29_unreg  # dead flag, removed
    assert "COMFYMODAL_V2_CRITICAL_PATH_LEDGER" not in e29_unreg  # registered
    # GANTT_TELEMETRY is registered; e29's env value becomes a profile flag.
    gantt = config_e29.flag("COMFYMODAL_V2_GANTT_TELEMETRY")
    assert gantt is not None and gantt.registered is True
    assert gantt.source == "profile:e29-tracer"
    # The canonical ledger flag is registered and set from the profile.
    ledger = config_e29.flag("COMFYMODAL_V2_CRITICAL_PATH_LEDGER")
    assert ledger is not None and ledger.registered is True
    assert ledger.value == "1"


def test_unregistered_sorted(resolver):
    config = resolver.resolve(
        profile_name="production",
        sets=[("V2_ZEBRA", "1"), ("V2_ALPHA", "1")],
    )
    assert [f.name for f in config.unregistered] == ["V2_ALPHA", "V2_ZEBRA"]


def test_unregistered_no_protected_check_at_resolve(resolver):
    # Name syntax is enforced; protected-name policy lives in environment.py.
    with pytest.raises(FlagError):
        resolver.resolve(profile_name="production", sets=[("lowercase_name", "1")])


# ── --set parsing ──────────────────────────────────────────────────────────


def test_parse_set_spec_ok():
    assert ConfigResolver.parse_set_spec("NAME=VALUE") == ("NAME", "VALUE")
    assert ConfigResolver.parse_set_spec("V2_X=1") == ("V2_X", "1")
    assert ConfigResolver.parse_set_spec("V2_X=a=b") == ("V2_X", "a=b")


@pytest.mark.parametrize(
    "spec",
    ["", "NOEQUALS", "=VALUE", "lower=1", "A B=1", "A-B=1", "A=  "],
)
def test_parse_set_spec_bad(spec):
    with pytest.raises(FlagError):
        ConfigResolver.parse_set_spec(spec)


def test_parse_set_spec_non_string():
    with pytest.raises(FlagError):
        ConfigResolver.parse_set_spec(None)


# ── check_run_safety ───────────────────────────────────────────────────────


def test_run_only_refuses_deploy_required_change(resolver):
    config = resolver.resolve(
        profile_name="production",
        sets=[("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "1")],
    )
    with pytest.raises(FlagError, match="deploy-required"):
        resolver.check_run_safety(config, run_only=True)
    # deploy mode is fine.
    resolver.check_run_safety(config, run_only=False)


def test_run_only_refuses_unregistered_explicit(resolver):
    config = resolver.resolve(
        profile_name="production",
        sets=[("V2_UNKNOWN_FLAG", "1")],
    )
    with pytest.raises(FlagError, match="unregistered"):
        resolver.check_run_safety(config, run_only=True)


def test_run_only_allows_run_safe_changes(resolver):
    config = resolver.resolve(
        profile_name="production",
        sets=[("V2_BENCHMARK_GAP_SECONDS", "10.0")],
    )
    resolver.check_run_safety(config, run_only=True)


def test_run_only_allows_profile_and_default_flags(resolver):
    config = resolver.resolve(profile_name="production")
    resolver.check_run_safety(config, run_only=True)


# ── ResolvedFlag helpers ───────────────────────────────────────────────────


def test_resolved_flag_lifecycle_helpers():
    deploy_flag = ResolvedFlag(
        name="A", value="1", source="set", registered=True,
        consumed_at="restore", change_requires="deploy", type="bool",
        description="d",
    )
    run_flag = ResolvedFlag(
        name="B", value="1", source="set", registered=True,
        consumed_at="request", change_requires="run", type="bool",
        description="d",
    )
    assert deploy_flag.is_deploy_required() is True
    assert deploy_flag.is_run_safe() is False
    assert run_flag.is_deploy_required() is False
    assert run_flag.is_run_safe() is True


# ── to_dict / JSON safety ──────────────────────────────────────────────────


def test_to_dict_json_safe(resolver):
    import json

    config = resolver.resolve(
        profile_name="e31-clip-fp32-fastsafe-arm-b",
        sets=[("V2_UNKNOWN_JSON", "1")],
    )
    data = config.to_dict()
    json.dumps(data)  # must not raise
    assert data["profile_name"] == "e31-clip-fp32-fastsafe-arm-b"
    assert data["target"]["app"] == "stable-modal-comfy-v2-restore-only-shadow"
    assert isinstance(data["flags"], list)
    assert isinstance(data["unregistered"], list)
    assert data["runtime_override_policy"] == "forbid"
    assert set(data["git"]) == {"head", "branch", "dirty", "dirty_hashes"}


# ── compute_git_state ──────────────────────────────────────────────────────


def _run(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True,
        capture_output=True, text=True, timeout=30,
    )


def _git_available() -> bool:
    try:
        subprocess.run(
            ["git", "--version"], capture_output=True, text=True, timeout=10,
        )
        return True
    except (FileNotFoundError, OSError):
        return False


@pytest.mark.skipif(not _git_available(), reason="git not available")
def test_compute_git_state_dirty(tmp_path):
    _run(tmp_path, "init", "-b", "main")
    _run(tmp_path, "config", "user.email", "test@example.com")
    _run(tmp_path, "config", "user.name", "Test")
    (tmp_path / "tracked.txt").write_text("one", encoding="utf-8")
    (tmp_path / "comfyapp.py").write_text("runtime", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "v2").mkdir()
    (tmp_path / "config" / "v2" / "note.txt").write_text("v2", encoding="utf-8")
    _run(tmp_path, "add", ".")
    _run(tmp_path, "commit", "-m", "initial")
    _run(tmp_path, "tag", "start")

    # Modify a deploy-relevant file; add an untracked one elsewhere.
    (tmp_path / "comfyapp.py").write_text("runtime-v2", encoding="utf-8")
    (tmp_path / "tracked.txt").write_text("two", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("new", encoding="utf-8")

    state = compute_git_state(tmp_path)
    assert state.head != "unknown"
    assert state.branch == "main"
    assert state.dirty is True
    # comfyapp.py is deploy-relevant → hash recorded.
    assert "comfyapp.py" in state.dirty_hashes
    assert len(state.dirty_hashes["comfyapp.py"]) == 40  # sha1 hex
    # tracked.txt is NOT deploy-relevant → not in dirty_hashes.
    assert "tracked.txt" not in state.dirty_hashes
    assert "untracked.txt" not in state.dirty_hashes


@pytest.mark.skipif(not _git_available(), reason="git not available")
def test_compute_git_state_clean(tmp_path):
    _run(tmp_path, "init", "-b", "main")
    _run(tmp_path, "config", "user.email", "test@example.com")
    _run(tmp_path, "config", "user.name", "Test")
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    _run(tmp_path, "add", ".")
    _run(tmp_path, "commit", "-m", "initial")
    state = compute_git_state(tmp_path)
    assert state.head != "unknown"
    assert state.branch == "main"
    assert state.dirty is False
    assert state.dirty_hashes == {}


@pytest.mark.skipif(not _git_available(), reason="git not available")
def test_compute_git_state_directory_relevant(tmp_path):
    _run(tmp_path, "init", "-b", "main")
    _run(tmp_path, "config", "user.email", "test@example.com")
    _run(tmp_path, "config", "user.name", "Test")
    (tmp_path / "config" / "v2").mkdir(parents=True)
    (tmp_path / "config" / "v2" / "x.toml").write_text("x", encoding="utf-8")
    _run(tmp_path, "add", ".")
    _run(tmp_path, "commit", "-m", "initial")
    (tmp_path / "config" / "v2" / "x.toml").write_text("y", encoding="utf-8")
    state = compute_git_state(tmp_path)
    assert state.dirty is True
    assert "config/v2/x.toml" in state.dirty_hashes


def test_compute_git_state_non_git_dir(tmp_path):
    # No .git, no git binary needed — must not raise; head/branch unknown.
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    state = compute_git_state(tmp_path)
    assert isinstance(state, GitState)
    assert state.head == "unknown"
    assert state.branch == "unknown"
    assert state.dirty is False
    assert state.dirty_hashes == {}


# ── DEPLOY_RELEVANT_PATHS contract ─────────────────────────────────────────


def test_deploy_relevant_paths_contract():
    assert DEPLOY_RELEVANT_PATHS == (
        "comfymodal_runtime",
        "comfyapp.py",
        "tools/benchmark_v2_direct.py",
        "config/v2",
    )


# ── cli option key validation ──────────────────────────────────────────────


def test_unknown_cli_option_rejected(resolver):
    with pytest.raises(FlagError, match="unknown cli option"):
        resolver.resolve(profile_name="production", cli_options={"target.bogus": "x"})


def test_cli_dotted_target_keys(resolver):
    config = resolver.resolve(
        profile_name="production",
        cli_options={
            "target.app": "other-app",
            "target.class": "OtherClass",
            "target.method": "other_method",
        },
    )
    assert config.target.app == "other-app"
    assert config.target.class_name == "OtherClass"
    assert config.target.method == "other_method"


def test_workload_nonce_via_cli(resolver):
    config = resolver.resolve(
        profile_name="production",
        cli_options={"workload.nonce": "abc-123"},
    )
    assert config.workload.nonce == "abc-123"
