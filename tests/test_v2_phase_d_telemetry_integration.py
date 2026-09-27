"""Phase-D telemetry integration gate tests (Task 7b/7d/9/10 coverage gaps).

One self-contained unittest module covering the six verified coverage gaps
from the Phase-D integration gate:

  GAP 1  D2 must NOT report a CPU->GPU ModelPatcher transfer when D3 created
         GPU-resident parameters (Task 7b).  Resident loads count zero
         transfer ops / zero H2D bytes; cold loads still count (proving the
         instrumentation is not broken).  CUDA-gated GPU variant plus a
         CPU-safe variant that exercises the same accounting logic through a
         mocked, device-labelled patcher load.
  GAP 2  D2 truthfully records a native fallback activation (Task 7d):
         injected failing fastsafetensors path -> native fallback runs once,
         fallback_count == 1, native loader invoked exactly once, D2 sees the
         native activation (encode_calls == 1, gpu-wait span present), and no
         partial owner state leaks (no OWNER_ATTR / fastsafe-owner attr, next
         encode not blocked).
  GAP 3  No meta/empty invalid model escapes to encode (Task 10): after the
         fallback, every parameter is real (not meta, numel > 0) and a parity
         encode succeeds.
  GAP 4  Corrupted / mismatched CLIP manifests fail closed (Task 10): corrupt
         JSON header file, truncated manifest dict, schema-version mismatch and
         key-set mismatch (manifest key_set != replayed sd keys after blob
         exclusion) each fail closed - no strip performed, native path
         available, no exception escapes, status reports the reason.
  GAP 5  Explicit tokenizer / non-tensor structural retention in the snapshot
         round trip (Task 10): identity preserved capture -> restore alongside
         the existing weight-removal assertions (cloudpickle-gated, mirrors
         the production round-trip test).
  GAP 6  Cross-summary disjointness D2/D3/D4/D5 (Task 9): one synthetic trace
         with all four layers; D3 hydration nested inside the D2 gpu-wait
         wall; no event interval attributed to two layer summaries; the D4
         pipeline reconcile reports accounting_disjoint=True; each summarizer
         consumes only its own event names.  Pure structural functions on
         synthetic monotonic stamps - no real timers.

All fixtures are synthetic torch modules + mocked patcher paths; ``comfy`` is
never imported.  CUDA-dependent tests skip cleanly (skipUnless pattern mirrors
``tests/test_v2_clip_fast_hydration_production.py``).
"""

from __future__ import annotations

import importlib.util
import os
import struct
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import torch

from comfymodal_runtime import clip_fast_hydration as cfh
from comfymodal_runtime import clip_fast_hydration_wiring as wiring
from comfymodal_runtime import trace as trace_mod
from comfymodal_runtime import unet_fastsafetensors as fs
from comfymodal_runtime.clip_cold_path_forensics import ClipColdPathForensics
from comfymodal_runtime.wait_attribution import (
    WAIT_LOADER,
    WAIT_SAMPLER_LANE,
    build_node_wait_report,
    build_remote_setup_reconciliation,
    build_wait_reconciliation,
    classify_node_wait,
    extract_wait_windows,
)


CUDA_OK = torch.cuda.is_available()
FASTSAFE_OK = importlib.util.find_spec("fastsafetensors") is not None
CLOUDPICKLE_OK = importlib.util.find_spec("cloudpickle") is not None


# ═══════════════════════════════════════════════════════════════════════════
# Synthetic fixtures (mirror tests/test_v2_clip_fast_hydration_production.py
# and tests/test_v2_clip_cold_forensics.py)
# ═══════════════════════════════════════════════════════════════════════════


class _TinyTransformer(torch.nn.Module):
    """CLIPTextModel-like module: flat HF-style keys (mirrors comfy.clip_model,
    whose state dict receives the file sd directly from SDClipModel.load_sd)."""

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
    load_state_dict(assign=can_assign_sd) — the canonical Comfy body."""

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


class _EncodeCSM(torch.nn.Module):
    """Container with a measurable encode_token_weights (for the D2 forward
    wrapper) plus Comfy-style leaf dispatch."""

    def __init__(self, dtype: torch.dtype = torch.float16):
        super().__init__()
        self.clip_l = _Leaf(dtype=dtype)
        self.clip_g = _Leaf(prefix="g", dtype=dtype)

    def load_sd(self, sd: dict) -> Any:
        if any(k.startswith("gtransformer.") for k in sd):
            return self.clip_g.load_sd(sd)
        return self.clip_l.load_sd(sd)

    def encode_token_weights(self, tokens):
        return (tokens, None)


class _EncodeClip:
    """CLIP-like object with tokenize -> load_model -> encode decomposition
    (mirrors the D2 forensics fake CLIP) and a real tokenizer attribute."""

    def __init__(self, dtype: torch.dtype = torch.float16):
        self.cond_stage_model = _EncodeCSM(dtype=dtype)
        self.patcher = _ResidentAwarePatcher(self.cond_stage_model)
        self.tokenizer = object()

    def tokenize(self, text):
        return {"l": [["a"], ["b"]]}

    def load_model(self, tokens={}):
        self.patcher.load(device_to=self.patcher.load_device, full_load=False)
        return self.patcher

    def encode_from_tokens(self, tokens, return_pooled=False, **kwargs):
        self.tokenize("")
        self.load_model(tokens)
        self.cond_stage_model.encode_token_weights(tokens)
        return [[tokens, {"pooled_output": None}]]

    def encode_from_tokens_scheduled(self, tokens, **kwargs):
        return self.encode_from_tokens(tokens, **kwargs)


class _ResidentAwarePatcher:
    """ModelPatcher mock whose load skips patch_weight_to_device for params
    already on the target device — mirroring the residency semantics of
    comfy.model_patcher.ModelPatcher.load that the D2 instrumentation relies
    on to detect D3-created GPU residency."""

    def __init__(self, model: Any = None):
        self.model = model if model is not None else _TinyEncoder()
        self.load_device = torch.device("cuda:0" if CUDA_OK else "cpu")
        self.offload_device = torch.device("cpu")
        self.is_clip = True

    def is_dynamic(self) -> bool:
        return False

    def model_size(self) -> int:
        return sum(int(p.numel() * p.element_size()) for p in self.model.parameters())

    def load(self, device_to=None, lowvram_model_memory=0, force_patch_weights=False, full_load=False):
        if device_to is None or full_load:
            device_to = self.load_device
        for name, param in self.model.named_parameters():
            if str(param.device) != str(device_to):
                self.patch_weight_to_device(name, device_to=device_to)
        self.model.device = device_to
        self.model.model_loaded_weight_memory = sum(
            int(p.numel() * p.element_size()) for p in self.model.parameters()
        )
        self.model.model_lowvram = False
        return self.model

    def patch_weight_to_device(self, key, device_to=None, inplace_update=False, return_weight=False, force_cast=False):
        weight = getattr(self.model, key, None)
        if weight is None or device_to is None:
            return weight
        # The accounting wrapper counts the op regardless; only actually move
        # when the destination is real (CPU-safe tests label cuda without it).
        if str(device_to) != str(weight.device) and (
            device_to.type == "cpu" or torch.cuda.is_available()
        ):
            weight = weight.to(device_to)
        return weight

    def partially_load(self, device_to=None, lowvram_model_memory=0):
        self.model.device = device_to or self.load_device
        return self.model

    def partially_unload(self, device_to=None, memory_to_free=0):
        self.model.device = device_to or self.offload_device
        return memory_to_free

    def detach(self, unpatch_weights=True):
        return None


class _TinyEncoder(torch.nn.Module):
    """Small synthetic encoder with three known-size float16 parameters
    (mirrors the D2 forensics _FakeModel) for transfer accounting."""

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


class _FakeMM:
    """Mock comfy.model_management surface (load_models_gpu drives patcher.load)."""

    def load_models_gpu(self, models, memory_required=0, force_patch_weights=False, **kwargs):
        for model in models:
            if hasattr(model, "load"):
                model.load(device_to=getattr(model, "load_device", None), full_load=False)

    def free_memory(self, memory_required, device, keep_loaded=[], **kwargs):
        return memory_required

    def soft_empty_cache(self):
        return None


class _DummyCache:
    def lookup_many(self, base_ctx, entries):
        return {}, [], 0, 0


class _DummyTorch:
    def synchronize(self):
        return None


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


# ── Tokenizer singleton (identity-preserving pickling for GAP 5) ────────────

_TOKENIZER_INSTANCE: Any = None


def _tokenizer_factory():
    global _TOKENIZER_INSTANCE
    if _TOKENIZER_INSTANCE is None:
        _TOKENIZER_INSTANCE = _RetainedTokenizer()
    return _TOKENIZER_INSTANCE


class _RetainedTokenizer:
    """Tokenizer-like object whose pickling preserves instance identity
    (mirrors a Comfy config-singleton tokenizer retained across the snapshot
    round trip)."""

    def __init__(self):
        self.name = "bpe"
        self.vocab = 49408

    def __reduce__(self):
        return (_tokenizer_factory, ())


# ── Helpers ─────────────────────────────────────────────────────────────────

def _new_forensics(**kwargs) -> ClipColdPathForensics:
    kwargs.setdefault("enabled", True)
    return ClipColdPathForensics(**kwargs)


def _install_with_cleanup(
    testcase: unittest.TestCase,
    forensics: ClipColdPathForensics,
    targets: SimpleNamespace,
) -> dict[str, str]:
    statuses = forensics.install(targets=targets)
    testcase.addCleanup(forensics.uninstall)
    return statuses


def _forensics_targets(patcher: Any = None, clip_cls: Any = None) -> SimpleNamespace:
    return SimpleNamespace(
        mm_module=_FakeMM(),
        mp_class=_ResidentAwarePatcher if patcher is None else type(patcher),
        sd_clip_class=clip_cls if clip_cls is not None else _EncodeClip,
        cache_class=_DummyCache,
        torch_module=_DummyTorch(),
    )


def _events_by_name(forensics: ClipColdPathForensics) -> dict[str, list[dict]]:
    by_name: dict[str, list[dict]] = {}
    for event in forensics._events:
        by_name.setdefault(event["name"], []).append(event)
    return by_name


def _param_bytes(module: torch.nn.Module) -> int:
    return sum(int(p.numel() * p.element_size()) for p in module.parameters())


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


class _FhFixture:
    """Writes a real single-file clip_l.safetensors from a synthetic encoder."""

    def __init__(self) -> None:
        self.tmpdir = tempfile.mkdtemp(
            prefix="phase_d_int_",
            dir=r"C:\Users\parla\AppData\Local\Temp\opencode"
            if os.path.isdir(r"C:\Users\parla\AppData\Local\Temp\opencode")
            else None,
        )
        import safetensors.torch

        self.leaf = _Leaf()
        self.leaf_sd = {
            k: v.detach().clone() for k, v in self.leaf.transformer.state_dict().items()
        }
        self.path1 = os.path.join(self.tmpdir, "clip_l.safetensors")
        safetensors.torch.save_file(self.leaf_sd, self.path1)

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


class _FallbackTestBase(unittest.TestCase):
    """Shared setup for the GAP 2/3/4 fallback scenarios."""

    def setUp(self) -> None:
        self.fx = _FhFixture()
        self.addCleanup(self.fx.cleanup)
        wiring._RECORD.clear()
        wiring._LAST_EXCLUDED.clear()
        self.addCleanup(wiring._RECORD.clear)
        self.addCleanup(wiring._LAST_EXCLUDED.clear)
        self.ref = _reference(self.fx.leaf)

    def _prepare_excluded(self) -> _EncodeClip:
        clip = _EncodeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.fx.path1]), trace=_RecordingTrace()
            )
        self.assertEqual(result["status"], "excluded", result)
        return clip

    def _prepare_manifest_only(self) -> _EncodeClip:
        clip = _EncodeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "0", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.fx.path1]), trace=_RecordingTrace()
            )
        self.assertEqual(result["status"], "manifest_only", result)
        return clip

    def _install_d2(self, clip: Any) -> tuple[ClipColdPathForensics, _RecordingTrace]:
        trace = _RecordingTrace()
        forensics = _new_forensics(request_id="gap_fallback", trace=trace)
        forensics.begin_request("gap_fallback")
        statuses = _install_with_cleanup(self, forensics, _forensics_targets(clip_cls=_EncodeClip))
        self.assertEqual(statuses["clip_encode"], "installed")
        self.assertEqual(statuses["clip_load_model"], "installed")
        return forensics, trace

    def _install_d3(self, clip: Any, trace: _RecordingTrace) -> None:
        with patch.dict(
            os.environ,
            {wiring._FLAG_FAST: "1", wiring._FLAG_EXCLUDE: "1"},
            clear=False,
        ):
            status = wiring.maybe_install_clip_fh_demand(
                SimpleNamespace(clip=clip), trace=trace
            )
        self.assertEqual(status["status"], "installed", status)

    def _native_clip_with_real_weights(self) -> _EncodeClip:
        native = _EncodeClip()
        native.cond_stage_model.clip_l.transformer.load_state_dict(
            {k: v.clone() for k, v in self.fx.leaf_sd.items()}, strict=False
        )
        return native

    def _break_fast_and_manifest(self, clip: Any) -> None:
        """Point the frozen manifest at a missing file so both the fast path
        and the CPU-assign fallback fail, forcing the native-copy fallback."""
        manifest = cfh.get_clip_manifest(clip)
        manifest["files"][0]["path"] = os.path.join(self.fx.tmpdir, "gone.safetensors")
        cfh.attach_clip_manifest(clip, manifest)


# ═══════════════════════════════════════════════════════════════════════════
# GAP 1 — D2 must NOT report a CPU->GPU transfer for D3-resident models (7b)
# ═══════════════════════════════════════════════════════════════════════════


@unittest.skipUnless(CUDA_OK, "CUDA required")
class TestD2ResidentTransferAccountingGpu(unittest.TestCase):
    """Real CUDA-resident parameters: a load of an already-resident model
    records zero transfer ops / zero H2D bytes while a cold model still
    counts a transfer (instrumentation is not broken)."""

    def test_resident_no_transfer_then_cold_transfers(self) -> None:
        forensics = _new_forensics(request_id="gap1_gpu", cast_accounting=True)

        # ── Resident: D3 already placed the parameters on CUDA ──
        forensics.begin_request("gap1_gpu_resident")
        model = _TinyEncoder()
        model.cuda()
        total = _param_bytes(model)
        model.device = torch.device("cuda:0")
        model.model_loaded_weight_memory = total
        patcher = _ResidentAwarePatcher(model)
        targets = _forensics_targets(patcher=patcher)
        _install_with_cleanup(self, forensics, targets)
        targets.mm_module.load_models_gpu([patcher])
        meta = _events_by_name(forensics)["clip_cold_patcher_load_end"][0]["metadata"]
        self.assertTrue(meta["resident_before"])
        self.assertEqual(meta["already_resident_bytes"], total)
        self.assertEqual(meta["transfer_ops"], 0)
        summary = forensics.end_request()
        self.assertEqual(summary["total_h2d_bytes"], 0)
        self.assertEqual(summary["total_transfer_ops"], 0)

        # ── Cold: CPU model still counts a real transfer ──
        forensics.begin_request("gap1_gpu_cold")
        cold_model = _TinyEncoder()
        cold_patcher = _ResidentAwarePatcher(cold_model)
        cold_targets = _forensics_targets(patcher=cold_patcher)
        _install_with_cleanup(self, forensics, cold_targets)
        cold_targets.mm_module.load_models_gpu([cold_patcher])
        meta2 = _events_by_name(forensics)["clip_cold_patcher_load_end"][0]["metadata"]
        self.assertFalse(meta2["resident_before"])
        self.assertEqual(meta2["already_resident_bytes"], 0)
        self.assertEqual(meta2["transfer_ops"], 3)
        self.assertEqual(meta2["bytes_transferred"], _param_bytes(cold_model))
        summary2 = forensics.end_request()
        self.assertEqual(summary2["total_transfer_ops"], 3)
        self.assertEqual(summary2["total_h2d_bytes"], _param_bytes(cold_model))


class TestD2ResidentTransferAccountingCpuSafe(unittest.TestCase):
    """CPU-safe variant exercising the same accounting logic via a mocked,
    device-labelled patcher load: the per-op transfer accounting and the
    resident_before / already_resident_bytes residency detection are pure
    string comparisons, so no real CUDA is required."""

    def test_resident_no_transfer_then_cold_transfers_via_mock(self) -> None:
        forensics = _new_forensics(request_id="gap1_cpu", cast_accounting=True)

        # ── Resident: load_device cpu, parameters already on cpu ──
        forensics.begin_request("gap1_cpu_resident")
        model = _TinyEncoder()
        total = _param_bytes(model)
        model.device = torch.device("cpu")
        model.model_loaded_weight_memory = total
        patcher = _ResidentAwarePatcher(model)
        patcher.load_device = torch.device("cpu")
        targets = _forensics_targets(patcher=patcher)
        _install_with_cleanup(self, forensics, targets)
        targets.mm_module.load_models_gpu([patcher])
        meta = _events_by_name(forensics)["clip_cold_patcher_load_end"][0]["metadata"]
        self.assertTrue(meta["resident_before"])
        self.assertEqual(meta["already_resident_bytes"], total)
        self.assertEqual(meta["transfer_ops"], 0)
        summary = forensics.end_request()
        self.assertEqual(summary["total_h2d_bytes"], 0)
        self.assertEqual(summary["total_transfer_ops"], 0)

        # ── Cold: parameters live somewhere other than load_device ──
        forensics.begin_request("gap1_cpu_cold")
        cold_model = _TinyEncoder()
        cold_patcher = _ResidentAwarePatcher(cold_model)  # load_device cuda:0 label
        cold_targets = _forensics_targets(patcher=cold_patcher)
        _install_with_cleanup(self, forensics, cold_targets)
        cold_targets.mm_module.load_models_gpu([cold_patcher])
        meta2 = _events_by_name(forensics)["clip_cold_patcher_load_end"][0]["metadata"]
        self.assertFalse(meta2["resident_before"])
        self.assertEqual(meta2["already_resident_bytes"], 0)
        self.assertEqual(meta2["transfer_ops"], 3)
        self.assertEqual(meta2["bytes_transferred"], _param_bytes(cold_model))
        summary2 = forensics.end_request()
        self.assertEqual(summary2["total_transfer_ops"], 3)
        self.assertEqual(summary2["total_h2d_bytes"], _param_bytes(cold_model))


# ═══════════════════════════════════════════════════════════════════════════
# GAP 2 — D2 truthfully records a native fallback activation (7d)
# ═══════════════════════════════════════════════════════════════════════════


class TestNativeFallbackActivation(_FallbackTestBase):
    """Injected failing fast path -> native fallback runs exactly once, D2
    records the native activation, and no partial owner state leaks."""

    def test_native_fallback_activation_recorded_by_d2(self) -> None:
        clip = self._prepare_excluded()
        self._break_fast_and_manifest(clip)

        forensics, trace = self._install_d2(clip)
        self._install_d3(clip, trace)

        native = self._native_clip_with_real_weights()
        with patch.object(
            wiring, "_fastsafe_load", side_effect=RuntimeError("simulated fast failure")
        ):
            with patch.object(
                wiring, "_invoke_native_clip_loader", return_value=native
            ) as inv:
                result = clip.encode_from_tokens({"l": [["a"], ["b"]]})
        self.assertIsNotNone(result)
        inv.assert_called_once()  # native loader invoked exactly once

        # D3 attribution: native fallback recorded truthfully.
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["hydration_source"], cfh.MODE_NATIVE)
        self.assertEqual(summary["fallback_count"], 1)
        self.assertTrue(summary["hydrated"])

        # D2 accounting sees the native activation.
        fsum = forensics.end_request()
        self.assertEqual(fsum["encode_calls"], 1)
        self.assertEqual(fsum["load_calls"], 1)
        names = [e["name"] for e in fsum["events"]]
        self.assertIn("clip_cold_gpu_wait_start", names)
        self.assertIn("clip_cold_gpu_wait_end", names)
        self.assertIn("clip_cold_patcher_load_end", names)

        # No leaked partial owner state after the failure.
        self.assertFalse(hasattr(clip.patcher, cfh.OWNER_ATTR))
        for module in clip.cond_stage_model.modules():
            self.assertFalse(hasattr(module, cfh._FASTSAFE_OWNER_ATTR))

        # No pending hydration marker blocks the next encode.
        self.assertTrue(cfh.clip_hydrated(clip))
        clip.encode_from_tokens({"l": [["c"], ["d"]]})
        summary2 = wiring.clip_fh_request_summary("")
        self.assertEqual(summary2["hydration_source"], cfh.MODE_RESIDENT)


# ═══════════════════════════════════════════════════════════════════════════
# GAP 3 — no meta/empty invalid model escapes to encode (Task 10)
# ═══════════════════════════════════════════════════════════════════════════


class TestNoInvalidModelEscapesToEncode(_FallbackTestBase):
    """After the corrupted/missing fast path, the model that reaches encode
    carries real (non-meta, non-empty) parameters and a parity encode
    succeeds."""

    def test_post_fallback_parameters_real_and_parity(self) -> None:
        clip = self._prepare_excluded()
        self._break_fast_and_manifest(clip)

        forensics, trace = self._install_d2(clip)
        self._install_d3(clip, trace)

        native = self._native_clip_with_real_weights()
        with patch.object(
            wiring, "_fastsafe_load", side_effect=RuntimeError("simulated fast failure")
        ):
            with patch.object(wiring, "_invoke_native_clip_loader", return_value=native):
                result = clip.encode_from_tokens({"l": [["a"], ["b"]]})
        self.assertIsNotNone(result)

        # Every parameter that reaches encode is real and non-empty.
        for name, param in clip.cond_stage_model.named_parameters():
            self.assertFalse(getattr(param, "is_meta", False), name)
            self.assertGreater(param.numel(), 0, name)

        # Post-fallback parity encode succeeds.
        out = _forward(clip.cond_stage_model.clip_l)
        self.assertTrue(torch.allclose(out, self.ref, rtol=1e-2, atol=1e-2), "parity after fallback")
        forensics.end_request()


# ═══════════════════════════════════════════════════════════════════════════
# GAP 4 — corrupted / mismatched CLIP manifests fail closed (Task 10)
# ═══════════════════════════════════════════════════════════════════════════


class TestManifestFailClosed(_FallbackTestBase):
    """Corrupt JSON manifest, schema-version mismatch and key-set mismatch
    (manifest key_set != replayed sd keys after blob exclusion) each fail
    closed: no strip performed, native path available, no exception escapes,
    status reports the reason."""

    def test_corrupt_json_file_manifest_fails_closed(self) -> None:
        # A safetensors file whose header is corrupt JSON: _build_manifest
        # must fail closed to an ineligible manifest with the reason reported.
        corrupt = os.path.join(self.fx.tmpdir, "corrupt.safetensors")
        header = b'{"not": "valid json'
        with open(corrupt, "wb") as fh:
            fh.write(struct.pack("<Q", len(header)))
            fh.write(header)
        clip = _EncodeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [corrupt]), trace=_RecordingTrace()
            )
        self.assertEqual(result["status"], "ineligible", result)
        self.assertTrue(result.get("reason"))
        self.assertFalse(cfh.clip_weights_excluded(clip))  # no strip performed
        self.assertIsNone(cfh.get_clip_manifest(clip))
        # The demand gate also refuses; native path is untouched.
        with patch.dict(os.environ, {wiring._FLAG_FAST: "1"}, clear=False):
            status = wiring.maybe_install_clip_fh_demand(
                SimpleNamespace(clip=clip), trace=_RecordingTrace()
            )
        self.assertEqual(status["status"], "no_manifest")
        self.assertFalse(hasattr(clip, cfh.DEMAND_WRAPPER_MARKER))
        self.assertIsNotNone(clip.load_model({}))

    def test_truncated_manifest_dict_fails_closed(self) -> None:
        # A manifest that a corrupt JSON parse produced as a partial object:
        # no "eligible", no "files" — the gate and hydrator fail closed.
        clip = _EncodeClip()
        cfh.attach_clip_manifest(clip, {"schema": 1})
        with patch.dict(os.environ, {wiring._FLAG_FAST: "1"}, clear=False):
            status = wiring.maybe_install_clip_fh_demand(
                SimpleNamespace(clip=clip), trace=_RecordingTrace()
            )
        self.assertEqual(status["status"], "no_manifest")
        self.assertFalse(cfh.clip_weights_excluded(clip))
        outcome = wiring._hydrate_clip_on_demand(clip, trace=_RecordingTrace())
        self.assertEqual(outcome["mode"], cfh.MODE_NATIVE)
        self.assertEqual(outcome.get("reason"), "no_manifest")
        self.assertTrue(outcome.get("ok"))
        self.assertIsNotNone(clip.load_model({}))

    def test_schema_version_mismatch_fails_closed(self) -> None:
        # A frozen manifest claiming an unknown schema cannot be trusted: the
        # fast path is refused and the failure reports a reason with the
        # native path left available and nothing stripped.
        clip = self._prepare_manifest_only()
        manifest = cfh.get_clip_manifest(clip)
        manifest["schema"] = 99
        cfh.attach_clip_manifest(clip, manifest)
        with patch.object(
            wiring, "_fastsafe_load", side_effect=RuntimeError("fast unavailable")
        ):
            outcome = wiring._hydrate_clip_on_demand(clip, trace=_RecordingTrace())
        self.assertEqual(outcome["mode"], cfh.MODE_NATIVE)
        self.assertEqual(outcome["fallback_count"], 1)
        self.assertFalse(outcome.get("ok"))
        self.assertTrue(outcome.get("reason"))  # status reports the reason
        self.assertFalse(cfh.clip_weights_excluded(clip))  # no strip performed
        self.assertIsNotNone(clip.load_model({}))

    def test_key_set_mismatch_verify_fails_closed(self) -> None:
        # The manifest verify function (used by every hydration path before any
        # bind) rejects replay sd key sets that diverge from the frozen
        # manifest, including the blob-exclusion divergence.
        clip = self._prepare_manifest_only()
        entry = cfh.get_clip_manifest(clip)["files"][0]

        # Replay sd carries an unexpected extra key -> mismatch.
        tampered = dict(self.fx.leaf_sd)
        tampered["extra.weight"] = torch.zeros(4, dtype=torch.float16)
        ok, detail = wiring._verify_file_against_manifest(entry, tampered)
        self.assertFalse(ok)
        self.assertIn("key set mismatch", detail)

        # Manifest key_set includes a tokenizer blob key while the replayed
        # view excludes blobs -> mismatch (blob-exclusion divergence).
        entry_with_blob = dict(entry)
        entry_with_blob["key_set"] = sorted(list(entry["key_set"]) + ["spiece_model"])
        blob_sd = dict(self.fx.leaf_sd)
        blob_sd["spiece_model"] = torch.zeros(4, dtype=torch.uint8)
        ok2, detail2 = wiring._verify_file_against_manifest(entry_with_blob, blob_sd)
        self.assertFalse(ok2)
        self.assertIn("key set mismatch", detail2)

        # Pristine replay still verifies: instrumentation is not broken.
        ok3, _ = wiring._verify_file_against_manifest(entry, dict(self.fx.leaf_sd))
        self.assertTrue(ok3)

    def test_key_set_mismatch_pipeline_falls_back_native(self) -> None:
        # End-to-end: a tampered manifest (key_set diverging after blob
        # exclusion) never binds partial state — the failed verification falls
        # back to a clean native reconstruction with real parameters.
        clip = self._prepare_excluded()
        manifest = cfh.get_clip_manifest(clip)
        entry = dict(manifest["files"][0])
        entry["key_set"] = sorted(list(entry["key_set"]) + ["spiece_model"])
        entry["key_shapes"] = dict(entry["key_shapes"])
        entry["key_shapes"]["spiece_model"] = [4]
        manifest["files"] = [entry]
        cfh.attach_clip_manifest(clip, manifest)

        native = self._native_clip_with_real_weights()
        with patch.object(
            wiring, "_fastsafe_load", side_effect=RuntimeError("fast unavailable")
        ):
            with patch.object(
                wiring, "_invoke_native_clip_loader", return_value=native
            ) as inv:
                outcome = wiring._hydrate_clip_on_demand(clip, trace=_RecordingTrace())
        self.assertTrue(outcome.get("ok"), outcome)
        self.assertEqual(outcome.get("reconstruction"), "native_copy")
        self.assertEqual(outcome["fallback_count"], 1)
        inv.assert_called_once()
        for name, param in clip.cond_stage_model.named_parameters():
            self.assertFalse(getattr(param, "is_meta", False), name)
        self.assertFalse(hasattr(clip.patcher, cfh.OWNER_ATTR))


# ═══════════════════════════════════════════════════════════════════════════
# GAP 5 — explicit tokenizer / structural retention in the round trip (Task 10)
# ═══════════════════════════════════════════════════════════════════════════


class TestSnapshotRoundTripRetention(_FallbackTestBase):
    """The tokenizer object and non-tensor structural data survive the
    capture -> restore round trip with identity intact, alongside the existing
    weight-removal assertions (mirrors the production cloudpickle round trip)."""

    def test_tokenizer_and_structure_survive_round_trip(self) -> None:
        if not CLOUDPICKLE_OK:
            self.skipTest("cloudpickle not installed")
        import cloudpickle

        clip = _EncodeClip()
        tokenizer = _tokenizer_factory()
        clip.tokenizer = tokenizer
        clip.config = {"hidden_size": 64, "vocab": 49408}

        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.fx.path1]), trace=_RecordingTrace()
            )
        self.assertEqual(result["status"], "excluded", result)

        # Capture keeps the tokenizer identity intact.
        self.assertIs(clip.tokenizer, tokenizer)

        blob = cloudpickle.dumps(clip)
        self.assertLess(len(blob), 200_000, "stripped structure must be small")
        restored = cloudpickle.loads(blob)

        # Tokenizer identity survives restore; its data is intact.
        self.assertIs(restored.tokenizer, tokenizer)
        self.assertEqual(restored.tokenizer.vocab, 49408)

        # Non-tensor structural data survives.
        self.assertEqual(restored.config, {"hidden_size": 64, "vocab": 49408})

        # Existing weight-removal assertions still hold.
        self.assertTrue(cfh.clip_weights_excluded(restored))
        self.assertIsNotNone(cfh.get_clip_manifest(restored))
        for name, param in restored.cond_stage_model.named_parameters():
            self.assertTrue(getattr(param, "is_meta", False), name)


# ═══════════════════════════════════════════════════════════════════════════
# GAP 6 — cross-summary disjointness D2/D3/D4/D5 (Task 9)
# ═══════════════════════════════════════════════════════════════════════════

# Shared monotonic clock base (ns); offsets below are in ms on top of it.
BASE_MONO_NS = 1_000_000_000_000


def _ms_ns(offset_ms: float) -> int:
    return BASE_MONO_NS + int(offset_ms * 1_000_000)


def _event(name: str, offset_ms: float, process: str = "remote", metadata: dict | None = None) -> dict:
    mono = _ms_ns(offset_ms)
    return {
        "name": name,
        "process": process,
        "wall_unix_ns": mono,
        "monotonic_ns": mono,
        "metadata": dict(metadata or {}),
    }


def _node(node_id: str, class_type: str, start_ms: float, end_ms: float, duration_ms: float | None = None, **extra) -> dict:
    record = {
        "node_id": node_id,
        "class_type": class_type,
        "duration_ms": duration_ms if duration_ms is not None else round(end_ms - start_ms, 3),
        "start_perf_ns": _ms_ns(start_ms),
        "end_perf_ns": _ms_ns(end_ms),
        "pass_outcome": "success",
    }
    record.update(extra)
    return record


def _make_result(events: list[dict], node_records: list[dict] | None = None, report_extra: dict | None = None) -> dict:
    report = {"per_node_timings": list(node_records or [])}
    report.update(report_extra or {})
    return {
        "trace": {"events": list(events), "metadata": {}},
        "pre_sampler_structured_report": report,
    }


# The 22 fastsafe pipeline accounting phases (mirrors test_d4_forensics_reconciliation).
_PIPELINE_PHASE_NAMES = (
    "metrics_init",
    "eligibility",
    "header_config",
    "parity_gate",
    "target_and_mem",
    "worker_creation",
    "worker_submit",
    "join_delay",
    "post_join_prep",
    "post_load_gates",
    "transform_gate",
    "bind",
    "zero_copy_proof",
    "mem2",
    "sweep",
    "final_to",
    "final_sync",
    "validate",
    "patcher",
    "owner_attach",
    "telemetry",
    "return_gap",
)


def _tiled_d4_intervals(total_ms: float = 1000.0, base_offset_ms: float = 600.0) -> list[tuple[str, int, int]]:
    """22 disjoint intervals tiling [base, base + total_ms] exactly (the D4
    pipeline phases, placed after the clip phase block on the shared clock)."""
    durations_ms = [45.0] * 21 + [55.0]
    cursor = _ms_ns(base_offset_ms)
    intervals: list[tuple[str, int, int]] = []
    for name, d in zip(_PIPELINE_PHASE_NAMES, durations_ms):
        end = cursor + int(round(d * 1_000_000))
        intervals.append((name, cursor, end))
        cursor = end
    return intervals


class TestCrossLayerDisjointness(unittest.TestCase):
    """One synthetic trace spanning D2 (clip_cold_*), D3 (clip_fh_hydration_*),
    D4 (fastsafe pipeline phases + meta worker intervals) and D5 (remote-setup
    segments + node wait windows).  Structural assertions only — no real
    timers."""

    def setUp(self) -> None:
        trace_mod._forensic_intervals.clear()
        self.addCleanup(trace_mod._forensic_intervals.clear)

    @staticmethod
    def _span(events: list[dict], name: str) -> tuple[int, int]:
        starts = [e for e in events if e["name"] == name + "_start"]
        ends = [e for e in events if e["name"] == name + "_end"]
        return starts[0]["monotonic_ns"], ends[0]["monotonic_ns"]

    def test_d2_d3_d4_d5_cross_summary_disjointness(self) -> None:
        events = [
            # D5: remote setup segments (before execution).
            _event("remote_method_entry", 0),
            _event("run_plan_identity_capture_start", 50),
            _event("run_plan_identity_capture_end", 55),
            _event("run_plan_first_status_yield", 100),
            _event("runtime_config_start", 120),
            _event("runtime_config_end", 140),
            _event("prompt_executor_invoke_start", 300),
            # D2/D3: clip cold-path spans (execution, after remote setup).
            _event("clip_cold_gpu_wait_start", 400),
            _event("clip_cold_patcher_load_start", 410),
            _event("clip_fh_hydration_start", 420),
            _event("clip_fh_hydration_end", 450),
            _event("clip_cold_patcher_load_end", 470),
            _event("clip_cold_gpu_wait_end", 480),
            _event("clip_cold_encode_start", 490),
            _event("clip_cold_encode_end", 530),
            # D5: node wait windows (graph / sampler lanes).
            _event("graph_wait_start", 550),
            _event("graph_wait_end", 650),
            _event("sampler_lane_wait_start", 660),
            _event("sampler_lane_wait_end", 680),
        ]
        node_records = [
            _node("1", "CLIPLoader", 400, 480, duration_ms=80.0),
            _node("2", "UNETLoader", 480, 550, duration_ms=70.0),
            _node("3", "ImpactSwitch", 550, 680, duration_ms=130.0),
        ]
        result = _make_result(
            events,
            node_records,
            report_extra={"pre_sampler_total_ms": 280.0, "future_wait_ms": 0.0},
        )

        gw_s, gw_e = self._span(events, "clip_cold_gpu_wait")
        lw_s, lw_e = self._span(events, "clip_cold_patcher_load")
        h_s, h_e = self._span(events, "clip_fh_hydration")

        # (i) D3 hydration window is NESTED inside the D2 load wall, which is
        # itself inside the D2 gpu-wait wall — one layer, no cross-attribution.
        self.assertGreaterEqual(lw_s, gw_s)
        self.assertLessEqual(lw_e, gw_e)
        self.assertGreaterEqual(h_s, lw_s)
        self.assertLessEqual(h_e, lw_e)
        self.assertGreater(h_s, lw_s)
        self.assertLess(h_e, lw_e)
        self.assertGreaterEqual(h_s, gw_s)
        self.assertLessEqual(h_e, gw_e)

        # (ii) no event interval attributed to two different layer summaries:
        #   - D2's load wall does not contain D4's pipeline phases
        #   - D5's remote-setup segments contain no D2/D3 clip spans
        #   - D4 phases overlap neither the clip block nor the remote setup.
        d4 = _tiled_d4_intervals()
        ok, detail = trace_mod.forensic_intervals_disjoint(
            [("d2_load_wall", lw_s, lw_e)] + d4
        )
        self.assertTrue(ok, detail)
        ok2, detail2 = trace_mod.forensic_intervals_disjoint(
            [
                ("remote_setup", _ms_ns(0), _ms_ns(300)),
                ("clip_phase_block", _ms_ns(400), _ms_ns(530)),
            ]
            + d4
        )
        self.assertTrue(ok2, detail2)
        self.assertEqual(
            trace_mod.forensic_overlap_ms(_ms_ns(0), _ms_ns(300), gw_s, gw_e), 0.0
        )
        self.assertEqual(
            trace_mod.forensic_overlap_ms(_ms_ns(0), _ms_ns(300), h_s, h_e), 0.0
        )

        # (iii) D4 pipeline reconcile reports accounting_disjoint=True on its
        # own phases and tiles the total exactly.
        rec = fs._fs_pipeline_reconcile(1000.0, d4)
        self.assertTrue(rec["accounting_disjoint"])
        self.assertIsNone(rec["accounting_overlap_detail"])
        self.assertEqual(rec["reconciliation_status"], "OK")
        self.assertEqual(rec["accounting_children_ms"], 1000.0)
        self.assertEqual(rec["residual_ms"], 0.0)

        # D4 meta worker intervals are registered and live strictly inside
        # join_delay; they stay out of the accounting children sum.
        jidx = _PIPELINE_PHASE_NAMES.index("join_delay")
        _jname, js, je = d4[jidx]
        half = (je - js) // 2
        trace_mod.register_forensic_interval(
            "fastsafe_worker_a", start_mono_ns=js, end_mono_ns=js + half
        )
        trace_mod.register_forensic_interval(
            "fastsafe_worker_b", start_mono_ns=js + half, end_mono_ns=je
        )
        reg = trace_mod.forensic_intervals()
        self.assertIn("fastsafe_worker_a", reg)
        self.assertIn("fastsafe_worker_b", reg)
        self.assertGreaterEqual(reg["fastsafe_worker_a"]["start_mono_ns"], js)
        self.assertLessEqual(reg["fastsafe_worker_b"]["end_mono_ns"], je)
        self.assertLessEqual(
            reg["fastsafe_worker_a"]["end_mono_ns"],
            reg["fastsafe_worker_b"]["start_mono_ns"],
        )
        rec2 = fs._fs_pipeline_reconcile(1000.0, d4)
        self.assertTrue(rec2["accounting_disjoint"])
        self.assertEqual(rec2["accounting_children_ms"], 1000.0)

        # (iv) each summarizer consumes only its own event names.
        windows = extract_wait_windows(result)
        self.assertEqual([w.kind for w in windows], [WAIT_SAMPLER_LANE, WAIT_LOADER])
        allowed_sources = {
            "sampler_lane_wait_start->sampler_lane_wait_end",
            "graph_wait_start->graph_wait_end",
        }
        self.assertTrue(all(w.source in allowed_sources for w in windows))

        impact = classify_node_wait(node_records[2], windows)
        self.assertEqual(impact[WAIT_SAMPLER_LANE], 20.0)
        self.assertEqual(impact[WAIT_LOADER], 100.0)
        self.assertEqual(impact["wait_total"], 120.0)
        self.assertEqual(impact["node_non_wait_wall"], 10.0)

        setup = build_remote_setup_reconciliation(result)
        self.assertEqual(setup["remote_setup_total_ms"], 300.0)
        self.assertEqual(
            [seg["ms"] for seg in setup["top_level_segments"]], [100.0, 200.0]
        )
        self.assertEqual(setup["accounting_children_sum"], 300.0)
        self.assertEqual(setup["residual_ms"], 0.0)
        self.assertEqual(setup["status"], "closed")
        by_key = {row["key"]: row for row in setup["nested_details"]}
        self.assertEqual(by_key["identity_capture"]["ms"], 5.0)
        self.assertEqual(by_key["runtime_configuration"]["ms"], 20.0)
        self.assertEqual(by_key["residual_within_plan_receipt"]["ms"], 95.0)
        self.assertEqual(by_key["residual_after_plan_receipt"]["ms"], 180.0)
        self.assertNotIn("clip_cold", str(setup))
        self.assertNotIn("clip_fh", str(setup))

        wait = build_wait_reconciliation(result)
        self.assertEqual(wait["node_wall_sum"], 280.0)
        self.assertEqual(wait["loader_wait_sum"], 100.0)
        self.assertEqual(wait["sampler_lane_wait_sum"], 20.0)
        self.assertEqual(wait["async_model_future_sum"], 0.0)
        self.assertEqual(wait["other_wait_sum"], 0.0)
        self.assertEqual(wait["status"], "closed")

        # D2/D3 pairing yields only clip-layer intervals (nothing from D4/D5
        # event names is attributed to the clip layer).
        d23 = [
            name
            for name in ("clip_cold_gpu_wait", "clip_cold_patcher_load", "clip_cold_encode")
            if any(e["name"] == name + "_start" for e in events)
        ]
        self.assertEqual(len(d23), 3)

    def test_wait_report_uses_only_wait_events(self) -> None:
        events = [
            _event("graph_wait_start", 550),
            _event("graph_wait_end", 650),
            _event("clip_cold_encode_start", 400),
            _event("clip_cold_encode_end", 430),
        ]
        result = _make_result(
            events,
            [_node("1", "CLIPLoader", 400, 480, duration_ms=80.0)],
            report_extra={"pre_sampler_total_ms": 80.0, "future_wait_ms": 0.0},
        )
        windows = extract_wait_windows(result)
        self.assertEqual([w.kind for w in windows], [WAIT_LOADER])
        self.assertEqual(windows[0].source, "graph_wait_start->graph_wait_end")
        report = build_node_wait_report(result)
        self.assertEqual(len(report), 1)
        # The CLIP encode span contributed nothing to the D5 wait report.
        self.assertEqual(report[0][WAIT_LOADER], 0.0)
        self.assertEqual(report[0]["wait_total"], 0.0)
        self.assertEqual(report[0]["node_non_wait_wall"], 80.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
