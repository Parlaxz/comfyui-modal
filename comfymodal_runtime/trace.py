"""One event trace with temporary legacy serializers."""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from .contracts import TraceEvent, stable_hash


PROCESS_LOCAL = "local"
PROCESS_PUBLISHER = "publisher"
PROCESS_REMOTE_LIFECYCLE = "remote_lifecycle"
PROCESS_REMOTE_METHOD = "remote_method"


_LEGACY_STAGE_NAMES = {
    "local_request_received": "t1_local_recv",
    "plan_build_start": "t2_local_dispatch",
    "modal_submit_start": "t2c_modal_call_start",
    "container_entry": "t3_modal_entry",
    "graph_execution_start": "t3d_prompt_start",
    "prompt_executor_start": "t3e_execution_start",
    "unet_prepare_start": "t4b_unet_load_start",
    "unet_prepare_end": "t4b_unet_load_end",
    "clip_prepare_start": "t4_clip_load_start",
    "clip_prepare_end": "t4_clip_load_end",
    "prefill_start": "t5_text_encode_start",
    "prefill_end": "t5_text_encode_end",
    "sampler_start": "t6_sampler_start",
    "sampler_end": "t6_sampler_end",
    "vae_decode_start": "t7_vae_decode_start",
    "vae_decode_end": "t7_vae_decode_end",
    "output_collect_start": "t7b_collect_start",
    "output_collect_end": "t8b_outputs_collected",
    "remote_return_start": "t9_modal_return",
    "local_result_received": "t9b_local_result_received",
    "local_materialize_start": "t9e_local_materialize_start",
    "local_materialize_end": "t10_local_materialized",
    "ui_response_start": "t10d_local_response_sent",
}


class RuntimeTrace:
    """Collects `TraceEvent` values and emits old timing shapes temporarily."""

    def __init__(
        self,
        *,
        request_id: str = "",
        container_session_id: str = "",
        process: str = "local",
        trace_id: str = "",
    ) -> None:
        self.request_id = request_id
        self.container_session_id = container_session_id
        self.process = process
        self.trace_id = trace_id or uuid.uuid4().hex[:16]
        self._events: list[TraceEvent] = []
        self._started_ns: dict[str, int] = {}
        self._metadata: dict[str, Any] = {}

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(self._events)

    def emit(
        self,
        name: str,
        *,
        process: str | None = None,
        phase: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> TraceEvent:
        event = TraceEvent.now(
            name,
            process=process or self.process,
            phase=phase,
            request_id=self.request_id,
            container_session_id=self.container_session_id,
            metadata=metadata or {},
        )
        self._events.append(event)
        return event

    def begin(self, name: str, **metadata: Any) -> TraceEvent:
        event = self.emit(name, metadata=metadata)
        self._started_ns[name] = event.monotonic_ns
        return event

    def end(self, name: str, **metadata: Any) -> TraceEvent:
        event = self.emit(f"{name}_end", metadata=metadata)
        self._started_ns.pop(name, None)
        return event

    def set_metadata(self, **metadata: Any) -> None:
        self._metadata.update(metadata)

    def extend(self, values: Iterable[TraceEvent]) -> None:
        self._events.extend(values)

    @contextmanager
    def span(self, name: str, **metadata: Any) -> Iterator[None]:
        self.begin(name, **metadata)
        try:
            yield
        finally:
            self.end(name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "container_session_id": self.container_session_id,
            "events": [event.to_dict() for event in self._events],
            "metadata": dict(self._metadata),
        }

    def to_legacy_timing(self, *, prompt_id: str = "") -> dict[str, Any]:
        stages: dict[str, float] = {}
        for event in self._events:
            legacy_name = _LEGACY_STAGE_NAMES.get(event.name)
            if legacy_name:
                stages[legacy_name] = event.wall_unix_ns / 1_000_000_000
        return {
            "prompt_id": prompt_id or self.request_id,
            "trace_version": "2.0.0",
            "stages": stages,
            "events": [event.to_dict() for event in self._events],
            "metadata": dict(self._metadata),
        }

    @classmethod
    def from_legacy(
        cls,
        value: Mapping[str, Any],
        *,
        request_id: str = "",
        container_session_id: str = "",
    ) -> "RuntimeTrace":
        trace = cls(
            request_id=request_id or str(value.get("prompt_id", "")),
            container_session_id=container_session_id,
            process="legacy",
            trace_id=str(value.get("trace_id", "")),
        )
        events = value.get("events")
        if isinstance(events, list):
            trace.extend(TraceEvent.from_dict(event) for event in events if isinstance(event, Mapping))
        stages = value.get("stages")
        reverse = {legacy: name for name, legacy in _LEGACY_STAGE_NAMES.items()}
        if isinstance(stages, Mapping):
            for legacy_name, timestamp in stages.items():
                if legacy_name not in reverse or not isinstance(timestamp, (int, float)):
                    continue
                trace._events.append(
                    TraceEvent(
                        name=reverse[legacy_name],
                        process="legacy",
                        phase="timing_trace",
                        wall_unix_ns=int(float(timestamp) * 1_000_000_000),
                        monotonic_ns=0,
                        request_id=trace.request_id,
                        container_session_id=container_session_id,
                    )
                )
        metadata = value.get("metadata")
        if isinstance(metadata, Mapping):
            trace.set_metadata(**dict(metadata))
        return trace

    def durations_ms(self) -> dict[str, float]:
        starts: dict[str, int] = {}
        durations: dict[str, float] = {}
        for event in self._events:
            if event.name.endswith("_start"):
                starts[event.name[:-6]] = event.monotonic_ns
            elif event.name.endswith("_end"):
                key = event.name[:-4]
                start = starts.get(key)
                if start and event.monotonic_ns >= start:
                    durations[key] = round((event.monotonic_ns - start) / 1_000_000, 2)
        return durations

    def export_phase_durations(self) -> dict[str, float]:
        """Explicit span durations from paired ``_start``/``_end`` events.

        Only phases where both a ``_start`` and ``_end`` event exist in this
        trace are included.  Durations are computed from the monotonic clock
        delta of the paired events — no subtraction-based ownership inference
        across spans, and overlapping spans are reported independently (the
        map is not a partition of wall time).
        """
        return self.durations_ms()


def merge_runtime_traces(*values: RuntimeTrace | Mapping[str, Any] | None) -> RuntimeTrace:
    """Merge local and remote traces without losing process evidence.

    Mapping inputs are normalized through the legacy serializer first. Exact
    duplicate events are removed, metadata is merged in input order (so a
    later remote payload can supply authoritative derived fields), and the
    resulting event list is sorted by wall time for display. Monotonic clocks
    are never compared across processes.
    """
    result = RuntimeTrace(process="merged")
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, RuntimeTrace):
            normalized = value
        elif isinstance(value, Mapping):
            normalized = RuntimeTrace.from_legacy(value)
        else:
            continue

        if not result.request_id and normalized.request_id:
            result.request_id = normalized.request_id
        if not result.container_session_id and normalized.container_session_id:
            result.container_session_id = normalized.container_session_id
        result.set_metadata(**normalized._metadata)
        for event in normalized.events:
            identity = stable_hash(event.to_dict())
            if identity in seen:
                continue
            seen.add(identity)
            result._events.append(event)

    result._events.sort(key=lambda event: event.wall_unix_ns)
    return result


def merge_traces(*values: RuntimeTrace | Mapping[str, Any] | None) -> RuntimeTrace:
    """Compatibility alias for the unified trace merge implementation."""
    return merge_runtime_traces(*values)
