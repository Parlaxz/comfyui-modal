"""Batch D3 production wiring tests: default-off CLIP fast hydration +
snapshot weight exclusion.

Exercises the real ``clip_fast_hydration`` / ``clip_fast_hydration_wiring``
modules against synthetic CLIP-like modules and mocked patcher paths — no
real models, no remote calls, no comfy import required at module level.

Covers the ten memory-correctness proofs plus flag semantics, the frozen
capability manifest, fallback counting, and D2 telemetry integration.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
import torch

from comfymodal_runtime import clip_fast_hydration as cfh
from comfymodal_runtime import clip_fast_hydration_wiring as wiring


@pytest.fixture(autouse=True)
def _reset_clip_fh_records():
    wiring._RECORD.clear()
    wiring._LAST_EXCLUDED.clear()
    yield
    wiring._RECORD.clear()
    wiring._LAST_EXCLUDED.clear()

CUDA_OK = torch.cuda.is_available()
FASTSAFE_OK = importlib.util.find_spec("fastsafetensors") is not None
CLOUDPICKLE_OK = importlib.util.find_spec("cloudpickle") is not None

PAYLOAD_BYTES = 0


class _TinyTransformer(torch.nn.Module):
    """CLIPTextModel-like module: flat HF-style keys, text_projection inside
    (mirrors comfy.clip_model, whose state dict receives the file sd
    directly from SDClipModel.load_sd)."""

    def __init__(self, dim: int = 64, dtype: torch.dtype = torch.float16):
        super().__init__()
        self.emb = torch.nn.Embedding(512, dim, dtype=dtype)
        self.ln1 = torch.nn.LayerNorm(dim, dtype=dtype)
        self.ff = torch.nn.Linear(dim, dim, dtype=dtype)
        self.ln2 = torch.nn.LayerNorm(dim, dtype=dtype)
        self.ff2 = torch.nn.Linear(dim, dim, dtype=dtype)
        self.text_projection = torch.nn.Linear(dim, 32, dtype=dtype)

    def forward(self, ids: torch.Tensor) -> torch.Tensor:
        x = self.emb(ids)
        x = self.ff(self.ln1(x))
        x = self.ff2(self.ln2(x))
        x = x.mean(dim=1)
        return self.text_projection(x)


class _Leaf(torch.nn.Module):
    """SDClipModel-like dispatch leaf honoring the can_assign_sd convention:
    load_sd forwards the whole file sd to the transformer's
    load_state_dict(assign=can_assign_sd), exactly like sd1_clip.py:308-309.
    With prefix='g' the transformer keys gain a 'gtransformer.' prefix so the
    container can dispatch by key presence."""

    def __init__(self, prefix: str = "", dtype: torch.dtype = torch.float16):
        super().__init__()
        if prefix:
            self.transformer = torch.nn.Module()
            self.transformer.add_module("gtransformer", _TinyTransformer(dtype=dtype))
        else:
            self.transformer = _TinyTransformer(dtype=dtype)

    def load_sd(self, sd: dict) -> Any:
        return self.transformer.load_state_dict(
            sd, strict=False, assign=getattr(self, "can_assign_sd", False)
        )

    def forward(self, ids: torch.Tensor) -> torch.Tensor:
        transformer = self.transformer
        if hasattr(transformer, "gtransformer"):
            transformer = transformer.gtransformer
        return transformer(ids)


class _FakeCSM(torch.nn.Module):
    """Container dispatching per-file sds by key presence (Comfy pattern)."""

    def __init__(self, dtype: torch.dtype = torch.float16):
        super().__init__()
        self.clip_l = _Leaf(dtype=dtype)
        self.clip_g = _Leaf(prefix="g", dtype=dtype)

    def load_sd(self, sd: dict) -> Any:
        if any(k.startswith("gtransformer.") for k in sd):
            return self.clip_g.load_sd(sd)
        return self.clip_l.load_sd(sd)


class _FakePatcher:
    def __init__(self, model: Any):
        self.model = model
        self.load_device = torch.device("cuda:0" if CUDA_OK else "cpu")
        self.offload_device = torch.device("cpu")
        self.is_clip = True

    def is_dynamic(self) -> bool:
        return False

    def model_size(self) -> int:
        return sum(int(p.numel() * p.element_size()) for p in self.model.parameters())


class _FakeClip:
    def __init__(self, dtype: torch.dtype = torch.float16):
        self.cond_stage_model = _FakeCSM(dtype=dtype)
        self.patcher = _FakePatcher(self.cond_stage_model)
        self.tokenizer = object()

    def load_model(self, tokens: Any = None) -> Any:
        return self.patcher


class _CanonicalLeaf(torch.nn.Module):
    """Parent leaf with the canonical assign-forwarding ``load_sd`` body
    (mirrors comfy/sd1_clip.py:308-309 ``SDClipModel.load_sd``)."""

    def __init__(self, dtype: torch.dtype = torch.float16):
        super().__init__()
        self.transformer = _TinyTransformer(dtype=dtype)

    def load_sd(self, sd: dict) -> Any:
        return self.transformer.load_state_dict(
            sd, strict=False, assign=getattr(self, "can_assign_sd", False)
        )


class _SuperForwardLeaf(_CanonicalLeaf):
    """SDXLClipG-style leaf whose ``load_sd`` is a trivial
    ``return super().load_sd(sd)`` forward (mirrors comfy/sdxl_clip.py:16-17)."""

    def load_sd(self, sd: dict) -> Any:
        return super().load_sd(sd)


class _SuperChainCSM(torch.nn.Module):
    def __init__(self, dtype: torch.dtype = torch.float16):
        super().__init__()
        self.text_encoder = _SuperForwardLeaf(dtype=dtype)

    def load_sd(self, sd: dict) -> Any:
        return self.text_encoder.load_sd(sd)


class _TopForward(torch.nn.Module):
    def load_sd(self, sd: dict) -> Any:
        return super().load_sd(sd)


class _MidForward(_TopForward):
    def load_sd(self, sd: dict) -> Any:
        return super().load_sd(sd)


class _NeverResolvingLeaf(_MidForward):
    def load_sd(self, sd: dict) -> Any:
        return super().load_sd(sd)


class _NeverResolvingCSM(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.text_encoder = _NeverResolvingLeaf()

    def load_sd(self, sd: dict) -> Any:
        return self.text_encoder.load_sd(sd)


class _FlagNoAssignLeaf(torch.nn.Module):
    """Direct body that references ``can_assign_sd`` (reads the flag) but
    never forwards ``assign=`` to ``load_state_dict`` — must be rejected by
    the strengthened probe."""

    def __init__(self, dtype: torch.dtype = torch.float16):
        super().__init__()
        self.transformer = _TinyTransformer(dtype=dtype)

    def load_sd(self, sd: dict) -> Any:
        flag = getattr(self, "can_assign_sd", False)
        return self.transformer.load_state_dict(sd, strict=False)


class _FlagNoAssignCSM(torch.nn.Module):
    def __init__(self, dtype: torch.dtype = torch.float16):
        super().__init__()
        self.text_encoder = _FlagNoAssignLeaf(dtype=dtype)

    def load_sd(self, sd: dict) -> Any:
        return self.text_encoder.load_sd(sd)


class _RecordingTrace:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit_at(self, name: str, **kwargs: Any) -> None:
        self.events.append({"name": name, "metadata": kwargs.get("metadata") or {}})

    def emit(self, name: str, **kwargs: Any) -> None:
        self.events.append({"name": name, "metadata": kwargs.get("metadata") or {}})

    def names(self) -> list[str]:
        return [e["name"] for e in self.events]

    def by_name(self, name: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["name"] == name]


def _ids(seed: int = 3) -> torch.Tensor:
    gen = torch.Generator().manual_seed(seed)
    return torch.randint(0, 512, (2, 6), generator=gen)


def _forward(model: torch.nn.Module) -> torch.Tensor:
    model.eval()
    ids = _ids()
    first_param = next(model.parameters(), None)
    if first_param is not None and first_param.device.type == "cuda":
        ids = ids.cuda()
    with torch.no_grad():
        out = model(ids)
    return out.detach().cpu() if out.is_cuda else out.detach()


def _reference(leaf: _Leaf) -> torch.Tensor:
    return _forward(leaf)


def _param_bytes(module: torch.nn.Module) -> int:
    return sum(int(p.numel() * p.element_size()) for p in module.parameters())


class ClipFhFixture:
    def __init__(self) -> None:
        global PAYLOAD_BYTES
        self.tmpdir = tempfile.mkdtemp(
            prefix="clip_fh_prod_",
            dir=r"C:\Users\parla\AppData\Local\Temp\opencode"
            if os.path.isdir(r"C:\Users\parla\AppData\Local\Temp\opencode")
            else None,
        )
        import safetensors.torch

        self.leaf = _Leaf()
        self.leaf_sd = {
            k: v.detach().clone() for k, v in self.leaf.transformer.state_dict().items()
        }
        PAYLOAD_BYTES = _param_bytes(self.leaf)
        self.path1 = os.path.join(self.tmpdir, "clip_l.safetensors")
        safetensors.torch.save_file(self.leaf_sd, self.path1)

        self.leaf_g = _Leaf(prefix="g")
        self.leaf_g_sd = {
            k: v.detach().clone()
            for k, v in self.leaf_g.transformer.state_dict().items()
        }
        self.path2 = os.path.join(self.tmpdir, "clip_g.safetensors")
        safetensors.torch.save_file(self.leaf_g_sd, self.path2)

        legacy = dict(self.leaf_sd)
        legacy["text_projection"] = legacy.pop("text_projection.weight").transpose(0, 1).contiguous()
        self.legacy_path = os.path.join(self.tmpdir, "legacy.safetensors")
        safetensors.torch.save_file(legacy, self.legacy_path)

        quant = dict(self.leaf_sd)
        quant["transformer.ff.comfy_quant"] = torch.zeros(64, 64, dtype=torch.uint8)
        self.quant_path = os.path.join(self.tmpdir, "quant.safetensors")
        safetensors.torch.save_file(quant, self.quant_path)

        mixed = dict(self.leaf_sd)
        mixed["ff.weight"] = mixed["ff.weight"].float()
        self.mixed_path = os.path.join(self.tmpdir, "mixed.safetensors")
        safetensors.torch.save_file(mixed, self.mixed_path)

    def cpu_models(self, clip: Any, paths: list[str]) -> SimpleNamespace:
        facts = tuple(
            SimpleNamespace(role=f"clip{i + 1}", path=p, size_bytes=os.path.getsize(p), mtime_ns=0)
            for i, p in enumerate(paths)
        )
        return SimpleNamespace(
            clip=clip,
            file_facts=facts,
            model_spec={
                "loaders": {
                    "clip": [{"clip_name": os.path.basename(p), "type": "stable_diffusion"} for p in paths]
                }
            },
        )

    def cleanup(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)


@unittest.skipUnless(CUDA_OK, "CUDA required")
class TestFlags(unittest.TestCase):
    def test_flags_default_off(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(wiring._FLAG_FAST, None)
            os.environ.pop(wiring._FLAG_EXCLUDE, None)
            self.assertFalse(wiring.clip_fast_hydration_enabled())
            self.assertFalse(wiring.clip_snapshot_exclude_weights_enabled())

    def test_flags_true_values(self) -> None:
        for value in ("1", "true", "yes", "on"):
            with patch.dict(os.environ, {wiring._FLAG_FAST: value}, clear=False):
                self.assertTrue(wiring.clip_fast_hydration_enabled())
            with patch.dict(os.environ, {wiring._FLAG_EXCLUDE: value}, clear=False):
                self.assertTrue(wiring.clip_snapshot_exclude_weights_enabled())

    def test_flags_invalid_fail_closed(self) -> None:
        for value in ("0", "false", "no", "off", "", "garbage", "2"):
            with patch.dict(os.environ, {wiring._FLAG_FAST: value}, clear=False):
                self.assertFalse(wiring.clip_fast_hydration_enabled())
            with patch.dict(os.environ, {wiring._FLAG_EXCLUDE: value}, clear=False):
                self.assertFalse(wiring.clip_snapshot_exclude_weights_enabled())


@unittest.skipUnless(CUDA_OK, "CUDA required")
class TestManifestAndExclusion(unittest.TestCase):
    """Proofs 1 and 10: exclusion strips only eligible payloads; ineligible
    candidates never have their payload removed."""

    def setUp(self) -> None:
        self.fx = ClipFhFixture()

    def tearDown(self) -> None:
        self.fx.cleanup()

    def _prepare(self, paths: list[str], exclude: bool, fast: bool = True) -> tuple[_FakeClip, dict]:
        clip = _FakeClip()
        flags = {wiring._FLAG_EXCLUDE: "1" if exclude else "0", wiring._FLAG_FAST: "1" if fast else "0"}
        with patch.dict(os.environ, flags, clear=False):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, paths), trace=_RecordingTrace()
            )
        return clip, result

    def test_eligible_manifest_and_strip(self) -> None:
        clip, result = self._prepare([self.fx.path1], exclude=True)
        self.assertEqual(result["status"], "excluded")
        manifest = cfh.get_clip_manifest(clip)
        self.assertIsNotNone(manifest)
        self.assertTrue(manifest["eligible"])
        self.assertEqual(manifest["files"][0]["key_set"], sorted(self.fx.leaf_sd.keys()))
        self.assertEqual(manifest["files"][0]["dtype"], "torch.float16")
        self.assertTrue(cfh.clip_weights_excluded(clip))
        for name, param in clip.cond_stage_model.named_parameters():
            self.assertTrue(getattr(param, "is_meta", False), f"{name} not meta")
        self.assertEqual(result.get("manifest", {}).get("files", [])[0]["key_set"], manifest["files"][0]["key_set"])

    def test_manifest_only_when_not_excluding(self) -> None:
        clip, result = self._prepare([self.fx.path1], exclude=False)
        self.assertEqual(result["status"], "manifest_only")
        self.assertFalse(cfh.clip_weights_excluded(clip))
        self.assertIsNotNone(cfh.get_clip_manifest(clip))

    def test_quant_marked_ineligible_never_stripped(self) -> None:
        clip, result = self._prepare([self.fx.quant_path], exclude=True)
        self.assertEqual(result["status"], "ineligible")
        self.assertFalse(cfh.clip_weights_excluded(clip))
        for name, param in clip.cond_stage_model.named_parameters():
            self.assertFalse(getattr(param, "is_meta", False), f"{name} stripped")
        self.assertIsNone(cfh.get_clip_manifest(clip))

    def test_mixed_dtype_ineligible_never_stripped(self) -> None:
        clip, result = self._prepare([self.fx.mixed_path], exclude=True)
        self.assertEqual(result["status"], "ineligible")
        self.assertFalse(cfh.clip_weights_excluded(clip))

    def test_legacy_transform_recorded(self) -> None:
        clip, result = self._prepare([self.fx.legacy_path], exclude=True)
        self.assertEqual(result["status"], "excluded")
        manifest = cfh.get_clip_manifest(clip)
        pipeline = manifest["files"][0]["pipeline"]
        self.assertEqual(pipeline, [{"op": "text_projection"}])
        self.assertIn("text_projection.weight", manifest["files"][0]["key_set"])

    def test_payload_bytes_removed(self) -> None:
        clip, result = self._prepare([self.fx.path1], exclude=True)
        self.assertEqual(result["status"], "excluded")
        stats_bytes = 0
        for name, param in clip.cond_stage_model.named_parameters():
            if not getattr(param, "is_meta", False):
                stats_bytes += int(param.numel()) * int(param.element_size())
        self.assertEqual(stats_bytes, 0)


@unittest.skipUnless(CUDA_OK, "CUDA required")
class TestRestoreHydrationCpu(unittest.TestCase):
    """Proofs 2, 3, 4 on the safe native reconstruction path (Path B without
    Path A): assign bind from CPU tensors through Comfy's own dispatch."""

    def setUp(self) -> None:
        self.fx = ClipFhFixture()
        self.ref = _reference(self.fx.leaf)

    def tearDown(self) -> None:
        self.fx.cleanup()

    def test_cpu_assign_rehydrates_and_parity(self) -> None:
        clip, _ = self._prepare_excluded()
        result = wiring._hydrate_clip_on_demand(clip, trace=_RecordingTrace())
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result.get("mode"), cfh.MODE_NATIVE)
        self.assertEqual(result.get("reconstruction"), "cpu_assign")
        out = _forward(clip.cond_stage_model.clip_l)
        self.assertTrue(torch.allclose(out, self.ref, rtol=1e-2, atol=1e-2), "parity")
        self.assertTrue(cfh.clip_hydrated(clip))
        self.assertFalse(
            any(getattr(p, "is_meta", False) for p in clip.cond_stage_model.clip_l.parameters())
        )
        for name, param in clip.cond_stage_model.clip_l.state_dict().items():
            self.assertEqual(str(param.device), "cpu", name)

    def test_no_duplicate_cpu_payload(self) -> None:
        clip, _ = self._prepare_excluded()
        result = wiring._hydrate_clip_on_demand(clip, trace=_RecordingTrace())
        self.assertTrue(result.get("ok"))
        self.assertTrue("share storage" in str(result.get("zero_copy_evidence", "")))

    def _prepare_excluded(self) -> tuple[_FakeClip, dict]:
        clip = _FakeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "0"},
            clear=False,
        ):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.fx.path1]), trace=_RecordingTrace()
            )
        self.assertEqual(result["status"], "excluded")
        return clip, result


@unittest.skipUnless(CUDA_OK and FASTSAFE_OK, "CUDA + fastsafetensors required")
class TestFastHydrationCuda(unittest.TestCase):
    """Proofs 2-6 on the fastsafetensors direct-GPU path."""

    def setUp(self) -> None:
        self.fx = ClipFhFixture()
        self.ref = _reference(self.fx.leaf)
        self.ref_g = _reference(self.fx.leaf_g)

    def tearDown(self) -> None:
        self.fx.cleanup()

    def _prepare(self, paths: list[str], exclude: bool) -> tuple[_FakeClip, dict]:
        clip = _FakeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1" if exclude else "0", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, paths), trace=_RecordingTrace()
            )
        return clip, result

    def test_fast_hydrate_zero_copy_cuda(self) -> None:
        clip, result = self._prepare([self.fx.path1], exclude=True)
        self.assertEqual(result["status"], "excluded")
        trace = _RecordingTrace()
        outcome = wiring._hydrate_clip_on_demand(clip, trace=trace)
        self.assertTrue(outcome.get("ok"), outcome)
        self.assertEqual(outcome.get("mode"), cfh.MODE_FASTSAFE)
        self.assertTrue(outcome.get("zero_copy"), outcome.get("zero_copy_evidence"))
        self.assertGreater(outcome.get("checkpoint_bytes", 0), 0)
        self.assertIn("gbps", outcome)
        self.assertIn("file_to_gpu_wall_ms", outcome)
        self.assertIn("bind_wall_ms", outcome)
        self.assertEqual(outcome.get("owner_mode"), "fastsafetensors_buf")
        self.assertEqual(outcome.get("fallback_count"), 0)
        self.assertLess(
            outcome.get("cuda_delta_bytes") or 0,
            2 * PAYLOAD_BYTES + 4 * 1024 * 1024,
            "no second full GPU copy",
        )
        out = _forward(clip.cond_stage_model.clip_l)
        self.assertTrue(torch.allclose(out, self.ref, rtol=1e-2, atol=1e-2), "parity")
        self.assertTrue(cfh.clip_hydrated(clip))
        owners = getattr(clip.patcher, cfh.OWNER_ATTR, None)
        self.assertTrue(owners, "owner retained")
        self.assertEqual(
            str(next(iter(clip.cond_stage_model.clip_l.parameters())).device).split(":")[0],
            "cuda",
        )
        end_events = trace.by_name("clip_fh_hydration_end")
        self.assertTrue(end_events, "clip_fh_hydration_end emitted")
        meta = end_events[0]["metadata"]
        for key in (
            "mode",
            "file_to_gpu_wall_ms",
            "checkpoint_bytes",
            "gbps",
            "bind_wall_ms",
            "owner_mode",
            "cuda_delta_bytes",
            "zero_copy",
            "fallback_count",
        ):
            self.assertIn(key, meta, key)

    def test_multi_file_dispatch_both_leaves(self) -> None:
        clip, result = self._prepare([self.fx.path1, self.fx.path2], exclude=True)
        self.assertEqual(result["status"], "excluded")
        manifest = cfh.get_clip_manifest(clip)
        self.assertEqual(len(manifest["files"]), 2)
        outcome = wiring._hydrate_clip_on_demand(clip, trace=_RecordingTrace())
        self.assertTrue(outcome.get("ok"), outcome)
        out_l = _forward(clip.cond_stage_model.clip_l)
        out_g = _forward(clip.cond_stage_model.clip_g)
        self.assertTrue(torch.allclose(out_l, self.ref, rtol=1e-2, atol=1e-2), "clip_l parity")
        self.assertTrue(torch.allclose(out_g, self.ref_g, rtol=1e-2, atol=1e-2), "clip_g parity")
        self.assertTrue(all(p.device.type == "cuda" for p in clip.cond_stage_model.parameters()))

    def test_owner_release_teardown(self) -> None:
        clip, _ = self._prepare([self.fx.path1], exclude=True)
        wiring._hydrate_clip_on_demand(clip, trace=_RecordingTrace())
        owners = getattr(clip.patcher, cfh.OWNER_ATTR, None)
        self.assertTrue(owners)
        released = cfh.release_owner(clip)
        self.assertTrue(released)
        self.assertFalse(hasattr(clip.patcher, cfh.OWNER_ATTR))

    def test_fast_failure_path_a_leaves_native_untouched(self) -> None:
        clip = _FakeClip()
        with patch.dict(os.environ, {wiring._FLAG_EXCLUDE: "0", wiring._FLAG_FAST: "1"}, clear=False):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.fx.path1]), trace=_RecordingTrace()
            )
        self.assertEqual(result["status"], "manifest_only")
        before = {k: v.detach().clone() for k, v in clip.cond_stage_model.clip_l.state_dict().items()}
        missing = os.path.join(self.fx.tmpdir, "gone.safetensors")
        manifest = cfh.get_clip_manifest(clip)
        manifest["files"][0]["path"] = missing
        cfh.attach_clip_manifest(clip, manifest)
        outcome = wiring._hydrate_clip_on_demand(clip, trace=_RecordingTrace())
        self.assertFalse(outcome.get("ok"))
        self.assertEqual(outcome.get("mode"), cfh.MODE_NATIVE)
        self.assertEqual(outcome.get("fallback_count"), 1)
        after = clip.cond_stage_model.clip_l.state_dict()
        for key in before:
            self.assertTrue(torch.equal(before[key], after[key].detach().cpu()), key)


@unittest.skipUnless(CUDA_OK, "CUDA required")
class TestDemandWrapperAndCacheHit(unittest.TestCase):
    """Proof 8: an exact cache hit performs ZERO hydration."""

    def setUp(self) -> None:
        self.fx = ClipFhFixture()

    def tearDown(self) -> None:
        self.fx.cleanup()

    def _install(self) -> tuple[_FakeClip, _RecordingTrace]:
        clip = _FakeClip()
        trace = _RecordingTrace()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.fx.path1]), trace=trace
            )
            status = wiring.maybe_install_clip_fh_demand(
                SimpleNamespace(clip=clip), trace=trace
            )
        self.assertEqual(status["status"], "installed")
        return clip, trace

    def test_cache_hit_zero_hydration(self) -> None:
        clip, trace = self._install()
        self.assertFalse(cfh.clip_hydrated(clip))
        for event in trace.events:
            self.assertNotEqual(event["name"], "clip_fh_hydration_end")
        # The unittest runner (run_tests.py) does not apply the module-level
        # pytest autouse fixture that clears _RECORD between tests, so an
        # earlier demand hydration (e.g. TestD2TelemetryIntegration) can
        # leave a per-request record behind.  Clear it here so the cache-hit
        # assertion is order-independent — exactly what the pytest fixture
        # would have done between tests.  _LAST_EXCLUDED is left intact: this
        # clip IS excluded (Path B) and no demand ever hydrates it.
        wiring._RECORD.clear()
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["hydration_source"], cfh.MODE_CACHE_HIT)
        self.assertFalse(summary["hydrated"])

    def test_first_demand_hydrates_once(self) -> None:
        clip, trace = self._install()
        clip.load_model({})
        self.assertTrue(cfh.clip_hydrated(clip))
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["hydration_source"], cfh.MODE_FASTSAFE)
        self.assertTrue(summary["hydrated"])
        clip.load_model({})
        summary2 = wiring.clip_fh_request_summary("")
        self.assertEqual(summary2["hydration_source"], cfh.MODE_RESIDENT)

    def test_no_manifest_means_native(self) -> None:
        clip = _FakeClip()
        trace = _RecordingTrace()
        with patch.dict(os.environ, {wiring._FLAG_FAST: "1"}, clear=False):
            status = wiring.maybe_install_clip_fh_demand(
                SimpleNamespace(clip=clip), trace=trace
            )
        self.assertEqual(status["status"], "no_manifest")
        self.assertFalse(hasattr(clip, cfh.DEMAND_WRAPPER_MARKER))
        self.assertFalse(cfh.clip_hydrated(clip))


@unittest.skipUnless(CUDA_OK, "CUDA required")
class TestFallbackChain(unittest.TestCase):
    """Proof 9: fast-path failure reconstructs through native exactly once."""

    def setUp(self) -> None:
        self.fx = ClipFhFixture()
        self.ref = _reference(self.fx.leaf)

    def tearDown(self) -> None:
        self.fx.cleanup()

    def test_b_exclusion_fast_failure_uses_cpu_assign(self) -> None:
        clip = _FakeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.fx.path1]), trace=_RecordingTrace()
            )
        with patch.object(
            wiring, "_fastsafe_load", side_effect=RuntimeError("simulated fast failure")
        ):
            outcome = wiring._hydrate_clip_on_demand(clip, trace=_RecordingTrace())
        self.assertTrue(outcome.get("ok"), outcome)
        self.assertEqual(outcome.get("reconstruction"), "cpu_assign")
        self.assertEqual(outcome.get("fallback_count"), 1)
        out = _forward(clip.cond_stage_model.clip_l)
        self.assertTrue(torch.allclose(out, self.ref, rtol=1e-2, atol=1e-2), "parity")

    def test_native_copy_invoked_exactly_once(self) -> None:
        clip = _FakeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.fx.path1]), trace=_RecordingTrace()
            )
        manifest = cfh.get_clip_manifest(clip)
        manifest["files"][0]["path"] = os.path.join(self.fx.tmpdir, "gone.safetensors")
        cfh.attach_clip_manifest(clip, manifest)
        native = _FakeClip()
        native.cond_stage_model.clip_l.transformer.load_state_dict(
            {k: v.clone() for k, v in self.fx.leaf_sd.items()}, strict=False
        )
        with patch.object(wiring, "_invoke_native_clip_loader", return_value=native) as inv:
            outcome = wiring._hydrate_clip_on_demand(clip, trace=_RecordingTrace())
        inv.assert_called_once()
        self.assertTrue(outcome.get("ok"), outcome)
        self.assertEqual(outcome.get("reconstruction"), "native_copy")
        self.assertGreater(outcome.get("params_copied", 0), 0)
        out = _forward(clip.cond_stage_model.clip_l)
        self.assertTrue(torch.allclose(out, self.ref, rtol=1e-2, atol=1e-2), "parity")


@unittest.skipUnless(CUDA_OK, "CUDA required")
class TestSnapshotRoundTrip(unittest.TestCase):
    """Proof 1 + restore semantics: the stripped structure survives a
    serialization round trip with its manifest and rehydrates."""

    def setUp(self) -> None:
        self.fx = ClipFhFixture()
        self.ref = _reference(self.fx.leaf)

    def tearDown(self) -> None:
        self.fx.cleanup()

    def test_cloudpickle_round_trip(self) -> None:
        if not CLOUDPICKLE_OK:
            self.skipTest("cloudpickle not installed")
        import cloudpickle

        clip = _FakeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.fx.path1]), trace=_RecordingTrace()
            )
        blob = cloudpickle.dumps(clip)
        self.assertLess(len(blob), 200_000, "stripped structure must be small")
        restored = cloudpickle.loads(blob)
        self.assertTrue(cfh.clip_weights_excluded(restored))
        self.assertIsNotNone(cfh.get_clip_manifest(restored))
        for name, param in restored.cond_stage_model.named_parameters():
            self.assertTrue(getattr(param, "is_meta", False), name)
        outcome = wiring._hydrate_clip_on_demand(restored, trace=_RecordingTrace())
        self.assertTrue(outcome.get("ok"), outcome)
        out = _forward(restored.cond_stage_model.clip_l)
        self.assertTrue(torch.allclose(out, self.ref, rtol=1e-2, atol=1e-2), "parity")


@unittest.skipUnless(CUDA_OK, "CUDA required")
class TestD2TelemetryIntegration(unittest.TestCase):
    """Events ride the same trace as D2's forensics with the same shape."""

    def test_events_flow_through_d2_trace(self) -> None:
        try:
            from comfymodal_runtime.clip_cold_path_forensics import ClipColdPathForensics
        except Exception:
            self.skipTest("D2 forensics module unavailable")
        fx = ClipFhFixture()
        try:
            trace = _RecordingTrace()
            forensics = ClipColdPathForensics(enabled=True, trace=trace)
            clip = _FakeClip()
            with patch.dict(
                os.environ,
                {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
                clear=False,
            ):
                wiring.maybe_prepare_clip_snapshot_exclusion(
                    fx.cpu_models(clip, [fx.path1]), trace=trace
                )
            wiring._hydrate_clip_on_demand(clip, trace=trace)
            names = trace.names()
            self.assertIn("clip_fh_hydration_start", names)
            self.assertIn("clip_fh_hydration_end", names)
            self.assertTrue(forensics is not None)
        finally:
            fx.cleanup()


class TestSuperChainProbe(unittest.TestCase):
    """Items 1-2: a leaf whose ``load_sd`` is a trivial
    ``return super().load_sd(sd)`` forward (SDXLClipG -> SDClipModel pattern)
    resolves through the MRO to the canonical assign-forwarding body instead
    of being marked ineligible; unresolvable chains and non-forwarding
    bodies fail closed."""

    def setUp(self) -> None:
        self.fx = ClipFhFixture()

    def tearDown(self) -> None:
        self.fx.cleanup()

    def _clip_with_csm(self, csm: torch.nn.Module) -> _FakeClip:
        clip = _FakeClip()
        clip.cond_stage_model = csm
        clip.patcher = _FakePatcher(csm)
        return clip

    def test_super_forward_leaf_resolves_and_eligible(self) -> None:
        clip = self._clip_with_csm(_SuperChainCSM())
        ok, detail = cfh.can_assign_sd_supported(clip)
        self.assertTrue(ok, detail)
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.fx.path1]), trace=_RecordingTrace()
            )
        self.assertEqual(result["status"], "excluded", result)
        manifest = cfh.get_clip_manifest(clip)
        self.assertIsNotNone(manifest)
        self.assertTrue(manifest["eligible"], manifest.get("reason"))
        self.assertTrue(manifest["assign_bind_supported"])

    def test_unresolvable_super_chain_fails_closed(self) -> None:
        clip = self._clip_with_csm(_NeverResolvingCSM())
        ok, detail = cfh.can_assign_sd_supported(clip)
        self.assertFalse(ok, detail)
        self.assertIn("super() chain unresolved", detail)

    def test_body_without_assign_forward_rejected(self) -> None:
        # References can_assign_sd but never forwards assign= to
        # load_state_dict — the strengthened probe must reject it.
        clip = self._clip_with_csm(_FlagNoAssignCSM())
        ok, detail = cfh.can_assign_sd_supported(clip)
        self.assertFalse(ok, detail)


class TestTokenizerBlobKeys(unittest.TestCase):
    """Item 3: structural tokenizer blobs (spiece_model / tekken_model /
    tokenizer_json) are excluded from the capability gates and the frozen
    manifest evidence, but the actual bind state dict still carries them
    (strict=False tolerates unexpected keys)."""

    def setUp(self) -> None:
        self.fx = ClipFhFixture()
        import safetensors.torch

        blob_sd = dict(self.fx.leaf_sd)
        blob_sd["spiece_model"] = torch.zeros(4, dtype=torch.uint8)
        self.blob_path = os.path.join(self.fx.tmpdir, "blob.safetensors")
        safetensors.torch.save_file(blob_sd, self.blob_path)

    def tearDown(self) -> None:
        self.fx.cleanup()

    def test_blob_excluded_from_manifest_but_eligible(self) -> None:
        clip = _FakeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.blob_path]), trace=_RecordingTrace()
            )
        self.assertEqual(result["status"], "excluded", result)
        manifest = cfh.get_clip_manifest(clip)
        self.assertIsNotNone(manifest)
        self.assertTrue(manifest["eligible"], manifest.get("reason"))
        file_entry = manifest["files"][0]
        self.assertNotIn("spiece_model", file_entry["key_set"])
        self.assertNotIn("spiece_model", file_entry["key_shapes"])
        self.assertIn("emb.weight", file_entry["key_set"])
        self.assertEqual(file_entry["dtype"], "torch.float16")

    def test_blob_key_carried_through_bind(self) -> None:
        clip = _FakeClip()
        raw = dict(self.fx.leaf_sd)
        raw["spiece_model"] = torch.zeros(4, dtype=torch.uint8)
        ok, evidence = cfh.hydrate_clip_bind(
            clip, [raw], require_no_meta=False, expect_device=None
        )
        self.assertTrue(ok, evidence)
        self.assertIn("share storage", evidence)

    def test_blob_full_round_trip_cpu_assign(self) -> None:
        clip = _FakeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "0"},
            clear=False,
        ):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.blob_path]), trace=_RecordingTrace()
            )
        self.assertEqual(result["status"], "excluded", result)
        outcome = wiring._hydrate_clip_on_demand(clip, trace=_RecordingTrace())
        self.assertTrue(outcome.get("ok"), outcome)
        self.assertEqual(outcome.get("reconstruction"), "cpu_assign")
        self.assertTrue(cfh.clip_hydrated(clip))
        self.assertTrue("share storage" in str(outcome.get("zero_copy_evidence", "")))


class TestDemandWrapperOrderIndependence(unittest.TestCase):
    """Item 4: D3's demand wrapper resolves the class-level ``load_model`` at
    CALL time, so a class-level wrapper installed before OR after D3 both
    fire (order-independent D3/D2 coexistence).  The D3 instance wrapper is
    the outermost callable the caller touches (the instance attribute
    shadows the class attribute); it delegates to the CURRENT class method,
    so whichever order D2 wraps in, both wrappers participate."""

    def test_class_wrap_after_d3_install_both_fire(self) -> None:
        clip = _FakeClip()
        events: list[str] = []

        def hydrator(c: Any) -> None:
            events.append("d3")

        self.assertTrue(cfh.install_demand_wrapper(clip, hydrator))
        orig_cls = type(clip).load_model

        def d2_wrapper(self, tokens=None, **kwargs):
            events.append("d2")
            return orig_cls(self, tokens, **kwargs)

        type(clip).load_model = d2_wrapper
        try:
            result = clip.load_model({})
        finally:
            type(clip).load_model = orig_cls
        self.assertEqual(events, ["d3", "d2"], "both wrappers must fire")
        self.assertIs(result, clip.patcher)

    def test_class_wrap_before_d3_install_both_fire(self) -> None:
        clip = _FakeClip()
        events: list[str] = []
        orig_cls = type(clip).load_model

        def d2_wrapper(self, tokens=None, **kwargs):
            events.append("d2")
            return orig_cls(self, tokens, **kwargs)

        type(clip).load_model = d2_wrapper
        try:
            def hydrator(c: Any) -> None:
                events.append("d3")

            self.assertTrue(cfh.install_demand_wrapper(clip, hydrator))
            result = clip.load_model({})
        finally:
            type(clip).load_model = orig_cls
        self.assertEqual(events, ["d3", "d2"], "both wrappers must fire")
        self.assertIs(result, clip.patcher)

    def test_instance_wrap_after_d3_d2_is_outer(self) -> None:
        # D2's real forensics wraps the clip INSTANCE, capturing whatever
        # load_model is current (the D3 instance wrapper) — so the D2
        # wrapper becomes the outer wrapper and fires first.
        clip = _FakeClip()
        events: list[str] = []

        def hydrator(c: Any) -> None:
            events.append("d3")

        self.assertTrue(cfh.install_demand_wrapper(clip, hydrator))
        original = clip.load_model

        def d2_wrapper(tokens=None, **kwargs):
            events.append("d2")
            return original(tokens, **kwargs)

        clip.load_model = d2_wrapper
        try:
            result = clip.load_model({})
        finally:
            clip.__dict__.pop("load_model", None)
        self.assertEqual(events, ["d2", "d3"], "outer D2 wrapper fires first")
        self.assertIs(result, clip.patcher)


class TestWiringImportStandalone(unittest.TestCase):
    def test_module_imports_without_comfy(self) -> None:
        self.assertTrue(callable(wiring.maybe_prepare_clip_snapshot_exclusion))
        self.assertTrue(callable(wiring.maybe_install_clip_fh_demand))
        self.assertTrue(callable(wiring.clip_fh_request_summary))


if __name__ == "__main__":
    unittest.main(verbosity=2)
