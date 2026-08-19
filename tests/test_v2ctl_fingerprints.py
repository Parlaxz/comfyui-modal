"""Agent B tests: tools/v2_control/fingerprints.py (Batch E32).

Covers (contract §21 subset):
- deploy-required change (COMFYMODAL_V2_UNET_FASTSAFETENSORS 0->1) alters
  the deploy fingerprint AND the run fingerprint (run embeds deploy fp);
- run-only change (V2_BENCHMARK_GAP_SECONDS) does NOT alter the deploy fp
  but alters the run fp;
- unregistered flag change alters BOTH fingerprints (unknown is not trusted);
- determinism: same config -> same fingerprints across engine instances;
- canonical_json format (sort_keys, compact separators, ensure_ascii=False);
- float formatting via repr().

Python 3.11 stdlib + pytest only; no network.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.v2_control.fingerprints import FingerprintEngine  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal ResolvedConfig duck-type (Agent A's config.py is not required).
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


def _flag(name: str, value: str, change_requires: str = "run") -> _Flag:
    return _Flag(name=name, value=value, change_requires=change_requires)


def _base_config(**overrides) -> _Config:
    config = _Config(
        flags=[
            _flag("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "0", "deploy"),
            _flag("V2_BENCHMARK_GAP_SECONDS", "35.0", "run"),
        ],
        unregistered=[],
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_config_same_fingerprints_across_engines():
    config = _base_config()
    a = FingerprintEngine(config)
    b = FingerprintEngine(config)
    assert a.deploy_fingerprint() == b.deploy_fingerprint()
    assert a.run_fingerprint() == b.run_fingerprint()
    assert a.deploy_fingerprint() == a.deploy_fingerprint()  # idempotent


def test_fingerprints_are_sha256_hex():
    engine = FingerprintEngine(_base_config())
    for fp in (engine.deploy_fingerprint(), engine.run_fingerprint()):
        assert len(fp) == 64
        int(fp, 16)  # raises if not hex


# ---------------------------------------------------------------------------
# Deploy-required change
# ---------------------------------------------------------------------------


def test_deploy_required_change_alters_deploy_fp():
    base = _base_config()
    changed = _base_config()
    changed.flags = [
        _flag("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "1", "deploy"),
        _flag("V2_BENCHMARK_GAP_SECONDS", "35.0", "run"),
    ]
    assert FingerprintEngine(base).deploy_fingerprint() != FingerprintEngine(changed).deploy_fingerprint()


def test_deploy_required_change_alters_run_fp():
    base = _base_config()
    changed = _base_config()
    changed.flags = [
        _flag("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "1", "deploy"),
        _flag("V2_BENCHMARK_GAP_SECONDS", "35.0", "run"),
    ]
    assert FingerprintEngine(base).run_fingerprint() != FingerprintEngine(changed).run_fingerprint()


def test_deploy_flags_contain_only_deploy_required():
    engine = FingerprintEngine(_base_config())
    inputs = engine.deploy_inputs()
    assert inputs["deploy_flags"] == {"COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0"}
    # run-only flag excluded from deploy inputs
    assert "V2_BENCHMARK_GAP_SECONDS" not in inputs["deploy_flags"]


def test_run_flags_contain_only_run_safe():
    engine = FingerprintEngine(_base_config())
    inputs = engine.run_inputs()
    assert inputs["run_flags"] == {"V2_BENCHMARK_GAP_SECONDS": "35.0"}
    assert "COMFYMODAL_V2_UNET_FASTSAFETENSORS" not in inputs["run_flags"]


# ---------------------------------------------------------------------------
# Run-only change
# ---------------------------------------------------------------------------


def test_run_only_change_does_not_alter_deploy_fp():
    base = _base_config()
    changed = _base_config()
    changed.flags = [
        _flag("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "0", "deploy"),
        _flag("V2_BENCHMARK_GAP_SECONDS", "45.0", "run"),
    ]
    assert FingerprintEngine(base).deploy_fingerprint() == FingerprintEngine(changed).deploy_fingerprint()
    assert FingerprintEngine(base).run_fingerprint() != FingerprintEngine(changed).run_fingerprint()


def test_run_inputs_embed_deploy_fingerprint():
    engine = FingerprintEngine(_base_config())
    inputs = engine.run_inputs()
    assert inputs["deploy_fingerprint"] == engine.deploy_fingerprint()


# ---------------------------------------------------------------------------
# Unregistered flags — unknown is not trusted
# ---------------------------------------------------------------------------


def test_unregistered_change_alters_both_fingerprints():
    base = _base_config()
    changed = _base_config()
    changed.unregistered = [_flag("V2_BRAND_NEW_EXPERIMENT", "1", "unknown")]
    base_engine = FingerprintEngine(base)
    changed_engine = FingerprintEngine(changed)
    assert base_engine.deploy_fingerprint() != changed_engine.deploy_fingerprint()
    assert base_engine.run_fingerprint() != changed_engine.run_fingerprint()


def test_unregistered_appears_in_both_inputs():
    config = _base_config()
    config.unregistered = [_flag("V2_BRAND_NEW_EXPERIMENT", "1", "unknown")]
    engine = FingerprintEngine(config)
    # deploy inputs: deploy-required flag + unregistered flag
    assert engine.deploy_inputs()["deploy_flags"] == {
        "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
        "V2_BRAND_NEW_EXPERIMENT": "1",
    }
    # run inputs: run-safe flag + unregistered flag
    assert engine.run_inputs()["run_flags"] == {
        "V2_BENCHMARK_GAP_SECONDS": "35.0",
        "V2_BRAND_NEW_EXPERIMENT": "1",
    }


# ---------------------------------------------------------------------------
# Git / target / resources / profile / policy shape
# ---------------------------------------------------------------------------


def test_dirty_git_state_alters_deploy_fp():
    base = _base_config()
    dirty = _base_config()
    dirty.git = _Git(head="0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997", dirty=True,
                     dirty_hashes={"comfymodal_runtime/modal_app.py": "abc123"})
    assert FingerprintEngine(base).deploy_fingerprint() != FingerprintEngine(dirty).deploy_fingerprint()
    assert FingerprintEngine(base).run_fingerprint() != FingerprintEngine(dirty).run_fingerprint()


def test_dirty_hashes_sorted_in_inputs():
    config = _base_config()
    config.git = _Git(head="h", dirty=True, dirty_hashes={"z.py": "1", "a.py": "2"})
    inputs = FingerprintEngine(config).deploy_inputs()
    assert list(inputs["dirty_hashes"].items()) == [("a.py", "2"), ("z.py", "1")]


def test_target_change_alters_deploy_fp():
    base = _base_config()
    changed = _base_config()
    changed.target = _Target(app="different-app")
    assert FingerprintEngine(base).deploy_fingerprint() != FingerprintEngine(changed).deploy_fingerprint()


def test_resource_change_alters_deploy_fp():
    base = _base_config()
    changed = _base_config()
    changed.resources = _Resources(gpu="a10g", cpu=4, memory_mb=8192, min_containers=1, scaledown_window=0)
    assert FingerprintEngine(base).deploy_fingerprint() != FingerprintEngine(changed).deploy_fingerprint()


def test_profile_and_policy_in_inputs():
    engine = FingerprintEngine(_base_config())
    inputs = engine.deploy_inputs()
    assert inputs["profile"] == "production"
    assert inputs["runtime_override_policy"] == "forbid"
    assert inputs["target"]["app"].startswith("stable-modal")


# ---------------------------------------------------------------------------
# Workload -> run fingerprint only
# ---------------------------------------------------------------------------


def test_workload_change_alters_run_fp_not_deploy_fp():
    base = _base_config()
    changed = _base_config()
    changed.workload = _Workload(fresh_required=False)
    assert FingerprintEngine(base).deploy_fingerprint() == FingerprintEngine(changed).deploy_fingerprint()
    assert FingerprintEngine(base).run_fingerprint() != FingerprintEngine(changed).run_fingerprint()


# ---------------------------------------------------------------------------
# canonical_json
# ---------------------------------------------------------------------------


def test_canonical_json_sorted_compact_ascii():
    data = {"b": "β", "a": 1}
    out = FingerprintEngine.canonical_json(data)
    assert out == '{"a":1,"b":"β"}'
    assert "," in out and ":" in out
    assert " " not in out


def test_float_formatting_repr():
    config = _base_config()
    config.workload = _Workload(gap_seconds=0.30000000000000004)
    inputs = FingerprintEngine(config).run_inputs()
    assert inputs["workload"]["gap_seconds"] == repr(0.30000000000000004)
