"""Tests for comfymodal_runtime.variance_diagnostics.

Covers, without requiring CUDA/Modal/torch:
  1  variance gate default off and enable semantics
  2  pretouch gate default off and enable semantics
  3  page_aligned_ranges alignment for a fake StorageRegistry
  4  read_storage_pages real-reads every page (checksum, bounded)
  5  read_storage_pages respects the page budget (bounded)
  6  non-power-of-two page size rejected
  7  pretouch_unet_storage over a StorageRegistry returns a JSON-safe record
  8  pretouch_unet_storage empty registry -> status=empty
  9  pretouch_unet_storage exception -> status=error (exception-safe)
  9  capture_metric_snapshot keys + JSON-safe
 10  compute_metric_deltas same-tid thread cpu + faults + effective gb/s
 11  compute_metric_deltas differing tid -> thread-bounded fields None
 12  bounded_record truncates ranges list
 13  activation_join_wait_ms reads existing trace boundaries (or None)
 14  emit_stage_variance / variance_stage no-op when gate off
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from comfymodal_runtime.cpu_snapshot_models import StorageRange, StorageRegistry
from comfymodal_runtime import variance_diagnostics as vd
from comfymodal_runtime.trace import RuntimeTrace

_HAS_TORCH = False
try:
    import torch
    _HAS_TORCH = True
except ImportError:
    torch = None

_VAR_ENV = "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"
_PT_ENV = "COMFYMODAL_V2_UNET_PRETOUCH"


def _registry(*ranges, total_bytes=0, **kwargs):
    return StorageRegistry(ranges=tuple(ranges), total_bytes=total_bytes, **kwargs)


class VarianceGatesTest(unittest.TestCase):
    def test_variance_gate_default_off(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_VAR_ENV, None)
            self.assertFalse(vd.variance_diagnostics_enabled())

    def test_variance_gate_enabled(self):
        with patch.dict(os.environ, {_VAR_ENV: "1"}, clear=False):
            self.assertTrue(vd.variance_diagnostics_enabled())

    def test_pretouch_gate_default_off(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_PT_ENV, None)
            self.assertFalse(vd.unet_pretouch_enabled())

    def test_pretouch_gate_enabled(self):
        with patch.dict(os.environ, {_PT_ENV: "on"}, clear=False):
            self.assertTrue(vd.unet_pretouch_enabled())


class PageTraversalTest(unittest.TestCase):
    def test_page_aligned_ranges(self):
        reg = _registry(StorageRange(address=100, length=6000))
        with patch.object(vd, "_page_size", return_value=4096):
            ranges = vd.page_aligned_ranges(reg)
        self.assertEqual(ranges, [(0, 2)])  # 0..4096, 4096..8192

    def test_read_storage_pages_reads_every_page(self):
        reg = _registry(
            StorageRange(address=100, length=6000),     # 2 pages
            StorageRange(address=100000, length=8192),  # 3 pages (unaligned span)
        )
        touched: list[tuple[int, int]] = []

        def fake_reader(address, length):
            touched.append((address, length))
            return b"\x01" * length

        with patch.object(vd, "_page_size", return_value=4096):
            result = vd.read_storage_pages(reg, reader=fake_reader)
        self.assertEqual(result["touched_pages"], 5)
        self.assertEqual(result["expected_pages"], 5)
        self.assertEqual(len(touched), 5)
        self.assertIsInstance(result["checksum"], int)

    def test_read_storage_pages_bounded(self):
        reg = _registry(StorageRange(address=0, length=4096 * 5))
        count = 0

        def fake_reader(address, length):
            nonlocal count
            count += 1
            return b"\x00" * length

        with patch.object(vd, "_page_size", return_value=4096):
            result = vd.read_storage_pages(reg, reader=fake_reader, max_pages=3)
        self.assertEqual(result["touched_pages"], 3)
        self.assertEqual(result["expected_pages"], 5)
        self.assertEqual(count, 3)
        self.assertEqual(result["status"], "bounded")

    def test_non_power_of_two_page_rejected(self):
        reg = _registry(StorageRange(address=0, length=4096))
        result = vd.read_storage_pages(reg, page_size=3000)
        self.assertEqual(result["status"], "invalid_page_size")
        self.assertEqual(result["touched_pages"], 0)

    def test_page_aligned_ranges_invalid_returns_empty(self):
        reg = _registry(StorageRange(address=4096, length=4096))
        self.assertEqual(vd.page_aligned_ranges(reg, page_size=3000), [])
        self.assertEqual(vd.page_aligned_ranges(reg, page_size=0), [])

    def test_read_storage_pages_counts_failed_reads(self):
        reg = _registry(StorageRange(address=4096, length=4096))  # 1 page

        def fake_reader(address, length):
            raise OSError("unreadable")

        result = vd.read_storage_pages(reg, reader=fake_reader)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["touched_pages"], 0)
        self.assertEqual(result["failed_pages"], 1)
        self.assertIsNone(result["checksum"])  # no successful read -> no proof

    def test_read_storage_pages_empty_read_not_touched(self):
        reg = _registry(StorageRange(address=4096, length=4096))

        def fake_reader(address, length):
            return b""  # empty read must NOT count as touched

        result = vd.read_storage_pages(reg, reader=fake_reader)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["touched_pages"], 0)
        self.assertEqual(result["failed_pages"], 1)

    def test_checksum_folds_real_bytes(self):
        self.assertEqual(vd.fold_checksum(b"abcd"), vd.fold_checksum(b"abcd"))
        self.assertNotEqual(vd.fold_checksum(b"abcd"), vd.fold_checksum(b"abce"))


class PreTouchTest(unittest.TestCase):
    def test_pretouch_registry_returns_json_safe_record(self):
        reg = _registry(StorageRange(address=4096, length=4096), total_bytes=4096,
                        unique_storage_count=1, raw_byte_count=4096)
        with patch.object(vd, "_default_page_reader", return_value=b"\xAB" * 4096):
            record = vd.pretouch_unet_storage(reg)
        self.assertEqual(record["status"], "ok")
        self.assertEqual(record["touched_pages"], 1)
        self.assertEqual(record["expected_pages"], 1)
        self.assertEqual(record["total_bytes"], 4096)
        self.assertEqual(record["unique_storage_count"], 1)
        self.assertIsInstance(record["checksum"], int)
        # Report-compatible aliases (tools/variance_report.py).
        self.assertEqual(record["total_pages"], record["expected_pages"])
        self.assertEqual(record["bytes"], record["bytes_read"])
        json.dumps(record)  # must be JSON-safe

    def test_pretouch_empty_registry(self):
        reg = _registry()
        with patch.object(vd, "_default_page_reader", return_value=b"\x00"):
            record = vd.pretouch_unet_storage(reg)
        self.assertEqual(record["status"], "empty")
        self.assertEqual(record["touched_pages"], 0)

    def test_pretouch_exception_safe(self):
        reg = _registry(StorageRange(address=4096, length=4096))
        with patch.object(vd, "read_storage_pages", side_effect=RuntimeError("boom")):
            record = vd.pretouch_unet_storage(reg)
        self.assertEqual(record["status"], "error")
        self.assertIn("boom", record["error"])
        self.assertIn("duration_ms", record)

    def test_pretouch_reports_alias_overlap_unsupported(self):
        reg = _registry(
            StorageRange(address=4096, length=4096), total_bytes=4096,
            unique_storage_count=1, raw_byte_count=8192,
            alias_count=1, overlap_count=1, overlap_bytes=4096,
            unsupported_count=2,
            unsupported_entries=({"reason": "meta"}, {"reason": "sparse"}),
        )
        with patch.object(vd, "_default_page_reader", return_value=b"\x00" * 4096):
            record = vd.pretouch_unet_storage(reg)
        self.assertEqual(record["alias_count"], 1)
        self.assertEqual(record["overlap_count"], 1)
        self.assertEqual(record["overlap_bytes"], 4096)
        self.assertEqual(record["unsupported_count"], 2)
        self.assertEqual(len(record["unsupported_entries"]), 2)
        json.dumps(record)


class MetricSnapshotTest(unittest.TestCase):
    def test_capture_metric_snapshot_json_safe(self):
        snap = vd.capture_metric_snapshot()
        for key in ("mono_ns", "wall_unix_ns", "process_cpu_ns", "native_tid",
                    "faults", "threads", "fingerprint"):
            self.assertIn(key, snap)
        json.dumps(snap)

    def test_compute_metric_deltas_same_tid(self):
        before = {
            "mono_ns": 1_000_000,
            "process_cpu_ns": 1_000_000,
            "thread_cpu_ns": 1_000_000,
            "native_tid": 7,
            "faults": {"minor_faults": 10, "major_faults": 1},
            "io": {"rchar": 100, "read_bytes": 0},
            "rss_bytes": 1000,
        }
        after = {
            "mono_ns": 2_000_000,
            "process_cpu_ns": 2_500_000,
            "thread_cpu_ns": 3_000_000,
            "native_tid": 7,
            "faults": {"minor_faults": 25, "major_faults": 3},
            "io": {"rchar": 300, "read_bytes": 50},
            "rss_bytes": 1400,
        }
        deltas = vd.compute_metric_deltas(before, after, bytes_=1_000_000)
        self.assertEqual(deltas["wall_ms"], 1.0)
        self.assertEqual(deltas["process_cpu_ms"], 1.5)
        self.assertEqual(deltas["thread_cpu_ms"], 2.0)
        self.assertEqual(deltas["minor_faults"], 15)
        self.assertEqual(deltas["major_faults"], 2)
        self.assertEqual(deltas["io_deltas"]["rchar"], 200)
        self.assertEqual(deltas["rss_delta_bytes"], 400)
        self.assertEqual(deltas["bytes"], 1_000_000)
        self.assertEqual(deltas["effective_gb_per_s"], 1.0)

    def test_compute_metric_deltas_diff_tid(self):
        before = {"mono_ns": 1000, "thread_cpu_ns": 1000, "native_tid": 7,
                  "faults": {"minor_faults": 1}, "io": {}, "rss_bytes": 100}
        after = {"mono_ns": 2000, "thread_cpu_ns": 5000, "native_tid": 8,
                 "faults": {"minor_faults": 9}, "io": {}, "rss_bytes": 100}
        deltas = vd.compute_metric_deltas(before, after)
        self.assertIsNone(deltas["thread_cpu_ms"])
        self.assertIsNone(deltas["minor_faults"])
        self.assertIsNone(deltas["io_deltas"])


class BoundedRecordTest(unittest.TestCase):
    def test_bounded_record_truncates_ranges(self):
        record = {"ranges": list(range(2000)), "x": 1}
        safe = vd.bounded_record(record)
        self.assertEqual(len(safe["ranges"]), vd._MAX_RECORD_RANGES)
        self.assertEqual(safe["ranges_truncated"], 2000 - vd._MAX_RECORD_RANGES)
        json.dumps(safe)


def _evidence_snapshot(mono, wall, rss, tid=7):
    return {
        "mono_ns": mono,
        "wall_unix_ns": wall,
        "process_cpu_ns": mono,
        "thread_cpu_ns": mono,
        "native_tid": tid,
        "faults": {"major_faults": 0, "minor_faults": 0},
        "rss_bytes": rss,
        "smaps_rollup": {"Rss": rss, "RssAnon": rss // 2},
        "io": {"rchar": rss, "read_bytes": rss},
        "numa": {"nodes": {"N0": 1}, "pages_sampled": 1},
        "threads": {"torch_available": False, "torch_intraop_threads": None,
                    "torch_interop_threads": None},
        "native_thread_count": 4,
        "fingerprint": {"pid": "1", "python": "3.x"},
    }


class EvidenceRetentionTest(unittest.TestCase):
    def test_snapshot_evidence_retains_absolutes(self):
        before = _evidence_snapshot(1_000_000, 1_000_000, 1000)
        after = _evidence_snapshot(2_000_000, 2_000_000, 1400)
        ev = vd.snapshot_evidence(before, after)
        self.assertEqual(ev["before_rss_bytes"], 1000)
        self.assertEqual(ev["after_rss_bytes"], 1400)
        self.assertEqual(ev["before_smaps_rollup"]["Rss"], 1000)
        self.assertEqual(ev["after_smaps_rollup"]["Rss"], 1400)
        self.assertEqual(ev["before_io"]["rchar"], 1000)
        self.assertEqual(ev["after_io"]["rchar"], 1400)
        self.assertEqual(ev["before_numa"]["pages_sampled"], 1)
        self.assertEqual(ev["after_native_thread_count"], 4)
        self.assertEqual(ev["before_fingerprint"]["pid"], "1")
        self.assertEqual(ev["before_mono_ns"], 1_000_000)
        self.assertEqual(ev["after_wall_unix_ns"], 2_000_000)
        json.dumps(ev)

    def test_deltas_with_evidence_merges(self):
        before = _evidence_snapshot(1_000_000, 1_000_000, 1000)
        after = _evidence_snapshot(2_000_000, 2_000_000, 1400)
        rec = vd.deltas_with_evidence(before, after, bytes_=1_000_000)
        self.assertEqual(rec["wall_ms"], 1.0)
        self.assertEqual(rec["before_rss_bytes"], 1000)
        self.assertEqual(rec["after_rss_bytes"], 1400)
        json.dumps(rec)

    def test_stage_record_retains_evidence_and_fingerprint(self):
        before = _evidence_snapshot(1_000_000, 1_000_000, 1000)
        after = _evidence_snapshot(2_000_000, 2_000_000, 1400)
        rec = vd.build_stage_variance_record("models", "end", before, after)
        self.assertEqual(rec["stage"], "models")
        self.assertEqual(rec["fingerprint"]["pid"], "1")
        self.assertEqual(rec["before_rss_bytes"], 1000)
        self.assertEqual(rec["after_smaps_rollup"]["Rss"], 1400)
        self.assertEqual(rec["before_io"]["rchar"], 1000)
        self.assertEqual(rec["after_numa"]["pages_sampled"], 1)
        json.dumps(rec)

    def test_pretouch_record_retains_evidence(self):
        reg = _registry(StorageRange(address=4096, length=4096), total_bytes=4096)
        with patch.object(vd, "capture_metric_snapshot",
                          side_effect=[_evidence_snapshot(1_000_000, 1_000_000, 1000),
                                       _evidence_snapshot(2_000_000, 2_000_000, 1400)]):
            with patch.object(vd, "_default_page_reader", return_value=b"\x00" * 4096):
                record = vd.pretouch_unet_storage(reg)
        self.assertEqual(record["before_rss_bytes"], 1000)
        self.assertEqual(record["after_rss_bytes"], 1400)
        self.assertEqual(record["before_io"]["rchar"], 1000)
        self.assertEqual(record["after_native_thread_count"], 4)
        json.dumps(record)

    def test_sampler_variance_retains_evidence(self):
        trace = RuntimeTrace(request_id="r1")
        with patch.dict(os.environ, {_VAR_ENV: "1"}, clear=False):
            vd.emit_sampler_variance(
                trace,
                node_id="n1",
                node_class="Sampler",
                steps=10,
                before=_evidence_snapshot(1_000_000, 1_000_000, 1000),
                after=_evidence_snapshot(2_000_000, 2_000_000, 1400),
                sampling_duration_ms=2.5,
            )
        event = next(e for e in trace.events if e.name == "sampler_variance")
        self.assertEqual(event.metadata["before_rss_bytes"], 1000)
        self.assertEqual(event.metadata["after_rss_bytes"], 1400)
        self.assertEqual(event.metadata["before_smaps_rollup"]["Rss"], 1000)
        json.dumps(trace.to_dict())


class ActivationWaitTest(unittest.TestCase):
    def test_activation_join_wait_ms_from_trace(self):
        trace = RuntimeTrace(request_id="r1")
        trace.emit("unet_early_activation_graph_join_start", phase="execution")
        trace.emit("unet_early_activation_graph_join_end", phase="execution")
        wait = vd.activation_join_wait_ms(trace)
        self.assertIsInstance(wait, float)
        if wait is not None:
            self.assertGreaterEqual(wait, 0.0)

    def test_activation_join_wait_ms_none_when_absent(self):
        trace = RuntimeTrace(request_id="r1")
        self.assertIsNone(vd.activation_join_wait_ms(trace))
        self.assertIsNone(vd.activation_join_wait_ms(None))

    def test_activation_wait_early_join_preferred(self):
        trace = RuntimeTrace(request_id="r1")
        trace.emit("unet_early_activation_graph_join_start", phase="execution")
        trace.emit("unet_early_activation_graph_join_end", phase="execution")
        wait, source = vd.activation_wait(trace)
        self.assertIsInstance(wait, float)
        self.assertEqual(source, "early_activation_graph_join")

    def test_activation_wait_demand_to_first_forward(self):
        trace = RuntimeTrace(request_id="r1")
        trace.emit("unet_gpu_demand_start", phase="execution",
                   metadata={"request_id": "r1"})
        trace.emit("unet_first_cuda_op", phase="execution",
                   metadata={"event_semantics": "first_unet_forward_with_cuda_input",
                             "elapsed_ms": 5.0})
        wait, source = vd.activation_wait(trace)
        self.assertIsInstance(wait, float)
        self.assertEqual(source, "demand_to_first_forward")

    def test_activation_wait_first_cuda_op_elapsed_ms(self):
        # No demand event present, but unet_first_cuda_op metadata has elapsed_ms.
        trace = RuntimeTrace(request_id="r1")
        trace.emit("unet_first_cuda_op", phase="execution",
                   metadata={"elapsed_ms": 12.5})
        wait, source = vd.activation_wait(trace)
        self.assertEqual(wait, 12.5)
        self.assertEqual(source, "first_cuda_op_elapsed_ms")

    def test_activation_wait_unavailable_when_absent(self):
        self.assertEqual(vd.activation_wait(None), (None, "unavailable"))
        trace = RuntimeTrace(request_id="r1")
        self.assertEqual(vd.activation_wait(trace), (None, "unavailable"))

    def test_sampler_variance_includes_activation_wait_source(self):
        trace = RuntimeTrace(request_id="r1")
        trace.emit("unet_gpu_demand_start", phase="execution")
        trace.emit("unet_first_cuda_op", phase="execution",
                   metadata={"elapsed_ms": 4.0})
        with patch.dict(os.environ, {_VAR_ENV: "1"}, clear=False):
            vd.emit_sampler_variance(
                trace,
                node_id="n1",
                node_class="Sampler",
                steps=10,
                before=_evidence_snapshot(1_000_000, 1_000_000, 1000),
                after=_evidence_snapshot(2_000_000, 2_000_000, 1400),
                sampling_duration_ms=2.5,
            )
        event = next(e for e in trace.events if e.name == "sampler_variance")
        self.assertEqual(event.metadata["activation_wait_source"], "demand_to_first_forward")
        self.assertIn("activation_wait_ms", event.metadata)


class ReconciliationTest(unittest.TestCase):
    def test_reconciliation_complete(self):
        rec = vd.reconciliation_fields(10.0, {"page_hydration": 4.0, "transfer": 6.0})
        self.assertEqual(rec["loader_wall_ms"], 10.0)
        self.assertEqual(rec["substage_sum_ms"], 10.0)
        self.assertEqual(rec["residual_ms"], 0.0)
        self.assertEqual(rec["reconciliation_status"], "complete")

    def test_reconciliation_overlap_and_gap(self):
        self.assertEqual(
            vd.reconciliation_fields(10.0, {"a": 6.0, "b": 6.0})["reconciliation_status"],
            "overlap",
        )
        self.assertEqual(
            vd.reconciliation_fields(10.0, {"a": 1.0, "b": 2.0})["reconciliation_status"],
            "unmeasured_gap",
        )

    def test_reconciliation_incomplete_when_substage_missing(self):
        rec = vd.reconciliation_fields(10.0, {"a": 4.0, "b": None})
        self.assertEqual(rec["substage_sum_ms"], 4.0)
        self.assertEqual(rec["residual_ms"], None)
        self.assertEqual(rec["reconciliation_status"], "incomplete")

    def test_reconciliation_incomplete_when_total_missing(self):
        rec = vd.reconciliation_fields(None, {"a": 4.0, "b": 6.0})
        self.assertEqual(rec["reconciliation_status"], "incomplete")

    def test_timed_transfer_partition_labeled(self):
        before = _evidence_snapshot(1_000_000, 1_000_000, 1000)
        after = _evidence_snapshot(2_000_000, 2_000_000, 1400)
        rec = vd.timed_transfer_partition(before, after, bytes_=1_000_000,
                                          label="cpu_to_gpu_transfer")
        self.assertEqual(rec["stage"], "cpu_to_gpu_transfer")
        self.assertEqual(rec["wall_ms"], 1.0)
        self.assertEqual(rec["before_rss_bytes"], 1000)
        self.assertEqual(rec["after_rss_bytes"], 1400)
        json.dumps(rec)


class StageVarianceTest(unittest.TestCase):
    def test_emit_stage_variance_noop_when_gate_off(self):
        trace = RuntimeTrace(request_id="r1")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_VAR_ENV, None)
            with vd.variance_stage(trace, stage="models", phase="restore"):
                pass
        self.assertFalse(any(e.name.startswith("variance_") for e in trace.events))

    def test_emit_stage_variance_when_gate_on(self):
        trace = RuntimeTrace(request_id="r1")
        with patch.dict(os.environ, {_VAR_ENV: "1"}, clear=False):
            with vd.variance_stage(trace, stage="models", phase="restore"):
                pass
        names = {e.name for e in trace.events}
        self.assertIn("variance_models_end", names)


class CudaSyncTest(unittest.TestCase):
    def test_disabled_never_initializes(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_VAR_ENV, None)
            self.assertFalse(vd.cuda_sync_if_enabled())

    @unittest.skipUnless(_HAS_TORCH, "torch required")
    def test_enabled_calls_synchronize_when_cuda(self):
        with patch.dict(os.environ, {_VAR_ENV: "1"}, clear=False):
            with patch("torch.cuda.is_available", return_value=True):
                with patch("torch.cuda.synchronize") as sync:
                    self.assertTrue(vd.cuda_sync_if_enabled())
                    sync.assert_called_once()

    @unittest.skipUnless(_HAS_TORCH, "torch required")
    def test_enabled_no_cuda_returns_false(self):
        with patch.dict(os.environ, {_VAR_ENV: "1"}, clear=False):
            with patch("torch.cuda.is_available", return_value=False):
                self.assertFalse(vd.cuda_sync_if_enabled())


if __name__ == "__main__":
    unittest.main()
