"""Opt-in, fail-closed Golden QD transport.

The producer side owns only a generation-tagged lease and its fill/mark APIs.
The dispatcher is the sole owner of submission, completion events, and slot
return.  CUDA is optional: importing this module does not import torch.
"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence, cast

try:
    from .preplanned_extent_transport import (
        ExtentState,
        ExtentTransportError,
        PlannedExtent,
        PlannedRead,
        PreplannedExtentTransport,
        plan_preplanned_extents,
        validate_preplanned_extents,
    )
except ImportError:
    from comfymodal_runtime.preplanned_extent_transport import (
        ExtentState,
        ExtentTransportError,
        PlannedExtent,
        PlannedRead,
        PreplannedExtentTransport,
        plan_preplanned_extents,
        validate_preplanned_extents,
    )

try:
    from .e27_source_mechanism import (
        ActualSourceTelemetry,
        evaluate_e27_source_mechanism,
    )
except ImportError:  # The existing focused tests load this file directly.
    from comfymodal_runtime.e27_source_mechanism import (
        ActualSourceTelemetry,
        evaluate_e27_source_mechanism,
    )


TRANSPORT_ENV = "COMFYMODAL_GOLDEN_QD_TRANSPORT"
LEGACY_ARM = "legacy"
DISPATCHER_ARM = "dispatcher"
CONTROL_ARM = DISPATCHER_ARM
STATIC_E27_ARM = "static_e27"
TEST_ARM = STATIC_E27_ARM
DECOUPLED_ARM = "decoupled"
STATIC_E27_PRODUCERS = 4
DEFAULT_QUEUE_DEPTH = 4
DEFAULT_BLOCK_BYTES = 32 * 1024 * 1024
DEFAULT_STAGING_SLOTS = 8
REQUEST_ARENA_BYTES = DEFAULT_STAGING_SLOTS * DEFAULT_BLOCK_BYTES
H2D_TARGET_BYTES_BY_ROLE = {
    "clip": 64 * 1024 * 1024,
    "unet": 128 * 1024 * 1024,
    "vae": 32 * 1024 * 1024,
}


def resolve_h2d_target_bytes(role: str) -> int:
    normalized = str(role).strip().lower()
    if normalized.startswith("clip"):
        normalized = "clip"
    try:
        return H2D_TARGET_BYTES_BY_ROLE[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported H2D target role: {role!r}") from exc


@dataclass
class CompletionTicket:
    """A generation-specific completion/timing receipt for one staging slot."""

    slot_index: int
    submission_id: int
    start_event: Any
    end_event: Any
    byte_count: int
    completion: bool = False
    timing_consumed: bool = False
    # Set only for a one-shot transfer, so the completion-event lifecycle can be
    # reconciled: every H2D owns its own generation of production events.
    production_event_generation: int | None = None
    production_events_retired: bool = False


class GoldenTransferResources:
    """Request-lifetime CPU staging and CUDA copy resources.

    This object deliberately does not retain model storage, modules, patchers,
    readers, or checkpoint state.  Every transport creates its own lease/pool
    metadata while borrowing these stable views.
    """

    slot_count = DEFAULT_STAGING_SLOTS
    slot_bytes = DEFAULT_BLOCK_BYTES
    arena_bytes = REQUEST_ARENA_BYTES

    def __init__(
        self,
        arena: Any,
        views: Sequence[Any],
        stream: Any,
        events: Sequence[tuple[Any, Any]],
        span_events: tuple[Any, Any],
        *,
        slot_count: int = DEFAULT_STAGING_SLOTS,
        slot_bytes: int = DEFAULT_BLOCK_BYTES,
        shared_arena: bool = False,
    ) -> None:
        if len(events) != slot_count:
            raise ValueError("request transport resources require one event pair per slot")
        if slot_count < 1 or slot_bytes < 1:
            raise ValueError("request transport resource dimensions must be positive")
        if shared_arena:
            # Borrowed mode: the caller owns the registered staging storage
            # (the C0 shared arena).  Only the dedicated H2D stream and the
            # persistent per-slot event pairs are allocated here; there is no
            # pinned host arena, and no staging views may be attached.
            if views:
                raise ValueError("shared-arena transport resources must not carry staging views")
        elif len(views) != slot_count:
            raise ValueError("request transport resources require matching slots and event pairs")
        self.slot_count = int(slot_count)
        self.slot_bytes = int(slot_bytes)
        self.arena_bytes = self.slot_count * self.slot_bytes
        self.shared_arena = bool(shared_arena)
        self.arena = arena
        self.views = tuple(views)
        self.slot_indices = tuple(range(self.slot_count))
        self.h2d_stream = stream
        self.events = tuple(events)
        self.span_events = span_events
        self._event_object_count = self.slot_count * 2 + len(self.span_events)
        # Borrowed shared-arena resources perform no pinned host allocation.
        self.physical_pinned_alloc_count = 0 if shared_arena else 1
        self.transport_physical_pinned_alloc_count = 0
        self.created = True
        self.closed = False
        self._poisoned = False
        self._poison_observed = False
        self._active_tickets: dict[int, CompletionTicket] = {}
        self._active_transports = 0
        self.transport_use_count = 0
        self._next_submission_id = 0
        # Completion-event lifetime.  ``reuse`` (default) keeps the persistent
        # per-slot event pair.  ``one_shot_events`` allocates ONE fresh
        # production event pair per H2D ticket and retires it when the slot is
        # returned, so no completion-event object is ever reused between
        # transfers.  The optional ``event_factory`` lets tests inject a fake.
        self.completion_event_lifetime = "reuse"
        self.production_event_allocations = 0
        self.retired_event_allocations = 0
        self.event_factory: Any = None
        self._span_started = False
        self._span_finished = False
        self.gpu_copy_active_sum_ms = 0.0
        self._gpu_copy_timing_samples = 0
        self.gpu_copy_count = 0
        self.gpu_copy_bytes = 0
        self.request_cumulative_gpu_copy_count = 0
        self.request_cumulative_gpu_copy_bytes = 0
        self.gpu_copy_stream_span_ms: float | None = None
        self.gpu_copy_active_union_ms = 0.0
        self.gpu_copy_idle_inside_stream_span_ms = 0.0
        self.event_rerecord_count = 0
        self.h2d_submit_count = 0
        self.h2d_completion_count = 0
        self.request_cumulative_h2d_submit_count = 0
        self.request_cumulative_h2d_completion_count = 0

    def reset_operation_metrics(self) -> None:
        self._span_started = False
        self._span_finished = False
        self.gpu_copy_active_sum_ms = 0.0
        self._gpu_copy_timing_samples = 0
        self.gpu_copy_count = 0
        self.gpu_copy_bytes = 0
        self.gpu_copy_stream_span_ms = None
        self.gpu_copy_active_union_ms = 0.0
        self.gpu_copy_idle_inside_stream_span_ms = 0.0
        self.h2d_submit_count = 0
        self.h2d_completion_count = 0

    @classmethod
    def create(
        cls,
        device: str | None = None,
        *,
        slot_count: int = DEFAULT_STAGING_SLOTS,
        slot_bytes: int = DEFAULT_BLOCK_BYTES,
    ) -> "GoldenTransferResources":
        try:
            import torch
        except ImportError as exc:
            raise TransportError("request transport resources require torch") from exc
        if not torch.cuda.is_available():
            raise TransportError("CUDA is unavailable for request transport resources")
        dev = device or f"cuda:{torch.cuda.current_device()}"
        # Exactly one physical pinned allocation.  All slot objects below are
        # stable views into this allocation, never additional allocations.
        arena_bytes = int(slot_count) * int(slot_bytes)
        arena = torch.empty(arena_bytes, dtype=torch.uint8, pin_memory=True)
        views = tuple(
            arena[index * slot_bytes : (index + 1) * slot_bytes]
            for index in range(slot_count)
        )
        stream = torch.cuda.Stream(device=dev)
        events = tuple(
            (
                torch.cuda.Event(enable_timing=True),
                torch.cuda.Event(enable_timing=True),
            )
            for _ in range(slot_count)
        )
        span_events = (
            torch.cuda.Event(enable_timing=True),
            torch.cuda.Event(enable_timing=True),
        )
        return cls(
            arena, views, stream, events, span_events,
            slot_count=slot_count,
            slot_bytes=slot_bytes,
        )

    @classmethod
    def create_shared(
        cls,
        stream: Any = None,
        *,
        slot_count: int,
        slot_bytes: int,
        device: str | None = None,
    ) -> "GoldenTransferResources":
        """Borrow a caller-owned registered shared arena as staging storage.

        Golden I/O V2 C0 uses exactly one shared, CUDA-registered arena for
        every payload byte.  This factory therefore allocates only the
        persistent copy resources: one dedicated H2D stream and one reusable
        event pair per slot.  It performs **no** pinned host allocation and
        exposes **no** staging views; the caller's ``StagingPool`` over the
        registered arena is the only staging storage.
        """
        try:
            import torch
        except ImportError as exc:
            raise TransportError("shared-arena transport resources require torch") from exc
        if not torch.cuda.is_available():
            raise TransportError("CUDA is unavailable for shared-arena transport resources")
        dev = device or f"cuda:{torch.cuda.current_device()}"
        h2d_stream = stream if stream is not None else torch.cuda.Stream(device=dev)
        events = tuple(
            (
                torch.cuda.Event(enable_timing=True),
                torch.cuda.Event(enable_timing=True),
            )
            for _ in range(int(slot_count))
        )
        span_events = (
            torch.cuda.Event(enable_timing=True),
            torch.cuda.Event(enable_timing=True),
        )
        return cls(
            None, (), h2d_stream, events, span_events,
            slot_count=int(slot_count),
            slot_bytes=int(slot_bytes),
            shared_arena=True,
        )

    @property
    def event_object_count(self) -> int:
        return self._event_object_count

    @property
    def active_tickets(self) -> int:
        return len(self._active_tickets)

    def new_pool(self, capacity_class: str) -> "StagingPool":
        if self.closed:
            raise TransportError("request transport resources are closed")
        if self._poisoned:
            raise PoolPoisonedError("request transport resources are poisoned")
        if self.shared_arena:
            # Borrowed resources own no staging views; the caller must provide
            # its own pool over the registered shared arena.
            raise TransportError("shared-arena transport resources own no staging pool")
        return StagingPool(
            self.slot_count, self.slot_bytes, capacity_class,
            buffers=self.views,
            backing_buffer=self.arena,
        )

    def transport_enter(self) -> None:
        if self.closed:
            raise TransportError("request transport resources are closed")
        if self._poisoned:
            raise PoolPoisonedError("request transport resources are poisoned")
        if self._active_transports == 0:
            self.reset_operation_metrics()
        self._active_transports += 1
        self.transport_use_count += 1
        self.transport_physical_pinned_alloc_count = 1 if self.transport_use_count == 1 else 0

    def transport_exit(self, *, poisoned: bool = False) -> None:
        self._active_transports = max(0, self._active_transports - 1)
        if poisoned:
            self._poisoned = True

    def acknowledge_poison(self) -> None:
        """Record that a fail-closed transport poison reached its caller."""
        self._poison_observed = True

    def begin_span(self) -> None:
        if self._span_started:
            return
        record = getattr(self.span_events[0], "record", None)
        if not callable(record):
            raise TransportError("request H2D span event is not recordable")
        record(self.h2d_stream)
        self._span_started = True

    def finish_span(self) -> None:
        if not self._span_started or self._span_finished:
            return
        record = getattr(self.span_events[1], "record", None)
        if not callable(record):
            raise TransportError("request H2D span event is not recordable")
        record(self.h2d_stream)
        self._span_finished = True
        elapsed = _event_elapsed_ms(self.span_events[0], self.span_events[1])
        if elapsed is not None:
            self.gpu_copy_stream_span_ms = elapsed
            self.gpu_copy_active_union_ms = self.gpu_copy_active_sum_ms
            self.gpu_copy_idle_inside_stream_span_ms = max(
                0.0, elapsed - self.gpu_copy_active_union_ms
            )

    def set_completion_event_lifetime(self, lifetime: str) -> str:
        """Select the per-transfer completion-event lifetime without changing geometry."""
        selected = str(lifetime).strip().lower() or "reuse"
        if selected not in {"reuse", "one_shot_events"}:
            raise TransportError(
                "completion event lifetime must be reuse or one_shot_events"
            )
        self.completion_event_lifetime = selected
        return selected

    def _allocate_production_events(self) -> tuple[Any, Any]:
        """Allocate ONE fresh production event pair for this transfer.

        Injected factories are honoured so tests can observe allocation and
        retirement without CUDA.  Production uses timing-enabled CUDA events.
        """
        if self.event_factory is not None:
            return self.event_factory(), self.event_factory()
        try:
            import torch
        except ImportError as exc:  # pragma: no cover - import error path
            raise TransportError("one-shot production events require torch") from exc
        return (
            torch.cuda.Event(enable_timing=True),
            torch.cuda.Event(enable_timing=True),
        )

    def begin_ticket(self, slot_index: int, byte_count: int) -> CompletionTicket:
        if slot_index in self._active_tickets:
            raise TransportError("staging slot event is still in use")
        if not 0 <= int(slot_index) < self.slot_count:
            raise TransportError("invalid request staging slot")
        self._next_submission_id += 1
        if self.completion_event_lifetime == "one_shot_events":
            # One fresh completion event pair for THIS H2D; never reused.
            start, end = self._allocate_production_events()
            production_generation = self._next_submission_id
            self.production_event_allocations += 2
        else:
            start, end = self.events[int(slot_index)]
            production_generation = None
        ticket = CompletionTicket(
            int(slot_index), self._next_submission_id, start, end, int(byte_count),
            production_event_generation=production_generation,
        )
        self._active_tickets[int(slot_index)] = ticket
        if production_generation is None and self._next_submission_id > self.slot_count:
            self.event_rerecord_count += 2
        return ticket

    def submit_ticket(self, ticket: CompletionTicket) -> None:
        record_start = getattr(ticket.start_event, "record", None)
        record_end = getattr(ticket.end_event, "record", None)
        if not callable(record_start) or not callable(record_end):
            raise TransportError("request H2D completion ticket is not recordable")
        record_start(self.h2d_stream)
        self.h2d_submit_count += 1
        self.request_cumulative_h2d_submit_count += 1
        record_end(self.h2d_stream)

    def harvest_ticket(self, ticket: CompletionTicket) -> None:
        if self._active_tickets.get(ticket.slot_index) is not ticket:
            raise TransportError("completion ticket is stale")
        if not ticket.completion:
            ticket.completion = True
            self.h2d_completion_count += 1
            self.request_cumulative_h2d_completion_count += 1
        if not ticket.timing_consumed:
            elapsed = _event_elapsed_ms(ticket.start_event, ticket.end_event)
            if elapsed is not None:
                self.gpu_copy_active_sum_ms += elapsed
                self._gpu_copy_timing_samples += 1
            ticket.timing_consumed = True
            self.gpu_copy_count += 1
            self.gpu_copy_bytes += ticket.byte_count
            self.request_cumulative_gpu_copy_count += 1
            self.request_cumulative_gpu_copy_bytes += ticket.byte_count

    def return_ticket(self, ticket: CompletionTicket) -> None:
        if not ticket.completion or not ticket.timing_consumed:
            raise TransportError("event pair returned before completion and timing harvest")
        if self._active_tickets.get(ticket.slot_index) is not ticket:
            raise TransportError("completion ticket is stale")
        self._active_tickets.pop(ticket.slot_index, None)
        if ticket.production_event_generation is not None and not ticket.production_events_retired:
            # Retire THIS transfer's one-shot event objects.  They are never
            # reused by a later H2D; dropping the references lets them be freed.
            ticket.production_events_retired = True
            self.retired_event_allocations += 2
            ticket.start_event = None
            ticket.end_event = None

    def telemetry(self) -> dict[str, Any]:
        timing_available = (
            self.gpu_copy_count == 0
            or self._gpu_copy_timing_samples == self.gpu_copy_count
        )
        active_sum = self.gpu_copy_active_sum_ms if timing_available else None
        union_available = bool(self._span_finished and timing_available)
        active_union = self.gpu_copy_active_sum_ms if union_available else None
        idle_inside_span = (
            self.gpu_copy_idle_inside_stream_span_ms
            if union_available else None
        )
        return {
            "arena_bytes": self.arena_bytes,
            "slot_count": self.slot_count,
            "slot_bytes": self.slot_bytes,
            "shared_arena": self.shared_arena,
            "shared_arena_staging": self.shared_arena,
            "request_physical_pinned_alloc_count": self.physical_pinned_alloc_count,
            "pinned_arena_physical_allocation_count": self.physical_pinned_alloc_count,
            "pinned_arena_physical_allocation_bytes": (
                0 if self.shared_arena else self.arena_bytes
            ),
            "logical_slot_count": self.slot_count,
            "logical_slot_bytes": self.slot_bytes,
            "transport_physical_pinned_alloc_count": (
                0 if self.shared_arena else (1 if self.transport_use_count == 1 else 0)
            ),
            "created_vs_reused": "CREATED" if self.transport_use_count <= 1 else "REUSED",
            "dedicated_h2d_stream_count": 1,
            "cuda_h2d_stream_object_count": 1,
            "event_object_count": self.event_object_count,
            "cuda_start_event_object_count": self.slot_count,
            "cuda_end_event_object_count": self.slot_count,
            "event_rerecord_count": self.event_rerecord_count,
            "cuda_event_rerecord_count": self.event_rerecord_count,
            "fresh_cuda_event_per_copy_count": int(
                self.production_event_allocations // 2
            ),
            "completion_event_lifetime": self.completion_event_lifetime,
            "production_event_allocations": int(self.production_event_allocations),
            "retired_event_allocations": int(self.retired_event_allocations),
            "h2d_submit_count": self.h2d_submit_count,
            "h2d_completion_count": self.h2d_completion_count,
            "GPU_COPY_ACTIVE_SUM_MS": active_sum,
            "GPU_COPY_STREAM_SPAN_MS": self.gpu_copy_stream_span_ms,
            "GPU_COPY_ACTIVE_UNION_MS": active_union,
            "GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS": idle_inside_span,
            "GPU_COPY_TIMING_AVAILABLE": timing_available,
            "GPU_COPY_ACTIVE_UNION_PROVEN_SINGLE_STREAM_NON_OVERLAP": True,
            "GPU_COPY_ACTIVE_UNION_PROOF": (
                "all H2D copies are ordered on one dedicated stream; therefore "
                "their measured active-time union equals their measured active-time sum"
            ),
            "GPU_COPY_COUNT": self.gpu_copy_count,
            "GPU_COPY_BYTES": self.gpu_copy_bytes,
            "REQUEST_CUMULATIVE_H2D_SUBMIT_COUNT": self.request_cumulative_h2d_submit_count,
            "REQUEST_CUMULATIVE_H2D_COMPLETION_COUNT": self.request_cumulative_h2d_completion_count,
            "REQUEST_CUMULATIVE_GPU_COPY_COUNT": self.request_cumulative_gpu_copy_count,
            "REQUEST_CUMULATIVE_GPU_COPY_BYTES": self.request_cumulative_gpu_copy_bytes,
        }

    def close(self) -> None:
        if self.closed:
            return
        if self._active_tickets or self._active_transports:
            raise TransportError("request transport resources are not quiescent")
        if getattr(self, "_poisoned", False) and not self._poison_observed:
            raise TransportError("request transport resources have unsurfaced poison")
        self.arena = None
        self.views = ()
        self.events = ()
        self.span_events = ()
        self.h2d_stream = None
        self.closed = True


def _event_elapsed_ms(start_event: Any, end_event: Any) -> float | None:
    elapsed = getattr(start_event, "elapsed_time", None)
    if not callable(elapsed):
        return None
    try:
        value = float(elapsed(end_event))
    except Exception:
        return None
    return value if value >= 0 else None


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
    if selected not in (LEGACY_ARM, DISPATCHER_ARM, STATIC_E27_ARM, DECOUPLED_ARM):
        raise ValueError(
            f"unknown Golden QD transport arm {selected!r}; "
            "expected legacy, dispatcher, static_e27, or decoupled"
        )
    return selected


def static_e27_regions(total: int, producer_count: int = STATIC_E27_PRODUCERS) -> tuple[tuple[int, int], ...]:
    """Return fixed E27 regions as relative ``[start, end)`` byte ranges.

    Regions are planned once per transport. Empty trailing regions are kept
    so the static arm always has the four explicit producer identities used
    by the E27 probe, including for very short test inputs.
    """
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ValueError("total must be a non-negative integer")
    if isinstance(producer_count, bool) or not isinstance(producer_count, int) or producer_count < 1:
        raise ValueError("static E27 transport requires at least one producer")
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
    h2d_target_bytes: int | None = None
    aggregation_enabled: bool = True
    source_qd: int | None = None
    source_block_bytes: int | None = None
    h2d_copy_bytes: int | None = None
    h2d_inflight_depth: int | None = None
    source_capacity: int | None = None

    def __post_init__(self) -> None:
        independent = any(
            value is not None
            for value in (
                self.source_qd,
                self.source_block_bytes,
                self.h2d_copy_bytes,
                self.h2d_inflight_depth,
                self.source_capacity,
            )
        )
        source_qd = self.queue_depth if self.source_qd is None else self.source_qd
        source_block_bytes = self.block_bytes if self.source_block_bytes is None else self.source_block_bytes
        h2d_copy_bytes = (
            self.h2d_target_bytes if self.h2d_copy_bytes is None and self.h2d_target_bytes is not None
            else self.block_bytes if self.h2d_copy_bytes is None else self.h2d_copy_bytes
        )
        h2d_inflight_depth = self.queue_depth if self.h2d_inflight_depth is None else self.h2d_inflight_depth
        source_capacity = self.staging_slots if self.source_capacity is None else self.source_capacity
        object.__setattr__(self, "source_qd", source_qd)
        object.__setattr__(self, "source_block_bytes", source_block_bytes)
        object.__setattr__(self, "h2d_copy_bytes", h2d_copy_bytes)
        object.__setattr__(self, "h2d_inflight_depth", h2d_inflight_depth)
        object.__setattr__(self, "source_capacity", source_capacity)
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
            "source_qd": source_qd,
            "source_block_bytes": source_block_bytes,
            "h2d_copy_bytes": h2d_copy_bytes,
            "h2d_inflight_depth": h2d_inflight_depth,
            "source_capacity": source_capacity,
        }
        for name, value in values.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.cleanup_timeout, (int, float)) or self.cleanup_timeout <= 0:
            raise ValueError("cleanup_timeout must be positive")
        if not independent and self.queue_depth > self.staging_slots:
            raise ValueError("queue_depth cannot exceed staging_slots")
        if not isinstance(self.capacity_class, str) or not self.capacity_class:
            raise ValueError("capacity_class must be a non-empty string")
        if not isinstance(self.aggregation_enabled, bool):
            raise ValueError("aggregation_enabled must be a bool")
        if self.h2d_target_bytes is not None and (
            not isinstance(self.h2d_target_bytes, int)
            or isinstance(self.h2d_target_bytes, bool)
            or self.h2d_target_bytes < 1
        ):
            raise ValueError("h2d_target_bytes must be positive")


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
        preferred_slot_index: int | None = None,
        preferred_slot_honored: bool | None = None,
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
        self.preferred_slot_index = preferred_slot_index
        self.preferred_slot_honored = preferred_slot_honored

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

    @property
    def declared_range(self) -> SourceRange | None:
        """The canonical source/destination extent declared for this lease.

        C0 child-fill relies on this to carry the absolute destination offset
        and source identity without exposing the raw staging buffer.
        """
        return self._declared_range

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


def _buffer_is_backing_range(buffer: Any, backing: Any, offset: int, length: int) -> bool:
    """Prove that one slot is the expected byte range of the shared arena."""
    if backing is None:
        return False
    try:
        import torch
        if isinstance(buffer, torch.Tensor) and isinstance(backing, torch.Tensor):
            return bool(
                buffer.dtype == getattr(torch, "uint8")
                and backing.dtype == getattr(torch, "uint8")
                and buffer.dim() == 1
                and backing.dim() == 1
                and buffer.numel() == length
                and backing.numel() >= offset + length
                and buffer.data_ptr() == backing.data_ptr() + offset
            )
    except (ImportError, AttributeError, TypeError, ValueError, RuntimeError):
        pass
    try:
        view = memoryview(buffer)
        arena = memoryview(backing)
        if view.nbytes != length or arena.nbytes < offset + length:
            return False
        if view.obj is not arena.obj:
            return False
        # A writable buffer lets us prove the slice offset as well as the
        # common underlying object.  Read-only buffers cannot be safely used
        # as staging storage, so rejecting them is the honest fallback.
        address = ctypes.addressof(ctypes.c_char.from_buffer(view))
        arena_address = ctypes.addressof(ctypes.c_char.from_buffer(arena))
        return address == arena_address + offset
    except (TypeError, ValueError, BufferError):
        return False


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
        backing_buffer: Any = None,
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
        self.backing_buffer = backing_buffer
        # Golden I/O Process V2: when set to a CPU uint8 tensor over the
        # CUDA-registered shared backing, the dispatcher H2Ds directly from
        # ``backing[destination_offset:...]`` instead of from a filled slot.
        # The slots remain lifecycle/ticket tokens only; no payload is copied.
        self.v2_source_backing: Any = None
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
        preferred_slot_index: int | None = None,
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
        if preferred_slot_index is not None and (
            not isinstance(preferred_slot_index, int)
            or isinstance(preferred_slot_index, bool)
            or not 0 <= preferred_slot_index < len(self._slots)
        ):
            raise LeaseError("preferred slot index is invalid")
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._available:
            while True:
                if self._poisoned:
                    raise PoolPoisonedError(self._poison_reason or "staging pool is poisoned")
                if self._cancelled:
                    raise CancellationError("staging pool acquisition was cancelled")
                candidates = self._slots
                if preferred_slot_index is not None:
                    preferred = self._slots[preferred_slot_index]
                    candidates = [preferred] + [slot for slot in self._slots if slot is not preferred]
                for slot in candidates:
                    if slot.state == SlotState.FREE:
                        slot.generation += 1
                        slot.state = SlotState.FILLING
                        lease = StageLease(
                            self, slot, slot.generation, declared_range, producer_id,
                            preferred_slot_index,
                            preferred_slot_index is None or slot.index == preferred_slot_index,
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

    def _v2_dispatch_source(self, record: ReadyRecord, nbytes: int) -> Any:
        """Return the registered-backing slice for a V2 record, or None.

        The slice is indexed by payload offset (``destination_offset``), which is
        exactly where the CUDA-sterile child wrote the model bytes.  Returning a
        zero-copy view keeps the canonical H2D destination/event/ticket path and
        removes the shared->pinned staging copy entirely.
        """
        backing = self.v2_source_backing
        if backing is None:
            return None
        start = int(record.destination_offset)
        end = start + int(nbytes)
        if start < 0 or end > len(backing):
            raise ReconciliationError("V2 backing slice is out of bounds")
        return backing[start:end]

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

    def _buffer_for_dispatch_group(self, leases: Sequence[StageLease], nbytes: int) -> Any:
        if not leases:
            raise LeaseError("H2D group requires at least one lease")
        with self._meta:
            slots = [self._validate_locked(lease) for lease in leases]
            if any(slot.state != SlotState.IN_FLIGHT or not lease._producer_retired for slot, lease in zip(slots, leases)):
                raise LeaseError("dispatcher may access only retired in-flight leases")
            indices = [slot.index for slot in slots]
            if indices != list(range(indices[0], indices[0] + len(indices))):
                raise LeaseError("H2D group slots are not physically consecutive")
            if self.backing_buffer is None:
                raise LeaseError("H2D group has no proven contiguous backing storage")
            start = indices[0] * self.block_bytes
            try:
                import torch
                if (
                    isinstance(self.backing_buffer, torch.Tensor)
                    and self.backing_buffer.dtype == getattr(torch, "uint8")
                    and self.backing_buffer.dim() == 1
                ):
                    return self.backing_buffer[start : start + nbytes]
            except (ImportError, TypeError, ValueError, RuntimeError):
                pass
            return _buffer_slice(self.backing_buffer, nbytes, start)

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
    first_h2d_submit_ns: int | None = None
    final_h2d_submit_ns: int | None = None
    first_h2d_completion_observed_ns: int | None = None
    final_h2d_completion_observed_ns: int | None = None
    h2d_submission_sizes: list[int] | None = None
    aggregated_submission_count: int = 0
    non_aggregated_submission_count: int = 0
    tail_submission_count: int = 0
    aggregation_fallback_count: int = 0
    aggregation_fallback_reasons: dict[str, int] | None = None
    aggregation_enabled: bool | None = None
    aggregation_wait_count: int = 0
    aggregation_scheduler_enter_count: int = 0
    h2d_target_bytes: int | None = None
    source_block_count: int = 0
    source_block_bytes: int = DEFAULT_BLOCK_BYTES
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
    affinity_breaks: int = 0
    poisoned: bool = False
    poison_reason: str | None = None
    coverage_ok: bool | None = None
    h2d_reconciled: bool | None = None
    late_submission_count: int | None = None
    late_submission_resolved_count: int | None = None
    late_submission_unresolved_count: int | None = None
    event_cancel_count: int | None = None
    completion_classification: str = "normal"
    actual_source: ActualSourceTelemetry | None = None
    gpu_copy_active_sum_ms: float = 0.0
    gpu_copy_stream_span_ms: float | None = None
    gpu_copy_active_union_ms: float = 0.0
    gpu_copy_idle_inside_stream_span_ms: float = 0.0
    gpu_copy_count: int = 0
    gpu_copy_bytes: int = 0
    event_object_count: int | None = None
    event_rerecord_count: int | None = None
    request_physical_pinned_alloc_count: int | None = None
    transport_physical_pinned_alloc_count: int | None = None
    transport_resources: Mapping[str, Any] | None = None
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
            self.h2d_submission_sizes = []
            self.aggregation_fallback_reasons = {}
            self.qd_samples = []
            self.source_qd_depth_samples = []
            self.source_qd_timeline = []
            self.producer_destination_offsets = {}
            self.producer_destination_offset_monotonic = True
        else:
            # Destination order is an optional observation, not a correctness
            # counter. Diagnostics-off must not report that it was observed.
            self.producer_destination_offset_monotonic = None
        self.h2d_submission_sizes = []
        self.aggregation_fallback_reasons = {}
        self.source_qd_depth = 0 if self.diagnostics_enabled else None
        self.producer_read_bytes = {}
        self.producer_read_counts = {}
        self.producer_last_source_offset = {}

    def note_aggregation_fallback(self, reason: str) -> None:
        self.aggregation_fallback_count += 1
        if self.aggregation_fallback_reasons is not None:
            self.aggregation_fallback_reasons[reason] = self.aggregation_fallback_reasons.get(reason, 0) + 1

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
            submission_sizes = (
                list(self.h2d_submission_sizes)
                if self.h2d_submission_sizes is not None else None
            )
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
            actual_source_report = (
                self.actual_source.to_dict() if self.actual_source is not None else None
            )
            resource_report = dict(self.transport_resources or {})
            resource_active_sum = resource_report.get(
                "GPU_COPY_ACTIVE_SUM_MS", self.gpu_copy_active_sum_ms
            )
            resource_stream_span = resource_report.get(
                "GPU_COPY_STREAM_SPAN_MS", self.gpu_copy_stream_span_ms
            )
            resource_active_union = resource_report.get(
                "GPU_COPY_ACTIVE_UNION_MS", self.gpu_copy_active_union_ms
            )
            resource_idle_inside_span = resource_report.get(
                "GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS",
                self.gpu_copy_idle_inside_stream_span_ms,
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
                "h2d_submission_count": self.h2d_submitted_count,
                "H2D_SUBMISSION_COUNT": self.h2d_submitted_count,
                "H2D_SUBMISSIONS": self.h2d_submitted_count,
                "h2d_submission_sizes": submission_sizes,
                "h2d_submission_size_distribution": submission_sizes,
                "H2D_SUBMISSION_SIZES": submission_sizes,
                "h2d_target_bytes": self.h2d_target_bytes,
                "aggregation_enabled": self.aggregation_enabled,
                "aggregation_wait_count": self.aggregation_wait_count,
                "aggregation_scheduler_enter_count": self.aggregation_scheduler_enter_count,
                "h2d_min_submission_bytes": min(submission_sizes) if submission_sizes else None,
                "h2d_max_submission_bytes": max(submission_sizes) if submission_sizes else None,
                "h2d_mean_submission_bytes": (
                    sum(submission_sizes) / len(submission_sizes)
                    if submission_sizes else None
                ),
                "aggregated_submission_count": self.aggregated_submission_count,
                "non_aggregated_submission_count": self.non_aggregated_submission_count,
                "tail_submission_count": self.tail_submission_count,
                "aggregation_fallback_count": self.aggregation_fallback_count,
                "aggregation_fallback_reasons": dict(self.aggregation_fallback_reasons or {}),
                "source_block_count": self.source_block_count,
                "source_block_bytes": self.source_block_bytes,
                "H2D_TARGET_BYTES": self.h2d_target_bytes,
                "AGGREGATION_ENABLED": self.aggregation_enabled,
                "AGGREGATION_WAIT_COUNT": self.aggregation_wait_count,
                "AGGREGATION_SCHEDULER_ENTER_COUNT": self.aggregation_scheduler_enter_count,
                "H2D_MIN_SUBMISSION_BYTES": min(submission_sizes) if submission_sizes else None,
                "H2D_MAX_SUBMISSION_BYTES": max(submission_sizes) if submission_sizes else None,
                "H2D_MEAN_SUBMISSION_BYTES": (
                    sum(submission_sizes) / len(submission_sizes)
                    if submission_sizes else None
                ),
                "AGGREGATED_SUBMISSION_COUNT": self.aggregated_submission_count,
                "NON_AGGREGATED_SUBMISSION_COUNT": self.non_aggregated_submission_count,
                "TAIL_SUBMISSION_COUNT": self.tail_submission_count,
                "AGGREGATION_FALLBACK_COUNT": self.aggregation_fallback_count,
                "AGGREGATION_FALLBACK_REASONS": dict(self.aggregation_fallback_reasons or {}),
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
                 "first_h2d_submit_ns": self.first_h2d_submit_ns,
                 "final_h2d_submit_ns": self.final_h2d_submit_ns,
                 "first_h2d_completion_observed_ns": self.first_h2d_completion_observed_ns,
                 "final_h2d_completion_observed_ns": self.final_h2d_completion_observed_ns,
                 "source_final_byte_complete_ns": self.source_end_ns,
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
                 "affinity_breaks": self.affinity_breaks,
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
                "actual_source": actual_source_report,
                "actual_source_telemetry": actual_source_report,
                "source_syscall_events": (
                    actual_source_report.get("actual_source_events")
                    if actual_source_report is not None else None
                ),
                "source_actual_transitions": (
                    actual_source_report.get("actual_source_transitions")
                    if actual_source_report is not None else None
                ),
                "SOURCE_TOTAL_WALL_MS": (
                    actual_source_report.get("SOURCE_TOTAL_WALL_MS")
                    if actual_source_report is not None else None
                ),
                "SOURCE_SYSCALL_UNION_BUSY_MS": (
                    actual_source_report.get("SOURCE_SYSCALL_UNION_BUSY_MS")
                    if actual_source_report is not None else None
                ),
                "H2D_TOTAL_WALL_MS": (
                    actual_source_report.get("H2D_TOTAL_WALL_MS")
                    if actual_source_report is not None else None
                ),
                "SOURCE_TO_GPU_READY_MS": (
                    actual_source_report.get("SOURCE_TO_GPU_READY_MS")
                    if actual_source_report is not None else None
                ),
                "SOURCE_H2D_OVERLAP_MS": (
                    actual_source_report.get("SOURCE_H2D_OVERLAP_MS")
                    if actual_source_report is not None else None
                ),
                "POST_SOURCE_H2D_TAIL_MS": (
                    actual_source_report.get("POST_SOURCE_H2D_TAIL_MS")
                    if actual_source_report is not None else None
                ),
                "GPU_COPY_ACTIVE_SUM_MS": resource_active_sum,
                "GPU_COPY_STREAM_SPAN_MS": resource_stream_span,
                "GPU_COPY_ACTIVE_UNION_MS": resource_active_union,
                "GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS": resource_idle_inside_span,
                "GPU_COPY_COUNT": self.gpu_copy_count,
                "GPU_COPY_BYTES": self.gpu_copy_bytes,
                "REQUEST_CUMULATIVE_H2D_SUBMIT_COUNT": resource_report.get(
                    "REQUEST_CUMULATIVE_H2D_SUBMIT_COUNT"
                ),
                "REQUEST_CUMULATIVE_H2D_COMPLETION_COUNT": resource_report.get(
                    "REQUEST_CUMULATIVE_H2D_COMPLETION_COUNT"
                ),
                "REQUEST_CUMULATIVE_GPU_COPY_COUNT": resource_report.get(
                    "REQUEST_CUMULATIVE_GPU_COPY_COUNT"
                ),
                "REQUEST_CUMULATIVE_GPU_COPY_BYTES": resource_report.get(
                    "REQUEST_CUMULATIVE_GPU_COPY_BYTES"
                ),
                "GPU_COPY_ACTIVE_UNION_PROVEN_SINGLE_STREAM_NON_OVERLAP": (
                    resource_report.get(
                        "GPU_COPY_ACTIVE_UNION_PROVEN_SINGLE_STREAM_NON_OVERLAP"
                    )
                    if self.transport_resources is not None else None
                ),
                "GPU_COPY_ACTIVE_UNION_PROOF": resource_report.get(
                    "GPU_COPY_ACTIVE_UNION_PROOF"
                ) if self.transport_resources is not None else None,
                "event_object_count": self.event_object_count,
                "event_rerecord_count": self.event_rerecord_count,
                "request_physical_pinned_alloc_count": self.request_physical_pinned_alloc_count,
                "transport_physical_pinned_alloc_count": self.transport_physical_pinned_alloc_count,
                "transport_resources": _json_safe(self.transport_resources),
                "arena_bytes": resource_report.get("arena_bytes"),
                "slot_count": resource_report.get("slot_count"),
                "slot_bytes": resource_report.get("slot_bytes"),
                "pinned_arena_physical_allocation_count": resource_report.get("pinned_arena_physical_allocation_count"),
                "pinned_arena_physical_allocation_bytes": resource_report.get("pinned_arena_physical_allocation_bytes"),
                "logical_slot_count": resource_report.get("logical_slot_count"),
                "logical_slot_bytes": resource_report.get("logical_slot_bytes"),
                "request_physical_pinned_alloc_count": resource_report.get(
                    "request_physical_pinned_alloc_count"
                ),
                "transport_physical_pinned_alloc_count": resource_report.get(
                    "transport_physical_pinned_alloc_count"
                ),
                "created_vs_reused": resource_report.get("created_vs_reused"),
                "dedicated_h2d_stream_count": resource_report.get(
                    "dedicated_h2d_stream_count"
                ),
                "event_object_count": resource_report.get("event_object_count"),
                "event_rerecord_count": resource_report.get("event_rerecord_count"),
                "h2d_submit_count": resource_report.get("h2d_submit_count"),
                "h2d_completion_count": resource_report.get("h2d_completion_count"),
                "cuda_h2d_stream_object_count": resource_report.get("cuda_h2d_stream_object_count"),
                "cuda_start_event_object_count": resource_report.get("cuda_start_event_object_count"),
                "cuda_end_event_object_count": resource_report.get("cuda_end_event_object_count"),
                "cuda_event_rerecord_count": resource_report.get("cuda_event_rerecord_count"),
                "fresh_cuda_event_per_copy_count": resource_report.get("fresh_cuda_event_per_copy_count"),
                "quiescence_evidence": (
                    actual_source_report.get("quiescence_evidence")
                    if actual_source_report is not None else None
                ),
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


@dataclass
class _DispatchSubmission:
    leases: tuple[StageLease, ...]
    records: tuple[ReadyRecord, ...]
    ticket: CompletionTicket | None = None
    submit_ns: int | None = None
    tail: bool = False

    @property
    def byte_count(self) -> int:
        return sum(record.nbytes for record in self.records)


class TransportDispatcher:
    """One owner for H2D submit, event lifecycle, reaping, and slot return."""

    def __init__(self, pool: StagingPool, backend: TransportBackend, config: TransportConfig, telemetry: _Telemetry, destination_size: int | None = None, aggregation_ranges: Sequence[SourceRange] | None = None) -> None:
        self.pool, self.backend, self.config, self.telemetry = pool, backend, config, telemetry
        self.destination_size = destination_size
        self._queue: list[tuple[StageLease, ReadyRecord]] = []
        self._queue_condition = threading.Condition()
        # A ready item is removed from _queue before the backend call.  Keep
        # that handoff visible until the event is registered so bounded drain
        # cannot mistake the gap for quiescence and lose the lease/event.
        self._handoff: dict[int, _DispatchSubmission] = {}
        self._uncertain_handoffs: dict[int, _DispatchSubmission] = {}
        self._late_submissions: dict[int, _DispatchSubmission] = {}
        self._unresolved_late_submission_keys: set[int] = set()
        self._in_flight: dict[int, _DispatchSubmission] = {}
        self._actual_h2d_tokens: dict[int, int] = {}
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
        self._next_group_id = 0
        self._submitted_keys: set[tuple[int, int, int, str | int | None]] = set()
        self._aggregation_order = tuple(
            (item.source_offset, item.target_offset, item.length, item.record_id)
            for item in sorted(aggregation_ranges or (), key=lambda item: (item.source_offset, item.target_offset))
        )
        self._aggregation_index = {
            key: index for index, key in enumerate(self._aggregation_order)
        }

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

    def _record_h2d_complete(self, key: int, ticket: CompletionTicket | None = None) -> None:
        token = self._actual_h2d_tokens.pop(key, None)
        if token is not None and self.telemetry.actual_source is not None:
            self.telemetry.actual_source.record_h2d_complete(token)
        harvest = getattr(self.backend, "harvest_completion", None)
        if callable(harvest) and ticket is not None:
            harvest(ticket)
            resource_stats = getattr(getattr(self.backend, "resources", None), "telemetry", None)
            if callable(resource_stats):
                self.telemetry.transport_resources = resource_stats()
                resource = getattr(self.backend, "resources", None)
                self.telemetry.gpu_copy_active_sum_ms = resource.gpu_copy_active_sum_ms
                self.telemetry.gpu_copy_count = resource.gpu_copy_count
                self.telemetry.gpu_copy_bytes = resource.gpu_copy_bytes

    def _poll(self) -> None:
        started = time.monotonic_ns() if self.telemetry.diagnostics_enabled else None
        with self._queue_condition:
            active = list(self._in_flight.items())
            if self.telemetry.diagnostics_enabled:
                assert self.telemetry.qd_samples is not None
                self.telemetry.qd_samples.append(len(active))
        for key, submission in active:
            ticket = submission.ticket
            if ticket is None:
                raise TransportError("H2D submission has no completion ticket")
            try:
                raw_status = self.backend.poll_event(ticket.end_event)
                status = EventStatus(raw_status)
            except BaseException as exc:
                with self._lease_cleanup_lock:
                    with self._queue_condition:
                        current = self._in_flight.pop(key, None)
                        self._queue_condition.notify_all()
                    if current is None or any(lease._returned for lease in submission.leases):
                        continue
                    for lease in submission.leases:
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
                if current is None or any(lease._returned for lease in submission.leases):
                    continue
                if status == EventStatus.COMPLETE:
                    # The completion event is the proof that the submitted
                    # copy finished.  Count it before pool bookkeeping so a
                    # cleanup race cannot make telemetry claim it did not.
                    completion_observed_ns = time.monotonic_ns()
                    self.telemetry.h2d_completed_bytes += submission.byte_count
                    self.telemetry.h2d_completed_count += 1
                    if self.telemetry.first_h2d_completion_observed_ns is None:
                        self.telemetry.first_h2d_completion_observed_ns = completion_observed_ns
                    self.telemetry.final_h2d_completion_observed_ns = completion_observed_ns
                    self._record_h2d_complete(key, ticket)
                    for lease in submission.leases:
                        self.pool._return_completed(lease)
                    release_ticket = getattr(self.backend, "release_ticket", None)
                    if callable(release_ticket):
                        release_ticket(ticket)
                    with self._queue_condition:
                        self._completed_records.extend(submission.records)
                    if self.telemetry.diagnostics_enabled:
                        assert submission.submit_ns is not None
                        assert self.telemetry.h2d_latencies_ns is not None
                        self.telemetry.h2d_latencies_ns.append(time.monotonic_ns() - submission.submit_ns)
                elif status == EventStatus.UNCERTAIN:
                    for lease in submission.leases:
                        self.pool._poison(lease, "uncertain H2D completion")
                    self.telemetry.completion_classification = "uncertain"
                    raise TransportError("uncertain H2D completion; staging pool poisoned")
                else:
                    for lease in submission.leases:
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
        for key, submission in active:
            ticket = submission.ticket
            if ticket is None:
                continue
            with self._queue_condition:
                is_late_submission = key in self._late_submissions
            try:
                if self.telemetry.diagnostics_enabled:
                    assert self.telemetry.event_cancel_count is not None
                    self.telemetry.event_cancel_count += 1
                self.backend.cancel_event(ticket.end_event)
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
                    status = EventStatus(self.backend.poll_event(ticket.end_event))
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
                        self.telemetry.h2d_completed_bytes += submission.byte_count
                        self.telemetry.h2d_completed_count += 1
                        self._record_h2d_complete(key, ticket)
                        for lease in submission.leases:
                            if not lease._returned:
                                self.pool._return_completed(lease)
                        release_ticket = getattr(self.backend, "release_ticket", None)
                        if callable(release_ticket):
                            release_ticket(ticket)
                        with self._queue_condition:
                            self._completed_records.extend(submission.records)
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
                    for lease in submission.leases:
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
                    for lease in submission.leases:
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
                handoff = list(self._handoff.items())
                self._handoff.clear()
                self._uncertain_handoffs.update(dict(handoff))
                self._queue_condition.notify_all()
            for _key, item in handoff:
                for lease in item.leases:
                    self.pool._poison(lease, "cancelled dispatcher handoff was not completed", expected_abort=True)
        self._cancel_in_flight(deadline)

    @staticmethod
    def _record_key(record: ReadyRecord) -> tuple[int, int, int, str | int | None]:
        return (record.source_offset, record.destination_offset, record.nbytes, record.record_id)

    def _take_submission(self) -> tuple[int, _DispatchSubmission] | None:
        with self._queue_condition:
            if not self._queue:
                return None
            forced_tail = False
            if not self._aggregation_order:
                chosen = [self._queue[0]]
            else:
                self.telemetry.aggregation_scheduler_enter_count += 1
                available = {
                    self._record_key(record): (index, lease, record)
                    for index, (lease, record) in enumerate(self._queue)
                }
                pending = [
                    key for key in self._aggregation_order
                    if key not in self._submitted_keys
                ]
                key = next((key for key in pending if key in available), None)
                if key is None:
                    candidates = [
                        self._record_key(record)
                        for _index, (_lease, record) in enumerate(self._queue)
                        if self._record_key(record) not in self._submitted_keys
                    ]
                    if not candidates:
                        return None
                    key = min(
                        candidates,
                        key=lambda item: self._aggregation_index.get(
                            item, len(self._aggregation_order)
                        ),
                    )
                first_index = available[key][0]
                first_order = self._aggregation_index.get(key)
                chosen = [self._queue[first_index]]
                if first_order is not None:
                    for next_key in self._aggregation_order[first_order + 1:]:
                        if next_key in self._submitted_keys or next_key not in available:
                            break
                        candidate = self._queue[available[next_key][0]]
                        if (
                            self.config.h2d_target_bytes is not None
                            and sum(item[1].nbytes for item in chosen) + candidate[1].nbytes
                            > self.config.h2d_target_bytes
                        ):
                            break
                        chosen.append(candidate)

                    first_record = chosen[0][1]
                    eligible = (
                        len(chosen) == 1
                        and self.config.h2d_target_bytes is not None
                        and self.config.h2d_target_bytes > self.config.block_bytes
                        and first_record.nbytes == self.config.block_bytes
                        and first_record.destination_offset % self.config.block_bytes == 0
                        and first_order + 1 < len(self._aggregation_order)
                    )
                    if eligible:
                        next_key = self._aggregation_order[first_order + 1]
                        next_missing = (
                            next_key not in available
                            and next_key not in self._submitted_keys
                        )
                        if next_missing and not self._stop:
                            # The producer may still publish the next
                            # canonical extent.  Keep every queued item in
                            # place and let publish/quiesce wake the loop.
                            # A full ready queue would otherwise block that
                            # producer forever, so use an explicit singleton
                            # fallback in that bounded case.
                            if len(self._queue) < int(self.config.ready_queue_capacity):
                                self.telemetry.aggregation_wait_count += 1
                                return None
                            self.telemetry.note_aggregation_fallback(
                                "canonical_extent_not_ready_queue_full"
                            )
                        forced_tail = next_missing and self._stop

            candidate_submission = _DispatchSubmission(
                tuple(item[0] for item in chosen),
                tuple(item[1] for item in chosen),
            )
            if len(chosen) > 1:
                reason = self._group_reason(candidate_submission)
                if reason is not None:
                    self.telemetry.note_aggregation_fallback(reason)
                    # Only remove the canonical first item.  The remaining
                    # queue entries retain their publication order.
                    chosen = [chosen[0]]
                    forced_tail = False
            chosen_keys = {self._record_key(record) for _lease, record in chosen}
            self._queue[:] = [
                item for item in self._queue
                if self._record_key(item[1]) not in chosen_keys
            ]
            self._submitted_keys.update(chosen_keys)
            self._next_group_id += 1
            submission = _DispatchSubmission(
                tuple(item[0] for item in chosen),
                tuple(item[1] for item in chosen),
                tail=forced_tail,
            )
            self._handoff[self._next_group_id] = submission
            if self.telemetry.diagnostics_enabled:
                self.telemetry.ready_depth = len(self._queue)
            self._queue_condition.notify_all()
            return self._next_group_id, submission

    def _group_reason(self, submission: _DispatchSubmission) -> str | None:
        if len(submission.records) == 1:
            return None
        if self.config.h2d_target_bytes is None:
            return "h2d_target_not_configured"
        if submission.byte_count > self.config.h2d_target_bytes:
            return "h2d_target_exceeded"
        if any(record.nbytes != self.config.block_bytes for record in submission.records):
            return "partial_extent"
        for left, right in zip(submission.records, submission.records[1:]):
            if left.source_offset + left.nbytes != right.source_offset:
                return "source_extents_not_contiguous"
            if left.destination_offset + left.nbytes != right.destination_offset:
                return "destination_extents_not_contiguous"
        indices = [lease.slot_index for lease in submission.leases]
        if indices != list(range(indices[0], indices[0] + len(indices))):
            return "physical_slots_not_consecutive"
        if self.pool.backing_buffer is None:
            return "physical_storage_not_contiguous"
        if any(
            lease.preferred_slot_index is not None and not lease.preferred_slot_honored
            for lease in submission.leases
        ):
            return "canonical_slot_assignment_failed"
        with self.pool._meta:
            for lease in submission.leases:
                try:
                    slot = self.pool._validate_locked(lease)
                except LeaseError:
                    return "lease_ownership_invalid"
                if slot.state != SlotState.READY or not lease._producer_retired:
                    return "lease_ownership_invalid"
                if not _buffer_is_backing_range(
                    slot.buffer,
                    self.pool.backing_buffer,
                    slot.index * self.pool.block_bytes,
                    self.pool.block_bytes,
                ):
                    return "physical_storage_not_contiguous"
        return None

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
                    can_take = not cancelled and self._queue and len(self._in_flight) < self.config.queue_depth
                    done = self._stop and not can_take and not self._queue and not self._in_flight and not self._late_submissions
                if cancelled:
                    self._cleanup_cancelled(self._cleanup_deadline)
                    return
                if done:
                    return
                if not can_take:
                    with self._queue_condition:
                        self._queue_condition.wait(0.001)
                    continue
                taken = self._take_submission()
                if taken is None:
                    continue
                group_id, submission = taken
                lease = submission.leases[0]
                record = submission.records[0]
                ticket: CompletionTicket | None = None
                try:
                    with self._lease_cleanup_lock:
                        for member in submission.leases:
                            self.pool._mark_in_flight(member)
                        v2_source = self.pool._v2_dispatch_source(record, submission.byte_count)
                        if v2_source is not None:
                            source = v2_source
                        else:
                            source = (
                                self.pool._buffer_for_dispatch_group(submission.leases, submission.byte_count)
                                if len(submission.leases) > 1
                                else self.pool._buffer_for_dispatch(lease, record.nbytes)
                            )
                    submit_ns = time.monotonic_ns()
                    actual_h2d_token = None
                    if self.telemetry.actual_source is not None:
                        # This is deliberately before submit_h2d: the core
                        # telemetry timestamp represents entry to the backend
                        # operation, not the point at which it returns.
                        actual_h2d_token = self.telemetry.actual_source.record_h2d_submit(
                            submission.byte_count, timestamp_ns=submit_ns
                        )
                    submit_ticket = getattr(self.backend, "submit_h2d_ticket", None)
                    if callable(submit_ticket):
                        ticket = submit_ticket(
                            source, record.destination_offset,
                            slot_index=lease.slot_index,
                            submission_id=lease.generation,
                        )
                    else:
                        event = self.backend.submit_h2d(source, record.destination_offset)
                        if event is not None:
                            ticket = CompletionTicket(
                                lease.slot_index, lease.generation, None, event, submission.byte_count
                            )
                    if ticket is None:
                        raise TransportError("backend returned no completion event")
                    # The backend accepted the copy.  Count it before the
                    # handoff bookkeeping so a bounded-drain race cannot
                    # under-report a real submission.
                    self.telemetry.h2d_submitted_bytes += submission.byte_count
                    self.telemetry.h2d_submitted_count += 1
                    if self.telemetry.h2d_submission_sizes is not None:
                        self.telemetry.h2d_submission_sizes.append(submission.byte_count)
                    if len(submission.records) > 1:
                        self.telemetry.aggregated_submission_count += 1
                    else:
                        self.telemetry.non_aggregated_submission_count += 1
                        if submission.tail or record.nbytes < self.config.block_bytes:
                            self.telemetry.tail_submission_count += 1
                    if actual_h2d_token is not None:
                        # Do not associate the token until a completion event
                        # exists.  A failed/no-event submit remains incomplete
                        # in the core telemetry and can never be reported as a
                        # completed H2D.
                        self._actual_h2d_tokens[group_id] = actual_h2d_token
                    if self.telemetry.diagnostics_enabled:
                        if self.telemetry.first_h2d_submit_ns is None:
                            self.telemetry.first_h2d_submit_ns = submit_ns
                        self.telemetry.final_h2d_submit_ns = submit_ns
                except BaseException as exc:
                    if self._cancelled:
                        self._cleanup_cancelled(self._cleanup_deadline)
                        return
                    with self._lease_cleanup_lock:
                        for member in submission.leases:
                            self.pool._poison(member, "H2D submission did not produce a completion event")
                    self._set_dispatcher_error(exc)
                    self._cleanup_cancelled(self._cleanup_deadline)
                    return
                with self._lease_cleanup_lock:
                    with self._queue_condition:
                        handoff = self._handoff.get(group_id)
                        uncertain = self._uncertain_handoffs.pop(group_id, None)
                        registered = _DispatchSubmission(
                            submission.leases, submission.records, ticket,
                            submit_ns if self.telemetry.diagnostics_enabled else None,
                        )
                        if handoff is not None and handoff.leases == submission.leases:
                            self._handoff.pop(group_id, None)
                            self._in_flight[group_id] = registered
                            registration_error = None
                        elif uncertain is not None and uncertain.leases == submission.leases and self._cancelled:
                            # The backend accepted the copy after bounded
                            # cancellation detached the handoff.  It is now a
                            # first-class event, not an ignorable late return.
                            self._late_submissions[group_id] = registered
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
                        for member in submission.leases:
                            self.pool._poison(member, str(registration_error))
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
                handoff = list(self._handoff.items())
                self._queue.clear()
                self._handoff.clear()
                self._uncertain_handoffs.update(dict(handoff))
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
            for _key, item in handoff:
                for lease in item.leases:
                    self.pool._poison(lease, "bounded drain could not complete dispatcher handoff", expected_abort=True)
            for item in active:
                for lease in item.leases:
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
        resources: GoldenTransferResources | None = None,
    ) -> None:
        self.config = config or TransportConfig()
        # This class is the dispatcher implementation.  The legacy default is
        # exposed only by create_transport()/LegacyTransport, so supplying a
        # backend here cannot accidentally report the legacy arm.
        self.arm = normalize_transport_arm(DISPATCHER_ARM if arm is None else arm)
        if self.arm == DISPATCHER_ARM and backend is None:
            raise ValueError("dispatcher arm requires an explicitly supplied backend")
        self.backend = backend
        self.resources = resources
        if resources is not None and (
            self.config.staging_slots != resources.slot_count
            or self.config.block_bytes != resources.slot_bytes
        ):
            raise ValueError("request transport resources require the fixed E27 staging dimensions")
        if pool is None:
            buffers = None
            if resources is not None:
                pool = resources.new_pool(self.config.capacity_class)
            allocator = getattr(backend, "allocate_staging_buffers", None)
            if pool is None and callable(allocator):
                buffers = cast(Sequence[Any], allocator(self.config.staging_slots, self.config.block_bytes))
            if pool is None:
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
        preferred_slot_index: int | None = None,
    ) -> StageLease:
        started = time.monotonic_ns() if self.telemetry.diagnostics_enabled else None
        try:
            return self.pool.acquire(
                timeout=timeout, declared_range=declared_range, producer_id=producer_id,
                preferred_slot_index=preferred_slot_index,
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

    def start(self, *, destination_size: int | None = None, aggregation_ranges: Sequence[SourceRange] | None = None) -> None:
        if self.backend is None:
            raise ValueError("dispatcher arm requires an explicitly supplied backend")
        if self.dispatcher is not None:
            raise TransportError("transport already started")
        self.dispatcher = TransportDispatcher(
            self.pool, self.backend, self.config, self.telemetry, destination_size,
            aggregation_ranges,
        )
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
        ranges: Sequence[SourceRange], block_bytes: int, producer_count: int
    ) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[SourceRange, ...], ...]]:
        """Plan four fixed source regions and their block-clamped work.

        The input ranges describe the logical destination layout. Static E27
        deliberately ignores their scheduling order, partitions the contiguous
        source span once, and lets each producer walk only its own region.
        Intersections preserve destination mapping and record identity.
        """
        if producer_count < 1:
            raise ValueError("static E27 transport requires at least one producer")
        if not ranges:
            regions = static_e27_regions(0, producer_count)
            return regions, tuple(() for _ in range(producer_count))
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
        regions = static_e27_regions(total, producer_count)
        work_specs: list[list[tuple[int, SourceRange, int, int]]] = [
            [] for _ in range(producer_count)
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
        work: list[list[SourceRange]] = [[] for _ in range(producer_count)]
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
        return self._static_e27_work(
            source_ranges, self.config.block_bytes, self.config.producer_workers
        )

    @staticmethod
    def _read_exact(reader: Callable[[int, int], bytes], item: SourceRange, retries: int, telemetry: _Telemetry, producer_id: int = 0) -> bytes:
        pieces: list[bytes] = []
        offset = item.source_offset
        remaining = item.length
        attempts = 0
        while remaining:
            if attempts > retries:
                raise ReconciliationError(f"short read for source range {item.source_offset}:{item.length}")
            if telemetry.actual_source is not None:
                chunk = telemetry.actual_source.read(
                    reader, offset, remaining, producer_id=producer_id,
                    retry_number=attempts, destination_offset=item.target_offset + (offset - item.source_offset),
                )
            else:
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
            # Golden I/O V2 C0 child-fill is lease-aware: the reader needs the
            # slot/generation/declared range to write the exact leased arena
            # slot.  Prefer that explicit seam over the raw target/offset form.
            lease_reader = getattr(reader, "readinto_lease", None)
            bound_actual_source = getattr(reader, "actual_source_telemetry", None)
            handles_actual_source = getattr(reader, "handles_actual_source_telemetry", False) is True
            if callable(lease_reader):
                count = lease_reader(lease, view, offset, producer_id)
            elif handles_actual_source and bound_actual_source is not None:
                count = reader.readinto(view, offset, producer_id)
            elif telemetry.actual_source is not None:
                count = telemetry.actual_source.readinto(
                    reader, view, offset, item.length - total, producer_id=producer_id,
                    retry_number=attempts,
                    destination_offset=item.target_offset + total,
                )
            else:
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

    def _persist_actual_source_quiescence(self, phase: str) -> dict[str, Any] | None:
        """Persist one honest lifecycle checkpoint in the core telemetry."""
        actual_source = self.telemetry.actual_source
        if actual_source is None:
            return None

        with self._active_lock:
            live_workers = self._active_producers
        with self._reader_lock:
            open_readers = len(self._reader_handles)

        queue_blocks = handoff_blocks = event_count = 0
        dispatcher_live = False
        unresolved_late = False
        if self.dispatcher is not None:
            dispatcher_live = bool(
                self.dispatcher._thread is not None and self.dispatcher._thread.is_alive()
            )
            with self.dispatcher._queue_condition:
                queue_blocks = len(self.dispatcher._queue)
                handoff_blocks = len(self.dispatcher._handoff) + len(self.dispatcher._uncertain_handoffs)
                event_count = len(self.dispatcher._in_flight) + len(self.dispatcher._late_submissions)
                unresolved_late = bool(self.dispatcher._unresolved_late_submission_keys)

        actual_h2d_inflight = 0
        raw_h2d = getattr(actual_source, "_h2d", None)
        if isinstance(raw_h2d, Mapping):
            actual_h2d_inflight = sum(
                getattr(item, "complete_ns", None) is None for item in raw_h2d.values()
            )
        h2d_inflight = max(event_count, actual_h2d_inflight)
        slot_states = self.pool.states()
        ownership_quiescent = not (
            open_readers or dispatcher_live or queue_blocks or handoff_blocks or h2d_inflight
            or unresolved_late
            or any(state in (SlotState.FILLING, SlotState.READY, SlotState.IN_FLIGHT) for state in slot_states)
        )
        source_fallback = getattr(actual_source, "fallback", 0)
        fallback = max(
            self.telemetry.fallback_count,
            source_fallback if isinstance(source_fallback, int) and not isinstance(source_fallback, bool) else 0,
        )
        source_poison = getattr(actual_source, "poison", 0)
        poison = max(
            1 if self.pool.poisoned else 0,
            source_poison if isinstance(source_poison, int) and not isinstance(source_poison, bool) else 0,
        )
        actual_source.fallback = fallback
        actual_source.poison = poison
        evidence = {
            "checkpoint": phase,
            "phase": phase,
            "live_source_workers": live_workers,
            "live_source_readers": open_readers,
            "live_dispatcher": int(dispatcher_live),
            "live_slots": sum(state in (SlotState.FILLING, SlotState.READY, SlotState.IN_FLIGHT) for state in slot_states),
            "actual_syscalls_in_flight": actual_source.actual_inflight,
            "queued_ready_blocks": queue_blocks + handoff_blocks,
            "free_buffers": sum(state == SlotState.FREE for state in slot_states),
            "h2ds_in_flight": h2d_inflight,
            "unreaped_events": h2d_inflight,
            "outstanding_futures": 0,
            "fallback": fallback,
            "poison": poison,
            "reconciliation_state": bool(self.telemetry.coverage_ok and self.telemetry.h2d_reconciled),
            "ownership_quiescent": ownership_quiescent,
        }

        # Newer core telemetry may retain every checkpoint under either name;
        # the current core exposes set_quiescence as its compatible API.
        for method_name in (
            "record_quiescence_checkpoint",
            "checkpoint",
            "set_quiescence",
        ):
            method = getattr(actual_source, method_name, None)
            if not callable(method):
                continue
            try:
                method(evidence)
            except TypeError:
                try:
                    method(**evidence)
                except TypeError:
                    method(phase, evidence)
            break
        return evidence

    def execute(
        self, *args: Any, **kwargs: Any
    ) -> TransportResult:
        if self.resources is not None:
            self.resources.transport_enter()
        try:
            return self._execute(*args, **kwargs)
        finally:
            if self.resources is not None:
                self.resources.transport_exit(poisoned=self.pool.poisoned)

    def _execute(
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
        if self.resources is not None:
            self.telemetry.request_physical_pinned_alloc_count = self.resources.physical_pinned_alloc_count
            self.telemetry.transport_physical_pinned_alloc_count = 0
            self.telemetry.event_object_count = self.resources.event_object_count
            self.telemetry.event_rerecord_count = self.resources.event_rerecord_count
            self.telemetry.transport_resources = self.resources.telemetry()
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
        self.telemetry.h2d_target_bytes = self.config.h2d_target_bytes
        self.telemetry.aggregation_enabled = self.config.aggregation_enabled
        self.telemetry.source_block_bytes = self.config.block_bytes
        producer_count = self.config.producer_workers
        self.telemetry.producer_ids = tuple(range(producer_count))
        if self.arm == STATIC_E27_ARM:
            self._static_regions, self._static_work = self._static_e27_work(
                source_ranges, self.config.block_bytes, producer_count
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
        self.telemetry.source_block_count = len(planned_ranges)
        if parse_count < 0:
            raise ValueError("parse_count must be non-negative")
        self.telemetry.parse_count = parse_count
        self.telemetry.owner, self.telemetry.adoption = owner, adoption
        self.telemetry.owner_count, self.telemetry.adoption_result = owner_count, adoption_result
        self._owner_lifetime = owner
        source_qd = min(self.config.queue_depth, producer_count)
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
        handles_actual_source = getattr(read_source, "handles_actual_source_telemetry", False) is True
        bound_actual_source = getattr(read_source, "actual_source_telemetry", None)
        if self.pool.v2_source_backing is not None:
            # Golden I/O Process V2: the CUDA-sterile child already filled the
            # registered backing, so the parent performs NO physical source
            # read.  Leave actual-source telemetry unset rather than fabricating
            # physical syscall events for the parent.
            self.telemetry.actual_source = None
        elif getattr(read_source, "child_owned_physical_reads", False) is True:
            # Golden I/O V2 C0: the CUDA-sterile child performs the positioned
            # source reads directly into the leased shared slots.  The parent
            # records no physical source syscall of its own.
            self.telemetry.actual_source = None
        elif handles_actual_source:
            if not isinstance(bound_actual_source, ActualSourceTelemetry):
                close_errors = self._close_source()
                error = ReconciliationError(
                    "source marked handles_actual_source_telemetry=True must provide "
                    "an ActualSourceTelemetry instance"
                )
                if close_errors:
                    failure = TransportFailure(error, secondary_errors=close_errors)
                    self._retain_failure_lifetime(failure)
                    raise failure from error
                raise error
            self.telemetry.actual_source = bound_actual_source
        elif self.arm == STATIC_E27_ARM:
            source_start = source_ranges[0].source_offset if source_ranges else 0
            source_end = max((item.source_offset + item.length for item in source_ranges), default=source_start)
            self.telemetry.actual_source = ActualSourceTelemetry(
                arm=self.arm,
                producer_count=producer_count,
                regions=self.telemetry.static_regions or (),
                expected_ranges=((source_start, source_end),) if source_end > source_start else (),
                expected_destination_ranges=tuple(
                    (item.target_offset, item.target_offset + item.length) for item in source_ranges
                ),
                expected_h2d_bytes=exact_destination_size,
            )
        self._persist_actual_source_quiescence("bind")
        read_fn: Callable[[int, int], bytes] | None = None
        if not direct_readinto:
            read_fn = cast(
                Callable[[int, int], bytes],
                read_source if callable(read_source) else getattr(read_source, "read"),
            )
        self.telemetry.source_read_mode = "direct_readinto" if direct_readinto else "legacy_bytes"
        self.telemetry.source_open_count += 1
        try:
            self.start(
                destination_size=exact_destination_size,
                aggregation_ranges=planned_ranges if self.config.aggregation_enabled else None,
            )
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
        static_cursors = [0] * producer_count

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
                while not self._abort_requested:
                    if static_items is not None:
                        with index_lock:
                            item = None
                            if static_cursors[producer_id] < len(static_items):
                                item = static_items[static_cursors[producer_id]]
                                static_cursors[producer_id] += 1
                            else:
                                # Match M2's affinity_breaks rule: once a
                                # sticky lane is exhausted, claim the next
                                # unowned extent from another lane.
                                for other_id, other_items in enumerate(self._static_work or ()):
                                    if static_cursors[other_id] < len(other_items):
                                        item = other_items[static_cursors[other_id]]
                                        static_cursors[other_id] += 1
                                        if other_id != producer_id:
                                            self.telemetry.affinity_breaks += 1
                                        break
                            if item is None:
                                return
                    else:
                        with index_lock:
                            if index >= len(source_ranges):
                                return
                            item = source_ranges[index]
                            index += 1
                    lease: StageLease | None = None
                    try:
                        preferred_slot = (
                            (item.target_offset // self.config.block_bytes) % self.config.staging_slots
                            if self.config.aggregation_enabled
                            and item.length == self.config.block_bytes
                            and item.target_offset % self.config.block_bytes == 0
                            else None
                        )
                        lease = self.acquire(
                            declared_range=item,
                            producer_id=producer_id,
                            preferred_slot_index=preferred_slot,
                        )
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
                                data = self._read_exact(
                                    read_fn, item, self.config.read_retries, self.telemetry, producer_id
                                )
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
        self._persist_actual_source_quiescence("source_completion")
        if self.telemetry.diagnostics_enabled:
            self.telemetry.final_drain_start_ns = time.monotonic_ns()
        if abort_deadline is None:
            # No abort occurred: wait for the dispatcher to quiesce without
            # applying the cleanup timeout to normal completion.
            self.drain(None, bounded=False)
        else:
            self.drain(deadline=abort_deadline)
        if self.resources is not None:
            self.resources.finish_span()
            self.telemetry.gpu_copy_active_sum_ms = self.resources.gpu_copy_active_sum_ms
            self.telemetry.gpu_copy_stream_span_ms = self.resources.gpu_copy_stream_span_ms
            self.telemetry.gpu_copy_active_union_ms = self.resources.gpu_copy_active_union_ms
            self.telemetry.gpu_copy_idle_inside_stream_span_ms = self.resources.gpu_copy_idle_inside_stream_span_ms
            self.telemetry.gpu_copy_count = self.resources.gpu_copy_count
            self.telemetry.gpu_copy_bytes = self.resources.gpu_copy_bytes
            self.telemetry.event_rerecord_count = self.resources.event_rerecord_count
            self.telemetry.transport_resources = self.resources.telemetry()
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
        self._persist_actual_source_quiescence("final_completion")
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
        if self.telemetry.actual_source is not None:
            actual_report = telemetry.get("actual_source")
            evidence = actual_report.get("quiescence_evidence") if isinstance(actual_report, Mapping) else None
            failed_proofs: list[str] = []
            if self.telemetry.actual_source.actual_inflight != 0:
                failed_proofs.append("actual source syscalls remain in flight")
            if not isinstance(actual_report, Mapping) or actual_report.get("quiescence") is not True:
                failed_proofs.append("final raw quiescence proof is not true")
            if not isinstance(actual_report, Mapping) or actual_report.get("h2d_reconciliation_complete") is not True:
                failed_proofs.append("required H2D events were not reconciled")
            if not isinstance(evidence, Mapping):
                failed_proofs.append("final quiescence evidence is missing")
            else:
                for field in (
                    "live_source_workers", "live_source_readers", "live_dispatcher",
                    "live_slots", "queued_ready_blocks", "h2ds_in_flight",
                    "unreaped_events", "outstanding_futures", "fallback", "poison",
                ):
                    if evidence.get(field) != 0:
                        failed_proofs.append(f"final quiescence field {field} is not zero")
                if evidence.get("actual_syscalls_in_flight") != 0:
                    failed_proofs.append("final actual syscall count is not zero")
                if evidence.get("reconciliation_state") is not True:
                    failed_proofs.append("final reconciliation state is not true")
                if evidence.get("ownership_quiescent") is not True:
                    failed_proofs.append("ownership is not quiescent")
            if failed_proofs:
                failure = TransportFailure(
                    ReconciliationError("actual source telemetry did not prove completion: " + "; ".join(failed_proofs)),
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
        actual_source = self.telemetry.actual_source
        actual_source_inflight = actual_source.actual_inflight if actual_source is not None else 0
        actual_h2d_inflight = 0
        if actual_source is not None:
            raw_h2d = getattr(actual_source, "_h2d", None)
            if isinstance(raw_h2d, Mapping):
                actual_h2d_inflight = sum(
                    getattr(item, "complete_ns", None) is None for item in raw_h2d.values()
                )
        final_evidence = None
        if actual_source is not None:
            final_evidence = getattr(actual_source, "quiescence_evidence", None)
            if final_evidence is None:
                # The current core keeps its latest checkpoint privately.  Do
                # not call report() here: snapshot checks must stay shallow,
                # including with diagnostics disabled.
                final_evidence = getattr(actual_source, "_quiescence", None)
        if (
            self.pool.poisoned or producers or dispatcher_live or queue_live or handoff_live
            or events_live or open_readers or slot_live or actual_source_inflight
            or actual_h2d_inflight
            or (self.resources is not None and self.resources.active_tickets)
            or (final_evidence is not None and not ActualSourceTelemetry._quiescent(final_evidence))
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
    resources: GoldenTransferResources | None = None,
) -> GoldenQDTransport | LegacyTransport:
    selected = normalize_transport_arm(arm)
    return (
        LegacyTransport(config, backend)
        if selected == LEGACY_ARM
        else GoldenQDTransport(
            config, backend, arm=selected, diagnostics=diagnostics, resources=resources
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

    def __init__(self, destination: Any, *, stream: Any = None, resources: GoldenTransferResources | None = None) -> None:
        try:
            import torch
        except ImportError as exc:
            raise TransportError("CudaTransferBackend requires torch") from exc
        torch_uint8 = getattr(torch, "uint8")
        if not isinstance(destination, torch.Tensor) or destination.dtype != torch_uint8 or not destination.is_cuda or destination.dim() != 1:
            raise ValueError("destination must be a one-dimensional CUDA uint8 torch tensor")
        self.torch = torch
        self.destination = destination
        self.resources = resources
        self.stream = stream if stream is not None else (resources.h2d_stream if resources is not None else None)

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
        if slots == DEFAULT_STAGING_SLOTS and block_bytes == DEFAULT_BLOCK_BYTES:
            arena = torch_empty(REQUEST_ARENA_BYTES, dtype=torch_uint8, pin_memory=True)
            return [
                arena[index * block_bytes : (index + 1) * block_bytes]
                for index in range(slots)
            ]
        return [torch_empty(block_bytes, dtype=torch_uint8, pin_memory=True) for _ in range(slots)]

    def submit_h2d(self, source: Any, destination_offset: int) -> Any:
        raise TransportError(
            "CudaTransferBackend requires a reusable completion ticket; "
            "use submit_h2d_ticket"
        )

    def submit_h2d_ticket(
        self, source: Any, destination_offset: int, *, slot_index: int, submission_id: int
    ) -> CompletionTicket:
        if self.resources is None:
            raise TransportError("request resources are required for ticketed CUDA copies")
        ticket = self.resources.begin_ticket(slot_index, int(source.numel()))
        try:
            self._submit(source, destination_offset, ticket=ticket)
        except BaseException:
            self.resources._active_tickets.pop(ticket.slot_index, None)
            raise
        return ticket

    def _submit(self, source: Any, destination_offset: int, *, ticket: CompletionTicket | None) -> Any:
        torch = self.torch
        if self.resources is None or ticket is None:
            raise TransportError("request resources are required for CUDA submission")
        torch_uint8 = getattr(torch, "uint8")
        if not isinstance(source, torch.Tensor) or source.dtype != torch_uint8 or source.dim() != 1 or source.is_cuda:
            raise ValueError("CUDA backend requires a one-dimensional CPU uint8 staging tensor")
        end = destination_offset + source.numel()
        if destination_offset < 0 or end > self.destination.numel():
            raise ReconciliationError("CUDA destination offset is out of bounds")
        stream = self.stream
        if stream is None:
            raise TransportError("CUDA submission requires a request-owned dedicated stream")
        with torch.cuda.stream(stream):
            self.resources.begin_span()
            record_start = getattr(ticket.start_event, "record", None)
            if not callable(record_start):
                raise TransportError("request H2D start event is not recordable")
            record_start(stream)
            self.destination[destination_offset:end].copy_(source, non_blocking=True)
            record_end = getattr(ticket.end_event, "record", None)
            if not callable(record_end):
                raise TransportError("request H2D end event is not recordable")
            record_end(stream)
            self.resources.h2d_submit_count += 1
        return ticket

    def harvest_completion(self, ticket: CompletionTicket) -> None:
        if self.resources is not None:
            self.resources.harvest_ticket(ticket)

    def release_ticket(self, ticket: CompletionTicket) -> None:
        if self.resources is not None:
            self.resources.return_ticket(ticket)

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
    "BackingAdoption", "BackingOwner", "CancellationError", "CompletionTicket", "CudaTransferBackend", "DECOUPLED_ARM", "DEFAULT_BLOCK_BYTES",
    "DEFAULT_QUEUE_DEPTH", "DEFAULT_STAGING_SLOTS", "REQUEST_ARENA_BYTES", "DISPATCHER_ARM", "CONTROL_ARM", "STATIC_E27_ARM", "TEST_ARM",
    "STATIC_E27_PRODUCERS", "EventStatus", "FakeBackend", "FakeEvent", "FakeSource", "GoldenQDTransport", "GoldenTransferResources", "LEGACY_ARM", "LeaseError", "LegacyTransport", "OutputViewSpec",
    "PoolPoisonedError", "QDTransport", "ReadyRecord", "ReconciliationError", "SlotState", "SourceRange",
    "StageLease", "StagingPool", "PinnedRangeReader", "TransportBackend", "TransportConfig", "TransportDispatcher", "TransportError",
    "evaluate_e27_source_mechanism",
    "TransportFailure", "TransportResult", "create_transport", "map_output_views", "normalize_transport_arm", "resolve_h2d_target_bytes", "static_e27_regions", "static_segments",
    "prove_backing_survives_stage_release", "ExtentState", "ExtentTransportError", "PlannedExtent", "PlannedRead",
    "PreplannedExtentTransport", "plan_preplanned_extents", "validate_preplanned_extents",
]
