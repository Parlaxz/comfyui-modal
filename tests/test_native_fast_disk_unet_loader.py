"""Focused tests for the V2 native fast-disk UNET loader.

``COMFYMODAL_V2_NATIVE_FAST_DISK_UNET`` (opt-in, default OFF):

  - flag off -> byte-for-byte legacy behavior: the nn.Module.to wrapper
    calls the original, the per-instance load_model_weights wrapper calls
    the original with its ORIGINAL assign value, no deferral windows are
    opened, and no fast-disk helper/event is ever touched (no state-dict
    or model traversal).
  - eligible flow: native model construction -> native plain ModelPatcher
    -> original load_model_weights(assign=True) [bind] -> exactly ONE REAL
    original model.to(target) -> continue native path.
  - every major guard family fails closed: target not CUDA, not HIGH_VRAM,
    dynamic/non-plain patcher, load/offload/target device mismatch (all
    three must be equal AND CUDA), quant_config / custom_operations /
    fp8 optimization / force_channels_last present, torch
    swap-module-params future enabled, model already CUDA-resident,
    unrecorded patcher, non-plain sd tensors, sd tensors not on CPU,
    non-uniform sd dtype, sd dtype != model parameter dtype, no
    prefix-matching sd tensors, native assign != False.
  - a failed bind guard replays the deferred real model.to(target) BEFORE
    invoking the original load_model_weights with its ORIGINAL assign
    value (legacy ordering preserved).
  - exceptions are preserved and the deferral record is cleaned up on
    every path; no later ``to`` can be suppressed.
  - literal ModelPatcher constructor timing excludes the delayed
    ensure_sampling_timing_wrapper / register_unet_forward_probe helpers.
  - proof/accounting fields (param count, parameter bytes, dtype/device
    distribution, CPU param/buffer counts, exact patcher class/dynamic
    status) are emitted and remain valid after record cleanup.

No CUDA or real ComfyUI is required: the real ``torch.device`` objects are
used only as descriptors and every original ``to``/``load_model_weights``
call is a fake, so the tests run on CPU-only machines.
"""

from __future__ import annotations

import contextlib
import io
import sys
import time
import types
import unittest
from types import SimpleNamespace
from unittest import mock
from typing import Any

import torch

import comfymodal_runtime.model_preload as mp
from comfymodal_runtime.trace import RuntimeTrace

_CLEAN_EVIDENCE: dict[str, Any] = {
    "quant_config_present": False,
    "custom_operations_present": False,
    "fp8_optimization": False,
    "force_channels_last": False,
}

_CUDA = torch.device("cuda")


# ── Fakes ────────────────────────────────────────────────────────────────


class _PatcherMeta(type):
    """Metaclass that lets a fake class report an arbitrary ``__name__``
    (``type.__new__`` would otherwise force the real class name)."""

    def __new__(mcs, name, bases, ns):
        return super().__new__(mcs, ns.get("__type_name__", name), bases, ns)


class _PlainPatcher(metaclass=_PatcherMeta):
    """Fake that reports itself as ``comfy.model_patcher.ModelPatcher``."""

    __type_name__ = "ModelPatcher"
    __module__ = "comfy.model_patcher"

    def __init__(self, model, load_device, offload_device, dynamic=False):
        self.model = model
        self.load_device = load_device
        self.offload_device = offload_device
        self._dynamic = dynamic

    def is_dynamic(self):
        return self._dynamic


class _DynamicPatcher(_PlainPatcher):
    """Fake reporting ModelPatcherDynamic (is_dynamic True)."""

    __type_name__ = "ModelPatcherDynamic"
    __module__ = "comfy.model_patcher"

    def is_dynamic(self):
        return True


class _ForeignPatcher(_PlainPatcher):
    """Subclass in a foreign module (not comfy.model_patcher)."""

    __type_name__ = "ModelPatcher"
    __module__ = "somewhere.else"


def _make_lane(request_id: str = "fd-unet"):
    trace = RuntimeTrace(request_id=request_id, process="remote")
    lane = mp.ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)
    return trace, lane


def _make_model(dtype=torch.float32) -> torch.nn.Module:
    model = torch.nn.Module()
    model.diffusion_model = torch.nn.Linear(4, 4, dtype=dtype)
    model.load_model_weights = lambda *a, **k: "loaded"
    return model


def _make_sd(*, dtype=torch.float32, count: int = 2) -> dict[str, torch.Tensor]:
    sd = {
        "diffusion_model.weight": torch.zeros(4, 4, dtype=dtype),
    }
    if count > 1:
        sd["diffusion_model.bias"] = torch.zeros(4, dtype=dtype)
    return sd


def _open_record(model, lane):
    mc = SimpleNamespace(quant_config=None, custom_operations=None, optimizations={})
    with mock.patch.object(mp, "_fast_disk_model_config_evidence", return_value=dict(_CLEAN_EVIDENCE)):
        return mp._fast_disk_new_record(model, mc, lane)


def _record_plain_patcher(
    model,
    lane,
    *,
    load=None,
    offload=None,
    patcher_cls=_PlainPatcher,
    dynamic: bool = False,
    record_patcher: bool = True,
):
    record = _open_record(model, lane)
    if record_patcher:
        patcher = patcher_cls(
            model, load if load is not None else _CUDA,
            offload if offload is not None else _CUDA, dynamic=dynamic,
        )
        mp._fast_disk_record_patcher(patcher)
        return record, patcher
    return record, None


def _eligible_setup(model, lane, calls):
    """Open an eligible window and defer the to(); returns (record, fake_to, fake_load)."""
    record, _ = _record_plain_patcher(model, lane)

    def fake_to(m, *a, **k):
        calls.append("to")
        return m

    def fake_load(sd, unet_prefix="", assign=False):
        calls.append(("load", assign))
        return "loaded"

    with mock.patch.object(mp, "_fast_disk_high_vram", return_value=True):
        decision = mp._fast_disk_maybe_defer_to(model, (_CUDA,), {}, lane, fake_to)
    assert decision == "deferred", f"expected deferral, got {decision!r}"
    return record, fake_to, fake_load


def _skip_reason(trace, expected: str) -> str:
    for event in trace.events:
        if event.name == mp._EVENT_FAST_DISK_SKIP:
            reason = str(event.metadata.get("reason", ""))
            if expected in reason:
                return reason
    raise AssertionError(f"no unet_fast_disk_skip with reason {expected!r} in {[e.name for e in trace.events]}")


class _Patches:
    def __init__(self, patches):
        self._patches = patches

    def __enter__(self):
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()


@contextlib.contextmanager
def _fake_comfy_model_management(fake_mm):
    _saved_mm = sys.modules.get("comfy.model_management")
    _saved_comfy = sys.modules.get("comfy")
    sys.modules["comfy"] = _saved_comfy if _saved_comfy is not None else types.ModuleType("comfy")
    sys.modules["comfy.model_management"] = fake_mm
    try:
        yield
    finally:
        if _saved_mm is None:
            sys.modules.pop("comfy.model_management", None)
        else:
            sys.modules["comfy.model_management"] = _saved_mm
        if _saved_comfy is None:
            sys.modules.pop("comfy", None)
        else:
            sys.modules["comfy"] = _saved_comfy


# ── Flag off: exact legacy fallback ──────────────────────────────────────


class TestFastDiskFlagOff(unittest.TestCase):
    def setUp(self):
        self._saved_flag = mp._NATIVE_FAST_DISK_UNET
        mp._NATIVE_FAST_DISK_UNET = False

    def tearDown(self):
        mp._NATIVE_FAST_DISK_UNET = self._saved_flag
        with mp._FAST_DISK_UNET_LOCK:
            mp._FAST_DISK_UNET_DEFERRALS.clear()

    def test_to_wrapper_legacy_when_flag_off(self):
        trace, lane = _make_lane()
        calls = []

        def fake_orig(self, *args, **kwargs):
            calls.append((args, kwargs))
            return self

        wrapper = mp._make_model_to_wrapper(fake_orig)
        token = mp._ACTIVE_LANE_TRACE.set(lane)
        try:
            result = wrapper(object(), torch.device("cpu"))
        finally:
            mp._ACTIVE_LANE_TRACE.reset(token)

        assert result is not None
        assert len(calls) == 1
        names = [e.name for e in trace.events]
        assert "unet_model_to_start" in names and "unet_model_to_end" in names
        assert not any(name.startswith("unet_fast_disk_") for name in names)
        assert mp._FAST_DISK_UNET_DEFERRALS == {}

    def test_to_wrapper_no_fast_disk_helper_invoked(self):
        """Flag off must not even invoke the deferral helper (no traversal)."""
        model = _make_model()
        trace, lane = _make_lane()
        wrapper = mp._make_model_to_wrapper(lambda self, *a, **k: self)
        token = mp._ACTIVE_LANE_TRACE.set(lane)
        try:
            with mock.patch.object(mp, "_fast_disk_maybe_defer_to", wraps=mp._fast_disk_maybe_defer_to) as spy:
                wrapper(model, torch.device("cpu"))
                spy.assert_not_called()
        finally:
            mp._ACTIVE_LANE_TRACE.reset(token)

    def test_load_weights_wrapper_legacy_when_flag_off(self):
        model = _make_model()
        trace, lane = _make_lane()
        load_calls = []
        model.load_model_weights = (
            lambda sd, up="", assign=False: load_calls.append(assign) or "ok"
        )
        mp._instrument_unet_model_weights(model, lane)
        token = mp._ACTIVE_LANE_TRACE.set(lane)
        try:
            model.load_model_weights(_make_sd(), "", assign=False)
        finally:
            mp._ACTIVE_LANE_TRACE.reset(token)

        assert load_calls == [False], load_calls
        names = [e.name for e in trace.events]
        assert not any(name.startswith("unet_fast_disk_") for name in names)
        assert mp._FAST_DISK_UNET_DEFERRALS == {}

    def test_get_model_no_window_when_flag_off(self):
        model = _make_model()
        trace, lane = _make_lane()
        config = SimpleNamespace(get_model=lambda *a, **k: model)
        mp._instrument_unet_model_config(config, lane)
        token = mp._ACTIVE_LANE_TRACE.set(lane)
        try:
            with mock.patch.object(mp, "_fast_disk_open_window", wraps=mp._fast_disk_open_window) as spy:
                result = config.get_model("sd")
                spy.assert_not_called()
        finally:
            mp._ACTIVE_LANE_TRACE.reset(token)
        assert result is model
        assert mp._FAST_DISK_UNET_DEFERRALS == {}


# ── Eligible fast path ───────────────────────────────────────────────────


class TestEligibleFastPath(unittest.TestCase):
    def setUp(self):
        self._saved_flag = mp._NATIVE_FAST_DISK_UNET
        mp._NATIVE_FAST_DISK_UNET = True

    def tearDown(self):
        mp._NATIVE_FAST_DISK_UNET = self._saved_flag
        with mp._FAST_DISK_UNET_LOCK:
            mp._FAST_DISK_UNET_DEFERRALS.clear()

    def test_eligible_bind_then_one_real_to(self):
        model = _make_model()
        trace, lane = _make_lane()
        calls = []
        record, fake_to, fake_load = _eligible_setup(model, lane, calls)

        result = mp._fast_disk_handle_bind(model, fake_load, (_make_sd(), ""), {"assign": False}, lane)

        assert result == "loaded"
        # Fast ordering: bind(assign=True) FIRST, then exactly one real to.
        assert calls == [("load", True), "to"], calls
        assert mp._fast_disk_record_for(model) is None, "record must be dropped"

        names = [e.name for e in trace.events]
        for expected in (
            mp._EVENT_FAST_DISK_DEFER,
            mp._EVENT_FAST_DISK_BIND_START,
            mp._EVENT_FAST_DISK_BIND_END,
            mp._EVENT_FAST_DISK_TO_START,
            mp._EVENT_FAST_DISK_TO_END,
            mp._EVENT_FAST_DISK_COMPLETE,
        ):
            assert expected in names, f"missing {expected} in {names}"

    def test_complete_event_accounting_fields(self):
        model = _make_model()
        trace, lane = _make_lane()
        calls = []
        record, fake_to, fake_load = _eligible_setup(model, lane, calls)
        mp._fast_disk_handle_bind(model, fake_load, (_make_sd(), ""), {"assign": False}, lane)

        complete = [e for e in trace.events if e.name == mp._EVENT_FAST_DISK_COMPLETE]
        assert len(complete) == 1
        meta = complete[0].metadata
        assert meta["decision"] == "complete"
        assert meta["param_count"] == 2
        assert meta["parameter_bytes"] == 80  # 16*4 + 4*4 float32
        assert meta["dtype_distribution"] == {"torch.float32": 2}
        assert meta["device_distribution"] == {"cpu": 2}
        assert meta["cpu_param_count"] == 2
        assert meta["cpu_buffer_count"] == 0
        assert meta["patcher_class"] == "comfy.model_patcher.ModelPatcher"
        assert meta["patcher_dynamic"] is False
        assert meta["native_assign"] is False
        assert meta["bind_assign"] is True
        assert isinstance(meta["to_wall_ms"], float) and meta["to_wall_ms"] >= 0.0
        # Synchronized/device measurement is labelled clearly and present
        # whenever CUDA events are supported (otherwise truthfully None).
        assert meta["to_device_ms_label"] in ("synchronized_device", "unavailable")
        if meta["to_device_ms_label"] == "unavailable":
            assert meta["to_device_ms"] is None

    def test_proof_line_fields_valid_after_record_cleanup(self):
        """The concise [v2.native_fast_disk_unet] line carries every requested
        field and remains valid after the deferral record has been dropped."""
        model = _make_model()
        trace, lane = _make_lane()
        calls = []
        record, fake_to, fake_load = _eligible_setup(model, lane, calls)
        mp._fast_disk_handle_bind(model, fake_load, (_make_sd(), ""), {"assign": False}, lane)
        assert mp._fast_disk_record_for(model) is None

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mp._fast_disk_emit_event(
                record, lane, decision="complete", reason="ok",
                stage="load_model_weights", model=model,
            )
        line = buf.getvalue()
        assert line.startswith("[v2.native_fast_disk_unet]")
        assert "decision=complete" in line
        assert "patcher_class=comfy.model_patcher.ModelPatcher" in line
        assert "patcher_dynamic=0" in line
        assert "param_count=2" in line
        assert "parameter_bytes=80" in line
        assert "dtype_distribution={'torch.float32': 2}" in line
        assert "device_distribution={'cpu': 2}" in line
        assert "cpu_params=2" in line
        assert "cpu_buffers=0" in line
        assert "bind_ms=" in line
        assert "to_wall_ms=" in line
        assert "to_device_ms=" in line
        assert "to_device_ms_label=" in line

    def test_to_wrapper_defers_and_returns_self(self):
        model = _make_model()
        trace, lane = _make_lane()
        calls = []
        _record_plain_patcher(model, lane)

        def fake_to(self, *a, **k):
            calls.append("to")
            return self

        wrapper = mp._make_model_to_wrapper(fake_to)
        token = mp._ACTIVE_LANE_TRACE.set(lane)
        try:
            with mock.patch.object(mp, "_fast_disk_high_vram", return_value=True):
                result = wrapper(model, _CUDA)
        finally:
            mp._ACTIVE_LANE_TRACE.reset(token)

        assert result is model
        assert calls == [], "deferred to() must not call the original"
        assert mp._fast_disk_record_for(model)["status"] == "deferred"
        names = [e.name for e in trace.events]
        assert mp._EVENT_FAST_DISK_DEFER in names
        assert "unet_model_to_start" not in names  # no legacy span for the deferred to

    def test_load_weights_wrapper_fast_path_integration(self):
        model = _make_model()
        trace, lane = _make_lane()
        calls = []
        model.load_model_weights = (
            lambda sd, up="", assign=False: calls.append(("load", assign)) or "ok"
        )
        _record_plain_patcher(model, lane)

        def fake_to(m, *a, **k):
            calls.append("to")
            return m

        with mock.patch.object(mp, "_fast_disk_high_vram", return_value=True):
            assert mp._fast_disk_maybe_defer_to(model, (_CUDA,), {}, lane, fake_to) == "deferred"

        mp._instrument_unet_model_weights(model, lane)
        token = mp._ACTIVE_LANE_TRACE.set(lane)
        try:
            result = model.load_model_weights(_make_sd(), "", assign=False)
        finally:
            mp._ACTIVE_LANE_TRACE.reset(token)

        assert result == "ok"
        assert calls == [("load", True), "to"], calls
        assert mp._fast_disk_record_for(model) is None
        names = [e.name for e in trace.events]
        assert "unet_load_model_weights_start" in names
        assert "unet_load_model_weights_end" in names
        assert mp._EVENT_FAST_DISK_COMPLETE in names

    def test_after_complete_later_to_runs_legacy(self):
        """No second to() can ever be suppressed after the fast path."""
        model = _make_model()
        trace, lane = _make_lane()
        calls = []
        record, fake_to, fake_load = _eligible_setup(model, lane, calls)
        mp._fast_disk_handle_bind(model, fake_load, (_make_sd(), ""), {"assign": False}, lane)
        assert mp._fast_disk_record_for(model) is None

        wrapper = mp._make_model_to_wrapper(fake_to)
        token = mp._ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(model, _CUDA)
        finally:
            mp._ACTIVE_LANE_TRACE.reset(token)
        assert calls == [("load", True), "to", "to"], (
            "later to() must run the real original again"
        )

    def test_second_to_before_bind_safety_net(self):
        """A second to() while deferred (not the native flow) replays the
        deferred real to(), closes the window, and lets the current to() run
        through the legacy path."""
        model = _make_model()
        trace, lane = _make_lane()
        calls = []
        record, fake_to, fake_load = _eligible_setup(model, lane, calls)

        with mock.patch.object(mp, "_fast_disk_high_vram", return_value=True):
            decision = mp._fast_disk_maybe_defer_to(model, (_CUDA,), {}, lane, fake_to)

        assert decision == "skip"
        assert "to" in calls, "the deferred to() must have been replayed"
        assert mp._fast_disk_record_for(model) is None
        _skip_reason(trace, "second_to_before_bind")

    def test_get_model_opens_window_when_eligible(self):
        model = _make_model()
        trace, lane = _make_lane()
        config = SimpleNamespace(get_model=lambda *a, **k: model)
        with mock.patch.object(mp, "_fast_disk_model_config_evidence", return_value=dict(_CLEAN_EVIDENCE)):
            mp._instrument_unet_model_config(config, lane)
        token = mp._ACTIVE_LANE_TRACE.set(lane)
        try:
            config.get_model("sd")
        finally:
            mp._ACTIVE_LANE_TRACE.reset(token)

        record = mp._fast_disk_record_for(model)
        assert record is not None
        assert record["status"] == "constructed"
        assert isinstance(record["timings"]["get_model_wall_ms"], float)


# ── to-stage guard rejections (fail closed, no deferral) ────────────────


class TestToGuardRejection(unittest.TestCase):
    def setUp(self):
        self._saved_flag = mp._NATIVE_FAST_DISK_UNET
        mp._NATIVE_FAST_DISK_UNET = True

    def tearDown(self):
        mp._NATIVE_FAST_DISK_UNET = self._saved_flag
        with mp._FAST_DISK_UNET_LOCK:
            mp._FAST_DISK_UNET_DEFERRALS.clear()

    def _attempt(self, *, patcher_cls=_PlainPatcher, dynamic=False, load=None, offload=None,
                 target=None, high_vram=True, record_patcher=True, mutate=None, extra_patches=()):
        model = _make_model()
        trace, lane = _make_lane()
        record, patcher = _record_plain_patcher(
            model, lane, load=load if load is not None else _CUDA,
            offload=offload if offload is not None else _CUDA,
            patcher_cls=patcher_cls, dynamic=dynamic, record_patcher=record_patcher,
        )
        if mutate:
            mutate(record, patcher)
        calls = []

        def fake_to(m, *a, **k):
            calls.append("to")
            return m

        with _Patches([mock.patch.object(mp, "_fast_disk_high_vram", return_value=high_vram), *extra_patches]):
            decision = mp._fast_disk_maybe_defer_to(
                model, (target if target is not None else _CUDA,), {}, lane, fake_to,
            )
        return decision, calls, model, trace

    def test_target_not_cuda(self):
        decision, calls, model, trace = self._attempt(target=torch.device("cpu"))
        assert decision == "skip"
        assert calls == []
        assert mp._fast_disk_record_for(model) is None
        _skip_reason(trace, "target_not_cuda")

    def test_not_high_vram(self):
        decision, calls, model, trace = self._attempt(high_vram=False)
        assert decision == "skip"
        assert calls == []
        assert mp._fast_disk_record_for(model) is None
        _skip_reason(trace, "not_high_vram")

    def test_dynamic_patcher(self):
        decision, calls, model, trace = self._attempt(dynamic=True)
        assert decision == "skip"
        _skip_reason(trace, "dynamic_patcher")

    def test_dynamic_patcher_class_name(self):
        decision, calls, model, trace = self._attempt(patcher_cls=_DynamicPatcher)
        assert decision == "skip"
        _skip_reason(trace, "dynamic_patcher")

    def test_non_plain_patcher_subclass(self):
        decision, calls, model, trace = self._attempt(patcher_cls=_ForeignPatcher)
        assert decision == "skip"
        _skip_reason(trace, "patcher_not_plain_model_patcher")

    def test_load_offload_mismatch(self):
        """Exact device guard: load_device != offload_device fails closed."""
        decision, calls, model, trace = self._attempt(offload=torch.device("cpu"))
        assert decision == "skip"
        assert calls == []
        assert mp._fast_disk_record_for(model) is None
        _skip_reason(trace, "deferred_target_mismatch")

    def test_target_mismatch_with_load_offload(self):
        """Exact device guard: target != load/offload fails closed."""
        decision, calls, model, trace = self._attempt(target=torch.device("cuda:1"))
        assert decision == "skip"
        assert calls == []
        assert mp._fast_disk_record_for(model) is None
        _skip_reason(trace, "deferred_target_mismatch")

    def test_quant_config_present(self):
        decision, calls, model, trace = self._attempt(
            mutate=lambda r, p: r["model_config_evidence"].update(quant_config_present=True)
        )
        assert decision == "skip"
        _skip_reason(trace, "quant_config_present")

    def test_custom_operations_present(self):
        decision, calls, model, trace = self._attempt(
            mutate=lambda r, p: r["model_config_evidence"].update(custom_operations_present=True)
        )
        assert decision == "skip"
        _skip_reason(trace, "custom_operations_present")

    def test_fp8_optimization(self):
        decision, calls, model, trace = self._attempt(
            mutate=lambda r, p: r["model_config_evidence"].update(fp8_optimization=True)
        )
        assert decision == "skip"
        _skip_reason(trace, "fp8_optimization")

    def test_force_channels_last(self):
        decision, calls, model, trace = self._attempt(
            mutate=lambda r, p: r["model_config_evidence"].update(force_channels_last=True)
        )
        assert decision == "skip"
        _skip_reason(trace, "force_channels_last")

    def test_torch_swap_module_params_future(self):
        decision, calls, model, trace = self._attempt(
            extra_patches=[mock.patch.object(mp, "_fast_disk_torch_future_enabled", return_value=True)]
        )
        assert decision == "skip"
        _skip_reason(trace, "torch_swap_module_params_future")

    def test_model_not_cpu_resident(self):
        decision, calls, model, trace = self._attempt(
            extra_patches=[mock.patch.object(mp, "_fast_disk_model_is_cpu_resident", return_value=False)]
        )
        assert decision == "skip"
        _skip_reason(trace, "model_not_cpu_resident")

    def test_patcher_unrecorded(self):
        decision, calls, model, trace = self._attempt(record_patcher=False)
        assert decision == "skip"
        _skip_reason(trace, "patcher_unrecorded")


# ── bind-stage guard rejections (legacy ordering replay) ────────────────


class TestBindGuardRejection(unittest.TestCase):
    """Every bind-stage rejection replays the deferred real to() BEFORE the
    original load_model_weights with its ORIGINAL assign value."""

    def setUp(self):
        self._saved_flag = mp._NATIVE_FAST_DISK_UNET
        mp._NATIVE_FAST_DISK_UNET = True

    def tearDown(self):
        mp._NATIVE_FAST_DISK_UNET = self._saved_flag
        with mp._FAST_DISK_UNET_LOCK:
            mp._FAST_DISK_UNET_DEFERRALS.clear()

    def _run(self, sd, *, args=None, kwargs=None):
        calls = []
        model = _make_model()
        trace, lane = _make_lane()
        record, fake_to, fake_load = _eligible_setup(model, lane, calls)
        a = args if args is not None else (sd, "")
        k = dict(kwargs if kwargs is not None else {"assign": False})
        result = mp._fast_disk_handle_bind(model, fake_load, a, k, lane)
        return calls, result, model, trace

    def _assert_legacy_order(self, calls, result, model, trace, reason):
        assert result == "loaded"
        assert calls == ["to", ("load", False)], (
            f"legacy order must be [real to, original load(assign=False)], got {calls}"
        )
        assert mp._fast_disk_record_for(model) is None
        _skip_reason(trace, reason)

    def test_sd_not_mapping(self):
        calls, result, model, trace = self._run([1, 2, 3])
        self._assert_legacy_order(calls, result, model, trace, "sd_not_mapping")

    def test_non_plain_tensor_sd(self):
        sd = {"a": torch.nn.Parameter(torch.zeros(2, 2))}
        calls, result, model, trace = self._run(sd)
        self._assert_legacy_order(calls, result, model, trace, "non_plain_tensor_sd")

    def test_sd_tensor_not_cpu(self):
        sd = {"a": torch.empty(2, 2, device="meta")}
        calls, result, model, trace = self._run(sd)
        self._assert_legacy_order(calls, result, model, trace, "sd_tensor_not_cpu")

    def test_sd_dtype_not_uniform(self):
        sd = {
            "diffusion_model.weight": torch.zeros(4, 4, dtype=torch.float32),
            "diffusion_model.bias": torch.zeros(4, dtype=torch.float16),
        }
        calls, result, model, trace = self._run(sd)
        self._assert_legacy_order(calls, result, model, trace, "sd_dtype_not_uniform")

    def test_sd_dtype_mismatch_param_dtype(self):
        # Model is float32; a uniform float16 sd must fail closed.
        sd = _make_sd(dtype=torch.float16)
        calls, result, model, trace = self._run(sd)
        self._assert_legacy_order(calls, result, model, trace, "sd_dtype_mismatch")

    def test_no_prefix_sd_tensors(self):
        calls, result, model, trace = self._run(
            _make_sd(), args=(_make_sd(), "nomatch."),
        )
        self._assert_legacy_order(calls, result, model, trace, "no_prefix_sd_tensors")

    def test_native_assign_not_false(self):
        calls, result, model, trace = self._run(
            _make_sd(), kwargs={"assign": True},
        )
        # Original assign value True is preserved on the legacy path.
        assert result == "loaded"
        assert calls == ["to", ("load", True)], calls
        assert mp._fast_disk_record_for(model) is None
        _skip_reason(trace, "native_assign_not_false")

    def test_legacy_replay_then_load_preserves_exception(self):
        calls = []
        model = _make_model()
        trace, lane = _make_lane()
        record, fake_to, _ = _eligible_setup(model, lane, calls)

        def exploding_load(sd, up="", assign=False):
            raise RuntimeError("load boom")

        with self.assertRaises(RuntimeError) as cm:
            mp._fast_disk_handle_bind(model, exploding_load, ([1, 2], ""), {"assign": False}, lane)
        assert str(cm.exception) == "load boom"
        assert calls == ["to"], "deferred to() must replay before the failing load"
        assert mp._fast_disk_record_for(model) is None


# ── Exception cleanup / no later deferral ───────────────────────────────


class TestExceptionCleanup(unittest.TestCase):
    def setUp(self):
        self._saved_flag = mp._NATIVE_FAST_DISK_UNET
        mp._NATIVE_FAST_DISK_UNET = True

    def tearDown(self):
        mp._NATIVE_FAST_DISK_UNET = self._saved_flag
        with mp._FAST_DISK_UNET_LOCK:
            mp._FAST_DISK_UNET_DEFERRALS.clear()

    def test_bind_exception_replays_to_and_cleans_up(self):
        calls = []
        model = _make_model()
        trace, lane = _make_lane()
        record, fake_to, _ = _eligible_setup(model, lane, calls)

        def exploding_bind(sd, up="", assign=False):
            calls.append(("load", assign))
            raise RuntimeError("bind boom")

        with self.assertRaises(RuntimeError) as cm:
            mp._fast_disk_handle_bind(model, exploding_bind, (_make_sd(), ""), {"assign": False}, lane)
        assert str(cm.exception) == "bind boom"
        assert calls == [("load", True), "to"], (
            "bind(assign=True) failed -> replay real to() -> re-raise original"
        )
        assert mp._fast_disk_record_for(model) is None

    def test_replay_exception_cleans_up(self):
        calls = []
        model = _make_model()
        trace, lane = _make_lane()
        record, fake_to, fake_load = _eligible_setup(model, lane, calls)

        def exploding_to(m, *a, **k):
            calls.append("to")
            raise RuntimeError("to boom")

        record["original_to"] = exploding_to
        with self.assertRaises(RuntimeError) as cm:
            mp._fast_disk_handle_bind(model, fake_load, (_make_sd(), ""), {"assign": False}, lane)
        assert str(cm.exception) == "to boom"
        assert "to" in calls
        assert mp._fast_disk_record_for(model) is None


# ── Literal ModelPatcher constructor timing ownership ───────────────────


class TestConstructorTiming(unittest.TestCase):
    def setUp(self):
        self._saved_flag = mp._NATIVE_FAST_DISK_UNET
        mp._NATIVE_FAST_DISK_UNET = False  # timing fix applies with the flag off too

    def tearDown(self):
        mp._NATIVE_FAST_DISK_UNET = self._saved_flag

    def test_ctor_duration_excludes_helper_delay(self):
        import comfymodal_runtime.runtime_executor as rt_exec
        from comfymodal_runtime import unet_forward_probe as ufp

        trace, lane = _make_lane()
        helper_calls = []

        def sleeper(*a, **k):
            # Each helper adds ~0.2 s; the native __init__ adds ~0.1 s.
            # Windows sleep granularity (~15 ms) is far below these margins.
            time.sleep(0.2)
            helper_calls.append(time.monotonic_ns())
            return None

        def fake_orig(self, *a, **k):
            time.sleep(0.1)
            return object()

        patcher = SimpleNamespace(model_options={}, model=None)
        wrapper = mp._make_model_patcher_constructor_wrapper(fake_orig)

        _saved_children = mp._child_durations.get()
        mp._child_durations.set([])
        children_capture: list = []
        try:
            token = mp._ACTIVE_LANE_TRACE.set(lane)
            try:
                with mock.patch.object(rt_exec, "ensure_sampling_timing_wrapper", sleeper), \
                     mock.patch.object(ufp, "register_unet_forward_probe", sleeper):
                    wrapper(patcher)
            finally:
                mp._ACTIVE_LANE_TRACE.reset(token)
            children_capture = list(mp._child_durations.get() or [])
        finally:
            mp._child_durations.set(_saved_children)

        end_events = [e for e in trace.events if e.name == "unet_model_patcher_constructor_end"]
        assert len(end_events) == 1
        duration_ms = end_events[0].metadata["duration_ms"]
        # Literal span = the ~0.1 s native __init__ only (≈109 ms on Windows
        # with timer granularity).  The ~0.4 s of helper delay must be
        # excluded entirely — an included-helper span would exceed 500 ms.
        assert duration_ms < 200, f"ctor duration {duration_ms} includes helper delay"

        end_mono = end_events[0].monotonic_ns
        assert len(helper_calls) == 2, "both helpers must still run"
        assert all(t >= end_mono for t in helper_calls), "helpers must run AFTER the span"

        ctor_child = [c for c in children_capture if isinstance(c, tuple) and c[0] == "model_patcher_constructor"]
        assert ctor_child and ctor_child[0][1] < 200


# ── Standalone helpers / accounting ─────────────────────────────────────


class TestFastDiskHelpers(unittest.TestCase):
    def test_parameter_accounting(self):
        model = _make_model()
        model.register_buffer("buf", torch.zeros(2, dtype=torch.float32))
        acc = mp._fast_disk_parameter_accounting(model)
        assert acc["param_count"] == 2
        assert acc["parameter_bytes"] == 80
        assert acc["dtype_distribution"] == {"torch.float32": 2}
        assert acc["device_distribution"] == {"cpu": 2}
        assert acc["cpu_param_count"] == 2
        assert acc["cpu_buffer_count"] == 1

    def test_parameter_accounting_none(self):
        acc = mp._fast_disk_parameter_accounting(None)
        assert acc["param_count"] == 0 and acc["parameter_bytes"] == 0

    def test_device_key_normalization(self):
        assert mp._fast_disk_device_key(torch.device("cuda")) == ("cuda", 0)
        assert mp._fast_disk_device_key(torch.device("cuda:0")) == ("cuda", 0)
        assert mp._fast_disk_device_key(torch.device("cuda:1")) == ("cuda", 1)
        assert mp._fast_disk_device_key(torch.device("cpu")) == ("cpu", 0)
        assert mp._fast_disk_device_key(None) is None

    def test_resolve_to_target(self):
        assert mp._fast_disk_resolve_to_target((_CUDA,), {}) == _CUDA
        assert mp._fast_disk_resolve_to_target((), {"device": "cuda"}) == _CUDA
        assert mp._fast_disk_resolve_to_target((torch.float32,), {}) is None
        assert mp._fast_disk_resolve_to_target((), {"dtype": torch.float32}) is None
        assert mp._fast_disk_resolve_to_target((), {}) is None

    def test_model_config_evidence_extraction(self):
        fake_mm = types.ModuleType("comfy.model_management")
        fake_mm.force_channels_last = lambda: True
        with _fake_comfy_model_management(fake_mm):
            mc = SimpleNamespace(
                quant_config=object(), custom_operations=object(),
                optimizations={"fp8": True},
            )
            evidence = mp._fast_disk_model_config_evidence(mc)
        assert evidence["quant_config_present"] is True
        assert evidence["custom_operations_present"] is True
        assert evidence["fp8_optimization"] is True
        assert evidence["force_channels_last"] is True

    def test_high_vram_from_live_state(self):
        fake_mm = types.ModuleType("comfy.model_management")
        fake_mm.vram_state = "HIGH"

        class _VRAMState:
            HIGH_VRAM = "HIGH"
            NORMAL_VRAM = "NORMAL"

        fake_mm.VRAMState = _VRAMState
        with _fake_comfy_model_management(fake_mm):
            assert mp._fast_disk_high_vram() is True
            fake_mm.vram_state = "NORMAL"
            assert mp._fast_disk_high_vram() is False

    def test_torch_future_guard_disabled_by_default(self):
        assert mp._fast_disk_torch_future_enabled() is False

    def test_model_cpu_resident(self):
        model = _make_model()
        assert mp._fast_disk_model_is_cpu_resident(model) is True
        assert mp._fast_disk_model_is_cpu_resident(None) is False


if __name__ == "__main__":
    unittest.main()
