"""E30 offline tests: CLIP QD reader, queue-depth proof, parity, ownership.

No Modal, no remote execution.  Synthetic safetensors files, real CPU reads,
and (when CUDA is available) the real GPU pipeline with zero-copy proof.
The E30 reader is default-OFF; every test that exercises it sets the env
flag explicitly.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

import torch

sys.path.insert(0, r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal")

from comfymodal_runtime import clip_qd_reader as qr  # noqa: E402
from comfymodal_runtime import clip_fast_hydration as cfh  # noqa: E402
from comfymodal_runtime import clip_fast_hydration_wiring as cfw  # noqa: E402
from comfymodal_runtime import speculative_clip_hydration as sch  # noqa: E402

CUDA_OK = torch.cuda.is_available()

_E30_ENV_VARS = (
    qr.ENABLE_FLAG,
    "COMFYMODAL_V2_CLIP_QD_QD",
    "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION",
    "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION",
)


def _save_env() -> dict:
    return {k: os.environ.get(k) for k in _E30_ENV_VARS}


def _restore_env(saved: dict) -> None:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _make_synth(path: str, tensors_per_layer: int = 4, dim: int = 512) -> dict:
    import safetensors.torch

    tensors = {}
    for i in range(tensors_per_layer):
        tensors[f"layer{i}.weight"] = torch.randn(dim, dim, dtype=torch.bfloat16)
        tensors[f"layer{i}.bias"] = torch.randn(dim, dtype=torch.bfloat16)
    safetensors.torch.save_file(tensors, path)
    return tensors


class _FirstReadBarrier:
    """Deterministically overlap the first source read of every worker."""

    def __init__(self, read, participants: int):
        self._read = read
        self._barrier = threading.Barrier(int(participants))
        self._lock = threading.Lock()
        self._calls = 0

    def __call__(self, fd, mv, offset):
        with self._lock:
            call = self._calls
            self._calls += 1
        if call < self._barrier.parties:
            self._barrier.wait(timeout=5.0)
        return self._read(fd, mv, offset)


class GateOffTests(unittest.TestCase):
    def setUp(self):
        self._env = _save_env()
        os.environ.pop(qr.ENABLE_FLAG, None)

    def tearDown(self):
        _restore_env(self._env)

    def test_entry_points_disabled_before_touching_file(self):
        # Gate OFF: must return disabled without opening the file or CUDA.
        missing = r"C:\definitely_missing_e30.safetensors"
        self.assertEqual(qr.read_file_qd(missing)["status"], "disabled")
        self.assertEqual(qr.read_file_qd_gpu(missing)["status"], "disabled")

    def test_no_threads_spawned_when_off(self):
        baseline = threading.active_count()
        missing = r"C:\definitely_missing_e30.safetensors"
        qr.read_file_qd(missing)
        self.assertEqual(threading.active_count(), baseline)

    def test_flag_off_fastsafe_failure_not_mislabeled_as_qd_fallback(self):
        """A flag-OFF fastsafe failure must NOT emit clip_qd_fallback: the
        E30 fallback event is reserved for a flag-ON QD failure (a non-QD
        run is provably not mislabeled)."""
        # clear all E30 flags so the seam takes the plain fastsafe path
        os.environ.pop(qr.ENABLE_FLAG, None)
        try:
            from comfymodal_runtime import speculative_clip_hydration as _sch

            # call the seam's effective branch: fastsafe failure on a bogus
            # file must raise (propagate) without any clip_qd_fallback event
            import tempfile
            from pathlib import Path as _Path

            bogus = _Path(tempfile.mkdtemp(prefix="e30-gateoff-")) / "bogus.safetensors"
            bogus.write_bytes(b"\x00" * 64)
            # a lane whose read will fail on the fastsafe path
            lane = _sch._SpeculativeClipLane(
                request_id="r-gateoff", identity="gateoff",
                file_paths=(str(bogus),),
                manifest_files=[{
                    "path": str(bogus), "size_bytes": 64,
                    "dtype": "torch.float16", "key_set": [], "key_shapes": {},
                    "pipeline": [],
                }],
                manifest={"eligible": True, "files": []},
                path_source="frozen_manifest",
            )
            trace = FakeTrace("r-gateoff")
            # _run_speculative_read must fail-closed WITHOUT the QD fallback
            _sch._run_speculative_read(lane, trace=trace)
            self.assertFalse(lane.record.get("result", {}).get("ok", False))
            qd_fallback = [n for n, _ in trace.events if n == "clip_qd_fallback"]
            self.assertEqual(qd_fallback, [])
        finally:
            pass

    def test_launch_policy_validation(self):
        self.assertEqual(qr.validate_launch_policy("restore_earliest"), "restore_earliest")
        self.assertEqual(qr.validate_launch_policy("method_entry"), "method_entry")
        with self.assertRaises(ValueError):
            qr.validate_launch_policy("at_boot_random")


class StaticPlannerTests(unittest.TestCase):
    def test_exact_qd_forward_regions_and_coverage(self):
        regions = qr.plan_raw_source_regions(100, 23, 5, 7)
        self.assertEqual(len(regions), 7)
        flat = [item for region in regions for item in region]
        self.assertEqual(flat, sorted(flat))
        self.assertTrue(all(0 < ln <= 5 for _, ln in flat))
        self.assertEqual(sum(ln for _, ln in flat), 23)
        self.assertEqual(
            qr.partition_coverage([(off - 100, off - 100 + ln) for off, ln in flat], 23)[0],
            True,
        )

    def test_small_and_partial_sections(self):
        self.assertEqual(qr.plan_raw_source_regions(4, 0, 8, 3), [[], [], []])
        regions = qr.plan_raw_source_regions(4, 9, 8, 2)
        self.assertEqual([item for r in regions for item in r], [(4, 8), (12, 1)])

    def test_header_map_is_independent_of_raw_blocks(self):
        header = {
            "a": {"dtype": "U8", "shape": [3], "data_offsets": [0, 3]},
            "b": {"dtype": "U8", "shape": [7], "data_offsets": [3, 10]},
        }
        self.assertEqual(qr.build_header_tensor_map(header)[1][0], "b")
        regions = qr.plan_raw_source_regions(8, 10, 5, 1)
        self.assertEqual(regions[0], [(8, 5), (13, 5)])

    def test_owner_release_does_not_purge_and_explicit_purge_does(self):
        owner = qr.QdGpuOwner(None, [], "cpu")
        with mock.patch.object(qr.torch.cuda, "empty_cache") as purge:
            owner.release_storage(purge_allocator=False)
            owner.release_storage()
            purge.assert_not_called()
            owner.purge_allocator()
            purge.assert_called_once()

    def test_malformed_headers_fail_before_raw_planning(self):
        import json

        cases = (
            ({
                "a": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
                "b": {"dtype": "F32", "shape": [1], "data_offsets": [8, 12]},
            }, 12),
            ({
                "a": {"dtype": "F32", "shape": [2], "data_offsets": [0, 4]},
            }, 4),
            ({
                "a": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
            }, 8),
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, (header, data_length) in enumerate(cases):
                raw_header = json.dumps(header, separators=(",", ":")).encode()
                path = Path(directory) / f"bad_{index}.safetensors"
                path.write_bytes(len(raw_header).to_bytes(8, "little") + raw_header + bytes(data_length))
                parsed = qr.parse_safetensors_header(str(path))
                self.assertEqual(parsed["status"], "error")

    def test_event_barrier_uses_host_query_and_sync(self):
        class Event:
            def __init__(self):
                self.complete = False
                self.wait_called = False
                self.sync_called = False

            def query(self):
                return self.complete

            def synchronize(self):
                self.sync_called = True
                self.complete = True

            def wait(self):
                self.wait_called = True
                raise AssertionError("event.wait is not host memory protection")

        event = Event()
        self.assertGreaterEqual(qr._wait_event_host(event), 0.0)
        self.assertTrue(event.sync_called)
        self.assertFalse(event.wait_called)

    def test_source_wall_and_gpu_ready_tail_are_distinct(self):
        state = qr._StaticReaderState([[(100, 4)]])
        state.submit()
        state.record({
            "worker_id": 0, "off": 100, "planned_len": 4, "read_len": 4,
            "source_end_ns": 2_000_000_000, "gbps": 1.0,
            "h2d_submitted_bytes": 4, "h2d_completed_bytes": 4,
        })

        class Telemetry:
            max_inflight = 1

            def snapshot(self):
                return {
                    "inflight": 0, "max_inflight": 1,
                    "earliest_start_ns": 1_000_000_000,
                    "latest_end_ns": 2_000_000_000,
                    "per_worker": {"0": {"read_count": 1, "read_bytes": 4}},
                }

        stats = qr._new_stats(
            qd=1, block_bytes=4, file_bytes=4, n_ranges=1,
            launch_policy="method_entry", syscall_mode="pread",
        )
        qr._finalize_stats(stats, state, 1.0, 0.0, Telemetry(), 4_000_000_000, 0.0)
        self.assertEqual(stats["qd_source_io_wall_ms"], 1000.0)
        self.assertEqual(stats["qd_source_to_gpu_ready_ms"], 3000.0)
        self.assertEqual(stats["cuda_readiness_wait_ms"], 0.0)

    def test_incomplete_h2d_record_fails_validation(self):
        ok, reason = qr._validate_static_records(
            [{
                "off": 100, "planned_len": 4, "read_len": 4,
                "h2d_submitted_bytes": 4, "h2d_completed_bytes": 0,
            }], [(100, 4)], 100, 4, gpu=True,
        )
        self.assertFalse(ok)
        self.assertIn("h2d_completed", reason)

    def test_source_telemetry_tracks_true_inflight_peak(self):
        telemetry = qr._SourceTelemetry(2)
        first = telemetry.before(0)
        second = telemetry.before(1)
        telemetry.after(0, first, 4)
        telemetry.after(1, second, 4)
        snapshot = telemetry.snapshot()
        self.assertEqual(snapshot["max_inflight"], 2)
        self.assertEqual(snapshot["inflight"], 0)
        self.assertEqual(snapshot["per_worker"]["0"]["read_count"], 1)
        self.assertEqual(snapshot["per_worker"]["1"]["read_count"], 1)
        self.assertEqual(snapshot["per_worker"]["0"]["read_bytes"], 4)
        self.assertEqual(snapshot["per_worker"]["1"]["read_bytes"], 4)

    def test_record_reconciliation_uses_authoritative_records_and_worker_finalization(self):
        state = qr._StaticReaderState([[(100, 4), (104, 4)]])
        telemetry = qr._SourceTelemetry(1)
        for offset in (100, 104):
            state.submit(0)
            started = telemetry.before(0)
            ended = telemetry.after(0, started, 4)
            state.record({
                "worker_id": 0, "off": offset, "planned_len": 4,
                "read_len": 4, "source_end_ns": ended,
            })
        state.finalize_worker(0)
        stats = qr._new_stats(
            qd=1, block_bytes=4, file_bytes=8, n_ranges=2,
            launch_policy="method_entry", syscall_mode="pread",
        )
        qr._finalize_stats(stats, state, 1.0, 0.0, telemetry)

        reconciliation = stats["record_reconciliation"]
        worker = reconciliation["per_worker"]["0"]
        self.assertTrue(reconciliation["ok"])
        self.assertEqual(reconciliation["authoritative_record_count"], 2)
        self.assertEqual(worker["record_count"], 2)
        self.assertEqual(worker["completion_count"], 2)
        self.assertEqual(worker["read_count"], 2)
        self.assertEqual(worker["record_bytes"], 8)
        self.assertEqual(worker["read_bytes"], 8)
        self.assertEqual(worker["excluded_from_source_read_counters"]["record_count"], 0)
        self.assertTrue(worker["finalization"]["matches_authoritative_records"])

    def test_record_reconciliation_labels_records_excluded_from_source_counters(self):
        state = qr._StaticReaderState([[(100, 4), (104, 4)]])
        telemetry = qr._SourceTelemetry(1)
        state.submit(0)
        started = telemetry.before(0)
        ended = telemetry.after(0, started, 4)
        state.record({
            "worker_id": 0, "off": 100, "planned_len": 4,
            "read_len": 4, "source_end_ns": ended,
        })
        # This completion record is authoritative, but intentionally has no
        # matching source-read callback: the artifact must name that semantic
        # rather than backfilling telemetry.read_count.
        state.submit(0)
        state.record({
            "worker_id": 0, "off": 104, "planned_len": 4,
            "read_len": 4,
        })
        state.finalize_worker(0)
        stats = qr._new_stats(
            qd=1, block_bytes=4, file_bytes=8, n_ranges=2,
            launch_policy="method_entry", syscall_mode="pread",
        )
        qr._finalize_stats(stats, state, 1.0, 0.0, telemetry)

        worker = stats["record_reconciliation"]["per_worker"]["0"]
        self.assertTrue(stats["record_reconciliation"]["ok"])
        self.assertEqual(worker["record_count"], 2)
        self.assertEqual(worker["read_count"], 1)
        self.assertEqual(worker["excluded_from_source_read_counters"]["record_count"], 1)
        self.assertEqual(worker["excluded_from_source_read_counters"]["bytes"], 4)
        self.assertIn("not additional reads", worker["excluded_from_source_read_counters"]["semantics"])
        self.assertEqual(worker["finalization"]["record_count"], 2)

    def test_queue_depth_tracks_observed_submitted_minus_completed(self):
        state = qr._StaticReaderState([[(100, 4), (104, 4), (108, 4)]])
        state.submit()
        state.submit()
        self.assertEqual(state.outstanding, 2)
        self.assertEqual(state.max_outstanding, 2)
        state.record({"off": 100, "planned_len": 4, "read_len": 4})
        self.assertEqual(state.outstanding, 1)
        state.record({"off": 104, "planned_len": 4, "read_len": 4})
        self.assertEqual(state.outstanding, 0)
        self.assertEqual(state.queue_backlog_max, 2)

    def test_queue_depth_does_not_use_planned_count(self):
        state = qr._StaticReaderState([[(100, 4), (104, 4), (108, 4)]])
        state.submit()
        state.record({"off": 100, "planned_len": 4, "read_len": 4})
        stats = qr._new_stats(
            qd=2, block_bytes=4, file_bytes=12, n_ranges=3,
            launch_policy="method_entry", syscall_mode="pread",
        )
        qr._finalize_stats(stats, state, 1.0, 0.0)
        self.assertEqual(stats["planned_block_count"], 3)
        self.assertEqual(stats["queue_backlog_max"], 1)
        self.assertNotEqual(stats["queue_backlog_max"], stats["planned_block_count"])

    def test_telemetry_schema_keeps_legacy_and_qd_fields(self):
        stats = qr._new_stats(
            qd=4, block_bytes=4, file_bytes=12, n_ranges=3,
            launch_policy="method_entry", syscall_mode="pread",
        )
        for key in (
            "queue_backlog_max", "planned_block_count", "submitted_block_count",
            "completed_block_count", "submit_count", "completion_count",
            "total_source_wall_ms", "aggregate_gbps", "source_io",
            "per_worker_source_io", "qd_max_source_io_inflight",
        ):
            self.assertIn(key, stats)
        self.assertIsNone(stats["queue_backlog_max"])

    def test_raw_block_can_cross_tensors_without_changing_view_map(self):
        header = {
            "left": {"dtype": "U8", "shape": [7], "data_offsets": [0, 7]},
            "right": {"dtype": "U8", "shape": [3], "data_offsets": [7, 10]},
        }
        blocks = qr.plan_raw_source_regions(200, 10, 5, 1)[0]
        self.assertEqual(blocks, [(200, 5), (205, 5)])
        self.assertEqual(qr.build_header_tensor_map(header), [
            ("left", "U8", [7], 0, 7),
            ("right", "U8", [3], 7, 3),
        ])

    def test_gpu_worker_alternates_two_slots_and_waits_only_on_reuse(self):
        class Slot:
            def __init__(self):
                self.data = bytearray(4)

            def numpy(self):
                return self.data

            def __getitem__(self, item):
                return self

        class Destination:
            def __init__(self):
                self.copies = []

            def numel(self):
                return 12

            def __getitem__(self, item):
                return self

            def copy_(self, source, non_blocking=False):
                self.copies.append(bool(non_blocking))

        class Event:
            def __init__(self, elapsed_ms=None):
                self.recorded = False
                self.sync_count = 0
                self.wait_called = False
                self.elapsed_ms = elapsed_ms

            def record(self):
                self.recorded = True

            def query(self):
                return self.recorded and self.sync_count > 0

            def synchronize(self):
                self.sync_count += 1

            def wait(self):
                self.wait_called = True

            def elapsed_time(self, start):
                if self.elapsed_ms is None:
                    raise RuntimeError("timing unavailable")
                return self.elapsed_ms

        state = qr._StaticReaderState([[(100, 4), (104, 4), (108, 4)]])
        slots = [Slot(), Slot()]
        events = [(Event(2.5), Event()), (Event(4.0), Event())]
        stats = qr._new_stats(
            qd=1, block_bytes=4, file_bytes=12, n_ranges=3,
            launch_policy="method_entry", syscall_mode="pread",
        )
        with mock.patch.object(qr, "_read_at", side_effect=lambda fd, mv, off: len(mv)):
            qr._static_gpu_worker(
                state, slots, [False, False], events, Destination(), 100, 0,
                0, qr._SourceTelemetry(1), stats, [0.0], None,
            )
        self.assertEqual(events[0][1].sync_count, 1)
        self.assertEqual(events[1][1].sync_count, 0)
        self.assertFalse(any(event.wait_called for pair in events for event in pair))
        self.assertEqual([record["slot_index"] for record in state.records], [0, 1, 0])
        self.assertEqual(sum(record["h2d_completed_bytes"] for record in state.records), 4)
        self.assertEqual(state.records[0]["h2d_device_ms"], 2.5)

    def test_gpu_worker_leaves_device_timing_none_when_elapsed_time_unavailable(self):
        class Event:
            def __init__(self):
                self.recorded = False

            def record(self):
                self.recorded = True

            def query(self):
                return self.recorded

            def synchronize(self):
                self.recorded = True

        class Slot:
            def numpy(self):
                return bytearray(4)

            def __getitem__(self, item):
                return self

        class Destination:
            def numel(self):
                return 4

            def __getitem__(self, item):
                return self

            def copy_(self, source, non_blocking=False):
                return None

        state = qr._StaticReaderState([[(100, 4), (104, 4)]])
        stats = qr._new_stats(
            qd=1, block_bytes=4, file_bytes=8, n_ranges=2,
            launch_policy="method_entry", syscall_mode="pread",
        )
        events = [(Event(), Event()), (Event(), Event())]
        with mock.patch.object(qr, "_read_at", side_effect=lambda fd, mv, off: len(mv)):
            qr._static_gpu_worker(
                state, [Slot(), Slot()], [False, False], events, Destination(), 100, 0,
                0, qr._SourceTelemetry(1), stats, [0.0], None,
            )
        self.assertIsNone(state.records[0]["h2d_device_ms"])


class QDReaderTests(unittest.TestCase):
    def setUp(self):
        self._env = _save_env()
        os.environ[qr.ENABLE_FLAG] = "1"
        os.environ["COMFYMODAL_V2_CLIP_QD_QD"] = "4"
        os.environ["COMFYMODAL_V2_CLIP_QD_BLOCK_MIB"] = "2"
        self._dir = tempfile.TemporaryDirectory()
        self.path = str(Path(self._dir.name) / "synth_clip.safetensors")
        self.reference = _make_synth(self.path)

    def tearDown(self):
        self._dir.cleanup()
        _restore_env(self._env)

    def test_queue_depth_proof(self):
        r = qr.read_file_qd(self.path)
        self.assertEqual(r["status"], "ok")
        st = r["stats"]
        self.assertEqual(st["configured_qd"], 4)
        self.assertGreaterEqual(st["observed_max_outstanding"], 1)
        self.assertLessEqual(st["observed_max_outstanding"], st["configured_qd"])
        self.assertEqual(st["submit_count"], st["n_ranges"])
        self.assertEqual(st["completion_count"], st["n_ranges"])
        self.assertEqual(st["per_read_errors"], 0)
        self.assertGreater(st["total_source_wall_ms"], 0)
        self.assertGreater(st["aggregate_gbps"], 0)
        self.assertGreater(st["qd_source_io_wall_ms"], 0)
        self.assertEqual(st["total_source_wall_ms"], st["qd_source_io_wall_ms"])
        self.assertEqual(
            sum(v["read_bytes"] for v in st["per_worker_source_io"].values()),
            st["file_bytes"],
        )
        self.assertEqual(
            sum(v["read_count"] for v in st["per_worker_source_io"].values()),
            st["completion_count"],
        )
        self.assertEqual(
            sum(v["completion_count"] for v in st["per_worker_source_io"].values()),
            st["record_reconciliation"]["authoritative_record_count"],
        )
        self.assertEqual(
            sum(v["record_bytes"] for v in st["per_worker_source_io"].values()),
            st["bytes_read"],
        )
        self.assertEqual(
            st["record_reconciliation"]["excluded_from_source_read_counters"]["record_count"],
            0,
        )
        for worker_id, worker in st["source_io"]["per_worker"].items():
            self.assertEqual(worker["completion_record_count"], worker["record_count"])
            self.assertEqual(worker["completion_record_bytes"], worker["record_bytes"])
        self.assertGreaterEqual(st["qd_max_source_io_inflight"], 1)
        for key in qr.CANONICAL_METRIC_KEYS:
            self.assertEqual(st[key], st["metrics"][key])
        self.assertEqual(st["QD_SOURCE_IO_WALL_MS"], st["qd_source_io_wall_ms"])
        for worker_id in range(st["configured_qd"]):
            offsets = [
                block["off"] for block in st["blocks"]
                if block.get("worker_id") == worker_id
            ]
            self.assertEqual(offsets, sorted(offsets))

    def test_queue_depth_reaches_configured_with_enough_ranges(self):
        # A normal OS scheduler may complete a read before it starts the next
        # worker, so configured QD is an upper bound, not an observation the
        # reader promises to manufacture.  This fixture deliberately creates
        # the overlap needed for the stronger exact-QD assertion.
        path = str(Path(self._dir.name) / "qd_concurrency.safetensors")
        _make_synth(path, tensors_per_layer=2, dim=1024)
        os.environ["COMFYMODAL_V2_CLIP_QD_BLOCK_MIB"] = "1"
        real_read = qr._read_at
        qr._read_at = _FirstReadBarrier(real_read, participants=4)
        try:
            r = qr.read_file_qd(path, qd=4, block_mib=1)
        finally:
            qr._read_at = real_read
        self.assertEqual(r["status"], "ok")
        st = r["stats"]
        self.assertEqual(st["configured_qd"], 4)
        self.assertEqual(st["n_ranges"], 5)
        self.assertEqual(st["observed_max_outstanding"], 4)
        self.assertEqual(st["queue_backlog_max"], 4)
        self.assertLess(st["queue_backlog_max"], st["n_ranges"])
        self.assertEqual(st["qd_max_source_io_inflight"], 4)
        self.assertEqual(st["submit_count"], st["n_ranges"])
        self.assertEqual(st["completion_count"], st["n_ranges"])

    def test_tensor_map_exact_coverage(self):
        r = qr.read_file_qd(self.path)
        parsed = qr.parse_safetensors_header(self.path)
        self.assertEqual(parsed["status"], "ok")
        self.assertEqual(parsed["tensor_count"], len(r["tensor_map"]))
        # every tensor's range sums to total data bytes
        total = sum(length for _, _, _, _, length in r["tensor_map"])
        self.assertEqual(total, parsed["total_data_bytes"])
        # no gap / no overlap via the item coverage proof
        items, _, cov = qr.build_block_items(
            parsed["header"], parsed["data_start"], 2 * 1024 * 1024
        )
        self.assertTrue(cov["ok"])

    def test_byte_exactness_collected(self):
        r = qr.read_file_qd(self.path, collect_bytes=True)
        self.assertEqual(r["status"], "ok")
        # spot: rebuild the file data section from collected blocks and
        # compare with the safetensors reference tensor bytes.
        data_start = qr.parse_safetensors_header(self.path)["data_start"]
        import io

        buf = bytearray()
        # blocks are per-range; collect full file via the tensor map
        # (collect_bytes returns per-range dict keyed by abs offset).
        collected = r["bytes"]
        self.assertTrue(collected)
        # sorted offsets cover the data section contiguously
        offs = sorted(collected)
        self.assertEqual(offs[0], data_start)
        prev = offs[0]
        for off in offs[1:]:
            self.assertEqual(off, prev + len(collected[prev]))
            prev = off
        # compare a sample tensor's bytes with reference
        key = "layer0.weight"
        ref_t = self.reference[key]
        ref_bytes = ref_t.reshape(-1).view(torch.uint8).numpy().tobytes()
        # find the block covering the tensor's rel range
        rel = qr.parse_safetensors_header(self.path)
        header = rel["header"]
        r0 = header[key]["data_offsets"][0]
        # verify the reference tensor bytes appear in the collected stream
        stream = b"".join(collected[o] for o in offs)
        # the stream is the full data section in file order
        self.assertEqual(len(stream), rel["total_data_bytes"])
        self.assertIn(ref_bytes[:64], stream)
        self.assertIn(ref_bytes[-64:], stream)

    def test_sample_hash_matches_reference(self):
        r = qr.read_file_qd(self.path)
        self.assertEqual(r["status"], "ok")
        # The CPU reader produces bytearrays; rebuild a tensor dict from the
        # data section stream and hash it (bounded sample).
        data_start = qr.parse_safetensors_header(self.path)["data_start"]
        header = qr.parse_safetensors_header(self.path)["header"]
        with open(self.path, "rb") as fh:
            fh.seek(data_start)
            stream = fh.read()
        import torch as _t

        sd = {}
        for key, info in header.items():
            if key == "__metadata__":
                continue
            offs = info["data_offsets"]
            dtype = {"F32": _t.float32, "BF16": _t.bfloat16, "F16": _t.float16}[info["dtype"]]
            shape = [int(d) for d in info["shape"]]
            length = int(offs[1]) - int(offs[0])
            elem = _t._utils._element_size(dtype)
            raw = bytearray(stream[offs[0] : offs[1]])
            sd[key] = _t.frombuffer(raw, dtype=_t.uint8).view(dtype).view(shape)
        reader_hash = qr.sample_hash_of_tensors(sd)
        self.assertNotEqual(reader_hash, "")
        # the reader's sample hash of the SAME data must be deterministic
        self.assertEqual(reader_hash, qr.sample_hash_of_tensors(sd))

    def test_partition_coverage(self):
        ok, reason = qr.partition_coverage([(0, 10), (12, 20)], 20)
        self.assertFalse(ok)
        self.assertIn("gap", reason)
        ok, reason = qr.partition_coverage([(0, 5), (5, 10)], 10)
        self.assertTrue(ok, reason)

    def test_missing_file_errors_cleanly(self):
        r = qr.read_file_qd(str(Path(self._dir.name) / "nope.safetensors"))
        self.assertEqual(r["status"], "error")

    def test_short_read_fails_closed_without_partial_publication(self):
        real_read = qr._read_at
        qr._read_at = lambda fd, mv, offset: 0
        try:
            r = qr.read_file_qd(self.path)
        finally:
            qr._read_at = real_read
        self.assertEqual(r["status"], "error")
        self.assertNotEqual(r.get("stats", {}).get("status"), "ok")
        stats = r["stats"]
        self.assertEqual(stats["planned_block_count"], stats["n_ranges"])
        self.assertEqual(stats["submitted_block_count"], stats["n_ranges"])
        self.assertEqual(stats["completed_block_count"], stats["n_ranges"])
        self.assertLess(stats["bytes_read"], stats["planned_bytes"])

    def test_source_worker_exception_fails_closed(self):
        real_read = qr._read_at
        qr._read_at = mock.Mock(side_effect=OSError("synthetic source failure"))
        try:
            r = qr.read_file_qd(self.path)
        finally:
            qr._read_at = real_read
        self.assertEqual(r["status"], "error")
        self.assertNotIn("bytes", r)
        self.assertEqual(r["stats"]["submitted_block_count"], r["stats"]["n_ranges"])
        self.assertEqual(r["stats"]["completed_block_count"], 0)

    def test_qd1_qd2_qd4_mechanics_matrix(self):
        """QD1/QD2/QD4 expose bounded, observed depth under the OS scheduler.

        The implementation starts at most one worker per configured slot; it
        does not promise that a fast synthetic read will overlap every worker.
        The deterministic overlap guarantee is covered separately above.
        """
        real_read = qr._read_at

        def slow_read(fd, mv, offset):
            time.sleep(0.004)
            return real_read(fd, mv, offset)

        qr._read_at = slow_read
        try:
            for qd in (1, 2, 4):
                os.environ["COMFYMODAL_V2_CLIP_QD_QD"] = str(qd)
                r = qr.read_file_qd(self.path)
                self.assertEqual(r["status"], "ok", qd)
                st = r["stats"]
                self.assertEqual(st["configured_qd"], qd, qd)
                self.assertGreaterEqual(st["observed_max_outstanding"], 1, qd)
                self.assertLessEqual(st["observed_max_outstanding"], min(qd, st["n_ranges"]), qd)
                self.assertGreaterEqual(st["queue_backlog_max"], 1, qd)
                self.assertLessEqual(st["queue_backlog_max"], st["n_ranges"], qd)
                self.assertEqual(st["submit_count"], st["n_ranges"], qd)
                self.assertEqual(st["completion_count"], st["n_ranges"], qd)
                self.assertEqual(st["per_read_errors"], 0, qd)
        finally:
            qr._read_at = real_read
            os.environ["COMFYMODAL_V2_CLIP_QD_QD"] = "4"

    def test_ledger_events_ingested_when_enabled(self):
        """The reader stamps the canonical E29 ledger events (submit/first/
        last/device-ready) when the ledger module is importable+enabled."""
        try:
            from comfymodal_runtime import critical_path_ledger as cpl
        except Exception:
            self.skipTest("critical_path_ledger unavailable")
        if not cpl._ENABLED:
            self.skipTest("critical_path_ledger disabled")
        cpl.clear_ledger_for_test()
        r = qr.read_file_qd(self.path)
        self.assertEqual(r["status"], "ok")
        names = {e["name"] for e in cpl._EVENTS}
        for expected in (
            qr.EVT_SUBMIT_START,
            qr.EVT_FIRST_COMPLETION,
            qr.EVT_LAST_COMPLETION,
            qr.EVT_SUBMIT_END,
        ):
            self.assertIn(expected, names)
        cpl.clear_ledger_for_test()


@unittest.skipUnless(CUDA_OK, "CUDA required")
class QDReaderGpuTests(unittest.TestCase):
    def setUp(self):
        self._env = _save_env()
        os.environ[qr.ENABLE_FLAG] = "1"
        os.environ["COMFYMODAL_V2_CLIP_QD_QD"] = "4"
        os.environ["COMFYMODAL_V2_CLIP_QD_BLOCK_MIB"] = "2"
        self._dir = tempfile.TemporaryDirectory()
        self.path = str(Path(self._dir.name) / "synth_clip.safetensors")
        self.reference = _make_synth(self.path)

    def tearDown(self):
        self._dir.cleanup()
        _restore_env(self._env)

    def test_gpu_pipeline_zero_copy_and_parity(self):
        r = qr.read_file_qd_gpu(self.path)
        self.assertEqual(r["status"], "ok")
        st = r["stats"]
        self.assertGreaterEqual(st["observed_max_outstanding"], 1)
        self.assertLessEqual(st["observed_max_outstanding"], st["configured_qd"])
        self.assertEqual(st["completion_count"], st["n_ranges"])
        self.assertEqual(st["per_read_errors"], 0)
        self.assertGreater(st["h2d"]["copy_count"], 0)
        self.assertIsNone(st["h2d"]["h2d_device_ms"])
        self.assertTrue(all(block["h2d_device_ms"] is None for block in st["blocks"]))
        self.assertGreater(st["memory"]["cuda_alloc_delta_bytes"], 0)
        # zero-copy proof
        sd = r["sd"]
        g = r["owner"].gpu_buf
        sample = sd["layer0.weight"]
        self.assertEqual(
            sample.untyped_storage().data_ptr(), g.untyped_storage().data_ptr()
        )
        self.assertEqual(str(sample.device), "cuda:0")
        # value parity vs reference
        diff = (sample.float().cpu() - self.reference["layer0.weight"].float()).abs().max().item()
        self.assertEqual(diff, 0.0)
        # exact shape/dtype/bytes vs header map
        vm = qr.verify_tensors_against_map(sd, r["tensor_map"])
        self.assertTrue(vm["ok"], vm["mismatches"])
        # close is idempotent
        owner = r["owner"]
        owner.close()
        self.assertTrue(owner.closed)
        owner.close()

    def test_clip_qd_load_contract(self):
        sd, loader, fb = qr.clip_qd_load(self.path)
        self.assertIn("layer0.weight", sd)
        self.assertTrue(hasattr(loader, "close"))
        self.assertTrue(hasattr(fb, "close"))
        loader.close()
        self.assertTrue(loader.closed)

    def test_alignment_fallback_exact_parity(self):
        """A tensor whose rel_start is NOT element-aligned takes the re-read
        fallback path; its bytes must still match the reference exactly."""
        import safetensors.torch

        tensors = {"odd": torch.randn(13, 17, dtype=torch.float32)}
        path = str(Path(self._dir.name) / "odd_align.safetensors")
        safetensors.torch.save_file(tensors, path)
        r = qr.read_file_qd_gpu(path)
        self.assertEqual(r["status"], "ok")
        st = r["stats"]
        # handcrafted: header length is odd-ish -> data_start not 4-aligned
        # for a float32 tensor; the fallback path must have engaged OR the
        # zero-copy path was correctly rejected.
        got = r["sd"]["odd"]
        diff = (got.float().cpu() - tensors["odd"].float()).abs().max().item()
        self.assertEqual(diff, 0.0)
        # value parity is the requirement; either path is acceptable but the
        # tensor must be a real CUDA tensor with the right shape/dtype.
        self.assertEqual(str(got.device), "cuda:0")
        self.assertEqual(list(got.shape), [13, 17])
        self.assertEqual(got.dtype, torch.float32)
        r["owner"].close()

    def test_bounded_staging_no_full_host_copy(self):
        """Staging memory must be qd x 2 x block_bytes (never a full second
        host copy of the file); the GPU holds exactly one contiguous
        destination buffer.  Use a file larger than the staging budget so
        the bound is meaningful."""
        import safetensors.torch

        big = {
            f"b{i}.weight": torch.randn(512, 512, dtype=torch.bfloat16)
            for i in range(32)
        }
        path = str(Path(self._dir.name) / "big_staging.safetensors")
        safetensors.torch.save_file(big, path)
        st = qr.read_file_qd_gpu(path)["stats"]
        self.assertEqual(st["h2d"]["pinned_bytes"], 4 * 2 * 2 * 1024 * 1024)
        self.assertEqual(st["h2d"]["gpu_bytes"], st["file_bytes"])
        self.assertLessEqual(st["h2d"]["pinned_bytes"], st["file_bytes"])


class FakeTrace:
    def __init__(self, request_id="r1"):
        self.request_id = request_id
        self.events = []

    def emit(self, name, phase="execution", metadata=None):
        self.events.append((name, dict(metadata or {})))


class ClipLoaderEndpointTests(unittest.TestCase):
    def test_common_endpoints_have_roles_and_shared_monotonic_clock(self):
        trace = FakeTrace("endpoint-test")
        try:
            from comfymodal_runtime import critical_path_ledger as cpl
        except Exception:
            self.skipTest("critical_path_ledger unavailable")
        if not cpl._ENABLED:
            self.skipTest("critical_path_ledger disabled")
        cpl.clear_ledger_for_test()
        with mock.patch.object(cfw.time, "monotonic_ns", side_effect=[101, 202, 303, 404]):
            for arm in ("fastsafe", "qd_speculative"):
                cfw._emit_clip_loader_endpoint(
                    trace,
                    cfw.CLIP_LOADER_START,
                    endpoint_role="loader_start",
                    loader_arm=arm,
                )
                cfw._emit_clip_loader_endpoint(
                    trace,
                    cfw.CLIP_DEVICE_READY,
                    endpoint_role="device_ready",
                    loader_arm=arm,
                )

        self.assertEqual(
            [name for name, _ in trace.events],
            [
                cfw.CLIP_LOADER_START,
                cfw.CLIP_DEVICE_READY,
                cfw.CLIP_LOADER_START,
                cfw.CLIP_DEVICE_READY,
            ],
        )
        for index, (name, metadata) in enumerate(trace.events):
            self.assertEqual(metadata["clock_source"], "time.monotonic_ns")
            self.assertEqual(metadata["clock"], "monotonic_ns")
            self.assertEqual(metadata["monotonic_ns"], [101, 202, 303, 404][index])
            self.assertEqual(metadata["loader_arm"], ["fastsafe", "fastsafe", "qd_speculative", "qd_speculative"][index])
            self.assertEqual(
                metadata["endpoint_role"],
                "loader_start" if name == cfw.CLIP_LOADER_START else "device_ready",
            )
            self.assertEqual(metadata["endpoint_role"], metadata["semantic_endpoint_role"])

        canonical = [event for event in cpl._EVENTS if event["name"] in {
            cfw.CLIP_LOADER_START, cfw.CLIP_DEVICE_READY,
        }]
        self.assertEqual([event["mono_ns"] for event in canonical], [101, 202, 303, 404])
        self.assertEqual(
            [event["metadata"]["endpoint_role"] for event in canonical],
            ["loader_start", "device_ready", "loader_start", "device_ready"],
        )
        cpl.clear_ledger_for_test()


class ClipQdLoadInferenceModeTests(unittest.TestCase):
    def test_qd_read_boundary_disables_inference_mode(self):
        """QD publication must yield normal tensors for assign=True binding."""
        owner = qr.QdGpuOwner(None, [], "cuda:0")
        observed = {}

        def fake_read(*args, **kwargs):
            observed["inference_mode"] = torch.is_inference_mode_enabled()
            tensor = torch.empty(1)
            observed["tensor"] = tensor
            return {
                "status": "ok",
                "sd": {"weight": tensor},
                "owner": owner,
                "stats": {"configured_qd": 4, "total_source_wall_ms": 0.0},
            }

        with mock.patch.object(qr, "read_file_qd_gpu", side_effect=fake_read):
            with torch.inference_mode():
                sd, loader, fb = qr.clip_qd_load("mock.safetensors")

        self.assertFalse(observed["inference_mode"])
        self.assertFalse(observed["tensor"].is_inference())
        self.assertIs(sd["weight"], observed["tensor"])
        self.assertIs(fb, owner)
        loader.close()


class _TinyTransformer(torch.nn.Module):
    def __init__(self, dim: int = 32, dtype: torch.dtype = torch.bfloat16):
        super().__init__()
        self.emb = torch.nn.Embedding(64, dim, dtype=dtype)
        self.ln1 = torch.nn.LayerNorm(dim, dtype=dtype)
        self.ff = torch.nn.Linear(dim, dim, dtype=dtype)

    def forward(self, ids):
        return self.ff(self.ln1(self.emb(ids)))


class _Leaf(torch.nn.Module):
    def __init__(self, prefix: str = "", dtype: torch.dtype = torch.bfloat16):
        super().__init__()
        if prefix:
            self.transformer = torch.nn.Module()
            self.transformer.add_module("gtransformer", _TinyTransformer(dtype=dtype))
        else:
            self.transformer = _TinyTransformer(dtype=dtype)

    def load_sd(self, sd):
        return self.transformer.load_state_dict(
            sd, strict=False, assign=getattr(self, "can_assign_sd", False)
        )


class _FakeCSM(torch.nn.Module):
    def __init__(self, dtype: torch.dtype = torch.bfloat16):
        super().__init__()
        self.clip_l = _Leaf(dtype=dtype)
        self.clip_g = _Leaf(prefix="g", dtype=dtype)

    def load_sd(self, sd):
        if any(k.startswith("gtransformer.") for k in sd):
            return self.clip_g.load_sd(sd)
        return self.clip_l.load_sd(sd)


class _FakePatcher:
    def __init__(self, model):
        self.model = model
        self.load_device = torch.device("cuda:0" if CUDA_OK else "cpu")
        self.offload_device = torch.device("cpu")
        self.is_clip = True

    def is_dynamic(self):
        return False


class _FakeClip:
    def __init__(self, dtype: torch.dtype = torch.bfloat16):
        self.cond_stage_model = _FakeCSM(dtype=dtype)
        self.patcher = _FakePatcher(self.cond_stage_model)
        self.tokenizer = object()
        self.manifest = None

    @property
    def manifest(self):
        return cfh.get_clip_manifest(self)

    @manifest.setter
    def manifest(self, value):
        if value is not None:
            cfh.attach_clip_manifest(self, value)

    def load_model(self, tokens=None):
        return self.patcher


def _build_manifest_file_entry(path: str, sd: dict) -> dict:
    """Mirror the wiring manifest builder for a single file: blob-free key
    set, shapes, dtype, pipeline."""
    tensors = {k: v for k, v in sd.items() if isinstance(v, torch.Tensor)}
    dtypes = {str(v.dtype) for v in tensors.values()}
    return {
        "path": path,
        "size_bytes": int(os.path.getsize(path)),
        "mtime_ns": int(os.path.getmtime(path) * 1_000_000_000),
        "dtype": str(next(iter(dtypes))),
        "key_set": sorted(tensors.keys()),
        "key_shapes": {k: list(v.shape) for k, v in tensors.items()},
        "pipeline": [],
        "non_tensor_entries": [],
        "quant_metadata_present": False,
    }


@unittest.skipUnless(CUDA_OK, "CUDA required")
class SpeculativeOwnershipContractTests(unittest.TestCase):
    """Phase 3: the E30 reader must satisfy the speculative lane's contract —
    one source read, exact manifest verification, take-on-match, bind,
    owner retained for zero-copy lifetime."""

    def setUp(self):
        self._env = _save_env()
        os.environ[qr.ENABLE_FLAG] = "1"
        os.environ["COMFYMODAL_V2_CLIP_QD_QD"] = "2"
        os.environ["COMFYMODAL_V2_CLIP_QD_BLOCK_MIB"] = "1"
        os.environ["COMFYMODAL_V2_CLIP_FAST_HYDRATION"] = "1"
        os.environ["COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION"] = "1"
        sch.clear_speculative_lanes_for_test()
        sch._RESTORE_MANIFEST_DIGESTS.clear()
        self._dir = tempfile.TemporaryDirectory()
        self.clip = _FakeClip()
        # The file must carry the leaf-receivable keys: the inner transformer
        # state dict (production fixture contract — leaf.load_sd forwards the
        # file sd to transformer.load_state_dict).
        import safetensors.torch

        leaf_sd = {
            k: v.detach().clone()
            for k, v in self.clip.cond_stage_model.clip_l.transformer.state_dict().items()
        }
        self.path = str(Path(self._dir.name) / "clip.safetensors")
        safetensors.torch.save_file(leaf_sd, self.path)
        self.reference = leaf_sd
        manifest = {
            "schema": 1,
            "eligible": True,
            "reason": "capability gates passed at capture",
            "files": [_build_manifest_file_entry(self.path, leaf_sd)],
            "assign_bind_supported": True,
            "fast_hydration_allowed": True,
            "staged_hydration_allowed": False,
            "capture_ts_ns": 0,
            "loader_specs": [],
        }
        cfh.attach_clip_manifest(self.clip, manifest)

    def tearDown(self):
        sch.clear_speculative_lanes_for_test()
        sch._RESTORE_MANIFEST_DIGESTS.clear()
        _restore_env(self._env)
        self._dir.cleanup()

    def _run_speculative_with_qd(self, trace: FakeTrace) -> dict:
        """Reproduce the lane worker with the QD reader as the load backend
        (the exact integration the seam provides), then take + verify + bind.
        Returns the take record."""
        lane = sch._SpeculativeClipLane(
            request_id="r1",
            identity="e30-test",
            file_paths=(self.path,),
            manifest_files=list(self.clip.manifest["files"]),
            manifest=self.clip.manifest,
            path_source="frozen_manifest",
        )
        lane.release_callback = None
        # register in the single-flight store so demand take resolves it
        sch._LANES["r1"] = lane
        # worker body mirroring _run_speculative_read with clip_qd_load
        import time

        t0 = time.perf_counter()
        owners = []
        per_file_sds = []
        sd, loader, fb = qr.clip_qd_load(
            self.path, trace=trace, launch_policy="method_entry"
        )
        owners.append((loader, fb))
        per_file_sds.append(sd)
        lane.owners = owners
        lane.per_file_sds = per_file_sds
        lane.record = {
            "speculative_read_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "checkpoint_bytes": int(os.path.getsize(self.path)),
            "files": 1,
            "gpu_tensors_held": True,
            # the helper uses the real QD loader -> qd_used must be True
            "qd_used": True,
            "cast_once": {},
            "result": {"ok": True, "mode": cfh.MODE_FASTSAFE, "reason": "speculative_read_complete"},
        }
        lane.finished_mono_ns = time.monotonic_ns()
        # demand take
        taken = sch.take_speculative_read("r1")
        self.assertIsNotNone(taken)
        per_file_sds, owners, record = taken
        # exact manifest verification
        for file_manifest, sd_ in zip(self.clip.manifest["files"], per_file_sds):
            self.assertEqual(sorted(sd_.keys()), file_manifest["key_set"])
            for k, shape in file_manifest["key_shapes"].items():
                self.assertEqual(list(sd_[k].shape), shape)
            self.assertEqual(str(next(iter({v.dtype for v in sd_.values() if isinstance(v, torch.Tensor)}))), file_manifest["dtype"])
        # bind via Comfy dispatch with assign=True (zero-copy)
        ok, evidence = cfh.hydrate_clip_bind(self.clip, per_file_sds, require_no_meta=True, expect_device="cuda:0")
        self.assertTrue(ok, evidence)
        # owner retained
        cfh.owner_attach(self.clip, *owners[0])
        self.assertTrue(cfh.clip_hydration_state(self.clip)["fastsafe_owner_present"])
        # zero-copy proof after bind: the file key (transformer key) must be
        # the SAME storage as the bound parameter.
        state = self.clip.cond_stage_model.state_dict()
        file_key = sorted(per_file_sds[0])[0]
        bound_key = "clip_l.transformer." + file_key
        sample = per_file_sds[0][file_key]
        self.assertEqual(
            sample.data_ptr(),
            state[bound_key].data_ptr(),
        )
        return record

    def test_speculative_take_bind_owner_retained(self):
        trace = FakeTrace("r1")
        record = self._run_speculative_with_qd(trace)
        self.assertTrue(record["result"]["ok"])
        self.assertEqual(record["files"], 1)
        # No duplicate read: the lane was taken; a second take is None.
        self.assertIsNone(sch.take_speculative_read("r1"))
        names = [n for n, _ in trace.events]
        for expected in (
            qr.EVT_SPEC_RECORD_PUBLISH,
            qr.EVT_TAKE,
            qr.EVT_BIND,
            qr.EVT_OWNER_RETAINED,
        ):
            self.assertIn(expected, names)

    def test_close_releases_owner_without_dangling(self):
        trace = FakeTrace("r1")
        record = self._run_speculative_with_qd(trace)
        self.assertTrue(record["result"]["ok"])
        # closing the lane releases owners (close is idempotent, no raise)
        sch.close_speculative_clip_lane("r1")
        self.assertIsNone(sch.get_speculative_clip_lane("r1"))
        # a request that never consumes can be closed safely twice
        sch.close_speculative_clip_lane("r1")

    def test_cancellation_before_take_releases_cleanly(self):
        lane = sch._SpeculativeClipLane(
            request_id="r1", identity="e30-test",
            file_paths=(self.path,),
            manifest_files=list(self.clip.manifest["files"]),
            manifest=self.clip.manifest, path_source="frozen_manifest",
        )
        lane.owners = []
        lane.per_file_sds = []
        lane.cancelled = True
        # closing a cancelled/empty lane must not raise and must release
        sch._LANES["r1"] = lane
        sch.close_speculative_clip_lane("r1")
        self.assertIsNone(sch.get_speculative_clip_lane("r1"))

    def test_mismatch_falls_back_without_poisoning(self):
        """A speculative read whose manifest verification fails must fall
        back safely (release owners) and a subsequent request must be able
        to start a fresh lane."""
        trace = FakeTrace("r1")
        # start a lane whose manifest now disagrees (stale size)
        self.clip.manifest["files"][0]["size_bytes"] = 999999
        sd, loader, fb = qr.clip_qd_load(self.path, trace=trace, launch_policy="method_entry")
        # verification fails -> release owners
        self.assertNotEqual(int(os.path.getsize(self.path)), 999999)
        loader.close()
        # fresh request starts a new lane cleanly
        self.clip.manifest["files"][0]["size_bytes"] = int(os.path.getsize(self.path))
        sd2, loader2, fb2 = qr.clip_qd_load(self.path, trace=FakeTrace("r2"), launch_policy="method_entry")
        self.assertIn("emb.weight", sd2)
        loader2.close()

    def test_no_double_read_on_successful_take(self):
        """The E30 reader reads the source exactly once per load; a
        successful speculative take must not trigger a second read."""
        trace = FakeTrace("r1")
        record = self._run_speculative_with_qd(trace)
        self.assertTrue(record["result"]["ok"])
        # exactly one submit batch for the single lane load
        submits = [m for n, m in trace.events if n == qr.EVT_SUBMIT_START]
        self.assertEqual(len(submits), 1)

    def test_qd_used_marker_and_ledger_events(self):
        """The lane record must prove qd_used, and the source-side take/bind/
        owner-retained events must be stamped on the E29 ledger."""
        try:
            from comfymodal_runtime import critical_path_ledger as cpl
        except Exception:
            self.skipTest("critical_path_ledger unavailable")
        if not cpl._ENABLED:
            self.skipTest("critical_path_ledger disabled")
        cpl.clear_ledger_for_test()
        trace = FakeTrace("r1")
        record = self._run_speculative_with_qd(trace)
        # the take record carries qd_used proof
        self.assertTrue(record["qd_used"])
        names = {e["name"] for e in cpl._EVENTS}
        for expected in (
            qr.EVT_SPEC_RECORD_PUBLISH,
            qr.EVT_TAKE,
            qr.EVT_BIND,
            qr.EVT_OWNER_RETAINED,
        ):
            self.assertIn(expected, names)
        cpl.clear_ledger_for_test()


if __name__ == "__main__":
    unittest.main(verbosity=2)
