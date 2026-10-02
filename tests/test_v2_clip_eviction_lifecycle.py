"""D6 zero-spend preflight: exact CLIP capture -> eviction -> fresh reload ->
reconcile lifecycle reproduced locally with the REAL wiring/cfh code, plus a
physical-storage alias proof.

Background (deploy4, proven — do not re-litigate):
The D3-stripped original CLIP was rooted by the module-global strong
``_LAST_CLIP`` telemetry reference at capture-install time, so the snapshot
eviction weakref-death gate could never reach alive=0 and the snapshot build
failed on every attempt with
``RuntimeError('Full eviction failed: original weakrefs still alive')``.
``_LAST_CLIP`` now stores ``weakref.ref(clip)``.  These tests pin the FULL
lifecycle the fix protects:

  * capture side: full CPU clip -> excluded placeholder (manifest + strip +
    demand-wrapper install);
  * eviction: the original must DIE (weakref dead) once the container ref is
    dropped + gc — the hard contract that failed on deploy4;
  * eviction fresh reload: a full CPU fake takes its place (no manifest, no
    wrapper, CPU_NATIVE_MATERIALIZED);
  * reconcile (mirrors ``modal_app._evict_snapshot_models`` semantics with the
    REAL helpers): re-attach the FROZEN manifest (deepcopy captured before
    eviction) + strip + install demand wrapper on the new clip;
  * physical storage: no original ``data_ptr`` may survive in the stripped
    clip's named_parameters or be reachable after gc; the logical payload
    removal must equal the recorded ``clip_fh_capture`` stats.

Synthetic torch fixtures only (no ``comfy`` import, mirroring
``tests/test_v2_clip_fast_hydration_production.py`` /
``tests/test_v2_clip_eviction_reconcile.py``).  All tests restore the D3 env
flags after use (default-OFF preserved).
"""

from __future__ import annotations

import contextlib
import copy
import gc
import io
import os
import shutil
import tempfile
import unittest
import weakref
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import torch
from pathlib import Path

from comfymodal_runtime import clip_fast_hydration as cfh
from comfymodal_runtime import clip_fast_hydration_wiring as wiring


# ── Synthetic fixtures (mirror test_v2_clip_fast_hydration_production.py) ──


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

    def forward(self, ids: torch.Tensor) -> torch.Tensor:
        x = self.emb(ids)
        x = self.ff(self.ln1(x))
        x = self.ff2(self.ln2(x))
        x = x.mean(dim=1)
        return self.text_projection(x)


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
        self.load_device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
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


class _RecordingTrace:
    """Lifecycle-trace-like object (the wiring ``_emit`` helper prefers
    ``emit_at``); records name + metadata for assertions."""

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


class _ClipFhFixture:
    """Writes one eligible safetensors file so a frozen manifest can be built."""

    def __init__(self) -> None:
        self.tmpdir = tempfile.mkdtemp(
            prefix="clip_fh_lifecycle_",
            dir=r"C:\Users\parla\AppData\Local\Temp\opencode"
            if os.path.isdir(r"C:\Users\parla\AppData\Local\Temp\opencode")
            else None,
        )
        import safetensors.torch

        self.leaf = _Leaf()
        self.leaf_sd = {
            k: v.detach().clone() for k, v in self.leaf.transformer.state_dict().items()
        }
        self.path = os.path.join(self.tmpdir, "clip_l.safetensors")
        safetensors.torch.save_file(self.leaf_sd, self.path)

    def cpu_models(self, clip: Any) -> SimpleNamespace:
        facts = (
            SimpleNamespace(
                role="clip1", path=self.path, size_bytes=os.path.getsize(self.path), mtime_ns=0
            ),
        )
        return SimpleNamespace(
            clip=clip,
            file_facts=facts,
            model_spec={
                "loaders": {
                    "clip": [{"clip_name": os.path.basename(self.path), "type": "stable_diffusion"}]
                }
            },
        )

    def cleanup(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)


# ── helpers ─────────────────────────────────────────────────────────────────


def _param_bytes(module: torch.nn.Module) -> int:
    return sum(int(p.numel() * p.element_size()) for p in module.parameters())


def _param_data_ptrs(clip: Any) -> set[int]:
    return {p.data_ptr() for _, p in clip.cond_stage_model.named_parameters()}


def _gc_reachable_with_ptrs(ptr_set: set[int]) -> list[torch.Tensor]:
    """Best-effort reachability scan: live tensors whose data_ptr matches one of
    the original storages.  Address-reuse caveat handled by the callers."""
    return [t for t in gc.get_objects() if torch.is_tensor(t) and t.data_ptr() in ptr_set]


def _rss_mb() -> float | None:
    try:
        import psutil

        return round(float(psutil.Process().memory_info().rss) / 1048576.0, 3)
    except Exception:
        return None


class _LifecycleTestBase(unittest.TestCase):
    """Shared setup for the lifecycle + storage tests: wiring globals reset,
    a real safetensors fixture for eligible manifests, flags restored after."""

    def setUp(self) -> None:
        wiring._RECORD.clear()
        wiring._LAST_EXCLUDED.clear()
        wiring._LAST_CLIP = None
        self.fx = _ClipFhFixture()
        self.addCleanup(self.fx.cleanup)
        self.addCleanup(wiring._RECORD.clear)
        self.addCleanup(wiring._LAST_EXCLUDED.clear)
        self.addCleanup(setattr, wiring, "_LAST_CLIP", None)

    @staticmethod
    def _flags_on():
        return patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        )

    def _capture(self, clip: _FakeClip) -> tuple[dict, _RecordingTrace]:
        """Capture side: frozen manifest + Path-B strip (all params meta)."""
        trace = _RecordingTrace()
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                result = wiring.maybe_prepare_clip_snapshot_exclusion(
                    self.fx.cpu_models(clip), trace=trace
                )
        self.assertEqual(result["status"], "excluded", result)
        return result, trace

    def _install(self, clip: _FakeClip, *, trace: Any = None) -> dict:
        container = SimpleNamespace(clip=clip)
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                status = wiring.maybe_install_clip_fh_demand(container, trace=trace)
        self.assertEqual(status["status"], "installed", status)
        return status

    def _prepare_and_install(self, clip: _FakeClip) -> tuple[dict, SimpleNamespace]:
        """Full capture-side sequence; returns (frozen_manifest, container)."""
        self._capture(clip)
        manifest = cfh.get_clip_manifest(clip)
        assert manifest is not None, "eligible manifest expected after capture"
        frozen = copy.deepcopy(manifest)
        self.assertTrue(frozen["eligible"])
        container = SimpleNamespace(clip=clip)
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                status = wiring.maybe_install_clip_fh_demand(container, trace=_RecordingTrace())
        self.assertEqual(status["status"], "installed", status)
        return frozen, container

    def _reconcile_new_clip(self, new_clip: _FakeClip, frozen: dict) -> tuple[dict, SimpleNamespace]:
        """Mirror of the ``modal_app._evict_snapshot_models`` reconcile block
        semantics using the REAL helpers: attach frozen manifest + strip +
        install demand wrapper on the fresh reload."""
        new_container = SimpleNamespace(clip=new_clip)
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                cfh.attach_clip_manifest(new_clip, frozen)
                stats = cfh.strip_clip_weights(new_clip)
                status = wiring.maybe_install_clip_fh_demand(new_container, trace=_RecordingTrace())
        self.assertEqual(status["status"], "installed", status)
        return stats, new_container

    @staticmethod
    def _assert_no_structural_alias(clip: Any, original_ptr_set: set[int]) -> None:
        """Every visible param is a meta placeholder whose storage is NOT one of
        the original storages."""
        for name, param in clip.cond_stage_model.named_parameters():
            assert getattr(param, "is_meta", False), name
            assert param.data_ptr() not in original_ptr_set, name
            assert param.untyped_storage().data_ptr() not in original_ptr_set, name


# ═══════════════════════════════════════════════════════════════════════════
# PACKAGE B — exact eviction lifecycle reproduction (Task 3/5)
# ═══════════════════════════════════════════════════════════════════════════


class TestEvictionLifecycle(_LifecycleTestBase):
    """The REAL capture -> eviction -> fresh reload -> reconcile lifecycle."""

    def test_single_lifecycle_round_trip(self) -> None:
        """One full iteration with the hard eviction-contract + reconcile
        assertions.  The fresh reload is built BEFORE the original is dropped
        so ``new_clip is not original`` is a valid identity comparison (no
        allocator id-reuse flake); the death proof then runs on the original."""
        original = _FakeClip()
        full_bytes = _param_bytes(original.cond_stage_model)
        full_count = sum(1 for _ in original.cond_stage_model.named_parameters())
        self.assertEqual(
            cfh.clip_hydration_state(original)["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED
        )

        frozen, container = self._prepare_and_install(original)
        # capture side: excluded placeholder, zero CPU payload
        captured = cfh.clip_hydration_state(original)
        self.assertEqual(captured["state"], cfh.STATE_EXCLUDED_PLACEHOLDER)
        self.assertEqual(captured["bytes"]["cpu"], 0)
        self.assertEqual(captured["params"]["meta"], full_count)

        # eviction: fresh full-weight reload takes the original's place.
        wr = weakref.ref(original)
        new_clip = _FakeClip()  # original still alive -> identity check valid
        self.assertIsNot(new_clip, original)
        # post_reload_before_reconcile: full CPU, no manifest, no wrapper.
        pre = cfh.clip_hydration_state(new_clip)
        self.assertEqual(pre["state"], cfh.STATE_CPU_NATIVE_MATERIALIZED)
        self.assertGreater(pre["bytes"]["cpu"], 0)
        self.assertEqual(pre["params"]["cpu"], pre["params"]["total"])
        self.assertIsNone(cfh.get_clip_manifest(new_clip))
        self.assertFalse(cfh.clip_weights_excluded(new_clip))
        self.assertFalse(hasattr(new_clip, cfh.DEMAND_WRAPPER_MARKER))

        # HARD eviction contract: the original must die once dropped + gc'd.
        del container, original
        gc.collect()
        gc.collect()
        self.assertIsNone(wr(), "original must be dead after eviction (deploy4 gate)")
        self.assertIsNone(wiring._LAST_CLIP())

        # reconcile the fresh reload with the frozen manifest.
        stats, new_container = self._reconcile_new_clip(new_clip, frozen)
        self.assertEqual(stats["params_replaced"], full_count)
        self.assertEqual(stats["payload_bytes_removed"], full_bytes)

        # post_reconcile hard assertions (Task 3/5).
        self.assertIsNone(wr())
        after = cfh.clip_hydration_state(new_clip)
        self.assertEqual(after["state"], cfh.STATE_EXCLUDED_PLACEHOLDER)
        self.assertEqual(after["bytes"]["cpu"], 0)
        self.assertEqual(after["params"]["cpu"], 0)
        self.assertEqual(after["params"]["meta"], full_count)
        self.assertEqual(after["params"]["total"], full_count)
        manifest = cfh.get_clip_manifest(new_clip)
        assert manifest is not None, "reconciled new clip must carry the frozen manifest"
        self.assertTrue(manifest["eligible"], manifest.get("reason"))
        self.assertTrue(hasattr(new_clip, cfh.DEMAND_WRAPPER_MARKER))
        self.assertIs(new_container.clip, new_clip)
        # the original is unreachable while the reconciled new clip is served;
        # the telemetry weakref tracks the NEW (alive) clip, never the dead one.
        self.assertIsNone(wr())
        self.assertIs(wiring._LAST_CLIP(), new_clip)

    def test_repeat_three_times_no_retained_refs(self) -> None:
        """Repeat the whole lifecycle 3x (Task 3: catch accidental retained
        references): each iteration's original dies, the new clip is
        reconciled, and NO module global in wiring/cfh holds any iteration
        clip between iterations."""
        iteration_clips: list[_FakeClip] = []
        for iteration in range(3):
            original = _FakeClip()
            full_bytes = _param_bytes(original.cond_stage_model)
            full_count = sum(1 for _ in original.cond_stage_model.named_parameters())
            frozen, container = self._prepare_and_install(original)
            wr = weakref.ref(original)

            new_clip = _FakeClip()
            self.assertIsNot(new_clip, original)
            del container, original
            gc.collect()
            gc.collect()
            self.assertIsNone(wr(), f"iteration {iteration}: original not evicted")

            stats, new_container = self._reconcile_new_clip(new_clip, frozen)
            self.assertEqual(stats["params_replaced"], full_count)
            self.assertEqual(stats["payload_bytes_removed"], full_bytes)
            after = cfh.clip_hydration_state(new_clip)
            self.assertEqual(after["state"], cfh.STATE_EXCLUDED_PLACEHOLDER)
            self.assertEqual(after["bytes"]["cpu"], 0)
            self.assertEqual(after["params"]["meta"], full_count)
            self.assertIs(new_container.clip, new_clip)

            iteration_clips.append(new_clip)
            # Between iterations no module global may reference any clip.
            leaked = [
                name
                for name, value in list(vars(wiring).items()) + list(vars(cfh).items())
                if any(value is c for c in iteration_clips)
            ]
            self.assertEqual(
                leaked,
                [],
                f"iteration {iteration}: module globals retained a clip: {leaked}",
            )
            # telemetry weakref points at the LIVE new clip (weak, not rooting).
            self.assertIs(wiring._LAST_CLIP(), new_clip)


# ═══════════════════════════════════════════════════════════════════════════
# PACKAGE C — physical storage alias proof (Task 4)
# ═══════════════════════════════════════════════════════════════════════════


class TestPhysicalStorageAliasProof(_LifecycleTestBase):
    """The strip removes the PHYSICAL payload: no original storage may remain
    aliased by the stripped structure, and the logical removal must match the
    recorded capture stats.  RSS is reported best-effort but never asserted
    (the Windows allocator retains arenas; storage identity is the proof)."""

    def test_original_storage_freed_after_exclusion(self) -> None:
        """Record every original param's data_ptr before the strip; after the
        strip all visible params are meta, none aliases an original storage,
        and after drop+gc no live tensor shares an original data_ptr."""
        original = _FakeClip()
        original_ptrs = _param_data_ptrs(original)
        self.assertGreater(len(original_ptrs), 0)
        self.assertNotIn(0, original_ptrs, "pre-strip CPU params must own real storage")

        result, _ = self._capture(original)
        self.assertEqual(result["status"], "excluded", result)
        self._assert_no_structural_alias(original, original_ptrs)

        del original
        gc.collect()
        gc.collect()
        reachable = _gc_reachable_with_ptrs(original_ptrs)
        self.assertEqual(
            len(reachable),
            0,
            f"{len(reachable)} original storages still reachable after strip + gc",
        )

    def test_post_reconcile_no_original_alias(self) -> None:
        """Full lifecycle: after eviction + reconcile, the NEW clip's named
        parameters contain none of the ORIGINAL storages and carry no full-CPU
        payload (all meta)."""
        original = _FakeClip()
        original_ptrs = _param_data_ptrs(original)
        frozen, _container = self._prepare_and_install(original)
        del _container, original
        gc.collect()
        gc.collect()

        new_clip = _FakeClip()
        _stats, _new_container = self._reconcile_new_clip(new_clip, frozen)
        self._assert_no_structural_alias(new_clip, original_ptrs)
        state = cfh.clip_hydration_state(new_clip)
        self.assertEqual(state["state"], cfh.STATE_EXCLUDED_PLACEHOLDER)
        self.assertEqual(state["bytes"]["cpu"], 0)
        self.assertEqual(state["params"]["cpu"], 0)
        self.assertEqual(state["params"]["meta"], state["params"]["total"])

    def test_logical_vs_physical_report(self) -> None:
        """logical_parameter_bytes_removed=<L> unique_original_storage_bytes_
        still_reachable=<R> full_cpu_payload_reachable=<F> (rss_before_mb=<B>
        rss_after_mb=<A>) — the physical proof: the recorded payload removal
        equals the logical parameter bytes and no original storage survives."""
        original = _FakeClip()
        original_ptrs = _param_data_ptrs(original)
        logical_bytes = _param_bytes(original.cond_stage_model)
        rss_before = _rss_mb()

        trace = _RecordingTrace()
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                result = wiring.maybe_prepare_clip_snapshot_exclusion(
                    self.fx.cpu_models(original), trace=trace
                )
        self.assertEqual(result["status"], "excluded", result)
        capture = trace.by_name("clip_fh_capture")
        self.assertTrue(capture, trace.names())
        payload_bytes = int(capture[0]["metadata"]["payload_bytes_removed"])
        self.assertEqual(payload_bytes, logical_bytes)

        _manifest = cfh.get_clip_manifest(original)
        assert _manifest is not None, "eligible manifest expected after capture"
        frozen = copy.deepcopy(_manifest)
        self._assert_no_structural_alias(original, original_ptrs)
        del original
        gc.collect()
        gc.collect()

        new_clip = _FakeClip()
        self._reconcile_new_clip(new_clip, frozen)
        state = cfh.clip_hydration_state(new_clip)
        full_cpu_reachable = int(state["bytes"]["cpu"]) > 0
        reachable = _gc_reachable_with_ptrs(original_ptrs)
        rss_after = _rss_mb()

        report = (
            f"logical_parameter_bytes_removed={payload_bytes} "
            f"unique_original_storage_bytes_still_reachable={len(reachable)} "
            f"full_cpu_payload_reachable={full_cpu_reachable} "
            f"rss_before_mb={rss_before} rss_after_mb={rss_after}"
        )
        self.assertEqual(
            len(reachable),
            0,
            f"{report} — original storages still reachable after full lifecycle",
        )
        self.assertFalse(full_cpu_reachable, f"{report} — full CPU payload on new clip")
        self.assertEqual(
            state["params"]["meta"],
            state["params"]["total"],
            f"{report} — new clip must be fully stripped",
        )


# ═══════════════════════════════════════════════════════════════════════════
# PACKAGE D — D10 Gate-D reconcile-to-capture boundary (zero-spend)
# ═══════════════════════════════════════════════════════════════════════════


class TestGateDReconcileToCapture(_LifecycleTestBase):
    """D10 Gate-D root cause: the reconcile log proved 399 meta params +
    eligible manifest at 16:01:29.809Z, yet `capture_pre_snapshot_return`
    reported INVALID/PARTIAL total_params=0 at 16:01:29.853Z.  The reconciled
    object did NOT disappear — the checkpoint was handed the CpuSnapshotModels
    CONTAINER (modal_app passes `self._cpu_snapshot_models`), and
    `clip_hydration_state` walks the passed object literally, so a container
    (no cond_stage_model / manifest / markers) reports all-zeros INVALID.

    These tests drive the REAL sequence through the exact Gate-D-equivalent
    ready-return boundary and prove: the same reconciled CLIP object survives
    with EXCLUDED_PLACEHOLDER + full meta structure + manifest + wrapper, and
    the checkpoint now resolves the canonical capture holder."""

    def test_reconciled_object_identity_survives_to_gate_d(self) -> None:
        """Reconcile returns EXCLUDED_PLACEHOLDER; the Gate-D checkpoint —
        called with the CONTAINER exactly like modal_app — resolves the SAME
        new clip object (id match), state EXCLUDED_PLACEHOLDER, meta=full,
        cpu=0, bytes=0, manifest present+eligible, wrapper present."""
        original = _FakeClip()
        full_bytes = _param_bytes(original.cond_stage_model)
        full_count = sum(1 for _ in original.cond_stage_model.named_parameters())

        frozen, container = self._prepare_and_install(original)
        wr = weakref.ref(original)
        new_clip = _FakeClip()
        self.assertIsNot(new_clip, original)
        del container, original
        gc.collect()
        gc.collect()
        self.assertIsNone(wr(), "original must die before reconcile")

        new_container = SimpleNamespace(clip=new_clip)
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                cfh.attach_clip_manifest(new_clip, frozen)
                stats = cfh.strip_clip_weights(new_clip)
                status = wiring.maybe_install_clip_fh_demand(
                    new_container, trace=_RecordingTrace()
                )
        self.assertEqual(status["status"], "installed", status)
        self.assertEqual(stats["params_replaced"], full_count)
        self.assertEqual(stats["payload_bytes_removed"], full_bytes)

        # Gate-D equivalent: pass the CONTAINER (as modal_app.py:9296-9300 does).
        trace = _RecordingTrace()
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                wiring.clip_state_checkpoint(
                    trace, "capture_pre_snapshot_return", new_container
                )
        events = trace.by_name("clip_state_checkpoint")
        self.assertEqual(len(events), 1, trace.names())
        meta = events[0]["metadata"]
        self.assertEqual(meta["checkpoint"], "capture_pre_snapshot_return")
        self.assertEqual(meta["holder_source"], "cpu_snapshot_models.clip")
        self.assertEqual(meta["clip_object_id"], id(new_clip))
        state = meta["state"]
        self.assertEqual(state["state"], cfh.STATE_EXCLUDED_PLACEHOLDER)
        self.assertEqual(state["params"]["total"], full_count)
        self.assertEqual(state["params"]["cpu"], 0)
        self.assertEqual(state["params"]["meta"], full_count)
        self.assertEqual(state["bytes"]["cpu"], 0)
        self.assertTrue(state["manifest_present"])
        self.assertTrue(state["manifest_eligible"])
        self.assertTrue(meta["demand_wrapper_present"])
        self.assertIs(new_container.clip, new_clip)

    def test_direct_clip_argument_unchanged(self) -> None:
        """Passing the CLIP itself (legacy/test path) still resolves directly
        with holder_source=direct and the same state contract."""
        original = _FakeClip()
        frozen, container = self._prepare_and_install(original)
        del container, original
        gc.collect()
        gc.collect()
        new_clip = _FakeClip()
        new_container = SimpleNamespace(clip=new_clip)
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                cfh.attach_clip_manifest(new_clip, frozen)
                cfh.strip_clip_weights(new_clip)
                wiring.maybe_install_clip_fh_demand(new_container, trace=_RecordingTrace())

        trace = _RecordingTrace()
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                wiring.clip_state_checkpoint(trace, "probe_direct", new_clip)
        meta = trace.by_name("clip_state_checkpoint")[0]["metadata"]
        self.assertEqual(meta["holder_source"], "direct")
        self.assertEqual(meta["clip_object_id"], id(new_clip))
        self.assertEqual(meta["state"]["state"], cfh.STATE_EXCLUDED_PLACEHOLDER)

    def test_stale_cleared_holder_cannot_fake_gate_d(self) -> None:
        """A cleared/stale holder (container.clip = None) must report no_clip —
        never a fabricated INVALID/PARTIAL — and must not hide a healthy clip."""
        original = _FakeClip()
        frozen, container = self._prepare_and_install(original)
        del container, original
        gc.collect()
        gc.collect()
        new_clip = _FakeClip()
        new_container = SimpleNamespace(clip=new_clip)
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                cfh.attach_clip_manifest(new_clip, frozen)
                cfh.strip_clip_weights(new_clip)
                wiring.maybe_install_clip_fh_demand(new_container, trace=_RecordingTrace())

        # Case A: reconciled object is healthy, but the inspected holder is
        # cleared — the checkpoint must fail closed (no_clip), NOT INVALID.
        cleared = SimpleNamespace(clip=None)
        trace = _RecordingTrace()
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                wiring.clip_state_checkpoint(trace, "capture_pre_snapshot_return", cleared)
        meta = trace.by_name("clip_state_checkpoint")[0]["metadata"]
        self.assertEqual(meta["holder_source"], "cpu_snapshot_models.clip")
        self.assertIsNone(meta["clip_object_id"])
        self.assertIsNone(meta["state"])
        # The real canonical clip is untouched by the stale-holder probe.
        self.assertEqual(
            cfh.clip_hydration_state(new_clip)["state"], cfh.STATE_EXCLUDED_PLACEHOLDER
        )

    def test_conflicting_candidates_fail_closed(self) -> None:
        """An object carrying BOTH cond_stage_model and clip (conflicting
        candidates) resolves to ambiguous -> no_clip (fail closed, never
        guessed)."""
        clip = _FakeClip()
        holder = SimpleNamespace(clip=clip)
        holder.cond_stage_model = clip.cond_stage_model  # now both present
        resolved, source = wiring.resolve_capture_clip(holder)
        self.assertIsNone(resolved)
        self.assertEqual(source, "ambiguous")
        trace = _RecordingTrace()
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                wiring.clip_state_checkpoint(trace, "probe_ambiguous", holder)
        meta = trace.by_name("clip_state_checkpoint")[0]["metadata"]
        self.assertEqual(meta["holder_source"], "ambiguous")
        self.assertIsNone(meta["clip_object_id"])

    def test_unsupported_holder_fails_closed(self) -> None:
        resolved, source = wiring.resolve_capture_clip(object())
        self.assertIsNone(resolved)
        self.assertEqual(source, "unsupported")

    def test_post_reconcile_cleanup_preserves_meta_structure(self) -> None:
        """The 44 ms production window ran NO clip-affecting operation after
        the reconcile emit (only VAE metadata writes, RSS reads, floor prints,
        marker stores, del locals).  Simulate those cleanup/finalization ops
        after reconcile and prove the meta structure + manifest + wrapper
        survive to the Gate-D boundary."""
        original = _FakeClip()
        full_count = sum(1 for _ in original.cond_stage_model.named_parameters())
        frozen, container = self._prepare_and_install(original)
        del container, original
        gc.collect()
        gc.collect()
        new_clip = _FakeClip()
        new_container = SimpleNamespace(clip=new_clip)
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                cfh.attach_clip_manifest(new_clip, frozen)
                cfh.strip_clip_weights(new_clip)
                wiring.maybe_install_clip_fh_demand(new_container, trace=_RecordingTrace())
        # post-reconcile finalization equivalent (modal_app 6954-7222):
        new_container.vae_validation_metadata = {"policy": "v1"}  # VAE only
        new_container.vae_storage_registry = None  # VAE only
        del new_clip  # drop the local; container.clip remains the root
        gc.collect()
        gc.collect()
        trace = _RecordingTrace()
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                wiring.clip_state_checkpoint(
                    trace, "capture_pre_snapshot_return", new_container
                )
        meta = trace.by_name("clip_state_checkpoint")[0]["metadata"]
        self.assertIsNotNone(meta["clip_object_id"])
        state = meta["state"]
        self.assertEqual(state["state"], cfh.STATE_EXCLUDED_PLACEHOLDER)
        self.assertEqual(state["params"]["meta"], full_count)
        self.assertEqual(state["params"]["total"], full_count)
        self.assertEqual(state["params"]["cpu"], 0)
        self.assertEqual(state["bytes"]["cpu"], 0)
        self.assertTrue(state["manifest_present"])
        self.assertTrue(state["manifest_eligible"])
        self.assertTrue(meta["demand_wrapper_present"])
        self.assertTrue(meta["manifest_present"])

    def test_strip_is_idempotent(self) -> None:
        """A second strip on an already-excluded placeholder preserves the meta
        structure (399-equivalent) — it must NEVER turn meta into 0 params."""
        clip = _FakeClip()
        full_count = sum(1 for _ in clip.cond_stage_model.named_parameters())
        first = cfh.strip_clip_weights(clip)
        self.assertEqual(first["params_replaced"], full_count)
        second = cfh.strip_clip_weights(clip)
        self.assertEqual(second["params_replaced"], full_count)
        state = cfh.clip_hydration_state(clip)
        self.assertEqual(state["state"], cfh.STATE_EXCLUDED_PLACEHOLDER)
        self.assertEqual(state["params"]["meta"], full_count)
        self.assertEqual(state["params"]["total"], full_count)
        self.assertEqual(state["params"]["cpu"], 0)
        self.assertTrue(state["excluded_marker"])

    def test_manifest_wrapper_lifetime_through_gate_d(self) -> None:
        """At each stage record object id + manifest + wrapper + state; prove
        both manifest and demand wrapper remain on the canonical capture
        object through the Gate-D boundary."""
        original = _FakeClip()
        frozen, container = self._prepare_and_install(original)
        del container, original
        gc.collect()
        gc.collect()
        new_clip = _FakeClip()
        new_container = SimpleNamespace(clip=new_clip)

        def _snap(label: str) -> dict:
            return {
                "label": label,
                "object_id": id(new_clip),
                "manifest": cfh.get_clip_manifest(new_clip) is not None,
                "eligible": bool((cfh.get_clip_manifest(new_clip) or {}).get("eligible")),
                "wrapper": hasattr(new_clip, cfh.DEMAND_WRAPPER_MARKER),
                "state": cfh.clip_hydration_state(new_clip)["state"],
            }

        stages = [_snap("post_reload_before_reconcile")]
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                cfh.attach_clip_manifest(new_clip, frozen)
                stages.append(_snap("post_manifest_attach"))
                cfh.strip_clip_weights(new_clip)
                stages.append(_snap("post_strip"))
                wiring.maybe_install_clip_fh_demand(new_container, trace=_RecordingTrace())
                stages.append(_snap("post_wrapper_install"))
        gc.collect()
        gc.collect()
        stages.append(_snap("post_cleanup"))
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                wiring.clip_state_checkpoint(
                    trace := _RecordingTrace(), "capture_pre_snapshot_return", new_container
                )
        stages.append(_snap("pre_snapshot_return"))
        meta = trace.by_name("clip_state_checkpoint")[0]["metadata"]
        self.assertEqual(meta["clip_object_id"], id(new_clip))
        self.assertTrue(meta["manifest_present"])
        self.assertTrue(meta["manifest_eligible"])
        self.assertTrue(meta["demand_wrapper_present"])
        self.assertEqual(stages[-1]["state"], cfh.STATE_EXCLUDED_PLACEHOLDER)
        # Manifest is attached at post_manifest_attach; the demand wrapper is
        # installed only at post_wrapper_install — assert each from its stage.
        for stage in stages[1:]:
            self.assertTrue(stage["manifest"], stage["label"])
            self.assertTrue(stage["eligible"], stage["label"])
            self.assertEqual(stage["object_id"], id(new_clip), stage["label"])
        for stage in stages[3:]:
            self.assertTrue(stage["wrapper"], stage["label"])
            self.assertEqual(stage["state"], cfh.STATE_EXCLUDED_PLACEHOLDER, stage["label"])

    def test_patcher_cleanup_error_does_not_touch_reconciled_clip(self) -> None:
        """patcher_cleanup_errors=1 (modal_app 6441-6493) runs on the ORIGINAL
        objects BEFORE the fresh reload — it cannot mutate the reconciled clip.
        Prove the cleanup-error path on a synthetic original leaves the new
        clip's meta structure intact through Gate D."""
        original = _FakeClip()
        full_count = sum(1 for _ in original.cond_stage_model.named_parameters())
        frozen, container = self._prepare_and_install(original)

        # Simulate the patcher-cleanup block (original objects only):
        orig_patcher = original.patcher

        def _boom_cleanup():
            raise RuntimeError("synthetic cleanup error")

        def _boom_detach(*_a, **_k):
            raise RuntimeError("synthetic detach error")

        with patch.object(orig_patcher, "cleanup", _boom_cleanup, create=True), patch.object(
            orig_patcher, "detach", _boom_detach, create=True
        ):
            cleanup_errors = 0
            for obj in (original, orig_patcher):
                for op in ("cleanup", "detach"):
                    try:
                        fn = getattr(obj, op, None)
                        if fn is None:
                            raise AttributeError(op)
                        fn(True) if op == "detach" else fn()
                    except Exception:
                        cleanup_errors += 1
            self.assertGreaterEqual(cleanup_errors, 2)
        del container, original
        gc.collect()
        gc.collect()
        new_clip = _FakeClip()
        new_container = SimpleNamespace(clip=new_clip)
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                cfh.attach_clip_manifest(new_clip, frozen)
                cfh.strip_clip_weights(new_clip)
                wiring.maybe_install_clip_fh_demand(new_container, trace=_RecordingTrace())
        trace = _RecordingTrace()
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                wiring.clip_state_checkpoint(
                    trace, "capture_pre_snapshot_return", new_container
                )
        meta = trace.by_name("clip_state_checkpoint")[0]["metadata"]
        self.assertEqual(meta["clip_object_id"], id(new_clip))
        self.assertEqual(meta["state"]["state"], cfh.STATE_EXCLUDED_PLACEHOLDER)
        self.assertEqual(meta["state"]["params"]["meta"], full_count)

    def test_gate_d_telemetry_non_rooting(self) -> None:
        """The new checkpoint metadata (ids only) must not root the clip:
        after Gate D, no module global in wiring/cfh holds the clip strongly
        (the D6 `_LAST_CLIP` weakref contract is preserved)."""
        original = _FakeClip()
        frozen, container = self._prepare_and_install(original)
        del container, original
        gc.collect()
        gc.collect()
        new_clip = _FakeClip()
        new_container = SimpleNamespace(clip=new_clip)
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                cfh.attach_clip_manifest(new_clip, frozen)
                cfh.strip_clip_weights(new_clip)
                wiring.maybe_install_clip_fh_demand(new_container, trace=_RecordingTrace())
        with self._flags_on():
            with contextlib.redirect_stdout(io.StringIO()):
                wiring.clip_state_checkpoint(
                    _RecordingTrace(), "capture_pre_snapshot_return", new_container
                )
        leaked = [
            name
            for name, value in list(vars(wiring).items()) + list(vars(cfh).items())
            if value is new_clip
        ]
        self.assertEqual(leaked, [], f"checkpoint telemetry rooted the clip: {leaked}")
        wr = weakref.ref(new_clip)
        del new_clip, new_container
        gc.collect()
        gc.collect()
        self.assertIsNone(wr(), "clip must be collectable after Gate D")

    def test_capture_and_restore_consume_same_holder(self) -> None:
        """Restore consumes `_cpu_snapshot_models.clip` (modal_app
        `_activate_clip_vae_only_request_binding` publishes `models.clip`) —
        the SAME holder the Gate-D checkpoint now resolves.  Prove the
        resolver maps the container to the object restore would bind."""
        clip = _FakeClip()
        holder = SimpleNamespace(clip=clip)
        resolved, source = wiring.resolve_capture_clip(holder)
        self.assertIs(resolved, clip)
        self.assertEqual(source, "cpu_snapshot_models.clip")
        # Source-level: the restore bind reads models.clip, not a shadow slot.
        import ast

        src = (
            Path(__file__).resolve().parents[1] / "comfymodal_runtime" / "modal_app.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(src)
        bind_text = ""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in (
                "_activate_clip_vae_only_request_binding",
            ):
                bind_text = ast.get_source_segment(src, node) or ""
        self.assertIn("models.clip", bind_text)
        self.assertIn("use_ready_clip", bind_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
