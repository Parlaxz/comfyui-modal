"""Generic bounded checkpoint/safetensors prewarm reader for the V2 runtime.

Purpose
-------
On request entry the V2 runtime has a window (after authoritative physical
paths are resolved at plan receipt, while unrelated setup still runs, and
before the native demand schedule begins) in which a single cooperative daemon
thread can issue a sequential, unbuffered ``readinto`` pass over the request's
checkpoint files.  That read prewarms the page/disk cache for the upcoming
demand load without retaining any payload in Python state and without touching
the demand-loading critical path.

The module is deliberately a *generic physical-path API*: it accepts absolute
physical paths to safetensors/checkpoint files and never resolves model names.
Integration (future, E13+) is responsible for resolving model names to physical
paths (e.g. ``folder_paths.get_full_path_or_raise``) before calling ``start``.

Guarantees
----------
* stdlib-only (plus the shared ``comfymodal_runtime.env`` flag parser); import
  safe on Windows and Linux.
* Default OFF: ``COMFYMODAL_V2_CHECKPOINT_PREWARM`` (absent or ``0`` -> off).
* Generic path-list API with deterministic source order and first-occurrence
  de-duplication (:func:`resolve_prewarm_paths`).
* One daemon reader thread using a single reusable buffer (exactly 8 MiB by
  default, matching ``modal_app._VOLUME_READ_CHUNK_BYTES`` at
  ``comfymodal_runtime/modal_app.py:4955``).  The explicitly enabled V2
  orchestration may opt into bounded parallel readers through the thread env.
* Unbuffered binary ``open(..., buffering=0)`` + ``readinto`` so no checkpoint
  payload is ever retained in Python state.
* Bounded: ``COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MB`` (total bytes) and
  ``COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MS`` (wall time).  ``0``/absent
  means *no bound*, which is only meaningful once the feature is explicitly
  enabled.  Invalid/negative bound values fail closed to zero (no bound).
* Fail-open: a missing/unreadable file is recorded in telemetry and skipped;
  the remaining deterministic path order is still walked, and a later demand
  load is never blocked by a prewarm failure.
* Bounded source fence: ``before_demand_load()`` stops the workers and first
  joins with ``join_timeout_ms``.  If a worker is still in a filesystem read,
  its reader-owned file descriptor is closed and all workers are given a
  separate bounded retirement window.  Demand is allowed only after every
  reader thread has physically retired; an unretireable reader reports a hard
  fence failure instead of permitting a second source reader.
* One-shot lifecycle: after the demand guard runs, ``start()`` can no longer
  start a worker.

Telemetry is truthful: ``prewarm_bytes`` / ``bytes_read_for_prewarm`` means
*bytes read by the prewarm reader*, never a claim of page residency/caching.
"""

from __future__ import annotations

import os
import queue
import threading
import time
from typing import Any, Iterable, List, Optional

try:  # import-safe: identical inline fallback keeps the module stdlib-only
    from .env import env_flag as _env_flag
except Exception:  # pragma: no cover - defensive fallback
    def _env_flag(name: str, default: bool = False) -> bool:  # type: ignore[misc]
        raw = os.environ.get(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}


_MIB = 1024 * 1024

PREWARM_FLAG = "COMFYMODAL_V2_CHECKPOINT_PREWARM"
PREWARM_MAX_MB_ENV = "COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MB"
PREWARM_MAX_MS_ENV = "COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MS"
PREWARM_JOIN_MS_ENV = "COMFYMODAL_V2_CHECKPOINT_PREWARM_JOIN_MS"
PREWARM_RETIRE_MS_ENV = "COMFYMODAL_V2_CHECKPOINT_PREWARM_RETIRE_MS"
PREWARM_THREADS_ENV = "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS"
PREWARM_CHUNK_MB_ENV = "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB"
PREWARM_SAFETY_RESERVE_MB_ENV = "COMFYMODAL_V2_CHECKPOINT_PREWARM_SAFETY_RESERVE_MB"
PREWARM_PINNED_RESERVE_MB_ENV = "COMFYMODAL_V2_CHECKPOINT_PREWARM_PINNED_RESERVE_MB"
PREWARM_RAM_FALLBACK_MB_ENV = "COMFYMODAL_V2_CHECKPOINT_PREWARM_RAM_FALLBACK_MB"

#: Storage preparation is intentionally smaller than the DMA blocks used by
#: fastsafetensors.
DEFAULT_CHUNK_BYTES = 8 * _MIB
DEFAULT_THREADS = 4
DEFAULT_SAFETY_RESERVE_BYTES = 2 * 1024 * _MIB
DEFAULT_PINNED_RESERVE_BYTES = 512 * _MIB
DEFAULT_RAM_FALLBACK_BYTES = 512 * _MIB
#: Safe default for the hard-bounded join (milliseconds).
DEFAULT_JOIN_TIMEOUT_MS = 1000
#: Upper clamp so a misconfigured join timeout can never wedge inference.
MAX_JOIN_TIMEOUT_MS = 60_000
DEFAULT_RETIREMENT_TIMEOUT_MS = 1000
MAX_RETIREMENT_TIMEOUT_MS = 60_000

_STOP_REASONS = frozenset(
    {
        "never_started",
        "disabled",
        "no_paths",
        "running",
        "completed",
        "completed_with_errors",
        "cancelled",
        "max_bytes",
        "max_wall_ms",
        "abandoned_join_timeout",
        "abandoned_guard_error",
        "retired_after_fd_close",
        "retirement_failed",
        "after_demand_guard",
    }
)


def _env_int(name: str, default: int) -> int:
    """Parse a non-negative int env var; invalid/negative fail closed to 0."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return 0
    return value if value >= 0 else 0


def _available_host_bytes() -> Optional[int]:
    """Return a conservative host-available-memory estimate."""
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return max(0, int(line.split()[1]) * 1024)
    except Exception:
        pass
    try:
        import psutil

        return max(0, int(psutil.virtual_memory().available))
    except Exception:
        return None


def _headroom_limit_bytes() -> tuple[int, Optional[int], int, int]:
    """Resolve the bounded prefetch target without retaining model payload."""
    safety = _env_int(
        PREWARM_SAFETY_RESERVE_MB_ENV,
        DEFAULT_SAFETY_RESERVE_BYTES // _MIB,
    ) * _MIB
    pinned = _env_int(
        PREWARM_PINNED_RESERVE_MB_ENV,
        DEFAULT_PINNED_RESERVE_BYTES // _MIB,
    ) * _MIB
    available = _available_host_bytes()
    if available is None:
        fallback = _env_int(
            PREWARM_RAM_FALLBACK_MB_ENV,
            DEFAULT_RAM_FALLBACK_BYTES // _MIB,
        ) * _MIB
        return max(0, fallback), None, safety, pinned
    return max(0, available - safety - pinned), available, safety, pinned


def _join_ms_from_env() -> int:
    """Resolve the dedicated join env; invalid/negative fall back to default."""
    raw = os.environ.get(PREWARM_JOIN_MS_ENV)
    if raw is None:
        return DEFAULT_JOIN_TIMEOUT_MS
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_JOIN_TIMEOUT_MS
    if value < 0:
        return DEFAULT_JOIN_TIMEOUT_MS
    return min(value, MAX_JOIN_TIMEOUT_MS)


def resolve_prewarm_paths(paths: Optional[Iterable[Any]]) -> List[str]:
    """Return a deterministic, de-duplicated physical path list.

    Order follows the source iterable; each path appears only at its first
    occurrence.  ``None``/empty entries are dropped.  Accepts ``str`` and
    ``os.PathLike`` entries.
    """
    seen = set()
    resolved: List[str] = []
    for path in paths or ():
        if path is None:
            continue
        try:
            key = os.fspath(path)
        except TypeError:
            continue
        if not isinstance(key, str):
            key = str(key)
        dedup_key = os.path.normcase(os.path.normpath(key))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        resolved.append(key)
    return resolved


def _open_for_prewarm(path: str):
    """Open *path* for an unbuffered binary sequential read.

    Module-level so tests can monkeypatch it.  ``buffering=0`` keeps payload
    out of the Python buffered-reader state; ``readinto`` into the single
    reusable buffer keeps it out of Python memory entirely.
    """
    return open(path, "rb", buffering=0)


def _maybe_fadvise(fh) -> None:
    """POSIX-only advisory sequential-read hint.

    Purely advisory per POSIX semantics (best-effort, ignored on Windows);
    nothing here claims page residency or caching, and telemetry never
    references this hint.
    """
    adv = getattr(os, "posix_fadvise", None)
    flag = getattr(os, "POSIX_FADV_SEQUENTIAL", None)
    if adv is None or flag is None:
        return
    try:
        adv(fh.fileno(), 0, 0, flag)
    except (AttributeError, OSError, ValueError, TypeError):
        pass


class CheckpointPrewarmer:
    """One cooperative daemon reader that sequentially prewarms checkpoint
    files, bounded by bytes/wall-time and a hard-bounded join.

    Lifecycle: ``start(paths)`` -> (optionally ``mark_setup_start/end``) ->
    ``before_demand_load()`` (or ``stop_and_join_before_demand()``).
    One-shot: after the demand guard runs, ``start()`` refuses to restart.
    """

    def __init__(
        self,
        *,
        enabled: Optional[bool] = None,
        max_bytes: Optional[int] = None,
        max_wall_ms: Optional[int] = None,
        chunk_bytes: Optional[int] = None,
        join_timeout_ms: Optional[int] = None,
        retirement_timeout_ms: Optional[int] = None,
        threads: Optional[int] = None,
    ):
        """Configure the prewarmer.

        ``enabled``            — None reads ``COMFYMODAL_V2_CHECKPOINT_PREWARM``
                                 (default OFF); an explicit bool overrides.
        ``max_bytes``          — None reads ``COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MB``
                                 (``0``/absent/invalid -> no bound); explicit int overrides.
        ``max_wall_ms``        — None reads ``COMFYMODAL_V2_CHECKPOINT_PREWARM_MAX_MS``
                                 (``0``/absent/invalid -> no bound); explicit int overrides.
        ``chunk_bytes``        — size of each reusable reader buffer
                                 (default exactly 8 MiB).
        ``join_timeout_ms``    — hard bound for ``before_demand_load()`` join;
                                 None reads ``COMFYMODAL_V2_CHECKPOINT_PREWARM_JOIN_MS``,
                                 default 1000 ms, clamped to 60 s.
        """
        self._enabled = _env_flag(PREWARM_FLAG, default=False) if enabled is None else bool(enabled)
        if max_bytes is None:
            max_bytes = _env_int(PREWARM_MAX_MB_ENV, 0) * _MIB
        else:
            max_bytes = max(0, int(max_bytes))
        if max_wall_ms is None:
            max_wall_ms = _env_int(PREWARM_MAX_MS_ENV, 0)
        else:
            max_wall_ms = max(0, int(max_wall_ms))
        if join_timeout_ms is None:
            join_timeout_ms = _join_ms_from_env()
        else:
            join_timeout_ms = min(max(0, int(join_timeout_ms)), MAX_JOIN_TIMEOUT_MS)
        if retirement_timeout_ms is None:
            retirement_timeout_ms = _env_int(
                PREWARM_RETIRE_MS_ENV, DEFAULT_RETIREMENT_TIMEOUT_MS
            )
        else:
            retirement_timeout_ms = max(0, int(retirement_timeout_ms))
        retirement_timeout_ms = min(retirement_timeout_ms, MAX_RETIREMENT_TIMEOUT_MS)
        if chunk_bytes is None:
            _chunk_mb = _env_int(PREWARM_CHUNK_MB_ENV, DEFAULT_CHUNK_BYTES // _MIB)
            chunk_bytes = (_chunk_mb or DEFAULT_CHUNK_BYTES // _MIB) * _MIB
        if threads is None:
            if enabled is None:
                threads = _env_int(PREWARM_THREADS_ENV, DEFAULT_THREADS) or DEFAULT_THREADS
            else:
                threads = 1
        self._max_bytes = int(max_bytes)
        self._max_wall_ms = int(max_wall_ms)
        self._chunk_bytes = max(1, int(chunk_bytes))
        self._threads = max(1, int(threads))
        self._join_timeout_ms = int(join_timeout_ms)
        self._retirement_timeout_ms = int(retirement_timeout_ms)
        (
            self._ram_allowed_bytes,
            self._ram_available_bytes,
            self._ram_safety_reserve_bytes,
            self._ram_pinned_reserve_bytes,
        ) = _headroom_limit_bytes()

        # Worker/telemetry state (mutated under ``_lock`` where shared).
        self._files: List[str] = []
        self._started = False
        self._start_at: Optional[float] = None
        self._stop_at: Optional[float] = None
        self._bytes_read = 0
        self._read_calls = 0
        self._file_stats: dict[str, dict[str, int]] = {}
        self._open_errors = 0
        self._read_errors = 0
        self._stop_reason = "never_started"
        self._join_ms: Optional[float] = None
        self._retirement_ms: Optional[float] = None
        self._retirement_result = "not_started"
        self._thread_cpu_ms: Optional[float] = None
        self._finished_before_demand: Optional[bool] = None
        self._demand_loader_start_at: Optional[float] = None
        self._demand_boundary_at: Optional[float] = None
        self._stop_requested_at: Optional[float] = None
        self._workers_alive_at_stop = 0
        self._workers_alive_after_primary_join = 0
        self._workers_alive_at_demand_start = 0
        self._source_fence_valid = True
        self._closed_handle_count = 0
        self._setup_start_at: Optional[float] = None
        self._setup_end_at: Optional[float] = None
        self._buffer: Optional[bytearray] = None
        self._thread: Optional[threading.Thread] = None
        self._workers: list[threading.Thread] = []
        self._active_handles: list[Any] = []
        self._abandoned = False
        self._demand_guard_called = False
        self._stop_event = threading.Event()
        self._finished_event = threading.Event()
        self._lock = threading.Lock()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self, paths: Optional[Iterable[Any]]) -> bool:
        """Start the single cooperative prewarm reader over *paths*.

        Returns True only when a worker thread was actually started.
        Idempotent: a second call while running, after completion, after a
        demand guard, or while disabled is a no-op returning False.
        """
        with self._lock:
            if not self._enabled:
                self._stop_reason = "disabled"
                return False
            if self._demand_guard_called:
                self._stop_reason = "after_demand_guard"
                return False
            if self._started or (self._thread is not None and self._thread.is_alive()):
                return False
            resolved = resolve_prewarm_paths(paths)
            if not resolved:
                self._stop_reason = "no_paths"
                return False
            self._files = resolved
            self._started = True
            self._start_at = time.monotonic()
            self._stop_reason = "running"
            self._stop_event.clear()
            self._finished_event.clear()
            self._workers = []
            self._active_handles = []
            self._stop_requested_at = None
            self._workers_alive_at_stop = 0
            self._workers_alive_after_primary_join = 0
            self._workers_alive_at_demand_start = 0
            self._demand_boundary_at = None
            self._retirement_ms = None
            self._retirement_result = "not_started"
            self._source_fence_valid = True
            self._closed_handle_count = 0
            self._file_stats = {
                path: {
                    "file_bytes": self._file_size(path),
                    "bytes_read_for_prewarm": 0,
                    "read_calls": 0,
                    "open_errors": 0,
                    "read_errors": 0,
                }
                for path in resolved
            }
            self._buffer = bytearray(self._chunk_bytes) if self._threads == 1 else None
            self._thread = threading.Thread(
                target=self._run_worker,
                args=(list(resolved),),
                name="checkpoint-prewarm-reader",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop_and_join_before_demand(self) -> bool:
        """Stop readers and return only after the physical source fence holds."""
        with self._lock:
            if self._demand_guard_called and self._source_fence_valid:
                return True
            thread = self._thread
            self._demand_guard_called = True
            if self._stop_requested_at is None:
                self._stop_requested_at = time.monotonic()
                self._workers_alive_at_stop = len(self._alive_threads_locked())
            self._stop_event.set()

        joined = True
        try:
            if thread is not None:
                join_start = time.monotonic()
                thread.join(timeout=max(0.0, self._join_timeout_ms / 1000.0))
                join_ms = round((time.monotonic() - join_start) * 1000.0, 3)
                with self._lock:
                    if self._join_ms is None:
                        self._join_ms = join_ms

            with self._lock:
                primary_alive = self._alive_threads_locked()
                self._workers_alive_after_primary_join = len(primary_alive)

            retirement_start = time.monotonic()
            if primary_alive:
                self._close_active_handles()
                joined = self._join_threads_until(
                    retirement_start + self._retirement_timeout_ms / 1000.0
                )
            with self._lock:
                remaining = self._alive_threads_locked()
                self._workers_alive_at_demand_start = len(remaining)
                self._retirement_ms = round(
                    (time.monotonic() - (self._stop_requested_at or retirement_start))
                    * 1000.0,
                    3,
                )
                if remaining:
                    joined = False
                    self._source_fence_valid = False
                    self._abandoned = True
                    self._stop_reason = "retirement_failed"
                    self._retirement_result = "retirement_failed"
                elif primary_alive:
                    self._source_fence_valid = True
                    self._retirement_result = "retired_after_fd_close"
                else:
                    self._source_fence_valid = True
                    self._retirement_result = (
                        "joined_primary" if thread is not None else "not_started"
                    )
                self._buffer = None
                self._finished_before_demand = joined
                self._demand_boundary_at = time.monotonic()
                if joined and self._demand_loader_start_at is None:
                    self._demand_loader_start_at = time.monotonic()
                if not joined:
                    self._finished_event.set()
        except Exception:
            joined = False
            with self._lock:
                self._source_fence_valid = False
                self._abandoned = True
                self._stop_reason = "abandoned_guard_error"
                self._retirement_result = "guard_error"
                self._workers_alive_at_demand_start = len(self._alive_threads_locked())
                self._buffer = None
                self._finished_before_demand = False
                self._demand_boundary_at = time.monotonic()
                self._finished_event.set()
        return joined

    def before_demand_load(self) -> bool:
        """Demand-loader guard: stop/join (or abandon) before returning.

        Call this immediately before the demand loader begins.  A false return
        is a structural source-fence failure; callers must not start another
        source reader.
        """
        return self.stop_and_join_before_demand()

    # ── Unrelated-setup window (for overlap telemetry) ──────────────────────

    def mark_setup_start(self) -> None:
        """Record the start of the unrelated-setup window."""
        with self._lock:
            if self._setup_start_at is None:
                self._setup_start_at = time.monotonic()

    def mark_setup_end(self) -> None:
        """Close the unrelated-setup window."""
        with self._lock:
            self._setup_end_at = time.monotonic()

    # ── Worker ───────────────────────────────────────────────────────────────

    def _alive_threads_locked(self) -> list[threading.Thread]:
        threads: list[threading.Thread] = []
        if self._thread is not None and self._thread.is_alive():
            threads.append(self._thread)
        threads.extend(worker for worker in self._workers if worker.is_alive())
        return threads

    def _join_threads_until(self, deadline: float) -> bool:
        while True:
            with self._lock:
                alive = self._alive_threads_locked()
            if not alive:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            for worker in alive:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                worker.join(timeout=min(0.05, remaining))

    def _register_handle(self, handle: Any) -> bool:
        with self._lock:
            close_now = self._stop_event.is_set()
            if not close_now:
                self._active_handles.append(handle)
        if close_now:
            try:
                handle.close()
            except Exception:
                pass
            return False
        return True

    def _unregister_handle(self, handle: Any) -> None:
        with self._lock:
            for index, active in enumerate(self._active_handles):
                if active is handle:
                    self._active_handles.pop(index)
                    break

    def _close_active_handles(self) -> None:
        with self._lock:
            handles = list(self._active_handles)
            self._active_handles.clear()
        closed = 0
        for handle in handles:
            try:
                handle.close()
                closed += 1
            except Exception:
                pass
        with self._lock:
            self._closed_handle_count += closed

    @staticmethod
    def _thread_time_s() -> Optional[float]:
        try:
            return time.thread_time()
        except (AttributeError, OSError, ValueError):
            return None

    @staticmethod
    def _file_size(path: str) -> int:
        try:
            return max(0, int(os.path.getsize(path)))
        except Exception:
            return 0

    def _read_limit(self) -> int:
        limit = self._ram_allowed_bytes
        if self._max_bytes > 0:
            limit = min(limit, self._max_bytes)
        return max(0, int(limit))

    def _record_read(self, path: str, count: int, *, calls: int = 1) -> None:
        with self._lock:
            self._bytes_read += max(0, int(count))
            self._read_calls += max(0, int(calls))
            stats = self._file_stats.setdefault(path, {
                "file_bytes": self._file_size(path),
                "bytes_read_for_prewarm": 0,
                "read_calls": 0,
                "open_errors": 0,
                "read_errors": 0,
            })
            stats["bytes_read_for_prewarm"] += max(0, int(count))
            stats["read_calls"] += max(0, int(calls))

    def _record_error(self, path: str, kind: str) -> None:
        with self._lock:
            if kind == "open":
                self._open_errors += 1
            else:
                self._read_errors += 1
            stats = self._file_stats.setdefault(path, {
                "file_bytes": self._file_size(path),
                "bytes_read_for_prewarm": 0,
                "read_calls": 0,
                "open_errors": 0,
                "read_errors": 0,
            })
            stats[f"{kind}_errors"] += 1

    def _read_range(
        self,
        path: str,
        offset: int,
        length: int,
        wall_start: float,
    ) -> str:
        if length <= 0:
            return "completed"
        if self._stop_event.is_set():
            return "cancelled"
        fh = None
        try:
            fh = _open_for_prewarm(path)
            if not self._register_handle(fh):
                return "cancelled"
            _maybe_fadvise(fh)
            if offset:
                fh.seek(offset)
            remaining = int(length)
            buffer = bytearray(min(self._chunk_bytes, remaining))
            while remaining > 0:
                if self._stop_event.is_set():
                    return "cancelled"
                if self._max_wall_ms > 0 and (
                    time.monotonic() - wall_start
                ) * 1000.0 >= self._max_wall_ms:
                    return "max_wall_ms"
                target = memoryview(buffer)[:min(len(buffer), remaining)]
                try:
                    count = fh.readinto(target)
                except Exception:
                    self._record_error(path, "read")
                    return "completed_with_errors"
                self._record_read(path, int(count or 0))
                if not count:
                    return "completed_with_errors"
                remaining -= int(count)
            return "completed"
        except Exception:
            self._record_error(path, "open")
            return "completed_with_errors"
        finally:
            if fh is not None:
                self._unregister_handle(fh)
                try:
                    fh.close()
                except Exception:
                    pass

    def _run_single(self, paths: List[str], wall_start: float) -> str:
        buffer = self._buffer if self._buffer is not None else bytearray(self._chunk_bytes)
        reason = "completed"
        for path in paths:
            if self._stop_event.is_set():
                return "cancelled"
            fh = None
            try:
                fh = _open_for_prewarm(path)
                if not self._register_handle(fh):
                    return "cancelled"
                _maybe_fadvise(fh)
                while True:
                    if self._stop_event.is_set():
                        return "cancelled"
                    if self._max_wall_ms > 0 and (
                        time.monotonic() - wall_start
                    ) * 1000.0 >= self._max_wall_ms:
                        return "max_wall_ms"
                    read_target = buffer
                    limit = self._read_limit()
                    with self._lock:
                        remaining_limit = limit - self._bytes_read
                    if remaining_limit <= 0:
                        return "max_bytes"
                    read_target = memoryview(buffer)[:min(len(buffer), remaining_limit)]
                    try:
                        count = fh.readinto(read_target)
                    except Exception:
                        self._record_error(path, "read")
                        reason = "completed_with_errors"
                        break
                    self._record_read(path, int(count or 0))
                    if not count:
                        break
            except Exception:
                self._record_error(path, "open")
                reason = "completed_with_errors"
            finally:
                if fh is not None:
                    self._unregister_handle(fh)
                    try:
                        fh.close()
                    except Exception:
                        pass
            if reason in ("max_bytes", "max_wall_ms", "cancelled"):
                return reason
        return reason

    def _run_parallel(self, paths: List[str], wall_start: float) -> str:
        limit = self._read_limit()
        jobs: queue.Queue[tuple[str, int, int]] = queue.Queue()
        remaining = limit
        for path in paths:
            if remaining <= 0:
                break
            size = self._file_stats.get(path, {}).get("file_bytes", 0) or 0
            if size <= 0:
                # A failed stat must still exercise the opener so missing or
                # unreadable paths remain visible in fail-open telemetry.
                if not os.path.isfile(path):
                    jobs.put((path, 0, self._chunk_bytes))
                continue
            budget = min(size, remaining)
            offset = 0
            while offset < budget:
                length = min(self._chunk_bytes, budget - offset)
                jobs.put((path, offset, length))
                offset += length
            remaining -= budget
        for index in range(min(self._threads, max(1, jobs.qsize()))):
            worker = threading.Thread(
                target=self._parallel_worker,
                args=(jobs, wall_start),
                name=f"checkpoint-prewarm-reader-{index}",
                daemon=True,
            )
            with self._lock:
                self._workers.append(worker)
            worker.start()
        # Keep the supervisor alive until every source worker has retired.  A
        # demand guard can close active handles from another thread if this
        # wait exceeds its primary bound.
        for worker in list(self._workers):
            while worker.is_alive():
                worker.join(timeout=0.05)
        if self._stop_event.is_set():
            if self._max_wall_ms > 0 and (
                time.monotonic() - wall_start
            ) * 1000.0 >= self._max_wall_ms:
                return "max_wall_ms"
            return "cancelled"
        if self._bytes_read >= limit and limit > 0:
            return "max_bytes"
        return "completed_with_errors" if self._open_errors or self._read_errors else "completed"

    def _parallel_worker(self, jobs: queue.Queue, wall_start: float) -> None:
        while not self._stop_event.is_set():
            try:
                path, offset, length = jobs.get_nowait()
            except queue.Empty:
                return
            try:
                reason = self._read_range(path, offset, length, wall_start)
                if reason in ("cancelled", "max_wall_ms", "completed_with_errors"):
                    if reason == "max_wall_ms":
                        self._stop_event.set()
                    elif reason == "cancelled":
                        self._stop_event.set()
            finally:
                jobs.task_done()

    def _run_worker(self, paths: List[str]) -> None:
        cpu_start = self._thread_time_s()
        wall_start = time.monotonic()
        reason = "completed"
        try:
            if self._threads == 1:
                reason = self._run_single(paths, wall_start)
            else:
                reason = self._run_parallel(paths, wall_start)
        finally:
            stop_at = time.monotonic()
            thread_cpu_ms = None
            if cpu_start is not None:
                try:
                    thread_cpu_ms = round((time.thread_time() - cpu_start) * 1000.0, 3)
                except (AttributeError, OSError, ValueError):
                    thread_cpu_ms = None
            with self._lock:
                self._stop_at = stop_at
                self._thread_cpu_ms = thread_cpu_ms
                if not self._abandoned:
                    self._stop_reason = reason
                self._buffer = None
                self._finished_event.set()

    # ── Telemetry ────────────────────────────────────────────────────────────

    def _wall_ms(self, now: float) -> float:
        if not self._started or self._start_at is None:
            return 0.0
        end = self._stop_at if self._stop_at is not None else now
        return round(max(0.0, (end - self._start_at) * 1000.0), 3)

    def _overlap_setup_ms(self, now: float) -> float:
        if self._setup_start_at is None or self._start_at is None:
            return 0.0
        setup_end = self._setup_end_at if self._setup_end_at is not None else now
        prewarm_end = self._stop_at if self._stop_at is not None else now
        lo = max(self._setup_start_at, self._start_at)
        hi = min(setup_end, prewarm_end)
        if hi <= lo:
            return 0.0
        return round((hi - lo) * 1000.0, 3)

    def as_dict(self) -> dict[str, Any]:
        """Truthful telemetry snapshot.

        ``prewarm_bytes``/``bytes_read_for_prewarm`` = bytes *read by the
        prewarm reader* — never a residency/cache claim.  Timestamps are
        ``time.monotonic`` seconds.
        """
        with self._lock:
            now = time.monotonic()
            total_file_bytes = sum(
                int(stats.get("file_bytes", 0) or 0)
                for stats in self._file_stats.values()
            )
            fraction = (
                float(self._bytes_read) / float(total_file_bytes)
                if total_file_bytes > 0 else 0.0
            )
            file_details = []
            for path in self._files:
                stats = dict(self._file_stats.get(path, {}))
                file_bytes = int(stats.get("file_bytes", 0) or 0)
                bytes_read = int(stats.get("bytes_read_for_prewarm", 0) or 0)
                file_details.append({
                    "path": path,
                    "file_bytes": file_bytes,
                    "bytes_read_for_prewarm": bytes_read,
                    "fraction_read": (
                        round(bytes_read / file_bytes, 6) if file_bytes > 0 else 0.0
                    ),
                    "read_calls": int(stats.get("read_calls", 0) or 0),
                    "open_errors": int(stats.get("open_errors", 0) or 0),
                    "read_errors": int(stats.get("read_errors", 0) or 0),
                })
            return {
                "prewarm_enabled": bool(self._enabled),
                "prewarm_started": bool(self._started),
                "prewarm_start_at": self._start_at,
                "prewarm_stop_at": self._stop_at,
                "prewarm_files": list(self._files),
                "prewarm_file_count": int(len(self._files)),
                "prewarm_bytes": int(self._bytes_read),
                "prewarm_fraction": round(fraction, 6),
                "prewarm_file_details": file_details,
                "prewarm_read_calls": int(self._read_calls),
                "prewarm_wall_ms": self._wall_ms(now),
                "prewarm_thread_cpu_ms": self._thread_cpu_ms,
                "prewarm_stop_reason": str(self._stop_reason),
                "prewarm_join_ms": self._join_ms,
                "prefetch_stop_requested_at": self._stop_requested_at,
                "prefetch_workers_alive_at_stop": int(self._workers_alive_at_stop),
                "prefetch_workers_alive_after_primary_join": int(
                    self._workers_alive_after_primary_join
                ),
                "prefetch_workers_alive_at_demand_start": int(
                    self._workers_alive_at_demand_start
                ),
                "prefetch_retirement_ms": self._retirement_ms,
                "prefetch_retirement_result": str(self._retirement_result),
                "prefetch_demand_boundary_at": self._demand_boundary_at,
                "source_fence_valid": bool(
                    self._source_fence_valid and not self._alive_threads_locked()
                ),
                "prefetch_active_handles": int(len(self._active_handles)),
                "prefetch_closed_handle_count": int(self._closed_handle_count),
                "prewarm_overlap_with_setup_ms": self._overlap_setup_ms(now),
                "demand_loader_start_at": self._demand_loader_start_at,
                "prewarm_finished_before_demand": self._finished_before_demand,
                # Truthful alias for ``prewarm_bytes`` (same value).
                "bytes_read_for_prewarm": int(self._bytes_read),
                # Configured bounds (diagnostic).
                "prewarm_max_bytes": int(self._max_bytes),
                "prewarm_max_wall_ms": int(self._max_wall_ms),
                "prewarm_join_timeout_ms": int(self._join_timeout_ms),
                "prewarm_chunk_bytes": int(self._chunk_bytes),
                "prewarm_threads": int(self._threads),
                "prewarm_total_file_bytes": int(total_file_bytes),
                "prewarm_ram_headroom_bound_bytes": int(self._ram_allowed_bytes),
                "prewarm_ram_available_bytes": self._ram_available_bytes,
                "prewarm_ram_safety_reserve_bytes": int(self._ram_safety_reserve_bytes),
                "prewarm_ram_pinned_reserve_bytes": int(self._ram_pinned_reserve_bytes),
                "prewarm_effective_max_bytes": int(self._read_limit()),
                "prewarm_open_errors": int(self._open_errors),
                "prewarm_read_errors": int(self._read_errors),
            }


__all__ = [
    "CheckpointPrewarmer",
    "resolve_prewarm_paths",
    "PREWARM_FLAG",
    "PREWARM_MAX_MB_ENV",
    "PREWARM_MAX_MS_ENV",
    "PREWARM_JOIN_MS_ENV",
    "PREWARM_RETIRE_MS_ENV",
    "PREWARM_THREADS_ENV",
    "PREWARM_CHUNK_MB_ENV",
    "PREWARM_SAFETY_RESERVE_MB_ENV",
    "PREWARM_PINNED_RESERVE_MB_ENV",
    "PREWARM_RAM_FALLBACK_MB_ENV",
    "DEFAULT_CHUNK_BYTES",
    "DEFAULT_THREADS",
    "DEFAULT_JOIN_TIMEOUT_MS",
    "DEFAULT_RETIREMENT_TIMEOUT_MS",
]
