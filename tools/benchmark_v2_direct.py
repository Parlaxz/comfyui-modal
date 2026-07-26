from __future__ import annotations

import argparse
import asyncio
import hashlib
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
from comfymodal_runtime.trace import RuntimeTrace
from production_workflow import normalize_production_options


WORKFLOW_PATH = ROOT / "latest_benchmark_workflow.json"
WORKSPACES_PATH = ROOT / ".modal_workspaces.json"
APP_NAME = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow")
CLASS_NAME = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2")
GPU = os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000")
RUN_COUNT = int(os.environ.get("V2_BENCHMARK_RUNS", "3"))
GAP_SECONDS = float(os.environ.get("V2_BENCHMARK_GAP_SECONDS", "20"))
_ABSENT_STR = "absent"


def _load_workspace() -> dict[str, Any]:
    data = json.loads(WORKSPACES_PATH.read_text(encoding="utf-8"))
    active_id = data.get("active_workspace_id")
    for workspace in data.get("workspaces", []):
        if workspace.get("id") == active_id:
            if not workspace.get("token_id") or not workspace.get("token_secret"):
                raise RuntimeError("active Modal workspace has no credentials")
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
                "container_session_id": (
                    metadata.get("container_session_id")
                    or result.get("container_session_id", "")
                    or trace.get("container_session_id", "")
                ),
            }
    metadata = trace.get("metadata", {}) if isinstance(trace, dict) else {}
    return dict(metadata) if isinstance(metadata, dict) else {}


def _timing(result: dict[str, Any], wall_ms: float) -> dict[str, Any]:
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
    # Forward local_timing from result (copied/safe block)
    _local_timing = result.get("local_timing", {}) if isinstance(result, dict) else {}
    if not isinstance(_local_timing, dict):
        _local_timing = {}
    return {
        "wall_ms": round(wall_ms, 1),
        "submit2entry_ms": deltas.get("modal_submit_to_entry_ms", submit2entry_ms),
        "t3b_to_t8_ms": deltas.get("t3b_to_t8", derived.get("t3b_to_t8_ms", validation_to_output_ms)),
        "restore_total_ms": restore.get("restore_total_ms") if isinstance(restore, dict) else None,
        "pre_sampler_ms": derived.get("prompt_start_to_sampler_start_ms", pre_sampler_ms),
        "sampler_ms": derived.get("sampler_ms", sampler_ms),
        "vae_decode_ms": derived.get("vae_decode_ms", deltas.get("vae_decode_ms", vae_decode_ms)),
        "output_collection_ms": deltas.get("output_collection_total_ms", output_collection_ms),
        "local_timing": _local_timing,
    }


def _capture_ts() -> tuple[int, int]:
    """Return (wall_unix_ns, monotonic_ns) snapshot.

    Same-process duration calculations use monotonic_ns exclusively.
    Cross-process correlation uses wall_unix_ns only.
    """
    return (int(time.time() * 1_000_000_000), time.monotonic_ns())


async def _run_one(
    *,
    index: int,
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    bypass_cpu_snapshot_unet: bool = False,
    # Test overrides (injected helpers, not used in production)
    _test_restore_publisher: Any = None,
    _test_profile_setter: Any = None,
    _test_profile_checker: Any = None,
) -> dict[str, Any]:
    # T0: benchmark iteration origin (literal first line)
    _req_id = f"v2-benchmark-{index}-{uuid.uuid4().hex[:12]}"
    _t0_wall_ms = int(time.time() * 1000)
    _t0_perf = time.perf_counter()
    # T1: local receive (this runner is itself the local receiver)
    _t1_wall_ns, _t1_mono_ns = _capture_ts()
    request_origin_info = {
        "request_id": _req_id,
        "trigger_source": "benchmark",
        "ui_run_triggered_wall_unix_ms": _t0_wall_ms,
        "benchmark_run_index": index,
        "local_receive_wall_ns": _t1_wall_ns,
        "local_receive_mono_ns": _t1_mono_ns,
    }
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
    wall_ms = (time.perf_counter() - started) * 1000.0
    identity = _identity(result)
    if identity.get("app_name") and identity.get("app_name") != APP_NAME:
        raise RuntimeError(f"V2 run {index} returned app {identity['app_name']!r}, expected {APP_NAME!r}")
    artifact = {
        "run_index": index,
        "prompt_id": prompt_id,
        "target": {"app_name": APP_NAME, "class_name": CLASS_NAME, "gpu": GPU},
        "identity": identity,
        "event_types": ["result"],
        "timing": _timing(result, wall_ms),
        "result": result,
    }
    (output_dir / f"run_{index}.json").write_text(
        json.dumps(artifact, default=str, indent=2), encoding="utf-8"
    )
    print(json.dumps({"run_index": index, "identity": identity, "timing": artifact["timing"]}, default=str))
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
        # vae=missing_snapshot_output.
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
                    "vae": "missing_snapshot_output",
                }
                for role, expected in _EXPECTED.items():
                    if role in role_decisions:
                        actual = role_decisions[role][0]
                        if actual != expected:
                            failures.append(
                                f"{run_label}: {role} decision={actual!r}, "
                                f"expected={expected!r}"
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
    return {
        "restored_instance_id": instance_id,
        "restore_count": restore_count,
        "request_count": request_count,
        "request_id": request_id,
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
        _t1_wall_ns, _t1_mono_ns = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        request_origin_info = {
            "request_id": _req_id,
            "trigger_source": "acceptance_benchmark",
            "ui_run_triggered_wall_unix_ms": _t0_wall_ms,
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
        wall_ms = (time.perf_counter() - started) * 1000.0

        # Extract identity from REQUEST-SCOPED trace events
        identity = _extract_identity_from_trace(result, _req_id)
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
            "images": images,
            "asset_proofs": asset_proofs,
            "timing": timing,
            "wall_ms": round(wall_ms, 1),
            "result": result,  # Include full remote result for event inspection
        }
        (output_dir / f"run_{label}.json").write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
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
        "timestamp": _fmt_ts(),
        "wait_seconds": WAIT_SECONDS,
        "accepted": not ACCEPTANCE_FAILED,
        "runs": [],
    }
    for r in runs:
        entry = {
            "label": r["label"],
            "identity": r["identity"],
            "timing": r["timing"],
            "asset_proofs": r["asset_proofs"],
            "acceptance_checks": r.get("acceptance_checks", {}),
        }
        if r.get("was_placed_elsewhere"):
            entry["was_placed_elsewhere"] = True
        summary["runs"].append(entry)

    (output_dir / "acceptance_summary.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, default=str, indent=2), flush=True)

    if ACCEPTANCE_FAILED:
        raise RuntimeError("acceptance mode: one or more checks failed")
    return summary


async def main(bypass_cpu_snapshot_unet: bool = False, cpu_snapshot_unet_ab: bool = False,
               acceptance: bool = False) -> None:
    os.environ["COMFYMODAL_V2_APP_NAME"] = APP_NAME
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = CLASS_NAME
    os.environ["COMFYMODAL_V2_GPU"] = GPU
    workspace = _load_workspace()
    workflow, modal_options = _load_workflow()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = ROOT.parent.parent / "comfymodal-data" / "benchmarks" / "runs" / f"v2_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    transport = ModalTransport()

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
        ))
        if index + 1 < RUN_COUNT:
            await asyncio.sleep(GAP_SECONDS)
    summary = {
        "target": {"app_name": APP_NAME, "class_name": CLASS_NAME, "gpu": GPU},
        "run_count": len(artifacts),
        "gap_seconds": GAP_SECONDS,
        "runs": [{"run_index": item["run_index"], "identity": item["identity"], "timing": item["timing"]} for item in artifacts],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, default=str, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), **summary}, default=str, indent=2))


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
    _args = _parser.parse_args()
    asyncio.run(main(
        bypass_cpu_snapshot_unet=_args.bypass_cpu_snapshot_unet,
        cpu_snapshot_unet_ab=_args.cpu_snapshot_unet_ab,
        acceptance=_args.acceptance,
    ))
