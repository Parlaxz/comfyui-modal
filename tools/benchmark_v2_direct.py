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
from modal_client import check_active_warmup_profile, set_active_warmup_profile
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


async def _run_one(
    *,
    index: int,
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
) -> dict[str, Any]:
    # T0: benchmark iteration origin (literal first line)
    _req_id = f"v2-benchmark-{index}-{uuid.uuid4().hex[:12]}"
    _t0_wall_ms = int(time.time() * 1000)
    _t0_perf = time.perf_counter()
    # T1: local receive (this runner is itself the local receiver)
    _t1_wall_ns = int(time.time() * 1_000_000_000)
    _t1_mono_ns = time.monotonic_ns()
    request_origin_info = {
        "request_id": _req_id,
        "trigger_source": "benchmark",
        "ui_run_triggered_wall_unix_ms": _t0_wall_ms,
        "benchmark_run_index": index,
        "local_receive_wall_ns": _t1_wall_ns,
        "local_receive_mono_ns": _t1_mono_ns,
    }
    prompt_id = _req_id  # request_id == prompt_id
    production_options = normalize_production_options(modal_options)
    runtime_trace = RuntimeTrace(request_id=prompt_id, process="local")
    runtime_trace.set_metadata(request_origin_info=request_origin_info)
    plan = build_execution_plan(
        workflow,
        prompt_id=prompt_id,
        client_id=f"v2-benchmark-client-{uuid.uuid4().hex[:8]}",
        modal_options=modal_options,
        production_options=production_options if production_options.get("enabled") else None,
        gpu=GPU,
        workspace=workspace,
        request_metadata={"benchmark_run_index": index, "benchmark_app": APP_NAME,
                          "__request_origin_info__": request_origin_info},
        trace=runtime_trace,
        validate=False,
    )
    started = time.perf_counter()
    result = await execute_plan(
        plan,
        transport=transport,
        restore_publisher=RemoteRestorePlanPublisher(transport, workspace),
        profile_setter=set_active_warmup_profile,
        profile_checker=check_active_warmup_profile,
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


async def main() -> None:
    os.environ["COMFYMODAL_V2_APP_NAME"] = APP_NAME
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = CLASS_NAME
    os.environ["COMFYMODAL_V2_GPU"] = GPU
    workspace = _load_workspace()
    workflow, modal_options = _load_workflow()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = ROOT.parent.parent / "comfymodal-data" / "benchmarks" / "runs" / f"v2_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    transport = ModalTransport()
    artifacts = []
    for index in range(RUN_COUNT):
        artifacts.append(await _run_one(
            index=index,
            workflow=workflow,
            modal_options=modal_options,
            workspace=workspace,
            transport=transport,
            output_dir=output_dir,
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
    asyncio.run(main())
