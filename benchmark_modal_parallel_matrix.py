#!/usr/bin/env python3
"""
benchmark_modal_parallel_matrix.py

Systematically tests request-start scheduling strategies for ComfyUI x Modal.

Sends per-request scheduler configs under payload["comfymodal_scheduler_test"].

Modes are defined in DEFAULT_MODES.  Run subsets with --modes smoke|focused|all.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib import request


LOCAL_BASE_URL = "http://127.0.0.1:8188"
BENCHMARK_WORKFLOW_ROUTE = f"{LOCAL_BASE_URL}/comfymodal/benchmark/workflow"
LOCAL_PROMPT_ROUTE = f"{LOCAL_BASE_URL}/comfymodal/prompt"
LOCAL_SYSTEM_STATS_ROUTE = f"{LOCAL_BASE_URL}/system_stats"
_BENCHMARK_RUNS_DIRNAME = "parallel"  # subdirectory within external benchmarks/runs

LOCAL_COMFYUI_PROCESS_PATTERN = "ComfyUI\\main.py"
WINDOWS_COMFYUI_PROCESS_NAMES = ("python.exe", "pythonw.exe")

REPO_ROOT = Path(__file__).resolve().parent
OUTER_COMFYUI_ROOT = REPO_ROOT.parents[2]
SAVED_WORKFLOWS_DIR = OUTER_COMFYUI_ROOT / "saved workflows"
DEFAULT_SAVED_WORKFLOW_FILE = SAVED_WORKFLOWS_DIR / "flux_2-klein-9b(2).json"
REDEPLOY_BATCH = OUTER_COMFYUI_ROOT / "redeploy_modal_and_run_comfyui.bat"
COMFYAPP_DEPLOY_TARGET = OUTER_COMFYUI_ROOT / "ComfyUI" / "custom_nodes" / "comfyui-modal" / "comfyapp.py"
EMBEDDED_PYTHON = OUTER_COMFYUI_ROOT / "python_embeded" / "python.exe"
LATEST_BENCHMARK_WORKFLOW_FILE = REPO_ROOT / "latest_benchmark_workflow.json"


DEFAULT_MODES: dict[str, dict] = {
    # ── Smoke set ──────────────────────────────────────────────
    "baseline_current": {
        "enabled": False,
        "mode": "baseline_current",
        "description": "Existing pipeline. No speculative scheduling override.",
    },
    "early_unet_vae": {
        "enabled": True,
        "mode": "early_unet_vae",
        "start_dependency_validation_ms": 0,
        "start_unet_ms": 0,
        "start_vae_ms": 0,
        "start_clip_ms": None,
        "prefetch_clip_encode": False,
        "description": "Speculative UNET+VAE at request start; no CLIP speculation.",
    },
    "max_parallel_all_at_once": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_dependency_validation_ms": 0,
        "start_clip_ms": 0,
        "start_unet_ms": 0,
        "start_vae_ms": 0,
        "prefetch_clip_encode": True,
        "description": "All loads start simultaneously; CLIP encode prefetch after CLIP load.",
    },
    "all_parallel_clip0_unet500": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_dependency_validation_ms": 0,
        "start_clip_ms": 0,
        "start_unet_ms": 500,
        "start_vae_ms": 500,
        "prefetch_clip_encode": True,
        "description": "Parallel with 500ms UNET delay; CLIP encode prefetch after CLIP load.",
    },
    "clip_load_then_unet_and_encode": {
        "enabled": True,
        "mode": "clip_load_then_unet_and_encode",
        "start_dependency_validation_ms": 0,
        "start_clip_ms": 0,
        "start_unet_after_clip_load": True,
        "start_vae_after_clip_load": True,
        "prefetch_clip_encode": True,
        "description": "CLIP serial first; then UNET+VAE+encode all start after CLIP done.",
    },
    "unet_load_then_clip": {
        "enabled": True,
        "mode": "unet_load_then_clip",
        "start_dependency_validation_ms": 0,
        "start_unet_ms": 0,
        "start_vae_ms": 0,
        "start_clip_after_unet_load": True,
        "prefetch_clip_encode": True,
        "description": "UNET+VAE first; CLIP starts after UNET done.",
    },
}

SMOKE_MODES: dict[str, dict] = {k: DEFAULT_MODES[k] for k in [
    "baseline_current", "early_unet_vae", "max_parallel_all_at_once",
    "all_parallel_clip0_unet500", "clip_load_then_unet_and_encode", "unet_load_then_clip",
]}

# ── Focused set: all parallel_matrix delay variants for CLIP-first vs UNET-first ──
FOCUSED_MODES: dict[str, dict] = {
    "baseline_current": {
        "enabled": False,
        "mode": "baseline_current",
        "description": "Existing pipeline.",
    },
    "early_unet_vae": {
        "enabled": True,
        "mode": "early_unet_vae",
        "start_unet_ms": 0, "start_vae_ms": 0,
        "prefetch_clip_encode": False,
        "description": "UNET+VAE at request start; no CLIP speculation.",
    },
    "max_parallel_all_at_once": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_clip_ms": 0, "start_unet_ms": 0, "start_vae_ms": 0,
        "prefetch_clip_encode": True,
        "description": "All loads start simultaneously.",
    },
    "all_parallel_clip0_unet0": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_clip_ms": 0, "start_unet_ms": 0, "start_vae_ms": 0,
        "prefetch_clip_encode": True,
        "description": "CLIP and UNET start together.",
    },
    "all_parallel_clip0_unet100": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_clip_ms": 0, "start_unet_ms": 100, "start_vae_ms": 100,
        "prefetch_clip_encode": True,
        "description": "CLIP gets 100ms head start.",
    },
    "all_parallel_clip0_unet250": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_clip_ms": 0, "start_unet_ms": 250, "start_vae_ms": 250,
        "prefetch_clip_encode": True,
        "description": "CLIP gets 250ms head start.",
    },
    "all_parallel_clip0_unet500": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_clip_ms": 0, "start_unet_ms": 500, "start_vae_ms": 500,
        "prefetch_clip_encode": True,
        "description": "CLIP gets 500ms head start.",
    },
    "all_parallel_clip0_unet750": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_clip_ms": 0, "start_unet_ms": 750, "start_vae_ms": 750,
        "prefetch_clip_encode": True,
        "description": "CLIP gets 750ms head start.",
    },
    "all_parallel_clip0_unet1000": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_clip_ms": 0, "start_unet_ms": 1000, "start_vae_ms": 1000,
        "prefetch_clip_encode": True,
        "description": "CLIP gets 1000ms head start.",
    },
    "all_parallel_clip0_unet1500": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_clip_ms": 0, "start_unet_ms": 1500, "start_vae_ms": 1500,
        "prefetch_clip_encode": True,
        "description": "CLIP gets 1500ms head start.",
    },
    "all_parallel_clip0_unet2000": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_clip_ms": 0, "start_unet_ms": 2000, "start_vae_ms": 2000,
        "prefetch_clip_encode": True,
        "description": "CLIP gets 2000ms head start.",
    },
    "all_parallel_unet0_clip0": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_unet_ms": 0, "start_vae_ms": 0, "start_clip_ms": 0,
        "prefetch_clip_encode": True,
        "description": "UNET and CLIP start together (inverse).",
    },
    "all_parallel_unet0_clip100": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_unet_ms": 0, "start_vae_ms": 0, "start_clip_ms": 100,
        "prefetch_clip_encode": True,
        "description": "UNET gets 100ms head start.",
    },
    "all_parallel_unet0_clip250": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_unet_ms": 0, "start_vae_ms": 0, "start_clip_ms": 250,
        "prefetch_clip_encode": True,
        "description": "UNET gets 250ms head start.",
    },
    "all_parallel_unet0_clip500": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_unet_ms": 0, "start_vae_ms": 0, "start_clip_ms": 500,
        "prefetch_clip_encode": True,
        "description": "UNET gets 500ms head start.",
    },
    "all_parallel_unet0_clip750": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_unet_ms": 0, "start_vae_ms": 0, "start_clip_ms": 750,
        "prefetch_clip_encode": True,
        "description": "UNET gets 750ms head start.",
    },
    "all_parallel_unet0_clip1000": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_unet_ms": 0, "start_vae_ms": 0, "start_clip_ms": 1000,
        "prefetch_clip_encode": True,
        "description": "UNET gets 1000ms head start.",
    },
    "all_parallel_unet0_clip1500": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_unet_ms": 0, "start_vae_ms": 0, "start_clip_ms": 1500,
        "prefetch_clip_encode": True,
        "description": "UNET gets 1500ms head start.",
    },
    "all_parallel_unet0_clip2000": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_unet_ms": 0, "start_vae_ms": 0, "start_clip_ms": 2000,
        "prefetch_clip_encode": True,
        "description": "UNET gets 2000ms head start.",
    },
    "early_unet_vae_clip1000": {
        "enabled": True,
        "mode": "parallel_matrix",
        "start_unet_ms": 0, "start_vae_ms": 0, "start_clip_ms": 1000,
        "prefetch_clip_encode": True,
        "description": "UNET+VAE at 0, CLIP at 1000ms.",
    },
    "clip_load_then_unet_and_encode": {
        "enabled": True,
        "mode": "clip_load_then_unet_and_encode",
        "prefetch_clip_encode": True,
        "description": "CLIP serial first; then UNET+VAE+encode.",
    },
    "unet_load_then_clip": {
        "enabled": True,
        "mode": "unet_load_then_clip",
        "prefetch_clip_encode": True,
        "description": "UNET+VAE first; CLIP after UNET done.",
    },
}

FULL_MODES: dict[str, dict] = {
    "baseline_current": DEFAULT_MODES["baseline_current"],
    "early_unet_vae": DEFAULT_MODES["early_unet_vae"],
    "max_parallel_all_at_once": DEFAULT_MODES["max_parallel_all_at_once"],
}
FULL_MODES.update(FOCUSED_MODES)


def _json_request(url: str, method: str = "GET", payload: dict | None = None, timeout: int = 30) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _json_hash(payload: dict) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_OID, json.dumps(payload, sort_keys=True)))


def _ensure_run_dir() -> Path:
    from local_artifacts import get_benchmark_runs_dir
    run_dir = get_benchmark_runs_dir() / _BENCHMARK_RUNS_DIRNAME / _timestamp()
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _append_log(log_path: Path, message: str) -> None:
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(message.rstrip() + "\n")


def _write_json(path: Path, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _load_latest_snapshot() -> dict:
    if DEFAULT_SAVED_WORKFLOW_FILE.is_file():
        with open(DEFAULT_SAVED_WORKFLOW_FILE, "r", encoding="utf-8") as f:
            workflow = json.load(f)
        if isinstance(workflow, dict) and workflow:
            return {
                "captured_at": time.time(),
                "payload": {"prompt": workflow},
                "source": str(DEFAULT_SAVED_WORKFLOW_FILE),
                "workflow_hash": _json_hash(workflow),
            }

    try:
        response = _json_request(BENCHMARK_WORKFLOW_ROUTE, timeout=5)
        if isinstance(response, dict) and response.get("status") == "ok":
            return response
    except Exception:
        pass

    with open(LATEST_BENCHMARK_WORKFLOW_FILE, "r", encoding="utf-8") as f:
        snapshot = json.load(f)
    if not isinstance(snapshot, dict) or not snapshot:
        raise RuntimeError("latest benchmark workflow snapshot is empty")
    return snapshot


def _list_local_comfyui_pids() -> list[int]:
    if os.name != "nt":
        return []
    ps_script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { ($_.Name -in 'python.exe','pythonw.exe') -and $_.CommandLine -match 'ComfyUI\\\\main.py' } | "
        "Select-Object -ExpandProperty ProcessId | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return []
    raw = (result.stdout or "").strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    if isinstance(parsed, list):
        return [int(pid) for pid in parsed]
    return [int(parsed)]


def _terminate_local_comfyui() -> None:
    pids = _list_local_comfyui_pids()
    for pid in pids:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"Stop-Process -Id {pid}"],
            capture_output=True, text=True, timeout=30,
        )
    if pids:
        time.sleep(5)
    remaining = _list_local_comfyui_pids()
    for pid in remaining:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=30)


def _run_redeploy_batch() -> subprocess.CompletedProcess:
    return subprocess.run(
        ["cmd.exe", "/c", str(REDEPLOY_BATCH)],
        input="\n", capture_output=True, text=True, timeout=1800,
    )


def _run_direct_deploy() -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        ["modal", "deploy", str(COMFYAPP_DEPLOY_TARGET)],
        capture_output=True, text=True, timeout=1800,
        cwd=str(OUTER_COMFYUI_ROOT), env=env,
    )


def _launch_local_comfyui() -> subprocess.Popen:
    return subprocess.Popen(
        [str(EMBEDDED_PYTHON), "-s", "ComfyUI\\main.py", "--windows-standalone-build"],
        cwd=str(OUTER_COMFYUI_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _wait_for_local_health(timeout_s: int = 600) -> None:
    deadline = time.time() + timeout_s
    last_error = ""
    while time.time() < deadline:
        try:
            _json_request(LOCAL_SYSTEM_STATS_ROUTE, timeout=10)
            return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(2)
    raise TimeoutError(f"local ComfyUI health timeout: {last_error}")


def _build_prompt_payload(snapshot: dict, run_label: str, scheduler_config: dict) -> dict:
    payload = dict(snapshot.get("payload") or snapshot)
    payload["client_id"] = f"parallel-benchmark-{run_label}-{uuid.uuid4()}"
    payload["t0_client_press_ms"] = int(time.time() * 1000)
    payload.pop("t0_client_press", None)
    payload.pop("t0_perf_ms", None)
    payload.pop("t0_perf_now_ms", None)

    payload["comfymodal_scheduler_test"] = dict(scheduler_config)
    payload["comfymodal_scheduler_test"]["run_label"] = run_label
    payload["comfymodal_scheduler_test"]["benchmark_client_time_ms"] = payload["t0_client_press_ms"]
    payload["comfymodal_scheduler_test"]["benchmark_script"] = "benchmark_modal_parallel_matrix.py"
    return payload


def _submit_prompt(payload: dict) -> str:
    response = _json_request(LOCAL_PROMPT_ROUTE, method="POST", payload=payload, timeout=30)
    prompt_id = response.get("prompt_id", "")
    if not prompt_id:
        raise RuntimeError(f"missing prompt_id in response: {response}")
    return prompt_id


def _poll_history(prompt_id: str, timeout_s: int = 1800) -> dict:
    deadline = time.time() + timeout_s
    history_url = f"{LOCAL_BASE_URL}/history/{prompt_id}"
    while time.time() < deadline:
        data = _json_request(history_url, timeout=30)
        if isinstance(data, dict) and prompt_id in data:
            entry = data[prompt_id]
            meta = entry.get("meta", {}) if isinstance(entry, dict) else {}
            if meta.get("error"):
                raise RuntimeError(str(meta.get("error")))
            return entry
        time.sleep(2)
    raise TimeoutError(f"history timeout for prompt_id={prompt_id}")


def _extract_trace(history_entry: dict) -> dict:
    meta = history_entry.get("meta", {}) if isinstance(history_entry, dict) else {}
    trace = dict(meta.get("trace", {}) or {})
    restore = meta.get("restore_timing", {})
    if isinstance(restore, dict) and restore:
        trace["restore"] = restore

    scheduler = meta.get("scheduler_trace") or trace.get("scheduler_trace") or trace.get("scheduler") or {}
    if isinstance(scheduler, dict):
        trace["scheduler_trace"] = scheduler
    return trace


def _get_nested(data: dict, path: str, default=None):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _metric(trace: dict, *paths: str):
    for path in paths:
        val = _get_nested(trace, path, None)
        if val is not None:
            return val
    return None


def _flatten_run(mode_name: str, iteration: int, prompt_id: str, wall_ms: float, trace: dict, error: str = "") -> dict:
    scheduler = trace.get("scheduler_trace") if isinstance(trace.get("scheduler_trace"), dict) else {}
    deltas = trace.get("deltas_ms") if isinstance(trace.get("deltas_ms"), dict) else {}
    restore = trace.get("restore") if isinstance(trace.get("restore"), dict) else {}

    return {
        "mode": mode_name,
        "iteration": iteration,
        "prompt_id": prompt_id,
        "status": "error" if error else "ok",
        "error": error,
        "wall_ms": round(wall_ms, 1) if wall_ms else None,

        "modal_to_return_ms": deltas.get("modal_to_return"),
        "modal_to_browser_ms": deltas.get("modal_to_browser"),
        "prompt_start_to_sampler_start_ms": deltas.get("prompt_start_to_sampler_start"),
        "sampler_ms": deltas.get("sampler"),
        "sampler_end_to_outputs_collected_ms": deltas.get("sampler_end_to_outputs_collected"),
        "total_input_execution_ms": deltas.get("total_input_execution"),
        "output_collection_total_ms": deltas.get("output_collection_total"),
        "clip_load_ms": deltas.get("clip_load"),
        "clip_encode_ms": deltas.get("clip_encode"),
        "unet_load_ms": deltas.get("unet_load"),
        "vae_load_ms": deltas.get("vae_load"),
        "vae_decode_ms": deltas.get("vae_decode"),
        "graph_overhead_ms": deltas.get("graph_overhead"),

        "restore_total_ms": restore.get("restore_total_ms"),
        "warmup_preload_ms": restore.get("warmup_preload_ms"),
        "custom_nodes_sync_ms": restore.get("custom_nodes_sync_ms"),
        "custom_nodes_created": restore.get("custom_nodes_created"),

        # Scheduler fields
        "scheduler_enabled": scheduler.get("enabled"),
        "scheduler_mode": scheduler.get("mode"),
        "dependency_gate_done_ms": scheduler.get("dependency_gate_done_ms"),
        "missing_node_gate_done_ms": scheduler.get("missing_node_gate_done_ms"),
        "unet_scheduled_start_ms": scheduler.get("unet_scheduled_start_ms"),
        "unet_start_ms": scheduler.get("unet_start_ms"),
        "unet_ready_ms": scheduler.get("unet_ready_ms"),
        "unet_load_wall_ms": scheduler.get("unet_load_wall_ms"),
        "unet_size_gb": scheduler.get("unet_size_gb"),
        "unet_gbps": scheduler.get("unet_gbps"),
        "vae_scheduled_start_ms": scheduler.get("vae_scheduled_start_ms"),
        "vae_start_ms": scheduler.get("vae_start_ms"),
        "vae_ready_ms": scheduler.get("vae_ready_ms"),
        "vae_load_wall_ms": scheduler.get("vae_load_wall_ms"),
        "vae_size_gb": scheduler.get("vae_size_gb"),
        "vae_gbps": scheduler.get("vae_gbps"),
        "clip_scheduled_start_ms": scheduler.get("clip_scheduled_start_ms"),
        "clip_start_ms": scheduler.get("clip_start_ms"),
        "clip_ready_ms": scheduler.get("clip_ready_ms"),
        "clip_load_wall_ms": scheduler.get("clip_load_wall_ms"),
        "clip_size_gb": scheduler.get("clip_size_gb"),
        "clip_gbps": scheduler.get("clip_gbps"),
        "clip_encode_start_ms": scheduler.get("clip_encode_start_ms"),
        "clip_encode_ready_ms": scheduler.get("clip_encode_ready_ms"),
        "clip_encode_wall_ms": scheduler.get("clip_encode_wall_ms"),
        "clip_encode_prefetch_hit": scheduler.get("clip_encode_prefetch_hit"),
        "clip_encode_prefetch_real_hit": scheduler.get("clip_encode_prefetch_real_hit"),
        "clip_encode_prefetch_eligible_count": scheduler.get("clip_encode_prefetch_eligible_count"),
        "clip_encode_prefetch_done_count": scheduler.get("clip_encode_prefetch_done_count"),
        "clip_encode_prefetch_miss_reason": scheduler.get("clip_encode_prefetch_miss_reason"),
        "sampler_gate_ready_ms": scheduler.get("sampler_gate_ready_ms"),
        "sampler_gate_ready_without_vae_ms": scheduler.get("sampler_gate_ready_without_vae_ms"),
        "sampler_gate_ready_with_vae_ms": scheduler.get("sampler_gate_ready_with_vae_ms"),
        "scheduler_notes": scheduler.get("notes"),
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _median(values: list[float]) -> float | None:
    clean = [float(v) for v in values if isinstance(v, (int, float))]
    if not clean:
        return None
    return round(statistics.median(clean), 1)


def _summarize(rows: list[dict]) -> list[dict]:
    out = []
    by_mode: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("status") != "ok":
            continue
        by_mode.setdefault(str(row["mode"]), []).append(row)

    fields = [
        "wall_ms",
        "modal_to_return_ms",
        "total_input_execution_ms",
        "prompt_start_to_sampler_start_ms",
        "sampler_gate_ready_without_vae_ms",
        "dependency_gate_done_ms",
        "clip_load_wall_ms",
        "clip_encode_wall_ms",
        "clip_encode_prefetch_hit",
        "unet_load_wall_ms",
        "sampler_ms",
        "restore_total_ms",
        "unet_gbps",
        "clip_gbps",
    ]
    for mode, mode_rows in by_mode.items():
        summary = {"mode": mode, "runs_ok": len(mode_rows)}
        for field in fields:
            summary[f"median_{field}"] = _median([r.get(field) for r in mode_rows])
        out.append(summary)
    out.sort(key=lambda r: (r.get("median_wall_ms") is None, r.get("median_wall_ms") or 10**18))
    return out


def _write_summary_md(path: Path, summaries: list[dict], rows: list[dict], modes_arg: str, runs_per: int, cold_wait: float) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Parallel Scheduler Benchmark Summary\n\n")
        f.write(f"`{modes_arg}` modes, {runs_per} runs/mode, {cold_wait}s cold wait\n\n")
        if not summaries:
            f.write("No successful runs.\n")
            return

        f.write("## Ranked by median wall time\n\n")
        f.write("| Rank | Mode | Runs | Wall ms | Modal→Return | Total Exec | Prompt→Sampler | Gate w/o VAE | Dep Gate | CLIP load | CLIP enc | Prefetch Hit | UNET load | Sampler | Restore |\n")
        f.write("|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for i, row in enumerate(summaries, 1):
            f.write(
                f"| {i} | {row['mode']} | {row['runs_ok']} | "
                f"{row.get('median_wall_ms','')} | "
                f"{row.get('median_modal_to_return_ms','')} | "
                f"{row.get('median_total_input_execution_ms','')} | "
                f"{row.get('median_prompt_start_to_sampler_start_ms','')} | "
                f"{row.get('median_sampler_gate_ready_without_vae_ms','')} | "
                f"{row.get('median_dependency_gate_done_ms','')} | "
                f"{row.get('median_clip_load_wall_ms','')} | "
                f"{row.get('median_clip_encode_wall_ms','')} | "
                f"{row.get('median_clip_encode_prefetch_hit','')} | "
                f"{row.get('median_unet_load_wall_ms','')} | "
                f"{row.get('median_sampler_ms','')} | "
                f"{row.get('median_restore_total_ms','')} |\n"
            )

        f.write("\n## Interpretation\n\n")
        f.write("- Prefer mode with lowest median wall_ms and total_input_execution_ms\n")
        f.write("- If CLIP-first lowers sampler_gate_ready_without_vae_ms, CLIP-load-unlocks-encode hypothesis supported\n")
        f.write("- If all_parallel_* ties clip_load_then_unet, loads likely share bandwidth without contention\n")
        f.write("- If early_unet_vae improves by ~dependency validation time, dep validation was avoidable blocker\n")
        f.write("- clip_encode_prefetch_hit > 0 means prefetch computed; real_hit > 0 means graph found the cache\n")

        f.write("\n## Best modes\n\n")
        best_wall = summaries[0] if summaries else {}
        f.write(f"- **Best wall time:** {best_wall.get('mode','?')} ({best_wall.get('median_wall_ms','?')}ms)\n")
        best_gate = min(summaries, key=lambda r: r.get('median_sampler_gate_ready_without_vae_ms') or 10**9) if summaries else {}
        if best_gate.get("mode") != best_wall.get("mode"):
            f.write(f"- **Best sampler gate:** {best_gate.get('mode','?')} ({best_gate.get('median_sampler_gate_ready_without_vae_ms','?')}ms)\n")
        f.write(f"- **Baseline:** {summaries[0]['mode'] if summaries and summaries[0].get('mode') == 'baseline_current' else 'N/A - see first row'}\n")


def _parse_modes(arg: str) -> dict[str, dict]:
    arg_lower = arg.strip().lower()
    if arg_lower in ("all", "*"):
        return dict(FULL_MODES)
    if arg_lower == "smoke":
        return dict(SMOKE_MODES)
    if arg_lower == "focused":
        return dict(FOCUSED_MODES)
    selected = {}
    for raw in arg.split(","):
        name = raw.strip()
        if not name:
            continue
        if name in FULL_MODES:
            selected[name] = FULL_MODES[name]
        elif name in DEFAULT_MODES:
            selected[name] = DEFAULT_MODES[name]
        else:
            raise ValueError(f"unknown mode {name!r}")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Modal Comfy scheduler parallel matrix.")
    parser.add_argument("--modes", default="smoke", help="Comma-separated modes or smoke|focused|all.")
    parser.add_argument("--runs-per-mode", type=int, default=3)
    parser.add_argument("--cold-wait-s", type=float, default=12.0, help="Wait between runs.")
    parser.add_argument("--no-deploy", action="store_true", help="Skip redeploy/local restart.")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle mode order.")
    parser.add_argument("--history-timeout-s", type=int, default=1800)
    args = parser.parse_args()

    modes = _parse_modes(args.modes)
    if args.shuffle:
        import random
        items = list(modes.items())
        random.shuffle(items)
        modes = dict(items)

    run_dir = _ensure_run_dir()
    log_path = run_dir / "benchmark.log"
    _write_json(run_dir / "modes.json", modes)
    _append_log(log_path, f"benchmark_modal_parallel_matrix.py modes={args.modes} runs_per={args.runs_per_mode} cold_wait={args.cold_wait_s}s shuffle={args.shuffle} no_deploy={args.no_deploy}")

    rows: list[dict] = []

    try:
        snapshot = _load_latest_snapshot()
        _write_json(run_dir / "workflow_snapshot.json", snapshot)
        _append_log(log_path, f"loaded workflow snapshot hash={snapshot.get('workflow_hash', '')}")

        if not args.no_deploy:
            _terminate_local_comfyui()
            _append_log(log_path, "terminated previous local ComfyUI processes")

            batch_result = _run_redeploy_batch()
            _append_log(log_path, batch_result.stdout or "")
            if batch_result.stderr:
                _append_log(log_path, batch_result.stderr)
            if batch_result.returncode != 0:
                _append_log(log_path, "batch deploy failed; retrying direct modal deploy")
                direct_result = _run_direct_deploy()
                _append_log(log_path, direct_result.stdout or "")
                if direct_result.stderr:
                    _append_log(log_path, direct_result.stderr)
                if direct_result.returncode != 0:
                    raise RuntimeError(
                        f"deploy failed: batch={batch_result.returncode} direct={direct_result.returncode}"
                    )
                _launch_local_comfyui()

            _wait_for_local_health()
            _append_log(log_path, "local ComfyUI health check passed")

        for mode_name, scheduler_config in modes.items():
            for iteration in range(1, args.runs_per_mode + 1):
                run_label = f"{mode_name}-r{iteration}"
                _append_log(log_path, f"starting {run_label}: {scheduler_config}")

                if rows or iteration > 1:
                    _append_log(log_path, f"sleeping cold_wait_s={args.cold_wait_s}")
                    time.sleep(args.cold_wait_s)

                prompt_id = ""
                started = time.time()
                try:
                    payload = _build_prompt_payload(snapshot, run_label, scheduler_config)
                    _write_json(run_dir / f"{run_label}_payload.json", payload)
                    prompt_id = _submit_prompt(payload)
                    entry = _poll_history(prompt_id, timeout_s=args.history_timeout_s)
                    wall_ms = (time.time() - started) * 1000
                    trace = _extract_trace(entry)

                    _write_json(run_dir / f"{run_label}_response.json", {"prompt_id": prompt_id, "history": entry})
                    _write_json(run_dir / f"{run_label}_trace.json", trace)

                    row = _flatten_run(mode_name, iteration, prompt_id, wall_ms, trace)
                    rows.append(row)
                    _append_log(log_path, f"completed {run_label} prompt_id={prompt_id} wall_ms={wall_ms:.1f}")
                except Exception as exc:
                    wall_ms = (time.time() - started) * 1000
                    row = _flatten_run(mode_name, iteration, prompt_id, wall_ms, {}, error=str(exc))
                    rows.append(row)
                    _append_log(log_path, f"failed {run_label}: {exc}")

                _write_csv(run_dir / "runs.csv", rows)
                summaries = _summarize(rows)
                _write_json(run_dir / "summary.json", {"summaries": summaries, "rows": rows})
                _write_csv(run_dir / "summary.csv", summaries)
                _write_summary_md(run_dir / "summary.md", summaries, rows, args.modes, args.runs_per_mode, args.cold_wait_s)

        _append_log(log_path, "done")
        return 0
    except Exception as exc:
        _append_log(log_path, f"fatal: {exc}")
        _write_csv(run_dir / "runs.csv", rows)
        _write_json(run_dir / "summary.json", {"fatal": str(exc), "rows": rows, "summaries": _summarize(rows)})
        _write_summary_md(run_dir / "summary.md", _summarize(rows), rows, args.modes, args.runs_per_mode, args.cold_wait_s)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
