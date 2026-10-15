"""Focused tests for generic dispatch substitution (no GPU, no Modal).

Covers the upstream-dispatch wrapper: role selection, class verification,
list-mapping refusal, stage dispatch with native fallback, merged output
shape, owner retention through the real holder, trace accounting, and
install/restore lifecycle. Golden cores themselves are exercised live,
never here.
"""

from __future__ import annotations

import asyncio
import sys
import types

import pytest

from comfymodal_runtime import golden_generic_loaders as ggl


pytestmark = pytest.mark.fast_unit


class CLIPLoader:
    pass


class UNETLoader:
    pass


class VAELoader:
    pass


class KSampler:
    pass


class _Owner:
    """Recording QD owner (close-compatible facade)."""

    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _clean_dispatch():
    yield
    ggl._ACTIVE_DISPATCH_CTX = None


def _install_fake_execution(monkeypatch, calls):
    async def fake_native(prompt_id, unique_id, obj, input_data_all,
                         execution_block_cb=None, pre_execute_cb=None,
                         v3_data=None):
        calls.append((prompt_id, str(unique_id), type(obj).__name__))
        return ("native-output", {}, False, False)

    def fake_merge(results, obj):
        out = []
        is_list = getattr(obj, "OUTPUT_IS_LIST", None) or []
        for i in range(len(results[0])):
            if i < len(is_list) and is_list[i]:
                merged = []
                for item in results:
                    merged.extend(item[i])
                out.append(merged)
            else:
                out.append([item[i] for item in results])
        return out

    fake = types.ModuleType("execution")
    setattr(fake, "get_output_data", fake_native)
    setattr(fake, "merge_result_data", fake_merge)
    monkeypatch.setitem(sys.modules, "execution", fake)
    return fake


def _install(monkeypatch, calls, bindings, holder=None, sink=None):
    fake = _install_fake_execution(monkeypatch, calls)
    if holder is None:
        holder = ggl.GenericLoaderHolder()
    if sink is None:
        sink = []
    restore = ggl.install_execution_dispatch_substitution(
        role_bindings=bindings,
        holder=holder,
        trace_emit=(lambda name, **kw: sink.append((name, kw.get("metadata", {})))),
        request_id="r1",
    )
    assert restore is not None
    return fake, holder, sink, restore


def _clip_inputs():
    return {"clip_name": ["qwen.safetensors"], "type": ["krea2"]}


class TestDispatchSubstitution:
    def test_substitute_clip_success(self, monkeypatch):
        calls = []
        fake, holder, sink, restore = _install(
            monkeypatch, calls, {"clip": {"node_id": "195", "input_name": "clip_name"}})
        try:
            clip_obj = object()
            owner = _Owner()

            async def fake_qd4(**kwargs):
                return {"ok": True, "clip": clip_obj, "session": None,
                        "owners": [owner], "elapsed_ms": 2.0, "reason": "",
                        "source_arm": "qd4_demand"}

            monkeypatch.setattr(ggl, "compose_generic_clip_load_qd4", fake_qd4)
            out = asyncio.run(fake.get_output_data(
                "p1", "195", CLIPLoader(), _clip_inputs()))
            assert out == ([[clip_obj]], {}, False, False)
            assert calls == []  # native never ran
            assert holder._owners == [owner]
            released = holder.close()
            assert released["released"] == 1
            assert owner.closed is True
            shared = [m for n, m in sink
                      if n == "generic_dispatch_substitution"
                      and m.get("actual") == "shared_core"]
            assert len(shared) == 1
            assert shared[0]["source_arm"] == "qd4_demand"
        finally:
            restore()
        assert ggl._ACTIVE_DISPATCH_CTX is None
        assert fake.get_output_data.__name__ == "fake_native"

    def test_unbound_node_passthrough(self, monkeypatch):
        calls = []
        fake, _holder, _sink, restore = _install(
            monkeypatch, calls, {"clip": {"node_id": "195"}})
        try:
            out = asyncio.run(fake.get_output_data(
                "p1", "999", KSampler(), {}))
            assert out == ("native-output", {}, False, False)
            assert len(calls) == 1
        finally:
            restore()

    def test_class_mismatch_passthrough_records_reason(self, monkeypatch):
        calls = []
        fake, _holder, sink, restore = _install(
            monkeypatch, calls, {"clip": {"node_id": "195"}})
        try:
            out = asyncio.run(fake.get_output_data(
                "p1", "195", KSampler(), _clip_inputs()))
            assert out[0] == "native-output"
            reasons = [m.get("reason", "") for n, m in sink
                       if n == "generic_dispatch_substitution"]
            assert any("class_mismatch:KSampler" in r for r in reasons)
        finally:
            restore()

    def test_list_mapped_inputs_passthrough(self, monkeypatch):
        calls = []
        fake, _holder, _sink, restore = _install(
            monkeypatch, calls, {"clip": {"node_id": "195"}})
        try:
            out = asyncio.run(fake.get_output_data(
                "p1", "195", CLIPLoader(),
                {"clip_name": ["a.safetensors", "b.safetensors"]}))
            assert out[0] == "native-output"
            assert len(calls) == 1
        finally:
            restore()

    def test_qd4_fail_stage_success(self, monkeypatch):
        calls = []
        fake, _holder, sink, restore = _install(
            monkeypatch, calls, {"clip": {"node_id": "195"}})
        try:
            clip_obj = object()

            async def fake_qd4(**kwargs):
                return {"ok": False, "reason": "qd4_gate_disabled",
                        "elapsed_ms": 0.5, "source_arm": "qd4_demand"}

            async def fake_stage(**kwargs):
                return {"ok": True, "clip": clip_obj, "session": object(),
                        "owners": [], "elapsed_ms": 3.0, "reason": "",
                        "source_arm": "golden_clip"}

            monkeypatch.setattr(ggl, "compose_generic_clip_load_qd4", fake_qd4)
            monkeypatch.setattr(ggl, "compose_generic_clip_load_stage", fake_stage)
            out = asyncio.run(fake.get_output_data(
                "p1", "195", CLIPLoader(), _clip_inputs()))
            assert out == ([[clip_obj]], {}, False, False)
            assert calls == []
            shared = [m for n, m in sink
                      if n == "generic_dispatch_substitution"
                      and m.get("actual") == "shared_core"]
            assert shared and shared[0]["source_arm"] == "golden_clip"
        finally:
            restore()

    def test_both_arms_fail_native_fallback(self, monkeypatch):
        calls = []
        fake, _holder, sink, restore = _install(
            monkeypatch, calls, {"clip": {"node_id": "195"}})
        try:
            async def fake_qd4(**kwargs):
                return {"ok": False, "reason": "qd4_gate_disabled",
                        "source_arm": "qd4_demand"}

            async def fake_stage(**kwargs):
                return {"ok": False, "reason": "RuntimeError:legacy_qd_unavailable"}

            monkeypatch.setattr(ggl, "compose_generic_clip_load_qd4", fake_qd4)
            monkeypatch.setattr(ggl, "compose_generic_clip_load_stage", fake_stage)
            out = asyncio.run(fake.get_output_data(
                "p1", "195", CLIPLoader(), _clip_inputs()))
            assert out[0] == "native-output"
            assert len(calls) == 1
            native = [m for n, m in sink
                      if n == "generic_dispatch_substitution"
                      and m.get("actual") == "native"]
            assert native and "qd4_gate_disabled" in native[0]["reason"]
        finally:
            restore()

    def test_unet_substitution_success(self, monkeypatch):
        calls = []
        fake, holder, sink, restore = _install(
            monkeypatch, calls, {"unet": {"node_id": "194"}})
        try:
            patcher_obj = object()
            owner = _Owner()

            async def fake_unet(**kwargs):
                assert kwargs["unet_filenames"] == ["u.safetensors"]
                assert kwargs["folder"] == "diffusion_models"
                return {"ok": True, "loaded": patcher_obj, "session": object(),
                        "owners": [owner], "elapsed_ms": 4.0, "reason": "",
                        "source_arm": "golden_unet"}

            monkeypatch.setattr(ggl, "compose_generic_unet_load", fake_unet)
            out = asyncio.run(fake.get_output_data(
                "p1", "194", UNETLoader(), {"unet_name": ["u.safetensors"]}))
            assert out == ([[patcher_obj]], {}, False, False)
            assert calls == []
            assert holder._owners == [owner]
            shared = [m for n, m in sink
                      if n == "generic_dispatch_substitution"
                      and m.get("actual") == "shared_core"]
            assert len(shared) == 1
            assert shared[0]["source_arm"] == "golden_unet"
        finally:
            restore()

    def test_unet_name_missing_native(self, monkeypatch):
        calls = []
        fake, _holder, sink, restore = _install(
            monkeypatch, calls, {"unet": {"node_id": "194"}})
        try:
            out = asyncio.run(fake.get_output_data(
                "p1", "194", UNETLoader(), {}))
            assert out[0] == "native-output"
            native = [m for n, m in sink
                      if n == "generic_dispatch_substitution"
                      and m.get("actual") == "native"]
            assert native and "unet_name_missing" in native[0]["reason"]
        finally:
            restore()

    def test_unet_stage_rejection_native(self, monkeypatch):
        calls = []
        fake, _holder, sink, restore = _install(
            monkeypatch, calls, {"unet": {"node_id": "194"}})
        try:
            async def fake_unet(**kwargs):
                return {"ok": False, "reason": "RuntimeError:scaled_fp8_rejected",
                        "elapsed_ms": 1.0, "source_arm": "golden_unet"}

            monkeypatch.setattr(ggl, "compose_generic_unet_load", fake_unet)
            out = asyncio.run(fake.get_output_data(
                "p1", "194", UNETLoader(), {"unet_name": ["u.safetensors"]}))
            assert out[0] == "native-output"
            assert len(calls) == 1
            native = [m for n, m in sink
                      if n == "generic_dispatch_substitution"
                      and m.get("actual") == "native"]
            assert native and "scaled_fp8_rejected" in native[0]["reason"]
        finally:
            restore()

    def test_vae_substitution_success(self, monkeypatch):
        calls = []
        fake, holder, sink, restore = _install(
            monkeypatch, calls, {"vae": {"node_id": "196"}})
        try:
            vae_obj = object()
            owner = _Owner()

            async def fake_vae(**kwargs):
                assert kwargs["vae_filenames"] == ["v.safetensors"]
                assert kwargs["folder"] == "vae"
                return {"ok": True, "loaded": vae_obj, "session": object(),
                        "owners": [owner], "elapsed_ms": 1.0, "reason": "",
                        "source_arm": "golden_vae"}

            monkeypatch.setattr(ggl, "compose_generic_vae_load", fake_vae)
            out = asyncio.run(fake.get_output_data(
                "p1", "196", VAELoader(), {"vae_name": ["v.safetensors"]}))
            assert out == ([[vae_obj]], {}, False, False)
            assert calls == []
            assert holder._owners == [owner]
            shared = [m for n, m in sink
                      if n == "generic_dispatch_substitution"
                      and m.get("actual") == "shared_core"]
            assert len(shared) == 1
            assert shared[0]["source_arm"] == "golden_vae"
        finally:
            restore()

    def test_vae_name_missing_native(self, monkeypatch):
        calls = []
        fake, _holder, sink, restore = _install(
            monkeypatch, calls, {"vae": {"node_id": "196"}})
        try:
            out = asyncio.run(fake.get_output_data(
                "p1", "196", VAELoader(), {}))
            assert out[0] == "native-output"
            native = [m for n, m in sink
                      if n == "generic_dispatch_substitution"
                      and m.get("actual") == "native"]
            assert native and "vae_name_missing" in native[0]["reason"]
        finally:
            restore()

    def test_install_no_bindings_is_noop(self, monkeypatch):
        calls = []
        fake = _install_fake_execution(monkeypatch, calls)
        noop_emit = lambda *a, **k: None  # noqa: E731
        assert ggl.install_execution_dispatch_substitution(
            role_bindings={},
            holder=ggl.GenericLoaderHolder(),
            trace_emit=noop_emit,
            request_id="r1") is None
        assert ggl.install_execution_dispatch_substitution(
            role_bindings={"prompt": {"node_id": "1"}},
            holder=ggl.GenericLoaderHolder(),
            trace_emit=noop_emit,
            request_id="r1") is None
        assert fake.get_output_data.__name__ == "fake_native"
        assert ggl._ACTIVE_DISPATCH_CTX is None

    def test_install_twice_restore_reinstall(self, monkeypatch):
        calls = []
        fake = _install_fake_execution(monkeypatch, calls)
        noop_emit = lambda *a, **k: None  # noqa: E731
        first = ggl.install_execution_dispatch_substitution(
            role_bindings={"clip": {"node_id": "195"}},
            holder=ggl.GenericLoaderHolder(),
            trace_emit=noop_emit,
            request_id="r1")
        assert first is not None
        assert ggl.install_execution_dispatch_substitution(
            role_bindings={"clip": {"node_id": "195"}},
            holder=ggl.GenericLoaderHolder(),
            trace_emit=noop_emit,
            request_id="r1") is None
        first()
        assert ggl._ACTIVE_DISPATCH_CTX is None
        assert fake.get_output_data.__name__ == "fake_native"
        second = ggl.install_execution_dispatch_substitution(
            role_bindings={"clip": {"node_id": "195"}},
            holder=ggl.GenericLoaderHolder(),
            trace_emit=noop_emit,
            request_id="r1")
        assert second is not None
        second()

    def test_merge_failure_falls_back_native(self, monkeypatch):
        calls = []
        fake = _install_fake_execution(monkeypatch, calls)

        def bad_merge(results, obj):
            raise RuntimeError("merge_boom")

        setattr(fake, "merge_result_data", bad_merge)
        holder = ggl.GenericLoaderHolder()
        sink = []
        restore = ggl.install_execution_dispatch_substitution(
            role_bindings={"clip": {"node_id": "195"}},
            holder=holder,
            trace_emit=(lambda n, **kw: sink.append((n, kw.get("metadata", {})))),
            request_id="r1")
        assert restore is not None
        try:
            async def fake_qd4(**kwargs):
                return {"ok": True, "clip": object(), "session": None,
                        "owners": [], "elapsed_ms": 1.0, "reason": "",
                        "source_arm": "qd4_demand"}

            monkeypatch.setattr(ggl, "compose_generic_clip_load_qd4", fake_qd4)
            out = asyncio.run(fake.get_output_data(
                "p1", "195", CLIPLoader(), _clip_inputs()))
            assert out[0] == "native-output"
            assert len(calls) == 1
        finally:
            restore()


class TestDynamicVramGating:
    """Golden stages require DynamicVRAM; the gate must fail closed
    BEFORE any stage import or transport work. Uses the real compose
    ordering with a mocked activator (stages stay unexercised here)."""

    def test_helper_gate_not_set(self, monkeypatch):
        sink = []
        monkeypatch.setattr(
            ggl, "activate_golden_dynamic_vram",
            lambda: {"activated": False, "already_activated": False,
                     "reason": "gate_not_set"})
        ok, detail = ggl._ensure_stage_dynamic_vram(
            (lambda n, **kw: sink.append((n, kw.get("metadata", {})))), "r1")
        assert ok is False
        assert detail == "gate_not_set"
        assert sink and sink[0][0] == "generic_dynamic_vram"
        assert sink[0][1]["outcome"] == "skipped"

    def test_helper_activated(self, monkeypatch):
        monkeypatch.setattr(
            ggl, "activate_golden_dynamic_vram",
            lambda: {"activated": True, "already_activated": False})
        ok, detail = ggl._ensure_stage_dynamic_vram(None, "r1")
        assert (ok, detail) == (True, "activated")

    def test_helper_already_activated(self, monkeypatch):
        monkeypatch.setattr(
            ggl, "activate_golden_dynamic_vram",
            lambda: {"activated": True, "already_activated": True})
        ok, detail = ggl._ensure_stage_dynamic_vram(None, "r1")
        assert (ok, detail) == (True, "already")

    def test_helper_activator_raises(self, monkeypatch):
        def boom():
            raise RuntimeError("golden_aimdo_activation_failed:x")

        monkeypatch.setattr(ggl, "activate_golden_dynamic_vram", boom)
        ok, detail = ggl._ensure_stage_dynamic_vram(None, "r1")
        assert ok is False
        assert "RuntimeError" in detail

    def test_unet_compose_gated_before_stage(self, monkeypatch):
        monkeypatch.setattr(
            ggl, "activate_golden_dynamic_vram",
            lambda: {"activated": False, "already_activated": False,
                     "reason": "gate_not_set"})
        outcome = asyncio.run(ggl.compose_generic_unet_load(
            unet_filenames=["u.safetensors"], folder="diffusion_models",
            request_id="r1",
            path_resolver=lambda folder, name: "/tmp/" + name))
        assert outcome["ok"] is False
        assert "dynamic_vram_unavailable" in outcome["reason"]
        assert outcome["source_arm"] == "golden_unet"


class TestQuantMarkerPlacement:
    """*.comfy_quant descriptors must be CPU (loaders call .numpy()).

    Weights stay untouched (zero-copy preserved); only CUDA-like marker
    tensors move. Duck-typed: no torch needed."""

    def test_cuda_like_markers_moved_to_cpu(self):
        moved = []

        class FakeCudaTensor:
            is_cuda = True

            def __init__(self, name):
                self.name = name

            def to(self, device):
                moved.append((self.name, device))
                return "cpu-%s" % self.name

        weight = object()
        sd = {"layer.weight": weight,
              "layer.comfy_quant": FakeCudaTensor("q"),
              "other.comfy_quant": FakeCudaTensor("q2")}
        out = ggl._cpu_native_quant_markers(sd)
        assert out is sd
        assert sd["layer.comfy_quant"] == "cpu-q"
        assert ("q", "cpu") in moved and ("q2", "cpu") in moved
        assert sd["layer.weight"] is weight

    def test_cpu_and_non_markers_untouched(self):
        class FakeCpuTensor:
            is_cuda = False

            def to(self, device):
                raise AssertionError("must not move")

        marker = FakeCpuTensor()
        sd = {"w": FakeCpuTensor(), "m.comfy_quant": marker,
              "plain": 123, "x.comfy_quant": object()}
        out = ggl._cpu_native_quant_markers(sd)
        assert out is sd
        assert sd["m.comfy_quant"] is marker
        assert sd["plain"] == 123

    def test_non_dict_passthrough(self):
        assert ggl._cpu_native_quant_markers(None) is None
        assert ggl._cpu_native_quant_markers([1]) == [1]


class TestUnetWeightDtypeGuard:
    """Explicit UNETLoader weight_dtype stays native: the shared stage
    never receives that input, so only the default may substitute."""

    def test_explicit_weight_dtype_native(self, monkeypatch):
        calls = []
        fake, _holder, sink, restore = _install(
            monkeypatch, calls, {"unet": {"node_id": "194"}})

        async def fail_if_called(**kwargs):
            raise AssertionError("stage must not run with explicit weight_dtype")

        monkeypatch.setattr(ggl, "compose_generic_unet_load", fail_if_called)
        try:
            out = asyncio.run(fake.get_output_data(
                "p1", "194", UNETLoader(),
                {"unet_name": ["u.safetensors"], "weight_dtype": ["fp8_e4m3fn"]}))
            assert out[0] == "native-output"
            assert len(calls) == 1
            native = [m for n, m in sink
                      if n == "generic_dispatch_substitution"
                      and m.get("actual") == "native"]
            assert native and "unet_explicit_weight_dtype_native" in native[0]["reason"]
        finally:
            restore()

    def test_default_weight_dtype_proceeds(self, monkeypatch):
        calls = []
        fake, holder, sink, restore = _install(
            monkeypatch, calls, {"unet": {"node_id": "194"}})
        try:
            patcher_obj = object()

            async def fake_unet(**kwargs):
                return {"ok": True, "loaded": patcher_obj, "session": object(),
                        "owners": [], "elapsed_ms": 1.0, "reason": "",
                        "source_arm": "golden_unet"}

            monkeypatch.setattr(ggl, "compose_generic_unet_load", fake_unet)
            out = asyncio.run(fake.get_output_data(
                "p1", "194", UNETLoader(),
                {"unet_name": ["u.safetensors"], "weight_dtype": ["default"]}))
            assert out == ([[patcher_obj]], {}, False, False)
            assert calls == []
        finally:
            restore()


class TestUnetQdFallback:
    """Stage-contract rejection falls through to QD-native, then native."""

    def test_stage_fail_qd_success(self, monkeypatch):
        calls = []
        fake, holder, sink, restore = _install(
            monkeypatch, calls, {"unet": {"node_id": "194"}})
        try:
            patcher_obj = object()
            owner = _Owner()

            async def fake_stage(**kwargs):
                return {"ok": False,
                        "reason": "RuntimeError:non_uniform_dtype:['BF16']",
                        "elapsed_ms": 1.0, "source_arm": "golden_unet"}

            async def fake_qd(**kwargs):
                assert kwargs["unet_filenames"] == ["u.safetensors"]
                assert kwargs["folder"] == "diffusion_models"
                return {"ok": True, "loaded": patcher_obj, "session": None,
                        "owners": [owner], "elapsed_ms": 2.0, "reason": "",
                        "source_arm": "qd_unet_demand"}

            monkeypatch.setattr(ggl, "compose_generic_unet_load", fake_stage)
            monkeypatch.setattr(ggl, "compose_generic_unet_load_qd", fake_qd)
            out = asyncio.run(fake.get_output_data(
                "p1", "194", UNETLoader(), {"unet_name": ["u.safetensors"]}))
            assert out == ([[patcher_obj]], {}, False, False)
            assert calls == []
            assert holder._owners == [owner]
            shared = [m for n, m in sink
                      if n == "generic_dispatch_substitution"
                      and m.get("actual") == "shared_core"]
            assert len(shared) == 1
            assert shared[0]["source_arm"] == "qd_unet_demand"
        finally:
            restore()

    def test_stage_and_qd_fail_native_combined(self, monkeypatch):
        calls = []
        fake, _holder, sink, restore = _install(
            monkeypatch, calls, {"unet": {"node_id": "194"}})
        try:
            async def fake_stage(**kwargs):
                return {"ok": False, "reason": "RuntimeError:non_uniform_dtype",
                        "source_arm": "golden_unet"}

            async def fake_qd(**kwargs):
                return {"ok": False, "reason": "RuntimeError:qd_unet_gate_disabled",
                        "source_arm": "qd_unet_demand"}

            monkeypatch.setattr(ggl, "compose_generic_unet_load", fake_stage)
            monkeypatch.setattr(ggl, "compose_generic_unet_load_qd", fake_qd)
            out = asyncio.run(fake.get_output_data(
                "p1", "194", UNETLoader(), {"unet_name": ["u.safetensors"]}))
            assert out[0] == "native-output"
            assert len(calls) == 1
            native = [m for n, m in sink
                      if n == "generic_dispatch_substitution"
                      and m.get("actual") == "native"]
            assert native and "non_uniform_dtype" in native[0]["reason"]
            assert "qd_unet_gate_disabled" in native[0]["reason"]
        finally:
            restore()


class _FakeKitchenScope:
    def __init__(self, log, state):
        self._log = log
        self._state = dict(state)

    def __enter__(self):
        self._log.append("enter")
        return self._state

    def __exit__(self, *exc):
        self._log.append("exit")
        return False


class _ExitPopulatingScope:
    """Mirrors the real attention_backend_scope protocol: the final call
    count is written into the yielded state on context exit, not entry.
    A reader that aggregates before unwind observes 0."""

    def __init__(self, log, calls_at_exit):
        self._log = log
        self._calls_at_exit = calls_at_exit
        self._state = {"selected_callable": "fake_kitchen_int8", "calls": 0}

    def __enter__(self):
        self._log.append("enter")
        return self._state

    def __exit__(self, *exc):
        self._state["calls"] = self._calls_at_exit
        self._log.append("exit")
        return False


class TestKitchenAttention:
    """Native sampling runs untouched; kitchen attention wraps it when the
    deployment selects comfy_kitchen. Setup failure degrades to bare
    native; node errors propagate with the scope restored."""

    def _sampler_inputs(self, patcher):
        return {"model": [patcher], "seed": [1], "steps": [8]}

    def test_engaged(self, monkeypatch):
        calls = []
        log = []
        seen = {}
        fake, _holder, sink, restore = _install(
            monkeypatch, calls, {"clip": {"node_id": "195"}})
        monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                           "comfy_kitchen")

        def factory(patcher, backend):
            seen["patcher"] = patcher
            seen["backend"] = backend
            return _FakeKitchenScope(
                log, {"selected_callable": "fake_kitchen_int8", "calls": 7})

        monkeypatch.setattr(ggl, "_kitchen_scope_for", factory)
        try:
            patcher = type("P", (), {"model_options": {}})()
            out = asyncio.run(fake.get_output_data(
                "p1", "163", KSampler(), self._sampler_inputs(patcher)))
            assert out[0] == "native-output"
            assert len(calls) == 1
            assert seen["patcher"] is patcher
            assert seen["backend"] == "comfy_kitchen"
            assert log == ["enter", "exit"]
            engaged = [m for n, m in sink
                       if n == "generic_kitchen_attention"
                       and m.get("outcome") == "engaged"]
            assert len(engaged) == 1
            assert engaged[0]["selected"] == "fake_kitchen_int8"
            assert engaged[0]["calls"] == 7
            assert engaged[0]["node_id"] == "163"
        finally:
            restore()
            monkeypatch.delenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                               raising=False)

    def test_policy_off_bare(self, monkeypatch):
        calls = []
        fake, _holder, sink, restore = _install(
            monkeypatch, calls, {"clip": {"node_id": "195"}})
        monkeypatch.delenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                           raising=False)

        def factory(patcher, backend):
            raise AssertionError("scope must not build when policy off")

        monkeypatch.setattr(ggl, "_kitchen_scope_for", factory)
        try:
            patcher = type("P", (), {"model_options": {}})()
            out = asyncio.run(fake.get_output_data(
                "p1", "163", KSampler(), self._sampler_inputs(patcher)))
            assert out[0] == "native-output"
            assert len(calls) == 1
            assert not [n for n, _m in sink if n == "generic_kitchen_attention"]
        finally:
            restore()

    def test_setup_failure_falls_back_bare(self, monkeypatch):
        calls = []
        fake, _holder, sink, restore = _install(
            monkeypatch, calls, {"clip": {"node_id": "195"}})
        monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                           "comfy_kitchen")

        def factory(patcher, backend):
            raise RuntimeError("comfy_kitchen_attention_unavailable")

        monkeypatch.setattr(ggl, "_kitchen_scope_for", factory)
        try:
            patcher = type("P", (), {"model_options": {}})()
            out = asyncio.run(fake.get_output_data(
                "p1", "163", KSampler(), self._sampler_inputs(patcher)))
            assert out[0] == "native-output"
            assert len(calls) == 1
            skipped = [m for n, m in sink
                       if n == "generic_kitchen_attention"
                       and m.get("outcome") == "skipped"]
            assert len(skipped) == 1
            assert "scope_setup" in skipped[0]["reason"]
        finally:
            restore()
            monkeypatch.delenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                               raising=False)

    def test_non_sampler_untouched(self, monkeypatch):
        calls = []
        log = []
        fake, _holder, sink, restore = _install(
            monkeypatch, calls, {"clip": {"node_id": "195"}})
        monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                           "comfy_kitchen")

        def factory(patcher, backend):
            log.append("built")
            return _FakeKitchenScope(log, {})

        monkeypatch.setattr(ggl, "_kitchen_scope_for", factory)
        try:
            out = asyncio.run(fake.get_output_data(
                "p1", "199", CLIPLoader(), {"images": ["1", 0]}))
            assert out[0] == "native-output"
            assert log == []
            assert not [n for n, _m in sink if n == "generic_kitchen_attention"]
        finally:
            restore()
            monkeypatch.delenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                               raising=False)

    def test_node_error_propagates_scope_restored(self, monkeypatch):
        import sys as _sys
        import types as _types

        log = []

        async def raising_native(prompt_id, unique_id, obj, input_data_all,
                                 execution_block_cb=None, pre_execute_cb=None,
                                 v3_data=None):
            raise RuntimeError("sampler_boom")

        def fake_merge(results, obj):
            return results

        fake = _types.ModuleType("execution")
        setattr(fake, "get_output_data", raising_native)
        setattr(fake, "merge_result_data", fake_merge)
        monkeypatch.setitem(_sys.modules, "execution", fake)
        monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                           "comfy_kitchen")

        def factory(patcher, backend):
            return _FakeKitchenScope(
                log, {"selected_callable": "x", "calls": 0})

        monkeypatch.setattr(ggl, "_kitchen_scope_for", factory)
        holder = ggl.GenericLoaderHolder()
        restore = ggl.install_execution_dispatch_substitution(
            role_bindings={"clip": {"node_id": "195"}}, holder=holder,
            trace_emit=lambda *a, **k: None, request_id="r1")
        assert restore is not None
        try:
            patcher = type("P", (), {"model_options": {}})()
            with pytest.raises(RuntimeError, match="sampler_boom"):
                asyncio.run(fake.get_output_data(
                    "p1", "163", KSampler(), self._sampler_inputs(patcher)))
            assert log == ["enter", "exit"]
        finally:
            restore()
            monkeypatch.delenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                               raising=False)

    def test_guider_fed_sampler_engages(self, monkeypatch):
        # Ideogram/Flux2 wiring: SamplerCustomAdvanced carries no direct
        # model input; the patcher arrives via the guider.
        calls = []
        seen = {}

        class SamplerCustomAdvanced:
            pass

        class FakeGuider:
            def __init__(self, patcher):
                self.model_patcher = patcher

        fake, holder, sink, restore = _install(
            monkeypatch, calls, {"clip": {"node_id": "195"}})
        monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                           "comfy_kitchen")

        def factory(patcher, backend):
            seen["patcher"] = patcher
            return _FakeKitchenScope(
                [], {"selected_callable": "fake_kitchen_int8", "calls": 3})

        monkeypatch.setattr(ggl, "_kitchen_scope_for", factory)
        try:
            patcher = type("P", (), {"model_options": {}})()
            inputs = {"guider": [FakeGuider(patcher)], "noise": ["n", 0],
                      "sampler": ["s", 0], "sigmas": ["g", 0],
                      "latent_image": ["l", 0]}
            out = asyncio.run(fake.get_output_data(
                "p1", "98:12", SamplerCustomAdvanced(), inputs))
            assert out[0] == "native-output"
            assert seen["patcher"] is patcher
            engaged = [m for n, m in sink
                       if n == "generic_kitchen_attention"
                       and m.get("outcome") == "engaged"]
            assert len(engaged) == 1
            assert engaged[0]["calls"] == 3
            assert engaged[0]["patchers"] == 1
            summary = holder.kitchen_summary()
            assert summary["requested"] == "comfy_kitchen"
            assert summary["engaged"][0]["node_id"] == "98:12"
            assert summary["engaged"][0]["node_class"] == (
                "SamplerCustomAdvanced")
            assert summary["engaged"][0]["patchers"] == 1
            assert summary["engaged"][0]["models"] == ["P"]
        finally:
            restore()
            monkeypatch.delenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                               raising=False)

    def test_executor_shaped_sampler_without_patcher_warns(self, monkeypatch):
        # Sampler-named executor inputs (latent/noise) but no resolvable
        # patcher: native fallback with an explicit skipped record so the
        # generation metadata and Studio viewer show the miss.
        calls = []

        class SamplerCustomAdvanced:
            pass

        fake, holder, sink, restore = _install(
            monkeypatch, calls, {"clip": {"node_id": "195"}})
        monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                           "comfy_kitchen")
        try:
            inputs = {"noise": ["n", 0], "latent_image": ["l", 0]}
            out = asyncio.run(fake.get_output_data(
                "p1", "98:12", SamplerCustomAdvanced(), inputs))
            assert out[0] == "native-output"
            skipped = [m for n, m in sink
                       if n == "generic_kitchen_attention"
                       and m.get("outcome") == "skipped"]
            assert len(skipped) == 1
            assert skipped[0]["reason"] == "no_sampler_patcher_resolved"
            summary = holder.kitchen_summary()
            assert summary["skipped"][0]["node_id"] == "98:12"
        finally:
            restore()
            monkeypatch.delenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                               raising=False)

    def test_selector_without_latent_stays_silent(self, monkeypatch):
        # KSamplerSelect is sampler-named but not an executor: no warning.
        calls = []

        class KSamplerSelect:
            pass

        fake, holder, sink, restore = _install(
            monkeypatch, calls, {"clip": {"node_id": "195"}})
        monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                           "comfy_kitchen")
        try:
            out = asyncio.run(fake.get_output_data(
                "p1", "98:16", KSamplerSelect(), {"sampler_name": ["euler"]}))
            assert out[0] == "native-output"
            assert not [n for n, _m in sink
                        if n == "generic_kitchen_attention"]
            assert holder.kitchen_summary()["skipped"] == []
        finally:
            restore()
            monkeypatch.delenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                               raising=False)

    def test_calls_aggregate_after_scope_exit(self, monkeypatch):
        # Regression: the shared scope writes its final call count on
        # context exit. Aggregating before unwind always observes 0.
        calls = []
        log = []

        fake, holder, sink, restore = _install(
            monkeypatch, calls, {"clip": {"node_id": "195"}})
        monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                           "comfy_kitchen")

        def factory(patcher, backend):
            return _ExitPopulatingScope(log, 256)

        monkeypatch.setattr(ggl, "_kitchen_scope_for", factory)
        try:
            patcher = type("P", (), {"model_options": {}})()
            out = asyncio.run(fake.get_output_data(
                "p1", "163", KSampler(), self._sampler_inputs(patcher)))
            assert out[0] == "native-output"
            assert log == ["enter", "exit"]
            engaged = [m for n, m in sink
                       if n == "generic_kitchen_attention"
                       and m.get("outcome") == "engaged"]
            assert len(engaged) == 1
            assert engaged[0]["calls"] == 256
            assert holder.kitchen_summary()["engaged"][0]["calls"] == 256
        finally:
            restore()
            monkeypatch.delenv("COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND",
                               raising=False)


class TestGenericOverlapPlan:
    """Pure overlap planner: triple derivation, no scheduling."""

    @staticmethod
    def _zit_bindings():
        return {
            "clip": {"node_id": "62", "input_name": "clip_name"},
            "model_unet": {"node_id": "66", "input_name": "unet_name"},
            "vae": {"node_id": "1277", "input_name": "vae_name"},
        }

    @staticmethod
    def _zit_workflow(extra=None):
        wf = {
            "62": {"class_type": "CLIPLoader",
                   "inputs": {"clip_name": "qwen.safetensors"}},
            "66": {"class_type": "UNETLoader",
                   "inputs": {"unet_name": "z.safetensors"}},
            "67": {"class_type": "CLIPTextEncode",
                   "inputs": {"clip": ["62", 0], "text": ["82", 0]}},
            "82": {"class_type": "GetNode",
                   "inputs": {}},
        }
        if extra:
            wf.update(extra)
        return wf

    def test_zit_triple_eligible(self):
        plan = ggl._derive_generic_overlap_plan(
            workflow=self._zit_workflow(),
            role_bindings=self._zit_bindings())
        assert plan["eligible"] is True
        assert plan["clip_node_id"] == "62"
        assert plan["unet_node_id"] == "66"
        assert plan["forward_node_id"] == "67"
        assert plan["deferral_allowed"] is True
        assert plan["identification"] == "derived"
        assert plan["reason"] == ""

    def test_ambiguous_forward_degrades(self):
        wf = self._zit_workflow(extra={
            "68": {"class_type": "CLIPTextEncode",
                   "inputs": {"clip": ["62", 0], "text": "x"}}})
        plan = ggl._derive_generic_overlap_plan(
            workflow=wf, role_bindings=self._zit_bindings())
        assert plan["eligible"] is True
        assert plan["forward_node_id"] is None
        assert plan["deferral_allowed"] is False
        assert plan["reason"] == "ambiguous_forward"

    def test_no_encode_clip_first_only(self):
        wf = {k: v for k, v in self._zit_workflow().items() if k != "67"}
        plan = ggl._derive_generic_overlap_plan(
            workflow=wf, role_bindings=self._zit_bindings())
        assert plan["eligible"] is True
        assert plan["forward_node_id"] is None
        assert plan["reason"] == "forward_not_found"

    def test_stale_clip_binding_ineligible(self):
        plan = ggl._derive_generic_overlap_plan(
            workflow=self._zit_workflow(),
            role_bindings={"clip": {"node_id": "999"}})
        assert plan["eligible"] is False

    def test_unet_class_mismatch_clip_first_only(self):
        wf = self._zit_workflow()
        wf["66"] = {"class_type": "VAELoader", "inputs": {}}
        plan = ggl._derive_generic_overlap_plan(
            workflow=wf, role_bindings=self._zit_bindings())
        assert plan["eligible"] is True
        assert plan["unet_node_id"] is None
        assert plan["deferral_allowed"] is False

    def test_unet_ancestor_of_forward_no_deferral(self):
        wf = self._zit_workflow()
        wf["67"] = {"class_type": "CLIPTextEncode",
                    "inputs": {"clip": ["62", 0], "model": ["66", 0]}}
        plan = ggl._derive_generic_overlap_plan(
            workflow=wf, role_bindings=self._zit_bindings())
        assert plan["eligible"] is True
        assert plan["forward_node_id"] == "67"
        assert plan["deferral_allowed"] is False
        assert plan["reason"] == "unet_ancestor_of_forward"

    def test_empty_bindings_ineligible(self):
        plan = ggl._derive_generic_overlap_plan(
            workflow=self._zit_workflow(), role_bindings={})
        assert plan["eligible"] is False
        assert plan["reason"] == "no_eligible_roles"

    def test_non_mapping_workflow_ineligible(self):
        plan = ggl._derive_generic_overlap_plan(
            workflow=None, role_bindings=self._zit_bindings())
        assert plan["eligible"] is False

    def test_never_raises_on_garbage(self):
        for wf, bindings in ((None, None), ([], []),
                             ("x", "y"), ({"62": []}, {"clip": "62"})):
            plan = ggl._derive_generic_overlap_plan(
                workflow=wf, role_bindings=bindings)
            assert isinstance(plan, dict)
            assert plan["eligible"] is False

    def test_installer_emits_plan_when_enabled(self, monkeypatch):
        calls = []
        _install_fake_execution(monkeypatch, calls)
        monkeypatch.setenv("COMFYMODAL_V2_GENERIC_OVERLAP", "1")
        sink = []
        restore = None
        try:
            restore = ggl.install_execution_dispatch_substitution(
                role_bindings=self._zit_bindings(),
                holder=ggl.GenericLoaderHolder(),
                trace_emit=(lambda name, **kw: sink.append(
                    (name, kw.get("metadata", {})))),
                request_id="r1",
                workflow=self._zit_workflow(),
            )
            assert restore is not None
            events = [m for n, m in sink if n == "generic_overlap_plan"]
            assert len(events) == 1
            assert events[0]["eligible"] is True
            assert events[0]["forward_node_id"] == "67"
            assert ggl._ACTIVE_DISPATCH_CTX is not None
            stored = ggl._ACTIVE_DISPATCH_CTX["overlap_plan"]
            assert stored["eligible"] is True
            assert stored["deferral_allowed"] is True
        finally:
            if restore is not None:
                restore()
            monkeypatch.delenv("COMFYMODAL_V2_GENERIC_OVERLAP",
                               raising=False)

    def test_installer_silent_when_disabled(self, monkeypatch):
        calls = []
        _install_fake_execution(monkeypatch, calls)
        monkeypatch.delenv("COMFYMODAL_V2_GENERIC_OVERLAP", raising=False)
        sink = []
        restore = ggl.install_execution_dispatch_substitution(
            role_bindings=self._zit_bindings(),
            holder=ggl.GenericLoaderHolder(),
            trace_emit=(lambda name, **kw: sink.append(
                (name, kw.get("metadata", {})))),
            request_id="r1",
            workflow=self._zit_workflow(),
        )
        assert restore is not None
        try:
            assert not [n for n, _m in sink if n == "generic_overlap_plan"]
            assert ggl._ACTIVE_DISPATCH_CTX is not None
            stored = ggl._ACTIVE_DISPATCH_CTX["overlap_plan"]
            assert stored["eligible"] is False
            assert stored["reason"] == "overlap_disabled"
        finally:
            restore()


class TestGenericUnetPrepareBind:
    """UNET prepare/bind split: single read, identity-checked bind."""

    @staticmethod
    def _reloader(*args, **kwargs):
        raise AssertionError("reloader must stay inert during bind")

    @staticmethod
    def _reader(calls, sd=None, metadata=None, explode=None):
        def _read(path):
            calls.append(path)
            if explode is not None:
                raise explode
            return ({"w": object()} if sd is None else sd,
                    {} if metadata is None else metadata)
        return _read

    @staticmethod
    def _file(tmp_path, name="u.safetensors", data=b"0123456789"):
        target = tmp_path / name
        target.write_bytes(data)
        return str(target)

    def test_prepare_single_read_with_identity(self, tmp_path):
        calls = []
        out = ggl._prepare_generic_unet_source(
            folder="diffusion_models", filename="u.safetensors",
            path_resolver=lambda _f, _n: self._file(tmp_path),
            reader=self._reader(calls))
        assert out["ok"] is True
        assert calls and len(calls) == 1
        assert out["size_bytes"] == 10
        assert out["mtime_ns"] > 0
        assert isinstance(out["sd"], dict)
        assert out["advise_status"] != ""
        assert out["elapsed_ms"] >= 0.0

    def test_prepare_failures_never_raise(self, tmp_path):
        assert ggl._prepare_generic_unet_source(
            folder="d", filename="",
            path_resolver=lambda _f, _n: None)["ok"] is False
        assert ggl._prepare_generic_unet_source(
            folder="d", filename="x",
            path_resolver=lambda _f, _n: None)["ok"] is False
        out = ggl._prepare_generic_unet_source(
            folder="d", filename="x",
            path_resolver=lambda _f, _n: self._file(tmp_path),
            reader=self._reader([], explode=RuntimeError("disk")))
        assert out["ok"] is False
        assert "RuntimeError" in out["reason"]
        out = ggl._prepare_generic_unet_source(
            folder="d", filename="x",
            path_resolver=lambda _f, _n: self._file(tmp_path),
            reader=lambda _p: (["not", "a", "dict"], {}))
        assert out["ok"] is False
        assert out["reason"] == "source_not_mapping"

    def test_bind_consumes_without_reread(self, tmp_path):
        calls = []
        seen = {}

        class _Model:
            pass

        def _ctor(sd, model_options=None, metadata=None):
            seen["sd"] = sd
            seen["options"] = dict(model_options or {})
            seen["metadata"] = metadata
            return seen.setdefault("model", _Model())

        prepared = ggl._prepare_generic_unet_source(
            folder="d", filename="u.safetensors",
            path_resolver=lambda _f, _n: self._file(tmp_path),
            reader=self._reader(calls))
        assert prepared["ok"] is True
        out = ggl._bind_generic_unet_source(
            prepared=prepared,
            constructor=_ctor, reloader=self._reloader)
        assert out["ok"] is True
        assert len(calls) == 1
        assert seen["sd"] is prepared["sd"]
        assert seen["options"] == {}
        assert out["model"] is seen["model"]

    def test_bind_options_and_patcher_init(self, tmp_path):
        seen = {}

        class _Model:
            pass

        def _ctor(sd, model_options=None, metadata=None):
            seen["options"] = dict(model_options or {})
            return _Model()

        reloader = self._reloader
        prepared = ggl._prepare_generic_unet_source(
            folder="d", filename="u.safetensors",
            path_resolver=lambda _f, _n: self._file(tmp_path),
            reader=self._reader([]))
        out = ggl._bind_generic_unet_source(
            prepared=prepared, model_options={"dtype": "x"},
            constructor=_ctor, reloader=reloader)
        assert out["ok"] is True
        assert seen["options"] == {"dtype": "x"}
        assert out["model"].cached_patcher_init == (
            reloader, (prepared["path"], {"dtype": "x"}))

    def test_bind_rejects_changed_source(self, tmp_path):
        path = self._file(tmp_path)
        prepared = ggl._prepare_generic_unet_source(
            folder="d", filename="u.safetensors",
            path_resolver=lambda _f, _n: path,
            reader=self._reader([]))
        assert prepared["ok"] is True
        with open(path, "ab") as handle:
            handle.write(b"more")
        out = ggl._bind_generic_unet_source(
            prepared=prepared,
            constructor=lambda **_k: object(), reloader=self._reloader)
        assert out["ok"] is False
        assert out["reason"] == "source_changed"

    def test_bind_rejects_undetected_or_raising(self, tmp_path):
        prepared = ggl._prepare_generic_unet_source(
            folder="d", filename="u.safetensors",
            path_resolver=lambda _f, _n: self._file(tmp_path),
            reader=self._reader([]))
        out = ggl._bind_generic_unet_source(
            prepared=prepared,
            constructor=lambda sd, **_k: None, reloader=self._reloader)
        assert out["ok"] is False
        assert out["reason"] == "model_type_undetected"
        out = ggl._bind_generic_unet_source(
            prepared=prepared,
            constructor=lambda sd, **_k: (_ for _ in ()).throw(
                ValueError("bad")),
            reloader=self._reloader)
        assert out["ok"] is False
        assert "ValueError" in out["reason"]

    def test_bind_never_raises_on_garbage(self):
        for prepared in (None, [], "x", {}, {"sd": []}, {"sd": {}}):
            out = ggl._bind_generic_unet_source(
                prepared=prepared,
                constructor=lambda **_k: object(), reloader=self._reloader)
            assert isinstance(out, dict)
            assert out["ok"] is False


class TestPlainDeclineSwitchGate:
    """Plain-source decline fires only with overlap active."""

    @staticmethod
    def _plain_header(monkeypatch, tmp_path):
        target = tmp_path / "u.safetensors"
        target.write_bytes(b"0" * 64)
        monkeypatch.setattr(
            ggl, "_default_path_resolver",
            lambda _f, _n: str(target))
        monkeypatch.setattr(
            ggl, "_describe_safetensors_header",
            lambda _p: {"ok": True, "dtypes": {"BF16"},
                        "quantized_key_count": 0,
                        "scaled_fp8_key_count": 0,
                        "has_quantization_metadata": False})

    def test_decline_off_by_default(self, monkeypatch, tmp_path):
        self._plain_header(monkeypatch, tmp_path)
        monkeypatch.delenv("COMFYMODAL_V2_GENERIC_OVERLAP", raising=False)
        assert ggl._plain_source_native_decline(
            folder="d", filename="u.safetensors",
            source_arm="golden_unet") is None

    def test_decline_fires_when_enabled(self, monkeypatch, tmp_path):
        self._plain_header(monkeypatch, tmp_path)
        monkeypatch.setenv("COMFYMODAL_V2_GENERIC_OVERLAP", "1")
        try:
            out = ggl._plain_source_native_decline(
                folder="d", filename="u.safetensors",
                source_arm="golden_unet")
            assert out is not None
            assert out["ok"] is False
            assert out["reason"] == "plain_source_native_optimal"
        finally:
            monkeypatch.delenv("COMFYMODAL_V2_GENERIC_OVERLAP",
                               raising=False)


class TestComfyQuantQdRoute:
    """*.comfy_quant UNETs route deterministically to the QD demand arm.

    Every golden dtype-plan builder rejects raw ``.comfy_quant``
    descriptors fail-closed, while the QD arm carries them CPU-only
    into native construction: the stage attempt is provably doomed,
    so compose must decline before session build / stage import.
    """

    @staticmethod
    def _header_file(tmp_path, keys):
        import json as _json

        header = {k: {"dtype": "F32", "shape": [1],
                      "data_offsets": [0, 4]} for k in keys}
        raw = _json.dumps(header).encode("utf-8")
        target = tmp_path / "u.safetensors"
        target.write_bytes(len(raw).to_bytes(8, "little") + raw)
        return str(target)

    def test_survey_counts_comfy_quant_keys(self, tmp_path):
        path = self._header_file(
            tmp_path, ["a.weight", "b.comfy_quant", "c.scale_weight"])
        out = ggl._describe_safetensors_header(path)
        assert out["ok"] is True
        assert out["comfy_quant_key_count"] == 1
        assert out["quantized_key_count"] == 2

    def test_compose_routes_without_stage(self, monkeypatch, tmp_path):
        path = self._header_file(tmp_path, ["a.weight", "a.comfy_quant"])

        def boom(**_kw):
            raise AssertionError("stage must not be entered")

        monkeypatch.setattr(ggl, "build_generic_unet_session", boom)
        out = asyncio.run(ggl.compose_generic_unet_load(
            unet_filenames=["u.safetensors"], folder="diffusion_models",
            request_id="r1", path_resolver=lambda _f, _n: path))
        assert out["ok"] is False
        assert out["reason"].startswith("unet_comfy_quant_qd_routed:1")
        assert out["source_arm"] == "golden_unet"

    def test_compose_without_markers_keeps_stage_path(
            self, monkeypatch, tmp_path):
        # No markers: the survey passes through and the existing vram
        # gate (not the new route) still decides, proving the route is
        # marker-gated and nothing else changed.
        path = self._header_file(tmp_path, ["a.weight"])
        monkeypatch.setattr(
            ggl, "activate_golden_dynamic_vram",
            lambda: {"activated": False, "already_activated": False,
                     "reason": "gate_not_set"})
        out = asyncio.run(ggl.compose_generic_unet_load(
            unet_filenames=["u.safetensors"], folder="diffusion_models",
            request_id="r1", path_resolver=lambda _f, _n: path))
        assert out["ok"] is False
        assert "dynamic_vram_unavailable" in out["reason"]


class TestGenericOverlapPick:
    """Pick policy + advise hints: ordering only, never execution."""

    @staticmethod
    def _pick(**kw):
        base: dict[str, object] = dict(
            available=[], clip_node_id="62", unet_node_id="66",
            forward_node_id="67", deferral_allowed=True,
            dispatched=set())
        base.update(kw)
        return ggl._overlap_select_pick(
            available=base["available"],
            clip_node_id=base["clip_node_id"],
            unet_node_id=base["unet_node_id"],
            forward_node_id=base["forward_node_id"],
            deferral_allowed=bool(base["deferral_allowed"]),
            dispatched=base["dispatched"])

    def test_clip_first(self):
        out = self._pick(available=["66", "62", "1277"])
        assert out == {"action": "pick", "node_id": "62"}

    def test_clip_done_no_force(self):
        # A dispatched node never reappears in the live ready set; the
        # policy must not re-pick it.
        out = self._pick(available=["62"], dispatched={"62"})
        assert out["action"] == "original"

    def test_forward_preferred_over_unet(self):
        out = self._pick(available=["66", "67", "1277"])
        assert out == {"action": "pick", "node_id": "67"}

    def test_unet_excluded_while_forward_pending(self):
        out = self._pick(available=["66", "1277"])
        assert out == {"action": "exclude", "node_id": "66"}

    def test_unet_only_available_runs(self):
        out = self._pick(available=["66"])
        assert out["action"] == "original"

    def test_forward_dispatched_lifts_deferral(self):
        out = self._pick(available=["66", "1277"], dispatched={"67"})
        assert out["action"] == "original"

    def test_deferral_off_leaves_order(self):
        out = self._pick(available=["66", "67"], deferral_allowed=False)
        assert out["action"] == "original"

    def test_no_forward_no_deferral(self):
        out = self._pick(available=["66", "1277"], forward_node_id=None)
        assert out["action"] == "original"

    def test_never_raises(self):
        out = ggl._overlap_select_pick(
            available=None, clip_node_id=None, unet_node_id=None,
            forward_node_id=None, deferral_allowed=True, dispatched=None)
        assert out["action"] == "original"

    def test_advise_model_tmp_file(self, tmp_path):
        target = tmp_path / "m.safetensors"
        target.write_bytes(b"0123456789")
        out = ggl._overlap_advise_model(
            folder="any", filename="m.safetensors")
        assert isinstance(out, dict)
        # Resolver is folder_paths-backed; unresolvable locally is fine.
        assert out["ok"] in (True, False)
        assert out["advise_status"] != ""

    def test_advise_model_failures_never_raise(self):
        assert ggl._overlap_advise_model(
            folder="d", filename="")["ok"] is False
        assert ggl._overlap_advise_model(
            folder="d", filename="missing.safetensors")["ok"] is False

    def test_pick_wrapper_reorders_and_restores(self, monkeypatch):
        import sys as _sys
        import types as _types

        calls = []

        class _ExecList:
            def ux_friendly_pick_node(self, node_list):
                calls.append(list(node_list))
                return node_list[0]

        pkg = _types.ModuleType("comfy_execution")
        sub = _types.ModuleType("comfy_execution.graph")
        setattr(sub, "ExecutionList", _ExecList)
        monkeypatch.setitem(_sys.modules, "comfy_execution", pkg)
        monkeypatch.setitem(_sys.modules, "comfy_execution.graph", sub)
        ctx = {"overlap_plan": {
            "eligible": True, "clip_node_id": "62",
            "unet_node_id": "66", "forward_node_id": "67",
            "deferral_allowed": True},
            "dispatched_nodes": set()}
        sink = []
        restore = ggl._install_overlap_pick_policy(
            trace_emit=(lambda name, **kw: sink.append(
                (name, kw.get("metadata", {})))),
            request_id="r1", get_ctx=lambda: ctx)
        assert restore is not None
        try:
            inst = _ExecList()
            assert inst.ux_friendly_pick_node(["66", "67"]) == "67"
            assert inst.ux_friendly_pick_node(["62", "66"]) == "62"
            ctx["dispatched_nodes"].add("67")
            assert inst.ux_friendly_pick_node(["66", "1277"]) == "66"
            assert [n for n, _m in sink
                    if n == "generic_overlap_pick"]
        finally:
            restore()
        assert (_ExecList.ux_friendly_pick_node.__name__ ==
                "ux_friendly_pick_node")

    def test_pick_wrapper_missing_graph_is_none(self, monkeypatch):
        import sys as _sys

        monkeypatch.delitem(_sys.modules, "comfy_execution", raising=False)
        monkeypatch.delitem(_sys.modules, "comfy_execution.graph",
                            raising=False)
        out = ggl._install_overlap_pick_policy(
            trace_emit=None, request_id="r1", get_ctx=dict)
        assert out is None

    def test_dispatched_tracking_recorded(self, monkeypatch):
        calls = []
        _install_fake_execution(monkeypatch, calls)
        monkeypatch.setenv("COMFYMODAL_V2_GENERIC_OVERLAP", "1")
        wf = TestGenericOverlapPlan._zit_workflow()
        sink = []
        restore = None
        try:
            restore = ggl.install_execution_dispatch_substitution(
                role_bindings=TestGenericOverlapPlan._zit_bindings(),
                holder=ggl.GenericLoaderHolder(),
                trace_emit=(lambda name, **kw: sink.append(
                    (name, kw.get("metadata", {})))),
                request_id="r1",
                workflow=wf,
            )
            assert restore is not None
            stored = ggl._ACTIVE_DISPATCH_CTX
            assert stored is not None
            assert stored["overlap_plan"]["eligible"] is True
            assert "overlap_pick_restore" in stored
        finally:
            if restore is not None:
                restore()
            monkeypatch.delenv("COMFYMODAL_V2_GENERIC_OVERLAP",
                               raising=False)


class TestOverlapUnetTicket:
    """Early UNET load ticket: launch, match, restore-cancel."""

    @staticmethod
    def _ctx(**kw):
        base = {"overlap_plan": {
            "eligible": True, "clip_node_id": "62",
            "unet_node_id": "66", "forward_node_id": "67",
            "deferral_allowed": True},
            "overlap_unet_spec": {
                "node_id": "66", "unet_name": "z.safetensors"}}
        base.update(kw)
        return base

    def test_match_ticket(self):
        class _T:
            def done(self):
                return False

        good = {"path": "/m/u.safetensors", "task": _T()}
        assert ggl._match_unet_ticket(good, "/m/u.safetensors") is True
        assert ggl._match_unet_ticket(good, "/m/other.safetensors") is False
        # A finished ticket is accepted: joining a completed read is free,
        # and a failed one raises into the stage's existing fallback.
        done = {"path": "/m/u.safetensors",
                "task": type("D", (), {"done": lambda self: True})()}
        assert ggl._match_unet_ticket(done, "/m/u.safetensors") is True
        for bad in (None, [], "x", {}, {"path": "/m/u.safetensors"}):
            assert ggl._match_unet_ticket(bad, "/m/u.safetensors") is False
        assert ggl._match_unet_ticket(good, None) is False

    def test_launch_rejections_never_raise(self):
        assert ggl._overlap_launch_unet_load({})["started"] is False
        assert ggl._overlap_launch_unet_load(None)["started"] is False
        noplan = {"overlap_plan": {"eligible": False}}
        assert ggl._overlap_launch_unet_load(noplan)["started"] is False
        nospec = {"overlap_plan": {"eligible": True},
                  "overlap_unet_spec": {"node_id": "66",
                                        "unet_name": None}}
        assert ggl._overlap_launch_unet_load(nospec)["started"] is False

    def test_launch_no_running_loop(self, monkeypatch):
        active = self._ctx()
        monkeypatch.setattr(
            ggl, "_default_path_resolver", lambda _f, _n: "/m/u.safetensors")
        out = ggl._overlap_launch_unet_load(active)
        assert out["started"] is False
        assert out["reason"] == "no_running_loop"
        assert "unet_ticket" not in active

    def test_launch_starts_ticket(self, monkeypatch):
        import asyncio as _asyncio
        import sys as _sys
        import types as _types

        seen = {}

        class _Transport:
            async def load(self, path, role=None):
                seen["path"] = path
                seen["role"] = role
                return {"views": "V"}

        fake_mod = _types.ModuleType(
            "comfymodal_runtime.golden_model_transport")
        setattr(fake_mod, "get_golden_model_transport",
                lambda: _Transport())
        monkeypatch.setitem(
            _sys.modules,
            "comfymodal_runtime.golden_model_transport", fake_mod)
        monkeypatch.setattr(
            ggl, "_default_path_resolver", lambda _f, _n: "/m/u.safetensors")
        active = self._ctx()

        async def _drive():
            return ggl._overlap_launch_unet_load(active)

        out = _asyncio.run(_drive())
        assert out["started"] is True
        ticket = active.get("unet_ticket")
        assert isinstance(ticket, dict)
        assert ticket["path"] == "/m/u.safetensors"

        async def _join():
            return await ticket["task"]

        assert _asyncio.run(_join()) == {"views": "V"}
        assert seen == {"path": "/m/u.safetensors", "role": "unet"}
        # Second launch refuses (ticket exists).
        out2 = _asyncio.run(_drive())
        assert out2["started"] is False
        assert out2["reason"] == "ticket_already_exists"

    def test_launch_transport_unavailable(self, monkeypatch):
        import asyncio as _asyncio
        import sys as _sys
        import types as _types

        fake_mod = _types.ModuleType(
            "comfymodal_runtime.golden_model_transport")
        setattr(fake_mod, "get_golden_model_transport", lambda: None)
        monkeypatch.setitem(
            _sys.modules,
            "comfymodal_runtime.golden_model_transport", fake_mod)
        monkeypatch.setattr(
            ggl, "_default_path_resolver", lambda _f, _n: "/m/u.safetensors")
        active = self._ctx()

        async def _drive():
            return ggl._overlap_launch_unet_load(active)

        out = _asyncio.run(_drive())
        assert out["started"] is False
        assert out["reason"] == "transport_unavailable"

    def test_restore_cancels_pending_ticket(self, monkeypatch):
        calls = []
        _install_fake_execution(monkeypatch, calls)
        monkeypatch.setenv("COMFYMODAL_V2_GENERIC_OVERLAP", "1")
        wf = TestGenericOverlapPlan._zit_workflow()
        sink = []
        restore = None
        try:
            restore = ggl.install_execution_dispatch_substitution(
                role_bindings=TestGenericOverlapPlan._zit_bindings(),
                holder=ggl.GenericLoaderHolder(),
                trace_emit=(lambda name, **kw: sink.append(
                    (name, kw.get("metadata", {})))),
                request_id="r1",
                workflow=wf,
            )
            assert restore is not None
            log = []

            class _Task:
                def done(self):
                    return False

                def cancel(self):
                    log.append("cancelled")

            stored = ggl._ACTIVE_DISPATCH_CTX
            assert stored is not None
            stored["unet_ticket"] = {"path": "/m/u.safetensors",
                                     "task": _Task()}
            restore()
            assert log == ["cancelled"]
            events = [n for n, _m in sink if n == "generic_overlap_plan"]
            assert events
        finally:
            monkeypatch.delenv("COMFYMODAL_V2_GENERIC_OVERLAP",
                               raising=False)

    def test_compose_accepts_ticket_kwarg(self):
        out = asyncio.run(ggl.compose_generic_unet_load(
            unet_filenames=[], folder="diffusion_models",
            request_id="r1", unet_ticket={"path": "x"}))
        assert out["ok"] is False
        assert out["reason"] == "unet_filenames_missing"


class TestOverlapClipTicket:
    """Early CLIP load ticket: launch, match, join-handoff, restore-cancel."""

    @staticmethod
    def _ctx(**kw):
        base = {"overlap_plan": {
            "eligible": True, "clip_node_id": "62",
            "unet_node_id": "66", "forward_node_id": "67",
            "deferral_allowed": True},
            "overlap_clip_spec": {
                "node_id": "62", "clip_name": "qwen.safetensors"},
            "deployment_identity": {
                "deployment_combined_hash": "dep",
                "custom_nodes_generation": "gen"}}
        base.update(kw)
        return base

    def test_match_ticket(self):
        class _T:
            def done(self):
                return False

        good = {"path": "/m/qwen.safetensors", "task": _T()}
        assert ggl._match_clip_ticket(good, "/m/qwen.safetensors") is True
        assert ggl._match_clip_ticket(good, "/m/other.safetensors") is False
        # A finished ticket is accepted: joining a completed read is free
        # (the early read winning its race is the normal case), and a
        # failed one raises into the stage's existing fallback.
        done = {"path": "/m/qwen.safetensors",
                "task": type("D", (), {"done": lambda self: True})()}
        assert ggl._match_clip_ticket(done, "/m/qwen.safetensors") is True
        for bad in (None, [], "x", {}, {"path": "/m/qwen.safetensors"}):
            assert ggl._match_clip_ticket(bad, "/m/qwen.safetensors") is False
        assert ggl._match_clip_ticket(good, None) is False

    def test_launch_rejections_never_raise(self):
        assert ggl._overlap_launch_clip_load({})["started"] is False
        assert ggl._overlap_launch_clip_load(None)["started"] is False
        noplan = {"overlap_plan": {"eligible": False}}
        assert ggl._overlap_launch_clip_load(noplan)["started"] is False
        nospec = {"overlap_plan": {"eligible": True, "clip_node_id": "62"},
                  "overlap_clip_spec": {"node_id": "62", "clip_name": None},
                  "deployment_identity": {"deployment_combined_hash": "d",
                                           "custom_nodes_generation": "g"}}
        assert ggl._overlap_launch_clip_load(nospec)["started"] is False
        assert ggl._overlap_launch_clip_load(nospec)["reason"] == "clip_filename_unresolved"
        nodeploy = {"overlap_plan": {"eligible": True, "clip_node_id": "62"},
                    "overlap_clip_spec": {"node_id": "62", "clip_name": "q.safetensors"}}
        out = ggl._overlap_launch_clip_load(nodeploy)
        assert out["started"] is False
        assert out["reason"] == "deployment_identity_incomplete"

    def test_launch_no_running_loop(self, monkeypatch):
        active = self._ctx()
        monkeypatch.setattr(
            ggl, "_default_path_resolver", lambda _f, _n: "/m/qwen.safetensors")
        out = ggl._overlap_launch_clip_load(active)
        assert out["started"] is False
        assert out["reason"] == "no_running_loop"
        assert "clip_ticket" not in active

    def test_launch_starts_ticket(self, monkeypatch):
        import sys as _sys
        import types as _types

        seen = {}

        class _Transport:
            async def load(self, path, role=None):
                seen["path"] = path
                seen["role"] = role
                return {"views": "V"}

        fake_mod = _types.ModuleType(
            "comfymodal_runtime.golden_model_transport")
        setattr(fake_mod, "get_golden_model_transport",
                lambda: _Transport())
        monkeypatch.setitem(
            _sys.modules,
            "comfymodal_runtime.golden_model_transport", fake_mod)
        monkeypatch.setattr(
            ggl, "_default_path_resolver", lambda _f, _n: "/m/qwen.safetensors")
        active = self._ctx()

        async def _drive():
            return ggl._overlap_launch_clip_load(active)

        out = asyncio.run(_drive())
        assert out["started"] is True
        ticket = active.get("clip_ticket")
        assert isinstance(ticket, dict)
        assert ticket["path"] == "/m/qwen.safetensors"

        async def _join():
            return await ticket["task"]

        assert asyncio.run(_join()) == {"views": "V"}
        assert seen == {"path": "/m/qwen.safetensors", "role": "clip"}
        # Second launch refuses (ticket exists).
        out2 = asyncio.run(_drive())
        assert out2["started"] is False
        assert out2["reason"] == "ticket_already_exists"

    def test_launch_transport_unavailable(self, monkeypatch):
        import sys as _sys
        import types as _types

        fake_mod = _types.ModuleType(
            "comfymodal_runtime.golden_model_transport")
        setattr(fake_mod, "get_golden_model_transport", lambda: None)
        monkeypatch.setitem(
            _sys.modules,
            "comfymodal_runtime.golden_model_transport", fake_mod)
        monkeypatch.setattr(
            ggl, "_default_path_resolver", lambda _f, _n: "/m/qwen.safetensors")
        active = self._ctx()

        async def _drive():
            return ggl._overlap_launch_clip_load(active)

        out = asyncio.run(_drive())
        assert out["started"] is False
        assert out["reason"] == "transport_unavailable"

    def test_install_launches_clip_ticket(self, monkeypatch):
        import sys as _sys
        import types as _types

        calls = []
        _install_fake_execution(monkeypatch, calls)
        monkeypatch.setenv("COMFYMODAL_V2_GENERIC_OVERLAP", "1")

        seen = {}

        class _Transport:
            async def load(self, path, role=None):
                seen["path"] = path
                seen["role"] = role
                return {"views": "V"}

        fake_mod = _types.ModuleType(
            "comfymodal_runtime.golden_model_transport")
        setattr(fake_mod, "get_golden_model_transport",
                lambda: _Transport())
        monkeypatch.setitem(
            _sys.modules,
            "comfymodal_runtime.golden_model_transport", fake_mod)
        monkeypatch.setattr(
            ggl, "_default_path_resolver",
            lambda _f, _n: "/m/qwen.safetensors")
        wf = TestGenericOverlapPlan._zit_workflow()
        sink = []
        restore = None
        try:

            async def _drive():
                return ggl.install_execution_dispatch_substitution(
                    role_bindings=TestGenericOverlapPlan._zit_bindings(),
                    holder=ggl.GenericLoaderHolder(),
                    trace_emit=(lambda name, **kw: sink.append(
                        (name, kw.get("metadata", {})))),
                    request_id="r1",
                    workflow=wf,
                    deployment_identity={
                        "deployment_combined_hash": "dep",
                        "custom_nodes_generation": "gen"},
                )

            restore = asyncio.run(_drive())
            assert restore is not None
            stored = ggl._ACTIVE_DISPATCH_CTX
            assert stored is not None
            assert stored["overlap_clip_spec"]["clip_name"] == "qwen.safetensors"
            ticket = stored.get("clip_ticket")
            assert isinstance(ticket, dict)
            assert ticket["path"] == "/m/qwen.safetensors"
            assert seen == {"path": "/m/qwen.safetensors", "role": "clip"}
            launches = [n for n, _m in sink if n == "generic_overlap_clip_launch"]
            assert launches
            restore()
        finally:
            monkeypatch.delenv("COMFYMODAL_V2_GENERIC_OVERLAP",
                               raising=False)

    def test_install_without_deployment_identity_launches_nothing(self, monkeypatch):
        calls = []
        _install_fake_execution(monkeypatch, calls)
        monkeypatch.setenv("COMFYMODAL_V2_GENERIC_OVERLAP", "1")
        monkeypatch.setattr(
            ggl, "_default_path_resolver",
            lambda _f, _n: (_ for _ in ()).throw(AssertionError("must not resolve")))
        wf = TestGenericOverlapPlan._zit_workflow()
        sink = []
        restore = None
        try:

            async def _drive():
                return ggl.install_execution_dispatch_substitution(
                    role_bindings=TestGenericOverlapPlan._zit_bindings(),
                    holder=ggl.GenericLoaderHolder(),
                    trace_emit=(lambda name, **kw: sink.append(
                        (name, kw.get("metadata", {})))),
                    request_id="r1",
                    workflow=wf,
                )

            restore = asyncio.run(_drive())
            assert restore is not None
            stored = ggl._ACTIVE_DISPATCH_CTX
            assert stored is not None
            assert "clip_ticket" not in stored
            restore()
        finally:
            monkeypatch.delenv("COMFYMODAL_V2_GENERIC_OVERLAP",
                               raising=False)

    def test_restore_cancels_pending_clip_ticket(self, monkeypatch):
        calls = []
        _install_fake_execution(monkeypatch, calls)
        monkeypatch.setenv("COMFYMODAL_V2_GENERIC_OVERLAP", "1")
        wf = TestGenericOverlapPlan._zit_workflow()
        sink = []
        restore = None
        try:
            restore = ggl.install_execution_dispatch_substitution(
                role_bindings=TestGenericOverlapPlan._zit_bindings(),
                holder=ggl.GenericLoaderHolder(),
                trace_emit=(lambda name, **kw: sink.append(
                    (name, kw.get("metadata", {})))),
                request_id="r1",
                workflow=wf,
            )
            assert restore is not None
            log = []

            class _Task:
                def done(self):
                    return False

                def cancel(self):
                    log.append("cancelled")

            stored = ggl._ACTIVE_DISPATCH_CTX
            assert stored is not None
            stored["clip_ticket"] = {"path": "/m/qwen.safetensors",
                                      "task": _Task()}
            restore()
            assert log == ["cancelled"]
        finally:
            monkeypatch.delenv("COMFYMODAL_V2_GENERIC_OVERLAP",
                               raising=False)


class TestOverlapVaeTicket:
    """Early VAE load ticket: launch at sampler dispatch, match, cancel."""

    @staticmethod
    def _ctx(**kw):
        base = {"overlap_plan": {
            "eligible": True, "clip_node_id": "62",
            "unet_node_id": "66", "forward_node_id": "67",
            "deferral_allowed": True},
            "overlap_vae_spec": {
                "node_id": "1277", "vae_name": "ae.safetensors"},
            "deployment_identity": {
                "deployment_combined_hash": "dep",
                "custom_nodes_generation": "gen"}}
        base.update(kw)
        return base

    @staticmethod
    def _sampler(obj_name="ClownsharKSampler_Beta"):
        # Dispatch-time inputs carry resolved objects (the executor resolves
        # links before get_output_data); the model is a patcher-like object.
        _patcher = type("OverlapPatcher", (), {"model_options": {}})()
        return type(obj_name, (), {})(), {"model": [_patcher]}

    def test_match_ticket(self):
        class _T:
            def done(self):
                return False

        good = {"path": "/m/ae.safetensors", "task": _T()}
        assert ggl._match_vae_ticket(good, "/m/ae.safetensors") is True
        assert ggl._match_vae_ticket(good, "/m/other.safetensors") is False
        # A finished ticket is accepted: joining a completed read is free
        # (the read winning the sampling race is the normal case), and a
        # failed one raises into the stage's existing fallback.
        done = {"path": "/m/ae.safetensors",
                "task": type("D", (), {"done": lambda self: True})()}
        assert ggl._match_vae_ticket(done, "/m/ae.safetensors") is True
        for bad in (None, [], "x", {}, {"path": "/m/ae.safetensors"}):
            assert ggl._match_vae_ticket(bad, "/m/ae.safetensors") is False
        assert ggl._match_vae_ticket(good, None) is False

    def test_launch_rejections_never_raise(self):
        assert ggl._overlap_launch_vae_load({})["started"] is False
        assert ggl._overlap_launch_vae_load(None)["started"] is False
        noplan = {"overlap_plan": {"eligible": False}}
        assert ggl._overlap_launch_vae_load(noplan)["started"] is False
        nospec = {"overlap_plan": {"eligible": True},
                  "overlap_vae_spec": {"node_id": "1277", "vae_name": None},
                  "deployment_identity": {"deployment_combined_hash": "d",
                                           "custom_nodes_generation": "g"}}
        out = ggl._overlap_launch_vae_load(nospec)
        assert out["started"] is False
        assert out["reason"] == "vae_filename_unresolved"
        nodeploy = {"overlap_plan": {"eligible": True},
                    "overlap_vae_spec": {"node_id": "1277",
                                         "vae_name": "ae.safetensors"}}
        out2 = ggl._overlap_launch_vae_load(nodeploy)
        assert out2["started"] is False
        assert out2["reason"] == "deployment_identity_incomplete"

    def test_launch_no_running_loop(self, monkeypatch):
        active = self._ctx()
        monkeypatch.setattr(
            ggl, "_default_path_resolver", lambda _f, _n: "/m/ae.safetensors")
        out = ggl._overlap_launch_vae_load(active)
        assert out["started"] is False
        assert out["reason"] == "no_running_loop"
        assert "vae_ticket" not in active

    def test_launch_starts_ticket_with_stage_identical_call(self, monkeypatch):
        import sys as _sys
        import types as _types

        seen = {}

        class _Transport:
            async def load(self, path, role=None):
                seen["path"] = path
                seen["role"] = role
                return {"views": "V"}

        fake_mod = _types.ModuleType(
            "comfymodal_runtime.golden_model_transport")
        setattr(fake_mod, "get_golden_model_transport",
                lambda: _Transport())
        monkeypatch.setitem(
            _sys.modules,
            "comfymodal_runtime.golden_model_transport", fake_mod)
        monkeypatch.setattr(
            ggl, "_default_path_resolver", lambda _f, _n: "/m/ae.safetensors")
        active = self._ctx()

        async def _drive():
            return ggl._overlap_launch_vae_load(active)

        out = asyncio.run(_drive())
        assert out["started"] is True
        ticket = active.get("vae_ticket")
        assert isinstance(ticket, dict)
        assert ticket["path"] == "/m/ae.safetensors"

        async def _join():
            return await ticket["task"]

        assert asyncio.run(_join()) == {"views": "V"}
        # Identical to golden_vae_load's own call (no role override).
        assert seen == {"path": "/m/ae.safetensors", "role": None}
        out2 = asyncio.run(_drive())
        assert out2["started"] is False
        assert out2["reason"] == "ticket_already_exists"

    def test_launch_transport_unavailable(self, monkeypatch):
        import sys as _sys
        import types as _types

        fake_mod = _types.ModuleType(
            "comfymodal_runtime.golden_model_transport")
        setattr(fake_mod, "get_golden_model_transport", lambda: None)
        monkeypatch.setitem(
            _sys.modules,
            "comfymodal_runtime.golden_model_transport", fake_mod)
        monkeypatch.setattr(
            ggl, "_default_path_resolver", lambda _f, _n: "/m/ae.safetensors")
        active = self._ctx()

        async def _drive():
            return ggl._overlap_launch_vae_load(active)

        out = asyncio.run(_drive())
        assert out["started"] is False
        assert out["reason"] == "transport_unavailable"

    def test_maybe_launch_fires_only_on_sampler(self):
        obj, inputs = self._sampler()
        out = ggl._overlap_maybe_launch_vae_on_dispatch(
            {"overlap_plan": {"eligible": False}}, obj, inputs)
        assert isinstance(out, dict) and out["started"] is False

        _loader = type("CLIPLoader", (), {})()
        assert ggl._overlap_maybe_launch_vae_on_dispatch(
            self._ctx(), _loader, {"clip_name": ["q.safetensors"]}) is None
        noctx = ggl._overlap_maybe_launch_vae_on_dispatch(None, obj, inputs)
        assert isinstance(noctx, dict) and noctx["started"] is False

    def test_maybe_launch_skips_already_dispatched_vae(self):
        # Early-VAE workflows dispatch the VAE node before the sampler:
        # launching then would only burn a read that teardown cancels.
        obj, inputs = self._sampler()
        active = self._ctx()
        active["dispatched_nodes"] = {"62", "1277", "66"}
        out = ggl._overlap_maybe_launch_vae_on_dispatch(active, obj, inputs)
        assert isinstance(out, dict)
        assert out["started"] is False
        assert out["reason"] == "vae_already_dispatched"
        assert "vae_ticket" not in active

    def test_launch_refuses_while_unet_inflight(self):
        # The shared transport serves a single generation at a time:
        # a pending UNET read blocks the VAE launch (fail closed, the
        # VAE stage reads synchronously as before).
        class _Pending:
            def done(self):
                return False

        active = self._ctx()
        active["unet_ticket"] = {"path": "/m/z.safetensors", "task": _Pending()}
        out = ggl._overlap_launch_vae_load(active)
        assert out["started"] is False
        assert out["reason"] == "transport_busy_unet_inflight"
        assert "vae_ticket" not in active

    def test_launch_proceeds_once_unet_done(self, monkeypatch):
        import sys as _sys
        import types as _types

        class _Done:
            def done(self):
                return True

        fake_mod = _types.ModuleType(
            "comfymodal_runtime.golden_model_transport")
        setattr(fake_mod, "get_golden_model_transport", lambda: None)
        monkeypatch.setitem(
            _sys.modules,
            "comfymodal_runtime.golden_model_transport", fake_mod)
        monkeypatch.setattr(
            ggl, "_default_path_resolver", lambda _f, _n: "/m/ae.safetensors")
        active = self._ctx()
        active["unet_ticket"] = {"path": "/m/z.safetensors", "task": _Done()}

        async def _drive():
            return ggl._overlap_launch_vae_load(active)

        import asyncio as _asyncio
        out = _asyncio.run(_drive())
        # Done UNET task: gate passes, launch continues to transport
        # resolution (unavailable here) instead of refusing as busy.
        assert out["started"] is False
        assert out["reason"] == "transport_unavailable"

    def test_install_builds_vae_spec(self, monkeypatch):
        calls = []
        _install_fake_execution(monkeypatch, calls)
        monkeypatch.setenv("COMFYMODAL_V2_GENERIC_OVERLAP", "1")
        wf = TestGenericOverlapPlan._zit_workflow(extra={
            "1277": {"class_type": "VAELoader",
                     "inputs": {"vae_name": "ae.safetensors"}}})
        bindings = dict(TestGenericOverlapPlan._zit_bindings())
        bindings["vae"] = {"node_id": "1277", "input_name": "vae_name"}
        sink = []
        restore = None
        try:
            restore = ggl.install_execution_dispatch_substitution(
                role_bindings=bindings,
                holder=ggl.GenericLoaderHolder(),
                trace_emit=(lambda name, **kw: sink.append(
                    (name, kw.get("metadata", {})))),
                request_id="r1",
                workflow=wf,
                deployment_identity={
                    "deployment_combined_hash": "dep",
                    "custom_nodes_generation": "gen"},
            )
            assert restore is not None
            stored = ggl._ACTIVE_DISPATCH_CTX
            assert stored is not None
            assert stored["overlap_vae_spec"] == {
                "node_id": "1277", "vae_name": "ae.safetensors"}
            restore()
        finally:
            monkeypatch.delenv("COMFYMODAL_V2_GENERIC_OVERLAP",
                               raising=False)

    def test_restore_cancels_pending_vae_ticket(self, monkeypatch):
        calls = []
        _install_fake_execution(monkeypatch, calls)
        monkeypatch.setenv("COMFYMODAL_V2_GENERIC_OVERLAP", "1")
        wf = TestGenericOverlapPlan._zit_workflow()
        sink = []
        restore = None
        try:
            restore = ggl.install_execution_dispatch_substitution(
                role_bindings=TestGenericOverlapPlan._zit_bindings(),
                holder=ggl.GenericLoaderHolder(),
                trace_emit=(lambda name, **kw: sink.append(
                    (name, kw.get("metadata", {})))),
                request_id="r1",
                workflow=wf,
            )
            assert restore is not None
            log = []

            class _Task:
                def done(self):
                    return False

                def cancel(self):
                    log.append("cancelled")

            stored = ggl._ACTIVE_DISPATCH_CTX
            assert stored is not None
            stored["vae_ticket"] = {"path": "/m/ae.safetensors",
                                    "task": _Task()}
            restore()
            assert log == ["cancelled"]
        finally:
            monkeypatch.delenv("COMFYMODAL_V2_GENERIC_OVERLAP",
                               raising=False)
