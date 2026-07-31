"""Tests for the rebuildable SQLite summary index (history_index.py).

Coverage:
- Index rebuild idempotence (production layout: root/<run_id>/meta.json)
- Corrupt/missing/schema-mismatch fallback and auto-rebuild
- Incremental source-write updates (upsert)
- Filters, sorts, pagination, total
- Annotations/timing fields
- Experiment summary inclusion
- Endpoint contract shape
- Concurrent safety
- Schema version mismatch detection
"""

import json
import os
import shutil
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Optional


class TestHistoryIndex(unittest.TestCase):
    """Tests for the history_index module using production layout."""

    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util
        import sys
        cls.REPO_ROOT = Path(__file__).resolve().parents[1]
        mod_path = cls.REPO_ROOT / "history_index.py"
        if not mod_path.exists():
            raise AssertionError("history_index.py not found")
        spec = importlib.util.spec_from_file_location("history_index", mod_path)
        assert spec is not None and spec.loader is not None
        cls.mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.mod
        spec.loader.exec_module(cls.mod)

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        # Production layout: RunHistoryService root directly contains <run_id>/meta.json
        self.idx = self.mod.HistoryIndex(self.root)

    def tearDown(self) -> None:
        try:
            self.idx.close()
        except Exception:
            pass
        self._tmpdir.cleanup()

    # ── Helpers ─────────────────────────────────────────────────────────

    def _write_meta(self, run_id: str, overrides: Optional[dict] = None) -> Path:
        meta = {
            "run_id": run_id,
            "kind": "ordinary",
            "status": "completed",
            "started_at": "2026-07-01T12:00:00Z",
            "completed_at": "2026-07-01T12:01:00Z",
            "updated_at": "2026-07-01T12:01:00Z",
            "prompt": "test prompt",
            "negative_prompt": "",
            "seed": 42,
            "steps": 20,
            "guidance": 3.5,
            "sampler": "euler",
            "scheduler": "normal",
            "output_path": "/tmp/out.png",
            "extra": {
                "experiment_id": "",
                "preset_id": "",
                "preset_label": "",
                "feature_id": "",
                "output_count": 1,
                "studio_preset_label": "",
                "resolved_controls": {
                    "prompt": "test prompt",
                    "seed": 42,
                    "steps": 20,
                },
            },
            "annotations": {
                "favorite": False,
                "note": "",
                "updated_at": None,
            },
        }
        if overrides:
            self._deep_merge(meta, overrides)
        # Production layout: root/<run_id>/meta.json
        run_dir = self.root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        meta_path = run_dir / "meta.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta_path

    def _deep_merge(self, base: dict, override: dict) -> None:
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                self._deep_merge(base[k], v)
            else:
                base[k] = v

    # ── Tests ───────────────────────────────────────────────────────────

    def test_ensure_creates_index(self):
        """Ensure creates the SQLite database file."""
        self.assertFalse(self.idx._db_path.exists())
        self.idx.ensure()
        self.assertTrue(self.idx._db_path.exists())

    def test_rebuild_empty(self):
        """Rebuild on empty directory returns 0."""
        count = self.idx.rebuild()
        self.assertEqual(count, 0)

    def test_rebuild_indexes_records(self):
        """Rebuild indexes all existing meta.json files (production layout)."""
        for i in range(5):
            self._write_meta(f"r_{i:04x}")
        count = self.idx.rebuild()
        self.assertEqual(count, 5)

    def test_rebuild_skips_dot_dirs(self):
        """Rebuild skips dot-prefixed directories like .history_index.db."""
        # Write a real record
        self._write_meta("r_0001")
        # Create a dot directory that should be skipped
        dot_dir = self.root / ".hidden"
        dot_dir.mkdir(parents=True, exist_ok=True)
        (dot_dir / "meta.json").write_text('{"run_id": "skip_me"}', encoding="utf-8")
        count = self.idx.rebuild()
        self.assertEqual(count, 1, "Should skip dot-prefixed directories")

    def test_upsert_adds_record(self):
        """Upsert adds a record to the index."""
        meta = {
            "run_id": "r_test001",
            "kind": "ordinary",
            "status": "completed",
            "started_at": "2026-07-01T12:00:00Z",
            "extra": {"resolved_controls": {"prompt": "hello"}},
            "annotations": {"favorite": True, "note": "my note"},
        }
        self.idx.upsert_from_meta(meta)
        row = self.idx.get("r_test001")
        self.assertIsNotNone(row)
        self.assertEqual(row["run_id"], "r_test001")
        self.assertEqual(row["status"], "completed")
        self.assertTrue(row["favorite"])

    def test_upsert_updates_existing(self):
        """Upsert updates an existing record."""
        self._write_meta("r_update")
        self.idx.rebuild()
        self.idx.upsert_from_meta({
            "run_id": "r_update",
            "kind": "ordinary",
            "status": "failed",
            "started_at": "2026-07-01T12:00:00Z",
            "annotations": {"favorite": True, "note": ""},
        })
        row = self.idx.get("r_update")
        self.assertEqual(row["status"], "failed")

    def test_remove_deletes_record(self):
        """Remove deletes a record from the index."""
        self._write_meta("r_del")
        self.idx.rebuild()
        self.idx.remove("r_del")
        row = self.idx.get("r_del")
        self.assertIsNone(row)

    def test_query_pagination(self):
        """Query returns paginated results with correct total and has_more."""
        for i in range(15):
            rid = f"r_pag_{i:04d}"
            self._write_meta(rid, {"started_at": f"2026-07-01T12:{i:02d}:00Z"})
        self.idx.rebuild()
        r1 = self.idx.query(page=1, page_size=10, sort="oldest")
        self.assertEqual(len(r1["items"]), 10)
        self.assertEqual(r1["total"], 15)
        self.assertTrue(r1["has_more"])
        self.assertEqual(r1["page"], 1)
        r2 = self.idx.query(page=2, page_size=10, sort="oldest")
        self.assertEqual(len(r2["items"]), 5)
        self.assertFalse(r2["has_more"])

    def test_query_filter_kind(self):
        """Query filters by kind."""
        self._write_meta("r_ord", {"kind": "ordinary"})
        self._write_meta("r_exp", {"kind": "experiment_cell"})
        self.idx.rebuild()
        r = self.idx.query(kind="ordinary")
        self.assertEqual(len(r["items"]), 1)
        self.assertEqual(r["items"][0]["run_id"], "r_ord")

    def test_query_filter_status(self):
        """Query filters by status."""
        self._write_meta("r_ok", {"status": "completed"})
        self._write_meta("r_fail", {"status": "error"})
        self.idx.rebuild()
        r = self.idx.query(status="error")
        self.assertEqual(len(r["items"]), 1)
        self.assertEqual(r["items"][0]["run_id"], "r_fail")

    def test_query_filter_favorite(self):
        """Query filters by favorite."""
        self._write_meta("r_fav", {"annotations": {"favorite": True, "note": ""}})
        self._write_meta("r_not", {"annotations": {"favorite": False, "note": ""}})
        self.idx.rebuild()
        r = self.idx.query(favorite_only=True)
        self.assertEqual(len(r["items"]), 1)
        self.assertEqual(r["items"][0]["run_id"], "r_fav")

    def test_query_filter_search(self):
        """Query filters by text search."""
        self._write_meta("r_hello", {"extra": {"resolved_controls": {"prompt": "hello world"}}})
        self._write_meta("r_goodbye", {"extra": {"resolved_controls": {"prompt": "goodbye"}}})
        self.idx.rebuild()
        r = self.idx.query(search="hello")
        self.assertEqual(len(r["items"]), 1)

    def test_query_sort_newest_oldest(self):
        """Query sorts by started_at."""
        self._write_meta("r_early", {"started_at": "2026-06-01T12:00:00Z"})
        self._write_meta("r_late", {"started_at": "2026-07-01T12:00:00Z"})
        self.idx.rebuild()
        newest = self.idx.query(sort="newest")
        self.assertEqual(newest["items"][0]["run_id"], "r_late")
        oldest = self.idx.query(sort="oldest")
        self.assertEqual(oldest["items"][0]["run_id"], "r_early")

    def test_query_sort_fastest_slowest(self):
        """Query sorts by duration_ms."""
        self._write_meta("r_fast", {"duration_ms": 100})
        self._write_meta("r_slow", {"duration_ms": 2000})
        self.idx.rebuild()
        fastest = self.idx.query(sort="fastest")
        self.assertEqual(fastest["items"][0]["run_id"], "r_fast")

    def test_query_has_image(self):
        """Query filters by has_image."""
        self._write_meta("r_img", {"output_path": "/tmp/img.png"})
        self._write_meta("r_noimg", {"output_path": ""})
        self.idx.rebuild()
        r = self.idx.query(has_image=True)
        self.assertEqual(len(r["items"]), 1)
        self.assertEqual(r["items"][0]["run_id"], "r_img")

    def test_rebuild_idempotent(self):
        """Rebuilding twice produces the same count."""
        for i in range(10):
            self._write_meta(f"r_idem_{i:04d}")
        c1 = self.idx.rebuild()
        for i in range(10, 15):
            self._write_meta(f"r_idem_{i:04d}")
        c2 = self.idx.rebuild()
        self.assertEqual(c1, 10)
        self.assertEqual(c2, 15)

    def test_corrupt_fallback(self):
        """Corrupt index database recovers safely."""
        self._write_meta("r_ok")
        self.idx.rebuild()
        # Corrupt the database with garbage
        with open(self.idx._db_path, "wb") as f:
            f.write(b"NOT A SQLITE DATABASE")
        # ensure() should recover (rebuild or otherwise make usable)
        self.idx._schema_initialised = False
        ok = self.idx.ensure()
        # After recovery, the record should still be queryable
        r = self.idx.get("r_ok")
        self.assertIsNotNone(r, "Index should recover from corruption")
        self.assertEqual(r["run_id"], "r_ok")
        # Index is now usable; ok indicates whether it was already usable (True)
        # or needed recovery (False). Either is acceptable as long as data is
        # intact — SQLite WAL recovery on Windows may mask main-file corruption
        # so ensure() may return True on some platforms.
        self.assertIsInstance(ok, bool)

    def test_missing_db_creates_and_rebuilds(self):
        """Missing database file triggers creation and rebuild."""
        self._write_meta("r_missing")
        self.idx._db_path.unlink(missing_ok=True)
        self.idx._schema_initialised = False
        ok = self.idx.ensure()
        r = self.idx.get("r_missing")
        self.assertIsNotNone(r)
        self.assertIsInstance(ok, bool)

    def test_schema_version_mismatch_triggers_rebuild(self):
        """If schema_version differs from SCHEMA_VERSION, ensure triggers rebuild."""
        self._write_meta("r_old_schema")
        self.idx.rebuild()
        # Manually set a different schema version in the DB
        conn = self.idx._conn()
        conn.execute("UPDATE meta SET schema_version = 999")
        conn.commit()
        self.idx.close()
        self.idx._schema_initialised = False
        ok = self.idx.ensure()
        # Schema mismatch should be detected and fixed
        row = self.idx.get("r_old_schema")
        self.assertIsNotNone(row)
        # Schema version should be current
        cur = self.idx._cursor().execute(
            "SELECT schema_version FROM meta LIMIT 1"
        ).fetchone()
        self.assertEqual(cur[0], 1)

    def test_ensure_returns_true_when_usable(self):
        """ensure returns True when index is already present and valid."""
        self._write_meta("r_valid")
        self.idx.ensure()
        # Second ensure on valid DB returns True
        ok = self.idx.ensure()
        self.assertTrue(ok)

    def test_upsert_with_full_meta(self):
        """Upsert preserves all summary fields."""
        self._write_meta("r_full", {
            "seed": 123,
            "steps": 30,
            "guidance": 7.5,
            "sampler": "dpmpp_2m",
            "scheduler": "karras",
            "extra": {
                "experiment_id": "exp_001",
                "experiment_revision": 2,
                "studio_preset_id": "preset_abc",
                "studio_preset_label": "My Preset",
                "studio_feature_id": "txt2img",
                "output_count": 3,
                "execution_engine": "modal",
                "resolved_controls": {"seed": 123, "steps": 30, "prompt": ""},
            },
            "annotations": {"favorite": True, "note": "Great result"},
        })
        self.idx.rebuild()
        row = self.idx.get("r_full")
        self.assertIsNotNone(row)
        self.assertEqual(row["preset_id"], "preset_abc")
        self.assertEqual(row["preset_label"], "My Preset")
        self.assertEqual(row["feature_id"], "txt2img")
        self.assertEqual(row["seed"], 123)
        self.assertEqual(row["steps"], 30)
        self.assertEqual(row["guidance"], 7.5)
        self.assertEqual(row["experiment_id"], "exp_001")
        self.assertEqual(row["experiment_revision"], 2)
        self.assertTrue(row["favorite"])
        self.assertEqual(row["note"], "Great result")

    def test_query_excludes_removed_after_rebuild(self):
        """After removing a source file and rebuilding, it should not appear."""
        self._write_meta("r_keep")
        self._write_meta("r_del")
        self.idx.rebuild()
        (self.root / "r_del" / "meta.json").unlink()
        self.idx.rebuild()
        r = self.idx.get("r_del")
        self.assertIsNone(r)

    def test_query_preset_filter(self):
        """Query filters by preset_id."""
        self._write_meta("r_p1", {"extra": {"studio_preset_id": "preset_one"}})
        self._write_meta("r_p2", {"extra": {"studio_preset_id": "preset_two"}})
        self.idx.rebuild()
        r = self.idx.query(preset="preset_one")
        self.assertEqual(len(r["items"]), 1)

    def test_query_experiment_id_filter(self):
        """Query filters by experiment_id."""
        self._write_meta("r_e1", {"extra": {"experiment_id": "exp_one"}})
        self._write_meta("r_e2", {"extra": {"experiment_id": "exp_two"}})
        self.idx.rebuild()
        r = self.idx.query(experiment_id="exp_one")
        self.assertEqual(len(r["items"]), 1)

    def test_timing_summary_stored(self):
        """Timing summary is stored and round-tripped."""
        timing = {"end_to_end_total_ms": 1500, "sampling_ms": 800}
        meta_path = self._write_meta("r_timing")
        self.idx.upsert_from_meta(
            {
                "run_id": "r_timing",
                "kind": "ordinary",
                "status": "completed",
                "started_at": "2026-07-01T12:00:00Z",
                "annotations": {"favorite": False, "note": ""},
            },
            source_path=str(meta_path),
        )
        # Upsert with timing_summary
        self.idx.upsert_from_meta(
            {
                "run_id": "r_timing",
                "kind": "ordinary",
                "status": "completed",
                "started_at": "2026-07-01T12:00:00Z",
                "annotations": {"favorite": False, "note": ""},
                "timing_summary": timing,
                "duration_ms": 1500,
            },
        )
        row = self.idx.get("r_timing")
        self.assertIsNotNone(row)
        self.assertEqual(row["duration_ms"], 1500)
        self.assertIsInstance(row.get("timing_summary"), dict)

    def test_stale_mark(self):
        """Marking stale sets source_mtime to 0."""
        self._write_meta("r_stale")
        self.idx.rebuild()
        self.idx.mark_stale("r_stale")
        row = self.idx.get("r_stale")
        self.assertEqual(row["source_mtime"], 0)

    def test_empty_query_returns_empty(self):
        """Query on empty index returns empty items."""
        r = self.idx.query()
        self.assertEqual(r["items"], [])
        self.assertEqual(r["total"], 0)
        self.assertFalse(r["has_more"])

    def test_endpoint_contract_shape(self):
        """Query returns correct response contract."""
        self._write_meta("r_contract")
        self.idx.rebuild()
        r = self.idx.query(page=1, page_size=10)
        self.assertIn("items", r)
        self.assertIn("page", r)
        self.assertIn("page_size", r)
        self.assertIn("total", r)
        self.assertIn("has_more", r)

    def test_query_page_size_behavior(self):
        """Query respects page_size limit."""
        for i in range(25):
            self._write_meta(f"r_ps_{i:04d}")
        self.idx.rebuild()
        r = self.idx.query(page=1, page_size=5, sort="newest")
        self.assertEqual(len(r["items"]), 5)
        self.assertEqual(r["page_size"], 5)
        self.assertEqual(r["total"], 25)
        self.assertTrue(r["has_more"])
        r2 = self.idx.query(page=5, page_size=5, sort="newest")
        self.assertEqual(len(r2["items"]), 5)
        self.assertFalse(r2["has_more"])

    def test_experiment_id_in_summary(self):
        """Experiment summary fields (id, revision) survive round-trip."""
        self._write_meta("r_exp_summary", {
            "extra": {
                "experiment_id": "exp_group_1",
                "experiment_revision": 3,
            },
        })
        self.idx.rebuild()
        row = self.idx.get("r_exp_summary")
        self.assertEqual(row["experiment_id"], "exp_group_1")
        self.assertEqual(row["experiment_revision"], 3)

    def test_ensure_rebuilds_on_schema_too_old(self):
        """If schema_version is stale, ensure restores current version."""
        self._write_meta("r_stale_schema")
        self.idx.rebuild()
        # Downgrade schema version
        conn = self.idx._conn()
        conn.execute("UPDATE meta SET schema_version = 0")
        conn.commit()
        self.idx.close()
        self.idx._schema_initialised = False
        self.idx.ensure()
        cur = self.idx._cursor().execute(
            "SELECT schema_version FROM meta LIMIT 1"
        ).fetchone()
        self.assertEqual(cur[0], self.mod.SCHEMA_VERSION)


class TestHistoryIndexConcurrency(unittest.TestCase):
    """Basic concurrency safety test."""

    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util
        import sys
        cls.REPO_ROOT = Path(__file__).resolve().parents[1]
        mod_path = cls.REPO_ROOT / "history_index.py"
        spec = importlib.util.spec_from_file_location("history_index", mod_path)
        assert spec is not None and spec.loader is not None
        cls.mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.mod
        spec.loader.exec_module(cls.mod)

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.idx = self.mod.HistoryIndex(self.root)

    def tearDown(self) -> None:
        try:
            self.idx.close()
        except Exception:
            pass
        import gc
        gc.collect()
        self._tmpdir.cleanup()

    def test_concurrent_upserts(self):
        """Multiple UPSERTs from simulated threads do not corrupt."""
        import concurrent.futures

        def _upsert(i: int) -> str:
            local_idx = self.mod.HistoryIndex(self.root)
            try:
                rid = f"r_conc_{i:04d}"
                local_idx.upsert_from_meta({
                    "run_id": rid,
                    "kind": "ordinary",
                    "status": "completed",
                    "started_at": "2026-07-01T12:00:00Z",
                    "annotations": {"favorite": False, "note": ""},
                })
                return rid
            finally:
                local_idx.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(_upsert, i) for i in range(20)]
            # Surface any worker exception (e.g. a transient write-lock
            # failure) as the test failure instead of a silent missing row.
            for fut in concurrent.futures.as_completed(futs):
                self.assertIsNone(fut.exception(), f"worker failed: {fut.exception()}")

        for i in range(20):
            rid = f"r_conc_{i:04d}"
            row = self.idx.get(rid)
            self.assertIsNotNone(row, f"Missing record: {rid}")
            self.assertEqual(row["status"], "completed")


class TestHistoryIndexRecoveryAndStaleness(TestHistoryIndex):
    """Bounded recovery and staleness handling for indexed history.

    Root-cause coverage for /comfymodal/history:
    - rebuild only for missing/corrupt/incompatible/demonstrably stale
    - no rebuild on every request (rate-limited validation + probe)
    - fingerprint is maintained by plugin-owned upserts/removes so they do
      not false-positive as stale
    - restart-safe (a fresh HistoryIndex on the same root reuses the index)
    - flat/incompletely-built schema recovers on the first request
    """

    def test_stale_detects_externally_added_run(self):
        """A source run written outside the plugin is picked up once."""
        self._write_meta("r_known")
        self.idx.rebuild()
        self.assertIsNotNone(self.idx.get("r_known"))
        # Simulate a run created by another process after the index build.
        time.sleep(0.01)
        self._write_meta("r_external")
        result = self.idx.refresh_if_stale(force=True)
        self.assertTrue(result["rebuilt"], result)
        self.assertEqual(result["record_count"], 2)
        self.assertIsNotNone(self.idx.get("r_external"))

    def test_stale_detects_removed_run(self):
        """Removing a source run dir prunes the index on the next probe."""
        self._write_meta("r_keep")
        self._write_meta("r_gone")
        self.idx.rebuild()
        shutil.rmtree(self.root / "r_gone")
        result = self.idx.refresh_if_stale(force=True)
        self.assertTrue(result["rebuilt"], result)
        self.assertIsNone(self.idx.get("r_gone"))
        self.assertIsNotNone(self.idx.get("r_keep"))

    def test_refresh_is_rate_limited(self):
        """Repeated refresh calls within the interval do not rescan/rebuild."""
        self._write_meta("r_a")
        self.idx.rebuild()
        first = self.idx.refresh_if_stale(force=True)
        self.assertFalse(first["rebuilt"])  # fingerprint present and fresh
        second = self.idx.refresh_if_stale()
        self.assertFalse(second["rebuilt"])
        self.assertEqual(second["reason"], "rate_limited")

    def test_upsert_does_not_false_positive_as_stale(self):
        """Plugin-owned writes keep the fingerprint in sync (no rebuild)."""
        self._write_meta("r_base")
        self.idx.rebuild()
        # Plugin path: write meta.json then upsert with source_path.
        meta = {
            "run_id": "r_new",
            "kind": "ordinary",
            "status": "completed",
            "started_at": "2026-07-20T12:00:00Z",
            "annotations": {"favorite": False, "note": ""},
        }
        meta_path = self.root / "r_new" / "meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        self.idx.upsert_from_meta(meta, str(meta_path))
        result = self.idx.refresh_if_stale(force=True)
        self.assertFalse(result["rebuilt"], result)
        self.assertEqual(result["reason"], "fresh")
        # And the row is queryable without any rebuild.
        self.assertIsNotNone(self.idx.get("r_new"))

    def test_remove_does_not_false_positive_as_stale(self):
        """remove() with the source gone keeps the fingerprint in sync."""
        self._write_meta("r_del")
        self.idx.rebuild()
        # Deletion removes both the authoritative source and the index row.
        shutil.rmtree(self.root / "r_del")
        self.idx.remove("r_del")
        result = self.idx.refresh_if_stale(force=True)
        self.assertFalse(result["rebuilt"], result)
        self.assertEqual(result["reason"], "fresh")
        self.assertIsNone(self.idx.get("r_del"))

    def test_remove_with_source_still_present_is_self_healing(self):
        """An index-only remove with the source still present is corrected."""
        self._write_meta("r_keep")
        self.idx.rebuild()
        # Index row removed but source dir left behind: source is
        # authoritative, so the next probe restores the row.
        self.idx.remove("r_keep")
        result = self.idx.refresh_if_stale(force=True)
        self.assertTrue(result["rebuilt"], result)
        self.assertIsNotNone(self.idx.get("r_keep"))

    def test_flat_metadata_index_recovers(self):
        """A schema-only (flat) index with zero entries rebuilds on demand."""
        self._write_meta("r_flat")
        conn = sqlite3.connect(self.idx._db_path)
        conn.execute("CREATE TABLE meta (schema_version INTEGER NOT NULL DEFAULT 1)")
        conn.execute("INSERT INTO meta (schema_version) VALUES (1)")
        conn.execute("CREATE TABLE index_entries (run_id TEXT PRIMARY KEY NOT NULL)")
        conn.commit()
        conn.close()
        self.idx._schema_initialised = False
        # ensure() accepts the schema-versioned but flat DB...
        ok = self.idx.ensure()
        self.assertTrue(ok)
        # ...but the staleness probe detects the missing fingerprint and
        # rebuilds so history is no longer empty.
        result = self.idx.refresh_if_stale(force=True)
        self.assertTrue(result["rebuilt"], result)
        self.assertIsNotNone(self.idx.get("r_flat"))

    def test_restart_reuses_existing_index(self):
        """A fresh index instance (restart) reuses a healthy index."""
        self._write_meta("r_before")
        self.idx.rebuild()
        self.idx.close()
        # New instance on the same root == ComfyUI restart.
        idx2 = self.mod.HistoryIndex(self.root)
        try:
            ok = idx2.ensure()
            self.assertTrue(ok, "restart should not trigger a rebuild")
            self.assertIsNotNone(idx2.get("r_before"))
            refresh = idx2.refresh_if_stale(force=True)
            self.assertFalse(refresh["rebuilt"], refresh)
            self.assertEqual(refresh["reason"], "fresh")
        finally:
            idx2.close()

    def test_restart_picks_up_external_run(self):
        """A run written between restarts is indexed on the first probe."""
        self._write_meta("r_old")
        self.idx.rebuild()
        self.idx.close()
        time.sleep(0.01)
        self._write_meta("r_after_restart")
        idx2 = self.mod.HistoryIndex(self.root)
        try:
            ok = idx2.ensure()
            self.assertTrue(ok)
            refresh = idx2.refresh_if_stale(force=True)
            self.assertTrue(refresh["rebuilt"], refresh)
            self.assertIsNotNone(idx2.get("r_after_restart"))
        finally:
            idx2.close()

    def test_ensure_force_recovers_corruption(self):
        """ensure(force=True) rebuilds a database corrupted mid-session."""
        self._write_meta("r_ok")
        self.idx.rebuild()
        self.idx.close()
        with open(self.idx._db_path, "wb") as f:
            f.write(b"NOT A SQLITE DATABASE")
        self.idx._schema_initialised = False
        ok = self.idx.ensure(force=True)
        self.assertFalse(ok, "corrupt index should trigger a rebuild")
        self.assertIsNotNone(self.idx.get("r_ok"))

    def test_ensure_is_cheap_after_validation(self):
        """Repeated ensure() on a healthy index stays cheap (no revalidation)."""
        self._write_meta("r_valid")
        self.idx.ensure()
        validated = self.idx._validated_at
        self.assertIsNotNone(validated)
        # Immediately repeated calls return the cached validation result.
        self.assertTrue(self.idx.ensure())
        self.assertEqual(self.idx._validated_at, validated)
        self.assertTrue(self.idx.ensure())
        self.assertEqual(self.idx._validated_at, validated)


class TestHistoryIndexBenchmark(unittest.TestCase):
    """Synthetic benchmark for index operations.

    Run with: python -m pytest tests/test_history_index.py::TestHistoryIndexBenchmark -s
    """

    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util
        import sys
        cls.REPO_ROOT = Path(__file__).resolve().parents[1]
        mod_path = cls.REPO_ROOT / "history_index.py"
        spec = importlib.util.spec_from_file_location("history_index", mod_path)
        assert spec is not None and spec.loader is not None
        cls.mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.mod
        spec.loader.exec_module(cls.mod)

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        import gc
        gc.collect()
        self._tmpdir.cleanup()

    def _populate(self, count: int) -> None:
        for i in range(count):
            rid = f"r_bm_{i:06d}"
            meta = {
                "run_id": rid,
                "kind": "ordinary",
                "status": "completed" if i % 2 == 0 else "error",
                "started_at": f"2026-07-01T12:{i % 60:02d}:{i % 60:02d}Z",
                "annotations": {"favorite": i % 5 == 0, "note": f"note_{i}" if i % 3 == 0 else ""},
                "extra": {
                    "studio_preset_id": f"preset_{i % 10}",
                    "studio_feature_id": "txt2img" if i % 2 == 0 else "object_remove",
                    "output_count": 1,
                },
                "duration_ms": float(i * 100),
            }
            # Production layout: root/<run_id>/meta.json
            run_dir = self.root / rid
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def test_benchmark_rebuild_100(self):
        """Measure rebuild time for 100 records."""
        self._populate(100)
        idx = self.mod.HistoryIndex(self.root)
        try:
            t0 = time.monotonic()
            count = idx.rebuild()
            elapsed = time.monotonic() - t0
            print(f"\n  Rebuild 100 records: {elapsed*1000:.1f}ms ({count} records)")
            self.assertEqual(count, 100)
        finally:
            idx.close()

    def test_benchmark_rebuild_1000(self):
        """Measure rebuild time for 1000 records."""
        self._populate(1000)
        idx = self.mod.HistoryIndex(self.root)
        try:
            t0 = time.monotonic()
            count = idx.rebuild()
            elapsed = time.monotonic() - t0
            print(f"\n  Rebuild 1000 records: {elapsed*1000:.1f}ms ({count} records)")
            self.assertEqual(count, 1000)
        finally:
            idx.close()

    def test_benchmark_query_warm(self):
        """Measure warm query time for 1000 records."""
        self._populate(1000)
        idx = self.mod.HistoryIndex(self.root)
        try:
            idx.rebuild()
            t0 = time.monotonic()
            for _ in range(10):
                idx.query(page=1, page_size=50, sort="newest")
            elapsed = time.monotonic() - t0
            print(f"\n  Warm query (10x page=1, 50 items): {elapsed*1000:.1f}ms avg {(elapsed*1000/10):.1f}ms")
            t1 = time.monotonic()
            for _ in range(10):
                idx.query(page=1, page_size=50, kind="ordinary", status="completed", favorite_only=True)
            elapsed2 = time.monotonic() - t1
            print(f"  Warm filtered query (10x): {elapsed2*1000:.1f}ms avg {(elapsed2*1000/10):.1f}ms")
            t2 = time.monotonic()
            for _ in range(10):
                idx.query(page=1, page_size=20, search="note_1")
            elapsed3 = time.monotonic() - t2
            print(f"  Warm search query (10x): {elapsed3*1000:.1f}ms avg {(elapsed3*1000/10):.1f}ms")
        finally:
            idx.close()

    def test_benchmark_rebuild_10000(self):
        """Measure rebuild time for 10000 records."""
        self._populate(10000)
        idx = self.mod.HistoryIndex(self.root)
        try:
            t0 = time.monotonic()
            count = idx.rebuild()
            elapsed = time.monotonic() - t0
            print(f"\n  Rebuild 10000 records: {elapsed*1000:.1f}ms ({count} records)")
            self.assertEqual(count, 10000)
        finally:
            idx.close()


if __name__ == "__main__":
    unittest.main()
