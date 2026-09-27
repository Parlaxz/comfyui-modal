"""F5 backend-truth tests: replay-capability projection + Experiment favorite filter.

Offline coverage closing the two backend truth gaps left open after F2A:

* Generation detail, generation feed items, and Experiment cell-generation
  payloads project ``replay_capable`` (+ stable machine-readable
  ``replay_unavailable_reason`` when false) derived from the CANONICAL replay
  validator (``load_replay_plan``).  Projection is informational only: actual
  POST action routes re-validate independently and stay fail-closed, and
  projection performs zero writes.
* The feed ``favorite`` filter now applies to the Experiment stream INSIDE the
  SQL query (mirroring generations), so mixed favorites-only keyset/mixed
  pagination stays truthful and composes with search/date filters.

No Modal, no deploy, no GPU, no live generation, no commits.
"""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock
from urllib.parse import quote

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import history_v2_replay as hvr
from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
from history_v2_replay import (
    CODE_GENERATION_NOT_REPRODUCIBLE,
    CODE_RESUME_NOT_AVAILABLE,
    GenerateOriginalService,
)
from history_v2_repository import HistoryV2Repository
from history_v2_routes import register_history_v2_routes
from history_v2_store import HistoryV2Store


# ── Shared immutable-plan fixtures (same shape the E3B2/F1A suites use) ──


def _build_plan(
    *, output_mode: str = "original", workspace_id: str | None = "ws_frozen"
) -> tuple[ExecutionPlan, dict[str, Any]]:
    workflow = {
        "1": {
            "class_type": "KSampler",
            "inputs": {"seed": 0, "steps": 0, "cfg": 0.0},
        },
        "7": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
    }
    conversion = (
        {
            "format": "webp_lossy",
            "quality": 70,
            "webp_lossless_compression": "fast",
        }
        if output_mode == "preview"
        else {"format": "webp", "quality": 70}
    )
    options = ExecutionOptions(
        production_enabled=True,
        production_output_node_ids=("7",),
        output_conversion_options=conversion,
        result_route="history-v2",
        profiling_level="detailed",
        requested_backend="modal",
        cancellation_options={"grace_seconds": 0},
        progress_options={"events": False},
        compatibility_flags={"legacy_mode": False},
        legacy_passthrough={"future_option": {"enabled": True}},
        output_mode=output_mode,
    )
    metadata: dict[str, Any] = {
        "workflow_id": "wf_frozen",
        "workflow_version_id": "wv_frozen",
        "preset_id": "preset_frozen",
        "prompt_id": "initial-prompt",
        "studio_controls": {
            "seed": 0,
            "steps": 0,
            "cfg": 0.0,
            "enabled": False,
            "custom_control": "preserved",
        },
    }
    if workspace_id is not None:
        metadata["workspace_id"] = workspace_id
    plan = ExecutionPlan(
        schema_version=1,
        workflow=workflow,
        workflow_hash="executed-workflow-hash",
        source_workflow_hash="source-workflow-hash",
        production_report={"enabled": True, "output_node_ids": ["7"]},
        model_stack={"checkpoint": "frozen.safetensors"},
        prompt_bundle={"prompt": "immutable prompt", "negative_prompt": "none"},
        output_node_ids=("7",),
        input_images={"reference.png": "base64:reference"},
        execution_options=options,
        request_metadata=metadata,
        validation={"schema_version": 1, "validated": True, "certificate": "p"},
        deployment_identity={"app": "comfy", "revision": "deploy-1"},
    )
    return plan, plan.to_dict()


def _snapshot_payload(raw_plan: dict[str, Any], *, snapshot_id: str = "snap_x") -> dict[str, Any]:
    return {
        "snapshot_id": snapshot_id,
        "schema_version": 1,
        "workflow": copy.deepcopy(raw_plan["workflow"]),
        "workflow_hash": raw_plan["workflow_hash"],
        "workflow_version_id": "wv_frozen",
        "request": {
            "workflow_id": "wf_frozen",
            "workflow_version_id": "wv_frozen",
            "preset_id": "preset_frozen",
            "controls": {"seed": 0, "enabled": False},
            "workflow_hash": raw_plan["workflow_hash"],
            "source_workflow_hash": raw_plan["source_workflow_hash"],
        },
        "preset_snapshot": {
            "preset_id": "preset_frozen",
            "preset_name": "Frozen Preset",
            "merged_values": {"seed": 0},
        },
        "generation_params": {
            "workflow_id": "wf_frozen",
            "workflow_version_id": "wv_frozen",
            "preset_id": "preset_frozen",
            "controls": {"seed": 0},
        },
        "execution_plan": copy.deepcopy(raw_plan),
        "deployment_identity": copy.deepcopy(raw_plan["deployment_identity"]),
    }


def _persist_snapshot(
    repo: HistoryV2Repository,
    generation_id: str,
    raw_plan: dict[str, Any],
    *,
    snapshot_id: str = "snap_x",
) -> None:
    payload = _snapshot_payload(raw_plan, snapshot_id=snapshot_id)
    repo.create_request_snapshot(
        generation_id=generation_id,
        workflow_json=payload["workflow"],
        workflow_hash=payload["workflow_hash"],
        workflow_version_id=payload["workflow_version_id"],
        preset_snapshot=payload["preset_snapshot"],
        generation_params=payload["generation_params"],
        request=payload["request"],
        execution_plan=payload["execution_plan"],
        deployment_identity=payload["deployment_identity"],
    )


def _seed_single(
    repo: HistoryV2Repository,
    *,
    mode: str = "original",
    status: str = "completed",
    with_snapshot: bool = True,
    workspace_id: str | None = "ws_frozen",
):
    plan, raw_plan = _build_plan(output_mode=mode, workspace_id=workspace_id)
    generation = repo.create_generation(
        workflow_id="wf_frozen",
        workflow_version_id="wv_frozen",
        preset_id="preset_frozen",
        preset_name="Frozen Preset",
    )
    if with_snapshot:
        _persist_snapshot(repo, generation.generation_id, raw_plan)
    attempt = repo.add_attempt(generation.generation_id, mode=mode)
    if status in {"completed", "failed", "canceled", "interrupted"}:
        repo.update_attempt_terminal(attempt.run_id, status=status)
    return generation, attempt, plan, raw_plan


def _cell_spec(raw_plan: dict[str, Any] | None, cell_id: str) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "cell_id": cell_id,
        "axis_values": {"seed": 0},
        "controls": {"seed": 0},
        "merged_values": {"seed": 0},
        "axis_to_control": {"seed": "seed"},
        "workflow_id": "wf_frozen",
        "workflow_version_id": "wv_frozen",
        "preset_id": "preset_frozen",
        "preset_name": "Frozen Preset",
        "workflow_name": "Frozen Workflow",
    }
    if raw_plan is not None:
        spec["plan_hash"] = f"h_{cell_id}"
        spec["workflow_hash"] = raw_plan["workflow_hash"]
        spec["execution_plan"] = copy.deepcopy(raw_plan)
    return spec


class _FakeExecutor:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.plans: list[ExecutionPlan] = []
        self.calls = 0

    async def __call__(self, plan: ExecutionPlan, *, transport: Any = None) -> dict[str, Any]:
        self.calls += 1
        self.plans.append(plan)
        return {"status": "ok", "trace": {}}


def _fake_materializer(output_dir: Path):
    async def materialize(result, plan, prompt_id):
        return []

    return materialize


# ── Replay-capability projection ─────────────────────────────────────────


class ReplayCapabilityProjectionTests(unittest.IsolatedAsyncioTestCase):
    """F5 §1-§6: truthful pre-click replay-capability projection."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.output_dir = self.root / "studio_outputs"
        self.repo = HistoryV2Repository(
            HistoryV2Store(self.root / ".studio_history_v2" / "history_v2.db")
        )
        self.executor = _FakeExecutor(self.output_dir)
        self.workspace: dict[str, Any] | None = {"id": "ws_test"}
        workspace_patch = mock.patch.object(
            hvr,
            "_resolve_replay_workspace",
            side_effect=lambda plan: self.workspace,
        )
        workspace_patch.start()
        self.addCleanup(workspace_patch.stop)
        self.service_kwargs: dict[str, Any] = {}

    async def asyncSetUp(self) -> None:
        app = web.Application()
        register_history_v2_routes(
            app.router,
            self.root,
            generate_original_service_factory=self._make_service,
        )
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    def _make_service(self, repo: HistoryV2Repository) -> GenerateOriginalService:
        kwargs = dict(self.service_kwargs)
        kwargs.setdefault("data_root", self.root)
        kwargs.setdefault("transport_factory", lambda: object())
        kwargs.setdefault("executor", self.executor)
        kwargs.setdefault("materializer", _fake_materializer(self.output_dir))
        return GenerateOriginalService(repo, **kwargs)

    async def _detail(self, generation_id: str) -> dict[str, Any]:
        resp = await self.client.get(
            f"/comfymodal/history-v2/generations/{generation_id}"
        )
        self.assertEqual(resp.status, 200)
        body = await resp.json()
        return body["item"]

    async def _feed_items(self, **params: Any) -> list[dict[str, Any]]:
        url = "/comfymodal/history-v2/feed?"
        url += "&".join(f"{k}={v}" for k, v in params.items())
        resp = await self.client.get(url)
        self.assertEqual(resp.status, 200, url)
        return (await resp.json())["items"]

    # ── modern Singles project true across eligible statuses ─────────────

    async def test_modern_completed_single_projects_replay_capable_true(self):
        generation, _attempt, _plan, _raw = _seed_single(
            self.repo, status="completed"
        )
        item = await self._detail(generation.generation_id)
        self.assertTrue(item["replay_capable"])
        self.assertNotIn("replay_unavailable_reason", item)

        feed_items = await self._feed_items(kind="generation")
        self.assertEqual(len(feed_items), 1)
        self.assertTrue(feed_items[0]["replay_capable"])
        self.assertNotIn("replay_unavailable_reason", feed_items[0])

    async def test_modern_failed_single_projects_replay_capable_true(self):
        generation, _attempt, _plan, _raw = _seed_single(self.repo, status="failed")
        item = await self._detail(generation.generation_id)
        self.assertTrue(item["replay_capable"])

    async def test_modern_interrupted_single_projects_replay_capable_true(self):
        generation, _attempt, _plan, _raw = _seed_single(
            self.repo, status="interrupted"
        )
        item = await self._detail(generation.generation_id)
        self.assertTrue(item["replay_capable"])

    # ── legacy / incomplete records project false with stable reasons ────

    async def test_legacy_row_without_snapshot_projects_false(self):
        generation, attempt, _plan, _raw = _seed_single(
            self.repo, with_snapshot=False
        )
        self.repo.update_attempt_terminal(attempt.run_id, status="completed")
        item = await self._detail(generation.generation_id)
        self.assertFalse(item["replay_capable"])
        self.assertEqual(
            item["replay_unavailable_reason"], "missing_request_snapshot"
        )

    async def test_legacy_empty_execution_plan_projects_false(self):
        generation, _attempt, _plan, _raw = _seed_single(
            self.repo, with_snapshot=False
        )
        payload = _snapshot_payload(_raw)
        payload["execution_plan"] = {}
        self.repo.create_request_snapshot(
            generation_id=generation.generation_id,
            workflow_json=payload["workflow"],
            workflow_hash=payload["workflow_hash"],
            workflow_version_id=payload["workflow_version_id"],
            preset_snapshot=payload["preset_snapshot"],
            generation_params=payload["generation_params"],
            request=payload["request"],
            execution_plan=payload["execution_plan"],
            deployment_identity=payload["deployment_identity"],
        )
        item = await self._detail(generation.generation_id)
        self.assertFalse(item["replay_capable"])
        self.assertEqual(item["replay_unavailable_reason"], "missing_execution_plan")

    async def test_malformed_saved_plan_projects_false_with_stable_reason(self):
        _plan, raw = _build_plan()
        generation = self.repo.create_generation(
            workflow_id="wf_frozen",
            workflow_version_id="wv_frozen",
            preset_id="preset_frozen",
        )
        payload = _snapshot_payload(raw, snapshot_id="snap_tampered")
        tampered = copy.deepcopy(raw)
        tampered["workflow_hash"] = "rewritten-after-save"
        payload["execution_plan"] = tampered
        self.repo.create_request_snapshot(
            generation_id=generation.generation_id,
            workflow_json=payload["workflow"],
            workflow_hash=payload["workflow_hash"],
            workflow_version_id=payload["workflow_version_id"],
            preset_snapshot=payload["preset_snapshot"],
            generation_params=payload["generation_params"],
            request=payload["request"],
            execution_plan=payload["execution_plan"],
            deployment_identity=payload["deployment_identity"],
        )
        item = await self._detail(generation.generation_id)
        self.assertFalse(item["replay_capable"])
        self.assertEqual(item["replay_unavailable_reason"], "snapshot_hash_mismatch")

    async def test_missing_deployment_identity_projects_false(self):
        _plan, raw = _build_plan()
        generation = self.repo.create_generation(
            workflow_id="wf_frozen",
            workflow_version_id="wv_frozen",
            preset_id="preset_frozen",
        )
        payload = _snapshot_payload(raw, snapshot_id="snap_nodeploy")
        payload["execution_plan"]["deployment_identity"] = {}
        payload["deployment_identity"] = {}
        self.repo.create_request_snapshot(
            generation_id=generation.generation_id,
            workflow_json=payload["workflow"],
            workflow_hash=payload["workflow_hash"],
            workflow_version_id=payload["workflow_version_id"],
            preset_snapshot=payload["preset_snapshot"],
            generation_params=payload["generation_params"],
            request=payload["request"],
            execution_plan=payload["execution_plan"],
            deployment_identity=payload["deployment_identity"],
        )
        item = await self._detail(generation.generation_id)
        self.assertFalse(item["replay_capable"])
        self.assertEqual(
            item["replay_unavailable_reason"], "missing_deployment_identity"
        )

    async def test_unknown_saved_workspace_still_projects_capability_truthfully(
        self,
    ):
        """Capability means immutable-request reproducibility, NOT credential
        availability: an explicitly saved unknown workspace keeps
        replay_capable=true while dispatch/workspace preflight remains the
        POST-time gate.  No workspace identifiers or credentials leak through
        the projected capability fields themselves."""
        generation, _attempt, _plan, _raw = _seed_single(
            self.repo, workspace_id="ws_unknown_nonexistent"
        )
        item = await self._detail(generation.generation_id)
        self.assertTrue(item["replay_capable"])
        self.assertNotIn("replay_unavailable_reason", item)

    # ── capability ≠ action eligibility (F5 §4) ──────────────────────────

    async def test_completed_single_is_replay_capable_but_not_resumable(self):
        generation, attempt, _plan, _raw = _seed_single(
            self.repo, status="completed"
        )
        item = await self._detail(generation.generation_id)
        self.assertTrue(item["replay_capable"])
        self.assertEqual(item["status"], "completed")

        resp = await self.client.post(
            f"/comfymodal/history-v2/generations/{generation.generation_id}/resume"
        )
        body = await resp.json()
        self.assertEqual(resp.status, 409)
        self.assertEqual(body["code"], CODE_RESUME_NOT_AVAILABLE)
        detail = self.repo.get_generation(generation.generation_id)
        assert detail is not None
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].run_id, attempt.run_id)

    # ── projection is read-only and cannot authorize actions ─────────────

    def _table_dump(self) -> list[list[list[tuple[str, str]]]]:
        dump: list[list[list[tuple[str, str]]]] = []
        conn = self.repo._store.connect()
        try:
            for table in ("generations", "run_attempts", "request_snapshots"):
                rows = conn.execute(
                    f"SELECT * FROM {table} ORDER BY 1 ASC"
                ).fetchall()
                dump.append(
                    [
                        [(key, repr(row[key])) for key in row.keys()]
                        for row in rows
                    ]
                )
        finally:
            conn.close()
        return dump

    async def test_projection_performs_no_writes(self):
        generation, _attempt, _plan, _raw = _seed_single(
            self.repo, status="completed"
        )
        before = self._table_dump()

        await self._detail(generation.generation_id)
        await self._feed_items(kind="mixed")

        self.assertEqual(self._table_dump(), before)

    async def test_projection_cannot_make_invalid_post_action_succeed(self):
        generation, attempt, _plan, _raw = _seed_single(
            self.repo, with_snapshot=False
        )
        item = await self._detail(generation.generation_id)
        self.assertFalse(item["replay_capable"])

        resp = await self.client.post(
            f"/comfymodal/history-v2/generations/{generation.generation_id}/original"
        )
        body = await resp.json()
        self.assertEqual(resp.status, 409)
        self.assertEqual(body["code"], CODE_GENERATION_NOT_REPRODUCIBLE)
        detail = self.repo.get_generation(generation.generation_id)
        assert detail is not None
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "completed")

    # ── Experiment cell payloads agree with the Single projection (§5) ───

    async def test_experiment_cell_payload_matches_single_projection(self):
        plan, raw = _build_plan()
        detail = self.repo.create_modern_matrix(
            experiment_id="exp_f5_parity",
            name="Parity",
            definition={
                "version": 2,
                "contract": "modern_v2",
                "cells": [_cell_spec(raw, "cell_ok"), _cell_spec(None, "cell_bare")],
            },
            cells=[_cell_spec(raw, "cell_ok"), _cell_spec(None, "cell_bare")],
        )
        ok_gid = detail.cells[0].generation_id
        bare_gid = detail.cells[1].generation_id
        assert ok_gid is not None and bare_gid is not None

        resp = await self.client.get(
            f"/comfymodal/history-v2/experiments/exp_f5_parity"
        )
        self.assertEqual(resp.status, 200)
        exp_item = (await resp.json())["item"]
        cells_by_gid = {
            c["generation_id"]: c.get("generation") for c in exp_item["cells"]
        }
        ok_cell = cells_by_gid[ok_gid]
        bare_cell = cells_by_gid[bare_gid]

        ok_detail = await self._detail(ok_gid)
        bare_detail = await self._detail(bare_gid)

        self.assertTrue(ok_cell["replay_capable"])
        self.assertTrue(ok_detail["replay_capable"])
        self.assertFalse(bare_cell["replay_capable"])
        self.assertFalse(bare_detail["replay_capable"])
        self.assertEqual(
            bare_cell["replay_unavailable_reason"],
            bare_detail["replay_unavailable_reason"],
        )


# ── Experiment favorite filter ───────────────────────────────────────────


class ExperimentFavoriteFilterRepositoryTests(unittest.TestCase):
    """F5 §7/§10: repository-level filter semantics and composition."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = HistoryV2Store(Path(tmp.name) / ".studio_history_v2" / "history_v2.db")
        self.repo = HistoryV2Repository(self.store)

    def _exp(self, name: str, created: str, favorite: bool = False):
        detail = self.repo.create_experiment(name=name, cells=[{}], created_at=created)
        if favorite:
            self.assertTrue(
                self.repo.set_experiment_favorite(detail.experiment.experiment_id, True)
            )
        return detail.experiment.experiment_id

    def test_favorite_true_false_and_none_semantics(self):
        fav = self._exp("fav", "2026-01-01T10:00:00.000+00:00", favorite=True)
        unfav = self._exp("unfav", "2026-01-01T11:00:00.000+00:00")

        result = self.repo.query_experiments(favorite=True)
        self.assertEqual([i["experiment_id"] for i in result["items"]], [fav])
        self.assertEqual(result["total"], 1)

        result = self.repo.query_experiments(favorite=False)
        self.assertEqual([i["experiment_id"] for i in result["items"]], [unfav])
        self.assertEqual(result["total"], 1)

        result = self.repo.query_experiments()
        self.assertEqual(result["total"], 2)

    def test_favorite_composes_with_search_date_and_order(self):
        a = self._exp("Alpha Matrix", "2026-01-01T10:00:00.000+00:00", favorite=True)
        self._exp("Beta Matrix", "2026-01-02T10:00:00.000+00:00", favorite=True)
        self._exp("Alpha Unfavorited", "2026-01-03T10:00:00.000+00:00")

        result = self.repo.query_experiments(favorite=True, search="Alpha")
        self.assertEqual(
            [i["experiment_id"] for i in result["items"]], [a]
        )

        result = self.repo.query_experiments(
            favorite=True,
            date_from="2026-01-02T00:00:00.000+00:00",
            date_to="2026-01-02T23:59:59.000+00:00",
        )
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["name"], "Beta Matrix")

        result = self.repo.query_experiments(favorite=True, order="oldest")
        self.assertEqual(
            [i["created_at"] for i in result["items"]],
            sorted(i["created_at"] for i in result["items"]),
        )

    def test_favorite_filter_paginates_in_query_not_memory(self):
        for minute in range(6):
            self._exp(
                f"exp_{minute}",
                f"2026-01-01T10:{minute:02d}:00.000+00:00",
                favorite=(minute % 2 == 0),
            )
        seen: list[str] = []
        cursor: str | None = None
        while True:
            result = self.repo.query_experiments(
                favorite=True, limit=2, cursor=cursor
            )
            seen.extend(i["experiment_id"] for i in result["items"])
            cursor = result["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(len(seen), 3)
        self.assertEqual(len(set(seen)), 3)


class FavoriteFilterApiTests(unittest.IsolatedAsyncioTestCase):
    """F5 §7/§8/§14: end-to-end feed filtering across kinds and pages."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = HistoryV2Repository(
            HistoryV2Store(self.root / ".studio_history_v2" / "history_v2.db")
        )

    async def asyncSetUp(self) -> None:
        app = web.Application()
        register_history_v2_routes(app.router, self.root)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    def _gen(self, prompt: str, created: str, favorite: bool = False) -> str:
        gen = self.repo.create_generation(prompt_text=prompt, created_at=created)
        attempt = self.repo.add_attempt(gen.generation_id, mode="preview")
        self.repo.update_attempt_terminal(attempt.run_id, status="completed")
        if favorite:
            self.assertTrue(self.repo.set_favorite(gen.generation_id, True))
        return gen.generation_id

    def _exp(self, name: str, created: str, favorite: bool = False) -> str:
        detail = self.repo.create_experiment(name=name, cells=[{}], created_at=created)
        if favorite:
            self.assertTrue(
                self.repo.set_experiment_favorite(detail.experiment.experiment_id, True)
            )
        return detail.experiment.experiment_id

    async def _feed(self, kind: str = "mixed", **params: Any) -> dict[str, Any]:
        url = f"/comfymodal/history-v2/feed?kind={kind}"
        for key, value in params.items():
            url += f"&{key}={value}"
        resp = await self.client.get(url)
        self.assertEqual(resp.status, 200, url)
        return await resp.json()

    async def test_generation_only_favorite_true(self):
        fav = self._gen("fav gen", "2026-01-01T10:00:00.000+00:00", favorite=True)
        self._gen("unfav gen", "2026-01-01T11:00:00.000+00:00")
        data = await self._feed("generation", favorite="true")
        self.assertEqual(data["total"], 1)
        self.assertEqual([i["id"] for i in data["items"]], [fav])

    async def test_experiment_only_favorite_true(self):
        fav = self._exp("fav exp", "2026-01-01T10:00:00.000+00:00", favorite=True)
        self._exp("unfav exp", "2026-01-01T11:00:00.000+00:00")
        data = await self._feed("experiment", favorite="true")
        self.assertEqual(data["total"], 1)
        self.assertEqual([i["id"] for i in data["items"]], [fav])

    async def test_mixed_favorite_true_filters_both_streams(self):
        fav_g = self._gen("fav gen", "2026-01-01T10:00:00.000+00:00", favorite=True)
        fav_e = self._exp("fav exp", "2026-01-01T11:00:00.000+00:00", favorite=True)
        self._gen("unfav gen", "2026-01-01T12:00:00.000+00:00")
        self._exp("unfav exp", "2026-01-01T13:00:00.000+00:00")
        data = await self._feed("mixed", favorite="true")
        self.assertEqual(data["total"], 2)
        kinds = {(i["kind"], i["id"]) for i in data["items"]}
        self.assertEqual(kinds, {("generation", fav_g), ("experiment", fav_e)})

    async def test_mixed_favorite_generation_favorited_experiment_not(self):
        fav_g = self._gen("g1", "2026-01-01T10:00:00.000+00:00", favorite=True)
        unfav_e = self._exp("e1", "2026-01-01T11:00:00.000+00:00")
        data = await self._feed("mixed", favorite="true")
        self.assertEqual(
            [(i["kind"], i["id"]) for i in data["items"]], [("generation", fav_g)]
        )
        self.assertNotIn(unfav_e, [i["id"] for i in data["items"]])

    async def test_mixed_favorite_experiment_favorited_generation_not(self):
        unfav_g = self._gen("g2", "2026-01-01T10:00:00.000+00:00")
        fav_e = self._exp("e2", "2026-01-01T11:00:00.000+00:00", favorite=True)
        data = await self._feed("mixed", favorite="true")
        self.assertEqual(
            [(i["kind"], i["id"]) for i in data["items"]], [("experiment", fav_e)]
        )
        self.assertNotIn(unfav_g, [i["id"] for i in data["items"]])

    async def test_mixed_favorite_both_favorited(self):
        fav_g = self._gen("g3", "2026-01-01T10:00:00.000+00:00", favorite=True)
        fav_e = self._exp("e3", "2026-01-01T11:00:00.000+00:00", favorite=True)
        data = await self._feed("mixed", favorite="true")
        self.assertEqual(
            {(i["kind"], i["id"]) for i in data["items"]},
            {("generation", fav_g), ("experiment", fav_e)},
        )

    async def test_mixed_favorite_neither_favorited(self):
        self._gen("g4", "2026-01-01T10:00:00.000+00:00")
        self._exp("e4", "2026-01-01T11:00:00.000+00:00")
        data = await self._feed("mixed", favorite="true")
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["items"], [])
        self.assertIsNone(data["next_cursor"])

    async def test_mixed_favorite_pagination_no_leak_across_pages(self):
        favorited: set[str] = set()
        # Interleave 8 generations and 8 experiments by timestamp; even ones
        # favorited.  Unfavorited EXPERIMENTS must never appear on any page.
        for minute in range(8):
            ts = f"2026-01-01T10:{minute:02d}:00.000+00:00"
            gid = self._gen(f"g{minute}", ts, favorite=(minute % 2 == 0))
            eid = self._exp(f"e{minute}", ts.replace("10:", "11:"), favorite=(minute % 2 == 0))
            if minute % 2 == 0:
                favorited.add(gid)
                favorited.add(eid)

        collected: list[dict[str, Any]] = []
        cursor: str | None = None
        pages = 0
        while True:
            params: dict[str, Any] = {"favorite": "true", "limit": 3}
            if cursor is not None:
                params["cursor"] = quote(cursor)
            data = await self._feed("mixed", **params)
            collected.extend(data["items"])
            pages += 1
            cursor = data["next_cursor"]
            if cursor is None:
                break
        self.assertGreaterEqual(pages, 3)
        ids = [i["id"] for i in collected]
        self.assertEqual(sorted(ids), sorted(favorited))
        self.assertEqual(len(ids), len(set(ids)), "no duplicates across pages")
        for item in collected:
            self.assertTrue(item["favorite"])

    async def test_explicit_favorite_false_returns_truthful_inverse(self):
        fav_e = self._exp("fav", "2026-01-01T10:00:00.000+00:00", favorite=True)
        unfav_e = self._exp("unfav", "2026-01-01T11:00:00.000+00:00")
        data = await self._feed("experiment", favorite="false")
        self.assertEqual(data["total"], 1)
        self.assertEqual([i["id"] for i in data["items"]], [unfav_e])
        self.assertNotIn(fav_e, [i["id"] for i in data["items"]])

    async def test_favorite_composes_with_search(self):
        kept = self._exp("Kept Alpha", "2026-01-01T10:00:00.000+00:00", favorite=True)
        self._exp("Dropped Alpha", "2026-01-01T11:00:00.000+00:00")
        self._exp("Kept Beta", "2026-01-01T12:00:00.000+00:00", favorite=True)
        data = await self._feed(
            "experiment", favorite="true", search=quote("Alpha")
        )
        self.assertEqual(data["total"], 1)
        self.assertEqual([i["id"] for i in data["items"]], [kept])

    async def test_favorite_composes_with_date_range(self):
        inside = self._exp("inside", "2026-01-02T10:00:00.000+00:00", favorite=True)
        self._exp("early", "2026-01-01T10:00:00.000+00:00", favorite=True)
        self._exp("late-unfav", "2026-01-03T10:00:00.000+00:00")
        data = await self._feed(
            "experiment",
            favorite="true",
            date_from="2026-01-02T00:00:00.000+00:00",
            date_to="2026-01-02T23:59:59.000+00:00",
        )
        self.assertEqual(data["total"], 1)
        self.assertEqual([i["id"] for i in data["items"]], [inside])

    async def test_no_favorite_param_preserves_existing_behavior(self):
        self._gen("g", "2026-01-01T10:00:00.000+00:00", favorite=True)
        self._gen("g2", "2026-01-01T11:00:00.000+00:00")
        self._exp("e", "2026-01-01T12:00:00.000+00:00", favorite=True)
        self._exp("e2", "2026-01-01T13:00:00.000+00:00")
        data = await self._feed("mixed")
        self.assertEqual(data["total"], 4)
        self.assertEqual({i["kind"] for i in data["items"]}, {"generation", "experiment"})
        created = [i["created_at"] for i in data["items"]]
        self.assertEqual(created, sorted(created, reverse=True))


class ExperimentFavoriteIndexTests(unittest.TestCase):
    """F5 §11: idempotent favorite index, including the legacy-upgrade path."""

    def test_index_exists_and_initialize_is_idempotent(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = HistoryV2Store(Path(tmp.name) / ".studio_history_v2" / "history_v2.db")
        store.initialize()
        store.initialize()
        self.assertIn("idx_experiments_favorite", self._index_names(store, "experiments"))
        self.assertIn("idx_generations_favorite", self._index_names(store, "generations"))

    def test_legacy_db_without_columns_upgrades_and_creates_index(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db_path = Path(tmp.name) / ".studio_history_v2" / "history_v2.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = __import__("sqlite3").connect(str(db_path))
        try:
            conn.execute(
                "CREATE TABLE experiments ("
                " experiment_id TEXT PRIMARY KEY, name TEXT,"
                " definition_json TEXT NOT NULL DEFAULT '{}',"
                " cell_ordering_json TEXT NOT NULL DEFAULT '[]',"
                " expected_cell_count INTEGER NOT NULL DEFAULT 0,"
                " status TEXT NOT NULL, created_at TEXT NOT NULL,"
                " updated_at TEXT NOT NULL)"
            )
            conn.commit()
        finally:
            conn.close()

        store = HistoryV2Store(db_path)
        store.initialize()
        self.assertIn(
            "idx_experiments_favorite", self._index_names(store, "experiments")
        )
        conn = store.connect()
        try:
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(experiments)").fetchall()
            }
        finally:
            conn.close()
        self.assertIn("favorite", cols)
        self.assertIn("note", cols)

    @staticmethod
    def _index_names(store: HistoryV2Store, table: str) -> set[str]:
        conn = store.connect()
        try:
            rows = conn.execute(f"PRAGMA index_list('{table}')").fetchall()
            return {row["name"] for row in rows}
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
