"""Focused tests for the one-shot, non-destructive sampler-stall watchdog.

Covers (bounded runtime fix):
  - exact deadlines: 5s for the first UNET forward and 15s from watchdog
    arm / sampling start for the first completed sampler step (NOT 5s + 15s)
  - a diagnostic ``[v2.sampler_stall_watchdog]`` record is emitted ONLY when
    a threshold is missed (status=timeout, once per stage)
  - normal completion and cancel are SILENT (no status=ok / status=cancelled)
  - daemon/self-cleaning: the watchdog thread exits and the registry cleans up
  - no duplicate watchdog per request (idempotent start)
  - mark methods are deduplicated (single latency per stage)

Uses real threading with short injected timeouts — no GPU needed.
"""

from __future__ import annotations

import io
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from comfymodal_runtime import model_preload as mp


def _cleanup_registry():
    with mp._SAMPLER_STALL_WATCHDOG_LOCK:
        for watchdog in list(mp._SAMPLER_STALL_WATCHDOGS.values()):
            watchdog.cancel()
        mp._SAMPLER_STALL_WATCHDOGS.clear()


class SamplerStallWatchdogTests(unittest.TestCase):
    def setUp(self):
        self._cleanup = True
        _cleanup_registry()
        self.addCleanup(_cleanup_registry)

    def test_exact_default_deadlines(self):
        """The configured deadlines are exactly 5s (forward) and 15s (step),
        both measured from watchdog arm / sampling start."""
        self.assertEqual(mp._SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S, 5.0)
        self.assertEqual(mp._SAMPLER_STALL_FIRST_STEP_TIMEOUT_S, 15.0)

    def test_armed_line_preserves_required_fields(self):
        """The armed [v2.sampler_stall_watchdog] line carries the required
        fields: request_id, restored_instance_id, sampler_node_id,
        sampler_class, patcher_object_id, diffusion_model_object_id,
        unet_object_id and both exact deadlines."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            mp.start_sampler_stall_watchdog(
                request_id="wd-fields",
                restored_instance_id="ri-1",
                sampler_node_id="node-7",
                sampler_class="KSampler",
                patcher_object_id="p-1",
                diffusion_model_object_id="dm-1",
                unet_object_id="u-1",
            )
            mp.cancel_sampler_stall_watchdog("wd-fields")
        lines = buf.getvalue()
        self.assertIn("stage=armed", lines)
        self.assertIn("request_id=wd-fields", lines)
        self.assertIn("restored_instance_id=ri-1", lines)
        self.assertIn("sampler_node_id=node-7", lines)
        self.assertIn("sampler_class=KSampler", lines)
        self.assertIn("patcher_object_id=p-1", lines)
        self.assertIn("diffusion_model_object_id=dm-1", lines)
        self.assertIn("unet_object_id=u-1", lines)
        self.assertIn("first_forward_timeout_s=5.0", lines)
        self.assertIn("first_step_timeout_s=15.0", lines)

    def test_normal_completion_is_silent(self):
        """Armed watchdog + first forward + first step -> NO diagnostic
        records (silent): normal completion must not emit status=ok or
        status=cancelled; only the armed boundary line is present."""
        buf = io.StringIO()
        with patch.object(mp, "_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S", 2.0), \
             patch.object(mp, "_SAMPLER_STALL_FIRST_STEP_TIMEOUT_S", 2.0), \
             redirect_stdout(buf):
            armed = mp.start_sampler_stall_watchdog(
                request_id="wd-normal",
                restored_instance_id="ri-1",
                sampler_node_id="node-7",
                sampler_class="KSampler",
                patcher_object_id="p-1",
                diffusion_model_object_id="dm-1",
                unet_object_id="u-1",
            )
            self.assertTrue(armed)
            mp.mark_first_unet_forward("wd-normal")
            mp.mark_first_sampler_step("wd-normal")
            mp.cancel_sampler_stall_watchdog("wd-normal")
            # Give the daemon thread a moment to finish.
            time.sleep(0.3)

        lines = buf.getvalue()
        self.assertIn("stage=armed", lines)
        self.assertNotIn("status=ok", lines)
        self.assertNotIn("status=cancelled", lines)
        self.assertNotIn("status=timeout", lines)
        # Registry cleaned.
        with mp._SAMPLER_STALL_WATCHDOG_LOCK:
            self.assertNotIn("wd-normal", mp._SAMPLER_STALL_WATCHDOGS)

    def test_cancel_is_silent(self):
        """cancel() with no marks is SILENT: no status=cancelled record, no
        timeout record, and the daemon thread exits promptly."""
        buf = io.StringIO()
        with patch.object(mp, "_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S", 60.0), \
             patch.object(mp, "_SAMPLER_STALL_FIRST_STEP_TIMEOUT_S", 60.0), \
             redirect_stdout(buf):
            mp.start_sampler_stall_watchdog(request_id="wd-cancel-silent")
            mp.cancel_sampler_stall_watchdog("wd-cancel-silent")
            time.sleep(0.3)
        lines = buf.getvalue()
        self.assertIn("stage=armed", lines)
        self.assertNotIn("status=cancelled", lines)
        self.assertNotIn("status=timeout", lines)
        with mp._SAMPLER_STALL_WATCHDOG_LOCK:
            self.assertNotIn("wd-cancel-silent", mp._SAMPLER_STALL_WATCHDOGS)

    def test_stall_reports_timeout_once_per_stage(self):
        """No marks -> both stages report status=timeout exactly once and the
        watchdog self-cleans."""
        buf = io.StringIO()
        with patch.object(mp, "_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S", 0.2), \
             patch.object(mp, "_SAMPLER_STALL_FIRST_STEP_TIMEOUT_S", 0.2), \
             redirect_stdout(buf):
            armed = mp.start_sampler_stall_watchdog(
                request_id="wd-stall", restored_instance_id="ri-2",
            )
            self.assertTrue(armed)
            time.sleep(1.0)  # let both timeouts fire

        lines = buf.getvalue()
        self.assertIn(
            "[v2.sampler_stall_watchdog] stage=first_unet_forward status=timeout", lines
        )
        self.assertIn(
            "[v2.sampler_stall_watchdog] stage=first_sampler_step status=timeout", lines
        )
        self.assertEqual(lines.count("stage=first_unet_forward status=timeout"), 1)
        self.assertEqual(lines.count("stage=first_sampler_step status=timeout"), 1)
        self.assertIn("timeout_s=0.2", lines)
        with mp._SAMPLER_STALL_WATCHDOG_LOCK:
            self.assertNotIn("wd-stall", mp._SAMPLER_STALL_WATCHDOGS)

    def test_step_deadline_is_from_arm_not_cumulative(self):
        """The step deadline is measured from watchdog arm, NOT cumulative
        forward(5s) + step(15s).  With injected 0.15s forward / 0.5s step
        deadlines: a forward that times out at ~0.15s must NOT extend the
        step deadline — a step marked at 0.3s (before arm+0.5s) still passes
        without a step-timeout record."""
        buf = io.StringIO()
        with patch.object(mp, "_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S", 0.15), \
             patch.object(mp, "_SAMPLER_STALL_FIRST_STEP_TIMEOUT_S", 0.5), \
             redirect_stdout(buf):
            mp.start_sampler_stall_watchdog(
                request_id="wd-deadline", restored_instance_id="ri-3",
            )
            # Let the forward threshold lapse without marking it.
            time.sleep(0.25)
            # Mark the step well before arm+0.5s -> no step timeout.
            mp.mark_first_sampler_step("wd-deadline")
            mp.cancel_sampler_stall_watchdog("wd-deadline")
            time.sleep(0.6)
        lines = buf.getvalue()
        # Forward threshold was missed -> exactly one forward timeout record.
        self.assertEqual(lines.count("stage=first_unet_forward status=timeout"), 1)
        # Step was completed before the arm-relative deadline -> no step
        # timeout record (proves the deadline is NOT 0.15s + 0.5s).
        self.assertEqual(lines.count("stage=first_sampler_step status=timeout"), 0)

    def test_cancel_finishes_without_keeping_thread_alive(self):
        """cancel() wakes the daemon thread; it exits without hanging."""
        with patch.object(mp, "_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S", 60.0), \
             patch.object(mp, "_SAMPLER_STALL_FIRST_STEP_TIMEOUT_S", 60.0):
            mp.start_sampler_stall_watchdog(request_id="wd-cancel")
            with mp._SAMPLER_STALL_WATCHDOG_LOCK:
                watchdog = mp._SAMPLER_STALL_WATCHDOGS["wd-cancel"]
            mp.cancel_sampler_stall_watchdog("wd-cancel")
            thread = watchdog._thread
            self.assertIsNotNone(thread)
            thread.join(timeout=2.0)
            self.assertFalse(thread.is_alive(), "watchdog thread must exit on cancel")
            with mp._SAMPLER_STALL_WATCHDOG_LOCK:
                self.assertNotIn("wd-cancel", mp._SAMPLER_STALL_WATCHDOGS)

    def test_no_duplicate_watchdog_per_request(self):
        """Second start for the same request_id returns False and does not
        create a duplicate watchdog."""
        with patch.object(mp, "_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S", 0.2), \
             patch.object(mp, "_SAMPLER_STALL_FIRST_STEP_TIMEOUT_S", 0.2):
            first = mp.start_sampler_stall_watchdog(request_id="wd-dup")
            second = mp.start_sampler_stall_watchdog(request_id="wd-dup")
            self.assertTrue(first)
            self.assertFalse(second)
            with mp._SAMPLER_STALL_WATCHDOG_LOCK:
                self.assertEqual(len(mp._SAMPLER_STALL_WATCHDOGS), 1)
                self.assertIn("wd-dup", mp._SAMPLER_STALL_WATCHDOGS)
            mp.cancel_sampler_stall_watchdog("wd-dup")

    def test_marks_deduplicated_single_latency(self):
        """Repeated marks produce a single latency record per stage."""
        with patch.object(mp, "_SAMPLER_STALL_FIRST_FORWARD_TIMEOUT_S", 2.0), \
             patch.object(mp, "_SAMPLER_STALL_FIRST_STEP_TIMEOUT_S", 2.0):
            mp.start_sampler_stall_watchdog(request_id="wd-mark")
            with mp._SAMPLER_STALL_WATCHDOG_LOCK:
                watchdog = mp._SAMPLER_STALL_WATCHDOGS["wd-mark"]
            mp.mark_first_unet_forward("wd-mark")
            mp.mark_first_unet_forward("wd-mark")
            mp.mark_first_unet_forward("wd-mark")
            mp.mark_first_sampler_step("wd-mark")
            mp.mark_first_sampler_step("wd-mark")
            self.assertTrue(watchdog._forward_seen)
            self.assertTrue(watchdog._step_seen)
            self.assertIsNotNone(watchdog._forward_latency_ms)
            self.assertIsNotNone(watchdog._step_latency_ms)
            self.assertTrue(watchdog._unet_forward_event.is_set())
            self.assertTrue(watchdog._sampler_step_event.is_set())
            mp.cancel_sampler_stall_watchdog("wd-mark")

    def test_unarmed_mark_is_noop(self):
        """mark_* on a request with no armed watchdog is a safe no-op."""
        mp.mark_first_unet_forward("wd-absent")
        mp.mark_first_sampler_step("wd-absent")
        with mp._SAMPLER_STALL_WATCHDOG_LOCK:
            self.assertNotIn("wd-absent", mp._SAMPLER_STALL_WATCHDOGS)


if __name__ == "__main__":
    unittest.main()
