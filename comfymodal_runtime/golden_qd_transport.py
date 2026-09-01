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
CONTROL_ARM = DISPATCHER_ARM
STATIC_E27_ARM = "static_e27"
TEST_ARM = STATIC_E27_ARM
STATIC_E27_PRODUCERS = 4
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
    if selected == "control":
        selected = CONTROL_ARM
    elif selected == "test":
        selected = TEST_ARM
    if selected not in (LEGACY_ARM, DISPATCHER_ARM, STATIC_E27_ARM):
        raise ValueError(
            f"unknown Golden QD transport arm {selected!r}; "
            "expected legacy, dispatcher, or static_e27"
        )
    return selected


def static_e27_regions(total: int, producer_count: int = STATIC_E27_PRODUCERS) -> tuple[tuple[int, int], ...]:
    """Return fixed E27 regions as relative ``[start, end)`` byte ranges.

    Regions are planned once per transport.  Empty trailing regions are kept
    so the static arm always has the four explicit producer identities used by
    the E27 probe, including for very short test inputs.
    """
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ValueError("total must be a non-negative integer")
    if producer_count != STATIC_E27_PRODUCERS:
        raise ValueError("static E27 transport requires exactly four producers")
    width = (total + producer_count - 1) // producer_count if total else 0
    return tuple(
        (min(i * width, total), min((i + 1) * width, total))
        for i in range(producer_count)
    )


def static_segments(total: int, qd: int) -> tuple[tuple[int, int], ...]:
    """E27-compatible non-empty static segmentation helper."""
    if isinstance(total, bool) or not isinstance(total, int):
        raise ValueError("total must be an integer")
    if isinstance(qd, bool) or not isinstance(qd, int) or qd <= 0 or total < 0:
        raise ValueError("invalid total or qd")
    if total == 0:
        return ()
    width = (total + qd - 1) // qd
    return tuple(
        (start, min(start + width, total))
        for start in (i * width for i in range(qd))
        if start < total
    )


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
    producer_id: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_offset, int) or isinstance(self.source_offset, bool) or self.source_offset < 0:
            raise ValueError("source_offset must be non-negative")
        if not isinstance(self.destination_offset, int) or isinstance(self.destination_offset, bool) or self.destination_offset < 0:
            raise ValueError("destination_offset must be non-negative")
        if not isinstance(self.nbytes, int) or isinstance(self.nbytes, bool) or self.nbytes < 1:
            raise ValueError("nbytes must be positive")
        if self.record_id is not None and not isinstance(self.record_id, (str, int)):
            raise ValueError("record_id must be a string, integer, or None")
        if self.producer_id is not None and (
            not isinstance(self.producer_id, int)
            or isinstance(self.producer_id, bool)
            or self.producer_id < 0
        ):
            raise ValueError("producer_id must be a non-negative integer or None")


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


class PinnedRangeReader(Protocol):
    """The narrow zero-copy source contract used by the dispatcher arm.

    ``target`` is writable lease storage and is valid only for this call.
    Implementations must fill at most ``len(target)`` bytes starting at the
    absolute source ``offset`` and return the number written.  The explicit
    offset avoids a shared seek/read cursor between producer workers.
    """

    def readinto(self, target: Any, offset: int, producer_id: int | None = None) -> int:
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
    if record.producer_id is not None and (
        not isinstance(record.producer_id, int)
        or isinstance(record.producer_id, bool)
        or record.producer_id < 0
    ):
        raise ReconciliationError("invalid producer id")


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

    def __init__(
        self,
        pool: "StagingPool",
        slot: _Slot,
        generation: int,
        declared_range: SourceRange | None,
        producer_id: int | None = None,
    ) -> None:
        self._pool = pool
        self.slot_index = slot.index
        self.generation = generation
        self.capacity_class = slot.capacity_class
        self._declared_range = declared_range
        self._filled = 0
        self._returned = False
        self._producer_retired = False
        self.producer_id = producer_id
        self._producer_identity: int | None = producer_id

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

    def _read_target(self, nbytes: int) -> Any:
        """Return a bounded, ephemeral writable target for a source reader."""
        if not isinstance(nbytes, int) or isinstance(nbytes, bool) or not 0 < nbytes <= self._pool.block_bytes:
            raise LeaseError("invalid read target size")
        with self._pool._meta:
            slot = self._pool._validate_locked(self)
            if slot.state != SlotState.FILLING or self._producer_retired:
                raise LeaseError("lease is no longer writable")
            return _buffer_slice(slot.buffer, nbytes)

    def retire(self) -> None:
        """Relinquish producer ownership before the dispatcher can return it."""
        with self._pool._meta:
            slot = self._pool._validate_locked(self)
            if slot.state != SlotState.FILLING:
                raise LeaseError("only a filling lease can be retired")
            self._producer_retired = True
            self._producer_identity = self.producer_id


def _buffer_slice(buffer: Any, nbytes: int, offset: int = 0) -> Any:
    """Slice byte-addressable storage without converting it to Python bytes."""
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise LeaseError("staging buffer slice offset is invalid")
    if not isinstance(nbytes, int) or isinstance(nbytes, bool) or nbytes < 0:
        raise LeaseError("staging buffer slice length is invalid")
    try:
        return memoryview(buffer)[offset : offset + nbytes]
    except (TypeError, ValueError):
        try:
            return buffer[offset : offset + nbytes]
        except (TypeError, ValueError, RuntimeError) as exc:
            raise LeaseError("staging buffer is not sliceable as uint8 storage") from exc


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
            source = getattr(torch, "frombuffer")(memoryview(data), dtype=getattr(torch, "uint8"))
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
        self._expected_abort_cleanup: set[int] = set()

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
        producer_id: int | None = None,
    ) -> StageLease:
        requested = self.capacity_class if capacity_class is None else capacity_class
        if requested != self.capacity_class:
            raise LeaseError("staging capacity class mismatch")
        if producer_id is not None and (
            not isinstance(producer_id, int)
            or isinstance(producer_id, bool)
            or producer_id < 0
        ):
            raise LeaseError("producer_id must be a non-negative integer")
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
                        lease = StageLease(
                            self, slot, slot.generation, declared_range, producer_id
                        )
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
            lease._producer_identity = lease.producer_id
            self._free_locked(slot, lease)

    release = return_lease

    def _free_locked(self, slot: _Slot, lease: StageLease) -> None:
        slot.state = SlotState.FREE
        slot.lease = None
        lease._returned = True
        self._available.notify_all()

    def _expect_abort_cleanup(self, lease: StageLease) -> None:
        with self._meta:
            self._expected_abort_cleanup.add(id(lease))

    def _consume_expected_abort_cleanup(self, lease: StageLease, error: BaseException) -> bool:
        """Consume only the stale errors caused by our own abort detachment."""
        if not isinstance(error, LeaseError):
            return False
        if str(error) not in {"stale lease generation", "lease was already returned"}:
            return False
        with self._meta:
            marker = id(lease)
            if marker not in self._expected_abort_cleanup:
                return False
            self._expected_abort_cleanup.remove(marker)
            return True

    def _buffer_for_read(self, lease: StageLease, nbytes: int) -> Any:
        return lease._read_target(nbytes)

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
            lease._producer_identity = lease.producer_id
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
            # Full-block CPU torch staging is submitted as the original slot
            # object.  The source reader gets a separate bytes-compatible view
            # of that same storage; the backend must retain the tensor API.
            try:
                import torch
                if (
                    isinstance(slot.buffer, torch.Tensor)
                    and slot.buffer.dtype == getattr(torch, "uint8")
                    and slot.buffer.dim() == 1
                    and nbytes == slot.buffer.numel()
                ):
                    return slot.buffer
            except (ImportError, TypeError, ValueError, RuntimeError):
                pass
            return _buffer_slice(slot.buffer, nbytes)

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

    def _poison(
        self,
        lease: StageLease | None,
        reason: str,
        *,
        all_active: bool = False,
        expected_abort: bool = False,
    ) -> None:
        with self._available:
            self._poisoned = True
            self._poison_reason = reason
            for slot in self._slots:
                if all_active or (lease is not None and slot.lease is lease and slot.generation == lease.generation):
                    if slot.lease is not None:
                        if expected_abort:
                            self._expected_abort_cleanup.add(id(slot.lease))
                        slot.state = SlotState.POISONED
                        slot.lease._returned = True
                        slot.lease = None
            self._available.notify_all()

    def states(self) -> tuple[SlotState, ...]:
        with self._meta:
            return tuple(slot.state for slot in self._slots)


@dataclass
class _Telemetry:
    diagnostics_enabled: bool = True
    entry_ns: int | None = None
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
    producer_capacity_block_wall_ns: int | None = None
    producer_capacity_block_count: int | None = None
    ready_queue_block_wall_ns: int | None = None
    ready_queue_block_count: int | None = None
    dispatcher_reap_wall_ns: int | None = None
    dispatcher_reap_count: int | None = None
    h2d_latencies_ns: list[int] | None = None
    qd_samples: list[int] | None = None
    source_qd_target: int | None = None
    source_qd_depth: int | None = None
    source_qd_depth_samples: list[int] | None = None
    source_qd_timeline: list[dict[str, int]] | None = None
    _source_qd_start_ns: int | None = field(default=None, repr=False)
    _source_qd_last_transition_ns: int | None = field(default=None, repr=False)
    _source_qd_target_time_ns: int = field(default=0, repr=False)
    ready_depth: int | None = None
    min_free_slots: int | None = None
    owner: Any = None
    adoption: Any = None
    owner_count: Any = None
    adoption_result: Any = None
    execution_arm: str = DISPATCHER_ARM
    fallback_count: int = 0
    fallback_reason: str | None = None
    source_read_mode: str = "legacy_bytes"
    direct_readinto_count: int = 0
    static_regions: list[dict[str, int]] | None = None
    producer_read_bytes: dict[int, int] | None = None
    producer_read_counts: dict[int, int] | None = None
    producer_last_source_offset: dict[int, int] | None = None
    producer_offset_monotonic: bool = True
    producer_destination_offsets: dict[int, list[int]] | None = None
    producer_destination_offset_monotonic: bool | None = True
    producer_ids: tuple[int, ...] = ()
    poisoned: bool = False
    poison_reason: str | None = None
    coverage_ok: bool | None = None
    h2d_reconciled: bool | None = None
    late_submission_count: int | None = None
    late_submission_resolved_count: int | None = None
    late_submission_unresolved_count: int | None = None
    event_cancel_count: int | None = None
    completion_classification: str = "normal"
    _lock: threading.Lock | None = field(default=None, repr=False)
    _correctness_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        if self.diagnostics_enabled:
            self._lock = threading.Lock()
            self.entry_ns = time.monotonic_ns()
            self.producer_capacity_block_wall_ns = 0
            self.producer_capacity_block_count = 0
            self.ready_queue_block_wall_ns = 0
            self.ready_queue_block_count = 0
            self.dispatcher_reap_wall_ns = 0
            self.dispatcher_reap_count = 0
            self.late_submission_count = 0
            self.late_submission_resolved_count = 0
            self.late_submission_unresolved_count = 0
            self.event_cancel_count = 0
            self.h2d_latencies_ns = []
            self.qd_samples = []
            self.source_qd_depth_samples = []
            self.source_qd_timeline = []
            self.producer_destination_offsets = {}
            self.producer_destination_offset_monotonic = True
        else:
            # Destination order is an optional observation, not a correctness
            # counter.  Diagnostics-off must not report that it was observed.
            self.producer_destination_offset_monotonic = None
        self.source_qd_depth = 0 if self.diagnostics_enabled else None
        self.producer_read_bytes = {}
        self.producer_read_counts = {}
        self.producer_last_source_offset = {}

    def source_read(
        self,
        nbytes: int,
        *,
        duplicate: bool = False,
        producer_id: int | None = None,
        source_offset: int | None = None,
    ) -> None:
        with self._correctness_lock:
            self.source_read_count += 1
            self.source_bytes += nbytes
            if duplicate:
                self.duplicate_read_count += 1
            if producer_id is not None:
                assert self.producer_read_bytes is not None
                assert self.producer_read_counts is not None
                self.producer_read_bytes[producer_id] = self.producer_read_bytes.get(producer_id, 0) + nbytes
                self.producer_read_counts[producer_id] = self.producer_read_counts.get(producer_id, 0) + 1
                if source_offset is not None:
                    assert self.producer_last_source_offset is not None
                    previous = self.producer_last_source_offset.get(producer_id)
                    if previous is not None and source_offset < previous:
                        self.producer_offset_monotonic = False
                    self.producer_last_source_offset[producer_id] = source_offset

    def configure_source_qd(self, target: int) -> None:
        if not self.diagnostics_enabled:
            self.source_qd_target = target
            return
        with self._correctness_lock:
            self.source_qd_target = target

    def source_read_begin(self) -> None:
        self._source_qd_transition(1)

    def source_read_end(self) -> None:
        self._source_qd_transition(-1)

    def note_record(self, record: ReadyRecord) -> None:
        if not self.diagnostics_enabled or record.producer_id is None:
            return
        assert self.producer_destination_offsets is not None
        with self._correctness_lock:
            offsets = self.producer_destination_offsets.setdefault(record.producer_id, [])
            if offsets and record.destination_offset < offsets[-1]:
                self.producer_destination_offset_monotonic = False
            offsets.append(record.destination_offset)

    def _source_qd_transition(self, delta: int) -> None:
        if not self.diagnostics_enabled:
            return
        assert self._lock is not None
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
            next_depth = int(self.source_qd_depth or 0) + delta
            if next_depth < 0:
                raise RuntimeError("source-read QD became negative")
            self.source_qd_depth = next_depth
            self._source_qd_last_transition_ns = now
            assert self.source_qd_depth_samples is not None
            assert self.source_qd_timeline is not None
            self.source_qd_depth_samples.append(next_depth)
            self.source_qd_timeline.append({"timestamp_ns": now, "depth": next_depth})

    def snapshot(self, queue_depth: int, free_slots: int, total_end_ns: int | None = None) -> dict[str, Any]:
        if self.diagnostics_enabled:
            assert self._lock is not None
            with self._lock:
                return self._snapshot_locked(queue_depth, free_slots, total_end_ns)
        with self._correctness_lock:
            return self._snapshot_locked(queue_depth, free_slots, total_end_ns)

    def _snapshot_locked(self, queue_depth: int, free_slots: int, total_end_ns: int | None) -> dict[str, Any]:
            end = (
                time.monotonic_ns() if self.diagnostics_enabled and total_end_ns is None
                else total_end_ns
            )
            source_wall = (
                None if not self.diagnostics_enabled or self.source_start_ns is None
                else (self.source_end_ns or end or self.source_start_ns) - self.source_start_ns
            )
            drain_wall = (
                None if not self.diagnostics_enabled or self.final_drain_start_ns is None
                else (self.final_drain_end_ns or end or self.final_drain_start_ns) - self.final_drain_start_ns
            )
            qd = list(self.qd_samples) if self.qd_samples is not None else None
            source_qd = (
                list(self.source_qd_depth_samples)
                if self.source_qd_depth_samples is not None else None
            )
            source_qd_timeline = (
                list(self.source_qd_timeline)
                if self.source_qd_timeline is not None else None
            )
            source_qd_target = self.source_qd_target if self.source_qd_target is not None else queue_depth
            last_source_transition = self._source_qd_last_transition_ns
            # Once all reads have ended, H2D drain time is outside the source
            # QD observation window.  If a read is still outstanding (for a
            # bounded-failure snapshot), account through the snapshot boundary.
            source_qd_end = (
                max(end, last_source_transition or end)
                if self.diagnostics_enabled and end is not None and self.source_qd_depth
                else (last_source_transition or end or 0)
            )
            source_qd_wall = (
                None
                if not self.diagnostics_enabled or self._source_qd_start_ns is None
                else source_qd_end - self._source_qd_start_ns
            )
            target_time = self._source_qd_target_time_ns
            if self.diagnostics_enabled and (
                self._source_qd_last_transition_ns is not None
                and self.source_qd_depth == source_qd_target
            ):
                target_time += source_qd_end - self._source_qd_last_transition_ns
            target_fraction = (
                target_time / source_qd_wall
                if source_qd_wall is not None and source_qd_wall else None
            )
            latency = (
                sum(self.h2d_latencies_ns) / len(self.h2d_latencies_ns)
                if self.h2d_latencies_ns else None
            )
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
                "total_entry_to_return_wall_ms": (
                    (end - self.entry_ns) / 1e6
                    if self.diagnostics_enabled and end is not None and self.entry_ns is not None else None
                ),
                "source_aggregate_wall_ms": source_wall / 1e6 if source_wall is not None else None,
                "source_wall_ms": source_wall / 1e6 if source_wall is not None else None,
                "source_throughput_bytes_s": (
                    self.source_bytes / (source_wall / 1e9)
                    if source_wall else None
                ),
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
                "minimum_free_slots": self.min_free_slots if self.diagnostics_enabled else None,
                "min_free_slots": self.min_free_slots if self.diagnostics_enabled else None,
                "producer_capacity_block_wall_ms": (
                    self.producer_capacity_block_wall_ns / 1e6
                    if self.producer_capacity_block_wall_ns is not None else None
                ),
                "producer_capacity_block_count": self.producer_capacity_block_count,
                "ready_queue_block_wall_ms": (
                    self.ready_queue_block_wall_ns / 1e6
                    if self.ready_queue_block_wall_ns is not None else None
                ),
                "ready_queue_block_count": self.ready_queue_block_count,
                "dispatcher_reap_wall_ms": (
                    self.dispatcher_reap_wall_ns / 1e6
                    if self.dispatcher_reap_wall_ns is not None else None
                ),
                "dispatcher_reap_count": self.dispatcher_reap_count,
                "h2d_event_completion_latency_ms": latency,
                "final_drain_wall_ms": drain_wall / 1e6 if drain_wall is not None else None,
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
                "source_read_mode": self.source_read_mode,
                "reader_mode": self.source_read_mode,
                "direct_readinto_count": self.direct_readinto_count,
                "static_regions": list(self.static_regions) if self.static_regions is not None else None,
                "producer_ids": list(self.producer_ids),
                "producer_read_bytes": dict(self.producer_read_bytes or {}),
                "producer_read_counts": dict(self.producer_read_counts or {}),
                "producer_offset_monotonic": self.producer_offset_monotonic,
                "producer_destination_offset_monotonic": self.producer_destination_offset_monotonic,
                "producer_destination_offsets": (
                    {str(k): list(v) for k, v in self.producer_destination_offsets.items()}
                    if self.producer_destination_offsets is not None else None
                ),
                "poisoned": self.poisoned,
                "poison_reason": self.poison_reason,
                "coverage": {
                    "ok": self.coverage_ok,
                    "source_bytes": self.source_bytes,
                    "h2d_submitted_bytes": self.h2d_submitted_bytes,
                    "h2d_completed_bytes": self.h2d_completed_bytes,
                },
                "h2d_reconciliation": {
                    "ok": self.h2d_reconciled,
                    "submitted_bytes": self.h2d_submitted_bytes,
                    "completed_bytes": self.h2d_completed_bytes,
                },
                "python_payload_materialization": self.source_read_mode != "direct_readinto",
                "late_submission_count": self.late_submission_count,
                "late_submission_resolved_count": self.late_submission_resolved_count,
                "late_submission_unresolved_count": self.late_submission_unresolved_count,
                "event_cancel_count": self.event_cancel_count,
                "completion_classification": self.completion_classification,
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
        self.retained_owner: Any = None
        self.retained_transport: Any = None
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
        self._uncertain_handoffs: dict[int, tuple[StageLease, ReadyRecord]] = {}
        self._late_submissions: dict[int, tuple[StageLease, ReadyRecord, Any, int | None]] = {}
        self._unresolved_late_submission_keys: set[int] = set()
        self._in_flight: dict[int, tuple[StageLease, ReadyRecord, Any, int | None]] = {}
        self._completed_records: list[ReadyRecord] = []
        self._dispatcher_error: BaseException | None = None
        self._cleanup_errors: list[BaseException] = []
        # Pool bookkeeping and bounded detachment must not race.  Backend
        # calls deliberately happen outside this lock; only the lease/event
        # state transition is serialized with cleanup.
        self._lease_cleanup_lock = threading.RLock()
        self._stop = False
        self._cancelled = False
        self._cleanup_deadline: float | None = None
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

    @property
    def unresolved_late_events(self) -> int:
        """Number of late backend events whose terminal state is not proven."""
        with self._queue_condition:
            # A newly registered late event is unresolved until its first
            # terminal classification; do not create a release window between
            # registration and the cancellation poll.
            return len(self._late_submissions)

    def start(self) -> None:
        if self._thread is not None:
            raise TransportError("dispatcher already started")
        self._thread = threading.Thread(target=self._run, name="golden-qd-dispatcher", daemon=True)
        self._thread.start()

    def publish(self, lease: StageLease, record: ReadyRecord) -> None:
        _validate_ready_record(record)
        started = time.monotonic_ns() if self.telemetry.diagnostics_enabled else None
        blocked = False
        capacity = self.config.ready_queue_capacity
        assert capacity is not None
        with self._lease_cleanup_lock:
            with self._queue_condition:
                while len(self._queue) >= capacity and not self._cancelled and not self._stop:
                    blocked = True
                    self._queue_condition.wait()
                if blocked and self.telemetry.diagnostics_enabled:
                    assert started is not None
                    assert self.telemetry.ready_queue_block_count is not None
                    assert self.telemetry.ready_queue_block_wall_ns is not None
                    self.telemetry.ready_queue_block_count += 1
                    self.telemetry.ready_queue_block_wall_ns += time.monotonic_ns() - started
                if self._cancelled:
                    raise CancellationError("transport was cancelled before publish")
                if self._stop:
                    raise CancellationError("transport was quiesced before publish")
                # This call does not call back into the dispatcher condition.
                self.pool._mark_ready(lease, record, self.destination_size)
                self._queue.append((lease, record))
                if self.telemetry.diagnostics_enabled:
                    self.telemetry.ready_depth = len(self._queue)
                self._queue_condition.notify_all()

    def quiesce(self) -> None:
        with self._queue_condition:
            self._stop = True
            self._queue_condition.notify_all()

    def cancel(self, *, deadline: float | None = None) -> None:
        with self._queue_condition:
            self._cancelled = True
            self._stop = True
            if deadline is not None:
                self._cleanup_deadline = (
                    deadline if self._cleanup_deadline is None
                    else min(self._cleanup_deadline, deadline)
                )
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
        started = time.monotonic_ns() if self.telemetry.diagnostics_enabled else None
        with self._queue_condition:
            active = list(self._in_flight.items())
            if self.telemetry.diagnostics_enabled:
                assert self.telemetry.qd_samples is not None
                self.telemetry.qd_samples.append(len(active))
        for key, (lease, record, event, submit_ns) in active:
            try:
                raw_status = self.backend.poll_event(event)
                status = EventStatus(raw_status)
            except BaseException as exc:
                with self._lease_cleanup_lock:
                    with self._queue_condition:
                        current = self._in_flight.pop(key, None)
                        self._queue_condition.notify_all()
                    if current is None or lease._returned:
                        continue
                    self.pool._poison(lease, "H2D poll was uncertain")
                raise TransportError("H2D poll failed; staging pool poisoned") from exc
            if status == EventStatus.PENDING:
                continue
            with self._lease_cleanup_lock:
                # Bounded drain may have detached and poisoned this lease
                # while poll_event was in progress.  It owns that cleanup;
                # do not turn the expected stale generation into a second
                # dispatcher failure.
                with self._queue_condition:
                    current = self._in_flight.pop(key, None)
                    self._queue_condition.notify_all()
                if current is None or lease._returned:
                    continue
                if status == EventStatus.COMPLETE:
                    # The completion event is the proof that the submitted
                    # copy finished.  Count it before pool bookkeeping so a
                    # cleanup race cannot make telemetry claim it did not.
                    self.telemetry.h2d_completed_bytes += record.nbytes
                    self.telemetry.h2d_completed_count += 1
                    self.pool._return_completed(lease)
                    with self._queue_condition:
                        self._completed_records.append(record)
                    if self.telemetry.diagnostics_enabled:
                        assert submit_ns is not None
                        assert self.telemetry.h2d_latencies_ns is not None
                        self.telemetry.h2d_latencies_ns.append(time.monotonic_ns() - submit_ns)
                elif status == EventStatus.UNCERTAIN:
                    self.pool._poison(lease, "uncertain H2D completion")
                    self.telemetry.completion_classification = "uncertain"
                    raise TransportError("uncertain H2D completion; staging pool poisoned")
                else:
                    self.pool._poison(lease, "H2D event failed")
                    self.telemetry.completion_classification = "failed"
                    raise TransportError("H2D completion event failed; staging pool poisoned")
        if self.telemetry.diagnostics_enabled:
            assert started is not None
            assert self.telemetry.dispatcher_reap_count is not None
            assert self.telemetry.dispatcher_reap_wall_ns is not None
            self.telemetry.dispatcher_reap_count += 1
            self.telemetry.dispatcher_reap_wall_ns += time.monotonic_ns() - started

    def _return_queued(self) -> None:
        with self._lease_cleanup_lock:
            with self._queue_condition:
                queued = self._queue[:]
                self._queue.clear()
                if self.telemetry.diagnostics_enabled:
                    self.telemetry.ready_depth = 0
                self._queue_condition.notify_all()
            for lease, _record in queued:
                self.pool._expect_abort_cleanup(lease)
                try:
                    self.pool._return_ready(lease)
                except BaseException as exc:
                    self._note_cleanup(exc)

    def _cancel_in_flight(self, deadline: float | None = None) -> None:
        # Snapshot under the condition, then release it before any backend or
        # pool call.  In particular, never reacquire this condition while it
        # is held by _run.
        with self._queue_condition:
            active = list(self._in_flight.items()) + list(self._late_submissions.items())
        for key, (lease, record, event, _submit_ns) in active:
            with self._queue_condition:
                is_late_submission = key in self._late_submissions
            try:
                if self.telemetry.diagnostics_enabled:
                    assert self.telemetry.event_cancel_count is not None
                    self.telemetry.event_cancel_count += 1
                self.backend.cancel_event(event)
            except BaseException as exc:
                self._note_cleanup(exc)
            status: EventStatus | None = None
            for poll_index in range(self.config.cancellation_poll_limit):
                # Even an expired abort budget gets one post-cancel query. A
                # submit_h2d call may return its event after the deadline, and
                # that event must be explicitly classified rather than
                # silently abandoned.
                if poll_index and deadline is not None and time.monotonic() >= deadline:
                    break
                try:
                    status = EventStatus(self.backend.poll_event(event))
                except BaseException as exc:
                    self._note_cleanup(exc)
                    status = None
                    break
                if status != EventStatus.PENDING:
                    break
            # A successful terminal query is completion proof even for a
            # backend whose event cancellation operation is unsupported.  The
            # cancellation attempt is still required and is accounted above.
            proven = status == EventStatus.COMPLETE
            with self._lease_cleanup_lock:
                with self._queue_condition:
                    current = self._in_flight.get(key) or self._late_submissions.get(key)
                if current is None:
                    # A concurrent bounded drain already detached this event.
                    continue
                if proven:
                    try:
                        self.telemetry.h2d_completed_bytes += record.nbytes
                        self.telemetry.h2d_completed_count += 1
                        if not lease._returned:
                            self.pool._return_completed(lease)
                        with self._queue_condition:
                            self._completed_records.append(record)
                            self._in_flight.pop(key, None)
                            if key in self._late_submissions:
                                self._late_submissions.pop(key, None)
                                self._unresolved_late_submission_keys.discard(key)
                                if self.telemetry.diagnostics_enabled:
                                    assert self.telemetry.late_submission_resolved_count is not None
                                    self.telemetry.late_submission_resolved_count += 1
                                self.telemetry.completion_classification = "late_submit_resolved"
                            else:
                                self.telemetry.completion_classification = "cancelled_resolved"
                    except BaseException as exc:
                        self._note_cleanup(exc)
                elif status == EventStatus.FAILED:
                    # FAILED is terminal.  It is not completion proof, but it
                    # is no longer an unresolved event either.  In particular
                    # do not leave a late submission in the ownership map
                    # forever merely because its copy failed after abort.
                    self.pool._poison(lease, "cancelled H2D completion failed", expected_abort=True)
                    with self._queue_condition:
                        self._in_flight.pop(key, None)
                        self._late_submissions.pop(key, None)
                        self._unresolved_late_submission_keys.discard(key)
                        self._queue_condition.notify_all()
                    self.telemetry.completion_classification = (
                        "late_submit_failed" if is_late_submission else "cancelled_failed"
                    )
                    self._note_cleanup(TransportError("cancelled H2D completion failed"))
                else:
                    self.pool._poison(lease, "cancelled H2D completion was not proven", expected_abort=True)
                    if is_late_submission and key not in self._unresolved_late_submission_keys:
                        self._unresolved_late_submission_keys.add(key)
                        if self.telemetry.diagnostics_enabled:
                            assert self.telemetry.late_submission_unresolved_count is not None
                            self.telemetry.late_submission_unresolved_count += 1
                    self.telemetry.completion_classification = "cancelled_unresolved"
                    if status == EventStatus.PENDING:
                        self._note_cleanup(TransportError("cancelled H2D event remained pending"))
                    elif status == EventStatus.UNCERTAIN:
                        self._note_cleanup(TransportError("cancelled H2D completion was uncertain"))
                with self._queue_condition:
                    if proven:
                        self._in_flight.pop(key, None)
                        self._late_submissions.pop(key, None)
                        self._unresolved_late_submission_keys.discard(key)
                    self._queue_condition.notify_all()

    def _cleanup_cancelled(self, deadline: float | None = None) -> None:
        self._return_queued()
        with self._lease_cleanup_lock:
            with self._queue_condition:
                handoff = list(self._handoff.values())
                self._handoff.clear()
                self._uncertain_handoffs.update({item[0].slot_index: item for item in handoff})
                self._queue_condition.notify_all()
            for lease, _record in handoff:
                self.pool._poison(lease, "cancelled dispatcher handoff was not completed", expected_abort=True)
        self._cancel_in_flight(deadline)

    def _run(self) -> None:
        try:
            while True:
                try:
                    self._poll()
                except BaseException as exc:
                    self._set_dispatcher_error(exc)
                    self._cleanup_cancelled(self._cleanup_deadline)
                    return
                with self._queue_condition:
                    cancelled = self._cancelled
                    item = None
                    if not cancelled and self._queue and len(self._in_flight) < self.config.queue_depth:
                        item = self._queue.pop(0)
                        self._handoff[item[0].slot_index] = item
                        if self.telemetry.diagnostics_enabled:
                            self.telemetry.ready_depth = len(self._queue)
                        self._queue_condition.notify_all()
                    done = self._stop and item is None and not self._queue and not self._in_flight and not self._late_submissions
                if cancelled:
                    self._cleanup_cancelled(self._cleanup_deadline)
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
                    with self._lease_cleanup_lock:
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
                    if self._cancelled:
                        self._cleanup_cancelled(self._cleanup_deadline)
                        return
                    with self._lease_cleanup_lock:
                        self.pool._poison(lease, "H2D submission did not produce a completion event")
                    self._set_dispatcher_error(exc)
                    self._cleanup_cancelled(self._cleanup_deadline)
                    return
                with self._lease_cleanup_lock:
                    with self._queue_condition:
                        handoff = self._handoff.get(lease.slot_index)
                        uncertain = self._uncertain_handoffs.pop(lease.slot_index, None)
                        if handoff is item:
                            self._handoff.pop(lease.slot_index, None)
                            self._in_flight[lease.slot_index] = (
                                lease, record, event,
                                time.monotonic_ns() if self.telemetry.diagnostics_enabled else None,
                            )
                            registration_error = None
                        elif uncertain is item and self._cancelled:
                            # The backend accepted the copy after bounded
                            # cancellation detached the handoff.  It is now a
                            # first-class event, not an ignorable late return.
                            self._late_submissions[lease.slot_index] = (
                                lease, record, event,
                                time.monotonic_ns() if self.telemetry.diagnostics_enabled else None,
                            )
                            if self.telemetry.diagnostics_enabled:
                                assert self.telemetry.late_submission_count is not None
                                self.telemetry.late_submission_count += 1
                            registration_error = None
                        else:
                            # A bounded cancellation may have detached this
                            # handoff without a matching event.  Only an
                            # actual cancellation owns that state.
                            registration_error = TransportError(
                                "dispatcher handoff was cleaned up before event registration"
                            )
                        self._queue_condition.notify_all()
                if registration_error is not None:
                    with self._lease_cleanup_lock:
                        self.pool._poison(lease, str(registration_error))
                    self._set_dispatcher_error(registration_error)
                    self._cleanup_cancelled(self._cleanup_deadline)
                    return
                if self._cancelled:
                    self._cleanup_cancelled(self._cleanup_deadline)
                    return
        finally:
            with self._queue_condition:
                self._queue_condition.notify_all()

    def drain(
        self,
        timeout: float | None = None,
        *,
        bounded: bool = True,
        deadline: float | None = None,
    ) -> None:
        thread = self._thread
        if thread is None:
            return
        if not bounded:
            thread.join()
            return
        if deadline is None:
            budget = self.config.cleanup_timeout if timeout is None else max(0.0, timeout)
            deadline = time.monotonic() + budget
        thread.join(max(0.0, deadline - time.monotonic()))
        if not thread.is_alive():
            return
        # A backend may never settle.  Detach every event and poison every
        # uncertain lease; do not wait indefinitely for a permanently pending
        # event or hold a dispatcher condition while doing pool cleanup.
        with self._lease_cleanup_lock:
            with self._queue_condition:
                queued = self._queue[:]
                active = list(self._in_flight.values()) + list(self._late_submissions.values())
                handoff = list(self._handoff.values())
                self._queue.clear()
                self._handoff.clear()
                self._uncertain_handoffs.update({item[0].slot_index: item for item in handoff})
                self._stop = True
                self._cancelled = True
                self._cleanup_deadline = (
                    deadline if self._cleanup_deadline is None
                    else min(self._cleanup_deadline, deadline)
                )
                if self.telemetry.diagnostics_enabled:
                    self.telemetry.ready_depth = 0
                self._queue_condition.notify_all()
            for lease, _record in queued:
                self.pool._expect_abort_cleanup(lease)
                try:
                    self.pool._return_ready(lease)
                except BaseException as exc:
                    self._note_cleanup(exc)
            for lease, _record in handoff:
                self.pool._poison(lease, "bounded drain could not complete dispatcher handoff", expected_abort=True)
            for lease, _record, _event, _submit_ns in active:
                self.pool._poison(lease, "bounded drain could not prove H2D completion", expected_abort=True)
            for key in self._late_submissions:
                if key not in self._unresolved_late_submission_keys:
                    self._unresolved_late_submission_keys.add(key)
                    if self.telemetry.diagnostics_enabled:
                        assert self.telemetry.late_submission_unresolved_count is not None
                        self.telemetry.late_submission_unresolved_count += 1
        thread.join(max(0.0, deadline - time.monotonic()))
        if thread.is_alive():
            self._note_cleanup(TransportError("dispatcher thread did not stop within bounded drain"))


class GoldenQDTransport:
    """Explicit integration seam for a dispatcher-backed Golden stage."""

    def __init__(
        self,
        config: TransportConfig | None = None,
        backend: TransportBackend | None = None,
        *,
        arm: str | None = None,
        pool: StagingPool | None = None,
        diagnostics: bool = True,
    ) -> None:
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
        self.telemetry = _Telemetry(
            execution_arm=self.arm, diagnostics_enabled=bool(diagnostics)
        )
        self.dispatcher: TransportDispatcher | None = None
        self._active_producers = 0
        self._active_lock = threading.Lock()
        self._cancel_requested = False
        self._abort_requested = False
        self._abort_deadline: float | None = None
        self._abort_lock = threading.Lock()
        self._reader_handles: dict[int, Any] = {}
        self._reader_lock = threading.Lock()
        # Kept only as a lifetime anchor for the fail-closed late-event
        # contract.  The caller remains responsible for releasing an owner
        # after successful transport/adoption or a proven terminal failure.
        self._owner_lifetime: Any = None
        self._static_regions: tuple[tuple[int, int], ...] | None = None
        self._static_work: tuple[tuple[SourceRange, ...], ...] | None = None

    def acquire(
        self,
        timeout: float | None = None,
        *,
        declared_range: SourceRange | None = None,
        producer_id: int | None = None,
    ) -> StageLease:
        started = time.monotonic_ns() if self.telemetry.diagnostics_enabled else None
        try:
            return self.pool.acquire(
                timeout=timeout, declared_range=declared_range, producer_id=producer_id
            )
        finally:
            waited = (
                time.monotonic_ns() - started
                if self.telemetry.diagnostics_enabled and started is not None else None
            )
            if waited is not None and waited > 100_000:
                assert self.telemetry.producer_capacity_block_count is not None
                assert self.telemetry.producer_capacity_block_wall_ns is not None
                self.telemetry.producer_capacity_block_count += 1
                self.telemetry.producer_capacity_block_wall_ns += waited
            if self.telemetry.diagnostics_enabled:
                free = sum(state == SlotState.FREE for state in self.pool.states())
                self.telemetry.min_free_slots = (
                    free if self.telemetry.min_free_slots is None
                    else min(self.telemetry.min_free_slots, free)
                )

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

    def drain(
        self,
        timeout: float | None = None,
        *,
        bounded: bool = True,
        deadline: float | None = None,
    ) -> None:
        if self.dispatcher is not None:
            if self.telemetry.diagnostics_enabled:
                self.telemetry.final_drain_start_ns = time.monotonic_ns()
            self.dispatcher.quiesce()
            self.dispatcher.drain(timeout, bounded=bounded, deadline=deadline)
            if self.telemetry.diagnostics_enabled:
                self.telemetry.final_drain_end_ns = time.monotonic_ns()

    def cancel(self, timeout: float | None = None) -> None:
        self._cancel_requested = True
        # Compute the effective deadline once.  Every participant in this
        # abort (waiters, producers, dispatcher, and drain) must see this same
        # absolute point rather than independently starting a timeout budget.
        deadline = self._begin_abort(timeout)
        self.pool._cancel_waiters()
        if self.dispatcher is not None:
            self.dispatcher.cancel(deadline=deadline)
            self.dispatcher.drain(bounded=True, deadline=deadline)

    def _request_abort(self) -> None:
        self._begin_abort()
        self.pool._cancel_waiters()
        if self.dispatcher is not None:
            self.dispatcher.cancel(deadline=self._abort_deadline)

    def _begin_abort(self, timeout: float | None = None) -> float:
        with self._abort_lock:
            self._abort_requested = True
            budget = self.config.cleanup_timeout if timeout is None else max(0.0, timeout)
            requested_deadline = time.monotonic() + budget
            if self._abort_deadline is None:
                self._abort_deadline = requested_deadline
            else:
                self._abort_deadline = min(self._abort_deadline, requested_deadline)
            return self._abort_deadline

    def backend_owner_release_allowed(self) -> bool:
        """Return whether an adapter may release its CUDA owner.

        An unresolved late submission still has access to the backend's CUDA
        destination.  Adapters must retain the owner (and this transport) in
        that case; releasing storage would make the event's ownership lie
        about the lifetime it actually requires.
        """
        if self.dispatcher is None:
            return True
        with self.dispatcher._queue_condition:
            outstanding = bool(
                self.dispatcher._late_submissions
                or self.dispatcher._in_flight
                or self.dispatcher._handoff
                or self.dispatcher._uncertain_handoffs
            )
            dispatcher_live = (
                self.dispatcher._thread is not None
                and self.dispatcher._thread.is_alive()
            )
            # During cancellation a live dispatcher may still register an
            # event after the caller's bounded drain has returned.  Retain the
            # owner across that race; releasing here would be fail-open.
            return not outstanding and not (self._cancel_requested and dispatcher_live)

    def _retain_failure_lifetime(self, failure: TransportFailure) -> None:
        with self._reader_lock:
            reader_live = bool(self._reader_handles)
        if not self.backend_owner_release_allowed():
            failure.retained_owner = self._owner_lifetime
            failure.retained_transport = self
        elif reader_live:
            # A failed close is retriable through this transport.  Keep the
            # source handle and its transport reachable instead of turning an
            # OS-resource leak into an apparently complete failure path.
            failure.retained_transport = self

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
    def _static_e27_work(
        ranges: Sequence[SourceRange], block_bytes: int
    ) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[SourceRange, ...], ...]]:
        """Plan four fixed source regions and their block-clamped work.

        The input ranges describe the logical destination layout.  Static E27
        deliberately ignores their scheduling order, partitions the contiguous
        source span once, and lets each producer walk only its own region.
        Intersections preserve destination mapping and record identity.
        """
        if not ranges:
            regions = static_e27_regions(0)
            return regions, tuple(() for _ in range(STATIC_E27_PRODUCERS))
        ordered = sorted(ranges, key=lambda item: item.source_offset)
        source_start = ordered[0].source_offset
        cursor = source_start
        destination_cursor = 0
        for item in ordered:
            if item.source_offset != cursor:
                raise ReconciliationError("static E27 source ranges must be contiguous")
            if item.target_offset != destination_cursor:
                raise ReconciliationError(
                    "static E27 destination ranges must preserve canonical forward layout"
                )
            cursor += item.length
            destination_cursor += item.length
        total = cursor - source_start
        regions = static_e27_regions(total)
        work_specs: list[list[tuple[int, SourceRange, int, int]]] = [
            [] for _ in range(STATIC_E27_PRODUCERS)
        ]
        item_index = 0
        for producer_id, (relative_start, relative_end) in enumerate(regions):
            absolute = source_start + relative_start
            region_end = source_start + relative_end
            while absolute < region_end:
                while item_index < len(ordered) and absolute >= ordered[item_index].source_offset + ordered[item_index].length:
                    item_index += 1
                if item_index >= len(ordered):
                    raise ReconciliationError("static E27 region exceeds source ranges")
                item = ordered[item_index]
                item_end = item.source_offset + item.length
                chunk_end = min(region_end, item_end, absolute + block_bytes)
                if chunk_end <= absolute:
                    raise ReconciliationError("static E27 planner did not advance")
                work_specs[producer_id].append((item_index, item, absolute, chunk_end))
                absolute = chunk_end

        chunk_counts: dict[int, int] = {}
        for producer_items in work_specs:
            for original_index, _item, _start, _end in producer_items:
                chunk_counts[original_index] = chunk_counts.get(original_index, 0) + 1
        used_ids = {item.record_id for item in ordered if item.record_id is not None}
        generated_ids: set[str | int] = set()
        work: list[list[SourceRange]] = [[] for _ in range(STATIC_E27_PRODUCERS)]
        chunk_indices: dict[int, int] = {}
        for producer_id, producer_items in enumerate(work_specs):
            for original_index, item, absolute, chunk_end in producer_items:
                chunk_index = chunk_indices.get(original_index, 0)
                chunk_indices[original_index] = chunk_index + 1
                if chunk_counts[original_index] == 1:
                    record_id = item.record_id
                elif chunk_index == 0 and item.record_id is not None:
                    # Preserve the caller's identity once, but never duplicate
                    # it across the chunks of a split source range.
                    record_id = item.record_id
                else:
                    stem = (
                        f"{item.record_id}:static_e27:{chunk_index}"
                        if item.record_id is not None
                        else f"static_e27:{original_index}:{chunk_index}"
                    )
                    record_id = stem
                    suffix = 1
                    while record_id in used_ids or record_id in generated_ids:
                        record_id = f"{stem}:{suffix}"
                        suffix += 1
                    generated_ids.add(record_id)
                work[producer_id].append(
                    SourceRange(
                        absolute,
                        chunk_end - absolute,
                        item.target_offset + (absolute - item.source_offset),
                        record_id,
                    )
                )
        return regions, tuple(tuple(items) for items in work)

    def plan_static_work(
        self, ranges: Iterable[SourceRange], destination_size: int | None = None
    ) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[SourceRange, ...], ...]]:
        """Return the transport-owned static plan before execution begins."""
        if self.arm != STATIC_E27_ARM:
            raise ReconciliationError("static E27 plan requested for non-static arm")
        source_ranges = self._record_ranges(ranges, destination_size)
        return self._static_e27_work(source_ranges, self.config.block_bytes)

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

    @staticmethod
    def _read_exact_into(
        lease: StageLease,
        reader: PinnedRangeReader,
        item: SourceRange,
        retries: int,
        telemetry: _Telemetry,
        producer_id: int,
    ) -> None:
        """Fill one lease directly, retaining no Python payload between reads."""
        target = lease._read_target(item.length)
        offset = item.source_offset
        total = 0
        attempts = 0
        while total < item.length:
            if attempts > retries:
                raise ReconciliationError(f"short read for source range {item.source_offset}:{item.length}")
            view = _buffer_slice(target, item.length - total, total)
            # Do not catch TypeError here: it may be raised after a reader has
            # already touched the target. Retrying through another API would
            # turn one physical source read into an unaccounted duplicate.
            count = reader.readinto(view, offset, producer_id)
            if not isinstance(count, int) or isinstance(count, bool):
                raise ReconciliationError("source readinto must return an integer byte count")
            if count < 0 or count > item.length - total:
                raise ReconciliationError("source readinto returned an invalid byte count")
            attempts += 1
            telemetry.source_read(
                count,
                duplicate=attempts > 1,
                producer_id=producer_id,
                source_offset=offset,
            )
            total += count
            offset += count
        lease.mark_filled(total)
        with telemetry._correctness_lock:
            telemetry.direct_readinto_count += 1

    def _open_source(self, reader: Any) -> tuple[Any, bool]:
        """Open and register a source handle until all producers have joined."""
        opened = reader
        opener = getattr(reader, "open", None)
        if callable(opener):
            opened = opener()
            if opened is None:
                opened = reader
        direct = callable(getattr(opened, "readinto", None))
        if not direct and not callable(opened) and not callable(getattr(opened, "read", None)):
            raise TypeError("source reader must provide readinto(target, offset) or read(offset, length)")
        with self._reader_lock:
            self._reader_handles[id(opened)] = opened
        return opened, direct

    def _close_source(self) -> list[BaseException]:
        with self._reader_lock:
            handles = list(self._reader_handles.items())
        errors: list[BaseException] = []
        for handle_id, handle in handles:
            close = getattr(handle, "close", None)
            if callable(close):
                try:
                    close()
                except BaseException as exc:
                    errors.append(exc)
                    # A failed close is still an open reader.  Keep the exact
                    # handle registered so quiescence cannot pass until a
                    # later close succeeds.
                    continue
            with self._reader_lock:
                if self._reader_handles.get(handle_id) is handle:
                    self._reader_handles.pop(handle_id, None)
        return errors

    def execute(
        self,
        ranges: Iterable[SourceRange],
        reader: PinnedRangeReader | Callable[[int, int], bytes],
        *,
        output_size: int | None = None,
        destination_size: int | None = None,
        materialize_output: bool = True,
        parse_count: int = 0,
        owner: Any = None,
        adoption: Any = None,
        owner_count: Any = None,
        adoption_result: Any = None,
        diagnostics: bool | None = None,
    ) -> TransportResult:
        if diagnostics is not None and bool(diagnostics) != self.telemetry.diagnostics_enabled:
            self.telemetry = _Telemetry(
                execution_arm=self.arm, diagnostics_enabled=bool(diagnostics)
            )
        if self.telemetry.diagnostics_enabled:
            self.telemetry.entry_ns = time.monotonic_ns()
        if not isinstance(materialize_output, bool):
            raise ValueError("materialize_output must be a bool")
        if output_size is not None and destination_size is not None and output_size != destination_size:
            raise ValueError("output_size and destination_size disagree")
        exact_destination_size = destination_size if destination_size is not None else output_size
        source_ranges = self._record_ranges(ranges, exact_destination_size)
        planned_ranges = source_ranges
        self.telemetry.producer_ids = tuple(
            range(STATIC_E27_PRODUCERS if self.arm == STATIC_E27_ARM else self.config.producer_workers)
        )
        if self.arm == STATIC_E27_ARM:
            self._static_regions, self._static_work = self._static_e27_work(
                source_ranges, self.config.block_bytes
            )
            planned_ranges = [item for producer_items in self._static_work for item in producer_items]
            self.telemetry.static_regions = [
                {
                    "producer_id": producer_id,
                    "start": source_ranges[0].source_offset + start if source_ranges else start,
                    "end": source_ranges[0].source_offset + end if source_ranges else end,
                    "relative_start": start,
                    "relative_end": end,
                }
                for producer_id, (start, end) in enumerate(self._static_regions)
            ]
        if parse_count < 0:
            raise ValueError("parse_count must be non-negative")
        self.telemetry.parse_count = parse_count
        self.telemetry.owner, self.telemetry.adoption = owner, adoption
        self.telemetry.owner_count, self.telemetry.adoption_result = owner_count, adoption_result
        self._owner_lifetime = owner
        source_qd = STATIC_E27_PRODUCERS if self.arm == STATIC_E27_ARM else min(
            self.config.queue_depth, self.config.producer_workers
        )
        self.telemetry.configure_source_qd(source_qd)
        if self.telemetry.diagnostics_enabled:
            self.telemetry.source_start_ns = time.monotonic_ns()
        read_source, direct_readinto = self._open_source(reader)
        if self.arm == STATIC_E27_ARM and not direct_readinto:
            close_errors = self._close_source()
            error = ReconciliationError("static E27 arm requires direct readinto source")
            if close_errors:
                raise TransportFailure(error, secondary_errors=close_errors) from error
            raise error
        read_fn: Callable[[int, int], bytes] | None = None
        if not direct_readinto:
            read_fn = cast(
                Callable[[int, int], bytes],
                read_source if callable(read_source) else getattr(read_source, "read"),
            )
        self.telemetry.source_read_mode = "direct_readinto" if direct_readinto else "legacy_bytes"
        self.telemetry.source_open_count += 1
        try:
            self.start(destination_size=exact_destination_size)
        except BaseException as exc:
            close_errors = self._close_source()
            if close_errors:
                failure = TransportFailure(exc, secondary_errors=close_errors)
                self._retain_failure_lifetime(failure)
                raise failure from exc
            raise
        errors: list[BaseException] = []
        producer_cleanup_errors: list[BaseException] = []
        errors_lock = threading.Lock()
        index = 0
        index_lock = threading.Lock()

        def note_worker_error(exc: BaseException) -> None:
            with errors_lock:
                errors.append(exc)
            self._request_abort()

        def worker(producer_id: int) -> None:
            nonlocal index
            with self._active_lock:
                self._active_producers += 1
            try:
                static_items = (
                    self._static_work[producer_id]
                    if self.arm == STATIC_E27_ARM and self._static_work is not None
                    else None
                )
                local_index = 0
                while not self._abort_requested:
                    if static_items is not None:
                        if local_index >= len(static_items):
                            return
                        item = static_items[local_index]
                        local_index += 1
                    else:
                        with index_lock:
                            if index >= len(source_ranges):
                                return
                            item = source_ranges[index]
                            index += 1
                    lease: StageLease | None = None
                    try:
                        lease = self.acquire(declared_range=item, producer_id=producer_id)
                        if self.telemetry.diagnostics_enabled:
                            self.telemetry.source_read_begin()
                        try:
                            if direct_readinto:
                                self._read_exact_into(
                                    lease, cast(PinnedRangeReader, read_source), item,
                                    self.config.read_retries, self.telemetry, producer_id,
                                )
                            else:
                                assert read_fn is not None
                                data = self._read_exact(read_fn, item, self.config.read_retries, self.telemetry)
                                lease.fill(data)
                        finally:
                            if self.telemetry.diagnostics_enabled:
                                self.telemetry.source_read_end()
                        self.publish(
                            lease,
                            ReadyRecord(
                                item.source_offset,
                                item.target_offset,
                                item.length,
                                item.record_id,
                                producer_id,
                            ),
                        )
                        self.telemetry.note_record(
                            ReadyRecord(
                                item.source_offset,
                                item.target_offset,
                                item.length,
                                item.record_id,
                                producer_id,
                            )
                        )
                        lease = None  # dispatcher now owns the lease
                    finally:
                        if lease is not None:
                            try:
                                self.pool.return_lease(lease)
                            except BaseException as exc:
                                # Abort cleanup may already have detached and
                                # poisoned this exact lease.  That expected
                                # handoff must not become a stale-generation
                                # secondary diagnostic (a real producer
                                # cleanup error is still retained).
                                if not self.pool._consume_expected_abort_cleanup(lease, exc):
                                    with errors_lock:
                                        producer_cleanup_errors.append(exc)
            except BaseException as exc:
                note_worker_error(exc)
            finally:
                with self._active_lock:
                    self._active_producers -= 1

        producer_count = STATIC_E27_PRODUCERS if self.arm == STATIC_E27_ARM else self.config.producer_workers
        threads = [
            threading.Thread(
                target=worker,
                args=(producer_id,),
                name=f"golden-qd-source-{producer_id}",
                daemon=True,
            )
            for producer_id in range(producer_count)
        ]
        for thread in threads:
            thread.start()
        # Successful producer completion is ordinary work, not cleanup.  Do
        # not spend the abort budget once per worker: slow source reads and
        # backpressure are allowed to finish normally.  Once an abort is
        # observed, all remaining joins share one absolute deadline with the
        # dispatcher drain below.
        abort_deadline = self._abort_deadline
        while True:
            live_workers = [thread for thread in threads if thread.is_alive()]
            if not live_workers:
                break
            if self._abort_requested:
                if abort_deadline is None:
                    abort_deadline = self._begin_abort()
                remaining = abort_deadline - time.monotonic()
                if remaining <= 0:
                    break
                live_workers[0].join(min(0.01, remaining))
            else:
                # A short join lets another producer report an abort while a
                # different producer is blocked on source I/O or backpressure.
                live_workers[0].join(0.01)
        if self._abort_requested and abort_deadline is None:
            abort_deadline = self._begin_abort()
        live_workers = [thread for thread in threads if thread.is_alive()]
        if live_workers:
            errors.append(TransportError("source worker did not stop within bounded cleanup"))
            self._request_abort()
            if self.dispatcher is not None:
                with self.dispatcher._lease_cleanup_lock:
                    self.pool._poison(None, "source worker cleanup was uncertain", all_active=True, expected_abort=True)
            else:
                self.pool._poison(None, "source worker cleanup was uncertain", all_active=True, expected_abort=True)
            if abort_deadline is None:
                abort_deadline = self._begin_abort()
            while live_workers:
                remaining = abort_deadline - time.monotonic()
                if remaining <= 0:
                    break
                live_workers[0].join(min(0.01, remaining))
                live_workers = [thread for thread in threads if thread.is_alive()]
        if self.telemetry.diagnostics_enabled:
            self.telemetry.source_end_ns = time.monotonic_ns()
            self.telemetry.final_drain_start_ns = time.monotonic_ns()
        if abort_deadline is None:
            # No abort occurred: wait for the dispatcher to quiesce without
            # applying the cleanup timeout to normal completion.
            self.drain(None, bounded=False)
        else:
            self.drain(deadline=abort_deadline)
        if self.telemetry.diagnostics_enabled:
            self.telemetry.final_drain_end_ns = time.monotonic_ns()
        # Never close a source behind a producer that did not retire; the
        # open handle is part of the uncertainty reported to snapshot hygiene.
        close_errors = [] if live_workers else self._close_source()

        dispatcher_error = self.dispatcher.dispatcher_error if self.dispatcher else None
        cleanup_errors = (list(self.dispatcher.cleanup_errors) if self.dispatcher else []) + close_errors
        with errors_lock:
            worker_errors = list(errors)
            worker_cleanup_errors = list(producer_cleanup_errors)
        source_errors = [error for error in worker_errors if not isinstance(error, (CancellationError, PoolPoisonedError))]
        primary = source_errors[0] if source_errors else dispatcher_error
        if primary is None and self._cancel_requested:
            primary = CancellationError("Golden QD transport was explicitly cancelled")
        if primary is None and worker_errors:
            primary = worker_errors[0]
        if primary is None and close_errors:
            # A source that could not be closed is not a successful, reusable
            # transport even when all bytes and completion events reconciled.
            primary = close_errors[0]
        self.telemetry.poisoned = self.pool.poisoned
        self.telemetry.poison_reason = getattr(self.pool, "_poison_reason", None)
        completed = self.dispatcher.completed_records if self.dispatcher else ()
        expected = {(r.source_offset, r.target_offset, r.length, r.record_id) for r in planned_ranges}
        actual = {(r.source_offset, r.destination_offset, r.nbytes, r.record_id) for r in completed}
        self.telemetry.coverage_ok = actual == expected and len(completed) == len(planned_ranges)
        self.telemetry.h2d_reconciled = (
            self.telemetry.h2d_submitted_bytes == self.telemetry.h2d_completed_bytes
        )
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
        if len(completed) != len(actual):
            secondary.append(ReconciliationError("completed records were duplicated"))
        if self.telemetry.h2d_submitted_bytes != self.telemetry.h2d_completed_bytes:
            secondary.append(ReconciliationError("submitted and completed H2D byte counts differ"))
        if primary is not None:
            failure = TransportFailure(
                primary,
                secondary_errors=secondary,
                telemetry=telemetry,
                cancelled=self._cancel_requested,
            )
            self._retain_failure_lifetime(failure)
            raise failure from primary
        if actual != expected or len(completed) != len(planned_ranges):
            failure = TransportFailure(
                ReconciliationError("source record coverage is missing or duplicated"),
                secondary_errors=secondary,
                telemetry=telemetry,
            )
            self._retain_failure_lifetime(failure)
            raise failure from None
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
        with self._reader_lock:
            open_readers = len(self._reader_handles)
        dispatcher_live = self.dispatcher is not None and self.dispatcher._thread is not None and self.dispatcher._thread.is_alive()
        if self.dispatcher is None:
            queue_live = handoff_live = events_live = False
        else:
            with self.dispatcher._queue_condition:
                queue_live = bool(self.dispatcher._queue)
                handoff_live = bool(self.dispatcher._handoff or self.dispatcher._uncertain_handoffs)
                events_live = bool(self.dispatcher._in_flight or self.dispatcher._late_submissions)
        slot_live = any(state in (SlotState.FILLING, SlotState.READY, SlotState.IN_FLIGHT) for state in self.pool.states())
        if (
            self.pool.poisoned or producers or dispatcher_live or queue_live or handoff_live
            or events_live or open_readers or slot_live
        ):
            raise TransportError(
                "snapshot requires an unpoisoned pool with no live producer, dispatcher, "
                "slot, event, reader, queue, or uncertain handoff state"
            )
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


def create_transport(
    arm: str | None = None,
    *,
    config: TransportConfig | None = None,
    backend: TransportBackend | None = None,
    diagnostics: bool = True,
) -> GoldenQDTransport | LegacyTransport:
    selected = normalize_transport_arm(arm)
    return (
        LegacyTransport(config, backend)
        if selected == LEGACY_ARM
        else GoldenQDTransport(
            config, backend, arm=selected, diagnostics=diagnostics
        )
    )


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
        length = int(source.numel()) if hasattr(source, "numel") else len(source)
        end = destination_offset + length
        if end > len(self.destination):
            self.destination.extend(b"\0" * (end - len(self.destination)))
        self.destination[destination_offset:end] = source[:length]
        self.submissions.append((destination_offset, length))
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

    def readinto(self, target: Any, offset: int, producer_id: int | None = None) -> int:
        """Exercise the production range-reader contract without a payload."""
        length = len(target)
        self.calls.append((offset, length))
        if offset in self.fail_at:
            raise OSError(f"injected source read failure at {offset}")
        available = min(length, len(self.data) - offset)
        if self.short_reads and available > 1:
            available = min(available, self.short_reads)
        if available > 0:
            target[:available] = memoryview(self.data)[offset : offset + available]
        return max(0, available)


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
    "DEFAULT_QUEUE_DEPTH", "DEFAULT_STAGING_SLOTS", "DISPATCHER_ARM", "CONTROL_ARM", "STATIC_E27_ARM", "TEST_ARM",
    "STATIC_E27_PRODUCERS", "EventStatus", "FakeBackend", "FakeEvent", "FakeSource", "GoldenQDTransport", "LEGACY_ARM", "LeaseError", "LegacyTransport", "OutputViewSpec",
    "PoolPoisonedError", "QDTransport", "ReadyRecord", "ReconciliationError", "SlotState", "SourceRange",
    "StageLease", "StagingPool", "PinnedRangeReader", "TransportBackend", "TransportConfig", "TransportDispatcher", "TransportError",
    "TransportFailure", "TransportResult", "create_transport", "map_output_views", "normalize_transport_arm", "static_e27_regions", "static_segments",
    "prove_backing_survives_stage_release",
]
