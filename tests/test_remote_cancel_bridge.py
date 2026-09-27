"""Focused deterministic tests for the remote cooperative cancellation bridge.

Covers, with pure in-process stubs (no Modal network, no paid run):
  * per-invocation watcher starts and stops (bounded join, no lingering thread)
  * no-message normal execution (watcher idles, never confirms)
  * partition / attempt identity matching (mismatched cancels are ignored)
  * primitive-only ``cancel`` messages (non-dicts, non-primitives, and wrong
    message types are ignored)
  * cancel event + ComfyUI native interrupt call (``interrupt_fn(True)``)
  * ``RuntimeExecutor.stream`` terminal classification:
      - a confirmed cancel never becomes a generic ``error`` event
      - ordinary errors are unchanged
      - a late cancel after the result has begun preserves the normal result
  * existing ``cancelled`` callback behavior preserved via
    ``combine_cancel_predicate``
  * end-to-end ``run_plan_stream`` integration: ``control_queue`` message ->
    explicit ``cancelled`` terminal event (``confirmed=True``); the watcher is
    joined; a normal no-cancel run and a legacy-callback cancel are unchanged.
"""

from __future__ import annotations

import asyncio
import threading
import time
import unittest
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
from comfymodal_runtime import modal_app
from comfymodal_runtime import runtime_executor
from comfymodal_runtime.modal_app import resolve_post_executor_cancel
from comfymodal_runtime.runtime_executor import (
    ExecutionContext,
    RemoteCancellationError,
    RemoteCancelWatcher,
    RuntimeExecutor,
    build_remote_cancel_terminal_event,
    combine_cancel_predicate,
    guard_remote_cancel_stream,
)


# ── In-process stubs ─────────────────────────────────────────────────────


class _FakeControlQueue:
    """Deterministic in-process stand-in for a hydrated Modal Queue partition.

    ``get(block=True, timeout=..., partition=...)`` blocks until a message is
    available or the timeout elapses (then raises ``TimeoutError``), mirroring
    what the watcher expects from the real queue.  Partition isolation is
    enforced: a message whose payload carries a ``partition`` is served only
    to a ``get`` polling that same partition — exactly like Modal's routing —
    so a mispartitioned cancel can never leak across attempts.
    """

    def __init__(self) -> None:
        self._messages: list[Any] = []
        self._lock = threading.Lock()
        self.put_calls: list[tuple[Any, str | None]] = []

    def put(self, msg: Any, partition: str | None = None) -> None:
        with self._lock:
            self._messages.append(msg)
            self.put_calls.append((msg, str(partition) if partition is not None else None))

    def get(
        self,
        block: bool = True,
        timeout: float | None = None,
        partition: Any = None,
    ) -> Any:
        wanted = str(partition if partition is not None else "")
        deadline = time.time() + (float(timeout) if timeout is not None else 5.0)
        while True:
            with self._lock:
                for index, msg in enumerate(self._messages):
                    if isinstance(msg, dict):
                        msg_partition = msg.get("partition")
                        if msg_partition is not None and str(msg_partition) != wanted:
                            continue  # addressed to a different partition
                    return self._messages.pop(index)
            if time.time() >= deadline:
                raise TimeoutError("fake queue poll timeout")
            time.sleep(0.001)


class _PersistentFailureQueue:
    """Queue whose ``get`` raises a non-timeout error every poll (the channel
    is permanently broken — polling must not spin forever)."""

    def __init__(self) -> None:
        self.calls = 0

    def put(self, msg: Any, partition: str | None = None) -> None:
        pass

    def get(
        self,
        block: bool = True,
        timeout: float | None = None,
        partition: Any = None,
    ) -> Any:
        self.calls += 1
        raise ConnectionError("queue backend unreachable")


def _busy_runner(
    *,
    cancel_check_interval: float = 0.005,
    run_budget: float = 10.0,
):
    """Runner that mimics busy PromptExecutor sampling.

    Polls the combined ``ctx.cancelled()`` predicate (which the impl merges
    with the watcher event) and raises ``asyncio.CancelledError`` — exactly
    like ComfyUI's native ``interrupt_current_processing`` path — or returns a
    normal result when the budget elapses without a cancel.
    """

    def runner(plan: Any, ctx: ExecutionContext) -> dict[str, Any]:
        deadline = time.time() + run_budget
        while time.time() < deadline:
            if ctx.cancelled and ctx.cancelled():
                raise asyncio.CancelledError()
            time.sleep(cancel_check_interval)
        return {"ok": True, "trace": {}}

    return runner


def _raising_runner(exc: BaseException):
    """Runner factory that raises *exc* when invoked."""

    def runner(plan: Any, ctx: ExecutionContext) -> Any:
        raise exc

    return runner


async def _raise_stream(exc: BaseException) -> Any:
    """Async generator that raises *exc* on first iteration."""
    if False:
        yield None  # pragma: no cover - marks this as an async generator
    raise exc


class _RaiseStream:
    """Async iterator that raises *exc* on the first ``__anext__``."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def __aiter__(self) -> "_RaiseStream":
        return self

    async def __anext__(self) -> Any:
        raise self._exc


async def _events_stream(events: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
    """Async generator yielding the given events."""
    for event in events:
        yield event


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        workflow={"1": {"class_type": "KSampler"}},
        execution_options=ExecutionOptions(production_enabled=False),
    )


# ── Watcher unit tests ───────────────────────────────────────────────────


class TestRemoteCancelWatcher(unittest.TestCase):
    def _watcher(self, queue: Any, partition: Any = "attempt-42", **kw: Any) -> RemoteCancelWatcher:
        return RemoteCancelWatcher(
            queue,
            partition,
            request_id="req-1",
            poll_timeout=0.05,
            **kw,
        )

    def test_starts_and_stops_bounded(self):
        watcher = self._watcher(_FakeControlQueue()).start()
        self.assertTrue(watcher.thread_alive)
        watcher.stop_and_join(timeout=2.0)
        self.assertFalse(watcher.thread_alive)
        # Idempotent: stopping again is a no-op.
        watcher.stop_and_join()
        self.assertFalse(watcher.thread_alive)

    def test_no_messages_normal_idle(self):
        watcher = self._watcher(_FakeControlQueue()).start()
        time.sleep(0.15)  # let it poll several times
        self.assertFalse(watcher.cancel_confirmed)
        watcher.stop_and_join()
        self.assertFalse(watcher.thread_alive)
        self.assertFalse(watcher.cancel_confirmed)

    def test_matching_cancel_sets_event_and_calls_native_interrupt(self):
        queue = _FakeControlQueue()
        interrupts: list[bool] = []
        watcher = self._watcher(
            queue, interrupt_fn=lambda value: interrupts.append(value),
        ).start()
        queue.put({"type": "cancel", "attempt_id": "attempt-42"})
        self.assertTrue(watcher.cancel_event.wait(timeout=2.0))
        self.assertTrue(watcher.cancel_confirmed)
        self.assertEqual(interrupts, [True])
        watcher.stop_and_join()
        self.assertFalse(watcher.thread_alive)

    def test_mismatched_attempt_id_is_ignored(self):
        queue = _FakeControlQueue()
        interrupts: list[bool] = []
        watcher = self._watcher(
            queue, interrupt_fn=lambda value: interrupts.append(value),
        ).start()
        queue.put({"type": "cancel", "attempt_id": "attempt-OTHER"})
        time.sleep(0.15)
        self.assertFalse(watcher.cancel_confirmed)
        self.assertEqual(interrupts, [])
        # A subsequently matching cancel is still accepted.
        queue.put({"type": "cancel", "attempt_id": "attempt-42"})
        self.assertTrue(watcher.cancel_event.wait(timeout=2.0))
        self.assertEqual(interrupts, [True])
        watcher.stop_and_join()

    def test_cancel_without_attempt_id_is_partition_scoped(self):
        queue = _FakeControlQueue()
        interrupts: list[bool] = []
        watcher = self._watcher(
            queue, interrupt_fn=lambda value: interrupts.append(value),
        ).start()
        queue.put({"type": "cancel"})
        self.assertTrue(watcher.cancel_event.wait(timeout=2.0))
        self.assertEqual(interrupts, [True])
        watcher.stop_and_join()

    def test_transport_format_cancel_message_accepted(self):
        # The local transport builds primitive cancel messages as
        # ``{"type": "cancel", "partition": ..., "reason": ...}`` — keyed by
        # partition.  The watcher must accept the matching partition.
        queue = _FakeControlQueue()
        interrupts: list[bool] = []
        watcher = self._watcher(
            queue, interrupt_fn=lambda value: interrupts.append(value),
        ).start()
        queue.put({"type": "cancel", "partition": "attempt-42", "reason": "user requested"})
        self.assertTrue(watcher.cancel_event.wait(timeout=2.0))
        self.assertEqual(interrupts, [True])
        watcher.stop_and_join()

    def test_mismatched_partition_field_is_ignored(self):
        queue = _FakeControlQueue()
        interrupts: list[bool] = []
        watcher = self._watcher(
            queue, interrupt_fn=lambda value: interrupts.append(value),
        ).start()
        queue.put({"type": "cancel", "partition": "attempt-OTHER", "reason": "wrong attempt"})
        time.sleep(0.15)
        self.assertFalse(watcher.cancel_confirmed)
        self.assertEqual(interrupts, [])
        watcher.stop_and_join()

    def test_non_cancel_and_non_primitive_messages_ignored(self):
        queue = _FakeControlQueue()
        watcher = self._watcher(queue).start()
        queue.put({"type": "progress", "step": 1})
        queue.put({"type": "cancel", "attempt_id": "attempt-42", "nested": {"a": 1}})
        queue.put({"type": "cancel", "attempt_id": "attempt-42", "values": [1, 2]})
        queue.put("a plain string")
        queue.put(None)
        time.sleep(0.15)
        self.assertFalse(watcher.cancel_confirmed)
        watcher.stop_and_join()

    def test_no_lingering_watcher_thread(self):
        queue = _FakeControlQueue()
        watcher = self._watcher(queue).start()
        watcher.stop_and_join(timeout=2.0)
        self.assertFalse(watcher.thread_alive)
        remaining = [
            t for t in threading.enumerate()
            if t.name.startswith("comfymodal-remote-cancel-watcher")
        ]
        self.assertEqual(remaining, [])

    def test_poll_timeout_keeps_watcher_polling(self):
        # A queue that only ever times out must keep the watcher polling
        # (healthy no-message path) — never treated as a channel failure.
        queue = _FakeControlQueue()
        watcher = self._watcher(queue).start()
        time.sleep(0.15)
        self.assertTrue(watcher.thread_alive)
        self.assertFalse(watcher.cancel_confirmed)
        self.assertIsNone(watcher.queue_error)
        watcher.stop_and_join()
        self.assertFalse(watcher.thread_alive)

    def test_persistent_queue_error_stops_watcher(self):
        # Finding 5: a persistent (non-timeout) queue error must STOP the
        # watcher and be surfaced — never silently spin forever.
        queue = _PersistentFailureQueue()
        watcher = self._watcher(queue).start()
        deadline = time.time() + 5.0
        while watcher.thread_alive and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(watcher.thread_alive, "watcher must not spin forever")
        self.assertIsInstance(watcher.queue_error, ConnectionError)
        self.assertFalse(watcher.cancel_confirmed)
        self.assertGreater(queue.calls, 0)
        # No lingering thread survives the failure.
        remaining = [
            t for t in threading.enumerate()
            if t.name.startswith("comfymodal-remote-cancel-watcher")
        ]
        self.assertEqual(remaining, [])


# ── Combined cancel predicate ────────────────────────────────────────────


class TestCombineCancelPredicate(unittest.TestCase):
    def test_no_cancel_path_unchanged(self):
        self.assertIsNone(combine_cancel_predicate(None, None))
        callback = lambda: False  # noqa: E731
        self.assertIs(combine_cancel_predicate(callback, None), callback)

    def test_event_only_predicate(self):
        event = threading.Event()
        predicate = combine_cancel_predicate(None, event)
        assert predicate is not None
        self.assertFalse(predicate())
        event.set()
        self.assertTrue(predicate())

    def test_existing_callback_still_fires(self):
        event = threading.Event()
        calls: list[int] = []

        def callback() -> bool:
            calls.append(1)
            return True

        predicate = combine_cancel_predicate(callback, event)
        assert predicate is not None
        self.assertTrue(predicate())
        self.assertEqual(calls, [1])
        calls.clear()
        predicate_false = combine_cancel_predicate(lambda: False, event)
        assert predicate_false is not None
        self.assertFalse(predicate_false())

    def test_raising_callback_does_not_mask_watcher_event(self):
        event = threading.Event()

        def callback() -> bool:
            raise RuntimeError("legacy callback failed")

        predicate = combine_cancel_predicate(callback, event)
        assert predicate is not None
        event.set()
        self.assertTrue(predicate())


# ── RuntimeExecutor terminal classification ──────────────────────────────


class TestRuntimeExecutorCancellationClassification(unittest.TestCase):
    def _run_stream(self, executor: RuntimeExecutor, ctx: ExecutionContext) -> list[dict[str, Any]]:
        async def run() -> list[dict[str, Any]]:
            return [event async for event in executor.stream(_plan(), context=ctx)]
        return asyncio.run(run())

    def test_confirmed_cancel_is_not_generic_error(self):
        event = threading.Event()
        event.set()
        ctx = ExecutionContext(request_id="r-1", remote_cancel_event=event)
        executor = RuntimeExecutor(in_process_runner=_raising_runner(RuntimeError("boom")))
        with self.assertRaises(RemoteCancellationError):
            self._run_stream(executor, ctx)

    def test_ordinary_error_unchanged(self):
        ctx = ExecutionContext(request_id="r-2")
        executor = RuntimeExecutor(in_process_runner=_raising_runner(RuntimeError("boom")))
        events = self._run_stream(executor, ctx)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(events[0]["message"], "boom")

    def test_late_cancel_preserves_normal_result(self):
        # The cancel event is already set, but the runner returned normally:
        # the result is preserved (late cancel after result has begun).
        event = threading.Event()
        event.set()
        ctx = ExecutionContext(request_id="r-3", remote_cancel_event=event)
        executor = RuntimeExecutor(in_process_runner=lambda plan, ctx: {"ok": True})
        events = self._run_stream(executor, ctx)
        self.assertEqual(events[0]["type"], "result")
        self.assertEqual(events[0]["data"]["ok"], True)

    def test_normal_result_unchanged(self):
        ctx = ExecutionContext(request_id="r-4")
        executor = RuntimeExecutor(in_process_runner=lambda plan, ctx: {"ok": True})
        events = self._run_stream(executor, ctx)
        self.assertEqual(events[0]["type"], "result")
        self.assertEqual(events[0]["data"]["ok"], True)

    def test_cancelled_error_from_runner_propagates(self):
        # Native ComfyUI interruption surfaces as asyncio.CancelledError; the
        # executor must NOT convert it to a generic error event.  The bridge
        # guard classifies it (confirmed -> cancelled terminal) one layer up.
        event = threading.Event()
        event.set()
        ctx = ExecutionContext(request_id="r-5", remote_cancel_event=event)
        executor = RuntimeExecutor(
            in_process_runner=_raising_runner(asyncio.CancelledError()),
        )
        with self.assertRaises(asyncio.CancelledError):
            self._run_stream(executor, ctx)

    def test_execute_re_raises_confirmed_cancel(self):
        event = threading.Event()
        event.set()
        ctx = ExecutionContext(request_id="r-6", remote_cancel_event=event)
        executor = RuntimeExecutor(
            in_process_runner=_raising_runner(RuntimeError("boom")),
        )
        with self.assertRaises(RemoteCancellationError):
            asyncio.run(executor.execute(_plan(), context=ctx))


# ── Stream bridge guard ──────────────────────────────────────────────────


class TestGuardRemoteCancelStream(unittest.TestCase):
    def _watcher(self) -> RemoteCancelWatcher:
        return RemoteCancelWatcher(
            _FakeControlQueue(), "attempt-42", request_id="r-1", poll_timeout=0.05,
        ).start()

    def test_confirmed_cancelled_error_becomes_terminal_event(self):
        async def run() -> list[dict[str, Any]]:
            watcher = self._watcher()
            watcher.cancel_event.set()  # watcher confirmed a matching cancel

            events = [
                event async for event in guard_remote_cancel_stream(
                    _RaiseStream(asyncio.CancelledError()),
                    watcher=watcher,
                    request_id="r-1",
                )
            ]
            self.assertFalse(watcher.thread_alive)  # watcher stopped/joined
            return events

        events = asyncio.run(run())
        self.assertEqual(
            events,
            [{"type": "cancelled", "request_id": "r-1", "reason": "remote_cancel", "confirmed": True}],
        )

    def test_confirmed_marker_exception_becomes_terminal_event(self):
        async def run() -> list[dict[str, Any]]:
            watcher = self._watcher()
            watcher.cancel_event.set()

            events = [
                event async for event in guard_remote_cancel_stream(
                    _RaiseStream(RemoteCancellationError("interrupted")),
                    watcher=watcher,
                    request_id="r-1",
                )
            ]
            self.assertFalse(watcher.thread_alive)
            return events

        events = asyncio.run(run())
        self.assertEqual(
            events,
            [{"type": "cancelled", "request_id": "r-1", "reason": "remote_cancel", "confirmed": True}],
        )

    def test_unconfirmed_cancelled_error_propagates(self):
        async def run() -> None:
            watcher = self._watcher()  # never confirmed
            calls: list[Any] = []

            with self.assertRaises(asyncio.CancelledError):
                async for event in guard_remote_cancel_stream(
                    _RaiseStream(asyncio.CancelledError()),
                    watcher=watcher,
                    request_id="r-1",
                ):
                    calls.append(event)
            self.assertFalse(watcher.thread_alive)  # still stopped by finally

        asyncio.run(run())

    def test_passthrough_without_cancel(self):
        async def run() -> list[dict[str, Any]]:
            watcher = self._watcher()
            out = [
                event async for event in guard_remote_cancel_stream(
                    _events_stream([
                        {"type": "status", "phase": "x"},
                        {"type": "result", "data": {"ok": True}},
                    ]),
                    watcher=watcher,
                    request_id="r-1",
                )
            ]
            self.assertFalse(watcher.thread_alive)
            return out

        out = asyncio.run(run())
        self.assertEqual(
            out,
            [{"type": "status", "phase": "x"}, {"type": "result", "data": {"ok": True}}],
        )

    def test_no_watcher_passthrough(self):
        async def run() -> list[dict[str, Any]]:
            return [
                event async for event in guard_remote_cancel_stream(
                    _events_stream([{"type": "result", "data": {"ok": True}}]),
                    watcher=None,
                    request_id="r-1",
                )
            ]

        self.assertEqual(
            asyncio.run(run()),
            [{"type": "result", "data": {"ok": True}}],
        )

    def test_terminal_event_shape(self):
        event = build_remote_cancel_terminal_event("req-9", reason="remote_cancel")
        self.assertEqual(event, {
            "type": "cancelled",
            "request_id": "req-9",
            "reason": "remote_cancel",
            "confirmed": True,
        })

    def test_terminal_event_preserves_matched_reason(self):
        # Finding 3: a matched cancel message's reason is preserved through the
        # terminal event (shutdown stays distinguishable from user cancel);
        # the generic label is only the empty-reason fallback.
        self.assertEqual(
            build_remote_cancel_terminal_event("req-9", reason="shutdown")["reason"],
            "shutdown",
        )
        self.assertEqual(
            build_remote_cancel_terminal_event("req-9", reason="user_cancel")["reason"],
            "user_cancel",
        )
        self.assertEqual(
            build_remote_cancel_terminal_event("req-9")["reason"],
            "remote_cancel",
        )

    def test_confirmed_cancel_preserves_matched_reason(self):
        # Finding 3 end-to-end through the guard: the reason recorded by the
        # watcher from the matched queue message is what the terminal event
        # carries — never a hardcoded label.
        async def run() -> list[dict[str, Any]]:
            watcher = self._watcher()
            watcher.cancel_event.set()
            watcher._cancel_reason = "shutdown"  # set by _run on a matched msg

            events = [
                event async for event in guard_remote_cancel_stream(
                    _RaiseStream(asyncio.CancelledError()),
                    watcher=watcher,
                    request_id="r-1",
                )
            ]
            self.assertFalse(watcher.thread_alive)  # watcher stopped/joined
            return events

        events = asyncio.run(run())
        self.assertEqual(
            events,
            [{"type": "cancelled", "request_id": "r-1", "reason": "shutdown", "confirmed": True}],
        )

    def test_empty_reason_falls_back_to_remote_cancel(self):
        # A watcher that matched a reason-less message keeps the legacy label.
        async def run() -> list[dict[str, Any]]:
            watcher = self._watcher()
            watcher.cancel_event.set()

            events = [
                event async for event in guard_remote_cancel_stream(
                    _RaiseStream(RemoteCancellationError("interrupted")),
                    watcher=watcher,
                    request_id="r-1",
                )
            ]
            return events

        events = asyncio.run(run())
        self.assertEqual(events[0]["reason"], "remote_cancel")


class TestPostExecutorCompletionFirst(unittest.TestCase):
    """Finding 2 regression: the production post-executor check must never
    discard outputs after a successful PromptExecutor completion, even when a
    watcher cancel arrives late (success=True wins)."""

    def test_successful_completion_wins_over_late_cancel(self):
        # The exact production shape: executor.success is True and a late
        # watcher cancel has already fired.  Completion-first: no error.
        self.assertIsNone(resolve_post_executor_cancel(lambda: True, executor_success=True))

    def test_successful_completion_no_cancel_still_proceeds(self):
        self.assertIsNone(resolve_post_executor_cancel(lambda: False, executor_success=True))
        self.assertIsNone(resolve_post_executor_cancel(None, executor_success=True))

    def test_raising_cancel_callback_never_masks_completion(self):
        def boom() -> bool:
            raise RuntimeError("legacy callback failed")

        self.assertIsNone(resolve_post_executor_cancel(boom, executor_success=True))

    def test_failed_execution_can_be_reclassified_as_cancelled(self):
        self.assertEqual(
            resolve_post_executor_cancel(lambda: True, executor_success=False),
            "execution cancelled after PromptExecutor completion",
        )

    def test_failed_execution_without_cancel_stays_executor_error(self):
        # Non-successful execution with no cancel: the caller surfaces the
        # executor error itself; the helper reports no cancellation.
        self.assertIsNone(resolve_post_executor_cancel(lambda: False, executor_success=False))
        self.assertIsNone(resolve_post_executor_cancel(None, executor_success=False))


# ── End-to-end run_plan_stream integration ───────────────────────────────


class TestRunPlanStreamRemoteCancelIntegration(unittest.TestCase):
    def _entrypoint(self, runner: Any) -> modal_app.ModalRuntimeEntrypoint:
        return modal_app.ModalRuntimeEntrypoint(
            executor=RuntimeExecutor(in_process_runner=runner),
        )

    def _no_watcher_threads(self) -> None:
        remaining = [
            t for t in threading.enumerate()
            if t.name.startswith("comfymodal-remote-cancel-watcher")
        ]
        self.assertEqual(remaining, [])

    def test_confirmed_cancel_emits_terminal_cancelled_event(self):
        async def run() -> tuple[list[dict[str, Any]], list[bool]]:
            queue = _FakeControlQueue()
            interrupts: list[bool] = []
            entrypoint = self._entrypoint(_busy_runner())
            injected = False
            messages: list[dict[str, Any]] = []
            with patch.object(
                runtime_executor, "_default_interrupt_fn",
                lambda value: interrupts.append(value),
            ):
                async for msg in entrypoint.run_plan_stream(
                    _plan().to_dict(),
                    request_id="req-cancel",
                    control_queue=queue,
                    control_partition="attempt-42",
                ):
                    messages.append(msg)
                    if msg.get("type") == "status" and not injected:
                        injected = True
                        queue.put({"type": "cancel", "attempt_id": "attempt-42"})
            return messages, interrupts

        messages, interrupts = asyncio.run(run())
        types = [m["type"] for m in messages]
        self.assertIn("cancelled", types)
        terminal = next(m for m in messages if m["type"] == "cancelled")
        self.assertEqual(terminal["request_id"], "req-cancel")
        self.assertEqual(terminal["reason"], "remote_cancel")
        self.assertEqual(terminal["confirmed"], True)
        # The native interrupt seam was invoked exactly once with True.
        self.assertEqual(interrupts, [True])
        self._no_watcher_threads()

    def test_cancel_message_reason_preserved_through_terminal_event(self):
        # Finding 3 end-to-end: the queue message's reason flows through the
        # watcher -> guard -> terminal event (shutdown stays distinguishable).
        async def run() -> tuple[list[dict[str, Any]], list[bool]]:
            queue = _FakeControlQueue()
            interrupts: list[bool] = []
            entrypoint = self._entrypoint(_busy_runner())
            injected = False
            messages: list[dict[str, Any]] = []
            with patch.object(
                runtime_executor, "_default_interrupt_fn",
                lambda value: interrupts.append(value),
            ):
                async for msg in entrypoint.run_plan_stream(
                    _plan().to_dict(),
                    request_id="req-reason",
                    control_queue=queue,
                    control_partition="attempt-42",
                ):
                    messages.append(msg)
                    if msg.get("type") == "status" and not injected:
                        injected = True
                        queue.put({
                            "type": "cancel",
                            "attempt_id": "attempt-42",
                            "reason": "shutdown",
                        })
            return messages, interrupts

        messages, interrupts = asyncio.run(run())
        terminal = next(m for m in messages if m["type"] == "cancelled")
        self.assertEqual(terminal["reason"], "shutdown")
        self.assertEqual(terminal["confirmed"], True)
        self.assertEqual(interrupts, [True])
        self._no_watcher_threads()

    def test_confirmed_cancel_is_terminal(self):
        # The cancelled event is a terminal event: it must not be preceded by
        # a result and no result may follow it.
        async def run() -> list[dict[str, Any]]:
            queue = _FakeControlQueue()
            entrypoint = self._entrypoint(_busy_runner())
            injected = False
            messages: list[dict[str, Any]] = []
            async for msg in entrypoint.run_plan_stream(
                _plan().to_dict(),
                request_id="req-cancel-2",
                control_queue=queue,
                control_partition="attempt-42",
            ):
                messages.append(msg)
                if msg.get("type") == "status" and not injected:
                    injected = True
                    queue.put({"type": "cancel", "attempt_id": "attempt-42"})
            return messages

        messages = asyncio.run(run())
        index = next(i for i, m in enumerate(messages) if m["type"] == "cancelled")
        self.assertNotIn("result", [m["type"] for m in messages[:index]])
        self.assertNotIn("result", [m["type"] for m in messages[index + 1:]])

    def test_no_cancel_message_normal_result(self):
        async def run() -> list[dict[str, Any]]:
            queue = _FakeControlQueue()
            entrypoint = self._entrypoint(lambda plan, ctx: {"ok": True})
            return [
                msg async for msg in entrypoint.run_plan_stream(
                    _plan().to_dict(),
                    request_id="req-normal",
                    control_queue=queue,
                    control_partition="attempt-42",
                )
            ]

        messages = asyncio.run(run())
        types = [m["type"] for m in messages]
        self.assertIn("result", types)
        self.assertNotIn("cancelled", types)
        self._no_watcher_threads()

    def test_nonmatching_attempt_id_ignored_end_to_end(self):
        async def run() -> list[dict[str, Any]]:
            queue = _FakeControlQueue()
            # Mismatched attempt id: the watcher must ignore it and execution
            # must complete normally.
            queue.put({"type": "cancel", "attempt_id": "attempt-OTHER"})
            entrypoint = self._entrypoint(_busy_runner(run_budget=0.6))
            return [
                msg async for msg in entrypoint.run_plan_stream(
                    _plan().to_dict(),
                    request_id="req-mismatch",
                    control_queue=queue,
                    control_partition="attempt-42",
                )
            ]

        messages = asyncio.run(run())
        types = [m["type"] for m in messages]
        self.assertIn("result", types)
        self.assertNotIn("cancelled", types)

    def test_late_cancel_after_result_preserves_result(self):
        async def run() -> list[dict[str, Any]]:
            queue = _FakeControlQueue()
            # A cancel that would only arrive after the result: the stream
            # must not reclassify the delivered result (late cancel ignored).
            queue.put({"type": "cancel", "attempt_id": "attempt-42"})
            entrypoint = self._entrypoint(lambda plan, ctx: {"ok": True})
            return [
                msg async for msg in entrypoint.run_plan_stream(
                    _plan().to_dict(),
                    request_id="req-late",
                    control_queue=queue,
                    control_partition="attempt-42",
                )
            ]

        messages = asyncio.run(run())
        types = [m["type"] for m in messages]
        self.assertIn("result", types)
        self.assertNotIn("cancelled", types)

    def test_legacy_callback_cancel_not_mislabeled(self):
        # A host-side `cancelled` callback firing mid-run (with no remote
        # control message) must keep the existing behavior: it propagates
        # asyncio.CancelledError and is NEVER reclassified as a confirmed
        # user cancellation.
        async def run() -> list[str]:
            queue = _FakeControlQueue()
            flag = {"on": False}
            entrypoint = self._entrypoint(_busy_runner())
            seen: list[str] = []
            with self.assertRaises(asyncio.CancelledError):
                async for msg in entrypoint.run_plan_stream(
                    _plan().to_dict(),
                    request_id="req-legacy",
                    cancelled=lambda: flag["on"],
                    control_queue=queue,
                    control_partition="attempt-42",
                ):
                    seen.append(msg.get("type", ""))
                    if msg.get("type") == "status":
                        flag["on"] = True
            return seen

        seen = asyncio.run(run())
        self.assertNotIn("cancelled", seen)
        self.assertIn("status", seen)

    def test_no_control_queue_path_unchanged(self):
        async def run() -> list[dict[str, Any]]:
            entrypoint = self._entrypoint(lambda plan, ctx: {"ok": True})
            return [
                msg async for msg in entrypoint.run_plan_stream(
                    _plan().to_dict(), request_id="req-plain",
                )
            ]

        messages = asyncio.run(run())
        types = [m["type"] for m in messages]
        self.assertIn("result", types)
        self.assertNotIn("cancelled", types)
        self._no_watcher_threads()


if __name__ == "__main__":
    unittest.main()
