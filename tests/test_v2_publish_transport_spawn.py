"""Focused tests for ModalTransport.publish_restore_plan spawn-based calling.

Verifies:
- Class-handle path uses _call_publish_with_spawn (spawn.aio / get.aio).
- Direct Function path uses _call_publish_with_spawn.
- On get.aio TimeoutError: cancels the container and raises TransportError.
- On get.aio CancelledError: cancels the container and re-raises.
- Normal exceptions are wrapped in TransportError without cancellation.
- No remote Modal calls are made — all Modal SDK interactions are faked.

The tests construct fake Modal handles that expose spawn.aio → call objects
with configurable get.aio behavior.
"""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import MagicMock, patch

from comfymodal_runtime.modal_transport import (
    HandleCache,
    HandleCacheKey,
    ModalTransport,
    TransportError,
)


# ── Fake Modal call object ────────────────────────────────────────────────


class _FakeGet:
    """Simulates call.get.aio(...)."""

    def __init__(self, call: FakeModalCall) -> None:
        self._call = call

    async def aio(self, timeout: float = 180) -> object:
        if self._call._get_error is not None:
            raise self._call._get_error
        return self._call._result


class _FakeCancel:
    """Simulates call.cancel.aio(...)."""

    def __init__(self, call: FakeModalCall) -> None:
        self._call = call

    async def aio(self, terminate_containers: bool = False) -> None:
        self._call.cancel_called = True
        self._call.cancel_terminate_containers = terminate_containers


class FakeModalCall:
    """Simulates a Modal FunctionCall with configurable get.aio behavior.

    *result* — return value when get.aio succeeds.
    *get_error* — exception raised by get.aio.
    """

    def __init__(
        self,
        result: object = None,
        get_error: BaseException | None = None,
    ) -> None:
        self._result = result
        self._get_error = get_error
        self.cancel_called: bool = False
        self.cancel_terminate_containers: bool | None = None
        self.get = _FakeGet(self)
        self.cancel = _FakeCancel(self)


class _FakeSpawn:
    """Simulates target.spawn."""

    def __init__(self, owner: FakeSpawnable) -> None:
        self._owner = owner

    async def aio(self, payload: object) -> FakeModalCall:
        self._owner.spawned_payload = payload
        return self._owner._call


class FakeSpawnable:
    """Wraps a FakeModalCall; exposes spawn.aio to simulate a Modal handle."""

    def __init__(self, call: FakeModalCall) -> None:
        self._call = call
        self.spawned_payload: object = None
        self.spawn = _FakeSpawn(self)


# ── Transport helper constructors ─────────────────────────────────────────


def _transport_with_class_handle(call: FakeModalCall) -> ModalTransport:
    """Return a ModalTransport whose v2_handle_factory returns a
    pseudo-handle whose ``publish_restore_plan`` attribute is a
    FakeSpawnable wrapping *call*."""
    def factory(**kwargs):
        return MagicMock(
            publish_restore_plan=FakeSpawnable(call),
        )
    return ModalTransport(v2_handle_factory=factory, handle_cache=HandleCache())


# ── Shared payload fixture ────────────────────────────────────────────────

_SAMPLE_PAYLOAD: dict[str, object] = {"workflow": {"1": {"class_type": "KSampler"}}}


# ── Tests: class-handle path using spawn ──────────────────────────────────


class TestPublishRestorePlanClassHandleSpawn(unittest.TestCase):
    """Class-handle (v2_handle_factory) path uses spawn.aio."""

    def test_success_path_uses_spawn(self):
        """Successful call uses spawn.aio/get.aio and returns the result."""
        call = FakeModalCall(result={"status": "published"})
        transport = _transport_with_class_handle(call)
        result = asyncio.run(
            transport.publish_restore_plan(_SAMPLE_PAYLOAD, workspace={"id": "ws-1"}),
        )
        self.assertEqual(result, {"status": "published"})

    def test_get_timeout_cancels_and_raises_transport_error(self):
        """get.aio TimeoutError causes cancel.aio and TransportError."""
        call = FakeModalCall(get_error=asyncio.TimeoutError())
        transport = _transport_with_class_handle(call)
        with self.assertRaises(TransportError) as ctx:
            asyncio.run(
                transport.publish_restore_plan(_SAMPLE_PAYLOAD, workspace={"id": "ws-1"}),
            )
        self.assertIn("timed out", str(ctx.exception))
        self.assertTrue(call.cancel_called)
        self.assertTrue(call.cancel_terminate_containers)

    def test_cancelled_error_cancels_and_re_raises(self):
        """get.aio CancelledError causes cancel.aio and re-raises CancelledError."""
        call = FakeModalCall(get_error=asyncio.CancelledError())
        transport = _transport_with_class_handle(call)
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(
                transport.publish_restore_plan(_SAMPLE_PAYLOAD, workspace={"id": "ws-1"}),
            )
        self.assertTrue(call.cancel_called)
        self.assertTrue(call.cancel_terminate_containers)

    def test_other_exception_wrapped_no_cancel(self):
        """Non-timeout/cancellation exceptions are wrapped in TransportError
        without calling cancel."""
        call = FakeModalCall(get_error=ValueError("disk full"))
        transport = _transport_with_class_handle(call)
        with self.assertRaises(TransportError) as ctx:
            asyncio.run(
                transport.publish_restore_plan(_SAMPLE_PAYLOAD, workspace={"id": "ws-1"}),
            )
        self.assertIn("publication failed", str(ctx.exception))
        self.assertFalse(call.cancel_called)


# ── Tests: direct Function path using spawn ────────────────────────────────


def _run_direct_path(call: FakeModalCall, payload: object) -> object:
    """Run publish_restore_plan through the direct Function path.

    Pre-populates the handle cache with a FakeSpawnable and sets env
    variables so the production key matches.  Patches _modal so the
    Modal-not-available guard passes.
    """
    transport = ModalTransport(v2_handle_factory=None, handle_cache=HandleCache())
    # Pre-populate cache with a key that matches the production lookup.
    key = HandleCacheKey("ws-1", "publisher-test-app", "publish_restore_plan_remote", environment="")
    transport.handle_cache.put(key, FakeSpawnable(call))
    with patch.dict(os.environ, {"COMFYMODAL_V2_APP_NAME": "publisher-test-app"}, clear=False):
        with patch("comfymodal_runtime.modal_transport._modal", spec=[]):
            return asyncio.run(
                transport.publish_restore_plan(
                    payload,
                    workspace={"id": "ws-1", "token_id": "tid", "token_secret": "ts"},
                ),
            )


def _run_direct_path_exception(
    call: FakeModalCall, payload: object,
) -> BaseException | None:
    """Run publish_restore_plan through the direct Function path and
    return the raised exception.  Catches BaseException to handle
    asyncio.CancelledError (a BaseException subclass)."""
    with patch.dict(os.environ, {"COMFYMODAL_V2_APP_NAME": "publisher-test-app"}, clear=False):
        with patch("comfymodal_runtime.modal_transport._modal", spec=[]):
            transport = ModalTransport(v2_handle_factory=None, handle_cache=HandleCache())
            key = HandleCacheKey("ws-1", "publisher-test-app", "publish_restore_plan_remote", environment="")
            transport.handle_cache.put(key, FakeSpawnable(call))
            try:
                asyncio.run(
                    transport.publish_restore_plan(
                        payload,
                        workspace={"id": "ws-1", "token_id": "tid", "token_secret": "ts"},
                    ),
                )
                return None
            except BaseException as exc:
                return exc


class TestPublishRestorePlanDirectFnSpawn(unittest.TestCase):
    """Direct Function handle path uses spawn.aio."""

    def test_success_path_uses_spawn(self):
        """Direct Function path uses spawn.aio/get.aio and returns result."""
        call = FakeModalCall(result={"status": "published"})
        result = _run_direct_path(call, _SAMPLE_PAYLOAD)
        self.assertEqual(result, {"status": "published"})

    def test_get_timeout_cancels_and_raises_transport_error(self):
        """get.aio TimeoutError -> cancel.aio + TransportError."""
        call = FakeModalCall(get_error=asyncio.TimeoutError())
        exc = _run_direct_path_exception(call, _SAMPLE_PAYLOAD)
        self.assertIsInstance(exc, TransportError)
        self.assertIn("timed out", str(exc))
        self.assertTrue(call.cancel_called)
        self.assertTrue(call.cancel_terminate_containers)

    def test_cancelled_error_cancels_and_re_raises(self):
        """CancelledError -> cancel.aio + re-raise."""
        call = FakeModalCall(get_error=asyncio.CancelledError())
        exc = _run_direct_path_exception(call, _SAMPLE_PAYLOAD)
        self.assertIsInstance(exc, asyncio.CancelledError)
        self.assertTrue(call.cancel_called)
        self.assertTrue(call.cancel_terminate_containers)

    def test_other_exception_wrapped_no_cancel(self):
        """Non-timeout exceptions wrap in TransportError, no cancel."""
        call = FakeModalCall(get_error=ValueError("bad payload"))
        exc = _run_direct_path_exception(call, _SAMPLE_PAYLOAD)
        self.assertIsInstance(exc, TransportError)
        self.assertIn("publication failed", str(exc))
        self.assertFalse(call.cancel_called)


# ── Shared helper unit test ────────────────────────────────────────────────


class TestCallPublishWithSpawnHelper(unittest.TestCase):
    """Direct unit test of ModalTransport._call_publish_with_spawn."""

    def test_helper_returns_result_on_success(self):
        transport = ModalTransport()
        call = FakeModalCall(result={"ok": True})
        spawnable = FakeSpawnable(call)
        result = asyncio.run(
            transport._call_publish_with_spawn(spawnable, {"key": "val"}),
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(spawnable.spawned_payload, {"key": "val"})

    def test_helper_timeout_cancels(self):
        transport = ModalTransport()
        call = FakeModalCall(get_error=asyncio.TimeoutError())
        spawnable = FakeSpawnable(call)
        with self.assertRaises(TransportError) as ctx:
            asyncio.run(
                transport._call_publish_with_spawn(spawnable, {}),
            )
        self.assertIn("timed out", str(ctx.exception))
        self.assertTrue(call.cancel_called)

    def test_helper_cancelled_re_raises(self):
        transport = ModalTransport()
        call = FakeModalCall(get_error=asyncio.CancelledError())
        spawnable = FakeSpawnable(call)
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(
                transport._call_publish_with_spawn(spawnable, {}),
            )
        self.assertTrue(call.cancel_called)

    def test_helper_other_error_wraps_no_cancel(self):
        transport = ModalTransport()
        call = FakeModalCall(get_error=RuntimeError("oops"))
        spawnable = FakeSpawnable(call)
        with self.assertRaises(TransportError):
            asyncio.run(
                transport._call_publish_with_spawn(spawnable, {}),
            )
        self.assertFalse(call.cancel_called)
