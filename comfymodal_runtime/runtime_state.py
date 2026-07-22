"""Atomic runtime-state JSON writes and serialized commit coordination.

Provides:

* ``FakeVolume`` — in-memory state volume for testing (reports write/read
  metrics and commit metrics).
* ``MountedStateVolume`` — real filesystem volume using temp file +
  ``os.replace()`` for genuine atomicity.  Temp files are always cleaned
  up after rename.
* ``CommitMetrics`` — exported coordinator metrics.
* ``CommitCoordinator`` — one-Volume-wide serialized commit coordinator
  with dirty generation tracking, at most one in-flight worker, committed
  generation tracking, and exactly one follow-up commit when writes arrive
  during a commit.

The coordinator never touches a models volume.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable


# ── Volume abstraction ───────────────────────────────────────────────────


@runtime_checkable
class StateVolume(Protocol):
    """Abstract volume interface for runtime state persistence.

    Implement with a real Modal Volume, ``MountedStateVolume``, or
    ``FakeVolume`` for tests.
    """

    def write_bytes(self, path: str, data: bytes) -> None: ...
    def read_bytes(self, path: str) -> bytes: ...
    def exists(self, path: str) -> bool: ...
    def remove(self, path: str) -> None: ...
    def commit(self) -> None: ...


class FakeVolume:
    """In-memory state volume for testing.

    Attributes
    ----------
    write_count : int
        Number of ``write_bytes()`` calls.
    read_count : int
        Number of ``read_bytes()`` calls.
    commit_count : int
        Number of ``commit()`` calls.
    write_bytes_total : int
        Total bytes written across all calls.
    """

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self.write_count: int = 0
        self.read_count: int = 0
        self.commit_count: int = 0
        self.write_bytes_total: int = 0

    def write_bytes(self, path: str, data: bytes) -> None:
        self._files[path] = data
        self.write_count += 1
        self.write_bytes_total += len(data)

    def read_bytes(self, path: str) -> bytes:
        self.read_count += 1
        return self._files.get(path, b"")

    def exists(self, path: str) -> bool:
        return path in self._files

    def remove(self, path: str) -> None:
        self._files.pop(path, None)

    def commit(self) -> None:
        """Explicit volume commit — no-op for in-memory, but tracks call count."""
        self.commit_count += 1

    @property
    def file_count(self) -> int:
        """Number of unique files stored."""
        return len(self._files)


class MountedStateVolume:
    """Real filesystem volume using temp file + ``os.replace()``.

    Writes go to a temporary file first, then are atomically renamed
    to the final path.  Temp files never appear at the final path
    until the rename completes.  Temp files are cleaned up after the
    rename.

    Parameters
    ----------
    root : str
        Root directory on the mounted filesystem.
    """

    def __init__(self, root: str) -> None:
        self._root = root
        self._write_count: int = 0
        self._read_count: int = 0
        self._commit_count: int = 0
        self._write_bytes_total: int = 0

    # ── Public path resolvers ────────────────────────────────────────

    def _resolve(self, path: str) -> str:
        return os.path.join(self._root, path)

    def _temp_path(self, path: str) -> str:
        return f"{self._resolve(path)}.tmp.{os.getpid()}.{threading.get_ident()}"

    # ── StateVolume protocol ─────────────────────────────────────────

    def write_bytes(self, path: str, data: bytes) -> None:
        """Atomically write *data* to *path* using temp file + rename.

        The temp file is created alongside the final path in the same
        directory to ensure same-filesystem rename semantics.
        """
        final = self._resolve(path)
        temp = self._temp_path(path)
        # Ensure parent directory exists
        parent = os.path.dirname(final)
        os.makedirs(parent, exist_ok=True)
        # Write temp file
        with open(temp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        # Atomic rename
        os.replace(temp, final)
        self._write_count += 1
        self._write_bytes_total += len(data)

    def reload(self) -> None:
        """Hook for mounted filesystems; Modal-backed volumes override it."""
        return None

    def read_bytes(self, path: str) -> bytes:
        final = self._resolve(path)
        self._read_count += 1
        with open(final, "rb") as f:
            return f.read()

    def exists(self, path: str) -> bool:
        return os.path.isfile(self._resolve(path))

    def remove(self, path: str) -> None:
        """Remove *path* and any orphan temp file for it."""
        final = self._resolve(path)
        temp = self._temp_path(path)
        try:
            os.remove(final)
        except FileNotFoundError:
            pass
        try:
            os.remove(temp)
        except FileNotFoundError:
            pass

    def commit(self) -> None:
        """Explicit volume commit — calls ``fsync`` on the parent dir.

        This is the point where the filesystem is told "this write is
        durable".  After ``commit()`` returns, the data is guaranteed
        to have survived a crash (assuming the underlying filesystem
        honours ``fsync``).
        """
        try:
            fd = os.open(self._root, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass  # best-effort fsync on directory
        self._commit_count += 1

    # ── Metrics ──────────────────────────────────────────────────────

    @property
    def write_count(self) -> int:
        return self._write_count

    @property
    def read_count(self) -> int:
        return self._read_count

    @property
    def commit_count(self) -> int:
        return self._commit_count

    @property
    def write_bytes_total(self) -> int:
        return self._write_bytes_total


class ModalMountedStateVolume(MountedStateVolume):
    """Mounted runtime-state files backed by a real Modal Volume."""

    def __init__(self, root: str, modal_volume: Any) -> None:
        super().__init__(root)
        self._modal_volume = modal_volume

    def reload(self) -> None:
        reload_fn = getattr(self._modal_volume, "reload", None)
        if callable(reload_fn):
            reload_fn()

    async def reload_async(self) -> None:
        """Async reload — tries ``self._modal_volume.reload.aio()`` first,
        falls back to ``asyncio.to_thread(self.reload)`` for fakes/older
        APIs that only expose a synchronous ``reload()``.

        Modal's ``Volume.reload`` exposes an ``.aio()`` coroutine method
        that should be preferred in async contexts to avoid the "synchronous
        reload in async context" warning.  When the attribute check fails
        (e.g. ``FakeVolume`` or an older API surface), the fallback runs
        ``self.reload()`` in a thread via ``asyncio.to_thread()``.
        """
        modal_volume = self._modal_volume
        reload_fn = getattr(modal_volume, "reload", None)
        if reload_fn is not None:
            aio_method = getattr(reload_fn, "aio", None)
            if callable(aio_method):
                await aio_method()
                return
        # Fallback: synchronous reload in a thread.
        await asyncio.to_thread(self.reload)

    def commit(self) -> None:
        super().commit()
        commit_fn = getattr(self._modal_volume, "commit", None)
        if not callable(commit_fn):
            raise RuntimeError("runtime-state Modal Volume does not expose commit()")
        commit_fn()

    async def commit_async(self) -> None:
        """Async commit — uses Modal's native async Volume commit.

        Prefers ``commit.aio()`` when available (Modal's synchronous wrapper
        exposing the coroutine).  Falls back to ``commit()`` via
        ``asyncio.to_thread`` for older APIs or fakes that only expose a
        synchronous commit.

        Does NOT call ``super().commit()`` (which performs a synchronous
        fsync) — Modal's commit handles durability.  The coordinator's
        ``commit_async`` caller tracks the single commit via metrics.
        """
        commit_fn = getattr(self._modal_volume, "commit", None)
        if not callable(commit_fn):
            raise RuntimeError("runtime-state Modal Volume does not expose commit()")
        aio_method = getattr(commit_fn, "aio", None)
        if callable(aio_method):
            await aio_method()  # type: ignore[call-overload]
        elif asyncio.iscoroutinefunction(commit_fn):
            await commit_fn()  # type: ignore[call-overload]
        else:
            # Synchronous commit in a thread — never blocking Modal commit
            await asyncio.to_thread(commit_fn)


# ── Metrics ──────────────────────────────────────────────────────────────


@dataclass
class CommitMetrics:
    """Exported commit-coordinator metrics."""

    write_count: int = 0
    commit_count: int = 0
    follow_up_count: int = 0
    total_write_bytes: int = 0
    last_commit_ms: float = 0.0


# ── Coordinator ──────────────────────────────────────────────────────────


class CommitCoordinator:
    """One-Volume-wide serialized commit coordinator.

    Semantics
    ---------
    * ``dirty_generation`` — the generation that has pending uncommitted
      writes.
    * ``committed_generation`` — the last generation fully committed.
    * At most one commit in-flight at any time.
    * When writes arrive during an in-flight commit, exactly one follow-up
      commit is scheduled after the current commit completes.
    * ``write_state()`` uses an atomic temp-file + rename pattern to
      prevent partial writes.
    * Never touches a models volume — only a single state path.

    Parameters
    ----------
    volume : StateVolume
        Abstract volume (real or fake) for state persistence.
    state_path : str
        Path on the volume for the runtime-state JSON file.
    """

    def __init__(
        self, volume: StateVolume, state_path: str = "runtime_state.json"
    ) -> None:
        self._volume = volume
        self._state_path = state_path
        self._lock = threading.Lock()
        self._in_flight = False
        self._dirty_gen: int = -1
        self._committed_gen: int = -1
        self._needs_follow_up = False
        self._metrics = CommitMetrics()

    # ── Read-only accessors ──────────────────────────────────────────

    @property
    def dirty_generation(self) -> int:
        with self._lock:
            return self._dirty_gen

    @property
    def committed_generation(self) -> int:
        with self._lock:
            return self._committed_gen

    @property
    def in_flight(self) -> bool:
        with self._lock:
            return self._in_flight

    @property
    def metrics(self) -> CommitMetrics:
        with self._lock:
            return CommitMetrics(
                write_count=self._metrics.write_count,
                commit_count=self._metrics.commit_count,
                follow_up_count=self._metrics.follow_up_count,
                total_write_bytes=self._metrics.total_write_bytes,
                last_commit_ms=self._metrics.last_commit_ms,
            )

    @property
    def state_path(self) -> str:
        return self._state_path

    # ── Internal helpers ───────────────────────────────────────────────

    def _temp_path(self) -> str:
        """Derive a unique temp-file path for the state path."""
        return f"{self._state_path}.tmp.{os.getpid()}.{threading.get_ident()}"

    def _cleanup_temp(self) -> None:
        """Remove any orphan temp file for the state path."""
        temp = self._temp_path()
        try:
            self._volume.remove(temp)
        except Exception:
            pass

    # ── Public API ───────────────────────────────────────────────────

    def write_state(self, generation: int, data: dict[str, Any]) -> None:
        """Atomically write runtime-state JSON for *generation*.

        Uses a temp-file + final-path write pattern for atomicity
        on a mounted filesystem (via ``MountedStateVolume``).
        Marks *generation* as dirty.
        """
        # Stamp metadata onto the payload
        data["_generation"] = generation
        data["_committed_generation"] = self._committed_gen

        encoded = json.dumps(
            data, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")

        # Clean up any previous orphan temp before writing.
        self._cleanup_temp()

        # Write through the volume (atomic for MountedStateVolume,
        # in-memory for FakeVolume).
        self._volume.write_bytes(self._state_path, encoded)

        with self._lock:
            self._dirty_gen = generation
            self._metrics.write_count += 1
            self._metrics.total_write_bytes += len(encoded)
            # If a commit is in-flight, schedule a follow-up commit
            if self._in_flight:
                self._needs_follow_up = True

    def reload(self) -> None:
        """Reload the authoritative backing volume before a state read."""
        reload_fn = getattr(self._volume, "reload", None)
        if callable(reload_fn):
            reload_fn()

    async def reload_async(self) -> None:
        """Async reload — uses ``volume.reload_async`` when available,
        falls back to ``asyncio.to_thread(self.reload)`` for older APIs."""
        reload_fn = getattr(self._volume, "reload_async", None)
        if callable(reload_fn):
            await reload_fn()  # type: ignore[call-overload]
        else:
            await asyncio.to_thread(self.reload)

    def commit(self, generation: int) -> bool:
        """Commit *generation* if it matches the current dirty generation.

        Calls the volume's own ``commit()`` for filesystem-level durability
        (e.g. ``fsync`` on a ``MountedStateVolume``).

        Returns ``True`` when this call performed the commit.  Returns
        ``False`` when a commit was already in-flight (a follow-up is
        automatically scheduled after the current commit completes).

        When writes arrive during the commit, exactly one follow-up commit
        runs after the current commit finishes.
        """
        with self._lock:
            if generation != self._dirty_gen:
                return False  # stale or superseded generation
            if self._in_flight:
                self._needs_follow_up = True
                return False
            self._in_flight = True

        # ── Perform the commit ───────────────────────────────────
        _start = time.perf_counter()
        try:
            # Re-read to confirm persistence on the volume.
            self._volume.read_bytes(self._state_path)
            # Volume-level durability commit (fsync).
            self._volume.commit()
            with self._lock:
                self._committed_gen = generation
                self._metrics.commit_count += 1
                self._metrics.last_commit_ms = (
                    time.perf_counter() - _start
                ) * 1000
        finally:
            with self._lock:
                self._in_flight = False

        # ── One follow-up if writes arrived during commit ─────────
        follow_gen: int | None = None
        with self._lock:
            if self._needs_follow_up:
                self._needs_follow_up = False
                if self._dirty_gen > self._committed_gen:
                    self._metrics.follow_up_count += 1
                    follow_gen = self._dirty_gen

        if follow_gen is not None:
            # Lock is released before recursive call (max depth 1).
            self.commit(follow_gen)

        return True

    async def commit_async(self, generation: int) -> bool:
        """Async variant of ``commit()`` that uses the volume's async commit.

        Same serialization semantics as ``commit()`` but uses
        ``volume.commit_async()`` to avoid blocking the event loop when the
        underlying Modal Volume.commit() is async.
        """
        with self._lock:
            if generation != self._dirty_gen:
                return False
            if self._in_flight:
                self._needs_follow_up = True
                return False
            self._in_flight = True

        _start = time.perf_counter()
        try:
            self._volume.read_bytes(self._state_path)
            commit_fn = getattr(self._volume, "commit_async", None)
            if callable(commit_fn):
                await commit_fn()  # type: ignore[call-overload]
            else:
                # No async commit method — use thread fallback to avoid
                # blocking the event loop with a synchronous Modal commit.
                await asyncio.to_thread(self._volume.commit)
            with self._lock:
                self._committed_gen = generation
                self._metrics.commit_count += 1
                self._metrics.last_commit_ms = (
                    time.perf_counter() - _start
                ) * 1000
        finally:
            with self._lock:
                self._in_flight = False

        follow_gen: int | None = None
        with self._lock:
            if self._needs_follow_up:
                self._needs_follow_up = False
                if self._dirty_gen > self._committed_gen:
                    self._metrics.follow_up_count += 1
                    follow_gen = self._dirty_gen

        if follow_gen is not None:
            await self.commit_async(follow_gen)

        return True

    def read_state(self) -> dict[str, Any] | None:
        """Read the current state from the volume.

        Returns ``None`` when the state path does not exist.
        """
        if not self._volume.exists(self._state_path):
            return None
        raw = self._volume.read_bytes(self._state_path)
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))
