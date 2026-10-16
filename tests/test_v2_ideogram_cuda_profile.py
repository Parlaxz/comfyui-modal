"""FAST_UNIT: flag-gated single-iteration Ideogram CUDA profiling hooks.

Pure policy/state-machine coverage, no ComfyUI, Modal, model scans, or CUDA.
``torch`` is stubbed absent so every test runs the dependency-free path.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
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


class _FakeTrace:
    def __init__(self):
        self.events = []

    def emit(self, name, *, phase="", metadata=None):
        self.events.append({"name": name, "phase": phase, "metadata": dict(metadata or {})})
        return SimpleNamespace(monotonic_ns=0, wall_unix_ns=0)


def test_second_arm_returns_existing_no_double_arm(monkeypatch):
    first = _arm(monkeypatch, backend="nsys", iteration="3")
    assert first is not None
    monkeypatch.setenv(FLAG_BACKEND, "torch")
    second = ideo.arm_ideogram_profile(request_id="other-request", patcher=None)
    assert second is first
    assert ideo.get_active() is first


def test_owned_finalize_emits_event_once(monkeypatch):
    cap = _arm(monkeypatch, backend="nsys", iteration="3")
    trace = _FakeTrace()
    artifact = ideo.finalize_sampler_profile(cap, trace, owned=True)
    assert artifact is not None
    assert artifact["event"] == ideo.EVENT_NAME
    assert len(trace.events) == 1
    assert trace.events[0]["name"] == ideo.EVENT_NAME
    assert trace.events[0]["phase"] == "execution"
    assert trace.events[0]["metadata"]["event"] == ideo.EVENT_NAME
    # Finalize-once: the owner finalizing again reports already_finalized
    # and emits nothing new.
    again = ideo.finalize_sampler_profile(cap, trace, owned=True)
    assert again is not None
    assert again["status"] == "already_finalized"
    assert len(trace.events) == 1
    assert ideo.get_active() is None


def test_unowned_finalize_is_noop_preserves_owner(monkeypatch):
    # Golden-style: an earlier seam armed; the wrapper seam finds the
    # existing capture and must neither finalize nor emit.
    cap = _arm(monkeypatch, backend="nsys", iteration="3")
    trace = _FakeTrace()
    assert ideo.finalize_sampler_profile(cap, trace, owned=False) is None
    assert trace.events == []
    assert ideo.get_active() is cap
    # The owner can still finalize afterwards.
    artifact = ideo.finalize_ideogram_profile(cap)
    assert artifact["status"] == "unresolved"
    assert ideo.get_active() is None


def test_flags_off_arm_none_and_no_emit():
    assert ideo.arm_ideogram_profile(request_id="r") is None
    trace = _FakeTrace()
    assert ideo.finalize_sampler_profile(None, trace, owned=True) is None
    assert ideo.finalize_sampler_profile(None, trace, owned=False) is None
    assert trace.events == []


def test_notify_step_index_extraction(monkeypatch):
    cap = _arm(monkeypatch, backend="nsys", iteration="3")
    assert cap is not None
    ideo.notify_step_index(2)  # raw sampler-callback args[0]
    assert cap.callback_notifications == 1
    assert cap.last_callback == 2
    for _bad in (True, "2", None, 2.0):
        ideo.notify_step_index(_bad)
    assert cap.callback_notifications == 1 + 4
    assert cap.unknown_callbacks == 4
    assert cap.last_callback == 2


def test_export_base_explicit_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("COMFYMODAL_V2_IDEOGRAM_CUDA_PROFILE_DIR", str(tmp_path))
    monkeypatch.setattr(ideo, "PROFILE_MOUNT_PATH", str(tmp_path / "nope"))
    where, kind = ideo._resolve_export_base()
    assert where == str(tmp_path)
    assert kind == "explicit_env"


def test_export_base_prefers_mounted_volumes_then_temp(monkeypatch, tmp_path):
    monkeypatch.delenv("COMFYMODAL_V2_IDEOGRAM_CUDA_PROFILE_DIR", raising=False)
    _profile = tmp_path / "profiles"
    _state = tmp_path / "state"
    _profile.mkdir()
    _state.mkdir()
    monkeypatch.setattr(ideo, "PROFILE_MOUNT_PATH", str(_profile))
    monkeypatch.setattr(ideo, "RUNTIME_STATE_MOUNT_PATH", str(_state))
    where, kind = ideo._resolve_export_base()
    assert kind == "profile"
    assert where == str(_profile / ideo.EXPORT_SUBDIR)
    # Profile mount absent (full-trace off): always-mounted state volume.
    monkeypatch.setattr(ideo, "PROFILE_MOUNT_PATH", str(tmp_path / "absent"))
    where, kind = ideo._resolve_export_base()
    assert kind == "runtime_state"
    assert where == str(_state / ideo.EXPORT_SUBDIR)
    # Neither mounted (local dev): unreachable tempdir last resort.
    monkeypatch.setattr(ideo, "RUNTIME_STATE_MOUNT_PATH", str(tmp_path / "absent"))
    where, kind = ideo._resolve_export_base()
    assert kind == "local_temp"
    assert where.endswith(ideo.EXPORT_SUBDIR)


def test_commit_helper_skips_without_volume(monkeypatch):
    assert ideo._commit_export_volume(None, "profile") == "skipped_no_volume_handle"
    assert ideo._commit_export_volume("/tmp/x.json", "local_temp") == "skipped_no_volume_handle"
    assert ideo._commit_export_volume("/tmp/x.json", "bogus") == "skipped_no_volume_handle"

class _FakeRegistry:
    def __init__(self, winner="eager", details=None):
        self.winner = winner
        self.details = details or {}
        self.calls = []

    def list_backends(self):
        return {
            "cuda": {"available": True, "disabled": False,
                     "unavailable_reason": None,
                     "capabilities": ["fp16_linear"]},
            "triton": {"available": False, "disabled": False,
                       "unavailable_reason": "No module named \u0027triton\u0027",
                       "capabilities": []},
            "eager": {"available": True, "disabled": False,
                      "unavailable_reason": None,
                      "capabilities": ["int8_linear"]},
        }

    def validate_backend_for_call(self, backend, func, kwargs):
        self.calls.append((backend, func))
        return SimpleNamespace(success=(backend == "eager"),
                               failed_param=None if backend == "eager" else "__function__",
                               failure_reason=None if backend == "eager" else "not implemented")

    def get_capable_backend(self, func, kwargs=None):
        self.calls.append(("select", func))
        return self.winner


def _install_fake_kitchen(monkeypatch, registry):
    import types
    ck = types.ModuleType("comfy_kitchen")
    ck.registry = registry
    backends = types.ModuleType("comfy_kitchen.backends")
    cuda = types.ModuleType("comfy_kitchen.backends.cuda")
    cuda._EXT_AVAILABLE = True
    cuda._EXT_ERROR = None
    cuda._C = SimpleNamespace(HAS_CUBLASLT=False)
    monkeypatch.setitem(sys.modules, "comfy_kitchen", ck)
    monkeypatch.setitem(sys.modules, "comfy_kitchen.backends", backends)
    monkeypatch.setitem(sys.modules, "comfy_kitchen.backends.cuda", cuda)
    return ck


def test_backend_proof_reports_once_and_winner(monkeypatch, capsys):
    ideo._proof_emitted = False
    reg = _FakeRegistry(winner="eager")
    _install_fake_kitchen(monkeypatch, reg)
    import types as _types
    _torch = _types.ModuleType("torch")
    _torch.bfloat16 = "bf16"
    _torch.int8 = "i8"
    _torch.float32 = "f32"
    _torch.device = lambda *a: "cuda"
    _torch.zeros = lambda *a, **k: ("zeros", a, k)
    _torch.ones = lambda *a, **k: ("ones", a, k)
    _cuda = _types.ModuleType("torch.cuda")
    _cuda.is_available = lambda: True
    _cuda.current_device = lambda: 0
    _torch.cuda = _cuda
    monkeypatch.setitem(sys.modules, "torch", _torch)
    proof = ideo.emit_kitchen_backend_proof()
    assert proof["synth_dispatched"] == "eager"
    assert proof["has_cublaslt"] is False
    assert proof["cuda"]["int8_linear"] is False
    assert proof["eager"]["int8_linear"] is True
    out = capsys.readouterr().out
    assert ideo.PROOF_TAG in out
    assert "dispatch_winner=int8_linear->eager" in out
    # Once per process: second call is silent and empty.
    assert ideo.emit_kitchen_backend_proof() == {}
    assert capsys.readouterr().out == ""
    ideo._proof_emitted = False


def test_backend_proof_survives_missing_kitchen(monkeypatch, capsys):
    ideo._proof_emitted = False
    monkeypatch.delitem(sys.modules, "comfy_kitchen", raising=False)
    monkeypatch.setitem(sys.modules, "comfy_kitchen", None)
    proof = ideo.emit_kitchen_backend_proof()
    assert proof["kitchen_import"] is False
    assert proof["cuda_visible"] is False
    ideo._proof_emitted = False


def test_selection_counter_counts_int8_only(monkeypatch):
    ideo._selection_counts.clear()
    ideo._selection_wrap_installed = False
    reg = _FakeRegistry(winner="cuda")
    _install_fake_kitchen(monkeypatch, reg)
    assert ideo.install_int8_selection_counter() is True
    assert ideo.install_int8_selection_counter() is True  # idempotent
    from comfy_kitchen import registry as live_reg
    assert live_reg.get_capable_backend("int8_linear", {}) == "cuda"
    assert live_reg.get_capable_backend("int8_linear", {}) == "cuda"
    assert live_reg.get_capable_backend("fp16_linear", {}) == "cuda"
    totals = ideo.int8_selection_totals()
    assert totals == {"cuda": 2, "total": 2}
    ideo._selection_counts.clear()
    ideo._selection_wrap_installed = False

# NOTE (Part A4): GPU-restore repair tests moved to tests/test_gpu_restore.py
# (canonical implementation: comfymodal_runtime/gpu_restore.py; this module
# keeps a thin delegating wrapper for compat).  This file keeps profiling,
# proof, and selection-counter coverage only.


def test_sampler_proof_then_counter_before_actual_sample():
    root = Path(__file__).resolve().parents[1]
    source = (root / "comfymodal_runtime" / "runtime_executor.py").read_text(encoding="utf-8")
    arm = source.index("arm_ideogram_profile(")
    proof = source.index("emit_kitchen_backend_proof()")
    counter = source.index("install_int8_selection_counter()")
    invoke = source.index("return executor(*args, **kwargs)", arm)
    assert arm < proof < counter < invoke
