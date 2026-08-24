"""Golden loader genericity: CLIP/UNET/VAE through the SAME engine."""

from __future__ import annotations

import pytest

from comfymodal_runtime.golden.contracts import DestinationKind, ModelRole
from comfymodal_runtime.golden.pipeline import GOLDEN_ROLE_LOADER_POLICY
from comfymodal_runtime.golden.qd_engine import CpuCopyBackend, GoldenQD4Loader, QD4EngineConfig

from conftest import build_manifest, contiguous_destination, expected_data_bytes, parameter_destination


def _run(manifest, destination):
    return GoldenQD4Loader(QD4EngineConfig(), backend=CpuCopyBackend()).load(manifest, destination)


def test_clip_through_generic_loader_contiguous(small_clip_file):
    manifest = build_manifest(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    dest = contiguous_destination(manifest)
    result = _run(manifest, dest)
    assert result.ok
    names = [t.name for t in manifest.layout.tensor_map]
    assert names == ["w0", "w1"]
    dtypes = {t.dtype for t in manifest.layout.tensor_map}
    assert dtypes == {"F32"}
    shapes = {t.shape for t in manifest.layout.tensor_map}
    assert (64, 64) in shapes and (32, 128) in shapes
    data = expected_data_bytes(small_clip_file)
    data_start = manifest.qd_range_plan.data_start
    for entry in manifest.layout.tensor_map:
        expect = data[entry.abs_start - data_start : entry.abs_end - data_start]
        got = bytes(dest.buffers[0].numpy()[entry.abs_start - data_start : entry.abs_end - data_start])
        assert got == expect


def test_unet_through_same_loader_parameter_targets(unet_file):
    manifest = build_manifest(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    dest = parameter_destination(manifest)
    result = _run(manifest, dest)
    assert result.ok
    data = expected_data_bytes(unet_file)
    entries = sorted(manifest.layout.tensor_map, key=lambda t: t.abs_start)
    assert [e.name for e in entries] == ["blk0.w", "blk0.b", "blk1.w", "norm.g"]
    for entry, buf in zip(entries, dest.buffers):
        assert bytes(buf.numpy()) == data[entry.abs_start - manifest.qd_range_plan.data_start : entry.abs_end - manifest.qd_range_plan.data_start]


def test_vae_small_single_block_through_same_loader(vae_file):
    manifest = build_manifest(vae_file, ModelRole.VAE, 1048576, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    assert manifest.qd_range_plan.n_blocks == 1
    dest = contiguous_destination(manifest)
    result = _run(manifest, dest)
    assert result.ok
    assert result.telemetry.configured_qd == 4
    assert result.telemetry.completion_count == 1
    data = expected_data_bytes(vae_file)
    assert bytes(dest.buffers[0].numpy()) == data


def test_role_policy_immutable_qd4_for_all():
    assert dict(GOLDEN_ROLE_LOADER_POLICY) == {
        ModelRole.CLIP: "QD4",
        ModelRole.UNET: "QD4",
        ModelRole.VAE: "QD4",
    }
    with pytest.raises(TypeError):
        GOLDEN_ROLE_LOADER_POLICY[ModelRole.CLIP] = "FastSafe"  # type: ignore[index]
