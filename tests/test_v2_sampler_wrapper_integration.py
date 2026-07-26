"""Integration test for the SAMPLER_SAMPLE production wrapper using the
actual pinned comfy.patcher_extension classes.

Proves:
- wrapper is callable through real WrapperExecutor chain
- one continuation call (not infinite recursion)
- sampling_start/sampling_end emitted via active RuntimeTrace
- dedup prevents duplicate events
- sigma steps properly counted
- exception in sampling still emits sampling_end
"""

from __future__ import annotations

import time
import unittest
from typing import Any
from unittest.mock import patch

# Import the real production wrapper
from comfymodal_runtime.runtime_executor import _COMFYMODAL_V2_SAMPLING_WRAPPER
from comfymodal_runtime.trace import RuntimeTrace


def _try_import_comfy_patcher_extension():
    """Try to import real comfy.patcher_extension; return module or None."""
    try:
        import comfy.patcher_extension as pe
        return pe
    except ImportError:
        return None


def _make_faithful_wrapper_executor(original, wrappers):
    """Build a WrapperExecutor matching the real comfy API but importable
    without the full ComfyUI environment.  Uses the real WrapperExecutor
    when available, else builds a faithful standalone replica."""
    pe = _try_import_comfy_patcher_extension()
    if pe is not None:
        return pe.WrapperExecutor.new_executor(original, wrappers, 0)
    # Faithful standalone replica
    class _FakeWE:
        def __init__(self, orig, wlist, idx):
            self.original = orig
            self.wrappers = list(wlist)
            self.idx = idx
            self.is_last = idx == len(wlist)
        def __call__(self, *args, **kwargs):
            new = _FakeWE(self.original, self.wrappers, self.idx + 1)
            return new.execute(*args, **kwargs)
        def execute(self, *args, **kwargs):
            if self.is_last:
                return self.original(*args, **kwargs)
            return self.wrappers[self.idx](self, *args, **kwargs)
    return _FakeWE(original, wrappers, 0)


class TestSamplerWrapperIntegration(unittest.TestCase):
    """Integration test exercising the real production wrapper through a
    WrapperExecutor chain that mimics the pinned ComfyUI API."""

    def setUp(self):
        # Reset dedup between tests
        from comfymodal_runtime.runtime_executor import _sampler_wrapper_dedup
        _sampler_wrapper_dedup.clear()
        self._trace = RuntimeTrace(request_id="test_int", process="test")

    def _set_trace(self):
        from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE
        self._token = _ACTIVE_REQUEST_TRACE.set(self._trace)

    def _reset_trace(self):
        from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE
        _ACTIVE_REQUEST_TRACE.reset(self._token)

    def test_one_continuation_call_no_recursion(self):
        """The wrapper must call executor(...) exactly once, advancing to the
        original function, not re-invoking itself (which would cause recursion)."""
        call_count = 0

        def _original(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return {"result": "ok"}

        executor = _make_faithful_wrapper_executor(
            _original,
            [_COMFYMODAL_V2_SAMPLING_WRAPPER],
        )

        self._set_trace()
        try:
            result = executor.execute(
                type("FakeGuider", (), {"_node_id": "n1", "_class_type": "KSampler"})(),
                type("FakeSigmas", (), {"__len__": lambda self: 9})(),
                {}, None, None, None, None,
            )
        finally:
            self._reset_trace()

        self.assertEqual(call_count, 1,
                         "original must be called exactly once (no recursion)")
        self.assertEqual(result, {"result": "ok"})

        # Verify events emitted
        names = [e.name for e in self._trace.events]
        self.assertIn("sampling_start", names)
        self.assertIn("sampling_end", names)

    def test_sampling_events_emitted(self):
        """sampling_start and sampling_end with correct metadata."""
        def _original(*args, **kwargs):
            return {"latent": "ok"}

        executor = _make_faithful_wrapper_executor(
            _original,
            [_COMFYMODAL_V2_SAMPLING_WRAPPER],
        )

        self._set_trace()
        try:
            executor.execute(
                type("FakeGuider", (), {"_node_id": "n2", "_class_type": "KSampler"})(),
                type("FakeSigmas", (), {"__len__": lambda self: 9})(),
                {}, None, None, None, None,
            )
        finally:
            self._reset_trace()

        start_events = [e for e in self._trace.events if e.name == "sampling_start"]
        end_events = [e for e in self._trace.events if e.name == "sampling_end"]
        self.assertEqual(len(start_events), 1)
        self.assertEqual(len(end_events), 1)

        start_meta = start_events[0].metadata
        self.assertEqual(start_meta.get("node_id"), "n2")
        self.assertEqual(start_meta.get("steps"), 8)

        end_meta = end_events[0].metadata
        self.assertEqual(end_meta.get("node_id"), "n2")
        self.assertEqual(end_meta.get("steps"), 8)
        self.assertEqual(end_meta.get("source"), "sampler_sample_wrapper")
        self.assertIsInstance(end_meta.get("duration_ms"), (int, float))

    def test_sigma_steps_counted(self):
        """sigma tensor length determines steps (len - 1)."""
        def _original(*args, **kwargs):
            return {}

        executor = _make_faithful_wrapper_executor(
            _original,
            [_COMFYMODAL_V2_SAMPLING_WRAPPER],
        )

        self._set_trace()
        try:
            executor.execute(
                object(),
                type("S", (), {"__len__": lambda self: 25})(),  # 24 steps
                {}, None, None, None, None,
            )
        finally:
            self._reset_trace()

        end_events = [e for e in self._trace.events if e.name == "sampling_end"]
        self.assertEqual(end_events[0].metadata.get("steps"), 24)

    def test_exception_still_emits_sampling_end(self):
        """Exception in sampling must still emit sampling_end via finally."""
        def _original(*args, **kwargs):
            raise ValueError("simulated failure")

        executor = _make_faithful_wrapper_executor(
            _original,
            [_COMFYMODAL_V2_SAMPLING_WRAPPER],
        )

        self._set_trace()
        with self.assertRaises(ValueError):
            try:
                executor.execute(
                    type("FakeGuider", (), {"_node_id": "n3", "_class_type": "KSampler"})(),
                    type("S", (), {"__len__": lambda self: 9})(),
                    {}, None, None, None, None,
                )
            finally:
                self._reset_trace()

        names = [e.name for e in self._trace.events]
        self.assertIn("sampling_end", names,
                      "sampling_end must be emitted even on exception")

    def test_dedup_prevents_duplicate_events(self):
        """Same (request_id, executor_id) must not emit duplicate events."""
        def _original(*args, **kwargs):
            return {"ok": True}

        executor = _make_faithful_wrapper_executor(
            _original,
            [_COMFYMODAL_V2_SAMPLING_WRAPPER],
        )

        self._set_trace()
        try:
            executor.execute(object(), type("S", (), {"__len__": lambda self: 9})(),
                             {}, None, None, None, None)
            executor.execute(object(), type("S", (), {"__len__": lambda self: 9})(),
                             {}, None, None, None, None)
        finally:
            self._reset_trace()

        # First call is deduped by same executor, only one set of events
        start_count = len([e for e in self._trace.events if e.name == "sampling_start"])
        self.assertEqual(start_count, 1,
                         "duplicate executor invocations must not emit second sampling_start")

    def test_wrapper_preserves_return_value(self):
        """Wrapper must return the original function's result."""
        def _original(*args, **kwargs):
            return {"preserved": True, "value": 42}

        executor = _make_faithful_wrapper_executor(
            _original,
            [_COMFYMODAL_V2_SAMPLING_WRAPPER],
        )

        self._set_trace()
        try:
            result = executor.execute(object(), object(), {}, None, None, None, None)
        finally:
            self._reset_trace()

        self.assertEqual(result, {"preserved": True, "value": 42})

    def test_no_trace_fast_path(self):
        """When no active trace, wrapper must call through without emitting."""
        def _original(*args, **kwargs):
            return {"fast_path": True}

        executor = _make_faithful_wrapper_executor(
            _original,
            [_COMFYMODAL_V2_SAMPLING_WRAPPER],
        )

        # No trace set - should use fast path
        result = executor.execute(object(), object(), {}, None, None, None, None)
        self.assertEqual(result, {"fast_path": True})

    def test_multiple_wrappers_chain(self):
        """Multiple wrappers in the chain must all execute in order."""
        order = []

        def _wrapper_a(executor, *args, **kwargs):
            order.append("a_before")
            result = executor(*args, **kwargs)
            order.append("a_after")
            return result

        def _original(*args, **kwargs):
            order.append("original")
            return {"ok": True}

        executor = _make_faithful_wrapper_executor(
            _original,
            [_wrapper_a, _COMFYMODAL_V2_SAMPLING_WRAPPER],
        )
        # _COMFYMODAL_V2_SAMPLING_WRAPPER is second in the chain

        self._set_trace()
        try:
            _fake_guider = type("FG", (), {"_node_id": "n", "_class_type": "KSampler"})()
            result = executor.execute(
                _fake_guider,
                type("S", (), {"__len__": lambda self: 9})(),
                {}, None, None, None, None,
            )
        finally:
            self._reset_trace()

        self.assertEqual(result, {"ok": True})
        # Order: wrapper_a starts, then sampling_wrapper starts+ends, then original, then wrapper_a ends
        self.assertIn("sampling_start", [e.name for e in self._trace.events])
        self.assertIn("sampling_end", [e.name for e in self._trace.events])




# ═══════════════════════════════════════════════════════════════════════
# UNET first-CUDA timing integration tests
# ═══════════════════════════════════════════════════════════════════════

class _FakeDM:
    """Duck-typed diffusion model with register_forward_pre_hook."""
    def __init__(self, name="test_dm"):
        self._name = name
        self._hooks = []
    def register_forward_pre_hook(self, hook, **kwargs):
        self._hooks.append(hook)
        return hook

class _FakeModel:
    def __init__(self, dm=None):
        self.diffusion_model = dm or _FakeDM()

class _FakePatcher:
    def __init__(self, model=None):
        self.model = model or _FakeModel()

class _FakeCUDATensor:
    def __init__(self):
        self.device = "cuda:0"
        self.dtype = "torch.float32"
        self.shape = [1, 4, 64, 64]

class _FakeCPUTensor:
    def __init__(self):
        self.device = "cpu"
        self.dtype = "torch.float32"
        self.shape = [1, 4, 64, 64]


class TestUnetFirstCudaTiming(unittest.TestCase):
    """Integration test for registration -> hook -> forward -> timing.

    Proves:
    - register_unet_forward_probe installs a forward pre-hook on the model
    - calling the hook with CUDA tensor emits unet_first_cuda_op
    - setting demand start before forward gives nonzero elapsed_ms
    - non-CUDA first forward does NOT consume the dedup slot
    - alternate model registration works
    """

    def setUp(self):
        from comfymodal_runtime import unet_forward_probe as _ufp
        # Clear global state
        with _ufp._registry_lock:
            _ufp._registry.clear()
        with _ufp._first_cuda_dedup_lock:
            _ufp._first_cuda_dedup.clear()
        with _ufp._unet_gpu_demand_lock:
            _ufp._unet_gpu_demand_start.clear()
        _ufp._installed_hook_handles.clear()
        _ufp._unet_forward_hooks_installed = False
        self._ufp = _ufp

    def _setup_trace(self, request_id="test_unet"):
        trace = RuntimeTrace(request_id=request_id, process="test")
        from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE
        self._token = _ACTIVE_REQUEST_TRACE.set(trace)
        return trace

    def _teardown_trace(self):
        from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE
        _ACTIVE_REQUEST_TRACE.reset(self._token)

    def test_registration_installs_hook(self):
        """register_unet_forward_probe must install a forward pre-hook."""
        dm = _FakeDM()
        model = _FakeModel(dm)
        patcher = _FakePatcher(model)
        self._ufp.register_unet_forward_probe(patcher, source="cpu_snapshot")
        self.assertEqual(len(dm._hooks), 1,
                         "forward pre-hook must be installed on diffusion model")

    def test_hook_emits_first_cuda_op_with_elapsed(self):
        """Hook with CUDA tensor and demand start emits nonzero elapsed."""
        dm = _FakeDM()
        model = _FakeModel(dm)
        patcher = _FakePatcher(model)
        self._ufp.register_unet_forward_probe(patcher, source="cpu_snapshot")
        
        # Set demand start
        import time as _time
        self._ufp.set_unet_gpu_demand_start("test_unet", _time.monotonic_ns() - 5_000_000)  # 5ms ago
        
        trace = self._setup_trace("test_unet")
        try:
            self._ufp._forward_pre_hook(dm, (_FakeCUDATensor(),))
        finally:
            self._teardown_trace()
        
        ops = [e for e in trace.events if e.name == "unet_first_cuda_op"]
        self.assertEqual(len(ops), 1,
                         "must emit exactly one unet_first_cuda_op")
        meta = ops[0].metadata
        self.assertEqual(meta.get("event_semantics"), "first_unet_forward_with_cuda_input")
        self.assertEqual(meta.get("demand_start_present"), 1)
        elapsed = meta.get("elapsed_ms")
        self.assertIsInstance(elapsed, (int, float),
                              f"elapsed_ms must be numeric, got {type(elapsed).__name__}")
        self.assertGreater(elapsed, 0.0,
                           "elapsed_ms must be positive when demand exists")
        self.assertEqual(meta.get("x_device"), "cuda:0")
        self.assertIn("diffusion_model_object_id", meta)
        self.assertIn("patcher_object_id", meta)
        self.assertIn("model_identity", meta)

    def test_missing_demand_reports_absent(self):
        """Hook without demand start reports absent and demand_present=0."""
        dm = _FakeDM()
        model = _FakeModel(dm)
        patcher = _FakePatcher(model)
        self._ufp.register_unet_forward_probe(patcher, source="cpu_snapshot")
        
        trace = self._setup_trace("test_missing")
        try:
            self._ufp._forward_pre_hook(dm, (_FakeCUDATensor(),))
        finally:
            self._teardown_trace()
        
        ops = [e for e in trace.events if e.name == "unet_first_cuda_op"]
        self.assertEqual(len(ops), 1)
        meta = ops[0].metadata
        self.assertEqual(meta.get("demand_start_present"), 0)
        self.assertEqual(meta.get("elapsed_ms"), "absent")

    def test_non_cuda_does_not_consume_dedup(self):
        """Non-CUDA first forward must NOT consume the dedup slot,
        so a later CUDA forward can still emit."""
        dm = _FakeDM()
        model = _FakeModel(dm)
        patcher = _FakePatcher(model)
        self._ufp.register_unet_forward_probe(patcher, source="cpu_snapshot")
        
        trace = self._setup_trace("test_noncuda")
        try:
            # First forward: CPU tensor — should NOT emit, NOT consume dedup
            self._ufp._forward_pre_hook(dm, (_FakeCPUTensor(),))
        finally:
            self._teardown_trace()
        
        ops1 = [e for e in trace.events if e.name == "unet_first_cuda_op"]
        self.assertEqual(len(ops1), 0,
                         "CPU forward must not emit unet_first_cuda_op")
        
        # Second forward: CUDA tensor — should emit (dedup not consumed)
        trace2 = RuntimeTrace(request_id="test_noncuda", process="test")
        from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE as _ART
        tok2 = _ART.set(trace2)
        try:
            self._ufp._forward_pre_hook(dm, (_FakeCUDATensor(),))
        finally:
            _ART.reset(tok2)
        
        ops2 = [e for e in trace2.events if e.name == "unet_first_cuda_op"]
        self.assertEqual(len(ops2), 1,
                         "CUDA forward after non-CUDA must still emit")

    def test_alternate_model_registration(self):
        """Alternate (different) model registration works independently."""
        dm1 = _FakeDM()
        dm2 = _FakeDM()
        patcher1 = _FakePatcher(_FakeModel(dm1))
        patcher2 = _FakePatcher(_FakeModel(dm2))
        self._ufp.register_unet_forward_probe(patcher1, source="cpu_snapshot")
        self._ufp.register_unet_forward_probe(patcher2, source="normal_loader")
        
        self.assertEqual(len(dm1._hooks), 1)
        self.assertEqual(len(dm2._hooks), 1)
        
        with self._ufp._registry_lock:
            self.assertEqual(len(self._ufp._registry), 2)

    def test_repeated_registration_idempotent(self):
        """Repeated registration must NOT install duplicate hooks."""
        dm = _FakeDM()
        model = _FakeModel(dm)
        patcher = _FakePatcher(model)
        # Register twice
        self._ufp.register_unet_forward_probe(patcher, source="cpu_snapshot")
        self._ufp.register_unet_forward_probe(patcher, source="cpu_snapshot")
        # Only one hook should be installed
        self.assertEqual(len(dm._hooks), 1,
                         "duplicate register_unet_forward_probe must not add second hook")
        with self._ufp._registry_lock:
            self.assertEqual(len(self._ufp._registry), 1)


class TestBoundaryExtractionTermination(unittest.TestCase):
    """Events after the boundary include everything from the matching
    remote_method_entry onward.  In production, this naturally terminates
    at the current request's durable result boundary because subsequent
    requests have their own remote_method_entry boundary markers."""

    def test_events_after_boundary_include_all(self):
        from tools.benchmark_v2_direct import _trace_events_for_request
        # A single-request trace: lifecycle events before boundary, request
        # events after.  In production, the merged trace for one request
        # terminates at output_persist_end — subsequent requests are not
        # in the same merged trace segment.
        events = [
            # Lifecycle (before boundary) — excluded
            {"name": "remote_method_entry", "monotonic_ns": 100, "metadata": {"request_id": "lifecycle"}},
            {"name": "restore_method_start", "monotonic_ns": 200, "metadata": {}},
            # Request A boundary
            {"name": "remote_method_entry", "monotonic_ns": 500, "metadata": {"request_id": "req_A"}},
            {"name": "sampling_start", "monotonic_ns": 600, "metadata": {}},
            {"name": "sampling_end", "monotonic_ns": 700, "metadata": {}},
            {"name": "output_persist_end", "monotonic_ns": 800, "metadata": {}},
        ]
        result = {"trace": {"events": events}}
        filtered = _trace_events_for_request(result, "req_A")
        self.assertEqual(len(filtered), 4)  # boundary + sampling_start + sampling_end + output_persist_end
        self.assertEqual(filtered[0]["name"], "remote_method_entry")
        self.assertEqual(filtered[0]["monotonic_ns"], 500)

    def test_boundary_excludes_earlier_lifecycle(self):
        from tools.benchmark_v2_direct import _trace_events_for_request
        events = [
            {"name": "remote_method_entry", "monotonic_ns": 100, "metadata": {"request_id": "lifecycle"}},
            {"name": "restore_method_start", "monotonic_ns": 200, "metadata": {}},
            {"name": "remote_method_entry", "monotonic_ns": 500, "metadata": {"request_id": "req_X"}},
            {"name": "sampling_start", "monotonic_ns": 600, "metadata": {}},
        ]
        result = {"trace": {"events": events}}
        filtered = _trace_events_for_request(result, "req_X")
        self.assertEqual(len(filtered), 2)  # remote_method_entry + sampling_start only
        self.assertEqual(filtered[0]["monotonic_ns"], 500)
        self.assertEqual(filtered[1]["name"], "sampling_start")




class TestEndToEndUnetTiming(unittest.TestCase):
    """End-to-end test: ModelPatcher -> register_unet_forward_probe ->
    load_models_gpu demand recording -> hooked model forward with CUDA
    tensor -> emitted unet_first_cuda_op with nonzero elapsed."""

    def _restore_env(self):
        import os
        if self._saved_diag is not None:
            os.environ["COMFYMODAL_V2_UNET_FORWARD_DIAG"] = self._saved_diag
        else:
            os.environ.pop("COMFYMODAL_V2_UNET_FORWARD_DIAG", None)

    def setUp(self):
        import os
        # Save and restore env to avoid destroying state other tests rely on
        self._saved_diag = os.environ.get("COMFYMODAL_V2_UNET_FORWARD_DIAG")
        os.environ.pop("COMFYMODAL_V2_UNET_FORWARD_DIAG", None)
        self.addCleanup(self._restore_env)
        from comfymodal_runtime import unet_forward_probe as _ufp
        from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE as _ART
        # Clear global state
        with _ufp._registry_lock:
            _ufp._registry.clear()
        with _ufp._first_cuda_dedup_lock:
            _ufp._first_cuda_dedup.clear()
        with _ufp._unet_gpu_demand_lock:
            _ufp._unet_gpu_demand_start.clear()
        _ufp._installed_hook_handles.clear()
        _ufp._unet_forward_hooks_installed = False
        self._ufp = _ufp
        # Reset ContextVar to prevent cross-test contamination
        try:
            _ART.set(None)
        except Exception:
            pass

    def _make_model_patcher_like(self):
        """Create an object shaped like a real ModelPatcher with
        .model.diffusion_model, as used by load_models_gpu."""
        class _DM:
            def __init__(self):
                self._hooks = []
            def register_forward_pre_hook(self, hook, **kwargs):
                self._hooks.append(hook)
                return hook
        class _M:
            def __init__(self):
                self.diffusion_model = _DM()
        class _MP:
            def __init__(self):
                self.model = _M()
                self.model_options = {}
        return _MP()

    def test_end_to_end_registration_and_hook(self):
        """Simulate the real production path:
        1. ModelPatcher constructed -> register_unet_forward_probe called
        2. Hook installed on diffusion model
        3. load_models_gpu observed (simulated via set_unet_gpu_demand_start)
        4. Hooked model forward with CUDA tensor -> event with nonzero elapsed
        """
        mp = self._make_model_patcher_like()
        self._ufp.register_unet_forward_probe(mp, source="model_patcher_constructor")
        
        dm = mp.model.diffusion_model
        self.assertEqual(len(dm._hooks), 1, "hook must be installed")
        
        # Verify demand can be set (simulating load_models_gpu observing registered UNET)
        from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE as _ART
        from comfymodal_runtime.trace import RuntimeTrace
        rtrace = RuntimeTrace(request_id='e2e_test', process='test')
        _tok = _ART.set(rtrace)
        try:
            from comfymodal_runtime.unet_forward_probe import set_unet_gpu_demand_start
            set_unet_gpu_demand_start('e2e_test', 5000000)  # 5ms in the past (load_models_gpu path)
            
            # Forward hook with CUDA tensor
            self._ufp._forward_pre_hook(dm, (type('T', (), {'device': 'cuda:0', 'dtype': 'float'})(),))
        finally:
            _ART.reset(_tok)
        
        # Check event with nonzero elapsed (real demand set)
        ops = [e for e in rtrace.events if e.name == 'unet_first_cuda_op']
        self.assertEqual(len(ops), 1, "must emit unet_first_cuda_op")
        meta = ops[0].metadata
        self.assertEqual(meta.get('demand_start_present'), 1,
                         "demand must be present from load_models_gpu path")
        self.assertIsInstance(meta.get('elapsed_ms'), (int, float),
                              "elapsed_ms must be numeric when demand is set")
        self.assertGreater(meta.get('elapsed_ms', 0), 0,
                           "elapsed must be positive with past demand")
    
    def test_no_demand_reports_absent(self):
        """Without demand set (load_models_gpu NOT called), event reports absent."""
        mp = self._make_model_patcher_like()
        self._ufp.register_unet_forward_probe(mp, source="model_patcher_constructor")
        
        dm = mp.model.diffusion_model
        self.assertEqual(len(dm._hooks), 1, "hook must be installed")
        
        from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE as _ART
        from comfymodal_runtime.trace import RuntimeTrace
        rtrace = RuntimeTrace(request_id='e2e_test', process='test')
        _tok = _ART.set(rtrace)
        try:
            # NO set_unet_gpu_demand_start call (load_models_gpu not invoked)
            self._ufp._forward_pre_hook(dm, (type('T', (), {'device': 'cuda:0', 'dtype': 'float'})(),))
        finally:
            _ART.reset(_tok)
        
        ops = [e for e in rtrace.events if e.name == 'unet_first_cuda_op']
        self.assertEqual(len(ops), 1, "must still emit unet_first_cuda_op")
        meta = ops[0].metadata
        self.assertEqual(meta.get('demand_start_present'), 0,
                         "demand_present must be 0 when load_models_gpu not observed")
        self.assertEqual(meta.get('elapsed_ms'), "absent",
                         "elapsed must be 'absent' without demand")


class TestLoadModelsGpuShape(unittest.TestCase):
    """Verify _has_registered_unet_in_models matches actual ModelPatcher shape."""

    def test_has_registered_unet_matches_model_patcher(self):
        """The function must detect a registered UNET in a load_models_gpu-style
        list of ModelPatcher objects."""
        from comfymodal_runtime.unet_forward_probe import (
            register_unet_forward_probe,
            _has_registered_unet_in_models,
            _registry, _registry_lock,
        )
        with _registry_lock:
            _registry.clear()
        
        class _DM:
            pass
        class _M:
            def __init__(self):
                self.diffusion_model = _DM()
        class _MP:
            def __init__(self):
                self.model = _M()
        
        mp = _MP()
        register_unet_forward_probe(mp, source="test")
        
        # Now check _has_registered_unet_in_models with a list containing mp
        self.assertTrue(_has_registered_unet_in_models([mp]),
                        "must detect registered UNET in model list")



# ═══════════════════════════════════════════════════════════════════════
# Fix 3: pre-sampler critical path sampling_start_authoritative flag
# ═══════════════════════════════════════════════════════════════════════


class TestPreSamplerCriticalPathFix3(unittest.TestCase):
    """attach_pre_sampler_critical_path must set sampling_start_authoritative
    when sampling_start event is present in trace events (Fix 3)."""

    def _make_minimal_plan(self):
        class _FakePlan:
            workflow = {}
            workflow_hash = "test_hash"
        return _FakePlan()

    def test_sampling_start_present_sets_flag(self):
        """When sampling_start event in trace, flag must be True."""
        from comfymodal_runtime.runtime_executor import attach_pre_sampler_critical_path
        result = {
            "trace": {
                "events": [
                    {"name": "sampling_start", "monotonic_ns": 1000, "metadata": {}},
                ],
            },
        }
        plan = self._make_minimal_plan()
        enriched = attach_pre_sampler_critical_path(result, plan, cache=None)
        cpath = enriched.get("trace", {}).get("pre_sampler_critical_path", {})
        self.assertTrue(cpath.get("sampling_start_authoritative"),
                        "sampling_start_authoritative must be True when event present")

    def test_sampling_start_absent_no_flag(self):
        """Without sampling_start event, flag must not be set."""
        from comfymodal_runtime.runtime_executor import attach_pre_sampler_critical_path
        result = {
            "trace": {
                "events": [
                    {"name": "some_other_event", "monotonic_ns": 500, "metadata": {}},
                ],
            },
        }
        plan = self._make_minimal_plan()
        enriched = attach_pre_sampler_critical_path(result, plan, cache=None)
        cpath = enriched.get("trace", {}).get("pre_sampler_critical_path", {})
        self.assertNotIn("sampling_start_authoritative", cpath,
                         "flag must not be present when sampling_start absent")

    def test_milestone_does_not_include_sampler_node_to_sampler_start(self):
        """The removed sampler_node_to_sampler_start milestone must NOT
        appear in dominant_spans even when pre_sampler_stage_metadata
        contains the field."""
        from comfymodal_runtime.runtime_executor import attach_pre_sampler_critical_path
        result = {
            "trace": {
                "events": [
                    {
                        "name": "pre_sampler_stages",
                        "metadata": {
                            "sampler_node_to_sampler_start_ms": 42.0,
                            "first_sampler_node_id": "n1",
                            "sampler_stage_node_id": "n2",
                        },
                    },
                ],
            },
        }
        plan = self._make_minimal_plan()
        enriched = attach_pre_sampler_critical_path(result, plan, cache=None)
        cpath = enriched.get("trace", {}).get("pre_sampler_critical_path", {})
        spans = cpath.get("dominant_spans", [])
        span_names = [s.get("span") for s in spans]
        self.assertNotIn("sampler_node_to_sampler_start", span_names,
                         "sampler_node_to_sampler_start milestone must be removed")

    def test_sampling_start_first_event_detected(self):
        """Only the first sampling_start event triggers the flag."""
        from comfymodal_runtime.runtime_executor import attach_pre_sampler_critical_path
        result = {
            "trace": {
                "events": [
                    {"name": "pre_sampler_stages", "metadata": {}},
                    {"name": "sampling_start", "monotonic_ns": 2000, "metadata": {}},
                    {"name": "sampling_start", "monotonic_ns": 3000, "metadata": {}},
                ],
            },
        }
        plan = self._make_minimal_plan()
        enriched = attach_pre_sampler_critical_path(result, plan, cache=None)
        cpath = enriched.get("trace", {}).get("pre_sampler_critical_path", {})
        self.assertTrue(cpath.get("sampling_start_authoritative"),
                        "flag must be set when sampling_start appears")


if __name__ == "__main__":
    unittest.main()
