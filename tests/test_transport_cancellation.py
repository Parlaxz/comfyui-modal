"""Focused transport/IPC cooperative cancellation tests.

Proves the transport-owned cooperative cancellation seam for both transport
modes:

- Direct V2 transport: lazily resolves/caches the named Modal control Queue
  and passes the hydrated handle + ``control_partition=request_id`` into every
  ``run_plan_stream.remote_gen.aio(...)`` path (including stale/fallback
  retries).
- Persistent IPC transport: the JSON request carries the queue name/partition;
  the owner resolves the same named Queue through its cached client and hands
  the hydrated handle to the remote generator; cancellation is sent through its
  OWN dedicated loopback channel (``cancel_attempt``), never the busy stream
  socket.

Verdict truthfulness is central: a Queue put is ``pending`` (NOT
confirmation); the handle becomes ``confirmed`` only when the stream consumer
observes the remote ``cancelled`` event (``confirmed: True``); channel
failures are ``unavailable``; completion-before-cancel is distinguished from
a still-pending cancellation; duplicate cancels are idempotent.  A
``cancelled`` event never triggers the normal result → shielded persistence
drain, and the normal persistence-drain behavior is byte-for-byte preserved.

All tests are local: no real Modal calls, no network beyond the loopback IPC
server, no ComfyUI imports.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from comfymodal_runtime import local_handle_owner as owner_mod
from comfymodal_runtime.contracts import ExecutionPlan
from comfymodal_runtime.local_handle_client import (
    CANCEL_STATE_COMPLETED_BEFORE_CANCEL,
    CANCEL_STATE_CONFIRMED,
    CANCEL_STATE_PENDING,
    CANCEL_STATE_UNAVAILABLE,
    PersistentHandleClient,
    PersistentHandleError,
    PersistentHandleUnavailable,
    RemoteCancellationHandle,
    build_cancel_message,
)
from comfymodal_runtime.modal_transport import (
    ModalTransport,
    get_persistence_status,
    join_persistence_drain,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
_AUTH = "test-auth-cancel"


# ═══════════════════════════════════════════════════════════════════════
# Shared fakes
# ═══════════════════════════════════════════════════════════════════════


class _FakeQueue:
    """Synchronous fake Modal Queue recording every put.

    Mirrors the real Modal partitioned-Queue contract: every put must declare
    the routing ``partition`` keyword AND it must equal the message payload's
    ``partition`` — a mismatch raises so a producer that forgets to route on
    partition (delivering to the default partition) fails the test loudly.
    """

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.put_calls: int = 0
        self.put_partitions: list[str] = []

    def put(self, message, partition: str | None = None) -> None:
        self.put_calls += 1
        msg = dict(message)
        routed = str(partition if partition is not None else "")
        payload = str(msg.get("partition", "") or "")
        if routed != payload:
            raise AssertionError(
                f"queue.put routed to partition {routed!r} but the message "
                f"payload carries {payload!r} — cancel messages must be "
                f"delivered to their own partition"
            )
        self.messages.append(msg)
        self.put_partitions.append(routed)


class _FakeStream:
    """A remote-gen stream: consumes events, supports aclose."""

    def __init__(self, events) -> None:
        self._events = list(events)
        self._i = 0
        self.input_id = "in-test"
        self.input_created_at = 1.0
        self.aclosed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._i >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._i]
        self._i += 1
        return event

    async def aclose(self) -> None:
        self.aclosed = True


class _RemoteGen:
    def __init__(self, handle) -> None:
        self._handle = handle

    def aio(self, payload, request_id="", **kwargs):
        self._handle.aio_calls.append({
            "payload": payload, "request_id": request_id, "kwargs": dict(kwargs),
        })
        return _FakeStream(self._handle._events)


class _FakeHandle:
    """``run_plan_stream.remote_gen.aio(...)`` compatible fake handle.

    ``aio_calls`` records every invocation (payload, request_id, kwargs) so
    control-queue propagation is assertable.
    """

    def __init__(self, events=None) -> None:
        self._events = list(events or [{"type": "result", "data": {"images": [], "outputs": {}}}])
        self.aio_calls: list[dict] = []
        self.run_plan_stream = SimpleNamespace(remote_gen=_RemoteGen(self))


class _Factory:
    """v2_handle_factory producing fresh ``_FakeHandle``s (one per lookup)."""

    def __init__(self, events=None) -> None:
        self._events = events
        self.handles: list[_FakeHandle] = []
        self.call_count = 0

    def __call__(self, **kwargs):
        self.call_count += 1
        handle = _FakeHandle(self._events)
        self.handles.append(handle)
        return handle


class _StaleHandle:
    """First-iteration handle whose stream raises a stale-handle error."""

    def __init__(self) -> None:
        self.aio_calls: list[dict] = []
        self.run_plan_stream = SimpleNamespace(remote_gen=_StaleRemoteGen(self))


class _StaleRemoteGen:
    def __init__(self, handle) -> None:
        self._handle = handle

    def aio(self, payload, request_id="", **kwargs):
        self._handle.aio_calls.append({
            "payload": payload, "request_id": request_id, "kwargs": dict(kwargs),
        })
        return _StaleFirstStream()


class _StaleFirstStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise RuntimeError("Function handle not found: deployment no longer exists")

    async def aclose(self) -> None:
        pass


class _StaleRetryFactory:
    """First lookup yields a stale handle; later lookups yield good streams."""

    def __init__(self, good_events) -> None:
        self.good_events = good_events
        self.calls = 0
        self.handles: list = []

    def __call__(self, **kwargs):
        self.calls += 1
        handle = _StaleHandle() if self.calls == 1 else _FakeHandle(self.good_events)
        self.handles.append(handle)
        return handle


# ═══════════════════════════════════════════════════════════════════════
# Plan / trace helpers
# ═══════════════════════════════════════════════════════════════════════


def _make_plan(request_id: str = "req"):
    return ExecutionPlan.from_dict(_make_plan_dict(request_id))


def _make_plan_dict(request_id: str = "req"):
    return {
        "workflow": {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
        "workflow_hash": "h",
        "output_node_ids": ["1"],
        "input_images": {},
        "production_report": {},
        "request_metadata": {"prompt_id": request_id},
    }


def _trace(request_id: str) -> dict:
    return {
        "prompt_id": request_id,
        "metadata": {"request_origin_info": {"request_id": request_id}},
    }


def _make_transport(events=None, *, queue=None):
    return ModalTransport(
        v2_handle_factory=_Factory(events),
        control_queue_factory=(lambda workspace=None: queue) if queue is not None else None,
    )


# ═══════════════════════════════════════════════════════════════════════
# 1. Direct V2 transport
# ═══════════════════════════════════════════════════════════════════════


class TestDirectTransportCancellation(unittest.IsolatedAsyncioTestCase):
    async def test_no_cancel_stream_unchanged(self):
        events = [
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ]
        factory = _Factory(events)
        transport = ModalTransport(v2_handle_factory=factory)
        gen = transport.run_plan_stream(_make_plan("req-nc"), trace=_trace("req-nc"))
        ev = await gen.__anext__()
        self.assertEqual(ev["type"], "status")
        # No queue channel configured -> no control kwargs injected.
        self.assertEqual(factory.handles[0].aio_calls[0]["kwargs"], {})
        # While still running, cancellation without a channel is truthfully
        # unavailable (never fabricated).
        result = await transport.cancel_attempt("req-nc", reason="user_cancel")
        self.assertEqual(result.state, CANCEL_STATE_UNAVAILABLE)
        self.assertFalse(result.confirmed)
        ev2 = await gen.__anext__()
        self.assertEqual(ev2["type"], "result")
        with self.assertRaises(StopAsyncIteration):
            await gen.__anext__()
        await gen.aclose()

    async def test_control_queue_and_partition_propagate_to_remote_gen(self):
        queue = _FakeQueue()
        factory = _Factory([{"type": "result", "data": {"images": [], "outputs": {}}}])
        transport = ModalTransport(
            v2_handle_factory=factory,
            control_queue_factory=lambda workspace=None: queue,
        )
        seen = []
        async for ev in transport.run_plan_stream(_make_plan("req-prop"), trace=_trace("req-prop")):
            seen.append(ev)
        self.assertEqual([e["type"] for e in seen], ["result"])
        call = factory.handles[0].aio_calls[0]
        self.assertEqual(call["kwargs"], {"control_queue": queue, "control_partition": "req-prop"})
        # Queue resolved exactly once (lazily resolved + cached).
        self.assertEqual(factory.call_count, 1)

    async def test_control_kwargs_propagate_on_stale_retry(self):
        queue = _FakeQueue()
        factory = _StaleRetryFactory([{"type": "result", "data": {"images": [], "outputs": {}}}])
        transport = ModalTransport(
            v2_handle_factory=factory,
            control_queue_factory=lambda workspace=None: queue,
        )
        seen = []
        async for ev in transport.run_plan_stream(_make_plan("req-stale"), trace=_trace("req-stale")):
            seen.append(ev)
        self.assertEqual([e["type"] for e in seen], ["result"])
        self.assertEqual(len(factory.handles), 2, "stale handle must be re-resolved once")
        for handle in factory.handles:
            call = handle.aio_calls[0]
            self.assertEqual(call["kwargs"]["control_queue"], queue)
            self.assertEqual(call["kwargs"]["control_partition"], "req-stale")

    async def test_control_kwargs_on_persistent_to_direct_fallback(self):
        queue = _FakeQueue()
        factory = _Factory([{"type": "result", "data": {"images": [], "outputs": {}}}])
        transport = ModalTransport(
            v2_handle_factory=factory,
            control_queue_factory=lambda workspace=None: queue,
        )

        class _FailingClient:
            async def run_plan_stream(self, *args, **kwargs):
                raise PersistentHandleUnavailable("owner unreachable")

        transport.persistent_handle_client = _FailingClient()
        with mock.patch.object(ModalTransport, "_persistent_enabled", return_value=True):
            seen = []
            async for ev in transport.run_plan_stream(_make_plan("req-fb"), trace=_trace("req-fb")):
                seen.append(ev)
        self.assertEqual([e["type"] for e in seen], ["result"])
        self.assertEqual(len(factory.handles), 1)
        call = factory.handles[0].aio_calls[0]
        self.assertEqual(call["kwargs"], {"control_queue": queue, "control_partition": "req-fb"})

    async def test_cancel_put_is_not_confirmation(self):
        queue = _FakeQueue()
        events = [
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ]
        transport = _make_transport(events, queue=queue)
        gen = transport.run_plan_stream(_make_plan("req-put"), trace=_trace("req-put"))
        ev = await gen.__anext__()
        self.assertEqual(ev["type"], "status")
        result = await transport.cancel_attempt("req-put", reason="user_cancel")
        self.assertEqual(result.state, CANCEL_STATE_PENDING)
        self.assertFalse(result.confirmed)  # put success != confirmation
        self.assertEqual(
            queue.messages,
            [{"type": "cancel", "partition": "req-put", "reason": "user_cancel"}],
        )
        self.assertEqual(queue.put_partitions, ["req-put"])  # routed on partition
        ev2 = await gen.__anext__()
        self.assertEqual(ev2["type"], "result")
        with self.assertRaises(StopAsyncIteration):
            await gen.__anext__()
        await gen.aclose()

    async def test_duplicate_cancel_is_idempotent(self):
        queue = _FakeQueue()
        events = [
            {"type": "status", "data": {}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ]
        transport = _make_transport(events, queue=queue)
        gen = transport.run_plan_stream(_make_plan("req-dupe"), trace=_trace("req-dupe"))
        await gen.__anext__()
        r1 = await transport.cancel_attempt("req-dupe", reason="first")
        r2 = await transport.cancel_attempt("req-dupe", reason="second")
        self.assertEqual(r1.state, CANCEL_STATE_PENDING)
        self.assertEqual(r2.state, CANCEL_STATE_PENDING)  # idempotent reflection
        self.assertEqual(len(queue.messages), 1, "duplicate must not re-deliver")
        self.assertEqual(queue.messages[0]["reason"], "first")
        ev2 = await gen.__anext__()
        self.assertEqual(ev2["type"], "result")
        with self.assertRaises(StopAsyncIteration):
            await gen.__anext__()
        await gen.aclose()

    async def test_completion_before_cancel(self):
        transport = _make_transport(
            [{"type": "result", "data": {"images": [], "outputs": {}}}],
            queue=_FakeQueue(),
        )
        seen = []
        async for ev in transport.run_plan_stream(_make_plan("req-done"), trace=_trace("req-done")):
            seen.append(ev)
        result = await transport.cancel_attempt("req-done", reason="late_cancel")
        self.assertEqual(result.state, CANCEL_STATE_COMPLETED_BEFORE_CANCEL)
        self.assertFalse(result.confirmed)

    async def test_remote_cancelled_event_confirms_handle(self):
        queue = _FakeQueue()
        cancelled = {
            "type": "cancelled", "request_id": "req-conf",
            "reason": "user_cancel", "confirmed": True,
        }
        transport = _make_transport([cancelled], queue=queue)
        gen = transport.run_plan_stream(_make_plan("req-conf"), trace=_trace("req-conf"))
        # The cancelled confirmation is transport-internal protocol: it is
        # never surfaced as a stream event.
        with self.assertRaises(StopAsyncIteration):
            await gen.__anext__()
        await gen.aclose()
        handle = transport.get_cancellation_handle("req-conf")
        self.assertIsNotNone(handle)
        snapshot = handle.snapshot()
        self.assertEqual(snapshot.state, CANCEL_STATE_CONFIRMED)
        self.assertTrue(snapshot.confirmed)
        # A cancelled event must NOT trigger the normal result drain.
        self.assertNotIn("req-conf", transport._drain_request_ids)
        self.assertIsNone(get_persistence_status("req-conf"))

    async def test_put_then_remote_confirmation_flow(self):
        queue = _FakeQueue()
        events = [
            {"type": "status", "data": {}},
            {"type": "cancelled", "request_id": "req-cc", "reason": "user_cancel", "confirmed": True},
        ]
        transport = _make_transport(events, queue=queue)
        gen = transport.run_plan_stream(_make_plan("req-cc"), trace=_trace("req-cc"))
        await gen.__anext__()  # status
        r1 = await transport.cancel_attempt("req-cc", reason="user_cancel")
        self.assertEqual(r1.state, CANCEL_STATE_PENDING)
        self.assertFalse(r1.confirmed)
        # The remote observes the queue message, stops, and confirms on the
        # stream.
        with self.assertRaises(StopAsyncIteration):
            await gen.__anext__()
        await gen.aclose()
        handle = transport.get_cancellation_handle("req-cc")
        self.assertEqual(handle.snapshot().state, CANCEL_STATE_CONFIRMED)
        self.assertTrue(handle.snapshot().confirmed)

    async def test_channel_failure_returns_unavailable(self):
        class _BoomQueue:
            def put(self, message):
                raise RuntimeError("queue unavailable")

        transport = ModalTransport(
            v2_handle_factory=_Factory([
                {"type": "status", "data": {}},
                {"type": "result", "data": {"images": [], "outputs": {}}},
            ]),
            control_queue_factory=lambda workspace=None: _BoomQueue(),
        )
        gen = transport.run_plan_stream(_make_plan("req-boom"), trace=_trace("req-boom"))
        await gen.__anext__()
        result = await transport.cancel_attempt("req-boom", reason="user_cancel")
        self.assertEqual(result.state, CANCEL_STATE_UNAVAILABLE)
        self.assertFalse(result.confirmed)
        ev2 = await gen.__anext__()
        self.assertEqual(ev2["type"], "result")
        with self.assertRaises(StopAsyncIteration):
            await gen.__anext__()
        await gen.aclose()

    async def test_normal_result_keeps_persistence_drain(self):
        events = [
            {"type": "result", "data": {"images": [], "outputs": {}}},
            {"type": "persistence", "status": "committed", "commit_ms": 12.0, "detail": "ok", "skipped": False},
        ]
        transport = ModalTransport(v2_handle_factory=_Factory(events))
        gen = transport.run_plan_stream(_make_plan("req-drain"), trace=_trace("req-drain"))
        ev = await gen.__anext__()
        self.assertEqual(ev["type"], "result")
        await gen.aclose()
        record = await join_persistence_drain("req-drain", timeout=5.0)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "committed")
        self.assertIn("req-drain", transport._drain_request_ids)

    async def test_direct_put_routes_partition(self):
        # Finding 1: every direct cancel put must declare the routing
        # ``partition`` (never the queue's default partition).
        queue = _FakeQueue()
        events = [
            {"type": "status", "data": {}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ]
        transport = _make_transport(events, queue=queue)
        gen = transport.run_plan_stream(_make_plan("req-route"), trace=_trace("req-route"))
        await gen.__anext__()
        result = await transport.cancel_attempt("req-route", reason="user_cancel")
        self.assertEqual(result.state, CANCEL_STATE_PENDING)
        self.assertEqual(queue.put_partitions, ["req-route"])
        self.assertEqual(
            queue.messages,
            [{"type": "cancel", "partition": "req-route", "reason": "user_cancel"}],
        )
        await gen.aclose()

    async def test_empty_partition_rejected_by_direct_putter(self):
        # Finding 5: a cancel message without a partition must fail loudly
        # (never silently land on the default partition).
        queue = _FakeQueue()
        putter = ModalTransport._make_direct_cancel_putter(queue)
        with self.assertRaises(ValueError):
            await putter({"type": "cancel", "reason": "user_cancel"})
        self.assertEqual(queue.put_calls, 0)

    async def test_oversized_partition_rejected_by_direct_putter(self):
        # Finding 5: Modal partition keys are capped at 64 bytes.
        queue = _FakeQueue()
        putter = ModalTransport._make_direct_cancel_putter(queue)
        with self.assertRaises(ValueError):
            await putter({"type": "cancel", "partition": "p" * 65, "reason": "user_cancel"})
        self.assertEqual(queue.put_calls, 0)

    async def test_oversized_partition_maps_to_unavailable(self):
        # Finding 5: a partition beyond Modal's 64-byte limit surfaces a
        # truthful ``unavailable`` verdict — never a silent misdelivery.
        queue = _FakeQueue()
        handle = RemoteCancellationHandle(
            request_id="req-big",
            partition="p" * 65,
            putter=ModalTransport._make_direct_cancel_putter(queue),
        )
        result = await handle.cancel("user_cancel")
        self.assertEqual(result.state, CANCEL_STATE_UNAVAILABLE)
        self.assertFalse(result.confirmed)
        self.assertEqual(queue.messages, [])

    async def test_persistent_putter_validates_partition(self):
        # Finding 5: the persistent putter rejects an invalid partition before
        # ever calling the owner client.
        class _RecordingClient:
            def __init__(self):
                self.cancel_calls = 0

            async def cancel_attempt(self, **kwargs):
                self.cancel_calls += 1
                return {"delivered": True}

        client = _RecordingClient()
        transport = ModalTransport()
        transport.persistent_handle_client = client
        putter = transport._make_persistent_cancel_putter(
            request_id="req-p", persistent_key={}, workspace={},
        )
        with self.assertRaises(ValueError):
            await putter({"type": "cancel", "reason": "user_cancel"})
        self.assertEqual(client.cancel_calls, 0)

    async def test_observe_cancelled_event_requires_confirmed(self):
        # Finding 4: only a confirmed ``cancelled`` event is treated as the
        # cooperative-cancellation confirmation; unconfirmed/malformed frames
        # are ordinary events and must NOT skip the persistence drain.
        transport = ModalTransport(v2_handle_factory=_Factory([]))
        self.assertFalse(transport._observe_cancelled_event(
            {"type": "cancelled", "request_id": "req-x"}, request_id="req-x",
        ))
        self.assertFalse(transport._observe_cancelled_event(
            {"type": "cancelled", "request_id": "req-x", "confirmed": False},
            request_id="req-x",
        ))
        self.assertTrue(transport._observe_cancelled_event(
            {"type": "cancelled", "request_id": "req-x", "confirmed": True,
             "reason": "user_cancel"},
            request_id="req-x",
        ))

    async def test_unconfirmed_cancelled_event_keeps_persistence_drain(self):
        # Finding 4: an unconfirmed ``cancelled`` frame after the result must
        # NOT suppress the normal result -> shielded persistence drain.
        events = [
            {"type": "result", "data": {"images": [], "outputs": {}}},
            {"type": "cancelled", "request_id": "req-unconf", "confirmed": False,
             "reason": "stale"},
            {"type": "persistence", "status": "committed", "commit_ms": 3.0,
             "detail": "ok", "skipped": False},
        ]
        transport = ModalTransport(v2_handle_factory=_Factory(events))
        gen = transport.run_plan_stream(_make_plan("req-unconf"), trace=_trace("req-unconf"))
        ev = await gen.__anext__()
        self.assertEqual(ev["type"], "result")
        await gen.aclose()
        record = await join_persistence_drain("req-unconf", timeout=5.0)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "committed")
        self.assertIn("req-unconf", transport._drain_request_ids)


# ═══════════════════════════════════════════════════════════════════════
# 2. Adapter boundary (cancel message primitive + A/B partition isolation)
# ═══════════════════════════════════════════════════════════════════════


class TestAdapterBoundary(unittest.TestCase):
    def test_cancel_message_is_primitive_json(self):
        message = build_cancel_message("req-x", "user_cancel")
        self.assertEqual(message, {"type": "cancel", "partition": "req-x", "reason": "user_cancel"})
        # Primitive only: round-trips through plain JSON.
        self.assertEqual(json.loads(json.dumps(message)), message)

    def test_ab_partition_isolation_at_adapter_boundary(self):
        queue = _FakeQueue()
        putter = ModalTransport._make_direct_cancel_putter(queue)
        handle_a = RemoteCancellationHandle(request_id="req-a", partition="req-a", putter=putter)
        handle_b = RemoteCancellationHandle(request_id="req-b", partition="req-b", putter=putter)
        asyncio.run(handle_a.cancel("user_cancel"))
        asyncio.run(handle_b.cancel("shutdown"))
        # Each message is addressed to its own partition.
        self.assertEqual([m["partition"] for m in queue.messages], ["req-a", "req-b"])
        # Adapter boundary: a consumer filtering by control_partition sees
        # only its own messages (A never receives B's cancel and vice versa).
        a_msgs = [m for m in queue.messages if m["partition"] == "req-a"]
        b_msgs = [m for m in queue.messages if m["partition"] == "req-b"]
        self.assertEqual(a_msgs, [{"type": "cancel", "partition": "req-a", "reason": "user_cancel"}])
        self.assertEqual(b_msgs, [{"type": "cancel", "partition": "req-b", "reason": "shutdown"}])


# ═══════════════════════════════════════════════════════════════════════
# 3. Persistent IPC transport (in-process owner)
# ═══════════════════════════════════════════════════════════════════════


class TestPersistentIpcCancellation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = self._td.name
        self._clients: list[PersistentHandleClient] = []

    def tearDown(self):
        for client in self._clients:
            client.shutdown()
        self._td.cleanup()

    async def _start_owner(self, *, queue=None, resolve_queue=None, stream_events=None):
        """In-process owner server with a fake Modal handle + fake queue."""
        owner = owner_mod.LocalHandleOwner()
        fake = _FakeHandle(
            stream_events if stream_events is not None else [{"type": "result", "data": {"images": []}}]
        )

        async def _resolve_modal(key, workspace):
            return (fake, False)

        owner._resolve_modal = _resolve_modal
        if resolve_queue is not None:
            owner._resolve_control_queue = resolve_queue
        else:
            async def _default_resolve_queue(key, workspace, queue_name):
                return queue

            owner._resolve_control_queue = _default_resolve_queue
        server = await asyncio.start_server(
            lambda reader, writer: owner_mod._handle_connection(reader, writer, _AUTH, owner),
            host="127.0.0.1",
            port=0,
            limit=owner_mod.IPC_STREAM_LIMIT,
        )
        port = server.sockets[0].getsockname()[1]
        state_path = os.path.join(self.td, "owner.json")
        owner_mod._atomic_write_json(Path(state_path), {
            "schema_version": 1,
            "status": "ready",
            "pid": os.getpid(),
            "port": port,
            "auth_token": _AUTH,
            "started_at": 0.0,
        })
        return server, fake, state_path, port, owner

    def _client(self, state_path) -> PersistentHandleClient:
        client = PersistentHandleClient(
            state_path=state_path, auth_token=_AUTH, repo_root=str(REPO_ROOT),
        )
        self._clients.append(client)
        return client

    async def test_owner_forwards_hydrated_queue_to_remote_generator(self):
        queue = _FakeQueue()
        server, fake, state_path, port, owner = await self._start_owner(queue=queue)
        try:
            client = self._client(state_path)
            await client._ensure_owner()
            proxy = await client.run_plan_stream(
                key={}, workspace={}, payload=_make_plan_dict("req-ipc-1"),
                request_id="req-ipc-1",
                control_queue_name="comfymodal-v2-control",
                control_partition="req-ipc-1",
            )
            events = [ev async for ev in proxy]
            await proxy.aclose()
        finally:
            server.close()
            await server.wait_closed()
        self.assertEqual(len(events), 1)
        call = fake.aio_calls[-1]
        self.assertEqual(call["kwargs"]["control_queue"], queue)
        self.assertEqual(call["kwargs"]["control_partition"], "req-ipc-1")

    async def test_cancel_attempt_puts_primitive_cancel_over_own_channel(self):
        queue = _FakeQueue()
        server, fake, state_path, port, owner = await self._start_owner(queue=queue)
        try:
            client = self._client(state_path)
            await client._ensure_owner()
            result = await client.cancel_attempt(
                key={}, workspace={},
                control_queue_name="comfymodal-v2-control",
                control_partition="req-ipc-2",
                reason="user_cancel",
            )
        finally:
            server.close()
            await server.wait_closed()
        self.assertIs(result.get("delivered"), True)
        self.assertEqual(result.get("partition"), "req-ipc-2")
        # PUT success only — the message is primitive and addressed to the
        # partition; confirmation is a separate stream signal.
        self.assertEqual(
            queue.messages,
            [{"type": "cancel", "partition": "req-ipc-2", "reason": "user_cancel"}],
        )
        # The owner's put is routed on the partition (never the default one).
        self.assertEqual(queue.put_partitions, ["req-ipc-2"])

    async def test_owner_queue_resolution_failure_is_truthful(self):
        async def _boom(key, workspace, queue_name):
            raise RuntimeError("queue boom")

        server, fake, state_path, port, owner = await self._start_owner(
            queue=_FakeQueue(), resolve_queue=_boom,
        )
        try:
            client = self._client(state_path)
            await client._ensure_owner()
            with self.assertRaises(PersistentHandleError) as ctx:
                await client.cancel_attempt(
                    key={}, workspace={},
                    control_queue_name="comfymodal-v2-control",
                    control_partition="req-ipc-3",
                    reason="user_cancel",
                )
            self.assertEqual(ctx.exception.frame.get("type"), "queue_resolve_failed")
        finally:
            server.close()
            await server.wait_closed()

    async def test_owner_run_stream_survives_queue_resolution_failure(self):
        async def _boom(key, workspace, queue_name):
            raise RuntimeError("queue boom")

        server, fake, state_path, port, owner = await self._start_owner(
            queue=_FakeQueue(), resolve_queue=_boom,
        )
        try:
            client = self._client(state_path)
            await client._ensure_owner()
            proxy = await client.run_plan_stream(
                key={}, workspace={}, payload=_make_plan_dict("req-ipc-3b"),
                request_id="req-ipc-3b",
                control_queue_name="comfymodal-v2-control",
                control_partition="req-ipc-3b",
            )
            events = [ev async for ev in proxy]
            await proxy.aclose()
        finally:
            server.close()
            await server.wait_closed()
        # Queue plumbing failure never fails the stream; the remote just runs
        # without cooperative cancellation (no control kwargs forwarded).
        self.assertEqual(len(events), 1)
        self.assertEqual(fake.aio_calls[-1]["kwargs"], {})

    async def test_persistent_transport_cancel_confirms_via_stream(self):
        queue = _FakeQueue()
        events = [
            {"type": "status", "data": {"phase": "restore"}},
            {"type": "cancelled", "request_id": "req-ipc-4", "reason": "user_cancel", "confirmed": True},
        ]
        server, fake, state_path, port, owner = await self._start_owner(queue=queue, stream_events=events)
        try:
            client = self._client(state_path)
            transport = ModalTransport()
            transport.persistent_handle_client = client
            with mock.patch.object(ModalTransport, "_persistent_enabled", return_value=True):
                gen = transport.run_plan_stream(
                    _make_plan("req-ipc-4"), trace=_trace("req-ipc-4"),
                    workspace={"id": "w1", "token_id": "t1", "token_secret": "s1"},
                )
                ev = await gen.__anext__()
                self.assertEqual(ev["type"], "status")
                result = await transport.cancel_attempt("req-ipc-4", reason="user_cancel")
                self.assertEqual(result.state, CANCEL_STATE_PENDING)
                self.assertFalse(result.confirmed)
                with self.assertRaises(StopAsyncIteration):
                    await gen.__anext__()
                await gen.aclose()
            handle = transport.get_cancellation_handle("req-ipc-4")
            self.assertIsNotNone(handle)
            self.assertEqual(handle.snapshot().state, CANCEL_STATE_CONFIRMED)
            self.assertTrue(handle.snapshot().confirmed)
            # The owner put the primitive message (put success) and the remote
            # confirmation travelled on the stream — not the same channel.
            self.assertEqual(
                queue.messages,
                [{"type": "cancel", "partition": "req-ipc-4", "reason": "user_cancel"}],
            )
        finally:
            server.close()
            await server.wait_closed()

    async def test_persistent_transport_channel_failure_unavailable(self):
        async def _boom(key, workspace, queue_name):
            raise RuntimeError("queue boom")

        server, fake, state_path, port, owner = await self._start_owner(
            queue=_FakeQueue(), resolve_queue=_boom,
            stream_events=[
                {"type": "status", "data": {}},
                {"type": "result", "data": {"images": [], "outputs": {}}},
            ],
        )
        try:
            client = self._client(state_path)
            transport = ModalTransport()
            transport.persistent_handle_client = client
            with mock.patch.object(ModalTransport, "_persistent_enabled", return_value=True):
                gen = transport.run_plan_stream(
                    _make_plan("req-ipc-5"), trace=_trace("req-ipc-5"),
                    workspace={"id": "w1", "token_id": "t1", "token_secret": "s1"},
                )
                await gen.__anext__()
                result = await transport.cancel_attempt("req-ipc-5", reason="user_cancel")
                self.assertEqual(result.state, CANCEL_STATE_UNAVAILABLE)
                self.assertFalse(result.confirmed)
                ev2 = await gen.__anext__()
                self.assertEqual(ev2["type"], "result")
                with self.assertRaises(StopAsyncIteration):
                    await gen.__anext__()
                await gen.aclose()
        finally:
            server.close()
            await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
