import json
import os
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib import error, request


# ── Modal function call helpers (no deploy, lightweight) ──

_MODAL_APP_NAME = os.environ.get("COMFYMODAL_BENCHMARK_APP_NAME", "comfyui")


def _call_modal_function_spawn(func_name: str, *args) -> str:
    """Call a Modal function by name using spawn (fire-and-forget, no deploy).
    
    Uses fn.spawn() which returns immediately. The function runs asynchronously
    on Modal's infrastructure. Use this for setting runtime flags where we
    don't need to wait for completion.
    """
    import modal
    t0 = time.time()
    fn = modal.Function.from_name(_MODAL_APP_NAME, func_name)
    handle = fn.spawn(*args)
    elapsed = time.time() - t0
    print(f"  [modal] {func_name}({args}) spawned in {elapsed:.1f}s (handle={handle.object_id})")
    return f"spawned {func_name}({args})"


def _call_set_preload_mode(mode: str) -> str:
    return _call_modal_function_spawn("set_preload_mode", mode)


def _call_set_runtime_flag(name: str, value: str) -> str:
    return _call_modal_function_spawn("set_runtime_flag", name, value)


LOCAL_BASE_URL = "http://127.0.0.1:8188"
BENCHMARK_WORKFLOW_ROUTE = f"{LOCAL_BASE_URL}/comfymodal/benchmark/workflow"
LOCAL_PROMPT_ROUTE = f"{LOCAL_BASE_URL}/comfymodal/prompt"
LOCAL_RESULT_ROUTE = f"{LOCAL_BASE_URL}/comfymodal/result"
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


def _build_prompt_payload(snapshot: dict, run_label: str, result_route: str = "legacy") -> dict:
    payload = dict(snapshot.get("payload") or snapshot)
    payload["client_id"] = f"benchmark-{run_label}-{uuid.uuid4()}"
    payload["t0_client_press_ms"] = int(time.time() * 1000)
    payload.pop("t0_client_press", None)
    payload.pop("t0_perf_ms", None)
    payload.pop("t0_perf_now_ms", None)
    if result_route in ("legacy", "direct"):
        payload["result_route"] = result_route
    return payload


def _submit_prompt(payload: dict) -> str:
    response = _json_request(LOCAL_PROMPT_ROUTE, method="POST", payload=payload, timeout=30)
    prompt_id = response.get("prompt_id", "")
    if not prompt_id:
        raise RuntimeError(f"missing prompt_id in response: {response}")
    return prompt_id


def _poll_direct_result(prompt_id: str, timeout_s: int = 1800) -> dict:
    """Poll the direct result endpoint for a completed prompt result.
    
    Unlike _poll_history, this retrieves the full Modal result payload
    (including trace, outputs, images) without waiting for local ComfyUI
    history to be written.
    """
    deadline = time.time() + timeout_s
    result_url = f"{LOCAL_RESULT_ROUTE}/{prompt_id}"
    while time.time() < deadline:
        try:
            data = _json_request(result_url, timeout=30)
        except Exception:
            time.sleep(1)
            continue
        if isinstance(data, dict) and data.get("status") == "ok":
            return data
        time.sleep(1)
    raise TimeoutError(f"direct result timeout for prompt_id={prompt_id}")


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
    # dependency validation fields are optional — no longer required for schema_ok
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


# ── Trace normalization ──────────────────────────────────────────────────────

_TRACE_DERIVATION_PAIRS = [
    ("modal_entry_to_prompt_start_ms", "t3_modal_entry", "t3d_prompt_start"),
    ("prompt_start_to_sampler_start_ms", "t3d_prompt_start", "t6_sampler_start"),
    ("execution_start_to_sampler_start_ms", "t3e_execution_start", "t6_sampler_start"),
    ("sampler_ms", "t6_sampler_start", "t6_sampler_end"),
    ("sampler_progress_ms", "t6_sampler_progress_start", "t6_sampler_progress_end"),
    ("sampler_end_to_vae_decode_start_ms", "t6_sampler_end", "t7_vae_decode_start"),
    ("vae_decode_ms", "t7_vae_decode_start", "t7_vae_decode_end"),
    ("vae_decode_end_to_collect_start_ms", "t7_vae_decode_end", "t7b_collect_start"),
    ("output_collection_total_ms", "t7b_collect_start", "t8b_outputs_collected"),
    ("sampler_end_to_outputs_collected_ms", "t6_sampler_end", "t8b_outputs_collected"),
    ("total_input_execution_ms", "t3d_prompt_start", "t9_modal_return"),
    ("modal_to_return_ms", "t3_modal_entry", "t9_modal_return"),
    ("local_dispatch_to_modal_entry_ms", "t2_local_dispatch", "t3_modal_entry"),
    ("local_recv_to_dispatch_ms", "t1_local_recv", "t2_local_dispatch"),
    ("client_to_local_recv_ms", "t0_client_press", "t1_local_recv"),
    # Phase 2 local path timing
    ("local_prepare_ms", "t1_local_recv", "t2_local_prepared"),
    ("modal_handle_resolve_ms", "t2_local_prepared", "t2b_modal_handle_resolved"),
    ("modal_call_submit_ms", "t2b_modal_handle_resolved", "t2c_modal_call_start"),
    ("modal_queue_or_start_gap_ms", "t2c_modal_call_start", "t3_modal_entry"),
    ("modal_return_to_local_receive_ms", "t9_modal_return", "t9b_local_result_received"),
    ("local_history_poll_ms", "t9c_local_history_poll_start", "t9d_local_history_poll_end"),
    ("local_materialize_ms", "t9e_local_materialize_start", "t10_local_materialized"),
    ("local_save_ms", "t10b_local_save_start", "t10c_local_save_end"),
    ("local_response_send_ms", "t10_local_materialized", "t10d_local_response_sent"),
    ("modal_return_to_browser_ms", "t9_modal_return", "t10d_local_response_sent"),
    ("client_to_response_sent_ms", "t0_client_press", "t10d_local_response_sent"),
    ("clip_load_ms", "t4_clip_load_start", "t4_clip_load_end"),
    ("clip_encode_ms", "t5_text_encode_start", "t5_text_encode_end"),
    ("unet_node_wait_ms", "t4b_unet_load_start", "t4b_unet_load_end"),
    ("vae_node_wait_ms", "t4c_vae_load_start", "t4c_vae_load_end"),
]

_TRACE_REQUIRED_STAGES = [
    "t3_modal_entry", "t3d_prompt_start",
    "t6_sampler_start", "t6_sampler_end",
    "t7b_collect_start", "t8b_outputs_collected",
    "t9_modal_return",
]

_TRACE_OPTIONAL_STAGES = [
    "t3e_execution_start",
    "t4_clip_load_start", "t4_clip_load_end",
    "t5_text_encode_start", "t5_text_encode_end",
    "t7_vae_decode_start", "t7_vae_decode_end",
    "t10_local_materialized",
    # Phase 2 local path stages
    "t2b_modal_handle_resolved", "t2c_modal_call_start",
    "t9b_local_result_received",
    "t9c_local_history_poll_start", "t9d_local_history_poll_end",
    "t9e_local_materialize_start",
    "t10b_local_save_start", "t10c_local_save_end",
    "t10d_local_response_sent",
]


def _delta_s(stages: dict, a: str, b: str) -> float | None:
    ta = stages.get(a)
    tb = stages.get(b)
    if ta is None or tb is None:
        return None
    return tb - ta


def _delta_ms(stages: dict, a: str, b: str) -> float | None:
    d = _delta_s(stages, a, b)
    if d is None:
        return None
    return round(d * 1000, 2)


def _extract_trace_from_response(response: dict) -> dict:
    candidates = []
    if not isinstance(response, dict):
        return {}
    for location in (
        ("history", "meta", "trace"),
        ("meta", "trace"),
        ("trace",),
        ("result", "trace"),
        ("direct_result", "trace"),
        ("direct_result", "result", "trace"),
    ):
        obj = response
        for key in location:
            if not isinstance(obj, dict):
                obj = None
                break
            obj = obj.get(key)
        if isinstance(obj, dict) and obj:
            candidates.append(obj)
    return _pick_richest_trace(candidates) if candidates else {}


def _pick_richest_trace(traces: list[dict]) -> dict:
    def score(t):
        s = 0
        for k in ("stages", "deltas_ms", "derived_ms", "restore"):
            v = t.get(k, {})
            if isinstance(v, dict):
                s += len(v)
        return s
    return max(traces, key=score)


def _classify_timing_quality(trace: dict) -> dict:
    stages = trace.get("stages", {})
    if not isinstance(stages, dict):
        stages = {}
    derived = trace.get("derived_ms", {})
    if not isinstance(derived, dict):
        derived = {}
    existing_missing = trace.get("missing_timing_fields", [])
    if not isinstance(existing_missing, list):
        existing_missing = []

    required_present = [k for k in _TRACE_REQUIRED_STAGES if k in stages and stages[k] is not None]
    required_missing = [k for k in _TRACE_REQUIRED_STAGES if k not in stages or stages[k] is None]
    optional_missing = [k for k in _TRACE_OPTIONAL_STAGES if k not in stages or stages[k] is None]

    negative_derived = [k for k in ("total_input_execution_ms", "prompt_start_to_sampler_start_ms",
                                     "sampler_ms", "output_collection_total_ms",
                                     "modal_to_return_ms", "modal_to_browser_ms",
                                     "modal_entry_to_prompt_start_ms", "restore_end_to_prompt_start_ms",
                                     "sampler_end_to_outputs_collected_ms",
                                     "local_dispatch_to_modal_entry_ms", "clip_load_ms",
                                     "clip_encode_ms", "unet_node_wait_ms", "vae_node_wait_ms")
                        if derived.get(k) is not None and
                        (not isinstance(derived[k], (int, float)) or derived[k] < 0)]

    has_total_exec = derived.get("total_input_execution_ms") is not None
    has_prompt_to_sampler = derived.get("prompt_start_to_sampler_start_ms") is not None
    has_sampler = derived.get("sampler_ms") is not None
    has_output_collection = derived.get("output_collection_total_ms") is not None
    has_modal_to_return = derived.get("modal_to_return_ms") is not None

    reason_parts = []
    if required_missing:
        reason_parts.append(f"missing_required_stages={required_missing}")
    if optional_missing:
        reason_parts.append(f"missing_optional={optional_missing}")
    if negative_derived:
        reason_parts.append(f"negative_duration:{','.join(negative_derived)}")

    all_missing = list(set(existing_missing +
                           [f"stage:{k}" for k in required_missing] +
                           [f"stage:{k}" for k in optional_missing]))

    if (len(required_present) == len(_TRACE_REQUIRED_STAGES)
            and has_total_exec and has_prompt_to_sampler
            and has_sampler and has_output_collection
            and not negative_derived):
        quality = "complete"
        if not reason_parts:
            reason_parts.append("all_required_fields_present")
        reason = "; ".join(reason_parts)
        schema_ok = True
    elif (has_sampler and has_modal_to_return
          and (has_prompt_to_sampler or has_total_exec)
          and len(required_present) >= 4):
        quality = "partial"
        if not reason_parts:
            reason_parts.append("partial_fields_present")
        reason = "; ".join(reason_parts)
        schema_ok = True
    else:
        quality = "bad"
        if not reason_parts:
            reason_parts.append("cannot_trust_execution_timing")
        reason = "; ".join(reason_parts)
        schema_ok = False

    return {
        "timing_quality": quality,
        "timing_quality_reason": reason,
        "missing_timing_fields": all_missing,
        "schema_ok": schema_ok,
    }


def _normalize_trace(trace: dict, response: dict | None = None) -> dict:
    import copy
    if not isinstance(trace, dict):
        trace = {}
    result = copy.deepcopy(trace)

    stages = result.get("stages", {})
    if not isinstance(stages, dict):
        stages = {}
        result["stages"] = stages

    if "trace_version" not in result:
        result["trace_version"] = ""

    deltas = result.get("deltas_ms", {})
    if not isinstance(deltas, dict):
        deltas = {}
        result["deltas_ms"] = deltas

    restore = result.get("restore", {})
    if not isinstance(restore, dict):
        restore = {}
        result["restore"] = restore

    if response and isinstance(response, dict):
        meta = response.get("meta", {})
        if isinstance(meta, dict):
            rt = meta.get("restore_timing", {})
            if isinstance(rt, dict) and rt and not restore:
                result["restore"] = rt
                restore = rt

    derived = result.get("derived_ms", {})
    if not isinstance(derived, dict):
        derived = {}

    has_remote_derived = (
        derived.get("total_input_execution_ms") is not None
        or derived.get("sampler_ms") is not None
    )

    missing_fields = list(result.get("missing_timing_fields", []))
    if not isinstance(missing_fields, list):
        missing_fields = []

    if not has_remote_derived and stages:
        local_derived = {}
        for name, a, b in _TRACE_DERIVATION_PAIRS:
            d = _delta_ms(stages, a, b)
            if d is not None:
                if d < 0:
                    local_derived[name] = None
                    missing_fields.append(f"negative_duration:{name}")
                else:
                    local_derived[name] = d

        if stages.get("t10_local_materialized") is not None and stages.get("t3_modal_entry") is not None:
            d = _delta_ms(stages, "t3_modal_entry", "t10_local_materialized")
            if d is not None:
                if d < 0:
                    local_derived["modal_to_browser_ms"] = None
                    missing_fields.append("negative_duration:modal_to_browser_ms")
                else:
                    local_derived["modal_to_browser_ms"] = d

        if stages.get("t0_client_press") is not None and stages.get("t10_local_materialized") is not None:
            d = _delta_ms(stages, "t0_client_press", "t10_local_materialized")
            if d is not None:
                if d < 0:
                    local_derived["client_to_local_materialized_ms"] = None
                    missing_fields.append("negative_duration:client_to_local_materialized_ms")
                else:
                    local_derived["client_to_local_materialized_ms"] = d

        re_end = restore.get("restore_end_unix_s") if isinstance(restore, dict) else None
        t3d = stages.get("t3d_prompt_start")
        if re_end is not None and t3d is not None:
            d = round((t3d - re_end) * 1000, 2)
            if d < 0:
                local_derived["restore_end_to_prompt_start_ms"] = None
                missing_fields.append("negative_duration:restore_end_to_prompt_start_ms")
            else:
                local_derived["restore_end_to_prompt_start_ms"] = d

        for k, v in derived.items():
            if k not in local_derived:
                local_derived[k] = v

        result["derived_ms"] = local_derived
        result["missing_timing_fields"] = list(set(missing_fields))

    qual = _classify_timing_quality(result)
    result["timing_quality"] = qual["timing_quality"]
    result["timing_quality_reason"] = qual["timing_quality_reason"]
    result["missing_timing_fields"] = qual["missing_timing_fields"]
    result["schema_ok"] = qual["schema_ok"]
    return result


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
        "run", "status", "wall_ms",
        "modal_to_return_ms", "modal_to_browser_ms",
        "client_to_local_materialized_ms", "local_dispatch_to_modal_entry_ms",
        "restore_total_ms",
        "modal_entry_to_prompt_start_ms", "restore_end_to_prompt_start_ms",
        "prompt_start_to_sampler_start_ms", "execution_start_to_sampler_start_ms",
        "total_input_execution_ms",
        "sampler_ms", "sampler_progress_ms",
        "sampler_end_to_outputs_collected_ms", "output_collection_total_ms",
        "clip_load_ms", "clip_encode_ms", "unet_node_wait_ms", "vae_node_wait_ms",
        "dependency_validation_ms", "dependency_total_ms",
        "dependency_validation_result", "dependency_validation_cache_layer",
        "dependency_validation_cache_hit", "dependency_validation_reason",
        "dependency_validation_baked_hash", "dependency_validation_current_hash",
        "dependency_validation_changed_nodes",
        "dependency_pre_key_check_ms", "dependency_baked_manifest_load_ms",
        "dependency_source_root_resolve_ms", "dependency_fingerprint_ms",
        "dependency_cache_key_ms", "dependency_memory_lookup_ms",
        "dependency_sentinel_lookup_ms", "dependency_full_validation_ms",
        "dependency_sentinel_write_ms",
        "timing_quality", "timing_quality_reason", "schema_ok", "missing_timing_fields",
        # Phase 2 local path fields
        "result_route", "direct_route_used", "direct_fallback_to_legacy", "direct_fallback_reason",
        "local_prepare_ms", "modal_handle_resolve_ms", "modal_call_submit_ms",
        "modal_queue_or_start_gap_ms", "modal_return_to_local_receive_ms",
        "local_history_poll_ms", "local_materialize_ms", "local_save_ms",
        "local_response_send_ms", "modal_return_to_browser_ms", "client_to_response_sent_ms",
        "fresh_container_requested",
        # Phase 3A preload/warmup diagnostics
        "preload_mode", "preload_mode_source", "preload_env_raw",
        "preload_skipped", "preload_skip_reason",
        "preload_unknown_profiles", "disable_restore_warmup_for_z_image",
        "enable_warmup", "direct_warmup_load_unet_flag", "direct_warmup_load_clip_flag", "direct_warmup_clip_encode_flag",
        "active_profile_lookup_attempted", "active_profile_found", "active_profile_source",
        "active_profile_workflow_hash", "active_profile_token",
        "warmup_profile_selected", "warmup_profile_source", "warmup_profile_token", "warmup_profile_workflow_hash",
        "preload_eligibility_active_next", "preload_eligibility_unknown_profiles",
        "disable_restore_warmup_for_z_image_effective",
        "direct_warmup_z_image_guard_skipped", "direct_warmup_skip_reason",
        "warmup_preload_ms", "warmup_direct_total_ms",
        "clip_cache_size_at_start", "clip_cache_size_after_warmup",
    ]

    rows = []
    for label, trace_raw in [("run1", run1_trace), ("run2", run2_trace)]:
        trace = _normalize_trace(trace_raw) if isinstance(trace_raw, dict) else {}
        derived = trace.get("derived_ms", {})
        if not isinstance(derived, dict):
            derived = {}
        restore = trace.get("restore", {})
        if not isinstance(restore, dict):
            restore = {}
        wall_ms = _get_t0_wall_ms(trace)

        def _v(d, key):
            val = d.get(key) if isinstance(d, dict) else None
            return val if val is not None else ""

        row = {
            "run": label,
            "status": "",
            "wall_ms": _v({"w": wall_ms}, "w"),
            "modal_to_return_ms": _v(derived, "modal_to_return_ms"),
            "modal_to_browser_ms": _v(derived, "modal_to_browser_ms"),
            "client_to_local_materialized_ms": _v(derived, "client_to_local_materialized_ms"),
            "local_dispatch_to_modal_entry_ms": _v(derived, "local_dispatch_to_modal_entry_ms"),
            "restore_total_ms": _v(restore, "restore_total_ms"),
            "modal_entry_to_prompt_start_ms": _v(derived, "modal_entry_to_prompt_start_ms"),
            "restore_end_to_prompt_start_ms": _v(derived, "restore_end_to_prompt_start_ms"),
            "prompt_start_to_sampler_start_ms": _v(derived, "prompt_start_to_sampler_start_ms"),
            "execution_start_to_sampler_start_ms": _v(derived, "execution_start_to_sampler_start_ms"),
            "total_input_execution_ms": _v(derived, "total_input_execution_ms"),
            "sampler_ms": _v(derived, "sampler_ms"),
            "sampler_progress_ms": _v(derived, "sampler_progress_ms"),
            "sampler_end_to_outputs_collected_ms": _v(derived, "sampler_end_to_outputs_collected_ms"),
            "output_collection_total_ms": _v(derived, "output_collection_total_ms"),
            "clip_load_ms": _v(derived, "clip_load_ms"),
            "clip_encode_ms": _v(derived, "clip_encode_ms"),
            "unet_node_wait_ms": _v(derived, "unet_node_wait_ms"),
            "vae_node_wait_ms": _v(derived, "vae_node_wait_ms"),
            "dependency_validation_ms": _v(derived, "dependency_validation_ms"),
            "dependency_total_ms": _v(derived, "dependency_total_ms"),
            "dependency_validation_result": str(trace.get("dependency_validation_result", "")),
            "dependency_validation_cache_layer": str(trace.get("dependency_validation_cache_layer", "")),
            "dependency_validation_cache_hit": str(trace.get("dependency_validation_cache_hit", "")),
            "dependency_validation_reason": str(trace.get("dependency_validation_reason", "")),
            "dependency_validation_baked_hash": str(trace.get("dependency_validation_baked_hash", "")),
            "dependency_validation_current_hash": str(trace.get("dependency_validation_current_hash", "")),
            "dependency_validation_changed_nodes": str(trace.get("dependency_validation_changed_nodes", [])),
            "dependency_pre_key_check_ms": _v(derived, "dependency_pre_key_check_ms"),
            "dependency_baked_manifest_load_ms": _v(derived, "dependency_baked_manifest_load_ms"),
            "dependency_source_root_resolve_ms": _v(derived, "dependency_source_root_resolve_ms"),
            "dependency_fingerprint_ms": _v(derived, "dependency_fingerprint_ms"),
            "dependency_cache_key_ms": _v(derived, "dependency_cache_key_ms"),
            "dependency_memory_lookup_ms": _v(derived, "dependency_memory_lookup_ms"),
            "dependency_sentinel_lookup_ms": _v(derived, "dependency_sentinel_lookup_ms"),
            "dependency_full_validation_ms": _v(derived, "dependency_full_validation_ms"),
            "dependency_sentinel_write_ms": _v(derived, "dependency_sentinel_write_ms"),
            "timing_quality": trace.get("timing_quality", ""),
            "timing_quality_reason": trace.get("timing_quality_reason", ""),
            "schema_ok": str(trace.get("schema_ok", False)),
            "missing_timing_fields": "; ".join(trace.get("missing_timing_fields", [])) if isinstance(trace.get("missing_timing_fields", []), list) else "",
            # Phase 2 local path fields
            "result_route": trace.get("result_route", ""),
            "direct_route_used": str(trace.get("direct_route_used", False)),
            "direct_fallback_to_legacy": str(trace.get("direct_fallback_to_legacy", 0)),
            "direct_fallback_reason": trace.get("direct_fallback_reason", ""),
            "local_prepare_ms": _v(derived, "local_prepare_ms"),
            "modal_handle_resolve_ms": _v(derived, "modal_handle_resolve_ms"),
            "modal_call_submit_ms": _v(derived, "modal_call_submit_ms"),
            "modal_queue_or_start_gap_ms": _v(derived, "modal_queue_or_start_gap_ms"),
            "modal_return_to_local_receive_ms": _v(derived, "modal_return_to_local_receive_ms"),
            "local_history_poll_ms": _v(derived, "local_history_poll_ms"),
            "local_materialize_ms": _v(derived, "local_materialize_ms"),
            "local_save_ms": _v(derived, "local_save_ms"),
            "local_response_send_ms": _v(derived, "local_response_send_ms"),
            "modal_return_to_browser_ms": _v(derived, "modal_return_to_browser_ms"),
            "client_to_response_sent_ms": _v(derived, "client_to_response_sent_ms"),
            "fresh_container_requested": str(trace.get("fresh_container_requested", "")),
            # Phase 3A preload/warmup diagnostics
            "preload_mode": _v(restore, "preload_mode"),
            "preload_mode_source": _v(restore, "preload_mode_source"),
            "preload_env_raw": _v(restore, "preload_env_raw"),
            "preload_skipped": _v(restore, "preload_skipped"),
            "preload_skip_reason": _v(restore, "preload_skip_reason"),
            "preload_unknown_profiles": _v(restore, "preload_unknown_profiles"),
            "disable_restore_warmup_for_z_image": _v(restore, "disable_restore_warmup_for_z_image"),
            "enable_warmup": _v(restore, "enable_warmup"),
            "direct_warmup_load_unet_flag": _v(restore, "direct_warmup_load_unet_flag"),
            "direct_warmup_load_clip_flag": _v(restore, "direct_warmup_load_clip_flag"),
            "direct_warmup_clip_encode_flag": _v(restore, "direct_warmup_clip_encode_flag"),
            "active_profile_lookup_attempted": _v(restore, "active_profile_lookup_attempted"),
            "active_profile_found": _v(restore, "active_profile_found"),
            "active_profile_source": _v(restore, "active_profile_source"),
            "active_profile_workflow_hash": _v(restore, "active_profile_workflow_hash"),
            "active_profile_token": _v(restore, "active_profile_token"),
            "warmup_profile_selected": _v(restore, "warmup_profile_selected"),
            "warmup_profile_source": _v(restore, "warmup_profile_source"),
            "warmup_profile_token": _v(restore, "warmup_profile_token"),
            "warmup_profile_workflow_hash": _v(restore, "warmup_profile_workflow_hash"),
            "preload_eligibility_active_next": _v(restore, "preload_eligibility_active_next"),
            "preload_eligibility_unknown_profiles": _v(restore, "preload_eligibility_unknown_profiles"),
            "clip_cache_size_at_start": _v(restore, "clip_cache_size_at_start"),
            "clip_cache_size_after_warmup": _v(restore, "clip_cache_size_after_warmup"),
            "disable_restore_warmup_for_z_image_effective": _v(restore, "disable_restore_warmup_for_z_image_effective"),
            "direct_warmup_z_image_guard_skipped": _v(restore, "direct_warmup_z_image_guard_skipped"),
            "direct_warmup_skip_reason": _v(restore, "direct_warmup_skip_reason"),
            "warmup_preload_ms": _v(restore, "warmup_preload_ms"),
            "warmup_direct_total_ms": _v(restore, "warmup_direct_total_ms"),
        }

        for k, v in row.items():
            if isinstance(v, float):
                row[k] = f"{v:.2f}"

        rows.append(row)

    with open(run_dir / "runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def _write_summary(run_dir: Path, status: str, run1_trace: dict, run2_trace: dict, extra: dict | None = None) -> None:
    run1_norm = _normalize_trace(run1_trace) if isinstance(run1_trace, dict) else {}
    run2_norm = _normalize_trace(run2_trace) if isinstance(run2_trace, dict) else {}

    r1 = run1_norm.get("derived_ms", {})
    r2 = run2_norm.get("derived_ms", {})
    if not isinstance(r1, dict):
        r1 = {}
    if not isinstance(r2, dict):
        r2 = {}
    r1_restore = run1_norm.get("restore", {})
    r2_restore = run2_norm.get("restore", {})
    if not isinstance(r1_restore, dict):
        r1_restore = {}
    if not isinstance(r2_restore, dict):
        r2_restore = {}
    r1_deltas = run1_norm.get("deltas_ms", {})
    r2_deltas = run2_norm.get("deltas_ms", {})
    if not isinstance(r1_deltas, dict):
        r1_deltas = {}
    if not isinstance(r2_deltas, dict):
        r2_deltas = {}
    r1_stages = run1_norm.get("stages", {})
    r2_stages = run2_norm.get("stages", {})
    if not isinstance(r1_stages, dict):
        r1_stages = {}
    if not isinstance(r2_stages, dict):
        r2_stages = {}

    run1_wall_ms = _get_t0_wall_ms(run1_norm)
    run2_wall_ms = _get_t0_wall_ms(run2_norm)
    run1_modal_to_return_ms = r1.get("modal_to_return_ms") or _extract_modal_to_browser(run1_norm)
    run2_modal_to_return_ms = r2.get("modal_to_return_ms") or _extract_modal_to_browser(run2_norm)
    run1_modal_to_browser_ms = r1.get("modal_to_browser_ms")
    run2_modal_to_browser_ms = r2.get("modal_to_browser_ms")

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
        "run1_total_input_execution_ms": r1.get("total_input_execution_ms"),
        "run2_total_input_execution_ms": r2.get("total_input_execution_ms"),
        "run1_trace": run1_norm,
        "run2_trace": run2_norm,
        "run1_schema_ok": run1_norm.get("schema_ok", False),
        "run2_schema_ok": run2_norm.get("schema_ok", False),
        "run1_timing_quality": run1_norm.get("timing_quality", ""),
        "run2_timing_quality": run2_norm.get("timing_quality", ""),
        "run1_timing_quality_reason": run1_norm.get("timing_quality_reason", ""),
        "run2_timing_quality_reason": run2_norm.get("timing_quality_reason", ""),
        "run1_missing_timing_fields": run1_norm.get("missing_timing_fields", []),
        "run2_missing_timing_fields": run2_norm.get("missing_timing_fields", []),
        "run1_trace_version": run1_norm.get("trace_version", ""),
        "run2_trace_version": run2_norm.get("trace_version", ""),
    }

    # Phase 3A: extract diagnostic string fields from restore
    _PHASE3A_DIAG_STR_FIELDS = (
        "preload_mode", "preload_mode_source", "preload_env_raw",
        "preload_skipped", "preload_skip_reason",
        "preload_unknown_profiles", "disable_restore_warmup_for_z_image",
        "enable_warmup", "direct_warmup_load_unet_flag", "direct_warmup_load_clip_flag",
        "active_profile_lookup_attempted", "active_profile_found", "active_profile_source",
        "active_profile_workflow_hash", "active_profile_token",
        "warmup_profile_selected", "warmup_profile_source", "warmup_profile_token",
        "warmup_profile_workflow_hash", "warmup_profile_stack",
        "preload_eligibility_active_next", "preload_eligibility_unknown_profiles",
        "clip_cache_size_at_start", "clip_cache_size_after_warmup",
        "preload_eligibility_known_good_check",
        "disable_restore_warmup_for_z_image_effective",
        "direct_warmup_z_image_guard_skipped", "direct_warmup_skip_reason",
    )
    for label, restore in [("run1", r1_restore), ("run2", r2_restore)]:
        if isinstance(restore, dict):
            for k, v in restore.items():
                if isinstance(v, (int, float)):
                    summary[f"{label}_{k}"] = v
                elif k in _PHASE3A_DIAG_STR_FIELDS and v is not None:
                    summary[f"{label}_{k}"] = str(v)

    for label, d in [("run1", r1), ("run2", r2)]:
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, (int, float)):
                    if k not in summary or summary[f"{label}_{k}"] is None:
                        summary[f"{label}_{k}"] = v

    # Phase 2: direct route / result route metadata
    for label, trace_norm in [("run1", run1_norm), ("run2", run2_norm)]:
        if isinstance(trace_norm, dict):
            for _f in ("result_route", "direct_route_used", "direct_fallback_to_legacy", "direct_fallback_reason"):
                _v = trace_norm.get(_f)
                if _v is not None and _v != "" and _v is not False:
                    summary[f"{label}_{_f}"] = str(_v)

    for label, trace_norm, derived_d in [("run1", run1_norm, r1), ("run2", run2_norm, r2)]:
        for f in ("dependency_validation_result", "dependency_validation_cache_layer",
                  "dependency_validation_cache_hit", "dependency_validation_reason",
                  "dependency_validation_baked_hash", "dependency_validation_current_hash",
                  "dependency_validation_changed_nodes",
                  "dependency_total_ms",
                  "dependency_pre_key_check_ms", "dependency_baked_manifest_load_ms",
                  "dependency_source_root_resolve_ms", "dependency_fingerprint_ms",
                  "dependency_cache_key_ms", "dependency_memory_lookup_ms",
                  "dependency_sentinel_lookup_ms", "dependency_full_validation_ms",
                  "dependency_sentinel_write_ms"):
            v = derived_d.get(f) if isinstance(derived_d, dict) else None
            if v is None:
                v = trace_norm.get(f)
            if v is not None:
                summary[f"{label}_{f}"] = str(v)

    if extra:
        summary.update(extra)
    _write_json(run_dir / "summary.json", summary)

    # ── summary.md ──
    def _fmt(v):
        if v is None:
            return "None"
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)

    lines = [
        f"status: {status}",
        "",
        "## Status",
        f"status: {status}",
        f"run1_output_returned: {bool(r1_stages.get('t9_modal_return'))}",
        f"run2_output_returned: {bool(r2_stages.get('t9_modal_return'))}",
        f"run1_schema_ok: {summary.get('run1_schema_ok', False)}",
        f"run2_schema_ok: {summary.get('run2_schema_ok', False)}",
        "",
        "## Wall / Return Timing",
        f"run1_wall_ms: {_fmt(run1_wall_ms)}",
        f"run2_wall_ms: {_fmt(run2_wall_ms)}",
        f"run1_modal_to_return_ms: {_fmt(run1_modal_to_return_ms)}",
        f"run2_modal_to_return_ms: {_fmt(run2_modal_to_return_ms)}",
        f"run1_modal_to_browser_ms: {_fmt(r1.get('modal_to_browser_ms'))}",
        f"run2_modal_to_browser_ms: {_fmt(r2.get('modal_to_browser_ms'))}",
        f"run1_client_to_local_materialized_ms: {_fmt(r1.get('client_to_local_materialized_ms'))}",
        f"run2_client_to_local_materialized_ms: {_fmt(r2.get('client_to_local_materialized_ms'))}",
        f"run1_local_dispatch_to_modal_entry_ms: {_fmt(r1.get('local_dispatch_to_modal_entry_ms'))}",
        f"run2_local_dispatch_to_modal_entry_ms: {_fmt(r2.get('local_dispatch_to_modal_entry_ms'))}",
        "",
        "## Internal Execution",
        f"run1_total_input_execution_ms: {_fmt(r1.get('total_input_execution_ms'))}",
        f"run2_total_input_execution_ms: {_fmt(r2.get('total_input_execution_ms'))}",
        f"run1_modal_entry_to_prompt_start_ms: {_fmt(r1.get('modal_entry_to_prompt_start_ms'))}",
        f"run2_modal_entry_to_prompt_start_ms: {_fmt(r2.get('modal_entry_to_prompt_start_ms'))}",
        f"run1_restore_end_to_prompt_start_ms: {_fmt(r1.get('restore_end_to_prompt_start_ms'))}",
        f"run2_restore_end_to_prompt_start_ms: {_fmt(r2.get('restore_end_to_prompt_start_ms'))}",
        f"run1_prompt_start_to_sampler_start_ms: {_fmt(r1.get('prompt_start_to_sampler_start_ms'))}",
        f"run2_prompt_start_to_sampler_start_ms: {_fmt(r2.get('prompt_start_to_sampler_start_ms'))}",
        f"run1_execution_start_to_sampler_start_ms: {_fmt(r1.get('execution_start_to_sampler_start_ms'))}",
        f"run2_execution_start_to_sampler_start_ms: {_fmt(r2.get('execution_start_to_sampler_start_ms'))}",
        f"run1_sampler_ms: {_fmt(r1.get('sampler_ms'))}",
        f"run2_sampler_ms: {_fmt(r2.get('sampler_ms'))}",
        f"run1_sampler_progress_ms: {_fmt(r1.get('sampler_progress_ms'))}",
        f"run2_sampler_progress_ms: {_fmt(r2.get('sampler_progress_ms'))}",
        f"run1_sampler_end_to_outputs_collected_ms: {_fmt(r1.get('sampler_end_to_outputs_collected_ms'))}",
        f"run2_sampler_end_to_outputs_collected_ms: {_fmt(r2.get('sampler_end_to_outputs_collected_ms'))}",
        f"run1_output_collection_total_ms: {_fmt(r1.get('output_collection_total_ms'))}",
        f"run2_output_collection_total_ms: {_fmt(r2.get('output_collection_total_ms'))}",
        "",
        "## Loader Timing",
        f"run1_clip_load_ms: {_fmt(r1.get('clip_load_ms'))}",
        f"run2_clip_load_ms: {_fmt(r2.get('clip_load_ms'))}",
        f"run1_clip_encode_ms: {_fmt(r1.get('clip_encode_ms'))}",
        f"run2_clip_encode_ms: {_fmt(r2.get('clip_encode_ms'))}",
        f"run1_unet_node_wait_ms: {_fmt(r1.get('unet_node_wait_ms'))}",
        f"run2_unet_node_wait_ms: {_fmt(r2.get('unet_node_wait_ms'))}",
        f"run1_vae_node_wait_ms: {_fmt(r1.get('vae_node_wait_ms'))}",
        f"run2_vae_node_wait_ms: {_fmt(r2.get('vae_node_wait_ms'))}",
        "",
        "## Phase 2 — Local Path Timing",
        f"run1_result_route: {run1_norm.get('result_route', 'legacy')}",
        f"run2_result_route: {run2_norm.get('result_route', 'legacy')}",
        f"run1_local_prepare_ms: {_fmt(r1.get('local_prepare_ms'))}",
        f"run2_local_prepare_ms: {_fmt(r2.get('local_prepare_ms'))}",
        f"run1_modal_handle_resolve_ms: {_fmt(r1.get('modal_handle_resolve_ms'))}",
        f"run2_modal_handle_resolve_ms: {_fmt(r2.get('modal_handle_resolve_ms'))}",
        f"run1_modal_call_submit_ms: {_fmt(r1.get('modal_call_submit_ms'))}",
        f"run2_modal_call_submit_ms: {_fmt(r2.get('modal_call_submit_ms'))}",
        f"run1_modal_queue_or_start_gap_ms: {_fmt(r1.get('modal_queue_or_start_gap_ms'))}",
        f"run2_modal_queue_or_start_gap_ms: {_fmt(r2.get('modal_queue_or_start_gap_ms'))}",
        f"run1_modal_return_to_local_receive_ms: {_fmt(r1.get('modal_return_to_local_receive_ms'))}",
        f"run2_modal_return_to_local_receive_ms: {_fmt(r2.get('modal_return_to_local_receive_ms'))}",
        f"run1_local_history_poll_ms: {_fmt(r1.get('local_history_poll_ms'))}",
        f"run2_local_history_poll_ms: {_fmt(r2.get('local_history_poll_ms'))}",
        f"run1_local_materialize_ms: {_fmt(r1.get('local_materialize_ms'))}",
        f"run2_local_materialize_ms: {_fmt(r2.get('local_materialize_ms'))}",
        f"run1_local_save_ms: {_fmt(r1.get('local_save_ms'))}",
        f"run2_local_save_ms: {_fmt(r2.get('local_save_ms'))}",
        f"run1_local_response_send_ms: {_fmt(r1.get('local_response_send_ms'))}",
        f"run2_local_response_send_ms: {_fmt(r2.get('local_response_send_ms'))}",
        f"run1_modal_return_to_browser_ms: {_fmt(r1.get('modal_return_to_browser_ms'))}",
        f"run2_modal_return_to_browser_ms: {_fmt(r2.get('modal_return_to_browser_ms'))}",
        f"run1_client_to_response_sent_ms: {_fmt(r1.get('client_to_response_sent_ms'))}",
        f"run2_client_to_response_sent_ms: {_fmt(r2.get('client_to_response_sent_ms'))}",
        f"run1_direct_route_used: {run1_norm.get('direct_route_used', False)}",
        f"run2_direct_route_used: {run2_norm.get('direct_route_used', False)}",
        f"run1_direct_fallback_to_legacy: {run1_norm.get('direct_fallback_to_legacy', '')}",
        f"run2_direct_fallback_to_legacy: {run2_norm.get('direct_fallback_to_legacy', '')}",
        "",
        "## Dependency Validation",
        f"run1_dependency_validation_ms: {_fmt(r1.get('dependency_validation_ms'))}",
        f"run2_dependency_validation_ms: {_fmt(r2.get('dependency_validation_ms'))}",
        f"run1_dependency_validation_result: {run1_norm.get('dependency_validation_result', '')}",
        f"run2_dependency_validation_result: {run2_norm.get('dependency_validation_result', '')}",
        f"run1_dependency_validation_cache_layer: {run1_norm.get('dependency_validation_cache_layer', '')}",
        f"run2_dependency_validation_cache_layer: {run2_norm.get('dependency_validation_cache_layer', '')}",
        f"run1_dependency_validation_cache_hit: {run1_norm.get('dependency_validation_cache_hit', '')}",
        f"run2_dependency_validation_cache_hit: {run2_norm.get('dependency_validation_cache_hit', '')}",
        f"run1_dependency_validation_reason: {run1_norm.get('dependency_validation_reason', '')}",
        f"run2_dependency_validation_reason: {run2_norm.get('dependency_validation_reason', '')}",
        f"run1_dependency_validation_baked_hash: {run1_norm.get('dependency_validation_baked_hash', '')}",
        f"run2_dependency_validation_baked_hash: {run2_norm.get('dependency_validation_baked_hash', '')}",
        f"run1_dependency_validation_current_hash: {run1_norm.get('dependency_validation_current_hash', '')}",
        f"run2_dependency_validation_current_hash: {run2_norm.get('dependency_validation_current_hash', '')}",
        f"run1_dependency_pre_key_check_ms: {_fmt(r1.get('dependency_pre_key_check_ms'))}",
        f"run2_dependency_pre_key_check_ms: {_fmt(r2.get('dependency_pre_key_check_ms'))}",
        f"run1_dependency_baked_manifest_load_ms: {_fmt(r1.get('dependency_baked_manifest_load_ms'))}",
        f"run2_dependency_baked_manifest_load_ms: {_fmt(r2.get('dependency_baked_manifest_load_ms'))}",
        f"run1_dependency_source_root_resolve_ms: {_fmt(r1.get('dependency_source_root_resolve_ms'))}",
        f"run2_dependency_source_root_resolve_ms: {_fmt(r2.get('dependency_source_root_resolve_ms'))}",
        f"run1_dependency_fingerprint_ms: {_fmt(r1.get('dependency_fingerprint_ms'))}",
        f"run2_dependency_fingerprint_ms: {_fmt(r2.get('dependency_fingerprint_ms'))}",
        f"run1_dependency_cache_key_ms: {_fmt(r1.get('dependency_cache_key_ms'))}",
        f"run2_dependency_cache_key_ms: {_fmt(r2.get('dependency_cache_key_ms'))}",
        f"run1_dependency_memory_lookup_ms: {_fmt(r1.get('dependency_memory_lookup_ms'))}",
        f"run2_dependency_memory_lookup_ms: {_fmt(r2.get('dependency_memory_lookup_ms'))}",
        f"run1_dependency_sentinel_lookup_ms: {_fmt(r1.get('dependency_sentinel_lookup_ms'))}",
        f"run2_dependency_sentinel_lookup_ms: {_fmt(r2.get('dependency_sentinel_lookup_ms'))}",
        f"run1_dependency_full_validation_ms: {_fmt(r1.get('dependency_full_validation_ms'))}",
        f"run2_dependency_full_validation_ms: {_fmt(r2.get('dependency_full_validation_ms'))}",
        f"run1_dependency_sentinel_write_ms: {_fmt(r1.get('dependency_sentinel_write_ms'))}",
        f"run2_dependency_sentinel_write_ms: {_fmt(r2.get('dependency_sentinel_write_ms'))}",
        "",
        "## Restore Timing",
        f"run1_restore_total_ms: {_fmt(r1_restore.get('restore_total_ms'))}",
        f"run2_restore_total_ms: {_fmt(r2_restore.get('restore_total_ms'))}",
        f"run1_cuda_warmup_ms: {_fmt(r1_restore.get('cuda_warmup_ms'))}",
        f"run2_cuda_warmup_ms: {_fmt(r2_restore.get('cuda_warmup_ms'))}",
        f"run1_gpu_state_ms: {_fmt(r1_restore.get('gpu_state_ms'))}",
        f"run2_gpu_state_ms: {_fmt(r2_restore.get('gpu_state_ms'))}",
        f"run1_warmup_preload_ms: {_fmt(r1_restore.get('warmup_preload_ms'))}",
        f"run2_warmup_preload_ms: {_fmt(r2_restore.get('warmup_preload_ms'))}",
        f"run1_ensure_models_ms: {_fmt(r1_restore.get('ensure_models_ms'))}",
        f"run2_ensure_models_ms: {_fmt(r2_restore.get('ensure_models_ms'))}",
        "",
        "## Preload / Warmup / Profile Diagnostics",
        f"run1_preload_mode: {_fmt(r1_restore.get('preload_mode'))}",
        f"run2_preload_mode: {_fmt(r2_restore.get('preload_mode'))}",
        f"run1_preload_mode_source: {_fmt(r1_restore.get('preload_mode_source'))}",
        f"run2_preload_mode_source: {_fmt(r2_restore.get('preload_mode_source'))}",
        f"run1_preload_skipped: {_fmt(r1_restore.get('preload_skipped'))}",
        f"run2_preload_skipped: {_fmt(r2_restore.get('preload_skipped'))}",
        f"run1_preload_skip_reason: {_fmt(r1_restore.get('preload_skip_reason'))}",
        f"run2_preload_skip_reason: {_fmt(r2_restore.get('preload_skip_reason'))}",
        f"run1_enable_warmup: {_fmt(r1_restore.get('enable_warmup'))}",
        f"run2_enable_warmup: {_fmt(r2_restore.get('enable_warmup'))}",
        f"run1_preload_unknown_profiles: {_fmt(r1_restore.get('preload_unknown_profiles'))}",
        f"run2_preload_unknown_profiles: {_fmt(r2_restore.get('preload_unknown_profiles'))}",
        f"run1_preload_eligibility_active_next: {_fmt(r1_restore.get('preload_eligibility_active_next'))}",
        f"run2_preload_eligibility_active_next: {_fmt(r2_restore.get('preload_eligibility_active_next'))}",
        f"run1_active_profile_source: {_fmt(r1_restore.get('active_profile_source'))}",
        f"run2_active_profile_source: {_fmt(r2_restore.get('active_profile_source'))}",
        f"run1_active_profile_workflow_hash: {_fmt(r1_restore.get('active_profile_workflow_hash'))}",
        f"run2_active_profile_workflow_hash: {_fmt(r2_restore.get('active_profile_workflow_hash'))}",
        f"run1_warmup_profile_selected: {_fmt(r1_restore.get('warmup_profile_selected'))}",
        f"run2_warmup_profile_selected: {_fmt(r2_restore.get('warmup_profile_selected'))}",
        f"run1_warmup_profile_source: {_fmt(r1_restore.get('warmup_profile_source'))}",
        f"run2_warmup_profile_source: {_fmt(r2_restore.get('warmup_profile_source'))}",
        f"run1_warmup_profile_token: {_fmt(r1_restore.get('warmup_profile_token'))}",
        f"run2_warmup_profile_token: {_fmt(r2_restore.get('warmup_profile_token'))}",
        f"run1_clip_cache_size_at_start: {_fmt(r1_restore.get('clip_cache_size_at_start'))}",
        f"run2_clip_cache_size_at_start: {_fmt(r2_restore.get('clip_cache_size_at_start'))}",
        f"run1_clip_cache_size_after_warmup: {_fmt(r1_restore.get('clip_cache_size_after_warmup'))}",
        f"run2_clip_cache_size_after_warmup: {_fmt(r2_restore.get('clip_cache_size_after_warmup'))}",
        "",
        "## Schema / Quality",
        f"run1_trace_version: {run1_norm.get('trace_version', '')}",
        f"run2_trace_version: {run2_norm.get('trace_version', '')}",
        f"run1_timing_quality: {run1_norm.get('timing_quality', '')}",
        f"run2_timing_quality: {run2_norm.get('timing_quality', '')}",
        f"run1_timing_quality_reason: {run1_norm.get('timing_quality_reason', '')}",
        f"run2_timing_quality_reason: {run2_norm.get('timing_quality_reason', '')}",
        f"run1_schema_ok: {summary.get('run1_schema_ok', False)}",
        f"run2_schema_ok: {summary.get('run2_schema_ok', False)}",
        f"run1_missing_timing_fields: {'; '.join(run1_norm.get('missing_timing_fields', [])) if isinstance(run1_norm.get('missing_timing_fields', []), list) else ''}",
        f"run2_missing_timing_fields: {'; '.join(run2_norm.get('missing_timing_fields', [])) if isinstance(run2_norm.get('missing_timing_fields', []), list) else ''}",
        "",
        "## Deltas (Raw)",
    ]
    for label, deltas in [("run1", r1_deltas), ("run2", r2_deltas)]:
        if isinstance(deltas, dict) and deltas:
            lines.append(f"### {label} Deltas")
            for k, v in deltas.items():
                if v is not None:
                    lines.append(f"  {label}_{k}: {_fmt(v)}")

    lines.append("")
    lines.append("## Legacy Total")
    lines.append(f"run1_total_ms: {_fmt(run1_total_ms)}")
    lines.append(f"run2_total_ms: {_fmt(run2_total_ms)}")

    with open(run_dir / "summary.md", "w", encoding="utf-8") as f:
        f.write("# Benchmark Summary\n\n")
        for line in lines:
            f.write(f"- {line}\n")

    _write_runs_csv(run_dir, run1_trace, run2_trace)


# ── Offline reprocess ────────────────────────────────────────────────────────


def _reprocess_run_dir(run_dir: str | Path) -> None:
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise ValueError(f"not a directory: {run_dir}")

    run1_trace: dict = {}
    run2_trace: dict = {}

    for label in ("run1", "run2"):
        trace_file = run_dir / f"{label}_trace.json"
        response_file = run_dir / f"{label}_response.json"

        trace = {}
        if trace_file.is_file():
            with open(trace_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                trace = data

        if response_file.is_file():
            with open(response_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                response_trace = _extract_trace_from_response(data)
                if response_trace:
                    merged = dict(response_trace)
                    merged.update(trace)
                    if "restore" not in merged and "restore" in response_trace:
                        merged["restore"] = response_trace["restore"]
                    if "restore" in trace and trace["restore"]:
                        merged["restore"] = trace["restore"]
                    trace = merged

        if label == "run1":
            run1_trace = trace
        else:
            run2_trace = trace

    summary_file = run_dir / "summary.json"
    status = "reprocessed"
    if summary_file.is_file():
        with open(summary_file, "r", encoding="utf-8") as f:
            old = json.load(f)
        if isinstance(old, dict) and old.get("status"):
            status = old["status"]

    _write_summary(run_dir, status, run1_trace, run2_trace)
    print(f"[reprocess] regenerated summary.md and runs.csv in {run_dir}")
    for label, t in [("run1", run1_trace), ("run2", run2_trace)]:
        stages = t.get("stages", {}) if isinstance(t, dict) else {}
        norm = _normalize_trace(t) if isinstance(t, dict) else {}
        derived = norm.get("derived_ms", {}) if isinstance(norm, dict) else {}
        print(f"[reprocess] {label} stages={len(stages)} derived_ms={len(derived)} "
              f"quality={norm.get('timing_quality', '')} "
              f"total_input_exec={derived.get('total_input_execution_ms')}")


def _print_banner(args: dict, local_reachable: bool) -> None:
    sep = "=" * 60
    print(sep)
    print("  Benchmark Modal — Startup")
    print(f"  deploy_mode:          {args.get('deploy_mode', 'existing')}")
    print(f"  local_restart_mode:   {'restart' if args.get('restart_local') else 'no-restart'}")
    print(f"  result_route:         {args.get('result_route', 'legacy')}")
    print(f"  app_name:             {args.get('app_name', '(default)')}")
    print(f"  function_name:        {args.get('function_name', '(default)')}")
    print(f"  fresh_container:      {'YES (best-effort)' if args.get('fresh_container') else 'NO'}")
    print(f"  local_comfyui_reachable: {'YES' if local_reachable else 'NO'}")
    if args.get('deploy') or args.get('force_deploy'):
        print(f"  will_deploy:          YES (reason: {'--force-deploy' if args.get('force_deploy') else '--deploy'})")
    else:
        print(f"  will_deploy:          NO")
    if args.get('restart_local'):
        print(f"  will_restart_local:   YES (reason: --restart-local)")
    else:
        print(f"  will_restart_local:   NO")
    print(f"  benchmark_run_dir:    {args.get('run_dir', '(not yet created)')}")
    print(sep)


def _check_local_reachable() -> bool:
    try:
        _json_request(LOCAL_SYSTEM_STATS_ROUTE, timeout=5)
        return True
    except Exception:
        return False


_RESULT_ROUTE_CHOICES = ("legacy", "direct")


def _parse_benchmark_args() -> dict:
    import sys

    # ── Defaults from env ──
    deploy_mode = os.environ.get("COMFYMODAL_BENCHMARK_DEPLOY_MODE", "existing").strip().lower()
    if deploy_mode not in ("existing", "deploy", "force_deploy"):
        deploy_mode = "existing"

    default_route = os.environ.get("COMFYMODAL_RESULT_ROUTE", "legacy").strip().lower()
    if default_route not in _RESULT_ROUTE_CHOICES:
        default_route = "legacy"

    args = {
        "result_route": default_route,
        "reprocess_dir": None,
        "compare_result_routes": None,
        "matrix_run": False,
        "deploy": False,
        "force_deploy": False,
        "no_deploy": False,
        "restart_local": False,
        "no_restart_local": False,
        "use_existing_deployment": True,
        "app_name": "",
        "function_name": "",
        "deploy_mode": deploy_mode,
        "set_preload_mode": None,
        "set_runtime_flags": [],
        "fresh_container": False,
    }
    argv = list(sys.argv)
    skip_next = False
    for i, a in enumerate(argv[1:], 1):
        if skip_next:
            skip_next = False
            continue
        if a == "--result-route" and i + 1 < len(argv):
            val = argv[i + 1].strip().lower()
            if val in _RESULT_ROUTE_CHOICES:
                args["result_route"] = val
            else:
                print(f"WARNING: invalid --result-route={val!r}, using {args['result_route']!r}")
            skip_next = True
        elif a == "--compare-result-routes" and i + 1 < len(argv):
            val = argv[i + 1].strip().lower()
            parts = [v.strip() for v in val.split(",") if v.strip() in _RESULT_ROUTE_CHOICES]
            if len(parts) >= 2:
                args["compare_result_routes"] = parts
                args["matrix_run"] = True
            else:
                print(f"WARNING: --compare-result-routes needs at least 2 values, got {parts}")
            skip_next = True
        elif a == "--reprocess" and i + 1 < len(argv):
            args["reprocess_dir"] = argv[i + 1]
            skip_next = True
        elif a == "--deploy":
            args["deploy"] = True
            args["use_existing_deployment"] = False
        elif a == "--force-deploy":
            args["force_deploy"] = True
            args["deploy"] = True
            args["use_existing_deployment"] = False
        elif a == "--no-deploy":
            args["no_deploy"] = True
            args["use_existing_deployment"] = True
        elif a == "--restart-local":
            args["restart_local"] = True
        elif a == "--no-restart-local":
            args["no_restart_local"] = True
            args["restart_local"] = False
        elif a == "--use-existing-deployment":
            args["use_existing_deployment"] = True
        elif a == "--app-name" and i + 1 < len(argv):
            args["app_name"] = argv[i + 1]
            skip_next = True
        elif a == "--function-name" and i + 1 < len(argv):
            args["function_name"] = argv[i + 1]
            skip_next = True
        elif a == "--set-preload-mode" and i + 1 < len(argv):
            args["set_preload_mode"] = argv[i + 1].strip().lower()
            skip_next = True
        elif a == "--set-runtime-flag" and i + 1 < len(argv):
            args["set_runtime_flags"].append(argv[i + 1].strip())
            skip_next = True
        elif a == "--fresh-container":
            args["fresh_container"] = True

    # ── Resolve deploy_mode from env + flags ──
    if args["force_deploy"]:
        args["deploy_mode"] = "force_deploy"
    elif args["deploy"]:
        args["deploy_mode"] = "deploy"
    elif args["no_deploy"] or args["use_existing_deployment"]:
        args["deploy_mode"] = "existing"
    elif deploy_mode in ("existing", "deploy", "force_deploy"):
        args["deploy_mode"] = deploy_mode

    # ── Resolve restart_local from env + flags ──
    if args["no_restart_local"]:
        args["restart_local"] = False
    elif args["restart_local"]:
        pass  # already True

    return args


def _run_benchmark_sequence(snapshot: dict, run_dir: Path, log_path: Path, result_route: str) -> tuple[dict, dict, str]:
    """Run a 2-prompt benchmark sequence with the given result route.
    
    Returns (run1_trace, run2_trace, status).
    """
    run1_trace: dict = {}
    run2_trace: dict = {}
    status = "ok"
    current_stage = "run1"
    run1_completed = False

    try:
        current_stage = "run1"
        run1_payload = _build_prompt_payload(snapshot, f"run1_{result_route}", result_route=result_route)
        run1_prompt_id = _submit_prompt(run1_payload)
        if result_route == "direct":
            _append_log(log_path, f"run1 using direct result route prompt_id={run1_prompt_id}")
            run1_entry = _poll_direct_result(run1_prompt_id)
            run1_trace_raw = run1_entry.get("trace", {})
            if isinstance(run1_trace_raw, dict):
                run1_trace = dict(run1_trace_raw)
            else:
                run1_trace = {}
            run1_trace["result_route"] = "direct"
            run1_trace["direct_route_used"] = True
            run1_restore = run1_entry.get("result", {}).get("_restore_timing", {})
            if isinstance(run1_restore, dict) and run1_restore:
                run1_trace["restore"] = run1_restore
            _write_json(run_dir / f"run1_{result_route}_response.json", {"prompt_id": run1_prompt_id, "direct_result": run1_entry})
        else:
            run1_entry = _poll_history(run1_prompt_id)
            run1_meta = run1_entry.get("meta", {}) if isinstance(run1_entry, dict) else {}
            run1_trace = dict(run1_meta.get("trace", {}))
            run1_restore = run1_meta.get("restore_timing", {})
            if isinstance(run1_restore, dict) and run1_restore:
                run1_trace["restore"] = run1_restore
            run1_trace["result_route"] = "legacy"
            _write_json(run_dir / f"run1_{result_route}_response.json", {"prompt_id": run1_prompt_id, "history": run1_entry})
        _write_json(run_dir / f"run1_{result_route}_trace.json", run1_trace if isinstance(run1_trace, dict) else {})
        _append_log(log_path, f"run1 ({result_route}) complete prompt_id={run1_prompt_id}")
        run1_completed = True

        time.sleep(10)

        current_stage = "run2"
        run2_payload = _build_prompt_payload(snapshot, f"run2_{result_route}", result_route=result_route)
        run2_prompt_id = _submit_prompt(run2_payload)
        if result_route == "direct":
            _append_log(log_path, f"run2 using direct result route prompt_id={run2_prompt_id}")
            run2_entry = _poll_direct_result(run2_prompt_id)
            run2_trace_raw = run2_entry.get("trace", {})
            if isinstance(run2_trace_raw, dict):
                run2_trace = dict(run2_trace_raw)
            else:
                run2_trace = {}
            run2_trace["result_route"] = "direct"
            run2_trace["direct_route_used"] = True
            run2_restore = run2_entry.get("result", {}).get("_restore_timing", {})
            if isinstance(run2_restore, dict) and run2_restore:
                run2_trace["restore"] = run2_restore
            _write_json(run_dir / f"run2_{result_route}_response.json", {"prompt_id": run2_prompt_id, "direct_result": run2_entry})
        else:
            run2_entry = _poll_history(run2_prompt_id)
            run2_meta = run2_entry.get("meta", {}) if isinstance(run2_entry, dict) else {}
            run2_trace = dict(run2_meta.get("trace", {}))
            run2_restore = run2_meta.get("restore_timing", {})
            if isinstance(run2_restore, dict) and run2_restore:
                run2_trace["restore"] = run2_restore
            run2_trace["result_route"] = "legacy"
            _write_json(run_dir / f"run2_{result_route}_response.json", {"prompt_id": run2_prompt_id, "history": run2_entry})
        _write_json(run_dir / f"run2_{result_route}_trace.json", run2_trace if isinstance(run2_trace, dict) else {})
        _append_log(log_path, f"run2 ({result_route}) complete prompt_id={run2_prompt_id}")

    except TimeoutError as exc:
        _append_log(log_path, f"timeout ({result_route}): {exc}")
        status = _classify_failure_status(current_stage, exc, run1_completed)
    except Exception as exc:
        _append_log(log_path, f"error ({result_route}): {exc}")
        status = _classify_failure_status(current_stage, exc, run1_completed)

    return run1_trace, run2_trace, status


def main() -> int:
    import sys

    _benchmark_args = _parse_benchmark_args()

    # ── Reprocess mode: no Modal, no local server ──
    if _benchmark_args.get("reprocess_dir"):
        target = Path(_benchmark_args["reprocess_dir"])
        if not target.is_dir():
            print(f"error: not a directory: {target}", file=sys.stderr)
            return 1
        _reprocess_run_dir(target)
        return 0

    # ── Runtime flag setter mode: call Modal function, no deploy, exit ──
    if _benchmark_args.get("set_preload_mode"):
        mode = _benchmark_args["set_preload_mode"]
        print(f"[benchmark] setting preload_mode={mode} via Modal function (no deploy)...")
        result = _call_set_preload_mode(mode)
        print(f"  result: {result}")
        return 0

    if _benchmark_args.get("set_runtime_flags"):
        for flag in _benchmark_args["set_runtime_flags"]:
            if "=" not in flag:
                print(f"WARNING: ignoring --set-runtime-flag {flag!r} (format: NAME=VALUE)")
                continue
            name, value = flag.split("=", 1)
            name = name.strip()
            value = value.strip()
            print(f"[benchmark] setting runtime flag {name}={value} via Modal function (no deploy)...")
            result = _call_set_runtime_flag(name, value)
            print(f"  result: {result}")
        return 0

    # ── Fresh container info ──
    if _benchmark_args.get("fresh_container"):
        print("[benchmark] --fresh-container requested")
        print("  WARNING: cannot force a fresh Modal container without redeploy or")
        print("  manual container stop. Marking results as best-effort only.")
        print("  To fully guarantee fresh container, run: modal app stop comfyui")

    run_dir = _ensure_run_dir()
    _benchmark_args["run_dir"] = str(run_dir)
    log_path = run_dir / "benchmark.log"

    # ── Check local health ──
    local_reachable = _check_local_reachable()
    _print_banner(_benchmark_args, local_reachable)

    # ── Fast-fail: if no-restart and local unreachable ──
    if not _benchmark_args["restart_local"] and not local_reachable:
        msg = (
            f"Local ComfyUI is not reachable at {LOCAL_BASE_URL}. "
            f"Start it manually or run with --restart-local to auto-launch.\n"
            f"  Suggested: {COMFYUI_LAUNCHER} (or your usual launcher)"
        )
        print(f"ERROR: {msg}", file=sys.stderr)
        _write_summary(run_dir, "local_unreachable", {}, {}, {"error": msg})
        return 1

    # ── Restart local if requested ──
    if _benchmark_args["restart_local"]:
        _terminate_local_comfyui()
        _append_log(log_path, "terminated previous local ComfyUI processes")
        _launch_local_comfyui()
        _append_log(log_path, f"launched local ComfyUI via {COMFYUI_LAUNCHER.name}")
        _wait_for_local_health()
        _append_log(log_path, "local ComfyUI health check passed")
    elif not local_reachable:
        # Should not reach here (caught above), but be safe
        msg = "Local ComfyUI unreachable in no-restart mode"
        print(f"ERROR: {msg}", file=sys.stderr)
        _write_summary(run_dir, "local_unreachable", {}, {}, {"error": msg})
        return 1
    else:
        _append_log(log_path, "using already-running local ComfyUI (no restart)")

    # ── Load snapshot ──
    try:
        snapshot = _load_latest_snapshot()
    except Exception as exc:
        print(f"ERROR: failed to load snapshot: {exc}", file=sys.stderr)
        _write_summary(run_dir, "snapshot_missing", {}, {}, {"error": str(exc)})
        return 1
    _write_json(run_dir / "workflow_snapshot.json", snapshot)
    _append_log(log_path, f"loaded workflow snapshot hash={snapshot.get('workflow_hash', '')}")

    # ── Deploy if requested ──
    current_stage = "snapshot"
    run1_completed = False
    should_deploy = _benchmark_args.get("deploy_mode") in ("deploy", "force_deploy")
    if should_deploy:
        current_stage = "deploy"
        deploy_reason = "--force-deploy" if _benchmark_args.get("force_deploy") else "--deploy"
        print(f"[benchmark] deploying Modal app ({deploy_reason})...")
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
                _write_summary(run_dir, "deploy_failed", {}, {}, {
                    "deploy_returncode": batch_result.returncode,
                    "direct_deploy_returncode": direct_result.returncode,
                })
                return 1
        # After deploy, local must be running for the benchmark
        if not _benchmark_args["restart_local"] and not _check_local_reachable():
            print("[benchmark] deploy done, launching local ComfyUI...")
            _launch_local_comfyui()
            _wait_for_local_health()
        _append_log(log_path, "deploy completed")
    else:
        _append_log(log_path, "skipping Modal deploy (no --deploy flag)")
        print("[benchmark] skipping Modal deploy (use --deploy or --force-deploy to deploy)")

    # ── Ensure local health for the actual benchmark ──
    if not _benchmark_args["restart_local"]:
        # Double-check health after possible deploy
        if not _check_local_reachable():
            print("[benchmark] local ComfyUI not reachable, re-checking...")
            try:
                _wait_for_local_health(timeout_s=30)
            except TimeoutError:
                msg = "Local ComfyUI unreachable before benchmark"
                print(f"ERROR: {msg}", file=sys.stderr)
                _write_summary(run_dir, "local_unreachable", {}, {}, {"error": msg})
                return 1

    # ── Run benchmark ──
    try:
        if _benchmark_args.get("matrix_run"):
            # ── Matrix mode: run all specified result routes ──
            routes = _benchmark_args["compare_result_routes"]
            all_traces: dict[str, dict] = {}
            all_statuses = {}
            for route in routes:
                _append_log(log_path, f"=== Starting matrix run for route={route} ===")
                r1, r2, st = _run_benchmark_sequence(snapshot, run_dir, log_path, route)
                all_traces[f"{route}_run1"] = r1
                all_traces[f"{route}_run2"] = r2
                all_statuses[route] = st
                _append_log(log_path, f"=== Matrix run complete for route={route} status={st} ===")
                time.sleep(5)

            overall_status = "ok" if all(s == "ok" for s in all_statuses.values()) else "partial"
            _write_summary(run_dir, overall_status,
                           all_traces.get("legacy_run1", {}) or all_traces.get("direct_run1", {}),
                           all_traces.get("legacy_run2", {}) or all_traces.get("direct_run2", {}),
                           {"benchmark_args": dict(_benchmark_args), "matrix_routes": routes, "all_traces": all_traces})
            return 0 if overall_status == "ok" else 1
        else:
            # ── Single mode: run with configured result route ──
            route = _benchmark_args.get("result_route", "legacy")
            _append_log(log_path, f"=== Starting single run for route={route} ===")
            run1_trace, run2_trace, status = _run_benchmark_sequence(snapshot, run_dir, log_path, route)
            _write_summary(run_dir, status, run1_trace, run2_trace, {"benchmark_args": dict(_benchmark_args)})
            return 0 if status == "ok" else 1

    except TimeoutError as exc:
        _append_log(log_path, f"timeout: {exc}")
        _write_summary(run_dir, "timeout", {}, {}, {"error": str(exc)})
        return 1
    except Exception as exc:
        _append_log(log_path, f"error: {exc}")
        _write_summary(run_dir, "error", {}, {}, {"error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
