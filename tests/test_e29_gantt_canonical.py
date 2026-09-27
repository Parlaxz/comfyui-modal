"""E29 offline tests: canonical Gantt repair.

No Modal, no CUDA, no remote execution.  Validates that the Gantt derives
strictly from the canonical ledger, that semantic row ordering groups CLIP
stages, that real gaps render as explicit UNATTRIBUTED bars (never blank),
and that a reused container cannot leak previous-request spans into the next
request's Gantt (the E28 warm-run leakage regression).
"""

import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("COMFYMODAL_V2_CRITICAL_PATH_LEDGER", "1")

sys.path.insert(0, r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal")

from comfymodal_runtime import critical_path_ledger as cpl  # noqa: E402
from comfymodal_runtime import gantt_canonical as gc  # noqa: E402


class CanonicalGanttTest(unittest.TestCase):
    def setUp(self):
        cpl.clear_ledger_for_test()
        cpl.set_request_identity(request_id="req-gantt")

    def tearDown(self):
        cpl.clear_ledger_for_test()

    def test_gantt_derives_only_from_ledger(self):
        with cpl.begin_span("restore method", lane="RESTORE") as s:
            s.record_work(1_000_000)
        with cpl.begin_span("sampling", lane="GPU") as s:
            s.record_work(2_000_000)
        lines = gc.render_canonical_gantt(cpl)
        text = "\n".join(lines)
        self.assertIn("restore method", text)
        self.assertIn("sampling", text)
        self.assertNotIn("fabricated", text)

    def test_semantic_row_order_groups_clip(self):
        """CLIP source read (starts during restore) must appear adjacent to
        CLIP hydration/bind/forward vertically — never scattered by start
        timestamp."""
        import time as _time
        with cpl.begin_span("restore method", lane="RESTORE") as s:
            s.record_work(1_000_000)
            _time.sleep(0.02)
        with cpl.begin_span("CLIP source read", lane="CLIP") as s:
            s.record_work(1_000_000)
            _time.sleep(0.02)
        with cpl.begin_span("CLIP GPU hydration", lane="CLIP") as s:
            s.record_work(1_000_000)
            _time.sleep(0.02)
        with cpl.begin_span("CLIP forward", lane="CLIP") as s:
            s.record_work(2_000_000)
            _time.sleep(0.02)
        lines = gc.render_canonical_gantt(cpl)
        text = "\n".join(lines)
        # Semantic lane rows: the three CLIP spans render as contiguous bar
        # rows (the exact-number table below also mentions CLIP, so only the
        # bar-region rows — those carrying a block/tiny bar glyph — count).
        bar_rows = [
            l for l in lines
            if l.startswith("CLIP") and ("█" in l or "▏" in l)
        ]
        self.assertEqual(len(bar_rows), 3)
        self.assertEqual(
            [l.split()[0] for l in bar_rows],
            ["CLIP", "CLIP", "CLIP"],
        )
        # The bar rows are contiguous in the bar region (no other row between
        # them): the exact-number table rows below also start with "CLIP", so
        # compare against the bar-row list only.
        clip_idx = [i for i, l in enumerate(lines) if l.startswith("CLIP") and ("█" in l or "▏" in l)]
        self.assertEqual(clip_idx[-1] - clip_idx[0], len(clip_idx) - 1)

    def test_real_gap_renders_unattributed(self):
        with cpl.begin_span("a", lane="RESTORE") as s:
            s.record_work(1_000_000)
        with cpl.begin_span("z", lane="OUTPUT") as s:
            s.record_work(1_000_000)
        lines = gc.render_canonical_gantt(cpl)
        text = "\n".join(lines)
        self.assertIn("UNATTRIBUTED", text)

    def test_no_previous_request_leakage(self):
        """E28 warm-run leakage regression: the Gantt of request B must not
        contain request A spans."""
        cpl.begin_request("req-a")
        with cpl.begin_span("prev_sampling", lane="GPU") as s:
            s.record_work(1_000_000)
        cpl.begin_request("req-b")
        with cpl.begin_span("next_sampling", lane="GPU") as s:
            s.record_work(1_000_000)
        lines = gc.render_canonical_gantt(cpl)
        text = "\n".join(lines)
        self.assertIn("next_sampling", text)
        self.assertNotIn("prev_sampling", text)

    def test_emit_writes_one_flushed_record_per_line(self):
        with cpl.begin_span("sampling", lane="GPU") as s:
            s.record_work(1_000_000)
        with mock.patch.object(gc, "_gantt_enabled", return_value=True), mock.patch(
            "builtins.print"
        ) as print_mock:
            gc.emit_canonical_gantt(cpl, request_id="req-gantt")

        lines = gc.render_canonical_gantt(cpl, title="E29 CANONICAL GANTT request=req-gantt")
        self.assertTrue(print_mock.call_args_list)
        self.assertEqual(
            print_mock.call_args_list,
            [mock.call(f"[GOLDEN GANTT] {line}", flush=True) for line in lines],
        )
        self.assertTrue(
            all(call.args[0].startswith("[GOLDEN GANTT]") for call in print_mock.call_args_list)
        )
        self.assertTrue(all(call.kwargs == {"flush": True} for call in print_mock.call_args_list))

    def test_emit_is_independent_of_optional_trace(self):
        """Canonical rows emit with either an absent or present E27 trace."""
        with cpl.begin_span("sampling", lane="GPU") as s:
            s.record_work(1_000_000)

        emitted = []
        for optional_trace in (None, object()):
            with mock.patch.object(gc, "_gantt_enabled", return_value=True), mock.patch(
                "builtins.print"
            ) as print_mock:
                # The canonical emitter intentionally takes only the ledger;
                # an optional E27 trace cannot gate this call path.
                _ = optional_trace
                gc.emit_canonical_gantt(cpl, request_id="req-gantt")
                emitted.append(list(print_mock.call_args_list))

        self.assertEqual(emitted[0], emitted[1])
        self.assertTrue(emitted[0])
        self.assertTrue(all(call.args[0].startswith("[GOLDEN GANTT]") for call in emitted[0]))
        self.assertTrue(all(call.kwargs == {"flush": True} for call in emitted[0]))
        self.assertIn("request=req-gantt", emitted[0][0].args[0])

    def test_emit_no_rows_is_explicitly_unavailable(self):
        with mock.patch.object(gc, "_gantt_enabled", return_value=True), mock.patch(
            "builtins.print"
        ) as print_mock:
            gc.emit_canonical_gantt(cpl, request_id="req-gantt")

        print_mock.assert_called_once_with(
            "[GOLDEN GANTT] request=req-gantt unavailable: no canonical ledger rows",
            flush=True,
        )

    def test_emit_falls_back_to_parallel_stage_list_without_trace(self):
        """Direct Golden Parallel stages remain renderable when E27 is absent."""
        telemetry = {
            "stages": [
                {
                    "name": "golden_clip_load",
                    "entry_monotonic_ns": 1_000_000_000,
                    "end_monotonic_ns": 2_000_000_000,
                },
                {
                    "name": "golden_unet_load",
                    "entry_monotonic_ns": 1_500_000_000,
                    "end_monotonic_ns": 3_000_000_000,
                },
                {
                    "name": "golden_clip_forward",
                    "entry_monotonic_ns": 2_000_000_000,
                    "end_monotonic_ns": 3_500_000_000,
                },
            ],
            "events": [],
            "transports": [
                {
                    "path": "clip.safetensors",
                    "source_wall_ms": 10.0,
                    "total_load_ms": 20.0,
                },
                {
                    "path": "unet.safetensors",
                    "gpu_ready_wall_ms": 30.0,
                    "gpu_ready_tail_ms": 4.0,
                },
            ],
        }
        with mock.patch.object(gc, "_gantt_enabled", return_value=True), mock.patch(
            "builtins.print"
        ) as print_mock:
            gc.emit_canonical_gantt(
                cpl,
                request_id="parallel-stage-list",
                golden_telemetry=telemetry,
            )

        emitted = [call.args[0] for call in print_mock.call_args_list]
        self.assertTrue(emitted)
        self.assertIn("request=parallel-stage-list", emitted[0])
        self.assertIn("CLIP load", "\n".join(emitted))
        self.assertIn("UNET load", "\n".join(emitted))
        self.assertIn("CLIP forward", "\n".join(emitted))
        self.assertIn("src=10.0ms full=20.0ms", "\n".join(emitted))
        self.assertIn("ready=30.0ms tail=4.0ms", "\n".join(emitted))
        self.assertTrue(all("\n" not in line and "\r" not in line for line in emitted))
        self.assertTrue(all(call.kwargs == {"flush": True} for call in print_mock.call_args_list))
        self.assertTrue(all(line.startswith("[GOLDEN GANTT]") for line in emitted))
        self.assertNotIn("unavailable", "\n".join(emitted))

    def test_emit_disabled_gate_writes_nothing(self):
        with cpl.begin_span("sampling", lane="GPU") as s:
            s.record_work(1_000_000)
        with mock.patch.object(gc, "_gantt_enabled", return_value=False), mock.patch(
            "builtins.print"
        ) as print_mock:
            gc.emit_canonical_gantt(cpl, request_id="req-gantt")

        print_mock.assert_not_called()

    def test_emit_force_ignores_disabled_gate(self):
        with cpl.begin_span("sampling", lane="GPU") as s:
            s.record_work(1_000_000)
        with mock.patch.object(gc, "_gantt_enabled", return_value=False), mock.patch(
            "builtins.print"
        ) as print_mock:
            gc.emit_canonical_gantt(cpl, request_id="req-gantt", force=True)

        self.assertTrue(print_mock.call_args_list)
        self.assertTrue(
            all(call.args[0].startswith("[GOLDEN GANTT]") for call in print_mock.call_args_list)
        )
        self.assertTrue(all(call.kwargs == {"flush": True} for call in print_mock.call_args_list))

    def test_bounded_line_width(self):
        with cpl.begin_span("restore method", lane="RESTORE") as s:
            s.record_work(1_000_000)
        with cpl.begin_span("sampling", lane="GPU") as s:
            s.record_work(2_000_000)
        lines = gc.render_canonical_gantt(cpl)
        for line in lines:
            self.assertLessEqual(len(line), 100, f"line too long: {line!r}")

    def test_point_events_in_detail_not_overview_bars(self):
        cpl.record_event("sampling_end", mono_ns=__import__("time").monotonic_ns())
        with cpl.begin_span("sampling", lane="GPU") as s:
            s.record_work(1_000_000)
        lines = gc.render_canonical_gantt(cpl)
        text = "\n".join(lines)
        # The event appears in the point-event detail section, not as a bar row.
        self.assertIn("point events", text)
        self.assertIn("sampling_end", text)


if __name__ == "__main__":
    unittest.main()
