"""Tests for the Variant A deferred-commit persistence contract.

Variant A moves the remote asset Volume commit AFTER the result event so the
client receives the result first.  This suite covers:

1.  Drain end-to-end (core): a caller that breaks on the result event hands
    the leftover remote iterator to a shielded background drain
    (``ModalTransport._drain_task``); the drain consumes the terminal
    ``persistence`` event, records it into the module registry keyed by
    prompt_id, and best-effort acloses the iterator exactly once.
2.  Drain failure recording: a ``persistence`` event with ``status=failed``
    is recorded with its detail preserved.
3.  Natural exhaustion skips the drain: a caller that consumes the whole
    stream takes the ``_stream_exhausted`` path (iterator aclosed, no drain
    task); the registry is populated only when a consumer records the
    persistence event (e.g. ``modal_client.run_prompt_stream``).
4.  ``record_persistence_status`` normalization (type coercion, skipped bool,
    non-persistence / empty-status rejection, overwrite semantics).
5.  ``get_persistence_status`` returns a defensive copy.
6.  ``_finalize_deferred_commit`` (modal_app.py): idempotent finalizer for
    the stashed commit task — ok / failed / cache-hit / not-pending, plus
    teardown-diagnostics emits.
7.  Asset-route decision logic (HTTP level): bounded retry that consults the
    persistence registry — definitive "failed" -> 503, exhaustion -> 404,
    other errors -> 502.

All tests are offline: every Modal SDK interaction is faked, the transport
uses ``prompt_stream_fn`` fakes, and the asset route is invoked directly via
the stub-server pattern from ``test_routes_registered.py``.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
from comfymodal_runtime.modal_transport import (
    ModalTransport,
    _PERSISTENCE_STATUS_BY_PROMPT,
    get_persistence_status,
    record_persistence_status,
)

try:
    from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint  # noqa: F401
except Exception:  # pragma: no cover - defensive: modal_app must import
    ModalRuntimeEntrypoint = None

from tests.test_routes_registered import (
    _MockRequest,
    _build_init_with_stub,
    _handler_for,
    _run,
)


# ── Shared fakes ────────────────────────────────────────────────────────────


class _TrackingIterator:
    """Async iterator that records explicit aclose() calls like Modal's
    ``remote_gen.aio()`` object."""

    def __init__(self, events: list[dict]) -> None:
        self._events = list(events)
        self.aclose_calls = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)

    async def aclose(self) -> None:
        self.aclose_calls += 1


def _reset_persistence_registry() -> None:
    _PERSISTENCE_STATUS_BY_PROMPT.clear()


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        workflow={"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
        execution_options=ExecutionOptions(production_enabled=False),
        request_metadata={},
    )


class _FakeDiag:
    """Lightweight ``TeardownDiagnostics`` stand-in that records emits."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def emit(self, name: str, **kwargs: Any) -> None:
        self.calls.append({"event": name, **kwargs})


# ═════════════════════════════════════════════════════════════════════════
# Contract items 4 + 5 — registry normalization and copy semantics
# ═════════════════════════════════════════════════════════════════════════


class TestPersistenceRegistry(unittest.TestCase):
    """``record_persistence_status`` normalization + ``get_persistence_status``
    copy semantics (contract items 4 & 5)."""

    def setUp(self):
        _reset_persistence_registry()

    def test_valid_event_is_recorded_with_coercion(self):
        """commit_ms coerced to float, skipped to bool, detail to str."""
        event = {
            "type": "persistence",
            "status": "ok",
            "commit_ms": "123.4",
            "detail": "committed",
            "skipped": 1,
        }
        record = record_persistence_status("pid-coerce", event)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "ok")
        self.assertEqual(record["commit_ms"], 123.4)
        self.assertEqual(record["detail"], "committed")
        self.assertIs(record["skipped"], True)
        # Registry copy is equal and typed the same.
        stored = get_persistence_status("pid-coerce")
        self.assertEqual(stored["commit_ms"], 123.4)
        self.assertIs(stored["skipped"], True)

    def test_valid_event_returns_registry_record(self):
        """The returned record equals what get_persistence_status returns."""
        event = {
            "type": "persistence",
            "status": "ok",
            "commit_ms": 12.5,
            "detail": "",
            "skipped": False,
        }
        record = record_persistence_status("pid-return", event)
        self.assertEqual(record, get_persistence_status("pid-return"))

    def test_non_persistence_event_returns_none_and_no_record(self):
        """Any event that is not a persistence event is ignored."""
        result = record_persistence_status("pid-x", {"type": "result", "data": {}})
        self.assertIsNone(result)
        self.assertIsNone(get_persistence_status("pid-x"))

    def test_empty_status_returns_none_and_no_record(self):
        """A persistence event with no status is ignored."""
        event = {"type": "persistence", "commit_ms": 1.0}
        self.assertIsNone(record_persistence_status("pid-empty", event))
        self.assertIsNone(get_persistence_status("pid-empty"))

    def test_non_dict_event_returns_none(self):
        self.assertIsNone(record_persistence_status("pid-nd", None))
        self.assertIsNone(get_persistence_status("pid-nd"))

    def test_overwrite_semantics(self):
        """A second record for the same request_id replaces the first."""
        record_persistence_status("pid-ow", {
            "type": "persistence", "status": "ok", "commit_ms": 1.0,
        })
        record_persistence_status("pid-ow", {
            "type": "persistence", "status": "failed",
            "commit_ms": 2.0, "detail": "boom",
        })
        record = get_persistence_status("pid-ow")
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["detail"], "boom")

    def test_get_returns_copy_not_registry_reference(self):
        """Mutating the returned dict must not mutate the registry."""
        record_persistence_status("pid-copy", {
            "type": "persistence", "status": "ok", "commit_ms": 7.0,
        })
        returned = get_persistence_status("pid-copy")
        returned["status"] = "hacked"
        returned["commit_ms"] = 999.0
        stored = get_persistence_status("pid-copy")
        self.assertEqual(stored["status"], "ok")
        self.assertEqual(stored["commit_ms"], 7.0)

    def test_unknown_prompt_returns_none(self):
        self.assertIsNone(get_persistence_status("pid-never-seen"))


# ═════════════════════════════════════════════════════════════════════════
# Contract items 1-3 — drain end-to-end and natural exhaustion
# ═════════════════════════════════════════════════════════════════════════


class TestDeferredCommitDrain(unittest.TestCase):
    """The local transport drain contract (items 1-3).

    NOTE: these tests exercise ``_spawn_persistence_drain``.  As of the
    current implementation that helper calls
    ``loop.create_task(asyncio.shield(...))`` which raises ``TypeError`` on
    Python 3.11 (``asyncio.shield`` returns a Future, and ``create_task``
    requires a coroutine).  The assertions below encode the APPROVED contract
    and will pass once that helper is corrected.
    """

    def setUp(self):
        _reset_persistence_registry()

    def _run_break_on_result(
        self,
        *,
        events: list[dict],
        prompt_id: str,
    ):
        """Drive ``transport.run_plan_stream`` with a caller that BREAKS on
        the result event (mirrors canonical_execution.py's break), closes the
        generator, and joins the background drain with a bounded timeout."""

        async def run():
            it = _TrackingIterator(events)
            transport = ModalTransport(prompt_stream_fn=lambda **kw: it)
            plan = _plan()
            agen = transport.run_plan_stream(
                plan,
                trace={"prompt_id": prompt_id},
                plan_dict=plan.to_dict(),
            )
            received: list[dict] = []
            async for message in agen:
                received.append(message)
                if message.get("type") == "result":
                    break
            await agen.aclose()
            drain = getattr(transport, "_drain_task", None)
            self.assertIsNotNone(
                drain,
                "early-stop must hand the leftover iterator to the drain",
            )
            await asyncio.wait_for(asyncio.shield(drain), timeout=5.0)
            return received, it

        return asyncio.run(run())

    def test_drain_end_to_end_records_ok(self):
        """Caller breaks on result -> drain consumes the terminal persistence
        event and records status=ok / commit_ms=123.4; iterator aclosed once."""
        prompt_id = "va-drain-ok"
        events = [
            {"type": "status", "event": "restore", "data": {}},
            {"type": "progress", "event": "progress", "data": {"value": 50}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
            {"type": "persistence", "status": "ok",
             "commit_ms": 123.4, "detail": "", "skipped": False},
        ]
        received, it = self._run_break_on_result(
            events=events, prompt_id=prompt_id,
        )
        # Result delivered to the caller before the drain ran.
        result_types = [m.get("type") for m in received]
        self.assertIn("result", result_types)
        self.assertNotIn("persistence", result_types)
        # Registry populated by the drain with the definitive outcome.
        record = get_persistence_status(prompt_id)
        self.assertEqual(record["status"], "ok")
        self.assertEqual(record["commit_ms"], 123.4)
        self.assertIs(record["skipped"], False)
        # The drain aclosed the iterator exactly once at its end.
        self.assertEqual(it.aclose_calls, 1)

    def test_drain_records_failure(self):
        """A terminal persistence event with status=failed is recorded with
        its detail preserved."""
        prompt_id = "va-drain-fail"
        events = [
            {"type": "status", "event": "restore", "data": {}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
            {"type": "persistence", "status": "failed",
             "commit_ms": 0.0, "detail": "volume commit exploded",
             "skipped": False},
        ]
        received, it = self._run_break_on_result(
            events=events, prompt_id=prompt_id,
        )
        self.assertEqual(received[-1]["type"], "result")
        record = get_persistence_status(prompt_id)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["detail"], "volume commit exploded")
        self.assertIs(record["skipped"], False)
        self.assertEqual(it.aclose_calls, 1)

    def test_natural_exhaustion_skips_drain(self):
        """A caller consuming ALL events takes the _stream_exhausted path:
        the iterator is aclosed, no drain task is created, and the transport
        itself does not record (only consumers record)."""
        prompt_id = "va-natural"
        events = [
            {"type": "status", "event": "restore", "data": {}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
        ]
        it = _TrackingIterator(events)

        async def run():
            transport = ModalTransport(prompt_stream_fn=lambda **kw: it)
            plan = _plan()
            received = [
                message async for message in transport.run_plan_stream(
                    plan,
                    trace={"prompt_id": prompt_id},
                    plan_dict=plan.to_dict(),
                )
            ]
            return transport, received

        transport, received = asyncio.run(run())
        self.assertEqual(received[-1]["type"], "result")
        self.assertIsNone(
            getattr(transport, "_drain_task", None),
            "natural exhaustion must not spawn a drain task",
        )
        self.assertEqual(it.aclose_calls, 1)
        # Nothing recorded the persistence outcome on this path.
        self.assertIsNone(get_persistence_status(prompt_id))

    def test_modal_client_natural_exhaustion_records(self):
        """modal_client.run_prompt_stream consumes the stream to natural
        completion and records the persistence event (contract item 3) while
        its finally acloses the generator."""
        prompt_id = "va-mc-natural"
        events = [
            {"type": "status", "event": "restore", "data": {}},
            {"type": "result", "data": {"images": [], "outputs": {}}},
            {"type": "persistence", "status": "ok",
             "commit_ms": 321.0, "detail": "", "skipped": False},
        ]
        it = _TrackingIterator(events)
        api = SimpleNamespace(
            run_prompt_stream=SimpleNamespace(
                remote_gen=SimpleNamespace(aio=lambda *a, **kw: it),
            ),
        )
        from modal_client import run_prompt_stream

        async def run():
            sem = asyncio.Semaphore(1)
            with patch("modal_client._resolve_workspace",
                       return_value={"id": "ws-mc", "token_id": "t",
                                     "token_secret": "s"}):
                with patch("modal_client._workspace_api", return_value=api):
                    with patch("modal_client._run_prompt_semaphore", sem):
                        return [
                            message async for message in run_prompt_stream(
                                {}, trace={"prompt_id": prompt_id},
                            )
                        ]

        messages = asyncio.run(run())
        self.assertEqual(messages[-1]["type"], "persistence")
        record = get_persistence_status(prompt_id)
        self.assertEqual(record["status"], "ok")
        self.assertEqual(record["commit_ms"], 321.0)
        self.assertEqual(it.aclose_calls, 1,
                         "modal_client finally must aclose the generator")


# ═════════════════════════════════════════════════════════════════════════
# Contract item 6 — remote finalizer _finalize_deferred_commit
# ═════════════════════════════════════════════════════════════════════════


def _new_entrypoint() -> Any:
    """Minimal ModalRuntimeEntrypoint instance WITHOUT running __init__ (no
    side effects / no Modal resources needed for the finalizer)."""
    assert ModalRuntimeEntrypoint is not None, "modal_app import failed"
    return object.__new__(ModalRuntimeEntrypoint)


class TestFinalizeDeferredCommit(unittest.TestCase):
    """``_finalize_deferred_commit`` (modal_app.py) — idempotent, never
    raises, emits teardown diagnostics (item 6)."""

    def test_finalize_ok_and_idempotent(self):
        async def _commit():
            return {"commit_ms": 999.0}

        async def run():
            ep = _new_entrypoint()
            diag = _FakeDiag()
            ep._teardown_diagnostics = diag
            ep._deferred_commit_pending = True
            ep._deferred_commit_task = asyncio.create_task(_commit())
            ep._deferred_commit_diag = {}
            first = await ep._finalize_deferred_commit(request_id="r-ok")
            second = await ep._finalize_deferred_commit(request_id="r-ok")
            return ep, diag, first, second

        ep, diag, first, second = asyncio.run(run())
        self.assertEqual(first, {
            "type": "persistence",
            "status": "ok",
            "commit_ms": 999.0,
            "detail": "",
            "skipped": False,
        })
        self.assertIsNone(second, "finalizer must consume the stash")
        self.assertEqual(ep._deferred_commit_pending, False)
        self.assertIsNone(ep._deferred_commit_task)
        # Diag holder updated with the awaited result.
        self.assertEqual(ep._deferred_commit_diag, {"commit_ms": 999.0})
        names = [c["event"] for c in diag.calls]
        self.assertIn("deferred_commit_start", names)
        self.assertIn("deferred_commit_end", names)
        end = next(c for c in diag.calls if c["event"] == "deferred_commit_end")
        self.assertEqual(end["status"], "ok")
        self.assertEqual(end["commit_ms"], 999.0)

    def test_finalize_task_error_returns_failed_never_raises(self):
        async def _commit():
            raise RuntimeError("volume commit exploded")

        async def run():
            ep = _new_entrypoint()
            diag = _FakeDiag()
            ep._teardown_diagnostics = diag
            ep._deferred_commit_pending = True
            ep._deferred_commit_task = asyncio.create_task(_commit())
            ep._deferred_commit_diag = {}
            first = await ep._finalize_deferred_commit(request_id="r-fail")
            second = await ep._finalize_deferred_commit(request_id="r-fail")
            return diag, first, second

        diag, first, second = asyncio.run(run())
        self.assertEqual(first["type"], "persistence")
        self.assertEqual(first["status"], "failed")
        self.assertIn("volume commit exploded", first["detail"])
        self.assertIs(first["skipped"], False)
        self.assertIsNone(second, "stash consumed even on failure")
        end = next(c for c in diag.calls if c["event"] == "deferred_commit_end")
        self.assertEqual(end["status"], "failed")
        self.assertIn("volume commit exploded", end["detail"])

    def test_finalize_cache_hit_skipped(self):
        """Pending True with no task (cache-hit / no commit needed) returns a
        definitive 'ok / skipped' event without awaiting anything."""
        async def run():
            ep = _new_entrypoint()
            diag = _FakeDiag()
            ep._teardown_diagnostics = diag
            ep._deferred_commit_pending = True
            ep._deferred_commit_task = None
            ep._deferred_commit_diag = None
            event = await ep._finalize_deferred_commit(request_id="r-skip")
            return ep, diag, event

        ep, diag, event = asyncio.run(run())
        self.assertEqual(event, {
            "type": "persistence",
            "status": "ok",
            "commit_ms": 0.0,
            "detail": "no commit needed",
            "skipped": True,
        })
        self.assertEqual(ep._deferred_commit_pending, False)
        names = [c["event"] for c in diag.calls]
        self.assertNotIn("deferred_commit_start", names,
                         "cache-hit finalize must not emit a start")
        end = next(c for c in diag.calls if c["event"] == "deferred_commit_end")
        self.assertEqual(end["status"], "ok")
        self.assertEqual(end["commit_ms"], 0.0)

    def test_finalize_not_pending_returns_none(self):
        async def run():
            ep = _new_entrypoint()
            diag = _FakeDiag()
            ep._teardown_diagnostics = diag
            ep._deferred_commit_pending = False
            event = await ep._finalize_deferred_commit(request_id="r-none")
            return diag, event

        diag, event = asyncio.run(run())
        self.assertIsNone(event)
        self.assertEqual(diag.calls, [], "no diagnostics when nothing pending")

    def test_finalize_without_diagnostics_still_works(self):
        """_teardown_diagnostics may be None/absent — finalizer must not
        dereference it."""
        async def _commit():
            return {"commit_ms": 1.0}

        async def run():
            ep = _new_entrypoint()
            ep._deferred_commit_pending = True
            ep._deferred_commit_task = asyncio.create_task(_commit())
            ep._deferred_commit_diag = {}
            return await ep._finalize_deferred_commit(request_id="r-nodiag")

        event = asyncio.run(run())
        self.assertEqual(event["status"], "ok")
        self.assertEqual(event["commit_ms"], 1.0)


# ═════════════════════════════════════════════════════════════════════════
# Contract item 7 — asset-route decision logic (HTTP level)
# ═════════════════════════════════════════════════════════════════════════


class TestAssetRouteVariantARetries(unittest.TestCase):
    """The ``/comfymodal/assets/{asset_id}`` handler retry loop (contract
    item 4): bounded retry on FileNotFoundError consulting the persistence
    registry — definitive failed -> 503, exhaustion -> 404, other errors
    -> 502.  Handlers are invoked directly via the stub-server pattern from
    test_routes_registered.py (no real aiohttp server / network)."""

    @classmethod
    def setUpClass(cls):
        cls.stub = None
        cls.init_mod = _build_init_with_stub(_StubServer())
        cls.asset_fn = _handler_for(
            cls.init_mod, "GET", "/comfymodal/assets/{asset_id}",
        )
        assert cls.asset_fn is not None, "asset_serve route handler not found"

    def setUp(self):
        _reset_persistence_registry()
        self._old_leases = (
            self.init_mod.REGISTRY._lease_singletons.get("_default")
        )
        self._tmp = tempfile.TemporaryDirectory()
        from experiment_lease import LeaseRegistry
        self._leases = LeaseRegistry(Path(self._tmp.name) / "leases.db")
        self.init_mod.REGISTRY._lease_singletons["_default"] = self._leases
        self._workspace_patch = patch.object(
            self.init_mod, "_workspace_or_400",
            return_value={"id": "ws-va", "token_id": "t", "token_secret": "s"},
        )
        self._workspace_patch.start()

    def tearDown(self):
        self._workspace_patch.stop()
        if self._old_leases is not None:
            self.init_mod.REGISTRY._lease_singletons["_default"] = self._old_leases
        else:
            self.init_mod.REGISTRY._lease_singletons.pop("_default", None)
        self._leases.close()
        self._tmp.cleanup()
        _reset_persistence_registry()

    def _register_modal_asset(self, asset_id: str, cell_key: str) -> None:
        self._leases.register_asset(
            asset_id=asset_id,
            experiment_id="",
            cell_key=cell_key,
            variant="original",
            path=f"modal://ws-va|rtx-pro-6000|output_assets/abc.png",
            mime_type="image/png",
            byte_size=7,
            content_hash="hash-va",
        )

    def _request(self, asset_id: str):
        # Call via the class: the handler is stored as a class attribute, and
        # ``self.asset_fn`` would bind it as an instance method.
        return _run(type(self).asset_fn(_MockRequest(match_info={"asset_id": asset_id})))

    async def _noop_sleep(self, _delay: float) -> None:
        return None

    def test_retries_then_succeeds(self):
        """FileNotFoundError twice then bytes -> 200 after bounded retries."""
        asset_id = "ast_va_retry"
        self._register_modal_asset(asset_id, cell_key="cell_va_retry")
        calls: list[str] = []

        async def _read(*args, **kwargs):
            calls.append("read")
            if len(calls) < 3:
                raise FileNotFoundError("not committed yet")
            return {"data": b"\x89PNG-fake", "sha256": "h"}

        with patch("modal_client.read_output_asset", new=_read):
            with patch.object(self.init_mod.asyncio, "sleep",
                              new=self._noop_sleep):
                resp = self._request(asset_id)
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.body, b"\x89PNG-fake")
        self.assertEqual(len(calls), 3)

    def test_definitive_failed_returns_503_without_retries(self):
        """get_persistence_status(cell_key) == failed -> 503 immediately."""
        asset_id = "ast_va_503"
        cell_key = "cell_va_503"
        self._register_modal_asset(asset_id, cell_key=cell_key)
        record_persistence_status(cell_key, {
            "type": "persistence", "status": "failed", "detail": "commit boom",
        })
        calls: list[str] = []

        async def _read(*args, **kwargs):
            calls.append("read")
            raise FileNotFoundError("not committed yet")

        with patch("modal_client.read_output_asset", new=_read):
            resp = self._request(asset_id)
        self.assertEqual(resp.status, 503)
        self.assertEqual(len(calls), 1,
                         "definitive failed status must short-circuit retries")
        self.assertIn("commit boom", str(resp.body))

    def test_exhaustion_returns_404(self):
        """Persistent FileNotFoundError with no registry record -> 404 after
        the bounded retry window."""
        asset_id = "ast_va_404"
        self._register_modal_asset(asset_id, cell_key="cell_va_404")
        calls: list[str] = []

        async def _read(*args, **kwargs):
            calls.append("read")
            raise FileNotFoundError("still missing")

        with patch("modal_client.read_output_asset", new=_read):
            with patch.object(self.init_mod.asyncio, "sleep",
                              new=self._noop_sleep):
                resp = self._request(asset_id)
        self.assertEqual(resp.status, 404)
        self.assertEqual(len(calls), 5, "exhaustion must try all 5 attempts")

    def test_other_error_returns_502(self):
        """A non-FileNotFoundError aborts the retry loop -> 502."""
        asset_id = "ast_va_502"
        self._register_modal_asset(asset_id, cell_key="cell_va_502")

        async def _read(*args, **kwargs):
            raise ValueError("remote exploded")

        with patch("modal_client.read_output_asset", new=_read):
            resp = self._request(asset_id)
        self.assertEqual(resp.status, 502)


class _StubServer:
    """Minimal stand-in so the asset-route class can build its own stub
    without importing the private class from test_routes_registered."""

    def __init__(self) -> None:
        self.routes: Any = _StubRouteTable()
        self.sent_events: list[tuple[str, dict, str]] = []

    def send_sync(self, event: str, data: dict, sid: str = "") -> None:
        self.sent_events.append((event, dict(data), sid))


class _StubRouteTable:
    def __init__(self) -> None:
        self._handlers: list[tuple[str, str, Any]] = []

    def get(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("GET", path, fn))
            return fn
        return deco

    def post(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("POST", path, fn))
            return fn
        return deco

    def put(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("PUT", path, fn))
            return fn
        return deco

    def delete(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("DELETE", path, fn))
            return fn
        return deco

    def patch(self, path: str) -> Any:
        def deco(fn):
            self._handlers.append(("PATCH", path, fn))
            return fn
        return deco


if __name__ == "__main__":
    unittest.main()
