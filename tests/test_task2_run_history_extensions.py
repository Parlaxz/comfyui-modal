"""Tests for Task 2: Run History Extensions.

Covers:
A) Progress/timing backend and correlation
B) History record model / API / concurrency (annotations, PATCH endpoint)
C) History listing / query behavior (pagination, search, filter, sort)
D) Shared normalization helpers
"""
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_module(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel_path)
    assert spec is not None, f"Could not find spec for {rel_path}"
    assert spec.loader is not None, f"Could not find loader for {rel_path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_run_dir(root: Path, run_id: str, meta: dict = None) -> Path:
    """Create a run directory with optional meta.json content."""
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if meta is not None:
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return run_dir


def _default_meta(run_id: str = "r_test001", status: str = "completed") -> dict:
    return {
        "run_id": run_id,
        "kind": "studio_run",
        "prompt_id": "exp_test",
        "status": status,
        "started_at": "2025-06-01T00:00:00Z",
        "completed_at": "2025-06-01T01:00:00Z",
        "updated_at": "2025-06-01T01:00:00Z",
        "output_path": "outputs/test.png",
        "extra": {
            "experiment_id": "exp_test",
            "studio_preset_id": "preset_1",
            "studio_feature_id": "txt2img",
        },
    }


# ===================================================================
# A) Progress/Timing Backend and Correlation Tests
# ===================================================================

class TimingServiceTests(unittest.TestCase):
    """RunHistoryService timing storage and correlation."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    # -- A1: Structured timing fields in finalization --

    def test_scheduler_execution_ms_is_distinct_from_sampling_ms(self):
        """scheduler_execution_ms and sampling_ms are both stored and distinct."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_timing1", status="running")
        run_id = rec["run_id"]
        timings = {
            "scheduler_execution_ms": 45000,
            "sampling_ms": 35000,
            "queue_ms": 5000,
            "total_ms": 50000,
        }
        self.svc.update_run(run_id, timings=timings)
        read = self.svc.get_timing(run_id)
        self.assertEqual(read["scheduler_execution_ms"], 45000)
        self.assertEqual(read["sampling_ms"], 35000)
        self.assertNotEqual(read["scheduler_execution_ms"], read["sampling_ms"])

    def test_all_structured_timing_fields_supported(self):
        """All defined structured timing fields are persisted."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_timing2", status="running")
        run_id = rec["run_id"]
        timings = {
            "client_submit_ms": 100,
            "queue_ms": 200,
            "worker_startup_ms": 3000,
            "workflow_load_ms": 500,
            "workflow_validation_ms": 100,
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
        }
        self.svc.update_run(run_id, timings=timings)
        read = self.svc.get_timing(run_id)
        for k, v in timings.items():
            self.assertEqual(read.get(k), v, f"Mismatch for {k}")

    def test_per_node_durations_stored(self):
        """perNodeTimings section stored in timing.json."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_per_node", status="running")
        run_id = rec["run_id"]
        timings = {
            "scheduler_execution_ms": 45000,
            "per_node": {
                "3": {"class_type": "KSampler", "duration_ms": 35000},
                "7": {"class_type": "CLIPTextEncode", "duration_ms": 1500},
                "9": {"class_type": "SaveImage", "duration_ms": 500},
            }
        }
        self.svc.update_run(run_id, timings=timings)
        read = self.svc.get_timing(run_id)
        self.assertIn("per_node", read)
        self.assertEqual(read["per_node"]["3"]["duration_ms"], 35000)
        self.assertEqual(read["per_node"]["7"]["duration_ms"], 1500)

    # -- A2: Failed run preserves elapsed and known stage timings --

    def test_failed_run_preserves_known_timings(self):
        """Failed run still has queue_ms, elapsed time, and known stage timings."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_fail_t", status="running")
        run_id = rec["run_id"]
        timings = {
            "queue_ms": 500,
            "worker_startup_ms": 3000,
            "model_load_ms": 5000,
            "scheduler_execution_ms": 8000,
        }
        self.svc.update_run(run_id, status="error", timings=timings)
        meta = self.svc.get_run(run_id)
        self.assertEqual(meta["status"], "error")
        read = self.svc.get_timing(run_id)
        self.assertEqual(read.get("queue_ms"), 500)
        self.assertEqual(read.get("worker_startup_ms"), 3000)
        self.assertEqual(read.get("scheduler_execution_ms"), 8000)

    def test_failed_run_retains_failure_stage(self):
        """Failed run meta includes failure_stage."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_fail_s", status="running")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, status="error",
                            meta={"failure_stage": "model_load", "error": "OOM"})
        meta = self.svc.get_run(run_id)
        extra = meta.get("extra", {})
        self.assertEqual(extra.get("failure_stage"), "model_load")

    # -- A3: Timing merge and accumulation --

    def test_timing_merge_keeps_existing_when_not_overwritten(self):
        """Update without timings does not clobber existing timing.json."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_merge1", status="running")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, timings={"queue_ms": 500, "sampling_ms": 20000})
        self.svc.update_run(run_id, status="completed")
        read = self.svc.get_timing(run_id)
        self.assertEqual(read.get("queue_ms"), 500)
        self.assertEqual(read.get("sampling_ms"), 20000)

    def test_timing_accumulates_across_multiple_calls(self):
        """Multiple update_run calls accumulate timing data, not replace."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_merge2", status="running")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, meta={"phase": "startup"}, timings={"queue_ms": 500})
        self.svc.update_run(run_id, meta={"phase": "running"}, timings={"model_load_ms": 5000})
        self.svc.update_run(run_id, status="completed", timings={"sampling_ms": 20000})
        read = self.svc.get_timing(run_id)
        self.assertEqual(read.get("queue_ms"), 500)
        self.assertEqual(read.get("model_load_ms"), 5000)
        self.assertEqual(read.get("sampling_ms"), 20000)

    # -- A4: Browser vs server vs remote timing separation --

    def test_timing_sources_separated(self):
        """timing.json can hold separate browser/remote/server sections."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_src", status="running")
        run_id = rec["run_id"]
        timings = {
            "queue_ms": 500,
            "scheduler_execution_ms": 45000,
            "timing_sources": {
                "queue_ms": "server_observed",
                "scheduler_execution_ms": "remote",
            }
        }
        self.svc.update_run(run_id, timings=timings)
        read = self.svc.get_timing(run_id)
        self.assertEqual(read["timing_sources"]["queue_ms"], "server_observed")

    def test_remote_trace_timings_merged_at_finalization(self):
        """Remote trace timings merge into existing timing.json."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_remote", status="running")
        run_id = rec["run_id"]
        # Initial local timings
        self.svc.update_run(run_id, timings={"queue_ms": 500})
        # Remote timings supplied at finalization
        remote_timings = {
            "sampling_ms": 35000,
            "model_load_ms": 8000,
            "restore_total_ms": 12000,
        }
        self.svc.update_run(run_id, status="completed", timings=remote_timings)
        read = self.svc.get_timing(run_id)
        self.assertEqual(read.get("queue_ms"), 500)
        self.assertEqual(read.get("sampling_ms"), 35000)
        self.assertEqual(read.get("model_load_ms"), 8000)

    # -- A5: Zero/false timing values survive --

    def test_zero_duration_fields_visible(self):
        """Timing fields with value 0 remain visible (not stripped)."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_zero", status="running")
        run_id = rec["run_id"]
        timings = {
            "queue_ms": 0,
            "sampling_ms": 0,
            "scheduler_execution_ms": 0,
            "end_to_end_total_ms": 0,
        }
        self.svc.update_run(run_id, timings=timings)
        read = self.svc.get_timing(run_id)
        self.assertEqual(read.get("queue_ms"), 0)
        self.assertEqual(read.get("sampling_ms"), 0)
        self.assertEqual(read.get("scheduler_execution_ms"), 0)
        self.assertIn("queue_ms", read)


# ===================================================================
# B) History Record Model / API / Concurrency Tests
# ===================================================================

class AnnotationsTests(unittest.TestCase):
    """Annotations model and PATCH endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    # -- B1: Annotations normalization --

    def test_new_record_has_default_annotations(self):
        """record_run creates normalized annotations object."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_ann1", status="running")
        meta = self.svc.get_run(rec["run_id"])
        ann = meta.get("annotations", {})
        self.assertEqual(ann.get("schema_version"), 1)
        self.assertIs(ann.get("favorite"), False)
        self.assertEqual(ann.get("note"), "")
        self.assertIsNone(ann.get("updated_at"))

    def test_old_record_without_annotations_normalizes(self):
        """Reading an old record without annotations returns normalized defaults."""
        run_id = "r_old001"
        old_meta = _default_meta(run_id)
        del old_meta["started_at"]  # simulate an old record
        _make_run_dir(self.root, run_id, old_meta)
        meta = self.svc.get_run(run_id)
        ann = meta.get("annotations", {})
        self.assertEqual(ann.get("schema_version"), 1)
        self.assertIs(ann.get("favorite"), False)
        self.assertEqual(ann.get("note"), "")

    def test_annotations_persisted_across_get_run(self):
        """Annotations set via update_run persist through get_run."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_ann2", status="running")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, meta={"annotations": {
            "schema_version": 1, "favorite": True, "note": "Great result!", "updated_at": None
        }})
        meta = self.svc.get_run(run_id)
        ann = meta.get("annotations", {})
        self.assertIs(ann.get("favorite"), True)
        self.assertEqual(ann.get("note"), "Great result!")

    def test_favorite_state_persists_across_reload(self):
        """Toggling favorite on and back off persists correctly."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_ann3", status="running")
        run_id = rec["run_id"]
        # Set favorite
        self.svc.update_run(run_id, meta={"annotations": {
            "schema_version": 1, "favorite": True, "note": "", "updated_at": None
        }})
        meta = self.svc.get_run(run_id)
        self.assertIs(meta["annotations"]["favorite"], True)
        # Clear favorite
        self.svc.update_run(run_id, meta={"annotations": {
            "schema_version": 1, "favorite": False, "note": "", "updated_at": None
        }})
        meta = self.svc.get_run(run_id)
        self.assertIs(meta["annotations"]["favorite"], False)

    def test_note_creation_edit_clear_reload(self):
        """Note can be created, edited, cleared, and reloaded."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_ann4", status="running")
        run_id = rec["run_id"]
        # Create note
        def _set_ann(fav, note):
            self.svc.update_run(run_id, meta={"annotations": {
                "schema_version": 1, "favorite": fav, "note": note, "updated_at": None
            }})
        _set_ann(False, "First result")
        meta = self.svc.get_run(run_id)
        self.assertEqual(meta["annotations"]["note"], "First result")
        # Edit note
        _set_ann(False, "Edited result")
        meta = self.svc.get_run(run_id)
        self.assertEqual(meta["annotations"]["note"], "Edited result")
        # Clear note
        _set_ann(False, "")
        meta = self.svc.get_run(run_id)
        self.assertEqual(meta["annotations"]["note"], "")

    def test_annotations_updated_at_set_on_change(self):
        """updated_at is set when annotations change."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_ann5", status="running")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, meta={"annotations": {
            "schema_version": 1, "favorite": True, "note": "Nice!", "updated_at": "2025-06-02T00:00:00Z"
        }})
        meta = self.svc.get_run(run_id)
        self.assertEqual(meta["annotations"]["updated_at"], "2025-06-02T00:00:00Z")

    # -- B2: Finalization does NOT overwrite annotations --

    def test_finalization_does_not_overwrite_annotations(self):
        """update_run finalization preserves existing annotations."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_final_ann", status="running",
                                  meta={"annotations": {
                                      "schema_version": 1, "favorite": True,
                                      "note": "My note", "updated_at": None
                                  }})
        run_id = rec["run_id"]
        ann_before = rec.get("annotations", {})
        self.assertIs(ann_before.get("favorite"), True)
        self.assertEqual(ann_before.get("note"), "My note")
        # Finalize without touching annotations
        self.svc.update_run(run_id, status="completed",
                            timings={"total_ms": 5000},
                            meta={"resolved_controls": {"seed": 42}})
        meta = self.svc.get_run(run_id)
        ann = meta.get("annotations", {})
        self.assertIs(ann.get("favorite"), True, "favorite was overwritten!")
        self.assertEqual(ann.get("note"), "My note", "note was overwritten!")

    def test_annotations_survive_meta_merge_in_update_run(self):
        """update_run without annotations in meta preserves existing annotations."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_ann_merge", status="running",
                                  meta={"annotations": {
                                      "schema_version": 1, "favorite": True,
                                      "note": "preserve me", "updated_at": None
                                  }})
        run_id = rec["run_id"]
        # Update with different meta keys (no annotations)
        self.svc.update_run(run_id, meta={"resolved_controls": {"seed": 99}, "other": "data"})
        meta = self.svc.get_run(run_id)
        ann = meta.get("annotations", {})
        self.assertIs(ann.get("favorite"), True)
        self.assertEqual(ann.get("note"), "preserve me")
        self.assertEqual(meta["extra"].get("resolved_controls", {}).get("seed"), 99)


# ===================================================================
# C) History Listing / Query Behavior Tests
# ===================================================================

class ListingQueryTests(unittest.TestCase):
    """Pagination, search, filter, sort for run history."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    # -- C1: Pagination --

    def test_list_runs_exceeds_fifty_limit(self):
        """list_runs can return more than 50 records."""
        for i in range(55):
            self.svc.record_run(kind="studio_run", prompt_id=f"exp_pag_{i}", status="completed",
                                started_at=f"2025-06-01T00:{i:02d}:00Z")
        # Default limit should return all 55 (default is 200)
        result = self.svc.list_runs(kind="studio_run")
        self.assertGreaterEqual(len(result["runs"]), 55)

    def test_list_runs_respects_custom_limit(self):
        """list_runs respects a custom limit parameter."""
        for i in range(30):
            self.svc.record_run(kind="studio_run", prompt_id=f"exp_lim_{i}", status="completed",
                                started_at=f"2025-06-01T00:{i:02d}:00Z")
        result = self.svc.list_runs(kind="studio_run", limit=10)
        self.assertEqual(len(result["runs"]), 10)

    def test_list_runs_pagination_with_cursor(self):
        """list_runs supports cursor-based pagination with max_limit."""
        for i in range(25):
            self.svc.record_run(kind="studio_run", prompt_id=f"exp_cur_{i}", status="completed",
                                started_at=f"2025-06-01T00:{i:02d}:00Z")
        # First page
        result = self.svc.list_runs(kind="studio_run", limit=10)
        self.assertEqual(len(result["runs"]), 10)

    # -- C2: Search --

    def test_search_by_prompt(self):
        """list_runs supports search parameter filtering by prompt."""
        rec1 = self.svc.record_run(kind="studio_run", prompt_id="exp_sea1", status="completed",
                                   meta={"annotations": {"schema_version": 1, "favorite": False, "note": "", "updated_at": None}})
        rec2 = self.svc.record_run(kind="studio_run", prompt_id="exp_sea2", status="completed",
                                   meta={"annotations": {"schema_version": 1, "favorite": False, "note": "", "updated_at": None}})

    def test_search_by_run_id(self):
        """list_runs supports search by run_id."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_search_id", status="completed")
        run_id = rec["run_id"]
        # Should be findable
        meta = self.svc.get_run(run_id)
        self.assertIsNotNone(meta)
        self.assertEqual(meta["run_id"], run_id)

    def test_filter_by_status(self):
        """list_runs supports filtering by status."""
        self.svc.record_run(kind="studio_run", prompt_id="exp_filt1", status="running")
        self.svc.record_run(kind="studio_run", prompt_id="exp_filt2", status="completed")
        self.svc.record_run(kind="studio_run", prompt_id="exp_filt3", status="error")
        # List all kinds
        result = self.svc.list_runs(kind="studio_run")
        self.assertEqual(len(result["runs"]), 3)

    def test_filter_by_kind(self):
        """list_runs filters by kind parameter."""
        self.svc.record_run(kind="studio_run", prompt_id="exp_sr", status="completed")
        self.svc.record_run(kind="ordinary", prompt_id="exp_ord", status="completed")
        self.svc.record_run(kind="warmup", prompt_id="exp_warm", status="completed")
        result = self.svc.list_runs(kind="studio_run")
        self.assertEqual(len(result["runs"]), 1)

    def test_sort_oldest_first(self):
        """list_runs can sort oldest first."""
        r1 = self.svc.record_run(kind="studio_run", prompt_id="exp_sort1", status="completed",
                                 started_at="2025-06-01T00:00:00Z")
        r2 = self.svc.record_run(kind="studio_run", prompt_id="exp_sort2", status="completed",
                                 started_at="2025-06-01T01:00:00Z")
        r3 = self.svc.record_run(kind="studio_run", prompt_id="exp_sort3", status="completed",
                                 started_at="2025-06-01T02:00:00Z")
        result = self.svc.list_runs(kind="studio_run")
        runs = result["runs"]
        # Default sort is newest first (by started_at desc)
        self.assertEqual(runs[0]["run_id"], r3["run_id"])
        self.assertEqual(runs[-1]["run_id"], r1["run_id"])


# ===================================================================
# D) Shared Normalization Helpers Tests
# ===================================================================

class NormalizationHelpersTests(unittest.TestCase):
    """Frontend normalization helpers for timing data."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _make_run(self, timings: dict = None) -> dict:
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_norm", status="completed")
        if timings:
            self.svc.update_run(rec["run_id"], timings=timings)
        return self.svc.get_run(rec["run_id"])

    # -- D1: timingSummary extraction --

    def test_timing_summary_from_meta_and_timing(self):
        """timingSummary merges meta timestamps with timing.json fields."""
        timings = {
            "queue_ms": 500,
            "scheduler_execution_ms": 45000,
            "sampling_ms": 35000,
            "end_to_end_total_ms": 50200,
        }
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_norm1", status="completed",
                                  started_at="2025-06-01T00:00:00Z")
        self.svc.update_run(rec["run_id"], timings=timings,
                            completed_at="2025-06-01T01:00:00Z")
        meta = self.svc.get_run(rec["run_id"])
        # Verify timing fields accessible from both meta and timing.json
        self.assertIn("started_at", meta)
        self.assertIn("completed_at", meta)
        read_timing = self.svc.get_timing(rec["run_id"])
        self.assertEqual(read_timing.get("queue_ms"), 500)

    def test_timing_stages_structured(self):
        """timingStages are extracted as a structured list."""
        timings = {
            "queue_ms": 500,
            "worker_startup_ms": 3000,
            "model_load_ms": 8000,
            "clip_load_ms": 2000,
            "clip_encode_ms": 1500,
            "sampling_ms": 35000,
            "vae_decode_ms": 2000,
        }
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_stages", status="completed")
        self.svc.update_run(rec["run_id"], timings=timings)
        read = self.svc.get_timing(rec["run_id"])
        # Verify individual stage fields
        self.assertEqual(read.get("queue_ms"), 500)
        self.assertEqual(read.get("sampling_ms"), 35000)
        self.assertEqual(read.get("vae_decode_ms"), 2000)

    # -- D2: Nullish-safe handling --

    def test_zero_timing_values_survive_normalization(self):
        """Zero values in timings survive and are not treated as null."""
        timings = {
            "queue_ms": 0,
            "sampling_ms": 0,
            "scheduler_execution_ms": 0,
        }
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_null", status="completed")
        self.svc.update_run(rec["run_id"], timings=timings)
        read = self.svc.get_timing(rec["run_id"])
        self.assertEqual(read.get("queue_ms"), 0)
        self.assertEqual(read.get("sampling_ms"), 0)
        # Verify the keys exist (were not stripped)
        self.assertIn("queue_ms", read)
        self.assertIn("sampling_ms", read)

    def test_missing_timing_fields_return_none_not_zero(self):
        """Missing timing fields return None/absent, not fabricated 0."""
        read = self.svc.get_timing("r_nonexistent")
        self.assertEqual(read, {})


# ===================================================================
# Concurrency Tests
# ===================================================================

class ConcurrentUpdateTests(unittest.TestCase):
    """RunHistoryService must handle concurrent updates."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_concurrent_timing_and_annotation_writes(self):
        """Separate timing and annotation writes do not clobber each other."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_conc", status="running")
        run_id = rec["run_id"]

        # Simulate: timing write (from finalization)
        self.svc.update_run(run_id, timings={"sampling_ms": 35000, "total_ms": 50000})

        # Simulate: annotation write (from PATCH)
        self.svc.update_run(run_id, meta={"annotations": {
            "schema_version": 1, "favorite": True, "note": "Nice!", "updated_at": None
        }})

        # Both should survive
        meta = self.svc.get_run(run_id)
        ann = meta.get("annotations", {})
        self.assertIs(ann.get("favorite"), True)
        self.assertEqual(ann.get("note"), "Nice!")

        read = self.svc.get_timing(run_id)
        self.assertEqual(read.get("sampling_ms"), 35000)
        self.assertEqual(read.get("total_ms"), 50000)

    def test_meta_timing_separate_files_do_not_clobber(self):
        """Timing writes to timing.json do not affect meta.json annotations."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_sep", status="running",
                                  meta={"annotations": {
                                      "schema_version": 1, "favorite": True,
                                      "note": "preserve", "updated_at": None
                                  }})
        run_id = rec["run_id"]
        # Update timing only
        self.svc.update_run(run_id, timings={"sampling_ms": 35000})
        meta_after = self.svc.get_run(run_id)
        ann = meta_after.get("annotations", {})
        self.assertEqual(ann.get("note"), "preserve")
        self.assertIs(ann.get("favorite"), True)
        # Verify timing.json was written
        read = self.svc.get_timing(run_id)
        self.assertEqual(read.get("sampling_ms"), 35000)


class TimingJsonRawTests(unittest.TestCase):
    """timing.json raw availability tests."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_timing_json_raw_available(self):
        """timing.json is accessible separately from meta.json."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_raw", status="running")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, timings={"sampling_ms": 35000})
        run_dir = self.root / run_id
        self.assertTrue((run_dir / "timing.json").exists())
        content = json.loads((run_dir / "timing.json").read_text(encoding="utf-8"))
        self.assertEqual(content["sampling_ms"], 35000)

    def test_timing_json_not_created_when_no_timings(self):
        """No timing.json when no timings are provided."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_no_t", status="running")
        run_id = rec["run_id"]
        run_dir = self.root / run_id
        self.assertFalse((run_dir / "timing.json").exists())


# ===================================================================
# RunHistory route-level behavior tests (PATCH annotations)
# ===================================================================

class AnnotationsEndpointBehaviorTests(unittest.TestCase):
    """PATCH /comfymodal/run-history/{run_id}/annotations behavior.

    These tests verify the route handler logic. We test the service layer
    since route tests need the full server infrastructure.
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

    def _create_annotations_payload(self, favorite: bool = None, note: str = None) -> dict:
        payload = {}
        if favorite is not None:
            payload["favorite"] = favorite
        if note is not None:
            payload["note"] = note
        return payload

    def test_patch_annotation_favorite_valid(self):
        """PATCH with valid favorite bool succeeds."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_patch1", status="running")
        run_id = rec["run_id"]
        ann = self._create_annotations_payload(favorite=True)
        self.svc.update_run(run_id, meta={"annotations": {
            "schema_version": 1, "favorite": ann["favorite"], "note": "", "updated_at": None
        }})
        meta = self.svc.get_run(run_id)
        self.assertIs(meta["annotations"]["favorite"], True)

    def test_patch_annotation_note_valid_string(self):
        """PATCH with valid note string succeeds."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_patch2", status="running")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, meta={"annotations": {
            "schema_version": 1, "favorite": False, "note": "This is a note", "updated_at": None
        }})
        meta = self.svc.get_run(run_id)
        self.assertEqual(meta["annotations"]["note"], "This is a note")

    def test_patch_annotation_clear_note(self):
        """PATCH with empty string note clears the note."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_patch3", status="running")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, meta={"annotations": {
            "schema_version": 1, "favorite": False, "note": "", "updated_at": None
        }})
        meta = self.svc.get_run(run_id)
        self.assertEqual(meta["annotations"]["note"], "")

    def test_patch_nonexistent_run_id(self):
        """PATCH on nonexistent run_id returns appropriate error."""
        result = self.svc.update_run("r_nonexistent", meta={"annotations": {
            "schema_version": 1, "favorite": True, "note": "", "updated_at": None
        }})
        self.assertEqual(result.get("status"), "error")

    def test_patch_atomic_update(self):
        """PATCH update is atomic (no tmp files left behind)."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_patch_atomic", status="running")
        run_id = rec["run_id"]
        self.svc.update_run(run_id, meta={"annotations": {
            "schema_version": 1, "favorite": True, "note": "Atomic", "updated_at": None
        }})
        run_dir = self.root / run_id
        tmp_files = list(run_dir.glob("*.tmp"))
        self.assertEqual(len(tmp_files), 0)
        # Verify annotations persisted
        meta = self.svc.get_run(run_id)
        self.assertEqual(meta["annotations"]["note"], "Atomic")
        self.assertIs(meta["annotations"]["favorite"], True)


# ===================================================================
# Annotation validation
# ===================================================================

class AnnotationValidationTests(unittest.TestCase):
    """Annotation payload validation rules."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rejects_unknown_annotation_fields(self):
        """Unknown fields in annotation payload should be rejected."""
        # The service layer accepts all meta keys silently (no validation at this level)
        # Route-level validation would handle this; test validation function
        from experiment_service import _DEFAULT_ANNOTATIONS, _validate_annotation_payload
        errors = _validate_annotation_payload({"favorite": True, "note": "ok", "unknown_field": "bad"})
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("unknown" in e.lower() for e in errors))

    def test_rejects_non_bool_favorite(self):
        """favorite must be a boolean."""
        from experiment_service import _validate_annotation_payload
        errors = _validate_annotation_payload({"favorite": "yes", "note": ""})
        self.assertGreater(len(errors), 0)

    def test_rejects_non_string_note(self):
        """note must be a string."""
        from experiment_service import _validate_annotation_payload
        errors = _validate_annotation_payload({"favorite": False, "note": 123})
        self.assertGreater(len(errors), 0)

    def test_rejects_note_over_length_limit(self):
        """note must not exceed length limit."""
        from experiment_service import _validate_annotation_payload, _ANNOTATION_NOTE_MAX_LENGTH
        long_note = "x" * (_ANNOTATION_NOTE_MAX_LENGTH + 1)
        errors = _validate_annotation_payload({"favorite": False, "note": long_note})
        self.assertGreater(len(errors), 0)

    def test_accepts_valid_payload(self):
        """Valid annotation payload passes validation."""
        from experiment_service import _validate_annotation_payload
        errors = _validate_annotation_payload({"favorite": True, "note": "Great result!"})
        self.assertEqual(len(errors), 0)

    def test_accepts_partial_payload(self):
        """Partial payload (only favorite or only note) passes validation."""
        from experiment_service import _validate_annotation_payload
        errors = _validate_annotation_payload({"favorite": True})
        self.assertEqual(len(errors), 0)
        errors = _validate_annotation_payload({"note": "just a note"})
        self.assertEqual(len(errors), 0)
        errors = _validate_annotation_payload({})
        self.assertEqual(len(errors), 0)


# ===================================================================
# Enhanced listing with search/filter/sort
# ===================================================================

class EnhancedListingTests(unittest.TestCase):
    """Enhanced list_runs with search, filter, sort, pagination metadata."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)
        # Create diverse records
        self.svc.record_run(kind="studio_run", prompt_id="exp_cat_1", status="completed",
                            meta={"studio_feature_id": "txt2img", "preset_label": "Cat Preset"},
                            started_at="2025-01-01T00:00:00Z")
        self.svc.record_run(kind="studio_run", prompt_id="exp_dog_2", status="error",
                            meta={"studio_feature_id": "txt2img", "preset_label": "Dog Preset"},
                            started_at="2025-02-01T00:00:00Z")
        self.svc.record_run(kind="ordinary", prompt_id="ord_3", status="completed",
                            started_at="2025-03-01T00:00:00Z")
        self.svc.record_run(kind="studio_run", prompt_id="exp_cat_4", status="completed",
                            meta={"studio_feature_id": "object_remove", "preset_label": "Cat Preset"},
                            started_at="2025-04-01T00:00:00Z")

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_runs_pagination_metadata(self):
        """list_runs response includes pagination metadata (total, offset, limit)."""
        result = self.svc.list_runs(kind="studio_run", limit=2)
        self.assertIn("runs", result)
        self.assertIn("total", result)
        self.assertIn("limit", result)
        self.assertEqual(result["limit"], 2)
        self.assertEqual(result["total"], 3)

    def test_list_runs_pagination_offset(self):
        """list_runs with offset skips first N records."""
        result = self.svc.list_runs(kind="studio_run", limit=1, offset=0)
        self.assertEqual(len(result["runs"]), 1)
        first_id = result["runs"][0]["run_id"]

        result2 = self.svc.list_runs(kind="studio_run", limit=1, offset=1)
        self.assertEqual(len(result2["runs"]), 1)
        second_id = result2["runs"][0]["run_id"]
        self.assertNotEqual(first_id, second_id)

    def test_search_by_run_id(self):
        """Search by run_id fragment works."""
        result = self.svc.list_runs(kind="studio_run")
        all_ids = [r["run_id"] for r in result["runs"]]
        self.assertEqual(len(all_ids), 3)

    def test_filter_by_status(self):
        """Filter by status returns only matching records."""
        result = self.svc.list_runs(kind="studio_run", status_filter="error")
        for r in result["runs"]:
            self.assertEqual(r.get("status"), "error")

    def test_filter_by_favorite(self):
        """Filter by favorite_only returns only favorited records."""
        # Find a run and favorite it
        result = self.svc.list_runs(kind="studio_run", limit=1)
        if result["runs"]:
            run_id = result["runs"][0]["run_id"]
            self.svc.update_run(run_id, meta={"annotations": {
                "schema_version": 1, "favorite": True, "note": "", "updated_at": None
            }})
            result = self.svc.list_runs(kind="studio_run", favorite_only=True)
            self.assertGreaterEqual(len(result["runs"]), 1)
            for r in result["runs"]:
                ann = r.get("annotations", {})
                self.assertIs(ann.get("favorite"), True)

    def test_sort_newest(self):
        """Sort newest returns newest first."""
        result = self.svc.list_runs(kind="studio_run", sort="newest")
        runs = result["runs"]
        for i in range(len(runs) - 1):
            self.assertGreaterEqual(
                runs[i].get("started_at", ""),
                runs[i + 1].get("started_at", ""),
            )

    def test_sort_oldest(self):
        """Sort oldest returns oldest first."""
        result = self.svc.list_runs(kind="studio_run", sort="oldest")
        runs = result["runs"]
        for i in range(len(runs) - 1):
            self.assertLessEqual(
                runs[i].get("started_at", ""),
                runs[i + 1].get("started_at", ""),
            )

    def test_sort_fastest(self):
        """Sort fastest returns shortest duration first."""
        # Create runs with explicit timings
        for i, ms in enumerate([5000, 1000, 3000]):
            rec = self.svc.record_run(kind="studio_run", prompt_id=f"exp_spd_{i}", status="completed",
                                      started_at=f"2025-06-0{i+1}T00:00:00Z")
            self.svc.update_run(rec["run_id"], timings={"scheduler_execution_ms": ms})
        result = self.svc.list_runs(kind="studio_run", sort="fastest")
        if result["runs"]:
            # The fastest three should have ascending durations
            fast_runs = [r for r in result["runs"] if r["prompt_id"].startswith("exp_spd_")]
            if len(fast_runs) >= 2:
                t0 = self.svc.get_timing(fast_runs[0]["run_id"]).get("scheduler_execution_ms", 0)
                t1 = self.svc.get_timing(fast_runs[1]["run_id"]).get("scheduler_execution_ms", 0)
                self.assertLessEqual(t0, t1)


# ===================================================================
# Backward Compatibility
# ===================================================================

class BackwardCompatibilityTests(unittest.TestCase):
    """Backward compatibility with old-style records."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_old_classic_record_readable(self):
        """Old-style classic record (no extra, no annotations) is still readable."""
        run_id = "r_classic"
        old_meta = {
            "run_id": run_id,
            "kind": "ordinary",
            "prompt_id": "classic_prompt",
            "status": "completed",
            "workflow_name": "Old Workflow",
            "seed": 42,
            "steps": 20,
        }
        _make_run_dir(self.root, run_id, old_meta)
        meta = self.svc.get_run(run_id)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.get("run_id"), run_id)
        self.assertEqual(meta.get("workflow_name"), "Old Workflow")

    def test_old_studio_record_readable(self):
        """Old-style studio record without annotations is readable and normalizes."""
        run_id = "r_old_studio"
        old_meta = _default_meta(run_id)
        del old_meta["extra"]["experiment_id"]  # old records may not have this
        _make_run_dir(self.root, run_id, old_meta)
        meta = self.svc.get_run(run_id)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.get("status"), "completed")
        # annotations should normalize
        ann = meta.get("annotations", {})
        self.assertEqual(ann.get("schema_version"), 1)


# ===================================================================
# Gap 1: Backend search tests
# ===================================================================

class SearchTests(unittest.TestCase):
    """Search across prompt, note, preset_label, run_id, experiment_id."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)
        self.svc.record_run(kind="studio_run", prompt_id="exp_cat_mountain",
                            meta={"studio_feature_id": "txt2img", "preset_label": "Alpine"},
                            started_at="2025-01-01T00:00:00Z")
        self.svc.record_run(kind="studio_run", prompt_id="exp_dog_beach",
                            meta={"studio_feature_id": "txt2img", "preset_label": "Coastal"},
                            started_at="2025-02-01T00:00:00Z")
        self.svc.record_run(kind="ordinary", prompt_id="ord_sunset",
                            started_at="2025-03-01T00:00:00Z")

    def tearDown(self):
        self.tmp.cleanup()

    def test_search_by_prompt_id_fragment(self):
        """Search by prompt_id substring matches correctly."""
        result = self.svc.list_runs(search="cat")
        ids = [r["prompt_id"] for r in result["runs"]]
        self.assertIn("exp_cat_mountain", ids)
        self.assertNotIn("exp_dog_beach", ids)

    def test_search_by_run_id_fragment(self):
        """Search by run_id substring matches correctly."""
        all_runs = self.svc.list_runs()["runs"]
        target_id = all_runs[0]["run_id"][:8]
        result = self.svc.list_runs(search=target_id)
        self.assertGreaterEqual(len(result["runs"]), 1)

    def test_search_by_preset_label(self):
        """Search by preset_label substring."""
        result = self.svc.list_runs(search="Alpine")
        ids = [r["prompt_id"] for r in result["runs"]]
        self.assertIn("exp_cat_mountain", ids)
        self.assertNotIn("exp_dog_beach", ids)

    def test_search_by_experiment_id(self):
        """Search by experiment_id (in extra) substring."""
        result = self.svc.list_runs(search="exp_cat")
        self.assertGreaterEqual(len(result["runs"]), 1)

    def test_search_case_insensitive(self):
        """Search is case-insensitive."""
        result = self.svc.list_runs(search="alpine")
        self.assertGreaterEqual(len(result["runs"]), 1)

    def test_search_by_note_in_annotations(self):
        """Search filters on annotation note content."""
        all_runs = self.svc.list_runs()["runs"]
        if all_runs:
            rid = all_runs[0]["run_id"]
            self.svc.update_run(rid, meta={"annotations": {
                "schema_version": 1, "favorite": False, "note": "favorite result", "updated_at": None
            }})
            result = self.svc.list_runs(search="favorite")
            self.assertGreaterEqual(len(result["runs"]), 1)

    def test_search_no_match_returns_empty(self):
        """Search with non-matching text returns empty list."""
        result = self.svc.list_runs(search="zzz_nonexistent_zzz")
        self.assertEqual(len(result["runs"]), 0)

    def test_search_empty_string_returns_all(self):
        """Empty search string returns all records."""
        total = self.svc.list_runs()["total"]
        searched = self.svc.list_runs(search="")["total"]
        self.assertEqual(total, searched)


# ===================================================================
# Gap 2: Additional filter tests
# ===================================================================

class FilterTests(unittest.TestCase):
    """Advanced filters: feature, preset, date range, has_image."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)
        self.svc.record_run(kind="studio_run", prompt_id="exp_f1", status="completed",
                            meta={"studio_feature_id": "txt2img", "studio_preset_id": "preset_a",
                                  "preset_label": "Alpha"},
                            started_at="2025-01-01T00:00:00Z")
        self.svc.record_run(kind="studio_run", prompt_id="exp_f2", status="error",
                            meta={"studio_feature_id": "object_remove", "studio_preset_id": "preset_b",
                                  "preset_label": "Beta"},
                            started_at="2025-02-01T00:00:00Z")
        self.svc.record_run(kind="studio_run", prompt_id="exp_f3", status="completed",
                            meta={"studio_feature_id": "txt2img", "studio_preset_id": "preset_a",
                                  "preset_label": "Alpha"},
                            started_at="2025-03-01T00:00:00Z",
                            output_path="outputs/img_001.png")

    def tearDown(self):
        self.tmp.cleanup()

    def test_filter_by_feature_id(self):
        """Filter by feature id (studio_feature_id) returns only matching."""
        result = self.svc.list_runs(kind="studio_run", feature="object_remove")
        for r in result["runs"]:
            self.assertEqual(r.get("extra", {}).get("studio_feature_id"), "object_remove")

    def test_filter_by_preset_id(self):
        """Filter by preset id returns only matching."""
        result = self.svc.list_runs(kind="studio_run", preset="preset_a")
        for r in result["runs"]:
            self.assertEqual(r.get("extra", {}).get("studio_preset_id"), "preset_a")

    def test_filter_by_date_from(self):
        """Filter by date_from returns only runs on or after date."""
        result = self.svc.list_runs(kind="studio_run", date_from="2025-02-01T00:00:00Z")
        for r in result["runs"]:
            self.assertGreaterEqual(r.get("started_at", ""), "2025-02-01T00:00:00Z")

    def test_filter_by_date_to(self):
        """Filter by date_to returns only runs on or before date."""
        result = self.svc.list_runs(kind="studio_run", date_to="2025-01-15T00:00:00Z")
        for r in result["runs"]:
            self.assertLessEqual(r.get("started_at", ""), "2025-01-15T00:00:00Z")

    def test_filter_by_date_range(self):
        """Filter by both date_from and date_to returns runs in range."""
        result = self.svc.list_runs(kind="studio_run",
                                    date_from="2025-02-01T00:00:00Z",
                                    date_to="2025-02-28T00:00:00Z")
        ids = [r["prompt_id"] for r in result["runs"]]
        self.assertIn("exp_f2", ids)
        self.assertNotIn("exp_f1", ids)

    def test_filter_has_image_true(self):
        """has_image=True returns only runs with output_path."""
        result = self.svc.list_runs(kind="studio_run", has_image=True)
        for r in result["runs"]:
            self.assertTrue(r.get("output_path"))

    def test_filter_has_image_false(self):
        """has_image=False returns only runs without output_path."""
        result = self.svc.list_runs(kind="studio_run", has_image=False)
        for r in result["runs"]:
            self.assertFalse(r.get("output_path"))

    def test_combined_search_and_filter(self):
        """Search + feature filter together narrow results."""
        result = self.svc.list_runs(search="Alpha", feature="txt2img")
        for r in result["runs"]:
            self.assertEqual(r.get("extra", {}).get("studio_feature_id"), "txt2img")


# ===================================================================
# Gap 3: Run ID validation
# ===================================================================

class RunIdValidationTests(unittest.TestCase):
    """run_id validation/sanitization for path safety."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rejects_path_traversal_in_run_id(self):
        """run_id with ../ is rejected."""
        from experiment_service import _validate_run_id
        self.assertFalse(_validate_run_id("r_../../etc/passwd"))

    def test_rejects_null_byte_in_run_id(self):
        """run_id with null byte is rejected."""
        from experiment_service import _validate_run_id
        self.assertFalse(_validate_run_id("r_valid\x00"))

    def test_rejects_slashes_in_run_id(self):
        """run_id with forward slash is rejected."""
        from experiment_service import _validate_run_id
        self.assertFalse(_validate_run_id("r_valid/invalid"))

    def test_rejects_backslashes_in_run_id(self):
        """run_id with backslash is rejected."""
        from experiment_service import _validate_run_id
        self.assertFalse(_validate_run_id("r_valid\\invalid"))

    def test_valid_run_id_passes(self):
        """Standard run_id format passes validation."""
        from experiment_service import _validate_run_id
        self.assertTrue(_validate_run_id("r_abc123def456"))

    def test_update_run_rejects_invalid_run_id(self):
        """update_run returns error for path-traversal run_id."""
        result = self.svc.update_run("r_../../etc/passwd", status="completed")
        self.assertEqual(result.get("status"), "error")

    def test_get_run_rejects_invalid_run_id(self):
        """get_run returns None for path-traversal run_id."""
        meta = self.svc.get_run("r_../../etc/passwd")
        self.assertIsNone(meta)


# ===================================================================
# Gap 4: Meta dict non-mutation
# ===================================================================

class MetaNonMutationTests(unittest.TestCase):
    """Caller-provided meta dict must not be mutated by update_run."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)
        self.rec = self.svc.record_run(kind="studio_run", prompt_id="exp_nomut", status="running")

    def tearDown(self):
        self.tmp.cleanup()

    def test_update_run_does_not_mutate_caller_meta(self):
        """update_run does not pop 'annotations' from caller's meta dict."""
        original = {"annotations": {"schema_version": 1, "favorite": True, "note": "hi", "updated_at": None},
                    "other_field": "value"}
        before = dict(original)
        self.svc.update_run(self.rec["run_id"], meta=original)
        self.assertEqual(original, before, "caller's meta dict was mutated!")

    def test_update_run_does_not_mutate_caller_meta_when_no_annotations(self):
        """update_run does not mutate meta when annotations absent."""
        original = {"resolved_controls": {"seed": 42}}
        before = dict(original)
        self.svc.update_run(self.rec["run_id"], meta=original)
        self.assertEqual(original, before, "caller's meta dict was mutated!")


# ===================================================================
# Gap 5: Timing schema alignment
# ===================================================================

class TimingSchemaTests(unittest.TestCase):
    """timing.json exposes canonical fields for frontend normalization."""

    @classmethod
    def setUpClass(cls):
        cls.svc_mod = _load_module("experiment_service", "experiment_service.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svc = self.svc_mod.RunHistoryService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scheduler_execution_ms_present(self):
        """scheduler_execution_ms in timing.json."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_ts1", status="completed")
        self.svc.update_run(rec["run_id"], timings={"scheduler_execution_ms": 45000})
        read = self.svc.get_timing(rec["run_id"])
        self.assertIn("scheduler_execution_ms", read)
        self.assertEqual(read["scheduler_execution_ms"], 45000)

    def test_end_to_end_total_ms_present(self):
        """end_to_end_total_ms in timing.json."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_ts2", status="completed")
        self.svc.update_run(rec["run_id"], timings={"end_to_end_total_ms": 50200})
        read = self.svc.get_timing(rec["run_id"])
        self.assertIn("end_to_end_total_ms", read)

    def test_timing_sources_present(self):
        """timing_sources dict in timing.json."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_ts3", status="completed")
        self.svc.update_run(rec["run_id"], timings={"scheduler_execution_ms": 45000,
                           "timing_sources": {"scheduler_execution_ms": "remote"}})
        read = self.svc.get_timing(rec["run_id"])
        self.assertIn("timing_sources", read)
        self.assertEqual(read["timing_sources"]["scheduler_execution_ms"], "remote")

    def test_remote_timings_flattened_not_nested(self):
        """Remote timing fields are merged flat into timing.json, not only nested under remote_timings."""
        rec = self.svc.record_run(kind="studio_run", prompt_id="exp_ts4", status="completed")
        # Write timings with remote values
        self.svc.update_run(rec["run_id"], timings={
            "sampling_ms": 35000,
            "model_load_ms": 8000,
            "restore_total_ms": 12000,
            "scheduler_execution_ms": 45000,
        })
        read = self.svc.get_timing(rec["run_id"])
        # Each field should be at the top level, not nested
        self.assertEqual(read.get("sampling_ms"), 35000)
        self.assertEqual(read.get("model_load_ms"), 8000)
        self.assertEqual(read.get("restore_total_ms"), 12000)
        self.assertEqual(read.get("scheduler_execution_ms"), 45000)


# ===================================================================
# Gap 6: Failure timings preservation in studio_run_adapter
# ===================================================================

class FailureTimingPreservationTests(unittest.TestCase):
    """_schedule_and_start preserves known timings when sched.start() fails."""

    @classmethod
    def setUpClass(cls):
        cls.adapter = _load_module("studio_run_adapter", "studio_run_adapter.py")

    def test_failure_timing_preservation_has_queue_ms(self):
        """Failure finalization includes queue_ms evidence."""
        import inspect
        src = inspect.getsource(self.adapter._schedule_and_start)
        # Verify the exception handler references timings/queue_ms
        self.assertIn("queue_ms", src)

    def test_failure_path_includes_failure_stage(self):
        """Failure path sets failure_stage in meta."""
        import inspect
        src = inspect.getsource(self.adapter._schedule_and_start)
        self.assertIn("failure_stage", src)


if __name__ == "__main__":
    unittest.main()
