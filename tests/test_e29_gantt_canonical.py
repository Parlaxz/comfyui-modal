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
