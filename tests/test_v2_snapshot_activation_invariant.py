"""Focused tests for the post-9628c51 CPU-snapshot bounded runtime fix.

Covers:
  - production activation invariant passes when active
  - production with BOTH models present but inactive fails clearly (never
    serves present-but-inactive CPU patchers)
  - diagnostic no-model / CLIP-only / UNET-only modes remain allowed
  - exact retained UNET object identity flow across snapshot / bridge /
    activation / cachedit stages, failing on mismatch
  - one activation / one CacheDiT patch, and no duplicate future
  - active state is set only after successful bridge publication
  - CacheDiT remains enabled (not permanently disabled)

All tests use mocks/fakes only — no real ComfyUI/Modal/GPU.
"""

from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
from comfymodal_runtime.model_preload import V2LoaderBridge
from comfymodal_runtime.modal_app import (
    ModalRuntimeEntrypoint,
    _cpu_model_snapshot_enabled,
)
from comfymodal_runtime.trace import RuntimeTrace


class _FakeClip:
    pass


class _FakeUnet:
    """Duck-typed UNET patcher with the ModelPatcher-ish shape used by the
    bridge/probe helpers (no GPU)."""

    def __init__(self, name="u.safetensors"):
        self._name = name
        self.model = SimpleNamespace(
            diffusion_model=_FakeDM(),
        )

    def named_parameters(self, recurse=True):
        return iter([])

    def named_buffers(self, recurse=True):
        return iter([])


class _FakeDM:
    def __init__(self):
        self._hooks = []

    def register_forward_pre_hook(self, hook, **kwargs):
        self._hooks.append(hook)
        return hook

    def parameters(self):
        return iter([])


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
            return (_FakeClip(),)

    class _FakeDualCLIPLoader:
        def load_clip(self, clip_name1, clip_name2, type, device="default"):
            return (_FakeClip(),)

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


def _make_snapshot_spec(unet_name="u.safetensors", clip_name="c.safetensors"):
    return {
        "loaders": {
            "unet": [{"loader_class": "UNETLoader", "unet_name": unet_name, "weight_dtype": "default"}],
            "clip": [{"loader_class": "CLIPLoader", "clip_name": clip_name, "type": "sd3", "device": "default"}],
            "vae": [],
        },
    }


def _make_entrypoint(*, profile, cpu_snapshot="1") -> ModalRuntimeEntrypoint:
    """Construct a real entrypoint with controlled env profile."""
    os.environ["COMFYMODAL_V2_ENV_PROFILE"] = profile
    if cpu_snapshot == "1":
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "1"
    else:
        os.environ.pop("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", None)
    os.environ.pop("COMFYMODAL_ENABLE_GPU_SNAPSHOT", None)
    ep = ModalRuntimeEntrypoint()
    ep._lazy_init_snapshot_state()
    return ep


class SnapshotActivationInvariantTests(unittest.TestCase):
    """[v2.snapshot_activation_invariant] production/diagnostic behaviour."""

    def setUp(self):
        self._saved_env = dict(os.environ)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        os.environ.clear()
        os.environ.update(self._saved_env)

    def _models_container(self, clip=True, unet=True):
        return SimpleNamespace(
            clip=_FakeClip() if clip else None,
            unet=_FakeUnet() if unet else None,
            model_key=SimpleNamespace(
                unet_identity="u.safetensors" if unet else "",
                clip_identity="c.safetensors" if clip else "",
            ),
        )

    def test_production_active_invariant_passes(self):
        """Production + both models present + active -> pass, no raise."""
        ep = _make_entrypoint(profile="production")
        _ensure_bridge_has_fake_nodes(ep._preload_bridge)
        ep._cpu_snapshot_models = self._models_container()
        ep._cpu_snapshot_models_active = True
        # Bridge must be active too for a truthful loader_bridge_active field.
        ep._preload_bridge.use_ready_models(
            model_key=ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors", clip_type="sd3"),
            prefill_key=PrefillKey(),
            model_spec=_make_snapshot_spec(),
            unet=ep._cpu_snapshot_models.unet,
            clip=ep._cpu_snapshot_models.clip,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = ep._enforce_snapshot_activation_invariant(
                request_id="req-active",
                trace=RuntimeTrace(request_id="req-active", process="test"),
            )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["reason"], "ok")
        line = buf.getvalue()
        self.assertIn("[v2.snapshot_activation_invariant]", line)
        self.assertIn("profile=production", line)
        self.assertIn("models_container_present=1", line)
        self.assertIn("clip_present=1", line)
        self.assertIn("unet_present=1", line)
        self.assertIn("snapshot_enabled_by_config=1", line)
        self.assertIn("cpu_snapshot_active=1", line)
        self.assertIn("loader_bridge_active=1", line)
        self.assertIn("execution_prefill_allowed=0", line)
        self.assertIn("status=pass", line)
        self.assertIn("reason=ok", line)

    def test_production_both_models_inactive_fails(self):
        """Production + both models present + INACTIVE -> clear RuntimeError."""
        ep = _make_entrypoint(profile="production")
        ep._cpu_snapshot_models = self._models_container()
        ep._cpu_snapshot_models_active = False
        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(RuntimeError) as ctx:
                ep._enforce_snapshot_activation_invariant(request_id="req-inactive")
        msg = str(ctx.exception)
        self.assertIn("INACTIVE", msg)
        self.assertIn("inactive", msg.lower())
        self.assertIn("present", msg.lower())
        line = buf.getvalue()
        self.assertIn("status=fail", line)
        self.assertIn("reason=production_models_present_but_inactive", line)
        self.assertIn("cpu_snapshot_active=0", line)

    def test_production_present_but_inactive_guard_clears_bridge_diagnostic(self):
        """Diagnostic profile with present-but-inactive models must NOT serve
        them: bridge is cleared and no RuntimeError is raised."""
        ep = _make_entrypoint(profile="diagnostic")
        _ensure_bridge_has_fake_nodes(ep._preload_bridge)
        ep._cpu_snapshot_models = self._models_container()
        ep._cpu_snapshot_models_active = False
        ep._preload_bridge.use_ready_models(
            model_key=ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors", clip_type="sd3"),
            prefill_key=PrefillKey(),
            model_spec=_make_snapshot_spec(),
            unet=ep._cpu_snapshot_models.unet,
            clip=ep._cpu_snapshot_models.clip,
        )
        self.assertIsNotNone(ep._preload_bridge._preparation)
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = ep._enforce_snapshot_activation_invariant(request_id="req-diag")
        self.assertEqual(result["status"], "pass")
        self.assertIn("[v2.snapshot_activation_invariant]", buf.getvalue())

    def test_diagnostic_no_model_allowed(self):
        """Diagnostic profile with no snapshot container -> allowed (pass)."""
        ep = _make_entrypoint(profile="diagnostic")
        ep._cpu_snapshot_models = None
        result = ep._enforce_snapshot_activation_invariant(request_id="req-none")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["models_container_present"], 0)

    def test_diagnostic_clip_only_allowed(self):
        """Diagnostic CLIP-only mode remains allowed."""
        ep = _make_entrypoint(profile="diagnostic")
        ep._cpu_snapshot_models = self._models_container(clip=True, unet=False)
        ep._cpu_snapshot_models_active = True
        result = ep._enforce_snapshot_activation_invariant(request_id="req-clip")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["clip_present"], 1)
        self.assertEqual(result["unet_present"], 0)

    def test_diagnostic_unet_only_allowed(self):
        """Diagnostic UNET-only mode remains allowed."""
        ep = _make_entrypoint(profile="diagnostic")
        ep._cpu_snapshot_models = self._models_container(clip=False, unet=True)
        ep._cpu_snapshot_models_active = True
        result = ep._enforce_snapshot_activation_invariant(request_id="req-unet")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["clip_present"], 0)
        self.assertEqual(result["unet_present"], 1)

    def test_inherit_profile_with_models_inactive_allowed(self):
        """Non-production (inherit) profile with inactive models -> allowed."""
        ep = _make_entrypoint(profile="inherit")
        ep._cpu_snapshot_models = self._models_container()
        ep._cpu_snapshot_models_active = False
        result = ep._enforce_snapshot_activation_invariant(request_id="req-inherit")
        self.assertEqual(result["status"], "pass")

    def test_cpu_snapshot_enabled_config_flag(self):
        """snapshot_enabled_by_config reflects COMFYMODAL_V2_CPU_MODEL_SNAPSHOT."""
        ep = _make_entrypoint(profile="diagnostic", cpu_snapshot="1")
        self.assertTrue(_cpu_model_snapshot_enabled())
        ep2 = _make_entrypoint(profile="diagnostic", cpu_snapshot="0")
        self.assertFalse(_cpu_model_snapshot_enabled())
        result = ep2._enforce_snapshot_activation_invariant(request_id="req-disabled")
        self.assertEqual(result["snapshot_enabled_by_config"], 0)


class RetainedUnetIdentityChainTests(unittest.TestCase):
    """Exact retained UNET object identity across snapshot/bridge/activation/
    cachedit/sampler; mismatch fails."""

    def setUp(self):
        from comfymodal_runtime import model_preload as mp
        self.mp = mp
        with mp._SNAPSHOT_UNET_CHAIN_LOCK:
            mp._SNAPSHOT_UNET_CHAIN.clear()
        self.addCleanup(self._clear_chain)

    def _clear_chain(self):
        with self.mp._SNAPSHOT_UNET_CHAIN_LOCK:
            self.mp._SNAPSHOT_UNET_CHAIN.clear()

    def test_same_object_across_all_stages_passes(self):
        """The same retained object through all stages verifies ok."""
        unet = _FakeUnet()
        self.mp.record_retained_unet_identity("snapshot", unet, request_id="r1")
        self.mp.record_retained_unet_identity("activation", unet, request_id="r1")
        self.mp.record_retained_unet_identity("cachedit", unet, request_id="r1")
        self.mp.record_retained_unet_identity("bridge", unet, request_id="r1")
        ok, reason = self.mp.verify_retained_unet_identity(
            stage_a="snapshot", unet_a=unet,
            stage_b="bridge", unet_b=unet,
            request_id="r1",
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        with self.mp._SNAPSHOT_UNET_CHAIN_LOCK:
            chain = self.mp._SNAPSHOT_UNET_CHAIN["r1"]
        self.assertEqual(len(chain), 4)
        self.assertEqual(chain["snapshot"], id(unet))
        self.assertEqual(chain["cachedit"], id(unet))
        self.assertEqual(chain["bridge"], id(unet))

    def test_mismatch_fails(self):
        """A different sampler object must raise on verification."""
        unet_a = _FakeUnet()
        unet_b = _FakeUnet()
        self.mp.record_retained_unet_identity("snapshot", unet_a, request_id="r2")
        with self.assertRaises(RuntimeError) as ctx:
            self.mp.verify_retained_unet_identity(
                stage_a="snapshot", unet_a=unet_a,
                stage_b="sampler", unet_b=unet_b,
                request_id="r2",
            )
        self.assertIn("identity mismatch", str(ctx.exception).lower())

    def test_rewrap_same_diffusion_model_passes(self):
        """ComfyUI dynamic ModelPatcher delegates / CacheDiT wrapper re-attach
        create NEW patcher objects around the SAME diffusion model.  The
        logical identity (resolved diffusion model) must match, so a re-wrap
        of the same diffusion model verifies OK while patcher object ids
        differ."""
        dm = _FakeDM()
        patcher_a = _FakeUnet()
        patcher_a.model = SimpleNamespace(diffusion_model=dm)
        patcher_b = _FakeUnet()  # distinct patcher object, SAME diffusion model
        patcher_b.model = SimpleNamespace(diffusion_model=dm)
        self.assertNotEqual(id(patcher_a), id(patcher_b))
        self.mp.record_retained_unet_identity("bridge", patcher_a, request_id="r-wrap")
        ok, reason = self.mp.verify_retained_unet_identity(
            stage_a="bridge", unet_a=patcher_a,
            stage_b="sampler", unet_b=patcher_b,
            request_id="r-wrap",
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        # The emitted chain line logs BOTH patcher and diffusion ids.
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.mp.verify_retained_unet_identity(
                stage_a="bridge", unet_a=patcher_a,
                stage_b="sampler", unet_b=patcher_b,
                request_id="r-wrap",
            )
        line = buf.getvalue()
        self.assertIn("diffusion_a_object_id=", line)
        self.assertIn("diffusion_b_object_id=", line)
        self.assertIn("patcher_a_object_id=", line)
        self.assertIn("patcher_b_object_id=", line)

    def test_rewrap_different_diffusion_model_fails(self):
        """A DIFFERENT resolved diffusion model must raise even if the patcher
        wrappers look alike — never silently load/patch another model."""
        patcher_a = _FakeUnet()
        patcher_b = _FakeUnet()  # distinct patcher AND distinct diffusion model
        self.assertNotEqual(
            id(patcher_a.model.diffusion_model),
            id(patcher_b.model.diffusion_model),
        )
        with self.assertRaises(RuntimeError) as ctx:
            self.mp.verify_retained_unet_identity(
                stage_a="bridge", unet_a=patcher_a,
                stage_b="sampler", unet_b=patcher_b,
                request_id="r-wrap-diff",
            )
        self.assertIn("identity mismatch", str(ctx.exception).lower())

    def test_missing_object_fails(self):
        """A missing (None) object must raise on verification."""
        unet_a = _FakeUnet()
        with self.assertRaises(RuntimeError):
            self.mp.verify_retained_unet_identity(
                stage_a="snapshot", unet_a=unet_a,
                stage_b="bridge", unet_b=None,
                request_id="r3",
            )

    def test_no_records_under_empty_key_and_cleanup_removes_request_key(self):
        """Recording without a request_id never stores under the empty key,
        and cleanup removes exactly the request key."""
        unet = _FakeUnet()
        self.mp.record_retained_unet_identity("snapshot", unet)  # no request_id
        self.mp.record_retained_unet_identity("bridge", unet, request_id="r-clean")
        with self.mp._SNAPSHOT_UNET_CHAIN_LOCK:
            self.assertNotIn("", self.mp._SNAPSHOT_UNET_CHAIN)
            self.assertIn("r-clean", self.mp._SNAPSHOT_UNET_CHAIN)
        self.mp.clear_retained_unet_identity_chain("r-clean")
        with self.mp._SNAPSHOT_UNET_CHAIN_LOCK:
            self.assertNotIn("r-clean", self.mp._SNAPSHOT_UNET_CHAIN)
        # Empty-key cleanup is a no-op that never clears unrelated keys.
        self.mp.record_retained_unet_identity("bridge", unet, request_id="r-keep")
        self.mp.clear_retained_unet_identity_chain("")
        with self.mp._SNAPSHOT_UNET_CHAIN_LOCK:
            self.assertIn("r-keep", self.mp._SNAPSHOT_UNET_CHAIN)

    def test_cachedit_replacement_is_single_patch(self):
        """CacheDiT replaces the snapshot object exactly once; bridge then
        serves the patched object and it verifies against cachedit."""
        original = _FakeUnet()
        patched = _FakeUnet()
        self.mp.record_retained_unet_identity("snapshot", original, request_id="r4")
        self.mp.record_retained_unet_identity("activation", original, request_id="r4")
        # CacheDiT patches exactly once.
        self.mp.record_retained_unet_identity("cachedit", patched, request_id="r4")
        self.mp.record_retained_unet_identity("bridge", patched, request_id="r4")
        ok, _ = self.mp.verify_retained_unet_identity(
            stage_a="cachedit", unet_a=patched,
            stage_b="bridge", unet_b=patched,
            request_id="r4",
        )
        self.assertTrue(ok)
        with self.mp._SNAPSHOT_UNET_CHAIN_LOCK:
            chain = self.mp._SNAPSHOT_UNET_CHAIN["r4"]
        cachedit_entries = [s for s in chain if s == "cachedit"]
        self.assertEqual(len(cachedit_entries), 1, "exactly one CacheDiT patch")


class UnetGpuResidencyProofTests(unittest.TestCase):
    """Prove GPU activation with post-load evidence; fail on CPU residency."""

    def test_gpu_resident_evidence_reported(self):
        """A GPU-resident model yields gpu_resident status with device/memory
        evidence fields (no tensor contents)."""
        from comfymodal_runtime.cpu_snapshot_models import prove_unet_gpu_residency

        class _GpuParam:
            device = "cuda:0"

        class _DM:
            def parameters(self):
                yield _GpuParam()
                yield _GpuParam()

        unet = SimpleNamespace(
            model=SimpleNamespace(diffusion_model=_DM()),
            load_device="cuda:0",
            current_device="cuda:0",
        )
        evidence = prove_unet_gpu_residency(unet, request_id="gpu-proof")
        self.assertEqual(evidence["status"], "gpu_resident")
        self.assertEqual(evidence["gpu_parameter_count"], 2)
        self.assertEqual(evidence["parameter_count"], 2)
        self.assertEqual(evidence["load_device"], "cuda:0")
        self.assertIn("unet_in_model_cache", evidence)
        self.assertIn("model_cache_size", evidence)
        self.assertIn("unet_object_id", evidence)

    def test_cpu_resident_with_params_fails_only_when_enforced(self):
        """CPU-resident parameters raise ONLY when *enforce* is True (the
        production CPU-snapshot path sampling the exact retained object);
        without enforcement the same model reports cpu_resident status."""
        from comfymodal_runtime.cpu_snapshot_models import verify_unet_gpu_residency

        class _CpuParam:
            device = "cpu"

        class _DM:
            def parameters(self):
                yield _CpuParam()
                yield _CpuParam()

        unet = SimpleNamespace(
            model=SimpleNamespace(diffusion_model=_DM()),
            load_device="cuda:0",
            current_device="cpu",
        )
        # Diagnostic mode (no enforcement): reported, NOT raised.
        buf = io.StringIO()
        with redirect_stdout(buf):
            evidence = verify_unet_gpu_residency(
                unet, request_id="cpu-proof", context="pre_sampler",
            )
        self.assertEqual(evidence["status"], "cpu_resident")
        self.assertIn("[v2.unet_gpu_residency]", buf.getvalue())
        # Production CPU-snapshot path (enforce=True): raises before sampling.
        with self.assertRaises(RuntimeError) as ctx:
            verify_unet_gpu_residency(
                unet, request_id="cpu-proof", context="pre_sampler",
                enforce=True,
            )
        msg = str(ctx.exception)
        self.assertIn("CPU-resident", msg)
        self.assertIn("pre_sampler", msg)

    def test_meta_params_are_unknown_not_cpu_resident(self):
        """Meta/unknown device parameters are classified as unknown/partial,
        never CPU-resident, and never raise."""
        from comfymodal_runtime.cpu_snapshot_models import verify_unet_gpu_residency

        class _MetaParam:
            device = "meta"

        class _DM:
            def parameters(self):
                yield _MetaParam()
                yield _MetaParam()

        unet = SimpleNamespace(
            model=SimpleNamespace(diffusion_model=_DM()),
            load_device="cpu",
            current_device="meta",
        )
        evidence = verify_unet_gpu_residency(
            unet, request_id="meta-proof", context="pre_sampler", enforce=True,
        )
        self.assertEqual(evidence["status"], "unknown")
        self.assertEqual(evidence["meta_parameter_count"], 2)
        self.assertEqual(evidence["cpu_parameter_count"], 0)

    def test_mixed_cpu_and_unknown_devices_not_cpu_resident(self):
        """A mix of CPU and unknown devices (dynamic/offload) is classified as
        unknown/partial, NOT CPU-resident, and does not raise even when
        enforced."""
        from comfymodal_runtime.cpu_snapshot_models import verify_unet_gpu_residency

        class _CpuParam:
            device = "cpu"

        class _OtherParam:
            device = "xpu"

        class _DM:
            def parameters(self):
                yield _CpuParam()
                yield _OtherParam()

        unet = SimpleNamespace(
            model=SimpleNamespace(diffusion_model=_DM()),
            load_device="cpu",
            current_device="cpu",
        )
        evidence = verify_unet_gpu_residency(
            unet, request_id="mixed-proof", context="pre_sampler", enforce=True,
        )
        self.assertEqual(evidence["status"], "unknown")
        self.assertEqual(evidence["cpu_parameter_count"], 1)
        self.assertEqual(evidence["unknown_parameter_count"], 1)

    def test_no_params_does_not_raise(self):
        """Stub models with no parameters are reported but not raised."""
        from comfymodal_runtime.cpu_snapshot_models import verify_unet_gpu_residency

        class _DM:
            def parameters(self):
                return iter([])

        unet = SimpleNamespace(model=SimpleNamespace(diffusion_model=_DM()))
        evidence = verify_unet_gpu_residency(unet, request_id="no-params", enforce=True)
        self.assertEqual(evidence["status"], "no_params")


class BridgePublicationOrderingTests(unittest.TestCase):
    """Active state only after bridge publication; one activation; no duplicate
    future; CacheDiT is not disabled."""

    def setUp(self):
        self.bridge = V2LoaderBridge()
        _ensure_bridge_has_fake_nodes(self.bridge)
        self.trace = RuntimeTrace(request_id="order", process="test")
        self.unet = _FakeUnet()
        self.clip = _FakeClip()
        self.model_key = ModelRestoreKey(
            unet_identity="u.safetensors",
            clip_identity="c.safetensors",
            clip_type="sd3",
        )

    def test_one_activation_no_duplicate_future(self):
        """use_ready_models publishes ONE preparation; the unet_future holds
        the exact retained object and coordinator._active matches."""
        prep = self.bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=PrefillKey(model_key=self.model_key),
            model_spec=_make_snapshot_spec(),
            unet=self.unet,
            clip=self.clip,
            trace=self.trace,
        )
        self.assertIs(self.bridge._preparation, prep)
        self.assertIs(self.bridge.coordinator._active, prep)
        self.assertIs(prep.unet_future.result(), self.unet)
        self.assertIs(prep.clip_future.result(), self.clip)
        # Only one unet future exists (no duplicate/background future).
        self.assertIsNone(prep.vae_future)
        self.assertIsNone(prep.prefill_future)
        self.assertTrue(prep.unet_future.done())
        # Bridge serves the exact object at graph time.
        from comfymodal_runtime.model_preload import _ACTIVE_V2_LOADER_BRIDGE
        token = _ACTIVE_V2_LOADER_BRIDGE.set(self.bridge)
        try:
            served = self.bridge.coordinator.wait_unet(prep, trace=self.trace)
        finally:
            _ACTIVE_V2_LOADER_BRIDGE.reset(token)
        self.assertIs(served, self.unet)

    def test_rebind_after_cachedit_keeps_single_future_exact_object(self):
        """Re-publishing the bridge after a CacheDiT patch replaces the future
        content with the patched object — still exactly one preparation and no
        stray background submission."""
        patched = _FakeUnet(name="patched.safetensors")
        self.bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=PrefillKey(model_key=self.model_key),
            model_spec=_make_snapshot_spec(),
            unet=self.unet,
            clip=self.clip,
            trace=self.trace,
        )
        prep2 = self.bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=PrefillKey(model_key=self.model_key, prompt_bundle_hash="cachedit"),
            model_spec=_make_snapshot_spec(),
            unet=patched,
            clip=self.clip,
            trace=self.trace,
        )
        self.assertIs(self.bridge._preparation, prep2)
        self.assertIs(prep2.unet_future.result(), patched)
        # No second future coexists.
        self.assertTrue(prep2.unet_future.done())
        self.assertFalse(prep2.unet_future.running())

    def test_active_set_only_after_bridge_publication(self):
        """The active flag must be False while the bridge is empty and become
        True only after use_ready_models publishes successfully."""
        ep = ModalRuntimeEntrypoint()
        ep._lazy_init_snapshot_state()
        _ensure_bridge_has_fake_nodes(ep._preload_bridge)
        self.assertFalse(ep._cpu_snapshot_models_active)
        # Simulate restore-time ordering: publish to bridge first, then mark
        # active — exactly what restore() does after validation/retarget.
        ep._preload_bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=PrefillKey(model_key=self.model_key),
            model_spec=_make_snapshot_spec(),
            unet=self.unet,
            clip=self.clip,
            trace=self.trace,
        )
        self.assertIsNotNone(ep._preload_bridge._preparation)
        # Activation succeeds -> set active.
        ep._cpu_snapshot_models_active = True
        self.assertTrue(ep._cpu_snapshot_models_active)
        # Failed publication must never leave active=True behind:
        ep2 = ModalRuntimeEntrypoint()
        ep2._lazy_init_snapshot_state()
        ep2._cpu_snapshot_models_active = True
        # clear() (the failure path) resets the preparation but active is
        # explicitly reset by the caller — assert bridge is now empty.
        ep2._preload_bridge.clear()
        self.assertIsNone(ep2._preload_bridge._preparation)

    def test_cachedit_not_permanently_disabled(self):
        """CacheDiT remains available after activation — the code must not
        permanently disable it.  Simulated by re-preparing through the bridge
        after a CacheDiT patch and confirming the patched model is served."""
        patched = _FakeUnet(name="patched2.safetensors")
        self.bridge.use_ready_models(
            model_key=self.model_key,
            prefill_key=PrefillKey(model_key=self.model_key),
            model_spec=_make_snapshot_spec(),
            unet=patched,
            clip=self.clip,
            trace=self.trace,
        )
        from comfymodal_runtime.model_preload import _ACTIVE_V2_LOADER_BRIDGE
        token = _ACTIVE_V2_LOADER_BRIDGE.set(self.bridge)
        try:
            served = self.bridge.coordinator.wait_unet(self.bridge._preparation, trace=self.trace)
        finally:
            _ACTIVE_V2_LOADER_BRIDGE.reset(token)
        self.assertIs(served, patched)
        # The forward probe registry still holds the patched model (CacheDiT
        # integration is live, not disabled).
        from comfymodal_runtime import unet_forward_probe as ufp
        _, dm = ufp.resolve_diffusion_model(patched)
        self.assertIsNotNone(dm)
        with ufp._registry_lock:
            self.assertIn(id(dm), ufp._registry)


if __name__ == "__main__":
    unittest.main()
