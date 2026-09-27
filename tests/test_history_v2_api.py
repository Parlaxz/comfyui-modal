"""HTTP API tests for the History V2 routes (history_v2_routes.py).

Runs a real aiohttp test server against a temp-dir database, exercising the
exact contract consumed by the History V2 frontend.
"""
from __future__ import annotations

import base64
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from history_v2_repository import HistoryV2Repository
from history_v2_routes import register_history_v2_routes
from history_v2_store import HistoryV2Store
from history_v2_writer import (
    _gen_id,
    get_writer,
    reset_writer_config,
    set_asset_resolver,
)


def _png_bytes() -> bytes:
    """Tiny 1x1 PNG (byte identity is what matters in tests)."""
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )


class HistoryV2ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_root = Path(self._tmp.name)
        db_path = self.data_root / ".studio_history_v2" / "history_v2.db"
        self.store = HistoryV2Store(db_path)
        self.repo = HistoryV2Repository(self.store)
        self.app = web.Application()
        register_history_v2_routes(self.app.router, self.data_root)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    # ── Seed helpers ─────────────────────────────────────────────────────

    def _gen(self, prompt: str = "", created=None, **kw):
        return self.repo.create_generation(
            prompt_text=prompt, created_at=created, **kw
        )

    def _gen_completed(self, created=None, mode: str = "preview"):
        gen = self._gen(created=created)
        attempt = self.repo.add_attempt(gen.generation_id, mode=mode)
        self.repo.update_attempt_terminal(attempt.run_id, status="completed")
        return gen

    def _exp(self, name=None, cells=None, created=None, **kw):
        return self.repo.create_experiment(
            name=name, cells=cells if cells is not None else [{}], created_at=created,
            **kw,
        )

    async def _feed(self, kind: str = "mixed", **params):
        url = f"/comfymodal/history-v2/feed?kind={kind}"
        for key, value in params.items():
            url += f"&{key}={value}"
        resp = await self.client.get(url)
        self.assertEqual(resp.status, 200, url)
        return await resp.json()

    # ── Feed ─────────────────────────────────────────────────────────────

    async def test_empty_history_feed(self):
        data = await self._feed("mixed")
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total"], 0)
        self.assertIsNone(data["next_cursor"])
        self.assertFalse(data["has_more"])
        self.assertEqual(data["limit"], 24)

    async def test_mixed_feed_returns_generations_and_experiments(self):
        self._gen_completed(created="2026-01-01T10:00:00.000+00:00")
        self._gen_completed(created="2026-01-01T12:00:00.000+00:00")
        self._exp(created="2026-01-01T09:00:00.000+00:00")
        self._exp(created="2026-01-01T11:00:00.000+00:00")

        data = await self._feed("mixed")
        self.assertEqual(data["total"], 4)
        items = data["items"]
        self.assertEqual({i["kind"] for i in items}, {"generation", "experiment"})
        created = [i["created_at"] for i in items]
        self.assertEqual(created, sorted(created, reverse=True))
        self.assertEqual(
            items[0]["created_at"], "2026-01-01T12:00:00.000+00:00"
        )
        self.assertEqual(
            items[1]["created_at"], "2026-01-01T11:00:00.000+00:00"
        )

    async def test_feed_search_matches_workflow_display_name(self):
        # C15 regression: the workflow display name lives in the linked
        # request snapshot (not the workflow_id), and search + canonical
        # completed must still return the generation.
        gen = self._gen(
            created="2026-01-01T10:00:00.000+00:00",
            workflow_id="wf_smoke_test_id",
        )
        attempt = self.repo.add_attempt(gen.generation_id)
        self.repo.update_attempt_terminal(attempt.run_id, status="completed")
        self.repo.create_request_snapshot(
            generation_id=gen.generation_id,
            workflow_json={"name": "Smoke Test Workflow"},
        )

        data = await self._feed(
            "generation", search=quote("Smoke Test Workflow"), statuses="completed"
        )
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["id"], gen.generation_id)
        self.assertEqual(data["items"][0]["workflow_name"], "Smoke Test Workflow")

        # A completed generation whose display name does not match the term
        # stays excluded (search semantics are not broadened).
        other = self._gen_completed(created="2026-01-01T11:00:00.000+00:00")
        self.repo.create_request_snapshot(
            generation_id=other.generation_id,
            workflow_json={"name": "Other Workflow"},
        )
        data = await self._feed(
            "generation", search=quote("Smoke Test Workflow"), statuses="completed"
        )
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["id"], gen.generation_id)

    async def test_pagination_single_kind(self):
        for i in range(7):
            self._gen_completed(created=f"2026-01-01T10:00:0{i}.000+00:00")

        page1 = await self._feed("generation", limit=3)
        self.assertEqual(len(page1["items"]), 3)
        self.assertIsNotNone(page1["next_cursor"])
        page2 = await self._feed("generation", limit=3, cursor=page1["next_cursor"])
        self.assertEqual(len(page2["items"]), 3)
        self.assertIsNotNone(page2["next_cursor"])
        page3 = await self._feed("generation", limit=3, cursor=page2["next_cursor"])
        self.assertEqual(len(page3["items"]), 1)
        self.assertIsNone(page3["next_cursor"])
        self.assertFalse(page3["has_more"])

        ids = (
            [i["id"] for i in page1["items"]]
            + [i["id"] for i in page2["items"]]
            + [i["id"] for i in page3["items"]]
        )
        self.assertEqual(len(ids), 7)
        self.assertEqual(len(set(ids)), 7, "no overlap across pages")

    async def test_failed_canceled_filter(self):
        failed = self._gen(created="2026-01-01T10:00:00.000+00:00")
        a = self.repo.add_attempt(failed.generation_id, mode="original")
        self.repo.update_attempt_terminal(a.run_id, status="failed", error="boom")
        canceled = self._gen(created="2026-01-01T11:00:00.000+00:00")
        a2 = self.repo.add_attempt(canceled.generation_id, mode="original")
        self.repo.update_attempt_terminal(a2.run_id, status="canceled")
        ok = self._gen_completed(created="2026-01-01T12:00:00.000+00:00")

        expected = {failed.generation_id, canceled.generation_id}
        data = await self._feed("generation", failed_or_canceled="1")
        self.assertEqual({i["id"] for i in data["items"]}, expected)
        data2 = await self._feed("generation", statuses="failed,canceled")
        self.assertEqual({i["id"] for i in data2["items"]}, expected)
        self.assertNotIn(ok.generation_id, {i["id"] for i in data["items"]})

    async def test_interrupted_filter(self):
        interrupted = self._gen(created="2026-01-01T10:00:00.000+00:00")
        a = self.repo.add_attempt(interrupted.generation_id, mode="original")
        self.repo.update_attempt_terminal(a.run_id, status="interrupted")
        other = self._gen_completed(created="2026-01-01T11:00:00.000+00:00")

        data = await self._feed("generation", interrupted="1")
        self.assertEqual({i["id"] for i in data["items"]}, {interrupted.generation_id})
        self.assertNotIn(other.generation_id, {i["id"] for i in data["items"]})

    async def test_status_alias_mapping(self):
        ok = self._gen_completed(created="2026-01-01T10:00:00.000+00:00")
        bad = self._gen(created="2026-01-01T11:00:00.000+00:00")
        a = self.repo.add_attempt(bad.generation_id, mode="preview")
        self.repo.update_attempt_terminal(a.run_id, status="failed", error="boom")

        data = await self._feed("generation", statuses="success")
        self.assertEqual({i["id"] for i in data["items"]}, {ok.generation_id})

        # "partial" → experiments with completed_with_failures
        exp = self.repo.create_experiment(cells=[{}, {}], created_at="2026-01-01T12:00:00.000+00:00")
        exp_id = exp.experiment.experiment_id
        cell_fail, cell_ok = exp.cells
        gen_a = self.repo.create_generation(experiment_id=exp_id)
        attempt = self.repo.add_attempt(
            gen_a.generation_id, mode="original", experiment_id=exp_id, cell_id=cell_fail.cell_id
        )
        self.repo.update_attempt_terminal(attempt.run_id, status="failed", error="boom")
        gen_b = self.repo.create_generation(experiment_id=exp_id)
        attempt2 = self.repo.add_attempt(
            gen_b.generation_id, mode="original", experiment_id=exp_id, cell_id=cell_ok.cell_id
        )
        self.repo.update_attempt_terminal(attempt2.run_id, status="completed")

        data = await self._feed("experiment", statuses="partial")
        self.assertEqual({i["id"] for i in data["items"]}, {exp_id})
        self.assertEqual(data["items"][0]["status"], "completed_with_failures")

    # ── Detail ───────────────────────────────────────────────────────────

    async def test_generation_detail(self):
        gen = self.repo.create_generation(
            workflow_id="wf_a", workflow_version_id="wv_1", preset_id="preset_x",
            preset_name="Preset X", prompt_text="a cat", negative_prompt_text="blur",
            model_stack=[{"type": "checkpoint", "name": "sd15"}],
            created_at="2026-01-01T10:00:00.000+00:00",
        )
        self.repo.create_request_snapshot(
            workflow_json={"3": {"class_type": "KSampler", "inputs": {}}},
            generation_params={"seed": 42, "steps": 20, "cfg": 7.0, "sampler": "euler",
                               "width": 512, "height": 512},
            generation_id=gen.generation_id,
        )
        attempt = self.repo.add_attempt(
            gen.generation_id, mode="preview",
            started_at="2026-01-01T10:00:01.000+00:00",
        )
        self.repo.update_attempt_terminal(
            attempt.run_id, status="completed",
            finished_at="2026-01-01T10:00:05.000+00:00", timing={"total": 4000},
        )
        thumb = self.repo.attach_asset(
            gen.generation_id, run_id=attempt.run_id, asset_type="thumbnail",
            data=_png_bytes(), filename="t.png", fmt="png",
        )
        original = self.repo.attach_asset(
            gen.generation_id, run_id=attempt.run_id, asset_type="original",
            data=_png_bytes(), filename="o.png", fmt="png",
        )
        # F9: the seeded exported record must point at a REAL destination
        # file — the detail route now lazily classifies export state through
        # the F7 checker, so a nonexistent destination would truthfully
        # project `missing` instead of `exported`.
        export_dest = self.data_root / "seeded_export_copy.png"
        export_dest.write_bytes(_png_bytes())
        self.repo.upsert_export_record(
            original.asset_id, state="exported", destination_path=str(export_dest)
        )

        resp = await self.client.get(f"/comfymodal/history-v2/generations/{gen.generation_id}")
        self.assertEqual(resp.status, 200)
        item = (await resp.json())["item"]

        self.assertEqual(item["id"], gen.generation_id)
        self.assertEqual(item["kind"], "generation")
        self.assertEqual(item["status"], "completed")
        self.assertEqual(item["duration_ms"], 4000)
        self.assertEqual(item["completed_at"], "2026-01-01T10:00:05.000+00:00")
        self.assertEqual(item["models"], [{"name": "sd15"}])
        self.assertEqual(len(item["outputs"]), 1)
        out = item["outputs"][0]
        self.assertEqual(out["thumb_url"], f"/comfymodal/history-v2/assets/{thumb.asset_id}")
        self.assertEqual(out["original_url"], f"/comfymodal/history-v2/assets/{original.asset_id}")
        self.assertFalse(out["original_failed"])
        # F9 per-variant export projection (winner identity + lazy state).
        self.assertIsNone(out.get("preview_asset_id"))
        self.assertIsNone(out.get("preview_export_state"))
        self.assertEqual(out["original_asset_id"], original.asset_id)
        self.assertEqual(out["original_export_state"], "exported")

        self.assertEqual(item["attempts"][0]["run_id"], attempt.run_id)
        self.assertEqual(item["attempts"][0]["status"], "completed")
        self.assertEqual(item["attempts"][0]["duration_ms"], 4000)
        self.assertEqual(item["attempts"][0]["timing"], {"total": 4000})
        self.assertEqual(item["errors"], [])
        self.assertEqual(item["export_state"], "exported")
        self.assertEqual(item["params"]["seed"], 42)
        self.assertEqual(item["params"]["steps"], 20)
        self.assertEqual(item["params"]["cfg"], 7.0)
        self.assertEqual(item["params"]["sampler"], "euler")
        self.assertEqual(item["params"]["width"], 512)
        self.assertEqual(item["timing"], {"total": 4000})
        self.assertEqual(item["workflow_json"], {"3": {"class_type": "KSampler", "inputs": {}}})

        # Unknown generation → 404
        resp = await self.client.get("/comfymodal/history-v2/generations/gen_unknown")
        self.assertEqual(resp.status, 404)

    async def test_experiment_detail_fixed_cells(self):
        exp = self.repo.create_experiment(
            name="grid", created_at="2026-01-01T10:00:00.000+00:00",
            definition={"workflow": "wf-a", "preset": "preset-a",
                        "axis_labels": {"seed": [1, 2, 3, 4, 5]}},
            cells=[{"axis_labels": {"seed": i}} for i in range(5)],
        )
        exp_id = exp.experiment.experiment_id
        for i, cell in enumerate(exp.cells[:4]):
            gen = self.repo.create_generation(
                experiment_id=exp_id, created_at=f"2026-01-01T11:0{i}:00.000+00:00"
            )
            attempt = self.repo.add_attempt(
                gen.generation_id, mode="preview", experiment_id=exp_id,
                cell_id=cell.cell_id, started_at=f"2026-01-01T11:0{i}:01.000+00:00",
            )
            self.repo.update_attempt_terminal(
                attempt.run_id, status="completed", finished_at=f"2026-01-01T11:0{i}:02.000+00:00"
            )
            self.repo.attach_asset(
                gen.generation_id, run_id=attempt.run_id, asset_type="preview",
                data=_png_bytes(), filename=f"p{i}.png", fmt="png",
            )
            self.repo.update_experiment_cell(cell.cell_id, generation_id=gen.generation_id)
        last = exp.cells[4]
        gen_last = self.repo.create_generation(experiment_id=exp_id)
        attempt = self.repo.add_attempt(
            gen_last.generation_id, mode="original", experiment_id=exp_id, cell_id=last.cell_id
        )
        self.repo.update_attempt_terminal(attempt.run_id, status="failed", error="boom")
        self.repo.update_experiment_cell(last.cell_id, generation_id=gen_last.generation_id)

        resp = await self.client.get(f"/comfymodal/history-v2/experiments/{exp_id}")
        self.assertEqual(resp.status, 200)
        item = (await resp.json())["item"]

        self.assertEqual(item["kind"], "experiment")
        self.assertEqual(item["status"], "completed_with_failures")
        self.assertEqual(item["name"], "grid")
        self.assertEqual(item["workflow"], "wf-a")
        self.assertEqual(item["preset"], "preset-a")
        self.assertEqual(item["true_cell_count"], 5)
        self.assertEqual(item["result_count"], 4)
        self.assertEqual(item["failed_count"], 1)
        self.assertEqual(item["interrupted_count"], 0)
        self.assertEqual(item["axis_labels"], {"x": "seed", "y": ""})

        cells = item["cells"]
        self.assertEqual([c["index"] for c in cells], [0, 1, 2, 3, 4])
        self.assertEqual([c["status"] for c in cells],
                         ["completed", "completed", "completed", "completed", "failed"])
        self.assertIsNone(cells[0]["error"])
        self.assertEqual(cells[4]["error"], "boom")
        self.assertEqual(cells[0]["thumb_url"], "")
        self.assertTrue(cells[0]["preview_url"].startswith("/comfymodal/history-v2/assets/"))
        self.assertEqual(cells[0]["original_url"], "")
        self.assertFalse(cells[0]["original_failed"])
        self.assertEqual(len(item["cover"]), 4)
        self.assertEqual(item["cover"][0]["cellKey"], exp.cells[0].cell_id)
        self.assertTrue(
            item["cover"][0]["thumb_url"].startswith("/comfymodal/history-v2/assets/")
        )

        # Unknown experiment → 404
        resp = await self.client.get("/comfymodal/history-v2/experiments/exp_unknown")
        self.assertEqual(resp.status, 404)

    # ── Annotations ──────────────────────────────────────────────────────

    async def test_favorite_persistence(self):
        gen = self._gen_completed(created="2026-01-01T10:00:00.000+00:00")
        resp = await self.client.patch(
            f"/comfymodal/history-v2/generations/{gen.generation_id}/favorite",
            json={"favorite": True},
        )
        self.assertEqual(resp.status, 200)
        self.assertIs((await resp.json())["favorite"], True)
        feed = await self._feed("generation")
        self.assertIs(feed["items"][0]["favorite"], True)

        resp = await self.client.patch(
            f"/comfymodal/history-v2/generations/{gen.generation_id}/favorite",
            json={"favorite": False},
        )
        self.assertEqual(resp.status, 200)
        feed = await self._feed("generation")
        self.assertIs(feed["items"][0]["favorite"], False)

        # Unknown generation → 404
        resp = await self.client.patch(
            "/comfymodal/history-v2/generations/gen_unknown/favorite", json={"favorite": True}
        )
        self.assertEqual(resp.status, 404)

    async def test_note_persistence(self):
        gen = self._gen_completed(created="2026-01-01T10:00:00.000+00:00")
        resp = await self.client.patch(
            f"/comfymodal/history-v2/generations/{gen.generation_id}/note",
            json={"note": "hello note"},
        )
        self.assertEqual(resp.status, 200)
        feed = await self._feed("generation")
        self.assertEqual(feed["items"][0]["note"], "hello note")

        resp = await self.client.patch(
            f"/comfymodal/history-v2/generations/{gen.generation_id}/note",
            json={"note": "x" * 2001},
        )
        self.assertEqual(resp.status, 400)

        # Unknown generation → 404
        resp = await self.client.patch(
            "/comfymodal/history-v2/generations/gen_unknown/note", json={"note": "n"}
        )
        self.assertEqual(resp.status, 404)

    async def test_featured_output_change(self):
        gen = self._gen_completed(created="2026-01-01T10:00:00.000+00:00")
        run = self.repo.add_attempt(gen.generation_id, mode="preview")
        self.repo.update_attempt_terminal(run.run_id, status="completed")
        run2 = self.repo.add_attempt(gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(run2.run_id, status="completed")
        self.repo.attach_asset(
            gen.generation_id, run_id=run.run_id, asset_type="preview",
            data=_png_bytes(), filename="a.png", fmt="png",
        )
        self.repo.attach_asset(
            gen.generation_id, run_id=run2.run_id, asset_type="original",
            data=_png_bytes(), filename="b.png", fmt="png",
        )

        resp = await self.client.patch(
            f"/comfymodal/history-v2/generations/{gen.generation_id}/featured",
            json={"output_index": 1},
        )
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        detail = self.repo.get_generation(gen.generation_id)
        assert detail is not None
        self.assertEqual(detail.generation.featured_asset_id, data["featured_asset_id"])

        feed = await self._feed("generation")
        self.assertEqual(feed["items"][0]["featured_output_index"], 1)

        # Invalid output index → 400
        resp = await self.client.patch(
            f"/comfymodal/history-v2/generations/{gen.generation_id}/featured",
            json={"output_index": 99},
        )
        self.assertEqual(resp.status, 400)

    async def test_featured_invalid_foreign_asset_rejected(self):
        gen = self._gen_completed(created="2026-01-01T10:00:00.000+00:00")
        other = self._gen_completed(created="2026-01-01T11:00:00.000+00:00")
        foreign = self.repo.attach_asset(
            other.generation_id, asset_type="preview", data=_png_bytes(),
            filename="f.png", fmt="png",
        )
        resp = await self.client.patch(
            f"/comfymodal/history-v2/generations/{gen.generation_id}/featured",
            json={"asset_id": foreign.asset_id},
        )
        self.assertEqual(resp.status, 400)
        body = await resp.json()
        self.assertEqual(body["message"], "asset does not belong to generation")

    async def test_experiment_multi_status_filter(self):
        # UI always sends a statuses list (e.g. ["success","running","partial"]).
        # Experiments must filter by the full mapped set, not a single status.
        exp1 = self._exp(name="completed exp", created="2026-01-01T10:00:00.000+00:00")
        self.repo.set_experiment_status(exp1.experiment.experiment_id, "completed")
        exp = self._exp(name="running exp", created="2026-01-01T11:00:00.000+00:00")
        self.repo.set_experiment_status(exp.experiment.experiment_id, "running")
        exp3 = self._exp(name="partial exp", created="2026-01-01T12:00:00.000+00:00")
        self.repo.set_experiment_status(exp3.experiment.experiment_id, "completed_with_failures")
        exp4 = self._exp(name="failed exp", created="2026-01-01T13:00:00.000+00:00")
        self.repo.set_experiment_status(exp4.experiment.experiment_id, "failed")

        data = await self._feed(
            "experiment", statuses="success,running,partial"
        )
        statuses = {i["status"] for i in data["items"]}
        self.assertEqual(
            statuses, {"completed", "running", "completed_with_failures"}
        )

        # Single kind via the mixed feed must apply the same multi-status set.
        mixed = await self._feed("mixed", statuses="success,running,partial")
        mixed_statuses = {i["status"] for i in mixed["items"]}
        self.assertIn("completed_with_failures", mixed_statuses)
        self.assertIn("running", mixed_statuses)
        self.assertNotIn("failed", mixed_statuses)

    async def test_experiment_favorite_and_note_durable(self):
        exp = self._exp(name="grid", created="2026-01-01T10:00:00.000+00:00")
        exp_id = exp.experiment.experiment_id
        resp = await self.client.patch(
            f"/comfymodal/history-v2/experiments/{exp_id}/favorite", json={"favorite": True}
        )
        self.assertEqual(resp.status, 200)
        resp = await self.client.patch(
            f"/comfymodal/history-v2/experiments/{exp_id}/note", json={"note": "exp note"}
        )
        self.assertEqual(resp.status, 200)

        rows = self.repo.query_experiments(limit=50)["items"]
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0]["favorite"], True)
        self.assertEqual(rows[0]["note"], "exp note")

        feed = await self._feed("experiment")
        self.assertIs(feed["items"][0]["favorite"], True)
        self.assertEqual(feed["items"][0]["note"], "exp note")

        # Unknown experiment → 404
        resp = await self.client.patch(
            "/comfymodal/history-v2/experiments/exp_unknown/favorite", json={"favorite": True}
        )
        self.assertEqual(resp.status, 404)
        # Over-long note → 400
        resp = await self.client.patch(
            f"/comfymodal/history-v2/experiments/{exp_id}/note", json={"note": "x" * 2001}
        )
        self.assertEqual(resp.status, 400)

    # ── Assets ───────────────────────────────────────────────────────────

    async def test_managed_asset_serves_correct_file(self):
        gen = self._gen_completed(created="2026-01-01T10:00:00.000+00:00")
        asset = self.repo.attach_asset(
            gen.generation_id, asset_type="preview", data=_png_bytes(),
            filename="t.png", fmt="png",
        )
        resp = await self.client.get(f"/comfymodal/history-v2/assets/{asset.asset_id}")
        self.assertEqual(resp.status, 200)
        self.assertEqual(await resp.read(), _png_bytes())
        self.assertEqual(resp.headers["Content-Type"], "image/png")

    async def test_asset_route_rejects_invalid(self):
        gen = self._gen_completed(created="2026-01-01T10:00:00.000+00:00")
        self.repo.attach_asset(
            gen.generation_id, asset_type="preview", data=_png_bytes(),
            filename="t.png", fmt="png",
        )
        for bad in ("does-not-exist", "..%2Fetc%2Fpasswd", "../foo", "x/../../y"):
            resp = await self.client.get(f"/comfymodal/history-v2/assets/{bad}")
            self.assertEqual(resp.status, 404, f"asset id {bad!r} must be 404")
            body = await resp.read()
            self.assertNotEqual(body, _png_bytes(), f"asset id {bad!r} leaked file bytes")


    # ── C14: producer-adopted asset through feed / detail / asset route ──

    async def test_c14_adopted_producer_asset_feed_detail_and_route(self):
        """A descriptor-only modern success (valid ``primary_asset_id``, no
        output path) adopted by the writer surfaces in the feed and detail with
        ``output_count == 1`` / ``has_image == True`` and a featured original,
        and the History V2 asset route serves the producer file bytes with the
        correct MIME type (endpoint regression)."""
        producer_id = "ast_c14_producer"
        file = Path(self.data_root) / "c14_producer.png"
        file.write_bytes(_png_bytes())
        record = {
            "asset_id": producer_id,
            "path": str(file),
            "mime_type": "image/png",
            "content_hash": hashlib.sha256(_png_bytes()).hexdigest(),
            "width": 1,
            "height": 1,
        }
        set_asset_resolver(
            lambda aid: record if aid == producer_id else None
        )
        self.addCleanup(reset_writer_config)
        writer = get_writer(self.data_root)
        writer.record_run(
            run_id="r_c14_api", kind="studio_run", status="submitted",
            prompt_id="p", workflow_hash="w",
            meta={
                "workflow_id": "wf_c14",
                "workflow_name": "C14 Workflow",
                "primary_asset_id": producer_id,
                "requested_controls": {"prompt": "a cat", "seed": 0, "steps": 20},
                "workflow_json": {"3": {"class_type": "KSampler", "inputs": {}}},
            },
        )
        writer.update_run(
            "r_c14_api", status="completed",
            completed_at="2026-01-01T10:05:00.000+00:00",
            timings={"end_to_end_total_ms": 500}, meta={},
            primary_asset_id=producer_id,
        )
        gid = _gen_id("r_c14_api")

        # Feed: one output, has_image, featured, workflow_name persisted.
        data = await self._feed("generation")
        item = next(i for i in data["items"] if i["id"] == gid)
        self.assertEqual(item["output_count"], 1)
        self.assertIs(item["has_image"], True)
        self.assertEqual(item["featured_output_index"], 0)
        self.assertEqual(item["workflow_name"], "C14 Workflow")
        asset_id = item["outputs"][0]["asset_id"]
        self.assertEqual(
            item["outputs"][0]["original_url"],
            f"/comfymodal/history-v2/assets/{asset_id}",
        )

        # Detail agrees.
        resp = await self.client.get(f"/comfymodal/history-v2/generations/{gid}")
        self.assertEqual(resp.status, 200)
        detail = (await resp.json())["item"]
        self.assertEqual(detail["output_count"], 1)
        self.assertIs(detail["has_image"], True)
        self.assertEqual(detail["featured_output_index"], 0)

        # Asset route serves the producer file bytes with the right MIME, and
        # the producer/generic file itself stays valid.
        asset = self.repo.get_asset(asset_id)
        self.assertIsNotNone(asset)
        self.assertEqual(Path(asset.managed_path), file.resolve())
        self.assertEqual(asset.sha256, record["content_hash"])
        resp = await self.client.get(f"/comfymodal/history-v2/assets/{asset_id}")
        self.assertEqual(resp.status, 200)
        self.assertEqual(await resp.read(), _png_bytes())
        self.assertEqual(resp.headers["Content-Type"], "image/png")
        self.assertEqual(file.read_bytes(), _png_bytes())

    # ── C14: workflow display-name persistence / fallback ────────────────

    async def test_c14_workflow_display_name_persistence_and_fallback(self):
        """``workflow_name`` is persisted from the request snapshot and never
        falls back to the workflow_id: a name in ``workflow_json`` wins, the
        preset snapshot's ``workflow_name`` is the fallback, and a record with
        neither reports null."""
        writer = get_writer(self.data_root)
        self.addCleanup(reset_writer_config)

        def _run(run_id: str, meta: dict):
            writer.record_run(
                run_id=run_id, kind="studio_run", status="submitted",
                prompt_id="p", workflow_hash="w", meta=meta,
            )
            writer.update_run(
                run_id, status="completed",
                completed_at="2026-01-01T10:05:00.000+00:00", meta={},
            )

        # (a) workflow_json extra.workflow.name persists and wins over meta.
        _run("r_name1", {
            "workflow_id": "wf_a", "workflow_name": "Meta Fallback",
            "workflow_json": {
                "3": {"class_type": "KSampler", "inputs": {}},
                "extra": {"workflow": {"name": "Persisted Name"}},
            },
        })
        # (b) workflow_json top-level title is a valid display name.
        _run("r_name2", {
            "workflow_id": "wf_b",
            "workflow_json": {
                "3": {"class_type": "KSampler", "inputs": {}},
                "title": "Title Name",
            },
        })
        # (c) preset_snapshot.workflow_name fallback when JSON carries none.
        _run("r_name3", {
            "workflow_id": "wf_c", "workflow_name": "Fallback Name",
            "workflow_json": {"3": {"class_type": "KSampler", "inputs": {}}},
        })
        # (d) never falls back to workflow_id (unknown name → null).
        _run("r_name4", {
            "workflow_id": "wf_d",
            "workflow_json": {"3": {"class_type": "KSampler", "inputs": {}}},
        })

        data = await self._feed("generation")
        by_id = {i["id"]: i for i in data["items"]}
        self.assertEqual(by_id[_gen_id("r_name1")]["workflow_name"], "Persisted Name")
        self.assertEqual(by_id[_gen_id("r_name2")]["workflow_name"], "Title Name")
        self.assertEqual(by_id[_gen_id("r_name3")]["workflow_name"], "Fallback Name")
        self.assertIsNone(by_id[_gen_id("r_name4")]["workflow_name"])

    # ── C14: History asset endpoint regression ───────────────────────────

    async def test_c14_asset_endpoint_regression_missing_reference_404(self):
        """An adopted producer reference whose backing file disappears makes
        the asset route 404 truthfully (never serves stale or fabricated
        bytes)."""
        producer_id = "ast_c14_gone"
        file = Path(self.data_root) / "c14_gone.png"
        file.write_bytes(_png_bytes())
        set_asset_resolver(lambda aid: {
            "asset_id": producer_id,
            "path": str(file),
            "mime_type": "image/png",
        } if aid == producer_id else None)
        self.addCleanup(reset_writer_config)
        writer = get_writer(self.data_root)
        writer.record_run(
            run_id="r_c14_gone", kind="studio_run", status="submitted",
            prompt_id="p", workflow_hash="w",
            meta={
                "workflow_id": "wf_g",
                "primary_asset_id": producer_id,
                "workflow_json": {"3": {"class_type": "KSampler", "inputs": {}}},
            },
        )
        writer.update_run(
            "r_c14_gone", status="completed",
            completed_at="2026-01-01T10:05:00.000+00:00",
            meta={}, primary_asset_id=producer_id,
        )
        asset = self.repo.get_asset(producer_id)
        self.assertIsNotNone(asset)
        self.assertEqual(Path(asset.managed_path), file.resolve())

        file.unlink()
        resp = await self.client.get(f"/comfymodal/history-v2/assets/{producer_id}")
        self.assertEqual(resp.status, 404)
        body = await resp.read()
        self.assertNotEqual(
            body, _png_bytes(),
            "a missing backing file must never serve file bytes",
        )


if __name__ == "__main__":
    unittest.main()
