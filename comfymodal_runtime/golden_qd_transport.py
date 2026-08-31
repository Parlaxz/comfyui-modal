"""Opt-in, fail-closed Golden QD transport.

The producer side owns only a generation-tagged lease and its fill/mark APIs.
The dispatcher is the sole owner of submission, completion events, and slot
return.  CUDA is optional: importing this module does not import torch.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence, cast


TRANSPORT_ENV = "COMFYMODAL_GOLDEN_QD_TRANSPORT"
LEGACY_ARM = "legacy"
DISPATCHER_ARM = "dispatcher"
DEFAULT_QUEUE_DEPTH = 4
DEFAULT_BLOCK_BYTES = 32 * 1024 * 1024
DEFAULT_STAGING_SLOTS = 8


class TransportError(RuntimeError):
    """Base class for fail-closed transport errors."""


class LeaseError(TransportError):
    pass


class PoolPoisonedError(TransportError):
    pass


class CancellationError(TransportError):
    pass


class ReconciliationError(TransportError):
    pass


class EventStatus(str, Enum):
    PENDING = "pending"
    COMPLETE = "complete"
    UNCERTAIN = "uncertain"
    FAILED = "failed"


class SlotState(str, Enum):
    FREE = "free"
    FILLING = "filling"
    READY = "ready"
    IN_FLIGHT = "in_flight"
    POISONED = "poisoned"


def normalize_transport_arm(value: str | None = None) -> str:
    selected = os.environ.get(TRANSPORT_ENV) if value is None else value
    selected = LEGACY_ARM if selected is None or selected == "" else str(selected).strip().lower()
    if selected not in (LEGACY_ARM, DISPATCHER_ARM):
        raise ValueError(f"unknown Golden QD transport arm {selected!r}; expected legacy or dispatcher")
    return selected


@dataclass(frozen=True)
class TransportConfig:
    queue_depth: int = DEFAULT_QUEUE_DEPTH
    block_bytes: int = DEFAULT_BLOCK_BYTES
    staging_slots: int = DEFAULT_STAGING_SLOTS
    ready_queue_capacity: int | None = None
    read_retries: int = 2
    producer_workers: int = 4
    cancellation_poll_limit: int = 1024
    cleanup_timeout: float = 1.0
    capacity_class: str = "qd4-32m"

    def __post_init__(self) -> None:
        ready_capacity = self.staging_slots if self.ready_queue_capacity is None else self.ready_queue_capacity
        object.__setattr__(self, "ready_queue_capacity", ready_capacity)
        values = {
            "queue_depth": self.queue_depth,
            "block_bytes": self.block_bytes,
            "staging_slots": self.staging_slots,
            "ready_queue_capacity": ready_capacity,
            "read_retries": self.read_retries,
            "producer_workers": self.producer_workers,
            "cancellation_poll_limit": self.cancellation_poll_limit,
        }
        for name, value in values.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.cleanup_timeout, (int, float)) or self.cleanup_timeout <= 0:
            raise ValueError("cleanup_timeout must be positive")
        if self.queue_depth > self.staging_slots:
            raise ValueError("queue_depth cannot exceed staging_slots")
        if not isinstance(self.capacity_class, str) or not self.capacity_class:
            raise ValueError("capacity_class must be a non-empty string")


@dataclass(frozen=True)
class SourceRange:
    source_offset: int
    length: int
    destination_offset: int | None = None
    record_id: str | int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_offset, int) or isinstance(self.source_offset, bool) or self.source_offset < 0:
            raise ValueError("source_offset must be non-negative")
        if not isinstance(self.length, int) or isinstance(self.length, bool) or self.length < 1:
            raise ValueError("length must be positive")
        if self.destination_offset is not None and (
            not isinstance(self.destination_offset, int)
            or isinstance(self.destination_offset, bool)
            or self.destination_offset < 0
        ):
            raise ValueError("destination_offset must be non-negative")
        if self.record_id is not None and not isinstance(self.record_id, (str, int)):
            raise ValueError("record_id must be a string, integer, or None")

    @property
    def target_offset(self) -> int:
        return self.source_offset if self.destination_offset is None else self.destination_offset


@dataclass(frozen=True)
class ReadyRecord:
    source_offset: int
    destination_offset: int
    nbytes: int
    record_id: str | int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_offset, int) or isinstance(self.source_offset, bool) or self.source_offset < 0:
            raise ValueError("source_offset must be non-negative")
        if not isinstance(self.destination_offset, int) or isinstance(self.destination_offset, bool) or self.destination_offset < 0:
            raise ValueError("destination_offset must be non-negative")
        if not isinstance(self.nbytes, int) or isinstance(self.nbytes, bool) or self.nbytes < 1:
            raise ValueError("nbytes must be positive")
        if self.record_id is not None and not isinstance(self.record_id, (str, int)):
            raise ValueError("record_id must be a string, integer, or None")


@dataclass(frozen=True)
class OutputViewSpec:
    name: str
    offset: int
    length: int
    dtype: str | None = None


class TransportBackend(Protocol):
    def submit_h2d(self, source: Any, destination_offset: int) -> Any:
        ...

    def poll_event(self, event: Any) -> EventStatus | str:
        ...

    def cancel_event(self, event: Any) -> None:
        ...


def _validate_ready_record(record: ReadyRecord) -> None:
    if not isinstance(record, ReadyRecord):
        raise TypeError("publish requires ReadyRecord")
    if not isinstance(record.source_offset, int) or isinstance(record.source_offset, bool) or record.source_offset < 0:
        raise ReconciliationError("invalid record source offset")
    if not isinstance(record.destination_offset, int) or isinstance(record.destination_offset, bool) or record.destination_offset < 0:
        raise ReconciliationError("invalid record destination offset")
    if not isinstance(record.nbytes, int) or isinstance(record.nbytes, bool) or record.nbytes < 1:
        raise ReconciliationError("record nbytes must be positive")
    if record.record_id is not None and not isinstance(record.record_id, (str, int)):
        raise ReconciliationError("invalid record id")


class _Slot:
    def __init__(self, index: int, block_bytes: int, capacity_class: str, buffer: Any = None) -> None:
        self.index = index
        self.buffer = bytearray(block_bytes) if buffer is None else buffer
        self.capacity_class = capacity_class
        self.generation = 0
        self.state = SlotState.FREE
        self.lease: StageLease | None = None


class StageLease:
    """A generation-tagged producer lease with no public raw-buffer escape."""

    def __init__(self, pool: "StagingPool", slot: _Slot, generation: int, declared_range: SourceRange | None) -> None:
        self._pool = pool
        self.slot_index = slot.index
        self.generation = generation
        self.capacity_class = slot.capacity_class
        self._declared_range = declared_range
        self._filled = 0
        self._returned = False
        self._producer_retired = False
        self._producer_identity: int | None = None

    @property
    def state(self) -> SlotState:
        with self._pool._meta:
            return self._pool._validate_locked(self).state

    @property
    def buffer(self) -> memoryview:
        # Keep an explicit failure for callers holding old API references.  Do
        # not return a memoryview: it would outlive the generation check.
        raise LeaseError("raw staging buffers are private; use fill and mark_filled")

    @property
    def filled_bytes(self) -> int:
        return self._filled

    def fill(self, payload: bytes | bytearray | memoryview) -> None:
        data = memoryview(payload)
        if len(data) > self._pool.block_bytes:
            raise LeaseError("payload exceeds staging block")
        with self._pool._meta:
            slot = self._pool._validate_locked(self)
            if slot.state != SlotState.FILLING or self._producer_retired:
                raise LeaseError("lease is no longer writable")
            _write_buffer(slot.buffer, data)
            self._filled = len(data)

    def mark_filled(self, nbytes: int) -> None:
        if not isinstance(nbytes, int) or isinstance(nbytes, bool) or not 0 <= nbytes <= self._pool.block_bytes:
            raise LeaseError("invalid filled byte count")
        with self._pool._meta:
            slot = self._pool._validate_locked(self)
            if slot.state != SlotState.FILLING or self._producer_retired:
                raise LeaseError("lease is no longer writable")
            self._filled = nbytes

    def retire(self) -> None:
        """Relinquish producer ownership before the dispatcher can return it."""
        with self._pool._meta:
            slot = self._pool._validate_locked(self)
            if slot.state != SlotState.FILLING:
                raise LeaseError("only a filling lease can be retired")
            self._producer_retired = True
            self._producer_identity = threading.get_ident()


def _write_buffer(buffer: Any, data: memoryview) -> None:
    try:
        buffer[: len(data)] = data
        return
    except (TypeError, ValueError, RuntimeError):
        pass
    # This path supports CPU torch uint8 tensors without importing torch at
    # module import time.  It is intentionally not a fallback to a new slot.
    try:
        import torch
        if isinstance(buffer, torch.Tensor) and buffer.dtype == getattr(torch, "uint8"):
            source = getattr(torch, "frombuffer")(bytearray(data), dtype=getattr(torch, "uint8"))
            buffer[: len(data)].copy_(source)
            return
    except (ImportError, TypeError, ValueError, RuntimeError):
        pass
    raise LeaseError("staging buffer is not writable as uint8 storage")


class StagingPool:
    """Bounded reusable staging storage; metadata lock never guards I/O."""

    def __init__(
        self,
        slots: int = DEFAULT_STAGING_SLOTS,
        block_bytes: int = DEFAULT_BLOCK_BYTES,
        capacity_class: str = "qd4-32m",
        *,
        buffers: Sequence[Any] | None = None,
        buffer_factory: Callable[[int], Any] | None = None,
    ) -> None:
        if (
            not isinstance(slots, int) or isinstance(slots, bool) or slots < 1
            or not isinstance(block_bytes, int) or isinstance(block_bytes, bool) or block_bytes < 1
            or not isinstance(capacity_class, str) or not capacity_class
        ):
            raise ValueError("invalid staging pool dimensions")
        if buffers is not None and len(buffers) != slots:
            raise ValueError("buffers must contain exactly one buffer per slot")
        if buffers is not None and buffer_factory is not None:
            raise ValueError("provide buffers or buffer_factory, not both")
        self.block_bytes = block_bytes
        self.capacity_class = capacity_class
        self._meta = threading.RLock()
        self._available = threading.Condition(self._meta)
        self._slots = [
            _Slot(i, block_bytes, capacity_class, buffers[i] if buffers is not None else (buffer_factory(block_bytes) if buffer_factory else None))
            for i in range(slots)
        ]
        self._poisoned = False
        self._poison_reason: str | None = None
        self._cancelled = False

    @property
    def capacity(self) -> int:
        return len(self._slots)

    @property
    def poisoned(self) -> bool:
        with self._meta:
            return self._poisoned

    def _validate_locked(self, lease: StageLease) -> _Slot:
        if not isinstance(lease, StageLease) or lease._pool is not self:
            raise LeaseError("lease belongs to a different staging pool")
        if lease.slot_index < 0 or lease.slot_index >= len(self._slots):
            raise LeaseError("invalid lease slot")
        slot = self._slots[lease.slot_index]
        if slot.lease is not lease or slot.generation != lease.generation:
            raise LeaseError("stale lease generation")
        if lease.capacity_class != self.capacity_class or slot.capacity_class != self.capacity_class:
            raise LeaseError("staging capacity class mismatch")
        if lease._returned:
            raise LeaseError("lease was already returned")
        return slot

    def acquire(
        self,
        capacity_class: str | None = None,
        timeout: float | None = None,
        *,
        declared_range: SourceRange | None = None,
    ) -> StageLease:
        requested = self.capacity_class if capacity_class is None else capacity_class
        if requested != self.capacity_class:
            raise LeaseError("staging capacity class mismatch")
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._available:
            while True:
                if self._poisoned:
                    raise PoolPoisonedError(self._poison_reason or "staging pool is poisoned")
                if self._cancelled:
                    raise CancellationError("staging pool acquisition was cancelled")
                for slot in self._slots:
                    if slot.state == SlotState.FREE:
                        slot.generation += 1
                        slot.state = SlotState.FILLING
                        lease = StageLease(self, slot, slot.generation, declared_range)
                        slot.lease = lease
                        return lease
                if timeout is not None:
                    remaining = (deadline or time.monotonic()) - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("staging pool acquire timed out")
                    self._available.wait(remaining)
                else:
                    self._available.wait()

    def _cancel_waiters(self) -> None:
        with self._available:
            self._cancelled = True
            self._available.notify_all()

    def return_lease(self, lease: StageLease) -> None:
        with self._available:
            slot = self._validate_locked(lease)
            if slot.state != SlotState.FILLING:
                raise LeaseError(f"cannot return slot in {slot.state.value} state before completion proof")
            # A direct producer return is itself the retirement handshake.
            lease._producer_retired = True
            lease._producer_identity = threading.get_ident()
            self._free_locked(slot, lease)

    release = return_lease

    def _free_locked(self, slot: _Slot, lease: StageLease) -> None:
        slot.state = SlotState.FREE
        slot.lease = None
        lease._returned = True
        self._available.notify_all()

    def _mark_ready(self, lease: StageLease, record: ReadyRecord, destination_size: int | None = None) -> None:
        _validate_ready_record(record)
        with self._meta:
            slot = self._validate_locked(lease)
            if slot.state != SlotState.FILLING or lease._producer_retired:
                raise LeaseError("only an unretired filling lease can be published")
            expected = lease._declared_range
            if expected is not None:
                if (record.source_offset, record.destination_offset, record.nbytes, record.record_id) != (
                    expected.source_offset, expected.target_offset, expected.length, expected.record_id
                ):
                    raise ReconciliationError("ready record does not match its declared source range")
            if record.nbytes != lease.filled_bytes or record.nbytes > self.block_bytes:
                raise ReconciliationError("record bytes do not equal filled bytes")
            if destination_size is not None and record.destination_offset + record.nbytes > destination_size:
                raise ReconciliationError("record exceeds destination bounds")
            lease._producer_retired = True
            lease._producer_identity = threading.get_ident()
            slot.state = SlotState.READY

    def _mark_in_flight(self, lease: StageLease) -> None:
        with self._meta:
            slot = self._validate_locked(lease)
            if slot.state != SlotState.READY or not lease._producer_retired:
                raise LeaseError("only a retired ready lease can be submitted")
            slot.state = SlotState.IN_FLIGHT

    def _buffer_for_dispatch(self, lease: StageLease, nbytes: int) -> Any:
        with self._meta:
            slot = self._validate_locked(lease)
            if slot.state != SlotState.IN_FLIGHT or not lease._producer_retired:
                raise LeaseError("dispatcher may access only a retired in-flight lease")
            return slot.buffer[:nbytes]

    def _return_completed(self, lease: StageLease) -> None:
        with self._available:
            slot = self._validate_locked(lease)
            if slot.state != SlotState.IN_FLIGHT or not lease._producer_retired:
                raise LeaseError("completion proof arrived before producer retirement")
            self._free_locked(slot, lease)

    def _return_ready(self, lease: StageLease) -> None:
        with self._available:
            slot = self._validate_locked(lease)
            if slot.state != SlotState.READY or not lease._producer_retired:
                raise LeaseError("only a retired unsubmitted ready lease can be drained")
            self._free_locked(slot, lease)

    def _poison(self, lease: StageLease | None, reason: str, *, all_active: bool = False) -> None:
        with self._available:
            self._poisoned = True
            self._poison_reason = reason
            for slot in self._slots:
                if all_active or (lease is not None and slot.lease is lease and slot.generation == lease.generation):
                    if slot.lease is not None:
                        slot.state = SlotState.POISONED
                        slot.lease._returned = True
                        slot.lease = None
            self._available.notify_all()

    def states(self) -> tuple[SlotState, ...]:
        with self._meta:
            return tuple(slot.state for slot in self._slots)


@dataclass
class _Telemetry:
    entry_ns: int = field(default_factory=time.monotonic_ns)
    source_start_ns: int | None = None
    source_end_ns: int | None = None
    final_drain_start_ns: int | None = None
    final_drain_end_ns: int | None = None
    source_bytes: int = 0
    source_read_count: int = 0
    h2d_submitted_bytes: int = 0
    h2d_completed_bytes: int = 0
    h2d_submitted_count: int = 0
    h2d_completed_count: int = 0
    parse_count: int = 0
    source_open_count: int = 0
    duplicate_read_count: int = 0
    producer_capacity_block_wall_ns: int = 0
    producer_capacity_block_count: int = 0
    ready_queue_block_wall_ns: int = 0
    ready_queue_block_count: int = 0
    dispatcher_reap_wall_ns: int = 0
    dispatcher_reap_count: int = 0
    h2d_latencies_ns: list[int] = field(default_factory=list)
    qd_samples: list[int] = field(default_factory=list)
    source_qd_target: int | None = None
    source_qd_depth: int = 0
    source_qd_depth_samples: list[int] = field(default_factory=list)
    source_qd_timeline: list[dict[str, int]] = field(default_factory=list)
    _source_qd_start_ns: int | None = field(default=None, repr=False)
    _source_qd_last_transition_ns: int | None = field(default=None, repr=False)
    _source_qd_target_time_ns: int = field(default=0, repr=False)
    ready_depth: int = 0
    min_free_slots: int | None = None
    owner: Any = None
    adoption: Any = None
    owner_count: Any = None
    adoption_result: Any = None
    execution_arm: str = DISPATCHER_ARM
    fallback_count: int = 0
    fallback_reason: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def source_read(self, nbytes: int, *, duplicate: bool = False) -> None:
        with self._lock:
            self.source_read_count += 1
            self.source_bytes += nbytes
            if duplicate:
                self.duplicate_read_count += 1

    def configure_source_qd(self, target: int) -> None:
        with self._lock:
            self.source_qd_target = target

    def source_read_begin(self) -> None:
        self._source_qd_transition(1)

    def source_read_end(self) -> None:
        self._source_qd_transition(-1)

    def _source_qd_transition(self, delta: int) -> None:
        with self._lock:
            now = time.monotonic_ns()
            previous = self._source_qd_last_transition_ns
            if previous is None:
                self._source_qd_start_ns = now
            else:
                # Keep accounting monotonic even if a clock reading is adjusted
                # between transitions.  The lock makes the depth/time update a
                # single transition from the telemetry consumer's perspective.
                now = max(now, previous)
                elapsed = now - previous
                if self.source_qd_target is not None and self.source_qd_depth == self.source_qd_target:
                    self._source_qd_target_time_ns += elapsed
            next_depth = self.source_qd_depth + delta
            if next_depth < 0:
                raise RuntimeError("source-read QD became negative")
            self.source_qd_depth = next_depth
            self._source_qd_last_transition_ns = now
            self.source_qd_depth_samples.append(next_depth)
            self.source_qd_timeline.append({"timestamp_ns": now, "depth": next_depth})

    def snapshot(self, queue_depth: int, free_slots: int, total_end_ns: int | None = None) -> dict[str, Any]:
        with self._lock:
            end = time.monotonic_ns() if total_end_ns is None else total_end_ns
            source_wall = 0 if self.source_start_ns is None else (self.source_end_ns or end) - self.source_start_ns
            drain_wall = 0 if self.final_drain_start_ns is None else (self.final_drain_end_ns or end) - self.final_drain_start_ns
            qd = list(self.qd_samples)
            source_qd = list(self.source_qd_depth_samples)
            source_qd_timeline = list(self.source_qd_timeline)
            source_qd_target = self.source_qd_target if self.source_qd_target is not None else queue_depth
            last_source_transition = self._source_qd_last_transition_ns
            # Once all reads have ended, H2D drain time is outside the source
            # QD observation window.  If a read is still outstanding (for a
            # bounded-failure snapshot), account through the snapshot boundary.
            source_qd_end = (
                max(end, last_source_transition or end)
                if self.source_qd_depth
                else (last_source_transition or end)
            )
            source_qd_wall = (
                0
                if self._source_qd_start_ns is None
                else source_qd_end - self._source_qd_start_ns
            )
            target_time = self._source_qd_target_time_ns
            if (
                self._source_qd_last_transition_ns is not None
                and self.source_qd_depth == source_qd_target
            ):
                target_time += source_qd_end - self._source_qd_last_transition_ns
            target_fraction = target_time / source_qd_wall if source_qd_wall else 0.0
            latency = (sum(self.h2d_latencies_ns) / len(self.h2d_latencies_ns)) if self.h2d_latencies_ns else 0.0
            return {
                "timing_scope": {
                    "total_entry_to_return_wall_ms": "TOTAL",
                    "source_aggregate_wall_ms": "TOTAL nested source workers; may overlap",
                    "source_wall_ms": "PARTIAL aggregate source interval",
                    "final_drain_wall_ms": "TOTAL final drain interval",
                    "h2d_event_completion_latency_ms": "PARTIAL submit-to-event completion",
                    "target_qd_occupancy_fraction": "TOTAL weighted source-read interval at target source QD",
                    "h2d_inflight_depth_samples": "PARTIAL dispatcher in-flight H2D depth samples",
                },
                "total_entry_to_return_wall_ms": (end - self.entry_ns) / 1e6,
                "source_aggregate_wall_ms": source_wall / 1e6,
                "source_wall_ms": source_wall / 1e6,
                "source_throughput_bytes_s": self.source_bytes / (source_wall / 1e9) if source_wall else 0.0,
                "source_bytes": self.source_bytes,
                "source_read_count": self.source_read_count,
                "h2d_submitted_bytes": self.h2d_submitted_bytes,
                "h2d_completed_bytes": self.h2d_completed_bytes,
                "h2d_submitted_count": self.h2d_submitted_count,
                "h2d_completed_count": self.h2d_completed_count,
                # These are source-reader metrics.  Keep the old names as
                # compatibility aliases, but do not confuse them with H2D
                # dispatcher depth below.
                "source_qd_target": source_qd_target,
                "source_qd_depth": self.source_qd_depth,
                "source_qd_depth_samples": source_qd,
                "source_qd_timeline": source_qd_timeline,
                "fraction_time_at_target_source_qd": target_fraction,
                "target_qd_occupancy_fraction": target_fraction,
                # Historical compatibility: this field was the dispatcher
                # sample stream.  The explicit names above/below remove that
                # ambiguity for new consumers.
                "target_qd_depth_samples": qd,
                "h2d_inflight_depth_samples": qd,
                "ready_queue_depth": self.ready_depth,
                "minimum_free_slots": self.min_free_slots if self.min_free_slots is not None else free_slots,
                "min_free_slots": self.min_free_slots if self.min_free_slots is not None else free_slots,
                "producer_capacity_block_wall_ms": self.producer_capacity_block_wall_ns / 1e6,
                "producer_capacity_block_count": self.producer_capacity_block_count,
                "ready_queue_block_wall_ms": self.ready_queue_block_wall_ns / 1e6,
                "ready_queue_block_count": self.ready_queue_block_count,
                "dispatcher_reap_wall_ms": self.dispatcher_reap_wall_ns / 1e6,
                "dispatcher_reap_count": self.dispatcher_reap_count,
                "h2d_event_completion_latency_ms": latency,
                "final_drain_wall_ms": drain_wall / 1e6,
                "parse_count": self.parse_count,
                "owner": _json_safe(self.owner),
                "adoption": _json_safe(self.adoption),
                "owner_count": _json_safe(self.owner_count),
                "adoption_result": _json_safe(self.adoption_result),
                "execution_arm": self.execution_arm,
                "fallback_count": self.fallback_count,
                "fallback_reason": self.fallback_reason,
                "source_open_count": self.source_open_count,
                "duplicate_read_count": self.duplicate_read_count,
            }


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


class TransportFailure(TransportError):
    def __init__(self, primary_error: BaseException, *, secondary_errors: Sequence[BaseException] = (), telemetry: Mapping[str, Any] | None = None, cancelled: bool = False) -> None:
        self.primary_error = primary_error
        self.secondary_errors = tuple(secondary_errors)
        self.telemetry = dict(telemetry or {})
        self.cancelled = cancelled
        super().__init__(str(primary_error))

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_error": f"{type(self.primary_error).__name__}: {self.primary_error}",
            "secondary_errors": [f"{type(e).__name__}: {e}" for e in self.secondary_errors],
            "cancelled": self.cancelled,
            "telemetry": _json_safe(self.telemetry),
        }


@dataclass(frozen=True)
class TransportResult:
    records: tuple[ReadyRecord, ...]
    submitted_bytes: int
    completed_bytes: int
    output: bytes | None
    telemetry: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [_json_safe(record.__dict__) for record in self.records],
            "submitted_bytes": self.submitted_bytes,
            "completed_bytes": self.completed_bytes,
            "output_bytes": None if self.output is None else len(self.output),
            "telemetry": _json_safe(self.telemetry),
        }


class TransportDispatcher:
    """One owner for H2D submit, event lifecycle, reaping, and slot return."""

    def __init__(self, pool: StagingPool, backend: TransportBackend, config: TransportConfig, telemetry: _Telemetry, destination_size: int | None = None) -> None:
        self.pool, self.backend, self.config, self.telemetry = pool, backend, config, telemetry
        self.destination_size = destination_size
        self._queue: list[tuple[StageLease, ReadyRecord]] = []
        self._queue_condition = threading.Condition()
        # A ready item is removed from _queue before the backend call.  Keep
        # that handoff visible until the event is registered so bounded drain
        # cannot mistake the gap for quiescence and lose the lease/event.
        self._handoff: dict[int, tuple[StageLease, ReadyRecord]] = {}
        self._in_flight: dict[int, tuple[StageLease, ReadyRecord, Any, int]] = {}
        self._completed_records: list[ReadyRecord] = []
        self._dispatcher_error: BaseException | None = None
        self._cleanup_errors: list[BaseException] = []
        self._stop = False
        self._cancelled = False
        self._thread: threading.Thread | None = None

    @property
    def dispatcher_error(self) -> BaseException | None:
        return self._dispatcher_error

    @property
    def cleanup_errors(self) -> tuple[BaseException, ...]:
        with self._queue_condition:
            return tuple(self._cleanup_errors)

    @property
    def completed_records(self) -> tuple[ReadyRecord, ...]:
        with self._queue_condition:
            return tuple(self._completed_records)

    def start(self) -> None:
        if self._thread is not None:
            raise TransportError("dispatcher already started")
        self._thread = threading.Thread(target=self._run, name="golden-qd-dispatcher", daemon=True)
        self._thread.start()

    def publish(self, lease: StageLease, record: ReadyRecord) -> None:
        _validate_ready_record(record)
        started = time.monotonic_ns()
        blocked = False
        capacity = self.config.ready_queue_capacity
        assert capacity is not None
        with self._queue_condition:
            while len(self._queue) >= capacity and not self._cancelled and not self._stop:
                blocked = True
                self._queue_condition.wait()
            if blocked:
                self.telemetry.ready_queue_block_count += 1
                self.telemetry.ready_queue_block_wall_ns += time.monotonic_ns() - started
            if self._cancelled:
                raise CancellationError("transport was cancelled before publish")
            if self._stop:
                raise CancellationError("transport was quiesced before publish")
            # This call does not call back into the dispatcher condition.
            self.pool._mark_ready(lease, record, self.destination_size)
            self._queue.append((lease, record))
            self.telemetry.ready_depth = len(self._queue)
            self._queue_condition.notify_all()

    def quiesce(self) -> None:
        with self._queue_condition:
            self._stop = True
            self._queue_condition.notify_all()

    def cancel(self) -> None:
        with self._queue_condition:
            self._cancelled = True
            self._stop = True
            self._queue_condition.notify_all()

    def _note_cleanup(self, error: BaseException) -> None:
        with self._queue_condition:
            self._cleanup_errors.append(error)

    def _set_dispatcher_error(self, error: BaseException) -> None:
        with self._queue_condition:
            if self._dispatcher_error is None:
                self._dispatcher_error = error
            self._cancelled = True
            self._stop = True
            self._queue_condition.notify_all()

    def _poll(self) -> None:
        started = time.monotonic_ns()
        with self._queue_condition:
            active = list(self._in_flight.items())
            self.telemetry.qd_samples.append(len(active))
        for key, (lease, record, event, submit_ns) in active:
            try:
                raw_status = self.backend.poll_event(event)
                status = EventStatus(raw_status)
            except BaseException as exc:
                self.pool._poison(lease, "H2D poll was uncertain")
                raise TransportError("H2D poll failed; staging pool poisoned") from exc
            if status == EventStatus.PENDING:
                continue
            with self._queue_condition:
                self._in_flight.pop(key, None)
                self._queue_condition.notify_all()
            if status == EventStatus.COMPLETE:
                # The completion event is the proof that the submitted copy
                # finished.  Count it before pool bookkeeping so a cleanup
                # race cannot make the telemetry claim that it did not.
                self.telemetry.h2d_completed_bytes += record.nbytes
                self.telemetry.h2d_completed_count += 1
                self.pool._return_completed(lease)
                with self._queue_condition:
                    self._completed_records.append(record)
                self.telemetry.h2d_latencies_ns.append(time.monotonic_ns() - submit_ns)
            elif status == EventStatus.UNCERTAIN:
                self.pool._poison(lease, "uncertain H2D completion")
                raise TransportError("uncertain H2D completion; staging pool poisoned")
            else:
                self.pool._poison(lease, "H2D event failed")
                raise TransportError("H2D completion event failed; staging pool poisoned")
        self.telemetry.dispatcher_reap_count += 1
        self.telemetry.dispatcher_reap_wall_ns += time.monotonic_ns() - started

    def _return_queued(self) -> None:
        with self._queue_condition:
            queued = self._queue[:]
            self._queue.clear()
            self.telemetry.ready_depth = 0
            self._queue_condition.notify_all()
        for lease, _record in queued:
            try:
                self.pool._return_ready(lease)
            except BaseException as exc:
                self._note_cleanup(exc)

    def _cancel_in_flight(self) -> None:
        # Snapshot under the condition, then release it before any backend or
        # pool call.  In particular, never reacquire this condition while it
        # is held by _run.
        with self._queue_condition:
            active = list(self._in_flight.items())
        for key, (lease, record, event, _submit_ns) in active:
            cancel_ok = True
            try:
                self.backend.cancel_event(event)
            except BaseException as exc:
                cancel_ok = False
                self._note_cleanup(exc)
            status: EventStatus | None = None
            for _ in range(self.config.cancellation_poll_limit):
                try:
                    status = EventStatus(self.backend.poll_event(event))
                except BaseException as exc:
                    self._note_cleanup(exc)
                    status = None
                    break
                if status != EventStatus.PENDING:
                    break
            proven = cancel_ok and status == EventStatus.COMPLETE
            if proven:
                try:
                    self.telemetry.h2d_completed_bytes += record.nbytes
                    self.telemetry.h2d_completed_count += 1
                    self.pool._return_completed(lease)
                    with self._queue_condition:
                        self._completed_records.append(record)
                except BaseException as exc:
                    self._note_cleanup(exc)
            else:
                self.pool._poison(lease, "cancelled H2D completion was not proven")
                if status == EventStatus.PENDING:
                    self._note_cleanup(TransportError("cancelled H2D event remained pending"))
                elif status == EventStatus.UNCERTAIN:
                    self._note_cleanup(TransportError("cancelled H2D completion was uncertain"))
                elif status == EventStatus.FAILED:
                    self._note_cleanup(TransportError("cancelled H2D completion failed"))
            with self._queue_condition:
                self._in_flight.pop(key, None)
                self._queue_condition.notify_all()

    def _cleanup_cancelled(self) -> None:
        self._return_queued()
        with self._queue_condition:
            handoff = list(self._handoff.values())
            self._handoff.clear()
            self._queue_condition.notify_all()
        for lease, _record in handoff:
            self.pool._poison(lease, "cancelled dispatcher handoff was not completed")
        self._cancel_in_flight()

    def _run(self) -> None:
        try:
            while True:
                try:
                    self._poll()
                except BaseException as exc:
                    self._set_dispatcher_error(exc)
                    self._cleanup_cancelled()
                    return
                with self._queue_condition:
                    cancelled = self._cancelled
                    item = None
                    if not cancelled and self._queue and len(self._in_flight) < self.config.queue_depth:
                        item = self._queue.pop(0)
                        self._handoff[item[0].slot_index] = item
                        self.telemetry.ready_depth = len(self._queue)
                        self._queue_condition.notify_all()
                    done = self._stop and item is None and not self._queue and not self._in_flight
                if cancelled:
                    self._cleanup_cancelled()
                    return
                if done:
                    return
                if item is None:
                    with self._queue_condition:
                        self._queue_condition.wait(0.001)
                    continue
                lease, record = item
                event = None
                try:
                    self.pool._mark_in_flight(lease)
                    source = self.pool._buffer_for_dispatch(lease, record.nbytes)
                    event = self.backend.submit_h2d(source, record.destination_offset)
                    if event is None:
                        raise TransportError("backend returned no completion event")
                    # The backend accepted the copy.  Count it before the
                    # handoff bookkeeping so a bounded-drain race cannot
                    # under-report a real submission.
                    self.telemetry.h2d_submitted_bytes += record.nbytes
                    self.telemetry.h2d_submitted_count += 1
                except BaseException as exc:
                    self.pool._poison(lease, "H2D submission did not produce a completion event")
                    self._set_dispatcher_error(exc)
                    self._cleanup_cancelled()
                    return
                with self._queue_condition:
                    handoff = self._handoff.get(lease.slot_index)
                    if handoff is not item:
                        registration_error = TransportError(
                            "dispatcher handoff was cleaned up before event registration"
                        )
                    else:
                        self._handoff.pop(lease.slot_index, None)
                        self._in_flight[lease.slot_index] = (
                            lease, record, event, time.monotonic_ns()
                        )
                        registration_error = None
                    self._queue_condition.notify_all()
                if registration_error is not None:
                    self.pool._poison(lease, str(registration_error))
                    self._set_dispatcher_error(registration_error)
                    self._cleanup_cancelled()
                    return
        finally:
            with self._queue_condition:
                self._queue_condition.notify_all()

    def drain(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is None:
            return
        bounded = self.config.cleanup_timeout if timeout is None else max(0.0, timeout)
        thread.join(bounded)
        if not thread.is_alive():
            return
        # A backend may never settle.  Detach every event and poison every
        # uncertain lease; do not wait indefinitely for a permanently pending
        # event or hold a dispatcher condition while doing pool cleanup.
        with self._queue_condition:
            queued = self._queue[:]
            active = list(self._in_flight.values())
            handoff = list(self._handoff.values())
            self._queue.clear()
            self._handoff.clear()
            self._in_flight.clear()
            self._stop = True
            self._cancelled = True
            self.telemetry.ready_depth = 0
            self._queue_condition.notify_all()
        for lease, _record in queued:
            try:
                self.pool._return_ready(lease)
            except BaseException as exc:
                self._note_cleanup(exc)
        for lease, _record in handoff:
            self.pool._poison(lease, "bounded drain could not complete dispatcher handoff")
        for lease, _record, _event, _submit_ns in active:
            self.pool._poison(lease, "bounded drain could not prove H2D completion")
        thread.join(min(0.05, bounded))
        if thread.is_alive():
            self._note_cleanup(TransportError("dispatcher thread did not stop within bounded drain"))


class GoldenQDTransport:
    """Explicit integration seam for a dispatcher-backed Golden stage."""

    def __init__(self, config: TransportConfig | None = None, backend: TransportBackend | None = None, *, arm: str | None = None, pool: StagingPool | None = None) -> None:
        self.config = config or TransportConfig()
        # This class is the dispatcher implementation.  The legacy default is
        # exposed only by create_transport()/LegacyTransport, so supplying a
        # backend here cannot accidentally report the legacy arm.
        self.arm = normalize_transport_arm(DISPATCHER_ARM if arm is None else arm)
        if self.arm == DISPATCHER_ARM and backend is None:
            raise ValueError("dispatcher arm requires an explicitly supplied backend")
        self.backend = backend
        if pool is None:
            buffers = None
            allocator = getattr(backend, "allocate_staging_buffers", None)
            if callable(allocator):
                buffers = cast(Sequence[Any], allocator(self.config.staging_slots, self.config.block_bytes))
            pool = StagingPool(self.config.staging_slots, self.config.block_bytes, self.config.capacity_class, buffers=buffers)
        self.pool = pool
        self.telemetry = _Telemetry(execution_arm=self.arm)
        self.dispatcher: TransportDispatcher | None = None
        self._active_producers = 0
        self._active_lock = threading.Lock()
        self._cancel_requested = False
        self._abort_requested = False

    def acquire(self, timeout: float | None = None, *, declared_range: SourceRange | None = None) -> StageLease:
        started = time.monotonic_ns()
        try:
            return self.pool.acquire(timeout=timeout, declared_range=declared_range)
        finally:
            waited = time.monotonic_ns() - started
            if waited > 100_000:
                self.telemetry.producer_capacity_block_count += 1
                self.telemetry.producer_capacity_block_wall_ns += waited
            free = sum(state == SlotState.FREE for state in self.pool.states())
            self.telemetry.min_free_slots = free if self.telemetry.min_free_slots is None else min(self.telemetry.min_free_slots, free)

    def start(self, *, destination_size: int | None = None) -> None:
        if self.backend is None:
            raise ValueError("dispatcher arm requires an explicitly supplied backend")
        if self.dispatcher is not None:
            raise TransportError("transport already started")
        self.dispatcher = TransportDispatcher(self.pool, self.backend, self.config, self.telemetry, destination_size)
        self.dispatcher.start()

    def publish(self, lease: StageLease, record: ReadyRecord) -> None:
        if self.dispatcher is None:
            raise TransportError("transport is not started")
        self.dispatcher.publish(lease, record)

    def quiesce(self) -> None:
        if self.dispatcher is not None:
            self.dispatcher.quiesce()

    def drain(self, timeout: float | None = None) -> None:
        if self.dispatcher is not None:
            self.telemetry.final_drain_start_ns = time.monotonic_ns()
            self.dispatcher.quiesce()
            self.dispatcher.drain(timeout)
            self.telemetry.final_drain_end_ns = time.monotonic_ns()

    def cancel(self, timeout: float | None = None) -> None:
        self._cancel_requested = True
        self._abort_requested = True
        self.pool._cancel_waiters()
        if self.dispatcher is not None:
            self.dispatcher.cancel()
            self.dispatcher.drain(timeout)

    def _request_abort(self) -> None:
        self._abort_requested = True
        self.pool._cancel_waiters()
        if self.dispatcher is not None:
            self.dispatcher.cancel()

    @staticmethod
    def _record_ranges(ranges: Iterable[SourceRange], destination_size: int | None = None) -> list[SourceRange]:
        result = list(ranges)
        if any(not isinstance(item, SourceRange) for item in result):
            raise ReconciliationError("all source ranges must be SourceRange instances")
        source_seen: set[tuple[int, int, int, str | int | None]] = set()
        ids: set[str | int] = set()
        for item in result:
            key = (item.source_offset, item.target_offset, item.length, item.record_id)
            if key in source_seen:
                raise ReconciliationError("duplicate source range")
            source_seen.add(key)
            if item.record_id is not None:
                if item.record_id in ids:
                    raise ReconciliationError("duplicate record id")
                ids.add(item.record_id)
        for left, right in zip(sorted(result, key=lambda r: r.source_offset), sorted(result, key=lambda r: r.source_offset)[1:]):
            if left.source_offset + left.length > right.source_offset:
                raise ReconciliationError("source ranges overlap; exact coverage is impossible")
        ordered_dest = sorted(result, key=lambda r: r.target_offset)
        for left, right in zip(ordered_dest, ordered_dest[1:]):
            if left.target_offset + left.length > right.target_offset:
                raise ReconciliationError("destination ranges overlap")
        if destination_size is not None:
            if not isinstance(destination_size, int) or isinstance(destination_size, bool) or destination_size < 0:
                raise ValueError("destination_size must be a non-negative integer")
            cursor = 0
            for item in ordered_dest:
                if item.target_offset != cursor or item.target_offset + item.length > destination_size:
                    raise ReconciliationError("destination ranges do not exactly cover destination_size")
                cursor += item.length
            if cursor != destination_size:
                raise ReconciliationError("destination ranges do not exactly cover destination_size")
        return result

    @staticmethod
    def _read_exact(reader: Callable[[int, int], bytes], item: SourceRange, retries: int, telemetry: _Telemetry) -> bytes:
        pieces: list[bytes] = []
        offset = item.source_offset
        remaining = item.length
        attempts = 0
        while remaining:
            if attempts > retries:
                raise ReconciliationError(f"short read for source range {item.source_offset}:{item.length}")
            chunk = reader(offset, remaining)
            duplicate = attempts > 0
            attempts += 1
            if not isinstance(chunk, (bytes, bytearray, memoryview)):
                raise ReconciliationError("source reader must return bytes-like data")
            data = bytes(chunk)
            if len(data) > remaining:
                raise ReconciliationError("source reader returned more bytes than requested")
            telemetry.source_read(len(data), duplicate=duplicate)
            if not data:
                continue
            pieces.append(data)
            offset += len(data)
            remaining -= len(data)
        return b"".join(pieces)

    def execute(
        self,
        ranges: Iterable[SourceRange],
        reader: Callable[[int, int], bytes],
        *,
        output_size: int | None = None,
        destination_size: int | None = None,
        materialize_output: bool = True,
        parse_count: int = 0,
        owner: Any = None,
        adoption: Any = None,
        owner_count: Any = None,
        adoption_result: Any = None,
    ) -> TransportResult:
        self.telemetry.entry_ns = time.monotonic_ns()
        if not isinstance(materialize_output, bool):
            raise ValueError("materialize_output must be a bool")
        if output_size is not None and destination_size is not None and output_size != destination_size:
            raise ValueError("output_size and destination_size disagree")
        exact_destination_size = destination_size if destination_size is not None else output_size
        source_ranges = self._record_ranges(ranges, exact_destination_size)
        if parse_count < 0:
            raise ValueError("parse_count must be non-negative")
        self.telemetry.parse_count = parse_count
        self.telemetry.owner, self.telemetry.adoption = owner, adoption
        self.telemetry.owner_count, self.telemetry.adoption_result = owner_count, adoption_result
        self.telemetry.configure_source_qd(min(self.config.queue_depth, self.config.producer_workers))
        self.telemetry.source_start_ns = time.monotonic_ns()
        read_fn: Callable[[int, int], bytes] = reader
        reader_open = getattr(reader, "open", None)
        if callable(reader_open):
            opened = reader_open()
            if opened is None:
                opened = reader
            read_fn = cast(Callable[[int, int], bytes], opened if callable(opened) else getattr(opened, "read"))
        self.telemetry.source_open_count += 1
        self.start(destination_size=exact_destination_size)
        errors: list[BaseException] = []
        producer_cleanup_errors: list[BaseException] = []
        errors_lock = threading.Lock()
        index = 0
        index_lock = threading.Lock()

        def note_worker_error(exc: BaseException) -> None:
            with errors_lock:
                errors.append(exc)
            self._request_abort()

        def worker() -> None:
            nonlocal index
            with self._active_lock:
                self._active_producers += 1
            try:
                while not self._abort_requested:
                    with index_lock:
                        if index >= len(source_ranges):
                            return
                        item = source_ranges[index]
                        index += 1
                    lease: StageLease | None = None
                    try:
                        lease = self.acquire(declared_range=item)
                        self.telemetry.source_read_begin()
                        try:
                            data = self._read_exact(read_fn, item, self.config.read_retries, self.telemetry)
                        finally:
                            self.telemetry.source_read_end()
                        lease.fill(data)
                        self.publish(lease, ReadyRecord(item.source_offset, item.target_offset, item.length, item.record_id))
                        lease = None  # dispatcher now owns the lease
                    finally:
                        if lease is not None:
                            try:
                                self.pool.return_lease(lease)
                            except BaseException as exc:
                                with errors_lock:
                                    producer_cleanup_errors.append(exc)
            except BaseException as exc:
                note_worker_error(exc)
            finally:
                with self._active_lock:
                    self._active_producers -= 1

        threads = [threading.Thread(target=worker, name=f"golden-qd-source-{i}", daemon=True) for i in range(self.config.producer_workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(self.config.cleanup_timeout)
        live_workers = [thread for thread in threads if thread.is_alive()]
        if live_workers:
            errors.append(TransportError("source worker did not stop within bounded cleanup"))
            self._request_abort()
            self.pool._poison(None, "source worker cleanup was uncertain", all_active=True)
            for thread in live_workers:
                thread.join(0.05)
        self.telemetry.source_end_ns = time.monotonic_ns()
        self.telemetry.final_drain_start_ns = time.monotonic_ns()
        self.drain(self.config.cleanup_timeout)
        self.telemetry.final_drain_end_ns = time.monotonic_ns()

        dispatcher_error = self.dispatcher.dispatcher_error if self.dispatcher else None
        cleanup_errors = list(self.dispatcher.cleanup_errors) if self.dispatcher else []
        with errors_lock:
            worker_errors = list(errors)
            worker_cleanup_errors = list(producer_cleanup_errors)
        source_errors = [error for error in worker_errors if not isinstance(error, (CancellationError, PoolPoisonedError))]
        primary = source_errors[0] if source_errors else dispatcher_error
        if primary is None and self._cancel_requested:
            primary = CancellationError("Golden QD transport was explicitly cancelled")
        if primary is None and worker_errors:
            primary = worker_errors[0]
        telemetry = self.telemetry.snapshot(self.config.queue_depth, sum(s == SlotState.FREE for s in self.pool.states()))
        secondary: list[BaseException] = []
        for error in (cleanup_errors + worker_cleanup_errors + worker_errors):
            if error is not primary and error not in secondary:
                secondary.append(error)
        if dispatcher_error is not None and dispatcher_error is not primary:
            secondary.insert(0, dispatcher_error)
        # Cancellation is never a successful result, but completed records are
        # still reconciled for accounting and queued records are intentionally
        # absent from this set.
        completed = self.dispatcher.completed_records if self.dispatcher else ()
        expected = {(r.source_offset, r.target_offset, r.length, r.record_id) for r in source_ranges}
        actual = {(r.source_offset, r.destination_offset, r.nbytes, r.record_id) for r in completed}
        if len(completed) != len(actual):
            secondary.append(ReconciliationError("completed records were duplicated"))
        if self.telemetry.h2d_submitted_bytes != self.telemetry.h2d_completed_bytes:
            secondary.append(ReconciliationError("submitted and completed H2D byte counts differ"))
        if primary is not None:
            raise TransportFailure(primary, secondary_errors=secondary, telemetry=telemetry, cancelled=self._cancel_requested) from primary
        if actual != expected or len(completed) != len(source_ranges):
            raise TransportFailure(ReconciliationError("source record coverage is missing or duplicated"), secondary_errors=secondary, telemetry=telemetry) from None
        # A caller that supplies a CUDA destination may request only source
        # reads and H2D submission/completion.  In that mode the destination
        # remains the caller-owned backing store and is never copied to CPU.
        output = None
        if exact_destination_size is not None and materialize_output:
            output = _read_destination(getattr(self.backend, "destination", None), exact_destination_size)
        return TransportResult(tuple(sorted(completed, key=lambda r: (r.destination_offset, r.source_offset))), self.telemetry.h2d_submitted_bytes, self.telemetry.h2d_completed_bytes, output, telemetry)

    def snapshot_quiescence(self) -> bool:
        with self._active_lock:
            producers = self._active_producers
        dispatcher_live = self.dispatcher is not None and self.dispatcher._thread is not None and self.dispatcher._thread.is_alive()
        queue_live = bool(self.dispatcher and self.dispatcher._queue)
        handoff_live = bool(self.dispatcher and self.dispatcher._handoff)
        events_live = bool(self.dispatcher and self.dispatcher._in_flight)
        slot_live = any(state in (SlotState.FILLING, SlotState.READY, SlotState.IN_FLIGHT) for state in self.pool.states())
        if producers or dispatcher_live or queue_live or handoff_live or events_live or slot_live:
            raise TransportError("snapshot requires no live producer, dispatcher, slot, event, or queue state")
        return True


QDTransport = GoldenQDTransport


class LegacyTransport:
    """Legacy availability/API selector; it does not implement QD dispatch."""

    def __init__(self, config: TransportConfig | None = None, backend: TransportBackend | None = None) -> None:
        self.config = replace(config or TransportConfig(), queue_depth=1, ready_queue_capacity=1)
        self.backend = backend
        self.arm = LEGACY_ARM
        self.dispatcher = None
        self.available = True

    def execute(self, *args: Any, **kwargs: Any) -> TransportResult:
        raise TransportError("legacy execution is owned by the Golden legacy loader")


def create_transport(arm: str | None = None, *, config: TransportConfig | None = None, backend: TransportBackend | None = None) -> GoldenQDTransport | LegacyTransport:
    selected = normalize_transport_arm(arm)
    return LegacyTransport(config, backend) if selected == LEGACY_ARM else GoldenQDTransport(config, backend, arm=selected)


class FakeEvent:
    def __init__(self, pending_polls: int, uncertain: bool = False, failed: bool = False) -> None:
        self.pending_polls = pending_polls
        self.uncertain = uncertain
        self.failed = failed
        self.cancelled = False


class FakeBackend:
    """Deterministic test backend.  It must always be explicitly supplied."""

    def __init__(self, *, h2d_delay_polls: int = 0, event_uncertain: bool = False, event_failed: bool = False, fail_submit: BaseException | None = None, destination: bytearray | None = None) -> None:
        if h2d_delay_polls < 0:
            raise ValueError("h2d_delay_polls must be non-negative")
        self.h2d_delay_polls = h2d_delay_polls
        self.event_uncertain = event_uncertain
        self.event_failed = event_failed
        self.fail_submit = fail_submit
        self.destination = destination if destination is not None else bytearray()
        self.submissions: list[tuple[int, int]] = []
        self.poll_count = 0

    def submit_h2d(self, source: Any, destination_offset: int) -> FakeEvent:
        if self.fail_submit is not None:
            raise self.fail_submit
        data = bytes(source)
        end = destination_offset + len(data)
        if end > len(self.destination):
            self.destination.extend(b"\0" * (end - len(self.destination)))
        self.destination[destination_offset:end] = data
        self.submissions.append((destination_offset, len(data)))
        return FakeEvent(self.h2d_delay_polls, self.event_uncertain, self.event_failed)

    def poll_event(self, event: FakeEvent) -> EventStatus:
        self.poll_count += 1
        if event.cancelled:
            return EventStatus.COMPLETE
        if event.pending_polls:
            event.pending_polls -= 1
            return EventStatus.PENDING
        if event.uncertain:
            return EventStatus.UNCERTAIN
        if event.failed:
            return EventStatus.FAILED
        return EventStatus.COMPLETE

    def cancel_event(self, event: FakeEvent) -> None:
        event.cancelled = True


class CudaTransferBackend:
    """Minimal production adapter for a caller-owned CUDA uint8 destination."""

    def __init__(self, destination: Any, *, stream: Any = None) -> None:
        try:
            import torch
        except ImportError as exc:
            raise TransportError("CudaTransferBackend requires torch") from exc
        torch_uint8 = getattr(torch, "uint8")
        if not isinstance(destination, torch.Tensor) or destination.dtype != torch_uint8 or not destination.is_cuda or destination.dim() != 1:
            raise ValueError("destination must be a one-dimensional CUDA uint8 torch tensor")
        self.torch = torch
        self.destination = destination
        self.stream = stream

    @staticmethod
    def allocate_staging_buffers(slots: int, block_bytes: int) -> list[Any]:
        try:
            import torch
        except ImportError as exc:
            raise TransportError("CUDA staging allocation requires torch") from exc
        if not torch.cuda.is_available():
            raise TransportError("CUDA is unavailable for pinned staging allocation")
        torch_empty = getattr(torch, "empty")
        torch_uint8 = getattr(torch, "uint8")
        return [torch_empty(block_bytes, dtype=torch_uint8, pin_memory=True) for _ in range(slots)]

    def submit_h2d(self, source: Any, destination_offset: int) -> Any:
        torch = self.torch
        torch_uint8 = getattr(torch, "uint8")
        if not isinstance(source, torch.Tensor) or source.dtype != torch_uint8 or source.dim() != 1 or source.is_cuda:
            raise ValueError("CUDA backend requires a one-dimensional CPU uint8 staging tensor")
        end = destination_offset + source.numel()
        if destination_offset < 0 or end > self.destination.numel():
            raise ReconciliationError("CUDA destination offset is out of bounds")
        stream = self.stream or torch.cuda.current_stream(device=self.destination.device)
        with torch.cuda.stream(stream):
            self.destination[destination_offset:end].copy_(source, non_blocking=True)
            event = torch.cuda.Event()
            event.record(stream)
        return event

    def poll_event(self, event: Any) -> EventStatus:
        try:
            return EventStatus.COMPLETE if bool(event.query()) else EventStatus.PENDING
        except BaseException as exc:
            raise TransportError("CUDA event query is uncertain") from exc

    def cancel_event(self, event: Any) -> None:
        raise TransportError("CUDA completion events cannot be cancelled safely")


class FakeSource:
    def __init__(self, data: bytes, *, short_reads: int = 0, fail_at: set[int] | None = None) -> None:
        self.data = data
        self.short_reads = short_reads
        self.fail_at = set(fail_at or ())
        self.calls: list[tuple[int, int]] = []

    def read(self, offset: int, length: int) -> bytes:
        self.calls.append((offset, length))
        if offset in self.fail_at:
            raise OSError(f"injected source read failure at {offset}")
        available = min(length, len(self.data) - offset)
        if self.short_reads and available > 1:
            available = min(available, self.short_reads)
        return self.data[offset : offset + max(0, available)]


class BackingOwner:
    def __init__(self, storage: bytes | bytearray | memoryview, identity: str = "backing") -> None:
        self.storage = bytearray(storage)
        self.identity = identity
        self.released = False

    def view(self, offset: int, length: int) -> memoryview:
        if self.released:
            raise RuntimeError("backing owner has been released")
        if offset < 0 or length < 0 or offset + length > len(self.storage):
            raise ValueError("backing view is out of bounds")
        return memoryview(self.storage)[offset : offset + length]

    def adopt(self) -> "BackingAdoption":
        return BackingAdoption(self)

    def release(self) -> None:
        self.released = True


@dataclass
class BackingAdoption:
    owner: BackingOwner
    retained: bool = True

    @property
    def alive(self) -> bool:
        return self.retained and not self.owner.released

    def close(self) -> None:
        self.retained = False
        self.owner.release()


def map_output_views(owner: BackingOwner, specs: Iterable[OutputViewSpec]) -> dict[str, memoryview]:
    result: dict[str, memoryview] = {}
    for spec in specs:
        if spec.name in result:
            raise ValueError(f"duplicate output view name {spec.name!r}")
        result[spec.name] = owner.view(spec.offset, spec.length)
    return result


def prove_backing_survives_stage_release() -> bool:
    owner = BackingOwner(b"0123456789")
    adoption = owner.adopt()
    pool = StagingPool(slots=1, block_bytes=4)
    lease = pool.acquire()
    lease.fill(b"data")
    pool.return_lease(lease)
    survived = adoption.alive and bytes(owner.view(2, 3)) == b"234"
    adoption.close()
    return survived


def _read_destination(destination: Any, size: int) -> bytes:
    if destination is None:
        return b""
    if isinstance(destination, (bytes, bytearray, memoryview)):
        return bytes(destination[:size])
    try:
        return bytes(destination[:size].detach().cpu().tolist())
    except AttributeError:
        return bytes(destination[:size])


__all__ = [
    "BackingAdoption", "BackingOwner", "CancellationError", "CudaTransferBackend", "DEFAULT_BLOCK_BYTES",
    "DEFAULT_QUEUE_DEPTH", "DEFAULT_STAGING_SLOTS", "DISPATCHER_ARM", "EventStatus", "FakeBackend", "FakeEvent",
    "FakeSource", "GoldenQDTransport", "LEGACY_ARM", "LeaseError", "LegacyTransport", "OutputViewSpec",
    "PoolPoisonedError", "QDTransport", "ReadyRecord", "ReconciliationError", "SlotState", "SourceRange",
    "StageLease", "StagingPool", "TransportBackend", "TransportConfig", "TransportDispatcher", "TransportError",
    "TransportFailure", "TransportResult", "create_transport", "map_output_views", "normalize_transport_arm",
    "prove_backing_survives_stage_release",
]
