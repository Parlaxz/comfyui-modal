"""Tests for collect_unet_forward_probe_state in cpu_snapshot_models.py."""
from __future__ import annotations

import hashlib
import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from comfymodal_runtime.cpu_snapshot_models import collect_unet_forward_probe_state


# ---------------------------------------------------------------------------
# Fake tensor stubs — safe operations only
# ---------------------------------------------------------------------------

class _SafeFakeTensor:
    """Tensor stub that only supports .device, .dtype, .numel()."""
    def __init__(self, device="cpu", dtype="torch.float32", numel=1):
        self.device = device
        self.dtype = dtype
        self._numel = numel

    def numel(self):
        return self._numel


class _RaisingFakeTensor:
    """Tensor stub that returns device/dtype/numel but raises on forbidden methods."""
    def __init__(self, device="cpu", dtype="torch.float32", numel=1):
        self.device = device
        self.dtype = dtype
        self._numel = numel

    def numel(self):
        return self._numel

    def cpu(self):
        raise RuntimeError("forbidden: cpu()")

    def cuda(self):
        raise RuntimeError("forbidden: cuda()")

    def to(self, *args, **kwargs):
        raise RuntimeError("forbidden: to()")

    def item(self):
        raise RuntimeError("forbidden: item()")

    def clone(self):
        raise RuntimeError("forbidden: clone()")

    def numpy(self):
        raise RuntimeError("forbidden: numpy()")


# ---------------------------------------------------------------------------
# Fake forward wrappers with __wrapped__
# ---------------------------------------------------------------------------

def _make_wrapped_forward(base_fn, qualname):
    """Create a wrapper function with __wrapped__ attribute."""
    import functools
    @functools.wraps(base_fn)
    def wrapper(*args, **kwargs):
        return base_fn(*args, **kwargs)
    wrapper.__qualname__ = qualname
    return wrapper


# ---------------------------------------------------------------------------
# Fake Module stubs
# ---------------------------------------------------------------------------

class _FakeDiffusionModel:
    """Minimal diffusion model stand-in with parameters/buffers."""
    def __init__(self, params=None, buffers=None):
        self._params = params or []
        self._buffers = buffers or []

    def parameters(self, recurse=True):
        return iter(self._params)

    def buffers(self, recurse=True):
        return iter(self._buffers)

    def forward(self, *args, **kwargs):
        return None


class _FakeModel:
    """Mimics BaseModel with .diffusion_model and device."""
    def __init__(self, diffusion_model=None, device="cpu"):
        self.diffusion_model = diffusion_model or _FakeDiffusionModel()
        self.device = device
        self.manual_cast_dtype = None
        self.model_loaded_weight_memory = 123456
        self.model_lowvram = False
        self.lowvram_patch_counter = 0


class _FakeUNETPatcher:
    """Mimics ComfyUI ModelPatcher for UNET."""
    def __init__(self, model=None, load_device="cpu", offload_device="cpu"):
        self.model = model or _FakeModel()
        self.load_device = load_device
        self.offload_device = offload_device

    def model_dtype(self):
        return "torch.float32"


class _FakeUNETPatcherNoMethod:
    """Patcher without model_dtype()."""
    def __init__(self):
        self.model = _FakeModel()
        self.load_device = "cpu"
        self.offload_device = "cpu"

    # no model_dtype method


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCollectorIdentity(unittest.TestCase):
    """Collector identity fields."""

    def test_identity_fields_present(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        state = collect_unet_forward_probe_state(patcher)

        self.assertEqual(state["patcher_object_id"], str(id(patcher)))
        self.assertEqual(state["model_object_id"], str(id(model)))
        self.assertEqual(state["diffusion_model_object_id"], str(id(dm)))
        self.assertIsInstance(state["collector_duration_ms"], float)

    def test_absent_model(self):
        patcher = object()  # no .model at all
        state = collect_unet_forward_probe_state(patcher)
        self.assertEqual(state["model_object_id"], "absent")
        self.assertEqual(state["model_type"], "absent")
        self.assertEqual(state["diffusion_model_object_id"], "absent")
        self.assertEqual(state["diffusion_model_type"], "absent")


class TestCollectorModelState(unittest.TestCase):
    """Model state fields."""

    def test_model_state_fields(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm, device="cuda:0")
        patcher = _FakeUNETPatcher(model=model, load_device="cuda:0", offload_device="cpu")
        state = collect_unet_forward_probe_state(patcher)

        self.assertEqual(state["load_device"], "cuda:0")
        self.assertEqual(state["offload_device"], "cpu")
        self.assertEqual(state["model_device"], "cuda:0")
        self.assertEqual(state["model_dtype"], "torch.float32")
        self.assertEqual(state["model_loaded_weight_memory"], "123456")
        self.assertEqual(state["model_lowvram"], "False")
        self.assertEqual(state["lowvram_patch_counter"], "0")

    def test_model_dtype_absent_when_not_callable(self):
        patcher = _FakeUNETPatcherNoMethod()
        state = collect_unet_forward_probe_state(patcher)
        self.assertEqual(state["model_dtype"], "absent")

    def test_absent_model_state(self):
        patcher = object()
        state = collect_unet_forward_probe_state(patcher)
        self.assertEqual(state["load_device"], "absent")
        self.assertEqual(state["offload_device"], "absent")
        self.assertEqual(state["model_device"], "absent")
        self.assertEqual(state["model_dtype"], "absent")
        self.assertEqual(state["manual_cast_dtype"], "absent")
        self.assertEqual(state["model_loaded_weight_memory"], "absent")
        self.assertEqual(state["model_lowvram"], "absent")
        self.assertEqual(state["lowvram_patch_counter"], "absent")


class TestCollectorParameterDistribution(unittest.TestCase):
    """Parameter distribution fields."""

    def test_cpu_fp32_distribution(self):
        params = [
            _SafeFakeTensor(device="cpu", dtype="torch.float32", numel=1000),
            _SafeFakeTensor(device="cpu", dtype="torch.float32", numel=2000),
            _SafeFakeTensor(device="cpu", dtype="torch.float32", numel=3000),
        ]
        dm = _FakeDiffusionModel(params=params)
        patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm))
        state = collect_unet_forward_probe_state(patcher)

        self.assertEqual(state["param_count"], 3)
        self.assertEqual(state["total_param_numel"], 6000)
        self.assertEqual(state["param_dev_dtype_count"], {"cpu|torch.float32": 3})
        self.assertEqual(state["param_dev_dtype_numel"], {"cpu|torch.float32": 6000})

    def test_bf16_distribution(self):
        params = [
            _SafeFakeTensor(device="cpu", dtype="torch.bfloat16", numel=500),
            _SafeFakeTensor(device="cpu", dtype="torch.bfloat16", numel=1500),
        ]
        dm = _FakeDiffusionModel(params=params)
        patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm))
        state = collect_unet_forward_probe_state(patcher)

        self.assertEqual(state["param_count"], 2)
        self.assertEqual(state["total_param_numel"], 2000)
        self.assertEqual(state["param_dev_dtype_count"], {"cpu|torch.bfloat16": 2})

    def test_mixed_device_dtype_distribution(self):
        params = [
            _SafeFakeTensor(device="cpu", dtype="torch.float32", numel=100),
            _SafeFakeTensor(device="cpu", dtype="torch.bfloat16", numel=200),
            _SafeFakeTensor(device="cuda:0", dtype="torch.float32", numel=300),
            _SafeFakeTensor(device="cuda:0", dtype="torch.float32", numel=400),
        ]
        dm = _FakeDiffusionModel(params=params)
        patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm))
        state = collect_unet_forward_probe_state(patcher)

        self.assertEqual(state["param_count"], 4)
        self.assertEqual(state["total_param_numel"], 1000)
        self.assertEqual(state["param_dev_dtype_count"], {
            "cpu|torch.float32": 1,
            "cpu|torch.bfloat16": 1,
            "cuda:0|torch.float32": 2,
        })
        self.assertEqual(state["param_dev_dtype_numel"], {
            "cpu|torch.float32": 100,
            "cpu|torch.bfloat16": 200,
            "cuda:0|torch.float32": 700,
        })

    def test_zero_parameter_model(self):
        dm = _FakeDiffusionModel(params=[])  # no params
        patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm))
        state = collect_unet_forward_probe_state(patcher)

        self.assertEqual(state["param_count"], 0)
        self.assertEqual(state["total_param_numel"], 0)
        self.assertEqual(state["param_dev_dtype_count"], {})
        self.assertEqual(state["param_dev_dtype_numel"], {})

    def test_deterministic_distribution_hash(self):
        params = [
            _SafeFakeTensor(device="cpu", dtype="torch.float32", numel=100),
            _SafeFakeTensor(device="cpu", dtype="torch.bfloat16", numel=200),
        ]
        dm1 = _FakeDiffusionModel(params=params)
        dm2 = _FakeDiffusionModel(params=params)
        p1 = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm1))
        p2 = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm2))

        s1 = collect_unet_forward_probe_state(p1)
        s2 = collect_unet_forward_probe_state(p2)

        self.assertEqual(s1["param_distribution_hash"], s2["param_distribution_hash"])
        self.assertIsInstance(s1["param_distribution_hash"], str)
        self.assertEqual(len(s1["param_distribution_hash"]), 64)  # SHA-256 hex

    def test_diffusion_model_override(self):
        """Supplied diffusion_model is used instead of resolving."""
        default_dm = _FakeDiffusionModel(params=[_SafeFakeTensor(numel=10)])
        override_dm = _FakeDiffusionModel(params=[_SafeFakeTensor(numel=99)])
        patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=default_dm))
        state = collect_unet_forward_probe_state(patcher, diffusion_model=override_dm)

        self.assertEqual(state["diffusion_model_object_id"], str(id(override_dm)))
        self.assertEqual(state["total_param_numel"], 99)


class TestCollectorBufferDistribution(unittest.TestCase):
    """Separate buffer distribution fields."""

    def test_separate_buffer_distribution(self):
        params = [_SafeFakeTensor(device="cpu", dtype="torch.float32", numel=100)]
        buffers = [_SafeFakeTensor(device="cpu", dtype="torch.float32", numel=50)]
        dm = _FakeDiffusionModel(params=params, buffers=buffers)
        patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm))
        state = collect_unet_forward_probe_state(patcher)

        # Parameters
        self.assertEqual(state["param_count"], 1)
        self.assertEqual(state["total_param_numel"], 100)
        # Buffers
        self.assertEqual(state["buffer_count"], 1)
        self.assertEqual(state["total_buffer_numel"], 50)
        self.assertEqual(state["buffer_dev_dtype_count"], {"cpu|torch.float32": 1})
        self.assertEqual(state["buffer_dev_dtype_numel"], {"cpu|torch.float32": 50})

    def test_zero_buffer_model(self):
        dm = _FakeDiffusionModel(buffers=[])
        patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm))
        state = collect_unet_forward_probe_state(patcher)

        self.assertEqual(state["buffer_count"], 0)
        self.assertEqual(state["total_buffer_numel"], 0)

    def test_buffer_distribution_hash(self):
        buffers = [_SafeFakeTensor(device="cpu", dtype="torch.float32", numel=50)]
        dm = _FakeDiffusionModel(buffers=buffers)
        patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm))
        state = collect_unet_forward_probe_state(patcher)

        self.assertIsInstance(state["buffer_distribution_hash"], str)
        self.assertEqual(len(state["buffer_distribution_hash"]), 64)


class TestCollectorForwardStructure(unittest.TestCase):
    """Forward callable structure fields."""

    def test_forward_module_and_qualname(self):
        dm = _FakeDiffusionModel()
        patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm))
        state = collect_unet_forward_probe_state(patcher)

        self.assertEqual(state["forward_module"], "_FakeDiffusionModel")
        self.assertEqual(state["forward_qualname"], "_FakeDiffusionModel.forward")
        self.assertEqual(state["wrapper_chain"], [])

    def test_no_diffusion_model_forward(self):
        patcher = object()
        state = collect_unet_forward_probe_state(patcher)
        self.assertEqual(state["forward_module"], "absent")
        self.assertEqual(state["forward_qualname"], "absent")
        self.assertEqual(state["wrapper_chain"], [])

    def test_wrapper_chain(self):
        """Simple wrapper chain via __wrapped__."""
        base_fn = _FakeDiffusionModel.forward
        wrapped1 = _make_wrapped_forward(base_fn, "wrapper1")
        wrapped2 = _make_wrapped_forward(wrapped1, "wrapper2")

        dm = _FakeDiffusionModel()
        dm.forward = wrapped2
        patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm))
        state = collect_unet_forward_probe_state(patcher)

        # The collector records __wrapped__ targets, not the outermost fn
        self.assertEqual(state["wrapper_chain"], ["wrapper1", "_FakeDiffusionModel.forward"])

    def test_wrapper_depth_limit(self):
        """More than 8 wrappers — only 8 recorded."""
        base_fn = _FakeDiffusionModel.forward
        fn = base_fn
        for i in range(12):
            fn = _make_wrapped_forward(fn, f"wrapper{i}")

        dm = _FakeDiffusionModel()
        dm.forward = fn
        patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm))
        state = collect_unet_forward_probe_state(patcher)

        self.assertLessEqual(len(state["wrapper_chain"]), 8)

    def test_deterministic_wrapper_chain_hash(self):
        base_fn = _FakeDiffusionModel.forward
        w1 = _make_wrapped_forward(base_fn, "wrapA")
        w2 = _make_wrapped_forward(w1, "wrapB")

        dm1 = _FakeDiffusionModel(); dm1.forward = w2
        dm2 = _FakeDiffusionModel(); dm2.forward = w2
        p1 = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm1))
        p2 = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm2))

        s1 = collect_unet_forward_probe_state(p1)
        s2 = collect_unet_forward_probe_state(p2)

        self.assertEqual(s1["wrapper_chain_hash"], s2["wrapper_chain_hash"])


class TestCollectorSafety(unittest.TestCase):
    """Hard safety: never call forbidden methods on tensors."""

    def test_fake_tensors_raise_on_forbidden_methods(self):
        """Use raising fake tensors — collector must not trigger them."""
        params = [_RaisingFakeTensor(device="cpu", dtype="torch.float32", numel=100)]
        buffers = [_RaisingFakeTensor(device="cpu", dtype="torch.float32", numel=50)]
        dm = _FakeDiffusionModel(params=params, buffers=buffers)

        # Must not raise any RuntimeError from forbidden tensor methods
        try:
            patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm))
            state = collect_unet_forward_probe_state(patcher)
        except RuntimeError as e:
            self.fail(f"collector called a forbidden tensor method: {e}")

        self.assertEqual(state["param_count"], 1)
        self.assertEqual(state["total_param_numel"], 100)
        self.assertEqual(state["buffer_count"], 1)
        self.assertEqual(state["total_buffer_numel"], 50)

    def test_no_tensor_content_access(self):
        """Verify we only access .device, .dtype, .numel() — no content."""
        params = [_RaisingFakeTensor(device="cpu", dtype="torch.float32", numel=100)]
        dm = _FakeDiffusionModel(params=params)
        patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm))

        # Should succeed without triggering any forbidden methods
        state = collect_unet_forward_probe_state(patcher)
        self.assertIn("param_count", state)

    def test_no_cuda_synchronize(self):
        """No torch.cuda.synchronize() call needed — pure Python attribute access."""
        # The collector only reads .device, .dtype, .numel() — no synchronize needed.
        # Verify by importing torch and checking torch.cuda.synchronize is never called.
        try:
            import torch
            with patch.object(torch.cuda, "synchronize") as mock_sync:
                params = [_SafeFakeTensor(device="cpu", dtype="torch.float32", numel=10)]
                dm = _FakeDiffusionModel(params=params)
                patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm))
                state = collect_unet_forward_probe_state(patcher)
                mock_sync.assert_not_called()
                self.assertEqual(state["param_count"], 1)
        except ImportError:
            # No real torch — can't patch, skip verification
            params = [_SafeFakeTensor(device="cpu", dtype="torch.float32", numel=10)]
            dm = _FakeDiffusionModel(params=params)
            patcher = _FakeUNETPatcher(model=_FakeModel(diffusion_model=dm))
            state = collect_unet_forward_probe_state(patcher)
            self.assertEqual(state["param_count"], 1)


class TestCollectorMissingFields(unittest.TestCase):
    """Missing optional fields produce 'absent' values."""

    def test_missing_manual_cast_dtype(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        # Delete optional attribute
        if hasattr(model, "manual_cast_dtype"):
            del model.manual_cast_dtype
        patcher = _FakeUNETPatcher(model=model)
        state = collect_unet_forward_probe_state(patcher)
        self.assertEqual(state["manual_cast_dtype"], "absent")

    def test_missing_memory_fields(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        for attr in ("model_loaded_weight_memory", "model_lowvram", "lowvram_patch_counter"):
            if hasattr(model, attr):
                delattr(model, attr)
        patcher = _FakeUNETPatcher(model=model)
        state = collect_unet_forward_probe_state(patcher)
        self.assertEqual(state["model_loaded_weight_memory"], "absent")
        self.assertEqual(state["model_lowvram"], "absent")
        self.assertEqual(state["lowvram_patch_counter"], "absent")


class TestCollectorTiming(unittest.TestCase):
    """Collector metadata timing."""

    def test_collector_duration_ms_positive(self):
        patcher = _FakeUNETPatcher()
        state = collect_unet_forward_probe_state(patcher)
        self.assertGreaterEqual(state["collector_duration_ms"], 0.0)
        self.assertIsInstance(state["collector_duration_ms"], float)
        self.assertLess(state["collector_duration_ms"], 60000.0)  # sane upper bound
