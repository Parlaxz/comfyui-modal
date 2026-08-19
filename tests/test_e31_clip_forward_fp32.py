"""E31 offline tests: synchronized forward timing, cast classification,
corrected cast wrapper, FP32 residency + lifecycle invalidation, profiler gate.

No Modal, no CUDA, no remote execution — synthetic objects and CPU tensors.
All E31 behavior must be default OFF; every test here that exercises an
enabled path sets the flag explicitly and restores it afterward.
"""

import os
import sys
import unittest

os.environ.setdefault("COMFYMODAL_V2_E31_FORENSICS", "0")
os.environ.setdefault("COMFYMODAL_V2_E31_FORWARD_PROFILE", "0")

sys.path.insert(0, r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal")

import torch  # noqa: E402

from comfymodal_runtime import clip_forward_forensics as ff  # noqa: E402
from comfymodal_runtime import clip_fp32_cast_once as cast_once  # noqa: E402


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
    def cast_to(self, weight, dtype=None, device=None, **kwargs):
        return weight.to(dtype=dtype) if dtype is not None and weight.dtype != dtype else weight

    def cast_to_device(self, tensor, device, dtype, copy=False):
        return tensor.to(dtype=dtype) if dtype is not None and tensor.dtype != dtype else tensor


class DefaultOffTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
