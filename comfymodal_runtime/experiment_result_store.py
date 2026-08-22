"""Deterministic per-run result persistence for the V2 A/B benchmark campaign.

Standalone, dependency-free helpers that persist one flat JSON record per
benchmark run and a single ``campaign_manifest.json`` per campaign directory.

All extraction is defensive: every lookup goes through ``Mapping.get`` with
fallbacks, nothing raises for malformed result dicts, and every value is
JSON-normalized before writing (non-serializable objects fall back to
``repr``).

Owned by the V2 A/B benchmark campaign (comfyui-modal).  Nothing here imports
Modal, ComfyUI, or the harness; it is import-safe in any context.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = [
    "build_run_record",
    "run_storage_dir",
    "save_experiment_run",
    "write_campaign_manifest",
]

_CRITICAL_PATH_RE = re.compile(r"(ms|s$|_wall|_latency)")
_ENV_PREFIXES = ("COMFYMODAL_", "V2_BENCHMARK")
_RUN_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]")


# ────────────────────────────────────────────────────────────────────────────
# JSON normalization helpers
# ────────────────────────────────────────────────────────────────────────────


def _json_safe(value: Any, _depth: int = 0) -> Any:
    """Recursively coerce *value* into a JSON-serializable form.

    Mappings/lists are rebuilt recursively; all other non-serializable objects
    fall back to ``repr``.  ``float`` NaN/Infinity (which ``json`` emits as
    non-standard literals) are replaced with ``None``.
    """
    if _depth > 64:  # pathological nesting guard
        return repr(value)[:2000]
    if isinstance(value, Mapping):
        return {
            str(k): _json_safe(v, _depth + 1) for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(v, _depth + 1) for v in value]
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    return repr(value)


def _dumps(data: Any) -> str:
    """Deterministic JSON dump (sorted keys, normalized values)."""
    return json.dumps(
        _json_safe(data), indent=2, sort_keys=True, ensure_ascii=False,
    )


# ────────────────────────────────────────────────────────────────────────────
# Storage helpers
# ────────────────────────────────────────────────────────────────────────────


def run_storage_dir(
    *,
    base_dir: str | Path | None = None,
    timestamp: str | None = None,
) -> Path:
    """Return (and create) the per-run storage directory.

    Directory name is ``<UTC YYYYMMDD-HHMMSS>`` — or *timestamp* when given.
    *base_dir* defaults to ``./benchmark_runs`` (relative to the CWD).
    """
    root = Path(base_dir) if base_dir is not None else Path("./benchmark_runs")
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    directory = root / stamp
    directory.mkdir(parents=True, exist_ok=True)
    return directory


# ────────────────────────────────────────────────────────────────────────────
# Record construction
# ────────────────────────────────────────────────────────────────────────────


def _sources(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Candidate mappings in lookup-priority order.

    The harness passes the per-run *artifact* dict, which nests the remote
    result under ``result`` and the computed timing under ``timing``.  Those
    are appended as fallback sources so lookups also succeed against the raw
    remote result payload.
    """
    out: list[Mapping[str, Any]] = []
    if isinstance(result, Mapping):
        out.append(result)
        nested = result.get("result")
        if isinstance(nested, Mapping):
            out.append(nested)
        timing = result.get("timing")
        if isinstance(timing, Mapping):
            out.append(timing)
    return out


def _first_value(
    result: Mapping[str, Any],
    keys: Sequence[str],
    *,
    skip_empty: bool = True,
) -> Any:
    """First non-None (optionally non-empty) value for any of *keys*."""
    for source in _sources(result):
        for key in keys:
            try:
                value = source.get(key)
            except Exception:  # noqa: BLE001 - defensive
                continue
            if value is None:
                continue
            if skip_empty and isinstance(value, str) and not value.strip():
                continue
            return value
    return None


def _first_mapping(
    result: Mapping[str, Any],
    keys: Sequence[str],
) -> Mapping[str, Any] | None:
    """First Mapping found for any of *keys* (any source level)."""
    for source in _sources(result):
        for key in keys:
            value = source.get(key)
            if isinstance(value, Mapping):
                return value
    return None


def _first_scalar(value: Any) -> Any:
    """Best-effort first scalar found inside *value* (list/dict unwrap)."""
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, (str, int, float)) and not isinstance(item, bool):
                return item
    if isinstance(value, Mapping):
        for key in ("image_id", "filename", "name", "path"):
            item = value.get(key)
            if isinstance(item, (str, int, float)) and not isinstance(item, bool):
                return item
    return None


def _trace_of(result: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the trace dict (nested-aware), or an empty mapping."""
    trace = result.get("trace")
    if not isinstance(trace, Mapping):
        nested = result.get("result")
        if isinstance(nested, Mapping):
            trace = nested.get("trace")
    return trace if isinstance(trace, Mapping) else {}


def _trace_events(result: Mapping[str, Any]) -> list[Any]:
    trace = _trace_of(result)
    events = trace.get("events", []) if isinstance(trace, Mapping) else []
    return events if isinstance(events, list) else []


_E31_FORWARD_EVENT_NAMES = frozenset({
    "clip_forward_evidence",
    "clip_forward_cast_summary",
    "clip_forward_start",
    "clip_forward_end",
    "clip_gpu_event_start",
    "clip_gpu_event_end",
    "clip_forward_gpu_ms",
})
_E31_PROOF_EVENT_NAMES = frozenset({
    "clip_fh_cast_once_bind_proof",
    "clip_fh_cast_once_forward_check",
    "clip_fh_cast_once_forward_failed",
    "clip_fh_cast_once_residency_failed",
    "clip_fh_cast_once_applied",
})


def _canonical_ledger(result: Mapping[str, Any]) -> Mapping[str, Any]:
    ledger = _first_mapping(result, ("canonical_ledger",))
    return ledger if isinstance(ledger, Mapping) else {}


def _e31_events(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return E31 events from both the trace and canonical ledger.

    Hydration diagnostics are intentionally not treated as forward evidence.
    In particular, a hydration ``conversion_count=0`` is not a forward
    conversion result; only the E31 forward event names below qualify.
    """
    events: list[Mapping[str, Any]] = []
    for event in _trace_events(result):
        if isinstance(event, Mapping):
            name = str(event.get("name", ""))
            if name in _E31_FORWARD_EVENT_NAMES or name in _E31_PROOF_EVENT_NAMES:
                events.append(event)
    for event in _canonical_ledger(result).get("events", []) or []:
        if isinstance(event, Mapping):
            name = str(event.get("name", ""))
            if name in _E31_FORWARD_EVENT_NAMES or name in _E31_PROOF_EVENT_NAMES:
                events.append(event)
    return events


def _e31_metadata(result: Mapping[str, Any], names: frozenset[str]) -> Mapping[str, Any] | None:
    """Return the latest metadata payload for the selected E31 events."""
    latest: Mapping[str, Any] | None = None
    for event in _e31_events(result):
        if str(event.get("name", "")) not in names:
            continue
        metadata = event.get("metadata")
        if isinstance(metadata, Mapping):
            latest = metadata
    return latest


def _collect_e31_evidence(result: Mapping[str, Any]) -> dict[str, Any]:
    """Collect explicit forward/proof evidence without inferring from hydration."""
    # Prefer the complete evidence envelope over start/end timing markers.
    # The latter are useful ledger events but do not prove a forward ran.
    forward = _e31_metadata(result, frozenset({"clip_forward_evidence"}))
    if forward is None:
        forward = _e31_metadata(result, frozenset({"clip_forward_cast_summary"}))
    summary = _e31_metadata(result, frozenset({"clip_forward_cast_summary"}))
    if summary is None and isinstance(forward, Mapping):
        nested_summary = forward.get("forward_cast_summary")
        if isinstance(nested_summary, Mapping):
            summary = nested_summary
    residency = _e31_metadata(result, frozenset({"clip_fh_cast_once_bind_proof"}))
    forward_proof = _e31_metadata(result, frozenset({"clip_fh_cast_once_forward_check"}))
    failed = _e31_metadata(
        result,
        frozenset({"clip_fh_cast_once_forward_failed", "clip_fh_cast_once_residency_failed"}),
    )
    generation_proof: Mapping[str, Any] | None = None
    for source in (forward_proof, residency):
        if not isinstance(source, Mapping):
            continue
        generation_fields = {
            key: source[key]
            for key in (
                "generation", "bind_generation", "post_forward_generation",
                "generation_stable", "storage_stable",
            )
            if key in source
        }
        if generation_fields:
            generation_proof = generation_fields
            break
    observed = bool(forward) and any(
        key in forward for key in ("forward_observed", "forward_actually_observed", "forward_conversion_count")
    )
    return {
        "forward_evidence": forward,
        "forward_cast_summary": summary,
        "cast_once_residency_proof": residency,
        "cast_once_forward_proof": forward_proof,
        "cast_once_generation_proof": generation_proof,
        "cast_once_failure": failed,
        "forward_evidence_observed": observed,
    }


def _identity_of(result: Mapping[str, Any]) -> Mapping[str, Any]:
    """The run's identity dict (artifact-level or nested remote-level)."""
    identity = result.get("identity")
    if isinstance(identity, Mapping):
        return identity
    nested = result.get("result")
    if isinstance(nested, Mapping) and isinstance(nested.get("identity"), Mapping):
        return nested["identity"]
    return {}


def _is_partial_waterfall(value: Any) -> bool:
    return isinstance(value, Mapping) and value.get("partial_waterfall") is True


def _waterfall_differs(a: Any, b: Any) -> bool:
    """Structural inequality for two waterfall dicts.

    The volatile display ``run_label`` is ignored so that a local rebuild that
    only re-labels the same stages does not count as a different waterfall.
    """
    if not isinstance(a, Mapping) or not isinstance(b, Mapping):
        return a != b
    a_copy = {k: v for k, v in a.items() if k != "run_label"}
    b_copy = {k: v for k, v in b.items() if k != "run_label"}
    return a_copy != b_copy


def _resource_attr(result: Mapping[str, Any], name: str) -> str:
    """Best-effort cpu/ram scalar from ``resource_shape`` / ``resources``."""
    keys_by_attr = {
        "cpu": ("cpu", "cpu_request", "cpu_cores", "cpu_count", "n_cpu"),
        "ram": ("ram", "memory_request", "memory_mb", "ram_mb", "memory"),
    }
    for src_key in ("resource_shape", "resources"):
        shape = _first_mapping(result, (src_key,))
        if not isinstance(shape, Mapping):
            continue
        for key in keys_by_attr.get(name, ()):
            value = shape.get(key)
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                return str(value)
    return ""


def _collect_opt_diagnostics(result: Mapping[str, Any]) -> dict[str, Any]:
    """Merge every ``opt_*`` diagnostic payload into one flat dict.

    Sources, in order: trace-event metadata (event name starts with ``opt_``
    or any metadata key starts with ``opt_``), then top-level result keys
    starting with ``opt_`` / ``_opt_``.  First-seen values win so the result
    is deterministic.
    """
    merged: dict[str, Any] = {}
    for event in _trace_events(result):
        if not isinstance(event, Mapping):
            continue
        name = str(event.get("name", ""))
        meta = event.get("metadata")
        if not isinstance(meta, Mapping):
            continue
        if name.startswith("opt_") or any(
            isinstance(k, str) and k.startswith("opt_") for k in meta.keys()
        ):
            for key, value in meta.items():
                merged.setdefault(str(key), value)
    for source in _sources(result):
        for key, value in source.items():
            if isinstance(key, str) and (key.startswith("opt_") or key.startswith("_opt_")):
                merged.setdefault(key, value)
    return merged


def _collect_experiment_settings(result: Mapping[str, Any]) -> dict[str, Any]:
    """Effective experiment settings + scraped ``experiment_selection`` events.

    Base settings come from ``experiment_settings`` (or ``experiment_selection``)
    on the result, falling back to ``{}``.  Additionally, every trace event
    named ``experiment_selection`` contributes its metadata dict to the
    ``experiment_selection_events`` list.
    """
    settings: dict[str, Any] = {}
    base = _first_value(
        result, ("experiment_settings", "experiment_selection"), skip_empty=False,
    )
    if isinstance(base, Mapping):
        settings = dict(base)
    elif isinstance(base, list):
        settings = {"experiment_selection_events": list(base)}

    event_meta: list[Any] = []
    for event in _trace_events(result):
        if not isinstance(event, Mapping):
            continue
        if event.get("name") != "experiment_selection":
            continue
        meta = event.get("metadata")
        if isinstance(meta, Mapping):
            event_meta.append(_json_safe(meta))
    if event_meta:
        existing = settings.get("experiment_selection_events")
        if isinstance(existing, list):
            settings["experiment_selection_events"] = list(existing) + event_meta
        else:
            settings["experiment_selection_events"] = event_meta
    return settings


def build_run_record(
    result: Mapping[str, Any],
    *,
    request_id: str = "",
    experiment: str = "",
    arm: str = "",
    run_ordinal: int = 1,
    run_role: str = "sample",
    retained: bool = True,
    discard_reason: str = "",
    v2ctl_invocation_id: str = "",
    profile: str = "",
    profile_config_fingerprint: str = "",
    deploy_fingerprint: str = "",
    run_fingerprint: str = "",
    generated_at_utc: str = "",
) -> dict[str, Any]:
    """Assemble one flat, deterministic experiment-run record.

    Every field is extracted defensively (missing values become ``None`` or
    ``""``); no lookup raises.  The returned dict is JSON-safe (see
    ``_json_safe``).
    """
    # Waterfall selection (used for both the persisted values and the
    # per-field timing lookups below).
    waterfall_local = result.get("waterfall_local")
    waterfall_remote = result.get("waterfall")
    if not isinstance(waterfall_local, Mapping):
        waterfall_local = None
    if not isinstance(waterfall_remote, Mapping):
        waterfall_remote = None

    final_reconciled = waterfall_local
    if final_reconciled is None and waterfall_remote is not None:
        if not _is_partial_waterfall(waterfall_remote):
            final_reconciled = waterfall_remote

    remote_partial: Any = None
    if waterfall_remote is not None and (
        _is_partial_waterfall(waterfall_remote)
        or (
            waterfall_local is not None
            and _waterfall_differs(waterfall_remote, waterfall_local)
        )
    ):
        remote_partial = waterfall_remote

    identity = _identity_of(result)

    # image_id: best-effort first scalar from images/outputs/image_ids.
    image_id: Any = None
    for key in ("images", "outputs", "image_ids"):
        value = _first_value(result, (key,), skip_empty=False)
        scalar = _first_scalar(value)
        if scalar is not None:
            image_id = scalar
            break
    if image_id is None:
        image_id = ""

    snapshot_identity = _first_value(result, ("snapshot_identity",))
    if not snapshot_identity:
        parts = [
            str(identity.get("image_id") or "").strip(),
            str(identity.get("restore_session_id") or "").strip(),
        ]
        snapshot_identity = "|".join(p for p in parts if p)
    if not snapshot_identity:
        snapshot_identity = ""

    provider = str(identity.get("cloud") or identity.get("provider") or "").strip()
    region = str(identity.get("region") or "").strip()
    gpu = str(identity.get("gpu") or "").strip()
    if not provider:
        provider = str(_first_value(result, ("cloud", "provider")) or "").strip()
    if not region:
        region = str(_first_value(result, ("region",)) or "").strip()
    if not gpu:
        gpu = str(_first_value(result, ("gpu",)) or "").strip()

    # critical_path_metrics: scalar top-level keys matching the ms/latency regex.
    critical_path_metrics: dict[str, Any] = {}
    for source in _sources(result):
        for key, value in source.items():
            if not isinstance(key, str) or not _CRITICAL_PATH_RE.search(key):
                continue
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                continue
            critical_path_metrics.setdefault(key, value)

    timing_source = final_reconciled if isinstance(final_reconciled, Mapping) else {}

    # Reserved v2ctl metadata is read at write time as well as accepted by
    # callers.  This makes the durable record self-contained and keeps
    # non-v2ctl harnesses unchanged when the channel is absent.
    _v2ctl_id = str(v2ctl_invocation_id or _first_value(result, ("v2ctl_invocation_id",)) or os.environ.get("COMFYMODAL_V2CTL_INVOCATION_ID", "") or "")
    _profile = str(profile or _first_value(result, ("profile", "profile_name")) or os.environ.get("COMFYMODAL_V2CTL_PROFILE", "") or "")
    _profile_cfg = str(profile_config_fingerprint or _first_value(result, ("profile_config_fingerprint", "config_fingerprint")) or os.environ.get("COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT", "") or "")
    _deploy_fp = str(deploy_fingerprint or _first_value(result, ("deploy_fingerprint",)) or os.environ.get("COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT", "") or "")
    _run_fp = str(run_fingerprint or _first_value(result, ("run_fingerprint",)) or os.environ.get("COMFYMODAL_V2CTL_RUN_FINGERPRINT", "") or "")
    _request_id = str(request_id or _first_value(result, ("request_id", "prompt_id")) or "")
    _generated = str(generated_at_utc or _first_value(result, ("generated_at_utc", "run_timestamp")) or datetime.now(timezone.utc).isoformat())
    # E31 evidence is sourced only from explicit forward/proof events.  Do not
    # substitute hydration counters here: hydration conversion_count=0 says
    # nothing about whether the real CLIP forward converted weights.
    e31_evidence = _collect_e31_evidence(result)
    record: dict[str, Any] = {
        "request_id": _request_id,
        "experiment": str(experiment or ""),
        "arm": str(arm or ""),
        "run_ordinal": int(run_ordinal) if run_ordinal is not None else 1,
        "run_role": str(run_role or "sample"),
        "retained": bool(retained),
        "discard_reason": str(discard_reason or ""),
        "image_id": image_id,
        "snapshot_identity": snapshot_identity,
        "provider": provider,
        "region": region,
        "gpu": gpu,
        "cpu": _resource_attr(result, "cpu"),
        "ram": _resource_attr(result, "ram"),
        "full_trace": _trace_of(result) or None,
        "opt_diagnostics": _collect_opt_diagnostics(result),
        "final_reconciled_waterfall": final_reconciled,
        "remote_partial_waterfall": remote_partial,
        "effective_env": {
            k: v
            for k, v in os.environ.items()
            if k.startswith(_ENV_PREFIXES)
        },
        "effective_experiment_settings": _collect_experiment_settings(result),
        "output_descriptor": _first_value(
            result, ("descriptor", "asset_descriptors", "output_descriptor"),
        ),
        "output_sha": _first_value(
            result, ("output_sha", "content_sha256", "sha256"),
        ),
        "sampling_boundary_ms": _first_value(
            result, ("sampling_ms", "sampler_ms"),
        ),
        "critical_path_metrics": critical_path_metrics,
        "total_wall_ms": timing_source.get("total_wall_ms"),
        "scheduling_ms": timing_source.get("scheduling_ms"),
        "command_response_ms": timing_source.get("command_response_ms"),
        "wall_ms": _first_value(result, ("wall_ms",)),
        "generated_at_utc": _generated,
        "persisted_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_identity": dict(identity),
        "v2ctl_invocation_id": _v2ctl_id,
        "profile": _profile,
        "profile_name": _profile,
        "profile_config_fingerprint": _profile_cfg,
        "deploy_fingerprint": _deploy_fp,
        "run_fingerprint": _run_fp,
        "e31_forward_evidence": e31_evidence["forward_evidence"],
        "e31_forward_cast_summary": e31_evidence["forward_cast_summary"],
        "e31_cast_once_residency_proof": e31_evidence["cast_once_residency_proof"],
        "e31_cast_once_forward_proof": e31_evidence["cast_once_forward_proof"],
        "e31_cast_once_generation_proof": e31_evidence["cast_once_generation_proof"],
        "e31_cast_once_failure": e31_evidence["cast_once_failure"],
        "e31_forward_evidence_observed": e31_evidence["forward_evidence_observed"],
        # ── E29: canonical critical-path ledger (ground truth) ───────────
        # The remote result attaches the full canonical ledger report; carry
        # it verbatim (plus its status) into the persisted sample record so
        # the gate validator reads the SAME structure the remote emitted.
        "canonical_ledger": _first_value(
            result, ("canonical_ledger",),
        ),
        "canonical_ledger_status": _first_value(
            result, ("canonical_ledger_status",),
        ),
        "canonical_ledger_error": _first_value(
            result, ("canonical_ledger_error",),
        ),
    }
    return _json_safe(record)  # type: ignore[return-value]


# ────────────────────────────────────────────────────────────────────────────
# Persistence
# ────────────────────────────────────────────────────────────────────────────


def save_experiment_run(
    record: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> Path:
    """Write ``<output_dir>/run_<run_ordinal:03d>_<run_role>.json``.

    Deterministic: sorted keys, fixed indentation.  Returns the written path.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    run_ordinal = int(record.get("run_ordinal") or 1)
    run_role = str(record.get("run_role") or "sample") or "sample"
    role_clean = _RUN_FILENAME_RE.sub("_", run_role) or "sample"
    path = out / f"run_{run_ordinal:03d}_{role_clean}.json"

    # The path is part of the canonical artifact identity.  Add it only after
    # the final filename is known; an artifact hash, if needed, belongs in the
    # provenance sidecar because embedding a hash of these bytes would be
    # self-referential.  Discard a caller-supplied embedded hash rather than
    # persisting misleading integrity metadata.
    canonical_record = dict(record)
    canonical_record.pop("artifact_sha256", None)
    canonical_record["artifact_path"] = str(path.resolve())
    path.write_text(_dumps(canonical_record), encoding="utf-8")
    return path


def _record_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    """Compact per-record manifest summary (scalars only)."""
    keys = (
        "request_id",
        "experiment",
        "arm",
        "run_ordinal",
        "run_role",
        "retained",
        "discard_reason",
        "image_id",
        "snapshot_identity",
        "provider",
        "region",
        "gpu",
        "cpu",
        "ram",
        "sampling_boundary_ms",
        "wall_ms",
        "total_wall_ms",
        "scheduling_ms",
        "command_response_ms",
        "output_sha",
        "persisted_at_utc",
        "generated_at_utc",
        "v2ctl_invocation_id",
        "profile",
        "profile_config_fingerprint",
        "deploy_fingerprint",
        "run_fingerprint",
    )
    summary = {key: _json_safe(record.get(key)) for key in keys}
    run_ordinal = int(record.get("run_ordinal") or 1)
    run_role = str(record.get("run_role") or "sample") or "sample"
    summary["record_file"] = f"run_{run_ordinal:03d}_{run_role}.json"
    return summary


def write_campaign_manifest(
    records: Sequence[Mapping[str, Any]],
    *,
    output_dir: str | Path,
) -> Path:
    """Write ``<output_dir>/campaign_manifest.json`` for the campaign.

    Deterministic ordering (records kept in the given order, which is the
    run order).  Returns the written path.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "campaign_timestamp": datetime.now(timezone.utc).isoformat(),
        "generations_total": len(records),
        "retained": sum(
            1 for record in records if record.get("retained") is True
        ),
        "discarded": sum(
            1 for record in records if record.get("retained") is not True
        ),
        "records": [_record_summary(record) for record in records],
        "record_files": [
            f"run_{int(record.get('run_ordinal') or 1):03d}_"
            f"{str(record.get('run_role') or 'sample')}.json"
            for record in records
        ],
    }
    # Additive campaign-level identity summary.  Do not invent provenance for
    # legacy campaigns; an empty/mixed set is explicitly represented.
    invocation_ids = sorted({str(r.get("v2ctl_invocation_id") or "") for r in records if r.get("v2ctl_invocation_id")})
    profiles = sorted({str(r.get("profile") or r.get("profile_name") or "") for r in records if r.get("profile") or r.get("profile_name")})
    profile_fps = sorted({str(r.get("profile_config_fingerprint") or "") for r in records if r.get("profile_config_fingerprint")})
    if invocation_ids:
        manifest["v2ctl_invocation_id"] = invocation_ids[0] if len(invocation_ids) == 1 else None
        manifest["v2ctl_invocation_ids"] = invocation_ids
        manifest["profile"] = profiles[0] if len(profiles) == 1 else None
        manifest["profile_config_fingerprint"] = profile_fps[0] if len(profile_fps) == 1 else None
    path = out / "campaign_manifest.json"
    path.write_text(_dumps(manifest), encoding="utf-8")
    return path
