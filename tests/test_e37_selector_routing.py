from __future__ import annotations

from pathlib import Path

from tools.v2_control import cli


ROOT = Path(__file__).resolve().parents[1]


def _resolved(profile: str, *, strict: bool = False):
    sets = ["COMFYMODAL_V2_E37_STRICT_PROOF=1"] if strict else []
    return cli.build_components(
        ROOT,
        profile,
        cli_options={"workload.nonce": "workload-e37-nonce"},
        sets=sets,
    )[3]


def test_e37_profiles_win_over_inherited_e28_selector():
    for profile in ("e37-clip-qd4", "e37-clip-fastsafe"):
        config = _resolved(profile)
        assert cli._backend_selector(config) == "E37_VALIDATION"
        assert getattr(config.flag("V2_E28_VALIDATION"), "value", None) == "1"


def test_clean_lane_profile_uses_distinct_selector_and_never_projects_e19():
    config = _resolved("e37-clean-lane-qd4")
    assert cli._backend_selector(config) == "E37_CLEAN_LANE_VALIDATION"
    args, env = cli._validation_backend_args(config)

    assert args[0] == "E37_CLEAN_LANE_VALIDATION"
    assert env["COMFYMODAL_V2_E37_CLEAN_LANE"] == "1"
    assert env["COMFYMODAL_V2_CLEAN_LANE"] == "1"
    assert env["V2_E37_CONDITIONING_NONCE"] == "workload-e37-nonce"
    assert env["V2_E28_VALIDATION"] == "0"
    assert env["V2_E31_VALIDATION"] == "0"
    assert "V2_E19_FINAL_COLD_LOADER" not in env


def test_e37_strict_flag_wins_over_inherited_e28_selector():
    config = _resolved("e29-tracer", strict=True)
    assert cli._backend_selector(config) == "E37_VALIDATION"


def test_e37_validation_args_use_e37_nonce_and_full_run_mode():
    config = _resolved("e37-clip-qd4")
    args, env = cli._validation_backend_args(config)

    assert args == [
        "E37_VALIDATION",
        "--run-count",
        "1",
        "--conditioning-cache-nonce",
        "workload-e37-nonce",
    ]
    assert env["V2_E37_CONDITIONING_NONCE"] == "workload-e37-nonce"
    assert env["V2_E37_VALIDATION"] == "1"
    assert env["V2_E28_VALIDATION"] == "0"
    assert env["V2_E31_VALIDATION"] == "0"
    assert env["V2_BENCHMARK_MODE"] == "e37_single"
    assert env["V2_BENCHMARK_RUNS"] == "1"
    assert "V2_E28_CONDITIONING_NONCE" not in env


def test_e37_batch_paths_are_fail_closed_and_do_not_rewrite_e28_or_e31_values():
    deploy = (ROOT / "deploy_and_run_v2_single.bat").read_text(encoding="utf-8")
    run = (ROOT / "run_v2_single.bat").read_text(encoding="utf-8")
    benchmark = (ROOT / "tools" / "benchmark_v2_direct.py").read_text(encoding="utf-8")

    deploy_block = deploy.split("REM -- E37 late CLIP validation selector", 1)[1].split(
        "REM -- E31 QD4 cast-once validation selector", 1
    )[0]
    assert "E37_VALIDATION" in deploy_block
    assert 'set "V2_E19_FINAL_COLD_LOADER=1"' not in deploy_block
    assert 'set "V2_E28_VALIDATION=0"' in deploy_block
    assert 'set "V2_E31_VALIDATION=0"' in deploy_block
    assert 'set "V2_BENCHMARK_MODE=e37_single"' in deploy_block
    assert "restore_earliest" not in deploy_block.split("set \"", 1)[-1]
    assert 'set "COMFYMODAL_V2_GANTT_TELEMETRY=1"' not in deploy_block
    assert 'set "COMFYMODAL_V2_E27_FORENSICS=1"' not in deploy_block
    assert 'set "COMFYMODAL_V2_E31_FORENSICS=1"' not in deploy_block
    assert "--verify-e37-profile --run-count 1" in deploy
    assert "selector=E37_VALIDATION" in deploy

    run_block = run.split("REM -- E37 late CLIP validation selector", 1)[1].split(
        "if not defined V2_E28_VALIDATION", 1
    )[0]
    assert 'set "V2_E19_FINAL_COLD_LOADER=1"' in run_block
    assert 'set "V2_E28_VALIDATION=0"' in run_block
    assert 'set "V2_E31_VALIDATION=0"' in run_block
    assert 'set "V2_BENCHMARK_MODE=e37_single"' in run_block
    assert 'set "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY=restore_earliest"' not in run_block
    assert "--verify-e37-profile --run-count 1" in run
    assert "--verify-run-preflight --run-count 1 --conditioning-cache-nonce !V2_E37_CONDITIONING_NONCE!" in run

    assert '"E37_VALIDATION"' in benchmark
    assert "--verify-e37-profile" in benchmark
    assert "def verify_e37_validation_profile" in benchmark
    assert "def verify_e37_clean_lane_profile" in benchmark
    assert "--verify-e37-clean-lane-profile" in benchmark


def test_clean_lane_batch_path_forces_the_off_tuple_without_changing_legacy_e37():
    deploy = (ROOT / "deploy_and_run_v2_single.bat").read_text(encoding="utf-8")
    run = (ROOT / "run_v2_single.bat").read_text(encoding="utf-8")
    clean_block = deploy.split("\n:e37_clean_validation\n", 1)[1].split(
        ":e37_fail_no_e19", 1
    )[0]
    assert 'set "COMFYMODAL_V2_ATOMIC_PROFILE=E37_CLEAN_LANE"' in clean_block
    assert 'set "COMFYMODAL_V2_CHECKPOINT_PREWARM=0"' in clean_block
    assert 'set "COMFYMODAL_V2_UNET_FASTSAFETENSORS=0"' in clean_block
    assert 'set "COMFYMODAL_V2_PREFILL_LANES=none"' in clean_block
    assert 'set "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=0"' in clean_block
    legacy_block = deploy.split("REM -- E37 late CLIP validation selector", 1)[1].split(
        "REM -- E31 QD4 cast-once validation selector", 1
    )[0]
    assert 'set "V2_E19_FINAL_COLD_LOADER=1"' not in legacy_block
    assert "e19=1" in legacy_block
    clear = 'if "!V2_E37_CLEAN_LANE_ACTIVE!"=="0" set "COMFYMODAL_V2_ATOMIC_PROFILE="'
    clean_profile = 'set "COMFYMODAL_V2_ATOMIC_PROFILE=E37_CLEAN_LANE"'
    assert clear in run
    assert run.index(clean_profile) < run.index(clear)
