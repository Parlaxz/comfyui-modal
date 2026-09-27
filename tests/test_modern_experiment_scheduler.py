"""Deterministic tests for ``experiment_modern_scheduler`` (Phase D, lane L2).

Uses fake in-memory persistence / executor / remote-canceller only.  Never
touches real Modal or generation.  The module under test imports only the
standard library, so this suite can be run standalone.
"""
import asyncio
import importlib.util
import itertools
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "experiment_modern_scheduler.py"

# The scheduler under test is loaded under a unique test-only module name so
# collection NEVER clobbers ``sys.modules['experiment_modern_scheduler']``.
# In a combined run (routes/binding tests alongside this suite) every importer
# keeps resolving the live scheduler module and its process-local registry;
# this suite's sandbox copy carries its own registry instead of splitting the
# shared one.
TEST_MODULE_NAME = "_modern_experiment_scheduler_sandbox"


def load_module():
    spec = importlib.util.spec_from_file_location(TEST_MODULE_NAME, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[TEST_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


MOD = load_module()
MOD_SOURCE = MODULE_PATH.read_text(encoding="utf-8")


def plan(cell_id, **kw):
    base = {
        "cell_id": cell_id,
        "workflow_id": "wf_a",
        "workflow_version_id": "v_frozen",
        "preset_id": "p_frozen",
        "workflow_hash": "wh_" + cell_id,
        "seed": 1,
    }
    base.update(kw)
    return base


def plans_for(ids):
    return [plan(cid) for cid in ids]


class FakePersistence:
    """In-memory stand-in for History V2.

    Mirrors the frozen semantic operations and the durable rules the real
    History enforces: append-only attempts, one active attempt per cell,
    atomic queued->running claims, first-terminal-wins, and attempt-identity
    guarding for terminal writes.
    """

    def __init__(self, cell_plans, seed=None):
        self.cells = {}
        self._counter = itertools.count(1)
        for cell_plan in cell_plans:
            cell_id = cell_plan["cell_id"]
            self.cells[cell_id] = {"plan": cell_plan, "attempts": []}
        seeded = set(seed or {})
        if seed:
            for cell_id, attempts in seed.items():
                if cell_id not in self.cells:
                    continue
                self.cells[cell_id]["attempts"] = [dict(a) for a in attempts]
        for cell_id in self.cells:
            if cell_id not in seeded and not self.cells[cell_id]["attempts"]:
                self._new_attempt(cell_id, "queued")
        self.terminal_writes = []

    def _new_attempt(self, cell_id, status):
        attempt = {
            "attempt_id": f"run_{next(self._counter)}",
            "cell_id": cell_id,
            "status": status,
            "error": None,
        }
        self.cells[cell_id]["attempts"].append(attempt)
        return attempt

    def _active(self, cell_id):
        cell = self.cells.get(cell_id)
        if cell is None:
            return None
        attempts = cell["attempts"]
        return attempts[-1] if attempts else None

    def active(self, cell_id):
        attempt = self._active(cell_id)
        if attempt is None:
            raise AssertionError(f"cell {cell_id} has no active attempt")
        return attempt

    def attempt_history(self, cell_id):
        return [dict(a) for a in self.cells[cell_id]["attempts"]]

    # -- frozen semantic operations ----------------------------------------

    def load_queued_cells(self):
        records = []
        for cell_id in self.cells:
            active = self._active(cell_id)
            if active is None or active["status"] in ("queued", "pending"):
                records.append(MOD.CellRecord(
                    cell_id=cell_id,
                    attempt_id=active["attempt_id"] if active else None,
                    status=active["status"] if active else None,
                ))
        return records

    def atomically_claim_queued_attempt(self, cell_id):
        if cell_id not in self.cells:
            return None
        active = self._active(cell_id)
        if active is None:
            created = self._new_attempt(cell_id, "running")
            return MOD.AttemptClaim(attempt_id=created["attempt_id"], cell_id=cell_id, is_new=True)
        if active["status"] in ("queued", "pending"):
            active["status"] = "running"
            return MOD.AttemptClaim(attempt_id=active["attempt_id"], cell_id=cell_id, is_new=False)
        return None

    def read_active_attempt(self, cell_id):
        active = self._active(cell_id)
        if active is None:
            return None
        return MOD.AttemptRecord(attempt_id=active["attempt_id"], cell_id=cell_id, status=active["status"])

    def record_running(self, attempt_id, cell_id):
        active = self._active(cell_id)
        if active and active["attempt_id"] == attempt_id and active["status"] not in MOD.TERMINAL_STATUSES:
            active["status"] = "running"

    def record_terminal(self, attempt_id, cell_id, status, error=None):
        active = self._active(cell_id)
        if active is None or active["attempt_id"] != attempt_id:
            return False
        if active["status"] in MOD.TERMINAL_STATUSES:
            return False
        active["status"] = status
        active["error"] = error
        self.terminal_writes.append((attempt_id, cell_id, status, error, True))
        return True

    def create_resume_attempt(self, cell_id):
        active = self._active(cell_id)
        if active is None or active["status"] != "interrupted":
            return None
        created = self._new_attempt(cell_id, "running")
        return MOD.AttemptClaim(attempt_id=created["attempt_id"], cell_id=cell_id, is_new=True)

    def create_retry_attempt(self, cell_id):
        active = self._active(cell_id)
        if active is None or active["status"] != "failed":
            return None
        created = self._new_attempt(cell_id, "running")
        return MOD.AttemptClaim(attempt_id=created["attempt_id"], cell_id=cell_id, is_new=True)

    def list_recoverable_cells(self):
        records = []
        for cell_id in self.cells:
            active = self._active(cell_id)
            if active is None:
                records.append(MOD.CellRecord(cell_id=cell_id, attempt_id=None, status=None))
            elif active["status"] in ("running", "interrupted", "queued", "pending"):
                records.append(MOD.CellRecord(
                    cell_id=cell_id, attempt_id=active["attempt_id"], status=active["status"],
                ))
        return records

    def aggregate_status(self):
        statuses = []
        for cell_id in self.cells:
            active = self._active(cell_id)
            statuses.append(active["status"] if active else None)
        if any(s in ("running", "queued", "pending") or s is None for s in statuses):
            return "running"
        if any(s == "interrupted" for s in statuses):
            return "interrupted"
        if any(s == "failed" for s in statuses):
            return "completed_with_failures"
        if any(s == "canceled" for s in statuses):
            return "canceled"
        return "completed"


class FakeExecutor:
    def __init__(self, delay=0.0):
        self.delay = delay
        self.running = 0
        self.peak = 0
        self.started = []
        self.received = {}
        self.events = []
        self.fail_cells = {}
        self.gates = {}
        self.sync = None

    async def __call__(self, cell_plan, *, attempt_id, cell_id):
        self.running += 1
        self.peak = max(self.peak, self.running)
        self.started.append((cell_id, attempt_id))
        self.received[cell_id] = cell_plan
        self.events.append(("started", cell_id, attempt_id))
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            gate = self.gates.get(cell_id)
            if gate is not None:
                await gate.wait()
            if cell_id in self.fail_cells:
                raise RuntimeError(self.fail_cells[cell_id])
        finally:
            self.running -= 1
            self.events.append(("finished", cell_id, attempt_id))


class FakeCanceller:
    def __init__(self):
        self.calls = []

    async def __call__(self, attempt_id, cell_id, *, intent, reason):
        self.calls.append((attempt_id, cell_id, intent, reason))


class ConfirmingCanceller:
    """Async remote canceller returning a fixed (or computed) result per call.

    ``result`` may be a value (``CancelResult`` / dict / bool) or a callable
    ``(attempt_id, cell_id, *, intent, reason) -> result`` evaluated per call.
    """

    def __init__(self, result):
        self.calls = []
        self.result = result

    async def __call__(self, attempt_id, cell_id, *, intent, reason):
        self.calls.append((attempt_id, cell_id, intent, reason))
        if callable(self.result):
            return self.result(attempt_id, cell_id, intent=intent, reason=reason)
        return self.result


class SyncConfirmingCanceller:
    """Synchronous remote canceller returning a fixed result per call."""

    def __init__(self, result):
        self.calls = []
        self.result = result

    def __call__(self, attempt_id, cell_id, *, intent, reason):
        self.calls.append((attempt_id, cell_id, intent, reason))
        if callable(self.result):
            return self.result(attempt_id, cell_id, intent=intent, reason=reason)
        return self.result


class RaisingCanceller:
    """Async remote canceller that always raises (channel failure)."""

    def __init__(self, exc=None):
        self.calls = []
        self.exc = exc if exc is not None else RuntimeError("channel down")

    async def __call__(self, attempt_id, cell_id, *, intent, reason):
        self.calls.append((attempt_id, cell_id, intent, reason))
        raise self.exc


def make_scheduler(plans, persistence=None, executor=None, canceller=None, concurrency=None):
    if persistence is None:
        persistence = FakePersistence(plans)
    if executor is None:
        executor = FakeExecutor()
    if canceller is None:
        canceller = FakeCanceller()
    kwargs = {}
    if concurrency is not None:
        kwargs["concurrency"] = concurrency
    return MOD.ExperimentModernScheduler(
        experiment_id="exp_test",
        cell_plans=plans,
        persistence=persistence,
        execute=executor,
        remote_cancel=canceller,
        **kwargs,
    ), persistence, executor, canceller


async def wait_until(cond, timeout=5.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not cond():
        if loop.time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.005)


async def await_drain(sched, timeout=10.0):
    async def drained():
        while True:
            if (sched._dispatch_task is None or sched._dispatch_task.done()) and not sched._active_tasks:
                return
            await asyncio.sleep(0.005)
    await asyncio.wait_for(drained(), timeout)


def active_status(persistence, cell_id):
    active = persistence._active(cell_id)
    return active["status"] if active else None


def claim_attempt(persistence, cell_id):
    claim = persistence.atomically_claim_queued_attempt(cell_id)
    if claim is None:
        raise AssertionError(f"expected a claim for cell {cell_id}")
    return claim


class ModernSchedulerTests(unittest.IsolatedAsyncioTestCase):

    async def test_single_cell_completes(self):
        plans = plans_for(["a"])
        sched, persistence, executor, _ = make_scheduler(plans)
        await sched.start()
        await await_drain(sched)
        self.assertEqual(active_status(persistence, "a"), "completed")
        self.assertEqual(await sched.status(), "completed")
        self.assertEqual(len(persistence.attempt_history("a")), 1)
        self.assertEqual(executor.peak, 1)

    async def test_success_result_is_finalized_before_completed_terminal(self):
        class ResultPersistence(FakePersistence):
            def __init__(self, cell_plans):
                super().__init__(cell_plans)
                self.results = []

            def record_result(self, attempt_id, cell_id, result):
                self.results.append((attempt_id, cell_id, result))
                return True

        result_store = ResultPersistence(plans_for(["a"]))

        async def execute(cell_plan, *, attempt_id, cell_id):
            return {"status": "ok", "output_paths": ["result.png"]}

        sched, persistence, _, _ = make_scheduler(
            plans_for(["a"]), persistence=result_store, executor=execute,
        )
        await sched.start()
        await await_drain(sched)

        self.assertEqual(len(result_store.results), 1)
        self.assertEqual(result_store.results[0][1], "a")
        self.assertEqual(active_status(persistence, "a"), "completed")
        self.assertEqual(persistence.terminal_writes[-1][2], "completed")

    async def test_two_cells_both_complete(self):
        plans = plans_for(["a", "b"])
        sched, persistence, executor, _ = make_scheduler(plans)
        await sched.start()
        await await_drain(sched)
        for cid in ("a", "b"):
            self.assertEqual(active_status(persistence, cid), "completed")
        self.assertEqual(await sched.status(), "completed")
        self.assertEqual(len(executor.started), 2)

    async def test_forty_cells_peak_concurrency_leq_6(self):
        plans = plans_for([f"c{i:02d}" for i in range(40)])
        sched, persistence, executor, _ = make_scheduler(plans, executor=FakeExecutor(delay=0.005))
        await sched.start()
        await await_drain(sched, timeout=20.0)
        self.assertLessEqual(executor.peak, 6)
        self.assertEqual(len(executor.started), 40)
        for cid in persistence.cells:
            self.assertEqual(active_status(persistence, cid), "completed")

    async def test_continuous_refill_bounded_launch(self):
        plans = plans_for([f"c{i:02d}" for i in range(40)])
        sched, persistence, executor, _ = make_scheduler(plans, executor=FakeExecutor(delay=0.005))
        await sched.start()
        await await_drain(sched, timeout=20.0)
        self.assertLessEqual(executor.peak, 6)
        launched_before_first_finish = 0
        for event in executor.events:
            if event[0] == "started":
                launched_before_first_finish += 1
            elif event[0] == "finished":
                break
        self.assertEqual(launched_before_first_finish, 6)
        self.assertEqual(len(executor.started), 40)
        self.assertEqual(executor.running, 0)

    async def test_mixed_workflow_axis_plan_used_verbatim(self):
        p_a = plan("a", workflow_id="wf_x", workflow_version_id="v_x2", preset_id="p_x")
        p_b = plan("b", workflow_id="wf_y", workflow_version_id="v_y1", preset_id="p_y")
        sched, persistence, executor, _ = make_scheduler([p_a, p_b])
        await sched.start()
        await await_drain(sched)
        self.assertIs(executor.received["a"], p_a)
        self.assertIs(executor.received["b"], p_b)
        self.assertEqual(executor.received["a"]["workflow_version_id"], "v_x2")
        self.assertEqual(executor.received["b"]["preset_id"], "p_y")

    async def test_no_silent_version_substitution(self):
        frozen = plan("a", workflow_version_id="v_old")
        sched, persistence, executor, _ = make_scheduler([frozen])
        latest_now = "v_new"
        self.assertNotEqual(frozen["workflow_version_id"], latest_now)
        await sched.start()
        await await_drain(sched)
        self.assertIs(executor.received["a"], frozen)
        self.assertEqual(executor.received["a"]["workflow_version_id"], "v_old")

    async def test_one_failed_sibling_isolation_no_auto_retry(self):
        plans = plans_for(["a", "b", "c"])
        executor = FakeExecutor()
        executor.fail_cells = {"b": "boom"}
        sched, persistence, executor, _ = make_scheduler(plans, executor=executor)
        await sched.start()
        await await_drain(sched)
        self.assertEqual(active_status(persistence, "a"), "completed")
        self.assertEqual(active_status(persistence, "b"), "failed")
        self.assertEqual(active_status(persistence, "c"), "completed")
        self.assertEqual(len(persistence.attempt_history("b")), 1)
        self.assertEqual(persistence.active("b")["error"], "RuntimeError('boom')")
        self.assertEqual(await sched.status(), "completed_with_failures")

    async def test_multiple_failed_siblings_isolated(self):
        plans = plans_for(["a", "b", "c", "d"])
        executor = FakeExecutor()
        executor.fail_cells = {"b": "err_b", "d": "err_d"}
        sched, persistence, executor, _ = make_scheduler(plans, executor=executor)
        await sched.start()
        await await_drain(sched)
        self.assertEqual(persistence.active("b")["error"], "RuntimeError('err_b')")
        self.assertEqual(persistence.active("d")["error"], "RuntimeError('err_d')")
        self.assertEqual(active_status(persistence, "a"), "completed")
        self.assertEqual(active_status(persistence, "c"), "completed")

    async def test_cancel_queued_cells_zero_execute_calls(self):
        plans = plans_for([f"c{i:02d}" for i in range(20)])
        executor = FakeExecutor()
        for cell_plan in plans:
            executor.gates[cell_plan["cell_id"]] = asyncio.Event()
        sched, persistence, executor, canceller = make_scheduler(plans, executor=executor)
        await sched.start()
        await wait_until(lambda: len(executor.started) >= 6)
        counts = await sched.cancel_experiment()
        self.assertEqual(counts["canceled_running"], 6)
        self.assertEqual(counts["canceled_queued"], 14)
        self.assertEqual(len(executor.started), 6)
        for cid in persistence.cells:
            self.assertEqual(active_status(persistence, cid), "canceled")
        self.assertEqual(len(canceller.calls), 6)
        self.assertEqual(await sched.status(), "canceled")

    async def test_cancel_running_remote_primitive_exactly_once(self):
        plans = plans_for(["a"])
        executor = FakeExecutor(delay=0.5)
        sched, persistence, executor, canceller = make_scheduler(plans, executor=executor)
        await sched.start()
        await wait_until(lambda: len(executor.started) == 1)
        result = await sched.cancel_cell("a")
        self.assertEqual(result, "canceled_running")
        self.assertEqual(len(canceller.calls), 1)
        attempt_id, cell_id, intent, reason = canceller.calls[0]
        self.assertEqual(cell_id, "a")
        self.assertEqual(intent, "cancel")
        self.assertEqual(reason, "user_cancel")
        self.assertEqual(active_status(persistence, "a"), "canceled")
        self.assertEqual(await sched.status(), "canceled")
        second = await sched.cancel_cell("a")
        self.assertEqual(second, "noop")
        self.assertEqual(len(canceller.calls), 1)

    async def test_cancel_after_terminal_wins_is_noop(self):
        plans = plans_for(["a"])
        sched, persistence, executor, canceller = make_scheduler(plans)
        await sched.start()
        await await_drain(sched)
        result = await sched.cancel_cell("a")
        self.assertEqual(result, "noop")
        self.assertEqual(len(canceller.calls), 0)
        self.assertEqual(active_status(persistence, "a"), "completed")
        self.assertEqual(await sched.status(), "completed")

    async def test_cancel_in_flight_never_records_failed(self):
        plans = plans_for(["a"])
        executor = FakeExecutor()
        executor.gates["a"] = asyncio.Event()
        sched, persistence, executor, _ = make_scheduler(plans, executor=executor)
        await sched.start()
        await wait_until(lambda: len(executor.started) == 1)
        result = await sched.cancel_cell("a")
        self.assertEqual(result, "canceled_running")
        self.assertEqual(active_status(persistence, "a"), "canceled")
        await wait_until(lambda: not sched._active_tasks)
        self.assertEqual(active_status(persistence, "a"), "canceled")

    async def test_shutdown_marks_running_interrupted_queued_remain_queued(self):
        plans = plans_for([f"c{i:02d}" for i in range(20)])
        executor = FakeExecutor()
        for cid in [p["cell_id"] for p in plans]:
            executor.gates[cid] = asyncio.Event()
        sched, persistence, executor, canceller = make_scheduler(plans, executor=executor)
        await sched.start()
        await wait_until(lambda: len(executor.started) >= 6)
        await sched.shutdown()
        running_cells = [cid for cid, _ in executor.started]
        self.assertEqual(len(running_cells), 6)
        for cid in running_cells:
            self.assertEqual(active_status(persistence, cid), "interrupted")
        for cid in persistence.cells:
            if cid not in running_cells:
                self.assertEqual(active_status(persistence, cid), "queued")
        self.assertEqual(len(canceller.calls), 6)
        for _, _, intent, reason in canceller.calls:
            self.assertEqual(intent, "shutdown")
            self.assertEqual(reason, "shutdown")
        self.assertEqual(len(executor.started), 6)
        self.assertIsNone(sched._dispatch_task)
        await sched.shutdown()

    async def test_startup_recovery_only_stuck_running_marked_interrupted(self):
        seed = {
            "a": [{"attempt_id": "run_a1", "cell_id": "a", "status": "running", "error": None}],
            "b": [{"attempt_id": "run_b1", "cell_id": "b", "status": "completed", "error": None}],
            "c": [{"attempt_id": "run_c1", "cell_id": "c", "status": "failed", "error": "x"}],
            "d": [{"attempt_id": "run_d1", "cell_id": "d", "status": "canceled", "error": None}],
            "e": [{"attempt_id": "run_e1", "cell_id": "e", "status": "queued", "error": None}],
            "f": [],
        }
        plans = plans_for(["a", "b", "c", "d", "e", "f"])
        persistence = FakePersistence(plans, seed=seed)
        sched, persistence, _, _ = make_scheduler(plans, persistence=persistence)
        swept = await sched._startup_recovery()
        self.assertEqual(swept, 1)
        self.assertEqual(active_status(persistence, "a"), "interrupted")
        self.assertEqual(active_status(persistence, "b"), "completed")
        self.assertEqual(active_status(persistence, "c"), "failed")
        self.assertEqual(active_status(persistence, "d"), "canceled")
        self.assertEqual(active_status(persistence, "e"), "queued")
        self.assertIsNone(persistence._active("f"))
        again = await sched._startup_recovery()
        self.assertEqual(again, 0)

    async def test_resume_submits_only_interrupted_and_never_started(self):
        seed = {
            "a": [{"attempt_id": "run_a_old", "cell_id": "a", "status": "interrupted", "error": None}],
            "b": [{"attempt_id": "run_b1", "cell_id": "b", "status": "completed", "error": None}],
            "c": [{"attempt_id": "run_c1", "cell_id": "c", "status": "failed", "error": "x"}],
            "d": [{"attempt_id": "run_d1", "cell_id": "d", "status": "canceled", "error": None}],
            "e": [{"attempt_id": "run_e_queued", "cell_id": "e", "status": "queued", "error": None}],
            "f": [],
        }
        plans = plans_for(["a", "b", "c", "d", "e", "f"])
        persistence = FakePersistence(plans, seed=seed)
        sched, persistence, executor, _ = make_scheduler(plans, persistence=persistence)
        counts = await sched.resume()
        self.assertEqual(counts["resumed"], 3)
        self.assertEqual(counts["skipped"], 3)
        await await_drain(sched)
        started = {(cid, aid) for cid, aid in executor.started}
        self.assertNotIn(("a", "run_a_old"), started)
        self.assertIn(("e", "run_e_queued"), started)
        self.assertEqual(len(started), 3)
        for cid in ("a", "e", "f"):
            self.assertEqual(active_status(persistence, cid), "completed")
        self.assertEqual(len(persistence.attempt_history("a")), 2)
        self.assertEqual(persistence.attempt_history("a")[0]["attempt_id"], "run_a_old")

    async def test_resume_double_call_no_duplicate_execution(self):
        seed = {
            "a": [{"attempt_id": "run_a_old", "cell_id": "a", "status": "interrupted", "error": None}],
        }
        persistence = FakePersistence(plans_for(["a"]), seed=seed)
        executor = FakeExecutor(delay=0.2)
        sched, persistence, executor, _ = make_scheduler(plans_for(["a"]), persistence=persistence, executor=executor)
        first = await sched.resume()
        self.assertEqual(first["resumed"], 1)
        await wait_until(lambda: len(executor.started) == 1)
        second = await sched.resume()
        self.assertEqual(second["resumed"], 0)
        self.assertEqual(len(executor.started), 1)
        await sched.shutdown()

    async def test_resume_forty_interrupted_cells_stays_bounded(self):
        cell_plans = plans_for([f"c{i:02d}" for i in range(40)])
        seed = {
            plan_item["cell_id"]: [{
                "attempt_id": f"old_{plan_item['cell_id']}",
                "cell_id": plan_item["cell_id"],
                "status": "interrupted",
                "error": "shutdown",
            }]
            for plan_item in cell_plans
        }
        persistence = FakePersistence(cell_plans, seed=seed)
        executor = FakeExecutor(delay=0.003)
        sched, persistence, executor, _ = make_scheduler(
            cell_plans, persistence=persistence, executor=executor
        )
        counts = await sched.resume()
        self.assertEqual(counts, {"resumed": 40, "skipped": 0})
        await await_drain(sched, timeout=20.0)
        self.assertEqual(len(executor.started), 40)
        self.assertLessEqual(executor.peak, 6)
        for plan_item in cell_plans:
            history = persistence.attempt_history(plan_item["cell_id"])
            self.assertEqual(len(history), 2)
            self.assertNotEqual(history[0]["attempt_id"], history[1]["attempt_id"])

    async def test_claim_cancel_race_does_not_execute_canceled_cell(self):
        class SlowClaimPersistence(FakePersistence):
            def __init__(self, cell_plans):
                super().__init__(cell_plans)
                self.claim_started = asyncio.Event()
                self.release_claim = asyncio.Event()

            async def atomically_claim_queued_attempt(self, cell_id):
                self.claim_started.set()
                await self.release_claim.wait()
                return super().atomically_claim_queued_attempt(cell_id)

        cell_plans = plans_for(["a"])
        race_persistence = SlowClaimPersistence(cell_plans)
        executor = FakeExecutor()
        sched, _, executor, _ = make_scheduler(
            cell_plans, persistence=race_persistence, executor=executor
        )
        await sched.start()
        await race_persistence.claim_started.wait()
        self.assertEqual(await sched.cancel_cell("a"), "canceled_queued")
        race_persistence.release_claim.set()
        await await_drain(sched)
        self.assertEqual(executor.started, [])
        self.assertEqual(active_status(race_persistence, "a"), "canceled")

    async def test_start_does_not_perform_startup_recovery(self):
        cell_plans = plans_for(["a"])
        persistence = FakePersistence(cell_plans, seed={
            "a": [{
                "attempt_id": "run_old",
                "cell_id": "a",
                "status": "running",
                "error": None,
            }],
        })
        sched, persistence, executor, _ = make_scheduler(
            cell_plans, persistence=persistence
        )
        await sched.start()
        await await_drain(sched)
        self.assertEqual(active_status(persistence, "a"), "running")
        self.assertEqual(executor.started, [])
        self.assertEqual(await sched._startup_recovery(), 1)
        self.assertEqual(active_status(persistence, "a"), "interrupted")
        await sched.shutdown()

    async def test_stale_terminal_and_progress_events_are_rejected(self):
        cell_plans = plans_for(["a"])
        persistence = FakePersistence(cell_plans, seed={
            "a": [{
                "attempt_id": "run_old",
                "cell_id": "a",
                "status": "running",
                "error": None,
            }],
        })
        sched, persistence, _, _ = make_scheduler(
            cell_plans, persistence=persistence
        )
        self.assertTrue(await sched.handle_progress("a", "run_old"))
        self.assertTrue(await sched.handle_terminal("a", "run_old", "failed"))
        self.assertFalse(await sched.handle_terminal("a", "run_old", "completed"))
        new_attempt = persistence.create_retry_attempt("a")
        self.assertIsNotNone(new_attempt)
        assert new_attempt is not None
        self.assertFalse(await sched.handle_progress("a", "run_old"))
        self.assertFalse(await sched.handle_terminal("a", "run_old", "completed"))
        self.assertTrue(await sched.handle_progress("a", new_attempt.attempt_id))
        self.assertTrue(await sched.handle_terminal("a", new_attempt.attempt_id, "completed"))

    async def test_retry_failed_new_attempt_same_cell(self):
        plans = plans_for(["a"])
        executor = FakeExecutor()
        executor.fail_cells = {"a": "boom"}
        sched, persistence, executor, _ = make_scheduler(plans, executor=executor)
        await sched.start()
        await await_drain(sched)
        first_attempt = persistence.active("a")["attempt_id"]
        executor.fail_cells.pop("a")
        retried = await sched.retry_cell("a")
        self.assertTrue(retried)
        await await_drain(sched)
        history = persistence.attempt_history("a")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1]["attempt_id"], persistence.active("a")["attempt_id"])
        self.assertNotEqual(history[1]["attempt_id"], first_attempt)
        self.assertEqual(active_status(persistence, "a"), "completed")
        self.assertEqual(await sched.status(), "completed")

    async def test_retry_failed_twice_accumulates_attempts(self):
        plans = plans_for(["a"])
        executor = FakeExecutor()
        executor.fail_cells = {"a": "boom"}
        sched, persistence, executor, _ = make_scheduler(plans, executor=executor)
        await sched.start()
        await await_drain(sched)
        self.assertTrue(await sched.retry_cell("a"))
        await await_drain(sched)
        self.assertEqual(active_status(persistence, "a"), "failed")
        executor.fail_cells.pop("a")
        self.assertTrue(await sched.retry_cell("a"))
        await await_drain(sched)
        history = persistence.attempt_history("a")
        self.assertEqual(len(history), 3)
        self.assertEqual(active_status(persistence, "a"), "completed")

    async def test_retry_rejects_non_failed_cells(self):
        plans = plans_for(["a", "b"])
        sched, persistence, executor, _ = make_scheduler(plans)
        await sched.start()
        await await_drain(sched)
        self.assertFalse(await sched.retry_cell("a"))
        self.assertEqual(len(persistence.attempt_history("a")), 1)

    async def test_duplicate_terminal_writes_ignored(self):
        persistence = FakePersistence(plans_for(["a"]))
        claim = claim_attempt(persistence, "a")
        self.assertTrue(persistence.record_terminal(claim.attempt_id, "a", "completed"))
        self.assertFalse(persistence.record_terminal(claim.attempt_id, "a", "completed"))
        self.assertFalse(persistence.record_terminal(claim.attempt_id, "a", "failed"))
        self.assertEqual(active_status(persistence, "a"), "completed")

    async def test_stale_event_previous_attempt_rejected(self):
        persistence = FakePersistence(plans_for(["a"]))
        old = claim_attempt(persistence, "a")
        old_attempt = old.attempt_id
        self.assertTrue(persistence.record_terminal(old_attempt, "a", "failed", error="boom"))
        new = persistence.create_retry_attempt("a")
        self.assertIsNotNone(new)
        assert new is not None
        self.assertFalse(persistence.record_terminal(old_attempt, "a", "completed"))
        self.assertEqual(persistence.active("a")["status"], "running")
        self.assertTrue(persistence.record_terminal(new.attempt_id, "a", "completed"))
        self.assertEqual(active_status(persistence, "a"), "completed")

    async def test_out_of_order_terminal_first_wins(self):
        persistence = FakePersistence(plans_for(["a"]))
        claim = claim_attempt(persistence, "a")
        persistence.record_running(claim.attempt_id, "a")
        self.assertTrue(persistence.record_terminal(claim.attempt_id, "a", "completed"))
        self.assertFalse(persistence.record_terminal(claim.attempt_id, "a", "failed"))
        self.assertFalse(persistence.record_terminal(claim.attempt_id, "a", "canceled"))
        persistence.record_running(claim.attempt_id, "a")
        self.assertEqual(active_status(persistence, "a"), "completed")

    async def test_immutable_plan_identity_preserved(self):
        plans = plans_for(["a", "b", "c"])
        executor = FakeExecutor()
        executor.fail_cells = {"b": "boom"}
        sched, persistence, executor, _ = make_scheduler(plans, executor=executor)
        await sched.start()
        await await_drain(sched)
        executor.fail_cells.pop("b")
        self.assertTrue(await sched.retry_cell("b"))
        await await_drain(sched)
        original = {p["cell_id"]: p for p in plans}
        for cell_id, received in executor.received.items():
            self.assertIs(received, original[cell_id])
        self.assertEqual(list(persistence.cells.keys()), ["a", "b", "c"])

    async def test_no_taskgroup_in_module_source(self):
        self.assertNotIn("TaskGroup", MOD_SOURCE)
        self.assertNotIn("asyncio.gather(", MOD_SOURCE)

    async def test_collection_preserves_live_scheduler_module_registry(self):
        """The sandbox loader never shadows the live scheduler module.

        In a combined run (routes/binding tests collected alongside this
        suite) the real ``experiment_modern_scheduler`` module must remain
        the module every importer resolves, so the process-local scheduler
        registry is shared instead of split across two module copies.
        """
        import experiment_modern_scheduler as live_scheduler

        # Distinct module object: this suite's sandbox copy is its own module.
        self.assertIsNot(MOD, live_scheduler)
        self.assertNotEqual(MOD.__name__, "experiment_modern_scheduler")
        # The sandbox copy is registered only under its unique test-only name.
        self.assertIs(sys.modules.get(MOD.__name__), MOD)
        # The live module entry is intact — routes/binding tests resolve it.
        self.assertIs(sys.modules.get("experiment_modern_scheduler"), live_scheduler)
        self.assertTrue(hasattr(live_scheduler, "ExperimentModernScheduler"))
        self.assertIsNot(live_scheduler.ExperimentModernScheduler, MOD.ExperimentModernScheduler)

    async def test_payload_concurrency_override_ignored(self):
        plans = plans_for([f"c{i:02d}" for i in range(12)])
        executor = FakeExecutor()
        for cid in [p["cell_id"] for p in plans]:
            executor.gates[cid] = asyncio.Event()
        sched, persistence, executor, _ = make_scheduler(plans, executor=executor)
        self.assertEqual(sched.concurrency, 6)
        await sched.start(payload={"concurrency": 1, "max_parallel": 2})
        await wait_until(lambda: len(executor.started) >= 6)
        self.assertEqual(len(executor.started), 6)
        await sched.shutdown()

    async def test_aggregate_status_delegates_to_history(self):
        plans = plans_for(["a"])
        sched, persistence, executor, _ = make_scheduler(plans)
        self.assertEqual(await sched.status(), persistence.aggregate_status())
        await sched.start()
        await await_drain(sched)
        self.assertEqual(await sched.status(), persistence.aggregate_status())
        self.assertEqual(await sched.status(), "completed")

    async def test_sync_execute_and_cancel_callables_supported(self):
        sync_calls = []

        def sync_execute(cell_plan, *, attempt_id, cell_id):
            sync_calls.append((cell_id, attempt_id))
            return None

        sync_cancel_calls = []

        def sync_cancel(attempt_id, cell_id, *, intent, reason):
            sync_cancel_calls.append((attempt_id, cell_id, intent, reason))
            return None

        sched = MOD.ExperimentModernScheduler(
            experiment_id="exp_sync",
            cell_plans=plans_for(["a", "b"]),
            persistence=FakePersistence(plans_for(["a", "b"])),
            execute=sync_execute,
            remote_cancel=sync_cancel,
        )
        await sched.start()
        await await_drain(sched)
        self.assertEqual(len(sync_calls), 2)
        self.assertEqual(await sched.status(), "completed")

        gate = asyncio.Event()
        executor = FakeExecutor()
        executor.gates["x"] = gate
        sched2 = MOD.ExperimentModernScheduler(
            experiment_id="exp_sync2",
            cell_plans=plans_for(["x"]),
            persistence=FakePersistence(plans_for(["x"])),
            execute=executor,
            remote_cancel=sync_cancel,
        )
        await sched2.start()
        await wait_until(lambda: len(executor.started) == 1)
        self.assertEqual(await sched2.cancel_cell("x"), "canceled_running")
        self.assertEqual(len(sync_cancel_calls), 1)
        self.assertEqual(sync_cancel_calls[0][2], "cancel")
        await sched2.shutdown()

    async def test_module_surface_functions(self):
        for name in ("ExperimentModernScheduler", "submit_cell", "cancel_cell", "cancel_experiment"):
            self.assertTrue(hasattr(MOD, name), name)
        executor = FakeExecutor()
        executor.gates["a"] = asyncio.Event()
        sched = MOD.ExperimentModernScheduler(
            experiment_id="exp_surface",
            cell_plans=[],
            persistence=FakePersistence(plans_for(["a"])),
            execute=executor,
            remote_cancel=FakeCanceller(),
        )
        self.assertTrue(MOD.get_scheduler("exp_surface") is sched)
        for name in ("submit_cell", "cancel_cell", "cancel_experiment",
                     "resume", "retry_cell", "status", "shutdown",
                     "_shutdown_mark_interrupted", "_startup_recovery"):
            self.assertTrue(callable(getattr(sched, name)), name)
        await MOD.submit_cell("exp_surface", plan("a"))
        await wait_until(lambda: len(executor.started) == 1)
        result = await MOD.cancel_cell("exp_surface", "a")
        self.assertIn(result, ("canceled_running", "canceled_queued"))
        counts = await MOD.cancel_experiment("exp_surface")
        self.assertEqual(sum(counts.values()), 1)
        self.assertEqual(counts["noop"], 1)
        await sched.shutdown()

    async def test_adapter_wrapper_broad_compat(self):
        class D1LikeAdapter:
            def __init__(self):
                self.inner = FakePersistence(plans_for(["a"]))

            def queued_cells(self):
                return self.inner.load_queued_cells()

            def try_claim_attempt(self, cell_id):
                return self.inner.atomically_claim_queued_attempt(cell_id)

            def get_active_attempt(self, cell_id):
                return self.inner.read_active_attempt(cell_id)

            def set_running(self, attempt_id, cell_id):
                return self.inner.record_running(attempt_id, cell_id)

            def write_terminal(self, attempt_id, cell_id, status, error=None):
                return self.inner.record_terminal(attempt_id, cell_id, status, error)

            def create_attempt_for_resume(self, cell_id):
                return self.inner.create_resume_attempt(cell_id)

            def create_attempt_for_retry(self, cell_id):
                return self.inner.create_retry_attempt(cell_id)

            def list_resumable_cells(self):
                return self.inner.list_recoverable_cells()

            def experiment_status(self):
                return self.inner.aggregate_status()

        adapter = D1LikeAdapter()
        sched, _, executor, _ = make_scheduler(plans_for(["a"]), persistence=adapter)
        await sched.start()
        await await_drain(sched)
        self.assertEqual(active_status(adapter.inner, "a"), "completed")
        self.assertEqual(await sched.status(), "completed")

    async def test_adapter_wrapper_raises_for_incompatible(self):
        class IncompleteAdapter:
            def load_queued_cells(self):
                return []

        with self.assertRaises(TypeError) as ctx:
            MOD.PersistenceAdapter(IncompleteAdapter())
        message = str(ctx.exception)
        self.assertIn("missing required operations", message)
        self.assertIn("record_terminal", message)

    async def test_queued_cancel_with_no_attempt_guard(self):
        persistence = FakePersistence([])
        sched = MOD.ExperimentModernScheduler(
            experiment_id="exp_noattempt",
            cell_plans=[],
            persistence=persistence,
            execute=FakeExecutor(),
            remote_cancel=FakeCanceller(),
        )
        p = plan("z")
        await sched.submit_cell(p)
        self.assertEqual(await sched.cancel_cell("z"), "canceled_queued")
        self.assertIn("z", sched._cancelled_cells)
        await sched.submit_cell(p)
        self.assertIn("z", sched._cancelled_cells)
        self.assertNotIn("z", sched._queue)
        self.assertEqual(len(persistence.cells), 0)
        await sched.shutdown()


class RemoteCancelConfirmationTests(unittest.IsolatedAsyncioTestCase):
    """D3 scheduler-side confirmation semantics for remote cancel.

    A running cell's ``canceled`` terminal may only be persisted after the
    remote-cancel primitive *explicitly confirms*; an unconfirmed result or a
    channel failure leaves the durable running state truthful and returns
    ``"cancel_unconfirmed"``.  ``None`` returns are the explicit legacy
    compatibility mode.  Shutdown always converges to ``interrupted`` after a
    best-effort stop, never ``canceled``.
    """

    async def test_confirmed_result_records_canceled(self):
        plans = plans_for(["a"])
        executor = FakeExecutor()
        executor.gates["a"] = asyncio.Event()
        canceller = ConfirmingCanceller(MOD.CancelResult(confirmed=True, outcome="acknowledged"))
        sched, persistence, executor, canceller = make_scheduler(plans, executor=executor, canceller=canceller)
        await sched.start()
        await wait_until(lambda: len(executor.started) == 1)
        result = await sched.cancel_cell("a")
        self.assertEqual(result, "canceled_running")
        self.assertEqual(len(canceller.calls), 1)
        attempt_id, cell_id, intent, reason = canceller.calls[0]
        self.assertEqual(cell_id, "a")
        self.assertEqual(intent, "cancel")
        self.assertEqual(reason, "user_cancel")
        self.assertEqual(active_status(persistence, "a"), "canceled")
        await wait_until(lambda: not sched._active_tasks)
        self.assertEqual(active_status(persistence, "a"), "canceled")
        await sched.shutdown()

    async def test_confirmed_dict_result_records_canceled(self):
        plans = plans_for(["a"])
        executor = FakeExecutor()
        executor.gates["a"] = asyncio.Event()
        canceller = ConfirmingCanceller({"confirmed": True, "outcome": "cancelled", "detail": "ok"})
        sched, persistence, executor, canceller = make_scheduler(plans, executor=executor, canceller=canceller)
        await sched.start()
        await wait_until(lambda: len(executor.started) == 1)
        self.assertEqual(await sched.cancel_cell("a"), "canceled_running")
        self.assertEqual(active_status(persistence, "a"), "canceled")
        self.assertEqual(len(canceller.calls), 1)
        await sched.shutdown()

    async def test_unconfirmed_result_leaves_durable_running(self):
        plans = plans_for(["a"])
        executor = FakeExecutor()
        executor.gates["a"] = asyncio.Event()
        canceller = ConfirmingCanceller(MOD.CancelResult(confirmed=False, outcome="cancel_unavailable"))
        sched, persistence, executor, canceller = make_scheduler(plans, executor=executor, canceller=canceller)
        await sched.start()
        await wait_until(lambda: len(executor.started) == 1)
        result = await sched.cancel_cell("a")
        self.assertEqual(result, "cancel_unconfirmed")
        self.assertEqual(len(canceller.calls), 1)
        self.assertEqual(active_status(persistence, "a"), "running")
        self.assertEqual(persistence.terminal_writes, [])
        self.assertEqual(executor.running, 1)
        await sched.shutdown()
        self.assertEqual(active_status(persistence, "a"), "interrupted")

    async def test_false_and_unconfirmed_dict_results_do_not_mark_canceled(self):
        for bad in (False, {"confirmed": False}, {"ok": False}, MOD.CancelResult()):
            plans = plans_for(["a"])
            executor = FakeExecutor()
            executor.gates["a"] = asyncio.Event()
            canceller = ConfirmingCanceller(bad)
            sched, persistence, executor, canceller = make_scheduler(plans, executor=executor, canceller=canceller)
            await sched.start()
            await wait_until(lambda: len(executor.started) == 1)
            self.assertEqual(await sched.cancel_cell("a"), "cancel_unconfirmed")
            self.assertEqual(active_status(persistence, "a"), "running")
            self.assertEqual(persistence.terminal_writes, [])
            await sched.shutdown()
            self.assertEqual(active_status(persistence, "a"), "interrupted")

    async def test_channel_exception_returns_unconfirmed(self):
        plans = plans_for(["a"])
        executor = FakeExecutor()
        executor.gates["a"] = asyncio.Event()
        canceller = RaisingCanceller(RuntimeError("channel down"))
        sched, persistence, executor, canceller = make_scheduler(plans, executor=executor, canceller=canceller)
        await sched.start()
        await wait_until(lambda: len(executor.started) == 1)
        result = await sched.cancel_cell("a")
        self.assertEqual(result, "cancel_unconfirmed")
        self.assertEqual(len(canceller.calls), 1)
        self.assertEqual(active_status(persistence, "a"), "running")
        self.assertEqual(persistence.terminal_writes, [])
        await sched.shutdown()
        self.assertEqual(active_status(persistence, "a"), "interrupted")

    async def test_async_and_sync_confirming_callables_supported(self):
        # Async callable returning CancelResult(confirmed=True).
        plans = plans_for(["a"])
        executor = FakeExecutor()
        executor.gates["a"] = asyncio.Event()
        async_canceller = ConfirmingCanceller(MOD.CancelResult(confirmed=True))
        sched, persistence, executor, canceller = make_scheduler(plans, executor=executor, canceller=async_canceller)
        await sched.start()
        await wait_until(lambda: len(executor.started) == 1)
        self.assertEqual(await sched.cancel_cell("a"), "canceled_running")
        self.assertEqual(active_status(persistence, "a"), "canceled")
        await sched.shutdown()

        # Sync callable returning a confirming dict.
        plans2 = plans_for(["b"])
        executor2 = FakeExecutor()
        executor2.gates["b"] = asyncio.Event()
        sync_canceller = SyncConfirmingCanceller({"confirmed": True})
        sched2, persistence2, executor2, canceller2 = make_scheduler(plans2, executor=executor2, canceller=sync_canceller)
        await sched2.start()
        await wait_until(lambda: len(executor2.started) == 1)
        self.assertEqual(await sched2.cancel_cell("b"), "canceled_running")
        self.assertEqual(active_status(persistence2, "b"), "canceled")
        await sched2.shutdown()

        # Sync callable returning a sync unconfirmed result.
        plans3 = plans_for(["c"])
        executor3 = FakeExecutor()
        executor3.gates["c"] = asyncio.Event()
        sync_unconf = SyncConfirmingCanceller({"confirmed": False})
        sched3, persistence3, executor3, canceller3 = make_scheduler(plans3, executor=executor3, canceller=sync_unconf)
        await sched3.start()
        await wait_until(lambda: len(executor3.started) == 1)
        self.assertEqual(await sched3.cancel_cell("c"), "cancel_unconfirmed")
        self.assertEqual(active_status(persistence3, "c"), "running")
        await sched3.shutdown()

    async def test_legacy_none_return_is_explicit_compat_mode(self):
        plans = plans_for(["a"])
        executor = FakeExecutor()
        executor.gates["a"] = asyncio.Event()
        calls = []

        def legacy_cancel(attempt_id, cell_id, *, intent, reason):
            calls.append((attempt_id, cell_id, intent, reason))
            return None

        sched, persistence, executor, _ = make_scheduler(plans, executor=executor, canceller=legacy_cancel)
        await sched.start()
        await wait_until(lambda: len(executor.started) == 1)
        self.assertEqual(await sched.cancel_cell("a"), "canceled_running")
        self.assertEqual(active_status(persistence, "a"), "canceled")
        self.assertEqual(len(calls), 1)
        await sched.shutdown()

    async def test_duplicate_cancel_confirmed_exactly_once(self):
        plans = plans_for(["a"])
        executor = FakeExecutor()
        executor.gates["a"] = asyncio.Event()
        canceller = ConfirmingCanceller(MOD.CancelResult(confirmed=True))
        sched, persistence, executor, canceller = make_scheduler(plans, executor=executor, canceller=canceller)
        await sched.start()
        await wait_until(lambda: len(executor.started) == 1)
        self.assertEqual(await sched.cancel_cell("a"), "canceled_running")
        self.assertEqual(await sched.cancel_cell("a"), "noop")
        self.assertEqual(len(canceller.calls), 1)
        self.assertEqual(active_status(persistence, "a"), "canceled")
        await sched.shutdown()

    async def test_duplicate_cancel_unconfirmed_retries_remote(self):
        plans = plans_for(["a"])
        executor = FakeExecutor()
        executor.gates["a"] = asyncio.Event()
        results = iter([MOD.CancelResult(confirmed=False), MOD.CancelResult(confirmed=True)])
        canceller = ConfirmingCanceller(lambda *args, **kwargs: next(results))
        sched, persistence, executor, canceller = make_scheduler(plans, executor=executor, canceller=canceller)
        await sched.start()
        await wait_until(lambda: len(executor.started) == 1)
        self.assertEqual(await sched.cancel_cell("a"), "cancel_unconfirmed")
        self.assertEqual(active_status(persistence, "a"), "running")
        self.assertEqual(await sched.cancel_cell("a"), "canceled_running")
        self.assertEqual(len(canceller.calls), 2)
        self.assertEqual(active_status(persistence, "a"), "canceled")
        await sched.shutdown()

    async def test_shutdown_preserves_interrupted_when_user_cancel_unconfirmed(self):
        plans = plans_for(["a"])
        executor = FakeExecutor()
        executor.gates["a"] = asyncio.Event()
        canceller = ConfirmingCanceller(MOD.CancelResult(confirmed=False))
        sched, persistence, executor, canceller = make_scheduler(plans, executor=executor, canceller=canceller)
        await sched.start()
        await wait_until(lambda: len(executor.started) == 1)
        self.assertEqual(await sched.cancel_cell("a"), "cancel_unconfirmed")
        await sched.shutdown()
        self.assertEqual(active_status(persistence, "a"), "interrupted")
        self.assertNotEqual(active_status(persistence, "a"), "canceled")

    async def test_shutdown_best_effort_stop_records_interrupted_on_channel_failure(self):
        plans = plans_for(["a"])
        executor = FakeExecutor()
        executor.gates["a"] = asyncio.Event()
        canceller = RaisingCanceller(RuntimeError("channel down"))
        sched, persistence, executor, canceller = make_scheduler(plans, executor=executor, canceller=canceller)
        await sched.start()
        await wait_until(lambda: len(executor.started) == 1)
        await sched.shutdown()
        self.assertEqual(active_status(persistence, "a"), "interrupted")
        self.assertEqual(len(canceller.calls), 1)

    async def test_no_durable_false_cancel_on_unconfirmed(self):
        plans = plans_for(["a"])
        executor = FakeExecutor()
        executor.gates["a"] = asyncio.Event()
        canceller = ConfirmingCanceller({"confirmed": False, "outcome": "cancel_unavailable"})
        sched, persistence, executor, canceller = make_scheduler(plans, executor=executor, canceller=canceller)
        await sched.start()
        await wait_until(lambda: len(executor.started) == 1)
        self.assertEqual(await sched.cancel_cell("a"), "cancel_unconfirmed")
        self.assertEqual(persistence.terminal_writes, [])
        history = persistence.attempt_history("a")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "running")
        self.assertEqual(await sched.status(), "running")
        await sched.shutdown()
        self.assertEqual(active_status(persistence, "a"), "interrupted")

    async def test_cancel_experiment_counts_unconfirmed_outcomes(self):
        plans = plans_for(["a", "b"])
        executor = FakeExecutor()
        executor.gates["a"] = asyncio.Event()
        executor.gates["b"] = asyncio.Event()
        outcomes = {
            "a": MOD.CancelResult(confirmed=True),
            "b": MOD.CancelResult(confirmed=False),
        }

        class PerCellCanceller:
            def __init__(self):
                self.calls = []

            async def __call__(self, attempt_id, cell_id, *, intent, reason):
                self.calls.append((attempt_id, cell_id, intent, reason))
                return outcomes[cell_id]

        canceller = PerCellCanceller()
        sched, persistence, executor, canceller = make_scheduler(plans, executor=executor, canceller=canceller)
        await sched.start()
        await wait_until(lambda: len(executor.started) == 2)
        counts = await sched.cancel_experiment()
        self.assertEqual(counts["canceled_running"], 1)
        self.assertEqual(counts["cancel_unconfirmed"], 1)
        self.assertEqual(counts["canceled_queued"], 0)
        self.assertEqual(counts["noop"], 0)
        self.assertEqual(active_status(persistence, "a"), "canceled")
        self.assertEqual(active_status(persistence, "b"), "running")
        await sched.shutdown()
        self.assertEqual(active_status(persistence, "b"), "interrupted")


if __name__ == "__main__":
    unittest.main()
