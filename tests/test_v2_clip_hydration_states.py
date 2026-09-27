"""Batch D3 hydration-state taxonomy + demand decision-event tests (D6
follow-up).

The D6 corrected remote run proved that a fully CPU-materialized CLIP was
served with no D3 manifest and no demand wrapper.  This module pins the
D3-side state machine that prevents that class of silent success:

  * ``clip_hydration_state`` — the explicit hydration-state taxonomy
    (EXCLUDED_PLACEHOLDER / CPU_NATIVE_MATERIALIZED / GPU_FAST_HYDRATED /
    GPU_NATIVE_LOADED / INVALID/PARTIAL).  Pure, side-effect-free, never
    raises, JSON-safe.
  * ``clip_hydrated`` — marker-only: CPU residency alone NEVER satisfies it
    (regression for the exact D6 bug class).
  * ``clip_fh_hydration_decision`` events on every demand branch with
    state_before / state_after labels so future telemetry distinguishes
    already_gpu_fast_hydrated / already_gpu_native_resident /
    cpu_materialized_requires_hydration / excluded_requires_hydration.
  * ``clip_state_checkpoint`` gating (strict no-op when the D3 flags are
    off).
  * ``clip_fh_request_summary`` defaults unchanged.

Synthetic fixtures only (no comfy import), mirroring
``tests/test_v2_clip_fast_hydration_production.py``.
"""

from __future__ import annotations

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

CUDA_OK = torch.cuda.is_available()


def _reset_wiring_state() -> None:
    wiring._RECORD.clear()
    wiring._LAST_EXCLUDED.clear()
    wiring._LAST_CLIP = None


class _TinyTransformer(torch.nn.Module):
    """CLIPTextModel-like module with flat HF-style keys."""

    def __init__(self, dim: int = 64, dtype: torch.dtype = torch.float16):
        super().__init__()
        self.emb = torch.nn.Embedding(512, dim, dtype=dtype)
        self.ln1 = torch.nn.LayerNorm(dim, dtype=dtype)
        self.ff = torch.nn.Linear(dim, dim, dtype=dtype)
        self.ln2 = torch.nn.LayerNorm(dim, dtype=dtype)
        self.ff2 = torch.nn.Linear(dim, dim, dtype=dtype)
        self.text_projection = torch.nn.Linear(dim, 32, dtype=dtype)


class _Leaf(torch.nn.Module):
    """SDClipModel-like dispatch leaf honoring the can_assign_sd convention."""

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

    def model_size(self) -> int:
        return sum(int(p.numel() * p.element_size()) for p in self.model.parameters())


class _FakeClip:
    def __init__(self, dtype: torch.dtype = torch.float16):
        self.cond_stage_model = _FakeCSM(dtype=dtype)
        self.patcher = _FakePatcher(self.cond_stage_model)
        self.tokenizer = object()

    def load_model(self, tokens: Any = None) -> Any:
        return self.patcher


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


class ClipFhFixture:
    """Writes a real single-file clip_l.safetensors from a synthetic encoder."""

    def __init__(self) -> None:
        self.tmpdir = tempfile.mkdtemp(
            prefix="clip_fh_state_",
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


def _mixed_clip() -> _FakeClip:
    """A clip whose structure mixes cpu + meta parameters (partial restore)."""

    class _MixedCSM(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.cpu_param = torch.nn.Parameter(torch.zeros(4, dtype=torch.float32))
            self.meta_param = torch.nn.Parameter(torch.empty(4, dtype=torch.float32, device="meta"))

    clip = _FakeClip()
    clip.cond_stage_model = _MixedCSM()
    clip.patcher = _FakePatcher(clip.cond_stage_model)
    return clip


class TestHydrationStateTaxonomy(unittest.TestCase):
    """Task 2 taxonomy: every canonical label + the pure/never-raises contract."""

    def test_excluded_fake_placeholder(self) -> None:
        clip = _FakeClip()
        stats = cfh.strip_clip_weights(clip)
        self.assertGreater(stats["params_replaced"], 0)
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_EXCLUDED_PLACEHOLDER)
        self.assertTrue(state["excluded_marker"])
        self.assertEqual(state["params"]["meta"], state["params"]["total"])
        self.assertEqual(state["params"]["cpu"], 0)
        self.assertGreater(state["bytes"]["total"], 0, "meta structure still has logical size")
        json.dumps(state)  # JSON-safe

    def test_full_cpu_materialized(self) -> None:
        clip = _FakeClip()
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertGreater(state["bytes"]["cpu"], 0)
        self.assertEqual(state["params"]["cpu"], state["params"]["total"])
        self.assertFalse(state["hydrated"])
        json.dumps(state)

    def test_cuda_resident_gpu_native(self) -> None:
        if not CUDA_OK:
            self.skipTest("CUDA not available")
        clip = _FakeClip()
        clip.cond_stage_model.cuda()
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_GPU_NATIVE_LOADED)
        self.assertEqual(state["params"]["cuda"], state["params"]["total"])
        json.dumps(state)

    def test_cuda_resident_with_fastsafe_owner_gpu_fast(self) -> None:
        if not CUDA_OK:
            self.skipTest("CUDA not available")
        clip = _FakeClip()
        clip.cond_stage_model.cuda()
        cfh.mark_clip_hydrated(clip)
        owners = []
        setattr(clip.patcher, cfh.OWNER_ATTR, owners)
        owners.append(object())
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_GPU_FAST_HYDRATED)
        self.assertTrue(state["fastsafe_owner_present"])
        json.dumps(state)

    def test_mixed_devices_invalid(self) -> None:
        clip = _mixed_clip()
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_INVALID)
        self.assertGreater(state["params"]["cpu"], 0)
        self.assertGreater(state["params"]["meta"], 0)
        json.dumps(state)

    def test_missing_structure_invalid(self) -> None:
        clip = _FakeClip()
        clip.cond_stage_model = None
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_INVALID)
        self.assertEqual(state["params"]["total"], 0)

    def test_no_cond_stage_model_never_raises(self) -> None:
        clip = _FakeClip()
        del clip.cond_stage_model
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_INVALID)

    def test_meta_without_excluded_marker_invalid(self) -> None:
        # Structure on meta but the excluded marker was lost (the D6 restore
        # discard class) — must NOT classify as EXCLUDED_PLACEHOLDER.
        clip = _FakeClip()
        for name, param in list(clip.cond_stage_model.named_parameters()):
            owner = clip.cond_stage_model
            parts = name.split(".")
            for part in parts[:-1]:
                owner = getattr(owner, part)
            meta = torch.empty(param.shape, dtype=param.dtype, device="meta")
            setattr(owner, parts[-1], torch.nn.Parameter(meta, requires_grad=bool(param.requires_grad)))
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_INVALID)
        self.assertFalse(state["excluded_marker"])

    def test_hydrated_marker_does_not_mask_cpu(self) -> None:
        # A fully CPU-materialized clip with the hydrated marker set is still
        # CPU_NATIVE_MATERIALIZED — the marker alone must never relabel a CPU
        # model as GPU-resident.
        clip = _FakeClip()
        cfh.mark_clip_hydrated(clip)
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertTrue(state["hydrated"])


class TestClipHydratedMarkerOnly(unittest.TestCase):
    """D6 regression: marker-only predicate, CPU residency never qualifies."""

    def test_cpu_residency_not_hydrated(self) -> None:
        clip = _FakeClip()
        self.assertFalse(cfh.clip_hydrated(clip))
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)

    def test_marker_alone_satisfies(self) -> None:
        clip = _FakeClip()
        cfh.mark_clip_hydrated(clip)
        self.assertTrue(cfh.clip_hydrated(clip))


class TestDemandDecisionEvents(unittest.TestCase):
    """Task 6: every demand branch records clip_fh_hydration_decision with
    state_before / state_detail, JSON-safe, before acting."""

    def setUp(self) -> None:
        _reset_wiring_state()
        self.fx = ClipFhFixture()
        self.addCleanup(self.fx.cleanup)

    def test_no_manifest_decision(self) -> None:
        clip = _FakeClip()
        trace = _RecordingTrace()
        outcome = wiring._hydrate_clip_on_demand(clip, trace=trace)
        self.assertEqual(outcome["mode"], cfh.MODE_NATIVE)
        self.assertEqual(outcome["reason"], "no_manifest")
        decisions = trace.by_name("clip_fh_hydration_decision")
        self.assertTrue(decisions, trace.names())
        meta = decisions[0]["metadata"]
        self.assertEqual(meta["decision"], "no_manifest")
        self.assertEqual(meta["state_before"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertFalse(meta["fast_hydration_allowed"])
        self.assertFalse(meta["weights_excluded"])
        self.assertIn("state_detail", meta)
        self.assertIn("params", meta["state_detail"])
        self.assertIn("devices", meta["state_detail"])
        json.dumps(meta)  # JSON-safe
        # record carries the state labels
        self.assertEqual(outcome.get("state_before"), cfh.STATE_CPU_NATIVE_MATERIALIZED)

    def test_already_hydrated_decision(self) -> None:
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
        cfh.mark_clip_hydrated(clip)
        trace = _RecordingTrace()
        outcome = wiring._hydrate_clip_on_demand(clip, trace=trace)
        self.assertEqual(outcome["mode"], cfh.MODE_RESIDENT)
        self.assertEqual(outcome["reason"], "already_hydrated")
        decisions = trace.by_name("clip_fh_hydration_decision")
        self.assertTrue(decisions)
        meta = decisions[0]["metadata"]
        self.assertEqual(meta["decision"], "already_hydrated")
        self.assertEqual(meta["state_before"], cfh.STATE_EXCLUDED_PLACEHOLDER)
        self.assertTrue(meta["weights_excluded"])
        json.dumps(meta)

    def test_fast_path_decision_when_fast_allowed(self) -> None:
        clip = _FakeClip()
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
        self.assertTrue(manifest["fast_hydration_allowed"])
        trace = _RecordingTrace()
        with patch.object(
            wiring, "_fastsafe_load", side_effect=RuntimeError("simulated fast failure")
        ):
            wiring._hydrate_clip_on_demand(clip, trace=trace)
        decisions = trace.by_name("clip_fh_hydration_decision")
        fast = [
            e for e in decisions
            if e["metadata"].get("decision") == "fast_path"
            and e["metadata"].get("fast_hydration_allowed") is True
        ]
        self.assertTrue(fast, decisions)
        meta = fast[0]["metadata"]
        self.assertEqual(meta["state_before"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertFalse(meta["weights_excluded"])
        json.dumps(meta)

    def test_cpu_materialized_requires_hydration(self) -> None:
        """The D6 failure class: full-CPU clip WITH manifest, marker absent,
        fast hydration disallowed -> cpu_assign_fallback is chosen (never a
        silent already_hydrated), hydration proceeds, state_after recorded."""
        clip = _FakeClip()
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
        manifest["fast_hydration_allowed"] = False
        cfh.attach_clip_manifest(clip, manifest)
        self.assertFalse(cfh.clip_hydrated(clip))
        self.assertEqual(
            cfh.clip_hydration_state(clip)["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED
        )
        trace = _RecordingTrace()
        outcome = wiring._hydrate_clip_on_demand(clip, trace=trace)
        self.assertTrue(outcome.get("ok"), outcome)
        self.assertTrue(cfh.clip_hydrated(clip), "hydration must proceed, not be silently skipped")
        self.assertEqual(outcome.get("reconstruction"), "cpu_assign")
        decisions = trace.by_name("clip_fh_hydration_decision")
        cpu_assign = [e for e in decisions if e["metadata"].get("decision") == "cpu_assign_fallback"]
        self.assertTrue(cpu_assign, decisions)
        self.assertEqual(cpu_assign[0]["metadata"]["state_before"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        # fallback entry records state_after
        native_fb = [e for e in decisions if e["metadata"].get("decision") == "native_fallback"]
        self.assertTrue(native_fb, decisions)
        fb_meta = native_fb[0]["metadata"]
        self.assertIn("state_after", fb_meta)
        json.dumps(fb_meta)
        # demand record carries both labels
        self.assertEqual(outcome.get("state_before"), cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertEqual(outcome.get("state_after"), cfh.STATE_CPU_NATIVE_MATERIALIZED)

    def test_excluded_requires_hydration_proceeds(self) -> None:
        """An excluded clip (all meta) without the marker must hydrate, not be
        skipped as already_hydrated."""
        clip = _FakeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "0"},
            clear=False,
        ):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(clip, [self.fx.path1]), trace=_RecordingTrace()
            )
        self.assertEqual(result["status"], "excluded", result)
        self.assertFalse(cfh.clip_hydrated(clip))
        trace = _RecordingTrace()
        outcome = wiring._hydrate_clip_on_demand(clip, trace=trace)
        self.assertTrue(outcome.get("ok"), outcome)
        self.assertTrue(cfh.clip_hydrated(clip))
        decisions = trace.by_name("clip_fh_hydration_decision")
        self.assertTrue(decisions)
        self.assertEqual(decisions[0]["metadata"]["decision"], "cpu_assign_fallback")
        self.assertEqual(decisions[0]["metadata"]["state_before"], cfh.STATE_EXCLUDED_PLACEHOLDER)


class TestStateCheckpointGating(unittest.TestCase):
    """Task 3: clip_state_checkpoint is a strict no-op when the D3 flags are
    off and emits when they are on."""

    def setUp(self) -> None:
        _reset_wiring_state()

    def test_noop_when_flags_off(self) -> None:
        clip = _FakeClip()
        trace = _RecordingTrace()
        with patch.dict(
            os.environ,
            {wiring._FLAG_FAST: "0", wiring._FLAG_EXCLUDE: "0"},
            clear=False,
        ):
            wiring.clip_state_checkpoint(trace, "probe", clip)
        self.assertEqual(trace.events, [])

    def test_noop_when_flags_absent(self) -> None:
        clip = _FakeClip()
        trace = _RecordingTrace()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(wiring._FLAG_FAST, None)
            os.environ.pop(wiring._FLAG_EXCLUDE, None)
            wiring.clip_state_checkpoint(trace, "probe", clip)
        self.assertEqual(trace.events, [])

    def test_emits_when_flags_on(self) -> None:
        clip = _FakeClip()
        trace = _RecordingTrace()
        with patch.dict(
            os.environ,
            {wiring._FLAG_FAST: "1", wiring._FLAG_EXCLUDE: "1"},
            clear=False,
        ):
            wiring.clip_state_checkpoint(trace, "probe", clip)
        events = trace.by_name("clip_state_checkpoint")
        self.assertEqual(len(events), 1)
        meta = events[0]["metadata"]
        self.assertEqual(meta["checkpoint"], "probe")
        self.assertEqual(meta["state"]["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        json.dumps(meta)

    def test_demand_wrapper_entry_checkpoint_fires(self) -> None:
        fx = ClipFhFixture()
        self.addCleanup(fx.cleanup)
        clip = _FakeClip()
        trace = _RecordingTrace()
        # The D3 flags must stay set across the demand (clip_state_checkpoint
        # is gated dynamically at call time — mirrors the production env where
        # the flags are process-wide).
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            wiring.maybe_prepare_clip_snapshot_exclusion(
                fx.cpu_models(clip, [fx.path1]), trace=trace
            )
            status = wiring.maybe_install_clip_fh_demand(
                SimpleNamespace(clip=clip), trace=trace
            )
            self.assertEqual(status["status"], "installed", status)
            clip.load_model({})
        checkpoints = [e["metadata"]["checkpoint"] for e in trace.by_name("clip_state_checkpoint")]
        self.assertIn("clip_fh_pre_install", checkpoints)
        self.assertIn("clip_fh_post_install", checkpoints)
        self.assertIn("clip_load_model_entry", checkpoints)
        self.assertIn("clip_hydration_decision", checkpoints)
        self.assertIn("capture_pre_exclusion", checkpoints)
        self.assertIn("capture_post_exclusion", checkpoints)


class TestRequestSummaryDefaults(unittest.TestCase):
    """clip_fh_request_summary default behavior is unchanged; live state is
    attached when a clip is available."""

    def setUp(self) -> None:
        _reset_wiring_state()

    def test_default_resident(self) -> None:
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["hydration_source"], cfh.MODE_RESIDENT)
        self.assertFalse(summary["hydrated"])
        self.assertEqual(summary["fallback_count"], 0)
        self.assertNotIn("state", summary)

    def test_default_cache_hit_when_excluded(self) -> None:
        wiring._LAST_EXCLUDED[""] = True
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["hydration_source"], cfh.MODE_CACHE_HIT)

    def test_state_attached_when_clip_available(self) -> None:
        clip = _FakeClip()
        wiring._LAST_CLIP = clip
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertEqual(summary["hydration_source"], cfh.MODE_RESIDENT)

    def test_recorded_demand_keeps_labels(self) -> None:
        clip = _FakeClip()
        trace = _RecordingTrace()
        wiring._hydrate_clip_on_demand(clip, trace=trace)
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["hydration_source"], cfh.MODE_NATIVE)
        self.assertEqual(summary["last"]["state_before"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertEqual(summary["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)


class TestPublicExports(unittest.TestCase):
    """Restore-side lanes (modal_app / model_preload) import the no-underscore
    helpers from the wiring module."""

    def test_clip_hydration_state_exported(self) -> None:
        self.assertIs(wiring.clip_hydration_state, cfh.clip_hydration_state)
        self.assertTrue(callable(wiring.clip_hydration_state))

    def test_clip_state_checkpoint_exported(self) -> None:
        self.assertTrue(callable(wiring.clip_state_checkpoint))

    def test_state_constants_exported(self) -> None:
        self.assertEqual(cfh.STATE_EXCLUDED_PLACEHOLDER, "EXCLUDED_PLACEHOLDER")
        self.assertEqual(cfh.STATE_CPU_NATIVE_MATERIALIZED, "CPU_NATIVE_MATERIALIZED")
        self.assertEqual(cfh.STATE_GPU_FAST_HYDRATED, "GPU_FAST_HYDRATED")
        self.assertEqual(cfh.STATE_GPU_NATIVE_LOADED, "GPU_NATIVE_LOADED")
        self.assertEqual(cfh.STATE_INVALID, "INVALID/PARTIAL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
