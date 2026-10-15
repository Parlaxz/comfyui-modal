"""FAST_UNIT: flag-gated single-iteration Ideogram CUDA profiling hooks.

Pure policy/state-machine coverage, no ComfyUI, Modal, model scans, or CUDA.
``torch`` is stubbed absent so every test runs the dependency-free path.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.fast_unit

from comfymodal_runtime import ideogram_cuda_profile as ideo


FLAG_BACKEND = ideo.FLAG_BACKEND
FLAG_ITERATION = ideo.FLAG_ITERATION
FLAG_BLOCK_RANGES = ideo.FLAG_BLOCK_RANGES
_PROFILE_DIR_VAR = "COMFYMODAL_V2_IDEOGRAM_CUDA_PROFILE_DIR"


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    for _var in (FLAG_BACKEND, FLAG_ITERATION, FLAG_BLOCK_RANGES, _PROFILE_DIR_VAR):
        monkeypatch.delenv(_var, raising=False)
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setitem(sys.modules, "torch.profiler", None)
    monkeypatch.setitem(sys.modules, "torch._C._profiler", None)
    ideo._ACTIVE.set(None)
    yield
    ideo._ACTIVE.set(None)


def _fake_x(batch=2):
    return SimpleNamespace(shape=(batch, 4))


def _arm(monkeypatch, backend="nsys", iteration="3", blocks="0"):
    monkeypatch.setenv(FLAG_BACKEND, backend)
    monkeypatch.setenv(FLAG_ITERATION, iteration)
    monkeypatch.setenv(FLAG_BLOCK_RANGES, blocks)
    return ideo.arm_ideogram_profile(request_id="test-request", patcher=None)


def test_disabled_by_default():
    assert ideo.arm_ideogram_profile(request_id="r") is None


def test_invalid_backend_falls_back_to_off(monkeypatch):
    cap = _arm(monkeypatch, backend="kineto_please")
    assert cap is None


def test_flags_registered_in_config_authority():
    from comfymodal_runtime import config_authority as ca

    for _name in (FLAG_BACKEND, FLAG_ITERATION, FLAG_BLOCK_RANGES):
        assert _name in ca.GOLDEN_CONTROL_FLAGS, _name
    assert ca.resolve({}).get(FLAG_BACKEND) == "off"
    assert ca.resolve({}).get(FLAG_ITERATION) == 3
    assert ca.resolve({}).get(FLAG_BLOCK_RANGES) is False
    assert ca.resolve({FLAG_BACKEND: "nsys"}).get(FLAG_BACKEND) == "nsys"
    assert ca.resolve({FLAG_ITERATION: "7"}).get(FLAG_ITERATION) == 7
    assert ca.resolve({FLAG_BACKEND: "bogus"}).get(FLAG_BACKEND) == "off"


def test_effective_values_recorded(monkeypatch):
    cap = _arm(monkeypatch, backend="torch", iteration="5", blocks="1")
    assert cap is not None
    ideo.notify_sampler_step(4)
    ideo.observe_forward_pre(None, (_fake_x(),), {"cond": object()})
    ideo.observe_forward_post()
    ideo.notify_sampler_step(5)
    artifact = ideo.finalize_ideogram_profile(cap)
    assert artifact["backend_effective"] == "torch"
    assert artifact["iteration_effective"] == 5
    assert artifact["block_ranges_effective"] is True
    assert artifact["torch_profiler_started"] is False
    assert artifact["torch_skip_reason"] == "torch_unavailable"


def test_completed_step_ordering_captures_target_iteration(monkeypatch):
    cap = _arm(monkeypatch, backend="nsys", iteration="3")
    assert cap is not None
    for _step in (0, 1, 2):
        ideo.notify_sampler_step(_step)
    assert ideo.get_active() is cap
    # Target iteration forwards: cond then uncond, explicit markers.
    ideo.observe_forward_pre(None, (_fake_x(),), {"cond": object()})
    assert cap.capturing is True
    ideo.observe_forward_post()
    ideo.observe_forward_pre(None, (_fake_x(),), {"uncond": object()})
    ideo.observe_forward_post()
    ideo.notify_sampler_step(3)
    assert cap.capturing is False
    assert cap.done is True
    artifact = ideo.finalize_ideogram_profile(cap)
    assert artifact["status"] == "captured"
    assert artifact["hook_fired"] is True
    assert artifact["forwards_inside_iteration"] == 2
    assert artifact["conditional_forwards"] == 1
    assert artifact["unconditional_forwards"] == 1
    assert artifact["close_reason"] == "completed_step_callback"
    assert artifact["span_partial"] is True
    assert "IDEOGRAM_ITERATION" in artifact["ranges_emitted"]


def test_shared_keys_stay_unknown_never_guessed(monkeypatch):
    cap = _arm(monkeypatch, backend="nsys", iteration="3")
    ideo.notify_sampler_step(2)
    # Both CFG calls share the identical `context` key: values are never
    # inspected, so both stay UNKNOWN with batch evidence.
    ideo.observe_forward_pre(None, (_fake_x(batch=4),), {"context": object()})
    ideo.observe_forward_post()
    ideo.observe_forward_pre(None, (_fake_x(batch=4),), {"context": object()})
    ideo.observe_forward_post()
    ideo.notify_sampler_step(3)
    artifact = ideo.finalize_ideogram_profile(cap)
    assert artifact["status"] == "captured"
    assert artifact["unknown_forwards"] == 2
    assert artifact["conditional_forwards"] == 0
    assert artifact["unconditional_forwards"] == 0


def test_batched_cfg_single_call(monkeypatch):
    cap = _arm(monkeypatch, backend="nsys", iteration="1")
    ideo.notify_sampler_step(0)
    ideo.observe_forward_pre(
        None, (_fake_x(),), {"cond": object(), "uncond": object()}
    )
    ideo.observe_forward_post()
    ideo.notify_sampler_step(1)
    artifact = ideo.finalize_ideogram_profile(cap)
    assert artifact["batched_forwards"] == 1
    assert artifact["forwards_inside_iteration"] == 1


def test_cond_or_uncond_marker_from_metadata(monkeypatch):
    assert ideo.classify_conditioning(
        (), {"transformer_options": {"cond_or_uncond": [1, 1]}}
    )[0] == "CONDITIONAL"
    assert ideo.classify_conditioning(
        (), {"transformer_options": {"cond_or_uncond": [0, 0]}}
    )[0] == "UNCONDITIONAL"
    assert ideo.classify_conditioning(
        (), {"transformer_options": {"cond_or_uncond": [1, 0]}}
    )[0] == "BATCHED"


def test_skipped_cfg_single_forward_is_not_an_error(monkeypatch):
    cap = _arm(monkeypatch, backend="nsys", iteration="2")
    ideo.notify_sampler_step(1)
    ideo.observe_forward_pre(None, (_fake_x(),), {"cond": object()})
    ideo.observe_forward_post()
    ideo.notify_sampler_step(2)
    artifact = ideo.finalize_ideogram_profile(cap)
    assert artifact["status"] == "captured"
    assert artifact["conditional_forwards"] == 1
    assert artifact["unconditional_forwards"] == 0
    assert "single_forward_note" in artifact


def test_no_callback_no_count_fallback_unresolved(monkeypatch):
    cap = _arm(monkeypatch, backend="nsys", iteration="3")
    # Forwards arrive with no step anchor: refuse the alternating-count
    # fallback and report unresolved honestly.
    ideo.observe_forward_pre(None, (_fake_x(),), {"cond": object()})
    ideo.observe_forward_post()
    artifact = ideo.finalize_ideogram_profile(cap)
    assert artifact["status"] == "unresolved"
    assert artifact["hook_fired"] is False
    assert "refusing_count_based_fallback" in (artifact["unresolved_reason"] or "")


def test_target_zero_without_callbacks(monkeypatch):
    cap = _arm(monkeypatch, backend="nsys", iteration="0")
    ideo.observe_forward_pre(None, (_fake_x(),), {"cond": object()})
    ideo.observe_forward_post()
    artifact = ideo.finalize_ideogram_profile(cap)
    assert artifact["hook_fired"] is True
    assert artifact["anchor_callback"] == -1


def test_callback_wrap_absent_stays_absent_and_no_double_wrap(monkeypatch):
    cap = _arm(monkeypatch, backend="nsys", iteration="1")
    assert ideo.maybe_wrap_sampler_callback({}) == {}
    seen = []

    def _cb(i):
        seen.append(i)
        return "ok"

    wrapped = ideo.maybe_wrap_sampler_callback({"callback": _cb})
    # Real call shape: callback(i, ...) with int index 0.
    assert wrapped["callback"](0) == "ok"
    assert seen == [0]
    assert cap is not None
    assert cap.callback_notifications == 1
    rewrapped = ideo.maybe_wrap_sampler_callback(wrapped)
    assert rewrapped["callback"](1) == "ok"
    assert cap.callback_notifications == 2  # not doubled


def test_callback_wrap_off_path_returns_inputs_unchanged():
    inputs = {"callback": lambda i: i}
    assert ideo.maybe_wrap_sampler_callback(inputs) is inputs


def test_block_ranges_capped_and_bounded(monkeypatch):
    class _FakeBlock:
        def register_forward_pre_hook(self, hook, with_kwargs=True):
            return SimpleNamespace(remove=lambda: None)

        def register_forward_hook(self, hook):
            return SimpleNamespace(remove=lambda: None)

    class _FakeDM:
        def __init__(self, count):
            self.blocks = [_FakeBlock() for _ in range(count)]

    cap = _arm(monkeypatch, backend="nsys", iteration="0", blocks="1")
    assert cap is not None
    assert cap.block_supported is False  # patcher=None: no diffusion model
    ideo._install_block_hooks(cap, _FakeDM(34))
    assert cap.block_supported is True
    assert cap.block_containers == ["blocks"]
    assert len(cap.block_handles) == 2 * 34
    ideo._install_block_hooks(cap, _FakeDM(100))
    # 100 blocks exceed the seam bound: seam reports unsupported rather than
    # flooding with per-op ranges.
    assert cap.block_supported is False
    artifact = ideo.finalize_ideogram_profile(cap)
    assert artifact["block_range_cap"] == ideo.MAX_BLOCK_RANGES


def test_finalize_never_raises_and_is_idempotent(monkeypatch):
    cap = _arm(monkeypatch, backend="nsys", iteration="3")
    first = ideo.finalize_ideogram_profile(cap)
    assert first["status"] == "unresolved"
    second = ideo.finalize_ideogram_profile(cap)
    assert second["status"] == "already_finalized"
    assert ideo.finalize_ideogram_profile(None)["status"] == "disabled"
    assert ideo.get_active() is None
