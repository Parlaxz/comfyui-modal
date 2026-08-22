"""E30 A/B evidence extraction and fail-closed comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v2_control.config import ConfigResolver
from v2_control.fingerprints import FingerprintEngine
from v2_control.profiles import Profiles
from v2_control.registry import FlagRegistry

DEFAULT_ARM_A = "e30-clip-qd-arm-a"
DEFAULT_ARM_B = "e30-clip-qd-arm-b"
EXPECTED_METRIC_SCHEMA_VERSION = 2
E30_METRIC_SCHEMA_VERSION = EXPECTED_METRIC_SCHEMA_VERSION
E30_ACCEPTED_OUTPUT_SHA = "20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260"
RESTORE_MISMATCH_TOLERANCE_MS = 2.0
RESTORE_TOLERANCE_MS = RESTORE_MISMATCH_TOLERANCE_MS
E31_FLAGS = (
    "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE",
    "COMFYMODAL_V2_E31_FORENSICS",
    "COMFYMODAL_V2_E31_FORWARD_PROFILE",
)

EVT_CLIP_QD_SOURCE_SUBMIT_START = "clip_qd_source_submit_start"
EVT_CLIP_QD_DEVICE_READY = "clip_qd_device_ready"
EVT_CLIP_QD_STATS = "clip_qd_stats"
EVT_CLIP_QD_FALLBACK = "clip_qd_fallback"
CLIP_QD_STATS_NAMES = {"clip_qd_stats"}
CLIP_QD_FALLBACK_NAMES = {"clip_qd_fallback"}
CLIP_QD_PUBLICATION_NAMES = {"clip_qd_spec_record_publish"}

CLIP_CALLER_START_NAMES = {
    "clip_loader_start",
    "clip_loader_setup_start",
    "clip_loader_source_select_start",
    "clip_loader_source_selection_start",
    "clip_source_select_start",
    "clip_source_selection_start",
}
CLIP_READY_NAMES = {
    "clip_device_ready",
    "clip_loader_device_ready",
    "clip_qd_device_ready",
}
CLIP_CALLER_ROLES = {
    "caller_start",
    "clip_loader_start",
    "clip_loader_caller_start",
    "source_selection_start",
    "source_select_start",
    "caller_before_source_selection",
}
CLIP_READY_ROLES = {
    "device_ready",
    "clip_device_ready",
    "clip_loader_device_ready",
}
UNET_SPAN_NAMES = {"unet:lane-pipeline"}
CANONICAL_QD_METRIC_FIELDS = (
    "CUDA_READINESS_WAIT_MS",
    "QD_SOURCE_IO_WALL_MS",
    "QD_SOURCE_GBPS",
    "QD_MAX_SOURCE_IO_INFLIGHT",
    "QD_H2D_ISSUE_TO_FINAL_COMPLETE_MS",
    "QD_SOURCE_TO_GPU_READY_MS",
)
CANONICAL_IDENTITY_FIELDS = (
    "v2ctl_invocation_id",
    "request_id",
    "profile",
    "profile_config_fingerprint",
    "deploy_fingerprint",
    "run_fingerprint",
    "artifact_path",
    "artifact_sha256",
)


def _load_profiles() -> tuple[Any, Any]:
    root = Path(__file__).resolve().parents[1]
    profiles = Profiles(root / "config" / "v2" / "profiles")
    resolver = ConfigResolver(root, profiles, FlagRegistry())
    return resolver.resolve(profile_name=DEFAULT_ARM_A), resolver.resolve(profile_name=DEFAULT_ARM_B)


def _flag_map(config: Any) -> dict[str, str]:
    return {flag.name: str(flag.value) for flag in config.flags}


def _profile_diff(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[1]
    profiles = Profiles(root / "config" / "v2" / "profiles")
    resolver = ConfigResolver(root, profiles, FlagRegistry())
    a = resolver.resolve(profile_name=args.arm_a)
    b = resolver.resolve(profile_name=args.arm_b)
    ma = _flag_map(a)
    mb = _flag_map(b)
    same: list[tuple[str, str]] = []
    different: list[tuple[str, str | None, str | None]] = []
    only_a: list[str] = []
    only_b: list[str] = []
    for name in sorted(set(ma) | set(mb)):
        va, vb = ma.get(name), mb.get(name)
        if va is None:
            only_b.append(name)
        elif vb is None:
            only_a.append(name)
        elif va == vb:
            same.append((name, va))
        else:
            different.append((name, va, vb))
    critical = [x for x in different if x[0] != "COMFYMODAL_V2_CLIP_QD_READER"]
    fail = bool(critical or only_a or only_b)
    if args.json:
        print(json.dumps({
            "arm_a": args.arm_a, "arm_b": args.arm_b,
            "identical": [{"name": n, "value": v} for n, v in same],
            "differing": [{"name": n, "arm_a": x, "arm_b": y} for n, x, y in different],
            "only_a": only_a, "only_b": only_b,
            "fail_closed": fail,
        }, indent=2, default=str))
    else:
        print("E30 A/B Profile Diff")
        print("====================")
        print(f"ARM A: {args.arm_a}")
        print(f"ARM B: {args.arm_b}")
        print(f"Identical flags: {len(same)}")
        print("Differing flags:")
        for name, va, vb in different:
            print(f"  {name}: {va} (ARM A) -> {vb} (ARM B)")
        print(f"A_B_CONFIG_DIFF = {'FAIL' if fail else 'CLEAN'}")
    return 1 if fail else 0


cmd_diff = _profile_diff


def _load_artifact(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: artifact not found: {path}", file=sys.stderr)
        raise SystemExit(1)
    with p.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("artifact must be a JSON object")
    return value


def _find_event(events: list[dict], name: str) -> dict | None:
    for event in events:
        if event.get("name") == name or event.get("event_name") == name:
            return event
    return None


def _find_canonical_event(events: list[dict], name: str) -> dict | None:
    for event in events:
        if event.get("name") == name:
            return event
    return None


def _find_events(events: list[dict], names: set[str]) -> list[dict]:
    return [event for event in events if event.get("name") in names or event.get("event_name") in names]


def _endpoint_events(events: list[dict], names: set[str], roles: set[str]) -> list[dict]:
    selected = _find_events(events, names)
    for event in events:
        meta = _metadata(event)
        role = _first(meta.get("semantic_endpoint"), meta.get("endpoint_role"), meta.get("endpoint"))
        if role in roles and event not in selected:
            selected.append(event)
    return selected


def _endpoint_role(event: dict | None, default: str, aliases: set[str]) -> str | None:
    if event is None:
        return None
    role = _first(_metadata(event).get("semantic_endpoint"), _metadata(event).get("endpoint_role"), _metadata(event).get("endpoint"))
    if role in aliases:
        return default
    return role or default


def _find_span(spans: list[dict], name: str) -> dict | None:
    for span in spans:
        if span.get("name") == name:
            return span
    return None


def _find_spans(spans: list[dict], names: str | set[str]) -> list[dict]:
    wanted = {names} if isinstance(names, str) else names
    return [span for span in spans if span.get("name") in wanted]


def _stamp(item: dict[str, Any]) -> int | None:
    for key in ("mono_ns", "timestamp_mono_ns", "start_mono_ns", "end_mono_ns"):
        value = item.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return None


def _interval(start: dict | None, end: dict | None) -> float | None:
    if start is None or end is None:
        return None
    a, b = _stamp(start), _stamp(end)
    if a is None or b is None or b < a:
        return None
    return round((b - a) / 1_000_000.0, 3)


def _span_duration(span: dict | None) -> float | None:
    if span is None:
        return None
    value = span.get("duration_ms")
    if isinstance(value, (int, float)):
        return float(value)
    start, end = span.get("start_mono_ns"), span.get("end_mono_ns")
    if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end >= start:
        return round((int(end) - int(start)) / 1_000_000.0, 3)
    return None


def _metric_schema(artifact: dict[str, Any], ledger: dict[str, Any] | None) -> tuple[Any, bool]:
    ledger = ledger or {}
    candidates = (
        artifact.get("metric_schema_version"),
        artifact.get("e30_metric_schema_version"),
        artifact.get("metric_schema", {}).get("version") if isinstance(artifact.get("metric_schema"), dict) else None,
        artifact.get("e30", {}).get("schema_version") if isinstance(artifact.get("e30"), dict) else None,
        artifact.get("schema_version"),
        ledger.get("metric_schema_version"),
        ledger.get("schema_version"),
    )
    declared = [value for value in candidates if value is not None]
    normalized = {str(value) for value in declared}
    return (declared[0] if declared and len(normalized) == 1 else None), len(normalized) > 1


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _metadata(item: dict | None) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    value = item.get("metadata")
    return value if isinstance(value, dict) else {}


def _fallback_present(value: Any) -> bool:
    if isinstance(value, list):
        return any(_fallback_present(item) for item in value)
    if isinstance(value, dict):
        if value.get("used") is True or value.get("active") is True:
            return True
        for key in ("pin_fallback", "alignment_tensor_count", "alignment_extra_source_bytes", "count"):
            counter = value.get(key)
            if isinstance(counter, (int, float)) and counter > 0:
                return True
        return False
    return _truth(value)


def _stat_value(record: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = record.get(name)
        if value is not None:
            return value
        nested = record.get("metrics")
        if isinstance(nested, dict) and nested.get(name) is not None:
            return nested[name]
    return None


def _read_provenance(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    artifact = Path(path)
    sibling = artifact.with_name(artifact.name + ".v2ctl-provenance.json")
    try:
        with sibling.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _artifact_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    digest = hashlib.sha256()
    with p.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity(artifact: dict[str, Any], provenance: dict[str, Any], path: str | Path | None) -> dict[str, Any]:
    nested_value = artifact.get("v2ctl")
    nested: dict[str, Any] = dict(nested_value) if isinstance(nested_value, dict) else {}
    ledger_value = artifact.get("canonical_ledger")
    ledger: dict[str, Any] = dict(ledger_value) if isinstance(ledger_value, dict) else {}
    ledger_identity_value = ledger.get("identity")
    ledger_identity: dict[str, Any] = dict(ledger_identity_value) if isinstance(ledger_identity_value, dict) else {}
    source_identity_value = artifact.get("source_identity")
    source_identity: dict[str, Any] = dict(source_identity_value) if isinstance(source_identity_value, dict) else {}
    provenance_artifact_value = provenance.get("artifact")
    provenance_artifact = dict(provenance_artifact_value) if isinstance(provenance_artifact_value, dict) else {}
    merged: dict[str, Any] = {}
    merged.update(provenance)
    merged.update(ledger_identity)
    merged.update(source_identity)
    merged.update(nested)
    merged.update(artifact)
    env = _first(artifact.get("effective_env"), artifact.get("effective_environment"), nested.get("effective_env"), nested.get("effective_environment"), provenance.get("effective_environment"), provenance.get("requested_environment"))
    env = env if isinstance(env, dict) else {}
    # The path supplied by the comparison command is authoritative.  An
    # embedded path can only corroborate it; it must never redirect sibling
    # provenance lookup or the SHA calculation.
    selected_path = path
    actual_path = str(Path(path).resolve()) if path else None
    def source_value(field: str, *aliases: str) -> Any:
        names = (field, *aliases)
        for source in (provenance, provenance_artifact, artifact, nested, ledger_identity, source_identity):
            for name in names:
                value = source.get(name)
                if value not in (None, ""):
                    return value
        return None

    conflicts: list[str] = []
    for field, aliases in (
        ("v2ctl_invocation_id", ()),
        ("request_id", ()),
        ("profile", ("profile_name",)),
        ("profile_config_fingerprint", ("config_fingerprint", "profile_fingerprint")),
        ("deploy_fingerprint", ()),
        ("run_fingerprint", ()),
        ("artifact_sha256", ("artifact_sha", "file_sha256")),
        ("artifact_path", ("normalized_artifact_path",)),
    ):
        artifact_value = _first(artifact.get(field), *(artifact.get(alias) for alias in aliases))
        provenance_value = _first(provenance.get(field), *(provenance.get(alias) for alias in aliases))
        if artifact_value not in (None, "") and provenance_value not in (None, "") and str(artifact_value) != str(provenance_value):
            conflicts.append(field)
    profile_config_fingerprint = source_value("profile_config_fingerprint")
    artifact_sha = source_value("artifact_sha256")
    provenance_path = source_value("artifact_path")
    provenance_only = {**provenance_artifact, **provenance}
    return {
        "v2ctl_invocation_id": source_value("v2ctl_invocation_id"),
        "request_id": source_value("request_id"),
        "profile": source_value("profile"),
        "config_fingerprint": profile_config_fingerprint,
        "profile_config_fingerprint": profile_config_fingerprint,
        "profile_fingerprint": source_value("profile_fingerprint", "config_profile_fingerprint"),
        "artifact_path": str(Path(provenance_path).resolve()) if provenance_path else None,
        "selected_artifact_path": actual_path,
        "artifact_sha256": artifact_sha,
        "actual_artifact_sha256": _artifact_sha256(selected_path),
        "provenance_present": bool(provenance),
        "provenance_missing_fields": [field for field in CANONICAL_IDENTITY_FIELDS if provenance_only.get(field) in (None, "") and field not in {"artifact_path", "artifact_sha256"}],
        "deploy_fingerprint": source_value("deploy_fingerprint"),
        "run_fingerprint": source_value("run_fingerprint"),
        "effective_env": env,
        "runtime_overrides": _first(merged.get("runtime_overrides"), artifact.get("overrides"), []),
        "reuse_detected": bool(_first(merged.get("reuse_detected"), merged.get("container_reused"), merged.get("snapshot_reused"), merged.get("restored_instance_reused"), merged.get("container_reuse_detected"), merged.get("reuse"), False)),
        "freshness": _first(artifact.get("fresh"), artifact.get("freshness"), ledger_identity.get("fresh"), ledger_identity.get("freshness"), source_identity.get("fresh"), provenance.get("fresh"), provenance.get("freshness")),
        "identity_conflicts": conflicts,
    }


def _aggregate_qd_stats(events: list[dict], artifact: dict[str, Any]) -> dict[str, Any]:
    records = [_metadata(event) for event in events if event.get("name") in CLIP_QD_STATS_NAMES]
    artifact_stats = artifact.get("qd_stats")
    if not records and isinstance(artifact_stats, dict):
        records.append(dict(artifact_stats))
    if not records:
        return {"event_count": 0, "inconsistent": False}
    aggregate: dict[str, Any] = {"event_count": len(records), "inconsistent": False}
    for key in ("bytes_read", "file_bytes", "planned_bytes", "h2d_submitted_bytes", "h2d_completed_bytes", "gpu_bytes", "per_read_errors", "submit_count", "completion_count"):
        values = [_stat_value(record, key) for record in records if isinstance(_stat_value(record, key), (int, float))]
        if values:
            total = 0.0
            for value in values:
                if isinstance(value, (int, float)):
                    total += float(value)
            aggregate[key] = total
    for key, aliases in {
        "bytes_read": ("QD_SOURCE_BYTES", "bytes_read"),
        "h2d_completed_bytes": ("QD_GPU_BYTES_COMPLETED", "h2d_completed_bytes"),
        "per_read_errors": ("QD_ERROR_COUNT", "per_read_errors"),
    }.items():
        if key in aggregate:
            continue
        total = 0.0
        found = False
        for record in records:
            value = _first(*(_stat_value(record, alias) for alias in aliases))
            if isinstance(value, (int, float)):
                total += float(value)
                found = True
        if found:
            aggregate[key] = total
            canonical_name = {
                "bytes_read": "QD_SOURCE_BYTES",
                "h2d_completed_bytes": "QD_GPU_BYTES_COMPLETED",
                "per_read_errors": "QD_ERROR_COUNT",
            }.get(key)
            if canonical_name and any(_stat_value(record, canonical_name) is not None for record in records):
                aggregate[canonical_name] = total
    for key, aliases in {
        "configured_qd": ("configured_qd",),
        "source_io_max_inflight": ("QD_MAX_SOURCE_IO_INFLIGHT", "source_io_max_inflight"),
        "observed_max_outstanding": ("observed_max_outstanding",),
    }.items():
        values = []
        for record in records:
            value = _first(*(_stat_value(record, alias) for alias in aliases))
            if value is not None:
                values.append(value)
        if values:
            aggregate[key] = values[0]
            if any(str(value) != str(values[0]) for value in values[1:]):
                aggregate["inconsistent"] = True
                aggregate[f"{key}_values"] = values
    source_walls = [_stat_value(record, "total_source_wall_ms") for record in records if isinstance(_stat_value(record, "total_source_wall_ms"), (int, float))]
    if source_walls:
        total_source_wall = 0.0
        for value in source_walls:
            if isinstance(value, (int, float)):
                total_source_wall += float(value)
        aggregate["total_source_wall_ms"] = total_source_wall
    for key in ("QD_SOURCE_IO_WALL_MS", "QD_H2D_ISSUE_TO_FINAL_COMPLETE_MS"):
        values = [_stat_value(record, key) for record in records]
        values = [value for value in values if isinstance(value, (int, float))]
        if values:
            aggregate[key] = sum(float(value) for value in values)
    source_rates = [_stat_value(record, "QD_SOURCE_GBPS") for record in records]
    source_rates = [value for value in source_rates if isinstance(value, (int, float))]
    if source_rates:
        total_rate = 0.0
        for value in source_rates:
            if isinstance(value, (int, float)):
                total_rate += float(value)
        aggregate["QD_SOURCE_GBPS"] = total_rate / len(source_rates)
    ready_values = [_stat_value(record, "QD_SOURCE_TO_GPU_READY_MS") for record in records]
    ready_values = [value for value in ready_values if isinstance(value, (int, float))]
    if ready_values:
        aggregate["QD_SOURCE_TO_GPU_READY_MS"] = max(float(value) for value in ready_values)
    statuses = [_stat_value(record, "status") for record in records if _stat_value(record, "status") not in (None, "running")]
    if statuses:
        aggregate["status"] = "ok" if all(status == "ok" for status in statuses) else str(next(status for status in statuses if status != "ok"))
    publication_values = []
    for record in records:
        value = _first(_stat_value(record, "publication_ok"), _stat_value(record, "publication_status"), _stat_value(record, "publish_status"))
        if value is not None:
            publication_values.append(value)
    if publication_values:
        aggregate["publication_ok"] = all(_truth(value) for value in publication_values)
        if any(not _truth(value) for value in publication_values):
            aggregate["inconsistent"] = True
    fallback_values = [_stat_value(record, "fallback") for record in records if _stat_value(record, "fallback") is not None]
    if fallback_values:
        aggregate["fallback"] = fallback_values
    aggregate["records"] = records
    return aggregate


def _extract_metrics(artifact: dict[str, Any], artifact_path: str | Path | None = None) -> dict[str, Any]:
    cl = artifact.get("canonical_ledger")
    cl = cl if isinstance(cl, dict) else None
    events = cl.get("events", []) if cl else []
    spans = cl.get("spans", []) if cl else []
    events = events if isinstance(events, list) else []
    spans = spans if isinstance(spans, list) else []
    stats = _aggregate_qd_stats(events, artifact)

    restore_entry = _find_canonical_event(events, "modal_restore_entry")
    restore_exit = _find_canonical_event(events, "modal_restore_exit")
    restore_events_ms = _interval(restore_entry, restore_exit)
    # Restore is defined only by modal_restore_entry/exit.  A span or serial
    # total is not a substitute for this interval.
    restore_span_ms = None
    restore_ms = restore_events_ms
    restore_mismatch = False

    source_submit = _find_canonical_event(events, EVT_CLIP_QD_SOURCE_SUBMIT_START)
    qd_ready = _find_canonical_event(events, EVT_CLIP_QD_DEVICE_READY)
    qd_interval_ms = _interval(source_submit, qd_ready)
    caller_starts = _endpoint_events(events, CLIP_CALLER_START_NAMES, CLIP_CALLER_ROLES)
    ready_events = _endpoint_events(events, CLIP_READY_NAMES, CLIP_READY_ROLES)
    caller_start = caller_starts[0] if caller_starts else None
    ready_event = ready_events[0] if ready_events else None
    common_clip_ms = _interval(caller_start, ready_event)
    start_role = _endpoint_role(caller_start, "clip_loader_caller_before_source_selection", CLIP_CALLER_ROLES)
    end_role = _endpoint_role(ready_event, "clip_device_ready", CLIP_READY_ROLES)

    hydration = _span_duration(_find_span(spans, "CLIP hydration"))
    if hydration is None:
        hydration = _span_duration(_find_span(spans, "CLIP GPU hydration"))
    artifact_qd_stats_value = artifact.get("qd_stats")
    artifact_qd_stats: dict[str, Any] = dict(artifact_qd_stats_value) if isinstance(artifact_qd_stats_value, dict) else {}
    legacy_source_wall = _first(_stat_value(stats, "total_source_wall_ms"), _stat_value(artifact_qd_stats, "total_source_wall_ms"), _stat_value(artifact, "total_source_wall_ms"))
    # total_source_wall_ms is retained as a legacy diagnostic only; it never
    # redefines the canonical hydration metric.
    clip_source_ms = hydration
    forward = _span_duration(_find_span(spans, "CLIP forward"))
    unet_spans = _find_spans(spans, UNET_SPAN_NAMES)
    unet_ms = max((_span_duration(span) or 0.0 for span in unet_spans), default=None)

    serial = cl.get("serial_ledger") if cl else None
    endpoint_status = cl.get("endpoint_status", "missing") if cl else "missing"
    serial_total = serial.get("total_ms") if isinstance(serial, dict) else None
    remote_wall = serial_total if endpoint_status == "ok" else None
    all_clip_events = [e for e in events if str(e.get("name", "")).startswith("clip_qd_")]
    qd_enabled = _first(
        artifact.get("qd_reader_enabled"), artifact.get("clip_qd_enabled"),
        stats.get("enabled"),
        (artifact.get("effective_env") or {}).get("COMFYMODAL_V2_CLIP_QD_READER") if isinstance(artifact.get("effective_env"), dict) else None,
    )
    qd_used = _first(artifact.get("qd_used"), bool(all_clip_events))
    publication = _first(
        artifact.get("publication_ok"), artifact.get("qd_publication_ok"), artifact.get("publication_status"),
        artifact.get("publish_status"), artifact.get("qd_publication_status"), stats.get("publication_ok"), stats.get("publication_status"),
        True if any(event.get("name") in CLIP_QD_PUBLICATION_NAMES for event in events) else None,
    )
    errors = _first(artifact.get("errors"), artifact.get("error"), stats.get("errors"), stats.get("per_read_errors"), stats.get("status") if stats.get("status") not in {None, "ok", "running"} else None, [])
    fatal = bool(artifact.get("fatal") or artifact.get("fatal_error") or artifact.get("canonical_ledger_error") or artifact.get("status") == "error" or stats.get("status") == "error")
    provenance_path = artifact_path
    provenance = _read_provenance(provenance_path)
    inline_provenance = artifact.get("provenance")
    if isinstance(inline_provenance, dict):
        provenance = {**inline_provenance, **provenance}
    identity = _identity(artifact, provenance, artifact_path)
    fresh = artifact.get("fresh")
    if fresh is None:
        fresh = _first(artifact.get("freshness"), artifact.get("freshness_status"), artifact.get("fresh_verified"), identity.get("freshness"))
    if fresh is None:
        restore_count, request_count = artifact.get("restore_count"), artifact.get("request_count")
        if artifact.get("canonical_ledger_status") == "ok" and restore_count is not None and request_count is not None:
            fresh = str(restore_count) == "1" and str(request_count or "1") == "1"
        else:
            fresh = "unknown"
    output_sha = artifact.get("output_sha")
    if output_sha is None and isinstance(artifact.get("output_descriptor"), list) and artifact["output_descriptor"]:
        first = artifact["output_descriptor"][0]
        if isinstance(first, dict):
            output_sha = _first(first.get("asset_id"), first.get("identity"))
    if isinstance(output_sha, str) and output_sha.startswith("sha256:"):
        output_sha = output_sha[7:]

    source_io_max_inflight = _first(stats.get("source_io_max_inflight"), stats.get("qd_max_source_io_inflight"), stats.get("max_inflight"), artifact.get("source_io_max_inflight"))
    source_io_field = "source_io_max_inflight" if source_io_max_inflight is not None else None
    if source_io_max_inflight is None and _first(stats.get("observed_max_outstanding"), artifact.get("observed_max_outstanding")) is not None:
        source_io_max_inflight = _first(stats.get("observed_max_outstanding"), artifact.get("observed_max_outstanding"))
        source_io_field = "observed_max_outstanding_equivalent"
    qd_source_io_wall_ms = _first(_stat_value(stats, "QD_SOURCE_IO_WALL_MS"), _stat_value(artifact_qd_stats, "QD_SOURCE_IO_WALL_MS"), _stat_value(artifact, "QD_SOURCE_IO_WALL_MS"))
    qd_source_gbps = _first(_stat_value(stats, "QD_SOURCE_GBPS"), _stat_value(artifact_qd_stats, "QD_SOURCE_GBPS"), _stat_value(artifact, "QD_SOURCE_GBPS"))
    qd_max_source_io_inflight = _first(_stat_value(stats, "QD_MAX_SOURCE_IO_INFLIGHT"), _stat_value(artifact_qd_stats, "QD_MAX_SOURCE_IO_INFLIGHT"), _stat_value(artifact, "QD_MAX_SOURCE_IO_INFLIGHT"), source_io_max_inflight)
    qd_h2d_issue_to_final_complete_ms = _first(_stat_value(stats, "QD_H2D_ISSUE_TO_FINAL_COMPLETE_MS"), _stat_value(artifact_qd_stats, "QD_H2D_ISSUE_TO_FINAL_COMPLETE_MS"), _stat_value(artifact, "QD_H2D_ISSUE_TO_FINAL_COMPLETE_MS"))
    qd_source_to_gpu_ready_ms = _first(_stat_value(stats, "QD_SOURCE_TO_GPU_READY_MS"), _stat_value(artifact_qd_stats, "QD_SOURCE_TO_GPU_READY_MS"), _stat_value(artifact, "QD_SOURCE_TO_GPU_READY_MS"))
    qd_source_bytes = _first(_stat_value(stats, "QD_SOURCE_BYTES"), _stat_value(artifact_qd_stats, "QD_SOURCE_BYTES"), _stat_value(artifact, "QD_SOURCE_BYTES"))
    qd_gpu_bytes_completed = _first(_stat_value(stats, "QD_GPU_BYTES_COMPLETED"), _stat_value(artifact_qd_stats, "QD_GPU_BYTES_COMPLETED"), _stat_value(artifact, "QD_GPU_BYTES_COMPLETED"))
    qd_error_count = _first(_stat_value(stats, "QD_ERROR_COUNT"), _stat_value(artifact_qd_stats, "QD_ERROR_COUNT"), _stat_value(artifact, "QD_ERROR_COUNT"))
    metric_schema_version, metric_schema_ambiguous = _metric_schema(artifact, cl)
    metrics: dict[str, Any] = {
        "METRIC_SCHEMA_VERSION": metric_schema_version,
        "METRIC_SCHEMA_AMBIGUOUS": metric_schema_ambiguous,
        "METRIC_SCHEMA_VALID": _schema_ok(metric_schema_version) and not metric_schema_ambiguous,
        "LEDGER_STATUS": artifact.get("canonical_ledger_status", "missing"),
        "ENDPOINT_STATUS": endpoint_status,
        "CLIP_LOADER_TO_DEVICE_READY_MS": common_clip_ms,
        "CLIP_INTERVAL_START_EVENT": caller_start.get("name", caller_start.get("event_name")) if caller_start else None,
        "CLIP_INTERVAL_END_EVENT": ready_event.get("name", ready_event.get("event_name")) if ready_event else None,
        "CLIP_INTERVAL_START_ROLE": start_role,
        "CLIP_INTERVAL_END_ROLE": end_role,
        "CLIP_SOURCE_TO_GPU_READY_MS": qd_interval_ms,
        "CLIP_SOURCE_MS": clip_source_ms,
        "CLIP_SOURCE_MS_STATUS": "legacy_non_comparable" if legacy_source_wall is not None else ("missing" if clip_source_ms is None else "secondary"),
        "LEGACY_TOTAL_SOURCE_WALL_MS": legacy_source_wall,
        "CLIP_HYDRATION_MS": hydration,
        "CLIP_FORWARD_MS": forward,
        "CONFIGURED_QD": _first(stats.get("configured_qd"), artifact.get("configured_qd")),
        "SOURCE_IO_MAX_INFLIGHT": source_io_max_inflight,
        "SOURCE_IO_MAX_INFLIGHT_FIELD": source_io_field,
        "QD_SOURCE_IO_WALL_MS": qd_source_io_wall_ms,
        "QD_SOURCE_GBPS": qd_source_gbps,
        "QD_MAX_SOURCE_IO_INFLIGHT": qd_max_source_io_inflight,
        "QD_H2D_ISSUE_TO_FINAL_COMPLETE_MS": qd_h2d_issue_to_final_complete_ms,
        "QD_SOURCE_TO_GPU_READY_MS": qd_source_to_gpu_ready_ms,
        "QD_SOURCE_BYTES": qd_source_bytes,
        "QD_GPU_BYTES_COMPLETED": qd_gpu_bytes_completed,
        "QD_ERROR_COUNT": qd_error_count,
        "OBSERVED_MAX_OUTSTANDING": _first(stats.get("observed_max_outstanding"), artifact.get("observed_max_outstanding")),
        "QD_USED": bool(qd_used),
        "QD_READER_ENABLED": qd_enabled,
        "QD_FALLBACK": bool(any(event.get("name") in CLIP_QD_FALLBACK_NAMES for event in events) or _fallback_present(artifact.get("qd_fallback")) or _fallback_present(stats.get("fallback"))),
        "QD_PUBLICATION_OK": publication,
        "QD_STATS": dict(stats),
        "QD_STATS_EVENT_COUNT": stats.get("event_count", 0),
        "QD_STATS_INCONSISTENT": bool(stats.get("inconsistent")),
        "QD_BYTES_READ": _first(stats.get("bytes_read"), stats.get("byte_reconciliation", {}).get("read") if isinstance(stats.get("byte_reconciliation"), dict) else None, artifact.get("bytes_read")),
        "QD_FILE_BYTES": _first(stats.get("file_bytes"), stats.get("planned_bytes"), stats.get("byte_reconciliation", {}).get("planned") if isinstance(stats.get("byte_reconciliation"), dict) else None, artifact.get("file_bytes")),
        "UNET_PIPELINE_MS": unet_ms,
        "TOTAL_UNATTRIBUTED_MS": serial.get("unattributed_ms") if isinstance(serial, dict) else None,
        "SERIAL_ZERO_GAP": serial.get("zero_gap") if isinstance(serial, dict) else None,
        "RESTORE_TOTAL_MS": restore_ms,
        "RESTORE_MS": restore_ms,
        "RESTORE_INTERVAL_SOURCE": "modal_restore_events" if restore_events_ms is not None else None,
        "RESTORE_EVENT_MS": restore_events_ms,
        "RESTORE_SPAN_MS": restore_span_ms,
        "RESTORE_INTERVAL_MISMATCH": restore_mismatch,
        "RESTORE_MISMATCH_DIAGNOSTIC": {
            "event_ms": restore_events_ms,
            "span_ms": restore_span_ms,
            "difference_ms": round(abs(restore_events_ms - restore_span_ms), 3) if restore_events_ms is not None and restore_span_ms is not None else None,
            "tolerance_ms": RESTORE_MISMATCH_TOLERANCE_MS,
            "mismatch": restore_mismatch,
        },
        "REMOTE_PYTHON_TO_DURABLE_MS": remote_wall,
        "SERIAL_LEDGER_TOTAL_MS": serial_total,
        "OUTPUT_SHA": output_sha,
        "FRESH": fresh,
        "REQUEST_ID": identity.get("request_id"),
        "PROFILE": identity.get("profile"),
        "PROFILE_CONFIG_FINGERPRINT": identity.get("profile_config_fingerprint"),
        "V2CTL_INVOCATION_ID": identity.get("v2ctl_invocation_id"),
        "FATAL": fatal,
        "ERRORS": errors,
        "IDENTITY": identity,
        "PROVENANCE": provenance,
        "RAW_EVENTS": events,
        "RAW_SPANS": spans,
    }
    required = ("CLIP_LOADER_TO_DEVICE_READY_MS", "RESTORE_TOTAL_MS", "REMOTE_PYTHON_TO_DURABLE_MS", "UNET_PIPELINE_MS", "OUTPUT_SHA")
    metrics["E30_EVIDENCE_STATUS"] = "OK" if metrics["METRIC_SCHEMA_VALID"] and all(metrics.get(key) is not None for key in required) else "MISSING"
    return metrics


def _truth(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on", "ok", "pass", "passed"}


def _schema_ok(value: Any) -> bool:
    try:
        return int(value) == EXPECTED_METRIC_SCHEMA_VERSION
    except (TypeError, ValueError):
        return False


def _same_number(left: Any, right: Any) -> bool:
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return left == right


def _expected_sha() -> str:
    return E30_ACCEPTED_OUTPUT_SHA


def _expected_fingerprints() -> dict[str, set[str]]:
    try:
        config_a, config_b = _load_profiles()
        return {
            "A": {FingerprintEngine(config_a).profile_config_fingerprint()},
            "B": {FingerprintEngine(config_b).profile_config_fingerprint()},
        }
    except Exception:
        return {"A": set(), "B": set()}


def _expected_control_plane_fingerprints() -> dict[str, dict[str, set[str]]]:
    try:
        config_a, config_b = _load_profiles()
        return {
            "A": {
                "deploy_fingerprint": {FingerprintEngine(config_a).deploy_fingerprint()},
                "run_fingerprint": {FingerprintEngine(config_a).run_fingerprint()},
            },
            "B": {
                "deploy_fingerprint": {FingerprintEngine(config_b).deploy_fingerprint()},
                "run_fingerprint": {FingerprintEngine(config_b).run_fingerprint()},
            },
        }
    except Exception:
        return {"A": {}, "B": {}}


def _config_validity(metrics_a: dict[str, Any], metrics_b: dict[str, Any]) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    correctness: list[str] = []
    expected_fingerprints = _expected_fingerprints()
    expected_control_plane = _expected_control_plane_fingerprints()
    for label, metrics in (("A", metrics_a), ("B", metrics_b)):
        ident = metrics.get("IDENTITY", {})
        if metrics.get("E30_EVIDENCE_STATUS") != "OK":
            reasons.append(f"{label}:e30_evidence_status_not_ok")
        for required_metric in ("RESTORE_TOTAL_MS", "REMOTE_PYTHON_TO_DURABLE_MS", "CLIP_LOADER_TO_DEVICE_READY_MS", "UNET_PIPELINE_MS", "OUTPUT_SHA"):
            if metrics.get(required_metric) is None:
                reasons.append(f"{label}:missing_{required_metric.lower()}")
        if metrics.get("LEDGER_STATUS") != "ok":
            reasons.append(f"{label}:ledger_status_not_ok")
        if metrics.get("ENDPOINT_STATUS") != "ok":
            reasons.append(f"{label}:endpoint_status_not_ok")
        if metrics.get("SERIAL_ZERO_GAP") is not True:
            reasons.append(f"{label}:serial_zero_gap_not_true")
        if not _truth(metrics.get("FRESH")):
            reasons.append(f"{label}:not_fresh")
        if metrics.get("FATAL"):
            reasons.append(f"{label}:fatal_error")
        if ident.get("reuse_detected"):
            reasons.append(f"{label}:reuse_detected")
        if metrics.get("QD_FALLBACK"):
            reasons.append(f"{label}:qd_fallback")
        if metrics.get("RESTORE_INTERVAL_MISMATCH"):
            reasons.append(f"{label}:restore_interval_mismatch")
        if metrics.get("UNET_PIPELINE_MS") is None:
            reasons.append(f"{label}:unet_pipeline_missing")
        if not ident.get("artifact_path"):
            reasons.append(f"{label}:missing_artifact_path")
        elif ident.get("actual_artifact_sha256") is None:
            reasons.append(f"{label}:artifact_not_on_disk")
        elif str(ident.get("artifact_path")).lower() != str(ident.get("selected_artifact_path")).lower():
            reasons.append(f"{label}:artifact_path_mismatch")
        if not ident.get("v2ctl_invocation_id"):
            reasons.append(f"{label}:missing_v2ctl_invocation_id")
        if not ident.get("request_id"):
            reasons.append(f"{label}:missing_request_id")
        if not ident.get("profile"):
            reasons.append(f"{label}:missing_profile")
        if not ident.get("deploy_fingerprint"):
            reasons.append(f"{label}:missing_deploy_fingerprint")
        elif ident.get("deploy_fingerprint") not in expected_control_plane.get(label, {}).get("deploy_fingerprint", set()):
            reasons.append(f"{label}:unexpected_deploy_fingerprint")
        if not ident.get("run_fingerprint"):
            reasons.append(f"{label}:missing_run_fingerprint")
        elif ident.get("run_fingerprint") not in expected_control_plane.get(label, {}).get("run_fingerprint", set()):
            reasons.append(f"{label}:unexpected_run_fingerprint")
        if ident.get("provenance_missing_fields"):
            reasons.append(f"{label}:provenance_missing:{','.join(ident['provenance_missing_fields'])}")
        if ident.get("identity_conflicts"):
            reasons.append(f"{label}:identity_conflict:{','.join(ident['identity_conflicts'])}")
        if not expected_fingerprints.get(label):
            reasons.append(f"{label}:profile_fingerprint_resolution_failed")
        if not ident.get("profile_config_fingerprint"):
            reasons.append(f"{label}:missing_config_fingerprint")
        elif ident.get("profile_config_fingerprint") not in expected_fingerprints.get(label, set()):
            reasons.append(f"{label}:unexpected_config_fingerprint")
        expected_artifact_sha = ident.get("artifact_sha256")
        actual_artifact_sha = ident.get("actual_artifact_sha256")
        if not expected_artifact_sha:
            reasons.append(f"{label}:missing_artifact_sha")
        elif actual_artifact_sha and str(expected_artifact_sha).lower().replace("sha256:", "") != actual_artifact_sha:
            reasons.append(f"{label}:artifact_sha_mismatch")
        if metrics.get("ERRORS"):
            reasons.append(f"{label}:errors_present")
        if not _schema_ok(metrics.get("METRIC_SCHEMA_VERSION")) or metrics.get("METRIC_SCHEMA_AMBIGUOUS"):
            reasons.append(f"{label}:metric_schema_missing_or_old")
        if metrics.get("OUTPUT_SHA") != _expected_sha():
            correctness.append(f"{label}:output_sha_not_accepted")
    ia, ib = metrics_a.get("IDENTITY", {}), metrics_b.get("IDENTITY", {})
    duplicate_reasons = {
        "request_id": "duplicate_request_id",
        "artifact_path": "duplicate_artifact_path",
        "artifact_sha256": "duplicate_artifact_sha256",
        "v2ctl_invocation_id": "duplicate_v2ctl_invocation_id",
        "profile_config_fingerprint": "duplicate_profile_config_fingerprint",
        "deploy_fingerprint": "duplicate_deploy_fingerprint",
        "run_fingerprint": "duplicate_run_fingerprint",
    }
    for field, reason in duplicate_reasons.items():
        if ia.get(field) and ia.get(field) == ib.get(field):
            reasons.append(reason)
    if ia.get("artifact_sha256") and ia.get("actual_artifact_sha256") and str(ia["artifact_sha256"]).lower().replace("sha256:", "") != ia["actual_artifact_sha256"]:
        reasons.append("A:artifact_sha_mismatch")
    if ib.get("artifact_sha256") and ib.get("actual_artifact_sha256") and str(ib["artifact_sha256"]).lower().replace("sha256:", "") != ib["actual_artifact_sha256"]:
        reasons.append("B:artifact_sha_mismatch")
    if ia.get("actual_artifact_sha256") and ia.get("actual_artifact_sha256") == ib.get("actual_artifact_sha256"):
        reasons.append("duplicate_artifact_sha256")
    if ia.get("profile") != DEFAULT_ARM_A:
        reasons.append("A:unexpected_profile")
    if ib.get("profile") != DEFAULT_ARM_B:
        reasons.append("B:unexpected_profile")
    env_a = ia.get("effective_env", {})
    env_b = ib.get("effective_env", {})
    if "COMFYMODAL_V2_CLIP_QD_READER" not in env_a:
        reasons.append("A:missing_effective_qd_reader")
    elif str(env_a.get("COMFYMODAL_V2_CLIP_QD_READER")) != "0":
        reasons.append("A:qd_reader_not_off")
    if metrics_a.get("QD_READER_ENABLED") is not None and _truth(metrics_a.get("QD_READER_ENABLED")):
        reasons.append("A:qd_reader_not_off")
    if metrics_a.get("QD_USED") is True:
        reasons.append("A:qd_used_while_off")
    if "COMFYMODAL_V2_CLIP_QD_READER" not in env_b:
        reasons.append("B:missing_effective_qd_reader")
    elif str(env_b.get("COMFYMODAL_V2_CLIP_QD_READER")) != "1":
        reasons.append("B:qd_reader_not_on")
    if metrics_b.get("QD_READER_ENABLED") is not None and not _truth(metrics_b.get("QD_READER_ENABLED")):
        reasons.append("B:qd_reader_not_on")
    if not _same_number(metrics_b.get("CONFIGURED_QD"), 4):
        reasons.append("B:configured_qd_not_4")
    if metrics_b.get("SOURCE_IO_MAX_INFLIGHT") is None:
        reasons.append("B:missing_source_io_max_inflight")
    elif not _same_number(metrics_b.get("SOURCE_IO_MAX_INFLIGHT"), metrics_b.get("CONFIGURED_QD")):
        reasons.append("B:source_io_max_inflight_mismatch")
    if metrics_b.get("QD_USED") is not True:
        reasons.append("B:qd_not_used")
    if metrics_b.get("QD_PUBLICATION_OK") is not True and not _truth(metrics_b.get("QD_PUBLICATION_OK")):
        reasons.append("B:publication_not_ok")
    if metrics_b.get("QD_BYTES_READ") is None or metrics_b.get("QD_FILE_BYTES") is None:
        reasons.append("B:byte_reconciliation_missing")
    elif not _same_number(metrics_b.get("QD_BYTES_READ"), metrics_b.get("QD_FILE_BYTES")):
        reasons.append("B:byte_reconciliation_mismatch")
    for label, env in (("A", env_a), ("B", env_b)):
        for flag in E31_FLAGS:
            if flag not in env:
                reasons.append(f"{label}:missing_effective_{flag}")
            elif str(env.get(flag)) != "0":
                reasons.append(f"{label}:{flag}_not_off")
    for label, metrics in (("A", metrics_a), ("B", metrics_b)):
        overrides = metrics.get("IDENTITY", {}).get("runtime_overrides", [])
        if overrides:
            reasons.append(f"{label}:runtime_overrides_present")
        if metrics.get("QD_STATS_INCONSISTENT"):
            reasons.append(f"{label}:qd_stats_inconsistent")
    if metrics_a.get("CLIP_INTERVAL_START_ROLE") != metrics_b.get("CLIP_INTERVAL_START_ROLE") or metrics_a.get("CLIP_INTERVAL_END_ROLE") != metrics_b.get("CLIP_INTERVAL_END_ROLE"):
        reasons.append("clip_interval_semantic_mismatch")
    if metrics_a.get("CLIP_LOADER_TO_DEVICE_READY_MS") is None or metrics_b.get("CLIP_LOADER_TO_DEVICE_READY_MS") is None:
        reasons.append("common_clip_interval_missing")
    if metrics_a.get("REMOTE_PYTHON_TO_DURABLE_MS") is None or metrics_b.get("REMOTE_PYTHON_TO_DURABLE_MS") is None:
        reasons.append("remote_endpoint_wall_missing")
    if metrics_a.get("RESTORE_TOTAL_MS") is not None and metrics_a.get("REMOTE_PYTHON_TO_DURABLE_MS") == metrics_a.get("RESTORE_TOTAL_MS") and metrics_a.get("SERIAL_LEDGER_TOTAL_MS") != metrics_a.get("RESTORE_TOTAL_MS"):
        reasons.append("A:restore_masquerading_request_wall")
    if metrics_b.get("RESTORE_TOTAL_MS") is not None and metrics_b.get("REMOTE_PYTHON_TO_DURABLE_MS") == metrics_b.get("RESTORE_TOTAL_MS") and metrics_b.get("SERIAL_LEDGER_TOTAL_MS") != metrics_b.get("RESTORE_TOTAL_MS"):
        reasons.append("B:restore_masquerading_request_wall")
    if metrics_a.get("OUTPUT_SHA") != metrics_b.get("OUTPUT_SHA"):
        correctness.append("output_sha_mismatch")
    return sorted(set(reasons)), sorted(set(correctness))


def validate_e30_pair(metrics_a: dict[str, Any], metrics_b: dict[str, Any]) -> dict[str, Any]:
    reasons, correctness_reasons = _config_validity(metrics_a, metrics_b)
    validity = {
        "valid": not reasons,
        "reasons": reasons,
        "fatal": bool(reasons),
        "required_checks": {
            "both_artifacts": bool(metrics_a and metrics_b),
            "ledger_endpoint_ok": not any("status_not_ok" in r for r in reasons),
            "provenance_complete": not any("missing_v2ctl_invocation_id" in r or "missing_artifact_path" in r for r in reasons),
            "common_clip_interval": not any("common_clip_interval" in r or "semantic_mismatch" in r for r in reasons),
        },
    }
    return {"validity": validity, "correctness_pass": not correctness_reasons, "correctness_reasons": correctness_reasons}


def _compute_verdict(metrics_a: dict[str, Any], metrics_b: dict[str, Any]) -> dict[str, Any]:
    gate = validate_e30_pair(metrics_a, metrics_b)
    validity = gate["validity"]
    correctness = gate["correctness_pass"] if validity["valid"] else False
    result: dict[str, Any] = {
        "EXPERIMENT_VALID": validity["valid"],
        "CORRECTNESS_PASS": correctness,
        "PERFORMANCE_RESULT": None,
        "validity": validity,
        "correctness_reasons": gate["correctness_reasons"],
        "verdict": "INVALID_EVIDENCE",
        "reason": "; ".join(validity["reasons"]) or "",
        "note": "",
    }
    if not validity["valid"]:
        return result
    if not correctness:
        result["verdict"] = "CORRECTNESS_FAILURE"
        result["reason"] = "; ".join(gate["correctness_reasons"])
        return result
    remote_a = metrics_a.get("REMOTE_PYTHON_TO_DURABLE_MS")
    remote_b = metrics_b.get("REMOTE_PYTHON_TO_DURABLE_MS")
    clip_a = metrics_a.get("CLIP_LOADER_TO_DEVICE_READY_MS")
    clip_b = metrics_b.get("CLIP_LOADER_TO_DEVICE_READY_MS")
    if not all(isinstance(value, (int, float)) for value in (remote_a, remote_b, clip_a, clip_b)):
        result["verdict"] = "NOT_DECISIVE"
        result["reason"] = "primary performance metrics missing"
        return result
    improvements = [((remote_a - remote_b) / remote_a * 100.0) if remote_a else 0.0, ((clip_a - clip_b) / clip_a * 100.0) if clip_a else 0.0]
    threshold = 2.0
    if all(value > threshold for value in improvements):
        result["verdict"] = "ARM_B_WIN"
        result["PERFORMANCE_RESULT"] = "ARM_B_WIN"
        result["reason"] = "ARM B improves remote wall and common CLIP interval"
    elif all(value < -threshold for value in improvements):
        result["verdict"] = "ARM_A_WIN"
        result["PERFORMANCE_RESULT"] = "ARM_A_WIN"
        result["reason"] = "ARM A improves remote wall and common CLIP interval"
    else:
        result["verdict"] = "NOT_DECISIVE"
        result["PERFORMANCE_RESULT"] = "NOT_DECISIVE"
        result["reason"] = "primary timing difference is below threshold or contradictory"
    return result


def _pct_change(a: float | None, b: float | None) -> str | None:
    if a is None or b is None or a == 0:
        return None
    return f"{((b - a) / a) * 100.0:+.1f}%"


def _comparison_data(path_a: str, path_b: str) -> dict[str, Any]:
    artifact_a, artifact_b = _load_artifact(path_a), _load_artifact(path_b)
    metrics_a = _extract_metrics(artifact_a, path_a)
    metrics_b = _extract_metrics(artifact_b, path_b)
    verdict = _compute_verdict(metrics_a, metrics_b)
    keys = [
        ("REMOTE_PYTHON_TO_DURABLE_MS", "Remote endpoint wall"),
        ("CLIP_LOADER_TO_DEVICE_READY_MS", "CLIP loader -> device ready"),
        ("RESTORE_TOTAL_MS", "Restore interval"),
        ("CLIP_SOURCE_MS", "Legacy source wall"),
        ("CLIP_SOURCE_TO_GPU_READY_MS", "QD source -> device ready"),
        ("CLIP_HYDRATION_MS", "CLIP hydration"),
        ("CLIP_FORWARD_MS", "CLIP forward"),
        ("UNET_PIPELINE_MS", "UNET pipeline"),
    ]
    rows = []
    for key, label in keys:
        va, vb = metrics_a.get(key), metrics_b.get(key)
        delta = round(vb - va, 3) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None
        rows.append({"metric": key, "label": label, "arm_a": va, "arm_b": vb, "delta": delta, "pct_change": _pct_change(va, vb) if delta is not None else None})
    return {"arm_a": metrics_a, "arm_b": metrics_b, "metrics": rows, "verdict": verdict}


def cmd_extract(args: argparse.Namespace) -> int:
    metrics = _extract_metrics(_load_artifact(args.artifact), args.artifact)
    if args.json:
        print(json.dumps(metrics, indent=2, default=str))
    else:
        print("E30 Artifact Extraction")
        print("=======================")
        for key in ("LEDGER_STATUS", "ENDPOINT_STATUS", "CLIP_LOADER_TO_DEVICE_READY_MS", "RESTORE_TOTAL_MS", "REMOTE_PYTHON_TO_DURABLE_MS", "UNET_PIPELINE_MS", "OUTPUT_SHA", "FRESH", "E30_EVIDENCE_STATUS"):
            print(f"{key}: {metrics.get(key)}")
        print(f"CLIP_SOURCE_MS: {metrics.get('CLIP_SOURCE_MS')} (legacy/non-comparable)")
    return 0 if metrics["E30_EVIDENCE_STATUS"] == "OK" else 1


def cmd_compare(args: argparse.Namespace) -> int:
    data = _comparison_data(args.arm_a, args.arm_b)
    if args.json:
        output = {"arm_a": Path(args.arm_a).name, "arm_b": Path(args.arm_b).name, **data}
        print(json.dumps(output, indent=2, default=str))
    else:
        print("E30 A/B Comparison")
        print("==================")
        for row in data["metrics"]:
            print(f"{row['label']}: A={row['arm_a']} B={row['arm_b']} delta={row['delta']}")
        verdict = data["verdict"]
        print(f"VERDICT = {verdict['verdict']} -- {verdict['reason']}")
    return 0 if data["verdict"]["verdict"] not in {"INVALID_EVIDENCE", "CORRECTNESS_FAILURE"} else 1


def build_evidence_manifest(arm_a: str | Path, arm_b: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Copy the selected raw artifacts and write an inspectable E30 manifest."""
    source_a, source_b = Path(arm_a), Path(arm_b)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    provenance_copied: dict[str, dict[str, Any] | None] = {}
    for label, source in (("A", source_a), ("B", source_b)):
        if not source.is_file():
            raise FileNotFoundError(str(source))
        target = destination / f"arm_{label}_{source.name}"
        shutil.copy2(source, target)
        copied.append({"arm": label, "source_path": str(source.resolve()), "copied_path": str(target.resolve()), "sha256": _artifact_sha256(target), "artifact": _load_artifact(str(source))})
        sibling = source.with_name(source.name + ".v2ctl-provenance.json")
        if sibling.is_file():
            sibling_target = destination / f"arm_{label}_{sibling.name}"
            shutil.copy2(sibling, sibling_target)
            provenance_copied[label] = {
                "source_path": str(sibling.resolve()),
                "copied_path": str(sibling_target.resolve()),
                "sha256": _artifact_sha256(sibling_target),
                "raw": json.loads(sibling.read_text(encoding="utf-8")),
            }
        else:
            provenance_copied[label] = None
    comparison = _comparison_data(str(source_a), str(source_b))
    manifest = {
        "schema_version": EXPECTED_METRIC_SCHEMA_VERSION,
        "selected_artifacts": [{"arm": item["arm"], "source_path": item["source_path"], "selected_path": comparison["arm_a" if item["arm"] == "A" else "arm_b"]["IDENTITY"].get("artifact_path"), "copied_path": item["copied_path"], "sha256": item["sha256"], "provenance_sibling": provenance_copied[item["arm"]], "request_id": comparison["arm_a" if item["arm"] == "A" else "arm_b"]["IDENTITY"].get("request_id"), "v2ctl_invocation_id": comparison["arm_a" if item["arm"] == "A" else "arm_b"]["IDENTITY"].get("v2ctl_invocation_id"), "profile": comparison["arm_a" if item["arm"] == "A" else "arm_b"]["IDENTITY"].get("profile"), "config_fingerprint": comparison["arm_a" if item["arm"] == "A" else "arm_b"]["IDENTITY"].get("config_fingerprint"), "profile_fingerprint": comparison["arm_a" if item["arm"] == "A" else "arm_b"]["IDENTITY"].get("profile_fingerprint")} for item in copied],
        "extracted_metrics": {"A": comparison["arm_a"], "B": comparison["arm_b"]},
        "validity_reasons": comparison["verdict"]["validity"]["reasons"],
        "comparison_result": comparison["verdict"],
    }
    manifest_path = destination / "e30_evidence_manifest.json"
    fd, temporary_name = tempfile.mkstemp(prefix=".e30_evidence_manifest.", suffix=".tmp", dir=str(destination))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(manifest, indent=2, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, manifest_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return manifest


build_campaign_manifest = build_evidence_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="E30 A/B Analysis Tool")
    sub = parser.add_subparsers(dest="command", required=True)
    diff = sub.add_parser("diff")
    diff.add_argument("--arm-a", default=DEFAULT_ARM_A)
    diff.add_argument("--arm-b", default=DEFAULT_ARM_B)
    diff.add_argument("--json", action="store_true")
    diff.add_argument("--verbose", action="store_true")
    extract = sub.add_parser("extract")
    extract.add_argument("artifact")
    extract.add_argument("--json", action="store_true")
    compare = sub.add_parser("compare")
    compare.add_argument("arm_a")
    compare.add_argument("arm_b")
    compare.add_argument("--json", action="store_true")
    manifest = sub.add_parser("manifest")
    manifest.add_argument("arm_a")
    manifest.add_argument("arm_b")
    manifest.add_argument("output_dir")
    args = parser.parse_args()
    if args.command == "diff":
        rc = _profile_diff(args)
    elif args.command == "extract":
        rc = cmd_extract(args)
    elif args.command == "compare":
        rc = cmd_compare(args)
    else:
        build_evidence_manifest(args.arm_a, args.arm_b, args.output_dir)
        rc = 0
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
