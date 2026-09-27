"""Task 9: local reproduction of the REAL problematic CLIP restore lifecycle
(D6) plus a regression fixture for the observed bug.

Background — the D6 root cause (proven on the remote run):

The eviction retain-role (launcher pins
``COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1`` +
``COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae``) reloaded a FRESH full-weight CLIP
after the D3 strip and before the memory-snapshot fork, discarding the
excluded object (frozen manifest + demand wrapper).  At restore the served
CLIP was full CPU (399 params, 8.04 GB), native path, ZERO ``clip_fh_*``
hydration events.

The fixes now in the tree:

  * ``modal_app._evict_snapshot_models`` freezes the manifest before eviction
    (deepcopy, no reference to the original clip) and re-applies
    attach + strip + demand-wrapper to the reloaded CLIP pre-fork, emitting
    ``clip_fh_eviction_reconcile``.
  * the restore-site install trace hole was fixed (``self._lifecycle_trace``).
  * ``clip_fast_hydration`` carries an explicit hydration-state taxonomy
    (EXCLUDED_PLACEHOLDER / CPU_NATIVE_MATERIALIZED / GPU_FAST_HYDRATED /
    GPU_NATIVE_LOADED / INVALID/PARTIAL) via ``clip_hydration_state`` (pure,
    JSON-safe, never raises), and ``clip_hydrated()`` is marker-only — CPU
    residency NEVER qualifies.
  * ``clip_fast_hydration_wiring`` emits ``clip_fh_hydration_decision`` on
    EVERY demand branch (decision/reason/state_before/state_detail) plus the
    default-OFF ``clip_state_checkpoint`` helper.

This module pins the full lifecycle locally with synthetic fixtures only (no
``comfy`` import, mirroring ``tests/test_v2_clip_fast_hydration_production.py``):

  A. capture-side exclusion flow (full CPU clip -> excluded placeholder,
     manifest + ``clip_fh_capture`` stats, original storages freed);
  B. the D6 bug flow reproduced as a regression fixture (stripped clip
     discarded -> fresh full-CPU reload with no manifest/wrapper IS the
     observed D6 state) and the FIXED reconcile flow (freeze + attach + strip
     + demand wrapper restores exclusion);
  C. restore-like demand lifecycle (cache MISS -> exactly one CPU-assign
     hydration, cache HIT -> zero hydration, a CPU-materialized model is NEVER
     treated as already-hydrated, encode parity after hydration);
  D. no invalid model escapes (meta-only / no-manifest fails closed with no
     hydration attempted; the fast-path-failure fallback chain runs exactly
     once with no leaked owner state);
  E. request-summary defaults unchanged + live state attached after a demand.

All hydration exercised here is the CPU-safe native reconstruction path
(``cpu_assign``); no CUDA is required.
"""

from __future__ import annotations

import copy
import gc
import json
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import torch

from comfymodal_runtime import clip_fast_hydration as cfh
from comfymodal_runtime import clip_fast_hydration_wiring as wiring


def _reset_wiring_state() -> None:
    wiring._RECORD.clear()
    wiring._LAST_EXCLUDED.clear()
    wiring._LAST_CLIP = None


# ── Synthetic fixtures (mirror tests/test_v2_clip_fast_hydration_production.py) ──


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
        # This synthetic fixture is deliberately CPU-only. Avoid probing CUDA
        # here: the real preload-worker guard must continue rejecting worker
        # calls to torch.cuda.is_available().
        self.load_device = torch.device("cpu")
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


class _SingleClip:
    """CLIP whose cond_stage_model is ONE dispatch leaf (the real-world shape
    for a single-text-encoder CLIP, e.g. the D6 399-param model): the whole
    checkpoint is covered by the one safetensors file, so after the CPU-assign
    hydration EVERY parameter is on CPU and the strict full-structure state
    taxonomy classifies it CPU_NATIVE_MATERIALIZED (a two-leaf container
    rehydrated from a single file would mix CPU + meta and truthfully classify
    INVALID/PARTIAL)."""

    def __init__(self, dtype: torch.dtype = torch.float16):
        self.cond_stage_model = _Leaf(dtype=dtype)
        self.patcher = _FakePatcher(self.cond_stage_model)
        self.tokenizer = object()

    def load_model(self, tokens: Any = None) -> Any:
        return self.patcher


class _RecordingTrace:
    """Lifecycle-trace-like object: prefers ``emit_at`` (as the wiring ``_emit``
    helper does) and records name + metadata for assertions."""

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


class ClipFhFixture:
    """Writes a real single-file clip_l.safetensors from a synthetic encoder so
    a frozen manifest can be built and replayed by the real helpers."""

    def __init__(self) -> None:
        self.tmpdir = tempfile.mkdtemp(
            prefix="clip_fh_restore_lc_",
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
            SimpleNamespace(
                role=f"clip{i + 1}", path=p, size_bytes=os.path.getsize(p), mtime_ns=0
            )
            for i, p in enumerate(paths)
        )
        return SimpleNamespace(
            clip=clip,
            file_facts=facts,
            model_spec={
                "loaders": {
                    "clip": [
                        {"clip_name": os.path.basename(p), "type": "stable_diffusion"}
                        for p in paths
                    ]
                }
            },
        )

    def cleanup(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)


# ── shared helpers ───────────────────────────────────────────────────────────


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


# ═══════════════════════════════════════════════════════════════════════════
# A. TestCaptureExclusionFlow — capture side (real startup)
# ═══════════════════════════════════════════════════════════════════════════


class TestCaptureExclusionFlow(unittest.TestCase):
    """Capture side (startup): a full CPU fake CLIP becomes an excluded
    placeholder with a frozen manifest and truthful capture stats."""

    def setUp(self) -> None:
        _reset_wiring_state()
        self.fx = ClipFhFixture()
        self.addCleanup(self.fx.cleanup)

    def _capture(self, clip: _FakeClip, *, exclude: bool = True, fast: bool = True):
        flags = {
            wiring._FLAG_EXCLUDE: "1" if exclude else "0",
            wiring._FLAG_FAST: "1" if fast else "0",
        }
        trace = _RecordingTrace()
        with patch.dict(os.environ, flags, clear=False):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.fx.path1]), trace=trace
            )
        return result, trace

    def test_capture_full_cpu_to_excluded(self) -> None:
        clip = _FakeClip()  # full CPU payload with random (torch-init) tensors
        expected_count = sum(1 for _ in clip.cond_stage_model.named_parameters())
        expected_bytes = _param_bytes(clip.cond_stage_model)
        self.assertGreater(expected_count, 0)
        self.assertGreater(expected_bytes, 0)
        self.assertEqual(
            cfh.clip_hydration_state(clip)["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED
        )
        for name, param in clip.cond_stage_model.named_parameters():
            self.assertFalse(getattr(param, "is_meta", False), name)
            self.assertEqual(str(param.device), "cpu", name)

        result, trace = self._capture(clip)
        self.assertEqual(result["status"], "excluded", result)
        self.assertTrue(result.get("stripped"))

        # all params are meta placeholders; taxonomy says EXCLUDED_PLACEHOLDER
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_EXCLUDED_PLACEHOLDER)
        self.assertTrue(state["excluded_marker"])
        self.assertEqual(state["params"]["meta"], state["params"]["total"])
        self.assertEqual(state["params"]["cpu"], 0)
        self.assertTrue(cfh.clip_weights_excluded(clip))
        for name, param in clip.cond_stage_model.named_parameters():
            self.assertTrue(getattr(param, "is_meta", False), name)

        # manifest attached + eligible
        manifest = cfh.get_clip_manifest(clip)
        self.assertIsNotNone(manifest)
        self.assertTrue(manifest["eligible"], manifest.get("reason"))
        self.assertEqual(manifest["files"][0]["key_set"], sorted(self.fx.leaf_sd.keys()))

        # clip_fh_capture event carries the exact logical bytes removed
        events = trace.by_name("clip_fh_capture")
        self.assertEqual(len(events), 1, trace.names())
        meta = events[0]["metadata"]
        self.assertEqual(meta["status"], "excluded")
        self.assertEqual(meta["params_replaced"], expected_count)
        self.assertEqual(meta["payload_bytes_removed"], expected_bytes)
        json.dumps(meta)  # JSON-safe

    def test_exclusion_frees_original_storages(self) -> None:
        """Alias audit regression (Task 4): after the strip, NO original storage
        remains reachable from the clip's named_parameters — the visible params
        are meta placeholders with no aliasing to the pre-strip payload."""
        clip = _FakeClip()
        orig: dict[str, tuple[int, int, torch.Tensor]] = {}
        for name, param in clip.cond_stage_model.named_parameters():
            orig[name] = (param.data_ptr(), param.untyped_storage().data_ptr(), param.detach())
        distinct = {ptr for _, ptr, _ in orig.values()}
        self.assertGreater(len(distinct), 1, "fixture must use multiple distinct storages")
        self.assertNotIn(0, distinct, "pre-strip CPU params must own real storage")

        result, _ = self._capture(clip)
        self.assertEqual(result["status"], "excluded", result)

        for name, param in clip.cond_stage_model.named_parameters():
            self.assertTrue(getattr(param, "is_meta", False), name)
            self.assertEqual(param.data_ptr(), 0, name)
            self.assertEqual(param.untyped_storage().data_ptr(), 0, name)
            self.assertNotEqual(param.untyped_storage().data_ptr(), orig[name][1], name)
        current = {
            param.untyped_storage().data_ptr()
            for _, param in clip.cond_stage_model.named_parameters()
        }
        self.assertEqual(current, {0}, current)
        self.assertTrue(current.isdisjoint(distinct), "original storages must be gone")

    def test_capture_without_exclude_keeps_full_cpu(self) -> None:
        """Contrast in the lifecycle: Path-B off captures manifest_only and
        never strips — the full CPU payload survives untouched."""
        clip = _FakeClip()
        result, _ = self._capture(clip, exclude=False, fast=True)
        self.assertEqual(result["status"], "manifest_only", result)
        self.assertFalse(result.get("stripped", False))
        self.assertFalse(cfh.clip_weights_excluded(clip))
        manifest = cfh.get_clip_manifest(clip)
        self.assertIsNotNone(manifest)
        self.assertTrue(manifest["eligible"], manifest.get("reason"))
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertEqual(state["params"]["cpu"], state["params"]["total"])
        for name, param in clip.cond_stage_model.named_parameters():
            self.assertFalse(getattr(param, "is_meta", False), name)


# ═══════════════════════════════════════════════════════════════════════════
# B. TestEvictionReloadLifecycle — the D6 bug flow + the fixed reconcile flow
# ═══════════════════════════════════════════════════════════════════════════


class TestEvictionReloadLifecycle(unittest.TestCase):
    """The D6 bug flow reproduced locally as a regression fixture, plus the
    FIXED reconcile flow (freeze + attach + strip + demand wrapper)."""

    def setUp(self) -> None:
        _reset_wiring_state()
        self.fx = ClipFhFixture()
        self.addCleanup(self.fx.cleanup)

    def _excluded_original(self) -> _FakeClip:
        clip = _FakeClip()
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

    def test_eviction_style_fresh_reload_without_reconcile_is_the_bug(self) -> None:
        """Regression fixture for the EXACT observed D6 state.

        OLD (broken) eviction flow: the stripped excluded clip is discarded
        (``del`` + gc) and the retain-role reloads a FRESH full-weight CLIP
        that carries no frozen manifest and no demand wrapper.  That served
        object is precisely what D6 served at restore: full CPU, native path,
        zero ``clip_fh_*`` hydration events.
        """
        original = self._excluded_original()
        self.assertEqual(
            cfh.clip_hydration_state(original)["state"], cfh.STATE_EXCLUDED_PLACEHOLDER
        )
        del original
        gc.collect()

        fresh = _FakeClip()  # fresh full-weight reload — no manifest, no wrapper
        state = cfh.clip_hydration_state(fresh)
        self.assertEqual(state["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertGreater(state["bytes"]["cpu"], 0)
        self.assertEqual(state["params"]["cpu"], state["params"]["total"])
        self.assertIsNone(cfh.get_clip_manifest(fresh))
        self.assertFalse(cfh.clip_weights_excluded(fresh))
        self.assertFalse(hasattr(fresh, cfh.DEMAND_WRAPPER_MARKER))
        self.assertFalse(cfh.clip_hydrated(fresh))
        # native path works with zero D3 involvement
        self.assertIs(fresh.load_model({}), fresh.patcher)

        # a demand on the served object records no_manifest and hydrates nothing
        trace = _RecordingTrace()
        outcome = wiring._hydrate_clip_on_demand(fresh, trace=trace)
        self.assertEqual(outcome["mode"], cfh.MODE_NATIVE)
        self.assertEqual(outcome["reason"], "no_manifest")
        decisions = trace.by_name("clip_fh_hydration_decision")
        self.assertTrue(decisions, trace.names())
        self.assertEqual(decisions[0]["metadata"]["decision"], "no_manifest")
        self.assertFalse(cfh.clip_hydrated(fresh))
        self.assertEqual(trace.by_name("clip_fh_hydration_end"), [])
        self.assertEqual(
            cfh.clip_hydration_state(fresh)["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED
        )

    def test_reconcile_reattach_restores_exclusion(self) -> None:
        """FIXED flow: the manifest is frozen (deepcopy) BEFORE eviction, then
        attach + strip + demand wrapper re-apply the D3 exclusion to the fresh
        full-weight CLIP pre-fork."""
        original = self._excluded_original()
        frozen = copy.deepcopy(cfh.get_clip_manifest(original))
        self.assertTrue(frozen["eligible"])
        del original
        gc.collect()

        fresh = _FakeClip()  # fresh full-weight reload
        self.assertIsNone(cfh.get_clip_manifest(fresh))
        trace = _RecordingTrace()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            cfh.attach_clip_manifest(fresh, frozen)
            stats = cfh.strip_clip_weights(fresh)
            self.assertGreater(stats["params_replaced"], 0)
            self.assertGreater(stats["payload_bytes_removed"], 0)
            status = wiring.maybe_install_clip_fh_demand(
                SimpleNamespace(clip=fresh), trace=trace
            )
        self.assertEqual(status["status"], "installed", status)

        state = cfh.clip_hydration_state(fresh)
        self.assertEqual(state["state"], cfh.STATE_EXCLUDED_PLACEHOLDER)
        self.assertTrue(state["excluded_marker"])
        for name, param in fresh.cond_stage_model.named_parameters():
            self.assertTrue(getattr(param, "is_meta", False), name)
        manifest = cfh.get_clip_manifest(fresh)
        self.assertIsNotNone(manifest)
        self.assertTrue(manifest["eligible"], manifest.get("reason"))
        self.assertTrue(cfh.clip_weights_excluded(fresh))
        self.assertTrue(hasattr(fresh, cfh.DEMAND_WRAPPER_MARKER))
        self.assertNotEqual(fresh.load_model, type(fresh).load_model, "wrapper must shadow class method")
        install_events = trace.by_name("clip_fh_install")
        self.assertEqual(len(install_events), 1, trace.names())
        self.assertEqual(install_events[0]["metadata"]["status"], "installed")

        # a subsequent demand must NOT treat it as already_hydrated
        trace2 = _RecordingTrace()
        with patch.object(
            wiring, "_fastsafe_load", side_effect=RuntimeError("simulated fast failure")
        ):
            outcome = wiring._hydrate_clip_on_demand(fresh, trace=trace2)
        self.assertTrue(outcome.get("ok"), outcome)
        decisions = trace2.by_name("clip_fh_hydration_decision")
        decision_names = [d["metadata"]["decision"] for d in decisions]
        self.assertNotIn("already_hydrated", decision_names)
        self.assertEqual(decisions[0]["metadata"]["decision"], "fast_path")
        self.assertEqual(
            decisions[0]["metadata"]["state_before"], cfh.STATE_EXCLUDED_PLACEHOLDER
        )
        self.assertTrue(cfh.clip_hydrated(fresh))

    def test_reconcile_reattach_hydrates_on_demand(self) -> None:
        """The reconciled object hydrates through the CPU-safe fallback to a
        fully materialized CPU model with exactly one hydration end event."""
        original = self._excluded_original()
        frozen = copy.deepcopy(cfh.get_clip_manifest(original))
        del original
        gc.collect()

        fresh = _SingleClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            cfh.attach_clip_manifest(fresh, frozen)
            cfh.strip_clip_weights(fresh)
            status = wiring.maybe_install_clip_fh_demand(
                SimpleNamespace(clip=fresh), trace=_RecordingTrace()
            )
        self.assertEqual(status["status"], "installed", status)

        trace = _RecordingTrace()
        with patch.object(
            wiring, "_fastsafe_load", side_effect=RuntimeError("simulated fast failure")
        ):
            outcome = wiring._hydrate_clip_on_demand(fresh, trace=trace)
        self.assertTrue(outcome.get("ok"), outcome)
        self.assertEqual(outcome.get("reconstruction"), "cpu_assign")
        self.assertEqual(outcome.get("fallback_count"), 1)
        ends = trace.by_name("clip_fh_hydration_end")
        self.assertEqual(len(ends), 1, trace.names())
        self.assertTrue(cfh.clip_hydrated(fresh))
        state = cfh.clip_hydration_state(fresh)
        self.assertEqual(state["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertEqual(state["params"]["cpu"], state["params"]["total"])


# ═══════════════════════════════════════════════════════════════════════════
# C. TestDemandLifecycle — restore-like: cache MISS -> first encode demand
# ═══════════════════════════════════════════════════════════════════════════


class TestDemandLifecycle(unittest.TestCase):
    """Restore-like demand lifecycle: cache MISS -> exactly one CPU-assign
    hydration; cache HIT -> zero hydration; a CPU-materialized model is never
    silently treated as fast-hydrated; encode parity after hydration."""

    def setUp(self) -> None:
        _reset_wiring_state()
        self.fx = ClipFhFixture()
        self.addCleanup(self.fx.cleanup)

    def _prepare_excluded_cpu_safe(self, clip: _FakeClip | _SingleClip | None = None):
        """Excluded clip whose frozen manifest forbids the fast path (stays
        CPU-safe and deterministic).  ``clip`` defaults to the single-leaf
        ``_SingleClip`` so post-hydration state asserts the strict
        CPU_NATIVE_MATERIALIZED classification (the D6 real-world shape)."""
        clip = clip if clip is not None else _SingleClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "0"},
            clear=False,
        ):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.fx.path1]), trace=_RecordingTrace()
            )
        self.assertEqual(result["status"], "excluded", result)
        manifest = cfh.get_clip_manifest(clip)
        self.assertFalse(manifest["fast_hydration_allowed"])
        return clip

    def test_cache_miss_one_hydration_from_excluded(self) -> None:
        clip = self._prepare_excluded_cpu_safe()
        trace = _RecordingTrace()
        outcome = wiring._hydrate_clip_on_demand(clip, trace=trace)
        self.assertTrue(outcome.get("ok"), outcome)
        self.assertEqual(outcome.get("mode"), cfh.MODE_NATIVE)
        self.assertEqual(outcome.get("reconstruction"), "cpu_assign")

        decisions = trace.by_name("clip_fh_hydration_decision")
        self.assertTrue(decisions, trace.names())
        first = decisions[0]["metadata"]
        self.assertEqual(first["decision"], "cpu_assign_fallback")
        self.assertEqual(first["state_before"], cfh.STATE_EXCLUDED_PLACEHOLDER)
        self.assertIn("state_detail", first)
        self.assertIn("params", first["state_detail"])
        self.assertIn("devices", first["state_detail"])
        json.dumps(first)  # JSON-safe

        # exactly ONE hydration end event; marker set; params bound on CPU
        ends = trace.by_name("clip_fh_hydration_end")
        self.assertEqual(len(ends), 1, trace.names())
        self.assertTrue(cfh.clip_hydrated(clip))
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertEqual(state["params"]["cpu"], state["params"]["total"])
        self.assertGreater(state["bytes"]["cpu"], 0)

        # no double hydration on a second demand: already_hydrated, zero events
        trace2 = _RecordingTrace()
        outcome2 = wiring._hydrate_clip_on_demand(clip, trace=trace2)
        self.assertEqual(outcome2["mode"], cfh.MODE_RESIDENT)
        self.assertEqual(outcome2["reason"], "already_hydrated")
        d2 = trace2.by_name("clip_fh_hydration_decision")
        self.assertTrue(d2, trace2.names())
        self.assertEqual(d2[0]["metadata"]["decision"], "already_hydrated")
        self.assertEqual(trace2.by_name("clip_fh_hydration_end"), [])

    def test_cache_hit_zero_hydration(self) -> None:
        """Mirror of the production cache-hit proof: MODE_CACHE_HIT, zero
        hydration events (cache-hit requests never encode)."""
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
        self.assertEqual(status["status"], "installed", status)
        self.assertFalse(cfh.clip_hydrated(clip))
        for event in trace.events:
            self.assertNotEqual(event["name"], "clip_fh_hydration_end")
        # Clear the per-request record so the cache-hit attribution is
        # order-independent (same rationale as the production test).
        wiring._RECORD.clear()
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["hydration_source"], cfh.MODE_CACHE_HIT)
        self.assertFalse(summary["hydrated"])

    def test_cpu_materialized_before_demand_is_never_called_already_fast_hydrated(
        self,
    ) -> None:
        """THE regression fixture: a full-CPU fake WITH a frozen manifest
        attached but NO hydrated marker (exactly what a restored-but-
        unreconciled container could look like) must NEVER be treated as
        already fast-hydrated — a CPU-full model can never silently count as
        fast-hydrated."""
        clip = _FakeClip()  # full CPU payload
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "0", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.fx.path1]), trace=_RecordingTrace()
            )
        self.assertEqual(result["status"], "manifest_only", result)
        manifest = cfh.get_clip_manifest(clip)
        self.assertTrue(manifest["eligible"])
        self.assertFalse(cfh.clip_weights_excluded(clip))
        self.assertFalse(cfh.clip_hydrated(clip))
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertEqual(state["params"]["cpu"], state["params"]["total"])

        manifest["fast_hydration_allowed"] = False  # CPU-safe demand
        cfh.attach_clip_manifest(clip, manifest)

        trace = _RecordingTrace()
        outcome = wiring._hydrate_clip_on_demand(clip, trace=trace)
        decisions = trace.by_name("clip_fh_hydration_decision")
        self.assertTrue(decisions, trace.names())
        first = decisions[0]["metadata"]
        self.assertNotEqual(first["decision"], "already_hydrated")
        self.assertIn(first["decision"], ("cpu_assign_fallback", "native_record", "fast_path"))
        self.assertEqual(first["state_before"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertIn("state_detail", first)
        json.dumps(first)
        # hydration actually proceeds — it is never silently skipped
        self.assertTrue(cfh.clip_hydrated(clip))
        self.assertEqual(outcome.get("reconstruction"), "cpu_assign")
        after = cfh.clip_hydration_state(clip)
        self.assertEqual(after["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertEqual(after["params"]["cpu"], after["params"]["total"])

    def test_encode_parity_after_hydration(self) -> None:
        """After the CPU-assign hydration the hydrated params match the native
        full-CPU model's params (allclose parity, mirroring the production
        parity test style)."""
        clip = self._prepare_excluded_cpu_safe()
        ref = _reference(self.fx.leaf)
        outcome = wiring._hydrate_clip_on_demand(clip, trace=_RecordingTrace())
        self.assertTrue(outcome.get("ok"), outcome)
        self.assertTrue(cfh.clip_hydrated(clip))
        out = _forward(clip.cond_stage_model)
        self.assertTrue(torch.allclose(out, ref, rtol=1e-2, atol=1e-2), "parity after cpu_assign")
        for name, param in clip.cond_stage_model.state_dict().items():
            self.assertEqual(str(param.device), "cpu", name)


# ═══════════════════════════════════════════════════════════════════════════
# D. TestNoInvalidModelEscapes — fail closed, fallback exactly once
# ═══════════════════════════════════════════════════════════════════════════


class TestNoInvalidModelEscapes(unittest.TestCase):
    """A meta-only / no-manifest model must never escape to encode: the demand
    gate fails closed (native path untouched, no hydration attempted), and the
    fast-path-failure fallback chain runs exactly once with no leaked owner
    state."""

    def setUp(self) -> None:
        _reset_wiring_state()
        self.fx = ClipFhFixture()
        self.addCleanup(self.fx.cleanup)

    def test_meta_only_model_never_escapes_to_encode(self) -> None:
        """Excluded fake WITHOUT a manifest: the demand records no_manifest,
        never sets the hydrated marker, and hydrates nothing."""
        clip = _FakeClip()
        stats = cfh.strip_clip_weights(clip)  # excluded marker + meta — but NO manifest
        self.assertGreater(stats["params_replaced"], 0)
        self.assertTrue(cfh.clip_weights_excluded(clip))
        self.assertIsNone(cfh.get_clip_manifest(clip))
        state_before = cfh.clip_hydration_state(clip)
        self.assertEqual(state_before["state"], cfh.STATE_EXCLUDED_PLACEHOLDER)

        trace = _RecordingTrace()
        outcome = wiring._hydrate_clip_on_demand(clip, trace=trace)
        self.assertEqual(outcome["mode"], cfh.MODE_NATIVE)
        self.assertEqual(outcome["reason"], "no_manifest")
        decisions = trace.by_name("clip_fh_hydration_decision")
        self.assertTrue(decisions, trace.names())
        self.assertEqual(decisions[0]["metadata"]["decision"], "no_manifest")
        self.assertFalse(cfh.clip_hydrated(clip), "no_manifest must never set the marker")
        self.assertEqual(trace.by_name("clip_fh_hydration_end"), [])
        # native path untouched: params still meta, no hydration attempted
        for name, param in clip.cond_stage_model.named_parameters():
            self.assertTrue(getattr(param, "is_meta", False), name)
        self.assertEqual(
            cfh.clip_hydration_state(clip)["state"], cfh.STATE_EXCLUDED_PLACEHOLDER
        )

    def test_bare_full_cpu_no_manifest_fails_closed(self) -> None:
        """A full-CPU clip without a manifest also fails closed: no wrapper
        installed, no hydration, native load_model untouched."""
        clip = _FakeClip()
        with patch.dict(os.environ, {wiring._FLAG_FAST: "1"}, clear=False):
            status = wiring.maybe_install_clip_fh_demand(
                SimpleNamespace(clip=clip), trace=_RecordingTrace()
            )
        self.assertEqual(status["status"], "no_manifest", status)
        self.assertFalse(hasattr(clip, cfh.DEMAND_WRAPPER_MARKER))
        self.assertFalse(cfh.clip_hydrated(clip))
        self.assertIs(clip.load_model({}), clip.patcher)

        trace = _RecordingTrace()
        outcome = wiring._hydrate_clip_on_demand(clip, trace=trace)
        self.assertEqual(outcome["reason"], "no_manifest")
        self.assertEqual(trace.by_name("clip_fh_hydration_end"), [])

    def test_fallback_exactly_once(self) -> None:
        """Fast path forced to fail on an excluded clip with
        fast_hydration_allowed True: the fallback chain runs exactly once
        (fallback_count == 1), no owner state leaks, and the final state is
        truthful (CPU_NATIVE_MATERIALIZED, never a GPU/fast label)."""
        clip = _SingleClip()
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
        self.assertTrue(manifest["fast_hydration_allowed"])
        self.assertFalse(cfh.clip_hydrated(clip))

        trace = _RecordingTrace()
        with patch.object(
            wiring, "_fastsafe_load", side_effect=RuntimeError("simulated fast failure")
        ):
            outcome = wiring._hydrate_clip_on_demand(clip, trace=trace)
        self.assertTrue(outcome.get("ok"), outcome)
        self.assertEqual(outcome.get("mode"), cfh.MODE_NATIVE)
        self.assertEqual(outcome.get("reconstruction"), "cpu_assign")
        self.assertEqual(outcome.get("fallback_count"), 1)
        self.assertEqual(outcome.get("state_after"), cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertTrue(cfh.clip_hydrated(clip))
        # exactly one hydration end event (the CPU-assign bind)
        self.assertEqual(len(trace.by_name("clip_fh_hydration_end")), 1, trace.names())
        # no leaked owner state
        self.assertFalse(hasattr(clip.patcher, cfh.OWNER_ATTR))
        for module in clip.cond_stage_model.modules():
            self.assertFalse(hasattr(module, cfh._FASTSAFE_OWNER_ATTR))
        # final state truthful: fully CPU-materialized, not GPU/fast
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertEqual(state["params"]["cpu"], state["params"]["total"])
        self.assertFalse(state["fastsafe_owner_present"])
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["hydration_source"], cfh.MODE_NATIVE)
        self.assertEqual(summary["fallback_count"], 1)
        self.assertEqual(summary["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)


# ═══════════════════════════════════════════════════════════════════════════
# E. TestRequestSummaryStates — defaults unchanged, live state attached
# ═══════════════════════════════════════════════════════════════════════════


class TestRequestSummaryStates(unittest.TestCase):
    """``clip_fh_request_summary`` default behavior is unchanged; live state is
    attached when a clip/demand is available."""

    def setUp(self) -> None:
        _reset_wiring_state()

    def test_summary_defaults_unchanged(self) -> None:
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["hydration_source"], cfh.MODE_RESIDENT)
        self.assertFalse(summary["hydrated"])
        self.assertEqual(summary["fallback_count"], 0)
        self.assertNotIn("state", summary)

        wiring._LAST_EXCLUDED[""] = True
        summary2 = wiring.clip_fh_request_summary("")
        self.assertEqual(summary2["hydration_source"], cfh.MODE_CACHE_HIT)
        self.assertFalse(summary2["hydrated"])
        self.assertEqual(summary2["fallback_count"], 0)

    def test_summary_includes_state(self) -> None:
        """After a demand the summary carries the live hydration state and the
        record's state labels."""
        clip = _FakeClip()
        trace = _RecordingTrace()
        outcome = wiring._hydrate_clip_on_demand(clip, trace=trace)  # no_manifest demand
        self.assertEqual(outcome["reason"], "no_manifest")
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["hydration_source"], cfh.MODE_NATIVE)
        self.assertEqual(summary["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertEqual(summary["last"]["state_before"], cfh.STATE_CPU_NATIVE_MATERIALIZED)

    def test_summary_after_excluded_hydration_carries_state(self) -> None:
        """An excluded -> CPU-assign demand records MODE_NATIVE, hydrated=True,
        state_after CPU_NATIVE_MATERIALIZED and fallback_count 1."""
        fx = ClipFhFixture()
        self.addCleanup(fx.cleanup)
        clip = _SingleClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "0"},
            clear=False,
        ):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                fx.cpu_models(clip, [fx.path1]), trace=_RecordingTrace()
            )
        self.assertEqual(result["status"], "excluded", result)
        wiring._hydrate_clip_on_demand(clip, trace=_RecordingTrace())
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["hydration_source"], cfh.MODE_NATIVE)
        self.assertTrue(summary["hydrated"])
        self.assertEqual(summary["fallback_count"], 1)
        self.assertEqual(summary["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertEqual(summary["last"]["state_after"], cfh.STATE_CPU_NATIVE_MATERIALIZED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
