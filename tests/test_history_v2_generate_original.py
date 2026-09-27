"""E3B2 production Generate Original backend tests.

Offline coverage for the Generation-scoped Generate Original action:

* transactional duplicate/busy/success/retry/rerender decisions;
* immutable snapshot replay (capability, raw-hash fail-closed, exact delta);
* Single dispatch through the canonical executor seam with required-output
  persistence BEFORE the terminal ``completed`` write;
* Experiment-cell dispatch through the SAME service and the existing modern
  scheduler binding (no second engine);
* no-scheduler truthfulness (no orphan queued Attempt);
* failure/retry append-only semantics and E1B winner projection.

No Modal, no deployment, no live generation, no GPU work.
"""
from __future__ import annotations

import asyncio
import base64
import copy
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from history_v2_models import RunAttempt
from history_v2_repository import HistoryV2Repository
from history_v2_replay import (
    CODE_DISPATCH_UNAVAILABLE,
    CODE_GENERATION_BUSY,
    CODE_GENERATION_NOT_REPRODUCIBLE,
    CODE_ORIGINAL_ALREADY_ACTIVE,
    CODE_ORIGINAL_ALREADY_COMPLETED,
    CODE_ORIGINAL_CREATED,
    CODE_RETRY_NOT_AVAILABLE,
    CODE_RETRY_REQUIRED,
    GenerateOriginalService,
    validate_replay_delta,
)
from history_v2_routes import (
    _build_outputs,
    _original_projection,
    register_history_v2_routes,
)
from history_v2_store import HistoryV2Store
from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan


def _png_bytes() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )


def _build_plan(*, output_mode: str = "original") -> tuple[ExecutionPlan, dict]:
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
        request_metadata={
            "workflow_id": "wf_frozen",
            "workflow_version_id": "wv_frozen",
            "preset_id": "preset_frozen",
            "prompt_id": "preview-prompt",
            "studio_controls": {
                "seed": 0,
                "steps": 0,
                "cfg": 0.0,
                "enabled": False,
                "custom_control": "preserved",
            },
        },
        validation={"schema_version": 1, "validated": True, "certificate": "p"},
        deployment_identity={"app": "comfy", "revision": "deploy-1"},
    )
    return plan, plan.to_dict()


def _snapshot_payload(raw_plan: dict, *, snapshot_id: str = "snap_x") -> dict:
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


class FakeExecutor:
    """Offline canonical-executor seam recording every executed plan."""

    def __init__(self, *, error: str | None = None, output_dir: Path | None = None):
        self.plans: list[ExecutionPlan] = []
        self.error = error
        self.output_dir = output_dir
        self.calls = 0
        self.gate: asyncio.Event | None = None

    async def __call__(self, plan, *, transport=None):
        self.calls += 1
        self.plans.append(plan)
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise RuntimeError(self.error)
        result: dict = {"status": "ok", "trace": {}}
        if self.output_dir is not None:
            name = f"orig-{self.calls}.png"
            path = self.output_dir / name
            path.write_bytes(_png_bytes())
            result["outputs"] = {name: {"data": ""}}
            result["asset_descriptors"] = [
                {
                    "node_id": "7",
                    "output_key": "images",
                    "output_index": 0,
                    "filename": name,
                    "mime_type": "image/png",
                }
            ]
        return result


def _fake_materializer(output_dir: Path):
    async def materialize(result, plan, prompt_id):
        # Real file writes are performed by FakeExecutor; this seam only
        # mirrors the PlaygroundService materialization contract.
        return [str(path) for path in sorted(output_dir.glob("orig-*.png"))]

    return materialize


class FakeScheduler:
    def __init__(self) -> None:
        self.submitted: list[dict] = []

    async def submit_cell(self, plan) -> None:
        self.submitted.append(dict(plan))


# ── Repository: transactional decision semantics ──────────────────────────


class ClaimOriginalRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_root = Path(self._tmp.name)
        self.repo = HistoryV2Repository(
            HistoryV2Store(self.data_root / ".studio_history_v2" / "history_v2.db")
        )
        self.plan, self.raw_plan = _build_plan()
        self.gen = self._replayable_generation()

    def _replayable_generation(self) -> Any:
        gen = self.repo.create_generation(
            workflow_id="wf_frozen",
            workflow_version_id="wv_frozen",
            preset_id="preset_frozen",
            preset_name="Frozen Preset",
        )
        payload = _snapshot_payload(self.raw_plan)
        self.repo.create_request_snapshot(
            generation_id=gen.generation_id,
            workflow_json=payload["workflow"],
            workflow_hash=payload["workflow_hash"],
            workflow_version_id=payload["workflow_version_id"],
            preset_snapshot=payload["preset_snapshot"],
            generation_params=payload["generation_params"],
            request=payload["request"],
            execution_plan=payload["execution_plan"],
            deployment_identity=payload["deployment_identity"],
        )
        return gen

    def _attempts(self, generation_id: str) -> list[RunAttempt]:
        detail = self.repo.get_generation(generation_id)
        assert detail is not None
        return list(detail.attempts)

    def test_preview_only_creates_one_queued_original(self):
        preview = self.repo.add_attempt(self.gen.generation_id, mode="preview")
        self.repo.update_attempt_terminal(preview.run_id, status="completed")
        outcome = self.repo.claim_or_reuse_original_attempt(self.gen.generation_id)
        assert outcome is not None
        self.assertEqual(outcome.outcome, "created")
        assert outcome.attempt is not None
        self.assertEqual(outcome.attempt.mode, "original")
        self.assertEqual(outcome.attempt.status, "queued")
        self.assertIsNone(outcome.attempt.started_at)
        self.assertEqual(outcome.attempt.generation_id, self.gen.generation_id)
        attempts = self._attempts(self.gen.generation_id)
        self.assertEqual(len(attempts), 2)

    def test_double_submit_returns_same_active_attempt(self):
        first = self.repo.claim_or_reuse_original_attempt(self.gen.generation_id)
        assert first is not None and first.attempt is not None
        second = self.repo.claim_or_reuse_original_attempt(self.gen.generation_id)
        assert second is not None
        self.assertEqual(first.outcome, "created")
        self.assertEqual(second.outcome, "reuse_active")
        assert second.attempt is not None
        self.assertEqual(second.attempt.run_id, first.attempt.run_id)
        self.assertEqual(len(self._attempts(self.gen.generation_id)), 1)

    def test_rerender_race_creates_exactly_one(self):
        first = self.repo.claim_or_reuse_original_attempt(
            self.gen.generation_id, explicit_rerender=True
        )
        second = self.repo.claim_or_reuse_original_attempt(
            self.gen.generation_id, explicit_rerender=True
        )
        assert first is not None and second is not None
        outcomes = sorted([first.outcome, second.outcome])
        self.assertEqual(outcomes, ["created", "reuse_active"])
        self.assertEqual(len(self._attempts(self.gen.generation_id)), 1)

    def test_successful_original_is_reused_without_new_attempt(self):
        attempt = self.repo.add_attempt(self.gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(attempt.run_id, status="completed")
        outcome = self.repo.claim_or_reuse_original_attempt(self.gen.generation_id)
        assert outcome is not None
        self.assertEqual(outcome.outcome, "reuse_successful")
        assert outcome.attempt is not None
        self.assertEqual(outcome.attempt.run_id, attempt.run_id)
        self.assertEqual(len(self._attempts(self.gen.generation_id)), 1)

    def test_failed_only_reports_retry_required(self):
        attempt = self.repo.add_attempt(self.gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(attempt.run_id, status="failed")
        outcome = self.repo.claim_or_reuse_original_attempt(self.gen.generation_id)
        assert outcome is not None
        self.assertEqual(outcome.outcome, "retry_required")
        assert outcome.attempt is not None
        self.assertEqual(outcome.attempt.run_id, attempt.run_id)
        self.assertEqual(len(self._attempts(self.gen.generation_id)), 1)

    def test_active_preview_is_busy(self):
        self.repo.add_attempt(self.gen.generation_id, mode="preview")
        outcome = self.repo.claim_or_reuse_original_attempt(self.gen.generation_id)
        assert outcome is not None
        self.assertEqual(outcome.outcome, "busy")
        self.assertEqual(len(self._attempts(self.gen.generation_id)), 1)

    def test_retry_creates_append_only_original_attempt(self):
        failed = self.repo.add_attempt(self.gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(failed.run_id, status="failed")
        outcome = self.repo.create_original_retry_attempt(self.gen.generation_id)
        assert outcome is not None and outcome.attempt is not None
        self.assertEqual(outcome.outcome, "created")
        self.assertEqual(outcome.attempt.mode, "original")
        self.assertEqual(outcome.attempt.status, "queued")
        attempts = self._attempts(self.gen.generation_id)
        self.assertEqual(len(attempts), 2)
        old = next(a for a in attempts if a.run_id == failed.run_id)
        self.assertEqual(old.status, "failed")

    def test_retry_is_busy_when_any_attempt_active(self):
        self.repo.add_attempt(self.gen.generation_id, mode="preview")
        outcome = self.repo.create_original_retry_attempt(self.gen.generation_id)
        assert outcome is not None
        self.assertEqual(outcome.outcome, "busy")

    def test_retry_rejects_preview_only_and_successful_originals(self):
        outcome = self.repo.create_original_retry_attempt(self.gen.generation_id)
        assert outcome is not None
        self.assertEqual(outcome.outcome, "not_retryable")
        attempt = self.repo.add_attempt(self.gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(attempt.run_id, status="completed")
        outcome = self.repo.create_original_retry_attempt(self.gen.generation_id)
        assert outcome is not None
        self.assertEqual(outcome.outcome, "not_retryable")

    def test_unknown_generation_returns_none(self):
        self.assertIsNone(self.repo.claim_or_reuse_original_attempt("gen_missing"))
        self.assertIsNone(self.repo.create_original_retry_attempt("gen_missing"))

    def test_cell_aware_creation_appends_to_experiment_cell(self):
        spec = {
            "cell_id": "cell_a",
            "axis_values": {"seed": 0},
            "controls": {"seed": 0},
            "merged_values": {"seed": 0},
            "axis_to_control": {"seed": "seed"},
            "workflow_id": "wf_frozen",
            "workflow_version_id": "wv_frozen",
            "preset_id": "preset_frozen",
            "preset_name": "Frozen Preset",
            "workflow_name": "Frozen Workflow",
            "plan_hash": "h_cell_a",
            "workflow_hash": self.raw_plan["workflow_hash"],
            "execution_plan": copy.deepcopy(self.raw_plan),
        }
        detail = self.repo.create_modern_matrix(
            experiment_id="exp_replay",
            name="Matrix",
            definition={"version": 2, "cells": [spec]},
            cells=[spec],
        )
        cell = detail.cells[0]
        assert cell.generation_id is not None
        gid = cell.generation_id
        current = self.repo.get_current_cell_attempt(cell.cell_id)
        assert current is not None
        self.repo.update_attempt_terminal(current.run_id, status="completed")
        outcome = self.repo.claim_or_reuse_original_attempt(
            gid, explicit_rerender=True
        )
        assert outcome is not None and outcome.attempt is not None
        self.assertEqual(outcome.outcome, "created")
        self.assertEqual(outcome.attempt.cell_id, cell.cell_id)
        refreshed = self.repo.get_experiment_cell(cell.cell_id)
        assert refreshed is not None
        self.assertIn(outcome.attempt.run_id, refreshed.attempt_ids)


# ── Route/service production behavior ─────────────────────────────────────


class GenerateOriginalRouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self._tmp.name)
        self.output_dir = self.data_root / "studio_outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.store = HistoryV2Store(
            self.data_root / ".studio_history_v2" / "history_v2.db"
        )
        self.repo = HistoryV2Repository(self.store)
        self.plan, self.raw_plan = _build_plan()
        self.executor = FakeExecutor(error=None, output_dir=self.output_dir)
        self.scheduler = FakeScheduler()
        self.service_kwargs: dict = {}

    async def asyncSetUp(self) -> None:
        self.app = web.Application()
        register_history_v2_routes(
            self.app.router,
            self.data_root,
            generate_original_service_factory=self._make_service,
        )
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    def _make_service(self, repo: HistoryV2Repository) -> GenerateOriginalService:
        kwargs = dict(self.service_kwargs)
        kwargs.setdefault("data_root", self.data_root)
        kwargs.setdefault("transport_factory", lambda: object())
        kwargs.setdefault("executor", self.executor)
        kwargs.setdefault(
            "materializer", _fake_materializer(self.output_dir)
        )
        kwargs.setdefault(
            "scheduler_getter", lambda experiment_id: self.scheduler
        )
        return GenerateOriginalService(repo, **kwargs)

    # ── fixtures ────────────────────────────────────────────────────────

    def _replayable_generation(self, *, with_completed_preview: bool = True):
        gen = self.repo.create_generation(
            workflow_id="wf_frozen",
            workflow_version_id="wv_frozen",
            preset_id="preset_frozen",
            preset_name="Frozen Preset",
        )
        payload = _snapshot_payload(self.raw_plan)
        self.repo.create_request_snapshot(
            generation_id=gen.generation_id,
            workflow_json=payload["workflow"],
            workflow_hash=payload["workflow_hash"],
            workflow_version_id=payload["workflow_version_id"],
            preset_snapshot=payload["preset_snapshot"],
            generation_params=payload["generation_params"],
            request=payload["request"],
            execution_plan=payload["execution_plan"],
            deployment_identity=payload["deployment_identity"],
        )
        if with_completed_preview:
            preview = self.repo.add_attempt(gen.generation_id, mode="preview")
            self.repo.update_attempt_terminal(preview.run_id, status="completed")
            preview_file = self.output_dir / "preview.png"
            preview_file.write_bytes(_png_bytes())
            self.repo.attach_asset(
                gen.generation_id,
                run_id=preview.run_id,
                asset_type="preview",
                source_path=str(preview_file),
                fmt="png",
            )
        return gen

    def _detail(self, generation_id: str):
        detail = self.repo.get_generation(generation_id)
        assert detail is not None
        return detail

    async def _wait_for_terminal(self, run_id: str, timeout: float = 5.0) -> str:
        deadline = time.time() + timeout
        status = ""
        while time.time() < deadline:
            attempt = self.repo.get_attempt(run_id)
            status = attempt.status if attempt else ""
            if status in {"completed", "failed", "canceled", "interrupted"}:
                return status
            await asyncio.sleep(0.02)
        return status

    async def _post(self, generation_id: str, body: dict | None = None, retry: bool = False):
        suffix = "/original/retry" if retry else "/original"
        response = await self.client.post(
            f"/comfymodal/history-v2/generations/{generation_id}{suffix}",
            json=body if body is not None else {},
        )
        self.assertIn(response.status, (200, 400, 404, 409, 503))
        return response.status, await response.json()

    # ── core production behavior ────────────────────────────────────────

    async def test_preview_only_generates_one_new_original_attempt(self):
        gen = self._replayable_generation()
        snapshot_before = self._detail(gen.generation_id).request_snapshot
        assert snapshot_before is not None
        before = snapshot_before.to_dict()

        status, body = await self._post(gen.generation_id)

        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["outcome"], CODE_ORIGINAL_CREATED)
        self.assertEqual(body["generation_id"], gen.generation_id)
        self.assertEqual(body["purpose"], "original")
        self.assertEqual(body["attempt_status"], "queued")
        self.assertFalse(body["reused"])
        self.assertEqual(body["executor"], "canonical_execution.execute_plan")

        detail = self._detail(gen.generation_id)
        self.assertEqual(detail.generation.generation_id, gen.generation_id)
        originals = [a for a in detail.attempts if a.mode == "original"]
        self.assertEqual(len(originals), 1)
        self.assertEqual(originals[0].run_id, body["run_id"])
        # The response froze the creation-time state as queued; the offline
        # executor may already have finished by the time we re-read.
        self.assertIn(originals[0].status, {"queued", "running", "completed"})

        final = await self._wait_for_terminal(body["run_id"])
        self.assertEqual(final, "completed")

        # Immutable snapshot untouched by the whole flow.
        snapshot_after = self._detail(gen.generation_id).request_snapshot
        assert snapshot_after is not None
        self.assertEqual(snapshot_after.to_dict(), before)

        # Replay delta: only output intent + correlation metadata differ.
        executed = self.executor.plans[-1]
        delta = validate_replay_delta(self.plan, executed)
        self.assertTrue(delta.allowed, delta.unexpected_paths)
        self.assertEqual(
            executed.execution_options.output_conversion_options,
            {"format": "original"},
        )
        self.assertEqual(executed.workflow, self.plan.workflow)
        self.assertEqual(executed.workflow_hash, self.plan.workflow_hash)
        self.assertEqual(
            executed.source_workflow_hash, self.plan.source_workflow_hash
        )
        self.assertEqual(executed.model_stack, self.plan.model_stack)
        self.assertEqual(executed.input_images, self.plan.input_images)
        self.assertEqual(executed.deployment_identity, self.plan.deployment_identity)
        self.assertEqual(
            executed.request_metadata["studio_controls"]["seed"], 0
        )
        self.assertEqual(
            executed.request_metadata["workflow_version_id"], "wv_frozen"
        )
        self.assertEqual(executed.request_metadata["preset_id"], "preset_frozen")

        # Required-output persistence happened before completion and the
        # logical_output_key survives into the E1B grouping surface.
        assets = self.repo.get_generation_assets(gen.generation_id)
        originals_assets = [a for a in assets if a.type == "original"]
        self.assertEqual(len(originals_assets), 1)
        self.assertEqual(originals_assets[0].run_id, body["run_id"])
        self.assertEqual(
            originals_assets[0].logical_output_key,
            "node:7:slot:images:item:0",
        )
        previews = [a for a in assets if a.type == "preview"]
        self.assertEqual(len(previews), 1)

    async def test_generate_original_from_saved_preview_plan_executes_as_original(self):
        """Generate Original from a saved Preview plan is the intentional
        semantic delta: the executed plan carries output_mode='original'
        (never the frozen preview mode) and History assets attach typed
        'original', not 'preview'."""
        self.plan, self.raw_plan = _build_plan(output_mode="preview")
        self.assertEqual(self.plan.execution_options.output_mode, "preview")
        gen = self._replayable_generation()

        status, body = await self._post(gen.generation_id)

        self.assertEqual(status, 200)
        self.assertEqual(body["outcome"], CODE_ORIGINAL_CREATED)
        final = await self._wait_for_terminal(body["run_id"])
        self.assertEqual(final, "completed")

        # The executed plan converted the semantic mode to original.
        executed = self.executor.plans[-1]
        self.assertEqual(executed.execution_options.output_mode, "original")
        self.assertEqual(
            executed.execution_options.output_conversion_options,
            {"format": "original"},
        )
        delta = validate_replay_delta(self.plan, executed)
        self.assertTrue(delta.allowed, delta.unexpected_paths)
        self.assertIn(
            "execution_options.output_mode", delta.changed_paths
        )

        # History asset typing follows the executed semantic mode.
        assets = self.repo.get_generation_assets(gen.generation_id)
        originals = [a for a in assets if a.type == "original"]
        previews = [a for a in assets if a.type == "preview"]
        self.assertEqual(len(originals), 1)
        self.assertEqual(originals[0].run_id, body["run_id"])
        self.assertEqual(len(previews), 1)
        detail = self._detail(gen.generation_id)
        resumed = next(a for a in detail.attempts if a.run_id == body["run_id"])
        self.assertEqual(resumed.mode, "original")

    async def test_detail_polling_surfaces_new_attempt_and_outputs(self):
        gen = self._replayable_generation()
        _, body = await self._post(gen.generation_id)
        await self._wait_for_terminal(body["run_id"])

        resp = await self.client.get(
            f"/comfymodal/history-v2/generations/{gen.generation_id}"
        )
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        item = data["item"]
        modes = {a["mode"]: a["status"] for a in item["attempts"]}
        self.assertEqual(modes.get("preview"), "completed")
        self.assertEqual(modes.get("original"), "completed")
        outputs = [o for o in item["outputs"] if o.get("original_url")]
        self.assertEqual(len(outputs), 1)
        previews = [
            o for o in item["outputs"] if o.get("preview_url")
        ]
        self.assertEqual(len(previews), 1)

    async def test_double_submit_returns_existing_active_attempt(self):
        gen = self._replayable_generation()
        self.executor.gate = asyncio.Event()
        first_status, first = await self._post(gen.generation_id)
        second_status, second = await self._post(gen.generation_id)
        self.assertEqual(first_status, 200)
        self.assertEqual(second_status, 200)
        self.assertEqual(first["outcome"], CODE_ORIGINAL_CREATED)
        self.assertEqual(second["outcome"], CODE_ORIGINAL_ALREADY_ACTIVE)
        self.assertTrue(second["reused"])
        self.assertEqual(second["run_id"], first["run_id"])
        detail = self._detail(gen.generation_id)
        originals = [a for a in detail.attempts if a.mode == "original"]
        self.assertEqual(len(originals), 1)
        self.executor.gate.set()
        await self._wait_for_terminal(first["run_id"])

    async def test_concurrent_double_submit_creates_one_attempt(self):
        gen = self._replayable_generation()
        self.executor.gate = asyncio.Event()
        results = await asyncio.gather(
            self._post(gen.generation_id),
            self._post(gen.generation_id),
        )
        outcomes = sorted(body["outcome"] for _, body in results)
        self.assertEqual(
            outcomes, [CODE_ORIGINAL_ALREADY_ACTIVE, CODE_ORIGINAL_CREATED]
        )
        run_ids = {body["run_id"] for _, body in results}
        self.assertEqual(len(run_ids), 1)
        detail = self._detail(gen.generation_id)
        originals = [a for a in detail.attempts if a.mode == "original"]
        self.assertEqual(len(originals), 1)
        self.executor.gate.set()
        await self._wait_for_terminal(next(iter(run_ids)))

    async def test_running_original_is_reused_not_duplicated(self):
        gen = self._replayable_generation()
        attempt = self.repo.add_attempt(gen.generation_id, mode="original")
        self.repo.update_attempt_status(attempt.run_id, "running")
        status, body = await self._post(gen.generation_id)
        self.assertEqual(status, 200)
        self.assertEqual(body["outcome"], CODE_ORIGINAL_ALREADY_ACTIVE)
        self.assertEqual(body["run_id"], attempt.run_id)
        self.assertEqual(self.executor.calls, 0)

    async def test_existing_success_is_reused_without_execution(self):
        gen = self._replayable_generation()
        attempt = self.repo.add_attempt(gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(attempt.run_id, status="completed")
        status, body = await self._post(gen.generation_id)
        self.assertEqual(status, 200)
        self.assertEqual(body["outcome"], CODE_ORIGINAL_ALREADY_COMPLETED)
        self.assertTrue(body["reused"])
        self.assertEqual(body["attempt_status"], "completed")
        self.assertEqual(body["run_id"], attempt.run_id)
        self.assertEqual(self.executor.calls, 0)
        detail = self._detail(gen.generation_id)
        self.assertEqual(len(detail.attempts), 2)

    async def test_explicit_rerender_creates_new_attempt(self):
        gen = self._replayable_generation()
        first = self.repo.add_attempt(gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(first.run_id, status="completed")
        status, body = await self._post(gen.generation_id, {"rerender": True})
        self.assertEqual(status, 200)
        self.assertEqual(body["outcome"], CODE_ORIGINAL_CREATED)
        self.assertEqual(body["attempt_status"], "queued")
        self.assertNotEqual(body["run_id"], first.run_id)
        detail = self._detail(gen.generation_id)
        originals = [a for a in detail.attempts if a.mode == "original"]
        self.assertEqual(len(originals), 2)
        old = next(a for a in originals if a.run_id == first.run_id)
        self.assertEqual(old.status, "completed")
        await self._wait_for_terminal(body["run_id"])

    async def test_invalid_rerender_flag_is_rejected(self):
        gen = self._replayable_generation()
        status, body = await self._post(gen.generation_id, {"rerender": "yes"})
        self.assertEqual(status, 400)
        self.assertEqual(self.executor.calls, 0)

    async def test_failed_only_returns_retry_required(self):
        gen = self._replayable_generation()
        failed = self.repo.add_attempt(gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(failed.run_id, status="failed")
        status, body = await self._post(gen.generation_id)
        self.assertEqual(status, 200)
        self.assertEqual(body["outcome"], CODE_RETRY_REQUIRED)
        self.assertFalse(body["reused"])
        self.assertEqual(body["run_id"], failed.run_id)
        self.assertEqual(body["attempt_status"], "failed")
        self.assertEqual(self.executor.calls, 0)
        detail = self._detail(gen.generation_id)
        self.assertEqual(len(detail.attempts), 2)

    async def test_active_preview_is_busy_with_no_new_attempt(self):
        gen = self._replayable_generation(with_completed_preview=False)
        self.repo.add_attempt(gen.generation_id, mode="preview")
        status, body = await self._post(gen.generation_id)
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], CODE_GENERATION_BUSY)
        detail = self._detail(gen.generation_id)
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(self.executor.calls, 0)

    async def test_legacy_generation_is_irreproducible_and_non_destructive(self):
        gen = self.repo.create_generation()
        self.repo.add_attempt(gen.generation_id, mode="preview")
        status, body = await self._post(gen.generation_id)
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], CODE_GENERATION_NOT_REPRODUCIBLE)
        self.assertEqual(body["reason"], "missing_request_snapshot")
        detail = self._detail(gen.generation_id)
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(self.executor.calls, 0)

    async def test_invalid_raw_hash_fails_closed_before_deserialization(self):
        gen = self._replayable_generation(with_completed_preview=False)
        detail = self._detail(gen.generation_id)
        assert detail.request_snapshot is not None
        broken = detail.request_snapshot.to_dict()
        broken["execution_plan"].pop("workflow_hash")
        self.repo.create_request_snapshot(
            generation_id=gen.generation_id,
            workflow_json=broken["workflow"],
            workflow_hash=broken["workflow_hash"],
            workflow_version_id=broken["workflow_version_id"],
            request=broken["request"],
            execution_plan=broken["execution_plan"],
            deployment_identity=broken["deployment_identity"],
        )
        status, body = await self._post(gen.generation_id)
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], CODE_GENERATION_NOT_REPRODUCIBLE)
        self.assertEqual(body["reason"], "missing_workflow_hash")
        refreshed = self._detail(gen.generation_id)
        self.assertEqual(len(refreshed.attempts), 0)
        self.assertEqual(self.executor.calls, 0)

    async def test_retry_route_creates_new_original_and_retains_failure(self):
        gen = self._replayable_generation()
        failed = self.repo.add_attempt(gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(failed.run_id, status="failed")
        status, body = await self._post(gen.generation_id, retry=True)
        self.assertEqual(status, 200)
        self.assertEqual(body["outcome"], CODE_ORIGINAL_CREATED)
        self.assertEqual(body["attempt_status"], "queued")
        self.assertNotEqual(body["run_id"], failed.run_id)
        detail = self._detail(gen.generation_id)
        old = next(a for a in detail.attempts if a.run_id == failed.run_id)
        self.assertEqual(old.status, "failed")
        new = next(a for a in detail.attempts if a.run_id == body["run_id"])
        self.assertEqual(new.mode, "original")
        self.assertIn(new.status, {"queued", "running", "completed"})
        await self._wait_for_terminal(new.run_id)

    async def test_retry_is_rejected_when_not_available(self):
        gen = self._replayable_generation()
        status, body = await self._post(gen.generation_id, retry=True)
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], CODE_RETRY_NOT_AVAILABLE)
        attempt = self.repo.add_attempt(gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(attempt.run_id, status="completed")
        status, body = await self._post(gen.generation_id, retry=True)
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], CODE_RETRY_NOT_AVAILABLE)

    async def test_retry_is_busy_while_attempt_active(self):
        gen = self._replayable_generation()
        self.executor.gate = asyncio.Event()
        _, body = await self._post(gen.generation_id)
        status, retry_body = await self._post(gen.generation_id, retry=True)
        self.assertEqual(status, 409)
        self.assertEqual(retry_body["code"], CODE_GENERATION_BUSY)
        self.executor.gate.set()
        await self._wait_for_terminal(body["run_id"])

    async def test_execution_failure_retains_preview_and_prior_success(self):
        gen = self._replayable_generation()
        success = self.repo.add_attempt(gen.generation_id, mode="original")
        self.repo.update_attempt_terminal(success.run_id, status="completed")
        success_file = self.output_dir / "success.png"
        success_file.write_bytes(_png_bytes())
        self.repo.attach_asset(
            gen.generation_id,
            run_id=success.run_id,
            asset_type="original",
            source_path=str(success_file),
            fmt="png",
            logical_output_key="node:7:slot:images:item:0",
        )

        self.executor.error = "remote boom"
        status, body = await self._post(
            gen.generation_id, {"rerender": True}
        )
        self.assertEqual(status, 200)
        final = await self._wait_for_terminal(body["run_id"])
        self.assertEqual(final, "failed")
        failed_attempt = self.repo.get_attempt(body["run_id"])
        assert failed_attempt is not None
        self.assertIsNotNone(failed_attempt.error)

        detail = self._detail(gen.generation_id)
        assets = detail.assets
        previews = [a for a in assets if a.type == "preview"]
        self.assertEqual(len(previews), 1)
        originals = [a for a in assets if a.type == "original"]
        self.assertEqual(len(originals), 1)
        self.assertEqual(originals[0].run_id, success.run_id)

        # E1B projection: prior successful Original stays the winner.
        selected, original_failed = _original_projection_safe(
            assets, detail.attempts
        )
        assert selected is not None
        self.assertEqual(selected.asset_id, originals[0].asset_id)
        self.assertFalse(original_failed)

    async def test_no_remote_output_marks_attempt_failed_never_completed(self):
        gen = self._replayable_generation()

        class NoOutputExecutor(FakeExecutor):
            async def __call__(self, plan, *, transport=None):
                self.plans.append(plan)
                self.calls += 1
                return {"status": "ok", "trace": {}}

        self.executor = NoOutputExecutor()
        status, body = await self._post(gen.generation_id)
        self.assertEqual(status, 200)
        final = await self._wait_for_terminal(body["run_id"])
        self.assertEqual(final, "failed")
        attempt = self.repo.get_attempt(body["run_id"])
        assert attempt is not None
        self.assertIn("no output", attempt.error or "")

    async def test_failed_history_finalization_blocks_completion(self):
        gen = self._replayable_generation()

        class FailingWriter:
            def attach_result_assets(self, *args, **kwargs):
                return False

        self.service_kwargs["writer_factory"] = lambda: FailingWriter()
        status, body = await self._post(gen.generation_id)
        self.assertEqual(status, 200)
        final = await self._wait_for_terminal(body["run_id"])
        self.assertEqual(final, "failed")
        attempt = self.repo.get_attempt(body["run_id"])
        assert attempt is not None
        self.assertIn("History output finalization failed", attempt.error or "")
        # The required-output gate fired BEFORE any terminal completed
        # write: no original asset was attached and the attempt never
        # reported success.
        assets = self.repo.get_generation_assets(gen.generation_id)
        self.assertFalse(any(a.type == "original" for a in assets))

    async def test_executor_exception_marks_attempt_failed(self):
        gen = self._replayable_generation()
        self.executor.error = "transport exploded"
        status, body = await self._post(gen.generation_id)
        self.assertEqual(status, 200)
        final = await self._wait_for_terminal(body["run_id"])
        self.assertEqual(final, "failed")
        attempt = self.repo.get_attempt(body["run_id"])
        assert attempt is not None
        self.assertIn("transport exploded", attempt.error or "")
        # Preview retained, generation identity unchanged.
        detail = self._detail(gen.generation_id)
        self.assertEqual(detail.generation.generation_id, gen.generation_id)
        self.assertTrue(
            any(a.type == "preview" for a in detail.assets)
        )

    async def test_unknown_generation_is_404(self):
        status, body = await self._post("gen_missing")
        self.assertEqual(status, 404)
        status, body = await self._post("gen_missing", retry=True)
        self.assertEqual(status, 404)


def _original_projection_safe(assets, attempts):
    from history_v2_routes import _original_projection

    return _original_projection(list(assets), list(attempts))


# ── Experiment-cell dispatch through the same service ─────────────────────


class ExperimentGenerateOriginalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self._tmp.name)
        self.store = HistoryV2Store(
            self.data_root / ".studio_history_v2" / "history_v2.db"
        )
        self.repo = HistoryV2Repository(self.store)
        self.plan, self.raw_plan = _build_plan()
        self.executor = FakeExecutor()
        self.scheduler = FakeScheduler()
        self.scheduler_getter = lambda experiment_id: self.scheduler
        self.scheduler_factory = None

    async def asyncSetUp(self) -> None:
        self.app = web.Application()
        register_history_v2_routes(
            self.app.router,
            self.data_root,
            generate_original_service_factory=self._make_service,
        )
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    def _make_service(self, repo: HistoryV2Repository) -> GenerateOriginalService:
        return GenerateOriginalService(
            repo,
            data_root=self.data_root,
            transport_factory=lambda: object(),
            executor=self.executor,
            materializer=_fake_materializer(self.data_root),
            scheduler_getter=self.scheduler_getter,
            scheduler_factory=self.scheduler_factory,
        )

    def _matrix(self):
        spec = {
            "cell_id": "cell_a",
            "axis_values": {"seed": 0},
            "controls": {"seed": 0},
            "merged_values": {"seed": 0},
            "axis_to_control": {"seed": "seed"},
            "workflow_id": "wf_frozen",
            "workflow_version_id": "wv_frozen",
            "preset_id": "preset_frozen",
            "preset_name": "Frozen Preset",
            "workflow_name": "Frozen Workflow",
            "plan_hash": "h_cell_a",
            "workflow_hash": self.raw_plan["workflow_hash"],
            "execution_plan": copy.deepcopy(self.raw_plan),
        }
        detail = self.repo.create_modern_matrix(
            experiment_id="exp_orig",
            name="Matrix",
            definition={"version": 2, "cells": [spec]},
            cells=[spec],
        )
        cell = detail.cells[0]
        assert cell.generation_id is not None
        return cell

    async def test_experiment_generation_uses_same_service_and_scheduler(self):
        cell = self._matrix()
        gid = cell.generation_id
        assert gid is not None
        current = self.repo.get_current_cell_attempt(cell.cell_id)
        assert current is not None
        # A terminal failed Original leaves Generate Original (default) at
        # retry-required; the explicit rerender action is what creates the
        # new Attempt here.
        self.repo.update_attempt_terminal(current.run_id, status="failed")

        response = await self.client.post(
            f"/comfymodal/history-v2/generations/{gid}/original",
            json={"rerender": True},
        )
        self.assertEqual(response.status, 200)
        body = await response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["outcome"], CODE_ORIGINAL_CREATED)
        self.assertEqual(body["generation_id"], gid)
        self.assertEqual(body["purpose"], "original")
        self.assertFalse(body["reused"])
        self.assertEqual(self.executor.calls, 0)

        # The EXISTING modern scheduler binding received the cell: no second
        # Experiment execution engine was invoked.
        self.assertEqual(len(self.scheduler.submitted), 1)
        submitted = self.scheduler.submitted[0]
        self.assertEqual(submitted["cell_id"], cell.cell_id)
        replay_plan = ExecutionPlan.from_dict(submitted["execution_plan"])
        delta = validate_replay_delta(self.plan, replay_plan)
        self.assertTrue(delta.allowed, delta.unexpected_paths)
        self.assertEqual(
            replay_plan.execution_options.output_conversion_options,
            {"format": "original"},
        )
        self.assertEqual(replay_plan.workflow_hash, self.plan.workflow_hash)
        self.assertEqual(
            replay_plan.deployment_identity, self.plan.deployment_identity
        )

        detail = self.repo.get_generation(gid)
        assert detail is not None
        originals = [a for a in detail.attempts if a.mode == "original"]
        self.assertEqual(len(originals), 2)
        self.assertEqual(originals[-1].run_id, body["run_id"])
        self.assertEqual(originals[-1].cell_id, cell.cell_id)

    async def test_experiment_without_scheduler_leaves_no_orphan_attempt(self):
        cell = self._matrix()
        gid = cell.generation_id
        assert gid is not None
        before_detail = self.repo.get_generation(gid)
        assert before_detail is not None
        before = len(before_detail.attempts)

        self.scheduler_getter = lambda experiment_id: None
        self.scheduler_factory = lambda *args, **kwargs: None
        response = await self.client.post(
            f"/comfymodal/history-v2/generations/{gid}/original", json={}
        )
        self.assertEqual(response.status, 503)
        body = await response.json()
        self.assertEqual(body["code"], CODE_DISPATCH_UNAVAILABLE)
        after_detail = self.repo.get_generation(gid)
        assert after_detail is not None
        after = len(after_detail.attempts)
        self.assertEqual(after, before)
        self.assertEqual(len(self.scheduler.submitted), 0)


if __name__ == "__main__":
    unittest.main()
