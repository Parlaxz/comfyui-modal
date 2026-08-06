"""Focused tests for the quiesced UNET transfer diagnostic (A/B arm B).

Covers, CPU-only (no CUDA/Modal):
  1  quiesced_transfer_enabled() gate defaults off and honors the env
  2  wait_unet_activation_quiesced is a no-op without activation state
  3  wait_unet_activation_quiesced waits on a scheduled future and emits
     unet_quiesce_wait_start/end events with the measured wait
  4  the request-scoped allowlist carries unet_quiesced_transfer
  5  parse_proc_stat parses a real /proc/<pid>/task/<tid>/stat line
  6  ThreadCpuSampler.stop() returns a bounded summary with per-thread
     totals, affinity/NUMA fields, and transfer GB/s
  7  the worker variance record carries the quiesced_transfer record
"""

from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from concurrent.futures import Future
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from comfymodal_runtime import model_preload as mp
from comfymodal_runtime.thread_cpu_sampler import ThreadCpuSampler, parse_proc_stat
from comfymodal_runtime.trace import RuntimeTrace

_FAKE_STAT_LINE = (
    "12345 (v2-thread-cpu-sampler) S 1 12345 12345 0 -1 4194560 4245 0 1 0 "
    "3 21 0 0 20 0 4 0 1785982163 1234567890 12345 18446744073709551615 "
    "1 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 17 5 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0"
)


def _stat_line(comm: str, processor: int, utime: int = 5, stime: int = 5, tid: int = 9) -> str:
    """Build a realistic /proc/<pid>/task/<tid>/stat line.

    Post-``(comm)`` fields: index 0=state(field 3), 11=utime(field 14),
    12=stime(field 15), 36=processor(field 39).
    """
    _fields = ["S", "1", str(tid), str(tid), "0", "-1", "4194560", "0", "0", "1", "0",
               str(utime), str(stime), "0", "0", "20", "0", "4", "0",
               "1785982163", "1234567890", "0", "18446744073709551615"]
    # fields 23..38 (startcode .. exit_signal) are zeros; index 36 = processor.
    _fields.extend(["0"] * (36 - len(_fields)))
    _fields.append(str(processor))
    _fields.extend(["0", "0", "0", "0", "0", "0"])
    return f"{tid} ({comm}) {' '.join(_fields)}"


_FAKE_STAT_LINE = _stat_line("v2-thread-cpu-sampler", processor=17, utime=3, stime=21, tid=12345)


class QuiescedGateTest(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("COMFYMODAL_V2_UNET_QUIESCED_TRANSFER", None)

    def test_default_off(self):
        os.environ.pop("COMFYMODAL_V2_UNET_QUIESCED_TRANSFER", None)
        self.assertFalse(mp.quiesced_transfer_enabled())

    def test_on_tokens(self):
        for token in ("1", "true", "YES", "on"):
            os.environ["COMFYMODAL_V2_UNET_QUIESCED_TRANSFER"] = token
            self.assertTrue(mp.quiesced_transfer_enabled())

    def test_off_tokens(self):
        for token in ("0", "false", "no", "", "2"):
            os.environ["COMFYMODAL_V2_UNET_QUIESCED_TRANSFER"] = token
            self.assertFalse(mp.quiesced_transfer_enabled())


class QuiescedWaitTest(unittest.TestCase):
    def tearDown(self):
        mp._UNET_ACTIVATION_STATE.clear()

    def test_noop_without_state(self):
        out = mp.wait_unet_activation_quiesced("no-such-request")
        self.assertFalse(out["waited"])
        self.assertFalse(out["scheduled"])
        self.assertEqual(out["reason"], "no_activation_state")

    def test_noop_without_request_id(self):
        out = mp.wait_unet_activation_quiesced("")
        self.assertEqual(out["reason"], "no_request_id")

    def test_waits_on_scheduled_future(self):
        request_id = "q-wait-test-1"
        state = mp._unet_activation_new_state(request_id)
        future = Future()

        def _complete():
            time.sleep(0.05)
            future.set_result({"status": "ready"})

        threading.Thread(target=_complete, daemon=True).start()
        state["future"] = future
        mp._UNET_ACTIVATION_STATE[request_id] = state
        trace = RuntimeTrace(request_id=request_id, process="remote")
        out = mp.wait_unet_activation_quiesced(request_id, trace=trace, timeout_s=5.0)
        self.assertTrue(out["waited"])
        self.assertTrue(out["scheduled"])
        self.assertGreaterEqual(out["wait_ms"], 40.0)
        names = [e.name for e in trace.events]
        self.assertIn("unet_quiesce_wait_start", names)
        self.assertIn("unet_quiesce_wait_end", names)
        end_meta = trace.events[-1].metadata
        self.assertGreaterEqual(float(end_meta.get("wait_ms") or 0.0), 40.0)

    def test_timeout_bounded(self):
        request_id = "q-wait-timeout-1"
        state = mp._unet_activation_new_state(request_id)
        state["future"] = Future()  # never completes
        mp._UNET_ACTIVATION_STATE[request_id] = state
        _start = time.monotonic()
        out = mp.wait_unet_activation_quiesced(request_id, timeout_s=0.3)
        self.assertLess(time.monotonic() - _start, 5.0)
        self.assertTrue(out["timed_out"])
        self.assertTrue(out["waited"])


class AllowlistTest(unittest.TestCase):
    def test_quiesced_transfer_in_allowlist(self):
        from comfymodal_runtime.modal_app import _REQUEST_DIAGNOSTIC_ENV_ALLOWLIST
        self.assertIn(
            ("unet_quiesced_transfer", "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER"),
            _REQUEST_DIAGNOSTIC_ENV_ALLOWLIST,
        )

    def test_apply_request_quiesced_env(self):
        from comfymodal_runtime.modal_app import _apply_request_variance_diagnostics
        os.environ.pop("COMFYMODAL_V2_UNET_QUIESCED_TRANSFER", None)
        applied = _apply_request_variance_diagnostics({"unet_quiesced_transfer": 1})
        self.assertEqual(applied.get("COMFYMODAL_V2_UNET_QUIESCED_TRANSFER"), "1")
        self.assertEqual(os.environ.get("COMFYMODAL_V2_UNET_QUIESCED_TRANSFER"), "1")
        os.environ.pop("COMFYMODAL_V2_UNET_QUIESCED_TRANSFER", None)


class ProcStatParseTest(unittest.TestCase):
    def test_parses_standard_line(self):
        parsed = parse_proc_stat(_FAKE_STAT_LINE)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["tid"], 12345)
        self.assertEqual(parsed["comm"], "v2-thread-cpu-sampler")
        self.assertEqual(parsed["state"], "S")
        self.assertEqual(parsed["utime_jiffies"], 3)
        self.assertEqual(parsed["stime_jiffies"], 21)
        self.assertEqual(parsed["processor"], 17)

    def test_unparsable(self):
        self.assertFalse(parse_proc_stat("")["ok"])
        self.assertFalse(parse_proc_stat("garbage")["ok"])

    def test_comm_with_spaces_and_parens(self):
        parsed = parse_proc_stat(_stat_line("comm (x) with spaces", processor=3))
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["tid"], 9)
        self.assertEqual(parsed["comm"], "comm (x) with spaces")
        self.assertEqual(parsed["utime_jiffies"], 5)
        self.assertEqual(parsed["processor"], 3)


class ThreadCpuSamplerTest(unittest.TestCase):
    def test_stop_returns_bounded_summary(self):
        sampler = ThreadCpuSampler(interval_s=0.05)
        sampler.start()
        time.sleep(0.25)
        summary = sampler.stop(transfer_duration_ms=1234.5, transfer_bytes=12_309_817_472)
        self.assertGreaterEqual(summary["sample_count"], 1)
        self.assertEqual(summary["transfer_duration_ms"], 1234.5)
        self.assertEqual(summary["transfer_bytes"], 12_309_817_472)
        self.assertAlmostEqual(
            summary["effective_gb_per_s"], 12_309_817_472 / 1_000_000_000 / 1.2345, places=2,
        )
        self.assertIsInstance(summary["per_thread_totals"], list)
        # Every per-thread record is bounded and shaped.
        for entry in summary["per_thread_totals"]:
            self.assertIn("tid", entry)
            self.assertIn("comm", entry)
            self.assertIn("cpu_ms", entry)
        self.assertIsInstance(summary["per_interval_samples"], list)
        self.assertLessEqual(len(summary["per_interval_samples"]), 500)

    def test_stop_without_start(self):
        sampler = ThreadCpuSampler()
        summary = sampler.stop()
        self.assertEqual(summary["sample_count"], 0)


class WorkerVarianceRecordTest(unittest.TestCase):
    def test_variance_record_includes_quiesced_transfer(self):
        trace = RuntimeTrace(request_id="var-q-1", process="remote")
        state = {
            "submitted_mono_ns": time.monotonic_ns(),
            "worker_started_mono_ns": time.monotonic_ns(),
            "status": "ready",
            "trigger": "conditioning_cache_hit",
            "key_hash": "k",
        }
        q_record = {"transfer_duration_ms": 100.0, "transfer_bytes": 1000, "effective_gb_per_s": 10.0}
        with patch.object(mp, "variance_diagnostics_enabled", return_value=True):
            mp._emit_unet_worker_variance(
                trace, state=state, request_id="var-q-1", mode="late",
                registry_setup={"wall_ms": 1.0}, page_traversal=None,
                synchronized_load={"wall_ms": 100.0},
                pretouch_record=None, registry_record=None,
                patcher_ms=None, patcher_counts=None, patcher_nested=False,
                quiesced_transfer=q_record,
            )
        evs = [e for e in trace.events if e.name == "unet_activation_worker_variance"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].metadata.get("quiesced_transfer"), q_record)


if __name__ == "__main__":
    unittest.main()
