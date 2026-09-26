"""Focused offline contracts for the Golden parallel foundation."""

from __future__ import annotations

from pathlib import Path

from tools.v2_control import cli
from tools.v2_control.golden_payload import _golden_p1_request_payload


ROOT = Path(__file__).resolve().parents[1]
PARALLEL_SOURCE = ROOT / "comfymodal_runtime" / "golden_parallel.py"
SERIAL_SOURCE = ROOT / "comfymodal_runtime" / "golden_serial.py"
HARNESS_SOURCE = ROOT / "tools" / "benchmark_v2_direct.py"


def _config(profile: str):
    return cli.build_components(ROOT, profile)[3]


def test_parallel_profile_selects_distinct_method_mode_and_sage_default():
    config = _config("golden_p1_parallel")
    assert config.target.method == "run_golden_parallel_stream"
    assert config.target.app == "batch-r0-golden-parallel-ops"
    assert cli._benchmark_mode(config) == "golden_p1_parallel"
    attention = config.flag("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND")
    assert attention is not None
    assert attention.value == "sage"
    assert cli.golden_method_for_profile(config.profile_name) == config.target.method


def test_omitted_attention_is_explicit_sage_and_parallel_payload_is_not_serial():
    source = {"prompt": {"1": {}}, "extra_data": {}, "modal_options": {}}
    payload = _golden_p1_request_payload(
        source,
        request_id="parallel-default",
        index=0,
        golden_mode="parallel",
    )
    assert payload["attention_backend"] == "sage"
    assert payload["request_origin_info"]["golden_mode"] == "parallel"
    assert payload["request_origin_info"]["serial"] is False


def test_parallel_orchestrator_overlaps_independent_model_stages():
    source = PARALLEL_SOURCE.read_text(encoding="utf-8")
    assert "golden_clip_forward_unet_window" in source
    assert "golden_sampling_vae_window" in source
    assert "_resolve_clip_unet_schedule" in source
    assert "_resolve_sampling_vae_schedule" in source
    assert "GoldenSerialRunner" not in source


def test_serial_entrypoint_and_parallel_entrypoint_are_distinct():
    serial = SERIAL_SOURCE.read_text(encoding="utf-8")
    parallel = PARALLEL_SOURCE.read_text(encoding="utf-8")
    assert "async def golden_serial_execute" in serial
    assert "async def golden_parallel_execute" in parallel
    assert "golden_parallel_execute" not in serial


def test_parallel_harness_routes_method_and_persists_parallel_mode():
    source = HARNESS_SOURCE.read_text(encoding="utf-8")
    assert 'GOLDEN_PARALLEL_REMOTE_METHOD = "run_golden_parallel_stream"' in source
    assert '"golden_mode": golden_mode' in source
    assert "_golden_p1_consume_stream(handle, payload, remote_method)" in source
    assert '"--golden-mode", "--golden-p1-mode"' in source


def test_parallel_bat_selector_is_not_rejected_or_sent_to_serial_harness():
    run_bat = (ROOT / "run_v2_single.bat").read_text(encoding="utf-8")
    assert 'golden_p1_parallel' in run_bat
    assert "golden_p1_parallel requires V2_BENCHMARK_MODE=golden_p1_parallel" in run_bat
    assert "--golden-p1 --golden-mode parallel" in run_bat
