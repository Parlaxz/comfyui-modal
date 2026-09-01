"""Focused offline coverage for the opt-in Golden sampler timeline."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from comfymodal_runtime import golden_serial as gs


class _Handle:
    def __init__(self, owner, hooks):
        self.owner = owner
        self.hooks = hooks

    def remove(self):
        for hook in self.hooks:
            if hook in self.owner.hooks:
                self.owner.hooks.remove(hook)


class _HookModel:
    def __init__(self):
        self.hooks = []
        self._cache_dit_state = {
            "compute_count": 10,
            "skip_count": 7,
            "cache_hit_rate": 0.4,
            "recompute_reasons": ["warmup"],
        }

    def register_forward_pre_hook(self, hook, **kwargs):
        self.hooks.append(hook)
        return _Handle(self, [hook])

    def register_forward_hook(self, hook):
        self.hooks.append(hook)
        return _Handle(self, [hook])

    def __call__(self, value):
        for hook in list(self.hooks):
            if getattr(hook, "__name__", "").startswith("pre"):
                hook(self, (value,), {})
        for hook in list(self.hooks):
            if not getattr(hook, "__name__", "").startswith("pre"):
                hook(self, (value,), value)
        return value


class GoldenSamplingDiagnosticsTests(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(gs.GOLDEN_SAMPLING_DIAGNOSTICS_ENV, None)
            self.assertFalse(gs._sampling_diagnostics_enabled())

    def test_timeline_callback_forward_cleanup_and_passive_cachedit(self):
        recorder = gs.GoldenTelemetryRecorder()
        diagnostics = gs.GoldenSamplingDiagnostics(
            recorder, sampler_id="137", sampler_class=gs.CANONICAL_SAMPLER_CLASS
        )
        model = _HookModel()
        patcher = SimpleNamespace(model=SimpleNamespace(diffusion_model=model))
        diagnostics.install_model_hooks(patcher)

        calls = []

        def callback(index, *args):
            calls.append(index)

        wrapped = diagnostics.wrap_sampler_inputs({"callback": callback})["callback"]
        wrapped(2, None, None, 8)
        model("latent")
        diagnostics.finish_sampling(patcher, ok=True)
        diagnostics.cleanup()

        payload = diagnostics.to_json_dict()
        self.assertEqual(calls, [2])
        self.assertEqual(payload["callback"]["count"], 1)
        self.assertEqual(payload["model_forward"]["count"], 1)
        self.assertEqual(payload["model_forward"]["first_wall_ms"], payload["timeline"][2]["wall_ms"])
        self.assertEqual(payload["cachedit"]["computed"], 10)
        self.assertEqual(payload["cachedit"]["skipped"], 7)
        self.assertEqual(payload["cachedit"]["hit_rate"], 0.4)
        self.assertTrue(payload["cleanup_complete"])
        self.assertEqual(model.hooks, [])
        self.assertEqual(payload["sampler"]["boundary_status"], "fallback")
        self.assertEqual(
            payload["sampler"]["boundary"],
            "diagnostic_sampling_start->diagnostic_sampling_end",
        )
        self.assertTrue(payload["sampler"]["non_additive"])

    def test_actual_sampler_boundaries_drive_wall_and_step_partition(self):
        recorder = gs.GoldenTelemetryRecorder()
        diagnostics = gs.GoldenSamplingDiagnostics(
            recorder, sampler_id="137", sampler_class=gs.CANONICAL_SAMPLER_CLASS
        )
        patcher = SimpleNamespace(model=SimpleNamespace(diffusion_model=None))
        diagnostics.begin(SimpleNamespace(recorder=recorder))

        wrapped = diagnostics.wrap_sampler_inputs({"callback": lambda *_args: None})["callback"]
        wrapped(2, None, None, 8)
        callback_start_ns = diagnostics._callbacks[0]["start_ns"]
        sampler_start_ns = callback_start_ns - 5_000_000
        sampler_end_ns = callback_start_ns + 5_000_000

        diagnostics.finish_sampling(
            patcher,
            ok=True,
            sampler_start_ns=sampler_start_ns,
            sampler_end_ns=sampler_end_ns,
        )
        payload = diagnostics.to_json_dict()

        self.assertEqual(diagnostics.sampler_wall_ms, 10.0)
        self.assertEqual(payload["sampler"]["boundary_status"], "observed")
        self.assertEqual(
            payload["sampler"]["boundary"],
            "actual_sampler_function_entry->actual_sampler_function_return",
        )
        self.assertEqual(payload["sampler"]["boundary_start_monotonic_ns"], sampler_start_ns)
        self.assertEqual(payload["sampler"]["boundary_end_monotonic_ns"], sampler_end_ns)
        self.assertEqual(payload["step_partition"]["start_monotonic_ns"], sampler_start_ns)
        self.assertEqual(
            payload["steps"][0]["wall_ms"],
            diagnostics._duration_ms(sampler_start_ns, callback_start_ns),
        )
        self.assertEqual(payload["step_partition"]["scope"], "PARTIAL")
        self.assertTrue(payload["step_partition"]["non_additive"])


if __name__ == "__main__":
    unittest.main()
