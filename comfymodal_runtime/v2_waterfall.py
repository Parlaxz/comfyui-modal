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


def _stage_candidate(result: Mapping[str, Any], key: str) -> _Candidate:
    event = lambda names, **kwargs: _event_boundary(result, names, **kwargs)
    origin = lambda name: _origin_boundary(result, name, name)
    remote_entry = (
        event("remote_method_entry", process="remote", last=True)
        or event("remote_method_entry", process="remote_method", last=True)
        or event("remote_method_entry", last=True)
    )
    restore_start = _timing_boundary(result, "restore_method_start", "restore_method_start")
    restore_end = _timing_boundary(result, "restore_method_end", "restore_method_end")
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
        start = origin("modal_submission_attempt_wall_unix_ns") or event(("modal_submission_attempt", "modal_first_iteration_start"), process="local")
        end = _timing_boundary(result, "remote_python_resume", "remote_python_resume") or restore_start
        return _candidate(result, start, end, duration_keys=("modal_submit_to_entry_ms", "submit2entry_ms"))
    if key == "application_restore":
        return _candidate(result, restore_start, restore_end, duration_keys=("restore_total_ms",))
    if key == "restore_to_method_entry":
        start = restore_end
        end = remote_entry
        return _candidate(result, start, end, duration_keys=("restore_end_to_modal_method_ms",))
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
        start = event(("output_persist_end", "output_collect_end", "remote_return_start"), last=True)
        end = event(("response_received", "final_result_received", "local_result_received"), process="local", last=True)
        return _candidate(result, start, end, duration_keys=("remote_return_ms", "trigger_to_result_ms"))
    if key == "remote_return_handoff":
        return _candidate(
            result,
            event("output_collect_end", last=True),
            event("remote_return_start", process="local", last=True),
        )
    return _Candidate()


_STAGE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("local_preparation", "Local preparation", "local"),
    ("modal_handle_submission", "Modal handle and submission", "local"),
    ("modal_scheduling", "Modal scheduling/host snapshot restoration", "platform"),
    ("application_restore", "Application restore", "application"),
    ("restore_to_method_entry", "Restore-to-method entry", "platform"),
    ("remote_method_setup", "Remote method setup", "application"),
    ("prompt_executor_cache_setup", "PromptExecutor/cache setup", "application"),
    ("first_node_to_clip", "First node to CLIP", "application"),
    ("clip_to_sampler_node", "CLIP to sampler node", "application"),
    ("sampler_node_to_sampling", "Sampler node to sampling", "application"),
    ("sampling", "Sampling", "application"),
    ("post_sampling_transition", "Post-sampling transition", "application"),
    ("vae", "VAE", "application"),
    ("output_persistence", "Output persistence", "application"),
    ("remote_return_handoff", "Remote result handoff", "local"),
    ("remote_local_return", "Remote/local return", "local"),
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


def _detail_stages(result: Mapping[str, Any], total_ms: float | None) -> tuple[WaterfallStage, ...]:
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
        ("sampler_lane_wait", "sampler lane wait", "remote_method_setup", "sampler_lane_wait_ms"),
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
            percentage=(candidate.duration_ms / total_ms * 100.0 if candidate.duration_ms is not None and total_ms and total_ms > 0 else None),
            source=candidate.source or "detail",
            status=candidate.status,
            is_detail=True,
            parent_key=parent,
            included_in_total=False,
            clock_scope="metadata",
        ))
    structured = _as_mapping(result).get("pre_sampler_structured_report")
    for index, record in enumerate(_as_mapping(structured).get("cpu_owner_records", ())):
        if not isinstance(record, Mapping):
            continue
        duration = record.get("wall_ms")
        operation = str(record.get("operation") or "operation")
        role = str(record.get("role") or "other")
        details.append(WaterfallStage(
            key=f"cpu_owner_{index}",
            label=f"CPU owner: {operation} [{role}]",
            group="detail",
            start_ns=None,
            end_ns=None,
            duration_ms=float(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None,
            cumulative_ms=None,
            percentage=(float(duration) / total_ms * 100.0 if isinstance(duration, (int, float)) and total_ms and total_ms > 0 else None),
            source="cpu_owner",
            status=DERIVED if isinstance(duration, (int, float)) and not isinstance(duration, bool) else UNAVAILABLE,
            is_detail=True,
            parent_key="prompt_executor_cache_setup",
            included_in_total=False,
            clock_scope="metadata",
        ))
    for index, record in enumerate(_as_mapping(structured).get("per_node_timings", ())):
        if not isinstance(record, Mapping):
            continue
        duration = record.get("duration_ms")
        node_label = str(record.get("class_type") or record.get("node_id") or "node")
        details.append(WaterfallStage(
            key=f"node_timing_{index}",
            label=f"Node: {node_label}",
            group="detail",
            start_ns=None,
            end_ns=None,
            duration_ms=float(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None,
            cumulative_ms=None,
            percentage=(float(duration) / total_ms * 100.0 if isinstance(duration, (int, float)) and total_ms and total_ms > 0 else None),
            source="node_timing",
            status=DERIVED if isinstance(duration, (int, float)) and not isinstance(duration, bool) else UNAVAILABLE,
            is_detail=True,
            parent_key="prompt_executor_cache_setup",
            included_in_total=False,
            clock_scope="metadata",
        ))
    for index, record in enumerate(_as_mapping(structured).get("active_read_records", ())):
        if not isinstance(record, Mapping):
            continue
        duration = record.get("wall_ms")
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
            duration_ms=float(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None,
            cumulative_ms=None,
            percentage=(float(duration) / total_ms * 100.0 if isinstance(duration, (int, float)) and total_ms and total_ms > 0 else None),
            source="active_read",
            status=DERIVED if isinstance(duration, (int, float)) and not isinstance(duration, bool) else UNAVAILABLE,
            is_detail=True,
            parent_key="remote_method_setup",
            included_in_total=False,
            clock_scope="metadata",
        ))
    return tuple(details)


def build_waterfall(
    *,
    result: Mapping[str, Any],
    timing: Mapping[str, Any],
    wall_ms: float | None,
    command_start_unix_ms: int | None = None,
    response_received_unix_ns: int | None = None,
    run_label: str = "",
) -> WaterfallReport:
    """Build a pure, additive report from a completed result.

    ``timing`` is intentionally accepted separately because older benchmark
    artifacts expose useful derived fields there.  Neither input is mutated.
    """
    result_view: Mapping[str, Any] = dict(result)
    if timing:
        result_view = {**result_view, "timing": dict(timing)}
    warnings: list[str] = []
    command_start = _command_boundary(command_start_unix_ms)
    response = _response_boundary(response_received_unix_ns)
    stages: list[WaterfallStage] = []
    for key, label, group in _STAGE_SPECS:
        if key == "local_preparation" and command_start is not None:
            candidate = _candidate(
                result_view,
                command_start,
                _origin_boundary(result_view, "local_receive_wall_ns", "local_receive_wall_ns")
                or _event_boundary(result_view, ("transport_entry", "modal_handle_lookup_start"), process="local"),
            )
        elif key == "remote_local_return" and response is not None:
            start = _event_boundary(result_view, ("output_persist_end", "output_collect_end", "remote_return_start"), last=True)
            candidate = _candidate(result_view, start, response, duration_keys=("remote_return_ms", "trigger_to_result_ms"))
        else:
            candidate = _stage_candidate(result_view, key)
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
        overlaps = tuple(other.label for other in stages[:index] if _intervals_overlap(stage, other))
        if overlaps:
            warnings.append(f"{stage.label}: overlaps {', '.join(overlaps)}")
            stages[index] = WaterfallStage(**{**stage.__dict__, "overlaps": overlaps, "status": INVALID})

    accounted_values = [
        stage.duration_ms
        for stage in stages
        if stage.included_in_total and stage.duration_ms is not None and stage.status != INVALID
    ]
    accounted_before_residual = sum(accounted_values)
    residual = total - accounted_before_residual if total is not None and accounted_before_residual is not None else None
    if residual is not None and residual > 0.0005:
        # The catch-all residual is the UNATTRIBUTED gap, not a measured
        # stage.  Keep it visible in the report but exclude it from the
        # accounted total so reconciliation reflects the real unexplained
        # gap instead of fabricating a perfect reconcile (accounted == total
        # with reconciliation == 0) by construction.
        stages.append(WaterfallStage(
            key="captured_timeline_gap",
            label="Captured timeline gaps / residual",
            group="platform",
            start_ns=None,
            end_ns=None,
            duration_ms=residual,
            cumulative_ms=None,
            percentage=(residual / total * 100.0 if total and total > 0 else None),
            source="accounting",
            status=DERIVED,
            included_in_total=False,
            clock_scope="wall",
            source_fields=("command_to_response_ms", "known_stage_durations_ms", "unaccounted"),
        ))
        warnings.append(f"captured residual excluded from accounted: {residual:.3f}ms unaccounted")

    cumulative = 0.0
    completed: list[WaterfallStage] = []
    for stage in stages:
        if stage.duration_ms is not None and stage.status != INVALID:
            cumulative += stage.duration_ms
            cum_value: float | None = cumulative
        else:
            cum_value = None
        percentage = (stage.duration_ms / total * 100.0 if stage.duration_ms is not None and total and total > 0 else None)
        completed.append(WaterfallStage(**{**stage.__dict__, "cumulative_ms": cum_value, "percentage": percentage}))
    stages = completed

    accounted_values = [
        stage.duration_ms
        for stage in stages
        if stage.included_in_total and stage.duration_ms is not None and stage.status != INVALID
    ]
    accounted = sum(accounted_values) if accounted_values else None
    reconciliation = total - accounted if total is not None and accounted is not None else None
    tolerance = max(50.0, total * 0.005) if total is not None and total >= 0 else None
    if reconciliation is not None and tolerance is not None and abs(reconciliation) > tolerance:
        warnings.append(
            f"reconciliation exceeds tolerance: {reconciliation:.3f}ms > {tolerance:.3f}ms"
        )

    identity = _identity(result)
    details = _detail_stages(result_view, total)
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


def _bar(stage: WaterfallStage, total_ms: float | None, width: int) -> str:
    if stage.duration_ms is None or total_ms is None or total_ms <= 0:
        return " " * width
    units = max(1, round(stage.duration_ms / total_ms * width))
    char = "=" if stage.group == "platform" else "+" if stage.group == "local" else "#"
    if stage.status == INVALID:
        char = "!"
    return (char * min(width, units)).ljust(width)


def render_waterfall(report: WaterfallReport | Mapping[str, Any], *, terminal_columns: int | None = None) -> str:
    """Render a plain-ASCII report with deterministic width calculations."""
    if not isinstance(report, WaterfallReport):
        report = _report_from_value(report)
    detected = terminal_columns or shutil.get_terminal_size(fallback=(132, 40)).columns
    width = max(110, min(180, int(detected)))
    source_enabled = width >= 150
    source_width = 10 if source_enabled else 0
    label_target = max((len(stage.label) + (2 if stage.is_detail else 0) for stage in report.stages + report.details), default=28)
    fixed_without_label = 49 + (13 if source_enabled else 0)
    label_width = max(28, min(46, label_target, width - fixed_without_label - 24))
    fixed = fixed_without_label + label_width
    bar_width = max(24, width - fixed)
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
    lines.append("")
    columns = f" # | {'Stage':<{label_width}} | {'Duration':>8} | {'Cum.':>8} | {'%':>6} | "
    if source_enabled:
        columns += f"{'Source':<{source_width}} | "
    columns += "Relative wall time"
    rule = "+-" + "-+-".join(["-" * 3, "-" * label_width, "-" * 10, "-" * 10, "-" * 7] + (["-" * source_width] if source_enabled else []) + ["-" * bar_width]) + "-+"
    lines.extend([rule, columns, rule])
    detail_by_parent: dict[str, list[WaterfallStage]] = {}
    for detail in report.details:
        detail_by_parent.setdefault(detail.parent_key, []).append(detail)
    row = 1
    for stage in report.stages:
        prefix = f"{row:2d}"
        source = stage.source or "-"
        line = f" {prefix} | {_shorten(stage.label, label_width)} | {_fmt_duration(stage.duration_ms, stage.status):>10} | {_fmt_duration(stage.cumulative_ms):>10} | {_fmt_num(stage.percentage, '%'):>7} | "
        if source_enabled:
            line += f"{_shorten(source, source_width)} | "
        line += _bar(stage, report.total_ms, bar_width)
        lines.append(line)
        row += 1
        for detail in detail_by_parent.get(stage.key, ()):
            detail_label = "  detail: " + detail.label
            detail_line = f" {row:2d} | {_shorten(detail_label, label_width)} | {_fmt_duration(detail.duration_ms, detail.status):>10} | {'-':>10} | {_fmt_num(detail.percentage, '%'):>7} | "
            if source_enabled:
                detail_line += f"{_shorten('detail', source_width)} | "
            detail_line += " " * bar_width
            lines.append(detail_line)
            row += 1
    lines.append(rule)
    lines.append(f"    | ACCOUNTED     | {_fmt_duration(report.accounted_ms):>10} |            | {_fmt_num((report.accounted_ms / report.total_ms * 100.0) if report.accounted_ms is not None and report.total_ms and report.total_ms > 0 else None, '%'):>7} | " + (" " * (source_width + 3) if source_enabled else "") + "." * bar_width)
    lines.append(f"    | RECONCILIATION | {_fmt_duration(report.reconciliation_ms):>10} |            |            | " + (" " * (source_width + 3) if source_enabled else "") + "." * bar_width)
    lines.append(f"    | COMMAND -> RESPONSE | {_fmt_duration(report.total_ms):>10} |            |  100.0% | " + (" " * (source_width + 3) if source_enabled else "") + _bar(WaterfallStage("total", "", "application", None, None, report.total_ms, None, 100.0, "", MEASURED), report.total_ms, bar_width))
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
    }


__all__ = [
    "Boundary", "WaterfallStage", "WaterfallReport", "build_waterfall",
    "render_waterfall", "render_comparison", "waterfall_to_dict",
]
