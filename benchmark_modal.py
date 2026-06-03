import json
import os
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib import error, request


LOCAL_BASE_URL = "http://127.0.0.1:8188"
BENCHMARK_WORKFLOW_ROUTE = f"{LOCAL_BASE_URL}/comfymodal/benchmark/workflow"
LOCAL_PROMPT_ROUTE = f"{LOCAL_BASE_URL}/comfymodal/prompt"
LOCAL_SYSTEM_STATS_ROUTE = f"{LOCAL_BASE_URL}/system_stats"
BENCHMARK_RUNS_DIRNAME = "benchmark_runs"
# Match only local ComfyUI\main.py launcher command lines.
LOCAL_COMFYUI_PROCESS_PATTERN = "ComfyUI\\main.py"
WINDOWS_COMFYUI_PROCESS_NAMES = ("python.exe", "pythonw.exe")

REPO_ROOT = Path(__file__).resolve().parent
OUTER_COMFYUI_ROOT = REPO_ROOT.parents[2]
SAVED_WORKFLOWS_DIR = OUTER_COMFYUI_ROOT / "saved workflows"
DEFAULT_SAVED_WORKFLOW_FILE = SAVED_WORKFLOWS_DIR / "flux_2-klein-9b(2).json"
REDEPLOY_BATCH = OUTER_COMFYUI_ROOT / "redeploy_modal_and_run_comfyui.bat"
COMFYAPP_DEPLOY_TARGET = OUTER_COMFYUI_ROOT / "ComfyUI" / "custom_nodes" / "comfyui-modal" / "comfyapp.py"
COMFYUI_LAUNCHER = OUTER_COMFYUI_ROOT / "run_nvidia_gpu.bat"
EMBEDDED_PYTHON = OUTER_COMFYUI_ROOT / "python_embeded" / "python.exe"
LATEST_BENCHMARK_WORKFLOW_FILE = REPO_ROOT / "latest_benchmark_workflow.json"


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


def _ensure_run_dir() -> Path:
    run_dir = REPO_ROOT / BENCHMARK_RUNS_DIRNAME / _timestamp()
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _append_log(log_path: Path, message: str) -> None:
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(message.rstrip() + "\n")


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


def _json_hash(payload: dict) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_OID, json.dumps(payload, sort_keys=True)))


def _list_local_comfyui_pids() -> list[int]:
    ps_script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { ($_.Name -in 'python.exe','pythonw.exe') -and $_.CommandLine -match 'ComfyUI\\main.py' } | "
        "Select-Object -ExpandProperty ProcessId | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        capture_output=True,
        text=True,
        timeout=30,
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
            capture_output=True,
            text=True,
            timeout=30,
        )
    if pids:
        time.sleep(5)
    remaining = _list_local_comfyui_pids()
    for pid in remaining:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=30)


def _run_redeploy_batch() -> subprocess.CompletedProcess:
    return subprocess.run(
        ["cmd.exe", "/c", str(REDEPLOY_BATCH)],
        input="\n",
        capture_output=True,
        text=True,
        timeout=1800,
    )


def _run_direct_deploy() -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        ["modal", "deploy", str(COMFYAPP_DEPLOY_TARGET)],
        capture_output=True,
        text=True,
        timeout=1800,
        cwd=str(OUTER_COMFYUI_ROOT),
        env=env,
    )


def _launch_local_comfyui() -> subprocess.Popen:
    return subprocess.Popen(
        [str(EMBEDDED_PYTHON), "-s", "ComfyUI\\main.py", "--windows-standalone-build"],
        cwd=str(OUTER_COMFYUI_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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


def _build_prompt_payload(snapshot: dict, run_label: str) -> dict:
    payload = dict(snapshot.get("payload") or snapshot)
    payload["client_id"] = f"benchmark-{run_label}-{uuid.uuid4()}"
    payload["t0_client_press_ms"] = int(time.time() * 1000)
    payload.pop("t0_client_press", None)
    payload.pop("t0_perf_ms", None)
    payload.pop("t0_perf_now_ms", None)
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


def _extract_total(trace: dict) -> float | None:
    if not isinstance(trace, dict):
        return None
    deltas = trace.get("deltas_ms", {}) if isinstance(trace.get("deltas_ms", {}), dict) else {}
    return deltas.get("modal_to_browser") or deltas.get("modal_to_return")


def _write_json(path: Path, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _classify_failure_status(stage: str, exc: Exception, run1_completed: bool) -> str:
    if stage == "snapshot":
        return "snapshot_missing"
    if stage == "deploy":
        return "deploy_failed"
    if stage == "health" and isinstance(exc, TimeoutError):
        return "health_timeout"
    if stage == "run2" or run1_completed:
        return "run2_failed"
    return "run1_failed"


def _write_summary(run_dir: Path, status: str, run1_trace: dict, run2_trace: dict, extra: dict | None = None) -> None:
    summary = {
        "status": status,
        "run1_total_ms": _extract_total(run1_trace),
        "run2_total_ms": _extract_total(run2_trace),
        "run1_trace": run1_trace,
        "run2_trace": run2_trace,
    }
    # Extract restore timing from the runs that have it
    for label, trace in [("run1", run1_trace), ("run2", run2_trace)]:
        if isinstance(trace, dict):
            restore = trace.get("restore", {})
            if isinstance(restore, dict) and restore:
                for k, v in restore.items():
                    if isinstance(v, (int, float)):
                        summary[f"{label}_{k}"] = v
    if extra:
        summary.update(extra)
    _write_json(run_dir / "summary.json", summary)
    lines = [
        f"status: {status}",
        f"run1_total_ms: {summary['run1_total_ms']}",
        f"run2_total_ms: {summary['run2_total_ms']}",
    ]
    if isinstance(run2_trace, dict):
        deltas = run2_trace.get("deltas_ms", {}) if isinstance(run2_trace.get("deltas_ms", {}), dict) else {}
        for key in ("t2_to_t3", "clip_load", "clip_encode", "sampler", "vae_decode", "graph_overhead", "inference_total", "modal_to_return", "modal_to_browser"):
            if key in deltas:
                lines.append(f"run2_{key}: {deltas[key]}")
        restore = run2_trace.get("restore", {}) if isinstance(run2_trace.get("restore", {}), dict) else {}
        for key in ("restore_total_ms", "cuda_warmup_ms", "sage_runtime_ms", "warmup_preload_ms", "gpu_state_ms", "ensure_models_ms"):
            if key in restore:
                lines.append(f"run2_{key}: {restore[key]}")
    with open(run_dir / "summary.md", "w", encoding="utf-8") as f:
        f.write("# Benchmark Summary\n\n")
        for line in lines:
            f.write(f"- {line}\n")


def main() -> int:
    run_dir = _ensure_run_dir()
    log_path = run_dir / "benchmark.log"
    run1_trace: dict = {}
    run2_trace: dict = {}
    current_stage = "snapshot"
    run1_completed = False
    try:
        snapshot = _load_latest_snapshot()
        _write_json(run_dir / "workflow_snapshot.json", snapshot)
        _append_log(log_path, f"loaded workflow snapshot hash={snapshot.get('workflow_hash', '')}")

        _terminate_local_comfyui()
        _append_log(log_path, "terminated previous local ComfyUI processes")

        current_stage = "deploy"
        batch_result = _run_redeploy_batch()
        _append_log(log_path, batch_result.stdout or "")
        if batch_result.stderr:
            _append_log(log_path, batch_result.stderr)
        if batch_result.returncode != 0:
            _append_log(log_path, "batch deploy failed; retrying with direct UTF-8 modal deploy")
            direct_result = _run_direct_deploy()
            _append_log(log_path, direct_result.stdout or "")
            if direct_result.stderr:
                _append_log(log_path, direct_result.stderr)
            if direct_result.returncode != 0:
                _write_summary(run_dir, "deploy_failed", run1_trace, run2_trace, {
                    "deploy_returncode": batch_result.returncode,
                    "direct_deploy_returncode": direct_result.returncode,
                })
                return 1
            _launch_local_comfyui()
            _append_log(log_path, f"launched local ComfyUI via {COMFYUI_LAUNCHER.name} fallback path")

        current_stage = "health"
        _wait_for_local_health()
        _append_log(log_path, "local ComfyUI health check passed")

        current_stage = "run1"
        run1_payload = _build_prompt_payload(snapshot, "run1")
        run1_prompt_id = _submit_prompt(run1_payload)
        run1_entry = _poll_history(run1_prompt_id)
        run1_meta = run1_entry.get("meta", {}) if isinstance(run1_entry, dict) else {}
        run1_trace = dict(run1_meta.get("trace", {}))
        run1_restore = run1_meta.get("restore_timing", {})
        if isinstance(run1_restore, dict) and run1_restore:
            run1_trace["restore"] = run1_restore
        _write_json(run_dir / "run1_response.json", {"prompt_id": run1_prompt_id, "history": run1_entry})
        _write_json(run_dir / "run1_trace.json", run1_trace if isinstance(run1_trace, dict) else {})
        _append_log(log_path, f"run1 complete prompt_id={run1_prompt_id}")
        run1_completed = True

        time.sleep(10)

        current_stage = "run2"
        run2_payload = _build_prompt_payload(snapshot, "run2")
        run2_prompt_id = _submit_prompt(run2_payload)
        run2_entry = _poll_history(run2_prompt_id)
        run2_meta = run2_entry.get("meta", {}) if isinstance(run2_entry, dict) else {}
        run2_trace = dict(run2_meta.get("trace", {}))
        run2_restore = run2_meta.get("restore_timing", {})
        if isinstance(run2_restore, dict) and run2_restore:
            run2_trace["restore"] = run2_restore
        _write_json(run_dir / "run2_response.json", {"prompt_id": run2_prompt_id, "history": run2_entry})
        _write_json(run_dir / "run2_trace.json", run2_trace if isinstance(run2_trace, dict) else {})
        _append_log(log_path, f"run2 complete prompt_id={run2_prompt_id}")

        _write_summary(run_dir, "ok", run1_trace, run2_trace)
        return 0
    except TimeoutError as exc:
        _append_log(log_path, f"timeout: {exc}")
        status = _classify_failure_status(current_stage, exc, run1_completed)
        _write_summary(run_dir, status, run1_trace, run2_trace, {"error": str(exc)})
        return 1
    except Exception as exc:
        _append_log(log_path, f"error: {exc}")
        status = _classify_failure_status(current_stage, exc, run1_completed)
        _write_summary(run_dir, status, run1_trace, run2_trace, {"error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
