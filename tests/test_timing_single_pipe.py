"""Single-pipe timing contract (fast_unit).

Guards the invariant the Diagnostics viewer depends on: timing recorded for
a run must survive every layer it passes through — ``timing.json`` on disk,
the summary-index ``timing_summary`` column, and the History V2 attempt
timing.  A regression in any one of those layers used to surface as a bare
"Diagnostics pending" with no failing test; this suite pins the whole pipe.

Covers:
- ``_golden_node_spans``: per-node rows collected from Golden stream
  events (gantt_span / node_progress / completed golden_stage), completed
  durations only, never estimated, bounded, [] when unusable.
- ``RunHistoryService``: ``update_run(timings=...)`` lands in
  ``timing.json`` AND in the index ``timing_summary`` (the single-pipe
  merge), and the V2 mirror carries it onto the attempt.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import studio_golden_run
from experiment_service import RunHistoryService
from history_index import HistoryIndex
from history_v2_repository import HistoryV2Repository
from history_v2_store import HistoryV2Store
from history_v2_writer import (
    _gen_id,
    get_writer,
    reset_writer_config,
    set_writer_data_root,
    set_writer_enabled,
)


pytestmark = pytest.mark.fast_unit


def _span_events():
    return [
        {"type": "gantt_span", "name": "CLIPTextEncode (node 98:24)",
         "phase": "completed", "durationMs": 2000},
        {"type": "node_progress", "label": "SamplerCustomAdvanced (node 98:12)",
         "entry_monotonic_ns": 1_000_000_000, "end_monotonic_ns": 42_700_000_000},
        {"type": "golden_stage", "stage": "golden_restore", "phase": "completed",
         "entry_monotonic_ns": 0, "end_monotonic_ns": 1_100_000_000},
        # Started-but-never-closed: no truthful duration, must be dropped.
        {"type": "gantt_span", "name": "Ghost (node 1:1)", "phase": "started"},
        # Noise: no label / no duration.
        {"type": "node_progress", "phase": "completed", "durationMs": 5},
        {"type": "status", "phase": "restoring"},
        "not-a-mapping",
    ]


class GoldenNodeSpansTests(unittest.TestCase):
    def test_collects_completed_spans_with_measured_durations(self):
        rows = studio_golden_run._golden_node_spans(_span_events())
        by_label = {row["label"]: row["durationMs"] for row in rows}
        self.assertEqual(by_label["CLIPTextEncode (node 98:24)"], 2000)
        # Monotonic interval, ns -> ms.
        self.assertAlmostEqual(
            by_label["SamplerCustomAdvanced (node 98:12)"], 41700.0)
        self.assertEqual(by_label["golden_restore"], 1100.0)

    def test_drops_unclosable_and_labelless_spans(self):
        rows = studio_golden_run._golden_node_spans(_span_events())
        labels = [row["label"] for row in rows]
        self.assertNotIn("Ghost (node 1:1)", labels)
        self.assertEqual(len(labels), len(set(labels)))

    def test_empty_or_useless_stream_yields_no_rows(self):
        self.assertEqual(studio_golden_run._golden_node_spans([]), [])
        self.assertEqual(studio_golden_run._golden_node_spans(None), [])
        self.assertEqual(
            studio_golden_run._golden_node_spans(
                [{"type": "status", "phase": "restoring"}]), [])

    def test_stage_timings_still_honest_when_nothing_closed(self):
        # The companion contract: no closed stages -> {} (never zeros),
        # so History keeps showing pending instead of fabricated rows.
        self.assertEqual(studio_golden_run._golden_stage_timings([]), {})
        self.assertEqual(
            studio_golden_run._golden_stage_timings(
                [{"type": "status", "phase": "x"}]), {})


class TimingSinglePipeTests(unittest.TestCase):
    """One write (update_run with timings) must surface in timing.json,
    the index timing_summary, and the V2 attempt timing alike."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_root = Path(self._tmp.name)
        self.addCleanup(reset_writer_config)
        set_writer_data_root(self.tmp_root)
        set_writer_enabled(True)
        self.legacy_root = self.tmp_root / "legacy_run_history"
        self.svc = RunHistoryService(self.legacy_root)

    def _complete_run_with_spans(self, run_id="r_pipe0001"):
        spans = studio_golden_run._golden_node_spans(_span_events())
        self.assertTrue(spans, "fixture must yield span rows")
        timings = {"_run_type": "golden", "nodeSpans": spans}
        meta = self.svc.record_run(
            kind="playground_run", prompt_id="p1", status="running", meta={})
        rid = meta["run_id"]
        self.svc.update_run(rid, status="completed", timings=timings)
        return rid, spans

    def test_timings_land_in_timing_json(self):
        rid, spans = self._complete_run_with_spans()
        timing_path = self.legacy_root / rid / "timing.json"
        self.assertTrue(timing_path.is_file())
        stored = json.loads(timing_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["nodeSpans"], spans)

    def test_timings_surface_in_index_summary(self):
        rid, spans = self._complete_run_with_spans()
        index = HistoryIndex(self.legacy_root)
        try:
            entry = index.get(rid)
        finally:
            index.close()
        self.assertIsNotNone(entry)
        summary = entry.get("timing_summary") or {}
        self.assertTrue(summary, "index timing_summary must not be empty")
        self.assertEqual(summary.get("nodeSpans"), spans)

    def test_timings_mirror_onto_v2_attempt(self):
        rid, spans = self._complete_run_with_spans()
        repo = HistoryV2Repository(
            HistoryV2Store(self.tmp_root / ".studio_history_v2" / "history_v2.db"))
        detail = repo.get_generation(_gen_id(rid))
        self.assertIsNotNone(detail)
        self.assertTrue(detail.attempts, "expected a mirrored attempt")
        attempt_timing = detail.attempts[0].timing or {}
        self.assertTrue(
            attempt_timing, "V2 attempt timing must not be empty")
        self.assertEqual(attempt_timing.get("nodeSpans"), spans)
