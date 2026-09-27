"""Deterministic Batch D6A backend integration coverage.

This suite joins the existing modern planner, History V2 repository, bounded
scheduler, lifecycle routes, and cooperative cancellation seams. It uses only
temporary SQLite state and in-process fakes; it never deploys, imports Modal,
or performs generation.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import experiment_modern_plan as planner
import experiment_modern_routes as routes
import experiment_modern_scheduler as scheduler_mod
from comfymodal_runtime.contracts import ExecutionPlan
from history_v2_models import ExperimentCell, derive_experiment_status
from history_v2_repository import HistoryV2Repository
from history_v2_store import HistoryV2Store


T0 = "2026-08-16T00:00:00.000+00:00"


def _execution_plan(cell_id: str, *, version: str = "wv_frozen", identity: dict | None = None) -> dict:
    return ExecutionPlan(
        workflow={"1": {"class_type": "SaveImage", "inputs": {"filename_prefix": cell_id}}},
        workflow_hash=f"wh_{cell_id}",
        source_workflow_hash=f"source_{cell_id}",
        output_node_ids=("1",),
        request_metadata={"request_id": f"req_{cell_id}", "workflow_version_id": version},
        deployment_identity=identity or {"deployment_id": "dep_frozen", "revision": "r1"},
    ).to_dict()


def _spec(
    cell_id: str,
    position: int | None = None,
    *,
    version: str = "wv_frozen",
    preset: str = "preset_frozen",
    error: str | None = None,
    error_code: str | None = None,
    workflow: dict | None = None,
    execution_plan: dict | None = None,
) -> dict:
    spec = {
        "cell_id": cell_id,
        "position": position,
        "axis_labels": ["seed"],
        "axis_values": {"seed": 7},
        "axis_to_control": {"seed": "seed"},
        "controls": {"seed": 7},
        "merged_values": {"seed": 7},
        "workflow_id": "wf_frozen",
        "workflow_version_id": version,
        "preset_id": preset,
        "workflow_name": "Frozen Workflow",
        "preset_name": "Frozen Preset",
        "plan_hash": f"plan_{cell_id}",
        "workflow_hash": f"wh_{cell_id}",
        "execution_plan": execution_plan or _execution_plan(cell_id, version=version),
    }
    if workflow is not None:
        spec["workflow"] = workflow
    if error is not None:
        spec["error"] = error
    if error_code is not None:
        spec["error_code"] = error_code
    return spec


def _definition(specs: list[dict]) -> dict:
    return {"version": 2, "contract": "modern_v2", "cells": list(specs)}


class _FakePlannerCell:
    def __init__(self, spec: dict):
        self._spec = dict(spec)
        self.cell_id = spec["cell_id"]
        self.ok = not bool(spec.get("error") or spec.get("error_code"))
        self.error = spec.get("error")

    def to_dict(self) -> dict:
        return dict(self._spec)


class _FakeCellPlan:
    def __init__(self, specs: list[dict]):
        self.cells = [_FakePlannerCell(spec) for spec in specs]
        self.cell_ordering = [cell.cell_id for cell in self.cells]
        self.axis_labels = ["seed"]
        self.modal_options = {}
        self.workflow_branches = []


class _FakePlanner:
    class ExperimentDefinitionError(Exception):
        pass

    def __init__(self, specs: list[dict]):
        self.specs = specs

    def build_cell_plan(self, definition, node_dir=None):
        return _FakeCellPlan(self.specs)


class _CountingExecutor:
    def __init__(self, delay: float = 0.0, failures: dict[str, str] | None = None):
        self.delay = delay
        self.failures = failures or {}
        self.active = 0
        self.peak = 0
        self.started: list[tuple[str, str]] = []
        self.events: list[tuple[str, str]] = []
        self.received: dict[str, object] = {}
        self.gates: dict[str, asyncio.Event] = {}

    async def __call__(self, plan, *, attempt_id, cell_id):
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.started.append((cell_id, attempt_id))
        self.events.append(("started", cell_id))
        self.received[cell_id] = plan
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            gate = self.gates.get(cell_id)
            if gate is not None:
                await gate.wait()
            if cell_id in self.failures:
                raise RuntimeError(self.failures[cell_id])
        finally:
            self.active -= 1
            self.events.append(("finished", cell_id))


class _RouteCancelScheduler:
    remote_cancel_available = True

    def __init__(self, repo: HistoryV2Repository):
        self.repo = repo
        self.calls: list[str] = []

    async def cancel_cell(self, cell_id: str, *, reason: str = "user_cancel"):
        self.calls.append(cell_id)
        current = self.repo.read_active_attempt(cell_id)
        if current is not None:
            self.repo.record_terminal(current.run_id, cell_id, "canceled", error=reason)
        return "canceled_running"


class _FailingConnection:
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    def execute(self, sql, params=()):
        if sql.lstrip().upper().startswith("INSERT INTO RUN_ATTEMPTS"):
            raise RuntimeError("injected D6A persistence failure")
        return self._connection.execute(sql, tuple(params))

    def __getattr__(self, name):
        return getattr(self._connection, name)


class _FailingStore(HistoryV2Store):
    @contextmanager
    def transaction(self):
        connection = self.connect()
        connection.execute("BEGIN IMMEDIATE")
        proxy = _FailingConnection(connection)
        try:
            yield proxy
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        else:
            connection.execute("COMMIT")
        finally:
            connection.close()


async def _drain(sched, timeout: float = 20.0):
    async def wait_for_drain():
        while True:
            if (sched._dispatch_task is None or sched._dispatch_task.done()) and not sched._active_tasks:
                return
            await asyncio.sleep(0.002)

    await asyncio.wait_for(wait_for_drain(), timeout)


async def _wait_until(predicate, timeout: float = 5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition was not reached")
        await asyncio.sleep(0.002)


class D6ARepositorySchedulerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = HistoryV2Store(self.root / ".studio_history_v2" / "history_v2.db")
        self.repo = HistoryV2Repository(self.store)
        self.schedulers: list[scheduler_mod.ExperimentModernScheduler] = []

    async def asyncTearDown(self):
        for sched in self.schedulers:
            if not sched._shutdown_done:
                await sched.shutdown()
        for experiment_id in list(scheduler_mod._SCHEDULERS):
            scheduler_mod.unregister_scheduler(experiment_id)

    def _matrix(self, experiment_id: str, specs: list[dict]):
        return self.repo.create_modern_matrix(
            experiment_id=experiment_id,
            name=experiment_id,
            definition=_definition(specs),
            cells=specs,
            created_at=T0,
        )

    def _stored_plans(self, detail):
        return list(detail.experiment.definition["cells"])

    def _scheduler(self, experiment_id: str, detail, execute, remote_cancel=None, concurrency=None):
        bound = HistoryV2Repository(self.store, experiment_id=experiment_id)
        kwargs = {} if concurrency is None else {"concurrency": concurrency}
        sched = scheduler_mod.ExperimentModernScheduler(
            experiment_id,
            self._stored_plans(detail),
            bound,
            execute=execute,
            remote_cancel=remote_cancel or (lambda *args, **kwargs: True),
            **kwargs,
        )
        self.schedulers.append(sched)
        return sched, bound

    async def test_planner_matrix_persists_frozen_plan_and_interface_fields(self):
        repaired_workflow = {"1": {"class_type": "SaveImage", "inputs": {"filename_prefix": "fixed"}}}
        execution = ExecutionPlan(
            workflow=repaired_workflow,
            workflow_hash="repaired_hash",
            source_workflow_hash="source_hash",
            output_node_ids=("1",),
            request_metadata={"request_id": "req_plan"},
            deployment_identity={"deployment_id": "dep_plan", "revision": "r2"},
        )
        bundle = {
            "status": "ok",
            "workflow": {"workflow_id": "wf_plan", "name": "Frozen Workflow"},
            "version": {"workflow_version_id": "wv_plan", "version_number": 4, "graph_hash": "source_hash"},
            "preset": {"preset_id": "preset_plan", "name": "Preset", "values": {"seed": 1}},
            "control_schema": {"cfg": {}},
            "executable_prompt": repaired_workflow,
        }
        with mock.patch.object(planner._seam, "resolve_workflow_run_bundle", return_value=bundle), \
             mock.patch.object(planner._seam, "validate_workflow_controls", return_value=[]), \
             mock.patch.object(planner._seam, "merge_workflow_controls", return_value={"values": {"cfg": 9}, "errors": []}), \
             mock.patch.object(planner._seam, "build_workflow_execution_plan", return_value=(execution, None)):
            plan = planner.build_cell_plan(
                {
                    "experiment_id": "exp_plan_matrix",
                    "workflows": [{"workflow_id": "wf_plan", "workflow_version_id": "wv_plan", "preset_id": "preset_plan"}],
                    "axes": {"guidance": {"values": [9]}},
                },
                self.root,
            )
        detail = self._matrix("exp_plan_matrix", [cell.to_dict() for cell in plan.cells])
        cell = detail.cells[0]
        snapshot = self.repo.get_generation(cell.generation_id).request_snapshot
        self.assertEqual(cell.position, 0)
        self.assertEqual(cell.axis_labels, {"guidance": 9})
        self.assertEqual(snapshot.request["axis_to_control"], {"guidance": "cfg"})
        self.assertEqual(snapshot.request["merged_values"], {"cfg": 9})
        self.assertEqual(snapshot.request["workflow_version_id"], "wv_plan")
        self.assertEqual(snapshot.execution_plan["workflow_hash"], "repaired_hash")
        self.assertEqual(snapshot.deployment_identity, {"deployment_id": "dep_plan", "revision": "r2"})

    async def test_immutable_queued_replay_never_reresolves_latest_or_default(self):
        specs = [_spec("cell_replay", version="wv_old", preset="preset_old")]
        detail = self._matrix("exp_replay", specs)
        mutable_domain = {"latest_version_id": "wv_new", "default_preset_id": "preset_new", "values": {"seed": 999}}
        received = []

        async def execute(plan, *, attempt_id, cell_id):
            received.append(json.loads(json.dumps(plan)))

        with mock.patch.object(planner._seam, "resolve_workflow_run_bundle", side_effect=AssertionError("re-resolution")):
            sched, _bound = self._scheduler("exp_replay", detail, execute)
            await sched.start()
            await _drain(sched)
        self.assertEqual(mutable_domain["latest_version_id"], "wv_new")
        self.assertEqual(received[0]["workflow_version_id"], "wv_old")
        self.assertEqual(received[0]["preset_id"], "preset_old")
        self.assertEqual(received[0]["workflow_hash"], "wh_cell_replay")

    async def test_atomic_matrix_sizes_one_two_forty_have_no_orphans(self):
        for count in (1, 2, 40):
            experiment_id = f"exp_size_{count}"
            specs = [_spec(f"{experiment_id}_cell_{i}", i) for i in range(count)]
            detail = self._matrix(experiment_id, specs)
            self.assertEqual(len(detail.cells), count)
            self.assertEqual(detail.experiment.cell_ordering, [spec["cell_id"] for spec in specs])
            self.assertEqual(sum(len(self.repo.get_generation(c.generation_id).attempts) for c in detail.cells), count)
            self.assertEqual(
                self.store.execute(
                    "SELECT COUNT(*) FROM experiments WHERE experiment_id = ?",
                    (experiment_id,),
                )[0][0],
                1,
            )
            self.assertEqual(
                self.store.execute(
                    "SELECT COUNT(*) FROM experiment_cells WHERE experiment_id = ?",
                    (experiment_id,),
                )[0][0],
                count,
            )

    async def test_atomic_creation_rolls_back_mid_matrix(self):
        failing_store = _FailingStore(self.root / "failing" / ".studio_history_v2" / "history_v2.db")
        failing_store.initialize()
        repo = HistoryV2Repository(failing_store)
        specs = [_spec("rollback_a", 0), _spec("rollback_b", 1)]
        with self.assertRaises(RuntimeError):
            repo.create_modern_matrix(
                experiment_id="exp_rollback",
                name="rollback",
                definition=_definition(specs),
                cells=specs,
            )
        for table in ("experiments", "experiment_cells", "generations", "run_attempts", "request_snapshots"):
            self.assertEqual(failing_store.execute(f"SELECT COUNT(*) FROM {table}")[0][0], 0, table)

    async def test_planning_invalid_cell_fails_without_submission_and_siblings_complete(self):
        specs = [
            _spec("valid_a", 0),
            _spec("invalid_mapping", 1, error="control 'cfg' is not exposed", error_code="WORKFLOW_CONTROL_VALIDATION"),
            _spec("valid_c", 2),
        ]
        detail = self._matrix("exp_invalid", specs)
        execute = _CountingExecutor()
        sched, bound = self._scheduler("exp_invalid", detail, execute)
        await sched.start()
        await _drain(sched)
        self.assertEqual([cell_id for cell_id, _ in execute.started], ["valid_a", "valid_c"])
        self.assertEqual(bound.read_active_attempt("invalid_mapping").status, "failed")
        self.assertEqual(bound.read_active_attempt("invalid_mapping").error, "control 'cfg' is not exposed")
        self.assertEqual(await sched.status(), "completed_with_failures")

    async def test_scheduler_global_width_six_and_continuous_fill(self):
        specs = [_spec(f"width_{i}", i) for i in range(40)]
        detail = self._matrix("exp_width", specs)
        execute = _CountingExecutor(delay=0.003)
        sched, _bound = self._scheduler("exp_width", detail, execute, concurrency=40)
        await sched.start()
        await _drain(sched)
        self.assertEqual(sched.concurrency, 6)
        self.assertLessEqual(execute.peak, 6)
        self.assertEqual(len(execute.started), 40)
        first_finish = next(i for i, event in enumerate(execute.events) if event[0] == "finished")
        self.assertEqual(sum(event[0] == "started" for event in execute.events[:first_finish]), 6)

    async def test_scheduler_runtime_failures_isolate_siblings_without_retry(self):
        specs = [_spec(f"failure_{i}", i) for i in range(5)]
        detail = self._matrix("exp_failure", specs)
        execute = _CountingExecutor(failures={"failure_1": "boom", "failure_3": "bad"})
        sched, bound = self._scheduler("exp_failure", detail, execute)
        await sched.start()
        await _drain(sched)
        self.assertEqual(bound.read_active_attempt("failure_1").status, "failed")
        self.assertEqual(bound.read_active_attempt("failure_3").status, "failed")
        self.assertEqual(len(bound.get_attempts_for_cells(["failure_1"])), 1)
        self.assertEqual(len(execute.started), 5)
        self.assertEqual(await sched.status(), "completed_with_failures")

    async def test_queued_cancel_has_zero_execute_calls_and_preserves_grid(self):
        specs = [_spec(f"queued_{i}", i) for i in range(8)]
        detail = self._matrix("exp_queued_cancel", specs)
        execute = _CountingExecutor()
        sched, bound = self._scheduler("exp_queued_cancel", detail, execute)
        counts = await sched.cancel_experiment()
        self.assertEqual(counts["canceled_queued"], 8)
        self.assertEqual(execute.started, [])
        self.assertEqual([c.cell_id for c in bound.get_experiment("exp_queued_cancel").cells], [s["cell_id"] for s in specs])
        self.assertTrue(all(bound.read_active_attempt(s["cell_id"]).status == "canceled" for s in specs))

    async def test_cancel_completion_races_are_first_terminal_wins(self):
        completed_specs = [_spec("completion_first", 0)]
        completed_detail = self._matrix("exp_completion_first", completed_specs)
        completed_execute = _CountingExecutor()
        completed_sched, completed_bound = self._scheduler("exp_completion_first", completed_detail, completed_execute)
        await completed_sched.start()
        await _drain(completed_sched)
        self.assertEqual(await completed_sched.cancel_cell("completion_first"), "noop")
        self.assertEqual(completed_bound.read_active_attempt("completion_first").status, "completed")

        canceled_specs = [_spec("cancel_first", 0)]
        canceled_detail = self._matrix("exp_cancel_first", canceled_specs)
        gate = asyncio.Event()
        canceled_execute = _CountingExecutor()
        canceled_execute.gates["cancel_first"] = gate
        canceled_sched, canceled_bound = self._scheduler("exp_cancel_first", canceled_detail, canceled_execute, remote_cancel=lambda *args, **kwargs: True)
        await canceled_sched.start()
        await _wait_until(lambda: bool(canceled_execute.started))
        self.assertEqual(await canceled_sched.cancel_cell("cancel_first"), "canceled_running")
        gate.set()
        await _drain(canceled_sched)
        self.assertEqual(canceled_bound.read_active_attempt("cancel_first").status, "canceled")
        self.assertFalse(canceled_bound.record_terminal(canceled_execute.started[0][1], "cancel_first", "completed"))

    async def test_shutdown_recovery_running_to_interrupted_is_idempotent(self):
        specs = [_spec(f"recover_{i}", i) for i in range(4)]
        detail = self._matrix("exp_recover", specs)
        bound = HistoryV2Repository(self.store, experiment_id="exp_recover")
        bound.record_terminal(bound.read_active_attempt("recover_0").run_id, "recover_0", "completed")
        bound.record_terminal(bound.read_active_attempt("recover_1").run_id, "recover_1", "failed", error="boom")
        recover_run = bound.read_active_attempt("recover_2").run_id
        bound.record_running(recover_run, "recover_2")
        first = await routes.startup_experiment_modern_lifecycle(self.root)
        second = await routes.startup_experiment_modern_lifecycle(self.root)
        self.assertEqual(first["marked_interrupted"], [recover_run])
        self.assertEqual(second["marked_interrupted"], [])
        self.assertEqual(bound.read_active_attempt("recover_0").status, "completed")
        self.assertEqual(bound.read_active_attempt("recover_1").status, "failed")
        self.assertEqual(bound.read_active_attempt("recover_2").status, "interrupted")
        self.assertEqual(bound.read_active_attempt("recover_3").status, "queued")

    async def test_resume_and_retry_reuse_generation_and_snapshot(self):
        specs = [_spec(f"action_{i}", i) for i in range(5)]
        detail = self._matrix("exp_actions", specs)
        bound = HistoryV2Repository(self.store, experiment_id="exp_actions")
        for cid, status in (("action_0", "completed"), ("action_1", "failed"), ("action_2", "canceled"), ("action_3", "interrupted")):
            run_id = bound.read_active_attempt(cid).run_id
            bound.record_terminal(run_id, cid, status, error="old" if status == "failed" else None)
        old_generation = bound.get_experiment_cell("action_3").generation_id
        old_snapshot = bound.get_generation(old_generation).request_snapshot.to_dict()
        failed_run = bound.get_attempts_for_cells(["action_1"])[0].run_id
        failed_generation = bound.get_experiment_cell("action_1").generation_id
        app = web.Application()
        registry = {}
        routes.register_experiment_modern_routes(app.router, self.root, registry=registry)
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            response = await client.post("/comfymodal/history-v2/experiments/exp_actions/resume")
            data = await response.json()
            self.assertEqual(response.status, 200)
            self.assertEqual(data["resumed"], 1)
            self.assertEqual(len(bound.get_attempts_for_cells(["action_3"])), 2)
            self.assertEqual(len(bound.get_attempts_for_cells(["action_4"])), 1)
            self.assertEqual(bound.get_experiment_cell("action_3").generation_id, old_generation)
            self.assertEqual(bound.get_generation(old_generation).request_snapshot.to_dict(), old_snapshot)
            again = await client.post("/comfymodal/history-v2/experiments/exp_actions/resume")
            again_data = await again.json()
            self.assertEqual(again_data["resumed"], 0)
            retry = await client.post("/comfymodal/history-v2/experiments/exp_actions/cells/action_1/retry")
            retry_data = await retry.json()
            self.assertEqual(retry.status, 200)
            self.assertNotEqual(retry_data["run_id"], failed_run)
            self.assertEqual(bound.get_experiment_cell("action_1").generation_id, failed_generation)
            nonfailed = await client.post("/comfymodal/history-v2/experiments/exp_actions/cells/action_0/retry")
            self.assertEqual(nonfailed.status, 409)
            self.assertEqual((await nonfailed.json())["code"], "CELL_NOT_FAILED")
        finally:
            await client.close()

    async def test_stale_duplicate_progress_and_terminal_events_cannot_replace_retry(self):
        specs = [_spec("stale", 0)]
        detail = self._matrix("exp_stale", specs)
        bound = HistoryV2Repository(self.store, experiment_id="exp_stale")
        old_run = bound.read_active_attempt("stale").run_id
        bound.record_terminal(old_run, "stale", "failed", error="first")
        retry = bound.create_retry_attempt("stale")
        new_run = retry.attempt.run_id
        sched, _ = self._scheduler("exp_stale", detail, _CountingExecutor())
        self.assertFalse(await sched.handle_progress("stale", old_run, {"step": 1}))
        self.assertFalse(await sched.handle_terminal("stale", old_run, "completed"))
        self.assertTrue(await sched.handle_terminal("stale", new_run, "completed"))
        self.assertFalse(await sched.handle_terminal("stale", new_run, "failed"))
        self.assertEqual(bound.read_active_attempt("stale").status, "completed")

    async def test_aggregate_truth_table_has_no_partial(self):
        cases = {
            ("completed",): "completed",
            ("completed", "failed"): "completed_with_failures",
            ("completed", "canceled"): "canceled",
            ("failed", "canceled"): "canceled",
            ("failed", "interrupted"): "interrupted",
            ("canceled", "interrupted"): "interrupted",
            ("queued", "failed"): "running",
            ("running", "canceled"): "running",
        }
        for index, (statuses, expected) in enumerate(cases.items()):
            cells = [ExperimentCell(f"agg_{index}_{i}", "exp", i, status, T0) for i, status in enumerate(statuses)]
            result = derive_experiment_status(cells)
            self.assertEqual(result, expected)
            self.assertNotEqual(result, "partial")

    async def test_deployment_identity_rehydrates_without_manufacturing(self):
        identity = {"deployment_id": "dep_d6a", "revision": "2026.08.16", "registry_fingerprint": "fp"}
        specs = [_spec("identity", 0, execution_plan=_execution_plan("identity", identity=identity))]
        detail = self._matrix("exp_identity", specs)
        cell = detail.cells[0]
        snapshot = self.repo.get_generation(cell.generation_id).request_snapshot
        rehydrated = ExecutionPlan.from_dict(snapshot.execution_plan)
        self.assertEqual(rehydrated.deployment_identity, identity)
        self.assertEqual(snapshot.deployment_identity, identity)
        self.assertEqual(rehydrated.workflow_hash, "wh_identity")
        self.assertNotIn(".deployed_state.json", json.dumps(snapshot.to_dict()))

    async def test_phase_c_repaired_graph_uses_single_modern_builder_and_stored_version_stays_raw(self):
        raw_workflow = {
            "67": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive"}},
            "169": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
            "62": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors"}},
        }
        repaired = json.loads(json.dumps(raw_workflow))
        repaired["67"]["inputs"]["clip"] = ["62", 0]
        repaired["169"]["inputs"]["clip"] = ["62", 0]
        built = ExecutionPlan(workflow=repaired, workflow_hash="repaired", source_workflow_hash="raw")
        bundle = {
            "status": "ok",
            "workflow": {"workflow_id": "wf_repair", "name": "Repair"},
            "version": {"workflow_version_id": "wv_raw", "version_number": 1, "graph_hash": "raw"},
            "preset": {"preset_id": "preset_raw", "name": "Preset", "values": {}},
            "control_schema": {},
            "executable_prompt": raw_workflow,
        }
        with mock.patch.object(planner._seam, "resolve_workflow_run_bundle", return_value=bundle) as resolve, \
             mock.patch.object(planner._seam, "validate_workflow_controls", return_value=[]), \
             mock.patch.object(planner._seam, "merge_workflow_controls", return_value={"values": {}, "errors": []}), \
             mock.patch.object(planner._seam, "build_workflow_execution_plan", return_value=(built, None)) as build:
            plan = planner.build_cell_plan(
                {"experiment_id": "exp_repair", "workflows": [{"workflow_id": "wf_repair", "workflow_version_id": "wv_raw", "preset_id": "preset_raw"}]},
                self.root,
            )
        self.assertEqual(resolve.call_count, 1)
        self.assertEqual(build.call_count, 1)
        self.assertEqual(plan.cells[0].workflow_version_id, "wv_raw")
        self.assertEqual(plan.cells[0].execution_plan_dict["workflow"]["67"]["inputs"]["clip"], ["62", 0])
        self.assertNotIn("clip", raw_workflow["67"]["inputs"])

    async def test_output_finalization_helpers_are_strict_and_non_fabricating(self):
        from studio_workflow_run import _resolve_output_candidate

        output = self.root / "output.png"
        output.write_bytes(b"png")
        self.assertEqual(_resolve_output_candidate(str(output)), output)
        self.assertIsNone(_resolve_output_candidate(str(self.root / "missing.png")))
        plan = ExecutionPlan(
            workflow={"1": {"class_type": "SaveImage"}},
            output_node_ids=("1",),
            deployment_identity={"deployment_id": "dep"},
        )
        serialized = plan.to_dict()
        json.dumps(serialized, allow_nan=False)
        self.assertEqual(serialized["deployment_identity"], {"deployment_id": "dep"})
        detail = self._matrix("exp_output", [_spec("output", 0)])
        cell = detail.cells[0]
        adopted = self.repo.adopt_asset(
            cell.generation_id,
            run_id=cell.attempt_ids[0],
            asset_id="producer_asset",
            reference="modal://producer/asset",
            sha256="hash",
        )
        self.assertIsNotNone(adopted)
        self.assertEqual(self.repo.get_generation(cell.generation_id).assets[0].asset_id, "producer_asset")

    async def test_lifecycle_registration_is_single_additive_modern_path(self):
        init_source = (ROOT / "__init__.py").read_text(encoding="utf-8")
        route_source = (ROOT / "experiment_modern_routes.py").read_text(encoding="utf-8")
        self.assertEqual(init_source.count("register_experiment_modern_routes("), 1)
        self.assertEqual(init_source.count("_modern_on_startup.append(_modern_experiment_startup)"), 1)
        self.assertEqual(init_source.count("_modern_on_shutdown.append(_modern_experiment_shutdown)"), 1)
        self.assertNotIn(".scheduler_state.json", route_source)
        self.assertIn("_SCHEDULERS", (ROOT / "experiment_modern_scheduler.py").read_text(encoding="utf-8"))


class D6ARouteIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = HistoryV2Store(self.root / ".studio_history_v2" / "history_v2.db")
        self.repo = HistoryV2Repository(self.store)
        self.app = web.Application()
        self.registry: dict[str, object] = {}
        routes._SHUTDOWN_FLAG[0] = False
        routes._DEFAULT_TRANSPORT_FACTORY[0] = None
        routes.register_experiment_modern_routes(self.app.router, self.root, registry=self.registry)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        routes._SHUTDOWN_FLAG[0] = False
        routes._DEFAULT_TRANSPORT_FACTORY[0] = None
        await self.client.close()

    def _matrix(self, experiment_id: str, specs: list[dict]):
        return self.repo.create_modern_matrix(
            experiment_id=experiment_id,
            name=experiment_id,
            definition=_definition(specs),
            cells=specs,
            created_at=T0,
        )

    async def _create(self, experiment_id: str, specs: list[dict]):
        body = {"experiment_id": experiment_id, "name": experiment_id, "definition": {"workflows": [{"workflow_id": "wf_frozen"}]}}
        with mock.patch.object(routes, "_load_planner", return_value=_FakePlanner(specs)):
            return await self.client.post("/comfymodal/studio/experiment-v2", json=body)

    async def test_route_create_is_atomic_modern_matrix_not_cell_only_fallback(self):
        specs = [_spec("route_a", 0), _spec("route_b", 1)]
        with mock.patch.object(routes.HistoryV2Repository, "create_experiment", side_effect=AssertionError("legacy fallback")):
            response = await self._create("exp_route_matrix", specs)
        self.assertEqual(response.status, 200)
        detail = self.repo.get_experiment("exp_route_matrix")
        self.assertEqual(detail.experiment.expected_cell_count, 2)
        self.assertEqual([cell.position for cell in detail.cells], [0, 1])
        self.assertEqual(self.store.execute("SELECT COUNT(*) FROM request_snapshots")[0][0], 2)

    async def test_running_cancel_unavailable_returns_503_and_cancels_only_queued(self):
        specs = [_spec("unavailable_running", 0), _spec("unavailable_queued", 1)]
        self._matrix("exp_unavailable", specs)
        bound = HistoryV2Repository(self.store, experiment_id="exp_unavailable")
        bound.record_running(bound.read_active_attempt("unavailable_running").run_id, "unavailable_running")
        response = await self.client.post("/comfymodal/history-v2/experiments/exp_unavailable/cancel")
        payload = await response.json()
        self.assertEqual(response.status, 503)
        self.assertEqual(payload["code"], "CANCELLATION_UNAVAILABLE")
        self.assertEqual(bound.read_active_attempt("unavailable_running").status, "running")
        self.assertEqual(bound.read_active_attempt("unavailable_queued").status, "canceled")

    async def test_running_cancel_confirmed_route_reaches_durable_terminal(self):
        specs = [_spec("confirmed_running", 0), _spec("confirmed_queued", 1)]
        self._matrix("exp_confirmed", specs)
        bound = HistoryV2Repository(self.store, experiment_id="exp_confirmed")
        bound.record_running(bound.read_active_attempt("confirmed_running").run_id, "confirmed_running")
        canceler = _RouteCancelScheduler(bound)
        self.registry["exp_confirmed"] = canceler
        response = await self.client.post("/comfymodal/history-v2/experiments/exp_confirmed/cancel")
        payload = await response.json()
        self.assertEqual(response.status, 200)
        self.assertEqual(canceler.calls, ["confirmed_running"])
        self.assertEqual(payload["aggregate_status"], "canceled")
        self.assertEqual(bound.read_active_attempt("confirmed_running").status, "canceled")
        self.assertEqual(bound.read_active_attempt("confirmed_queued").status, "canceled")

    async def test_route_resume_is_idempotent_and_retry_preserves_generation(self):
        specs = [_spec(f"route_action_{i}", i) for i in range(5)]
        self._matrix("exp_route_actions", specs)
        bound = HistoryV2Repository(self.store, experiment_id="exp_route_actions")
        for cid, status in (("route_action_0", "completed"), ("route_action_1", "failed"), ("route_action_2", "canceled"), ("route_action_3", "interrupted")):
            run = bound.read_active_attempt(cid).run_id
            bound.record_terminal(run, cid, status, error="failure" if status == "failed" else None)
        generation = bound.get_experiment_cell("route_action_1").generation_id
        failed_run = bound.get_attempts_for_cells(["route_action_1"])[0].run_id
        response = await self.client.post("/comfymodal/history-v2/experiments/exp_route_actions/resume")
        self.assertEqual((await response.json())["resumed"], 1)
        response = await self.client.post("/comfymodal/history-v2/experiments/exp_route_actions/resume")
        self.assertEqual((await response.json())["resumed"], 0)
        retry = await self.client.post("/comfymodal/history-v2/experiments/exp_route_actions/cells/route_action_1/retry")
        retry_data = await retry.json()
        self.assertEqual(retry.status, 200)
        self.assertEqual(bound.get_experiment_cell("route_action_1").generation_id, generation)
        self.assertEqual(len(bound.get_attempts_for_cells(["route_action_1"])), 2)
        self.assertNotEqual(retry_data["run_id"], failed_run)

    async def test_route_status_projection_fixed_order_and_aggregate_matrix(self):
        specs = [_spec("status_a", 0), _spec("status_b", 1), _spec("status_c", 2)]
        self._matrix("exp_status_projection", specs)
        bound = HistoryV2Repository(self.store, experiment_id="exp_status_projection")
        bound.record_terminal(bound.read_active_attempt("status_a").run_id, "status_a", "completed")
        bound.record_terminal(bound.read_active_attempt("status_b").run_id, "status_b", "failed", error="boom")
        bound.record_terminal(bound.read_active_attempt("status_c").run_id, "status_c", "canceled")
        response = await self.client.get("/comfymodal/history-v2/experiments/exp_status_projection/status")
        payload = await response.json()
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["aggregate_status"], "canceled")
        self.assertEqual([cell["position"] for cell in payload["cells"]], [0, 1, 2])
        self.assertEqual([cell["cell_id"] for cell in payload["cells"]], ["status_a", "status_b", "status_c"])
        self.assertNotIn("partial", json.dumps(payload))

    async def test_lifecycle_routes_are_additive_and_startup_hook_is_idempotent(self):
        paths = {route.resource.canonical for route in self.app.router.routes()}
        self.assertIn("/comfymodal/studio/experiment-v2", paths)
        self.assertIn("/comfymodal/history-v2/experiments/{experiment_id}/status", paths)
        self.assertIn("/comfymodal/history-v2/experiments/{experiment_id}/cancel", paths)
        self.assertIn("/comfymodal/history-v2/experiments/{experiment_id}/resume", paths)
        self.assertIn("/comfymodal/history-v2/experiments/{experiment_id}/cells/{cell_id}/retry", paths)
        specs = [_spec("lifecycle_running", 0)]
        self._matrix("exp_lifecycle", specs)
        bound = HistoryV2Repository(self.store, experiment_id="exp_lifecycle")
        lifecycle_run = bound.read_active_attempt("lifecycle_running").run_id
        bound.record_running(lifecycle_run, "lifecycle_running")
        first = await routes.startup_experiment_modern_lifecycle(self.root, registry=self.registry)
        second = await routes.startup_experiment_modern_lifecycle(self.root, registry=self.registry)
        self.assertEqual(first["marked_interrupted"], [lifecycle_run])
        self.assertEqual(second["marked_interrupted"], [])
        self.assertEqual(bound.read_active_attempt("lifecycle_running").status, "interrupted")


if __name__ == "__main__":
    unittest.main()
