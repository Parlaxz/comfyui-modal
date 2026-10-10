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
