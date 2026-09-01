"""Stdlib-only evidence for the E27 source and H2D mechanism."""

from __future__ import annotations

import copy
import math
import threading
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class SourceReadEvent:
    producer_id: int
    region_id: int | None
    source_offset: int
    requested_bytes: int
    returned_bytes: int
    retry_number: int
    short_read: bool
    syscall_enter_monotonic_ns: int
    syscall_exit_monotonic_ns: int
    destination_offset: int | None = None
    error: str | None = None
    physical_provenance: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class SourceTransition:
    timestamp_ns: int
    delta: int
    depth: int
    producer_id: int

    def to_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class _Call:
    producer_id: int
    region_id: int | None
    source_offset: int
    requested_bytes: int
    retry_number: int
    destination_offset: int | None
    enter_ns: int
    sequence: int


@dataclass
class _H2D:
    token: int
    bytes: int
    submit_ns: int
    complete_ns: int | None = None


def _now() -> int:
    return time.monotonic_ns()


def _region_rows(regions: Sequence[Any] | None) -> list[dict[str, int]]:
    rows: list[dict[str, int]] = []
    for index, value in enumerate(regions or ()):
        if isinstance(value, Mapping):
            producer = int(value.get("producer_id", index))
            region_id = int(value.get("region_id", producer))
            start = int(value.get("start", value.get("region_start", 0)))
            end = int(value.get("end", value.get("region_end", start)))
        else:
            start, end = (int(value[0]), int(value[1]))
            producer = index
            region_id = index
        if producer < 0 or region_id < 0 or start < 0 or end < start:
            raise ValueError("invalid source region")
        rows.append({"producer_id": producer, "region_id": region_id, "start": start, "end": end})
    return rows


def _interval_union(intervals: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    ordered = sorted((start, end) for start, end in intervals if end > start)
    result: list[tuple[int, int]] = []
    for start, end in ordered:
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def _union_ns(intervals: Sequence[tuple[int, int]]) -> int:
    return sum(end - start for start, end in _interval_union(intervals))


class ActualSourceTelemetry:
    """Capture physical positioned reads and derive source/H2D evidence.

    ``readinto`` and ``read`` are adapters: their enter/exit calls surround
    the supplied reader call itself, rather than a worker's surrounding work.
    """

    def __init__(
        self,
        *,
        arm: str = "static_e27",
        producer_count: int = 4,
        regions: Sequence[Any] | None = None,
        expected_ranges: Sequence[Any] | None = None,
        expected_destination_ranges: Sequence[Any] | None = None,
        expected_h2d_bytes: int | None = None,
    ) -> None:
        self.arm = arm
        self.producer_count = int(producer_count)
        self.regions = _region_rows(regions)
        self.expected_ranges = self._ranges(expected_ranges)
        self.expected_destination_ranges = self._ranges(expected_destination_ranges)
        if expected_h2d_bytes is not None and expected_h2d_bytes < 0:
            raise ValueError("expected_h2d_bytes must be non-negative")
        self.expected_h2d_bytes = expected_h2d_bytes
        self._lock = threading.RLock()
        self._actual_inflight = 0
        self._max_actual_inflight = 0
        self._sequence = 0
        self._open: dict[int, _Call] = {}
        self._events: list[SourceReadEvent] = []
        self._transitions: list[SourceTransition] = []
        self._h2d: dict[int, _H2D] = {}
        self._next_h2d = 1
        self._quiescence: dict[str, Any] | None = None
        self._quiescence_checkpoints: list[dict[str, Any]] = []
        self._physical_provenance: str | None = None
        self.fallback = 0
        self.poison = 0

    @staticmethod
    def _ranges(values: Sequence[Any] | None) -> list[tuple[int, int]]:
        result = []
        for value in values or ():
            if isinstance(value, Mapping):
                start = int(value.get("start", value.get("source_offset", 0)))
                end = int(value.get("end", start + int(value.get("length", 0))))
            else:
                start, end = int(value[0]), int(value[1])
            if start < 0 or end < start:
                raise ValueError("invalid expected source range")
            result.append((start, end))
        return result

    def configure_topology(
        self,
        regions: Sequence[Any],
        expected_ranges: Sequence[Any],
        expected_destination_ranges: Sequence[Any] | None = None,
    ) -> None:
        with self._lock:
            self.regions = _region_rows(regions)
            self.expected_ranges = self._ranges(expected_ranges)
            self.expected_destination_ranges = self._ranges(expected_destination_ranges)

    def mark_physical_syscall_provenance(self, marker: str) -> None:
        """Mark events as coming from the physical syscall boundary.

        Reader adapters intentionally do not set this marker.  Callers which
        have established that their reader is the real positioned syscall
        path (or a test fixture explicitly standing in for it) must opt in.
        """
        if not isinstance(marker, str) or not marker.strip():
            raise ValueError("physical syscall provenance marker must be non-empty")
        with self._lock:
            self._physical_provenance = marker.strip()
            self._events = [
                replace(event, physical_provenance=self._physical_provenance)
                for event in self._events
            ]

    @property
    def actual_inflight(self) -> int:
        with self._lock:
            return self._actual_inflight

    @property
    def max_actual_source_inflight(self) -> int:
        with self._lock:
            return self._max_actual_inflight

    @property
    def events(self) -> tuple[SourceReadEvent, ...]:
        with self._lock:
            return tuple(self._events)

    @property
    def transitions(self) -> tuple[SourceTransition, ...]:
        with self._lock:
            return tuple(self._transitions)

    def _resolve_region(self, producer_id: int, source_offset: int, region_id: int | None) -> int | None:
        if region_id is not None:
            return int(region_id)
        for row in self.regions:
            if row["producer_id"] == producer_id and row["start"] <= source_offset < row["end"]:
                return row["region_id"]
        return None

    def syscall_enter(
        self,
        producer_id: int,
        source_offset: int,
        requested_bytes: int,
        *,
        retry_number: int = 0,
        region_id: int | None = None,
        destination_offset: int | None = None,
        timestamp_ns: int | None = None,
    ) -> _Call:
        if requested_bytes < 0 or retry_number < 0 or source_offset < 0:
            raise ValueError("invalid source syscall arguments")
        now = _now() if timestamp_ns is None else int(timestamp_ns)
        with self._lock:
            self._sequence += 1
            call = _Call(
                int(producer_id), self._resolve_region(producer_id, source_offset, region_id),
                int(source_offset), int(requested_bytes), int(retry_number), destination_offset,
                now, self._sequence,
            )
            self._open[id(call)] = call
            self._actual_inflight += 1
            self._max_actual_inflight = max(self._max_actual_inflight, self._actual_inflight)
            self._transitions.append(SourceTransition(now, 1, self._actual_inflight, int(producer_id)))
            return call

    def syscall_exit(
        self,
        call: _Call,
        returned_bytes: int,
        *,
        timestamp_ns: int | None = None,
        error: BaseException | str | None = None,
    ) -> SourceReadEvent:
        now = _now() if timestamp_ns is None else int(timestamp_ns)
        with self._lock:
            if id(call) not in self._open:
                raise RuntimeError("source syscall was already closed")
            self._open.pop(id(call), None)
            if returned_bytes < 0 or returned_bytes > call.requested_bytes:
                raise ValueError("invalid returned byte count")
            if now < call.enter_ns:
                raise ValueError("source syscall exit precedes enter")
            self._actual_inflight -= 1
            if self._actual_inflight < 0:
                self._actual_inflight = 0
                raise RuntimeError("actual source inflight became negative")
            self._transitions.append(SourceTransition(now, -1, self._actual_inflight, call.producer_id))
            event = SourceReadEvent(
                call.producer_id, call.region_id, call.source_offset, call.requested_bytes,
                int(returned_bytes), call.retry_number, returned_bytes < call.requested_bytes,
                call.enter_ns, now, call.destination_offset,
                None if error is None else str(error),
                self._physical_provenance,
            )
            self._events.append(event)
            return event

    def readinto(
        self,
        reader: Any,
        target: Any,
        source_offset: int,
        requested_bytes: int,
        *,
        producer_id: int,
        retry_number: int = 0,
        region_id: int | None = None,
        destination_offset: int | None = None,
    ) -> int:
        call = self.syscall_enter(producer_id, source_offset, requested_bytes,
                                  retry_number=retry_number, region_id=region_id,
                                  destination_offset=destination_offset)
        try:
            returned = reader.readinto(target, source_offset, producer_id)
        except BaseException as exc:
            self.syscall_exit(call, 0, error=exc)
            raise
        if not isinstance(returned, int) or isinstance(returned, bool):
            self.syscall_exit(call, 0, error="non-integer readinto result")
            raise TypeError("source readinto must return an integer byte count")
        self.syscall_exit(call, returned)
        return returned

    def read(
        self,
        reader: Callable[[int, int], bytes],
        source_offset: int,
        requested_bytes: int,
        *,
        producer_id: int,
        retry_number: int = 0,
        region_id: int | None = None,
        destination_offset: int | None = None,
    ) -> bytes:
        call = self.syscall_enter(producer_id, source_offset, requested_bytes,
                                  retry_number=retry_number, region_id=region_id,
                                  destination_offset=destination_offset)
        try:
            value = reader(source_offset, requested_bytes)
        except BaseException as exc:
            self.syscall_exit(call, 0, error=exc)
            raise
        if not isinstance(value, (bytes, bytearray, memoryview)):
            self.syscall_exit(call, 0, error="non-bytes read result")
            raise TypeError("source reader must return bytes-like data")
        result = bytes(value)
        self.syscall_exit(call, len(result))
        return result

    def record_h2d_submit(self, nbytes: int, *, timestamp_ns: int | None = None) -> int:
        if nbytes < 0:
            raise ValueError("H2D bytes must be non-negative")
        with self._lock:
            token = self._next_h2d
            self._next_h2d += 1
            self._h2d[token] = _H2D(token, int(nbytes), _now() if timestamp_ns is None else int(timestamp_ns))
            return token

    def record_h2d_complete(self, token: int, *, timestamp_ns: int | None = None) -> None:
        with self._lock:
            item = self._h2d.get(int(token))
            if item is None:
                raise KeyError(token)
            if item.complete_ns is not None:
                raise RuntimeError("H2D event was already completed")
            now = _now() if timestamp_ns is None else int(timestamp_ns)
            if now < item.submit_ns:
                raise ValueError("H2D completion precedes submit")
            item.complete_ns = now

    h2d_submit = record_h2d_submit
    h2d_complete = record_h2d_complete

    def set_quiescence(self, evidence: Mapping[str, Any] | None = None, **fields: Any) -> None:
        value = dict(evidence or {})
        value.update(fields)
        # Compatibility API: this updates the latest snapshot but deliberately
        # does not manufacture durable lifecycle history.
        with self._lock:
            self._quiescence = copy.deepcopy(value)

    def record_quiescence_checkpoint(self, evidence: Mapping[str, Any]) -> None:
        """Persist an immutable copy of one source lifecycle checkpoint."""
        if not isinstance(evidence, Mapping):
            raise TypeError("quiescence checkpoint must be a mapping")
        value = copy.deepcopy(dict(evidence))
        with self._lock:
            self._quiescence_checkpoints.append(value)
            self._quiescence = copy.deepcopy(value)

    @staticmethod
    def _quiescent(evidence: Mapping[str, Any] | None) -> bool:
        required = (
            "live_source_workers", "actual_syscalls_in_flight", "queued_ready_blocks",
            "free_buffers", "h2ds_in_flight", "unreaped_events", "outstanding_futures",
            "fallback", "poison", "reconciliation_state", "ownership_quiescent",
        )
        if not evidence or any(key not in evidence or evidence[key] is None for key in required):
            return False
        zero = ("live_source_workers", "actual_syscalls_in_flight", "queued_ready_blocks",
                "h2ds_in_flight", "unreaped_events", "outstanding_futures", "fallback", "poison")
        if not isinstance(evidence["free_buffers"], int) or isinstance(evidence["free_buffers"], bool) or evidence["free_buffers"] < 0:
            return False
        if any(not isinstance(evidence[key], int) or isinstance(evidence[key], bool) for key in zero):
            return False
        return all(evidence[key] == 0 for key in zero) and evidence["reconciliation_state"] is True and evidence["ownership_quiescent"] is True

    def _topology(self, events: Sequence[SourceReadEvent]) -> dict[str, Any]:
        regions = self.regions
        expected = _interval_union(self.expected_ranges)
        contiguous = len(regions) == 4 and {row["producer_id"] for row in regions} == set(range(4)) and {row["region_id"] for row in regions} == set(range(4)) and all(
            left["end"] == right["start"] for left, right in zip(regions, regions[1:])
        ) and (not expected or (regions[0]["start"] == expected[0][0] and regions[-1]["end"] == expected[-1][1]))
        fixed_ownership = len(regions) == 4 and all(
            row["producer_id"] == row["region_id"] for row in regions
        ) and all(
            (owned := next((r for r in regions if r["producer_id"] == event.producer_id and r["start"] <= event.source_offset < r["end"]), None)) is not None
            and event.region_id == owned["region_id"]
            for event in events
        )
        spans = sorted((e.source_offset, e.source_offset + e.returned_bytes) for e in events if e.returned_bytes)
        overlaps = sum(1 for left, right in zip(spans, spans[1:]) if right[0] < left[1])
        gaps = 0
        if expected:
            cursor = expected[0][0]
            for start, end in spans:
                if end <= cursor:
                    continue
                if start > cursor:
                    gaps += 1
                cursor = max(cursor, end)
            if cursor < expected[-1][1]:
                gaps += 1
            if spans and spans[0][0] < expected[0][0]:
                overlaps += 1
        elif spans:
            gaps = 0
        duplicates = 0
        identities: set[tuple[int, int, int, int]] = set()
        for event in events:
            identity = (event.producer_id, event.source_offset, event.requested_bytes, event.retry_number)
            if identity in identities:
                duplicates += 1
            identities.add(identity)
        expected_bytes = sum(end - start for start, end in expected)
        actual_bytes = sum(e.returned_bytes for e in events)
        coverage_exact = bool(expected) and actual_bytes == expected_bytes and gaps == 0 and overlaps == 0
        destination_spans = sorted(
            (e.destination_offset, e.destination_offset + e.returned_bytes)
            for e in events if e.destination_offset is not None and e.returned_bytes
        )
        destination_expected = _interval_union(self.expected_destination_ranges)
        if destination_expected:
            destination_gaps = 0
            destination_overlaps = sum(
                1 for left, right in zip(destination_spans, destination_spans[1:]) if right[0] < left[1]
            )
            cursor = destination_expected[0][0]
            for start, end in destination_spans:
                if end <= cursor:
                    continue
                if start > cursor:
                    destination_gaps += 1
                cursor = max(cursor, end)
            if cursor < destination_expected[-1][1]:
                destination_gaps += 1
            gaps += destination_gaps
            overlaps += destination_overlaps
            coverage_exact = coverage_exact and sum(end - start for start, end in destination_expected) == actual_bytes and destination_gaps == 0 and destination_overlaps == 0
        monotonic = True
        last: dict[int, int] = {}
        for event in events:
            if event.producer_id in last and event.source_offset < last[event.producer_id]:
                monotonic = False
            last[event.producer_id] = event.source_offset
        return {
            "producer_count": self.producer_count,
            "fixed_contiguous_regions": contiguous,
            "fixed_ownership": fixed_ownership,
            "monotonic_reads": monotonic,
            "coverage_exact": coverage_exact,
            "gaps": gaps,
            "overlaps": overlaps,
            "unexpected_duplicates": duplicates,
            "regions": [dict(row) for row in regions],
        }

    def report(self) -> dict[str, Any]:
        with self._lock:
            events = list(self._events)
            transitions = list(self._transitions)
            h2d = list(self._h2d.values())
            source_start = min((event.syscall_enter_monotonic_ns for event in events), default=None)
            source_end = max((event.syscall_exit_monotonic_ns for event in events), default=None)
            source_wall = None if source_start is None or source_end is None else source_end - source_start
            source_intervals = [(e.syscall_enter_monotonic_ns, e.syscall_exit_monotonic_ns) for e in events]
            busy = _union_ns(source_intervals)
            occupancy: dict[int, int] = {}
            starvation: list[dict[str, int]] = []
            current_depth = 0
            previous = source_start
            for transition in sorted(transitions, key=lambda row: row.timestamp_ns):
                if previous is not None and transition.timestamp_ns >= previous:
                    occupancy[current_depth] = occupancy.get(current_depth, 0) + transition.timestamp_ns - previous
                    if current_depth == 0 and transition.timestamp_ns > previous:
                        starvation.append({"start_ns": previous, "end_ns": transition.timestamp_ns, "duration_ns": transition.timestamp_ns - previous})
                current_depth = transition.depth
                previous = transition.timestamp_ns
            if source_end is not None and previous is not None and source_end >= previous:
                occupancy[current_depth] = occupancy.get(current_depth, 0) + source_end - previous
            h2d_intervals = [(item.submit_ns, item.complete_ns) for item in h2d if item.complete_ns is not None]
            h2d_start = min((item.submit_ns for item in h2d), default=None)
            h2d_end = max((item.complete_ns for item in h2d if item.complete_ns is not None), default=None)
            h2d_wall = None if h2d_start is None or h2d_end is None else h2d_end - h2d_start
            h2d_bytes = sum(item.bytes for item in h2d)
            h2d_completed = sum(item.bytes for item in h2d if item.complete_ns is not None)
            overlap = _union_ns([(max(a, source_start), min(b, source_end)) for a, b in h2d_intervals if source_start is not None and source_end is not None and a < source_end and b > source_start])
            topology = self._topology(events)
            producer_report: dict[str, Any] = {}
            for row in self.regions:
                mine = [e for e in events if e.producer_id == row["producer_id"]]
                first = min((e.syscall_enter_monotonic_ns for e in mine), default=None)
                last = max((e.syscall_exit_monotonic_ns for e in mine), default=None)
                wall = None if first is None or last is None else last - first
                bytes_read = sum(e.returned_bytes for e in mine)
                producer_report[str(row["producer_id"])] = {
                    "region_start": row["start"], "region_end": row["end"], "bytes": bytes_read,
                    "read_count": len(mine), "first_syscall": first, "last_syscall": last,
                    "wall_ms": None if wall is None else wall / 1e6,
                    "syscall_busy_total_ms": _union_ns([(e.syscall_enter_monotonic_ns, e.syscall_exit_monotonic_ns) for e in mine]) / 1e6,
                    "throughput_bytes_s": None if not wall else bytes_read / (wall / 1e9),
                }
            source_ms = None if source_wall is None else source_wall / 1e6
            final_gpu = h2d_end
            report = {
                "arm": self.arm,
                "producer_count": self.producer_count,
                "events": [event.to_dict() for event in events],
                "actual_source_events": [event.to_dict() for event in events],
                "transitions": [transition.to_dict() for transition in transitions],
                "actual_source_transitions": [transition.to_dict() for transition in transitions],
                "physical_syscall_provenance": self._physical_provenance,
                "actual_source_inflight": self._actual_inflight,
                "max_actual_source_inflight": self._max_actual_inflight,
                "SOURCE_TOTAL_WALL_MS": source_ms,
                "SOURCE_SYSCALL_UNION_BUSY_MS": busy / 1e6,
                "milliseconds_at_qd": {str(key): occupancy.get(key, 0) / 1e6 for key in range(5)} | {str(key): value / 1e6 for key, value in occupancy.items() if key > 4},
                "qd_occupancy_ms": {str(key): occupancy.get(key, 0) / 1e6 for key in range(5)} | {str(key): value / 1e6 for key, value in occupancy.items() if key > 4},
                "time_weighted_mean_qd": (sum(key * value for key, value in occupancy.items()) / source_wall if source_wall else None),
                "percentage_source_wall_at_qd4": (occupancy.get(4, 0) * 100 / source_wall if source_wall else None),
                "starvation_gaps": starvation,
                "producer_report": producer_report,
                "h2d_events": [{"token": item.token, "bytes": item.bytes, "submit_ns": item.submit_ns, "complete_ns": item.complete_ns} for item in h2d],
                "h2d_submitted_bytes": h2d_bytes,
                "h2d_completed_bytes": h2d_completed,
                "first_h2d_submit_ns": h2d_start,
                "last_h2d_submit_ns": max((item.submit_ns for item in h2d), default=None),
                "first_h2d_completion_ns": min((item.complete_ns for item in h2d if item.complete_ns is not None), default=None),
                "final_required_event_completion_ns": h2d_end,
                "h2d_reconciliation_complete": bool(h2d) and all(item.complete_ns is not None for item in h2d) and h2d_bytes == h2d_completed and (self.expected_h2d_bytes is None or h2d_bytes == self.expected_h2d_bytes),
                "H2D_TOTAL_WALL_MS": None if h2d_wall is None else h2d_wall / 1e6,
                "SOURCE_H2D_OVERLAP_MS": overlap / 1e6,
                "SOURCE_TO_GPU_READY_MS": None if source_start is None or final_gpu is None else (final_gpu - source_start) / 1e6,
                "POST_SOURCE_H2D_TAIL_MS": None if source_end is None or final_gpu is None else max(0, final_gpu - source_end) / 1e6,
                "source_finished_to_gpu_ready_tail_ms": None if source_end is None or final_gpu is None else max(0, final_gpu - source_end) / 1e6,
                "dispatcher_control": {
                    "h2d_submitted_bytes": h2d_bytes,
                    "h2d_completed_bytes": h2d_completed,
                    "h2d_inflight": sum(item.complete_ns is None for item in h2d),
                    "unreaped_events": sum(item.complete_ns is None for item in h2d),
                    "h2d_reconciliation_complete": bool(h2d) and all(item.complete_ns is not None for item in h2d) and h2d_bytes == h2d_completed,
                },
                "topology": topology,
                "topology_inputs": {
                    "regions": [dict(row) for row in self.regions],
                    "expected_ranges": [list(item) for item in self.expected_ranges],
                    "expected_destination_ranges": [list(item) for item in self.expected_destination_ranges],
                    "expected_h2d_bytes": self.expected_h2d_bytes,
                },
                "fallback": self.fallback,
                "poison": self.poison,
                "quiescence_evidence": copy.deepcopy(self._quiescence) if self._quiescence is not None else None,
                "quiescence": self._quiescent(self._quiescence),
                "required_evidence_persisted": False,
            }
            if self._quiescence_checkpoints:
                report["quiescence_checkpoints"] = copy.deepcopy(self._quiescence_checkpoints)
            # This is only a persistence marker; the public evaluator performs
            # the complete independent validation without trusting this flag.
            report["required_evidence_persisted"] = bool(
                events and transitions and h2d and self._physical_provenance
                and all(event.physical_provenance == self._physical_provenance for event in events)
                and self.expected_ranges and self.expected_destination_ranges
                and self.expected_h2d_bytes is not None
                and self._actual_inflight == 0
                and sum(item.bytes for item in h2d) == self.expected_h2d_bytes
                and _checkpoint_history_validation(self._quiescence_checkpoints)["history_ok"]
                and all(item.complete_ns is not None for item in h2d)
            )
            return report

    def to_dict(self) -> dict[str, Any]:
        return self.report()


_CHECKPOINT_INT_FIELDS = (
    "live_source_workers", "live_source_readers", "live_dispatcher", "live_slots",
    "actual_syscalls_in_flight", "queued_ready_blocks", "free_buffers",
    "h2ds_in_flight", "unreaped_events", "outstanding_futures", "fallback", "poison",
)
_CHECKPOINT_BOOL_FIELDS = ("reconciliation_state", "ownership_quiescent")
_CHECKPOINT_PHASES = ("bind", "source_completion", "final_completion")


def _checkpoint_history_validation(history: Any) -> dict[str, Any]:
    """Validate lifecycle checkpoints without consulting report summaries."""
    result: dict[str, Any] = {
        "history_ok": False,
        "fields_ok": False,
        "bind_ok": False,
        "source_completion_ok": False,
        "final_completion_ok": False,
        "ordered_ok": False,
    }
    if not isinstance(history, list) or not history:
        return result

    by_phase: dict[str, Mapping[str, Any]] = {}
    fields_ok = True
    for checkpoint in history:
        if not isinstance(checkpoint, Mapping):
            fields_ok = False
            continue
        required = ("checkpoint", "phase", *_CHECKPOINT_INT_FIELDS, *_CHECKPOINT_BOOL_FIELDS)
        if any(key not in checkpoint for key in required):
            fields_ok = False
            continue
        phase = checkpoint["phase"]
        if (
            not isinstance(phase, str)
            or not phase.strip()
            or checkpoint["checkpoint"] != phase
            or phase in by_phase
            or any(not _integer(checkpoint[key], minimum=0) for key in _CHECKPOINT_INT_FIELDS)
            or any(not isinstance(checkpoint[key], bool) for key in _CHECKPOINT_BOOL_FIELDS)
            or checkpoint["h2ds_in_flight"] != checkpoint["unreaped_events"]
        ):
            fields_ok = False
            continue
        by_phase[phase] = checkpoint

    result["fields_ok"] = fields_ok
    missing = any(phase not in by_phase for phase in _CHECKPOINT_PHASES)
    if missing:
        return result

    bind = by_phase["bind"]
    source = by_phase["source_completion"]
    final = by_phase["final_completion"]
    positions = [next(index for index, row in enumerate(history) if row is item) for item in (bind, source, final)]
    result["ordered_ok"] = positions == sorted(positions)

    # At bind the source handle is attached but work has not started.  This
    # is intentionally not quiescent: ownership of the reader is live.
    result["bind_ok"] = (
        fields_ok
        and bind["live_source_workers"] == 0
        and bind["live_source_readers"] > 0
        and bind["live_dispatcher"] == 0
        and bind["live_slots"] == 0
        and bind["actual_syscalls_in_flight"] == 0
        and bind["queued_ready_blocks"] == 0
        and bind["free_buffers"] > 0
        and bind["h2ds_in_flight"] == 0
        and bind["unreaped_events"] == 0
        and bind["outstanding_futures"] == 0
        and bind["fallback"] == 0
        and bind["poison"] == 0
        and bind["reconciliation_state"] is False
        and bind["ownership_quiescent"] is False
    )
    # Source workers and positioned syscalls have retired, but the reader,
    # dispatcher, slots, and asynchronous H2D work may still be live.
    result["source_completion_ok"] = (
        fields_ok
        and source["live_source_workers"] == 0
        and source["live_source_readers"] > 0
        and source["actual_syscalls_in_flight"] == 0
        and source["reconciliation_state"] is False
        and source["ownership_quiescent"] is False
    )
    result["final_completion_ok"] = (
        fields_ok
        and all(final[key] == 0 for key in _CHECKPOINT_INT_FIELDS if key != "free_buffers")
        and final["free_buffers"] > 0
        and final["reconciliation_state"] is True
        and final["ownership_quiescent"] is True
    )
    result["history_ok"] = bool(
        fields_ok
        and result["ordered_ok"]
        and result["bind_ok"]
        and result["source_completion_ok"]
        and result["final_completion_ok"]
    )
    return result


PREDICATES = (
    "arm", "producer_count", "fixed_contiguous_regions", "fixed_ownership", "monotonic_reads",
    "coverage_exact", "gaps", "overlaps", "unexpected_duplicates", "actual_syscall_qd_telemetry_complete",
    "max_actual_source_inflight", "source_total_wall_present", "qd_occupancy_present",
    "h2d_reconciliation_complete", "fallback", "poison", "quiescence_checkpoint_history",
    "checkpoint_fields", "bind_checkpoint", "source_completion_checkpoint",
    "final_completion_checkpoint", "checkpoint_order", "quiescence", "required_evidence_persisted",
)


def _integer(value: Any, *, minimum: int | None = None) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and (minimum is None or value >= minimum)
    )


def _finite_number(value: Any, *, minimum: float | None = None) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(number) and (minimum is None or number >= minimum)


def _same_number(left: Any, right: float, tolerance: float = 1e-9) -> bool:
    return _finite_number(left, minimum=0) and math.isclose(float(left), right, rel_tol=tolerance, abs_tol=tolerance)


def _parse_ranges(value: Any) -> tuple[list[tuple[int, int]], bool]:
    if not isinstance(value, list):
        return [], False
    result: list[tuple[int, int]] = []
    for row in value:
        if isinstance(row, Mapping):
            if "start" in row and "end" in row:
                start, end = row["start"], row["end"]
            elif "source_offset" in row and "length" in row:
                start, length = row["source_offset"], row["length"]
                if not _integer(start, minimum=0) or not _integer(length, minimum=0):
                    return [], False
                end = start + length
            else:
                return [], False
        elif isinstance(row, (list, tuple)) and len(row) == 2:
            start, end = row
        else:
            return [], False
        if not _integer(start, minimum=0) or not _integer(end, minimum=0) or end < start:
            return [], False
        result.append((start, end))
    return result, True


def _coverage(expected: list[tuple[int, int]], actual: list[tuple[int, int]]) -> tuple[bool, int, int]:
    """Return exact coverage, gap count, and overlap count without trusting summaries."""
    if not expected:
        return False, 1, 0
    expected_union = _interval_union(expected)
    ordered = sorted(actual)
    overlaps = 0
    previous_end: int | None = None
    for start, end in ordered:
        if end <= start:
            continue
        if previous_end is not None and start < previous_end:
            overlaps += 1
        previous_end = max(previous_end or end, end)
        if not any(region_start <= start and end <= region_end for region_start, region_end in expected_union):
            overlaps += 1
    actual_union = _interval_union(ordered)
    gaps = 0
    cursor = 0
    for start, end in expected_union:
        pieces = [(a, b) for a, b in actual_union if b > start and a < end]
        covered = start
        for piece_start, piece_end in pieces:
            if piece_start > covered:
                gaps += 1
            covered = max(covered, min(piece_end, end))
        if covered < end:
            gaps += 1
        cursor = max(cursor, covered)
    exact = actual_union == expected_union and gaps == 0 and overlaps == 0
    return exact, gaps, overlaps


def _validate_evidence(report: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct E27 facts from raw rows.  This function is deliberately defensive."""
    result: dict[str, Any] = {
        "events_ok": False, "transitions_ok": False, "topology_ok": False,
        "timing_ok": False, "h2d_ok": False, "quiescence_ok": False,
        "provenance_ok": False, "max_inflight": 0, "source_wall_ns": None,
        "busy_ns": None, "occupancy": {}, "starvation": [], "gaps": 1,
        "overlaps": 0, "duplicates": 0, "coverage_exact": False,
        "fixed_contiguous_regions": False, "fixed_ownership": False,
        "monotonic_reads": False,
    }
    try:
        # Only the explicitly persisted raw keys are authoritative.  In
        # particular, the convenient ``events`` and ``topology`` summaries
        # cannot stand in for these inputs.
        events = report.get("actual_source_events")
        transitions = report.get("actual_source_transitions")
        inputs = report.get("topology_inputs")
        if not isinstance(events, list) or not events or not isinstance(transitions, list):
            return result
        if not isinstance(inputs, Mapping):
            return result
        expected, expected_ok = _parse_ranges(inputs.get("expected_ranges"))
        expected_dest, expected_dest_ok = _parse_ranges(inputs.get("expected_destination_ranges"))
        regions_raw = inputs.get("regions")
        expected_h2d = inputs.get("expected_h2d_bytes")
        if not expected_ok or not expected_dest_ok or not expected or not expected_dest:
            return result
        if not _integer(expected_h2d, minimum=1):
            return result
        if sum(end - start for start, end in _interval_union(expected_dest)) != expected_h2d:
            return result
        for ranges in (expected, expected_dest):
            ordered_ranges = sorted(ranges)
            if any(left[1] > right[0] for left, right in zip(ordered_ranges, ordered_ranges[1:])):
                return result

        marker = report.get("physical_syscall_provenance")
        result["provenance_ok"] = isinstance(marker, str) and bool(marker.strip())
        event_fields = (
            "producer_id", "region_id", "source_offset", "requested_bytes",
            "returned_bytes", "retry_number", "short_read",
            "syscall_enter_monotonic_ns", "syscall_exit_monotonic_ns",
            "destination_offset", "error", "physical_provenance",
        )
        clean_events: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, Mapping) or any(field not in event for field in event_fields):
                return result
            if (
                not _integer(event["producer_id"], minimum=0)
                or not _integer(event["region_id"], minimum=0)
                or not _integer(event["source_offset"], minimum=0)
                or not _integer(event["requested_bytes"], minimum=1)
                or not _integer(event["returned_bytes"], minimum=0)
                or not _integer(event["retry_number"], minimum=0)
                or not isinstance(event["short_read"], bool)
                or not _integer(event["syscall_enter_monotonic_ns"], minimum=0)
                or not _integer(event["syscall_exit_monotonic_ns"], minimum=0)
                or not _integer(event["destination_offset"], minimum=0)
                or not isinstance(event["physical_provenance"], str)
                or not event["physical_provenance"].strip()
                or event["physical_provenance"] != marker
                or event["returned_bytes"] > event["requested_bytes"]
                or event["syscall_exit_monotonic_ns"] < event["syscall_enter_monotonic_ns"]
                or event["short_read"] != (event["returned_bytes"] < event["requested_bytes"])
                or (event["error"] is not None and not isinstance(event["error"], str))
            ):
                return result
            clean_events.append(dict(event))
        result["events_ok"] = bool(clean_events) and result["provenance_ok"]

        if len(transitions) != len(clean_events) * 2:
            return result
        depth = 0
        max_depth = 0
        previous_timestamp: int | None = None
        used: set[int] = set()
        for transition in transitions:
            if not isinstance(transition, Mapping) or any(
                key not in transition for key in ("timestamp_ns", "delta", "depth", "producer_id")
            ):
                return result
            if (
                not _integer(transition["timestamp_ns"], minimum=0)
                or transition["delta"] not in (-1, 1)
                or not _integer(transition["depth"], minimum=0)
                or not _integer(transition["producer_id"], minimum=0)
                or (previous_timestamp is not None and transition["timestamp_ns"] < previous_timestamp)
            ):
                return result
            previous_timestamp = transition["timestamp_ns"]
            depth += transition["delta"]
            if depth < 0 or transition["depth"] != depth:
                return result
            max_depth = max(max_depth, depth)
        if depth != 0:
            return result
        if "actual_source_inflight" in report and (not _integer(report["actual_source_inflight"]) or report["actual_source_inflight"] != 0):
            return result
        for event in clean_events:
            enter_match = next(
                (i for i, transition in enumerate(transitions) if i not in used
                 and transition["delta"] == 1
                 and transition["timestamp_ns"] == event["syscall_enter_monotonic_ns"]
                 and transition["producer_id"] == event["producer_id"]), None,
            )
            if enter_match is None:
                return result
            used.add(enter_match)
            exit_match = next(
                (i for i, transition in enumerate(transitions) if i not in used
                 and transition["delta"] == -1
                 and transition["timestamp_ns"] == event["syscall_exit_monotonic_ns"]
                 and transition["producer_id"] == event["producer_id"]), None,
            )
            if exit_match is None:
                return result
            if exit_match < enter_match:
                return result
            used.add(exit_match)
        if len(used) != len(transitions):
            return result
        result["transitions_ok"] = True
        result["max_inflight"] = max_depth
        if "max_actual_source_inflight" in report and (not _integer(report["max_actual_source_inflight"]) or report["max_actual_source_inflight"] != max_depth):
            result["transitions_ok"] = False

        regions: list[dict[str, int]] = []
        if not isinstance(regions_raw, list) or len(regions_raw) != 4:
            return result
        for row in regions_raw:
            if not isinstance(row, Mapping) or any(key not in row for key in ("producer_id", "region_id", "start", "end")):
                return result
            if not all(_integer(row[key], minimum=0) for key in ("producer_id", "region_id", "start", "end")) or row["end"] < row["start"]:
                return result
            regions.append({key: row[key] for key in ("producer_id", "region_id", "start", "end")})
        ordered_regions = sorted(regions, key=lambda row: (row["start"], row["end"]))
        result["fixed_contiguous_regions"] = (
            ordered_regions == regions
            and {row["producer_id"] for row in regions} == set(range(4))
            and {row["region_id"] for row in regions} == set(range(4))
            and all(left["end"] == right["start"] for left, right in zip(regions, regions[1:]))
            and regions[0]["start"] == _interval_union(expected)[0][0]
            and regions[-1]["end"] == _interval_union(expected)[-1][1]
        )
        result["fixed_ownership"] = True
        by_producer: dict[int, list[dict[str, Any]]] = {}
        for event in clean_events:
            owner = next((row for row in regions if row["producer_id"] == event["producer_id"] and row["start"] <= event["source_offset"] < row["end"]), None)
            if owner is None or event["region_id"] != owner["region_id"]:
                result["fixed_ownership"] = False
            if owner is not None and event["source_offset"] + event["returned_bytes"] > owner["end"]:
                result["fixed_ownership"] = False
            by_producer.setdefault(event["producer_id"], []).append(event)
        source_spans = [(e["source_offset"], e["source_offset"] + e["returned_bytes"]) for e in clean_events if e["returned_bytes"]]
        destination_spans = [(e["destination_offset"], e["destination_offset"] + e["returned_bytes"]) for e in clean_events if e["returned_bytes"]]
        source_exact, source_gaps, source_overlaps = _coverage(expected, source_spans)
        destination_exact, destination_gaps, destination_overlaps = _coverage(expected_dest, destination_spans)
        result["coverage_exact"] = source_exact and destination_exact
        result["gaps"] = source_gaps + destination_gaps
        result["overlaps"] = source_overlaps + destination_overlaps
        identities: set[tuple[int, int, int, int, int]] = set()
        result["duplicates"] = 0
        for event in clean_events:
            identity = (event["producer_id"], event["region_id"], event["source_offset"], event["requested_bytes"], event["retry_number"])
            if identity in identities:
                result["duplicates"] += 1
            identities.add(identity)
        result["monotonic_reads"] = True
        for producer, producer_events in by_producer.items():
            ordered = sorted(producer_events, key=lambda row: (row["syscall_enter_monotonic_ns"], row["syscall_exit_monotonic_ns"]))
            prior: dict[str, Any] | None = None
            for index, event in enumerate(ordered):
                if prior is not None and event["source_offset"] < prior["source_offset"]:
                    result["monotonic_reads"] = False
                retry = event["retry_number"]
                if retry:
                    if prior is None or prior["retry_number"] != retry - 1 or not prior["short_read"] or event["source_offset"] != prior["source_offset"] + prior["returned_bytes"]:
                        result["monotonic_reads"] = False
                if event["short_read"] and next((row for row in regions if row["producer_id"] == producer and row["start"] <= event["source_offset"] < row["end"]), {"end": event["source_offset"] + event["returned_bytes"]})["end"] > event["source_offset"] + event["returned_bytes"]:
                    continuation = ordered[index + 1] if index + 1 < len(ordered) else None
                    if continuation is None or continuation["retry_number"] != retry + 1 or continuation["source_offset"] != event["source_offset"] + event["returned_bytes"]:
                        result["monotonic_reads"] = False
                prior = event
        result["topology_ok"] = result["fixed_contiguous_regions"] and result["fixed_ownership"] and result["coverage_exact"] and result["monotonic_reads"] and result["duplicates"] == 0

        source_start = min(event["syscall_enter_monotonic_ns"] for event in clean_events)
        source_end = max(event["syscall_exit_monotonic_ns"] for event in clean_events)
        occupancy: dict[int, int] = {}
        starvation: list[dict[str, int]] = []
        previous = source_start
        depth = 0
        for transition in transitions:
            if transition["timestamp_ns"] < previous:
                return result
            duration = transition["timestamp_ns"] - previous
            occupancy[depth] = occupancy.get(depth, 0) + duration
            if depth == 0 and duration:
                starvation.append({"start_ns": previous, "end_ns": transition["timestamp_ns"], "duration_ns": duration})
            depth = transition["depth"]
            previous = transition["timestamp_ns"]
        if previous > source_end or depth != 0:
            return result
        occupancy[depth] = occupancy.get(depth, 0) + source_end - previous
        result["occupancy"] = occupancy
        result["starvation"] = starvation
        result["source_wall_ns"] = source_end - source_start
        result["busy_ns"] = _union_ns([(e["syscall_enter_monotonic_ns"], e["syscall_exit_monotonic_ns"]) for e in clean_events])
        result["timing_ok"] = result["transitions_ok"] and result["busy_ns"] <= result["source_wall_ns"]
        reported_busy = report.get("SOURCE_SYSCALL_UNION_BUSY_MS")
        reported_starvation = report.get("starvation_gaps")
        expected_starvation = result["starvation"]
        result["timing_ok"] = result["timing_ok"] and _same_number(
            reported_busy, result["busy_ns"] / 1e6
        ) and isinstance(reported_starvation, list) and reported_starvation == expected_starvation
        expected_mean = (
            sum(key * value for key, value in occupancy.items()) / result["source_wall_ns"]
            if result["source_wall_ns"] else None
        )
        expected_qd4 = (
            occupancy.get(4, 0) * 100 / result["source_wall_ns"]
            if result["source_wall_ns"] else None
        )
        if expected_mean is None or expected_qd4 is None:
            result["timing_ok"] = False
        else:
            result["timing_ok"] = result["timing_ok"] and _same_number(report.get("time_weighted_mean_qd"), expected_mean) and _same_number(report.get("percentage_source_wall_at_qd4"), expected_qd4)

        h2d_rows = report.get("h2d_events")
        if not isinstance(h2d_rows, list) or not h2d_rows:
            return result
        tokens: set[int] = set()
        h2d: list[dict[str, int]] = []
        for row in h2d_rows:
            if not isinstance(row, Mapping) or any(key not in row for key in ("token", "bytes", "submit_ns", "complete_ns")):
                return result
            if not all(_integer(row[key], minimum=1 if key in ("token", "bytes") else 0) for key in ("token", "bytes", "submit_ns", "complete_ns")):
                return result
            if row["token"] in tokens or row["complete_ns"] < row["submit_ns"]:
                return result
            tokens.add(row["token"])
            h2d.append({key: row[key] for key in ("token", "bytes", "submit_ns", "complete_ns")})
        submitted = sum(row["bytes"] for row in h2d)
        completed = submitted  # A row without complete_ns was rejected above.
        h2d_start = min(row["submit_ns"] for row in h2d)
        h2d_end = max(row["complete_ns"] for row in h2d)
        result["h2d"] = h2d
        result["h2d_submitted"] = submitted
        result["h2d_completed"] = completed
        result["h2d_wall_ns"] = h2d_end - h2d_start
        result["h2d_ok"] = submitted == expected_h2d
        source_h2d_overlap = _union_ns([
            (max(row["submit_ns"], source_start), min(row["complete_ns"], source_end))
            for row in h2d
            if row["submit_ns"] < source_end and row["complete_ns"] > source_start
        ])
        # The H2D event rows above are the raw completion evidence.  The
        # report-level timing, dispatcher, and reconciliation summaries are
        # diagnostics only and cannot establish E27.
        checkpoint_validation = _checkpoint_history_validation(report.get("quiescence_checkpoints"))
        result["checkpoint_validation"] = checkpoint_validation
        result["quiescence_ok"] = checkpoint_validation["history_ok"]
        return result
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return result


def evaluate_e27_source_mechanism(value: ActualSourceTelemetry | Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate E27 fail-closed; malformed untrusted reports never escape."""
    try:
        report = value.report() if isinstance(value, ActualSourceTelemetry) else dict(value) if isinstance(value, Mapping) else {}
        if not isinstance(report, Mapping):
            report = {}
        report = dict(report)
        evidence = _validate_evidence(report)
        occupancy = evidence["occupancy"]
        source_wall_ms = None if evidence["source_wall_ns"] is None else evidence["source_wall_ns"] / 1e6
        busy_ms = None if evidence["busy_ns"] is None else evidence["busy_ns"] / 1e6
        qd = report.get("qd_occupancy_ms")
        qd_ok = isinstance(qd, Mapping) and all(
            str(key) in qd and _same_number(qd[str(key)], occupancy.get(key, 0) / 1e6)
            for key in range(5)
        )
        if isinstance(qd, Mapping):
            qd_ok = qd_ok and all(_finite_number(item, minimum=0) for item in qd.values())
        legacy_qd = report.get("milliseconds_at_qd")
        if legacy_qd is not None:
            qd_ok = qd_ok and isinstance(legacy_qd, Mapping) and all(
                str(key) in legacy_qd and _same_number(legacy_qd[str(key)], occupancy.get(key, 0) / 1e6)
                for key in range(5)
            ) and all(_finite_number(item, minimum=0) for item in legacy_qd.values())
        source_wall_ok = _same_number(report.get("SOURCE_TOTAL_WALL_MS"), source_wall_ms or 0) if source_wall_ms is not None else False
        source_wall_ok = source_wall_ok and evidence["timing_ok"]
        fallback_ok = _integer(report.get("fallback"), minimum=0) and report.get("fallback") == 0
        poison_ok = _integer(report.get("poison"), minimum=0) and report.get("poison") == 0
        checkpoint_validation = evidence.get("checkpoint_validation", {})
        predicates: dict[str, Any] = {
            "arm": report.get("arm") == "static_e27",
            "producer_count": _integer(report.get("producer_count")) and report.get("producer_count") == 4,
            "fixed_contiguous_regions": evidence["fixed_contiguous_regions"],
            "fixed_ownership": evidence["fixed_ownership"],
            "monotonic_reads": evidence["monotonic_reads"],
            "coverage_exact": evidence["coverage_exact"],
            "gaps": evidence["gaps"] == 0,
            "overlaps": evidence["overlaps"] == 0,
            "unexpected_duplicates": evidence["duplicates"] == 0,
            "actual_syscall_qd_telemetry_complete": evidence["events_ok"] and evidence["transitions_ok"] and evidence["timing_ok"] and evidence["provenance_ok"],
            "max_actual_source_inflight": evidence["max_inflight"] >= 4,
            "source_total_wall_present": source_wall_ok,
            "qd_occupancy_present": qd_ok,
            "h2d_reconciliation_complete": evidence["h2d_ok"],
            "fallback": fallback_ok,
            "poison": poison_ok,
            "quiescence_checkpoint_history": bool(checkpoint_validation.get("history_ok")),
            "checkpoint_fields": bool(checkpoint_validation.get("fields_ok")),
            "bind_checkpoint": bool(checkpoint_validation.get("bind_ok")),
            "source_completion_checkpoint": bool(checkpoint_validation.get("source_completion_ok")),
            "final_completion_checkpoint": bool(checkpoint_validation.get("final_completion_ok")),
            "checkpoint_order": bool(checkpoint_validation.get("ordered_ok")),
            # Do not trust ``quiescence_evidence`` or the boolean summary in
            # the report; this is derived only from the durable history.
            "quiescence": evidence["quiescence_ok"],
            "required_evidence_persisted": all((
                evidence["events_ok"], evidence["transitions_ok"], evidence["topology_ok"],
                evidence["h2d_ok"], evidence["provenance_ok"],
                bool(checkpoint_validation.get("history_ok")),
            )),
        }
        failed = [name for name in PREDICATES if not predicates[name]]
        emitted_line = f"E27_SOURCE_MECHANISM_PROVEN={'YES' if not failed else 'NO'}"
        return {
            "proven": not failed,
            "emitted_line": emitted_line,
            "line": emitted_line,
            "E27_SOURCE_MECHANISM_PROVEN": "YES" if not failed else "NO",
            "predicates": predicates,
            "failed_predicates": failed,
            "report": report,
        }
    except BaseException:
        # The evaluator is an input boundary.  Even hostile Mapping objects
        # and unexpected scalar types must produce a machine-readable NO.
        predicates = {name: False for name in PREDICATES}
        return {
            "proven": False,
            "emitted_line": "E27_SOURCE_MECHANISM_PROVEN=NO",
            "line": "E27_SOURCE_MECHANISM_PROVEN=NO",
            "E27_SOURCE_MECHANISM_PROVEN": "NO",
            "predicates": predicates,
            "failed_predicates": list(PREDICATES),
            "report": {},
        }


SourceMechanismTelemetry = ActualSourceTelemetry
E27SourceMechanism = ActualSourceTelemetry


__all__ = [
    "ActualSourceTelemetry", "SourceMechanismTelemetry", "E27SourceMechanism",
    "SourceReadEvent", "SourceTransition", "evaluate_e27_source_mechanism",
]
