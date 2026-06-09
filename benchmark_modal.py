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


# ── Trace validation ──────────────────────────────────────────────────────────


def _validate_trace(trace: dict) -> dict:
    """Lightweight schema check.  Returns quality info, does not raise."""
    result: dict = {
        "schema_ok": False,
        "missing_major_fields": [],
        "missing_optional_fields": [],
        "bad_reason": "",
    }
    if not isinstance(trace, dict):
        result["bad_reason"] = "trace_is_not_a_dict"
        return result
    major = [
        "trace_version", "deltas_ms", "derived_ms",
        "timing_quality", "timing_quality_reason", "missing_timing_fields",
    ]
    for key in major:
        if key not in trace:
            result["missing_major_fields"].append(key)
    if result["missing_major_fields"]:
        result["bad_reason"] = f"missing_top_level_keys={result['missing_major_fields']}"
        return result
    if not isinstance(trace.get("deltas_ms"), dict):
        result["missing_major_fields"].append("deltas_ms(not_dict)")
        result["bad_reason"] = "deltas_ms_is_not_a_dict"
        return result
    if not isinstance(trace.get("derived_ms"), dict):
        result["missing_major_fields"].append("derived_ms(not_dict)")
        result["bad_reason"] = "derived_ms_is_not_a_dict"
        return result
    # Check execution-critical derived fields
    exec_derived = [
        "prompt_start_to_sampler_start_ms", "sampler_ms",
        "total_input_execution_ms", "output_collection_total_ms",
    ]
    derived = trace.get("derived_ms", {})
    for key in exec_derived:
        if key not in derived or derived[key] is None:
            result["missing_major_fields"].append(key)
    if result["missing_major_fields"]:
        result["bad_reason"] = f"missing_derived_fields={result['missing_major_fields']}"
        return result
    result["schema_ok"] = True
    return result


# ── Timing extraction helpers ────────────────────────────────────────────────


def _extract_modal_to_browser(trace: dict) -> float | None:
    if not isinstance(trace, dict):
        return None
    deltas = trace.get("deltas_ms", {}) if isinstance(trace.get("deltas_ms", {}), dict) else {}
    return deltas.get("modal_to_browser") or deltas.get("modal_to_return")


def _extract_derived(trace: dict, field: str) -> float | None:
    if not isinstance(trace, dict):
        return None
    derived = trace.get("derived_ms", {}) if isinstance(trace.get("derived_ms", {}), dict) else {}
    return derived.get(field)


def _get_t0_wall_ms(trace: dict) -> float | None:
    """Estimate wall time from t0 (client press) to t10 if both exist."""
    if not isinstance(trace, dict):
        return None
    stages = trace.get("stages", {}) if isinstance(trace.get("stages", {}), dict) else {}
    deltas = trace.get("deltas_ms", {}) if isinstance(trace.get("deltas_ms", {}), dict) else {}
    t0 = stages.get("t0_client_press")
    t10_key = "t10_browser_recv" if stages.get("t10_browser_recv") is not None else "t10_local_materialized"
    t10 = stages.get(t10_key)
    if t0 is not None and t10 is not None:
        return round((t10 - t0) * 1000, 2)
    # Fall back to t0_to_t10 delta
    return deltas.get("t0_to_t1") if deltas.get("t0_to_t1") is not None else None


def _extract_restore(trace: dict, field: str) -> float | None:
    if not isinstance(trace, dict):
        return None
    restore = trace.get("restore", {})
    if not isinstance(restore, dict):
        return None
    v = restore.get(field)
    return float(v) if isinstance(v, (int, float)) else None


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


def _pick_traced(trace: dict, field: str, default: str = "") -> str:
    """Return str(value) from derived_ms, or default."""
    v = _extract_derived(trace, field)
    return str(v) if v is not None else default


def _write_runs_csv(run_dir: Path, run1_trace: dict, run2_trace: dict) -> None:
    import csv
    fields = [
        "modal_to_return_ms",
        "total_input_execution_ms",
        "modal_entry_to_prompt_start_ms",
        "restore_end_to_prompt_start_ms",
        "prompt_start_to_sampler_start_ms",
        "sampler_ms",
        "sampler_end_to_outputs_collected_ms",
        "output_collection_total_ms",
        "restore_total_ms",
        "timing_quality",
        "timing_quality_reason",
        "missing_timing_fields",
    ]
    row: dict[str, str] = {}
    for f in fields:
        if f == "timing_quality":
            row[f] = str(run2_trace.get("timing_quality", "")) if isinstance(run2_trace, dict) else ""
        elif f == "timing_quality_reason":
            row[f] = str(run2_trace.get("timing_quality_reason", "")) if isinstance(run2_trace, dict) else ""
        elif f == "missing_timing_fields":
            mf = run2_trace.get("missing_timing_fields", []) if isinstance(run2_trace, dict) else []
            row[f] = "; ".join(mf)
        else:
            # try run2 first, fall back run1
            for trace in (run2_trace, run1_trace):
                if not isinstance(trace, dict):
                    continue
                val = _extract_derived(trace, f)
                if val is not None:
                    row[f] = str(val)
                    break
            else:
                row[f] = ""
    with open(run_dir / "runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerow(row)


def _write_summary(run_dir: Path, status: str, run1_trace: dict, run2_trace: dict, extra: dict | None = None) -> None:
    # ── Extract wall/return/execution separately ──
    run1_wall_ms = _get_t0_wall_ms(run1_trace)
    run2_wall_ms = _get_t0_wall_ms(run2_trace)
    run1_modal_to_return_ms = _extract_modal_to_browser(run1_trace)
    run2_modal_to_return_ms = _extract_modal_to_browser(run2_trace)
    run1_modal_to_browser_ms = _extract_derived(run1_trace, "modal_to_browser_ms")
    run2_modal_to_browser_ms = _extract_derived(run2_trace, "modal_to_browser_ms")
    run1_total_input_exec_ms = _extract_derived(run1_trace, "total_input_execution_ms")
    run2_total_input_exec_ms = _extract_derived(run2_trace, "total_input_execution_ms")

    # legacy fallback: modal_to_browser > modal_to_return > None (NOT exec time)
    run1_total_ms = run1_modal_to_browser_ms or run1_modal_to_return_ms or run1_wall_ms
    run2_total_ms = run2_modal_to_browser_ms or run2_modal_to_return_ms or run2_wall_ms

    summary = {
        "status": status,
        "run1_total_ms": run1_total_ms,
        "run2_total_ms": run2_total_ms,
        "run1_wall_ms": run1_wall_ms,
        "run2_wall_ms": run2_wall_ms,
        "run1_modal_to_return_ms": run1_modal_to_return_ms,
        "run2_modal_to_return_ms": run2_modal_to_return_ms,
        "run1_modal_to_browser_ms": run1_modal_to_browser_ms,
        "run2_modal_to_browser_ms": run2_modal_to_browser_ms,
        "run1_total_input_execution_ms": run1_total_input_exec_ms,
        "run2_total_input_execution_ms": run2_total_input_exec_ms,
        "run1_trace": run1_trace,
        "run2_trace": run2_trace,
    }
    # Validate traces
    run1_val = _validate_trace(run1_trace) if isinstance(run1_trace, dict) else {"schema_ok": False, "bad_reason": "not_a_dict"}
    run2_val = _validate_trace(run2_trace) if isinstance(run2_trace, dict) else {"schema_ok": False, "bad_reason": "not_a_dict"}
    summary["run1_schema_ok"] = run1_val.get("schema_ok", False)
    summary["run2_schema_ok"] = run2_val.get("schema_ok", False)

    # Restore timing
    for label, trace in [("run1", run1_trace), ("run2", run2_trace)]:
        if isinstance(trace, dict):
            restore = trace.get("restore", {})
            if isinstance(restore, dict) and restore:
                for k, v in restore.items():
                    if isinstance(v, (int, float)):
                        summary[f"{label}_{k}"] = v
    # Derived timing
    for label, trace in [("run1", run1_trace), ("run2", run2_trace)]:
        if isinstance(trace, dict):
            derived = trace.get("derived_ms", {})
            if isinstance(derived, dict) and derived:
                for k, v in derived.items():
                    if isinstance(v, (int, float)):
                        summary[f"{label}_{k}"] = v
    if extra:
        summary.update(extra)
    _write_json(run_dir / "summary.json", summary)

    # ── summary.md ──
    lines = [
        f"status: {status}",
        f"",
        f"## Wall / Return Timing",
        f"run1_wall_ms: {run1_wall_ms}",
        f"run2_wall_ms: {run2_wall_ms}",
        f"run1_modal_to_return_ms: {run1_modal_to_return_ms}",
        f"run2_modal_to_return_ms: {run2_modal_to_return_ms}",
        f"run1_modal_to_browser_ms: {run1_modal_to_browser_ms}",
        f"run2_modal_to_browser_ms: {run2_modal_to_browser_ms}",
        f"",
        f"## Internal Execution",
        f"run1_total_input_execution_ms: {run1_total_input_exec_ms}",
        f"run2_total_input_execution_ms: {run2_total_input_exec_ms}",
        "",
    ]
    for label, trace in [("run1", run1_trace), ("run2", run2_trace)]:
        if not isinstance(trace, dict):
            continue
        derived = trace.get("derived_ms", {}) if isinstance(trace.get("derived_ms", {}), dict) else {}
        lines.append(f"### {label} derived")
        for key in ("prompt_start_to_sampler_start_ms", "sampler_ms",
                     "sampler_end_to_outputs_collected_ms", "output_collection_total_ms",
                     "modal_entry_to_prompt_start_ms", "restore_end_to_prompt_start_ms",
                     "sampler_prep_ms", "sampler_denoise_ms", "sampler_teardown_ms",
                     "clip_node_wait_ms", "unet_node_wait_ms", "vae_node_wait_ms",
                     "modal_to_return_ms", "modal_to_browser_ms"):
            if key in derived and derived[key] is not None:
                lines.append(f"  {label}_{key}: {derived[key]}")
        # Restore timing
        restore = trace.get("restore", {}) if isinstance(trace.get("restore", {}), dict) else {}
        restore_keys = [k for k in ("restore_total_ms", "cuda_warmup_ms", "sage_runtime_ms",
                                     "warmup_preload_ms", "gpu_state_ms", "ensure_models_ms")
                        if k in restore and restore[k] is not None]
        if restore_keys:
            lines.append(f"### {label} Restore Timing")
            for key in restore_keys:
                lines.append(f"  {label}_{key}: {restore[key]}")
        # Deltas
        deltas = trace.get("deltas_ms", {}) if isinstance(trace.get("deltas_ms", {}), dict) else {}
        delta_keys = [k for k in ("clip_load", "clip_encode", "unet_load", "vae_load",
                                   "t2_to_t3", "graph_overhead", "inference_total")
                      if k in deltas and deltas[k] is not None]
        if delta_keys:
            lines.append(f"### {label} Deltas")
            for key in delta_keys:
                lines.append(f"  {label}_{key}: {deltas[key]}")
        # Timing quality
        qual = trace.get("timing_quality")
        if qual:
            lines.append(f"  {label}_timing_quality: {qual}")
        reason = trace.get("timing_quality_reason")
        if reason:
            lines.append(f"  {label}_timing_quality_reason: {reason}")
        missing = trace.get("missing_timing_fields", [])
        if missing:
            lines.append(f"  {label}_missing_fields: {', '.join(missing)}")
        val_result = _validate_trace(trace)
        lines.append(f"  {label}_schema_ok: {val_result.get('schema_ok', False)}")

    # legacy compat
    lines.append("")
    lines.append(f"## Legacy Total")
    lines.append(f"run1_total_ms: {run1_total_ms}")
    lines.append(f"run2_total_ms: {run2_total_ms}")

    with open(run_dir / "summary.md", "w", encoding="utf-8") as f:
        f.write("# Benchmark Summary\n\n")
        for line in lines:
            f.write(f"- {line}\n")

    # ── runs.csv ──
    _write_runs_csv(run_dir, run1_trace, run2_trace)


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
