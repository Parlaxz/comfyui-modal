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
from comfymodal_runtime.modal_transport import ModalTransport
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
    """Return (wall_unix_ns, monotonic_ns) snapshot."""
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


async def main(bypass_cpu_snapshot_unet: bool = False, cpu_snapshot_unet_ab: bool = False) -> None:
    os.environ["COMFYMODAL_V2_APP_NAME"] = APP_NAME
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = CLASS_NAME
    os.environ["COMFYMODAL_V2_GPU"] = GPU
    workspace = _load_workspace()
    workflow, modal_options = _load_workflow()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = ROOT.parent.parent / "comfymodal-data" / "benchmarks" / "runs" / f"v2_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    transport = ModalTransport()

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
    _args = _parser.parse_args()
    asyncio.run(main(
        bypass_cpu_snapshot_unet=_args.bypass_cpu_snapshot_unet,
        cpu_snapshot_unet_ab=_args.cpu_snapshot_unet_ab,
    ))
