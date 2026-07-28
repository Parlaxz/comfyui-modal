"""Run N fresh-restored requests against the deployed V2 Modal app and report metrics."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_execution import build_execution_plan, execute_plan
from comfymodal_runtime.modal_transport import ModalTransport, HandleCache
from comfymodal_runtime.restore_plan import RemoteRestorePlanPublisher
from comfymodal_runtime.trace import RuntimeTrace
from modal_client import check_active_warmup_profile, set_active_warmup_profile
from production_workflow import normalize_production_options

APP_NAME = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow")
CLASS_NAME = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2")
GPU = os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000")
RUN_COUNT = int(os.environ.get("FRESH_RUN_COUNT", "6"))
GAP_SECONDS = float(os.environ.get("FRESH_GAP_SECONDS", "8"))


def _load_workspace() -> dict[str, Any]:
    workspaces_path = ROOT / ".modal_workspaces.json"
    data = json.loads(workspaces_path.read_text(encoding="utf-8"))
    active_id = data.get("active_workspace_id")
    for ws in data.get("workspaces", []):
        if ws.get("id") == active_id:
            if not ws.get("token_id") or not ws.get("token_secret"):
                raise RuntimeError("active Modal workspace has no credentials")
            return ws
    raise RuntimeError("active Modal workspace was not found")


def _load_workflow() -> tuple[dict[str, Any], dict[str, Any]]:
    workflow_path = ROOT / "latest_benchmark_workflow.json"
    snapshot = json.loads(workflow_path.read_text(encoding="utf-8"))
    payload = snapshot.get("payload", snapshot)
    workflow = payload.get("prompt", payload)
    modal_options = payload.get("modal_options", {})
    if not isinstance(workflow, dict):
        raise RuntimeError("workflow prompt must be an object")
    if not isinstance(modal_options, dict):
        modal_options = {}
    return workflow, modal_options


def _extract_timing(result: dict[str, Any], req_id: str) -> dict[str, Any]:
    timing: dict[str, Any] = {}
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []

    # 1. _restore_timing in result root
    rt = result.get("_restore_timing", {})
    if isinstance(rt, dict):
        for k, v in rt.items():
            if isinstance(v, (int, float)):
                timing[k] = v

    # 2. phase_durations_ms in result root
    pd = result.get("phase_durations_ms", {})
    if isinstance(pd, dict):
        for k, v in pd.items():
            if isinstance(v, (int, float)):
                timing[k] = v

    # 3. intervals_ms in result root
    im = result.get("intervals_ms", {})
    if isinstance(im, dict):
        for k, v in im.items():
            if isinstance(v, (int, float)):
                timing[k] = v

    # 4. local_timing in result root
    lt = result.get("local_timing", {})
    if isinstance(lt, dict):
        for k, v in lt.items():
            if isinstance(v, (int, float)):
                timing[k] = v

    # 5. pre_sampler_structured_report in result root
    psr = result.get("pre_sampler_structured_report", {})
    if isinstance(psr, dict):
        for k, v in psr.items():
            if isinstance(v, (int, float)):
                timing[k] = v

    # 6. Parse trace events for duration pairs (start/end)
    starts: dict[str, float] = {}
    for ev in events:
        if not isinstance(ev, dict):
            continue
        name = ev.get("name", "")
        meta = ev.get("metadata", {})
        ts = ev.get("timestamp", 0)
        if isinstance(meta, dict):
            dur = meta.get("duration_ms")
            if dur is not None and isinstance(dur, (int, float)):
                timing[f"{name}_ms"] = dur

        if name.endswith("_start"):
            key = name[:-6]
            starts[key] = ts
        elif name.endswith("_end"):
            key = name[:-4]
            if key in starts:
                timing[f"{key}_ms"] = ts - starts[key]

    # 7. Look for load_models_gpu_duration explicitly
    for ev in events:
        if isinstance(ev, dict) and ev.get("name") == "load_models_gpu_duration":
            meta = ev.get("metadata", {})
            if isinstance(meta, dict):
                dur = meta.get("duration_ms", meta.get("ms"))
                if dur is not None:
                    timing["unet_load_models_gpu_ms"] = float(dur)

    # 8. Look for prefill_start/prefill_end for CLIP encode
    for ev in events:
        if isinstance(ev, dict) and ev.get("name") == "prefill_start":
            starts["prefill"] = ev.get("timestamp", 0)
        if isinstance(ev, dict) and ev.get("name") == "prefill_end":
            end = ev.get("timestamp", 0)
            if "prefill" in starts and end > starts["prefill"]:
                timing["clip_encode_ms"] = end - starts["prefill"]

    # 9. Look for remote_method_entry to extract restore_total_ms
    for ev in events:
        if isinstance(ev, dict) and ev.get("name") == "remote_method_entry":
            meta = ev.get("metadata", {})
            if isinstance(meta, dict):
                for mk in ("restore_total_ms", "restore_method_ms", "trigger_to_durable_result_ms"):
                    if mk in meta and mk not in timing:
                        timing[mk] = meta[mk]

    return timing


def _extract_identity(result: dict[str, Any], req_id: str) -> dict[str, Any]:
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("name") != "remote_method_entry":
            continue
        meta = ev.get("metadata", {})
        if isinstance(meta, dict) and meta.get("method_name") == "run_plan_stream":
            return {
                "app_name": meta.get("app_name", ""),
                "class_name": meta.get("class_name", ""),
                "gpu": meta.get("gpu", ""),
                "container_session_id": (
                    meta.get("container_session_id")
                    or result.get("container_session_id", "")
                    or trace.get("container_session_id", "")
                ),
                "restored_instance_id": (
                    meta.get("restored_instance_id")
                    or result.get("restored_instance_id", "")
                    or trace.get("restored_instance_id", "")
                ),
                "restore_count": (
                    meta.get("restore_count")
                    or result.get("restore_count", 0)
                    or trace.get("restore_count", 0)
                ),
                "request_count": (
                    meta.get("request_count")
                    or result.get("request_count", 0)
                    or trace.get("request_count", 0)
                ),
            }
    # Fallback
    return {
        "restored_instance_id": str(result.get("restored_instance_id", result.get("container_id", ""))),
    }


async def run_one_fresh(
    transport: ModalTransport,
    workspace: dict[str, Any],
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    run_idx: int,
) -> dict[str, Any]:
    req_id = f"v2-fresh-{run_idx:02d}-{uuid.uuid4().hex[:8]}"
    t0_ms = int(time.time() * 1000)
    t0_ns = int(time.time() * 1_000_000_000)

    production_options = normalize_production_options(modal_options)
    runtime_trace = RuntimeTrace(request_id=req_id, process="local")

    plan = build_execution_plan(
        workflow, prompt_id=req_id,
        client_id=f"v2-fresh-client-{uuid.uuid4().hex[:8]}",
        modal_options=dict(modal_options),
        production_options=production_options if production_options.get("enabled") else None,
        gpu=GPU, workspace=workspace,
        request_metadata={
            "benchmark_run_index": run_idx,
            "benchmark_app": APP_NAME,
            "__request_origin_info__": {
                "request_id": req_id,
                "trigger_source": "fresh_benchmark",
                "ui_run_triggered_wall_unix_ms": t0_ms,
                "local_receive_wall_ns": t0_ns,
            },
        },
        trace=runtime_trace, validate=False,
    )

    started = time.perf_counter()
    result = await execute_plan(
        plan, transport=transport,
        restore_publisher=RemoteRestorePlanPublisher(transport, workspace),
        profile_setter=set_active_warmup_profile,
        profile_checker=check_active_warmup_profile,
        gpu=GPU, workspace=workspace, trace=runtime_trace,
    )
    wall_ms = (time.perf_counter() - started) * 1000.0
    t1_ms = int(time.time() * 1000)

    identity = _extract_identity(result, req_id)
    timing = _extract_timing(result, req_id)
    timing["wall_ms"] = round(wall_ms, 1)
    timing["trigger_to_result_local_ms"] = t1_ms - t0_ms

    return {
        "run_index": run_idx,
        "request_id": req_id,
        "identity": identity,
        "timing": timing,
        "result": result,
    }


async def main() -> None:
    os.environ["COMFYMODAL_V2_APP_NAME"] = APP_NAME
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = CLASS_NAME
    os.environ["COMFYMODAL_V2_GPU"] = GPU

    workspace = _load_workspace()
    workflow, modal_options = _load_workflow()
    transport = ModalTransport()

    print(f"=== Running {RUN_COUNT} fresh-restored requests ===")
    print(f"App: {APP_NAME} | Class: {CLASS_NAME} | GPU: {GPU}")
    print(f"Gap: {GAP_SECONDS}s between requests")
    print()

    results = []
    for i in range(RUN_COUNT):
        print(f"[{i+1}/{RUN_COUNT}] Submitting fresh request...", flush=True)
        run_data = await run_one_fresh(transport, workspace, workflow, modal_options, i)
        results.append(run_data)

        identity = run_data["identity"]
        timing = run_data["timing"]

        def _fmt(v):
            if isinstance(v, (int, float)):
                return f"{v:.1f}"
            return str(v)

        print(f"  Request ID:      {run_data['request_id']}")
        print(f"  Container:       {identity.get('restored_instance_id', 'N/A')}")
        print(f"  Restore count:   {identity.get('restore_count', 'N/A')}")
        print(f"  Request count:   {identity.get('request_count', 'N/A')}")
        # Try to get modal_input_id from trace
        minput_id = "N/A"
        for ev in run_data["result"].get("trace", {}).get("events", []):
            if isinstance(ev, dict) and ev.get("name") == "modal_first_remote_event":
                minput_id = ev.get("metadata", {}).get("modal_input_id", "N/A")
                break
        print(f"  Modal input ID:  {minput_id}")

        print(f"  Restore total:   {_fmt(timing.get('restore_total_ms', timing.get('restore_method_ms', 'N/A')))} ms")
        print(f"  Snapshot restore:{_fmt(timing.get('snapshot_restore_ms', timing.get('restore_method_ms', 'N/A')))} ms")
        print(f"  CLIP encode:     {_fmt(timing.get('clip_encode_ms', timing.get('prefill_ms', 'N/A')))}")
        print(f"  UNET load GPU:   {_fmt(timing.get('unet_load_models_gpu_ms', timing.get('load_models_gpu_duration_ms', 'N/A')))}")
        print(f"  GPU restore:     {_fmt(timing.get('restore_gpu_state_ms', 'N/A'))} ms")
        print(f"  CUDA init:       {_fmt(timing.get('cuda_init_ms', 'N/A'))} ms")
        print(f"  Trigger->durable: {_fmt(timing.get('trigger_to_durable_result_ms', timing.get('trigger_to_result_local_ms', 'N/A')))} ms")
        print(f"  Wall time:       {_fmt(timing.get('wall_ms', timing.get('trigger_to_result_local_ms', 'N/A')))} ms")
        print(f"  Sampling:        {_fmt(timing.get('sampling_ms', 'N/A'))} ms")
        if timing:
            redundant = ('wall_ms', 'trigger_to_result_local_ms')
            print(f"  All timing keys: {sorted(k for k in timing.keys() if k not in redundant)}")

        if i + 1 < RUN_COUNT:
            print(f"  Waiting {GAP_SECONDS}s for container scale-down...")
            await asyncio.sleep(GAP_SECONDS)

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    def _sfmt(v, default="N/A"):
        if isinstance(v, (int, float)):
            return f"{v:.0f}"
        return str(v) if v is not None else default

    for r in results:
        t = r["timing"]
        print(f"Run {r['run_index']:2d} | "
              f"restore={_sfmt(t.get('restore_total_ms'))}ms | "
              f"trigger_to_durable={_sfmt(t.get('trigger_to_durable_result_ms'))}ms | "
              f"container={str(r['identity'].get('restored_instance_id', 'N/A'))[:12]}")

    # Save full results
    output = {
        "mode": "fresh_requests",
        "app_name": APP_NAME,
        "class_name": CLASS_NAME,
        "gpu": GPU,
        "run_count": RUN_COUNT,
        "gap_seconds": GAP_SECONDS,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "runs": results,
    }
    out_path = ROOT / "fresh_requests_results.json"
    out_path.write_text(json.dumps(output, default=str, indent=2), encoding="utf-8")
    print(f"\nFull results saved to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
