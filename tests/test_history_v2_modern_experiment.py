"""D4 modern-experiment durable tests (History V2 + modern routes).

Covers the frozen modern-experiment contract (Phase D / lane L2) against the
durable History V2 layer:

* ``create_modern_matrix``: atomic complete matrix, mid-create rollback, fixed
  ordering/identity, queued immutable request snapshots;
* the experiment-bound repository adapter: atomic CAS claims (double-claim),
  running/terminal first-wins and stale-attempt guards, queued cancel,
  aggregate-status precedence, startup recovery idempotence, resume/retry
  attempt creation;
* the modern routes: status projection, mixed feed, one-card experiment detail,
  queued/running cancel, resume, retry.

Everything runs against temp SQLite databases via
``HistoryV2Store``/``HistoryV2Repository`` with fake planner / scheduler
registry / aiohttp request helpers.  Never Modal, never deploy, never
generation.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from history_v2_models import (
    CLAIM_ALREADY_CLAIMED,
    CLAIM_CLAIMED,
    CLAIM_NOT_FOUND,
    CLAIM_TERMINAL,
    ExperimentCell,
    RunAttempt,
    derive_experiment_status,
)
from history_v2_repository import HistoryV2Repository
from history_v2_routes import register_history_v2_routes
from history_v2_store import HistoryV2Store

import experiment_modern_routes as emr
from experiment_modern_routes import register_experiment_modern_routes
from experiment_modern_routes import startup_experiment_modern_lifecycle

T0 = "2026-08-15T00:00:00.000+00:00"


# ── Shared fixture helpers ────────────────────────────────────────────────


def _execution_plan(cell_id: str) -> dict:
    return {
        "workflow": {
            "name": f"Workflow {cell_id}",
            "extra": {"workflow": {"name": f"Workflow {cell_id}"}},
        },
        "workflow_hash": f"wh_{cell_id}",
        "workflow_version_id": "v_frozen",
        "deployment_identity": {"gpu": "RTX6000"},
    }


def _cell_spec(
    cell_id: str,
    *,
    position: int | None = None,
    workflow_id: str | None = None,
    execution_plan: dict | None = None,
    error: str | None = None,
    error_code: str | None = None,
    **kw,
) -> dict:
    spec: dict = {
        "cell_id": cell_id,
        "axis_values": {"seed": 1},
        "controls": {"seed": 1},
        "merged_values": {"seed": 1},
        "axis_to_control": {"seed": "seed"},
        "workflow_id": workflow_id or f"wf_{cell_id}",
        "workflow_version_id": "v_frozen",
        "preset_id": "p_frozen",
        "preset_name": "Preset",
        "workflow_name": f"Workflow {cell_id}",
        "plan_hash": f"h_{cell_id}",
        "workflow_hash": f"wh_{cell_id}",
        "execution_plan": execution_plan if execution_plan is not None else _execution_plan(cell_id),
    }
    if position is not None:
        spec["position"] = position
    if error:
        spec["error"] = error
    if error_code:
        spec["error_code"] = error_code
    spec.update(kw)
    return spec


def _definition(cells: list[dict]) -> dict:
    return {"version": 2, "contract": "modern_v2", "cells": list(cells)}


# ── Repository: atomic matrix + rollback ──────────────────────────────────


class HistoryV2ModernMatrixTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_root = Path(self._tmp.name)
        self.db_path = self.data_root / ".studio_history_v2" / "history_v2.db"
        self.store = HistoryV2Store(self.db_path)
        self.repo = HistoryV2Repository(self.store)
        self.exp_id = "exp_test"

    def _matrix(self, cell_ids=("a", "b"), *, experiment_id=None, created_at=T0, **kw):
        specs = [_cell_spec(cid) for cid in cell_ids]
        detail = self.repo.create_modern_matrix(
            experiment_id=experiment_id or self.exp_id,
            name="Matrix",
            definition=_definition(specs),
            cells=specs,
            created_at=created_at,
            **kw,
        )
        return detail, specs

    def _count(self, table: str) -> int:
        return int(self.store.execute(f"SELECT COUNT(*) FROM {table}")[0][0])

    # ── atomic complete matrix ──────────────────────────────────────────

    def test_create_modern_matrix_is_atomic_and_complete(self):
        detail, specs = self._matrix(("a", "b", "c"))

        # Experiment row: fixed ordering + counts.
        exp = detail.experiment
        self.assertEqual(exp.experiment_id, self.exp_id)
        self.assertEqual(exp.status, "running")  # queued cells aggregate to running
        self.assertEqual(exp.expected_cell_count, 3)
        self.assertEqual(exp.cell_ordering, ["a", "b", "c"])

        # Every cell: fixed position, one queued attempt, linked generation.
        self.assertEqual([c.cell_id for c in detail.cells], ["a", "b", "c"])
        for index, cell in enumerate(detail.cells):
            self.assertEqual(cell.position, index)
            self.assertEqual(cell.status, "queued")
            self.assertIsNotNone(cell.generation_id)
            self.assertEqual(len(cell.attempt_ids), 1)

        # Every generation: queued attempt → running, linked immutable snapshot.
        for cell in detail.cells:
            gdetail = self.repo.get_generation(cell.generation_id)
            self.assertIsNotNone(gdetail)
            assert gdetail is not None
            self.assertEqual(gdetail.generation.status, "running")
            self.assertIsNotNone(gdetail.generation.request_snapshot_id)
            self.assertEqual(len(gdetail.attempts), 1)
            attempt = gdetail.attempts[0]
            self.assertEqual(attempt.status, "queued")
            self.assertIsNone(attempt.started_at)
            self.assertEqual(attempt.cell_id, cell.cell_id)
            snap = gdetail.request_snapshot
            self.assertIsNotNone(snap)
            assert snap is not None
            self.assertEqual(snap.generation_id, cell.generation_id)
            self.assertEqual(snap.workflow, {"name": f"Workflow {cell.cell_id}",
                                             "extra": {"workflow": {"name": f"Workflow {cell.cell_id}"}}})
            # The full immutable cell plan is preserved verbatim.
            self.assertEqual(snap.request["cell_id"], cell.cell_id)
            self.assertEqual(snap.execution_plan["workflow_hash"], f"wh_{cell.cell_id}")

        # One row per table, nothing orphaned.
        self.assertEqual(self._count("experiments"), 1)
        self.assertEqual(self._count("experiment_cells"), 3)
        self.assertEqual(self._count("generations"), 3)
        self.assertEqual(self._count("run_attempts"), 3)
        self.assertEqual(self._count("request_snapshots"), 3)

    def test_create_modern_matrix_planning_invalid_cell_gets_terminal_failed(self):
        specs = [_cell_spec("bad", error="axis value unknown", error_code="INVALID_AXIS")]
        detail = self.repo.create_modern_matrix(
            experiment_id=self.exp_id,
            name="M",
            definition=_definition(specs),
            cells=specs,
            created_at=T0,
        )
        cell = detail.cells[0]
        self.assertEqual(cell.status, "failed")
        self.assertEqual(cell.error, "axis value unknown")
        gdetail = self.repo.get_generation(cell.generation_id)
        assert gdetail is not None
        self.assertEqual(gdetail.attempts[0].status, "failed")
        self.assertEqual(gdetail.attempts[0].error, "axis value unknown")
        self.assertIsNotNone(gdetail.attempts[0].finished_at)

    # ── mid-create rollback ─────────────────────────────────────────────

    def _assert_empty(self):
        for table in (
            "experiments",
            "experiment_cells",
            "generations",
            "run_attempts",
            "request_snapshots",
        ):
            self.assertEqual(self._count(table), 0, f"{table} should be empty after rollback")

    def test_rollback_on_duplicate_cell_id(self):
        specs = [_cell_spec("dup"), _cell_spec("dup")]
        with self.assertRaises(ValueError):
            self.repo.create_modern_matrix(
                experiment_id=self.exp_id, name="M", definition=_definition(specs),
                cells=specs, created_at=T0,
            )
        self._assert_empty()

    def test_rollback_on_missing_cell_id(self):
        specs = [_cell_spec("a"), {"axis_values": {"seed": 1}}]
        with self.assertRaises(ValueError):
            self.repo.create_modern_matrix(
                experiment_id=self.exp_id, name="M", definition=_definition(specs),
                cells=specs, created_at=T0,
            )
        self._assert_empty()

    def test_rollback_on_empty_cells(self):
        with self.assertRaises(ValueError):
            self.repo.create_modern_matrix(
                experiment_id=self.exp_id, name="M", definition=_definition([]),
                cells=[], created_at=T0,
            )
        self._assert_empty()

    def test_rollback_on_position_mismatch(self):
        specs = [_cell_spec("a"), _cell_spec("b", position=5)]
        with self.assertRaises(ValueError):
            self.repo.create_modern_matrix(
                experiment_id=self.exp_id, name="M", definition=_definition(specs),
                cells=specs, created_at=T0,
            )
        self._assert_empty()

    def test_rollback_on_duplicate_explicit_generation_id(self):
        specs = [
            _cell_spec("a", generation_id="gen_fixed"),
            _cell_spec("b", generation_id="gen_fixed"),
        ]
        with self.assertRaises(ValueError):
            self.repo.create_modern_matrix(
                experiment_id=self.exp_id, name="M", definition=_definition(specs),
                cells=specs, created_at=T0,
            )
        self._assert_empty()

    # ── fixed ordering / identity ───────────────────────────────────────

    def test_fixed_ordering_and_stable_identity(self):
        specs = [
            _cell_spec("a", position=0, generation_id="gen_fixed_a", run_id="run_fixed_a",
                       request_snapshot_id="snap_fixed_a"),
            _cell_spec("b", position=1, generation_id="gen_fixed_b", run_id="run_fixed_b",
                       request_snapshot_id="snap_fixed_b"),
        ]
        detail = self.repo.create_modern_matrix(
            experiment_id=self.exp_id, name="M", definition=_definition(specs),
            cells=specs, created_at=T0,
        )
        self.assertEqual(detail.experiment.cell_ordering, ["a", "b"])
        for cell, expected in zip(detail.cells, specs):
            self.assertEqual(cell.position, expected["position"])
            self.assertEqual(cell.generation_id, expected["generation_id"])
            self.assertEqual(cell.attempt_ids, [expected["run_id"]])
            gdetail = self.repo.get_generation(cell.generation_id)
            assert gdetail is not None
            self.assertEqual(gdetail.generation.request_snapshot_id, expected["request_snapshot_id"])
            self.assertEqual(gdetail.attempts[0].run_id, expected["run_id"])

        # Queued sweep preserves the fixed order with the stable attempt ids.
        bound = HistoryV2Repository(HistoryV2Store(self.db_path), experiment_id=self.exp_id)
        queued = bound.load_queued_cells()
        self.assertEqual([q["cell_id"] for q in queued], ["a", "b"])
        self.assertEqual([q["attempt_id"] for q in queued], ["run_fixed_a", "run_fixed_b"])

    def test_modern_matrix_unaffected_by_legacy_create_experiment(self):
        # Legacy seam is untouched: separate tables/rows, no marker required.
        legacy = self.repo.create_experiment(name="legacy", cells=[{}], created_at=T0)
        self.assertEqual(legacy.experiment.status, "draft")
        detail, _ = self._matrix(("a",))
        self.assertEqual(detail.experiment.status, "running")
        self.assertEqual(self._count("experiments"), 2)


# ── Repository: durable adapter semantics ─────────────────────────────────


class HistoryV2ModernRepositoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_root = Path(self._tmp.name)
        self.db_path = self.data_root / ".studio_history_v2" / "history_v2.db"
        self.store = HistoryV2Store(self.db_path)
        self.exp_id = "exp_test"
        self.repo = HistoryV2Repository(self.store, experiment_id=self.exp_id)
        self.detail = self.repo.create_modern_matrix(
            experiment_id=self.exp_id,
            name="Matrix",
            definition=_definition([_cell_spec("a"), _cell_spec("b")]),
            cells=[_cell_spec("a"), _cell_spec("b")],
            created_at=T0,
        )

    def _bound(self, exp_id: str) -> HistoryV2Repository:
        return HistoryV2Repository(HistoryV2Store(self.db_path), experiment_id=exp_id)

    def _current(self, cell_id: str) -> RunAttempt:
        attempt = self.repo.read_active_attempt(cell_id)
        self.assertIsNotNone(attempt)
        assert attempt is not None
        return attempt

    def _claim(self, cell_id: str):
        return self.repo.atomically_claim_queued_attempt(cell_id)

    # ── queued immutable snapshot ───────────────────────────────────────

    def test_retry_reuses_same_immutable_snapshot(self):
        cell = self.detail.cells[0]
        gen_id = cell.generation_id
        first_run = cell.attempt_ids[0]
        snap_before = self.repo.get_generation(gen_id).request_snapshot
        self.assertIsNotNone(snap_before)
        assert snap_before is not None
        before = snap_before.to_dict()

        # Fail the cell, then retry: brand-new attempt under the SAME generation.
        self.assertEqual(self.repo.record_terminal(first_run, cell.cell_id, "failed", error="boom"), True)
        retry = self.repo.create_retry_attempt(cell.cell_id)
        self.assertIsNotNone(retry)
        assert retry is not None
        self.assertEqual(retry.outcome, CLAIM_CLAIMED)
        self.assertNotEqual(retry.attempt.run_id, first_run)
        self.assertEqual(retry.attempt.generation_id, gen_id)

        gdetail = self.repo.get_generation(gen_id)
        assert gdetail is not None
        self.assertEqual([a.run_id for a in gdetail.attempts], [first_run, retry.attempt.run_id])
        stored_cell = self.repo.get_experiment_cell(cell.cell_id)
        assert stored_cell is not None
        self.assertEqual(stored_cell.attempt_ids, [first_run, retry.attempt.run_id])
        self.assertEqual(stored_cell.generation_id, gen_id)

        # The immutable snapshot is byte-identical after the retry.
        snap_after = gdetail.request_snapshot
        self.assertIsNotNone(snap_after)
        assert snap_after is not None
        self.assertEqual(snap_after.to_dict(), before)
        self.assertEqual(snap_after.generation_id, gen_id)

    # ── CAS double claim ────────────────────────────────────────────────

    def test_atomic_double_claim_only_one_winner(self):
        first = self._claim("a")
        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(first.outcome, CLAIM_CLAIMED)
        self.assertEqual(first.attempt.status, "running")
        self.assertIsNotNone(first.attempt.started_at)

        second = self._claim("a")
        self.assertIsNotNone(second)
        assert second is not None
        self.assertEqual(second.outcome, CLAIM_ALREADY_CLAIMED)
        self.assertEqual(second.attempt.run_id, first.attempt.run_id)
        self.assertEqual(second.attempt.status, "running")

    def test_cas_double_claim_across_workers(self):
        # Two repository instances (two "workers") over the same DB file.
        worker_b = self._bound(self.exp_id)
        first = self.repo.atomically_claim_queued_attempt("a")
        second = worker_b.atomically_claim_queued_attempt("a")
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None
        self.assertEqual(first.outcome, CLAIM_CLAIMED)
        self.assertEqual(second.outcome, CLAIM_ALREADY_CLAIMED)
        self.assertEqual(second.attempt.run_id, first.attempt.run_id)

    def test_claim_by_run_id_outcomes(self):
        cell = self.detail.cells[0]
        run_id = cell.attempt_ids[0]
        claimed = self.repo.claim_attempt(run_id, claimed_at=T0)
        self.assertEqual(claimed.outcome, CLAIM_CLAIMED)
        self.assertEqual(claimed.attempt.status, "running")
        self.assertEqual(claimed.attempt.started_at, T0)

        again = self.repo.claim_attempt(run_id)
        self.assertEqual(again.outcome, CLAIM_ALREADY_CLAIMED)

        terminal = self.repo.update_attempt_terminal(run_id, status="completed")
        assert terminal is not None
        after_terminal = self.repo.claim_attempt(run_id)
        self.assertEqual(after_terminal.outcome, CLAIM_TERMINAL)

        missing = self.repo.claim_attempt("run_does_not_exist")
        self.assertEqual(missing.outcome, CLAIM_NOT_FOUND)
        self.assertIsNone(missing.attempt)

    def test_claim_unknown_cell_returns_none(self):
        self.assertIsNone(self.repo.atomically_claim_queued_attempt("nope"))

    # ── running terminal transitions + first-wins / stale guard ─────────

    def test_running_then_terminal_first_wins(self):
        cell = self.detail.cells[0]
        run_id = cell.attempt_ids[0]
        self.assertEqual(self.repo.record_running(run_id, cell.cell_id), None)
        current = self._current(cell.cell_id)
        self.assertEqual(current.status, "running")
        self.assertIsNotNone(current.started_at)
        self.assertEqual(current.run_id, run_id)

        # record_running is idempotent: second call is a no-op.
        self.repo.record_running(run_id, cell.cell_id)
        self.assertEqual(self._current(cell.cell_id).status, "running")

        self.assertEqual(self.repo.record_terminal(run_id, cell.cell_id, "completed"), True)
        gdetail = self.repo.get_generation(cell.generation_id)
        assert gdetail is not None
        self.assertEqual(gdetail.generation.status, "completed")
        stored_cell = self.repo.get_experiment_cell(cell.cell_id)
        assert stored_cell is not None
        self.assertEqual(stored_cell.status, "completed")

        # First-wins: a second terminal write cannot overwrite.
        self.assertEqual(self.repo.record_terminal(run_id, cell.cell_id, "failed", error="late"), False)
        self.assertEqual(self.repo.record_terminal(run_id, cell.cell_id, "canceled"), False)
        self.assertEqual(self.repo.record_terminal(run_id, cell.cell_id, "interrupted"), False)

        # The hardened status seam never reopens a terminal attempt.
        reopened = self.repo.update_attempt_status(run_id, "running")
        self.assertIsNotNone(reopened)
        assert reopened is not None
        self.assertEqual(reopened.status, "completed")
        self.assertEqual(reopened.error, None)

    def test_record_result_attaches_output_before_completed_terminal(self):
        cell = self.detail.cells[0]
        run_id = cell.attempt_ids[0]
        self.repo.record_running(run_id, cell.cell_id)
        output_dir = self.data_root / "experiments" / self.exp_id / "outputs" / "a" / run_id
        output_dir.mkdir(parents=True)
        (output_dir / "result.png").write_bytes(b"png-bytes")

        with mock.patch(
            "local_artifacts.get_experiments_dir",
            return_value=self.data_root / "experiments",
        ):
            self.assertTrue(self.repo.record_result(
                run_id,
                cell.cell_id,
                {
                    "output_paths": ["result.png"],
                    "_history_cell_key": "a",
                    "_history_output_required": True,
                },
            ))

        detail = self.repo.get_generation(cell.generation_id)
        assert detail is not None
        self.assertEqual([asset.type for asset in detail.assets], ["original"])
        self.assertEqual(self.repo.record_terminal(run_id, cell.cell_id, "completed"), True)
        self.assertEqual(self.repo.get_attempt(run_id).status, "completed")

    def test_record_result_rejects_required_missing_output(self):
        cell = self.detail.cells[0]
        run_id = cell.attempt_ids[0]
        self.repo.record_running(run_id, cell.cell_id)
        self.assertFalse(self.repo.record_result(
            run_id,
            cell.cell_id,
            {"_history_output_required": True},
        ))
        self.assertEqual(
            self.repo.record_terminal(
                run_id,
                cell.cell_id,
                "failed",
                error="History output finalization failed",
            ),
            True,
        )
        self.assertEqual(self.repo.get_attempt(run_id).status, "failed")

    def test_record_result_allows_legitimate_zero_output(self):
        cell = self.detail.cells[0]
        run_id = cell.attempt_ids[0]
        self.repo.record_running(run_id, cell.cell_id)
        self.assertTrue(self.repo.record_result(run_id, cell.cell_id, {}))
        self.assertEqual(self.repo.record_terminal(run_id, cell.cell_id, "completed"), True)
        detail = self.repo.get_generation(cell.generation_id)
        assert detail is not None
        self.assertEqual(detail.assets, [])

    def test_terminal_write_rejects_stale_attempt(self):
        cell = self.detail.cells[0]
        run_id = cell.attempt_ids[0]
        self.assertEqual(self.repo.record_terminal(run_id, cell.cell_id, "failed", error="boom"), True)

        # Newer retry attempt becomes the CURRENT attempt.
        retry = self.repo.create_retry_attempt(cell.cell_id)
        assert retry is not None
        new_run = retry.attempt.run_id
        self.assertEqual(self._current(cell.cell_id).run_id, new_run)

        # The stale OLD attempt can never mutate the newer one.
        self.assertEqual(self.repo.record_terminal(run_id, cell.cell_id, "completed"), False)
        self.assertEqual(self.repo.record_running(run_id, cell.cell_id), None)
        self.assertEqual(self._current(cell.cell_id).status, "queued")

        # The current (new) attempt transitions normally.
        self.assertEqual(self.repo.record_running(new_run, cell.cell_id), None)
        self.assertEqual(self.repo.record_terminal(new_run, cell.cell_id, "completed"), True)
        self.assertEqual(self._current(cell.cell_id).status, "completed")

    def test_update_attempt_terminal_rejects_unknown_status(self):
        run_id = self.detail.cells[0].attempt_ids[0]
        with self.assertRaises(ValueError):
            self.repo.update_attempt_terminal(run_id, status="running")

    # ── queued cancel ───────────────────────────────────────────────────

    def test_cancel_queued_attempt(self):
        cell = self.detail.cells[1]
        run_id = cell.attempt_ids[0]
        canceled = self.repo.cancel_queued_attempt(run_id, error="user changed mind", finished_at=T0)
        self.assertIsNotNone(canceled)
        assert canceled is not None
        self.assertEqual(canceled.status, "canceled")
        self.assertEqual(canceled.error, "user changed mind")
        self.assertEqual(canceled.finished_at, T0)
        stored_cell = self.repo.get_experiment_cell(cell.cell_id)
        assert stored_cell is not None
        self.assertEqual(stored_cell.status, "canceled")
        gdetail = self.repo.get_generation(cell.generation_id)
        assert gdetail is not None
        self.assertEqual(gdetail.generation.status, "canceled")

        # Repeated cancel of a terminal attempt is a no-op returning the stored row.
        again = self.repo.cancel_queued_attempt(run_id)
        self.assertIsNotNone(again)
        assert again is not None
        self.assertEqual(again.status, "canceled")

    def test_cancel_does_not_touch_running_or_unknown(self):
        cell = self.detail.cells[0]
        run_id = cell.attempt_ids[0]
        self._claim("a")
        running = self.repo.cancel_queued_attempt(run_id)
        self.assertIsNotNone(running)
        assert running is not None
        self.assertEqual(running.status, "running")  # untouched

        self.assertIsNone(self.repo.cancel_queued_attempt("run_missing"))

    # ── aggregate precedence ────────────────────────────────────────────

    def test_derive_experiment_status_precedence_pure(self):
        def cell(status: str) -> ExperimentCell:
            return ExperimentCell(
                cell_id="c", experiment_id="e", position=0, status=status, updated_at=T0
            )

        self.assertEqual(derive_experiment_status([cell("completed")]), "completed")
        self.assertEqual(derive_experiment_status([cell("completed"), cell("failed")]), "completed_with_failures")
        # canceled beats failed (completed_with_failures).
        self.assertEqual(derive_experiment_status([cell("canceled"), cell("failed")]), "canceled")
        # interrupted beats canceled and failed.
        self.assertEqual(
            derive_experiment_status([cell("interrupted"), cell("canceled"), cell("failed")]),
            "interrupted",
        )
        # queued/running beat everything.
        self.assertEqual(derive_experiment_status([cell("queued"), cell("interrupted")]), "running")
        self.assertEqual(derive_experiment_status([cell("running"), cell("failed")]), "running")
        # skipped is terminal non-failed: never blocks completion.
        self.assertEqual(derive_experiment_status([cell("skipped"), cell("completed")]), "completed")

    def test_aggregate_status_via_real_transitions(self):
        # Cell a: completed.  Cell b: queued → running.
        cell_a = self.detail.cells[0]
        cell_b = self.detail.cells[1]
        self.assertEqual(self.repo.record_terminal(cell_a.attempt_ids[0], "a", "completed"), True)
        self.assertEqual(self.repo.aggregate_status(), "running")  # b still queued
        self._claim("b")
        self.assertEqual(self.repo.aggregate_status(), "running")

        # Cancel cell b → no in-flight cells; canceled wins over completed-with-
        # failures only if no failed cells exist.  Both cells completed-ish:
        # a completed, b canceled → canceled.
        self.assertEqual(
            self.repo.record_terminal(self._current("b").run_id, "b", "canceled", error="skip"), True
        )
        self.assertEqual(self.repo.aggregate_status(), "canceled")

    def test_aggregate_status_failed_and_interrupted(self):
        bound = self._bound("exp_fail")
        specs = [_cell_spec("x"), _cell_spec("y")]
        self.repo.create_modern_matrix(
            experiment_id="exp_fail", name="F", definition=_definition(specs),
            cells=specs, created_at=T0,
        )
        x_run = self.repo.get_experiment_cell("x").attempt_ids[0]
        y_run = self.repo.get_experiment_cell("y").attempt_ids[0]
        # x failed, y completed → completed_with_failures.
        self.assertEqual(bound.record_terminal(x_run, "x", "failed", error="boom"), True)
        self.assertEqual(bound.record_terminal(y_run, "y", "completed"), True)
        self.assertEqual(bound.aggregate_status(), "completed_with_failures")

        # A retry re-queues x: running beats everything.
        retry = bound.create_retry_attempt("x")
        assert retry is not None
        self.assertEqual(bound.aggregate_status(), "running")

        # Interrupt the NEW retry attempt (terminal first-wins never reopens
        # the old failed attempt): interrupted beats failed + completed.
        self.assertEqual(bound.record_terminal(retry.attempt.run_id, "x", "interrupted"), True)
        self.assertEqual(bound.aggregate_status(), "interrupted")

        # Resume re-queues x: running beats interrupted.
        resume = bound.create_resume_attempt("x")
        assert resume is not None
        self.assertEqual(bound.aggregate_status(), "running")

    # ── resume / retry attempt creation ─────────────────────────────────

    def test_resume_interrupted_creates_new_attempt_same_generation(self):
        cell = self.detail.cells[0]
        gen_id = cell.generation_id
        first_run = cell.attempt_ids[0]
        self.assertEqual(self.repo.record_terminal(first_run, "a", "interrupted"), True)

        claim = self.repo.create_resume_attempt("a")
        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim.outcome, CLAIM_CLAIMED)
        self.assertNotEqual(claim.attempt.run_id, first_run)
        self.assertEqual(claim.attempt.status, "queued")
        self.assertEqual(claim.attempt.generation_id, gen_id)

        # Old interrupted attempt untouched (append-only), new one is current.
        stored = self.repo.get_experiment_cell("a")
        assert stored is not None
        self.assertEqual(stored.attempt_ids, [first_run, claim.attempt.run_id])
        self.assertEqual(self.repo.get_attempt(first_run).status, "interrupted")
        self.assertEqual(self._current("a").run_id, claim.attempt.run_id)

        # Double resume is guarded: current is now queued, not interrupted.
        self.assertIsNone(self.repo.create_resume_attempt("a"))

    def test_resume_skips_failed_and_ineligible(self):
        cell = self.detail.cells[0]
        self.assertEqual(self.repo.record_terminal(cell.attempt_ids[0], "a", "failed", error="boom"), True)
        self.assertIsNone(self.repo.create_resume_attempt("a"))
        # Queued / running / completed cells are not resume-eligible.
        self.assertIsNone(self.repo.create_resume_attempt("b"))
        claim = self._claim("b")
        assert claim is not None
        self.assertIsNone(self.repo.create_resume_attempt("b"))

    def test_retry_only_for_failed_cell(self):
        cell = self.detail.cells[0]
        # Queued cell: not retryable.
        self.assertIsNone(self.repo.create_retry_attempt("a"))
        # Failed cell: retryable with a fresh attempt identity.
        self.assertEqual(self.repo.record_terminal(cell.attempt_ids[0], "a", "failed", error="boom"), True)
        retry = self.repo.create_retry_attempt("a")
        self.assertIsNotNone(retry)
        assert retry is not None
        self.assertEqual(retry.attempt.status, "queued")
        # Now the current attempt is queued → not retryable again.
        self.assertIsNone(self.repo.create_retry_attempt("a"))

    def test_list_recoverable_cells_fixed_order(self):
        self.assertEqual(self.repo.record_terminal(self.detail.cells[0].attempt_ids[0], "a", "completed"), True)
        self.assertEqual(self.repo.record_terminal(self.detail.cells[1].attempt_ids[0], "b", "interrupted"), True)
        recoverable = self.repo.list_recoverable_cells()
        self.assertEqual([r["cell_id"] for r in recoverable], ["b"])
        self.assertEqual(recoverable[0]["status"], "interrupted")

        # Interrupted → new queued attempt becomes recoverable too.
        self.repo.create_resume_attempt("b")
        recoverable = self.repo.list_recoverable_cells()
        self.assertEqual([r["cell_id"] for r in recoverable], ["b"])
        self.assertEqual(recoverable[0]["status"], "queued")

    # ── startup recovery idempotence (modern marker only) ───────────────

    def test_startup_recovery_only_stale_running_and_idempotent(self):
        self.assertEqual(self.repo.record_terminal(self.detail.cells[1].attempt_ids[0], "b", "completed"), True)
        # Cell a is running (stale from a previous process).
        self.assertEqual(self.repo.record_running(self.detail.cells[0].attempt_ids[0], "a"), None)

        result = self._run_startup_recovery()
        self.assertEqual(result["marked_interrupted"], [self.detail.cells[0].attempt_ids[0]])
        self.assertEqual(self._current("a").status, "interrupted")
        # Queued/terminal cells unchanged: b stays completed.
        self.assertEqual(self._current("b").status, "completed")

        # Second sweep is idempotent: nothing left to mark.
        again = self._run_startup_recovery()
        self.assertEqual(again["marked_interrupted"], [])
        self.assertEqual(self._current("a").status, "interrupted")

    def test_startup_recovery_leaves_queued_unchanged(self):
        # Fresh matrix: both cells queued; no stale running attempt.
        self.assertEqual(self._run_startup_recovery()["marked_interrupted"], [])
        for cell in ("a", "b"):
            self.assertEqual(self._current(cell).status, "queued")

    def test_startup_recovery_never_touches_legacy_experiments(self):
        legacy = self.repo.create_experiment(name="legacy", cells=[{}], created_at=T0)
        gen = self.repo.create_generation(generation_id="gen_legacy")
        run = self.repo.add_attempt(
            gen.generation_id, experiment_id=legacy.experiment.experiment_id
        )
        self.repo.update_attempt_status(run.run_id, "running")

        self.assertEqual(self._run_startup_recovery()["marked_interrupted"], [])
        # The legacy running attempt is untouched.
        self.assertEqual(self.repo.get_attempt(run.run_id).status, "running")

    def _run_startup_recovery(self):
        # Sync boundary: startup_experiment_modern_lifecycle is async.
        import asyncio
        return asyncio.run(startup_experiment_modern_lifecycle(Path(self._tmp.name)))


# ── Modern routes: status / feed / detail / cancel / resume / retry ───────


class _FakePlannerCell:
    def __init__(self, cell_id: str, *, ok: bool = True, error: str | None = None):
        self.cell_id = cell_id
        self.ok = ok
        self.error = error

    def to_dict(self) -> dict:
        d = _cell_spec(self.cell_id)
        if not self.ok:
            d["error"] = self.error or "cell planning failed"
            d["error_code"] = "PLAN_INVALID"
        return d


class _FakeCellPlanBundle:
    def __init__(self, cells: list[_FakePlannerCell]):
        self.cells = cells
        self.cell_ordering = [c.cell_id for c in cells]
        self.modal_options = {}
        self.workflow_branches: list[dict] = []
        self.axis_labels = ["seed"]


class _FakePlanner:
    class ExperimentDefinitionError(Exception):
        pass

    def __init__(self, cells: list[_FakePlannerCell]):
        self._cells = cells

    def build_cell_plan(self, definition, node_dir=None):
        return _FakeCellPlanBundle(self._cells)


class _FakeModernScheduler:
    """Minimal scheduler stand-in advertising truthful remote cancel.

    Persists the ``canceled`` terminal write like the real scheduler
    (``record_terminal`` under the current attempt) so route-level cancels
    leave the durable state in the same shape the real scheduler would.
    """

    remote_cancel_available = True

    def __init__(self, repo: HistoryV2Repository | None = None):
        self.repo = repo
        self.cancelled: list[str] = []

    async def cancel_cell(self, cell_id, *, reason="user_cancel"):
        self.cancelled.append(cell_id)
        if self.repo is not None:
            current = self.repo.read_active_attempt(cell_id)
            if current is not None:
                self.repo.record_terminal(current.run_id, cell_id, "canceled", error=reason)
        return "canceled_running"


class HistoryV2ModernRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_root = Path(self._tmp.name)
        db_path = self.data_root / ".studio_history_v2" / "history_v2.db"
        self.store = HistoryV2Store(db_path)
        self.repo = HistoryV2Repository(self.store)
        self.app = web.Application()
        register_history_v2_routes(self.app.router, self.data_root)
        self.registry: dict[str, object] = {}
        register_experiment_modern_routes(
            self.app.router, self.data_root, registry=self.registry
        )
        emr._SHUTDOWN_FLAG[0] = False
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    # ── seed helpers ────────────────────────────────────────────────────

    def _matrix(self, experiment_id: str, cell_ids=("a", "b"), *, created_at=T0):
        specs = [_cell_spec(cid) for cid in cell_ids]
        return self.repo.create_modern_matrix(
            experiment_id=experiment_id,
            name=f"Matrix {experiment_id}",
            definition=_definition(specs),
            cells=specs,
            created_at=created_at,
        )

    def _claim(self, cell_id: str):
        claim = self.repo.atomically_claim_queued_attempt(cell_id)
        self.assertIsNotNone(claim)
        assert claim is not None
        return claim.attempt.run_id

    async def _post(self, url: str, body=None):
        kwargs = {"json": body} if body is not None else {}
        resp = await self.client.post(url, **kwargs)
        self.assertEqual(resp.status, 200, await resp.text())
        return await resp.json()

    # ── create (fake planner) ───────────────────────────────────────────

    async def test_create_route_accepts_modern_matrix(self):
        fake = _FakePlanner([_FakePlannerCell("a"), _FakePlannerCell("b")])
        with mock.patch.object(emr, "_load_planner", return_value=fake):
            data = await self._post(
                "/comfymodal/history-v2/experiments",
                {
                    "experiment_id": "exp_route",
                    "name": "Route Matrix",
                    "definition": {"workflows": {"wf_a": {}}, "axis": "seed"},
                },
            )
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["experiment_id"], "exp_route")
        self.assertFalse(data["started"])  # no scheduler registered → durable queued
        self.assertEqual(data["aggregate_status"], "running")
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["counts"]["queued"], 2)

        detail = self.repo.get_experiment("exp_route")
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual([c.cell_id for c in detail.cells], ["a", "b"])
        # Planning-invalid cell gets a terminal failed first attempt.
        gdetail = self.repo.get_generation(detail.cells[0].generation_id)
        assert gdetail is not None
        self.assertEqual(gdetail.attempts[0].status, "queued")

    async def test_create_route_rejects_duplicate_experiment(self):
        self._matrix("exp_dup")
        fake = _FakePlanner([_FakePlannerCell("a")])
        with mock.patch.object(emr, "_load_planner", return_value=fake):
            resp = await self.client.post(
                "/comfymodal/studio/experiment-v2",
                json={
                    "experiment_id": "exp_dup",
                    "definition": {"workflows": {"wf_a": {}}, "axis": "seed"},
                },
            )
        self.assertEqual(resp.status, 409)
        self.assertEqual((await resp.json())["code"], "EXPERIMENT_EXISTS")

    # ── status ──────────────────────────────────────────────────────────

    async def test_status_projection_counts_and_cells(self):
        self._matrix("exp_status")
        run = self._claim("a")
        self.repo.record_terminal(run, "a", "completed")

        data = await self._post(
            f"/comfymodal/history-v2/experiments/exp_status/start"
        )
        self.assertEqual(data["aggregate_status"], "running")  # b still queued

        resp = await self.client.get(
            f"/comfymodal/history-v2/experiments/exp_status/status"
        )
        self.assertEqual(resp.status, 200)
        status = await resp.json()
        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["experiment_id"], "exp_status")
        self.assertEqual(status["aggregate_status"], "running")
        self.assertEqual(status["total"], 2)
        self.assertEqual(status["counts"], {"queued": 1, "running": 0, "completed": 1,
                                            "failed": 0, "canceled": 0, "interrupted": 0})
        # Fixed order + identity in the cell records.
        self.assertEqual([c["cell_id"] for c in status["cells"]], ["a", "b"])
        self.assertEqual(status["cells"][0]["status"], "completed")
        self.assertEqual(status["cells"][1]["status"], "queued")
        self.assertEqual(status["cells"][1]["active_attempt_id"],
                         self.repo.get_experiment_cell("b").attempt_ids[0])
        self.assertEqual(status["cells"][1]["generation_id"],
                         self.repo.get_experiment_cell("b").generation_id)
        self.assertEqual(status["cells"][1]["workflow_id"], "wf_b")
        # The heavy immutable request is never part of the polling payload.
        self.assertNotIn("request", status["cells"][0])
        self.assertNotIn("execution_plan", status["cells"][0])

    async def test_status_404_for_unknown_experiment(self):
        resp = await self.client.get(
            f"/comfymodal/history-v2/experiments/exp_missing/status"
        )
        self.assertEqual(resp.status, 404)
        self.assertEqual((await resp.json())["code"], "EXPERIMENT_NOT_FOUND")

    # ── feed / detail one card ──────────────────────────────────────────

    async def test_feed_shows_modern_experiment_card(self):
        self._matrix("exp_feed", cell_ids=("a", "b", "c"))
        resp = await self.client.get(
            f"/comfymodal/history-v2/feed?kind=experiment&order=newest"
        )
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["total"], 1)
        item = data["items"][0]
        self.assertEqual(item["kind"], "experiment")
        self.assertEqual(item["id"], "exp_feed")
        self.assertEqual(item["status"], "running")
        self.assertEqual(item["true_cell_count"], 3)
        self.assertEqual(item["result_count"], 0)
        self.assertEqual(item["failed_count"], 0)
        self.assertEqual(len(item["cells"]), 3)

    async def test_experiment_detail_one_card(self):
        self._matrix("exp_detail")
        run = self._claim("a")
        self.repo.record_terminal(run, "a", "completed")
        self.repo.attach_asset(
            self.repo.get_experiment_cell("a").generation_id,
            run_id=run,
            asset_type="original",
            data=b"\x89PNG\r\n\x1a\nfakepngbytes",
            filename="out.png",
            fmt="png",
        )

        resp = await self.client.get(
            f"/comfymodal/history-v2/experiments/exp_detail"
        )
        self.assertEqual(resp.status, 200)
        item = (await resp.json())["item"]
        self.assertEqual(item["id"], "exp_detail")
        self.assertEqual(item["status"], "running")
        cells = item["cells"]
        self.assertEqual([c["key"] for c in cells], ["a", "b"])
        self.assertEqual(cells[0]["status"], "completed")
        self.assertEqual(cells[1]["status"], "queued")

        # One card: the generation payload is embedded per cell.
        gen_a = cells[0]["generation"]
        self.assertIsNotNone(gen_a)
        self.assertEqual(gen_a["id"], self.repo.get_experiment_cell("a").generation_id)
        self.assertEqual(gen_a["status"], "completed")
        self.assertEqual(len(gen_a["attempts"]), 1)
        self.assertEqual(gen_a["attempts"][0]["run_id"], run)
        self.assertIsNotNone(gen_a["request_snapshot"])
        self.assertEqual(len(gen_a["outputs"]), 1)
        self.assertEqual(gen_a["outputs"][0]["status"], "success")
        # Cell axis values from the frozen plan.
        self.assertEqual(cells[0]["axis"], {"x": "1", "y": ""})

    # ── cancel ──────────────────────────────────────────────────────────

    async def test_cancel_queued_cells_durably(self):
        self._matrix("exp_cancel")
        data = await self._post(
            f"/comfymodal/history-v2/experiments/exp_cancel/cancel"
        )
        self.assertEqual(data["aggregate_status"], "canceled")
        self.assertEqual(data["counts"]["canceled"], 2)
        for cell in ("a", "b"):
            current = self.repo.read_active_attempt(cell)
            assert current is not None
            self.assertEqual(current.status, "canceled")

        # Repeated cancel is idempotent.
        resp = await self.client.post(
            f"/comfymodal/history-v2/experiments/exp_cancel/cancel"
        )
        self.assertEqual(resp.status, 200)
        self.assertEqual((await resp.json())["message"], "experiment is already canceled")

    async def test_cancel_running_requires_truthful_scheduler(self):
        self._matrix("exp_running")
        self._claim("a")

        # No scheduler → truthful 503, running cell stays durable.
        resp = await self.client.post(
            f"/comfymodal/history-v2/experiments/exp_running/cancel"
        )
        self.assertEqual(resp.status, 503)
        self.assertEqual((await resp.json())["code"], "CANCELLATION_UNAVAILABLE")
        self.assertEqual(self.repo.read_active_attempt("a").status, "running")

        # With a truthful scheduler registered → canceled via remote cancel.
        sched = _FakeModernScheduler(repo=self.repo)
        self.registry["exp_running"] = sched
        data = await self._post(
            f"/comfymodal/history-v2/experiments/exp_running/cancel"
        )
        self.assertEqual(sched.cancelled, ["a"])
        self.assertEqual(data["counts"]["canceled"], 2)
        self.assertEqual(self.repo.read_active_attempt("a").status, "canceled")

    async def test_cancel_terminal_experiment_rejected(self):
        self._matrix("exp_terminal")
        for cell in ("a", "b"):
            run = self._claim(cell)
            self.repo.record_terminal(run, cell, "completed")
        resp = await self.client.post(
            f"/comfymodal/history-v2/experiments/exp_terminal/cancel"
        )
        self.assertEqual(resp.status, 409)
        self.assertEqual((await resp.json())["code"], "EXPERIMENT_TERMINAL")

    # ── resume ──────────────────────────────────────────────────────────

    async def test_resume_creates_attempt_for_interrupted_cell(self):
        self._matrix("exp_resume")
        run_a = self._claim("a")
        self.repo.record_terminal(run_a, "a", "interrupted")
        gen_before = self.repo.get_experiment_cell("a").generation_id
        attempts_before = len(self.repo.get_attempts_for_cells(["a"]))

        data = await self._post(
            f"/comfymodal/history-v2/experiments/exp_resume/resume"
        )
        self.assertEqual(data["resumed"], 1)
        self.assertEqual(len(data["created_attempts"]), 1)
        self.assertEqual(data["created_attempts"][0]["cell_id"], "a")
        self.assertEqual(data["resumable_cells"], ["a", "b"])

        # New queued attempt under the SAME generation (immutable snapshot).
        attempts = self.repo.get_attempts_for_cells(["a"])
        self.assertEqual(len(attempts), attempts_before + 1)
        self.assertEqual(attempts[-1].status, "queued")
        self.assertEqual(attempts[-1].generation_id, gen_before)
        self.assertEqual(self.repo.get_experiment_cell("a").status, "queued")

        # Double resume: the interrupted cell is now queued → no new attempts.
        again = await self._post(
            f"/comfymodal/history-v2/experiments/exp_resume/resume"
        )
        self.assertEqual(again["resumed"], 0)
        self.assertEqual(again["created_attempts"], [])
        self.assertEqual(len(self.repo.get_attempts_for_cells(["a"])), attempts_before + 1)

    async def test_resume_409_when_nothing_resumable(self):
        self._matrix("exp_none")
        for cell in ("a", "b"):
            run = self._claim(cell)
            self.repo.record_terminal(run, cell, "completed")
        resp = await self.client.post(
            f"/comfymodal/history-v2/experiments/exp_none/resume"
        )
        self.assertEqual(resp.status, 409)
        self.assertEqual((await resp.json())["code"], "NO_RESUMABLE_CELLS")

    # ── retry ───────────────────────────────────────────────────────────

    async def test_retry_failed_cell_reuses_generation(self):
        self._matrix("exp_retry")
        run_a = self._claim("a")
        self.repo.record_terminal(run_a, "a", "failed", error="boom")
        gen_before = self.repo.get_experiment_cell("a").generation_id

        data = await self._post(
            f"/comfymodal/history-v2/experiments/exp_retry/cells/a/retry"
        )
        self.assertTrue(data["retried"])
        new_run = data["run_id"]
        self.assertIsNotNone(new_run)
        self.assertNotEqual(new_run, run_a)
        attempts = self.repo.get_attempts_for_cells(["a"])
        self.assertEqual([a.run_id for a in attempts], [run_a, new_run])
        self.assertEqual(attempts[-1].generation_id, gen_before)
        self.assertEqual(self.repo.get_experiment_cell("a").status, "queued")

        # Retrying again while the cell is queued → 409.
        resp = await self.client.post(
            f"/comfymodal/history-v2/experiments/exp_retry/cells/a/retry"
        )
        self.assertEqual(resp.status, 409)
        self.assertEqual((await resp.json())["code"], "CELL_NOT_FAILED")

    async def test_retry_404_for_wrong_cell(self):
        self._matrix("exp_retry404")
        resp = await self.client.post(
            f"/comfymodal/history-v2/experiments/exp_retry404/cells/z/retry"
        )
        self.assertEqual(resp.status, 404)
        self.assertEqual((await resp.json())["code"], "CELL_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
