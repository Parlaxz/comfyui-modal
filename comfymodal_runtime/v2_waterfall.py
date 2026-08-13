"""V2 benchmark waterfall extraction and rendering.

This module deliberately knows nothing about ComfyUI. It consumes a completed
result and its already-captured timing data, so formatting cannot be part of
the measured request path.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


UNAVAILABLE = "unavailable"
MEASURED = "measured"
DERIVED = "derived"
INVALID = "invalid"
NON_APPLICABLE = "non_applicable"

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
    # Accounting role: "top_level" (exclusive wall, included_in_total=True),
    # "child" (detail, included_in_total=False), "overlap_diagnostic"
    # (overlapping/diagnostic span, excluded from accounted sums), or
    # "reconciliation" (footer metadata, never a numbered stage).
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
    partial_waterfall: bool = False
    partial_flags: tuple[str, ...] = ()
    pre_python_interval_ms: float | None = None
    pre_python_interval_classification: str = ""


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

    Priority: ``_restore_timing.remote_python_resume`` timing boundary →
    ``v2_startup_post_snapshot_restore_start`` event → ``snapshot_restore_start``
    event (both remote) → ``restore_method_start`` timing boundary.
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
        # still identifies a host-side trace (e.g. command → local receive).
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


def _stage_candidate(
    result: Mapping[str, Any],
    key: str,
    *,
    restore_begin: Boundary | None = None,
    python_resume: Boundary | None = None,
    python_restore_end: Boundary | None = None,
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
        #   1. measured submission → restore_begin (authoritative platform
        #      boundary from the Modal app log)
        #   2. measured submission → python_resume (combined interval; the
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
        # boundary) → first restored Python line.  When the platform boundary
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
    if key == "method_entry_to_unet_claim":
        # Method entry → the request-scoped UNET ownership claim (worker
        # publishes before touching storage/CUDA).  Both boundaries are remote
        # so the interval is same-process monotonic.  The claim event is only
        # emitted under the exclusive-owner gate; without it the stage is
        # unavailable (never a phantom zero).
        claim_event = _event_boundary(result, "unet_ownership_claim", process="remote")
        return _candidate(result, remote_entry, claim_event, duration_keys=("method_entry_to_unet_claim_ms",))
    if key == "unet_claim_to_ready":
        # Worker claim → terminal ready (the load itself).  Concurrent with
        # graph-side stages by design; reported explicitly, excluded from the
        # accounted total (see build_waterfall concurrency handling).
        claim_event = _event_boundary(result, "unet_ownership_claim", process="remote")
        terminal = (
            _event_boundary(result, "unet_early_activation_terminal", process="remote")
            or _event_boundary(result, "unet_early_activation_terminal")
        )
        candidate = _candidate(
            result, claim_event, terminal,
            duration_keys=("unet_claim_to_ready_ms", "early_activation_total_ms", "synchronized_transfer_ms"),
        )
        return candidate
    if key == "sampler_graph_join_wait":
        # The sampler-boundary graph join: first sampler node → join
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
    if key == "first_node_to_clip":
        value = _first_value(result, ("first_node_to_clip_ms",))
        return _candidate_from_duration(value)
    if key == "clip_to_sampler_node":
        value = _first_value(result, ("clip_to_sampler_node_ms",))
        return _candidate_from_duration(value)
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
        start = event("output_encode_start", process="remote") or event("output_persist_start", process="remote")
        end = event("output_persist_end", process="remote") or event("output_encode_end", process="remote")
        return _candidate(result, start, end, duration_keys=("output_collection_ms", "output_persist_ms", "output_commit_ms"))
    if key == "remote_local_return":
        # The local hop: remote_return_start (emitted by execute_plan once the
        # result leaves the transport) → final local receive.  Both boundaries
        # are local so the interval is same-clock and never overlaps the
        # cross-process handoff row.  Traces without a local return marker
        # fall back to the remote output persist/collect boundary.
        start = (
            event("remote_return_start", process="local", last=True)
            or event(("output_persist_end", "output_collect_end"), process="remote", last=True)
            or event(("output_persist_end", "output_collect_end", "remote_return_start"), last=True)
        )
        end = event(("response_received", "final_result_received", "local_result_received"), process="local", last=True)
        return _candidate(result, start, end, duration_keys=("remote_return_ms", "trigger_to_result_ms"))
    if key == "remote_return_handoff":
        return _candidate(
            result,
            event("output_collect_end", process="remote", last=True)
            or event("output_collect_end", last=True),
            event("remote_return_start", process="local", last=True)
            or event(("final_result_received", "response_received"), process="local", last=True),
        )
    return _Candidate()


_STAGE_SPECS: tuple[tuple[str, str, str, bool], ...] = (
    ("local_preparation", "Local preparation", "local", False),
    ("modal_handle_submission", "Modal handle and submission", "local", False),
    ("modal_scheduling", "Modal scheduling before snapshot restore begins", "platform", False),
    ("pre_python_snapshot_restore", "Modal pre-Python snapshot restoration", "platform", False),
    ("application_restore", "Python/application restore", "application", False),
    ("restore_to_method_entry", "Restore-to-method entry", "application", False),
    ("method_entry_to_unet_claim", "Method entry to UNET ownership claim", "application", True),
    ("unet_claim_to_ready", "UNET claim to ready (worker load)", "application", True),
    ("remote_method_setup", "Remote method setup", "application", False),
    ("prompt_executor_cache_setup", "PromptExecutor/cache setup", "application", False),
    ("first_node_to_clip", "First node to CLIP", "application", False),
    ("clip_to_sampler_node", "CLIP to sampler node", "application", False),
    ("sampler_graph_join_wait", "Sampler graph-join wait", "application", False),
    ("sampler_node_to_sampling", "Sampler node to sampling", "application", False),
    ("sampling", "Sampling", "application", False),
    ("post_sampling_transition", "Post-sampling transition", "application", False),
    ("vae", "VAE", "application", False),
    ("output_persistence", "Output encode / descriptor", "application", False),
    ("remote_return_handoff", "Remote result handoff", "local", False),
    ("remote_local_return", "Remote/local return", "local", False),
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
         start/end trace events (``snapshot_graph_seed_validate_start`` →
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
        ("output_encode", "output encode", "output_persistence", "output_encode_ms"),
        ("output_commit", "output commit", "output_persistence", "output_commit_ms"),
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
            parent_key="prompt_executor_cache_setup",
            included_in_total=False,
            clock_scope="metadata",
            provenance="remote_trace",
            accounting_role="child",
        ))
    for index, record in enumerate(_as_mapping(structured).get("per_node_timings", ())):
        if not isinstance(record, Mapping):
            continue
        duration = record.get("duration_ms")
        duration_ms = float(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None
        node_label = str(record.get("class_type") or record.get("node_id") or "node")
        # Node rows are filtered to keep the diagnostics tight: show a node
        # only when it took meaningful time (>= 25 ms) or it is strategic.
        if not (
            (duration_ms is not None and duration_ms >= 25.0)
            or node_label in STRATEGIC_NODE_CLASS_TYPES
        ):
            continue
        details.append(WaterfallStage(
            key=f"node_timing_{index}",
            label=f"Node: {node_label}",
            group="detail",
            start_ns=None,
            end_ns=None,
            duration_ms=duration_ms,
            cumulative_ms=None,
            percentage=_percentage(duration_ms, total_ms, total_wall_ms),
            source="node_timing",
            status=DERIVED if isinstance(duration, (int, float)) and not isinstance(duration, bool) else UNAVAILABLE,
            is_detail=True,
            parent_key="prompt_executor_cache_setup",
            included_in_total=False,
            clock_scope="metadata",
            provenance="remote_trace",
            accounting_role="child",
        ))
    for index, record in enumerate(_as_mapping(structured).get("active_read_records", ())):
        if not isinstance(record, Mapping):
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
            parent_key="remote_method_setup",
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
        *, overlaps: tuple[str, ...] = (), accounting_role: str = "child",
    ) -> None:
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
    # Pre-claim gaps hang off ``remote_method_setup``; the load chain hangs off
    # ``unet_claim_to_ready``.  Both top-level parents are concurrent /
    # excluded from the accounted total, so these children never affect it.
    fast_to_start = event("unet_fast_disk_to_start", process="remote") or event("unet_fast_disk_to_start")
    fast_to_end = event("unet_fast_disk_to_end", process="remote") or event("unet_fast_disk_to_end")
    fast_bind_start = event("unet_fast_disk_bind_start", process="remote") or event("unet_fast_disk_bind_start")
    fast_bind_end = event("unet_fast_disk_bind_end", process="remote") or event("unet_fast_disk_bind_end")
    ea_scheduled = event("unet_early_activation_scheduled", process="remote") or event("unet_early_activation_scheduled")
    ea_terminal = event("unet_early_activation_terminal", process="remote") or event("unet_early_activation_terminal")
    ea_load_start = event("unet_activation_load_start", process="remote") or event("unet_activation_load_start")
    complete_event = event("unet_fast_disk_complete", process="remote") or event("unet_fast_disk_complete")

    # 1. "UNET scheduled → worker start"
    add("unet_scheduled_to_worker_start", "UNET scheduled → worker start", "remote_method_setup",
        _candidate(result, ea_scheduled, fast_to_start or ea_load_start))

    # 2. "Worker start → checkpoint read start": active_read records carry
    #    only wall_ms in practice (no start/end ns), so this is usually
    #    unavailable and the read row below covers the span.
    read_start_ns = None
    read_end_ns = None
    structured = _as_mapping(result).get("pre_sampler_structured_report")
    for record in _as_mapping(structured).get("active_read_records", ()):
        if not isinstance(record, Mapping):
            continue
        for key in ("start_ns", "start_wall_unix_ns", "start_monotonic_ns"):
            value = _number(record.get(key))
            if value:
                read_start_ns = value
                break
        for key in ("end_ns", "end_wall_unix_ns", "end_monotonic_ns"):
            value = _number(record.get(key))
            if value:
                read_end_ns = value
                break
        if read_start_ns is not None and read_end_ns is not None:
            break
    if read_start_ns is not None:
        add("unet_worker_to_read_start", "Worker start → checkpoint read start", "remote_method_setup",
            _candidate(result, fast_to_start, Boundary("active_read_start", None, read_start_ns, "remote", "event")))
    else:
        add("unet_worker_to_read_start", "Worker start → checkpoint read start", "remote_method_setup", _Candidate())

    # 3. "Checkpoint read": active_read start→end when carried, else the
    #    fast-disk to_start→to_end pair.  When the H2D-pair fallback is used
    #    the row is a diagnostic overlap of the Synchronized H2D span (which
    #    the same pair would otherwise feed), so it is flagged overlap_diagnostic
    #    and excluded from accounted sums; the H2D row is never touched.
    if read_start_ns is not None and read_end_ns is not None:
        read_candidate = _candidate(
            result,
            Boundary("active_read_start", None, read_start_ns, "remote", "event"),
            Boundary("active_read_end", None, read_end_ns, "remote", "event"),
        )
        read_used_pair = False
    else:
        read_candidate = _candidate(result, fast_to_start, fast_to_end)
        read_used_pair = read_candidate.duration_ms is not None
    if read_used_pair:
        read_label = "Checkpoint read (overlap: H2D span fallback)"
        read_role = "overlap_diagnostic"
        read_overlaps = ("unet_synchronized_h2d",)
    else:
        read_label = "Checkpoint read"
        read_role = "child"
        read_overlaps = ()
    add("unet_checkpoint_read", read_label, "unet_claim_to_ready", read_candidate,
        accounting_role=read_role, overlaps=read_overlaps)

    # 4. "Read end → construction done": construction metadata (ctor/get_model)
    #    on the complete event, else the to_end → bind_start measured span.
    ctor_ms = _event_metadata_value(result, "unet_fast_disk_complete", "ctor_ms")
    get_model_ms = _event_metadata_value(result, "unet_fast_disk_complete", "get_model_ms")
    construction_candidate = _Candidate()
    ctor_ok = isinstance(ctor_ms, (int, float)) and not isinstance(ctor_ms, bool)
    model_ok = isinstance(get_model_ms, (int, float)) and not isinstance(get_model_ms, bool)
    if ctor_ok and model_ok:
        construction_candidate = _candidate_from_duration(
            float(ctor_ms) + float(get_model_ms), source="metadata",
            source_fields=("unet_fast_disk_complete.ctor_ms", "unet_fast_disk_complete.get_model_ms"),
        )
    elif ctor_ok:
        construction_candidate = _candidate_from_duration(float(ctor_ms), source="metadata", source_fields=("unet_fast_disk_complete.ctor_ms",))
    elif model_ok:
        construction_candidate = _candidate_from_duration(float(get_model_ms), source="metadata", source_fields=("unet_fast_disk_complete.get_model_ms",))
    if construction_candidate.duration_ms is None and fast_bind_start is not None:
        construction_candidate = _candidate(result, fast_to_end, fast_bind_start)
    add("unet_read_to_construction", "Read end → construction done", "unet_claim_to_ready", construction_candidate)

    # 5. "Bind": bind_start → bind_end, else bind_ms metadata on complete.
    bind_ms = _event_metadata_value(result, "unet_fast_disk_complete", "bind_ms")
    bind_candidate = _candidate(result, fast_bind_start, fast_bind_end)
    if bind_candidate.duration_ms is None and isinstance(bind_ms, (int, float)) and not isinstance(bind_ms, bool):
        bind_candidate = _candidate_from_duration(float(bind_ms), source="metadata", source_fields=("unet_fast_disk_complete.bind_ms",))
    add("unet_bind", "Bind", "unet_claim_to_ready", bind_candidate)

    # 6. "Synchronized H2D": to_device_ms/to_wall_ms metadata, else the
    #    to_start→to_end pair — only when the pair was NOT already used for
    #    the checkpoint-read row (never double-counted).
    h2d_candidate = _Candidate()
    for h2d_key in ("to_device_ms", "to_wall_ms"):
        h2d_value = _event_metadata_value(result, "unet_fast_disk_complete", h2d_key)
        if isinstance(h2d_value, (int, float)) and not isinstance(h2d_value, bool):
            h2d_candidate = _candidate_from_duration(float(h2d_value), source="metadata", source_fields=(f"unet_fast_disk_complete.{h2d_key}",))
            break
    if h2d_candidate.duration_ms is None and not read_used_pair:
        h2d_candidate = _candidate(result, fast_to_start, fast_to_end)
    add("unet_synchronized_h2d", "Synchronized H2D", "unet_claim_to_ready", h2d_candidate)

    # 7. "H2D end → UNET ready": to_end → early-activation terminal (or the
    #    fast-disk complete event).
    add("unet_h2d_to_ready", "H2D end → UNET ready", "unet_claim_to_ready",
        _candidate(result, fast_to_end, ea_terminal or complete_event))

    # 8. "UNET ready → sampler demand": terminal → graph-join demand
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
    add("unet_ready_to_demand", "UNET ready → sampler demand", "unet_claim_to_ready", demand_candidate)

    # 9. "Sampler demand → join complete": join_start → join_completed
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
    add("unet_demand_to_join", "Sampler demand → join complete", "unet_claim_to_ready", join_candidate)

    # 10. "Join complete → sampling": join_completed → sampling_start event.
    sampling_start = event("sampling_start", process="remote") or event("sampling_start")
    join_to_sampling = _Candidate()
    if (
        isinstance(join_end_meta, (int, float))
        and int(join_end_meta) > 0
        and sampling_start is not None
        and sampling_start.monotonic_ns is not None
    ):
        join_to_sampling = _candidate(result, Boundary("unet_graph_join", None, int(join_end_meta), "remote", "metadata"), sampling_start)
    add("unet_join_to_sampling", "Join complete → sampling", "unet_claim_to_ready", join_to_sampling)

    # ── B. VAE lane ───────────────────────────────────────────────────────
    sampling_end = event("sampling_end", process="remote") or event("sampling_end")
    vae_scheduled = event("vae_early_activation_scheduled", process="remote") or event("vae_early_activation_scheduled")
    vae_load_start = event("vae_early_activation_load_start", process="remote") or event("vae_early_activation_load_start")
    vae_terminal = event("vae_early_activation_terminal", process="remote") or event("vae_early_activation_terminal")
    vae_consumed = event("vae_early_activation_consumed", process="remote") or event("vae_early_activation_consumed")
    vae_decode_start = event("vae_decode_start", process="remote") or event("vae_decode_start")

    # 1. "Sampling end → VAE scheduled"
    add("vae_sampling_end_to_scheduled", "Sampling end → VAE scheduled", "post_sampling_transition",
        _candidate(result, sampling_end, vae_scheduled))
    # 2. "VAE scheduled → worker/load start"
    add("vae_scheduled_to_load", "VAE scheduled → worker/load start", "post_sampling_transition",
        _candidate(result, vae_scheduled, vae_load_start))
    # 3. "VAE load/H2D": load_start → terminal, else reconciliation load_wall_ms.
    vae_load_ms = _event_metadata_value(result, "vae_early_activation_reconciliation", "load_wall_ms")
    vae_load_candidate = _candidate(result, vae_load_start, vae_terminal)
    if vae_load_candidate.duration_ms is None and isinstance(vae_load_ms, (int, float)) and not isinstance(vae_load_ms, bool):
        vae_load_candidate = _candidate_from_duration(float(vae_load_ms), source="metadata", source_fields=("vae_early_activation_reconciliation.load_wall_ms",))
    add("vae_load", "VAE load/H2D", "vae", vae_load_candidate)
    # 4. "VAE ready → consumed": terminal → consumed, else reconciliation join_wait_ms.
    vae_join_ms = _event_metadata_value(result, "vae_early_activation_reconciliation", "join_wait_ms")
    vae_join_candidate = _candidate(result, vae_terminal, vae_consumed)
    if vae_join_candidate.duration_ms is None and isinstance(vae_join_ms, (int, float)) and not isinstance(vae_join_ms, bool):
        vae_join_candidate = _candidate_from_duration(float(vae_join_ms), source="metadata", source_fields=("vae_early_activation_reconciliation.join_wait_ms",))
    add("vae_ready_to_consumed", "VAE ready → consumed", "vae", vae_join_candidate)
    # 5. "Consumed → decode start" (the decode itself is the top-level vae stage).
    add("vae_consumed_to_decode", "Consumed → decode start", "vae",
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

    # 1. "VAE end → output encode start"
    vae_decode_end = event("vae_decode_end", process="remote") or event("vae_decode_end")
    add("output_vae_end_to_encode", "VAE end → output encode start", "output_persistence",
        _candidate(result, vae_decode_end, output_encode_start))
    # 2. "PNG encode": encode_start → encode_end, else output_encode_ms.
    encode_ms = _first_value(result, ("output_encode_ms",))
    encode_candidate = _candidate(result, output_encode_start, output_encode_end)
    if encode_candidate.duration_ms is None and isinstance(encode_ms, (int, float)) and not isinstance(encode_ms, bool):
        encode_candidate = _candidate_from_duration(float(encode_ms), source="metadata", source_fields=("output_encode_ms",))
    add("output_png_encode", "PNG encode", "output_persistence", encode_candidate)
    # 3. "Descriptor/materialization": encode_end → persist_end, else output_commit_ms.
    commit_ms = _first_value(result, ("output_commit_ms",))
    descriptor_candidate = _candidate(result, output_encode_end, output_persist_end)
    if descriptor_candidate.duration_ms is None and isinstance(commit_ms, (int, float)) and not isinstance(commit_ms, bool):
        descriptor_candidate = _candidate_from_duration(float(commit_ms), source="metadata", source_fields=("output_commit_ms",))
    add("output_descriptor", "Descriptor/materialization", "output_persistence", descriptor_candidate)

    # 4. "Remote result emitted": the last remote emission boundary (persist
    #    end / collect end) that the handoff stage already consumes — rendered
    #    as a marker child with the same boundary info (no fabricated span).
    emitted_source = output_collect_end or output_persist_end
    if emitted_source is not None:
        emitted_candidate = _Candidate(
            start=None, end=emitted_source,
            duration_ms=None, source="derived", status=DERIVED,
            clock_scope="wall", source_fields=(emitted_source.name,),
        )
    else:
        emitted_candidate = _Candidate()
    add("output_remote_emitted", "Remote result emitted", "remote_return_handoff", emitted_candidate)

    # 5. "Deferred persistence after yield": deferred_commit_start → end
    #    (emitted on the teardown trace; when absent → localized unavailable).
    add("output_deferred_commit", "Deferred persistence after yield", "remote_return_handoff",
        _candidate(result, event("deferred_commit_start"), event("deferred_commit_end", last=True)))

    # 6. "Local receipt → caller return": final_result_received /
    #    local_result_received (local) → response boundary.  When the response
    #    boundary is absent the row is a localized unavailable.
    local_receipt = event(("final_result_received", "local_result_received"), process="local", last=True)
    if local_receipt is not None and response is not None:
        add("local_receipt_to_return", "Local receipt → caller return", "remote_local_return",
            _candidate(result, local_receipt, response))
    else:
        add("local_receipt_to_return", "Local receipt → caller return", "remote_local_return", _Candidate())

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
    the combined submission → python_resume interval instead.
    """
    result_view: Mapping[str, Any] = dict(result)
    if timing:
        result_view = {**result_view, "timing": dict(timing)}
    warnings: list[str] = []
    command_start = _command_boundary(command_start_unix_ms)
    response = _response_boundary(response_received_unix_ns)
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
        elif key == "remote_local_return" and response is not None:
            start = _event_boundary(
                result_view, "remote_return_start", process="local", last=True,
            ) or _event_boundary(
                result_view, ("output_persist_end", "output_collect_end"),
                process="remote", last=True,
            ) or _event_boundary(
                result_view, ("output_persist_end", "output_collect_end", "remote_return_start"),
                last=True,
            )
            candidate = _candidate(result_view, start, response, duration_keys=("remote_return_ms", "trigger_to_result_ms"))
        else:
            candidate = _stage_candidate(
                result_view, key,
                restore_begin=restore_begin,
                python_resume=python_resume,
                python_restore_end=python_restore_end,
            )
        start_ns, end_ns = _stage_interval(candidate)
        status = candidate.status
        duration = candidate.duration_ms
        if duration is not None and duration < 0:
            status = INVALID
            warnings.append(f"{label}: negative duration")
            duration = None
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
        ))

    total: float | None
    if command_start is not None and response is not None:
        total = _duration_between(command_start, response)
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
    partial_flags: list[str] = []
    if submission is None:
        partial_flags.append("missing_submission")
    if restore_begin is None:
        partial_flags.append("missing_modal_restore_begin")
    if _event_boundary(
        result_view,
        ("final_result_received", "local_result_received"),
        process="local",
        last=True,
    ) is None:
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

    accounted_values = [
        stage.duration_ms
        for stage in stages
        if stage.included_in_total
        and not stage.concurrent
        and stage.accounting_role != "overlap_diagnostic"
        and stage.duration_ms is not None
        and stage.status != INVALID
    ]
    accounted_before_residual = sum(accounted_values)
    residual = total - accounted_before_residual if total is not None and accounted_before_residual is not None else None
    if residual is not None and residual > 0.0005:
        # The catch-all residual is the UNATTRIBUTED gap, not a measured
        # stage.  It is reconciliation metadata: reported in the footer
        # (residual_ms / residual_pct) but never staged as a numbered row
        # with a percentage or bar of its own.
        residual_pct = _percentage(residual, total, total_wall_ms)
        warnings.append(
            f"global residual {residual:.3f}ms ({residual_pct:.2f}%) of command-to-response unaccounted"
        )

    cumulative = 0.0
    completed: list[WaterfallStage] = []
    for stage in stages:
        if stage.duration_ms is not None and stage.status != INVALID and not stage.concurrent:
            cumulative += stage.duration_ms
            cum_value: float | None = cumulative
        else:
            cum_value = None
        percentage = _percentage(stage.duration_ms, total, total_wall_ms)
        completed.append(WaterfallStage(**{**stage.__dict__, "cumulative_ms": cum_value, "percentage": percentage}))
    stages = completed

    accounted_values = [
        stage.duration_ms
        for stage in stages
        if stage.included_in_total
        and not stage.concurrent
        and stage.accounting_role != "overlap_diagnostic"
        and stage.duration_ms is not None
        and stage.status != INVALID
    ]
    accounted = sum(accounted_values) if accounted_values else None
    reconciliation = total - accounted if total is not None and accounted is not None else None
    tolerance = max(25.0, total * 0.0025) if total is not None and total >= 0 else None
    if reconciliation is not None and tolerance is not None and abs(reconciliation) > tolerance:
        warnings.append(
            f"reconciliation exceeds tolerance: {reconciliation:.3f}ms > {tolerance:.3f}ms"
        )

    residual_pct = _percentage(residual, total, total_wall_ms)
    reconciliation_status = (
        "OK" if reconciliation is not None and tolerance is not None and abs(reconciliation) <= tolerance
        else "EXCEEDS_TOLERANCE"
    )
    included_stages = [
        stage for stage in stages
        if stage.included_in_total and not stage.concurrent
        and stage.duration_ms is not None and stage.status != INVALID
    ]
    controllable_wall_ms = sum(
        (stage.duration_ms or 0.0) for stage in included_stages
        if stage.group in ("local", "application")
    ) if included_stages else None
    platform_wall_ms = sum(
        (stage.duration_ms or 0.0) for stage in included_stages
        if stage.group == "platform"
    ) if included_stages else None

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
        partial_waterfall=partial_waterfall,
        partial_flags=tuple(partial_flags),
        pre_python_interval_ms=pre_python_interval_ms,
        pre_python_interval_classification=pre_python_interval_classification,
    )


def _fmt_duration(value: float | None, status: str = "") -> str:
    if status == INVALID:
        return "INVALID"
    if value is None:
        return "-"
    return f"{value / 1000.0:7.3f}s"


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


def _bar(stage: WaterfallStage, total_ms: float | None, width: int) -> str:
    if stage.duration_ms is None or total_ms is None or total_ms <= 0:
        return " " * width
    units = max(1, round(stage.duration_ms / total_ms * width))
    char = "=" if stage.group == "platform" else "+" if stage.group == "local" else "#"
    if stage.status == INVALID:
        char = "!"
    return (char * min(width, units)).ljust(width)


def _diagnostic_group(stage: WaterfallStage) -> str:
    """Small sub-header label for an expanded-diagnostics row.

    Detail rows carry ``group="detail"`` uniformly, so the sub-header is
    derived from the row's source / key prefix / parent stage instead.
    """
    if stage.source == "node_timing":
        return "Node timings"
    if stage.source == "cpu_owner":
        return "CPU ownership"
    if stage.source == "active_read":
        return "Model reads"
    key = stage.key
    parent = stage.parent_key
    if key.startswith("vae_") or parent == "vae":
        return "VAE"
    if key.startswith("unet_") or parent == "unet_claim_to_ready":
        return "UNET"
    if key.startswith("output_") or parent in ("output_persistence", "remote_return_handoff"):
        return "Output"
    if key.startswith("local_receipt_") or parent == "remote_local_return":
        return "Return"
    if key.startswith("snapshot_graph_seed_"):
        return "Snapshot seed"
    if parent in ("prompt_executor_cache_setup", "remote_method_setup"):
        return "PromptExecutor"
    if parent == "sampler_node_to_sampling":
        return "Sampler"
    if parent == "post_sampling_transition":
        return "Post-sampling"
    return stage.group or "Detail"


def render_waterfall(report: WaterfallReport | Mapping[str, Any], *, terminal_columns: int | None = None) -> str:
    """Render a plain-ASCII report with deterministic width calculations."""
    if not isinstance(report, WaterfallReport):
        report = _report_from_value(report)
    detected = terminal_columns or shutil.get_terminal_size(fallback=(132, 40)).columns
    width = max(110, min(180, int(detected)))
    source_enabled = width >= 150
    source_width = 20 if source_enabled else 0
    label_target = max((len(stage.label) + (2 if stage.is_detail else 0) for stage in report.stages + report.details), default=28)
    fixed_without_label = 49 + (23 if source_enabled else 0)
    label_width = max(28, min(46, label_target, width - fixed_without_label - 24))
    fixed = fixed_without_label + label_width
    bar_width = max(24, width - fixed)
    if report.partial_waterfall:
        title = _ascii_text("V2 COLD WATERFALL - REMOTE/PARTIAL (awaiting host reconciliation)")
    else:
        title = _ascii_text(f"V2 COLD WATERFALL - {report.run_label or 'run'}")
    identity = report.identity
    lines = [title]
    lines.append(
        "Request: {request}  Instance: {instance}  GPU: {gpu}  Fresh: {fresh}".format(
            request=_ascii_text(report.request_id or "-"),
            instance=_ascii_text(identity.get("restored_instance_id") or "-"),
            gpu=_ascii_text(identity.get("gpu") or "-"),
            fresh=("YES" if identity.get("fresh") is True else "NO" if identity.get("fresh") is False else "-"),
        )
    )
    lines.append(f"TOTAL WALL:        {_fmt_duration(report.total_wall_ms)}   (command->response minus Modal scheduling)")
    lines.append(f"SCHEDULING:        {_fmt_duration(report.scheduling_ms)}   (informational - excluded from % and bars)")
    lines.append(f"COMMAND->RESPONSE: {_fmt_duration(report.total_ms)}")
    lines.append("")
    columns = f" # | {'Stage':<{label_width}} | {'Duration':>8} | {'Cum.':>8} | {'%':>6} | "
    if source_enabled:
        columns += f"{'Source':<{source_width}} | "
    columns += "Relative wall time"
    rule = "+-" + "-+-".join(["-" * 3, "-" * label_width, "-" * 10, "-" * 10, "-" * 7] + (["-" * source_width] if source_enabled else []) + ["-" * bar_width]) + "-+"
    lines.extend([rule, columns, rule])

    def source_text(stage: WaterfallStage) -> str:
        provenance = stage.provenance
        source = stage.source or "-"
        if provenance and source not in ("-", ""):
            if source == provenance:
                return provenance
            return f"{provenance}/{source}"
        return provenance or source

    # REMOTE/PARTIAL (awaiting host reconciliation): total_wall_ms is unknown,
    # so no percentage denominator and no bars exist for ANY stage row.
    reconciled = report.total_wall_ms is not None and report.total_wall_ms > 0

    row = 1
    for stage in report.stages:
        if stage.accounting_role != "top_level":
            continue
        prefix = f"{row:2d}"
        source = source_text(stage)
        label_text = stage.label
        if stage.concurrent:
            label_text = "~ " + label_text
        if stage.key == "modal_scheduling":
            if "modal_restore_begin_unavailable" in report.boundary_flags:
                label_text = "Modal scheduling + pre-Python restore (awaiting host reconciliation)"
            percentage_text = "-"
            bar_text = " " * bar_width
        elif not reconciled:
            percentage_text = "-"
            bar_text = " " * bar_width
        else:
            percentage_text = _fmt_num(stage.percentage, "%")
            bar_text = _bar(stage, report.total_wall_ms or report.total_ms, bar_width)
        line = f" {prefix} | {_shorten(label_text, label_width)} | {_fmt_duration(stage.duration_ms, stage.status):>10} | {_fmt_duration(stage.cumulative_ms):>10} | {percentage_text:>7} | "
        if source_enabled:
            line += f"{_shorten(source, source_width)} | "
        line += bar_text
        lines.append(line)
        row += 1
    lines.append(rule)

    # Expanded diagnostics: child / overlap-diagnostic rows grouped under
    # small sub-headers.  These rows never carry a percentage or a bar
    # (duration + status only); reconciliation metadata stays in the footer.
    diagnostic_groups: dict[str, list[WaterfallStage]] = {}
    for detail in report.details:
        if detail.accounting_role in ("top_level", "reconciliation"):
            continue
        diagnostic_groups.setdefault(_diagnostic_group(detail), []).append(detail)
    if diagnostic_groups:
        lines.append("")
        lines.append("Expanded diagnostics")
        for group_label, group_rows in diagnostic_groups.items():
            lines.append(f"[{group_label}]")
            for detail in group_rows:
                marker = "overlap" if detail.accounting_role == "overlap_diagnostic" else "detail"
                lines.append(
                    f"  {marker}: {_shorten(detail.label, label_width)}   {_fmt_duration(detail.duration_ms, detail.status)}"
                )
        lines.append("")
    accounted_pct = (
        _fmt_num(_percentage(report.accounted_ms, report.total_ms, report.total_wall_ms), "%")
        if reconciled and report.accounted_ms is not None
        else "-"
    )
    total_wall_pct = "  100.0%" if reconciled else "-"
    command_response_pct = "  100.0%" if reconciled else "-"
    total_wall_footer_bar = (
        _bar(WaterfallStage("total_wall", "", "application", None, None, report.total_wall_ms, None, None, "", MEASURED), report.total_wall_ms or report.total_ms, bar_width)
        if reconciled
        else " " * bar_width
    )
    lines.append(f"    | ACCOUNTED     | {_fmt_duration(report.accounted_ms):>10} |            | {accounted_pct:>7} | " + (" " * (source_width + 3) if source_enabled else "") + "." * bar_width)
    lines.append(f"    | RECONCILIATION | {_fmt_duration(report.reconciliation_ms):>10} |            |            | " + (" " * (source_width + 3) if source_enabled else "") + "." * bar_width)
    lines.append(f"    | TOTAL WALL | {_fmt_duration(report.total_wall_ms):>10} |            | {total_wall_pct:>7} | " + (" " * (source_width + 3) if source_enabled else "") + total_wall_footer_bar)
    lines.append(f"    | COMMAND -> RESPONSE | {_fmt_duration(report.total_ms):>10} |            | {command_response_pct:>7} | " + (" " * (source_width + 3) if source_enabled else "") + total_wall_footer_bar)
    lines.append(f"    | TOP-LEVEL ACCOUNTED | {_fmt_duration(report.accounted_ms):>10} |            | {accounted_pct:>7} | " + (" " * (source_width + 3) if source_enabled else "") + "." * bar_width)
    lines.append(f"    | GLOBAL RESIDUAL | {_fmt_duration(report.residual_ms):>10} |            |            | " + (" " * (source_width + 3) if source_enabled else "") + "." * bar_width)
    lines.append(f"    | RESIDUAL %     | {_fmt_num(report.residual_pct, '%'):>10} |            |            | " + (" " * (source_width + 3) if source_enabled else "") + "." * bar_width)
    lines.append(f"    | RECONCILIATION STATUS | {_ascii_text(report.reconciliation_status or '-'):>10} |            |            | " + (" " * (source_width + 3) if source_enabled else "") + "." * bar_width)
    lines.append(f"    | CONTROLLABLE APPLICATION WALL | {_fmt_duration(report.controllable_wall_ms):>10} |            |            | " + (" " * (source_width + 3) if source_enabled else "") + "." * bar_width)
    lines.append(f"    | PLATFORM/MODAL WALL | {_fmt_duration(report.platform_wall_ms):>10} |            |            | " + (" " * (source_width + 3) if source_enabled else "") + "." * bar_width)
    if report.pre_python_interval_ms is not None and report.total_wall_ms is None:
        lines.append(_ascii_text(
            f"Pending host reconciliation: command start -> Python resume = {report.pre_python_interval_ms:.3f} ms"
            f" - classification = {report.pre_python_interval_classification or 'scheduling + pre-Python restore (unresolved platform interval)'}"
        ))
    if report.boundary_flags:
        flag_explanations = {
            "modal_restore_begin_unavailable": "modal_scheduling covers submission->python_resume combined",
            "submission_boundary_unavailable": "submission boundary absent; scheduling spans cannot start at the local submit",
        }
        lines.append(
            _ascii_text(
                "Boundary flags: "
                + ", ".join(
                    f"{flag} ({flag_explanations.get(flag, '')})"
                    for flag in report.boundary_flags
                )
            )
        )
    if report.partial_waterfall:
        lines.append(
            _ascii_text(
                "REMOTE/PARTIAL WATERFALL - awaiting host reconciliation (missing: "
                + ", ".join(report.partial_flags)
                + ")"
            )
        )
    lines.append(rule)
    if report.warnings:
        lines.append("Warnings:")
        lines.extend(f"  - {warning}" for warning in report.warnings)
    else:
        lines.append("Warnings: none")
    return "\n".join(lines)


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
        partial_waterfall=bool(value.get("partial_waterfall", False)),
        partial_flags=tuple(value.get("partial_flags", ())),
        pre_python_interval_ms=value.get("pre_python_interval_ms"),
        pre_python_interval_classification=str(value.get("pre_python_interval_classification", "")),
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
        pre_keys = ("remote_method_setup", "prompt_executor_cache_setup", "first_node_to_clip", "clip_to_sampler_node", "sampler_node_to_sampling")
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
        "partial_waterfall": report.partial_waterfall,
        "partial_flags": list(report.partial_flags),
        "pre_python_interval_ms": report.pre_python_interval_ms,
        "pre_python_interval_classification": report.pre_python_interval_classification,
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
) -> dict[str, Any] | None:
    """Idempotent, non-raising waterfall finalizer (mutates *result* in place).

    Preserves an existing valid waterfall; otherwise builds a report from
    *result_view* (or *result* itself) via ``build_waterfall`` — or serializes
    a prebuilt *report* — and attaches it as ``result["waterfall"]``.

    A failure never raises into the workflow: an error marker is attached and
    a concise line is printed.  Returns the attached/preserved waterfall dict,
    or ``None`` when *result* is not a dict.  ``print_render=False`` skips the
    full waterfall render (host-side callers) while still attaching it.
    """
    if not isinstance(result, dict):
        return None
    existing = result.get("waterfall")
    if _is_valid_waterfall(existing):
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
