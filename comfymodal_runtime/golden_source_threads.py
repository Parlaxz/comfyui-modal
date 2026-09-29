"""CUDA-sterile C0 source process with four persistent reader threads.

This module intentionally has a standard-library-only import surface.  The
parent owns the CUDA-registered arena; this process only attaches to its POSIX
backing and writes bytes into generation-tagged slots.  A model is described by
one plan message.  There is no per-range command and the source workers claim
both ranges and slots from the bounded shared control block.

The control block is deliberately explicit rather than relying on Python
objects shared by fork.  A lock file (``flock``) serializes all ownership
transitions.  The parent releases a slot only after its CUDA dispatcher has
proved the copy complete.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import mmap as _mmap
import os
import select
import struct
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from multiprocessing import shared_memory
from typing import Any, Iterable, Mapping, Sequence

if os.name == "posix":
    import fcntl as _fcntl
else:  # pragma: no cover - the runtime arm is deliberately POSIX-only.
    _fcntl = None


EXPERIMENT_ENV = "COMFYMODAL_GOLDEN_C0_SOURCE_THREADS"
ARENA_BYTES = 8 * 64 * 1024 * 1024
SLOT_COUNT = 8
SLOT_BYTES = 64 * 1024 * 1024
THREAD_COUNT = 4
PACER_GAP_NS = 4_000_000
CONTROL_BYTES = 512 * 1024
CONTROL_MAGIC = b"C0STHRD1"
CONTROL_VERSION = 1
HEADER = struct.Struct("<8sIIIIQQQQQQ")
SLOT = struct.Struct("<IIQQQQQQ")
# Fixed-size raw operation records.  The source process writes these records
# into the control segment; JSON is produced only when the parent asks for
# evidence after the measured work has drained.
OP = struct.Struct("<18Q")
OP_FIELDS = (
    "generation", "reader_id", "thread_id", "slot_index", "ordinal",
    "source_offset", "nbytes", "source_start_ns", "map_start_ns",
    "access_start_ns", "memcpy_start_ns", "memcpy_end_ns", "munmap_start_ns",
    "munmap_end_ns", "slot_wait_ns", "pacing_wait_ns", "ready_ns", "flags",
)
HEADER_SIZE = 128
SLOT_OFFSET = HEADER_SIZE
OP_OFFSET = SLOT_OFFSET + SLOT_COUNT * SLOT.size
MAX_OPS = (CONTROL_BYTES - OP_OFFSET) // OP.size
COUNTER_OFFSET = HEADER.size
COUNTERS = struct.Struct("<QQQQQQQ")

FREE = 0
FILLING = 1
READY = 2
IN_FLIGHT = 3
FAILED = 4


class SourceProtocolError(RuntimeError):
    """A source protocol or identity violation; callers must fail closed."""


def enabled(value: Any = None) -> bool:
    selected = os.environ.get(EXPERIMENT_ENV) if value is None else value
    return str(selected or "").strip().lower() in {"1", "true", "yes", "on"}


def geometry() -> dict[str, int]:
    return {
        "arena_bytes": ARENA_BYTES,
        "slot_count": SLOT_COUNT,
        "slot_bytes": SLOT_BYTES,
        "thread_count": THREAD_COUNT,
        "pacer_gap_ns": PACER_GAP_NS,
    }


def _identity(path: str) -> tuple[int, int, int, int]:
    stat = os.stat(path)
    return (int(stat.st_dev), int(stat.st_ino), int(stat.st_size), int(stat.st_mtime_ns))


def _validate_identity(path: str, expected: Sequence[int] | None) -> tuple[int, int, int, int]:
    actual = _identity(path)
    if expected is not None and tuple(int(x) for x in expected) != actual:
        raise SourceProtocolError(f"source_identity_changed:{actual!r}!={tuple(expected)!r}")
    return actual


@dataclass(frozen=True)
class SourceRange:
    source_offset: int
    length: int
    destination_offset: int
    record_id: str | int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_offset": self.source_offset,
            "length": self.length,
            "destination_offset": self.destination_offset,
            "record_id": self.record_id,
        }


@dataclass(frozen=True)
class ReadyRecord:
    slot_index: int
    generation: int
    source_offset: int
    destination_offset: int
    nbytes: int
    range_index: int
    producer_id: int
    ready_ns: int
    record_id: str | int | None = None
    plan_generation: int | None = None

    @property
    def slot_generation(self) -> int:
        """The historical ``generation`` field is the slot generation."""
        return self.generation


def validate_plan(
    ranges: Iterable[SourceRange], *, source_size: int, destination_size: int
) -> tuple[SourceRange, ...]:
    planned = tuple(ranges)
    if not planned and destination_size != 0:
        raise SourceProtocolError("empty_plan_does_not_cover_destination")
    ordered_source = sorted(planned, key=lambda item: item.source_offset)
    ordered_dest = sorted(planned, key=lambda item: item.destination_offset)
    cursor = 0
    ids: set[str | int] = set()
    for item in ordered_source:
        if item.length <= 0 or item.length > SLOT_BYTES:
            raise SourceProtocolError("range_length_out_of_bounds")
        if item.source_offset < 0 or item.source_offset + item.length > source_size:
            raise SourceProtocolError("source_range_out_of_bounds")
        if item.record_id is not None and item.record_id in ids:
            raise SourceProtocolError("duplicate_record_id")
        if item.record_id is not None:
            ids.add(item.record_id)
    for item in ordered_dest:
        if item.destination_offset != cursor:
            raise SourceProtocolError("destination_coverage_gap_or_overlap")
        cursor += item.length
    if cursor != destination_size:
        raise SourceProtocolError("destination_coverage_incomplete")
    for left, right in zip(ordered_source, ordered_source[1:]):
        if left.source_offset + left.length > right.source_offset:
            raise SourceProtocolError("source_coverage_overlap")
    return planned


class GlobalSourcePacer:
    """One locked 4 ms reservation clock shared by all source threads."""

    def __init__(self, *, gap_ns: int = PACER_GAP_NS, clock: Any = time.monotonic_ns,
                 sleeper: Any = time.sleep):
        if int(gap_ns) <= 0:
            raise ValueError("pacer_gap_must_be_positive")
        self.gap_ns = int(gap_ns)
        self._clock = clock
        self._sleep = sleeper
        self._lock = threading.Lock()
        self.last_start_ns: int | None = None
        self.timestamps_ns: list[int] = []
        self.actual_timestamps_ns: list[int] = []
        self.wait_ns: list[int] = []
        self.zero_delay_count = 0

    def reserve(self, *, now_ns: int | None = None) -> tuple[int, int]:
        """Reserve and return ``(actual_start_ns, wait_ns)``.

        ``now_ns`` is a deterministic test seam.  Production callers omit it;
        the operation boundary is the timestamp immediately before mapped
        access/memcpy begins.
        """
        with self._lock:
            waited = 0
            while True:
                now = int(self._clock() if now_ns is None else now_ns)
                target = now if self.last_start_ns is None else max(now, self.last_start_ns + self.gap_ns)
                if target > now:
                    if now_ns is not None:
                        # A supplied clock is a proof/test seam, not a request
                        # to sleep real time.  Return the reserved boundary.
                        now = target
                    else:
                        delay = target - now
                        waited += delay
                        self._sleep(delay / 1e9)
                        continue
                start = int(now if now >= target else target)
                if self.last_start_ns is not None and start - self.last_start_ns < self.gap_ns:
                    raise SourceProtocolError("pacer_start_gap_violation")
                self.last_start_ns = start
                self.timestamps_ns.append(start)
                self.wait_ns.append(waited)
                if waited == 0:
                    self.zero_delay_count += 1
                return start, waited

    def telemetry(self) -> dict[str, Any]:
        gaps = [right - left for left, right in zip(self.timestamps_ns, self.timestamps_ns[1:])]
        return {
            "pacer_gap_ns": self.gap_ns,
            "source_start_timestamps_ns": list(self.timestamps_ns),
            "pacing_wait_ns": list(self.wait_ns),
            "pacing_wait_count": sum(1 for value in self.wait_ns if value > 0),
            "pacing_zero_delay_count": self.zero_delay_count,
            "min_source_gap_ns": min(gaps) if gaps else None,
            "source_gap_violation_count": sum(1 for value in gaps if value < self.gap_ns),
            "pacer_boundary": "mapped_access_plus_memcpy_start",
        }

    def paced_copy(self, callback: Any, *, reader_id: int, ordinal: int) -> tuple[int, int, int]:
        """Pace and validate the actual copy-start boundary.

        The reservation lock covers only pacing state.  The native copy itself
        runs concurrently in the four reader threads.  ``callback`` receives a
        one-shot marker callable and must invoke it immediately before entering
        the native copy; the marker validates the real observed start order and
        fails closed if scheduling ever creates a sub-4 ms gap.
        """
        with self._lock:
            waited = 0
            while True:
                now = int(self._clock())
                target = now if self.last_start_ns is None else max(now, self.last_start_ns + self.gap_ns)
                if target <= now:
                    break
                delay = target - now
                waited += delay
                self._sleep(delay / 1e9)
            access_start = int(self._clock())

        def mark_actual_start() -> int:
            actual = int(self._clock())
            with self._lock:
                previous_actual = self.actual_timestamps_ns[-1] if self.actual_timestamps_ns else None
                if previous_actual is not None and actual - previous_actual < self.gap_ns:
                    raise SourceProtocolError(
                        f"pacer_memcpy_gap_violation:reader={reader_id}:ordinal={ordinal}:"
                        f"previous={previous_actual}:current={actual}"
                    )
                self.actual_timestamps_ns.append(actual)
                self.timestamps_ns.append(actual)
                self.wait_ns.append(waited)
                if waited == 0:
                    self.zero_delay_count += 1
            return actual

        result = callback(mark_actual_start)
        memcpy_start = int(result if result is not None else self._clock())
        return access_start, memcpy_start, waited


class _FileLock:
    def __init__(self, path: str):
        self._file = open(path, "a+b", buffering=0)
        self._thread_lock = threading.Lock()

    def __enter__(self):
        if _fcntl is None:
            raise SourceProtocolError("source_lock_requires_posix")
        self._thread_lock.acquire()
        _fcntl.flock(self._file.fileno(), _fcntl.LOCK_EX)
        return self

    def __exit__(self, *_args):
        if _fcntl is not None:
            _fcntl.flock(self._file.fileno(), _fcntl.LOCK_UN)
        self._thread_lock.release()

    def close(self) -> None:
        self._file.close()


def _read_header(buf: memoryview) -> tuple[Any, ...]:
    values = HEADER.unpack_from(buf, 0)
    if values[0] != CONTROL_MAGIC or values[1] != CONTROL_VERSION:
        raise SourceProtocolError("control_header_invalid")
    if values[2:5] != (SLOT_COUNT, SLOT_BYTES, ARENA_BYTES):
        raise SourceProtocolError("control_geometry_invalid")
    return values


def _write_header(buf: memoryview, *, generation: int, plan_count: int, next_range: int,
                  ready_count: int, completed_count: int, failed_count: int) -> None:
    HEADER.pack_into(
        buf, 0, CONTROL_MAGIC, CONTROL_VERSION, SLOT_COUNT, SLOT_BYTES, ARENA_BYTES,
        int(generation), int(plan_count), int(next_range), int(ready_count),
        int(completed_count), int(failed_count),
    )


def _slot(buf: memoryview, index: int) -> tuple[Any, ...]:
    if not 0 <= index < SLOT_COUNT:
        raise SourceProtocolError("slot_index_out_of_bounds")
    return SLOT.unpack_from(buf, SLOT_OFFSET + index * SLOT.size)


def _put_slot(buf: memoryview, index: int, values: Sequence[int]) -> None:
    SLOT.pack_into(buf, SLOT_OFFSET + index * SLOT.size, *values)


def _bump_counter(buf: memoryview, index: int, amount: int = 1) -> None:
    values = list(COUNTERS.unpack_from(buf, COUNTER_OFFSET))
    values[index] += int(amount)
    COUNTERS.pack_into(buf, COUNTER_OFFSET, *values)


def _time_weighted_concurrency(operations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize mapped-copy concurrency over the complete source span."""
    intervals = [
        (
            int(item.get("memcpy_start_ns") or 0),
            int(item.get("memcpy_end_ns") or 0),
            int(item.get("reader_id") or 0),
        )
        for item in operations
        if int(item.get("memcpy_end_ns") or 0) > int(item.get("memcpy_start_ns") or 0)
    ]
    if not intervals:
        return {
            "source_span_ns": 0,
            "levels": {str(level): {"ns": 0, "fraction": None} for level in range(THREAD_COUNT + 1)},
            "effective_concurrency": None,
            "longest_zero_reader_ns": 0,
            "longest_at_most_one_reader_ns": 0,
            "below_four_reader_ns": 0,
        }
    points = sorted({point for start, end, _reader in intervals for point in (start, end)})
    buckets = [0] * (THREAD_COUNT + 1)
    longest_zero = 0
    longest_at_most_one = 0
    for left, right in zip(points, points[1:]):
        active = {
            reader for start, end, reader in intervals if start <= left and end >= right
        }
        duration = max(0, right - left)
        level = min(THREAD_COUNT, len(active))
        buckets[level] += duration
        if level == 0:
            longest_zero = max(longest_zero, duration)
        if level <= 1:
            longest_at_most_one = max(longest_at_most_one, duration)
    span = max(0, points[-1] - points[0])
    return {
        "source_span_ns": span,
        "levels": {
            str(level): {"ns": value, "fraction": (value / span if span else None)}
            for level, value in enumerate(buckets)
        },
        "effective_concurrency": (
            sum(end - start for start, end, _reader in intervals) / span if span else None
        ),
        "longest_zero_reader_ns": longest_zero,
        "longest_at_most_one_reader_ns": longest_at_most_one,
        "below_four_reader_ns": sum(buckets[:THREAD_COUNT]),
    }


def _validate_memcpy_gaps(operations: Sequence[Mapping[str, Any]]) -> None:
    starts = sorted(
        (int(item["memcpy_start_ns"]), int(item.get("reader_id") or 0), int(item.get("ordinal") or 0))
        for item in operations if int(item.get("memcpy_start_ns") or 0)
    )
    for previous, current in zip(starts, starts[1:]):
        gap = current[0] - previous[0]
        if gap < PACER_GAP_NS:
            raise SourceProtocolError(
                f"pacer_memcpy_gap_violation:reader={current[1]}:ordinal={current[2]}:"
                f"previous={previous[0]}:current={current[0]}:gap={gap}"
            )


class SourceThreadProcess:
    """Parent-side owner of one source process and its shared control block."""

    def __init__(self, arena_name: str, *, lock_path: str | None = None,
                 mmap_lifecycle: str = "fresh"):
        if os.name != "posix":
            raise SourceProtocolError("source_thread_process_requires_posix")
        self.arena_name = str(arena_name)
        self.mmap_lifecycle = str(mmap_lifecycle).strip().lower()
        if self.mmap_lifecycle not in {"fresh", "whole"}:
            raise SourceProtocolError("unsupported_mmap_lifecycle")
        self.control = shared_memory.SharedMemory(create=True, size=CONTROL_BYTES)
        self.control.buf[:] = b"\0" * CONTROL_BYTES
        _write_header(self.control.buf, generation=0, plan_count=0, next_range=0,
                      ready_count=0, completed_count=0, failed_count=0)
        COUNTERS.pack_into(self.control.buf, COUNTER_OFFSET, 0, 0, 0, 0, 0, 0, 0)
        self._lock_path_owned = lock_path is None
        if lock_path is None:
            fd, lock_path = tempfile.mkstemp(prefix="comfymodal-c0-source-", suffix=".lock")
            os.close(fd)
        self.lock_path = str(lock_path)
        self._lock = _FileLock(self.lock_path)
        self._proc: subprocess.Popen[str] | None = None
        self._planned_generation: int | None = None
        self._planned_records: dict[tuple[int, int], str | int | None] = {}
        self._plan_count = 0
        self._stopped = False
        self.telemetry: dict[str, Any] = {
            "architecture": "one_process_four_threads",
            "arena_bytes": ARENA_BYTES,
            "slot_count": SLOT_COUNT,
            "slot_bytes": SLOT_BYTES,
            "thread_count": THREAD_COUNT,
            "pacer_boundary": "mapped_access_plus_memcpy_start",
            "mmap_lifecycle": self.mmap_lifecycle,
            "fallback": False,
            "effective_reader_concurrency": 0,
        }

    @property
    def process(self) -> subprocess.Popen[str] | None:
        return self._proc

    def start(self, timeout_s: float = 30.0) -> dict[str, Any]:
        if self._proc is not None:
            raise SourceProtocolError("source_process_already_started")
        self._proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--source-child",
             self.arena_name, self.control.name, self.lock_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, close_fds=True,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": ""},
        )
        assert self._proc.stdout is not None
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self._proc.stdout], [], [], max(0.0, deadline - time.monotonic()))
            if not ready:
                break
            line = self._proc.stdout.readline()
            if not line:
                break
            msg = json.loads(line)
            if msg.get("op") == "READY":
                if msg.get("geometry") != geometry():
                    raise SourceProtocolError("source_ready_geometry_mismatch")
                self.telemetry.update(msg.get("telemetry") or {})
                return msg
            if msg.get("op") == "fatal":
                raise SourceProtocolError(str(msg.get("error")))
        raise SourceProtocolError("source_process_ready_timeout")

    def plan_once(
        self, *, generation: int, path: str, identity: Sequence[int],
        ranges: Sequence[SourceRange], destination_size: int,
        mmap_lifecycle: str | None = None,
    ) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise SourceProtocolError("source_process_not_started")
        if self._planned_generation == int(generation):
            raise SourceProtocolError("source_plan_published_twice")
        if self._planned_generation is not None:
            with self._lock:
                header = _read_header(self.control.buf)
                if any(_slot(self.control.buf, i)[0] != FREE for i in range(SLOT_COUNT)):
                    raise SourceProtocolError("source_previous_plan_not_quiescent")
                if header[7] < int(self.telemetry.get("plan_range_count", 0)):
                    raise SourceProtocolError("source_previous_plan_not_complete")
        actual = _validate_identity(path, identity)
        if tuple(int(x) for x in identity) != actual:
            raise SourceProtocolError("source_identity_mismatch")
        planned = validate_plan(ranges, source_size=actual[2], destination_size=destination_size)
        lifecycle = str(mmap_lifecycle or self.mmap_lifecycle).strip().lower()
        if lifecycle not in {"fresh", "whole"}:
            raise SourceProtocolError("unsupported_mmap_lifecycle")
        with self._lock:
            # The parent never resets visible worker state.  The child owns
            # the PLAN install/ack transaction and resets slots exactly once
            # after the old generation has stopped.
            _read_header(self.control.buf)
        message = {
            "op": "PLAN", "generation": int(generation), "path": os.path.abspath(path),
            "identity": list(identity), "destination_size": int(destination_size),
            "mmap_lifecycle": lifecycle,
            "ranges": [item.as_dict() for item in planned],
        }
        self._proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self._proc.stdin.flush()
        # PLAN is not considered installed until the child has stopped the
        # previous generation, atomically installed this one, and acknowledged
        # it.  This closes the old-worker/new-generation race.
        assert self._proc.stdout is not None
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self._proc.stdout], [], [], max(0.0, deadline - time.monotonic()))
            if not ready:
                break
            ack_line = self._proc.stdout.readline()
            if not ack_line:
                break
            ack = json.loads(ack_line)
            if ack.get("op") == "PLAN_ACK" and int(ack.get("generation", -1)) == int(generation):
                self._planned_records = {
                    (int(generation), index): item.record_id
                    for index, item in enumerate(planned)
                }
                self._planned_generation = int(generation)
                self._plan_count = int(ack.get("plan_count") or (self._plan_count + 1))
                self.telemetry["plan_ack_ns"] = int(ack.get("ack_ns") or time.monotonic_ns())
                break
            if ack.get("op") == "fatal":
                raise SourceProtocolError(str(ack.get("error")))
        else:
            raise SourceProtocolError("source_plan_ack_timeout")
        if self._planned_generation != int(generation):
            raise SourceProtocolError("source_plan_ack_timeout")
        self.telemetry["plan_published_ns"] = time.monotonic_ns()
        self.telemetry["plan_count"] = self._plan_count
        self.telemetry["plan_range_count"] = len(planned)

    def _check_child(self) -> None:
        if self._proc is not None and self._proc.poll() is not None:
            raise SourceProtocolError("source_process_exited")
        with self._lock:
            failed = _read_header(self.control.buf)[-1]
        if failed:
            raise SourceProtocolError("source_thread_failed")

    def wait_ready(self, timeout_s: float = 30.0) -> ReadyRecord | None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self._check_child()
            with self._lock:
                _read_header(self.control.buf)
                for index in range(SLOT_COUNT):
                    state, generation, range_index, source, destination, length, ready_ns, producer_id = _slot(self.control.buf, index)
                    if state == READY:
                        plan_generation = int(_read_header(self.control.buf)[5])
                        if self._planned_generation != plan_generation:
                            raise SourceProtocolError("ready_plan_generation_mismatch")
                        return ReadyRecord(index, generation, source, destination, length,
                                           range_index, producer_id, ready_ns,
                                           self._planned_records.get((plan_generation, int(range_index))))
            time.sleep(0.0005)
        return None

    def claim_ready(self, record: ReadyRecord) -> ReadyRecord:
        with self._lock:
            header = _read_header(self.control.buf)
            if getattr(self, "_planned_generation", None) is not None and (
                record.plan_generation is None or int(record.plan_generation) != int(header[5])
            ):
                raise SourceProtocolError("stale_ready_plan_generation")
            current = _slot(self.control.buf, record.slot_index)
            if current[0] != READY or current[1] != record.generation:
                raise SourceProtocolError("stale_ready_generation")
            _put_slot(self.control.buf, record.slot_index,
                      (IN_FLIGHT, current[1], current[2], current[3], current[4], current[5], current[6], 0))
            values = list(_read_header(self.control.buf))
            values[8] = max(0, values[8] - 1)
            _write_header(self.control.buf, generation=values[5], plan_count=values[6],
                          next_range=values[7], ready_count=values[8],
                          completed_count=values[9], failed_count=values[10])
            _bump_counter(self.control.buf, 4)
        return record

    def release_slot(self, record: ReadyRecord, *, completion_ns: int | None = None) -> None:
        with self._lock:
            header = _read_header(self.control.buf)
            if getattr(self, "_planned_generation", None) is not None and (
                record.plan_generation is None or int(record.plan_generation) != int(header[5])
            ):
                raise SourceProtocolError("stale_release_plan_generation")
            current = _slot(self.control.buf, record.slot_index)
            if current[1] != record.generation:
                raise SourceProtocolError("stale_release_generation")
            if current[0] != IN_FLIGHT:
                raise SourceProtocolError("release_without_completion_ownership")
            _put_slot(self.control.buf, record.slot_index,
                      (FREE, current[1], current[2], current[3], current[4], current[5], current[6],
                       int(completion_ns or time.monotonic_ns())))
            values = list(_read_header(self.control.buf))
            values[-2] += 1
            _write_header(self.control.buf, generation=values[5], plan_count=values[6],
                          next_range=values[7], ready_count=values[8],
                          completed_count=values[9], failed_count=values[10])
            _bump_counter(self.control.buf, 5)
            self.telemetry["release_count"] = int(self.telemetry.get("release_count", 0)) + 1

    def wait_quiescent(self, timeout_s: float = 30.0) -> None:
        """Require all source ownership to be returned before the next PLAN."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self._check_child()
            with self._lock:
                header = _read_header(self.control.buf)
                slots_free = all(_slot(self.control.buf, i)[0] == FREE for i in range(SLOT_COUNT))
                if slots_free and header[8] == 0 and header[10] == 0:
                    return
            time.sleep(0.0005)
        raise SourceProtocolError("source_quiescence_timeout")

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            header = _read_header(self.control.buf)
            slots = [_slot(self.control.buf, i) for i in range(SLOT_COUNT)]
            counters = COUNTERS.unpack_from(self.control.buf, COUNTER_OFFSET)
        operation_count = int(counters[6])
        operations = []
        for i in range(min(operation_count, MAX_OPS)):
            raw = OP.unpack_from(self.control.buf, OP_OFFSET + i * OP.size)
            record = dict(zip(OP_FIELDS, raw))
            if int(record["generation"]) != int(header[5]):
                continue
            record["plan_generation"] = int(record["generation"])
            record["reader"] = int(record["reader_id"])
            record["thread"] = int(record["thread_id"])
            record["slot"] = int(record["slot_index"])
            record["ordinal"] = int(record["ordinal"])
            operations.append(record)
        effective_levels = [
            sum(1 for item in operations if min(THREAD_COUNT, int(item["flags"]) & 0xff) == level)
            for level in range(THREAD_COUNT + 1)
        ]
        _validate_memcpy_gaps(operations)
        return {
            **self.telemetry,
            "generation": header[5], "plan_count": header[6], "next_range": header[7],
            "ready_count": header[8], "completed_count": header[9], "failed_count": header[10],
            "slot_states": [item[0] for item in slots],
            "slot_acquire_wait_ns": counters[0],
            "slot_acquire_wait_count": counters[1],
            "all_slots_occupied_count": counters[2],
            "ready_publish_count": counters[3],
            "ready_receive_count": counters[4],
            "release_count": counters[5],
            "source_start_ns": [item["source_start_ns"] for item in operations],
            "source_operations": len(operations),
            "operation_count": operation_count,
            "source_operation_records": operations,
            "pacing_wait_count": sum(1 for item in operations if item["pacing_wait_ns"]),
            "pacing_zero_delay_count": sum(1 for item in operations if not item["pacing_wait_ns"]),
            "effective_reader_concurrency": max(
                (int(item["flags"]) & 0xff for item in operations), default=0
            ),
            "effective_reader_concurrency_distribution": effective_levels,
            "time_weighted_reader_concurrency": _time_weighted_concurrency(operations),
            "mmap_map_count": sum(1 for item in operations if item["map_start_ns"]),
            "mmap_unmap_count": sum(1 for item in operations if item["munmap_start_ns"]),
            "min_source_gap_ns": min(
                (right["source_start_ns"] - left["source_start_ns"] for left, right in zip(
                    sorted(operations, key=lambda item: item["source_start_ns"]),
                    sorted(operations, key=lambda item: item["source_start_ns"])[1:])), default=None
            ),
        }

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        stop_error: BaseException | None = None
        try:
            if self._proc is not None and self._proc.stdin is not None:
                self._proc.stdin.write('{"op":"STOP"}\n')
                self._proc.stdin.flush()
                self._proc.wait(timeout=10.0)
        except Exception as exc:
            stop_error = exc
            if self._proc is not None:
                self._proc.kill()
                try:
                    self._proc.wait(timeout=2.0)
                except Exception:
                    pass
        try:
            self.control.close()
            self.control.unlink()
        finally:
            self._lock.close()
            if self._lock_path_owned:
                try:
                    os.unlink(self.lock_path)
                except OSError:
                    pass
        if stop_error is not None:
            raise SourceProtocolError(
                f"source_process_stop_timeout:{type(stop_error).__name__}:{stop_error}"
            ) from stop_error


class SourcePlanBridge:
    """Feed READY ownership into an existing GoldenQDTransport dispatcher.

    This adapter intentionally owns no CUDA work.  The dispatcher remains the
    sole H2D/event/release owner; the callback is invoked only from its proven
    completion path.
    """

    def __init__(self, manager: SourceThreadProcess, transport: Any):
        self.manager = manager
        self.transport = transport

    def publish_all(self, ranges: Sequence[Any], *, generation: int, path: str,
                    identity: Sequence[int], destination_size: int, timeout_s: float = 120.0) -> int:
        normalized = tuple(
            SourceRange(int(item.source_offset), int(item.length), int(item.target_offset), item.record_id)
            for item in ranges
        )
        self.manager.plan_once(generation=generation, path=path, identity=identity,
                               ranges=normalized, destination_size=destination_size,
                               mmap_lifecycle=getattr(self.manager, "mmap_lifecycle", "fresh"))
        remaining = len(normalized)
        published = 0
        claimed: list[ReadyRecord] = []
        submitted: set[int] = set()
        deadline = time.monotonic() + timeout_s
        try:
            while remaining:
                budget = max(0.01, deadline - time.monotonic())
                record = self.manager.wait_ready(budget)
                if record is None:
                    raise SourceProtocolError("source_ready_timeout")
                record = self.manager.claim_ready(record)
                claimed.append(record)
                item = normalized[record.range_index]
                if (record.source_offset, record.destination_offset, record.nbytes) != (
                    item.source_offset, item.destination_offset, item.length
                ):
                    raise SourceProtocolError("ready_record_coverage_mismatch")
                lease = self.transport.acquire(
                    timeout=budget, declared_range=item, producer_id=record.producer_id,
                    preferred_slot_index=record.slot_index, preferred_only=True,
                )
                lease.mark_filled(record.nbytes)
                lease._external_release_callback = lambda rec=record: self.manager.release_slot(
                    rec, completion_ns=time.monotonic_ns()
                )
                lease._source_thread_correlation = {
                    "plan_generation": record.plan_generation,
                    "ordinal": record.range_index,
                    "slot_index": record.slot_index,
                    "slot_generation": record.slot_generation,
                    "manager_ready_receive_ns": time.monotonic_ns(),
                }
                self.transport.publish(
                    lease, self.transport._ready_record(
                        record.source_offset, record.destination_offset, record.nbytes,
                        item.record_id, record.producer_id,
                    ) if hasattr(self.transport, "_ready_record") else __import__(
                        "comfymodal_runtime.golden_qd_transport", fromlist=["ReadyRecord"]
                    ).ReadyRecord(record.source_offset, record.destination_offset, record.nbytes,
                                  item.record_id, record.producer_id)
                )
                submitted.add(record.slot_index)
                published += 1
                remaining -= 1
        except BaseException:
            # Only claimed slots which never entered the dispatcher can be
            # released here.  Submitted ownership remains with GoldenQDTransport
            # until completion is proven; uncertainty is intentionally retained.
            for record in claimed:
                if record.slot_index not in submitted:
                    try:
                        self.manager.release_slot(record, completion_ns=time.monotonic_ns())
                    except BaseException:
                        pass
            raise
        return published


def _native_mmap_setup() -> Any:
    """Return the small libc surface used by the CUDA-sterile source child."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                          ctypes.c_int, ctypes.c_int, ctypes.c_long]
    libc.munmap.restype = ctypes.c_int
    libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    libc.memmove.restype = ctypes.c_void_p
    libc.memmove.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    return libc


def _map_failed(address: Any) -> bool:
    return not address or int(ctypes.cast(address, ctypes.c_void_p).value or 0) == ctypes.c_void_p(-1).value


class _PosixAttachment:
    """Raw /dev/shm attachment; unlike SharedMemory it starts no tracker."""

    def __init__(self, name: str, size: int):
        if os.name != "posix":
            raise SourceProtocolError("source_attachment_requires_posix")
        path = os.path.join("/dev/shm", str(name).lstrip("/"))
        self._fd = os.open(path, os.O_RDWR)
        self._map = _mmap.mmap(self._fd, int(size), access=_mmap.ACCESS_WRITE)
        self.buf = memoryview(self._map)
        self.size = int(size)

    def close(self) -> None:
        self.buf.release()
        self._map.close()
        os.close(self._fd)


def _child_main(arena_name: str, control_name: str, lock_path: str) -> int:
    # Do not call multiprocessing.shared_memory.SharedMemory(name=...) here:
    # that attach path starts a resource-tracker helper process and can unlink
    # parent-owned storage during child teardown.  The old
    # ``resource_tracker.unregister`` workaround is intentionally not used.
    arena = _PosixAttachment(arena_name, ARENA_BYTES)
    control = _PosixAttachment(control_name, CONTROL_BYTES)
    lock = _FileLock(lock_path)
    stop = threading.Event()
    plan_ready = threading.Event()
    plan_data: dict[str, Any] = {}
    plan_lock = threading.Lock()
    pacer = GlobalSourcePacer()
    fd_by_thread: dict[int, tuple[int, tuple[Any, ...]]] = {}
    whole_maps: dict[int, tuple[tuple[Any, ...], int, int]] = {}
    libc = _native_mmap_setup()
    page_size = int(os.sysconf("SC_PAGE_SIZE"))
    fd_lock = threading.Lock()
    fatal: list[str] = []
    operation_count = 0
    records_lock = threading.Lock()
    active_lock = threading.Lock()
    active_workers = 0
    active_claims: set[int] = set()
    slot_wait_started: dict[int, int] = {}

    def emit(message: Mapping[str, Any]) -> None:
        sys.stdout.write(json.dumps(dict(message), separators=(",", ":")) + "\n")
        sys.stdout.flush()

    try:
        if arena.size != ARENA_BYTES:
            raise SourceProtocolError("arena_size_mismatch")
        _read_header(control.buf)
        threads: list[threading.Thread] = []
        barrier = threading.Barrier(THREAD_COUNT + 1)

        def worker(thread_id: int) -> None:
            nonlocal active_workers, operation_count
            try:
                barrier.wait(timeout=30.0)
                while not stop.is_set():
                    plan_ready.wait(0.05)
                    if stop.is_set():
                        return
                    with plan_lock:
                        current = dict(plan_data)
                    if not current:
                        continue
                    with plan_lock:
                        with lock:
                            header = _read_header(control.buf)
                            generation = header[5]
                            if int(current.get("generation", -1)) != int(generation):
                                continue
                            index = header[7]
                            ranges = current["ranges"]
                            if index >= len(ranges):
                                if header[8] == 0 and header[10] == 0:
                                    plan_ready.clear()
                                continue
                            slot_index = next((i for i in range(SLOT_COUNT) if _slot(control.buf, i)[0] == FREE), None)
                            if slot_index is None:
                                if thread_id not in slot_wait_started:
                                    slot_wait_started[thread_id] = time.monotonic_ns()
                                    _bump_counter(control.buf, 1)
                                _bump_counter(control.buf, 2)
                                continue
                            wait_started = slot_wait_started.pop(thread_id, None)
                            slot_wait_ns = 0
                            if wait_started is not None:
                                slot_wait_ns = time.monotonic_ns() - wait_started
                                _bump_counter(control.buf, 0, slot_wait_ns)
                            item = ranges[index]
                            slot_generation = _slot(control.buf, slot_index)[1] + 1
                            _put_slot(control.buf, slot_index, (FILLING, slot_generation, index,
                                      item["source_offset"], item["destination_offset"], item["length"], 0, 0))
                            values = list(header)
                            values[7] += 1
                            _write_header(control.buf, generation=generation, plan_count=values[6],
                                          next_range=values[7], ready_count=values[8],
                                          completed_count=values[9], failed_count=values[10])
                            with active_lock:
                                active_workers += 1
                                active_claims.add(thread_id)
                                effective_concurrency = active_workers
                    path = current["path"]
                    lifecycle = str(current.get("mmap_lifecycle") or "fresh").lower()
                    if lifecycle not in {"fresh", "whole"}:
                        raise SourceProtocolError("unsupported_mmap_lifecycle")
                    expected_identity = tuple(int(value) for value in current["identity"])
                    cache_key = (path, *expected_identity, int(generation))
                    fd_reused = False
                    with fd_lock:
                        cached = fd_by_thread.get(thread_id)
                        fd = cached[0] if cached is not None else None
                        actual_fd_identity = None
                        if fd is not None:
                            try:
                                stat = os.fstat(fd)
                                actual_fd_identity = (int(stat.st_dev), int(stat.st_ino), int(stat.st_size), int(stat.st_mtime_ns))
                            except OSError:
                                actual_fd_identity = None
                        if cached is not None and (cached[1] != cache_key or actual_fd_identity != expected_identity):
                            os.close(fd)
                            fd = None
                            prior_map = whole_maps.pop(thread_id, None)
                            if prior_map is not None:
                                _, prior_address, prior_length = prior_map
                                libc.munmap(ctypes.c_void_p(prior_address), ctypes.c_size_t(prior_length))
                        elif cached is not None:
                            fd_reused = True
                        if fd is None:
                            _validate_identity(path, expected_identity)
                            fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
                            fd_by_thread[thread_id] = (fd, cache_key)
                    length = int(item["length"])
                    target = memoryview(arena.buf)[slot_index * SLOT_BYTES:slot_index * SLOT_BYTES + length]
                    source_offset = int(item["source_offset"])
                    map_start = 0
                    map_address: int
                    map_length: int
                    temporary_map = False
                    if lifecycle == "whole":
                        existing = whole_maps.get(thread_id)
                        if existing is None or existing[0] != cache_key:
                            if existing is not None:
                                libc.munmap(ctypes.c_void_p(existing[1]), ctypes.c_size_t(existing[2]))
                            file_size = int(os.fstat(fd).st_size)
                            if file_size <= 0:
                                raise SourceProtocolError("empty_source_file")
                            map_start = time.monotonic_ns()
                            mapped = libc.mmap(None, ctypes.c_size_t(file_size), 1, 2, fd, 0)
                            if _map_failed(mapped):
                                raise SourceProtocolError(f"mmap_failed:{ctypes.get_errno()}")
                            map_address = int(ctypes.cast(mapped, ctypes.c_void_p).value)
                            map_length = file_size
                            whole_maps[thread_id] = (cache_key, map_address, map_length)
                        else:
                            _, map_address, map_length = existing
                        if source_offset < 0 or source_offset + length > map_length:
                            raise SourceProtocolError("mapped_source_range_out_of_bounds")
                        copy_address = map_address + source_offset
                    else:
                        aligned = (source_offset // page_size) * page_size
                        map_length = source_offset - aligned + length
                        map_start = time.monotonic_ns()
                        mapped = libc.mmap(None, ctypes.c_size_t(map_length), 1, 2, fd, aligned)
                        if _map_failed(mapped):
                            raise SourceProtocolError(f"mmap_failed:{ctypes.get_errno()}")
                        map_address = int(ctypes.cast(mapped, ctypes.c_void_p).value) + source_offset - aligned
                        temporary_map = True
                        copy_address = map_address
                    target_address = ctypes.addressof(ctypes.c_char.from_buffer(target))
                    def _copy(mark_actual_start: Any) -> int:
                        start = mark_actual_start()
                        libc.memmove(ctypes.c_void_p(target_address), ctypes.c_void_p(copy_address), ctypes.c_size_t(length))
                        return start
                    access_start, memcpy_start, waited = pacer.paced_copy(
                        _copy, reader_id=thread_id, ordinal=int(index)
                    )
                    source_start = memcpy_start
                    memcpy_end = time.monotonic_ns()
                    munmap_start = 0
                    munmap_end = 0
                    if temporary_map:
                        munmap_start = time.monotonic_ns()
                        raw_address = map_address - source_offset + (source_offset // page_size) * page_size
                        if libc.munmap(ctypes.c_void_p(raw_address), ctypes.c_size_t(map_length)) != 0:
                            raise SourceProtocolError(f"munmap_failed:{ctypes.get_errno()}")
                        munmap_end = time.monotonic_ns()
                    ready_ns = time.monotonic_ns()
                    with lock:
                        current_slot = _slot(control.buf, slot_index)
                        if current_slot[0] != FILLING or current_slot[1] != slot_generation:
                            raise SourceProtocolError("slot_generation_changed_during_fill")
                        _put_slot(control.buf, slot_index, (READY, slot_generation, index,
                                  item["source_offset"], item["destination_offset"], length, ready_ns, thread_id))
                        values = list(_read_header(control.buf))
                        values[8] += 1
                        _write_header(control.buf, generation=values[5], plan_count=values[6],
                                      next_range=values[7], ready_count=values[8],
                                      completed_count=values[9], failed_count=values[10])
                        _bump_counter(control.buf, 3)
                        with records_lock:
                            op_index = operation_count
                            operation_count += 1
                            if op_index < MAX_OPS:
                                record = (
                                    int(generation), int(thread_id), int(threading.get_native_id()),
                                    int(slot_index), int(index), int(source_offset), int(length),
                                    int(source_start), int(map_start), int(access_start),
                                    int(memcpy_start), int(memcpy_end), int(munmap_start),
                                    int(munmap_end), int(slot_wait_ns), int(waited),
                                    int(ready_ns), int(effective_concurrency)
                                    | (int(lifecycle == "whole") << 8)
                                     | (int(bool(map_start)) << 9)
                                     | (int(fd_reused) << 10),
                                )
                                OP.pack_into(control.buf, OP_OFFSET + op_index * OP.size,
                                              *record)
                            _bump_counter(control.buf, 6)
                    with active_lock:
                        active_workers = max(0, active_workers - 1)
                        active_claims.discard(thread_id)
            except BaseException as exc:
                with active_lock:
                    if thread_id in active_claims:
                        active_claims.discard(thread_id)
                        active_workers = max(0, active_workers - 1)
                try:
                    with lock:
                        values = list(_read_header(control.buf))
                        _write_header(
                            control.buf,
                            generation=values[5],
                            plan_count=values[6],
                            next_range=values[7],
                            ready_count=values[8],
                            completed_count=values[9],
                            failed_count=values[10] + 1,
                        )
                except BaseException:
                    pass
                fatal.append(f"{type(exc).__name__}:{exc}")
                stop.set()
                plan_ready.set()

        for thread_id in range(THREAD_COUNT):
            thread = threading.Thread(target=worker, args=(thread_id,), name=f"c0-source-{thread_id}", daemon=True)
            thread.start()
            threads.append(thread)
        barrier.wait(timeout=30.0)
        emit({"op": "READY", "geometry": geometry(), "telemetry": {
            "threads_created_ns": time.monotonic_ns(),
            "persistent_fd_policy": "one_fd_per_source_thread_per_model",
            "thread_identities": [
                {"reader_id": index, "name": thread.name, "thread_id": thread.native_id}
                for index, thread in enumerate(threads)
            ],
            "process_id": os.getpid(),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", "<unset>"),
            "shared_memory_attachment": "posix_mmap_no_resource_tracker",
            "resource_tracker_helper_process": False,
        }})
        assert sys.stdin is not None
        for line in sys.stdin:
            message = json.loads(line)
            operation = message.get("op")
            if operation == "STOP":
                break
            if operation != "PLAN":
                raise SourceProtocolError("source_accepts_only_one_plan_command_kind")
            with plan_lock:
                if plan_data:
                    with lock:
                        previous = _read_header(control.buf)
                        previous_complete = (
                            previous[7] >= len(plan_data["ranges"])
                            and all(_slot(control.buf, i)[0] == FREE for i in range(SLOT_COUNT))
                        )
                    if not previous_complete:
                        raise SourceProtocolError("source_previous_plan_not_quiescent")
                    plan_data = {}
                    plan_ready.clear()
                    deadline = time.monotonic() + 30.0
                    while time.monotonic() < deadline:
                        with active_lock:
                            active = bool(active_claims)
                        with lock:
                            free = all(_slot(control.buf, i)[0] == FREE for i in range(SLOT_COUNT))
                        if not active and free:
                            break
                        time.sleep(0.0005)
                    else:
                        raise SourceProtocolError("source_previous_plan_stop_timeout")
                actual = _validate_identity(str(message["path"]), message["identity"])
                plan_data = {
                    "path": str(message["path"]), "identity": tuple(message["identity"]),
                    "ranges": list(message["ranges"]), "destination_size": int(message["destination_size"]),
                    "mmap_lifecycle": str(message.get("mmap_lifecycle") or "fresh").lower(),
                }
                if plan_data["mmap_lifecycle"] not in {"fresh", "whole"}:
                    raise SourceProtocolError("unsupported_mmap_lifecycle")
                validate_plan(tuple(SourceRange(int(item["source_offset"]), int(item["length"]),
                                               int(item["destination_offset"]), item.get("record_id")) for item in plan_data["ranges"]),
                               source_size=actual[2], destination_size=plan_data["destination_size"])
                with lock:
                    previous = _read_header(control.buf)
                    if any(_slot(control.buf, i)[0] != FREE for i in range(SLOT_COUNT)):
                        raise SourceProtocolError("source_previous_plan_not_quiescent")
                    next_plan_count = int(previous[6]) + 1
                    _write_header(
                        control.buf, generation=int(message["generation"]),
                        plan_count=next_plan_count, next_range=0,
                        ready_count=0, completed_count=0, failed_count=0,
                    )
                    # Reset state once, but never reset slot generations.  A
                    # released slot must not be able to collide with an old
                    # token after a new PLAN is installed.
                    for slot_index in range(SLOT_COUNT):
                        old = _slot(control.buf, slot_index)
                        _put_slot(control.buf, slot_index, (FREE, old[1], 0, 0, 0, 0, 0, 0))
            plan_ready.set()
            emit({"op": "PLAN_ACK", "generation": int(message["generation"]),
                  "plan_count": next_plan_count, "ack_ns": time.monotonic_ns()})
        stop.set()
        plan_ready.set()
        for thread in threads:
            thread.join(timeout=10.0)
        if fatal:
            with lock:
                values = list(_read_header(control.buf))
                _write_header(control.buf, generation=values[5], plan_count=values[6], next_range=values[7],
                              ready_count=values[8], completed_count=values[9], failed_count=1)
            emit({"op": "fatal", "error": fatal[0]})
        emit({"op": "TELEMETRY", "telemetry": pacer.telemetry()})
        for fd, _key in fd_by_thread.values():
            os.close(fd)
        for _, address, length in whole_maps.values():
            libc.munmap(ctypes.c_void_p(address), ctypes.c_size_t(length))
        return 0 if not fatal else 1
    except BaseException as exc:
        emit({"op": "fatal", "error": f"{type(exc).__name__}:{exc}"})
        return 1
    finally:
        arena.close()
        control.close()
        lock.close()


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-child", nargs=3, metavar=("ARENA", "CONTROL", "LOCK"))
    args = parser.parse_args()
    if args.source_child:
        return _child_main(*args.source_child)
    parser.error("source module is not a standalone CLI")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "ARENA_BYTES", "CONTROL_BYTES", "EXPERIMENT_ENV", "FREE", "FILLING", "READY",
    "IN_FLIGHT", "PACER_GAP_NS", "SLOT_BYTES", "SLOT_COUNT", "THREAD_COUNT",
    "ReadyRecord", "SourcePlanBridge", "SourceProtocolError", "SourceRange",
    "SourceThreadProcess", "GlobalSourcePacer", "enabled", "geometry", "validate_plan",
]
