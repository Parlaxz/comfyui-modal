"""CUDA-sterile C0 source owner with four persistent reader workers.

This module has a standard-library-only import surface.  The parent owns the
CUDA-registered arena; the source owner only attaches to its POSIX backing and
writes bytes into generation-tagged physical slots.  A model is described by one
PLAN message.  There is no per-range command: source workers self-advance
through the installed plan and claim both ranges and slots from the bounded
shared control block.

Coordination is deliberately thin:

* one immutable per-generation plan (path identity, one descriptor, at most
  one whole-file mapping) is built once at PLAN install and never re-validated
  per block;
* slot ownership transitions happen under one process-shared lock plus an
  in-process lock, and that lock is never held across a syscall which can block
  for a meaningful time (mmap / memcpy / munmap all run unlocked);
* capacity exhaustion blocks the reader instead of re-taking the control lock
  while zero physical slots are free;
* READY publication is an event, not a poll: the source owner emits exactly
  one doorbell line per READY block and the parent blocks reading it.

Two reader topologies share one source kernel:

``thread``
    one source process, four reader threads, one shared address space, one
    shared descriptor and at most one whole-file mapping.

``process``
    one CUDA-sterile source supervisor, four independent persistent reader
    processes, each with its own address space and therefore its own
    descriptor and whole-file mapping.

In both cases the parent sends one PLAN per model and the readers self-service
every range and every slot.  The parent never schedules a block.

The parent releases a slot only after its CUDA dispatcher has proved the copy
complete.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import mmap as _mmap
import os
import queue
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

# --- import-time source identity (stale-snapshot detection) --------------
# Frozen here, not at request time: a container restored from a Modal
# memory snapshot keeps the code objects imported before capture while the
# mounted tree can be newer, so a request-time hash would read the NEW file
# and wrongly vouch for OLD executing code.
try:  # works both as a package module and when a test loads this file
    # standalone via spec_from_file_location, which sets no parent package.
    from .source_identity import freeze_imported_sha as _freeze_imported_sha
except ImportError:  # pragma: no cover - taken by standalone-load tests
    from comfymodal_runtime.source_identity import (
        freeze_imported_sha as _freeze_imported_sha,
    )

_IMPORTED_SOURCE_SHA256 = _freeze_imported_sha(__name__, __file__)

if os.name == "posix":
    import fcntl as _fcntl
else:  # pragma: no cover - the runtime arm is deliberately POSIX-only.
    _fcntl = None


EXPERIMENT_ENV = "COMFYMODAL_GOLDEN_C0_SOURCE_THREADS"
WORKER_KIND_ENV = "COMFYMODAL_GOLDEN_C0_SOURCE_WORKER_KIND"
# 16 x 64 MiB, not 8 x 64 MiB.  Production-009 proved the 8-slot arena can be
# outrun by a healthy QD4 source: all eight slots were occupied repeatedly with
# ~654 ms of cumulative slot wait, holding effective reader concurrency at
# ~3.51/4.  Doubling the buffering is the only variable in this treatment --
# READER_COUNT, the 64 MiB block size, the 4 ms pacer, the worker topology, the
# mmap lifecycle and the H2D dispatcher semantics are all unchanged, so this
# asks one question: can healthy QD4 stay fed when the arena is deeper?
# Six readers is a separate, later experiment.
ARENA_BYTES = 16 * 64 * 1024 * 1024
SLOT_COUNT = 16
SLOT_BYTES = 64 * 1024 * 1024
READER_COUNT = 4
THREAD_COUNT = READER_COUNT
PACER_GAP_NS = 4_000_000
# Fail-closed per-model-load wall gate.  This is a GUARDRAIL, not a throughput
# mechanism: a healthy 8 GiB CLIP load is ~1.3 s and a healthy 12 GiB UNET load
# is ~2.3 s, so 30 s is ~20x the worst healthy observation.  It replaces the
# former 120 s default, which let a pathologically slow source span run for
# two whole minutes before the request was abandoned.  The gate is enforced by
# the consumer loop in ``SourcePlanBridge.publish_all``, which is the only
# boundary that actually observes wall time while the source owner is busy --
# wrapping the blocking transport in ``asyncio.wait_for`` would not interrupt
# it, because the read runs synchronously on the caller's thread.
MODEL_LOAD_GATE_S = 30.0
CONTROL_BYTES = 512 * 1024
CONTROL_MAGIC = b"C0STHRD2"
CONTROL_VERSION = 2
# magic, version, slot_count, slot_bytes, arena_bytes, generation, plan_count,
# next_range, ready_count, completed_count, failed_count, free_mask, last_start_ns
HEADER = struct.Struct("<8sIIIIQQQQQQQQ")
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
SLOT_TABLE_BYTES = SLOT_COUNT * SLOT.size
# The counter and error regions are placed *after* the slot table and derived
# from its size.  Deriving them from the header size instead silently overlaps
# the slot table as soon as the counter block grows, and every counter bump
# would then corrupt slot 0's state and generation.
COUNTER_OFFSET = SLOT_OFFSET + SLOT_TABLE_BYTES
# Generation-scoped counters.  They are reset exactly once per installed PLAN,
# so no model generation can inherit another model's counts.
COUNTERS = struct.Struct("<QQQQQQQQQQQQ")
COUNTER_NAMES = (
    "slot_wait_ns",
    "slot_wait_count",
    "all_slots_occupied_count",
    "ready_publish_count",
    "ready_receive_count",
    "release_count",
    "operation_count",
    "ready_queue_wait_ns",
    "ready_queue_wait_count",
    "capacity_wait_ns",
    "capacity_wait_count",
    "plan_install_count",
)
ERROR_OFFSET = COUNTER_OFFSET + COUNTERS.size
ERROR_BYTES = 1024
OP_OFFSET = ERROR_OFFSET + ERROR_BYTES
# The installed plan is published as bounded JSON in the tail of the control
# segment so independent reader processes can adopt the same immutable plan the
# supervisor installed.  It is rewritten once per model, never per block.
# Sized for the largest real plan: a 184-block model serialises to roughly
# 17 KiB of JSON, which overflowed the previous 8 KiB region and killed every
# four-process arm at its first plan.
PLAN_BYTES = 64 * 1024
PLAN_OFFSET = CONTROL_BYTES - PLAN_BYTES
MAX_OPS = (PLAN_OFFSET - OP_OFFSET) // OP.size

FREE = 0
FILLING = 1
READY = 2
IN_FLIGHT = 3
FAILED = 4

# Every physical slot starts free.
FREE_MASK = (1 << SLOT_COUNT) - 1
# Reader wake bytes.  A blocked reader consumes exactly one byte.
WAKE_CAPACITY = b"c"
WAKE_PLAN = b"q"
WAKE_STOP = b"x"

WORKER_KINDS = ("thread", "process")
# Bounded liveness fallback for the in-child capacity semaphore.  Correct
# wakeups are delivered by the parent's completion-proven release message; this
# only bounds a pathological lost-message stall and is not a poll loop.
CAPACITY_WAIT_SLICE_S = 0.25


class SourceProtocolError(RuntimeError):
    """A source protocol or identity violation; callers must fail closed."""


def enabled(value: Any = None) -> bool:
    selected = os.environ.get(EXPERIMENT_ENV) if value is None else value
    return str(selected or "").strip().lower() in {"1", "true", "yes", "on"}


def worker_kind(value: Any = None) -> str:
    """Return the explicit, fail-closed source worker kind."""
    selected = os.environ.get(WORKER_KIND_ENV, "thread") if value is None else value
    kind = str(selected or "").strip().lower()
    if kind not in WORKER_KINDS:
        raise SourceProtocolError(f"unsupported_source_worker_kind:{kind!r}")
    return kind


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

    @property
    def target_offset(self) -> int:
        """Match GoldenQDTransport.SourceRange's destination spelling."""
        return int(self.destination_offset)

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

    @property
    def token(self) -> tuple[int, int]:
        """Full physical-slot ownership token.

        ``slot_index`` alone is not an ownership identity: slots are reused, so
        a successful old generation of slot 3 must never satisfy ownership of a
        newer slot 3.
        """
        return (int(self.slot_index), int(self.generation))


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
    """One locked 4 ms reservation clock shared by all source workers.

    The reservation lock is released by the copy-start marker, so only the start
    boundary itself is serialized; the native copies then run concurrently.  The
    marker re-checks the *observed* start and corrects in place if scheduling
    ever creates a sub-4 ms gap between two real copy starts.

    Because the reservation lock is held through the marker, two real copy
    starts can never be closer than the floor.  ``SharedSourcePacer`` is the
    cross-process equivalent and necessarily has a small post-reservation
    window; both report the same correction telemetry.
    """

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
        self.correction_ns = 0
        self.correction_count = 0

    def reserve(self, *, now_ns: int | None = None) -> tuple[int, int]:
        """Reserve and return ``(reserved_start_ns, wait_ns)``.

        ``now_ns`` is a deterministic test seam.  Production callers omit it;
        the operation boundary is the timestamp immediately before mapped
        access/memcpy begins.
        """
        with self._lock:
            waited = 0
            now = int(self._clock() if now_ns is None else now_ns)
            target = now if self.last_start_ns is None else max(now, self.last_start_ns + self.gap_ns)
            if target > now and now_ns is None:
                delay = target - now
                self._sleep(delay / 1e9)
                now = int(self._clock())
                waited += max(0, delay)
            start = int(max(now, target))
            self.last_start_ns = start
            self.timestamps_ns.append(start)
            self.wait_ns.append(waited)
            if waited == 0:
                self.zero_delay_count += 1
            return start, waited

    def telemetry(self) -> dict[str, Any]:
        gaps = [right - left for left, right in zip(self.actual_timestamps_ns, self.actual_timestamps_ns[1:])]
        return {
            "pacer_gap_ns": self.gap_ns,
            "pacer_scope": "process",
            "source_start_timestamps_ns": list(self.actual_timestamps_ns),
            "pacing_wait_ns": list(self.wait_ns),
            "pacing_wait_count": sum(1 for value in self.wait_ns if value > 0),
            "pacing_zero_delay_count": self.zero_delay_count,
            "pacing_correction_ns": self.correction_ns,
            "pacing_correction_count": self.correction_count,
            "min_source_gap_ns": min(gaps) if gaps else None,
            "source_gap_violation_count": sum(1 for value in gaps if value < self.gap_ns),
            "pacer_boundary": "mapped_access_plus_memcpy_start",
        }

    def paced_copy(self, callback: Any, *, reader_id: int = 0, ordinal: int = 0) -> tuple[int, int, int]:
        """Pace and validate the actual copy-start boundary.

        ``callback`` receives a one-shot marker callable and must invoke it
        immediately before entering the native copy.
        """
        self._lock.acquire()
        released = False
        try:
            waited = 0
            while True:
                now = int(self._clock())
                previous_actual = self.actual_timestamps_ns[-1] if self.actual_timestamps_ns else None
                target = now if previous_actual is None else max(now, previous_actual + self.gap_ns)
                if target <= now:
                    break
                delay = target - now
                waited += delay
                self._sleep(delay / 1e9)
            access_start = int(self._clock())

            def mark_actual_start() -> int:
                nonlocal released
                actual = int(self._clock())
                previous_actual = self.actual_timestamps_ns[-1] if self.actual_timestamps_ns else None
                corrected = 0
                while previous_actual is not None and actual - previous_actual < self.gap_ns:
                    delay = self.gap_ns - (actual - previous_actual)
                    self._sleep(delay / 1e9)
                    corrected += delay
                    actual = int(self._clock())
                if corrected:
                    self.correction_ns += int(corrected)
                    self.correction_count += 1
                self.actual_timestamps_ns.append(actual)
                self.timestamps_ns.append(actual)
                self.last_start_ns = actual
                self.wait_ns.append(waited + int(corrected))
                if waited + int(corrected) == 0:
                    self.zero_delay_count += 1
                self._lock.release()
                released = True
                return actual

            result = callback(mark_actual_start)
            memcpy_start = int(result if result is not None else self._clock())
            return access_start, memcpy_start, waited
        finally:
            if not released:
                self._lock.release()


class SharedSourcePacer:
    """Cross-process 4 ms floor backed by the shared control block.

    Independent reader processes cannot hold one Python lock through the copy
    start, so the floor is enforced with a compare-and-set on the shared
    ``last_start_ns`` field.  A reservation and the copy start can therefore
    differ by the preemption window; the observed gaps are still validated and
    published as violations so the weaker guarantee is visible, never silent.
    """

    def __init__(self, gap_ns: int = PACER_GAP_NS, clock: Any = time.monotonic_ns,
                 sleeper: Any = time.sleep):
        if int(gap_ns) <= 0:
            raise ValueError("pacer_gap_must_be_positive")
        self.gap_ns = int(gap_ns)
        self._clock = clock
        self._sleep = sleeper
        self.actual_timestamps_ns: list[int] = []
        self.wait_ns: list[int] = []
        self.correction_ns = 0
        self.correction_count = 0
        self.zero_delay_count = 0

    def telemetry(self) -> dict[str, Any]:
        gaps = [right - left for left, right in zip(self.actual_timestamps_ns, self.actual_timestamps_ns[1:])]
        return {
            "pacer_gap_ns": self.gap_ns,
            "pacer_scope": "cross_process",
            "source_start_timestamps_ns": list(self.actual_timestamps_ns),
            "pacing_wait_ns": list(self.wait_ns),
            "pacing_wait_count": sum(1 for value in self.wait_ns if value > 0),
            "pacing_zero_delay_count": self.zero_delay_count,
            "pacing_correction_ns": self.correction_ns,
            "pacing_correction_count": self.correction_count,
            "min_source_gap_ns": min(gaps) if gaps else None,
            "source_gap_violation_count": sum(1 for value in gaps if value < self.gap_ns),
            "pacer_boundary": "mapped_access_plus_memcpy_start",
        }

    def paced_copy(self, control_buf: Any, lock: Any, callback: Any, *,
                   reader_id: int = 0, ordinal: int = 0) -> tuple[int, int, int]:
        waited = 0
        while True:
            with lock:
                values = list(_read_header(control_buf))
                last = int(values[12])
                now = int(self._clock())
                if not last or now - last >= self.gap_ns:
                    values[12] = now
                    _write_header_all(control_buf, values)
                    access_start = now
                    break
                delay = self.gap_ns - (now - last)
            waited += delay
            self._sleep(delay / 1e9)

        def mark_actual_start() -> int:
            actual = int(self._clock())
            previous_actual = self.actual_timestamps_ns[-1] if self.actual_timestamps_ns else None
            if previous_actual is not None and actual - previous_actual < self.gap_ns:
                self.correction_ns += self.gap_ns - (actual - previous_actual)
                self.correction_count += 1
            self.actual_timestamps_ns.append(actual)
            self.wait_ns.append(waited)
            if waited == 0:
                self.zero_delay_count += 1
            return actual

        result = callback(mark_actual_start)
        memcpy_start = int(result if result is not None else self._clock())
        return access_start, memcpy_start, waited


class _FileLock:
    """Process-shared ownership lock with in-process fast path.

    Only source workers inside the source owner and the single parent consumer
    take this lock, and only for a bounded slot/header state transition.
    """

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


def new_control_buffer() -> bytearray:
    """Build a zeroed, self-describing control segment.

    Exposed so the slot/header state machine can be exercised without a
    POSIX shared-memory object.
    """
    buf = bytearray(CONTROL_BYTES)
    _write_header_all(buf, (
        CONTROL_MAGIC, CONTROL_VERSION, SLOT_COUNT, SLOT_BYTES, ARENA_BYTES,
        0, 0, 0, 0, 0, 0, FREE_MASK, 0,
    ))
    _reset_counters(buf)
    for index in range(SLOT_COUNT):
        _put_slot(buf, index, (FREE, 0, 0, 0, 0, 0, 0, 0))
    return buf


def _read_header(buf: Any) -> tuple[Any, ...]:
    values = HEADER.unpack_from(buf, 0)
    if values[0] != CONTROL_MAGIC or values[1] != CONTROL_VERSION:
        raise SourceProtocolError("control_header_invalid")
    if values[2:5] != (SLOT_COUNT, SLOT_BYTES, ARENA_BYTES):
        raise SourceProtocolError("control_geometry_invalid")
    return values


def _write_header_all(buf: Any, values: Sequence[Any]) -> None:
    """Rewrite the complete header.

    Every state transition goes through this, so no field can be silently
    dropped by a partial reconstruction.
    """
    if tuple(values[:5]) != (CONTROL_MAGIC, CONTROL_VERSION, SLOT_COUNT, SLOT_BYTES, ARENA_BYTES):
        raise SourceProtocolError("control_geometry_invalid")
    if not 0 <= int(values[11]) <= FREE_MASK:
        raise SourceProtocolError("control_free_mask_invalid")
    HEADER.pack_into(buf, 0, *values)


def _slot(buf: Any, index: int) -> tuple[Any, ...]:
    if not 0 <= index < SLOT_COUNT:
        raise SourceProtocolError("slot_index_out_of_bounds")
    return SLOT.unpack_from(buf, SLOT_OFFSET + index * SLOT.size)


def _put_slot(buf: Any, index: int, values: Sequence[int]) -> None:
    SLOT.pack_into(buf, SLOT_OFFSET + index * SLOT.size, *values)


def _bump_counter(buf: Any, index: int, amount: int = 1) -> None:
    values = list(COUNTERS.unpack_from(buf, COUNTER_OFFSET))
    values[index] += int(amount)
    COUNTERS.pack_into(buf, COUNTER_OFFSET, *values)


def _reset_counters(buf: Any) -> None:
    COUNTERS.pack_into(buf, COUNTER_OFFSET, *([0] * len(COUNTER_NAMES)))


def _write_error(buf: Any, message: str) -> None:
    encoded = str(message).encode("utf-8", "replace")[: ERROR_BYTES - 1]
    buf[ERROR_OFFSET : ERROR_OFFSET + ERROR_BYTES] = encoded + b"\0" * (ERROR_BYTES - len(encoded))


def _read_error(buf: Any) -> str:
    return bytes(buf[ERROR_OFFSET : ERROR_OFFSET + ERROR_BYTES]).split(b"\0", 1)[0].decode(
        "utf-8", "replace"
    )


def _write_plan(buf: Any, plan: Mapping[str, Any]) -> None:
    encoded = json.dumps(dict(plan), separators=(",", ":")).encode("utf-8")
    if len(encoded) >= PLAN_BYTES:
        raise SourceProtocolError(
            f"source_plan_metadata_too_large:{len(encoded)}>={PLAN_BYTES}"
            f":ranges={len(plan.get('ranges') or ())}"
        )
    buf[PLAN_OFFSET:PLAN_OFFSET + PLAN_BYTES] = encoded.ljust(PLAN_BYTES, b"\0")


def _read_plan(buf: Any) -> dict[str, Any]:
    raw = bytes(buf[PLAN_OFFSET:PLAN_OFFSET + PLAN_BYTES]).split(b"\0", 1)[0]
    if not raw:
        raise SourceProtocolError("source_plan_metadata_absent")
    return json.loads(raw.decode("utf-8"))


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
            "levels": {str(level): {"ns": 0, "fraction": None} for level in range(READER_COUNT + 1)},
            "effective_concurrency": None,
            "longest_zero_reader_ns": 0,
            "longest_at_most_one_reader_ns": 0,
            "below_four_reader_ns": 0,
        }
    points = sorted({point for start, end, _reader in intervals for point in (start, end)})
    buckets = [0] * (READER_COUNT + 1)
    longest_zero = 0
    longest_at_most_one = 0
    for left, right in zip(points, points[1:]):
        active = {
            reader for start, end, reader in intervals if start <= left and end >= right
        }
        duration = max(0, right - left)
        level = min(READER_COUNT, len(active))
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
        "below_four_reader_ns": sum(buckets[:READER_COUNT]),
    }


def _validate_memcpy_gaps(operations: Sequence[Mapping[str, Any]]) -> list[dict[str, int]]:
    starts = sorted(
        (int(item["memcpy_start_ns"]), int(item.get("reader_id") or 0), int(item.get("ordinal") or 0))
        for item in operations if int(item.get("memcpy_start_ns") or 0)
    )
    violations: list[dict[str, int]] = []
    for previous, current in zip(starts, starts[1:]):
        gap = current[0] - previous[0]
        if gap < PACER_GAP_NS:
            violations.append({
                "reader_id": current[1],
                "ordinal": current[2],
                "previous_ns": previous[0],
                "current_ns": current[0],
                "gap_ns": gap,
            })
    return violations


def canonical_source_span(operations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Derive the canonical model-level source boundaries.

    Operation records are appended on completion, so record order is *not*
    start order and the first record is not the first source start.  The
    authoritative boundaries are the minimum actual source copy start and the
    maximum actual source completion across every operation in the generation,
    in one monotonic clock domain.
    """
    if not operations:
        return {
            "source_start_ns": None,
            "source_end_ns": None,
            "source_wall_ms": None,
            "source_first_enter_ns": None,
            "source_last_exit_ns": None,
            "source_final_byte_complete_ns": None,
            "operation_count": 0,
        }
    starts = []
    ends = []
    for item in operations:
        start = int(item.get("memcpy_start_ns") or 0) or int(item.get("access_start_ns") or 0)
        end = int(item.get("memcpy_end_ns") or 0) or int(item.get("munmap_end_ns") or 0)
        if start:
            starts.append(start)
        if end:
            ends.append(end)
    if not starts or not ends:
        return canonical_source_span(())
    source_start = min(starts)
    # The source span ends when the last byte has been copied out of the file.
    source_end = max(ends)
    return {
        "source_start_ns": source_start,
        "source_end_ns": source_end,
        "source_wall_ms": (source_end - source_start) / 1e6 if source_end >= source_start else None,
        "source_first_enter_ns": source_start,
        "source_last_exit_ns": source_end,
        "source_final_byte_complete_ns": source_end,
        "operation_count": len(operations),
    }


@dataclass(frozen=True)
class Claim:
    """One physical-slot claim, or the reason no claim was possible."""

    outcome: str
    slot_index: int = -1
    slot_generation: int = -1
    range_index: int = -1
    item: tuple[int, int, int, int | None] | None = None
    effective_concurrency: int = 0


def claim_block(control_buf: Any, plan: "_ChildPlan") -> Claim:
    """Claim the next range plus a free physical slot, or explain why not.

    Shared by both reader topologies so the physical-slot state machine can
    never diverge between them.  Must be called under the control lock.

    Effective concurrency is read from the control block itself (slots
    currently FILLING, plus this claim) rather than from a shared Python
    counter, so it is identical in the thread and process topologies and needs
    no cross-process bookkeeping.
    """
    header = _read_header(control_buf)
    if plan.generation != int(header[5]):
        return Claim("stale")
    index = int(header[7])
    if index >= len(plan.ranges):
        return Claim("exhausted")
    free_mask = int(header[11])
    slot_index = -1
    for candidate in range(SLOT_COUNT):
        if free_mask & (1 << candidate):
            slot_index = candidate
            break
    if slot_index < 0:
        return Claim("no_capacity")
    item = plan.ranges[index]
    source_offset, length, destination_offset, _record_id = item
    slot_generation = int(_slot(control_buf, slot_index)[1]) + 1
    filling = sum(1 for position in range(SLOT_COUNT)
                  if _slot(control_buf, position)[0] == FILLING)
    _put_slot(control_buf, slot_index, (FILLING, slot_generation, index,
              source_offset, destination_offset, length, 0, 0))
    values = list(header)
    values[7] = index + 1
    values[11] = free_mask & ~(1 << slot_index)
    _write_header_all(control_buf, values)
    return Claim("claimed", slot_index, slot_generation, index, item,
                 min(READER_COUNT, filling + 1))


def publish_ready(control_buf: Any, reader_id: int, claim: Claim, record: Sequence[int]) -> int:
    """Move a filled slot to READY and append its operation record.

    Must be called under the control lock.  The shared operation-ring index is
    allocated from the control block under that same lock, so four independent
    reader processes cannot collide on it and no model generation can inherit
    another model's ring.  Returns the allocated index, or -1 when the ring is
    saturated.
    """
    if claim.item is None or claim.outcome != "claimed":
        raise SourceProtocolError("publish_ready_without_claim")
    current_slot = _slot(control_buf, claim.slot_index)
    if current_slot[0] != FILLING or int(current_slot[1]) != int(claim.slot_generation):
        raise SourceProtocolError("slot_generation_changed_during_fill")
    source_offset, destination_offset, length = claim.item[0], claim.item[2], claim.item[1]
    values = list(_read_header(control_buf))
    _put_slot(control_buf, claim.slot_index, (READY, claim.slot_generation,
              int(current_slot[2]), source_offset, destination_offset, length,
              int(record[OP_FIELDS.index("ready_ns")]), reader_id))
    values[8] += 1
    _write_header_all(control_buf, values)
    _bump_counter(control_buf, 3)
    index = int(COUNTERS.unpack_from(control_buf, COUNTER_OFFSET)[6])
    if index < MAX_OPS:
        OP.pack_into(control_buf, OP_OFFSET + index * OP.size, *record)
    _bump_counter(control_buf, 6)
    return index if index < MAX_OPS else -1


class SourceThreadProcess:
    """Parent-side owner of the source process and its shared control block."""

    def __init__(self, arena_name: str, *, lock_path: str | None = None,
                 mmap_lifecycle: str = "fresh", worker_kind: str = "thread"):
        if os.name != "posix":
            raise SourceProtocolError("source_thread_process_requires_posix")
        self.arena_name = str(arena_name)
        self.mmap_lifecycle = str(mmap_lifecycle).strip().lower()
        if self.mmap_lifecycle not in {"fresh", "whole"}:
            raise SourceProtocolError("unsupported_mmap_lifecycle")
        self.worker_kind = str(worker_kind).strip().lower()
        if self.worker_kind not in WORKER_KINDS:
            raise SourceProtocolError(f"unsupported_source_worker_kind:{self.worker_kind!r}")
        self.control = shared_memory.SharedMemory(create=True, size=CONTROL_BYTES)
        self.control.buf[:] = new_control_buffer()
        self._lock_path_owned = lock_path is None
        if lock_path is None:
            fd, lock_path = tempfile.mkstemp(prefix="comfymodal-c0-source-", suffix=".lock")
            os.close(fd)
        self.lock_path = str(lock_path)
        self._lock = _FileLock(self.lock_path)
        self._proc: Any = None
        self._planned_generation: int | None = None
        self._planned_records: dict[tuple[int, int], str | int | None] = {}
        self._plan_count = 0
        self._stopped = False
        self._spawned_ns: int | None = None
        # READY doorbells that arrived while a PLAN install was in flight.
        # They are announced work, so they must be handed to the next
        # ``wait_ready`` rather than dropped: discarding one leaves a physical
        # slot stuck READY and stalls the model until the request timeout.
        self._pending_ready: list[ReadyRecord] = []
        self._doorbell_wait_ns = 0
        self._doorbell_wait_count = 0
        self.telemetry: dict[str, Any] = {
            "architecture": f"one_source_owner_four_{self.worker_kind}s",
            "arena_bytes": ARENA_BYTES,
            "slot_count": SLOT_COUNT,
            "slot_bytes": SLOT_BYTES,
            "thread_count": THREAD_COUNT,
            "reader_count": READER_COUNT,
            "source_worker_kind": self.worker_kind,
            "pacer_boundary": "mapped_access_plus_memcpy_start",
            "mmap_lifecycle": self.mmap_lifecycle,
            "fallback": False,
            "effective_reader_concurrency": 0,
        }

    @property
    def process(self) -> Any:
        return self._proc

    def spawn(self) -> Any:
        """Create the CUDA-sterile source owner without waiting for it.

        Startup (interpreter boot, imports, shared-memory attach, and for the
        process kind four more interpreter boots) is independent of the parent's
        arena host registration, so callers can overlap the two rather than
        serializing them.
        """
        if self._proc is not None:
            raise SourceProtocolError("source_process_already_started")
        self._spawned_ns = time.monotonic_ns()
        self._proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--source-child",
             self.arena_name, self.control.name, self.lock_path, self.worker_kind],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, close_fds=True,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": ""},
        )
        return self._proc

    def await_ready(self, timeout_s: float = 30.0) -> dict[str, Any]:
        """Block until the spawned source owner reports READY."""
        if self._proc is None:
            raise SourceProtocolError("source_process_not_started")
        assert self._proc.stdout is not None
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SourceProtocolError("source_process_ready_timeout")
            ready, _, _ = select.select([self._proc.stdout], [], [], remaining)
            if not ready:
                raise SourceProtocolError("source_process_ready_timeout")
            line = self._proc.stdout.readline()
            if not line:
                raise SourceProtocolError("source_process_exited_before_ready")
            message = json.loads(line)
            operation = message.get("op")
            if operation == "READY":
                if message.get("geometry") != geometry():
                    raise SourceProtocolError("source_ready_geometry_mismatch")
                ready_ns = time.monotonic_ns()
                self.telemetry.update(message.get("telemetry") or {})
                self.telemetry["source_spawn_ns"] = self._spawned_ns
                self.telemetry["source_ready_ns"] = ready_ns
                if self._spawned_ns is not None:
                    self.telemetry["source_startup_ms"] = (ready_ns - self._spawned_ns) / 1e6
                return message
            if operation == "fatal":
                raise SourceProtocolError(str(message.get("error")))

    def start(self, timeout_s: float = 30.0) -> dict[str, Any]:
        self.spawn()
        return self.await_ready(timeout_s)

    def _read_message(self, timeout_s: float) -> dict[str, Any] | None:
        """Block until the source owner emits one control message."""
        if self._proc is None or self._proc.stdout is None:
            raise SourceProtocolError("source_process_not_started")
        started = time.monotonic_ns()
        ready, _, _ = select.select([self._proc.stdout], [], [], max(0.0, timeout_s))
        if not ready:
            return None
        line = self._proc.stdout.readline()
        elapsed = time.monotonic_ns() - started
        if not line:
            raise SourceProtocolError("source_process_exited")
        message = json.loads(line)
        if message.get("op") == "READY_BLOCK":
            self._doorbell_wait_ns += elapsed
            self._doorbell_wait_count += 1
        return message

    def plan_once(
        self, *, generation: int, path: str, identity: Sequence[int],
        ranges: Sequence[SourceRange], destination_size: int,
        mmap_lifecycle: str | None = None,
    ) -> dict[str, Any]:
        if self._proc is None or self._proc.stdin is None:
            raise SourceProtocolError("source_process_not_started")
        if self._planned_generation == int(generation):
            raise SourceProtocolError("source_plan_published_twice")
        if self._planned_generation is not None:
            with self._lock:
                header = _read_header(self.control.buf)
                if int(header[11]) != FREE_MASK:
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
        plan_install_begin_ns = time.monotonic_ns()
        # The generation this process is about to serve must be visible to
        # ``_resolve_ready_block`` BEFORE any READY_BLOCK can be read.  The
        # source owner can publish a block before the PLAN ack is drained -- and
        # with a whole-file mapping a small checkpoint is read in well under a
        # second, so the pre-ack window is the common case, not the rare one.
        # Resolving those blocks against the previous generation orphaned their
        # slots in READY and starved the consumer until the load gate fired.
        self._planned_records = {
            (int(generation), index): item.record_id
            for index, item in enumerate(planned)
        }
        self._planned_generation = int(generation)
        message = {
            "op": "PLAN", "generation": int(generation), "path": os.path.abspath(path),
            "identity": list(identity), "destination_size": int(destination_size),
            "mmap_lifecycle": lifecycle,
            "ranges": [item.as_dict() for item in planned],
        }
        self._proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self._proc.stdin.flush()
        # PLAN is not installed until the source owner has stopped the previous
        # generation, atomically installed this one, and acknowledged it.  This
        # closes the old-worker/new-generation race.
        deadline = time.monotonic() + 30.0
        ack: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            candidate = self._read_message(deadline - time.monotonic())
            if candidate is None:
                break
            if candidate.get("op") == "fatal":
                raise SourceProtocolError(str(candidate.get("error")))
            if candidate.get("op") == "READY_BLOCK":
                # A block published before this PLAN landed.  Its slot is
                # genuinely READY, so buffer the exact token for the consumer
                # instead of dropping the announcement.
                self._buffer_ready_block(candidate)
                continue
            if candidate.get("op") == "PLAN_ACK" and int(candidate.get("generation", -1)) == int(generation):
                ack = candidate
                break
        if ack is None:
            raise SourceProtocolError("source_plan_ack_timeout")
        self._planned_records = {
            (int(generation), index): item.record_id
            for index, item in enumerate(planned)
        }
        self._planned_generation = int(generation)
        self._plan_count = int(ack.get("plan_count") or (self._plan_count + 1))
        plan_install_ns = int(ack.get("plan_install_ns") or time.monotonic_ns())
        self.telemetry["plan_install_begin_ns"] = plan_install_begin_ns
        self.telemetry["plan_install_ns"] = plan_install_ns
        self.telemetry["plan_install_ms"] = (plan_install_ns - plan_install_begin_ns) / 1e6
        self.telemetry["plan_count"] = self._plan_count
        self.telemetry["plan_range_count"] = len(planned)
        return dict(ack)

    def _raise_if_failed(self, header: Sequence[int]) -> None:
        """Fail closed on the shared failure counter. Caller holds the lock.

        Reading the header is the only reason the health check needs the lock
        at all, so every caller that already reads the header for another
        reason checks the counter here instead of taking the lock again.
        """
        if header[10]:
            detail = _read_error(self.control.buf)
            raise SourceProtocolError(f"source_thread_failed:{detail or 'unknown'}")

    def _poll_child(self) -> None:
        """Fast child liveness for the blocking wait: ``poll()`` only.

        Takes no shared lock. Process liveness is the only thing a healthy
        blocking wait needs, and the shared failure counter is only
        *additional* information.

        It is not the sole failure channel. Every site that raises the counter
        (``fail_control`` in the reader loops and in the supervisor's terminal
        block) is paired with an ``emit``-ed ``fatal`` message, after which the
        supervisor returns non-zero, so the parent observes the failure either
        as a ``fatal`` operation on the pipe or as EOF. The counter exists to
        carry the error *detail* for the case where the message is lost, which
        is why it is inspected whenever the header is read under the lock.

        Calling the authoritative check on every wait iteration was redundant
        with work already done under that lock -- READY token resolution,
        doorbell-loss recovery and timeout recovery all read the header -- and
        could stall the parent behind the very lock the source workers need in
        order to claim slots and publish READY.
        """
        self.telemetry["health_poll_count"] = int(self.telemetry.get("health_poll_count", 0)) + 1
        if self._proc is not None and self._proc.poll() is not None:
            raise SourceProtocolError("source_process_exited")

    def _check_child(self) -> None:
        if self._proc is not None and self._proc.poll() is not None:
            raise SourceProtocolError("source_process_exited")
        self.telemetry["health_authoritative_count"] = (
            int(self.telemetry.get("health_authoritative_count", 0)) + 1
        )
        with self._lock:
            header = _read_header(self.control.buf)
        self._raise_if_failed(header)

    def _resolve_ready_block(self, message: Mapping[str, Any]) -> ReadyRecord | None:
        """Turn one READY_BLOCK announcement into a verified exact token."""
        slot_index = int(message["slot_index"])
        generation = int(message["generation"])
        with self._lock:
            header = _read_header(self.control.buf)
            self._raise_if_failed(header)
            state, slot_generation, range_index, source, destination, length, ready_ns, producer_id = _slot(
                self.control.buf, slot_index
            )
            plan_generation = int(header[5])
            if self._planned_generation != plan_generation:
                raise SourceProtocolError("ready_plan_generation_mismatch")
            if state != READY or int(slot_generation) != generation:
                # A doorbell for a slot the consumer already owns, or one a
                # newer generation has replaced.  Either way this announcement
                # cannot be honoured, so it is dropped rather than raised: the
                # shared control block is the authority, and wait_ready
                # immediately re-derives the real READY token from the slot
                # table.  Raising here instead aborted the whole generation
                # with stale_ready_generation on a slow (degraded-throughput)
                # run, where a doorbell can legitimately land against a slot
                # that is IN_FLIGHT under an earlier generation.  claim_ready
                # still enforces the exact (slot, generation) token, so
                # recovering from the table cannot transfer the wrong bytes.
                return None
        return ReadyRecord(
            slot_index, int(slot_generation), int(source), int(destination), int(length),
            int(range_index), int(producer_id), int(ready_ns),
            self._planned_records.get((plan_generation, int(range_index))), plan_generation,
        )

    def _buffer_ready_block(self, message: Mapping[str, Any]) -> None:
        record = self._resolve_ready_block(message)
        if record is not None:
            self._pending_ready.append(record)

    def request_status(self, timeout_s: float = 5.0) -> dict[str, Any]:
        """Ask the source owner what generation it believes it is serving."""
        proc = getattr(self, "_proc", None)
        if proc is None or proc.stdin is None:
            return {}
        try:
            proc.stdin.write('{"op":"STATUS"}\n')
            proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError):
            return {}
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            message = self._read_message(deadline - time.monotonic())
            if message is None:
                break
            if message.get("op") == "STATUS_REPLY":
                return dict(message)
        return {}

    def _recover_ready_from_table(self) -> ReadyRecord | None:
        """Re-derive one READY ownership token straight from the slot table.

        The doorbell stream is an optimisation, not the source of truth: the
        shared control block is.  A whole-file mapping lets a small checkpoint
        be fully read before the consumer has drained every announcement, so a
        single lost or coalesced line must not leave a slot owned by nobody and
        starve the consumer until the load gate fires.  Anything found here is
        still validated by the same exact token rules as a delivered doorbell.
        """
        with self._lock:
            header = _read_header(self.control.buf)
            self._raise_if_failed(header)
            plan_generation = int(header[5])
            if self._planned_generation != plan_generation:
                return None
            for slot_index in range(SLOT_COUNT):
                (state, slot_generation, range_index, source, destination,
                 length, ready_ns, producer_id) = _slot(self.control.buf, slot_index)
                if state != READY:
                    continue
                return ReadyRecord(
                    slot_index, int(slot_generation), int(source), int(destination),
                    int(length), int(range_index), int(producer_id), int(ready_ns),
                    self._planned_records.get((plan_generation, int(range_index))),
                    plan_generation,
                )
        return None

    def wait_ready(self, timeout_s: float = 30.0) -> ReadyRecord | None:
        """Block until a READY block exists, then return its exact token.

        There is no polling loop: the source owner emits exactly one doorbell
        line per READY block and this blocks reading it.  Doorbells buffered
        during a PLAN install are served first, so an announcement is never
        lost.  A bounded slice keeps child-crash detection responsive without
        re-scanning the slot table.
        """
        if self._pending_ready:
            return self._pending_ready.pop(0)
        deadline = time.monotonic() + timeout_s
        while True:
            self._poll_child()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                # The wait budget is spent, but the shared control block is the
                # source of truth, not the doorbell stream.  A block whose
                # announcement was dropped or coalesced would otherwise be left
                # owned by nobody in READY, so make one last authoritative
                # attempt before reporting the wait as unsatisfied.
                self._check_child()
                return self._recover_ready_from_table()
            message = self._read_message(min(remaining, 0.25))
            if message is None:
                recovered = self._recover_ready_from_table()
                if recovered is not None:
                    return recovered
                continue
            operation = message.get("op")
            if operation == "fatal":
                raise SourceProtocolError(str(message.get("error")))
            if operation == "TELEMETRY":
                self.telemetry["pacer"] = message.get("telemetry")
                continue
            if operation != "READY_BLOCK":
                continue
            record = self._resolve_ready_block(message)
            if record is not None:
                return record
            # This announcement did not resolve to a usable token.  Recover an
            # owned READY block from the table rather than dropping the slot.
            recovered = self._recover_ready_from_table()
            if recovered is not None:
                return recovered

    def claim_ready(self, record: ReadyRecord) -> ReadyRecord:
        """Take the exact ``(slot_index, slot_generation)`` token."""
        with self._lock:
            header = _read_header(self.control.buf)
            if getattr(self, "_planned_generation", None) is not None and (
                record.plan_generation is None or int(record.plan_generation) != int(header[5])
            ):
                raise SourceProtocolError("stale_ready_plan_generation")
            current = _slot(self.control.buf, record.slot_index)
            if current[0] != READY or int(current[1]) != int(record.generation):
                raise SourceProtocolError("stale_ready_generation")
            values = list(header)
            _put_slot(self.control.buf, record.slot_index,
                      (IN_FLIGHT, current[1], current[2], current[3], current[4], current[5], current[6], 0))
            values[8] = max(0, values[8] - 1)
            values[11] = int(values[11]) & ~(1 << int(record.slot_index))
            _write_header_all(self.control.buf, values)
            _bump_counter(self.control.buf, 4)
        return record

    def release_slot(self, record: ReadyRecord, *, completion_ns: int | None = None) -> None:
        """Return a physical slot only after H2D completion was proven."""
        with self._lock:
            header = _read_header(self.control.buf)
            if getattr(self, "_planned_generation", None) is not None and (
                record.plan_generation is None or int(record.plan_generation) != int(header[5])
            ):
                raise SourceProtocolError("stale_release_plan_generation")
            current = _slot(self.control.buf, record.slot_index)
            if int(current[1]) != int(record.generation):
                raise SourceProtocolError("stale_release_generation")
            if current[0] != IN_FLIGHT:
                raise SourceProtocolError("release_without_completion_ownership")
            values = list(header)
            _put_slot(self.control.buf, record.slot_index,
                      (FREE, current[1], current[2], current[3], current[4], current[5], current[6],
                       int(completion_ns or time.monotonic_ns())))
            values[9] += 1
            values[11] = int(values[11]) | (1 << int(record.slot_index))
            _write_header_all(self.control.buf, values)
            _bump_counter(self.control.buf, 5)
            self.telemetry["release_count"] = int(self.telemetry.get("release_count", 0)) + 1
        # Capacity is an event, not a poll: wake waiting readers.
        self.notify_capacity()

    def notify_capacity(self) -> None:
        if self._proc is not None and self._proc.stdin is not None:
            try:
                self._proc.stdin.write('{"op":"CAPACITY"}\n')
                self._proc.stdin.flush()
            except (BrokenPipeError, ValueError, OSError):
                pass

    def wait_quiescent(self, timeout_s: float = 30.0) -> None:
        """Require all source ownership to be returned before the next PLAN."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self._check_child()
            with self._lock:
                header = _read_header(self.control.buf)
                if int(header[11]) == FREE_MASK and header[8] == 0 and header[10] == 0:
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
        by_start = sorted(operations, key=lambda item: item["memcpy_start_ns"])
        effective_levels = [
            sum(1 for item in operations if min(READER_COUNT, int(item["flags"]) & 0xff) == level)
            for level in range(READER_COUNT + 1)
        ]
        pacer_violations = _validate_memcpy_gaps(operations)
        gap_values = [
            right["memcpy_start_ns"] - left["memcpy_start_ns"]
            for left, right in zip(by_start, by_start[1:])
        ]
        span = canonical_source_span(operations)
        return {
            **self.telemetry,
            "generation": header[5], "plan_count": header[6], "next_range": header[7],
            "ready_count": header[8], "completed_count": header[9], "failed_count": header[10],
            "free_slot_mask": int(header[11]),
            "slot_states": [item[0] for item in slots],
            "counters": {name: int(value) for name, value in zip(COUNTER_NAMES, counters)},
            "slot_acquire_wait_ns": counters[0],
            "slot_acquire_wait_count": counters[1],
            "all_slots_occupied_count": counters[2],
            "ready_publish_count": counters[3],
            "ready_receive_count": counters[4],
            "release_count": counters[5],
            "ready_queue_wait_ns": counters[7] + self._doorbell_wait_ns,
            "ready_queue_wait_count": counters[8] + self._doorbell_wait_count,
            "capacity_wait_ns": counters[9],
            "capacity_wait_count": counters[10],
            "source_start_ns": [item["memcpy_start_ns"] for item in by_start],
            "source_operations": len(operations),
            "operation_count": operation_count,
            "source_operation_records": operations,
            "source_span": span,
            "pacing_wait_count": sum(1 for item in operations if item["pacing_wait_ns"]),
            "pacing_zero_delay_count": sum(1 for item in operations if not item["pacing_wait_ns"]),
            "effective_reader_concurrency": max(
                (int(item["flags"]) & 0xff for item in operations), default=0
            ),
            "effective_reader_concurrency_distribution": effective_levels,
            "time_weighted_reader_concurrency": _time_weighted_concurrency(operations),
            "mmap_map_count": sum(1 for item in operations if item["map_start_ns"]),
            "mmap_unmap_count": sum(1 for item in operations if item["munmap_start_ns"]),
            "min_source_gap_ns": min(gap_values) if gap_values else None,
            "pacer_gap_violation_count": len(pacer_violations),
            "pacer_gap_violations": pacer_violations,
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
    """Feed READY ownership into the existing GoldenQDTransport dispatcher.

    This adapter owns no CUDA work.  The dispatcher remains the sole
    H2D/event/release owner; the release callback is invoked only from its
    proven completion path.
    """

    def __init__(self, manager: SourceThreadProcess, transport: Any):
        self.manager = manager
        self.transport = transport

    def publish_all(self, ranges: Sequence[Any], *, generation: int, path: str,
                    identity: Sequence[int], destination_size: int,
                    timeout_s: float = MODEL_LOAD_GATE_S,
                    role: str = "model") -> int:
        normalized = tuple(
            SourceRange(int(item.source_offset), int(item.length), int(item.target_offset), item.record_id)
            for item in ranges
        )
        plan_install_begin_ns = time.monotonic_ns()
        self.manager.plan_once(generation=generation, path=path, identity=identity,
                               ranges=normalized, destination_size=destination_size,
                               mmap_lifecycle=getattr(self.manager, "mmap_lifecycle", "fresh"))
        plan_install_end_ns = time.monotonic_ns()
        remaining = len(normalized)
        published = 0
        claimed: list[ReadyRecord] = []
        # Ownership is tracked by the complete physical-slot token.  Slot
        # indices are reused, so a successful old generation of slot 3 must not
        # make cleanup treat a newer slot-3 generation as already submitted.
        submitted: set[tuple[int, int]] = set()
        deadline = time.monotonic() + timeout_s
        started_ns = time.monotonic_ns()
        try:
            while remaining:
                budget = max(0.01, deadline - time.monotonic())
                record = self.manager.wait_ready(budget)
                if record is None:
                    raise self._load_gate_timeout(
                        role=role, generation=generation, started_ns=started_ns,
                        gate_s=timeout_s, remaining=remaining, total=len(normalized),
                        published=published,
                    )
                record = self.manager.claim_ready(record)
                claimed.append(record)
                item = normalized[record.range_index]
                if (record.source_offset, record.destination_offset, record.nbytes) != (
                    item.source_offset, item.destination_offset, item.length
                ):
                    raise SourceProtocolError("ready_record_coverage_mismatch")
                # The dispatcher adopts this exact physical slot and its
                # generation.  There is no second FREE -> FILLING -> READY
                # producer round trip around a slot the source already filled.
                lease = self.transport.adopt_external_slot(
                    slot_index=record.slot_index,
                    external_generation=record.slot_generation,
                    declared_range=item,
                    producer_id=record.producer_id,
                )
                lease._external_release_callback = lambda rec=record: self.manager.release_slot(
                    rec, completion_ns=time.monotonic_ns()
                )
                lease._source_thread_correlation = {
                    "plan_generation": record.plan_generation,
                    "ordinal": record.range_index,
                    "slot_index": record.slot_index,
                    "slot_generation": record.slot_generation,
                    "slot_token": list(record.token),
                    "manager_ready_receive_ns": time.monotonic_ns(),
                }
                self.transport.publish(
                    lease, self._ready_record(record, item), externally_filled=True
                )
                submitted.add(record.token)
                published += 1
                remaining -= 1
        except BaseException:
            # Only claimed slots which never entered the dispatcher can be
            # released here.  Submitted ownership remains with GoldenQDTransport
            # until completion is proven; uncertainty is intentionally retained.
            for record in claimed:
                if record.token not in submitted:
                    try:
                        self.manager.release_slot(record, completion_ns=time.monotonic_ns())
                    except BaseException:
                        pass
            raise
        telemetry = getattr(self.manager, "telemetry", None)
        if isinstance(telemetry, dict):
            telemetry["plan_install_ms"] = (plan_install_end_ns - plan_install_begin_ns) / 1e6
            telemetry["source_pipeline_begin_ns"] = plan_install_end_ns
        return published

    def _load_gate_timeout(self, *, role: str, generation: int, started_ns: int,
                           gate_s: float, remaining: int, total: int,
                           published: int) -> SourceProtocolError:
        """Build the fail-closed model-load gate error with terminal evidence.

        Every field is sampled AFTER the gate has already fired, so the message
        describes the state that actually blocked the load.  Snapshot and child
        status are best-effort: a gate must still fail closed when the evidence
        path itself is broken, so an unreadable snapshot degrades to a recorded
        error marker rather than a different exception type.
        """
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1e6
        try:
            snapshot = self.manager.snapshot()
        except BaseException as exc:
            snapshot = {"snapshot_error": f"{type(exc).__name__}:{exc}"}
        try:
            status = self.manager.request_status()
        except BaseException as exc:
            status = {"status_error": f"{type(exc).__name__}:{exc}"}
        operations = list(snapshot.get("source_operation_records") or [])
        slot_states = list(snapshot.get("slot_states") or [])
        # The last operation each reader published is the most direct evidence of
        # which reader stopped working, and the offset it stopped at.
        per_reader: dict[Any, dict[str, Any]] = {}
        for item in sorted(operations, key=lambda entry: int(entry.get("ready_ns") or 0)):
            reader = item.get("reader")
            per_reader[reader] = {
                "last_offset": item.get("source_offset"),
                "last_nbytes": item.get("nbytes"),
                "last_ready_ns": item.get("ready_ns"),
                "op_wall_ns": (
                    int(item.get("memcpy_end_ns") or 0) - int(item.get("memcpy_start_ns") or 0)
                ),
            }
        gate_name = f"golden_{role}_load_timeout_{int(gate_s)}s"
        return SourceProtocolError(
            f"{gate_name}:"
            f"role={role}:"
            f"stage=model_source_publish:"
            f"elapsed_ms={elapsed_ms:.3f}:"
            f"gate_s={gate_s}:"
            f"generation={generation}:"
            f"planned_generation={getattr(self.manager, '_planned_generation', None)}:"
            f"mmap_lifecycle={getattr(self.manager, 'mmap_lifecycle', None)}:"
            f"published={published}:"
            f"remaining={remaining}:"
            f"plan_range_count={total}:"
            f"ready_depth={snapshot.get('ready_count')}:"
            f"in_flight_depth={sum(1 for state in slot_states if int(state) == 3)}:"
            f"filling_depth={sum(1 for state in slot_states if int(state) == 1)}:"
            f"free_depth={sum(1 for state in slot_states if int(state) == 0)}:"
            f"slot_states={slot_states}:"
            f"free_mask={snapshot.get('free_slot_mask')}:"
            f"failed_count={snapshot.get('failed_count')}:"
            f"next_range={snapshot.get('next_range')}:"
            f"plan_count={snapshot.get('plan_count')}:"
            f"source_operations={snapshot.get('source_operations')}:"
            f"release_count={snapshot.get('release_count')}:"
            f"capacity_wait_count={snapshot.get('capacity_wait_count')}:"
            f"capacity_wait_ns={snapshot.get('capacity_wait_ns')}:"
            f"slot_acquire_wait_count={snapshot.get('slot_acquire_wait_count')}:"
            f"slot_acquire_wait_ns={snapshot.get('slot_acquire_wait_ns')}:"
            f"all_slots_occupied_count={snapshot.get('all_slots_occupied_count')}:"
            f"ready_queue_wait_ns={snapshot.get('ready_queue_wait_ns')}:"
            f"effective_reader_concurrency={snapshot.get('effective_reader_concurrency')}:"
            f"time_weighted_reader_concurrency={snapshot.get('time_weighted_reader_concurrency')}:"
            f"pacing_wait_count={snapshot.get('pacing_wait_count')}:"
            f"pacer_gap_violation_count={snapshot.get('pacer_gap_violation_count')}:"
            f"min_source_gap_ns={snapshot.get('min_source_gap_ns')}:"
            f"mmap_map_count={snapshot.get('mmap_map_count')}:"
            f"mmap_unmap_count={snapshot.get('mmap_unmap_count')}:"
            f"last_source_start_ns={snapshot.get('source_start_ns') and max(snapshot['source_start_ns'])}:"
            f"source_span={snapshot.get('source_span')}:"
            f"per_reader={per_reader}:"
            f"child_alive={getattr(self.manager, '_proc', None) is not None and self.manager._proc.poll() is None}:"
            f"child_status={status}"
        )

    def _ready_record(self, record: ReadyRecord, item: SourceRange) -> Any:
        builder = getattr(self.transport, "_ready_record", None)
        if callable(builder):
            return builder(
                record.source_offset, record.destination_offset, record.nbytes,
                item.record_id, record.producer_id,
            )
        from .golden_qd_transport import ReadyRecord as DispatcherReadyRecord
        return DispatcherReadyRecord(
            record.source_offset, record.destination_offset, record.nbytes,
            item.record_id, record.producer_id,
        )


def _native_mmap_setup() -> Any:
    """Return the small libc surface used by the CUDA-sterile source owner."""
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


@dataclass(frozen=True)
class _ChildPlan:
    """Immutable per-generation source plan.

    Path identity, the descriptor, and (for the whole-file lifecycle) the
    single MAP_PRIVATE whole-file mapping are established exactly once at PLAN
    install.  Workers consume this state; they never re-stat, re-validate, or
    re-open anything per block.
    """

    generation: int
    path: str
    identity: tuple[int, int, int, int]
    destination_size: int
    mmap_lifecycle: str
    ranges: tuple[tuple[int, int, int, int | None], ...]
    fd: int = -1
    map_address: int = 0
    map_length: int = 0
    plan_install_ns: int = 0

    def metadata(self) -> dict[str, Any]:
        """Cross-address-space form: no descriptor or mapping travels here.

        Ranges are emitted as the same mapping shape the parent sends, so a
        reader process can hand the result straight back to :func:`build_plan`.
        Emitting tuples/lists here instead made every cross-process plan
        adoption fail with a str-index-on-list TypeError.
        """
        return {
            "generation": self.generation,
            "path": self.path,
            "identity": list(self.identity),
            "destination_size": self.destination_size,
            "mmap_lifecycle": self.mmap_lifecycle,
            "ranges": [
                {
                    "source_offset": item[0],
                    "length": item[1],
                    "destination_offset": item[2],
                    "record_id": item[3],
                }
                for item in self.ranges
            ],
        }

    @staticmethod
    def from_metadata(metadata: Mapping[str, Any], *, fd: int = -1, map_address: int = 0,
                      map_length: int = 0, plan_install_ns: int = 0) -> "_ChildPlan":
        return _ChildPlan(
            generation=int(metadata["generation"]), path=str(metadata["path"]),
            identity=tuple(int(value) for value in metadata["identity"]),
            destination_size=int(metadata["destination_size"]),
            mmap_lifecycle=str(metadata["mmap_lifecycle"]),
            ranges=tuple(
                (int(item[0]), int(item[1]), int(item[2]), item[3])
                for item in metadata["ranges"]
            ),
            fd=fd, map_address=map_address, map_length=map_length,
            plan_install_ns=plan_install_ns,
        )


def build_plan(message: Mapping[str, Any], *, open_source: bool) -> _ChildPlan:
    """Validate identity and, when this address space will read, open/map once.

    Descriptor and mapping lifecycle happens here, exactly once per model
    generation, instead of once per 64 MiB block.
    """
    lifecycle = str(message.get("mmap_lifecycle") or "fresh").lower()
    if lifecycle not in {"fresh", "whole"}:
        raise SourceProtocolError("unsupported_mmap_lifecycle")
    path = str(message["path"])
    identity = tuple(int(value) for value in message["identity"])
    ranges = tuple(
        (int(item["source_offset"]), int(item["length"]),
         int(item["destination_offset"]), item.get("record_id"))
        for item in message["ranges"]
    )
    actual = _validate_identity(path, identity)
    validate_plan(
        tuple(SourceRange(*item) for item in ranges),
        source_size=actual[2], destination_size=int(message["destination_size"]),
    )
    fd = -1
    map_address = 0
    map_length = 0
    if open_source:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
        try:
            if lifecycle == "whole":
                if actual[2] <= 0:
                    raise SourceProtocolError("empty_source_file")
                mapped = _MAPPER.mmap(
                    None, ctypes.c_size_t(actual[2]), 1, 2, fd, 0
                )
                if _map_failed(mapped):
                    raise SourceProtocolError(f"mmap_failed:{ctypes.get_errno()}")
                map_address = int(ctypes.cast(mapped, ctypes.c_void_p).value)
                map_length = int(actual[2])
        except BaseException:
            os.close(fd)
            raise
    return _ChildPlan(
        generation=int(message["generation"]), path=path, identity=actual,
        destination_size=int(message["destination_size"]), mmap_lifecycle=lifecycle,
        ranges=ranges, fd=fd, map_address=map_address, map_length=map_length,
        plan_install_ns=time.monotonic_ns(),
    )


def retire_plan(plan: "_ChildPlan | None") -> None:
    if plan is None:
        return
    if plan.map_address and _MAPPER is not None:
        _MAPPER.munmap(ctypes.c_void_p(plan.map_address), ctypes.c_size_t(plan.map_length))
    if plan.fd >= 0:
        os.close(plan.fd)


def execute_block(plan: _ChildPlan, arena_buf: Any, control_buf: Any, lock: Any,
                  pacer: Any, reader_id: int, claim: Claim, slot_wait_ns: int,
                  emit: Any, page_size: int) -> None:
    """Map, pace, copy, unmap, publish READY, and ring the doorbell once.

    No lock is held across mmap/memcpy/munmap, and nothing here stats, opens,
    or validates a descriptor: the plan already carries one validated
    descriptor and, for the whole-file lifecycle, one shared mapping.
    """
    if claim.item is None:
        raise SourceProtocolError("claim_without_item")
    source_offset, length = int(claim.item[0]), int(claim.item[1])
    target = memoryview(arena_buf)[claim.slot_index * SLOT_BYTES: claim.slot_index * SLOT_BYTES + length]
    map_start = 0
    munmap_start = 0
    munmap_end = 0
    base_address = 0
    base_length = 0
    temporary_map = False
    if plan.mmap_lifecycle == "whole":
        if source_offset < 0 or source_offset + length > plan.map_length:
            raise SourceProtocolError("mapped_source_range_out_of_bounds")
        copy_address = plan.map_address + source_offset
    else:
        aligned = (source_offset // page_size) * page_size
        base_length = source_offset - aligned + length
        map_start = time.monotonic_ns()
        mapped = _MAPPER.mmap(None, ctypes.c_size_t(base_length), 1, 2, plan.fd, aligned)
        if _map_failed(mapped):
            raise SourceProtocolError(f"mmap_failed:{ctypes.get_errno()}")
        base_address = int(ctypes.cast(mapped, ctypes.c_void_p).value)
        copy_address = base_address + source_offset - aligned
        temporary_map = True
    target_address = ctypes.addressof(ctypes.c_char.from_buffer(target))

    def _copy(mark_actual_start: Any) -> int:
        start = mark_actual_start()
        _MAPPER.memmove(ctypes.c_void_p(target_address), ctypes.c_void_p(copy_address),
                        ctypes.c_size_t(length))
        return start

    try:
        access_start, memcpy_start, waited = _paced_copy(
            pacer, control_buf, lock, _copy, reader_id, claim.range_index
        )
        memcpy_end = time.monotonic_ns()
        if temporary_map:
            munmap_start = time.monotonic_ns()
            if _MAPPER.munmap(ctypes.c_void_p(base_address), ctypes.c_size_t(base_length)) != 0:
                raise SourceProtocolError(f"munmap_failed:{ctypes.get_errno()}")
            munmap_end = time.monotonic_ns()
        ready_ns = time.monotonic_ns()
        record = (
            int(plan.generation), int(reader_id), int(threading.get_native_id()),
            int(claim.slot_index), int(claim.range_index), int(source_offset), int(length),
            int(memcpy_start), int(map_start), int(access_start),
            int(memcpy_start), int(memcpy_end), int(munmap_start),
            int(munmap_end), int(slot_wait_ns), int(waited), int(ready_ns),
            int(claim.effective_concurrency)
            | (int(plan.mmap_lifecycle == "whole") << 8)
            | (int(bool(map_start)) << 9),
        )
        with lock:
            publish_ready(control_buf, reader_id, claim, record)
    finally:
        del target
    # One doorbell per READY block.  The parent blocks on this line, so it
    # never polls the slot table.  It is emitted outside the control lock.
    emit({"op": "READY_BLOCK", "slot_index": int(claim.slot_index),
          "generation": int(claim.slot_generation), "reader_id": int(reader_id),
          "ready_ns": int(ready_ns)})


def _paced_copy(pacer: Any, control_buf: Any, lock: Any, callback: Any,
                reader_id: int, ordinal: int) -> tuple[int, int, int]:
    """Drive either pacer implementation through one copy."""
    if isinstance(pacer, SharedSourcePacer):
        return pacer.paced_copy(control_buf, lock, callback, reader_id=reader_id, ordinal=ordinal)
    return pacer.paced_copy(callback, reader_id=reader_id, ordinal=ordinal)


# Populated once per process before any reader starts.
_MAPPER: Any = None
_PAGE_SIZE: int = 4096


def _init_native() -> None:
    global _MAPPER, _PAGE_SIZE
    _MAPPER = _native_mmap_setup()
    _PAGE_SIZE = int(os.sysconf("SC_PAGE_SIZE"))


def _run_reader_loop(
    reader_id: int, *, arena_buf: Any, control_buf: Any, lock: Any, pacer: Any,
    plan_getter: Any, refresh_plan: Any, wake: Any, stop: Any, fatal: list,
    fail_control: Any, emit: Any, page_size: int, ready_barrier: Any = None,
) -> None:
    """One persistent reader: claim, copy, publish, repeat.

    Shared verbatim by the thread topology (a Python thread) and the process
    topology (a separate process running this same code), so the physical-slot
    state machine can never diverge between the two arms.

    The loop never spins.  When it cannot claim it blocks on the single wake
    channel, which the parent drives from its completion-proven slot release
    and the supervisor drives on every plan install.
    """
    if ready_barrier is not None:
        ready_barrier.wait(timeout=60.0)
    wait_started_ns = 0
    waiting = False
    while not stop.is_set():
        current = plan_getter()
        if current is None:
            # No plan installed in this address space yet.  Adopt the
            # supervisor's plan if one is published, otherwise block.
            current = refresh_plan()
            if current is None:
                wake(CAPACITY_WAIT_SLICE_S)
                continue
        try:
            with lock:
                claim = claim_block(control_buf, current)
                if claim.outcome == "claimed":
                    if waiting:
                        slot_wait_ns = max(0, time.monotonic_ns() - wait_started_ns)
                        _bump_counter(control_buf, 0, slot_wait_ns)
                        _bump_counter(control_buf, 1)
                        waiting = False
                    else:
                        slot_wait_ns = 0
                elif claim.outcome == "no_capacity":
                    # Every physical slot is FILLING, READY, or IN_FLIGHT.
                    # Count the pressure once, then block; never re-take the
                    # control lock while zero capacity exists.
                    if not waiting:
                        wait_started_ns = time.monotonic_ns()
                        waiting = True
                    _bump_counter(control_buf, 2)
                else:
                    # Exhausted or a retired generation: idle until the
                    # supervisor installs the next PLAN.
                    if waiting:
                        _bump_counter(control_buf, 0, max(0, time.monotonic_ns() - wait_started_ns))
                        _bump_counter(control_buf, 1)
                        waiting = False
        except BaseException as exc:
            fail_control(f"{type(exc).__name__}:{exc}")
            fatal.append(f"{type(exc).__name__}:{exc}")
            stop.set()
            return
        if claim.outcome != "claimed":
            started = time.monotonic_ns()
            if not wake(CAPACITY_WAIT_SLICE_S):
                _bump_counter(control_buf, 9, time.monotonic_ns() - started)
                _bump_counter(control_buf, 10)
            continue
        try:
            execute_block(
                current, arena_buf, control_buf, lock, pacer, reader_id, claim,
                slot_wait_ns, emit, page_size,
            )
        except BaseException as exc:
            fail_control(f"{type(exc).__name__}:{exc}")
            fatal.append(f"{type(exc).__name__}:{exc}")
            stop.set()
            return


class _ActiveCounter:
    """RETIRED.

    Effective concurrency is derived from the control block's own FILLING slot
    count, and a copy is in progress exactly when its slot is not FREE, so the
    supervisor's plan-transition drain needs no in-process accounting either.
    """


def install_generation_header(control_buf: Any, generation: int, plan: "_ChildPlan") -> int:
    """Atomically publish a generation and reset only its scoped state.

    Must be called under the control lock.  Two invariants matter here and are
    enforced together:

    * slot generations are *never* reset, so a released slot cannot collide
      with an old token after a new PLAN;
    * the generation-scoped counters are reset exactly once, so no model
      generation can inherit another model's counts.

    Returns the new plan count.
    """
    values = list(_read_header(control_buf))
    if int(values[11]) != FREE_MASK:
        raise SourceProtocolError("source_previous_plan_not_quiescent")
    plan_count = int(values[6]) + 1
    values[5] = int(generation)
    values[6] = plan_count
    values[7] = 0
    values[8] = 0
    values[9] = 0
    values[10] = 0
    values[11] = FREE_MASK
    for slot_index in range(SLOT_COUNT):
        old = _slot(control_buf, slot_index)
        _put_slot(control_buf, slot_index, (FREE, old[1], 0, 0, 0, 0, 0, 0))
    _write_header_all(control_buf, values)
    _reset_counters(control_buf)
    _bump_counter(control_buf, COUNTER_NAMES.index("plan_install_count"))
    _write_plan(control_buf, plan.metadata())
    return plan_count


def quiescent(control_buf: Any, lock: Any) -> bool:
    """True when no source ownership is outstanding.

    A reader that is mid-copy holds its slot in FILLING, and a block awaiting
    H2D holds it in READY or IN_FLIGHT, so an all-FREE free mask is a complete
    proof of source quiescence.
    """
    with lock:
        return int(_read_header(control_buf)[11]) == FREE_MASK


def _child_main(arena_name: str, control_name: str, lock_path: str, kind: str = "thread") -> int:
    # Do not call multiprocessing.shared_memory.SharedMemory(name=...) here:
    # that attach path starts a resource-tracker helper process and can unlink
    # parent-owned storage during child teardown.  The old
    # ``resource_tracker.unregister`` workaround is intentionally not used.
    if kind not in WORKER_KINDS:
        raise SourceProtocolError(f"unsupported_source_worker_kind:{kind!r}")
    _init_native()
    arena = _PosixAttachment(arena_name, ARENA_BYTES)
    control = _PosixAttachment(control_name, CONTROL_BYTES)
    lock = _FileLock(lock_path)
    stop = threading.Event()
    # The single wake channel.  A completion-proven slot release posts it, and
    # so does a plan install; readers block on it instead of re-taking the
    # control lock while zero capacity exists.
    capacity = threading.Semaphore(0)
    pacer = GlobalSourcePacer()
    fatal: list[str] = []
    # The installed plan lives in one holder shared by every reader.  Readers
    # still re-derive it from the control block whenever the generation moves.
    holder: dict[str, "_ChildPlan | None"] = {"plan": None}
    plan: _ChildPlan | None = None
    emit_lock = threading.Lock()
    readers: list[Any] = []

    def emit(message: Mapping[str, Any]) -> None:
        with emit_lock:
            sys.stdout.write(json.dumps(dict(message), separators=(",", ":")) + "\n")
            sys.stdout.flush()

    def fail_control(message: str) -> None:
        try:
            with lock:
                values = list(_read_header(control.buf))
                values[10] = int(values[10]) + 1
                _write_header_all(control.buf, values)
                _write_error(control.buf, message)
        except BaseException:
            pass

    def wake(timeout_s: float) -> bool:
        return capacity.acquire(timeout=max(0.0, timeout_s))

    def no_plan() -> "_ChildPlan | None":
        return None

    def current_plan() -> "_ChildPlan | None":
        return holder["plan"]

    def adopt_shared_plan() -> "_ChildPlan | None":
        """Return the plan for the generation the control block names.

        The supervisor owns plan construction and retirement.  A reader only
        ever *reads* the holder: it never builds a plan of its own, because a
        reader-built plan would race the supervisor's publication and orphan a
        descriptor and mapping that nobody can ever retire.

        If the holder somehow lags the shared generation, this returns the
        holder unchanged rather than mutating shared ownership, and the reader
        simply blocks until the supervisor publishes.
        """
        with lock:
            generation = int(_read_header(control.buf)[5])
        return holder["plan"]

    def install_generation(installed: _ChildPlan) -> int:
        with lock:
            return install_generation_header(control.buf, installed.generation, installed)

    def drain_previous() -> None:
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if quiescent(control.buf, lock):
                return
            time.sleep(0.0005)
        raise SourceProtocolError("source_previous_plan_stop_timeout")

    try:
        if arena.size != ARENA_BYTES:
            raise SourceProtocolError("arena_size_mismatch")
        _read_header(control.buf)
        if kind == "thread":
            # Every in-process reader must be live before READY is published,
            # so the reported worker count is proof rather than an assumption.
            ready_barrier = threading.Barrier(READER_COUNT + 1)
            for index in range(READER_COUNT):
                thread = threading.Thread(
                    target=_run_reader_loop,
                    args=(index,),
                    kwargs={
                        "arena_buf": arena.buf, "control_buf": control.buf, "lock": lock,
                        "pacer": pacer, "plan_getter": current_plan,
                        "refresh_plan": adopt_shared_plan, "wake": wake,
                        "stop": stop, "fatal": fatal, "fail_control": fail_control,
                        "emit": emit, "page_size": _PAGE_SIZE,
                        "ready_barrier": ready_barrier,
                    },
                    name=f"c0-source-{index}", daemon=True,
                )
                thread.start()
                readers.append(thread)
            ready_barrier.wait(timeout=60.0)
        else:
            # Reader processes cannot cross an in-process barrier.  Prove
            # liveness by each process having spawned and not yet exited;
            # waiting on a barrier here would stall READY for its full timeout.
            readers.extend(_spawn_reader_processes(
                arena_name, control_name, lock_path, emit_lock, stop
            ))
            deadline = time.monotonic() + 60.0
            while time.monotonic() < deadline:
                if all(reader.alive() for reader in readers):
                    break
                time.sleep(0.001)
            else:
                raise SourceProtocolError("source_reader_process_start_failed")
        emit({"op": "READY", "geometry": geometry(), "telemetry": {
            "threads_created_ns": time.monotonic_ns(),
            "source_worker_kind": kind,
            "persistent_fd_policy": "one_fd_per_source_generation_per_address_space",
            "whole_map_policy": "one_whole_file_map_per_address_space",
            "reader_identities": [
                {"reader_id": index, "name": getattr(reader, "name", f"c0-source-reader-{index}"),
                 "thread_id": getattr(reader, "native_id", -1)}
                for index, reader in enumerate(readers)
            ],
            "process_id": os.getpid(),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", "<unset>"),
            "shared_memory_attachment": "posix_mmap_no_resource_tracker",
            "resource_tracker_helper_process": False,
        }})

        def publish_wake() -> None:
            """One wake per reader per released slot and per installed PLAN."""
            for _ in range(READER_COUNT):
                capacity.release()
            for reader in readers:
                if isinstance(reader, _ReaderProcess):
                    reader.wake(WAKE_CAPACITY)

        assert sys.stdin is not None
        previous: _ChildPlan | None = None
        for line in sys.stdin:
            message = json.loads(line)
            operation = message.get("op")
            if operation == "STOP":
                break
            if operation == "CAPACITY":
                # A physical slot was returned after proven H2D completion.
                publish_wake()
                continue
            if operation == "STATUS":
                # Report what this source owner actually believes, so a
                # stalled transition is diagnosable from the failure alone
                # instead of inferred from counters.
                held = holder["plan"]
                with lock:
                    header_generation = int(_read_header(control.buf)[5])
                emit({
                    "op": "STATUS_REPLY",
                    "header_generation": header_generation,
                    "holder_generation": int(held.generation) if held else None,
                    "holder_ranges": len(held.ranges) if held else 0,
                    "readers_alive": [bool(reader.alive()) for reader in readers],
                    "stopped": bool(stop.is_set()),
                })
                continue
            if operation != "PLAN":
                raise SourceProtocolError("source_accepts_only_plan_and_capacity_messages")
            # Retract the plan first so no reader can claim against the old
            # generation while the transition is in progress.  A reader that is
            # mid-copy finishes its own block; every other reader falls back to
            # the shared control block and adopts the new generation itself.
            plan = None
            holder["plan"] = None
            publish_wake()
            if previous is not None:
                drain_previous()
            installed = build_plan(message, open_source=(kind == "thread"))
            # Publish the descriptor and mapping BEFORE the control block names
            # this generation.  Readers only read the holder, so publishing
            # first guarantees a reader can never observe a header generation
            # it has no plan for, and guarantees every plan is retired exactly
            # once by its single owner.
            holder["plan"] = installed
            plan = installed
            try:
                plan_count = install_generation(installed)
            except BaseException:
                holder["plan"] = None
                retire_plan(installed)
                raise
            publish_wake()
            emit({"op": "PLAN_ACK", "generation": installed.generation,
                  "plan_count": plan_count, "ack_ns": time.monotonic_ns(),
                  "plan_install_ns": installed.plan_install_ns})
            retire_plan(previous)
            previous = installed
        stop.set()
        publish_wake()
        if kind == "thread":
            for reader in readers:
                reader.join(timeout=10.0)
        else:
            for reader in readers:
                reader.stop()
            for reader in readers:
                reader.join(timeout=5.0)
        if fatal:
            fail_control(fatal[0])
            emit({"op": "fatal", "error": fatal[0]})
        emit({"op": "TELEMETRY", "telemetry": pacer.telemetry()})
        retire_plan(previous)
        return 0 if not fatal else 1
    except BaseException as exc:
        emit({"op": "fatal", "error": f"{type(exc).__name__}:{exc}"})
        return 1
    finally:
        arena.close()
        control.close()
        lock.close()


class _ReaderProcess:
    """One persistent CUDA-sterile reader process.

    Isolation boundary only: the reader kernel is the same ``_run_reader_loop``
    used by the thread topology.  The supervisor relays this process's stdout
    doorbells onto its own stdout, so the parent still sees exactly one line per
    READY block, and writes one-byte wake tokens into its stdin.
    """

    def __init__(self, reader_id: int, arena_name: str, control_name: str, lock_path: str,
                 emit_lock: Any, stop: Any):
        self.reader_id = int(reader_id)
        self.name = f"c0-source-reader-{reader_id}"
        self.native_id = -1
        self._proc: Any = None
        self._relay: Any = None
        self._arena_name = arena_name
        self._control_name = control_name
        self._lock_path = lock_path
        self._emit_lock = emit_lock
        self._stop = stop

    def start(self) -> None:
        self._proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--source-reader",
             self._arena_name, self._control_name, self._lock_path, str(self.reader_id)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, close_fds=True,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": ""},
        )
        self.native_id = int(getattr(self._proc, "pid", 0) or 0)
        self._relay = threading.Thread(target=self._relay_loop, daemon=True)
        self._relay.start()

    def _relay_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            for line in self._proc.stdout:
                with self._emit_lock:
                    sys.stdout.write(line)
                    sys.stdout.flush()
        except BaseException:
            pass
        self._stop.set()

    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def wake(self, byte: bytes) -> None:
        if self._proc is not None and self._proc.stdin is not None:
            try:
                self._proc.stdin.write(byte.decode("ascii"))
                self._proc.stdin.flush()
            except (BrokenPipeError, ValueError, OSError):
                pass

    def stop(self) -> None:
        self.wake(WAKE_STOP)

    def join(self, timeout: float | None = None) -> None:
        if self._proc is not None:
            try:
                self._proc.wait(timeout=timeout)
            except Exception:
                self._proc.kill()


def _spawn_reader_processes(arena_name: str, control_name: str, lock_path: str,
                            emit_lock: Any, stop: Any) -> list["_ReaderProcess"]:
    """Start the four independent persistent reader processes."""
    processes = [_ReaderProcess(index, arena_name, control_name, lock_path, emit_lock, stop)
                 for index in range(READER_COUNT)]
    for process in processes:
        process.start()
    return processes


def _reader_main(arena_name: str, control_name: str, lock_path: str, reader_id: str) -> int:
    """Entry point for one independent persistent reader process.

    The wake channel is a blocking read of the supervisor's stdin, so this
    reader genuinely sleeps while no capacity or plan change exists.  It never
    polls the control block.
    """
    _init_native()
    arena = _PosixAttachment(arena_name, ARENA_BYTES)
    control = _PosixAttachment(control_name, CONTROL_BYTES)
    lock = _FileLock(lock_path)
    stop = threading.Event()
    fatal: list[str] = []
    reader = int(reader_id)
    holder: dict[str, "_ChildPlan | None"] = {"plan": None}
    pacer = SharedSourcePacer()
    emit_lock = threading.Lock()
    wakes: "queue.Queue[bytes]" = queue.Queue()

    def emit(message: Mapping[str, Any]) -> None:
        with emit_lock:
            sys.stdout.write(json.dumps(dict(message), separators=(",", ":")) + "\n")
            sys.stdout.flush()

    def fail_control(message: str) -> None:
        try:
            with lock:
                values = list(_read_header(control.buf))
                values[10] = int(values[10]) + 1
                _write_header_all(control.buf, values)
                _write_error(control.buf, message)
        except BaseException:
            pass

    def current_plan() -> "_ChildPlan | None":
        return holder["plan"]

    def refresh_plan() -> "_ChildPlan | None":
        """Adopt the supervisor's installed plan for this address space.

        Runs at most once per generation, and only when the shared generation
        differs from the one this reader already holds.  The descriptor and,
        for the whole-file lifecycle, this process's own whole-file mapping are
        established here and then reused for every block.
        """
        with lock:
            generation = int(_read_header(control.buf)[5])
            if generation == 0:
                return holder["plan"]
            if holder["plan"] is not None and holder["plan"].generation == generation:
                return holder["plan"]
            metadata = _read_plan(control.buf)
            if int(metadata["generation"]) != generation:
                return holder["plan"]
        adopted = build_plan(metadata, open_source=True)
        previous = holder["plan"]
        holder["plan"] = adopted
        retire_plan(previous)
        return adopted

    def wake(timeout_s: float) -> bool:
        """Block on the supervisor's next wake byte."""
        try:
            wakes.get(timeout=max(0.0, timeout_s))
            return True
        except queue.Empty:
            return False

    def stdin_pump() -> None:
        stream = sys.stdin.buffer if sys.stdin is not None else None
        if stream is None:
            stop.set()
            return
        try:
            while True:
                byte = stream.read(1)
                if not byte:
                    stop.set()
                    return
                if byte == WAKE_STOP:
                    stop.set()
                    return
                wakes.put(byte)
        except BaseException:
            stop.set()

    try:
        pump = threading.Thread(target=stdin_pump, daemon=True)
        pump.start()
        _run_reader_loop(
            reader, arena_buf=arena.buf, control_buf=control.buf, lock=lock,
            pacer=pacer, plan_getter=current_plan, refresh_plan=refresh_plan,
            wake=wake, stop=stop, fatal=fatal, fail_control=fail_control,
            emit=emit, page_size=_PAGE_SIZE,
        )
        return 0 if not fatal else 1
    except BaseException as exc:
        emit({"op": "fatal", "error": f"{type(exc).__name__}:{exc}"})
        return 1
    finally:
        stop.set()
        retire_plan(holder["plan"])
        arena.close()
        control.close()
        lock.close()


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-child", nargs=4, metavar=("ARENA", "CONTROL", "LOCK", "KIND"))
    parser.add_argument("--source-reader", nargs=4, metavar=("ARENA", "CONTROL", "LOCK", "READER"))
    args = parser.parse_args()
    if args.source_child:
        return _child_main(*args.source_child)
    if args.source_reader:
        return _reader_main(*args.source_reader)
    parser.error("source module is not a standalone CLI")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "ARENA_BYTES", "CONTROL_BYTES", "COUNTER_NAMES", "EXPERIMENT_ENV", "FREE", "FILLING",
    "FREE_MASK", "READY", "IN_FLIGHT", "PACER_GAP_NS", "READER_COUNT", "SLOT_BYTES", "SLOT_COUNT",
    "THREAD_COUNT", "WORKER_KINDS", "WORKER_KIND_ENV", "GlobalSourcePacer", "ReadyRecord",
    "SharedSourcePacer", "SourcePlanBridge", "SourceProtocolError", "SourceRange",
    "SourceThreadProcess", "canonical_source_span", "claim_block", "enabled", "geometry",
    "new_control_buffer", "publish_ready", "validate_plan", "worker_kind",
]
