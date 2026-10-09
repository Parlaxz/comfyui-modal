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
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        self._cache_signature: tuple[int, int] | None = None
        self._cache_data: list[dict[str, Any]] | None = None

    # ── public helpers ──────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        """The underlying file path this store manages."""
        return self._path

    # ── read ─────────────────────────────────────────────────────────────

    def read(self) -> list[dict[str, Any]]:
        """Read and return the full list from the JSON file.

        Returns an empty list when the file does not exist (first use).

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
            # Do not mutate a list previously handed to a read() caller.
            data = self._read_unlocked(use_cache=False)
            mutator(data)
            self._write_unlocked(data)
            self._invalidate_cache()
            return data

    # ── private unlocked helpers (caller must hold _lock) ────────────────

    def _read_unlocked(self, *, use_cache: bool = True) -> list[dict[str, Any]]:
        """Read without acquiring the lock (caller must hold _lock)."""
        if not use_cache:
            self._invalidate_cache()
        try:
            stat = self._path.stat()
        except FileNotFoundError:
            self._invalidate_cache()
            return []
        except OSError as exc:
            raise StudioStoreError(
                f"Failed to stat {self._path}: {exc}"
            ) from exc
        signature = (stat.st_mtime_ns, stat.st_size)
        if (
            use_cache
            and self._cache_signature == signature
            and self._cache_data is not None
        ):
            return self._cache_data
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
        if use_cache:
            self._cache_signature = signature
            self._cache_data = data
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
            self._invalidate_cache()
        except OSError as exc:
            # Best-effort cleanup of the temp file.
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise StudioStoreError(
                f"Failed to write {self._path}: {exc}"
            ) from exc

    def _invalidate_cache(self) -> None:
        """Drop parsed rows after this store changes its file."""
        self._cache_signature = None
        self._cache_data = None
