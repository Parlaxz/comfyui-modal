"""Focused offline contracts for the Golden parallel foundation."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.v2_control import cli
from tools.v2_control.golden_payload import _golden_p1_request_payload


ROOT = Path(__file__).resolve().parents[1]
PARALLEL_SOURCE = ROOT / "comfymodal_runtime" / "golden_parallel.py"
SERIAL_SOURCE = ROOT / "comfymodal_runtime" / "golden_serial.py"
HARNESS_SOURCE = ROOT / "tools" / "benchmark_v2_direct.py"
M2_PROFILE = ROOT / "config" / "v2" / "profiles" / "golden_p1_parallel_m2clip_h100.toml"
MODEL_TRANSPORT_SOURCE = ROOT / "comfymodal_runtime" / "golden_model_transport.py"

pytestmark = pytest.mark.fast_unit


def _config(profile: str):
    return cli.build_components(ROOT, profile)[3]


def test_parallel_profile_selects_distinct_method_mode_and_comfy_kitchen_backend():
    config = _config("golden_p1_parallel")
    assert config.target.method == "run_golden_parallel_stream"
    assert config.target.app == "batch-r0-golden-parallel-ops"
    assert cli._benchmark_mode(config) == "golden_p1_parallel"
    attention = config.flag("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND")
    assert attention is not None
    assert attention.value == "comfy_kitchen"
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


def test_parallel_c0_profile_keeps_overlap_and_selects_c0_shared_arena():
    # FAST C0 contract: the 12-CPU parallel profile routes CLIP/UNET/VAE
    # through the shared transport, and the transport must resolve to the C0
    # shared arena (16 x 64 MiB, streaming, frozen exact-window mmap engine) --
    # never to a standalone M2 execution arm.
    profile = M2_PROFILE.read_text(encoding="utf-8")
    transport = MODEL_TRANSPORT_SOURCE.read_text(encoding="utf-8")
    serial = SERIAL_SOURCE.read_text(encoding="utf-8")
    config = _config("golden_p1_parallel_m2clip_h100")
    clip_loader = config.flag("COMFYMODAL_GOLDEN_CLIP_LOADER")
    model_transport = config.flag("COMFYMODAL_GOLDEN_MODEL_TRANSPORT")

    assert config.target.method == "run_golden_parallel_stream"
    assert config.resources.cpu == 12
    assert clip_loader is not None and clip_loader.value == "m2"
    assert model_transport is not None and str(model_transport.value).lower() in {"1", "true"}
    assert 'COMFYMODAL_GOLDEN_CLIP_LOADER = "m2"' in profile
    assert 'COMFYMODAL_GOLDEN_MODEL_TRANSPORT = "1"' in profile
    assert 'COMFYMODAL_GOLDEN_CLIP_UNET_SCHEDULE = "overlap"' in profile
    assert 'COMFYMODAL_GOLDEN_SAMPLING_VAE_SCHEDULE = "overlap"' in profile
    # C0 shared-arena selectors (deploy-baked): streaming + exact-window mmap
    # engine + treatment geometry over the registered POSIX backing.
    assert 'COMFYMODAL_GOLDEN_IO_PROCESS_V2 = "1"' in profile
    assert 'COMFYMODAL_GOLDEN_IO_PROCESS_V2_BACKING = "posix"' in profile
    assert 'COMFYMODAL_GOLDEN_IO_PROCESS_V2_STREAMING = "1"' in profile
    assert 'COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_ENGINE = "mmap_fresh"' in profile
    assert 'COMFYMODAL_GOLDEN_IO_PROCESS_V2_SOURCE_GEOMETRY = "qd4_64"' in profile
    assert 'COMFYMODAL_GOLDEN_C0_HOST_REGISTER = "1"' in profile
    # The C0 dispatch lives inside the transport; the standalone M2 loader
    # wrapper must not be reachable from it.
    assert "_load_c0_sync" in transport
    assert "_load_canonical_m2_sync" not in transport
    assert "load_m2_safetensors" not in transport
    assert '"execution_architecture": "c0_parallel"' in transport
    assert '"source_engine": "m2_exact_window"' in transport
    # Each major model load names its role so the 30 s load gate can fail as
    # golden_clip_load_timeout_30s / golden_unet_load_timeout_30s.  The role is
    # a label on the gate, never a change of which loader runs.
    assert "transport.load_sync(path, role=role)" in serial
    assert 'shared_transport.load(unet_path, role="unet")' in serial
    assert 'model_transport.load(session.model_paths["vae"])' in serial


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
