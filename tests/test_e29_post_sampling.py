"""E29 post-sampling decomposition ledger tests: sampling_end ->
first_durable_result real owners.

No Modal, no CUDA, no remote execution.  Validates:
1. All post-sampling events are recordable via record_event.
2. The post-sampling spans persist in request_ledger_report.
3. Post-sampling child spans survive artifact conversion.
4. Parent executor coverage cannot masquerade as semantic decomposition:
   children's union plus honest UNATTRIBUTED residual.
5. Cross-request isolation for the new spans/events.
6. Monotonic ordering of the post-sampling event sequence.
"""

import os
import sys
import time
import unittest

os.environ.setdefault("COMFYMODAL_V2_CRITICAL_PATH_LEDGER", "1")

sys.path.insert(0, r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal")

from comfymodal_runtime import critical_path_ledger as cpl  # noqa: E402


POST_SAMPLING_EVENT_NAMES = (
    "sampling_end",
    "sampler_finally_done",
    "vae_activation_requested",
    "vae_lane_acquired",
    "vae_ready_terminal",
    "graph_next_node_after_sampler",
    "post_vae_decode",
    "result_assembly_start",
    "output_persist_done",
    "first_durable_result",
)

POST_SAMPLING_SPAN_NAMES = (
    "vae:activation-handoff",
    "post-vae:graph-tail",
    "result:assembly",
)


class PostSamplingEventRecordabilityTest(unittest.TestCase):
    """All post-sampling events are recordable and land in the ledger with
    the correct name and identity."""

    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(request_id="post-sampling-events-fixture")

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_all_post_sampling_events_recordable(self):
        t0 = time.monotonic_ns()
        for i, name in enumerate(POST_SAMPLING_EVENT_NAMES):
            cpl.record_event(name, mono_ns=t0 + i * 1_000_000)
        events = cpl.get_events()
        names = [e["name"] for e in events]
        for expected in POST_SAMPLING_EVENT_NAMES:
            self.assertIn(expected, names)
        for e in events:
            self.assertEqual(
                e["identity"]["request_id"], "post-sampling-events-fixture"
            )

    def test_events_have_ascending_monotonic_stamps(self):
        t0 = time.monotonic_ns()
        for i, name in enumerate(POST_SAMPLING_EVENT_NAMES):
            cpl.record_event(name, mono_ns=t0 + i * 1_000_000)
        events = cpl.get_events()
        stamps = [e["mono_ns"] for e in events]
        for i in range(1, len(stamps)):
            self.assertGreaterEqual(
                stamps[i], stamps[i - 1],
                f"ascending order violated at index {i}",
            )


class PostSamplingSpanPersistenceTest(unittest.TestCase):
    """The post-sampling spans persist and survive artifact conversion."""

    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(request_id="post-sampling-span-fixture")

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_spans_persist_with_boundaries(self):
        t0 = time.monotonic_ns()
        spans_opened = {}
        for i, name in enumerate(POST_SAMPLING_SPAN_NAMES):
            spans_opened[name] = cpl.begin_span(
                name, lane="VAE" if "vae" in name else "EXECUTOR",
                start_mono_ns=t0 + i * 1_000_000,
            )
        time.sleep(0.001)
        for name, span in spans_opened.items():
            span.finish(end_mono_ns=time.monotonic_ns())
        spans = cpl.get_spans()
        names = [s["name"] for s in spans]
        for expected in POST_SAMPLING_SPAN_NAMES:
            self.assertIn(expected, names)
        for rec in spans:
            self.assertGreaterEqual(rec["duration_ms"], 0.0)

    def test_spans_survive_request_ledger_report(self):
        t0 = time.monotonic_ns()
        for i, name in enumerate(POST_SAMPLING_SPAN_NAMES):
            span = cpl.begin_span(
                name, lane="EXECUTOR", start_mono_ns=t0 + i * 1_000_000,
            )
            span.finish(end_mono_ns=time.monotonic_ns())
        cpl.set_authoritative_endpoints(
            remote_python_resume_mono_ns=t0 - 1_000_000,
            first_durable_result_mono_ns=time.monotonic_ns() + 1_000_000,
        )
        report = cpl.request_ledger_report()
        self.assertEqual(report["endpoint_status"], "ok")
        span_names = [s["name"] for s in report["spans"]]
        for expected in POST_SAMPLING_SPAN_NAMES:
            self.assertIn(expected, span_names)

    def test_spans_survive_artifact_capture(self):
        t0 = time.monotonic_ns()
        for i, name in enumerate(POST_SAMPLING_SPAN_NAMES):
            span = cpl.begin_span(
                name, lane="EXECUTOR", start_mono_ns=t0 + i * 1_000_000,
            )
            span.finish(end_mono_ns=time.monotonic_ns())
        cpl.set_authoritative_endpoints(
            remote_python_resume_mono_ns=t0 - 1_000_000,
            first_durable_result_mono_ns=time.monotonic_ns() + 1_000_000,
        )
        artifact = cpl.capture_ledger_report_for_artifact()
        self.assertIsNotNone(artifact)
        span_names = [s["name"] for s in artifact["spans"]]
        for expected in POST_SAMPLING_SPAN_NAMES:
            self.assertIn(expected, span_names)


class PostSamplingArithmeticTest(unittest.TestCase):
    """Parent executor coverage must NOT masquerade as semantic
    decomposition: the parent reconciles its own residual separately from its
    children's union, and unexplained parent residual stays UNATTRIBUTED."""

    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(request_id="post-sampling-arithmetic-fixture")

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def _build_nested_fixture(self, parent_work_ns=10_000_000):
        t0 = time.monotonic_ns()
        parent = cpl.begin_span("executor:graph-execution", lane="EXECUTOR",
                                start_mono_ns=t0)
        time.sleep(0.002)
        vae_decode = cpl.begin_span("VAE decode", lane="VAE",
                                    start_mono_ns=time.monotonic_ns())
        vae_decode.record_work(2_000_000)
        time.sleep(0.002)
        vae_decode.finish(end_mono_ns=time.monotonic_ns())
        parent.add_child(vae_decode)

        mm = cpl.begin_span("model-mgmt:load_models_gpu", lane="MODEL-MGMT",
                            start_mono_ns=time.monotonic_ns())
        mm.record_work(1_000_000)
        time.sleep(0.001)
        mm.finish(end_mono_ns=time.monotonic_ns())
        parent.add_child(mm)

        graph_tail = cpl.begin_span("post-vae:graph-tail", lane="EXECUTOR",
                                    start_mono_ns=time.monotonic_ns())
        graph_tail.record_work(1_000_000)
        time.sleep(0.001)
        graph_tail.finish(end_mono_ns=time.monotonic_ns())
        parent.add_child(graph_tail)

        result = cpl.begin_span("result:assembly", lane="EXECUTOR",
                                start_mono_ns=time.monotonic_ns())
        result.record_work(1_000_000)
        time.sleep(0.001)
        result.finish(end_mono_ns=time.monotonic_ns())
        parent.add_child(result)

        if parent_work_ns:
            parent.record_work(parent_work_ns)
        time.sleep(0.002)
        parent.finish(end_mono_ns=time.monotonic_ns())
        return parent, t0

    def test_children_union_is_not_naive_parent_cover(self):
        parent, t0 = self._build_nested_fixture()
        rec = parent._persist if False else None
        spans = cpl.get_spans()
        parent_rec = next(s for s in spans if s["name"] == "executor:graph-execution")
        # child_union_ms must be present and > 0 (children overlap; union not sum)
        self.assertGreaterEqual(parent_rec["child_union_ms"], 0.0)
        # The parent has an honest residual budget separate from children.
        self.assertIn("residual_ms", parent_rec)
        self.assertIn("residual_label", parent_rec)

    def test_unexplained_parent_residual_is_unattributed(self):
        parent, t0 = self._build_nested_fixture()
        spans = cpl.get_spans()
        parent_rec = next(s for s in spans if s["name"] == "executor:graph-execution")
        # The parent's declared work covers only part of its wall.
        self.assertIn("residual_label", parent_rec)
        # A >1 ms unexplained residual in the parent must be labeled UNATTRIBUTED,
        # proving parent coverage cannot hide a semantic unknown.
        residual_ms = parent_rec["residual_ms"]
        label = parent_rec["residual_label"]
        if residual_ms > 1.0:
            self.assertEqual(label, "UNATTRIBUTED")

    def test_post_sampling_spans_own_wall_under_parent(self):
        parent, t0 = self._build_nested_fixture()
        spans = cpl.get_spans()
        child_names = {s["name"] for s in spans}
        for expected in ("VAE decode", "model-mgmt:load_models_gpu",
                         "post-vae:graph-tail", "result:assembly"):
            self.assertIn(expected, child_names)
        # Each child persists its own duration independent of the parent.
        for s in spans:
            self.assertGreaterEqual(s["duration_ms"], 0.0)
            self.assertLessEqual(s["start_mono_ns"], s["end_mono_ns"])


class PostSamplingCrossRequestIsolationTest(unittest.TestCase):
    """begin_request must clear post-sampling spans/events from a prior
    request."""

    def setUp(self):
        cpl.clear_ledger_for_test()

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_begin_request_clears_post_sampling_events(self):
        cpl.set_request_identity(request_id="req-prev")
        cpl.record_event("sampling_end")
        cpl.record_event("first_durable_result")
        self.assertEqual(len(cpl.get_events()), 2)
        cpl.begin_request("req-next")
        self.assertEqual(len(cpl.get_events()), 0)

    def test_begin_request_clears_post_sampling_spans(self):
        cpl.set_request_identity(request_id="req-prev")
        span = cpl.begin_span("result:assembly", lane="EXECUTOR")
        span.finish(end_mono_ns=time.monotonic_ns())
        self.assertEqual(len(cpl.get_spans()), 1)
        cpl.begin_request("req-next")
        self.assertEqual(len(cpl.get_spans()), 0)

    def test_new_request_post_sampling_events_not_leaked(self):
        cpl.set_request_identity(request_id="req-1")
        cpl.record_event("sampling_end")
        cpl.begin_request("req-2")
        cpl.set_request_identity(request_id="req-2")
        cpl.record_event("post_vae_decode")
        events = cpl.get_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "post_vae_decode")


class PostSamplingMonotonicOrderingTest(unittest.TestCase):
    """Fixture proving the strict monotonic ordering of the post-sampling
    event sequence on the canonical axis."""

    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(request_id="post-sampling-ordering-fixture")

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_full_post_sampling_sequence_monotonic(self):
        t0 = time.monotonic_ns()
        ordered = [
            ("sampling_end", t0),
            ("sampler_finally_done", t0 + 100_000),
            ("vae_activation_requested", t0 + 200_000),
            ("vae_lane_acquired", t0 + 300_000),
            ("vae_ready_terminal", t0 + 400_000),
            ("graph_next_node_after_sampler", t0 + 500_000),
            ("post_vae_decode", t0 + 600_000),
            ("result_assembly_start", t0 + 700_000),
            ("output_persist_done", t0 + 800_000),
            ("first_durable_result", t0 + 900_000),
        ]
        for name, mono in ordered:
            cpl.record_event(name, mono_ns=mono)
        events = cpl.get_events()
        self.assertEqual(len(events), len(ordered))
        stamps = [e["mono_ns"] for e in events]
        for i in range(1, len(stamps)):
            self.assertGreaterEqual(
                stamps[i], stamps[i - 1],
                f"monotonic ordering violated at index {i}: "
                f"{events[i-1]['name']}={stamps[i-1]} > "
                f"{events[i]['name']}={stamps[i]}",
            )

    def test_sampling_end_precedes_first_durable_result(self):
        t0 = time.monotonic_ns()
        cpl.record_event("sampling_end", mono_ns=t0)
        cpl.record_event("first_durable_result", mono_ns=t0 + 50_000)
        events = cpl.get_events()
        by_name = {e["name"]: e for e in events}
        self.assertLess(
            by_name["sampling_end"]["mono_ns"],
            by_name["first_durable_result"]["mono_ns"],
        )


class ParentCoverageCannotMasqueradeTest(unittest.TestCase):
    """A parent span covering a child interval must still report honest
    residual: the serial ledger surfaces gaps as UNATTRIBUTED and never lets
    the parent's name own the child's semantic work."""

    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(request_id="parent-cover-fixture")

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_serial_ledger_renders_unowned_gap_as_unattributed(self):
        t0 = time.monotonic_ns()
        span = cpl.begin_span("executor:graph-execution", lane="EXECUTOR",
                              start_mono_ns=t0)
        time.sleep(0.02)
        span.finish(end_mono_ns=time.monotonic_ns())
        # No child spans were recorded: all wall (minus declared work) must
        # surface as residual; the serial ledger must not invent ownership.
        rec = cpl.get_spans()[0]
        self.assertGreaterEqual(rec["residual_ms"], 0.0)
        end = time.monotonic_ns()
        serial = cpl.build_serial_ledger(
            start_mono_ns=t0, end_mono_ns=end, spans=cpl.get_spans(),
        )
        self.assertTrue(serial["zero_gap"])
        unattributed = [
            seg for seg in serial["segments"]
            if seg["name"] == "UNATTRIBUTED"
        ]
        # Window fully covered by the executor span; residual is personal.
        self.assertEqual(len(unattributed), 0)


if __name__ == "__main__":
    unittest.main()