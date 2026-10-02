"""F1A durable recovery and Resume backend contracts.

Offline-only coverage for ordinary Single startup recovery/Resume and
post-restart modern Experiment Resume.  The tests use temporary History V2
SQLite stores, injected canonical executor/transport seams, and never call
Modal, deploy, GPU, or live generation.
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
from unittest import mock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import canonical_execution
import experiment_modern_routes as emr
import experiment_modern_scheduler as ems
import history_v2_replay as hvr
from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
from history_v2_models import current_attempt
from history_v2_repository import HistoryV2Repository
from history_v2_routes import register_history_v2_routes
from history_v2_store import HistoryV2Store
from history_v2_replay import (
    CODE_DISPATCH_UNAVAILABLE,
    CODE_GENERATION_BUSY,
    CODE_GENERATION_NOT_REPRODUCIBLE,
    CODE_RESUME_CREATED,
    CODE_RESUME_NOT_AVAILABLE,
    GenerateOriginalService,
    ReplayCapability,
    ReplayCapabilityError,
    validate_replay_delta,
)
from experiment_modern_routes import (
    register_experiment_modern_routes,
    startup_experiment_modern_lifecycle,
)


T0 = "2026-08-15T00:00:00.000+00:00"
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _build_plan(*, output_mode: str = "original") -> tuple[ExecutionPlan, dict[str, Any]]:
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
            "workspace_id": "ws_frozen",
            "prompt_id": "initial-prompt",
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
    status: str = "interrupted",
    with_snapshot: bool = True,
) -> tuple[Any, Any, Any, dict[str, Any]]:
    plan, raw_plan = _build_plan(output_mode=mode)
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
    elif status != "queued":
        repo.update_attempt_status(attempt.run_id, status)
    return generation, attempt, plan, raw_plan


class _FakeExecutor:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.plans: list[ExecutionPlan] = []
        self.calls = 0
        self.gate: asyncio.Event | None = None
        self.error: str | None = None

    async def __call__(self, plan: ExecutionPlan, *, transport: Any = None) -> dict[str, Any]:
        self.calls += 1
        self.plans.append(plan)
        if self.gate is not None:
            await self.gate.wait()
        if self.error:
            raise RuntimeError(self.error)
        filename = f"resume-{self.calls}.png"
        (self.output_dir / filename).write_bytes(_PNG_BYTES)
        return {
            "status": "ok",
            "trace": {},
            "outputs": {filename: {"data": ""}},
            "asset_descriptors": [
                {
                    "node_id": "7",
                    "output_key": "images",
                    "output_index": 0,
                    "filename": filename,
                    "mime_type": "image/png",
                }
            ],
        }


def _fake_materializer(output_dir: Path):
    async def materialize(result: Any, plan: ExecutionPlan, prompt_id: str) -> list[str]:
        return [str(path) for path in sorted(output_dir.glob("resume-*.png"))]

    return materialize


class _ExecuteRecorder:
    def __init__(self):
        self.plans: list[ExecutionPlan] = []

    async def __call__(self, plan: ExecutionPlan, **kwargs: Any) -> dict[str, Any]:
        self.plans.append(plan)
        return {"status": "ok"}


class SingleStartupRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = HistoryV2Repository(
            HistoryV2Store(self.root / ".studio_history_v2" / "history_v2.db")
        )

    def _startup(self) -> dict[str, Any]:
        return asyncio.run(startup_experiment_modern_lifecycle(self.root))

    def test_stale_owned_single_running_becomes_interrupted(self):
        generation, attempt, _plan, _raw = _seed_single(
            self.repo, mode="preview", status="running"
        )
        result = self._startup()
        self.assertEqual(result["marked_interrupted_singles"], [attempt.run_id])
        detail = self.repo.get_generation(generation.generation_id)
        assert detail is not None
        self.assertEqual(detail.generation.status, "interrupted")
        self.assertEqual(detail.attempts[0].status, "interrupted")
        self.assertEqual(detail.attempts[0].error, "startup recovery")

    def test_terminal_single_states_are_unchanged(self):
        for status in ("completed", "failed", "canceled"):
            generation, attempt, _plan, _raw = _seed_single(
                self.repo, status=status
            )
            result = self._startup()
            self.assertNotIn(attempt.run_id, result["marked_interrupted_singles"])
            stored = self.repo.get_attempt(attempt.run_id)
            assert stored is not None
            self.assertEqual(stored.status, status)
            self.assertEqual(self.repo.get_generation(generation.generation_id).generation.status, status)

    def test_already_interrupted_and_queued_are_unchanged(self):
        interrupted_gen, interrupted, _plan, _raw = _seed_single(
            self.repo, status="interrupted"
        )
        queued_gen, queued, _plan, _raw = _seed_single(
            self.repo, status="queued"
        )
        result = self._startup()
        self.assertEqual(result["marked_interrupted_singles"], [])
        self.assertEqual(self.repo.get_attempt(interrupted.run_id).status, "interrupted")
        self.assertEqual(self.repo.get_attempt(queued.run_id).status, "queued")
        self.assertEqual(self.repo.get_generation(interrupted_gen.generation_id).generation.status, "interrupted")
        self.assertEqual(self.repo.get_generation(queued_gen.generation_id).generation.status, "running")

    def test_repeated_sweep_is_idempotent(self):
        _generation, attempt, _plan, _raw = _seed_single(
            self.repo, status="running"
        )
        first = self._startup()
        second = self._startup()
        self.assertEqual(first["marked_interrupted_singles"], [attempt.run_id])
        self.assertEqual(second["marked_interrupted_singles"], [])
        self.assertEqual(self.repo.get_attempt(attempt.run_id).status, "interrupted")

    def test_experiment_owned_running_attempt_is_not_single_recovered(self):
        legacy = self.repo.create_experiment(name="legacy", cells=[{}], created_at=T0)
        generation = self.repo.create_generation(generation_id="gen_legacy")
        attempt = self.repo.add_attempt(
            generation.generation_id,
            experiment_id=legacy.experiment.experiment_id,
        )
        self.repo.update_attempt_status(attempt.run_id, "running")
        result = self._startup()
        self.assertNotIn(attempt.run_id, result["marked_interrupted_singles"])
        self.assertEqual(self.repo.get_attempt(attempt.run_id).status, "running")

    def test_snapshot_is_unchanged_by_startup_sweep(self):
        generation, attempt, _plan, _raw = _seed_single(
            self.repo, mode="preview", status="running"
        )
        before = self.repo.get_generation(generation.generation_id).request_snapshot.to_dict()
        self._startup()
        after = self.repo.get_generation(generation.generation_id).request_snapshot.to_dict()
        self.assertEqual(after, before)
        self.assertEqual(self.repo.get_attempt(attempt.run_id).status, "interrupted")


class SingleResumeRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = HistoryV2Repository(
            HistoryV2Store(self.root / ".studio_history_v2" / "history_v2.db")
        )

    def test_interrupted_preview_appends_same_generation_and_mode(self):
        generation, old, _plan, _raw = _seed_single(
            self.repo, mode="preview", status="interrupted"
        )
        outcome = self.repo.create_single_resume_attempt(generation.generation_id)
        assert outcome is not None and outcome.attempt is not None
        self.assertEqual(outcome.outcome, "created")
        self.assertEqual(outcome.attempt.mode, "preview")
        self.assertEqual(outcome.attempt.status, "queued")
        self.assertEqual(outcome.attempt.generation_id, generation.generation_id)
        self.assertNotEqual(outcome.attempt.run_id, old.run_id)
        self.assertEqual(self.repo.get_attempt(old.run_id).status, "interrupted")
        self.assertEqual(len(self.repo.get_generation(generation.generation_id).attempts), 2)

    def test_interrupted_original_preserves_original_mode(self):
        generation, _old, _plan, _raw = _seed_single(
            self.repo, mode="original", status="interrupted"
        )
        outcome = self.repo.create_single_resume_attempt(generation.generation_id)
        assert outcome is not None and outcome.attempt is not None
        self.assertEqual(outcome.attempt.mode, "original")

    def test_active_resume_is_busy_without_new_attempt(self):
        generation, _old, _plan, _raw = _seed_single(
            self.repo, mode="preview", status="queued"
        )
        outcome = self.repo.create_single_resume_attempt(generation.generation_id)
        assert outcome is not None
        self.assertEqual(outcome.outcome, "busy")
        self.assertEqual(len(self.repo.get_generation(generation.generation_id).attempts), 1)

    def test_terminal_states_are_not_resumable(self):
        for status, reason in (
            ("failed", "failed_requires_retry"),
            ("canceled", "canceled_not_resumable"),
            ("completed", "generation_completed"),
        ):
            generation, _old, _plan, _raw = _seed_single(self.repo, status=status)
            outcome = self.repo.create_single_resume_attempt(generation.generation_id)
            assert outcome is not None
            self.assertEqual(outcome.outcome, "not_resumable")
            self.assertEqual(outcome.reason, reason)

    def test_missing_attempt_and_experiment_cell_are_not_resumable(self):
        generation = self.repo.create_generation()
        outcome = self.repo.create_single_resume_attempt(generation.generation_id)
        assert outcome is not None
        self.assertEqual(outcome.reason, "no_attempts")

        plan, raw_plan = _build_plan()
        spec = {
            "cell_id": "cell_a",
            "workflow_id": "wf_frozen",
            "workflow_version_id": "wv_frozen",
            "preset_id": "preset_frozen",
            "workflow_hash": raw_plan["workflow_hash"],
            "execution_plan": raw_plan,
        }
        detail = self.repo.create_modern_matrix(
            experiment_id="exp_cell",
            name="Cell",
            definition={"version": 2, "contract": "modern_v2", "cells": [spec]},
            cells=[spec],
        )
        cell_generation = detail.cells[0].generation_id
        assert cell_generation is not None
        cell_attempt = self.repo.get_current_cell_attempt("cell_a")
        assert cell_attempt is not None
        self.repo.update_attempt_terminal(cell_attempt.run_id, status="interrupted")
        cell_outcome = self.repo.create_single_resume_attempt(cell_generation)
        assert cell_outcome is not None
        self.assertEqual(cell_outcome.reason, "experiment_cell_generation")

    def test_concurrent_resume_claims_are_first_wins(self):
        generation, _old, _plan, _raw = _seed_single(
            self.repo, mode="preview", status="interrupted"
        )
        results: list[Any] = []

        def claim() -> None:
            local = HistoryV2Repository(
                HistoryV2Store(self.root / ".studio_history_v2" / "history_v2.db")
            )
            results.append(local.create_single_resume_attempt(generation.generation_id))

        import threading

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        outcomes = sorted(result.outcome for result in results if result is not None)
        self.assertEqual(outcomes, ["busy", "created"])
        attempts = self.repo.get_generation(generation.generation_id).attempts
        self.assertEqual(len(attempts), 2)
        self.assertEqual(sum(a.status in {"queued", "running"} for a in attempts), 1)


class SingleResumeRouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.output_dir = self.root / "studio_outputs"
        self.repo = HistoryV2Repository(
            HistoryV2Store(self.root / ".studio_history_v2" / "history_v2.db")
        )
        self.executor = _FakeExecutor(self.output_dir)
        self.workspace: dict[str, Any] | None = {"id": "ws_test"}
        self.transport_factory: Any = lambda: object()
        self.service_kwargs: dict[str, Any] = {}
        self.workspace_patch = mock.patch.object(
            hvr, "_resolve_replay_workspace", side_effect=lambda plan: self.workspace
        )
        self.workspace_patch.start()
        self.addCleanup(self.workspace_patch.stop)

    async def asyncSetUp(self) -> None:
        self.app = web.Application()
        register_history_v2_routes(
            self.app.router,
            self.root,
            generate_original_service_factory=self._make_service,
        )
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    def _make_service(self, repo: HistoryV2Repository) -> GenerateOriginalService:
        kwargs = dict(self.service_kwargs)
        kwargs.setdefault("data_root", self.root)
        kwargs.setdefault("transport_factory", self.transport_factory)
        kwargs.setdefault("executor", self.executor)
        kwargs.setdefault("materializer", _fake_materializer(self.output_dir))
        return GenerateOriginalService(repo, **kwargs)

    async def _post(self, generation_id: str) -> tuple[int, dict[str, Any]]:
        response = await self.client.post(
            f"/comfymodal/history-v2/generations/{generation_id}/resume"
        )
        return response.status, await response.json()

    async def _wait_terminal(self, run_id: str, timeout: float = 5.0) -> str:
        deadline = time.monotonic() + timeout
        status = ""
        while time.monotonic() < deadline:
            attempt = self.repo.get_attempt(run_id)
            status = attempt.status if attempt is not None else ""
            if status in {"completed", "failed", "canceled", "interrupted"}:
                return status
            await asyncio.sleep(0.01)
        return status

    def _seed(self, *, mode: str = "original", status: str = "interrupted"):
        return _seed_single(self.repo, mode=mode, status=status)

    async def test_interrupted_single_resume_is_append_only_and_dispatches(self):
        generation, old, saved_plan, _raw = self._seed(mode="original")
        status, body = await self._post(generation.generation_id)
        self.assertEqual(status, 200)
        self.assertEqual(body["outcome"], CODE_RESUME_CREATED)
        self.assertEqual(body["purpose"], "resume")
        self.assertEqual(body["decision"], "resume_created")
        self.assertEqual(body["executor"], "canonical_execution.execute_plan")
        self.assertFalse(body["reused"])
        self.assertEqual(body["mode"], "original")
        self.assertNotEqual(body["run_id"], old.run_id)
        self.assertEqual(body["attempt_status"], "queued")
        final = await self._wait_terminal(body["run_id"])
        self.assertEqual(final, "completed")
        detail = self.repo.get_generation(generation.generation_id)
        assert detail is not None
        self.assertEqual(detail.generation.generation_id, generation.generation_id)
        self.assertEqual(next(a for a in detail.attempts if a.run_id == old.run_id).status, "interrupted")
        self.assertEqual(next(a for a in detail.attempts if a.run_id == body["run_id"]).mode, "original")
        self.assertTrue(any(asset.run_id == body["run_id"] for asset in detail.assets))

    async def test_resume_preserves_frozen_original_plan_without_conversion_delta(self):
        generation, _old, saved_plan, _raw = self._seed(mode="original")
        status, body = await self._post(generation.generation_id)
        self.assertEqual(status, 200)
        await self._wait_terminal(body["run_id"])
        executed = self.executor.plans[-1]
        delta = validate_replay_delta(saved_plan, executed)
        self.assertTrue(delta.allowed, delta.unexpected_paths)
        self.assertEqual(executed.execution_options.output_mode, "original")
        self.assertEqual(
            executed.execution_options.output_conversion_options,
            saved_plan.execution_options.output_conversion_options,
        )
        self.assertNotEqual(
            executed.execution_options.output_conversion_options,
            {"format": "original"},
        )
        self.assertEqual(executed.workflow, saved_plan.workflow)
        self.assertEqual(executed.model_stack, saved_plan.model_stack)
        self.assertEqual(
            executed.request_metadata["workspace_id"],
            saved_plan.request_metadata["workspace_id"],
        )

    async def test_resume_preserves_preview_mode_and_conversion_options(self):
        generation, _old, saved_plan, _raw = self._seed(mode="preview")
        status, body = await self._post(generation.generation_id)
        self.assertEqual(status, 200)
        self.assertEqual(body["mode"], "preview")
        await self._wait_terminal(body["run_id"])
        executed = self.executor.plans[-1]
        self.assertEqual(executed.execution_options.output_mode, "preview")
        self.assertEqual(
            executed.execution_options.output_conversion_options,
            saved_plan.execution_options.output_conversion_options,
        )
        self.assertEqual(
            executed.execution_options.output_conversion_options["format"],
            "webp_lossy",
        )
        detail = self.repo.get_generation(generation.generation_id)
        assert detail is not None
        resumed = detail.attempts[-1]
        self.assertEqual(resumed.mode, "preview")
        self.assertTrue(any(asset.type == "preview" and asset.run_id == resumed.run_id for asset in detail.assets))

    async def test_failed_canceled_completed_and_active_are_refused(self):
        for source_status, expected_reason in (
            ("failed", "failed_requires_retry"),
            ("canceled", "canceled_not_resumable"),
            ("completed", "generation_completed"),
        ):
            generation, _old, _plan, _raw = self._seed(status=source_status)
            status, body = await self._post(generation.generation_id)
            self.assertEqual(status, 409)
            self.assertEqual(body["code"], CODE_RESUME_NOT_AVAILABLE)
            self.assertEqual(body["reason"], expected_reason)
            self.assertEqual(self.executor.calls, 0)

        generation, _old, _plan, _raw = self._seed(status="running")
        status, body = await self._post(generation.generation_id)
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], CODE_GENERATION_BUSY)
        self.assertEqual(self.executor.calls, 0)

    async def test_legacy_and_experiment_cell_resume_are_truthfully_refused(self):
        generation = self.repo.create_generation()
        old = self.repo.add_attempt(generation.generation_id, mode="original")
        self.repo.update_attempt_terminal(old.run_id, status="interrupted")
        status, body = await self._post(generation.generation_id)
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], CODE_GENERATION_NOT_REPRODUCIBLE)
        self.assertEqual(body["reason"], "missing_request_snapshot")

        _plan, raw_plan = _build_plan()
        spec = {
            "cell_id": "cell_resume",
            "workflow_id": "wf_frozen",
            "workflow_version_id": "wv_frozen",
            "preset_id": "preset_frozen",
            "workflow_hash": raw_plan["workflow_hash"],
            "execution_plan": raw_plan,
        }
        matrix = self.repo.create_modern_matrix(
            experiment_id="exp_resume_cell",
            name="Cell",
            definition={"version": 2, "contract": "modern_v2", "cells": [spec]},
            cells=[spec],
        )
        cell_generation = matrix.cells[0].generation_id
        assert cell_generation is not None
        cell_attempt = self.repo.get_current_cell_attempt("cell_resume")
        assert cell_attempt is not None
        self.repo.update_attempt_terminal(cell_attempt.run_id, status="interrupted")
        status, body = await self._post(cell_generation)
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], CODE_RESUME_NOT_AVAILABLE)
        self.assertEqual(body["reason"], "experiment_cell_generation")

    async def test_missing_workspace_or_transport_leaves_no_orphan(self):
        generation, _old, _plan, _raw = self._seed()
        before = len(self.repo.get_generation(generation.generation_id).attempts)
        self.workspace = None
        status, body = await self._post(generation.generation_id)
        self.assertEqual(status, 503)
        self.assertEqual(body["code"], CODE_DISPATCH_UNAVAILABLE)
        self.assertEqual(body["reason"], "workspace_unresolved")
        self.assertEqual(len(self.repo.get_generation(generation.generation_id).attempts), before)

        generation, _old, _plan, _raw = self._seed()
        self.workspace = {"id": "ws_test"}
        self.transport_factory = lambda: (_ for _ in ()).throw(RuntimeError("no transport"))
        before = len(self.repo.get_generation(generation.generation_id).attempts)
        status, body = await self._post(generation.generation_id)
        self.assertEqual(status, 503)
        self.assertEqual(body["code"], CODE_DISPATCH_UNAVAILABLE)
        self.assertEqual(len(self.repo.get_generation(generation.generation_id).attempts), before)

    async def test_late_resume_replay_failure_marks_new_attempt_failed(self):
        generation, old, _plan, _raw = self._seed()
        capability = ReplayCapability(False, "late_invalid_plan")
        with mock.patch.object(
            hvr,
            "build_resume_replay_dispatch",
            side_effect=ReplayCapabilityError(capability),
        ):
            status, body = await self._post(generation.generation_id)
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], CODE_GENERATION_NOT_REPRODUCIBLE)
        detail = self.repo.get_generation(generation.generation_id)
        assert detail is not None
        self.assertEqual(len(detail.attempts), 2)
        self.assertEqual(detail.attempts[0].run_id, old.run_id)
        self.assertEqual(detail.attempts[0].status, "interrupted")
        self.assertEqual(detail.attempts[1].status, "failed")

    async def test_concurrent_resume_creates_at_most_one_active_attempt(self):
        generation, old, _plan, _raw = self._seed(mode="preview")
        self.executor.gate = asyncio.Event()
        results = await asyncio.gather(
            self._post(generation.generation_id),
            self._post(generation.generation_id),
        )
        outcomes = sorted(body.get("outcome", body.get("code", "")) for _status, body in results)
        self.assertEqual(outcomes, [CODE_GENERATION_BUSY, CODE_RESUME_CREATED])
        detail = self.repo.get_generation(generation.generation_id)
        assert detail is not None
        self.assertEqual(len(detail.attempts), 2)
        self.assertEqual(sum(a.status in {"queued", "running"} for a in detail.attempts), 1)
        self.executor.gate.set()
        created = next(body["run_id"] for _status, body in results if body.get("outcome") == CODE_RESUME_CREATED)
        self.assertEqual(await self._wait_terminal(created), "completed")

    async def test_terminal_output_association_precedes_completed(self):
        generation, _old, _plan, _raw = self._seed()
        status, body = await self._post(generation.generation_id)
        self.assertEqual(status, 200)
        self.assertEqual(await self._wait_terminal(body["run_id"]), "completed")
        detail = self.repo.get_generation(generation.generation_id)
        assert detail is not None
        self.assertTrue(any(asset.run_id == body["run_id"] for asset in detail.assets))

        class FailingWriter:
            def attach_result_assets(self, *args: Any, **kwargs: Any) -> bool:
                return False

        generation, _old, _plan, _raw = self._seed()
        self.service_kwargs["writer_factory"] = lambda: FailingWriter()
        status, body = await self._post(generation.generation_id)
        self.assertEqual(status, 200)
        self.assertEqual(await self._wait_terminal(body["run_id"]), "failed")
        attempt = self.repo.get_attempt(body["run_id"])
        assert attempt is not None
        self.assertIn("History output finalization failed", attempt.error or "")


class ExperimentPostRestartResumeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = HistoryV2Repository(
            HistoryV2Store(self.root / ".studio_history_v2" / "history_v2.db")
        )
        self.registry: dict[str, Any] = {}
        self.previous_transport_factory = emr._DEFAULT_TRANSPORT_FACTORY[0]
        self.app = web.Application()
        register_history_v2_routes(self.app.router, self.root)
        register_experiment_modern_routes(
            self.app.router,
            self.root,
            registry=self.registry,
            transport_factory=lambda: object(),
        )
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        for experiment_id in list(ems._SCHEDULERS):
            if experiment_id.startswith("exp_f1a_"):
                scheduler = ems.get_scheduler(experiment_id)
                if scheduler is not None:
                    await scheduler.shutdown()
                ems.unregister_scheduler(experiment_id)
        emr._DEFAULT_TRANSPORT_FACTORY[0] = self.previous_transport_factory
        await self.client.close()
        self.tmp.cleanup()

    def _specs(self, count: int = 2) -> list[dict[str, Any]]:
        _plan, raw_plan = _build_plan()
        specs: list[dict[str, Any]] = []
        for index in range(count):
            cell_id = chr(ord("a") + index)
            specs.append(
                {
                    "cell_id": cell_id,
                    "position": index,
                    "workflow_id": "wf_frozen",
                    "workflow_version_id": "wv_frozen",
                    "preset_id": "preset_frozen",
                    "workflow_hash": raw_plan["workflow_hash"],
                    "execution_plan": copy.deepcopy(raw_plan),
                }
            )
        return specs

    def _matrix(self, experiment_id: str, count: int = 2, *, include_cells: bool = True):
        specs = self._specs(count)
        definition = {
            "version": 2,
            "contract": "modern_v2",
        }
        if include_cells:
            definition["cells"] = copy.deepcopy(specs)
        return self.repo.create_modern_matrix(
            experiment_id=experiment_id,
            name="F1A Matrix",
            definition=definition,
            cells=specs,
            created_at=T0,
        )

    async def _post(self, experiment_id: str) -> tuple[int, dict[str, Any]]:
        response = await self.client.post(
            f"/comfymodal/history-v2/experiments/{experiment_id}/resume"
        )
        return response.status, await response.json()

    async def _wait_cells_terminal(self, cell_ids: list[str], timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            statuses = [
                self.repo.get_current_cell_attempt(cell_id).status
                for cell_id in cell_ids
            ]
            if all(status in {"completed", "failed", "canceled", "interrupted"} for status in statuses):
                return
            await asyncio.sleep(0.01)
        self.fail(
            "cells did not reach terminal state: "
            + repr(
                [
                    (cell_id, self.repo.get_current_cell_attempt(cell_id).status)
                    for cell_id in cell_ids
                ]
            )
        )

    async def test_startup_sweep_then_restart_resume_reconstructs_and_dispatches(self):
        experiment_id = "exp_f1a_restart"
        detail = self._matrix(experiment_id)
        run_a = self.repo.atomically_claim_queued_attempt("a")
        assert run_a is not None
        run_b = self.repo.get_current_cell_attempt("b")
        assert run_b is not None
        run_b_id = run_b.run_id

        recovery = await startup_experiment_modern_lifecycle(self.root, registry={})
        self.assertIn(run_a.attempt.run_id, recovery["marked_interrupted"])
        self.assertEqual(self.repo.get_current_cell_attempt("a").status, "interrupted")
        self.assertEqual(self.repo.get_current_cell_attempt("b").status, "queued")

        recorder = _ExecuteRecorder()
        with mock.patch.object(canonical_execution, "execute_plan", new=recorder):
            status, body = await self._post(experiment_id)
        self.assertEqual(status, 200)
        self.assertTrue(body["dispatched"])
        self.assertTrue(body["scheduler_reconstructed"])
        self.assertEqual(body["resumed"], 2)
        self.assertEqual(body["created_attempts"][0]["cell_id"], "a")
        self.assertEqual(len(recorder.plans), 2)
        scheduler = ems.get_scheduler(experiment_id)
        self.assertIsNotNone(scheduler)
        assert scheduler is not None
        self.assertEqual(scheduler.concurrency, 6)

        await self._wait_cells_terminal(["a", "b"])
        attempts_a = self.repo.get_attempts_for_cells(["a"])
        attempts_b = self.repo.get_attempts_for_cells(["b"])
        self.assertEqual(len(attempts_a), 2)
        self.assertEqual(attempts_a[0].status, "interrupted")
        self.assertEqual(len(attempts_b), 1)
        self.assertEqual(attempts_b[0].run_id, run_b_id)
        self.assertNotIn("queued", [self.repo.get_current_cell_attempt(cid).status for cid in ("a", "b")])

    async def test_failed_canceled_completed_cells_are_untouched(self):
        experiment_id = "exp_f1a_terminal"
        self._matrix(experiment_id, count=5)
        run_a = self.repo.atomically_claim_queued_attempt("a")
        assert run_a is not None
        self.repo.record_terminal(run_a.attempt.run_id, "a", "interrupted")
        original: dict[str, tuple[str, str]] = {}
        for cell_id, terminal in (("c", "failed"), ("d", "canceled"), ("e", "completed")):
            claim = self.repo.atomically_claim_queued_attempt(cell_id)
            assert claim is not None
            self.repo.record_terminal(claim.attempt.run_id, cell_id, terminal)
            original[cell_id] = (claim.attempt.run_id, terminal)

        recorder = _ExecuteRecorder()
        with mock.patch.object(canonical_execution, "execute_plan", new=recorder):
            status, body = await self._post(experiment_id)
        self.assertEqual(status, 200)
        self.assertEqual(body["resumed"], 2)
        await self._wait_cells_terminal(["a", "b"])
        for cell_id, (run_id, terminal) in original.items():
            current = self.repo.get_current_cell_attempt(cell_id)
            assert current is not None
            self.assertEqual(current.run_id, run_id)
            self.assertEqual(current.status, terminal)
        self.assertEqual(len(self.repo.get_attempts_for_cells(["c"])), 1)
        self.assertEqual(len(self.repo.get_attempts_for_cells(["d"])), 1)
        self.assertEqual(len(self.repo.get_attempts_for_cells(["e"])), 1)

    async def test_reconstruction_unavailable_fails_closed_without_orphan(self):
        experiment_id = "exp_f1a_unavailable"
        self._matrix(experiment_id)
        claim = self.repo.atomically_claim_queued_attempt("a")
        assert claim is not None
        self.repo.record_terminal(claim.attempt.run_id, "a", "interrupted")
        before_a = len(self.repo.get_attempts_for_cells(["a"]))
        before_b = len(self.repo.get_attempts_for_cells(["b"]))
        emr._DEFAULT_TRANSPORT_FACTORY[0] = None
        status, body = await self._post(experiment_id)
        self.assertEqual(status, 503)
        self.assertEqual(body["code"], "DISPATCH_UNAVAILABLE")
        self.assertEqual(len(self.repo.get_attempts_for_cells(["a"])), before_a)
        self.assertEqual(len(self.repo.get_attempts_for_cells(["b"])), before_b)
        self.assertEqual(self.repo.get_current_cell_attempt("a").status, "interrupted")
        self.assertEqual(self.repo.get_current_cell_attempt("b").status, "queued")
        self.assertIsNone(ems.get_scheduler(experiment_id))

    async def test_missing_persisted_cell_plans_fails_closed(self):
        experiment_id = "exp_f1a_no_plan"
        self._matrix(experiment_id, include_cells=False)
        claim = self.repo.atomically_claim_queued_attempt("a")
        assert claim is not None
        self.repo.record_terminal(claim.attempt.run_id, "a", "interrupted")
        status, body = await self._post(experiment_id)
        self.assertEqual(status, 503)
        self.assertEqual(body["code"], "DISPATCH_UNAVAILABLE")
        self.assertEqual(len(self.repo.get_attempts_for_cells(["a"])), 1)

    def _matrix_with_raw_definition(
        self,
        experiment_id: str,
        definition_cells: list[dict[str, Any]] | None,
    ):
        """Create a matrix whose durable cells are well-formed but whose
        persisted ``definition['cells']`` payload is an arbitrary raw list
        (used to simulate corrupt/partial persistence)."""
        specs = self._specs(2)
        definition: dict[str, Any] = {
            "version": 2,
            "contract": "modern_v2",
        }
        if definition_cells is not None:
            definition["cells"] = definition_cells
        return self.repo.create_modern_matrix(
            experiment_id=experiment_id,
            name="F1A Matrix",
            definition=definition,
            cells=specs,
            created_at=T0,
        )

    async def _assert_fail_closed(
        self,
        experiment_id: str,
        *,
        before_counts: dict[str, int],
    ) -> tuple[int, dict[str, Any]]:
        statuses_before = {
            cell_id: (
                self.repo.get_current_cell_attempt(cell_id).status
                if self.repo.get_current_cell_attempt(cell_id) is not None
                else None
            )
            for cell_id in before_counts
        }
        recorder = _ExecuteRecorder()
        with mock.patch.object(canonical_execution, "execute_plan", new=recorder):
            status, body = await self._post(experiment_id)
        self.assertEqual(status, 503)
        self.assertEqual(body["code"], "DISPATCH_UNAVAILABLE")
        # No scheduler was registered anywhere.
        self.assertIsNone(ems.get_scheduler(experiment_id))
        self.assertNotIn(experiment_id, self.registry)
        # No attempt mutation happened.
        for cell_id, count in before_counts.items():
            self.assertEqual(len(self.repo.get_attempts_for_cells([cell_id])), count)
            current = self.repo.get_current_cell_attempt(cell_id)
            assert current is not None
            self.assertEqual(current.status, statuses_before[cell_id])
        return status, body

    async def test_partial_persisted_plan_missing_cell_id_fails_closed(self):
        experiment_id = "exp_f1a_partial"
        specs = self._specs(2)
        self._matrix_with_raw_definition(experiment_id, [specs[0]])
        claim = self.repo.atomically_claim_queued_attempt("a")
        assert claim is not None
        self.repo.record_terminal(claim.attempt.run_id, "a", "interrupted")
        await self._assert_fail_closed(
            experiment_id, before_counts={"a": 1, "b": 1}
        )

    async def test_extra_persisted_cell_id_fails_closed(self):
        experiment_id = "exp_f1a_extra"
        specs = self._specs(2)
        extra = copy.deepcopy(specs[0])
        extra["cell_id"] = "ghost"
        self._matrix_with_raw_definition(
            experiment_id, [*copy.deepcopy(specs), extra]
        )
        claim = self.repo.atomically_claim_queued_attempt("a")
        assert claim is not None
        self.repo.record_terminal(claim.attempt.run_id, "a", "interrupted")
        await self._assert_fail_closed(
            experiment_id, before_counts={"a": 1, "b": 1}
        )

    async def test_duplicate_persisted_cell_ids_fail_closed(self):
        experiment_id = "exp_f1a_dup"
        specs = self._specs(2)
        self._matrix_with_raw_definition(
            experiment_id, [copy.deepcopy(specs[0]), copy.deepcopy(specs[0])]
        )
        claim = self.repo.atomically_claim_queued_attempt("a")
        assert claim is not None
        self.repo.record_terminal(claim.attempt.run_id, "a", "interrupted")
        await self._assert_fail_closed(
            experiment_id, before_counts={"a": 1, "b": 1}
        )

    async def test_resumable_cell_without_execution_plan_fails_closed(self):
        experiment_id = "exp_f1a_no_exec_plan"
        specs = self._specs(2)
        stripped = copy.deepcopy(specs)
        stripped[1].pop("execution_plan")
        self._matrix_with_raw_definition(experiment_id, stripped)
        claim = self.repo.atomically_claim_queued_attempt("a")
        assert claim is not None
        self.repo.record_terminal(claim.attempt.run_id, "a", "interrupted")
        # Cell "b" remains queued with no mapping execution_plan → reject.
        await self._assert_fail_closed(
            experiment_id, before_counts={"a": 1, "b": 1}
        )

    async def test_interrupted_cell_without_execution_plan_fails_closed(self):
        experiment_id = "exp_f1a_interrupted_no_plan"
        specs = self._specs(2)
        stripped = copy.deepcopy(specs)
        stripped[0].pop("execution_plan")
        self._matrix_with_raw_definition(experiment_id, stripped)
        claim = self.repo.atomically_claim_queued_attempt("a")
        assert claim is not None
        self.repo.record_terminal(claim.attempt.run_id, "a", "interrupted")
        await self._assert_fail_closed(
            experiment_id, before_counts={"a": 1, "b": 1}
        )

    async def test_duplicate_resume_race_has_one_scheduler_and_one_execution_per_cell(self):
        experiment_id = "exp_f1a_race"
        self._matrix(experiment_id)
        claim = self.repo.atomically_claim_queued_attempt("a")
        assert claim is not None
        self.repo.record_terminal(claim.attempt.run_id, "a", "interrupted")
        recorder = _ExecuteRecorder()
        with mock.patch.object(canonical_execution, "execute_plan", new=recorder):
            results = await asyncio.gather(
                self._post(experiment_id),
                self._post(experiment_id),
            )
        self.assertTrue(all(status == 200 for status, _body in results))
        created = [
            entry
            for _status, body in results
            for entry in body.get("created_attempts", [])
        ]
        self.assertEqual(len(created), 1)
        self.assertEqual(len({entry["cell_id"] for entry in created}), 1)
        schedulers = [
            scheduler
            for scheduler in ems._SCHEDULERS.values()
            if scheduler.experiment_id == experiment_id
        ]
        self.assertEqual(len(schedulers), 1)
        await self._wait_cells_terminal(["a", "b"])
        self.assertEqual(len(recorder.plans), 2)


if __name__ == "__main__":
    unittest.main()
