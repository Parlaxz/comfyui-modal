"""Preplanned source-to-CUDA extent transport.

The planner fixes every source and destination offset before execution. Source
workers fill those offsets directly in reusable extent buffers; a buffer is
submitted only after all of its reads complete.
"""

from __future__ import annotations

import threading
import time
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence, cast


def _cpu_allocation_identity() -> dict[str, Any]:
    """Expose the existing runtime allocation identity without changing it."""
    try:
        from .runtime_shape import runtime_shape_config

        requested = int(runtime_shape_config().cpu_request)
        source = "runtime_shape_config.cpu_request"
    except Exception:
        try:
            requested = int(os.environ.get("COMFYMODAL_V2_CPU_REQUEST", "0") or 0)
        except (TypeError, ValueError):
            requested = 0
        source = "COMFYMODAL_V2_CPU_REQUEST"
    return {
        "cpu_request": requested,
        "cpu": requested,
        "identity_source": source,
    }


class ExtentTransportError(RuntimeError):
    pass


class ExtentState(str, Enum):
    FREE = "free"
    FILLING = "filling"
    READY = "ready"
    IN_FLIGHT = "in_flight"


@dataclass(frozen=True)
class PlannedRead:
    source_offset: int
    destination_offset: int
    length: int
    extent_index: int
    read_index: int


@dataclass(frozen=True)
class PlannedExtent:
    extent_index: int
    destination_offset: int
    length: int
    reads: tuple[PlannedRead, ...]


@dataclass
class _ExtentSlot:
    index: int
    buffer: Any
    extent_index: int | None = None
    state: ExtentState = ExtentState.FREE


@dataclass
class _ExtentRuntime:
    plan: PlannedExtent
    slot: _ExtentSlot | None = None
    completed_reads: int = 0
    submitted: bool = False
    completed: bool = False


@dataclass
class _PhysicalRead:
    producer_id: int
    source_offset: int
    destination_offset: int
    requested_bytes: int
    returned_bytes: int
    retry_number: int
    start_ns: int
    end_ns: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "producer_id": self.producer_id,
            "source_offset": self.source_offset,
            "destination_offset": self.destination_offset,
            "requested_bytes": self.requested_bytes,
            "returned_bytes": self.returned_bytes,
            "retry_number": self.retry_number,
            "short_read": self.returned_bytes < self.requested_bytes,
            "syscall_enter_monotonic_ns": self.start_ns,
            "syscall_exit_monotonic_ns": self.end_ns,
            "error": self.error,
        }


@dataclass
class _PipelineTelemetry:
    configured_source_qd: int
    configured_source_block_bytes: int
    configured_h2d_copy_bytes: int
    configured_h2d_inflight_depth: int
    configured_source_capacity: int
    source_qd_depth: int = 0
    max_source_qd: int = 0
    source_qd_target_ns: int = 0
    source_qd_started_ns: int | None = None
    source_qd_last_ns: int | None = None
    source_active_interval_start_ns: int | None = None
    source_active_interval_end_ns: int | None = None
    source_qd_occupancy_ns: dict[int, int] = field(default_factory=dict)
    source_qd_integral_ns: int = 0
    source_worker_busy_ns: int = 0
    _state_lock: threading.RLock = field(
        default_factory=threading.RLock, repr=False, compare=False
    )
    source_reads: int = 0
    source_bytes: int = 0
    h2d_copy_count: int = 0
    h2d_bytes: int = 0
    h2d_completion_count: int = 0
    h2d_completed_bytes: int = 0
    h2d_events: list[dict[str, Any]] = field(default_factory=list)
    next_h2d_token: int = 1
    h2d_inflight_depth: int = 0
    max_h2d_inflight_depth: int = 0
    source_capacity_wait_ns: int = 0
    source_capacity_wait_count: int = 0
    ready_queue_wait_ns: int = 0
    ready_queue_wait_count: int = 0
    h2d_capacity_wait_ns: int = 0
    h2d_capacity_wait_count: int = 0
    source_start_ns: int | None = None
    source_end_ns: int | None = None
    ready_start_ns: int | None = None
    ready_end_ns: int | None = None
    h2d_start_ns: int | None = None
    h2d_end_ns: int | None = None
    physical_reads: list[_PhysicalRead] = field(default_factory=list)
    source_qd_timeline: list[dict[str, int]] = field(default_factory=list)
    source_worker_timing: dict[int, dict[str, Any]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def source_transition(self, delta: int, producer_id: int) -> None:
        """Record one reader transition and integrate depth over elapsed time.

        The active interval begins at the first physical reader entry and ends
        when the last reader exits.  Thus setup before the first read and
        teardown after the last read are not in the denominator, while genuine
        QD0 gaps between reads remain visible in the occupancy integral.
        """
        with self._state_lock:
            now = time.monotonic_ns()
            if self.source_qd_last_ns is None:
                self.source_active_interval_start_ns = now
                self.source_qd_started_ns = now
            else:
                elapsed = max(0, now - self.source_qd_last_ns)
                self.source_qd_occupancy_ns[self.source_qd_depth] = (
                    self.source_qd_occupancy_ns.get(self.source_qd_depth, 0) + elapsed
                )
                self.source_qd_integral_ns += self.source_qd_depth * elapsed
            self.source_qd_depth += delta
            if self.source_qd_depth < 0:
                raise ExtentTransportError("source QD became negative")
            self.max_source_qd = max(self.max_source_qd, self.source_qd_depth)
            self.source_qd_last_ns = now
            if self.source_qd_depth == 0:
                self.source_active_interval_end_ns = now
            else:
                # A later burst keeps the same active interval so QD0 gaps
                # remain in the denominator rather than being discarded.
                self.source_active_interval_end_ns = None
            self.source_qd_timeline.append({
                "timestamp_ns": now,
                "depth": self.source_qd_depth,
                "delta": delta,
                "producer_id": producer_id,
            })

    def snapshot(self) -> dict[str, Any]:
        active_start = self.source_active_interval_start_ns
        active_end = self.source_active_interval_end_ns
        if active_start is not None and active_end is None:
            active_end = self.source_qd_last_ns or time.monotonic_ns()
        qd_wall = (
            None if active_start is None or active_end is None
            else max(0, active_end - active_start)
        )
        occupancy_ns = {
            depth: self.source_qd_occupancy_ns.get(depth, 0)
            for depth in range(self.configured_source_qd + 1)
        }
        for depth, value in self.source_qd_occupancy_ns.items():
            occupancy_ns.setdefault(depth, value)
        integral_ns = self.source_qd_integral_ns
        # A failed/incomplete operation can be snapshotted while a reader is
        # open.  Close that final interval for diagnostics without claiming a
        # completed transport.
        if self.source_qd_last_ns is not None and active_end is not None and active_end > self.source_qd_last_ns:
            elapsed = active_end - self.source_qd_last_ns
            occupancy_ns[self.source_qd_depth] = occupancy_ns.get(self.source_qd_depth, 0) + elapsed
            integral_ns += self.source_qd_depth * elapsed
        target_ns = occupancy_ns.get(self.configured_source_qd, 0)
        occupancy_ms = {str(key): value / 1e6 for key, value in occupancy_ns.items()}
        occupancy_ns_json = {str(key): value for key, value in occupancy_ns.items()}
        source_wall = (
            None
            if self.source_start_ns is None or self.source_end_ns is None
            else max(0, self.source_end_ns - self.source_start_ns)
        )
        h2d_wall = (
            None
            if self.h2d_start_ns is None or self.h2d_end_ns is None
            else max(0, self.h2d_end_ns - self.h2d_start_ns)
        )
        ready_wall = (
            None
            if self.ready_start_ns is None or self.ready_end_ns is None
            else max(0, self.ready_end_ns - self.ready_start_ns)
        )
        cpu_allocation = _cpu_allocation_identity()
        return {
            "cpu_request": cpu_allocation["cpu_request"],
            "cpu_allocation": cpu_allocation,
            "configured_source_qd": self.configured_source_qd,
            "configured_source_capacity": self.configured_source_capacity,
            "source_capacity_semantics": "buffering_work_capacity_only",
            "achieved_source_qd_max": self.max_source_qd,
            "achieved_source_qd_mean": (
                integral_ns / qd_wall
                if qd_wall else 0.0
            ),
            "achieved_qd_mean": integral_ns / qd_wall if qd_wall else 0.0,
            "achieved_qd_max": self.max_source_qd,
            "source_active_interval_start_ns": active_start,
            "source_active_interval_end_ns": active_end,
            "source_active_wall_ns": qd_wall,
            "source_active_wall_ms": None if qd_wall is None else qd_wall / 1e6,
            "source_active_start_ns": active_start,
            "source_active_end_ns": active_end,
            "source_active_duration_ns": qd_wall,
            "source_active_duration_ms": None if qd_wall is None else qd_wall / 1e6,
            "active_source_interval_start_ns": active_start,
            "active_source_interval_end_ns": active_end,
            "active_source_wall_ns": qd_wall,
            "active_source_wall_ms": None if qd_wall is None else qd_wall / 1e6,
            "source_qd_integral_ns": integral_ns,
            "qd_occupancy_ns": occupancy_ns_json,
            "qd_occupancy_ms": occupancy_ms,
            "milliseconds_at_qd": occupancy_ms,
            "source_qd_time_ns": occupancy_ns_json,
            "source_qd_time_ms": occupancy_ms,
            "time_at_qd_ns": occupancy_ns_json,
            "time_at_qd_ms": occupancy_ms,
            "source_qd_target_ns": target_ns,
            "configured_source_block_bytes": self.configured_source_block_bytes,
            "configured_h2d_copy_bytes": self.configured_h2d_copy_bytes,
            "configured_h2d_inflight_depth": self.configured_h2d_inflight_depth,
            "achieved_h2d_inflight_depth_max": self.max_h2d_inflight_depth,
            "source_capacity_wait_ns": self.source_capacity_wait_ns,
            "source_capacity_wait_ms": self.source_capacity_wait_ns / 1e6,
            "source_capacity_wait_count": self.source_capacity_wait_count,
            "ready_queue_wait_ns": self.ready_queue_wait_ns,
            "ready_queue_wait_ms": self.ready_queue_wait_ns / 1e6,
            "ready_queue_wait_count": self.ready_queue_wait_count,
            "h2d_capacity_wait_ns": self.h2d_capacity_wait_ns,
            "h2d_capacity_wait_ms": self.h2d_capacity_wait_ns / 1e6,
            "h2d_capacity_wait_count": self.h2d_capacity_wait_count,
            "source_read_count": self.source_reads,
            "source_read_bytes": self.source_bytes,
            "source_requested_bytes": sum(
                event.requested_bytes for event in self.physical_reads
            ),
            "source_returned_bytes": sum(
                event.returned_bytes for event in self.physical_reads
            ),
            "h2d_copy_count": self.h2d_copy_count,
            "h2d_copy_bytes": self.h2d_bytes,
            "h2d_copy_bytes_total": self.h2d_bytes,
            "h2d_submit_count": self.h2d_copy_count,
            "h2d_completion_count": self.h2d_completion_count,
            "h2d_submitted_bytes": self.h2d_bytes,
            "h2d_completed_bytes": self.h2d_completed_bytes,
            "h2d_events": [dict(event) for event in self.h2d_events],
            "source_wall_ms": None if source_wall is None else source_wall / 1e6,
            "ready_queue_wall_ms": None if ready_wall is None else ready_wall / 1e6,
            "h2d_stream_span_ms": None if h2d_wall is None else h2d_wall / 1e6,
            "source_qd_timeline": list(self.source_qd_timeline),
            "source_worker_busy_ns": self.source_worker_busy_ns,
            "source_worker_busy_ms": self.source_worker_busy_ns / 1e6,
            "source_worker_busy_time_ns": self.source_worker_busy_ns,
            "source_worker_busy_time_ms": self.source_worker_busy_ns / 1e6,
            "physical_reads": [event.to_dict() for event in self.physical_reads],
            "source_worker_timing": {
                str(key): dict(value) for key, value in self.source_worker_timing.items()
            },
            "errors": list(self.errors),
        }


def plan_preplanned_extents(
    total_bytes: int,
    source_block_bytes: int,
    h2d_copy_bytes: int,
    *,
    source_offset: int = 0,
    destination_offset: int = 0,
) -> tuple[PlannedExtent, ...]:
    """Plan source reads and H2D extents without consulting runtime state."""
    for name, value in (
        ("total_bytes", total_bytes),
        ("source_block_bytes", source_block_bytes),
        ("h2d_copy_bytes", h2d_copy_bytes),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    if source_block_bytes < 1 or h2d_copy_bytes < 1:
        raise ValueError("source_block_bytes and h2d_copy_bytes must be positive")
    if source_offset < 0 or destination_offset < 0:
        raise ValueError("offsets must be non-negative")
    result: list[PlannedExtent] = []
    remaining = total_bytes
    extent_index = 0
    cursor = 0
    while remaining:
        extent_length = min(h2d_copy_bytes, remaining)
        reads: list[PlannedRead] = []
        extent_cursor = 0
        read_index = 0
        while extent_cursor < extent_length:
            length = min(source_block_bytes, extent_length - extent_cursor)
            reads.append(PlannedRead(
                source_offset + cursor + extent_cursor,
                destination_offset + cursor + extent_cursor,
                length,
                extent_index,
                read_index,
            ))
            extent_cursor += length
            read_index += 1
        result.append(PlannedExtent(
            extent_index,
            destination_offset + cursor,
            extent_length,
            tuple(reads),
        ))
        cursor += extent_length
        remaining -= extent_length
        extent_index += 1
    return tuple(result)


def validate_preplanned_extents(
    extents: Sequence[PlannedExtent],
    total_bytes: int,
    *,
    source_offset: int = 0,
    destination_offset: int = 0,
) -> tuple[bool, str]:
    """Check exact, corresponding source/destination coverage.

    ``source_offset`` and ``destination_offset`` are explicit bases.  A
    safetensors data section commonly starts after a nonzero header while the
    CUDA destination starts at zero; treating both ranges as zero-based would
    reject a valid plan (or invite callers to weaken the coverage check).
    """
    if (
        isinstance(total_bytes, bool)
        or not isinstance(total_bytes, int)
        or total_bytes < 0
        or isinstance(source_offset, bool)
        or not isinstance(source_offset, int)
        or source_offset < 0
        or isinstance(destination_offset, bool)
        or not isinstance(destination_offset, int)
        or destination_offset < 0
    ):
        return False, "invalid_extent_bases"
    reads = [read for extent in extents for read in extent.reads]
    source = sorted((read.source_offset, read.source_offset + read.length) for read in reads)
    destination = sorted((read.destination_offset, read.destination_offset + read.length) for read in reads)
    expected_source_end = source_offset + total_bytes
    expected_destination_end = destination_offset + total_bytes
    for read in reads:
        if (
            isinstance(read.length, bool)
            or not isinstance(read.length, int)
            or read.length <= 0
            or read.source_offset < source_offset
            or read.source_offset + read.length > expected_source_end
            or read.destination_offset < destination_offset
            or read.destination_offset + read.length > expected_destination_end
            or read.destination_offset - destination_offset
            != read.source_offset - source_offset
        ):
            return False, "read_destination_mismatch"
    for spans, name in ((source, "source"), (destination, "destination")):
        cursor = source_offset if name == "source" else destination_offset
        for start, end in spans:
            if start != cursor or end <= start:
                return False, f"{name}_gap_or_overlap"
            cursor = end
        expected_end = expected_source_end if name == "source" else expected_destination_end
        if cursor != expected_end:
            return False, f"{name}_incomplete"
    for extent in extents:
        if extent.length <= 0 or extent.length > total_bytes:
            return False, "invalid_extent_length"
        if sum(read.length for read in extent.reads) != extent.length:
            return False, "extent_length_mismatch"
        if (
            extent.destination_offset < destination_offset
            or extent.destination_offset + extent.length > expected_destination_end
            or not extent.reads
            or extent.reads[0].destination_offset != extent.destination_offset
            or any(
                read.destination_offset < extent.destination_offset
                or read.destination_offset + read.length
                > extent.destination_offset + extent.length
                for read in extent.reads
            )
            or extent.reads
            and extent.reads[0].extent_index != extent.extent_index
            or any(read.extent_index != extent.extent_index for read in extent.reads)
        ):
            return False, "extent_identity_mismatch"
        extent_cursor = extent.destination_offset
        for read in sorted(extent.reads, key=lambda item: item.destination_offset):
            if read.destination_offset != extent_cursor:
                return False, "extent_read_gap_or_overlap"
            extent_cursor += read.length
        if extent_cursor != extent.destination_offset + extent.length:
            return False, "extent_read_incomplete"
    if [extent.extent_index for extent in extents] != list(range(len(extents))):
        return False, "extent_index_sequence"
    return True, "ok"


class PreplannedExtentTransport:
    """Bounded source workers plus an independently bounded H2D dispatcher."""

    def __init__(
        self,
        *,
        source_qd: int,
        source_block_bytes: int,
        h2d_copy_bytes: int,
        h2d_inflight_depth: int,
        source_capacity: int,
        buffers: Sequence[Any] | None = None,
        buffer_factory: Callable[[int], Any] | None = None,
        ready_queue_capacity: int | None = None,
        diagnostics: bool = True,
        metadata: Mapping[str, Any] | None = None,
        cleanup_timeout: float = 1.0,
    ) -> None:
        values = {
            "source_qd": source_qd,
            "source_block_bytes": source_block_bytes,
            "h2d_copy_bytes": h2d_copy_bytes,
            "h2d_inflight_depth": h2d_inflight_depth,
            "source_capacity": source_capacity,
        }
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in values.values()):
            raise ValueError("preplanned transport dimensions must be positive integers")
        self.source_qd = source_qd
        self.source_block_bytes = source_block_bytes
        self.h2d_copy_bytes = h2d_copy_bytes
        self.h2d_inflight_depth = h2d_inflight_depth
        self.source_capacity = source_capacity
        self.ready_queue_capacity = h2d_inflight_depth if ready_queue_capacity is None else ready_queue_capacity
        if self.ready_queue_capacity < 1:
            raise ValueError("ready_queue_capacity must be positive")
        if (
            isinstance(cleanup_timeout, bool)
            or not isinstance(cleanup_timeout, (int, float))
            or cleanup_timeout <= 0
        ):
            raise ValueError("cleanup_timeout must be positive")
        self.cleanup_timeout = float(cleanup_timeout)
        extent_slots = max(1, h2d_inflight_depth)
        if buffers is not None and len(buffers) != extent_slots:
            raise ValueError("buffers must match H2D extent capacity")
        if buffers is not None and buffer_factory is not None:
            raise ValueError("provide buffers or buffer_factory, not both")
        self.buffers = tuple(
            buffers[i] if buffers is not None else (
                buffer_factory(h2d_copy_bytes) if buffer_factory else bytearray(h2d_copy_bytes)
            )
            for i in range(extent_slots)
        )
        self.diagnostics = bool(diagnostics)
        self.metadata = dict(metadata or {})
        self.telemetry: _PipelineTelemetry | None = None
        self.last_extents: tuple[PlannedExtent, ...] = ()

    @staticmethod
    def _buffer_slice(buffer: Any, offset: int, length: int) -> Any:
        try:
            return memoryview(buffer)[offset : offset + length]
        except TypeError:
            return buffer[offset : offset + length]

    def execute(
        self,
        extents: Sequence[PlannedExtent],
        reader: Any,
        backend: Any = None,
        *,
        total_bytes: int,
        materialize_output: bool = True,
        h2d_observer: Any = None,
        source_offset: int | None = None,
        destination_offset: int | None = None,
        source_only: bool = False,
    ) -> dict[str, Any]:
        """Execute the preplanned source path, optionally without H2D.

        ``source_only`` is an explicit control arm, not a backend fallback.  It
        uses the same planned reads, source workers, buffers, and join boundary
        as the integrated path, but retires each extent at source completion.
        Consequently no dispatcher thread, CUDA backend, or H2D observer is
        created for that arm.
        """
        if source_only and h2d_observer is not None:
            raise ExtentTransportError("source_only_cannot_observe_h2d")
        if not source_only and backend is None:
            raise ExtentTransportError("integrated_execution_requires_backend")
        source_base = (
            min(
                (read.source_offset for extent in extents for read in extent.reads),
                default=0,
            )
            if source_offset is None
            else source_offset
        )
        destination_base = (
            min(
                (read.destination_offset for extent in extents for read in extent.reads),
                default=0,
            )
            if destination_offset is None
            else destination_offset
        )
        ok, reason = validate_preplanned_extents(
            extents,
            total_bytes,
            source_offset=source_base,
            destination_offset=destination_base,
        )
        if not ok:
            raise ExtentTransportError(reason)
        self.last_extents = tuple(extents)
        telemetry = _PipelineTelemetry(
            self.source_qd,
            self.source_block_bytes,
            self.h2d_copy_bytes,
            self.h2d_inflight_depth,
            self.source_capacity,
        )
        self.telemetry = telemetry
        if extents:
            telemetry.source_start_ns = time.monotonic_ns()
        runtimes = [_ExtentRuntime(plan) for plan in extents]
        slots = [_ExtentSlot(index, buffer) for index, buffer in enumerate(self.buffers)]
        max_extent_length = max((extent.length for extent in extents), default=0)
        for slot in slots:
            try:
                capacity = int(slot.buffer.numel()) if hasattr(slot.buffer, "numel") else len(slot.buffer)
            except (TypeError, ValueError, AttributeError) as exc:
                raise ExtentTransportError("extent_buffer_capacity_unknown") from exc
            if capacity < max_extent_length or capacity < self.h2d_copy_bytes:
                raise ExtentTransportError(
                    f"extent_buffer_capacity:{capacity}<{self.h2d_copy_bytes}"
                )
        backend_destination = getattr(backend, "destination", None) if not source_only else None
        # The production CUDA destination is fixed-capacity (and exposes
        # ``numel``).  Test/adaptor destinations such as bytearray are
        # intentionally growable, so their capacity is enforced by the
        # backend's write protocol rather than rejected here.
        if backend_destination is not None and hasattr(backend_destination, "numel"):
            try:
                destination_capacity = int(backend_destination.numel()) if hasattr(backend_destination, "numel") else len(backend_destination)
            except (TypeError, ValueError, AttributeError) as exc:
                raise ExtentTransportError("destination_capacity_unknown") from exc
            if destination_capacity < destination_base + total_bytes:
                raise ExtentTransportError("destination_capacity_insufficient")
        meta = threading.Condition()
        source_slots = threading.BoundedSemaphore(self.source_capacity)
        next_read = 0
        read_jobs = [read for extent in extents for read in extent.reads]
        next_lock = threading.Lock()
        ready: list[int] = []
        inflight: dict[int, tuple[Any, int, int, int | None, int]] = {}
        failure: list[BaseException] = []
        abort = threading.Event()

        def fail(exc: BaseException) -> None:
            if not failure:
                failure.append(exc)
            abort.set()
            with meta:
                meta.notify_all()

        def extent_slot(runtime: _ExtentRuntime) -> _ExtentSlot:
            with meta:
                while runtime.slot is None:
                    if abort.is_set():
                        raise ExtentTransportError("source pipeline aborted")
                    candidate = slots[runtime.plan.extent_index % len(slots)]
                    if candidate.state == ExtentState.FREE:
                        candidate.state = ExtentState.FILLING
                        candidate.extent_index = runtime.plan.extent_index
                        runtime.slot = candidate
                        break
                    meta.wait(0.001)
                assert runtime.slot is not None
                return runtime.slot

        def source_worker(producer_id: int) -> None:
            nonlocal next_read
            worker = telemetry.source_worker_timing.setdefault(producer_id, {
                "read_count": 0,
                "read_bytes": 0,
                "first_start_ns": None,
                "last_end_ns": None,
                "wall_ms": 0.0,
                "busy_ns": 0,
                "busy_ms": 0.0,
            })
            try:
                while not abort.is_set():
                    with next_lock:
                        if next_read >= len(read_jobs):
                            return
                        item = read_jobs[next_read]
                        next_read += 1
                    runtime = runtimes[item.extent_index]
                    slot = extent_slot(runtime)
                    wait_start = time.monotonic_ns()
                    acquired = source_slots.acquire(timeout=1.0)
                    wait_ns = max(0, time.monotonic_ns() - wait_start)
                    if wait_ns:
                        telemetry.source_capacity_wait_ns += wait_ns
                        telemetry.source_capacity_wait_count += 1
                    if not acquired:
                        raise ExtentTransportError("source capacity wait timed out")
                    try:
                        offset = item.source_offset
                        destination = item.destination_offset - runtime.plan.destination_offset
                        remaining = item.length
                        retry = 0
                        first_start = None
                        while remaining:
                            target = self._buffer_slice(slot.buffer, destination, remaining)
                            started = time.monotonic_ns()
                            if first_start is None:
                                first_start = started
                            if telemetry.source_qd_depth == 0:
                                telemetry.source_transition(1, producer_id)
                            else:
                                telemetry.source_transition(1, producer_id)
                            error_text = None
                            returned = 0
                            try:
                                if callable(getattr(reader, "readinto", None)):
                                    returned = reader.readinto(target, offset, producer_id)
                                else:
                                    payload = reader(offset, remaining)
                                    if not isinstance(payload, (bytes, bytearray, memoryview)):
                                        raise TypeError("source reader must return bytes-like data")
                                    returned = len(payload)
                                    if returned > remaining:
                                        raise ValueError("source reader returned invalid byte count")
                                    target[:returned] = payload
                                if not isinstance(returned, int) or isinstance(returned, bool):
                                    raise TypeError("source reader must return an integer byte count")
                                if returned < 0 or returned > remaining:
                                    raise ValueError("source reader returned invalid byte count")
                            except BaseException as exc:
                                error_text = f"{type(exc).__name__}:{exc}"
                                returned = 0
                                raise
                            finally:
                                ended = time.monotonic_ns()
                                telemetry.source_transition(-1, producer_id)
                                busy_ns = max(0, ended - started)
                                worker["busy_ns"] += busy_ns
                                worker["busy_ms"] += busy_ns / 1e6
                                telemetry.source_worker_busy_ns += busy_ns
                                telemetry.physical_reads.append(_PhysicalRead(
                                    producer_id, offset, item.destination_offset + (offset - item.source_offset),
                                    remaining, returned, retry, started, ended, error_text,
                                ))
                            telemetry.source_reads += 1
                            telemetry.source_bytes += returned
                            worker["read_count"] += 1
                            worker["read_bytes"] += returned
                            worker["first_start_ns"] = worker["first_start_ns"] or started
                            worker["last_end_ns"] = ended
                            remaining -= returned
                            offset += returned
                            destination += returned
                            retry += 1
                            if returned == 0 or retry > 1024:
                                raise ExtentTransportError("short read retry limit exceeded")
                        if first_start is not None:
                            worker["wall_ms"] += max(0, time.monotonic_ns() - first_start) / 1e6
                        with meta:
                            runtime.completed_reads += 1
                            if runtime.completed_reads == len(runtime.plan.reads):
                                assert runtime.slot is not None
                                runtime.slot.state = ExtentState.READY
                                ready_wait_start = time.monotonic_ns()
                                while len(ready) >= self.ready_queue_capacity and not abort.is_set():
                                    meta.wait(0.001)
                                ready_wait = max(0, time.monotonic_ns() - ready_wait_start)
                                if ready_wait:
                                    telemetry.ready_queue_wait_ns += ready_wait
                                    telemetry.ready_queue_wait_count += 1
                                if abort.is_set():
                                    return
                                if source_only:
                                    # Source completion is the only ownership
                                    # boundary in this arm.  Do not enqueue a
                                    # READY extent or wait for GPU state.
                                    runtime.completed = True
                                    runtime.slot.state = ExtentState.FREE
                                    runtime.slot.extent_index = None
                                else:
                                    ready.append(runtime.plan.extent_index)
                                meta.notify_all()
                    finally:
                        source_slots.release()
            except BaseException as exc:
                telemetry.errors.append(f"source[{producer_id}]={type(exc).__name__}:{exc}")
                fail(exc)

        def dispatch() -> None:
            telemetry.ready_start_ns = time.monotonic_ns()
            while True:
                with meta:
                    while (
                        not ready
                        and not inflight
                        and not abort.is_set()
                        and any(not runtime.completed for runtime in runtimes)
                    ):
                        meta.wait(0.001)
                    while ready and len(inflight) < self.h2d_inflight_depth and not abort.is_set():
                        extent_index = ready.pop(0)
                        runtime = runtimes[extent_index]
                        slot = runtime.slot
                        if slot is None or slot.state != ExtentState.READY:
                            fail(ExtentTransportError("extent ready state was lost"))
                            return
                        slot.state = ExtentState.IN_FLIGHT
                        started = time.monotonic_ns()
                        try:
                            source_buffer = self._buffer_slice(
                                slot.buffer, 0, runtime.plan.length
                            )
                            event = backend.submit_h2d(
                                source_buffer, runtime.plan.destination_offset
                            )
                            submitted_ns = time.monotonic_ns()
                            observer_token: int | None = None
                            if h2d_observer is not None:
                                submit = getattr(h2d_observer, "record_h2d_submit", None)
                                if not callable(submit):
                                    raise ExtentTransportError("invalid_h2d_observer")
                                observer_token = int(cast(Callable[..., Any], submit)(
                                    runtime.plan.length, timestamp_ns=submitted_ns
                                ))
                        except BaseException as exc:
                            fail(exc)
                            return
                        runtime.submitted = True
                        token = telemetry.next_h2d_token
                        telemetry.next_h2d_token += 1
                        telemetry.h2d_events.append({
                            "token": token,
                            "bytes": runtime.plan.length,
                            "submit_ns": submitted_ns,
                            "complete_ns": None,
                            "observer_token": observer_token,
                        })
                        inflight[extent_index] = (
                            event, started, runtime.plan.length, observer_token, token
                        )
                        telemetry.h2d_copy_count += 1
                        telemetry.h2d_bytes += runtime.plan.length
                        telemetry.h2d_inflight_depth = len(inflight)
                        telemetry.max_h2d_inflight_depth = max(telemetry.max_h2d_inflight_depth, len(inflight))
                        telemetry.h2d_start_ns = telemetry.h2d_start_ns or started
                        meta.notify_all()
                    if abort.is_set():
                        return
                    if not ready and not inflight and all(runtime.completed for runtime in runtimes):
                        return
                    capacity_blocked = bool(ready and len(inflight) >= self.h2d_inflight_depth)
                    active = list(inflight.items())
                for extent_index, (event, _started, length, observer_token, token) in active:
                    try:
                        status = backend.poll_event(event)
                    except BaseException as exc:
                        fail(exc)
                        return
                    if str(status).lower() not in {"complete", "completed", "eventstatus.complete"} and getattr(status, "value", status) != "complete":
                        continue
                    with meta:
                        if extent_index not in inflight:
                            continue
                        completed_ns = time.monotonic_ns()
                        if h2d_observer is not None and observer_token is not None:
                            complete = getattr(h2d_observer, "record_h2d_complete", None)
                            if not callable(complete):
                                fail(ExtentTransportError("invalid_h2d_observer"))
                                return
                            try:
                                complete(observer_token, timestamp_ns=completed_ns)
                            except BaseException as exc:
                                fail(exc)
                                return
                        del inflight[extent_index]
                        runtime = runtimes[extent_index]
                        runtime.completed = True
                        if runtime.slot is not None:
                            runtime.slot.state = ExtentState.FREE
                            runtime.slot.extent_index = None
                        telemetry.h2d_inflight_depth = len(inflight)
                        telemetry.h2d_completion_count += 1
                        telemetry.h2d_completed_bytes += length
                        for h2d_event in telemetry.h2d_events:
                            if h2d_event["token"] == token:
                                h2d_event["complete_ns"] = completed_ns
                                break
                        telemetry.h2d_end_ns = completed_ns
                        meta.notify_all()
                if capacity_blocked:
                    telemetry.h2d_capacity_wait_ns += 100_000
                    telemetry.h2d_capacity_wait_count += 1
                time.sleep(0.0001)

        workers = [threading.Thread(target=source_worker, args=(i,), name=f"preplanned-source-{i}", daemon=True) for i in range(self.source_qd)]
        dispatcher = None if source_only else threading.Thread(
            target=dispatch, name="preplanned-h2d-dispatcher", daemon=True
        )
        if dispatcher is not None:
            dispatcher.start()
        for worker in workers:
            worker.start()
        deadline = time.monotonic() + self.cleanup_timeout

        def join_bounded(threads: Sequence[threading.Thread], label: str) -> None:
            for thread in threads:
                remaining = max(0.0, deadline - time.monotonic())
                thread.join(remaining)
                if thread.is_alive():
                    abort.set()
                    with meta:
                        meta.notify_all()
                    raise ExtentTransportError(f"{label}_join_timeout")

        try:
            join_bounded(workers, "source_worker")
            telemetry.source_end_ns = time.monotonic_ns()
            for worker in telemetry.source_worker_timing.values():
                worker["worker_terminated_ns"] = telemetry.source_end_ns
                worker["worker_release_ns"] = (
                    worker.get("last_end_ns") or telemetry.source_end_ns
                )
                worker["release_reason"] = (
                    "source_completion" if source_only else "source_worker_join"
                )
            with meta:
                meta.notify_all()
            if dispatcher is not None:
                join_bounded((dispatcher,), "h2d_dispatcher")
        except BaseException:
            abort.set()
            with meta:
                meta.notify_all()
            # Give cooperative workers one final bounded chance to observe
            # abort.  A blocked external reader cannot be made safe to kill;
            # in that case the daemon thread is intentionally left behind and
            # the operation fails closed rather than hanging the request.
            cleanup_deadline = time.monotonic() + self.cleanup_timeout
            cleanup_threads = (*workers,) if dispatcher is None else (*workers, dispatcher)
            for thread in cleanup_threads:
                thread.join(max(0.0, cleanup_deadline - time.monotonic()))
            raise
        if failure:
            raise ExtentTransportError(str(failure[0])) from failure[0]
        if any(not runtime.completed for runtime in runtimes):
            raise ExtentTransportError("not all planned extents completed")
        telemetry.ready_end_ns = time.monotonic_ns()
        report = telemetry.snapshot()
        report.update(self.metadata)
        provenance = report.get("physical_syscall_provenance") or report.get("physical_read_provenance")
        if isinstance(provenance, str) and provenance:
            report["physical_syscall_provenance"] = provenance
            report["physical_read_provenance"] = provenance
            for event in report["physical_reads"]:
                event["physical_provenance"] = provenance
        report.update({
            "extent_count": len(extents),
            "extent_slot_count": len(slots),
            "source_base": source_base,
            "destination_base": destination_base,
            "source_capacity": self.source_capacity,
            "source_block_bytes": self.source_block_bytes,
            "configured_h2d_copy_bytes": self.h2d_copy_bytes,
            "h2d_inflight_depth": self.h2d_inflight_depth,
            "post_hoc_aggregation": False,
            "preplanned_extents": [
                {
                    "extent_index": extent.extent_index,
                    "destination_offset": extent.destination_offset,
                    "length": extent.length,
                    "read_count": len(extent.reads),
                    "reads": [
                        {
                            "source_offset": read.source_offset,
                            "destination_offset": read.destination_offset,
                            "length": read.length,
                        }
                        for read in extent.reads
                    ],
                }
                for extent in extents
            ],
            "coverage_ok": True,
        })
        output = None
        if materialize_output and not source_only:
            destination = getattr(backend, "destination", None)
            if destination is not None:
                output = bytes(destination[:total_bytes])
        report["execution_mode"] = "source_only" if source_only else "integrated"
        report["h2d_dispatcher_started"] = dispatcher is not None
        report["h2d_dispatcher_participation"] = dispatcher is not None
        return {"output": output, "telemetry": report}

    def execute_source_only(
        self,
        extents: Sequence[PlannedExtent],
        reader: Any,
        *,
        total_bytes: int,
        source_offset: int | None = None,
        destination_offset: int | None = None,
    ) -> dict[str, Any]:
        """Run the explicit source-only control arm on the shared worker path."""
        return self.execute(
            extents,
            reader,
            None,
            total_bytes=total_bytes,
            materialize_output=False,
            source_offset=source_offset,
            destination_offset=destination_offset,
            source_only=True,
        )


__all__ = [
    "ExtentState",
    "ExtentTransportError",
    "PlannedRead",
    "PlannedExtent",
    "PreplannedExtentTransport",
    "plan_preplanned_extents",
    "validate_preplanned_extents",
]
