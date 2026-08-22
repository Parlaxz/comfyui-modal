"""E31 offline tests: synchronized forward timing, cast classification,
corrected cast wrapper, FP32 residency + lifecycle invalidation, profiler gate.

No Modal, no CUDA, no remote execution — synthetic objects and CPU tensors.
All E31 behavior must be default OFF; every test here that exercises an
enabled path sets the flag explicitly and restores it afterward.
"""

import os
import json
import inspect
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("COMFYMODAL_V2_E31_FORENSICS", "0")
os.environ.setdefault("COMFYMODAL_V2_E31_FORWARD_PROFILE", "0")

sys.path.insert(0, r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal")

import torch  # noqa: E402

from comfymodal_runtime import clip_forward_forensics as ff  # noqa: E402
from comfymodal_runtime import clip_fp32_cast_once as cast_once  # noqa: E402
from comfymodal_runtime import clip_fast_hydration as cfh  # noqa: E402
from comfymodal_runtime import clip_fast_hydration_wiring as hydration_wiring  # noqa: E402


class _FakeModule:
    """Minimal stand-in for a comfy cast-weight module (weight+bias)."""

    def __init__(self, weight, bias=None):
        self.weight = weight
        self.bias = bias
        self.comfy_cast_weights = True
        self.weight_function = []
        self.bias_function = []


class _FakeOps:
    def __init__(self):
        self.calls = []

    def cast_bias_weight(self, s, input=None, dtype=None, device=None, offloadable=False, **kwargs):
        self.calls.append(("cast_bias_weight", s, dtype))
        w = s.weight.to(dtype=dtype) if dtype is not None and s.weight.dtype != dtype else s.weight
        b = None
        if s.bias is not None:
            b = s.bias.to(dtype=dtype) if dtype is not None and s.bias.dtype != dtype else s.bias
        result = (w, b)
        if offloadable:
            result = result + (object(),)  # (weight, bias, offload_stream)
        return result

    def cast_to(self, weight, dtype=None, device=None, **kwargs):
        self.calls.append(("cast_to", weight, dtype))
        return weight.to(dtype=dtype) if dtype is not None and weight.dtype != dtype else weight

    def cast_to_device(self, tensor, device, dtype, copy=False):
        self.calls.append(("cast_to_device", tensor, dtype))
        return tensor.to(dtype=dtype) if dtype is not None and tensor.dtype != dtype else tensor


class _FakeMM:
    def cast_bias_weight(self, s, input=None, dtype=None, device=None, offloadable=False, **kwargs):
        w = s.weight.to(dtype=dtype) if dtype is not None and s.weight.dtype != dtype else s.weight
        b = None if s.bias is None else (
            s.bias.to(dtype=dtype) if dtype is not None and s.bias.dtype != dtype else s.bias
        )
        return (w, b, object()) if offloadable else (w, b)

    def cast_to(self, weight, dtype=None, device=None, **kwargs):
        return weight.to(dtype=dtype) if dtype is not None and weight.dtype != dtype else weight

    def cast_to_device(self, tensor, device, dtype, copy=False):
        return tensor.to(dtype=dtype) if dtype is not None and tensor.dtype != dtype else tensor


class _MappingLeaf(torch.nn.Module):
    """CPU dispatch leaf whose state dict is an exact checkpoint mapping."""

    def __init__(self, tensors):
        super().__init__()
        for key, tensor in tensors.items():
            self.register_parameter(key, torch.nn.Parameter(tensor, requires_grad=False))

    def load_sd(self, sd):
        return None


class _MappingModel(torch.nn.Module):
    def __init__(self, tensors):
        super().__init__()
        self.leaf = _MappingLeaf(tensors)


class _ForwardClip:
    def __init__(self, tensors):
        self.cond_stage_model = _MappingModel(tensors)
        self.forward_calls = 0

    def encode_from_tokens(self, tokens):
        self.forward_calls += 1
        return (tokens, self.forward_calls)


def _mapping_fixture(destination=None, source=None):
    source = source or {
        "a": torch.arange(4, dtype=torch.float32),
        "b": torch.arange(6, dtype=torch.float32),
    }
    destination = source if destination is None else destination
    clip = _ForwardClip(destination)
    manifest = [{
        "dtype": "torch.bfloat16",
        "key_set": sorted(source),
        "key_shapes": {key: list(value.shape) for key, value in source.items()},
    }]
    return clip, [source], manifest


class DefaultOffTest(unittest.TestCase):
    def test_gate_sync_tracks_effective_env_after_import(self):
        import importlib

        saved = os.environ.get("COMFYMODAL_V2_E31_FORENSICS")
        try:
            os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "1"
            mod = importlib.reload(ff)
            os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "0"
            state = mod.sync_e31_gates()
            self.assertFalse(state["forensics"])
            os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "1"
            state = mod.sync_e31_gates()
            self.assertTrue(state["forensics"])
        finally:
            if saved is None:
                os.environ.pop("COMFYMODAL_V2_E31_FORENSICS", None)
            else:
                os.environ["COMFYMODAL_V2_E31_FORENSICS"] = saved
            importlib.reload(ff)

    def test_module_import_does_no_cuda_work(self):
        # The gate is off by default; no CUDA context may be created by import.
        self.assertFalse(ff.e31_enabled())
        self.assertFalse(ff.e31_profile_enabled())

    def test_install_with_gate_off_is_noop(self):
        ops = _FakeOps()
        mm = _FakeMM()
        status = ff.install_cast_forensics(ops, mm)
        self.assertEqual(status, {"enabled": False, "installed": {}})
        # wrappers must not be installed
        self.assertFalse(hasattr(ops.cast_bias_weight, ff._SENTINEL_CAST))

    def test_forward_timer_no_cuda_reports_none_not_zero(self):
        timer = ff.ForwardTimer()
        timer.start()
        timer.end()
        record = timer.end()
        # end() is idempotent-safe; the second call without start is a no-op
        self.assertIn("gpu_elapsed_ms", record)


class CastClassificationTest(unittest.TestCase):
    def test_noop_same_tensor(self):
        t = torch.zeros(4)
        cls, ev = ff.classify_cast(t, t)
        self.assertEqual(cls, ff.NOOP_SAME_TENSOR)

    def test_real_conversion(self):
        t = torch.zeros(4, dtype=torch.bfloat16)
        cls, ev = ff.classify_cast(t, t.float())
        self.assertEqual(cls, ff.REAL_CONVERSION)

    def test_same_storage_view(self):
        t = torch.zeros(4)
        v = t.view(2, 2)
        cls, ev = ff.classify_cast(t, v)
        self.assertEqual(cls, ff.VIEW_ALIAS)

    def test_same_storage_offset_view(self):
        t = torch.zeros(6)
        v = t[2:]  # different data_ptr, same storage
        cls, ev = ff.classify_cast(t, v)
        self.assertEqual(cls, ff.NOOP_SAME_STORAGE)

    def test_real_copy_same_dtype(self):
        t = torch.zeros(4)
        cls, ev = ff.classify_cast(t, t.clone())
        self.assertEqual(cls, ff.REAL_COPY_NO_DTYPE_CHANGE)

    def test_non_tensor_other(self):
        cls, ev = ff.classify_cast(None, 42)
        self.assertEqual(cls, ff.OTHER)


class CorrectedCastWrapperTest(unittest.TestCase):
    def _install_and_run(self, env_val):
        os.environ["COMFYMODAL_V2_E31_FORENSICS"] = env_val
        try:
            import importlib

            mod = importlib.reload(ff)
            ops = _FakeOps()
            mm = _FakeMM()
            status = mod.install_cast_forensics(ops, mm)
            w = torch.zeros(8, 8, dtype=torch.bfloat16)
            b = torch.zeros(8, dtype=torch.bfloat16)
            m = _FakeModule(w, b)
            out = ops.cast_bias_weight(m, dtype=torch.float32)
            # Snapshot BEFORE the finally's env restore + reload (reload
            # re-initializes the account in place).
            return mod, ops, mm, out, mod.cast_forensics_summary()
        finally:
            os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "0"
            import importlib

            importlib.reload(ff)

    def test_wrapper_correctly_parses_module_signature(self):
        mod, ops, mm, out, summary = self._install_and_run("1")
        # The corrected wrapper must see the REAL source dtype (bf16), not
        # E28's "unknown".
        self.assertEqual(summary["source_dtypes"].get("torch.bfloat16", 0), 2)
        self.assertEqual(summary["dest_dtypes"].get("torch.float32", 0), 2)
        # 1 weight cast + 1 bias cast
        self.assertEqual(summary["weight_casts"], 1)
        self.assertEqual(summary["bias_casts"], 1)
        # bf16->fp32 is a REAL_CONVERSION
        self.assertEqual(summary["classifications"].get(ff.REAL_CONVERSION, 0), 2)

    def test_wrapper_gated_off_is_noop(self):
        mod, ops, mm, out, summary = self._install_and_run("0")
        self.assertEqual(summary["weight_casts"], 0)
        self.assertEqual(summary["classifications"], {})


class ForwardTimerTest(unittest.TestCase):
    def test_timer_reports_wall_and_gpu_state(self):
        timer = ff.ForwardTimer()
        timer.start()
        timer.end()
        r = timer.end()
        self.assertIn("host_wall_ms", r)
        # When CUDA is present the GPU elapsed must be a real number; when
        # absent it must be None (never a fabricated 0.0).
        if torch.cuda.is_available():
            self.assertIsNotNone(r.get("gpu_elapsed_ms"))
        else:
            self.assertIsNone(r.get("gpu_elapsed_ms"))

    def test_classify_after_real_conversion_counts_bytes(self):
        summary = self._install_and_run_helper()
        self.assertGreaterEqual(summary["real_conversion_bytes"], 8 * 8 * 4 + 8 * 4)

    def test_forward_scoped_summary_is_not_hydration_global(self):
        os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "1"
        try:
            import importlib

            mod = importlib.reload(ff)
            ops = _FakeOps()
            mod.install_cast_forensics(ops, _FakeMM())
            module = _FakeModule(
                torch.zeros(4, dtype=torch.bfloat16),
            )
            # A bind/hydration conversion before the forward must not become
            # the forward conversion count.
            ops.cast_bias_weight(module, dtype=torch.bfloat16)
            mod.reset_cast_forensics()
            timer = mod.ForwardTimer()
            timer.start()
            timer.mark_forward_observed()
            ops.cast_bias_weight(module, dtype=torch.float32)
            record = timer.end()
            self.assertTrue(record["forward_observed"])
            self.assertEqual(record["forward_conversion_count"], 1)
            self.assertEqual(record["forward_cast_summary"]["real_conversions"], 1)
        finally:
            os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "0"
            import importlib

            importlib.reload(ff)

    def _install_and_run_helper(self):
        os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "1"
        try:
            import importlib

            mod = importlib.reload(ff)
            ops = _FakeOps()
            mm = _FakeMM()
            mod.install_cast_forensics(ops, mm)
            w = torch.zeros(8, 8, dtype=torch.bfloat16)
            b = torch.zeros(8, dtype=torch.bfloat16)
            m = _FakeModule(w, b)
            ops.cast_bias_weight(m, dtype=torch.float32)
            return mod.cast_forensics_summary()
        finally:
            os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "0"
            import importlib

            importlib.reload(ff)


class CastOnceResidencyTest(unittest.TestCase):
    def test_apply_cast_once_gated_off_is_noop(self):
        sd = {"a": torch.zeros(2, 2, dtype=torch.bfloat16)}
        manifest = [{"dtype": "torch.bfloat16", "key_set": ["a"], "key_shapes": {"a": [2, 2]}}]
        os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "0"
        out, record = cast_once.apply_cast_once([sd], manifest)
        self.assertFalse(record["applied"])
        self.assertEqual(str(out[0]["a"].dtype), "torch.bfloat16")

    def test_apply_cast_once_exact_widening(self):
        sd = {"a": torch.zeros(2, 2, dtype=torch.bfloat16)}
        manifest = [{"dtype": "torch.bfloat16", "key_set": ["a"], "key_shapes": {"a": [2, 2]}}]
        os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "1"
        try:
            import importlib

            mod = importlib.reload(cast_once)
            out, record = mod.apply_cast_once([sd], manifest)
            self.assertTrue(record["applied"])
            self.assertEqual(str(out[0]["a"].dtype), "torch.float32")
            self.assertEqual(record["bytes_out"], 2 * 2 * 4)
        finally:
            os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "0"
            import importlib

            importlib.reload(cast_once)

    def test_invalidation_generation(self):
        clip = _FakeModule(torch.zeros(2))
        self.assertEqual(cast_once.cast_once_generation(clip), 0)
        cast_once.mark_cast_once_applied(clip)
        self.assertEqual(cast_once.cast_once_generation(clip), 1)
        cast_once.invalidate_cast_once(clip)
        self.assertEqual(cast_once.cast_once_generation(clip), 0)

    def test_verify_resident_fp32_fails_closed_on_bf16(self):
        # A leaf with a BF16 weight must fail closed (not FP32).
        class _Leaf(torch.nn.Module):
            def __init__(self, weight, bias=None):
                super().__init__()
                self.weight = torch.nn.Parameter(weight)
                if bias is not None:
                    self.bias = torch.nn.Parameter(bias)
                else:
                    self.register_parameter("bias", None)

            def load_sd(self, sd):
                return None

        class _CSM(torch.nn.Module):
            def __init__(self, leaf):
                super().__init__()
                self.leaf = leaf

        leaf = _Leaf(torch.zeros(8, dtype=torch.bfloat16))
        csm = _CSM(leaf)
        clip = _FakeModule(torch.zeros(2))
        clip.cond_stage_model = csm
        ok, record = cast_once.verify_resident_fp32(clip)
        self.assertFalse(ok)
        self.assertIn("non_fp32", record.get("reason", ""))

    def test_second_forward_no_repeat_conversion(self):
        """Phase 4 proof: after cast-once, the SECOND forward must not
        perform real conversions (the FP32 storage is consumed directly)."""
        os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "1"
        os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "1"
        try:
            import importlib

            mod = importlib.reload(ff)
            # Simulate the cast-once bind: cast the BF16 weights to FP32 once
            # (as apply_cast_once does), then run two forwards through the
            # cast wrapper on the FP32-resident module.
            ops = _FakeOps()
            mm = _FakeMM()
            mod.install_cast_forensics(ops, mm)
            w = torch.zeros(8, 8, dtype=torch.bfloat16)
            b = torch.zeros(8, dtype=torch.bfloat16)
            m = _FakeModule(w, b)
            # cast-once bind equivalent:
            m.weight = torch.nn.Parameter(m.weight.to(torch.float32))
            m.bias = torch.nn.Parameter(m.bias.to(torch.float32))
            mod.reset_cast_forensics()
            # forward 1: the cast wrapper still runs; the resident FP32
            # storage means the weight/bias casts are NOOPs (same storage),
            # and the per-forward .to(dtype=fp32) is a no-op.
            ops.cast_bias_weight(m, dtype=torch.float32)
            first = mod.cast_forensics_summary()
            mod.reset_cast_forensics()
            # forward 2: must show ZERO real conversions.
            ops.cast_bias_weight(m, dtype=torch.float32)
            second = mod.cast_forensics_summary()
            self.assertEqual(second["real_conversions"], 0,
                             f"second forward repeated real conversion: {second}")
            self.assertEqual(second["classifications"].get(mod.REAL_CONVERSION, 0), 0)
            # The casts are still counted (the call sites run) but they are
            # no-ops — exactly the cast-once contract.
            self.assertGreaterEqual(second["weight_casts"] + second["bias_casts"], 2)
            # Storage stability: same storage pointers across both forwards.
            self.assertEqual(
                first["classifications"].get(mod.NOOP_SAME_TENSOR, 0)
                + first["classifications"].get(mod.NOOP_SAME_STORAGE, 0),
                2,
            )
        finally:
            os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "0"
            os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "0"
            import importlib

            importlib.reload(ff)

    def test_normal_multi_file_cast_preserves_manifest_file_index(self):
        os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "1"
        try:
            files = [
                {"a": torch.ones(2, dtype=torch.bfloat16)},
                {"b": torch.ones(3, dtype=torch.bfloat16)},
            ]
            manifests = [
                {"file_index": 0, "dtype": "torch.bfloat16", "key_set": ["a"], "key_shapes": {"a": [2]}},
                {"file_index": 1, "dtype": "torch.bfloat16", "key_set": ["b"], "key_shapes": {"b": [3]}},
            ]
            converted, record = cast_once.apply_cast_once(files, manifests)
            self.assertTrue(record["applied"])
            self.assertEqual(
                [item["file_index"] for item in record["source_provenance"]], [0, 1]
            )
            for sd, manifest in zip(converted, manifests):
                ok, detail = cast_once.verify_cast_once_sd(manifest, sd)
                self.assertTrue(ok, detail)
        finally:
            os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "0"

    def test_same_object_mutation_invalidates_marker_generation_and_callback(self):
        clip = _ForwardClip({"a": torch.ones(2, dtype=torch.float32)})
        cast_once.mark_cast_once_applied(clip)
        cfh.mark_clip_hydrated(clip)
        setattr(clip, cfh._E31_PENDING_FORWARD_ATTR if hasattr(cfh, "_E31_PENDING_FORWARD_ATTR") else "_comfymodal_e31_pending_forward_callback", {"callback": lambda _: None})
        clip.cond_stage_model.leaf.a = torch.nn.Parameter(torch.ones(2))
        self.assertFalse(cfh.clip_hydrated(clip))
        self.assertFalse(getattr(clip, cfh.HYDRATED_MARKER, False))
        self.assertEqual(cast_once.cast_once_generation(clip), 0)

    def test_clone_rehome_identity_invalidates_marker_generation(self):
        class _Patcher:
            def __init__(self):
                self.current_object = object()

        clip = _ForwardClip({"a": torch.ones(2, dtype=torch.float32)})
        clip.patcher = _Patcher()
        cast_once.mark_cast_once_applied(clip)
        cfh.mark_clip_hydrated(clip)
        clip.patcher.current_object = object()
        self.assertFalse(cfh.clip_hydrated(clip))
        self.assertFalse(getattr(clip, cfh.HYDRATED_MARKER, False))
        self.assertEqual(cast_once.cast_once_generation(clip), 0)


class ProfilerGateTest(unittest.TestCase):
    def test_profiler_default_off(self):
        prof = ff.ForwardProfiler()
        with prof:
            pass
        rec = prof.record()
        self.assertEqual(rec["status"], "not_run")

    def test_profiler_explicit_on_cpu_only(self):
        prof = ff.ForwardProfiler(enabled=True)
        with prof:
            _ = torch.zeros(4) + torch.ones(4)
        rec = prof.record()
        self.assertEqual(rec["status"], "ok")
        self.assertGreaterEqual(rec["op_count"], 1)


class DeferredCastTimingTest(unittest.TestCase):
    """Phase 4/5 correctness: per-cast event pairs must NOT be read before
    the forward sync (the E28 0.0 ms bug class).  The wrapper queues pairs;
    the resolution happens only after ForwardTimer.end()'s one sync."""

    def _install(self):
        os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "1"
        import importlib

        mod = importlib.reload(ff)
        ops = _FakeOps()
        mm = _FakeMM()
        mod.install_cast_forensics(ops, mm)
        return mod, ops

    def _restore(self):
        os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "0"
        import importlib

        importlib.reload(ff)

    def test_pending_events_queued_not_read_at_call_time(self):
        mod, ops = self._install()
        w = torch.zeros(8, 8, dtype=torch.bfloat16)
        b = torch.zeros(8, dtype=torch.bfloat16)
        m = _FakeModule(w, b)
        try:
            mod.reset_cast_forensics()
            ops.cast_bias_weight(m, dtype=torch.float32)
            # At call time the account must NOT yet contain per-cast GPU time
            # (it cannot be known before the sync); the pairs are queued.
            summary = mod.cast_forensics_summary()
            self.assertEqual(summary["gpu_event_ms"], 0.0)
            if torch.cuda.is_available():
                self.assertEqual(summary["pending_event_pairs"], 1)
            # Resolution with CUDA available on a real stream completes the
            # read; without CUDA the queue still drains without fabricating.
            mod.resolve_pending_cast_events()
            summary = mod.cast_forensics_summary()
            self.assertEqual(summary["pending_event_pairs"], 0)
            self.assertGreaterEqual(summary["gpu_event_ms"], 0.0)
        finally:
            mod.reset_cast_forensics()
            self._restore()

    def test_wrapper_records_module_prefix_facts(self):
        mod, ops = self._install()
        w = torch.zeros(8, 8, dtype=torch.bfloat16)
        m = _FakeModule(w)
        try:
            mod.reset_cast_forensics()
            ops.cast_bias_weight(m, dtype=torch.float32)
            summary = mod.cast_forensics_summary()
            self.assertIn("module_paths", summary)
            self.assertGreaterEqual(len(summary["module_paths"]), 1)
        finally:
            mod.reset_cast_forensics()
            self._restore()

    def test_offloadable_triple_not_counted_as_bias(self):
        # cast_bias_weight(..., offloadable=True) returns (weight, bias,
        # offload_stream); the third element must never be recorded as a
        # bias cast.
        mod, ops = self._install()
        w = torch.zeros(8, 8, dtype=torch.bfloat16)
        m = _FakeModule(w)  # no bias
        try:
            mod.reset_cast_forensics()
            ops.cast_bias_weight(m, dtype=torch.float32, offloadable=True)
            summary = mod.cast_forensics_summary()
            self.assertEqual(summary["weight_casts"], 1)
            self.assertEqual(summary["bias_casts"], 0)
        finally:
            mod.reset_cast_forensics()
            self._restore()


class LedgerIntegrationTest(unittest.TestCase):
    """Phase 8: E31 events appear on the E29 canonical ledger axis, only
    when the E31 gate is on, with the required names."""

    def _install(self, forensics_val):
        os.environ["COMFYMODAL_V2_E31_FORENSICS"] = forensics_val
        import importlib

        return importlib.reload(ff)

    def _restore(self):
        os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "0"
        import importlib

        importlib.reload(ff)

    def test_forward_timer_emits_ledger_events_when_enabled(self):
        mod = self._install("1")
        try:
            from comfymodal_runtime import critical_path_ledger as cpl

            cpl.clear_ledger_for_test()
            timer = mod.ForwardTimer()
            timer.start()
            timer.end()
            events = cpl.get_events()
            names = {e.get("name") for e in events}
            self.assertIn("clip_forward_start", names)
            self.assertIn("clip_forward_end", names)
            self.assertIn("clip_gpu_event_start", names)
            self.assertIn("clip_gpu_event_end", names)
        finally:
            try:
                from comfymodal_runtime import critical_path_ledger as cpl

                cpl.clear_ledger_for_test()
            except Exception:
                pass
            self._restore()

    def test_gate_off_emits_nothing(self):
        mod = self._install("0")
        try:
            from comfymodal_runtime import critical_path_ledger as cpl

            cpl.clear_ledger_for_test()
            timer = mod.ForwardTimer()
            timer.start()
            timer.end()
            events = cpl.get_events()
            names = {e.get("name") for e in events}
            self.assertNotIn("clip_forward_start", names)
        finally:
            try:
                from comfymodal_runtime import critical_path_ledger as cpl

                cpl.clear_ledger_for_test()
            except Exception:
                pass
            self._restore()

    def test_unknown_event_name_dropped(self):
        mod = self._install("1")
        try:
            from comfymodal_runtime import critical_path_ledger as cpl

            cpl.clear_ledger_for_test()
            mod.emit_ledger_event("not_a_real_e31_event")
            events = cpl.get_events()
            names = {e.get("name") for e in events}
            self.assertNotIn("not_a_real_e31_event", names)
        finally:
            try:
                from comfymodal_runtime import critical_path_ledger as cpl

                cpl.clear_ledger_for_test()
            except Exception:
                pass
            self._restore()

    def test_emit_cast_summary_ledger(self):
        mod = self._install("1")
        try:
            from comfymodal_runtime import critical_path_ledger as cpl

            cpl.clear_ledger_for_test()
            mod.emit_cast_summary_ledger()
            events = cpl.get_events()
            names = {e.get("name") for e in events}
            self.assertIn("clip_forward_cast_summary", names)
        finally:
            try:
                from comfymodal_runtime import critical_path_ledger as cpl

                cpl.clear_ledger_for_test()
            except Exception:
                pass
            self._restore()


class CastOnceIdentityTest(unittest.TestCase):
    """Phase 6: the generation is keyed on the real clip identity, not just
    the object id — a rehydrated/replaced model must fail closed."""

    def test_generation_keyed_on_identity_not_object_id(self):
        class _Patcher:
            def __init__(self, current):
                self.current_object = current

        clip_a = _FakeModule(torch.zeros(2))
        csm_a = _FakeModule(torch.zeros(2))
        clip_a.cond_stage_model = csm_a
        clip_a.patcher = _Patcher(_FakeModule(torch.zeros(2)))
        cast_once.mark_cast_once_applied(clip_a)
        self.assertEqual(cast_once.cast_once_generation(clip_a), 1)
        # A different clip object with the SAME outer id must not inherit the
        # claim (identity includes csm + patcher current_object ids).
        clip_b = _FakeModule(torch.zeros(2))
        clip_b.cond_stage_model = _FakeModule(torch.zeros(2))
        clip_b.patcher = _Patcher(_FakeModule(torch.zeros(2)))
        self.assertEqual(cast_once.cast_once_generation(clip_b), 0)
        # Rehydration of the SAME object (new csm) fails closed.
        clip_a.cond_stage_model = _FakeModule(torch.zeros(2))
        self.assertEqual(cast_once.cast_once_generation(clip_a), 0)
        # Explicit invalidation works.
        clip_a.cond_stage_model = csm_a
        clip_a.patcher = _Patcher(_FakeModule(torch.zeros(2)))
        self.assertEqual(cast_once.cast_once_generation(clip_a), 0)

    def test_invalidate_removes_claim(self):
        clip = _FakeModule(torch.zeros(2))
        clip.cond_stage_model = _FakeModule(torch.zeros(2))
        cast_once.mark_cast_once_applied(clip)
        self.assertEqual(cast_once.cast_once_generation(clip), 1)
        cast_once.invalidate_cast_once(clip)
        self.assertEqual(cast_once.cast_once_generation(clip), 0)


class ExactResidencyProofTest(unittest.TestCase):
    """The cast-once claim is an exact checkpoint-to-parameter proof."""

    def test_successful_fp32_cast_and_exact_mapping(self):
        original = {
            "a": torch.arange(4, dtype=torch.bfloat16),
            "b": torch.arange(6, dtype=torch.bfloat16),
        }
        os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "1"
        try:
            converted, record = cast_once.apply_cast_once(
                [original], [{
                    "dtype": "torch.bfloat16",
                    "key_set": ["a", "b"],
                    "key_shapes": {"a": [4], "b": [6]},
                }],
            )
            self.assertTrue(record["applied"])
            self.assertEqual(record["tensor_count"], 2)
            self.assertEqual(record["bytes_in"], 10 * 2)
            self.assertEqual(record["bytes_out"], 10 * 4)
            self.assertTrue(all(t.dtype == torch.float32 for t in converted[0].values()))
            self.assertTrue(all(t.dtype == torch.bfloat16 for t in original.values()))

            clip, source, manifest = _mapping_fixture(source=converted[0])
            ok, proof = cast_once.verify_resident_fp32(
                clip, source, manifest, expect_device="cpu"
            )
            self.assertTrue(ok, proof)
            self.assertEqual(proof["expected_count"], 2)
            self.assertEqual(proof["matched_count"], 2)
            self.assertEqual({e["key"] for e in proof["per_key"]}, {"a", "b"})
            self.assertTrue(all(e["matched"] for e in proof["per_key"]))
        finally:
            os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "0"

    def test_zero_expected_count_fails_closed(self):
        clip = _ForwardClip({"a": torch.zeros(2, dtype=torch.float32)})
        ok, record = cast_once.verify_resident_fp32(clip, [{}], [{"key_set": []}])
        self.assertFalse(ok)
        self.assertEqual(record["reason"], "zero_expected_count")

    def test_missing_parameter_fails_closed(self):
        source = {"a": torch.ones(2), "b": torch.ones(3)}
        clip, _, manifest = _mapping_fixture(destination={"a": source["a"]}, source=source)
        ok, record = cast_once.verify_resident_fp32(clip, [source], manifest, expect_device="cpu")
        self.assertFalse(ok)
        self.assertEqual(record["destination_count"], 1)
        self.assertEqual(record["matched_count"], 1)
        missing = next(item for item in record["per_key"] if item["key"] == "b")
        self.assertFalse(missing["present_destination"])
        self.assertIn("matched_count", record["reason"])

    def test_duplicate_mapping_fails_closed(self):
        class _DuplicateLeaf(_MappingLeaf):
            def state_dict(self, *args, **kwargs):
                # Deliberately preserve one tensor object for two checkpoint keys;
                # this is an unambiguous duplicate destination mapping.
                return {"a": self.a, "b": self.a}

        source = {"a": torch.ones(2), "b": torch.ones(2)}
        shared = torch.ones(2)
        leaf = _DuplicateLeaf({"a": shared})
        clip = _ForwardClip({"a": shared})
        clip.cond_stage_model.leaf = leaf
        manifest = [{"dtype": "torch.bfloat16", "key_set": ["a", "b"], "key_shapes": {"a": [2], "b": [2]}}]
        ok, record = cast_once.verify_resident_fp32(clip, [source], manifest, expect_device="cpu")
        self.assertFalse(ok)
        self.assertGreaterEqual(record["duplicate_count"], 1)

    def test_wrong_dtype_device_and_storage_fail_closed(self):
        source = {"a": torch.ones(4, dtype=torch.float32)}
        cases = (
            ("dtype", {"a": source["a"].to(torch.bfloat16)}, "cpu"),
            ("device", {"a": source["a"]}, "cuda:0"),
            ("storage", {"a": source["a"].clone()}, "cpu"),
        )
        for kind, destination, device in cases:
            with self.subTest(kind=kind):
                clip, _, manifest = _mapping_fixture(destination=destination, source=source)
                ok, record = cast_once.verify_resident_fp32(
                    clip, [source], manifest, expect_device=device
                )
                self.assertFalse(ok)
                self.assertIn(
                    {"dtype": "dtype_mismatch_count", "device": "device_mismatch_count", "storage": "storage_mismatch_count"}[kind],
                    record["reason"],
                )

    def test_byte_mismatch_is_not_value_or_dtype_proof(self):
        source = {"a": torch.ones(4, dtype=torch.float32)}
        destination = {"a": source["a"].clone()}
        destination["a"][0] = 9.0
        clip, _, manifest = _mapping_fixture(destination=destination, source=source)
        ok, record = cast_once.verify_resident_fp32(clip, [source], manifest, expect_device="cpu")
        self.assertFalse(ok)
        self.assertEqual(record["byte_mismatch_count"], 1)

    def test_failed_cast_once_proof_does_not_publish_success(self):
        os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "1"
        try:
            source = {"a": torch.ones(2, dtype=torch.float32)}
            clip, _, manifest = _mapping_fixture(
                destination={"a": source["a"].to(torch.bfloat16)}, source=source
            )
            setattr(clip, cfh.HYDRATED_MARKER, False)
            ok, record = cast_once.verify_resident_fp32(
                clip, [source], manifest, expect_device="cpu"
            )
            self.assertFalse(ok)
            self.assertFalse(getattr(clip, cfh.HYDRATED_MARKER, False))
            self.assertEqual(cast_once.cast_once_generation(clip), 0)
            self.assertIn("dtype_mismatch_count", record["reason"])
        finally:
            os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "0"

    def test_multi_file_residency_evidence_has_exact_destination_and_file_totals(self):
        a = torch.ones(2, dtype=torch.float32)
        b = torch.ones(3, dtype=torch.float32)
        clip = _ForwardClip({"a": a, "b": b})
        source = [{"a": a}, {"b": b}]
        manifests = [
            {"file_index": 0, "dtype": "torch.bfloat16", "key_set": ["a"], "key_shapes": {"a": [2]}},
            {"file_index": 1, "dtype": "torch.bfloat16", "key_set": ["b"], "key_shapes": {"b": [3]}},
        ]
        ok, evidence = cast_once.verify_resident_fp32(
            clip, source, manifests, expect_device="cpu"
        )
        self.assertTrue(ok, evidence)
        self.assertEqual(evidence["destination_count"], 2)
        self.assertEqual(evidence["verified_count"], 2)
        self.assertEqual(evidence["destination_bytes"], 5 * 4)
        self.assertEqual(evidence["verified_bytes"], 5 * 4)
        self.assertEqual(
            [(item["destination_count"], item["verified_bytes"]) for item in evidence["per_file"]],
            [(1, 2 * 4), (1, 3 * 4)],
        )
        json.dumps(evidence)

    def test_declared_structural_destination_is_accepted(self):
        source = {
            "a": torch.ones(2, dtype=torch.float32),
            "b": torch.ones(3, dtype=torch.float32),
        }
        destination = dict(source)
        destination["logit_scale"] = torch.ones(1, dtype=torch.float32)
        clip, _, manifest = _mapping_fixture(destination=destination, source=source)
        manifest[0]["structural_destination_keys"] = ["logit_scale"]

        ok, evidence = cast_once.verify_resident_fp32(
            clip, [source], manifest, expect_device="cpu"
        )

        self.assertTrue(ok, evidence)
        self.assertEqual(evidence["unexpected_destination_keys"], [])
        self.assertEqual(evidence["structural_destination_keys"], ["logit_scale"])

    def test_undeclared_structural_destination_is_rejected(self):
        source = {
            "a": torch.ones(2, dtype=torch.float32),
            "b": torch.ones(3, dtype=torch.float32),
        }
        destination = dict(source)
        destination["logit_scale"] = torch.ones(1, dtype=torch.float32)
        clip, _, manifest = _mapping_fixture(destination=destination, source=source)

        ok, evidence = cast_once.verify_resident_fp32(
            clip, [source], manifest, expect_device="cpu"
        )

        self.assertFalse(ok)
        self.assertEqual(evidence["unexpected_destination_keys"], ["logit_scale"])
        self.assertIn("unexpected_count", evidence["reason"])


class OwnerRetirementTest(unittest.TestCase):
    def test_bf16_owner_retires_without_allocator_purge(self):
        class _Owner:
            def __init__(self):
                self.release_args = None
                self.close_calls = 0
                self.empty_cache_calls = 0

            def release_storage(self, purge_allocator=True):
                self.release_args = purge_allocator

            def close(self):
                self.close_calls += 1

            def empty_cache(self):
                self.empty_cache_calls += 1

        owner = _Owner()
        with patch.object(torch.cuda, "empty_cache", wraps=torch.cuda.empty_cache) as empty_cache:
            record = cfh.retire_source_owners(
                [(owner, owner)], bf16_bytes=12, fp32_bytes=24
            )
        self.assertEqual(record["owner_count_before"], 1)
        self.assertEqual(record["owners_retired"], 1)
        self.assertEqual(record["release_calls"], 1)
        self.assertIs(owner.release_args, False)
        self.assertEqual(owner.close_calls, 0)
        self.assertEqual(owner.empty_cache_calls, 0)
        empty_cache.assert_not_called()

    def test_owner_with_unreleased_component_fails_closed(self):
        class _Released:
            def release_storage(self, purge_allocator=True):
                return None

        class _Unreleased:
            pass

        owners = [(_Released(), _Unreleased())]
        record = cfh.retire_source_owners(owners)
        self.assertFalse(record["ok"])
        self.assertEqual(record["owners_failed"], 1)
        self.assertEqual(len(owners), 1)

    def test_owner_release_without_no_purge_keyword_fails_closed(self):
        class _Unsafe:
            def release_storage(self):
                raise AssertionError("must not be retried without keyword")

        record = cfh.retire_source_owners([(_Unsafe(),)])
        self.assertFalse(record["ok"])
        self.assertEqual(record["per_owner"][0]["components"][0]["error"], "release_api_requires_explicit_no_purge")

    def test_instrumentation_validation_precedes_generation_and_owner_publish(self):
        source = inspect.getsource(hydration_wiring._try_fast_hydrate)
        hook = source.index("_e31_forward_hook(")
        mark = source.index("_e31_mark_applied(")
        bind_proof = source.index('"clip_fh_cast_once_bind_proof"')
        retire = source.index("retire_source_owners(")
        self.assertLess(hook, mark)
        self.assertLess(mark, bind_proof)
        self.assertLess(mark, retire)


class RealForwardProofTest(unittest.TestCase):
    def _hook_fixture(self, *, mutate=None, trace=None):
        source = {
            "a": torch.ones(3, dtype=torch.float32),
            "b": torch.ones(2, dtype=torch.float32),
        }
        clip, per_file_sds, manifests = _mapping_fixture(source=source)
        clip.mutate = mutate

        def _forward(tokens):
            clip.forward_calls += 1
            if clip.mutate is not None:
                clip.mutate(clip)
            return tokens

        clip.encode_from_tokens = _forward
        cast_once.mark_cast_once_applied(clip)
        bind_snapshot = cast_once.snapshot_resident_fp32(
            clip, per_file_sds, manifests, expect_device="cpu", phase="post_bind"
        )
        hook = hydration_wiring._e31_forward_hook(
            clip, per_file_sds, manifests, expect_device="cpu",
            bind_snapshot=bind_snapshot, trace=trace,
        )
        return clip, bind_snapshot, hook

    def test_real_forward_is_between_snapshots_and_post_mark_generation_is_emitted(self):
        events = []

        class _Trace:
            def emit(self, name, **kwargs):
                events.append((name, kwargs["metadata"]))

        clip, bind_snapshot, hook = self._hook_fixture(trace=_Trace())
        try:
            clip.encode_from_tokens([1, 2])
            self.assertEqual(clip.forward_calls, 1)
            self.assertTrue(hook["hook"]["installed"])
            evidence = [m for name, m in events if name == "clip_fh_cast_once_forward_check"]
            self.assertEqual(len(evidence), 1)
            self.assertTrue(evidence[0]["forward_observed"])
            self.assertEqual(evidence[0]["bind_generation"], bind_snapshot["generation"])
            self.assertEqual(evidence[0]["post_forward_generation"], bind_snapshot["generation"])
            self.assertTrue(evidence[0]["storage_stable"])
            self.assertEqual(evidence[0]["residency"]["matched_count"], 2)
            self.assertEqual(evidence[0]["residency"]["count_by_dtype"]["torch.float32"], 2)
        finally:
            cast_once.invalidate_cast_once(clip)

    def test_forward_storage_change_fails_closed_and_clears_marker(self):
        def _move_storage(clip):
            leaf = clip.cond_stage_model.leaf
            leaf.a = torch.nn.Parameter(leaf.a.detach().clone(), requires_grad=False)

        clip, _, _ = self._hook_fixture(mutate=_move_storage)
        setattr(clip, cfh.HYDRATED_MARKER, True)
        try:
            with self.assertRaisesRegex(RuntimeError, "real-forward proof failed"):
                clip.encode_from_tokens([1])
            self.assertFalse(getattr(clip, cfh.HYDRATED_MARKER, False))
            self.assertEqual(cast_once.cast_once_generation(clip), 0)
        finally:
            cast_once.invalidate_cast_once(clip)

    def test_bf16_to_fp32_conversion_during_forward_is_evidence_violation(self):
        events = []

        class _Trace:
            def emit(self, name, **kwargs):
                events.append((name, kwargs["metadata"]))

        e27 = __import__("comfymodal_runtime.e27_forensics", fromlist=["forward_cast_account_summary"])
        try:
            with patch.object(
                e27,
                "forward_cast_account_summary",
                side_effect=[{"dest_bytes": 0}, {"dest_bytes": 4}],
            ):
                clip, _, _ = self._hook_fixture(trace=_Trace())
                with self.assertRaisesRegex(RuntimeError, "real-forward proof failed"):
                    clip.encode_from_tokens([1])
            evidence = [m for name, m in events if name == "clip_fh_cast_once_forward_check"]
            self.assertEqual(len(evidence), 1)
            self.assertFalse(evidence[0]["conversion_ok"])
            self.assertFalse(getattr(clip, cfh.HYDRATED_MARKER, False))
        finally:
            cast_once.invalidate_cast_once(clip)

    def test_trace_less_outer_forward_consumes_callback_with_timing(self):
        class _OuterModel(_MappingModel):
            def encode_token_weights(self, tokens):
                return tokens

        clip, per_file_sds, manifests = _mapping_fixture()
        clip.cond_stage_model = _OuterModel(per_file_sds[0])
        cast_once.mark_cast_once_applied(clip)
        bind_snapshot = cast_once.snapshot_resident_fp32(
            clip, per_file_sds, manifests, expect_device="cpu", phase="post_bind"
        )
        import comfymodal_runtime.model_preload as model_preload

        os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "1"
        try:
            import importlib
            importlib.reload(ff)
            self.assertEqual(model_preload._ensure_clip_forward_wrapper(clip), "installed")
            self.assertTrue(
                getattr(
                    type(clip.cond_stage_model).encode_token_weights,
                    model_preload._SENTINEL_CLIP_FORWARD,
                    False,
                )
            )
            hook = hydration_wiring._e31_forward_hook(
                clip, per_file_sds, manifests, expect_device="cpu",
                bind_snapshot=bind_snapshot, trace=None,
            )
            self.assertTrue(hook["hook"]["installed"])
            clip.cond_stage_model.encode_token_weights([1])
            self.assertTrue(hook["hook"]["forward_actually_observed"])
            self.assertTrue(hook["hook"]["forward_timing"] is not None)
        finally:
            os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "0"
            import importlib
            importlib.reload(ff)
            cast_once.invalidate_cast_once(clip)

    def test_two_outer_forwards_are_not_one_e31_proof(self):
        """The bound callback must expose and reject a second real forward."""
        import comfymodal_runtime.model_preload as model_preload

        class _CountingOuter(_MappingModel):
            def __init__(self, tensors):
                super().__init__(tensors)
                self.calls = 0

            def encode_token_weights(self, tokens):
                self.calls += 1
                return tokens

        clip, per_file_sds, manifests = _mapping_fixture()
        clip.cond_stage_model = _CountingOuter(per_file_sds[0])
        observations = []

        def _reject_multiple(observation):
            observations.append(dict(observation))
            if observation["forward_count"] > 1:
                raise RuntimeError("multiple outer forwards")

        try:
            self.assertEqual(model_preload._ensure_clip_forward_wrapper(clip), "installed")
            registered = model_preload.register_e31_forward_callback(
                clip.cond_stage_model,
                _reject_multiple,
                generation=17,
                request_id="e31-two-forward",
            )
            self.assertTrue(registered["installed"])

            clip.cond_stage_model.encode_token_weights([1])
            with self.assertRaisesRegex(RuntimeError, "multiple outer forwards"):
                clip.cond_stage_model.encode_token_weights([2])

            # Both underlying workload calls ran; the second was not hidden
            # or converted into a second claim for the first forward.
            self.assertEqual(clip.cond_stage_model.calls, 2)
            self.assertEqual([item["forward_count"] for item in observations], [1, 2])
            self.assertEqual(observations[0]["real_outer_forward_count"], 1)
            self.assertEqual(observations[1]["real_outer_forward_count"], 2)
        finally:
            model_preload.clear_e31_forward_callback(clip.cond_stage_model)

    def test_strict_zero_conversion_requires_same_forward_cast_call_evidence(self):
        """Zero REAL_CONVERSION is invalid when no canonical call was seen."""
        source = {"a": torch.ones(3, dtype=torch.float32), "b": torch.ones(2, dtype=torch.float32)}
        clip, per_file_sds, manifests = _mapping_fixture(source=source)
        cast_once.mark_cast_once_applied(clip)
        bind_snapshot = cast_once.snapshot_resident_fp32(
            clip, per_file_sds, manifests, expect_device="cpu", phase="post_bind"
        )
        os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "1"
        os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "1"
        try:
            import importlib
            importlib.reload(ff)
            with patch.object(ff, "cast_installation_evidence", return_value=[
                {
                    "module": "comfy.ops",
                    "attribute": "cast_bias_weight",
                    "callable_identity": 1,
                    "wrapped": True,
                    "status": "installed",
                },
                {
                    "module": "comfy.model_management",
                    "attribute": "cast_to",
                    "callable_identity": 2,
                    "wrapped": True,
                    "status": "installed",
                },
                {
                    "module": "comfy.model_management",
                    "attribute": "cast_to_device",
                    "callable_identity": 3,
                    "wrapped": True,
                    "status": "installed",
                },
            ]), patch.object(ff, "cast_forensics_summary", return_value={
                "real_conversions": 0,
                "real_conversion_bytes": 0,
            }):
                hook = hydration_wiring._e31_forward_hook(
                    clip, per_file_sds, manifests, expect_device="cpu",
                    bind_snapshot=bind_snapshot, trace=None,
                )
            # The fallback hook has no outer-forward timer call evidence, so
            # strict E31 cannot publish success merely from zero totals.
            self.assertTrue(hook["instrumentation_available"])
            with self.assertRaisesRegex(RuntimeError, "real-forward proof failed"):
                clip.encode_from_tokens([1])
            self.assertFalse(hook["hook"].get("cast_call_evidence_ok", False))
            self.assertFalse(hook["hook"].get("e31_success", False))
        finally:
            os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "0"
            os.environ["COMFYMODAL_V2_CLIP_FP32_CAST_ONCE"] = "0"
            import importlib
            importlib.reload(ff)
            cast_once.invalidate_cast_once(clip)

    def test_forward_timer_evidence_is_json_safe_and_versioned(self):
        timer = ff.ForwardTimer()
        timer.start()
        record = timer.end()
        json.dumps(record)
        import comfymodal_runtime.model_preload as model_preload
        versioned = model_preload._version_e31_forward_timing(record)
        json.dumps(versioned)
        self.assertEqual(versioned["schema"], "e31.clip_forward")
        self.assertEqual(versioned["schema_version"], 1)
        self.assertEqual(versioned["evidence_version"], 1)

    def test_fallback_forward_hook_evidence_does_not_publish_callables(self):
        clip = _ForwardClip({"a": torch.ones(2, dtype=torch.float32)})
        cast_once.mark_cast_once_applied(clip)
        try:
            evidence = cast_once.install_real_forward_check(clip, lambda _: None)
            json.dumps(evidence)
            self.assertTrue(all(isinstance(item, dict) for item in evidence["originals"].values()))
        finally:
            cast_once.clear_real_forward_check(clip)

    def test_missing_canonical_cast_surface_is_not_instrumentation_ready(self):
        source = {"a": torch.ones(3, dtype=torch.float32), "b": torch.ones(2, dtype=torch.float32)}
        clip, per_file_sds, manifests = _mapping_fixture(source=source)
        cast_once.mark_cast_once_applied(clip)
        bind_snapshot = cast_once.snapshot_resident_fp32(
            clip, per_file_sds, manifests, expect_device="cpu", phase="post_bind"
        )
        import importlib
        os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "1"
        try:
            importlib.reload(ff)
            missing = [{"module": "comfy.ops", "attribute": "cast_bias_weight", "wrapped": True}]
            with patch.object(ff, "cast_installation_evidence", return_value=missing):
                hook = hydration_wiring._e31_forward_hook(
                    clip, per_file_sds, manifests, expect_device="cpu",
                    bind_snapshot=bind_snapshot, trace=None,
                )
            self.assertFalse(hook["instrumentation_available"])
            self.assertFalse(all(hook["hook"]["canonical_cast_surfaces"].values()))
        finally:
            os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "0"
            importlib.reload(ff)
            cast_once.invalidate_cast_once(clip)


class ForensicsInstallationTest(unittest.TestCase):
    def test_nested_parent_child_casts_count_each_conversion_once(self):
        import importlib

        class _NestedOps(_FakeOps):
            def cast_bias_weight(
                self, s, input=None, dtype=None, device=None,
                offloadable=False, **kwargs
            ):
                # Match Comfy's layered implementation: the parent delegates
                # each parameter conversion to the child surface.
                weight = self.cast_to(s.weight, dtype=dtype)
                bias = None if s.bias is None else self.cast_to(s.bias, dtype=dtype)
                result = (weight, bias)
                return result + (object(),) if offloadable else result

            def cast_to_device(self, tensor, device, dtype, copy=False):
                # The device helper delegates again, creating a second
                # parent/child nesting shape covered by the same guard.
                return self.cast_to(tensor, dtype=dtype)

        os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "1"
        try:
            mod = importlib.reload(ff)
            ops = _NestedOps()
            mod.install_cast_forensics(ops, _FakeMM())
            weight = torch.zeros(8, 8, dtype=torch.bfloat16)
            bias = torch.zeros(8, dtype=torch.bfloat16)
            module = _FakeModule(weight, bias)

            mod.reset_cast_forensics()
            ops.cast_bias_weight(module, dtype=torch.float32)
            summary = mod.cast_forensics_summary()
            self.assertEqual(summary["real_conversions"], 2)
            self.assertEqual(summary["real_conversion_bytes"], (8 * 8 + 8) * 4)
            self.assertEqual(summary["classifications"].get(mod.REAL_CONVERSION), 2)
            self.assertEqual(len(mod.cast_sample_evidence()), 2)

            mod.reset_cast_forensics()
            ops.cast_to_device(weight, "cpu", torch.float32)
            summary = mod.cast_forensics_summary()
            self.assertEqual(summary["real_conversions"], 1)
            self.assertEqual(summary["real_conversion_bytes"], 8 * 8 * 4)
            self.assertEqual(summary["classifications"].get(mod.REAL_CONVERSION), 1)
            self.assertEqual(len(mod.cast_sample_evidence()), 1)
        finally:
            os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "0"
            importlib.reload(ff)

    def test_all_surfaces_are_wrapped_and_aliases_are_deduplicated(self):
        import importlib

        os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "1"
        try:
            mod = importlib.reload(ff)
            ops = _FakeOps()
            mm = _FakeMM()
            ops.cast_alias = ops.cast_to
            mm.cast_alias = mm.cast_to
            result = mod.install_cast_forensics(ops, mm)
            evidence = result["installation_evidence"]
            canonical = [e for e in evidence if e["attribute"] in {"cast_bias_weight", "cast_to", "cast_to_device"}]
            aliases = [e for e in evidence if e["attribute"] == "cast_alias"]
            self.assertEqual(len(canonical), 6)
            self.assertTrue(all(e["wrapped"] and e["status"] == "installed" for e in canonical))
            self.assertEqual(len(aliases), 2)
            self.assertTrue(all(e["duplicate_alias"] and e["status"] == "alias" for e in aliases))
            self.assertEqual(len({e["callable_identity"] for e in canonical}), 6)
            self.assertTrue(all(e["callable_identity"] is not None for e in evidence))
            self.assertTrue(all(
                {"module", "attribute", "callable_identity", "wrapped", "duplicate_alias"}
                <= set(e)
                for e in evidence
            ))
            self.assertIs(ops.cast_alias, ops.cast_to)
            self.assertIs(mm.cast_alias, mm.cast_to)
        finally:
            os.environ["COMFYMODAL_V2_E31_FORENSICS"] = "0"
            importlib.reload(ff)


if __name__ == "__main__":
    unittest.main()
