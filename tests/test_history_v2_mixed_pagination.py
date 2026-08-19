"""History V2 mixed-feed pagination correctness tests (API level).

Regression fixture for the mixed Generations+Experiments feed across all six
orders.  The oracle is the fully-materialized expected ordering: each stream
is materialized with the proven single-kind keyset pagination, then merged
with the production ``_merge_streams`` sort tuple — the SAME tuple used by
the production merge comparison, cursor advancement, and these tests.

Pre-fix failure mode (documented production bug): the old ``{g, e, gs, es}``
mixed cursor anchored each stream cursor after the last FETCHED item and
carried "skip" counts for fetched-but-unemitted window tails.  Because the
cursor already advanced past those tails, the next page sliced away the
first ``gs``/``es`` FRESH items (never seen) while the true tails were
permanently unreachable — any page where one stream lost the merge dropped
records from that stream (duplicates/loss across mixed pages).

These tests assert zero gaps, zero duplicates, deterministic order, and
exact equality with the oracle for every ordering and every page size.
"""
from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from history_v2_repository import HistoryV2Repository
from history_v2_routes import _merge_streams, register_history_v2_routes
from history_v2_store import HistoryV2Store

ORDERS = ("newest", "oldest", "fastest", "slowest", "workflow_asc", "workflow_desc")
PAGE_SIZES = (1, 2, 5, 24)


def _keyset_cursor(created_at: str, item_id: str, key=None) -> str:
    payload = json.dumps({"k": key, "created_at": created_at, "id": item_id})
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _legacy_mixed_cursor(g: Optional[str], e: Optional[str], gs: int, es: int) -> str:
    """Craft a pre-fix (V1) mixed cursor ``{g, e, gs, es}``."""
    payload = json.dumps({"g": g, "e": e, "gs": gs, "es": es})
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_payload(cursor: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))


class HistoryV2MixedPaginationTests(unittest.IsolatedAsyncioTestCase):
    """Full-traversal gap/duplicate/order correctness across all six orders."""

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

    # ── Seeding ──────────────────────────────────────────────────────────

    def _ts(self, base: str, i: int, step_ms: int = 1000) -> str:
        """Deterministic millisecond-precision UTC timestamp."""
        import datetime as _dt

        dt = _dt.datetime.fromisoformat(base)
        dt = dt + _dt.timedelta(milliseconds=i * step_ms)
        return dt.isoformat(timespec="milliseconds").replace("+00:00", "+00:00")

    def _gen(self, created: str, workflow_id: Optional[str] = None, **kw):
        return self.repo.create_generation(
            created_at=created, workflow_id=workflow_id, **kw
        )

    def _gen_timed(self, created: str, duration_ms: int, workflow_id: Optional[str] = None):
        """Generation with one completed attempt of exactly duration_ms."""
        import datetime as _dt

        gen = self._gen(created=created, workflow_id=workflow_id)
        start = _dt.datetime.fromisoformat(created)
        start = start + _dt.timedelta(seconds=1)
        finish = start + _dt.timedelta(milliseconds=duration_ms)
        attempt = self.repo.add_attempt(
            gen.generation_id, mode="original",
            started_at=start.isoformat(timespec="milliseconds"),
        )
        self.repo.update_attempt_terminal(
            attempt.run_id, status="completed",
            finished_at=finish.isoformat(timespec="milliseconds"),
        )
        return gen

    def _exp(self, created: str, name: Optional[str] = None, **kw):
        return self.repo.create_experiment(
            name=name, cells=[], created_at=created, **kw
        )

    def _exp_timed(self, created: str, duration_ms: int, name: Optional[str] = None):
        """Experiment whose max attempt wall-clock duration is duration_ms."""
        import datetime as _dt

        exp = self._exp(created=created, name=name)
        gen = self.repo.create_generation(
            experiment_id=exp.experiment.experiment_id, created_at=created,
        )
        start = _dt.datetime.fromisoformat(created)
        start = start + _dt.timedelta(seconds=1)
        finish = start + _dt.timedelta(milliseconds=duration_ms)
        attempt = self.repo.add_attempt(
            gen.generation_id, mode="original",
            experiment_id=exp.experiment.experiment_id,
            started_at=start.isoformat(timespec="milliseconds"),
        )
        self.repo.update_attempt_terminal(
            attempt.run_id, status="completed",
            finished_at=finish.isoformat(timespec="milliseconds"),
        )
        return exp

    # ── Seed shapes (deliberately uneven distributions) ─────────────────

    def seed_gens_dense(self) -> None:
        """30 generations clustered between 5 experiment timestamps."""
        for i in range(5):
            self._exp(created=self._ts("2026-01-01T00:00:00.000+00:00", i * 60))
        for i in range(30):
            self._gen(created=self._ts("2026-01-01T00:00:00.000+00:00", i * 2 + 1))

    def seed_exps_dense(self) -> None:
        """5 generations vs 30 experiments clustered between them."""
        for i in range(5):
            self._gen(created=self._ts("2026-01-01T00:00:00.000+00:00", i * 60))
        for i in range(30):
            self._exp(created=self._ts("2026-01-01T00:00:00.000+00:00", i * 2 + 1))

    def seed_identical_timestamps(self) -> None:
        """Many items sharing the SAME created_at across kinds."""
        for i in range(10):
            self._gen(created="2026-01-01T00:00:00.000+00:00")
        for i in range(10):
            self._exp(created="2026-01-01T00:00:00.000+00:00")
        for i in range(5):
            self._gen(created="2026-01-01T01:00:00.000+00:00")
        for i in range(5):
            self._exp(created="2026-01-01T01:00:00.000+00:00")

    def seed_page_boundary_clusters(self) -> None:
        """Alternating runs of 7 so merge losers cluster at window edges."""
        for run in range(4):
            base = run * 100
            for i in range(7):
                self._gen(created=self._ts("2026-01-01T00:00:00.000+00:00", base + i))
            for i in range(7):
                self._exp(created=self._ts("2026-01-01T00:00:00.000+00:00", base + 10 + i))

    def seed_large(self) -> None:
        """60 gens + 40 exps interleaved (5 pages at limit=24)."""
        for i in range(60):
            self._gen(created=self._ts("2026-01-01T00:00:00.000+00:00", i * 3))
        for i in range(40):
            self._exp(created=self._ts("2026-01-01T00:00:00.000+00:00", i * 4 + 1))

    # ── Oracle ───────────────────────────────────────────────────────────

    def _materialize(self, order: str, kind: str) -> list[dict]:
        items: list[dict] = []
        cursor: Optional[str] = None
        while True:
            if kind == "generation":
                page = self.repo.query_generations(limit=200, cursor=cursor, order=order)
            else:
                page = self.repo.query_experiments(limit=200, cursor=cursor, order=order)
            items.extend(page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                return items

    def _oracle_ids(self, order: str) -> list[str]:
        """Fully-materialized expected mixed ordering (test oracle only)."""
        gen_items = self._materialize(order, "generation")
        exp_items = self._materialize(order, "experiment")
        merged = _merge_streams(gen_items, exp_items, order)
        return [
            m.get("id") or m.get("generation_id") or m.get("experiment_id") or ""
            for m in merged
        ]

    # ── Traversal ────────────────────────────────────────────────────────

    async def _feed(self, kind: str = "mixed", **params) -> dict:
        url = f"/comfymodal/history-v2/feed?kind={kind}"
        for key, value in params.items():
            url += f"&{key}={value}"
        resp = await self.client.get(url)
        self.assertEqual(resp.status, 200, url)
        return await resp.json()

    async def _walk(self, order: str, limit: int) -> tuple[list[str], int]:
        """Walk the entire mixed feed page by page; return (ids, pages)."""
        ids: list[str] = []
        cursor: Optional[str] = None
        pages = 0
        while True:
            params = {"limit": limit, "order": order}
            if cursor:
                params["cursor"] = cursor
            data = await self._feed("mixed", **params)
            self.assertEqual(data["status"], "ok")
            page_ids = [i["id"] for i in data["items"]]
            self.assertEqual(
                len(page_ids), len(set(page_ids)),
                f"{order} limit={limit} page {pages}: duplicate ids within page",
            )
            ids.extend(page_ids)
            cursor = data["next_cursor"]
            pages += 1
            self.assertLess(pages, 200, f"{order} limit={limit}: no-replay guard")
            if cursor is None:
                break
        return ids, pages

    async def _assert_oracle_traversal(self, order: str, limit: int) -> None:
        expected = self._oracle_ids(order)
        ids, pages = await self._walk(order, limit)
        self.assertEqual(
            ids, expected,
            f"{order} limit={limit}: traversal order differs from oracle "
            f"(got {len(ids)} ids over {pages} pages, expected {len(expected)})",
        )
        self.assertEqual(
            len(set(ids)), len(ids),
            f"{order} limit={limit}: duplicates across pages",
        )
        self.assertEqual(
            set(ids), set(expected),
            f"{order} limit={limit}: dropped records across pages "
            f"(missing {set(expected) - set(ids)})",
        )

    # ── Matrix: every order × every page size × every seed shape ────────

    async def test_gens_dense_all_orders_all_page_sizes(self):
        self.seed_gens_dense()
        for order in ORDERS:
            for limit in PAGE_SIZES:
                await self._assert_oracle_traversal(order, limit)

    async def test_exps_dense_all_orders_all_page_sizes(self):
        self.seed_exps_dense()
        for order in ORDERS:
            for limit in PAGE_SIZES:
                await self._assert_oracle_traversal(order, limit)

    async def test_identical_timestamps_all_orders(self):
        self.seed_identical_timestamps()
        for order in ORDERS:
            for limit in PAGE_SIZES:
                await self._assert_oracle_traversal(order, limit)

    async def test_page_boundary_clusters_all_orders(self):
        self.seed_page_boundary_clusters()
        for order in ORDERS:
            for limit in PAGE_SIZES:
                await self._assert_oracle_traversal(order, limit)

    async def test_large_dataset_three_plus_pages_all_orders(self):
        self.seed_large()
        for order in ORDERS:
            for limit in (1, 24):
                await self._assert_oracle_traversal(order, limit)

    # ── Exhausted-stream behavior (one stream ends early) ────────────────

    async def test_one_stream_exhausts_early(self):
        # 3 experiments at the very start, then 40 generations: the
        # experiment stream drains on page 1-2 while generations continue.
        for i in range(3):
            self._exp(created=self._ts("2026-01-01T00:00:00.000+00:00", i))
        for i in range(40):
            self._gen(created=self._ts("2026-01-01T00:00:00.000+00:00", 10 + i * 3))
        for order in ORDERS:
            for limit in (1, 24):
                await self._assert_oracle_traversal(order, limit)

    async def test_both_streams_end_same_page(self):
        # 25 gens + 25 exps, limit 24: both streams exhaust mid-traversal.
        for i in range(25):
            self._gen(created=self._ts("2026-01-01T00:00:00.000+00:00", i * 2))
            self._exp(created=self._ts("2026-01-01T00:00:00.000+00:00", i * 2 + 1))
        for order in ORDERS:
            await self._assert_oracle_traversal(order, 24)

    # ── Fastest / Slowest edge cases ─────────────────────────────────────

    async def test_fastest_slowest_null_durations(self):
        # Mix of NULL-duration and timed items across both kinds.
        self._gen(created="2026-01-01T00:00:00.000+00:00")  # NULL duration
        self._gen(created="2026-01-01T00:00:01.000+00:00")
        self._exp(created="2026-01-01T00:00:02.000+00:00")  # NULL duration
        self._gen_timed(created="2026-01-01T00:00:03.000+00:00", duration_ms=500)
        self._exp_timed(created="2026-01-01T00:00:04.000+00:00", duration_ms=100)
        self._gen_timed(created="2026-01-01T00:00:05.000+00:00", duration_ms=500)
        self._exp_timed(created="2026-01-01T00:00:06.000+00:00", duration_ms=9000)
        for order in ("fastest", "slowest"):
            for limit in (1, 2, 5):
                await self._assert_oracle_traversal(order, limit)

    async def test_fastest_slowest_duration_ties(self):
        # Equal durations across kinds and within a kind (tie-break on
        # created_at then id — deterministic final tie-breakers).
        for i in range(4):
            self._gen_timed(
                created=self._ts("2026-01-01T00:00:00.000+00:00", i), duration_ms=1000
            )
            self._exp_timed(
                created=self._ts("2026-01-01T00:00:00.000+00:00", i), duration_ms=1000
            )
        self._gen_timed(
            created="2026-01-01T00:00:05.000+00:00", duration_ms=1000
        )
        self._exp_timed(
            created="2026-01-01T00:00:05.000+00:00", duration_ms=1000
        )
        for order in ("fastest", "slowest"):
            for limit in (1, 2, 5, 24):
                await self._assert_oracle_traversal(order, limit)

    # ── Workflow A-Z / Z-A edge cases ────────────────────────────────────

    async def test_workflow_orders_missing_keys_case_and_ties(self):
        # Missing workflow names/ids, case-insensitive ordering, equal keys,
        # and deterministic timestamp/id tie-breakers.
        self._gen(created="2026-01-01T00:00:00.000+00:00", workflow_id=None)
        self._gen(created="2026-01-01T00:00:01.000+00:00", workflow_id="")
        self._exp(created="2026-01-01T00:00:02.000+00:00", name=None)
        self._exp(created="2026-01-01T00:00:03.000+00:00", name="")
        self._gen(created="2026-01-01T00:00:04.000+00:00", workflow_id="alpha")
        self._gen(created="2026-01-01T00:00:05.000+00:00", workflow_id="Alpha")
        self._exp(created="2026-01-01T00:00:06.000+00:00", name="beta")
        self._exp(created="2026-01-01T00:00:07.000+00:00", name="Beta")
        self._gen(created="2026-01-01T00:00:08.000+00:00", workflow_id="zeta")
        # Equal workflow keys → created_at/id tie-break.
        self._gen(created="2026-01-01T00:00:09.000+00:00", workflow_id="same")
        self._gen(created="2026-01-01T00:00:09.000+00:00", workflow_id="same")
        self._exp(created="2026-01-01T00:00:09.000+00:00", name="same")
        for order in ("workflow_asc", "workflow_desc"):
            for limit in (1, 2, 5):
                await self._assert_oracle_traversal(order, limit)

    async def test_workflow_orders_case_only_names(self):
        # Names differing ONLY in case with identical timestamps: the merge
        # must be deterministic and match the oracle (case-insensitive key,
        # then created_at, then id).
        for i in range(6):
            self._gen(created="2026-01-01T00:00:00.000+00:00",
                      workflow_id=["a", "A", "b", "B", "aa", "AA"][i])
        for i in range(6):
            self._exp(created="2026-01-01T00:00:00.000+00:00",
                      name=["a", "A", "b", "B", "aa", "AA"][i])
        for order in ("workflow_asc", "workflow_desc"):
            for limit in (1, 2, 5):
                await self._assert_oracle_traversal(order, limit)

    # ── Equal timestamps / equal durations (cross-kind ties) ─────────────

    async def test_equal_timestamps_newest_oldest(self):
        self.seed_identical_timestamps()
        for order in ("newest", "oldest"):
            for limit in (1, 2, 5):
                await self._assert_oracle_traversal(order, limit)

    # ── API contract: cursor payload ─────────────────────────────────────

    async def test_cursor_payload_is_versioned_and_skip_free(self):
        self.seed_large()
        data = await self._feed("mixed", limit=5, order="newest")
        self.assertIsNotNone(data["next_cursor"])
        payload = _decode_payload(data["next_cursor"])
        self.assertEqual(payload.get("v"), 2, "mixed cursor must be versioned v2")
        self.assertNotIn("gs", payload, "v2 cursor must not carry skip counts")
        self.assertNotIn("es", payload, "v2 cursor must not carry skip counts")
        self.assertIn("g", payload)
        self.assertIn("e", payload)
        self.assertIsInstance(payload["g"], (str, type(None)))
        self.assertIsInstance(payload["e"], (str, type(None)))

    async def test_malformed_cursor_rejected(self):
        self.seed_large()
        bad_cursors = [
            "not-a-cursor",
            "!!!",
            base64.urlsafe_b64encode(b"hello").decode("ascii"),
            base64.urlsafe_b64encode(json.dumps({"v": 99}).encode()).decode("ascii"),
            base64.urlsafe_b64encode(json.dumps({"v": 2, "g": 5, "e": None}).encode()).decode("ascii"),
            base64.urlsafe_b64encode(json.dumps({"v": 2, "g": "x", "e": []}).encode()).decode("ascii"),
            base64.urlsafe_b64encode(json.dumps([1, 2, 3]).encode()).decode("ascii"),
        ]
        for bad in bad_cursors:
            resp = await self.client.get(
                f"/comfymodal/history-v2/feed?kind=mixed&limit=5&cursor={bad}"
            )
            self.assertEqual(resp.status, 400, f"cursor {bad!r} must be rejected")
            body = await resp.json()
            self.assertEqual(body["message"], "invalid cursor")

    async def test_legacy_v1_cursor_tolerated(self):
        self.seed_gens_dense()
        page1 = await self._feed("mixed", limit=5, order="newest")
        # Anchor a legacy cursor at the last EMITTED item of each stream.
        last_gen = next(
            (i for i in reversed(page1["items"]) if i["kind"] == "generation"), None
        )
        last_exp = next(
            (i for i in reversed(page1["items"]) if i["kind"] == "experiment"), None
        )
        g_keyset = _keyset_cursor(last_gen["created_at"], last_gen["id"]) if last_gen else None
        e_keyset = _keyset_cursor(last_exp["created_at"], last_exp["id"]) if last_exp else None
        legacy = _legacy_mixed_cursor(g_keyset, e_keyset, gs=0, es=0)

        # V1 cursors are tolerated (200), and zero-skip legacy anchors behave
        # exactly like v2 anchors → full traversal still matches the oracle.
        ids: list[str] = [i["id"] for i in page1["items"]]
        cursor: Optional[str] = legacy
        while cursor:
            data = await self._feed("mixed", limit=5, order="newest", cursor=cursor)
            ids.extend(i["id"] for i in data["items"])
            cursor = data["next_cursor"]
        self.assertEqual(ids, self._oracle_ids("newest"))

        # Non-zero skip counts in a legacy cursor are ignored, not rejected.
        legacy_skip = _legacy_mixed_cursor(g_keyset, e_keyset, gs=1, es=1)
        resp = await self.client.get(
            f"/comfymodal/history-v2/feed?kind=mixed&limit=5&cursor={legacy_skip}"
        )
        self.assertEqual(resp.status, 200)
        body = await resp.json()
        self.assertEqual(body["status"], "ok")
        # The response upgrades to a v2 cursor.
        if body["next_cursor"] is not None:
            self.assertEqual(_decode_payload(body["next_cursor"]).get("v"), 2)

    async def test_complete_traversal_yields_exact_ids_once(self):
        self.seed_page_boundary_clusters()
        expected = self._oracle_ids("newest")
        for limit in (1, 7, 24):
            ids, pages = await self._walk("newest", limit)
            self.assertEqual(len(ids), len(set(ids)), f"limit={limit}: unique ids")
            self.assertEqual(set(ids), set(expected), f"limit={limit}: same set")
            self.assertEqual(len(ids), len(expected), f"limit={limit}: no extras")
            self.assertEqual(pages, -(-len(expected) // limit), f"limit={limit}: page count")


class HistoryV2ContractTests(unittest.IsolatedAsyncioTestCase):
    """workflow_name truthfulness + experiment axis value correctness."""

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

    # ── workflow_name ────────────────────────────────────────────────────

    async def test_workflow_name_null_when_unknown(self):
        gen = self.repo.create_generation(
            workflow_id="wf_hash_123", created_at="2026-01-01T10:00:00.000+00:00",
        )
        resp = await self.client.get(f"/comfymodal/history-v2/generations/{gen.generation_id}")
        self.assertEqual(resp.status, 200)
        item = (await resp.json())["item"]
        self.assertEqual(item["workflow_id"], "wf_hash_123", "workflow_id preserved")
        self.assertIsNone(item["workflow_name"], "no name known → null, never the id")

        data = await self.client.get(
            "/comfymodal/history-v2/feed?kind=generation&limit=5"
        )
        body = await data.json()
        self.assertEqual(body["items"][0]["workflow_id"], "wf_hash_123")
        self.assertIsNone(body["items"][0]["workflow_name"])

    async def test_workflow_name_derived_from_snapshot(self):
        gen = self.repo.create_generation(
            workflow_id="wf_hash_456", created_at="2026-01-01T10:00:00.000+00:00",
        )
        self.repo.create_request_snapshot(
            workflow_json={"extra": {"workflow": {"name": "My Cool Flow"}}},
            generation_id=gen.generation_id,
        )
        resp = await self.client.get(f"/comfymodal/history-v2/generations/{gen.generation_id}")
        item = (await resp.json())["item"]
        self.assertEqual(item["workflow_name"], "My Cool Flow")
        self.assertEqual(item["workflow_id"], "wf_hash_456")

        data = await self.client.get(
            "/comfymodal/history-v2/feed?kind=generation&limit=5"
        )
        body = await data.json()
        self.assertEqual(body["items"][0]["workflow_name"], "My Cool Flow")
        self.assertEqual(body["items"][0]["workflow_id"], "wf_hash_456")

    async def test_workflow_name_does_not_leak_workflow_version(self):
        # workflow_version stays separate; name still null when unknown.
        gen = self.repo.create_generation(
            workflow_id="wf_hash_789", workflow_version_id="wv_2",
            created_at="2026-01-01T10:00:00.000+00:00",
        )
        resp = await self.client.get(f"/comfymodal/history-v2/generations/{gen.generation_id}")
        item = (await resp.json())["item"]
        self.assertEqual(item["workflow_version"], "wv_2")
        self.assertIsNone(item["workflow_name"])

    # ── Experiment axis values ───────────────────────────────────────────

    async def test_cell_axis_exposes_values_not_names(self):
        exp = self.repo.create_experiment(
            name="grid", created_at="2026-01-01T10:00:00.000+00:00",
            cells=[
                {"axis_labels": {"Model": "SDXL", "Steps": 8}},
                {"axis_labels": {"Model": "SD1.5", "Steps": 8}},
            ],
        )
        exp_id = exp.experiment.experiment_id
        resp = await self.client.get(f"/comfymodal/history-v2/experiments/{exp_id}")
        self.assertEqual(resp.status, 200)
        item = (await resp.json())["item"]

        # Item-level axis labels remain the NAMES (frontend matrix headers).
        self.assertEqual(item["axis_labels"], {"x": "Model", "y": "Steps"})

        cells = item["cells"]
        self.assertEqual(cells[0]["axis"], {"x": "SDXL", "y": "8"},
                         "cell axis must carry the selected axis VALUES")
        self.assertEqual(cells[1]["axis"], {"x": "SD1.5", "y": "8"})
        # Per-cell axis label names preserved alongside the values.
        self.assertEqual(cells[0]["axis_labels"], {"x": "Model", "y": "Steps"})

    async def test_cell_axis_single_axis_and_missing_values(self):
        exp = self.repo.create_experiment(
            name="single", created_at="2026-01-01T10:00:00.000+00:00",
            cells=[
                {"axis_labels": {"seed": 7}},
                {"axis_labels": {}},
            ],
        )
        exp_id = exp.experiment.experiment_id
        resp = await self.client.get(f"/comfymodal/history-v2/experiments/{exp_id}")
        item = (await resp.json())["item"]
        self.assertEqual(item["axis_labels"], {"x": "seed", "y": ""})
        cells = item["cells"]
        self.assertEqual(cells[0]["axis"], {"x": "7", "y": ""})
        self.assertEqual(cells[1]["axis"], {"x": "", "y": ""})

    async def test_experiment_feed_item_axis_labels_names_only(self):
        exp = self.repo.create_experiment(
            name="feed", created_at="2026-01-01T10:00:00.000+00:00",
            cells=[{"axis_labels": {"seed": 1, "cfg": 7}}],
        )
        data = await self.client.get("/comfymodal/history-v2/feed?kind=experiment&limit=5")
        body = await data.json()
        self.assertEqual(body["items"][0]["axis_labels"], {"x": "seed", "y": "cfg"})


if __name__ == "__main__":
    unittest.main()
