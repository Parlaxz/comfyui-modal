"""Production-writer test suite for History V2 (history_v2_writer.py).

Covers the production-style writer flow (``HistoryV2ProductionWriter`` via
``get_writer(tmp_root)``) end-to-end against a temp SQLite store, the
legacy dual-write path through the real ``RunHistoryService``, and the six
History V2 feed sort orders with keyset pagination + mixed-stream merging.

The writer stores its database at ``<data_root>/.studio_history_v2/
history_v2.db``; every test verifies against that exact path.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiment_service import RunHistoryService
from history_v2_repository import HistoryV2Repository
from history_v2_store import HistoryV2Store
from history_v2_writer import (
    _cell_id,
    _gen_id,
    _run_id,
    get_writer,
    reset_writer_config,
    set_asset_resolver,
    set_writer_data_root,
    set_writer_enabled,
)

_LATER = "2026-01-01T10:05:00.000+00:00"
_SUBMIT_META = {
    "requested_controls": {"prompt": "a cat"},
    "studio_preset_id": "preset1",
    "studio_preset_label": "Preset One",
    "workflow_json": {"nodes": {"1": {"class_type": "KSampler"}}},
}


def _png_bytes() -> bytes:
    """Tiny valid 1x1 PNG (byte identity is what matters in tests)."""
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )


class HistoryV2ProductionWriterTests(unittest.TestCase):
    """Cases 1-18 of the production-writer spec + headless-disable check."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_root = Path(self._tmp.name)
        self.addCleanup(reset_writer_config)
        self.writer = get_writer(self.tmp_root)
        self.db_path = self.tmp_root / ".studio_history_v2" / "history_v2.db"
        self.repo = HistoryV2Repository(HistoryV2Store(self.db_path))

    # ── Helpers ──────────────────────────────────────────────────────────

    def _write_png(self, name: str) -> str:
        path = self.tmp_root / name
        path.write_bytes(_png_bytes())
        return str(path)

    def _run_success_flow(self, run_id: str = "r_abcd1234", outputs=None):
        """Production-style submit then complete (case 1 shape)."""
        update_meta = {"output_paths": outputs if outputs is not None else []}
        self.writer.record_run(
            run_id=run_id, kind="studio_run", status="submitted",
            prompt_id="exp1", workflow_hash="wfhash1", meta=dict(_SUBMIT_META),
        )
        self.writer.update_run(
            run_id, status="completed", completed_at=_LATER,
            timings={"end_to_end_total_ms": 500}, meta=update_meta,
        )

    # ── Case 1: single generation success ────────────────────────────────

    def test_single_generation_success(self):
        self._run_success_flow()
        # Writer persists at the documented V2 path under the data root.
        self.assertTrue(self.db_path.is_file())
        detail = self.repo.get_generation(_gen_id("r_abcd1234"))
        self.assertIsNotNone(detail)
        self.assertEqual(detail.generation.workflow_id, "wfhash1")
        self.assertEqual(detail.generation.preset_id, "preset1")
        self.assertEqual(detail.generation.preset_name, "Preset One")
        self.assertEqual(detail.generation.prompt_text, "a cat")
        self.assertEqual(detail.generation.status, "completed")

    # ── Case 2: exactly one run attempt ──────────────────────────────────

    def test_run_attempt_created(self):
        self._run_success_flow()
        detail = self.repo.get_generation(_gen_id("r_abcd1234"))
        self.assertEqual(len(detail.attempts), 1)
        attempt = detail.attempts[0]
        self.assertEqual(attempt.status, "completed")
        self.assertEqual(attempt.mode, "original")
        self.assertIsNotNone(attempt.started_at)
        self.assertEqual(attempt.finished_at, _LATER)
        self.assertEqual(attempt.timing.get("end_to_end_total_ms"), 500)

    # ── Case 3: immutable request snapshot ───────────────────────────────

    def test_immutable_request_snapshot(self):
        self._run_success_flow()
        detail = self.repo.get_generation(_gen_id("r_abcd1234"))
        snapshot = detail.request_snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.workflow, {"nodes": {"1": {"class_type": "KSampler"}}})
        self.assertEqual(snapshot.workflow_hash, "wfhash1")
        self.assertEqual(snapshot.generation_params.get("prompt"), "a cat")

    # ── Case 4: single output asset ──────────────────────────────────────

    def test_single_output_asset(self):
        png = self._write_png("single.png")
        self._run_success_flow(outputs=[png])
        detail = self.repo.get_generation(_gen_id("r_abcd1234"))
        originals = [a for a in detail.assets if a.type == "original"]
        self.assertEqual(len(originals), 1)
        self.assertEqual(originals[0].format, "png")
        self.assertEqual(originals[0].filename, "single.png")

    # ── Case 5: multiple outputs ─────────────────────────────────────────

    def test_multiple_outputs(self):
        png_a = self._write_png("multi_a.png")
        png_b = self._write_png("multi_b.png")
        self._run_success_flow(outputs=[png_a, png_b])
        detail = self.repo.get_generation(_gen_id("r_abcd1234"))
        originals = [a for a in detail.assets if a.type == "original"]
        self.assertEqual(len(originals), 2)
        self.assertEqual({a.filename for a in originals}, {"multi_a.png", "multi_b.png"})

    # ── Case 6: failed run ───────────────────────────────────────────────

    def test_failed_run(self):
        self.writer.record_run(
            run_id="r_failed1", kind="studio_run", status="submitted",
            prompt_id="p", workflow_hash="w", meta={"requested_controls": {}},
        )
        self.writer.update_run(
            "r_failed1", status="error",
            meta={"error": "boom", "_error_detail": "trace"},
        )
        attempt = self.repo.get_attempt(_run_id("r_failed1"))
        self.assertEqual(attempt.status, "failed")
        self.assertEqual(attempt.error, "boom")

    # ── Case 7: canceled run ─────────────────────────────────────────────

    def test_canceled_run(self):
        self.writer.record_run(
            run_id="r_cancel1", kind="studio_run", status="submitted",
            prompt_id="p", workflow_hash="w", meta={},
        )
        self.writer.update_run("r_cancel1", status="canceled")
        attempt = self.repo.get_attempt(_run_id("r_cancel1"))
        self.assertEqual(attempt.status, "canceled")
        self.assertNotIn(attempt.status, ("failed", "completed"))

    # ── Case 8: interrupted run ──────────────────────────────────────────

    def test_interrupted_run(self):
        self.writer.record_run(
            run_id="r_int1", kind="studio_run", status="submitted",
            prompt_id="p", workflow_hash="w", meta={},
        )
        self.writer.update_run("r_int1", status="interrupted")
        attempt = self.repo.get_attempt(_run_id("r_int1"))
        self.assertEqual(attempt.status, "interrupted")

    # ── Case 9: duplicate terminal callbacks / first-terminal-wins ───────

    def test_duplicate_terminal_callback_no_duplicates(self):
        png = self._write_png("dup.png")
        self._run_success_flow(outputs=[png])
        gid = _gen_id("r_abcd1234")
        detail = self.repo.get_generation(gid)
        self.assertEqual(len(detail.attempts), 1)
        originals = [a for a in detail.assets if a.type == "original"]
        self.assertEqual(len(originals), 1)
        asset_count_after_first = len(detail.assets)
        # Replay the identical terminal twice more: no new attempt, no new asset.
        for _ in range(2):
            self.writer.update_run(
                "r_abcd1234", status="completed", meta={"output_paths": [png]}
            )
        detail = self.repo.get_generation(gid)
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(len(detail.assets), asset_count_after_first)
        self.assertEqual(len([a for a in detail.assets if a.type == "original"]), 1)
        # Conflicting replay of a different terminal: first-terminal-wins.
        self.writer.update_run("r_abcd1234", status="failed")
        detail = self.repo.get_generation(gid)
        self.assertEqual(detail.attempts[0].status, "completed")

    # ── Case 10: legacy dual write through the REAL RunHistoryService ────

    def test_legacy_dual_write_intact(self):
        legacy_root = self.tmp_root / "legacy_run_history"
        set_writer_data_root(self.tmp_root)
        set_writer_enabled(True)
        svc = RunHistoryService(legacy_root)
        meta_obj = svc.record_run(
            kind="studio_run", prompt_id="p", status="submitted",
            meta={"requested_controls": {}},
        )
        run_id = meta_obj["run_id"]
        svc.update_run(
            run_id, status="completed", completed_at=_LATER, timings={"x": 1},
        )
        # (a) Legacy write intact at <legacy_root>/<run_id>/meta.json.
        legacy_meta_path = legacy_root / run_id / "meta.json"
        self.assertTrue(legacy_meta_path.is_file())
        legacy_meta = json.loads(legacy_meta_path.read_text(encoding="utf-8"))
        self.assertEqual(legacy_meta["status"], "completed")
        # (b) V2 mirror worked: matching generation + completed attempt.
        v2_repo = HistoryV2Repository(HistoryV2Store(self.db_path))
        detail = v2_repo.get_generation(_gen_id(run_id))
        self.assertIsNotNone(detail)
        self.assertEqual(detail.generation.status, "completed")
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "completed")
        self.assertEqual(detail.attempts[0].timing.get("x"), 1)

    # ── Case 11: experiment created ──────────────────────────────────────

    def test_experiment_created(self):
        result = self.writer.ensure_experiment(
            "exp_studio1", name="My Exp", definition={"production": True},
            cells=[
                {"cell_key": "k1", "sequence": 0, "axis_values": {"seed": 1}},
                {"cell_key": "k2", "sequence": 1, "axis_values": {"seed": 2}},
            ],
        )
        self.assertEqual(result["status"], "draft")
        detail = self.repo.get_experiment("exp_studio1")
        self.assertIsNotNone(detail)
        self.assertEqual(detail.experiment.name, "My Exp")
        self.assertEqual(detail.experiment.definition, {"production": True})
        self.assertEqual(detail.experiment.status, "draft")
        self.assertEqual(len(detail.experiment.cell_ordering), 2)

    # ── Case 12: fixed cells persisted / deterministic ids ───────────────

    def test_fixed_cells_persisted(self):
        cells = [
            {"cell_key": "k1", "sequence": 0, "axis_values": {"seed": 1}},
            {"cell_key": "k2", "sequence": 1, "axis_values": {"seed": 2}},
        ]
        self.writer.ensure_experiment(
            "exp_studio1", name="My Exp", definition={"production": True}, cells=cells,
        )
        detail = self.repo.get_experiment("exp_studio1")
        self.assertEqual(len(detail.cells), 2)
        self.assertEqual([c.position for c in detail.cells], [0, 1])
        self.assertEqual(detail.cells[0].axis_labels, {"seed": 1})
        self.assertEqual(detail.cells[1].axis_labels, {"seed": 2})
        expected_ids = [_cell_id("exp_studio1", "k1"), _cell_id("exp_studio1", "k2")]
        self.assertEqual([c.cell_id for c in detail.cells], expected_ids)
        # Second call is a no-op: identical ids, no duplicates.
        self.writer.ensure_experiment(
            "exp_studio1", name="My Exp", definition={"production": True}, cells=cells,
        )
        detail2 = self.repo.get_experiment("exp_studio1")
        self.assertEqual([c.cell_id for c in detail2.cells], expected_ids)
        self.assertEqual(len(detail2.cells), 2)

    # ── Case 13: cell success ────────────────────────────────────────────

    def test_cell_success(self):
        png = self._write_png("cell.png")
        self.writer.ensure_experiment(
            "exp_studio1", name="My Exp", definition={"production": True},
            cells=[{"cell_key": "k1", "sequence": 0, "axis_values": {"seed": 1}}],
        )
        result = self.writer.mirror_cell_terminal(
            "exp_studio1", cell_key="k1", attempt_id="a1", status="completed",
            params={"prompt": "p"}, output_paths=[png],
        )
        cell = self.repo.get_experiment_cell(result["cell_id"])
        self.assertEqual(cell.status, "completed")
        self.assertEqual(cell.generation_id, result["generation_id"])
        detail = self.repo.get_generation(result["generation_id"])
        self.assertIsNotNone(detail)
        self.assertEqual(detail.generation.experiment_id, "exp_studio1")
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "completed")
        originals = [a for a in detail.assets if a.type == "original"]
        self.assertEqual(len(originals), 1)
        self.assertEqual(originals[0].format, "png")

    # ── Case 14: cell failure ────────────────────────────────────────────

    def test_cell_failure(self):
        self.writer.ensure_experiment(
            "exp_studio1", name="My Exp", definition={"production": True},
            cells=[{"cell_key": "k1", "sequence": 0, "axis_values": {"seed": 1}}],
        )
        result = self.writer.mirror_cell_terminal(
            "exp_studio1", cell_key="k1", attempt_id="a1", status="failed",
            error="cell exploded", params={"prompt": "p"},
        )
        cell = self.repo.get_experiment_cell(result["cell_id"])
        self.assertEqual(cell.status, "failed")
        self.assertEqual(cell.error, "cell exploded")
        attempt = self.repo.get_attempt(result["run_id"])
        self.assertEqual(attempt.status, "failed")
        self.assertEqual(attempt.error, "cell exploded")

    # ── Case 15: completed_with_failures aggregation ─────────────────────

    def test_completed_with_failures_aggregation(self):
        self.writer.ensure_experiment(
            "exp_studio1", name="My Exp", definition={"production": True},
            cells=[
                {"cell_key": "k1", "sequence": 0, "axis_values": {"seed": 1}},
                {"cell_key": "k2", "sequence": 1, "axis_values": {"seed": 2}},
            ],
        )
        self.writer.mirror_cell_terminal(
            "exp_studio1", cell_key="k1", attempt_id="a1", status="completed",
        )
        self.writer.mirror_cell_terminal(
            "exp_studio1", cell_key="k2", attempt_id="a2", status="failed",
            error="boom",
        )
        detail = self.repo.get_experiment("exp_studio1")
        self.assertEqual(detail.experiment.status, "completed_with_failures")

    # ── Case 16: interrupted experiment ──────────────────────────────────

    def test_interrupted_experiment(self):
        self.writer.ensure_experiment(
            "exp_studio1", name="My Exp", definition={"production": True},
            cells=[
                {"cell_key": "k1", "sequence": 0, "axis_values": {"seed": 1}},
                {"cell_key": "k2", "sequence": 1, "axis_values": {"seed": 2}},
            ],
        )
        self.writer.mirror_cell_terminal(
            "exp_studio1", cell_key="k1", attempt_id="a1", status="completed",
        )
        self.writer.mirror_cell_terminal(
            "exp_studio1", cell_key="k2", attempt_id="a2", status="interrupted",
        )
        detail = self.repo.get_experiment("exp_studio1")
        self.assertEqual(detail.experiment.status, "interrupted")

    # ── Case 17: finalize_experiment mapping ─────────────────────────────

    def test_canceled_experiment(self):
        self.writer.ensure_experiment(
            "exp_fin", cells=[{"cell_key": "k1", "sequence": 0}],
        )
        self.assertIs(self.writer.finalize_experiment("exp_fin", "canceled"), True)
        self.assertEqual(self.repo.get_experiment("exp_fin").experiment.status, "canceled")
        # "stopped" maps to "interrupted".
        self.writer.ensure_experiment(
            "exp_x", cells=[{"cell_key": "k1", "sequence": 0}],
        )
        self.assertIs(self.writer.finalize_experiment("exp_x", "stopped"), True)
        self.assertEqual(self.repo.get_experiment("exp_x").experiment.status, "interrupted")
        # Unknown experiment → False.
        self.assertIs(self.writer.finalize_experiment("exp_missing", "canceled"), False)

    # ── Case 18: retry history durable (attempt rows untouched) ──────────

    def test_retry_history_durable(self):
        self.writer.ensure_experiment(
            "exp_retry", name="R",
            cells=[{"cell_key": "k1", "sequence": 0, "axis_values": {"seed": 1}}],
        )
        first = self.writer.mirror_cell_terminal(
            "exp_retry", cell_key="k1", attempt_id="a1", status="failed", error="err1",
        )
        second = self.writer.mirror_cell_terminal(
            "exp_retry", cell_key="k1", attempt_id="a2", status="completed",
        )
        self.assertEqual(first["generation_id"], second["generation_id"])
        cell = self.repo.get_experiment_cell(first["cell_id"])
        self.assertEqual(cell.status, "completed")
        detail = self.repo.get_generation(first["generation_id"])
        # Both attempts retained under the cell's generation.
        self.assertEqual(len(detail.attempts), 2)
        failed = [a for a in detail.attempts if a.status == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].error, "err1")
        # Cell-level derivation is "latest effective terminal"; the aggregate
        # experiment status derives from CELL statuses only, so a single
        # completed cell aggregates to "completed" while the failed attempt
        # stays visible at the attempt level (attempt rows are untouched).
        exp = self.repo.get_experiment("exp_retry")
        self.assertEqual(exp.experiment.status, "completed")

    # ── Additional: writer disabled headless (no overrides) ──────────────

    def test_writer_disabled_headless(self):
        reset_writer_config()
        self.assertIsNone(get_writer())


class HistoryV2SortOrderTests(unittest.TestCase):
    """Cases 19-26: the six feed orders, keyset pagination, merging."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = HistoryV2Store(Path(self._tmp.name) / "history_v2.db")
        self.repo = HistoryV2Repository(self.store)

    # ── Seed data (shared across sort tests) ─────────────────────────────

    def _seed_sort_dataset(self):
        def attempt(gen_id, run_id, start, finish):
            a = self.repo.add_attempt(
                gen_id, run_id=run_id, mode="original", started_at=start,
            )
            self.repo.update_attempt_terminal(a.run_id, status="completed", finished_at=finish)

        # A fastest (100ms), B slowest (30s), C no attempts (None), D multi
        # attempt (shared start → duration = MAX = 250ms), E workflow None,
        # F workflow "zeta".  Timestamps mix "Z" and "+00:00" suffixes to prove
        # julianday parses both.
        self.repo.create_generation(
            generation_id="gen_a", workflow_id="Alpha",
            created_at="2026-01-01T10:00:00.000+00:00",
        )
        attempt("gen_a", "run_a1", "2026-01-01T10:00:01.000Z", "2026-01-01T10:00:01.100Z")
        self.repo.create_generation(
            generation_id="gen_b", workflow_id="bravo",
            created_at="2026-01-01T10:01:00.000+00:00",
        )
        attempt("gen_b", "run_b1", "2026-01-01T10:01:00.000+00:00", "2026-01-01T10:01:30.000+00:00")
        self.repo.create_generation(
            generation_id="gen_c", workflow_id="", created_at="2026-01-01T10:02:00.000+00:00",
        )
        self.repo.create_generation(
            generation_id="gen_d", workflow_id="delta",
            created_at="2026-01-01T10:03:00.000+00:00",
        )
        attempt("gen_d", "run_d1", "2026-01-01T10:03:01.000Z", "2026-01-01T10:03:01.050Z")
        attempt("gen_d", "run_d2", "2026-01-01T10:03:01.000Z", "2026-01-01T10:03:01.250Z")
        self.repo.create_generation(
            generation_id="gen_e", workflow_id=None, created_at="2026-01-01T10:04:00.000+00:00",
        )
        attempt("gen_e", "run_e1", "2026-01-01T10:04:00.000Z", "2026-01-01T10:04:05.000Z")
        self.repo.create_generation(
            generation_id="gen_f", workflow_id="zeta", created_at="2026-01-01T10:05:00.000+00:00",
        )
        attempt("gen_f", "run_f1", "2026-01-01T10:05:00.000Z", "2026-01-01T10:05:01.000Z")

    def _assert_durations(self, items):
        """C has no timing (None); every other generation has duration_ms >= 0."""
        durations = {item["generation_id"]: item["duration_ms"] for item in items}
        self.assertIsNone(durations["gen_c"])
        for gid, duration in durations.items():
            if gid == "gen_c":
                continue
            self.assertIsInstance(duration, (int, float))
            self.assertGreaterEqual(duration, 0)

    # ── Case 19: newest ──────────────────────────────────────────────────

    def test_sort_newest(self):
        self._seed_sort_dataset()
        page = self.repo.query_generations(order="newest", limit=200)
        ids = [i["generation_id"] for i in page["items"]]
        self.assertEqual(ids, ["gen_f", "gen_e", "gen_d", "gen_c", "gen_b", "gen_a"])
        self._assert_durations(page["items"])

    # ── Case 20: oldest ──────────────────────────────────────────────────

    def test_sort_oldest(self):
        self._seed_sort_dataset()
        page = self.repo.query_generations(order="oldest", limit=200)
        ids = [i["generation_id"] for i in page["items"]]
        self.assertEqual(ids, ["gen_a", "gen_b", "gen_c", "gen_d", "gen_e", "gen_f"])
        self._assert_durations(page["items"])

    # ── Case 21: fastest (duration ASC, None LAST) ───────────────────────

    def test_sort_fastest(self):
        self._seed_sort_dataset()
        page = self.repo.query_generations(order="fastest", limit=200)
        ids = [i["generation_id"] for i in page["items"]]
        self.assertEqual(ids, ["gen_a", "gen_d", "gen_f", "gen_e", "gen_b", "gen_c"])
        self._assert_durations(page["items"])
        # C (no timing) is LAST in the fastest feed.
        self.assertIsNone(page["items"][-1]["duration_ms"])

    # ── Case 22: slowest (duration DESC, None LAST) ──────────────────────

    def test_sort_slowest(self):
        self._seed_sort_dataset()
        page = self.repo.query_generations(order="slowest", limit=200)
        ids = [i["generation_id"] for i in page["items"]]
        self.assertEqual(ids, ["gen_b", "gen_e", "gen_f", "gen_d", "gen_a", "gen_c"])
        self._assert_durations(page["items"])
        # C (no timing) is LAST in the slowest feed too.
        self.assertIsNone(page["items"][-1]["duration_ms"])

    # ── Case 23: workflow ascending / descending (missing LAST) ──────────

    def test_sort_workflow_asc(self):
        self._seed_sort_dataset()
        page = self.repo.query_generations(order="workflow_asc", limit=200)
        ids = [i["generation_id"] for i in page["items"]]
        self.assertEqual(ids, ["gen_a", "gen_b", "gen_d", "gen_f", "gen_c", "gen_e"])
        self._assert_durations(page["items"])
        # Present group is case-insensitively sorted; None/"" rows are LAST.
        present = page["items"][:4]
        self.assertEqual(
            [i["workflow_id"] for i in present], ["Alpha", "bravo", "delta", "zeta"]
        )
        self.assertEqual(
            [i["workflow_id"] for i in present],
            sorted([i["workflow_id"] for i in present], key=lambda s: s.casefold()),
        )
        self.assertEqual([i["workflow_id"] for i in page["items"][4:]], ["", None])

    def test_sort_workflow_desc(self):
        self._seed_sort_dataset()
        page = self.repo.query_generations(order="workflow_desc", limit=200)
        ids = [i["generation_id"] for i in page["items"]]
        self.assertEqual(ids, ["gen_f", "gen_d", "gen_b", "gen_a", "gen_c", "gen_e"])
        self._assert_durations(page["items"])
        present = page["items"][:4]
        self.assertEqual(
            [i["workflow_id"] for i in present], ["zeta", "delta", "bravo", "Alpha"]
        )
        self.assertEqual([i["workflow_id"] for i in page["items"][4:]], ["", None])

    # ── Case 24: mixed feed merge + keyset pagination ────────────────────

    def test_mixed_feed_sort_pagination(self):
        import history_v2_routes as routes

        self._seed_sort_dataset()
        self.repo.create_experiment(
            name="exp one", created_at="2026-01-01T10:00:30.000+00:00",
            cells=[{"axis_labels": {"seed": 1}}],
        )
        self.repo.create_experiment(
            name="exp two", created_at="2026-01-01T10:04:30.000+00:00",
            cells=[{"axis_labels": {"seed": 2}}],
        )
        for order in ("newest", "fastest"):
            gen_page = self.repo.query_generations(order=order, limit=3)
            exp_page = self.repo.query_experiments(order=order, limit=3)
            gen_items = routes._build_generation_items(self.repo, gen_page["items"])
            exp_items = routes._build_experiment_items(self.repo, exp_page["items"])
            merged = routes._merge_streams(gen_items, exp_items, order)
            all_items = gen_items + exp_items
            reference = sorted(
                all_items, key=lambda item: routes._sort_tuple(item, order)
            )
            self.assertEqual(
                [item["id"] for item in merged], [item["id"] for item in reference]
            )
            # Walk the generation pages to exhaustion: no dupes, no losses.
            seen: list[str] = []
            cursor = None
            while True:
                page = self.repo.query_generations(order=order, limit=3, cursor=cursor)
                seen.extend(item["generation_id"] for item in page["items"])
                cursor = page["next_cursor"]
                if cursor is None:
                    break
            self.assertEqual(len(seen), 6)
            self.assertEqual(len(set(seen)), 6)

    # ── Case 25: missing durations are deterministic (None rows last) ─────

    def test_missing_duration_deterministic(self):
        self.repo.create_generation(
            generation_id="gen_ma", created_at="2026-01-01T10:00:00.000+00:00",
        )
        self.repo.create_generation(
            generation_id="gen_mb", created_at="2026-01-01T10:00:00.000+00:00",
        )
        self.repo.create_generation(
            generation_id="gen_t", created_at="2026-01-01T10:01:00.000+00:00",
        )
        attempt = self.repo.add_attempt(
            "gen_t", run_id="run_tt", mode="original",
            started_at="2026-01-01T10:01:00.000Z",
        )
        self.repo.update_attempt_terminal(
            attempt.run_id, status="completed", finished_at="2026-01-01T10:01:01.000Z",
        )
        self.repo.create_generation(
            generation_id="gen_mc", created_at="2026-01-01T10:02:00.000+00:00",
        )
        for order in ("fastest", "slowest"):
            page = self.repo.query_generations(order=order, limit=200)
            ids = [i["generation_id"] for i in page["items"]]
            # Timed row first; None rows (created_at ASC, id ASC) deterministic.
            self.assertEqual(ids, ["gen_t", "gen_ma", "gen_mb", "gen_mc"])
            durations = {i["generation_id"]: i["duration_ms"] for i in page["items"]}
            self.assertIsNone(durations["gen_ma"])
            self.assertIsNone(durations["gen_mb"])
            self.assertIsNone(durations["gen_mc"])
            self.assertIsInstance(durations["gen_t"], (int, float))
            self.assertGreaterEqual(durations["gen_t"], 0)

    # ── Additional: invalid order raises ─────────────────────────────────

    def test_invalid_order_raises(self):
        with self.assertRaises(ValueError):
            self.repo.query_generations(order="bogus")
        with self.assertRaises(ValueError):
            self.repo.query_experiments(order="bogus")


class HistoryV2C14ProducerAssetRegressionTests(unittest.TestCase):
    """C14 regression: producer (LeaseRegistry-shaped) primary-asset adoption
    through the ``set_asset_resolver`` / ``reset_writer_config`` seam.

    Pins the C13-shaped descriptor-only contract at the writer boundary:

    * a valid ``primary_asset_id`` with NO output path adopts exactly ONE
      ``original`` as a managed reference — the producer file is never copied,
      re-encoded, or thumbnailed, and the producer file stays valid;
    * an UNKNOWN ``primary_asset_id`` fabricates no asset and never invents a
      featured association (strictness/finalization lives in the run lane);
    * an output path AND a primary id resolving to the SAME producer output
      dedupe to one logical original with the path-attached asset featured;
    * ONE content-addressed producer id shared across two descriptor-only
      generations adopts in each: the first keeps the producer id, the second
      mints a fresh History ``ast_*`` id with ``metadata.producer_asset_id``
      equal to the producer id — both complete with exactly one visible
      original + featured, and terminal replays never duplicate;
    * a completed run with no outputs and no primary id remains a legitimate
      zero-output record (never fabricated).
    """

    PRODUCER_ID = "ast_c13_producer"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_root = Path(self._tmp.name)
        self.addCleanup(reset_writer_config)
        self.writer = get_writer(self.tmp_root)
        self.db_path = self.tmp_root / ".studio_history_v2" / "history_v2.db"
        self.repo = HistoryV2Repository(HistoryV2Store(self.db_path))
        self.assets_root = self.tmp_root / ".studio_assets"

    # ── Helpers ──────────────────────────────────────────────────────────

    def _producer_file(self, name: str = "producer_output.png") -> str:
        path = self.tmp_root / name
        path.write_bytes(_png_bytes())
        return str(path)

    def _producer_record(self, path: str, asset_id=None) -> dict:
        """LeaseRegistry-shaped producer asset record for a local file."""
        return {
            "asset_id": asset_id or self.PRODUCER_ID,
            "path": path,
            "mime_type": "image/png",
            "content_hash": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "width": 1,
            "height": 1,
            "byte_size": Path(path).stat().st_size,
            "variant": "main",
            "node_id": "6",
            "output_key": "images",
            "output_index": 1,
        }

    def _run_descriptor_success(self, run_id: str, primary_asset_id: str,
                                outputs=None):
        """record_run + completed update with a modern meta carrying
        ``primary_asset_id`` (and optional output paths)."""
        meta = {
            "workflow_id": "wf_c13",
            "workflow_name": "C13 Workflow",
            "workflow_version_id": "wv_c13",
            "preset_id": "p_c13",
            "primary_asset_id": primary_asset_id,
            "requested_controls": {
                "prompt": "a cat", "seed": 0, "steps": 20, "cfg": 0.0,
            },
            "workflow_json": {"3": {"class_type": "KSampler", "inputs": {}}},
        }
        self.writer.record_run(
            run_id=run_id, kind="studio_run", status="submitted",
            prompt_id="exp1", workflow_hash="wfhash_c13", meta=meta,
            output_path=outputs[0] if outputs else "",
        )
        self.writer.update_run(
            run_id, status="completed", completed_at=_LATER,
            timings={"end_to_end_total_ms": 500},
            meta={"output_paths": outputs if outputs is not None else []},
            primary_asset_id=primary_asset_id,
        )

    # ── C13: descriptor-only adoption ────────────────────────────────────

    def test_c13_descriptor_success_adopts_one_reference_no_copy(self):
        file = self._producer_file()
        record = self._producer_record(file)
        set_asset_resolver(
            lambda aid: record if aid == self.PRODUCER_ID else None
        )
        self._run_descriptor_success("r_c13_adopt", self.PRODUCER_ID)

        detail = self.repo.get_generation(_gen_id("r_c13_adopt"))
        self.assertIsNotNone(detail)
        self.assertEqual(detail.generation.status, "completed")
        self.assertEqual(len(detail.attempts), 1)
        attempt = detail.attempts[0]
        self.assertEqual(attempt.status, "completed")
        self.assertEqual(attempt.mode, "original")
        self.assertEqual(attempt.finished_at, _LATER)

        # Exactly ONE logical original; never re-encoded / thumbnailed.
        originals = [a for a in detail.assets if a.type == "original"]
        self.assertEqual(len(originals), 1)
        self.assertEqual(
            [a for a in detail.assets if a.type == "thumbnail"], [],
            "producer adoption must never create a thumbnail copy",
        )
        asset = originals[0]
        self.assertEqual(asset.asset_id, self.PRODUCER_ID)
        self.assertEqual(asset.format, "png")
        self.assertEqual(asset.sha256, record["content_hash"])
        self.assertEqual(asset.metadata.get("producer_asset_id"), self.PRODUCER_ID)
        self.assertEqual(asset.metadata.get("node_id"), "6")
        self.assertEqual(asset.metadata.get("output_index"), 1)

        # No duplicate / copy / re-encode: the managed path IS the producer
        # file reference (never copied into the managed asset root) and the
        # bytes are byte-identical to the original producer file.
        self.assertEqual(Path(asset.managed_path), Path(file).resolve())
        self.assertFalse(
            Path(asset.managed_path).is_relative_to(self.assets_root),
            "adopted asset must not be copied into the managed asset root",
        )
        self.assertEqual(Path(asset.managed_path).read_bytes(), _png_bytes())

        # Featured set; the producer/generic asset remains valid.
        self.assertEqual(detail.generation.featured_asset_id, asset.asset_id)
        self.assertEqual(Path(file).read_bytes(), _png_bytes())

        # Replaying the terminal + same primary id adds nothing.
        self.writer.update_run(
            "r_c13_adopt", status="completed", completed_at=_LATER,
            meta={}, primary_asset_id=self.PRODUCER_ID,
        )
        detail = self.repo.get_generation(_gen_id("r_c13_adopt"))
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(len(detail.assets), 1)
        self.assertEqual(
            [a for a in detail.assets if a.type == "original"], [asset]
        )

    # ── C13: unknown primary asset id fabricates nothing ─────────────────

    def test_c13_unknown_primary_asset_fabricates_nothing(self):
        set_asset_resolver(lambda aid: None)
        self._run_descriptor_success("r_c13_unknown", "ast_c13_unknown")

        detail = self.repo.get_generation(_gen_id("r_c13_unknown"))
        self.assertIsNotNone(detail)
        self.assertEqual(detail.generation.status, "completed")
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "completed")
        self.assertEqual(
            detail.assets, [], "unknown producer id must fabricate no asset"
        )
        self.assertIsNone(detail.generation.featured_asset_id)

    # ── C14: path-only unchanged + ID+path same output dedupes ───────────

    def test_c14_path_only_and_id_path_same_output_single_original(self):
        file = self._producer_file()
        record = self._producer_record(file)
        set_asset_resolver(
            lambda aid: record if aid == self.PRODUCER_ID else None
        )

        # (a) Path-only success is unchanged: one copied original, featured.
        self.writer.record_run(
            run_id="r_path1", kind="studio_run", status="submitted",
            prompt_id="p", workflow_hash="w", meta={"workflow_id": "wf_p"},
            output_path=file,
        )
        self.writer.update_run(
            "r_path1", status="completed", completed_at=_LATER, meta={},
        )
        detail = self.repo.get_generation(_gen_id("r_path1"))
        originals = [a for a in detail.assets if a.type == "original"]
        self.assertEqual(len(originals), 1)
        self.assertEqual(Path(originals[0].managed_path).read_bytes(), _png_bytes())
        self.assertEqual(
            detail.generation.featured_asset_id, originals[0].asset_id
        )

        # (b) ID+path for the SAME producer output → still exactly ONE logical
        # original (the path-attached copy wins; the producer reference dedupes
        # against it via content_hash — no producer_asset_id asset is added)
        # and it stays featured.  The path copy may carry its own thumbnail.
        self._run_descriptor_success("r_both1", self.PRODUCER_ID, outputs=[file])
        detail = self.repo.get_generation(_gen_id("r_both1"))
        originals = [a for a in detail.assets if a.type == "original"]
        self.assertEqual(
            len(originals), 1, "ID+path same output must dedupe to one original"
        )
        self.assertEqual(
            [a for a in detail.assets if a.metadata.get("producer_asset_id")],
            [], "producer reference must dedupe against the path copy",
        )
        self.assertEqual(Path(originals[0].managed_path).read_bytes(), _png_bytes())
        self.assertEqual(originals[0].sha256, record["content_hash"])
        self.assertEqual(
            detail.generation.featured_asset_id, originals[0].asset_id,
            "the path-attached original stays featured",
        )

    # ── C14: one content-addressed producer id across two generations ────

    def test_c14_same_content_addressed_producer_id_across_generations(self):
        """Two descriptor-only successful generations sharing ONE content-
        addressed producer ``asset_id`` both complete with exactly one visible
        original and a featured asset: the first generation keeps the producer
        id as its History asset id, the second mints a fresh ``ast_*``
        History-local id with ``metadata["producer_asset_id"]`` equal to the
        producer id.  Replaying the terminal for either never duplicates."""
        shared_id = "ast_c13_shared"
        file = self._producer_file()
        record = self._producer_record(file, asset_id=shared_id)
        set_asset_resolver(lambda aid: record if aid == shared_id else None)

        self._run_descriptor_success("r_share1", shared_id)
        self._run_descriptor_success("r_share2", shared_id)

        first = self.repo.get_generation(_gen_id("r_share1"))
        second = self.repo.get_generation(_gen_id("r_share2"))
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)

        # Both generations complete with exactly one visible original +
        # featured (a producer adoption never thumbnails).
        for detail in (first, second):
            self.assertEqual(detail.generation.status, "completed")
            self.assertEqual(len(detail.attempts), 1)
            self.assertEqual(detail.attempts[0].status, "completed")
            originals = [a for a in detail.assets if a.type == "original"]
            self.assertEqual(len(originals), 1, "exactly one visible original")
            self.assertEqual(
                [a for a in detail.assets if a.type == "thumbnail"], [],
                "producer adoption must never thumbnail",
            )
            self.assertEqual(
                detail.generation.featured_asset_id, originals[0].asset_id
            )

        # First generation keeps the content-addressed producer id itself.
        first_asset = [a for a in first.assets if a.type == "original"][0]
        self.assertEqual(first_asset.asset_id, shared_id)
        self.assertEqual(first_asset.metadata.get("producer_asset_id"), shared_id)
        # Second generation mints a fresh History-local ast_* id and retains
        # the producer identity in metadata.
        second_asset = [a for a in second.assets if a.type == "original"][0]
        self.assertNotEqual(second_asset.asset_id, shared_id)
        self.assertTrue(second_asset.asset_id.startswith("ast_"))
        self.assertEqual(
            second_asset.metadata.get("producer_asset_id"), shared_id
        )
        # Both adoptions reference the same producer file bytes.
        self.assertEqual(Path(first_asset.managed_path).read_bytes(), _png_bytes())
        self.assertEqual(Path(second_asset.managed_path).read_bytes(), _png_bytes())

        # Replaying the terminal + same primary id adds nothing to either.
        self.writer.update_run(
            "r_share1", status="completed", completed_at=_LATER,
            meta={}, primary_asset_id=shared_id,
        )
        self.writer.update_run(
            "r_share2", status="completed", completed_at=_LATER,
            meta={}, primary_asset_id=shared_id,
        )
        for run_id, expected_asset in (
            ("r_share1", first_asset), ("r_share2", second_asset),
        ):
            detail = self.repo.get_generation(_gen_id(run_id))
            self.assertEqual(len(detail.attempts), 1)
            self.assertEqual(len(detail.assets), 1)
            self.assertEqual(
                [a for a in detail.assets if a.type == "original"],
                [expected_asset], "terminal replay must not duplicate",
            )
            self.assertEqual(
                detail.generation.featured_asset_id, expected_asset.asset_id
            )

    # ── C14: legitimate zero-output writer contract ──────────────────────

    def test_c14_zero_output_writer_contract_allowed(self):
        # A completed run with no output paths and no primary asset id is a
        # legitimate zero-output record (e.g. descriptor runs): it completes
        # with zero assets and no featured association, never fabricating.
        self.writer.record_run(
            run_id="r_zero1", kind="studio_run", status="submitted",
            prompt_id="p", workflow_hash="w", meta={"workflow_id": "wf_z"},
        )
        self.writer.update_run(
            "r_zero1", status="completed", completed_at=_LATER, meta={},
        )
        detail = self.repo.get_generation(_gen_id("r_zero1"))
        self.assertEqual(detail.generation.status, "completed")
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "completed")
        self.assertEqual(detail.assets, [])
        self.assertIsNone(detail.generation.featured_asset_id)


if __name__ == "__main__":
    unittest.main()
