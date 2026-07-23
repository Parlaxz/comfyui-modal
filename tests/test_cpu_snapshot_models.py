"""Tests for comfymodal_runtime.cpu_snapshot_models.

Covers all required categories:
  1  identity_from_profile valid split profile -> 3-tuple
  2  identity_from_profile missing mode -> ValueError
  3  identity_from_profile unsupported mode -> ValueError
  4  identity_from_profile missing unet -> ValueError
  5  identity_from_profile missing clip1 -> ValueError
  6  identity_from_profile missing clip_type -> ValueError
  7  identity_from_profile clip2 duplicate collapse
  8  identity_from_profile weight_dtype preserved in model_spec
  9  identity_from_profile weight_dtype absent -> "default" in model_spec
 10  ModelRestoreKey unet_identity
 11  ModelRestoreKey clip_identity single
 12  ModelRestoreKey clip_identity dual (||)
 13  ModelRestoreKey vae_identity empty
 14  ModelRestoreKey clip_type
 15  model_spec UNETLoader loader_class + unet_name + weight_dtype
 16  model_spec CLIPLoader / DualCLIPLoader type device
 17  model_spec no node IDs, no prompt fields, no hashes
 18  load: sequential CLIP -> gc -> UNET -> gc
 19  load: torch.no_grad (not inference_mode)
 20  load: calls identity_from_profile (primary path)
 21  load: trace events exact names (cpu_snapshot_clip/unet_*)
 22  load: failed trace event
 23  validate: identity mismatch -> (False, reason)
 24  validate: spec mismatch
 25  validate: file fact resolved-path, size, mtime
 26  validate: split config check
 27  validate: unet shape invalid
 28  validate: clip shape invalid (missing patcher/tokenizer)
 29  validate: CUDA tensors rejected
 30  validate: meta tensors rejected
 31  validate: custom-device (xpu) allowed
 32  validate: tokenizer failure
 33  retarget: done with model_management
 34  retarget: unsupported_unet_shape
 35  retarget: unsupported_clip_shape
 36  retarget: missing model_management function
 37  retarget: only patcher device attributes, no .to
"""

from __future__ import annotations

import gc
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Fake torch stubs (duck-typed, no real torch dependency for fake modules)
# ---------------------------------------------------------------------------

_HAS_REAL_TORCH = False
try:
    import torch
    _HAS_REAL_TORCH = True
except ImportError:
    pass


class _FakeTensor:
    """Minimal tensor stub for device attribute checks."""
    def __init__(self, device="cpu", is_meta=False):
        self.device = device
        self.is_meta = is_meta


class _FakeModule:
    """Duck-typed torch.nn.Module stand-in with parameters/buffers."""
    def __init__(self, device="cpu"):
        self._params = {"weight": _FakeTensor(device)}
        self._buffers = {"bias": _FakeTensor(device)}

    def parameters(self, recurse=True):
        return iter([self._params["weight"]])

    def named_parameters(self, recurse=True):
        for name, tensor in self._params.items():
            yield name, tensor

    def buffers(self, recurse=True):
        return iter([self._buffers["bias"]])

    def named_buffers(self, recurse=True):
        for name, tensor in self._buffers.items():
            yield name, tensor


class _FakeUNETPatcher:
    """Mimics a ComfyUI ModelPatcher for UNET."""
    def __init__(self, device="cpu"):
        self.model = _FakeModule(device)
        self.load_device = device
        self.offload_device = "cpu"


class _FakeCLIP:
    """Mimics a ComfyUI CLIP object with cond_stage_model + patcher."""
    def __init__(self, device="cpu"):
        self.cond_stage_model = _FakeModule(device)
        self.tokenizer = MagicMock()
        patcher = MagicMock()
        patcher.load_device = device
        patcher.offload_device = "cpu"
        patcher.model = self.cond_stage_model
        self.patcher = patcher


class _FakeCLIPNested:
    """Mimics DualCLIP with clip_l/clip_g nested under cond_stage_model."""
    def __init__(self, device="cpu"):
        self.tokenizer = MagicMock()
        self.cond_stage_model = MagicMock()
        self.cond_stage_model.clip_l = _FakeModule(device)
        self.cond_stage_model.clip_g = _FakeModule(device)
        patcher = MagicMock()
        patcher.load_device = device
        patcher.offload_device = "cpu"
        patcher.model = self.cond_stage_model.clip_l
        self.patcher = patcher


class _FakeCLIPPatcherModel:
    """Mimics a CLIP where only patcher.model is available (no cond_stage_model)."""
    def __init__(self, device="cpu"):
        self.tokenizer = MagicMock()
        pm = _FakeModule(device)
        patcher = MagicMock()
        patcher.load_device = device
        patcher.offload_device = "cpu"
        patcher.model = pm
        self.patcher = patcher


class _FakeCLIPNoTokenizer:
    """CLIP without tokenizer — should fail validation."""
    def __init__(self, device="cpu"):
        self.cond_stage_model = _FakeModule(device)
        self.tokenizer = None
        patcher = MagicMock()
        patcher.load_device = device
        patcher.offload_device = "cpu"
        self.patcher = patcher


# ---------------------------------------------------------------------------
# Fake model_management module
# ---------------------------------------------------------------------------


class _FakeModelManagement:
    @staticmethod
    def get_torch_device():
        return "cuda:0"

    @staticmethod
    def unet_offload_device():
        return "cpu"

    @staticmethod
    def text_encoder_device():
        return "cuda:0"

    @staticmethod
    def text_encoder_offload_device():
        return "cpu"


class _FakeModelManagementMissingFunc:
    @staticmethod
    def get_torch_device():
        return "cuda:0"
    # missing unet_offload_device, text_encoder_device, text_encoder_offload_device


# ---------------------------------------------------------------------------
# Shared profile / resolve_path helpers
# ---------------------------------------------------------------------------

_VALID_SPLIT_PROFILE = {
    "mode": "split",
    "unet": "flux1-dev.safetensors",
    "clip1": "clip_l.safetensors",
    "clip2": "t5xxl.safetensors",
    "clip_type": "flux",
}

_SINGLE_CLIP_PROFILE = {
    "mode": "split",
    "unet": "flux1-dev.safetensors",
    "clip1": "clip_l.safetensors",
    "clip2": "",
    "clip_type": "flux",
}


def _make_resolve_path(temp_dir: str):
    """Build a resolve_path callback that creates stat-able temporary files."""
    def resolve_path(role: str, filename: str) -> str:
        path = os.path.join(temp_dir, filename)
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(b"x" * 1024)
        return path
    return resolve_path


def _get_stored_mtime(path: str) -> int:
    st = os.stat(path)
    return int(st.st_mtime_ns if hasattr(st, "st_mtime_ns") else st.st_mtime * 1_000_000_000)


def _create_file(temp_dir: str, name: str, size: int = 100) -> str:
    path = os.path.join(temp_dir, name)
    with open(path, "wb") as f:
        f.write(b"\x00" * size)
    return path


class TestIdentityFromProfile(unittest.TestCase):
    """Categories 1-9: identity_from_profile behaviour."""

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.resolve = _make_resolve_path(self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. Valid split profile returns 3-tuple
    def test_valid_split_profile(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        result = identity_from_profile(_VALID_SPLIT_PROFILE, resolve_path=self.resolve)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)
        key, spec, facts = result
        self.assertEqual(key.unet_identity, "flux1-dev.safetensors")
        self.assertEqual(key.clip_identity, "clip_l.safetensors||t5xxl.safetensors")
        self.assertEqual(key.vae_identity, "")
        self.assertEqual(key.clip_type, "flux")
        # facts: unet, clip1, clip2
        self.assertEqual(len(facts), 3)
        self.assertEqual(facts[0].role, "unet")
        self.assertEqual(facts[1].role, "clip1")
        self.assertEqual(facts[2].role, "clip2")

    # 2. Missing mode
    def test_missing_mode(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        with self.assertRaises(ValueError) as ctx:
            identity_from_profile({"unet": "x", "clip1": "y", "clip_type": "flux"}, resolve_path=self.resolve)
        self.assertIn("mode", str(ctx.exception).lower())

    # 3. Unsupported mode
    def test_unsupported_mode(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        with self.assertRaises(ValueError) as ctx:
            identity_from_profile({"mode": "checkpoint", "unet": "x", "clip1": "y", "clip_type": "flux"}, resolve_path=self.resolve)
        self.assertIn("unsupported", str(ctx.exception).lower())

    # 4. Missing unet
    def test_missing_unet(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        with self.assertRaises(ValueError) as ctx:
            identity_from_profile({"mode": "split", "clip1": "y", "clip_type": "flux"}, resolve_path=self.resolve)
        self.assertIn("unet", str(ctx.exception).lower())

    # 5. Missing clip1
    def test_missing_clip1(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        with self.assertRaises(ValueError) as ctx:
            identity_from_profile({"mode": "split", "unet": "x", "clip_type": "flux"}, resolve_path=self.resolve)
        self.assertIn("clip1", str(ctx.exception).lower())

    # 6. Missing clip_type
    def test_missing_clip_type(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        with self.assertRaises(ValueError) as ctx:
            identity_from_profile({"mode": "split", "unet": "x", "clip1": "y"}, resolve_path=self.resolve)
        self.assertIn("clip_type", str(ctx.exception).lower())

    # 7. Duplicate clip2 collapsed
    def test_clip2_duplicate_collapse(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        profile = dict(_VALID_SPLIT_PROFILE, clip2="clip_l.safetensors", clip1="clip_l.safetensors")
        key, spec, facts = identity_from_profile(profile, resolve_path=self.resolve)
        self.assertEqual(key.clip_identity, "clip_l.safetensors")
        # clip2 should be collapsed, so only 2 facts (unet, clip1)
        self.assertEqual(len(facts), 2)
        self.assertEqual(facts[0].role, "unet")
        self.assertEqual(facts[1].role, "clip1")

    # 8. weight_dtype preserved in model_spec
    def test_weight_dtype_preserved(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        profile = dict(_SINGLE_CLIP_PROFILE, weight_dtype="fp8_e4m3fn")
        key, spec, facts = identity_from_profile(profile, resolve_path=self.resolve)
        unet_loaders = spec["loaders"]["unet"]
        self.assertEqual(unet_loaders[0]["weight_dtype"], "fp8_e4m3fn")

    # 9. weight_dtype absent -> "default" in model_spec
    def test_weight_dtype_absent(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        profile = dict(_SINGLE_CLIP_PROFILE)
        key, spec, facts = identity_from_profile(profile, resolve_path=self.resolve)
        unet_loaders = spec["loaders"]["unet"]
        self.assertEqual(unet_loaders[0]["weight_dtype"], "default")


class TestModelKeyConstruction(unittest.TestCase):
    """Categories 10-14: ModelRestoreKey field values."""

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.resolve = _make_resolve_path(self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 10. unet_identity
    def test_unet_identity(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        key, _, _ = identity_from_profile(_VALID_SPLIT_PROFILE, resolve_path=self.resolve)
        self.assertEqual(key.unet_identity, "flux1-dev.safetensors")

    # 11. clip_identity single
    def test_clip_identity_single(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        key, _, _ = identity_from_profile(_SINGLE_CLIP_PROFILE, resolve_path=self.resolve)
        self.assertEqual(key.clip_identity, "clip_l.safetensors")

    # 12. clip_identity dual (||)
    def test_clip_identity_dual(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        key, _, _ = identity_from_profile(_VALID_SPLIT_PROFILE, resolve_path=self.resolve)
        self.assertEqual(key.clip_identity, "clip_l.safetensors||t5xxl.safetensors")

    # 13. vae_identity empty
    def test_vae_identity_empty(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        key, _, _ = identity_from_profile(_VALID_SPLIT_PROFILE, resolve_path=self.resolve)
        self.assertEqual(key.vae_identity, "")

    # 14. clip_type
    def test_clip_type(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        key, _, _ = identity_from_profile(_VALID_SPLIT_PROFILE, resolve_path=self.resolve)
        self.assertEqual(key.clip_type, "flux")


class TestIdentitySemantics(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.resolve = _make_resolve_path(self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _key(self, profile):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        return identity_from_profile(profile, resolve_path=self.resolve)[0]

    def test_prompt_like_fields_do_not_change_identity(self):
        base = dict(_SINGLE_CLIP_PROFILE)
        changed = dict(
            base,
            prompt="a different prompt",
            prompt_bundle_hash="bundle-b",
            workflow_hash="workflow-b",
        )
        self.assertEqual(self._key(base), self._key(changed))

    def test_seed_output_and_production_fields_do_not_change_identity(self):
        base = dict(_SINGLE_CLIP_PROFILE)
        changed = dict(
            base,
            seed=987,
            output_nodes=["9"],
            production_enabled=True,
            production_plan_hash="plan-b",
            source_workflow_hash="source-b",
        )
        self.assertEqual(self._key(base), self._key(changed))

    def test_model_fields_change_identity(self):
        base = self._key(_SINGLE_CLIP_PROFILE)
        self.assertNotEqual(
            base,
            self._key(dict(_SINGLE_CLIP_PROFILE, unet="other-unet.safetensors")),
        )
        self.assertNotEqual(
            base,
            self._key(dict(_SINGLE_CLIP_PROFILE, clip1="other-clip.safetensors")),
        )
        self.assertNotEqual(
            base,
            self._key(dict(_SINGLE_CLIP_PROFILE, clip_type="other")),
        )

    def test_identity_reads_stat_metadata_without_reading_contents(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        for filename in ("flux1-dev.safetensors", "clip_l.safetensors"):
            _create_file(self.temp_dir, filename, 32)
        with patch("builtins.open", side_effect=AssertionError("file contents read")):
            key, spec, facts = identity_from_profile(
                _SINGLE_CLIP_PROFILE,
                resolve_path=self.resolve,
            )
        self.assertEqual(key.unet_identity, "flux1-dev.safetensors")
        self.assertEqual(spec["loaders"]["clip"][0]["clip_name"], "clip_l.safetensors")
        self.assertEqual([fact.role for fact in facts], ["unet", "clip1"])

    def test_none_optional_clip2_is_absent(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        key, _, facts = identity_from_profile(
            dict(_SINGLE_CLIP_PROFILE, clip2=None),
            resolve_path=self.resolve,
        )
        self.assertEqual(key.clip_identity, "clip_l.safetensors")
        self.assertEqual(len(facts), 2)


class TestModelSpec(unittest.TestCase):
    """Categories 15-17: model_spec construction."""

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.resolve = _make_resolve_path(self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 15. UNETLoader loader_class + unet_name + weight_dtype (with explicit)
    def test_unet_loader_with_explicit_weight_dtype(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        profile = dict(_SINGLE_CLIP_PROFILE, weight_dtype="fp8_e4m3fn")
        _, spec, _ = identity_from_profile(profile, resolve_path=self.resolve)
        unet_loaders = spec["loaders"]["unet"]
        self.assertEqual(len(unet_loaders), 1)
        self.assertEqual(unet_loaders[0]["loader_class"], "UNETLoader")
        self.assertEqual(unet_loaders[0]["unet_name"], "flux1-dev.safetensors")
        self.assertEqual(unet_loaders[0]["weight_dtype"], "fp8_e4m3fn")

    def test_unet_loader_without_weight_dtype(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        profile = dict(_SINGLE_CLIP_PROFILE)
        _, spec, _ = identity_from_profile(profile, resolve_path=self.resolve)
        unet_loaders = spec["loaders"]["unet"]
        self.assertEqual(len(unet_loaders), 1)
        self.assertEqual(unet_loaders[0]["weight_dtype"], "default")

    # 16. CLIPLoader / DualCLIPLoader type device
    def test_clip_loader_single(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        profile = dict(_SINGLE_CLIP_PROFILE)
        _, spec, _ = identity_from_profile(profile, resolve_path=self.resolve)
        clip_loaders = spec["loaders"]["clip"]
        self.assertEqual(len(clip_loaders), 1)
        self.assertEqual(clip_loaders[0]["loader_class"], "CLIPLoader")
        self.assertEqual(clip_loaders[0]["clip_name"], "clip_l.safetensors")
        self.assertEqual(clip_loaders[0]["type"], "flux")
        self.assertEqual(clip_loaders[0]["device"], "default")

    def test_dual_clip_loader(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        _, spec, _ = identity_from_profile(_VALID_SPLIT_PROFILE, resolve_path=self.resolve)
        clip_loaders = spec["loaders"]["clip"]
        self.assertEqual(len(clip_loaders), 1)
        self.assertEqual(clip_loaders[0]["loader_class"], "DualCLIPLoader")
        self.assertEqual(clip_loaders[0]["clip_name1"], "clip_l.safetensors")
        self.assertEqual(clip_loaders[0]["clip_name2"], "t5xxl.safetensors")
        self.assertEqual(clip_loaders[0]["type"], "flux")
        self.assertEqual(clip_loaders[0]["device"], "default")

    # 17. No node IDs, prompt fields, or hashes in spec
    def test_no_node_ids_in_spec(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        profile = dict(_SINGLE_CLIP_PROFILE)
        _, spec, _ = identity_from_profile(profile, resolve_path=self.resolve)
        for bucket in ("unet", "clip", "vae"):
            for loader in spec.get("loaders", {}).get(bucket, []):
                self.assertNotIn("node_id", loader)
                self.assertNotIn("prompt", loader)
                self.assertNotIn("hash", loader)
                self.assertNotIn("stable_restore_key", loader)


class TestLoad(unittest.TestCase):
    """Categories 18-22: load order, no_grad, identity delegation, trace events."""

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.resolve = _make_resolve_path(self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 18. Sequential CLIP -> gc -> UNET -> gc
    def test_load_order(self):
        from comfymodal_runtime.cpu_snapshot_models import load_cpu_snapshot_models
        load_order = []
        unet_stub = _FakeUNETPatcher()
        clip_stub = _FakeCLIP()

        def load_clip(name, *args):
            load_order.append("clip")
            return clip_stub

        def load_unet(name, *args):
            load_order.append("unet")
            return unet_stub

        profile = dict(_SINGLE_CLIP_PROFILE)
        result = load_cpu_snapshot_models(
            profile,
            load_unet=load_unet,
            load_clip=load_clip,
            resolve_path=self.resolve,
        )
        self.assertEqual(load_order, ["clip", "unet"])
        self.assertIs(result.clip, clip_stub)
        self.assertIs(result.unet, unet_stub)

    def test_gc_called(self):
        from comfymodal_runtime.cpu_snapshot_models import load_cpu_snapshot_models
        original_gc = gc.collect
        gc_calls = []

        def tracking_gc():
            gc_calls.append(len(gc_calls))
            return original_gc()

        unet_stub = _FakeUNETPatcher()
        clip_stub = _FakeCLIP()
        profile = dict(_SINGLE_CLIP_PROFILE)

        with patch("comfymodal_runtime.cpu_snapshot_models.gc.collect", side_effect=tracking_gc):
            load_cpu_snapshot_models(
                profile,
                load_unet=lambda name, *args: unet_stub,
                load_clip=lambda *args: clip_stub,
                resolve_path=self.resolve,
            )
        self.assertGreaterEqual(len(gc_calls), 2)

    # 19. torch.no_grad (not inference_mode)
    def test_no_grad_not_inference_mode(self):
        import inspect
        from comfymodal_runtime import cpu_snapshot_models as csm
        source = inspect.getsource(csm.load_cpu_snapshot_models)
        self.assertIn("torch.no_grad()", source,
                      "Must use torch.no_grad() in load_cpu_snapshot_models")
        self.assertNotIn("torch.inference_mode", source,
                         "Must NOT use torch.inference_mode")
        # Verify the function runs successfully with real torch.no_grad
        unet_stub = _FakeUNETPatcher()
        clip_stub = _FakeCLIP()
        profile = dict(_SINGLE_CLIP_PROFILE)
        result = csm.load_cpu_snapshot_models(
            profile,
            load_unet=lambda name, *args: unet_stub,
            load_clip=lambda *args: clip_stub,
            resolve_path=self.resolve,
        )
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.clip)
        self.assertIsNotNone(result.unet)

    # 20. Load calls identity_from_profile (primary path — uses returned model_spec)
    def test_calls_identity_from_profile(self):
        from comfymodal_runtime.cpu_snapshot_models import (
            load_cpu_snapshot_models,
            identity_from_profile,
        )
        unet_stub = _FakeUNETPatcher()
        clip_stub = _FakeCLIP()
        profile = dict(_SINGLE_CLIP_PROFILE)

        with patch("comfymodal_runtime.cpu_snapshot_models.identity_from_profile",
                   wraps=identity_from_profile) as mock_identity:
            result = load_cpu_snapshot_models(
                profile,
                load_unet=lambda name, *args: unet_stub,
                load_clip=lambda *args: clip_stub,
                resolve_path=self.resolve,
            )
        # identity_from_profile was called
        mock_identity.assert_called_once()
        # The model_spec in the result should match identity's output
        self.assertEqual(result.model_spec["loaders"]["unet"][0]["unet_name"], "flux1-dev.safetensors")

    # 21. Trace events exact names
    def test_trace_events_exact_names(self):
        from comfymodal_runtime.cpu_snapshot_models import load_cpu_snapshot_models
        from comfymodal_runtime.trace import RuntimeTrace
        trace = RuntimeTrace()
        unet_stub = _FakeUNETPatcher()
        clip_stub = _FakeCLIP()
        profile = dict(_SINGLE_CLIP_PROFILE)
        load_cpu_snapshot_models(
            profile,
            load_unet=lambda name, *args: unet_stub,
            load_clip=lambda *args: clip_stub,
            resolve_path=self.resolve,
            trace=trace,
        )
        emitted_names = [e.name for e in trace.events]
        self.assertIn("cpu_snapshot_clip_load_start", emitted_names)
        self.assertIn("cpu_snapshot_clip_load_end", emitted_names)
        self.assertIn("cpu_snapshot_unet_load_start", emitted_names)
        self.assertIn("cpu_snapshot_unet_load_end", emitted_names)
        self.assertIn("cpu_snapshot_models_ready", emitted_names)
        # Old names must NOT be present
        self.assertNotIn("clip_load_start", emitted_names)
        self.assertNotIn("clip_load_end", emitted_names)
        self.assertNotIn("unet_load_start", emitted_names)
        self.assertNotIn("unet_load_end", emitted_names)
        # Metadata on end events has duration_ms
        for e in trace.events:
            if e.name in ("cpu_snapshot_clip_load_end", "cpu_snapshot_unet_load_end"):
                self.assertIn("duration_ms", e.metadata)
                self.assertIsInstance(e.metadata["duration_ms"], (int, float))
            if e.name == "cpu_snapshot_models_ready":
                self.assertIn("model_key_hash", e.metadata)
                self.assertIn("object_type", e.metadata)
                self.assertIn("status", e.metadata)
                self.assertEqual(e.metadata["status"], "ok")

    # 22. Failed trace event
    def test_failed_trace_event(self):
        from comfymodal_runtime.cpu_snapshot_models import load_cpu_snapshot_models
        from comfymodal_runtime.trace import RuntimeTrace
        trace = RuntimeTrace()
        profile = dict(_SINGLE_CLIP_PROFILE)
        with self.assertRaises(RuntimeError):
            load_cpu_snapshot_models(
                profile,
                load_unet=lambda name, *args: (_ for _ in ()).throw(RuntimeError("load failed")),
                load_clip=lambda *args: _FakeCLIP(),
                resolve_path=self.resolve,
                trace=trace,
            )
        emitted_names = [e.name for e in trace.events]
        self.assertIn("cpu_snapshot_models_failed", emitted_names)
        failed_event = [e for e in trace.events if e.name == "cpu_snapshot_models_failed"]
        self.assertGreater(len(failed_event), 0)
        fe = failed_event[0]
        self.assertIn("duration_ms", fe.metadata)
        self.assertIn("model_key_hash", fe.metadata)
        self.assertIn("object_type", fe.metadata)
        self.assertIn("basename", fe.metadata)
        self.assertIn("status", fe.metadata)
        self.assertIn("reason", fe.metadata)
        self.assertEqual(fe.metadata["status"], "error")


class TestValidate(unittest.TestCase):
    """Categories 23-28: validate_cpu_snapshot_models."""

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.resolve = _make_resolve_path(self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_valid_models(self):
        from comfymodal_runtime.cpu_snapshot_models import (
            CpuSnapshotModels,
            ModelRestoreKey,
            ModelFileFact,
        )
        # Create files
        u_path = _create_file(self.temp_dir, "u.safetensors", 100)
        c_path = _create_file(self.temp_dir, "c.safetensors", 200)
        st_u = os.stat(u_path)
        st_c = os.stat(c_path)
        mtime_u = _get_stored_mtime(u_path)
        mtime_c = _get_stored_mtime(c_path)

        key = ModelRestoreKey(
            unet_identity="u.safetensors",
            clip_identity="c.safetensors",
            vae_identity="",
            clip_type="sd",
        )
        spec = {
            "loaders": {
                "unet": [{"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"}],
                "clip": [{"loader_class": "CLIPLoader", "clip_name": "c.safetensors", "type": "sd", "device": "default"}],
                "vae": [],
            },
        }
        facts = (
            ModelFileFact(role="unet", path=u_path, size_bytes=st_u.st_size, mtime_ns=mtime_u),
            ModelFileFact(role="clip1", path=c_path, size_bytes=st_c.st_size, mtime_ns=mtime_c),
        )
        unet_obj = _FakeUNETPatcher()
        clip_obj = _FakeCLIP()
        return CpuSnapshotModels(
            model_key=key,
            model_spec=spec,
            normalized_profile={"mode": "split", "unet": "u.safetensors", "clip1": "c.safetensors", "clip_type": "sd"},
            file_facts=facts,
            unet=unet_obj,
            clip=clip_obj,
        ), key, spec

    # 23. Identity mismatch
    def test_identity_mismatch(self):
        from comfymodal_runtime.cpu_snapshot_models import (
            validate_cpu_snapshot_models,
            ModelRestoreKey,
        )
        models, _, spec = self._make_valid_models()
        bad_key = ModelRestoreKey(
            unet_identity="wrong.safetensors",
            clip_identity="c.safetensors",
            vae_identity="",
            clip_type="sd",
        )
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=bad_key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertFalse(ok)
        self.assertIn("unet identity", reason.lower())

    # 24. Spec mismatch
    def test_spec_mismatch(self):
        from comfymodal_runtime.cpu_snapshot_models import validate_cpu_snapshot_models
        models, key, _ = self._make_valid_models()
        bad_spec = {"loaders": {"unet": [], "clip": [], "vae": []}}
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=bad_spec, resolve_path=self.resolve,
        )
        self.assertFalse(ok)
        self.assertIn("model_spec", reason.lower())

    # 25. File fact validation (path, size, mtime)
    def test_file_fact_missing_path(self):
        from comfymodal_runtime.cpu_snapshot_models import (
            validate_cpu_snapshot_models,
            CpuSnapshotModels,
            ModelRestoreKey,
            ModelFileFact,
        )
        key = ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors",
                              vae_identity="", clip_type="sd")
        spec = {"loaders": {"unet": [{"unet_name": "u.safetensors"}], "clip": [], "vae": []}}
        nonexistent = os.path.join(self.temp_dir, "nope.safetensors")
        facts = (ModelFileFact(role="unet", path=nonexistent, size_bytes=0, mtime_ns=0),)
        models = CpuSnapshotModels(
            model_key=key,
            model_spec=spec,
            normalized_profile={"mode": "split", "unet": "u.safetensors", "clip1": "c.safetensors", "clip_type": "sd"},
            file_facts=facts,
            unet=_FakeUNETPatcher(),
            clip=_FakeCLIP(),
        )
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertFalse(ok)
        self.assertIn("mismatch", reason)

    def test_file_fact_size_mismatch(self):
        from comfymodal_runtime.cpu_snapshot_models import (
            validate_cpu_snapshot_models,
            CpuSnapshotModels,
            ModelRestoreKey,
            ModelFileFact,
        )
        u_path = _create_file(self.temp_dir, "u.safetensors", 100)
        c_path = _create_file(self.temp_dir, "c.safetensors", 200)
        key = ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors",
                              vae_identity="", clip_type="sd")
        spec = {"loaders": {"unet": [{"unet_name": "u.safetensors"}], "clip": [], "vae": []}}
        # Stored size is 50, but actual is 100
        facts = (
            ModelFileFact(role="unet", path=u_path, size_bytes=50, mtime_ns=0),
            ModelFileFact(
                role="clip1",
                path=c_path,
                size_bytes=200,
                mtime_ns=_get_stored_mtime(c_path),
            ),
        )
        models = CpuSnapshotModels(
            model_key=key,
            model_spec=spec,
            normalized_profile={"mode": "split", "unet": "u.safetensors", "clip1": "c.safetensors", "clip_type": "sd"},
            file_facts=facts,
            unet=_FakeUNETPatcher(),
            clip=_FakeCLIP(),
        )
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertFalse(ok)
        self.assertIn("size mismatch", reason)

    # 26. Split config check
    def test_split_config_check(self):
        from comfymodal_runtime.cpu_snapshot_models import (
            validate_cpu_snapshot_models,
            CpuSnapshotModels,
            ModelRestoreKey,
            ModelFileFact,
        )
        u_path = _create_file(self.temp_dir, "u.safetensors", 100)
        c_path = _create_file(self.temp_dir, "c.safetensors", 200)
        key = ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors",
                              vae_identity="", clip_type="sd")
        spec = {"loaders": {"unet": [{"unet_name": "u.safetensors"}], "clip": [], "vae": []}}
        facts = (
            ModelFileFact(role="unet", path=u_path, size_bytes=100, mtime_ns=_get_stored_mtime(u_path)),
            ModelFileFact(role="clip1", path=c_path, size_bytes=200, mtime_ns=_get_stored_mtime(c_path)),
        )
        models = CpuSnapshotModels(
            model_key=key,
            model_spec=spec,
            normalized_profile={"mode": "checkpoint", "unet": "u.safetensors", "clip1": "c.safetensors", "clip_type": "sd"},
            file_facts=facts,
            unet=_FakeUNETPatcher(),
            clip=_FakeCLIP(),
        )
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertFalse(ok)
        self.assertIn("mode", reason.lower())

    # 27. Unet shape invalid
    def test_unet_shape_invalid(self):
        from comfymodal_runtime.cpu_snapshot_models import (
            validate_cpu_snapshot_models,
            CpuSnapshotModels,
            ModelRestoreKey,
            ModelFileFact,
        )
        u_path = _create_file(self.temp_dir, "u.safetensors", 100)
        c_path = _create_file(self.temp_dir, "c.safetensors", 200)
        key = ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors",
                              vae_identity="", clip_type="sd")
        spec = {"loaders": {"unet": [{"unet_name": "u.safetensors"}], "clip": [], "vae": []}}
        facts = (
            ModelFileFact(role="unet", path=u_path, size_bytes=100, mtime_ns=_get_stored_mtime(u_path)),
            ModelFileFact(role="clip1", path=c_path, size_bytes=200, mtime_ns=_get_stored_mtime(c_path)),
        )
        # UNET without model attribute
        unet_obj = object()
        clip_obj = _FakeCLIP()
        models = CpuSnapshotModels(
            model_key=key,
            model_spec=spec,
            normalized_profile={"mode": "split", "unet": "u.safetensors", "clip1": "c.safetensors", "clip_type": "sd"},
            file_facts=facts,
            unet=unet_obj,
            clip=clip_obj,
        )
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertFalse(ok)
        self.assertIn("unet", reason.lower())
        self.assertIn("model", reason.lower())

    # 28. Clip shape invalid (missing patcher)
    def test_clip_shape_invalid(self):
        from comfymodal_runtime.cpu_snapshot_models import (
            validate_cpu_snapshot_models,
            CpuSnapshotModels,
            ModelRestoreKey,
            ModelFileFact,
        )
        u_path = _create_file(self.temp_dir, "u.safetensors", 100)
        c_path = _create_file(self.temp_dir, "c.safetensors", 200)
        key = ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors",
                              vae_identity="", clip_type="sd")
        spec = {"loaders": {"unet": [{"unet_name": "u.safetensors"}], "clip": [], "vae": []}}
        facts = (
            ModelFileFact(role="unet", path=u_path, size_bytes=100, mtime_ns=_get_stored_mtime(u_path)),
            ModelFileFact(role="clip1", path=c_path, size_bytes=200, mtime_ns=_get_stored_mtime(c_path)),
        )
        models = CpuSnapshotModels(
            model_key=key,
            model_spec=spec,
            normalized_profile={"mode": "split", "unet": "u.safetensors", "clip1": "c.safetensors", "clip_type": "sd"},
            file_facts=facts,
            unet=_FakeUNETPatcher(),
            clip=object(),  # not a valid CLIP
        )
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertFalse(ok)
        self.assertIn("clip", reason.lower())

    # 28b. Clip shape invalid (missing tokenizer)
    def test_clip_shape_no_tokenizer(self):
        from comfymodal_runtime.cpu_snapshot_models import (
            validate_cpu_snapshot_models,
            CpuSnapshotModels,
            ModelRestoreKey,
            ModelFileFact,
        )
        u_path = _create_file(self.temp_dir, "u.safetensors", 100)
        c_path = _create_file(self.temp_dir, "c.safetensors", 200)
        key = ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors",
                              vae_identity="", clip_type="sd")
        spec = {"loaders": {"unet": [{"unet_name": "u.safetensors"}], "clip": [], "vae": []}}
        facts = (
            ModelFileFact(role="unet", path=u_path, size_bytes=100, mtime_ns=_get_stored_mtime(u_path)),
            ModelFileFact(role="clip1", path=c_path, size_bytes=200, mtime_ns=_get_stored_mtime(c_path)),
        )
        models = CpuSnapshotModels(
            model_key=key,
            model_spec=spec,
            normalized_profile={"mode": "split", "unet": "u.safetensors", "clip1": "c.safetensors", "clip_type": "sd"},
            file_facts=facts,
            unet=_FakeUNETPatcher(),
            clip=_FakeCLIPNoTokenizer(),
        )
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertFalse(ok)
        self.assertIn("tokenizer", reason.lower())

    # Happy path: success must be (True, 'ok')
    def test_valid_models_success(self):
        from comfymodal_runtime.cpu_snapshot_models import validate_cpu_snapshot_models
        models, key, spec = self._make_valid_models()
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_stable_nonzero_mtime_mismatch_invalidates(self):
        from comfymodal_runtime.cpu_snapshot_models import validate_cpu_snapshot_models
        models, key, spec = self._make_valid_models()
        fact = models.file_facts[0]
        changed_mtime = fact.mtime_ns + 2_000_000_000
        os.utime(fact.path, ns=(changed_mtime, changed_mtime))
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertFalse(ok)
        self.assertIn("mtime", reason.lower())


class TestValidateDeviceSafety(unittest.TestCase):
    """Categories 29-31: CUDA/meta rejection, custom-device allowance."""

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.resolve = _make_resolve_path(self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_base_models(self, unet=None, clip=None):
        from comfymodal_runtime.cpu_snapshot_models import (
            CpuSnapshotModels,
            ModelRestoreKey,
            ModelFileFact,
        )
        u_path = _create_file(self.temp_dir, "u.safetensors", 100)
        c_path = _create_file(self.temp_dir, "c.safetensors", 200)
        key = ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors",
                              vae_identity="", clip_type="sd")
        spec = {"loaders": {"unet": [{"unet_name": "u.safetensors"}], "clip": [], "vae": []}}
        facts = (
            ModelFileFact(role="unet", path=u_path, size_bytes=100, mtime_ns=_get_stored_mtime(u_path)),
            ModelFileFact(role="clip1", path=c_path, size_bytes=200, mtime_ns=_get_stored_mtime(c_path)),
        )
        return CpuSnapshotModels(
            model_key=key,
            model_spec=spec,
            normalized_profile={"mode": "split", "unet": "u.safetensors", "clip1": "c.safetensors", "clip_type": "sd"},
            file_facts=facts,
            unet=unet or _FakeUNETPatcher(),
            clip=clip or _FakeCLIP(),
        ), key, spec

    # 29. CUDA tensors rejected
    def test_cuda_unet_rejected(self):
        from comfymodal_runtime.cpu_snapshot_models import validate_cpu_snapshot_models
        unet_cuda = _FakeUNETPatcher(device="cuda:0")
        models, key, spec = self._make_base_models(unet=unet_cuda)
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertFalse(ok)
        self.assertIn("cuda", reason.lower())

    def test_cuda_clip_rejected(self):
        from comfymodal_runtime.cpu_snapshot_models import validate_cpu_snapshot_models
        clip_cuda = _FakeCLIP(device="cuda:0")
        models, key, spec = self._make_base_models(clip=clip_cuda)
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertFalse(ok)
        self.assertIn("cuda", reason.lower())

    # 30. Meta tensors rejected
    def test_meta_unet_rejected(self):
        from comfymodal_runtime.cpu_snapshot_models import validate_cpu_snapshot_models
        # Create a fake module with meta tensor
        meta_module = _FakeModule("meta")
        unet_meta = _FakeUNETPatcher()
        unet_meta.model = meta_module
        unet_meta.load_device = "meta"
        models, key, spec = self._make_base_models(unet=unet_meta)
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertFalse(ok)
        self.assertIn("meta", reason.lower())

    # 31. Custom device (xpu) allowed
    def test_custom_device_unet_allowed(self):
        from comfymodal_runtime.cpu_snapshot_models import validate_cpu_snapshot_models
        unet_xpu = _FakeUNETPatcher(device="xpu")
        models, key, spec = self._make_base_models(unet=unet_xpu)
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_custom_device_clip_allowed(self):
        from comfymodal_runtime.cpu_snapshot_models import validate_cpu_snapshot_models
        clip_xpu = _FakeCLIP(device="xpu")
        models, key, spec = self._make_base_models(clip=clip_xpu)
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    # Patcher-model-only CLIP (no cond_stage_model) still valid
    def test_clip_patcher_model_fallback(self):
        from comfymodal_runtime.cpu_snapshot_models import validate_cpu_snapshot_models
        clip_pm = _FakeCLIPPatcherModel()
        models, key, spec = self._make_base_models(clip=clip_pm)
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=key, expected_spec=spec, resolve_path=self.resolve,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")


class TestRetarget(unittest.TestCase):
    """Categories 32-37: retarget_cpu_snapshot_models."""

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.resolve = _make_resolve_path(self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_models(self, unet=None, clip=None):
        from comfymodal_runtime.cpu_snapshot_models import (
            CpuSnapshotModels,
            ModelRestoreKey,
            ModelFileFact,
        )
        u_path = _create_file(self.temp_dir, "u.safetensors", 100)
        c_path = _create_file(self.temp_dir, "c.safetensors", 200)
        key = ModelRestoreKey(unet_identity="u.safetensors", clip_identity="c.safetensors",
                              vae_identity="", clip_type="sd")
        spec = {"loaders": {"unet": [{"unet_name": "u.safetensors"}], "clip": [], "vae": []}}
        facts = (
            ModelFileFact(role="unet", path=u_path, size_bytes=100, mtime_ns=_get_stored_mtime(u_path)),
            ModelFileFact(role="clip1", path=c_path, size_bytes=200, mtime_ns=_get_stored_mtime(c_path)),
        )
        return CpuSnapshotModels(
            model_key=key,
            model_spec=spec,
            normalized_profile={"mode": "split", "unet": "u.safetensors", "clip1": "c.safetensors", "clip_type": "sd"},
            file_facts=facts,
            unet=unet or _FakeUNETPatcher(device="cpu"),
            clip=clip or _FakeCLIP(device="cpu"),
        )

    # 33. Done with model_management
    def test_retarget_done(self):
        from comfymodal_runtime.cpu_snapshot_models import retarget_cpu_snapshot_models
        models = self._make_models()
        ok, reason = retarget_cpu_snapshot_models(models, model_management=_FakeModelManagement)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    # 34. Unsupported UNET shape
    def test_unsupported_unet_shape(self):
        from comfymodal_runtime.cpu_snapshot_models import retarget_cpu_snapshot_models
        bad_unet = object()
        models = self._make_models(unet=bad_unet)
        ok, reason = retarget_cpu_snapshot_models(models, model_management=_FakeModelManagement)
        self.assertFalse(ok)
        self.assertEqual(reason, "unsupported_unet_shape")

    # 35. Unsupported CLIP shape
    def test_unsupported_clip_shape(self):
        from comfymodal_runtime.cpu_snapshot_models import retarget_cpu_snapshot_models
        bad_clip = object()
        models = self._make_models(clip=bad_clip)
        ok, reason = retarget_cpu_snapshot_models(models, model_management=_FakeModelManagement)
        self.assertFalse(ok)
        self.assertEqual(reason, "unsupported_clip_shape")

    # 36. Missing model_management function
    def test_missing_model_management_function(self):
        from comfymodal_runtime.cpu_snapshot_models import retarget_cpu_snapshot_models
        models = self._make_models()
        ok, reason = retarget_cpu_snapshot_models(models, model_management=_FakeModelManagementMissingFunc)
        self.assertFalse(ok)
        self.assertIn("missing_model_management_function", reason)

    # 37. Only patcher device attributes changed (no .to or load_models_gpu)
    def test_only_device_attrs_changed(self):
        from comfymodal_runtime.cpu_snapshot_models import retarget_cpu_snapshot_models
        unet_obj = _FakeUNETPatcher(device="cpu")
        clip_obj = _FakeCLIP(device="cpu")
        models = self._make_models(unet=unet_obj, clip=clip_obj)
        ok, reason = retarget_cpu_snapshot_models(models, model_management=_FakeModelManagement)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        # Verify device attributes were updated correctly
        self.assertEqual(unet_obj.load_device, "cuda:0")
        self.assertEqual(unet_obj.offload_device, "cpu")
        self.assertEqual(clip_obj.patcher.load_device, "cuda:0")
        self.assertEqual(clip_obj.patcher.offload_device, "cpu")

    # No partial assignment: all checks pass before assignments
    def test_no_partial_assignment(self):
        from comfymodal_runtime.cpu_snapshot_models import retarget_cpu_snapshot_models
        unet_obj = _FakeUNETPatcher(device="cpu")
        clip_obj = _FakeCLIP(device="cpu")
        models = self._make_models(unet=unet_obj, clip=clip_obj)
        # Capture initial device values
        orig_unet_load = unet_obj.load_device
        orig_unet_offload = unet_obj.offload_device
        orig_clip_load = clip_obj.patcher.load_device
        orig_clip_offload = clip_obj.patcher.offload_device

        # Use a model_management that fails the function check on first function
        class BadMgmt:
            pass

        ok, reason = retarget_cpu_snapshot_models(models, model_management=BadMgmt)
        self.assertFalse(ok)
        # Devices should be unchanged
        self.assertEqual(unet_obj.load_device, orig_unet_load)
        self.assertEqual(unet_obj.offload_device, orig_unet_offload)
        self.assertEqual(clip_obj.patcher.load_device, orig_clip_load)
        self.assertEqual(clip_obj.patcher.offload_device, orig_clip_offload)


class TestDataclassDefaults(unittest.TestCase):
    """Minimal coverage for CpuSnapshotModels and ModelFileFact."""

    def test_model_file_fact_frozen(self):
        from comfymodal_runtime.cpu_snapshot_models import ModelFileFact
        fact = ModelFileFact(role="unet", path="/tmp/x", size_bytes=100, mtime_ns=12345)
        self.assertEqual(fact.role, "unet")
        self.assertEqual(fact.path, "/tmp/x")
        self.assertEqual(fact.size_bytes, 100)
        self.assertEqual(fact.mtime_ns, 12345)
        with self.assertRaises(AttributeError):
            fact.role = "clip1"  # frozen

    def test_cpu_snapshot_models_defaults(self):
        from comfymodal_runtime.cpu_snapshot_models import (
            CpuSnapshotModels,
            ModelRestoreKey,
        )
        key = ModelRestoreKey()
        spec = {}
        models = CpuSnapshotModels(
            model_key=key,
            model_spec=spec,
            normalized_profile={},
            file_facts=(),
        )
        self.assertIsNone(models.unet)
        self.assertIsNone(models.clip)
        self.assertEqual(models.load_timings_ms, {})


if __name__ == "__main__":
    unittest.main()
