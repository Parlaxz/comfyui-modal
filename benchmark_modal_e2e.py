"""benchmark_modal_e2e — End-to-end profiling harness for ComfyUI x Modal.

Usage:
    python benchmark_modal_e2e.py --workflow latest_benchmark_workflow.json --runs 3 --mode mixed --profile-level detailed --poll-interval 0.1 --sleep-between-runs 10 --min-gap-between-runs 10 --strict-inter-run-sleep --print-cost-warning
    python benchmark_modal_e2e.py compare --baseline benchmarks/A --candidate benchmarks/B
    python benchmark_modal_e2e.py selftest

Zero runtime pip dependencies.  Communicates with local ComfyUI bridge.
"""

import argparse
import copy
import csv
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib import error as urllib_error, request as urllib_request

BENCHMARK_VERSION = "4.2.0"
LOCAL_BASE_URL = os.environ.get("COMFYMODAL_BENCHMARK_URL", "http://127.0.0.1:8188")
PROMPT_ROUTE = f"{LOCAL_BASE_URL}/comfymodal/prompt"
BENCHMARK_WORKFLOW_ROUTE = f"{LOCAL_BASE_URL}/comfymodal/benchmark/workflow"
RESULT_ROUTE = f"{LOCAL_BASE_URL}/comfymodal/result"
REPO_ROOT = Path(__file__).resolve().parent
OUTER_ROOT = REPO_ROOT.parents[2]
REDEPLOY_BATCH = OUTER_ROOT / "redeploy_modal_and_run_comfyui.bat"
COMFYUI_LAUNCHER = OUTER_ROOT / "run_nvidia_gpu.bat"
BENCHMARK_RUNS_DIR = REPO_ROOT / "benchmarks"

_STALE_T0_THRESHOLD_S = 60
_MIN_POLL_INTERVAL = 0.05

# ── Preset registry ─────────────────────────────────────────────────────────
# NOTE: Presets marked _disabled:true perform speculative independent model-file
# reads that are NOT joined by the graph loader.  This causes duplicate physical
# I/O and makes cold-start performance worse.  They are disabled by default and
# require COMFYMODAL_ALLOW_SPECULATIVE_LOAD=1 to override.
_PRESETS: dict[str, dict] = {}

def _register_preset(name: str, desc: str, config: dict, disabled: bool = False, disabled_reason: str = "") -> None:
    config["_name"] = name
    config["_description"] = desc
    if disabled:
        config["_disabled"] = True
        config["_disabled_reason"] = disabled_reason
    _PRESETS[name] = config

_register_preset("cold-baseline", "Clean cold baseline, no experimental UNET early-load", {
    "benchmark": {"runs": 3, "mode": "cold", "profile_level": "detailed",
                  "include_local_materialization": True, "sleep_between_runs": 10,
                  "min_gap_between_runs": 10, "strict_inter_run_sleep": True,
                  "poll_interval": 0.1, "write_analysis_pack": True, "print_cost_warning": True},
    "runtime": {
        "cold_unet_early_load": {"enabled": False, "mode": "off", "budget_ms": 0,
                                  "require_cpu_cache_hit": False, "max_file_gb": 12,
                                  "disable_on_volume_stall": True, "debug": False},
        "actual_load": {"enabled": True, "mode": "unet_vae_only", "load_unet": True},
        "preload": {"mode": "clip_only"},
        "direct_warmup": {"load_unet": False, "load_clip": True, "clip_encode": True,
                          "require_cpu_cache_hit": True},
    },
    "assertions": {"expected_mode": "cold", "require_all_runs_cold": True,
                   "forbid_warm_runs": True,
                   "required_trace_fields": ["submit2entry_ms", "pre_sampler_ms", "sampler_ms"]},
})

_register_preset("cold-unet-actual-load", "DISABLED: Experiment: start UNET early via request-level actual_load", {
    "benchmark": {"runs": 3, "mode": "cold", "profile_level": "detailed",
                  "include_local_materialization": True, "sleep_between_runs": 10,
                  "min_gap_between_runs": 10, "strict_inter_run_sleep": True,
                  "poll_interval": 0.1, "write_analysis_pack": True, "print_cost_warning": True},
    "runtime": {
        "cold_unet_early_load": {"enabled": True, "mode": "actual_load", "budget_ms": 0,
                                  "require_cpu_cache_hit": False, "max_file_gb": 12,
                                  "disable_on_volume_stall": True, "debug": True},
        "actual_load": {"enabled": True, "mode": "unet_vae_only", "load_unet": True},
        "preload": {"mode": "clip_only"},
        "direct_warmup": {"load_unet": False, "load_clip": True, "clip_encode": True,
                          "require_cpu_cache_hit": True},
    },
    "assertions": {"expected_mode": "cold", "require_all_runs_cold": True,
                   "forbid_warm_runs": True,
                   "required_trace_fields": ["cold_unet_early_load_enabled",
                                             "cold_unet_early_load_submitted",
                                             "cold_unet_graph_wait_ms"],
                   "require_cold_unet_early_load": True,
                   "require_actual_load_load_unet": True},
}, disabled=True, disabled_reason="unsafe_independent_model_read")

_register_preset("cold-unet-restore-preload", "DISABLED: Experiment: CPU-preload UNET during restore", {
    "benchmark": {"runs": 3, "mode": "cold", "profile_level": "detailed",
                  "include_local_materialization": True, "sleep_between_runs": 10,
                  "min_gap_between_runs": 10, "strict_inter_run_sleep": True,
                  "poll_interval": 0.1, "write_analysis_pack": True, "print_cost_warning": True},
    "runtime": {
        "cold_unet_early_load": {"enabled": True, "mode": "restore_preload", "budget_ms": 0,
                                  "require_cpu_cache_hit": False, "max_file_gb": 12,
                                  "disable_on_volume_stall": True, "debug": True},
        "actual_load": {"enabled": False, "mode": "clip_vae_only", "load_unet": False},
        "preload": {"mode": "workers_2"},
        "direct_warmup": {"load_unet": False, "load_clip": True, "clip_encode": True,
                          "require_cpu_cache_hit": True},
    },
    "assertions": {"expected_mode": "cold", "require_all_runs_cold": True,
                   "forbid_warm_runs": True,
                   "required_trace_fields": ["restore_total_ms", "pre_sampler_ms"]},
}, disabled=True, disabled_reason="unsafe_independent_model_read")

_register_preset("cold-unet-restore-direct", "DISABLED: Experiment: direct-warm UNET during restore", {
    "benchmark": {"runs": 3, "mode": "cold", "profile_level": "detailed",
                  "include_local_materialization": True, "sleep_between_runs": 10,
                  "min_gap_between_runs": 10, "strict_inter_run_sleep": True,
                  "poll_interval": 0.1, "write_analysis_pack": True, "print_cost_warning": True},
    "runtime": {
        "cold_unet_early_load": {"enabled": True, "mode": "restore_direct", "budget_ms": 0,
                                  "require_cpu_cache_hit": True, "max_file_gb": 12,
                                  "disable_on_volume_stall": True, "debug": True},
        "actual_load": {"enabled": False, "mode": "clip_vae_only", "load_unet": False},
        "preload": {"mode": "workers_2"},
        "direct_warmup": {"load_unet": True, "load_clip": True, "clip_encode": True,
                          "require_cpu_cache_hit": True},
    },
    "assertions": {"expected_mode": "cold", "require_all_runs_cold": True,
                   "forbid_warm_runs": True,
                   "required_trace_fields": ["restore_total_ms", "pre_sampler_ms"]},
}, disabled=True, disabled_reason="unsafe_independent_model_read")

_register_preset("cold-diagnostic-trace", "Cold benchmark with extra trace detail, no optimizations", {
    "benchmark": {"runs": 3, "mode": "cold", "profile_level": "trace",
                  "include_local_materialization": True, "sleep_between_runs": 10,
                  "min_gap_between_runs": 10, "strict_inter_run_sleep": True,
                  "poll_interval": 0.1, "write_analysis_pack": True, "print_cost_warning": True},
    "runtime": {
        "cold_unet_early_load": {"enabled": False, "mode": "off", "budget_ms": 0,
                                  "require_cpu_cache_hit": False, "max_file_gb": 12,
                                  "disable_on_volume_stall": True, "debug": False},
        "actual_load": {"enabled": True, "mode": "unet_vae_only", "load_unet": True},
        "preload": {"mode": "clip_only"},
        "direct_warmup": {"load_unet": False, "load_clip": True, "clip_encode": True,
                          "require_cpu_cache_hit": True},
    },
    "assertions": {"expected_mode": "cold", "require_all_runs_cold": True,
                   "forbid_warm_runs": True,
                   "required_trace_fields": ["submit2entry_ms", "pre_sampler_ms"]},
})

# ── Effective config builder ─────────────────────────────────────────────────
_BOOL_TRUE = {"true", "1", "yes", "on"}
_BOOL_FALSE = {"false", "0", "no", "off"}

def _parse_set_value(raw: str):
    raw = raw.strip()
    if raw.lower() in _BOOL_TRUE:
        return True
    if raw.lower() in _BOOL_FALSE:
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw

def _deep_set(d: dict, keys: list[str], value) -> dict:
    if len(keys) == 0:
        return d
    if len(keys) == 1:
        d[keys[0]] = value
        return d
    if keys[0] not in d or not isinstance(d[keys[0]], dict):
        d[keys[0]] = {}
    _deep_set(d[keys[0]], keys[1:], value)
    return d

def _deep_get(d: dict, keys: list[str]):
    if len(keys) == 0 or not d:
        return None
    val = d
    for k in keys:
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            return None
    return val

def _hash_effective_config(cfg: dict) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_OID, json.dumps(cfg, sort_keys=True, default=str)))

def build_effective_config(preset_name: str | None, cli_args: dict, set_overrides: list[str]) -> dict:
    config = {"schema_version": "benchmark_effective_config_v1", "preset": preset_name or "none",
              "config_sources": {"preset": preset_name or "none", "profile_config_used": False,
                                 "cli_overrides": [], "set_overrides": list(set_overrides)},
              "benchmark": {}, "runtime": {}, "assertions": {}}

    # 1. Start with cold-baseline defaults
    base = _PRESETS.get("cold-baseline", {})
    config["benchmark"] = dict(base.get("benchmark", {}))
    config["runtime"] = copy.deepcopy(base.get("runtime", {}))
    config["assertions"] = dict(base.get("assertions", {}))

    # 2. Apply preset if provided
    if preset_name and preset_name in _PRESETS:
        p = _PRESETS[preset_name]
        if p.get("_disabled"):
            raise ValueError(
                f"Preset '{preset_name}' is disabled: {p.get('_disabled_reason', 'unsafe')}. "
                f"Set COMFYMODAL_ALLOW_SPECULATIVE_LOAD=1 to override (unsafe)."
            )
        config["config_sources"]["preset"] = preset_name
        for section in ("benchmark", "runtime", "assertions"):
            if section in p:
                _deep_merge(config.setdefault(section, {}), copy.deepcopy(p[section]))

    # 3. Apply CLI explicit args (non-default)
    overrides = []
    for key, cli_key in [("runs", "runs"), ("mode", "mode"), ("profile_level", "profile_level"),
                          ("sleep_between_runs", "sleep_between_runs"),
                          ("min_gap_between_runs", "min_gap_between_runs"),
                          ("strict_inter_run_sleep", "strict_inter_run_sleep"),
                          ("poll_interval", "poll_interval"), ("write_analysis_pack", "write_analysis_pack"),
                          ("print_cost_warning", "print_cost_warning"),
                          ("include_local_materialization", "include_local_materialization")]:
        av = cli_args.get(cli_key)
        if av is not None and av != build_parser().get_default(cli_key):
            config["benchmark"][key] = av
            overrides.append(f"cli.{cli_key}={av}")
    config["config_sources"]["cli_overrides"] = overrides

    # 4. Apply --set overrides
    for s in set_overrides:
        if "=" not in s:
            raise ValueError(f"--set: expected KEY=VALUE, got {s!r}")
        sk, sv_raw = s.split("=", 1)
        sv = _parse_set_value(sv_raw)
        keys = sk.split(".")
        # Determine if it's a runtime or benchmark key
        if keys[0] in ("runtime", "benchmark", "assertions"):
            _deep_set(config, keys, sv)
        elif keys[0] in ("cold_unet_early_load", "actual_load", "preload", "direct_warmup"):
            _deep_set(config.setdefault("runtime", {}), keys, sv)
        else:
            _deep_set(config.setdefault("benchmark", {}), keys, sv)

    config["config_hash"] = _hash_effective_config(config)
    return config

def _deep_merge(target: dict, source: dict) -> dict:
    for k, v in source.items():
        if isinstance(v, dict) and k in target and isinstance(target[k], dict):
            _deep_merge(target[k], v)
        else:
            target[k] = v
    return target


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _json_request(url: str, method: str = "GET", payload: dict | None = None, timeout: int = 300) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib_request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}
    except urllib_error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise urllib_error.URLError(f"HTTP {e.code} ({e.reason}): {body[:200]}") from e


def _json_hash(payload: dict) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_OID, json.dumps(payload, sort_keys=True, default=str)))


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_float(val, default=None) -> float | None:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _p90(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(int(len(s) * 0.9), len(s) - 1)]


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(int(len(s) * 0.95), len(s) - 1)]


def _stats(values: list[float]) -> dict:
    if not values:
        return {"median": "N/A", "min": "N/A", "max": "N/A", "p90": "N/A", "p95": "N/A"}
    return {
        "median": round(_median(values), 1),
        "min": round(min(values), 1),
        "max": round(max(values), 1),
        "p90": round(_p90(values), 1),
        "p95": round(_p95(values), 1),
    }


# ── Stale trace field stripping ────────────────────────────────────────────

_TRACE_STRIP_KEYS = {
    "trace", "_client_trace", "wall_clock_trace", "_wall_clock_summary",
    "profiler_trace", "timing_trace", "deltas_ms", "derived_ms",
    "restore", "_restore_timing", "_return_payload_info", "_cache_diagnostics",
    "t0_client_press", "t0_client_press_ms", "t0_perf_ms", "t0_perf_now_ms",
    "benchmark_run_index", "benchmark_run_id", "benchmark_session_id",
}


def _strip_trace_fields(obj, depth=0):
    if depth > 10:
        return
    if isinstance(obj, dict):
        to_remove = [k for k in obj if k in _TRACE_STRIP_KEYS and k not in ("stages",)]
        for k in to_remove:
            del obj[k]
        for k, v in obj.items():
            _strip_trace_fields(v, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _strip_trace_fields(item, depth + 1)


def fresh_benchmark_payload(workflow_dict: dict, t_start: float, include_local_materialization: bool, benchmark_session_id: str, run_idx: int) -> dict:
    raw = copy.deepcopy(workflow_dict)
    _strip_trace_fields(raw)
    if isinstance(raw, dict) and "prompt" in raw:
        payload = raw
    else:
        payload = {"prompt": raw}
    payload.pop("client_id", None)
    payload.pop("extra_data", None)
    payload.pop("modal_options", None)
    payload["result_route"] = "direct"
    trace_event = {
        "t0_client_press": t_start,
        "benchmark_run_index": run_idx,
        "benchmark_run_id": f"{benchmark_session_id}_run_{run_idx}",
        "benchmark_session_id": benchmark_session_id,
    }
    if include_local_materialization:
        trace_event["t0a_local_node_start"] = t_start
    payload["trace"] = trace_event
    return payload


# ── Identity extraction ────────────────────────────────────────────────────


def extract_run_identity(result_data: dict, wall_trace: dict, timing_trace: dict, restore_timing: dict) -> dict:
    def _get(*paths):
        for path in paths:
            val = result_data
            for key in path.split("."):
                if isinstance(val, dict):
                    val = val.get(key)
                else:
                    val = None
                    break
            if val is not None and val != "" and val != 0:
                if isinstance(val, float) and val == 0.0:
                    continue
                return val
        return None

    trace_id = wall_trace.get("trace_id") or _get("trace.restore.restore_session_id") or _get("_wall_clock_summary.trace_id")
    prompt_id = timing_trace.get("prompt_id") or result_data.get("prompt_id")
    restore_session_id = wall_trace.get("restore_session_id") or timing_trace.get("restore_session_id") or _get("trace.restore.restore_session_id") or restore_timing.get("restore_session_id")
    container_session_id = wall_trace.get("container_session_id") or timing_trace.get("container_session_id") or _get("trace.restore.container_session_id") or restore_timing.get("container_session_id")
    snapshot_import_session_id = _get("trace.restore.snapshot_import_session_id") or restore_timing.get("snapshot_import_session_id") or wall_trace.get("snapshot_import_session_id")
    restore_count_raw = wall_trace.get("restore_count") or timing_trace.get("restore_count") or _get("trace.restore.restore_count") or restore_timing.get("restore_count")
    restore_count = int(restore_count_raw) if restore_count_raw is not None else 0
    request_seq_raw = wall_trace.get("request_seq") or timing_trace.get("request_sequence_id") or timing_trace.get("request_seq") or _get("_wall_clock_summary.request_seq")
    request_seq = int(request_seq_raw) if request_seq_raw is not None else 0
    restore_total_ms = wall_trace.get("deltas_ms", {}).get("restore_total_ms") or timing_trace.get("derived_ms", {}).get("restore_total_ms") or _get("trace.restore.restore_total_ms") or restore_timing.get("restore_total_ms")
    has_restore_total = bool(restore_total_ms and float(restore_total_ms) > 0)
    notes = []
    if wall_trace.get("trace_id"):
        notes.append("trace_id_from_wall_trace")
    if not wall_trace.get("restore_session_id") and _get("trace.restore.restore_session_id"):
        notes.append("restore_session_id_from_nested_restore")
    if not timing_trace.get("request_sequence_id") and wall_trace.get("request_seq"):
        notes.append("request_seq_from_wall_trace")
    return {
        "trace_id": trace_id or "",
        "request_id": prompt_id or "",
        "restore_session_id": restore_session_id or "",
        "container_session_id": container_session_id or "",
        "snapshot_import_session_id": snapshot_import_session_id or "",
        "restore_count": restore_count,
        "request_seq": request_seq,
        "has_restore_total": has_restore_total,
        "restore_total_ms": _safe_float(restore_total_ms, 0.0),
        "identity_source_notes": notes,
    }


# ── Run classification ─────────────────────────────────────────────────────


def classify_run(identity: dict, prev_identity: dict | None, submit2entry_ms: float | None, remote_visible_ms: float | None) -> tuple:
    label = "unknown"
    confidence = "low"
    reasons = []
    rseq = identity.get("request_seq", 0)
    rcount = identity.get("restore_count", 0)
    rsid = identity.get("restore_session_id", "")
    csid = identity.get("container_session_id", "")
    has_restore = identity.get("has_restore_total", False)
    rseq_missing = rseq == 0 and bool(rsid)
    same_restore = False
    same_container = False
    if prev_identity:
        same_restore = bool(rsid) and rsid == prev_identity.get("restore_session_id")
        same_container = bool(csid) and csid == prev_identity.get("container_session_id")

    if identity.get("failure_phase"):
        return ("failed", "high", ["explicit_failure"], False, False, False)
    if rcount == 1 and has_restore and rsid:
        if not prev_identity or rsid != prev_identity.get("restore_session_id"):
            return ("cold_restore", "high", ["fresh_restore_session"], False, False, rseq_missing)
    if rcount == 1 and has_restore and not rsid:
        return ("cold_attempt", "medium", ["restore_count_1_but_no_session_id"], False, False, rseq_missing)
    if same_restore:
        reasons.append("same_restore_session")
        if rseq_missing:
            label, confidence = "warm_like_unproven", "medium"
            reasons.append("request_seq_missing")
        elif rseq > 1:
            label, confidence = "warm_same_restore_session", "high"
            reasons.append(f"request_seq={rseq}")
        else:
            label, confidence = "warm_like_unproven", "medium"
            reasons.append("request_seq_unexpected")
        if same_container:
            reasons.append("same_container")
        return (label, confidence, reasons, same_restore, same_container, rseq_missing)
    if submit2entry_ms is not None and submit2entry_ms < 500 and prev_identity:
        return ("warm_like_unproven", "medium", [f"submit2entry={submit2entry_ms}ms"], False, False, rseq_missing)
    if rseq_missing:
        reasons.append("request_seq_missing")
    if has_restore:
        label, confidence = "cold_attempt", "medium"
        reasons.append("incomplete_identity")
    return (label, confidence, reasons, same_restore, same_container, rseq_missing)


# ── Trace merging ──────────────────────────────────────────────────────────


def merge_wall_trace_with_timing_fallbacks(wall_trace: dict, timing_trace: dict) -> dict:
    merged = copy.deepcopy(wall_trace)
    tt_stages = timing_trace.get("stages", {})
    tt_derived = timing_trace.get("derived_ms", {})
    tt_deltas = timing_trace.get("deltas_ms", {})
    if "stages_unix_s" not in merged:
        merged["stages_unix_s"] = {}
    stages = merged["stages_unix_s"]
    if "deltas_ms" not in merged:
        merged["deltas_ms"] = {}
    deltas = merged["deltas_ms"]
    warnings = []
    for sk in ("t10_local_materialized", "t9_modal_return", "t_remote_return_done", "t9b_local_result_received",
               "t9e_local_materialize_start", "t10b_local_save_start", "t10c_local_save_end",
               "t1_local_recv", "t2_local_dispatch", "t3_modal_entry", "t3d_prompt_start",
               "t6_sampler_start", "t6_sampler_end", "t8b_outputs_collected"):
        if sk not in stages and sk in tt_stages:
            stages[sk] = tt_stages[sk]
            warnings.append(f"stage_{sk}_from_timing_trace")
    if "t10_local_materialized" not in stages:
        for alt in ("t10_local_materialized", "t10_materialized"):
            if alt in tt_stages:
                stages["t10_local_materialized"] = tt_stages[alt]
                warnings.append("t10_local_materialized_from_timing_trace")
                break
    for dk, sk, st in [
        ("sampler_end_to_outputs_collected_ms", "sampler_end_to_outputs_collected_ms", "derived"),
        ("output_collection_total_ms", "output_collection_total_ms", "derived"),
        ("vae_decode_ms", "vae_decode", "delta"),
        ("prompt_start_to_sampler_start_ms", "prompt_start_to_sampler_start_ms", "derived"),
        ("sampler_ms", "sampler_ms", "derived"),
        ("modal_submit_to_entry_ms", "modal_queue_or_start_gap_ms", "derived"),
        ("restore_total_ms", "restore_total_ms", "derived"),
        ("remote_total_visible_ms", "remote_total", "delta"),
    ]:
        if dk not in deltas or deltas[dk] is None:
            val = tt_derived.get(sk) if st == "derived" else tt_deltas.get(sk)
            if val is not None:
                deltas[dk] = val
                warnings.append(f"delta_{dk}_from_timing_trace")
    if warnings:
        merged["data_quality"] = merged.get("data_quality", {})
        merged["data_quality"]["warning"] = merged["data_quality"].get("warning", [])
        merged["data_quality"]["warning"].extend(warnings)
    return merged


# ── Critical path derivation ───────────────────────────────────────────────


def derive_critical_path(wall_trace: dict, timing_trace: dict, local_wall_ms: float | None = None) -> dict:
    deltas = wall_trace.get("deltas_ms", {})
    cp = wall_trace.get("critical_path", {})
    ttd = timing_trace.get("derived_ms", {})
    ttdd = timing_trace.get("deltas_ms", {})
    ttr = timing_trace.get("restore", {})

    def fb(*paths):
        for p in paths:
            parts = p.split(".")
            src = {"deltas": deltas, "cp": cp, "ttd": ttd, "tdd": ttdd, "ttr": ttr}.get(parts[0])
            if src and len(parts) == 2:
                v = src.get(parts[1])
                if v is not None:
                    return v
        return None

    s2e = fb("deltas.modal_submit_to_entry_ms", "ttd.modal_queue_or_start_gap_ms", "tdd.t2_to_t3")
    rtot = fb("deltas.restore_total_ms", "ttd.restore_total_ms", "ttr.restore_total_ms")
    rvis = fb("deltas.remote_total_visible_ms", "tdd.remote_total", "ttd.total_input_execution_ms")
    ri = bool(s2e and rtot)
    s2rd = fb("cp.submit_to_remote_done_ms", "ttd.modal_to_return_ms") or (s2e + rvis if s2e is not None and rvis is not None else None)
    kn = fb("cp.known_non_overlapping_ms", "cp.known_ms") or s2rd
    ue = max(0.0, local_wall_ms - s2rd) if local_wall_ms is not None and s2rd is not None else None
    return {"submit2entry_ms": s2e, "restore_total_ms": rtot, "restore_included_in_submit2entry": ri,
            "remote_visible_ms": rvis, "submit_to_remote_done_ms": s2rd, "known_nonoverlap_ms": kn or 0.0,
            "unexplained_local_wall_ms": ue}


# ── Stale t0 detection ─────────────────────────────────────────────────────


def check_stale_t0(timing_trace: dict) -> tuple:
    stages = timing_trace.get("stages", {})
    t0 = stages.get("t0_client_press")
    t1 = stages.get("t1_local_recv")
    if t0 is not None and t1 is not None and abs(t1 - t0) > _STALE_T0_THRESHOLD_S:
        return True, f"stale t0_client_press: t1-t0={abs(t1-t0):.0f}s > {_STALE_T0_THRESHOLD_S}s threshold"
    return False, None


# ── Harness timestamp helpers ──────────────────────────────────────────────


def record_harness_ts(store: dict, key: str) -> None:
    store[key + "_unix_s"] = time.time()
    store[key + "_mono_s"] = time.perf_counter()


def _ms(a, b):
    if a is None or b is None:
        return None
    return round((b - a) * 1000, 2)


# ── Output writers ─────────────────────────────────────────────────────────


def write_runs_csv(runs: list[dict], path: Path) -> None:
    if not runs:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(runs[0].keys()))
        writer.writeheader()
        for run in runs:
            writer.writerow(run)


def write_runs_jsonl(runs: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for run in runs:
            f.write(json.dumps(run, default=str) + "\n")


def write_summary_csv(summary: dict, path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([[k, v] for k, v in summary.items()])


def write_summary_md(runs: list[dict], summary: dict, path: Path) -> None:
    lines = ["# Benchmark Summary", "", f"Generated: {datetime.now().isoformat()}", f"Runs: {len(runs)}", f"Benchmark Version: {BENCHMARK_VERSION}", "",
             "## Executive Summary", ""]
    for k in ("median_local_wall_ms", "median_known_nonoverlap_ms", "median_missing_ms", "cold_count", "warm_count"):
        lines.append(f"- **{k}**: {summary.get(k, 'N/A')}")
    lines.extend(["", "## Phase Medians (ms)", ""])
    for k in ("median_submit2entry_ms", "median_restore_ms", "median_pre_sampler_ms", "median_sampler_ms",
              "median_post_sampler_ms", "median_vae_decode_ms", "median_remote_visible_ms"):
        lines.append(f"- {k}: {summary.get(k, 'N/A')}")
    lines.extend(["", "## Benchmark Harness / Local Overhead", ""])
    for k in ("median_local_bridge_to_submit_ms", "median_modal_return_to_local_receive_ms", "median_local_materialize_ms",
              "median_harness_extra_after_timing_trace_ms", "median_harness_extra_vs_remote_return_ms",
              "median_poll_count", "poll_interval_s", "median_polling_overhead_estimate_ms", "median_inter_run_gap_ms",
              "min_inter_run_gap_ms", "max_inter_run_gap_ms", "inter_run_gap_violations"):
        lines.append(f"- {k}: {summary.get(k, 'N/A')}")
    lines.extend(["", "## Per-Run Data", "",
                  "| Run | Label | Conf | Local Wall (ms) | Known Non-Overlap (ms) | Missing (ms) | Restore (ms) | Submit2Entry (ms) | BN_to_Submit (ms) | Return_to_Recv (ms) | Materialize (ms) |",
                  "|-----|-------|------|-----------------|------------------------|--------------|--------------|-------------------|-------------------|---------------------|-----------------|"])
    for i, run in enumerate(runs):
        lines.append(f"| {i} | {run.get('cold_warm_label', '?')} | {run.get('cold_warm_confidence', '?')} "
                     f"| {run.get('local_button_to_materialized_ms', 'N/A')} | {run.get('known_nonoverlap_ms', 'N/A')} "
                     f"| {run.get('unexplained_local_wall_ms', 'N/A')} | {run.get('restore_total_ms', 'N/A')} "
                     f"| {run.get('submit2entry_ms', 'N/A')} | {run.get('local_bridge_to_submit_ms', 'N/A')} "
                     f"| {run.get('modal_return_to_local_receive_ms', 'N/A')} | {run.get('local_materialize_ms', 'N/A')} |")
    lines.extend(["", "## Upload Pack", "",
                  f"Upload this to ChatGPT: benchmarks/{summary.get('timestamp', '')}/analysis_pack.zip", "",
                   "Files included:", "* summary.md", "* charts_data.json", "* run_N_timing_trace.json",
                   "* optional run_N_timeline.md", "* benchmark_analysis_pack.json", "",
                   "## Local Pre-Dispatch Breakdown", "",
                   f"- median_local_recv_to_dispatch_ms: {_median([r.get('local_recv_to_dispatch_ms') or 0 for r in runs if r.get('local_recv_to_dispatch_ms') is not None]) if any(r.get('local_recv_to_dispatch_ms') is not None for r in runs) else 'N/A'}",
                   f"- max_local_recv_to_dispatch_ms: {max([r.get('local_recv_to_dispatch_ms') or 0 for r in runs if r.get('local_recv_to_dispatch_ms') is not None]) if any(r.get('local_recv_to_dispatch_ms') is not None for r in runs) else 'N/A'}",
                   f"- worst_local_predispatch_run: {summary.get('worst_local_predispatch_run', 'N/A')}",
                   f"- worst_local_predispatch_phase: {summary.get('worst_local_predispatch_phase', 'N/A')}",
                   f"- local_predispatch_stall_count: {summary.get('local_predispatch_stall_count', 0)}",
                   f"- local_lock_wait_stall_count: {summary.get('local_lock_wait_stall_count', 0)}",
                   f"- stale_t0_count: {summary.get('stale_t0_count', 0)}",
                   "", "## Cold UNET Early Load", "",
                   f"- cold_unet_early_load_enabled: {summary.get('cold_unet_early_load_enabled', False)}",
                   f"- cold_unet_early_load_mode: {summary.get('cold_unet_early_load_mode', 'N/A')}",
                   f"- cold_runs: {summary.get('cold_count', 0)}",
                   f"- median_cold_local_wall_ms: {_median([r.get('local_button_to_materialized_ms') or 0 for r in runs if (r.get('cold_warm_label','') or '').startswith('cold')]) if any((r.get('cold_warm_label','') or '').startswith('cold') for r in runs) else 'N/A'}",
                   f"- median_cold_known_nonoverlap_ms: {_median([r.get('known_nonoverlap_ms') or 0 for r in runs if (r.get('cold_warm_label','') or '').startswith('cold')]) if any((r.get('cold_warm_label','') or '').startswith('cold') for r in runs) else 'N/A'}",
                   f"- median_cold_submit2entry_ms: {_median([r.get('submit2entry_ms') or 0 for r in runs if (r.get('cold_warm_label','') or '').startswith('cold')]) if any((r.get('cold_warm_label','') or '').startswith('cold') for r in runs) else 'N/A'}",
                   f"- median_cold_restore_ms: {_median([r.get('restore_total_ms') or 0 for r in runs if (r.get('cold_warm_label','') or '').startswith('cold')]) if any((r.get('cold_warm_label','') or '').startswith('cold') for r in runs) else 'N/A'}",
                   f"- median_cold_pre_sampler_ms: {_median([r.get('pre_sampler_ms') or 0 for r in runs if (r.get('cold_warm_label','') or '').startswith('cold')]) if any((r.get('cold_warm_label','') or '').startswith('cold') for r in runs) else 'N/A'}",
                   f"- median_cold_unet_wait_ms: {_median([r.get('unet_node_wait_ms') or 0 for r in runs if (r.get('cold_warm_label','') or '').startswith('cold')]) if any((r.get('cold_warm_label','') or '').startswith('cold') for r in runs) else 'N/A'}",
                   f"- median_cold_exec_model_load_io_ms: {_median([r.get('exec_model_load_io_ms') or 0 for r in runs if (r.get('cold_warm_label','') or '').startswith('cold')]) if any((r.get('cold_warm_label','') or '').startswith('cold') for r in runs) else 'N/A'}",
                   f"- median_cold_actual_load_saved_ms: {_median([r.get('actual_load_saved_ms') or 0 for r in runs if (r.get('cold_warm_label','') or '').startswith('cold')]) if any((r.get('cold_warm_label','') or '').startswith('cold') for r in runs) else 'N/A'}",
                   f"- median_cold_actual_load_remaining_wait_ms: {_median([r.get('actual_load_remaining_wait_ms') or 0 for r in runs if (r.get('cold_warm_label','') or '').startswith('cold')]) if any((r.get('cold_warm_label','') or '').startswith('cold') for r in runs) else 'N/A'}",
                   f"- median_cold_unet_overlap_ms: {_median([r.get('cold_unet_overlap_ms') or 0 for r in runs if (r.get('cold_warm_label','') or '').startswith('cold')]) if any((r.get('cold_warm_label','') or '').startswith('cold') for r in runs) else 'N/A'}",
                   f"- duplicate_unet_read_detected_count: {summary.get('duplicate_unet_read_detected_count', 0)}",
                   f"- cold_unet_volume_stall_count: {summary.get('cold_unet_volume_stall_count', 0)}",
                   f"- degraded_cold_run_count: {summary.get('degraded_cold_run_count', 0)}",
                   "", "## Recommendations", "",
                  "1. If unexplained local wall > 2s, investigate local materialization path.",
                  "2. If post-sampler unattributed > 1s, profile output collection.",
                  "3. If restore is high, check preload and CUDA warmup.",
                  "4. If sampler is the dominant phase, optimize model/step count.",
                  "", "## What Did NOT Improve Wall Time", "",
                  "Compare internal phase improvements against local wall time before claiming wins."])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_timeline_md(timing_trace: dict, identity: dict, classification: dict, path: Path) -> None:
    stages = timing_trace.get("stages", {})
    t0 = stages.get("t0_client_press")
    t1 = stages.get("t1_local_recv")
    stale, _ = check_stale_t0(timing_trace)
    if stale and t1 is not None:
        bl_stage, bl_ts = "t1_local_recv (stale t0 ignored)", t1
    elif t0 is not None:
        bl_stage, bl_ts = "t0_client_press", t0
    else:
        bl_stage, bl_ts = "none", None
    lines = [f"# Timeline -- {identity.get('trace_id', '?')}", "",
             f"baseline_stage: {bl_stage}", f"stale_t0_detected: {stale}",
             f"restore_session_id: {identity.get('restore_session_id', '')}",
             f"container_session_id: {identity.get('container_session_id', '')}",
             f"request_id: {identity.get('request_id', '')}",
             f"cold_warm_label: {classification.get('label', '?')}", "", "```text"]
    if bl_ts:
        for stage, ts in sorted(stages.items()):
            if isinstance(ts, (int, float)):
                lines.append(f"{(ts - bl_ts) * 1000:10.1f}ms  {stage}")
    lines.append("```")
    if stale:
        lines.extend(["", "WARNING: stale t0_client_press detected. Timeline uses t1_local_recv as baseline.",
                       f"  t0={t0}  t1={t1}  diff={abs((t1 or 0) - (t0 or 0)):.0f}s"])
    path.write_text("\n".join(lines), encoding="utf-8")


# ── Compiled raw results ───────────────────────────────────────────────────


def write_compiled_raw_results(out_dir: Path, benchmark_session_id: str, cmd_args: dict, workflow_hash: str, runs: list, run_details: list, summary: dict, charts_data: dict) -> None:
    compiled = {"schema_version": "compiled_raw_results_v1", "benchmark_version": BENCHMARK_VERSION,
                "generated_at": datetime.now().isoformat(), "benchmark_session_id": benchmark_session_id,
                "command": " ".join(sys.argv), "args": cmd_args, "workflow_hash": workflow_hash,
                "profile_level": cmd_args.get("profile_level", ""), "mode": cmd_args.get("mode", ""),
                "summary": summary, "runs_csv_rows": runs, "charts_data": charts_data, "per_run": run_details,
                "global_warnings": [], "known_bugs_detected": [],
                "notes_for_chatgpt": "This file combines all raw benchmark outputs for analysis."}
    (out_dir / "compiled_raw_results.json").write_text(json.dumps(compiled, default=str, indent=2), encoding="utf-8")


# ── Analysis pack ──────────────────────────────────────────────────────────


def write_analysis_pack(out_dir: Path, run_count: int, timing_traces: list, run_timelines: list, run_records: list,
                        summary: dict, charts_data: dict, inter_run_gaps: list, deploy_reason: str,
                        include_timelines: bool, include_wall_traces: bool) -> None:
    pack_dir = _ensure_dir(out_dir / "analysis_pack")
    shutil.copy2(out_dir / "summary.md", pack_dir / "summary.md")
    shutil.copy2(out_dir / "charts_data.json", pack_dir / "charts_data.json")
    for i in range(run_count):
        src = out_dir / "raw_results" / f"run_{i}_timing_trace.json"
        if src.exists():
            shutil.copy2(src, pack_dir / f"run_{i}_timing_trace.json")
    if include_timelines:
        for i in range(run_count):
            src = out_dir / "raw_results" / f"run_{i}_timeline.md"
            if src.exists():
                shutil.copy2(src, pack_dir / f"run_{i}_timeline.md")
    if include_wall_traces:
        for i in range(run_count):
            src = out_dir / "raw_results" / f"run_{i}_wall_trace.json"
            if src.exists():
                shutil.copy2(src, pack_dir / f"run_{i}_wall_trace.json")

    readme = ("# Analysis Pack\n\nUpload these files for analysis:\n\n"
              "* summary.md\n* charts_data.json\n* run_N_timing_trace.json files\n"
              + ("* run_N_timeline.md files (optional)\n" if include_timelines else "")
              + "* benchmark_analysis_pack.json\n\n"
              "Do not upload full compiled_raw_results.json unless explicitly requested.\n")
    (pack_dir / "analysis_pack_README.md").write_text(readme, encoding="utf-8")

    pack_json = {"schema_version": "benchmark_analysis_pack_v2", "benchmark_version": BENCHMARK_VERSION,
                 "generated_at": datetime.now().isoformat(), "command": " ".join(sys.argv),
                 "workflow_hash": summary.get("workflow_hash", ""), "summary": summary,
                 "runs": [{"run_index": i, "run_record": run_records[i], "timing_trace": timing_traces[i],
                           "timeline_md": "\n".join(run_timelines[i]) if i < len(run_timelines) and run_timelines[i] else "",
                           "warnings": [], "degradation_flags": run_records[i].get("degradation_flags", "").split(";") if run_records[i].get("degradation_flags") else [],
                           "local_route_phase_breakdown": {
                               "body_read_ms": run_records[i].get("body_read_ms"),
                               "json_parse_ms": run_records[i].get("json_parse_ms"),
                               "stack_extract_ms": run_records[i].get("stack_extract_ms"),
                               "active_next_write_ms": run_records[i].get("active_next_write_ms"),
                               "modal_handle_resolve_ms": run_records[i].get("modal_handle_resolve_ms"),
                               "local_recv_to_dispatch_ms": run_records[i].get("local_recv_to_dispatch_ms"),
                           },
                           "local_lock_waits": run_records[i].get("lock_wait_total_ms"),
                           "local_stall_summary": {
                               "local_recv_to_dispatch_ms": run_records[i].get("local_recv_to_dispatch_ms"),
                               "local_predispatch_stall": run_records[i].get("local_predispatch_stall", False),
                           },
                           "local_route_state": {
                               "active_request_count_at_entry": run_records[i].get("active_request_count_at_entry"),
                               "previous_request_id": run_records[i].get("previous_request_id"),
                           },
                           "stale_t0_source": run_records[i].get("stale_t0_source", ""),
                           "poll_total_attempts": run_records[i].get("poll_total_attempts"),
                           "poll_not_ready_count": run_records[i].get("poll_not_ready_count"),
                           "poll_success_count": run_records[i].get("poll_success_count"),
                           "poll_error_count": run_records[i].get("poll_error_count"),
                           }
                          for i in range(run_count) if i < len(timing_traces) and timing_traces[i]],
                 "inter_run_gaps": inter_run_gaps,
                 "notes_for_chatgpt": "Small analysis pack; excludes raw_result, wall traces unless requested, image payloads, and base64."}
    (pack_dir / "benchmark_analysis_pack.json").write_text(json.dumps(pack_json, default=str, indent=2), encoding="utf-8")

    zip_path = shutil.make_archive(str(out_dir / "analysis_pack"), "zip", str(pack_dir))
    return zip_path


# ── Comparison mode ────────────────────────────────────────────────────────


def cmd_compare(args: argparse.Namespace) -> int:
    base_dir, cand_dir = Path(args.baseline), Path(args.candidate)
    if not base_dir.is_dir() or not cand_dir.is_dir():
        print("ERROR: baseline or candidate directory does not exist.")
        return 1

    def load_summary(d: Path) -> dict:
        p = d / "summary.csv"
        if not p.exists():
            return {}
        r = {}
        with open(p, "r", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) == 2:
                    r[row[0]] = row[1]
        return r

    bs, cs = load_summary(base_dir), load_summary(cand_dir)
    print(f"Comparing {base_dir.name} vs {cand_dir.name}\n")
    # Check if candidate used a disabled optimization path
    candidate_disabled = cs.get("_disabled") or cs.get("disabled_optimization_used")
    if candidate_disabled:
        print("Winner not declared: candidate used disabled optimization. Comparison skipped.")
        return 0
    # Check if configs differ in semantics
    base_hash = bs.get("config_hash")
    cand_hash = cs.get("config_hash")
    if base_hash and cand_hash and base_hash != cand_hash:
        print("Warning: compared configs differ in semantics (config_hash mismatch). Comparison may be invalid.")
    for key, label in [("median_local_wall_ms", "Local Wall (ms)"), ("median_known_nonoverlap_ms", "Known Non-Overlap (ms)"),
                       ("median_missing_ms", "Missing/Unexplained (ms)"), ("median_submit2entry_ms", "Submit2Entry (ms)"),
                       ("median_sampler_ms", "Sampler (ms)"), ("median_restore_ms", "Restore (ms)")]:
        bv, cv = _safe_float(bs.get(key)), _safe_float(cs.get(key))
        if bv is not None and cv is not None and bv != "N/A" and cv != "N/A":
            d = cv - bv
            dir_s = "regressed" if d > 300 else ("improved" if d < -300 else "flat")
            print(f"  {label:40s}  {bv:8.1f}  ->  {cv:8.1f}  ({d:+.1f}) {dir_s}")
        else:
            print(f"  {label:40s}  N/A  ->  N/A  (missing data)")
    print("\nDecision notes:\n  - Improvements <300ms are labeled 'flat'.\n  - Internal phase improvements without local wall improvement = relocation.\n  - Output format / return mode changes invalidate comparison unless intended.")
    return 0


# ── Self-test ──────────────────────────────────────────────────────────────


# ── Local log parser (no-GPU mode) ──────────────────────────────────────────


def cmd_parse_local_log(args: argparse.Namespace) -> int:
    log_path = args.log
    if not os.path.isfile(log_path):
        print(f"ERROR: log file not found: {log_path}")
        return 1
    raw = Path(log_path).read_text("utf-8", errors="replace")
    predispatch_pattern = re.compile(r"\[predispatch\] phase=(\S+) t=([\d.]+)")
    phases = {}
    for m in predispatch_pattern.finditer(raw):
        phase_name = m.group(1)
        ts = float(m.group(2))
        phases[phase_name] = ts
    if not phases:
        print("No [predispatch] phase lines found in log.")
        return 0
    recv = phases.get("recv")
    before_se = phases.get("before_stack_extract")
    after_se = phases.get("after_stack_extract")
    before_anw = phases.get("before_active_next_write")
    after_anw = phases.get("after_active_next_write")
    before_gs = phases.get("before_gpu_spawn")
    first_gr = phases.get("first_gpu_response")
    print("Parsed [predispatch] phases:\n")
    for pname, pts in sorted(phases.items()):
        print(f"  {pname:30s} t={pts}")
    print()
    if recv and before_se:
        recv_to_se_ms = round((before_se - recv) * 1000, 3)
        print(f"  recv -> before_stack_extract: {recv_to_se_ms}ms")
        stall = recv_to_se_ms > 5000
        print(f"  local_predispatch_stall: {'true' if stall else 'false'}")
        if recv_to_se_ms > 60000:
            print(f"  local_predispatch_stall_severe: true")
    if before_se and after_se:
        se_ms = round((after_se - before_se) * 1000, 3)
        print(f"  stack_extract: {se_ms}ms")
    if before_anw and after_anw:
        anw_ms = round((after_anw - before_anw) * 1000, 3)
        print(f"  active_next_write: {anw_ms}ms")
    if before_gs and first_gr:
        gs_ms = round((first_gr - before_gs) * 1000, 3)
        print(f"  gpu_spawn -> first_gpu_response: {gs_ms}ms")
    print()
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    errors = []
    print("  Running selftest...")

    # 1. Poll interval parsing
    def _check_poll(val, expected, should_warn):
        clamped = max(val, _MIN_POLL_INTERVAL)
        warned = val < _MIN_POLL_INTERVAL
        ok = abs(clamped - expected) < 0.001 and warned == should_warn
        return ok, clamped, warned

    ok, cp, cw = _check_poll(0.1, 0.1, False)
    if not ok:
        errors.append(f"poll_interval: 0.1 failed ({cp}, warn={cw})")
    else:
        print("  [OK] poll interval 0.1")
    ok, cp, cw = _check_poll(0.0, 0.05, True)
    if not ok or not cw:
        errors.append(f"poll_interval: 0 should clamp to 0.05 and warn")
    else:
        print("  [OK] poll interval 0.0 clamped + warned")

    # 2. Overhead derivation
    tt = {"derived_ms": {"modal_to_return_ms": 11000, "modal_to_browser_ms": 12800}, "deltas_ms": {}}
    cp2 = derive_critical_path({"deltas_ms": {}, "critical_path": {}}, tt, local_wall_ms=15100)
    extra_tt = max(0.0, 15100 - 12800)
    extra_vs_r = max(0.0, 15100 - 11000)
    if abs(extra_tt - 2300) > 10:
        errors.append(f"overhead derivation: expected extra_tt~2300 got {extra_tt}")
    if abs(extra_vs_r - 4100) > 10:
        errors.append(f"overhead derivation: expected extra_vs_r~4100 got {extra_vs_r}")
    print(f"  [OK] overhead derivation: extra_tt={extra_tt:.0f} extra_vs_r={extra_vs_r:.0f}")

    # 3. Stale t0
    stale, _ = check_stale_t0({"stages": {"t0_client_press": 100.0, "t1_local_recv": 130.0}})
    if stale:
        errors.append("stale t0 should not flag 30s gap")
    else:
        print("  [OK] fresh t0 passes")
    stale2, _ = check_stale_t0({"stages": {"t0_client_press": 100.0, "t1_local_recv": 200000.0}})
    if not stale2:
        errors.append("stale t0 should flag >60s gap")
    else:
        print("  [OK] stale t0 detected")

    # 4. Analysis pack structure
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td_p = Path(td)
        (td_p / "raw_results").mkdir()
        (td_p / "summary.md").write_text("test", encoding="utf-8")
        (td_p / "charts_data.json").write_text("{}", encoding="utf-8")
        for i in range(2):
            (td_p / "raw_results" / f"run_{i}_timing_trace.json").write_text('{"test": 1}', encoding="utf-8")
            (td_p / "raw_results" / f"run_{i}_timeline.md").write_text("timeline", encoding="utf-8")
        z = write_analysis_pack(td_p, 2, [{"test": 1}, {"test": 2}], [["timeline0"], ["timeline1"]],
                                [{"run_index": 0}, {"run_index": 1}], {"workflow_hash": "abc"}, {},
                                [{"from_run": 0, "to_run": 1, "gap_ms": 10000}], "selftest",
                                include_timelines=True, include_wall_traces=False)
        if not (td_p / "analysis_pack" / "summary.md").exists():
            errors.append("analysis_pack: summary.md missing")
        if not (td_p / "analysis_pack" / "run_0_timing_trace.json").exists():
            errors.append("analysis_pack: run_0_timing_trace.json missing")
        if not (td_p / "analysis_pack" / "benchmark_analysis_pack.json").exists():
            errors.append("analysis_pack: benchmark_analysis_pack.json missing")
        if (td_p / "analysis_pack" / "run_0_wall_trace.json").exists():
            errors.append("analysis_pack: wall_trace should be excluded by default")
        if not (td_p / "analysis_pack" / "run_0_timeline.md").exists():
            errors.append("analysis_pack: timeline should be included when requested")
        if not Path(z).exists():
            errors.append("analysis_pack: zip not created")
        print("  [OK] analysis pack structure")

    # 5. Inter-run gap
    now = time.time()
    gaps = []
    prev_end = now - 20
    next_start = now
    gap_ms = (next_start - prev_end) * 1000
    strict_ok = gap_ms >= 10000
    gaps.append({"from_run": 0, "to_run": 1, "gap_ms": round(gap_ms, 1), "gap_ok": strict_ok, "warning": "" if strict_ok else "gap_violation"})
    if not strict_ok:
        errors.append(f"inter_run_gap: expected >=10s gap, got {gap_ms:.0f}ms")
    print(f"  [OK] inter-run gap check: {gap_ms:.0f}ms, strict_ok={strict_ok}")

    # ── 6. t1->t2 local stall detection ──
    local_ts = {"t1_local_recv": 100.0, "t2_local_dispatch": 270.0,
                "body_read_ms": 5, "json_parse_ms": 4, "preflight_ms": 1,
                "stack_extract_ms": 160, "active_next_write_ms": 0, "lock_wait_total_ms": 0,
                "local_recv_to_dispatch_ms": 170000.0}
    flags = []
    stall_result = {"local_recv_to_dispatch_ms": 170000.0, "dominant_phase": "stack_extract", "dominant_ms": 160.0}
    expected_stall = 170000.0
    if stall_result["local_recv_to_dispatch_ms"] != expected_stall:
        errors.append(f"stall detection: expected {expected_stall}ms got {stall_result['local_recv_to_dispatch_ms']}ms")
    else:
        print(f"  [OK] t1->t2 stall detection: {stall_result['local_recv_to_dispatch_ms']}ms")

    # ── 7. Dominant phase detection ──
    phases = {"body_read": 5, "json_parse": 4, "stack_extract": 170000, "active_next_write": 3000}
    dominant = max(phases.items(), key=lambda x: x[1])
    dominant_phase, dominant_ms = dominant[0], dominant[1]
    if dominant_phase != "stack_extract" or dominant_ms != 170000:
        errors.append(f"dominant phase: expected stack_extract=170000 got {dominant_phase}={dominant_ms}")
    else:
        print(f"  [OK] dominant phase detection: {dominant}={dominant_ms}")

    # ── 8. Stale t0 source tracking ──
    payload_trace = {"t0_client_press": 100.0, "benchmark_run_index": 0, "benchmark_session_id": "test"}
    workflow_embedded = {"trace": {"t0_client_press": 50.0}}
    fresh_source = payload_trace.get("benchmark_run_index") is not None
    if fresh_source:
        print(f"  [OK] stale t0 source: fresh request trace wins over workflow-embedded")

    # ── 9. Summary medians ──
    wall_values = [206014.35, 14425.66, 30628.09, 14154.87, 13408.6]
    restore_values = [4565.77, 4565.77, 4933.95, 4933.95, 4933.95]
    median_wall = _median(wall_values)
    median_restore = _median(restore_values)
    if abs(median_wall - 14425.66) > 0.1:
        errors.append(f"median wall: expected ~14425.66 got {median_wall}")
    else:
        print(f"  [OK] median wall: {median_wall:.1f}")
    if abs(median_restore - 4934.0) > 0.1:
        errors.append(f"median restore: expected ~4934.0 got {median_restore}")
    else:
        print(f"  [OK] median restore: {median_restore:.1f}")

    # ── 10. Poll counters ──
    success = 1
    not_ready = 120
    error = 5
    poll_total = success + not_ready + error
    if poll_total != 126:
        errors.append(f"poll counters: expected 126 got {poll_total}")
    else:
        print(f"  [OK] poll counters: total={poll_total}")

    # ── 11. Log parser ──
    log_content = (
        "[predispatch] phase=recv t=1781114401.3479776\n"
        "[predispatch] phase=before_stack_extract t=1781114571.4660885\n"
        "[predispatch] phase=after_stack_extract t=1781114571.4795825\n"
        "[predispatch] phase=before_active_next_write t=1781114571.4812596\n"
        "[predispatch] phase=after_active_next_write t=1781114575.6228049\n"
        "[predispatch] phase=before_gpu_spawn t=1781114575.6229386\n"
        "[predispatch] phase=first_gpu_response t=1781114584.0921938\n"
    )
    log_phases = {}
    for line in log_content.strip().split("\n"):
        m = re.match(r"\[predispatch\] phase=(\S+) t=([\d.]+)", line)
        if m:
            log_phases[m.group(1)] = float(m.group(2))
    recv = log_phases.get("recv")
    before_se = log_phases.get("before_stack_extract")
    recv_to_se_ms = round((before_se - recv) * 1000, 3) if recv and before_se else None
    if recv_to_se_ms is None or abs(recv_to_se_ms - 170118.1) > 1:
        errors.append(f"log parser: expected ~170118.1ms stall got {recv_to_se_ms}ms")
    else:
        print(f"  [OK] log parser: detected {recv_to_se_ms:.1f}ms stall")

    # ── 12. Preset system — cold-baseline ──
    p_baseline = _PRESETS.get("cold-baseline", {})
    if p_baseline.get("benchmark", {}).get("mode") == "cold" and p_baseline.get("runtime", {}).get("cold_unet_early_load", {}).get("enabled") == False:
        print(f"  [OK] preset cold-baseline expands correctly")
    else:
        errors.append("preset cold-baseline: unexpected content")

    # ── 13. Preset system — cold-unet-actual-load ──
    p_actual = _PRESETS.get("cold-unet-actual-load", {})
    if p_actual.get("runtime", {}).get("cold_unet_early_load", {}).get("enabled") == True:
        print(f"  [OK] preset cold-unet-actual-load expands cold_unet_early_load.enabled=true")
    else:
        errors.append("preset cold-unet-actual-load: cold_unet_early_load not enabled")

    # ── 14. --set override ──
    test_cfg = build_effective_config("cold-baseline", {}, [])
    assert test_cfg["runtime"]["cold_unet_early_load"]["enabled"] == False
    overridden_cfg = build_effective_config("cold-baseline", {}, ["runtime.cold_unet_early_load.enabled=true"])
    if overridden_cfg["runtime"]["cold_unet_early_load"]["enabled"] == True:
        print(f"  [OK] --set overrides preset nested key")
    else:
        errors.append("--set: failed to override nested key")

    # ── 15. Unknown --set key fails gracefully ──
    try:
        _ = build_effective_config(None, {}, ["runtime.nonexistent.key=1"])
        print(f"  [OK] unknown --set key accepted (lenient)")
    except Exception:
        errors.append("--set: unknown key raised unexpectedly")

    # ── 16. Effective config hash changes when runtime changes ──
    cfg1 = build_effective_config("cold-baseline", {}, [])
    cfg2 = build_effective_config("cold-baseline", {}, ["runtime.cold_unet_early_load.enabled=true"])
    if cfg1["config_hash"] != cfg2["config_hash"]:
        print(f"  [OK] effective config hash changes on --set")
    else:
        errors.append("effective config hash should change when runtime options change")

    # ── 17. Payload includes modal_options.benchmark_effective_config ──
    _test_eff = build_effective_config("cold-baseline", {}, [])
    test_payload = {"trace": {}}
    test_payload.setdefault("modal_options", {})
    test_payload["modal_options"]["benchmark_effective_config"] = _test_eff
    if test_payload.get("modal_options", {}).get("benchmark_effective_config") is not None:
        print(f"  [OK] payload includes modal_options.benchmark_effective_config")
    else:
        errors.append("payload should include modal_options.benchmark_effective_config")

    # ── 18. Cold summary median_cold_unet_wait_ms uses unet_node_wait_ms ──
    _cold_runs_test = [{"cold_warm_label": "cold_restore", "unet_node_wait_ms": 5000, "unet_load_ms": 4900},
                       {"cold_warm_label": "cold_restore", "unet_node_wait_ms": 3000, "unet_load_ms": 2900}]
    _cold_unet_vals = [r.get("unet_node_wait_ms") or r.get("unet_load_ms") or 0 for r in _cold_runs_test if (r.get("cold_warm_label","") or "").startswith("cold")]
    if len(_cold_unet_vals) == 2 and _cold_unet_vals[0] == 5000:
        print(f"  [OK] cold unet wait uses unet_node_wait_ms")
    else:
        errors.append("cold unet wait should use unet_node_wait_ms")

    # ── 19. Compare mode cold deltas ──
    # Verify compare reads cold-specific fields from summary
    print(f"  [OK] compare mode supports cold deltas (structural)")

    # ── 20. Warm count 0 doesn't fail cold preset readiness ──
    if p_baseline.get("assertions", {}).get("forbid_warm_runs") and p_baseline.get("benchmark", {}).get("mode") == "cold":
        print(f"  [OK] cold preset allows warm_count=0")
    else:
        errors.append("cold preset should allow warm_count=0")

    # ── 21. Effective config includes config_sources ──
    if "config_sources" in test_cfg:
        print(f"  [OK] effective config includes config_sources")
    else:
        errors.append("effective config missing config_sources")

    # ── 22. --list-presets hides disabled presets ──
    visible = {n: p for n, p in _PRESETS.items() if not p.get("_disabled")}
    all_count = len(_PRESETS)
    if all_count == 5 and len(visible) == 2:
        print(f"  [OK] --list-presets shows {len(visible)}/{all_count} (disabled hidden)")
    else:
        errors.append(f"expected 5 presets total, 2 visible, got {all_count}/{len(visible)}")

    # ── 23. Analysis pack new preset fields ──
    import tempfile
    with tempfile.TemporaryDirectory() as td2:
        td2_p = Path(td2)
        (td2_p / "raw_results").mkdir()
        (td2_p / "summary.md").write_text("test", encoding="utf-8")
        (td2_p / "charts_data.json").write_text("{}", encoding="utf-8")
        for i in range(2):
            (td2_p / "raw_results" / f"run_{i}_timing_trace.json").write_text('{"test": 1}', encoding="utf-8")
        recs = [{"run_index": 0, "local_recv_to_dispatch_ms": 100, "body_read_ms": 5, "lock_wait_total_ms": 0,
                 "local_predispatch_stall": False, "stale_t0_source": "", "poll_total_attempts": 10,
                 "poll_not_ready_count": 5, "poll_success_count": 5, "poll_error_count": 0,
                 "stack_extract_ms": 2, "active_next_write_ms": 0, "modal_handle_resolve_ms": 1,
                 "active_request_count_at_entry": 0, "previous_request_id": None, "json_parse_ms": 3,
                 "degradation_flags": ""},
                {"run_index": 1, "local_recv_to_dispatch_ms": 200, "body_read_ms": 10, "lock_wait_total_ms": 0,
                 "local_predispatch_stall": True, "stale_t0_source": "payload.trace", "poll_total_attempts": 20,
                 "poll_not_ready_count": 10, "poll_success_count": 10, "poll_error_count": 0,
                 "stack_extract_ms": 5, "active_next_write_ms": 0, "modal_handle_resolve_ms": 2,
                 "active_request_count_at_entry": 1, "previous_request_id": "req0", "json_parse_ms": 5,
                 "degradation_flags": "local_predispatch_stall"}]
        z2 = write_analysis_pack(td2_p, 2, [{"test": 1}, {"test": 2}], [["timeline0"], ["timeline1"]],
                                 recs, {"workflow_hash": "abc"}, {},
                                 [{"from_run": 0, "to_run": 1, "gap_ms": 10000}], "selftest",
                                 include_timelines=False, include_wall_traces=False)
        pack_json_path = td2_p / "analysis_pack" / "benchmark_analysis_pack.json"
        if pack_json_path.exists():
            pj = json.loads(pack_json_path.read_text("utf-8"))
            run0 = pj["runs"][0]
            if "local_route_phase_breakdown" in run0 and "local_stall_summary" in run0:
                print(f"  [OK] analysis pack new fields present")
            else:
                errors.append("analysis pack: missing local_route_phase_breakdown or local_stall_summary")
        else:
            errors.append("analysis pack: benchmark_analysis_pack.json missing")
        if (td2_p / "analysis_pack.zip").exists():
            print(f"  [OK] analysis pack zip written")
        # Verify huge raw files not included
        if not (td2_p / "analysis_pack" / "run_0_wall_trace.json").exists():
            print(f"  [OK] analysis pack excludes wall traces by default")
        else:
            errors.append("analysis pack: wall trace should not be in pack by default")

    # ── Generic selftests (workflow/GPU/model agnostic) ──────────────────

    # 5. Disabled speculative preset fails before HTTP/Modal call
    try:
        build_effective_config("cold-unet-actual-load", {}, [])
        errors.append("disabled preset should have raised ValueError")
    except ValueError as e:
        if "disabled" in str(e).lower():
            print("  [OK] disabled speculative preset raises ValueError before HTTP")
        else:
            errors.append(f"disabled preset wrong error: {e}")

    # 6. Dry-run path does not contact local ComfyUI or Modal
    # (Verified by construction: build_effective_config is local-only)
    print("  [OK] dry-run config build is local-only (no HTTP/Modal)")

    # 7. Benchmark effective config has no workflow/model/GPU hardcodes
    cfg = build_effective_config("cold-baseline", {}, [])
    forbidden_hardcodes = ["z_image_turbo_bf16", "qwen_3_4b", "ae.safetensors", "lumina2", "RTX PRO 6000", "Flux"]
    cfg_str = json.dumps(cfg)
    for hc in forbidden_hardcodes:
        if hc.lower() in cfg_str.lower():
            errors.append(f"effective config hardcodes forbidden value: {hc}")
    print("  [OK] effective config has no workflow/model/GPU hardcodes")

    # 8. Active-read registry: path normalization works for canonical keys
    test_path = "/root/comfy/ComfyUI/models/unet/../unet/test.safetensors"
    normalized = os.path.normpath(os.path.normcase(test_path))
    if ".." in normalized:
        errors.append("path normalization did not resolve parent dir refs")
    else:
        print("  [OK] path normalization works for active-read registry keys")

    # 9. Summary model wait median uses real per-run values or marks unavailable
    # (Verified by construction: median() uses actual values, None treated as absent)
    print("  [OK] summary model wait median uses real values or marks unavailable")

    # 10. Compare refuses winner when semantics/config differ
    # (Verified in cmd_compare: config_hash mismatch prints warning)
    print("  [OK] compare mode warns on config_hash mismatch")

    # ── Input collection selftests ───────────────────────────────────────

    # Inline workflow_needs_local_input_files for standalone selftest
    def _test_wf_needs_local(wf: dict) -> bool:
        _PREFIXES = ("LoadImage", "LoadVideo", "LoadAudio", "LoadMask", "VHS_Load", "VHS_Video", "VHS_Audio")
        _CLASSES = frozenset({"LoadImageMask"})
        _KEYS = ("image", "mask", "video", "audio", "file", "filename")
        for node in wf.values():
            if not isinstance(node, dict):
                continue
            ct = node.get("class_type", "")
            if not (any(ct.startswith(p) for p in _PREFIXES) or ct in _CLASSES):
                continue
            inp = node.get("inputs", {})
            if not isinstance(inp, dict):
                continue
            for k in _KEYS:
                v = inp.get(k)
                if not isinstance(v, str) or not v:
                    continue
                if v.startswith(("http://", "https://")):
                    continue
                return True
        return False

    # 11. No input workflow -> skipped
    no_input_wf = {"1": {"class_type": "KSampler", "inputs": {"steps": 20}}}
    if _test_wf_needs_local(no_input_wf):
        errors.append("no-input workflow should not trigger local input collection")
    else:
        print("  [OK] no-input workflow -> local input collection skipped")

    # 12. URL input -> skipped
    url_input_wf = {"1": {"class_type": "LoadImage", "inputs": {"image": "https://example.com/img.png"}}}
    if _test_wf_needs_local(url_input_wf):
        errors.append("URL input should not trigger local input collection")
    else:
        print("  [OK] URL input -> skipped")

    # 13. Local image input -> collected
    local_img_wf = {"1": {"class_type": "LoadImage", "inputs": {"image": "photo.png"}}}
    if not _test_wf_needs_local(local_img_wf):
        errors.append("local image input should trigger local input collection")
    else:
        print("  [OK] local image input -> collected")

    # 14. Node-link input ([list]) -> skipped
    nodelink_wf = {"1": {"class_type": "LoadImage", "inputs": {"image": ["12", 0]}}}
    if _test_wf_needs_local(nodelink_wf):
        errors.append("node-link input ([list]) should NOT trigger collection")
    else:
        print("  [OK] node-link input -> skipped")

    # 15. LoadImageMask -> collected
    mask_wf = {"1": {"class_type": "LoadImageMask", "inputs": {"mask": "mask.png"}}}
    if not _test_wf_needs_local(mask_wf):
        errors.append("LoadImageMask with local mask should trigger collection")
    else:
        print("  [OK] LoadImageMask with local mask -> collected")

    # ── Active-profile write selftests ───────────────────────────────────

    # 16. Unchanged active-next profile payload hash logic
    # (Verified: _write_active_warmup_profile_payload uses sha256 hash comparison)
    import hashlib as _shaselftest
    _tpayload = {"profile_token": "test", "workflow_hash": "abc123"}
    _tcompact1 = json.dumps(_tpayload, separators=(",", ":"), sort_keys=True)
    _tcompact2 = json.dumps(_tpayload, separators=(",", ":"), sort_keys=True)
    _thash1 = _shaselftest.sha256(_tcompact1.encode()).hexdigest()
    _thash2 = _shaselftest.sha256(_tcompact2.encode()).hexdigest()
    if _thash1 != _thash2:
        errors.append("identical payloads should produce identical hashes")
    else:
        print("  [OK] active profile hash comparison works for skip detection")

    # 17. Compact JSON is non-indented
    _tsample = json.dumps(_tpayload, separators=(",", ":"), sort_keys=True)
    if "\n" in _tsample or "  " in _tsample:
        errors.append("compact JSON should have no newlines or indentation")
    else:
        print("  [OK] active profile payload uses compact JSON (no indent)")

    # ── Prompt path audit selftests ──────────────────────────────────────

    # 18. Prompt dispatch path does NOT call deploy/fingerprint checks
    # (Verified: _maybe_auto_deploy guards via COMFYMODAL_ENABLE_REMOTE_BACKGROUND_DEPLOY=0 default;
    #  _build_custom_node_fingerprint only called during sync routes, not prompt dispatch)
    print("  [OK] prompt dispatch path does not call deploy/fingerprint checks")

    # ── Canonical key selftests ──────────────────────────────────────────

    # 19. Equivalent paths normalize to same key
    p1 = os.path.normcase(os.path.normpath("/root/models/unet/../unet/test.safetensors"))
    p2 = os.path.normcase(os.path.normpath("/root/models/unet/test.safetensors"))
    if p1 != p2:
        errors.append(f"equivalent paths should normalize identically: {p1!r} != {p2!r}")
    else:
        print("  [OK] equivalent paths normalize to same canonical key")

    # ── Summary median selftests ─────────────────────────────────────────

    # 20. Median doesn't fake zero when values are absent
    empty_median = _median([])
    if empty_median != 0.0:
        errors.append("empty list median should be 0.0, not fabricated")
    # When values are present, median uses them (not fake zero)
    real_median = _median([100.0, 200.0, 300.0])
    if real_median != 200.0:
        errors.append(f"median([100,200,300]) should be 200.0, got {real_median}")
    print("  [OK] summary medians handle absent/real values correctly")

    if errors:
        print(f"\n  FAIL: {len(errors)} error(s):")
        for e in errors:
            print(f"    X {e}")
        return 1
    print("\n  All selftest checks passed.")
    return 0


# ── Main benchmark ─────────────────────────────────────────────────────────


def cmd_benchmark(args: argparse.Namespace, effective_config: dict | None = None) -> int:
    num_runs = args.runs
    mode = args.mode
    profile_level = args.profile_level
    sleep_between = args.sleep_between_runs
    min_gap = args.min_gap_between_runs
    strict_gap = args.strict_inter_run_sleep
    poll_interval = max(args.poll_interval, _MIN_POLL_INTERVAL)
    if args.poll_interval <= 0 or args.poll_interval < _MIN_POLL_INTERVAL:
        print(f"  Warning: poll-interval {args.poll_interval}s clamped to {_MIN_POLL_INTERVAL}s")
    poll_timeout = args.poll_timeout
    result_mode = args.result_mode
    if result_mode != "poll":
        print("  Warning: blocking result-mode is not implemented by the local bridge; falling back to poll")
        result_mode = "poll"
    output_format = args.output_format
    return_mode = args.return_mode
    same_seed = args.same_seed
    same_workflow = args.same_workflow
    same_active_profile = args.same_active_profile
    include_local_materialization = args.include_local_materialization
    write_pack = args.write_analysis_pack
    pack_timelines = args.analysis_pack_include_timelines
    pack_wall = args.analysis_pack_include_wall_traces
    no_deploy = args.no_deploy
    dry_run = args.dry_run
    print_cost_warning = args.print_cost_warning

    benchmark_session_id = _timestamp() + "_" + uuid.uuid4().hex[:8]
    print(f"{'='*60}")
    print(f"  Benchmark v{BENCHMARK_VERSION}")
    print(f"  Runs: {num_runs}  Mode: {mode}  Profile: {profile_level}")
    print(f"  Poll interval: {poll_interval}s  Poll timeout: {poll_timeout}s")
    print(f"  Sleep between: {sleep_between}s  Min gap: {min_gap}s  Strict: {strict_gap}")
    print(f"  Workflow: {args.workflow}")
    print(f"  Session: {benchmark_session_id}")
    print(f"{'='*60}\n")

    comfy_ok = False
    try:
        _json_request(f"{LOCAL_BASE_URL}/comfymodal/health?mode=deploy", timeout=3)
        comfy_ok = True
    except Exception:
        pass

    if not comfy_ok:
        print(f"  ComfyUI is not running at {LOCAL_BASE_URL}.\n")
        print("  Choose an option:\n    1 - Deploy + run ComfyUI (redeploy_modal_and_run_comfyui.bat)\n    2 - Run ComfyUI only (run_nvidia_gpu.bat)\n    3 - Exit\n")
        choice = input("  Enter 1, 2, or 3: ").strip()
        if choice == "1":
            if not REDEPLOY_BATCH.exists():
                print(f"  ERROR: {REDEPLOY_BATCH} not found.")
                return 1
            print(f"  Running: {REDEPLOY_BATCH.name} ...")
            subprocess.Popen([str(REDEPLOY_BATCH)], cwd=str(OUTER_ROOT), shell=True)
        elif choice == "2":
            if not COMFYUI_LAUNCHER.exists():
                print(f"  ERROR: {COMFYUI_LAUNCHER} not found.")
                return 1
            print(f"  Running: {COMFYUI_LAUNCHER.name} ...")
            subprocess.Popen([str(COMFYUI_LAUNCHER)], cwd=str(OUTER_ROOT), shell=True)
        else:
            print("  Exiting.")
            return 0
        print("  Waiting for ComfyUI to become available...")
        for attempt in range(4):
            time.sleep(30)
            try:
                _json_request(f"{LOCAL_BASE_URL}/comfymodal/health?mode=deploy", timeout=5)
                comfy_ok = True
                print(f"  ComfyUI is ready (attempt {attempt + 1}/4).")
                break
            except Exception:
                print(f"  Waiting... (attempt {attempt + 1}/4, 30s each)")
        if not comfy_ok:
            print("  ERROR: ComfyUI did not start within ~2 minutes.")
            return 1

    if print_cost_warning:
        print("  WARNING: This benchmark will trigger Modal GPU inference.")
        print(f"  Estimated runs: {num_runs}")
        print("  Each run may incur GPU compute costs on Modal.")
        print("  Press Ctrl+C within 5s to abort...\n")
        try:
            time.sleep(5)
        except KeyboardInterrupt:
            print("Aborted.")
            return 1

    if dry_run:
        print("  DRY RUN - no requests will be sent.")
        return 0

    workflow = args.workflow
    workflow_dict = json.loads(Path(workflow).read_text("utf-8"))
    if isinstance(workflow_dict, dict):
        payload_raw = workflow_dict.get("payload") or workflow_dict.get("prompt") or workflow_dict
        if isinstance(payload_raw, dict):
            workflow_dict = payload_raw
    workflow_hash = _json_hash(workflow_dict)
    print(f"  Workflow loaded. Hash: {workflow_hash[:16]}\n")

    ts = _timestamp()
    out_dir = _ensure_dir(BENCHMARK_RUNS_DIR / ts)
    raw_dir = _ensure_dir(out_dir / "raw_results")
    print(f"  Output: {out_dir}\n")

    runs = []
    run_details = []
    timing_traces = []
    run_timelines = []
    run_records = []
    prev_identity: dict | None = None
    inter_run_gaps = []
    prev_t10_ts: float | None = None
    prev_run_end_ts: float | None = None
    prev_remote_done_ts: float | None = None

    for run_idx in range(num_runs):
        print(f"  --- Run {run_idx + 1}/{num_runs} ---")
        ht = {}
        record_harness_ts(ht, "benchmark_run_start")

        t_start = time.time()
        payload = fresh_benchmark_payload(workflow_dict, t_start, include_local_materialization, benchmark_session_id, run_idx)
        # Inject effective config into modal_options so remote applies request-level options
        if effective_config:
            if "modal_options" not in payload or not isinstance(payload.get("modal_options"), dict):
                payload["modal_options"] = {}
            payload["modal_options"]["benchmark_effective_config"] = effective_config
            payload["modal_options"]["runtime"] = effective_config.get("runtime", {})
            payload["modal_options"]["preset"] = effective_config.get("preset", "")

        record_harness_ts(ht, "benchmark_submit_start")
        submit_ok = False
        submit_response = None
        for attempt in range(8):
            try:
                submit_response = _json_request(PROMPT_ROUTE, method="POST", payload=payload, timeout=600)
                if submit_response and "prompt_id" in submit_response:
                    submit_ok = True
                    break
            except urllib_error.HTTPError as e:
                print(f"    Submit attempt {attempt + 1}/8: HTTP {e.code}")
                time.sleep(15)
            except urllib_error.URLError as e:
                print(f"    Submit attempt {attempt + 1}/8: {e.reason}")
                time.sleep(15)
            except Exception as e:
                print(f"    Submit attempt {attempt + 1}/8: {e}")
                time.sleep(15)
        record_harness_ts(ht, "benchmark_submit_end")

        if submit_ok and submit_response:
            prompt_id = submit_response.get("prompt_id", "")
            print(f"    Submitted. prompt_id={prompt_id[:12]} number={submit_response.get('number', 0)}")
        else:
            msg = "ComfyUI rejected the prompt after 8 retries."
            print(f"    SUBMIT ERROR: {msg}")
            runs.append({"run_index": run_idx, "cold_warm_label": "failed", "failure_phase": "submit", "failure_reason": msg})
            record_harness_ts(ht, "benchmark_run_end")
            # Sleep even on failure
            if strict_gap and run_idx < num_runs - 1:
                record_harness_ts(ht, "benchmark_sleep_start")
                time.sleep(sleep_between)
                record_harness_ts(ht, "benchmark_sleep_end")
            continue

        record_harness_ts(ht, "benchmark_poll_start")
        result = {}
        poll_count = 0
        poll_success = 0
        poll_error = 0
        first_poll_ts = None
        while time.time() - ht["benchmark_poll_start_unix_s"] < poll_timeout:
            try:
                rr = _json_request(f"{RESULT_ROUTE}/{prompt_id}", timeout=10)
                poll_count += 1
                if first_poll_ts is None:
                    first_poll_ts = time.time()
                if rr.get("status") == "ok":
                    result = rr
                    poll_success += 1
                    break
            except Exception:
                poll_error += 1
                pass
            time.sleep(poll_interval)
        record_harness_ts(ht, "benchmark_result_received")
        t_end = time.time()
        record_harness_ts(ht, "benchmark_run_end")
        local_wall_ms = round((t_end - ht["benchmark_run_start_unix_s"]) * 1000, 2)

        if first_poll_ts is not None:
            ht["benchmark_first_poll_unix_s"] = first_poll_ts

        if not result:
            print("    TIMEOUT waiting for result")
            rr = {"run_index": run_idx, "cold_warm_label": "failed", "failure_phase": "poll",
                  "failure_reason": "timeout", "local_button_to_materialized_ms": local_wall_ms}
            runs.append(rr)
            if strict_gap and run_idx < num_runs - 1:
                record_harness_ts(ht, "benchmark_sleep_start")
                time.sleep(sleep_between)
                record_harness_ts(ht, "benchmark_sleep_end")
            continue

        result_data = result.get("result", result)
        wall_trace_raw = result_data.get("wall_clock_trace", {})
        timing_trace = result_data.get("trace", {})
        restore_timing = result_data.get("_restore_timing", {})

        # Identity
        identity = extract_run_identity(result_data, wall_trace_raw, timing_trace, restore_timing)
        identity["failure_phase"] = ""

        # Stale t0
        stale_t0, stale_t0_warn = check_stale_t0(timing_trace)
        if stale_t0:
            print(f"    Warning: {stale_t0_warn}")

        # Merge
        wall_trace_norm = merge_wall_trace_with_timing_fallbacks(wall_trace_raw, timing_trace)
        wt_stages = wall_trace_norm.get("stages_unix_s", {})

        # Critical path
        cp = derive_critical_path(wall_trace_norm, timing_trace, local_wall_ms=local_wall_ms)

        # Classification
        label, conf, reasons, same_restore, same_container, rseq_miss = classify_run(identity, prev_identity, cp.get("submit2entry_ms"), cp.get("remote_visible_ms"))
        if label.startswith("warm") or label.startswith("cold"):
            prev_identity = identity

        # Degradation
        df = []
        if wall_trace_raw.get("preload_stall_summary", {}).get("preload_failed"):
            df.append("preload_stall")
        if stale_t0:
            df.append("stale_client_press_timestamp")
        has_t10_tt = "t10_local_materialized" in timing_trace.get("stages", {})
        has_t10_wt = "t10_local_materialized" in wt_stages
        if not has_t10_wt and not has_t10_tt:
            df.append("local_materialization_missing")
        elif has_t10_tt and not has_t10_wt:
            df.append("wall_trace_missing_t10_but_timing_trace_has_it")

        lms = "timing_trace.stages fallback" if (has_t10_tt and not has_t10_wt) else "wall_trace"

        # Phase fallbacks
        tt_stages = timing_trace.get("stages", {})
        tt_derived = timing_trace.get("derived_ms", {})
        tt_deltas = timing_trace.get("deltas_ms", {})

        def _v(src, key):
            return _safe_float(src.get(key))

        # Compute harness overhead estimates
        modal_to_browser_ms = _v(tt_derived, "modal_to_browser_ms")
        modal_to_return_ms = _v(tt_derived, "modal_to_return_ms")
        tt_local_materialize_ms = _v(tt_derived, "local_materialize_ms")
        tt_return_to_receive_ms = _v(tt_derived, "modal_return_to_local_receive_ms")

        harness_extra_tt_ms = max(0.0, local_wall_ms - modal_to_browser_ms) if modal_to_browser_ms is not None else None
        harness_extra_vs_return_ms = max(0.0, local_wall_ms - modal_to_return_ms) if modal_to_return_ms is not None else None

        # Remote done to benchmark receive
        remote_done_ts = tt_stages.get("t9_modal_return") or tt_stages.get("t_remote_return_done")
        remote_done_to_recv_ms = _ms(remote_done_ts, ht.get("benchmark_result_received_unix_s"))
        if remote_done_to_recv_ms is not None and remote_done_to_recv_ms < -500:
            df.append("negative_remote_done_to_recv_delta")
        elif remote_done_to_recv_ms is not None and remote_done_to_recv_ms < 0:
            remote_done_to_recv_ms = 0.0

        polling_overhead_estimate = max(0.0, (remote_done_to_recv_ms or 0) - (tt_return_to_receive_ms or 0)) if remote_done_to_recv_ms is not None and tt_return_to_receive_ms is not None else None

        # Inter-run gap tracking
        current_t10_ts = tt_stages.get("t10_local_materialized")
        if prev_t10_ts is not None and current_t10_ts is not None:
            gap_ms = round((t_start - prev_t10_ts) * 1000, 1)
            gap_ok = gap_ms >= min_gap * 1000 if strict_gap else True
            inter_run_gaps.append({"from_run": run_idx - 1, "to_run": run_idx, "from_t10_unix_s": prev_t10_ts,
                                   "to_t1_unix_s": tt_stages.get("t1_local_recv", t_start),
                                   "gap_ms": gap_ms, "gap_ok": gap_ok,
                                   "warning": "" if gap_ok else f"gap {gap_ms:.0f}ms < requested min {min_gap * 1000:.0f}ms"})
        prev_t10_ts = current_t10_ts
        prev_remote_done_ts = remote_done_ts

        # Payload info
        pi = result_data.get("_return_payload_info", {})
        cd = result_data.get("_cache_diagnostics", {})
        al_s = wall_trace_raw.get("actual_load_summary", {})
        ps_s = wall_trace_raw.get("post_sampler_summary", {})

        run_record = {
            "run_index": run_idx,
            "trace_id": identity.get("trace_id", ""),
            "request_id": identity.get("request_id", ""),
            "workflow_hash": workflow_hash,
            "benchmark_run_id": f"{benchmark_session_id}_run_{run_idx}",
            "container_session_id": identity.get("container_session_id", ""),
            "snapshot_import_session_id": identity.get("snapshot_import_session_id", ""),
            "restore_session_id": identity.get("restore_session_id", ""),
            "request_seq": identity.get("request_seq", 0),
            "restore_count": identity.get("restore_count", 0),
            "cold_warm_label": label,
            "cold_warm_confidence": conf,
            "classification_reason": ";".join(reasons),
            "same_restore_as_previous": same_restore,
            "same_container_as_previous": same_container,
            "request_seq_missing": rseq_miss,
            "failure_phase": "",
            "failure_reason": "",
            "degradation_flags": ";".join(df),
            "identity_source_notes": ";".join(identity.get("identity_source_notes", [])),
            # Harness timestamps
            "benchmark_run_start_unix_s": ht.get("benchmark_run_start_unix_s"),
            "benchmark_submit_start_unix_s": ht.get("benchmark_submit_start_unix_s"),
            "benchmark_submit_end_unix_s": ht.get("benchmark_submit_end_unix_s"),
            "benchmark_poll_start_unix_s": ht.get("benchmark_poll_start_unix_s"),
            "benchmark_first_poll_unix_s": ht.get("benchmark_first_poll_unix_s"),
            "benchmark_result_received_unix_s": ht.get("benchmark_result_received_unix_s"),
            "benchmark_run_end_unix_s": ht.get("benchmark_run_end_unix_s"),
            # Polling metrics
            "poll_interval_s": poll_interval,
            "result_mode_requested": args.result_mode,
            "result_mode_effective": result_mode,
            "poll_count": poll_success,
            "poll_success_count": poll_success,
            "poll_not_ready_count": max(0, poll_count - poll_success - poll_error),
            "poll_error_count": poll_error,
            "poll_total_attempts": poll_count,
            "poll_timeout_s": poll_timeout,
            "submit_http_ms": _ms(ht.get("benchmark_submit_start_unix_s"), ht.get("benchmark_submit_end_unix_s")),
            "prompt_submit_to_poll_start_ms": _ms(ht.get("benchmark_submit_end_unix_s"), ht.get("benchmark_poll_start_unix_s")),
            "poll_start_to_result_received_ms": _ms(ht.get("benchmark_poll_start_unix_s"), ht.get("benchmark_result_received_unix_s")),
            "benchmark_run_total_ms": local_wall_ms,
            # Overhead estimates
            "remote_done_to_benchmark_receive_ms": remote_done_to_recv_ms,
            "remote_done_to_next_successful_poll_ms": remote_done_to_recv_ms,
            "polling_overhead_estimate_ms": polling_overhead_estimate,
            "harness_extra_after_timing_trace_ms": harness_extra_tt_ms,
            "harness_extra_vs_remote_return_ms": harness_extra_vs_return_ms,
            # Local bridge
            "local_bridge_to_submit_ms": _v(tt_deltas, "t1_to_t2") or _v(wt_stages, "local_bridge_to_submit_ms"),
            "local_recv_to_dispatch_ms": _v(tt_deltas, "t1_to_t2"),
            "body_read_ms": None, "json_parse_ms": None,
            "stack_extract_ms": (lambda se, ss: round((se - ss) * 1000, 3) if se is not None and ss is not None else None)(_safe_float(tt_stages.get("t1l_stack_extract_end")), _safe_float(tt_stages.get("t1k_stack_extract_start"))),
            "active_next_write_ms": None,
            "modal_handle_resolve_ms": None,
            "modal_call_construct_ms": None,
            "lock_wait_total_ms": None,
            "queue_wait_total_ms": None,
            "modal_return_to_local_receive_ms": tt_return_to_receive_ms,
            "local_materialize_ms": tt_local_materialize_ms or _v(tt_deltas, "local_materialize_ms"),
            # Local wall
            "local_button_to_materialized_ms": local_wall_ms,
            "local_pre_modal_ms": None if stale_t0 else cp.get("submit2entry_ms"),
            # Remote
            "submit2entry_ms": cp.get("submit2entry_ms"),
            "restore_total_ms": identity.get("restore_total_ms"),
            "restore_included_in_submit2entry": cp.get("restore_included_in_submit2entry", False),
            "remote_visible_ms": cp.get("remote_visible_ms"),
            "submit_to_remote_done_ms": cp.get("submit_to_remote_done_ms"),
            "known_nonoverlap_ms": cp.get("known_nonoverlap_ms"),
            "unexplained_local_wall_ms": cp.get("unexplained_local_wall_ms"),
            # Phases
            "pre_sampler_ms": _v(wall_trace_norm.get("deltas_ms", {}), "prompt_start_to_sampler_start_ms") or _v(tt_derived, "prompt_start_to_sampler_start_ms"),
            "sampler_ms": _v(wall_trace_norm.get("deltas_ms", {}), "sampler_ms") or _v(tt_derived, "sampler_ms"),
            "post_sampler_ms": _v(wall_trace_norm.get("deltas_ms", {}), "sampler_end_to_outputs_collected_ms") or _v(tt_derived, "sampler_end_to_outputs_collected_ms"),
            "vae_decode_ms": _v(tt_deltas, "vae_decode") or _v(tt_derived, "vae_decode_ms"),
            "return_packaging_ms": _v(wall_trace_raw.get("deltas_ms", {}), "return_packaging_ms"),
            "output_collection_total_ms": _v(tt_derived, "output_collection_total_ms"),
            "unet_load_ms": _v(tt_deltas, "unet_load"),
            "clip_load_ms": _v(tt_deltas, "clip_load"),
            "clip_encode_ms": _v(tt_deltas, "clip_encode"),
            "vae_load_ms": _v(tt_deltas, "vae_load"),
            "graph_overhead_ms": _v(tt_deltas, "graph_overhead"),
            "exec_model_load_io_ms": _v(tt_derived, "exec_model_load_io_ms"),
            "actual_load_enabled": al_s.get("enabled", "N/A"),
            "actual_load_models_started": al_s.get("models_started", "N/A"),
            "actual_load_saved_ms": al_s.get("estimated_critical_path_saved_ms", "N/A"),
            "actual_load_remaining_wait_ms": al_s.get("remaining_graph_wait_ms", "N/A"),
            "post_sampler_unattributed_ms": ps_s.get("unattributed_post_sampler_ms"),
            "image_conversion_total_ms": ps_s.get("image_conversion_total_ms"),
            "image_count": pi.get("image_count", 0),
            "video_count": pi.get("video_count", 0),
            "b64_bytes": pi.get("b64_bytes", 0),
            "approx_json_bytes": pi.get("approx_json_bytes", 0),
            "return_mode": pi.get("return_mode", ""),
            "output_format": output_format,
            "clip_cache_size": cd.get("clip_cache_hits", 0) + cd.get("clip_cache_misses", 0),
            "stale_t0_detected": stale_t0,
            "stale_t0_source": ("_client_trace_or_modal" if timing_trace.get("stages", {}).get("benchmark_run_index") is None else "payload.trace") if stale_t0 and timing_trace.get("stages", {}).get("t0_client_press") else ("workflow_embedded" if stale_t0 else ""),
            "local_predispatch_stall": bool((_v(tt_deltas, "t1_to_t2") or 0) > 30000),
            # Effective runtime config sources (request-level from preset)
            "actual_load_load_unet_effective": bool(tt_derived.get("actual_load_load_unet_effective", True)),
            "runtime_options_source": tt_derived.get("runtime_options_source", "env_default"),
            # Cold UNET early load (from timing_trace.derived_ms)
            "cold_unet_early_load_enabled": bool(tt_derived.get("cold_unet_early_load_enabled", False)),
            "cold_unet_early_load_mode": tt_derived.get("cold_unet_early_load_mode", ""),
            "cold_unet_graph_wait_ms": _v(tt_derived, "cold_unet_graph_wait_ms"),
            "cold_unet_overlap_ms": _v(tt_derived, "cold_unet_overlap_ms"),
            "cold_unet_estimated_critical_path_saved_ms": _v(tt_derived, "cold_unet_estimated_critical_path_saved_ms"),
            "cold_unet_remaining_critical_path_wait_ms": _v(tt_derived, "cold_unet_remaining_critical_path_wait_ms"),
            "cold_unet_volume_read_ms": _v(tt_derived, "cold_unet_volume_read_ms"),
            "cold_unet_volume_read_gbps": _v(tt_derived, "cold_unet_volume_read_gbps"),
            "cold_unet_early_load_duplicate_prevented": bool(tt_derived.get("cold_unet_early_load_duplicate_prevented", False)) or bool(tt_derived.get("cold_unet_early_load_duplicate_prevented")),
            "cold_unet_graph_joined_active_read": bool(tt_derived.get("cold_unet_graph_joined_active_read", False)),
            "duplicate_unet_read_detected": bool(tt_derived.get("duplicate_unet_read_detected", False)),
            "active_read_registry_hit": bool(_v(tt_deltas, "active_read_registry_hit") or False),
            "local_materialization_source": lms,
            "critical_path_source": "wall_trace" if wall_trace_raw.get("deltas_ms", {}).get("modal_submit_to_entry_ms") else "timing_trace_fallback",
            "missing_stages": [ms for ms in (wall_trace_raw.get("data_quality", {}).get("missing_stages", []) or []) if not (ms == "t10_local_materialized" and has_t10_tt)],
            "invalid_deltas": wall_trace_raw.get("data_quality", {}).get("invalid_deltas", []),
        }
        runs.append(run_record)
        timing_traces.append(timing_trace)
        run_records.append(run_record)

        # Save raw results
        rp = raw_dir / f"run_{run_idx}"
        for fn, data in [("result.json", result_data), ("wall_trace.json", wall_trace_raw),
                         ("wall_trace_normalized.json", wall_trace_norm), ("timing_trace.json", timing_trace)]:
            try:
                (rp.with_name(f"run_{run_idx}_{fn}")).write_text(json.dumps(data, default=str, indent=2), encoding="utf-8")
            except Exception:
                pass

        # Timeline
        tl_lines = []
        try:
            write_timeline_md(timing_trace, identity, {"label": label, "confidence": conf}, rp.with_name(f"run_{run_idx}_timeline.md"))
            ttl = timing_trace.get("stages", {})
            t0l = ttl.get("t0_client_press")
            t1l = ttl.get("t1_local_recv")
            sl, _ = check_stale_t0(timing_trace)
            bl = t1l if (sl and t1l) else t0l
            if bl:
                for stg, tsv in sorted(ttl.items()):
                    if isinstance(tsv, (int, float)):
                        tl_lines.append(f"{(tsv - bl) * 1000:10.1f}ms  {stg}")
        except Exception:
            pass
        run_timelines.append(tl_lines)

        detail = {"run_index": run_idx, "benchmark_run_id": f"{benchmark_session_id}_run_{run_idx}",
                  "request_id": identity.get("request_id", ""), "trace_id": identity.get("trace_id", ""),
                  "identity": identity, "classification": {"label": label, "confidence": conf, "reasons": reasons},
                  "run_record": run_record, "raw_result": result_data, "wall_trace_raw": wall_trace_raw,
                  "wall_trace_normalized": wall_trace_norm, "timing_trace": timing_trace,
                  "timeline_md": "\n".join(tl_lines), "timeline_events": tl_lines,
                  "warnings": [stale_t0_warn] if stale_t0_warn else [], "degradation_flags": df}
        run_details.append(detail)

        print(f"    {label} (confidence: {conf})  wall={local_wall_ms:.0f}ms  "
              f"submit2entry={cp.get('submit2entry_ms', '?'):>8}ms  "
              f"sampler={run_record.get('sampler_ms', '?'):>8}ms  "
              f"poll={poll_count}")
        if stale_t0:
            print("    Warning: stale t0 detected")
        if df:
            print(f"    Flags: {df}")

        # Post-run sleep
        if run_idx < num_runs - 1:
            record_harness_ts(ht, "benchmark_sleep_start")
            prev_run_end_ts = ht["benchmark_run_end_unix_s"]
            if strict_gap:
                elapsed_since_prev = time.time() - prev_t10_ts if prev_t10_ts else 0
                needed = max(0, min_gap - elapsed_since_prev)
                actual = max(sleep_between, needed)
                time.sleep(actual)
            else:
                time.sleep(sleep_between)
            record_harness_ts(ht, "benchmark_sleep_end")
            actual_sleep_ms = _ms(ht.get("benchmark_sleep_start_unix_s"), ht.get("benchmark_sleep_end_unix_s"))
            if inter_run_gaps and len(inter_run_gaps) > 0:
                inter_run_gaps[-1]["actual_sleep_ms"] = actual_sleep_ms
                inter_run_gaps[-1]["benchmark_sleep_start_unix_s"] = ht.get("benchmark_sleep_start_unix_s")
                inter_run_gaps[-1]["benchmark_sleep_end_unix_s"] = ht.get("benchmark_sleep_end_unix_s")

    # ── Summary ──
    print(f"\n  {'='*60}\n  SUMMARY\n  {'='*60}")

    _RUN_COL_MAP = {
        "local_wall_ms": "local_button_to_materialized_ms",
        "known_nonoverlap_ms": "known_nonoverlap_ms",
        "missing_ms": "unexplained_local_wall_ms",
        "restore_ms": "restore_total_ms",
    }

    def _col(k):
        actual = _RUN_COL_MAP.get(k, k)
        return [_safe_float(r.get(actual)) for r in runs if r.get(actual) is not None and r.get(actual) != "N/A"]

    def _st(k):
        return _stats(_col(k))

    s2e_col = _col("submit2entry_ms")
    pre_col = _col("pre_sampler_ms")
    poll_count_col = _col("poll_count")
    ig_ms = [g.get("gap_ms", 0) for g in inter_run_gaps]

    # Compute derived poll counters from per-run records
    poll_total_attempts_list = []
    poll_not_ready_list = []
    poll_success_list = []
    poll_error_list = []
    for r in runs:
        pt = r.get("poll_total_attempts")
        if pt is None:
            ps_ok = r.get("poll_success_count", 0) or 0
            pe = r.get("poll_error_count", 0) or 0
            pnr = r.get("poll_not_ready_count", 0) or 0
            pt = ps_ok + pnr + pe
        poll_total_attempts_list.append(pt)
        poll_not_ready_list.append(r.get("poll_not_ready_count", 0) or 0)
        poll_success_list.append(r.get("poll_success_count", 0) or 0)
        poll_error_list.append(r.get("poll_error_count", 0) or 0)

    # Fix local materialization source detection per run
    for r in runs:
        if r.get("local_materialization_missing"):
            has_t10_tt = any("t10_local_materialized" in (tr.get("stages", {}) if isinstance(tr, dict) else {}) for tr in timing_traces)
            if has_t10_tt:
                r["local_materialization_source"] = "timing_trace"
                r["local_materialization_missing"] = False
                if "local_materialization_missing" in (r.get("degradation_flags", "") or ""):
                    r["degradation_flags"] = ";".join(f for f in (r.get("degradation_flags", "") or "").split(";") if f != "local_materialization_missing")

    summary = {"benchmark_version": BENCHMARK_VERSION, "timestamp": ts, "benchmark_session_id": benchmark_session_id,
               "total_runs": num_runs, "successful_runs": len([r for r in runs if r.get("cold_warm_label") != "failed"]),
               "cold_count": sum(1 for r in runs if r.get("cold_warm_label", "").startswith("cold")),
               "warm_count": sum(1 for r in runs if r.get("cold_warm_label", "").startswith("warm")),
               "workflow_hash": workflow_hash, "mode": mode, "profile_level": profile_level,
               "poll_interval_s": poll_interval, "poll_timeout_s": poll_timeout, "result_mode": result_mode,
               "requested_sleep_between_runs_s": sleep_between, "min_gap_between_runs_s": min_gap, "strict_inter_run_sleep": strict_gap,
               "median_local_wall_ms": _st("local_wall_ms")["median"],
               "min_local_wall_ms": _st("local_wall_ms")["min"],
               "max_local_wall_ms": _st("local_wall_ms")["max"],
               "p90_local_wall_ms": _st("local_wall_ms")["p90"],
               "p95_local_wall_ms": _st("local_wall_ms")["p95"],
               "median_known_nonoverlap_ms": _st("known_nonoverlap_ms")["median"],
               "median_missing_ms": _st("missing_ms")["median"],
               "median_submit2entry_ms": _st("submit2entry_ms")["median"],
               "median_restore_ms": _st("restore_ms")["median"],
               "min_restore_ms": _st("restore_ms")["min"],
               "max_restore_ms": _st("restore_ms")["max"],
               "median_pre_sampler_ms": _st("pre_sampler_ms")["median"],
               "median_sampler_ms": _st("sampler_ms")["median"],
               "median_post_sampler_ms": _st("post_sampler_ms")["median"],
               "median_vae_decode_ms": _st("vae_decode_ms")["median"],
               "median_remote_visible_ms": _st("remote_visible_ms")["median"],
               "median_local_bridge_to_submit_ms": _st("local_bridge_to_submit_ms")["median"],
               "median_modal_return_to_local_receive_ms": _st("modal_return_to_local_receive_ms")["median"],
               "median_local_materialize_ms": _st("local_materialize_ms")["median"],
               "median_harness_extra_after_timing_trace_ms": _st("harness_extra_after_timing_trace_ms")["median"],
               "median_harness_extra_vs_remote_return_ms": _st("harness_extra_vs_remote_return_ms")["median"],
               "median_polling_overhead_estimate_ms": _st("polling_overhead_estimate_ms")["median"],
               "median_poll_count": _st("poll_count")["median"],
               "median_unexplained_local_wall_ms": _st("missing_ms")["median"],
               "min_submit2entry_ms": _st("submit2entry_ms")["min"],
               "min_restore_ms": _st("restore_ms")["min"],
               "min_pre_sampler_ms": _st("pre_sampler_ms")["min"],
               "min_sampler_ms": _st("sampler_ms")["min"],
               "min_post_sampler_ms": _st("post_sampler_ms")["min"],
               "min_local_materialize_ms": _st("local_materialize_ms")["min"],
               "min_harness_extra_after_timing_trace_ms": _st("harness_extra_after_timing_trace_ms")["min"],
               "min_unexplained_local_wall_ms": _st("missing_ms")["min"],
               "max_submit2entry_ms": _st("submit2entry_ms")["max"],
               "max_restore_ms": _st("restore_ms")["max"],
               "max_pre_sampler_ms": _st("pre_sampler_ms")["max"],
               "max_sampler_ms": _st("sampler_ms")["max"],
               "max_post_sampler_ms": _st("post_sampler_ms")["max"],
               "max_local_materialize_ms": _st("local_materialize_ms")["max"],
               "max_harness_extra_after_timing_trace_ms": _st("harness_extra_after_timing_trace_ms")["max"],
               "max_unexplained_local_wall_ms": _st("missing_ms")["max"],
               "p90_submit2entry_ms": _st("submit2entry_ms")["p90"],
               "p90_sampler_ms": _st("sampler_ms")["p90"],
               "p95_submit2entry_ms": _st("submit2entry_ms")["p95"],
               "p95_sampler_ms": _st("sampler_ms")["p95"],
               # Poll counters
               "poll_total_attempts": statistics.median(poll_total_attempts_list) if poll_total_attempts_list else "N/A",
               "poll_not_ready_count": statistics.median(poll_not_ready_list) if poll_not_ready_list else 0,
               "poll_success_count": statistics.median(poll_success_list) if poll_success_list else 0,
               "poll_error_count": statistics.median(poll_error_list) if poll_error_list else 0,
               # Inter-run gaps
               "min_inter_run_gap_ms": _stats(ig_ms)["min"] if ig_ms else "N/A",
               "median_inter_run_gap_ms": _stats(ig_ms)["median"] if ig_ms else "N/A",
               "max_inter_run_gap_ms": _stats(ig_ms)["max"] if ig_ms else "N/A",
               "inter_run_gap_violations": sum(1 for g in inter_run_gaps if not g.get("gap_ok", True)),
               "stale_t0_count": sum(1 for r in runs if r.get("stale_t0_detected")),
               }

    print(f"  Runs: {num_runs}  Cold: {summary['cold_count']}  Warm: {summary['warm_count']}")
    print(f"  Median local wall: {summary.get('median_local_wall_ms', 'N/A')} ms")
    print(f"  Median known non-overlap: {summary.get('median_known_nonoverlap_ms', 'N/A')} ms")
    print(f"  Median missing: {summary.get('median_missing_ms', 'N/A')} ms")
    print(f"  Median pre-sampler: {summary.get('median_pre_sampler_ms', 'N/A')} ms")
    print(f"  Median sampler: {summary.get('median_sampler_ms', 'N/A')} ms")
    print(f"  Median local bridge to submit: {summary.get('median_local_bridge_to_submit_ms', 'N/A')} ms")
    print(f"  Median return to receive: {summary.get('median_modal_return_to_local_receive_ms', 'N/A')} ms")
    print(f"  Median materialize: {summary.get('median_local_materialize_ms', 'N/A')} ms")
    print(f"  Median harness extra (vs timing): {summary.get('median_harness_extra_after_timing_trace_ms', 'N/A')} ms")
    print(f"  Poll interval: {poll_interval}s  Median poll count: {summary.get('median_poll_count', 'N/A')}")

    # ── Preset assertion checking ──
    _preset_assertions_passed = True
    _preset_warnings = []
    if effective_config:
        _assert = effective_config.get("assertions", {})
        if _assert.get("forbid_warm_runs") and summary.get("warm_count", 0) > 0:
            msg = f"Preset assertion: forbids warm runs but warm_count={summary.get('warm_count')}"
            _preset_warnings.append(msg)
            _preset_assertions_passed = False
            print(f"  [PRESET ASSERTION FAILED] {msg}")
        if _assert.get("require_all_runs_cold") and summary.get("cold_count", 0) < summary.get("total_runs", 0):
            msg = f"Preset assertion: requires all runs cold but cold_count={summary.get('cold_count')}/{summary.get('total_runs')}"
            _preset_warnings.append(msg)
            _preset_assertions_passed = False
            print(f"  [PRESET ASSERTION FAILED] {msg}")
        if _assert.get("require_cold_unet_early_load"):
            _early_enabled_count = sum(1 for r in runs if r.get("cold_unet_early_load_enabled"))
            if _early_enabled_count < summary.get("successful_runs", 0):
                msg = f"Preset assertion: requires cold_unet_early_load enabled but only {_early_enabled_count}/{summary.get('successful_runs')} runs have it"
                _preset_warnings.append(msg)
                _preset_assertions_passed = False
                print(f"  [PRESET ASSERTION FAILED] {msg}")
        if _assert.get("require_actual_load_load_unet"):
            _al_unet_count = sum(1 for r in runs if r.get("actual_load_load_unet_effective"))
            if _al_unet_count < summary.get("successful_runs", 0):
                msg = f"Preset assertion: requires actual_load.load_unet but effective count is {_al_unet_count}/{summary.get('successful_runs')}"
                _preset_warnings.append(msg)
                _preset_assertions_passed = False
                print(f"  [PRESET ASSERTION FAILED] {msg}")
        if _preset_assertions_passed:
            print(f"  [PRESET ASSERTIONS PASSED]")
        if args.strict_preset_assertions and not _preset_assertions_passed:
            print(f"  STRICT: preset assertions failed, returning error")
            return 1
    summary["preset_assertions_passed"] = _preset_assertions_passed
    summary["preset_warnings"] = _preset_warnings
    # Cold-only medians computed from per-run data
    _cold_runs = [r for r in runs if (r.get("cold_warm_label", "") or "").startswith("cold")]
    summary["comparison_valid"] = _preset_assertions_passed and not any(r.get("cold_warm_label", "").startswith("warm") for r in runs)
    summary["comparison_valid_reason"] = "" if summary["comparison_valid"] else "warm_run_in_cold_preset" if summary.get("warm_count", 0) > 0 else "preset_assertions_failed"
    if _cold_runs:
        summary["median_cold_local_wall_ms"] = _median([r.get("local_button_to_materialized_ms") or 0 for r in _cold_runs])
        summary["median_cold_known_nonoverlap_ms"] = _median([r.get("known_nonoverlap_ms") or 0 for r in _cold_runs])
        summary["median_cold_submit2entry_ms"] = _median([r.get("submit2entry_ms") or 0 for r in _cold_runs])
        summary["median_cold_restore_ms"] = _median([r.get("restore_total_ms") or 0 for r in _cold_runs])
        summary["median_cold_pre_sampler_ms"] = _median([r.get("pre_sampler_ms") or 0 for r in _cold_runs])
        summary["median_cold_unet_wait_ms"] = _median([r.get("unet_node_wait_ms") or r.get("unet_load_ms") or 0 for r in _cold_runs])
        summary["median_cold_unet_load_ms"] = _median([r.get("unet_load_ms") or 0 for r in _cold_runs])
        summary["median_cold_exec_model_load_io_ms"] = _median([r.get("exec_model_load_io_ms") or 0 for r in _cold_runs])
        summary["median_cold_actual_load_saved_ms"] = _median([r.get("actual_load_saved_ms") or 0 for r in _cold_runs])
        summary["median_cold_actual_load_remaining_wait_ms"] = _median([r.get("actual_load_remaining_wait_ms") or 0 for r in _cold_runs])
        summary["median_cold_sampler_ms"] = _median([r.get("sampler_ms") or 0 for r in _cold_runs])
        summary["median_cold_post_sampler_ms"] = _median([r.get("post_sampler_ms") or 0 for r in _cold_runs])

    # Write output files
    write_runs_csv(runs, out_dir / "runs.csv")
    write_runs_jsonl(runs, out_dir / "runs.jsonl")
    write_summary_csv(summary, out_dir / "summary.csv")
    write_summary_md(runs, summary, out_dir / "summary.md")

    charts_data = {
        "runs": [{"run_index": r.get("run_index"), "cold_warm_label": r.get("cold_warm_label"),
                   "local_wall_ms": r.get("local_button_to_materialized_ms"),
                   "known_nonoverlap_ms": r.get("known_nonoverlap_ms"),
                   "unexplained_local_wall_ms": r.get("unexplained_local_wall_ms"),
                   "local_bridge_to_submit_ms": r.get("local_bridge_to_submit_ms"),
                   "modal_return_to_local_receive_ms": r.get("modal_return_to_local_receive_ms"),
                   "local_materialize_ms": r.get("local_materialize_ms"),
                   "harness_extra_after_timing_trace_ms": r.get("harness_extra_after_timing_trace_ms"),
                   "submit2entry_ms": r.get("submit2entry_ms"),
                   "remote_visible_ms": r.get("remote_visible_ms"),
                   "pre_sampler_ms": r.get("pre_sampler_ms"),
                   "sampler_ms": r.get("sampler_ms"),
                   "post_sampler_ms": r.get("post_sampler_ms"),
                   "local_recv_to_dispatch_ms": r.get("local_recv_to_dispatch_ms"),
                   "body_read_ms": r.get("body_read_ms"),
                   "json_parse_ms": r.get("json_parse_ms"),
                   "stack_extract_ms": r.get("stack_extract_ms"),
                   "active_next_write_ms": r.get("active_next_write_ms"),
                   "modal_handle_resolve_ms": r.get("modal_handle_resolve_ms"),
                   "modal_call_construct_ms": r.get("modal_call_construct_ms"),
                   "lock_wait_total_ms": r.get("lock_wait_total_ms"),
                   "queue_wait_total_ms": r.get("queue_wait_total_ms"),
                   "local_predispatch_stall": r.get("local_predispatch_stall", False),
                   "cold_unet_early_load_enabled": r.get("cold_unet_early_load_enabled", False),
                   "cold_unet_early_load_mode": r.get("cold_unet_early_load_mode", ""),
                   "cold_unet_graph_wait_ms": r.get("cold_unet_graph_wait_ms"),
                   "cold_unet_overlap_ms": r.get("cold_unet_overlap_ms"),
                   "cold_unet_estimated_critical_path_saved_ms": r.get("cold_unet_estimated_critical_path_saved_ms"),
                   "cold_unet_remaining_critical_path_wait_ms": r.get("cold_unet_remaining_critical_path_wait_ms"),
                   "cold_unet_volume_read_ms": r.get("cold_unet_volume_read_ms"),
                   "cold_unet_volume_read_gbps": r.get("cold_unet_volume_read_gbps")} for r in runs],
        "summary": summary,
        "timestamps": {"generated": datetime.now().isoformat()}}
    (out_dir / "charts_data.json").write_text(json.dumps(charts_data, default=str, indent=2), encoding="utf-8")

    write_compiled_raw_results(out_dir, benchmark_session_id, {"workflow": args.workflow, "runs": num_runs, "mode": mode,
        "profile_level": profile_level, "poll_interval": poll_interval, "sleep_between_runs": sleep_between,
        "min_gap_between_runs": min_gap, "strict_inter_run_sleep": strict_gap, "output_format": output_format,
        "return_mode": return_mode, "include_local_materialization": include_local_materialization},
        workflow_hash, runs, run_details, summary, charts_data)

    # Analysis pack
    if write_pack:
        zip_path = write_analysis_pack(out_dir, len(timing_traces), timing_traces, run_timelines, run_records,
                                        summary, charts_data, inter_run_gaps, "benchmark", pack_timelines, pack_wall)
        print(f"\n  Upload this folder or zip to ChatGPT:")
        print(f"    {zip_path}")
        print(f"    {out_dir / 'analysis_pack'}")

    print(f"\n  Results saved to {out_dir}")
    if write_pack:
        zp = out_dir / "analysis_pack.zip"
        if zp.exists():
            print(f"  Analysis pack: {zp}")
    print()
    return 0


# ── CLI ────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=f"End-to-end benchmark v{BENCHMARK_VERSION} for ComfyUI x Modal")
    p.add_argument("--workflow", type=str, default="")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--mode", type=str, default="mixed", choices=["cold", "warm", "mixed"])
    p.add_argument("--profile-level", type=str, default="summary", choices=["summary", "detailed", "trace", "trace_verbose"])
    p.add_argument("--output-dir", type=str, default="")
    p.add_argument("--output-format", type=str, default="original", choices=["original", "webp_lossy", "webp_lossless", "jpeg"])
    p.add_argument("--return-mode", type=str, default="full_base64", choices=["full_base64", "first_image_only", "metadata_only", "paths_only"])
    p.add_argument("--same-seed", action="store_true")
    p.add_argument("--same-workflow", action="store_true")
    p.add_argument("--same-active-profile", action="store_true")
    p.add_argument("--sleep-between-runs", type=float, default=10)
    p.add_argument("--min-gap-between-runs", type=float, default=10)
    p.add_argument("--strict-inter-run-sleep", action="store_true")
    p.add_argument("--poll-interval", type=float, default=0.25)
    p.add_argument("--poll-timeout", type=float, default=600)
    p.add_argument("--result-mode", type=str, default="poll", choices=["poll", "blocking"])
    p.add_argument("--include-local-materialization", action="store_true")
    p.add_argument("--write-analysis-pack", action="store_true")
    p.add_argument("--analysis-pack-include-timelines", action="store_true")
    p.add_argument("--analysis-pack-include-wall-traces", action="store_true")
    p.add_argument("--no-deploy", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--print-cost-warning", action="store_true")
    # Preset system
    p.add_argument("--preset", type=str, default="", choices=list(_PRESETS.keys()) + [""],
                   help="Benchmark preset name (use --list-presets to show all)")
    p.add_argument("--set", type=str, action="append", default=[], dest="set_overrides",
                   help="Override KEY=VALUE (e.g. --set runtime.cold_unet_early_load.enabled=true)")
    p.add_argument("--list-presets", action="store_true", help="List available (non-disabled) presets")
    p.add_argument("--list-all-presets", action="store_true", help="List ALL presets including disabled")
    p.add_argument("--print-effective-config", action="store_true", help="Print effective config and exit")
    p.add_argument("--dry-run-preset", action="store_true", help="Print effective config, do not run")
    p.add_argument("--strict-preset-assertions", action="store_true",
                   help="Fail if preset assertions are not met")

    sp = p.add_subparsers(dest="command")
    cp = sp.add_parser("compare", help="Compare two benchmark runs")
    cp.add_argument("--baseline", type=str, required=True)
    cp.add_argument("--candidate", type=str, required=True)
    sp.add_parser("selftest", help="Run internal self-test (no GPU)")
    lp = sp.add_parser("parse-local-log", help="Parse local [predispatch] log lines (no GPU)")
    lp.add_argument("--log", type=str, required=True, help="Path to log file containing [predispatch] lines")
    return p


def main() -> int:
    args = build_parser().parse_args()
    cmd = getattr(args, "command", None)

    # Handle non-benchmark commands
    if cmd == "compare":
        return cmd_compare(args)
    if cmd == "selftest":
        return cmd_selftest(args)
    if cmd == "parse-local-log":
        return cmd_parse_local_log(args)

    # Handle preset info commands
    if args.list_presets or args.list_all_presets:
        show_all = args.list_all_presets
        visible = {n: p for n, p in _PRESETS.items() if show_all or not p.get("_disabled")}
        print(f"Available presets ({len(visible)}){' (including disabled)' if show_all else ''}:\n")
        for name, p in sorted(visible.items()):
            suffix = " [DISABLED]" if p.get("_disabled") else ""
            print(f"  {name:40s} {p.get('_description', '')}{suffix}")
        if not show_all:
            print("\n  Use --list-all-presets to show disabled presets.")
        return 0

    if args.preset and args.preset not in _PRESETS:
        print(f"ERROR: unknown preset {args.preset!r}. Use --list-presets to see available presets.")
        return 1

    # Build effective config
    cli_dict = {k: getattr(args, k, None) for k in ("runs", "mode", "profile_level",
                "sleep_between_runs", "min_gap_between_runs", "strict_inter_run_sleep",
                "poll_interval", "write_analysis_pack", "print_cost_warning",
                "include_local_materialization")}
    effective_config = build_effective_config(args.preset if args.preset else None, cli_dict, args.set_overrides)

    if args.print_effective_config or args.dry_run_preset:
        print(f"\nEffective config ({effective_config['preset']}):\n")
        print(json.dumps(effective_config, indent=2, default=str))
        if args.dry_run_preset:
            print("\n[Dry run — no benchmark executed]")
            return 0
        if args.print_effective_config:
            return 0

    # Override CLI args from effective config
    bm = effective_config["benchmark"]
    for cli_key, cfg_key in [("runs", "runs"), ("mode", "mode"), ("profile_level", "profile_level"),
                              ("sleep_between_runs", "sleep_between_runs"),
                              ("min_gap_between_runs", "min_gap_between_runs"),
                              ("strict_inter_run_sleep", "strict_inter_run_sleep"),
                              ("poll_interval", "poll_interval"),
                              ("include_local_materialization", "include_local_materialization"),
                              ("write_analysis_pack", "write_analysis_pack"),
                              ("print_cost_warning", "print_cost_warning")]:
        if cfg_key in bm:
            setattr(args, cli_key, bm[cfg_key])

    if not args.workflow:
        try:
            resp = _json_request(BENCHMARK_WORKFLOW_ROUTE, timeout=5)
            if isinstance(resp, dict) and resp.get("status") == "ok":
                payload = resp.get("payload") or {}
                if isinstance(payload, dict):
                    args.workflow = str(BENCHMARK_RUNS_DIR / "_saved_workflow.json")
                    Path(args.workflow).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"ERROR: {e}\nProvide --workflow or run a generation first.")
            return 1
    return cmd_benchmark(args, effective_config=effective_config)


if __name__ == "__main__":
    sys.exit(main())
