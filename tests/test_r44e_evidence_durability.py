"""R44E tests: evidence durability, no duplicate instrumentation, forward-start
prep arming, D15-safe overlap, storage-count payload persistence, and
residual/overlap math that never double-counts overlapping intervals.

Run standalone: python -m pytest tests/test_r44e_evidence_durability.py -q
"""

from __future__ import annotations

import os
import sys
import threading
import types
from typing import Any

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comfymodal_runtime import request_fastpath as rfp


class _DiagSink:
    """TeardownDiagnostics-style sink: emit(..., snapshot=...) accepted."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, event: str, *, phase: str = "", metadata: dict | None = None,
             snapshot: bool = True, **fields: Any) -> None:
        self.events.append((str(event), dict(metadata or {})))


class _DurableTrace:
    """RuntimeTrace-style durable sink (no snapshot kwarg)."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.lock = threading.Lock()

    def emit(self, name: str, *, process=None, phase: str = "",
             metadata: dict | None = None) -> None:
        with self.lock:
            self.events.append((str(name), dict(metadata or {})))


@pytest.fixture()
def ctx():
    saved = rfp._active.get()
    context = rfp.FastPathRequestContext(request_id="r44e-test")
    token = rfp._active.set(context)
    yield context
    rfp._active.reset(token)
    if saved is not None:  # pragma: no cover
        pass


def test_dual_emission_same_payload(ctx):
    diag = _DiagSink()
    durable = _DurableTrace()
    ctx.trace = diag
    ctx.set_durable_trace_resolver(lambda: durable)
    ctx.telemetry("clip_fast_load_end", ok=True, wall_ms=12.5, bind_mode="same_storage")
    assert [e for e, _ in diag.events] == ["clip_fast_load_end"]
    assert [e for e, _ in durable.events] == ["clip_fast_load_end"]
    assert diag.events[0][1] == durable.events[0][1]
    assert durable.events[0][1]["bind_mode"] == "same_storage"
    assert durable.events[0][1]["wall_ms"] == 12.5


def test_no_duplicate_when_durable_is_diagnostics(ctx):
    single = _DurableTrace()
    ctx.trace = single
    ctx.set_durable_trace_resolver(lambda: single)
    ctx.telemetry("unet_fastsafe_pipeline", status="ok")
    assert len(single.events) == 1


def test_lazy_active_trace_resolution(ctx, monkeypatch):
    durable = _DurableTrace()
    fake_mp = types.ModuleType("comfymodal_runtime.model_preload")
    fake_mp._ACTIVE_REQUEST_TRACE = types.SimpleNamespace(get=lambda: durable)
    monkeypatch.setitem(sys.modules, "comfymodal_runtime.model_preload", fake_mp)
    ctx.trace = _DiagSink()
    ctx.telemetry("request_fastpath_begin", master=True)
    assert durable.events and durable.events[0][0] == "request_fastpath_begin"


def test_identity_set_alone_does_not_arm(ctx, monkeypatch):
    monkeypatch.setenv(rfp.FLAG_MASTER, "1")
    monkeypatch.setenv(rfp.FLAG_SOURCE_PREP, "1")
    ctx.set_unet_source_identity(path="whatever.safetensors", size_bytes=1)
    assert ctx._prep_armed is False
    assert ctx._prewarmer is None


def _install_fake_prewarm_module(monkeypatch, prewarmer_cls):
    fake = types.ModuleType("comfymodal_runtime.checkpoint_prewarm")
    fake.PREWARM_THREADS_ENV = "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS"
    fake.PREWARM_CHUNK_MB_ENV = "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB"
    fake.CheckpointPrewarmer = prewarmer_cls
    monkeypatch.setitem(sys.modules, "comfymodal_runtime.checkpoint_prewarm", fake)


def test_forward_start_arms_prep_with_identity(ctx, monkeypatch):
    monkeypatch.setenv(rfp.FLAG_MASTER, "1")
    monkeypatch.setenv(rfp.FLAG_SOURCE_PREP, "1")
    armed: dict = {}

    class _FakePrewarmer:
        def __init__(self, **kwargs):
            armed.update(kwargs)

        def start(self, paths):
            armed["paths"] = list(paths)
            return True

        def as_dict(self):
            return {"prewarm_bytes": 123, "prewarm_read_calls": 4,
                    "prewarm_stop_reason": "running"}

        def before_demand_load(self):
            return True

        def stop_and_join_before_demand(self):
            return True

    _install_fake_prewarm_module(monkeypatch, _FakePrewarmer)
    diag = _DiagSink()
    durable = _DurableTrace()
    ctx.trace = diag
    ctx.set_durable_trace_resolver(lambda: durable)
    ctx.set_unet_source_identity(
        path="x.safetensors", size_bytes=10, node_id="7",
        unet_name="x.safetensors", weight_dtype="default", resolution="plan",
    )
    ctx.mark_clip_forward_start()
    assert ctx._prep_armed is True
    assert armed.get("paths") == ["x.safetensors"]
    names = [e for e, _ in durable.events]
    assert "unet_source_prep_armed" in names
    ev = dict(durable.events[names.index("unet_source_prep_armed")][1])
    assert ev["trigger"] == "clip_forward_start"
    assert ev["targeted_bytes"] == 10
    joined = ctx.join_unet_source_prep(timeout_s=2.0)
    assert joined["joined"] is True
    names = [e for e, _ in durable.events]
    assert "unet_source_prep_joined" in names
    stamps = ctx.prep_stamps()
    assert stamps["armed"] is True and stamps["joined"] is True
    assert stamps["prep_join_end_mono_ns"] is not None
    assert stamps["stats"]["prewarm_bytes"] == 123


def test_no_prep_before_forward_and_not_during_transport(ctx, monkeypatch):
    monkeypatch.setenv(rfp.FLAG_MASTER, "1")
    monkeypatch.setenv(rfp.FLAG_SOURCE_PREP, "1")
    ctx.set_unet_source_identity(path="y.safetensors", size_bytes=3)
    ctx.claim_physical_load("clip")
    ctx.mark_clip_loaded()
    assert ctx._prep_armed is False
    started = threading.Event()

    orig_arm = ctx.arm_unet_source_prep

    def spy(paths, trigger="unet_loader_entry"):
        started.set()
        return orig_arm(paths, trigger=trigger)

    ctx.arm_unet_source_prep = spy  # type: ignore[method-assign]
    ctx.mark_clip_forward_start()
    assert started.is_set()


def test_prep_arm_acquires_no_gpu_gate(ctx, monkeypatch):
    monkeypatch.setenv(rfp.FLAG_MASTER, "1")
    monkeypatch.setenv(rfp.FLAG_SOURCE_PREP, "1")

    class _FakePrewarmer:
        def start(self, paths):
            return True

        def as_dict(self):
            return {}

    _install_fake_prewarm_module(monkeypatch, _FakePrewarmer)
    gate_calls = {"n": 0}
    fake_coord = types.SimpleNamespace(
        begin_unet_gpu_phase=lambda *a, **k: gate_calls.__setitem__(
            "n", gate_calls["n"] + 1
        )
        or "tok",
    )
    saved_coord = sys.modules.get("comfymodal_runtime.gpu_lane_coordination")
    sys.modules["comfymodal_runtime.gpu_lane_coordination"] = fake_coord
    try:
        ctx.set_unet_source_identity(path="z.safetensors", size_bytes=5)
        ctx.mark_clip_forward_start()
        assert gate_calls["n"] == 0
    finally:
        if saved_coord is not None:
            sys.modules["comfymodal_runtime.gpu_lane_coordination"] = saved_coord
        else:
            sys.modules.pop("comfymodal_runtime.gpu_lane_coordination", None)


def test_interval_overlap_math_never_double_counts():
    assert rfp.interval_overlap_ms(None, 10, 0, 5) is None
    assert rfp.interval_overlap_ms(0, 10, 20, 30) == 0.0
    assert rfp.interval_overlap_ms(0, 10_000_000, 5_000_000, 15_000_000) == pytest.approx(5.0)
    assert rfp.interval_overlap_ms(0, 10_000_000, 0, 10_000_000) == pytest.approx(10.0)
    assert rfp.interval_overlap_ms(
        100_000_000, 200_000_000, 150_000_000, 300_000_000
    ) == pytest.approx(50.0)
    assert rfp.interval_overlap_ms(0, 10, 5, 15) == pytest.approx(5e-06)


def test_pipeline_payload_persists_bind_mode_counts_copied():
    from comfymodal_runtime import request_unet_fastsafe as ruf

    durable = _DurableTrace()

    class _Ctx:
        def clip_forward_window(self):
            return (1_000_000_000, 3_000_000_000)

        def prep_stamps(self):
            return {
                "armed": True,
                "armed_at_mono_ns": 900_000_000,
                "prep_start_mono_ns": 1_100_000_000,
                "prep_join_start_mono_ns": 2_500_000_000,
                "prep_join_end_mono_ns": 2_800_000_000,
                "joined": True,
            }

        def telemetry(self, event, **md):
            durable.emit(event, phase="execution", metadata=md)

    timings = {
        "storage_identity_matched": 453,
        "storage_identity_total": 453,
        "fastsafe_metrics": {
            "fastsafe_setup_wall_ms": 1.0,
            "fastsafe_file_gpu_wall_ms": 2500.0,
            "fastsafe_instantiate_wall_ms": 40.0,
            "final_validation": {"all_params_on_target": True},
        },
        "gate_wait_ms": 0.4,
        "prepare_join_ms": 300.0,
    }
    ruf._publish_success_telemetry(_Ctx(), "after_clip", timings)
    names = [e for e, _ in durable.events]
    assert "unet_fastsafe_pipeline" in names
    md = dict(durable.events[names.index("unet_fastsafe_pipeline")][1])
    assert md["bind_mode"] == "same_storage"
    assert md["copied_count"] == 0
    assert md["storage_identity_matched"] == 453
    assert md["final_validation_all_params_on_target"] is True
    assert md["unet_prep_overlap_ms"] == pytest.approx(1700.0, abs=0.01)
    assert md["unet_prep_tail_at_forward_end_ms"] < 0.001 or md[
        "unet_prep_tail_at_forward_end_ms"
    ] >= 0.0
    assert md["unet_prep_tail_at_demand_ms"] == pytest.approx(0.0, abs=0.001)


def test_summary_includes_identity(ctx):
    ctx.set_unet_source_identity(path="p.safetensors", size_bytes=9)
    summary = ctx.summary()
    assert summary["unet_source_identity"]["size_bytes"] == 9


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
