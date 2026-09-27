"""Deterministic D15 request-scoped CLIP/UNET GPU-lane tests."""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from comfymodal_runtime import gpu_lane_coordination as coord
from comfymodal_runtime import model_preload as mp
from comfymodal_runtime import clip_fast_hydration as cfh
from comfymodal_runtime.clip_fast_hydration import install_gpu_critical_coordination
from comfymodal_runtime.trace import RuntimeTrace


@pytest.fixture(autouse=True)
def _clean_coordination():
    with patch.dict(
        "os.environ",
        {coord.COORDINATION_FLAG: "1"},
        clear=False,
    ):
        coord.reset_for_tests()
        yield
        coord.reset_for_tests()


def _wait_for_event(trace: RuntimeTrace, name: str, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(event.name == name for event in trace.events):
            return
        time.sleep(0.001)
    raise AssertionError(f"timed out waiting for {name}")


def test_miss_preserves_cpu_prepare_while_unet_gpu_waits_for_clip():
    trace = RuntimeTrace(request_id="d15-miss", process="remote")
    order: list[str] = []
    clip = coord.begin_clip_critical(
        "d15-miss", trace, reason="clip_encode", cache_state="cache_miss"
    )
    cpu_ready = threading.Event()
    transfer_ready = threading.Event()

    def unet_worker() -> None:
        order.append("unet_cpu_prepare_start")
        cpu_ready.set()
        order.append("unet_cpu_prepare_ready")
        gate = coord.begin_unet_gpu_phase("d15-miss", trace)
        transfer_ready.set()
        order.append("unet_gpu_transfer")
        coord.end_unet_gpu_phase(gate)

    worker = threading.Thread(target=unet_worker)
    worker.start()
    assert cpu_ready.wait(1.0)
    _wait_for_event(trace, "unet_gpu_gate_wait_start")
    assert not transfer_ready.is_set()
    assert order[:2] == ["unet_cpu_prepare_start", "unet_cpu_prepare_ready"]

    trace.emit("clip_forward_end", phase="execution", metadata={"request_id": "d15-miss"})
    coord.end_clip_critical(clip)
    assert transfer_ready.wait(1.0)
    worker.join(1.0)
    assert not worker.is_alive()
    assert order[-1] == "unet_gpu_transfer"
    assert any(event.name == "unet_gpu_gate_wait_end" for event in trace.events)


def test_cache_hit_has_no_clip_critical_section_and_unet_proceeds():
    trace = RuntimeTrace(request_id="d15-hit", process="remote")
    started = time.monotonic()
    gate = coord.begin_unet_gpu_phase("d15-hit", trace)
    coord.end_unet_gpu_phase(gate)
    assert time.monotonic() - started < 0.2
    assert not any(event.name == "clip_gpu_critical_enter" for event in trace.events)
    assert coord.active_request_ids() == ("d15-hit",)
    coord.request_end("d15-hit", trace)
    assert coord.active_request_ids() == ()


def test_clip_exception_releases_state_for_unet():
    trace = RuntimeTrace(request_id="d15-clip-error", process="remote")
    token = coord.begin_clip_critical("d15-clip-error", trace)
    coord.end_clip_critical(token, success=False, reason="clip_exception")
    gate = coord.begin_unet_gpu_phase("d15-clip-error", trace)
    coord.end_unet_gpu_phase(gate)
    assert not any(event.name == "clip_gpu_critical_active" for event in trace.events)


def test_unet_exception_releases_state_for_clip():
    trace = RuntimeTrace(request_id="d15-unet-error", process="remote")
    gate = coord.begin_unet_gpu_phase("d15-unet-error", trace)
    coord.end_unet_gpu_phase(gate, success=False)
    clip = coord.begin_clip_critical("d15-unet-error", trace)
    coord.end_clip_critical(clip, success=True)
    assert any(event.name == "clip_gpu_critical_enter" for event in trace.events)


def test_staged_clip_unet_emit_authoritative_readiness_gate():
    trace = RuntimeTrace(request_id="d15-staged-readiness", process="remote")
    with mp.request_execution_trace_scope(trace):
        coord.record_clip_ready(
            trace.request_id, trace, cache_state="staged_clip_miss"
        )
        coord.record_unet_ready(
            trace.request_id, trace, reason="staged_unet_ready"
        )
    gates = [event for event in trace.events if event.name == "model_readiness_gate"]
    assert len(gates) == 1
    metadata = gates[0].metadata
    assert metadata["MODEL_READINESS_GATE_AT"] == max(
        metadata["CLIP_READY_AT"], metadata["UNET_READY_AT"]
    )
    assert metadata["MODEL_READINESS_GATE_MS"] >= 0
    assert metadata["SAMPLER_GATED_BY"] in {"CLIP", "UNET", "TIE"}
    assert metadata["READINESS_GATED_BY"] == metadata["SAMPLER_GATED_BY"]


def test_request_state_does_not_cross_requests():
    trace = RuntimeTrace(request_id="d15-n", process="remote")
    clip = coord.begin_clip_critical("d15-n", trace)
    request_two_ready = threading.Event()

    def request_two() -> None:
        gate = coord.begin_unet_gpu_phase("d15-n-plus-one", trace)
        request_two_ready.set()
        coord.end_unet_gpu_phase(gate)

    worker = threading.Thread(target=request_two)
    worker.start()
    assert request_two_ready.wait(1.0)
    coord.end_clip_critical(clip)
    worker.join(1.0)
    assert not worker.is_alive()
    coord.request_end("d15-n", trace)
    coord.request_end("d15-n-plus-one", trace)
    assert coord.active_request_ids() == ()


class _FakeClip:
    def __init__(self, fail_load: bool = False) -> None:
        self.fail_load = fail_load

    def load_model(self, tokens=None):
        if self.fail_load:
            raise RuntimeError("load failed")
        return self

    def encode_from_tokens_scheduled(self, tokens, **kwargs):
        self.load_model(tokens)
        return "forward"

    def encode_from_tokens(self, tokens, **kwargs):
        self.load_model(tokens)
        return "forward"


def test_wrapped_encode_covers_hydration_forward_and_exception_release():
    trace = RuntimeTrace(request_id="d15-wrapper", process="remote")
    clip = _FakeClip()
    assert cfh.install_demand_wrapper(clip, lambda _clip: None)
    assert install_gpu_critical_coordination(clip) == "installed"
    with mp.request_execution_trace_scope(trace):
        assert clip.encode_from_tokens_scheduled({}) == "forward"
    names = [event.name for event in trace.events]
    assert names.index("clip_gpu_critical_enter") < names.index("clip_hydration_gpu_start")
    assert names.index("clip_hydration_gpu_end") < names.index("clip_forward_start")
    assert names.index("clip_forward_start") < names.index("clip_forward_end")
    assert names.index("clip_forward_end") < names.index("clip_gpu_critical_exit")

    error_trace = RuntimeTrace(request_id="d15-wrapper-error", process="remote")
    failing = _FakeClip(fail_load=True)
    assert install_gpu_critical_coordination(failing) == "installed"
    with mp.request_execution_trace_scope(error_trace):
        with pytest.raises(RuntimeError):
            failing.load_model({})
        gate = coord.begin_unet_gpu_phase("d15-wrapper-error", error_trace)
        coord.end_unet_gpu_phase(gate)
    assert any(event.name == "clip_gpu_critical_exit" for event in error_trace.events)


def test_existing_clip_sync_is_still_device_wide():
    source = open(
        "comfymodal_runtime/clip_fast_hydration_wiring.py",
        encoding="utf-8",
    ).read()
    assert "torch.cuda.synchronize()" in source


@pytest.mark.parametrize("activation_identity", ["cpu_snapshot", "native", "fallback"])
def test_shared_load_models_gpu_boundary_waits_for_all_unet_activation_paths(
    monkeypatch, activation_identity
):
    trace = RuntimeTrace(request_id=f"d15-{activation_identity}", process="remote")
    entered = threading.Event()
    finished = threading.Event()

    monkeypatch.setattr(mp, "_has_registered_unet_in_models", lambda _models: True)
    wrapped = mp._make_gpu_loader_wrapper(lambda *_args, **_kwargs: entered.set())
    clip = coord.begin_clip_critical(trace.request_id, trace)

    def activate() -> None:
        with mp.request_execution_trace_scope(trace):
            wrapped([object()])
        finished.set()

    worker = threading.Thread(target=activate)
    worker.start()
    _wait_for_event(trace, "unet_gpu_gate_wait_start")
    assert not entered.is_set()
    assert not finished.is_set()
    coord.end_clip_critical(clip)
    worker.join(1.0)
    assert not worker.is_alive()
    assert entered.is_set()
    assert finished.is_set()
    assert any(event.name == "unet_gpu_gate_wait_end" for event in trace.events)
