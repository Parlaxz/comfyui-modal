"""Focused tests for the graph-time UNETLoader wrapper.

Problem addressed: with ``COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=0`` the restore-time
wrapper installers (``external_model_lane_scope``, ``ModelPreloadCoordinator``,
``V2LoaderBridge.install``) never run, so the graph-time UNETLoader would
execute an un-instrumented ``comfy.sd.load_diffusion_model`` and the flag-gated
fast-disk hooks (get_model window, patcher record, nn.Module.to defer,
load_model_weights bind) plus ``register_unet_forward_probe`` /
``ensure_sampling_timing_wrapper`` would never engage.

Covered here:
  - flag-off passthrough: no wrapper installed, byte-identical call, the
    ensure installers are never invoked, restore() is inert;
  - flag-on install: the wrapper ensures the installers (in order, BEFORE the
    lane is set) and sets/restores the UNET lane ContextVar bound to the
    current request trace;
  - end-to-end fast path with fakes through the graph wrapper
    (window -> patcher record -> defer -> bind assign=True -> one real to ->
    complete proof event on the request trace);
  - snapshot-mode guard fails closed (non-HIGH_VRAM -> legacy order);
  - idempotent double-install (one wrapper layer);
  - no double-wrap vs the ``load_diffusion_model_state_dict`` wrapper;
  - lazy install from ``runtime_bootstrap.restore`` (flag-gated).

No CUDA or real ComfyUI is required: ``torch.device`` objects are used only as
descriptors and every original call is a fake.
"""

from __future__ import annotations

import contextlib
import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock
from typing import Any

import torch

import comfymodal_runtime.model_preload as mp
from comfymodal_runtime.trace import RuntimeTrace

_CUDA = torch.device("cuda")


# ── Fakes ────────────────────────────────────────────────────────────────


class _PatcherMeta(type):
    """Metaclass that lets a fake class report an arbitrary ``__name__``."""

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


def _make_model(dtype=torch.float32, load_recorder=None) -> torch.nn.Module:
    model = torch.nn.Module()
    model.diffusion_model = torch.nn.Linear(4, 4, dtype=dtype)
    if load_recorder is not None:

        def _record_load(sd, unet_prefix="", assign=False):
            load_recorder.append(("load", assign))
            return "loaded"

        model.load_model_weights = _record_load
    else:
        model.load_model_weights = lambda *a, **k: "loaded"
    return model


def _make_sd() -> dict[str, torch.Tensor]:
    return {
        "diffusion_model.weight": torch.zeros(4, 4, dtype=torch.float32),
        "diffusion_model.bias": torch.zeros(4, dtype=torch.float32),
    }


@contextlib.contextmanager
def _fake_comfy_sd(fake_sd):
    _saved_sd = sys.modules.get("comfy.sd")
    _saved_comfy = sys.modules.get("comfy")
    sys.modules["comfy"] = _saved_comfy if _saved_comfy is not None else types.ModuleType("comfy")
    sys.modules["comfy.sd"] = fake_sd
    try:
        yield
    finally:
        if _saved_sd is None:
            sys.modules.pop("comfy.sd", None)
        else:
            sys.modules["comfy.sd"] = _saved_sd
        if _saved_comfy is None:
            sys.modules.pop("comfy", None)
        else:
            sys.modules["comfy"] = _saved_comfy


@contextlib.contextmanager
def _without_comfy_sd():
    _saved_sd = sys.modules.pop("comfy.sd", None)
    try:
        yield
    finally:
        if _saved_sd is not None:
            sys.modules["comfy.sd"] = _saved_sd


class _FastDiskFlagMixin:
    """Flag management + per-test registry/installer reset."""

    def setUp(self):
        self._saved_flag = mp._NATIVE_FAST_DISK_UNET
        mp._NATIVE_FAST_DISK_UNET = True
        self._saved_installed = mp._graph_unet_loader_wrapper_installed
        mp._graph_unet_loader_wrapper_installed = False

    def tearDown(self):
        mp._NATIVE_FAST_DISK_UNET = self._saved_flag
        mp._graph_unet_loader_wrapper_installed = self._saved_installed
        with mp._FAST_DISK_UNET_LOCK:
            mp._FAST_DISK_UNET_DEFERRALS.clear()


def _set_request_trace(trace):
    return mp._ACTIVE_REQUEST_TRACE.set(trace)


# ── Flag-off passthrough ─────────────────────────────────────────────────


class TestGraphWrapperFlagOff(unittest.TestCase):
    def setUp(self):
        self._saved_flag = mp._NATIVE_FAST_DISK_UNET
        mp._NATIVE_FAST_DISK_UNET = False
        self._saved_installed = mp._graph_unet_loader_wrapper_installed
        mp._graph_unet_loader_wrapper_installed = False

    def tearDown(self):
        mp._NATIVE_FAST_DISK_UNET = self._saved_flag
        mp._graph_unet_loader_wrapper_installed = self._saved_installed
        with mp._FAST_DISK_UNET_LOCK:
            mp._FAST_DISK_UNET_DEFERRALS.clear()

    def test_install_inert_when_flag_off(self):
        calls = []

        def fake_original(*a, **k):
            calls.append((a, k))
            return "original-result"

        fake_sd = types.ModuleType("comfy.sd")
        fake_sd.load_diffusion_model = fake_original
        with _fake_comfy_sd(fake_sd):
            status = mp._install_graph_unet_loader_wrapper(trace=None)
            assert status == "inert_flag_off"
            # Live function is untouched — byte-identical call.
            assert fake_sd.load_diffusion_model is fake_original
            assert not hasattr(fake_sd.load_diffusion_model, mp._SENTINEL_GRAPH_UNET_LOADER)
            result = fake_sd.load_diffusion_model("unet.safetensors", {"dtype": "default"})
        assert result == "original-result"
        assert len(calls) == 1
        # Byte-identical forwarding: exact positional args and no kwargs.
        assert calls[0][0] == ("unet.safetensors", {"dtype": "default"})
        assert calls[0][1] == {}

    def test_ensure_installers_never_invoked_when_flag_off(self):
        """The wrapper is not installed, so its ensure calls never run."""
        fake_sd = types.ModuleType("comfy.sd")
        fake_sd.load_diffusion_model = lambda *a, **k: None
        with _fake_comfy_sd(fake_sd), \
             mock.patch.object(mp, "_ensure_core_wrappers", wraps=mp._ensure_core_wrappers) as core_spy, \
             mock.patch.object(mp, "_ensure_unet_decompose_wrappers", wraps=mp._ensure_unet_decompose_wrappers) as dec_spy:
            status = mp._install_graph_unet_loader_wrapper(trace=None)
            assert status == "inert_flag_off"
            core_spy.assert_not_called()
            dec_spy.assert_not_called()

    def test_lazy_install_inert_when_flag_off(self):
        assert mp._ensure_graph_unet_loader_wrapper_lazy(trace=None) == "inert_flag_off"

    def test_restore_inert_when_flag_off(self):
        """restore() with the env flag off must not import/install anything."""
        import comfymodal_runtime.runtime_bootstrap as rbs
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "0"}, clear=False):
            bootstrap = rbs.RuntimeBootstrap()
            with mock.patch.object(mp, "_ensure_graph_unet_loader_wrapper_lazy") as spy:
                state = bootstrap.restore(trace=None)
            spy.assert_not_called()
        assert state.restore_completed_at > 0


# ── Flag-on install / lane scope ────────────────────────────────────────


class TestGraphWrapperInstall(_FastDiskFlagMixin, unittest.TestCase):
    def test_install_wraps_live_function(self):
        fake_sd = types.ModuleType("comfy.sd")
        fake_sd.load_diffusion_model = lambda *a, **k: "original"
        with _fake_comfy_sd(fake_sd):
            status = mp._install_graph_unet_loader_wrapper(trace=None)
            assert status == "installed"
            assert getattr(fake_sd.load_diffusion_model, mp._SENTINEL_GRAPH_UNET_LOADER, False)

    def test_install_unavailable_when_comfy_sd_missing(self):
        with _without_comfy_sd():
            assert mp._install_graph_unet_loader_wrapper(trace=None) == "unavailable"

    def test_install_unavailable_when_symbol_missing(self):
        fake_sd = types.ModuleType("comfy.sd")
        with _fake_comfy_sd(fake_sd):
            assert mp._install_graph_unet_loader_wrapper(trace=None) == "unavailable"

    def test_installed_wrapper_ensures_then_lane_scope(self):
        """Installers run (in order, BEFORE the lane is set); the lane is bound
        to the request trace as UNET/execution and restored afterwards."""
        request_trace = RuntimeTrace(request_id="graph-lane", process="remote")
        ensure_states = []
        lane_inside = []

        def fake_original(*a, **k):
            lane = mp._ACTIVE_LANE_TRACE.get()
            lane_inside.append((lane._lane, lane._phase, lane._trace is request_trace))
            return "original-result"

        fake_sd = types.ModuleType("comfy.sd")
        fake_sd.load_diffusion_model = fake_original
        with _fake_comfy_sd(fake_sd), \
             mock.patch.object(
                 mp, "_ensure_core_wrappers",
                 side_effect=lambda trace=None: ensure_states.append(
                     ("core", mp._ACTIVE_LANE_TRACE.get())
                 ) or {},
             ), \
             mock.patch.object(
                 mp, "_ensure_unet_decompose_wrappers",
                 side_effect=lambda trace=None: ensure_states.append(
                     ("decompose", mp._ACTIVE_LANE_TRACE.get())
                 ) or {},
             ):
            assert mp._install_graph_unet_loader_wrapper(trace=None) == "installed"
            token = _set_request_trace(request_trace)
            try:
                result = fake_sd.load_diffusion_model("unet.safetensors", {"dtype": "default"})
            finally:
                mp._ACTIVE_REQUEST_TRACE.reset(token)

        assert result == "original-result"
        # Install order: core BEFORE decompose; both BEFORE the lane was set.
        assert [s[0] for s in ensure_states] == ["core", "decompose"], ensure_states
        assert all(s[1] is None for s in ensure_states), (
            f"ensures must run before the lane is set: {ensure_states}"
        )
        # Inside the original the lane is UNET/execution bound to the request trace.
        assert lane_inside == [("UNET", "execution", True)], lane_inside
        # Restored after the call.
        assert mp._ACTIVE_LANE_TRACE.get() is None

    def test_installed_wrapper_preserves_active_lane(self):
        """When a UNET lane is already active the wrapper must not override it."""
        request_trace = RuntimeTrace(request_id="graph-lane-keep", process="remote")
        existing_lane = mp.ModelLaneTrace(request_trace, "UNET", phase="restore", expected_read_count=1)
        lane_inside = []

        def fake_original(*a, **k):
            lane_inside.append(mp._ACTIVE_LANE_TRACE.get() is existing_lane)
            return "ok"

        fake_sd = types.ModuleType("comfy.sd")
        fake_sd.load_diffusion_model = fake_original
        with _fake_comfy_sd(fake_sd), \
             mock.patch.object(mp, "_ensure_core_wrappers", return_value={}), \
             mock.patch.object(mp, "_ensure_unet_decompose_wrappers", return_value={}):
            assert mp._install_graph_unet_loader_wrapper(trace=None) == "installed"
            token = _set_request_trace(request_trace)
            lane_token = mp._ACTIVE_LANE_TRACE.set(existing_lane)
            try:
                fake_sd.load_diffusion_model("unet.safetensors")
            finally:
                mp._ACTIVE_LANE_TRACE.reset(lane_token)
                mp._ACTIVE_REQUEST_TRACE.reset(token)
        assert lane_inside == [True]
        assert mp._ACTIVE_LANE_TRACE.get() is None

    def test_no_request_trace_skips_lane_binding(self):
        """Flag-on wrapper with NO active request trace: lane binding is
        skipped entirely, the original is called directly (safe legacy
        degradation), no crash, and the fast-disk path is not engaged."""
        assert mp._ACTIVE_REQUEST_TRACE.get() is None
        lane_inside = []

        def fake_original(*a, **k):
            lane_inside.append(mp._ACTIVE_LANE_TRACE.get())
            return "original-result"

        fake_sd = types.ModuleType("comfy.sd")
        fake_sd.load_diffusion_model = fake_original
        with _fake_comfy_sd(fake_sd), \
             mock.patch.object(mp, "_ensure_core_wrappers", return_value={}), \
             mock.patch.object(mp, "_ensure_unet_decompose_wrappers", return_value={}):
            assert mp._install_graph_unet_loader_wrapper(trace=None) == "installed"
            result = fake_sd.load_diffusion_model("unet.safetensors")
        assert result == "original-result"
        # No lane may be set without a request trace (fast path cannot engage).
        assert lane_inside == [None], f"no lane may be bound without a request trace: {lane_inside}"
        assert mp._ACTIVE_LANE_TRACE.get() is None


# ── End-to-end fast path through the graph wrapper ──────────────────────


class TestGraphWrapperEndToEnd(_FastDiskFlagMixin, unittest.TestCase):
    def test_fast_path_engages_end_to_end(self):
        request_trace = RuntimeTrace(request_id="graph-fd-e2e", process="remote")
        calls = []
        returned_patchers = []
        model = _make_model(load_recorder=calls)

        def fake_to(m, *a, **k):
            calls.append("to")
            return m

        def fake_native_load(unet_path, model_options=None, disable_dynamic=False):
            # Simulates the instrumented comfy.sd.load_diffusion_model flow.
            lane = mp._ACTIVE_LANE_TRACE.get()
            assert lane is not None and lane._lane == "UNET", "wrapper must set the UNET lane"
            assert lane._phase == "execution"
            assert lane._trace is request_trace
            config = SimpleNamespace(get_model=lambda *a, **k: model)
            mp._instrument_unet_model_config(config, lane)
            config.get_model("sd")  # opens the fast-disk window
            patcher = _PlainPatcher(model, _CUDA, _CUDA)
            mp._fast_disk_record_patcher(patcher)
            with mock.patch.object(mp, "_fast_disk_high_vram", return_value=True):
                decision = mp._fast_disk_maybe_defer_to(model, (_CUDA,), {}, lane, fake_to)
            assert decision == "deferred", f"expected deferral, got {decision!r}"
            assert calls == [], "deferred to() must not run yet"
            result = model.load_model_weights(_make_sd(), "", assign=False)
            assert result == "loaded"
            returned_patchers.append(patcher)
            return patcher

        fake_sd = types.ModuleType("comfy.sd")
        fake_sd.load_diffusion_model = fake_native_load
        with _fake_comfy_sd(fake_sd), \
             mock.patch.object(mp, "_ensure_core_wrappers", return_value={}), \
             mock.patch.object(mp, "_ensure_unet_decompose_wrappers", return_value={}):
            assert mp._install_graph_unet_loader_wrapper(trace=None) == "installed"
            token = _set_request_trace(request_trace)
            try:
                result = fake_sd.load_diffusion_model("unet.safetensors")
            finally:
                mp._ACTIVE_REQUEST_TRACE.reset(token)

        # Fast ordering: bind(assign=True) then exactly one real to().
        assert calls == [("load", True), "to"], calls
        assert result is returned_patchers[0]
        assert mp._fast_disk_record_for(model) is None, "deferral record must be dropped"
        # Complete proof event lands on the request trace.
        names = [e.name for e in request_trace.events]
        assert mp._EVENT_FAST_DISK_COMPLETE in names, names
        assert mp._EVENT_FAST_DISK_DEFER in names
        # Lane restored after the load.
        assert mp._ACTIVE_LANE_TRACE.get() is None

    def test_snapshot_mode_guard_fails_closed_legacy(self):
        """CPU-snapshot mode (non-HIGH_VRAM) must fail the fast-disk guard
        closed and preserve the legacy order: real to() then original
        load_model_weights with its ORIGINAL assign value."""
        request_trace = RuntimeTrace(request_id="graph-fd-snap", process="remote")
        calls = []
        returned_patchers = []
        model = _make_model(load_recorder=calls)

        def fake_to(m, *a, **k):
            calls.append("to")
            return m

        def fake_native_load(unet_path, model_options=None, disable_dynamic=False):
            lane = mp._ACTIVE_LANE_TRACE.get()
            assert lane is not None and lane._lane == "UNET"
            config = SimpleNamespace(get_model=lambda *a, **k: model)
            mp._instrument_unet_model_config(config, lane)
            config.get_model("sd")
            patcher = _PlainPatcher(model, _CUDA, _CUDA)
            mp._fast_disk_record_patcher(patcher)
            # Snapshot mode: HIGH_VRAM false -> guard rejects at the to().
            with mock.patch.object(mp, "_fast_disk_high_vram", return_value=False):
                decision = mp._fast_disk_maybe_defer_to(model, (_CUDA,), {}, lane, fake_to)
            assert decision == "skip", f"snapshot mode must skip the fast path, got {decision!r}"
            assert mp._fast_disk_record_for(model) is None
            # Native flow continues: real to() (legacy) then load with ORIGINAL assign.
            fake_to(model, _CUDA)
            result = model.load_model_weights(_make_sd(), "", assign=False)
            assert result == "loaded"
            returned_patchers.append(patcher)
            return patcher

        fake_sd = types.ModuleType("comfy.sd")
        fake_sd.load_diffusion_model = fake_native_load
        with _fake_comfy_sd(fake_sd), \
             mock.patch.object(mp, "_ensure_core_wrappers", return_value={}), \
             mock.patch.object(mp, "_ensure_unet_decompose_wrappers", return_value={}):
            assert mp._install_graph_unet_loader_wrapper(trace=None) == "installed"
            token = _set_request_trace(request_trace)
            try:
                result = fake_sd.load_diffusion_model("unet.safetensors")
            finally:
                mp._ACTIVE_REQUEST_TRACE.reset(token)

        # Legacy order preserved: real to() first, then original assign=False.
        assert calls == ["to", ("load", False)], calls
        assert result is returned_patchers[0]
        names = [e.name for e in request_trace.events]
        assert any(
            e.name == mp._EVENT_FAST_DISK_SKIP and "not_high_vram" in str(e.metadata.get("reason", ""))
            for e in request_trace.events
        ), names
        assert mp._EVENT_FAST_DISK_COMPLETE not in names


# ── Idempotence / coexistence / lazy install ─────────────────────────────


class TestGraphWrapperIdempotence(_FastDiskFlagMixin, unittest.TestCase):
    def test_double_install_single_layer(self):
        fake_sd = types.ModuleType("comfy.sd")
        calls = []

        def fake_original(*a, **k):
            calls.append(a)
            return "original"

        fake_sd.load_diffusion_model = fake_original
        request_trace = RuntimeTrace(request_id="graph-double", process="remote")
        with _fake_comfy_sd(fake_sd), \
             mock.patch.object(mp, "_ensure_core_wrappers", return_value={}), \
             mock.patch.object(mp, "_ensure_unet_decompose_wrappers", return_value={}):
            assert mp._install_graph_unet_loader_wrapper(trace=None) == "installed"
            assert mp._install_graph_unet_loader_wrapper(trace=None) == "already_installed"
            token = _set_request_trace(request_trace)
            try:
                result = fake_sd.load_diffusion_model("unet.safetensors")
            finally:
                mp._ACTIVE_REQUEST_TRACE.reset(token)
        # Exactly one wrapper layer: the original runs exactly once.
        assert result == "original"
        assert calls == [("unet.safetensors",)], calls

    def test_no_double_wrap_vs_state_dict_wrapper(self):
        """Installing the graph wrapper must not touch
        ``load_diffusion_model_state_dict`` (which has its own wrapper)."""
        fake_sd = types.ModuleType("comfy.sd")
        fake_sd.load_diffusion_model = lambda *a, **k: "ldm"
        fake_sd.load_diffusion_model_state_dict = lambda *a, **k: "sd"
        with _fake_comfy_sd(fake_sd), \
             mock.patch.object(mp, "_ensure_core_wrappers", return_value={}), \
             mock.patch.object(mp, "_ensure_unet_decompose_wrappers", return_value={}):
            assert mp._install_graph_unet_loader_wrapper(trace=None) == "installed"
            assert getattr(fake_sd.load_diffusion_model, mp._SENTINEL_GRAPH_UNET_LOADER, False)
            # The state-dict function is untouched (not the graph wrapper, no sentinel).
            assert not hasattr(fake_sd.load_diffusion_model_state_dict, mp._SENTINEL_GRAPH_UNET_LOADER)
            assert fake_sd.load_diffusion_model_state_dict("sd") == "sd"

    def test_lazy_install_retries_when_comfy_sd_missing(self):
        with _without_comfy_sd():
            assert mp._ensure_graph_unet_loader_wrapper_lazy(trace=None) == "unavailable"
        fake_sd = types.ModuleType("comfy.sd")
        fake_sd.load_diffusion_model = lambda *a, **k: None
        with _fake_comfy_sd(fake_sd):
            assert mp._ensure_graph_unet_loader_wrapper_lazy(trace=None) == "installed"

    def test_restore_installs_lazily(self):
        """runtime_bootstrap.restore installs the graph wrapper when the flag
        is on (all restore callbacks are None so the rest is a no-op)."""
        import comfymodal_runtime.runtime_bootstrap as rbs
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1"}, clear=False):
            bootstrap = rbs.RuntimeBootstrap()
            with mock.patch.object(mp, "_ensure_graph_unet_loader_wrapper_lazy", return_value="installed") as spy:
                state = bootstrap.restore(trace=None)
            spy.assert_called_once()
        assert state.restore_completed_at > 0

    def test_belt_and_braces_in_ensure_core_wrappers(self):
        """_ensure_core_wrappers calls the graph-wrapper installer so existing
        lane/bridge paths install it too."""
        with mock.patch.object(mp, "_install_read_wrapper", return_value="ok"), \
             mock.patch.object(mp, "_install_gpu_wrapper", return_value="ok"), \
             mock.patch.object(mp, "_install_cast_to_device_wrapper", return_value="ok"), \
             mock.patch.object(mp, "_install_model_patcher_wrappers", return_value={}), \
             mock.patch.object(mp, "_install_clip_wrapper", return_value="ok"), \
             mock.patch.object(mp, "_install_clip_span_wrappers", return_value={}), \
             mock.patch.object(mp, "_install_mp_load_wrappers", return_value={}), \
             mock.patch.object(mp, "install_nextdit_forward_pre_hook", return_value=True), \
             mock.patch.object(mp, "_install_graph_unet_loader_wrapper", return_value="installed") as spy:
            result = mp._ensure_core_wrappers(trace=None)
        spy.assert_called_once()
        assert result.get("graph_unet_loader") == "installed"


if __name__ == "__main__":
    unittest.main()
