"""Tests for runtime_state async commit boundaries.

Ensures:
* ModalMountedStateVolume.commit() is sync-only — one sync call, zero async.
* ModalMountedStateVolume.commit_async() invokes one async call exactly once
  without falling back to sync after an async path was chosen.
* CommitCoordinator.commit_async() delegates to volume.commit_async()
  exactly once, with proper lock/in-flight/follow-up semantics.
* No un-awaited coroutines and no duplicate operations when .aio is used.
* Write-before-commit ordering and stable JSON serialization.
"""

import asyncio
import json
import shutil
import tempfile
import unittest

from comfymodal_runtime.runtime_state import (
    CommitCoordinator,
    FakeVolume,
    ModalMountedStateVolume,
)


# ── Fakes for ModalMountedStateVolume tests ─────────────────────────


class _SyncOnlyFakeModal:
    """Fake Modal Volume exposing only synchronous commit()."""

    def __init__(self):
        self.commit_call_count = 0

    def commit(self):
        self.commit_call_count += 1


class _SyncReturningAwaitableModal:
    """Fake sync API whose single call returns an awaitable."""

    def __init__(self):
        self.commit_call_count = 0
        self.awaited_count = 0

    def commit(self):
        self.commit_call_count += 1

        async def finish():
            self.awaited_count += 1

        return finish()


class _CoroutineFakeModal:
    """Fake Modal Volume where commit is a coroutine function."""

    def __init__(self):
        self.commit_call_count = 0

    async def commit(self):
        self.commit_call_count += 1


class _AioCommitHolder:
    """Holder that looks like Modal's Volume.commit with an ``.aio`` attribute.

    ``__call__`` implements the synchronous wrapper; ``.aio`` is an async
    callable returning a coroutine.
    """

    def __init__(self, parent: "_AioFakeModal"):
        self._parent = parent

        async def _aio():
            parent.aio_call_count += 1

        self.aio = _aio

    def __call__(self):
        self._parent.sync_call_count += 1


class _AioFakeModal:
    """Fake Modal Volume exposing ``commit.aio`` as the async path.

    Tracks both ``sync_call_count`` and ``aio_call_count`` independently.
    """

    def __init__(self):
        self.sync_call_count = 0
        self.aio_call_count = 0
        self._commit_holder = _AioCommitHolder(self)

    @property
    def commit(self):
        return self._commit_holder


# ── Fakes for CommitCoordinator tests ──────────────────────────────


class _CoordAsyncVolume:
    """In-memory volume with ``commit_async()`` for coordinator tests."""

    def __init__(self):
        self._files: dict[str, bytes] = {}
        self.write_count = 0
        self.read_count = 0
        self.sync_commit_count = 0
        self.async_commit_count = 0
        self.fail_async = False

    def write_bytes(self, path: str, data: bytes) -> None:
        self._files[path] = data
        self.write_count += 1

    def read_bytes(self, path: str) -> bytes:
        self.read_count += 1
        return self._files.get(path, b"")

    def exists(self, path: str) -> bool:
        return path in self._files

    def remove(self, path: str) -> None:
        self._files.pop(path, None)

    def commit(self) -> None:
        self.sync_commit_count += 1

    async def commit_async(self) -> None:
        self.async_commit_count += 1
        if self.fail_async:
            raise RuntimeError("async commit failed")


class _CoordSyncOnlyVolume:
    """In-memory volume *without* ``commit_async`` (tests sync fallback)."""

    def __init__(self):
        self._files: dict[str, bytes] = {}
        self.write_count = 0
        self.read_count = 0
        self.sync_commit_count = 0

    def write_bytes(self, path: str, data: bytes) -> None:
        self._files[path] = data
        self.write_count += 1

    def read_bytes(self, path: str) -> bytes:
        self.read_count += 1
        return self._files.get(path, b"")

    def exists(self, path: str) -> bool:
        return path in self._files

    def remove(self, path: str) -> None:
        self._files.pop(path, None)

    def commit(self) -> None:
        self.sync_commit_count += 1


class _PausableCoordVolume(_CoordAsyncVolume):
    """Volume whose ``commit_async()`` can be paused for in-flight tests.

    The test can wait for ``commit_started`` (signals the commit is
    executing), then write during the commit, and finally signal
    ``commit_continue`` to let it finish.
    """

    def __init__(self):
        super().__init__()
        self.commit_started = asyncio.Event()
        self.commit_continue = asyncio.Event()

    async def commit_async(self) -> None:
        self.async_commit_count += 1
        self.commit_started.set()
        await self.commit_continue.wait()
        if self.fail_async:
            raise RuntimeError("async commit failed")


class _OrderTrackingVolume:
    """Records call sequence for ordering assertion."""

    def __init__(self):
        self._files: dict[str, bytes] = {}
        self.sequence: list[str] = []

    def write_bytes(self, path: str, data: bytes) -> None:
        self._files[path] = data
        self.sequence.append("write")

    def read_bytes(self, path: str) -> bytes:
        self.sequence.append("read")
        return self._files.get(path, b"")

    def exists(self, path: str) -> bool:
        return path in self._files

    def remove(self, path: str) -> None:
        self._files.pop(path, None)

    def commit(self) -> None:
        self.sequence.append("sync_commit")

    async def commit_async(self) -> None:
        self.sequence.append("async_commit")


# ── Tests: ModalMountedStateVolume.commit() (sync-only) ────────────


class TestVolumeSyncCommit(unittest.TestCase):
    """``ModalMountedStateVolume.commit()`` is sync-only.

    It must invoke exactly one synchronous ``modal_volume.commit()`` and
    *never* reach into any async API.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def test_sync_commit_calls_modal_commit_exactly_once(self):
        """Sync commit invokes ``modal_volume.commit()`` once."""
        fake = _SyncOnlyFakeModal()
        vol = ModalMountedStateVolume(self.tmpdir, fake)
        vol.commit()
        self.assertEqual(fake.commit_call_count, 1)

    def test_sync_commit_does_not_call_aio_when_available(self):
        """When both sync and .aio exist, commit() calls sync only."""
        fake = _AioFakeModal()
        vol = ModalMountedStateVolume(self.tmpdir, fake)
        vol.commit()
        self.assertEqual(fake.sync_call_count, 1)
        self.assertEqual(fake.aio_call_count, 0)

    def test_sync_commit_invokes_super_fsync(self):
        """Sync commit also calls ``super().commit()`` for local durability."""
        fake = _SyncOnlyFakeModal()
        vol = ModalMountedStateVolume(self.tmpdir, fake)
        vol.commit()
        self.assertEqual(vol.commit_count, 1)


# ── Tests: ModalMountedStateVolume.commit_async() ──────────────────


class TestVolumeAsyncCommit(unittest.IsolatedAsyncioTestCase):
    """``ModalMountedStateVolume.commit_async()`` uses exactly one async call.

    Three paths are exercised:
    * ``.aio`` callable (preferred)
    * coroutine-function ``commit()``
    * synchronous ``commit()`` via thread fallback
    """

    async def asyncSetUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    async def test_aio_called_exactly_once_no_sync_fallback(self):
        """``.aio`` is invoked once; sync ``commit()`` is not called."""
        fake = _AioFakeModal()
        vol = ModalMountedStateVolume(self.tmpdir, fake)
        await vol.commit_async()
        self.assertEqual(fake.aio_call_count, 1)
        self.assertEqual(fake.sync_call_count, 0)

    async def test_coroutine_function_called_exactly_once(self):
        """A coroutine-function ``commit()`` is called once, result awaited."""
        fake = _CoroutineFakeModal()
        vol = ModalMountedStateVolume(self.tmpdir, fake)
        await vol.commit_async()
        self.assertEqual(fake.commit_call_count, 1)

    async def test_sync_fallback_runs_in_thread(self):
        """Without async API, the sync commit is run via ``to_thread``."""
        fake = _SyncOnlyFakeModal()
        vol = ModalMountedStateVolume(self.tmpdir, fake)
        await vol.commit_async()
        self.assertEqual(fake.commit_call_count, 1)

    async def test_sync_fallback_awaits_returned_awaitable_once(self):
        """A sync fallback result is awaited without a second invocation."""
        fake = _SyncReturningAwaitableModal()
        vol = ModalMountedStateVolume(self.tmpdir, fake)
        await vol.commit_async()
        self.assertEqual(fake.commit_call_count, 1)
        self.assertEqual(fake.awaited_count, 1)

    async def test_aio_path_does_not_leak_to_sync(self):
        """When ``.aio`` is present, sync path is never entered."""
        fake = _AioFakeModal()
        vol = ModalMountedStateVolume(self.tmpdir, fake)
        await vol.commit_async()
        self.assertEqual(fake.aio_call_count, 1)
        self.assertEqual(fake.sync_call_count, 0)

    async def test_async_commit_skips_super_commit(self):
        """``commit_async()`` does **not** call ``super().commit()`` (no fsync)."""
        fake = _SyncOnlyFakeModal()
        vol = ModalMountedStateVolume(self.tmpdir, fake)
        await vol.commit_async()
        self.assertEqual(vol.commit_count, 0)


# ── Tests: CommitCoordinator.commit_async() ────────────────────────


class TestCoordinatorAsyncCommit(unittest.IsolatedAsyncioTestCase):
    """``CommitCoordinator.commit_async()`` semantics."""

    # ── Basic delegation ────────────────────────────────────────────

    async def test_delegates_to_volume_commit_async_once(self):
        """Coordinator calls ``volume.commit_async()`` exactly once."""
        vol = _CoordAsyncVolume()
        coord = CommitCoordinator(vol)
        coord.write_state(1, {"key": "val"})
        result = await coord.commit_async(1)
        self.assertTrue(result)
        self.assertEqual(vol.async_commit_count, 1)
        self.assertEqual(vol.sync_commit_count, 0)

    async def test_fallback_to_sync_commit_in_thread(self):
        """When volume lacks ``commit_async``, runs sync in thread."""
        vol = _CoordSyncOnlyVolume()
        coord = CommitCoordinator(vol)
        coord.write_state(1, {"key": "val"})
        result = await coord.commit_async(1)
        self.assertTrue(result)
        self.assertEqual(vol.sync_commit_count, 1)

    # ── Serialization / locking ─────────────────────────────────────

    async def test_stale_generation_returns_false(self):
        """Stale generation returns False without committing."""
        vol = _CoordAsyncVolume()
        coord = CommitCoordinator(vol)
        coord.write_state(1, {"key": "val"})
        result = await coord.commit_async(0)  # stale
        self.assertFalse(result)
        self.assertEqual(vol.async_commit_count, 0)
        self.assertEqual(coord.committed_generation, -1)

    async def test_in_flight_is_true_during_commit(self):
        """``in_flight`` is True while commit is executing."""
        vol = _PausableCoordVolume()
        coord = CommitCoordinator(vol)
        coord.write_state(1, {"key": "val"})

        async def do_commit():
            return await coord.commit_async(1)

        task = asyncio.create_task(do_commit())
        await vol.commit_started.wait()
        self.assertTrue(coord.in_flight)
        vol.commit_continue.set()
        await task
        self.assertFalse(coord.in_flight)

    async def test_follow_up_on_write_during_in_flight(self):
        """Write during in-flight triggers exactly one follow-up commit."""
        vol = _PausableCoordVolume()
        coord = CommitCoordinator(vol)
        coord.write_state(1, {"key": "val1"})

        async def do_commit():
            return await coord.commit_async(1)

        task = asyncio.create_task(do_commit())
        await vol.commit_started.wait()

        # Write while first commit is in-flight
        coord.write_state(2, {"key": "val2"})

        vol.commit_continue.set()
        await task

        self.assertEqual(coord.committed_generation, 2)
        self.assertEqual(coord.metrics.commit_count, 2)
        self.assertEqual(coord.metrics.follow_up_count, 1)
        self.assertEqual(vol.async_commit_count, 2)
        self.assertFalse(coord.in_flight)

    async def test_failure_clears_in_flight(self):
        """Exception during ``commit_async()`` clears ``in_flight``."""
        vol = _CoordAsyncVolume()
        vol.fail_async = True
        coord = CommitCoordinator(vol)
        coord.write_state(1, {"key": "val"})
        with self.assertRaises(RuntimeError):
            await coord.commit_async(1)
        self.assertFalse(coord.in_flight)

    async def test_failure_preserves_previous_committed_gen(self):
        """Failed commit does not advance ``committed_generation``."""
        vol = _CoordAsyncVolume()
        vol.fail_async = True
        coord = CommitCoordinator(vol)
        coord.write_state(1, {"key": "val"})
        with self.assertRaises(RuntimeError):
            await coord.commit_async(1)
        self.assertEqual(coord.committed_generation, -1)

    # ── Ordering ────────────────────────────────────────────────────

    async def test_write_before_commit_ordering(self):
        """``read_bytes`` executes before ``commit_async``."""
        vol = _OrderTrackingVolume()
        coord = CommitCoordinator(vol)
        coord.write_state(1, {"key": "val"})
        await coord.commit_async(1)
        self.assertEqual(vol.sequence, ["write", "read", "async_commit"])

    # ── Concurrent callers ──────────────────────────────────────────

    async def test_concurrent_async_callers_one_commits_second_follows_up(self):
        """Two concurrent callers: first commits, second detects in-flight
        and is covered by the follow-up after the first completes."""
        vol = _PausableCoordVolume()
        coord = CommitCoordinator(vol)
        coord.write_state(1, {"key": "first"})

        async def caller_1():
            return await coord.commit_async(1)

        task1 = asyncio.create_task(caller_1())
        await vol.commit_started.wait()

        # Second caller arrives while first is in-flight
        coord.write_state(2, {"key": "second"})
        result2 = await coord.commit_async(2)
        self.assertFalse(result2)  # in-flight, so False

        # Let first commit finish
        vol.commit_continue.set()
        await task1

        self.assertEqual(coord.committed_generation, 2)
        self.assertEqual(coord.metrics.commit_count, 2)
        self.assertEqual(coord.metrics.follow_up_count, 1)
        self.assertFalse(coord.in_flight)


# ── Tests: state serialization ─────────────────────────────────────


class TestStateSerialization(unittest.TestCase):
    """``write_state`` JSON serialisation byte-for-byte stable."""

    def test_metadata_fields_stamped(self):
        """``write_state`` stamps ``_generation`` and ``_committed_generation``."""
        vol = FakeVolume()
        coord = CommitCoordinator(vol, "state.json")
        coord.write_state(7, {"user": "data"})
        raw = vol.read_bytes("state.json")
        parsed = json.loads(raw)
        self.assertEqual(parsed["_generation"], 7)
        self.assertEqual(parsed["_committed_generation"], -1)
        self.assertEqual(parsed["user"], "data")

    def test_json_format_exact(self):
        """JSON uses ``separators=(',',':')`` and ``sort_keys=True``."""
        vol = FakeVolume()
        coord = CommitCoordinator(vol, "state.json")
        coord.write_state(3, {"b": 2, "a": 1})
        raw = vol.read_bytes("state.json")
        expected = b'{"_committed_generation":-1,"_generation":3,"a":1,"b":2}'
        self.assertEqual(raw, expected)

    def test_committed_generation_updates_after_commit(self):
        """After a sync commit, subsequent writes reflect the new committed gen."""
        vol = FakeVolume()
        coord = CommitCoordinator(vol, "state.json")
        coord.write_state(1, {"x": 1})
        coord.commit(1)  # synchronous commit
        coord.write_state(2, {"x": 2})
        raw = vol.read_bytes("state.json")
        parsed = json.loads(raw)
        self.assertEqual(parsed["_generation"], 2)
        self.assertEqual(parsed["_committed_generation"], 1)



# ── Test: no blocking synchronous Modal commit in async pipeline ─────


class TestNoBlockingModalCommitInAsyncPath(unittest.IsolatedAsyncioTestCase):
    """Verifies that the full async commit pipeline never calls a
    synchronous Modal volume.commit() without .aio() or to_thread."""

    async def test_modal_mounted_volume_async_commit_uses_aio(self):
        """ModalMountedStateVolume.commit_async() uses .aio() when available,
        never calls the synchronous commit path."""
        fake = _AioFakeModal()
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp()
        try:
            vol = ModalMountedStateVolume(tmpdir, fake)
            await vol.commit_async()
            # aio path called exactly once
            self.assertEqual(fake.aio_call_count, 1,
                             ".aio() must be called exactly once")
            # sync path NOT called
            self.assertEqual(fake.sync_call_count, 0,
                             "sync commit must NOT be called in async path")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    async def test_coordinator_async_commit_uses_volume_async(self):
        """CommitCoordinator.commit_async() delegates to volume.commit_async(),
        NOT to volume.commit() directly."""
        class _TrackingVolume:
            """Volume that tracks which commit method is called."""
            def __init__(self):
                self._files = {}
                self.sync_commit_calls = 0
                self.async_commit_calls = 0
            def write_bytes(self, path, data):
                self._files[path] = data
            def read_bytes(self, path):
                return self._files.get(path, b"")
            def exists(self, path):
                return path in self._files
            def remove(self, path):
                self._files.pop(path, None)
            def commit(self):
                self.sync_commit_calls += 1
            async def commit_async(self):
                self.async_commit_calls += 1

        vol = _TrackingVolume()
        coord = CommitCoordinator(vol)
        coord.write_state(1, {"key": "val"})
        result = await coord.commit_async(1)
        self.assertTrue(result)
        self.assertEqual(vol.async_commit_calls, 1,
                         "volume.commit_async() must be called exactly once")
        self.assertEqual(vol.sync_commit_calls, 0,
                         "volume.commit() must NOT be called in async path")

    async def test_full_async_write_and_commit_pipeline(self):
        """A complete write → commit_async pipeline works correctly."""
        class _AsyncAwareVolume:
            """Volume that supports both sync and async commit."""
            def __init__(self):
                self._files = {}
                self.sync_commit_count = 0
                self.async_commit_count = 0
                self.write_count = 0
                self.read_count = 0
            def write_bytes(self, path, data):
                self._files[path] = data
                self.write_count += 1
            def read_bytes(self, path):
                self.read_count += 1
                return self._files.get(path, b"")
            def exists(self, path):
                return path in self._files
            def remove(self, path):
                self._files.pop(path, None)
            def commit(self):
                self.sync_commit_count += 1
            async def commit_async(self):
                self.async_commit_count += 1

        vol = _AsyncAwareVolume()
        coord = CommitCoordinator(vol)
        coord.write_state(1, {"data": "hello"})
        coord.write_state(2, {"data": "world"})
        result = await coord.commit_async(2)
        self.assertTrue(result)
        self.assertEqual(vol.write_count, 2)
        self.assertEqual(vol.async_commit_count, 1)
        self.assertEqual(vol.sync_commit_count, 0)
        self.assertEqual(coord.committed_generation, 2)
        # Verify persisted data
        state = coord.read_state()
        self.assertIsNotNone(state)
        if state is not None:
            self.assertEqual(state.get("data"), "world")


if __name__ == "__main__":
    unittest.main()
