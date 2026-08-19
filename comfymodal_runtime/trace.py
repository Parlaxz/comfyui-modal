"""One event trace with temporary legacy serializers."""

from __future__ import annotations

import time
import uuid
import os
import threading
from dataclasses import replace
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
    "output_persist_start": "t8bb_persist_start",
    "output_persist_end": "t8bb_persist_end",
    "output_encode_start": "t8c_output_encode_start",
    "output_encode_end": "t8c_output_encode_end",
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
        self._last_emitted_mono_ns = 0
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
        event_metadata = dict(metadata or {})
        event_metadata.setdefault("trace_id", self.trace_id)
        event_metadata.setdefault("pid", os.getpid())
        try:
            event_metadata.setdefault("thread_native_id", threading.get_native_id())
        except Exception:
            pass
        for key in (
            "restored_instance_id",
            "restore_session_id",
            "legacy_container_session_id",
            "container_task_id",
            "modal_input_id",
            "image_id",
            "cloud",
            "region",
            "app_name",
            "class_name",
            "method_name",
            "workflow_hash_prefix",
            "restore_plan_generation",
            "lane",
            "canonical_key_hash",
            "diagnostic_id",
        ):
            if key in self._metadata:
                event_metadata.setdefault(key, self._metadata[key])
        if "canonical_key_hash" not in event_metadata and "canonical_key" in event_metadata:
            event_metadata["canonical_key_hash"] = stable_hash(str(event_metadata["canonical_key"]))[:16]
        event = TraceEvent.now(
            name,
            process=process or self.process,
            phase=phase,
            request_id=self.request_id,
            container_session_id=self.container_session_id,
            trace_id=self.trace_id,
            metadata=event_metadata,
        )
        if event.monotonic_ns <= self._last_emitted_mono_ns:
            event = replace(event, monotonic_ns=self._last_emitted_mono_ns + 1)
        self._last_emitted_mono_ns = event.monotonic_ns
        self._events.append(event)
        return event

    def emit_at(
        self,
        name: str,
        *,
        wall_unix_ns: int,
        monotonic_ns: int = 0,
        process: str | None = None,
        phase: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> TraceEvent:
        """Append an event whose timestamp was captured at another boundary.

        Preserves the supplied timestamps exactly — does not mix clock domains.
        ``wall_unix_ns`` is for cross-process correlation; ``monotonic_ns`` is
        for same-process duration calculations.
        """
        event_metadata = dict(metadata or {})
        event_metadata.setdefault("trace_id", self.trace_id)
        event_metadata.setdefault("pid", os.getpid())
        try:
            event_metadata.setdefault("thread_native_id", threading.get_native_id())
        except Exception:
            pass
        for key in (
            "restored_instance_id",
            "restore_session_id",
            "legacy_container_session_id",
            "container_task_id",
            "modal_input_id",
            "image_id",
            "cloud",
            "region",
            "app_name",
            "class_name",
            "method_name",
            "workflow_hash_prefix",
            "restore_plan_generation",
            "lane",
            "canonical_key_hash",
            "diagnostic_id",
        ):
            if key in self._metadata:
                event_metadata.setdefault(key, self._metadata[key])
        if "canonical_key_hash" not in event_metadata and "canonical_key" in event_metadata:
            event_metadata["canonical_key_hash"] = stable_hash(str(event_metadata["canonical_key"]))[:16]
        event_metadata.setdefault("clock_scope", "cross_process")
        event_metadata.setdefault("clock_precision", "wall_clock")
        event = TraceEvent(
            name=name,
            process=process or self.process,
            phase=phase,
            wall_unix_ns=int(wall_unix_ns),
            monotonic_ns=int(monotonic_ns),
            request_id=self.request_id,
            container_session_id=self.container_session_id,
            trace_id=self.trace_id,
            metadata=event_metadata,
        )
        if event.process == self.process:
            self._last_emitted_mono_ns = max(
                self._last_emitted_mono_ns,
                event.monotonic_ns,
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
    resulting event list is sorted by wall_unix_ns for display.

    IMPORTANT: monotonic_ns values are only valid for same-process duration
    calculations (they come from ``time.monotonic_ns()`` which has no meaning
    across processes). Wall_unix_ns (from ``time.time_ns()``) is used for
    cross-process correlation only. The sort key is wall_unix_ns, not
    monotonic_ns.
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


# ---------------------------------------------------------------------------
# Local submission breakdown helper
# ---------------------------------------------------------------------------

_ABSENT_STR = "absent"
_INVALID_NEG_STR = "invalid_negative"


def _event_mono_ns(trace: RuntimeTrace, name: str) -> int | None:
    """Return the monotonic_ns of the first event with *name*, or None."""
    for event in trace.events:
        if event.name == name:
            return event.monotonic_ns
    return None


def _strict_event_span_ms(trace: RuntimeTrace, start_name: str, end_name: str) -> float | str | None:
    """Like _event_span_ms but returns _INVALID_NEG_STR for negative durations.
    Returns None when missing, _INVALID_NEG_STR when start > end, float otherwise."""
    start_ns: int | None = None
    for event in trace.events:
        if event.name == start_name:
            start_ns = event.monotonic_ns
        elif event.name == end_name and start_ns is not None:
            delta = event.monotonic_ns - start_ns
            if delta < 0:
                return _INVALID_NEG_STR
            return round(delta / 1_000_000, 3)
    return None


def _derived_mono_delta_ms(trace: RuntimeTrace, start_name: str, end_name: str) -> float | str | None:
    """Compute ``end_name - start_name`` in ms using monotonic timestamps.
    Returns ``None`` when either event is missing, ``"invalid_negative"`` when
    the delta is negative, otherwise the non-negative float ms."""
    start_ns = _event_mono_ns(trace, start_name)
    end_ns = _event_mono_ns(trace, end_name)
    if start_ns is None or end_ns is None:
        return None
    delta = end_ns - start_ns
    if delta < 0:
        return _INVALID_NEG_STR
    return round(delta / 1_000_000, 3)


# ---------------------------------------------------------------------------
# Canonical field map for local_submission_breakdown
# ---------------------------------------------------------------------------
# One map used by both local and remote emitters so field names never diverge.

LOCAL_SUBMISSION_FIELD_KEYS: tuple[tuple[str, str], ...] = (
    ("request_id",                          "request_id"),
    ("local_receive_to_worker_start_ms",    "local_receive_to_worker_start_ms"),
    ("worker_start_to_normalize_start_ms",  "worker_start_to_normalize_start_ms"),
    ("normalize_production_options_ms",     "normalize_production_options_ms"),
    ("normalize_end_to_trace_construct_start_ms", "normalize_end_to_trace_construct_start_ms"),
    ("runtime_trace_construct_ms",          "runtime_trace_construct_ms"),
    ("trace_construct_to_options_copy_start_ms", "trace_construct_to_options_copy_start_ms"),
    ("benchmark_options_copy_ms",           "benchmark_options_copy_ms"),
    ("options_copy_to_client_id_start_ms",  "options_copy_to_client_id_start_ms"),
    ("client_id_generation_ms",             "client_id_generation_ms"),
    ("client_id_end_to_plan_call_ms",       "client_id_end_to_plan_call_ms"),
    ("plan_call_to_function_entry_ms",      "plan_call_to_function_entry_ms"),
    ("worker_start_to_plan_build_ms",       "worker_start_to_plan_build_ms"),
    ("local_receive_to_plan_build_start_ms","local_receive_to_plan_build_start_ms"),
    ("worker_queue_ms",                     "worker_queue_ms"),
    ("plan_build_ms",                 "plan_build_ms"),
    ("plan_build_to_execute_plan_entry_ms", "plan_build_to_execute_plan_entry_ms"),
    ("execute_plan_entry_to_plan_materialization_ms", "execute_plan_entry_to_plan_materialization_ms"),
    ("plan_materialization_ms",       "plan_materialization_ms"),
    ("plan_materialization_to_active_profile_ms", "plan_materialization_to_active_profile_ms"),
    ("active_profile_ms",             "active_profile_ms"),
    ("restore_plan_build_ms",         "restore_plan_build_ms"),
    ("restore_publish_ms",            "restore_publish_ms"),
    ("restore_publish_to_transport_entry_ms", "restore_publish_to_transport_entry_ms"),
    ("transport_entry_to_handle_lookup_ms", "transport_entry_to_handle_lookup_ms"),
    ("handle_lookup_ms",              "handle_lookup_ms"),
    ("payload_materialization_ms",    "payload_materialization_ms"),
    ("payload_size_measurement_ms",   "payload_size_measurement_ms"),
    ("payload_size_to_serialize_end_ms", "payload_size_to_serialize_end_ms"),
    ("payload_ready_to_modal_call_ms","payload_ready_to_modal_call_ms"),
    ("local_receive_to_modal_call_ms","local_receive_to_modal_call_ms"),
    ("generator_create_ms",           "generator_create_ms"),
    ("generator_created_to_first_iteration_ms", "generator_created_to_first_iteration_ms"),
    ("local_receive_to_actual_submission_ms", "local_receive_to_actual_submission_ms"),
    ("measured_children_ms",          "measured_children_ms"),
    ("residual_ms",                   "residual_ms"),
    ("reconciliation_status",         "reconciliation_status"),
    ("profile_cache_hit",             "profile_cache_hit"),
    ("profile_remote_call_performed", "profile_remote_call_performed"),
    ("profile_checker_matched",       "profile_checker_matched"),
    ("restore_publish_cache_hit",     "restore_publish_cache_hit"),
    ("restore_remote_call_performed", "restore_remote_call_performed"),
    ("handle_cache_hit",              "handle_cache_hit"),
    ("plan_to_dict_count",            "plan_to_dict_count"),
    ("payload_bytes",                 "payload_bytes"),
    # Active-profile timing decomposition (blended into local stage)
    ("active_profile_local_ms",       "active_profile_local_ms"),
    ("active_profile_cache_lookup_ms","active_profile_cache_lookup_ms"),
    ("active_profile_checker_ms",     "active_profile_checker_ms"),
    ("active_profile_setter_ms",      "active_profile_setter_ms"),
    ("active_profile_total_ms",       "active_profile_total_ms"),
    # Handle resolution booleans
    ("created_modal_client",          "created_modal_client"),
    ("performed_cls_from_name",       "performed_cls_from_name"),
    ("constructed_instance",          "constructed_instance"),
    # Payload / workflow metadata
    ("input_image_count",             "input_image_count"),
    ("workflow_node_count",           "workflow_node_count"),
    # Large-residual diagnostic
    ("unmeasured_boundary",           "unmeasured_boundary"),
)
"""Canonical ordered field list for [v2.local_submission_breakdown].
Each entry is (dict_key, fmt_key) where fmt_key is the printed field name."""

# Compact breakdown mode.  Set COMFYMODAL_V2_COMPACT_BREAKDOWN=1 to print only
# the present (non-None) fields plus absent_count=N instead of every field with
# "absent".  Default off keeps the historical all-fields-with-absent rendering
# that the pinned tests rely on.
_COMPACT_BREAKDOWN: bool = (
    os.environ.get("COMFYMODAL_V2_COMPACT_BREAKDOWN", "").strip().lower()
    in {"1", "true", "yes", "on"}
)

# Sane one-line cap for compact breakdown output (safety net for very wide
# breakdown dicts such as the host-side final line with ~63 fields).
_COMPACT_BREAKDOWN_MAX_LINE_CHARS = 4096


def _fmt_or_absent(v: Any) -> str:
    """Format a value for one-line summary: numeric values (including 0.0)
    are returned as str(v), None/"absent"/"invalid_negative" as-is."""
    if v is None:
        return _ABSENT_STR
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return str(v)
    return str(v)


def _emit_breakdown_line(prefix: str, breakdown: dict[str, Any],
                         field_keys: tuple[tuple[str, str], ...] | None = None) -> None:
    """Print one canonical breakdown line using *prefix* and *field_keys*.

    When *field_keys* is None, uses LOCAL_SUBMISSION_FIELD_KEYS.
    Default (COMFYMODAL_V2_COMPACT_BREAKDOWN unset) prints every field with
    ``absent`` for missing values, exactly one line.  In compact mode only
    present (non-None) fields are printed plus ``absent_count=N``; the line
    still starts with the same prefix, keeps field ordering (request_id
    first), is exactly one line, and is capped at a sane length.
    """
    keys = field_keys if field_keys is not None else LOCAL_SUBMISSION_FIELD_KEYS
    parts = [f"{prefix}"]
    absent_count = 0
    for dk, fk in keys:
        v = breakdown.get(dk)
        if v is not None:
            parts.append(f"{fk}={_fmt_or_absent(v)}")
        elif not _COMPACT_BREAKDOWN:
            parts.append(f"{fk}={_ABSENT_STR}")
        else:
            absent_count += 1
    if _COMPACT_BREAKDOWN:
        parts.append(f"absent_count={absent_count}")
    _line = " ".join(parts)
    if _COMPACT_BREAKDOWN and len(_line) > _COMPACT_BREAKDOWN_MAX_LINE_CHARS:
        _line = _line[:_COMPACT_BREAKDOWN_MAX_LINE_CHARS - 3] + "..."
    print(_line, flush=True)


def _build_local_submission_breakdown(
    trace: RuntimeTrace,
    *,
    origin: Mapping[str, Any] | None = None,
    transport_meta: Mapping[str, Any] | None = None,
    plan_to_dict_count: int = 1,
) -> dict[str, Any]:
    """Build the [v2.local_submission_breakdown] dict from trace events.

    Extracts stage durations from RuntimeTrace events and metadata from
    *origin* (request_origin_info) and *transport_meta* (trace._metadata).
    Missing values render as *abs_str*. Negative deltas render as
    *invalid_neg_str*.

    This function computes whatever is available — callers that emit before
    the Modal generator is created will see generator/timing fields as
    "absent".  Callers that emit after the full flow see all fields.
    """
    _origin = dict(origin or {})
    _transport_meta = dict(transport_meta or {})
    _ABS = _ABSENT_STR
    _INV = _INVALID_NEG_STR
    _ld = lambda s, e: _derived_mono_delta_ms(trace, s, e)

    # ── Shorthand: value or absent ──
    def _val(v: Any) -> Any:
        return _ABS if v is None else v

    # ── Reference monotonic timestamps ──
    _ref_mono_local_receive = _origin.get("local_receive_mono_ns")
    _ref_mono_worker_start = _event_mono_ns(trace, "worker_start")
    _ref_mono_submission = _event_mono_ns(trace, "modal_submission_attempt")

    # ── One-stage durations ──
    _plan_build_ms = _strict_event_span_ms(trace, "plan_build_start", "plan_build_end")
    _active_profile_ms = _strict_event_span_ms(trace,
                                                "active_profile_prepare_start",
                                                "active_profile_prepare_end")
    _restore_plan_build_ms = _strict_event_span_ms(trace,
                                                    "restore_plan_build_start",
                                                    "restore_plan_build_end")
    _restore_publish_ms = _strict_event_span_ms(trace,
                                                 "restore_plan_publish_start",
                                                 "restore_plan_publish_end")
    _handle_lookup_ms = _strict_event_span_ms(trace,
                                               "modal_handle_lookup_start",
                                               "modal_handle_lookup_end")

    # Payload stages
    _payload_materialization_prep_ms = _ld("modal_payload_serialize_start",
                                            "payload_measure_size_start")
    _payload_size_measurement_ms = _ld("payload_measure_size_start",
                                        "payload_measure_size_end")
    _payload_size_to_serialize_end_ms = _ld("payload_measure_size_end",
                                             "modal_payload_serialize_end")

    # ── Derived gap durations ──
    _restore_pub_to_transport_entry_ms = _ld("restore_plan_publish_end",
                                              "transport_entry")
    _transport_entry_to_handle_lookup_ms = _ld("transport_entry",
                                                "modal_handle_lookup_start")
    _transport_entry_ms = _transport_entry_to_handle_lookup_ms
    _payload_ready_to_gen_create_ms = _ld("modal_payload_serialize_end",
                                           "modal_generator_create_start")
    _generator_create_ms = _ld("modal_generator_create_start",
                                "modal_generator_created")
    _gen_created_to_first_iter_ms = _ld("modal_generator_created",
                                         "modal_first_iteration_start")

    # Plan materialization stages
    _plan_materialization_ms = _ld("plan_materialization_start",
                                    "plan_materialization_end")

    # ── Gap stages in worker→plan→execute→materialize→profile sequence ──
    _plan_build_to_exec_entry_ms = _ld("plan_build_end", "execute_plan_entry")
    _exec_entry_to_plan_mat_ms = _ld("execute_plan_entry",
                                      "plan_materialization_start")
    _plan_mat_to_active_profile_ms = _ld("plan_materialization_end",
                                          "active_profile_prepare_start")

    # ── Boundary-anchored durations ──
    _local_receive_to_worker_start_ms: Any = _ABS
    if isinstance(_ref_mono_local_receive, int) and isinstance(_ref_mono_worker_start, int):
        _delta = _ref_mono_worker_start - _ref_mono_local_receive
        if _delta < 0:
            _local_receive_to_worker_start_ms = _INV
        else:
            _local_receive_to_worker_start_ms = round(_delta / 1_000_000, 3)

    _worker_start_to_plan_build_ms: Any = _ABS
    if isinstance(_ref_mono_worker_start, int):
        _ref_mono_plan_build_start = _event_mono_ns(trace, "plan_build_start")
        if isinstance(_ref_mono_plan_build_start, int):
            _delta = _ref_mono_plan_build_start - _ref_mono_worker_start
            if _delta < 0:
                _worker_start_to_plan_build_ms = _INV
            else:
                _worker_start_to_plan_build_ms = round(_delta / 1_000_000, 3)
    _worker_queue_ms = _worker_start_to_plan_build_ms

    # ── Benchmark prefix stages (decompose worker_start→plan_build_start) ──
    # ── Benchmark prefix stages (non-overlapping partition: ws→norm_start→norm_end→
    #    rtc_start→rtc_end→bc_start→bc_end→cid_start→cid_end→bep_call→plan_build_start) ──
    _normalize_production_options_ms = _strict_event_span_ms(trace,
        "normalize_production_options_start", "normalize_production_options_end")
    _benchmark_options_copy_ms = _strict_event_span_ms(trace,
        "benchmark_options_copy_start", "benchmark_options_copy_end")
    _client_id_generation_ms = _strict_event_span_ms(trace,
        "client_id_generation_start", "client_id_generation_end")
    _plan_call_to_func_entry_ms = _derived_mono_delta_ms(trace,
        "build_execution_plan_call_start", "plan_build_start")

    # Gap fields: each is the delta between consecutive prefix boundaries.
    # These form a strict non-overlapping partition of ws→plan_build_start.
    _worker_start_to_normalize_start_ms = _derived_mono_delta_ms(trace,
        "worker_start", "normalize_production_options_start")
    _normalize_end_to_trace_construct_start_ms = _derived_mono_delta_ms(trace,
        "normalize_production_options_end", "runtime_trace_construct_start")
    _runtime_trace_construct_ms = _derived_mono_delta_ms(trace,
        "runtime_trace_construct_start", "trace_construct_end")
    _trace_construct_to_options_copy_start_ms = _derived_mono_delta_ms(trace,
        "trace_construct_end", "benchmark_options_copy_start")
    _options_copy_to_client_id_start_ms = _derived_mono_delta_ms(trace,
        "benchmark_options_copy_end", "client_id_generation_start")
    _client_id_end_to_plan_call_ms = _derived_mono_delta_ms(trace,
        "client_id_generation_end", "build_execution_plan_call_start")

    # Total: local_receive → plan_build_start
    _local_receive_to_plan_build_start_ms: Any = _ABS
    if isinstance(_ref_mono_local_receive, int):
        _ref_mono_plan_bs = _event_mono_ns(trace, "plan_build_start")
        if isinstance(_ref_mono_plan_bs, int):
            _delta = _ref_mono_plan_bs - _ref_mono_local_receive
            if _delta < 0:
                _local_receive_to_plan_build_start_ms = _INV
            else:
                _local_receive_to_plan_build_start_ms = round(_delta / 1_000_000, 3)

    # ── Total span: local_receive→submission ──
    _total_ms: Any = _ABS
    if isinstance(_ref_mono_local_receive, int) and isinstance(_ref_mono_submission, int):
        _delta = _ref_mono_submission - _ref_mono_local_receive
        if _delta < 0:
            _total_ms = _INV
        else:
            _total_ms = round(_delta / 1_000_000, 3)

    # local_receive → generator_create_start (modal_call)
    _ref_mono_modal_call = _event_mono_ns(trace, "modal_generator_create_start")
    _local_receive_to_modal_call_ms: Any = _ABS
    if isinstance(_ref_mono_local_receive, int) and isinstance(_ref_mono_modal_call, int):
        _delta = _ref_mono_modal_call - _ref_mono_local_receive
        if _delta < 0:
            _local_receive_to_modal_call_ms = _INV
        else:
            _local_receive_to_modal_call_ms = round(_delta / 1_000_000, 3)

    # ── Measured children: sum of all valid sequential non-overlapping stages ──
    # After first iterator submission this is rebuilt from the live local trace
    # (not pre-dispatch data) so the final reconciliation is complete.
    # Prefix stage fields (benchmark) replace the coarse worker_start_to_plan_build_ms
    # when detailed events exist; when absent the coarse field is used.
    _prefix_keys = [
        ("worker_start_to_normalize_start_ms", _worker_start_to_normalize_start_ms),
        ("normalize_production_options_ms", _normalize_production_options_ms),
        ("normalize_end_to_trace_construct_start_ms", _normalize_end_to_trace_construct_start_ms),
        ("runtime_trace_construct_ms", _runtime_trace_construct_ms),
        ("trace_construct_to_options_copy_start_ms", _trace_construct_to_options_copy_start_ms),
        ("benchmark_options_copy_ms", _benchmark_options_copy_ms),
        ("options_copy_to_client_id_start_ms", _options_copy_to_client_id_start_ms),
        ("client_id_generation_ms", _client_id_generation_ms),
        ("client_id_end_to_plan_call_ms", _client_id_end_to_plan_call_ms),
        ("plan_call_to_function_entry_ms", _plan_call_to_func_entry_ms),
    ]
    _has_prefix_stages = any(
        isinstance(v, (int, float)) for _, v in _prefix_keys
    )
    _child_keys = [
        ("local_receive_to_worker_start_ms", _local_receive_to_worker_start_ms),
    ]
    if _has_prefix_stages:
        _child_keys.extend(_prefix_keys)
    else:
        _child_keys.append(("worker_start_to_plan_build_ms", _worker_start_to_plan_build_ms))
    _child_keys.extend([
        ("plan_build_ms", _plan_build_ms),
        ("plan_build_to_execute_plan_entry_ms", _plan_build_to_exec_entry_ms),
        ("execute_plan_entry_to_plan_materialization_ms", _exec_entry_to_plan_mat_ms),
        ("plan_materialization_ms", _plan_materialization_ms),
        ("plan_materialization_to_active_profile_ms", _plan_mat_to_active_profile_ms),
        ("active_profile_ms", _active_profile_ms),
        ("restore_plan_build_ms", _restore_plan_build_ms),
    ])
    # The restore-publish span is part of the sequential child accounting ONLY
    # when a publish was actually attempted (its start/end events exist).  On
    # the default no-publish path (COMFYMODAL_V2_PUBLISH_RESTORE_PLAN disabled)
    # execute_plan emits ``restore_publish_skipped`` and no
    # ``restore_plan_publish_start/end`` events, so ``restore_publish_ms`` and
    # ``restore_publish_to_transport_entry_ms`` render absent and are excluded
    # from the measured-children sum — the (zero) publish gap lands in the
    # residual and reconciliation stays complete.
    if _event_mono_ns(trace, "restore_plan_publish_start") is not None:
        _child_keys.extend([
            ("restore_publish_ms", _restore_publish_ms),
            ("restore_publish_to_transport_entry_ms", _restore_pub_to_transport_entry_ms),
        ])
    _child_keys.extend([
        ("transport_entry_to_handle_lookup_ms", _transport_entry_to_handle_lookup_ms),
        ("handle_lookup_ms", _handle_lookup_ms),
        ("payload_materialization_ms", _payload_materialization_prep_ms),
        ("payload_size_measurement_ms", _payload_size_measurement_ms),
        ("payload_size_to_serialize_end_ms", _payload_size_to_serialize_end_ms),
        ("payload_ready_to_modal_call_ms", _payload_ready_to_gen_create_ms),
        ("generator_create_ms", _generator_create_ms),
        ("generator_created_to_first_iteration_ms", _gen_created_to_first_iter_ms),
    ])
    _measured_children_ms: Any = _ABS
    _all_numeric = True
    _child_sum = 0.0
    for _ck, _cv in _child_keys:
        if isinstance(_cv, (int, float)):
            _child_sum += float(_cv)
        else:
            _all_numeric = False
    if _all_numeric:
        _measured_children_ms = round(_child_sum, 3)

    # ── Residual ──
    _residual_ms: Any = _ABS
    if isinstance(_total_ms, (int, float)) and _all_numeric:
        _residual_val = _total_ms - _child_sum
        _residual_ms = round(_residual_val, 3)

    # ── Reconciliation status ──
    _reconciliation_status: str = "complete"
    if not isinstance(_total_ms, (int, float)):
        _reconciliation_status = "incomplete"
    elif not isinstance(_measured_children_ms, (int, float)):
        _reconciliation_status = "incomplete"
    elif isinstance(_residual_ms, (int, float)) and _residual_ms < -0.001:
        _reconciliation_status = "overlap"
    for _ck, _cv in _child_keys:
        if _cv == _INV:
            _reconciliation_status = "overlap"
            break

    # ── Extract booleans from transport_meta ──
    _performed_remote_setter_call: Any = None
    _used_existing_stable_profile: Any = None
    _rebuilt_profile_locally: Any = None
    _ap_decision = _transport_meta.get("active_profile_publish_decision", "")
    _remote_call_count = _transport_meta.get("active_profile_remote_call", 0)
    if _ap_decision:
        _performed_remote_setter_call = bool(_remote_call_count)
        _used_existing_stable_profile = _ap_decision in ("stable_key_exists", "stable_found", "stable_key_found")
        _rebuilt_profile_locally = _ap_decision in ("rebuilt", "rebuilt_locally", "rebuilt_profile")
    _remote_call_performed = bool(_remote_call_count) if _ap_decision else None

    _hit_restore_publish_cache: Any = None
    _performed_remote_publish: Any = None
    _rpc_skipped = _transport_meta.get("restore_publish_cache_skipped")
    if isinstance(_rpc_skipped, bool):
        _hit_restore_publish_cache = bool(_rpc_skipped)
        _performed_remote_publish = not bool(_rpc_skipped)

    _has_cache_hit_event = any(e.name == "handle_cache_hit" for e in trace.events)
    _has_cache_miss_event = any(e.name == "handle_cache_miss" for e in trace.events)
    if _has_cache_hit_event:
        _hit_handle_cache = True
    elif _has_cache_miss_event:
        _hit_handle_cache = False
    else:
        _hit_handle_cache = None

    # Handle resolution booleans from transport events
    _created_client = any(e.name == "client_resolution_start" for e in trace.events)
    _performed_cls = any(e.name == "class_lookup_start" for e in trace.events)
    _constructed_instance = any(e.name == "instance_construction_start" for e in trace.events)

    _payload_bytes = _transport_meta.get("payload_bytes") or _transport_meta.get("modal_payload_serialize_bytes")

    # ── unmeasured_boundary = diagnostic when residual > 100ms ──
    _unmeasured_boundary: Any = _ABS
    if isinstance(_residual_ms, (int, float)) and _residual_ms > 100:
        _absent_for_boundary: list[str] = []
        for _ck, _cv in _child_keys:
            if not isinstance(_cv, (int, float)):
                _absent_for_boundary.append(str(_ck))
        if _absent_for_boundary:
            _unmeasured_boundary = ",".join(_absent_for_boundary)
        else:
            _unmeasured_boundary = "between_recorded_stages"

    return {
        # Required fields
        "request_id": _origin.get("request_id") or trace.request_id,
        "local_receive_to_worker_start_ms": _local_receive_to_worker_start_ms,
        "worker_start_to_normalize_start_ms": _worker_start_to_normalize_start_ms,
        "normalize_production_options_ms": _normalize_production_options_ms,
        "normalize_end_to_trace_construct_start_ms": _normalize_end_to_trace_construct_start_ms,
        "runtime_trace_construct_ms": _runtime_trace_construct_ms,
        "trace_construct_to_options_copy_start_ms": _trace_construct_to_options_copy_start_ms,
        "benchmark_options_copy_ms": _benchmark_options_copy_ms,
        "options_copy_to_client_id_start_ms": _options_copy_to_client_id_start_ms,
        "client_id_generation_ms": _client_id_generation_ms,
        "client_id_end_to_plan_call_ms": _client_id_end_to_plan_call_ms,
        "plan_call_to_function_entry_ms": _plan_call_to_func_entry_ms,
        "worker_start_to_plan_build_ms": _worker_start_to_plan_build_ms,
        "local_receive_to_plan_build_start_ms": _local_receive_to_plan_build_start_ms,
        "worker_queue_ms": _worker_queue_ms,
        "plan_build_ms": _plan_build_ms,
        "plan_build_to_execute_plan_entry_ms": _plan_build_to_exec_entry_ms,
        "execute_plan_entry_to_plan_materialization_ms": _exec_entry_to_plan_mat_ms,
        "plan_materialization_ms": _plan_materialization_ms,
        "plan_materialization_to_active_profile_ms": _plan_mat_to_active_profile_ms,
        "active_profile_ms": _active_profile_ms,
        "restore_plan_build_ms": _restore_plan_build_ms,
        "restore_publish_ms": _restore_publish_ms,
        "restore_publish_to_transport_entry_ms": _restore_pub_to_transport_entry_ms,
        "transport_entry_to_handle_lookup_ms": _transport_entry_to_handle_lookup_ms,
        "transport_entry_ms": _transport_entry_ms,
        "handle_lookup_ms": _handle_lookup_ms,
        "payload_materialization_ms": _payload_materialization_prep_ms,
        "payload_size_measurement_ms": _payload_size_measurement_ms,
        "payload_size_to_serialize_end_ms": _payload_size_to_serialize_end_ms,
        "payload_ready_to_modal_call_ms": _payload_ready_to_gen_create_ms,
        "local_receive_to_modal_call_ms": _local_receive_to_modal_call_ms,
        "generator_create_ms": _generator_create_ms,
        "generator_created_to_first_iteration_ms": _gen_created_to_first_iter_ms,
        "local_receive_to_actual_submission_ms": _total_ms,
        "measured_children_ms": _measured_children_ms,
        "residual_ms": _residual_ms,
        "reconciliation_status": _reconciliation_status,
        "profile_cache_hit": _transport_meta.get("profile_cache_hit"),
        "profile_remote_call_performed": _transport_meta.get("profile_remote_call_performed"),
        "profile_checker_matched": _transport_meta.get("profile_checker_matched"),
        "restore_publish_cache_hit": _hit_restore_publish_cache,
        "restore_remote_call_performed": _performed_remote_publish,
        "handle_cache_hit": _hit_handle_cache,
        "plan_to_dict_count": plan_to_dict_count,
        "payload_bytes": _payload_bytes,
        # Informative metadata (backward compat)
        "active_profile_publish_decision": _ap_decision,
        "active_profile_stable_key": _transport_meta.get("active_profile_stable_key", ""),
        "active_profile_token": _transport_meta.get("active_profile_token", ""),
        "local_active_profile_prepare_ms": _transport_meta.get("local_active_profile_prepare_ms"),
        "profile_cache_hit": _transport_meta.get("profile_cache_hit"),
        "profile_remote_call_performed": _transport_meta.get("profile_remote_call_performed"),
        "active_profile_remote_call": _remote_call_count,
        "active_profile_remote_ms": _transport_meta.get("active_profile_remote_ms"),
        "performed_remote_setter_call": _performed_remote_setter_call,
        "used_existing_stable_profile": _used_existing_stable_profile,
        "rebuilt_profile_locally": _rebuilt_profile_locally,
        "remote_call_performed": _remote_call_performed,
        "restore_publish_generation": (
            _transport_meta.get("restore_publish_result", {}).get("generation")
            if isinstance(_transport_meta.get("restore_publish_result"), dict) else None
        ),
        "restore_publish_cache_hit": _hit_restore_publish_cache,
        "restore_remote_call_performed": _performed_remote_publish,
        "handle_lookup_app_name": _transport_meta.get("handle_lookup_app_name", ""),
        "handle_lookup_class_name": _transport_meta.get("handle_lookup_class_name", ""),
        "handle_lookup_gpu": _transport_meta.get("handle_lookup_gpu", ""),
        "handle_cache_hit": _hit_handle_cache,
        "payload_bytes": _payload_bytes,
        "payload_serialized_bytes": _transport_meta.get("modal_payload_serialize_bytes"),
        "workflow_hash": _transport_meta.get("workflow_hash", ""),
        "input_image_count": _transport_meta.get("input_image_count", 0),
        "workflow_node_count": _transport_meta.get("workflow_node_count"),
        "plan_materialization_count": _transport_meta.get("plan_materialization_count"),
        "plan_to_dict_count": plan_to_dict_count,
        # Active-profile timing decomposition (truthful non-overlapping)
        "active_profile_local_ms": _transport_meta.get("active_profile_local_ms"),
        "active_profile_cache_lookup_ms": _transport_meta.get("active_profile_cache_lookup_ms"),
        "active_profile_checker_ms": _transport_meta.get("active_profile_checker_ms"),
        "active_profile_setter_ms": _transport_meta.get("active_profile_setter_ms"),
        "active_profile_total_ms": _transport_meta.get("active_profile_total_ms"),
        # Handle resolution booleans
        "created_modal_client": _created_client,
        "performed_cls_from_name": _performed_cls,
        "constructed_instance": _constructed_instance,
        # Large-residual diagnostic
        "unmeasured_boundary": _unmeasured_boundary,
    }


# ---------------------------------------------------------------------------
# Forensic interval registry (module-level, thread-safe)
# ---------------------------------------------------------------------------
# Shared cross-lane registry of named wall-clock intervals (JSON-safe values
# only).  Concurrent worker lanes (e.g. input-types warming, fastsafe UNET
# workers) register their scheduling/duration intervals here under a single
# module-level lock so other lanes can compute cross-thread overlap.

_FORENSIC_LOCK = threading.Lock()
_forensic_intervals: dict[str, dict[str, Any]] = {}


def register_forensic_interval(
    name: str,
    *,
    start_mono_ns: int,
    end_mono_ns: int,
    cpu_ms: float | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    """Store or replace one forensic interval entry under *name*.

    ``start_mono_ns``/``end_mono_ns`` are ``time.monotonic_ns()`` stamps;
    ``cpu_ms`` is the optional thread-CPU duration; ``metadata`` is copied so
    later caller-side mutations cannot corrupt the stored record.  All values
    are JSON-safe.
    """
    with _FORENSIC_LOCK:
        _forensic_intervals[name] = {
            "start_mono_ns": int(start_mono_ns),
            "end_mono_ns": int(end_mono_ns),
            "cpu_ms": cpu_ms,
            "metadata": dict(metadata or {}),
        }


def forensic_intervals() -> dict[str, dict[str, Any]]:
    """Return a deep-enough copy (dict + inner dict) of all entries."""
    with _FORENSIC_LOCK:
        return {
            _name: {
                "start_mono_ns": _record["start_mono_ns"],
                "end_mono_ns": _record["end_mono_ns"],
                "cpu_ms": _record.get("cpu_ms"),
                "metadata": dict(_record.get("metadata") or {}),
            }
            for _name, _record in _forensic_intervals.items()
        }


def forensic_overlap_ms(
    a_start_mono_ns: int,
    a_end_mono_ns: int,
    b_start_mono_ns: int,
    b_end_mono_ns: int,
) -> float:
    """Overlap in milliseconds of two monotonic-ns intervals (0.0 when
    disjoint): ``max(0, min(a_end,b_end) - max(a_start,b_start)) / 1e6``."""
    _overlap_ns = max(
        0,
        min(a_end_mono_ns, b_end_mono_ns)
        - max(a_start_mono_ns, b_start_mono_ns),
    )
    return _overlap_ns / 1_000_000


def cpu_affinity_count() -> int:
    """Number of CPUs the current process may run on.

    Prefers ``os.sched_getaffinity(0)`` (mask size, Linux); falls back to
    ``os.cpu_count()`` (0 when unknown).  Never raises.  Stdlib-only.
    """
    try:
        return int(len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        pass
    try:
        return int(os.cpu_count() or 0)
    except Exception:
        return 0


def effective_cores_from(cpu_ms, wall_ms) -> float | None:
    """Ratio of thread-CPU ms to wall ms (``round(cpu_ms / wall_ms, 4)``).

    None-safe: returns None when either input is None or wall_ms <= 0.  This
    is a utilization ratio — it does NOT imply scheduling-wait attribution.
    """
    if cpu_ms is None or wall_ms is None:
        return None
    try:
        _wall = float(wall_ms)
        if _wall <= 0:
            return None
        return round(float(cpu_ms) / _wall, 4)
    except Exception:
        return None


def forensic_intervals_disjoint(intervals) -> tuple[bool, str | None]:
    """Check a list of ``(name, start_mono_ns, end_mono_ns)`` intervals for
    strict non-overlap (touching allowed: ``prev_end <= next_start``).

    Returns ``(True, None)`` when disjoint, or ``(False, "<name_a> overlaps
    <name_b>")`` naming the first violating adjacent pair.  Never raises.
    """
    try:
        _sorted_iv = sorted(
            (iv for iv in (intervals or [])
             if isinstance(iv, (list, tuple)) and len(iv) >= 3),
            key=lambda iv: int(iv[1]),
        )
        for _a, _b in zip(_sorted_iv, _sorted_iv[1:]):
            _a_name, _a_end = str(_a[0]), int(_a[2])
            _b_name, _b_start = str(_b[0]), int(_b[1])
            if _a_end > _b_start:
                return (False, f"{_a_name} overlaps {_b_name}")
        return (True, None)
    except Exception:
        return (True, None)
