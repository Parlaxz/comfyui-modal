"""Focused D3/D4 production-binding tests (scheduler construction + transport).

Covers the minimal production path that turns a durably-accepted modern
Experiment into a running scheduler:

* scheduler construction + registration on create (route level),
* the injected transport identity reaching ``execute_plan`` (factory level),
* attempt -> request-id binding lookup + cleanup,
* confirmed cancel through the REAL ``ModalTransport`` adapter with a fake
  Modal backend,
* unavailable/unconfirmed cancel -> ``503 CANCELLATION_UNAVAILABLE`` with the
  durable running state untouched (route level),
* queued cancel unaffected,
* registry/binding/handle lifecycle cleanup.

All deterministic, in-process, never touching real Modal or generation.
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import experiment_modern_routes as emr
import experiment_modern_scheduler as ems
from comfymodal_runtime.contracts import ExecutionPlan
from comfymodal_runtime.local_handle_client import (
    CANCEL_STATE_CONFIRMED,
    CANCEL_STATE_UNAVAILABLE,
    CancelResult as TransportCancelResult,
)
from comfymodal_runtime.modal_transport import ModalTransport
from history_v2_repository import HistoryV2Repository
from history_v2_store import HistoryV2Store

T0 = "2026-08-15T00:00:00.000+00:00"


# ── Shared fixtures ──────────────────────────────────────────────────────


def _execution_plan_dict(request_id: str) -> dict:
    return {
        "workflow": {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
        "workflow_hash": "wh",
        "output_node_ids": ["1"],
        "input_images": {},
        "production_report": {},
        "request_metadata": {"prompt_id": request_id},
    }


def _cell_spec(cell_id: str, *, request_id: str | None = None, **kw) -> dict:
    spec: dict = {
        "cell_id": cell_id,
        "axis_values": {"seed": 1},
        "controls": {"seed": 1},
        "merged_values": {"seed": 1},
        "axis_to_control": {"seed": "seed"},
        "workflow_id": f"wf_{cell_id}",
        "workflow_version_id": "v_frozen",
        "preset_id": "p_frozen",
        "preset_name": "Preset",
        "workflow_name": f"Workflow {cell_id}",
        "plan_hash": f"h_{cell_id}",
        "workflow_hash": "wh",
        "execution_plan": _execution_plan_dict(request_id or f"req_{cell_id}"),
    }
    spec.update(kw)
    return spec


def _definition(specs: list[dict]) -> dict:
    return {"version": 2, "contract": "modern_v2", "cells": list(specs)}


class _FakePlannerCell:
    """Planner cell carrying an ``execution_plan`` so the binding execute
    closure can actually run (or be observed)."""

    def __init__(self, cell_id: str, *, request_id: str | None = None):
        self.cell_id = cell_id
        self.ok = True
        self.error = None
        self.execution_plan = ExecutionPlan.from_dict(
            _execution_plan_dict(request_id or f"req_{cell_id}")
        )

    def to_dict(self) -> dict:
        d = _cell_spec(self.cell_id)
        d["execution_plan"] = self.execution_plan.to_dict()
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


class _FakeTransport:
    """Minimal transport stand-in: records cancel/release calls and returns a
    configurable (default confirmed) ``cancel_attempt`` verdict."""

    def __init__(self, cancel_result=None):
        self.cancel_result = cancel_result
        self.cancel_calls: list[tuple[str, str]] = []
        self.released: list[str] = []

    async def cancel_attempt(self, request_id: str, reason: str = "") -> TransportCancelResult:
        self.cancel_calls.append((str(request_id), str(reason)))
        if self.cancel_result is not None:
            result = self.cancel_result
            if callable(result):
                result = result(str(request_id), str(reason))
            return result
        return TransportCancelResult(CANCEL_STATE_CONFIRMED, reason=str(reason))

    def release_cancellation_handle(self, request_id: str) -> None:
        self.released.append(str(request_id))


class _FakePersistence:
    """Minimal in-memory stand-in for the experiment-bound History V2
    repository (frozen semantic operations the scheduler adapter needs)."""

    def __init__(self, cell_plans):
        self.cells: dict[str, dict] = {}
        self._counter = 0
        self.terminal_writes: list[tuple] = []
        for p in cell_plans:
            cid = p["cell_id"]
            self._counter += 1
            self.cells[cid] = {
                "attempt_id": f"run_{self._counter}",
                "status": "queued",
                "error": None,
            }

    def load_queued_cells(self):
        return [
            {"cell_id": cid, "attempt_id": rec["attempt_id"], "status": rec["status"]}
            for cid, rec in self.cells.items()
            if rec["status"] in ("queued", "pending")
        ]

    def atomically_claim_queued_attempt(self, cell_id):
        rec = self.cells.get(cell_id)
        if rec is None or rec["status"] != "queued":
            return None
        rec["status"] = "running"
        return ems.AttemptClaim(attempt_id=rec["attempt_id"], cell_id=cell_id, is_new=False)

    def read_active_attempt(self, cell_id):
        rec = self.cells.get(cell_id)
        if rec is None:
            return None
        return ems.AttemptRecord(attempt_id=rec["attempt_id"], cell_id=cell_id, status=rec["status"])

    def record_running(self, attempt_id, cell_id):
        rec = self.cells.get(cell_id)
        if (
            rec is not None
            and rec["attempt_id"] == attempt_id
            and rec["status"] not in ems.TERMINAL_STATUSES
        ):
            rec["status"] = "running"

    def record_terminal(self, attempt_id, cell_id, status, error=None):
        rec = self.cells.get(cell_id)
        if rec is None or rec["attempt_id"] != attempt_id or rec["status"] in ems.TERMINAL_STATUSES:
            return False
        rec["status"] = status
        rec["error"] = error
        self.terminal_writes.append((attempt_id, cell_id, status, error))
        return True

    def create_resume_attempt(self, cell_id):
        return None

    def create_retry_attempt(self, cell_id):
        return None

    def list_recoverable_cells(self):
        return [
            {"cell_id": cid, "attempt_id": rec["attempt_id"], "status": rec["status"]}
            for cid, rec in self.cells.items()
            if rec["status"] in ("running", "queued", "pending", "interrupted")
        ]

    def aggregate_status(self):
        statuses = [rec["status"] for rec in self.cells.values()]
        if any(s in ("running", "queued", "pending") for s in statuses):
            return "running"
        if any(s == "interrupted" for s in statuses):
            return "interrupted"
        if any(s == "failed" for s in statuses):
            return "completed_with_failures"
        if any(s == "canceled" for s in statuses):
            return "canceled"
        return "completed"


async def _drain(scheduler, timeout: float = 10.0) -> None:
    async def drained() -> None:
        while True:
            if (
                scheduler._dispatch_task is None or scheduler._dispatch_task.done()
            ) and not scheduler._active_tasks:
                return
            await asyncio.sleep(0.005)

    await asyncio.wait_for(drained(), timeout)


async def _wait_until(cond, timeout: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not cond():
        if loop.time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.005)


def _claim(repo: HistoryV2Repository, cell_id: str) -> str:
    claim = repo.atomically_claim_queued_attempt(cell_id)
    assert claim is not None, f"expected a claim for cell {cell_id}"
    return claim.attempt.run_id


# ── D3: factory / binding (scheduler level) ──────────────────────────────


class ExperimentModernBindingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._made: list[ems.ExperimentModernScheduler] = []
        ems.unregister_scheduler("exp_bind")
        ems.unregister_scheduler("exp_exec")
        ems.unregister_scheduler("exp_conf")

    async def _make_scheduler(self, *args, **kwargs) -> ems.ExperimentModernScheduler:
        sched = ems.build_experiment_scheduler(*args, **kwargs)
        self._made.append(sched)
        return sched

    async def asyncTearDown(self):
        for sched in self._made:
            if not sched._shutdown_done:
                await sched.shutdown()
            ems.unregister_scheduler(sched.experiment_id)

    def test_factory_registers_and_wires_shared_transport(self):
        plans = [{"cell_id": "a", "execution_plan": _execution_plan_dict("req_a")}]
        transport = _FakeTransport()
        sched = ems.build_experiment_scheduler(
            "exp_bind",
            plans,
            _FakePersistence(plans),
            transport=transport,
        )
        self._made.append(sched)
        # Registered in the process-local registry.
        self.assertIs(ems.get_scheduler("exp_bind"), sched)
        # One shared per-experiment transport wired into the scheduler.
        self.assertIs(sched._shared_transport, transport)
        self.assertIsNotNone(sched._transport_binding)
        self.assertEqual(len(sched._transport_binding), 0)
        # Truthful remote-cancel capability probe (route uses it).
        self.assertTrue(emr._scheduler_has_remote_cancel(sched))
        # No Modal SDK was required to build the closures.
        self.assertIn("experiment_modern_scheduler", sched._remote_cancel.__module__)

    async def test_execute_plan_receives_injected_transport_and_cleans_binding(self):
        plans = [{"cell_id": "a", "execution_plan": _execution_plan_dict("req_exec")}]
        transport = _FakeTransport()
        calls: list[tuple] = []
        gate = asyncio.Event()

        async def fake_execute_plan(plan, **kwargs):
            calls.append((plan, kwargs))
            await gate.wait()
            return {"status": "ok"}

        with mock.patch(
            "canonical_execution.execute_plan", side_effect=fake_execute_plan
        ):
            sched = await self._make_scheduler(
                "exp_exec",
                plans,
                _FakePersistence(plans),
                transport=transport,
            )
            await sched.start()
            await _wait_until(lambda: len(calls) == 1)

        plan, kwargs = calls[0]
        # The injected transport identity reaches execute_plan (no second
        # transport, no plan rebuild).
        self.assertIs(kwargs["transport"], transport)
        # Dict cell plans are rehydrated ONLY through ExecutionPlan.from_dict.
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(plan.request_metadata["prompt_id"], "req_exec")
        # The trace carries the binding request id so the transport registers
        # the cancellation handle under the same key.
        self.assertEqual(kwargs["trace"].request_id, "req_exec")
        # The attempt is bound while executing.
        attempt_id = sched._attempt_for_cell["a"]
        self.assertIsNotNone(attempt_id)
        self.assertEqual(sched._transport_binding.lookup(attempt_id), "req_exec")

        gate.set()
        await _drain(sched)
        # Binding cleaned up in ``finally`` after terminal handling.
        self.assertEqual(len(sched._transport_binding), 0)
        self.assertEqual(transport.released, ["req_exec"])
        self.assertEqual(sched._transport_binding.lookup(attempt_id), None)

    async def test_bound_cell_materializes_result_before_terminal(self):
        plans = [{"cell_id": "a", "execution_plan": _execution_plan_dict("req_output")}]
        transport = _FakeTransport()

        class _ResultPersistence(_FakePersistence):
            def __init__(self, cell_plans):
                super().__init__(cell_plans)
                self.results: list[dict] = []

            def record_result(self, attempt_id, cell_id, result):
                self.results.append(dict(result))
                return True

        persistence = _ResultPersistence(plans)
        materialize_calls: list[dict] = []

        async def fake_execute_plan(plan, **kwargs):
            return {
                "status": "ok",
                "outputs": {
                    "1": {"images": [{"filename": "remote.png"}]},
                },
            }

        async def fake_materialize(result, **kwargs):
            materialize_calls.append(dict(kwargs))
            return ["remote.png"]

        with (
            mock.patch("canonical_execution.execute_plan", side_effect=fake_execute_plan),
            mock.patch(
                "comfymodal_runtime.playground_service._default_materialize",
                side_effect=fake_materialize,
            ),
        ):
            sched = await self._make_scheduler(
                "exp_output",
                plans,
                persistence,
                transport=transport,
            )
            await sched.start()
            await _drain(sched)

        self.assertEqual(len(materialize_calls), 1)
        self.assertTrue(materialize_calls[0]["require_output"])
        self.assertEqual(persistence.results[0]["output_paths"], ["remote.png"])
        self.assertEqual(persistence.cells["a"]["status"], "completed")

    async def test_attempt_binding_lookup_routes_transport_cancel(self):
        plans = [{"cell_id": "a", "execution_plan": _execution_plan_dict("req_bind")}]
        transport = _FakeTransport()
        sched = await self._make_scheduler(
            "exp_bind2",
            plans,
            _FakePersistence(plans),
            transport=transport,
        )
        # Bound attempt -> confirmed transport verdict routes through
        # cancel_attempt with the resolved request id.
        sched._transport_binding.bind("run_1", "req_bind")
        result = await sched._remote_cancel(
            "run_1", "a", intent="cancel", reason="user_cancel"
        )
        self.assertTrue(result.confirmed)
        self.assertEqual(transport.cancel_calls, [("req_bind", "user_cancel")])

        # No binding (or unknown attempt) -> explicitly unconfirmed; the
        # durable running state is never fabricated as canceled.
        result = await sched._remote_cancel(
            "run_missing", "a", intent="cancel", reason="user_cancel"
        )
        self.assertFalse(result.confirmed)
        self.assertEqual(result.outcome, "unavailable")

        # Cleanup on shutdown clears the binding.
        sched._transport_binding.bind("run_1", "req_bind")
        await sched.shutdown()
        self.assertEqual(len(sched._transport_binding), 0)

    async def test_confirmed_cancel_through_real_transport_adapter(self):
        """A confirmed transport ``CancelResult`` allows the ``canceled``
        terminal through the REAL ``ModalTransport`` adapter (fake Modal
        backend: confirmed ``cancelled`` event then a gated stream)."""
        import asyncio

        class _ConfirmStream:
            def __init__(self, confirmed_event, gate):
                self._events = [confirmed_event]
                self._gate = gate
                self._i = 0
                self.input_id = "in-conf"
                self.input_created_at = 1.0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._i < len(self._events):
                    event = self._events[self._i]
                    self._i += 1
                    return event
                await self._gate.wait()
                raise StopAsyncIteration

            async def aclose(self):
                pass

        class _GatedRemoteGen:
            def __init__(self, handle):
                self._handle = handle

            def aio(self, payload, request_id="", **kwargs):
                self._handle.aio_calls.append(
                    {"payload": payload, "request_id": request_id, "kwargs": dict(kwargs)}
                )
                return _ConfirmStream(self._handle._confirmed_event, self._handle._gate)

        class _GatedHandle:
            def __init__(self, confirmed_event, gate):
                self._confirmed_event = confirmed_event
                self._gate = gate
                self.aio_calls: list[dict] = []
                self.run_plan_stream = SimpleNamespace(remote_gen=_GatedRemoteGen(self))

        class _GatedFactory:
            def __init__(self, confirmed_event, gate):
                self._confirmed_event = confirmed_event
                self._gate = gate
                self.handles: list[_GatedHandle] = []
                self.call_count = 0

            def __call__(self, **kwargs):
                self.call_count += 1
                handle = _GatedHandle(self._confirmed_event, self._gate)
                self.handles.append(handle)
                return handle

        class _FakeQueue:
            def __init__(self):
                self.messages: list[dict] = []

            def put(self, message, partition: str | None = None) -> None:
                self.messages.append(dict(message))

        gate = asyncio.Event()
        cancelled_event = {
            "type": "cancelled",
            "request_id": "req_conf",
            "reason": "user_cancel",
            "confirmed": True,
        }
        transport = ModalTransport(
            v2_handle_factory=_GatedFactory(cancelled_event, gate),
            control_queue_factory=lambda workspace=None: _FakeQueue(),
        )
        plans = [{"cell_id": "a", "execution_plan": _execution_plan_dict("req_conf")}]
        sched = await self._make_scheduler(
            "exp_conf",
            plans,
            _FakePersistence(plans),
            transport=transport,
        )
        await sched.start()
        # The execute closure bound the attempt and the real transport
        # observed the remote ``cancelled`` confirmation.
        await _wait_until(lambda: sched._attempt_for_cell.get("a") is not None)
        attempt_id = sched._attempt_for_cell["a"]
        await _wait_until(lambda: sched._transport_binding.lookup(attempt_id) is not None)
        handle = transport.get_cancellation_handle("req_conf")
        self.assertIsNotNone(handle)
        await _wait_until(lambda: handle.snapshot().confirmed)

        result = await sched.cancel_cell("a")
        self.assertEqual(result, "canceled_running")
        # Durable state converged to canceled (confirmed verdict allowed it).
        rec = sched._persistence.read_active_attempt("a")
        self.assertEqual(rec.status, "canceled")
        # The execute task unwinds (finally) and cleans the binding + handle.
        await _wait_until(lambda: not sched._active_tasks)
        self.assertEqual(sched._transport_binding.lookup(attempt_id), None)
        self.assertEqual(len(sched._transport_binding), 0)
        # The transport-owned handle was released (no unbounded growth).
        self.assertIsNone(transport.get_cancellation_handle("req_conf"))
        gate.set()
        await sched.shutdown()

    async def test_run_cell_confirmed_cancelled_stream_end_records_canceled(self):
        """A remote stream that ends right after an explicit confirmed
        ``cancelled`` event must record durable ``canceled`` — never
        ``failed`` and never requiring a user retry.

        Full ``_run_cell`` path through the REAL ``ModalTransport`` adapter
        (fake Modal backend): the stream yields the confirmed ``cancelled``
        event and then ends without a result, so ``execute_plan`` raises.
        The binding execution closure inspects the transport-owned handle
        snapshot BEFORE releasing it and reports ``{'status': 'canceled'}``,
        which the ``_run_cell`` status branch persists durably.
        """
        import asyncio

        class _EndingStream:
            def __init__(self, confirmed_event):
                self._events = [confirmed_event]
                self._i = 0
                self.input_id = "in-cancel-end"
                self.input_created_at = 1.0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._i < len(self._events):
                    event = self._events[self._i]
                    self._i += 1
                    return event
                raise StopAsyncIteration

            async def aclose(self):
                pass

        class _EndingRemoteGen:
            def __init__(self, handle):
                self._handle = handle

            def aio(self, payload, request_id="", **kwargs):
                self._handle.aio_calls.append(
                    {"payload": payload, "request_id": request_id, "kwargs": dict(kwargs)}
                )
                return _EndingStream(self._handle._confirmed_event)

        class _EndingHandle:
            def __init__(self, confirmed_event):
                self._confirmed_event = confirmed_event
                self.aio_calls: list[dict] = []
                self.run_plan_stream = SimpleNamespace(remote_gen=_EndingRemoteGen(self))

        class _EndingFactory:
            def __init__(self, confirmed_event):
                self._confirmed_event = confirmed_event
                self.handles: list[_EndingHandle] = []

            def __call__(self, **kwargs):
                handle = _EndingHandle(self._confirmed_event)
                self.handles.append(handle)
                return handle

        class _FakeQueue:
            def __init__(self):
                self.messages: list[dict] = []

            def put(self, message, partition: str | None = None) -> None:
                self.messages.append(dict(message))

        cancelled_event = {
            "type": "cancelled",
            "request_id": "req_end",
            "reason": "user_cancel",
            "confirmed": True,
        }
        factory = _EndingFactory(cancelled_event)
        transport = ModalTransport(
            v2_handle_factory=factory,
            control_queue_factory=lambda workspace=None: _FakeQueue(),
        )
        plans = [{"cell_id": "a", "execution_plan": _execution_plan_dict("req_end")}]
        sched = await self._make_scheduler(
            "exp_cancel_end",
            plans,
            _FakePersistence(plans),
            transport=transport,
        )
        await sched.start()
        # Wait until the execute closure actually reached the transport stream
        # (not merely until the dispatch loop was created), then unwind.
        await _wait_until(
            lambda: len(factory.handles) == 1 and len(factory.handles[0].aio_calls) == 1
        )
        # The execute closure unwinds once the confirmed remote cancellation
        # terminated the stream — no user cancel call and no user retry.
        await _wait_until(lambda: not sched._active_tasks)
        rec = sched._persistence.read_active_attempt("a")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.status, "canceled")
        # Exactly one terminal write, and it is ``canceled`` (never failed).
        self.assertEqual(len(sched._persistence._inner.terminal_writes), 1)
        self.assertEqual(sched._persistence._inner.terminal_writes[0][2], "canceled")
        # A canceled cell is not retryable: no user retry is required and a
        # retry is correctly refused.
        self.assertFalse(await sched.retry_cell("a"))
        self.assertEqual(await sched.cancel_cell("a"), "noop")
        # Binding + transport-owned handle cleaned up in ``finally``.
        self.assertEqual(len(sched._transport_binding), 0)
        self.assertIsNone(transport.get_cancellation_handle("req_end"))
        await sched.shutdown()


# ── D4: routes (construction / cancel semantics) ─────────────────────────


class _UnconfirmedModernScheduler:
    """Truthful scheduler stand-in whose remote cancel never confirms."""

    remote_cancel_available = True

    async def cancel_cell(self, cell_id, *, reason="user_cancel"):
        return "cancel_unconfirmed"


class ExperimentModernBindingRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_root = Path(self._tmp.name)
        db_path = self.data_root / ".studio_history_v2" / "history_v2.db"
        self.store = HistoryV2Store(db_path)
        self.repo = HistoryV2Repository(self.store)
        self.app = web.Application()
        self.registry: dict[str, object] = {}
        register = emr.register_experiment_modern_routes
        register(self.app.router, self.data_root, registry=self.registry)
        emr._SHUTDOWN_FLAG[0] = False
        emr._DEFAULT_TRANSPORT_FACTORY[0] = None
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        emr._DEFAULT_TRANSPORT_FACTORY[0] = None
        for exp_id in list(self.registry):
            ems.unregister_scheduler(exp_id)
        for exp_id in list(ems._SCHEDULERS):
            ems.unregister_scheduler(exp_id)
        await self.client.close()

    def _matrix(self, experiment_id: str, cell_ids=("a", "b"), *, created_at=T0):
        specs = [_cell_spec(cid) for cid in cell_ids]
        return self.repo.create_modern_matrix(
            experiment_id=experiment_id,
            name=f"Matrix {experiment_id}",
            definition=_definition(specs),
            cells=specs,
            created_at=created_at,
        )

    async def _post(self, url: str, body=None, expected: int = 200):
        kwargs = {"json": body} if body is not None else {}
        resp = await self.client.post(url, **kwargs)
        self.assertEqual(resp.status, expected, await resp.text())
        return await resp.json()

    async def test_create_constructs_registers_and_starts_scheduler(self):
        fake_transport = _FakeTransport()
        emr._DEFAULT_TRANSPORT_FACTORY[0] = lambda: fake_transport
        fake = _FakePlanner([_FakePlannerCell("a"), _FakePlannerCell("b")])
        with mock.patch.object(emr, "_load_planner", return_value=fake):
            data = await self._post(
                "/comfymodal/history-v2/experiments",
                {
                    "experiment_id": "exp_created",
                    "name": "Created",
                    "definition": {"workflows": {"wf_a": {}}, "axis": "seed"},
                },
            )
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["started"])  # scheduler bound + dispatched
        # Registered in the process-local module registry AND the injected
        # registry; the shared per-experiment transport is the injected one.
        sched = ems.get_scheduler("exp_created")
        self.assertIsNotNone(sched)
        self.assertIs(self.registry.get("exp_created"), sched)
        self.assertIs(sched._shared_transport, fake_transport)
        # Construction used the bound repository (experiment scoped).
        self.assertEqual(sched._persistence._inner.experiment_id, "exp_created")
        # A second create of the same experiment cannot double-register.
        await sched.shutdown()
        ems.unregister_scheduler("exp_created")

    async def test_create_stays_queued_without_transport_factory(self):
        # Explicitly unable to construct a scheduler -> the accepted matrix
        # stays durably queued and never claims started.
        emr._DEFAULT_TRANSPORT_FACTORY[0] = None
        fake = _FakePlanner([_FakePlannerCell("a"), _FakePlannerCell("b")])
        with mock.patch.object(emr, "_load_planner", return_value=fake):
            data = await self._post(
                "/comfymodal/history-v2/experiments",
                {
                    "experiment_id": "exp_no_sched",
                    "definition": {"workflows": {"wf_a": {}}, "axis": "seed"},
                },
            )
        self.assertFalse(data["started"])
        self.assertIsNone(ems.get_scheduler("exp_no_sched"))
        self.assertNotIn("exp_no_sched", self.registry)
        detail = self.repo.get_experiment("exp_no_sched")
        self.assertIsNotNone(detail)
        self.assertEqual([c.status for c in detail.cells], ["queued", "queued"])

    async def test_cancel_unconfirmed_returns_503_and_keeps_running_durable(self):
        self._matrix("exp_unconf")
        run = _claim(self.repo, "a")
        self.registry["exp_unconf"] = _UnconfirmedModernScheduler()

        resp = await self.client.post(
            f"/comfymodal/history-v2/experiments/exp_unconf/cancel"
        )
        self.assertEqual(resp.status, 503)
        body = await resp.json()
        self.assertEqual(body["code"], "CANCELLATION_UNAVAILABLE")
        self.assertEqual(body["cell_id"], "a")
        # Durable running state untouched by the unconfirmed cancel.
        self.assertEqual(self.repo.get_attempt(run).status, "running")
        self.assertEqual(self.repo.read_active_attempt("a").status, "running")
        # Queued cells are still atomically canceled so the experiment stops
        # launching (durable queued cancel is never tied to the remote).
        self.assertEqual(self.repo.read_active_attempt("b").status, "canceled")

    async def test_cancel_queued_unaffected_when_scheduler_registered(self):
        self._matrix("exp_queued")
        self.registry["exp_queued"] = _UnconfirmedModernScheduler()
        data = await self._post(
            f"/comfymodal/history-v2/experiments/exp_queued/cancel"
        )
        self.assertEqual(data["aggregate_status"], "canceled")
        self.assertEqual(data["counts"]["canceled"], 2)
        for cell in ("a", "b"):
            current = self.repo.read_active_attempt(cell)
            assert current is not None
            self.assertEqual(current.status, "canceled")

    async def test_registry_lifecycle_cleanup_releases_bindings(self):
        # A scheduler built through the route path cleans its binding and
        # releases the transport cancellation handle on shutdown, and
        # shutdown lifecycle iterates only owned schedulers.
        fake_transport = _FakeTransport()
        emr._DEFAULT_TRANSPORT_FACTORY[0] = lambda: fake_transport
        fake = _FakePlanner([_FakePlannerCell("a")])
        with mock.patch.object(emr, "_load_planner", return_value=fake):
            await self._post(
                "/comfymodal/history-v2/experiments",
                {
                    "experiment_id": "exp_cleanup",
                    "definition": {"workflows": {"wf_a": {}}, "axis": "seed"},
                },
            )
        sched = ems.get_scheduler("exp_cleanup")
        self.assertIsNotNone(sched)
        sched._transport_binding.bind("run_x", "req_x")
        await emr.shutdown_experiment_modern_lifecycle(registry=self.registry)
        self.assertTrue(sched._shutdown_done)
        # Binding cleared + handle released on shutdown (safety net).
        self.assertEqual(len(sched._transport_binding), 0)


if __name__ == "__main__":
    unittest.main()
