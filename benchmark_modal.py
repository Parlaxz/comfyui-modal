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

    for label, restore in [("run1", r1_restore), ("run2", r2_restore)]:
        if isinstance(restore, dict):
            for k, v in restore.items():
                if isinstance(v, (int, float)):
                    summary[f"{label}_{k}"] = v

    for label, d in [("run1", r1), ("run2", r2)]:
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, (int, float)):
                    if k not in summary or summary[f"{label}_{k}"] is None:
                        summary[f"{label}_{k}"] = v

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


def main() -> int:
    import sys

    if "--reprocess" in sys.argv:
        idx = sys.argv.index("--reprocess")
        if idx + 1 >= len(sys.argv):
            print("usage: python benchmark_modal.py --reprocess <run_dir>", file=sys.stderr)
            return 1
        target = Path(sys.argv[idx + 1])
        if not target.is_dir():
            print(f"error: not a directory: {target}", file=sys.stderr)
            return 1
        _reprocess_run_dir(target)
        return 0

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
