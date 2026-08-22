"""Tests for tools/v2_control/profiles.py (Batch E32, Agent A).

Stdlib only; uses the real config/v2/profiles tree for integration-style
coverage and tmp_path for isolated cycle/multi-parent fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.v2_control.profiles import Profiles
from tools.v2_control.errors import ProfileError

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = REPO_ROOT / "config" / "v2" / "profiles"


@pytest.fixture(scope="module")
def real_profiles() -> Profiles:
    return Profiles(PROFILES_DIR)


def _write_profile(directory: Path, name: str, body: str) -> None:
    (directory / f"{name}.toml").write_text(body, encoding="utf-8")


# ── discovery / real tree ──────────────────────────────────────────────────


def test_available_sorted(real_profiles):
    names = real_profiles.available()
    assert names == sorted(names)
    assert "production" in names
    assert "e29-tracer" in names
    assert "e30-clip-qd" in names
    assert "e31-clip-fp32-fastsafe-arm-a" in names
    assert "e31-clip-fp32-fastsafe-arm-b" in names


def test_load_production(real_profiles):
    profile = real_profiles.load("production")
    assert profile.name == "production"
    assert profile.extends is None
    assert profile.owner == "v2-core"
    assert profile.target["app"] == "stable-modal-comfy-v2-restore-only-shadow"
    assert profile.resources["cpu"] == 12
    assert profile.resources["memory_mb"] == 32768
    assert profile.workload["fresh_required"] is True
    assert profile.workload["run_count"] == 10
    assert profile.runtime_overrides == {"policy": "forbid"}
    assert profile.environment["COMFYMODAL_V2_ENV_PROFILE"] == "production"
    assert profile.environment["COMFYMODAL_V2_CPU_REQUEST"] == "12"


# ── profile inheritance (integration) ──────────────────────────────────────


def test_e29_extends_production(real_profiles):
    rp = real_profiles.resolve("e29-tracer")
    assert rp.name == "e29-tracer"
    assert rp.owner == "E29"
    assert rp.chain == ["production", "e29-tracer"]
    # production defaults survive…
    assert rp.target["app"] == "stable-modal-comfy-v2-restore-only-shadow"
    assert rp.resources["cpu"] == 12
    assert rp.resources["memory_mb"] == 32768
    assert rp.workload["conditioning_cache"] == "forced_miss"
    assert rp.environment["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] == "1"
    # …e29 overrides apply.
    assert rp.environment["COMFYMODAL_V2_CRITICAL_PATH_LEDGER"] == "1"
    assert rp.environment["COMFYMODAL_V2_GANTT_TELEMETRY"] == "1"
    assert rp.environment["COMFYMODAL_V2_CRITICAL_GPU_COORDINATION"] == "1"
    assert rp.environment["V2_BENCHMARK_RUNS"] == "1"
    # E30/E31 experimental behavior stays OFF in the tracer profile.
    assert rp.environment["COMFYMODAL_V2_CLIP_QD_READER"] == "0"
    assert rp.environment["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] == "0"
    assert rp.environment["COMFYMODAL_V2_E31_FORENSICS"] == "0"
    assert rp.workload["fresh_required"] is True
    assert rp.runtime_overrides["policy"] == "forbid"


def test_e30_extends_production(real_profiles):
    rp = real_profiles.resolve("e30-clip-qd")
    assert rp.owner == "E30"
    assert rp.chain == ["production", "e30-clip-qd"]
    assert rp.environment["COMFYMODAL_V2_CLIP_QD_READER"] == "1"
    assert rp.environment["COMFYMODAL_V2_CLIP_QD_QD"] == "4"
    assert rp.environment["COMFYMODAL_V2_CLIP_QD_BLOCK_MIB"] == "32"
    assert rp.environment["COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY"] == "restore_earliest"
    assert rp.environment["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] == "1"
    assert rp.environment["COMFYMODAL_V2_CLIP_COLD_FORENSICS"] == "1"
    # Parent's production value for a shared key is overridden by the child.
    assert rp.environment["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] == "1"
    assert rp.workload["expected_output_sha"] == "20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260"
    assert rp.runtime_overrides["policy"] == "forbid"


@pytest.mark.parametrize(
    ("profile_name", "cast_once"),
    [
        ("e31-clip-fp32-fastsafe-arm-a", "0"),
        ("e31-clip-fp32-fastsafe-arm-b", "1"),
    ],
)
def test_e31_extends_production(real_profiles, profile_name, cast_once):
    rp = real_profiles.resolve(profile_name)
    assert rp.owner == "E31"
    assert rp.chain == ["production", "e29-tracer", profile_name]
    assert rp.environment["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] == cast_once
    assert rp.environment["COMFYMODAL_V2_CLIP_FASTSAFE_THREADS"] == "8"
    assert rp.environment["COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES"] == "67108864"
    assert rp.environment["COMFYMODAL_V2_MEMORY_MB"] == "32768"  # inherited
    assert rp.workload["fresh_required"] is True
    assert rp.runtime_overrides["policy"] == "forbid"


def test_profiles_tolerate_unregistered_env_keys(real_profiles):
    # COMFYMODAL_V2_E29_CRITICAL_PATH is NOT in the registry — profile load
    # must not care.  (The E30 QD flags ARE registered; the profile sets the
    # real flag names.)
    rp = real_profiles.resolve("e30-clip-qd")
    assert rp.environment["COMFYMODAL_V2_CLIP_QD_READER"] == "1"


def test_resolve_production_no_parent(real_profiles):
    rp = real_profiles.resolve("production")
    assert rp.chain == ["production"]
    assert rp.owner == "v2-core"
    assert rp.environment["COMFYMODAL_V2_VAE_POLICY"] == "v1"


# ── errors: missing / cycle / multi-parent ─────────────────────────────────


def test_missing_profile_error(tmp_path):
    profiles = Profiles(tmp_path)
    with pytest.raises(ProfileError, match="not found"):
        profiles.load("does-not-exist")
    with pytest.raises(ProfileError, match="not found"):
        profiles.resolve("does-not-exist")


def test_cycle_detection(tmp_path):
    _write_profile(
        tmp_path, "a",
        'schema_version = 1\nname = "a"\nextends = "b"\n',
    )
    _write_profile(
        tmp_path, "b",
        'schema_version = 1\nname = "b"\nextends = "a"\n',
    )
    profiles = Profiles(tmp_path)
    with pytest.raises(ProfileError, match="cycle"):
        profiles.load("a")
    with pytest.raises(ProfileError, match="cycle"):
        profiles.resolve("a")


def test_self_cycle_detection(tmp_path):
    _write_profile(
        tmp_path, "selfy",
        'schema_version = 1\nname = "selfy"\nextends = "selfy"\n',
    )
    profiles = Profiles(tmp_path)
    with pytest.raises(ProfileError, match="cycle"):
        profiles.load("selfy")


def test_multi_parent_rejected(tmp_path):
    # `extends` must be a plain string; a table/array means >1 parent.
    _write_profile(
        tmp_path, "multi",
        'schema_version = 1\nname = "multi"\n'
        '[extends]\np1 = "production"\np2 = "production"\n',
    )
    profiles = Profiles(tmp_path)
    with pytest.raises(ProfileError, match="plain string"):
        profiles.load("multi")


def test_missing_parent_rejected(tmp_path):
    _write_profile(
        tmp_path, "orphan",
        'schema_version = 1\nname = "orphan"\nextends = "no-such-parent"\n',
    )
    profiles = Profiles(tmp_path)
    with pytest.raises(ProfileError, match="not found"):
        profiles.resolve("orphan")


def test_bad_toml_raises_profile_error(tmp_path):
    _write_profile(tmp_path, "broken", "schema_version = [unclosed")
    profiles = Profiles(tmp_path)
    with pytest.raises(ProfileError, match="TOML"):
        profiles.load("broken")


def test_available_ignores_non_toml(tmp_path):
    (tmp_path / "notes.txt").write_text("hi", encoding="utf-8")
    profiles = Profiles(tmp_path)
    assert profiles.available() == []


# ── merge semantics (isolated) ─────────────────────────────────────────────


def test_merge_shallow_target_resources_workload(tmp_path):
    _write_profile(
        tmp_path, "base",
        'schema_version = 1\nname = "base"\nowner = "root"\n'
        "[target]\napp = \"A\"\nclass = \"C\"\nmethod = \"M\"\n"
        "[resources]\ngpu = \"gpu-a\"\ncpu = 4\nmemory_mb = 8192\n"
        "[workload]\nrun_count = 5\nfresh_required = true\n",
    )
    _write_profile(
        tmp_path, "child",
        'schema_version = 1\nname = "child"\nextends = "base"\nowner = "kid"\n'
        "[target]\napp = \"B\"\n"
        "[resources]\ncpu = 8\n"
        "[workload]\nrun_count = 9\n",
    )
    rp = Profiles(tmp_path).resolve("child")
    assert rp.chain == ["base", "child"]
    assert rp.owner == "kid"
    # Child wins where set; parent values survive elsewhere (shallow merge).
    assert rp.target["app"] == "B"
    assert rp.target["class"] == "C"
    assert rp.target["method"] == "M"
    assert rp.resources["gpu"] == "gpu-a"
    assert rp.resources["cpu"] == 8
    assert rp.resources["memory_mb"] == 8192
    assert rp.resources["min_containers"] == 0  # inherited from base defaults
    assert rp.workload["run_count"] == 9
    assert rp.workload["fresh_required"] is True
    assert rp.workload["conditioning_cache"] == "forced_miss"  # base default


def test_environment_merges_child_wins(tmp_path):
    _write_profile(
        tmp_path, "base",
        'schema_version = 1\nname = "base"\n'
        "[environment]\nSHARED = \"base\"\nONLY_BASE = \"1\"\n",
    )
    _write_profile(
        tmp_path, "child",
        'schema_version = 1\nname = "child"\nextends = "base"\n'
        "[environment]\nSHARED = \"child\"\nONLY_CHILD = \"2\"\n",
    )
    rp = Profiles(tmp_path).resolve("child")
    assert rp.environment == {
        "SHARED": "child",
        "ONLY_BASE": "1",
        "ONLY_CHILD": "2",
    }


def test_runtime_overrides_policy_forbid_default(tmp_path):
    _write_profile(
        tmp_path, "base",
        'schema_version = 1\nname = "base"\n[runtime_overrides]\npolicy = "forbid"\n',
    )
    rp = Profiles(tmp_path).resolve("base")
    assert rp.runtime_overrides == {"policy": "forbid"}


def test_defaults_applied_when_profile_silent(tmp_path):
    _write_profile(
        tmp_path, "bare",
        'schema_version = 1\nname = "bare"\n',
    )
    rp = Profiles(tmp_path).resolve("bare")
    # Built-in base defaults fill the structural sections.
    assert rp.target["app"] == "stable-modal-comfy-v2-restore-only-shadow"
    assert rp.resources["cpu"] == 12
    assert rp.workload["gap_seconds"] == 35.0
    assert rp.runtime_overrides["policy"] == "forbid"
    assert rp.environment == {}
