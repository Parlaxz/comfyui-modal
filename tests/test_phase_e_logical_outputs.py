"""Focused E1B logical-output identity and projection regressions."""
from __future__ import annotations

import hashlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from history_v2_models import (
    Asset,
    ExperimentCell,
    Generation,
    GenerationDetail,
    RunAttempt,
)
from history_v2_repository import HistoryV2Repository
from history_v2_routes import (
    _build_outputs,
    _cell_generation_payload,
    _detail_cell,
    _generation_feed_item,
)
from history_v2_store import HistoryV2Store
from history_v2_writer import (
    HistoryV2ProductionWriter,
    reset_writer_config,
    set_asset_resolver,
)


T0 = "2026-08-17T10:00:00.000+00:00"
T1 = "2026-08-17T10:01:00.000+00:00"
T2 = "2026-08-17T10:02:00.000+00:00"
KEY_A = "node:9:slot:images:item:0"
KEY_B = "node:9:slot:images:item:1"
KEY_OTHER_NODE = "node:10:slot:images:item:0"


def _asset(
    asset_id: str,
    asset_type: str,
    path: str,
    *,
    key: str | None = KEY_A,
    run_id: str | None = None,
    created_at: str = T0,
) -> Asset:
    return Asset(
        asset_id=asset_id,
        generation_id="gen_e1b",
        type=asset_type,
        managed_path=path,
        filename=f"{asset_id}.png",
        created_at=created_at,
        run_id=run_id,
        format="png",
        logical_output_key=key,
    )


def _attempt(
    run_id: str,
    mode: str = "original",
    status: str = "completed",
    *,
    created_at: str = T0,
    error: str | None = None,
) -> RunAttempt:
    return RunAttempt(
        run_id=run_id,
        generation_id="gen_e1b",
        mode=mode,
        status=status,
        created_at=created_at,
        error=error,
    )


def _feed_generation(assets, attempts, featured_asset_id=None):
    return _generation_feed_item(
        {
            "generation_id": "gen_e1b",
            "status": "completed",
            "created_at": T0,
            "featured_asset_id": featured_asset_id,
        },
        assets,
        attempts,
    )


class LogicalOutputProjectionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _path(self, name: str) -> str:
        path = self.root / name
        path.write_bytes(name.encode())
        return str(path)

    def test_thumbnail_and_original_same_key_are_one_output(self):
        original = _asset("original", "original", self._path("original.png"), run_id="run_o")
        thumb = _asset("thumb", "thumbnail", self._path("thumb.png"), run_id="run_o")
        attempts = [_attempt("run_o")]

        item = _feed_generation([original, thumb], attempts)

        self.assertEqual(item["output_count"], 1)
        self.assertEqual(len(item["outputs"]), 1)
        self.assertEqual(item["outputs"][0]["original_url"].split("/")[-1], "original")
        self.assertTrue(item["outputs"][0]["thumb_url"].endswith("/thumb"))

    def test_preview_and_original_across_attempts_are_one_output(self):
        preview = _asset("preview", "preview", self._path("preview.png"), run_id="run_p")
        original = _asset("original", "original", self._path("original.png"), run_id="run_o")
        attempts = [
            _attempt("run_p", "preview"),
            _attempt("run_o", "original", created_at=T1),
        ]

        outputs = _build_outputs([preview, original], attempts=attempts)

        self.assertEqual(len(outputs), 1)
        self.assertTrue(outputs[0]["preview_url"].endswith("/preview"))
        self.assertTrue(outputs[0]["original_url"].endswith("/original"))

    def test_failed_original_retry_and_successful_retry_are_one_output(self):
        preview = _asset("preview", "preview", self._path("preview.png"), run_id="run_p")
        original = _asset("original", "original", self._path("original.png"), run_id="run_o2")
        attempts = [
            _attempt("run_p", "preview"),
            _attempt("run_o1", "original", "failed", created_at=T1, error="OOM"),
            _attempt("run_o2", "original", "completed", created_at=T2),
        ]

        outputs = _build_outputs([preview, original], attempts=attempts)

        self.assertEqual(len(outputs), 1)
        self.assertTrue(outputs[0]["original_url"].endswith("/original"))
        self.assertFalse(outputs[0]["original_failed"])

    def test_two_successful_original_retries_newest_wins(self):
        old = _asset("old", "original", self._path("old.png"), run_id="run_o1")
        new = _asset("new", "original", self._path("new.png"), run_id="run_o2", created_at=T1)
        attempts = [
            _attempt("run_o1", created_at=T0),
            _attempt("run_o2", created_at=T1),
        ]

        outputs = _build_outputs([old, new], attempts=attempts)

        self.assertEqual(len(outputs), 1)
        self.assertTrue(outputs[0]["original_url"].endswith("/new"))
        self.assertFalse(outputs[0]["original_failed"])

    def test_failed_latest_retry_preserves_earlier_original(self):
        old = _asset("old", "original", self._path("old.png"), run_id="run_o1")
        attempts = [
            _attempt("run_o1"),
            _attempt("run_o2", "original", "failed", created_at=T1, error="retry failed"),
        ]

        outputs = _build_outputs([old], attempts=attempts)

        self.assertEqual(len(outputs), 1)
        self.assertTrue(outputs[0]["original_url"].endswith("/old"))
        self.assertFalse(outputs[0]["original_failed"])

    def test_item_indexes_and_output_nodes_are_distinct(self):
        assets = [
            _asset("a", "original", self._path("a.png"), key=KEY_A, run_id="run_a"),
            _asset("b", "original", self._path("b.png"), key=KEY_B, run_id="run_b"),
            _asset("other", "original", self._path("other.png"), key=KEY_OTHER_NODE, run_id="run_c"),
        ]
        attempts = [_attempt("run_a"), _attempt("run_b"), _attempt("run_c")]

        item = _feed_generation(assets, attempts)

        self.assertEqual(item["output_count"], 3)
        self.assertEqual(len(item["outputs"]), 3)

    def test_featured_thumbnail_maps_by_logical_membership(self):
        a = _asset("a", "original", self._path("a.png"), key=KEY_A, run_id="run_a")
        a_thumb = _asset("a_thumb", "thumbnail", self._path("a_thumb.png"), key=KEY_A, run_id="run_a")
        b = _asset("b", "original", self._path("b.png"), key=KEY_B, run_id="run_b")
        attempts = [_attempt("run_a"), _attempt("run_b")]

        item = _feed_generation([a, a_thumb, b], attempts, featured_asset_id="a_thumb")

        self.assertEqual(item["featured_output_index"], 0)

    def test_featured_preview_maps_by_logical_membership(self):
        a = _asset("a", "original", self._path("a.png"), key=KEY_A, run_id="run_a")
        b_preview = _asset("b_preview", "preview", self._path("b_preview.png"), key=KEY_B, run_id="run_b")
        attempts = [_attempt("run_a"), _attempt("run_b", "preview")]

        item = _feed_generation([a, b_preview], attempts, featured_asset_id="b_preview")

        self.assertEqual(item["featured_output_index"], 1)

    def test_featured_older_original_stays_in_same_group_after_newer_success(self):
        old = _asset("old", "original", self._path("old.png"), key=KEY_A, run_id="run_old")
        new = _asset("new", "original", self._path("new.png"), key=KEY_A, run_id="run_new", created_at=T1)
        other = _asset("other", "original", self._path("other.png"), key=KEY_B, run_id="run_other")
        attempts = [_attempt("run_old"), _attempt("run_new", created_at=T1), _attempt("run_other")]

        item = _feed_generation([old, new, other], attempts, featured_asset_id="old")

        self.assertEqual(item["featured_output_index"], 0)
        self.assertTrue(item["outputs"][0]["original_url"].endswith("/new"))

    def test_remote_keyed_original_keeps_e1a_uri_semantics(self):
        remote = _asset(
            "remote",
            "original",
            "modal://ws_e1b||output_assets/remote.png",
            key=KEY_A,
            run_id="run_remote",
        )

        output = _build_outputs([remote], attempts=[_attempt("run_remote")])[0]

        self.assertTrue(output["original_url"].endswith("/remote"))
        self.assertFalse(output["original_failed"])

    def test_experiment_cell_uses_same_keyed_generation_grouping(self):
        original = _asset("original", "original", self._path("original.png"), key=KEY_A, run_id="run_o")
        thumb = _asset("thumb", "thumbnail", self._path("thumb.png"), key=KEY_A, run_id="run_p")
        attempts = [_attempt("run_p", "preview"), _attempt("run_o")]
        generation = Generation(
            generation_id="gen_e1b",
            created_at=T0,
            status="completed",
            featured_asset_id="thumb",
        )
        payload = _cell_generation_payload(
            GenerationDetail(generation=generation, attempts=attempts, assets=[original, thumb])
        )

        self.assertEqual(len(payload["outputs"]), 1)
        self.assertEqual(payload["featured_output_index"], 0)

        cell = ExperimentCell(
            cell_id="cell_e1b",
            experiment_id="exp_e1b",
            position=0,
            status="completed",
            updated_at=T0,
            generation_id="gen_e1b",
        )
        projected = _detail_cell(
            cell,
            {"gen_e1b": [original, thumb]},
            {"cell_e1b": attempts},
            {},
        )
        self.assertTrue(projected["original_url"].endswith("/original"))

    def test_legacy_unkeyed_assets_group_only_by_run(self):
        first = _asset("first", "original", self._path("first.png"), key=None, run_id="run_legacy")
        second = _asset("second", "thumbnail", self._path("second.png"), key=None, run_id="run_legacy")
        orphan = _asset("orphan", "original", self._path("orphan.png"), key=None)

        outputs = _build_outputs([first, second, orphan])

        self.assertEqual(len(outputs), 2)

    def test_mixed_keyed_and_legacy_data_is_deterministic(self):
        keyed = _asset("keyed", "original", self._path("keyed.png"), key=KEY_A, run_id="run_k")
        keyed_thumb = _asset("keyed_thumb", "thumbnail", self._path("keyed_thumb.png"), key=KEY_A, run_id="run_k")
        legacy = _asset("legacy", "original", self._path("legacy.png"), key=None, run_id="run_l")
        legacy_thumb = _asset("legacy_thumb", "thumbnail", self._path("legacy_thumb.png"), key=None, run_id="run_l")
        orphan = _asset("orphan", "original", self._path("orphan.png"), key=None)

        first = _build_outputs([orphan, legacy_thumb, keyed, legacy, keyed_thumb])
        second = _build_outputs([keyed_thumb, legacy, orphan, keyed, legacy_thumb])

        self.assertEqual(
            [output["asset_id"] for output in first],
            [output["asset_id"] for output in second],
        )
        self.assertEqual(len(first), 3)


class LogicalOutputPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.db_path = self.root / ".studio_history_v2" / "history_v2.db"
        self.repo = HistoryV2Repository(HistoryV2Store(self.db_path))

    def test_repository_round_trips_logical_output_key(self):
        generation = self.repo.create_generation(generation_id="gen_e1b")
        asset = self.repo.attach_asset(
            generation.generation_id,
            asset_type="original",
            data=b"original",
            filename="original.png",
            fmt="png",
            logical_output_key=KEY_A,
        )

        stored = self.repo.get_asset(asset.asset_id)

        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.logical_output_key, KEY_A)

    def test_migration_adds_key_column_and_is_idempotent(self):
        legacy_path = self.root / "legacy.db"
        conn = sqlite3.connect(legacy_path)
        conn.execute(
            """CREATE TABLE assets (
                asset_id TEXT PRIMARY KEY,
                generation_id TEXT NOT NULL,
                run_id TEXT,
                type TEXT NOT NULL,
                managed_path TEXT NOT NULL,
                filename TEXT NOT NULL,
                width INTEGER,
                height INTEGER,
                format TEXT,
                sha256 TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            "INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("legacy", "gen_legacy", None, "original", "/missing", "old.png",
             None, None, "png", None, "{}", T0),
        )
        conn.commit()
        conn.close()

        store = HistoryV2Store(legacy_path)
        store.initialize()
        store.initialize()
        columns = {
            row["name"] for row in store.execute("PRAGMA table_info(assets)")
        }
        row = store.execute(
            "SELECT logical_output_key FROM assets WHERE asset_id = ?", ("legacy",)
        )[0]

        self.assertIn("logical_output_key", columns)
        self.assertIsNone(row["logical_output_key"])
        self.assertEqual(store.execute("PRAGMA user_version")[0][0], 2)


class LogicalOutputWriterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.writer = HistoryV2ProductionWriter(self.root)
        self.addCleanup(reset_writer_config)

    def _file(self, name: str) -> str:
        path = self.root / name
        path.write_bytes(name.encode())
        return str(path)

    def test_writer_consumes_explicit_and_derived_output_keys(self):
        explicit_path = self._file("explicit.png")
        self.writer.record_run(
            run_id="run_explicit",
            kind="studio_run",
            status="submitted",
            meta={
                "output_paths": [explicit_path],
                "logical_output_key": KEY_A,
            },
        )
        self.writer.update_run("run_explicit", status="completed", meta={})

        derived_path = self._file("derived.png")
        self.writer.record_run(
            run_id="run_derived",
            kind="studio_run",
            status="submitted",
            meta={
                "output_paths": [derived_path],
                "node_id": "9",
                "output_key": "images",
                "output_index": 1,
            },
        )
        self.writer.update_run("run_derived", status="completed", meta={})

        repo = HistoryV2Repository(HistoryV2Store(self.root / ".studio_history_v2" / "history_v2.db"))
        explicit = repo.get_generation_assets("gen_" + hashlib.sha256(b"v2gen:run_explicit").hexdigest()[:12])
        derived = repo.get_generation_assets("gen_" + hashlib.sha256(b"v2gen:run_derived").hexdigest()[:12])

        self.assertEqual({a.logical_output_key for a in explicit if a.type == "original"}, {KEY_A})
        self.assertEqual(
            {a.logical_output_key for a in derived if a.type == "original"},
            {"node:9:slot:images:item:1"},
        )

    def test_producer_adoption_consumes_explicit_key(self):
        producer_id = "producer_e1b"
        path = self._file("producer.png")
        record = {
            "asset_id": producer_id,
            "path": path,
            "mime_type": "image/png",
            "content_hash": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "node_id": "9",
            "output_key": "images",
            "output_index": 0,
            "logical_output_key": KEY_A,
        }
        set_asset_resolver(lambda asset_id: record if asset_id == producer_id else None)

        self.writer.record_run(
            run_id="run_producer",
            kind="studio_run",
            status="submitted",
            meta={"primary_asset_id": producer_id},
        )
        self.writer.update_run(
            "run_producer",
            status="completed",
            primary_asset_id=producer_id,
            meta={},
        )

        repo = HistoryV2Repository(HistoryV2Store(self.root / ".studio_history_v2" / "history_v2.db"))
        generation_id = "gen_" + hashlib.sha256(b"v2gen:run_producer").hexdigest()[:12]
        assets = repo.get_generation_assets(generation_id)

        self.assertEqual([a.logical_output_key for a in assets], [KEY_A])


if __name__ == "__main__":
    unittest.main()
