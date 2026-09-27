"""Focused tests for the authoritative sampler-boundary diagnostics added by
the post-9628c51 bounded runtime fix.

Covers:
  - [v2.sampler_boundary] event=sampling_start / sampling_end one-lines with
    request_id / restored_instance_id / node / class / patcher / diffusion
    model ids
  - first_sampler_step trace event emitted exactly once even when the
    per-step callback fires multiple times, and the original callback still
    receives every step
  - None callback is preserved (no wrapping, no crash)
  - exact retained-UNET object identity check: a sampler patcher that differs
    from the bridge-served object fails before sampling
  - the one-shot stall watchdog is marked on the first completed step
  - GPU-residency evidence is emitted without raising for no-parameter stubs

All tests use mocks/fakes only — no real ComfyUI/Modal/GPU.
"""

from __future__ import annotations

import io
import os
import time
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from comfymodal_runtime import runtime_executor as runtime_exec
from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey
from comfymodal_runtime.model_preload import V2LoaderBridge
from comfymodal_runtime.runtime_executor import (
    _COMFYMODAL_V2_SAMPLING_WRAPPER,
    _sampler_wrapper_dedup,
    _sampler_wrapper_dedup_lock,
)
from comfymodal_runtime.trace import RuntimeTrace


def _try_import_comfy_patcher_extension():
    try:
        import comfy.patcher_extension as pe
        return pe
    except ImportError:
        return None


def _make_faithful_wrapper_executor(original, wrappers):
    """Build a WrapperExecutor matching the real comfy API but importable
    without the full ComfyUI environment."""
    pe = _try_import_comfy_patcher_extension()
    if pe is not None:
        return pe.WrapperExecutor.new_executor(original, wrappers, 0)

    class _FakeWE:
        def __init__(self, orig, wlist, idx):
            self.original = orig
            self.wrappers = list(wlist)
            self.idx = idx
            self.is_last = idx == len(wlist)

        def __call__(self, *args, **kwargs):
            return _FakeWE(self.original, self.wrappers, self.idx + 1).execute(*args, **kwargs)

        def execute(self, *args, **kwargs):
            if self.is_last:
                return self.original(*args, **kwargs)
            return self.wrappers[self.idx](self, *args, **kwargs)

    return _FakeWE(original, wrappers, 0)


class _FakeDM:
    def __init__(self):
        self._hooks = []
        self.device = "cuda:0"
        self.current_device = "cuda:0"

    def register_forward_pre_hook(self, hook, **kwargs):
        self._hooks.append(hook)
        return hook

    def parameters(self):
        return iter([])


class _CpuParamsDM:
    """Diffusion-model fake whose parameters all live on CPU (the classic
    CPU-snapshot stall signature)."""

    class _CpuParam:
        device = "cpu"

    def __init__(self):
        self.device = "cpu"
        self.current_device = "cpu"

    def parameters(self):
        return iter([self._CpuParam(), self._CpuParam()])


class _FakePatcher:
    def __init__(self, dm=None):
        self.model = SimpleNamespace(diffusion_model=dm or _FakeDM())
        self.load_device = "cuda:0"
        self.current_device = "cuda:0"


def _ensure_bridge_has_fake_nodes(bridge):
    """Install minimal fake node classes on a bare bridge so use_ready_models
    can establish loader wrappers without importing the real ComfyUI ``nodes``
    module (which may be unavailable outside a full ComfyUI install).
    Uses the injectable ``V2LoaderBridge.install(nodes_module)`` path.
    Safe to call multiple times (idempotent)."""
    if bridge._original_methods:  # already installed
        return

    class _FakeUNETLoader:
        def load_unet(self, unet_name, weight_dtype):
            return (object(),)

    class _FakeCLIPLoader:
        def load_clip(self, clip_name, type="stable_diffusion", device="default"):
            return (object(),)

    class _FakeDualCLIPLoader:
        def load_clip(self, clip_name1, clip_name2, type, device="default"):
            return (object(),)

    class _FakeVAELoader:
        def load_vae(self, vae_name):
            return (f"vae:{vae_name}",)

    class _FakeCLIPTextEncode:
        def encode(self, clip, text):
            return (f"conditioning:{text}",)

    fake_nodes = SimpleNamespace(
        NODE_CLASS_MAPPINGS={
            "UNETLoader": _FakeUNETLoader,
            "CLIPLoader": _FakeCLIPLoader,
            "DualCLIPLoader": _FakeDualCLIPLoader,
            "VAELoader": _FakeVAELoader,
            "CLIPTextEncode": _FakeCLIPTextEncode,
        }
    )
    bridge.install(fake_nodes)


class SamplerBoundaryDiagnosticsTests(unittest.TestCase):
    """sampling_start/end one-lines + first_sampler_step once per request."""

    def setUp(self):
        _sampler_wrapper_dedup.clear()
        from comfymodal_runtime import model_preload as mp
        self.mp = mp
        _cleanup = mp._SAMPLER_STALL_WATCHDOGS.copy()
        with mp._SAMPLER_STALL_WATCHDOG_LOCK:
            for wd in list(mp._SAMPLER_STALL_WATCHDOGS.values()):
                wd.cancel()
            mp._SAMPLER_STALL_WATCHDOGS.clear()
        self.addCleanup(self._cleanup_watchdogs)
        self.trace = RuntimeTrace(request_id="samp-boundary", process="test")
        self._token = self.mp._ACTIVE_REQUEST_TRACE.set(self.trace)

    def _cleanup_watchdogs(self):
        try:
            self.mp._ACTIVE_REQUEST_TRACE.reset(self._token)
        except Exception:
            pass
        with self.mp._SAMPLER_STALL_WATCHDOG_LOCK:
            for wd in list(self.mp._SAMPLER_STALL_WATCHDOGS.values()):
                wd.cancel()
            self.mp._SAMPLER_STALL_WATCHDOGS.clear()

    def _run_wrapper(self, guider, callback, original=None, step_count=0):
        if original is None:
            def original(*args, **kwargs):
                cb = args[3] if len(args) > 3 else None
                if callable(cb):
                    for _i in range(step_count):
                        cb(_i, "denoised", "x", 8)
                return {"latent": "ok"}
        executor = _make_faithful_wrapper_executor(original, [_COMFYMODAL_V2_SAMPLING_WRAPPER])
        result = executor.execute(
            guider,
            type("S", (), {"__len__": lambda self: 9})(),  # 8 steps
            {}, callback, None, None, None, None,
        )
        return result

    def _make_guider(self, patcher=None, node_id="n1", node_class="KSampler"):
        guider = SimpleNamespace(
            _node_id=node_id,
            _class_type=node_class,
        )
        if patcher is not None:
            guider.model_patcher = patcher
        return guider

    def test_sampling_start_end_boundary_lines(self):
        """[v2.sampler_boundary] sampling_start and sampling_end emitted with
        node/class/patcher/diffusion-model identity."""
        patcher = _FakePatcher()
        guider = self._make_guider(patcher=patcher, node_id="n-1", node_class="KSampler")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self._run_wrapper(guider, callback=None)
        lines = buf.getvalue()
        self.assertIn("[v2.sampler_boundary] event=sampling_start", lines)
        self.assertIn("[v2.sampler_boundary] event=sampling_end", lines)
        start_line = [l for l in lines.splitlines() if "event=sampling_start" in l][0]
        self.assertIn("request_id=samp-boundary", start_line)
        self.assertIn("node_id=n-1", start_line)
        self.assertIn("node_class=KSampler", start_line)
        self.assertIn(f"patcher_object_id={id(patcher)}", start_line)
        self.assertIn(f"diffusion_model_object_id={id(patcher.model.diffusion_model)}", start_line)
        # sampling_start/end trace events carry patcher/dm identity too.
        start_events = [e for e in self.trace.events if e.name == "sampling_start"]
        self.assertEqual(len(start_events), 1)
        self.assertEqual(start_events[0].metadata.get("node_id"), "n-1")
        self.assertEqual(
            start_events[0].metadata.get("diffusion_model_object_id"),
            str(id(patcher.model.diffusion_model)),
        )

    def test_first_sampler_step_emitted_once_callback_all_calls(self):
        """first_sampler_step fires once even when the step callback fires
        multiple times; the original callback still gets every step."""
        patcher = _FakePatcher()
        guider = self._make_guider(patcher=patcher, node_id="n-2", node_class="KSampler")
        step_calls = []
        def callback(*args):
            step_calls.append(args)
            return "cb-ok"
        buf = io.StringIO()
        with redirect_stdout(buf):
            self._run_wrapper(guider, callback=callback, step_count=3)
        self.assertEqual(len(step_calls), 3, "original callback must see every step")
        # The callback receives (step_index, denoised, x, total_steps) per step.
        self.assertEqual([c[0] for c in step_calls], [0, 1, 2])
        self.assertEqual([c[3] for c in step_calls], [8, 8, 8])
        first_step_events = [e for e in self.trace.events if e.name == "first_sampler_step"]
        self.assertEqual(len(first_step_events), 1, "first_sampler_step must fire exactly once")
        meta = first_step_events[0].metadata
        self.assertEqual(meta.get("node_id"), "n-2")
        self.assertEqual(meta.get("node_class"), "KSampler")
        self.assertEqual(meta.get("steps"), 8)
        # The one-line boundary is also emitted exactly once.
        step_lines = [l for l in buf.getvalue().splitlines() if "event=first_sampler_step" in l]
        self.assertEqual(len(step_lines), 1)

    def test_none_callback_preserved(self):
        """None callback is preserved (no wrapping) and no crash."""
        patcher = _FakePatcher()
        guider = self._make_guider(patcher=patcher, node_id="n-3", node_class="KSampler")
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = self._run_wrapper(guider, callback=None)
        self.assertEqual(result, {"latent": "ok"})
        self.assertEqual(
            len([e for e in self.trace.events if e.name == "first_sampler_step"]), 0,
        )

    def test_first_step_marks_watchdog(self):
        """The first completed sampler step marks the one-shot watchdog."""
        from comfymodal_runtime.model_preload import start_sampler_stall_watchdog
        with patch.object(self.mp, "_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S", 2.0), \
             patch.object(self.mp, "_SAMPLER_STALL_FIRST_STEP_TIMEOUT_S", 2.0):
            start_sampler_stall_watchdog(
                request_id="samp-boundary", restored_instance_id="ri-wd",
            )
            with self.mp._SAMPLER_STALL_WATCHDOG_LOCK:
                watchdog = self.mp._SAMPLER_STALL_WATCHDOGS.get("samp-boundary")
            self.assertIsNotNone(watchdog)
            patcher = _FakePatcher()
            guider = self._make_guider(patcher=patcher, node_id="n-4", node_class="KSampler")
            buf = io.StringIO()
            with redirect_stdout(buf):
                self._run_wrapper(
                    guider,
                    callback=lambda *a: "step",
                    step_count=2,
                )
            self.assertTrue(watchdog._step_seen)
            self.assertIsNotNone(watchdog._step_latency_ms)
            # Identity enrichment from the sampler wrapper.
            self.assertEqual(watchdog.sampler_node_id, "n-4")
            self.assertEqual(watchdog.sampler_class, "KSampler")
            self.assertEqual(
                watchdog.diffusion_model_object_id,
                str(id(patcher.model.diffusion_model)),
            )
            self.mp.cancel_sampler_stall_watchdog("samp-boundary")

    def test_wrapper_arms_watchdog_at_sampling_start(self):
        """Production arming lives at the sampling_start boundary: running the
        sampler wrapper (without any pre-arming) must arm the one-shot
        watchdog with the sampler identity and request key."""
        with self.mp._SAMPLER_STALL_WATCHDOG_LOCK:
            self.assertNotIn("samp-boundary", self.mp._SAMPLER_STALL_WATCHDOGS)
        patcher = _FakePatcher()
        guider = self._make_guider(patcher=patcher, node_id="n-6", node_class="KSampler")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self._run_wrapper(
                guider,
                callback=lambda *a: "step",
                step_count=2,
            )
        with self.mp._SAMPLER_STALL_WATCHDOG_LOCK:
            watchdog = self.mp._SAMPLER_STALL_WATCHDOGS.get("samp-boundary")
        self.assertIsNotNone(
            watchdog, "the wrapper must arm the watchdog at sampling_start"
        )
        # Armed with the sampler/node identity captured at the boundary.
        self.assertEqual(watchdog.request_id, "samp-boundary")
        self.assertEqual(watchdog.sampler_node_id, "n-6")
        self.assertEqual(watchdog.sampler_class, "KSampler")
        self.assertEqual(
            watchdog.diffusion_model_object_id,
            str(id(patcher.model.diffusion_model)),
        )
        # The armed boundary line is emitted by the wrapper path.
        self.assertIn("[v2.sampler_stall_watchdog] stage=armed", buf.getvalue())
        self.mp.cancel_sampler_stall_watchdog("samp-boundary")

    def test_gpu_residency_evidence_emitted_no_raise_for_stub(self):
        """[v2.unet_gpu_residency] is emitted at sampling_start; no-parameter
        stubs do not raise (diagnostic mode preserved)."""
        patcher = _FakePatcher()
        guider = self._make_guider(patcher=patcher, node_id="n-5", node_class="KSampler")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self._run_wrapper(guider, callback=None)
        self.assertIn("[v2.unet_gpu_residency]", buf.getvalue())
        # Stub (no parameters) must not raise.
        self.assertIn("status=no_params", buf.getvalue())


class SamplerIdentityMismatchTests(unittest.TestCase):
    """Exact retained-UNET identity check between bridge and sampler."""

    def setUp(self):
        _sampler_wrapper_dedup.clear()
        from comfymodal_runtime import model_preload as mp
        self.mp = mp
        self.trace = RuntimeTrace(request_id="samp-mismatch", process="test")
        self._token = self.mp._ACTIVE_REQUEST_TRACE.set(self.trace)
        self.bridge = V2LoaderBridge()
        _ensure_bridge_has_fake_nodes(self.bridge)
        self.model_key = ModelRestoreKey(
            unet_identity="u.safetensors", clip_identity="c.safetensors", clip_type="sd3",
        )

    def tearDown(self):
        try:
            self.mp._ACTIVE_REQUEST_TRACE.reset(self._token)
        except Exception:
            pass

    def _publish(self, unet):
        self.bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=PrefillKey(model_key=self.model_key),
            model_spec={
                "loaders": {
                    "unet": [{"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"}],
                    "clip": [],
                    "vae": [],
                },
            },
            unet=unet,
            clip=object(),
        )
        from comfymodal_runtime.model_preload import _ACTIVE_V2_LOADER_BRIDGE
        return _ACTIVE_V2_LOADER_BRIDGE.set(self.bridge)

    def test_sampler_gets_served_object_passes(self):
        """Guider patcher == bridge-served retained object -> passes."""
        unet = _FakePatcher()
        token = self._publish(unet)
        try:
            guider = SimpleNamespace(_node_id="n-1", _class_type="KSampler", model_patcher=unet)
            executor = _make_faithful_wrapper_executor(
                lambda *a, **k: {"ok": True},
                [_COMFYMODAL_V2_SAMPLING_WRAPPER],
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = executor.execute(
                    guider, type("S", (), {"__len__": lambda self: 9})(),
                    {}, None, None, None, None, None,
                )
            self.assertEqual(result, {"ok": True})
        finally:
            self.mp._ACTIVE_V2_LOADER_BRIDGE.reset(token)

    def test_sampler_gets_different_object_fails(self):
        """Guider patcher differs from the bridge-served object -> fail before
        sampling with the exact identity-mismatch error.  The in-flight dedup
        key must also be released so a later sampler is never suppressed."""
        served = _FakePatcher()
        different = _FakePatcher()
        token = self._publish(served)
        try:
            guider = SimpleNamespace(_node_id="n-1", _class_type="KSampler", model_patcher=different)
            executor = _make_faithful_wrapper_executor(
                lambda *a, **k: {"ok": True},
                [_COMFYMODAL_V2_SAMPLING_WRAPPER],
            )
            buf = io.StringIO()
            with redirect_stdout(buf), self.assertRaises(RuntimeError) as ctx:
                executor.execute(
                    guider, type("S", (), {"__len__": lambda self: 9})(),
                    {}, None, None, None, None,
                )
            msg = str(ctx.exception)
            self.assertIn("Retained UNET identity mismatch", msg)
            self.assertIn("bridge", msg)
            self.assertIn("sampler", msg)
            # The sampler must NOT have run.
            self.assertNotIn("[v2.sampler_boundary] event=sampling_start", buf.getvalue())
            # Fail-closed raise must release the in-flight dedup key.
            with _sampler_wrapper_dedup_lock:
                self.assertEqual(
                    len(_sampler_wrapper_dedup), 0,
                    "identity-mismatch raise must release the dedup key",
                )
        finally:
            self.mp._ACTIVE_V2_LOADER_BRIDGE.reset(token)

    def test_no_bridge_active_no_fail(self):
        """With no active bridge (non-snapshot path) the wrapper still runs."""
        guider = SimpleNamespace(_node_id="n-1", _class_type="KSampler", model_patcher=_FakePatcher())
        executor = _make_faithful_wrapper_executor(
            lambda *a, **k: {"ok": True},
            [_COMFYMODAL_V2_SAMPLING_WRAPPER],
        )
        result = executor.execute(
            guider, type("S", (), {"__len__": lambda self: 9})(),
            {}, None, None, None, None, None,
        )
        self.assertEqual(result, {"ok": True})

    def test_rewrapped_patcher_same_diffusion_model_passes(self):
        """ComfyUI ModelPatcher delegates / CacheDiT wrapper re-attach create a
        NEW patcher around the SAME diffusion model.  The logical identity
        (resolved diffusion model) matches, so the sampler runs."""
        dm = _FakeDM()
        served = _FakePatcher(dm=dm)
        token = self._publish(served)
        try:
            # Re-wrap: a NEW patcher object wrapping the SAME diffusion model.
            rewrapped = _FakePatcher(dm=dm)
            self.assertNotEqual(id(served), id(rewrapped))
            guider = SimpleNamespace(_node_id="n-1", _class_type="KSampler", model_patcher=rewrapped)
            executor = _make_faithful_wrapper_executor(
                lambda *a, **k: {"ok": True},
                [_COMFYMODAL_V2_SAMPLING_WRAPPER],
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = executor.execute(
                    guider, type("S", (), {"__len__": lambda self: 9})(),
                    {}, None, None, None, None, None,
                )
            self.assertEqual(result, {"ok": True})
            # The emitted check line logs BOTH patcher and diffusion ids.
            line = buf.getvalue()
            self.assertIn("patcher_a_object_id=", line)
            self.assertIn("patcher_b_object_id=", line)
            self.assertIn("diffusion_a_object_id=", line)
            self.assertIn("diffusion_b_object_id=", line)
        finally:
            self.mp._ACTIVE_V2_LOADER_BRIDGE.reset(token)

    def test_rewrapped_patcher_different_diffusion_model_fails(self):
        """A re-wrapped patcher around a DIFFERENT diffusion model must raise —
        never silently sample another model."""
        served = _FakePatcher()
        token = self._publish(served)
        try:
            different_dm_patcher = _FakePatcher()  # distinct dm
            guider = SimpleNamespace(_node_id="n-1", _class_type="KSampler", model_patcher=different_dm_patcher)
            executor = _make_faithful_wrapper_executor(
                lambda *a, **k: {"ok": True},
                [_COMFYMODAL_V2_SAMPLING_WRAPPER],
            )
            buf = io.StringIO()
            with redirect_stdout(buf), self.assertRaises(RuntimeError) as ctx:
                executor.execute(
                    guider, type("S", (), {"__len__": lambda self: 9})(),
                    {}, None, None, None, None, None,
                )
            self.assertIn("Retained UNET identity mismatch", str(ctx.exception))
            self.assertNotIn("[v2.sampler_boundary] event=sampling_start", buf.getvalue())
        finally:
            self.mp._ACTIVE_V2_LOADER_BRIDGE.reset(token)


class SamplerResidencyEnforcementTests(unittest.TestCase):
    """GPU-residency enforcement is gated to the production CPU-snapshot path
    sampling the exact retained snapshot/bridge model.  All other paths report
    diagnostic status instead of raising."""

    def setUp(self):
        _sampler_wrapper_dedup.clear()
        from comfymodal_runtime import model_preload as mp
        self.mp = mp
        with mp._PRODUCTION_CPU_SNAPSHOT_REQUESTS_LOCK:
            mp._PRODUCTION_CPU_SNAPSHOT_REQUESTS.clear()
        self.addCleanup(self._cleanup_marker)
        self.trace = RuntimeTrace(request_id="samp-res", process="test")
        self._token = self.mp._ACTIVE_REQUEST_TRACE.set(self.trace)
        self.bridge = V2LoaderBridge()
        _ensure_bridge_has_fake_nodes(self.bridge)
        self.model_key = ModelRestoreKey(
            unet_identity="u.safetensors", clip_identity="c.safetensors", clip_type="sd3",
        )

    def _cleanup_marker(self):
        try:
            self.mp._ACTIVE_REQUEST_TRACE.reset(self._token)
        except Exception:
            pass
        with self.mp._PRODUCTION_CPU_SNAPSHOT_REQUESTS_LOCK:
            self.mp._PRODUCTION_CPU_SNAPSHOT_REQUESTS.clear()
        with self.mp._SAMPLER_STALL_WATCHDOG_LOCK:
            for wd in list(self.mp._SAMPLER_STALL_WATCHDOGS.values()):
                wd.cancel()
            self.mp._SAMPLER_STALL_WATCHDOGS.clear()

    def _run_wrapper(self, guider):
        executor = _make_faithful_wrapper_executor(
            lambda *a, **k: {"ok": True},
            [_COMFYMODAL_V2_SAMPLING_WRAPPER],
        )
        return executor.execute(
            guider, type("S", (), {"__len__": lambda self: 9})(),
            {}, None, None, None, None, None,
        )

    def _publish(self, unet, request_id="samp-res"):
        self.trace.request_id = request_id
        self.bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=PrefillKey(model_key=self.model_key),
            model_spec={
                "loaders": {
                    "unet": [{"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"}],
                    "clip": [],
                    "vae": [],
                },
            },
            unet=unet,
            clip=object(),
        )
        from comfymodal_runtime.model_preload import _ACTIVE_V2_LOADER_BRIDGE
        return _ACTIVE_V2_LOADER_BRIDGE.set(self.bridge)

    def test_cpu_only_patcher_non_snapshot_reports_not_raises(self):
        """Normal non-snapshot CPU-only path: cpu_resident status is reported
        with enforce=0 and the sampler still runs (no raise)."""
        patcher = _FakePatcher(dm=_CpuParamsDM())
        patcher.current_device = "cpu"
        guider = SimpleNamespace(_node_id="n-1", _class_type="KSampler", model_patcher=patcher)
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = self._run_wrapper(guider)
        self.assertEqual(result, {"ok": True})
        self.assertIn("[v2.unet_gpu_residency]", buf.getvalue())
        self.assertIn("status=cpu_resident", buf.getvalue())
        self.assertIn("enforce=0", buf.getvalue())

    def test_cpu_only_patcher_production_snapshot_raises(self):
        """Production CPU-snapshot path sampling the exact retained bridge
        object: CPU-resident activation failure raises before sampling."""
        patcher = _FakePatcher(dm=_CpuParamsDM())
        patcher.current_device = "cpu"
        self.mp.mark_production_cpu_snapshot_request("samp-res")
        token = self._publish(patcher)
        try:
            guider = SimpleNamespace(_node_id="n-1", _class_type="KSampler", model_patcher=patcher)
            buf = io.StringIO()
            with redirect_stdout(buf), self.assertRaises(RuntimeError) as ctx:
                self._run_wrapper(guider)
            msg = str(ctx.exception)
            self.assertIn("CPU-resident", msg)
            self.assertIn("sampler_wrapper_before_sample", msg)
            # The sampler must NOT have run.
            self.assertNotIn("[v2.sampler_boundary] event=sampling_start", buf.getvalue())
        finally:
            self.mp._ACTIVE_V2_LOADER_BRIDGE.reset(token)

    def test_production_snapshot_with_different_model_not_enforced(self):
        """A production-marked request sampling a DIFFERENT model than the
        retained bridge object is not residency-enforced (it is not the exact
        retained snapshot/bridge object); diagnostics only."""
        served = _FakePatcher(dm=_FakeDM())
        other = _FakePatcher(dm=_CpuParamsDM())
        other.current_device = "cpu"
        self.mp.mark_production_cpu_snapshot_request("samp-res")
        token = self._publish(served)
        try:
            # Different patcher + different dm -> identity check raises first.
            guider = SimpleNamespace(_node_id="n-1", _class_type="KSampler", model_patcher=other)
            buf = io.StringIO()
            with redirect_stdout(buf), self.assertRaises(RuntimeError) as ctx:
                self._run_wrapper(guider)
            self.assertIn("Retained UNET identity mismatch", str(ctx.exception))
        finally:
            self.mp._ACTIVE_V2_LOADER_BRIDGE.reset(token)

    def test_meta_only_patcher_never_raises(self):
        """Meta/unknown device models are classified unknown/partial, never
        CPU-resident — the sampler runs even on the production snapshot path."""
        class _MetaDM(_FakeDM):
            class _MetaParam:
                device = "meta"

            def parameters(self):
                return iter([self._MetaParam(), self._MetaParam()])

        patcher = _FakePatcher(dm=_MetaDM())
        self.mp.mark_production_cpu_snapshot_request("samp-res")
        token = self._publish(patcher)
        try:
            guider = SimpleNamespace(_node_id="n-1", _class_type="KSampler", model_patcher=patcher)
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = self._run_wrapper(guider)
            self.assertEqual(result, {"ok": True})
            self.assertIn("status=unknown", buf.getvalue())
        finally:
            self.mp._ACTIVE_V2_LOADER_BRIDGE.reset(token)


class SamplerNodeContextAndCleanupTests(unittest.TestCase):
    """Authoritative sampler node context (node id 1242 / ClownsharKSampler_Beta
    when present) reaches the watchdog arm, sampling_start, first_unet_forward,
    first_sampler_step and sampling_end markers; successful completion and
    failure both finish the single watchdog with no timeout records."""

    def setUp(self):
        _sampler_wrapper_dedup.clear()
        from comfymodal_runtime import model_preload as mp
        self.mp = mp
        with mp._SAMPLER_STALL_WATCHDOG_LOCK:
            for wd in list(mp._SAMPLER_STALL_WATCHDOGS.values()):
                wd.cancel()
            mp._SAMPLER_STALL_WATCHDOGS.clear()
        self.addCleanup(self._cleanup)
        self.trace = RuntimeTrace(request_id="samp-ctx", process="test")
        self._token = self.mp._ACTIVE_REQUEST_TRACE.set(self.trace)
        self._ctx_token = None

    def _cleanup(self):
        try:
            if self._ctx_token is not None:
                runtime_exec._current_node_context.reset(self._ctx_token)
        except Exception:
            pass
        try:
            self.mp._ACTIVE_REQUEST_TRACE.reset(self._token)
        except Exception:
            pass
        with self.mp._SAMPLER_STALL_WATCHDOG_LOCK:
            for wd in list(self.mp._SAMPLER_STALL_WATCHDOGS.values()):
                wd.cancel()
            self.mp._SAMPLER_STALL_WATCHDOGS.clear()

    def _guider_without_node_attrs(self, patcher=None):
        """A plain guider that does NOT carry _node_id / _class_type (stock
        ComfyUI guider): the authoritative node context must come from the
        active ``_current_node_context`` ContextVar instead."""
        guider = SimpleNamespace()
        if patcher is not None:
            guider.model_patcher = patcher
        return guider

    def _run_wrapper(self, guider, callback, original=None, step_count=0):
        if original is None:
            def original(*args, **kwargs):
                cb = args[3] if len(args) > 3 else None
                if callable(cb):
                    for _i in range(step_count):
                        cb(_i, "denoised", "x", 8)
                return {"latent": "ok"}
        executor = _make_faithful_wrapper_executor(original, [_COMFYMODAL_V2_SAMPLING_WRAPPER])
        return executor.execute(
            guider,
            type("S", (), {"__len__": lambda self: 9})(),  # 8 steps
            {}, callback, None, None, None, None,
        )

    def _armed_watchdog(self):
        with self.mp._SAMPLER_STALL_WATCHDOG_LOCK:
            return self.mp._SAMPLER_STALL_WATCHDOGS.get("samp-ctx")

    def test_node_context_fallback_reaches_all_sampler_markers(self):
        """With no guider attributes, the active _current_node_context
        (node id 1242 / ClownsharKSampler_Beta) reaches the watchdog arm,
        sampling_start, first_unet_forward, first_sampler_step and
        sampling_end."""
        patcher = _FakePatcher()
        guider = self._guider_without_node_attrs(patcher)
        self._ctx_token = runtime_exec._current_node_context.set(
            ("1242", "ClownsharKSampler_Beta")
        )
        buf = io.StringIO()
        with patch.object(self.mp, "_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S", 2.0), \
             patch.object(self.mp, "_SAMPLER_STALL_FIRST_STEP_TIMEOUT_S", 2.0), \
             redirect_stdout(buf):
            self._run_wrapper(guider, callback=lambda *a: "step", step_count=2)
        # Watchdog arm carries the authoritative node context.
        watchdog = self._armed_watchdog()
        self.assertIsNotNone(watchdog)
        self.assertEqual(watchdog.sampler_node_id, "1242")
        self.assertEqual(watchdog.sampler_class, "ClownsharKSampler_Beta")
        # first_unet_forward reaches the watchdog carrying that context.
        self.mp.mark_first_unet_forward("samp-ctx")
        self.assertTrue(watchdog._forward_seen)
        self.assertIsNotNone(watchdog._forward_latency_ms)
        # sampling_start / first_sampler_step / sampling_end trace events.
        events = {e.name: e for e in self.trace.events}
        for marker in ("sampling_start", "first_sampler_step", "sampling_end"):
            self.assertIn(marker, events)
            self.assertEqual(events[marker].metadata.get("node_id"), "1242")
            self.assertEqual(events[marker].metadata.get("node_class"), "ClownsharKSampler_Beta")
        # One-lines carry it too.
        lines = buf.getvalue()
        for event in ("sampling_start", "first_sampler_step", "sampling_end"):
            event_lines = [l for l in lines.splitlines() if f"event={event}" in l]
            self.assertTrue(event_lines, f"{event} one-line missing")
            self.assertIn("node_id=1242", event_lines[0])
            self.assertIn("node_class=ClownsharKSampler_Beta", event_lines[0])
        # Owner cleanup: single watchdog finished, no timeout records.
        self.mp.cancel_sampler_stall_watchdog("samp-ctx")
        time.sleep(0.3)
        self.assertNotIn("status=timeout", buf.getvalue())
        with self.mp._SAMPLER_STALL_WATCHDOG_LOCK:
            self.assertNotIn("samp-ctx", self.mp._SAMPLER_STALL_WATCHDOGS)

    def test_guider_attributes_win_over_context_fallback(self):
        """Guider-owned _node_id/_class_type stay authoritative even when the
        node-context ContextVar names a different node."""
        patcher = _FakePatcher()
        guider = SimpleNamespace(_node_id="n-1", _class_type="KSampler", model_patcher=patcher)
        self._ctx_token = runtime_exec._current_node_context.set(
            ("1242", "ClownsharKSampler_Beta")
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            self._run_wrapper(guider, callback=lambda *a: "step", step_count=1)
        watchdog = self._armed_watchdog()
        self.assertIsNotNone(watchdog)
        self.assertEqual(watchdog.sampler_node_id, "n-1")
        self.assertEqual(watchdog.sampler_class, "KSampler")
        start_events = [e for e in self.trace.events if e.name == "sampling_start"]
        self.assertEqual(start_events[0].metadata.get("node_id"), "n-1")
        self.mp.cancel_sampler_stall_watchdog("samp-ctx")

    def test_partial_guider_pair_never_mixes_with_context_var(self):
        """A partial guider pair (node_id only) must NEVER mix one guider field
        with one ContextVar field: the complete ContextVar pair (1242 /
        ClownsharKSampler_Beta) wins as a unit."""
        patcher = _FakePatcher()
        guider = SimpleNamespace(_node_id="n-partial", model_patcher=patcher)
        self._ctx_token = runtime_exec._current_node_context.set(
            ("1242", "ClownsharKSampler_Beta")
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            self._run_wrapper(guider, callback=lambda *a: "step", step_count=1)
        watchdog = self._armed_watchdog()
        self.assertIsNotNone(watchdog)
        # Complete ContextVar pair wins as a unit; no guider/ContextVar mix.
        self.assertEqual(watchdog.sampler_node_id, "1242")
        self.assertEqual(watchdog.sampler_class, "ClownsharKSampler_Beta")
        start_events = [e for e in self.trace.events if e.name == "sampling_start"]
        self.assertEqual(start_events[0].metadata.get("node_id"), "1242")
        self.assertEqual(start_events[0].metadata.get("node_class"), "ClownsharKSampler_Beta")
        self.mp.cancel_sampler_stall_watchdog("samp-ctx")

    def test_partial_sources_return_blank_not_mixed(self):
        """When neither source provides a complete pair, no mixed or partial
        identity is reported — both fields are blank rather than fabricated."""
        patcher = _FakePatcher()
        # Partial guider node_id + partial ContextVar class: mixing would
        # fabricate ("n-only", "ClownsharKSampler_Beta"); both blank instead.
        guider = SimpleNamespace(_node_id="n-only", model_patcher=patcher)
        self._ctx_token = runtime_exec._current_node_context.set(
            ("", "ClownsharKSampler_Beta")
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            self._run_wrapper(guider, callback=lambda *a: "step", step_count=1)
        watchdog = self._armed_watchdog()
        self.assertIsNotNone(watchdog)
        self.assertEqual(watchdog.sampler_node_id, "")
        self.assertEqual(watchdog.sampler_class, "")
        start_events = [e for e in self.trace.events if e.name == "sampling_start"]
        self.assertEqual(start_events[0].metadata.get("node_id"), "")
        self.assertEqual(start_events[0].metadata.get("node_class"), "")
        self.mp.cancel_sampler_stall_watchdog("samp-ctx")

    def test_successful_completion_cleanup_no_timeout(self):
        """Successful completion marks the watchdog; the owner cleanup path
        finishes it and no timeout records are emitted."""
        patcher = _FakePatcher()
        guider = self._guider_without_node_attrs(patcher)
        buf = io.StringIO()
        with patch.object(self.mp, "_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S", 2.0), \
             patch.object(self.mp, "_SAMPLER_STALL_FIRST_STEP_TIMEOUT_S", 2.0), \
             redirect_stdout(buf):
            self._run_wrapper(guider, callback=lambda *a: "step", step_count=2)
        watchdog = self._armed_watchdog()
        self.assertIsNotNone(watchdog)
        # first_sampler_step fired during the run; mark the forward too.
        self.assertTrue(watchdog._step_seen)
        self.mp.mark_first_unet_forward("samp-ctx")
        self.assertTrue(watchdog._forward_seen)
        # Owner cleanup path (modal_app finally equivalent).
        self.mp.cancel_sampler_stall_watchdog("samp-ctx")
        time.sleep(0.3)
        with self.mp._SAMPLER_STALL_WATCHDOG_LOCK:
            self.assertNotIn("samp-ctx", self.mp._SAMPLER_STALL_WATCHDOGS)
        self.assertNotIn("status=timeout", buf.getvalue())

    def test_failure_cleanup_no_timeout(self):
        """If the inner executor raises, sampling_end is still emitted and the
        single watchdog is finished by the cleanup path with no timeout."""
        patcher = _FakePatcher()
        guider = self._guider_without_node_attrs(patcher)

        def failing(*args, **kwargs):
            raise RuntimeError("sampler boom")

        buf = io.StringIO()
        with patch.object(self.mp, "_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S", 2.0), \
             patch.object(self.mp, "_SAMPLER_STALL_FIRST_STEP_TIMEOUT_S", 2.0), \
             redirect_stdout(buf), self.assertRaises(RuntimeError):
            self._run_wrapper(guider, callback=None, original=failing)
        # sampling_end still emitted by the finally block.
        self.assertIn("[v2.sampler_boundary] event=sampling_end", buf.getvalue())
        self.assertIn("event=sampling_start", buf.getvalue())
        # Owner cleanup path removes the watchdog; failure does not time out.
        self.mp.cancel_sampler_stall_watchdog("samp-ctx")
        time.sleep(0.3)
        with self.mp._SAMPLER_STALL_WATCHDOG_LOCK:
            self.assertNotIn("samp-ctx", self.mp._SAMPLER_STALL_WATCHDOGS)
        self.assertNotIn("status=timeout", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
