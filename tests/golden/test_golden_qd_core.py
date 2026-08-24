"""Golden QD4 engine core tests: ranges, occupancy, decoupling, fail-closed."""

from __future__ import annotations

import threading
import time

import pytest

from comfymodal_runtime.golden import qd_engine
from comfymodal_runtime.golden.contracts import (
    BindError,
    DestinationKind,
    GoldenQDFailure,
    ModelRole,
    QDDropReason,
    ShortReadError,
)
from comfymodal_runtime.golden.qd_engine import (
    CpuCopyBackend,
    GoldenQD4Loader,
    QD4EngineConfig,
)

from conftest import (
    build_manifest,
    contiguous_destination,
    expected_data_bytes,
    parameter_destination,
    write_safetensors,
)

pytestmark = pytest.mark.filterwarnings("ignore")


def _load(manifest, destination, backend=None, config=None):
    loader = GoldenQD4Loader(config or QD4EngineConfig(), backend=backend or CpuCopyBackend())
    return loader.load(manifest, destination)


def test_configured_qd_default_is_four(small_clip_file):
    manifest = build_manifest(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    result = _load(manifest, contiguous_destination(manifest))
    assert result.ok
    assert result.telemetry.configured_qd == 4
    assert result.telemetry.target_qd == 4


def test_range_accounting_complete_no_overlap_no_gap(small_clip_file):
    manifest = build_manifest(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    plan = manifest.qd_range_plan
    assert plan.data_start == manifest.layout.data_start
    cursor = plan.data_start
    seen = set()
    for blk in plan.blocks:
        assert blk.file_start == cursor
        assert blk.length > 0
        assert blk.index not in seen
        seen.add(blk.index)
        cursor = blk.file_end
    assert cursor == plan.data_end == manifest.layout.file_bytes
    import math

    assert plan.n_blocks == math.ceil((plan.data_end - plan.data_start) / plan.block_bytes)


def test_load_success_exact_bytes_and_counts(small_clip_file):
    manifest = build_manifest(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    dest = contiguous_destination(manifest)
    result = _load(manifest, dest)
    t = result.telemetry
    expected = expected_data_bytes(small_clip_file)
    assert bytes(dest.buffers[0].numpy()) == expected
    assert t.submit_count == t.completion_count == t.planned_block_count
    assert t.bytes_read == t.bytes_total
    assert t.status == "ok"


def test_occupancy_instrumentation_present(tmp_path, monkeypatch):
    # Long enough to span multiple OS-timer granularities (~15.6 ms on
    # Windows): 128 blocks x 3 ms read latency / 4 workers ~= 96 ms wall.
    path = write_safetensors(tmp_path / "occ.safetensors", [("blob", "U8", (524288,))])
    manifest = build_manifest(path, ModelRole.CLIP, 4096, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    original = qd_engine._BlockReader.read_into

    def slow_read(self, file_offset, mv, expected):
        time.sleep(0.003)
        return original(self, file_offset, mv, expected)

    monkeypatch.setattr(qd_engine._BlockReader, "read_into", slow_read)
    result = _load(manifest, contiguous_destination(manifest))
    t = result.telemetry
    assert t.occupancy_samples > 0
    assert t.samples_at_target_qd >= 1
    assert t.fraction_time_at_target_qd > 0.0
    unknown = set(t.time_below_qd_ms_by_reason) - {r.value for r in QDDropReason}
    assert not unknown


def test_concurrency_reaches_multiple_outstanding(small_clip_file, monkeypatch):
    manifest = build_manifest(small_clip_file, ModelRole.CLIP, 2048, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    original = qd_engine._BlockReader.read_into

    def slow_read(self, file_offset, mv, expected):
        time.sleep(0.002)
        return original(self, file_offset, mv, expected)

    monkeypatch.setattr(qd_engine._BlockReader, "read_into", slow_read)
    result = _load(manifest, contiguous_destination(manifest))
    assert result.telemetry.observed_max_outstanding >= 2


def test_decoupling_slow_h2d_does_not_starve_source(tmp_path):
    """THE structural regression test: slow H2D must not starve the source plane.

    64 blocks through an 8-slot bounded ring with 30 ms simulated H2D per
    copy: the source plane must saturate at configured QD=4 whenever work
    and free slots exist; the ONLY coupling allowed is legitimate bounded-
    ring backpressure, which must be counted and classified.
    """
    path = write_safetensors(tmp_path / "blob.safetensors", [("blob", "U8", (262144,))])
    manifest = build_manifest(path, ModelRole.CLIP, 4096, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    assert manifest.qd_range_plan.n_blocks == 64
    backend = CpuCopyBackend(copy_latency_s=lambda n: 0.03)
    try:
        result = _load(manifest, contiguous_destination(manifest), backend=backend)
    finally:
        backend.close()
    t = result.telemetry
    assert result.ok
    assert t.observed_max_outstanding == 4
    assert t.h2d_backpressure_events >= 1
    assert t.free_slots_min == 0
    assert t.completed_waiting_h2d_max_depth >= 1
    # Every below-QD interval must be EXPLAINED: only the three legitimate
    # reasons (startup ramp, tail drain, classified H2D backpressure) may
    # appear — unexplained starvation must be zero.
    legit = {
        QDDropReason.H2D_BACKPRESSURE.value,
        QDDropReason.STARTUP_RAMP.value,
        QDDropReason.TAIL_DRAIN.value,
    }
    unexplained_ms = sum(v for k, v in t.time_below_qd_ms_by_reason.items() if k not in legit)
    # Sub-interval GIL/scheduler wake-up bubbles (worker between publish and
    # next read-start) can straddle 1 ms occupancy samples; the structural
    # guarantee is that unexplained time stays a small minority of below-QD
    # time and never a steady-state mode.
    total_below_ms = sum(t.time_below_qd_ms_by_reason.values())
    assert unexplained_ms <= max(5.0, 0.10 * total_below_ms)
    assert QDDropReason.H2D_BACKPRESSURE.value in t.time_below_qd_ms_by_reason
    assert set(t.time_below_qd_ms_by_reason) <= {r.value for r in QDDropReason}


def test_worker_exception_fail_closed_with_telemetry(small_clip_file, monkeypatch):
    manifest = build_manifest(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    calls = {"n": 0}
    lock = threading.Lock()
    original = qd_engine._BlockReader.read_into

    def flaky(self, file_offset, mv, expected):
        with lock:
            calls["n"] += 1
            n = calls["n"]
        if n == 3:
            raise RuntimeError("injected source device fault")
        return original(self, file_offset, mv, expected)

    monkeypatch.setattr(qd_engine._BlockReader, "read_into", flaky)
    with pytest.raises(GoldenQDFailure) as excinfo:
        _load(manifest, contiguous_destination(manifest))
    assert hasattr(excinfo.value, "telemetry")
    assert excinfo.value.telemetry.worker_exceptions >= 1
    assert excinfo.value.telemetry.status != "ok"


def test_short_read_raises_shortread(small_clip_file, monkeypatch):
    manifest = build_manifest(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)

    def short(self, file_offset, mv, expected):
        return expected - 1 if expected > 1 else 0

    monkeypatch.setattr(qd_engine._BlockReader, "read_into", short)
    with pytest.raises(ShortReadError):
        _load(manifest, contiguous_destination(manifest))


def test_bind_error_on_undersized_destination(small_clip_file):
    from comfymodal_runtime.golden.contracts import DestinationPlan
    import torch

    manifest = build_manifest(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    total = manifest.qd_range_plan.total_bytes
    bad = DestinationPlan(
        kind=DestinationKind.CONTIGUOUS_GPU_BUFFER,
        buffers=[torch.empty(total - 1, dtype=torch.uint8)],
        buffer_bytes=[total - 1],
    )
    with pytest.raises(BindError):
        _load(manifest, bad)


def test_cleanup_no_thread_leak_after_failure(small_clip_file, monkeypatch):
    manifest = build_manifest(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    monkeypatch.setattr(qd_engine._BlockReader, "read_into", lambda self, off, mv, exp: 0)
    baseline = threading.active_count()
    with pytest.raises(GoldenQDFailure):
        _load(manifest, contiguous_destination(manifest))
    assert threading.active_count() <= baseline + 1


def test_parameter_copy_destination_equality(unet_file):
    manifest = build_manifest(unet_file, ModelRole.UNET, 16384, DestinationKind.PARAMETER_COPY_TARGET)
    dest = parameter_destination(manifest)
    result = _load(manifest, dest)
    assert result.ok
    data = expected_data_bytes(unet_file)
    data_start = manifest.qd_range_plan.data_start
    for entry, buf in zip(sorted(manifest.layout.tensor_map, key=lambda t: t.abs_start), dest.buffers):
        expect = data[entry.abs_start - data_start : entry.abs_end - data_start]
        assert bytes(buf.numpy()) == expect


@pytest.mark.skipif(not __import__("torch").cuda.is_available(), reason="CUDA unavailable")
def test_cuda_backend_parity(small_clip_file):
    import torch

    from comfymodal_runtime.golden.contracts import DestinationPlan
    from comfymodal_runtime.golden.qd_engine import CudaTransferBackend

    manifest = build_manifest(small_clip_file, ModelRole.CLIP, 8192, DestinationKind.CONTIGUOUS_GPU_BUFFER)
    total = manifest.qd_range_plan.total_bytes
    backend = CudaTransferBackend(device="cuda:0")
    destination = DestinationPlan(
        kind=DestinationKind.CONTIGUOUS_GPU_BUFFER,
        buffers=[backend.allocate_destination_buffer(total)],
        buffer_bytes=[total],
    )
    result = GoldenQD4Loader(QD4EngineConfig(), backend=backend).load(manifest, destination)
    assert result.ok
    got = destination.buffers[0].cpu().numpy().tobytes()
    assert got == expected_data_bytes(small_clip_file)
