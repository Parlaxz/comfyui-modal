"""
diagnosis_collector — Section-14/15 tooling for V1/V2 container performance diagnosis.

No production execution path is modified.  This module wraps existing benchmark
artifacts (``summary.json`` with embedded traces) under the convention defined
by ``local_artifacts.get_benchmark_runs_dir()``.

Usage (local-only, no Modal launch)::

    python -c "
    from diagnosis_collector import collect_diagnosis
    collect_diagnosis(
        runs=[
            (\"C:/path/to/benchmark/run_1/summary.json\", \"V1\"),
            (\"C:/path/to/benchmark/run_2/summary.json\", \"V2\"),
        ],
        label=\"2026-07-18-initial-diagnosis\",
    )
    "

Dashboard/OTel correlation (optional CSV)::

    # CSV columns: modal_input_id,input_created_to_scheduled_ms,scheduled_to_execution_ms,execution_ms
    python -c "
    from diagnosis_collector import collect_diagnosis
    collect_diagnosis(
        runs=[
            (\"C:/path/to/benchmark/run_1/summary.json\", \"V1\"),
            (\"C:/path/to/benchmark/run_2/summary.json\", \"V2\"),
        ],
        label=\"2026-07-18-correlated\",
        dashboard_csv=\"C:/path/to/dashboard_timing.csv\",
    )
    "

The CSV is keyed by ``modal_input_id``.  Every snapshot that carries a
``modal_input_id`` must match exactly one row; unmatched or duplicate
IDs are reported as errors rather than silently guessed.

Output layout under ``<benchmark-runs>/diagnosis/<label>/``::

    diagnosis/
      <label>/
        diagnosis.json          # metadata + Section-14 run entries
        comparison.json         # Section-15 comparison table
        runs/
          <run_id>.json         # one Section-14 snapshot per run
"""

from __future__ import annotations

import copy
import csv
import json
import os
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Section-14 field names (all nullable) ──────────────────────────────────

SECTION_14_SCHEMA = [
    "run_id",
    "variant",
    "request_id",
    "trace_id",
    "modal_input_id",
    "container_task_id",
    "image_id",
    "resource_identity",
    "workflow_hash",
    "effective_options_hash",
    "local_wall_clock_ms",
    "publisher_ms",
    "gpu_submit_to_first_event_ms",
    "dashboard_input_to_scheduled_ms",
    "dashboard_scheduled_to_execution_ms",
    "dashboard_execution_ms",
    "lifecycle_breakdown",
    "preload_breakdown",
    "execution_breakdown",
    "output_breakdown",
    "trace",
    "status",
    "errors",
    "validation_errors",
]

# ── Section-15 comparison rows ─────────────────────────────────────────────

SECTION_15_ROWS = [
    "total_user_facing_wall_clock_ms",
    "restore_plan_profile_publication_ms",
    "gpu_submit_to_first_event_ms",
    "modal_input_queue_ms",
    "scheduled_to_execution_ms",
    "lifecycle_total_ms",
    "volume_reloads_ms",
    "cuda_sage_setup_ms",
    "unet_clip_preload_work_ms",
    "unet_clip_graph_wait_ms",
    "loader_misses_fallbacks",
    "validation_preflight_ms",
    "prompt_executor_ms",
    "sampler_ms",
    "vae_ms",
    "output_collection_conversion_ms",
    "local_materialization_ms",
]

SECTION_15_INTERPRETATION_NOTE = (
    "interpretation: Application-derived fields (gpu_submit_to_first_event_ms, "
    "publisher_ms, sampler_ms, vae_ms, local_materialization_ms) are computed "
    "from application-level trace events. Dashboard-only fields "
    "(modal_input_queue_ms, scheduled_to_execution_ms, "
    "lifecycle_total_ms, volume_reloads_ms, cuda_sage_setup_ms) are NULL "
    "unless manually entered after dashboard correlation. Computed fields "
    "(lifecycle_total_ms, prompt_executor_ms, unet_clip_preload_work_ms, "
    "unet_clip_graph_wait_ms, validation_preflight_ms, "
    "output_collection_conversion_ms, loader_misses_fallbacks) are derived "
    "from nested breakdown dicts. Each row includes a \"source\" annotation "
    "(application_derived | dashboard_only | computed | direct) so the "
    "data provenance is explicit. Do not assign queue time to application "
    "code without correlated evidence. Do not call an isolated phase "
    "improvement a win if total wall time regresses. Separate facts from "
    "hypotheses. Preserve V1/V2 raw measurements beside medians."
)

# ── Helpers ────────────────────────────────────────────────────────────────


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_float(val, default=None) -> Optional[float]:
    if val is None:
        return default
    try:
        v = float(val)
        return v
    except (TypeError, ValueError):
        return default


def _safe_int(val, default=None) -> Optional[int]:
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _nested_get(d, *keys):
    """Get a value from nested dicts, returning None if any key is missing."""
    for key in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(key)
    return d


def _median(values: list[Optional[float]]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(statistics.median(clean), 2)


def _fmt_ms(v: Optional[float]) -> str:
    if v is None:
        return "NULL"
    return f"{v:.2f}"


_AMBIGUOUS_VALUES: frozenset = frozenset({"", "auto", "default", "unknown", "none", "null"})


def _is_ambiguous(val) -> bool:
    """Return True if *val* is an ambiguous placeholder for gpu/cloud/region."""
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip().lower() in _AMBIGUOUS_VALUES
    return False


# ── modal_input_id extraction ─────────────────────────────────────────────


def _extract_modal_input_id(
    trace: dict,
    v1_id: dict,
    meta: dict,
    restore: dict,
) -> Optional[str]:
    """Extract ``modal_input_id`` from trace data without inventing IDs.

    Checks (in order):
    1. Top-level trace key ``modal_input_id``
    2. ``trace.metadata`` sub-dict (V2 RuntimeTrace pattern)
    3. Explicit *meta* parameter (already-extracted metadata)
    4. ``v1_identity`` sub-dict (keys ``modal_input_id`` / ``input_id``)
    5. ``restore`` sub-dict (keys ``modal_input_id`` / ``input_id``)
    6. ``trace.events`` — iterates event metadata for ``modal_input_id`` / ``input_id``
    """
    # 1. Top-level trace
    val = trace.get("modal_input_id")
    if val:
        return str(val)

    # 2. trace.metadata sub-dict (V2 RuntimeTrace hoist target)
    trace_meta = trace.get("metadata", {})
    if isinstance(trace_meta, dict):
        val = trace_meta.get("modal_input_id") or trace_meta.get("input_id")
        if val:
            return str(val)

    # 3. Explicit meta parameter (already extracted in extract_section14_run)
    val = meta.get("modal_input_id") or meta.get("input_id")
    if val:
        return str(val)

    # 4. v1_identity sub-dict
    val = v1_id.get("modal_input_id") or v1_id.get("input_id")
    if val:
        return str(val)

    # 5. restore sub-dict
    val = restore.get("modal_input_id") or restore.get("input_id")
    if val:
        return str(val)

    # 6. RuntimeTrace events — check each event's metadata
    events = trace.get("events")
    if isinstance(events, list):
        for event in events:
            if not isinstance(event, dict):
                continue
            ev_meta = event.get("metadata", {})
            if not isinstance(ev_meta, dict):
                continue
            val = ev_meta.get("modal_input_id") or ev_meta.get("input_id")
            if val:
                return str(val)

    return None


# ── Dashboard CSV parser ──────────────────────────────────────────────────


def _parse_dashboard_csv(csv_path: str) -> Dict[str, Dict[str, Optional[float]]]:
    """Parse dashboard/OTel correlation CSV.

    Expected columns:
        ``modal_input_id``, ``input_created_to_scheduled_ms``,
        ``scheduled_to_execution_ms``, ``execution_ms``

    Returns a dict keyed by ``modal_input_id`` with sub-dicts containing
    the three timing fields.

    Raises
    ------
    ValueError
        If required columns are missing or duplicate ``modal_input_id``
        values are found.
    """
    result: dict[str, dict[str, Optional[float]]] = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV file is empty or has no header row")
        required = {
            "modal_input_id",
            "input_created_to_scheduled_ms",
            "scheduled_to_execution_ms",
            "execution_ms",
        }
        if not required.issubset(reader.fieldnames):
            missing = required - set(reader.fieldnames)
            raise ValueError(
                f"Dashboard CSV missing required columns: {missing}. "
                f"Got: {set(reader.fieldnames)}"
            )
        for row_num, row in enumerate(reader, start=2):
            mid = (row.get("modal_input_id") or "").strip()
            if not mid:
                continue  # skip blank rows
            if mid in result:
                raise ValueError(
                    f"Duplicate modal_input_id in dashboard CSV at row {row_num}: {mid!r}"
                )
            result[mid] = {
                "input_created_to_scheduled_ms": _safe_float(
                    row.get("input_created_to_scheduled_ms")
                ),
                "scheduled_to_execution_ms": _safe_float(
                    row.get("scheduled_to_execution_ms")
                ),
                "execution_ms": _safe_float(row.get("execution_ms")),
            }
    return result


def _merge_dashboard_data(
    snapshot: dict,
    dashboard_data: Dict[str, Dict[str, Optional[float]]],
) -> Optional[str]:
    """Merge dashboard timing into *snapshot* by matching ``modal_input_id``.

    If *snapshot* has a ``modal_input_id`` that exists in *dashboard_data*,
    the three dashboard timing fields are populated.  Returns ``None`` on
    success, or an error string if the snapshot has an ID but no match.
    """
    mid = snapshot.get("modal_input_id")
    if not mid:
        return None  # nothing to match — not an error
    if mid in dashboard_data:
        d = dashboard_data[mid]
        snapshot["dashboard_input_to_scheduled_ms"] = d["input_created_to_scheduled_ms"]
        snapshot["dashboard_scheduled_to_execution_ms"] = d["scheduled_to_execution_ms"]
        snapshot["dashboard_execution_ms"] = d["execution_ms"]
        return None
    return f"Snapshot {snapshot.get('run_id', '?')} has modal_input_id {mid!r} but no matching dashboard CSV row — unmatched correlation"


# ── Completed-run validation ──────────────────────────────────────────────


def _validate_completed_run(snapshot: dict) -> list[str]:
    """Validate a run snapshot has all fields required for comparison datasets.

    Returns a list of validation error messages (empty = valid for inclusion).
    """
    errors: list[str] = []
    if not snapshot.get("request_id") and not snapshot.get("trace_id"):
        errors.append("Missing both request_id and trace_id")
    if not snapshot.get("modal_input_id"):
        errors.append("Missing modal_input_id")
    if not snapshot.get("container_task_id"):
        errors.append("Missing container_task_id")
    if not snapshot.get("image_id"):
        errors.append("Missing image_id")
    rid = snapshot.get("resource_identity")
    if not isinstance(rid, dict):
        errors.append("Missing resource_identity dict")
    else:
        gpu_val = rid.get("gpu")
        cloud_val = rid.get("cloud")
        region_val = rid.get("region")
        if _is_ambiguous(gpu_val):
            errors.append(f"Ambiguous resource_identity.gpu: {gpu_val!r}")
        if _is_ambiguous(cloud_val):
            errors.append(f"Ambiguous resource_identity.cloud: {cloud_val!r}")
        if _is_ambiguous(region_val):
            errors.append(f"Ambiguous resource_identity.region: {region_val!r}")
    if not snapshot.get("workflow_hash"):
        errors.append("Missing workflow_hash")
    if not snapshot.get("effective_options_hash"):
        errors.append("Missing effective_options_hash")
    return errors


# ── Section-14 extractor ──────────────────────────────────────────────────


def extract_section14_run(
    summary: dict,
    which: str,  # "run1" or "run2"
    variant: str,  # "V1" or "V2"
    run_index: int,
) -> dict:
    """Build a Section-14-compliant snapshot from one run within a summary.json.

    Parameters
    ----------
    summary : dict
        Parsed ``summary.json`` from an existing benchmark run directory.
    which : str
        ``"run1"`` or ``"run2"`` — which trace slot to read.
    variant : str
        ``"V1"`` or ``"V2"`` — caller must supply this; it is not embedded
        in existing benchmark artifacts.
    run_index : int
        Sequential index assigned by the collector for stable ordering.

    Returns
    -------
    dict
        Section-14 snapshot.  Fields that cannot be extracted from legacy
        traces are set to ``None`` (nullable for manual dashboard correlation).
    """
    trace: dict = summary.get(f"{which}_trace", {})
    if not isinstance(trace, dict):
        trace = {}

    deltas: dict = trace.get("deltas_ms", {}) if isinstance(trace.get("deltas_ms"), dict) else {}
    stages: dict = trace.get("stages", {}) if isinstance(trace.get("stages"), dict) else {}
    derived: dict = trace.get("derived_ms", {}) if isinstance(trace.get("derived_ms"), dict) else {}
    restore: dict = trace.get("restore", {}) if isinstance(trace.get("restore"), dict) else {}
    errors_raw = summary.get("error") or summary.get("errors") or trace.get("errors") or None

    run_id = f"run-{run_index:02d}-{variant}-{trace.get('prompt_id', uuid.uuid4().hex[:12])}"

    # ── Wall clock ────────────────────────────────────────────────────
    local_wall_ms = _safe_float(summary.get(f"{which}_total_ms"))
    if local_wall_ms is None:
        # Derive from stages if possible
        t0 = stages.get("t0_client_press")
        t10 = stages.get("t10_local_materialized")
        if t0 is not None and t10 is not None:
            local_wall_ms = round((t10 - t0) * 1000, 2)
        else:
            local_wall_ms = _safe_float(deltas.get("modal_to_browser"))

    # ── Phase durations from available data ───────────────────────────
    # publisher_ms: ONLY from dedicated RestorePlan/profile publication
    # evidence.  NEVER fall back to local_dispatch_to_modal_entry_ms,
    # modal_call_submit_ms, or t2_to_t3 because those conflate submission
    # or queue time.
    publisher_ms = None
    # 1. Explicit dedicated duration field
    pub_dur = _safe_float(
        derived.get("restore_publication_ms")
        or derived.get("profile_publication_ms")
    )
    if pub_dur is not None:
        publisher_ms = pub_dur
    # 2. RuntimeTrace event pair restore_publish_start/end with monotonic_ns
    if publisher_ms is None:
        events = trace.get("events")
        if isinstance(events, list):
            start_ns = None
            end_ns = None
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                ename = ev.get("name", "")
                mns = ev.get("monotonic_ns")
                if ename == "restore_publish_start" and mns is not None:
                    start_ns = int(mns)
                elif ename == "restore_publish_end" and mns is not None:
                    end_ns = int(mns)
            if start_ns is not None and end_ns is not None:
                publisher_ms = round((end_ns - start_ns) / 1_000_000, 2)
    # 3. V1 profile_publish_start/end in trace dict (wall-clock pair)
    if publisher_ms is None:
        pp_start = trace.get("profile_publish_start")
        pp_end = trace.get("profile_publish_end")
        if pp_start is not None and pp_end is not None:
            publisher_ms = round((pp_end - pp_start) * 1000, 2)

    # gpu_submit_to_first_event = modal entry → prompt start
    gpu_to_first = _safe_float(
        derived.get("modal_entry_to_prompt_start_ms")
        or derived.get("submit2entry_ms")
        or deltas.get("t2_to_t3")  # legacy approximation
    )

    # ── Execution breakdown ───────────────────────────────────────────
    execution_breakdown = {
        "prompt_start_to_sampler_start_ms": _safe_float(
            derived.get("prompt_start_to_sampler_start_ms")
            or derived.get("pre_sampler_ms")
        ),
        "sampler_ms": _safe_float(
            derived.get("sampler_ms")
            or deltas.get("sampler")
        ),
        "sampler_end_to_outputs_collected_ms": _safe_float(
            derived.get("sampler_end_to_outputs_collected_ms")
            or derived.get("post_sampler_ms")
        ),
        "vae_decode_ms": _safe_float(
            derived.get("vae_decode_ms")
            or deltas.get("vae_decode")
        ),
        "output_collection_total_ms": _safe_float(
            derived.get("output_collection_total_ms")
            or deltas.get("t8b_to_t9")
        ),
        "clip_encode_ms": _safe_float(
            derived.get("clip_encode_ms")
            or deltas.get("clip_encode")
        ),
        "clip_load_ms": _safe_float(derived.get("clip_load_ms")),
        "unet_node_wait_ms": _safe_float(derived.get("unet_node_wait_ms")),
        "vae_node_wait_ms": _safe_float(derived.get("vae_node_wait_ms")),
    }

    # ── Lifecycle breakdown (from restore timing if available) ────────
    lifecycle_breakdown = {}
    restore_total = _safe_float(
        restore.get("restore_total_ms")
        or derived.get("restore_total_ms")
    )
    if isinstance(restore, dict):
        for k, v in restore.items():
            if isinstance(v, (int, float)) and k not in ("restore_total_ms",):
                lifecycle_breakdown[k] = v
    if restore_total is not None:
        lifecycle_breakdown["restore_total_ms"] = restore_total
    if not lifecycle_breakdown:
        lifecycle_breakdown = None

    # ── Preload breakdown ──────────────────────────────────────────────
    preload_keys = [
        "preload_mode", "preload_skipped", "preload_skip_reason",
        "warmup_preload_ms", "warmup_direct_total_ms",
        "clip_cache_size_at_start", "clip_cache_size_after_warmup",
        "cold_unet_early_load_enabled", "cold_unet_early_load_mode",
        "cold_unet_graph_wait_ms",
    ]
    preload_breakdown = {}
    for k in preload_keys:
        v = restore.get(k) or trace.get(k)
        if v is not None:
            preload_breakdown[k] = v

    # ── Output breakdown ───────────────────────────────────────────────
    output_breakdown = {
        "output_collection_total_ms": execution_breakdown["output_collection_total_ms"],
        "t9_to_t10_ms": _safe_float(deltas.get("t9_to_t10")),
        "strategy": trace.get("result_route") or trace.get("direct_route_used"),
        "fallback_count": _safe_int(trace.get("direct_fallback_to_legacy")),
        "fallback_reason": trace.get("direct_fallback_reason"),
    }

    # ── Identity fields (with fallback to v1_identity / metadata) ───
    # When the legacy trace stores authoritative identity data in a nested
    # ``v1_identity`` sub-dict (V1 streaming path) or ``metadata`` sub-dict
    # (V2 RuntimeTrace pattern), fall back to those values.
    _v1_id: dict[str, Any] = trace.get("v1_identity", {})
    if not isinstance(_v1_id, dict):
        _v1_id = {}
    _meta: dict[str, Any] = trace.get("metadata", {})
    if not isinstance(_meta, dict):
        _meta = {}

    # ── Resource identity (with fallback to v1_identity / metadata) ───
    resource_identity = {
        "gpu": (
            restore.get("gpu") or trace.get("gpu")
            or _v1_id.get("gpu") or _meta.get("gpu")
            or None
        ),
        "cloud": (
            restore.get("cloud") or trace.get("cloud")
            or _v1_id.get("cloud") or _v1_id.get("cloud_provider")
            or _meta.get("cloud") or _meta.get("cloud_provider")
            or None
        ),
        "region": (
            restore.get("region") or trace.get("region")
            or _v1_id.get("region") or _meta.get("region")
            or None
        ),
        "cpu": (
            restore.get("cpu") or trace.get("cpu")
            or _v1_id.get("cpu") or _meta.get("cpu")
            or None
        ),
        "memory_mb": (
            restore.get("memory_mb") or trace.get("memory_mb")
            or _v1_id.get("memory_mb") or _meta.get("memory_mb")
            or None
        ),
        "snapshot_enabled": (
            restore.get("snapshot_enabled") or trace.get("snapshot_enabled")
            or _v1_id.get("snapshot_enabled") or _meta.get("snapshot_enabled")
            or None
        ),
        "gpu_snapshot_enabled": (
            restore.get("gpu_snapshot_enabled") or trace.get("gpu_snapshot_enabled")
            or _v1_id.get("gpu_snapshot_enabled") or _meta.get("gpu_snapshot_enabled")
            or None
        ),
        "restore_plan_generation": (
            restore.get("restore_plan_generation") or trace.get("restore_plan_generation")
            or _meta.get("restore_plan_generation")
            or None
        ),
        "app_name": (
            trace.get("app_name") or _v1_id.get("app_name") or _meta.get("app_name")
            or None
        ),
        "class_name": (
            trace.get("class_name") or _v1_id.get("class_name") or _meta.get("class_name")
            or None
        ),
        "target_inputs": (
            trace.get("target_inputs") or _v1_id.get("target_inputs") or _meta.get("target_inputs")
            or None
        ),
        "max_inputs": (
            trace.get("max_inputs") or _v1_id.get("max_inputs") or _meta.get("max_inputs")
            or None
        ),
        "models_volume": (
            trace.get("models_volume") or _v1_id.get("models_volume")
            or _meta.get("models_volume") or None
        ),
        "runtime_state_volume": (
            trace.get("runtime_state_volume") or _v1_id.get("runtime_state_volume")
            or _meta.get("runtime_state_volume") or None
        ),
        "custom_nodes_volume": (
            trace.get("custom_nodes_volume") or _v1_id.get("custom_nodes_volume")
            or _meta.get("custom_nodes_volume") or None
        ),
        "volume_mount_paths": (
            trace.get("volume_mount_paths") or _v1_id.get("volume_mount_paths")
            or _meta.get("volume_mount_paths") or None
        ),
    }

    # ── modal_input_id from trace / metadata / v1_identity / restore / events ─
    modal_input_id = _extract_modal_input_id(trace, _v1_id, _meta, restore)
    # Safety: never fabricate or default — if nothing is found this stays None.

    request_id = trace.get("prompt_id") or summary.get("prompt_id") or None
    trace_id = (
        trace.get("trace_id")
        or _v1_id.get("trace_id")
        or _nested_get(trace, "trace", "restore", "restore_session_id")
        or None
    )

    # workflow_hash: check trace, summary, v1_identity, metadata (in order)
    workflow_hash = (
        trace.get("workflow_hash")
        or summary.get("workflow_hash")
        or _v1_id.get("workflow_hash_prefix")
        or _meta.get("workflow_hash")
        or _meta.get("workflow_hash_prefix")
        or None
    )
    effective_options_hash = (
        trace.get("effective_options_hash")
        or trace.get("config_hash")
        or summary.get("config_hash")
        or _v1_id.get("effective_options_hash")
        or _meta.get("effective_options_hash")
        or None
    )

    # ── Status / errors ────────────────────────────────────────────────
    status = summary.get("status", "")
    if which == "run1":
        if status in ("run1_failed", "deploy_failed", "health_timeout", "snapshot_missing"):
            run_status = status
        elif status == "ok":
            run_status = "completed"
        else:
            run_status = status
    else:  # run2
        if status == "run2_failed":
            run_status = "failed"
        elif status == "ok":
            run_status = "completed"
        else:
            run_status = status or "completed"

    # Additional execution breakdown from newer derived fields
    for extra_key in ("total_input_execution_ms", "local_dispatch_to_modal_entry_ms",
                      "modal_call_submit_ms", "modal_queue_or_start_gap_ms",
                      "modal_return_to_local_receive_ms", "local_materialize_ms",
                      "local_save_ms", "local_response_send_ms",
                      "local_prepare_ms", "modal_handle_resolve_ms"):
        v = _safe_float(derived.get(extra_key))
        if v is not None:
            execution_breakdown[extra_key] = v

    # ── Validation for completed-run dataset inclusion ──────────────────
    # Every snapshot gets validated; only completed runs with empty
    # validation_errors are eligible for median computation.
    validation_errors = _validate_completed_run({
        "request_id": request_id,
        "trace_id": trace_id,
        "modal_input_id": modal_input_id,
        "container_task_id": (
            trace.get("container_task_id")
            or _nested_get(trace, "metadata", "container_task_id")
            or _v1_id.get("task_id")
            or _v1_id.get("container_task_id")
            or _meta.get("container_task_id")
            or restore.get("container_task_id")
            or None
        ),
        "image_id": (
            trace.get("image_id")
            or _v1_id.get("image_id")
            or _meta.get("image_id")
            or restore.get("image_id")
            or None
        ),
        "resource_identity": resource_identity,
        "workflow_hash": workflow_hash,
        "effective_options_hash": effective_options_hash,
    })

    snapshot = {
        "run_id": run_id,
        "variant": variant,
        "request_id": request_id,
        "trace_id": trace_id,
        "modal_input_id": modal_input_id,
        "container_task_id": (
            trace.get("container_task_id")
            or _nested_get(trace, "metadata", "container_task_id")
            or _v1_id.get("task_id")
            or _v1_id.get("container_task_id")
            or _meta.get("container_task_id")
            or restore.get("container_task_id")
            or None
        ),
        "image_id": (
            trace.get("image_id")
            or _v1_id.get("image_id")
            or _meta.get("image_id")
            or restore.get("image_id")
            or None
        ),
        "resource_identity": resource_identity,
        "workflow_hash": workflow_hash,
        "effective_options_hash": effective_options_hash,
        "local_wall_clock_ms": local_wall_ms,
        "publisher_ms": publisher_ms,
        "gpu_submit_to_first_event_ms": gpu_to_first,
        "dashboard_input_to_scheduled_ms": None,
        "dashboard_scheduled_to_execution_ms": None,
        "dashboard_execution_ms": None,
        "lifecycle_breakdown": lifecycle_breakdown if lifecycle_breakdown else None,
        "preload_breakdown": preload_breakdown if preload_breakdown else None,
        "execution_breakdown": execution_breakdown if any(v is not None for v in execution_breakdown.values()) else None,
        "output_breakdown": output_breakdown,
        "trace": trace,
        "status": run_status,
        "errors": errors_raw if run_status in ("failed", "run1_failed", "run2_failed") else None,
        "validation_errors": validation_errors if validation_errors else None,
    }

    # Ensure all Section-14 keys are present (nullable if missing)
    for key in SECTION_14_SCHEMA:
        if key not in snapshot:
            snapshot[key] = None

    return snapshot


# ── Section-15 comparison builder ──────────────────────────────────────────


def _is_valid_for_median(snap: dict) -> bool:
    """Return True if *snap* is eligible for median computation.

    Failed runs and runs with validation errors are excluded from medians but
    still retained in per-run overviews.
    """
    if snap.get("status") in ("failed", "run1_failed", "run2_failed"):
        return False
    ve = snap.get("validation_errors")
    if ve:
        return False
    return True


def build_comparison_table(
    v1_snapshots: list[dict],
    v2_snapshots: list[dict],
    diagnosis_label: str,
    dashboard_correlation_status: str = "none",
) -> dict:
    """Produce a Section-15 comparison table from lists of Section-14 snapshots.

    Parameters
    ----------
    v1_snapshots : list[dict]
        Section-14 run snapshots labeled ``"V1"``.
    v2_snapshots : list[dict]
        Section-14 run snapshots labeled ``"V2"``.
    diagnosis_label : str
        Human-readable label for the comparison set.
    dashboard_correlation_status : str
        ``"none"``, ``"partial"``, or ``"complete"``.

    Returns
    -------
    dict
        Comparison table with medians, individual values per row, and
        facts-only interpretation metadata.
    """
    generated_at = _timestamp()

    def _extract_value(snap: dict, field: str) -> Optional[float]:
        """Map Section-15 row names to fields inside a Section-14 snapshot."""
        mapping = {
            "total_user_facing_wall_clock_ms": "local_wall_clock_ms",
            "restore_plan_profile_publication_ms": "publisher_ms",
            "gpu_submit_to_first_event_ms": "gpu_submit_to_first_event_ms",
            "modal_input_queue_ms": "dashboard_input_to_scheduled_ms",
            "scheduled_to_execution_ms": "dashboard_scheduled_to_execution_ms",
            "lifecycle_total_ms": None,  # restore_total_ms inside lifecycle_breakdown
            "volume_reloads_ms": None,
            "cuda_sage_setup_ms": None,
            "unet_clip_preload_work_ms": None,
            "unet_clip_graph_wait_ms": None,
            "loader_misses_fallbacks": None,
            "validation_preflight_ms": None,
            "prompt_executor_ms": "total_input_execution_ms",
            "sampler_ms": "sampler_ms",
            "vae_ms": "vae_decode_ms",
            "output_collection_conversion_ms": "output_collection_total_ms",
            "local_materialization_ms": "local_materialize_ms",
        }

        # Special handling for nested fields
        if field == "lifecycle_total_ms":
            lb = snap.get("lifecycle_breakdown")
            if isinstance(lb, dict):
                return _safe_float(lb.get("restore_total_ms"))
            return None

        if field == "volume_reloads_ms":
            lb = snap.get("lifecycle_breakdown")
            if isinstance(lb, dict):
                return _safe_float(lb.get("volume_reload_ms") or lb.get("models_volume_reload_ms"))
            return None

        if field == "cuda_sage_setup_ms":
            lb = snap.get("lifecycle_breakdown")
            if isinstance(lb, dict):
                return _safe_float(lb.get("cuda_init_ms") or lb.get("sage_init_ms"))
            return None

        if field == "unet_clip_preload_work_ms":
            pb = snap.get("preload_breakdown")
            if isinstance(pb, dict):
                return _safe_float(pb.get("warmup_preload_ms") or pb.get("warmup_direct_total_ms"))
            return None

        if field == "unet_clip_graph_wait_ms":
            eb = snap.get("execution_breakdown")
            if isinstance(eb, dict):
                return _safe_float(eb.get("unet_node_wait_ms"))
            return None

        if field == "loader_misses_fallbacks":
            # This is a count, stored as int.  Return as float for uniformity.
            eb = snap.get("execution_breakdown")
            if isinstance(eb, dict):
                misses = eb.get("loader_misses") or eb.get("fallback_count")
                return _safe_float(misses)
            return None

        if field == "validation_preflight_ms":
            eb = snap.get("execution_breakdown")
            if isinstance(eb, dict):
                return _safe_float(eb.get("prompt_start_to_sampler_start_ms"))
            return None

        if field == "prompt_executor_ms":
            eb = snap.get("execution_breakdown")
            if isinstance(eb, dict):
                return _safe_float(eb.get("total_input_execution_ms"))
            return None

        if field == "sampler_ms":
            eb = snap.get("execution_breakdown")
            if isinstance(eb, dict):
                return _safe_float(eb.get("sampler_ms"))
            return None

        if field == "vae_ms":
            eb = snap.get("execution_breakdown")
            if isinstance(eb, dict):
                return _safe_float(eb.get("vae_decode_ms"))
            return None

        if field == "output_collection_conversion_ms":
            eb = snap.get("execution_breakdown")
            if isinstance(eb, dict):
                return _safe_float(eb.get("output_collection_total_ms"))
            return None

        if field == "local_materialization_ms":
            eb = snap.get("execution_breakdown")
            if isinstance(eb, dict):
                return _safe_float(eb.get("local_materialize_ms"))
            return None

        # Simple direct field lookups
        direct_key = mapping.get(field)
        if direct_key:
            return _safe_float(snap.get(direct_key))

        return None

    # ── Per-field source provenance ────────────────────────────────────
    # Explicitly classifies each Section-15 row so consumers can clearly
    # distinguish application-derived fields from dashboard-only fields
    # without inspecting raw trace values.
    _FIELD_SOURCES: dict[str, str] = {
        "total_user_facing_wall_clock_ms": "application_derived",
        "restore_plan_profile_publication_ms": "application_derived",
        "gpu_submit_to_first_event_ms": "application_derived",
        "modal_input_queue_ms": "dashboard_only",
        "scheduled_to_execution_ms": "dashboard_only",
        "lifecycle_total_ms": "computed",        # from lifecycle_breakdown
        "volume_reloads_ms": "computed",          # from lifecycle_breakdown
        "cuda_sage_setup_ms": "computed",         # from lifecycle_breakdown
        "unet_clip_preload_work_ms": "computed",  # from preload_breakdown
        "unet_clip_graph_wait_ms": "computed",    # from execution_breakdown
        "loader_misses_fallbacks": "computed",    # from execution_breakdown
        "validation_preflight_ms": "computed",    # from execution_breakdown
        "prompt_executor_ms": "computed",         # from execution_breakdown
        "sampler_ms": "application_derived",
        "vae_ms": "application_derived",
        "output_collection_conversion_ms": "computed",  # from execution_breakdown
        "local_materialization_ms": "application_derived",
    }

    # Filter out failed / invalid runs before computing medians
    v1_valid = [s for s in v1_snapshots if _is_valid_for_median(s)]
    v2_valid = [s for s in v2_snapshots if _is_valid_for_median(s)]
    v1_excluded_count = len(v1_snapshots) - len(v1_valid)
    v2_excluded_count = len(v2_snapshots) - len(v2_valid)

    rows = {}
    for field in SECTION_15_ROWS:
        v1_values = [_extract_value(s, field) for s in v1_valid]
        v2_values = [_extract_value(s, field) for s in v2_valid]

        v1_median = _median(v1_values)
        v2_median = _median(v2_values)

        delta = None
        if v1_median is not None and v2_median is not None:
            delta = round(v2_median - v1_median, 2)

        rows[field] = {
            "v1_individual_ms": v1_values,
            "v1_median_ms": v1_median,
            "v2_individual_ms": v2_values,
            "v2_median_ms": v2_median,
            "delta_v2_minus_v1_ms": delta,
            "note": None,
            "source": _FIELD_SOURCES.get(field, "unknown"),
        }

        # Add facts-only notes for notable deltas
        if delta is not None and abs(delta) > 1000:
            if delta > 0:
                rows[field]["note"] = f"V2 higher by {delta:.0f}ms — investigate cause"
            else:
                rows[field]["note"] = f"V2 lower by {abs(delta):.0f}ms — confirm with repeated runs"

    # Build facts list depending on correlation state
    facts: list[str] = [
        "Facts are derived from available trace stages and deltas.",
    ]
    if dashboard_correlation_status == "complete":
        facts.append(
            "Dashboard correlation applied — queue timing from CSV input "
            "(input_created_to_scheduled_ms, scheduled_to_execution_ms, execution_ms)."
        )
    elif dashboard_correlation_status == "partial":
        facts.append(
            "Dashboard correlation partial — some completed runs have missing "
            "or unmatched modal_input_id or duplicate IDs."
        )
    else:
        facts.append(
            "Dashboard queue timestamps have not been manually correlated."
        )
    facts.append("No outlier has been discarded — all runs preserved.")
    if v1_excluded_count or v2_excluded_count:
        facts.append(
            f"{v1_excluded_count} V1 and {v2_excluded_count} V2 run(s) "
            f"excluded from medians (failed or incomplete identity data)."
        )
    facts.extend([
        "gpu_submit_to_first_event_ms is application-derived "
        "(from trace events), not a dashboard queue metric.",
        "Rows include a 'source' field classifying each metric as "
        "application_derived, dashboard_only, computed, or direct.",
    ])

    dashboard_correlated_bool = (dashboard_correlation_status == "complete")
    comparison = {
        "schema": "section_15_comparison_v1",
        "diagnosis_label": diagnosis_label,
        "generated_at": generated_at,
        "dashboard_correlation_status": dashboard_correlation_status,
        "dashboard_correlated": dashboard_correlated_bool,
        "v1_run_count": len(v1_snapshots),
        "v2_run_count": len(v2_snapshots),
        "v1_run_ids": [s.get("run_id") for s in v1_snapshots],
        "v2_run_ids": [s.get("run_id") for s in v2_snapshots],
        "v1_valid_count": len(v1_valid),
        "v2_valid_count": len(v2_valid),
        "rows": rows,
        "interpretation": SECTION_15_INTERPRETATION_NOTE,
        "facts": facts,
    }

    return comparison


# ── High-level collector ──────────────────────────────────────────────────


def collect_diagnosis(
    runs: List[Tuple[str, str]],
    label: Optional[str] = None,
    diagnosis_base_dir: Optional[Path] = None,
    dashboard_csv: Optional[str] = None,
) -> Path:
    """Collect Section-14 snapshots and produce a Section-15 comparison table.

    Parameters
    ----------
    runs : list of (str, str)
        Each element is ``(summary_json_path, variant)`` where *variant* is
        ``"V1"`` or ``"V2"``.
    label : str or None
        Short label for the diagnosis session (used as directory name).
        Defaults to a timestamp.
    diagnosis_base_dir : Path or None
        Root directory for diagnosis output.  Defaults to
        ``<benchmark-runs>/diagnosis/``.
    dashboard_csv : str or None
        Path to a CSV file with columns ``modal_input_id``,
        ``input_created_to_scheduled_ms``, ``scheduled_to_execution_ms``,
        ``execution_ms``.  When provided, matching snapshots have their
        dashboard-only fields populated.  Unmatched IDs or duplicates
        produce errors rather than silent guessing.

    Returns
    -------
    Path
        Path to the created diagnosis directory.
    """
    from local_artifacts import get_benchmark_runs_dir

    if label is None:
        label = _timestamp()

    base = (diagnosis_base_dir or (get_benchmark_runs_dir() / "diagnosis")).resolve()
    out_dir = _ensure_dir(base / label)
    runs_dir = _ensure_dir(out_dir / "runs")

    # ── Parse dashboard CSV if provided ────────────────────────────────
    dashboard_data: dict[str, dict[str, Optional[float]]] = {}
    if dashboard_csv:
        csv_path = Path(dashboard_csv)
        if not csv_path.is_file():
            raise FileNotFoundError(f"Dashboard CSV not found: {csv_path}")
        try:
            dashboard_data = _parse_dashboard_csv(str(csv_path))
        except (ValueError, OSError) as exc:
            raise ValueError(f"Failed to parse dashboard CSV {csv_path}: {exc}") from exc

    v1_snaps: list[dict] = []
    v2_snaps: list[dict] = []
    all_snaps: list[dict] = []
    errors: list[str] = []
    correlation_count = 0

    for idx, (summary_path_str, variant) in enumerate(runs):
        summary_path = Path(summary_path_str)
        if not summary_path.is_file():
            errors.append(f"[{idx}] summary not found: {summary_path}")
            continue
        try:
            summary = _read_json(summary_path)
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"[{idx}] read/parse error: {summary_path} — {exc}")
            continue

        # Extract run1 and run2 from each summary
        for which in ("run1", "run2"):
            trace = summary.get(f"{which}_trace")
            if not isinstance(trace, dict) or not trace:
                continue
            snap = extract_section14_run(summary, which, variant, len(all_snaps))

            # ── Merge dashboard correlation data ───────────────────────
            if dashboard_data:
                err = _merge_dashboard_data(snap, dashboard_data)
                if err:
                    errors.append(err)
                elif snap.get("modal_input_id") in dashboard_data:
                    correlation_count += 1

            snap_file = runs_dir / f"{snap['run_id']}.json"
            _write_json(snap_file, snap)
            all_snaps.append(snap)

            if variant.upper() == "V1":
                v1_snaps.append(snap)
            elif variant.upper() == "V2":
                v2_snaps.append(snap)

    # ── Post-processing: correlation integrity ──────────────────────────
    dashboard_correlation_status: str = "none"
    dashboard_correlated: bool = False
    if dashboard_data:
        # Track which CSV IDs were matched by a completed run
        used_csv_ids: set[str] = set()
        for snap in all_snaps:
            mid = snap.get("modal_input_id")
            if mid and mid in dashboard_data and _is_valid_for_median(snap):
                used_csv_ids.add(mid)

        # Detect duplicate modal_input_id across completed snapshots
        mid_to_snaps: dict[str, list[dict]] = {}
        for snap in all_snaps:
            if not _is_valid_for_median(snap):
                continue
            mid = snap.get("modal_input_id")
            if mid:
                mid_to_snaps.setdefault(mid, []).append(snap)
        dup_ids: set[str] = {mid for mid, snaps in mid_to_snaps.items() if len(snaps) > 1}

        for mid, snaps in mid_to_snaps.items():
            if len(snaps) > 1:
                msg = (
                    f"Duplicate modal_input_id {mid!r} across {len(snaps)} "
                    f"completed snapshots — all invalidated"
                )
                for snap in snaps:
                    ve_list = list(snap.get("validation_errors") or [])
                    ve_list.append(msg)
                    snap["validation_errors"] = ve_list
                errors.append(msg)

        # Check completed snapshots with missing or unmatched modal_input_id
        for snap in all_snaps:
            if not _is_valid_for_median(snap):
                continue
            mid = snap.get("modal_input_id")
            run_id = snap.get("run_id", "?")
            if not mid:
                msg = (
                    f"Completed snapshot {run_id} has no modal_input_id "
                    f"— cannot correlate"
                )
                ve_list = list(snap.get("validation_errors") or [])
                ve_list.append(msg)
                snap["validation_errors"] = ve_list
                errors.append(msg)
            elif mid not in dashboard_data:
                msg = (
                    f"Completed snapshot {run_id} has modal_input_id {mid!r} "
                    f"not found in dashboard CSV — unmatched correlation"
                )
                ve_list = list(snap.get("validation_errors") or [])
                ve_list.append(msg)
                snap["validation_errors"] = ve_list
                errors.append(msg)

        # Report unused CSV rows
        unused_ids = sorted(set(dashboard_data.keys()) - used_csv_ids)
        for uid in unused_ids:
            errors.append(
                f"Dashboard CSV row {uid!r} was not matched by any "
                f"completed-run snapshot"
            )

        # Re-write snapshots that had validation_errors updated
        for snap in all_snaps:
            snap_file = runs_dir / f"{snap['run_id']}.json"
            _write_json(snap_file, snap)

        # Determine correlation status
        completed_count = sum(1 for s in all_snaps if s.get("status") in ("completed",))
        valid_completed = sum(
            1 for s in all_snaps
            if s.get("status") in ("completed",) and not s.get("validation_errors")
        )
        if completed_count == 0:
            dashboard_correlation_status = "none"
        elif valid_completed == completed_count:
            dashboard_correlation_status = "complete"
        else:
            dashboard_correlation_status = "partial"
        dashboard_correlated = (dashboard_correlation_status == "complete")

    # Build comparison
    comparison = build_comparison_table(
        v1_snaps, v2_snaps, label,
        dashboard_correlation_status=dashboard_correlation_status,
    )
    _write_json(out_dir / "comparison.json", comparison)

    # Generate markdown summary
    _write_comparison_md(out_dir, comparison, v1_snaps, v2_snaps,
                         dashboard_correlation_status=dashboard_correlation_status)

    # Diagnosis index
    diagnosis_index = {
        "schema": "section_14_diagnosis_v1",
        "diagnosis_label": label,
        "generated_at": _timestamp(),
        "run_count": len(all_snaps),
        "v1_count": len(v1_snaps),
        "v2_count": len(v2_snaps),
        "dashboard_correlation_status": dashboard_correlation_status,
        "dashboard_correlated": dashboard_correlated,
        "correlation_count": correlation_count,
        "snapshots": [
            {
                "run_id": s["run_id"],
                "variant": s["variant"],
                "status": s["status"],
                "local_wall_clock_ms": s["local_wall_clock_ms"],
                "modal_input_id": s.get("modal_input_id"),
                "validation_errors": s.get("validation_errors"),
                "file": f"runs/{s['run_id']}.json",
            }
            for s in all_snaps
        ],
        "errors": errors if errors else None,
    }
    _write_json(out_dir / "diagnosis.json", diagnosis_index)

    return out_dir


# ── Comparison Markdown writer ────────────────────────────────────────────


def _write_comparison_md(
    out_dir: Path,
    comparison: dict,
    v1_snaps: list[dict],
    v2_snaps: list[dict],
    dashboard_correlation_status: str = "none",
) -> None:
    """Write a human-readable Section-15 comparison table as Markdown."""
    lines = [
        f"# V1/V2 Comparison — {comparison['diagnosis_label']}",
        "",
        f"Generated: {comparison['generated_at']}",
        f"V1 runs: {comparison['v1_run_count']}",
        f"V2 runs: {comparison['v2_run_count']}",
        f"Dashboard correlation: {dashboard_correlation_status}",
        "",
        "## Interpretation",
        "",
        comparison["interpretation"],
        "",
        "## Facts",
        "",
    ]
    for fact in comparison["facts"]:
        lines.append(f"- {fact}")

    lines.extend([
        "",
        "## Comparison Table (ms)",
        "",
        "| Metric | V1 Med | V2 Med | Δ (V2−V1) | V1 Values | V2 Values | Note |",
        "|--------|--------|--------|-----------|-----------|-----------|------|",
    ])

    for field in SECTION_15_ROWS:
        row = comparison["rows"].get(field, {})
        v1_med = _fmt_ms(row.get("v1_median_ms"))
        v2_med = _fmt_ms(row.get("v2_median_ms"))
        delta = row.get("delta_v2_minus_v1_ms")
        delta_str = _fmt_ms(delta)
        v1_vals = ", ".join(_fmt_ms(v) for v in row.get("v1_individual_ms", []))
        v2_vals = ", ".join(_fmt_ms(v) for v in row.get("v2_individual_ms", []))
        note = row.get("note") or ""
        lines.append(f"| {field} | {v1_med} | {v2_med} | {delta_str} | {v1_vals} | {v2_vals} | {note} |")

    lines.extend([
        "",
        "## Per-Run Overview",
        "",
        "| Run ID | Variant | Status | Wall Clock (ms) |",
        "|--------|---------|--------|-----------------|",
    ])

    for snap in v1_snaps + v2_snaps:
        run_id = snap.get("run_id", "?")
        variant = snap.get("variant", "?")
        status = snap.get("status", "?")
        wall = _fmt_ms(snap.get("local_wall_clock_ms"))
        lines.append(f"| {run_id} | {variant} | {status} | {wall} |")

    lines.append("")
    lines.append("## Dashboard / External Fields")
    lines.append("")
    if dashboard_correlation_status == "complete":
        lines.append(
            "Dashboard timing was successfully correlated via CSV "
            "(input_created_to_scheduled_ms, scheduled_to_execution_ms, execution_ms)."
        )
    elif dashboard_correlation_status == "partial":
        lines.append(
            "Dashboard correlation was attempted but some completed runs have "
            "missing or unmatched modal_input_id, or duplicate IDs."
        )
    else:
        lines.append(
            "The following fields require manual dashboard correlation and are NULL:"
        )
        lines.append("")
        manual_fields = [
            "modal_input_id",
            "dashboard_input_to_scheduled_ms",
            "dashboard_scheduled_to_execution_ms",
            "dashboard_execution_ms",
        ]
        for f in manual_fields:
            lines.append(f"- **{f}**")

    lines.append("")
    lines.append("## Validation & Excluded Runs")
    v1_valid_count = comparison.get("v1_valid_count", len(v1_snaps))
    v2_valid_count = comparison.get("v2_valid_count", len(v2_snaps))
    v1_excluded = len(v1_snaps) - v1_valid_count
    v2_excluded = len(v2_snaps) - v2_valid_count
    if v1_excluded or v2_excluded:
        lines.append(
            f"{v1_excluded} V1 and {v2_excluded} V2 run(s) excluded from medians "
            "(failed or incomplete identity data)."
        )
    else:
        lines.append("No runs were excluded from median computation.")
    failed_count = sum(1 for s in v1_snaps + v2_snaps if s.get("status") in ("failed", "run1_failed", "run2_failed"))
    lines.append(f"{failed_count} failed run(s) present in snapshots and retained.")

    (out_dir / "comparison.md").write_text("\n".join(lines), encoding="utf-8")


# ── CLI entry point ───────────────────────────────────────────────────────


def main(argv: Optional[list[str]] = None) -> int:
    """Minimal CLI for diagnosis_collector.

    Usage::

        python diagnosis_collector.py \\
            --label 2026-07-18-initial \\
            --variant V1 run1/summary.json run2/summary.json \\
            --variant V2 run3/summary.json run4/summary.json

    Optional dashboard correlation::

        python diagnosis_collector.py \\
            --label 2026-07-18-correlated \\
            --variant V1 run1/summary.json run2/summary.json \\
            --variant V2 run3/summary.json run4/summary.json \\
            --dashboard-csv ./dashboard_timing.csv

    Alternatively, use the Python API directly for programmatic access.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Diagnosis collector — Section-14/15 tooling (no Modal launch)"
    )
    parser.add_argument(
        "--label", default=None,
        help="Short label for the diagnosis session (default: timestamp)"
    )
    parser.add_argument(
        "--variant", action="append", nargs="+",
        metavar=("VARIANT", "SUMMARY_JSON"),
        help="One or more: VARIANT V1|V2 followed by summary.json paths"
    )
    parser.add_argument(
        "--out", default=None,
        help="Output base directory (default: <benchmark-runs>/diagnosis)"
    )
    parser.add_argument(
        "--dashboard-csv", default=None,
        help=(
            "Path to dashboard/OTel correlation CSV with columns: "
            "modal_input_id, input_created_to_scheduled_ms, "
            "scheduled_to_execution_ms, execution_ms"
        ),
    )

    args = parser.parse_args(argv)

    if not args.variant:
        parser.error("At least one --variant group is required")

    runs: list[Tuple[str, str]] = []
    for group in args.variant:
        if len(group) < 2:
            parser.error("Each --variant group needs at least VARIANT and one path")
        variant = group[0].upper()
        if variant not in ("V1", "V2"):
            parser.error(f"Variant must be V1 or V2, got {variant!r}")
        for path_str in group[1:]:
            runs.append((path_str, variant))

    out_base = Path(args.out).resolve() if args.out else None
    out_dir = collect_diagnosis(
        runs,
        label=args.label,
        diagnosis_base_dir=out_base,
        dashboard_csv=args.dashboard_csv,
    )
    print(f"Diagnosis written to: {out_dir}")
    print(f"  diagnosis.json    — index of all run snapshots")
    print(f"  comparison.json   — Section-15 comparison table (JSON)")
    print(f"  comparison.md     — Section-15 comparison table (Markdown)")
    print(f"  runs/             — individual Section-14 snapshots")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
