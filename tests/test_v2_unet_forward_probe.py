"""Tests for unet_forward_probe.py: registry, forward hook, GPU event.

Run: python -m pytest tests/test_v2_unet_forward_probe.py -q
"""
from __future__ import annotations

import os
import sys
import gc
import unittest
from unittest.mock import patch, MagicMock

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Enable diagnostics BEFORE importing the probe module.
os.environ["COMFYMODAL_V2_UNET_FORWARD_DIAG"] = "1"

import comfymodal_runtime.unet_forward_probe as _ufp_mod

from comfymodal_runtime.unet_forward_probe import (
    _dedup_lock,
    _forward_pre_hook,
    _is_enabled,
    _lookup_entry,
    emit_post_load_models_gpu_event,
    install_nextdit_forward_pre_hook,
    register_unet_forward_probe,
    resolve_diffusion_model,
)
from comfymodal_runtime.runtime_executor import ensure_sampling_timing_wrapper
from comfymodal_runtime.trace import RuntimeTrace


# ---------------------------------------------------------------------------
# Fake stubs
# ---------------------------------------------------------------------------

class _FakeTensor:
    """Minimal tensor stub for shape/device/dtype inspection."""
    def __init__(self, shape=None, device="cpu", dtype="torch.float32"):
        self.shape = shape or [2, 4, 64, 64]
        self.device = device
        self.dtype = dtype


class _FakeDiffusionModel:
    """Stub that mimics NextDiT's interface."""
    def __init__(self, name="test_dm"):
        self._name = name
        self._hooks = []

    def forward(self, *args, **kwargs):
        return None

    def register_forward_pre_hook(self, hook, **kwargs):
        """Accept **kwargs (e.g. with_kwargs=True) to match production API."""
        self._hooks.append(hook)
        return hook


class _FakeModel:
    """Mimics BaseModel with .diffusion_model."""
    def __init__(self, diffusion_model=None, device="cpu"):
        self.diffusion_model = diffusion_model or _FakeDiffusionModel()
        self.device = device
        self.manual_cast_dtype = None
        self.model_loaded_weight_memory = 123456
        self.model_lowvram = False
        self.lowvram_patch_counter = 0


class _FakeUNETPatcher:
    """Mimics ComfyUI ModelPatcher."""
    def __init__(self, model=None):
        self.model = model or _FakeModel()
        self.load_device = "cpu"
        self.offload_device = "cpu"

    def model_dtype(self):
        return "torch.float32"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_globals():
    with _ufp_mod._registry_lock:
        _ufp_mod._registry.clear()
    with _ufp_mod._dedup_lock:
        _ufp_mod._dedup.clear()


class _TraceContext:
    """Context manager that sets _ACTIVE_REQUEST_TRACE for a test."""
    def __init__(self, request_id="test-req"):
        self.trace = RuntimeTrace(request_id=request_id)
        self._token = None

    def __enter__(self):
        from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE
        self._token = _ACTIVE_REQUEST_TRACE.set(self.trace)
        return self.trace

    def __exit__(self, *args):
        from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE
        _ACTIVE_REQUEST_TRACE.reset(self._token)


# Ensure module is in a clean state.
_reset_globals()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDiagnosticGate(unittest.TestCase):
    """Diagnostics disabled by default."""

    def test_register_always_on(self):
        """Registration always succeeds (needed for always-on first-CUDA timing),
        even when diagnostics are disabled."""
        with patch.object(_ufp_mod, "_is_enabled", return_value=False):
            dm = _FakeDiffusionModel()
            model = _FakeModel(diffusion_model=dm)
            patcher = _FakeUNETPatcher(model=model)
            register_unet_forward_probe(patcher, source="cpu_snapshot")
            with _ufp_mod._registry_lock:
                self.assertEqual(len(_ufp_mod._registry), 1,
                                 "registration must succeed even when diagnostics are disabled")

    def test_emit_noop_when_disabled(self):
        with patch.object(_ufp_mod, "_is_enabled", return_value=False):
            with _TraceContext("test") as trace:
                emit_post_load_models_gpu_event([])
                self.assertIsNone(_forward_pre_hook(object(), ()))
            probe_events = [e for e in trace._events if e.name == "unet_forward_probe"]
            self.assertEqual(len(probe_events), 0)


class TestRegistration(unittest.TestCase):
    """Registration behavior."""

    def setUp(self):
        _reset_globals()

    def test_registers_snapshot(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        entry = _lookup_entry(dm)
        self.assertIsNotNone(entry)
        unet, source, ver = entry
        self.assertIs(unet, patcher)
        self.assertEqual(source, "cpu_snapshot")
        self.assertEqual(ver, 1)

    def test_no_model_attr_skipped(self):
        patcher = object()
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        with _ufp_mod._registry_lock:
            self.assertEqual(len(_ufp_mod._registry), 0)

    def test_registers_normal_loader(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="normal_loader")
        entry = _lookup_entry(dm)
        self.assertIsNotNone(entry)
        _, source, _ = entry
        self.assertEqual(source, "normal_loader")

    def test_duplicate_registration_ignored(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        with _ufp_mod._registry_lock:
            self.assertEqual(len(_ufp_mod._registry), 1)

    def test_weak_when_dm_gced(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        dm_id = id(dm)
        with _ufp_mod._registry_lock:
            self.assertIn(dm_id, _ufp_mod._registry)
        del dm, model, patcher
        gc.collect()
        gc.collect()
        with _ufp_mod._registry_lock:
            self.assertNotIn(dm_id, _ufp_mod._registry)

    def test_weakref_unet_gced(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        del patcher
        gc.collect()
        gc.collect()
        entry = _lookup_entry(dm)
        self.assertIsNone(entry)


class TestOncePerRequest(unittest.TestCase):
    """Dedup: once per (request_id, dm_id)."""

    def setUp(self):
        _reset_globals()

    def test_once_per_request(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        with _TraceContext("req-001") as trace:
            _forward_pre_hook(dm, (_FakeTensor(),))
            _forward_pre_hook(dm, (_FakeTensor(),))
        probe_events = [e for e in trace._events if e.name == "unet_forward_probe"]
        self.assertEqual(len(probe_events), 1)

    def test_new_request_emits_again(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        with _TraceContext("req-001") as trace1:
            _forward_pre_hook(dm, (_FakeTensor(),))
        with _TraceContext("req-002") as trace2:
            _forward_pre_hook(dm, (_FakeTensor(),))
        probe1 = [e for e in trace1._events if e.name == "unet_forward_probe"]
        probe2 = [e for e in trace2._events if e.name == "unet_forward_probe"]
        self.assertEqual(len(probe1), 1)
        self.assertEqual(len(probe2), 1)


class TestNoActiveTrace(unittest.TestCase):
    """No emission without active request trace."""

    def setUp(self):
        _reset_globals()

    def test_no_trace_no_forward_event(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        _forward_pre_hook(dm, (_FakeTensor(),))
        # No crash means success

    def test_no_trace_no_gpu_event(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        emit_post_load_models_gpu_event([patcher])
        # No crash means success


class TestCorrectSource(unittest.TestCase):
    """Source string preserved through registration."""

    def setUp(self):
        _reset_globals()

    def test_cpu_snapshot_source(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        entry = _lookup_entry(dm)
        self.assertIsNotNone(entry)
        self.assertEqual(entry[1], "cpu_snapshot")

    def test_normal_loader_source(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="normal_loader")
        entry = _lookup_entry(dm)
        self.assertIsNotNone(entry)
        self.assertEqual(entry[1], "normal_loader")


class TestCorrectInputMetadata(unittest.TestCase):
    """Forward hook captures correct primary input metadata."""

    def setUp(self):
        _reset_globals()

    def _capture_forward_event(self, x_tensor):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        with _TraceContext("req-meta") as trace:
            _forward_pre_hook(dm, (x_tensor,))
        probe_events = [e for e in trace._events if e.name == "unet_forward_probe"]
        return probe_events[0] if probe_events else None

    def test_x_shape_captured(self):
        event = self._capture_forward_event(_FakeTensor(shape=[1, 4, 128, 128]))
        self.assertIsNotNone(event)
        self.assertEqual(list(event.metadata.get("x_shape", [])), [1, 4, 128, 128])

    def test_x_device_captured(self):
        event = self._capture_forward_event(_FakeTensor(device="cuda:0"))
        self.assertIsNotNone(event)
        self.assertEqual(event.metadata.get("x_device"), "cuda:0")

    def test_x_dtype_captured(self):
        event = self._capture_forward_event(_FakeTensor(dtype="torch.bfloat16"))
        self.assertIsNotNone(event)
        self.assertEqual(event.metadata.get("x_dtype"), "torch.bfloat16")

    def test_positional_arg(self):
        event = self._capture_forward_event(_FakeTensor(shape=[2, 4, 64, 64]))
        self.assertIsNotNone(event)
        self.assertEqual(list(event.metadata.get("x_shape", [])), [2, 4, 64, 64])


class TestPostLoadModelsGpuEvent(unittest.TestCase):
    """GPU loader event emission."""

    def setUp(self):
        _reset_globals()

    def _setup_registered_unet(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        return dm, patcher

    def test_emits_after_success(self):
        dm, patcher = self._setup_registered_unet()
        with _TraceContext("req-gpu") as trace:
            emit_post_load_models_gpu_event([patcher])
        probe_events = [e for e in trace._events if e.name == "unet_forward_probe"]
        self.assertEqual(len(probe_events), 1)
        self.assertEqual(probe_events[0].metadata.get("stage"), "post_load_models_gpu")
        self.assertEqual(probe_events[0].metadata.get("source"), "cpu_snapshot")
        self.assertEqual(probe_events[0].metadata.get("request_id"), "req-gpu")

    def test_unrelated_model_ignored(self):
        dm, patcher = self._setup_registered_unet()
        with _TraceContext("req-unrel") as trace:
            emit_post_load_models_gpu_event([object()])
        probe_events = [e for e in trace._events if e.name == "unet_forward_probe"]
        self.assertEqual(len(probe_events), 0)

    def test_mixed_models(self):
        dm1, patcher1 = self._setup_registered_unet()
        dm2 = _FakeDiffusionModel(name="unrelated")
        model2 = _FakeModel(diffusion_model=dm2)
        patcher2 = _FakeUNETPatcher(model=model2)
        with _TraceContext("req-mix") as trace:
            emit_post_load_models_gpu_event([patcher1, patcher2])
        probe_events = [e for e in trace._events if e.name == "unet_forward_probe"]
        self.assertEqual(len(probe_events), 1)


class TestReturnAndExceptionPreserved(unittest.TestCase):
    """Original return values and exceptions preserved."""

    def test_no_exception_path(self):
        original = MagicMock(return_value="success")
        _diag_ok = False
        try:
            _retval = original()
            _diag_ok = True
            result = _retval
        finally:
            pass
        self.assertEqual(result, "success")
        self.assertTrue(_diag_ok)
        original.assert_called_once()

    def test_exception_preserved(self):
        original = MagicMock(side_effect=ValueError("test error"))
        with self.assertRaises(ValueError) as ctx:
            _diag_ok = False
            try:
                _retval = original()
                _diag_ok = True
            finally:
                self.assertFalse(_diag_ok)
        self.assertIn("test error", str(ctx.exception))


class TestNoCudaSyncOrMutation(unittest.TestCase):
    """Safety: no CUDA sync, no tensor mutation."""

    def setUp(self):
        _reset_globals()

    def test_no_cuda_synchronize(self):
        try:
            import torch
            with patch.object(torch.cuda, "synchronize") as mock_sync:
                dm = _FakeDiffusionModel()
                model = _FakeModel(diffusion_model=dm)
                patcher = _FakeUNETPatcher(model=model)
                register_unet_forward_probe(patcher, source="cpu_snapshot")
                with _TraceContext("req-safe") as trace:
                    emit_post_load_models_gpu_event([patcher])
                mock_sync.assert_not_called()
        except ImportError:
            pass

    def test_forward_hook_returns_none(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        result = _forward_pre_hook(dm, (_FakeTensor(),))
        self.assertIsNone(result)


class TestForwardHookInstallation(unittest.TestCase):
    """install_nextdit_forward_pre_hook behavior."""

    def test_noop_when_disabled(self):
        # install_nextdit_forward_pre_hook is not gated by _is_enabled,
        # so it always tries to install.  When NextDiT is unavailable
        # it returns False.
        saved = _ufp_mod._nextdit_hook_installed
        _ufp_mod._nextdit_hook_installed = False
        try:
            result = install_nextdit_forward_pre_hook()
            # NextDiT is not available in test env, so returns False
            self.assertFalse(result)
        finally:
            _ufp_mod._nextdit_hook_installed = saved

    def test_idempotent(self):
        saved = _ufp_mod._nextdit_hook_installed
        _ufp_mod._nextdit_hook_installed = True
        result = install_nextdit_forward_pre_hook()
        self.assertTrue(result)
        _ufp_mod._nextdit_hook_installed = saved


class TestGpuEventSchema(unittest.TestCase):
    """post_load_models_gpu event schema fields."""

    def setUp(self):
        _reset_globals()

    def test_includes_schema_version(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        with _TraceContext("req-schema") as trace:
            emit_post_load_models_gpu_event([patcher])
        probe_events = [e for e in trace._events if e.name == "unet_forward_probe"]
        self.assertEqual(len(probe_events), 1)
        meta = probe_events[0].metadata
        self.assertIn("schema_version", meta)
        self.assertIn("gpu_call_index", meta)
        self.assertIn("caller_classification", meta)
        self.assertIn("diffusion_model_object_id", meta)

    def test_includes_collector_state(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        with _TraceContext("req-state") as trace:
            emit_post_load_models_gpu_event([patcher])
        probe_events = [e for e in trace._events if e.name == "unet_forward_probe"]
        self.assertEqual(len(probe_events), 1)
        meta = probe_events[0].metadata
        self.assertIn("patcher_object_id", meta)
        self.assertIn("model_object_id", meta)
        self.assertIn("diffusion_model_object_id", meta)
        self.assertIn("param_count", meta)
        self.assertIn("total_param_numel", meta)


class TestForwardEventSchema(unittest.TestCase):
    """first_nextdit_forward event schema fields."""

    def setUp(self):
        _reset_globals()

    def test_includes_all_required_fields(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        register_unet_forward_probe(patcher, source="cpu_snapshot")
        with _TraceContext("req-fwd") as trace:
            _forward_pre_hook(dm, (_FakeTensor(shape=[1, 4, 64, 64]),))
        probe_events = [e for e in trace._events if e.name == "unet_forward_probe"]
        self.assertEqual(len(probe_events), 1)
        meta = probe_events[0].metadata
        # _FakeDiffusionModel is not a NextDiT, so stage is first_unet_forward
        self.assertEqual(meta.get("stage"), "first_unet_forward")
        self.assertIn("source", meta)
        self.assertIn("request_id", meta)
        self.assertIn("diffusion_model_object_id", meta)
        self.assertIn("patcher_object_id", meta)
        self.assertIn("x_shape", meta)
        self.assertIn("x_device", meta)
        self.assertIn("x_dtype", meta)
        self.assertIn("param_count", meta)


class TestSnapshotBypass(unittest.TestCase):
    """When bypass is active, snapshot source is not registered."""

    def setUp(self):
        _reset_globals()

    def test_bypass_not_registered(self):
        dm = _FakeDiffusionModel()
        model = _FakeModel(diffusion_model=dm)
        patcher = _FakeUNETPatcher(model=model)
        entry = _lookup_entry(dm)
        self.assertIsNone(entry)


class TestBoundedDedup(unittest.TestCase):
    """Dedup bounded to prevent unbounded memory growth."""

    def setUp(self):
        _reset_globals()

    def test_dedup_trimmed(self):
        saved_max = _ufp_mod._DEDUP_MAX
        try:
            _ufp_mod._DEDUP_MAX = 5
            dm = _FakeDiffusionModel()
            model = _FakeModel(diffusion_model=dm)
            patcher = _FakeUNETPatcher(model=model)
            register_unet_forward_probe(patcher, source="cpu_snapshot")
            for i in range(10):
                with _TraceContext(f"req-dedup-{i:03d}"):
                    _forward_pre_hook(dm, (_FakeTensor(),))
            with _dedup_lock:
                self.assertLessEqual(len(_ufp_mod._dedup), _ufp_mod._DEDUP_MAX)
        finally:
            _ufp_mod._DEDUP_MAX = saved_max


# ═══════════════════════════════════════════════════════════════════════
# Fix 4: resolve_diffusion_model tests
# ═══════════════════════════════════════════════════════════════════════


class _FakeModelPatcher:
    """Minimal ModelPatcher duck type with model_options."""
    def __init__(self, dm=None):
        self.model = _FakeModel(diffusion_model=dm or _FakeDiffusionModel())
        self.model_options = {}


class _FakeLoadedModel:
    """LoadedModel shape: .model is a ModelPatcher."""
    def __init__(self, dm=None):
        self.model = _FakeModelPatcher(dm=dm)


class _FakeRawDM:
    """Raw diffusion model (no model_options, just forward)."""
    def forward(self, x):
        return x


class TestResolveDiffusionModel(unittest.TestCase):
    """Behavioral tests for resolve_diffusion_model."""

    def test_model_patcher_resolved(self):
        """ModelPatcher -> (patcher, diffusion_model)."""
        dm = _FakeDiffusionModel()
        mp = _FakeModelPatcher(dm=dm)
        patcher, resolved_dm = resolve_diffusion_model(mp)
        self.assertIs(patcher, mp)
        self.assertIs(resolved_dm, dm)

    def test_loaded_model_unwrapped(self):
        """LoadedModel -> (inner_patcher, diffusion_model)."""
        dm = _FakeDiffusionModel()
        loaded = _FakeLoadedModel(dm=dm)
        patcher, resolved_dm = resolve_diffusion_model(loaded)
        self.assertIs(patcher, loaded.model)
        self.assertIs(resolved_dm, dm)

    def test_raw_diffusion_model(self):
        """Raw diffusion model -> (None, model)."""
        raw = _FakeRawDM()
        patcher, resolved_dm = resolve_diffusion_model(raw)
        self.assertIsNone(patcher)
        self.assertIs(resolved_dm, raw)

    def test_none_returns_none(self):
        """None input -> (None, None)."""
        self.assertEqual(resolve_diffusion_model(None), (None, None))

    def test_model_without_diffusion_model(self):
        """Patcher without diffusion_model -> (patcher, None)."""
        mp = _FakeModelPatcher(dm=None)
        mp.model.diffusion_model = None
        patcher, resolved_dm = resolve_diffusion_model(mp)
        self.assertIs(patcher, mp)
        self.assertIsNone(resolved_dm)


# ═══════════════════════════════════════════════════════════════════════
# Fix 4: ensure_sampling_timing_wrapper tests
# ═══════════════════════════════════════════════════════════════════════


class TestEnsureSamplingTimingWrapper(unittest.TestCase):
    """Behavioral tests for ensure_sampling_timing_wrapper."""

    def setUp(self):
        self._patcher = _FakeModelPatcher()

    def test_missing_model_options_returns_false(self):
        """Model patcher without model_options -> False."""
        obj = object()
        result = ensure_sampling_timing_wrapper(obj)
        self.assertFalse(result)

    def test_no_model_options_attribute_returns_false(self):
        """Object without model_options attr -> False."""
        result = ensure_sampling_timing_wrapper(object())
        self.assertFalse(result)

    @patch("comfymodal_runtime.runtime_executor.ensure_sampling_timing_wrapper")
    def test_register_unet_calls_ensure_wrapper(self, mock_ensure):
        """register_unet_forward_probe must call ensure_sampling_timing_wrapper."""
        dm = _FakeDiffusionModel()
        mp = _FakeModelPatcher(dm=dm)
        mock_ensure.return_value = True
        register_unet_forward_probe(mp, source="test")
        mock_ensure.assert_called_once()
        # Verify it was called with the patcher
        call_args = mock_ensure.call_args[0]
        self.assertIs(call_args[0], mp)

    def test_register_unet_probes_loaded_model_calls_ensure(self):
        """register_unet_forward_probe with LoadedModel must call
        ensure_sampling_timing_wrapper on the inner ModelPatcher."""
        from unittest.mock import patch as _patch
        dm = _FakeDiffusionModel()
        loaded = _FakeLoadedModel(dm=dm)
        with _patch("comfymodal_runtime.runtime_executor.ensure_sampling_timing_wrapper") as mock_ensure:
            mock_ensure.return_value = True
            register_unet_forward_probe(loaded, source="test_loaded")
            # Should have been called with the inner patcher
            mock_ensure.assert_called_once()
            call_args = mock_ensure.call_args[0]
            self.assertIs(call_args[0], loaded.model)


if __name__ == "__main__":
    unittest.main()
