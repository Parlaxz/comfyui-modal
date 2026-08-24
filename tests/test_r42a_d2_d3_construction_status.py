"""R42A D2/D3 focused contracts.

D2 (UNET construction):
- The Golden detection-input helper reproduces EXACTLY the native
  ``comfy.sd.load_diffusion_model_state_dict`` detection input sequence
  (convert_old_quants -> prefix strip applied ONLY when non-empty).
- A bare-key state dict (no candidate prefix > 5 keys, e.g. z_image-style
  diffusion exports) must produce a NON-EMPTY detection input — the pre-D2
  bug fed an empty dict to ``model_config_from_unet`` -> None ->
  ``model_config_none`` construct fallback.
- No filename-specific hardcoding in the construct wrapper.
- Storage-identity counting treats data_ptr equality as zero-copy proof.

D3 (status truth):
- Terminal native fallbacks are sticky across loader_selection records,
  bridge degradation clears, and final RuntimeStatus assembly inputs.
- Provisional scheduling states never degrade and stay fully clearable.
- Bridge terminal truth forces loader_selection agreement.

D1 (VAE KeyError regression):
- ``bind_vae_payload`` reads ``detail["detail"]["assigned_count"]`` and
  completes without KeyError after a successful strict bind.
"""

from __future__ import annotations

import inspect
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_COMFY_ROOT = str(Path(__file__).resolve().parents[3])
if os.path.isdir(os.path.join(_COMFY_ROOT, "comfy")):
    sys.path.insert(0, _COMFY_ROOT)

import torch  # noqa: E402

from comfymodal_runtime import golden_runtime_bridge as grb  # noqa: E402
from comfymodal_runtime import loader_selection as ls  # noqa: E402
from comfymodal_runtime import model_preload as mp  # noqa: E402
from comfymodal_runtime import runtime_status as rs  # noqa: E402
from comfymodal_runtime.golden.contracts import JoinDecision, ModelRole  # noqa: E402


def _comfy_fns():
    try:
        import comfy.model_detection as md
        import comfy.utils as cu

        return (
            md.unet_prefix_from_state_dict,
            cu.state_dict_prefix_replace,
            cu.convert_old_quants,
        )
    except Exception:
        return (None, None, None)


class TestNativeDetectionInputParity(unittest.TestCase):
    """D2: Golden detection input == native detection input."""

    def _reference_native(self, sd, metadata, prefix_fn, strip_fn, quant_fn):
        """Literal transcription of comfy.sd.load_diffusion_model_state_dict
        lines 1947-1965 (custom_operations=None branch)."""
        detect_sd = dict(sd)
        detect_meta = metadata
        if callable(quant_fn):
            detect_sd, detect_meta = quant_fn(detect_sd, "", metadata=detect_meta)
        prefix = prefix_fn(detect_sd)
        temp = strip_fn(dict(detect_sd), {prefix: ""}, filter_keys=True)
        if len(temp) > 0:
            detect_sd = temp
            if callable(quant_fn):
                detect_sd, detect_meta = quant_fn(detect_sd, "", metadata=detect_meta)
        return detect_sd, detect_meta, prefix

    def _cases(self):
        bare = {f"layers.{i}.weight": None for i in range(8)}
        bare.update({"final_layer.weight": None})
        checkpoint_prefixed = {
            f"model.diffusion_model.layers.{i}.weight": None for i in range(8)
        }
        unprefixed_export = {f"blocks.{i}.weight": None for i in range(8)}
        return [("bare_keys", bare), ("checkpoint_prefix", checkpoint_prefixed), ("other_prefix", unprefixed_export)]

    def test_parity_with_native_sequence(self):
        prefix_fn, strip_fn, quant_fn = _comfy_fns()
        if prefix_fn is None:
            self.skipTest("comfy not importable")
        for name, sd in self._cases():
            with self.subTest(case=name):
                got = mp._native_detection_input(sd, {"k": "v"}, prefix_fn, strip_fn, quant_fn)
                want = self._reference_native(sd, {"k": "v"}, prefix_fn, strip_fn, quant_fn)
                self.assertEqual(got[0], want[0], "detect_sd parity")
                self.assertEqual(got[1], want[1], "metadata parity")
                self.assertEqual(got[2], want[2], "prefix parity")

    def test_bare_keys_detection_input_non_empty(self):
        """THE D2 defect: bare-key files previously produced an EMPTY
        detection state dict (unconditional filter_keys strip against the
        'model.' fallback prefix)."""
        prefix_fn, strip_fn, quant_fn = _comfy_fns()
        if prefix_fn is None:
            self.skipTest("comfy not importable")
        sd = {f"layers.{i}.weight": None for i in range(8)}
        detect_sd, _meta, prefix = mp._native_detection_input(sd, None, prefix_fn, strip_fn, quant_fn)
        self.assertEqual(len(detect_sd), len(sd))
        self.assertEqual(set(detect_sd), set(sd))

    def test_empty_input_never_from_nonempty_input(self):
        prefix_fn, strip_fn, quant_fn = _comfy_fns()
        if prefix_fn is None:
            self.skipTest("comfy not importable")
        for name, sd in self._cases():
            with self.subTest(case=name):
                detect_sd, _meta, _prefix = mp._native_detection_input(
                    sd, None, prefix_fn, strip_fn, quant_fn
                )
                self.assertGreater(len(detect_sd), 0)

    def test_quant_transform_failure_falls_back(self):
        def bad_quant(sd, prefix="", metadata={}):
            raise RuntimeError("boom")

        calls = {"n": 0}

        def prefix_fn(sd):
            return "model."

        def strip_fn(sd, replace, filter_keys=False):
            calls["n"] += 1
            out = {}
            if filter_keys:
                for rp in replace:
                    for k in sd:
                        if k.startswith(rp):
                            out[k[len(rp):]] = sd[k]
            return out

        sd = {f"w{i}": i for i in range(10)}
        detect_sd, meta, prefix = mp._native_detection_input(
            sd, {"m": 1}, prefix_fn, strip_fn, bad_quant
        )
        self.assertEqual(set(detect_sd), set(sd))
        self.assertEqual(meta, {"m": 1})
        self.assertEqual(prefix, "model.")


class TestNoFilenameHardcoding(unittest.TestCase):
    def test_wrapper_has_no_basename_specific_config(self):
        src = inspect.getsource(mp._make_golden_load_diffusion_model_wrapper)
        self.assertNotIn("z_image", src)
        self.assertNotIn("get_filename", src)
        self.assertNotIn("basename ==", src)

    def test_identity_measured_at_diffusion_level(self):
        """Regression: model-level names carry a ``diffusion_model.``
        prefix and never match bare Golden payload keys (vacuous 0/0)."""
        src = inspect.getsource(mp._make_golden_load_diffusion_model_wrapper)
        self.assertIn('getattr(model, "diffusion_model", model)', src)
        self.assertIn("dict(views)", src)  # load_model_weights pops its arg
        inner = torch.nn.Module()
        inner.w = torch.nn.Parameter(torch.zeros(4, 4))
        views = {"w": inner.w}
        counts, ptr_map = mp._storage_identity_counts(dict(inner.named_parameters()), views)
        self.assertEqual(counts["same_storage_count"], 1)
        self.assertEqual(counts["copied_storage_count"], 0)
        self.assertIn("w", ptr_map)

    def test_views_survives_pop_mutating_consumer(self):
        """load_model_weights pops every key from the dict it receives;
        the wrapper must pass a copy so identity measurement still sees
        the full mapping afterwards."""

        def pop_all(sd, prefix=""):
            for k in list(sd.keys()):
                sd.pop(k)

        views = {"w": torch.zeros(4, 4)}
        pop_all(dict(views))
        counts, _pm = mp._storage_identity_counts({"w": views["w"]}, views)
        self.assertEqual(counts["same_storage_count"], 1)


class _FakeTensor:
    def __init__(self, ptr, device="cuda:0", dtype=torch.bfloat16):
        self._ptr = ptr
        self.device = device
        self.dtype = dtype

    def data_ptr(self):
        return self._ptr


class TestStorageIdentityCounts(unittest.TestCase):
    def test_same_objects_are_zero_copy(self):
        src = {"a": _FakeTensor(111), "b": _FakeTensor(222)}
        counts, ptr_map = mp._storage_identity_counts(dict(src), src)
        self.assertEqual(counts["tensor_count"], 2)
        self.assertEqual(counts["same_storage_count"], 2)
        self.assertEqual(counts["copied_storage_count"], 0)
        self.assertEqual(counts["unexpected_device_count"], 0)
        self.assertEqual(counts["unexpected_dtype_count"], 0)
        self.assertEqual(ptr_map["a"], (111, "cuda:0", str(torch.bfloat16)))

    def test_copied_and_wrong_device_counted(self):
        src = {"a": _FakeTensor(111), "b": _FakeTensor(222)}
        bound = {
            "a": _FakeTensor(999),
            "b": _FakeTensor(222, device="cpu"),
        }
        counts, _pm = mp._storage_identity_counts(bound, src)
        self.assertEqual(counts["same_storage_count"], 1)
        self.assertEqual(counts["copied_storage_count"], 1)
        self.assertEqual(counts["unexpected_device_count"], 1)

    def test_torch_zero_copy_bind_shares_storage(self):
        src = {"w": torch.zeros(4, 4)}
        module_param = torch.nn.Parameter(src["w"])  # assign-style share
        counts, _pm = mp._storage_identity_counts({"w": module_param}, src)
        self.assertEqual(counts["copied_storage_count"], 0)
        self.assertEqual(counts["same_storage_count"], 1)


class TestNativeIoWindow(unittest.TestCase):
    def setUp(self):
        self.ctx = grb.GoldenRunContext(join_timeout_s=5.0)

    def test_counter_increments(self):
        before = dict(self.ctx.native_io_counters)
        self.ctx.count_native_source_read("nonexistent-file.safetensors")
        self.assertEqual(
            self.ctx.native_io_counters["native_load_torch_file_calls"],
            before["native_load_torch_file_calls"] + 1,
        )

    def test_window_delta_and_idempotent_close(self):
        self.ctx.begin_native_io_window()
        self.ctx.count_native_source_read("x.safetensors")
        self.ctx.end_native_io_window("sampling_start")
        report = self.ctx.telemetry.get("native_post_ready_io", {})
        self.assertEqual(report.get("window_reason"), "sampling_start")
        self.assertEqual(report.get("native_load_torch_file_calls"), 1)
        if not report.get("physical_storage_read_bytes") == "UNOBSERVABLE":
            # Linux: physical bytes must be a measured int
            self.assertIsInstance(report.get("physical_storage_read_bytes"), int)
        else:
            self.assertEqual(report.get("physical_storage_read_bytes"), "UNOBSERVABLE")
        # second close is a no-op
        self.ctx.telemetry.pop("native_post_ready_io")
        self.ctx.end_native_io_window("again")
        self.assertNotIn("native_post_ready_io", self.ctx.telemetry)

    def test_close_without_open_is_noop(self):
        self.ctx.end_native_io_window("sampling_start")
        self.assertNotIn("native_post_ready_io", self.ctx.telemetry)


class TestLoaderSelectionStickyFallback(unittest.TestCase):
    def setUp(self):
        ls.reset_for_run()
        ls.seed_from_resolved({"clip": "golden_qd4", "unet": "golden_qd4", "vae": "golden_qd4"})

    def tearDown(self):
        ls.reset_for_run()

    def test_fallback_recorded_when_observed_empty(self):
        ls.record_observed("unet", "native_comfy", fallback_attempted=True,
                           fallback_loader="native_comfy", fallback_reason="construct:x")
        snap = ls.snapshot()["unet"]
        self.assertTrue(snap["fallback_attempted"])
        self.assertEqual(snap["observed"], "native_comfy")

    def test_late_golden_success_cannot_clear_terminal_fallback(self):
        ls.record_observed("unet", "native_comfy", fallback_attempted=True,
                           fallback_loader="native_comfy", fallback_reason="construct:x")
        ls.record_observed("unet", "golden_qd4")
        snap = ls.snapshot()["unet"]
        self.assertTrue(snap["fallback_attempted"])
        self.assertEqual(snap["observed"], "native_comfy")
        self.assertEqual(snap["fallback_loader"], "native_comfy")

    def test_provisional_native_probe_still_clearable_by_golden_success(self):
        ls.record_observed("unet", "native_comfy")  # transient probe, no flag
        ls.record_observed("unet", "golden_qd4")  # golden succeeds later
        snap = ls.snapshot()["unet"]
        self.assertEqual(snap["observed"], "golden_qd4")
        self.assertFalse(snap["fallback_attempted"])

    def test_mismatches_report_fallback(self):
        ls.record_observed("vae", "native_comfy", fallback_attempted=True,
                           fallback_loader="native_comfy", fallback_reason="schedule_denied")
        reasons = ls.mismatches()
        self.assertTrue(any(r.startswith("loader_fallback_vae") for r in reasons))


class TestBridgeTerminalAuthority(unittest.TestCase):
    def setUp(self):
        ls.reset_for_run()
        ls.seed_from_resolved({"clip": "golden_qd4", "unet": "golden_qd4", "vae": "golden_qd4"})
        self.ctx = grb.GoldenRunContext(join_timeout_s=5.0)

    def tearDown(self):
        ls.reset_for_run()

    def test_terminal_role_registered_and_summarized(self):
        self.ctx.record_real_fallback("unet", "construct_fallback:model_config_none")
        self.assertIn("unet", self.ctx.terminal_fallback_roles())
        summary = self.ctx.role_lifecycle_summary()["unet"]
        self.assertTrue(summary["native_fallback_executed"])
        self.assertEqual(summary["terminal_reason"], "construct_fallback:model_config_none")

    def test_status_reasons_survive_degradation_clear(self):
        self.ctx.record_real_fallback("unet", "construct_fallback:x")
        self.ctx.degradations.clear()  # even hostile clearing cannot erase truth
        self.assertIn("golden_qd_fallback:unet", self.ctx.status_reasons())

    def test_provisional_states_do_not_degrade(self):
        for text in (
            "schedule_not_yet_allowed",
            "producer_pending",
            "waiting_for_first_sampler_step",
            "joining_owner",
            "resource_temporarily_denied",
        ):
            self.ctx.add_degradation(text)
        self.assertEqual(self.ctx.terminal_fallback_roles(), [])
        self.ctx.clear_role_fallback_degradations("vae")
        for text in (
            "schedule_not_yet_allowed",
            "producer_pending",
            "waiting_for_first_sampler_step",
            "joining_owner",
            "resource_temporarily_denied",
        ):
            self.assertIn(text, self.ctx.status_reasons())
        self.assertNotIn("vae", self.ctx.terminal_fallback_roles())

    def test_enforce_loader_selection_consistency(self):
        self.ctx.record_real_fallback("unet", "construct_fallback:model_config_none")
        reconciled = self.ctx.enforce_loader_selection_consistency()
        self.assertIn("unet", reconciled)
        snap = ls.snapshot()["unet"]
        self.assertTrue(snap["fallback_attempted"])
        self.assertEqual(snap["fallback_loader"], "native_comfy")

    def test_runtime_status_degraded_on_terminal_nominal_on_success(self):
        self.ctx.record_real_fallback("unet", "construct_fallback:model_config_none")
        reasons = grb.map_degradation_to_reasons(self.ctx.status_reasons())
        status = rs.build_runtime_status(loader_selection=ls.snapshot(), reasons=reasons)
        self.assertEqual(status["status"], "DEGRADED")
        self.assertTrue(any("unet" in r for r in status["reasons"]))
        # all-success lifecycle -> NOMINAL
        ok_ctx = grb.GoldenRunContext(join_timeout_s=5.0)
        ok_reasons = grb.map_degradation_to_reasons(ok_ctx.status_reasons())
        ok_status = rs.build_runtime_status(loader_selection=ls.snapshot(), reasons=ok_reasons)
        self.assertEqual(ok_status["status"], "NOMINAL")
        self.assertEqual(ok_status["reasons"], [])


class TestVaeBindKeyErrorRegression(unittest.TestCase):
    """D1: successful strict bind must read the NESTED assigned_count."""

    class _FirstStage(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.dec_w = torch.nn.Parameter(torch.empty(8, 8))

    class _FakeVae:
        def __init__(self):
            self.first_stage_model = TestVaeBindKeyErrorRegression._FirstStage()

    def test_bind_vae_payload_success_without_keyerror(self):
        ctx = grb.GoldenRunContext(join_timeout_s=5.0)
        payload = {"dec_w": torch.randn(8, 8)}
        owner = type("Owner", (), {"identity_hash": "ih", "payload": None})()
        ctx.join_vae = lambda timeout_s=None: (JoinDecision.ALREADY_READY, owner)
        ctx.vae_payload = lambda timeout_s=0.0: dict(payload)
        vae = self._FakeVae()
        ok = ctx.bind_vae_payload(vae, timeout_s=5.0)
        self.assertTrue(ok)
        self.assertEqual(ctx._role_lifecycle["vae"]["state"], "ADOPTED")
        self.assertNotIn("vae", ctx.terminal_fallback_roles())
        # zero-copy: parameter shares the Golden storage
        param = vae.first_stage_model.dec_w
        self.assertEqual(param.data.data_ptr(), payload["dec_w"].data_ptr())

    def test_bind_mismatch_records_real_fallback_not_keyerror(self):
        ctx = grb.GoldenRunContext(join_timeout_s=5.0)
        payload = {"dec_w": torch.randn(16, 8)}  # wrong shape vs module
        owner = type("Owner", (), {"identity_hash": "ih", "payload": None})()
        ctx.join_vae = lambda timeout_s=None: (JoinDecision.ALREADY_READY, owner)
        ctx.vae_payload = lambda timeout_s=0.0: dict(payload)
        vae = self._FakeVae()
        ok = ctx.bind_vae_payload(vae, timeout_s=5.0)
        self.assertFalse(ok)
        self.assertIn("vae", ctx.terminal_fallback_roles())


if __name__ == "__main__":
    unittest.main()
