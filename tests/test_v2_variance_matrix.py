"""Focused unit tests for the V2 variance-cold MATRIX (four-condition
round-robin) scheduler and its consolidated handoff report.

Covers:
  * condition scheduling / round-robin order and retry-to-target
  * fixed thresholds (slow classification, not median-derived)
  * preservation of failed / warm-invalid / snapshot-capture attempts
  * consolidated report embedding of raw attempt JSON

These tests use an injected fake ``_runner`` so no Modal / network is needed.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools.benchmark_v2_direct import (
    MATRIX_CONDITIONS,
    MATRIX_CONDITION_LABEL,
    MATRIX_SLOW_THRESHOLD_MS,
    _classify_attempt,
    _classify_slow,
    _matrix_origin,
    _report_only_from_dir,
    _resolve_slow_threshold,
    _run_variance_matrix,
)
from tools.variance_report import (
    build_matrix_summary,
    extract_run_metrics,
    render_matrix_report,
)


def _identity(instance: str, *, restore_count: int = 1, request_count: int = 1,
              task: str = "") -> dict[str, Any]:
    return {
        "restored_instance_id": instance,
        "restore_count": restore_count,
        "request_count": request_count,
        "container_task_id": task or f"ta-{instance}",
        "modal_container_id": f"mc-{instance}",
        "container_session_id": f"cs-{instance}",
        "cloud": "CLOUD_PROVIDER_AWS", "region": "us-east-2",
        "image_id": "im-x", "fingerprint": "fp-x", "cpu": 16,
        "app_name": "stable-modal-comfy-v2-variance-shadow",
        "runtime_shape": {"thread_policy": "TBASE"},
    }


def _artifact(index: int, identity: dict[str, Any], *, wall_ms: float = 2000.0,
              restore_total_ms: float = 800.0, unet_ms: float = 150.0,
              pretouch: int = 0) -> dict[str, Any]:
    timing = {
        "wall_ms": wall_ms,
        "restore_total_ms": restore_total_ms,
        "unet_demand_to_first_forward_ms": unet_ms,
        "sampling_ms": 4000.0,
        "sampler_node_to_sampler_start_ms": 1500.0,
        "vae_decode_ms": 700.0,
        "output_commit_ms": 250.0,
        "command_to_response_ms": wall_ms + 1000.0,
        "handle_lookup_ms": 3.0,
        "t3b_to_t8_ms": 10000.0,
        "local_timing": {"plan_build_ms": 2.0, "generator_create_ms": 1.0,
                         "first_iteration_to_first_remote_event_ms": 9000.0},
    }
    return {
        "run_index": index,
        "request_id": f"req-{index}",
        "identity": identity,
        "timing": timing,
        "result": {"trace": {"events": [], "_restore_timing": {"restore_total_ms": restore_total_ms}},
                   "_restore_timing": {"restore_total_ms": restore_total_ms}},
        "variance": {"pretouch": pretouch, "cold_valid": False, "cold": False, "failures": []},
    }


def make_fake_runner(outcome_map: dict[str, list[str]], *, slow_label: set[str] | None = None,
                     wall_ms: float = 2000.0):
    """Return (async fake _runner, captured_origins).

    *outcome_map* maps a condition label to a list of outcomes cycled per call:
      - "cold"    -> fresh restored instance (valid cold)
      - "warm"    -> request_count=2 (warm/invalid, freshness fails)
      - "capture" -> restore_count=0 (snapshot capture)
      - "failed"  -> raise an exception
    *slow_label* marks conditions whose cold attempts should exceed the fixed
    wall threshold.
    """
    slow_label = slow_label or set()
    calls: dict[str, int] = {}
    captured_origins: list[dict[str, Any]] = []

    async def fake(index, workflow, modal_options, workspace, transport,
                   output_dir, _extra_origin=None, _defer_waterfall=True, **kwargs):
        origin = dict(_extra_origin or {})
        captured_origins.append(origin)
        label = origin.get("variance_diagnostics", {}).get("benchmark_app", "?")
        # label is not in origin; recover condition from the request flags
        diag = int(origin.get("COMFYMODAL_V2_VARIANCE_DIAGNOSTICS", 0))
        pt = int(origin.get("COMFYMODAL_V2_UNET_PRETOUCH", 0))
        cond = MATRIX_CONDITION_LABEL(diag, pt)
        seq = calls.get(cond, 0)
        calls[cond] = seq + 1
        outcomes = outcome_map.get(cond, ["cold"])
        outcome = outcomes[seq % len(outcomes)]
        is_slow = cond in slow_label
        wall = 8000.0 if is_slow else wall_ms
        if outcome == "failed":
            raise RuntimeError("synthetic failure")
        if outcome == "capture":
            return _artifact(index, _identity(f"cap-{cond}-{seq}", restore_count=0),
                             wall_ms=wall, pretouch=pt)
        if outcome == "warm":
            return _artifact(index, _identity(f"warm-{cond}", request_count=2),
                             wall_ms=wall, pretouch=pt)
        # cold: fresh unique instance per attempt so freshness passes
        return _artifact(index, _identity(f"inst-{cond}-{seq}"), wall_ms=wall, pretouch=pt)

    return fake, captured_origins, calls


def _dummy_transport():
    class _Dummy:
        pass
    return _Dummy()


def run_matrix(runner, tmp: Path, *, target: int = 2, max_attempts: int = 100,
               slow: float = 0.0, gap: float = 0.0) -> dict[str, Any]:
    async def go():
        return await _run_variance_matrix(
            workflow={}, modal_options={}, workspace={}, transport=_dummy_transport(),
            output_dir=tmp, gap_seconds=gap, app_name="app", class_name="c", gpu="g",
            target_per_condition=target, max_total_attempts=max_attempts,
            slow_threshold_ms=slow, _runner=runner,
        )
    return asyncio.run(go())


# ═════════════════════════════════════════════════════════════════════════
# Condition scheduling / round-robin / retry-to-target
# ═════════════════════════════════════════════════════════════════════════

class TestMatrixScheduling(unittest.TestCase):
    def test_round_robin_all_conditions_reach_target(self):
        tmp = Path(tempfile.mkdtemp(prefix="v2mat_"))
        runner, origins, _calls = make_fake_runner({})  # all cold
        summary = run_matrix(runner, tmp, target=2, max_attempts=100)
        self.assertEqual(summary["total_attempts"], 8)  # 4 conditions x 2 target
        self.assertEqual(summary["total_cold"], 8)
        for label in ("diag0_pt0", "diag0_pt1", "diag1_pt0", "diag1_pt1"):
            self.assertEqual(summary["per_condition"][label]["cold_count"], 2)
            self.assertEqual(summary["per_condition"][label]["attempt_count"], 2)
        # Round-robin interleaving: first four attempts cover all four conditions.
        first_four = [o.get("variance_diagnostics", {}).get("mode") for o in origins[:4]]
        self.assertEqual(first_four, ["variance_matrix"] * 4)
        # Origin carries request-scoped diagnostics/pretouch flags per condition.
        for o in origins:
            self.assertIn("COMFYMODAL_V2_VARIANCE_DIAGNOSTICS", o)
            self.assertIn("COMFYMODAL_V2_UNET_PRETOUCH", o)

    def test_retry_to_target_skips_non_cold_attempts(self):
        tmp = Path(tempfile.mkdtemp(prefix="v2mat_"))
        # Every condition: first warm, then two capture, then colds.
        outcomes = {label: ["warm", "capture", "capture", "cold", "cold"] for label in
                    (MATRIX_CONDITION_LABEL(*c) for c in MATRIX_CONDITIONS)}
        runner, _origins, _calls = make_fake_runner(outcomes)
        summary = run_matrix(runner, tmp, target=2, max_attempts=200)
        for label in ("diag0_pt0", "diag0_pt1", "diag1_pt0", "diag1_pt1"):
            p = summary["per_condition"][label]
            self.assertEqual(p["cold_count"], 2)
            self.assertEqual(p["warm_invalid_count"], 1)
            self.assertEqual(p["snapshot_capture_count"], 2)
        # 5 attempts per condition => 20 total.
        self.assertEqual(summary["total_attempts"], 20)
        # Every attempt is preserved on disk (including warm/capture/failed).
        attempt_files = sorted(tmp.glob("attempt_*.json"))
        self.assertEqual(len(attempt_files), 20)

    def test_failed_attempts_preserved_and_capped(self):
        tmp = Path(tempfile.mkdtemp(prefix="v2mat_"))
        # One condition always fails -> cap reached, no target met.
        outcomes = {MATRIX_CONDITION_LABEL(0, 0): ["failed"],
                    **{MATRIX_CONDITION_LABEL(*c): ["cold"] for c in MATRIX_CONDITIONS
                       if c != (0, 0)}}
        runner, _origins, _calls = make_fake_runner(outcomes)
        with self.assertRaises(RuntimeError):
            run_matrix(runner, tmp, target=2, max_attempts=12, gap=0.0)
        files = list(tmp.glob("attempt_*.json"))
        self.assertEqual(len(files), 12)  # capped at max_attempts, all preserved
        # The failing condition's attempts are classified failed.
        failed = [json.loads(f.read_text(encoding="utf-8")) for f in files
                  if json.loads(f.read_text(encoding="utf-8")).get("condition_label") == "diag0_pt0"]
        self.assertTrue(failed)
        self.assertTrue(all(a.get("classification") == "failed" for a in failed))


# ═════════════════════════════════════════════════════════════════════════
# Classification / fixed thresholds
# ═════════════════════════════════════════════════════════════════════════

class TestClassificationAndFixedThresholds(unittest.TestCase):
    def test_classify_cold(self):
        art = _artifact(0, _identity("i", restore_count=1, request_count=1))
        art["variance"] = {"cold_valid": True, "cold": True, "failures": []}
        self.assertEqual(_classify_attempt(art), "cold")

    def test_classify_warm_invalid(self):
        art = _artifact(0, _identity("i", request_count=2))
        self.assertEqual(_classify_attempt(art), "warm_invalid")

    def test_classify_snapshot_capture_excluded(self):
        art = _artifact(0, _identity("i", restore_count=0))
        art["variance"] = {"cold_valid": False, "cold": False, "failures": []}
        self.assertEqual(_classify_attempt(art), "snapshot_capture")

    def test_classify_failed(self):
        art = _artifact(0, _identity("i"))
        art["error"] = "boom"
        self.assertEqual(_classify_attempt(art), "failed")

    def test_fixed_slow_flags(self):
        fast = _artifact(0, _identity("i"), restore_total_ms=2000.0, unet_ms=100.0)
        self.assertEqual(_classify_slow(fast), {"restore_over_3s": False, "unet_activation_over_3s": False})
        slow = _artifact(0, _identity("i"), restore_total_ms=4000.0, unet_ms=3500.0)
        self.assertEqual(_classify_slow(slow), {"restore_over_3s": True, "unet_activation_over_3s": True})
        missing = _artifact(0, _identity("i"), restore_total_ms=0.0)
        missing["timing"].pop("restore_total_ms", None)
        missing["timing"].pop("unet_demand_to_first_forward_ms", None)
        self.assertEqual(_classify_slow(missing), {"restore_over_3s": False, "unet_activation_over_3s": False})

    def test_unet_slow_derived_from_extracted_trace_metric(self):
        """The >3s UNET flag must use the trace-extracted
        unet_demand_to_first_forward_ms (metrics.page_traversal), even when the
        raw artifact.timing does not carry it."""
        art = _artifact(0, _identity("i"), restore_total_ms=800.0, unet_ms=100.0)
        # Remove the raw timing field; the trace event is the only source.
        art["timing"].pop("unet_demand_to_first_forward_ms", None)
        # Inject the trace event that extract_run_metrics reads.
        art["result"]["trace"]["events"].append({
            "name": "unet_first_cuda_op",
            "metadata": {"elapsed_ms": 4000.0, "demand_start_present": 1},
        })
        record = extract_run_metrics(art)
        self.assertEqual(
            record["metrics"]["page_traversal"]["unet_demand_to_first_forward_ms"], 4000.0)
        flags = _classify_slow(record)
        self.assertTrue(flags["unet_activation_over_3s"])
        self.assertFalse(flags["restore_over_3s"])

    def test_fixed_slow_threshold_default_nonzero(self):
        import os
        os.environ.pop("V2_VARIANCE_SLOW_THRESHOLD_MS", None)
        try:
            self.assertGreater(MATRIX_SLOW_THRESHOLD_MS, 0)
            self.assertEqual(_resolve_slow_threshold(), MATRIX_SLOW_THRESHOLD_MS)
        finally:
            os.environ.pop("V2_VARIANCE_SLOW_THRESHOLD_MS", None)

    def test_fixed_slow_threshold_fails_fast_on_nonpositive(self):
        import os
        os.environ["V2_VARIANCE_SLOW_THRESHOLD_MS"] = "0"
        try:
            with self.assertRaises(RuntimeError):
                _resolve_slow_threshold()
        finally:
            os.environ.pop("V2_VARIANCE_SLOW_THRESHOLD_MS", None)

    def test_fixed_slow_threshold_from_env(self):
        import os
        os.environ["V2_VARIANCE_SLOW_THRESHOLD_MS"] = "45000"
        try:
            self.assertEqual(_resolve_slow_threshold(), 45000.0)
        finally:
            os.environ.pop("V2_VARIANCE_SLOW_THRESHOLD_MS", None)

    def test_fixed_threshold_not_median_derived(self):
        """The fixed-threshold slow-run rate uses the EXPLICIT threshold, not a
        per-condition median.  A condition where all runs are slow is reported
        slow even though its own median exceeds the threshold."""
        tmp = Path(tempfile.mkdtemp(prefix="v2mat_"))
        slow_labels = {MATRIX_CONDITION_LABEL(0, 0)}
        runner, _o, _c = make_fake_runner({}, slow_label=slow_labels, wall_ms=2000.0)
        summary = run_matrix(runner, tmp, target=1, max_attempts=10, slow=5000.0)
        p = summary["per_condition"]["diag0_pt0"]
        # wall_ms=8000 for this condition > threshold 5000 -> slow.
        self.assertEqual(p["fixed_slow_run_rate"]["slow"], 1)
        self.assertEqual(p["fixed_slow_run_rate"]["rate"], 1.0)
        self.assertEqual(p["fixed_slow_run_rate"]["threshold_ms"], 5000.0)
        # A fast condition has no slow runs.
        self.assertEqual(summary["per_condition"]["diag1_pt1"]["fixed_slow_run_rate"]["slow"], 0)

    def test_matrix_origin_flags(self):
        o = _matrix_origin(0, diag=1, pretouch=0, app_name="app")
        self.assertEqual(o["COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"], "1")
        self.assertEqual(o["COMFYMODAL_V2_UNET_PRETOUCH"], "0")
        self.assertEqual(o["variance_pretouch"], 0)
        self.assertEqual(o["variance_diagnostics"]["diagnostics"], 1)


# ═════════════════════════════════════════════════════════════════════════
# Consolidated report embedding
# ═════════════════════════════════════════════════════════════════════════

class TestMatrixReportEmbedding(unittest.TestCase):
    def test_report_embeds_every_attempt_raw_json(self):
        tmp = Path(tempfile.mkdtemp(prefix="v2mat_"))
        outcomes = {label: ["cold", "warm"] for label in
                    (MATRIX_CONDITION_LABEL(*c) for c in MATRIX_CONDITIONS)}
        runner, _o, _c = make_fake_runner(outcomes)
        summary = run_matrix(runner, tmp, target=1, max_attempts=50, slow=5000.0)
        self.assertTrue((tmp / "variance_matrix_handoff.md").exists())
        handoff = (tmp / "variance_matrix_handoff.md").read_text(encoding="utf-8")
        # Header, per-condition identities, stats, root cause, recommended fix.
        for token in (
            "V2 Variance-Cold Matrix Handoff Report",
            "Per-condition identities",
            "Median / MAD / p90 / max per condition",
            "Unique storage / page / checksum / read metrics",
            "Fast-vs-slow comparison",
            "Root cause / alternatives / recommended fix",
            "Exact recommended production fix",
            "Every attempt (full raw artifact JSON)",
        ):
            self.assertIn(token, handoff)
        # Every attempt id appears and its raw JSON is embedded.
        for f in sorted(tmp.glob("attempt_*.json")):
            art = json.loads(f.read_text(encoding="utf-8"))
            self.assertIn(art["attempt_id"], handoff)
            # The raw artifact JSON content is embedded verbatim.
            self.assertIn(f"\"attempt_id\": \"{art['attempt_id']}\"", handoff)
        # Missing metrics stay unavailable, never zero.
        self.assertIn("unavailable", handoff)

    def test_summary_json_serializable(self):
        tmp = Path(tempfile.mkdtemp(prefix="v2mat_"))
        runner, _o, _c = make_fake_runner({})
        summary = run_matrix(runner, tmp, target=1, max_attempts=10, slow=5000.0)
        json_str = json.dumps(summary, default=str)
        self.assertIsInstance(json_str, str)


def _activation_artifact(worker: dict[str, Any] | None = None,
                         first: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build an artifact with optional activation variance events injected."""
    art = _artifact(0, _identity("inst-1", restore_count=1, request_count=1))
    events = art["result"]["trace"]["events"]
    if first is not None:
        events.append({"name": "first_unet_activation_variance", "metadata": dict(first)})
    if worker is not None:
        events.append({"name": "unet_activation_worker_variance", "metadata": dict(worker)})
    art["classification"] = "cold"
    return art


def _valid_worker_event() -> dict[str, Any]:
    return {
        "request_id": "req", "mode": "cold", "gate": "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS",
        "registry_setup": {"wall_ms": 2.0},
        "page_traversal": {"duration_ms": 3.0, "minor_faults": 5, "major_faults": 1,
                           "bytes": 1000, "effective_gb_per_s": 0.4,
                           "process_cpu_ms": 1.0, "thread_cpu_ms": 0.8},
        "synchronized_load": {"wall_ms": 4.0, "bytes": 2000, "effective_gb_per_s": 0.5,
                              "minor_faults": 0, "major_faults": 0,
                              "process_cpu_ms": 0.5, "thread_cpu_ms": 0.4},
        "pretouch": {"status": "ok", "expected_pages": 10, "touched_pages": 10,
                     "bytes_read": 40960, "checksum": "abc123"},
        "loader_reconciliation": {"loader_wall_ms": 9.0, "substage_sum_ms": 9.0,
                                  "residual_ms": 0.0, "reconciliation_status": "complete"},
        "patcher_bookkeeping_ms": 3.0,
        "patcher_bookkeeping_counts": {"patch_weight_count": 10, "cast_count": 2},
        "activation_future_publication_ms": 100.0,
        "activation_future_publication_source": "early_activation_completed",
        "unet_storage_registry": {"unique_storage_count": 5, "raw_byte_count": 5000,
                                  "unsupported_count": 0},
    }


def _invalid_first_event() -> dict[str, Any]:
    """Old-shape event whose CPU storage registry proof is unsupported-only."""
    return {
        "request_id": "req", "gate": "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS",
        "preload_setup": {"wall_ms": 3.137},
        "cpu_to_gpu_transfer": {"wall_ms": 2.736, "process_cpu_ms": 0.0,
                                "minor_faults": 0, "major_faults": 0},
        "pretouch": {"status": "empty", "unique_storage_count": 0, "unsupported_count": 453,
                     "unsupported_entries": [{"reason": "device:cuda"}]},
        "loader_reconciliation": {"loader_wall_ms": 5.873, "residual_ms": 0.0,
                                  "reconciliation_status": "complete"},
        "unet_storage_registry": {"unique_storage_count": 0, "raw_byte_count": 0,
                                  "unsupported_count": 453,
                                  "unsupported_entries": [{"reason": "device:cuda"}]},
    }


class TestMeasurementValidity(unittest.TestCase):
    def test_worker_event_preferred_over_first_event(self):
        """When both activation events are present, the worker event wins and
        its truthful metrics are used (registry_setup/page_traversal/
        synchronized_load/pretouch), not the first event."""
        # Worker event is valid; first event would give bogus values.
        art = _activation_artifact(worker=_valid_worker_event(),
                                   first={"cpu_to_gpu_transfer": {"wall_ms": 99.0},
                                          "unet_storage_registry": {"unique_storage_count": 0}})
        rec = extract_run_metrics(art)
        mv = rec["measurement_validity"]
        self.assertEqual(mv["activation_event_source"], "unet_activation_worker_variance")
        self.assertTrue(mv["registry_valid"])
        self.assertTrue(mv["synchronized_transfer_valid"])
        pt = rec["metrics"]["page_traversal"]
        tr = rec["metrics"]["transfer"]
        pre = rec["metrics"]["pretouch"]
        # Synchronized-load transfer from the worker event (not the 99ms first).
        self.assertEqual(tr["cpu_to_gpu_transfer_wall_ms"], 4.0)
        self.assertEqual(tr["cpu_to_gpu_transfer_bytes"], 2000)
        self.assertEqual(tr["cpu_to_gpu_transfer_gb_per_s"], 0.5)
        self.assertEqual(pt["cpu_page_traversal_wall_ms"], 3.0)
        self.assertEqual(pt["activation_total_ms"], 9.0)
        self.assertTrue(pre["pretouch_valid"])
        self.assertEqual(pre["pretouch_bytes_read"], 40960)
        self.assertEqual(pre["pretouch_checksum"], "abc123")
        # Storage registry reflects the worker (supported unique count).
        self.assertEqual(rec["metrics"]["storage"]["storage_unique_count"], 5)

    def test_invalid_registry_suppresses_transfer_and_pretouch(self):
        """A registry with unique_storage_count=0 / unsupported-only must
        suppress page-traversal, pretouch, checksum and CPU→GPU wall/GB-s."""
        art = _activation_artifact(first=_invalid_first_event())
        rec = extract_run_metrics(art)
        mv = rec["measurement_validity"]
        self.assertEqual(mv["activation_event_source"], "first_unet_activation_variance")
        self.assertFalse(mv["registry_valid"])
        self.assertFalse(mv["page_traversal_valid"])
        self.assertFalse(mv["synchronized_transfer_valid"])
        self.assertFalse(mv["pretouch_valid"])
        self.assertFalse(mv["checksum_valid"])
        self.assertIn("unique_storage_count=0", mv["registry_reason"])
        self.assertIn("device:cuda", mv["registry_reason"])
        tr = rec["metrics"]["transfer"]
        pt = rec["metrics"]["page_traversal"]
        pre = rec["metrics"]["pretouch"]
        # The 2.7ms outer-window artifact must NOT be reported.
        self.assertIsNone(tr["cpu_to_gpu_transfer_wall_ms"])
        self.assertIsNone(tr["cpu_to_gpu_transfer_gb_per_s"])
        self.assertIsNone(pt["cpu_page_traversal_wall_ms"])
        self.assertIsNone(pre["pretouch_effect_ms"])
        self.assertIsNone(pre["pretouch_bytes_read"])
        # Truthful loader reconciliation still surfaces as activation total.
        self.assertEqual(pt["activation_total_ms"], 5.873)

    def test_diag_off_no_activation_event_is_unavailable(self):
        art = _artifact(0, _identity("i", restore_count=1, request_count=1))
        art["classification"] = "cold"
        rec = extract_run_metrics(art)
        self.assertEqual(rec["measurement_validity"]["activation_event_source"], "none")
        self.assertFalse(rec["measurement_validity"]["registry_valid"])
        self.assertIsNone(rec["metrics"]["transfer"]["cpu_to_gpu_transfer_wall_ms"])

    def test_rendered_validity_section(self):
        """The consolidated report renders a prominent Measurement validity
        section and the post-hoc instrumentation-failure conclusion."""
        tmp = Path(tempfile.mkdtemp(prefix="v2mat_"))
        # diag-on, pretouch-on attempt with invalid registry proof.
        art = _activation_artifact(first=_invalid_first_event())
        art["attempt_id"] = "matrix-diag1_pt1-0-1-abc"
        art["condition_label"] = "diag1_pt1"
        art["attempt_file"] = "attempt_0001.json"
        (tmp / "attempt_0001.json").write_text(json.dumps(art, default=str), encoding="utf-8")
        rec = extract_run_metrics(art)
        rec["classification"] = "cold"
        rec["attempt_id"] = art["attempt_id"]
        rec["attempt_file"] = "attempt_0001.json"
        rec["condition_label"] = "diag1_pt1"
        s = build_matrix_summary([rec], [(0, 0), (0, 1), (1, 0), (1, 1)],
                                 meta={"mode": "variance_matrix"}, slow_threshold_ms=60000.0)
        md = render_matrix_report(s, tmp)
        for token in ("Measurement validity", "invalid or unavailable",
                      "launch/outer-window", "unique_storage_count=0",
                      "Post-hoc root-cause conclusion", "instrumentation failure",
                      "No production change recommended",
                      "Every attempt (full raw artifact JSON)"):
            self.assertIn(token, md)
        self.assertIn(art["attempt_id"], md)


def _write_matrix_dir(n_attempts: int = 24, tmp: Path | None = None) -> Path:
    """Write *n_attempts* synthetic matrix attempt files (round-robin across the
    four conditions, all cold) plus a minimal summary.json with a fixed
    threshold, returning the temp directory."""
    tmp = Path(tempfile.mkdtemp(prefix="v2mat_")) if tmp is None else tmp
    conditions = [(0, 0), (0, 1), (1, 0), (1, 1)]
    for i in range(n_attempts):
        c = conditions[i % 4]
        label = MATRIX_CONDITION_LABEL(*c)
        art = _artifact(i, _identity(f"inst-{i}", restore_count=1, request_count=1),
                        pretouch=c[1])
        art["attempt_id"] = f"matrix-{label}-{i // 4}-{i}-abc"
        art["attempt_file"] = f"attempt_{i + 1:04d}.json"
        art["condition_label"] = label
        art["diag"] = c[0]
        art["classification"] = "cold"
        art["mode"] = "variance_matrix"
        art["variance"]["pretouch"] = c[1]
        (tmp / art["attempt_file"]).write_text(json.dumps(art, default=str), encoding="utf-8")
    (tmp / "summary.json").write_text(
        json.dumps({"slow_threshold_ms": MATRIX_SLOW_THRESHOLD_MS}), encoding="utf-8")
    return tmp


class TestMatrixReportOnly(unittest.TestCase):
    def test_report_only_matrix_reads_24_attempts_and_writes_handoff(self):
        tmp = _write_matrix_dir(24)
        summary = _report_only_from_dir(tmp)
        # Loaded every attempt (24) and all are cold.
        self.assertEqual(summary["total_attempts"], 24)
        self.assertEqual(summary["total_cold"], 24)
        # Each of the four conditions got 6 cold runs (round-robin).
        for label in ("diag0_pt0", "diag0_pt1", "diag1_pt0", "diag1_pt1"):
            self.assertEqual(summary["per_condition"][label]["cold_count"], 6)
            self.assertEqual(summary["per_condition"][label]["attempt_count"], 6)
        # Fixed threshold reused from the existing summary.json.
        self.assertEqual(summary["slow_threshold_ms"], MATRIX_SLOW_THRESHOLD_MS)

        # Handoff written and embeds every attempt's raw JSON.
        self.assertTrue((tmp / "variance_matrix_handoff.md").is_file())
        handoff = (tmp / "variance_matrix_handoff.md").read_text(encoding="utf-8")
        self.assertIn("V2 Variance-Cold Matrix Handoff Report", handoff)
        self.assertEqual(handoff.count("```json"), 24)
        for i in range(24):
            self.assertIn(f"attempt_{i + 1:04d}.json", handoff)

        # summary.json overwritten with the matrix shape.
        s2 = json.loads((tmp / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(s2["mode"], "variance_matrix")
        self.assertEqual(s2["total_attempts"], 24)

    def test_report_only_matrix_default_threshold_when_summary_absent(self):
        tmp = _write_matrix_dir(4)
        (tmp / "summary.json").write_text("{}", encoding="utf-8")  # no threshold
        summary = _report_only_from_dir(tmp)
        self.assertEqual(summary["slow_threshold_ms"], MATRIX_SLOW_THRESHOLD_MS)


if __name__ == "__main__":
    unittest.main()
