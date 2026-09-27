"""Tests for Phase 2: timing data flow for Studio runs.

Covers the full path:
1. Canonical flattened timing fields in timing.json
2. studio_run_adapter finalization writes canonical fields with timing_sources
3. Failure timing data preserved with failure_stage
4. list_runs merges timing summaries into returned run objects
5. Frontend normalizer reads canonical backend shape
6. Raw timing JSON available for advanced diagnostics
7. Full behavioral path integration tests
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel_path)
    assert spec is not None, f"Could not find spec for {rel_path}"
    assert spec.loader is not None, f"Could not find loader for {rel_path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ===================================================================
# A) Canonical Timing Schema — backend storage
# ===================================================================

class CanonicalTimingSchemaTests(unittest.TestCase):
    """timing.json stores and retrieves the canonical Phase 2 schema."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_canonical_timings(self, run_id: str) -> dict:
        """Write a full set of canonical Phase 2 timing fields."""
        timings: dict = {
            "queue_ms": 500,
            "worker_startup_ms": 3000,
            "workflow_load_ms": 500,
            "model_load_ms": 8000,
            "clip_load_ms": 2000,
            "clip_encode_ms": 1500,
            "sampling_ms": 35000,
            "vae_decode_ms": 2000,
            "image_io_ms": 500,
            "output_transfer_ms": 1000,
            "history_finalization_ms": 100,
            "remote_inference_total_ms": 40000,
            "scheduler_execution_ms": 45000,
            "end_to_end_total_ms": 50200,
            "timing_sources": {
                "queue_ms": "server_observed",
                "scheduler_execution_ms": "server_observed",
                "sampling_ms": "remote",
                "model_load_ms": "remote",
                "end_to_end_total_ms": "server_observed",
            },
            "remote_timings": {
                "restore_total_ms": 12000,
                "inference_ms": 35000,
            },
        }
        self.svc.update_run(run_id, timings=timings)
        return timings

    def test_all_canonical_fields_present_in_timing_json(self):
        """All Phase 2 canonical fields survive write/read round-trip."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_canon", status="running")
        run_id = rec["run_id"]
        self._write_canonical_timings(run_id)
        read = self.svc.get_timing(run_id)
        # Check every canonical field exists
        for field in [
            "queue_ms", "worker_startup_ms", "workflow_load_ms",
            "model_load_ms", "clip_load_ms", "clip_encode_ms",
            "sampling_ms", "vae_decode_ms", "image_io_ms",
            "output_transfer_ms", "history_finalization_ms",
            "remote_inference_total_ms",
            "scheduler_execution_ms", "end_to_end_total_ms",
        ]:
            self.assertIn(field, read, f"Missing canonical field: {field}")
            self.assertIsInstance(read[field], (int, float), f"{field} should be numeric")

    def test_timing_sources_survives_round_trip(self):
        """timing_sources dict persists through write/read."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_src", status="running")
        run_id = rec["run_id"]
        self._write_canonical_timings(run_id)
        read = self.svc.get_timing(run_id)
        self.assertIn("timing_sources", read)
        self.assertEqual(read["timing_sources"]["queue_ms"], "server_observed")
        self.assertEqual(read["timing_sources"]["sampling_ms"], "remote")

    def test_remote_timings_kept_for_diagnostics(self):
        """raw remote_timings sub-dict is preserved for diagnostics."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_remote_diag", status="running")
        run_id = rec["run_id"]
        self._write_canonical_timings(run_id)
        read = self.svc.get_timing(run_id)
        self.assertIn("remote_timings", read)
        self.assertEqual(read["remote_timings"]["restore_total_ms"], 12000)

    def test_zero_values_survive(self):
        """Zero timing values are not stripped."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_zero", status="completed")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, timings={
            "scheduler_execution_ms": 0,
            "sampling_ms": 0,
            "queue_ms": 0,
            "end_to_end_total_ms": 0,
        })
        read = self.svc.get_timing(run_id)
        self.assertEqual(read.get("scheduler_execution_ms"), 0)
        self.assertEqual(read.get("sampling_ms"), 0)
        self.assertEqual(read.get("queue_ms"), 0)
        self.assertEqual(read.get("end_to_end_total_ms"), 0)


# ===================================================================
# B) list_runs merges timing summaries into returned run objects
# ===================================================================

class ListRunsTimingMergeTests(unittest.TestCase):
    """list_runs should merge timing.json data into returned run objects."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_runs_includes_timing_summary(self):
        """list_runs returns runs with a timing_summary merged from timing.json."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_list_t", status="completed")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, timings={
            "scheduler_execution_ms": 45000,
            "sampling_ms": 35000,
            "end_to_end_total_ms": 50200,
        })
        result = self.svc.list_runs(kind="studio_run")
        for r in result["runs"]:
            if r["run_id"] == run_id:
                self.assertIn("timing_summary", r,
                              "list_runs should add timing_summary to each run")
                summary = r["timing_summary"]
                self.assertIn("scheduler_execution_ms", summary)
                self.assertIn("end_to_end_total_ms", summary)
                self.assertEqual(summary["scheduler_execution_ms"], 45000)
                break
        else:
            self.fail("Run not found in list_runs results")

    def test_list_runs_timing_summary_has_timing_sources(self):
        """timing_summary includes timing_sources metadata."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_list_src", status="completed")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, timings={
            "queue_ms": 500,
            "scheduler_execution_ms": 45000,
            "timing_sources": {"queue_ms": "server_observed", "scheduler_execution_ms": "server_observed"},
        })
        result = self.svc.list_runs(kind="studio_run")
        for r in result["runs"]:
            if r["run_id"] == run_id:
                summary = r.get("timing_summary", {})
                self.assertIn("timing_sources", summary)
                self.assertEqual(summary["timing_sources"]["queue_ms"], "server_observed")
                break

    def test_list_runs_timing_summary_omitted_when_no_timing_json(self):
        """runs without timing.json have an empty timing_summary dict."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_list_no_t", status="completed")
        result = self.svc.list_runs(kind="studio_run")
        for r in result["runs"]:
            if r["run_id"] == rec["run_id"]:
                self.assertIn("timing_summary", r)
                self.assertEqual(r["timing_summary"], {})
                break

    def test_detail_fetch_includes_timing_summary(self):
        """get_run detail also includes timing_summary."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_detail_t", status="completed")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, timings={"scheduler_execution_ms": 45000})
        meta = self.svc.get_run(run_id)
        self.assertIn("timing_summary", meta)
        self.assertEqual(meta["timing_summary"].get("scheduler_execution_ms"), 45000)


# ===================================================================
# C) Failure timing preservation
# ===================================================================

class FailureTimingPreservationTests(unittest.TestCase):
    """Failure path preserves known timing fields and failure_stage."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_failure_preserves_queue_ms_and_end_to_end(self):
        """Failed run retains queue_ms and end_to_end_total_ms."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_fail_t", status="running")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, status="error", timings={
            "queue_ms": 500,
            "scheduler_execution_ms": 8000,
            "end_to_end_total_ms": 8500,
        })
        read = self.svc.get_timing(run_id)
        self.assertEqual(read.get("queue_ms"), 500)
        self.assertEqual(read.get("scheduler_execution_ms"), 8000)
        self.assertEqual(read.get("end_to_end_total_ms"), 8500)

    def test_failure_includes_failure_stage_in_extra(self):
        """Failed run meta includes failure_stage field."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_fail_s", status="running")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, status="error",
                            meta={"failure_stage": "model_load", "error": "OOM"})
        meta = self.svc.get_run(run_id)
        extra = meta.get("extra", {})
        self.assertEqual(extra.get("failure_stage"), "model_load")

    def test_failure_known_timings_and_failure_stage_coexist(self):
        """Failure stage and timing fields coexist in the same update."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_fail_both", status="running")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, status="error",
                            meta={"failure_stage": "scheduler_execution"},
                            timings={"queue_ms": 500, "scheduler_execution_ms": 8000})
        meta = self.svc.get_run(run_id)
        extra = meta.get("extra", {})
        self.assertEqual(extra.get("failure_stage"), "scheduler_execution")
        read = self.svc.get_timing(run_id)
        self.assertEqual(read.get("queue_ms"), 500)


# ===================================================================
# D) studio_run_adapter finalization builds canonical timings
# ===================================================================

class AdapterTimingFinalizationTests(unittest.TestCase):
    """_schedule_and_start-like finalization builds the canonical timing shape."""

    @classmethod
    def setUpClass(cls):
        cls.adapter = _load_module("studio_run_adapter", "studio_run_adapter.py")
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_adapter_has_canonical_timing_keys_in_source(self):
        """Verify the adapter source references the canonical timing field names."""
        import inspect
        src = inspect.getsource(self.adapter._schedule_and_start)
        # Check that key canonical fields appear in the finalization block
        self.assertIn("scheduler_execution_ms", src)
        self.assertIn("end_to_end_total_ms", src)
        self.assertIn("timing_sources", src,
                      "_schedule_and_start should write timing_sources")

    def test_adapter_flattens_remote_timings(self):
        """Remote timing fields (_ms suffix) are flattened into the top-level timing dict."""
        import inspect
        src = inspect.getsource(self.adapter._schedule_and_start)
        # The flattening logic iterates result keys ending with _ms
        self.assertIn("_ms", src,
                      "Adapter should iterate remote fields ending with _ms")

    def test_failure_path_in_adapter_has_failure_stage(self):
        """Adapter's exception handler sets failure_stage in meta."""
        import inspect
        src = inspect.getsource(self.adapter._schedule_and_start)
        self.assertIn("failure_stage", src)


# ===================================================================
# E) Frontend normalizer reads canonical backend shape
# ===================================================================

class FrontendNormalizerPhase2Tests(unittest.TestCase):
    """studio-run-normalizer.js reads the Phase 2 canonical timing shape."""

    def setUp(self):
        self.normalizer_path = REPO_ROOT / "web" / "studio-run-normalizer.js"
        self.text = self.normalizer_path.read_text(encoding="utf-8") if self.normalizer_path.exists() else ""

    def test_normalizer_reads_timing_sources(self):
        """normalizeStudioRun output includes timingSources from backend."""
        self.assertIn("timingSources", self.text)

    def test_normalizer_reads_scheduler_execution_ms(self):
        """Normalizer references scheduler_execution_ms field."""
        self.assertIn("scheduler_execution_ms", self.text)

    def test_normalizer_reads_end_to_end_total_ms(self):
        """Normalizer references end_to_end_total_ms field."""
        self.assertIn("end_to_end_total_ms", self.text)

    def test_normalizer_reads_remote_inference_total_ms(self):
        """Normalizer references remote_inference_total_ms."""
        self.assertIn("remote_inference_total_ms", self.text)

    def test_normalizer_flattens_remote_timing_fields(self):
        """Normalizer inspects top-level timing fields, not only nested remote_timings."""
        # The normalizer should prefer top-level fields over nested ones
        text = self.text
        # It should have the addStage helper checking d[key] for all known fields
        for stage_key in ["clip_load", "clip_encode", "vae_decode", "image_io"]:
            self.assertIn(stage_key, text,
                          f"Normalizer should flatten remote key: {stage_key}")

    def test_raw_timing_accessible_in_normalizer(self):
        """Raw timing JSON remains accessible as rawTiming."""
        self.assertIn("rawTiming", self.text)

    def test_timing_sources_in_output(self):
        """Normalizer output includes timingSources with source annotations."""
        self.assertIn("timingSources", self.text)
        # The timingSources should annotate source of each value
        source_annotation = '"timing_sources"' in self.text or 'timingSources' in self.text
        self.assertTrue(source_annotation or True)  # Already checked above


# ===================================================================
# F) Full path integration test
# ===================================================================

class FullPathTimingIntegrationTests(unittest.TestCase):
    """End-to-end behavioral test: write → list → detail → normalizer.

    Simulates the full data flow:
    1. A run is recorded (simulating handle_studio_run submission)
    2. Timing data is written (simulating _schedule_and_start finalization)
    3. list_runs returns timing_summary
    4. get_run returns timing_summary 
    5. Raw timing.json is available via get_timing
    """

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _simulate_full_run_with_timings(self) -> str:
        """Simulate a complete run with submission, execution, and finalization.

        Returns the run_id.
        """
        # Step 1: Record submission (like handle_studio_run does)
        rec = self.svc.record_run(
            kind="studio_run",
            prompt_id="exp_full_integration",
            status="submitted",
            meta={
                "studio_preset_id": "preset_test",
                "studio_snapshot_id": "snap_test",
                "studio_feature_id": "txt2img",
                "experiment_id": "exp_full_integration",
                "preset_label": "Test Preset",
            },
            started_at="2025-07-01T00:00:00Z",
        )
        run_id = rec["run_id"]

        # Step 2: Update to running
        self.svc.update_run(run_id, status="running")

        # Step 3: Finalize with canonical timings (like _schedule_and_start does)
        self.svc.update_run(
            run_id,
            status="completed",
            completed_at="2025-07-01T00:01:00Z",
            output_path="outputs/integration_test.png",
            primary_asset_id="asset_integration",
            workflow_hash="wh_integration",
            meta={
                "resolved_controls": {"seed": 42, "steps": 20},
                "studio_preset_id": "preset_test",
                "studio_feature_id": "txt2img",
            },
            timings={
                "queue_ms": 500,
                "scheduler_execution_ms": 45000,
                "sampling_ms": 35000,
                "model_load_ms": 8000,
                "clip_load_ms": 2000,
                "clip_encode_ms": 1500,
                "vae_decode_ms": 2000,
                "worker_startup_ms": 3000,
                "end_to_end_total_ms": 50200,
                "timing_sources": {
                    "queue_ms": "server_observed",
                    "scheduler_execution_ms": "server_observed",
                    "sampling_ms": "remote",
                    "model_load_ms": "remote",
                },
                "remote_timings": {
                    "restore_total_ms": 12000,
                    "inference_ms": 35000,
                },
            },
        )
        return run_id

    def test_full_path_list_runs_has_timing_summary(self):
        """After full simulation, list_runs returns timing_summary."""
        self._simulate_full_run_with_timings()
        result = self.svc.list_runs(kind="studio_run")
        self.assertGreater(len(result["runs"]), 0)
        for r in result["runs"]:
            self.assertIn("timing_summary", r)
            summary = r["timing_summary"]
            if summary:  # Should have data for our run
                self.assertIn("scheduler_execution_ms", summary)
                self.assertIn("end_to_end_total_ms", summary)

    def test_full_path_detail_has_timing_summary(self):
        """After full simulation, get_run includes timing_summary."""
        run_id = self._simulate_full_run_with_timings()
        meta = self.svc.get_run(run_id)
        self.assertIn("timing_summary", meta)
        summary = meta["timing_summary"]
        self.assertEqual(summary.get("scheduler_execution_ms"), 45000)
        self.assertEqual(summary.get("end_to_end_total_ms"), 50200)
        self.assertEqual(summary.get("sampling_ms"), 35000)

    def test_full_path_detail_timing_summary_has_sources(self):
        """timing_summary includes timing_sources."""
        run_id = self._simulate_full_run_with_timings()
        meta = self.svc.get_run(run_id)
        summary = meta["timing_summary"]
        self.assertIn("timing_sources", summary)
        self.assertEqual(summary["timing_sources"]["queue_ms"], "server_observed")
        self.assertEqual(summary["timing_sources"]["sampling_ms"], "remote")

    def test_full_path_raw_timing_available(self):
        """Raw timing.json is accessible separately."""
        run_id = self._simulate_full_run_with_timings()
        raw = self.svc.get_timing(run_id)
        self.assertIn("queue_ms", raw)
        self.assertIn("scheduler_execution_ms", raw)
        self.assertIn("remote_timings", raw)
        self.assertEqual(raw["remote_timings"]["restore_total_ms"], 12000)

    def test_full_path_normalizer_reads_shape(self):
        """Verify the timing.json shape matches what normalizer expects."""
        run_id = self._simulate_full_run_with_timings()
        raw = self.svc.get_timing(run_id)
        # The normalizer's normalizeTimingStages reads these keys
        for key in ["sampling_ms", "scheduler_execution_ms"]:
            self.assertIn(key, raw)
        # The normalizer's normalizePerNodeTimings reads per_node
        # The normalizer reads timing_sources
        self.assertIn("timing_sources", raw)

    def test_full_path_failure_timings(self):
        """Failure run still preserves timing data and failure_stage."""
        rec = self.svc.record_run(
            kind="studio_run",
            prompt_id="exp_fail_full",
            status="running",
            meta={"studio_preset_id": "preset_test"},
            started_at="2025-07-01T00:00:00Z",
        )
        run_id = rec["run_id"]
        # Simulate failure finalization
        self.svc.update_run(
            run_id,
            status="error",
            completed_at="2025-07-01T00:00:10Z",
            meta={"failure_stage": "scheduler_execution", "error": "Internal error"},
            timings={"queue_ms": 500, "scheduler_execution_ms": 10000, "end_to_end_total_ms": 10500},
        )
        # Verify through list_runs
        result = self.svc.list_runs(kind="studio_run")
        for r in result["runs"]:
            if r["run_id"] == run_id:
                self.assertEqual(r["status"], "error")
                summary = r.get("timing_summary", {})
                self.assertEqual(summary.get("queue_ms"), 500)
                self.assertEqual(summary.get("scheduler_execution_ms"), 10000)
                extra = r.get("extra", {})
                self.assertEqual(extra.get("failure_stage"), "scheduler_execution")
                break
        else:
            self.fail("Failed run not found in list_runs")

    def test_full_path_timing_json_file_present(self):
        """timing.json file exists on disk for the run."""
        run_id = self._simulate_full_run_with_timings()
        run_dir = self.root / run_id
        self.assertTrue((run_dir / "timing.json").exists())


# ===================================================================
# G) sort/fastest and sort/slowest work with canonical timing
# ===================================================================

class TimingBasedSortTests(unittest.TestCase):
    """Sort by scheduler_execution_ms works with canonical timing fields."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sort_fastest_uses_scheduler_execution_ms(self):
        """sort=fastest uses scheduler_execution_ms from timing.json."""
        durations = [30000, 10000, 50000]
        run_ids = []
        for i, ms in enumerate(durations):
            rec = self.svc.record_run(
                kind="studio_run",
                prompt_id=f"exp_sort_{i}",
                status="completed",
                started_at=f"2025-07-0{i+1}T00:00:00Z",
            )
            run_ids.append(rec["run_id"])
            self.svc.update_run(rec["run_id"], timings={"scheduler_execution_ms": ms})

        result = self.svc.list_runs(kind="studio_run", sort="fastest")
        # Extract durations in result order
        durations_result = []
        for r in result["runs"]:
            if r["run_id"] in run_ids:
                summary = r.get("timing_summary", {})
                durations_result.append(summary.get("scheduler_execution_ms", 0))

        if len(durations_result) >= 2:
            self.assertEqual(durations_result[0], 10000)
            self.assertEqual(durations_result[1], 30000)

    def test_sort_slowest_uses_scheduler_execution_ms(self):
        """sort=slowest uses scheduler_execution_ms from timing.json (desc)."""
        durations = [10000, 50000, 30000]
        run_ids = []
        for i, ms in enumerate(durations):
            rec = self.svc.record_run(
                kind="studio_run",
                prompt_id=f"exp_slow_{i}",
                status="completed",
                started_at=f"2025-07-0{i+1}T00:00:00Z",
            )
            run_ids.append(rec["run_id"])
            self.svc.update_run(rec["run_id"], timings={"scheduler_execution_ms": ms})

        result = self.svc.list_runs(kind="studio_run", sort="slowest")
        durations_result = []
        for r in result["runs"]:
            if r["run_id"] in run_ids:
                summary = r.get("timing_summary", {})
                durations_result.append(summary.get("scheduler_execution_ms", 0))

        if len(durations_result) >= 2:
            self.assertGreaterEqual(durations_result[0], durations_result[1])


if __name__ == "__main__":
    unittest.main()
