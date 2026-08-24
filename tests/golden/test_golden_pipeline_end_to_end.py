"""End-to-end Golden pipeline walk: one schedule, three roles, exact events."""

from __future__ import annotations

import pytest

from comfymodal_runtime.golden.contracts import (
    DEFAULT_CONDITIONING_CONTRACT,
    DestinationKind,
    InMemoryLedgerSink,
    JoinDecision,
    ModelRole,
    RuntimeStatus,
)
from comfymodal_runtime.golden.pipeline import (
    GOLDEN_ROLE_LOADER_POLICY,
    GoldenPipeline,
    RoleBinding,
    final_status,
)
from comfymodal_runtime.golden.qd_engine import CpuCopyBackend, GoldenQD4Loader, QD4EngineConfig
from comfymodal_runtime.golden.resource_scheduler import GoldenResourceScheduler

from conftest import build_manifest, contiguous_destination, parameter_destination


def _binding(path, role, block_bytes, kind):
    manifest = build_manifest(path, role, block_bytes, kind)
    if kind == DestinationKind.PARAMETER_COPY_TARGET:
        return RoleBinding(role=role, manifest=manifest, destination_factory=lambda: parameter_destination(manifest))
    return RoleBinding(role=role, manifest=manifest, destination_factory=lambda: contiguous_destination(manifest))


def test_full_deterministic_timeline_nominal(small_clip_file, unet_file, vae_file):
    ledger = InMemoryLedgerSink()
    scheduler = GoldenResourceScheduler(ledger_sink=ledger)
    pipeline = GoldenPipeline(scheduler, ledger_sink=ledger, conditioning=DEFAULT_CONDITIONING_CONTRACT)
    loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())

    clip = _binding(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    unet = _binding(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    vae = _binding(vae_file, ModelRole.VAE, 1048576, DestinationKind.CONTIGUOUS_GPU_BUFFER)

    pipeline.begin_restore()
    pipeline.restore_ready()

    clip_result, clip_owner = pipeline.run_role_load(ModelRole.CLIP, loader, clip)
    assert clip_result.ok and clip_owner.state.value == "device_ready"

    pipeline.begin_clip_forward()
    pipeline.clip_storage_release_proof()
    prep = pipeline.unet_prepare(unet, loader)
    assert prep.block_count == unet.manifest.qd_range_plan.n_blocks
    assert prep.lifecycle_status == "SOURCE_PREPARED"

    # UNET commit before CLIP critical done must fail loudly.
    from comfymodal_runtime.golden.contracts import ForbiddenOverlapError

    with pytest.raises(ForbiddenOverlapError):
        pipeline.run_unet_commit(loader, unet)

    pipeline.clip_forward_complete()
    pipeline.clip_gpu_critical_done()
    unet_result, unet_owner = pipeline.run_unet_commit(loader, unet)
    assert unet_result.ok

    pipeline.sampling_started()
    pipeline.first_sampler_step_proven()
    vae_result, vae_owner = pipeline.run_vae_qd(loader, vae)
    assert vae_result.ok

    demand = pipeline.vae_decode_demand()
    assert demand["decision"] in (JoinDecision.JOINED.value, JoinDecision.ALREADY_READY.value)
    assert demand["degradation"] is None

    pipeline.complete_output()
    status = final_status(True, None)
    assert status == RuntimeStatus.ACCEPTED_NOMINAL

    names = ledger.names()
    for expected in [
        "restore_ready",
        "clip_device_ready",
        "clip_forward_started",
        "clip_storage_released",
        "unet_prepare_started",
        "clip_gpu_critical_done",
        "unet_device_ready",
        "sampling_started",
        "first_sampler_step_proven",
        "vae_device_ready",
        "vae_decode_demand",
        "first_durable_result",
    ]:
        assert expected in names, f"missing ledger event {expected}"


def test_vae_demand_without_owner_is_degraded(vae_file):
    scheduler = GoldenResourceScheduler()
    pipeline = GoldenPipeline(scheduler)
    pipeline.begin_restore()
    pipeline.restore_ready()
    # jump through phases without a VAE producer
    clip_stub = _binding(vae_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    loader = GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend())
    pipeline.run_role_load(ModelRole.CLIP, loader, clip_stub)
    pipeline.begin_clip_forward()
    pipeline.clip_storage_release_proof()
    unet_stub = _binding(vae_file, ModelRole.UNET, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    pipeline.unet_prepare(unet_stub, loader)
    pipeline.clip_forward_complete()
    pipeline.clip_gpu_critical_done()
    pipeline.run_unet_commit(loader, unet_stub)
    pipeline.sampling_started()
    pipeline.first_sampler_step_proven()
    result = pipeline.vae_decode_demand(join_timeout_s=0.05)
    assert result["degradation"] is not None
    assert final_status(True, result["degradation"]) == RuntimeStatus.DEGRADED


def test_role_policy_immutable_in_pipeline_module():
    assert all(policy == "QD4" for policy in GOLDEN_ROLE_LOADER_POLICY.values())
