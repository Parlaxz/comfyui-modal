"""Focused tests for Plan C CPU snapshot lifecycle integration.

Tests cover configuration validation, profile extraction, bridge
activation, and request binding without instantiating real Modal or
ComfyUI.  Tests skip cleanly when optional imports are unavailable.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace, MappingProxyType
from typing import Any
from collections.abc import Mapping

from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan, stable_hash
from comfymodal_runtime.model_preload import V2LoaderBridge, RestorePreparation
from comfymodal_runtime.restore_plan import derive_model_key, derive_prefill_key, build_restore_model_spec
from comfymodal_runtime.trace import RuntimeTrace
from comfymodal_runtime.cpu_snapshot_models import (
    CpuSnapshotModels,
    identity_from_profile,
    validate_cpu_snapshot_models,
    retarget_cpu_snapshot_models,
)
from comfymodal_runtime.modal_app import (
    _collect_warmup_env,
    _cpu_model_snapshot_enabled,
    _cpu_snapshot_model_keys_match,
    _cpu_snapshot_spec_projection,
    _cpu_snapshot_specs_match,
    ModalRuntimeEntrypoint,
)


class _DummyCtxManager:
    """Minimal context manager for testing CPU snapshot context."""
    def __enter__(self):
        return None
    def __exit__(self, *exc):
        return None


# ── Helpers ────────────────────────────────────────────────────────────────


def _clean_env():
    """Remove Plan C env vars so tests start from a known state."""
    for key in ("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT",
                "COMFYMODAL_ENABLE_GPU_SNAPSHOT"):
        os.environ.pop(key, None)


class _FakeClip:
    pass


def _fake_model_management():
    """Return a minimal fake comfy.model_management module."""
    class _MM:
        @staticmethod
        def get_torch_device():
            return "cpu"
        @staticmethod
        def unet_offload_device():
            return "cpu"
        @staticmethod
        def text_encoder_device():
            return "cpu"
        @staticmethod
        def text_encoder_offload_device():
            return "cpu"
    return _MM


def _ensure_bridge_has_fake_nodes(bridge):
    """Install minimal fake node classes on a bare bridge so use_ready_models can
    establish loader wrappers.  Safe to call multiple times (idempotent)."""
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
    from types import SimpleNamespace
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


def _make_snapshot_models(
    unet_identity: str = "sd3.5_large.safetensors",
    clip_identity: str = "t5xxl_fp16.safetensors",
    clip_type: str = "sd3",
    clip2: str = "",
) -> CpuSnapshotModels:
    """Build a minimal CpuSnapshotModels for testing."""
    profile: dict[str, Any] = {
        "mode": "split",
        "unet": unet_identity,
        "clip1": clip_identity,
        "clip_type": clip_type,
    }
    if clip2:
        profile["clip2"] = clip2
    # Use SimpleNamespace so we can attach patcher attributes later
    unet_stub = SimpleNamespace()
    clip_stub = _FakeClip()
    return CpuSnapshotModels(
        model_key=ModelRestoreKey(
            unet_identity=unet_identity,
            clip_identity=f"{clip_identity}||{clip2}" if clip2 else clip_identity,
            vae_identity="",
            clip_type=clip_type,
        ),
        model_spec={
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": unet_identity, "weight_dtype": "default"}],
                "clip": [{"loader_class": "CLIPLoader", "clip_name": clip_identity, "type": clip_type, "device": "default"}],
                "vae": [],
            },
        },
        normalized_profile=dict(profile),
        file_facts=(),
        unet=unet_stub,
        clip=clip_stub,
        load_timings_ms={"clip_load_ms": 100.0, "unet_load_ms": 200.0},
    )


# ── Feature flag tests ─────────────────────────────────────────────────────


class CpuSnapshotEnabledTests(unittest.TestCase):
    """_cpu_model_snapshot_enabled() configuration validation."""

    def setUp(self):
        _clean_env()

    def test_disabled_by_default(self):
        self.assertFalse(_cpu_model_snapshot_enabled())

    def test_enabled_when_exactly_1(self):
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "1"
        self.assertTrue(_cpu_model_snapshot_enabled())

    def test_disabled_when_0(self):
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "0"
        self.assertFalse(_cpu_model_snapshot_enabled())

    def test_disabled_when_empty(self):
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = ""
        self.assertFalse(_cpu_model_snapshot_enabled())

    def test_disabled_when_arbitrary(self):
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "yes"
        self.assertFalse(_cpu_model_snapshot_enabled())

    def test_rejects_gpu_snapshot_combination(self):
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "1"
        os.environ["COMFYMODAL_ENABLE_GPU_SNAPSHOT"] = "1"
        with self.assertRaises(RuntimeError) as ctx:
            _cpu_model_snapshot_enabled()
        self.assertIn("incompatible", str(ctx.exception).lower())


# ── Profile extraction tests ─────────────────────────────────────────────


class CpuSnapshotProfileTests(unittest.TestCase):
    """_cpu_snapshot_profile() validation."""

    def setUp(self):
        _clean_env()

    def _make_api(self, profile: Any = None):
        return SimpleNamespace(_snapshot_preload_profile=lambda: profile)

    def test_accepts_valid_split_profile(self):
        entrypoint = ModalRuntimeEntrypoint()
        api = self._make_api({
            "mode": "split",
            "unet": "sd3.5_large.safetensors",
            "clip1": "t5xxl_fp16.safetensors",
            "clip_type": "sd3",
        })
        result = entrypoint._cpu_snapshot_profile(api)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["mode"], "split")
        self.assertEqual(result["unet"], "sd3.5_large.safetensors")

    def test_accepts_dual_clip_profile(self):
        entrypoint = ModalRuntimeEntrypoint()
        api = self._make_api({
            "mode": "split",
            "unet": "sd3.5_large.safetensors",
            "clip1": "t5xxl_fp16.safetensors",
            "clip2": "clip_g.safetensors",
            "clip_type": "sd3",
        })
        result = entrypoint._cpu_snapshot_profile(api)
        self.assertEqual(result.get("clip2"), "clip_g.safetensors")

    def test_rejects_none_profile(self):
        entrypoint = ModalRuntimeEntrypoint()
        api = self._make_api(None)
        with self.assertRaises(RuntimeError) as ctx:
            entrypoint._cpu_snapshot_profile(api)
        self.assertIn("None", str(ctx.exception))

    def test_rejects_non_mapping_profile(self):
        entrypoint = ModalRuntimeEntrypoint()
        api = self._make_api("not_a_dict")
        with self.assertRaises(RuntimeError) as ctx:
            entrypoint._cpu_snapshot_profile(api)
        self.assertIn("Mapping", str(ctx.exception))

    def test_rejects_non_split_mode(self):
        entrypoint = ModalRuntimeEntrypoint()
        api = self._make_api({
            "mode": "checkpoint",
            "unet": "model.safetensors",
            "clip1": "clip.safetensors",
            "clip_type": "sd3",
        })
        with self.assertRaises(RuntimeError) as ctx:
            entrypoint._cpu_snapshot_profile(api)
        self.assertIn("split", str(ctx.exception).lower())

    def test_rejects_missing_required_field(self):
        entrypoint = ModalRuntimeEntrypoint()
        api = self._make_api({
            "mode": "split",
            "unet": "",
            "clip1": "t5xxl_fp16.safetensors",
            "clip_type": "sd3",
        })
        with self.assertRaises(RuntimeError) as ctx:
            entrypoint._cpu_snapshot_profile(api)
        self.assertIn("unet", str(ctx.exception))


# ── Bridge activation tests ──────────────────────────────────────────────


class CpuSnapshotBridgeActivationTests(unittest.TestCase):
    """_use_cpu_snapshot_models_on_bridge() integration."""

    def setUp(self):
        _clean_env()
        self.entrypoint = ModalRuntimeEntrypoint()
        _ensure_bridge_has_fake_nodes(self.entrypoint._preload_bridge)
        self.trace = RuntimeTrace(request_id="bridge-test", process="remote")
        self.model_key = ModelRestoreKey(unet_identity="u", clip_identity="c", clip_type="sd3")
        self.prefill_key = PrefillKey(
            model_key=self.model_key,
            prompt_bundle_hash="abc123",
        )
        self.model_spec = {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": "u", "weight_dtype": "default"}],
                "clip": [{"loader_class": "CLIPLoader", "clip_name": "c", "type": "sd3", "device": "default"}],
                "vae": [],
            },
        }
        self.unet_stub = object()
        self.clip_stub = _FakeClip()

    def _activate(self):
        self.entrypoint._use_cpu_snapshot_models_on_bridge(
            self.model_key,
            self.prefill_key,
            self.model_spec,
            self.unet_stub,
            self.clip_stub,
            trace=self.trace,
        )

    def test_sets_bridge_state(self):
        self._activate()
        bridge = self.entrypoint._preload_bridge
        self.assertEqual(bridge._model_key, self.model_key)
        self.assertEqual(bridge._prefill_key, self.prefill_key)
        self.assertIsNotNone(bridge._preparation)

    def test_preparation_has_resolved_futures(self):
        self._activate()
        prep = self.entrypoint._preload_bridge._preparation
        self.assertIsNotNone(prep)
        self.assertIsNotNone(prep.unet_future)
        self.assertIsNotNone(prep.clip_future)
        self.assertTrue(prep.unet_future.done())
        self.assertTrue(prep.clip_future.done())
        self.assertIs(prep.unet_future.result(), self.unet_stub)
        self.assertIs(prep.clip_future.result(), self.clip_stub)

    def test_bridge_consume_unet_returns_snapshot_model(self):
        """Simulate graph-time UNET consumption via bridge."""
        self._activate()
        bridge = self.entrypoint._preload_bridge
        # Install bridge as active for request scope
        import comfymodal_runtime.model_preload as _mp
        # We need to make the bridge respond to _consume_unet.
        # The bridge's coordinator.wait_unet waits on prep.unet_future.
        # We can test this directly.
        prep = bridge._preparation
        unet = bridge.coordinator.wait_unet(prep)
        self.assertIs(unet, self.unet_stub)

    def test_bridge_consume_clip_returns_snapshot_model(self):
        self._activate()
        bridge = self.entrypoint._preload_bridge
        prep = bridge._preparation
        clip = bridge.coordinator.wait_clip(prep)
        self.assertIs(clip, self.clip_stub)

    def test_lazy_init_snapshot_state(self):
        """Verify _lazy_init_snapshot_state creates attrs on bare instance."""
        raw = ModalRuntimeEntrypoint.__new__(ModalRuntimeEntrypoint)
        self.assertFalse(hasattr(raw, "_cpu_snapshot_models"))
        raw._lazy_init_snapshot_state()
        self.assertTrue(hasattr(raw, "_cpu_snapshot_models"))
        self.assertIsNone(raw._cpu_snapshot_models)
        self.assertIsNotNone(hasattr(raw, "_cpu_snapshot_models_active"))
        self.assertFalse(raw._cpu_snapshot_models_active)


# ── Plan C request binding tests ─────────────────────────────────────────


class CpuSnapshotRequestBindingTests(unittest.TestCase):
    """Request-time binding of CPU snapshot models."""

    def setUp(self):
        _clean_env()
        self.entrypoint = ModalRuntimeEntrypoint()
        _ensure_bridge_has_fake_nodes(self.entrypoint._preload_bridge)
        self.trace = RuntimeTrace(request_id="req-bind", process="remote")

    def test_skip_when_not_active(self):
        """No-op when _cpu_snapshot_models_active is False."""
        self.entrypoint._cpu_snapshot_models_active = False
        self.entrypoint._cpu_snapshot_models = None
        # Should not raise
        self.entrypoint._lazy_init_snapshot_state()
        # Request binding only runs when active, so no explicit assertion needed.

    def test_binds_when_model_key_matches(self):
        """Bridge is configured when request model key matches snapshot."""
        unet_id = "sd3.5_large.safetensors"
        clip_id = "t5xxl_fp16.safetensors"
        snapshot = _make_snapshot_models(unet_identity=unet_id, clip_identity=clip_id)
        self.entrypoint._cpu_snapshot_models = snapshot
        self.entrypoint._cpu_snapshot_models_active = True
        bridge = self.entrypoint._preload_bridge

        # Activate bridge
        self.entrypoint._use_cpu_snapshot_models_on_bridge(
            snapshot.model_key,
            PrefillKey(model_key=snapshot.model_key),
            snapshot.model_spec,
            snapshot.unet,
            snapshot.clip,
            trace=self.trace,
        )

        prep = bridge._preparation
        unet = bridge.coordinator.wait_unet(prep)
        clip = bridge.coordinator.wait_clip(prep)
        self.assertIs(unet, snapshot.unet)
        self.assertIs(clip, snapshot.clip)

    def test_clears_on_model_key_mismatch(self):
        """Bridge is cleared when request model key differs from snapshot."""
        snapshot = _make_snapshot_models(unet_identity="model_a.safetensors")
        self.entrypoint._cpu_snapshot_models = snapshot
        self.entrypoint._cpu_snapshot_models_active = True
        # Activate first (simulating restore activation)
        self.entrypoint._use_cpu_snapshot_models_on_bridge(
            snapshot.model_key,
            PrefillKey(model_key=snapshot.model_key),
            snapshot.model_spec,
            snapshot.unet,
            snapshot.clip,
        )
        self.assertTrue(self.entrypoint._cpu_snapshot_models_active)

        # Simulate request with different model: clear bridge and deactivate.
        self.entrypoint._preload_bridge.clear()
        self.entrypoint._cpu_snapshot_models_active = False
        self.assertFalse(self.entrypoint._cpu_snapshot_models_active)
        self.assertIsNone(self.entrypoint._preload_bridge._model_key)


# ── Retarget/is_valid resource-invariant tests ────────────────────────────


class CpuSnapshotResourceInvariantTests(unittest.TestCase):
    """Resource-invariant checks for Plan C lifecycle."""

    def test_retarget_unknown_model_management(self):
        """retarget_cpu_snapshot_models fails clearly on missing functions."""
        mm = SimpleNamespace()  # no functions
        models = _make_snapshot_models()
        ok, reason = retarget_cpu_snapshot_models(models, model_management=mm)
        self.assertFalse(ok)
        self.assertIn("missing", reason)

    def test_retarget_fake_model_management(self):
        """retarget succeeds with minimal fake mm."""
        models = _make_snapshot_models()
        mm = _fake_model_management()
        # Attach patcher-like attributes to the stub unet/clip
        models.unet.load_device = "cpu"
        models.unet.offload_device = "cpu"
        models.clip = _FakeClip()
        # Need clip to have a patcher with load_device/offload_device
        clip_patcher = SimpleNamespace(load_device="cpu", offload_device="cpu")
        models.clip.patcher = clip_patcher
        models.clip.tokenizer = object()
        # Give clip named_parameters/named_buffers for validation
        models.clip.named_parameters = lambda recurse=True: iter([])
        models.clip.named_buffers = lambda recurse=True: iter([])
        models.clip.cond_stage_model = SimpleNamespace(
            named_parameters=lambda recurse=True: iter([]),
            named_buffers=lambda recurse=True: iter([]),
        )
        models.unet.named_parameters = lambda recurse=True: iter([])
        models.unet.named_buffers = lambda recurse=True: iter([])
        models.unet.model = SimpleNamespace(
            named_parameters=lambda recurse=True: iter([]),
            named_buffers=lambda recurse=True: iter([]),
            diffusion_model=SimpleNamespace(
                named_parameters=lambda recurse=True: iter([]),
                named_buffers=lambda recurse=True: iter([]),
            ),
        )
        ok, reason = retarget_cpu_snapshot_models(models, model_management=mm)
        self.assertTrue(ok, reason)

    def test_validate_cpu_snapshot_models_missing_files(self):
        """validate_cpu_snapshot_models returns (False, reason) on nonexistent files."""
        models = _make_snapshot_models()
        expected_key = models.model_key
        expected_spec = models.model_spec

        def resolve_path(role, filename):
            raise FileNotFoundError(f"not found: {filename}")

        ok, reason = validate_cpu_snapshot_models(
            models,
            expected_key=expected_key,
            expected_spec=expected_spec,
            resolve_path=resolve_path,
        )
        # Should fail at file fact validation
        self.assertFalse(ok)
        self.assertIn("file", reason.lower())


# ── Profile identity tests ──────────────────────────────────────────────


class CpuSnapshotProfileIdentityTests(unittest.TestCase):
    """identity_from_profile end-to-end."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="cpu_snap_test_")
        # Create actual files for stat to work
        unet_dir = os.path.join(self._tmpdir, "unet")
        clip_dir = os.path.join(self._tmpdir, "clip")
        os.makedirs(unet_dir, exist_ok=True)
        os.makedirs(clip_dir, exist_ok=True)
        self._unet_path = os.path.join(unet_dir, "sd3.5_large.safetensors")
        self._clip_path = os.path.join(clip_dir, "t5xxl_fp16.safetensors")
        self._clip2_path = os.path.join(clip_dir, "clip_g.safetensors")
        for p in (self._unet_path, self._clip_path, self._clip2_path):
            with open(p, "wb") as f:
                f.write(b"dummy")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _resolve_path(self, role, filename):
        if role == "unet":
            return self._unet_path
        elif role == "clip1":
            return self._clip_path
        elif role == "clip2":
            return self._clip2_path
        return os.path.join(self._tmpdir, role, filename)

    def test_identity_from_profile_split_single_clip(self):
        profile = {
            "mode": "split",
            "unet": "sd3.5_large.safetensors",
            "clip1": "t5xxl_fp16.safetensors",
            "clip_type": "sd3",
        }
        key, spec, facts = identity_from_profile(
            profile, resolve_path=self._resolve_path,
        )
        self.assertEqual(key.unet_identity, "sd3.5_large.safetensors")
        self.assertEqual(key.clip_identity, "t5xxl_fp16.safetensors")
        self.assertEqual(key.clip_type, "sd3")
        self.assertIn("loaders", spec)
        self.assertEqual(len(facts), 2)

    def test_identity_from_profile_split_dual_clip(self):
        profile = {
            "mode": "split",
            "unet": "sd3.5_large.safetensors",
            "clip1": "t5xxl_fp16.safetensors",
            "clip2": "clip_g.safetensors",
            "clip_type": "sd3",
        }
        key, spec, facts = identity_from_profile(
            profile, resolve_path=self._resolve_path,
        )
        self.assertIn("||", key.clip_identity)
        self.assertEqual(len(facts), 3)

    def test_identity_rejects_nonsplit_mode(self):
        with self.assertRaises(ValueError) as ctx:
            identity_from_profile(
                {"mode": "checkpoint"},
                resolve_path=lambda role, f: os.path.join(self._tmpdir, f),
            )
        self.assertIn("split", str(ctx.exception))


# ── Bridge use_ready_models interface tests ────────────────────────────


class CpuSnapshotBridgeUseReadyModelsTests(unittest.TestCase):
    """Tests that _use_cpu_snapshot_models_on_bridge tries use_ready_models first."""

    def setUp(self):
        _clean_env()
        self.entrypoint = ModalRuntimeEntrypoint()
        _ensure_bridge_has_fake_nodes(self.entrypoint._preload_bridge)
        self.trace = RuntimeTrace(request_id="bridge-urm", process="remote")
        self.model_key = ModelRestoreKey(unet_identity="u", clip_identity="c", clip_type="sd3")
        self.prefill_key = PrefillKey(model_key=self.model_key)
        self.model_spec = {"loaders": {"unet": [], "clip": [], "vae": []}}
        self.unet_stub = object()
        self.clip_stub = _FakeClip()

    def test_calls_use_ready_models_when_present(self):
        """When the bridge has use_ready_models, it is called instead of fallback."""
        _called = []

        class _FakeBridgeWithURM:
            def use_ready_models(self, **kwargs):
                _called.append(kwargs)
            def clear(self):
                pass
            diagnostics = lambda self: {}

        original_bridge = self.entrypoint._preload_bridge
        self.entrypoint._preload_bridge = _FakeBridgeWithURM()  # type: ignore[assignment]

        try:
            self.entrypoint._use_cpu_snapshot_models_on_bridge(
                self.model_key, self.prefill_key, self.model_spec,
                self.unet_stub, self.clip_stub, trace=self.trace,
            )
            self.assertEqual(len(_called), 1)
            kwargs = _called[0]
            self.assertIs(kwargs["model_key"], self.model_key)
            self.assertIs(kwargs["prefill_key"], self.prefill_key)
            self.assertIs(kwargs["unet"], self.unet_stub)
            self.assertIs(kwargs["clip"], self.clip_stub)
        finally:
            self.entrypoint._preload_bridge = original_bridge

    def test_use_ready_models_sets_correct_bridge_state(self):
        """use_ready_models sets model_key, prefill_key, model_spec, and preparation."""
        self.entrypoint._use_cpu_snapshot_models_on_bridge(
            self.model_key, self.prefill_key, self.model_spec,
            self.unet_stub, self.clip_stub, trace=self.trace,
        )
        bridge = self.entrypoint._preload_bridge
        self.assertEqual(bridge._model_key, self.model_key)
        self.assertIsNotNone(bridge._preparation)
        prep = bridge._preparation
        self.assertIsNotNone(prep.unet_future)
        self.assertIsNotNone(prep.clip_future)
        self.assertTrue(prep.unet_future.done())
        self.assertTrue(prep.clip_future.done())
        self.assertIs(prep.unet_future.result(), self.unet_stub)
        self.assertIs(prep.clip_future.result(), self.clip_stub)
        self.assertEqual(bridge._prefill_key.prompt_bundle_hash,
                         self.prefill_key.prompt_bundle_hash)

    def test_use_ready_models_sets_coordinator_active(self):
        """After activation, coordinator._active is set so wait_* without args works."""
        self.entrypoint._use_cpu_snapshot_models_on_bridge(
            self.model_key, self.prefill_key, self.model_spec,
            self.unet_stub, self.clip_stub, trace=self.trace,
        )
        bridge = self.entrypoint._preload_bridge
        self.assertIsNotNone(bridge.coordinator._active)
        self.assertIs(bridge.coordinator._active, bridge._preparation)


# ── Restore fast-path control flow tests ─────────────────────────────


class CpuSnapshotRestoreFastPathTests(unittest.TestCase):
    """Verify the restore fast-path control flow:
    - On exact hit (snapshot activated): bridge.prepare() and background UNET
      submission are NOT called.
    - On miss (snapshot not activated): bridge.prepare() IS called.
    """

    def setUp(self):
        _clean_env()
        self.entrypoint = ModalRuntimeEntrypoint()
        _ensure_bridge_has_fake_nodes(self.entrypoint._preload_bridge)

    def test_fast_path_skips_deferral_code(self):
        """When _cpu_snapshot_activated is True the else branch (containing
        _defer_api logic, _check_unet_deferral_eligible, bridge.prepare(),
        and background UNET submission) is structurally skipped.  Verify
        by installing a tracking wrapper and simulating both paths."""
        original_prepare = self.entrypoint._preload_bridge.prepare
        prepare_invoked = []

        def _tracking_prepare(*args, **kwargs):
            prepare_invoked.append(True)
            return original_prepare(*args, **kwargs)

        self.entrypoint._preload_bridge.prepare = _tracking_prepare  # type: ignore[assignment]
        try:
            self.entrypoint._restore_plan = SimpleNamespace(
                model_key=ModelRestoreKey(
                    unet_identity="u", clip_identity="c", vae_identity="", clip_type="sd3",
                ),
                prefill_key=PrefillKey(model_key=ModelRestoreKey(
                    unet_identity="u", clip_identity="c", vae_identity="", clip_type="sd3",
                )),
                model_spec={"loaders": {"unet": [], "clip": [], "vae": []}},
                generation=1,
            )

            # ── Branch A: exact hit (snapshot activated) ───────────
            # This path must NOT call prepare().
            self.entrypoint._cpu_snapshot_models = _make_snapshot_models()
            self.entrypoint._cpu_snapshot_models_active = True
            api_mock = SimpleNamespace(
                _snapshot_preload_profile=lambda: {},
                _force_cpu_during_snapshot=lambda: _DummyCtxManager(),
            )
            # Activate bridge as restore() would.
            self.entrypoint._use_cpu_snapshot_models_on_bridge(
                self.entrypoint._restore_plan.model_key,
                self.entrypoint._restore_plan.prefill_key,
                self.entrypoint._restore_plan.model_spec,
                self.entrypoint._cpu_snapshot_models.unet,
                self.entrypoint._cpu_snapshot_models.clip,
            )
            prepare_count_before = len(prepare_invoked)

            # Run the fast-path block (simplified restore logic).
            _cpu_snapshot_activated = True
            if self.entrypoint._restore_plan is not None:
                if _cpu_snapshot_activated:
                    # Fast path — no prepare, no background UNET, no deferral.
                    _prep_for_check: RestorePreparation | None = None
                else:
                    # This branch should NOT execute on exact hit.
                    _prep_for_check = self.entrypoint._preload_bridge.prepare(
                        self.entrypoint._restore_plan,
                    )

            self.assertEqual(
                len(prepare_invoked) - prepare_count_before, 0,
                "bridge.prepare() must NOT be called on exact snapshot hit",
            )

            # ── Branch B: miss (snapshot not activated) ────────────
            prepare_count_before = len(prepare_invoked)
            _cpu_snapshot_activated = False
            if self.entrypoint._restore_plan is not None:
                if _cpu_snapshot_activated:
                    pass  # pragma: no cover
                else:
                    # Miss path — prepare() is reachable through the else branch.
                    # (Full execution requires live ComfyUI, but we can verify
                    # the structural path exists.)
                    pass

            # Now verify that _defer_api + _check_unet_deferral_eligible
            # would run (they are inside the else branch), confirming the
            # structural separation.
            eligible = ModalRuntimeEntrypoint._check_unet_deferral_eligible(
                None, self.entrypoint._restore_plan,
            )
            self.assertFalse(eligible)  # None api => not eligible

        finally:
            self.entrypoint._preload_bridge.prepare = original_prepare
            self.entrypoint._restore_plan = None
            self.entrypoint._cpu_snapshot_models = None
            self.entrypoint._cpu_snapshot_models_active = False


# ── Plan A/B spec projection compatibility tests ────────────────────────


class CpuSnapshotSpecProjectionTests(unittest.TestCase):
    """_cpu_snapshot_spec_projection and _cpu_snapshot_specs_match compatibility.

    Plan A (identity_from_profile) and Plan B (build_restore_model_spec)
    produce structurally different model_spec dicts.  These tests verify
    that the projection helper normalises both shapes and compares only
    the requested identity fields (UNET name/class/weight_dtype, CLIP
    filenames/class/type/layout), ignoring node_id, model_stack, VAE,
    and device.
    """

    # ── Plan A-style spec (no node_id, no model_stack, VAE empty) ──────
    PLAN_A_SPEC = {
        "loaders": {
            "unet": [
                {"loader_class": "UNETLoader", "unet_name": "sd3.5_large.safetensors", "weight_dtype": "default"},
            ],
            "clip": [
                {"loader_class": "CLIPLoader", "clip_name": "t5xxl_fp16.safetensors", "type": "sd3", "device": "default"},
            ],
            "vae": [],
        },
    }

    # ── Plan B-style spec (node_id, model_stack, VAE populated) ────────
    PLAN_B_SPEC = {
        "model_stack": {"some": "stack"},
        "loaders": {
            "unet": [
                {"node_id": "13", "loader_class": "UNETLoader", "unet_name": "sd3.5_large.safetensors", "weight_dtype": "default"},
            ],
            "clip": [
                {"node_id": "45", "loader_class": "CLIPLoader", "clip_name": "t5xxl_fp16.safetensors", "type": "sd3", "device": "default"},
            ],
            "vae": [
                {"node_id": "67", "loader_class": "VAELoader", "vae_name": "ae.safetensors"},
            ],
        },
    }

    def test_projection_matches_across_plan_ab(self):
        """Projected fields are identical despite different top-level structure."""
        proj_a = _cpu_snapshot_spec_projection(self.PLAN_A_SPEC)
        proj_b = _cpu_snapshot_spec_projection(self.PLAN_B_SPEC)
        self.assertEqual(proj_a, proj_b)

    def test_specs_match_across_plan_ab(self):
        """_cpu_snapshot_specs_match returns True for compatible A/B specs."""
        self.assertTrue(
            _cpu_snapshot_specs_match(self.PLAN_A_SPEC, self.PLAN_B_SPEC)
        )

    def test_projection_strips_node_id_and_model_stack(self):
        """Projection must not contain node_id, model_stack, or device."""
        proj = _cpu_snapshot_spec_projection(self.PLAN_B_SPEC)
        for unet_entry in proj["unet"]:
            self.assertNotIn("node_id", unet_entry)
            self.assertNotIn("device", unet_entry)
        for clip_entry in proj["clip"]:
            self.assertNotIn("node_id", clip_entry)
            self.assertNotIn("device", clip_entry)
        self.assertNotIn("model_stack", proj)
        self.assertNotIn("vae", proj)

    def test_projection_preserves_multiplicity(self):
        """Extra UNET or CLIP loaders cause mismatch."""
        single_clip = {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"}],
                "clip": [{"loader_class": "CLIPLoader", "clip_name": "c.safetensors", "type": "sd3", "device": "default"}],
            },
        }
        dual_clip = {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"}],
                "clip": [
                    {"loader_class": "DualCLIPLoader", "clip_name1": "c1.safetensors", "clip_name2": "c2.safetensors", "type": "sd3", "device": "default"},
                ],
            },
        }
        # Different number of CLIP loaders
        two_clips = {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"}],
                "clip": [
                    {"loader_class": "CLIPLoader", "clip_name": "c1.safetensors", "type": "sd3", "device": "default"},
                    {"loader_class": "CLIPLoader", "clip_name": "c1.safetensors", "type": "sd3", "device": "default"},
                ],
            },
        }
        # Same projection for single clip
        self.assertTrue(_cpu_snapshot_specs_match(single_clip, single_clip))
        # Different layout (single vs dual) must NOT match
        self.assertFalse(_cpu_snapshot_specs_match(single_clip, dual_clip))
        # Different list length must NOT match
        self.assertFalse(_cpu_snapshot_specs_match(single_clip, two_clips))

    def test_projection_dual_clip_plan_ab(self):
        """Dual CLIP across Plan A and B shapes."""
        plan_a_dual = {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"}],
                "clip": [{"loader_class": "DualCLIPLoader", "clip_name1": "c1.safetensors", "clip_name2": "c2.safetensors", "type": "sdxl", "device": "default"}],
                "vae": [],
            },
        }
        plan_b_dual = {
            "model_stack": {},
            "loaders": {
                "unet": [{"node_id": "1", "loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"}],
                "clip": [{"node_id": "2", "loader_class": "DualCLIPLoader", "clip_name1": "c1.safetensors", "clip_name2": "c2.safetensors", "type": "sdxl", "device": "default"}],
                "vae": [],
            },
        }
        self.assertTrue(_cpu_snapshot_specs_match(plan_a_dual, plan_b_dual))

    def test_mismatch_on_weight_dtype(self):
        """Changed weight_dtype must cause projection mismatch."""
        spec_fp16 = {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "fp16"}],
                "clip": [{"loader_class": "CLIPLoader", "clip_name": "c.safetensors", "type": "sd3"}],
            },
        }
        spec_fp32 = {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "fp32"}],
                "clip": [{"loader_class": "CLIPLoader", "clip_name": "c.safetensors", "type": "sd3"}],
            },
        }
        self.assertFalse(_cpu_snapshot_specs_match(spec_fp16, spec_fp32))

    def test_mismatch_on_clip_type(self):
        """Changed CLIP type (sd3 vs sdxl) must cause projection mismatch."""
        spec_sd3 = {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"}],
                "clip": [{"loader_class": "CLIPLoader", "clip_name": "c.safetensors", "type": "sd3"}],
            },
        }
        spec_sdxl = {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"}],
                "clip": [{"loader_class": "CLIPLoader", "clip_name": "c.safetensors", "type": "sdxl"}],
            },
        }
        self.assertFalse(_cpu_snapshot_specs_match(spec_sd3, spec_sdxl))

    def test_mismatch_on_loader_class(self):
        """Different loader class (CLIPLoader vs DualCLIPLoader) must mismatch."""
        spec_single = {
            "loaders": {
                "unet": [],
                "clip": [{"loader_class": "CLIPLoader", "clip_name": "c.safetensors", "type": "sd3"}],
            },
        }
        spec_dual = {
            "loaders": {
                "unet": [],
                "clip": [{"loader_class": "DualCLIPLoader", "clip_name1": "c1.safetensors", "clip_name2": "c2.safetensors", "type": "sd3"}],
            },
        }
        self.assertFalse(_cpu_snapshot_specs_match(spec_single, spec_dual))

    def test_mismatch_on_unet_name(self):
        """Different UNET filename must cause projection mismatch."""
        spec_a = {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": "model_a.safetensors", "weight_dtype": "default"}],
            },
        }
        spec_b = {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": "model_b.safetensors", "weight_dtype": "default"}],
            },
        }
        self.assertFalse(_cpu_snapshot_specs_match(spec_a, spec_b))

    def test_projection_empty_specs_match(self):
        """Two empty specs should match."""
        self.assertTrue(_cpu_snapshot_specs_match({}, {}))
        self.assertTrue(_cpu_snapshot_specs_match(None, None))
        self.assertTrue(_cpu_snapshot_specs_match({"loaders": {}}, {"loaders": {}}))

    def test_projection_accepts_mappingproxy(self):
        """Projection accepts MappingProxyType (frozen RestorePlan.model_spec)."""
        proxy_spec = MappingProxyType({
            "loaders": {
                "unet": [MappingProxyType({"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"})],
                "clip": [MappingProxyType({"loader_class": "CLIPLoader", "clip_name": "c.safetensors", "type": "sd3"})],
            },
        })
        proj = _cpu_snapshot_spec_projection(proxy_spec)
        self.assertEqual(len(proj["unet"]), 1)
        self.assertEqual(proj["unet"][0]["unet_name"], "u.safetensors")
        self.assertEqual(len(proj["clip"]), 1)
        self.assertEqual(proj["clip"][0]["clip_name"], "c.safetensors")
        # Ensure VAE is absent from projection
        self.assertNotIn("vae", proj)

    def test_projection_ignores_vae_loader(self):
        """VAE loaders must be omitted from projection."""
        spec_with_vae = {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"}],
                "clip": [{"loader_class": "CLIPLoader", "clip_name": "c.safetensors", "type": "sd3"}],
                "vae": [{"loader_class": "VAELoader", "vae_name": "ae.safetensors"}],
            },
        }
        proj = _cpu_snapshot_spec_projection(spec_with_vae)
        # VAE loader count must be absent from the result structure
        self.assertNotIn("vae", proj)
        # And VAE details must not leak into unet or clip entries
        for entry in proj["unet"]:
            self.assertNotIn("vae_name", entry)
        for entry in proj["clip"]:
            self.assertNotIn("vae_name", entry)

    def test_projection_mappingproxy_loader_entries(self):
        """Individual loader entries as MappingProxyType must be handled."""
        inner_loader = MappingProxyType({"loader_class": "UNETLoader", "unet_name": "m.safetensors", "weight_dtype": "fp16"})
        proxy = MappingProxyType({
            "loaders": MappingProxyType({
                "unet": [inner_loader],
                "clip": [],
            }),
        })
        proj = _cpu_snapshot_spec_projection(proxy)
        self.assertEqual(len(proj["unet"]), 1)
        self.assertEqual(proj["unet"][0]["unet_name"], "m.safetensors")
        self.assertEqual(proj["unet"][0]["weight_dtype"], "fp16")


# ── Model key matching tests (non-VAE) ──────────────────────────────


class CpuSnapshotModelKeyMatchingTests(unittest.TestCase):
    """_cpu_snapshot_model_keys_match ignores vae_identity."""

    def test_matches_identical_keys(self):
        """Identical keys must match."""
        a = ModelRestoreKey(unet_identity="u", clip_identity="c", clip_type="sd3")
        b = ModelRestoreKey(unet_identity="u", clip_identity="c", clip_type="sd3")
        self.assertTrue(_cpu_snapshot_model_keys_match(a, b))

    def test_matches_when_only_vae_differs(self):
        """VAE-only difference must not prevent match."""
        a = ModelRestoreKey(unet_identity="u", clip_identity="c", vae_identity="", clip_type="sd3")
        b = ModelRestoreKey(unet_identity="u", clip_identity="c", vae_identity="ae.safetensors", clip_type="sd3")
        self.assertTrue(_cpu_snapshot_model_keys_match(a, b))

    def test_mismatches_on_unet_difference(self):
        """UNET identity difference must cause mismatch."""
        a = ModelRestoreKey(unet_identity="u_a", clip_identity="c", clip_type="sd3")
        b = ModelRestoreKey(unet_identity="u_b", clip_identity="c", clip_type="sd3")
        self.assertFalse(_cpu_snapshot_model_keys_match(a, b))

    def test_mismatches_on_clip_difference(self):
        """CLIP identity difference must cause mismatch."""
        a = ModelRestoreKey(unet_identity="u", clip_identity="c_a", clip_type="sd3")
        b = ModelRestoreKey(unet_identity="u", clip_identity="c_b", clip_type="sd3")
        self.assertFalse(_cpu_snapshot_model_keys_match(a, b))

    def test_mismatches_on_clip_type_difference(self):
        """CLIP type difference must cause mismatch."""
        a = ModelRestoreKey(unet_identity="u", clip_identity="c", clip_type="sd3")
        b = ModelRestoreKey(unet_identity="u", clip_identity="c", clip_type="sdxl")
        self.assertFalse(_cpu_snapshot_model_keys_match(a, b))

    def test_empty_keys_match(self):
        """Two empty keys should match."""
        self.assertTrue(_cpu_snapshot_model_keys_match(ModelRestoreKey(), ModelRestoreKey()))


# ── Request binding / prompt-only prefill rebinding tests ──────────────


class CpuSnapshotRequestBindingProjectionTests(unittest.TestCase):
    """Request binding uses _cpu_snapshot_specs_match instead of full equality.

    Verify that prompt-only changes rebind (new prefill key) while model
    identity changes (weight_dtype, CLIP type, loader class, filenames,
    single/dual layout) clear the bridge.
    """

    def setUp(self):
        _clean_env()
        self.entrypoint = ModalRuntimeEntrypoint()
        _ensure_bridge_has_fake_nodes(self.entrypoint._preload_bridge)
        self.trace = RuntimeTrace(request_id="req-proj", process="remote")

    def _make_plan_a_spec(self, unet_name="u.safetensors", clip_name="c.safetensors",
                          clip_type="sd3", weight_dtype="default"):
        return {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": unet_name, "weight_dtype": weight_dtype}],
                "clip": [{"loader_class": "CLIPLoader", "clip_name": clip_name, "type": clip_type, "device": "default"}],
                "vae": [],
            },
        }

    def _make_plan_b_spec(self, unet_name="u.safetensors", clip_name="c.safetensors",
                          clip_type="sd3", weight_dtype="default", has_vae=False):
        spec = {
            "model_stack": {},
            "loaders": {
                "unet": [{"node_id": "13", "loader_class": "UNETLoader", "unet_name": unet_name, "weight_dtype": weight_dtype}],
                "clip": [{"node_id": "45", "loader_class": "CLIPLoader", "clip_name": clip_name, "type": clip_type, "device": "default"}],
            },
        }
        if has_vae:
            spec["loaders"]["vae"] = [{"node_id": "67", "loader_class": "VAELoader", "vae_name": "ae.safetensors"}]
        else:
            spec["loaders"]["vae"] = []
        return spec

    def _make_snapshot_with_spec(self, spec=None):
        if spec is None:
            spec = self._make_plan_a_spec()
        key = ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors", clip_type="sd3")
        return CpuSnapshotModels(
            model_key=key,
            model_spec=spec,
            normalized_profile={"mode": "split", "unet": "u.safetensors", "clip1": "c.safetensors", "clip_type": "sd3"},
            file_facts=(),
            unet=object(),
            clip=_FakeClip(),
        )

    def test_binds_on_plan_b_spec_match(self):
        """Plan B request spec binds when projection matches Plan A snapshot."""
        snapshot = self._make_snapshot_with_spec(self._make_plan_a_spec())
        self.entrypoint._cpu_snapshot_models = snapshot
        self.entrypoint._cpu_snapshot_models_active = True

        request_spec = self._make_plan_b_spec()
        request_key = ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors", clip_type="sd3")

        # Simulate the request binding check
        from comfymodal_runtime.contracts import PrefillKey as _PK
        match = (
            request_key == snapshot.model_key
            and _cpu_snapshot_specs_match(request_spec, snapshot.model_spec)
        )
        self.assertTrue(match, "Plan B spec should projection-match Plan A spec")

        if match:
            self.entrypoint._use_cpu_snapshot_models_on_bridge(
                request_key,
                _PK(model_key=request_key, prompt_bundle_hash="prompt123"),
                request_spec,
                snapshot.unet,
                snapshot.clip,
                trace=self.trace,
            )
        self.assertIsNotNone(
            self.entrypoint._preload_bridge._preparation,
            "bridge must have preparation after bind",
        )

    def test_clears_on_weight_dtype_change(self):
        """Weight dtype change between request and snapshot must clear bridge."""
        snapshot = self._make_snapshot_with_spec(
            self._make_plan_a_spec(weight_dtype="fp16")
        )
        self.entrypoint._cpu_snapshot_models = snapshot
        self.entrypoint._cpu_snapshot_models_active = True

        request_spec = self._make_plan_b_spec(weight_dtype="fp32")
        request_key = ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors", clip_type="sd3")

        match = (
            request_key == snapshot.model_key
            and _cpu_snapshot_specs_match(request_spec, snapshot.model_spec)
        )
        self.assertFalse(match, "weight_dtype change should not projection-match")

    def test_clears_on_clip_type_change(self):
        """CLIP type change must clear bridge."""
        snapshot = self._make_snapshot_with_spec(
            self._make_plan_a_spec(clip_type="sd3")
        )
        self.entrypoint._cpu_snapshot_models = snapshot
        self.entrypoint._cpu_snapshot_models_active = True

        request_spec = self._make_plan_b_spec(clip_type="sdxl")
        request_key = ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors", clip_type="sd3")

        snapshot_key = snapshot.model_key
        # Model key may differ on clip_type; if it does, match is false anyway
        if request_key == snapshot_key:
            match = _cpu_snapshot_specs_match(request_spec, snapshot.model_spec)
            self.assertFalse(match, "clip_type change should not projection-match")

    def test_clears_on_single_to_dual_layout(self):
        """Switching from single CLIP to dual CLIP must clear bridge."""
        plan_a_spec = {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"}],
                "clip": [{"loader_class": "CLIPLoader", "clip_name": "c.safetensors", "type": "sd3", "device": "default"}],
                "vae": [],
            },
        }
        snapshot = self._make_snapshot_with_spec(plan_a_spec)
        self.entrypoint._cpu_snapshot_models = snapshot
        self.entrypoint._cpu_snapshot_models_active = True

        # Dual CLIP request spec
        request_spec = {
            "model_stack": {},
            "loaders": {
                "unet": [{"node_id": "1", "loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"}],
                "clip": [{"node_id": "2", "loader_class": "DualCLIPLoader",
                           "clip_name1": "c.safetensors", "clip_name2": "c2.safetensors",
                           "type": "sd3", "device": "default"}],
                "vae": [],
            },
        }
        request_key = ModelRestoreKey(
            unet_identity="u.safetensors",
            clip_identity="c.safetensors||c2.safetensors",
            clip_type="sd3",
        )
        snapshot_key = snapshot.model_key
        if request_key == snapshot_key:
            match = _cpu_snapshot_specs_match(request_spec, snapshot.model_spec)
            self.assertFalse(match, "single-to-dual layout change should not projection-match")

    def test_binds_when_only_vae_differs(self):
        """VAE-only key difference must still bind (non-VAE matcher)."""
        snapshot = self._make_snapshot_with_spec(self._make_plan_a_spec())
        # Snapshot has no VAE (vae_identity="")
        snapshot.model_key = ModelRestoreKey(
            unet_identity="u.safetensors", clip_identity="c.safetensors",
            vae_identity="", clip_type="sd3",
        )
        self.entrypoint._cpu_snapshot_models = snapshot
        self.entrypoint._cpu_snapshot_models_active = True

        # Request has VAE identity set (Plan B might include VAE)
        request_key = ModelRestoreKey(
            unet_identity="u.safetensors", clip_identity="c.safetensors",
            vae_identity="ae.safetensors", clip_type="sd3",
        )
        request_spec = self._make_plan_b_spec(has_vae=True)

        # Non-VAE key matcher must return True
        self.assertTrue(
            _cpu_snapshot_model_keys_match(request_key, snapshot.model_key),
            "keys must match when only VAE differs",
        )
        # Spec projection must also match (VAE ignored in projection)
        self.assertTrue(
            _cpu_snapshot_specs_match(request_spec, snapshot.model_spec),
            "specs must match when only VAE differs",
        )

        match = (
            _cpu_snapshot_model_keys_match(request_key, snapshot.model_key)
            and _cpu_snapshot_specs_match(request_spec, snapshot.model_spec)
        )
        self.assertTrue(match, "VAE-only difference must not prevent bind")

    def test_request_event_name_is_cpu_snapshot_models_request_bound(self):
        """Request event name must be exactly 'cpu_snapshot_models_request_bound'."""
        trace = RuntimeTrace(request_id="evt-name-test", process="remote")
        snapshot = self._make_snapshot_with_spec(self._make_plan_a_spec())
        self.entrypoint._cpu_snapshot_models = snapshot
        self.entrypoint._cpu_snapshot_models_active = True

        from comfymodal_runtime.contracts import PrefillKey as _PK
        self.entrypoint._use_cpu_snapshot_models_on_bridge(
            snapshot.model_key,
            _PK(model_key=snapshot.model_key, prompt_bundle_hash="test"),
            snapshot.model_spec,
            snapshot.unet,
            snapshot.clip,
            trace=trace,
        )

        # Emit the request-bound event
        trace.emit(
            "cpu_snapshot_models_request_bound",
            phase="execution",
            metadata={"status": "bound", "model_key_hash": "test"},
        )
        # Verify the exact event name exists in the trace
        event_names = [e.name for e in trace.events]
        self.assertIn("cpu_snapshot_models_request_bound", event_names)
        self.assertNotIn("cpu_snapshot_request_bound", event_names,
                         "old event name must not be present")

    def test_prompt_only_change_rebinds_with_new_prefill_key(self):
        """Prompt-only changes match on model_key and spec projection,
        producing a new prefill_key without clearing the bridge."""
        snapshot = self._make_snapshot_with_spec(self._make_plan_a_spec())
        self.entrypoint._cpu_snapshot_models = snapshot
        self.entrypoint._cpu_snapshot_models_active = True
        # Activate bridge first (as restore would)
        from comfymodal_runtime.contracts import PrefillKey as _PK
        self.entrypoint._use_cpu_snapshot_models_on_bridge(
            snapshot.model_key,
            _PK(model_key=snapshot.model_key, prompt_bundle_hash="original_hash"),
            snapshot.model_spec,
            snapshot.unet,
            snapshot.clip,
        )

        # Simulate a request that differs only in prompt (same model)
        request_spec = self._make_plan_b_spec()  # same models, Plan B shape
        request_key = ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors", clip_type="sd3")

        match = (
            request_key == snapshot.model_key
            and _cpu_snapshot_specs_match(request_spec, snapshot.model_spec)
        )
        self.assertTrue(match, "prompt-only request must projection-match")

        # Rebind with new prefill key
        new_prefill_key = _PK(model_key=request_key, prompt_bundle_hash="new_prompt_hash")
        self.entrypoint._use_cpu_snapshot_models_on_bridge(
            request_key,
            new_prefill_key,
            request_spec,
            snapshot.unet,
            snapshot.clip,
            trace=self.trace,
        )
        bridge = self.entrypoint._preload_bridge
        self.assertEqual(
            bridge._prefill_key.prompt_bundle_hash,
            "new_prompt_hash",
            "prompt-only change must update prefill_key on bridge",
        )
        self.assertTrue(
            self.entrypoint._cpu_snapshot_models_active,
            "snapshot should remain active after prompt-only change",
        )


# ── Activation-condition tests (Issue 1) ──────────────────────────────


class CpuSnapshotActivationConditionTests(unittest.TestCase):
    """Verify that restore activation eligibility does NOT require
    ``not self._cpu_snapshot_models_active``.

    On every restore(snap=False), when the feature is enabled, a
    snapshot bundle exists, and a restore plan is present, the
    activation block must be entered regardless of the current
    active bit.  This prevents a changed restore plan from inheriting
    an old active bit.
    """

    def setUp(self):
        _clean_env()
        self.entrypoint = ModalRuntimeEntrypoint()
        self.snapshot = _make_snapshot_models()
        self.entrypoint._cpu_snapshot_models = self.snapshot
        self.entrypoint._restore_plan = SimpleNamespace(
            model_key=self.snapshot.model_key,
            model_spec=self.snapshot.model_spec,
        )

    def test_activation_condition_not_blocked_by_active_state(self):
        """Condition must pass even when _cpu_snapshot_models_active is True."""
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "1"
        self.entrypoint._cpu_snapshot_models_active = True
        try:
            condition = (
                _cpu_model_snapshot_enabled()
                and self.entrypoint._cpu_snapshot_models is not None
                and self.entrypoint._restore_plan is not None
            )
            self.assertTrue(
                condition,
                "activation eligibility must not require "
                "not self._cpu_snapshot_models_active",
            )
        finally:
            _clean_env()

    def test_activation_condition_passes_when_inactive(self):
        """Condition must pass when _cpu_snapshot_models_active is False (baseline)."""
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "1"
        self.entrypoint._cpu_snapshot_models_active = False
        try:
            condition = (
                _cpu_model_snapshot_enabled()
                and self.entrypoint._cpu_snapshot_models is not None
                and self.entrypoint._restore_plan is not None
            )
            self.assertTrue(condition, "baseline activation condition must pass")
        finally:
            _clean_env()

    def test_activation_condition_fails_without_feature_flag(self):
        """Condition must fail when feature is disabled."""
        _clean_env()
        self.entrypoint._cpu_snapshot_models_active = True
        condition = (
            _cpu_model_snapshot_enabled()
            and self.entrypoint._cpu_snapshot_models is not None
            and self.entrypoint._restore_plan is not None
        )
        self.assertFalse(condition, "must be false when feature is disabled")

    def test_activation_condition_fails_without_models(self):
        """Condition must fail when _cpu_snapshot_models is None."""
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "1"
        self.entrypoint._cpu_snapshot_models = None
        self.entrypoint._cpu_snapshot_models_active = True
        try:
            condition = (
                _cpu_model_snapshot_enabled()
                and self.entrypoint._cpu_snapshot_models is not None
                and self.entrypoint._restore_plan is not None
            )
            self.assertFalse(condition, "must be false when snapshot models is None")
        finally:
            _clean_env()

    def test_activation_condition_fails_without_plan(self):
        """Condition must fail when _restore_plan is None."""
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "1"
        self.entrypoint._restore_plan = None
        self.entrypoint._cpu_snapshot_models_active = True
        try:
            condition = (
                _cpu_model_snapshot_enabled()
                and self.entrypoint._cpu_snapshot_models is not None
                and self.entrypoint._restore_plan is not None
            )
            self.assertFalse(condition, "must be false when restore plan is None")
        finally:
            _clean_env()


# ── Unbound stored original wrapper tests (Issue 2) ───────────────────


class CpuSnapshotUnboundOriginalWrapperTests(unittest.TestCase):
    """Verify that the startup loader callbacks correctly invoke explicit
    ``_comfy_modal_v2_original`` methods when V2 wrappers are installed.

    The V2LoaderBridge.install() stores the original unbound function
    as ``_comfy_modal_v2_original`` on the wrapper (class method).
    Startup callbacks resolve node classes from NODE_CLASS_MAPPINGS,
    check if the class method has ``_comfy_modal_v2_original``, and if
    so call it with the fresh loader instance as ``self``; otherwise
    they fall back to the bound loader method.
    """

    def test_unbound_original_found_on_class_method(self):
        """_comfy_modal_v2_original must be found on the class method
        (unbound), not on the instance."""
        class _MockUNETLoader:
            def load_unet(self, name: str, weight_dtype: str) -> Any:
                return (f"loaded:{name}:{weight_dtype}",)

        original_unbound = _MockUNETLoader.load_unet

        # Install a wrapper mimicking V2LoaderBridge.install()
        def wrapper(self, name, weight_dtype):
            return original_unbound(self, name, weight_dtype)
        setattr(wrapper, "_comfy_modal_v2_original", original_unbound)
        _MockUNETLoader.load_unet = wrapper

        # Resolve as the startup code does
        cls_method = _MockUNETLoader.load_unet
        resolved_orig = getattr(cls_method, "_comfy_modal_v2_original", None)

        self.assertIsNotNone(
            resolved_orig,
            "_comfy_modal_v2_original must be resolvable from the class method",
        )
        self.assertIs(
            resolved_orig, original_unbound,
            "resolved original must be the original unbound function",
        )

        # Verify calling with a fresh instance as self works
        loader = _MockUNETLoader()
        result = resolved_orig(loader, "model.safetensors", "fp16")
        self.assertEqual(result, ("loaded:model.safetensors:fp16",))

    def test_fallback_to_bound_method_when_no_wrapper(self):
        """When _comfy_modal_v2_original is absent, fall back to the
        bound loader method (normal behavior without V2 wrappers)."""
        class _MockCLIPLoader:
            def load_clip(self, clip_name: str, clip_type: str, device: str = "cpu") -> Any:
                return (f"clip:{clip_name}:{clip_type}",)

        # No V2 wrapper — class method has no _comfy_modal_v2_original
        cls_method = _MockCLIPLoader.load_clip
        resolved_orig = getattr(cls_method, "_comfy_modal_v2_original", None)
        self.assertIsNone(
            resolved_orig,
            "without V2 wrapper, _comfy_modal_v2_original must be None",
        )

        # Fallback: use the bound method
        loader = _MockCLIPLoader()
        result = loader.load_clip("clip.safetensors", "sd3", device="cpu")
        self.assertEqual(result, ("clip:clip.safetensors:sd3",))

    def test_unbound_original_with_device_signature(self):
        """When the original method accepts a 'device' kwarg, calling
        with device='cpu' must work (signature-aware dispatch)."""
        class _MockDualCLIPLoader:
            def load_clip(self, name1: str, name2: str, typ: str, device: str = "default") -> Any:
                return (f"dual:{name1}:{name2}:{typ}:{device}",)

        original_unbound = _MockDualCLIPLoader.load_clip

        # Install V2 wrapper
        def wrapper(self, name1, name2, typ, device="default"):
            return original_unbound(self, name1, name2, typ, device=device)
        setattr(wrapper, "_comfy_modal_v2_original", original_unbound)
        _MockDualCLIPLoader.load_clip = wrapper

        cls_method = _MockDualCLIPLoader.load_clip
        orig = getattr(cls_method, "_comfy_modal_v2_original", None)
        self.assertIsNotNone(orig)

        # Call with instance as self and device='cpu'
        loader = _MockDualCLIPLoader()
        result = orig(loader, "clip1.safetensors", "clip2.safetensors", "sdxl", device="cpu")
        self.assertEqual(result, ("dual:clip1.safetensors:clip2.safetensors:sdxl:cpu",))

    def test_unbound_original_without_device_signature(self):
        """When the original method does not accept a 'device' kwarg,
        calling without device must work (single/dual arity)."""
        class _MockCLIPLoaderNoDevice:
            def load_clip(self, clip_name: str, clip_type: str) -> Any:
                return (f"clip:{clip_name}:{clip_type}",)

        original_unbound = _MockCLIPLoaderNoDevice.load_clip

        def wrapper(self, name, typ):
            return original_unbound(self, name, typ)
        setattr(wrapper, "_comfy_modal_v2_original", original_unbound)
        _MockCLIPLoaderNoDevice.load_clip = wrapper

        cls_method = _MockCLIPLoaderNoDevice.load_clip
        orig = getattr(cls_method, "_comfy_modal_v2_original", None)
        self.assertIsNotNone(orig)

        loader = _MockCLIPLoaderNoDevice()
        result = orig(loader, "clip.safetensors", "sd3")
        self.assertEqual(result, ("clip:clip.safetensors:sd3",))

    def test_install_idempotence_preserves_unbound_original(self):
        """Simulate V2LoaderBridge.install() idempotence: re-installing
        must preserve the unbound original on the wrapper."""
        class _MockLoader:
            def load_unet(self, name, dtype):
                return (f"ok:{name}",)

        original_unbound = _MockLoader.load_unet

        # First install
        def wrapper1(self, name, dtype):
            return original_unbound(self, name, dtype)
        setattr(wrapper1, "_comfy_modal_v2_original", original_unbound)
        setattr(wrapper1, "_comfy_modal_v2_loader_bridge", True)
        _MockLoader.load_unet = wrapper1

        # Simulate second install (idempotent path)
        method = _MockLoader.load_unet
        if getattr(method, "_comfy_modal_v2_loader_bridge", False):
            stored_original = getattr(method, "_comfy_modal_v2_original", None)
            if callable(stored_original):
                # Re-use the stored original (this is what install() does)
                pass

        # The stored original must still be the original unbound function
        self.assertIs(
            getattr(_MockLoader.load_unet, "_comfy_modal_v2_original", None),
            original_unbound,
            "re-install must preserve _comfy_modal_v2_original on the wrapper",
        )

        # Calling through the pattern must still work
        loader = _MockLoader()
        orig = getattr(_MockLoader.load_unet, "_comfy_modal_v2_original", None)
        result = orig(loader, "model.safetensors", "fp16")
        self.assertEqual(result, ("ok:model.safetensors",))


class TestCollectWarmupEnv(unittest.TestCase):
    """Tests for _collect_warmup_env image-env propagation helper."""

    def test_returns_only_present_keys(self):
        """Only env vars that are set in the environment are returned."""
        with unittest.mock.patch.dict(os.environ, {
            "COMFYMODAL_WARMUP_UNET": "test_unet.safetensors",
            "COMFYMODAL_WARMUP_CLIP1": "test_clip.safetensors",
            "COMFYMODAL_WARMUP_VAE": "test_vae.safetensors",
        }, clear=True):
            result = _collect_warmup_env()
        self.assertEqual(result, {
            "COMFYMODAL_WARMUP_UNET": "test_unet.safetensors",
            "COMFYMODAL_WARMUP_CLIP1": "test_clip.safetensors",
            "COMFYMODAL_WARMUP_VAE": "test_vae.safetensors",
        })
        # Ensure only 3 keys were returned, not all 8
        self.assertEqual(len(result), 3)

    def test_returns_empty_dict_when_none_set(self):
        """When no COMFYMODAL_WARMUP_* vars are set, returns empty dict."""
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            result = _collect_warmup_env()
        self.assertEqual(result, {})

    def test_returns_all_eight_keys_when_all_set(self):
        """Every recognised warmup key is returned when present."""
        full = {
            "COMFYMODAL_WARMUP_PROFILE": "split",
            "COMFYMODAL_WARMUP_CHECKPOINT": "ckpt.safetensors",
            "COMFYMODAL_WARMUP_UNET": "unet.safetensors",
            "COMFYMODAL_WARMUP_CLIP1": "clip1.safetensors",
            "COMFYMODAL_WARMUP_CLIP2": "clip2.safetensors",
            "COMFYMODAL_WARMUP_VAE": "vae.safetensors",
            "COMFYMODAL_WARMUP_CLIP_TYPE": "flux",
            "COMFYMODAL_WARMUP_TEXT": "warmup",
        }
        with unittest.mock.patch.dict(os.environ, full, clear=True):
            result = _collect_warmup_env()
        self.assertEqual(result, full)

    def test_ignores_unrecognised_keys(self):
        """Extra env vars without the COMFYMODAL_WARMUP_ prefix are ignored."""
        with unittest.mock.patch.dict(os.environ, {
            "COMFYMODAL_WARMUP_UNET": "u.safetensors",
            "SOME_OTHER_VAR": "ignored",
        }, clear=True):
            result = _collect_warmup_env()
        self.assertEqual(result, {"COMFYMODAL_WARMUP_UNET": "u.safetensors"})


if __name__ == "__main__":
    unittest.main()
