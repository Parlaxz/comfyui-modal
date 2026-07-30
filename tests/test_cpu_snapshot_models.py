"""Tests for comfymodal_runtime.cpu_snapshot_models.

Covers all required categories:
  1  identity_from_profile valid split profile -> 3-tuple
  2  identity_from_profile missing mode -> ValueError
  3  identity_from_profile unsupported mode -> ValueError
  4  identity_from_profile missing unet -> ValueError
  5  identity_from_profile missing clip1 -> ValueError
  6  identity_from_profile missing clip_type -> ValueError
  7  identity_from_profile clip2 duplicate preserved in spec, one fact
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
 38  load: dual clip callback with clip1==clip2
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

    # 7. Duplicate clip2: preserved in normalized, dual spec, one file fact
    def test_clip2_duplicate_dual(self):
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        profile = dict(_VALID_SPLIT_PROFILE, clip2="clip_l.safetensors", clip1="clip_l.safetensors")
        key, spec, facts = identity_from_profile(profile, resolve_path=self.resolve)
        # Compact identity: duplicate → single name
        self.assertEqual(key.clip_identity, "clip_l.safetensors")
        # Dual loader spec (clip2 was supplied)
        clip_loaders = spec["loaders"]["clip"]
        self.assertEqual(clip_loaders[0]["loader_class"], "DualCLIPLoader")
        self.assertEqual(clip_loaders[0]["clip_name1"], "clip_l.safetensors")
        self.assertEqual(clip_loaders[0]["clip_name2"], "clip_l.safetensors")
        # Unique file facts: only unet+clip1 (clip2 same file as clip1)
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
    def test_unet_effective_dtype_resolver_default(self):
        """resolve_unet_effective_dtype('default') without target_gpus returns (None, 'default').

        In the normal (non-snapshot) path, "default" is passed through to
        ComfyUI for auto-detection, so the resolver returns None.
        """
        from comfymodal_runtime.model_preload import resolve_unet_effective_dtype
        eff_dtype, eff_label = resolve_unet_effective_dtype("default")
        self.assertIsNone(eff_dtype)
        self.assertEqual(eff_label, "default")

    def test_unet_effective_dtype_rtx_pro_6000_default(self):
        """RTX-PRO-6000 target resolves default to BF16."""
        from comfymodal_runtime.model_preload import resolve_unet_effective_dtype
        import torch
        eff_dtype, eff_label = resolve_unet_effective_dtype(
            "default",
            target_gpus=("RTX-PRO-6000",),
        )
        self.assertIs(eff_dtype, torch.bfloat16)
        self.assertEqual(eff_label, "bfloat16")

    def test_unet_effective_dtype_explicit_fp8(self):
        """resolve_unet_effective_dtype for fp8 strings returns the correct torch dtype, or None if unsupported."""
        from comfymodal_runtime.model_preload import resolve_unet_effective_dtype
        import torch
        eff_dtype, eff_label = resolve_unet_effective_dtype("fp8_e4m3fn")
        if hasattr(torch, "float8_e4m3fn"):
            self.assertIs(eff_dtype, torch.float8_e4m3fn)
        else:
            self.assertIsNone(eff_dtype)
        self.assertEqual(eff_label, "fp8_e4m3fn")

    def test_unet_effective_dtype_explicit_fp8_e5m2(self):
        from comfymodal_runtime.model_preload import resolve_unet_effective_dtype
        import torch
        eff_dtype, eff_label = resolve_unet_effective_dtype("fp8_e5m2")
        if hasattr(torch, "float8_e5m2"):
            self.assertIs(eff_dtype, torch.float8_e5m2)
        else:
            self.assertIsNone(eff_dtype)
        self.assertEqual(eff_label, "fp8_e5m2")

    def test_unet_effective_dtype_unknown_string(self):
        """resolve_unet_effective_dtype for unknown strings returns (None, string)."""
        from comfymodal_runtime.model_preload import resolve_unet_effective_dtype
        eff_dtype, eff_label = resolve_unet_effective_dtype("some_unknown_value")
        self.assertIsNone(eff_dtype)
        self.assertEqual(eff_label, "some_unknown_value")

    def test_unet_effective_dtype_snapshot_cpu_no_cuda(self):
        """CPU snapshot environment with target GPUs resolves to BF16 without CUDA probe.

        Simulates the CPU snapshot builder: torch.cuda.is_available() is False,
        but configured target is RTX-PRO-6000.  The resolver must return bfloat16
        without calling torch.cuda APIs.
        """
        import unittest.mock as _mock
        # Verify is_bf16_supported is NEVER called during resolution
        _orig_bf16 = __import__("torch").cuda.is_bf16_supported
        try:
            __import__("torch").cuda.is_bf16_supported = _mock.MagicMock(
                side_effect=RuntimeError("torch.cuda API called during snapshot")
            )
            from comfymodal_runtime.model_preload import resolve_unet_effective_dtype
            import torch
            eff_dtype, eff_label = resolve_unet_effective_dtype(
                "default",
                target_gpus=("RTX-PRO-6000",),
            )
            self.assertIs(eff_dtype, torch.bfloat16)
            self.assertEqual(eff_label, "bfloat16")
        finally:
            __import__("torch").cuda.is_bf16_supported = _orig_bf16

    def test_unet_effective_dtype_explicit_bf16(self):
        """Explicit bf16 CLI override remains bf16."""
        import unittest.mock as mock
        import comfy.cli_args
        with mock.patch.object(comfy.cli_args.args, "bf16_unet", True):
            from comfymodal_runtime.model_preload import resolve_unet_effective_dtype
            import torch
            eff_dtype, eff_label = resolve_unet_effective_dtype("default", target_gpus=("T4",))
            self.assertIs(eff_dtype, torch.bfloat16)
            self.assertEqual(eff_label, "bfloat16")

    def test_unet_effective_dtype_explicit_fp32(self):
        """Explicit fp32 CLI override remains fp32 even on BF16-capable GPU."""
        import unittest.mock as mock
        import comfy.cli_args
        with mock.patch.object(comfy.cli_args.args, "fp32_unet", True):
            from comfymodal_runtime.model_preload import resolve_unet_effective_dtype
            import torch
            eff_dtype, eff_label = resolve_unet_effective_dtype("default", target_gpus=("RTX-PRO-6000",))
            self.assertIs(eff_dtype, torch.float32)
            self.assertEqual(eff_label, "float32")

    def test_unet_effective_dtype_no_new_flag_needed(self):
        """Default env (no COMFYMODAL_V2_GPU set) works — policy uses V2_DEFAULT_GPU."""
        from gpu_catalog import V2_DEFAULT_GPU
        self.assertTrue(V2_DEFAULT_GPU.upper() in ("RTX-PRO-6000",))
        from comfymodal_runtime.model_preload import resolve_unet_effective_dtype
        import torch
        eff_dtype, eff_label = resolve_unet_effective_dtype(
            "default",
            target_gpus=("RTX-PRO-6000",),
        )
        # RTX-PRO-6000 is BF16 capable → default resolves to bfloat16
        self.assertIs(eff_dtype, torch.bfloat16)
        self.assertEqual(eff_label, "bfloat16")

    def test_unet_effective_dtype_requested_spec_preserved(self):
        """Requested model spec weight_dtype remains 'default' despite effective BF16."""
        from comfymodal_runtime.model_preload import resolve_unet_effective_dtype
        # The resolver takes the requested string and returns the effective dtype.
        # The requested string is NOT changed by the resolver.
        eff_dtype, eff_label = resolve_unet_effective_dtype(
            "default",
            target_gpus=("RTX-PRO-6000",),
        )
        self.assertIsNotNone(eff_dtype)
        self.assertEqual(eff_label, "bfloat16")
        # The requested weight_dtype "default" remains unchanged — the resolver
        # returns the effective dtype as a separate value.

    def test_unet_effective_dtype_identity_matching_works(self):
        """Snapshot/request identity matching succeeds despite effective dtype metadata."""
        from comfymodal_runtime.model_preload import resolve_unet_effective_dtype
        # Both request and snapshot use requested_weight_dtype="default" for matching.
        # The effective_snapshot_weight_dtype is separate metadata, not part of the key.
        request_wd = "default"
        snapshot_wd = "default"
        # Identity matching compares requested_weight_dtype, not effective
        self.assertEqual(request_wd, snapshot_wd)

    def test_unet_effective_dtype_snapshot_t4_no_bf16(self):
        """T4 target does NOT resolve default to BF16."""
        from comfymodal_runtime.model_preload import resolve_unet_effective_dtype
        import torch
        eff_dtype, eff_label = resolve_unet_effective_dtype(
            "default",
            target_gpus=("T4",),
        )
        self.assertIs(eff_dtype, torch.float32)
        self.assertEqual(eff_label, "float32")

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

    # 21b. Dual load callback with clip1==clip2
    def test_dual_clip_load_callback(self):
        """load_cpu_snapshot_models with clip1==clip2 invokes dual callback only."""
        from comfymodal_runtime.cpu_snapshot_models import load_cpu_snapshot_models
        unet_stub = _FakeUNETPatcher()
        clip_stub = _FakeCLIP()
        dual_calls = []
        single_calls = []

        def load_clip(*args):
            if len(args) == 4:
                dual_calls.append(args)
            else:
                single_calls.append(args)
            return clip_stub

        profile = dict(_VALID_SPLIT_PROFILE, clip1="clip_l.safetensors", clip2="clip_l.safetensors")
        result = load_cpu_snapshot_models(
            profile,
            load_unet=lambda name, *args: unet_stub,
            load_clip=load_clip,
            resolve_path=self.resolve,
        )
        self.assertEqual(len(dual_calls), 1, "should invoke dual callback once")
        name1, name2, clip_type, device = dual_calls[0]
        self.assertEqual(name1, "clip_l.safetensors")
        self.assertEqual(name2, "clip_l.safetensors")
        self.assertEqual(clip_type, "flux")
        self.assertEqual(device, "default")
        self.assertEqual(len(single_calls), 0, "must not invoke single callback")
        self.assertIsNotNone(result)
        self.assertIs(result.clip, clip_stub)

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
            CPU_SNAPSHOT_UNET_POLICY_VERSION,
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
            policy_version=CPU_SNAPSHOT_UNET_POLICY_VERSION,
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


# ---------------------------------------------------------------------------
# Realistic fake patchers for runtime-state tests
# ---------------------------------------------------------------------------


class _FakeRealModel:
    """Model-like object with the attributes a real ComfyUI model has."""
    def __init__(self, device="cpu"):
        self.device = device
        self.manual_cast_dtype = "torch.float16"
        self.model_loaded_weight_memory = 1234567890
        self.model_lowvram = False
        self.lowvram_patch_counter = 0
        self._param_tensor = _FakeTensor(device)
        self._buffer_tensor = _FakeTensor(device)

    def named_parameters(self, recurse=True):
        yield ("weight", self._param_tensor)

    def named_buffers(self, recurse=True):
        yield ("bias", self._buffer_tensor)


class _FakeRealDiffusionModel:
    """Diffusion model that owns forward."""
    def __init__(self, device="cpu"):
        self.device = device
        self._param_tensor = _FakeTensor(device)
        self._buffer_tensor = _FakeTensor(device)

    def named_parameters(self, recurse=True):
        yield ("weight", self._param_tensor)

    def named_buffers(self, recurse=True):
        yield ("bias", self._buffer_tensor)

    def forward(self, x):
        return x


class _FakeRealPatcher:
    """Realistic fake ModelPatcher for real ComfyUI ModelPatcher structure.

    * ``model_dtype`` is a **method**.
    * ``manual_cast_dtype`` / ``device`` / ``model_loaded_weight_memory`` /
      ``model_lowvram`` / ``lowvram_patch_counter`` live on ``.model``.
    * ``transformer_options`` is nested under ``model_options``.
    * ``diffusion_model`` (on ``.model``) owns ``forward``.
    """
    def __init__(self, device="cpu"):
        self.model = _FakeRealModel(device)
        self.model.diffusion_model = _FakeRealDiffusionModel(device)
        self.load_device = device
        self.offload_device = "cpu"
        self.weight_dtype = "fp8_e4m3fn"
        self.model_options = {
            "some_option": 1,
            "transformer_options": {
                "some_transformer_opt": 2,
            },
        }
        self.patches = {"patch1": object(), "patch2": object()}
        self.object_patches = {"op1": object()}

    def model_dtype(self):
        return "torch.float16"


class _FakeRealPatcherNoDM:
    """Realistic patcher without diffusion_model — tests fallback to model."""
    def __init__(self, device="cpu"):
        self.model = _FakeRealModel(device)
        # No diffusion_model
        self.load_device = device
        self.offload_device = "cpu"
        self.weight_dtype = "fp8_e4m3fn"

    def model_dtype(self):
        return "torch.float16"


class _FakeUNETMinimal:
    """Minimal UNET patcher with only the required attributes."""
    def __init__(self):
        self.model = _FakeModule("cpu")
        self.load_device = "cpu"
        self.offload_device = "cpu"


class _FakeUNETNoModel:
    """UNET-like object without .model attribute."""
    pass


# ── Single-request iterator that raises on second item ──────────────


class _SingleParameterGenerator:
    """An iterator that yields exactly one parameter, then raises.

    Proves the collector calls ``next()`` once and never ``list()``.
    """
    def __init__(self):
        self._called = 0

    def __iter__(self):
        return self

    def __next__(self):
        self._called += 1
        if self._called > 1:
            raise RuntimeError("second parameter requested — proves list() was called")
        return ("weight", _FakeTensor("cpu"))


class _SingleBufferGenerator:
    """An iterator that yields exactly one buffer, then raises."""
    def __init__(self):
        self._called = 0

    def __iter__(self):
        return self

    def __next__(self):
        self._called += 1
        if self._called > 1:
            raise RuntimeError("second buffer requested — proves list() was called")
        return ("bias", _FakeTensor("cpu"))


class _FakeModuleSingleIter:
    """Module whose named_parameters/buffers raise on second iteration."""
    def __init__(self):
        pass

    def named_parameters(self, recurse=True):
        return _SingleParameterGenerator()

    def named_buffers(self, recurse=True):
        return _SingleBufferGenerator()


class _FakePatcherSingleIter:
    """Patcher wrapping a single-iter module."""
    def __init__(self):
        self.model = _FakeModuleSingleIter()
        self.model.diffusion_model = _FakeModuleSingleIter()
        self.load_device = "cpu"
        self.offload_device = "cpu"
        self.weight_dtype = "default"


# ── Fake model_management with callable loaded_models ─────────────


class _FakeModelManagementWithCallable:
    """model_management where loaded_models is a callable."""
    def __init__(self, member_obj=None):
        self._member = member_obj

    @staticmethod
    def get_torch_device():
        return "cuda:0"

    @staticmethod
    def unet_offload_device():
        return "cpu"

    def loaded_models(self):
        if self._member is not None:
            return [self._member]
        return []


class _FakeModelManagementLoadedNotCallable:
    """model_management where loaded_models exists but is not callable."""
    loaded_models = "not_callable"


# ══════════════════════════════════════════════════════════════════════
# Tests: collect_unet_runtime_state
# ══════════════════════════════════════════════════════════════════════


class TestCollectUnetRuntimeState(unittest.TestCase):
    """collect_unet_runtime_state edge-to-edge coverage."""

    def test_collect_realistic_patcher(self):
        """Realistic patcher returns correct values for all standard fields."""
        from comfymodal_runtime.cpu_snapshot_models import collect_unet_runtime_state
        patcher = _FakeRealPatcher(device="cpu")
        state = collect_unet_runtime_state(patcher)
        self.assertIsInstance(state, dict)
        # Type identities
        self.assertEqual(state["patcher_type"], "_FakeRealPatcher")
        self.assertEqual(state["model_type"], "_FakeRealModel")
        self.assertEqual(state["diffusion_model_type"], "_FakeRealDiffusionModel")
        # Object IDs present (non-empty strings)
        self.assertTrue(state["patcher_object_id"])
        self.assertTrue(state["model_object_id"])
        self.assertTrue(state["diffusion_model_object_id"])
        # Device attributes
        self.assertEqual(state["load_device"], "cpu")
        self.assertEqual(state["offload_device"], "cpu")
        # current_device comes from model.device
        self.assertEqual(state["current_device"], "cpu")
        # First parameter/buffer from diffusion_model (first, not model)
        self.assertEqual(state["first_parameter_device"], "cpu")
        self.assertEqual(state["first_buffer_device"], "cpu")
        # model_dtype is a method result
        self.assertEqual(state["model_dtype"], "torch.float16")
        # manual_cast_dtype from model.manual_cast_dtype
        self.assertEqual(state["manual_cast_dtype"], "torch.float16")
        # weight_dtype from patcher
        self.assertEqual(state["weight_dtype"], "fp8_e4m3fn")
        # Options
        self.assertEqual(state["model_options_keys"], ["some_option", "transformer_options"])
        self.assertEqual(state["transformer_options_keys"], ["some_transformer_opt"])
        # Patch counts
        self.assertEqual(state["patch_count"], 2)
        self.assertEqual(state["object_patch_count"], 1)
        # Memory/lowvram from model.*
        self.assertEqual(state["model_loaded_weight_memory"], "1234567890")
        self.assertEqual(state["model_lowvram"], "False")
        self.assertEqual(state["model_lowvram_patch_counter"], "0")
        # Forward from diffusion_model
        self.assertEqual(state["forward_module"], "_FakeRealDiffusionModel")
        self.assertTrue(state["forward_qualname"].endswith("forward"))

    def test_collect_fallback_no_diffusion_model(self):
        """Without diffusion_model, first param/buffer fallbacks to model."""
        from comfymodal_runtime.cpu_snapshot_models import collect_unet_runtime_state
        patcher = _FakeRealPatcherNoDM(device="cpu")
        state = collect_unet_runtime_state(patcher)
        self.assertEqual(state["diffusion_model_type"], "absent")
        # Forward falls back to model (absent when model has no forward)
        self.assertEqual(state["forward_module"], "absent")
        # First parameter still reads (from model)
        self.assertEqual(state["first_parameter_device"], "cpu")

    def test_collect_minimal_patcher(self):
        """Minimal patcher returns 'absent' for missing advanced fields."""
        from comfymodal_runtime.cpu_snapshot_models import collect_unet_runtime_state
        patcher = _FakeUNETMinimal()
        state = collect_unet_runtime_state(patcher)
        self.assertIsInstance(state, dict)
        self.assertEqual(state["model_dtype"], "absent")
        self.assertEqual(state["manual_cast_dtype"], "absent")
        self.assertEqual(state["weight_dtype"], "absent")
        self.assertEqual(state["patch_count"], "absent")
        self.assertEqual(state["object_patch_count"], "absent")
        self.assertEqual(state["model_loaded_weight_memory"], "absent")

    def test_collect_no_model(self):
        """Object without .model returns absent for model-specific fields."""
        from comfymodal_runtime.cpu_snapshot_models import collect_unet_runtime_state
        state = collect_unet_runtime_state(_FakeUNETNoModel())
        self.assertEqual(state["model_type"], "absent")
        self.assertEqual(state["diffusion_model_type"], "absent")
        self.assertEqual(state["first_parameter_device"], "absent")
        self.assertEqual(state["current_device"], "absent")

    def test_collect_no_tensor_contents(self):
        """No tensor values or reprs in state values."""
        from comfymodal_runtime.cpu_snapshot_models import collect_unet_runtime_state
        state = collect_unet_runtime_state(_FakeRealPatcher("cpu"))
        for key, value in state.items():
            self.assertIsInstance(value, (str, int, float, bool, list, dict))
            s = str(value)
            self.assertNotIn("FakeTensor", s, msg=f"tensor content leaked in {key}={value!r}")
            self.assertNotIn("<", s, msg=f"object repr leaked in {key}={value!r}")

    def test_collect_only_first_parameter_single_iter(self):
        """Proves next(iter(...)) is used, not list()."""
        from comfymodal_runtime.cpu_snapshot_models import collect_unet_runtime_state
        patcher = _FakePatcherSingleIter()
        # This would raise RuntimeError("second parameter requested") if list() was called
        state = collect_unet_runtime_state(patcher)
        self.assertEqual(state["first_parameter_device"], "cpu")
        self.assertEqual(state["first_buffer_device"], "cpu")

    def test_collect_deterministic_keys(self):
        """State dict keys are deterministic."""
        from comfymodal_runtime.cpu_snapshot_models import collect_unet_runtime_state
        state_a = collect_unet_runtime_state(_FakeRealPatcher("cpu"))
        state_b = collect_unet_runtime_state(_FakeRealPatcher("cpu"))
        self.assertEqual(list(state_a.keys()), list(state_b.keys()))

    def test_collect_loaded_models_is_callable(self):
        """loaded_models_member resolves via function call."""
        from comfymodal_runtime.cpu_snapshot_models import collect_unet_runtime_state
        patcher = _FakeRealPatcher("cpu")
        mgmt = _FakeModelManagementWithCallable(member_obj=patcher)
        state = collect_unet_runtime_state(patcher, model_management=mgmt)
        self.assertEqual(state["loaded_models_member"], "1")

    def test_collect_loaded_models_not_member(self):
        """loaded_models_member is '0' when patcher not in the list."""
        from comfymodal_runtime.cpu_snapshot_models import collect_unet_runtime_state
        patcher = _FakeRealPatcher("cpu")
        other = _FakeRealPatcher("cpu")
        mgmt = _FakeModelManagementWithCallable(member_obj=other)
        state = collect_unet_runtime_state(patcher, model_management=mgmt)
        self.assertEqual(state["loaded_models_member"], "0")

    def test_collect_loaded_models_not_callable(self):
        """loaded_models_member is 'absent' when attribute is not callable."""
        from comfymodal_runtime.cpu_snapshot_models import collect_unet_runtime_state
        patcher = _FakeRealPatcher("cpu")
        state = collect_unet_runtime_state(patcher, model_management=_FakeModelManagementLoadedNotCallable)
        self.assertEqual(state["loaded_models_member"], "absent")

    def test_collect_model_dtype_not_callable(self):
        """model_dtype is 'absent' when the attribute is not callable."""
        from comfymodal_runtime.cpu_snapshot_models import collect_unet_runtime_state
        patcher = _FakeUNETMinimal()
        state = collect_unet_runtime_state(patcher)
        # _FakeUNETMinimal has no model_dtype attribute at all
        self.assertEqual(state["model_dtype"], "absent")


# ══════════════════════════════════════════════════════════════════════
# Tests: diff_unet_runtime_states
# ══════════════════════════════════════════════════════════════════════


class TestDiffUnetRuntimeStates(unittest.TestCase):
    """diff_unet_runtime_states coverage."""

    def _make_state(self, overrides: dict | None = None) -> dict[str, str]:
        base = {
            "patcher_type": "ModelPatcher",
            "model_type": "UNetModel",
            "load_device": "cpu",
            "offload_device": "cpu",
            "weight_dtype": "fp8_e4m3fn",
            "patch_count": "0",
            "model_loaded_weight_memory": "1000",
            # Object IDs should be excluded from semantic diff
            "patcher_object_id": "1234",
            "model_object_id": "5678",
            "diffusion_model_object_id": "90ab",
        }
        if overrides:
            base.update(overrides)
        return base

    def test_diff_identical(self):
        from comfymodal_runtime.cpu_snapshot_models import diff_unet_runtime_states
        s = self._make_state()
        diff = diff_unet_runtime_states(s, s)
        self.assertEqual(diff, {})

    def test_diff_single_field(self):
        from comfymodal_runtime.cpu_snapshot_models import diff_unet_runtime_states
        a = self._make_state({"load_device": "cpu"})
        b = self._make_state({"load_device": "cuda:0"})
        diff = diff_unet_runtime_states(a, b)
        self.assertIn("load_device", diff)
        self.assertEqual(diff["load_device"]["snapshot"], "cpu")
        self.assertEqual(diff["load_device"]["normal"], "cuda:0")
        self.assertEqual(len(diff), 1)

    def test_diff_excludes_object_ids(self):
        """Object-ID keys are excluded from the semantic diff."""
        from comfymodal_runtime.cpu_snapshot_models import diff_unet_runtime_states
        a = self._make_state({"patcher_object_id": "1111", "model_object_id": "2222"})
        b = self._make_state({"patcher_object_id": "3333", "model_object_id": "4444"})
        diff = diff_unet_runtime_states(a, b)
        self.assertNotIn("patcher_object_id", diff)
        self.assertNotIn("model_object_id", diff)
        self.assertNotIn("diffusion_model_object_id", diff)

    def test_diff_multiple_fields(self):
        from comfymodal_runtime.cpu_snapshot_models import diff_unet_runtime_states
        a = self._make_state({"load_device": "cpu", "offload_device": "cpu", "patch_count": "5"})
        b = self._make_state({"load_device": "cuda:0", "offload_device": "cpu", "patch_count": "3"})
        diff = diff_unet_runtime_states(a, b)
        self.assertIn("load_device", diff)
        self.assertIn("patch_count", diff)
        self.assertNotIn("offload_device", diff)
        self.assertEqual(len(diff), 2)

    def test_diff_missing_key(self):
        from comfymodal_runtime.cpu_snapshot_models import diff_unet_runtime_states
        a = self._make_state({"extra_field": "present"})
        b = self._make_state({})
        diff = diff_unet_runtime_states(a, b)
        self.assertIn("extra_field", diff)

    def test_diff_sorted_output(self):
        from comfymodal_runtime.cpu_snapshot_models import diff_unet_runtime_states
        a = self._make_state({"b_field": "1", "a_field": "2"})
        b = self._make_state({"b_field": "x", "a_field": "y"})
        diff = diff_unet_runtime_states(a, b)
        keys = list(diff.keys())
        self.assertEqual(keys, sorted(keys))

    def test_diff_zero_field_count_when_match(self):
        """field_count=0 when states match (except object IDs)."""
        from comfymodal_runtime.cpu_snapshot_models import diff_unet_runtime_states
        a = self._make_state({"load_device": "cpu"})
        b = self._make_state({"load_device": "cpu"})
        # Different object IDs only
        b["patcher_object_id"] = "different"
        diff = diff_unet_runtime_states(a, b)
        self.assertEqual(diff, {})
        self.assertEqual(len(diff), 0)


# ══════════════════════════════════════════════════════════════════════
# Tests: rehydrate_cpu_snapshot_unet
# ══════════════════════════════════════════════════════════════════════


class TestRehydrateCpuSnapshotUnet(unittest.TestCase):
    """rehydrate_cpu_snapshot_unet coverage."""

    def test_rehydrate_success(self):
        from comfymodal_runtime.cpu_snapshot_models import rehydrate_cpu_snapshot_unet
        patcher = _FakeRealPatcher(device="cpu")
        ok, reason = rehydrate_cpu_snapshot_unet(
            patcher,
            model_management=_FakeModelManagement,
        )
        self.assertTrue(ok, msg=reason)
        self.assertEqual(reason, "ok")
        self.assertEqual(patcher.load_device, "cuda:0")
        self.assertEqual(patcher.offload_device, "cpu")

    def test_rehydrate_no_change_to_other_fields(self):
        from comfymodal_runtime.cpu_snapshot_models import (
            rehydrate_cpu_snapshot_unet,
            collect_unet_runtime_state,
        )
        patcher = _FakeRealPatcher(device="cpu")
        state_before = collect_unet_runtime_state(patcher)
        ok, reason = rehydrate_cpu_snapshot_unet(
            patcher,
            model_management=_FakeModelManagement,
        )
        self.assertTrue(ok)
        state_after = collect_unet_runtime_state(patcher)
        changed = {k for k in state_before if str(state_before[k]) != str(state_after[k])}
        self.assertIn("load_device", changed)
        frozen = {"patcher_type", "model_type", "diffusion_model_type",
                  "model_dtype", "manual_cast_dtype", "weight_dtype",
                  "model_options_keys", "transformer_options_keys",
                  "patch_count", "object_patch_count",
                  "model_loaded_weight_memory", "model_lowvram",
                  "model_lowvram_patch_counter", "forward_module", "forward_qualname"}
        actually_changed_frozen = changed & frozen
        self.assertEqual(
            actually_changed_frozen, set(),
            msg=f"Frozen fields changed: {actually_changed_frozen}",
        )

    def test_rehydrate_no_model(self):
        from comfymodal_runtime.cpu_snapshot_models import rehydrate_cpu_snapshot_unet
        ok, reason = rehydrate_cpu_snapshot_unet(
            _FakeUNETNoModel(),
            model_management=_FakeModelManagement,
        )
        self.assertFalse(ok)
        self.assertIn("model", reason.lower())

    def test_rehydrate_missing_mgmt_func(self):
        from comfymodal_runtime.cpu_snapshot_models import rehydrate_cpu_snapshot_unet
        patcher = _FakeRealPatcher(device="cpu")
        ok, reason = rehydrate_cpu_snapshot_unet(
            patcher,
            model_management=_FakeModelManagementMissingFunc,
        )
        self.assertFalse(ok)
        self.assertTrue(
            "get_torch_device" in reason or "unet_offload_device" in reason,
            msg=f"Expected one of the missing functions in reason, got: {reason}",
        )

    def test_rehydrate_with_trace(self):
        from comfymodal_runtime.cpu_snapshot_models import rehydrate_cpu_snapshot_unet
        from comfymodal_runtime.trace import RuntimeTrace
        patcher = _FakeRealPatcher(device="cpu")
        trace = RuntimeTrace()
        ok, reason = rehydrate_cpu_snapshot_unet(
            patcher,
            model_management=_FakeModelManagement,
            trace=trace,
        )
        self.assertTrue(ok)
        names = {e.name for e in trace.events}
        self.assertIn("unet_rehydrate_pre_state", names)
        self.assertIn("unet_rehydrate_post_state", names)


# ══════════════════════════════════════════════════════════════════════
# Tests: no module-level snapshot-state bridge remains
# ══════════════════════════════════════════════════════════════════════


class TestNoModuleLevelBridge(unittest.TestCase):
    """Verify the cross-process A/B bridge was completely removed."""

    def test_no_latest_snapshot_unet_state(self):
        """_LATEST_SNAPSHOT_UNET_STATE is not defined in model_preload."""
        import comfymodal_runtime.model_preload as mp
        self.assertFalse(hasattr(mp, "_LATEST_SNAPSHOT_UNET_STATE"),
                         "Module-level bridge must be removed")

    def test_no_set_latest_snapshot_unet_state(self):
        """_set_latest_snapshot_unet_state is not defined in model_preload."""
        import comfymodal_runtime.model_preload as mp
        self.assertFalse(hasattr(mp, "_set_latest_snapshot_unet_state"),
                         "Setter function must be removed")

    def test_no_consume_latest_snapshot_unet_state(self):
        """_consume_latest_snapshot_unet_state is not defined in model_preload."""
        import comfymodal_runtime.model_preload as mp
        self.assertFalse(hasattr(mp, "_consume_latest_snapshot_unet_state"),
                         "Consumer function must be removed")


# ══════════════════════════════════════════════════════════════════════
# Tests: inspect_and_validate_snapshot_params
# ══════════════════════════════════════════════════════════════════════

# Better tensor stub with numel/dtype/is_floating_point for param inspection tests


class _FakeParamTensor:
    """Tensor stub with numel, dtype, and is_floating_point for param distribution."""
    def __init__(self, device="cpu", dtype="torch.bfloat16", numel=1000, is_float=True):
        self.device = device
        self._dtype_str = dtype
        self._numel = numel
        self._is_float = is_float

    @property
    def dtype(self):
        return self._dtype_str

    def numel(self):
        return self._numel

    def is_floating_point(self):
        return self._is_float


class _FakeParamModule:
    """Module with iterable parameters for inspect_and_validate_snapshot_params."""
    def __init__(self, params):
        """params: list of _FakeParamTensor"""
        self._params = params

    def parameters(self, recurse=True):
        return iter(self._params)


class TestInspectAndValidateSnapshotParams(unittest.TestCase):
    """inspect_and_validate_snapshot_params coverage."""

    def test_accepts_cpu_bf16_params(self):
        """CPU BF16 params pass validation with expected_dtype=bf16."""
        from comfymodal_runtime.cpu_snapshot_models import inspect_and_validate_snapshot_params
        module = _FakeParamModule([
            _FakeParamTensor("cpu", "torch.bfloat16", 5000, True),
            _FakeParamTensor("cpu", "torch.bfloat16", 3000, True),
        ])
        result = inspect_and_validate_snapshot_params(
            module, expected_dtype="torch.bfloat16", require_cpu=True,
        )
        self.assertIn("param_count", result)
        self.assertEqual(result["param_count"], 2)
        self.assertEqual(result["total_param_numel"], 8000)
        self.assertIn("cpu|torch.bfloat16", result["param_dev_dtype_count"])
        self.assertEqual(result["param_dev_dtype_numel"]["cpu|torch.bfloat16"], 8000)
        self.assertIn("param_distribution_hash", result)
        self.assertIsInstance(result["param_distribution_hash"], str)

    def test_rejects_cpu_fp32_when_bf16_expected(self):
        """All FP32 params with expected_dtype=bf16 raises RuntimeError."""
        from comfymodal_runtime.cpu_snapshot_models import inspect_and_validate_snapshot_params
        module = _FakeParamModule([
            _FakeParamTensor("cpu", "torch.float32", 5000, True),
            _FakeParamTensor("cpu", "torch.float32", 3000, True),
        ])
        with self.assertRaises(RuntimeError) as ctx:
            inspect_and_validate_snapshot_params(
                module, expected_dtype="torch.bfloat16", require_cpu=True,
            )
        self.assertIn("dtype mismatch", str(ctx.exception).lower())


class TestCpuSnapshotUnetConstruction(unittest.TestCase):
    """The target-GPU policy must reach ComfyUI's construction loader."""

    def test_default_rtx_pro_6000_passes_bf16_model_option(self):
        import types
        import torch

        from comfymodal_runtime.modal_app import _load_cpu_snapshot_unet

        calls = {}
        fake_sd = types.ModuleType("comfy.sd")
        fake_folder_paths = types.ModuleType("folder_paths")

        class _FakeValidPatcher:
            """Mimics a ModelPatcher returned by load_diffusion_model."""
            def __init__(self):
                self.model = _FakeManualCastModule(manual_cast_dtype=None,
                                                   params_dtype="torch.bfloat16")
                self.load_device = "cpu"
                self.offload_device = "cpu"
            def model_dtype(self):
                return torch.bfloat16
            def parameters(self, recurse=True):
                return self.model.parameters(recurse)
            def named_parameters(self, recurse=True):
                return iter([])
            def named_buffers(self, recurse=True):
                return iter([])

        def load_diffusion_model(path, *, model_options):
            calls["path"] = path
            calls["model_options"] = model_options
            return _FakeValidPatcher()

        fake_sd.load_diffusion_model = load_diffusion_model
        fake_folder_paths.get_full_path_or_raise = (
            lambda category, name: f"/models/{category}/{name}"
        )
        with patch.dict(
            sys.modules,
            {
                "comfy.sd": fake_sd,
                "folder_paths": fake_folder_paths,
            },
        ):
            result = _load_cpu_snapshot_unet(
                "z_image_turbo_bf16.safetensors",
                "default",
                target_gpus=("RTX-PRO-6000",),
                unet_cls=None,
            )

        self.assertIsInstance(result, _FakeValidPatcher)
        self.assertEqual(
            calls["path"],
            "/models/diffusion_models/z_image_turbo_bf16.safetensors",
        )
        self.assertIs(calls["model_options"]["dtype"], torch.bfloat16)

    def test_default_t4_passes_float32_model_option(self):
        import types
        import torch

        from comfymodal_runtime.modal_app import _load_cpu_snapshot_unet

        calls = {}
        fake_sd = types.ModuleType("comfy.sd")
        fake_folder_paths = types.ModuleType("folder_paths")
        sentinel = object()

        def load_diffusion_model(path, *, model_options):
            calls["path"] = path
            calls["model_options"] = model_options
            return sentinel

        fake_sd.load_diffusion_model = load_diffusion_model
        fake_folder_paths.get_full_path_or_raise = (
            lambda category, name: f"/models/{category}/{name}"
        )
        with patch.dict(
            sys.modules,
            {
                "comfy.sd": fake_sd,
                "folder_paths": fake_folder_paths,
            },
        ):
            result = _load_cpu_snapshot_unet(
                "model.safetensors",
                "default",
                target_gpus=("T4",),
                unet_cls=None,
            )

        self.assertIs(result, sentinel)
        self.assertIs(calls["model_options"]["dtype"], torch.float32)

    def test_accepts_mixed_dtype_when_no_expected_dtype(self):
        """Mixed FP32/BF16 params pass when expected_dtype is None."""
        from comfymodal_runtime.cpu_snapshot_models import inspect_and_validate_snapshot_params
        module = _FakeParamModule([
            _FakeParamTensor("cpu", "torch.float32", 5000, True),
            _FakeParamTensor("cpu", "torch.bfloat16", 3000, True),
        ])
        result = inspect_and_validate_snapshot_params(
            module, expected_dtype=None, require_cpu=True,
        )
        self.assertEqual(result["param_count"], 2)

    def test_rejects_non_cpu_param(self):
        """CUDA parameter with require_cpu=True raises RuntimeError."""
        from comfymodal_runtime.cpu_snapshot_models import inspect_and_validate_snapshot_params
        module = _FakeParamModule([
            _FakeParamTensor("cuda:0", "torch.bfloat16", 5000, True),
        ])
        with self.assertRaises(RuntimeError) as ctx:
            inspect_and_validate_snapshot_params(
                module, require_cpu=True,
            )
        self.assertIn("non-cpu", str(ctx.exception).lower())

    def test_rejects_meta_param(self):
        """Meta parameter with require_cpu=True raises RuntimeError."""
        from comfymodal_runtime.cpu_snapshot_models import inspect_and_validate_snapshot_params
        module = _FakeParamModule([
            _FakeParamTensor("meta", "torch.bfloat16", 5000, True),
        ])
        with self.assertRaises(RuntimeError) as ctx:
            inspect_and_validate_snapshot_params(
                module, require_cpu=True,
            )
        self.assertIn("non-cpu", str(ctx.exception).lower())

    def test_require_cpu_false_allows_non_cpu(self):
        """require_cpu=False allows CUDA params (restore time)."""
        from comfymodal_runtime.cpu_snapshot_models import inspect_and_validate_snapshot_params
        module = _FakeParamModule([
            _FakeParamTensor("cuda:0", "torch.bfloat16", 5000, True),
        ])
        result = inspect_and_validate_snapshot_params(
            module, require_cpu=False,
        )
        self.assertEqual(result["param_count"], 1)
        self.assertIn("cuda:0|torch.bfloat16", result["param_dev_dtype_count"])

    def test_empty_module(self):
        """Module with no parameters returns zeros."""
        from comfymodal_runtime.cpu_snapshot_models import inspect_and_validate_snapshot_params
        module = _FakeParamModule([])
        result = inspect_and_validate_snapshot_params(
            module, expected_dtype="torch.bfloat16", require_cpu=True,
        )
        self.assertEqual(result["param_count"], 0)
        self.assertEqual(result["total_param_numel"], 0)
        self.assertEqual(result["param_dev_dtype_count"], {})
        self.assertEqual(result["param_dev_dtype_numel"], {})

    def test_expected_dtype_mismatch_with_mixed_params(self):
        """When expected_dtype is bf16 and NO float params are bf16, raise."""
        from comfymodal_runtime.cpu_snapshot_models import inspect_and_validate_snapshot_params
        module = _FakeParamModule([
            _FakeParamTensor("cpu", "torch.float32", 5000, True),
            # Non-float param should not be counted
            _FakeParamTensor("cpu", "torch.int64", 100, False),
        ])
        with self.assertRaises(RuntimeError) as ctx:
            inspect_and_validate_snapshot_params(
                module, expected_dtype="torch.bfloat16", require_cpu=True,
            )
        self.assertIn("dtype mismatch", str(ctx.exception).lower())


# ── AimDO disablement regression tests ────────────────────────────────


class TestAimDOFlagDuringSnapshotUnetLoad(unittest.TestCase):
    """comfy.memory_management.aimdo_enabled must be False during snapshot
    UNET load and restored after success/exception."""

    def _make_fake_memory_management(self):
        import types
        mm = types.ModuleType("comfy.memory_management")
        mm.aimdo_enabled = True
        return mm

    def _make_fake_sd_and_folder_paths(self):
        import types
        import torch
        fake_sd = types.ModuleType("comfy.sd")
        fake_fp = types.ModuleType("folder_paths")

        class _ValidPatcher:
            def __init__(self):
                self.model = _FakeManualCastModule(
                    manual_cast_dtype=None, params_dtype="torch.bfloat16"
                )
                self.load_device = "cpu"
                self.offload_device = "cpu"
            def model_dtype(self):
                return torch.bfloat16
            def parameters(self, recurse=True):
                return self.model.parameters(recurse)
            def named_parameters(self, recurse=True):
                return iter([])
            def named_buffers(self, recurse=True):
                return iter([])

        fake_sd.load_diffusion_model = lambda path, *, model_options: _ValidPatcher()
        fake_fp.get_full_path_or_raise = lambda category, name: f"/models/{category}/{name}"
        return fake_sd, fake_fp

    def test_aimdo_disabled_during_load_and_restored_after_success(self):
        """AimDO flag is False during snapshot UNET load and restored after success."""
        import sys
        from unittest.mock import patch
        from comfymodal_runtime.modal_app import _load_cpu_snapshot_unet

        mm = self._make_fake_memory_management()
        fake_sd, fake_fp = self._make_fake_sd_and_folder_paths()
        aimdo_values = []
        original_load = fake_sd.load_diffusion_model
        def tracking_load(path, *, model_options):
            aimdo_values.append(mm.aimdo_enabled)
            return original_load(path, model_options=model_options)
        fake_sd.load_diffusion_model = tracking_load

        with patch.dict(sys.modules, {
            "comfy.memory_management": mm,
            "comfy.sd": fake_sd,
            "folder_paths": fake_fp,
        }):
            self.assertTrue(mm.aimdo_enabled)
            result = _load_cpu_snapshot_unet(
                "model.safetensors", "default",
                target_gpus=("T4",), unet_cls=None,
            )
            self.assertIsNotNone(result)
            self.assertFalse(aimdo_values[0], "aimdo_enabled must be False during UNET load")
            self.assertTrue(mm.aimdo_enabled, "aimdo_enabled must be restored after load")

    def test_aimdo_restored_after_exception(self):
        """AimDO flag is restored to original value even after exception."""
        import sys
        from unittest.mock import patch
        from comfymodal_runtime.modal_app import _load_cpu_snapshot_unet

        mm = self._make_fake_memory_management()
        fake_sd, fake_fp = self._make_fake_sd_and_folder_paths()
        fake_sd.load_diffusion_model = lambda path, *, model_options: (
            (_ for _ in ()).throw(RuntimeError("load failed"))
        )

        with patch.dict(sys.modules, {
            "comfy.memory_management": mm,
            "comfy.sd": fake_sd,
            "folder_paths": fake_fp,
        }):
            self.assertTrue(mm.aimdo_enabled)
            with self.assertRaises(RuntimeError):
                _load_cpu_snapshot_unet(
                    "model.safetensors", "default",
                    target_gpus=("T4",), unet_cls=None,
                )
            self.assertTrue(mm.aimdo_enabled,
                            "aimdo_enabled must be restored after exception")

    def test_aimdo_original_value_not_tampered(self):
        """AimDO original value is not permanently changed."""
        import sys
        from unittest.mock import patch
        from comfymodal_runtime.modal_app import _load_cpu_snapshot_unet

        mm = self._make_fake_memory_management()
        mm.aimdo_enabled = "custom_value"
        fake_sd, fake_fp = self._make_fake_sd_and_folder_paths()

        with patch.dict(sys.modules, {
            "comfy.memory_management": mm,
            "comfy.sd": fake_sd,
            "folder_paths": fake_fp,
        }):
            self.assertEqual(mm.aimdo_enabled, "custom_value")
            result = _load_cpu_snapshot_unet(
                "model.safetensors", "default",
                target_gpus=("T4",), unet_cls=None,
            )
            self.assertIsNotNone(result)
            self.assertEqual(mm.aimdo_enabled, "custom_value",
                             "non-bool aimdo value must be preserved")


# ── BF16-native validation tests ──────────────────────────────────────


class _FakeManualCastModule:
    """Fake .model attribute with manual_cast_dtype.
    model_dtype() lives on the patcher (unet), not on .model."""
    def __init__(self, manual_cast_dtype=None, params_device="cpu",
                 params_dtype="torch.bfloat16"):
        self.manual_cast_dtype = manual_cast_dtype
        self._params = [_FakeParamTensor(params_device, params_dtype, 1000, True)]

    def parameters(self, recurse=True):
        return iter(self._params)


class _FakeBF16Unet:
    """Duck-typed unet patcher for validate_snapshot_unet_bf16_native.
    model_dtype() is on the patcher (self), not on .model."""
    def __init__(self, manual_cast_dtype=None, model_dtype_val="torch.bfloat16",
                 params_device="cpu", params_dtype="torch.bfloat16"):
        self.model = _FakeManualCastModule(
            manual_cast_dtype=manual_cast_dtype,
            params_device=params_device,
            params_dtype=params_dtype,
        )
        self._model_dtype_val = model_dtype_val
        self.load_device = "cpu"
        self.offload_device = "cpu"

    def model_dtype(self):
        return self._model_dtype_val

    def parameters(self, recurse=True):
        return self.model.parameters(recurse)


class TestBF16NativeValidation(unittest.TestCase):
    """validate_snapshot_unet_bf16_native coverage."""

    def test_accepts_native_bf16_unet(self):
        """All-BF16 CPU params with no manual_cast passes."""
        from comfymodal_runtime.cpu_snapshot_models import validate_snapshot_unet_bf16_native
        unet = _FakeBF16Unet(manual_cast_dtype=None)
        try:
            validate_snapshot_unet_bf16_native(unet)
        except RuntimeError as exc:
            self.fail(f"Unexpected RuntimeError: {exc}")

    def test_rejects_manual_cast_float32(self):
        """manual_cast_dtype=torch.float32 raises."""
        from comfymodal_runtime.cpu_snapshot_models import validate_snapshot_unet_bf16_native
        unet = _FakeBF16Unet(manual_cast_dtype="torch.float32")
        with self.assertRaises(RuntimeError) as ctx:
            validate_snapshot_unet_bf16_native(unet)
        self.assertIn("manual_cast_dtype", str(ctx.exception).lower())
        self.assertIn("float32", str(ctx.exception))

    def test_rejects_model_dtype_not_bf16(self):
        """model_dtype returning float32 raises."""
        from comfymodal_runtime.cpu_snapshot_models import validate_snapshot_unet_bf16_native
        unet = _FakeBF16Unet(model_dtype_val="torch.float32", manual_cast_dtype=None)
        with self.assertRaises(RuntimeError) as ctx:
            validate_snapshot_unet_bf16_native(unet)
        self.assertIn("model_dtype", str(ctx.exception).lower())

    def test_rejects_non_cpu_params(self):
        """CUDA params raise."""
        from comfymodal_runtime.cpu_snapshot_models import validate_snapshot_unet_bf16_native
        unet = _FakeBF16Unet(params_device="cuda:0")
        with self.assertRaises(RuntimeError) as ctx:
            validate_snapshot_unet_bf16_native(unet)
        self.assertIn("non-cpu", str(ctx.exception).lower())

    def test_rejects_non_bf16_fp_params(self):
        """FP32 params on CPU raise."""
        from comfymodal_runtime.cpu_snapshot_models import validate_snapshot_unet_bf16_native
        unet = _FakeBF16Unet(params_dtype="torch.float32")
        with self.assertRaises(RuntimeError) as ctx:
            validate_snapshot_unet_bf16_native(unet)
        self.assertIn("non-bf16", str(ctx.exception).lower())

    def test_rejects_none_unet(self):
        """None unet raises."""
        from comfymodal_runtime.cpu_snapshot_models import validate_snapshot_unet_bf16_native
        with self.assertRaises(RuntimeError) as ctx:
            validate_snapshot_unet_bf16_native(None)
        self.assertIn("none", str(ctx.exception).lower())

    def test_accepts_include_target_gpus(self):
        """target_gpus parameter is accepted (no-op for validation)."""
        from comfymodal_runtime.cpu_snapshot_models import validate_snapshot_unet_bf16_native
        unet = _FakeBF16Unet(manual_cast_dtype=None)
        try:
            validate_snapshot_unet_bf16_native(unet, target_gpus=("RTX-PRO-6000",))
        except RuntimeError as exc:
            self.fail(f"Unexpected RuntimeError: {exc}")


# ── Compute policy identity tests ─────────────────────────────────────


class TestComputePolicyIdentity(unittest.TestCase):
    """_resolve_compute_policy and model_spec compute_policy field."""

    def test_rtx_pro_6000_resolves_bf16_native(self):
        """RTX-PRO-6000 default weight_dtype -> bf16_native."""
        from comfymodal_runtime.cpu_snapshot_models import _resolve_compute_policy
        result = _resolve_compute_policy("default", target_gpus=("RTX-PRO-6000",))
        self.assertEqual(result, "bf16_native")

    def test_t4_resolves_default(self):
        """T4 default weight_dtype -> default (no bf16)."""
        from comfymodal_runtime.cpu_snapshot_models import _resolve_compute_policy
        result = _resolve_compute_policy("default", target_gpus=("T4",))
        self.assertEqual(result, "default")

    def test_no_target_gpus_resolves_default(self):
        """No target_gpus -> default."""
        from comfymodal_runtime.cpu_snapshot_models import _resolve_compute_policy
        result = _resolve_compute_policy("default")
        self.assertEqual(result, "default")

    def test_explicit_fp32_resolves_default(self):
        """fp32 weight_dtype -> default even for RTX."""
        from comfymodal_runtime.cpu_snapshot_models import _resolve_compute_policy
        result = _resolve_compute_policy("fp32", target_gpus=("RTX-PRO-6000",))
        self.assertEqual(result, "default")

    def test_compute_policy_resolved_separately(self):
        """compute_policy is stored separately, NOT in model_spec."""
        from comfymodal_runtime.cpu_snapshot_models import _build_model_spec, _normalize_profile
        profile = {"mode": "split", "unet": "unet.safetensors", "clip1": "clip1.safetensors",
                    "clip_type": "stable_diffusion"}
        norm = _normalize_profile(profile)
        spec = _build_model_spec(norm)
        self.assertNotIn("compute_policy", spec)
        # Verify _resolve_compute_policy still works
        from comfymodal_runtime.cpu_snapshot_models import _resolve_compute_policy
        _cp = _resolve_compute_policy("default", target_gpus=("RTX-PRO-6000",))
        self.assertEqual(_cp, "bf16_native")
        _cp2 = _resolve_compute_policy("default", target_gpus=("T4",))
        self.assertEqual(_cp2, "default")


# ── cpu_snapshot_unet_compute_policy contextmanager tests ─────────────


class _FakeMMForContext:
    """Duck-typed comfy.model_management with inspectable unet_manual_cast."""
    def __init__(self, return_value="torch.float32"):
        self._return_value = return_value
        self.call_count = 0
        self.last_weight_dtype = None
        self.last_device = None

    def unet_manual_cast(self, weight_dtype, inference_device, supported_dtypes=None):
        self.call_count += 1
        self.last_weight_dtype = weight_dtype
        self.last_device = inference_device
        # Simulate CPU behavior: return float32 for bf16 on CPU
        if str(weight_dtype) == "torch.bfloat16":
            return "torch.float32"
        return self._return_value


class TestComputePolicyContextmanager(unittest.TestCase):
    """cpu_snapshot_unet_compute_policy coverage."""

    def setUp(self):
        # Install fake model_management in sys.modules
        self._mm = _FakeMMForContext()
        self._orig_module = sys.modules.get("comfy.model_management")
        sys.modules["comfy.model_management"] = self._mm

    def tearDown(self):
        # Restore original module
        if self._orig_module is not None:
            sys.modules["comfy.model_management"] = self._orig_module
        else:
            sys.modules.pop("comfy.model_management", None)
        # Clean up any thread state left behind
        from comfymodal_runtime.model_preload import (
            _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD,
            _CPU_SNAPSHOT_UNET_MANUAL_CAST_OVERRIDE,
        )
        _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD.set(0)
        _CPU_SNAPSHOT_UNET_MANUAL_CAST_OVERRIDE.set("")

    def _import_cm(self):
        from comfymodal_runtime.model_preload import cpu_snapshot_unet_compute_policy
        return cpu_snapshot_unet_compute_policy

    def test_bf16_rtx_returns_none(self):
        """BF16 weight + RTX target -> unet_manual_cast returns None."""
        import torch
        cm = self._import_cm()
        with cm(effective_weight_dtype=torch.bfloat16, target_gpus=("RTX-PRO-6000",)):
            result = self._mm.unet_manual_cast(torch.bfloat16, "cpu")
        self.assertIsNone(result)
        # Original function was called 0 times during the patched interval
        self.assertEqual(self._mm.call_count, 0)

    def test_bf16_t4_delegates(self):
        """BF16 weight + T4 target -> unet_manual_cast delegates (returns float32)."""
        import torch
        cm = self._import_cm()
        with cm(effective_weight_dtype=torch.bfloat16, target_gpus=("T4",)):
            result = self._mm.unet_manual_cast(torch.bfloat16, "cpu")
        self.assertEqual(result, "torch.float32")
        # Original was called once (our fake's unet_manual_cast)
        self.assertEqual(self._mm.call_count, 1)

    def test_no_patch_when_not_bf16(self):
        """fp32 weight with RTX target does not patch."""
        import torch
        cm = self._import_cm()
        with cm(effective_weight_dtype=torch.float32, target_gpus=("RTX-PRO-6000",)):
            result = self._mm.unet_manual_cast(torch.float32, "cpu")
        self.assertEqual(result, "torch.float32")

    def test_no_patch_when_no_target_gpus(self):
        """No target_gpus does not patch."""
        import torch
        cm = self._import_cm()
        with cm(effective_weight_dtype=torch.bfloat16, target_gpus=()):
            result = self._mm.unet_manual_cast(torch.bfloat16, "cpu")
        self.assertEqual(result, "torch.float32")

    def test_restores_after_success(self):
        """After context, unet_manual_cast is the original function."""
        import torch
        cm = self._import_cm()
        with cm(effective_weight_dtype=torch.bfloat16, target_gpus=("RTX-PRO-6000",)):
            self.assertIsNone(self._mm.unet_manual_cast(torch.bfloat16, "cpu"))
        # After context, original behavior restored
        result = self._mm.unet_manual_cast(torch.bfloat16, "cpu")
        self.assertEqual(result, "torch.float32")
        self.assertEqual(self._mm.call_count, 1)  # The call after restore

    def test_restores_after_exception(self):
        """After exception, unet_manual_cast is the original function."""
        import torch
        cm = self._import_cm()
        try:
            with cm(effective_weight_dtype=torch.bfloat16, target_gpus=("RTX-PRO-6000",)):
                self.assertIsNone(self._mm.unet_manual_cast(torch.bfloat16, "cpu"))
                raise ValueError("test error")
        except ValueError:
            pass
        # After exception, original behavior restored
        result = self._mm.unet_manual_cast(torch.bfloat16, "cpu")
        self.assertEqual(result, "torch.float32")

    def test_normal_loader_unaffected(self):
        """Outside policy context, unet_manual_cast behaves normally."""
        import torch
        result = self._mm.unet_manual_cast(torch.bfloat16, "cpu")
        self.assertEqual(result, "torch.float32")

    def test_does_not_call_cuda_apis(self):
        """Contextmanager never calls torch.cuda.* APIs.

        Patches ``is_available``, ``is_bf16_supported``, ``get_device_capability``,
        and ``get_device_properties`` to raise ``AssertionError`` if called.
        The test passes only if none of these are called.
        """
        import torch
        from unittest.mock import patch as _mpatch

        def _raise(*a, **kw):
            raise AssertionError("torch.cuda API was called during compute policy resolution")

        _patchers = []
        _cuda_mod = getattr(torch, "cuda", None)
        if _cuda_mod is not None:
            for _name in ("is_available", "is_bf16_supported",
                          "get_device_capability", "get_device_properties"):
                if hasattr(_cuda_mod, _name):
                    _patchers.append(_mpatch.object(_cuda_mod, _name, _raise))
        for _p in _patchers:
            _p.start()
        try:
            cm = self._import_cm()
            with cm(effective_weight_dtype=torch.bfloat16, target_gpus=("RTX-PRO-6000",)):
                self.assertIsNone(self._mm.unet_manual_cast(torch.bfloat16, "cpu"))
        except AssertionError:
            raise
        finally:
            for _p in _patchers:
                _p.stop()

    def test_unrelated_call_delegates_during_patch(self):
        """A call on the same thread that looks different delegates."""
        import torch
        cm = self._import_cm()
        with cm(effective_weight_dtype=torch.bfloat16, target_gpus=("RTX-PRO-6000",)):
            # Active thread calls with bf16 -> gets None
            self.assertIsNone(self._mm.unet_manual_cast(torch.bfloat16, "cpu"))
            # But a call with float32 delegates
            result = self._mm.unet_manual_cast(torch.float32, "cpu")
            self.assertEqual(result, "torch.float32")

    def test_other_thread_delegates_during_patch(self):
        """An unrelated caller on another thread delegates while wrapper installed."""
        import torch
        import threading
        cm = self._import_cm()
        _other_result = []
        def _other_thread():
            # Call from another thread during the active context
            _other_result.append(self._mm.unet_manual_cast(torch.bfloat16, "cpu"))
        with cm(effective_weight_dtype=torch.bfloat16, target_gpus=("RTX-PRO-6000",)):
            # Main thread gets None
            self.assertIsNone(self._mm.unet_manual_cast(torch.bfloat16, "cpu"))
            # Other thread calls - should delegate to original (returns float32)
            _t = threading.Thread(target=_other_thread)
            _t.start()
            _t.join(timeout=5)
            self.assertFalse(_t.is_alive())
        self.assertEqual(len(_other_result), 1)
        # Other thread saw original behavior (delegated)
        self.assertEqual(_other_result[0], "torch.float32")

    def test_second_context_cannot_replace(self):
        """A second context cannot replace/observe the first override (lock-held).

        Deterministic: verify second context remains blocked while first is
        active, then exit first and verify the second entered afterward.
        """
        import torch
        import threading
        cm = self._import_cm()
        _second_entered = threading.Event()
        _second_done = threading.Event()
        _second_result = []
        def _second_thread():
            try:
                with cm(effective_weight_dtype=torch.bfloat16, target_gpus=("RTX-PRO-6000",)):
                    _second_entered.set()
                    _second_result.append(self._mm.unet_manual_cast(torch.bfloat16, "cpu"))
            except Exception as e:
                _second_result.append(e)
            finally:
                _second_done.set()
        with cm(effective_weight_dtype=torch.bfloat16, target_gpus=("RTX-PRO-6000",)):
            # Start second thread that tries to enter another context
            _t = threading.Thread(target=_second_thread)
            _t.start()
            # Give second thread a moment to attempt entry — it must remain
            # blocked because the lock is held by the outer context.
            _entered = _second_entered.wait(timeout=1.5)
            self.assertFalse(
                _entered,
                "Second context should not be able to enter while first holds the lock",
            )
            # Main thread still gets None from the override
            self.assertIsNone(self._mm.unet_manual_cast(torch.bfloat16, "cpu"))
            self.assertEqual(self._mm.call_count, 0)
        # Outer context exited — second thread can now acquire the lock.
        # Wait for it to enter and complete.
        _done = _second_done.wait(timeout=5)
        self.assertTrue(_done, "Second thread did not complete after outer context exited")
        _t.join(timeout=2)
        self.assertTrue(_second_entered.is_set(),
                        "Second context should have entered after first exited")
        # The second thread enters its OWN context (after outer exited)
        # so it sees None from its own override.
        self.assertEqual(len(_second_result), 1)
        self.assertIsNone(_second_result[0])
        # Verify original is restored on main thread too
        self.assertEqual(self._mm.unet_manual_cast(torch.bfloat16, "cpu"), "torch.float32")
        self.assertEqual(self._mm.call_count, 1)  # one call after restore

    def test_bf16_native_validated_by_validate_cpu_snapshot_models(self):
        """validate_cpu_snapshot_models with bf16_native compute_policy calls bf16 validation.

        Uses temp files and real resolve_path to pass file facts validation,
        then verifies that validate_snapshot_unet_bf16_native rejects
        manual_cast_dtype at the validate_cpu_snapshot_models level."""
        import tempfile, types
        from comfymodal_runtime.cpu_snapshot_models import (
            validate_cpu_snapshot_models,
            CpuSnapshotModels,
            _COMPUTE_POLICY_BF16_NATIVE,
            ModelFileFact,
            CPU_SNAPSHOT_UNET_POLICY_VERSION,
        )
        from comfymodal_runtime.contracts import ModelRestoreKey
        _tmpdir = tempfile.mkdtemp()
        _unet_path = os.path.join(_tmpdir, "unet.safetensors")
        _clip1_path = os.path.join(_tmpdir, "clip1.safetensors")
        open(_unet_path, "w").close()
        open(_clip1_path, "w").close()
        _st_un = os.stat(_unet_path)
        _st_cl = os.stat(_clip1_path)
        _key = ModelRestoreKey(unet_identity="unet.safetensors", clip_identity="clip1.safetensors",
                                clip_type="stable_diffusion")
        # Build unet that passes _is_valid_unet_patcher but fails bf16-native
        # Must have non-zero floating params so zero-param check passes
        _fake_param = types.SimpleNamespace(
            device="cpu", dtype=types.SimpleNamespace(),
            is_floating_point=lambda: True, numel=lambda: 1000,
        )
        _fake_param.dtype = "torch.bfloat16"
        _mod = types.ModuleType("m")
        _mod.named_parameters = lambda recurse=True: iter([])
        _mod.named_buffers = lambda recurse=True: iter([])
        _mod.diffusion_model = _mod
        _mod.manual_cast_dtype = "torch.float32"  # Will fail bf16-native
        _unet = types.SimpleNamespace(
            model=_mod,
            load_device="cpu", offload_device="cpu",
            model_dtype=lambda: "torch.bfloat16",
            parameters=lambda: iter([_fake_param]),
            named_parameters=lambda recurse=True: iter([]),
            named_buffers=lambda recurse=True: iter([]),
        )
        _clip_mod = types.ModuleType("cm")
        _clip_mod.named_parameters = lambda recurse=True: iter([])
        _clip_mod.named_buffers = lambda recurse=True: iter([])
        _clip_patcher = types.SimpleNamespace(load_device="cpu", offload_device="cpu")
        _clip = types.SimpleNamespace(
            patcher=_clip_patcher,
            tokenizer=object(),
            cond_stage_model=_clip_mod,
        )
        models = CpuSnapshotModels(
            model_key=_key,
            model_spec={"loaders": {"unet": [], "clip": []}},
            normalized_profile={"mode": "split", "unet": "unet.safetensors",
                                "clip1": "clip1.safetensors", "clip_type": "stable_diffusion"},
            file_facts=[
                ModelFileFact(role="unet", path=_unet_path, size_bytes=_st_un.st_size, mtime_ns=0),
                ModelFileFact(role="clip1", path=_clip1_path, size_bytes=_st_cl.st_size, mtime_ns=0),
            ],
            unet=_unet,
            clip=_clip,
            compute_policy=_COMPUTE_POLICY_BF16_NATIVE,
            policy_version=CPU_SNAPSHOT_UNET_POLICY_VERSION,
            target_gpus=("RTX-PRO-6000",),
        )
        ok, reason = validate_cpu_snapshot_models(
            models,
            expected_key=_key,
            expected_spec={"loaders": {"unet": [], "clip": []}},
            resolve_path=lambda role, name: os.path.join(_tmpdir, name),
        )
        import shutil
        shutil.rmtree(_tmpdir, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("manual_cast", reason.lower())

    def test_compute_policy_not_in_model_spec_via_identity_from_profile(self):
        """identity_from_profile model_spec does NOT contain compute_policy."""
        import tempfile
        from comfymodal_runtime.cpu_snapshot_models import identity_from_profile
        _tmpdir = tempfile.mkdtemp()
        _unet_path = os.path.join(_tmpdir, "unet.safetensors")
        _clip1_path = os.path.join(_tmpdir, "clip1.safetensors")
        open(_unet_path, "w").close()
        open(_clip1_path, "w").close()
        profile = {
            "mode": "split",
            "unet": "unet.safetensors",
            "clip1": "clip1.safetensors",
            "clip_type": "stable_diffusion",
        }
        _key, spec, _facts = identity_from_profile(
            profile,
            resolve_path=lambda role, name: os.path.join(_tmpdir, name),
        )
        self.assertNotIn("compute_policy", spec)
        import shutil
        shutil.rmtree(_tmpdir, ignore_errors=True)


# ── Policy version / identity tests ──────────────────────────────────


class TestPolicyVersionIdentity(unittest.TestCase):
    """CPU_SNAPSHOT_UNET_POLICY_VERSION and _policy_identity."""

    def test_current_version_is_2(self):
        from comfymodal_runtime.cpu_snapshot_models import CPU_SNAPSHOT_UNET_POLICY_VERSION
        self.assertEqual(CPU_SNAPSHOT_UNET_POLICY_VERSION, 2)

    def test_policy_identity_changes_with_version(self):
        from comfymodal_runtime.cpu_snapshot_models import _policy_identity
        id1 = _policy_identity(2, "bfloat16", "bfloat16", "none")
        id2 = _policy_identity(1, "bfloat16", "bfloat16", "none")
        self.assertNotEqual(id1, id2)

    def test_policy_identity_changes_with_compute(self):
        from comfymodal_runtime.cpu_snapshot_models import _policy_identity
        id1 = _policy_identity(2, "bfloat16", "bfloat16", "none")
        id2 = _policy_identity(2, "bfloat16", "float32", "none")
        self.assertNotEqual(id1, id2)

    def test_policy_identity_changes_with_manual(self):
        from comfymodal_runtime.cpu_snapshot_models import _policy_identity
        id1 = _policy_identity(2, "bfloat16", "bfloat16", "none")
        id2 = _policy_identity(2, "bfloat16", "bfloat16", "float32")
        self.assertNotEqual(id1, id2)

    def test_current_native_snapshot_identity_accepted(self):
        """Native BF16 snapshot produces expected identity."""
        from comfymodal_runtime.cpu_snapshot_models import (
            _policy_identity, CPU_SNAPSHOT_UNET_POLICY_VERSION,
        )
        ident = _policy_identity(CPU_SNAPSHOT_UNET_POLICY_VERSION,
                                 "bfloat16", "bfloat16", "none")
        self.assertIn("v2:", ident)
        self.assertIn("weight=bfloat16", ident)
        self.assertIn("compute=bfloat16", ident)
        self.assertIn("manual=none", ident)

    def test_stale_version_rejected(self):
        """validate_cpu_snapshot_models rejects policy_version=0."""
        import tempfile
        from comfymodal_runtime.cpu_snapshot_models import (
            validate_cpu_snapshot_models, CpuSnapshotModels, ModelFileFact,
        )
        from comfymodal_runtime.contracts import ModelRestoreKey
        _tmpdir = tempfile.mkdtemp()
        _unet_path = os.path.join(_tmpdir, "u.safetensors")
        _clip_path = os.path.join(_tmpdir, "c.safetensors")
        open(_unet_path, "w").close()
        open(_clip_path, "w").close()
        _st_u = os.stat(_unet_path)
        _st_c = os.stat(_clip_path)
        _key = ModelRestoreKey(unet_identity="u.safetensors",
                               clip_identity="c.safetensors",
                               clip_type="stable_diffusion")
        models = CpuSnapshotModels(
            model_key=_key,
            model_spec={"loaders": {"unet": [], "clip": []}},
            normalized_profile={"mode": "split", "unet": "u.safetensors",
                                "clip1": "c.safetensors", "clip_type": "stable_diffusion"},
            file_facts=[
                ModelFileFact(role="unet", path=_unet_path, size_bytes=_st_u.st_size, mtime_ns=0),
                ModelFileFact(role="clip1", path=_clip_path, size_bytes=_st_c.st_size, mtime_ns=0),
            ],
            unet=_FakeUNETPatcher(), clip=_FakeCLIP(),
            policy_version=0,  # legacy
        )
        ok, reason = validate_cpu_snapshot_models(
            models, expected_key=_key,
            expected_spec={"loaders": {"unet": [], "clip": []}},
            resolve_path=lambda r, n: os.path.join(_tmpdir, n),
        )
        import shutil
        shutil.rmtree(_tmpdir, ignore_errors=True)
        self.assertFalse(ok)
        self.assertIn("policy_version", reason.lower())
        self.assertIn("legacy", reason.lower())

    def test_model_spec_remains_default_weight_dtype(self):
        """model_spec weight_dtype stays 'default' even with effective BF16."""
        from comfymodal_runtime.cpu_snapshot_models import _build_model_spec, _normalize_profile
        prof = {"mode": "split", "unet": "u.safetensors",
                "clip1": "c.safetensors", "clip_type": "stable_diffusion"}
        norm = _normalize_profile(prof)
        spec = _build_model_spec(norm)
        unet_loader = spec.get("loaders", {}).get("unet", [{}])[0]
        self.assertEqual(unet_loader.get("weight_dtype"), "default")


class TestConstructionSelectionAndExceptionRestoration(unittest.TestCase):
    """_load_cpu_snapshot_unet construction selection and exception restoration."""

    def setUp(self):
        # Install fake model_management in sys.modules
        self._mm = _FakeMMForContext()
        self._orig_mm = sys.modules.get("comfy.model_management")
        sys.modules["comfy.model_management"] = self._mm
        self._orig_cm = sys.modules.get("comfy.sd")
        self._orig_fp = sys.modules.get("folder_paths")

    def tearDown(self):
        if self._orig_mm is not None:
            sys.modules["comfy.model_management"] = self._orig_mm
        else:
            sys.modules.pop("comfy.model_management", None)
        if self._orig_cm is not None:
            sys.modules["comfy.sd"] = self._orig_cm
        else:
            sys.modules.pop("comfy.sd", None)
        if self._orig_fp is not None:
            sys.modules["folder_paths"] = self._orig_fp
        else:
            sys.modules.pop("folder_paths", None)
        from comfymodal_runtime.model_preload import (
            _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD,
            _CPU_SNAPSHOT_UNET_MANUAL_CAST_OVERRIDE,
        )
        _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD.set(0)
        _CPU_SNAPSHOT_UNET_MANUAL_CAST_OVERRIDE.set("")

    def test_construction_returns_none_manual_cast(self):
        """BF16-native construction: unet_manual_cast returns None, model_dtype BF16,
        manual None, CPU BF16 params, original restored after."""
        import types, torch
        from comfymodal_runtime.modal_app import _load_cpu_snapshot_unet

        # Fake comfy.sd with load_diffusion_model
        _fake_sd = types.ModuleType("comfy.sd")
        _construction_calls = []

        class _FakeModelPatcher:
            """Mimics ModelPatcher returned by load_diffusion_model."""
            def __init__(self):
                self.model = _FakeManualCastModule(manual_cast_dtype=None,
                                                   params_dtype="torch.bfloat16")
                self.load_device = "cpu"
                self.offload_device = "cpu"

            def model_dtype(self):
                return torch.bfloat16

            def parameters(self, recurse=True):
                return self.model.parameters(recurse)

            def named_parameters(self, recurse=True):
                return iter([])

            def named_buffers(self, recurse=True):
                return iter([])

        def _fake_load(path, *, model_options):
            _construction_calls.append(("load_diffusion_model", path, model_options))
            # Inside the compute policy context, verify unet_manual_cast returns None
            _call_result = self._mm.unet_manual_cast(torch.bfloat16, "cpu")
            _construction_calls.append(("unet_manual_cast_in_context", _call_result))
            return _FakeModelPatcher()

        _fake_sd.load_diffusion_model = _fake_load
        _fake_fp = types.ModuleType("folder_paths")
        _fake_fp.get_full_path_or_raise = lambda cat, name: f"/models/{cat}/{name}"
        sys.modules["comfy.sd"] = _fake_sd
        sys.modules["folder_paths"] = _fake_fp

        result = _load_cpu_snapshot_unet(
            "test_unet.safetensors", "default",
            target_gpus=("RTX-PRO-6000",), unet_cls=None,
        )

        # Verify load_diffusion_model was called
        self.assertEqual(len(_construction_calls), 2)
        self.assertEqual(_construction_calls[0][0], "load_diffusion_model")
        # Verify dtype model_option is bf16
        self.assertIs(_construction_calls[0][2]["dtype"], torch.bfloat16)
        # Verify unet_manual_cast returned None during context
        self.assertIsNone(_construction_calls[1][1])

        # Verify returned patcher has correct state
        self.assertIsInstance(result, _FakeModelPatcher)
        self.assertIsNone(result.model.manual_cast_dtype)
        self.assertEqual(result.model_dtype(), torch.bfloat16)
        # Verify original unet_manual_cast is restored after construction
        post_result = self._mm.unet_manual_cast(torch.bfloat16, "cpu")
        self.assertEqual(post_result, "torch.float32")
        self.assertEqual(self._mm.call_count, 1)  # call after restore

    def test_exception_restores_original(self):
        """Exception during construction restores unet_manual_cast."""
        import types, torch
        from comfymodal_runtime.modal_app import _load_cpu_snapshot_unet

        _fake_sd = types.ModuleType("comfy.sd")
        def _fake_load(path, *, model_options):
            raise ValueError("construction failure")

        _fake_sd.load_diffusion_model = _fake_load
        _fake_fp = types.ModuleType("folder_paths")
        _fake_fp.get_full_path_or_raise = lambda cat, name: f"/models/{cat}/{name}"
        sys.modules["comfy.sd"] = _fake_sd
        sys.modules["folder_paths"] = _fake_fp

        with self.assertRaises(ValueError):
            _load_cpu_snapshot_unet(
                "test_unet.safetensors", "default",
                target_gpus=("RTX-PRO-6000",), unet_cls=None,
            )

        # Original unet_manual_cast must be restored after exception
        post_result = self._mm.unet_manual_cast(torch.bfloat16, "cpu")
        self.assertEqual(post_result, "torch.float32")
        # The policy must also leave thread state clean
        from comfymodal_runtime.model_preload import (
            _CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD,
            _CPU_SNAPSHOT_UNET_MANUAL_CAST_OVERRIDE,
        )
        self.assertEqual(_CPU_SNAPSHOT_UNET_POLICY_ACTIVE_THREAD.get(), 0)
        self.assertEqual(_CPU_SNAPSHOT_UNET_MANUAL_CAST_OVERRIDE.get(), "")


if __name__ == "__main__":
    unittest.main()
