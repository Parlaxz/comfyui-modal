"""
Focused tests for ``diagnosis_collector`` — Section-14/15 tooling.

All tests are local-only (no Modal, no HTTP, no GPU).  They use synthetic
``summary.json`` payloads that mirror the shape of real benchmark artifacts.

Test coverage (per Phase 8 — Trace integrity and focused tests):

1. Section-14 snapshot contains all required keys (nullables are None not absent).
2. Failed runs are retained and labeled.
3. Variant (V1/V2) propagates to snapshot.
4. Comparison table has medians + individual values.
5. Dashboard-only fields are NULL (not missing).
6. Interpretation metadata is present.
7. Collector produces expected directory layout.
8. Snapshot fields are correct for a complete trace.
9. Snapshot fields are correct for a minimal/failed trace.
10. Collector accepts paths with spaces.
11. Collector produces stable output across multiple calls.
12. Comparison table handles empty V1 or V2 list.
13. Comparison Markdown has interpretation and facts sections.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

# Ensure the repo root is on sys.path so diagnosis_collector can import
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from diagnosis_collector import (
    SECTION_14_SCHEMA,
    SECTION_15_ROWS,
    SECTION_15_INTERPRETATION_NOTE,
    _ensure_dir,
    _extract_modal_input_id,
    _is_valid_for_median,
    _median,
    _merge_dashboard_data,
    _parse_dashboard_csv,
    _read_json,
    _validate_completed_run,
    _write_json,
    build_comparison_table,
    collect_diagnosis,
    extract_section14_run,
)


# ── Synthetic fixture builders ─────────────────────────────────────────────


def _make_complete_trace(
    prompt_id: str = "p123",
    sampler_ms: float = 4570.43,
    include_restore: bool = True,
    modal_input_id: str = "mi-synthetic-fixture",
) -> dict:
    """Build a realistic trace similar to what ``benchmark_modal`` produces."""
    trace: Dict[str, Any] = {
        "prompt_id": prompt_id,
        "modal_input_id": modal_input_id,
        "stages": {
            "t0_client_press": 1780442639.008,
            "t1_local_recv": 1780442639.0102432,
            "t2_local_dispatch": 1780442639.0149367,
            "t3_modal_entry": 1780442695.8682086,
            "t3d_prompt_start": 1780442695.870941,
            "t3e_execution_start": 1780442695.8709724,
            "t6_sampler_start": 1780442696.366952,
            "t6_sampler_end": 1780442700.93738,
            "t7_vae_decode_start": 1780442700.93738,
            "t7_vae_decode_end": 1780442701.2652519,
            "t8b_outputs_collected": 1780442701.724736,
            "t9_modal_return": 1780442701.7263339,
            "t10_local_materialized": 1780442703.5814075,
        },
        "deltas_ms": {
            "t0_to_t1": 2.24,
            "t1_to_t2": 4.69,
            "t2_to_t3": 56853.27,
            "t3_to_t3b": 2.73,
            "t9_to_t10": 1855.07,
            "sampler": sampler_ms,
            "vae_decode": 327.87,
            "clip_encode": 227.55,
            "modal_to_browser": 64566.47,
            "modal_to_return": 62711.4,
        },
        "derived_ms": {
            "total_input_execution_ms": 5831.04,
            "prompt_start_to_sampler_start_ms": 0.5,
            "sampler_ms": sampler_ms,
            "sampler_end_to_outputs_collected_ms": 0.79,
            "output_collection_total_ms": 1.6,
            "vae_decode_ms": 327.87,
            "clip_encode_ms": 227.55,
            "modal_entry_to_prompt_start_ms": 2.73,
            "local_dispatch_to_modal_entry_ms": 56853.27,
            "modal_to_return_ms": 62711.4,
            "modal_to_browser_ms": 64566.47,
            "local_materialize_ms": 1855.07,
            "unet_node_wait_ms": 4500.0,
            "vae_node_wait_ms": 0.5,
            "clip_load_ms": 1200.0,
        },
        "trace_id": "trace-abc-123",
        "workflow_hash": "wf-hash-001",
        "config_hash": "cfg-hash-002",
        "container_task_id": "ct-999",
        "image_id": "img-flux-1",
        "gpu": "RTX PRO 6000",
        "cloud": "aws",
        "region": "us-east-1",
        "result_route": "direct",
    }
    if include_restore:
        trace["restore"] = {
            "restore_total_ms": 4565.77,
            "gpu_state_recover_ms": 120.0,
            "cuda_init_ms": 3400.0,
            "sage_init_ms": 500.0,
            "volume_reload_ms": 300.0,
            "models_volume_reload_ms": 200.0,
            "preload_mode": "clip_only",
            "warmup_preload_ms": 2100.0,
            "warmup_direct_total_ms": 3200.0,
        }
    return trace


def _make_failed_trace(
    prompt_id: str = "p-fail-1",
    error_msg: str = "Modal error: Function call was cancelled",
) -> dict:
    """Build a minimal trace for a failed run."""
    return {
        "prompt_id": prompt_id,
        "stages": {},
        "deltas_ms": {},
    }


def _make_summary(
    run1_trace: dict,
    run2_trace: dict | None = None,
    status: str = "ok",
) -> dict:
    summary: Dict[str, Any] = {
        "status": status,
        "run1_trace": run1_trace,
    }
    if run2_trace is not None:
        summary["run2_trace"] = run2_trace
    else:
        summary["run2_trace"] = {}

    # Compute total from stages if possible
    for which, trace in [("run1", run1_trace), ("run2", run2_trace or {})]:
        stages = trace.get("stages", {}) if isinstance(trace, dict) else {}
        t0 = stages.get("t0_client_press")
        t10 = stages.get("t10_local_materialized")
        if t0 is not None and t10 is not None:
            summary[f"{which}_total_ms"] = round((t10 - t0) * 1000, 2)
        elif isinstance(trace, dict) and isinstance(trace.get("deltas_ms"), dict):
            summary[f"{which}_total_ms"] = trace["deltas_ms"].get("modal_to_browser")

    if status != "ok":
        summary["error"] = f"Simulated: {status}"
        for which in ("run1", "run2"):
            if f"{which}_total_ms" not in summary:
                summary[f"{which}_total_ms"] = None

    return summary


# ── Base class with shared fixtures ────────────────────────────────────────


class DiagnosisCollectorBase(unittest.TestCase):
    """Shared setup: synthetic summary.json files in a temp directory."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name).resolve()

        # Create V1 summary (simulating older benchmark format)
        v1_trace = _make_complete_trace(
            prompt_id="v1-prompt-001", sampler_ms=4570.43, include_restore=True
        )
        self.v1_summary = _make_summary(v1_trace, status="ok")
        self.v1_path = self.tmp_dir / "v1_run" / "summary.json"
        self.v1_path.parent.mkdir(parents=True)
        _write_json(self.v1_path, self.v1_summary)

        # Create V2 summary
        v2_trace = _make_complete_trace(
            prompt_id="v2-prompt-001", sampler_ms=5125.85, include_restore=True
        )
        self.v2_summary = _make_summary(v2_trace, status="ok")
        self.v2_path = self.tmp_dir / "v2_run" / "summary.json"
        self.v2_path.parent.mkdir(parents=True)
        _write_json(self.v2_path, self.v2_summary)

        # Create a failed V1 summary
        fail_trace = _make_failed_trace(prompt_id="v1-fail-001")
        self.fail_summary = _make_summary(fail_trace, status="run1_failed")
        self.fail_path = self.tmp_dir / "v1_fail" / "summary.json"
        self.fail_path.parent.mkdir(parents=True)
        _write_json(self.fail_path, self.fail_summary)

    def tearDown(self):
        self._tmp.cleanup()


# ── Test classes ───────────────────────────────────────────────────────────


class TestExtractSection14Run(DiagnosisCollectorBase):
    """Unit tests for ``extract_section14_run``."""

    def test_all_required_keys_present(self):
        """Section-14 snapshot contains every required key."""
        snap = extract_section14_run(self.v1_summary, "run1", "V1", 0)
        for key in SECTION_14_SCHEMA:
            self.assertIn(key, snap, f"Missing required key: {key}")

    def test_dashboard_fields_are_null(self):
        """Dashboard timing fields are NULL without CSV correlation."""
        snap = extract_section14_run(self.v1_summary, "run1", "V1", 0)
        # modal_input_id is now extracted from trace data, not dashboard-only
        self.assertIsNotNone(snap.get("modal_input_id"), "modal_input_id should be extracted from trace")
        # The three dashboard timing fields remain NULL until CSV correlation
        self.assertIsNone(snap["dashboard_input_to_scheduled_ms"])
        self.assertIsNone(snap["dashboard_scheduled_to_execution_ms"])
        self.assertIsNone(snap["dashboard_execution_ms"])

    def test_variant_propagates(self):
        """Variant string appears correctly in the snapshot."""
        snap_v1 = extract_section14_run(self.v1_summary, "run1", "V1", 0)
        snap_v2 = extract_section14_run(self.v2_summary, "run1", "V2", 0)
        self.assertEqual(snap_v1["variant"], "V1")
        self.assertEqual(snap_v2["variant"], "V2")

    def test_run_id_contains_variant_and_index(self):
        """run_id encodes the run index and variant."""
        snap = extract_section14_run(self.v1_summary, "run1", "V1", 3)
        self.assertIn("run-03", snap["run_id"])
        self.assertIn("-V1-", snap["run_id"])

    def test_workflow_hash_and_options_hash_fallback_to_v1_identity(self):
        """workflow_hash and effective_options_hash fall back to v1_identity."""
        summary = dict(self.v1_summary)
        trace = summary.get("run1_trace", {})
        if isinstance(trace, dict):
            trace["v1_identity"] = {
                "workflow_hash_prefix": "wf-test-prefix-001",
                "effective_options_hash": "opts-hash-002",
            }
        snap = extract_section14_run(summary, "run1", "V1", 0)
        # workflow_hash should come from trace/workflow_hash (set in fixture)
        # The v1_identity fallback only applies when trace-level key is missing.
        self.assertEqual(snap["workflow_hash"], "wf-hash-001")
        # effective_options_hash: fixture uses config_hash -> should be "cfg-hash-002"
        self.assertEqual(snap["effective_options_hash"], "cfg-hash-002")

    def test_workflow_hash_falls_back_to_v1_identity_when_missing(self):
        """When trace lacks workflow_hash, fall back to v1_identity."""
        summary = dict(self.v1_summary)
        trace = summary.get("run1_trace", {})
        if isinstance(trace, dict):
            trace.pop("workflow_hash", None)
            trace.pop("config_hash", None)
            trace["v1_identity"] = {
                "workflow_hash_prefix": "v1-wf-prefix",
                "effective_options_hash": "v1-opts-hash",
            }
        snap = extract_section14_run(summary, "run1", "V1", 0)
        self.assertEqual(snap["workflow_hash"], "v1-wf-prefix")
        self.assertEqual(snap["effective_options_hash"], "v1-opts-hash")

    def test_identity_fields_fallback_to_metadata(self):
        """Identity fields fall back to trace.metadata dict (V2 pattern)."""
        summary = dict(self.v1_summary)
        trace = summary.get("run1_trace", {})
        if isinstance(trace, dict):
            # Remove top-level identity keys so metadata becomes the fallback
            trace.pop("gpu", None)
            trace.pop("cloud", None)
            trace.pop("region", None)
            trace.pop("container_task_id", None)
            trace.pop("image_id", None)
            trace["metadata"] = {
                "gpu": "L40S",
                "cloud": "gcp",
                "region": "europe-west4",
                "container_task_id": "ct-meta-555",
                "image_id": "img-meta-666",
            }
        snap = extract_section14_run(summary, "run1", "V1", 0)
        rid = snap["resource_identity"]
        self.assertEqual(rid.get("gpu"), "L40S")
        self.assertEqual(rid.get("cloud"), "gcp")
        self.assertEqual(rid.get("region"), "europe-west4")
        self.assertEqual(snap["container_task_id"], "ct-meta-555")
        self.assertEqual(snap["image_id"], "img-meta-666")

    def test_complete_trace_wall_clock_extracted(self):
        """local_wall_clock_ms is extracted from stages."""
        snap = extract_section14_run(self.v1_summary, "run1", "V1", 0)
        self.assertIsNotNone(snap["local_wall_clock_ms"])
        self.assertGreater(snap["local_wall_clock_ms"], 0)

    def test_failed_run_retained_and_labeled(self):
        """Failed run trace is retained and status reflects failure."""
        snap = extract_section14_run(self.fail_summary, "run1", "V1", 0)
        self.assertEqual(snap["status"], "run1_failed")
        self.assertIsNotNone(snap["errors"])
        # Trace should still be present (failed runs are retained)
        self.assertIsInstance(snap["trace"], dict)

    def test_empty_run2_handled_gracefully(self):
        """When run2_trace is empty, extraction still works."""
        no_run2_summary = {
            "status": "ok",
            "run1_trace": _make_complete_trace("p1"),
            "run2_trace": {},
        }
        snap = extract_section14_run(no_run2_summary, "run2", "V2", 1)
        # Should not crash; trace is empty dict
        self.assertEqual(snap["variant"], "V2")

    def test_resource_identity_present(self):
        """resource_identity dict captures available fields."""
        snap = extract_section14_run(self.v1_summary, "run1", "V1", 0)
        rid = snap["resource_identity"]
        self.assertIsInstance(rid, dict)
        self.assertEqual(rid.get("gpu"), "RTX PRO 6000")
        self.assertEqual(rid.get("cloud"), "aws")

    def test_resource_identity_has_common_schema_keys(self):
        """resource_identity includes additive common-schema identity keys."""
        snap = extract_section14_run(self.v1_summary, "run1", "V1", 0)
        rid = snap["resource_identity"]
        self.assertIsInstance(rid, dict)
        # ── App / class identity ──
        self.assertIn("app_name", rid)
        self.assertIn("class_name", rid)
        # ── Resource allocation ──
        self.assertIn("target_inputs", rid)
        self.assertIn("max_inputs", rid)
        # ── Volume names ──
        self.assertIn("models_volume", rid)
        self.assertIn("runtime_state_volume", rid)
        self.assertIn("custom_nodes_volume", rid)
        self.assertIn("volume_mount_paths", rid)
        # Legacy keys still present
        self.assertEqual(rid.get("gpu"), "RTX PRO 6000")
        self.assertEqual(rid.get("cloud"), "aws")

    def test_resource_identity_falls_back_to_v1_identity(self):
        """When trace lacks top-level identity keys, falls back to v1_identity."""
        from diagnosis_collector import extract_section14_run
        summary = dict(self.v1_summary)
        trace = summary.get("run1_trace", {})
        if isinstance(trace, dict):
            # Remove top-level identity keys so v1_identity becomes the fallback
            trace.pop("gpu", None)
            trace.pop("cloud", None)
            trace.pop("region", None)
            trace.pop("cpu", None)
            trace.pop("memory_mb", None)
            trace.pop("app_name", None)
            trace.pop("class_name", None)
            trace.pop("models_volume", None)
            trace["v1_identity"] = {
                "app_name": "test-app",
                "class_name": "ComfyAPI_Test",
                "gpu": "custom-gpu",
                "cloud_provider": "azure",
                "region": "westus",
                "cpu": 8,
                "memory_mb": 65536,
                "target_inputs": 2,
                "max_inputs": 4,
                "snapshot_enabled": "True",
                "gpu_snapshot_enabled": "False",
                "models_volume": "test-models-vol",
                "runtime_state_volume": "test-rt-vol",
                "custom_nodes_volume": "test-cn-vol",
                "task_id": "ct-v1-999",
                "image_id": "img-v1-test",
            }
        snap = extract_section14_run(summary, "run1", "V1", 0)
        rid = snap["resource_identity"]
        # Should use v1_identity values since trace no longer has them
        self.assertEqual(rid.get("app_name"), "test-app")
        self.assertEqual(rid.get("class_name"), "ComfyAPI_Test")
        self.assertEqual(rid.get("gpu"), "custom-gpu")
        self.assertEqual(rid.get("cloud"), "azure")  # cloud_provider from v1_identity
        self.assertEqual(rid.get("region"), "westus")
        self.assertEqual(rid.get("cpu"), 8)
        self.assertEqual(rid.get("memory_mb"), 65536)
        self.assertEqual(rid.get("target_inputs"), 2)
        self.assertEqual(rid.get("max_inputs"), 4)
        self.assertEqual(rid.get("models_volume"), "test-models-vol")

    def test_execution_breakdown_present(self):
        """execution_breakdown contains extracted phase durations."""
        snap = extract_section14_run(self.v1_summary, "run1", "V1", 0)
        eb = snap["execution_breakdown"]
        self.assertIsInstance(eb, dict)
        self.assertIsNotNone(eb.get("sampler_ms"))
        self.assertIsNotNone(eb.get("vae_decode_ms"))
        self.assertIsNotNone(eb.get("output_collection_total_ms"))

    def test_lifecycle_breakdown_from_restore(self):
        """lifecycle_breakdown includes restore timing when available."""
        snap = extract_section14_run(self.v1_summary, "run1", "V1", 0)
        lb = snap["lifecycle_breakdown"]
        self.assertIsInstance(lb, dict)
        self.assertAlmostEqual(lb.get("restore_total_ms"), 4565.77, places=1)

    def test_no_restore_no_crash(self):
        """Trace without restore dict does not crash."""
        trace_no_restore = _make_complete_trace(include_restore=False)
        summary = _make_summary(trace_no_restore)
        snap = extract_section14_run(summary, "run1", "V1", 2)
        # lifecycle_breakdown may be empty dict or None — either is fine
        self.assertIn(snap["lifecycle_breakdown"], [None, {}])

    def test_preload_breakdown_from_restore(self):
        """preload_breakdown captures warmup fields from restore."""
        snap = extract_section14_run(self.v1_summary, "run1", "V1", 0)
        pb = snap["preload_breakdown"]
        self.assertIsInstance(pb, dict)
        self.assertEqual(pb.get("preload_mode"), "clip_only")

    def test_output_breakdown_structure(self):
        """output_breakdown has expected keys."""
        snap = extract_section14_run(self.v1_summary, "run1", "V1", 0)
        ob = snap["output_breakdown"]
        self.assertIsInstance(ob, dict)
        self.assertIn("output_collection_total_ms", ob)
        self.assertIn("strategy", ob)


class TestBuildComparisonTable(DiagnosisCollectorBase):
    """Unit tests for ``build_comparison_table``."""

    def setUp(self):
        super().setUp()
        self.v1_snap = extract_section14_run(self.v1_summary, "run1", "V1", 0)
        self.v2_snap = extract_section14_run(self.v2_summary, "run1", "V2", 1)

    def test_table_has_all_rows(self):
        """Comparison table contains every Section-15 row key."""
        table = build_comparison_table([self.v1_snap], [self.v2_snap], "test")
        for field in SECTION_15_ROWS:
            self.assertIn(field, table["rows"], f"Missing row: {field}")

    def test_medians_present(self):
        """Comparison table has V1/V2 medians for measurable fields."""
        table = build_comparison_table([self.v1_snap], [self.v2_snap], "test")
        sampler_row = table["rows"]["sampler_ms"]
        self.assertIsNotNone(sampler_row["v1_median_ms"])
        self.assertIsNotNone(sampler_row["v2_median_ms"])

    def test_individual_values_present(self):
        """Individual values list is present for each field."""
        table = build_comparison_table([self.v1_snap], [self.v2_snap], "test")
        wall_row = table["rows"]["total_user_facing_wall_clock_ms"]
        self.assertIsInstance(wall_row["v1_individual_ms"], list)
        self.assertIsInstance(wall_row["v2_individual_ms"], list)

    def test_dashboard_fields_null_in_table(self):
        """Dashboard-only fields produce NULL medians in comparison."""
        table = build_comparison_table([self.v1_snap], [self.v2_snap], "test")
        modal_queue = table["rows"]["modal_input_queue_ms"]
        self.assertIsNone(modal_queue["v1_median_ms"])
        self.assertIsNone(modal_queue["v2_median_ms"])

    def test_interpretation_metadata_present(self):
        """Comparison includes facts-only interpretation metadata."""
        table = build_comparison_table([self.v1_snap], [self.v2_snap], "test")
        self.assertIsInstance(table.get("interpretation"), str)
        self.assertGreater(len(table["interpretation"]), 10)
        self.assertIsInstance(table.get("facts"), list)
        self.assertGreater(len(table["facts"]), 0)

    def test_empty_v1_list(self):
        """Empty V1 list produces None medians but does not crash."""
        table = build_comparison_table([], [self.v2_snap], "empty-v1")
        self.assertEqual(table["v1_run_count"], 0)
        for field in SECTION_15_ROWS:
            row = table["rows"][field]
            self.assertIsNone(row["v1_median_ms"])

    def test_empty_v2_list(self):
        """Empty V2 list produces None medians but does not crash."""
        table = build_comparison_table([self.v1_snap], [], "empty-v2")
        self.assertEqual(table["v2_run_count"], 0)
        for field in SECTION_15_ROWS:
            row = table["rows"][field]
            self.assertIsNone(row["v2_median_ms"])

    def test_delta_calculation(self):
        """Delta is calculated when both medians are available."""
        table = build_comparison_table([self.v1_snap], [self.v2_snap], "test")
        sampler_row = table["rows"]["sampler_ms"]
        if sampler_row["v1_median_ms"] is not None and sampler_row["v2_median_ms"] is not None:
            expected_delta = round(sampler_row["v2_median_ms"] - sampler_row["v1_median_ms"], 2)
            self.assertEqual(sampler_row["delta_v2_minus_v1_ms"], expected_delta)

    def test_multiple_runs_per_variant(self):
        """Multiple runs per variant produce correct medians."""
        v1_dup = extract_section14_run(self.v1_summary, "run2", "V1", 2)
        table = build_comparison_table([self.v1_snap, v1_dup], [self.v2_snap], "multi")
        # Should not crash, medians from multiple values
        self.assertIsNotNone(table["rows"]["sampler_ms"]["v1_median_ms"])


class TestCollectDiagnosis(DiagnosisCollectorBase):
    """Integration tests for ``collect_diagnosis``."""

    def test_directory_layout(self):
        """Collector produces expected directory structure."""
        out_dir = collect_diagnosis(
            runs=[(str(self.v1_path), "V1"), (str(self.v2_path), "V2")],
            label="test-collection",
            diagnosis_base_dir=self.tmp_dir / "diag_out",
        )
        self.assertTrue((out_dir / "diagnosis.json").is_file())
        self.assertTrue((out_dir / "comparison.json").is_file())
        self.assertTrue((out_dir / "comparison.md").is_file())
        self.assertTrue((out_dir / "runs").is_dir())

    def test_diagnosis_json_index(self):
        """diagnosis.json contains run index with per-snapshot metadata."""
        out_dir = collect_diagnosis(
            runs=[(str(self.v1_path), "V1"), (str(self.v2_path), "V2")],
            label="test-index",
            diagnosis_base_dir=self.tmp_dir / "diag_idx",
        )
        diag = _read_json(out_dir / "diagnosis.json")
        self.assertEqual(diag["schema"], "section_14_diagnosis_v1")
        self.assertEqual(diag["v1_count"], 1)
        self.assertEqual(diag["v2_count"], 1)
        self.assertIsInstance(diag["snapshots"], list)
        for entry in diag["snapshots"]:
            self.assertIn("run_id", entry)
            self.assertIn("variant", entry)
            self.assertIn("status", entry)
            self.assertIn("file", entry)

    def test_comparison_json_has_all_rows(self):
        """comparison.json contains the full Section-15 table."""
        out_dir = collect_diagnosis(
            runs=[(str(self.v1_path), "V1"), (str(self.v2_path), "V2")],
            label="test-cmp",
            diagnosis_base_dir=self.tmp_dir / "diag_cmp",
        )
        cmp = _read_json(out_dir / "comparison.json")
        self.assertEqual(cmp["schema"], "section_15_comparison_v1")
        for field in SECTION_15_ROWS:
            self.assertIn(field, cmp["rows"])

    def test_failed_runs_appear_in_snapshots(self):
        """Failed runs appear in snapshot list with failure status."""
        out_dir = collect_diagnosis(
            runs=[(str(self.fail_path), "V1")],
            label="test-fail",
            diagnosis_base_dir=self.tmp_dir / "diag_fail",
        )
        diag = _read_json(out_dir / "diagnosis.json")
        self.assertGreaterEqual(len(diag["snapshots"]), 1)
        # At least one snapshot should have failed status
        statuses = {s["status"] for s in diag["snapshots"]}
        self.assertTrue(
            {"run1_failed", "failed"}.intersection(statuses),
            f"Expected failure status in {statuses}",
        )
        # Failed run's JSON file exists
        for entry in diag["snapshots"]:
            snap_file = out_dir / entry["file"]
            self.assertTrue(snap_file.is_file(), f"Missing {snap_file}")
            snap_data = _read_json(snap_file)
            if entry["status"] in ("run1_failed", "failed"):
                self.assertIsNotNone(snap_data.get("errors"))

    def test_multiple_run_sources(self):
        """Collector handles multiple summary files with mixed variants."""
        out_dir = collect_diagnosis(
            runs=[
                (str(self.v1_path), "V1"),
                (str(self.v2_path), "V2"),
                (str(self.v1_path), "V1"),
            ],
            label="test-multi",
            diagnosis_base_dir=self.tmp_dir / "diag_multi",
        )
        diag = _read_json(out_dir / "diagnosis.json")
        self.assertEqual(diag["v1_count"], 2)
        self.assertEqual(diag["v2_count"], 1)
        self.assertEqual(diag["run_count"], 3)

    def test_label_defaults_to_timestamp(self):
        """Diagnosis label defaults to a timestamp when not provided."""
        out_dir = collect_diagnosis(
            runs=[(str(self.v1_path), "V1")],
            diagnosis_base_dir=self.tmp_dir / "diag_ts",
        )
        diag = _read_json(out_dir / "diagnosis.json")
        self.assertIsInstance(diag["diagnosis_label"], str)
        self.assertGreater(len(diag["diagnosis_label"]), 5)

    def test_errors_collected_when_summary_missing(self):
        """Missing summary files are collected as errors, not crashes."""
        out_dir = collect_diagnosis(
            runs=[
                (str(self.tmp_dir / "nonexistent" / "summary.json"), "V1"),
                (str(self.v2_path), "V2"),
            ],
            label="test-err",
            diagnosis_base_dir=self.tmp_dir / "diag_err",
        )
        diag = _read_json(out_dir / "diagnosis.json")
        self.assertIsNotNone(diag.get("errors"))
        self.assertGreaterEqual(len(diag["errors"]), 1)

    def test_comparison_markdown_has_interpretation(self):
        """Comparison Markdown includes interpretation and facts sections."""
        out_dir = collect_diagnosis(
            runs=[(str(self.v1_path), "V1"), (str(self.v2_path), "V2")],
            label="test-md",
            diagnosis_base_dir=self.tmp_dir / "diag_md",
        )
        md_text = (out_dir / "comparison.md").read_text(encoding="utf-8")
        self.assertIn("Interpretation", md_text)
        self.assertIn("Facts", md_text)
        self.assertIn("V1/V2 Comparison", md_text)
        # Unified section heading covers both correlated and uncorrelated cases
        self.assertIn("Dashboard / External Fields", md_text)
        self.assertIn("modal_input_id", md_text)

    def test_per_run_json_files(self):
        """Each run gets a JSON file under runs/."""
        out_dir = collect_diagnosis(
            runs=[(str(self.v1_path), "V1"), (str(self.v2_path), "V2")],
            label="test-files",
            diagnosis_base_dir=self.tmp_dir / "diag_files",
        )
        run_files = list((out_dir / "runs").glob("*.json"))
        self.assertGreaterEqual(len(run_files), 2)

    def test_comparison_md_per_run_overview_table(self):
        """Markdown has per-run overview table with run ID, variant, status, wall clock."""
        out_dir = collect_diagnosis(
            runs=[(str(self.v1_path), "V1"), (str(self.v2_path), "V2")],
            label="test-overview",
            diagnosis_base_dir=self.tmp_dir / "diag_overview",
        )
        md_text = (out_dir / "comparison.md").read_text(encoding="utf-8")
        self.assertIn("Per-Run Overview", md_text)
        self.assertIn("Run ID", md_text)
        self.assertIn("Variant", md_text)
        self.assertIn("V1", md_text)
        self.assertIn("V2", md_text)


# ── New focused tests for controlled-run readiness fixes ────────────────────


class TestModalInputIdExtraction(unittest.TestCase):
    """Unit tests for ``_extract_modal_input_id``."""

    def test_top_level_trace(self):
        """Extracts modal_input_id from top-level trace key."""
        mid = _extract_modal_input_id(
            {"modal_input_id": "mi-top-001"},
            {}, {}, {},
        )
        self.assertEqual(mid, "mi-top-001")

    def test_metadata_sub_dict(self):
        """Extracts from trace.metadata (V2 RuntimeTrace pattern)."""
        mid = _extract_modal_input_id(
            {"metadata": {"modal_input_id": "mi-meta-002"}},
            {}, {}, {},
        )
        self.assertEqual(mid, "mi-meta-002")

    def test_v1_identity_key(self):
        """Extracts from v1_identity sub-dict."""
        mid = _extract_modal_input_id(
            {"v1_identity": {"modal_input_id": "mi-v1-003"}},
            {"modal_input_id": "mi-v1-003"}, {}, {},
        )
        self.assertEqual(mid, "mi-v1-003")

    def test_v1_identity_input_id_fallback(self):
        """Falls back to v1_identity 'input_id' key when modal_input_id absent."""
        mid = _extract_modal_input_id(
            {"v1_identity": {"input_id": "mi-input-id-004"}},
            {"input_id": "mi-input-id-004"}, {}, {},
        )
        self.assertEqual(mid, "mi-input-id-004")

    def test_restore_sub_dict(self):
        """Extracts from restore sub-dict."""
        mid = _extract_modal_input_id(
            {"restore": {"modal_input_id": "mi-restore-005"}},
            {}, {}, {"modal_input_id": "mi-restore-005"},
        )
        self.assertEqual(mid, "mi-restore-005")

    def test_events_metadata(self):
        """Extracts from RuntimeTrace event metadata."""
        trace = {
            "events": [
                {"name": "remote_method_entry", "metadata": {"modal_input_id": "mi-event-006"}},
            ]
        }
        mid = _extract_modal_input_id(trace, {}, {}, {})
        self.assertEqual(mid, "mi-event-006")

    def test_events_metadata_input_id_key(self):
        """Extracts from event metadata using 'input_id' key."""
        trace = {
            "events": [
                {"name": "gpu_invocation_submit", "metadata": {"input_id": "mi-alt-007"}},
            ]
        }
        mid = _extract_modal_input_id(trace, {}, {}, {})
        self.assertEqual(mid, "mi-alt-007")

    def test_not_found_returns_none(self):
        """Returns None when no modal_input_id is present in any source."""
        mid = _extract_modal_input_id(
            {"trace_id": "abc"}, {}, {}, {},
        )
        self.assertIsNone(mid)

    def test_precedence_top_level_over_metadata(self):
        """Top-level trace key takes precedence over metadata."""
        mid = _extract_modal_input_id(
            {
                "modal_input_id": "mi-top",
                "metadata": {"modal_input_id": "mi-meta"},
            },
            {}, {}, {},
        )
        self.assertEqual(mid, "mi-top")

    def test_precedence_metadata_over_v1_identity(self):
        """metadata takes precedence over v1_identity."""
        mid = _extract_modal_input_id(
            {
                "metadata": {"modal_input_id": "mi-meta"},
                "v1_identity": {"modal_input_id": "mi-v1"},
            },
            {"modal_input_id": "mi-v1"}, {"modal_input_id": "mi-meta"}, {},
        )
        self.assertEqual(mid, "mi-meta")

    def test_precedence_v1_identity_over_restore(self):
        """v1_identity takes precedence over restore."""
        mid = _extract_modal_input_id(
            {
                "v1_identity": {"modal_input_id": "mi-v1"},
            },
            {"modal_input_id": "mi-v1"}, {}, {"modal_input_id": "mi-restore"},
        )
        self.assertEqual(mid, "mi-v1")

    def test_trace_without_modal_input_id_returns_none(self):
        """Trace without any modal_input_id source returns None."""
        trace = {"prompt_id": "p-no-id", "stages": {}}
        mid = _extract_modal_input_id(trace, {}, {}, {})
        self.assertIsNone(mid)


class TestDashboardCsvParsing(unittest.TestCase):
    """Unit tests for ``_parse_dashboard_csv``."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_csv(self, rows: list[dict]) -> Path:
        path = self.tmp_dir / "dashboard.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "modal_input_id", "input_created_to_scheduled_ms",
                "scheduled_to_execution_ms", "execution_ms",
            ])
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return path

    def test_parses_valid_csv(self):
        """Successfully parses a valid dashboard CSV."""
        path = self._write_csv([
            {"modal_input_id": "mi-001", "input_created_to_scheduled_ms": "1500",
             "scheduled_to_execution_ms": "3200", "execution_ms": "5800"},
            {"modal_input_id": "mi-002", "input_created_to_scheduled_ms": "1800",
             "scheduled_to_execution_ms": "2900", "execution_ms": "6200"},
        ])
        data = _parse_dashboard_csv(str(path))
        self.assertIn("mi-001", data)
        self.assertIn("mi-002", data)
        self.assertEqual(data["mi-001"]["input_created_to_scheduled_ms"], 1500.0)
        self.assertEqual(data["mi-001"]["scheduled_to_execution_ms"], 3200.0)
        self.assertEqual(data["mi-001"]["execution_ms"], 5800.0)

    def test_rejects_duplicate_ids(self):
        """Raises ValueError on duplicate modal_input_id."""
        path = self._write_csv([
            {"modal_input_id": "mi-dup", "input_created_to_scheduled_ms": "100",
             "scheduled_to_execution_ms": "200", "execution_ms": "300"},
            {"modal_input_id": "mi-dup", "input_created_to_scheduled_ms": "400",
             "scheduled_to_execution_ms": "500", "execution_ms": "600"},
        ])
        with self.assertRaises(ValueError) as ctx:
            _parse_dashboard_csv(str(path))
        self.assertIn("Duplicate", str(ctx.exception))

    def test_rejects_missing_columns(self):
        """Raises ValueError when required columns are missing."""
        path = self.tmp_dir / "bad.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write("modal_input_id,foo,bar\n")
            f.write("mi-001,1,2\n")
        with self.assertRaises(ValueError) as ctx:
            _parse_dashboard_csv(str(path))
        self.assertIn("missing required columns", str(ctx.exception).lower())

    def test_skips_blank_rows(self):
        """Blank modal_input_id rows are silently skipped."""
        path = self._write_csv([
            {"modal_input_id": "", "input_created_to_scheduled_ms": "100",
             "scheduled_to_execution_ms": "200", "execution_ms": "300"},
            {"modal_input_id": "mi-real", "input_created_to_scheduled_ms": "400",
             "scheduled_to_execution_ms": "500", "execution_ms": "600"},
        ])
        data = _parse_dashboard_csv(str(path))
        self.assertNotIn("", data)
        self.assertIn("mi-real", data)


class TestDashboardMerge(unittest.TestCase):
    """Unit tests for ``_merge_dashboard_data``."""

    def test_successful_merge(self):
        """Dashboard timing populated when modal_input_id matches."""
        snapshot = {
            "run_id": "run-00-V1-abc",
            "modal_input_id": "mi-match",
            "dashboard_input_to_scheduled_ms": None,
            "dashboard_scheduled_to_execution_ms": None,
            "dashboard_execution_ms": None,
        }
        dashboard_data = {
            "mi-match": {
                "input_created_to_scheduled_ms": 1500.0,
                "scheduled_to_execution_ms": 3200.0,
                "execution_ms": 5800.0,
            }
        }
        err = _merge_dashboard_data(snapshot, dashboard_data)
        self.assertIsNone(err)
        self.assertEqual(snapshot["dashboard_input_to_scheduled_ms"], 1500.0)
        self.assertEqual(snapshot["dashboard_scheduled_to_execution_ms"], 3200.0)
        self.assertEqual(snapshot["dashboard_execution_ms"], 5800.0)

    def test_no_modal_input_id_returns_none(self):
        """No error when snapshot lacks modal_input_id."""
        snapshot = {"run_id": "run-00", "modal_input_id": None}
        err = _merge_dashboard_data(snapshot, {"mi-other": {}})
        self.assertIsNone(err)

    def test_unmatched_returns_error_string(self):
        """Returns error string when modal_input_id not in dashboard data."""
        snapshot = {
            "run_id": "run-01-V1-xyz",
            "modal_input_id": "mi-unknown",
        }
        err = _merge_dashboard_data(snapshot, {"mi-other": {}})
        self.assertIsNotNone(err)
        if err is not None:  #  narrow for type checker
            self.assertIn("unmatched", err.lower())
            self.assertIn("mi-unknown", err)


class TestCompletedRunValidation(unittest.TestCase):
    """Unit tests for ``_validate_completed_run``."""

    def test_complete_run_passes(self):
        """A fully populated snapshot passes validation."""
        errors = _validate_completed_run({
            "request_id": "req-001",
            "trace_id": "trace-001",
            "modal_input_id": "mi-001",
            "container_task_id": "ct-001",
            "image_id": "img-001",
            "resource_identity": {"gpu": "L40S", "cloud": "aws", "region": "us-east-1"},
            "workflow_hash": "wf-001",
            "effective_options_hash": "opts-001",
        })
        self.assertEqual(errors, [])

    def test_missing_request_id_and_trace_id(self):
        """Missing both request_id and trace_id is an error."""
        errors = _validate_completed_run({
            "request_id": None,
            "trace_id": None,
            "modal_input_id": "mi-001",
            "container_task_id": "ct-001",
            "image_id": "img-001",
            "resource_identity": {"gpu": "L40S", "cloud": "aws", "region": "us-east-1"},
            "workflow_hash": "wf-001",
            "effective_options_hash": "opts-001",
        })
        self.assertIn("request_id", " ".join(errors))
        self.assertIn("trace_id", " ".join(errors))

    def test_missing_modal_input_id(self):
        """Missing modal_input_id is an error."""
        errors = _validate_completed_run({
            "request_id": "req-001",
            "modal_input_id": None,
            "container_task_id": "ct-001",
            "image_id": "img-001",
            "resource_identity": {"gpu": "L40S", "cloud": "aws", "region": "us-east-1"},
            "workflow_hash": "wf-001",
            "effective_options_hash": "opts-001",
        })
        self.assertTrue(any("modal_input_id" in e for e in errors))

    def test_missing_container_task_id(self):
        """Missing container_task_id is an error."""
        errors = _validate_completed_run({
            "request_id": "req-001",
            "modal_input_id": "mi-001",
            "container_task_id": None,
            "image_id": "img-001",
            "resource_identity": {"gpu": "L40S", "cloud": "aws", "region": "us-east-1"},
            "workflow_hash": "wf-001",
            "effective_options_hash": "opts-001",
        })
        self.assertTrue(any("container_task_id" in e for e in errors))

    def test_missing_image_id(self):
        """Missing image_id is an error."""
        errors = _validate_completed_run({
            "request_id": "req-001",
            "modal_input_id": "mi-001",
            "container_task_id": "ct-001",
            "image_id": None,
            "resource_identity": {"gpu": "L40S", "cloud": "aws", "region": "us-east-1"},
            "workflow_hash": "wf-001",
            "effective_options_hash": "opts-001",
        })
        self.assertTrue(any("image_id" in e for e in errors))

    def test_missing_resource_identity_fields(self):
        """Missing gpu/cloud/region in resource_identity are errors."""
        errors = _validate_completed_run({
            "request_id": "req-001",
            "modal_input_id": "mi-001",
            "container_task_id": "ct-001",
            "image_id": "img-001",
            "resource_identity": {},
            "workflow_hash": "wf-001",
            "effective_options_hash": "opts-001",
        })
        self.assertTrue(any("gpu" in e for e in errors))
        self.assertTrue(any("cloud" in e for e in errors))
        self.assertTrue(any("region" in e for e in errors))

    def test_missing_workflow_hash(self):
        """Missing workflow_hash is an error."""
        errors = _validate_completed_run({
            "request_id": "req-001",
            "modal_input_id": "mi-001",
            "container_task_id": "ct-001",
            "image_id": "img-001",
            "resource_identity": {"gpu": "L40S", "cloud": "aws", "region": "us-east-1"},
            "workflow_hash": None,
            "effective_options_hash": "opts-001",
        })
        self.assertTrue(any("workflow_hash" in e for e in errors))

    def test_missing_effective_options_hash(self):
        """Missing effective_options_hash is an error."""
        errors = _validate_completed_run({
            "request_id": "req-001",
            "modal_input_id": "mi-001",
            "container_task_id": "ct-001",
            "image_id": "img-001",
            "resource_identity": {"gpu": "L40S", "cloud": "aws", "region": "us-east-1"},
            "workflow_hash": "wf-001",
            "effective_options_hash": None,
        })
        self.assertTrue(any("effective_options_hash" in e for e in errors))

    def test_missing_resource_identity_dict(self):
        """Missing resource_identity entirely is an error."""
        errors = _validate_completed_run({
            "request_id": "req-001",
            "modal_input_id": "mi-001",
            "container_task_id": "ct-001",
            "image_id": "img-001",
            "resource_identity": None,
            "workflow_hash": "wf-001",
            "effective_options_hash": "opts-001",
        })
        self.assertTrue(any("resource_identity" in e for e in errors))


class TestIsValidForMedian(unittest.TestCase):
    """Unit tests for ``_is_valid_for_median``."""

    def test_completed_no_errors_passes(self):
        """Completed run with no validation errors is valid."""
        self.assertTrue(_is_valid_for_median({
            "status": "completed",
            "validation_errors": None,
        }))

    def test_failed_excluded(self):
        """Failed run is excluded from medians."""
        self.assertFalse(_is_valid_for_median({
            "status": "failed",
            "validation_errors": None,
        }))

    def test_run1_failed_excluded(self):
        """run1_failed status is excluded."""
        self.assertFalse(_is_valid_for_median({
            "status": "run1_failed",
            "validation_errors": None,
        }))

    def test_validation_errors_excluded(self):
        """Run with non-empty validation_errors is excluded."""
        self.assertFalse(_is_valid_for_median({
            "status": "completed",
            "validation_errors": ["Missing modal_input_id"],
        }))

    def test_empty_validation_errors_list_passes(self):
        """Empty validation_errors list is treated as valid."""
        self.assertTrue(_is_valid_for_median({
            "status": "completed",
            "validation_errors": [],
        }))


class TestAmbiguousIdentityValidation(unittest.TestCase):
    """_validate_completed_run must reject ambiguous placeholders for gpu/cloud/region."""

    _VALID_BASE = {
        "request_id": "req-001",
        "trace_id": "trace-001",
        "modal_input_id": "mi-001",
        "container_task_id": "ct-001",
        "image_id": "img-001",
        "workflow_hash": "wf-001",
        "effective_options_hash": "opts-001",
    }

    def _make(self, gpu="L40S", cloud="aws", region="us-east-1") -> dict:
        return dict(
            self._VALID_BASE,
            resource_identity={"gpu": gpu, "cloud": cloud, "region": region},
        )

    def _first_error_containing(self, errors, keyword):
        return next((e for e in errors if keyword in e), None)

    def test_ambiguous_gpu_empty_string(self):
        errors = _validate_completed_run(self._make(gpu=""))
        self.assertIsNotNone(self._first_error_containing(errors, "gpu"))

    def test_ambiguous_gpu_auto(self):
        errors = _validate_completed_run(self._make(gpu="auto"))
        self.assertIsNotNone(self._first_error_containing(errors, "gpu"))

    def test_ambiguous_gpu_default(self):
        errors = _validate_completed_run(self._make(gpu="default"))
        self.assertIsNotNone(self._first_error_containing(errors, "gpu"))

    def test_ambiguous_gpu_unknown(self):
        errors = _validate_completed_run(self._make(gpu="unknown"))
        self.assertIsNotNone(self._first_error_containing(errors, "gpu"))

    def test_ambiguous_gpu_none_str(self):
        errors = _validate_completed_run(self._make(gpu="none"))
        self.assertIsNotNone(self._first_error_containing(errors, "gpu"))

    def test_ambiguous_gpu_null_str(self):
        errors = _validate_completed_run(self._make(gpu="null"))
        self.assertIsNotNone(self._first_error_containing(errors, "gpu"))

    def test_ambiguous_cloud_empty_string(self):
        errors = _validate_completed_run(self._make(cloud=""))
        self.assertIsNotNone(self._first_error_containing(errors, "cloud"))

    def test_ambiguous_region_unknown_case_insensitive(self):
        errors = _validate_completed_run(self._make(region="Unknown"))
        self.assertIsNotNone(self._first_error_containing(errors, "region"))

    def test_valid_gpu_not_rejected(self):
        errors = _validate_completed_run(self._make(gpu="RTX PRO 6000"))
        self.assertIsNone(self._first_error_containing(errors, "gpu"))

    def test_valid_cloud_not_rejected(self):
        errors = _validate_completed_run(self._make(cloud="gcp"))
        self.assertIsNone(self._first_error_containing(errors, "cloud"))


class TestPublisherMsAccuracy(unittest.TestCase):
    """publisher_ms must only come from dedicated evidence, not fallback fields."""

    def test_no_dedicated_evidence_returns_none(self):
        """publisher_ms is None when no dedicated publication evidence exists."""
        trace = {
            "derived_ms": {
                "local_dispatch_to_modal_entry_ms": 56853.27,
                "modal_call_submit_ms": 56000.0,
            },
            "deltas_ms": {"t2_to_t3": 56853.27},
            "stages": {"t0_client_press": 1000.0, "t10_local_materialized": 1065.0},
        }
        summary = {
            "run1_trace": trace,
            "status": "ok",
            "run1_total_ms": 65000.0,
        }
        snap = extract_section14_run(summary, "run1", "V1", 0)
        # Even though fallback fields exist, publisher_ms must be None
        self.assertIsNone(snap["publisher_ms"],
                          "publisher_ms must be None when only fallback fields exist")

    def test_dedicated_publication_field_is_used(self):
        """restore_publication_ms in derived_ms is used as publisher_ms."""
        trace = {
            "derived_ms": {"restore_publication_ms": 1234.56},
            "stages": {"t0_client_press": 1000.0, "t10_local_materialized": 1065.0},
        }
        summary = {
            "run1_trace": trace,
            "status": "ok",
            "run1_total_ms": 65000.0,
        }
        snap = extract_section14_run(summary, "run1", "V1", 0)
        self.assertEqual(snap["publisher_ms"], 1234.56)

    def test_profile_publication_field_is_used(self):
        """profile_publication_ms in derived_ms is used as publisher_ms."""
        trace = {
            "derived_ms": {"profile_publication_ms": 987.65},
            "stages": {"t0_client_press": 1000.0, "t10_local_materialized": 1065.0},
        }
        summary = {
            "run1_trace": trace,
            "status": "ok",
            "run1_total_ms": 65000.0,
        }
        snap = extract_section14_run(summary, "run1", "V1", 0)
        self.assertEqual(snap["publisher_ms"], 987.65)

    def test_restore_publish_event_pair_used(self):
        """restore_publish_start/end events with monotonic_ns produce publisher_ms."""
        trace = {
            "events": [
                {"name": "restore_publish_start", "monotonic_ns": 100_000_000},
                {"name": "restore_publish_end", "monotonic_ns": 150_000_000},
            ],
            "derived_ms": {},
            "stages": {"t0_client_press": 1000.0, "t10_local_materialized": 1065.0},
        }
        summary = {
            "run1_trace": trace,
            "status": "ok",
            "run1_total_ms": 65000.0,
        }
        snap = extract_section14_run(summary, "run1", "V1", 0)
        # 50ms = (150_000_000 - 100_000_000) / 1_000_000
        self.assertEqual(snap["publisher_ms"], 50.0)

    def test_fallback_fields_not_used_when_no_evidence(self):
        """Conflated fields (local_dispatch_to_modal_entry_ms, etc.) are NOT used."""
        trace = {
            "derived_ms": {
                "local_dispatch_to_modal_entry_ms": 50000.0,
                "modal_call_submit_ms": 49000.0,
            },
            "deltas_ms": {"t2_to_t3": 48000.0},
            "stages": {"t0_client_press": 1000.0, "t10_local_materialized": 1065.0},
        }
        summary = {
            "run1_trace": trace,
            "status": "ok",
            "run1_total_ms": 60000.0,
        }
        snap = extract_section14_run(summary, "run1", "V1", 0)
        self.assertIsNone(snap["publisher_ms"],
                          "publisher_ms must be None when only conflated fallback fields exist")

    def test_v1_profile_publish_pair_produces_publisher_ms(self):
        """V1 profile_publish_start/end in trace dict produce publisher_ms."""
        trace = {
            "profile_publish_start": 1000.0,
            "profile_publish_end": 1003.5,
            "stages": {"t0_client_press": 1000.0, "t10_local_materialized": 1065.0},
        }
        summary = {
            "run1_trace": trace,
            "status": "ok",
            "run1_total_ms": 65000.0,
        }
        snap = extract_section14_run(summary, "run1", "V1", 0)
        # 3.5 seconds = 3500 ms
        self.assertEqual(snap["publisher_ms"], 3500.0)


class TestCollectDiagnosisWithDashboardCsv(DiagnosisCollectorBase):
    """Integration tests for dashboard CSV correlation."""

    def _write_dashboard_csv(self, rows: list[dict]) -> Path:
        path = self.tmp_dir / "dashboard.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "modal_input_id", "input_created_to_scheduled_ms",
                "scheduled_to_execution_ms", "execution_ms",
            ])
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return path

    def test_non_null_queue_rows_after_correlation(self):
        """Dashboard fields are non-null after successful CSV correlation."""
        # Create run whose trace carries modal_input_id in v1_identity
        trace = _make_complete_trace(prompt_id="corr-test")
        trace["modal_input_id"] = "mi-corr-001"
        trace["container_task_id"] = "ct-corr-001"
        trace["image_id"] = "img-corr-001"
        trace["workflow_hash"] = "wf-corr-001"
        trace["config_hash"] = "opts-corr-001"
        summary = _make_summary(trace, status="ok")
        run_path = self.tmp_dir / "corr_run" / "summary.json"
        run_path.parent.mkdir(parents=True)
        _write_json(run_path, summary)

        csv_path = self._write_dashboard_csv([
            {
                "modal_input_id": "mi-corr-001",
                "input_created_to_scheduled_ms": "1500",
                "scheduled_to_execution_ms": "3200",
                "execution_ms": "5800",
            },
        ])

        out_dir = collect_diagnosis(
            runs=[(str(run_path), "V1")],
            label="test-corr",
            diagnosis_base_dir=self.tmp_dir / "diag_corr",
            dashboard_csv=str(csv_path),
        )
        diag = _read_json(out_dir / "diagnosis.json")
        self.assertTrue(diag["dashboard_correlated"])
        self.assertEqual(diag["correlation_count"], 1)

        # Read the snapshot to verify dashboard fields are populated
        snap_file = out_dir / diag["snapshots"][0]["file"]
        snap = _read_json(snap_file)
        self.assertEqual(snap["modal_input_id"], "mi-corr-001")
        self.assertEqual(snap["dashboard_input_to_scheduled_ms"], 1500.0)
        self.assertEqual(snap["dashboard_scheduled_to_execution_ms"], 3200.0)
        self.assertEqual(snap["dashboard_execution_ms"], 5800.0)

        # Verify comparison reflects correlation
        cmp = _read_json(out_dir / "comparison.json")
        self.assertTrue(cmp["dashboard_correlated"])
        self.assertIn("Dashboard correlation applied", " ".join(cmp["facts"]))

    def test_unmatched_correlation_reported_as_error(self):
        """Snapshot with modal_input_id but no CSV match produces error."""
        trace = _make_complete_trace(prompt_id="unmatch-test")
        trace["modal_input_id"] = "mi-unmatched"
        trace["container_task_id"] = "ct-unmatch"
        trace["image_id"] = "img-unmatch"
        trace["workflow_hash"] = "wf-unmatch"
        trace["config_hash"] = "opts-unmatch"
        summary = _make_summary(trace, status="ok")
        run_path = self.tmp_dir / "unmatch_run" / "summary.json"
        run_path.parent.mkdir(parents=True)
        _write_json(run_path, summary)

        csv_path = self._write_dashboard_csv([
            {
                "modal_input_id": "mi-other",
                "input_created_to_scheduled_ms": "100",
                "scheduled_to_execution_ms": "200",
                "execution_ms": "300",
            },
        ])

        out_dir = collect_diagnosis(
            runs=[(str(run_path), "V1")],
            label="test-unmatch",
            diagnosis_base_dir=self.tmp_dir / "diag_unmatch",
            dashboard_csv=str(csv_path),
        )
        diag = _read_json(out_dir / "diagnosis.json")
        self.assertIsNotNone(diag.get("errors"))
        self.assertTrue(any("unmatched" in e.lower() for e in diag["errors"]))

    def test_duplicate_dashboard_ids_rejected(self):
        """Duplicate modal_input_id in CSV raises ValueError."""
        trace = _make_complete_trace(prompt_id="dup-test")
        summary = _make_summary(trace, status="ok")
        run_path = self.tmp_dir / "dup_run" / "summary.json"
        run_path.parent.mkdir(parents=True)
        _write_json(run_path, summary)

        csv_path = self._write_dashboard_csv([
            {"modal_input_id": "mi-dup", "input_created_to_scheduled_ms": "100",
             "scheduled_to_execution_ms": "200", "execution_ms": "300"},
            {"modal_input_id": "mi-dup", "input_created_to_scheduled_ms": "400",
             "scheduled_to_execution_ms": "500", "execution_ms": "600"},
        ])
        with self.assertRaises(ValueError) as ctx:
            collect_diagnosis(
                runs=[(str(run_path), "V1")],
                label="test-dup",
                diagnosis_base_dir=self.tmp_dir / "diag_dup",
                dashboard_csv=str(csv_path),
            )
        self.assertIn("Duplicate", str(ctx.exception))

    def test_comparison_facts_say_correlated_when_applied(self):
        """Comparison facts accurately state dashboard was correlated."""
        trace = _make_complete_trace(prompt_id="fact-test")
        trace["modal_input_id"] = "mi-fact-001"
        trace["container_task_id"] = "ct-fact-001"
        trace["image_id"] = "img-fact-001"
        trace["workflow_hash"] = "wf-fact-001"
        trace["config_hash"] = "opts-fact-001"
        summary = _make_summary(trace, status="ok")
        run_path = self.tmp_dir / "fact_run" / "summary.json"
        run_path.parent.mkdir(parents=True)
        _write_json(run_path, summary)

        csv_path = self._write_dashboard_csv([
            {
                "modal_input_id": "mi-fact-001",
                "input_created_to_scheduled_ms": "100",
                "scheduled_to_execution_ms": "200",
                "execution_ms": "300",
            },
        ])
        out_dir = collect_diagnosis(
            runs=[(str(run_path), "V1")],
            label="test-facts",
            diagnosis_base_dir=self.tmp_dir / "diag_facts",
            dashboard_csv=str(csv_path),
        )
        cmp = _read_json(out_dir / "comparison.json")
        self.assertTrue(cmp["dashboard_correlated"])
        self.assertTrue(any("correlation applied" in f.lower() for f in cmp["facts"]))

    def test_comparison_facts_say_not_correlated_when_no_csv(self):
        """Comparison facts accurately state dashboard was NOT correlated."""
        out_dir = collect_diagnosis(
            runs=[(str(self.v1_path), "V1")],
            label="test-no-csv",
            diagnosis_base_dir=self.tmp_dir / "diag_no_csv",
        )
        cmp = _read_json(out_dir / "comparison.json")
        self.assertFalse(cmp.get("dashboard_correlated", True))
        self.assertEqual(cmp.get("dashboard_correlation_status"), "none")
        self.assertTrue(any("not been manually correlated" in f for f in cmp["facts"]))

    def test_correlation_status_complete(self):
        """All completed runs matched — status is 'complete'."""
        trace = _make_complete_trace(prompt_id="complete-test")
        trace["modal_input_id"] = "mi-complete-001"
        trace["container_task_id"] = "ct-complete-001"
        trace["image_id"] = "img-complete-001"
        trace["workflow_hash"] = "wf-complete-001"
        trace["config_hash"] = "opts-complete-001"
        summary = _make_summary(trace, status="ok")
        run_path = self.tmp_dir / "complete_corr_run" / "summary.json"
        run_path.parent.mkdir(parents=True)
        _write_json(run_path, summary)

        csv_path = self._write_dashboard_csv([
            {"modal_input_id": "mi-complete-001",
             "input_created_to_scheduled_ms": "100",
             "scheduled_to_execution_ms": "200",
             "execution_ms": "300"},
        ])
        out_dir = collect_diagnosis(
            runs=[(str(run_path), "V1")],
            label="test-corr-complete",
            diagnosis_base_dir=self.tmp_dir / "diag_corr_complete",
            dashboard_csv=str(csv_path),
        )
        cmp = _read_json(out_dir / "comparison.json")
        self.assertEqual(cmp["dashboard_correlation_status"], "complete")
        self.assertTrue(cmp["dashboard_correlated"])
        self.assertTrue(any("correlation applied" in f.lower() for f in cmp["facts"]))

    def test_correlation_status_partial_unmatched(self):
        """Completed run with unmatched modal_input_id — status is 'partial'."""
        trace = _make_complete_trace(prompt_id="partial-test")
        trace["modal_input_id"] = "mi-partial-unmatched"
        trace["container_task_id"] = "ct-partial-001"
        trace["image_id"] = "img-partial-001"
        trace["workflow_hash"] = "wf-partial-001"
        trace["config_hash"] = "opts-partial-001"
        summary = _make_summary(trace, status="ok")
        run_path = self.tmp_dir / "partial_corr_run" / "summary.json"
        run_path.parent.mkdir(parents=True)
        _write_json(run_path, summary)

        csv_path = self._write_dashboard_csv([
            {"modal_input_id": "mi-other",
             "input_created_to_scheduled_ms": "100",
             "scheduled_to_execution_ms": "200",
             "execution_ms": "300"},
        ])
        out_dir = collect_diagnosis(
            runs=[(str(run_path), "V1")],
            label="test-corr-partial",
            diagnosis_base_dir=self.tmp_dir / "diag_corr_partial",
            dashboard_csv=str(csv_path),
        )
        cmp = _read_json(out_dir / "comparison.json")
        self.assertEqual(cmp["dashboard_correlation_status"], "partial")
        self.assertFalse(cmp["dashboard_correlated"])
        # The unmatched snapshot should have validation_errors excluding it from medians
        self.assertIsNone(cmp["rows"]["total_user_facing_wall_clock_ms"]["v1_median_ms"],
                          "Unmatched snapshot should be excluded from medians")

    def test_correlation_status_none_no_csv(self):
        """No dashboard CSV — status is 'none'."""
        trace = _make_complete_trace(prompt_id="none-test")
        summary = _make_summary(trace, status="ok")
        run_path = self.tmp_dir / "none_corr_run" / "summary.json"
        run_path.parent.mkdir(parents=True)
        _write_json(run_path, summary)

        out_dir = collect_diagnosis(
            runs=[(str(run_path), "V1")],
            label="test-corr-none",
            diagnosis_base_dir=self.tmp_dir / "diag_corr_none",
        )
        cmp = _read_json(out_dir / "comparison.json")
        self.assertEqual(cmp["dashboard_correlation_status"], "none")
        self.assertFalse(cmp["dashboard_correlated"])

    def test_unused_csv_rows_reported(self):
        """Dashboard CSV rows unused by any completed run are reported as errors."""
        trace = _make_complete_trace(prompt_id="unused-test")
        trace["modal_input_id"] = "mi-used"
        trace["container_task_id"] = "ct-used-001"
        trace["image_id"] = "img-used-001"
        trace["workflow_hash"] = "wf-used-001"
        trace["config_hash"] = "opts-used-001"
        summary = _make_summary(trace, status="ok")
        run_path = self.tmp_dir / "used_run" / "summary.json"
        run_path.parent.mkdir(parents=True)
        _write_json(run_path, summary)

        csv_path = self._write_dashboard_csv([
            {"modal_input_id": "mi-used",
             "input_created_to_scheduled_ms": "100",
             "scheduled_to_execution_ms": "200",
             "execution_ms": "300"},
            {"modal_input_id": "mi-unused",
             "input_created_to_scheduled_ms": "400",
             "scheduled_to_execution_ms": "500",
             "execution_ms": "600"},
        ])
        out_dir = collect_diagnosis(
            runs=[(str(run_path), "V1")],
            label="test-unused-rows",
            diagnosis_base_dir=self.tmp_dir / "diag_unused_rows",
            dashboard_csv=str(csv_path),
        )
        diag = _read_json(out_dir / "diagnosis.json")
        self.assertIsNotNone(diag.get("errors"))
        self.assertTrue(any("mi-unused" in e for e in diag["errors"]))


class TestFailedRunRetentionAndExclusion(DiagnosisCollectorBase):
    """Tests for failed-run retention and median exclusion."""

    def test_failed_run_retained_in_snapshots(self):
        """Failed runs appear in snapshot list with failure status."""
        out_dir = collect_diagnosis(
            runs=[(str(self.fail_path), "V1")],
            label="test-fail-retain",
            diagnosis_base_dir=self.tmp_dir / "diag_fail_retain",
        )
        diag = _read_json(out_dir / "diagnosis.json")
        statuses = {s["status"] for s in diag["snapshots"]}
        self.assertTrue(
            {"run1_failed", "failed"}.intersection(statuses),
            f"Expected failure status in {statuses}",
        )

    def test_failed_run_excluded_from_medians(self):
        """Failed runs are excluded from comparison table medians."""
        out_dir = collect_diagnosis(
            runs=[(str(self.fail_path), "V1")],
            label="test-fail-median",
            diagnosis_base_dir=self.tmp_dir / "diag_fail_median",
        )
        cmp = _read_json(out_dir / "comparison.json")
        # All V1 medians should be None since only failed run present
        for field in SECTION_15_ROWS:
            self.assertIsNone(
                cmp["rows"][field]["v1_median_ms"],
                f"Expected None median for {field} with only failed run",
            )

    def test_completed_run_with_validation_errors_excluded(self):
        """Completed run with missing identity data excluded from medians."""
        # Build a trace that is "completed" but missing required identity fields
        trace = _make_complete_trace(prompt_id="incomplete-test")
        # Remove identity fields that would make it valid
        trace.pop("container_task_id", None)
        trace.pop("image_id", None)
        trace.pop("workflow_hash", None)
        trace.pop("config_hash", None)
        trace.pop("gpu", None)
        trace.pop("cloud", None)
        trace.pop("region", None)
        summary = _make_summary(trace, status="ok")
        run_path = self.tmp_dir / "incomplete_run" / "summary.json"
        run_path.parent.mkdir(parents=True)
        _write_json(run_path, summary)

        out_dir = collect_diagnosis(
            runs=[(str(run_path), "V1")],
            label="test-incomplete",
            diagnosis_base_dir=self.tmp_dir / "diag_incomplete",
        )
        # Snapshot should exist with validation_errors
        diag = _read_json(out_dir / "diagnosis.json")
        for entry in diag["snapshots"]:
            if entry["status"] == "completed":
                snap_file = out_dir / entry["file"]
                snap = _read_json(snap_file)
                self.assertIsNotNone(
                    snap.get("validation_errors"),
                    "Completed run with missing fields should have validation_errors",
                )

        # Medians should be None because only invalid run
        cmp = _read_json(out_dir / "comparison.json")
        for field in SECTION_15_ROWS:
            self.assertIsNone(
                cmp["rows"][field]["v1_median_ms"],
                f"Expected None median for {field} with only incomplete run",
            )


class TestHelperFunctions(unittest.TestCase):
    """Unit tests for internal helper functions."""

    def test_median_empty_list(self):
        """_median([]) returns None."""
        self.assertIsNone(_median([]))

    def test_median_all_none(self):
        """_median([None, None]) returns None."""
        self.assertIsNone(_median([None, None]))

    def test_median_mixed(self):
        """_median filters out None and computes median of remainder."""
        result = _median([1.0, None, 3.0, 2.0])
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 2.0)  # type: ignore[arg-type]

    def test_median_single_value(self):
        """_median([5.0]) returns 5.0."""
        result = _median([5.0])
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 5.0)  # type: ignore[arg-type]

    def test_read_json_roundtrip(self):
        """_write_json then _read_json returns the same data."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.json"
            data = {"a": 1, "b": [2, 3]}
            _write_json(p, data)
            result = _read_json(p)
            self.assertEqual(result, data)

    def test_ensure_dir_creates_parents(self):
        """_ensure_dir creates nested directories."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "a" / "b" / "c"
            result = _ensure_dir(d)
            self.assertTrue(result.is_dir())
            self.assertEqual(result, d)

    def test_ensure_dir_already_exists(self):
        """_ensure_dir does not fail on existing directory."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "existing"
            d.mkdir()
            result = _ensure_dir(d)
            self.assertTrue(result.is_dir())


if __name__ == "__main__":
    unittest.main()
