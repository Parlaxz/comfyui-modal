"""Tests for the History V2 repository (history_v2_repository.py).

Runs against a temp SQLite database via HistoryV2Store/HistoryV2Repository.
"""
from __future__ import annotations

import base64
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from history_v2_repository import HistoryV2Repository
from history_v2_store import HistoryV2Store


def _png_bytes() -> bytes:
    """Tiny valid 1x1 PNG (byte identity is what matters in tests)."""
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )


class HistoryV2RepositoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "history_v2.db"
        self.store = HistoryV2Store(self.db_path)
        self.repo = HistoryV2Repository(self.store)

    # ── Generations / attempts ──────────────────────────────────────────

    def test_generation_creation(self):
        gen = self.repo.create_generation(
            prompt_text="a cat",
            negative_prompt_text="blur",
            model_stack=[{"type": "checkpoint", "name": "sd15"}],
        )
        self.assertTrue(gen.generation_id.startswith("gen_"))
        self.assertEqual(gen.status, "pending")
        detail = self.repo.get_generation(gen.generation_id)
        assert detail is not None
        self.assertEqual(detail.generation.prompt_text, "a cat")
        self.assertEqual(detail.generation.negative_prompt_text, "blur")
        self.assertEqual(detail.generation.model_stack, [{"type": "checkpoint", "name": "sd15"}])
        self.assertEqual(detail.attempts, [])
        self.assertEqual(detail.assets, [])

    def test_preview_then_original_attempt(self):
        gen = self.repo.create_generation()
        preview = self.repo.add_attempt(gen.generation_id, mode="preview")
        self.assertEqual(preview.status, "queued")
        self.repo.update_attempt_terminal(preview.run_id, status="completed")
        detail = self.repo.get_generation(gen.generation_id)
        assert detail is not None
        self.assertEqual(detail.generation.status, "completed")
        self.assertEqual(len(detail.attempts), 1)

        original = self.repo.add_attempt(gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(original.run_id, status="completed")
        detail = self.repo.get_generation(gen.generation_id)
        assert detail is not None
        self.assertEqual(len(detail.attempts), 2)
        self.assertEqual([a.mode for a in detail.attempts], ["preview", "original"])
        self.assertEqual(detail.generation.status, "completed")

    def test_failed_original_after_successful_preview(self):
        gen = self.repo.create_generation()
        preview = self.repo.add_attempt(gen.generation_id, mode="preview")
        self.repo.update_attempt_terminal(preview.run_id, status="completed")
        self.repo.attach_asset(
            gen.generation_id, run_id=preview.run_id, asset_type="preview",
            data=_png_bytes(), filename="thumb.png", fmt="png",
        )
        original = self.repo.add_attempt(gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(original.run_id, status="failed", error="CUDA OOM")

        detail = self.repo.get_generation(gen.generation_id)
        assert detail is not None
        # Generation stays 'completed' because the preview succeeded...
        self.assertEqual(detail.generation.status, "completed")
        # ...but the failed attempt remains visible with its error.
        failed = [a for a in detail.attempts if a.status == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].error, "CUDA OOM")
        # Preview asset still present.
        self.assertTrue(any(a.type == "preview" for a in detail.assets))

    def test_preview_success_original_failure(self):
        gen = self.repo.create_generation()
        preview = self.repo.add_attempt(gen.generation_id, mode="preview")
        self.repo.update_attempt_terminal(preview.run_id, status="completed")
        self.repo.attach_asset(
            gen.generation_id, run_id=preview.run_id, asset_type="preview",
            data=_png_bytes(), filename="thumb.png", fmt="png",
        )
        original = self.repo.add_attempt(gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(original.run_id, status="failed", error="sampler crashed")

        detail = self.repo.get_generation(gen.generation_id)
        assert detail is not None
        # Generation remains usable ('completed') because the preview succeeded.
        self.assertEqual(detail.generation.status, "completed")
        # The preview asset is retained.
        self.assertTrue(any(a.type == "preview" for a in detail.assets))
        # The failed original attempt is retained, with its error intact.
        failed = [a for a in detail.attempts if a.status == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].mode, "original")
        self.assertEqual(failed[0].error, "sampler crashed")

    def test_preview_success_original_failure_then_original_retry_success(self):
        gen = self.repo.create_generation()
        preview = self.repo.add_attempt(gen.generation_id, mode="preview")
        self.repo.update_attempt_terminal(preview.run_id, status="completed")
        self.repo.attach_asset(
            gen.generation_id, run_id=preview.run_id, asset_type="preview",
            data=_png_bytes(), filename="thumb.png", fmt="png",
        )
        failed_original = self.repo.add_attempt(gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(
            failed_original.run_id, status="failed", error="sampler crashed"
        )
        retry = self.repo.add_attempt(gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(retry.run_id, status="completed")
        self.repo.attach_asset(
            gen.generation_id, run_id=retry.run_id, asset_type="original",
            data=_png_bytes(), filename="out.png", fmt="png",
        )

        detail = self.repo.get_generation(gen.generation_id)
        assert detail is not None
        self.assertEqual(detail.generation.status, "completed")
        # Both preview and original assets are present.
        asset_types = sorted(a.type for a in detail.assets)
        self.assertEqual(asset_types, ["original", "preview"])
        # ALL three attempts are retained: preview, failed original, retry.
        self.assertEqual(len(detail.attempts), 3)
        self.assertEqual([a.mode for a in detail.attempts], ["preview", "original", "original"])
        failed = [a for a in detail.attempts if a.status == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].error, "sampler crashed")

    def test_multiple_original_retries(self):
        gen = self.repo.create_generation()
        attempts = []
        for _ in range(3):
            attempts.append(self.repo.add_attempt(gen.generation_id, mode="original"))
        self.repo.update_attempt_terminal(attempts[0].run_id, status="failed", error="boom 1")
        self.repo.update_attempt_terminal(attempts[1].run_id, status="failed", error="boom 2")
        self.repo.update_attempt_terminal(attempts[2].run_id, status="completed")

        detail = self.repo.get_generation(gen.generation_id)
        assert detail is not None
        self.assertEqual(detail.generation.status, "completed")
        self.assertEqual(len(detail.attempts), 3)
        statuses = sorted(a.status for a in detail.attempts)
        self.assertEqual(statuses, ["completed", "failed", "failed"])

    def test_multi_output_run(self):
        gen = self.repo.create_generation()
        attempt = self.repo.add_attempt(gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(attempt.run_id, status="completed")
        for asset_type in ("preview", "original", "secondary"):
            self.repo.attach_asset(
                gen.generation_id, run_id=attempt.run_id, asset_type=asset_type,
                data=b"x", filename=f"{asset_type}.png", fmt="png",
            )
        assets = self.repo.get_generation_assets(gen.generation_id)
        self.assertEqual(len(assets), 3)
        self.assertEqual(sorted(a.type for a in assets), ["original", "preview", "secondary"])

    def test_featured_asset_change(self):
        gen = self.repo.create_generation()
        a1 = self.repo.attach_asset(gen.generation_id, asset_type="preview",
                                    data=b"a", filename="a.png", fmt="png")
        a2 = self.repo.attach_asset(gen.generation_id, asset_type="original",
                                    data=b"b", filename="b.png", fmt="png")
        self.assertIs(self.repo.set_featured_asset(gen.generation_id, a1.asset_id), True)
        self.assertIs(self.repo.set_featured_asset(gen.generation_id, a2.asset_id), True)
        detail = self.repo.get_generation(gen.generation_id)
        assert detail is not None
        self.assertEqual(detail.generation.featured_asset_id, a2.asset_id)
        self.assertEqual(len(detail.assets), 2)
        # An asset from a different generation must be rejected.
        other = self.repo.create_generation()
        foreign = self.repo.attach_asset(other.generation_id, asset_type="preview",
                                         data=b"c", filename="c.png", fmt="png")
        self.assertIs(self.repo.set_featured_asset(gen.generation_id, foreign.asset_id), False)

    def test_note_and_favorite_persistence(self):
        gen = self.repo.create_generation()
        self.assertIs(self.repo.set_note(gen.generation_id, "hello note"), True)
        self.assertIs(self.repo.set_favorite(gen.generation_id, True), True)
        with self.assertRaises(ValueError):
            self.repo.set_note(gen.generation_id, "x" * 2001)
        # A NEW repository on the same db file sees the values.
        repo2 = HistoryV2Repository(HistoryV2Store(self.db_path))
        detail = repo2.get_generation(gen.generation_id)
        self.assertEqual(detail.generation.note, "hello note")
        self.assertIs(detail.generation.favorite, True)

    # ── Experiments ─────────────────────────────────────────────────────

    def test_experiment_with_fixed_cells(self):
        detail = self.repo.create_experiment(
            name="grid",
            cells=[
                {"axis_labels": {"seed": 1}},
                {"axis_labels": {"seed": 2}},
                {"axis_labels": {"seed": 3}},
            ],
        )
        self.assertEqual(detail.experiment.expected_cell_count, 3)
        self.assertEqual([c.position for c in detail.cells], [0, 1, 2])
        self.assertEqual(detail.experiment.cell_ordering, [c.cell_id for c in detail.cells])
        loaded = self.repo.get_experiment(detail.experiment.experiment_id)
        assert loaded is not None
        self.assertEqual([c.cell_id for c in loaded.cells], [c.cell_id for c in detail.cells])
        self.assertEqual(loaded.cells[1].axis_labels, {"seed": 2})

    def test_failed_experiment_cell(self):
        detail = self.repo.create_experiment(cells=[{}, {}])
        exp_id = detail.experiment.experiment_id
        cell = detail.cells[0]
        gen = self.repo.create_generation(experiment_id=exp_id)
        attempt = self.repo.add_attempt(
            gen.generation_id, mode="original", experiment_id=exp_id, cell_id=cell.cell_id
        )
        self.repo.update_attempt_terminal(attempt.run_id, status="failed", error="cell failed")

        loaded = self.repo.get_experiment(exp_id)
        assert loaded is not None
        updated_cell = next(c for c in loaded.cells if c.cell_id == cell.cell_id)
        self.assertEqual(updated_cell.status, "failed")
        self.assertEqual(updated_cell.error, "cell failed")
        self.assertIn(attempt.run_id, updated_cell.attempt_ids)
        self.assertNotEqual(loaded.experiment.status, "completed")

    def test_interrupted_experiment(self):
        detail = self.repo.create_experiment(cells=[{}])
        exp_id = detail.experiment.experiment_id
        cell = detail.cells[0]
        gen = self.repo.create_generation(experiment_id=exp_id)
        attempt = self.repo.add_attempt(
            gen.generation_id, mode="original", experiment_id=exp_id, cell_id=cell.cell_id
        )
        self.repo.update_attempt_terminal(attempt.run_id, status="interrupted")

        loaded = self.repo.get_experiment(exp_id)
        assert loaded is not None
        updated_cell = next(c for c in loaded.cells if c.cell_id == cell.cell_id)
        self.assertEqual(updated_cell.status, "interrupted")
        self.assertIn(attempt.run_id, updated_cell.attempt_ids)
        self.assertNotEqual(loaded.experiment.status, "completed")

    def test_all_cells_completed_auto_completes_experiment(self):
        detail = self.repo.create_experiment(cells=[{}, {}, {}])
        exp_id = detail.experiment.experiment_id
        for cell in detail.cells:
            gen = self.repo.create_generation(experiment_id=exp_id)
            attempt = self.repo.add_attempt(
                gen.generation_id, mode="original", experiment_id=exp_id, cell_id=cell.cell_id
            )
            self.repo.update_attempt_terminal(attempt.run_id, status="completed")
        loaded = self.repo.get_experiment(exp_id)
        assert loaded is not None
        self.assertEqual(loaded.experiment.status, "completed")

    # ── Experiment aggregate status (derive_experiment_status) ──────────

    def _complete_cell(self, exp_id: str, cell_id: str) -> None:
        gen = self.repo.create_generation(experiment_id=exp_id)
        attempt = self.repo.add_attempt(
            gen.generation_id, mode="original", experiment_id=exp_id, cell_id=cell_id
        )
        self.repo.update_attempt_terminal(attempt.run_id, status="completed")

    def _fail_cell(self, exp_id: str, cell_id: str, error: str = "cell boom") -> None:
        gen = self.repo.create_generation(experiment_id=exp_id)
        attempt = self.repo.add_attempt(
            gen.generation_id, mode="original", experiment_id=exp_id, cell_id=cell_id
        )
        self.repo.update_attempt_terminal(attempt.run_id, status="failed", error=error)

    def _interrupt_cell(self, exp_id: str, cell_id: str) -> None:
        gen = self.repo.create_generation(experiment_id=exp_id)
        attempt = self.repo.add_attempt(
            gen.generation_id, mode="original", experiment_id=exp_id, cell_id=cell_id
        )
        self.repo.update_attempt_terminal(attempt.run_id, status="interrupted")

    def test_cell_failure_then_retry_success(self):
        detail = self.repo.create_experiment(cells=[{}])
        exp_id = detail.experiment.experiment_id
        cell = detail.cells[0]

        gen1 = self.repo.create_generation(experiment_id=exp_id)
        attempt1 = self.repo.add_attempt(
            gen1.generation_id, mode="original", experiment_id=exp_id, cell_id=cell.cell_id
        )
        self.repo.update_attempt_terminal(attempt1.run_id, status="failed", error="CUDA OOM")

        gen2 = self.repo.create_generation(experiment_id=exp_id)
        attempt2 = self.repo.add_attempt(
            gen2.generation_id, mode="original", experiment_id=exp_id, cell_id=cell.cell_id
        )
        self.repo.update_attempt_terminal(attempt2.run_id, status="completed")

        loaded = self.repo.get_experiment(exp_id)
        assert loaded is not None
        updated_cell = next(c for c in loaded.cells if c.cell_id == cell.cell_id)
        self.assertEqual(updated_cell.status, "completed")
        # Latest effective outcome is success -> cell error cleared.
        self.assertIsNone(updated_cell.error)
        # Both attempts retained; the failed attempt keeps its own error.
        self.assertEqual(sorted(updated_cell.attempt_ids),
                         sorted([attempt1.run_id, attempt2.run_id]))
        gen1_detail = self.repo.get_generation(gen1.generation_id)
        assert gen1_detail is not None
        self.assertEqual(gen1_detail.attempts[0].error, "CUDA OOM")
        self.assertEqual(gen1_detail.attempts[0].status, "failed")

    def test_cell_failure_then_retry_failure(self):
        detail = self.repo.create_experiment(cells=[{}])
        exp_id = detail.experiment.experiment_id
        cell = detail.cells[0]

        gen1 = self.repo.create_generation(experiment_id=exp_id)
        attempt1 = self.repo.add_attempt(
            gen1.generation_id, mode="original", experiment_id=exp_id, cell_id=cell.cell_id
        )
        self.repo.update_attempt_terminal(attempt1.run_id, status="failed", error="err A")

        gen2 = self.repo.create_generation(experiment_id=exp_id)
        attempt2 = self.repo.add_attempt(
            gen2.generation_id, mode="original", experiment_id=exp_id, cell_id=cell.cell_id
        )
        self.repo.update_attempt_terminal(attempt2.run_id, status="failed", error="err B")

        loaded = self.repo.get_experiment(exp_id)
        assert loaded is not None
        updated_cell = next(c for c in loaded.cells if c.cell_id == cell.cell_id)
        self.assertEqual(updated_cell.status, "failed")
        # Latest failure error is current on the cell.
        self.assertEqual(updated_cell.error, "err B")
        # Both attempts retained, each with its own error.
        self.assertEqual(sorted(updated_cell.attempt_ids),
                         sorted([attempt1.run_id, attempt2.run_id]))
        for gen_id, expected_error in ((gen1.generation_id, "err A"),
                                       (gen2.generation_id, "err B")):
            d = self.repo.get_generation(gen_id)
            assert d is not None
            self.assertEqual(d.attempts[0].error, expected_error)

    def test_experiment_all_success_completed(self):
        detail = self.repo.create_experiment(cells=[{}, {}, {}])
        exp_id = detail.experiment.experiment_id
        for cell in detail.cells:
            self._complete_cell(exp_id, cell.cell_id)
        loaded = self.repo.get_experiment(exp_id)
        assert loaded is not None
        self.assertEqual(loaded.experiment.status, "completed")

    def test_experiment_terminal_with_failed_cell(self):
        detail = self.repo.create_experiment(cells=[{}, {}])
        exp_id = detail.experiment.experiment_id
        self._complete_cell(exp_id, detail.cells[0].cell_id)
        self._fail_cell(exp_id, detail.cells[1].cell_id, error="cell boom")
        loaded = self.repo.get_experiment(exp_id)
        assert loaded is not None
        # Nothing unfinished, but a cell failed -> aggregate reflects it.
        self.assertEqual(loaded.experiment.status, "completed_with_failures")

    def test_experiment_interrupted_unfinished_cells(self):
        detail = self.repo.create_experiment(cells=[{}, {}])
        exp_id = detail.experiment.experiment_id
        self._complete_cell(exp_id, detail.cells[0].cell_id)
        self._interrupt_cell(exp_id, detail.cells[1].cell_id)
        loaded = self.repo.get_experiment(exp_id)
        assert loaded is not None
        self.assertEqual(loaded.experiment.status, "interrupted")

    def test_experiment_resume_from_interrupted_to_completed_with_failures(self):
        detail = self.repo.create_experiment(cells=[{}, {}, {}])
        exp_id = detail.experiment.experiment_id
        cell_a, cell_b, cell_c = detail.cells
        self._complete_cell(exp_id, cell_a.cell_id)
        self._fail_cell(exp_id, cell_b.cell_id, error="err B")
        self._interrupt_cell(exp_id, cell_c.cell_id)

        loaded = self.repo.get_experiment(exp_id)
        assert loaded is not None
        self.assertEqual(loaded.experiment.status, "interrupted")

        # Resume cell C with a fresh attempt that succeeds.
        self._complete_cell(exp_id, cell_c.cell_id)

        loaded = self.repo.get_experiment(exp_id)
        assert loaded is not None
        self.assertEqual(loaded.experiment.status, "completed_with_failures")
        # Cell B's failed attempt history stays intact.
        cell_b_loaded = next(c for c in loaded.cells if c.cell_id == cell_b.cell_id)
        self.assertEqual(cell_b_loaded.status, "failed")
        self.assertEqual(cell_b_loaded.error, "err B")

    # ── Queries / pagination ────────────────────────────────────────────

    def test_search_and_pagination(self):
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        created: list[str] = []
        for i in range(25):
            ts = (base + timedelta(minutes=i)).isoformat(timespec="milliseconds")
            gen = self.repo.create_generation(prompt_text=f"prompt number {i}", created_at=ts)
            attempt = self.repo.add_attempt(gen.generation_id, started_at=ts)
            status = "completed" if i % 2 == 0 else "failed"
            self.repo.update_attempt_terminal(attempt.run_id, status=status)
            if i % 3 == 0:
                self.repo.attach_asset(gen.generation_id, asset_type="preview",
                                       data=b"p", filename="p.png", fmt="png")
            created.append(gen.generation_id)

        # Total over no filters.
        page = self.repo.query_generations(limit=10)
        self.assertEqual(page["total"], 25)
        self.assertEqual(len(page["items"]), 10)

        # Newest walk: 25 unique ids, newest first.
        ids, cursor = [], None
        while True:
            page = self.repo.query_generations(limit=10, cursor=cursor, order="newest")
            ids.extend(item["generation_id"] for item in page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(len(ids), 25)
        self.assertEqual(len(set(ids)), 25)
        self.assertEqual(ids[0], created[24])
        self.assertEqual(ids[-1], created[0])

        # Oldest walk: oldest first.
        ids, cursor = [], None
        while True:
            page = self.repo.query_generations(limit=10, cursor=cursor, order="oldest")
            ids.extend(item["generation_id"] for item in page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(ids[0], created[0])
        self.assertEqual(ids[-1], created[24])

        # Search matches exactly the prompt containing "prompt number 7".
        page = self.repo.query_generations(search="prompt number 7", limit=200)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["items"][0]["generation_id"], created[7])

        # Status filter (i even -> completed: 13 of 25).
        page = self.repo.query_generations(status="completed", limit=200)
        self.assertEqual(page["total"], 13)
        self.assertEqual(len(page["items"]), 13)

        # statuses (IN ...) filter.
        page = self.repo.query_generations(statuses=["failed"], limit=200)
        self.assertEqual(len(page["items"]), 12)

        # Favorite filter.
        self.repo.set_favorite(created[5], True)
        page = self.repo.query_generations(favorite=True, limit=200)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["items"][0]["generation_id"], created[5])

        # Date range (inclusive): i in [5, 10].
        ts_from = (base + timedelta(minutes=5)).isoformat(timespec="milliseconds")
        ts_to = (base + timedelta(minutes=10)).isoformat(timespec="milliseconds")
        page = self.repo.query_generations(date_from=ts_from, date_to=ts_to, limit=200)
        got = {item["generation_id"] for item in page["items"]}
        expected = {created[i] for i in range(25) if 5 <= i <= 10}
        self.assertEqual(got, expected)

        # preview_only: i % 3 == 0 -> 9 generations with a preview and no original.
        page = self.repo.query_generations(preview_only=True, limit=200)
        self.assertEqual(len(page["items"]), 9)

        # has_preview same set; has_original empty (no original assets exist).
        page = self.repo.query_generations(has_preview=True, limit=200)
        self.assertEqual(len(page["items"]), 9)
        page = self.repo.query_generations(has_original=True, limit=200)
        self.assertEqual(len(page["items"]), 0)

        # interrupted / failed_or_canceled derive from run_attempts.
        page = self.repo.query_generations(interrupted=True, limit=200)
        self.assertEqual(len(page["items"]), 0)
        page = self.repo.query_generations(failed_or_canceled=True, limit=200)
        self.assertEqual(len(page["items"]), 12)

        # model_name best-effort containment over model_stack_json.
        self.repo.create_generation(model_stack=[{"type": "checkpoint", "name": "sd_xl"}])
        page = self.repo.query_generations(model_name="sd_xl", limit=200)
        self.assertEqual(len(page["items"]), 1)

        # Invalid inputs.
        with self.assertRaises(ValueError):
            self.repo.query_generations(limit=0)
        with self.assertRaises(ValueError):
            self.repo.query_generations(limit=201)
        with self.assertRaises(ValueError):
            self.repo.query_generations(cursor="not-a-cursor")

    def test_search_matches_workflow_display_name_from_snapshot(self):
        # C15 regression: a generation whose workflow DISPLAY name ("Smoke
        # Test Workflow") differs from its workflow_id and lives only in the
        # linked request snapshot.  Search + canonical completed must find it.
        def _c15_gen(workflow_json, preset_snapshot=None):
            gen = self.repo.create_generation(workflow_id="wf_smoke_test_id")
            attempt = self.repo.add_attempt(gen.generation_id)
            self.repo.update_attempt_terminal(attempt.run_id, status="completed")
            self.repo.create_request_snapshot(
                generation_id=gen.generation_id,
                workflow_json=workflow_json,
                preset_snapshot=preset_snapshot,
            )
            return gen

        # Every representation surfaced by history_v2_routes._workflow_name.
        for workflow_json in (
            {"name": "Smoke Test Workflow"},
            {"title": "Smoke Test Workflow"},
            {"extra": {"workflow": {"name": "Smoke Test Workflow"}}},
            {"extra": {"workflow": {"title": "Smoke Test Workflow"}}},
        ):
            gen = _c15_gen(workflow_json)
            page = self.repo.query_generations(
                search="Smoke Test Workflow", statuses=["completed"], limit=200
            )
            ids = {item["generation_id"] for item in page["items"]}
            self.assertIn(gen.generation_id, ids, workflow_json)

        # Preset-snapshot workflow_name fallback (workflow_json has no name).
        gen_fallback = _c15_gen({}, preset_snapshot={"workflow_name": "Smoke Test Workflow"})
        page = self.repo.query_generations(
            search="Smoke Test Workflow", statuses=["completed"], limit=200
        )
        self.assertEqual(page["total"], 5)
        ids = {item["generation_id"] for item in page["items"]}
        self.assertIn(gen_fallback.generation_id, ids)

        # The raw workflow_id still matches through the existing search field.
        page = self.repo.query_generations(search="wf_smoke_test_id", limit=200)
        self.assertEqual(page["total"], 5)

        # A search matching neither id nor display name matches nothing.
        page = self.repo.query_generations(search="no such workflow", limit=200)
        self.assertEqual(page["total"], 0)

        # LIKE wildcards in the search term stay escaped for the new fields.
        page = self.repo.query_generations(search="Smoke%Test Workflow", limit=200)
        self.assertEqual(page["total"], 0)

    def test_duplicate_filenames_do_not_collide(self):
        gen = self.repo.create_generation()
        dir_one = Path(self._tmp.name) / "one"
        dir_two = Path(self._tmp.name) / "two"
        dir_one.mkdir()
        dir_two.mkdir()
        file_one = dir_one / "same.png"
        file_two = dir_two / "same.png"
        file_one.write_bytes(b"data-one")
        file_two.write_bytes(b"data-two")

        a1 = self.repo.attach_asset(gen.generation_id, source_path=str(file_one),
                                    asset_type="original", copy=True)
        a2 = self.repo.attach_asset(gen.generation_id, source_path=str(file_two),
                                    asset_type="original", copy=True)
        self.assertNotEqual(a1.asset_id, a2.asset_id)
        self.assertNotEqual(a1.managed_path, a2.managed_path)
        self.assertEqual(Path(a1.managed_path).read_bytes(), b"data-one")
        self.assertEqual(Path(a2.managed_path).read_bytes(), b"data-two")
        self.assertTrue(Path(a1.managed_path).is_file())
        self.assertTrue(Path(a2.managed_path).is_file())


if __name__ == "__main__":
    unittest.main()
