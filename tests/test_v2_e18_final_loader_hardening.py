"""Focused E18 contracts for scoped CUDA readiness and source fencing."""

from __future__ import annotations

import threading
import time

import pytest

from comfymodal_runtime import checkpoint_prewarm as cp
from comfymodal_runtime import fast_cold_orchestration as fco
from comfymodal_runtime import gpu_lane_coordination as coord


class _Reader:
    def __init__(self, gate: threading.Event, *, close_releases: bool) -> None:
        self.gate = gate
        self.close_releases = close_releases
        self.started = threading.Event()
        self.closed = False
        self.read_calls = 0

    def readinto(self, target):
        self.started.set()
        if not self.gate.wait(5.0):
            raise RuntimeError("reader gate was not released")
        self.read_calls += 1
        if self.closed:
            raise OSError("reader closed")
        target[: min(len(target), 1024)] = b"\x00" * min(len(target), 1024)
        return min(len(target), 1024)

    def close(self) -> None:
        self.closed = True
        if self.close_releases:
            self.gate.set()


class _FakeEvent:
    def __init__(self) -> None:
        self.recorded_on = None
        self.synchronize_calls = 0

    def record(self, stream=None) -> None:
        self.recorded_on = stream

    def synchronize(self) -> None:
        self.synchronize_calls += 1


class _FakeStream:
    def __init__(self) -> None:
        self.waited_events = []

    def wait_event(self, event) -> None:
        self.waited_events.append(event)


class _FakeCuda:
    def __init__(self) -> None:
        self.producer = _FakeStream()
        self.consumer = _FakeStream()
        self.events = []
        self.device_sync_calls = 0

    def is_available(self) -> bool:
        return True

    def current_stream(self):
        return self.consumer

    def Event(self, **_kwargs):
        event = _FakeEvent()
        self.events.append(event)
        return event

    def synchronize(self) -> None:
        self.device_sync_calls += 1


class _FakeTorch:
    def __init__(self) -> None:
        self.cuda = _FakeCuda()


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fco.reset_for_tests()
    coord.reset_for_tests()
    monkeypatch.delenv(fco.MASTER_FLAG, raising=False)
    monkeypatch.delenv(cp.PREWARM_FLAG, raising=False)
    monkeypatch.delenv(coord.SCOPED_CUDA_READINESS_FLAG, raising=False)
    yield
    fco.reset_for_tests()
    coord.reset_for_tests()


def _wait_for_started(readers: list[_Reader]) -> None:
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if any(reader.started.is_set() for reader in readers):
            return
        time.sleep(0.001)
    raise AssertionError("no prefetch reader reached source I/O")


def test_normal_prefetch_fence_retires_all_four_workers(monkeypatch, tmp_path):
    source = tmp_path / "checkpoint.safetensors"
    source.write_bytes(b"\x00" * (128 * 1024))
    gate = threading.Event()
    readers: list[_Reader] = []

    def open_reader(_path):
        reader = _Reader(gate, close_releases=False)
        readers.append(reader)
        return reader

    monkeypatch.setattr(cp, "_open_for_prewarm", open_reader)
    prewarmer = cp.CheckpointPrewarmer(
        enabled=True,
        threads=4,
        chunk_bytes=8 * 1024,
        join_timeout_ms=500,
    )
    assert prewarmer.start([str(source)]) is True
    gate.set()
    assert prewarmer.before_demand_load() is True
    snapshot = prewarmer.as_dict()
    assert snapshot["prewarm_threads"] == 4
    assert snapshot["prefetch_workers_alive_at_demand_start"] == 0
    assert snapshot["source_fence_valid"] is True
    assert snapshot["prefetch_retirement_result"] == "joined_primary"
    assert prewarmer._thread is not None and not prewarmer._thread.is_alive()
    assert all(not worker.is_alive() for worker in prewarmer._workers)


def test_stop_cannot_start_another_chunk_after_stop(monkeypatch, tmp_path):
    source = tmp_path / "checkpoint.safetensors"
    source.write_bytes(b"\x00" * (32 * 1024))
    gate = threading.Event()
    reader = _Reader(gate, close_releases=True)
    monkeypatch.setattr(cp, "_open_for_prewarm", lambda _path: reader)
    prewarmer = cp.CheckpointPrewarmer(
        enabled=True,
        threads=1,
        chunk_bytes=8 * 1024,
        join_timeout_ms=10,
        retirement_timeout_ms=200,
    )
    assert prewarmer.start([str(source)]) is True
    assert reader.started.wait(2.0)
    assert prewarmer.before_demand_load() is True
    calls_at_fence = reader.read_calls
    time.sleep(0.05)
    assert reader.read_calls == calls_at_fence
    assert prewarmer.as_dict()["source_fence_valid"] is True


def test_primary_timeout_uses_secondary_retirement_and_fd_close(monkeypatch, tmp_path):
    source = tmp_path / "checkpoint.safetensors"
    source.write_bytes(b"\x00" * (32 * 1024))
    gate = threading.Event()
    reader = _Reader(gate, close_releases=True)
    monkeypatch.setattr(cp, "_open_for_prewarm", lambda _path: reader)
    prewarmer = cp.CheckpointPrewarmer(
        enabled=True,
        threads=1,
        chunk_bytes=8 * 1024,
        join_timeout_ms=10,
        retirement_timeout_ms=200,
    )
    assert prewarmer.start([str(source)]) is True
    assert reader.started.wait(2.0)
    assert prewarmer.before_demand_load() is True
    snapshot = prewarmer.as_dict()
    assert snapshot["prefetch_workers_alive_after_primary_join"] > 0
    assert snapshot["prefetch_workers_alive_at_demand_start"] == 0
    assert snapshot["prefetch_retirement_result"] == "retired_after_fd_close"
    assert snapshot["prefetch_closed_handle_count"] >= 1
    assert snapshot["source_fence_valid"] is True


def test_final_retirement_failure_blocks_demand_and_is_explicit(monkeypatch, tmp_path):
    source = tmp_path / "checkpoint.safetensors"
    source.write_bytes(b"\x00" * (32 * 1024))
    gate = threading.Event()
    reader = _Reader(gate, close_releases=False)
    monkeypatch.setattr(cp, "_open_for_prewarm", lambda _path: reader)
    prewarmer = cp.CheckpointPrewarmer(
        enabled=True,
        threads=1,
        chunk_bytes=8 * 1024,
        join_timeout_ms=10,
        retirement_timeout_ms=20,
    )
    assert prewarmer.start([str(source)]) is True
    assert reader.started.wait(2.0)
    assert prewarmer.before_demand_load() is False
    snapshot = prewarmer.as_dict()
    assert snapshot["prefetch_workers_alive_at_demand_start"] > 0
    assert snapshot["demand_loader_start_at"] is None
    assert snapshot["prefetch_retirement_result"] == "retirement_failed"
    assert snapshot["source_fence_valid"] is False
    gate.set()
    assert prewarmer._thread is not None
    prewarmer._thread.join(2.0)


def test_storage_owner_does_not_become_demand_on_fence_failure(monkeypatch, tmp_path):
    monkeypatch.setenv(fco.MASTER_FLAG, "1")
    monkeypatch.setenv(cp.PREWARM_FLAG, "1")
    monkeypatch.setenv(cp.PREWARM_JOIN_MS_ENV, "10")
    monkeypatch.setenv(cp.PREWARM_RETIRE_MS_ENV, "20")
    source = tmp_path / "clip.safetensors"
    source.write_bytes(b"\x00" * (32 * 1024))
    gate = threading.Event()
    reader = _Reader(gate, close_releases=False)
    monkeypatch.setattr(cp, "_open_for_prewarm", lambda _path: reader)
    controller = fco.FastColdOrchestrator(
        "e18-fence-failure",
        model_spec={"loaders": {"clip": [{"path": str(source)}]}},
    )
    assert reader.started.wait(2.0)
    assert controller.before_clip_demand([str(source)]) is False
    assert controller.storage.storage_owner == fco.STORAGE_CLIP_PREFETCH
    assert controller.source_fence_failed() is True
    assert controller._record["orchestration_fallback_reason"] == "clip_source_fence_failed"
    gate.set()
    controller.finalize()


def test_unet_prefetch_still_overlaps_clip_forward(monkeypatch):
    monkeypatch.setenv(fco.MASTER_FLAG, "1")
    controller = fco.FastColdOrchestrator("e18-overlap")
    order: list[str] = []
    monkeypatch.setattr(
        controller,
        "start_unet_prefetch",
        lambda paths=None: order.append("unet_prefetch") or True,
    )
    controller.on_clip_forward_start()
    order.append("clip_forward")
    controller.on_clip_forward_end()
    assert order == ["unet_prefetch", "clip_forward"]
    assert controller._record["clip_forward_start_at"] <= controller._record[
        "clip_forward_end_at"
    ]
    controller.finalize()


def test_scoped_copy_event_records_and_waits_only_on_consumer_stream(monkeypatch):
    fake_torch = _FakeTorch()
    monkeypatch.setenv(coord.SCOPED_CUDA_READINESS_FLAG, "1")
    monkeypatch.setattr(coord, "_torch_api", lambda: fake_torch)
    producer = fake_torch.cuda.producer
    consumer = fake_torch.cuda.consumer
    event = coord.record_copy_event("clip", stream=producer)
    assert event is not None
    assert event.recorded_on is producer
    assert coord.wait_copy_event("clip", event, stream=consumer) is True
    assert consumer.waited_events == [event]
    assert fake_torch.cuda.device_sync_calls == 0


def test_scoped_cpu_event_sync_is_targeted(monkeypatch):
    fake_torch = _FakeTorch()
    monkeypatch.setenv(coord.SCOPED_CUDA_READINESS_FLAG, "1")
    monkeypatch.setattr(coord, "_torch_api", lambda: fake_torch)
    event = coord.record_copy_event("unet", stream=fake_torch.cuda.producer)
    assert event is not None
    assert coord.synchronize_copy_event("unet", event) is True
    assert event.synchronize_calls == 1
    assert fake_torch.cuda.device_sync_calls == 0


def test_scoped_feature_off_preserves_historical_mode(monkeypatch):
    fake_torch = _FakeTorch()
    monkeypatch.setattr(coord, "_torch_api", lambda: fake_torch)
    assert coord.scoped_cuda_readiness_enabled() is False
    assert coord.record_copy_event("clip", stream=fake_torch.cuda.producer) is None
    assert fake_torch.cuda.events == []


def test_event_lifecycle_telemetry_is_monotonic(monkeypatch):
    monkeypatch.setenv(fco.MASTER_FLAG, "1")
    controller = fco.FastColdOrchestrator("e18-telemetry")
    controller.record_copy_event("clip")
    controller.record_copy_event_wait("clip")
    controller.record_device_wide_sync("unet")
    record = controller._final_record()
    assert record["clip_copy_event_recorded_at"] <= record["clip_copy_event_waited_at"]
    assert record["clip_targeted_event_sync_count"] == 1
    assert record["unet_device_wide_sync_count"] == 1
    controller.finalize()


def test_complete_unet_lifecycle_reconciles_symmetrically(monkeypatch):
    monkeypatch.setenv(fco.MASTER_FLAG, "1")
    controller = fco.FastColdOrchestrator("e19-unet-lifecycle")
    controller.record_meta("start")
    controller.record_meta("ready")
    with controller._lock:
        controller._record["unet_prefetch_start_at"] = 1.0
        controller._record["unet_prefetch_end_at"] = 2.0
        controller._record["unet_source_fence_valid"] = True
    controller.record_fastsafe(
        "unet", "start", execution_identity="fastsafetensors"
    )
    controller.record_fastsafe(
        "unet", "end", event_recorded=True,
        execution_identity="fastsafetensors",
    )
    controller.record_commit_wait(3.5)
    controller.record_copy_event("unet", recorded_at=3.0)
    controller.record_copy_event_wait("unet", waited_at=4.0)
    controller.record_loader_execution_identity(
        "unet", "fastsafetensors"
    )
    controller.record_unet_gpu_interval(3.0, 4.0, identity="fastsafetensors")
    with controller._lock:
        controller._record["unet_ready_at"] = 4.5
    with controller._lock:
        controller._record["clip_ready_at"] = 2.5
    record = controller._final_record()
    assert record["unet_meta_start_at"] is not None
    assert record["unet_meta_ready_at"] is not None
    assert record["unet_prefetch_start_at"] == 1.0
    assert record["unet_prefetch_end_at"] == 2.0
    assert record["unet_fastsafe_start_at"] is not None
    assert record["unet_fastsafe_done_at"] is not None
    assert record["unet_gpu_commit_wait_ms"] == 3.5
    assert record["unet_copy_event_recorded"] is True
    assert record["unet_copy_event_waited"] is True
    assert record["unet_targeted_event_sync_count"] == 1
    assert record["unet_ready_at"] is not None
    assert record["unet_loader_execution_identity"] == "fastsafetensors"
    assert record["model_readiness_status"] == "KNOWN"
    controller.finalize()


@pytest.mark.parametrize(
    ("clip_ready", "unet_ready", "expected"),
    [(10.0, 20.0, "UNET"), (20.0, 10.0, "CLIP"), (10.0, 10.0, "TIE")],
)
def test_model_readiness_gate_is_deterministic(monkeypatch, clip_ready, unet_ready, expected):
    monkeypatch.setenv(fco.MASTER_FLAG, "1")
    controller = fco.FastColdOrchestrator(f"e19-ready-{expected}")
    controller.started_at = 0.0
    with controller._lock:
        controller._record["clip_ready_at"] = clip_ready
        controller._record["unet_ready_at"] = unet_ready
    record = controller._final_record()
    assert record["model_readiness_gate_at"] == max(clip_ready, unet_ready)
    assert record["model_readiness_gate_ms"] == max(clip_ready, unet_ready) * 1000.0
    assert record["readiness_gated_by"] == expected
    controller.finalize()


def test_missing_unet_readiness_is_unknown(monkeypatch):
    monkeypatch.setenv(fco.MASTER_FLAG, "1")
    controller = fco.FastColdOrchestrator("e19-ready-missing")
    with controller._lock:
        controller._record["clip_ready_at"] = 10.0
        controller._record["unet_ready_at"] = None
    record = controller._final_record()
    assert record["model_readiness_status"] == "UNKNOWN"
    assert record["model_readiness_gate_ms"] is None
    assert record["readiness_gated_by"] == "UNKNOWN"
    controller.finalize()
