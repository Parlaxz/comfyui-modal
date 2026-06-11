"""profiler_trace_v4 — Dual-clock event-based profiling for ComfyUI x Modal.

Trace version ``4.0.0``.

Purpose
-------
Provide a single source of truth for end-to-end profiling with both wall-clock
(``time.time_ns``) and monotonic (``time.perf_counter_ns``) timestamps.

Every event records:
  * ``name`` — canonical event name (see CANONICAL_EVENTS)
  * ``phase`` — high-level phase classification
  * ``process`` — ``"local_bridge"``, ``"modal_remote"``, ``"comfy_internal"``
  * ``wall_unix_ns`` — ``time.time_ns()`` (cross-process comparable)
  * ``mono_ns`` — ``time.perf_counter_ns()`` (same-process deltas only)
  * ``pid``, ``thread_id``, ``thread_name``
  * optional metadata

Rules
-----
* Never subtract ``mono_ns`` across processes / machines.
* Use ``wall_unix_ns`` for cross-process deltas.
* Use ``mono_ns`` for same-process deltas.
* Negative deltas go to ``invalid_deltas``, never silently dropped.
"""

import json
import os
import threading
import time
import uuid
from typing import Any

TRACE_VERSION = "4.0.0"

# ── Profile level ──────────────────────────────────────────────────────────
_VALID_LEVELS = ("off", "summary", "detailed", "trace", "trace_verbose")

_PROFILE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), ".profile_config.json")


def _load_profile_level() -> str:
    level = os.environ.get("COMFYMODAL_PROFILE_LEVEL", "").strip().lower()
    if level in _VALID_LEVELS:
        return level
    try:
        with open(_PROFILE_CONFIG_PATH, "r") as _f:
            cfg = json.loads(_f.read())
        level = (cfg.get("level") or "").strip().lower()
        if level in _VALID_LEVELS:
            return level
    except Exception:
        pass
    return "summary"


_PROFILE_LEVEL = _load_profile_level()


def get_profile_level() -> str:
    return _PROFILE_LEVEL


def set_profile_level(level: str) -> None:
    global _PROFILE_LEVEL
    level = level.strip().lower()
    if level in _VALID_LEVELS:
        _PROFILE_LEVEL = level


def profile_enabled(level: str = "summary") -> bool:
    if _PROFILE_LEVEL == "off":
        return False
    order = {"off": 0, "summary": 1, "detailed": 2, "trace": 3, "trace_verbose": 4}
    return order.get(_PROFILE_LEVEL, 0) >= order.get(level, 1)


# ── Clock model ────────────────────────────────────────────────────────────
CLOCK_MODEL: dict[str, Any] = {
    "version": "4.0.0",
    "wall_clock": "time.time_ns",
    "monotonic_clock": "time.perf_counter_ns",
    "cross_process_delta_clock": "wall_unix_ns",
    "same_process_delta_clock": "mono_ns",
    "notes": [
        "Never subtract mono_ns across processes.",
        "Cross-machine wall time can include clock skew.",
        "Modal/local clock skew is estimated when possible.",
    ],
}

# ── Canonical event names ──────────────────────────────────────────────────

# Local/client events
T0_CLIENT_PRESS = "t0_client_press"
T0A_LOCAL_NODE_START = "t0a_local_node_start"
T1_LOCAL_BRIDGE_RECEIVED = "t1_local_bridge_received"
T1A_LOCAL_PAYLOAD_PARSE_START = "t1a_local_payload_parse_start"
T1B_LOCAL_PAYLOAD_PARSE_END = "t1b_local_payload_parse_end"
T1C_LOCAL_PREFLIGHT_START = "t1c_local_preflight_start"
T1D_LOCAL_PREFLIGHT_END = "t1d_local_preflight_end"
T1E_ACTIVE_PROFILE_WRITE_START = "t1e_active_profile_write_start"
T1F_ACTIVE_PROFILE_WRITE_END = "t1f_active_profile_write_end"

# ── New: detailed local pre-dispatch phases ───────────────────────────
T1G_BODY_READ_START = "t1g_body_read_start"
T1H_BODY_READ_END = "t1h_body_read_end"
T1I_JSON_PARSE_START = "t1i_json_parse_start"
T1J_JSON_PARSE_END = "t1j_json_parse_end"
T1K_PAYLOAD_NORMALIZE_START = "t1k_payload_normalize_start"
T1L_PAYLOAD_NORMALIZE_END = "t1l_payload_normalize_end"
T1M_TRACE_STRIP_START = "t1m_trace_strip_start"
T1N_TRACE_STRIP_END = "t1n_trace_strip_end"
T1O_PROMPT_EXTRACT_START = "t1o_prompt_extract_start"
T1P_PROMPT_EXTRACT_END = "t1p_prompt_extract_end"
T1Q_STACK_EXTRACT_START = "t1q_stack_extract_start"
T1R_STACK_EXTRACT_END = "t1r_stack_extract_end"
T1S_INPUT_COLLECT_START = "t1s_input_collect_start"
T1T_INPUT_COLLECT_END = "t1t_input_collect_end"
T1U_LOCAL_PREFLIGHT_START = "t1u_local_preflight_start"
T1V_LOCAL_PREFLIGHT_END = "t1v_local_preflight_end"
T1W_ACTIVE_NEXT_WRITE_START = "t1w_active_next_write_start"
T1X_ACTIVE_NEXT_WRITE_END = "t1x_active_next_write_end"
T1Y_MODAL_HANDLE_RESOLVE_START = "t1y_modal_handle_resolve_start"
T1Z_MODAL_HANDLE_RESOLVE_END = "t1z_modal_handle_resolve_end"
T1AA_MODAL_CALL_CONSTRUCT_START = "t1aa_modal_call_construct_start"
T1AB_MODAL_CALL_CONSTRUCT_END = "t1ab_modal_call_construct_end"
T1AC_DEEPLY_COPY_START = "t1ac_deepcopy_start"
T1AD_DEEPLY_COPY_END = "t1ad_deepcopy_end"
T1AE_PROFILE_WRITE_VOLUME_START = "t1ae_profile_write_volume_start"
T1AF_PROFILE_WRITE_VOLUME_END = "t1af_profile_write_volume_end"
# Legacy aliases for predispatch phases
BEFORE_STACK_EXTRACT = "before_stack_extract"
AFTER_STACK_EXTRACT = "after_stack_extract"
BEFORE_ACTIVE_NEXT_WRITE = "before_active_next_write"
AFTER_ACTIVE_NEXT_WRITE = "after_active_next_write"
BEFORE_GPU_SPAWN = "before_gpu_spawn"
FIRST_GPU_RESPONSE = "first_gpu_response"

T2_LOCAL_MODAL_SUBMIT_START = "t2_local_modal_submit_start"
T2A_MODAL_CALL_CONSTRUCTED = "t2a_modal_call_constructed"
T2B_MODAL_CALL_STREAM_OPEN = "t2b_modal_call_stream_open"
T2C_FIRST_REMOTE_EVENT_RECEIVED = "t2c_first_remote_event_received"
T2D_LOCAL_PROMPT_ACK_RETURNED = "t2d_local_prompt_ack_returned"
T9_LOCAL_REMOTE_RESULT_RECEIVED = "t9_local_remote_result_received"
T9A_LOCAL_RESULT_DESERIALIZE_START = "t9a_local_result_deserialize_start"
T9B_LOCAL_RESULT_DESERIALIZE_END = "t9b_local_result_deserialize_end"
T9C_LOCAL_BASE64_DECODE_START = "t9c_local_base64_decode_start"
T9D_LOCAL_BASE64_DECODE_END = "t9d_local_base64_decode_end"
T9E_LOCAL_FILE_WRITE_START = "t9e_local_file_write_start"
T9F_LOCAL_FILE_WRITE_END = "t9f_local_file_write_end"
T10_LOCAL_MATERIALIZED = "t10_local_materialized"
T10A_LOCAL_RESPONSE_TO_COMFY_START = "t10a_local_response_to_comfy_start"
T10B_LOCAL_RESPONSE_TO_COMFY_END = "t10b_local_response_to_comfy_end"
T11_LOCAL_UI_DONE = "t11_local_ui_done"

# Modal/remote events
T3_MODAL_ENTRY = "t3_modal_entry"
T3A_REMOTE_PAYLOAD_PARSE_START = "t3a_remote_payload_parse_start"
T3B_REMOTE_PAYLOAD_PARSE_END = "t3b_remote_payload_parse_end"
T3C_REMOTE_PREFLIGHT_START = "t3c_remote_preflight_start"
T3D_REMOTE_PREFLIGHT_END = "t3d_remote_preflight_end"
T3E_CUSTOM_NODE_SYNC_START = "t3e_custom_node_sync_start"
T3F_CUSTOM_NODE_SYNC_END = "t3f_custom_node_sync_end"
T3G_DEPENDENCY_VALIDATION_START = "t3g_dependency_validation_start"
T3H_DEPENDENCY_VALIDATION_END = "t3h_dependency_validation_end"
T3I_ACTIVE_PROFILE_READ_START = "t3i_active_profile_read_start"
T3J_ACTIVE_PROFILE_READ_END = "t3j_active_profile_read_end"
T3K_PREDISPATCH_DONE = "t3k_predispatch_done"
T4_PROMPT_START = "t4_prompt_start"
T4A_ACTUAL_LOAD_SUBMIT_START = "t4a_actual_load_submit_start"
T4B_ACTUAL_LOAD_SUBMIT_END = "t4b_actual_load_submit_end"
T4C_COMFY_VALIDATE_START = "t4c_comfy_validate_start"
T4D_COMFY_VALIDATE_END = "t4d_comfy_validate_end"
T4E_GRAPH_EXECUTION_START = "t4e_graph_execution_start"
T5_SAMPLER_START = "t5_sampler_start"
T6_SAMPLER_END = "t6_sampler_end"
T6A_VAE_DECODE_START = "t6a_vae_decode_start"
T6B_VAE_DECODE_END = "t6b_vae_decode_end"
T7_OUTPUTS_COLLECTION_START = "t7_outputs_collection_start"
T7A_HISTORY_FETCH_START = "t7a_history_fetch_start"
T7B_HISTORY_FETCH_END = "t7b_history_fetch_end"
T7C_OUTPUT_FILE_SCAN_START = "t7c_output_file_scan_start"
T7D_OUTPUT_FILE_SCAN_END = "t7d_output_file_scan_end"
T7E_OUTPUT_FILE_READ_START = "t7e_output_file_read_start"
T7F_OUTPUT_FILE_READ_END = "t7f_output_file_read_end"
T7G_IMAGE_CONVERT_START = "t7g_image_convert_start"
T7H_IMAGE_CONVERT_END = "t7h_image_convert_end"
T8_OUTPUTS_COLLECTED = "t8_outputs_collected"
T8A_RESULT_ENRICH_START = "t8a_result_enrich_start"
T8B_RESULT_ENRICH_END = "t8b_result_enrich_end"
T8C_RETURN_PACKAGING_START = "t8c_return_packaging_start"
T8D_RETURN_PACKAGING_END = "t8d_return_packaging_end"
T8E_REMOTE_RETURN_START = "t8e_remote_return_start"
T8F_REMOTE_RETURN_END = "t8f_remote_return_end"

# Restore events
RESTORE_START = "restore_start"
RESTORE_CUSTOM_NODE_SYNC_START = "restore_custom_node_sync_start"
RESTORE_CUSTOM_NODE_SYNC_END = "restore_custom_node_sync_end"
RESTORE_ACTIVE_PROFILE_LOOKUP_START = "restore_active_profile_lookup_start"
RESTORE_ACTIVE_PROFILE_LOOKUP_END = "restore_active_profile_lookup_end"
RESTORE_PRELOAD_PATH_RESOLVE_START = "restore_preload_path_resolve_start"
RESTORE_PRELOAD_PATH_RESOLVE_END = "restore_preload_path_resolve_end"
RESTORE_GPU_STATE_START = "restore_gpu_state_start"
RESTORE_GPU_STATE_END = "restore_gpu_state_end"
RESTORE_CUDA_WARMUP_START = "restore_cuda_warmup_start"
RESTORE_CUDA_WARMUP_END = "restore_cuda_warmup_end"
RESTORE_PATCHES_START = "restore_patches_start"
RESTORE_PATCHES_END = "restore_patches_end"
RESTORE_CPU_PRELOAD_START = "restore_cpu_preload_start"
RESTORE_CPU_PRELOAD_END = "restore_cpu_preload_end"
RESTORE_DIRECT_WARMUP_START = "restore_direct_warmup_start"
RESTORE_DIRECT_WARMUP_END = "restore_direct_warmup_end"
RESTORE_END = "restore_end"

# Model-load events
ACTUAL_LOAD_SUBMIT = "actual_load_submit"
ACTUAL_LOAD_WORKER_START = "actual_load_worker_start"
ACTUAL_LOAD_FILE_READ_START = "actual_load_file_read_start"
ACTUAL_LOAD_FILE_READ_END = "actual_load_file_read_end"
ACTUAL_LOAD_WORKER_DONE = "actual_load_worker_done"
GRAPH_MODEL_REQUEST = "graph_model_request"
GRAPH_MODEL_WAIT_START = "graph_model_wait_start"
GRAPH_MODEL_WAIT_END = "graph_model_wait_end"
GRAPH_MODEL_READY = "graph_model_ready"
MODEL_CPU_CACHE_HIT = "model_cpu_cache_hit"
MODEL_CPU_CACHE_MISS = "model_cpu_cache_miss"
MODEL_OBJECT_CACHE_HIT = "model_object_cache_hit"
MODEL_FUTURE_HIT = "model_future_hit"
MODEL_ORIGINAL_VOLUME_LOAD_START = "model_original_volume_load_start"
MODEL_ORIGINAL_VOLUME_LOAD_END = "model_original_volume_load_end"

# ── Phase categories ───────────────────────────────────────────────────────
PHASE_LOCAL_PRE = "local_pre"
PHASE_LOCAL_BRIDGE = "local_bridge"
PHASE_LOCAL_MATERIALIZE = "local_materialize"
PHASE_MODAL_INFRA = "modal_infra"
PHASE_RESTORE = "restore"
PHASE_REMOTE_PRE = "remote_pre"
PHASE_EXECUTION = "execution"
PHASE_SAMPLER = "sampler"
PHASE_POST_SAMPLER = "post_sampler"
PHASE_OUTPUT = "output"
PHASE_RETURN = "return"
PHASE_MODEL_LOAD = "model_load"
PHASE_ACTUAL_LOAD = "actual_load"


def _get_thread_info() -> dict[str, Any]:
    """Return current thread's ``pid``, ``thread_id``, ``thread_name``."""
    try:
        pid = os.getpid()
    except AttributeError:
        pid = 0
    try:
        thread_id = threading.get_ident()
    except AttributeError:
        thread_id = 0
    try:
        thread_name = threading.current_thread().name
    except AttributeError:
        thread_name = ""
    return {
        "pid": pid,
        "thread_id": thread_id,
        "thread_name": thread_name,
    }


def _generate_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def make_event(
    name: str,
    process: str = "",
    phase: str = "",
    trace_id: str = "",
    request_seq: int = 0,
    **metadata: Any,
) -> dict[str, Any]:
    """Create a single trace event with dual clocks."""
    wall_ns = time.time_ns()
    mono_ns = time.perf_counter_ns()
    thread_info = _get_thread_info()
    event: dict[str, Any] = {
        "name": name,
        "phase": phase,
        "process": process,
        "wall_unix_ns": wall_ns,
        "mono_ns": mono_ns,
        "pid": thread_info["pid"],
        "thread_id": thread_info["thread_id"],
        "thread_name": thread_info["thread_name"],
    }
    if trace_id:
        event["trace_id"] = trace_id
    if request_seq:
        event["request_seq"] = request_seq
    if metadata:
        event["metadata"] = metadata
    return event


def mark_event(
    trace: list[dict],
    name: str,
    process: str = "",
    phase: str = "",
    trace_id: str = "",
    request_seq: int = 0,
    profile_level: str = "summary",
    **metadata: Any,
) -> dict[str, Any]:
    """Record an instantaneous event into the trace list.

    Only records if the current (or passed) profile level is >= the required level.
    Returns the event dict for optional inline use.
    """
    if not profile_enabled(profile_level):
        empty: dict[str, Any] = {}
        return empty
    event = make_event(
        name=name,
        process=process,
        phase=phase,
        trace_id=trace_id,
        request_seq=request_seq,
        **metadata,
    )
    trace.append(event)
    return event


class SpanContext:
    """Context manager for recording span start/end events.

    Usage::

        with SpanContext(trace, "sampler", process="modal_remote", phase="sampler") as ctx:
            run_sampler()
        # ctx.duration_ns is set on exit
    """

    __slots__ = (
        "_trace", "_name", "_process", "_phase",
        "_trace_id", "_request_seq", "_profile_level",
        "_start_wall", "_start_mono", "duration_ns", "duration_ms",
    )

    def __init__(
        self,
        trace: list[dict],
        name: str,
        process: str = "",
        phase: str = "",
        trace_id: str = "",
        request_seq: int = 0,
        profile_level: str = "summary",
    ):
        self._trace = trace
        self._name = name
        self._process = process
        self._phase = phase
        self._trace_id = trace_id
        self._request_seq = request_seq
        self._profile_level = profile_level
        self._start_wall = 0
        self._start_mono = 0
        self.duration_ns = 0
        self.duration_ms = 0.0

    def __enter__(self) -> "SpanContext":
        if profile_enabled(self._profile_level):
            self._start_wall = time.time_ns()
            self._start_mono = time.perf_counter_ns()
            mark_event(
                self._trace,
                name=f"{self._name}_start",
                process=self._process,
                phase=self._phase,
                trace_id=self._trace_id,
                request_seq=self._request_seq,
                profile_level=self._profile_level,
            )
        return self

    def __exit__(self, *args: Any) -> None:
        if profile_enabled(self._profile_level) and self._start_mono:
            end_mono = time.perf_counter_ns()
            self.duration_ns = end_mono - self._start_mono
            self.duration_ms = round(self.duration_ns / 1_000_000, 3)
            mark_event(
                self._trace,
                name=f"{self._name}_end",
                process=self._process,
                phase=self._phase,
                trace_id=self._trace_id,
                request_seq=self._request_seq,
                profile_level=self._profile_level,
                duration_ns=self.duration_ns,
                duration_ms=self.duration_ms,
            )


# ── Trace container ────────────────────────────────────────────────────────


class EventTrace:
    """Collects events and derives spans + critical path.

    Lightweight container — stores events as a list of dicts.
    Serializes to JSON on demand.  Does NOT persist to disk automatically.
    """

    def __init__(
        self,
        trace_id: str = "",
        process: str = "",
        request_seq: int = 0,
    ):
        self.trace_id = trace_id or _generate_trace_id()
        self.process = process
        self.request_seq = request_seq
        self.events: list[dict[str, Any]] = []
        self._wall_offset: int = 0
        self._closed = False

    @property
    def wall_t0_ns(self) -> int:
        if self.events:
            return self.events[0].get("wall_unix_ns", 0)
        return 0

    def mark(
        self,
        name: str,
        phase: str = "",
        profile_level: str = "summary",
        **metadata: Any,
    ) -> dict[str, Any]:
        event = make_event(
            name=name,
            process=self.process,
            phase=phase,
            trace_id=self.trace_id,
            request_seq=self.request_seq,
            **metadata,
        )
        self.events.append(event)
        return event

    def span_start(self, name: str, phase: str = "", **metadata: Any) -> None:
        self.mark(f"{name}_start", phase=phase, **metadata)

    def span_end(self, name: str, phase: str = "", **metadata: Any) -> None:
        self.mark(f"{name}_end", phase=phase, **metadata)

    def merge(self, other: "EventTrace | list[dict] | None") -> None:
        if other is None:
            return
        if isinstance(other, EventTrace):
            self.events.extend(other.events)
        elif isinstance(other, list):
            self.events.extend(other)

    def close(self) -> None:
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_version": TRACE_VERSION,
            "trace_id": self.trace_id,
            "process": self.process,
            "request_seq": self.request_seq,
            "clock": CLOCK_MODEL,
            "event_count": len(self.events),
            "events": list(self.events),
        }


# ── Span derivation ────────────────────────────────────────────────────────


def derive_spans(events: list[dict]) -> list[dict]:
    """Derive named spans from start/end event pairs.

    Matches ``{name}_start`` / ``{name}_end`` pairs and computes duration.
    """
    starts: dict[str, list[dict]] = {}
    spans: list[dict] = []
    for ev in events:
        name = ev.get("name", "")
        if name.endswith("_start"):
            base = name[:-6]
            starts.setdefault(base, []).append(ev)
        elif name.endswith("_end"):
            base = name[:-4]
            start_list = starts.get(base, [])
            if start_list:
                start_ev = start_list.pop(0)
                dur_ns = ev.get("wall_unix_ns", 0) - start_ev.get("wall_unix_ns", 0)
                dur_mono = ev.get("mono_ns", 0) - start_ev.get("mono_ns", 0)
                same_proc = start_ev.get("process") == ev.get("process")
                spans.append({
                    "name": base,
                    "start_event": start_ev.get("name"),
                    "end_event": ev.get("name"),
                    "start_wall_unix_ns": start_ev.get("wall_unix_ns"),
                    "end_wall_unix_ns": ev.get("wall_unix_ns"),
                    "duration_wall_ns": dur_ns,
                    "duration_wall_ms": round(dur_ns / 1_000_000, 3),
                    "duration_mono_ms": round(dur_mono / 1_000_000, 3) if same_proc else None,
                    "process": ev.get("process", ""),
                    "same_process": same_proc,
                })
    return spans


def derive_non_overlapping_critical_path(
    spans: list[dict],
    stages: dict[str, float],
) -> dict[str, Any]:
    """Build a non-overlapping critical path from derived spans.

    Uses wall-clock time.  Assumes spans are already ordered by start time
    and may overlap.  The critical path is the set of non-overlapping spans
    that cover the maximum wall time.
    """
    if not spans:
        return {
            "known_ms": 0.0,
            "unknown_ms": 0.0,
            "phases": [],
            "note": "no spans available for critical path derivation",
        }

    sorted_spans = sorted(spans, key=lambda s: s.get("start_wall_unix_ns", 0))
    critical: list[dict] = []
    last_end = 0
    total_known = 0

    for sp in sorted_spans:
        start = sp.get("start_wall_unix_ns", 0)
        end = sp.get("end_wall_unix_ns", 0)
        dur_ms = sp.get("duration_wall_ms", 0)
        if start >= last_end:
            critical.append(sp)
            total_known += dur_ms
            last_end = end
        elif end > last_end:
            overlap = last_end - start
            remaining = end - last_end
            remaining_ms = max(0.0, dur_ms - (overlap / 1_000_000))
            if remaining_ms > 0:
                entry = dict(sp)
                entry["duration_wall_ms"] = round(remaining_ms, 3)
                entry["overlap_deduction_ns"] = overlap
                critical.append(entry)
                total_known += remaining_ms
                last_end = end

    total_wall_ns = 0
    if stages:
        start_keys = [k for k in stages if k.startswith("t0") or k == "t0_client_press"]
        end_keys = [k for k in stages if k.startswith("t10") or k == "t10_local_materialized" or k.startswith("t8f")]
        if start_keys and end_keys:
            sv = min(stages.get(k, float("inf")) for k in start_keys)
            ev = max(stages.get(k, 0) for k in end_keys)
            if sv < float("inf") and ev > 0:
                total_wall_ns = int((ev - sv) * 1e9)

    unknown_ms = max(0.0, (total_wall_ns / 1_000_000) - total_known) if total_wall_ns > 0 else 0.0

    return {
        "known_ms": round(total_known, 3),
        "unknown_ms": round(unknown_ms, 3),
        "total_wall_ms": round(total_wall_ns / 1_000_000, 3) if total_wall_ns > 0 else 0.0,
        "phases": critical[:50],
        "total_spans": len(spans),
        "critical_spans": len(critical),
    }


# ── Clock skew estimation ──────────────────────────────────────────────────


def estimate_clock_skew(
    local_submit_start_wall: int,
    first_remote_event_wall: int,
    remote_entry_wall: int,
) -> dict[str, Any]:
    """Estimate clock skew between local and Modal machines.

    This is imperfect — returns an estimate only.
    """
    midpoint = (local_submit_start_wall + first_remote_event_wall) // 2
    rtt_estimate = first_remote_event_wall - local_submit_start_wall
    skew_estimate = remote_entry_wall - midpoint

    confidence = "low" if rtt_estimate > 5_000_000_000 else "medium"

    return {
        "estimated": True,
        "skew_ms_estimate": round(skew_estimate / 1_000_000, 2),
        "round_trip_ms_for_estimate": round(rtt_estimate / 1_000_000, 2),
        "confidence": confidence,
        "notes": [
            "Skew = remote_entry_wall - midpoint(local_submit, first_remote_event)",
            "RTT > 5s reduces confidence due to possible queue/warmup time",
        ],
    }


# ── Summary helpers ────────────────────────────────────────────────────────


def summarize_trace(
    events: list[dict],
    stages: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Produce a compact summary from raw events."""
    spans = derive_spans(events)
    critical_path = derive_non_overlapping_critical_path(spans, stages or {})

    event_counts: dict[str, int] = {}
    for ev in events:
        name = ev.get("name", "")
        event_counts[name] = event_counts.get(name, 0) + 1

    return {
        "trace_version": TRACE_VERSION,
        "event_count": len(events),
        "unique_events": len(event_counts),
        "event_counts": event_counts,
        "span_count": len(spans),
        "critical_path": critical_path,
        "clock": CLOCK_MODEL,
    }


def log_event(event: dict[str, Any]) -> str:
    """Compact log line for a single event (trace_verbose only)."""
    name = event.get("name", "?")
    wall = event.get("wall_unix_ns", 0)
    mono = event.get("mono_ns", 0)
    proc = event.get("process", "?")
    phase = event.get("phase", "?")
    return f"[prof.event] name={name} t_wall_ns={wall} t_mono_ns={mono} process={proc} phase={phase}"
