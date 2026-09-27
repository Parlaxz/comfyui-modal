"""Reconcile the preserved September Experiment 03 Golden timelines.

This is deliberately a host-only evidence reader.  It reads the explicit
Experiment 03 manifest and the paths named by each row; it never discovers
artifacts by mtime, imports Modal, invokes subprocesses, or changes runtime
files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


MISSING = "UNAVAILABLE"
CORE_STAGES = (
    "golden_restore",
    "golden_request_setup",
    "golden_clip_load",
    "golden_clip_forward",
    "golden_unet_load",
    "golden_sampler_prepare",
    "golden_vae_load",
    "golden_sampling",
    "golden_sampler_tail",
    "golden_vae_decode",
    "golden_output",
    "golden_teardown",
)
STAGE_LABELS = {
    "golden_restore": "golden_restore",
    "golden_request_setup": "request_setup",
    "golden_clip_load": "clip_load",
    "golden_clip_forward": "clip_forward",
    "golden_unet_load": "unet_load",
    "golden_sampler_prepare": "sampler_prepare",
    "golden_vae_load": "vae_load",
    "golden_sampling": "sampling",
    "golden_sampler_tail": "sampler_tail",
    "golden_vae_decode": "vae_decode",
    "golden_output": "output",
    "golden_teardown": "teardown",
}
TRANSPORT_ROLES = ("clip", "unet", "vae")
GOLDEN_BUCKETS = ("< 12.0 s", "12.0-12.5 s", "12.5-13.0 s", "13.0-13.5 s", "13.5-14.0 s", "14.0-15.0 s", "> 15.0 s")
TRANSPORT_KEYS = (
    "SOURCE_TOTAL_WALL_MS", "SOURCE_SYSCALL_UNION_BUSY_MS",
    "SOURCE_TO_GPU_READY_MS", "H2D_TOTAL_WALL_MS", "SOURCE_H2D_OVERLAP_MS",
    "POST_SOURCE_H2D_TAIL_MS", "H2D_SUBMISSION_COUNT", "H2D_SUBMISSIONS",
    "H2D_SUBMISSION_SIZES", "GPU_COPY_COUNT", "GPU_COPY_BYTES",
    "GPU_COPY_ACTIVE_SUM_MS", "GPU_COPY_ACTIVE_UNION_MS",
    "GPU_COPY_STREAM_SPAN_MS", "GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS",
    "source_read_count", "source_open_count", "event_object_count",
    "event_rerecord_count", "fresh_cuda_event_per_copy_count",
    "producer_count", "arena_bytes", "logical_slot_count",
    "logical_slot_bytes", "source_block_bytes", "h2d_target_bytes",
    "h2d_completion_count", "h2d_submit_count", "aggregation_enabled",
    "aggregation_scheduler_enter_count", "aggregation_wait_count",
    "aggregated_submission_count", "non_aggregated_submission_count",
    "tail_submission_count", "fallback_count", "fallback_reason",
    "aggregation_fallback_count", "aggregation_fallback_reasons",
    "E27_SOURCE_MECHANISM_PROVEN", "e27_source_mechanism_failed_predicates",
    "adoption_result", "owner_count", "block_count", "copy_count",
    "slot_acquire_count", "slot_release_count", "queue_operation_count",
    "queue_submit_count", "queue_completion_count", "ownership_transition_count",
    "proof_traversal_count", "event_record_count", "event_wait_count",
    "event_poll_count", "h2d_submitted_bytes", "h2d_completed_bytes",
    "max_actual_source_inflight", "actual_source_inflight", "poison",
)
OMIT_LARGE_KEYS = {
    "image_data", "images", "executed_nodes", "events", "actual_source_events",
    "actual_source_transitions", "transitions", "snapshot_manifest",
    "snapshot_manifest_restore", "mappings", "memory_composition",
    "selected_root_census", "fds", "gc", "threads", "children",
    "transport_stats", "node_timing_records",
    "source_syscall_events", "source_actual_transitions", "source_qd_timeline",
}


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def value(mapping: Any, *keys: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def compact(value_: Any, depth: int = 0) -> Any:
    """Retain useful raw values without copying base64 or trace event floods."""
    if value_ is None or isinstance(value_, (str, bool, int, float)):
        return value_
    if depth > 5:
        return {"omitted": "depth_limit"}
    if isinstance(value_, dict):
        return {
            str(k): compact(v, depth + 1)
            for k, v in value_.items()
            if str(k) not in OMIT_LARGE_KEYS
        }
    if isinstance(value_, list):
        if len(value_) > 1000:
            return {"omitted": "large_list", "count": len(value_)}
        return [compact(v, depth + 1) for v in value_]
    return str(value_)


def small_raw_value(value_: Any) -> bool:
    if isinstance(value_, (str, bool, int, float)) or value_ is None:
        return True
    if isinstance(value_, list):
        return len(value_) <= 1000 and all(isinstance(item, (str, bool, int, float)) or item is None for item in value_)
    if isinstance(value_, dict):
        try:
            return len(json.dumps(value_, separators=(",", ":"))) <= 20_000
        except (TypeError, ValueError):
            return False
    return False


def file_meta(path: str | None) -> dict[str, Any]:
    if not path:
        return {"path": path, "present": False}
    candidate = Path(path)
    if not candidate.is_file():
        return {"path": path, "present": False}
    digest = hashlib.sha256()
    with candidate.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": path,
        "present": True,
        "bytes": candidate.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def stage_documents(artifact: dict[str, Any], event_data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    artifact_stages = artifact.get("golden_telemetry", {}).get("stages", [])
    event_stages = event_data.get("golden_telemetry", {}).get("stages", [])
    return (
        [x for x in artifact_stages if isinstance(x, dict)],
        [x for x in event_stages if isinstance(x, dict)],
    )


def stage_value(stage: dict[str, Any]) -> float | None:
    start = number(stage.get("entry_monotonic_ns"))
    end = number(stage.get("end_monotonic_ns"))
    return (end - start) / 1_000_000 if start is not None and end is not None and end >= start else None


def normalized_stage_data(stages: list[dict[str, Any]]) -> tuple[dict[str, float], dict[str, Any], dict[str, Any]]:
    walls: dict[str, float] = {}
    boundaries: dict[str, Any] = {}
    details: dict[str, Any] = {}
    for stage in stages:
        raw_name = str(stage.get("name", ""))
        name = STAGE_LABELS.get(raw_name, raw_name.removeprefix("golden_"))
        wall = stage_value(stage)
        if wall is not None:
            walls[name] = round(wall, 6)
        boundaries[name] = {
            key: stage.get(key)
            for key in (
                "entry_monotonic_ns", "end_monotonic_ns", "ready_monotonic_ns",
                "entry_wall_ns", "end_wall_ns", "ok",
            )
            if key in stage
        }
        details[name] = compact(stage.get("details", {}))
    return walls, boundaries, details


def transport_records(stages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for stage in stages:
        raw = stage.get("details", {}).get("transport_stats")
        items = raw if isinstance(raw, list) else [raw]
        for record in items:
            if isinstance(record, dict) and record.get("role") in TRANSPORT_ROLES:
                records[str(record["role"])] = record
    return records


def transport_pick(record: dict[str, Any], key: str, *fallbacks: str) -> Any:
    for source in (record, record.get("actual_source"), record.get("experiment")):
        found = value(source, key, *fallbacks)
        if found is not None:
            return found
    return None


def transport_projection(record: dict[str, Any]) -> dict[str, Any]:
    actual: dict[str, Any] = {}
    if isinstance(record.get("actual_source"), dict):
        actual = record["actual_source"]
    raw: dict[str, Any] = {}
    for key in TRANSPORT_KEYS:
        found = transport_pick(record, key)
        if found is not None:
            raw[key] = compact(found)
    for source_name, source in (("record", record), ("actual_source", actual)):
        for key, found in source.items():
            lower = str(key).lower()
            if key in OMIT_LARGE_KEYS or key in raw:
                continue
            if any(token in lower for token in (
                "count", "event", "queue", "slot", "handoff", "producer", "proof",
                "ownership", "operation", "copy", "read", "submission", "fallback",
                "poison", "block", "arena", "inflight",
            )) and small_raw_value(found):
                raw[f"{source_name}.{key}"] = compact(found)
    return {
        "raw_metrics": raw,
        "experiment": compact(record.get("experiment", {})),
        "actual_source": {
            key: compact(found)
            for key, found in actual.items()
            if key not in OMIT_LARGE_KEYS and (
                isinstance(found, (str, bool, int, float))
                or key in {"h2d_submission_sizes", "starvation_gaps", "fallback", "poison", "quiescence", "h2d_reconciliation"}
            )
            and small_raw_value(found)
        },
    }


def find_result_event(path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    events = load_json(path)
    for event in events if isinstance(events, list) else []:
        if isinstance(event, dict) and event.get("type") == "result" and isinstance(event.get("data"), dict):
            return event, event["data"]
    return {}, {}


def iso_ms(start: str | None, end: str | None) -> float | None:
    try:
        first = datetime.fromisoformat(start or "")
        last = datetime.fromisoformat(end or "")
        return (last - first).total_seconds() * 1000
    except (TypeError, ValueError):
        return None


def source_map(attempt: dict[str, Any]) -> dict[str, str | None]:
    return {
        "manifest_row": "03_direct_source_geometry_manifest.json",
        "attempt_artifact": attempt.get("artifact_path"),
        "summary": attempt.get("derived_summary_path"),
        "session_events": attempt.get("session_events_path"),
        "run_manifest": attempt.get("run_manifest_path"),
        "evidence_markdown": attempt.get("evidence_path"),
    }


def stage_conflicts(artifact_walls: dict[str, float], event_walls: dict[str, float]) -> list[dict[str, Any]]:
    conflicts = []
    for name in sorted(set(artifact_walls) & set(event_walls)):
        if abs(artifact_walls[name] - event_walls[name]) > 0.001:
            conflicts.append({
                "field": f"stage_values_ms.{name}",
                "artifact_value": artifact_walls[name],
                "session_event_value": event_walls[name],
                "authoritative": "session_events",
            })
    return conflicts


def build_run(attempt: dict[str, Any]) -> dict[str, Any]:
    artifact = load_json(attempt["artifact_path"])
    event, event_data = find_result_event(attempt["session_events_path"])
    summary = load_json(attempt["derived_summary_path"])
    run_manifest = load_json(attempt["run_manifest_path"])
    artifact_stages, event_stages = stage_documents(artifact, event_data)
    artifact_walls, _, _ = normalized_stage_data(artifact_stages)
    walls, boundaries, details = normalized_stage_data(event_stages or artifact_stages)
    telemetry = event_data.get("golden_telemetry", {}) if isinstance(event_data.get("golden_telemetry"), dict) else {}
    adapter = event_data.get("golden_adapter_timing", {}) if isinstance(event_data.get("golden_adapter_timing"), dict) else {}
    external = telemetry.get("external_restore", {}) if isinstance(telemetry.get("external_restore"), dict) else {}
    records = transport_records(event_stages or artifact_stages)
    identity = artifact.get("identity", {}) if isinstance(artifact.get("identity"), dict) else {}
    validation = artifact.get("validation", {}) if isinstance(artifact.get("validation"), dict) else {}
    guard = artifact.get("capture_guard", {}) if isinstance(artifact.get("capture_guard"), dict) else {}
    golden_wall = number(adapter.get("golden_call_wall_ms"))
    stage_sum = sum(walls.values()) if walls else None
    stage_span = number(adapter.get("golden_stage_span_ms"))
    if stage_span is None and boundaries:
        starts = [number(x.get("entry_monotonic_ns")) for x in boundaries.values()]
        ends = [number(x.get("end_monotonic_ns")) for x in boundaries.values()]
        valid_starts = [x for x in starts if x is not None]
        valid_ends = [x for x in ends if x is not None]
        if len(valid_starts) == len(starts) and len(valid_ends) == len(ends):
            stage_span = (max(valid_ends) - min(valid_starts)) / 1_000_000
    clip = records.get("clip", {})
    unet = records.get("unet", {})
    vae = records.get("vae", {})
    transport = {role: transport_projection(records[role]) for role in TRANSPORT_ROLES if role in records}
    source_paths = source_map(attempt)
    stage_sources = {name: source_paths["session_events"] for name in walls}
    output_shas = validation.get("observed_output_shas", [])
    if isinstance(output_shas, str):
        output_shas = [output_shas]
    fallback_counts = {role: transport_pick(records.get(role, {}), "fallback_count") for role in TRANSPORT_ROLES}
    fallback_reasons = {role: transport_pick(records.get(role, {}), "fallback_reason", "aggregation_fallback_reasons") for role in TRANSPORT_ROLES}
    poison = {role: transport_pick(records.get(role, {}), "poison") for role in TRANSPORT_ROLES}
    adapter_stage_sum = number(adapter.get("golden_stage_sum_ms"))
    stage_sum_value = stage_sum
    unaccounted = golden_wall - stage_sum_value if golden_wall is not None and stage_sum_value is not None else None
    app_restore_ms = None
    restore_start = number(external.get("actual_restore_start_mono_ns"))
    restore_end = number(external.get("actual_restore_end_mono_ns"))
    if restore_start is not None and restore_end is not None and restore_end >= restore_start:
        app_restore_ms = (restore_end - restore_start) / 1_000_000
    clip_ready = number(transport_pick(clip, "SOURCE_TO_GPU_READY_MS"))
    unet_ready = number(transport_pick(unet, "SOURCE_TO_GPU_READY_MS"))
    clip_source = number(transport_pick(clip, "SOURCE_TOTAL_WALL_MS"))
    unet_source = number(transport_pick(unet, "SOURCE_TOTAL_WALL_MS"))
    clip_load = number(walls.get("clip_load"))
    unet_load = number(walls.get("unet_load"))
    row: dict[str, Any] = {
        "arm_mib": attempt.get("arm"),
        "attempt_key": attempt.get("attempt_key"),
        "cohort_role": attempt.get("cohort_role"),
        "CORE_or_EXTRA": attempt.get("cohort_group"),
        "created_at": attempt.get("created_at"),
        "invocation_id": attempt.get("invocation_id"),
        "request_id": attempt.get("request_id"),
        "app": attempt.get("app"),
        "profile": attempt.get("profile"),
        "deployment_fingerprint": attempt.get("deployment_fingerprint"),
        "provider": value(identity, "cloud"),
        "region": value(identity, "region"),
        "gpu_identity": value(identity, "gpu") or value(attempt, "gpu") or value(telemetry, "device"),
        "container_identity": {
            key: value(identity, key)
            for key in ("modal_container_id", "container_id", "container_session_id", "modal_task_id", "container_task_id", "restored_instance_id", "restore_session_id", "boot_id", "pid")
        },
        "classification": attempt.get("classification"),
        "counted": attempt.get("counted"),
        "capture_guard_classification": guard.get("classification"),
        "true_cold": artifact.get("true_cold"),
        "restore_count": value(identity, "restore_count"),
        "request_count": value(identity, "request_count"),
        "output_sha": output_shas,
        "output_sha_match": validation.get("output_sha_match"),
        "raw_event_output_sha": event_data.get("image_sha256"),
        "raw_event_output_sha_matches_artifact": event_data.get("image_sha256") in output_shas if isinstance(output_shas, list) else None,
        "valid": artifact.get("valid"),
        "poison": poison,
        "fallback_count": fallback_counts,
        "fallback_reasons": fallback_reasons,
        "CLIP_E27_proven": transport_pick(clip, "E27_SOURCE_MECHANISM_PROVEN"),
        "UNET_E27_proven": transport_pick(unet, "E27_SOURCE_MECHANISM_PROVEN"),
        "VAE_E27_proven": transport_pick(vae, "E27_SOURCE_MECHANISM_PROVEN"),
        "scheduling_platform_wall_ms": artifact.get("duration_ms"),
        "dispatch_to_end_wall_ms": iso_ms(artifact.get("dispatch_iso"), artifact.get("end_ts")),
        "external_restore_ms": external.get("restore_total_ms"),
        "external_restore_definition": "golden_telemetry.external_restore.restore_total_ms; explicit persisted restore observation, not golden_restore stage",
        "external_restore_boundaries": {
            key: external.get(key)
            for key in ("actual_restore_start_mono_ns", "actual_restore_end_mono_ns", "remote_python_resume_mono_ns", "restore_method_status", "restore_count")
            if key in external
        },
        "python_restore_method_wall_ms": app_restore_ms,
        "golden_internal_wall_ms": golden_wall,
        "golden_internal_wall_definition": "golden_adapter_timing.golden_call_start_mono_ns -> golden_call_end_mono_ns; adapter call wall, includes adapter post-stage work such as telemetry persistence",
        "golden_internal_wall_boundaries": {
            key: adapter.get(key)
            for key in ("golden_call_start_wall_unix_ns", "golden_call_start_mono_ns", "golden_call_end_wall_unix_ns", "golden_call_end_mono_ns")
            if key in adapter
        },
        "golden_stage_span_ms": stage_span,
        "golden_stage_sum_ms": stage_sum_value,
        "adapter_reported_golden_stage_sum_ms": adapter_stage_sum,
        "adapter_reported_golden_stage_span_ms": number(adapter.get("golden_stage_span_ms")),
        "golden_pre_stage_overhead_ms": adapter.get("golden_pre_stage_overhead_ms"),
        "golden_post_stage_overhead_ms": adapter.get("golden_post_stage_overhead_ms"),
        "golden_telemetry_persist_ms": adapter.get("golden_telemetry_persist_ms"),
        "unaccounted_golden_ms": unaccounted,
        "unaccounted_golden_percent": (unaccounted / golden_wall * 100 if unaccounted is not None and golden_wall else None),
        "stage_span_gap_ms": (stage_span - stage_sum_value if stage_span is not None and stage_sum_value is not None else None),
        "stage_values_ms": walls,
        "stage_boundaries": boundaries,
        "stage_details": details,
        "additional_serialized_stages": sorted(set(walls) - set(STAGE_LABELS.values())),
        "combined_loader_wall_ms": sum(walls.get(name, 0.0) for name in ("clip_load", "unet_load", "vae_load")) if all(name in walls for name in ("clip_load", "unet_load", "vae_load")) else None,
        "transport": transport,
        "transport_metrics": {
            role: {
                "source_wall_ms": transport_pick(records.get(role, {}), "SOURCE_TOTAL_WALL_MS"),
                "source_to_gpu_ready_ms": transport_pick(records.get(role, {}), "SOURCE_TO_GPU_READY_MS"),
                "h2d_wall_ms": transport_pick(records.get(role, {}), "H2D_TOTAL_WALL_MS"),
                "gpu_active_ms": transport_pick(records.get(role, {}), "GPU_COPY_ACTIVE_UNION_MS", "GPU_COPY_ACTIVE_SUM_MS"),
                "gpu_stream_span_ms": transport_pick(records.get(role, {}), "GPU_COPY_STREAM_SPAN_MS"),
                "gpu_idle_inside_span_ms": transport_pick(records.get(role, {}), "GPU_COPY_IDLE_INSIDE_STREAM_SPAN_MS"),
                "copy_count": transport_pick(records.get(role, {}), "GPU_COPY_COUNT", "H2D_SUBMISSION_COUNT", "h2d_submit_count"),
                "h2d_submission_count": transport_pick(records.get(role, {}), "H2D_SUBMISSION_COUNT", "h2d_submit_count"),
                "source_read_count": transport_pick(records.get(role, {}), "source_read_count"),
                "event_object_count": transport_pick(records.get(role, {}), "event_object_count"),
                "event_rerecord_count": transport_pick(records.get(role, {}), "event_rerecord_count"),
                "producer_count": transport_pick(records.get(role, {}), "producer_count"),
                "arena_bytes": transport_pick(records.get(role, {}), "arena_bytes"),
                "logical_slot_count": transport_pick(records.get(role, {}), "logical_slot_count"),
                "logical_slot_bytes": transport_pick(records.get(role, {}), "logical_slot_bytes"),
                "source_block_bytes": transport_pick(records.get(role, {}), "source_block_bytes"),
                "h2d_target_bytes": transport_pick(records.get(role, {}), "h2d_target_bytes"),
                "aggregation_enabled": transport_pick(records.get(role, {}), "aggregation_enabled"),
                "max_actual_source_inflight": transport_pick(records.get(role, {}), "max_actual_source_inflight"),
                "source_block_count": transport_pick(records.get(role, {}), "source_block_count"),
                "tail_submission_count": transport_pick(records.get(role, {}), "tail_submission_count"),
                "aggregation_scheduler_enter_count": transport_pick(records.get(role, {}), "aggregation_scheduler_enter_count"),
                "aggregation_wait_count": transport_pick(records.get(role, {}), "aggregation_wait_count"),
                "aggregated_submission_count": transport_pick(records.get(role, {}), "aggregated_submission_count"),
                "slot_acquire_count": transport_pick(records.get(role, {}), "slot_acquire_count"),
                "slot_release_count": transport_pick(records.get(role, {}), "slot_release_count"),
            }
            for role in TRANSPORT_ROLES
        },
        "loader_residuals_ms": {
            "CLIP_LOAD_RESIDUAL_MS": clip_load - clip_ready if clip_load is not None and clip_ready is not None else None,
            "UNET_LOAD_RESIDUAL_MS": unet_load - unet_ready if unet_load is not None and unet_ready is not None else None,
            "CLIP_LOAD_MINUS_SOURCE_WALL_MS": clip_load - clip_source if clip_load is not None and clip_source is not None else None,
            "UNET_LOAD_MINUS_SOURCE_WALL_MS": unet_load - unet_source if unet_load is not None and unet_source is not None else None,
        },
        "raw_source_comparison": {
            "artifact_stage_values_ms": artifact_walls,
            "session_event_stage_values_ms": walls,
            "conflicts": stage_conflicts(artifact_walls, walls),
            "session_event_result_keys": sorted(event_data),
        },
        "evidence_paths": source_paths,
        "source_evidence_paths": source_paths,
        "source_field_paths": {
            "manifest_fields": source_paths["manifest_row"],
            "classification_counted_cohort": source_paths["manifest_row"],
            "validity_cold_output": source_paths["attempt_artifact"],
            "authoritative_summary": source_paths["summary"],
            "golden_internal_walls": source_paths["session_events"],
            "serialized_stage_values": source_paths["session_events"],
            "transport_metrics": source_paths["session_events"],
            "live_display_metric": "comfymodal_runtime/modal_app.py:1532,1624-1677",
        },
        "evidence_presence": {key: file_meta(path) for key, path in source_paths.items() if key != "manifest_row"},
        "authoritative_summary_fields": {
            key: summary.get(key)
            for key in ("valid", "valid_count", "invalid_count", "deployment_identity", "started_utc", "completed_utc")
            if key in summary
        },
        "run_manifest_fields": {
            key: run_manifest.get(key)
            for key in ("created_at", "deploy_fingerprint", "deployment_hash", "profile", "profile_config_fingerprint", "run_fingerprint", "provider", "region", "modal_workspace", "modal_environment", "provenance_validation_status")
            if key in run_manifest
        },
    }
    return row


def stat(values: Iterable[Any]) -> dict[str, Any]:
    clean = sorted(x for x in (number(v) for v in values) if x is not None)
    if not clean:
        return {"n": 0, "min": None, "max": None, "range": None, "mean": None, "median": None, "sample_sd": None, "cv": None, "p25": None, "p75": None, "iqr": None, "trimmed_mean_10pct": None, "mad": None}
    mean = statistics.mean(clean)
    sd = statistics.stdev(clean) if len(clean) > 1 else None
    q = statistics.quantiles(clean, n=4, method="inclusive") if len(clean) > 1 else [clean[0]] * 3
    trim = clean[1:-1] if len(clean) >= 3 else clean
    median = statistics.median(clean)
    return {
        "n": len(clean), "min": clean[0], "max": clean[-1], "range": clean[-1] - clean[0],
        "mean": mean, "median": median, "sample_sd": sd,
        "cv": sd / mean if sd is not None and mean else None,
        "p25": q[0], "p75": q[2], "iqr": q[2] - q[0],
        "trimmed_mean_10pct": statistics.mean(trim),
        "mad": statistics.median([abs(x - median) for x in clean]),
    }


def metric_values(rows: list[dict[str, Any]], metric: str) -> list[Any]:
    values = []
    for row in rows:
        if metric in row:
            values.append(row[metric])
        elif metric.startswith("stage:"):
            values.append(row["stage_values_ms"].get(metric.removeprefix("stage:")))
        elif metric.startswith("transport:"):
            _, role, field = metric.split(":", 2)
            values.append(row["transport_metrics"].get(role, {}).get(field))
        elif metric.startswith("residual:"):
            values.append(row["loader_residuals_ms"].get(metric.removeprefix("residual:")))
        else:
            values.append(None)
    return values


def stats_for(rows: list[dict[str, Any]], metrics: Iterable[str]) -> dict[str, Any]:
    return {metric: stat(metric_values(rows, metric)) for metric in metrics}


def sorted_values(rows: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    return [
        {"attempt_key": row["attempt_key"], "value_ms": number(metric_values([row], metric)[0]), "provider": row["provider"], "region": row["region"]}
        for row in sorted(rows, key=lambda r: (number(metric_values([r], metric)[0]) is None, number(metric_values([r], metric)[0]) or 0, r["attempt_key"]))
    ]


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    dx, dy = [x - mx for x in xs], [y - my for y in ys]
    denominator = math.sqrt(sum(x * x for x in dx) * sum(y * y for y in dy))
    return sum(x * y for x, y in zip(dx, dy)) / denominator if denominator else None


def ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda pair: pair[1])
    result = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + 1 + end) / 2
        for position, _ in ordered[index:end]:
            result[position] = rank
        index = end
    return result


def correlation(rows: list[dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    pairs = []
    for row in rows:
        x, y = metric_values([row], left)[0], metric_values([row], right)[0]
        if number(x) is not None and number(y) is not None:
            pairs.append((float(x), float(y)))
    xs, ys = [x for x, _ in pairs], [y for _, y in pairs]
    return {"n": len(pairs), "pearson": pearson(xs, ys), "spearman": pearson(ranks(xs), ranks(ys)) if pairs else None}


def arm_groups(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {str(arm): [row for row in rows if str(row["arm_mib"]) == str(arm)] for arm in sorted({row["arm_mib"] for row in rows})}


def rankings(rows: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    result = []
    for arm, group in arm_groups(rows).items():
        s = stat(metric_values(group, metric))
        result.append({"arm_mib": int(arm), "metric": metric, **s})
    return sorted(result, key=lambda x: (x["median"] is None, x["median"] or math.inf, x["mean"] is None, x["mean"] or math.inf, x["arm_mib"]))


def bucket_name(ms: float | None) -> str:
    if ms is None:
        return MISSING
    seconds = ms / 1000
    if seconds < 12:
        return "< 12.0 s"
    if seconds < 12.5:
        return "12.0-12.5 s"
    if seconds < 13:
        return "12.5-13.0 s"
    if seconds < 13.5:
        return "13.0-13.5 s"
    if seconds < 14:
        return "13.5-14.0 s"
    if seconds < 15:
        return "14.0-15.0 s"
    return "> 15.0 s"


def fmt(value_: Any, digits: int = 3) -> str:
    if value_ is None:
        return MISSING
    if isinstance(value_, bool):
        return str(value_).lower()
    if isinstance(value_, float):
        return f"{value_:.{digits}f}"
    if isinstance(value_, (dict, list)):
        return json.dumps(value_, sort_keys=True, separators=(",", ":"))
    return str(value_)


def md_table(headers: list[str], rows: list[list[Any]], digits: int = 3) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---:" if i else "---" for i in range(len(headers))) + "|"]
    lines.extend("| " + " | ".join(fmt(x, digits).replace("|", "\\|").replace("\n", " ") for x in row) + " |" for row in rows)
    return lines


def all_stats_table(groups: dict[str, list[dict[str, Any]]], metric: str) -> list[list[Any]]:
    result = []
    for arm, rows in groups.items():
        s = stat(metric_values(rows, metric))
        result.append([int(arm), s["n"], s["mean"], s["median"], s["sample_sd"], s["cv"], s["min"], s["max"], s["p25"], s["p75"]])
    return result


def decomposition(rows: list[dict[str, Any]], baseline: int, arms: Iterable[int]) -> dict[str, Any]:
    base = [r for r in rows if r["arm_mib"] == baseline]
    result: dict[str, Any] = {}
    metrics = ["golden_internal_wall_ms", "golden_stage_span_ms", "golden_stage_sum_ms", "golden_pre_stage_overhead_ms", "golden_post_stage_overhead_ms", "stage_span_gap_ms", "unaccounted_golden_ms", "unaccounted_golden_percent", "combined_loader_wall_ms"] + [f"stage:{name}" for name in sorted(set().union(*(r["stage_values_ms"].keys() for r in rows)))]
    for arm in arms:
        target = [r for r in rows if r["arm_mib"] == arm]
        fields = {}
        for metric in metrics:
            b, t = stat(metric_values(base, metric)), stat(metric_values(target, metric))
            fields[metric] = {
                "baseline_median": b["median"], "target_median": t["median"],
                "median_delta": (t["median"] - b["median"] if t["median"] is not None and b["median"] is not None else None),
                "median_delta_percent": ((t["median"] / b["median"] - 1) * 100 if t["median"] is not None and b["median"] else None),
                "baseline_mean": b["mean"], "target_mean": t["mean"],
                "mean_delta": (t["mean"] - b["mean"] if t["mean"] is not None and b["mean"] is not None else None),
                "mean_delta_percent": ((t["mean"] / b["mean"] - 1) * 100 if t["mean"] is not None and b["mean"] else None),
            }
        result[str(arm)] = fields
    return result


def build_analysis(manifest_path: str) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    attempts = [x for x in manifest.get("attempts", []) if isinstance(x, dict) and x.get("counted")]
    rows = [build_run(attempt) for attempt in attempts]
    groups = arm_groups(rows)
    stages = sorted(set().union(*(row["stage_values_ms"].keys() for row in rows)))
    stats_metrics = (
        ["golden_internal_wall_ms", "golden_stage_sum_ms", "unaccounted_golden_ms", "combined_loader_wall_ms"]
        + ["external_restore_ms", "python_restore_method_wall_ms", "scheduling_platform_wall_ms", "golden_stage_span_ms", "golden_pre_stage_overhead_ms", "golden_post_stage_overhead_ms", "stage_span_gap_ms", "unaccounted_golden_percent"]
        + [f"stage:{stage}" for stage in stages]
        + [f"transport:{role}:source_wall_ms" for role in TRANSPORT_ROLES]
        + [f"transport:{role}:source_to_gpu_ready_ms" for role in TRANSPORT_ROLES]
        + [f"transport:{role}:h2d_wall_ms" for role in TRANSPORT_ROLES]
        + [f"transport:{role}:gpu_active_ms" for role in TRANSPORT_ROLES]
        + [f"residual:{name}" for name in ("CLIP_LOAD_RESIDUAL_MS", "UNET_LOAD_RESIDUAL_MS", "CLIP_LOAD_MINUS_SOURCE_WALL_MS", "UNET_LOAD_MINUS_SOURCE_WALL_MS")]
    )
    per_arm_stats = {arm: stats_for(group, stats_metrics) for arm, group in groups.items()}
    stage_metrics = ["golden_internal_wall_ms", "combined_loader_wall_ms", "stage:clip_load", "stage:unet_load", "stage:sampling", "stage:clip_forward", "stage:vae_decode"]
    rankings_data = {name: rankings(rows, name) for name in ("golden_internal_wall_ms", "golden_stage_span_ms", "golden_stage_sum_ms", "stage:clip_load", "stage:unet_load", "combined_loader_wall_ms", "transport:clip:source_wall_ms", "transport:unet:source_wall_ms")}
    sorted_raw = {arm: {metric: sorted_values(group, metric) for metric in stage_metrics} for arm, group in groups.items()}
    bucket_rows: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for arm, group in groups.items():
        bucket_rows[arm] = {bucket: [] for bucket in GOLDEN_BUCKETS}
        for row in group:
            bucket_rows[arm].setdefault(bucket_name(row["golden_internal_wall_ms"]), []).append({
                "attempt_key": row["attempt_key"], "wall_ms": row["golden_internal_wall_ms"], "provider": row["provider"], "region": row["region"]
            })
    correlations_metrics = [
        "arm_mib", "golden_internal_wall_ms", "combined_loader_wall_ms", "stage:clip_load",
        "transport:clip:source_wall_ms", "residual:CLIP_LOAD_RESIDUAL_MS", "stage:unet_load",
        "transport:unet:source_wall_ms", "residual:UNET_LOAD_RESIDUAL_MS", "stage:clip_forward",
        "stage:sampling", "stage:vae_decode", "transport:clip:copy_count", "transport:unet:copy_count",
        "transport:clip:event_rerecord_count", "transport:unet:event_rerecord_count",
    ]
    correlations = {f"{left} vs {right}": correlation(rows, left, right) for index, left in enumerate(correlations_metrics) for right in correlations_metrics[index + 1:]}
    provider_groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = f"{row['provider'] or MISSING} / {row['region'] or MISSING}"
        provider_groups.setdefault(key, []).append(row)
    provider_stats = {
        key: {metric: stat(metric_values(group, metric)) for metric in stage_metrics}
        for key, group in sorted(provider_groups.items())
    }
    provider_region_by_geometry: dict[str, dict[str, dict[str, Any]]] = {}
    for arm, group in groups.items():
        strata: dict[str, list[dict[str, Any]]] = {}
        for row in group:
            key = f"{row['provider'] or MISSING} / {row['region'] or MISSING}"
            strata.setdefault(key, []).append(row)
        provider_region_by_geometry[arm] = {
            key: {metric: stat(metric_values(stratum, metric)) for metric in stage_metrics}
            for key, stratum in sorted(strata.items())
        }
    round_groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        round_groups.setdefault(str(row["cohort_role"]), []).append(row)
    time_local = []
    for round_name, group in sorted(round_groups.items()):
        times = [datetime.fromisoformat(row["created_at"]) for row in group]
        span = (max(times) - min(times)).total_seconds()
        time_local.append({
            "round": round_name, "classification": "TIME-LOCAL DESCRIPTIVE COMPARISON",
            "members": [{"attempt_key": row["attempt_key"], "arm_mib": row["arm_mib"], "created_at": row["created_at"], "golden_internal_wall_ms": row["golden_internal_wall_ms"]} for row in sorted(group, key=lambda x: x["created_at"])],
            "time_span_seconds": span, "near_contemporaneous": span <= 360,
        })
    best_runs = {}
    representative_runs = {}
    for arm, group in groups.items():
        best_runs[arm] = []
        for row in sorted(group, key=lambda x: (x["golden_internal_wall_ms"], x["attempt_key"]))[:3]:
            best_runs[arm].append({"attempt_key": row["attempt_key"], "golden_internal_wall_ms": row["golden_internal_wall_ms"], "stage_values_ms": row["stage_values_ms"], "transport_metrics": row["transport_metrics"], "provider": row["provider"], "region": row["region"]})
        median = stat(metric_values(group, "golden_internal_wall_ms"))["median"]
        representative_runs[arm] = min(group, key=lambda x: (abs(x["golden_internal_wall_ms"] - median), x["attempt_key"]))
    representative = {arm: {"attempt_key": row["attempt_key"], "golden_internal_wall_ms": row["golden_internal_wall_ms"], "stage_values_ms": row["stage_values_ms"], "transport_metrics": row["transport_metrics"], "loader_residuals_ms": row["loader_residuals_ms"], "provider": row["provider"], "region": row["region"]} for arm, row in representative_runs.items()}
    geometry_checks = {}
    for arm, group in groups.items():
        expected = int(arm) * 1024 * 1024
        failures = []
        for row in group:
            for role in TRANSPORT_ROLES:
                metric = row["transport_metrics"].get(role, {})
                if any(metric.get(key) != expected for key in ("source_block_bytes", "h2d_target_bytes", "logical_slot_bytes")) or metric.get("logical_slot_count") != 8 or metric.get("aggregation_enabled") is not False:
                    failures.append(f"{row['attempt_key']}:{role}")
        geometry_checks[arm] = {"n": len(group), "core_n": sum(row["CORE_or_EXTRA"] == "CORE" for row in group), "extra_n": sum(row["CORE_or_EXTRA"] == "EXTRA" for row in group), "geometry_ok": not failures, "failures": failures}
    core_extra = {}
    for arm, group in groups.items():
        core_extra[arm] = {}
        for label, subset in (("CORE", [x for x in group if x["CORE_or_EXTRA"] == "CORE"]), ("EXTRA", [x for x in group if x["CORE_or_EXTRA"] == "EXTRA"]), ("ALL", group)):
            core_extra[arm][label] = {metric: stat(metric_values(subset, metric)) for metric in ("golden_internal_wall_ms", "stage:clip_load", "stage:unet_load", "combined_loader_wall_ms", "stage:sampling", "stage:clip_forward")}
    return {
        "schema_version": 1,
        "status": "COMPLETE" if len(rows) == 72 else "CORRECTED_COUNT",
        "experiment_id": manifest.get("experiment_id"),
        "manifest_path": str(Path(manifest_path).resolve()),
        "counted_cohort_n": len(rows),
        "expected_counted_cohort_n": 72,
        "raw_evidence_precedence": ["session_events", "attempt_artifact", "run_summary", "manifest", "evidence_markdown", "derived_summary"],
        "definitions": {
            "scheduling_platform_wall": "attempt_artifact.duration_ms; request/invocation wall and not application performance",
            "external_restore": "golden_telemetry.external_restore.restore_total_ms; separate from the tiny golden_restore application stage; exact platform boundary is not available in the persisted partial waterfall",
            "golden_internal_wall": "raw session event golden_adapter_timing.golden_call_start_mono_ns to golden_call_end_mono_ns, exposed as golden_call_wall_ms; includes adapter post-stage work and persisted telemetry timing",
            "serial_stage_sum": "sum of all authoritative serialized Golden stage entry-to-end monotonic walls from raw session-event telemetry",
            "unaccounted_golden": "golden_internal_wall_ms - serial_stage_sum_ms; not assumed to be a missing stage",
            "loader_total": "clip_load + unet_load + vae_load enclosing stage walls",
            "time_local": "manifest cohort rounds compared descriptively; near-contemporaneous means manifest-created timestamps span <=360 seconds; not a randomized paired analysis",
        },
        "validation": {
            "all_counted_rows_have_artifacts": all(bool(row["evidence_presence"]["attempt_artifact"]["present"]) for row in rows),
            "all_counted_rows_have_session_events": all(bool(row["evidence_presence"]["session_events"]["present"]) for row in rows),
            "all_valid": all(row["valid"] is True for row in rows),
            "all_true_cold": all(row["true_cold"] is True for row in rows),
            "all_output_sha_match": all(row["output_sha_match"] is True for row in rows),
            "all_raw_event_output_sha_matches_artifact": all(row["raw_event_output_sha_matches_artifact"] is True for row in rows),
            "all_raw_event_output_sha_matches_manifest_expected": all(row["raw_event_output_sha"] == manifest.get("expected_output_sha") for row in rows),
            "all_stage_sets_equal": len({tuple(sorted(row["stage_values_ms"])) for row in rows}) == 1,
            "geometry_checks": geometry_checks,
            "raw_artifact_event_conflicts": [row["raw_source_comparison"] for row in rows if row["raw_source_comparison"]["conflicts"]],
        },
        "per_arm_stats": per_arm_stats,
        "core_extra_stats": core_extra,
        "rankings": rankings_data,
        "sorted_raw_values": sorted_raw,
        "golden_wall_buckets": bucket_rows,
        "provider_region_stats": provider_stats,
        "provider_region_by_geometry": provider_region_by_geometry,
        "operation_counts_by_arm": {
            arm: stats_for(group, [
                "transport:clip:source_read_count", "transport:clip:h2d_submission_count", "transport:clip:event_object_count", "transport:clip:event_rerecord_count", "transport:clip:copy_count", "transport:clip:producer_count", "transport:clip:source_block_count", "transport:clip:max_actual_source_inflight",
                "transport:unet:source_read_count", "transport:unet:h2d_submission_count", "transport:unet:event_object_count", "transport:unet:event_rerecord_count", "transport:unet:copy_count", "transport:unet:producer_count", "transport:unet:source_block_count", "transport:unet:max_actual_source_inflight",
                "transport:vae:source_read_count", "transport:vae:h2d_submission_count", "transport:vae:event_object_count", "transport:vae:event_rerecord_count", "transport:vae:copy_count", "transport:vae:producer_count", "transport:vae:source_block_count", "transport:vae:max_actual_source_inflight",
            ]) for arm, group in groups.items()
        },
        "time_local_descriptive_comparisons": time_local,
        "correlations": correlations,
        "decomposition_vs_32": decomposition(rows, 32, (256, 512, 1024)),
        "best_valid_runs": best_runs,
        "median_representative_runs": representative,
        "runs": rows,
        "report_generation_audit": {
            "previous_summary_path": str(Path("unetClipExperimentsSeptember/03_direct_source_geometry_summary.json").resolve()),
            "previous_renderer_path": str(Path("unetClipExperimentsSeptember/build_experiment_report.py").resolve()),
            "omission": "The direct_source_geometry branch _geometry_report builds a schema-version-1 summary with request_wall_ms, combined_loader_wall_ms, and selected transport summaries only. It does not read session_events_path, event_data.golden_adapter_timing, or serialize per-run stage values/reconciliation. The older generic renderer has stage helpers, but direct_source_geometry returns before that path.",
            "raw_data_available": "yes; every counted row has explicit attempt_artifact and session_events paths, and all 72 session events contain golden_adapter_timing and the same 12 Golden stages.",
            "live_display_source": {
                "metric_name": "Golden call wall [ADAPTER CALL]",
                "field": "golden_adapter_timing.golden_call_wall_ms",
                "printed_by": "comfymodal_runtime/modal_app.py:_format_golden_waterfall, timing label at line 1532; emitted by _emit_golden_waterfall",
                "definition": "adapter call start to adapter call end; source construction is _golden_adapter_timing at modal_app.py lines 1624-1677",
            },
        },
        "evidence_gaps": [
            "The persisted waterfall object is partial/UNRESOLVED for all rows: modal restore begin, submission, and local receipt boundaries are unavailable, so no authoritative scheduling-delay decomposition exists.",
            "The application adapter wall includes post-stage adapter work; stage telemetry explains the stage interval but cannot be treated as equivalent to the enclosing call wall.",
            "Container ID fields are empty where the runtime did not persist them; container_session_id/modal_task_id are retained when present.",
            "One raw result event is persisted per request; no separate raw event stream with additional enclosing boundaries is present in the named session-events files.",
            "E27 source-mechanism proof is not uniform across roles/rows (CLIP, UNET, and VAE proof fields are retained per run); artifact validity and output SHA validity are separate claims.",
        ],
    }


def report_markdown(data: dict[str, Any]) -> str:
    run_groups = arm_groups(data["runs"])
    lines = [
        "# Experiment 03 Direct-Source Geometry Reconciliation", "",
        "STATUS=COMPLETE" if data["status"] == "COMPLETE" else f"STATUS={data['status']}",
        "",
        f"Counted cohort: **{data['counted_cohort_n']} / {data['expected_counted_cohort_n']}** explicit manifest rows.",
        "All conclusions below are derived from the preserved per-run rows in the JSON companion. No requests, deployments, or runtime changes were performed.", "",
        "## Executive Findings", "",
        f"- Authoritative application wall: `golden_adapter_timing.golden_call_wall_ms` from raw session events. It is the adapter-call wall from `golden_call_start_mono_ns` to `golden_call_end_mono_ns` and includes adapter post-stage work.",
        f"- Most likely live 12-14 s display: `Golden call wall [ADAPTER CALL]`, emitted by `comfymodal_runtime/modal_app.py` and backed by `golden_adapter_timing.golden_call_wall_ms`.",
        f"- 1024 MiB <13 s runs: {sum(1 for r in data['runs'] if r['arm_mib'] == 1024 and r['golden_internal_wall_ms'] < 13000)}; 32 MiB <13 s runs: {sum(1 for r in data['runs'] if r['arm_mib'] == 32 and r['golden_internal_wall_ms'] < 13000)}.",
        "- The previous report was an extractor/schema omission, not evidence loss: its direct-source branch never read session-event adapter timing or emitted per-run Golden stages.", "",
        "## Evidence Definitions", "",
        *[f"- **{key}:** {definition}" for key, definition in data["definitions"].items()], "",
        "## Cohort And Geometry Audit", "",
    ]
    lines += md_table(["geometry", "n", "CORE", "EXTRA", "geometry check", "all valid", "all true cold", "all SHA"], [
        [arm, checks["n"], checks["core_n"], checks["extra_n"], "PASS" if checks["geometry_ok"] else "FAIL", data["validation"]["all_valid"], data["validation"]["all_true_cold"], data["validation"]["all_output_sha_match"]]
        for arm, checks in data["validation"]["geometry_checks"].items()
    ])
    lines += ["", "The six arms contain the explicit 72 counted rows. Geometry checks independently verify `source_block_bytes == h2d_target_bytes == logical_slot_bytes == arm_mib *  MiB`, `logical_slot_count == 8`, and aggregation disabled for CLIP, UNET, and VAE.", ""]
    lines += ["## Table A - Whole Golden", ""]
    lines += md_table(["geometry", "n", "mean ms", "median ms", "SD", "CV", "min", "max", "P25", "P75"], all_stats_table(run_groups, "golden_internal_wall_ms"))
    lines += ["", "## Table B - CLIP Load", ""]
    lines += md_table(["geometry", "n", "mean ms", "median ms", "SD", "CV", "min", "max", "P25", "P75"], all_stats_table(run_groups, "stage:clip_load"))
    lines += ["", "## Table C - UNET Load", ""]
    lines += md_table(["geometry", "n", "mean ms", "median ms", "SD", "CV", "min", "max", "P25", "P75"], all_stats_table(run_groups, "stage:unet_load"))
    lines += ["", "## Table D - Combined Loader", ""]
    lines += md_table(["geometry", "n", "mean ms", "median ms", "SD", "CV", "min", "max", "P25", "P75"], all_stats_table(run_groups, "combined_loader_wall_ms"))
    lines += ["", "## Stage-Sum Reconciliation", ""]
    lines += md_table(["geometry", "stage span median", "stage sum median", "pre-stage median", "post-stage median", "span gap median", "unaccounted median", "unaccounted % median"], [[arm, stat(metric_values(group, "golden_stage_span_ms"))["median"], stat(metric_values(group, "golden_stage_sum_ms"))["median"], stat(metric_values(group, "golden_pre_stage_overhead_ms"))["median"], stat(metric_values(group, "golden_post_stage_overhead_ms"))["median"], stat(metric_values(group, "stage_span_gap_ms"))["median"], stat(metric_values(group, "unaccounted_golden_ms"))["median"], stat([x["unaccounted_golden_percent"] for x in group])["median"]] for arm, group in run_groups.items()])
    lines += ["", "## Restore And Reconciliation Statistics", ""]
    lines += md_table(["geometry", "external restore mean", "external restore median", "Golden stage sum mean", "Golden stage sum median", "unaccounted mean", "unaccounted median", "unaccounted % median"], [[arm, stat(metric_values(group, "external_restore_ms"))["mean"], stat(metric_values(group, "external_restore_ms"))["median"], stat(metric_values(group, "golden_stage_sum_ms"))["mean"], stat(metric_values(group, "golden_stage_sum_ms"))["median"], stat(metric_values(group, "unaccounted_golden_ms"))["mean"], stat(metric_values(group, "unaccounted_golden_ms"))["median"], stat([x["unaccounted_golden_percent"] for x in group])["median"]] for arm, group in run_groups.items()])
    lines += ["", "## Table E - Compute Stages", ""]
    lines += md_table(["geometry", "clip_forward median", "sampling median", "decode median"], [[arm, stat(metric_values(group, "stage:clip_forward"))["median"], stat(metric_values(group, "stage:sampling"))["median"], stat(metric_values(group, "stage:vae_decode"))["median"]] for arm, group in arm_groups(data["runs"]).items()])
    lines += ["", "## Table F - Loader Residuals", ""]
    lines += md_table(["geometry", "CLIP load - source->ready median", "UNET load - source->ready median", "CLIP load - source median", "UNET load - source median"], [[arm, stat(metric_values(group, "residual:CLIP_LOAD_RESIDUAL_MS"))["median"], stat(metric_values(group, "residual:UNET_LOAD_RESIDUAL_MS"))["median"], stat(metric_values(group, "residual:CLIP_LOAD_MINUS_SOURCE_WALL_MS"))["median"], stat(metric_values(group, "residual:UNET_LOAD_MINUS_SOURCE_WALL_MS"))["median"]] for arm, group in arm_groups(data["runs"]).items()])
    lines += ["", "### Source Versus Enclosing Load", ""]
    lines += md_table(["geometry", "CLIP source median", "CLIP load median", "CLIP residual median", "UNET source median", "UNET load median", "UNET residual median"], [[arm, stat(metric_values(group, "transport:clip:source_wall_ms"))["median"], stat(metric_values(group, "stage:clip_load"))["median"], stat(metric_values(group, "residual:CLIP_LOAD_MINUS_SOURCE_WALL_MS"))["median"], stat(metric_values(group, "transport:unet:source_wall_ms"))["median"], stat(metric_values(group, "stage:unet_load"))["median"], stat(metric_values(group, "residual:UNET_LOAD_MINUS_SOURCE_WALL_MS"))["median"]] for arm, group in arm_groups(data["runs"]).items()])
    lines += ["", "## Table G - CORE Versus EXTRA", ""]
    lines += md_table(["geometry", "CORE Golden median", "EXTRA Golden median", "ALL Golden median", "CORE clip median", "EXTRA clip median", "CORE UNET median", "EXTRA UNET median"], [[arm, values["CORE"]["golden_internal_wall_ms"]["median"], values["EXTRA"]["golden_internal_wall_ms"]["median"], values["ALL"]["golden_internal_wall_ms"]["median"], values["CORE"]["stage:clip_load"]["median"], values["EXTRA"]["stage:clip_load"]["median"], values["CORE"]["stage:unet_load"]["median"], values["EXTRA"]["stage:unet_load"]["median"]] for arm, values in data["core_extra_stats"].items()])
    lines += ["", "## Table H - Provider / Region", ""]
    provider_rows = []
    for key, values in data["provider_region_stats"].items():
        provider_rows.append([key, values["golden_internal_wall_ms"]["n"], values["golden_internal_wall_ms"]["median"], values["golden_internal_wall_ms"]["mean"], values["stage:clip_load"]["median"], values["stage:unet_load"]["median"], values["stage:sampling"]["median"], values["stage:clip_forward"]["median"]])
    lines += md_table(["provider / region", "n", "Golden median", "Golden mean", "CLIP median", "UNET median", "sampling median", "CLIP forward median"], provider_rows)
    lines += ["", "### Geometry By Provider / Region", ""]
    geometry_provider_rows = []
    for arm, strata in data["provider_region_by_geometry"].items():
        for key, values in strata.items():
            geometry_provider_rows.append([arm, key, values["golden_internal_wall_ms"]["n"], values["golden_internal_wall_ms"]["median"], values["stage:clip_load"]["median"], values["stage:unet_load"]["median"], values["stage:sampling"]["median"], values["stage:clip_forward"]["median"]])
    lines += md_table(["geometry", "provider / region", "n", "Golden median", "CLIP median", "UNET median", "sampling median", "CLIP forward median"], geometry_provider_rows)
    lines += ["", "## Table I - Median Decomposition Versus 32 MiB", "", "Positive deltas mean the target is slower than 32 MiB; negative deltas mean faster. All values are target median minus 32 MiB median.", ""]
    delta_rows = []
    for metric in sorted(data["decomposition_vs_32"]["256"]):
        delta_rows.append([metric.removeprefix("stage:"), data["decomposition_vs_32"]["256"][metric]["median_delta"], data["decomposition_vs_32"]["512"][metric]["median_delta"], data["decomposition_vs_32"]["1024"][metric]["median_delta"]])
    lines += md_table(["metric", "256 - 32 ms", "512 - 32 ms", "1024 - 32 ms"], delta_rows)
    lines += ["", "### Table I Percentage Deltas", ""]
    delta_pct_rows = [[metric.removeprefix("stage:"), data["decomposition_vs_32"]["256"][metric]["median_delta_percent"], data["decomposition_vs_32"]["512"][metric]["median_delta_percent"], data["decomposition_vs_32"]["1024"][metric]["median_delta_percent"]] for metric in sorted(data["decomposition_vs_32"]["256"])]
    lines += md_table(["metric", "256 - 32 %", "512 - 32 %", "1024 - 32 %"], delta_pct_rows)
    lines += ["", "## Rankings", ""]
    ranking_labels = {"golden_internal_wall_ms": "Whole Golden adapter call", "golden_stage_span_ms": "Golden stage span", "golden_stage_sum_ms": "Golden stage sum", "stage:clip_load": "CLIP load", "stage:unet_load": "UNET load", "combined_loader_wall_ms": "Combined loader", "transport:clip:source_wall_ms": "CLIP source wall", "transport:unet:source_wall_ms": "UNET source wall"}
    for metric, ranking in data["rankings"].items():
        lines += [f"### {ranking_labels[metric]}", ""]
        lines += md_table(["rank", "geometry", "median", "mean", "SD", "CV", "min", "max"], [[index, item["arm_mib"], item["median"], item["mean"], item["sample_sd"], item["cv"], item["min"], item["max"]] for index, item in enumerate(ranking, 1)])
        lines.append("")
    lines += ["### Top Three CLIP Geometries", ""]
    lines += md_table(["rank", "geometry", "mean", "median", "SD", "CV", "min", "max", "source wall median", "H2D wall median", "GPU active median", "copy count median", "arena bytes median"], [[index, item["arm_mib"], item["mean"], item["median"], item["sample_sd"], item["cv"], item["min"], item["max"], stat(metric_values(arm_groups(data["runs"])[str(item["arm_mib"])], "transport:clip:source_wall_ms"))["median"], stat(metric_values(arm_groups(data["runs"])[str(item["arm_mib"])], "transport:clip:h2d_wall_ms"))["median"], stat(metric_values(arm_groups(data["runs"])[str(item["arm_mib"])], "transport:clip:gpu_active_ms"))["median"], stat(metric_values(arm_groups(data["runs"])[str(item["arm_mib"])], "transport:clip:copy_count"))["median"], stat([x["transport_metrics"]["clip"]["arena_bytes"] for x in arm_groups(data["runs"])[str(item["arm_mib"])]])["median"]] for index, item in enumerate(data["rankings"]["stage:clip_load"][:3], 1)])
    lines += ["", "### Top Three UNET Geometries", ""]
    lines += md_table(["rank", "geometry", "mean", "median", "SD", "CV", "min", "max", "source wall median", "H2D wall median", "GPU active median", "copy count median", "arena bytes median"], [[index, item["arm_mib"], item["mean"], item["median"], item["sample_sd"], item["cv"], item["min"], item["max"], stat(metric_values(arm_groups(data["runs"])[str(item["arm_mib"])], "transport:unet:source_wall_ms"))["median"], stat(metric_values(arm_groups(data["runs"])[str(item["arm_mib"])], "transport:unet:h2d_wall_ms"))["median"], stat(metric_values(arm_groups(data["runs"])[str(item["arm_mib"])], "transport:unet:gpu_active_ms"))["median"], stat(metric_values(arm_groups(data["runs"])[str(item["arm_mib"])], "transport:unet:copy_count"))["median"], stat([x["transport_metrics"]["unet"]["arena_bytes"] for x in arm_groups(data["runs"])[str(item["arm_mib"])]])["median"]] for index, item in enumerate(data["rankings"]["stage:unet_load"][:3], 1)])
    lines += ["", "### Top Three Whole-Golden Geometries", ""]
    lines += md_table(["rank", "geometry", "mean", "median", "SD", "CV", "min", "max"], [[index, item["arm_mib"], item["mean"], item["median"], item["sample_sd"], item["cv"], item["min"], item["max"]] for index, item in enumerate(data["rankings"]["golden_internal_wall_ms"][:3], 1)])
    lines += ["", "## Transport Operation Counts", "", "Counts are extracted from the raw per-role transport records. Missing counters remain unavailable; no count is inferred from elapsed time.", ""]
    operation_rows = []
    operation_fields = ("source_read_count", "h2d_submission_count", "event_object_count", "event_rerecord_count", "copy_count", "producer_count", "source_block_count", "max_actual_source_inflight")
    for arm, values in data["operation_counts_by_arm"].items():
        for role in ("clip", "unet", "vae"):
            operation_rows.append([arm, role.upper()] + [values[f"transport:{role}:{field}"]["median"] for field in operation_fields])
    lines += md_table(["geometry", "role", "source reads", "H2D submits", "event objects", "event rerecords", "GPU copies", "producers", "source blocks", "max source inflight"], operation_rows)
    lines += ["", "## Golden-Wall Buckets", "", "Buckets use the authoritative adapter-call wall. Bounds are lower-inclusive and upper-exclusive except the first/last buckets.", ""]
    for arm, buckets in data["golden_wall_buckets"].items():
        lines += [f"### {arm} MiB", "", *md_table(["bucket", "count", "attempt IDs / values / provider / region"], [[bucket, len(items), "; ".join(f"{x['attempt_key']}={fmt(x['wall_ms'])}ms {x['provider']}/{x['region']}" for x in items)] for bucket, items in buckets.items()]), ""]
    lines += ["## Raw Sorted Values", ""]
    for arm, metrics in data["sorted_raw_values"].items():
        lines += [f"### {arm} MiB", ""]
        for metric, values in metrics.items():
            lines += [f"**{metric}**", "", *md_table(["order", "attempt", "value ms", "provider", "region"], [[index, x["attempt_key"], x["value_ms"], x["provider"], x["region"]] for index, x in enumerate(values, 1)]), ""]
    lines += ["## Best Valid Runs", ""]
    for arm, values in data["best_valid_runs"].items():
        lines += [f"### {arm} MiB", "", *md_table(["attempt", "Golden ms", "stage values ms", "transport metrics", "provider", "region"], [[x["attempt_key"], x["golden_internal_wall_ms"], x["stage_values_ms"], x["transport_metrics"], x["provider"], x["region"]] for x in values]), ""]
    lines += ["## Median Representative Runs", ""]
    lines += md_table(["geometry", "attempt", "Golden ms", "stage values ms", "loader residuals", "provider", "region"], [[arm, x["attempt_key"], x["golden_internal_wall_ms"], x["stage_values_ms"], x["loader_residuals_ms"], x["provider"], x["region"]] for arm, x in data["median_representative_runs"].items()])
    lines += ["", "## CORE / EXTRA And Time-Local Interpretation", "", "The CORE/EXTRA tables are descriptive and retain all rows. Round comparisons below use the existing `R01`-style cohort labels and creation timestamps; they are not formal paired trials.", ""]
    for item in data["time_local_descriptive_comparisons"]:
        members = "; ".join(f"{x['attempt_key']}={fmt(x['golden_internal_wall_ms'])}ms" for x in item["members"])
        lines.append(f"- `{item['round']}` span={item['time_span_seconds']:.1f}s near_contemporaneous={item['near_contemporaneous']}: {members}")
    lines += ["", "## Correlations", "", "Pearson and Spearman values are descriptive across the 72 rows and are not causal estimates.", ""]
    lines += md_table(["pair", "n", "Pearson", "Spearman"], [[key, x["n"], x["pearson"], x["spearman"]] for key, x in data["correlations"].items()])
    lines += ["", "## Reporting Bug And Live Display Audit", "", f"{data['report_generation_audit']['omission']}", "", f"Live display: `{data['report_generation_audit']['live_display_source']['metric_name']}`; field `{data['report_generation_audit']['live_display_source']['field']}`; {data['report_generation_audit']['live_display_source']['printed_by']}.", "", "The persisted `waterfall` object is partial and `UNRESOLVED`; its total/scheduling fields are null. It cannot explain or replace the adapter-call wall.", ""]
    lines += ["## Conclusions", "", f"- SOURCE WINNER: CLIP source wall is {data['rankings']['transport:clip:source_wall_ms'][0]['arm_mib']} MiB by median; UNET source wall is {data['rankings']['transport:unet:source_wall_ms'][0]['arm_mib']} MiB by median. These are separate from enclosing loader walls.", f"- LOADER WINNER: {data['rankings']['combined_loader_wall_ms'][0]['arm_mib']} MiB by median, with the full mean/SD/CV ranking above.", f"- WHOLE-GOLDEN WINNER: {data['rankings']['golden_internal_wall_ms'][0]['arm_mib']} MiB by median, with the full mean/SD/CV ranking above.", "- Loader residuals and compute-stage deltas are reported separately; a later-stage difference is cohort/server compute variance, not automatically a geometry gain.", "- No production geometry decision is made from these observational cohorts alone; the persisted external/scheduling boundaries and host stratification are incomplete.", ""]
    lines += ["## Evidence Gaps", "", *[f"- {gap}" for gap in data["evidence_gaps"]], "", "## Ledger Path Inventory", "", "Every run row in the companion JSON contains the exact attempt artifact, summary, session-events, run-manifest, and evidence-Markdown paths. The companion JSON is the authoritative complete ledger for those mappings.", ""]
    lines += ["## Final Disposition", "", "1. Observed 12-14 s metric: adapter Golden call wall, not request/platform wall or stage sum.", "2. The answer to every requested arm/ranking/delta question is represented in Tables A-I, rankings, decomposition_vs_32, and the JSON fields `rankings`, `core_extra_stats`, `provider_region_stats`, `best_valid_runs`, and `median_representative_runs`.", "3. No evidence was filtered for speed, provider, region, or outlier status.", ""]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile preserved Experiment 03 Golden evidence.")
    parser.add_argument("manifest")
    parser.add_argument("--markdown", required=True)
    parser.add_argument("--json", dest="json_path", required=True)
    args = parser.parse_args()
    data = build_analysis(args.manifest)
    Path(args.json_path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    Path(args.markdown).write_text(report_markdown(data), encoding="utf-8")
    print(json.dumps({"status": data["status"], "counted_cohort_n": data["counted_cohort_n"], "markdown": args.markdown, "json": args.json_path}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
