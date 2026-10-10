"""Focused tests for generic Golden-loader composition (no GPU, no Modal).

Covers the pure orchestration logic: loader classification, owner-holder
lifecycle, cache-entry insertion mechanics, and the per-workflow compose
loop with strict native fallback.  Golden cores themselves are exercised
live, never here.
"""

from __future__ import annotations

import asyncio
import sys
import types

import pytest

from comfymodal_runtime import golden_generic_loaders as ggl


pytestmark = pytest.mark.fast_unit


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

class TestClassifyLoaderNode:
    def test_cliploader_supported(self):
        result = classify_loader_node(
            "CLIPLoader",
            {"clip_name": "qwen.safetensors", "type": "krea2", "device": "default"},
        ) if False else ggl.classify_loader_node(
            "CLIPLoader",
            {"clip_name": "qwen.safetensors", "type": "krea2", "device": "default"},
        )
        assert result["supported"] is True
        assert result["role"] == "clip"
        assert result["clip_name"] == "qwen.safetensors"
        assert result["clip_type"] == "krea2"

    def test_cliploader_missing_name_unsupported(self):
        result = ggl.classify_loader_node("CLIPLoader", {"type": "krea2"})
        assert result["supported"] is False
        assert result["reason"] == "clip_name_missing"

    def test_cliploader_explicit_cpu_respected(self):
        result = ggl.classify_loader_node(
            "CLIPLoader", {"clip_name": "qwen.safetensors", "device": "cpu"}
        )
        assert result["supported"] is False
        assert result["reason"] == "explicit_cpu_device_respected"

    def test_dual_clip_deferred(self):
        result = ggl.classify_loader_node(
            "DualCLIPLoader", {"clip_name1": "a.safetensors", "clip_name2": "b.safetensors"}
        )
        assert result["supported"] is False
        assert result["reason"] == "dual_clip_deferred"

    def test_vae_deferred(self):
        result = ggl.classify_loader_node("VAELoader", {"vae_name": "v.safetensors"})
        assert result["supported"] is False
        assert result["reason"] == "vae_deferred"

    def test_unet_deferred(self):
        result = ggl.classify_loader_node("UNETLoader", {"unet_name": "u.safetensors"})
        assert result["supported"] is False
        assert result["reason"] == "unet_deferred"

    def test_checkpoint_unsupported(self):
        result = ggl.classify_loader_node("CheckpointLoaderSimple", {"ckpt_name": "c.safetensors"})
        assert result["supported"] is False
        assert result["reason"] == "checkpoint_not_role_separable"

    def test_unknown_class_unsupported(self):
        result = ggl.classify_loader_node("MysteryNode", {"x": 1})
        assert result["supported"] is False
        assert result["reason"] == "unknown_loader_class"

    def test_non_dict_inputs_tolerated(self):
        result = ggl.classify_loader_node("CLIPLoader", None)
        assert result["supported"] is False


# ---------------------------------------------------------------------------
# Owner holder lifecycle
# ---------------------------------------------------------------------------

class _OwnerWithRelease:
    def __init__(self):
        self.released = False

    def release_storage(self):
        self.released = True


class _OwnerWithCloseOnly:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _OwnerExploding:
    def release_storage(self):
        raise RuntimeError("boom")


class TestGenericLoaderHolder:
    def test_close_releases_and_is_idempotent(self):
        holder = ggl.GenericLoaderHolder()
        owner = _OwnerWithRelease()
        holder.retain(object(), [owner])
        first = holder.close()
        assert first["released"] == 1
        assert first["errors"] == 0
        assert owner.released is True
        second = holder.close()
        assert second.get("already_closed") is True

    def test_close_falls_back_to_close_method(self):
        holder = ggl.GenericLoaderHolder()
        owner = _OwnerWithCloseOnly()
        holder.retain(None, [owner])
        result = holder.close()
        assert result["released"] == 1
        assert owner.closed is True

    def test_close_counts_errors_without_raising(self):
        holder = ggl.GenericLoaderHolder()
        holder.retain(None, [_OwnerExploding()])
        result = holder.close()
        assert result["released"] == 0
        assert result["errors"] == 1


# ---------------------------------------------------------------------------
# Cache insertion mechanics (fake executor cache, no ComfyUI needed)
# ---------------------------------------------------------------------------

class _FakeCache:
    def __init__(self, keys):
        self._keys = dict(keys)
        self._store = {}

    async def get(self, node_id):
        return self._store.get(str(node_id))

    async def set(self, node_id, entry):
        self._store[str(node_id)] = entry


class _FakeKeySet:
    def __init__(self, keys):
        self._keys = set(keys)

    def get_data_key(self, node_id):
        return "key" if str(node_id) in self._keys else None


class _FakeCacheEntry:
    def __init__(self, ui=None, outputs=None):
        self.ui = ui or {}
        self.outputs = outputs or []


def _install_fake_execution(monkeypatch):
    fake = types.ModuleType("execution")
    setattr(fake, "CacheEntry", _FakeCacheEntry)
    monkeypatch.setitem(sys.modules, "execution", fake)


class TestCacheInsertion:
    def test_cache_entry_none_without_execution_module(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "execution", raising=False)
        assert ggl._cache_entry_for(object()) is None

    def test_insert_verified(self, monkeypatch):
        _install_fake_execution(monkeypatch)
        cache = _FakeCache({})
        keys = _FakeKeySet({"7"})
        result = asyncio.run(ggl.insert_loader_cache_entry(cache, keys, "7", object()))
        assert result["decision"] == "seeded"

    def test_insert_missing_key(self, monkeypatch):
        _install_fake_execution(monkeypatch)
        cache = _FakeCache({})
        keys = _FakeKeySet(set())
        result = asyncio.run(ggl.insert_loader_cache_entry(cache, keys, "7", object()))
        assert result["decision"] == "cache_key_missing"


# ---------------------------------------------------------------------------
# Per-workflow compose loop (composer monkeypatched; no GPU)
# ---------------------------------------------------------------------------

def _workflow():
    return {
        "195": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": "qwen.safetensors", "type": "krea2"},
        },
        "199": {"class_type": "PixaromaPreview", "inputs": {}},
    }


class TestComposeLoop:
    def test_unknown_nodes_ignored(self, monkeypatch):
        _install_fake_execution(monkeypatch)
        holder = ggl.GenericLoaderHolder()
        results = asyncio.run(ggl.compose_loaders_for_workflow(
            workflow={"1": {"class_type": "KSampler", "inputs": {}}},
            outputs_cache=_FakeCache({}),
            cache_key_set=_FakeKeySet(set()),
            holder=holder,
            request_id="r1",
        ))
        assert results == {}

    def test_compose_success_seeds_cache(self, monkeypatch):
        _install_fake_execution(monkeypatch)

        async def fake_compose(**kwargs):
            return {"ok": True, "clip": object(), "session": object(),
                    "owners": [], "elapsed_ms": 1.0, "reason": ""}

        monkeypatch.setattr(ggl, "compose_generic_clip_load", fake_compose)
        holder = ggl.GenericLoaderHolder()
        cache = _FakeCache({})
        results = asyncio.run(ggl.compose_loaders_for_workflow(
            workflow=_workflow(),
            outputs_cache=cache,
            cache_key_set=_FakeKeySet({"195"}),
            holder=holder,
            request_id="r1",
        ))
        assert results["195"]["actual"] == "shared_core"
        assert asyncio.run(cache.get("195")) is not None

    def test_compose_failure_falls_back_native(self, monkeypatch):
        _install_fake_execution(monkeypatch)

        async def fake_compose(**kwargs):
            return {"ok": False, "reason": "scaled_fp8_rejected", "elapsed_ms": 1.0}

        monkeypatch.setattr(ggl, "compose_generic_clip_load", fake_compose)
        holder = ggl.GenericLoaderHolder()
        cache = _FakeCache({})
        results = asyncio.run(ggl.compose_loaders_for_workflow(
            workflow=_workflow(),
            outputs_cache=cache,
            cache_key_set=_FakeKeySet({"195"}),
            holder=holder,
            request_id="r1",
        ))
        assert results["195"]["actual"] == "native"
        assert "scaled_fp8_rejected" in results["195"]["reason"]
        assert asyncio.run(cache.get("195")) is None

    def test_cache_hit_skips_compose(self, monkeypatch):
        _install_fake_execution(monkeypatch)
        calls = []

        async def fake_compose(**kwargs):
            calls.append(kwargs)
            raise AssertionError("must not compose on cache hit")

        monkeypatch.setattr(ggl, "compose_generic_clip_load", fake_compose)
        holder = ggl.GenericLoaderHolder()
        cache = _FakeCache({})
        asyncio.run(cache.set("195", _FakeCacheEntry()))
        results = asyncio.run(ggl.compose_loaders_for_workflow(
            workflow=_workflow(),
            outputs_cache=cache,
            cache_key_set=_FakeKeySet({"195"}),
            holder=holder,
            request_id="r1",
        ))
        assert results["195"]["actual"] == "cache_hit"
        assert calls == []


# ---------------------------------------------------------------------------
# Arm ordering: QD4 demand first, M2 singleton second, native fallback
# ---------------------------------------------------------------------------

class TestArmOrdering:
    def test_qd4_success_skips_m2(self, monkeypatch):
        _install_fake_execution(monkeypatch)
        m2_calls = []

        async def fake_qd4(**kwargs):
            return {"ok": True, "clip": object(), "session": None,
                    "owners": [], "elapsed_ms": 2.0, "reason": "",
                    "source_arm": "qd4_demand"}

        async def fake_m2(**kwargs):
            m2_calls.append(kwargs)
            raise AssertionError("M2 must not run after QD4 success")

        monkeypatch.setattr(ggl, "compose_generic_clip_load_qd4", fake_qd4)
        monkeypatch.setattr(ggl, "compose_generic_clip_load", fake_m2)
        holder = ggl.GenericLoaderHolder()
        cache = _FakeCache({})
        results = asyncio.run(ggl.compose_loaders_for_workflow(
            workflow=_workflow(),
            outputs_cache=cache,
            cache_key_set=_FakeKeySet({"195"}),
            holder=holder,
            request_id="r1",
        ))
        assert results["195"]["actual"] == "shared_core"
        assert results["195"]["source_arm"] == "qd4_demand"
        assert m2_calls == []
        assert asyncio.run(cache.get("195")) is not None

    def test_qd4_failure_falls_back_to_m2(self, monkeypatch):
        _install_fake_execution(monkeypatch)
        m2_calls = []

        async def fake_qd4(**kwargs):
            return {"ok": False, "reason": "qd4_gate_disabled",
                    "elapsed_ms": 0.5, "source_arm": "qd4_demand"}

        async def fake_m2(**kwargs):
            m2_calls.append(kwargs)
            return {"ok": True, "clip": object(), "session": object(),
                    "owners": [], "elapsed_ms": 3.0, "reason": ""}

        monkeypatch.setattr(ggl, "compose_generic_clip_load_qd4", fake_qd4)
        monkeypatch.setattr(ggl, "compose_generic_clip_load", fake_m2)
        holder = ggl.GenericLoaderHolder()
        cache = _FakeCache({})
        results = asyncio.run(ggl.compose_loaders_for_workflow(
            workflow=_workflow(),
            outputs_cache=cache,
            cache_key_set=_FakeKeySet({"195"}),
            holder=holder,
            request_id="r1",
        ))
        assert results["195"]["actual"] == "shared_core"
        assert results["195"]["source_arm"] == "m2_transport"
        assert len(m2_calls) == 1

    def test_both_arms_fail_falls_back_native_with_combined_reason(
        self, monkeypatch
    ):
        _install_fake_execution(monkeypatch)

        async def fake_qd4(**kwargs):
            return {"ok": False, "reason": "qd4_gate_disabled",
                    "elapsed_ms": 0.5, "source_arm": "qd4_demand"}

        async def fake_m2(**kwargs):
            return {"ok": False, "reason": "PoolPoisonedError:cancelled",
                    "elapsed_ms": 1.0}

        monkeypatch.setattr(ggl, "compose_generic_clip_load_qd4", fake_qd4)
        monkeypatch.setattr(ggl, "compose_generic_clip_load", fake_m2)
        holder = ggl.GenericLoaderHolder()
        cache = _FakeCache({})
        results = asyncio.run(ggl.compose_loaders_for_workflow(
            workflow=_workflow(),
            outputs_cache=cache,
            cache_key_set=_FakeKeySet({"195"}),
            holder=holder,
            request_id="r1",
        ))
        assert results["195"]["actual"] == "native"
        assert "qd4_gate_disabled" in results["195"]["reason"]
        assert "PoolPoisonedError" in results["195"]["reason"]
        assert asyncio.run(cache.get("195")) is None
