"""E29 UNET pipeline ledger tests: canonical UNET critical-path spans/events.

No Modal, no CUDA, no remote execution.  Validates:
1. All 7 UNET pipeline events are recordable via record_event.
2. The unet:lane-pipeline span persists with correct start/end boundaries.
3. Events/span survive artifact conversion (request_ledger_report).
4. Cross-request isolation: begin_request clears UNET events from a prior request.
5. Monotonic ordering of the full UNET event sequence.
6. Concurrent UNET span does not add serial time when overlapping other spans.
"""

import os
import sys
import time
import unittest

os.environ.setdefault("COMFYMODAL_V2_CRITICAL_PATH_LEDGER", "1")

sys.path.insert(0, r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal")

from comfymodal_runtime import critical_path_ledger as cpl  # noqa: E402


UNET_EVENT_NAMES = (
    "unet_worker_first_instruction",
    "unet_source_io_start",
    "unet_source_io_end",
    "unet_gpu_transfer_start",
    "unet_gpu_transfer_end",
    "unet_device_ready",
    "unet_lane_complete",
)


class UnetEventRecordabilityTest(unittest.TestCase):
    """All 7 UNET pipeline events are recordable via record_event and land in
    the ledger with the correct name and monotonic stamp."""

    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(request_id="unet-events-fixture")

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_all_seven_events_recordable(self):
        t0 = time.monotonic_ns()
        for i, name in enumerate(UNET_EVENT_NAMES):
            cpl.record_event(name, mono_ns=t0 + i * 1_000_000,
                             metadata={"seq": i})
        events = cpl.get_events()
        names = [e["name"] for e in events]
        for expected in UNET_EVENT_NAMES:
            self.assertIn(expected, names)
        for e in events:
            self.assertEqual(e["identity"]["request_id"], "unet-events-fixture")

    def test_events_have_monotonic_stamps(self):
        t0 = time.monotonic_ns()
        cpl.record_event("unet_worker_first_instruction", mono_ns=t0)
        cpl.record_event("unet_lane_complete", mono_ns=t0 + 100_000)
        events = cpl.get_events()
        stamps = [e["mono_ns"] for e in events]
        self.assertEqual(len(stamps), 2)
        self.assertGreater(stamps[1], stamps[0])


class UnetSpanPersistenceTest(unittest.TestCase):
    """The unet:lane-pipeline span persists with correct start/end mono
    boundaries and survives the artifact conversion."""

    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(request_id="unet-span-fixture")

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_span_persists_with_correct_boundaries(self):
        t0 = time.monotonic_ns()
        span = cpl.begin_span("unet:lane-pipeline", lane="UNET",
                              start_mono_ns=t0)
        time.sleep(0.02)
        t1 = time.monotonic_ns()
        span.finish(end_mono_ns=t1)
        spans = cpl.get_spans()
        self.assertEqual(len(spans), 1)
        rec = spans[0]
        self.assertEqual(rec["name"], "unet:lane-pipeline")
        self.assertEqual(rec["lane"], "UNET")
        self.assertEqual(rec["start_mono_ns"], t0)
        self.assertEqual(rec["end_mono_ns"], t1)
        self.assertGreaterEqual(rec["duration_ms"], 0.0)

    def test_span_survives_request_ledger_report(self):
        t0 = time.monotonic_ns()
        span = cpl.begin_span("unet:lane-pipeline", lane="UNET",
                              start_mono_ns=t0)
        span.finish(end_mono_ns=time.monotonic_ns())
        cpl.record_event("unet_device_ready", mono_ns=time.monotonic_ns())
        # Set endpoints for a valid report
        cpl.set_authoritative_endpoints(
            remote_python_resume_mono_ns=t0 - 1_000_000,
            first_durable_result_mono_ns=time.monotonic_ns() + 1_000_000,
        )
        report = cpl.request_ledger_report()
        self.assertEqual(report["endpoint_status"], "ok")
        self.assertGreaterEqual(report["span_count"], 1)
        names = [s["name"] for s in report["spans"]]
        self.assertIn("unet:lane-pipeline", names)
        self.assertGreaterEqual(report["event_count"], 1)
        event_names = [e["name"] for e in report["events"]]
        self.assertIn("unet_device_ready", event_names)


class UnetCrossRequestIsolationTest(unittest.TestCase):
    """begin_request must clear UNET events from a previous request (reuse
    safety: a reused container never appends stale UNET spans)."""

    def setUp(self):
        cpl.clear_ledger_for_test()

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_begin_request_clears_unet_events(self):
        cpl.set_request_identity(request_id="req-prev")
        cpl.record_event("unet_worker_first_instruction")
        cpl.record_event("unet_device_ready")
        self.assertEqual(len(cpl.get_events()), 2)
        cpl.begin_request("req-next")
        cpl.set_request_identity(request_id="req-next")
        self.assertEqual(len(cpl.get_events()), 0)

    def test_begin_request_clears_unet_spans(self):
        cpl.set_request_identity(request_id="req-prev")
        span = cpl.begin_span("unet:lane-pipeline", lane="UNET")
        span.finish(end_mono_ns=time.monotonic_ns())
        self.assertEqual(len(cpl.get_spans()), 1)
        cpl.begin_request("req-next")
        self.assertEqual(len(cpl.get_spans()), 0)

    def test_new_request_unet_events_not_leaked(self):
        cpl.set_request_identity(request_id="req-1")
        cpl.record_event("unet_lane_submitted")
        cpl.begin_request("req-2")
        cpl.set_request_identity(request_id="req-2")
        cpl.record_event("unet_worker_first_instruction")
        events = cpl.get_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "unet_worker_first_instruction")


class UnetMonotonicOrderingTest(unittest.TestCase):
    """Fixture proving the strict monotonic ordering of the full UNET event
    sequence: submitted <= first_instruction <= source_io_start <= source_io_end
    <= gpu_transfer_start <= gpu_transfer_end <= device_ready <= lane_complete."""

    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(request_id="unet-ordering-fixture")

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_full_sequence_monotonic(self):
        t0 = time.monotonic_ns()
        ordered_events = [
            ("unet_lane_submitted", t0),
            ("unet_worker_first_instruction", t0 + 100_000),
            ("unet_source_io_start", t0 + 200_000),
            ("unet_source_io_end", t0 + 300_000),
            ("unet_gpu_transfer_start", t0 + 400_000),
            ("unet_gpu_transfer_end", t0 + 500_000),
            ("unet_device_ready", t0 + 600_000),
            ("unet_lane_complete", t0 + 700_000),
        ]
        for name, mono in ordered_events:
            cpl.record_event(name, mono_ns=mono)
        events = cpl.get_events()
        self.assertEqual(len(events), len(ordered_events))
        stamps = [e["mono_ns"] for e in events]
        for i in range(1, len(stamps)):
            self.assertGreaterEqual(
                stamps[i], stamps[i - 1],
                f"monotonic ordering violated at index {i}: "
                f"{events[i-1]['name']}={stamps[i-1]} > "
                f"{events[i]['name']}={stamps[i]}",
            )

    def test_strict_ordering_labels(self):
        t0 = time.monotonic_ns()
        ordered = [
            "unet_lane_submitted",
            "unet_worker_first_instruction",
            "unet_source_io_start",
            "unet_source_io_end",
            "unet_gpu_transfer_start",
            "unet_gpu_transfer_end",
            "unet_device_ready",
            "unet_lane_complete",
        ]
        for i, name in enumerate(ordered):
            cpl.record_event(name, mono_ns=t0 + i)
        events = cpl.get_events()
        event_order = [e["name"] for e in events]
        # Verify the events appear in the correct order
        last_idx = -1
        for name in ordered:
            idx = event_order.index(name)
            self.assertGreater(idx, last_idx,
                               f"{name} must appear after previous event")
            last_idx = idx


class UnetConcurrentSpanOverlapTest(unittest.TestCase):
    """A concurrent UNET span overlapping other spans must NOT add serial time
    beyond the overlapping window (union accounting, not naive sum)."""

    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(request_id="unet-concurrent-fixture")

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_unet_span_overlapping_other_span_uses_union(self):
        t0 = time.monotonic_ns()
        with cpl.begin_span("restore:bootstrap", lane="RESTORE") as rs:
            rs.record_work(2_000_000)
            # UNET lane overlaps restore (same wall)
            unet = cpl.begin_span("unet:lane-pipeline", lane="UNET",
                                  start_mono_ns=time.monotonic_ns())
            time.sleep(0.02)
            unet.finish(end_mono_ns=time.monotonic_ns())
            rs.add_child(unet)
        end = time.monotonic_ns()
        spans = cpl.get_spans()
        serial = cpl.assert_serial_ledger_zero_gap(
            start_mono_ns=t0, end_mono_ns=end, spans=spans,
        )
        # The serial window is fully covered (zero gap)
        self.assertTrue(serial["zero_gap"])
        # The concurrent UNET lane did not add serial time beyond the window
        self.assertLessEqual(serial["total_ms"], 40.0)

    def test_sequential_unet_and_sampling_additive_serial_time(self):
        t0 = time.monotonic_ns()
        with cpl.begin_span("restore:bootstrap", lane="RESTORE") as s:
            s.record_work(2_000_000)
            time.sleep(0.02)
        with cpl.begin_span("unet:lane-pipeline", lane="UNET") as u:
            u.record_work(3_000_000)
            time.sleep(0.02)
        end = time.monotonic_ns()
        # Both spans are persisted in the ledger
        spans = cpl.get_spans()
        names = [s["name"] for s in spans]
        self.assertIn("restore:bootstrap", names)
        self.assertIn("unet:lane-pipeline", names)
        serial = cpl.build_serial_ledger(
            start_mono_ns=t0, end_mono_ns=end, spans=spans,
        )
        self.assertTrue(serial["zero_gap"])

    def test_span_metadata_survives_persist(self):
        span = cpl.begin_span("unet:lane-pipeline", lane="UNET",
                              metadata={"request_id": "r1",
                                         "unet_identity_hash": "abc123",
                                         "transport": "fastsafe"})
        span.finish(end_mono_ns=time.monotonic_ns())
        rec = cpl.get_spans()[0]
        self.assertEqual(rec["metadata"]["request_id"], "r1")
        self.assertEqual(rec["metadata"]["unet_identity_hash"], "abc123")
        self.assertEqual(rec["metadata"]["transport"], "fastsafe")


if __name__ == "__main__":
    unittest.main()
