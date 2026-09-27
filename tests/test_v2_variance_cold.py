"""Focused unit tests for the V2 variance-cold benchmark mode.

Covers:
  * CLI / mode plumbing (`--variance-cold`, `V2_BENCHMARK_MODE=variance_cold`,
    `--variance-pretouch` / `V2_VARIANCE_PRETOUCH`, request-origin diagnostics).
  * Cold-identity validation from request-scoped `remote_method_entry`
    (restore_count==1, request_count==1, non-empty restored_instance_id,
    fresh container identity per run).
  * Percentile / median / p90 / slow-run-rate statistics.
  * Report rendering with synthetic artifacts, including explicit
    "unavailable" (never zero) handling for missing metrics.

These tests never touch Modal or the network; they run entirely locally.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools.benchmark_v2_direct import (
    _identity,
    _resolve_pretouch,
    _run_variance_cold,
    _validate_cold_identity,
    _variance_origin,
    VARIANCE_APP_NAME,
    _report_only_from_dir,
)
from tools.variance_report import (
    build_summary,
    compute_stats,
    extract_run_metrics,
    load_runs_from_dir,
    percentile,
    render_variance_report,
    slow_run_rate,
)


def _cold_identity(
    *,
    instance: str = "inst-1",
    task: str = "ta-1",
    container: str = "mc-1",
    session: str = "cs-1",
    restore_count: Any = 1,
    request_count: Any = 1,
) -> dict[str, Any]:
    return {
        "restored_instance_id": instance,
        "restore_count": restore_count,
        "request_count": request_count,
        "container_task_id": task,
        "modal_container_id": container,
        "container_session_id": session,
    }


def _synthetic_artifact(
    *,
    index: int,
    instance: str,
    task: str,
    restore_count: int = 1,
    request_count: int = 1,
    pretouch: int = 0,
    cold: bool = True,
    wall_ms: float = 30000.0,
    restore_total_ms: float = 1200.0,
    sampling_ms: float | None = 4000.0,
    include_timing: bool = True,
    first_unet_variance: dict[str, Any] | None = None,
    sampler_variance: dict[str, Any] | None = None,
    sampler_ms: float | None = None,
) -> dict[str, Any]:
    identity = _cold_identity(instance=instance, task=task,
                              restore_count=restore_count, request_count=request_count)
    identity.update({
        "app_name": "stable-modal-comfy-v2-variance-shadow",
        "cloud": "CLOUD_PROVIDER_AWS",
        "region": "us-east-2",
        "image_id": "im-1",
        "fingerprint": "fp-1",
        "cpu": 16,
        "runtime_shape": {"thread_policy": "TBASE", "cpu_request": 16},
    })
    pagein = {
        "name": "unet_snapshot_pagein",
        "metadata": {"major_faults": 3, "minor_faults": 40, "duration_ms": 15.0},
    }
    events: list[dict[str, Any]] = [pagein]
    if first_unet_variance is not None:
        events.append({"name": "first_unet_activation_variance",
                       "metadata": dict(first_unet_variance)})
    if sampler_variance is not None:
        events.append({"name": "sampler_variance", "metadata": dict(sampler_variance)})
    result: dict[str, Any] = {
        "trace": {
            "events": events,
            "_restore_timing": {
                "snapshot_restore_ms": 800.0,
                "backend_startup_ms": 200.0,
                "restore_total_ms": restore_total_ms,
            },
        },
        "_restore_timing": {
            "snapshot_restore_ms": 800.0,
            "backend_startup_ms": 200.0,
            "restore_total_ms": restore_total_ms,
        },
    }
    timing: dict[str, Any] = {}
    if include_timing:
        timing = {
            "wall_ms": wall_ms,
            "restore_total_ms": restore_total_ms,
            "sampling_ms": sampling_ms,
            "sampler_node_to_sampler_start_ms": 1500.0,
            "vae_decode_ms": 700.0,
            "output_commit_ms": 250.0,
            "command_to_response_ms": wall_ms + 1000.0,
            "handle_lookup_ms": 3.0,
            "t3b_to_t8_ms": 10000.0,
            "local_timing": {
                "plan_build_ms": 2.0,
                "generator_create_ms": 1.0,
                "first_iteration_to_first_remote_event_ms": 9000.0,
            },
        }
        if sampler_ms is not None:
            timing["sampler_ms"] = sampler_ms
    return {
        "run_index": index,
        "run_id": f"variance-cold-p{pretouch}-{index}-abcd",
        "request_id": f"req-{index}",
        "mode": "variance_cold",
        "start_ts": "2026-08-05T00:00:00.000000+00:00",
        "end_ts": "2026-08-05T00:00:30.000000+00:00",
        "remote_entry_ts": "2026-08-05T00:00:00.500000+00:00",
        "identity": identity,
        "variance": {
            "pretouch": pretouch,
            "cold_valid": cold,
            "cold": cold,
            "failures": [] if cold else ["synthetic not-cold"],
        },
        "timing": timing,
        "result": result,
    }


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# CLI / mode plumbing
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestModePlumbing(unittest.TestCase):
    def test_default_variance_app_name(self):
        self.assertEqual(VARIANCE_APP_NAME, "stable-modal-comfy-v2-variance-shadow")

    def test_variance_origin_carries_diagnostics(self):
        origin = _variance_origin(index=3, pretouch=1, app_name="stable-modal-comfy-v2-variance-shadow")
        self.assertEqual(origin["variance_mode"], "cold")
        self.assertEqual(origin["variance_pretouch"], 1)
        self.assertEqual(origin["COMFYMODAL_V2_UNET_PRETOUCH"], "1")
        self.assertEqual(origin["variance_diagnostics"]["mode"], "variance_cold")
        self.assertEqual(origin["env_profile"], "production")
        self.assertEqual(origin["variance_diagnostics"]["benchmark_app"],
                         "stable-modal-comfy-v2-variance-shadow")

    def test_variance_origin_pretouch_zero(self):
        origin = _variance_origin(index=0, pretouch=0, app_name="app")
        self.assertEqual(origin["variance_pretouch"], 0)
        self.assertEqual(origin["COMFYMODAL_V2_UNET_PRETOUCH"], "0")

    def test_resolve_pretouch_cli_wins(self):
        os.environ["V2_VARIANCE_PRETOUCH"] = "1"
        try:
            self.assertEqual(_resolve_pretouch(0), 0)
            self.assertEqual(_resolve_pretouch(1), 1)
            self.assertEqual(_resolve_pretouch(None), 1)
        finally:
            os.environ.pop("V2_VARIANCE_PRETOUCH", None)

    def test_resolve_pretouch_default_disabled(self):
        os.environ.pop("V2_VARIANCE_PRETOUCH", None)
        self.assertEqual(_resolve_pretouch(None), 0)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Cold identity validation
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestColdIdentityValidation(unittest.TestCase):
    def test_identity_preserves_remote_cold_proof_fields(self):
        result = {
            "trace": {
                "events": [{
                    "name": "remote_method_entry",
                    "metadata": {
                        "method_name": "run_plan_stream",
                        "restore_count": "1",
                        "request_count": "1",
                        "restored_instance_id": "restore-1",
                        "restore_session_id": "session-1",
                        "container_task_id": "task-1",
                        "image_id": "image-1",
                        "cloud": "CLOUD_PROVIDER_AWS",
                        "region": "us-east-2",
                    },
                }],
            },
        }
        identity = _identity(result)
        self.assertEqual(identity["restore_count"], "1")
        self.assertEqual(identity["request_count"], "1")
        self.assertEqual(identity["restored_instance_id"], "restore-1")
        self.assertEqual(identity["container_task_id"], "task-1")
        self.assertEqual(identity["region"], "us-east-2")

    def test_first_run_cold_pass(self):
        result = _validate_cold_identity(
            _cold_identity(), run_index=0, pretouch=0, prev_identity=None)
        self.assertTrue(result["cold_valid"])
        self.assertTrue(result["cold"])
        self.assertEqual(result["failures"], [])

    def test_fresh_instance_second_run_cold(self):
        first = _cold_identity(instance="a", task="ta-a")
        second = _cold_identity(instance="b", task="ta-b")
        result = _validate_cold_identity(
            second, run_index=1, pretouch=0, prev_identity=first)
        self.assertTrue(result["cold_valid"])
        self.assertTrue(result["cold"])
        self.assertTrue(result["freshness_checked"])

    def test_reused_instance_not_cold(self):
        """Same container identity as previous run must NOT be labeled cold."""
        first = _cold_identity(instance="a", task="ta-a")
        same = _cold_identity(instance="a", task="ta-a")
        result = _validate_cold_identity(
            same, run_index=1, pretouch=0, prev_identity=first)
        self.assertFalse(result["cold"])
        self.assertTrue(any("not fresh" in f for f in result["failures"]))

    def test_restore_count_2_fails(self):
        result = _validate_cold_identity(
            _cold_identity(restore_count=2), run_index=0, pretouch=0)
        self.assertFalse(result["cold_valid"])
        self.assertTrue(any("restore_count=2, expected 1" in f for f in result["failures"]))

    def test_request_count_2_fails(self):
        result = _validate_cold_identity(
            _cold_identity(request_count=2), run_index=0, pretouch=0)
        self.assertFalse(result["cold_valid"])
        self.assertTrue(any("request_count=2, expected 1" in f for f in result["failures"]))

    def test_empty_instance_fails(self):
        result = _validate_cold_identity(
            _cold_identity(instance=""), run_index=0, pretouch=0)
        self.assertFalse(result["cold_valid"])
        self.assertTrue(any("restored_instance_id is empty/absent" in f for f in result["failures"]))

    def test_missing_counts_fail_explicitly(self):
        """Absent counts default to -1 and fail explicitly (never pass silently)."""
        identity = {"restored_instance_id": "x"}  # no restore_count / request_count
        result = _validate_cold_identity(identity, run_index=0, pretouch=0)
        self.assertFalse(result["cold_valid"])
        self.assertTrue(any("restore_count=-1, expected 1" in f for f in result["failures"]))
        self.assertTrue(any("request_count=-1, expected 1" in f for f in result["failures"]))


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Statistics
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestStatistics(unittest.TestCase):
    def test_percentile(self):
        self.assertEqual(percentile([], 90), None)
        self.assertEqual(percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50), 5.5)
        self.assertEqual(percentile([1, 2, 3, 4, 5], 90), 4.6)
        self.assertEqual(percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 100), 10)
        self.assertEqual(percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0), 1)

    def test_compute_stats(self):
        stats = compute_stats([1.0, 2.0, 3.0])
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["median"], 2.0)
        self.assertEqual(stats["max"], 3.0)
        self.assertEqual(stats["min"], 1.0)

    def test_compute_stats_empty_is_unavailable(self):
        stats = compute_stats([])
        self.assertEqual(stats["count"], 0)
        self.assertEqual(stats["median"], "unavailable")
        self.assertEqual(stats["p90"], "unavailable")
        self.assertEqual(stats["percentile_method"], "linear_interpolation")

    def test_slow_run_rate(self):
        rate = slow_run_rate([1.0, 2.0, 10.0], threshold_ms=5.0)
        self.assertEqual(rate["count"], 3)
        self.assertEqual(rate["slow_count"], 1)
        self.assertAlmostEqual(rate["rate"], 1 / 3, places=4)

    def test_slow_run_rate_empty(self):
        rate = slow_run_rate([], threshold_ms=5.0)
        self.assertEqual(rate["rate"], "unavailable")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Metric extraction / missing metrics
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestMetricExtraction(unittest.TestCase):
    def test_extract_populated_metrics(self):
        rec = extract_run_metrics(_synthetic_artifact(
            index=0, instance="a", task="ta-a"))
        self.assertEqual(rec["metrics"]["restore"]["restore_total_ms"], 1200.0)
        self.assertEqual(rec["metrics"]["page_traversal"]["major_faults"], 3)
        self.assertEqual(rec["metrics"]["sampler"]["sampling_ms"], 4000.0)
        self.assertEqual(rec["identity"]["provider"], "CLOUD_PROVIDER_AWS")
        self.assertEqual(rec["identity"]["task_id"], "ta-a")

    def test_missing_metrics_never_zero(self):
        rec = extract_run_metrics(_synthetic_artifact(
            index=0, instance="a", task="ta-a", include_timing=False))
        # Missing restore_total_ms -> None (not 0).
        self.assertIsNone(rec["metrics"]["restore"]["restore_total_ms"])
        # No activation event => pretouch effect unavailable (None here, rendered
        # as "unavailable", never zero).
        self.assertIsNone(rec["metrics"]["pretouch"]["pretouch_effect_ms"])
        # Storage registry absent => suppressed to None (not 0).
        self.assertIsNone(rec["metrics"]["storage"]["storage_unique_count"])

    def _fua(self):
        """A valid activation-variance event: a supported CPU storage registry
        proof (unique_storage_count>0) so page-traversal / transfer metrics are
        surfaced (not suppressed by the unsupported-only validity guard)."""
        return {
            "request_id": "req",
            "gate": "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS",
            "page_traversal": {
                "wall_ms": 3100.0, "minor_faults": 42, "major_faults": 3,
                "bytes": 1_200_000_000, "effective_gb_per_s": 1.1,
                "process_cpu_ms": 900.0, "thread_cpu_ms": 850.0,
            },
            "cpu_to_gpu_transfer": {
                "wall_ms": 640.0, "minor_faults": 2, "major_faults": 0,
                "bytes": 1_000_000_000, "effective_gb_per_s": 1.6,
                "process_cpu_ms": 210.0, "thread_cpu_ms": 200.0,
            },
            "loader_reconciliation": {
                "loader_wall_ms": 3740.0, "residual_ms": 0.0,
                "reconciliation_status": "complete",
            },
            "patcher_bookkeeping_ms": 88.0,
            "patcher_bookkeeping_counts": {"patch_weight_count": 120, "cast_count": 45},
            "unet_storage_registry": {"unique_storage_count": 3, "raw_byte_count": 9000,
                                      "unsupported_count": 0},
        }

    def test_extract_first_unet_activation_variance(self):
        rec = extract_run_metrics(_synthetic_artifact(
            index=0, instance="a", task="ta-a", first_unet_variance=self._fua()))
        pt = rec["metrics"]["page_traversal"]
        tr = rec["metrics"]["transfer"]
        bk = rec["metrics"]["bookkeeping"]
        # CPU page traversal sub-stage.
        self.assertEqual(pt["cpu_page_traversal_wall_ms"], 3100.0)
        self.assertEqual(pt["cpu_page_traversal_minor_faults"], 42)
        self.assertEqual(pt["cpu_page_traversal_major_faults"], 3)
        self.assertEqual(pt["cpu_page_traversal_bytes"], 1_200_000_000)
        self.assertEqual(pt["cpu_page_traversal_gb_per_s"], 1.1)
        self.assertEqual(pt["cpu_page_traversal_process_cpu_ms"], 900.0)
        self.assertEqual(pt["cpu_page_traversal_thread_cpu_ms"], 850.0)
        # CPU→GPU transfer equivalents.
        self.assertEqual(pt["cpu_to_gpu_transfer_wall_ms"], 640.0)
        self.assertEqual(pt["cpu_to_gpu_transfer_minor_faults"], 2)
        self.assertEqual(pt["cpu_to_gpu_transfer_gb_per_s"], 1.6)
        self.assertEqual(pt["cpu_to_gpu_transfer_process_cpu_ms"], 210.0)
        # Transfer throughput surfaces in the transfer category too.
        self.assertEqual(tr["cpu_to_gpu_transfer_wall_ms"], 640.0)
        self.assertEqual(tr["cpu_to_gpu_transfer_bytes"], 1_000_000_000)
        self.assertEqual(tr["cpu_to_gpu_transfer_gb_per_s"], 1.6)
        # Patcher bookkeeping duration + counts.
        self.assertEqual(bk["patcher_bookkeeping_ms"], 88.0)
        self.assertEqual(bk["patch_weight_count"], 120)
        self.assertEqual(bk["cast_count"], 45)

    def test_first_unet_activation_variance_absent_is_unavailable(self):
        rec = extract_run_metrics(_synthetic_artifact(index=0, instance="a", task="ta-a"))
        pt = rec["metrics"]["page_traversal"]
        bk = rec["metrics"]["bookkeeping"]
        self.assertIsNone(pt["cpu_page_traversal_wall_ms"])
        self.assertIsNone(pt["cpu_to_gpu_transfer_wall_ms"])
        self.assertIsNone(bk["patcher_bookkeeping_ms"])
        self.assertIsNone(bk["patch_weight_count"])
        self.assertIsNone(bk["cast_count"])

    def test_sampler_ms_fallback_when_sampling_ms_absent(self):
        """sampler_ms is accepted as the sampling fallback when sampling_ms
        is not present; the source label reflects which field was used."""
        rec = extract_run_metrics(_synthetic_artifact(
            index=0, instance="a", task="ta-a",
            sampling_ms=None,  # omit sampling_ms so the fallback applies
            sampler_variance={
                "activation_wait_ms": 300.0,
                "activation_wait_source": "early_activation_join",
                "wall_ms": 4100.0,
            },
            sampler_ms=4050.0,
        ))
        s = rec["metrics"]["sampler"]
        self.assertEqual(s["sampling_ms"], 4050.0)
        self.assertEqual(s["sampling_source"], "sampler_ms")
        self.assertEqual(s["activation_wait_source"], "early_activation_join")
        self.assertEqual(s["activation_wait_ms"], 300.0)

    def test_sampling_ms_preferred_over_sampler_ms(self):
        rec = extract_run_metrics(_synthetic_artifact(
            index=0, instance="a", task="ta-a", sampler_ms=4050.0))
        s = rec["metrics"]["sampler"]
        self.assertEqual(s["sampling_ms"], 4000.0)  # sampling_ms wins
        self.assertEqual(s["sampling_source"], "sampling_ms")

    def test_activation_wait_source_unavailable_when_missing(self):
        rec = extract_run_metrics(_synthetic_artifact(index=0, instance="a", task="ta-a"))
        self.assertEqual(rec["metrics"]["sampler"]["activation_wait_source"], "unavailable")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Report rendering
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestReportRendering(unittest.TestCase):
    def _write_dir(self, artifacts: list[dict[str, Any]]) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="v2var_"))
        for a in artifacts:
            (tmp / f"run_{a['run_index']}.json").write_text(
                json.dumps(a, default=str), encoding="utf-8")
        return tmp

    def test_summary_and_report_render(self):
        artifacts = [
            _synthetic_artifact(index=0, instance="a", task="ta-a", cold=True, wall_ms=28000.0),
            _synthetic_artifact(index=1, instance="b", task="ta-b", cold=True, wall_ms=33000.0),
        ]
        tmp = self._write_dir(artifacts)
        records = load_runs_from_dir(tmp)
        self.assertEqual(len(records), 2)
        summary = build_summary(records, meta={
            "mode": "variance_cold", "pretouch": 0,
            "gap_seconds": 25, "run_count": 2,
        })
        self.assertEqual(summary["cold_count"], 2)
        self.assertEqual(summary["run_count"], 2)
        self.assertIn("wall_ms", summary["summary_stats"])
        # Median wall ~30000 (28000, 33000) -> 28000 is median (nearest rank).
        self.assertIsNotNone(summary["summary_stats"]["wall_ms"]["median"])

        md = render_variance_report(summary)
        self.assertIn("V2 Variance-Cold Benchmark Report", md)
        self.assertIn("Best-supported root cause", md)
        self.assertIn("Pretouch", md)
        # Missing pretouch_effect must be rendered as unavailable, never 0.
        self.assertIn("unavailable", md)

    def test_report_includes_transfer_throughput_and_bookkeeping(self):
        fua = {
            "request_id": "req", "gate": "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS",
            "page_traversal": {"wall_ms": 3100.0, "minor_faults": 42, "major_faults": 3,
                               "bytes": 1_200_000_000, "effective_gb_per_s": 1.1},
            "cpu_to_gpu_transfer": {"wall_ms": 640.0, "minor_faults": 2, "major_faults": 0,
                                    "bytes": 1_000_000_000, "effective_gb_per_s": 1.6},
            "loader_reconciliation": {"loader_wall_ms": 3740.0, "residual_ms": 0.0,
                                      "reconciliation_status": "complete"},
            "patcher_bookkeeping_ms": 88.0,
            "patcher_bookkeeping_counts": {"patch_weight_count": 120, "cast_count": 45},
            "unet_storage_registry": {"unique_storage_count": 3, "raw_byte_count": 9000,
                                      "unsupported_count": 0},
        }
        sampler_variance = {"activation_wait_ms": 300.0,
                            "activation_wait_source": "early_activation_join", "wall_ms": 4100.0}
        artifacts = [
            _synthetic_artifact(index=0, instance="a", task="ta-a", cold=True,
                                first_unet_variance=fua, sampler_variance=sampler_variance),
        ]
        tmp = self._write_dir(artifacts)
        summary = _report_only_from_dir(tmp)
        records = summary["runs"]
        tr = records[0]["metrics"]["transfer"]
        bk = records[0]["metrics"]["bookkeeping"]
        # Transfer throughput and bookkeeping duration are non-unavailable.
        self.assertEqual(tr["cpu_to_gpu_transfer_gb_per_s"], 1.6)
        self.assertEqual(bk["patcher_bookkeeping_ms"], 88.0)

        md = render_variance_report(summary)
        # Category tables surface transfer throughput + bookkeeping duration rows.
        self.assertIn("cpu_to_gpu_transfer_gb_per_s", md)
        self.assertIn("patcher_bookkeeping_ms", md)
        self.assertIn("patch_weight_count", md)
        self.assertIn("cast_count", md)
        # Activation-wait-source labels section appears.
        self.assertIn("Sampler activation-wait source labels", md)
        self.assertIn("early_activation_join", md)

    def test_report_only_from_dir_writes_files(self):
        artifacts = [
            _synthetic_artifact(index=0, instance="a", task="ta-a", cold=True),
            _synthetic_artifact(index=1, instance="b", task="ta-b", cold=True),
        ]
        tmp = self._write_dir(artifacts)
        summary = _report_only_from_dir(tmp)
        self.assertEqual(summary["cold_count"], 2)
        self.assertTrue((tmp / "summary.json").exists())
        self.assertTrue((tmp / "variance_cold_report.md").exists())
        report_text = (tmp / "variance_cold_report.md").read_text(encoding="utf-8")
        self.assertIn("Best-supported root cause", report_text)

    def test_warm_runs_are_not_cold_in_summary(self):
        artifacts = [
            _synthetic_artifact(index=0, instance="a", task="ta-a", cold=True),
            _synthetic_artifact(index=1, instance="a", task="ta-a", cold=False),
        ]
        tmp = self._write_dir(artifacts)
        records = load_runs_from_dir(tmp)
        summary = build_summary(records, meta={"mode": "variance_cold"})
        self.assertEqual(summary["cold_count"], 1)
        self.assertEqual(summary["warm_or_invalid_count"], 1)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Variance-cold sequence (with injected fake runner â€” no Modal)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class TestVarianceColdSequence(unittest.TestCase):
    """Exercise ``_run_variance_cold`` end-to-end with a fake ``_runner`` so
    no Modal/network is needed.  Verifies artifact writing, variance-origin
    propagation, warm-reuse rejection, and summary/report generation."""

    def _make_fake_runner(self, instances: list[tuple[str, str]]):
        """Return an async fake _runner yielding a synthetic artifact whose
        identity uses per-index (instance, task) from *instances*."""
        captured_origins: list[dict[str, Any]] = []

        async def fake(index, workflow, modal_options, workspace, transport,
                       output_dir, _extra_origin=None, _defer_waterfall=True, **kwargs):
            origin = dict(_extra_origin or {})
            captured_origins.append(origin)
            instance, task = instances[index % len(instances)]
            return _synthetic_artifact(
                index=index, instance=instance, task=task,
                pretouch=int(origin.get("variance_pretouch", 0)),
                cold=True, wall_ms=28000.0 + index * 1000.0,
            )

        return fake, captured_origins

    def _dummy_transport(self):
        class _Dummy:  # fake transport; never used by the injected runner
            pass
        return _Dummy()

    def test_all_cold_writes_artifacts_and_report(self):
        tmp = Path(tempfile.mkdtemp(prefix="v2varseq_"))
        fake, origins = self._make_fake_runner([("a", "ta-a"), ("b", "ta-b")])

        async def go():
            return await _run_variance_cold(
                workflow={}, modal_options={}, workspace={}, transport=self._dummy_transport(),
                output_dir=tmp, run_count=2, gap_seconds=0.0, pretouch=1,
                app_name="stable-modal-comfy-v2-variance-shadow",
                class_name="ModalRuntimeEntrypointV2", gpu="rtx-pro-6000",
                _runner=fake,
            )

        summary = asyncio.run(go())
        self.assertEqual(summary["cold_count"], 2)
        self.assertEqual(summary["run_count"], 2)
        self.assertTrue((tmp / "run_0.json").exists())
        self.assertTrue((tmp / "run_1.json").exists())
        self.assertTrue((tmp / "summary.json").exists())
        self.assertTrue((tmp / "variance_cold_report.md").exists())
        # Variance-origin diagnostics were carried for every run.
        self.assertEqual(len(origins), 2)
        for origin in origins:
            self.assertEqual(origin["variance_mode"], "cold")
            self.assertEqual(origin["variance_pretouch"], 1)
            self.assertEqual(origin["COMFYMODAL_V2_UNET_PRETOUCH"], "1")
            self.assertEqual(origin["variance_diagnostics"]["benchmark_app"],
                             "stable-modal-comfy-v2-variance-shadow")

    def test_warm_reuse_rejected_and_runs_preserved(self):
        """A reused container identity must not be labeled cold; the sequence
        must raise (so the runner cannot silently claim cold evidence)."""
        tmp = Path(tempfile.mkdtemp(prefix="v2varseq_"))
        # Same identity both runs -> second run is not fresh.
        fake, _origins = self._make_fake_runner([("a", "ta-a"), ("a", "ta-a")])

        async def go():
            return await _run_variance_cold(
                workflow={}, modal_options={}, workspace={}, transport=self._dummy_transport(),
                output_dir=tmp, run_count=2, gap_seconds=0.0, pretouch=0,
                app_name="app", class_name="c", gpu="g", _runner=fake,
            )

        with self.assertRaises(RuntimeError):
            asyncio.run(go())
        # Failed/warm runs are preserved in artifacts.
        self.assertTrue((tmp / "run_0.json").exists())
        self.assertTrue((tmp / "run_1.json").exists())
        summary_json = json.loads((tmp / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary_json["cold_count"], 1)
        self.assertEqual(summary_json["warm_or_invalid_count"], 1)


if __name__ == "__main__":
    unittest.main()
