"""Focused tests for ModalTransport.publish_restore_plan remote calling.

Covers the CURRENT direct-remote path (the older ``spawn.aio / get.aio``
`_call_publish_with_spawn` helper was removed):

- Class-handle path invokes ``handle.publish_restore_plan.remote.aio(...)``.
- Direct Function path resolves the handle via the cache and invokes
  ``remote.aio``.
- Exceptions raised by the remote call propagate unchanged (no cancel /
  no wrapping — the transport has no post-dispatch timeout/cancel machinery
  for the direct path).
- A non-remote callable ``publish_restore_plan`` is invoked via
  ``asyncio.to_thread``.
- Persistent-path failure classification (``_persistent_failure_is_local``)
  and the single-invocation guarantee are preserved.

No remote Modal calls are made — all Modal SDK interactions are faked.
"""

from __future__ import annotations

import asyncio
import os
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from comfymodal_runtime.local_handle_client import (
    PersistentHandleError,
    PersistentHandleUnavailable,
)
from comfymodal_runtime.modal_transport import (
    HandleCache,
    HandleCacheKey,
    ModalTransport,
    TransportError,
)


# ── Fake Modal remote object ──────────────────────────────────────────────


class _FakeRemote:
    """Simulates ``publish_restore_plan.remote.aio(...)``.

    *result* — return value; *error* — exception raised by aio.
    """

    def __init__(self, result: object = None, error: BaseException | None = None) -> None:
        self._result = result
        self._error = error
        self.calls: list[tuple[object, dict]] = []

    async def aio(self, payload: object, snapshot_seed: object = None) -> object:
        self.calls.append((payload, {"snapshot_seed": snapshot_seed}))
        if self._error is not None:
            raise self._error
        return self._result


def _remote_handle(remote: _FakeRemote) -> Any:
    """A handle whose ``publish_restore_plan`` attribute exposes
    ``remote.aio`` (the shape the current direct path expects)."""
    return MagicMock(publish_restore_plan=MagicMock(remote=remote))


def _callable_handle(fn: Any) -> Any:
    """A handle whose ``publish_restore_plan`` is a plain callable (invoked
    via ``asyncio.to_thread`` by the transport fallback)."""
    return MagicMock(publish_restore_plan=fn)


# ── Shared payload fixture ────────────────────────────────────────────────

_SAMPLE_PAYLOAD: dict[str, object] = {"workflow": {"1": {"class_type": "KSampler"}}}


# ── Tests: class-handle path using remote.aio ──────────────────────────────


class TestPublishRestorePlanClassHandleSpawn(unittest.TestCase):
    """Class-handle (v2_handle_factory) path invokes remote.aio."""

    def _transport(self, remote: _FakeRemote) -> ModalTransport:
        def factory(**kwargs):
            return _remote_handle(remote)
        return ModalTransport(v2_handle_factory=factory, handle_cache=HandleCache())

    def test_success_path_uses_remote_aio(self):
        """Successful call uses remote.aio and returns the result."""
        remote = _FakeRemote(result={"status": "published"})
        transport = self._transport(remote)
        result = asyncio.run(
            transport.publish_restore_plan(_SAMPLE_PAYLOAD, workspace={"id": "ws-1"}),
        )
        self.assertEqual(result, {"status": "published"})
        self.assertEqual(len(remote.calls), 1)
        self.assertEqual(remote.calls[0][0], _SAMPLE_PAYLOAD)

    def test_seed_forwarded_through_remote_aio(self):
        """snapshot_seed is passed through to remote.aio unchanged."""
        remote = _FakeRemote(result={"status": "published"})
        transport = self._transport(remote)
        seed = {"seed_source": "invocation_plan", "seed": {"schema_version": 2}}
        result = asyncio.run(
            transport.publish_restore_plan(
                _SAMPLE_PAYLOAD, workspace={"id": "ws-1"}, snapshot_seed=seed,
            ),
        )
        self.assertEqual(result, {"status": "published"})
        self.assertEqual(remote.calls[0][1], {"snapshot_seed": seed})

    def test_timeout_propagates_without_cancel(self):
        """TimeoutError raised by the remote call propagates unchanged (the
        direct path has no cancel machinery)."""
        remote = _FakeRemote(error=asyncio.TimeoutError())
        transport = self._transport(remote)
        with self.assertRaises(asyncio.TimeoutError):
            asyncio.run(
                transport.publish_restore_plan(_SAMPLE_PAYLOAD, workspace={"id": "ws-1"}),
            )

    def test_cancelled_error_propagates(self):
        """CancelledError raised by the remote call propagates unchanged."""
        remote = _FakeRemote(error=asyncio.CancelledError())
        transport = self._transport(remote)
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(
                transport.publish_restore_plan(_SAMPLE_PAYLOAD, workspace={"id": "ws-1"}),
            )

    def test_other_exception_propagates(self):
        """Non-timeout/cancellation exceptions propagate unchanged."""
        remote = _FakeRemote(error=ValueError("disk full"))
        transport = self._transport(remote)
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(
                transport.publish_restore_plan(_SAMPLE_PAYLOAD, workspace={"id": "ws-1"}),
            )
        self.assertIn("disk full", str(ctx.exception))

    def test_plain_callable_invoked_via_to_thread(self):
        """A publish_restore_plan that is a plain callable (no remote.aio) is
        invoked via asyncio.to_thread."""
        calls: list[tuple[object, dict]] = []

        def fn(payload, snapshot_seed=None):
            calls.append((payload, {"snapshot_seed": snapshot_seed}))
            return {"status": "published"}

        transport = ModalTransport(
            v2_handle_factory=lambda **kwargs: _callable_handle(fn),
            handle_cache=HandleCache(),
        )
        result = asyncio.run(
            transport.publish_restore_plan(_SAMPLE_PAYLOAD, workspace={"id": "ws-1"}),
        )
        self.assertEqual(result, {"status": "published"})
        self.assertEqual(len(calls), 1)


# ── Tests: direct Function path using remote.aio ────────────────────────────


def _run_direct_path(remote: _FakeRemote) -> object:
    """Run publish_restore_plan through the direct Function path.

    Pre-populates the handle cache with a handle whose publish_restore_plan
    exposes remote.aio, and sets env so the production key matches."""
    transport = ModalTransport(v2_handle_factory=None, handle_cache=HandleCache())
    # Build the EXACT production cache key via the transport itself so the
    # pre-populated entry is always found (GPU canonicalization, token_id,
    # cloud, deployment_identity, factory_identity all participate).
    key = transport._cache_key(
        workspace={"id": "ws-1", "token_id": "tid", "token_secret": "ts"},
        app_name="publisher-test-app",
        class_name="ModalRuntimeEntrypointV2",
        environment=transport._resolve_environment(),
        cloud=transport._resolve_v2_cloud(transport._canonicalize_gpu_config(None)),
        gpu=transport._canonicalize_gpu_config(None),
        deployment_identity="",
    )
    transport.handle_cache.put(key, _remote_handle(remote))
    with patch.dict(os.environ, {"COMFYMODAL_V2_APP_NAME": "publisher-test-app"}, clear=False):
        with patch("comfymodal_runtime.modal_transport._modal", spec=[]):
            return asyncio.run(
                transport.publish_restore_plan(
                    _SAMPLE_PAYLOAD,
                    workspace={"id": "ws-1", "token_id": "tid", "token_secret": "ts"},
                ),
            )


class TestPublishRestorePlanDirectFnSpawn(unittest.TestCase):
    """Direct Function handle path invokes remote.aio."""

    def test_success_path_uses_remote_aio(self):
        """Direct Function path uses remote.aio and returns the result."""
        remote = _FakeRemote(result={"status": "published"})
        result = _run_direct_path(remote)
        self.assertEqual(result, {"status": "published"})
        self.assertEqual(len(remote.calls), 1)

    def test_timeout_propagates(self):
        """TimeoutError propagates unchanged from the direct path."""
        remote = _FakeRemote(error=asyncio.TimeoutError())
        with self.assertRaises(asyncio.TimeoutError):
            _run_direct_path(remote)

    def test_cancelled_error_propagates(self):
        """CancelledError propagates unchanged from the direct path."""
        remote = _FakeRemote(error=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            _run_direct_path(remote)

    def test_other_exception_propagates(self):
        """Non-timeout exceptions propagate unchanged from the direct path."""
        remote = _FakeRemote(error=ValueError("bad payload"))
        with self.assertRaises(ValueError):
            _run_direct_path(remote)

# ── Persistent-path failure classification (single-publish guarantee) ──────


class _PersistentFailClient:
    """Persistent client that raises a configurable failure."""

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    async def publish_restore_plan(self, *args, **kwargs):
        raise self.exc


class TestPersistentFailureClassification(unittest.TestCase):
    """``_persistent_failure_is_local`` must be True ONLY for pre-op
    failures (owner unreachable / handle resolution) — never for post-op
    failures where the remote publish may have already executed."""

    def test_pre_op_unavailable_is_local(self):
        self.assertTrue(ModalTransport._persistent_failure_is_local(
            PersistentHandleUnavailable("cannot connect to local handle owner"),
        ))

    def test_pre_op_resolve_failed_is_local(self):
        self.assertTrue(ModalTransport._persistent_failure_is_local(
            PersistentHandleError("resolve failed", frame={"type": "resolve_failed"}),
        ))

    def test_post_op_result_unavailable_is_not_local(self):
        """Timeout / EOF / read failure after the op was delivered must NOT
        fall back — the remote publish may have already run."""
        self.assertFalse(ModalTransport._persistent_failure_is_local(
            PersistentHandleError("timed out", frame={"type": "result_unavailable"}),
        ))

    def test_empty_frame_type_is_not_local(self):
        """Unclassified failures are post-op by default: never fall back."""
        self.assertFalse(ModalTransport._persistent_failure_is_local(
            PersistentHandleError("boom", frame={}),
        ))

    def test_nonlocal_publish_failed_is_not_local(self):
        self.assertFalse(ModalTransport._persistent_failure_is_local(
            PersistentHandleError("publish failed", frame={"type": "publish_failed"}),
        ))


class TestPersistentPublishSingleInvocation(unittest.TestCase):
    """One transport publish call must never invoke the remote method twice:
    post-op persistent failures raise instead of falling back to a direct
    re-publish; pre-op failures fall back to exactly one direct call."""

    def _transport(self, persistent_exc: BaseException | None, direct_calls: list) -> ModalTransport:
        from unittest.mock import patch

        class _Remote:
            async def aio(self, *args, **kwargs):
                direct_calls.append(1)
                return {"status": "published", "generation": 9}

        handle = type("H", (), {
            "publish_restore_plan": type("F", (), {"remote": _Remote()})(),
        })()
        transport = ModalTransport(
            v2_handle_factory=None,
            handle_cache=HandleCache(),
            persistent_handle_client=(
                None if persistent_exc is None else _PersistentFailClient(persistent_exc)
            ),
        )
        # Persistent mode requires v2_handle_factory=None; the direct fallback
        # resolves via _v2_handle — stub it to return the fake handle.  The
        # patcher is stored on SELF (not the transport) so tearDown always
        # restores it and the patch can never leak into later tests.
        patcher = patch.object(ModalTransport, "_v2_handle", lambda self, **kw: handle)
        patcher.start()
        self._test_patcher = patcher
        return transport

    def tearDown(self):
        patcher = getattr(self, "_test_patcher", None)
        if patcher is not None:
            patcher.stop()
            self._test_patcher = None

    def test_post_op_failure_raises_without_direct_call(self):
        import os
        direct_calls: list[int] = []
        transport = self._transport(
            PersistentHandleError("timed out", frame={"type": "result_unavailable"}),
            direct_calls,
        )
        with patch.dict(os.environ, {"COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1"}, clear=False):
            with self.assertRaises(PersistentHandleError):
                asyncio.run(transport.publish_restore_plan(
                    {"workflow_hash": "wf"}, workspace={"id": "ws-1"},
                ))
        self.assertEqual(len(direct_calls), 0,
                         "post-op failure must NOT re-publish through the direct path")

    def test_pre_op_failure_falls_back_to_exactly_one_direct_call(self):
        import os
        direct_calls: list[int] = []
        transport = self._transport(
            PersistentHandleUnavailable("cannot connect to local handle owner"),
            direct_calls,
        )
        with patch.dict(os.environ, {"COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1"}, clear=False):
            result = asyncio.run(transport.publish_restore_plan(
                {"workflow_hash": "wf"}, workspace={"id": "ws-1"},
            ))
        self.assertEqual(result["generation"], 9)
        self.assertEqual(len(direct_calls), 1,
                         "pre-op failure falls back to exactly ONE direct call")
