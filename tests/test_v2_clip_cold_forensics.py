"""Batch D2 generic CLIP cold-path forensics tests.

Exercises the real ``ClipColdPathForensics`` instrumentation against
synthetic torch modules and mocked ModelPatcher/CLIP/conditioning-cache
paths — no real models, no remote calls, no comfy import required.

Test matrix (one class per scope):
  1. Identity capture (patcher/model/load/offload devices, dtype + device
     distributions, source files + checkpoint bytes, capabilities).
  2. Transfer accounting (bytes, op counts, histogram buckets, pinned vs
     pageable) under the per-op sub-flag.
  3. JSON-safety of every event + summary, and zero-overhead disabled no-op.
  4. Encode decomposition: tokenize / GPU-wait / encode / forward /
     post-forward walls, token + batch counts, encode call count.
  5. Conditioning-cache hit vs miss decision; miss drives a patcher load.
  6. Residency: load -> partial unload -> reload -> detach, multi-move
     detection, unload/free_memory/soft_empty_cache marks.
  7. Synchronize counting + cumulative sync wall under the sync sub-flag.
  8. Idempotent install and exact uninstall restore.
  9. Env-flag gating of the module-level install helper.
  10. install() with no usable targets never raises.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import torch

from comfymodal_runtime.clip_cold_path_forensics import (
    ClipColdPathForensics,
    cast_accounting_enabled,
    forensics_enabled,
    install_forensics_if_enabled,
    sync_cuda_enabled,
)
from comfymodal_runtime.trace import RuntimeTrace


# ═══════════════════════════════════════════════════════════════════════════
# Synthetic fixtures (real torch modules, mocked patcher paths)
# ═══════════════════════════════════════════════════════════════════════════


class _FakeModel(torch.nn.Module):
    """Small synthetic encoder with known parameter sizes (float16)."""

    def __init__(self) -> None:
        super().__init__()
        self.tiny = torch.nn.Parameter(torch.zeros(1_000, dtype=torch.float16))
        self.small = torch.nn.Parameter(torch.zeros(1_000_000, dtype=torch.float16))
        self.large = torch.nn.Parameter(torch.zeros(80_000_000, dtype=torch.float16))
        self.device = torch.device("cpu")
        self.model_loaded_weight_memory = 0
        self.model_offload_buffer_memory = 0
        self.model_lowvram = False

    def model_size(self) -> int:
        return sum(int(p.numel() * p.element_size()) for p in self.parameters())


class _FakePatcher:
    """Mock ModelPatcher: load transfers params, partial unload moves off."""

    def __init__(self, model: _FakeModel | None = None, *, load_delay_s: float = 0.01):
        self.model = model if model is not None else _FakeModel()
        self.load_device = torch.device("cuda:0")
        self.offload_device = torch.device("cpu")
        self.is_clip = True
        self.manual_cast_dtype = torch.float32
        self.force_cast_weights = True
        self._load_delay_s = load_delay_s
        self.cached_patcher_init: Any = None

    def is_dynamic(self) -> bool:
        return False

    def weight_dtype(self) -> torch.dtype:
        return torch.float16

    def model_size(self) -> int:
        return self.model.model_size()

    def load(self, device_to=None, lowvram_model_memory=0, force_patch_weights=False, full_load=False):
        time.sleep(self._load_delay_s)
        if full_load or device_to is None:
            device_to = self.load_device
        for name, param in self.model.named_parameters():
            self.patch_weight_to_device(name, device_to=device_to)
        self.model.device = device_to
        self.model.model_loaded_weight_memory = sum(
            int(p.numel() * p.element_size()) for p in self.model.parameters()
        )
        self.model.model_lowvram = False
        return self.model

    def partially_load(self, device_to=None, lowvram_model_memory=0):
        time.sleep(self._load_delay_s)
        self.model.device = device_to or self.load_device
        self.model.model_lowvram = True
        return self.model

    def patch_weight_to_device(self, key, device_to=None, inplace_update=False, return_weight=False, force_cast=False):
        weight = getattr(self.model, key, None)
        if weight is None:
            return weight
        if device_to is not None and str(device_to) != str(weight.device):
            weight = weight.to(device_to)
        return weight

    def partially_unload(self, device_to=None, memory_to_free=0):
        time.sleep(0.001)
        self.model.device = device_to or self.offload_device
        self.model.model_lowvram = True
        return memory_to_free

    def detach(self, unpatch_weights=True):
        return None


class _FakeCSM:
    """Mock cond_stage_model with a measurable encode_token_weights."""

    def __init__(self, forward_delay_s: float = 0.03):
        self._forward_delay_s = forward_delay_s

    def encode_token_weights(self, tokens):
        time.sleep(self._forward_delay_s)
        return (tokens, None)


class _FakeCLIP:
    """Mock CLIP: tokenize -> load_model -> forward, scheduled variant too."""

    def __init__(self, patcher: _FakePatcher | None = None, forward_delay_s: float = 0.03):
        self.patcher = patcher if patcher is not None else _FakePatcher()
        self.cond_stage_model = _FakeCSM(forward_delay_s=forward_delay_s)

    def tokenize(self, text):
        time.sleep(0.01)
        return {"l": [["a"], ["b"]]}

    def load_model(self, tokens={}):
        # Simulate the real ComfyUI path: CLIP.load_model -> load_models_gpu
        # -> patcher.load, so patcher-load attribution nests correctly.
        time.sleep(0.005)
        self.patcher.load(device_to=self.patcher.load_device, full_load=False)
        return self.patcher

    def encode_from_tokens(self, tokens, return_pooled=False, **kwargs):
        # Mirrors the real CLIPEncode node: tokenize first, then encode.
        self.tokenize("")
        self.load_model(tokens)
        cond, pooled = self.cond_stage_model.encode_token_weights(tokens)
        return [[cond, {"pooled_output": pooled}]]

    def encode_from_tokens_scheduled(self, tokens, **kwargs):
        self.tokenize("")
        self.load_model(tokens)
        cond, pooled = self.cond_stage_model.encode_token_weights(tokens)
        return [[cond, {"pooled_output": pooled}]]


class _FakeMM:
    """Mock comfy.model_management surface."""

    def __init__(self):
        self.load_models_gpu_calls = []

    def load_models_gpu(self, models, memory_required=0, force_patch_weights=False, **kwargs):
        self.load_models_gpu_calls.append(len(models))
        for model in models:
            if hasattr(model, "load"):
                model.load(device_to=getattr(model, "load_device", None), full_load=False)

    def free_memory(self, memory_required, device, keep_loaded=[], **kwargs):
        return memory_required

    def soft_empty_cache(self):
        return None

    def cast_to_device(self, tensor, device, dtype, copy=False):
        return tensor.to(device)


class _FakeCache:
    """Mock ExactConditioningCache.lookup_many with configurable verdict."""

    def __init__(self, hit_count: int = 0, miss_count: int = 0):
        self._hit_count = hit_count
        self._miss_count = miss_count

    def lookup_many(self, base_ctx, entries):
        hits = {i: ("value",) for i in range(self._hit_count)}
        misses = [dict(entry) for entry in (entries or [])[: self._miss_count]]
        return hits, misses, self._hit_count, self._miss_count


class _FakeTorch:
    """Mock torch module surface with a counted synchronize."""

    def __init__(self, sync_delay_s: float = 0.005):
        self.sync_calls = 0
        self._sync_delay_s = sync_delay_s

    def synchronize(self):
        self.sync_calls += 1
        time.sleep(self._sync_delay_s)


class _DecompositionTorch:
    """Fake CUDA operations with deterministic wall delays and ordering."""

    def __init__(self, *, fail_operation: str = ""):
        self.calls: list[str] = []
        self.fail_operation = fail_operation

    def _run(self, name: str, delay_s: float) -> None:
        self.calls.append(name)
        time.sleep(delay_s)
        if self.fail_operation == name:
            raise RuntimeError(f"{name} failed")

    def synchronize(self):
        self._run("synchronize", 0.1)

    def empty_cache(self):
        self._run("empty_cache", 0.2)

    def ipc_collect(self):
        self._run("ipc_collect", 0.3)


class _DecompositionMM(_FakeMM):
    def __init__(self, torch_mod: _DecompositionTorch):
        super().__init__()
        self._torch_mod = torch_mod

    def soft_empty_cache(self):
        self._torch_mod.synchronize()
        self._torch_mod.empty_cache()
        self._torch_mod.ipc_collect()


def _new_forensics(**kwargs) -> ClipColdPathForensics:
    kwargs.setdefault("enabled", True)
    return ClipColdPathForensics(**kwargs)


def _install_with_cleanup(
    testcase: unittest.TestCase,
    forensics: ClipColdPathForensics,
    targets: SimpleNamespace,
) -> dict[str, str]:
    """Install wrappers and guarantee uninstall after the test.

    The fake classes are module-level, so sentinel wrappers would leak
    across tests; cleanup restores the pristine classes for the next test.
    """
    statuses = forensics.install(targets=targets)
    testcase.addCleanup(forensics.uninstall)
    return statuses


def _targets(
    *, patcher: _FakePatcher | None = None, mm: _FakeMM | None = None,
    clip: _FakeCLIP | None = None, cache: _FakeCache | None = None,
    torch_mod: _FakeTorch | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        mm_module=mm if mm is not None else _FakeMM(),
        mp_class=_FakePatcher if patcher is None else type(patcher),
        sd_clip_class=_FakeCLIP if clip is None else type(clip),
        cache_class=_FakeCache if cache is None else type(cache),
        torch_module=torch_mod if torch_mod is not None else _FakeTorch(),
    )


def _events_by_name(forensics: ClipColdPathForensics) -> dict[str, list[dict]]:
    by_name: dict[str, list[dict]] = {}
    for event in forensics._events:
        by_name.setdefault(event["name"], []).append(event)
    return by_name


def _load_end_event(forensics: ClipColdPathForensics) -> dict | None:
    for event in reversed(forensics._events):
        if event["name"] == "clip_cold_patcher_load_end":
            return event
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 1. Identity capture
# ═══════════════════════════════════════════════════════════════════════════


class TestIdentityCapture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._path_a = Path(self._tmpdir.name, "clip_identity_a.safetensors")
        self._path_b = Path(self._tmpdir.name, "clip_identity_b.safetensors")
        self._path_a.write_bytes(b"x" * 1234)
        self._path_b.write_bytes(b"y" * 5678)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_identity_capture_on_patcher_load(self) -> None:
        patcher = _FakePatcher()
        patcher.cached_patcher_init = (
            lambda *a, **k: None,
            ([str(self._path_a), str(self._path_b)], "emb", "clip", {}),
        )
        targets = _targets(patcher=patcher)
        forensics = _new_forensics(request_id="id_req_1")
        forensics.begin_request("id_req_1")
        statuses = _install_with_cleanup(self, forensics, targets)
        self.assertEqual(statuses["patcher_load"], "installed")
        targets.mm_module.load_models_gpu([patcher])
        end = _load_end_event(forensics)
        self.assertIsNotNone(end, "patcher load end event missing")
        meta = end["metadata"]
        self.assertEqual(meta["clip_role"], "clip")
        self.assertEqual(meta["load_device"], "cuda:0")
        self.assertEqual(meta["offload_device"], "cpu")
        self.assertEqual(meta["patcher_dynamic"], False)
        self.assertEqual(meta["current_device"], "cuda:0")
        self.assertTrue(meta["model_class"].endswith("_FakeModel"))
        self.assertEqual(meta["stored_dtypes"].get("torch.float16"), 3)
        self.assertEqual(meta["device_distribution"], {"cpu": 3})
        self.assertEqual(meta["source_files"], ["clip_identity_a.safetensors", "clip_identity_b.safetensors"])
        self.assertEqual(meta["checkpoint_bytes"], 1234 + 5678)
        self.assertTrue(meta["recreatable_from_cpu_snapshot"])
        self.assertTrue(meta["capabilities"]["manual_cast_dtype"])
        self.assertTrue(meta["capabilities"]["force_cast_weights"])
        self.assertEqual(meta["capabilities"]["weight_dtype"], "torch.float16")
        self.assertEqual(meta["model_ready_wall_unix_ns"] > 0, True)
        self.assertEqual(meta["resident_before"], False)
        self.assertEqual(meta["already_resident_bytes"], 0)
        forensics.end_request()


# ═══════════════════════════════════════════════════════════════════════════
# 2. Transfer accounting (per-op sub-flag)
# ═══════════════════════════════════════════════════════════════════════════


class TestTransferAccounting(unittest.TestCase):
    def test_bytes_ops_histogram_pinned(self) -> None:
        patcher = _FakePatcher()
        targets = _targets(patcher=patcher)
        forensics = _new_forensics(
            request_id="xfer_req_1", cast_accounting=True, sync_cuda=False,
        )
        forensics.begin_request("xfer_req_1")
        statuses = _install_with_cleanup(self, forensics, targets)
        self.assertEqual(statuses["patch_weight_to_device"], "installed")
        targets.mm_module.load_models_gpu([patcher])
        end = _load_end_event(forensics)
        self.assertIsNotNone(end)
        meta = end["metadata"]
        # 3 params, each moved once.
        self.assertEqual(meta["transfer_ops"], 3)
        expected_bytes = sum(
            int(p.numel() * p.element_size()) for p in patcher.model.parameters()
        )
        self.assertEqual(meta["bytes_transferred"], expected_bytes)
        self.assertEqual(meta["total_model_bytes"], expected_bytes)
        hist = meta["histogram"]
        self.assertEqual(hist["tiny"]["count"], 1)   # 2 KB
        self.assertEqual(hist["small"]["count"], 1)  # 2 MB
        self.assertEqual(hist["large"]["count"], 1)  # 160 MB
        self.assertEqual(hist["medium"]["count"], 0)
        self.assertEqual(meta["pinned_count"] + meta["pageable_count"], 3)
        # Summary aggregates.
        summary = forensics.end_request()
        self.assertEqual(summary["total_transfer_ops"], 3)
        self.assertEqual(summary["total_h2d_bytes"], expected_bytes)
        self.assertEqual(summary["histogram"]["tiny"]["bytes"], 2000)

    def test_per_op_gated_off_by_default(self) -> None:
        patcher = _FakePatcher()
        targets = _targets(patcher=patcher)
        forensics = _new_forensics(request_id="xfer_req_2")
        statuses = _install_with_cleanup(self, forensics, targets)
        self.assertEqual(statuses["patch_weight_to_device"], "gated_off")
        targets.mm_module.load_models_gpu([patcher])
        end = _load_end_event(forensics)
        self.assertIsNotNone(end)
        # bytes still captured from model_loaded_weight_memory.
        expected = sum(
            int(p.numel() * p.element_size()) for p in patcher.model.parameters()
        )
        self.assertEqual(end["metadata"]["bytes_transferred"], expected)
        self.assertEqual(end["metadata"]["transfer_ops"], 0)


# ═══════════════════════════════════════════════════════════════════════════
# 3. JSON-safety + disabled no-op
# ═══════════════════════════════════════════════════════════════════════════


class TestJsonSafeAndDisabledNoop(unittest.TestCase):
    def test_all_events_and_summary_json_serializable(self) -> None:
        patcher = _FakePatcher()
        cache = _FakeCache(hit_count=0, miss_count=2)
        clip = _FakeCLIP(patcher=patcher)
        targets = _targets(patcher=patcher, cache=cache, clip=clip)
        forensics = _new_forensics(
            request_id="json_req_1", cast_accounting=True, sync_cuda=True,
        )
        forensics.begin_request("json_req_1")
        _install_with_cleanup(self, forensics, targets)
        targets.mm_module.load_models_gpu([patcher])
        clip.encode_from_tokens({"l": [["a"], ["b"]]})
        cache.lookup_many({}, [{"node": "1"}, {"node": "2"}])
        patcher.partially_unload(device_to="cpu", memory_to_free=100)
        patcher.detach()
        targets.mm_module.free_memory(100, torch.device("cuda:0"))
        targets.mm_module.soft_empty_cache()
        forensics.flush()  # must not raise
        summary = forensics.end_request()
        for event in summary["events"]:
            json.dumps(event)  # raises on non-serializable
        json.dumps(summary)
        self.assertIn("events", summary)
        self.assertTrue(summary["events"])

    def test_disabled_instance_is_zero_overhead(self) -> None:
        targets = _targets()
        original_load = targets.mm_module.load_models_gpu
        forensics = _new_forensics(enabled=False)
        statuses = forensics.install(targets=targets)
        self.assertEqual(statuses, {"status": "disabled"})
        self.assertIs(
            targets.mm_module.load_models_gpu.__func__,
            original_load.__func__,
        )
        summary = forensics.request_summary()
        self.assertIs(summary["enabled"], False)
        self.assertEqual(summary["request_id"], "")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Encode decomposition
# ═══════════════════════════════════════════════════════════════════════════


class TestEncodeDecomposition(unittest.TestCase):
    def _run_one_encode(self) -> tuple[ClipColdPathForensics, dict, dict]:
        patcher = _FakePatcher()
        clip = _FakeCLIP(patcher=patcher, forward_delay_s=0.03)
        targets = _targets(patcher=patcher, clip=clip)
        forensics = _new_forensics(request_id="enc_req_1")
        forensics.begin_request("enc_req_1")
        _install_with_cleanup(self, forensics, targets)
        result = clip.encode_from_tokens({"l": [["a"], ["b"]]})
        by_name = _events_by_name(forensics)
        encode_end = by_name["clip_cold_encode_end"][0]["metadata"]
        forward_end = by_name["clip_cold_forward_end"][0]["metadata"]
        return forensics, encode_end, forward_end

    def test_encode_decomposition_walls_and_counts(self) -> None:
        forensics, encode_end, forward_end = self._run_one_encode()
        self.assertIn("clip_cold_tokenize_end", _events_by_name(forensics))
        self.assertIn("clip_cold_gpu_wait_end", _events_by_name(forensics))
        self.assertGreater(encode_end["wall_ms"], 0)
        self.assertGreater(forward_end["wall_ms"], 0)
        self.assertGreaterEqual(encode_end["forward_wall_ms"], 0)
        self.assertGreaterEqual(encode_end["post_forward_ms"], 0)
        self.assertEqual(encode_end["token_count"], 2)
        self.assertEqual(encode_end["batch_count"], 2)
        self.assertEqual(encode_end["encode_index"], 1)
        self.assertEqual(encode_end["clip_role"], "clip")
        summary = forensics.end_request()
        self.assertEqual(summary["encode_calls"], 1)
        self.assertGreater(summary["forward_wall_ms_total"], 0)
        self.assertGreater(summary["encode_wall_ms_total"], 0)
        self.assertGreater(summary["load_wall_ms_total"], 0)
        self.assertIn("resident_at_last_encode", summary)

    def test_encode_call_count_increments(self) -> None:
        patcher = _FakePatcher()
        clip = _FakeCLIP(patcher=patcher, forward_delay_s=0.01)
        targets = _targets(patcher=patcher, clip=clip)
        forensics = _new_forensics(request_id="enc_req_2")
        forensics.begin_request("enc_req_2")
        _install_with_cleanup(self, forensics, targets)
        clip.encode_from_tokens({"l": [["a"]]})
        clip.encode_from_tokens_scheduled({"l": [["b"]]})
        summary = forensics.end_request()
        self.assertEqual(summary["encode_calls"], 2)
        by_name = _events_by_name(forensics)
        self.assertEqual(len(by_name.get("clip_cold_encode_end", [])), 1)
        self.assertEqual(len(by_name.get("clip_cold_scheduled_encode_end", [])), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Conditioning-cache hit vs miss
# ═══════════════════════════════════════════════════════════════════════════


class TestCacheHitVsMiss(unittest.TestCase):
    def _run(self, hit: int, miss: int) -> ClipColdPathForensics:
        patcher = _FakePatcher()
        cache = _FakeCache(hit_count=hit, miss_count=miss)
        clip = _FakeCLIP(patcher=patcher, forward_delay_s=0.005)
        targets = _targets(patcher=patcher, cache=cache, clip=clip)
        forensics = _new_forensics(request_id="cache_req")
        forensics.begin_request("cache_req")
        _install_with_cleanup(self, forensics, targets)
        cache.lookup_many({}, [{"node": "pos"}, {"node": "neg"}])
        if miss > 0:
            clip.encode_from_tokens({"l": [["a"]]})
        return forensics

    def test_cache_hit_no_load(self) -> None:
        forensics = self._run(hit=2, miss=0)
        summary = forensics.end_request()
        self.assertEqual(summary["cache_hits"], 2)
        self.assertEqual(summary["cache_misses"], 0)
        self.assertEqual(summary["cache_decisions"], ["hit"])
        self.assertEqual(summary["load_calls"], 0)
        self.assertEqual(summary["encode_calls"], 0)

    def test_cache_miss_drives_load_and_encode(self) -> None:
        forensics = self._run(hit=0, miss=2)
        summary = forensics.end_request()
        self.assertEqual(summary["cache_hits"], 0)
        self.assertEqual(summary["cache_misses"], 2)
        self.assertEqual(summary["cache_decisions"], ["miss"])
        self.assertEqual(summary["load_calls"], 1)
        self.assertEqual(summary["encode_calls"], 1)

    def test_partial_decision(self) -> None:
        cache = _FakeCache(hit_count=1, miss_count=1)
        targets = _targets(cache=cache)
        forensics = _new_forensics(request_id="cache_req_part")
        forensics.begin_request("cache_req_part")
        _install_with_cleanup(self, forensics, targets)
        cache.lookup_many({}, [{"node": "pos"}, {"node": "neg"}])
        summary = forensics.end_request()
        self.assertEqual(summary["cache_decisions"], ["partial"])


# ═══════════════════════════════════════════════════════════════════════════
# 6. Residency: multi-move detection + unload marks
# ═══════════════════════════════════════════════════════════════════════════


class TestResidencyMultiMove(unittest.TestCase):
    def test_load_unload_reload_detach_sequence(self) -> None:
        patcher = _FakePatcher()
        targets = _targets(patcher=patcher)
        forensics = _new_forensics(request_id="res_req_1")
        forensics.begin_request("res_req_1")
        _install_with_cleanup(self, forensics, targets)
        targets.mm_module.load_models_gpu([patcher])   # load #1 (cold)
        patcher.partially_unload(device_to="cpu", memory_to_free=64)
        targets.mm_module.load_models_gpu([patcher])   # load #2 (cold again: was unloaded)
        targets.mm_module.load_models_gpu([patcher])   # load #3 (already resident)
        patcher.detach()
        targets.mm_module.free_memory(100, torch.device("cuda:0"))
        targets.mm_module.soft_empty_cache()
        summary = forensics.end_request()
        self.assertEqual(summary["load_calls"], 3)
        patcher_id = str(id(patcher))
        self.assertIn(patcher_id, summary["multi_load_patchers"])
        self.assertTrue(summary["moved_more_than_once"])
        seq = [entry["event"] for entry in forensics._residency[patcher_id]]
        self.assertEqual(seq, ["load", "partial_unload", "load", "load", "detach"])
        by_name = _events_by_name(forensics)
        self.assertEqual(by_name["clip_cold_unload"][0]["metadata"]["kind"], "partial_unload")
        self.assertEqual(by_name["clip_cold_unload"][0]["metadata"]["device_to"], "cpu")
        self.assertIn("clip_cold_detach", by_name)
        self.assertEqual(by_name["clip_cold_detach"][0]["metadata"]["kind"], "detach")
        self.assertIn("clip_cold_free_memory", by_name)
        self.assertIn("clip_cold_soft_empty_cache", by_name)
        # Load #1 and #2 are genuine cold transfers (model was CPU/offloaded);
        # load #3 finds the encoder already resident on the GPU.
        loads = [e["metadata"] for e in by_name["clip_cold_patcher_load_end"]]
        self.assertEqual(loads[0]["resident_before"], False)
        self.assertEqual(loads[1]["resident_before"], False)
        self.assertEqual(loads[2]["resident_before"], True)
        self.assertGreater(loads[2]["already_resident_bytes"], 0)

    def test_single_load_not_flagged(self) -> None:
        patcher = _FakePatcher()
        targets = _targets(patcher=patcher)
        forensics = _new_forensics(request_id="res_req_2")
        forensics.begin_request("res_req_2")
        _install_with_cleanup(self, forensics, targets)
        targets.mm_module.load_models_gpu([patcher])
        summary = forensics.end_request()
        self.assertEqual(summary["multi_load_patchers"], [])
        self.assertFalse(summary["moved_more_than_once"])


# ═══════════════════════════════════════════════════════════════════════════
# 7. Synchronize counting (sync sub-flag)
# ═══════════════════════════════════════════════════════════════════════════


class TestSyncCounting(unittest.TestCase):
    def test_sync_count_and_wall_attributed(self) -> None:
        patcher = _FakePatcher()
        # Keep the synthetic interval above Windows' coarse timer granularity.
        torch_mod = _FakeTorch(sync_delay_s=0.02)
        # Patch the real torch.cuda.synchronize surface via the fake module.
        patcher.synchronize = torch_mod.synchronize

        class _SyncPatcher(_FakePatcher):
            def load(self, device_to=None, **kwargs):
                time.sleep(0.02)
                torch_mod.synchronize()
                torch_mod.synchronize()
                self.model.device = device_to or self.load_device
                self.model.model_loaded_weight_memory = sum(
                    int(p.numel() * p.element_size())
                    for p in self.model.parameters()
                )
                return self.model

        sync_patcher = _SyncPatcher()
        targets = _targets(patcher=sync_patcher, torch_mod=torch_mod)
        forensics = _new_forensics(
            request_id="sync_req_1", sync_cuda=True, cast_accounting=False,
        )
        forensics.begin_request("sync_req_1")
        statuses = _install_with_cleanup(self, forensics, targets)
        self.assertEqual(statuses["torch_cuda_synchronize"], "installed")
        targets.mm_module.load_models_gpu([sync_patcher])
        end = _load_end_event(forensics)
        self.assertIsNotNone(end)
        self.assertEqual(end["metadata"]["sync_count"], 2)
        self.assertGreater(end["metadata"]["sync_ms"], 0)
        summary = forensics.end_request()
        self.assertEqual(summary["total_sync_count"], 2)
        self.assertGreater(summary["total_sync_ms"], 0)

    def test_sync_wrapper_gated_off_by_default(self) -> None:
        targets = _targets()
        forensics = _new_forensics(request_id="sync_req_2")
        statuses = _install_with_cleanup(self, forensics, targets)
        self.assertEqual(statuses["torch_cuda_synchronize"], "installed")
        targets.torch_module.synchronize()
        self.assertEqual(forensics.request_summary()["total_sync_count"], 0)


class TestSoftEmptyCacheDecomposition(unittest.TestCase):
    def test_existing_operations_are_split_without_reordering(self) -> None:
        torch_mod = _DecompositionTorch()
        mm = _DecompositionMM(torch_mod)
        targets = _targets(mm=mm, torch_mod=torch_mod)
        forensics = _new_forensics(
            request_id="soft-cache-decomp", sync_cuda=True, cast_accounting=False,
        )
        forensics.begin_request("soft-cache-decomp")
        statuses = _install_with_cleanup(self, forensics, targets)
        self.assertEqual(statuses["torch_cuda_synchronize"], "installed")
        self.assertEqual(statuses["torch_cuda_empty_cache"], "installed")
        self.assertEqual(statuses["torch_cuda_ipc_collect"], "installed")

        mm.soft_empty_cache()

        self.assertEqual(
            torch_mod.calls, ["synchronize", "empty_cache", "ipc_collect"]
        )
        by_name = _events_by_name(forensics)
        self.assertEqual(
            [
                "model_management_soft_empty_cache_start",
                "model_management_cuda_sync_end",
                "model_management_empty_cache_end",
                "model_management_ipc_collect_end",
                "model_management_soft_empty_cache_end",
            ],
            [event["name"] for event in forensics._events
             if event["name"].startswith("model_management_")],
        )
        end = by_name["model_management_soft_empty_cache_end"][-1]["metadata"]
        self.assertAlmostEqual(end["cuda_synchronize_ms"], 100.0, delta=25.0)
        self.assertAlmostEqual(end["empty_cache_ms"], 200.0, delta=25.0)
        self.assertAlmostEqual(end["ipc_collect_ms"], 300.0, delta=25.0)
        self.assertGreaterEqual(end["soft_empty_cache_total_ms"], 550.0)
        self.assertGreaterEqual(end["pre_sync_ms"], 0.0)
        self.assertGreaterEqual(end["post_cleanup_ms"], 0.0)

    def test_operation_exception_preserves_native_failure(self) -> None:
        torch_mod = _DecompositionTorch(fail_operation="empty_cache")
        mm = _DecompositionMM(torch_mod)
        targets = _targets(mm=mm, torch_mod=torch_mod)
        forensics = _new_forensics(
            request_id="soft-cache-error", sync_cuda=True, cast_accounting=False,
        )
        forensics.begin_request("soft-cache-error")
        _install_with_cleanup(self, forensics, targets)

        with self.assertRaisesRegex(RuntimeError, "empty_cache failed"):
            mm.soft_empty_cache()

        self.assertEqual(torch_mod.calls, ["synchronize", "empty_cache"])
        by_name = _events_by_name(forensics)
        self.assertEqual(
            by_name["model_management_empty_cache_end"][-1]["metadata"]["status"],
            "error",
        )
        self.assertEqual(
            by_name["model_management_soft_empty_cache_end"][-1]["metadata"]["status"],
            "error",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 8. Idempotent install + exact uninstall restore
# ═══════════════════════════════════════════════════════════════════════════


class TestInstallIdempotentAndUninstall(unittest.TestCase):
    def test_double_install_and_restore(self) -> None:
        targets = _targets()
        orig_mm_load = targets.mm_module.load_models_gpu
        orig_patcher_load = targets.mp_class.load
        forensics = _new_forensics(request_id="inst_req_1")
        forensics.begin_request("inst_req_1")
        first = _install_with_cleanup(self, forensics, targets)
        self.assertEqual(first["load_models_gpu"], "installed")
        self.assertEqual(first["patcher_load"], "installed")
        second = forensics.install(targets=targets)
        self.assertEqual(second["load_models_gpu"], "already_installed")
        self.assertEqual(second["patcher_load"], "already_installed")
        restored = forensics.uninstall()
        self.assertTrue(restored)
        self.assertIs(targets.mm_module.load_models_gpu.__func__, orig_mm_load.__func__)
        self.assertIs(targets.mp_class.load, orig_patcher_load)
        # No further events after uninstall.
        targets.mm_module.load_models_gpu([_FakePatcher()])
        self.assertEqual(forensics._events, [])

    def test_uninstall_never_raises_when_nothing_installed(self) -> None:
        forensics = _new_forensics(request_id="inst_req_2")
        self.assertEqual(forensics.uninstall(), {})


# ═══════════════════════════════════════════════════════════════════════════
# 9. Env-flag gating
# ═══════════════════════════════════════════════════════════════════════════


class TestGatingEnvFlag(unittest.TestCase):
    def test_forensics_enabled_flag(self) -> None:
        with patch.dict(os.environ, {"COMFYMODAL_V2_CLIP_COLD_FORENSICS": "1"}):
            self.assertTrue(forensics_enabled())
        with patch.dict(os.environ, {"COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0"}):
            self.assertFalse(forensics_enabled())
        self.assertFalse(forensics_enabled())

    def test_sub_flags(self) -> None:
        with patch.dict(os.environ, {"COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "1"}):
            self.assertTrue(cast_accounting_enabled())
        with patch.dict(os.environ, {"COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "1"}):
            self.assertTrue(sync_cuda_enabled())
        self.assertFalse(cast_accounting_enabled())
        self.assertFalse(sync_cuda_enabled())

    def test_install_helper_disabled_without_flag(self) -> None:
        self.assertEqual(install_forensics_if_enabled(), {"status": "disabled"})


# ═══════════════════════════════════════════════════════════════════════════
# 10. install() with no usable targets never raises
# ═══════════════════════════════════════════════════════════════════════════


class TestInstallNoTargetsNeverRaises(unittest.TestCase):
    def test_empty_targets(self) -> None:
        forensics = _new_forensics(request_id="none_req_1")
        result = forensics.install(targets=SimpleNamespace())
        self.assertIsInstance(result, dict)
        # No exception; anything returned is fine (all components unavailable).

    def test_targets_none_never_raises(self) -> None:
        forensics = _new_forensics(request_id="none_req_2")
        result = forensics.install(targets=None)
        self.assertIsInstance(result, dict)

    def test_exception_in_original_does_not_break_wrappers(self) -> None:
        class _RaisingPatcher(_FakePatcher):
            def load(self, device_to=None, **kwargs):
                raise RuntimeError("simulated load failure")

        patcher = _RaisingPatcher()
        targets = _targets(patcher=patcher)
        forensics = _new_forensics(request_id="none_req_3")
        forensics.begin_request("none_req_3")
        _install_with_cleanup(self, forensics, targets)
        with self.assertRaises(RuntimeError):
            targets.mm_module.load_models_gpu([patcher])
        end = _load_end_event(forensics)
        self.assertIsNotNone(end, "load end must be emitted even on error")
        self.assertEqual(end["metadata"]["status"], "error")


# ═══════════════════════════════════════════════════════════════════════════
# 11. Cross-sentinel guard against the model_preload core wrappers
# ═══════════════════════════════════════════════════════════════════════════
# The five shared targets (load_models_gpu, free_memory, soft_empty_cache,
# ModelPatcher.patch_weight_to_device, CLIP.load_model) are wrapped by BOTH
# the core model_preload machinery (sentinel ``_comfy_modal_gpu_wrapper``)
# and this module.  Both sides carry a symmetric guard so exactly one
# wrapper wins regardless of install order — no nested double
# instrumentation.  Targets are mocked as plain functions/classes so no
# ``comfy`` import is required.


def _plain_mm() -> SimpleNamespace:
    """A plain fake ``comfy.model_management`` surface (no comfy import)."""
    mm = SimpleNamespace()

    def load_models_gpu(models, memory_required=0, **kwargs):
        return ("loaded",)

    def free_memory(memory_required, device, **kwargs):
        return memory_required

    def soft_empty_cache():
        return None

    mm.load_models_gpu = load_models_gpu
    mm.free_memory = free_memory
    mm.soft_empty_cache = soft_empty_cache
    return mm


class TestCrossSentinelGuard(unittest.TestCase):
    """Forensics <-> core model_preload cross-sentinel guards."""

    def _reset_gpu_flag(self) -> Any:
        import comfymodal_runtime.model_preload as _mp

        saved = _mp._gpu_wrapper_installed
        _mp._gpu_wrapper_installed = False
        self.addCleanup(setattr, _mp, "_gpu_wrapper_installed", saved)
        return _mp

    def test_core_first_then_forensics_skips_load_models_gpu(self) -> None:
        """Core wrapper installed first: forensics must skip the shared
        ``load_models_gpu`` target (status ``skipped_core_wrapper_present``)
        leaving exactly one wrapper layer — the core one."""
        from comfymodal_runtime.model_preload import _install_gpu_wrapper

        _mp = self._reset_gpu_flag()
        mm = _plain_mm()
        core_status = _install_gpu_wrapper(mm_module=mm)
        self.assertEqual(core_status, "installed")

        forensics = _new_forensics(request_id="xsent_1")
        statuses = forensics.install(targets=SimpleNamespace(mm_module=mm))
        self.addCleanup(forensics.uninstall)
        self.assertEqual(
            statuses["load_models_gpu"],
            "skipped_core_wrapper_present",
            "forensics must not re-wrap a core-owned shared target",
        )
        # The cross-sentinel guard is target-scoped: non-conflicting targets
        # still get the forensics wrapper.
        self.assertEqual(statuses["free_memory"], "installed")
        self.assertEqual(statuses["soft_empty_cache"], "installed")

        # Exactly one wrapper layer: attribute is the core wrapper whose
        # __wrapped__ chain bottoms out at the plain function.
        current = mm.load_models_gpu
        self.assertTrue(getattr(current, "_comfy_modal_gpu_wrapper", False))
        self.assertFalse(
            getattr(current, "_comfymodal_clip_cold_forensics", False),
            "forensics wrapper must not have been layered on",
        )
        self.assertIs(getattr(current, "__wrapped__", None), mm.load_models_gpu.__wrapped__)

    def test_forensics_first_then_core_skips_load_models_gpu(self) -> None:
        """Forensics installed first: the core installer must skip via its
        symmetric guard (status ``skipped_forensics_wrapper_present``)
        leaving exactly one wrapper layer — the forensics one."""
        from comfymodal_runtime.model_preload import _install_gpu_wrapper

        self._reset_gpu_flag()
        mm = _plain_mm()
        forensics = _new_forensics(request_id="xsent_2")
        statuses = forensics.install(targets=SimpleNamespace(mm_module=mm))
        self.addCleanup(forensics.uninstall)
        self.assertEqual(statuses["load_models_gpu"], "installed")

        core_status = _install_gpu_wrapper(mm_module=mm)
        self.assertEqual(
            core_status,
            "skipped_forensics_wrapper_present",
            "core installer must not re-wrap a forensics-owned target",
        )

        # Exactly one wrapper layer: attribute is the forensics wrapper
        # whose __wrapped__ chain bottoms out at the plain function.
        current = mm.load_models_gpu
        self.assertTrue(getattr(current, "_comfymodal_clip_cold_forensics", False))
        self.assertFalse(
            getattr(current, "_comfy_modal_gpu_wrapper", False),
            "core wrapper must not have been layered on",
        )
        self.assertIs(getattr(current, "__wrapped__", None), mm.load_models_gpu.__wrapped__)

    def test_guard_covers_all_five_shared_targets(self) -> None:
        """The forensics cross-sentinel guard applies to every shared
        target, not just ``load_models_gpu``: stamp the core sentinel on
        ``patch_weight_to_device`` and ``CLIP.load_model`` and verify each
        is reported ``skipped_core_wrapper_present`` while non-shared
        targets (``clip_tokenize``) still install."""
        class _LocalPatcher:
            def load(self, device_to=None, lowvram_model_memory=0, **kwargs):
                return None

            def partially_load(self, device_to=None, lowvram_model_memory=0, **kwargs):
                return None

            def partially_unload(self, device_to=None, memory_to_free=0, **kwargs):
                return memory_to_free

            def detach(self, unpatch_weights=True, **kwargs):
                return None

            def patch_weight_to_device(self, key, device_to=None, **kwargs):
                return None

        class _LocalClip:
            def tokenize(self, text):
                return {}

            def load_model(self, tokens={}):
                return None

            def encode_from_tokens(self, tokens, return_pooled=False, **kwargs):
                return []

            def encode_from_tokens_scheduled(self, tokens, **kwargs):
                return []

        # Simulate the core model_preload wrappers already owning these two
        # shared targets.
        setattr(_LocalPatcher.patch_weight_to_device, "_comfy_modal_gpu_wrapper", True)
        setattr(_LocalClip.load_model, "_comfy_modal_gpu_wrapper", True)

        targets = SimpleNamespace(
            mm_module=_plain_mm(),
            mp_class=_LocalPatcher,
            sd_clip_class=_LocalClip,
            cache_class=_FakeCache(),
            torch_module=None,
        )
        forensics = _new_forensics(request_id="xsent_3", cast_accounting=True)
        statuses = forensics.install(targets=targets)
        self.addCleanup(forensics.uninstall)
        self.assertEqual(
            statuses["patch_weight_to_device"], "skipped_core_wrapper_present"
        )
        self.assertEqual(statuses["clip_load_model"], "skipped_core_wrapper_present")
        # Non-shared targets are unaffected by the guard.
        self.assertEqual(statuses["clip_tokenize"], "installed")


if __name__ == "__main__":
    unittest.main()
