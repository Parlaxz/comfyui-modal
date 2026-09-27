"""Focused offline validation for the E31 A/B profile matrix."""

from pathlib import Path

import pytest

import tools.benchmark_v2_direct as benchmark
from tools.v2_control.profiles import Profiles


PROFILES = Profiles(Path(__file__).resolve().parents[1] / "config" / "v2" / "profiles")
EXPECTED_SHA = "20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260"


@pytest.mark.parametrize(
    "control,experiment,loader_keys",
    [
        (
            "e31-clip-fp32-fastsafe-arm-a",
            "e31-clip-fp32-fastsafe-arm-b",
            ("COMFYMODAL_V2_CLIP_QD_READER",),
        ),
        (
            "e31-clip-fp32-qd4-arm-a",
            "e31-clip-fp32-qd4-arm-b",
            (
                "COMFYMODAL_V2_CLIP_QD_READER",
                "COMFYMODAL_V2_CLIP_QD_QD",
                "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB",
                "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY",
            ),
        ),
    ],
)
def test_e31_ab_profiles_differ_only_by_cast_once(control, experiment, loader_keys):
    left = PROFILES.resolve(control)
    right = PROFILES.resolve(experiment)

    assert left.chain[-2] == right.chain[-2] == "e29-tracer"
    assert left.chain[:1] == right.chain[:1] == ["production"]
    assert left.workload["fresh_required"] is True
    assert right.workload["fresh_required"] is True
    assert left.workload["expected_output_sha"] == right.workload["expected_output_sha"] == EXPECTED_SHA
    assert left.owner == right.owner == "E31"
    assert left.target == right.target
    assert left.resources == right.resources
    assert left.runtime_overrides == right.runtime_overrides == {"policy": "forbid"}

    # Every loader setting is identical between arms; only the experiment bit
    # changes.  Keeping the assertion over the full environment also catches
    # accidental inherited E29 or profiler drift.
    cast_key = "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"
    assert left.environment[cast_key] == "0"
    assert right.environment[cast_key] == "1"
    assert left.environment["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] == "1"
    assert right.environment["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] == "1"
    left_without_cast = {k: v for k, v in left.environment.items() if k != cast_key}
    right_without_cast = {k: v for k, v in right.environment.items() if k != cast_key}
    assert left_without_cast == right_without_cast
    assert {key: left.environment[key] for key in loader_keys} == {
        key: right.environment[key] for key in loader_keys
    }


def test_e31_profiles_are_fresh_and_profiler_off_by_default():
    names = (
        "e31-clip-fp32-fastsafe-arm-a",
        "e31-clip-fp32-fastsafe-arm-b",
        "e31-clip-fp32-qd4-arm-a",
        "e31-clip-fp32-qd4-arm-b",
    )
    for name in names:
        profile = PROFILES.resolve(name)
        assert profile.workload["fresh_required"] is True
        assert profile.workload["expected_output_sha"] == EXPECTED_SHA
        assert profile.environment["COMFYMODAL_V2_E31_FORWARD_PROFILE"] == "0"
        assert profile.environment["COMFYMODAL_V2_E31_FORENSICS"] == "1"


def test_legacy_e31_profile_is_not_selectable():
    assert "e31-clip-fp32" not in PROFILES.available()


def _activate_e31_runtime(monkeypatch, **overrides):
    monkeypatch.setenv("V2_E31_VALIDATION", "1")
    monkeypatch.setenv("V2_E28_VALIDATION", "0")
    monkeypatch.setenv("V2_E19_FINAL_COLD_LOADER", "1")
    for key, value in benchmark.E19_FINAL_COLD_LOADER_PROFILE.items():
        monkeypatch.setenv(key, value)
    for key, value in benchmark.E31_QD4_CAST_ONCE_PROFILE.items():
        monkeypatch.setenv(key, overrides.get(key, value))


def test_e31_qd4_verifier_accepts_only_the_canonical_tuple(monkeypatch):
    _activate_e31_runtime(monkeypatch)
    ok, details = benchmark.verify_e31_validation_profile()
    assert ok is True, details
    assert details["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] == "1"
    assert details["COMFYMODAL_V2_CLIP_QD_BLOCK_MIB"] == "32"


@pytest.mark.parametrize(
    "key,value",
    [
        ("COMFYMODAL_V2_CLIP_FP32_CAST_ONCE", "0"),
        ("COMFYMODAL_V2_CLIP_QD_QD", "2"),
        ("COMFYMODAL_V2_CLIP_QD_BLOCK_MIB", "64"),
        ("COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY", "request"),
        ("COMFYMODAL_V2_E31_FORWARD_PROFILE", "1"),
    ],
)
def test_e31_qd4_verifier_fails_closed_on_required_value_mismatch(
    monkeypatch, key, value
):
    _activate_e31_runtime(monkeypatch, **{key: value})
    ok, details = benchmark.verify_e31_validation_profile()
    assert ok is False
    assert details["validation"] == "FAIL"


def test_e28_verifier_remains_cast_once_off(monkeypatch):
    monkeypatch.setenv("V2_E19_FINAL_COLD_LOADER", "1")
    monkeypatch.setenv("V2_E28_VALIDATION", "1")
    monkeypatch.setenv("V2_E31_VALIDATION", "0")
    for key, value in benchmark.E19_FINAL_COLD_LOADER_PROFILE.items():
        monkeypatch.setenv(key, value)
    for key, value in benchmark.E28_VALIDATION_PROFILE.items():
        monkeypatch.setenv(key, value)
    for key, value in benchmark.E28_LOADER_PROFILE.items():
        monkeypatch.setenv(key, value)
    ok, details = benchmark.verify_e28_validation_profile()
    assert ok is True, details
    monkeypatch.setenv("COMFYMODAL_V2_CLIP_FP32_CAST_ONCE", "1")
    ok, _ = benchmark.verify_e28_validation_profile()
    assert ok is False
