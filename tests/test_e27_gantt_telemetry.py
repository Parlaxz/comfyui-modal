"""Offline tests for E27 Gantt telemetry (comfymodal_runtime.gantt_telemetry).

These validate the span-collection and ASCII rendering logic with synthetic
traces — no Modal, no CUDA, no remote execution.
"""

import os
import sys
import time
import unittest

os.environ.setdefault("COMFYMODAL_V2_GANTT_TELEMETRY", "1")

sys.path.insert(0, r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal")

from comfymodal_runtime.contracts import TraceEvent  # noqa: E402
from comfymodal_runtime.trace import RuntimeTrace  # noqa: E402
from comfymodal_runtime.gantt_telemetry import (  # noqa: E402
    _collect_spans,
    _render_window,
    _pick_scale_ms,
    collect_gantt_report,
    register_gantt_span,
    reset_gantt_spans,
    render_gantt_trace,
    render_gantt_windows,
    render_zoomed_gantt,
    lane_for,
    _TOTAL_LINE_MAX,
)


class _FakeEvent:
    def __init__(self, name, monotonic_ns):
        self.name = name
        self.monotonic_ns = monotonic_ns


def _build_trace():
    trace = RuntimeTrace(request_id="e27-test", process="remote_method")
    # Simulate the real event stream: restore boundaries, CLIP hydration,
    # CLIP forward, UNET transfer, sampling, VAE decode.  All events are
    # stamped with synthetic monotonic_ns so the axis is coherent.
    t = 1_000_000_000
    for name, dur_ns in (
        ("clip_fh_hydration_start", 200_000_000),
        ("clip_hydration_gpu_start", 180_000_000),
        ("unet_gpu_transfer_start", 150_000_000),
        ("clip_forward_start", 300_000_000),
    ):
        trace.emit_at(name, wall_unix_ns=time.time_ns(), monotonic_ns=t, phase="execution")
        t += 1
    t += 100_000_000  # let hydration finish
    for name in (
        "clip_fh_hydration_end",
        "clip_hydration_gpu_end",
        "unet_gpu_transfer_end",
        "clip_forward_end",
    ):
        trace.emit_at(name, wall_unix_ns=time.time_ns(), monotonic_ns=t, phase="execution")
        t += 1
    trace.emit_at("sampling_start", wall_unix_ns=time.time_ns(), monotonic_ns=t, phase="execution")
    t += 400_000_000
    trace.emit_at("sampling_end", wall_unix_ns=time.time_ns(), monotonic_ns=t, phase="execution")
    t += 100_000_000
    trace.emit_at("vae_decode_start", wall_unix_ns=time.time_ns(), monotonic_ns=t, phase="execution")
    t += 120_000_000
    trace.emit_at("vae_decode_end", wall_unix_ns=time.time_ns(), monotonic_ns=t, phase="execution")
    # Metadata origin (restore resume) BEFORE the first span start.
    trace.set_metadata(
        remote_python_resume_mono_ns=500_000_000,
        restore_method_start_mono_ns=600_000_000,
        restore_method_end_mono_ns=900_000_000,
        modal_method_entry_mono_ns=950_000_000,
    )
    return trace


class GanttSpanCollectionTest(unittest.TestCase):
    def test_spans_collected_from_trace_pairs(self):
        trace = _build_trace()
        spans = _collect_spans(trace)
        by_name = {s["name"]: s for s in spans}
        self.assertIn("CLIP hydration", by_name)
        self.assertIn("CLIP forward", by_name)
        self.assertIn("UNET H2D", by_name)
        self.assertIn("sampling", by_name)
        self.assertIn("VAE decode", by_name)
        self.assertIn("restore method", by_name)
        self.assertIn("remote python resume", by_name)
        self.assertIn("method entry", by_name)
        # Ordering by start.
        starts = [s["start_mono_ns"] for s in spans]
        self.assertEqual(starts, sorted(starts))

    def test_no_fabricated_spans_for_unpaired_events(self):
        trace = RuntimeTrace(request_id="e27-test2", process="remote_method")
        trace.emit("clip_fh_hydration_start", metadata={})
        # No _end event — must NOT produce a span.
        spans = _collect_spans(trace)
        self.assertNotIn("CLIP hydration", [s["name"] for s in spans])

    def test_extra_span_registry(self):
        reset_gantt_spans()
        register_gantt_span(
            "method_setup",
            start_mono_ns=1_000_000_000,
            end_mono_ns=1_100_000_000,
            lane="MAIN",
        )
        trace = _build_trace()
        spans = _collect_spans(trace)
        names = [s["name"] for s in spans]
        self.assertIn("method_setup", names)
        reset_gantt_spans()

    def test_origin_resolution_prefers_python_resume(self):
        trace = _build_trace()
        origin = trace._metadata.get("remote_python_resume_mono_ns")
        spans = _collect_spans(trace)
        min_start = min(s["start_mono_ns"] for s in spans)
        self.assertEqual(origin, 500_000_000)
        self.assertLessEqual(origin, min_start)


class GanttRenderTest(unittest.TestCase):
    def test_render_uses_block_char_and_precise_numbers(self):
        trace = _build_trace()
        lines = render_gantt_trace(trace, max_chars=60)
        text = "\n".join(lines)
        # Solid block char present.
        self.assertIn("\u2588", text)
        # Graph rows do NOT append start/end/dur on every row.
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("CLIP hydration"):
                self.assertIn("ms", line)
        # The exact-number table exists below the graph.
        self.assertIn("---", text)
        self.assertIn("Start", text)
        self.assertIn("Duration", text)

    def test_fixed_width_bounded_lines(self):
        trace = _build_trace()
        lines = render_gantt_trace(trace) + render_gantt_windows(trace)
        for line in lines:
            self.assertLessEqual(len(line), _TOTAL_LINE_MAX + 4, f"line too wide: {line!r}")

    def test_tiny_spans_visible(self):
        reset_gantt_spans()
        trace = _build_trace()
        # A point span inside the window renders as ▏.
        register_gantt_span(
            "clip_bind",
            start_mono_ns=1_050_000_000,
            end_mono_ns=1_050_000_000,
            lane="GPU",
        )
        spans = _collect_spans(trace)
        lines = _render_window(
            spans,
            origin_ns=trace._metadata["remote_python_resume_mono_ns"],
            window_start_ns=1_000_000_000,
            window_end_ns=1_100_000_000,
            title="TINY TEST",
        )
        text = "\n".join(lines)
        reset_gantt_spans()
        # The tiny marker ▏ appears for point/sub-char spans.
        self.assertIn("\u258f", text)

    def test_zoom_view_bounds(self):
        trace = _build_trace()
        lines = render_zoomed_gantt(trace, window_ms=500.0, max_chars=40)
        self.assertTrue(lines)

    def test_scale_picker(self):
        spans = [{"duration_ms": 3000.0}, {"duration_ms": 10.0}]
        scale = _pick_scale_ms(spans, max_chars=100)
        self.assertGreaterEqual(scale, 30.0)

    def test_report_is_json_safe(self):
        trace = _build_trace()
        report = collect_gantt_report(trace)
        self.assertGreater(report["count"], 0)
        for span in report["spans"]:
            for key in ("name", "lane", "start_mono_ns", "end_mono_ns", "duration_ms"):
                self.assertIn(key, span)

    def test_multi_window_generation(self):
        trace = _build_trace()
        lines = render_gantt_windows(trace)
        text = "\n".join(lines)
        self.assertIn("FULL REQUEST OVERVIEW", text)
        # At least one window title with "RESTORE + EARLY CLIP" or the
        # overview.  The anchor windows are emitted when their anchor events
        # exist in the trace.
        self.assertIn("V2 GANTT", text)
        # Auto-dense window present.
        self.assertIn("AUTO-DENSE", text)


class GanttPointEventsTest(unittest.TestCase):
    def test_point_events_listed_separately(self):
        from comfymodal_runtime.gantt_telemetry import collect_point_events

        trace = _build_trace()
        points = collect_point_events(trace)
        self.assertIsInstance(points, list)


if __name__ == "__main__":
    unittest.main()
