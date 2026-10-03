"""Reusable JSON file store with locking and atomic writes.

Provides ``StudioJsonStore`` — a thread-safe, crash-safe persistence helper
that uses an RLock for concurrent access and a tmp+os.replace pattern for
atomic file writes.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable


class StudioStoreError(RuntimeError):
    """Base error for ``StudioJsonStore`` operations."""

    pass


class StudioJsonStore:
    """Thread-safe JSON file store with atomic writes.

    Usage::

        store = StudioJsonStore("/path/to/data.json")
        store.write_atomic([{"id": "a"}, {"id": "b"}])
        items = store.read()          # -> [{"id": "a"}, {"id": "b"}]
        store.write_atomic([{"id": "c"}])

    * All public methods are thread-safe (reentrant lock).
    * ``write_atomic`` writes to a ``.tmp`` sibling, then ``os.replace``.
    * On read, corrupt JSON raises ``StudioStoreError`` (never returns []).
    * Reads tolerate a UTF-8 BOM (``utf-8-sig``); the BOM is stripped on read.
    * Missing files on read return [] (first-use convention).
    * Every I/O error is surfaced explicitly — no silent ``except: pass``.
    * Unchanged files are served from a parse cache keyed on
      ``(st_mtime_ns, st_size)``, so repeated reads of a large collection
      cost one ``stat()`` instead of a full re-parse. Callers therefore MUST
      treat the returned list and its rows as read-only; ``update`` and
      ``write_atomic`` drop the cache so a mutator never edits a list that
      ``read()`` already handed out.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        # (mtime_ns, size) of the file the cache was parsed from, plus the
        # parsed rows. Both are cleared on every write path.
        self._cache_key: tuple[int, int] | None = None
        self._cache_rows: list[dict[str, Any]] | None = None

    # ── public helpers ──────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        """The underlying file path this store manages."""
        return self._path

    # ── read ─────────────────────────────────────────────────────────────

    def read(self) -> list[dict[str, Any]]:
        """Read and return the full list from the JSON file.

        Returns an empty list when the file does not exist (first use).
        The result is cached until the file's ``(mtime_ns, size)`` changes,
        so callers MUST NOT mutate the returned list or its rows.

        Raises ``StudioStoreError`` when the file contains corrupt JSON or
        the root value is not a JSON array.
        """
        with self._lock:
            return self._read_unlocked()

    # ── write (atomic) ───────────────────────────────────────────────────

    def write_atomic(self, data: list[dict[str, Any]]) -> None:
        """Atomically write *data* to the JSON file.

        The write goes to a ``.tmp`` sibling file first, then is renamed
        over the target via ``os.replace`` (atomic on POSIX and Windows
        when source and dest are on the same filesystem).

        Raises ``StudioStoreError`` on any I/O failure.  The temporary
        file is cleaned up on error.
        """
        with self._lock:
            self._write_unlocked(data)
            self._invalidate_cache()

    # ── read-modify-write ────────────────────────────────────────────────

    def update(
        self, mutator: Callable[[list[dict[str, Any]]], None]
    ) -> list[dict[str, Any]]:
        """Atomically read, mutate, and write the store under one lock.

        The *mutator* receives the full data list and should modify it in
        place.  The modified list is written back atomically and returned.

        Raises ``StudioStoreError`` on any I/O failure.
        """
        with self._lock:
            # Drop the cache BEFORE the mutator runs: it edits this list in
            # place, and read() may already have handed the cached list to
            # other callers. Re-reading also keeps a failed write from
            # leaving a mutated list in the cache.
            self._invalidate_cache()
            data = self._read_unlocked()
            mutator(data)
            self._write_unlocked(data)
            self._invalidate_cache()
            return data

    # ── private unlocked helpers (caller must hold _lock) ────────────────

    def _invalidate_cache(self) -> None:
        """Forget the parsed rows so the next read re-parses from disk."""
        self._cache_key = None
        self._cache_rows = None

    def _read_unlocked(self) -> list[dict[str, Any]]:
        """Read without acquiring the lock (caller must hold _lock)."""
        try:
            stat = self._path.stat()
        except OSError:
            # Missing (or unstattable) file: first-use empty. Never cached, so
            # a file created later is picked up on the very next read.
            self._invalidate_cache()
            return []
        cache_key = (stat.st_mtime_ns, stat.st_size)
        if self._cache_rows is not None and self._cache_key == cache_key:
            return self._cache_rows
        try:
            with open(self._path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise StudioStoreError(
                f"Corrupt JSON in {self._path}: {exc}"
            ) from exc
        except OSError as exc:
            raise StudioStoreError(
                f"Failed to read {self._path}: {exc}"
            ) from exc
        if not isinstance(data, list):
            raise StudioStoreError(
                f"Expected JSON array in {self._path}, "
                f"got {type(data).__name__}"
            )
        self._cache_key = cache_key
        self._cache_rows = data
        return data

    def _write_unlocked(self, data: list[dict[str, Any]]) -> None:
        """Write without acquiring the lock (caller must hold _lock)."""
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self._path)
        except OSError as exc:
            # Best-effort cleanup of the temp file.
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise StudioStoreError(
                f"Failed to write {self._path}: {exc}"
            ) from exc
