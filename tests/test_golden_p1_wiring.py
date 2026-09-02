"""Offline wiring tests for the golden_p1 control-plane integration.

Covers: registry/profile resolution with provenance, child-environment
projection, BAT-level selector routing without post-resolution clobbering,
deploy-fingerprint sensitivity, and unchanged unknown-flag run safety.
No network, no Modal calls, no subprocess beyond v2ctl's local git probe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.v2_control import cli
from tools.v2_control import backend as backend_mod
from tools.v2_control.environment import EnvironmentBuilder
from tools.v2_control.errors import FlagError
from tools.v2_control.golden_payload import _golden_p1_request_payload

ROOT = Path(__file__).resolve().parents[1]
FLAG = "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM"
HASH_CHECK_FLAG = "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK"
ATTENTION_BACKEND_FLAG = "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND"
SAGE_RUNTIME_MODE_FLAG = "COMFYMODAL_SAGE_RUNTIME_MODE"
SAMPLING_DEEP_PROFILE_FLAG = "COMFYMODAL_SAMPLING_DEEP_PROFILE"


def _config(profile: str, *, sets: list[str] | None = None):
    return cli.build_components(ROOT, profile, sets=sets or [])[3]


# ── Resolution and provenance ─────────────────────────────────────────────


def test_profile_resolves_flag_true_with_provenance():
    config = _config("golden_p1")
    flag = config.flag(FLAG)
    assert flag is not None
    assert flag.value == "1"
    assert flag.source == "profile:golden_p1"
    assert flag.registered is True
    assert flag.change_requires == "deploy"
    assert flag.consumed_at == "restore"


def test_golden_and_production_sage_runtime_modes_are_explicit_and_distinct():
    golden = _config("golden_p1").flag(SAGE_RUNTIME_MODE_FLAG)
    production = _config("production").flag(SAGE_RUNTIME_MODE_FLAG)
    assert golden is not None
    assert golden.value == "auto"
    assert golden.source == "profile:golden_p1"
    assert production is not None
    assert production.value == "baked_cuda"
    assert production.source == "profile:production"


def test_run_manifest_carries_configured_and_resolved_sage_modes(tmp_path: Path):
    config = _config("golden_p1")
    # configured is auto (policy), resolved must be observed (not auto); use triton_fallback as valid execution
    result = backend_mod.BackendResult(
        exit_code=0,
        stdout="",
        stderr="",
        command="golden",
        started_at="",
        ended_at="",
        elapsed_seconds=0.0,
        artifacts=backend_mod.ArtifactSet(
            experiment_identity={
                "sage_mode": "triton_fallback",
            },
        ),
    )
    path = cli.write_run_manifest(
        tmp_path, config, cli.build_components(ROOT, "golden_p1")[4], {}, result, None,
    )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["configured_sage_runtime_mode"] == "auto"
    assert manifest["resolved_sage_runtime_mode"] == "triton_fallback"
    assert manifest["experiment_identity"]["configured_sage_runtime_mode"] == "auto"
    assert manifest["experiment_identity"]["resolved_sage_runtime_mode"] == "triton_fallback"
    # resolved must never be auto for completed execution
    assert manifest["resolved_sage_runtime_mode"] != "auto"

    # when no runtime observation is present, resolved is missing/unknown (not auto)
    empty_result = backend_mod.BackendResult(
        exit_code=0,
        stdout="",
        stderr="",
        command="golden",
        started_at="",
        ended_at="",
        elapsed_seconds=0.0,
        artifacts=backend_mod.ArtifactSet(
            experiment_identity={},
        ),
    )
    empty_path = cli.write_run_manifest(
        tmp_path, config, cli.build_components(ROOT, "golden_p1")[4], {}, empty_result, None,
    )
    empty_manifest = json.loads(empty_path.read_text(encoding="utf-8"))
    assert empty_manifest["configured_sage_runtime_mode"] == "auto"
    assert empty_manifest["resolved_sage_runtime_mode"] == ""


def test_set_resolution_normalizes_bool_and_carries_provenance():
    config = _config("production", sets=[f"{FLAG}=true"])
    flag = config.flag(FLAG)
    assert flag is not None
    assert flag.value == "1"
    assert flag.source == "set"
    assert flag.registered is True
    assert flag.is_deploy_required() is True


def test_config_command_reports_flag_with_provenance(capsys):
    exit_code = cli.main(["--profile", "golden_p1", "config"])
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    entry = next(f for f in out["flags"] if f["name"] == FLAG)
    assert entry == {
        "name": FLAG,
        "value": "1",
        "source": "profile:golden_p1",
        "registered": True,
        "consumed_at": "restore",
        "change_requires": "deploy",
        "type": "bool",
        "description": entry["description"],
    }
    assert entry["description"]
    assert out["profile"] == "golden_p1"


def test_child_environment_carries_the_flag():
    for config in (_config("golden_p1"), _config("production", sets=[f"{FLAG}=true"])):
        env = EnvironmentBuilder().build(config, host_env={}, backend_extra={})
        assert env[FLAG] == "1"


def test_golden_p1_explicitly_uses_model_free_single_use_snapshot_contract():
    config = _config("golden_p1")

    expected = {
        "COMFYMODAL_V2_ENV_PROFILE": "inherit",
        "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
        "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
        "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
        "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
        FLAG: "1",
        SAGE_RUNTIME_MODE_FLAG: "auto",
        HASH_CHECK_FLAG: "1",
    }
    effective = {}
    for name in expected:
        flag = config.flag(name)
        assert flag is not None
        assert flag.source == "profile:golden_p1"
        assert flag.change_requires == "deploy"
        effective[name] = flag.value
    assert effective == expected
    assert config.workload.run_count == 1
    assert config.workload.fresh_required is True
    assert config.workload.conditioning_cache == "forced_miss"
    assert (
        config.workload.expected_output_sha
        == "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"
    )
    assert config.flag("COMFYMODAL_V2_ENABLE_MEMORY_SNAPSHOT") is None


def test_golden_p1_keeps_sampling_decomposition_opt_in_by_default():
    config = _config("golden_p1")
    flag = config.flag(SAMPLING_DEEP_PROFILE_FLAG)
    assert flag is not None
    assert flag.value == "off"
    assert flag.source == "profile:golden_p1"


def test_golden_p1_uses_serial_mode_and_accepts_only_explicit_canonical_selector():
    assert cli._benchmark_mode(_config("golden_p1")) == "golden_p1_serial"
    args, env = cli._validation_backend_args(_config("golden_p1"))
    assert args == [
        "--run-count",
        "1",
        "--golden-p1-expected-output-sha",
        "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
        "--attention-backend",
        "pytorch",
    ]
    assert env == {
        "V2_BENCHMARK_MODE": "golden_p1_serial"
    }

    explicit = _config("golden_p1", sets=["V2_BENCHMARK_MODE=golden_p1_serial"])
    cli._reject_golden_mode_override(explicit, command="v2ctl golden run")
    assert cli._benchmark_mode(explicit) == "golden_p1_serial"
    explicit_args, explicit_env = cli._validation_backend_args(explicit)
    assert explicit_args == args
    assert explicit_env == {
        "V2_BENCHMARK_MODE": "golden_p1_serial"
    }

    assert cli._benchmark_mode(_config("production")) == "e28_single"


def test_golden_attention_backend_is_run_only_and_resolved_by_default():
    config = _config("golden_p1")
    flag = config.flag(ATTENTION_BACKEND_FLAG)
    assert flag is not None
    assert flag.value == "pytorch"
    assert flag.source == "default"
    assert flag.change_requires == "run"
    args, _env = cli._validation_backend_args(config)
    assert args[-2:] == ["--attention-backend", "pytorch"]

    source = {"prompt": {"1": {}}, "extra_data": {}, "modal_options": {}}
    payload = _golden_p1_request_payload(
        source, request_id="r-default", index=0,
    )
    assert "attention_backend" not in payload


def test_golden_attention_backend_sage_propagates_to_top_level_payload():
    config = _config("golden_p1", sets=[f"{ATTENTION_BACKEND_FLAG}=sage"])
    flag = config.flag(ATTENTION_BACKEND_FLAG)
    assert flag is not None
    assert flag.value == "sage"
    assert flag.source == "set"
    assert flag.change_requires == "run"
    args, _env = cli._validation_backend_args(config)
    assert args[-2:] == ["--attention-backend", "sage"]

    source = {
        "prompt": {"1": {}},
        "extra_data": {},
        "modal_options": {"unrelated": True},
    }
    payload = _golden_p1_request_payload(
        source, request_id="r-sage", index=0, attention_backend="sage",
    )
    assert payload["attention_backend"] == "sage"
    assert "attention_backend" not in payload["modal_options"]


def test_golden_attention_backend_comfy_kitchen_is_run_only_and_propagates():
    config = _config("golden_p1", sets=[f"{ATTENTION_BACKEND_FLAG}=comfy_kitchen"])
    flag = config.flag(ATTENTION_BACKEND_FLAG)
    assert flag is not None
    assert flag.value == "comfy_kitchen"
    assert flag.source == "set"
    assert flag.change_requires == "run"
    args, _env = cli._validation_backend_args(config)
    assert args[-2:] == ["--attention-backend", "comfy_kitchen"]


def test_golden_attention_backend_rejects_values_outside_public_selector():
    with pytest.raises(FlagError):
        _config("golden_p1", sets=[f"{ATTENTION_BACKEND_FLAG}=flash"])


@pytest.mark.parametrize(
    "mode",
    ["acceptance", "variance_cold", "variance_matrix", "volume_read", "snapshot_restore_only"],
)
def test_golden_p1_rejects_explicit_generic_mode(mode):
    config = _config("golden_p1", sets=[f"V2_BENCHMARK_MODE={mode}"])
    with pytest.raises(cli.GateError, match="only golden_p1_serial is allowed"):
        cli._reject_golden_mode_override(config, command="v2ctl golden run")


# ── Batch wrapper routing (static analysis) ───────────────────────────────


def _bat_lines(name: str) -> list[str]:
    return (ROOT / name).read_text(encoding="utf-8").splitlines()


def test_both_bats_activate_golden_p1_via_existing_selector_mechanisms():
    for name in ("deploy_and_run_v2_single.bat", "run_v2_single.bat"):
        text = "\n".join(_bat_lines(name))
        # Positional %~1 selector mechanism (same as E25/E28/E31 selectors).
        assert 'if /i "%~1"=="golden_p1"' in text
        # Env-var activation mechanism (same as the CLEAN_LANE selectors), so
        # a v2ctl-resolved golden_p1 child environment activates the path too.
        assert 'if /i "!COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM!"=="1"' in text


def test_deploy_golden_selector_uses_golden_mode_and_preserves_target_identity():
    lines = _bat_lines("deploy_and_run_v2_single.bat")
    golden_active = next(i for i, line in enumerate(lines) if 'if "!V2_GOLDEN_P1_ACTIVE!"=="1" (' in line)
    mode_guard = next(i for i, line in enumerate(lines) if "golden_p1 requires V2_BENCHMARK_MODE=golden_p1_serial" in line)
    golden_mode = next(i for i, line in enumerate(lines) if 'set "V2_BENCHMARK_MODE=golden_p1_serial"' in line)
    default_mode = next(i for i, line in enumerate(lines) if 'set "V2_BENCHMARK_MODE=snapshot_restore_only"' in line)
    restore_only = next(i for i, line in enumerate(lines) if 'if /i "!V2_BENCHMARK_MODE!"=="snapshot_restore_only" set "V2_IS_RESTORE_ONLY=1"' in line)
    app_default = next(i for i, line in enumerate(lines) if 'COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-restore-only-shadow' in line)
    restore_app = next(i for i, line in enumerate(lines) if 'set "COMFYMODAL_V2_APP_NAME=!COMFYMODAL_V2_RESTORE_ONLY_APP_NAME!"' in line)

    assert golden_active < mode_guard < golden_mode
    assert golden_mode < default_mode < restore_only < restore_app
    assert lines[app_default].strip().startswith(
        "if not defined COMFYMODAL_V2_APP_NAME set "
    )
    assert _config("golden_p1").target.app == "batch-r0-golden-ops"


def test_run_bat_rejects_missing_or_wrong_golden_app_before_fallback():
    lines = _bat_lines("run_v2_single.bat")
    text = "\n".join(lines)
    assert 'if /i "!COMFYMODAL_V2CTL_PROFILE!"=="golden_p1"' in text
    assert "golden_p1 requires an experimental COMFYMODAL_V2_APP_NAME" in text
    assert 'if /i "!COMFYMODAL_V2_APP_NAME!"=="stable-modal-comfy-v2-golden-p1"' in text
    guard = next(i for i, line in enumerate(lines) if "golden_p1 requires an experimental" in line)
    fallback = next(i for i, line in enumerate(lines) if "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-restore-only-shadow" in line)
    assert guard < fallback


def test_both_bats_reject_non_golden_mode_before_generic_branches():
    for name in ("deploy_and_run_v2_single.bat", "run_v2_single.bat"):
        lines = _bat_lines(name)
        mode_guard = next(
            i for i, line in enumerate(lines)
            if "golden_p1 requires V2_BENCHMARK_MODE=golden_p1_serial" in line
        )
        generic_branch = next(
            i for i, line in enumerate(lines)
            if 'V2_BENCHMARK_MODE!"=="variance_matrix' in line
        )
        assert mode_guard < generic_branch
        assert 'if defined V2_BENCHMARK_MODE if /i not "!V2_BENCHMARK_MODE!"=="golden_p1_serial" (' in lines[mode_guard - 1]


def test_deploy_bat_rejects_missing_or_protected_golden_app_before_fallback():
    lines = _bat_lines("deploy_and_run_v2_single.bat")
    text = "\n".join(lines)
    assert "golden_p1 requires an experimental COMFYMODAL_V2_APP_NAME" in text
    assert 'if /i "!COMFYMODAL_V2_APP_NAME!"=="stable-modal-comfy-v2-golden-p1"' in text
    guard = next(i for i, line in enumerate(lines) if "golden_p1 requires an experimental" in line)
    fallback = next(i for i, line in enumerate(lines) if "COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-restore-only-shadow" in line)
    assert guard < fallback


def test_run_bat_routes_golden_p1_to_benchmark_harness_after_existing_modes():
    lines = _bat_lines("run_v2_single.bat")
    text = "\n".join(lines)
    assert "--golden-p1" in text
    golden_idx = next(i for i, l in enumerate(lines) if "python tools\\benchmark_v2_direct.py --golden-p1 !V2_GOLDEN_ARGS!" in l)
    # Every explicit V2_BENCHMARK_MODE branch keeps precedence: the golden
    # branch sits after them, immediately before the plain fallback else.
    snapshot_idx = next(
        i for i, l in enumerate(lines) if "--snapshot-restore-only %" in l
    )
    fallback_idx = next(
        i for i, l in enumerate(lines)
        if l.strip() == "python tools\\benchmark_v2_direct.py %*"
    )
    assert snapshot_idx < golden_idx < fallback_idx
    # CALL's second expansion removes only the leading selector from the
    # original argument string, preserving quoted remaining arguments.
    golden_start = next(i for i, l in enumerate(lines) if l.strip() == ') else if "!V2_GOLDEN_P1_ACTIVE!"=="1" (')
    golden_block = "\n".join(lines[golden_start:golden_idx + 1])
    assert 'set "V2_GOLDEN_ARGS=%*"' in golden_block
    assert 'if /i "%~1"=="golden_p1"' in golden_block
    assert 'call set "V2_GOLDEN_ARGS=%%V2_GOLDEN_ARGS:* =%%"' in golden_block
    assert 'set "V2_GOLDEN_ARGS="' in golden_block
    assert "python tools\\benchmark_v2_direct.py --golden-p1 %*" not in golden_block
    assert "V2_TOOL_ARGS" not in golden_block


def test_neither_bat_clobbers_the_flag_after_resolution():
    for name in ("deploy_and_run_v2_single.bat", "run_v2_single.bat"):
        for line in _bat_lines(name):
            if 'set "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=' not in line:
                continue
            # The ONLY legal assignment is the resolution-safe guard: an
            # already-resolved value (v2ctl profile/--set) must survive.
            assert line.strip().startswith(
                f"if not defined {FLAG} set "
            ), f"unguarded assignment would clobber resolved value: {line}"


def test_deploy_bat_never_routes_the_generation_flag():
    text = "\n".join(_bat_lines("deploy_and_run_v2_single.bat"))
    assert "--golden-p1" not in text


# ── Deploy-fingerprint sensitivity ────────────────────────────────────────


def test_flag_value_flips_deploy_fingerprint_inputs():
    base = cli.build_components(ROOT, "production")[4]
    flipped = cli.build_components(ROOT, "production", sets=[f"{FLAG}=true"])[4]
    assert base.deploy_inputs()["deploy_flags"][FLAG] == "0"
    assert flipped.deploy_inputs()["deploy_flags"][FLAG] == "1"
    assert base.deploy_fingerprint() != flipped.deploy_fingerprint()


def test_golden_p1_profile_differs_from_production_in_deploy_fingerprint():
    production = cli.build_components(ROOT, "production")[4]
    golden = cli.build_components(ROOT, "golden_p1")[4]
    assert golden.deploy_inputs()["deploy_flags"][FLAG] == "1"
    assert production.deploy_fingerprint() != golden.deploy_fingerprint()


# ── Run-safety contract unchanged ─────────────────────────────────────────


def test_explicit_deploy_required_flag_is_refused_at_run_time():
    config = _config("production", sets=[f"{FLAG}=true"])
    with pytest.raises(FlagError):
        cli.build_components(ROOT, "production", sets=[f"{FLAG}=true"])[2] \
            .check_run_safety(config, run_only=True)


def test_unknown_flag_run_safety_behavior_unchanged():
    resolver = cli.build_components(ROOT, "production")[2]
    config = _config("production", sets=["COMFYMODAL_V2_NOT_A_REAL_FLAG=1"])
    unknown = config.flag("COMFYMODAL_V2_NOT_A_REAL_FLAG")
    assert unknown is not None and unknown.registered is False
    with pytest.raises(FlagError):
        resolver.check_run_safety(config, run_only=True)


def test_profile_sourced_golden_flag_passes_run_safety():
    # Profile-owned values are canonical configuration; run-time refusal is
    # reserved for explicit override channels (--set/--inherit/cli).
    config = _config("golden_p1")
    cli.build_components(ROOT, "golden_p1")[2].check_run_safety(config, run_only=True)
