"""Offline contract tests for the Golden-only RES4LYF GC shim."""

from __future__ import annotations

import gc
import asyncio
import importlib.util
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "comfymodal_runtime" / "golden_serial.py"


def _load_golden():
    spec = importlib.util.spec_from_file_location(
        "golden_res4lyf_gc_suppression_under_test", GOLDEN_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gs = _load_golden()


def _fake_runner(*, module_name="RES4LYF.beta.samplers", module_file=None, gc_binding=None):
    module_file = module_file or os.path.join("x", "RES4LYF", "beta", "samplers.py")
    active = types.ModuleType(module_name)
    active.__file__ = module_file
    setattr(active, "gc", gc if gc_binding is None else gc_binding)

    def main(self):
        return "ok"

    main.__module__ = module_name
    sampler_class = type(
        "ClownsharKSampler_Beta",
        (),
        {"__module__": module_name, "FUNCTION": "main", "main": main},
    )
    active.ClownsharKSampler_Beta = sampler_class
    sys.modules[module_name] = active
    runner = SimpleNamespace(
        prompt={"sampler": {"class_type": "ClownsharKSampler_Beta"}},
        _classes=lambda: {"ClownsharKSampler_Beta": sampler_class},
    )
    return runner, active


def _session():
    return SimpleNamespace(recorder=gs.GoldenTelemetryRecorder(), run_identity={})


def test_exact_binding_intercepts_collect_and_delegates_everything_else(monkeypatch):
    runner, active = _fake_runner()
    monkeypatch.setitem(sys.modules, "RES4LYF.beta.samplers", active)
    original_collect = gc.collect
    session = _session()

    with gs.res4lyf_gc_suppression_scope(runner, "sampler", session=session) as proxy:
        assert active.gc is proxy
        assert active.gc.isenabled() == gc.isenabled()
        assert active.gc.garbage is gc.garbage
        assert active.gc.collect() == 0
        assert proxy.intercepted_collect_count == 1
        assert gc.collect is original_collect

    assert active.gc is gc
    record = session.recorder.res4lyf_gc_suppression
    assert record["status"] == "applied"
    assert record["module_name"] == active.__name__
    assert record["expected_target"] == "RES4LYF.beta.samplers"
    assert record["module_path"].replace("\\", "/").endswith(
        "/RES4LYF/beta/samplers.py"
    )
    assert record["intercepted_collect_count"] == 1
    assert record["restoration_state"] == "restored"
    assert record["suppression_wall_ms"] >= 0


def test_binding_restores_after_sampler_exception(monkeypatch):
    runner, active = _fake_runner()
    monkeypatch.setitem(sys.modules, "RES4LYF.beta.samplers", active)
    session = _session()

    with pytest.raises(ValueError, match="sampler failed"):
        with gs.res4lyf_gc_suppression_scope(runner, "sampler", session=session):
            active.gc.collect()
            raise ValueError("sampler failed")

    assert active.gc is gc
    assert session.recorder.res4lyf_gc_suppression["restoration_state"] == "restored"
    assert session.recorder.res4lyf_gc_suppression["intercepted_collect_count"] == 1


def test_restoration_failure_replaces_body_error_and_releases_lock(monkeypatch):
    runner, active = _fake_runner()
    monkeypatch.setitem(sys.modules, active.__name__, active)
    session = _session()
    body_error = ValueError("sampler failed")
    restoration_error = OSError("restore failed")

    def fail_restore(_module, _original_gc):
        raise restoration_error

    monkeypatch.setattr(gs, "_restore_res4lyf_gc_binding", fail_restore)
    with pytest.raises(OSError, match="restore failed") as exc_info:
        with gs.res4lyf_gc_suppression_scope(runner, "sampler", session=session):
            raise body_error

    assert exc_info.value is restoration_error
    assert exc_info.value.__cause__ is body_error
    assert active.gc is not gc
    assert session.recorder.res4lyf_gc_suppression["restoration_state"] == "restore_failed"
    assert gs._GOLDEN_RES4LYF_GC_LOCK.acquire(blocking=False)
    gs._GOLDEN_RES4LYF_GC_LOCK.release()


@pytest.mark.parametrize(
    "kwargs, error",
    [
        ({"module_name": "not.res4lyf.samplers"}, "class_module_mismatch"),
        (
            {"module_name": "/root/comfy/ComfyUI/custom_nodes/other.beta.samplers"},
            "class_module_mismatch",
        ),
        (
            {"module_name": "alias.RES4LYF.beta.samplers"},
            "class_module_mismatch",
        ),
        ({"module_file": os.path.join("x", "RES4LYF", "samplers.py")}, "source_path_mismatch"),
        ({"gc_binding": object()}, "gc_binding_invalid"),
    ],
)
def test_wrong_or_unidentifiable_paths_fail_closed_without_mutation(monkeypatch, kwargs, error):
    runner, active = _fake_runner(**kwargs)
    monkeypatch.setitem(sys.modules, active.__name__, active)
    original = active.gc
    session = _session()

    with pytest.raises(RuntimeError, match=error):
        with gs.res4lyf_gc_suppression_scope(runner, "sampler", session=session):
            pytest.fail("fail-closed resolver must not yield")

    assert active.gc is original
    record = session.recorder.res4lyf_gc_suppression
    assert record["status"] == "fail_closed"
    assert record["restoration_state"] == "not_applied"


@pytest.mark.parametrize(
    "module_name",
    [
        "/root/comfy/ComfyUI/custom_nodes/RES4LYF.beta.samplers",
        r"C:\root\comfy\ComfyUI\custom_nodes\RES4LYF.beta.samplers",
    ],
)
def test_absolute_path_like_loader_module_key_is_resolved_exactly(monkeypatch, module_name):
    runner, active = _fake_runner(module_name=module_name)
    monkeypatch.setitem(sys.modules, module_name, active)
    session = _session()

    with gs.res4lyf_gc_suppression_scope(runner, "sampler", session=session):
        assert active.gc.collect() == 0

    record = session.recorder.res4lyf_gc_suppression
    assert record["status"] == "applied"
    assert record["module_name"] == module_name
    assert record["expected_target"] == "RES4LYF.beta.samplers"
    assert active.gc is gc


def test_registered_class_must_match_module_class_identity(monkeypatch):
    runner, active = _fake_runner()
    monkeypatch.setitem(sys.modules, active.__name__, active)
    active.ClownsharKSampler_Beta = type(
        "ClownsharKSampler_Beta",
        (),
        {"__module__": active.__name__, "FUNCTION": "main"},
    )
    session = _session()

    with pytest.raises(RuntimeError, match="class_binding_mismatch"):
        with gs.res4lyf_gc_suppression_scope(runner, "sampler", session=session):
            pytest.fail("class identity mismatch must not yield")

    assert active.gc is gc
    record = session.recorder.res4lyf_gc_suppression
    assert record["status"] == "fail_closed"
    assert "class_binding_mismatch" in record["fail_closed_reason"]


def test_missing_module_local_gc_binding_fails_closed(monkeypatch):
    runner, active = _fake_runner(gc_binding=None)
    delattr(active, "gc")
    monkeypatch.setitem(sys.modules, active.__name__, active)
    session = _session()

    with pytest.raises(RuntimeError, match="gc_binding_missing"):
        with gs.res4lyf_gc_suppression_scope(runner, "sampler", session=session):
            pytest.fail("missing binding must not yield")

    assert session.recorder.res4lyf_gc_suppression["status"] == "fail_closed"


def test_overlap_fails_closed_and_outer_binding_is_restored(monkeypatch):
    runner, active = _fake_runner()
    monkeypatch.setitem(sys.modules, active.__name__, active)
    outer = _session()
    inner = _session()

    with gs.res4lyf_gc_suppression_scope(runner, "sampler", session=outer):
        held_proxy = active.gc
        with pytest.raises(RuntimeError, match="suppression_overlap"):
            with gs.res4lyf_gc_suppression_scope(runner, "sampler", session=inner):
                pass
        assert active.gc is held_proxy

    assert active.gc is gc
    assert inner.recorder.res4lyf_gc_suppression["status"] == "fail_closed"
    assert outer.recorder.res4lyf_gc_suppression["restoration_state"] == "restored"


def test_feature_flag_skip_is_observable_and_does_not_patch(monkeypatch):
    monkeypatch.delenv(gs.GOLDEN_RES4LYF_GC_SUPPRESSION_ENV, raising=False)
    assert gs.res4lyf_gc_suppression_enabled() is False
    session = _session()
    gs._record_res4lyf_gc_suppression(
        session,
        status="skipped",
        skip_reason="feature_flag_disabled",
        intercepted_collect_count=0,
        suppression_wall_ms=0.0,
        restoration_state="not_applied",
    )
    payload = session.recorder.to_json_dict()
    assert payload["res4lyf_gc_suppression"]["status"] == "skipped"
    assert payload["res4lyf_gc_suppression"]["restoration_state"] == "not_applied"


def test_golden_sampling_wraps_only_the_direct_sampler_closure(monkeypatch):
    runner, active = _fake_runner()
    monkeypatch.setitem(sys.modules, active.__name__, active)
    monkeypatch.setenv(gs.GOLDEN_RES4LYF_GC_SUPPRESSION_ENV, "1")

    class ClosureRunner:
        def __init__(self):
            self.prompt = runner.prompt
            self.cache = {}
            self.executed = []
            self._golden_futures = set()
            self._golden_task_baseline = set()
            self._classes = runner._classes

        def set_sampler_target(self, *_args):
            pass

        def set_sampler_total_observer(self, observer):
            self.observer = observer

        def begin_scope(self, _allowed):
            pass

        def end_scope(self):
            pass

        async def run_closure(self, target_id, *, include_target):
            assert include_target is True
            assert active.gc is not gc
            assert active.gc.collect() == 0
            self.executed.append({
                "node_id": target_id,
                "class_type": "ClownsharKSampler_Beta",
                "stage_class": "sampling",
            })
            self.cache[target_id] = gs._CacheEntry(outputs=[["latent"]])
            return [(target_id, "ClownsharKSampler_Beta", "sampling")]

    actual_runner = ClosureRunner()
    session = SimpleNamespace(
        recorder=gs.GoldenTelemetryRecorder(),
        request=SimpleNamespace(
            request_id="golden-boundary",
            prompt=actual_runner.prompt,
            attention_backend=None,
            deep_trace=False,
        ),
        contract=SimpleNamespace(sampler_class_type="ClownsharKSampler_Beta"),
        node_map=SimpleNamespace(sampler_id="sampler"),
        runner=actual_runner,
        patcher=SimpleNamespace(model_options={"transformer_options": {}}),
        golden_mode="serial",
    )

    assert asyncio.run(gs.golden_sampling(session)) == [["latent"]]
    assert active.gc is gc
    assert session.recorder.res4lyf_gc_suppression["intercepted_collect_count"] == 1
    assert session.recorder.res4lyf_gc_suppression["restoration_state"] == "restored"
