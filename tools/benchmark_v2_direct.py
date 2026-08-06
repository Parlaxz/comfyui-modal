from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_execution import build_execution_plan, execute_plan
from modal_client import check_active_warmup_profile, set_active_warmup_profile
from comfymodal_runtime.cpu_snapshot_models import diff_unet_runtime_states
from comfymodal_runtime.modal_transport import ModalTransport, HandleCache
from comfymodal_runtime.restore_plan import RemoteRestorePlanPublisher
from comfymodal_runtime.runtime_shape import runtime_shape_config
from comfymodal_runtime.trace import RuntimeTrace
from production_workflow import normalize_production_options
from tools.v2_waterfall import (
    build_waterfall,
    render_comparison,
    render_waterfall,
    waterfall_to_dict,
)
from tools.variance_report import (
    build_summary,
    build_matrix_summary,
    extract_run_metrics,
    load_runs_from_dir,
    render_variance_report,
    render_matrix_report,
    percentile,
    compute_stats,
    slow_run_rate,
    _num,
)


WORKFLOW_PATH = ROOT / "latest_benchmark_workflow.json"
WORKSPACES_PATH = ROOT / ".modal_workspaces.json"
APP_NAME = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow")
CLASS_NAME = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2")
GPU = os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000")
RUN_COUNT = int(os.environ.get("V2_BENCHMARK_RUNS", "1"))
GAP_SECONDS = float(os.environ.get("V2_BENCHMARK_GAP_SECONDS", "20"))
_ABSENT_STR = "absent"

# ── Variance-cold mode (opt-in, never the default) ────────────────────────
# Unique shadow app name used ONLY for variance mode.  Normal/production modes
# keep the default APP_NAME identity above; this default is overridable only
# by an explicit environment variable.
VARIANCE_APP_NAME = os.environ.get(
    "COMFYMODAL_V2_VARIANCE_APP_NAME", "stable-modal-comfy-v2-variance-shadow"
)
# Fixed one-request-at-a-time gap for true-cold scaledown between runs.
VARIANCE_COLD_GAP_SECONDS = float(
    os.environ.get("V2_VARIANCE_COLD_GAP_SECONDS", "25")
)
# Number of variance-cold runs (defaults to the shared run count).
VARIANCE_RUN_COUNT = int(os.environ.get("V2_VARIANCE_RUN_COUNT", "0")) or RUN_COUNT

# ── Variance-cold MATRIX (four-condition round-robin) ──────────────────────
# Conditions: (diagnostics, pretouch) for each of the four cells.
MATRIX_CONDITIONS: list[tuple[int, int]] = [(0, 0), (0, 1), (1, 0), (1, 1)]
# Continue attempts until >= this many valid cold runs per condition.
MATRIX_TARGET_COLD_PER_CONDITION = int(
    os.environ.get("V2_MATRIX_TARGET_PER_CONDITION", "6")
)
# Safety cap on total attempts across all conditions.
MATRIX_MAX_TOTAL_ATTEMPTS = int(os.environ.get("V2_MATRIX_MAX_TOTAL_ATTEMPTS", "200"))
# ONE explicit fixed slow threshold (ms) applied across ALL conditions.
# It is a NONZERO default (never derived from condition medians).  A cold
# request normally takes tens of seconds; 60s separates pathological outliers.
MATRIX_SLOW_THRESHOLD_MS = float(
    os.environ.get("V2_VARIANCE_SLOW_THRESHOLD_MS", "60000") or 60000
)
# Fixed slow classification flags (ms), independent of any threshold.
MATRIX_RESTORE_SLOW_MS = 3000.0
MATRIX_UNET_ACTIVATION_SLOW_MS = 3000.0
MATRIX_CONDITION_LABEL = lambda diag, pretouch: f"diag{int(diag)}_pt{int(pretouch)}"


def _load_workspace() -> dict[str, Any]:
    data = json.loads(WORKSPACES_PATH.read_text(encoding="utf-8"))
    active_id = data.get("active_workspace_id")
    for workspace in data.get("workspaces", []):
        if workspace.get("id") == active_id:
            if not workspace.get("token_id") or not workspace.get("token_secret"):
                raise RuntimeError("active Modal workspace has no credentials")
            os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
            os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])
            return workspace
    raise RuntimeError("active Modal workspace was not found")


def _load_workflow() -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    payload = snapshot.get("payload", snapshot)
    workflow = payload.get("prompt", payload)
    modal_options = payload.get("modal_options", {})
    if not isinstance(workflow, dict):
        raise RuntimeError("workflow prompt must be an object")
    if not isinstance(modal_options, dict):
        modal_options = {}
    return workflow, modal_options


def _identity(result: dict[str, Any]) -> dict[str, Any]:
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("name") != "remote_method_entry":
            continue
        metadata = event.get("metadata", {})
        if isinstance(metadata, dict) and metadata.get("method_name") == "run_plan_stream":
            return {
                "app_name": metadata.get("app_name", ""),
                "class_name": metadata.get("class_name", ""),
                "method_name": metadata.get("method_name", ""),
                "gpu": metadata.get("gpu", ""),
                "cpu": metadata.get("cpu"),
                "memory_mb": metadata.get("memory_mb"),
                "fingerprint": metadata.get("fingerprint", ""),
                "runtime_shape": metadata.get("runtime_shape", {}),
                "runtime_shape_fingerprint": metadata.get(
                    "runtime_shape_fingerprint", ""
                ),
                "runtime_shape_label": metadata.get("runtime_shape_label"),
                "stored_snapshot_model_order": metadata.get(
                    "stored_snapshot_model_order"
                ),
                # Preserve the request-scoped cold-proof fields emitted by
                # remote_method_entry.  The variance validator must inspect
                # these values rather than treating their absence as a warm
                # run after identity extraction.
                "restore_count": metadata.get("restore_count"),
                "request_count": metadata.get("request_count"),
                "restored_instance_id": metadata.get("restored_instance_id", ""),
                "restore_session_id": metadata.get("restore_session_id", ""),
                "container_task_id": metadata.get("container_task_id", ""),
                "modal_container_id": metadata.get("modal_container_id", ""),
                "image_id": metadata.get("image_id", ""),
                "cloud": metadata.get("cloud", ""),
                "region": metadata.get("region", ""),
                "modal_input_id": metadata.get("modal_input_id", ""),
                "container_session_id": (
                    metadata.get("container_session_id")
                    or result.get("container_session_id", "")
                    or trace.get("container_session_id", "")
                ),
            }
    metadata = trace.get("metadata", {}) if isinstance(trace, dict) else {}
    return dict(metadata) if isinstance(metadata, dict) else {}



def _runtime_shape_guard(shape: dict[str, Any]) -> dict[str, Any]:
    def _baseline_int(env_name: str, fallback: int) -> int:
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            return fallback
        try:
            value = int(raw)
        except ValueError as exc:
            raise RuntimeError(f"{env_name}={raw!r} is not an integer") from exc
        if value <= 0:
            raise RuntimeError(f"{env_name}={raw!r} must be positive")
        return value

    baseline_cpu = _baseline_int("COMFYMODAL_V2_BASELINE_CPU_REQUEST", 16)
    baseline_memory = _baseline_int(
        "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST",
        int(shape["memory_request"]),
    )
    changed_axes: list[str] = []
    if shape["thread_policy"] != "TBASE":
        changed_axes.append("thread_policy")
    if shape["snapshot_model_order"] != "O0":
        changed_axes.append("snapshot_model_order")
    if int(shape["cpu_request"]) != baseline_cpu:
        changed_axes.append("cpu_request")
    if int(shape["memory_request"]) != baseline_memory:
        changed_axes.append("memory_request")
    raw_override = os.environ.get("COMFYMODAL_V2_ALLOW_MULTI_AXIS", "").strip().lower()
    allow_multi_axis = raw_override in {"1", "true", "yes", "on"}
    guard = {
        "changed_axes": changed_axes,
        "allow_multi_axis": allow_multi_axis,
        "baseline_cpu_request": baseline_cpu,
        "baseline_memory_request": baseline_memory,
    }
    if len(changed_axes) > 1 and not allow_multi_axis:
        raise RuntimeError(
            "C8 experiment changes multiple axes without "
            "COMFYMODAL_V2_ALLOW_MULTI_AXIS=1: "
            + ", ".join(changed_axes)
        )
    return guard


def _runtime_shape_observations(result: dict[str, Any]) -> list[dict[str, Any]]:
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    if not isinstance(events, list):
        return []
    return [
        event.get("metadata", {})
        for event in events
        if isinstance(event, dict)
        and event.get("name") == "runtime_shape_observed"
        and isinstance(event.get("metadata"), dict)
    ]


def _validate_runtime_shape(
    result: dict[str, Any],
    identity: dict[str, Any],
) -> dict[str, Any]:
    expected = runtime_shape_config().identity_payload()
    guard = _runtime_shape_guard(expected)
    deployed = identity.get("runtime_shape")
    if not isinstance(deployed, dict):
        deployed = {}
    failures: list[str] = []
    for key in (
        "thread_policy",
        "snapshot_model_order",
        "cpu_request",
        "memory_request",
        "runtime_shape_fingerprint",
        "runtime_shape_label",
    ):
        if deployed.get(key) != expected.get(key):
            failures.append(
                f"deployed {key}={deployed.get(key)!r} "
                f"requested={expected.get(key)!r}"
            )
    if int(identity.get("cpu", -1) or -1) != int(expected["cpu_request"]):
        failures.append(
            f"resource cpu={identity.get('cpu')!r} requested={expected['cpu_request']!r}"
        )
    if int(identity.get("memory_mb", -1) or -1) != int(expected["memory_request"]):
        failures.append(
            "resource memory_mb="
            f"{identity.get('memory_mb')!r} requested={expected['memory_request']!r}"
        )
    if not identity.get("fingerprint"):
        failures.append("snapshot target fingerprint is missing")
    observations = _runtime_shape_observations(result)
    observed = observations[-1] if observations else {}
    if not observed:
        failures.append("runtime_shape_observed event is missing")
    elif observed.get("runtime_shape_fingerprint") != expected["runtime_shape_fingerprint"]:
        failures.append(
            "observed runtime_shape_fingerprint="
            f"{observed.get('runtime_shape_fingerprint')!r} "
            f"requested={expected['runtime_shape_fingerprint']!r}"
        )
    if expected["thread_policy"] == "TBASE":
        if observed.get("status") not in {"baseline_passthrough", "validated"}:
            failures.append(f"baseline thread status={observed.get('status')!r}")
    else:
        if observed.get("status") not in {"applied", "already_applied", "validated"}:
            failures.append(f"active thread status={observed.get('status')!r}")
        if observed.get("requested_vs_actual_match") is not True:
            failures.append("requested Torch thread counts do not match actual counts")
    stored_order = identity.get("stored_snapshot_model_order")
    if stored_order is None:
        trace = result.get("trace", {}) if isinstance(result, dict) else {}
        events = trace.get("events", []) if isinstance(trace, dict) else []
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict) or event.get("name") != "cpu_snapshot_models_ready":
                continue
            metadata = event.get("metadata", {})
            if isinstance(metadata, dict) and metadata.get("status") == "ok":
                stored_order = metadata.get("construction_order")
    if stored_order != expected["snapshot_model_order"]:
        failures.append(
            f"stored snapshot order={stored_order!r} "
            f"deployed={expected['snapshot_model_order']!r}"
        )
    if failures:
        raise RuntimeError("C8 runtime-shape validation failed: " + "; ".join(failures))
    return {
        "requested": expected,
        "deployed": deployed,
        "observed": observed,
        "stored_snapshot_model_order": stored_order,
        "snapshot_target_fingerprint": identity.get("fingerprint", ""),
        "guard": guard,
        "construction_order_semantics": "model_construction_order_only",
    }


def _validate_remote_profile(result: dict[str, Any]) -> None:
    """Reject a production benchmark when the remote profile is not production."""
    requested_profile = os.environ.get("COMFYMODAL_V2_ENV_PROFILE", "").strip().lower()
    if requested_profile != "production":
        return

    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    trace_metadata = trace.get("metadata", {}) if isinstance(trace, dict) else {}
    request_origin = (
        trace_metadata.get("request_origin_info", {})
        if isinstance(trace_metadata, dict)
        else {}
    )
    remote_effective = (
        str(request_origin.get("env_profile", "")).strip().lower()
        if isinstance(request_origin, dict)
        else ""
    ) or "absent"
    if remote_effective != "production":
        raise RuntimeError(
            "V2 production profile mismatch:\n"
            "requested=production\n"
            f"remote_effective={remote_effective}\n"
            "The benchmark would bypass the CPU snapshot fast path."
        )


def _timing(
    result: dict[str, Any],
    wall_ms: float,
    *,
    command_start_unix_ms: int | None = None,
    response_received_unix_ns: int | None = None,
) -> dict[str, Any]:
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    deltas = trace.get("deltas_ms", {}) if isinstance(trace, dict) else {}
    derived = trace.get("derived_ms", {}) if isinstance(trace, dict) else {}
    restore = result.get("_restore_timing", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []

    def event_ns(name: str, *, method_name: str = "") -> int | None:
        for event in events:
            if not isinstance(event, dict) or event.get("name") != name:
                continue
            if method_name and event.get("metadata", {}).get("method_name") != method_name:
                continue
            value = event.get("wall_unix_ns")
            if isinstance(value, (int, float)):
                return int(value)
        return None

    def event_mono(name: str, *, phase: str = "") -> int | None:
        """First event's monotonic_ns (same-process duration helper)."""
        for event in events:
            if not isinstance(event, dict) or event.get("name") != name:
                continue
            if phase and event.get("phase") != phase:
                continue
            value = event.get("monotonic_ns")
            if isinstance(value, (int, float)):
                return int(value)
        return None

    def duration_ms(start_name: str, end_name: str) -> float | None:
        start = event_ns(start_name)
        end = event_ns(end_name)
        if start is None or end is None:
            return None
        return round((end - start) / 1_000_000.0, 3)

    validation_to_output_ms = duration_ms("prompt_validation_end", "output_collect_end")
    pre_sampler_ms = duration_ms("prompt_validation_end", "sampler_start")
    sampler_ms = duration_ms("sampler_start", "sampler_end")
    vae_decode_ms = duration_ms("vae_decode_start", "vae_decode_end")
    output_collection_ms = duration_ms("output_collect_start", "output_collect_end")
    local_submit = event_ns("modal_submit_start")
    remote_entry = event_ns("remote_method_entry", method_name="run_plan_stream")
    submit2entry_ms = (
        round((remote_entry - local_submit) / 1_000_000.0, 3)
        if local_submit is not None and remote_entry is not None
        else None
    )
    handle_lookup_ms = duration_ms("modal_handle_lookup_start", "modal_handle_lookup_end")
    submission_to_first_remote_event_ms = duration_ms(
        "modal_submission_attempt", "modal_first_remote_event",
    )
    command_to_response_ms = None
    if command_start_unix_ms is not None and response_received_unix_ns is not None:
        command_to_response_ms = round(
            (response_received_unix_ns - int(command_start_unix_ms) * 1_000_000) / 1_000_000.0,
            1,
        )
    # ── Exact cross-process platform-entry reconciliation ────────────
    # Every interval below is computed from RAW wall timestamps that exist in
    # the trace events / restore timing — nothing is pushed into a generic
    # residual.  Local boundary = local submission attempt (wall); remote
    # boundaries = restore _restore_timing wall fields + method-entry event.
    _restore_timing_dict = restore if isinstance(restore, dict) else {}
    _remote_resume_ns = _num(_restore_timing_dict.get("remote_python_resume_wall_unix_ns"))
    _restore_start_ns = _num(_restore_timing_dict.get("restore_method_start_wall_unix_ns"))
    _restore_end_ns = _num(_restore_timing_dict.get("restore_method_end_wall_unix_ns"))
    _local_submit_ns = event_ns("modal_submission_attempt") or event_ns("modal_submit_start")
    _method_entry_ns = (
        event_ns("run_plan_method_first_line")
        or event_ns("remote_method_entry", method_name="run_plan_stream")
    )
    _first_remote_ns = event_ns("modal_first_remote_event")
    _final_ns = event_ns("final_result_received")

    def _wall_interval(start: Any, end: Any) -> float | None:
        if (
            start is None or end is None
            or not isinstance(start, (int, float)) or not isinstance(end, (int, float))
        ):
            return None
        _delta = int(end) - int(start)
        if _delta < 0:
            return None
        return round(_delta / 1_000_000.0, 3)

    submission_to_remote_python_resume_ms = _wall_interval(
        _local_submit_ns, _remote_resume_ns
    )
    remote_python_resume_to_restore_start_ms = _wall_interval(
        _remote_resume_ns, _restore_start_ns
    )
    restore_to_method_entry_ms = _wall_interval(_restore_end_ns, _method_entry_ns)
    method_entry_to_first_remote_event_ms = _wall_interval(
        _method_entry_ns, _first_remote_ns
    )
    first_remote_event_to_final_result_ms = _wall_interval(
        _first_remote_ns, _final_ns
    )
    # ── Diagnostic UNET transfer stages (same-process monotonic) ──────
    _ea_sched_mono = event_mono("unet_early_activation_scheduled")
    _ea_load_start_mono = event_mono("unet_early_activation_load_start")
    _ea_load_end_mono = event_mono("unet_early_activation_load_end")
    _transfer_queue_delay_ms = None
    if (
        _ea_sched_mono is not None and _ea_load_start_mono is not None
        and _ea_load_start_mono >= _ea_sched_mono
    ):
        _transfer_queue_delay_ms = round(
            (_ea_load_start_mono - _ea_sched_mono) / 1_000_000.0, 3
        )
    _synchronized_transfer_ms = None
    if (
        _ea_load_start_mono is not None and _ea_load_end_mono is not None
        and _ea_load_end_mono >= _ea_load_start_mono
    ):
        _synchronized_transfer_ms = round(
            (_ea_load_end_mono - _ea_load_start_mono) / 1_000_000.0, 3
        )
    # Quiesce wait (quiesced-transfer A/B arm B): emitted only when the
    # request-scoped diagnostic is enabled.
    _quiesce_wait_ms = None
    _quiesce_start_mono = event_mono("unet_quiesce_wait_start")
    _quiesce_end_mono = event_mono("unet_quiesce_wait_end")
    if (
        _quiesce_start_mono is not None and _quiesce_end_mono is not None
        and _quiesce_end_mono >= _quiesce_start_mono
    ):
        _quiesce_wait_ms = round(
            (_quiesce_end_mono - _quiesce_start_mono) / 1_000_000.0, 3
        )
    # Graph/prefill activity: PromptExecutor invoke → sampler lane wait
    # (the graph's own work before the sampler blocks on the mutation lane).
    _graph_activity_ms = None
    _invoke_mono = event_mono("prompt_executor_invoke_start")
    _lane_wait_mono = event_mono("sampler_lane_wait_start")
    if (
        _invoke_mono is not None and _lane_wait_mono is not None
        and _lane_wait_mono >= _invoke_mono
    ):
        _graph_activity_ms = round(
            (_lane_wait_mono - _invoke_mono) / 1_000_000.0, 3
        )
    # Sampler lane wait (authoritative metadata from the boundary events).
    _sampler_lane_wait_ms = None
    _sl_meta = None
    for _event in events:
        if (
            isinstance(_event, dict)
            and _event.get("name") == "sampler_lane_wait_end"
        ):
            _sl_meta = _event.get("metadata", {}) if isinstance(_event.get("metadata"), dict) else {}
            break
    if isinstance(_sl_meta, dict) and isinstance(_sl_meta.get("wait_ms"), (int, float)):
        _sampler_lane_wait_ms = round(float(_sl_meta["wait_ms"]), 3)
    # Quiesced transfer sampler record (arm B; absent otherwise).
    _quiesced_transfer = None
    for _event in events:
        if isinstance(_event, dict) and _event.get("name") == "unet_quiesced_transfer":
            _qt_meta = _event.get("metadata", {})
            if isinstance(_qt_meta, dict):
                _quiesced_transfer = _qt_meta
            break
    # Forward local_timing from result (copied/safe block)
    _local_timing = result.get("local_timing", {}) if isinstance(result, dict) else {}
    if not isinstance(_local_timing, dict):
        _local_timing = {}
    # Full restore breakdown: every restore_timing key ending in ``_ms``.
    restore_breakdown: dict[str, Any] = {}
    if isinstance(restore, dict):
        for _rk, _rv in restore.items():
            if isinstance(_rk, str) and _rk.endswith("_ms") and isinstance(_rv, (int, float)):
                restore_breakdown[_rk] = round(float(_rv), 3)
    # Worker-variance fields from the ``unet_activation_worker_variance`` event.
    _ea_total_ms = None
    _queue_delay_ms = None
    _cpu_snapshot_wait_ms = None
    _dtype_prep_ms = None
    _post_load_bb_ms = None
    for _event in events:
        if not isinstance(_event, dict) or _event.get("name") != "unet_activation_worker_variance":
            continue
        _meta = _event.get("metadata", {}) if isinstance(_event.get("metadata"), dict) else {}
        if isinstance(_meta.get("early_activation_total_ms"), (int, float)):
            _ea_total_ms = float(_meta["early_activation_total_ms"])
        if isinstance(_meta.get("queue_delay_ms"), (int, float)):
            _queue_delay_ms = float(_meta["queue_delay_ms"])
        if isinstance(_meta.get("cpu_snapshot_wait_ms"), (int, float)):
            _cpu_snapshot_wait_ms = float(_meta["cpu_snapshot_wait_ms"])
        _dtype_prep = _meta.get("dtype_layout_preparation")
        if isinstance(_dtype_prep, dict) and isinstance(_dtype_prep.get("wall_ms"), (int, float)):
            _dtype_prep_ms = float(_dtype_prep["wall_ms"])
        _post_bb = _meta.get("post_load_bookkeeping")
        if isinstance(_post_bb, dict) and isinstance(_post_bb.get("wall_ms"), (int, float)):
            _post_load_bb_ms = float(_post_bb["wall_ms"])
        break
    return {
        "wall_ms": round(wall_ms, 1),
        "handle_lookup_ms": handle_lookup_ms,
        "submission_to_first_remote_event_ms": submission_to_first_remote_event_ms,
        "command_to_response_ms": command_to_response_ms,
        "submit2entry_ms": deltas.get("modal_submit_to_entry_ms", submit2entry_ms),
        "t3b_to_t8_ms": deltas.get("t3b_to_t8", derived.get("t3b_to_t8_ms", validation_to_output_ms)),
        "restore_total_ms": restore.get("restore_total_ms") if isinstance(restore, dict) else None,
        "pre_sampler_ms": derived.get("prompt_start_to_sampler_start_ms", pre_sampler_ms),
        "sampler_ms": derived.get("sampler_ms", sampler_ms),
        "vae_decode_ms": derived.get("vae_decode_ms", deltas.get("vae_decode_ms", vae_decode_ms)),
        "output_collection_ms": deltas.get("output_collection_total_ms", output_collection_ms),
        "snapshot_callback_age_at_restore_ms": restore.get("snapshot_callback_age_at_restore_ms") if isinstance(restore, dict) else result.get("snapshot_callback_age_at_restore_ms"),
        "snapshot_callback_to_command_start_ms": result.get("snapshot_callback_to_command_start_ms"),
        "command_start_to_restore_start_ms": result.get("command_start_to_restore_start_ms"),
        "local_timing": _local_timing,
        "restore_breakdown": restore_breakdown,
        "early_activation_total_ms": _ea_total_ms,
        "queue_delay_ms": _queue_delay_ms,
        "cpu_snapshot_wait_ms": _cpu_snapshot_wait_ms,
        "dtype_layout_preparation_ms": _dtype_prep_ms,
        "post_load_bookkeeping_ms": _post_load_bb_ms,
        # Exact cross-process platform-entry reconciliation (raw timestamps).
        "submission_to_remote_python_resume_ms": submission_to_remote_python_resume_ms,
        "remote_python_resume_to_restore_start_ms": remote_python_resume_to_restore_start_ms,
        "restore_to_method_entry_ms": restore_to_method_entry_ms,
        "method_entry_to_first_remote_event_ms": method_entry_to_first_remote_event_ms,
        "first_remote_event_to_final_result_ms": first_remote_event_to_final_result_ms,
        # Diagnostic UNET transfer stages.
        "transfer_queue_delay_ms": _transfer_queue_delay_ms,
        "synchronized_transfer_ms": _synchronized_transfer_ms,
        "quiesce_wait_ms": _quiesce_wait_ms,
        "graph_activity_ms": _graph_activity_ms,
        "sampler_lane_wait_ms": _sampler_lane_wait_ms,
        "quiesced_transfer": _quiesced_transfer,
    }


def _capture_ts() -> tuple[int, int]:
    """Return (wall_unix_ns, monotonic_ns) snapshot.

    Same-process duration calculations use monotonic_ns exclusively.
    Cross-process correlation uses wall_unix_ns only.
    """
    return (int(time.time() * 1_000_000_000), time.monotonic_ns())


# ═══════════════════════════════════════════════════════════════════════════
# Full trace bundle download handoff
# ═══════════════════════════════════════════════════════════════════════════


def _find_in_dir(directory: Path, pattern: str) -> Path | None:
    """Find first file matching *pattern* in *directory* (recursive)."""
    matches = list(directory.rglob(pattern))
    return matches[0] if matches else None


async def _run_downloader_cli(
    *,
    volume_name: str,
    remote_bundle_path: str,
    bundle_sha256: str,
    trace_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Invoke ``tools/download_v2_full_trace.py`` via subprocess.

    The CLI outputs 6 ``KEY=VALUE`` lines on success.  This function parses
    those lines, discovers additional file paths inside the extract directory,
    times the operation, and returns a full metadata dict with all required
    keys for ``full_trace_download.json``.

    Raises ``RuntimeError`` on any failure (CLI not found, nonzero exit,
    timeout, or parse error).
    """
    downloader_path = ROOT / "tools" / "download_v2_full_trace.py"
    if not downloader_path.is_file():
        raise RuntimeError(
            f"Trace downloader not found at {downloader_path}"
        )

    t0 = time.perf_counter()

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(downloader_path),
            "--volume", str(volume_name),
            "--remote-path", str(remote_bundle_path),
            "--sha256", str(bundle_sha256),
            "--trace-id", str(trace_id),
            "--output-dir", str(output_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=120.0,
        )
    except asyncio.TimeoutError:
        raise RuntimeError("Trace downloader timed out after 120s")
    except Exception as exc:
        raise RuntimeError(f"Trace downloader subprocess failed: {exc}") from exc

    download_ms = (time.perf_counter() - t0) * 1000.0

    if proc.returncode != 0:
        stderr_text = (
            stderr_bytes.decode("utf-8", errors="replace")[:500]
            if stderr_bytes else ""
        )
        raise RuntimeError(
            f"Trace downloader exited code={proc.returncode}: {stderr_text}"
        )

    # Parse the 6 FULL_TRACE_* KEY=VALUE output lines from the downloader CLI.
    # Keys are: FULL_TRACE_BUNDLE, FULL_TRACE_REPORT, FULL_TRACE_VIZTRACER,
    #           FULL_TRACE_TORCH, FULL_TRACE_MANIFEST, FULL_TRACE_EXTRACT_DIR
    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    parsed: dict[str, str] = {}
    for line in stdout_text.strip().splitlines():
        line = line.strip()
        if "=" in line:
            k, _, v = line.partition("=")
            parsed[k.strip()] = v.strip()

    required_keys = {
        "FULL_TRACE_BUNDLE",
        "FULL_TRACE_REPORT",
        "FULL_TRACE_VIZTRACER",
        "FULL_TRACE_TORCH",
        "FULL_TRACE_MANIFEST",
        "FULL_TRACE_EXTRACT_DIR",
    }
    missing_keys = sorted(key for key in required_keys if key not in parsed)
    if missing_keys:
        raise RuntimeError(
            "Trace downloader output missing keys: " + ", ".join(missing_keys)
        )

    # Extract the known keys, then map to the required metadata schema
    extract_dir = Path(parsed.get("FULL_TRACE_EXTRACT_DIR", str(output_dir / f"full_trace_{trace_id}")))
    torch_val = parsed.get("FULL_TRACE_TORCH", "")
    if torch_val.lower() == "absent":
        torch_trace_path_val = "absent"
    else:
        torch_trace_path_val = torch_val

    meta: dict[str, Any] = {
        "trace_id": trace_id,
        "remote_bundle_path": remote_bundle_path,
        "local_bundle_path": parsed.get("FULL_TRACE_BUNDLE", ""),
        "extract_dir": str(extract_dir),
        "bundle_sha256": bundle_sha256,
        "verified": True,
        "report_path": parsed.get("FULL_TRACE_REPORT", ""),
        "viztracer_path": parsed.get("FULL_TRACE_VIZTRACER", ""),
        "torch_trace_path": torch_trace_path_val,
        "manifest_path": parsed.get("FULL_TRACE_MANIFEST", ""),
        "download_ms": round(download_ms, 1),
    }
    return meta


async def _handle_full_trace_artifact(
    result: dict[str, Any],
    output_dir: Path,
    workspace: dict[str, Any],
    transport: ModalTransport,
    *,
    _test_trace_downloader: Any = None,
) -> dict[str, Any] | None:
    """Handle ``full_trace_artifact`` from a remote result.

    Descriptor contract (the artifact dict):
      - ``status == 'ready'`` plus ``volume_name``, ``remote_bundle_path``,
        ``bundle_sha256``, ``trace_id`` → invoke the downloader exactly once,
        write ``full_trace_download.json`` beside the run file.
      - ``status == 'error'`` with ``error_type`` and optional ``error`` →
        raise ``RuntimeError`` with a sanitised message; the caller is
        expected to preserve the run file.
      - Absent artifact (no ``full_trace_artifact`` key or non-dict value)
        → return ``None``, no-op.
      - Unknown status → treated as absent (no-op).

    The caller **must** write ``run_<index>.json`` to disk *before* calling
    this function.

    Raises ``RuntimeError`` on error artifacts and on any download /
    verification / extraction / CLI failure.
    """
    full_trace_artifact = (
        result.get("full_trace_artifact")
        if isinstance(result, dict)
        else None
    )
    if not isinstance(full_trace_artifact, dict):
        return None  # absent

    status = full_trace_artifact.get("status", "")

    # ── Error artifact ──────────────────────────────────────────────────
    if status == "error":
        error_type = str(full_trace_artifact.get("error_type", "unknown_error"))[:100]
        error_msg = str(full_trace_artifact.get("error", ""))[:200]
        sanitized = (
            f"({error_type}) {error_msg}"
            if error_msg
            else f"({error_type})"
        )
        raise RuntimeError(f"Trace bundle error: {sanitized}")

    # ── Unknown status — treat as absent ────────────────────────────────
    if status != "ready":
        return None

    # ── Ready artifact — validate required fields ───────────────────────
    volume_name = str(full_trace_artifact.get("volume_name", ""))
    remote_bundle_path = str(full_trace_artifact.get("remote_bundle_path", ""))
    bundle_sha256 = str(full_trace_artifact.get("bundle_sha256", ""))
    trace_id = str(full_trace_artifact.get("trace_id", ""))

    if not all([volume_name, remote_bundle_path, bundle_sha256, trace_id]):
        raise RuntimeError(
            "Trace bundle error: ready artifact missing required fields "
            "(volume_name, remote_bundle_path, bundle_sha256, trace_id)"
        )

    # ── Invoke downloader exactly once ─────────────────────────────────
    if _test_trace_downloader is not None:
        download_meta = await _test_trace_downloader(
            volume_name=volume_name,
            remote_bundle_path=remote_bundle_path,
            bundle_sha256=bundle_sha256,
            trace_id=trace_id,
            output_dir=output_dir,
            workspace=workspace,
            transport=transport,
        )
    else:
        download_meta = await _run_downloader_cli(
            volume_name=volume_name,
            remote_bundle_path=remote_bundle_path,
            bundle_sha256=bundle_sha256,
            trace_id=trace_id,
            output_dir=output_dir,
        )

    if not isinstance(download_meta, dict):
        raise RuntimeError("Trace downloader returned invalid metadata")
    required_meta_keys = {
        "trace_id",
        "remote_bundle_path",
        "local_bundle_path",
        "extract_dir",
        "bundle_sha256",
        "verified",
        "report_path",
        "viztracer_path",
        "torch_trace_path",
        "manifest_path",
        "download_ms",
    }
    missing_meta_keys = sorted(required_meta_keys - set(download_meta))
    if missing_meta_keys:
        raise RuntimeError(
            "Trace downloader metadata missing keys: "
            + ", ".join(missing_meta_keys)
        )

    # Write download metadata beside run file
    (output_dir / "full_trace_download.json").write_text(
        json.dumps(download_meta, default=str, indent=2), encoding="utf-8",
    )
    return download_meta


async def _run_one(
    *,
    index: int,
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    bypass_cpu_snapshot_unet: bool = False,
    _defer_waterfall: bool = False,
    # Variance-cold mode: extra request-origin diagnostic keys carried to the
    # remote runtime (e.g. variance_mode, variance_pretouch, env_profile).
    _extra_origin: dict[str, Any] | None = None,
    # Test overrides (injected helpers, not used in production)
    _test_restore_publisher: Any = None,
    _test_profile_setter: Any = None,
    _test_profile_checker: Any = None,
    _test_trace_downloader: Any = None,
) -> dict[str, Any]:
    # T0: benchmark iteration origin (literal first line)
    _req_id = f"v2-benchmark-{index}-{uuid.uuid4().hex[:12]}"
    _t0_wall_ms = int(time.time() * 1000)
    try:
        _command_start_for_origin = int(os.environ.get("COMFYMODAL_COMMAND_START_UNIX_MS", ""))
    except (TypeError, ValueError):
        _command_start_for_origin = _t0_wall_ms
    _t0_perf = time.perf_counter()
    # T1: local receive (this runner is itself the local receiver)
    _t1_wall_ns, _t1_mono_ns = _capture_ts()
    request_origin_info = {
        "request_id": _req_id,
        "trigger_source": "benchmark",
        "ui_run_triggered_wall_unix_ms": _t0_wall_ms,
        "command_start_unix_ms": _command_start_for_origin,
        "benchmark_run_index": index,
        "local_receive_wall_ns": _t1_wall_ns,
        "local_receive_mono_ns": _t1_mono_ns,
    }
    if _extra_origin:
        request_origin_info.update(_extra_origin)
    prompt_id = _req_id  # request_id == prompt_id

    # ═══════════════════════════════════════════════════════════════════════
    # Prefix timestamp capture: worker_start → plan_build_start
    #
    # Events are captured as (wall_unix_ns, monotonic_ns) tuples BEFORE the
    # RuntimeTrace exists, then emitted via emit_at() after trace creation.
    # This yields a strict non-overlapping partition:
    #
    #   ws [gap1] norm_start [normalize] norm_end [gap2] rtc_start [construct]
    #   rtc_end [gap3] bc_start [copy] bc_end [gap4] cid_start [gen] cid_end
    #   [gap5] bep_call [args] plan_build_start
    #
    # Each gap/span maps to exactly one breakdown field.
    # ═══════════════════════════════════════════════════════════════════════

    # T_worker: first executable boundary (no queue)
    _ws_ts = _capture_ts()

    # T_normalize_start / T_normalize_end
    _norm_ts = _capture_ts()
    production_options = normalize_production_options(modal_options)
    _norm_end_ts = _capture_ts()

    # T_trace_construct_start / T_trace_construct_end
    _rtc_start_ts = _capture_ts()
    runtime_trace = RuntimeTrace(request_id=prompt_id, process="local")
    runtime_trace.set_metadata(request_origin_info=request_origin_info)
    _rtc_end_ts = _capture_ts()

    # ── Emit all captured timestamps in temporal order ──
    runtime_trace.emit_at("worker_start",
        wall_unix_ns=_ws_ts[0], monotonic_ns=_ws_ts[1],
        phase="local", metadata={
            "pid": os.getpid(),
            "thread_native_id": threading.get_native_id(),
            "request_id": _req_id,
        })
    runtime_trace.emit_at("normalize_production_options_start",
        wall_unix_ns=_norm_ts[0], monotonic_ns=_norm_ts[1], phase="local")
    runtime_trace.emit_at("normalize_production_options_end",
        wall_unix_ns=_norm_end_ts[0], monotonic_ns=_norm_end_ts[1], phase="local")
    runtime_trace.emit_at("runtime_trace_construct_start",
        wall_unix_ns=_rtc_start_ts[0], monotonic_ns=_rtc_start_ts[1], phase="local")
    runtime_trace.emit_at("trace_construct_end",
        wall_unix_ns=_rtc_end_ts[0], monotonic_ns=_rtc_end_ts[1], phase="local")

    # T_benchmark_options_copy_start / T_benchmark_options_copy_end
    _bc_ts = _capture_ts()
    runtime_trace.emit_at("benchmark_options_copy_start",
        wall_unix_ns=_bc_ts[0], monotonic_ns=_bc_ts[1], phase="local")
    _bench_modal_options = dict(modal_options)
    if bypass_cpu_snapshot_unet:
        _existing_flags = _bench_modal_options.get("compatibility_flags", {})
        if isinstance(_existing_flags, dict):
            _bench_modal_options["compatibility_flags"] = dict(_existing_flags)
        else:
            _bench_modal_options["compatibility_flags"] = {}
        _bench_modal_options["compatibility_flags"]["diagnostic_bypass_cpu_snapshot_unet"] = True
    _bc_end_ts = _capture_ts()
    runtime_trace.emit_at("benchmark_options_copy_end",
        wall_unix_ns=_bc_end_ts[0], monotonic_ns=_bc_end_ts[1], phase="local")

    # T_client_id_generation_start / T_client_id_generation_end
    _cid_ts = _capture_ts()
    runtime_trace.emit_at("client_id_generation_start",
        wall_unix_ns=_cid_ts[0], monotonic_ns=_cid_ts[1], phase="local")
    _bench_client_id = f"v2-benchmark-client-{uuid.uuid4().hex[:8]}"
    _cid_end_ts = _capture_ts()
    runtime_trace.emit_at("client_id_generation_end",
        wall_unix_ns=_cid_end_ts[0], monotonic_ns=_cid_end_ts[1], phase="local")

    # T_build_execution_plan_call_start
    _bep_call_ts = _capture_ts()
    runtime_trace.emit_at("build_execution_plan_call_start",
        wall_unix_ns=_bep_call_ts[0], monotonic_ns=_bep_call_ts[1], phase="local")
    plan = build_execution_plan(
        workflow,
        prompt_id=prompt_id,
        client_id=_bench_client_id,
        modal_options=_bench_modal_options,
        production_options=production_options if production_options.get("enabled") else None,
        gpu=GPU,
        workspace=workspace,
        request_metadata={"benchmark_run_index": index, "benchmark_app": APP_NAME,
                          "__request_origin_info__": request_origin_info},
        trace=runtime_trace,
        validate=False,
    )

    _mode = "bypass" if bypass_cpu_snapshot_unet else "reuse"
    print(f"cpu_snapshot_unet_mode={_mode}", flush=True)

    # ── execute_plan call ─────────────────────────────────────────────────
    _ep_call_wall_ns, _ep_call_mono_ns = _capture_ts()
    runtime_trace.emit_at("execute_plan_call_start",
        wall_unix_ns=_ep_call_wall_ns, monotonic_ns=_ep_call_mono_ns,
        phase="local")
    started = time.perf_counter()
    print("[v2.benchmark] phase=execute_plan_start", flush=True)
    result = await execute_plan(
        plan,
        transport=transport,
        restore_publisher=_test_restore_publisher if _test_restore_publisher is not None else RemoteRestorePlanPublisher(transport, workspace),
        profile_setter=_test_profile_setter if _test_profile_setter is not None else set_active_warmup_profile,
        profile_checker=_test_profile_checker if _test_profile_checker is not None else check_active_warmup_profile,
        gpu=GPU,
        workspace=workspace,
        trace=runtime_trace,
    )
    _validate_remote_profile(result)
    _response_wall_ns, _response_mono_ns = _capture_ts()
    wall_ms = (time.perf_counter() - started) * 1000.0
    identity = _identity(result)
    if identity.get("app_name") and identity.get("app_name") != APP_NAME:
        raise RuntimeError(f"V2 run {index} returned app {identity['app_name']!r}, expected {APP_NAME!r}")
    runtime_shape_artifact = _validate_runtime_shape(result, identity)
    _host_diag = result.get("host_diagnostics") if isinstance(result, dict) else None
    if not isinstance(_host_diag, dict):
        _host_diag = {}
    artifact = {
        "run_index": index,
        "request_id": prompt_id,
        "prompt_id": prompt_id,
        "target": {"app_name": APP_NAME, "class_name": CLASS_NAME, "gpu": GPU},
        "identity": identity,
        "host_diagnostics": _host_diag,
        "runtime_shape": runtime_shape_artifact,
        "event_types": ["result"],
        "timing": _timing(
            result,
            wall_ms,
            command_start_unix_ms=_command_start_for_origin,
            response_received_unix_ns=_response_wall_ns,
        ),
        "result": result,
    }
    _command_start_ms: int | None = None
    if index == 0:
        try:
            _command_start_ms = int(os.environ.get("COMFYMODAL_COMMAND_START_UNIX_MS", ""))
        except (TypeError, ValueError):
            _command_start_ms = None
    if _command_start_ms is None:
        _command_start_ms = _t0_wall_ms
    _waterfall = build_waterfall(
        result=result,
        timing=artifact["timing"],
        wall_ms=wall_ms,
        command_start_unix_ms=_command_start_ms,
        response_received_unix_ns=_response_wall_ns,
        run_label=f"run {index + 1}",
    )
    artifact["waterfall"] = waterfall_to_dict(_waterfall)
    (output_dir / f"run_{index}.json").write_text(
        json.dumps(artifact, default=str, indent=2), encoding="utf-8"
    )

    # ── Full trace bundle download handoff ─────────────────────────────
    # Run file is safely committed to disk.  Now process any
    # full_trace_artifact from the remote result:
    #   - status == "ready"   → invoke downloader, write full_trace_download.json
    #   - status == "error"   → raise RuntimeError (caught below, run file preserved)
    #   - absent              → no-op (preserves existing behaviour)
    #
    # Errors are caught and stored in the artifact so they do not abort
    # remaining benchmark runs.  The main loop collects all errors and
    # exits non-zero at the end.
    try:
        await _handle_full_trace_artifact(
            result, output_dir, workspace, transport,
            _test_trace_downloader=_test_trace_downloader,
        )
    except Exception as exc:
        artifact["_trace_handoff_error"] = str(exc)[:300]
        (output_dir / f"run_{index}.json").write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )

    print(json.dumps({
        "run_index": index,
        "request_id": prompt_id,
        "identity": identity,
        "runtime_shape": runtime_shape_artifact,
        "timing": artifact["timing"],
    }, default=str))
    if not _defer_waterfall:
        print(render_waterfall(_waterfall), flush=True)
    return artifact


def _extract_unet_runtime_state_event(
    result: dict[str, Any],
    stage: str,
) -> dict[str, Any] | None:
    """Extract the first ``unet_runtime_state`` trace event at *stage*.

    Returns the metadata dict, or ``None`` if not found.
    """
    trace_data = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace_data.get("events", []) if isinstance(trace_data, dict) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("name") != "unet_runtime_state":
            continue
        meta = event.get("metadata", {})
        if isinstance(meta, dict) and meta.get("stage") == stage:
            return meta
    return None


async def _run_ab_compare(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
) -> dict[str, Any]:
    """Run one reuse request and one bypass request, then compute A/B diff.

    Uses the same ``ModalTransport`` but the remote requests may execute
    in different container processes.  Extracts ``unet_runtime_state``
    trace events from each returned trace, validates identity, calls
    ``diff_unet_runtime_states`` locally, and saves the result.

    Raises ``RuntimeError`` when either state is missing or models differ.
    """
    # ── Run A (reuse) ───────────────────────────────────────────────────
    print("[v2.unet_ab] phase=reuse_start", flush=True)
    reuse_result = await _run_one(
        index=0, workflow=workflow, modal_options=modal_options,
        workspace=workspace, transport=transport, output_dir=output_dir,
        bypass_cpu_snapshot_unet=False,
    )
    reuse_meta = _extract_unet_runtime_state_event(
        reuse_result.get("result", {}), "snapshot_restored_post_retarget",
    )
    if reuse_meta is None:
        raise RuntimeError(
            "A/B diff: snapshot_restored_post_retarget state not found in reuse result"
        )

    # ── Run B (bypass) ──────────────────────────────────────────────────
    print("[v2.unet_ab] phase=bypass_start", flush=True)
    bypass_result = await _run_one(
        index=1, workflow=workflow, modal_options=modal_options,
        workspace=workspace, transport=transport, output_dir=output_dir,
        bypass_cpu_snapshot_unet=True,
    )
    bypass_meta = _extract_unet_runtime_state_event(
        bypass_result.get("result", {}), "normal_loader_ready",
    )
    if bypass_meta is None:
        raise RuntimeError(
            "A/B diff: normal_loader_ready state not found in bypass result"
        )

    # ── Validate identity match ─────────────────────────────────────────
    reuse_identity = str(reuse_meta.get("unet_identity", ""))
    bypass_identity = str(bypass_meta.get("unet_identity", ""))
    reuse_wd = str(reuse_meta.get("requested_weight_dtype", ""))
    bypass_wd = str(bypass_meta.get("requested_weight_dtype", ""))
    if reuse_identity != bypass_identity:
        raise RuntimeError(
            f"A/B diff: UNET identity mismatch "
            f"reuse={reuse_identity!r} bypass={bypass_identity!r}"
        )
    if reuse_wd != bypass_wd:
        raise RuntimeError(
            f"A/B diff: weight_dtype mismatch "
            f"reuse={reuse_wd!r} bypass={bypass_wd!r}"
        )

    # ── Compute diff ────────────────────────────────────────────────────
    snapshot_state = dict(reuse_meta.get("state", {})) if isinstance(reuse_meta.get("state"), dict) else {}
    normal_state = dict(bypass_meta.get("state", {})) if isinstance(bypass_meta.get("state"), dict) else {}
    diff = diff_unet_runtime_states(snapshot_state, normal_state)

    # ── Print and save ──────────────────────────────────────────────────
    _diff_json = json.dumps(diff, default=str, separators=(",", ":"), sort_keys=True)
    print(
        f"[v2.unet_runtime_diff] "
        f"field_count={len(diff)} "
        f"fields={_diff_json}",
        flush=True,
    )

    ab_artifact = {
        "unet_identity": reuse_identity,
        "requested_weight_dtype": reuse_wd,
        "reuse_state": snapshot_state,
        "bypass_state": normal_state,
        "diff": diff,
        "field_count": len(diff),
    }
    (output_dir / "unet_runtime_diff.json").write_text(
        json.dumps(ab_artifact, default=str, indent=2), encoding="utf-8",
    )
    print(
        json.dumps({"ab_diff": {"field_count": len(diff), "output": str(output_dir / "unet_runtime_diff.json")}}, default=str),
    )
    return ab_artifact


# ═══════════════════════════════════════════════════════════════════════════
# Acceptance-mode helpers
# ═══════════════════════════════════════════════════════════════════════════


def _trace_event(result: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Return the first trace event with *name*, or None."""
    trace_data = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace_data.get("events", []) if isinstance(trace_data, dict) else []
    for event in events:
        if isinstance(event, dict) and event.get("name") == name:
            return event
    return None


def _event_metadata(event: dict[str, Any] | None, key: str | None = None, default: Any = None) -> Any:
    """Read a metadata key from a trace event dict.
    If *key* is None, returns the entire metadata dict (or default).
    """
    if event is None:
        return default
    meta = event.get("metadata", {})
    if not isinstance(meta, dict):
        return default
    if key is None:
        return meta
    return meta.get(key, default)


def _event_mono_ns(result: dict[str, Any], name: str) -> int | None:
    """Return monotonic_ns of the first event with *name*, or None."""
    ev = _trace_event(result, name)
    if ev is None:
        return None
    val = ev.get("monotonic_ns")
    return int(val) if isinstance(val, (int, float)) else None


def _event_wall_ns(result: dict[str, Any], name: str) -> int | None:
    """Return wall_unix_ns of the first event with *name*, or None."""
    ev = _trace_event(result, name)
    if ev is None:
        return None
    val = ev.get("wall_unix_ns")
    return int(val) if isinstance(val, (int, float)) else None


def _mono_delta_ms(result: dict[str, Any], start: str, end: str) -> float | str | None:
    """Compute end - start in ms using monotonic_ns."""
    s = _event_mono_ns(result, start)
    e = _event_mono_ns(result, end)
    if s is None or e is None:
        return None
    delta = e - s
    if delta < 0:
        return "invalid_negative"
    return round(delta / 1_000_000, 3)


def _wall_delta_ms(result: dict[str, Any], start: str, end: str) -> float | str | None:
    """Compute end - start in ms using wall_unix_ns."""
    s = _event_wall_ns(result, start)
    e = _event_wall_ns(result, end)
    if s is None or e is None:
        return None
    delta = e - s
    if delta < 0:
        return "invalid_negative"
    return round(delta / 1_000_000, 3)


def _extract_restore_timing(result: dict[str, Any]) -> dict[str, Any]:
    """Extract restore_timing from result."""
    rt = result.get("_restore_timing")
    if isinstance(rt, dict):
        return rt
    trace = result.get("trace", {})
    if isinstance(trace, dict):
        rt2 = trace.get("_restore_timing")
        if isinstance(rt2, dict):
            return rt2
    return {}


def _extract_images(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract image descriptors from result."""
    images = result.get("images", [])
    if isinstance(images, list):
        return images
    trace = result.get("trace", {})
    if isinstance(trace, dict):
        im2 = trace.get("images", [])
        if isinstance(im2, list):
            return im2
    return []


async def _read_remote_asset(
    handle: Any,
    backend_path: str,
    expected_sha256: str,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Read an output asset from the remote Modal volume.

    Returns dict with ``byte_count``, ``sha256``, ``data``, and ``fetch_ms``.
    Raises on failure.
    """
    t0 = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                handle.read_output_asset.remote,
                backend_path,
                expected_sha256,
            ),
            timeout=timeout,
        )
    except Exception as exc:
        raise RuntimeError(
            f"asset fetch failed backend_path={backend_path!r} "
            f"expected_sha256={expected_sha256!r}: {exc}"
        ) from exc
    fetch_ms = (time.perf_counter() - t0) * 1000.0
    if not isinstance(result, dict):
        raise RuntimeError(
            f"asset fetch returned non-dict: {type(result).__name__}"
        )
    data = result.get("data")
    if not data:
        raise RuntimeError(
            f"asset fetch returned empty data for {backend_path!r}"
        )
    actual_sha256 = result.get("sha256", "")
    if expected_sha256 and actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"asset SHA mismatch: expected {expected_sha256}, got {actual_sha256}"
        )
    return {
        "backend_path": backend_path,
        "expected_sha256": expected_sha256,
        "actual_sha256": actual_sha256,
        "byte_count": result.get("byte_count", len(data)),
        "fetch_ms": round(fetch_ms, 3),
    }


def _extract_acceptance_timing(
    result: dict[str, Any],
    trigger_to_modal_entry_ms: float | None = None,
    wall_ms: float = 0.0,
) -> dict[str, Any]:
    """Extract comprehensive timing fields for acceptance reporting."""
    restore_timing = _extract_restore_timing(result)
    timing: dict[str, Any] = {
        "wall_ms": round(wall_ms, 1),
        "trigger_to_modal_entry_ms": trigger_to_modal_entry_ms,
        "method_entry_to_durable_result_ms": None,
        "trigger_to_durable_result_ms": None,
        "restore_total_ms": None,
        "dispatch_to_modal_entry_ms": None,
        "exec_start_to_cached_ms": None,
        "sampler_node_to_sampler_start_ms": None,
        "sampling_ms": None,
        "vae_decode_ms": None,
        "output_encode_ms": None,
        "snapshot_callback_age_at_restore_ms": None,
        "snapshot_callback_to_command_start_ms": None,
        "command_start_to_restore_start_ms": None,
        "sampler_node_id": None,
        "sampler_class_type": None,
        "sampler_identification_source": "unavailable",
        "sampler_node_to_sampling_start_ms": None,
    }

    # restore_total_ms
    rt_val = restore_timing.get("restore_total_ms")
    if isinstance(rt_val, (int, float)):
        timing["restore_total_ms"] = round(float(rt_val), 3)

    # Method entry = remote_method_entry for run_plan_stream
    _method_entry_mono = _event_mono_ns(result, "remote_method_entry")
    _method_entry_wall = _event_wall_ns(result, "remote_method_entry")
    # Plan received = run_plan_first_status_yield
    _plan_received_mono = _event_mono_ns(result, "run_plan_first_status_yield")
    # Output collect end = output_collect_end or output_persist_end (whichever later)
    _output_end_mono = _event_mono_ns(result, "output_persist_end")

    # dispatch_to_modal_entry_ms
    _local_submit_wall = _event_wall_ns(result, "modal_submit_start")
    if _local_submit_wall and _method_entry_wall:
        timing["dispatch_to_modal_entry_ms"] = round(
            (_method_entry_wall - _local_submit_wall) / 1_000_000, 3
        )

    # method_entry_to_durable_result_ms
    if _method_entry_mono and _output_end_mono:
        val = (_output_end_mono - _method_entry_mono) / 1_000_000
        if val >= 0:
            timing["method_entry_to_durable_result_ms"] = round(val, 3)

    # trigger_to_durable_result_ms (if trigger_to_modal_entry_ms is given)
    if trigger_to_modal_entry_ms is not None and timing.get("method_entry_to_durable_result_ms") is not None:
        timing["trigger_to_durable_result_ms"] = round(
            trigger_to_modal_entry_ms + timing["method_entry_to_durable_result_ms"], 3
        )

    # exec_start_to_cached_ms: execution_start -> execution_cached
    timing["exec_start_to_cached_ms"] = _mono_delta_ms(result, "execution_start", "execution_cached")

    # sampler_node_to_sampler_start_ms: milestone metadata
    _pre_sampler = _trace_event(result, "pre_sampler_stages")
    if _pre_sampler is not None:
        _ps_meta = _event_metadata(_pre_sampler)  # returns full metadata dict
        val = _ps_meta.get("sampler_node_to_sampler_start_ms")
        if isinstance(val, (int, float)):
            timing["sampler_node_to_sampler_start_ms"] = round(float(val), 3)
        timing["sampler_node_id"] = _ps_meta.get("sampler_node_id") or None
        timing["sampler_class_type"] = _ps_meta.get("sampler_class_type") or None
        timing["sampler_identification_source"] = _ps_meta.get(
            "sampler_identification_source", "unavailable"
        )
        timing["sampler_node_to_sampling_start_ms"] = timing.get(
            "sampler_node_to_sampler_start_ms"
        )

    _restore_age = restore_timing.get("snapshot_callback_age_at_restore_ms")
    timing["snapshot_callback_age_at_restore_ms"] = _restore_age
    _trace_meta = result.get("trace", {}).get("metadata", {}) if isinstance(result.get("trace"), dict) else {}
    timing["snapshot_callback_to_command_start_ms"] = result.get(
        "snapshot_callback_to_command_start_ms", _trace_meta.get("snapshot_callback_to_command_start_ms")
    )
    timing["command_start_to_restore_start_ms"] = result.get(
        "command_start_to_restore_start_ms", _trace_meta.get("command_start_to_restore_start_ms")
    )

    # sampling_ms
    _ss = _event_mono_ns(result, "sampling_start")
    _se = _event_mono_ns(result, "sampling_end")
    if _ss is not None and _se is not None:
        val = (_se - _ss) / 1_000_000
        if val >= 0:
            timing["sampling_ms"] = round(val, 3)

    # vae_decode_ms
    _vd_start = _event_mono_ns(result, "vae_decode_start")
    _vd_end = _event_mono_ns(result, "vae_decode_end")
    if _vd_start is not None and _vd_end is not None:
        val = (_vd_end - _vd_start) / 1_000_000
        if val >= 0:
            timing["vae_decode_ms"] = round(val, 3)

    # output_encode_ms
    _oe_start = _event_mono_ns(result, "output_encode_start")
    _oe_end = _event_mono_ns(result, "output_encode_end")
    if _oe_start is not None and _oe_end is not None:
        val = (_oe_end - _oe_start) / 1_000_000
        if val >= 0:
            timing["output_encode_ms"] = round(val, 3)

    # Clip preparation timings
    timing["clip_prepare_start_ms"] = _mono_delta_ms(result, "clip_prepare_start", "clip_prepare_end")

    # UNET demand/load/page-fault timings (from trace events)
    _unet_demand = _trace_event(result, "unet_gpu_demand_start")
    _unet_first_cuda = _trace_event(result, "unet_first_cuda_op")
    if _unet_first_cuda is not None:
        timing["unet_demand_to_first_forward_ms"] = _event_metadata(
            _unet_first_cuda, "elapsed_ms"
        )
        timing["demand_start_present"] = _event_metadata(
            _unet_first_cuda, "demand_start_present", 0
        )
    else:
        timing["unet_demand_to_first_forward_ms"] = _ABSENT_STR
        timing["demand_start_present"] = 0

    # Output commit ms
    _asset_diag = _trace_event(result, "output_persist_end")
    if _asset_diag is not None:
        _asset_meta = _event_metadata(_asset_diag)
        if isinstance(_asset_meta, dict):
            _commit_ms = _asset_meta.get("commit_ms") or _asset_meta.get("output_volume_commit_ms")
            if isinstance(_commit_ms, (int, float)):
                timing["output_commit_ms"] = round(float(_commit_ms), 3)

    return timing


def _check_acceptance(
    run_label: str,
    result: dict[str, Any],
    timing: dict[str, Any],
    images: list[dict[str, Any]],
    asset_proofs: list[dict[str, Any]],
    *,
    is_fresh: bool = False,
    is_reused: bool = False,
    expected_restore_count: int | None = None,
    expected_request_count: int | None = None,
    expected_request_count_min: int | None = None,
    expected_instance_id: str | None = None,
    forbid_instance_id: str | None = None,
) -> list[str]:
    """Run acceptance checks for a single run. Returns list of failures (empty = pass).

    Identity proof uses ``restored_instance_id``, ``restore_count``, and
    ``request_count`` from the request-scoped ``remote_method_entry`` metadata.
    Absent/missing values fail explicitly — never default to "pass".

    * ``expected_restore_count`` — exact restore_count requirement
    * ``expected_request_count`` — exact request_count requirement (A, C fresh)
    * ``expected_request_count_min`` — minimum request_count (B reused, >= 2)
    * ``expected_instance_id`` — must match this restored_instance_id (B)
    * ``forbid_instance_id`` — must differ (C fresh)

    ``restore_count`` is cumulative per-instance from ``_v2_container_restore_count``
    and is 1 for every request within the same restore lifecycle.
    B's no-new-restore proof uses lifecycle event counting, not restore_count=0.
    """
    failures: list[str] = []

    # ── Unwrap artifact['result'] for trace/event inspection ──
    # In production acceptance mode, this function receives the artifact wrapper
    # (keys: identity, images, timing, asset_proofs, result).  The actual remote
    # result with the 'trace' key lives at result['result'].
    # Unwrap transparently so both direct (unit-test flat dict) and wrapped
    # (production artifact) callers work — trace/event helpers see the raw result.
    _ev_result: dict[str, Any] = result
    if isinstance(result, dict):
        _inner = result.get("result")
        if isinstance(_inner, dict) and "trace" in _inner:
            _ev_result = _inner

    # ── Identity checks ──
    identity = result.get("identity", {})
    restored_instance_id = str(identity.get("restored_instance_id", ""))
    restore_count = int(identity.get("restore_count", -1))
    request_count = int(identity.get("request_count", -1))

    if not restored_instance_id:
        failures.append(f"{run_label}: restored_instance_id is empty/absent")
    if expected_restore_count is not None and restore_count != expected_restore_count:
        failures.append(
            f"{run_label}: restore_count={restore_count}, expected={expected_restore_count}"
        )
    if expected_request_count is not None and request_count != expected_request_count:
        failures.append(
            f"{run_label}: request_count={request_count}, expected={expected_request_count}"
        )
    if expected_request_count_min is not None and request_count < expected_request_count_min:
        failures.append(
            f"{run_label}: request_count={request_count} < min={expected_request_count_min}"
        )
    if expected_instance_id and restored_instance_id != expected_instance_id:
        failures.append(
            f"{run_label}: restored_instance_id={restored_instance_id!r} != "
            f"expected={expected_instance_id!r}"
        )
    if forbid_instance_id and restored_instance_id == forbid_instance_id:
        failures.append(
            f"{run_label}: restored_instance_id={restored_instance_id!r} should differ "
            f"from forbid={forbid_instance_id!r}"
        )

    # ── Check no AsyncUsageWarning in result text or trace ──
    result_str = json.dumps(result, default=str)
    if "AsyncUsageWarning" in result_str or "SyncUsageWarning" in result_str:
        failures.append(f"{run_label}: contains AsyncUsageWarning/SyncUsageWarning")

    # ── base64 zero ──
    _attempts = result.get("output_attempts", [])
    if isinstance(_attempts, list):
        for attempt in _attempts:
            if isinstance(attempt, dict):
                enc = attempt.get("base64_encode_count", 0)
                dec = attempt.get("base64_decode_count", 0)
                if enc or dec:
                    failures.append(f"{run_label}: base64 count non-zero (enc={enc}, dec={dec})")

    # ── Asset proofs ──
    if not images:
        failures.append(f"{run_label}: no image descriptors found")
    else:
        for img in images:
            _aid = str(img.get("asset_id", ""))
            _backend = str(img.get("backend_path", ""))
            _identity = str(img.get("identity", ""))
            _expected_sha = _aid  # asset_id is the bare sha256
            if not _aid and not _backend:
                failures.append(f"{run_label}: image descriptor missing asset_id and backend_path")
                continue
            if not _expected_sha:
                failures.append(f"{run_label}: image descriptor has empty asset_id")
                continue
            # Verify asset proof was fetched
            _found = False
            for proof in asset_proofs:
                if proof.get("expected_sha256") == _expected_sha:
                    _found = True
                    if not proof.get("byte_count", 0):
                        failures.append(f"{run_label}: asset {_expected_sha[:16]} empty bytes")
                    if proof.get("actual_sha256") != _expected_sha:
                        failures.append(f"{run_label}: asset {_expected_sha[:16]} SHA mismatch")
                    break
            if not _found:
                failures.append(f"{run_label}: asset {_expected_sha[:16]} not fetched")

    # ── Timing gate: method_entry_to_durable_result <= 12s ──
    method_to_result = timing.get("method_entry_to_durable_result_ms")
    if isinstance(method_to_result, (int, float)):
        if method_to_result > 12000:
            failures.append(
                f"{run_label}: method_entry_to_durable_result_ms={method_to_result} > 12000"
            )
    else:
        failures.append(f"{run_label}: method_entry_to_durable_result_ms unavailable")

    # ── Timing gate: trigger_to_durable_result <= 18s (when dispatch <= 6s) ──
    dispatch_ms = timing.get("dispatch_to_modal_entry_ms")
    trigger_to_result = timing.get("trigger_to_durable_result_ms")
    if isinstance(dispatch_ms, (int, float)):
        if dispatch_ms <= 6000 and isinstance(trigger_to_result, (int, float)):
            if trigger_to_result > 18000:
                failures.append(
                    f"{run_label}: dispatch={dispatch_ms} <= 6000 but "
                    f"trigger_to_durable_result={trigger_to_result} > 18000"
                )

    # ── Fresh-request specific checks ──
    if is_fresh:
        # UNET first-CUDA timing must be present with nonzero elapsed
        _unet_elapsed = timing.get("unet_demand_to_first_forward_ms")
        _demand_present = timing.get("demand_start_present", 0)
        if not isinstance(_unet_elapsed, (int, float)):
            failures.append(f"{run_label}: unet_demand_to_first_forward_ms missing/absent ({_unet_elapsed})")
        elif _unet_elapsed < 0:
            failures.append(f"{run_label}: unet_demand_to_first_forward_ms negative ({_unet_elapsed})")
        if _demand_present != 1:
            failures.append(f"{run_label}: demand_start_present={_demand_present}, expected 1")

        # output_encode_ms must be present
        _oenc = timing.get("output_encode_ms")
        if not isinstance(_oenc, (int, float)):
            failures.append(f"{run_label}: output_encode_ms missing/absent ({_oenc})")

        # output_commit_ms must be present (0.0 is valid — means zero latency)
        _oc = timing.get("output_commit_ms")
        if _oc is None:
            failures.append(f"{run_label}: output_commit_ms missing/absent")

        # clip_preparation_timings_ms: structured dict from _restore_timing keys.
        # Informational — not a blocking check since clip load is a restore-stage
        # operation and may be per-container rather than per-request.

        # ── UNET/CLIP/VAE seeded check from seed_loader_cache_signatures evidence ──
        # Require executor_loader_cache_seed_end event containing diagnostics from
        # seed_loader_cache_signatures().  Every fresh request must have exactly
        # one non-conflicting decision per role: unet=seeded, clip=seeded,
        # vae=seeded (the production warmup profile declares a VAE, so the
        # retained snapshot VAE is seeded when the canonical identity matches).
        _seed_ev = _trace_event(_ev_result, "executor_loader_cache_seed_end")
        if _seed_ev is None:
            failures.append(
                f"{run_label}: seed_loader_cache_signatures evidence missing "
                "(no executor_loader_cache_seed_end trace event)"
            )
        else:
            _seed_meta = _event_metadata(_seed_ev, "diagnostics", {})
            if not isinstance(_seed_meta, dict) or not _seed_meta:
                failures.append(f"{run_label}: seed diagnostics empty or absent")
            else:
                # Collect decisions per role
                role_decisions: dict[str, list[str]] = {}
                role_node_ids: dict[str, list[str]] = {}
                for node_id, decision in _seed_meta.items():
                    if not isinstance(decision, dict):
                        continue
                    role = decision.get("role", "")
                    dec = decision.get("decision", "")
                    if role:
                        role_decisions.setdefault(role, []).append(dec)
                        role_node_ids.setdefault(role, []).append(node_id)

                # Each required role must be present
                for role in ("unet", "clip", "vae"):
                    if role not in role_decisions:
                        failures.append(
                            f"{run_label}: no {role} decision in seed evidence "
                            f"(present roles: {sorted(role_decisions)})"
                        )

                # No conflicting decisions within a role
                for role, decisions in role_decisions.items():
                    unique = set(decisions)
                    if len(unique) > 1:
                        failures.append(
                            f"{run_label}: conflicting {role} decisions: "
                            f"{dict(zip(role_node_ids[role], decisions))}"
                        )

                # Verify expected decision values for known roles
                _EXPECTED: dict[str, str] = {
                    "unet": "seeded",
                    "clip": "seeded",
                    "vae": "seeded",
                }
                for role, expected in _EXPECTED.items():
                    if role in role_decisions:
                        actual = role_decisions[role][0]
                        if actual != expected:
                            failures.append(
                                f"{run_label}: {role} decision={actual!r}, "
                                f"expected={expected!r}"
                            )

        # ── Step 3 evidence: snapshot graph seed apply ──
        # Every fresh request must carry the executor seed-apply seam result:
        # a snapshot_graph_seed_apply_end trace event attesting schema-v2,
        # within_budget, zero invalidations (fresh workflow == published seed),
        # sampler entries untouched, and an explicit fallback reason (the
        # marker must never silently claim "seeded").
        _seed_apply_ev = _trace_event(_ev_result, "snapshot_graph_seed_apply_end")
        if _seed_apply_ev is None:
            failures.append(
                f"{run_label}: snapshot_graph_seed_apply_end event missing"
            )
        else:
            _sa_meta = _event_metadata(_seed_apply_ev)
            if not isinstance(_sa_meta, dict) or not _sa_meta:
                failures.append(f"{run_label}: seed apply metadata empty or absent")
            else:
                _sa_schema = _sa_meta.get("schema", 0)
                if _sa_schema != 2:
                    failures.append(
                        f"{run_label}: seed apply schema={_sa_schema}, expected 2"
                    )
                if _sa_meta.get("within_budget") is not True:
                    failures.append(
                        f"{run_label}: seed apply within_budget not true "
                        f"({_sa_meta.get('within_budget')})"
                    )
                if _sa_meta.get("invalidated", -1) != 0:
                    failures.append(
                        f"{run_label}: seed apply invalidated="
                        f"{_sa_meta.get('invalidated')}, expected 0"
                    )
                if _sa_meta.get("sampler_untouched") is not True:
                    failures.append(
                        f"{run_label}: seed apply sampler_untouched not true "
                        f"({_sa_meta.get('sampler_untouched')})"
                    )
                if not isinstance(_sa_meta.get("fallback_reason"), str) or not _sa_meta.get("fallback_reason"):
                    failures.append(
                        f"{run_label}: seed apply fallback_reason missing"
                    )

        # exec_start_to_cached_ms must be present; threshold <= 500ms
        _esc = timing.get("exec_start_to_cached_ms")
        if not isinstance(_esc, (int, float)):
            failures.append(
                f"{run_label}: exec_start_to_cached_ms missing/absent ({_esc})"
            )
        elif _esc > 500:
            failures.append(f"{run_label}: exec_start_to_cached_ms={_esc} > 500")

        # sampler_node_to_sampler_start_ms must be present; threshold <= 1000ms
        _snss = timing.get("sampler_node_to_sampler_start_ms")
        if not isinstance(_snss, (int, float)):
            failures.append(
                f"{run_label}: sampler_node_to_sampler_start_ms missing/absent ({_snss})"
            )
        elif _snss > 1000:
            failures.append(f"{run_label}: sampler_node_to_sampler_start_ms={_snss} > 1000")

        # Require authoritative sampling_start and sampling_end events
        _sampling_start = _trace_event(_ev_result, "sampling_start")
        _sampling_end = _trace_event(_ev_result, "sampling_end")
        if _sampling_start is None:
            failures.append(f"{run_label}: sampling_start event missing")
        if _sampling_end is None:
            failures.append(f"{run_label}: sampling_end event missing")

        # Exactly 8 sigma-derived wrapper steps
        if _sampling_end is not None:
            _steps = _event_metadata(_sampling_end, "steps", None)
            if _steps is None:
                failures.append(
                    f"{run_label}: steps not found on sampling_end event"
                )
            elif _steps != 8:
                failures.append(f"{run_label}: steps={_steps}, expected 8")

        # Sampling ends before VAE decode starts
        _ss_ns = _event_mono_ns(_ev_result, "sampling_end")
        _vd_ns = _event_mono_ns(_ev_result, "vae_decode_start")
        if _ss_ns is not None and _vd_ns is not None:
            if _ss_ns >= _vd_ns:
                failures.append(
                    f"{run_label}: sampling_end ({_ss_ns}) >= vae_decode_start ({_vd_ns})"
                )

    # ── Reused request (B) specific checks ──
    # B must share A's restored_instance_id (same container, no new restore).
    # B must have request_count >= 2 (A's request plus this one).
    # B's restore_count is 1 (cumulative per-instance from _v2_container_restore_count).
    # No-new-restore proof: zero request-scoped restore lifecycle events.
    if is_reused:
        if request_count < 2:
            failures.append(f"{run_label} (reused): request_count={request_count} < 2")
        if not expected_instance_id:
            failures.append(f"{run_label} (reused): expected_instance_id not provided for comparison")
        # Lifecycle event check: count request-scoped events with names indicating
        # a restore lifecycle ran during this request.
        _req_id = str(identity.get("request_id", ""))
        _lifecycle_events = _trace_events_for_request(_ev_result, _req_id)
        _restore_lifecycle = [
            ev for ev in _lifecycle_events
            if isinstance(ev, dict) and ev.get("name", "") in (
                "remote_lifecycle_start", "remote_lifecycle_end",
                "restore_method_start", "restore_method_end",
                "gpu_invocation_submit", "startup",
            )
        ]
        if _restore_lifecycle:
            _names = [ev.get("name", "") for ev in _restore_lifecycle]
            failures.append(
                f"{run_label} (reused): found {len(_restore_lifecycle)} request-scoped "
                f"restore lifecycle events: {_names}"
            )

    return failures


def _extract_request_id(result: dict[str, Any]) -> str:
    """Extract the authoritative request_id from trace events."""
    for ev in result.get("trace", {}).get("events", []):
        if isinstance(ev, dict):
            meta = ev.get("metadata", {})
            if isinstance(meta, dict):
                rid = meta.get("request_id", "")
                if rid:
                    return str(rid)
    return ""


def _trace_events_for_request(result: dict[str, Any], request_id: str) -> list[dict[str, Any]]:
    """Return events belonging to the current request's execution.

    Most production RuntimeTrace events do NOT carry per-event ``request_id``
    in metadata — they are identified by their position AFTER the matching
    ``remote_method_entry`` event (which DOES carry request_id).

    Strategy: find the LAST ``remote_method_entry`` whose metadata.request_id
    matches *request_id*.  All events from that index onward belong to this
    request.  Events before that index are from startup/restore lifecycle
    (which share the same container_session_id but are not this request).
    """
    trace = result.get("trace", {})
    if not isinstance(trace, dict):
        return []
    events = trace.get("events", [])
    if not isinstance(events, list):
        return []

    # Find the index of the LAST remote_method_entry matching request_id
    boundary_idx = -1
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            continue
        if ev.get("name") != "remote_method_entry":
            continue
        meta = ev.get("metadata", {})
        if isinstance(meta, dict) and meta.get("request_id") == request_id:
            boundary_idx = i  # keep overwriting — we want the LAST match

    if boundary_idx < 0:
        return []

    # All events at or after boundary_idx belong to this request
    return events[boundary_idx:]


def _extract_identity_from_trace(result: dict[str, Any], request_id: str) -> dict[str, Any]:
    """Extract identity fields from the LAST ``remote_method_entry`` matching
    ``request_id`` (these DO carry per-event request_id).

    Reads ``restored_instance_id``, ``restore_count``, ``request_count``.
    Missing/absent values are reported as empty/0 — checks will fail on absence.
    """
    trace = result.get("trace", {})
    events = trace.get("events", []) if isinstance(trace, dict) else []
    if not isinstance(events, list):
        events = []
    instance_id = ""
    restore_count = 0
    request_count = 0
    runtime_fields: dict[str, Any] = {}
    # Find the LAST matching remote_method_entry (most recent before return)
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("name") != "remote_method_entry":
            continue
        meta = ev.get("metadata", {})
        if isinstance(meta, dict) and meta.get("request_id") == request_id:
            instance_id = str(meta.get("restored_instance_id", "")) or instance_id
            rc = meta.get("restore_count", 0)
            if isinstance(rc, (int, float)):
                restore_count = int(rc)
            rqc = meta.get("request_count", 0)
            if isinstance(rqc, (int, float)):
                request_count = int(rqc)
            for field in (
                "app_name",
                "class_name",
                "cpu",
                "memory_mb",
                "fingerprint",
                "runtime_shape",
                "runtime_shape_fingerprint",
                "runtime_shape_label",
                "stored_snapshot_model_order",
            ):
                if field in meta:
                    runtime_fields[field] = meta[field]
    return {
        "restored_instance_id": instance_id,
        "restore_count": restore_count,
        "request_count": request_count,
        "request_id": request_id,
        **runtime_fields,
    }


def _extract_acceptance_timing_scoped(
    result: dict[str, Any],
    request_id: str,
    *,
    trigger_to_modal_entry_ms: float | None = None,
    wall_ms: float = 0.0,
) -> dict[str, Any]:
    """Extract timing fields using boundary-based event selection.

    Most production RuntimeTrace events do NOT carry per-event ``request_id``.
    Instead, find the LAST ``remote_method_entry`` with matching ``request_id``
    (the request boundary marker), then use ALL monotonic timestamps from events
    at or after that position.  Events before the boundary (lifecycle, prior
    requests, startup) are excluded.
    """
    trace = result.get("trace", {})
    all_events = trace.get("events", []) if isinstance(trace, dict) else []
    if not isinstance(all_events, list):
        all_events = []

    # Find boundary index: last remote_method_entry matching request_id
    boundary_idx = -1
    for i, ev in enumerate(all_events):
        if not isinstance(ev, dict):
            continue
        if ev.get("name") != "remote_method_entry":
            continue
        meta = ev.get("metadata", {})
        if isinstance(meta, dict) and meta.get("request_id") == request_id:
            boundary_idx = i

    if boundary_idx < 0:
        # Fallback: use all events (may include lifecycle)
        events = all_events
    else:
        events = all_events[boundary_idx:]

    # Build monotonic timestamp map (last occurrence wins, skip zero/placeholder)
    ts: dict[str, int] = {}
    for ev in events:
        name = ev.get("name", "")
        mono = ev.get("monotonic_ns")
        if isinstance(mono, (int, float)) and mono > 0:
            ts[name] = int(mono)

    def _d(start: str, end: str) -> float | None:
        s = ts.get(start)
        e = ts.get(end)
        if s is None or e is None:
            return None
        delta = e - s
        if delta < 0:
            return None
        return round(delta / 1_000_000, 3)

    restore_timing = _extract_restore_timing(result)

    # Required field names per spec
    timing: dict[str, Any] = {
        "wall_ms": round(wall_ms, 1),
        "trigger_to_result_ms": trigger_to_modal_entry_ms,
        "dispatch_to_modal_entry_ms": None,
        "restore_total_ms": None,
        "method_entry_to_result_ms": _d("remote_method_entry", "output_persist_end"),
        "method_entry_to_durable_result_ms": _d("remote_method_entry", "output_persist_end"),
        "trigger_to_durable_result_ms": None,
        "exec_start_to_cached_ms": None,
        "sampler_node_to_sampler_start_ms": None,
        "sampling_ms": _d("sampling_start", "sampling_end"),
        "vae_decode_ms": _d("vae_decode_start", "vae_decode_end"),
        "output_encode_ms": _d("output_encode_start", "output_encode_end") or _d("output_encode_start", "output_persist_start"),
        "output_commit_ms": None,
        "clip_preparation_timings_ms": _d("clip_prepare_start", "clip_prepare_end"),
        "unet_demand_to_first_forward_ms": _ABSENT_STR,
        "demand_start_present": 0,
        "asset_fetch_ms": None,
        "snapshot_callback_age_at_restore_ms": restore_timing.get("snapshot_callback_age_at_restore_ms"),
        "snapshot_callback_to_command_start_ms": result.get("snapshot_callback_to_command_start_ms"),
        "command_start_to_restore_start_ms": result.get("command_start_to_restore_start_ms"),
        "sampler_node_id": None,
        "sampler_class_type": None,
        "sampler_identification_source": "unavailable",
        "sampler_node_to_sampling_start_ms": None,
    }

    # restore_total_ms
    rt_val = restore_timing.get("restore_total_ms")
    if isinstance(rt_val, (int, float)):
        timing["restore_total_ms"] = round(float(rt_val), 3)

    # dispatch_to_modal_entry_ms: use wall clock from modal_submit_start to
    # the boundary remote_method_entry.  modal_submit_start may be before the
    # boundary in the merged trace (local event precedes remote).  Find it by
    # scanning ALL events for the LAST one (most recent for this request).
    _sub_wall = None
    _entry_wall = None
    for ev in all_events:
        if not isinstance(ev, dict):
            continue
        if ev.get("name") == "modal_submit_start":
            w = ev.get("wall_unix_ns")
            if isinstance(w, (int, float)):
                _sub_wall = int(w)
    # Find remote_method_entry at boundary
    if boundary_idx >= 0:
        b_ev = all_events[boundary_idx]
        w = b_ev.get("wall_unix_ns")
        if isinstance(w, (int, float)):
            _entry_wall = int(w)
    if _sub_wall and _entry_wall:
        delta = _entry_wall - _sub_wall
        if delta >= 0:
            timing["dispatch_to_modal_entry_ms"] = round(delta / 1_000_000, 3)

    # trigger_to_durable_result_ms
    if trigger_to_modal_entry_ms is not None and timing.get("method_entry_to_durable_result_ms") is not None:
        val = trigger_to_modal_entry_ms + timing["method_entry_to_durable_result_ms"]
        timing["trigger_to_durable_result_ms"] = round(val, 3)
        timing["trigger_to_result_ms"] = timing["trigger_to_durable_result_ms"]

    # exec_start_to_cached_ms from prompt_executor_milestones metadata
    for ev in events:
        if ev.get("name") == "prompt_executor_milestones":
            meta = ev.get("metadata", {})
            if isinstance(meta, dict):
                val = meta.get("execution_start_to_cached_ms")
                if isinstance(val, (int, float)) and val >= 0:
                    timing["exec_start_to_cached_ms"] = round(float(val), 3)

    # sampler_node_to_sampler_start_ms from pre_sampler_stages metadata
    for ev in events:
        if ev.get("name") == "pre_sampler_stages":
            meta = ev.get("metadata", {})
            if isinstance(meta, dict):
                val = meta.get("sampler_node_to_sampler_start_ms")
                if isinstance(val, (int, float)) and val >= 0:
                    timing["sampler_node_to_sampler_start_ms"] = round(float(val), 3)
                timing["sampler_node_id"] = meta.get("sampler_node_id") or None
                timing["sampler_class_type"] = meta.get("sampler_class_type") or None
                timing["sampler_identification_source"] = meta.get(
                    "sampler_identification_source", "unavailable"
                )
                timing["sampler_node_to_sampling_start_ms"] = timing.get(
                    "sampler_node_to_sampler_start_ms"
                )

    # unet_demand_to_first_forward_ms from unet_first_cuda_op
    for ev in events:
        if ev.get("name") == "unet_first_cuda_op":
            meta = ev.get("metadata", {})
            if isinstance(meta, dict):
                val = meta.get("elapsed_ms")
                if isinstance(val, (int, float)):
                    timing["unet_demand_to_first_forward_ms"] = round(float(val), 3)
                dp = meta.get("demand_start_present", 0)
                timing["demand_start_present"] = int(dp) if dp else 0

    # output_commit_ms from result output_diagnostics (commit happens async
    # after output_persist_end is emitted, so event metadata has None).
    _od = result.get("output_diagnostics", {})
    if isinstance(_od, dict):
        cm = (_od.get("output_volume_commit_ms") or _od.get("commit_ms")
              or _od.get("output_commit_overlap_ms"))
        if isinstance(cm, (int, float)) and cm >= 0:
            timing["output_commit_ms"] = round(float(cm), 3)
    # Fallback: check output_persist_end metadata directly
    if timing["output_commit_ms"] is None:
        for ev in events:
            if ev.get("name") == "output_persist_end":
                meta = ev.get("metadata", {})
                if isinstance(meta, dict):
                    cm = meta.get("commit_ms") or meta.get("output_volume_commit_ms")
                    if isinstance(cm, (int, float)) and cm >= 0:
                        timing["output_commit_ms"] = round(float(cm), 3)

    # clip_preparation_timings: structured dict of available restore-stage
    # model/GPU preparation timings from _restore_timing.  These include
    # snapshot_restore, GPU state restoration, CUDA init, model reload, and
    # the full backend startup (which encompasses all model loading).
    _clip_keys = (
        "snapshot_restore_ms", "restore_gpu_state_ms", "cuda_init_ms",
        "reload_models_ms", "reload_runtime_state_ms", "backend_startup_ms",
        "restore_total_ms",
    )
    _clip_t: dict[str, Any] = {}
    for _ck in _clip_keys:
        _cv = restore_timing.get(_ck)
        if isinstance(_cv, (int, float)):
            _clip_t[str(_ck)] = round(float(_cv), 3)
    if _clip_t:
        timing["clip_preparation_timings_ms"] = _clip_t

    return timing


async def _run_acceptance_sequence(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
) -> dict[str, Any]:
    """Run the A/B/C acceptance sequence with full identity/asset/timing validation.

    Sequence:
      A: Fresh restored request.  Fetch all assets.
      B: IMMEDIATELY submit second request via same transport/handle (no cache clear,
         no wait).  Fetch all assets.
      Wait >= 6 seconds.
      C: Another fresh restored request.  Fetch all assets.

    Every run: fetch all image assets via remote read_output_asset, verify SHA.
    Summary includes all runs, failures, retries.
    """
    _APP_NAME = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow")
    _CLASS_NAME = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2")
    _GPU = os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000")
    os.environ["COMFYMODAL_V2_APP_NAME"] = _APP_NAME
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = _CLASS_NAME
    os.environ["COMFYMODAL_V2_GPU"] = _GPU

    WAIT_SECONDS = 25  # >= 6, increased for Modal scaledown scheduling variance
    ASSET_TIMEOUT = 30.0
    ACCEPTANCE_FAILED = False
    runs: list[dict[str, Any]] = []

    def _fmt_ts() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # ── Pre-resolve handle once (async-safe) to avoid AsyncUsageWarning ──
    # The ModalTransport._v2_handle does synchronous Client.from_credentials.
    # Run it in a thread to keep the async context clean.
    print("[v2.acceptance] phase=resolve_handle", flush=True)
    handle = await asyncio.to_thread(transport._v2_handle, workspace=workspace, gpu=_GPU)

    async def _run_acceptance_request(
        label: str, index: int,
    ) -> tuple[dict[str, Any], str]:
        _req_id = f"v2-accept-{label}-{uuid.uuid4().hex[:12]}"
        _t0_wall_ms = int(time.time() * 1000)
        try:
            _command_start_for_origin = int(os.environ.get("COMFYMODAL_COMMAND_START_UNIX_MS", ""))
        except (TypeError, ValueError):
            _command_start_for_origin = _t0_wall_ms
        _t1_wall_ns, _t1_mono_ns = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        request_origin_info = {
            "request_id": _req_id,
            "trigger_source": "acceptance_benchmark",
            "ui_run_triggered_wall_unix_ms": _t0_wall_ms,
            "command_start_unix_ms": _command_start_for_origin,
            "benchmark_run_index": index,
            "local_receive_wall_ns": _t1_wall_ns,
            "local_receive_mono_ns": _t1_mono_ns,
        }
        _ws_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        _norm_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        production_options = normalize_production_options(modal_options)
        _norm_end_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        _rtc_start_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace = RuntimeTrace(request_id=_req_id, process="local")
        runtime_trace.set_metadata(request_origin_info=request_origin_info)
        _rtc_end_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace.emit_at("worker_start",
            wall_unix_ns=_ws_ts[0], monotonic_ns=_ws_ts[1],
            phase="local", metadata={"pid": os.getpid(), "thread_native_id": threading.get_native_id(),
                                     "request_id": _req_id})
        runtime_trace.emit_at("normalize_production_options_start",
            wall_unix_ns=_norm_ts[0], monotonic_ns=_norm_ts[1], phase="local")
        runtime_trace.emit_at("normalize_production_options_end",
            wall_unix_ns=_norm_end_ts[0], monotonic_ns=_norm_end_ts[1], phase="local")
        runtime_trace.emit_at("runtime_trace_construct_start",
            wall_unix_ns=_rtc_start_ts[0], monotonic_ns=_rtc_start_ts[1], phase="local")
        runtime_trace.emit_at("trace_construct_end",
            wall_unix_ns=_rtc_end_ts[0], monotonic_ns=_rtc_end_ts[1], phase="local")
        _bc_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace.emit_at("benchmark_options_copy_start",
            wall_unix_ns=_bc_ts[0], monotonic_ns=_bc_ts[1], phase="local")
        _bench_modal_options = dict(modal_options)
        _bc_end_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace.emit_at("benchmark_options_copy_end",
            wall_unix_ns=_bc_end_ts[0], monotonic_ns=_bc_end_ts[1], phase="local")
        _cid_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace.emit_at("client_id_generation_start",
            wall_unix_ns=_cid_ts[0], monotonic_ns=_cid_ts[1], phase="local")
        _bench_client_id = f"v2-accept-client-{uuid.uuid4().hex[:8]}"
        _cid_end_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace.emit_at("client_id_generation_end",
            wall_unix_ns=_cid_end_ts[0], monotonic_ns=_cid_end_ts[1], phase="local")
        _bep_call_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace.emit_at("build_execution_plan_call_start",
            wall_unix_ns=_bep_call_ts[0], monotonic_ns=_bep_call_ts[1], phase="local")
        plan = build_execution_plan(
            workflow, prompt_id=_req_id, client_id=_bench_client_id,
            modal_options=_bench_modal_options,
            production_options=production_options if production_options.get("enabled") else None,
            gpu=_GPU, workspace=workspace,
            request_metadata={"benchmark_run_index": index, "benchmark_app": _APP_NAME,
                              "__request_origin_info__": request_origin_info},
            trace=runtime_trace, validate=False,
        )
        _ep_call_wall_ns, _ep_call_mono_ns = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace.emit_at("execute_plan_call_start",
            wall_unix_ns=_ep_call_wall_ns, monotonic_ns=_ep_call_mono_ns, phase="local")
        started = time.perf_counter()
        print(f"[v2.acceptance] phase=execute_plan label={label}", flush=True)
        result = await execute_plan(
            plan, transport=transport,
            restore_publisher=RemoteRestorePlanPublisher(transport, workspace),
            profile_setter=set_active_warmup_profile,
            profile_checker=check_active_warmup_profile,
            gpu=_GPU, workspace=workspace, trace=runtime_trace,
        )
        _validate_remote_profile(result)
        _response_wall_ns, _response_mono_ns = _capture_ts()
        wall_ms = (time.perf_counter() - started) * 1000.0

        # Extract identity from REQUEST-SCOPED trace events
        identity = _extract_identity_from_trace(result, _req_id)
        runtime_shape_artifact = _validate_runtime_shape(result, identity)
        instance_id = identity.get("restored_instance_id", "")

        # Extract images
        images = _extract_images(result)
        asset_proofs: list[dict[str, Any]] = []
        for img in images:
            _aid = str(img.get("asset_id", ""))
            _backend = str(img.get("backend_path", ""))
            if not _aid and not _backend:
                continue
            _path = _backend or f"output_assets/{_aid}{img.get('file_ext', '.png')}"
            _expected_sha = _aid
            try:
                proof = await _read_remote_asset(handle, _path, _expected_sha, timeout=ASSET_TIMEOUT)
                asset_proofs.append(proof)
                print(f"[v2.acceptance] asset_fetched label={label} "
                      f"sha={_expected_sha[:16]} ms={proof['fetch_ms']}", flush=True)
            except Exception as exc:
                asset_proofs.append({"backend_path": _path, "expected_sha256": _expected_sha,
                                     "error": str(exc)[:200]})
                print(f"[v2.acceptance] asset_fetch_failed label={label} "
                      f"sha={_expected_sha[:16]} error={str(exc)[:100]}", flush=True)

        # Timing: scoped to current request_id
        trigger_to_modal_entry_ms = None
        for ev in result.get("trace", {}).get("events", []):
            if isinstance(ev, dict) and ev.get("name") == "remote_method_entry":
                meta = ev.get("metadata", {})
                if isinstance(meta, dict) and meta.get("request_id") == _req_id:
                    # Compute from local origin timestamps
                    # Use local_receive to first remote event from request_origin_info
                    pass
        # Fallback: use wall clock delta
        trigger_to_modal_entry_ms = round((time.time() * 1000 - _t0_wall_ms), 3)

        timing = _extract_acceptance_timing_scoped(
            result, _req_id,
            trigger_to_modal_entry_ms=trigger_to_modal_entry_ms,
            wall_ms=wall_ms,
        )
        # Update asset_fetch_ms after asset fetch: use max individual fetch time
        # or total if available.  Use total of all proof fetch latencies.
        _total_fetch_ms = sum(p.get("fetch_ms", 0) or 0 for p in asset_proofs)
        if _total_fetch_ms > 0:
            timing["asset_fetch_ms"] = round(_total_fetch_ms, 3)

        artifact = {
            "label": label,
            "run_index": index,
            "timestamp": _fmt_ts(),
            "identity": identity,
            "runtime_shape": runtime_shape_artifact,
            "images": images,
            "asset_proofs": asset_proofs,
            "timing": timing,
            "wall_ms": round(wall_ms, 1),
            "result": result,  # Include full remote result for event inspection
        }
        _waterfall = build_waterfall(
            result=result,
            timing=timing,
            wall_ms=wall_ms,
            command_start_unix_ms=_t0_wall_ms,
            response_received_unix_ns=_response_wall_ns,
            run_label=f"run {label}",
        )
        artifact["waterfall"] = waterfall_to_dict(_waterfall)
        (output_dir / f"run_{label}.json").write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        print(render_waterfall(_waterfall), flush=True)
        return artifact, _req_id

    # ══════════════════════════════════════════════════════════════════════
    # A: Fresh restored request + asset fetch
    # ══════════════════════════════════════════════════════════════════════
    print("[v2.acceptance] phase=A fresh_restored_start", flush=True)
    run_a, req_a_id = await _run_acceptance_request("A", 0)
    a_identity = run_a["identity"]
    a_instance_id = a_identity.get("restored_instance_id", "")
    a_checks = _check_acceptance(
        "A", run_a, run_a["timing"], run_a["images"], run_a["asset_proofs"],
        is_fresh=True, expected_restore_count=1, expected_request_count=1,
    )
    run_a["acceptance_checks"] = {"pass": len(a_checks) == 0, "failures": a_checks}
    if a_checks:
        print(f"[v2.acceptance] A failures: {a_checks}", flush=True)
        ACCEPTANCE_FAILED = True
    else:
        print(f"[v2.acceptance] A PASS instance={a_instance_id}", flush=True)
    runs.append(run_a)

    # ══════════════════════════════════════════════════════════════════════
    # B: IMMEDIATE second request (no wait, no cache clear)
    # ══════════════════════════════════════════════════════════════════════
    print("[v2.acceptance] phase=B immediate_reuse_start", flush=True)
    run_b, req_b_id = await _run_acceptance_request("B", 1)
    b_identity = run_b["identity"]
    b_instance_id = b_identity.get("restored_instance_id", "")

    b_placed_elsewhere = False
    if b_instance_id and a_instance_id and b_instance_id != a_instance_id:
        b_placed_elsewhere = True
        print(f"[v2.acceptance] B placed elsewhere instance={b_instance_id} "
              f"!= A instance={a_instance_id} — recording failure, allowing one retry", flush=True)
        print("[v2.acceptance] phase=B_retry_start", flush=True)
        run_b_retry, _ = await _run_acceptance_request("B_retry", 2)
        b_retry_instance = run_b_retry["identity"].get("restored_instance_id", "")
        b_retry_failures = _check_acceptance(
            "B_retry", run_b_retry, run_b_retry["timing"],
            run_b_retry["images"], run_b_retry["asset_proofs"],
            is_reused=True, expected_instance_id=a_instance_id,
            expected_request_count_min=2,
        )
        run_b_retry["acceptance_checks"] = {"pass": len(b_retry_failures) == 0, "failures": b_retry_failures}
        run_b["was_placed_elsewhere"] = True
        run_b["retry_attempt"] = run_b_retry
        runs.append(run_b)
        runs.append(run_b_retry)
        if not b_retry_failures:
            print(f"[v2.acceptance] B_retry PASS instance={b_retry_instance}", flush=True)
        else:
            ACCEPTANCE_FAILED = True
            print(f"[v2.acceptance] B_retry failures: {b_retry_failures}", flush=True)
    else:
        b_checks = _check_acceptance(
            "B", run_b, run_b["timing"], run_b["images"], run_b["asset_proofs"],
            is_reused=True, expected_instance_id=a_instance_id,
            expected_request_count_min=2,
        )
        run_b["acceptance_checks"] = {"pass": len(b_checks) == 0, "failures": b_checks}
        if b_checks:
            print(f"[v2.acceptance] B failures: {b_checks}", flush=True)
            ACCEPTANCE_FAILED = True
        else:
            print(f"[v2.acceptance] B PASS instance={b_instance_id}", flush=True)
        runs.append(run_b)

    # ══════════════════════════════════════════════════════════════════════
    # Wait >= 6 seconds
    # ══════════════════════════════════════════════════════════════════════
    print(f"[v2.acceptance] phase=wait seconds={WAIT_SECONDS}", flush=True)
    await asyncio.sleep(WAIT_SECONDS)

    # ══════════════════════════════════════════════════════════════════════
    # C: Another fresh restored request + asset fetch
    # ══════════════════════════════════════════════════════════════════════
    print("[v2.acceptance] phase=C fresh_restored_start", flush=True)
    run_c, req_c_id = await _run_acceptance_request("C", 3)
    c_instance_id = run_c["identity"].get("restored_instance_id", "")
    c_checks = _check_acceptance(
        "C", run_c, run_c["timing"], run_c["images"], run_c["asset_proofs"],
        is_fresh=True, expected_restore_count=1, expected_request_count=1,
        forbid_instance_id=a_instance_id,
    )
    run_c["acceptance_checks"] = {"pass": len(c_checks) == 0, "failures": c_checks}
    if c_checks:
        print(f"[v2.acceptance] C failures: {c_checks}", flush=True)
        ACCEPTANCE_FAILED = True
    else:
        print(f"[v2.acceptance] C PASS instance={c_instance_id}", flush=True)
    runs.append(run_c)

    # ══════════════════════════════════════════════════════════════════════
    # Summary
    # ══════════════════════════════════════════════════════════════════════
    summary: dict[str, Any] = {
        "mode": "acceptance",
        "app_name": _APP_NAME,
        "class_name": _CLASS_NAME,
        "gpu": _GPU,
        "runtime_shape": {
            "requested": runtime_shape_config().identity_payload(),
            "guard": _runtime_shape_guard(runtime_shape_config().identity_payload()),
        },
        "timestamp": _fmt_ts(),
        "wait_seconds": WAIT_SECONDS,
        "accepted": not ACCEPTANCE_FAILED,
        "runs": [],
    }
    for r in runs:
        entry = {
            "label": r["label"],
            "identity": r["identity"],
            "runtime_shape": r.get("runtime_shape", {}),
            "timing": r["timing"],
            "waterfall": r.get("waterfall", {}),
            "asset_proofs": r["asset_proofs"],
            "acceptance_checks": r.get("acceptance_checks", {}),
        }
        if r.get("was_placed_elsewhere"):
            entry["was_placed_elsewhere"] = True
        summary["runs"].append(entry)

    (output_dir / "acceptance_summary.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    _acceptance_reports = [r["waterfall"] for r in runs if r.get("waterfall")]
    print(json.dumps(summary, default=str, indent=2), flush=True)
    if len(_acceptance_reports) > 1:
        print(render_comparison(_acceptance_reports), flush=True)

    if ACCEPTANCE_FAILED:
        raise RuntimeError("acceptance mode: one or more checks failed")
    return summary


# ═══════════════════════════════════════════════════════════════════════════
# Variance-cold mode
#
# True-cold experiment: one request at a time, a fixed gap between runs, and a
# strict per-run assertion that the run is genuinely cold (not silently reused).
# Cold is proven from the request-scoped ``remote_method_entry`` metadata:
#   * restore_count == 1
#   * request_count == 1
#   * a non-empty restored_instance_id
#   * when available, a fresh container task/instance identity per run
# Warm/reused runs are never relabeled cold; they are preserved as invalid.
# ═══════════════════════════════════════════════════════════════════════════


def _remote_entry_wall_iso(result: dict[str, Any]) -> str:
    """Return ISO timestamp of the remote_method_entry wall clock, if present."""
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    for event in events:
        if not isinstance(event, dict) or event.get("name") != "remote_method_entry":
            continue
        wall_ns = event.get("wall_unix_ns")
        if isinstance(wall_ns, (int, float)) and wall_ns > 0:
            try:
                return datetime.fromtimestamp(wall_ns / 1_000_000_000, tz=timezone.utc).isoformat()
            except (OverflowError, OSError, ValueError):
                return "unavailable"
    return "unavailable"


def _cold_identity_key(identity: dict[str, Any]) -> tuple[str, ...]:
    """Canonical key for "same container/task instance" comparison.

    Uses the most authoritative identity tokens available.  An empty tuple
    means no freshness token could be established (freshness check is skipped,
    never treated as proof of cold).
    """
    candidates = (
        identity.get("container_task_id", ""),
        identity.get("modal_container_id", ""),
        identity.get("container_session_id", ""),
        identity.get("restored_instance_id", ""),
    )
    present = tuple(str(c) for c in candidates if str(c).strip())
    return present


def _validate_cold_identity(
    identity: dict[str, Any],
    *,
    run_index: int,
    pretouch: int,
    prev_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate true cold identity for one variance run.

    Returns a dict with ``cold_valid`` (bool), ``cold`` (bool), and ``failures``
    (list).  ``cold`` is True only when the run is both valid on its own and
    provably fresh relative to *prev_identity*.  Missing identity tokens fail
    explicitly — absence is never treated as cold.
    """
    failures: list[str] = []
    label = f"variance-cold run {run_index} (pretouch={pretouch})"

    restored_instance_id = str(identity.get("restored_instance_id", "") or "")
    try:
        restore_count = int(identity.get("restore_count", -1))
    except (TypeError, ValueError):
        restore_count = -1
    try:
        request_count = int(identity.get("request_count", -1))
    except (TypeError, ValueError):
        request_count = -1

    if not restored_instance_id:
        failures.append(f"{label}: restored_instance_id is empty/absent")
    if restore_count != 1:
        failures.append(f"{label}: restore_count={restore_count}, expected 1")
    if request_count != 1:
        failures.append(f"{label}: request_count={request_count}, expected 1")

    # Freshness relative to the previous run (only when a token is available).
    prev_key = _cold_identity_key(prev_identity or {})
    cur_key = _cold_identity_key(identity)
    freshness_checked = False
    if prev_key and cur_key:
        freshness_checked = True
        if cur_key == prev_key:
            failures.append(
                f"{label}: not fresh — container/task identity identical to "
                f"previous run ({cur_key})"
            )
    elif prev_identity is not None:
        # We have a previous run but cannot establish a freshness token for it
        # or the current run.  That is not proof of cold; flag it as a caveat
        # only when the previous run was itself deemed cold.
        if prev_identity.get("restored_instance_id"):
            failures.append(
                f"{label}: cannot establish freshness token; not provably cold"
            )

    cold = (len(failures) == 0) and (not prev_identity or freshness_checked or _cold_identity_key(identity))
    return {
        "cold_valid": len(failures) == 0,
        "cold": cold and len(failures) == 0,
        "failures": failures,
        "freshness_checked": freshness_checked,
    }


def _variance_origin(index: int, pretouch: int, app_name: str, teardown: str = "full", pin_transfer: int = 0, quiesced_transfer: int = 0) -> dict[str, Any]:
    """Request-origin metadata carrying per-run variance diagnostics.

    These keys travel inside ``__request_origin_info__`` so the remote runtime
    can apply variance diagnostics / ``COMFYMODAL_V2_UNET_PRETOUCH`` /
    ``COMFYMODAL_V2_UNET_QUIESCED_TRANSFER`` without a production default
    being changed.  ``env_profile`` is carried explicitly so the remote
    request-time profile semantics match the submitter.
    """
    return {
        "variance_mode": "cold",
        "variance_pretouch": int(pretouch),
        "minimal_teardown": 1 if teardown == "minimal" else 0,
        "pin_unet_transfer": int(pin_transfer),
        "unet_quiesced_transfer": int(quiesced_transfer),
        "variance_diagnostics": {
            "variance_cold_gap_seconds": VARIANCE_COLD_GAP_SECONDS,
            "benchmark_app": app_name,
            "mode": "variance_cold",
            "quiesced_transfer": int(quiesced_transfer),
        },
        "env_profile": os.environ.get("COMFYMODAL_V2_ENV_PROFILE", "production").strip().lower() or "production",
        "COMFYMODAL_V2_UNET_PRETOUCH": str(int(pretouch)),
        "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": str(int(quiesced_transfer)),
    }


def _resolve_pretouch(cli_value: int | None) -> int:
    """Resolve the UNET pretouch mode from CLI or env.

    Explicit CLI value wins; otherwise ``V2_VARIANCE_PRETOUCH`` is read
    (0 = disabled is the default).  Always returns 0 or 1.
    """
    if cli_value in (0, 1):
        return int(cli_value)
    raw = os.environ.get("V2_VARIANCE_PRETOUCH", "0").strip().lower()
    return 1 if raw in {"1", "true", "yes", "on"} else 0


def _resolve_slow_threshold() -> float:
    """Resolve the ONE fixed slow threshold (ms) used across all conditions.

    Uses the explicit env value when set, else the nonzero default.  A
    non-positive value fails fast rather than silently disabling the
    threshold — the threshold is never auto-derived from condition medians.
    """
    raw = os.environ.get("V2_VARIANCE_SLOW_THRESHOLD_MS", "").strip()
    value = float(raw) if raw else MATRIX_SLOW_THRESHOLD_MS
    if value <= 0:
        raise RuntimeError(
            "variance_matrix: V2_VARIANCE_SLOW_THRESHOLD_MS must be a positive "
            f"value, got {raw!r}; a fixed threshold is required and is never "
            "auto-derived from condition medians"
        )
    return value


def _matrix_origin(index: int, diag: int, pretouch: int, app_name: str, teardown: str = "full", pin_transfer: int = 0, quiesced_transfer: int = 0) -> dict[str, Any]:
    """Request-origin metadata for one matrix attempt.

    Carries the diagnostics and pretouch gates request-scoped so the remote
    runtime (``_apply_request_variance_diagnostics``) applies
    ``COMFYMODAL_V2_VARIANCE_DIAGNOSTICS`` / ``COMFYMODAL_V2_UNET_PRETOUCH`` /
    ``COMFYMODAL_V2_UNET_QUIESCED_TRANSFER`` per request without changing any
    production default.
    """
    return {
        "variance_mode": "cold",
        "variance_pretouch": int(pretouch),
        "minimal_teardown": 1 if teardown == "minimal" else 0,
        "pin_unet_transfer": int(pin_transfer),
        "unet_quiesced_transfer": int(quiesced_transfer),
        "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": str(int(diag)),
        "COMFYMODAL_V2_UNET_PRETOUCH": str(int(pretouch)),
        "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": str(int(quiesced_transfer)),
        "variance_diagnostics": {
            "variance_cold_gap_seconds": VARIANCE_COLD_GAP_SECONDS,
            "benchmark_app": app_name,
            "mode": "variance_matrix",
            "diagnostics": int(diag),
            "pretouch": int(pretouch),
            "quiesced_transfer": int(quiesced_transfer),
        },
        "env_profile": os.environ.get("COMFYMODAL_V2_ENV_PROFILE", "production").strip().lower() or "production",
    }


def _classify_attempt(record: dict[str, Any]) -> str:
    """Classify an attempt into cold / warm_invalid / failed / snapshot_capture.

    A run that never restored (``restore_count == 0``) is a snapshot capture
    and is NEVER counted as a valid cold request.  Absence of identity is
    ``warm_invalid``.  Exceptions are ``failed``.
    """
    if record.get("error"):
        return "failed"
    identity = record.get("identity", {}) or {}
    variance = record.get("variance", {}) or {}
    if variance.get("cold_valid") and variance.get("cold"):
        return "cold"
    try:
        restore_count = int(identity.get("restore_count", -1))
    except (TypeError, ValueError):
        restore_count = -1
    if restore_count == 0:
        return "snapshot_capture"
    return "warm_invalid"


def _slow_flag(value: float | None, threshold_ms: float) -> bool:
    """True only when *value* is a real number above *threshold_ms*."""
    return bool(value is not None and value > threshold_ms)


def _classify_slow(record: dict[str, Any]) -> dict[str, bool]:
    """Fixed slow flags: restore > 3s and UNET activation > 3s.

    These are fixed classifications, independent of any median-derived
    threshold.  UNET activation duration is sourced from the *extracted*
    result/trace metric ``metrics.page_traversal.unet_demand_to_first_forward_ms``
    (and the activation total when present), falling back to the raw
    ``timing.unet_demand_to_first_forward_ms`` only when the trace-derived
    value is absent.  Missing values never become slow.
    """
    timing = record.get("timing", {}) if isinstance(record.get("timing"), dict) else {}
    metrics = record.get("metrics", {}) if isinstance(record.get("metrics"), dict) else {}
    rt = metrics.get("restore", {}) if isinstance(metrics.get("restore"), dict) else {}
    pt = metrics.get("page_traversal", {}) if isinstance(metrics.get("page_traversal"), dict) else {}

    # Restore: prefer the extracted restore metric, fall back to raw timing.
    restore = _num(rt.get("restore_total_ms")) or _num(timing.get("restore_total_ms"))
    # UNET activation: trace-extracted demand->first-forward, then activation
    # total, then raw timing field.
    unet = (
        _num(pt.get("unet_demand_to_first_forward_ms"))
        or _num(pt.get("activation_total_ms"))
        or _num(timing.get("unet_demand_to_first_forward_ms"))
    )
    return {
        "restore_over_3s": _slow_flag(restore, MATRIX_RESTORE_SLOW_MS),
        "unet_activation_over_3s": _slow_flag(unet, MATRIX_UNET_ACTIVATION_SLOW_MS),
    }


async def _run_transfer_ab(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    gap_seconds: float,
    app_name: str,
    class_name: str,
    gpu: str,
    target_per_condition: int,
    max_attempts_per_condition: int,
    teardown: str = "minimal",
    _runner: Any = None,
) -> dict[str, Any]:
    """Interleaved UNET-transfer contention A/B (quiesced transfer diagnostic).

    A = current overlap (early activation runs concurrently with graph
    execution; sampler lane absorbs the tail).  B = quiesced transfer
    (request-scoped ``COMFYMODAL_V2_UNET_QUIESCED_TRANSFER=1``; the request
    waits for the transfer to complete before graph execution begins, and the
    worker samples per-thread CPU deltas during the synchronized transfer).
    Both conditions run with variance diagnostics ON (request-scoped) so the
    synchronized 12.31 GB CPU→GPU transfer is measured identically in A and B.

    Runs are strictly interleaved A,B,A,B,… with *gap_seconds* cold gaps.
    Continues until each condition collects *target_per_condition* valid cold
    runs (restore_count==1 && request_count==1 && fresh identity) or
    *max_attempts_per_condition* attempts.  EVERY attempt is preserved as
    ``attempt_<seq>.json``; a consolidated ``transfer_ab_report.md`` +
    ``summary.json`` are written.
    """
    conditions = (0, 1)  # quiesced_transfer: 0 = A (overlap), 1 = B (quiesced)
    per_cond: dict[int, dict[str, Any]] = {
        q: {"quiesced": q, "attempts": [], "cold_count": 0, "prev_identity": None}
        for q in conditions
    }
    print(
        f"[v2.transfer_ab] mode=start gap={gap_seconds}s "
        f"target={target_per_condition} max_per_cond={max_attempts_per_condition} "
        f"teardown={teardown} app={app_name}",
        flush=True,
    )
    records: list[dict[str, Any]] = []
    total_attempts = 0
    global_seq = 0
    round_robin_idx = 0
    target_met = False

    while total_attempts < max_attempts_per_condition * len(conditions):
        chosen: int | None = None
        for _ in range(len(conditions)):
            q = conditions[round_robin_idx % len(conditions)]
            round_robin_idx += 1
            if per_cond[q]["cold_count"] < target_per_condition and (
                len(per_cond[q]["attempts"]) < max_attempts_per_condition
            ):
                chosen = q
                break
        if chosen is None:
            target_met = True
            break

        quiesced = chosen
        state = per_cond[quiesced]
        total_attempts += 1
        global_seq += 1
        attempt_seq_in_cond = len(state["attempts"])
        label = "A-overlap" if quiesced == 0 else "B-quiesced"
        attempt_id = f"transfer-ab-{label}-{attempt_seq_in_cond}-{global_seq}-{uuid.uuid4().hex[:8]}"
        attempt_file = f"attempt_{global_seq:04d}.json"
        _start_ts = datetime.now(timezone.utc).isoformat()
        origin = _variance_origin(
            global_seq, pretouch=0, app_name=app_name, teardown=teardown,
            pin_transfer=0, quiesced_transfer=quiesced,
        )
        # Both arms measure the synchronized transfer identically (diagnostics
        # request-scoped ON); only the quiesce flag differs.
        origin["variance_mode"] = "transfer_ab"
        origin["COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"] = "1"

        artifact: dict[str, Any] = {}
        try:
            if _runner is not None:
                artifact = await _runner(
                    index=global_seq, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
            else:
                artifact = await _run_one(
                    index=global_seq, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
        except Exception as exc:  # noqa: BLE001
            artifact = {
                "run_index": global_seq, "run_id": attempt_id, "request_id": "",
                "identity": {}, "result": {}, "timing": {},
                "variance": {
                    "quiesced_transfer": quiesced,
                    "teardown_mode": teardown,
                    "cold_valid": False, "cold": False,
                    "failures": [f"run raised: {str(exc)[:300]}"],
                },
                "start_ts": _start_ts, "end_ts": datetime.now(timezone.utc).isoformat(),
                "remote_entry_ts": "unavailable", "mode": "transfer_ab",
                "error": str(exc)[:300],
            }

        identity = artifact.get("identity", {}) or {}
        result = artifact.get("result", {}) if isinstance(artifact.get("result"), dict) else {}
        cold_check = _validate_cold_identity(
            identity, run_index=global_seq, pretouch=0, prev_identity=state["prev_identity"],
        )
        artifact.setdefault("run_id", attempt_id)
        artifact["attempt_id"] = attempt_id
        artifact["attempt_file"] = attempt_file
        artifact["condition_label"] = label
        artifact["quiesced_transfer"] = quiesced
        artifact["mode"] = "transfer_ab"
        artifact["start_ts"] = artifact.get("start_ts") or _start_ts
        artifact["end_ts"] = artifact.get("end_ts") or datetime.now(timezone.utc).isoformat()
        artifact["remote_entry_ts"] = artifact.get("remote_entry_ts") or _remote_entry_wall_iso(result)
        if not artifact.get("error"):
            artifact["variance"] = {
                "quiesced_transfer": quiesced,
                "teardown_mode": teardown,
                "cold_valid": cold_check["cold_valid"],
                "cold": cold_check["cold"],
                "failures": cold_check["failures"],
                "freshness_checked": cold_check["freshness_checked"],
            }
        classification = _classify_attempt(artifact)
        artifact["classification"] = classification
        record = extract_run_metrics(artifact)
        slow_flags = _classify_slow(record)
        artifact["slow_flags"] = slow_flags
        record["slow_flags"] = slow_flags
        record["classification"] = classification
        record["attempt_id"] = attempt_id
        record["attempt_file"] = attempt_file
        record["condition_label"] = label
        record["quiesced_transfer"] = quiesced
        record["attempt_log"] = f"[transfer_ab] cond={label} class={classification}"
        (output_dir / attempt_file).write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )

        records.append(record)
        if classification == "cold":
            state["cold_count"] += 1
            state["prev_identity"] = identity
        print(
            f"[v2.transfer_ab] seq={global_seq} id={attempt_id} cond={label} "
            f"class={classification} cold={state['cold_count']}/{target_per_condition}",
            flush=True,
        )
        if total_attempts < max_attempts_per_condition * len(conditions):
            needs = any(
                per_cond[q]["cold_count"] < target_per_condition
                and len(per_cond[q]["attempts"]) < max_attempts_per_condition
                for q in conditions
            )
            if needs:
                print(f"[v2.transfer_ab] phase=gap seconds={gap_seconds}", flush=True)
                await asyncio.sleep(gap_seconds)

    # ── Summary + handoff report ──────────────────────────────────────
    summary: dict[str, Any] = {
        "mode": "transfer_ab",
        "app_name": app_name,
        "class_name": class_name,
        "gpu": gpu,
        "gap_seconds": gap_seconds,
        "target_per_condition": target_per_condition,
        "max_attempts_per_condition": max_attempts_per_condition,
        "teardown_mode": teardown,
        "total_attempts": total_attempts,
        "conditions": {},
        "records": records,
    }
    for q in conditions:
        _cold = [r for r in records if r.get("quiesced_transfer") == q and r.get("classification") == "cold"]
        _all = [r for r in records if r.get("quiesced_transfer") == q]
        summary["conditions"][str(q)] = {
            "label": "A-overlap" if q == 0 else "B-quiesced",
            "attempts": len(_all),
            "cold_count": len(_cold),
        }
    (output_dir / "summary.json").write_text(
        json.dumps({k: v for k, v in summary.items() if k != "records"}, default=str, indent=2),
        encoding="utf-8",
    )
    _report_md = _render_transfer_ab_report(summary)
    (output_dir / "transfer_ab_report.md").write_text(_report_md, encoding="utf-8")
    print(f"[v2.transfer_ab] report={output_dir / 'transfer_ab_report.md'}", flush=True)
    print(json.dumps({
        "output_dir": str(output_dir),
        "mode": "transfer_ab",
        "total_attempts": total_attempts,
        "per_condition": {str(q): summary["conditions"][str(q)] for q in conditions},
        "target_met": target_met,
    }, default=str), flush=True)
    print(_report_md, flush=True)

    if not target_met:
        raise RuntimeError(
            "transfer_ab: reached the per-condition attempt cap before every "
            f"condition collected {target_per_condition} valid cold runs; "
            f"attempts preserved in {output_dir}"
        )
    return summary


def _render_transfer_ab_report(summary: dict[str, Any]) -> str:
    """Render the consolidated transfer A/B handoff report (markdown)."""
    records = summary.get("records", []) or []
    _lines: list[str] = []
    _lines.append("# V2 UNET-Transfer Contention A/B (overlap vs quiesced)\n")
    _lines.append(
        f"- App: `{summary.get('app_name', '')}` · GPU `{summary.get('gpu', '')}` · "
        f"gap `{summary.get('gap_seconds')}s` · teardown `{summary.get('teardown_mode', '')}`"
    )
    _lines.append(
        f"- A = current overlap (early activation runs concurrently with graph); "
        f"B = quiesced transfer (`COMFYMODAL_V2_UNET_QUIESCED_TRANSFER=1`, graph "
        f"waits for transfer completion). Both arms: variance diagnostics ON, "
        f"minimal teardown, single-use containers.\n"
    )
    _lines.append("| cond | attempt | class | cmd→resp (ms) | transfer queue delay (ms) | sync transfer (ms) | GB/s | restore (ms) | sampler wait (ms) | sampling (ms) | quiesce wait (ms) | graph activity (ms) |")
    _lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in sorted(records, key=lambda x: (x.get("quiesced_transfer", 0), x.get("attempt_id", ""))):
        _metrics = r.get("metrics", {}) if isinstance(r.get("metrics"), dict) else {}
        _t = _metrics.get("transfer", {}) if isinstance(_metrics.get("transfer"), dict) else {}
        _p = _metrics.get("page_traversal", {}) if isinstance(_metrics.get("page_traversal"), dict) else {}
        _rst = _metrics.get("restore", {}) if isinstance(_metrics.get("restore"), dict) else {}
        _sp = _metrics.get("sampler", {}) if isinstance(_metrics.get("sampler"), dict) else {}
        _label = "A" if r.get("quiesced_transfer") == 0 else "B"
        _lines.append(
            f"| {_label} | {r.get('attempt_id', '')} | {r.get('classification', '')} "
            f"| {_fmt_ms(_t.get('command_to_response_ms'))} "
            f"| {_fmt_ms(_t.get('transfer_queue_delay_ms'))} "
            f"| {_fmt_ms(_p.get('cpu_to_gpu_transfer_wall_ms'))} "
            f"| {_fmt_gbps(_p.get('cpu_to_gpu_transfer_gb_per_s'))} "
            f"| {_fmt_ms(_rst.get('restore_total_ms'))} "
            f"| {_fmt_ms(_sp.get('sampler_lane_wait_ms'))} "
            f"| {_fmt_ms(_sp.get('sampling_ms'))} "
            f"| {_fmt_ms(_t.get('quiesce_wait_ms'))} "
            f"| {_fmt_ms(_t.get('graph_activity_ms'))} |"
        )
    _lines.append("")
    for q, cond in (summary.get("conditions", {}) or {}).items():
        _lines.append(
            f"- Condition {q} ({cond.get('label', '')}): {cond.get('cold_count', 0)}/"
            f"{summary.get('target_per_condition', 0)} valid cold, "
            f"{cond.get('attempts', 0)} attempts preserved."
        )
    return "\n".join(_lines)


def _fmt_ms(value: Any) -> str:
    if value is None or value == "unavailable":
        return "–"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "–"


def _fmt_gbps(value: Any) -> str:
    if value is None or value == "unavailable":
        return "–"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "–"


async def _run_region_ab(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    gap_seconds: float,
    region: str,
    app_name: str,
    class_name: str,
    gpu: str,
    target_cold: int,
    max_attempts: int,
    skip_first: int = 2,
    teardown: str = "minimal",
    _runner: Any = None,
) -> dict[str, Any]:
    """Region-pinned cold transfer comparison (one pinned region per run).

    Deployed with ``COMFYMODAL_V2_REGION=<region>`` so every request lands on
    the pinned region pool.  The first *skip_first* attempts of the block are
    EXCLUDED from the valid set unconditionally: attempt 1 is the
    snapshot/cache-build run and attempt 2 is the run that restores the
    freshly-built snapshot — both are "snapshot builders" (the second often
    does not look like one).  Then collects *target_cold* valid cold runs
    (restore_count==1 && request_count==1 && fresh identity), production
    overlap arm (quiesced=0), variance diagnostics ON for the synchronized
    measurement, single-use containers, minimal teardown, 25 s gaps.  Every
    attempt is preserved as ``attempt_<seq>.json``.
    """
    print(
        f"[v2.region_ab] mode=start region={region} gap={gap_seconds}s "
        f"target={target_cold} max={max_attempts} skip_first={skip_first} "
        f"teardown={teardown} app={app_name}",
        flush=True,
    )
    records: list[dict[str, Any]] = []
    prev_identity: dict[str, Any] | None = None
    skipped = 0
    valid_cold = 0
    total_attempts = 0

    while valid_cold < target_cold and total_attempts < max_attempts:
        index = total_attempts
        total_attempts += 1
        _run_id = f"region-ab-{region}-{index}-{uuid.uuid4().hex[:8]}"
        _start_ts = datetime.now(timezone.utc).isoformat()
        origin = _variance_origin(
            index, pretouch=0, app_name=app_name, teardown=teardown,
            pin_transfer=0, quiesced_transfer=0,
        )
        origin["variance_mode"] = "region_ab"
        origin["COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"] = "1"
        origin["pinned_region"] = region

        artifact: dict[str, Any] = {}
        try:
            if _runner is not None:
                artifact = await _runner(
                    index=index, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
            else:
                artifact = await _run_one(
                    index=index, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
        except Exception as exc:  # noqa: BLE001
            artifact = {
                "run_index": index, "run_id": _run_id, "request_id": "",
                "identity": {}, "result": {}, "timing": {},
                "variance": {
                    "quiesced_transfer": 0, "teardown_mode": teardown,
                    "cold_valid": False, "cold": False,
                    "failures": [f"run raised: {str(exc)[:300]}"],
                },
                "start_ts": _start_ts, "end_ts": datetime.now(timezone.utc).isoformat(),
                "remote_entry_ts": "unavailable", "mode": "region_ab",
                "error": str(exc)[:300],
            }

        identity = artifact.get("identity", {}) or {}
        result = artifact.get("result", {}) if isinstance(artifact.get("result"), dict) else {}
        cold_check = _validate_cold_identity(
            identity, run_index=index, pretouch=0, prev_identity=prev_identity,
        )
        artifact["run_id"] = _run_id
        artifact["attempt_file"] = f"attempt_{index:04d}.json"
        artifact["pinned_region"] = region
        artifact["region"] = identity.get("region", "")
        artifact["mode"] = "region_ab"
        artifact["start_ts"] = artifact.get("start_ts") or _start_ts
        artifact["end_ts"] = artifact.get("end_ts") or datetime.now(timezone.utc).isoformat()
        artifact["remote_entry_ts"] = artifact.get("remote_entry_ts") or _remote_entry_wall_iso(result)
        artifact["excluded_snapshot_builder"] = index < skip_first
        if not artifact.get("error"):
            artifact["variance"] = {
                "quiesced_transfer": 0,
                "teardown_mode": teardown,
                "cold_valid": cold_check["cold_valid"],
                "cold": cold_check["cold"],
                "failures": cold_check["failures"],
                "freshness_checked": cold_check["freshness_checked"],
            }
        classification = _classify_attempt(artifact)
        artifact["classification"] = classification
        record = extract_run_metrics(artifact)
        record["classification"] = classification
        record["attempt_file"] = artifact["attempt_file"]
        record["pinned_region"] = region
        record["actual_region"] = identity.get("region", "")
        record["excluded_snapshot_builder"] = index < skip_first
        record["attempt_log"] = (
            f"[region_ab] region={region} index={index} class={classification}"
        )
        (output_dir / artifact["attempt_file"]).write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        records.append(record)

        if index < skip_first:
            skipped += 1
            status = "SKIPPED(snapshot-builder)"
        elif cold_check["cold"] and cold_check["cold_valid"]:
            valid_cold += 1
            prev_identity = identity
            status = "COLD"
        else:
            status = "NOT-COLD"
        print(
            f"[v2.region_ab] index={index} id={_run_id} region={region} "
            f"actual={identity.get('region', '?')} status={status} "
            f"valid={valid_cold}/{target_cold}",
            flush=True,
        )
        if total_attempts < max_attempts:
            print(f"[v2.region_ab] phase=gap seconds={gap_seconds}", flush=True)
            await asyncio.sleep(gap_seconds)

    summary: dict[str, Any] = {
        "mode": "region_ab",
        "region": region,
        "app_name": app_name,
        "class_name": class_name,
        "gpu": gpu,
        "gap_seconds": gap_seconds,
        "target_cold": target_cold,
        "max_attempts": max_attempts,
        "skip_first": skip_first,
        "teardown_mode": teardown,
        "total_attempts": total_attempts,
        "skipped_snapshot_builders": skipped,
        "valid_cold": valid_cold,
        "records": records,
    }
    (output_dir / "summary.json").write_text(
        json.dumps({k: v for k, v in summary.items() if k != "records"}, default=str, indent=2),
        encoding="utf-8",
    )
    _report_md = _render_region_ab_report(summary)
    (output_dir / "region_ab_report.md").write_text(_report_md, encoding="utf-8")
    print(f"[v2.region_ab] report={output_dir / 'region_ab_report.md'}", flush=True)
    print(json.dumps({
        "output_dir": str(output_dir),
        "region": region,
        "total_attempts": total_attempts,
        "skipped": skipped,
        "valid_cold": valid_cold,
    }, default=str), flush=True)
    print(_report_md, flush=True)

    if valid_cold < target_cold:
        raise RuntimeError(
            f"region_ab: only {valid_cold}/{target_cold} valid cold runs in "
            f"region {region} after {max_attempts} attempts; attempts preserved "
            f"in {output_dir}"
        )
    return summary


def _render_region_ab_report(summary: dict[str, Any]) -> str:
    """Render the region-pinned cold comparison report (markdown)."""
    records = summary.get("records", []) or []
    _lines: list[str] = []
    _lines.append("# V2 Region-Pinned Transfer Comparison\n")
    _lines.append(
        f"- Pinned region: `{summary.get('region', '')}` · app "
        f"`{summary.get('app_name', '')}` · GPU `{summary.get('gpu', '')}` · "
        f"gap `{summary.get('gap_seconds')}s` · teardown `{summary.get('teardown_mode', '')}`"
    )
    _lines.append(
        f"- Protocol: first {summary.get('skip_first', 2)} attempts excluded "
        f"(snapshot/cache build + the run after); "
        f"{summary.get('valid_cold', 0)}/{summary.get('target_cold', 0)} valid cold "
        f"collected in {summary.get('total_attempts', 0)} attempts; every attempt preserved.\n"
    )
    _lines.append("| attempt | class | actual region | cmd→resp (ms) | pre-python sched (ms) | restore (ms) | tfr queue (ms) | sync tfr (ms) | GB/s | sampler wait (ms) | sampling (ms) |")
    _lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in sorted(records, key=lambda x: x.get("attempt_file", "")):
        _metrics = r.get("metrics", {}) if isinstance(r.get("metrics"), dict) else {}
        _t = _metrics.get("transfer", {}) if isinstance(_metrics.get("transfer"), dict) else {}
        _p = _metrics.get("page_traversal", {}) if isinstance(_metrics.get("page_traversal"), dict) else {}
        _rst = _metrics.get("restore", {}) if isinstance(_metrics.get("restore"), dict) else {}
        _sp = _metrics.get("sampler", {}) if isinstance(_metrics.get("sampler"), dict) else {}
        _tag = "SKIP" if r.get("excluded_snapshot_builder") else r.get("classification", "")
        _lines.append(
            f"| {r.get('attempt_file', '')} | {_tag} | {r.get('actual_region', '?')} "
            f"| {_fmt_ms(_t.get('command_to_response_ms'))} "
            f"| {_fmt_ms(_t.get('pre_python_modal_scheduling_ms'))} "
            f"| {_fmt_ms(_rst.get('restore_total_ms'))} "
            f"| {_fmt_ms(_t.get('transfer_queue_delay_ms'))} "
            f"| {_fmt_ms(_p.get('cpu_to_gpu_transfer_wall_ms'))} "
            f"| {_fmt_gbps(_p.get('cpu_to_gpu_transfer_gb_per_s'))} "
            f"| {_fmt_ms(_sp.get('sampler_lane_wait_ms'))} "
            f"| {_fmt_ms(_sp.get('sampling_ms'))} |"
        )
    _lines.append("")
    return "\n".join(_lines)


def _classify_transfer_speed(transfer_ms: float | None) -> str:
    """Classify a transfer by wall time: FAST <2.5 s, MEDIUM 2.5–5 s, SLOW >5 s."""
    if transfer_ms is None:
        return "NO-DATA"
    if transfer_ms < 2500.0:
        return "FAST"
    if transfer_ms <= 5000.0:
        return "MEDIUM"
    return "SLOW"


def _host_label(record: dict[str, Any]) -> str:
    """Short stable host label for grouping: provider|region|cpu-model."""
    host = record.get("host_diagnostics", {}) if isinstance(record.get("host_diagnostics"), dict) else {}
    cpu = host.get("cpu", {}) if isinstance(host.get("cpu"), dict) else {}
    model = str(cpu.get("model_name", "?"))
    model = " ".join(model.split())[:48]
    provider = str(record.get("provider", "") or host.get("modal_cloud_provider", ""))
    region = str(record.get("region", "") or host.get("modal_region", ""))
    return f"{provider or '?'}|{region or '?'}|{model or '?'}"


async def _run_host_ab(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    gap_seconds: float,
    app_name: str,
    class_name: str,
    gpu: str,
    target_cold: int,
    max_attempts: int,
    skip_first: int = 2,
    teardown: str = "minimal",
    _runner: Any = None,
) -> dict[str, Any]:
    """Unpinned cold-run host-characteristics study.

    Same protocol as the region-pinned comparison but WITHOUT any region pin:
    Modal places each request naturally, so provider / region / host hardware
    vary across attempts.  The first *skip_first* attempts of the block are
    EXCLUDED from the valid set unconditionally (snapshot/cache build + the
    run after).  Then collects *target_cold* valid cold runs
    (restore_count==1 && request_count==1 && fresh identity), production
    overlap arm (quiesced=0), variance diagnostics ON for the synchronized
    measurement, single-use containers, minimal teardown, 25 s gaps.  Every
    attempt is preserved as ``attempt_<seq>.json`` including the remote
    ``host_diagnostics`` (CPU model, NUMA, GPU UUID/PCIe, VM family).
    """
    print(
        f"[v2.host_ab] mode=start gap={gap_seconds}s target={target_cold} "
        f"max={max_attempts} skip_first={skip_first} teardown={teardown} "
        f"app={app_name}",
        flush=True,
    )
    records: list[dict[str, Any]] = []
    prev_identity: dict[str, Any] | None = None
    skipped = 0
    valid_cold = 0
    total_attempts = 0

    while valid_cold < target_cold and total_attempts < max_attempts:
        index = total_attempts
        total_attempts += 1
        _run_id = f"host-ab-{index}-{uuid.uuid4().hex[:8]}"
        _start_ts = datetime.now(timezone.utc).isoformat()
        origin = _variance_origin(
            index, pretouch=0, app_name=app_name, teardown=teardown,
            pin_transfer=0, quiesced_transfer=0,
        )
        origin["variance_mode"] = "host_ab"
        origin["COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"] = "1"

        artifact: dict[str, Any] = {}
        try:
            if _runner is not None:
                artifact = await _runner(
                    index=index, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
            else:
                artifact = await _run_one(
                    index=index, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
        except Exception as exc:  # noqa: BLE001
            artifact = {
                "run_index": index, "run_id": _run_id, "request_id": "",
                "identity": {}, "result": {}, "timing": {},
                "variance": {
                    "quiesced_transfer": 0, "teardown_mode": teardown,
                    "cold_valid": False, "cold": False,
                    "failures": [f"run raised: {str(exc)[:300]}"],
                },
                "start_ts": _start_ts, "end_ts": datetime.now(timezone.utc).isoformat(),
                "remote_entry_ts": "unavailable", "mode": "host_ab",
                "error": str(exc)[:300],
            }

        identity = artifact.get("identity", {}) or {}
        result = artifact.get("result", {}) if isinstance(artifact.get("result"), dict) else {}
        cold_check = _validate_cold_identity(
            identity, run_index=index, pretouch=0, prev_identity=prev_identity,
        )
        artifact["run_id"] = _run_id
        artifact["attempt_file"] = f"attempt_{index:04d}.json"
        artifact["region"] = identity.get("region", "")
        artifact["mode"] = "host_ab"
        artifact["start_ts"] = artifact.get("start_ts") or _start_ts
        artifact["end_ts"] = artifact.get("end_ts") or datetime.now(timezone.utc).isoformat()
        artifact["remote_entry_ts"] = artifact.get("remote_entry_ts") or _remote_entry_wall_iso(result)
        artifact["excluded_snapshot_builder"] = index < skip_first
        if not artifact.get("error"):
            artifact["variance"] = {
                "quiesced_transfer": 0,
                "teardown_mode": teardown,
                "cold_valid": cold_check["cold_valid"],
                "cold": cold_check["cold"],
                "failures": cold_check["failures"],
                "freshness_checked": cold_check["freshness_checked"],
            }
        classification = _classify_attempt(artifact)
        artifact["classification"] = classification
        record = extract_run_metrics(artifact)
        record["classification"] = classification
        record["attempt_file"] = artifact["attempt_file"]
        record["provider"] = identity.get("cloud", "")
        record["actual_region"] = identity.get("region", "")
        record["excluded_snapshot_builder"] = index < skip_first
        record["host_diagnostics"] = artifact.get("host_diagnostics", {})
        record["host_label"] = _host_label(record)
        _metrics = record.get("metrics", {}) if isinstance(record.get("metrics"), dict) else {}
        _p = _metrics.get("page_traversal", {}) if isinstance(_metrics.get("page_traversal"), dict) else {}
        _transfer_ms = _p.get("cpu_to_gpu_transfer_wall_ms")
        record["transfer_speed"] = _classify_transfer_speed(_transfer_ms)
        record["transfer_ms"] = _transfer_ms
        record["attempt_log"] = (
            f"[host_ab] index={index} class={classification} "
            f"speed={record['transfer_speed']} host={record['host_label']}"
        )
        (output_dir / artifact["attempt_file"]).write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        records.append(record)

        if index < skip_first:
            skipped += 1
            status = "SKIPPED(snapshot-builder)"
        elif cold_check["cold"] and cold_check["cold_valid"]:
            valid_cold += 1
            prev_identity = identity
            status = "COLD"
        else:
            status = "NOT-COLD"
        print(
            f"[v2.host_ab] index={index} id={_run_id} "
            f"provider={identity.get('cloud', '?')} "
            f"region={identity.get('region', '?')} status={status} "
            f"speed={record['transfer_speed']} valid={valid_cold}/{target_cold}",
            flush=True,
        )
        if total_attempts < max_attempts:
            print(f"[v2.host_ab] phase=gap seconds={gap_seconds}", flush=True)
            await asyncio.sleep(gap_seconds)

    summary: dict[str, Any] = {
        "mode": "host_ab",
        "app_name": app_name,
        "class_name": class_name,
        "gpu": gpu,
        "gap_seconds": gap_seconds,
        "target_cold": target_cold,
        "max_attempts": max_attempts,
        "skip_first": skip_first,
        "teardown_mode": teardown,
        "total_attempts": total_attempts,
        "skipped_snapshot_builders": skipped,
        "valid_cold": valid_cold,
        "records": records,
    }
    (output_dir / "summary.json").write_text(
        json.dumps({k: v for k, v in summary.items() if k != "records"}, default=str, indent=2),
        encoding="utf-8",
    )
    _report_md = _render_host_ab_report(summary)
    (output_dir / "host_ab_report.md").write_text(_report_md, encoding="utf-8")
    print(f"[v2.host_ab] report={output_dir / 'host_ab_report.md'}", flush=True)
    print(json.dumps({
        "output_dir": str(output_dir),
        "total_attempts": total_attempts,
        "skipped": skipped,
        "valid_cold": valid_cold,
    }, default=str), flush=True)
    print(_report_md, flush=True)

    if valid_cold < target_cold:
        raise RuntimeError(
            f"host_ab: only {valid_cold}/{target_cold} valid cold runs in "
            f"{max_attempts} attempts; attempts preserved in {output_dir}"
        )
    return summary


def _render_host_ab_report(summary: dict[str, Any]) -> str:
    """Render the unpinned host-characteristics study report (markdown)."""
    records = summary.get("records", []) or []
    _lines: list[str] = []
    _lines.append("# V2 Host-Characteristics Cold Study\n")
    _lines.append(
        f"- Unpinned placement (no region pin) · app `{summary.get('app_name', '')}` "
        f"· GPU `{summary.get('gpu', '')}` · gap `{summary.get('gap_seconds')}s` "
        f"· teardown `{summary.get('teardown_mode', '')}`"
    )
    _lines.append(
        f"- Protocol: first {summary.get('skip_first', 2)} attempts excluded "
        f"(snapshot/cache build + the run after); "
        f"{summary.get('valid_cold', 0)}/{summary.get('target_cold', 0)} valid cold "
        f"collected in {summary.get('total_attempts', 0)} attempts; every attempt "
        f"preserved.  Transfer speed classes: FAST <2.5 s, MEDIUM 2.5–5 s, SLOW >5 s.\n"
    )
    _lines.append("| attempt | class | provider | region | CPU model | threads | NUMA | PCIe | transfer (ms) | GB/s | speed | restore (ms) | cmd→resp (ms) |")
    _lines.append("|---|---|---|---|---|---|---|---|---:|---:|---|---:|---:|")
    for r in sorted(records, key=lambda x: x.get("attempt_file", "")):
        _metrics = r.get("metrics", {}) if isinstance(r.get("metrics"), dict) else {}
        _t = _metrics.get("transfer", {}) if isinstance(_metrics.get("transfer"), dict) else {}
        _p = _metrics.get("page_traversal", {}) if isinstance(_metrics.get("page_traversal"), dict) else {}
        _rst = _metrics.get("restore", {}) if isinstance(_metrics.get("restore"), dict) else {}
        _host = r.get("host_diagnostics", {}) if isinstance(r.get("host_diagnostics"), dict) else {}
        _cpu = _host.get("cpu", {}) if isinstance(_host.get("cpu"), dict) else {}
        _gpu = _host.get("gpu", {}) if isinstance(_host.get("gpu"), dict) else {}
        _numa = _host.get("numa", {}) if isinstance(_host.get("numa"), dict) else {}
        _model = str(_cpu.get("model_name", "?"))
        _model = " ".join(_model.split())[:44]
        _pcie = ""
        if isinstance(_gpu.get("pcie_link_gen_current"), int) and isinstance(_gpu.get("pcie_link_width_current"), int):
            _pcie = f"PCIe{_gpu['pcie_link_gen_current']} x{_gpu['pcie_link_width_current']}"
        _tag = "SKIP" if r.get("excluded_snapshot_builder") else r.get("classification", "")
        _lines.append(
            f"| {r.get('attempt_file', '')} | {_tag} | {r.get('provider', '?')} "
            f"| {r.get('actual_region', '?')} | {_model} "
            f"| {_cpu.get('threads', '?')} | {('yes' if _numa else 'no')} | {_pcie} "
            f"| {_fmt_ms(_p.get('cpu_to_gpu_transfer_wall_ms'))} "
            f"| {_fmt_gbps(_p.get('cpu_to_gpu_transfer_gb_per_s'))} "
            f"| {r.get('transfer_speed', '?')} "
            f"| {_fmt_ms(_rst.get('restore_total_ms'))} "
            f"| {_fmt_ms(_t.get('command_to_response_ms'))} |"
        )
    _lines.append("")

    # ── By-host summary (valid cold runs only) ──
    _lines.append("## By host (valid cold runs)\n")
    _by_host: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if r.get("excluded_snapshot_builder"):
            continue
        _by_host.setdefault(str(r.get("host_label", "?")), []).append(r)
    _lines.append("| host (provider|region|CPU) | n | transfer ms (median/range) | GB/s (median) | FAST | MEDIUM | SLOW |")
    _lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for _label in sorted(_by_host):
        _group = _by_host[_label]
        _vals = sorted(float(v) for v in (_r.get("transfer_ms") for _r in _group) if isinstance(v, (int, float)))
        _median = _vals[len(_vals) // 2] if _vals else None
        _range = f"{_vals[0]:.0f}–{_vals[-1]:.0f}" if _vals else "?"
        _gb = [float(_r.get("metrics", {}).get("page_traversal", {}).get("cpu_to_gpu_transfer_gb_per_s")) for _r in _group]
        _gb = [g for g in _gb if g == g]
        _gb_med = sorted(_gb)[len(_gb) // 2] if _gb else None
        _n_fast = sum(1 for _r in _group if _r.get("transfer_speed") == "FAST")
        _n_med = sum(1 for _r in _group if _r.get("transfer_speed") == "MEDIUM")
        _n_slow = sum(1 for _r in _group if _r.get("transfer_speed") == "SLOW")
        _lines.append(
            f"| {_label} | {len(_group)} | {_fmt_ms(_median)} ({_range}) "
            f"| {_fmt_gbps(_gb_med)} | {_n_fast} | {_n_med} | {_n_slow} |"
        )
    _lines.append("")

    # ── Host inventory (unique containers) ──
    _lines.append("## Host inventory (unique containers)\n")
    _seen: set[str] = set()
    for r in sorted(records, key=lambda x: x.get("attempt_file", "")):
        _host = r.get("host_diagnostics", {}) if isinstance(r.get("host_diagnostics"), dict) else {}
        _cid = str(_host.get("container_key", "") or _host.get("modal_container_id", ""))
        if not _cid or _cid in _seen:
            continue
        _seen.add(_cid)
        _cpu = _host.get("cpu", {}) if isinstance(_host.get("cpu"), dict) else {}
        _gpu = _host.get("gpu", {}) if isinstance(_host.get("gpu"), dict) else {}
        _vm = _host.get("vm", {}) if isinstance(_host.get("vm"), dict) else {}
        _numa = _host.get("numa", {}) if isinstance(_host.get("numa"), dict) else {}
        _numa_nodes = _numa.get("nodes")
        _numa_txt = "yes"
        if isinstance(_numa_nodes, list):
            _numa_txt = f"yes({len(_numa_nodes)} nodes)"
        elif not _numa:
            _numa_txt = "no"
        _pcie = ""
        if isinstance(_gpu.get("pcie_link_gen_current"), int) and isinstance(_gpu.get("pcie_link_width_current"), int):
            _pcie = f"PCIe{_gpu['pcie_link_gen_current']} x{_gpu['pcie_link_width_current']}"
        _lines.append(
            f"- container `{_cid[:24]}`: provider={_host.get('modal_cloud_provider', '?')} "
            f"region={_host.get('modal_region', '?')} · "
            f"cpu=`{_cpu.get('model_name', '?')}` (family {_cpu.get('cpu_family', '?')}/model "
            f"{_cpu.get('model', '?')}/stepping {_cpu.get('stepping', '?')}, "
            f"{_cpu.get('sockets', '?')} socket(s)/{_cpu.get('cores', '?')} core(s)/"
            f"{_cpu.get('threads', '?')} thread(s)) · kernel={_host.get('kernel', '?')} · "
            f"numa={_numa_txt} · gpu=`{_gpu.get('name', '?')}` "
            f"uuid=`{str(_gpu.get('uuid', '?'))[:24]}` bus={_gpu.get('pci_bus_id', '?')} "
            f"{_pcie} driver={_gpu.get('driver_version', '?')} cuda={_gpu.get('cuda_version', '?')} · "
            f"vm={_vm.get('vm_family', '?')} "
            f"machine={_vm.get('gcp_machine_type', _vm.get('aws_instance_type', '?'))} "
            f"dmi={_vm.get('dmi_product_name', '?')}"
        )
    _lines.append("")
    return "\n".join(_lines)


async def _run_variance_matrix(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    gap_seconds: float,
    app_name: str,
    class_name: str,
    gpu: str,
    target_per_condition: int,
    max_total_attempts: int,
    slow_threshold_ms: float,
    teardown: str = "full",
    pin_transfer: int = 0,
    _runner: Any = None,
) -> dict[str, Any]:
    """Four-condition round-robin cold scheduler.

    Round-robins across (diagnostics off/on) x (pretouch off/on).  Keeps
    attempting each condition until it reaches *target_per_condition* valid
    cold runs or the global attempt cap is hit.  Every attempt — including
    failed, warm/invalid, slow and snapshot-capture runs — is preserved as
    ``attempt_<seq>.json`` with a unique attempt ID and the full result trace.
    Produces one consolidated ``variance_matrix_handoff.md`` + ``summary.json``.
    """
    print(
        f"[v2.variance_matrix] mode=start gap={gap_seconds}s target={target_per_condition} "
        f"max_attempts={max_total_attempts} slow_threshold_ms={slow_threshold_ms} "
        f"teardown={teardown} pin_transfer={pin_transfer} app={app_name}",
        flush=True,
    )
    per_cond: dict[str, dict[str, Any]] = {}
    for diag, pretouch in MATRIX_CONDITIONS:
        label = MATRIX_CONDITION_LABEL(diag, pretouch)
        per_cond[label] = {"diag": diag, "pretouch": pretouch, "attempts": [],
                           "cold_count": 0, "prev_identity": None}

    records: list[dict[str, Any]] = []
    total_attempts = 0
    global_seq = 0
    round_robin_idx = 0
    target_met = False

    while total_attempts < max_total_attempts:
        # ── Round-robin pick the next condition that still needs cold runs ──
        chosen: tuple[int, int] | None = None
        for _ in range(len(MATRIX_CONDITIONS)):
            cond = MATRIX_CONDITIONS[round_robin_idx % len(MATRIX_CONDITIONS)]
            round_robin_idx += 1
            label = MATRIX_CONDITION_LABEL(*cond)
            if per_cond[label]["cold_count"] < target_per_condition:
                chosen = cond
                break
        if chosen is None:
            target_met = True
            break  # every condition has reached its target

        diag, pretouch = chosen
        label = MATRIX_CONDITION_LABEL(diag, pretouch)
        state = per_cond[label]
        total_attempts += 1
        global_seq += 1
        attempt_seq_in_cond = len(state["attempts"])
        attempt_id = f"matrix-{label}-{attempt_seq_in_cond}-{global_seq}-{uuid.uuid4().hex[:8]}"
        attempt_file = f"attempt_{global_seq:04d}.json"
        _start_ts = datetime.now(timezone.utc).isoformat()
        origin = _matrix_origin(global_seq, diag, pretouch, app_name, teardown=teardown, pin_transfer=pin_transfer)

        artifact: dict[str, Any] = {}
        try:
            if _runner is not None:
                artifact = await _runner(
                    index=global_seq, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
            else:
                artifact = await _run_one(
                    index=global_seq, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
        except Exception as exc:  # noqa: BLE001
            artifact = {
                "run_index": global_seq, "run_id": attempt_id, "request_id": "",
                "identity": {}, "result": {}, "timing": {},
                "variance": {"pretouch": pretouch, "pin_transfer": pin_transfer,
                             "teardown_mode": teardown,
                             "cold_valid": False, "cold": False,
                             "failures": [f"run raised: {str(exc)[:300]}"]},
                "start_ts": _start_ts, "end_ts": datetime.now(timezone.utc).isoformat(),
                "remote_entry_ts": "unavailable", "mode": "variance_matrix",
                "error": str(exc)[:300],
            }

        # ── Augment with matrix metadata and write the raw attempt file ──
        identity = artifact.get("identity", {}) or {}
        result = artifact.get("result", {}) if isinstance(artifact.get("result"), dict) else {}
        cold_check = _validate_cold_identity(
            identity, run_index=global_seq, pretouch=pretouch, prev_identity=state["prev_identity"],
        )
        artifact.setdefault("run_id", attempt_id)
        artifact["attempt_id"] = attempt_id
        artifact["attempt_file"] = attempt_file
        artifact["condition_label"] = label
        artifact["diag"] = diag
        artifact["mode"] = "variance_matrix"
        artifact["start_ts"] = artifact.get("start_ts") or _start_ts
        artifact["end_ts"] = artifact.get("end_ts") or datetime.now(timezone.utc).isoformat()
        artifact["remote_entry_ts"] = artifact.get("remote_entry_ts") or _remote_entry_wall_iso(result)
        if not artifact.get("error"):
            artifact["variance"] = {
                "pretouch": pretouch,
                "pin_transfer": pin_transfer,
                "teardown_mode": teardown,
                "cold_valid": cold_check["cold_valid"],
                "cold": cold_check["cold"],
                "failures": cold_check["failures"],
                "freshness_checked": cold_check["freshness_checked"],
            }
        classification = _classify_attempt(artifact)
        artifact["classification"] = classification
        # Extract metrics FIRST so the fixed slow flags can use the trace-derived
        # UNET activation duration (not only raw artifact.timing).
        record = extract_run_metrics(artifact)
        slow_flags = _classify_slow(record)
        artifact["slow_flags"] = slow_flags
        record["slow_flags"] = slow_flags
        record["classification"] = classification
        record["attempt_id"] = attempt_id
        record["attempt_file"] = attempt_file
        record["condition_label"] = label
        record["diag"] = diag
        # Runner logs / stderr are embedded when the runner supplied them;
        # otherwise the full result trace in the attempt JSON is the log.
        artifact["runner_log"] = artifact.get("runner_log", "")
        artifact["attempt_log"] = artifact.get("attempt_log",
                                               f"[matrix] cond={label} class={classification}")
        record["attempt_log"] = artifact["attempt_log"]
        (output_dir / attempt_file).write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )

        records.append(record)

        if classification == "cold":
            state["cold_count"] += 1
            state["prev_identity"] = identity
        print(
            f"[v2.variance_matrix] seq={global_seq} id={attempt_id} cond={label} "
            f"class={classification} cold={state['cold_count']}/{target_per_condition}",
            flush=True,
        )

        if total_attempts < max_total_attempts:
            needs = any(
                per_cond[MATRIX_CONDITION_LABEL(*c)]["cold_count"] < target_per_condition
                for c in MATRIX_CONDITIONS
            )
            if needs:
                print(f"[v2.variance_matrix] phase=gap seconds={gap_seconds}", flush=True)
                await asyncio.sleep(gap_seconds)

    meta = {
        "mode": "variance_matrix",
        "app_name": app_name,
        "class_name": class_name,
        "gpu": gpu,
        "gap_seconds": gap_seconds,
        "target_per_condition": target_per_condition,
        "max_total_attempts": max_total_attempts,
        "slow_threshold_ms": slow_threshold_ms,
        "teardown_mode": teardown,
    }
    summary = build_matrix_summary(
        records, MATRIX_CONDITIONS, meta=meta, slow_threshold_ms=slow_threshold_ms,
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    handoff = render_matrix_report(summary, output_dir)
    (output_dir / "variance_matrix_handoff.md").write_text(handoff, encoding="utf-8")
    print(json.dumps({
        "output_dir": str(output_dir),
        "mode": "variance_matrix",
        "total_attempts": summary["total_attempts"],
        "total_cold": summary["total_cold"],
        "target_per_condition": target_per_condition,
        "target_met": target_met,
        "per_condition_cold": {k: p["cold_count"] for k, p in summary["per_condition"].items()},
    }, default=str), flush=True)

    if not target_met:
        raise RuntimeError(
            "variance_matrix: reached the total-attempt cap before every condition "
            f"collected {target_per_condition} valid cold runs; attempts preserved in "
            f"{output_dir}"
        )
    return summary


async def _run_variance_cold(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    run_count: int,
    gap_seconds: float,
    pretouch: int,
    app_name: str,
    class_name: str,
    gpu: str,
    teardown: str = "full",
    pin_transfer: int = 0,
    quiesced_transfer: int = 0,
    _runner: Any = None,
) -> dict[str, Any]:
    """Run the variance-cold sequence: one request at a time with a gap.

    Every run artifact (including slow/invalid runs) is preserved with run ID,
    mode, identity, provider/region/image/task/container IDs, runtime
    fingerprint/thread counts, exact timestamps, and the full result trace.
    Produces ``summary.json`` and ``variance_cold_report.md``.
    """
    print(
        f"[v2.variance_cold] mode=start runs={run_count} gap={gap_seconds}s "
        f"pretouch={pretouch} teardown={teardown} pin_transfer={pin_transfer} app={app_name}",
        flush=True,
    )
    records: list[dict[str, Any]] = []
    prev_identity: dict[str, Any] | None = None

    for index in range(run_count):
        _run_id = f"variance-cold-p{pretouch}-{index}-{uuid.uuid4().hex[:8]}"
        _start_ts = datetime.now(timezone.utc).isoformat()
        origin = _variance_origin(index, pretouch, app_name, teardown=teardown, pin_transfer=pin_transfer, quiesced_transfer=quiesced_transfer)

        artifact: dict[str, Any] = {}
        try:
            if _runner is not None:
                artifact = await _runner(
                    index=index,
                    workflow=workflow,
                    modal_options=modal_options,
                    workspace=workspace,
                    transport=transport,
                    output_dir=output_dir,
                    _extra_origin=origin,
                    _defer_waterfall=True,
                )
            else:
                artifact = await _run_one(
                    index=index,
                    workflow=workflow,
                    modal_options=modal_options,
                    workspace=workspace,
                    transport=transport,
                    output_dir=output_dir,
                    _extra_origin=origin,
                    _defer_waterfall=True,
                )
        except Exception as exc:  # noqa: BLE001
            artifact = {
                "run_index": index,
                "run_id": _run_id,
                "request_id": "",
                "identity": {},
                "result": {},
                "timing": {},
                "variance": {
                    "pretouch": pretouch,
                    "pin_transfer": pin_transfer,
                    "teardown_mode": teardown,
                    "cold_valid": False,
                    "cold": False,
                    "failures": [f"run raised: {str(exc)[:300]}"],
                },
                "start_ts": _start_ts,
                "end_ts": datetime.now(timezone.utc).isoformat(),
                "remote_entry_ts": "unavailable",
                "mode": "variance_cold",
                "error": str(exc)[:300],
            }
            # Preserve failed/invalid runs in artifacts.
            (output_dir / f"run_{index}.json").write_text(
                json.dumps(artifact, default=str, indent=2), encoding="utf-8"
            )
            records.append(extract_run_metrics(artifact))
            print(f"[v2.variance_cold] run={index} ERROR {str(exc)[:200]}", flush=True)
            prev_identity = None
            if index + 1 < run_count:
                await asyncio.sleep(gap_seconds)
            continue

        identity = artifact.get("identity", {}) or {}
        cold_check = _validate_cold_identity(
            identity, run_index=index, pretouch=pretouch, prev_identity=prev_identity,
        )
        result = artifact.get("result", {}) if isinstance(artifact.get("result"), dict) else {}
        artifact["run_id"] = _run_id
        artifact["mode"] = "variance_cold"
        artifact["start_ts"] = _start_ts
        artifact["end_ts"] = datetime.now(timezone.utc).isoformat()
        artifact["remote_entry_ts"] = _remote_entry_wall_iso(result)
        artifact["variance"] = {
            "pretouch": pretouch,
            "pin_transfer": pin_transfer,
            "teardown_mode": teardown,
            "cold_valid": cold_check["cold_valid"],
            "cold": cold_check["cold"],
            "failures": cold_check["failures"],
            "freshness_checked": cold_check["freshness_checked"],
        }
        # Re-write the augmented artifact (run_<index>.json was written by _run_one).
        (output_dir / f"run_{index}.json").write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        records.append(extract_run_metrics(artifact))

        status = "COLD" if cold_check["cold"] else "NOT-COLD"
        print(
            f"[v2.variance_cold] run={index} id={_run_id} status={status} "
            f"instance={identity.get('restored_instance_id', '')[:12]} "
            f"task={identity.get('container_task_id', '')[:16]}",
            flush=True,
        )
        if cold_check["failures"]:
            print(f"[v2.variance_cold] run={index} failures={cold_check['failures']}", flush=True)

        # Freshness baseline for the next run: only advance when this run was
        # cold so a warm run never becomes the "previous" baseline.
        if cold_check["cold"]:
            prev_identity = identity

        if index + 1 < run_count:
            print(f"[v2.variance_cold] phase=gap seconds={gap_seconds}", flush=True)
            await asyncio.sleep(gap_seconds)

    meta = {
        "mode": "variance_cold",
        "app_name": app_name,
        "class_name": class_name,
        "gpu": gpu,
        "run_count": run_count,
        "gap_seconds": gap_seconds,
        "pretouch": pretouch,
        "teardown_mode": teardown,
        "slow_threshold_ms": float(os.environ.get("V2_VARIANCE_SLOW_THRESHOLD_MS", "0") or 0),
    }
    summary = build_summary(records, meta=meta)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    report_md = render_variance_report(summary)
    (output_dir / "variance_cold_report.md").write_text(report_md, encoding="utf-8")
    print(f"[v2.variance_cold] report={output_dir / 'variance_cold_report.md'}", flush=True)
    print(json.dumps({
        "output_dir": str(output_dir),
        "run_count": summary["run_count"],
        "cold_count": summary["cold_count"],
        "warm_or_invalid_count": summary["warm_or_invalid_count"],
        "pretouch": pretouch,
        "root_cause": summary["root_cause"].get("dominant"),
    }, default=str), flush=True)
    print(report_md, flush=True)

    if summary["cold_count"] < run_count:
        raise RuntimeError(
            f"variance_cold: only {summary['cold_count']}/{run_count} runs were "
            "confirmed cold; warm/reused runs are not valid cold evidence"
        )
    return summary


def _report_only_from_dir(output_dir: Path) -> dict[str, Any]:
    """Render a report from an existing artifacts directory without Modal.

    Used when Modal/network is unavailable so the harness/report generator
    remains testable locally.  Also the entry point for offline report
    regeneration from a prior run.

    Detects a variance-cold MATRIX directory (one containing ``attempt_*.json``
    plus a ``summary.json``) and renders the consolidated matrix handoff.  A
    plain variance-cold directory (``run_*.json``) keeps the existing
    ``variance_cold_report.md`` behavior.
    """
    attempt_files = sorted(output_dir.glob("attempt_*.json"))
    if attempt_files and (output_dir / "summary.json").is_file():
        return _report_only_matrix_from_dir(output_dir, attempt_files)

    # ── Variance-cold (run_*.json) path ──
    records = load_runs_from_dir(output_dir)
    meta = {
        "mode": "variance_cold",
        "app_name": os.environ.get("COMFYMODAL_V2_VARIANCE_APP_NAME", VARIANCE_APP_NAME),
        "class_name": CLASS_NAME,
        "gpu": GPU,
        "run_count": len(records),
        "gap_seconds": VARIANCE_COLD_GAP_SECONDS,
        "pretouch": int(os.environ.get("V2_VARIANCE_PRETOUCH", "0") or 0),
        "slow_threshold_ms": float(os.environ.get("V2_VARIANCE_SLOW_THRESHOLD_MS", "0") or 0),
        "limitation": "Report generated offline from existing artifacts; no new Modal "
                      "runs were performed (Modal/network may be unavailable).",
    }
    summary = build_summary(records, meta=meta)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    report_md = render_variance_report(summary)
    (output_dir / "variance_cold_report.md").write_text(report_md, encoding="utf-8")
    print(f"[v2.variance_cold] offline_report={output_dir / 'variance_cold_report.md'}", flush=True)
    print(report_md, flush=True)
    return summary


def _report_only_matrix_from_dir(output_dir: Path, attempt_files: list[Path]) -> dict[str, Any]:
    """Render the consolidated variance-matrix handoff from existing attempt files.

    Loads every ``attempt_*.json``, extracts metrics, builds the matrix summary
    (condition labels taken from the artifacts; fixed slow threshold taken from
    the existing ``summary.json`` or the 60000 ms default), and overwrites
    ``summary.json`` + ``variance_matrix_handoff.md``.
    """
    records: list[dict[str, Any]] = []
    conditions_set: set[tuple[int, int]] = set()
    for f in attempt_files:
        try:
            artifact = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(artifact, dict):
            continue
        rec = extract_run_metrics(artifact)
        rec["classification"] = artifact.get("classification")
        rec["attempt_id"] = artifact.get("attempt_id")
        rec["attempt_file"] = artifact.get("attempt_file") or f.name
        rec["condition_label"] = artifact.get("condition_label")
        diag = artifact.get("diag")
        pretouch = 0
        _var = artifact.get("variance")
        if isinstance(_var, dict):
            try:
                pretouch = int(_var.get("pretouch", 0))
            except (TypeError, ValueError):
                pretouch = 0
        if diag is not None:
            conditions_set.add((int(diag), pretouch))
        records.append(rec)

    conditions = sorted(conditions_set) if conditions_set else list(MATRIX_CONDITIONS)

    # Fixed slow threshold: reuse the existing summary value, else 60000 default.
    slow_threshold_ms = MATRIX_SLOW_THRESHOLD_MS
    try:
        _existing = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
        if isinstance(_existing, dict):
            _t = _existing.get("slow_threshold_ms")
            if _t and float(_t) > 0:
                slow_threshold_ms = float(_t)
    except Exception:  # noqa: BLE001
        pass

    meta = {
        "mode": "variance_matrix",
        "app_name": os.environ.get("COMFYMODAL_V2_VARIANCE_APP_NAME", VARIANCE_APP_NAME),
        "class_name": CLASS_NAME,
        "gpu": GPU,
        "gap_seconds": VARIANCE_COLD_GAP_SECONDS,
        "target_per_condition": MATRIX_TARGET_COLD_PER_CONDITION,
        "slow_threshold_ms": slow_threshold_ms,
        "limitation": "Matrix report generated offline from existing artifacts; "
                      "no new Modal runs were performed.",
    }
    summary = build_matrix_summary(
        records, conditions, meta=meta, slow_threshold_ms=slow_threshold_ms,
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    handoff = render_matrix_report(summary, output_dir)
    (output_dir / "variance_matrix_handoff.md").write_text(handoff, encoding="utf-8")
    print(f"[v2.variance_matrix] offline_report={output_dir / 'variance_matrix_handoff.md'}", flush=True)
    print(json.dumps({
        "output_dir": str(output_dir),
        "mode": "variance_matrix",
        "total_attempts": summary["total_attempts"],
        "total_cold": summary["total_cold"],
        "per_condition_cold": {k: p["cold_count"] for k, p in summary["per_condition"].items()},
    }, default=str), flush=True)
    return summary


async def main(bypass_cpu_snapshot_unet: bool = False, cpu_snapshot_unet_ab: bool = False,
               acceptance: bool = False, variance_cold: bool = False,
               variance_matrix: bool = False, transfer_ab: bool = False,
               region_ab: str | None = None, host_ab: bool = False,
               variance_pretouch: int = 0, report_only: str | None = None,
               gap_seconds: float | None = None, run_count: int | None = None,
               teardown: str = "full", pin_transfer: int = 0,
               quiesced_transfer: int = 0) -> None:
    os.environ.setdefault("COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE", "1")
    os.environ["COMFYMODAL_V2_APP_NAME"] = APP_NAME
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = CLASS_NAME
    os.environ["COMFYMODAL_V2_GPU"] = GPU

    # ── Offline report regeneration (no Modal / network needed) ──────────
    if report_only:
        _report_dir = Path(report_only)
        if not _report_dir.is_absolute():
            _candidate = ROOT.parent.parent / "comfymodal-data" / "benchmarks" / "runs" / report_only
            if _candidate.is_dir():
                _report_dir = _candidate
        if not _report_dir.is_dir():
            raise RuntimeError(f"report-only directory not found: {report_only}")
        _report_only_from_dir(_report_dir)
        return

    requested_shape = runtime_shape_config().identity_payload()
    shape_guard = _runtime_shape_guard(requested_shape)
    print(json.dumps({"runtime_shape": requested_shape, "guard": shape_guard}, sort_keys=True), flush=True)
    workspace = _load_workspace()
    workflow, modal_options = _load_workflow()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = ROOT.parent.parent / "comfymodal-data" / "benchmarks" / "runs" / f"v2_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    transport = ModalTransport()

    # ── Variance-cold mode (explicit opt-in; unique shadow app name) ──────
    if variance_cold:
        _vc_app = os.environ.get("COMFYMODAL_V2_VARIANCE_APP_NAME", VARIANCE_APP_NAME) or VARIANCE_APP_NAME
        os.environ["COMFYMODAL_V2_APP_NAME"] = _vc_app
        _vc_gap = VARIANCE_COLD_GAP_SECONDS if gap_seconds is None else float(gap_seconds)
        _vc_runs = VARIANCE_RUN_COUNT if run_count is None else int(run_count)
        await _run_variance_cold(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
            run_count=_vc_runs, gap_seconds=_vc_gap, pretouch=int(variance_pretouch),
            app_name=_vc_app, class_name=CLASS_NAME, gpu=GPU, teardown=teardown,
            pin_transfer=int(pin_transfer), quiesced_transfer=int(quiesced_transfer),
        )
        return

    # ── Variance-cold MATRIX (four-condition round-robin) ───────────────
    if variance_matrix:
        _vm_app = os.environ.get("COMFYMODAL_V2_VARIANCE_APP_NAME", VARIANCE_APP_NAME) or VARIANCE_APP_NAME
        os.environ["COMFYMODAL_V2_APP_NAME"] = _vm_app
        _vm_gap = VARIANCE_COLD_GAP_SECONDS if gap_seconds is None else float(gap_seconds)
        _target = MATRIX_TARGET_COLD_PER_CONDITION
        _max_attempts = MATRIX_MAX_TOTAL_ATTEMPTS
        if os.environ.get("V2_MATRIX_TARGET_PER_CONDITION"):
            _target = int(os.environ["V2_MATRIX_TARGET_PER_CONDITION"])
        if os.environ.get("V2_MATRIX_MAX_TOTAL_ATTEMPTS"):
            _max_attempts = int(os.environ["V2_MATRIX_MAX_TOTAL_ATTEMPTS"])
        # Fixed slow threshold: nonzero default, or fail fast — never derived.
        _slow = _resolve_slow_threshold()
        await _run_variance_matrix(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
            gap_seconds=_vm_gap, app_name=_vm_app, class_name=CLASS_NAME, gpu=GPU,
            target_per_condition=_target, max_total_attempts=_max_attempts,
            slow_threshold_ms=_slow, teardown=teardown, pin_transfer=int(pin_transfer),
        )
        return

    # ── UNET-transfer contention A/B (interleaved overlap vs quiesced) ──
    if transfer_ab:
        _ta_app = os.environ.get("COMFYMODAL_V2_VARIANCE_APP_NAME", VARIANCE_APP_NAME) or VARIANCE_APP_NAME
        os.environ["COMFYMODAL_V2_APP_NAME"] = _ta_app
        _ta_gap = VARIANCE_COLD_GAP_SECONDS if gap_seconds is None else float(gap_seconds)
        _ta_target = int(os.environ.get("V2_TRANSFER_AB_TARGET_COLD", "10"))
        _ta_max = int(os.environ.get("V2_TRANSFER_AB_MAX_ATTEMPTS_PER_CONDITION", "15"))
        await _run_transfer_ab(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
            gap_seconds=_ta_gap, app_name=_ta_app, class_name=CLASS_NAME, gpu=GPU,
            target_per_condition=_ta_target, max_attempts_per_condition=_ta_max,
            teardown=teardown,
        )
        return

    # ── Host-characteristics cold study (unpinned placement) ────────────
    if host_ab:
        _ha_app = os.environ.get("COMFYMODAL_V2_VARIANCE_APP_NAME", VARIANCE_APP_NAME) or VARIANCE_APP_NAME
        os.environ["COMFYMODAL_V2_APP_NAME"] = _ha_app
        _ha_gap = VARIANCE_COLD_GAP_SECONDS if gap_seconds is None else float(gap_seconds)
        _ha_target = int(os.environ.get("V2_HOST_AB_TARGET_COLD", "12"))
        _ha_max = int(os.environ.get("V2_HOST_AB_MAX_ATTEMPTS", "18"))
        _ha_skip = int(os.environ.get("V2_HOST_AB_SKIP_FIRST", "2"))
        await _run_host_ab(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
            gap_seconds=_ha_gap, app_name=_ha_app,
            class_name=CLASS_NAME, gpu=GPU,
            target_cold=_ha_target, max_attempts=_ha_max, skip_first=_ha_skip,
            teardown=teardown,
        )
        return

    # ── Region-pinned cold comparison (one pinned region per invocation) ──
    if region_ab:
        _ra_app = os.environ.get("COMFYMODAL_V2_VARIANCE_APP_NAME", VARIANCE_APP_NAME) or VARIANCE_APP_NAME
        os.environ["COMFYMODAL_V2_APP_NAME"] = _ra_app
        _ra_region = str(region_ab or os.environ.get("COMFYMODAL_V2_REGION", "") or "").strip()
        if not _ra_region:
            raise RuntimeError(
                "region_ab: no pinned region; pass --region-ab REGION or set "
                "COMFYMODAL_V2_REGION (the deployment must be pinned to the same region)"
            )
        _ra_gap = VARIANCE_COLD_GAP_SECONDS if gap_seconds is None else float(gap_seconds)
        _ra_target = int(os.environ.get("V2_REGION_AB_TARGET_COLD", "10"))
        _ra_max = int(os.environ.get("V2_REGION_AB_MAX_ATTEMPTS", "15"))
        await _run_region_ab(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
            gap_seconds=_ra_gap, region=_ra_region, app_name=_ra_app,
            class_name=CLASS_NAME, gpu=GPU,
            target_cold=_ra_target, max_attempts=_ra_max,
            teardown=teardown,
        )
        return

    if acceptance:
        await _run_acceptance_sequence(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
        )
        return

    if cpu_snapshot_unet_ab:
        await _run_ab_compare(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
        )
        return

    artifacts = []
    for index in range(RUN_COUNT):
        artifacts.append(await _run_one(
            index=index,
            workflow=workflow,
            modal_options=modal_options,
            workspace=workspace,
            transport=transport,
            output_dir=output_dir,
            bypass_cpu_snapshot_unet=bypass_cpu_snapshot_unet,
            _defer_waterfall=(RUN_COUNT == 1),
        ))
        if index + 1 < RUN_COUNT:
            await asyncio.sleep(GAP_SECONDS)
    trace_errors = [
        a for a in artifacts if a.get("_trace_handoff_error")
    ]
    summary = {
        "target": {"app_name": APP_NAME, "class_name": CLASS_NAME, "gpu": GPU},
        "runtime_shape": {
            "requested": requested_shape,
            "guard": shape_guard,
        },
        "run_count": len(artifacts),
        "gap_seconds": GAP_SECONDS,
        "trace_handoff_errors": len(trace_errors),
        "waterfall_runs": sum(1 for item in artifacts if item.get("waterfall")),
        "runs": [{
            "run_index": item["run_index"],
            "request_id": item.get("request_id", item.get("prompt_id", "")),
            "identity": item["identity"],
            "runtime_shape": item.get("runtime_shape", {}),
            "timing": item["timing"],
        } for item in artifacts],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, default=str, indent=2), encoding="utf-8")
    _reports = [item["waterfall"] for item in artifacts if item.get("waterfall")]
    print(json.dumps({"output_dir": str(output_dir), **summary}, default=str, indent=2))
    if len(_reports) == 1:
        print(render_waterfall(_reports[0]), flush=True)
    elif len(_reports) > 1:
        print(render_comparison(_reports), flush=True)

    # Signal failure if any trace handoff failed (run files are preserved)
    if trace_errors:
        error_details = "; ".join(
            f"run_{a['run_index']}: {a['_trace_handoff_error']}"
            for a in trace_errors
        )
        raise RuntimeError(
            f"{len(trace_errors)} trace handoff error(s): {error_details}"
        )


if __name__ == "__main__":
    _parser = argparse.ArgumentParser(description="V2 direct benchmark runner")
    _parser.add_argument(
        "--bypass-cpu-snapshot-unet",
        action="store_true",
        default=False,
        help="Insert diagnostic_bypass_cpu_snapshot_unet=True into compatibility_flags "
             "so the snapshot CLIP serves graph demands but UNET loads "
             "through the original loader (A/B diagnostic mode)",
    )
    _parser.add_argument(
        "--cpu-snapshot-unet-ab",
        action="store_true",
        default=False,
        help="Run A/B comparison: one reuse + one bypass request, compare "
             "unet_runtime_state from trace events, print and save diff "
             "(does not require same remote process)",
    )
    _parser.add_argument(
        "--acceptance",
        action="store_true",
        default=False,
        help="Run explicit acceptance mode: A fresh, B immediate reuse, "
             "C fresh restored. Validates identity, timing, asset proofs, "
             "and acceptance criteria. Exits non-zero on failure.",
    )
    _parser.add_argument(
        "--variance-cold",
        action="store_true",
        default=False,
        help="Run variance-cold mode: one request at a time with a fixed gap, "
             "asserting true cold identity from request-scoped "
             "remote_method_entry (restore_count==1, request_count==1, "
             "nonempty restored_instance_id, fresh container identity). "
             "Opt-in; never the default.",
    )
    _parser.add_argument(
        "--variance-matrix",
        action="store_true",
        default=False,
        help="Run the variance-cold MATRIX: round-robin across four conditions "
             "(diagnostics off/on) x (pretouch off/on), continuing until each "
             "condition collects the target number of valid cold runs. "
             "Preserves every attempt and emits one consolidated handoff report. "
             "Opt-in; never the default.",
    )
    _parser.add_argument(
        "--variance-pretouch",
        type=int,
        choices=(0, 1),
        default=None,
        help="UNET pretouch mode for variance-cold runs: 0=disabled, 1=enabled. "
             "Defaults to env V2_VARIANCE_PRETOUCH (0 when unset).",
    )
    _parser.add_argument(
        "--report-only",
        default=None,
        metavar="DIR",
        help="Render a variance-cold report from an existing artifacts "
             "directory without contacting Modal (offline/testable).",
    )
    _parser.add_argument(
        "--gap-seconds",
        type=float,
        default=None,
        help="Override the inter-run gap (defaults to V2_VARIANCE_COLD_GAP_SECONDS=25).",
    )
    _parser.add_argument(
        "--run-count",
        type=int,
        default=None,
        help="Override the number of variance-cold runs (defaults to V2_VARIANCE_RUN_COUNT).",
    )
    _parser.add_argument(
        "--teardown",
        choices=("full", "minimal"),
        default=os.environ.get("V2_TEARDOWN_MODE", "full").strip().lower() or "full",
        help="Request teardown mode: full (default) or minimal "
             "(COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN; skip unload/cleanup/GC/CUDA). "
             "Defaults to env V2_TEARDOWN_MODE.",
    )
    _parser.add_argument(
        "--pin-transfer",
        type=int,
        choices=(0, 1),
        default=int(os.environ.get("V2_PIN_TRANSFER", "0") or 0),
        help="Pin the CPU-snapshot UNET storages with cudaHostRegister before "
             "the transfer (COMFYMODAL_V2_PIN_UNET_TRANSFER) so the H2D copy "
             "uses the true DMA path: 0=disabled (default), 1=enabled. "
             "Defaults to env V2_PIN_TRANSFER.",
    )
    _parser.add_argument(
        "--quiesced-transfer",
        type=int,
        choices=(0, 1),
        default=int(os.environ.get("V2_QUIESCED_TRANSFER", "0") or 0),
        help="Quiesce the early UNET transfer (request-scoped "
             "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER): the request waits for "
             "the synchronized transfer to complete before graph/prefill "
             "execution begins and samples per-thread CPU deltas during the "
             "transfer. 0=overlap (A, default), 1=quiesced (B). "
             "Defaults to env V2_QUIESCED_TRANSFER.",
    )
    _parser.add_argument(
        "--transfer-ab",
        action="store_true",
        default=False,
        help="Run the interleaved UNET-transfer contention A/B: A (overlap) "
             "and B (quiesced transfer) alternating with 25s cold gaps until "
             "each condition collects 10 valid cold runs (cap 15 attempts "
             "per condition). Preserves every attempt and writes "
             "transfer_ab_report.md.",
    )
    _parser.add_argument(
        "--region-ab",
        default=None,
        metavar="REGION",
        help="Run the region-pinned cold transfer comparison for one pinned "
             "region (e.g. us-east-2 or us-east4; the deployment must be "
             "pinned to the same region via COMFYMODAL_V2_REGION). Excludes "
             "the first 2 attempts (snapshot/cache build + the run after), "
             "then collects 10 valid cold runs (cap 15 attempts). Writes "
             "region_ab_report.md.",
    )
    _parser.add_argument(
        "--host-ab",
        action="store_true",
        default=False,
        help="Run the unpinned host-characteristics cold study: no region pin, "
             "every attempt carries remote host_diagnostics (provider, region, "
             "CPU model/family/stepping, sockets/cores/threads, NUMA, kernel, "
             "GPU UUID/PCI bus/PCIe gen+width, driver/CUDA, VM family). "
             "Excludes the first 2 attempts (snapshot/cache build + the run "
             "after), then collects 12 valid cold runs (cap 18 attempts; "
             "V2_HOST_AB_TARGET_COLD / V2_HOST_AB_MAX_ATTEMPTS / "
             "V2_HOST_AB_SKIP_FIRST). Writes host_ab_report.md.",
    )
    _args = _parser.parse_args()

    _variance_pretouch = _resolve_pretouch(_args.variance_pretouch)

    # --variance-cold / --variance-matrix imply the matching V2_BENCHMARK_MODE
    # semantics; the env mode alone is also honoured by the .bat wrappers.
    _variance_cold = _args.variance_cold or (
        os.environ.get("V2_BENCHMARK_MODE", "").strip().lower() == "variance_cold"
    )
    _variance_matrix = _args.variance_matrix or (
        os.environ.get("V2_BENCHMARK_MODE", "").strip().lower() == "variance_matrix"
    )
    _host_ab = _args.host_ab or (
        os.environ.get("V2_BENCHMARK_MODE", "").strip().lower() == "host_ab"
    )

    asyncio.run(main(
        bypass_cpu_snapshot_unet=_args.bypass_cpu_snapshot_unet,
        cpu_snapshot_unet_ab=_args.cpu_snapshot_unet_ab,
        acceptance=_args.acceptance,
        variance_cold=_variance_cold,
        variance_matrix=_variance_matrix,
        transfer_ab=_args.transfer_ab,
        region_ab=_args.region_ab,
        host_ab=_host_ab,
        variance_pretouch=_variance_pretouch,
        report_only=_args.report_only,
        gap_seconds=_args.gap_seconds,
        run_count=_args.run_count,
        teardown=_args.teardown,
        pin_transfer=int(_args.pin_transfer),
        quiesced_transfer=int(_args.quiesced_transfer),
    ))
