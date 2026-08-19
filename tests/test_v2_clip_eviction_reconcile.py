"""Eviction reconcile contract tests: D3 exclusion re-applied to the fresh
full-weight CLIP reloaded by the ``clip_vae`` eviction retain path.

The canonical launcher pins ``COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1`` +
``COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae``.  Between the capture-side strip
and the memory-snapshot fork, ``_evict_snapshot_models`` reloads a FRESH
full-weight CLIP that carries no frozen manifest and no demand wrapper — so a
request-time restore would serve the full 8.04 GB payload with zero hydration
events.  The reconcile (in ``_evict_snapshot_models``) freezes the manifest
before the original clip is nulled and re-applies attach + strip + demand
wrapper to the reloaded object.  These tests exercise that re-apply contract
against the real ``clip_fast_hydration`` / ``clip_fast_hydration_wiring``
modules with synthetic CLIP-like fixtures — no real models, no remote calls,
no comfy import required at module level.
"""

from __future__ import annotations

import contextlib
import copy
import gc
import io
import json
import os
import shutil
import tempfile
import unittest
import weakref
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import torch

from comfymodal_runtime import clip_fast_hydration as cfh
from comfymodal_runtime import clip_fast_hydration_wiring as wiring


class _TinyTransformer(torch.nn.Module):
    """CLIPTextModel-like module with flat HF-style keys (mirrors the D3
    production test fixture)."""

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
    """Lifecycle-trace-like object: prefers ``emit_at`` (as the wiring ``_emit``
    helper does), records wall/monotonic ns + phase + metadata."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit_at(self, name: str, **kwargs: Any) -> None:
        self.events.append(
            {
                "name": name,
                "phase": kwargs.get("phase"),
                "wall_unix_ns": kwargs.get("wall_unix_ns"),
                "monotonic_ns": kwargs.get("monotonic_ns"),
                "metadata": kwargs.get("metadata") or {},
            }
        )

    def emit(self, name: str, **kwargs: Any) -> None:
        self.events.append(
            {"name": name, "phase": kwargs.get("phase"), "metadata": kwargs.get("metadata") or {}}
        )

    def names(self) -> list[str]:
        return [e["name"] for e in self.events]

    def by_name(self, name: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["name"] == name]


class _ClipFhFixture:
    """Writes one eligible safetensors file so a frozen manifest can be built."""

    def __init__(self) -> None:
        self.tmpdir = tempfile.mkdtemp(
            prefix="clip_fh_reconcile_",
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


class TestEvictionReconcile(unittest.TestCase):
    """The re-apply contract exercised by ``_evict_snapshot_models`` on the
    fresh reloaded CLIP: attach frozen manifest + strip + install demand
    wrapper must yield the same excluded/manifest/wrapped state the original
    clip had at capture."""

    def setUp(self) -> None:
        self.fx = _ClipFhFixture()
        wiring._RECORD.clear()
        wiring._LAST_EXCLUDED.clear()
        # Simulate the capture side: an eligible clip, stripped under Path B.
        self.original = _FakeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            result = wiring.maybe_prepare_clip_snapshot_exclusion(
                self.fx.cpu_models(self.original), trace=_RecordingTrace()
            )
        self.assertEqual(result["status"], "excluded", result)
        self.frozen_manifest = cfh.get_clip_manifest(self.original)
        self.assertIsNotNone(self.frozen_manifest)
        # Deep-copy exactly like the freeze step in _evict_snapshot_models so
        # no reference to the original clip survives.
        self.frozen_copy = copy.deepcopy(self.frozen_manifest)
        self.frozen_eligible = bool(self.frozen_copy.get("eligible"))

    def tearDown(self) -> None:
        self.fx.cleanup()
        wiring._RECORD.clear()
        wiring._LAST_EXCLUDED.clear()

    def test_fresh_reload_reattach_yields_excluded(self) -> None:
        """A fresh full-weight CLIP + attach + strip + install ends up with all
        params meta, the frozen manifest attached, and the demand wrapper."""
        fresh = _FakeClip()  # fresh full-weight reload, no manifest/no marker
        self.assertFalse(cfh.clip_weights_excluded(fresh))
        self.assertIsNone(cfh.get_clip_manifest(fresh))
        self.assertFalse(hasattr(fresh, cfh.DEMAND_WRAPPER_MARKER))
        for name, param in fresh.cond_stage_model.named_parameters():
            self.assertFalse(getattr(param, "is_meta", False), f"{name} pre-stripped")

        trace = _RecordingTrace()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            cfh.attach_clip_manifest(fresh, self.frozen_copy)
            stats = cfh.strip_clip_weights(fresh)
            self.assertGreater(stats["params_replaced"], 0)
            self.assertGreater(stats["payload_bytes_removed"], 0)
            status = wiring.maybe_install_clip_fh_demand(
                SimpleNamespace(clip=fresh), trace=trace
            )

        self.assertEqual(status["status"], "installed", status)
        manifest = cfh.get_clip_manifest(fresh)
        self.assertIsNotNone(manifest)
        self.assertTrue(manifest["eligible"], manifest.get("reason"))
        self.assertTrue(cfh.clip_weights_excluded(fresh))
        for name, param in fresh.cond_stage_model.named_parameters():
            self.assertTrue(getattr(param, "is_meta", False), f"{name} not meta")
        self.assertTrue(hasattr(fresh, cfh.DEMAND_WRAPPER_MARKER))
        self.assertNotEqual(fresh.load_model, type(fresh).load_model, "wrapper must shadow class method")
        install_events = trace.by_name("clip_fh_install")
        self.assertTrue(install_events, "clip_fh_install must be emitted")
        self.assertEqual(install_events[0]["metadata"]["status"], "installed")

    def test_manifest_capture_is_deep_copied(self) -> None:
        """Mutating the frozen deep copy must NOT affect the original clip's
        manifest (the freeze keeps plain data only; no shared references)."""
        self.assertEqual(
            cfh.get_clip_manifest(self.original),
            self.frozen_manifest,
        )
        mutated = copy.deepcopy(self.frozen_manifest)
        mutated["files"][0]["path"] = "/replaced/path.safetensors"
        mutated["files"][0]["key_set"].append("bogus.key")
        mutated["files"][0]["key_shapes"]["bogus.key"] = [1, 2, 3]
        mutated["eligible"] = False
        mutated["fast_hydration_allowed"] = False
        mutated["extra_nested"] = {"a": [1, {"b": 2}]}

        original_manifest = cfh.get_clip_manifest(self.original)
        self.assertTrue(original_manifest["eligible"])
        self.assertNotEqual(
            original_manifest["files"][0]["path"],
            mutated["files"][0]["path"],
        )
        self.assertNotIn("bogus.key", original_manifest["files"][0]["key_set"])
        self.assertNotIn("bogus.key", original_manifest["files"][0]["key_shapes"])
        self.assertNotIn("extra_nested", original_manifest)
        # The clip object holds no reference to the mutated copy.
        self.assertIsNot(original_manifest, mutated)

    def test_reapplied_object_install_reports_installed(self) -> None:
        """``maybe_install_clip_fh_demand`` on the re-applied object must report
        ``installed`` (never ``no_manifest``), proving the restore-time install
        sees the re-attached frozen manifest instead of a bare full CLIP."""
        fresh = _FakeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            cfh.attach_clip_manifest(fresh, copy.deepcopy(self.frozen_manifest))
            cfh.strip_clip_weights(fresh)
            status = wiring.maybe_install_clip_fh_demand(
                SimpleNamespace(clip=fresh), trace=_RecordingTrace()
            )
            self.assertEqual(status["status"], "installed", status)
            # Idempotent second install: already_wrapped, still not no_manifest.
            status2 = wiring.maybe_install_clip_fh_demand(
                SimpleNamespace(clip=fresh), trace=_RecordingTrace()
            )
            self.assertEqual(status2["status"], "already_wrapped", status2)

        # Contrast: a bare fresh clip (no manifest) must fail closed.
        bare = _FakeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            status3 = wiring.maybe_install_clip_fh_demand(
                SimpleNamespace(clip=bare), trace=_RecordingTrace()
            )
            self.assertEqual(status3["status"], "no_manifest", status3)


class TestRestoreTraceEmit(unittest.TestCase):
    """The restore-site trace fix (``self._trace`` -> ``self._lifecycle_trace``)
    makes the wiring ``_emit`` helper drop demand events into the lifecycle
    trace.  Assert the helper records into a lifecycle-trace-like object and is
    a safe no-op for a None trace (the old hole)."""

    def test_emit_records_into_lifecycle_trace_like_object(self) -> None:
        trace = _RecordingTrace()
        wiring._emit(trace, "clip_fh_demand_restore", {"status": "installed"})
        self.assertEqual(len(trace.events), 1)
        event = trace.events[0]
        self.assertEqual(event["name"], "clip_fh_demand_restore")
        self.assertEqual(event["phase"], "execution")
        self.assertEqual(event["metadata"]["status"], "installed")
        self.assertIn("request_id", event["metadata"])

    def test_emit_none_trace_is_safe_noop(self) -> None:
        # The pre-fix restore site passed getattr(self, "_trace", None) which
        # was never assigned -> None -> every demand event was dropped.  The
        # helper must not raise and must record nothing.
        wiring._emit(None, "clip_fh_demand_restore", {"status": "installed"})

    def test_emit_supports_emit_fallback(self) -> None:
        class _EmitOnlyTrace:
            def __init__(self) -> None:
                self.events: list[dict[str, Any]] = []

            def emit(self, name: str, **kwargs: Any) -> None:
                self.events.append(
                    {
                        "name": name,
                        "phase": kwargs.get("phase"),
                        "metadata": kwargs.get("metadata") or {},
                    }
                )

        trace = _EmitOnlyTrace()
        wiring._emit(trace, "clip_fh_demand_restore", {"status": "installed"})
        self.assertEqual(len(trace.events), 1)
        self.assertEqual(trace.events[0]["name"], "clip_fh_demand_restore")
        self.assertEqual(trace.events[0]["phase"], "execution")


class TestDeployLogGatePrints(unittest.TestCase):
    """D6 deploy-log gates: the capture-side ``clip_state_checkpoint`` console
    print is default-OFF (only fires under the D3 flags) and the eviction
    reconcile print exists in ``_evict_snapshot_models`` so the key signals are
    verifiable from the deploy log before the authorized remote request."""

    def test_state_checkpoint_prints_when_enabled(self) -> None:
        clip = _FakeClip()
        cfh.strip_clip_weights(clip)  # excluded placeholder: all meta, cpu_bytes=0
        trace = _RecordingTrace()
        buf = io.StringIO()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            with contextlib.redirect_stdout(buf):
                wiring.clip_state_checkpoint(trace, "capture_pre_snapshot_return", clip)
        out = buf.getvalue()
        self.assertIn(
            "[v2.clip_state] checkpoint=capture_pre_snapshot_return "
            "state=EXCLUDED_PLACEHOLDER",
            out,
        )
        self.assertIn("cpu_bytes=0", out)
        self.assertIn("meta_params=", out)
        self.assertIn("total_params=", out)
        self.assertIn("manifest_eligible=False", out)
        # emit behavior is unchanged — the event still lands on the trace
        events = trace.by_name("clip_state_checkpoint")
        self.assertEqual(len(events), 1, trace.names())
        self.assertEqual(events[0]["metadata"]["checkpoint"], "capture_pre_snapshot_return")

    def test_state_checkpoint_no_print_when_disabled(self) -> None:
        clip = _FakeClip()
        buf = io.StringIO()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "0", wiring._FLAG_FAST: "0"},
            clear=False,
        ):
            with contextlib.redirect_stdout(buf):
                wiring.clip_state_checkpoint(_RecordingTrace(), "probe", clip)
        self.assertNotIn("[v2.clip_state]", buf.getvalue())
        self.assertEqual(buf.getvalue(), "")

    def test_eviction_reconcile_print_format(self) -> None:
        """Static AST assertion (mirrors the argparse test in
        tests/test_v2_unique_prompt_suffix.py): the eviction reconcile console
        print lives inside ``_evict_snapshot_models`` and carries the expected
        literal prefix.  Source path is resolved from the repo layout so no
        (comfy-importing) module import is required."""
        import ast
        from pathlib import Path

        modal_app_path = (
            Path(__file__).resolve().parent.parent / "comfymodal_runtime" / "modal_app.py"
        )
        tree = ast.parse(modal_app_path.read_text(encoding="utf-8"))
        found = False
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef) and node.name == "_evict_snapshot_models"):
                continue
            for child in ast.walk(node):
                if not isinstance(child, ast.Expr):
                    continue
                call = getattr(child, "value", None)
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
                    continue
                if call.func.id != "print":
                    continue
                for arg in call.args:
                    for value in ast.walk(arg):
                        if (
                            isinstance(value, ast.Constant)
                            and isinstance(value.value, str)
                            and "[v2.clip_fh] eviction_reconcile status=" in value.value
                        ):
                            found = True
        self.assertTrue(
            found,
            "[v2.clip_fh] eviction_reconcile status= print missing from "
            "_evict_snapshot_models",
        )


class TestEvictionNoRootingWeakref(unittest.TestCase):
    """Eviction-contract regression (deploy4 root cause): the capture-side
    ``maybe_install_clip_fh_demand`` must NOT root the clip through the
    module-global ``_LAST_CLIP`` telemetry feature.  A strong module-global
    reference keeps the CLIP alive and defeats the snapshot eviction
    weakref-death gate (``RuntimeError('Full eviction failed: original
    weakrefs still alive')``).  ``_LAST_CLIP`` is a weakref: the clip dies when
    the last real reference is dropped, while ``clip_fh_request_summary``
    keeps attaching live state while the clip is alive."""

    def setUp(self) -> None:
        wiring._RECORD.clear()
        wiring._LAST_EXCLUDED.clear()
        wiring._LAST_CLIP = None
        self.fx = _ClipFhFixture()
        self.addCleanup(self.fx.cleanup)
        self.addCleanup(wiring._RECORD.clear)
        self.addCleanup(wiring._LAST_EXCLUDED.clear)
        self.addCleanup(setattr, wiring, "_LAST_CLIP", None)

    def test_install_does_not_root_clip(self) -> None:
        """The weakref taken BEFORE install must report dead after the clip is
        dropped + gc'd — proving the install never rooted it (would fail
        before the fix: ``_LAST_CLIP`` held a strong reference)."""
        clip = _FakeClip()
        wr = weakref.ref(clip)
        # Build a real eligible manifest the way capture does, then install.
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                result = wiring.maybe_prepare_clip_snapshot_exclusion(
                    self.fx.cpu_models(clip), trace=_RecordingTrace()
                )
        self.assertEqual(result["status"], "excluded", result)
        container = SimpleNamespace(clip=clip)
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                status = wiring.maybe_install_clip_fh_demand(container, trace=None)
        self.assertEqual(status["status"], "installed", status)
        # The telemetry global is a weakref, not a strong reference.
        self.assertIsInstance(wiring._LAST_CLIP, weakref.ref)
        self.assertIsNot(wiring._LAST_CLIP, clip)
        self.assertIs(wiring._LAST_CLIP(), clip)  # alive while referenced
        self.assertIsNotNone(wr())

        del container, clip
        gc.collect()
        gc.collect()
        self.assertIsNone(
            wr(),
            "install must not root the clip via the _LAST_CLIP module global",
        )
        self.assertIsNone(wiring._LAST_CLIP())

    def test_summary_state_attached_while_clip_alive(self) -> None:
        """The telemetry feature is preserved: while the clip is alive the
        summary carries its live state; after the clip is dropped + gc'd the
        summary still returns without raising and the state is absent."""
        clip = _FakeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                wiring.maybe_prepare_clip_snapshot_exclusion(
                    self.fx.cpu_models(clip), trace=_RecordingTrace()
                )
                status = wiring.maybe_install_clip_fh_demand(
                    SimpleNamespace(clip=clip), trace=None
                )
        self.assertEqual(status["status"], "installed", status)
        expected = cfh.clip_hydration_state(clip)["state"]
        self.assertEqual(expected, cfh.STATE_EXCLUDED_PLACEHOLDER)

        wiring._RECORD.clear()
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["state"], expected)

        del clip
        gc.collect()
        gc.collect()
        wiring._RECORD.clear()
        summary2 = wiring.clip_fh_request_summary("")
        self.assertNotIn("state", summary2, summary2)
        self.assertEqual(summary2["hydration_source"], cfh.MODE_CACHE_HIT)

    def test_live_weakref_summary_works(self) -> None:
        """While the clip is alive (still referenced), the summary derefs the
        LIVE weakref and attaches the clip's current hydration state."""
        clip = _FakeClip()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                wiring.maybe_prepare_clip_snapshot_exclusion(
                    self.fx.cpu_models(clip), trace=_RecordingTrace()
                )
                status = wiring.maybe_install_clip_fh_demand(
                    SimpleNamespace(clip=clip), trace=None
                )
        self.assertEqual(status["status"], "installed", status)
        self.assertIsInstance(wiring._LAST_CLIP, weakref.ref)
        self.assertIs(wiring._LAST_CLIP(), clip)
        expected = cfh.clip_hydration_state(clip)["state"]
        self.assertEqual(expected, cfh.STATE_EXCLUDED_PLACEHOLDER)
        wiring._RECORD.clear()
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["state"], expected)

    def test_dead_weakref_summary_truthful(self) -> None:
        """After the clip is dropped + gc'd, the summary does NOT raise and is
        truthful about death: no ``state`` key, no resurrection."""
        clip = _FakeClip()
        wiring._note_clip(clip)
        del clip
        gc.collect()
        gc.collect()
        wiring._RECORD.clear()
        wiring._LAST_EXCLUDED.clear()
        summary = wiring.clip_fh_request_summary("")  # must not raise
        self.assertNotIn("state", summary, summary)
        self.assertEqual(summary["hydration_source"], cfh.MODE_RESIDENT)
        self.assertIsNone(wiring._LAST_CLIP(), "dead weakref must deref to None")

    def test_repeated_replacement(self) -> None:
        """Replacing the observed clip (a second install / _note_clip) retargets
        _LAST_CLIP; the previous clip is not retained and dies on drop + gc."""
        clip1 = _FakeClip()
        clip2 = _FakeClip()
        wr1 = weakref.ref(clip1)
        wiring._note_clip(clip1)
        wiring._note_clip(clip2)
        self.assertIsInstance(wiring._LAST_CLIP, weakref.ref)
        self.assertIs(wiring._LAST_CLIP(), clip2)
        self.assertIsNot(wiring._LAST_CLIP(), clip1)
        state2 = cfh.clip_hydration_state(clip2)["state"]
        wiring._RECORD.clear()
        summary = wiring.clip_fh_request_summary("")
        self.assertEqual(summary["state"], state2)
        del clip1
        gc.collect()
        gc.collect()
        self.assertIsNone(wr1(), "clip1 must die after replacement")
        self.assertIsNotNone(wiring._LAST_CLIP())
        self.assertIs(wiring._LAST_CLIP(), clip2)

    def test_no_resurrection_rooting(self) -> None:
        """The wiring module dict never holds the clip as a strong value: only
        the weakref is stored, so after death the clip is unreachable."""
        clip = _FakeClip()
        wiring._note_clip(clip)
        self.assertFalse(
            any(v is clip for v in vars(wiring).values()),
            "_LAST_CLIP must hold a weakref, never the raw clip object",
        )
        del clip
        gc.collect()
        gc.collect()
        self.assertIsNone(wiring._LAST_CLIP(), "dead clip must not be resurrected")

    def test_no_exception_path_retention(self) -> None:
        """A hostile clip / a raising state probe must not store the bad clip
        anywhere and must not cache an exception object in module globals."""

        class _BadCSM:
            def named_parameters(self):
                raise RuntimeError("named_parameters boom")

        class _BadClip:
            def __init__(self) -> None:
                self.cond_stage_model = _BadCSM()
                self.patcher = object()

        bad = _BadClip()
        # clip_hydration_state itself never raises, even on a hostile structure.
        state = cfh.clip_hydration_state(bad)
        self.assertIsInstance(state, dict)
        wiring._LAST_CLIP = None
        wiring._note_clip(bad)
        self.assertIsInstance(wiring._LAST_CLIP, weakref.ref)
        before = wiring._LAST_CLIP
        # Force the summary's state probe to raise; it must be swallowed.
        with patch.object(
            cfh, "clip_hydration_state", side_effect=RuntimeError("state probe boom")
        ):
            wiring._RECORD.clear()
            summary = wiring.clip_fh_request_summary("")  # must not raise
        self.assertNotIn("state", summary, summary)
        self.assertIs(wiring._LAST_CLIP, before, "_LAST_CLIP must be unchanged")
        self.assertFalse(
            any(isinstance(v, Exception) for v in vars(wiring).values()),
            "exception object cached in wiring module globals",
        )

    def test_note_clip_weakref_non_weakrefable_guard(self) -> None:
        """``_note_clip`` guards the weakref TypeError path: None and
        non-weakrefable objects leave ``_LAST_CLIP`` as None (no raise)."""

        class _NoWeakref:
            __slots__ = ()

        wiring._note_clip(None)
        self.assertIsNone(wiring._LAST_CLIP)
        wiring._note_clip(_NoWeakref())
        self.assertIsNone(wiring._LAST_CLIP)
        # A weakrefable clip is stored as a weakref (never the raw object).
        clip = _FakeClip()
        wiring._note_clip(clip)
        self.assertIsInstance(wiring._LAST_CLIP, weakref.ref)
        self.assertIsNot(wiring._LAST_CLIP, clip)
        self.assertIs(wiring._LAST_CLIP(), clip)


class TestTraceMetadataJsonSafe(unittest.TestCase):
    """D6 trace metadata must be JSON-round-trippable: every emitted event's
    metadata (and the ``_state_detail`` view) serializes with ``json.dumps``
    and carries no tensor/object leaves (``__class__.__module__`` never
    ``torch``/``comfy``)."""

    @staticmethod
    def _assert_json_safe(value: Any, path: str = "metadata") -> None:
        """Recursive leaf scan: only JSON primitives are allowed."""
        if isinstance(value, dict):
            for key, child in value.items():
                TestTraceMetadataJsonSafe._assert_json_safe(child, f"{path}.{key}")
            return
        if isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                TestTraceMetadataJsonSafe._assert_json_safe(child, f"{path}[{index}]")
            return
        if isinstance(value, (str, int, float, bool, type(None))):
            return
        module = (type(value).__module__ or "") if type(value).__module__ else ""
        raise AssertionError(
            f"non-JSON-safe leaf at {path}: {type(value).__name__} (module={module})"
        )

    def setUp(self) -> None:
        wiring._RECORD.clear()
        wiring._LAST_EXCLUDED.clear()
        wiring._LAST_CLIP = None
        self.fx = _ClipFhFixture()
        self.addCleanup(self.fx.cleanup)
        self.addCleanup(wiring._RECORD.clear)
        self.addCleanup(wiring._LAST_EXCLUDED.clear)
        self.addCleanup(setattr, wiring, "_LAST_CLIP", None)

    def test_d6_event_metadata_json_roundtrip(self) -> None:
        """Emit the full D6 event set through the REAL wiring paths (plus the
        reconcile/hydration-start shapes) and prove every event's metadata is
        JSON-round-trippable with no tensor/object leaves."""
        clip = _FakeClip()
        trace = _RecordingTrace()
        with patch.dict(
            os.environ,
            {wiring._FLAG_EXCLUDE: "1", wiring._FLAG_FAST: "1"},
            clear=False,
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                # clip_fh_capture + clip_state_checkpoint (real capture path).
                wiring.maybe_prepare_clip_snapshot_exclusion(
                    self.fx.cpu_models(clip), trace=trace
                )
                # clip_fh_install + clip_state_checkpoint (real install path).
                wiring.maybe_install_clip_fh_demand(
                    SimpleNamespace(clip=clip), trace=trace
                )
                # clip_fh_eviction_reconcile-shaped dict (emitted in modal_app).
                wiring._emit(
                    trace,
                    "clip_fh_eviction_reconcile",
                    {
                        "status": "excluded_after_eviction_reload",
                        "params_replaced": 22,
                        "payload_bytes_removed": 173696,
                        "manifest_eligible": 1,
                        "wrapper_installed": "installed",
                        "clip_reloaded_fresh": 1,
                    },
                )
                # clip_fh_hydration_start shape (fast-path start event).
                wiring._emit(
                    trace,
                    "clip_fh_hydration_start",
                    {"mode": cfh.MODE_FASTSAFE, "checkpoint_bytes": 173696},
                )
                # clip_fh_hydration_decision + clip_fh_hydration_end (real
                # CPU-safe demand path).
                manifest = cfh.get_clip_manifest(clip)
                manifest["fast_hydration_allowed"] = False
                cfh.attach_clip_manifest(clip, manifest)
                wiring._hydrate_clip_on_demand(clip, trace=trace)

        names = trace.names()
        for required in (
            "clip_state_checkpoint",
            "clip_fh_capture",
            "clip_fh_install",
            "clip_fh_eviction_reconcile",
            "clip_fh_hydration_decision",
            "clip_fh_hydration_start",
            "clip_fh_hydration_end",
        ):
            self.assertIn(required, names, trace.names())

        for event in trace.events:
            json.dumps(event["metadata"])  # must not raise
            TestTraceMetadataJsonSafe._assert_json_safe(event["metadata"])

    def test_state_detail_json_roundtrip(self) -> None:
        """The ``_state_detail`` telemetry view serializes cleanly and carries
        only primitives."""
        clip = _FakeClip()
        state = cfh.clip_hydration_state(clip)
        detail = wiring._state_detail(state)
        json.dumps(detail)  # must not raise
        TestTraceMetadataJsonSafe._assert_json_safe(detail)
        self.assertIn("params", detail)
        self.assertIn("bytes", detail)
        self.assertIn("devices", detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
