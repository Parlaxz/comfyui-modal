"""Focused tests for comfymodal_runtime.resource_telemetry.

Synthetic cgroup v2 files are written to a temp dir so the sampler runs
against deterministic counters; stage attribution and the windowed CPU
peaks are asserted end to end.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from comfymodal_runtime.resource_telemetry import (
    ResourceTelemetry,
    build_stage_boundaries,
    percentile,
    telemetry_enabled,
)


def _write_cgroup(root: Path, usage_usec: int, current: int, peak: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "cpu.stat").write_text(
        f"usage_usec {usage_usec}\nuser_usec {usage_usec // 2}\n"
        f"system_usec {usage_usec // 2}\nnr_periods 0\nnr_throttled 0\n"
        f"throttled_usec 0\n",
        encoding="utf-8",
    )
    (root / "memory.current").write_text(str(current), encoding="utf-8")
    (root / "memory.peak").write_text(str(peak), encoding="utf-8")


class TelemetryAggregationTests(unittest.TestCase):
    def test_percentile(self):
        self.assertEqual(percentile([1, 2, 3, 4], 50.0), 2)
        self.assertEqual(percentile([1], 95.0), 1)
        self.assertIsNone(percentile([], 95.0))

    def test_fails_closed_without_cgroup(self):
        tel = ResourceTelemetry(interval_ms=50, cgroup_root="C:/nonexistent-cgroup")
        tel.start()
        summary = tel.summarize()
        self.assertEqual(summary["status"], "unavailable")

    def test_aggregates_known_counters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # 10 samples, 50 ms apart, 8 cores busy -> 400k usec per 50ms
            tel = ResourceTelemetry(interval_ms=50, cgroup_root=str(root))
            usage = 0
            now = time.time_ns()
            samples = []
            for i in range(10):
                usage += 400_000
                _write_cgroup(root, usage, current=1_000_000_000 + i, peak=2_000_000_000)
                wall = now + i * 50_000_000
                sample = {
                    "wall_ns": wall,
                    "mono_ns": wall,
                    "usage_usec": usage,
                    "user_usec": usage // 2,
                    "system_usec": usage // 2,
                    "mem_current": 1_000_000_000 + i,
                    "mem_peak": 2_000_000_000,
                }
                samples.append(sample)
            tel._status = "measured"
            tel._samples = samples
            summary = tel.summarize()
            self.assertEqual(summary["status"], "measured")
            self.assertEqual(summary["samples"], 10)
            self.assertEqual(summary["ram"]["cgroup_peak_bytes"], 2_000_000_000)
            self.assertEqual(summary["ram"]["sampled_peak_bytes"], 1_000_000_009)
            self.assertEqual(summary["ram"]["p95_bytes"], 1_000_000_009)
            # 400k usec per 50 ms = 8 cores
            self.assertAlmostEqual(summary["cpu"]["average_cores"], 8.0, places=2)
            self.assertGreaterEqual(summary["cpu"]["peak_cores"], 8.0)
            self.assertAlmostEqual(
                summary["cpu"]["peak_cores_over_window_ms"]["50"], 8.0, places=1,
            )

    def test_stage_attribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tel = ResourceTelemetry(interval_ms=50, cgroup_root=str(root))
            usage = 0
            now = time.time_ns()
            samples = []
            # 2 samples bootstrap (1 core), 2 samples sampling (8 cores)
            for i in range(4):
                cores = 1 if i < 2 else 8
                usage += cores * 50_000  # 50 ms of `cores` cores
                _write_cgroup(root, usage, current=1_000_000_000, peak=1_000_000_000)
                samples.append({
                    "wall_ns": now + i * 50_000_000,
                    "mono_ns": now + i * 50_000_000,
                    "usage_usec": usage,
                    "user_usec": usage,
                    "system_usec": 0,
                    "mem_current": 1_000_000_000,
                    "mem_peak": 1_000_000_000,
                })
            tel._status = "measured"
            tel._samples = samples
            boundaries = {
                "bootstrap_setup": {
                    "start_unix_ns": samples[0]["wall_ns"],
                    "end_unix_ns": samples[2]["wall_ns"],
                },
                "sampling": {
                    "start_unix_ns": samples[2]["wall_ns"],
                    "end_unix_ns": samples[3]["wall_ns"] + 1,
                },
            }
            summary = tel.summarize(boundaries)
            stages = summary["stages"]
            self.assertIn("bootstrap_setup", stages)
            self.assertIn("sampling", stages)
            self.assertAlmostEqual(stages["bootstrap_setup"]["average_cores"], 1.0, places=2)
            self.assertAlmostEqual(stages["sampling"]["average_cores"], 8.0, places=2)
            self.assertEqual(stages["bootstrap_setup"]["samples"], 2)

    def test_build_stage_boundaries_from_events(self):
        base = 1_000_000_000_000
        ms = 1_000_000  # ns per ms
        events = [
            {"name": "run_plan_method_first_line", "wall_unix_ns": base + 100 * ms},
            {"name": "prompt_executor_invoke_start", "wall_unix_ns": base + 500 * ms},
            {"name": "sampler_lane_wait_start", "wall_unix_ns": base + 1000 * ms},
            {"name": "sampler_lane_wait_end", "wall_unix_ns": base + 1500 * ms},
            {"name": "sampler_start", "wall_unix_ns": base + 1600 * ms},
            {"name": "sampler_end", "wall_unix_ns": base + 3600 * ms},
            {"name": "vae_decode_start", "wall_unix_ns": base + 3700 * ms},
            {"name": "vae_decode_end", "wall_unix_ns": base + 4200 * ms},
            {"name": "output_collect_start", "wall_unix_ns": base + 4300 * ms},
            {"name": "remote_return_start", "wall_unix_ns": base + 4400 * ms},
        ]
        restore = {"remote_python_resume_wall_unix_ns": base}
        bounds = build_stage_boundaries(events, restore)
        self.assertIn("python_resume", bounds)
        self.assertIn("bootstrap_setup", bounds)
        self.assertIn("clip_graph_preparation", bounds)
        self.assertIn("two_lane_activation", bounds)
        self.assertIn("sampler_preparation", bounds)
        self.assertIn("sampling", bounds)
        self.assertIn("vae", bounds)
        self.assertIn("output_result", bounds)
        self.assertEqual(bounds["two_lane_activation"]["start_unix_ns"], base + 1000 * ms)
        self.assertEqual(bounds["two_lane_activation"]["end_unix_ns"], base + 1500 * ms)
        self.assertEqual(
            bounds["sampling"]["end_unix_ns"] - bounds["sampling"]["start_unix_ns"],
            2_000_000_000,
        )

    def test_enabled_flag(self):
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_RESOURCE_TELEMETRY": "1"}):
            self.assertTrue(telemetry_enabled())
        with mock.patch.dict(os.environ, {"COMFYMODAL_V2_RESOURCE_TELEMETRY": "0"}):
            self.assertFalse(telemetry_enabled())
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(telemetry_enabled())


if __name__ == "__main__":
    unittest.main()
