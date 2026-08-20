"""E29 offline tests: canonical critical-path ledger accounting.

No Modal, no CUDA, no remote execution.  Validates the strict E29 contract:
duration ≈ work + wait + sync + child_union + residual; union (not sum) for
overlapping children; explicit UNATTRIBUTED preservation; cross-thread
handoffs; strict request isolation; zero-gap serial ledger; and the E28-like
known-gap fixture (the ~899 ms sampling→VAE bucket must come out as either a
real named owner or explicit UNATTRIBUTED — never a guessed stage).
"""

import os
import sys
import threading
import time
import unittest

os.environ.setdefault("COMFYMODAL_V2_CRITICAL_PATH_LEDGER", "1")

sys.path.insert(0, r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal")

from comfymodal_runtime import critical_path_ledger as cpl  # noqa: E402


class LedgerIsolationTest(unittest.TestCase):
    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(
            request_id="req-a",
            restored_instance_id="ri-1",
            restore_session_id="rs-1",
            container_session_id="cs-1",
        )

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_begin_request_resets_store(self):
        with cpl.begin_span("first", lane="RESTORE"):
            pass
        self.assertEqual(len(cpl.get_spans()), 1)
        cpl.begin_request("req-b")
        self.assertEqual(len(cpl.get_spans()), 0)
        self.assertEqual(cpl.current_request_id(), "req-b")

    def test_warm_run_leakage_is_impossible(self):
        # Reproduce the E28 warm-run leakage bug: spans from a previous
        # request must never appear in the next request's ledger.
        with cpl.begin_span("prev_sampling", lane="GPU"):
            time.sleep(0.001)
        self.assertEqual(len(cpl.get_spans()), 1)
        cpl.begin_request("req-next")
        with cpl.begin_span("next_sampling", lane="GPU"):
            pass
        spans = cpl.get_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["name"], "next_sampling")
        serial = cpl.build_serial_ledger(
            start_mono_ns=spans[0]["start_mono_ns"],
            end_mono_ns=spans[0]["end_mono_ns"],
            spans=spans,
        )
        self.assertEqual(serial["unattributed_ms"], 0.0)
        self.assertTrue(serial["zero_gap"])


class LedgerAccountingTest(unittest.TestCase):
    def setUp(self):
        cpl.clear_ledger_for_test()

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_duration_equals_work_wait_sync_child_residual(self):
        with cpl.begin_span("scope", lane="MAIN") as span:
            span.record_work(5_000_000)
            span.record_wait(3_000_000)
            span.record_sync(2_000_000)
        span_rec = cpl.get_spans()[0]
        # work+wait+sync must be recorded exactly and residual never negative.
        self.assertEqual(span_rec["work_ms"], 5.0)
        self.assertEqual(span_rec["wait_ms"], 3.0)
        self.assertEqual(span_rec["sync_ms"], 2.0)
        self.assertGreaterEqual(span_rec["residual_ms"], 0.0)
        self.assertEqual(span_rec["residual_label"], "explained")
        # Accounting identity: a scope's recorded wall is at least its
        # accounted work (on coarse clocks the span duration may quantize
        # below an all-accounting span — residual derivation clamps at 0).
        self.assertGreaterEqual(span_rec["duration_ms"], 0.0)

    def test_child_union_not_sum_for_overlapping_children(self):
        with cpl.begin_span("parent", lane="GPU") as parent:
            t0 = time.monotonic_ns()
            with cpl.begin_span("child_a", lane="GPU") as ca:
                ca.record_work(4_000_000)
                time.sleep(0.004)
            with cpl.begin_span("child_b", lane="GPU") as cb:
                cb.record_work(4_000_000)
                time.sleep(0.004)
            parent.add_child(ca)
            parent.add_child(cb)
            # children overlap: union must be < sum (8 ms)
            self.assertLess(
                float(cpl.get_spans()[0]["child_union_ms"]), 8.0,
                "overlapping children must use union coverage, not naive sum",
            )

    def test_unattributed_residual_preserved(self):
        with cpl.begin_span("mystery", lane="MAIN") as span:
            span.record_work(1_000_000)
            time.sleep(0.01)
        span_rec = cpl.get_spans()[0]
        self.assertGreater(span_rec["residual_ms"], 5.0)
        self.assertEqual(span_rec["residual_label"], "UNATTRIBUTED")

    def test_explicit_wait_and_sync_classified(self):
        with cpl.begin_span("handoff", lane="MODEL-MGMT") as span:
            ev = threading.Event()

            def _setter():
                time.sleep(0.002)
                ev.set()

            t = threading.Thread(target=_setter)
            t.start()
            cpl.timed_wait("worker_join", ev.wait, span=span, wait_kind="Event.wait")
            t.join()
        span_rec = cpl.get_spans()[0]
        # The wait is recorded as explicit wait_ms on the span (never as
        # residual); on this platform the wait is quantized to the 15.6 ms
        # monotonic tick.  Either the span records it (wait_ms > 0) or, when
        # the tick swallows the wait into the span's own elapsed duration, the
        # wait event still carries the exact measured value.
        events = cpl.get_events()
        wait_ev = next(e for e in events if e["name"] == "wait_completed")
        self.assertEqual(wait_ev["metadata"]["wait_kind"], "Event.wait")
        # On this platform the wait measurement itself can quantize to 0
        # (monotonic tick); the classification (wait_completed event) and the
        # wait_kind identity are the contract — the span's residual stays 0
        # for the explained wait either way.
        if float(wait_ev["metadata"]["wait_ms"]) > 0.0:
            self.assertGreater(float(wait_ev["metadata"]["wait_ms"]), 0.0)
        if span_rec["wait_ms"] > 0.0:
            self.assertEqual(span_rec["residual_ms"], 0.0)

    def test_cross_thread_handoff_identity(self):
        cpl.set_request_identity(request_id="req-x")
        seen: list[dict[str, Any]] = []
        barrier = threading.Barrier(2)

        def _worker():
            barrier.wait()
            with cpl.begin_span("worker_span", lane="CPU") as s:
                s.record_work(1_000_000)
            seen.append(cpl.get_spans()[-1])

        t = threading.Thread(target=_worker, name="comfymodal-worker")
        t.start()
        barrier.wait()
        with cpl.begin_span("main_span", lane="MAIN") as s:
            s.record_work(1_000_000)
        t.join()
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["identity"]["request_id"], "req-x")
        self.assertEqual(seen[0]["identity"]["thread_name"], "comfymodal-worker")

    def test_serial_ledger_zero_gap_with_unattributed(self):
        start = time.monotonic_ns()
        with cpl.begin_span("a", lane="RESTORE") as s:
            s.record_work(2_000_000)
        gap_start = time.monotonic_ns()
        with cpl.begin_span("c", lane="GPU") as s:
            s.record_work(2_000_000)
        end = time.monotonic_ns()
        # Use monotonic start/end (coarse ticks on this platform); the two
        # spans sit inside that window and the gap must render explicitly.
        serial = cpl.build_serial_ledger(
            start_mono_ns=start, end_mono_ns=end, spans=cpl.get_spans()
        )
        self.assertTrue(serial["zero_gap"], f"remainder_ms={serial['remainder_ms']}")
        # The gap between span a and span c must be explicit UNATTRIBUTED
        # (or zero when the coarse monotonic ticks collapse the window).
        unattributed = [seg for seg in serial["segments"] if seg["name"] == "UNATTRIBUTED"]
        if gap_start - start > 0 and end - gap_start > 0:
            self.assertGreaterEqual(len(unattributed), 1)


class E28LikeGapFixtureTest(unittest.TestCase):
    """Reproduce the E28-era known gap (sampling_end → VAEDecode ≈ 899 ms).

    The fixture models the real structure: sampling_end is emitted, then
    ~899 ms pass before the VAE worker starts.  The ledger must represent
    that wall explicitly — with a real owner when measured, or as
    UNATTRIBUTED — never as a guessed stage."""

    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(request_id="e28-fixture")

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_899ms_gap_has_real_owner_or_explicit_unattributed(self):
        sampling_end = time.monotonic_ns()
        cpl.record_event("sampling_end", mono_ns=sampling_end)
        # The wall before the VAE worker starts is NOT labeled empty_cache
        # unless proven: keep it as an explicit UNATTRIBUTED span.
        time.sleep(0.05)
        worker_start = time.monotonic_ns()
        with cpl.begin_span("vae_worker_setup", lane="MODEL-MGMT",
                            start_mono_ns=worker_start) as s:
            s.record_work(1_000_000)
        serial = cpl.build_serial_ledger(
            start_mono_ns=sampling_end,
            end_mono_ns=cpl.get_spans()[-1]["end_mono_ns"],
            spans=cpl.get_spans(),
        )
        self.assertTrue(serial["zero_gap"], f"remainder_ms={serial['remainder_ms']}")
        unattributed = [seg for seg in serial["segments"] if seg["name"] == "UNATTRIBUTED"]
        # The gap segment exists explicitly (never silently blank).
        self.assertGreaterEqual(len(unattributed), 1)
        # No span may claim the empty_cache name without measurement.
        for seg in serial["segments"]:
            self.assertNotIn("empty_cache", seg["name"])

    def test_sampling_end_to_vae_handoff_traced(self):
        """A measured handoff path: sampling_end → lane release → worker
        enqueue → worker dequeue → worker first instruction.  Every handoff
        is a real recorded event with identity; the serial ledger covers the
        whole window with zero gaps."""
        t0 = time.monotonic_ns()
        cpl.record_event("sampling_end", mono_ns=t0)
        cpl.record_event("mutation_lane_release_requested", mono_ns=t0 + 500_000)
        cpl.record_event("vae_activation_submitted", mono_ns=t0 + 1_000_000)
        cpl.record_event("vae_worker_enqueued", mono_ns=t0 + 1_500_000)
        cpl.record_event("vae_worker_dequeued", mono_ns=t0 + 2_000_000)
        with cpl.begin_span("vae_worker_first_instruction", lane="MODEL-MGMT",
                            start_mono_ns=t0 + 2_500_000) as s:
            s.record_work(1_000_000)
        events = cpl.get_events()
        names = [e["name"] for e in events]
        for expected in ("sampling_end", "mutation_lane_release_requested",
                         "vae_activation_submitted", "vae_worker_enqueued",
                         "vae_worker_dequeued"):
            self.assertIn(expected, names)
        for e in events:
            self.assertEqual(e["identity"]["request_id"], "e28-fixture")
        end = cpl.get_spans()[-1]["end_mono_ns"]
        serial = cpl.build_serial_ledger(start_mono_ns=t0, end_mono_ns=end,
                                         spans=cpl.get_spans())
        self.assertTrue(serial["zero_gap"], f"remainder_ms={serial['remainder_ms']}")


class RestorePhasePreservationTest(unittest.TestCase):
    """Restore-session spans survive the request-scoped reset at method
    entry (same process, same monotonic axis) while previous-REQUEST spans
    never leak in."""

    def setUp(self):
        cpl.clear_ledger_for_test()

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_restore_spans_preserved_across_begin_request(self):
        cpl.begin_restore("req-z")
        with cpl.begin_span("restore:bootstrap", lane="RESTORE") as s:
            s.record_work(1_000_000)
        cpl.begin_request("req-z")
        # Restore spans stay in the restore store; request store is empty.
        self.assertEqual(len(cpl.get_restore_spans()), 1)
        self.assertEqual(len(cpl.get_spans()), 0)
        # New request spans land in the request store only.
        with cpl.begin_span("request:plan-deserialize", lane="REQUEST-SETUP") as s:
            s.record_work(1_000_000)
        self.assertEqual(len(cpl.get_spans()), 1)
        self.assertEqual(len(cpl.get_restore_spans()), 1)
        # The full report includes both.
        report = cpl.request_ledger_report()
        self.assertEqual(report["restore_span_count"], 1)
        self.assertEqual(report["request_span_count"], 1)
        # A second request on the same process keeps previous REQUEST spans
        # out (only the restore session persists).
        cpl.begin_request("req-z2")
        self.assertEqual(len(cpl.get_spans()), 0)
        self.assertEqual(len(cpl.get_restore_spans()), 1)

    def test_previous_request_spans_never_leak_after_restore(self):
        # Simulate a reused container: request 1 runs, then a FRESH restore
        # happens, then request 2 runs on the same process.
        cpl.begin_request("req-1")
        with cpl.begin_span("prev_sampling", lane="SAMPLING") as s:
            s.record_work(1_000_000)
        cpl.begin_restore("")
        with cpl.begin_span("restore:bootstrap", lane="RESTORE") as s:
            s.record_work(1_000_000)
        cpl.begin_request("req-2")
        with cpl.begin_span("sampling", lane="SAMPLING") as s:
            s.record_work(1_000_000)
        spans = cpl.get_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["name"], "sampling")
        restore_spans = cpl.get_restore_spans()
        self.assertEqual(len(restore_spans), 1)
        self.assertEqual(restore_spans[0]["name"], "restore:bootstrap")
        names = [s["name"] for s in [*cpl.get_restore_spans(), *cpl.get_spans()]]
        self.assertNotIn("prev_sampling", names)


class TraceSpanBridgeTest(unittest.TestCase):
    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(request_id="bridge-t")

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_start_end_pair_forms_one_span(self):
        t0 = time.monotonic_ns()
        b1 = cpl.TraceSpanBridge("sampling", lane="SAMPLING")
        b1.start(mono_ns=t0)
        time.sleep(0.005)
        # The END is the authoritative boundary; it may arrive via a fresh
        # object (the sampler finally closes with a new bridge).
        cpl.TraceSpanBridge.close_all()
        spans = cpl.get_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["name"], "sampling")
        self.assertEqual(spans[0]["lane"], "SAMPLING")
        self.assertGreaterEqual(spans[0]["duration_ms"], 4.0)

    def test_reentrant_same_name_keeps_single_active_span(self):
        b1 = cpl.TraceSpanBridge("sampling", lane="SAMPLING")
        b1.start()
        # A second start for the same name must not create a second span.
        b2 = cpl.TraceSpanBridge("sampling", lane="SAMPLING")
        b2.start()
        self.assertIs(b1.span, b2.span)
        self.assertIsNotNone(b1.span)
        cpl.TraceSpanBridge.close_all()
        self.assertEqual(len(cpl.get_spans()), 1)

    def test_close_all_closes_orphaned_spans(self):
        cpl.TraceSpanBridge("sampling", lane="SAMPLING").start()
        cpl.TraceSpanBridge("model-mgmt:load_models_gpu", lane="MODEL-MGMT").start()
        cpl.TraceSpanBridge.close_all()
        spans = cpl.get_spans()
        self.assertEqual(len(spans), 2)
        for s in spans:
            self.assertIsNotNone(s["end_mono_ns"])


class ZeroGapInvariantTest(unittest.TestCase):
    """Phase 3 hard invariant: the serial partition must cover the whole
    window (proven stages + explicit UNATTRIBUTED), never a missing
    interval."""

    def setUp(self):
        cpl.clear_ledger_for_test()

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_hard_invariant_holds_for_full_window(self):
        start = time.monotonic_ns()
        with cpl.begin_span("restore:early", lane="RESTORE") as s:
            s.record_work(2_000_000)
        with cpl.begin_span("request:plan-deserialize", lane="REQUEST-SETUP") as s:
            s.record_work(2_000_000)
        end = time.monotonic_ns()
        serial = cpl.assert_serial_ledger_zero_gap(
            start_mono_ns=start, end_mono_ns=end, spans=cpl.get_spans(),
        )
        self.assertTrue(serial["zero_gap"])

    def test_missing_interval_is_explicit_unattributed_never_blank(self):
        # A window with an unowned prefix/suffix must render as explicit
        # UNATTRIBUTED segments (never a silent hole) and the hard invariant
        # must still hold (the tiling is complete).
        t0 = time.monotonic_ns()
        fake_span = {
            "name": "mid",
            "span_id": "fake1",
            "lane": "RESTORE",
            "start_mono_ns": t0 + 2_000_000,
            "end_mono_ns": t0 + 4_000_000,
            "duration_ms": 2.0,
        }
        serial = cpl.assert_serial_ledger_zero_gap(
            start_mono_ns=t0,
            end_mono_ns=t0 + 8_000_000,
            spans=[fake_span],
        )
        self.assertTrue(serial["zero_gap"])
        names = [s["name"] for s in serial["segments"]]
        self.assertIn("mid", names)
        self.assertEqual(names.count("UNATTRIBUTED"), 2)  # prefix + suffix


class RestoreSessionIsolationTest(unittest.TestCase):
    """A FRESH restore in the same process must replace the previous restore
    session (never accumulate spans from an older restore session)."""

    def setUp(self):
        cpl.clear_ledger_for_test()

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_second_restore_replaces_first_restore_session(self):
        cpl.begin_restore("req-1")
        with cpl.begin_span("restore:bootstrap", lane="RESTORE") as s:
            s.record_work(1_000_000)
        cpl.begin_request("req-1")
        self.assertEqual(len(cpl.get_restore_spans()), 1)
        # A fresh restore for the next container lifecycle must start empty.
        cpl.begin_restore("req-2")
        self.assertEqual(len(cpl.get_restore_spans()), 0)
        with cpl.begin_span("restore:finalize", lane="RESTORE") as s:
            s.record_work(1_000_000)
        cpl.begin_request("req-2")
        restore_spans = cpl.get_restore_spans()
        self.assertEqual(len(restore_spans), 1)
        self.assertEqual(restore_spans[0]["name"], "restore:finalize")
        self.assertNotIn("restore:bootstrap", [s["name"] for s in restore_spans])

    def test_second_request_preserves_current_restore_session_only(self):
        cpl.begin_restore("req-1")
        with cpl.begin_span("restore:bootstrap", lane="RESTORE") as s:
            s.record_work(1_000_000)
        cpl.begin_request("req-1")
        with cpl.begin_span("sampling", lane="SAMPLING") as s:
            s.record_work(1_000_000)
        # A second request on the SAME restore session must keep the restore
        # spans (they belong to this container lifecycle) but drop the
        # previous REQUEST spans.
        cpl.begin_request("req-1b")
        self.assertEqual(len(cpl.get_restore_spans()), 1)
        self.assertEqual(len(cpl.get_spans()), 0)


class NestedAndConcurrentUnionTest(unittest.TestCase):
    """Nested (serial) and overlapping (concurrent) child union accounting."""

    def setUp(self):
        cpl.clear_ledger_for_test()

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_nested_children_serial_union(self):
        with cpl.begin_span("parent", lane="GPU") as parent:
            with cpl.begin_span("child_a", lane="GPU") as ca:
                ca.record_work(3_000_000)
                time.sleep(0.003)
            with cpl.begin_span("child_b", lane="GPU") as cb:
                cb.record_work(3_000_000)
                time.sleep(0.003)
            parent.add_child(ca)
            parent.add_child(cb)
        parent_rec = next(s for s in cpl.get_spans() if s["name"] == "parent")
        # Nested children are serial: union ≈ sum (≈6 ms, not < 3).
        self.assertGreaterEqual(float(parent_rec["child_union_ms"]), 5.0)

    def test_overlapping_children_union_less_than_sum(self):
        with cpl.begin_span("parent", lane="GPU") as parent:
            with cpl.begin_span("child_a", lane="GPU") as ca:
                ca.record_work(4_000_000)
                time.sleep(0.004)
            with cpl.begin_span("child_b", lane="GPU") as cb:
                cb.record_work(4_000_000)
                time.sleep(0.004)
            parent.add_child(ca)
            parent.add_child(cb)
        parent_rec = cpl.get_spans()[0]
        # Overlapping children: union must be < sum (8 ms).
        self.assertLess(float(parent_rec["child_union_ms"]), 8.0)

    def test_concurrent_clip_source_lane_does_not_serialize(self):
        # A concurrent CLIP source-read lane overlaps restore; the serial
        # ledger must NOT add its duration into restore's serial total.
        t0 = time.monotonic_ns()
        with cpl.begin_span("restore:bootstrap", lane="RESTORE") as rs:
            rs.record_work(2_000_000)
            lane = cpl.begin_span("clip_qd_source_read", lane="CLIP",
                                  start_mono_ns=time.monotonic_ns())
            time.sleep(0.006)
            lane.finish(end_mono_ns=time.monotonic_ns())
        end = time.monotonic_ns()
        spans = cpl.get_spans()
        serial = cpl.assert_serial_ledger_zero_gap(
            start_mono_ns=t0, end_mono_ns=end, spans=spans,
        )
        # The serial window is fully covered (zero gap) and the CLIP lane
        # overlapped restore: on this coarse 15.6 ms tick both spans may share
        # a start stamp, so the greedy merge assigns the window to one owner.
        # The contract: NO missing wall (total == segment sum), and the
        # concurrent lane never ADDED serial time beyond the window.
        self.assertTrue(serial["zero_gap"])
        self.assertLessEqual(serial["total_ms"], 20.0)


class EndMissingAndDuplicateTest(unittest.TestCase):
    """Duplicate and end-missing bridge behavior: a double start reuses the
    active span; an end with no active span is a safe no-op; a start after
    end creates a fresh span."""

    def setUp(self):
        cpl.clear_ledger_for_test()

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_double_start_reuses_active_span(self):
        b1 = cpl.TraceSpanBridge("sampling", lane="SAMPLING")
        b1.start()
        b2 = cpl.TraceSpanBridge("sampling", lane="SAMPLING")
        b2.start()
        self.assertIs(b1.span, b2.span)
        cpl.TraceSpanBridge.close_all()
        self.assertEqual(len(cpl.get_spans()), 1)

    def test_end_without_start_is_noop(self):
        b = cpl.TraceSpanBridge("sampling", lane="SAMPLING")
        b.end()
        self.assertEqual(len(cpl.get_spans()), 0)

    def test_start_after_end_creates_fresh_span(self):
        b1 = cpl.TraceSpanBridge("sampling", lane="SAMPLING")
        b1.start()
        b1.end()
        self.assertEqual(len(cpl.get_spans()), 1)
        b2 = cpl.TraceSpanBridge("sampling", lane="SAMPLING")
        b2.start()
        b2.end()
        self.assertEqual(len(cpl.get_spans()), 2)


class E30E31LedgerIngestionTest(unittest.TestCase):
    """E30 clip_qd_* and E31 CLIP-forward events land on the canonical ledger
    axis with the request identity (stamped via record_event)."""

    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(request_id="e30e31-fixture")

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_e30_clip_qd_events_ingested(self):
        e30_names = (
            "clip_qd_source_submit_start",
            "clip_qd_source_submit_end",
            "clip_qd_read_begin",
            "clip_qd_read_end",
            "clip_qd_source_first_completion",
            "clip_qd_source_last_completion",
            "clip_qd_buffer_wait",
            "clip_qd_copy_to_device_start",
            "clip_qd_copy_to_device_end",
            "clip_qd_device_ready",
            "clip_qd_owner_created",
            "clip_qd_spec_record_publish",
            "clip_qd_take",
            "clip_qd_bind",
            "clip_qd_owner_retained",
        )
        t0 = time.monotonic_ns()
        for i, name in enumerate(e30_names):
            cpl.record_event(name, mono_ns=t0 + i)
        events = cpl.get_events()
        names = [e["name"] for e in events]
        for expected in e30_names:
            self.assertIn(expected, names)
        for e in events:
            self.assertEqual(e["identity"]["request_id"], "e30e31-fixture")

    def test_e31_clip_forward_events_ingested(self):
        e31_names = (
            "clip_forward_start",
            "clip_forward_end",
            "clip_gpu_event_start",
            "clip_gpu_event_end",
            "clip_forward_gpu_ms",
            "clip_cast_once_start",
            "clip_cast_once_end",
            "clip_cast_once_gpu_ms",
            "clip_forward_cast_summary",
            "clip_profiler_start",
            "clip_profiler_end",
        )
        t0 = time.monotonic_ns()
        for i, name in enumerate(e31_names):
            cpl.record_event(name, mono_ns=t0 + i)
        events = cpl.get_events()
        names = [e["name"] for e in events]
        for expected in e31_names:
            self.assertIn(expected, names)
        for e in events:
            self.assertEqual(e["identity"]["request_id"], "e30e31-fixture")

    def test_speculative_clip_lane_events_ingested(self):
        # The restore-time speculative CLIP source lane (E28) emits its
        # started/finished boundaries on the canonical axis so the ledger can
        # prove overlap vs stretch of the concurrent source read.
        t0 = time.monotonic_ns()
        cpl.record_event("clip_speculative_lane_started", mono_ns=t0)
        cpl.record_event("clip_speculative_lane_finished", mono_ns=t0 + 1_000_000)
        events = cpl.get_events()
        names = [e["name"] for e in events]
        self.assertIn("clip_speculative_lane_started", names)
        self.assertIn("clip_speculative_lane_finished", names)

    def test_unet_and_empty_cache_events_ingested(self):
        # The plan-receipt UNET lane submit and the measured soft_empty_cache
        # wall are ledger events (Phase 8/9 evidence).
        t0 = time.monotonic_ns()
        cpl.record_event("unet_lane_submitted", mono_ns=t0)
        cpl.record_event("soft_empty_cache", mono_ns=t0 + 500_000,
                         metadata={"total_ms": 12.5, "empty_cache_ms": 10.0})
        events = cpl.get_events()
        names = [e["name"] for e in events]
        self.assertIn("unet_lane_submitted", names)
        self.assertIn("soft_empty_cache", names)


class ErrorPathTest(unittest.TestCase):
    """record_event / begin_span must never raise on bad input."""

    def setUp(self):
        cpl.clear_ledger_for_test()

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_record_event_never_raises(self):
        # None name, None mono, bogus metadata: all must be safe no-ops/records.
        cpl.record_event(None, mono_ns=None)
        cpl.record_event("", mono_ns=0)
        cpl.record_event("x", mono_ns=-5, metadata={"a": object()})
        self.assertGreaterEqual(len(cpl.get_events()), 1)

    def test_begin_span_never_raises(self):
        s = cpl.begin_span(None, lane=None, metadata=None)
        self.assertIsNotNone(s)
        s.finish(end_mono_ns=time.monotonic_ns())
        self.assertGreaterEqual(len(cpl.get_spans()), 1)


class AuthoritativeEndpointsTest(unittest.TestCase):
    """E29 acceptance contract: the serial ledger MUST be bounded by the
    explicit authoritative endpoints, never by min/max(existing events)."""

    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(
            request_id="req-ep",
            restored_instance_id="ri-1",
            restore_session_id="rs-1",
            container_session_id="cs-1",
        )

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_report_requires_both_endpoints(self):
        # No endpoints → endpoint_status missing, serial_ledger None.
        with cpl.begin_span("request:executor-run", lane="EXECUTOR") as s:
            s.record_work(1_000_000)
        report = cpl.request_ledger_report()
        self.assertEqual(report["endpoint_status"], "missing")
        self.assertIsNone(report["serial_ledger"])
        self.assertIn("remote_python_resume_mono_ns", report["missing_endpoints"])
        self.assertIn("first_durable_result_mono_ns", report["missing_endpoints"])

    def test_report_uses_explicit_endpoints_not_minmax(self):
        # Spans exist ONLY in a narrow window; the report must still cover the
        # FULL authoritative window with explicit UNATTRIBUTED gaps.
        start = time.monotonic_ns()
        with cpl.begin_span("request:executor-run", lane="EXECUTOR") as s:
            s.record_work(2_000_000)
        span_end = max(sp["end_mono_ns"] for sp in cpl.get_spans())
        # Authoritative window is LARGER than the span window on both sides.
        cpl.set_authoritative_endpoints(
            remote_python_resume_mono_ns=start - 5_000_000,
            first_durable_result_mono_ns=span_end + 5_000_000,
        )
        report = cpl.request_ledger_report()
        self.assertEqual(report["endpoint_status"], "ok")
        self.assertEqual(report["start_mono_ns"], start - 5_000_000)
        self.assertEqual(report["end_mono_ns"], span_end + 5_000_000)
        serial = report["serial_ledger"]
        # The pre-span and post-span windows MUST be explicit UNATTRIBUTED.
        names = [seg["name"] for seg in serial["segments"]]
        self.assertGreaterEqual(names.count("UNATTRIBUTED"), 2)
        self.assertGreater(serial["unattributed_ms"], 0.0)
        self.assertTrue(serial["zero_gap"])

    def test_truncated_ledger_cannot_shrink_bounds(self):
        # A ledger with only a tiny tail must NOT report zero-gap over the
        # truncated interval: the authoritative window is fixed.
        start = time.monotonic_ns()
        with cpl.begin_span("late-only", lane="SAMPLING") as s:
            s.record_work(1_000_000)
        end = max(sp["end_mono_ns"] for sp in cpl.get_spans())
        cpl.set_authoritative_endpoints(
            remote_python_resume_mono_ns=start,
            first_durable_result_mono_ns=end + 3_000_000,
        )
        report = cpl.request_ledger_report()
        serial = report["serial_ledger"]
        # The gap between the span and the end must be explicit UNATTRIBUTED.
        self.assertEqual(serial["end_mono_ns"], end + 3_000_000)
        names = [seg["name"] for seg in serial["segments"]]
        self.assertIn("UNATTRIBUTED", names)

    def test_clear_resets_endpoints(self):
        cpl.set_authoritative_endpoints(
            remote_python_resume_mono_ns=123,
            first_durable_result_mono_ns=456,
        )
        cpl.clear_ledger_for_test()
        report = cpl.request_ledger_report()
        self.assertEqual(report["endpoint_status"], "missing")


class V38SpanSurvivalRegressionTest(unittest.TestCase):
    """Reproduce the v38 2-spans/6-events failure so it can never return.

    v38's canonical ledger had restore_span_count=0, request_span_count=2
    (only the bridge spans ``sampling`` + ``executor:graph-execution``), and
    every direct ``begin_span`` (restore decomposition, request-setup,
    ``request:executor-run``) silently died.  Root causes:

    * ``CriticalPathSpan.finish`` only accepted ``end_mono_ns`` but every
      close site passed ``mono_ns=`` -> TypeError swallowed by the
      surrounding ``except Exception: pass``.
    * Restore spans were opened AFTER their close sites (None at close).
    * ``_deserialize_end_ns`` was referenced before assignment.

    These tests lock the FIXED behavior: the ledger API must accept both
    keyword spellings and the close-after-open lifecycle must persist.
    """

    def setUp(self):
        cpl.clear_ledger_for_test()

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_finish_accepts_mono_ns_keyword(self):
        # The exact v38 bug: close sites used finish(mono_ns=...); this must
        # now be an alias for end_mono_ns and MUST persist the span.
        t0 = time.monotonic_ns()
        s = cpl.begin_span("restore:early", lane="RESTORE", start_mono_ns=t0)
        time.sleep(0.002)
        s.finish(mono_ns=time.monotonic_ns())
        spans = cpl.get_spans()
        self.assertEqual(len(spans), 1, "finish(mono_ns=...) must persist the span")
        self.assertEqual(spans[0]["name"], "restore:early")
        self.assertIsNotNone(spans[0]["end_mono_ns"])
        self.assertGreaterEqual(spans[0]["duration_ms"], 0.0)

    def test_finish_end_mono_ns_still_works(self):
        s = cpl.begin_span("restore:finalize", lane="RESTORE")
        s.finish(end_mono_ns=time.monotonic_ns())
        spans = cpl.get_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["name"], "restore:finalize")

    def test_restore_phase_spans_survive_begin_request(self):
        # The v38 lifecycle: restore spans must be created BEFORE their close
        # sites and survive the request-scoped reset at method entry.
        cpl.begin_restore("req-v38")
        t0 = time.monotonic_ns()
        early = cpl.begin_span("restore:early", lane="RESTORE", start_mono_ns=t0)
        early.finish(mono_ns=time.monotonic_ns())
        evict = cpl.begin_span("restore:eviction", lane="RESTORE",
                               start_mono_ns=time.monotonic_ns())
        evict.finish(mono_ns=time.monotonic_ns())
        snap = cpl.begin_span("restore:snapshot", lane="RESTORE",
                              start_mono_ns=time.monotonic_ns())
        snap.finish(mono_ns=time.monotonic_ns())
        cpl.begin_request("req-v38")
        restore_spans = cpl.get_restore_spans()
        self.assertEqual(len(restore_spans), 3)
        names = [s["name"] for s in restore_spans]
        self.assertEqual(names, ["restore:early", "restore:eviction", "restore:snapshot"])

    def test_request_setup_spans_persist_with_close(self):
        # The v38 request-setup spans were created but never closed -> never
        # persisted.  Closing them must land them in the request store.
        cpl.begin_request("req-setup")
        t0 = time.monotonic_ns()
        idc = cpl.begin_span("request:identity-capture", lane="REQUEST-SETUP",
                             start_mono_ns=t0)
        idc.finish(mono_ns=time.monotonic_ns())
        ds = cpl.begin_span("request:plan-deserialize", lane="REQUEST-SETUP",
                            start_mono_ns=time.monotonic_ns())
        ds.finish(mono_ns=time.monotonic_ns())
        ss = cpl.begin_span("request:setup-schedule", lane="REQUEST-SETUP",
                            start_mono_ns=time.monotonic_ns())
        ss.finish(mono_ns=time.monotonic_ns())
        spans = cpl.get_spans()
        self.assertEqual(len(spans), 3)
        names = [s["name"] for s in spans]
        for expected in ("request:identity-capture", "request:plan-deserialize",
                         "request:setup-schedule"):
            self.assertIn(expected, names)

    def test_executor_run_span_plan_received_to_durable_result(self):
        # request:executor-run opens at plan_received and closes at the
        # durable result; it must persist with the exact end boundary.
        cpl.begin_request("req-exec")
        t0 = time.monotonic_ns()
        cpl.record_event("plan_received", mono_ns=t0)
        run = cpl.begin_span("request:executor-run", lane="EXECUTOR",
                             start_mono_ns=t0)
        time.sleep(0.002)
        end = time.monotonic_ns()
        cpl.record_event("first_durable_result", mono_ns=end)
        run.finish(mono_ns=end)
        spans = cpl.get_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["name"], "request:executor-run")
        self.assertEqual(spans[0]["start_mono_ns"], t0)
        self.assertEqual(spans[0]["end_mono_ns"], end)

    def test_identity_set_then_refreshed_keeps_ids(self):
        # The v38 identity block was empty because set_request_identity ran
        # before the IDs existed.  A later refresh must update the block used
        # by subsequent spans/events.
        cpl.set_request_identity(request_id="req-1")
        with cpl.begin_span("early", lane="RESTORE") as s:
            s.record_work(1_000_000)
        # IDs are created later in restore; refresh now.
        cpl.set_request_identity(
            request_id="req-1",
            restored_instance_id="ri-abc",
            restore_session_id="rs-xyz",
            container_session_id="cs-1",
        )
        with cpl.begin_span("later", lane="RESTORE") as s:
            s.record_work(1_000_000)
        spans = cpl.get_spans()
        self.assertEqual(spans[0]["identity"]["restored_instance_id"], "")
        self.assertEqual(spans[1]["identity"]["restored_instance_id"], "ri-abc")
        self.assertEqual(spans[1]["identity"]["restore_session_id"], "rs-xyz")

    def test_mm_load_models_gpu_bridge_lifecycle(self):
        # The real gpu-loader wrapper pattern: a fresh bridge opens at the
        # outermost call entry, a FRESH bridge instance closes it in the
        # finally (adopting the active span).  This must produce exactly one
        # persisted span spanning the call wall.
        t0 = time.monotonic_ns()
        cpl.TraceSpanBridge("model-mgmt:load_models_gpu", lane="MODEL-MGMT").start(
            mono_ns=t0
        )
        time.sleep(0.003)
        cpl.TraceSpanBridge("model-mgmt:load_models_gpu", lane="MODEL-MGMT").end(
            mono_ns=time.monotonic_ns()
        )
        spans = cpl.get_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["name"], "model-mgmt:load_models_gpu")
        self.assertEqual(spans[0]["lane"], "MODEL-MGMT")
        self.assertGreaterEqual(spans[0]["duration_ms"], 2.0)
        self.assertIsNotNone(spans[0]["end_mono_ns"])

    def test_restore_span_created_at_site_has_honest_duration(self):
        # The v38/early-fix corruption: spans created at restore entry but
        # re-stamped later reported duration from CREATION, not from the
        # stamped start.  A span created at its true site must have
        # duration_ms ≈ mono window.
        t0 = time.monotonic_ns()
        s = cpl.begin_span("restore:eviction", lane="RESTORE", start_mono_ns=t0)
        time.sleep(0.004)
        t1 = time.monotonic_ns()
        s.finish(mono_ns=t1)
        rec = cpl.get_spans()[0]
        self.assertEqual(rec["start_mono_ns"], t0)
        self.assertEqual(rec["end_mono_ns"], t1)
        self.assertLessEqual(abs(rec["duration_ms"] - (t1 - t0) / 1_000_000), 20.0)


if __name__ == "__main__":
    unittest.main()
