"""V2 benchmark waterfall extraction and rendering.

This module deliberately knows nothing about ComfyUI. It consumes a completed
result and its already-captured timing data, so formatting cannot be part of
the measured request path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

try:
    from comfymodal_runtime.wait_attribution import classify_node_wait, extract_wait_windows
except ImportError:  # pragma: no cover - degraded rendering when module missing
    classify_node_wait = None
    extract_wait_windows = None


UNAVAILABLE = "unavailable"
MEASURED = "measured"
DERIVED = "derived"
INVALID = "invalid"
NON_APPLICABLE = "non_applicable"

# Reconciliation acceptance model: the exclusive top-level sum is compared
# against the non-scheduling wall (command->response minus scheduling time).
# Hard acceptance is <= 50 ms; the <= 10 ms target is
# exposed as a warning (never hidden) but does not fail the run.
RECONCILIATION_TARGET_MS = 10.0
RECONCILIATION_HARD_MS = 50.0

# Accounting roles:
#   "top_level"        — exclusive chronological interval; the ONLY role that
#                        affects cumulative / % / bar / accounted.
#   "child"            — sequential detail under a top-level row; excluded.
#   "overlap_detail"   — overlapping diagnostic span (UNET/VAE early-activation
#                        lanes); excluded from accounted and rendered inline.
#   "informational"    — e.g. Modal scheduling: never a numbered row, never
#                        accounted/cumulative/%/bar; shown once in the footer.

# Node rows always shown in expanded diagnostics even when tiny (< 25 ms):
# strategic graph nodes whose presence/absence materially changes the read.
STRATEGIC_NODE_CLASS_TYPES = frozenset({
    "UNETLoader",
    "CLIPLoader",
    "CLIPTextEncode",
    "CLIPTextEncodeWithModel",
    "KSampler",
    "KSamplerAdvanced",
    "VAEDecode",
    "ComfyModalProductionOutput",
    "ComfyModalProductionImageComparerOutput",
})


@dataclass(frozen=True)
class Boundary:
    name: str
    wall_unix_ns: int | None
    monotonic_ns: int | None
    process: str
    source: str


@dataclass(frozen=True)
class WaterfallStage:
    key: str
    label: str
    group: str
    start_ns: int | None
    end_ns: int | None
    duration_ms: float | None
    cumulative_ms: float | None
    percentage: float | None
    source: str
    status: str
    overlaps: tuple[str, ...] = ()
    is_detail: bool = False
    parent_key: str = ""
    included_in_total: bool = True
    clock_scope: str = ""
    source_fields: tuple[str, ...] = ()
    concurrent: bool = False
    provenance: str = ""
    # Accounting role: "top_level" (exclusive chronological interval, the ONLY
    # role that affects cumulative/%/bar/accounted), "child" (sequential
    # detail, included_in_total=False), "overlap_detail" (overlapping
    # diagnostic span, excluded from accounted), or "informational" (never a
    # numbered row nor accounted; e.g. Modal scheduling shown once in footer).
    accounting_role: str = "top_level"


@dataclass(frozen=True)
class WaterfallReport:
    run_label: str
    request_id: str
    identity: Mapping[str, Any]
    total_ms: float | None
    stages: tuple[WaterfallStage, ...]
    reconciliation_ms: float | None
    warnings: tuple[str, ...]
    accounted_ms: float | None = None
    tolerance_ms: float | None = None
    details: tuple[WaterfallStage, ...] = ()
    residual_ms: float | None = None
    residual_pct: float | None = None
    reconciliation_status: str = ""
    controllable_wall_ms: float | None = None
    platform_wall_ms: float | None = None
    boundary_flags: tuple[str, ...] = ()
    scheduling_ms: float | None = None
    total_wall_ms: float | None = None
    command_response_ms: float | None = None
    command_to_enqueue_ms: float | None = None
    scheduling_time_ms: float | None = None
    non_scheduling_ms: float | None = None
    host_telemetry: dict = field(default_factory=dict)
    partial_waterfall: bool = False
    partial_flags: tuple[str, ...] = ()
    pre_python_interval_ms: float | None = None
    pre_python_interval_classification: str = ""
    # Required-data availability flags (e.g. "checkpoint_read_unavailable").
    data_flags: tuple[str, ...] = ()
    # Reconciliation acceptance thresholds (ms).  Hard acceptance <= 50 ms;
    # the 10 ms target is surfaced as a warning, never hidden.
    reconciliation_target_ms: float = RECONCILIATION_TARGET_MS
    reconciliation_hard_ms: float = RECONCILIATION_HARD_MS
    # Diagnostic status: "COMPLETE" only when no required-data flags exist AND
    # reconciliation is resolved within the hard ceiling.  "INCOMPLETE" when a
    # required-data flag exists, "UNRESOLVED" when the wall is unknown,
    # "FAILED" when reconciliation exceeds the hard ceiling.
    diagnostic_status: str = ""


@dataclass(frozen=True)
class _Candidate:
    start: Boundary | None = None
    end: Boundary | None = None
    duration_ms: float | None = None
    source: str = ""
    status: str = UNAVAILABLE
    clock_scope: str = ""
    source_fields: tuple[str, ...] = ()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _trace(result: Mapping[str, Any]) -> Mapping[str, Any]:
    direct = _as_mapping(result).get("trace")
    if isinstance(direct, Mapping):
        return direct
    nested = _as_mapping(result).get("result")
    nested_trace = _as_mapping(nested).get("trace")
    return nested_trace if isinstance(nested_trace, Mapping) else {}


def _events(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values = _as_mapping(_trace(result)).get("events", ())
    return [value for value in values if isinstance(value, Mapping)]


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _event_clock(event: Mapping[str, Any], key: str) -> int | None:
    value = event.get(key)
    if value is None:
        metadata = _as_mapping(event.get("metadata"))
        value = metadata.get(key)
        if value is None:
            value = metadata.get("wall_ns" if key == "wall_unix_ns" else "mono_ns")
    number = _number(value)
    return None if key == "monotonic_ns" and number is not None and number <= 0 else number


def _event_boundary(
    result: Mapping[str, Any],
    names: str | Sequence[str],
    *,
    process: str | None = None,
    last: bool = False,
) -> Boundary | None:
    wanted = {names} if isinstance(names, str) else set(names)
    found: list[Boundary] = []
    for event in _events(result):
        if event.get("name") not in wanted:
            continue
        event_process = str(event.get("process") or "")
        if process is not None and event_process != process:
            continue
        wall = _event_clock(event, "wall_unix_ns")
        mono = _event_clock(event, "monotonic_ns")
        if wall is None and mono is None:
            continue
        found.append(Boundary(
            name=str(event.get("name")),
            wall_unix_ns=wall,
            monotonic_ns=mono,
            process=event_process,
            source="event",
        ))
    if not found:
        return None
    return found[-1] if last else found[0]


def _request_origin(result: Mapping[str, Any]) -> Mapping[str, Any]:
    trace = _as_mapping(_trace(result))
    metadata = _as_mapping(trace.get("metadata"))
    origin = metadata.get("request_origin_info")
    if isinstance(origin, Mapping):
        return origin
    direct = _as_mapping(result).get("request_origin_info")
    return direct if isinstance(direct, Mapping) else {}


def _origin_boundary(result: Mapping[str, Any], key: str, name: str) -> Boundary | None:
    value = _request_origin(result).get(key)
    if value is None:
        return None
    if key.endswith("_wall_unix_ms"):
        wall = int(value * 1_000_000) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    else:
        wall = _number(value)
    if wall is None:
        return None
    return Boundary(name=name, wall_unix_ns=wall, monotonic_ns=None, process="local", source="origin")


def _metadata_interval(
    result: Mapping[str, Any],
    event_name: str,
    start_key: str,
    end_key: str,
) -> _Candidate:
    for metadata in _metadata_events(result, event_name):
        start_value = _number(metadata.get(start_key))
        end_value = _number(metadata.get(end_key))
        if start_value is not None and start_value <= 0:
            start_value = None
        if end_value is not None and end_value <= 0:
            end_value = None
        if start_value is not None and end_value is not None:
            start = Boundary(start_key, None, start_value, "remote", "metadata")
            end = Boundary(end_key, None, end_value, "remote", "metadata")
            return _candidate(result, start, end)
    return _Candidate()


def _event_metadata_value(result: Mapping[str, Any], name: str, key: str, *, last: bool = True) -> Any:
    values = [
        _as_mapping(event.get("metadata")).get(key)
        for event in _events(result)
        if event.get("name") == name
    ]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return values[-1] if last else values[0]


def _metadata_events(result: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    return [_as_mapping(event.get("metadata")) for event in _events(result) if event.get("name") == name]


def _first_value(result: Mapping[str, Any], keys: Sequence[str]) -> Any:
    trace = _as_mapping(_trace(result))
    root = _as_mapping(result)
    timing = _as_mapping(root.get("timing"))
    restore = _as_mapping(root.get("_restore_timing"))
    structured = _as_mapping(root.get("pre_sampler_structured_report"))
    sources: list[Mapping[str, Any]] = [
        root,
        timing,
        restore,
        structured,
        _as_mapping(root.get("local_timing")),
        _as_mapping(trace.get("metadata")),
        _request_origin(result),
        _as_mapping(trace.get("stages")),
        _as_mapping(trace.get("deltas_ms")),
        _as_mapping(root.get("phase_durations_ms")),
        _as_mapping(root.get("intervals_ms")),
    ]
    for name in ("pre_sampler_stages", "prompt_executor_milestones", "critical_path"):
        sources.extend(_metadata_events(result, name))
    sources.extend(_as_mapping(event.get("metadata")) for event in _events(result))
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value is not None:
                return value
    return None


def _restore_timing(result: Mapping[str, Any]) -> Mapping[str, Any]:
    direct = _as_mapping(result).get("_restore_timing")
    if isinstance(direct, Mapping):
        return direct
    trace_meta = _as_mapping(_trace(result)).get("metadata")
    candidate = _as_mapping(trace_meta).get("_restore_timing")
    return candidate if isinstance(candidate, Mapping) else {}


def _timing_boundary(result: Mapping[str, Any], key: str, name: str) -> Boundary | None:
    timing = _restore_timing(result)
    wall = _number(timing.get(f"{key}_wall_unix_ns"))
    mono = _number(timing.get(f"{key}_mono_ns"))
    if mono is not None and mono <= 0:
        mono = None
    if wall is None and mono is None:
        return None
    return Boundary(name=name, wall_unix_ns=wall, monotonic_ns=mono, process="remote", source="metadata")


def _command_boundary(command_start_unix_ms: int | None) -> Boundary | None:
    if command_start_unix_ms is None:
        return None
    return Boundary(
        name="command_start",
        wall_unix_ns=int(command_start_unix_ms * 1_000_000),
        monotonic_ns=None,
        process="local",
        source="argument",
    )


def _response_boundary(response_received_unix_ns: int | None) -> Boundary | None:
    if response_received_unix_ns is None:
        return None
    return Boundary(
        name="response_received",
        wall_unix_ns=int(response_received_unix_ns),
        monotonic_ns=None,
        process="local",
        source="argument",
    )


def _modal_restore_begin_boundary(
    result: Mapping[str, Any], param_value: int | None,
) -> Boundary | None:
    """The Modal platform restore-begin boundary.

    ``restore_begin`` is when the Modal scheduler hands the restored container
    to the (not yet resumed) Python process — a platform-side boundary that
    only the Modal app log / client can observe.  Priority: explicit keyword
    argument, then ``modal_restore_begin_wall_unix_ns`` in (result root,
    timing dict, local_timing dict, trace metadata).  The in-process
    ``snapshot_restore_start`` / ``v2_startup_post_snapshot_restore_start``
    events are NOT treated as restore_begin (they fire inside Python and are
    only used as python_resume fallbacks).
    """
    value = _number(param_value)
    if value is None:
        value = _first_value(result, ("modal_restore_begin_wall_unix_ns",))
    if value is None or value <= 0:
        return None
    return Boundary(
        name="snapshot_restore_begin",
        wall_unix_ns=int(value),
        monotonic_ns=None,
        process="remote",
        source="modal_app_log",
    )


def _python_resume_boundary(result: Mapping[str, Any]) -> Boundary | None:
    """The first executable line of the restored remote Python process.

    Priority: ``_restore_timing.remote_python_resume`` timing boundary ->
    ``v2_startup_post_snapshot_restore_start`` event -> ``snapshot_restore_start``
    event (both remote) -> ``restore_method_start`` timing boundary.
    """
    timing = _timing_boundary(result, "remote_python_resume", "remote_python_resume")
    if timing is not None:
        return timing
    for event_name in (
        "v2_startup_post_snapshot_restore_start",
        "snapshot_restore_start",
    ):
        event = _event_boundary(result, event_name, process="remote")
        if event is not None:
            return event
    return _timing_boundary(result, "restore_method_start", "restore_method_start")


def _submission_boundary(result: Mapping[str, Any]) -> Boundary | None:
    """The local actual-modal-submission boundary (existing semantics)."""
    return (
        _origin_boundary(result, "modal_submission_attempt_wall_unix_ns", "modal_submission_attempt_wall_unix_ns")
        or _event_boundary(result, ("modal_submission_attempt", "modal_first_iteration_start"), process="local")
    )


def _stage_provenance(candidate: _Candidate) -> str:
    """Map a candidate to a coarse provenance bucket for rendering."""
    if candidate.source == "accounting":
        return "accounting"
    if candidate.source == "derived":
        return "derived_exact"
    for boundary in (candidate.start, candidate.end):
        if boundary is not None and boundary.source == "modal_app_log":
            return "modal_app_log"
    if candidate.source in ("argument", "origin"):
        return "host_trace"
    local = any(
        boundary is not None and boundary.process == "local"
        for boundary in (candidate.start, candidate.end)
    )
    if candidate.source == "event":
        return "host_trace" if local else "remote_trace"
    if candidate.source == "metadata":
        # A mixed-source candidate collapses to "metadata"; a local boundary
        # still identifies a host-side trace (e.g. command -> local receive).
        return "host_trace" if local else "remote_trace"
    if candidate.source in ("detail", "cpu_owner", "node_timing", "active_read"):
        return "remote_trace"
    return ""


def _duration_between(start: Boundary, end: Boundary) -> float | None:
    if start.process and start.process == end.process:
        if start.monotonic_ns is not None and end.monotonic_ns is not None:
            return (end.monotonic_ns - start.monotonic_ns) / 1_000_000.0
    if start.wall_unix_ns is not None and end.wall_unix_ns is not None:
        return (end.wall_unix_ns - start.wall_unix_ns) / 1_000_000.0
    return None


def _clock_scope(start: Boundary | None, end: Boundary | None) -> str:
    if start is not None and end is not None and start.process == end.process and start.monotonic_ns is not None and end.monotonic_ns is not None:
        return f"monotonic:{start.process}"
    if start is not None and end is not None and start.wall_unix_ns is not None and end.wall_unix_ns is not None:
        return "wall"
    return ""


def _candidate(
    result: Mapping[str, Any],
    start: Boundary | None,
    end: Boundary | None,
    *,
    duration_keys: Sequence[str] = (),
) -> _Candidate:
    if start is not None and end is not None:
        duration = _duration_between(start, end)
        if duration is not None:
            if duration < 0 and start.process != end.process:
                # Cross-process wall-clock intervals are unreliable: the local
                # and remote hosts are not on a shared clock, so a negative
                # interval here reflects clock skew, not a real duration.
                # Never report a phantom negative measured value; fall through
                # to authoritative duration keys, else mark unavailable so the
                # interval is not subtracted into reconciliation.
                duration = None
            elif duration < 0 and start.process == end.process and abs(duration) < 2.0:
                # Conservative same-process order guard: the local return
                # markers are the same instant (final_result_received is
                # emitted a sub-ms/a-few-ms before execute_plan emits
                # remote_return_start), so a small same-process negative is a
                # boundary-order artifact, not a real duration.  Report the
                # true ~0 span instead of an INVALID negative.
                duration = 0.0
            if duration is not None:
                return _Candidate(start, end, duration, "event" if start.source == end.source == "event" else "metadata", MEASURED, _clock_scope(start, end))
    for key in duration_keys:
        value = _first_value(result, (key,))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return _Candidate(start, end, float(value), "metadata", DERIVED, source_fields=(key,))
    return _Candidate(start, end, None, "", UNAVAILABLE)


def _candidate_from_duration(
    value: Any,
    *,
    source: str = "metadata",
    source_fields: tuple[str, ...] = (),
) -> _Candidate:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _Candidate(
            duration_ms=float(value), source=source, status=DERIVED,
            clock_scope="metadata", source_fields=source_fields,
        )
    return _Candidate(source="", status=UNAVAILABLE)


# Active-read record timestamp keys (wall vs monotonic are kept on the correct
# Boundary field — never folded into the wrong clock domain).
_ACTIVE_READ_START_KEYS = (
    ("start_wall_unix_ns", "wall"),
    ("start_monotonic_ns", "mono"),
    ("start_ns", "wall"),
)
_ACTIVE_READ_END_KEYS = (
    ("end_wall_unix_ns", "wall"),
    ("end_monotonic_ns", "mono"),
    ("end_ns", "wall"),
)


# Node-row timeline placement (G3 / Batch A): per_node_timings
# start_perf_ns / end_perf_ns are captured with time.perf_counter_ns() in
# runtime_executor._patched_exec_node (same timer boundaries as duration_ms).
# Artifacts are produced on Linux (Modal), where CPython implements both
# perf_counter_ns() and monotonic_ns() on CLOCK_MONOTONIC (same clock, same
# epoch), so perf values are placed in the same "monotonic:remote" scope used
# for other remote same-process mono intervals (pre_sampler_stages,
# active_read_records) — the existing clock normalization.  Node rows are
# NON-ACCOUNTING overlap detail (included_in_total=False, accounting_role
# "child"), so any platform-level clock divergence could only misposition a
# diagnostic row and can never affect reconciliation totals.  Old records
# without timestamps fall back to duration-only rows (start/end None).


def _active_read_record_boundary(
    record: Mapping[str, Any],
) -> tuple[Boundary, Boundary] | None:
    """Build the active-read start/end Boundaries with correct wall-vs-mono
    placement, or ``None`` when either timestamp is absent."""
    start_wall = start_mono = None
    for key, kind in _ACTIVE_READ_START_KEYS:
        value = _number(record.get(key))
        if value is None:
            continue
        if kind == "wall":
            start_wall = value
        else:
            start_mono = value
        break
    end_wall = end_mono = None
    for key, kind in _ACTIVE_READ_END_KEYS:
        value = _number(record.get(key))
        if value is None:
            continue
        if kind == "wall":
            end_wall = value
        else:
            end_mono = value
        break
    if (start_wall is None and start_mono is None) or (end_wall is None and end_mono is None):
        return None
    process = str(record.get("process") or "remote")
    return (
        Boundary("active_read_start", start_wall, start_mono, process, "active_read"),
        Boundary("active_read_end", end_wall, end_mono, process, "active_read"),
    )


# Model-read owner/path semantics.  A record is a candidate checkpoint read
# only when its owner/path describes a model read; CLIP/text-encoder/VAE reads
# are never acceptable substitutes.
_ACTIVE_READ_MODEL_TOKENS = ("unet", "model", "read", "loader", "checkpoint", "graph")
_ACTIVE_READ_NON_MODEL_TOKENS = ("clip", "text", "vae", "tokenizer", "cond", "lora")


def _active_read_is_model_read(record: Mapping[str, Any]) -> bool:
    owner = str(record.get("owner") or "").strip().lower()
    path = str(record.get("path_hash") or record.get("path") or record.get("filename") or "").strip().lower()
    if not owner and not path:
        return False
    combined = owner
    if path:
        combined += " " + path
    if any(tag in combined for tag in _ACTIVE_READ_NON_MODEL_TOKENS):
        return False
    if any(tag in owner for tag in _ACTIVE_READ_MODEL_TOKENS):
        return True
    if path and any(ext in path for ext in (".safetensors", ".ckpt", ".pt", ".sft")):
        return True
    return False


def _active_read_matches_result(record: Mapping[str, Any], result: Mapping[str, Any]) -> bool:
    """The record must not explicitly belong to another request/instance/
    restore session.  A record carrying NO identity fields is treated as ours
    (matches); a record carrying a DIFFERENT request/instance/session is
    rejected — never choose a foreign read."""
    request_id = _request_id(result)
    identity = _identity(result)
    instance_id = str(identity.get("restored_instance_id") or "").strip()
    session_id = str(identity.get("restore_session_id") or "").strip()
    if request_id:
        record_request = str(record.get("request_id") or "").strip()
        if record_request and record_request != request_id:
            return False
    if instance_id:
        record_instance = str(
            record.get("restored_instance_id") or record.get("instance_id") or ""
        ).strip()
        if record_instance and record_instance != instance_id:
            return False
    if session_id:
        record_session = str(record.get("restore_session_id") or "").strip()
        if record_session and record_session != session_id:
            return False
    return True


def _active_read_match_score(record: Mapping[str, Any], result: Mapping[str, Any]) -> int:
    """Score how strongly the record matches this run (identity agreement) plus
    timestamp strength (monotonic pairs are the most reliable clock)."""
    score = 0
    request_id = _request_id(result)
    identity = _identity(result)
    if request_id and str(record.get("request_id") or "").strip() == request_id:
        score += 2
    if str(record.get("restored_instance_id") or "").strip() and identity.get("restored_instance_id"):
        score += 2
    if str(record.get("restore_session_id") or "").strip() and identity.get("restore_session_id"):
        score += 2
    if str(record.get("container_session_id") or "").strip() and identity.get("container_session_id"):
        score += 1
    if str(record.get("path_hash") or "").strip():
        score += 1
    pair = _active_read_record_boundary(record)
    if pair is not None and pair[0].monotonic_ns is not None and pair[1].monotonic_ns is not None:
        score += 1  # strong same-clock monotonic timestamps
    return score


def _best_active_read(
    result: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Boundary, Boundary] | None:
    """Pick the safest active-read record: a MODEL read that matches this
    request/instance/restore-session identity and has complete timestamps.

    Returns ``(record, start_boundary, end_boundary)`` or ``None`` when no
    safe match exists (the report then flags ``checkpoint_read_unavailable``
    instead of substituting the H2D span or a foreign read).
    """
    best = None
    best_score = -1
    structured = _as_mapping(result).get("pre_sampler_structured_report")
    for record in _as_mapping(structured).get("active_read_records", ()):
        if not isinstance(record, Mapping):
            continue
        if not _active_read_is_model_read(record):
            continue
        if not _active_read_matches_result(record, result):
            continue
        pair = _active_read_record_boundary(record)
        if pair is None:
            continue
        score = _active_read_match_score(record, result)
        if score > best_score:
            best = (record, pair[0], pair[1])
            best_score = score
    return best


def _identity(result: Mapping[str, Any]) -> dict[str, Any]:
    value = _as_mapping(result).get("identity")
    if isinstance(value, Mapping):
        return dict(value)
    trace = _trace(result)
    metadata = _as_mapping(trace.get("metadata"))
    identity = {}
    identity_keys = (
        "app_name", "class_name", "gpu", "image_id", "cloud", "region",
        "restored_instance_id", "restore_session_id", "container_session_id",
        "workflow_hash_prefix", "modal_task_id", "container_task_id",
        "restore_count", "request_count",
    )
    for key in identity_keys:
        if key in metadata:
            identity[key] = metadata[key]
    for event in _events(result):
        event_meta = _as_mapping(event.get("metadata"))
        for key in identity_keys:
            if not identity.get(key) and event_meta.get(key) not in (None, ""):
                identity[key] = event_meta[key]
    return identity


def _map_cpu_vendor(vendor: Any) -> str:
    """Normalize a CPU vendor id to a short display token: the classic
    ``AuthenticAMD`` / ``GenuineIntel`` ids become ``AMD`` / ``Intel``;
    anything else keeps its first whitespace token."""
    text = str(vendor or "").strip()
    if not text:
        return ""
    if text == "AuthenticAMD":
        return "AMD"
    if text == "GenuineIntel":
        return "Intel"
    return text.split()[0]


def _extract_host_telemetry(
    result: Mapping[str, Any],
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact host-hardware header data from the same result build_waterfall
    consumes (``result_view``).  Every value is optional and never fabricated:
    absent data simply omits the key, so the compact header can never show a
    fake zero.  Reads:

    - GPU from ``gpu_allocation`` (gpu_actual_name / gpu_vram_total_mib /
      cuda_version / gpu_compute_capability).
    - Platform from the resolved identity (cloud / region /
      restored_instance_id / fresh).
    - CPU identity from ``host_hardware_fingerprint`` event metadata
      (cpu_vendor / cpu_family / cpu_model / cpu_count_proc|cpu_count_os|
      cpu_siblings).
    - CPU runtime from ``runtime_shape.observed`` (cpu_request /
      torch_intraop_threads / torch_interop_threads / native_thread_count).
    - CPU pressure from ``trace.activation_diagnosis`` (cpu_peak_cores /
      cpu_above_16_ms).
    - Memory from ``host_memory`` event metadata (process_rss_mib /
      process_maxrss_mib by stage), with a maxRSS fallback from
      ``host_resource_snapshot`` ``ru_maxrss`` (KB -> MiB).
    """
    telemetry: dict[str, Any] = {}
    result_view = _as_mapping(result)

    # ── GPU ────────────────────────────────────────────────────────────────
    gpu_allocation = _as_mapping(result_view.get("gpu_allocation"))
    if gpu_allocation:
        gpu_name = gpu_allocation.get("gpu_actual_name")
        if gpu_name not in (None, ""):
            telemetry["gpu_name"] = str(gpu_name)
        vram = _number(gpu_allocation.get("gpu_vram_total_mib"))
        if vram is not None and vram > 0:
            telemetry["gpu_vram_mib"] = vram
        cuda = gpu_allocation.get("cuda_version")
        if cuda not in (None, ""):
            telemetry["cuda_version"] = str(cuda)
        capability = gpu_allocation.get("gpu_compute_capability")
        if capability not in (None, ""):
            telemetry["compute_capability"] = str(capability)

    # ── Platform / identity ────────────────────────────────────────────────
    resolved = _identity(result_view) if identity is None else identity
    cloud = resolved.get("cloud")
    if cloud not in (None, ""):
        telemetry["cloud"] = str(cloud)
    region = resolved.get("region")
    if region not in (None, ""):
        telemetry["region"] = str(region)
    instance = resolved.get("restored_instance_id")
    if instance not in (None, ""):
        telemetry["restored_instance_id"] = str(instance)
    if "fresh" in resolved:
        telemetry["fresh"] = resolved["fresh"]

    # ── CPU identity (host_hardware_fingerprint event metadata) ────────────
    for meta in _metadata_events(result_view, "host_hardware_fingerprint"):
        vendor = _map_cpu_vendor(meta.get("cpu_vendor"))
        if vendor and "cpu_vendor" not in telemetry:
            telemetry["cpu_vendor"] = vendor
        for out_key, source_key in (
            ("cpu_family", "cpu_family"),
            ("cpu_model", "cpu_model"),
        ):
            value = meta.get(source_key)
            if value not in (None, "") and out_key not in telemetry:
                telemetry[out_key] = str(value)
        visible = (
            meta.get("cpu_count_proc")
            if meta.get("cpu_count_proc") is not None
            else meta.get("cpu_count_os")
            if meta.get("cpu_count_os") is not None
            else meta.get("cpu_siblings")
        )
        visible_num = _number(visible)
        if visible_num is not None and visible_num > 0 and "cpu_visible" not in telemetry:
            telemetry["cpu_visible"] = visible_num

    # ── CPU runtime (runtime_shape.observed) ───────────────────────────────
    runtime_observed = _as_mapping(_as_mapping(result_view.get("runtime_shape")).get("observed"))
    if runtime_observed:
        requested = runtime_observed.get("cpu_request")
        if requested not in (None, ""):
            telemetry["cpu_requested"] = str(requested)
        intra = _number(runtime_observed.get("torch_intraop_threads"))
        if intra is not None and intra > 0:
            telemetry["torch_intraop"] = intra
        inter = _number(runtime_observed.get("torch_interop_threads"))
        if inter is not None and inter > 0:
            telemetry["torch_interop"] = inter
        native = _number(runtime_observed.get("native_thread_count"))
        if native is not None and native > 0:
            telemetry["native_threads"] = native
    if "cpu_requested" not in telemetry:
        identity_runtime = _as_mapping(resolved.get("runtime_shape"))
        identity_request = identity_runtime.get("cpu_request")
        if identity_request not in (None, ""):
            telemetry["cpu_requested"] = str(identity_request)

    # ── CPU pressure (trace.activation_diagnosis) ─────────────────────────
    activation = _as_mapping(_as_mapping(_trace(result_view)).get("activation_diagnosis"))
    if activation:
        peak = activation.get("cpu_peak_cores")
        if isinstance(peak, (int, float)) and not isinstance(peak, bool):
            telemetry["cpu_peak_cores"] = float(peak)
        above = _number(activation.get("cpu_above_16_ms"))
        if above is not None:
            telemetry["cpu_above_16_ms"] = above

    # ── Memory (host_memory events by stage) ───────────────────────────────
    rss_by_stage: dict[str, float] = {}
    max_rss_candidates: list[float] = []
    for meta in _metadata_events(result_view, "host_memory"):
        stage = str(meta.get("stage") or "")
        rss = meta.get("process_rss_mib")
        if isinstance(rss, (int, float)) and not isinstance(rss, bool):
            if stage and stage not in rss_by_stage:
                rss_by_stage[stage] = float(rss)
        maxrss = meta.get("process_maxrss_mib")
        if isinstance(maxrss, (int, float)) and not isinstance(maxrss, bool):
            max_rss_candidates.append(float(maxrss))
    if "restore_start" in rss_by_stage:
        telemetry["rss_restore_mib"] = rss_by_stage["restore_start"]
    elif "restore_complete" in rss_by_stage:
        telemetry["rss_restore_mib"] = rss_by_stage["restore_complete"]
    if "peak_execution" in rss_by_stage:
        telemetry["rss_peak_mib"] = rss_by_stage["peak_execution"]
    if "result_complete" in rss_by_stage:
        telemetry["rss_result_mib"] = rss_by_stage["result_complete"]
    if max_rss_candidates:
        telemetry["max_rss_mib"] = max(max_rss_candidates)
    if "max_rss_mib" not in telemetry:
        # maxRSS fallback: the highest ru_maxrss (KB) across resource
        # snapshots, converted to MiB (KB / 1024 — same convention the
        # host-memory producer uses for process_maxrss_mib).
        ru_values = [
            _number(meta.get("ru_maxrss"))
            for meta in _metadata_events(result_view, "host_resource_snapshot")
        ]
        ru_values = [value for value in ru_values if value is not None and value > 0]
        if ru_values:
            telemetry["max_rss_mib"] = max(ru_values) / 1024.0

    return telemetry


def _request_id(result: Mapping[str, Any]) -> str:
    direct = _as_mapping(result).get("request_id") or _as_mapping(result).get("prompt_id")
    if direct:
        return str(direct)
    trace = _trace(result)
    if trace.get("request_id"):
        return str(trace["request_id"])
    for event in _events(result):
        if event.get("request_id"):
            return str(event["request_id"])
    return ""


# ── Direct output-return boundaries ────────────────────────────────────────
# Consumed from the merged host trace (``remote_result_emit`` /
# ``local_result_received`` / ``execute_plan_return`` events) or from
# ``local_timing`` wall fields.  These are the exact direct-completion /
# host-receipt / caller-return boundaries — never a remote pre-yield span.


def _remote_emit_boundary(result: Mapping[str, Any]) -> Boundary | None:
    """Direct-output completion boundary: the remote result emit (wall or
    monotonic), falling back to the producer's ``remote_result_emit_wall_unix_ns``
    / ``remote_result_emit_mono_ns`` local-timing fields."""
    event = _event_boundary(result, "remote_result_emit", last=True)
    if event is not None:
        return event
    wall = _number(_first_value(result, ("remote_result_emit_wall_unix_ns",)))
    if wall is not None:
        return Boundary("remote_result_emit", wall, None, "remote", "metadata")
    mono = _number(_first_value(result, ("remote_result_emit_mono_ns",)))
    if mono is not None:
        return Boundary("remote_result_emit", None, mono, "remote", "metadata")
    return None


def _local_receipt_boundary(result: Mapping[str, Any]) -> Boundary | None:
    """Exact host local-result receipt boundary: the local receipt event
    (``local_result_received`` / ``final_result_received``) or the producer's
    ``local_result_received_wall_ns`` / ``_mono_ns`` local-timing fields."""
    event = _event_boundary(
        result,
        ("local_result_received", "final_result_received", "response_received"),
        process="local",
        last=True,
    )
    if event is not None:
        return event
    wall = _number(_first_value(result, ("local_result_received_wall_ns",)))
    if wall is not None:
        return Boundary("local_result_received", wall, None, "local", "metadata")
    mono = _number(_first_value(result, ("local_result_received_mono_ns",)))
    if mono is not None:
        return Boundary("local_result_received", None, mono, "local", "metadata")
    return None


def _caller_return_boundary(
    result: Mapping[str, Any],
    response: Boundary | None,
) -> Boundary | None:
    """The caller-return boundary: the exact ``execute_plan_return`` host event
    when present, else the *response* argument (the host's capture after the
    call returns).  Never a remote pre-yield timestamp."""
    event = _event_boundary(result, "execute_plan_return", last=True)
    if event is not None:
        return event
    return response


def _stage_candidate(
    result: Mapping[str, Any],
    key: str,
    *,
    restore_begin: Boundary | None = None,
    python_resume: Boundary | None = None,
    python_restore_end: Boundary | None = None,
    response: Boundary | None = None,
) -> _Candidate:
    event = lambda names, **kwargs: _event_boundary(result, names, **kwargs)
    origin = lambda name: _origin_boundary(result, name, name)
    remote_entry = (
        event("remote_method_entry", process="remote", last=True)
        or event("remote_method_entry", process="remote_method", last=True)
        or event("remote_method_entry", last=True)
    )
    restore_end = _timing_boundary(result, "restore_method_end", "restore_method_end")
    if python_restore_end is None:
        python_restore_end = restore_end
    if key == "local_preparation":
        start = origin("ui_run_triggered_wall_unix_ms") or event("worker_start", process="local")
        end = origin("local_receive_wall_ns") or event(("transport_entry", "modal_handle_lookup_start"), process="local")
        return _candidate(result, start, end)
    if key == "modal_handle_submission":
        start = origin("local_receive_wall_ns") or event(("modal_handle_lookup_start", "transport_entry"), process="local")
        end = origin("modal_submission_attempt_wall_unix_ns") or event(("modal_submission_attempt", "modal_first_iteration_start"), process="local")
        # Prefer the authoritative local submission span from local_timing;
        # handle lookup and payload serialization are its non-overlapping
        # sub-segments.  The first field found becomes the source_fields entry.
        return _candidate(
            result,
            start,
            end,
            duration_keys=(
                "local_receive_to_actual_submission_ms",
                "handle_lookup_ms",
                "payload_serialize_ms",
                "local_submission_ms",
            ),
        )
    if key == "modal_scheduling":
        # Modal scheduling before the snapshot restore begins.  Three tiers:
        #   1. measured submission -> restore_begin (authoritative platform
        #      boundary from the Modal app log)
        #   2. measured submission -> python_resume (combined interval; the
        #      report flags modal_restore_begin_unavailable so the reader
        #      knows scheduling + pre-Python restore are fused here)
        #   3. legacy derived math (dispatch − restore − restore-to-method)
        #   4. unavailable
        submission = _submission_boundary(result)
        if restore_begin is not None:
            candidate = _candidate(result, submission, restore_begin, duration_keys=("modal_submit_to_entry_ms", "submit2entry_ms"))
            if candidate.duration_ms is not None:
                return candidate
        if python_resume is not None:
            candidate = _candidate(result, submission, python_resume, duration_keys=("modal_submit_to_entry_ms", "submit2entry_ms"))
            if candidate.duration_ms is not None:
                return _Candidate(
                    candidate.start, candidate.end, candidate.duration_ms,
                    candidate.source, candidate.status, candidate.clock_scope,
                    source_fields=("submission_to_python_resume_ms",),
                )
        dispatch = _first_value(result, ("dispatch_to_modal_entry_ms",))
        restore = _first_value(result, ("restore_total_ms",))
        restore_to_method = _first_value(result, ("restore_end_to_modal_method_ms",))
        if all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in (dispatch, restore, restore_to_method)
        ):
            return _candidate_from_duration(
                float(dispatch) - float(restore) - float(restore_to_method),
                source="derived",
                source_fields=(
                    "dispatch_to_modal_entry_ms",
                    "restore_total_ms",
                    "restore_end_to_modal_method_ms",
                ),
            )
        return _Candidate()
    if key == "pre_python_snapshot_restore":
        # Modal pre-Python snapshot restoration: restore_begin (platform
        # boundary) -> first restored Python line.  When the platform boundary
        # is absent this is a legitimate localized unknown — the combined
        # interval is already attributed to modal_scheduling — so the stage is
        # explicitly UNAVAILABLE (never fabricated into the residual).
        if restore_begin is None:
            return _Candidate(source="", status=UNAVAILABLE, source_fields=("modal_restore_begin_unavailable",))
        return _candidate(result, restore_begin, python_resume)
    if key == "application_restore":
        return _candidate(result, python_resume, python_restore_end, duration_keys=("restore_total_ms",))
    if key == "restore_to_method_entry":
        start = restore_end
        end = remote_entry
        return _candidate(result, start, end, duration_keys=("restore_end_to_modal_method_ms",))
    if key == "sampler_graph_join_wait":
        # The sampler-boundary graph join: first sampler node -> join
        # completion.  The join is the worker-future wait that was previously
        # hidden inside the residual; the authoritative join span lives on the
        # ``unet_graph_join`` event metadata (join_start_mono_ns /
        # join_completed_mono_ns) or its join_wait_ms.
        join_meta = _event_metadata_value(result, "unet_graph_join", "join_start_mono_ns", last=True)
        join_end_meta = _event_metadata_value(result, "unet_graph_join", "join_completed_mono_ns", last=True)
        if isinstance(join_meta, (int, float)) and isinstance(join_end_meta, (int, float)):
            start = Boundary("sampler_graph_join_wait", None, int(join_meta), "remote", "metadata")
            end = Boundary("sampler_graph_join_wait", None, int(join_end_meta), "remote", "metadata")
            candidate = _candidate(result, start, end)
            if candidate.duration_ms is not None:
                return candidate
        join_wait = _event_metadata_value(result, "unet_graph_join", "join_wait_ms", last=True)
        if isinstance(join_wait, (int, float)) and not isinstance(join_wait, bool):
            return _candidate_from_duration(float(join_wait), source_fields=("unet_graph_join.join_wait_ms",))
        # No ownership-gate join metadata: the stage is genuinely unavailable
        # (never a phantom zero).  The lane-wait span is already attributed to
        # ``sampler_node_to_sampling``, so reusing it here would double count.
        return _Candidate()
    if key == "remote_method_setup":
        start = remote_entry
        end = event("prompt_executor_invoke_start", process="remote") or event("graph_execution_start", process="remote")
        return _candidate(result, start, end, duration_keys=("method_entry_to_graph_start_ms", "method_entry_to_runtime_configuration_ms", "remote_method_setup_ms"))
    if key == "prompt_executor_cache_setup":
        start = event("prompt_executor_invoke_start", process="remote")
        end = event(("graph_first_node", "first_executing_node"), process="remote")
        return _candidate(result, start, end, duration_keys=("executor_call_to_first_node_ms", "exec_start_to_cached_ms", "prompt_executor_cache_setup_ms"))
    if key == "pre_sampler_execution":
        # ONE mutually-exclusive pre-sampler parent: first node -> sampler
        # node.  The first-sampler-node boundary is the strongest exact
        # boundary (pre_sampler_stages.first_sampler_node_monotonic_ns, else
        # the graph-join start); otherwise the consolidated duration is the
        # exact sum of first_node_to_clip_ms + clip_to_sampler_node_ms so the
        # accounted total is byte-identical to the split rows it replaces.
        start = (
            event("graph_first_node", process="remote")
            or event("first_executing_node", process="remote")
            or event(("graph_first_node", "first_executing_node"))
        )
        first_sampler = None
        for metadata in _metadata_events(result, "pre_sampler_stages"):
            value = _number(metadata.get("first_sampler_node_monotonic_ns"))
            if value is not None:
                first_sampler = Boundary("first_sampler_node", None, value, "remote", "metadata")
                break
        if first_sampler is None:
            join_start_meta = _event_metadata_value(result, "unet_graph_join", "join_start_mono_ns", last=True)
            if isinstance(join_start_meta, (int, float)) and not isinstance(join_start_meta, bool):
                first_sampler = Boundary("sampler_graph_join_wait", None, int(join_start_meta), "remote", "metadata")
        candidate = _candidate(result, start, first_sampler)
        if candidate.duration_ms is not None:
            return candidate
        clip_start = _first_value(result, ("first_node_to_clip_ms",))
        clip_lane = _first_value(result, ("clip_to_sampler_node_ms",))
        if (
            isinstance(clip_start, (int, float)) and isinstance(clip_lane, (int, float))
            and not isinstance(clip_start, bool) and not isinstance(clip_lane, bool)
        ):
            return _candidate_from_duration(
                float(clip_start) + float(clip_lane),
                source_fields=("first_node_to_clip_ms", "clip_to_sampler_node_ms"),
            )
        return _Candidate()
    if key == "sampler_node_to_sampling":
        candidate = _candidate(
            result,
            event("sampler_lane_wait_start", process="remote"),
            event(("sampling_start", "sampler_start")),
        )
        if candidate.duration_ms is not None:
            return candidate
        candidate = _metadata_interval(
            result,
            "pre_sampler_stages",
            "first_sampler_node_monotonic_ns",
            "sampling_start_monotonic_ns",
        )
        if candidate.duration_ms is not None:
            return candidate
        value = _first_value(result, ("sampler_node_to_sampler_start_ms", "sampler_node_to_sampling_ms"))
        return _candidate_from_duration(value)
    if key == "sampling":
        start = event("sampling_start") or event("sampler_start")
        end = event("sampling_end") or event("sampler_end")
        candidate = _candidate(result, start, end, duration_keys=("sampler_ms", "sampling_ms"))
        if candidate.duration_ms is not None:
            return candidate
        return _candidate_from_duration(_event_metadata_value(result, "sampling_end", "duration_ms"), source="event")
    if key == "post_sampling_transition":
        return _candidate(
            result,
            event("sampling_end") or event("sampler_end"),
            event("vae_decode_start", process="remote") or event("vae_decode_start"),
            duration_keys=("post_sampling_transition_ms",),
        )
    if key == "vae":
        return _candidate(result, event("vae_decode_start", process="remote"), event("vae_decode_end", process="remote"), duration_keys=("vae_decode_ms",))
    if key == "output_persistence":
        # Output encode/descriptor ENDS at direct completion: the remote result
        # emit boundary when present, else the persist/collect completion.
        start = event("output_encode_start", process="remote") or event("output_persist_start", process="remote")
        end = (
            _remote_emit_boundary(result)
            or event("output_persist_end", process="remote")
            or event("output_collect_end", process="remote")
            or event("output_encode_end", process="remote")
        )
        return _candidate(result, start, end, duration_keys=("output_collection_ms", "output_persist_ms", "output_commit_ms"))
    if key == "remote_local_return":
        # Local result handling / caller return = local receipt -> caller return
        # (execute_plan_return event, else the response argument).  Never the
        # remote pre-yield build time.
        start = _local_receipt_boundary(result)
        end = _caller_return_boundary(result, response)
        return _candidate(result, start, end, duration_keys=("local_result_received_to_caller_return_ms", "result_received_to_return_ms", "remote_return_ms", "trigger_to_result_ms"))
    if key == "remote_return_handoff":
        # Remote result handoff = remote emit -> local receipt.  When the
        # direct emit marker is absent, the last remote completion boundary
        # (persist/collect end) is the fallback start.
        return _candidate(
            result,
            _remote_emit_boundary(result)
            or event("output_persist_end", process="remote", last=True)
            or event("output_collect_end", process="remote", last=True)
            or event("output_persist_end", last=True)
            or event("output_collect_end", last=True),
            _local_receipt_boundary(result),
        )
    return _Candidate()


_STAGE_SPECS: tuple[tuple[str, str, str, bool], ...] = (
    ("local_preparation", "Local preparation", "local", False),
    ("modal_handle_submission", "Modal handle and submission", "local", False),
    ("modal_scheduling", "Modal scheduling before snapshot restore begins", "platform", False),
    ("pre_python_snapshot_restore", "Modal pre-Python snapshot restoration", "platform", False),
    ("application_restore", "Python/application restore", "application", False),
    ("restore_to_method_entry", "Restore-to-method entry", "application", False),
    ("remote_method_setup", "Remote method setup", "application", False),
    ("prompt_executor_cache_setup", "PromptExecutor/cache setup", "application", False),
    # One mutually-exclusive pre-sampler parent: first node -> sampler node.
    # CLIP / UNET / conditioning-cache timings are indented details under it.
    ("pre_sampler_execution", "Pre-sampler execution", "application", False),
    ("sampler_graph_join_wait", "Sampler graph-join wait", "application", False),
    ("sampler_node_to_sampling", "Sampler node to sampling", "application", False),
    ("sampling", "Sampling", "application", False),
    ("post_sampling_transition", "Post-sampling / VAE transition", "application", False),
    ("vae", "VAE decode", "application", False),
    ("output_persistence", "Output encode / descriptor", "application", False),
    ("remote_return_handoff", "Remote result handoff", "local", False),
    ("remote_local_return", "Local result handling / caller return", "local", False),
)


def _stage_interval(candidate: _Candidate) -> tuple[int | None, int | None]:
    if (
        candidate.start is not None
        and candidate.end is not None
        and candidate.start.process == candidate.end.process
        and candidate.start.monotonic_ns is not None
        and candidate.end.monotonic_ns is not None
    ):
        return candidate.start.monotonic_ns, candidate.end.monotonic_ns
    return (
        candidate.start.wall_unix_ns if candidate.start else None,
        candidate.end.wall_unix_ns if candidate.end else None,
    )


def _intervals_overlap(a: WaterfallStage, b: WaterfallStage) -> bool:
    if a.start_ns is None or a.end_ns is None or b.start_ns is None or b.end_ns is None:
        return False
    return bool(a.clock_scope and a.clock_scope == b.clock_scope and max(a.start_ns, b.start_ns) < min(a.end_ns, b.end_ns))


def _seed_apply_marker(result: Mapping[str, Any]) -> Mapping[str, Any]:
    """Authoritative Step 3 seed-apply marker nested on ``executor_seed_apply_end``.

    The executor-apply trace event carries the full per-phase timing dict
    (``validate_ms`` / ``apply_ms`` / ``total_ms``) under ``seed_apply``, which
    is emitted by the executor even when the snapshot-graph events are absent.
    """
    for event in _events(result):
        if event.get("name") != "executor_seed_apply_end":
            continue
        marker = _as_mapping(event.get("metadata")).get("seed_apply")
        if isinstance(marker, Mapping):
            return marker
    return {}


def _seed_phase_duration(
    result: Mapping[str, Any],
    *,
    start_event: str,
    end_event: str,
    fallback_keys: Sequence[str],
) -> _Candidate:
    """Duration for one Step 3 snapshot-graph seed phase (validate or apply).

    Priority:
      1. measured — same-process monotonic pair between the phase's own
         start/end trace events (``snapshot_graph_seed_validate_start`` ->
         ``snapshot_graph_seed_validate_end``, and the apply equivalents)
      2. derived — authoritative metadata for the phase.  ``validate_ms`` is
         NOT carried on ``snapshot_graph_seed_validate_end``; it lives on the
         apply-end metadata (``snapshot_graph_seed_apply_end``) and on the
         nested ``executor_seed_apply_end.seed_apply`` dict, so those are the
         fallback sources.
    Returns a _Candidate whose status is MEASURED, DERIVED or UNAVAILABLE.
    """
    start = _event_boundary(result, start_event)
    end = _event_boundary(result, end_event)
    if start is not None and end is not None:
        if (
            start.process
            and start.process == end.process
            and start.monotonic_ns is not None
            and end.monotonic_ns is not None
        ):
            duration = (end.monotonic_ns - start.monotonic_ns) / 1_000_000.0
            if duration >= 0:
                return _Candidate(
                    start, end, duration, "event", MEASURED,
                    _clock_scope(start, end), (start_event, end_event),
                )
    for key in fallback_keys:
        value = _first_value(result, (key,))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return _Candidate(
                duration_ms=float(value), source="metadata", status=DERIVED,
                clock_scope="metadata", source_fields=(key,),
            )
    marker = _seed_apply_marker(result)
    for key in fallback_keys:
        value = marker.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return _Candidate(
                duration_ms=float(value), source="metadata", status=DERIVED,
                clock_scope="metadata",
                source_fields=(f"executor_seed_apply_end.seed_apply.{key}",),
            )
    return _Candidate()


def _authoritative_cache_decision(
    decisions: Sequence[Mapping[str, Any]],
    result: Mapping[str, Any] | None = None,
) -> tuple[str, Mapping[str, Any]] | None:
    """Pick the authoritative conditioning-cache decision from the trace.

    The producer emits one decision event per prefill.  A real exact hit is
    authoritative even when a later no-op ``miss_not_stored`` event (zero
    encode / zero store / zero miss entries) follows it.  A real miss (stored,
    or a miss with actual encode/store work) supersedes an older hit.  When
    *result* carries a request id, decisions explicitly belonging to another
    request are ignored.
    """
    if not decisions:
        return None
    request_id = _request_id(result) if result is not None else ""
    scoped = []
    for decision in decisions:
        if request_id:
            record_request = str(decision.get("request_id") or "").strip()
            if record_request and record_request != request_id:
                continue
        scoped.append(decision)
    if not scoped:
        scoped = list(decisions)

    def _has_work(decision: Mapping[str, Any], decision_name: str) -> bool:
        if decision_name in ("miss_stored", "miss", "cache_missing"):
            return True
        if decision_name == "miss_not_stored":
            encode = decision.get("encode_calls")
            store = decision.get("cache_store_calls")
            return (
                isinstance(encode, (int, float)) and not isinstance(encode, bool) and encode > 0
            ) or (
                isinstance(store, (int, float)) and not isinstance(store, bool) and store > 0
            )
        return False

    real_misses = [
        d for d in scoped
        if str(d.get("decision") or "").strip() in ("miss_stored", "miss", "cache_missing")
    ]
    exact_hits = [
        d for d in scoped if str(d.get("decision") or "").strip() == "exact_hit"
    ]
    no_ops = [
        d for d in scoped if str(d.get("decision") or "").strip() == "miss_not_stored"
    ]
    # A real miss that performed work supersedes an older hit.
    for decision in real_misses:
        name = str(decision.get("decision") or "").strip()
        if _has_work(decision, name):
            return name, decision
    # An authoritative exact hit wins over any following no-op miss_not_stored.
    if exact_hits:
        return "exact_hit", exact_hits[-1]
    # A miss_not_stored with actual encode/store work is a real miss.
    for decision in no_ops:
        if _has_work(decision, "miss_not_stored"):
            return "miss_not_stored", decision
    # Fall back to the last decision event.
    last = scoped[-1]
    return str(last.get("decision") or "").strip(), last


def _detail_stages(
    result: Mapping[str, Any],
    total_ms: float | None,
    *,
    total_wall_ms: float | None = None,
) -> tuple[WaterfallStage, ...]:
    details: list[WaterfallStage] = []
    detail_specs = (
        ("method_entry_to_graph_start", "method entry to graph start", "remote_method_setup", "method_entry_to_graph_start_ms"),
        ("method_entry_to_runtime_configuration", "method entry to runtime configuration", "remote_method_setup", "method_entry_to_runtime_configuration_ms"),
        ("runtime_configuration", "runtime configuration", "remote_method_setup", "runtime_configuration_ms"),
        ("graph_setup", "graph setup", "remote_method_setup", "graph_setup_ms"),
        ("certificate", "certificate", "remote_method_setup", "certificate_ms"),
        ("preflight", "preflight", "remote_method_setup", "preflight_ms"),
        ("validation", "validation", "remote_method_setup", "validation_ms"),
        ("legacy_runtime_resolution", "legacy runtime resolution", "remote_method_setup", "legacy_runtime_resolution_ms"),
        ("preload_check", "preload check", "remote_method_setup", "preload_check_ms"),
        ("missing_node_repair", "missing-node repair", "remote_method_setup", "missing_node_repair_ms"),
        ("production_registry_setup", "production registry setup", "remote_method_setup", "production_registry_setup_ms"),
        ("pregraph_setup", "pregraph setup", "remote_method_setup", "pregraph_setup_ms"),
        ("executor_reset", "executor reset", "remote_method_setup", "executor_reset_ms"),
        ("sampler_lane_wait", "sampler lane wait", "sampler_node_to_sampling", "sampler_lane_wait_ms"),
        ("residual_before_invoke", "residual before executor invoke", "remote_method_setup", "residual_before_invoke_ms"),
        ("pre_sampler_total", "pre-sampler total", "remote_method_setup", "pre_sampler_total_ms"),
        ("measured_children", "measured pre-sampler children", "remote_method_setup", "measured_children_ms"),
        ("pre_sampler_residual", "pre-sampler residual", "remote_method_setup", "residual_ms"),
        ("executor_invoke_to_execution", "PromptExecutor invoke to execution", "prompt_executor_cache_setup", "invoke_to_execution_start_ms"),
        ("execution_to_cached", "execution to cached", "prompt_executor_cache_setup", "execution_start_to_cached_ms"),
        ("cached_to_first_node", "cached to first node", "prompt_executor_cache_setup", "cached_to_first_node_ms"),
        ("sampler_node_to_lane_acquired", "sampler node to lane acquired", "sampler_node_to_sampling", "sampler_node_to_lane_acquired_ms"),
        ("lane_acquired_to_actual_stage", "lane acquired to actual stage", "sampler_node_to_sampling", "lane_acquired_to_actual_stage_ms"),
        # NOTE: "output_encode" / "output_commit" metadata rows are omitted on
        # purpose — the request-scoped PNG encode / descriptor details are the
        # measured canonical rows (no duplicate clutter).
        ("unet_quiesce_wait", "UNET quiesce wait (diagnostic)", "remote_method_setup", "quiesce_wait_ms"),
        ("unet_transfer_queue_delay", "UNET transfer queue delay", "remote_method_setup", "transfer_queue_delay_ms"),
        ("unet_synchronized_transfer", "UNET synchronized transfer", "remote_method_setup", "synchronized_transfer_ms"),
        ("graph_prefill_activity", "graph/prefill activity", "prompt_executor_cache_setup", "graph_activity_ms"),
    )
    for key, label, parent, metadata_key in detail_specs:
        value = _first_value(result, (metadata_key,))
        candidate = _candidate_from_duration(value)
        details.append(WaterfallStage(
            key=key,
            label=label,
            group="detail",
            start_ns=None,
            end_ns=None,
            duration_ms=candidate.duration_ms,
            cumulative_ms=None,
            percentage=_percentage(candidate.duration_ms, total_ms, total_wall_ms),
            source=candidate.source or "detail",
            status=candidate.status,
            is_detail=True,
            parent_key=parent,
            included_in_total=False,
            clock_scope="metadata",
            provenance=_stage_provenance(candidate) or "remote_trace",
            accounting_role="child",
        ))

    # Step 3: snapshot graph seed validate/apply detail stages.  Rendered from
    # the seed-apply trace event metadata (included_in_total=False so the
    # waterfall reconciliation is preserved — this is a request-scoped span
    # inside prompt-executor/cache setup).
    #
    # ``snapshot_graph_seed_validate_end`` carries only the decision, not a
    # validate duration.  The authoritative per-phase timings live on the
    # apply-end metadata (``snapshot_graph_seed_apply_end`` and the nested
    # ``executor_seed_apply_end.seed_apply`` dict), so each phase prefers its
    # own measured start/end boundary pair and falls back to those fields.
    if {event.get("name") for event in _events(result)} & {
        "snapshot_graph_seed_validate_start",
        "snapshot_graph_seed_validate_end",
        "snapshot_graph_seed_apply_start",
        "snapshot_graph_seed_apply_end",
        "executor_seed_apply_end",
    }:
        for phase_key, phase_label, start_name, end_name, fallback_keys in (
            (
                "snapshot_graph_seed_validate",
                "Snapshot graph seed validate",
                "snapshot_graph_seed_validate_start",
                "snapshot_graph_seed_validate_end",
                ("validate_ms",),
            ),
            (
                "snapshot_graph_seed_apply",
                "Snapshot graph seed apply",
                "snapshot_graph_seed_apply_start",
                "snapshot_graph_seed_apply_end",
                ("apply_ms", "total_ms"),
            ),
        ):
            candidate = _seed_phase_duration(
                result,
                start_event=start_name,
                end_event=end_name,
                fallback_keys=fallback_keys,
            )
            decision = str(
                _event_metadata_value(result, end_name, "decision", last=True)
                or _event_metadata_value(result, "snapshot_graph_seed_apply_end", "decision", last=True)
                or ""
            )
            schema = _event_metadata_value(result, end_name, "schema", last=True)
            if schema is None:
                schema = _event_metadata_value(result, "snapshot_graph_seed_apply_end", "schema", last=True)
            label = phase_label
            if decision:
                label += f" [{decision} schema={schema}]"
            details.append(WaterfallStage(
                key=phase_key,
                label=label,
                group="detail",
                start_ns=None,
                end_ns=None,
                duration_ms=candidate.duration_ms,
                cumulative_ms=None,
                percentage=_percentage(candidate.duration_ms, total_ms, total_wall_ms),
                source=candidate.source or "detail",
                status=candidate.status,
                is_detail=True,
                parent_key="prompt_executor_cache_setup",
                included_in_total=False,
                clock_scope=candidate.clock_scope or "metadata",
                source_fields=candidate.source_fields,
                provenance=_stage_provenance(candidate) or "remote_trace",
                accounting_role="child",
            ))

    # ── Pre-sampler curation: conditioning-cache + CLIP encode ────────────
    # Children of the pre-sampler region (included_in_total=False) so they can
    # never double-count the accounted chain.
    cache_events = _metadata_events(result, "clip_conditioning_cache_lookup")
    decision_events = _metadata_events(result, "clip_conditioning_cache_decision")
    if cache_events or decision_events:
        cache_meta = cache_events[-1] if cache_events else {}
        hit_count = cache_meta.get("hit_count")
        miss_count = cache_meta.get("miss_count")
        entry_count = cache_meta.get("entry_count")
        lookup_ms = cache_meta.get("lookup_wall_ms")
        # Authoritative outcome: a real exact hit wins over a following no-op
        # miss_not_stored; a real miss with encode/store work wins over a hit.
        decision_name, _decision_meta = _authoritative_cache_decision(decision_events, result)
        is_hit = decision_name == "exact_hit"
        if is_hit:
            # Truthful hit row: no contradictory hit/miss counts, no fake
            # duration.  Encode was skipped, shown as status text (no span).
            parts = ["Conditioning cache exact_hit"]
            if isinstance(lookup_ms, (int, float)):
                parts.append(f"lookup={lookup_ms:.3f}ms")
            label = " ".join(parts)
            cache_candidate = _candidate_from_duration(
                lookup_ms,
                source_fields=("clip_conditioning_cache_lookup.lookup_wall_ms",),
            )
            details.append(WaterfallStage(
                key="conditioning_cache_lookup",
                label=label,
                group="detail",
                start_ns=None,
                end_ns=None,
                duration_ms=cache_candidate.duration_ms,
                cumulative_ms=None,
                percentage=_percentage(cache_candidate.duration_ms, total_ms, total_wall_ms),
                source=cache_candidate.source or "detail",
                status=cache_candidate.status,
                is_detail=True,
                parent_key="pre_sampler_execution",
                included_in_total=False,
                clock_scope="metadata",
                source_fields=cache_candidate.source_fields,
                provenance="remote_trace",
                accounting_role="child",
            ))
            # Encode skipped on the hit: status text/detail, no fake duration.
            details.append(WaterfallStage(
                key="clip_encode_skipped",
                label="CLIP encode skipped (cache hit)",
                group="detail",
                start_ns=None,
                end_ns=None,
                duration_ms=None,
                cumulative_ms=None,
                percentage=None,
                source="status",
                status=DERIVED,
                is_detail=True,
                parent_key="pre_sampler_execution",
                included_in_total=False,
                clock_scope="metadata",
                provenance="remote_trace",
                accounting_role="child",
            ))
        else:
            parts = ["Conditioning cache"]
            if decision_name:
                parts.append(f"decision={decision_name}")
            if isinstance(hit_count, (int, float)):
                parts.append(f"hit={int(hit_count)}")
            if isinstance(miss_count, (int, float)):
                parts.append(f"miss={int(miss_count)}")
            if isinstance(entry_count, (int, float)):
                parts.append(f"entries={int(entry_count)}")
            if isinstance(lookup_ms, (int, float)):
                parts.append(f"lookup={lookup_ms:.3f}ms")
            cache_candidate = _candidate_from_duration(
                lookup_ms,
                source_fields=("clip_conditioning_cache_lookup.lookup_wall_ms",),
            )
            details.append(WaterfallStage(
                key="conditioning_cache_lookup",
                label=" ".join(parts),
                group="detail",
                start_ns=None,
                end_ns=None,
                duration_ms=cache_candidate.duration_ms,
                cumulative_ms=None,
                percentage=_percentage(cache_candidate.duration_ms, total_ms, total_wall_ms),
                source=cache_candidate.source or "detail",
                status=cache_candidate.status,
                is_detail=True,
                parent_key="pre_sampler_execution",
                included_in_total=False,
                clock_scope="metadata",
                source_fields=cache_candidate.source_fields,
                provenance="remote_trace",
                accounting_role="child",
            ))

    clip_encode_start = (
        _event_boundary(result, "execution_prefill_encode_start", process="remote")
        or _event_boundary(result, "execution_prefill_encode_start")
    )
    clip_encode_end = (
        _event_boundary(result, "execution_prefill_encode_end", process="remote")
        or _event_boundary(result, "execution_prefill_encode_end")
    )
    encoded_count = _event_metadata_value(result, "execution_prefill_encode_end", "encoded_count", last=True)
    if clip_encode_start is not None or clip_encode_end is not None or encoded_count is not None:
        clip_label = "CLIP encode"
        if isinstance(encoded_count, (int, float)) and not isinstance(encoded_count, bool):
            clip_label += f" ({int(encoded_count)} calls)"
        clip_candidate = _candidate(result, clip_encode_start, clip_encode_end)
        details.append(WaterfallStage(
            key="clip_encode",
            label=clip_label,
            group="detail",
            start_ns=None,
            end_ns=None,
            duration_ms=clip_candidate.duration_ms,
            cumulative_ms=None,
            percentage=_percentage(clip_candidate.duration_ms, total_ms, total_wall_ms),
            source=clip_candidate.source or "detail",
            status=clip_candidate.status,
            is_detail=True,
            parent_key="pre_sampler_execution",
            included_in_total=False,
            clock_scope=clip_candidate.clock_scope or "metadata",
            source_fields=clip_candidate.source_fields,
            provenance=_stage_provenance(clip_candidate) or "remote_trace",
            accounting_role="child",
        ))

    structured = _as_mapping(result).get("pre_sampler_structured_report")
    for index, record in enumerate(_as_mapping(structured).get("cpu_owner_records", ())):
        if not isinstance(record, Mapping):
            continue
        duration = record.get("wall_ms")
        duration_ms = float(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None
        operation = str(record.get("operation") or "operation")
        role = str(record.get("role") or "other")
        details.append(WaterfallStage(
            key=f"cpu_owner_{index}",
            label=f"CPU owner: {operation} [{role}]",
            group="detail",
            start_ns=None,
            end_ns=None,
            duration_ms=duration_ms,
            cumulative_ms=None,
            percentage=_percentage(duration_ms, total_ms, total_wall_ms),
            source="cpu_owner",
            status=DERIVED if isinstance(duration, (int, float)) and not isinstance(duration, bool) else UNAVAILABLE,
            is_detail=True,
            parent_key="pre_sampler_execution",
            included_in_total=False,
            clock_scope="metadata",
            provenance="remote_trace",
            accounting_role="child",
        ))
    _per_node_timings = _as_mapping(structured).get("per_node_timings", ())
    # Wait windows are only needed when node rows will actually render; compute
    # once, lazily, and never let a wait_attribution failure break rendering.
    _wait_windows: Sequence = ()
    if _per_node_timings and extract_wait_windows is not None:
        try:
            _wait_windows = extract_wait_windows(result)
        except Exception:
            _wait_windows = ()
    for index, record in enumerate(_per_node_timings):
        if not isinstance(record, Mapping):
            continue
        duration = record.get("duration_ms")
        duration_ms = float(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None
        start_perf = _number(record.get("start_perf_ns"))
        end_perf = _number(record.get("end_perf_ns"))
        positioned = (
            start_perf is not None
            and end_perf is not None
            and end_perf >= start_perf
        )
        node_label = str(record.get("class_type") or record.get("node_id") or "node")
        # Attribute any wait inside the node's window; the remaining "non-wait"
        # time is the wall minus known waits and may still contain unclassified
        # wait, so it is never labeled "compute".
        _wait_breakdown: dict | None = None
        if _wait_windows:
            try:
                _wait_breakdown = classify_node_wait(record, _wait_windows)
            except Exception:
                _wait_breakdown = None
        _augmented = bool(
            _wait_breakdown
            and _wait_breakdown.get("available")
            and _wait_breakdown.get("wait_total", 0.0) > 0.5
        )
        _display_label = node_label
        if _augmented:
            _non_wait_ms = float(_wait_breakdown.get("node_non_wait_wall", _wait_breakdown.get("node_compute_wall", 0.0)) or 0.0)
            _wait_ms = float(_wait_breakdown.get("wait_total", 0.0) or 0.0)
            _wait_kinds = "|".join(_wait_breakdown.get("wait_kinds") or ())
            _display_label = f"{node_label} — non-wait {_non_wait_ms:.1f}ms + wait {_wait_ms:.1f}ms [{_wait_kinds}]"
        # Node rows are filtered to keep the diagnostics tight: show a node
        # only when it took meaningful time (>= 25 ms) or it is strategic.
        if not (
            (duration_ms is not None and duration_ms >= 25.0)
            or node_label in STRATEGIC_NODE_CLASS_TYPES
        ):
            continue
        _pass_outcome_field = ("pass_outcome:" + str(record.get("pass_outcome")),) if record.get("pass_outcome") else ()
        _wait_provenance_field = (f"wait:{_display_label}",) if _augmented else ()
        details.append(WaterfallStage(
            key=f"node_timing_{index}",
            label=f"Node: {_display_label}",
            group="detail",
            start_ns=start_perf if positioned else None,
            end_ns=end_perf if positioned else None,
            duration_ms=duration_ms,
            cumulative_ms=None,
            percentage=_percentage(duration_ms, total_ms, total_wall_ms),
            source="node_timing",
            status=MEASURED if positioned else (DERIVED if duration_ms is not None else UNAVAILABLE),
            is_detail=True,
            parent_key="pre_sampler_execution",
            included_in_total=False,
            clock_scope="monotonic:remote" if positioned else "metadata",
            source_fields=_pass_outcome_field + _wait_provenance_field,
            provenance="remote_trace",
            accounting_role="child",
        ))
    for index, record in enumerate(_as_mapping(structured).get("active_read_records", ())):
        if not isinstance(record, Mapping):
            continue
        # Records carrying start/end timestamps feed the request-scoped
        # ``unet_checkpoint_read`` span; skipping them here avoids duplicate
        # clutter.  Records with only a duration stay as "Model read:" rows.
        if _active_read_record_boundary(record) is not None:
            continue
        duration = record.get("wall_ms")
        duration_ms = float(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None
        owner = str(record.get("owner") or "model read")
        path_hash = str(record.get("path_hash") or "")
        label = f"Model read: {owner}"
        if path_hash:
            label += f" [{path_hash[:12]}]"
        details.append(WaterfallStage(
            key=f"active_read_{index}",
            label=label,
            group="detail",
            start_ns=None,
            end_ns=None,
            duration_ms=duration_ms,
            cumulative_ms=None,
            percentage=_percentage(duration_ms, total_ms, total_wall_ms),
            source="active_read",
            status=DERIVED if isinstance(duration, (int, float)) and not isinstance(duration, bool) else UNAVAILABLE,
            is_detail=True,
            parent_key="pre_sampler_execution",
            included_in_total=False,
            clock_scope="metadata",
            provenance="remote_trace",
            accounting_role="child",
        ))
    return tuple(details)


def _request_detail_stages(
    result: Mapping[str, Any],
    total_ms: float | None,
    *,
    response: Boundary | None = None,
    stages: Sequence[WaterfallStage] = (),
    existing_children: Sequence[WaterfallStage] = (),
    total_wall_ms: float | None = None,
) -> tuple[WaterfallStage, ...]:
    """Request-scoped nested detail stages: UNET lane, VAE lane, the
    PromptExecutor localized residual, and output/handoff sub-spans.

    Every row is ``included_in_total=False`` (a child of a top-level stage, so
    it can never affect the accounted total).  Only EXISTING raw events and
    metadata are used — an interval whose start/end boundaries are both present
    is MEASURED, a metadata duration alone is DERIVED, and anything else is
    rendered as a localized 'unavailable' (never folded into the global
    residual).

    Event-name notes (verified against model_preload.py):
      - ``unet_fast_disk_to_start/to_end`` and ``unet_fast_disk_bind_start/end``
        are emitted by the native fast-disk UNET loader; the ``complete`` event
        carries ``ctor_ms`` / ``get_model_ms`` / ``bind_ms`` / ``to_wall_ms`` /
        ``to_device_ms`` metadata.
      - ``unet_early_activation_scheduled`` / ``unet_early_activation_terminal``
        bracket the early-activation worker; ``unet_activation_load_start`` is
        the alternative load-start marker.
      - ``unet_graph_join`` carries ``join_start_mono_ns`` /
        ``join_completed_mono_ns`` / ``join_wait_ms``.
      - VAE events use the ``vae_early_activation_*`` names; the
        ``vae_early_activation_reconciliation`` event carries ``load_wall_ms``
        and ``join_wait_ms``.
    """
    details: list[WaterfallStage] = []

    def event(names, **kwargs):
        return _event_boundary(result, names, **kwargs)

    def add(
        key: str, label: str, parent: str, candidate: _Candidate,
        *, overlaps: tuple[str, ...] = (), accounting_role: str | None = None,
    ) -> None:
        # UNET / VAE early-activation lane rows overlap the accounted chain by
        # design: they are overlap_detail (never accounted).  Output/return and
        # PromptExecutor rows are sequential children of an accounted parent.
        if accounting_role is None:
            accounting_role = (
                "overlap_detail"
                if parent in ("pre_sampler_execution", "remote_method_setup",
                              "post_sampling_transition", "vae")
                else "child"
            )
        status = candidate.status
        duration = candidate.duration_ms
        source_fields = candidate.source_fields
        if duration is not None and duration < 0:
            # A negative CHILD interval is a localized anomaly, never a hard
            # INVALID: downgrade to UNAVAILABLE with the reason preserved in
            # source_fields so the diagnostic stays available in artifacts.
            # (Top-level negative anomalies keep INVALID in build_waterfall.)
            status = UNAVAILABLE
            duration = None
            source_fields = source_fields + ("negative_interval",)
        start_ns, end_ns = _stage_interval(candidate)
        details.append(WaterfallStage(
            key=key,
            label=label,
            group="detail",
            start_ns=start_ns,
            end_ns=end_ns,
            duration_ms=duration,
            cumulative_ms=None,
            percentage=_percentage(duration, total_ms, total_wall_ms),
            source=candidate.source or "detail",
            status=status,
            is_detail=True,
            parent_key=parent,
            included_in_total=False,
            clock_scope=candidate.clock_scope or ("metadata" if candidate.status == DERIVED else ""),
            source_fields=source_fields,
            provenance=_stage_provenance(candidate),
            accounting_role=accounting_role,
            overlaps=overlaps,
        ))

    # ── A. UNET lane ──────────────────────────────────────────────────────
    # CLIP/UNET/cache timings are indented overlap details under the single
    # ``pre_sampler_execution`` parent (never numbered top-level rows).
    fast_to_start = event("unet_fast_disk_to_start", process="remote") or event("unet_fast_disk_to_start")
    fast_to_end = event("unet_fast_disk_to_end", process="remote") or event("unet_fast_disk_to_end")
    fast_bind_start = event("unet_fast_disk_bind_start", process="remote") or event("unet_fast_disk_bind_start")
    fast_bind_end = event("unet_fast_disk_bind_end", process="remote") or event("unet_fast_disk_bind_end")
    ea_scheduled = event("unet_early_activation_scheduled", process="remote") or event("unet_early_activation_scheduled")
    ea_terminal = event("unet_early_activation_terminal", process="remote") or event("unet_early_activation_terminal")
    ea_load_start = event("unet_activation_load_start", process="remote") or event("unet_activation_load_start")
    complete_event = event("unet_fast_disk_complete", process="remote") or event("unet_fast_disk_complete")

    # 1. "UNET scheduled -> worker start"
    add("unet_scheduled_to_worker_start", "UNET scheduled -> worker start", "pre_sampler_execution",
        _candidate(result, ea_scheduled, fast_to_start or ea_load_start))

    # 2. "Worker start -> checkpoint read start": active_read records carry
    #    only wall_ms in practice (no start/end ns), so this is usually
    #    unavailable and the read row below covers the span.
    best_read = _best_active_read(result)
    if best_read is not None:
        _read_record, read_start, _read_end = best_read
        add("unet_worker_to_read_start", "Worker start -> checkpoint read start", "pre_sampler_execution",
            _candidate(result, fast_to_start, read_start))
    else:
        add("unet_worker_to_read_start", "Worker start -> checkpoint read start", "pre_sampler_execution", _Candidate())

    # 3. "Checkpoint read": ONLY the active-read record's own span.  There is
    #    NO H2D-pair fallback — when the active read is absent the row is
    #    omitted entirely and the report flags checkpoint_read_unavailable
    #    (required-data failure) instead of substituting another span.
    if best_read is not None:
        _read_record, read_start, read_end = best_read
        add("unet_checkpoint_read", "Checkpoint read", "pre_sampler_execution",
            _candidate(result, read_start, read_end),
            accounting_role="overlap_detail", overlaps=())

    # 4. "Read end -> construction done" + independent "UNET get_model": both
    #    are derived from the complete-event metadata WITHOUT claiming
    #    exclusivity — construction is ctor_ms alone (measured to_end->bind_start
    #    as fallback), get_model is get_model_ms alone.
    ctor_ms = _event_metadata_value(result, "unet_fast_disk_complete", "ctor_ms")
    get_model_ms = _event_metadata_value(result, "unet_fast_disk_complete", "get_model_ms")
    construction_candidate = _Candidate()
    if isinstance(ctor_ms, (int, float)) and not isinstance(ctor_ms, bool):
        construction_candidate = _candidate_from_duration(
            float(ctor_ms), source="metadata", source_fields=("unet_fast_disk_complete.ctor_ms",),
        )
    if construction_candidate.duration_ms is None and fast_bind_start is not None:
        construction_candidate = _candidate(result, fast_to_end, fast_bind_start)
    add("unet_read_to_construction", "Read end -> construction done", "pre_sampler_execution", construction_candidate)
    get_model_candidate = _Candidate()
    if isinstance(get_model_ms, (int, float)) and not isinstance(get_model_ms, bool):
        get_model_candidate = _candidate_from_duration(
            float(get_model_ms), source="metadata", source_fields=("unet_fast_disk_complete.get_model_ms",),
        )
    add("unet_get_model", "UNET get_model", "pre_sampler_execution", get_model_candidate)

    # 5. "Bind": bind_start -> bind_end, else bind_ms metadata on complete.
    bind_ms = _event_metadata_value(result, "unet_fast_disk_complete", "bind_ms")
    bind_candidate = _candidate(result, fast_bind_start, fast_bind_end)
    if bind_candidate.duration_ms is None and isinstance(bind_ms, (int, float)) and not isinstance(bind_ms, bool):
        bind_candidate = _candidate_from_duration(float(bind_ms), source="metadata", source_fields=("unet_fast_disk_complete.bind_ms",))
    add("unet_bind", "Bind", "pre_sampler_execution", bind_candidate)

    # 6. "Synchronized H2D": to_device_ms/to_wall_ms metadata, else the
    #    to_start->to_end pair.  The checkpoint-read row never consumes the
    #    pair (no substitution), so the H2D detail always keeps its own span.
    #    When exact UNET byte metadata exists, effective throughput is shown
    #    as compact non-accounting text on the label (bytes / H2D wall sec).
    h2d_candidate = _Candidate()
    for h2d_key in ("to_device_ms", "to_wall_ms"):
        h2d_value = _event_metadata_value(result, "unet_fast_disk_complete", h2d_key)
        if isinstance(h2d_value, (int, float)) and not isinstance(h2d_value, bool):
            h2d_candidate = _candidate_from_duration(float(h2d_value), source="metadata", source_fields=(f"unet_fast_disk_complete.{h2d_key}",))
            break
    if h2d_candidate.duration_ms is None:
        h2d_candidate = _candidate(result, fast_to_start, fast_to_end)
    h2d_label = "Synchronized H2D"
    h2d_bytes = _event_metadata_value(result, "unet_fast_disk_complete", "parameter_bytes")
    if not isinstance(h2d_bytes, (int, float)) or isinstance(h2d_bytes, bool) or h2d_bytes <= 0:
        h2d_bytes = _first_value(result, ("parameter_bytes", "active_read_size_bytes", "unet_parameter_bytes"))
    h2d_seconds = (h2d_candidate.duration_ms or 0.0) / 1000.0
    if (
        isinstance(h2d_bytes, (int, float))
        and not isinstance(h2d_bytes, bool)
        and h2d_bytes > 0
        and h2d_seconds > 0
    ):
        gbps = h2d_bytes / 1_000_000_000.0 / h2d_seconds
        h2d_label += f" ({gbps:.1f} GB/s)"
    add("unet_synchronized_h2d", h2d_label, "pre_sampler_execution", h2d_candidate)

    # 7. "H2D end -> UNET ready": to_end -> early-activation terminal (or the
    #    fast-disk complete event).
    add("unet_h2d_to_ready", "H2D end -> UNET ready", "pre_sampler_execution",
        _candidate(result, fast_to_end, ea_terminal or complete_event))

    # 8. "UNET ready -> sampler demand": terminal -> graph-join demand
    #    (join_start_mono_ns) or the sampler lane-wait start event.
    join_start_meta = _event_metadata_value(result, "unet_graph_join", "join_start_mono_ns", last=True)
    demand_candidate = _Candidate()
    if (
        ea_terminal is not None
        and ea_terminal.monotonic_ns is not None
        and isinstance(join_start_meta, (int, float))
        and int(join_start_meta) > 0
    ):
        demand_candidate = _candidate(result, ea_terminal, Boundary("unet_graph_join", None, int(join_start_meta), "remote", "metadata"))
    if demand_candidate.duration_ms is None:
        demand_candidate = _candidate(result, ea_terminal, event("sampler_lane_wait_start", process="remote"))
    add("unet_ready_to_demand", "UNET ready -> sampler demand", "pre_sampler_execution", demand_candidate)

    # 9. "Sampler demand -> join complete": join_start -> join_completed
    #    metadata, else join_wait_ms.
    join_end_meta = _event_metadata_value(result, "unet_graph_join", "join_completed_mono_ns", last=True)
    join_wait_ms = _event_metadata_value(result, "unet_graph_join", "join_wait_ms", last=True)
    join_candidate = _Candidate()
    if isinstance(join_start_meta, (int, float)) and isinstance(join_end_meta, (int, float)) and int(join_end_meta) > 0:
        join_candidate = _candidate(
            result,
            Boundary("unet_graph_join", None, int(join_start_meta), "remote", "metadata"),
            Boundary("unet_graph_join", None, int(join_end_meta), "remote", "metadata"),
        )
    if join_candidate.duration_ms is None and isinstance(join_wait_ms, (int, float)) and not isinstance(join_wait_ms, bool):
        join_candidate = _candidate_from_duration(float(join_wait_ms), source_fields=("unet_graph_join.join_wait_ms",))
    add("unet_demand_to_join", "Sampler demand -> join complete", "pre_sampler_execution", join_candidate)

    # 10. "Join complete -> sampling": join_completed -> sampling_start event.
    sampling_start = event("sampling_start", process="remote") or event("sampling_start")
    join_to_sampling = _Candidate()
    if (
        isinstance(join_end_meta, (int, float))
        and int(join_end_meta) > 0
        and sampling_start is not None
        and sampling_start.monotonic_ns is not None
    ):
        join_to_sampling = _candidate(result, Boundary("unet_graph_join", None, int(join_end_meta), "remote", "metadata"), sampling_start)
    add("unet_join_to_sampling", "Join complete -> sampling", "pre_sampler_execution", join_to_sampling)

    # ── B. VAE lane ───────────────────────────────────────────────────────
    sampling_end = event("sampling_end", process="remote") or event("sampling_end")
    vae_scheduled = event("vae_early_activation_scheduled", process="remote") or event("vae_early_activation_scheduled")
    vae_load_start = event("vae_early_activation_load_start", process="remote") or event("vae_early_activation_load_start")
    vae_terminal = event("vae_early_activation_terminal", process="remote") or event("vae_early_activation_terminal")
    vae_consumed = event("vae_early_activation_consumed", process="remote") or event("vae_early_activation_consumed")
    vae_decode_start = event("vae_decode_start", process="remote") or event("vae_decode_start")

    # 1. "Sampling end -> VAE scheduled"
    add("vae_sampling_end_to_scheduled", "Sampling end -> VAE scheduled", "post_sampling_transition",
        _candidate(result, sampling_end, vae_scheduled))
    # 2. "VAE scheduled -> worker/load start"
    add("vae_scheduled_to_load", "VAE scheduled -> worker/load start", "post_sampling_transition",
        _candidate(result, vae_scheduled, vae_load_start))
    # 3. "VAE load/H2D": load_start -> terminal, else reconciliation load_wall_ms.
    vae_load_ms = _event_metadata_value(result, "vae_early_activation_reconciliation", "load_wall_ms")
    vae_load_candidate = _candidate(result, vae_load_start, vae_terminal)
    if vae_load_candidate.duration_ms is None and isinstance(vae_load_ms, (int, float)) and not isinstance(vae_load_ms, bool):
        vae_load_candidate = _candidate_from_duration(float(vae_load_ms), source="metadata", source_fields=("vae_early_activation_reconciliation.load_wall_ms",))
    add("vae_load", "VAE load/H2D", "vae", vae_load_candidate)
    # 4. "VAE ready -> consumed": terminal -> consumed, else reconciliation join_wait_ms.
    vae_join_ms = _event_metadata_value(result, "vae_early_activation_reconciliation", "join_wait_ms")
    vae_join_candidate = _candidate(result, vae_terminal, vae_consumed)
    if vae_join_candidate.duration_ms is None and isinstance(vae_join_ms, (int, float)) and not isinstance(vae_join_ms, bool):
        vae_join_candidate = _candidate_from_duration(float(vae_join_ms), source="metadata", source_fields=("vae_early_activation_reconciliation.join_wait_ms",))
    add("vae_ready_to_consumed", "VAE ready -> consumed", "vae", vae_join_candidate)
    # 5. "Consumed -> decode start" (the decode itself is the top-level vae stage).
    add("vae_consumed_to_decode", "Consumed -> decode start", "vae",
        _candidate(result, vae_consumed, vae_decode_start))

    # ── C. PromptExecutor localized residual ──────────────────────────────
    # This row is the LOCALIZED internal gap (parent minus measured children)
    # of ``prompt_executor_cache_setup``.  It is a child row — it never flows
    # into the global residual.
    cached_parent = next((stage for stage in stages if stage.key == "prompt_executor_cache_setup"), None)
    cached_children = [
        detail for detail in tuple(existing_children) + tuple(details)
        if detail.parent_key == "prompt_executor_cache_setup"
        and detail.duration_ms is not None
        and detail.status != INVALID
    ]
    cached_sum = sum((child.duration_ms or 0.0) for child in cached_children) if cached_children else None
    cached_residual_candidate = _Candidate()
    if (
        cached_parent is not None
        and cached_parent.duration_ms is not None
        and cached_sum is not None
        and cached_parent.duration_ms > cached_sum
    ):
        cached_residual_candidate = _Candidate(
            duration_ms=round(cached_parent.duration_ms - cached_sum, 6),
            source="derived",
            status=DERIVED,
            clock_scope="metadata",
            source_fields=("prompt_executor_cache_setup.duration_ms", "measured_children_sum"),
        )
    add("prompt_executor_internal", "PromptExecutor internal/unattributed", "prompt_executor_cache_setup", cached_residual_candidate)

    # ── D. Output / handoff ───────────────────────────────────────────────
    output_encode_start = event("output_encode_start", process="remote") or event("output_encode_start")
    output_encode_end = event("output_encode_end", process="remote") or event("output_encode_end")
    output_persist_end = event("output_persist_end", process="remote") or event("output_persist_end")
    output_collect_end = event("output_collect_end", process="remote") or event("output_collect_end")

    # 1. "VAE end -> output encode start"
    vae_decode_end = event("vae_decode_end", process="remote") or event("vae_decode_end")
    add("output_vae_end_to_encode", "VAE end -> output encode start", "output_persistence",
        _candidate(result, vae_decode_end, output_encode_start))
    # 2. "PNG encode": encode_start -> encode_end, else output_encode_ms.
    encode_ms = _first_value(result, ("output_encode_ms",))
    encode_candidate = _candidate(result, output_encode_start, output_encode_end)
    if encode_candidate.duration_ms is None and isinstance(encode_ms, (int, float)) and not isinstance(encode_ms, bool):
        encode_candidate = _candidate_from_duration(float(encode_ms), source="metadata", source_fields=("output_encode_ms",))
    add("output_png_encode", "PNG encode", "output_persistence", encode_candidate)
    # 3. "Descriptor/materialization": encode_end -> persist_end, else output_commit_ms.
    commit_ms = _first_value(result, ("output_commit_ms",))
    descriptor_candidate = _candidate(result, output_encode_end, output_persist_end)
    if descriptor_candidate.duration_ms is None and isinstance(commit_ms, (int, float)) and not isinstance(commit_ms, bool):
        descriptor_candidate = _candidate_from_duration(float(commit_ms), source="metadata", source_fields=("output_commit_ms",))
    add("output_descriptor", "Descriptor/materialization", "output_persistence", descriptor_candidate)

    # 4. "Remote result emitted": the direct-completion emission boundary that
    #    the handoff stage already consumes — rendered as a marker child with
    #    the same boundary info (no fabricated span).
    emitted_source = (
        _remote_emit_boundary(result) or output_collect_end or output_persist_end
    )
    if emitted_source is not None:
        emitted_candidate = _Candidate(
            start=None, end=emitted_source,
            duration_ms=None, source="derived", status=DERIVED,
            clock_scope="wall", source_fields=(emitted_source.name,),
        )
    else:
        emitted_candidate = _Candidate()
    add("output_remote_emitted", "Remote result emitted", "remote_return_handoff", emitted_candidate)

    # 5. "Deferred persistence after yield": deferred_commit_start -> end
    #    (emitted on the teardown trace; when absent -> localized unavailable).
    add("output_deferred_commit", "Deferred persistence after yield", "remote_return_handoff",
        _candidate(result, event("deferred_commit_start"), event("deferred_commit_end", last=True)))

    return tuple(details)


def build_waterfall(
    *,
    result: Mapping[str, Any],
    timing: Mapping[str, Any],
    wall_ms: float | None,
    command_start_unix_ms: int | None = None,
    response_received_unix_ns: int | None = None,
    run_label: str = "",
    modal_restore_begin_wall_unix_ns: int | None = None,
) -> WaterfallReport:
    """Build a pure, additive report from a completed result.

    ``timing`` is intentionally accepted separately because older benchmark
    artifacts expose useful derived fields there.  Neither input is mutated.

    ``modal_restore_begin_wall_unix_ns`` (ns) is the Modal platform restore-begin
    boundary (scheduler hands the restored container to Python); when absent it
    is looked up in the result/timing dicts, and when still absent the report
    flags ``modal_restore_begin_unavailable`` and ``modal_scheduling`` covers
    the combined submission -> python_resume interval instead.
    """
    result_view: Mapping[str, Any] = dict(result)
    if timing:
        result_view = {**result_view, "timing": dict(timing)}
    warnings: list[str] = []
    command_start = _command_boundary(command_start_unix_ms)
    response = _response_boundary(response_received_unix_ns)
    # The caller-return boundary is the exact execute_plan_return host event
    # when present, else the *response* argument (host capture).  Never a
    # remote pre-yield timestamp.
    caller_return = _caller_return_boundary(result_view, response)
    restore_begin = _modal_restore_begin_boundary(result_view, modal_restore_begin_wall_unix_ns)
    python_resume = _python_resume_boundary(result_view)
    python_restore_end = _timing_boundary(result_view, "restore_method_end", "restore_method_end")
    submission = _submission_boundary(result_view)
    boundary_flags: list[str] = []
    if restore_begin is None:
        boundary_flags.append("modal_restore_begin_unavailable")
    if submission is None:
        boundary_flags.append("submission_boundary_unavailable")
    stages: list[WaterfallStage] = []
    for key, label, group, concurrent in _STAGE_SPECS:
        if key == "local_preparation" and command_start is not None:
            candidate = _candidate(
                result_view,
                command_start,
                _origin_boundary(result_view, "local_receive_wall_ns", "local_receive_wall_ns")
                or _event_boundary(result_view, ("transport_entry", "modal_handle_lookup_start"), process="local"),
            )
        else:
            candidate = _stage_candidate(
                result_view, key,
                restore_begin=restore_begin,
                python_resume=python_resume,
                python_restore_end=python_restore_end,
                response=response,
            )
        start_ns, end_ns = _stage_interval(candidate)
        status = candidate.status
        duration = candidate.duration_ms
        if duration is not None and duration < 0:
            status = INVALID
            warnings.append(f"{label}: negative duration")
            duration = None
        # The whole scheduling window (enqueue + placement) is informational:
        # local_preparation / modal_handle_submission / modal_scheduling are
        # never numbered rows, never accounted/cumulative/%/bar.  The window is
        # summarized once at the bottom (Scheduling time), and the stage
        # percentages/bars use the non-scheduling wall as their denominator.
        is_scheduling_window = key in (
            "local_preparation", "modal_handle_submission", "modal_scheduling",
        )
        stages.append(WaterfallStage(
            key=key,
            label=label,
            group=group,
            start_ns=start_ns,
            end_ns=end_ns,
            duration_ms=duration,
            cumulative_ms=None,
            percentage=None,
            source=candidate.source,
            status=status,
            clock_scope=candidate.clock_scope,
            source_fields=candidate.source_fields,
            concurrent=concurrent,
            provenance=_stage_provenance(candidate),
            accounting_role="informational" if is_scheduling_window else "top_level",
            included_in_total=not is_scheduling_window,
        ))

    total: float | None
    if command_start is not None and caller_return is not None:
        total = _duration_between(command_start, caller_return)
        if total is not None and total < 0:
            warnings.append("command-to-response duration is negative")
            total = None
    else:
        raw_total = _as_mapping(result).get("wall_ms")
        total_value = raw_total if isinstance(raw_total, (int, float)) else wall_ms
        total = float(total_value) if isinstance(total_value, (int, float)) else None
        if total is not None and total < 0:
            warnings.append("command-to-response duration is negative")
            total = None

    if total is not None and total >= 0:
        for index, stage in enumerate(stages):
            if stage.duration_ms is not None and stage.duration_ms > total:
                warnings.append(f"{stage.label}: duration exceeds command-to-response total")
                stages[index] = WaterfallStage(**{**stage.__dict__, "status": INVALID})

    for index, stage in enumerate(stages):
        if stage.concurrent:
            # Intentional concurrency: the worker claim/ready spans overlap the
            # graph-side stages by design (the whole point of early
            # activation).  They are reported as explicit stages but are not
            # part of the sequential accounted total, so they can never
            # inflate or invalidate the reconciliation.
            continue
        overlaps = tuple(
            other.label for other in stages[:index]
            if not other.concurrent and _intervals_overlap(stage, other)
        )
        if overlaps:
            warnings.append(f"{stage.label}: overlaps {', '.join(overlaps)}")
            stages[index] = WaterfallStage(**{**stage.__dict__, "overlaps": overlaps, "status": INVALID})

    scheduling_stage = next((stage for stage in stages if stage.key == "modal_scheduling"), None)
    scheduling_ms = (
        scheduling_stage.duration_ms
        if scheduling_stage is not None
        and scheduling_stage.status != INVALID
        else None
    )
    total_wall_ms = (
        total - scheduling_ms
        if total is not None
        and scheduling_ms is not None
        and total >= scheduling_ms >= 0
        else None
    )
    # ── New timing contract ────────────────────────────────────────────────
    # Scheduling time = (command -> Modal enqueue) + (Modal scheduling /
    # placement).  Everything else (startup, restore, execution, output,
    # response) is NON-scheduling, derived as total - scheduling_time so the
    # invariant COMMAND->RESPONSE == scheduling + non-scheduling holds by
    # construction (drift is display rounding only).
    command_to_enqueue_ms: float | None = None
    if command_start is not None and submission is not None:
        enq = _duration_between(command_start, submission)
        if enq is not None and enq >= 0:
            command_to_enqueue_ms = enq
    if command_to_enqueue_ms is None:
        # Fallback: the two local scheduling-window stages tile the enqueue
        # span when both are measured and valid.
        enqueue_stages = {
            stage.key: stage for stage in stages
            if stage.key in ("local_preparation", "modal_handle_submission")
        }
        local_prep = enqueue_stages.get("local_preparation")
        handle = enqueue_stages.get("modal_handle_submission")
        if (
            local_prep is not None and handle is not None
            and local_prep.duration_ms is not None
            and handle.duration_ms is not None
            and local_prep.duration_ms >= 0
            and handle.duration_ms >= 0
            and local_prep.status != INVALID
            and handle.status != INVALID
        ):
            command_to_enqueue_ms = local_prep.duration_ms + handle.duration_ms
    scheduling_time_ms: float | None = None
    if (
        command_to_enqueue_ms is not None
        and scheduling_ms is not None
        and command_to_enqueue_ms >= 0
        and scheduling_ms >= 0
    ):
        scheduling_time_ms = command_to_enqueue_ms + scheduling_ms
        if total is not None and scheduling_time_ms > total:
            warnings.append("scheduling exceeds command-to-response total")
            scheduling_time_ms = None
    non_scheduling_ms: float | None = None
    if (
        total is not None
        and scheduling_time_ms is not None
        and total >= scheduling_time_ms >= 0
    ):
        non_scheduling_ms = total - scheduling_time_ms
    partial_flags: list[str] = []
    if submission is None:
        partial_flags.append("missing_submission")
    if restore_begin is None:
        partial_flags.append("missing_modal_restore_begin")
    if _local_receipt_boundary(result_view) is None:
        partial_flags.append("missing_local_result_receipt")
    partial_waterfall = bool(partial_flags)

    # Pre-Python interval classification (REMOTE/PARTIAL only): when the
    # scheduling / restore-begin boundaries are unavailable but the host has
    # supplied the command start -> python resume interval, record it as a
    # reconciliation-pending footer quantity (never a numbered stage).
    pre_python_interval_ms: float | None = None
    pre_python_interval_classification = ""
    if partial_waterfall and restore_begin is None:
        interval_value = _first_value(result_view, ("command_start_to_restore_start_ms", "command_start_to_python_resume_ms"))
        if isinstance(interval_value, (int, float)) and not isinstance(interval_value, bool):
            pre_python_interval_ms = float(interval_value)
            pre_python_interval_classification = "scheduling + pre-Python restore (unresolved platform interval)"

    # Required-data flags: the checkpoint read is only measurable from the
    # active-read record; when the UNET lane ran but no record is available it
    # is an explicit required-data failure, never a substituted H2D span.
    data_flags: list[str] = []
    if _best_active_read(result_view) is None and _event_boundary(
        result_view,
        ("unet_ownership_claim", "unet_fast_disk_to_start", "unet_fast_disk_complete"),
    ) is not None:
        data_flags.append("checkpoint_read_unavailable")

    # ── Accounting: exclusive top-level sum vs the non-scheduling wall ──────
    # Only accounting_role == "top_level", non-concurrent, valid stages count.
    # Detail / overlap_detail / informational rows never alter the accounted
    # total.  Non-scheduling wall = command->response minus scheduling time
    # (enqueue + placement); total_wall_ms is kept as the internal fallback.
    accounted_denom = non_scheduling_ms if non_scheduling_ms is not None else total_wall_ms
    accounted_values = [
        stage.duration_ms
        for stage in stages
        if stage.accounting_role == "top_level"
        and stage.included_in_total
        and not stage.concurrent
        and stage.duration_ms is not None
        and stage.status != INVALID
    ]
    accounted_before_residual = sum(accounted_values)

    cumulative = 0.0
    completed: list[WaterfallStage] = []
    for stage in stages:
        if (
            stage.accounting_role == "top_level"
            and stage.duration_ms is not None
            and stage.status != INVALID
            and not stage.concurrent
        ):
            cumulative += stage.duration_ms
            cum_value: float | None = cumulative
        else:
            cum_value = None
        percentage = (
            _percentage(stage.duration_ms, total, accounted_denom)
            if stage.accounting_role == "top_level" and not stage.concurrent
            else None
        )
        completed.append(WaterfallStage(**{**stage.__dict__, "cumulative_ms": cum_value, "percentage": percentage}))
    stages = completed

    accounted = accounted_before_residual if accounted_values else None
    # Reconciliation compares the exclusive top-level sum to the non-scheduling
    # wall.  residual_ms is reconciliation metadata (never a numbered stage).
    reconciliation = (
        accounted_denom - accounted
        if accounted_denom is not None and accounted is not None
        else None
    )
    residual = reconciliation
    tolerance = RECONCILIATION_HARD_MS if reconciliation is not None else None
    if reconciliation is not None:
        if abs(reconciliation) > RECONCILIATION_TARGET_MS:
            warnings.append(
                f"reconciliation exceeds 10ms target: {reconciliation:.3f}ms"
            )
        if abs(reconciliation) > RECONCILIATION_HARD_MS:
            warnings.append(
                f"reconciliation exceeds tolerance: {reconciliation:.3f}ms > {RECONCILIATION_HARD_MS:.3f}ms"
            )

    residual_pct = _percentage(residual, total, accounted_denom)
    if reconciliation is None:
        reconciliation_status = "UNRESOLVED" if partial_waterfall else ""
    elif abs(reconciliation) <= RECONCILIATION_HARD_MS:
        reconciliation_status = "OK"
    else:
        reconciliation_status = "EXCEEDS_TOLERANCE"
    # Validation can only be declared COMPLETE when no required-data flag
    # exists AND reconciliation is resolved within the hard ceiling.
    if data_flags:
        diagnostic_status = "INCOMPLETE"
    elif reconciliation is None:
        diagnostic_status = "UNRESOLVED" if partial_waterfall else "UNKNOWN"
    elif abs(reconciliation) <= RECONCILIATION_HARD_MS:
        diagnostic_status = "COMPLETE"
    else:
        diagnostic_status = "FAILED"
    included_stages = [
        stage for stage in stages
        if stage.accounting_role == "top_level" and not stage.concurrent
        and stage.duration_ms is not None and stage.status != INVALID
    ]
    controllable_wall_ms = sum(
        (stage.duration_ms or 0.0) for stage in included_stages
        if stage.group in ("local", "application")
    ) if included_stages else None
    # Platform wall includes the informational Modal scheduling span.
    platform_wall_ms = sum(
        (stage.duration_ms or 0.0) for stage in stages
        if stage.group == "platform"
        and stage.duration_ms is not None
        and stage.status != INVALID
    ) if stages else None

    identity = _identity(result)
    details = _detail_stages(result_view, total, total_wall_ms=total_wall_ms)
    details += _request_detail_stages(
        result_view, total,
        response=response,
        stages=tuple(stages),
        existing_children=details,
        total_wall_ms=total_wall_ms,
    )
    if "fresh" not in identity:
        restore_count = identity.get("restore_count")
        request_count = identity.get("request_count")
        if restore_count is not None or request_count is not None:
            identity["fresh"] = str(restore_count) == "1" and str(request_count or "1") == "1"
        else:
            identity["fresh"] = "unknown"
    host_telemetry = _extract_host_telemetry(result_view, identity)
    return WaterfallReport(
        run_label=run_label,
        request_id=_request_id(result_view),
        identity=identity,
        total_ms=total,
        stages=tuple(stages),
        reconciliation_ms=reconciliation,
        warnings=tuple(dict.fromkeys(warnings)),
        accounted_ms=accounted,
        tolerance_ms=tolerance,
        details=details,
        residual_ms=residual,
        residual_pct=residual_pct,
        reconciliation_status=reconciliation_status,
        controllable_wall_ms=controllable_wall_ms,
        platform_wall_ms=platform_wall_ms,
        boundary_flags=tuple(boundary_flags),
        scheduling_ms=scheduling_ms,
        total_wall_ms=total_wall_ms,
        command_response_ms=total,
        command_to_enqueue_ms=command_to_enqueue_ms,
        scheduling_time_ms=scheduling_time_ms,
        non_scheduling_ms=non_scheduling_ms,
        host_telemetry=host_telemetry,
        partial_waterfall=partial_waterfall,
        partial_flags=tuple(partial_flags),
        pre_python_interval_ms=pre_python_interval_ms,
        pre_python_interval_classification=pre_python_interval_classification,
        data_flags=tuple(data_flags),
        reconciliation_target_ms=RECONCILIATION_TARGET_MS,
        reconciliation_hard_ms=RECONCILIATION_HARD_MS,
        diagnostic_status=diagnostic_status,
    )


def _fmt_duration(value: float | None, status: str = "") -> str:
    """Honest duration formatting: >= 1 s prints seconds, < 1 s prints
    milliseconds (3 decimals) so a real sub-millisecond interval never reads
    ``0.000s``.  Both forms are 10 chars wide to keep the table aligned."""
    if status == INVALID:
        return "INVALID"
    if value is None:
        return "-"
    if value >= 1000.0:
        return f"{value / 1000.0:9.3f}s"
    return f"{value:7.3f} ms"


def _fmt_num(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{value:7.3f}{suffix}"


def _shorten(value: str, width: int) -> str:
    value = _ascii_text(value).replace("\r", " ").replace("\n", " ")
    if len(value) <= width:
        return value.ljust(width)
    if width <= 3:
        return value[:width]
    return (value[: width - 3] + "...").ljust(width)


def _ascii_text(value: Any) -> str:
    return str(value).encode("ascii", "replace").decode("ascii")


def _percentage(duration_ms, total_ms, total_wall_ms):
    denom = total_wall_ms if (total_wall_ms is not None and total_wall_ms > 0) else total_ms
    return (duration_ms / denom * 100.0 if duration_ms is not None and denom and denom > 0 else None)


def _bar(stage: WaterfallStage, total_wall_ms: float | None, width: int = 40) -> str:
    """Fixed-width '#'-only bar, top-level rows only, non-scheduling
    denominator (command->response minus scheduling time; internal
    ``total_wall_ms`` is the fallback)."""
    if stage.concurrent:
        return " " * width
    if stage.duration_ms is None or total_wall_ms is None or total_wall_ms <= 0:
        return " " * width
    units = max(1, round(stage.duration_ms / total_wall_ms * width))
    return ("#" * min(width, units)).ljust(width)


# ── Detail curation ────────────────────────────────────────────────────────
# Optional child rows under 25 ms are omitted unless strategically important
# AND useful (the curated set).  Diagnostic aggregates and duplicative CLIP/
# UNET/owner rows are hidden even when large.  Everything stays in the
# serialized artifact; only the console is curated.
_DETAIL_USEFUL_MIN_MS = 25.0
_CURATED_DETAIL_KEYS = frozenset({
    "conditioning_cache_lookup",   # conditioning cache decision/lookup
    "clip_encode",                 # CLIP encode (clearest single CLIP row)
    "clip_encode_skipped",         # status text when encode was skipped (cache hit)
    "unet_checkpoint_read",        # real active-read span
    "unet_read_to_construction",   # construction
    "unet_get_model",              # required get_model
    "unet_bind",                   # bind
    "unet_synchronized_h2d",       # H2D
    "unet_h2d_to_ready",           # H2D -> ready
    "vae_load",                    # VAE H2D
    "output_png_encode",           # PNG encode
})
_DETAIL_ALWAYS_HIDE_KEYS = frozenset({
    "pre_sampler_total", "measured_children", "pre_sampler_residual",
    "graph_prefill_activity", "output_remote_emitted",
    "vae_sampling_end_to_scheduled", "vae_scheduled_to_load",
    "vae_ready_to_consumed", "vae_consumed_to_decode",
})
# Node classes whose timing is already covered by a clearer curated detail
# (CLIP encode / conditioning cache / UNET lane) — never duplicated.
_DUPLICATIVE_NODE_CLASSES = frozenset({
    "CLIPTextEncode", "CLIPTextEncodeWithModel", "UNETLoader", "CLIPLoader",
})


def _detail_is_useful(detail: WaterfallStage) -> bool:
    """Console curation for inline child rows (artifact is never filtered)."""
    if detail.status in (UNAVAILABLE, INVALID):
        return False
    if detail.key in _CURATED_DETAIL_KEYS:
        # Curated rows render whenever present — including status-only rows
        # with no measured duration (e.g. "CLIP encode skipped (cache hit)")
        # and explicitly-required rows of any size.
        return True
    if detail.duration_ms is None or detail.duration_ms <= 0.0:
        return False
    if detail.key in _DETAIL_ALWAYS_HIDE_KEYS:
        return False
    if detail.source == "node_timing":
        label = detail.label
        class_type = label[len("Node: "):] if label.startswith("Node: ") else label
        if class_type in _DUPLICATIVE_NODE_CLASSES:
            # Covered by a clearer curated detail (CLIP encode / conditioning
            # cache / UNET lane): never duplicated.
            return False
        if detail.duration_ms >= _DETAIL_USEFUL_MIN_MS:
            return True
        return class_type in STRATEGIC_NODE_CLASS_TYPES
    if detail.source == "cpu_owner":
        # Dedupe: the CLIP encode detail is the clearest single CLIP row.
        return False
    return detail.duration_ms >= _DETAIL_USEFUL_MIN_MS


def _fmt_peak_cores(value: float) -> str:
    """Format a peak-core count with up to 2 decimals, trailing zeros stripped
    (``7.1333`` -> ``7.13``, ``7.0`` -> ``7``)."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _trim_gpu_name(name: str) -> str:
    """Trim marketing prefixes/suffixes so the compact header stays short:
    leading ``NVIDIA `` / ``AMD `` / ``Intel `` and trailing `` Server Edition``."""
    for prefix in ("NVIDIA ", "AMD ", "Intel "):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    if name.endswith(" Server Edition"):
        name = name[: -len(" Server Edition")]
    return name.strip()


def _render_compact_header(report: WaterfallReport) -> list[str]:
    """Compact host header shared by BOTH renderers.

    Four lines (labels padded to width 10, values joined by `` | ``):
      1. Request / Instance / Fresh (always emitted).
      2. Platform (cloud/region) + optional GPU / VRAM / CUDA / CC segments.
      3. CPU identity + runtime segments (omitted entirely when no data).
      4. Telemetry (CPU pressure / RSS / maxRSS) (omitted when no data).

    Every segment is optional and omitted (never faked as ``0``) when its data
    is missing, then one blank line separates the header from the table.
    """
    telemetry = report.host_telemetry or {}
    identity = report.identity
    lines: list[str] = []

    # Line 1 — always emitted.
    request = _ascii_text(report.request_id or "-")
    instance = _ascii_text(identity.get("restored_instance_id") or "-")
    fresh_value = identity.get("fresh")
    fresh = "YES" if fresh_value is True else "NO" if fresh_value is False else "-"
    lines.append(f"{'Request:':<10} {request} | Instance: {instance} | Fresh: {fresh}")

    # Line 2 — Platform + optional GPU segments.
    platform = _provider_region(report) or "-"
    platform_segments = [_ascii_text(platform)]
    gpu_name = telemetry.get("gpu_name")
    if gpu_name:
        platform_segments.append(f"GPU: {_ascii_text(_trim_gpu_name(str(gpu_name)))}")
    vram = telemetry.get("gpu_vram_mib")
    if vram is not None:
        platform_segments.append(f"VRAM {int(vram):,} MiB")
    cuda = telemetry.get("cuda_version")
    if cuda:
        platform_segments.append(f"CUDA {_ascii_text(cuda)}")
    capability = telemetry.get("compute_capability")
    if capability:
        platform_segments.append(f"CC {_ascii_text(capability)}")
    lines.append(f"{'Platform:':<10} " + " | ".join(platform_segments))

    # Line 3 — CPU identity + runtime (omitted entirely when no data).
    cpu_segments: list[str] = []
    vendor = telemetry.get("cpu_vendor")
    family = telemetry.get("cpu_family")
    model = telemetry.get("cpu_model")
    if vendor and family and model:
        cpu_segments.append(
            f"{_ascii_text(vendor)} Family {_ascii_text(family)} Model {_ascii_text(model)}"
        )
    visible = telemetry.get("cpu_visible")
    if visible is not None:
        cpu_segments.append(f"visible={int(visible)}")
    requested = telemetry.get("cpu_requested")
    if requested:
        cpu_segments.append(f"requested={_ascii_text(requested)}")
    intra = telemetry.get("torch_intraop")
    inter = telemetry.get("torch_interop")
    if intra is not None and inter is not None:
        cpu_segments.append(f"Torch={int(intra)}/{int(inter)}")
    native = telemetry.get("native_threads")
    if native is not None:
        cpu_segments.append(f"native={int(native)}")
    if cpu_segments:
        lines.append(f"{'CPU:':<10} " + " | ".join(cpu_segments))

    # Line 4 — Telemetry (omitted entirely when no data).
    telemetry_segments: list[str] = []
    peak = telemetry.get("cpu_peak_cores")
    if peak is not None:
        telemetry_segments.append(f"CPU peak={_fmt_peak_cores(float(peak))} cores")
    above = telemetry.get("cpu_above_16_ms")
    if above is not None:
        telemetry_segments.append(f">16 cores={int(above)}ms")
    rss_restore = telemetry.get("rss_restore_mib")
    rss_peak = telemetry.get("rss_peak_mib")
    rss_result = telemetry.get("rss_result_mib")
    if rss_restore is not None and rss_peak is not None and rss_result is not None:
        telemetry_segments.append(
            f"RSS {rss_restore / 1024.0:.2f} -> {rss_peak / 1024.0:.2f} -> {rss_result / 1024.0:.2f} GiB"
        )
    max_rss = telemetry.get("max_rss_mib")
    if max_rss is not None:
        telemetry_segments.append(f"maxRSS={max_rss / 1024.0:.2f} GiB")
    if telemetry_segments:
        lines.append(f"{'Telemetry:':<10} " + " | ".join(telemetry_segments))

    lines.append("")
    return lines


def _render_partial(report: WaterfallReport) -> str:
    """REMOTE/PARTIAL waterfalls render a REAL boxed ASCII table of the
    remotely-measured stages — the same table style/geometry as the reconciled
    render, subject to partial semantics: no percentages (the '%' column is
    always '-'), no '#' bars, and no scheduling/restore-begin/local-receipt
    values (unknown remotely).  The host produces the final reconciled table;
    the conclusive footer may still read "awaiting host reconciliation" for
    values the remote has not reconciled yet."""
    width_num = 3
    width_label = 46
    width_dur = 10
    width_pct = 8
    width_bar = 40
    lines: list[str] = []
    lines.append("V2 COLD WATERFALL - REMOTE/PARTIAL (awaiting host reconciliation)")
    lines.extend(_render_compact_header(report))
    rule = (
        "+" + "-" * (width_num + 2) + "+" + "-" * (width_label + 2) + "+"
        + "-" * (width_dur + 2) + "+" + "-" * (width_dur + 2) + "+"
        + "-" * (width_pct + 2) + "+" + "-" * (width_bar + 2) + "+"
    )
    header = (
        f"| {'#':>{width_num}} | {'Stage':<{width_label}} | {'Duration':>{width_dur}} | "
        f"{'Cum.':>{width_dur}} | {'%':>{width_pct}} | {'Relative wall (non-scheduling)':<{width_bar}} |"
    )
    lines.extend([rule, header, rule])

    row = 1
    for stage in report.stages:
        if stage.accounting_role != "top_level":
            continue
        # Never render unavailable top-level rows (identical to reconciled).
        if stage.duration_ms is None or stage.status in (UNAVAILABLE, INVALID):
            continue
        label = stage.label
        if stage.concurrent:
            label = "~ " + label
        # Partial semantics: '%' always renders '-', the bar column is blank —
        # no percentage numbers and no '#' characters anywhere in stage rows.
        lines.append(
            f"| {row:>{width_num}} | {_shorten(label, width_label)} | "
            f"{_fmt_duration(stage.duration_ms):>{width_dur}} | "
            f"{_fmt_duration(stage.cumulative_ms):>{width_dur}} | "
            f"{'-':>{width_pct}} | {'':>{width_bar}} |"
        )
        for detail in report.details:
            if detail.parent_key != stage.key:
                continue
            if not _detail_is_useful(detail):
                continue
            lines.append(_detail_row(
                detail, width_label, width_dur, width_num, width_pct, width_bar,
            ))
        row += 1
    lines.append(rule)
    # Minimal footer — reconciliation/status, same full column structure as the
    # main table, closed by a final boxed border.  Reconciliation is unknown
    # remotely ('-'); status is the pending host-reconciliation marker.  The
    # scheduling window is summarized once in the conclusive lines below.
    lines.append(_footer_full_row(
        "RECONCILIATION", _fmt_duration(report.reconciliation_ms),
        width_label, width_dur, width_num, width_pct, width_bar,
    ))
    lines.append(_footer_full_row(
        "STATUS", "PENDING",
        width_label, width_dur, width_num, width_pct, width_bar,
    ))
    lines.append(rule)
    # Post-table plain lines (never part of the box): the missing-boundary
    # flags, the full pending status token, and the pre-Python pending
    # classification the host will reconcile.
    if report.partial_flags:
        lines.append("missing=" + ",".join(report.partial_flags))
    lines.append("status=PENDING_HOST_RECONCILIATION")
    if report.pre_python_interval_ms is not None:
        lines.append(_ascii_text(
            f"Pending host reconciliation: command start -> Python resume = {report.pre_python_interval_ms:.3f} ms"
            f" - classification = {report.pre_python_interval_classification or 'scheduling + pre-Python restore (unresolved platform interval)'}"
        ))
    # Conclusive footer: scheduling = enqueue + placement, non-scheduling =
    # total - scheduling_time.  Pending values render the intermediate
    # diagnostic token (the host reconciles them into real numbers).
    lines.append(
        f"{'COMMAND -> RESPONSE:':<38}"
        f"{_fmt_duration(report.total_ms) if report.total_ms is not None else 'awaiting host reconciliation'}"
    )
    lines.append(
        f"{'Command (without scheduling) -> Response:':<38}"
        f"{_fmt_duration(report.non_scheduling_ms) if report.non_scheduling_ms is not None else 'awaiting host reconciliation'}"
    )
    lines.append(
        f"{'Scheduling time:':<38}"
        f"{_fmt_duration(report.scheduling_time_ms) if report.scheduling_time_ms is not None else 'awaiting host reconciliation'}"
    )
    return "\n".join(lines)


def _detail_row(
    detail: WaterfallStage,
    width_label: int,
    width_dur: int,
    width_num: int,
    width_pct: int,
    width_bar: int,
) -> str:
    """Inline curated detail row: duration only, blank number/Cum/%/bar."""
    label = "  " + detail.label
    return (
        f"| {'':>{width_num}} | {_shorten(label, width_label)} | "
        f"{_fmt_duration(detail.duration_ms):>{width_dur}} | {'':>{width_dur}} | "
        f"{'':>{width_pct}} | {'':>{width_bar}} |"
    )


def _provider_region(report: WaterfallReport) -> str:
    """Normalized ``Provider/Region`` from the report identity (e.g. the live
    ``CLOUD_PROVIDER_GCP/us-central1`` renders as ``GCP/us-central1``)."""
    identity = report.identity
    cloud = str(identity.get("cloud") or "").strip()
    if cloud.upper().startswith("CLOUD_PROVIDER_"):
        cloud = cloud[len("CLOUD_PROVIDER_"):]
    region = str(identity.get("region") or "").strip()
    if not cloud and not region:
        return ""
    return f"{cloud or '-'}/{region or '-'}"


def _footer_full_row(
    label: str,
    value: str,
    width_label: int,
    width_dur: int,
    width_num: int,
    width_pct: int,
    width_bar: int,
) -> str:
    """Footer row spanning the SAME full column structure as the main table."""
    return (
        f"| {'':>{width_num}} | {_shorten(label, width_label)} | "
        f"{value:>{width_dur}} | {'':>{width_dur}} | {'':>{width_pct}} | {'':>{width_bar}} |"
    )


def _render_reconciled(report: WaterfallReport) -> str:
    """ONE boxed ASCII table: exclusive top-level rows + inline curated
    details, minimal footer directly below (Reconciliation / Status).
    Unavailable top-level rows are never rendered.  Percentages and bars use
    the non-scheduling wall (command->response minus scheduling time)."""
    width_num = 3
    width_label = 46
    width_dur = 10
    width_pct = 8
    width_bar = 40
    lines: list[str] = []
    lines.append(_ascii_text(f"V2 COLD WATERFALL - {report.run_label or 'run'}"))
    lines.extend(_render_compact_header(report))
    rule = (
        "+" + "-" * (width_num + 2) + "+" + "-" * (width_label + 2) + "+"
        + "-" * (width_dur + 2) + "+" + "-" * (width_dur + 2) + "+"
        + "-" * (width_pct + 2) + "+" + "-" * (width_bar + 2) + "+"
    )
    header = (
        f"| {'#':>{width_num}} | {'Stage':<{width_label}} | {'Duration':>{width_dur}} | "
        f"{'Cum.':>{width_dur}} | {'%':>{width_pct}} | {'Relative wall (non-scheduling)':<{width_bar}} |"
    )
    lines.extend([rule, header, rule])

    row = 1
    for stage in report.stages:
        if stage.accounting_role != "top_level":
            continue
        # Never render unavailable top-level rows; a required unavailable
        # boundary surfaces only as Required data / reconciliation status.
        if stage.duration_ms is None or stage.status in (UNAVAILABLE, INVALID):
            continue
        label = stage.label
        if stage.concurrent:
            label = "~ " + label
        if stage.percentage is not None:
            percentage = _fmt_num(stage.percentage, "%")
        else:
            percentage = "-"
        bar = _bar(
            stage,
            report.non_scheduling_ms if report.non_scheduling_ms is not None else report.total_wall_ms,
            width_bar,
        )
        lines.append(
            f"| {row:>{width_num}} | {_shorten(label, width_label)} | "
            f"{_fmt_duration(stage.duration_ms):>{width_dur}} | "
            f"{_fmt_duration(stage.cumulative_ms):>{width_dur}} | "
            f"{percentage:>{width_pct}} | {bar} |"
        )
        for detail in report.details:
            if detail.parent_key != stage.key:
                continue
            if not _detail_is_useful(detail):
                continue
            lines.append(_detail_row(
                detail, width_label, width_dur, width_num, width_pct, width_bar,
            ))
        row += 1
    lines.append(rule)
    # Minimal footer — reconciliation/status, using the SAME full column
    # structure as the main table, closed by a final boxed border.  The 10 ms
    # target is surfaced only when missed (10 < |recon| <= 50 ms) while status
    # stays OK under the hard ceiling.  The scheduling window (enqueue +
    # placement) is summarized once in the conclusive lines below.
    lines.append(_footer_full_row(
        "RECONCILIATION", _fmt_duration(report.reconciliation_ms),
        width_label, width_dur, width_num, width_pct, width_bar,
    ))
    lines.append(_footer_full_row(
        "STATUS", _ascii_text(report.reconciliation_status or "-"),
        width_label, width_dur, width_num, width_pct, width_bar,
    ))
    if (
        report.reconciliation_ms is not None
        and abs(report.reconciliation_ms) > report.reconciliation_target_ms
        and abs(report.reconciliation_ms) <= report.reconciliation_hard_ms
    ):
        lines.append(_footer_full_row(
            "TARGET 10MS", "MISSED",
            width_label, width_dur, width_num, width_pct, width_bar,
        ))
    lines.append(rule)
    if report.data_flags:
        lines.append(f"Required data: {','.join(report.data_flags)}")
        lines.append(f"VALIDATION: {_ascii_text(report.diagnostic_status or 'INCOMPLETE')}")
    # Conclusive footer — the new timing contract.  Scheduling time = enqueue +
    # placement; non-scheduling = total - scheduling_time.  These are the
    # final reconciled values and are NEVER the intermediate pending token.
    lines.append(f"{'COMMAND -> RESPONSE:':<38}{_fmt_duration(report.total_ms)}")
    lines.append(
        f"{'Command (without scheduling) -> Response:':<38}"
        f"{_fmt_duration(report.non_scheduling_ms)}"
    )
    lines.append(f"{'Scheduling time:':<38}{_fmt_duration(report.scheduling_time_ms)}")
    return "\n".join(lines)


def render_waterfall(report: WaterfallReport | Mapping[str, Any], *, terminal_columns: int | None = None) -> str:
    """Render a plain-ASCII waterfall.

    REMOTE/PARTIAL waterfalls render as a REAL boxed ASCII table of the
    remotely-measured stages (no percentages, no bars — scheduling/
    restore-begin/local-receipt are unknown remotely and the host produces
    the final reconciled table); final host-reconciled waterfalls
    render as ONE ASCII table with a minimal footer.
    ``terminal_columns`` is accepted for call compatibility; the layout is a
    fixed deterministic width so console output is byte-stable.
    """
    del terminal_columns
    if not isinstance(report, WaterfallReport):
        report = _report_from_value(report)
    if report.partial_waterfall:
        return _render_partial(report)
    return _render_reconciled(report)


def _report_from_value(value: WaterfallReport | Mapping[str, Any]) -> WaterfallReport:
    if isinstance(value, WaterfallReport):
        return value
    def stage_from_dict(stage: Mapping[str, Any]) -> WaterfallStage:
        data = dict(stage)
        data["source_fields"] = tuple(data.get("source_fields", ()))
        data.setdefault("concurrent", False)
        data.setdefault("provenance", "")
        data.setdefault("accounting_role", "top_level")
        return WaterfallStage(**data)

    stages = tuple(stage_from_dict(stage) for stage in value.get("stages", ()) if isinstance(stage, Mapping))
    details = tuple(stage_from_dict(detail) for detail in value.get("details", ()) if isinstance(detail, Mapping))
    return WaterfallReport(
        run_label=str(value.get("run_label", "")),
        request_id=str(value.get("request_id", "")),
        identity=_as_mapping(value.get("identity")),
        total_ms=value.get("total_ms"),
        stages=stages,
        reconciliation_ms=value.get("reconciliation_ms"),
        warnings=tuple(value.get("warnings", ())),
        accounted_ms=value.get("accounted_ms"),
        tolerance_ms=value.get("tolerance_ms"),
        details=details,
        residual_ms=value.get("residual_ms"),
        residual_pct=value.get("residual_pct"),
        reconciliation_status=str(value.get("reconciliation_status", "")),
        controllable_wall_ms=value.get("controllable_wall_ms"),
        platform_wall_ms=value.get("platform_wall_ms"),
        boundary_flags=tuple(value.get("boundary_flags", ())),
        scheduling_ms=value.get("scheduling_ms"),
        total_wall_ms=value.get("total_wall_ms"),
        command_response_ms=value.get("command_response_ms"),
        command_to_enqueue_ms=value.get("command_to_enqueue_ms"),
        scheduling_time_ms=value.get("scheduling_time_ms"),
        non_scheduling_ms=value.get("non_scheduling_ms"),
        host_telemetry=dict(_as_mapping(value.get("host_telemetry"))),
        partial_waterfall=bool(value.get("partial_waterfall", False)),
        partial_flags=tuple(value.get("partial_flags", ())),
        pre_python_interval_ms=value.get("pre_python_interval_ms"),
        pre_python_interval_classification=str(value.get("pre_python_interval_classification", "")),
        data_flags=tuple(value.get("data_flags", ())),
        reconciliation_target_ms=float(value.get("reconciliation_target_ms", RECONCILIATION_TARGET_MS)),
        reconciliation_hard_ms=float(value.get("reconciliation_hard_ms", RECONCILIATION_HARD_MS)),
        diagnostic_status=str(value.get("diagnostic_status", value.get("validation_status", ""))),
    )


def render_comparison(reports: Sequence[WaterfallReport | Mapping[str, Any]]) -> str:
    """Render a compact multi-run comparison without requiring color."""
    parsed = [_report_from_value(report) for report in reports]
    if not parsed:
        return "THREE-RUN COLD COMPARISON\n(no completed runs)"
    lines = [
        "THREE-RUN COLD COMPARISON",
        "+-----+----------+----------+----------+----------+----------+----------+",
        "| Run | Total    | Platform | Restore  | PreSampler | Sampler | Output   |",
        "+-----+----------+----------+----------+----------+----------+----------+",
    ]
    totals: list[float] = []
    for index, report in enumerate(parsed, 1):
        stage_map = {stage.key: stage for stage in report.stages}
        total = report.total_ms
        if total is not None:
            totals.append(total)
        platform = stage_map.get("modal_scheduling")
        restore = stage_map.get("application_restore")
        pre_keys = ("remote_method_setup", "prompt_executor_cache_setup", "pre_sampler_execution", "sampler_node_to_sampling")
        pre = sum(stage_map[key].duration_ms or 0 for key in pre_keys if key in stage_map)
        sampler = stage_map.get("sampling")
        output = 0.0
        for output_key in ("vae", "output_persistence"):
            output_stage = stage_map.get(output_key)
            if output_stage is not None and output_stage.duration_ms is not None:
                output += output_stage.duration_ms
        instance = str(report.identity.get("restored_instance_id") or "-")[:8]
        platform_ms = platform.duration_ms if platform and platform.duration_ms is not None else None
        restore_ms = restore.duration_ms if restore and restore.duration_ms is not None else None
        sampler_ms = sampler.duration_ms if sampler and sampler.duration_ms is not None else None
        lines.append(
            f"| {index:3d} | {total / 1000.0:7.3f}s | {platform_ms / 1000.0:7.3f}s | {restore_ms / 1000.0:7.3f}s | {pre / 1000.0:7.3f}s | {sampler_ms / 1000.0:7.3f}s | {output / 1000.0:7.3f}s |"
            if total is not None and platform_ms is not None and restore_ms is not None and sampler_ms is not None
            else f"| {index:3d} |        - |        - |        - |        - |        - |        - |"
        )
    lines.append("+-----+----------+----------+----------+----------+----------+----------+")
    if totals:
        ordered = sorted(totals)
        median = ordered[len(ordered) // 2]
        lines.append(f"Median: {median / 1000.0:.3f}s  Worst: {max(totals) / 1000.0:.3f}s  {sum(total < 15000 for total in totals)}/{len(totals)} below 15s")
    return "\n".join(lines)


def waterfall_to_dict(report: WaterfallReport) -> dict[str, Any]:
    def stage_dict(stage: WaterfallStage) -> dict[str, Any]:
        return {
            "key": stage.key,
            "label": stage.label,
            "group": stage.group,
            "start_ns": stage.start_ns,
            "end_ns": stage.end_ns,
            "duration_ms": stage.duration_ms,
            "cumulative_ms": stage.cumulative_ms,
            "percentage": stage.percentage,
            "source": stage.source,
            "status": stage.status,
            "overlaps": list(stage.overlaps),
            "is_detail": stage.is_detail,
            "parent_key": stage.parent_key,
            "included_in_total": stage.included_in_total,
            "clock_scope": stage.clock_scope,
            "source_fields": list(stage.source_fields),
            "concurrent": stage.concurrent,
            "provenance": stage.provenance,
            "accounting_role": stage.accounting_role,
        }
    return {
        "run_label": report.run_label,
        "request_id": report.request_id,
        "identity": dict(report.identity),
        "total_ms": report.total_ms,
        "accounted_ms": report.accounted_ms,
        "reconciliation_ms": report.reconciliation_ms,
        "tolerance_ms": report.tolerance_ms,
        "warnings": list(report.warnings),
        "stages": [stage_dict(stage) for stage in report.stages],
        "details": [stage_dict(stage) for stage in report.details],
        "residual_ms": report.residual_ms,
        "residual_pct": report.residual_pct,
        "reconciliation_status": report.reconciliation_status,
        "controllable_wall_ms": report.controllable_wall_ms,
        "platform_wall_ms": report.platform_wall_ms,
        "boundary_flags": list(report.boundary_flags),
        "scheduling_ms": report.scheduling_ms,
        "total_wall_ms": report.total_wall_ms,
        "command_response_ms": report.command_response_ms,
        "command_to_enqueue_ms": report.command_to_enqueue_ms,
        "scheduling_time_ms": report.scheduling_time_ms,
        "non_scheduling_ms": report.non_scheduling_ms,
        "host_telemetry": dict(report.host_telemetry),
        "partial_waterfall": report.partial_waterfall,
        "partial_flags": list(report.partial_flags),
        "pre_python_interval_ms": report.pre_python_interval_ms,
        "pre_python_interval_classification": report.pre_python_interval_classification,
        "data_flags": list(report.data_flags),
        "reconciliation_target_ms": report.reconciliation_target_ms,
        "reconciliation_hard_ms": report.reconciliation_hard_ms,
        "diagnostic_status": report.diagnostic_status,
    }


def _is_valid_waterfall(value: Any) -> bool:
    """True for a real report dict (as produced by ``waterfall_to_dict``).

    Error / absent / non-applicable markers are NOT valid, so an idempotent
    finalizer never mistakes them for a completed report.
    """
    if not isinstance(value, Mapping):
        return False
    if value.get("status") in ("error", "absent", NON_APPLICABLE):
        return False
    return "stages" in value


def is_graph_result(value: Any) -> bool:
    """True when *value* carries a graph workflow result / timing payload.

    Non-graph payloads (checkpoint summaries, asset reads, health, canary,
    restore-only, NUMA, rehoming probes) return ``False`` so callers never
    fabricate graph waterfall stages for them.
    """
    if not isinstance(value, Mapping):
        return False
    for _key in ("trace", "timing", "images", "outputs", "generation_wall_ms"):
        if _key in value:
            return True
    return False


def graph_result_from_event(event: Any) -> dict[str, Any] | None:
    """Extract the graph workflow result dict from a stream event, or ``None``.

    Handles terminal ``{"type": "result", "data": {...}}`` events and nested
    checkpoint ``cell.completed`` / ``cell.failed`` events whose ``data`` or
    ``payload`` carries a ``result`` dict.  Returns the result dict only when
    one is present; never for summaries, cell metadata, probes, or absent
    results.  Callers still apply ``is_graph_result`` before attaching.
    """
    if not isinstance(event, Mapping):
        return None
    etype = event.get("type")
    if etype == "result":
        data = event.get("data")
        return data if isinstance(data, dict) else None
    if etype in ("cell.completed", "cell.failed"):
        for _container in (event.get("data"), event.get("payload")):
            if isinstance(_container, Mapping):
                _nested = _container.get("result")
                if isinstance(_nested, dict):
                    return _nested
    return None


def attach_waterfall(
    result: dict[str, Any],
    *,
    report: WaterfallReport | None = None,
    result_view: Mapping[str, Any] | None = None,
    timing: Mapping[str, Any] | None = None,
    wall_ms: float | None = None,
    command_start_unix_ms: int | None = None,
    response_received_unix_ns: int | None = None,
    run_label: str = "",
    modal_restore_begin_wall_unix_ns: int | None = None,
    print_render: bool = True,
    replace_partial: bool = False,
) -> dict[str, Any] | None:
    """Idempotent, non-raising waterfall finalizer (mutates *result* in place).

    Preserves an existing valid waterfall; otherwise builds a report from
    *result_view* (or *result* itself) via ``build_waterfall`` — or serializes
    a prebuilt *report* — and attaches it as ``result["waterfall"]``.

    ``replace_partial=True`` (host-reconciled callers) rebuilds even when an
    existing valid report is marked ``partial_waterfall=True``: a REMOTE raw
    artifact must never block the host from replacing it with the final
    reconciled report.  A non-partial existing report is always preserved.

    A failure never raises into the workflow: an error marker is attached and
    a concise line is printed.  Returns the attached/preserved waterfall dict,
    or ``None`` when *result* is not a dict.  ``print_render=False`` skips the
    full waterfall render (host-side callers) while still attaching it.
    """
    if not isinstance(result, dict):
        return None
    existing = result.get("waterfall")
    if _is_valid_waterfall(existing):
        if replace_partial and existing.get("partial_waterfall") is True:
            existing = None  # remote raw artifact must not block the host rebuild
        else:
            return existing
    try:
        if report is None:
            view = result_view if result_view is not None else dict(result)
            report = build_waterfall(
                result=view,
                timing=dict(timing) if timing else {},
                wall_ms=wall_ms,
                command_start_unix_ms=command_start_unix_ms,
                response_received_unix_ns=response_received_unix_ns,
                run_label=run_label,
                modal_restore_begin_wall_unix_ns=modal_restore_begin_wall_unix_ns,
            )
        result["waterfall"] = waterfall_to_dict(report)
        if print_render:
            print(render_waterfall(report), flush=True)
        return result["waterfall"]
    except Exception as exc:  # noqa: BLE001
        result["waterfall"] = {
            "status": "error",
            "error_type": type(exc).__name__,
        }
        print(
            f"[v2.waterfall] status=error error_type={type(exc).__name__}",
            flush=True,
        )
        return result["waterfall"]


def mark_waterfall_non_applicable(
    result: dict[str, Any],
    *,
    method: str = "",
) -> dict[str, Any] | None:
    """Attach an explicit non-applicable terminal classification.

    Used for lifecycle / infrastructure / probe / no-graph results so every
    result-returning path has an explicit terminal marker WITHOUT fabricated
    graph stages.  Idempotent: preserves an existing valid waterfall; otherwise
    sets ``result["waterfall"] = {"status": NON_APPLICABLE, ...}``.  Returns the
    attached marker dict, or ``None`` when *result* is not a dict.
    """
    if not isinstance(result, dict):
        return None
    existing = result.get("waterfall")
    if _is_valid_waterfall(existing):
        return existing
    marker: dict[str, Any] = {"status": NON_APPLICABLE}
    if method:
        marker["method"] = method
    result["waterfall"] = marker
    return marker


__all__ = [
    "Boundary", "WaterfallStage", "WaterfallReport", "build_waterfall",
    "render_waterfall", "render_comparison", "waterfall_to_dict",
    "attach_waterfall", "mark_waterfall_non_applicable", "is_graph_result",
    "graph_result_from_event", "NON_APPLICABLE",
]
