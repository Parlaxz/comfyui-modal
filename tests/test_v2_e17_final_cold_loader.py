"""Offline contracts for the opt-in E17 cold-loader orchestration."""

from __future__ import annotations

import threading
import time

import pytest

from comfymodal_runtime import checkpoint_prewarm as cp
from comfymodal_runtime import fast_cold_orchestration as fco


def _model_spec(clip_path: str, unet_path: str) -> dict:
    return {
        "loaders": {
            "clip": [{"path": clip_path}],
            "unet": [{"path": unet_path}],
        }
    }


class _BlockedFile:
    def __init__(self, gate: threading.Event) -> None:
        self.gate = gate
        self.started = threading.Event()
        self._data = b"\x00" * (64 * 1024)
        self._offset = 0
        self._lock = threading.Lock()

    def readinto(self, target):
        self.started.set()
        if not self.gate.wait(5.0):
            raise RuntimeError("blocked reader was not released")
        with self._lock:
            if self._offset >= len(self._data):
                return 0
            count = min(len(target), len(self._data) - self._offset)
            target[:count] = self._data[self._offset : self._offset + count]
            self._offset += count
            return count

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _clean_orchestration(monkeypatch):
    fco.reset_for_tests()
    monkeypatch.delenv(fco.MASTER_FLAG, raising=False)
    monkeypatch.delenv(cp.PREWARM_FLAG, raising=False)
    yield
    fco.reset_for_tests()


def test_master_orchestration_is_opt_in(monkeypatch):
    assert fco.enabled() is False
    assert fco.begin_request("e17-off") is None

    monkeypatch.setenv(fco.MASTER_FLAG, "1")
    controller = fco.begin_request("e17-on")
    assert controller is not None
    assert controller.storage.storage_owner == fco.STORAGE_NONE
    fco.finalize_request("e17-on")


def test_resolve_model_paths_is_generic_and_deduplicated(tmp_path):
    clip = tmp_path / "clip.safetensors"
    unet = tmp_path / "unet.safetensors"
    clip.write_bytes(b"clip")
    unet.write_bytes(b"unet")
    spec = {
        "loaders": {
            "clip": [
                {"path": str(clip), "clip_name": str(clip)},
            ],
            "unet": [
                {"path": str(unet), "resolved_path": str(unet)},
            ],
        }
    }

    assert fco.resolve_model_paths(spec) == {
        "clip": [str(clip)],
        "unet": [str(unet)],
    }


def test_parallel_prewarm_has_bounded_demand_guard(monkeypatch, tmp_path):
    source = tmp_path / "checkpoint.safetensors"
    source.write_bytes(b"\x00" * (64 * 1024))
    gate = threading.Event()
    fake = _BlockedFile(gate)
    monkeypatch.setattr(cp, "_open_for_prewarm", lambda _path: fake)

    prewarmer = cp.CheckpointPrewarmer(
        enabled=True,
        threads=2,
        chunk_bytes=1024,
        join_timeout_ms=50,
        retirement_timeout_ms=100,
    )
    assert prewarmer.start([str(source)]) is True
    assert fake.started.wait(2.0)

    started = time.monotonic()
    assert prewarmer.before_demand_load() is False
    assert time.monotonic() - started < 1.0
    snapshot = prewarmer.as_dict()
    assert snapshot["prewarm_stop_reason"] == "retirement_failed"
    assert snapshot["prewarm_finished_before_demand"] is False
    assert snapshot["demand_loader_start_at"] is None
    assert snapshot["source_fence_valid"] is False

    # The blocked readers are daemon workers, but tests must release and join
    # them so no work leaks into later cases.
    gate.set()
    if prewarmer._thread is not None:
        prewarmer._thread.join(2.0)
    for worker in prewarmer._workers:
        worker.join(2.0)
    assert prewarmer._thread is not None and not prewarmer._thread.is_alive()
    assert all(not worker.is_alive() for worker in prewarmer._workers)


def test_parallel_defaults_are_only_selected_for_env_enabled_runtime(monkeypatch):
    monkeypatch.setenv(cp.PREWARM_FLAG, "1")
    prewarmer = cp.CheckpointPrewarmer()
    assert prewarmer._threads == cp.DEFAULT_THREADS
    assert prewarmer._chunk_bytes == cp.DEFAULT_CHUNK_BYTES

    explicit = cp.CheckpointPrewarmer(enabled=True)
    assert explicit._threads == 1


def test_unet_demand_retires_clip_prefetch_before_transition(monkeypatch, tmp_path):
    monkeypatch.setenv(fco.MASTER_FLAG, "1")
    monkeypatch.setenv(cp.PREWARM_FLAG, "1")
    monkeypatch.setenv(fco.COMMIT_WAIT_MS_ENV, "0")
    clip = tmp_path / "clip.safetensors"
    unet = tmp_path / "unet.safetensors"
    clip.write_bytes(b"clip" * 1024)
    unet.write_bytes(b"unet" * 1024)

    controller = fco.FastColdOrchestrator(
        "e17-transition",
        model_spec=_model_spec(str(clip), str(unet)),
    )
    assert controller.storage.storage_owner == fco.STORAGE_CLIP_PREFETCH
    assert controller.before_unet_demand([str(unet)]) is True
    assert controller.storage.storage_owner == fco.STORAGE_UNET_DEMAND
    transitions = controller.storage.transitions
    assert [(item.transition_from, item.transition_to) for item in transitions] == [
        (fco.STORAGE_NONE, fco.STORAGE_CLIP_PREFETCH),
        (fco.STORAGE_CLIP_PREFETCH, fco.STORAGE_CLIP_DEMAND),
        (fco.STORAGE_CLIP_DEMAND, fco.STORAGE_UNET_DEMAND),
    ]
    assert all(
        not (
            item.transition_from == fco.STORAGE_CLIP_PREFETCH
            and item.transition_to == fco.STORAGE_UNET_DEMAND
        )
        for item in transitions
    )
    controller.finalize()


def test_commit_wait_is_counted_once(monkeypatch):
    monkeypatch.setenv(fco.MASTER_FLAG, "1")
    monkeypatch.setenv(fco.COMMIT_WAIT_MS_ENV, "500")
    controller = fco.FastColdOrchestrator("e17-wait")

    result: list[bool] = []

    def demand() -> None:
        result.append(controller.before_unet_demand())

    worker = threading.Thread(target=demand)
    worker.start()
    time.sleep(0.02)
    controller.on_clip_forward_end()
    worker.join(2.0)

    assert not worker.is_alive()
    assert result == [True]
    recorded = controller._record["unet_gpu_commit_wait_ms"]
    assert recorded >= 10.0
    assert recorded < 100.0
    controller.finalize()
