from __future__ import annotations

import asyncio
import json
import math
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modal_workspaces
from modal._logs import LogsFilters, tail_logs
from modal.client import _Client
from modal_proto import api_pb2


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts" / "phase_p1_parallel_golden_v1"
REPORT_PATH = ROOT / "reports" / "GOLDEN_LOST_EXECUTION_TIME_AUDIT_OCT07.md"
RAW_PLATFORM_PATH = ROOT / "reports" / "GOLDEN_LOST_EXECUTION_TIME_AUDIT_OCT07_platform_raw.json"
EXPECTED_SHA = "3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577"


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def first_mapping(value: Any, key: str) -> dict[str, Any]:
    for item in walk(value):
        if key in item and isinstance(item[key], dict):
            return item[key]
    return {}


def first_list_mapping(value: Any, key: str) -> list[dict[str, Any]]:
    for item in walk(value):
        candidate = item.get(key)
        if isinstance(candidate, list):
            return [x for x in candidate if isinstance(x, dict)]
    return []


def num(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def fmt(value: Any, digits: int = 3) -> str:
    return "N/A" if value is None else f"{float(value):.{digits}f}"


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * p / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def stats(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [float(row[key]) for row in rows if num(row.get(key)) is not None]
    if not values:
        return {name: None for name in ("N", "mean", "median", "sd", "min", "max", "p10", "p50", "p90")}
    return {
        "N": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
        "p10": percentile(values, 10),
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
    }


def latest_receipt() -> dict[str, Any]:
    receipts = []
    for path in (ROOT / ".v2ctl" / "deployments").glob("receipt_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_path"] = str(path)
            receipts.append(data)
        except (OSError, ValueError):
            pass
    return max(receipts, key=lambda item: int(item.get("deployment_version", 0) or 0))


def run_manifest_map() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in (ROOT / ".v2ctl" / "runs").glob("run_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            artifact = ((data.get("artifacts") or {}).get("run_artifact") or "")
            if artifact:
                result[str(Path(artifact).resolve())] = data
        except (OSError, ValueError):
            pass
    return result


def parse_outer_log(text: str, timestamp_ns: int) -> dict[str, Any] | None:
    match = re.search(r"\[v2\.golden\.outer\]\s+(\w+)\s+t_ns=(\d+)\s+elapsed_ms=([0-9.]+)", text)
    if not match:
        return None
    return {
        "name": match.group(1),
        "mono_ns": int(match.group(2)),
        "elapsed_ms": float(match.group(3)),
        "log_wall_ns": int(timestamp_ns),
        "text": text,
    }


async def fetch_platform(client: Any, app_id: str, task_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    response = await client.stub.TaskGetInfo(api_pb2.TaskGetInfoRequest(task_id=task_id))
    info = response.info
    since = datetime.fromtimestamp(float(info.enqueued_at) - 30.0, timezone.utc)
    until = datetime.fromtimestamp(float(info.finished_at) + 30.0, timezone.utc)
    logs: list[dict[str, Any]] = []
    async for batch in tail_logs(
        client,
        response.app_id,
        2000,
        since=since,
        until=until,
        filters=LogsFilters(task_id=task_id),
    ):
        for item in batch.items:
            raw = item.data.decode("utf-8", "replace") if isinstance(item.data, bytes) else str(item.data)
            logs.append({
                "timestamp_ns": int(item.timestamp_ns or 0),
                "file_descriptor": int(item.file_descriptor),
                "text": raw,
            })
    platform = {
        "task_id": task_id,
        "app_id": response.app_id,
        "enqueued_at": float(info.enqueued_at),
        "started_at": float(info.started_at),
        "finished_at": float(info.finished_at),
        "task_wall_ms": round((info.finished_at - info.started_at) * 1000.0, 3),
        "queue_to_task_start_ms": round((info.started_at - info.enqueued_at) * 1000.0, 3),
        "gpu_type": str(info.gpu_type),
    }
    return platform, logs


def derive(attempt: dict[str, Any], run_manifest: dict[str, Any], platform: dict[str, Any], logs: list[dict[str, Any]]) -> dict[str, Any]:
    events_path = Path(attempt["_path"]).with_name(attempt.get("events_file", "attempt_0_events.json"))
    try:
        events = json.loads(events_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        events = []
    adapter = first_mapping(events, "golden_adapter_timing")
    telemetry = attempt.get("golden_telemetry") or {}
    restore = telemetry.get("external_restore") if isinstance(telemetry, dict) else {}
    restore = restore if isinstance(restore, dict) else {}
    outer_logs = [parsed for item in logs if (parsed := parse_outer_log(item["text"], item["timestamp_ns"]))]
    method_entry = next((x for x in outer_logs if x["name"] == "remote_method_entry"), None)
    method_return = next((x for x in reversed(outer_logs) if x["name"] == "remote_method_return"), None)
    remote_outer_ms = None
    if method_entry and method_return:
        remote_outer_ms = (method_return["log_wall_ns"] - method_entry["log_wall_ns"]) / 1_000_000.0
    if remote_outer_ms is None:
        remote_outer_ms = num(adapter.get("golden_call_wall_ms"))
    task_wall = num(platform.get("task_wall_ms"))
    pre_method = None
    post_method = None
    if method_entry:
        pre_method = method_entry["log_wall_ns"] / 1_000_000.0 - float(platform["started_at"]) * 1000.0
    if method_return:
        post_method = float(platform["finished_at"]) * 1000.0 - method_return["log_wall_ns"] / 1_000_000.0
    execution_gap = task_wall - remote_outer_ms if task_wall is not None and remote_outer_ms is not None else None
    residual = (
        execution_gap - pre_method - post_method
        if execution_gap is not None and pre_method is not None and post_method is not None
        else None
    )
    caller = attempt.get("caller_timing") or {}
    caller_result_mono = num(caller.get("caller_result_received_mono_ns"))
    caller_invoke_mono = num(caller.get("caller_invoke_begin_mono_ns"))
    caller_close_mono = num(caller.get("caller_stream_closed_mono_ns"))
    marks = {}
    for item in first_list_mapping(attempt, "marks"):
        if item.get("mark"):
            marks[str(item["mark"])] = num(item.get("elapsed_ms"))
    stage_values = {}
    for stage in first_list_mapping(attempt, "stages"):
        start = num(stage.get("entry_monotonic_ns"))
        end = num(stage.get("end_monotonic_ns"))
        if start is not None and end is not None and end >= start:
            stage_values[str(stage.get("name", ""))] = (end - start) / 1_000_000.0
    run_id = attempt.get("request_id", "")
    return {
        "request_id": run_id,
        "cohort": Path(attempt["_path"]).parent.name,
        "valid": bool(attempt.get("valid")),
        "true_cold": bool(attempt.get("true_cold")),
        "excluded_reason": "" if run_manifest.get("deploy_fingerprint") == CURRENT_DEPLOY else "smoke/retry before final deployment",
        "deploy_fingerprint": run_manifest.get("deploy_fingerprint", ""),
        "output_sha": ((attempt.get("validation") or {}).get("observed_output_shas") or [None])[0],
        "region": ((attempt.get("identity") or {}).get("region") or ""),
        "task_id": platform.get("task_id"),
        "task_enqueued_at": platform.get("enqueued_at"),
        "task_started_at": platform.get("started_at"),
        "task_finished_at": platform.get("finished_at"),
        "startup_dashboard_ms": None,
        "execution_dashboard_ms": None,
        "task_wall_ms": task_wall,
        "queue_to_task_start_ms": platform.get("queue_to_task_start_ms"),
        "remote_outer_ms": remote_outer_ms,
        "execution_minus_outer_ms": execution_gap,
        "pre_method_ms": pre_method,
        "post_method_ms": post_method,
        "unaccounted_ms": residual,
        "external_restore_ms": num(restore.get("restore_total_ms")),
        "golden_call_wall_ms": num(adapter.get("golden_call_wall_ms")),
        "golden_stage_span_ms": num(adapter.get("golden_stage_span_ms")),
        "golden_pre_stage_overhead_ms": num(adapter.get("golden_pre_stage_overhead_ms")),
        "golden_post_stage_overhead_ms": num(adapter.get("golden_post_stage_overhead_ms")),
        "execute_enter_ms": marks.get("execute_enter"),
        "restore_done_ms": marks.get("restore_done"),
        "request_setup_done_ms": marks.get("request_setup_done"),
        "clip_load_begin_ms": marks.get("clip_load_begin"),
        "clip_load_done_ms": marks.get("clip_load_done"),
        "clip_stage_ms": stage_values.get("golden_clip_load"),
        "clip_forward_stage_ms": stage_values.get("golden_clip_forward"),
        "unet_stage_ms": stage_values.get("golden_unet_load"),
        "sampling_stage_ms": stage_values.get("golden_sampling"),
        "vae_load_stage_ms": stage_values.get("golden_vae_load"),
        "vae_decode_stage_ms": stage_values.get("golden_vae_decode"),
        "caller_timing": caller,
        "caller_result_after_invoke_ms": (
            (caller_result_mono - caller_invoke_mono) / 1_000_000.0
            if caller_result_mono is not None and caller_invoke_mono is not None
            else None
        ),
        "caller_close_after_result_ms": (
            (caller_close_mono - caller_result_mono) / 1_000_000.0
            if caller_close_mono is not None and caller_result_mono is not None
            else None
        ),
        "platform": platform,
        "outer_log_events": outer_logs,
        "external_restore_raw": restore,
        "golden_adapter_raw": adapter,
        "task_logs_raw": logs,
    }


def table(rows: list[dict[str, Any]], keys: list[tuple[str, str]]) -> str:
    def cell(value: Any) -> str:
        if value is None:
            return "N/A"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, dict):
            return "present"
        if isinstance(value, float):
            return fmt(value)
        return str(value)

    head = "| " + " | ".join(label for label, _ in keys) + " |\n|" + "|".join("---" for _ in keys) + "|\n"
    body = "".join("| " + " | ".join(cell(row.get(key)) for _, key in keys) + " |\n" for row in rows)
    return head + body


def build_report(rows: list[dict[str, Any]], receipt: dict[str, Any]) -> str:
    accepted = [row for row in rows if not row["excluded_reason"]]
    excluded = [row for row in rows if row["excluded_reason"]]
    metric_keys = [
        ("Task wall", "task_wall_ms"), ("Remote outer", "remote_outer_ms"),
        ("Execution−outer", "execution_minus_outer_ms"), ("Pre-method", "pre_method_ms"),
        ("Post-method", "post_method_ms"), ("External restore", "external_restore_ms"),
        ("Unaccounted", "unaccounted_ms"),
    ]
    lines = [
        "# Golden Lost Execution Time Audit — 2026-10-07",
        "",
        "## Scope and identity",
        f"- Canonical source SHA: `4cbc52005909edd0f76aadf97f9adcfbe4b0490e`.",
        f"- Deployment fingerprint: `{receipt.get('deploy_fingerprint', '')}`.",
        "- Profile: `golden_p1_parallel_c0_p8_h100`; app: `batch-c0-p8-h100`.",
        "- Workspace: Testing5 (`ws_c1487d319820`). Region: **us-central**. GPU: H100!.",
        f"- Expected output SHA: `{EXPECTED_SHA}`.",
        "- Accepted cohort: six sequential TRUE-COLD runs on deployment version 3. Smoke/retry attempts are retained below and excluded from cohort statistics.",
        "",
        "## Lifecycle map and timer definitions",
        "1. Modal platform container/task lifecycle is represented here by machine-readable `TaskGetInfo` (`enqueued_at`, `started_at`, `finished_at`). The dashboard labels `Startup` and `Execution` were not exposed as named fields by the v1.4.3 SDK/API path used by v2ctl; they are therefore `N/A`, not inferred.",
        "2. The earliest application boundary is remote `restore()` first executable line (`remote_python_resume_*`), followed by application restore return (`restore_method_end_*`).",
        "3. `remote_method_entry` and `remote_method_return` are read from Modal task stdout `[v2.golden.outer]` lines; their log-record wall timestamps are used for cross-boundary accounting, while their `t_ns` values remain remote monotonic evidence.",
        "4. `golden_call_wall_ms` is the adapter's `golden_call_start → golden_call_end`, not the whole remote method wall. `golden_outer_ms` is the outer method-entry → method-return interval from task logs.",
        "5. `External restore` is copied adapter restore metadata; its `restore_total_ms` is remote-process `perf_counter`/monotonic duration from `restore()` entry to return. It is not created by `golden_restore()`.",
        "6. Caller timestamps use the host harness process's `time.time_ns` and `time.perf_counter_ns`. The client exposed only a terminal stream result, so first activity is labeled post-stream fallback where intermediate event delivery was not observable.",
        "",
        "## Complete lifecycle/code trace",
        "- `comfymodal_runtime/modal_app.py:24222-24254`: outer async-generator wrapper surrounds Golden method invocation, performs final release, and emits the envelope log after stream closure.",
        "- `comfymodal_runtime/modal_app.py:22848-22907`: `run_golden_parallel_stream` marks remote method entry, pre-yield/post-yield seams, and remote method return.",
        "- `comfymodal_runtime/modal_app.py:12328-12367`: `restore()` captures first executable remote resume timestamps and selects minimal Golden restore when enabled.",
        "- `comfymodal_runtime/modal_app.py:12155-12326`: minimal restore performs mutable-state reset, logical GPU repair, source-thread restore setup when deploy-enabled, generation check, and restore-end timestamps.",
        "- `comfymodal_runtime/modal_app.py:23048-23627`: Golden adapter validates request/identity/volume/isolation, ensures GPU readiness, records `golden_call_start`, awaits the Golden executor, and records `golden_call_end`.",
        "- `comfymodal_runtime/golden_parallel.py:379-602`: Golden root and existing marks cover execute entry, restore observation, request setup, CLIP/UNET, sampling/VAE, teardown, persistence, and return arming.",
        "- `comfymodal_runtime/golden_serial.py:10094-10182`: `golden_restore` copies adapter restore metadata and explicitly owns no restore work.",
        "- `tools/benchmark_v2_direct.py:10685-10778,11814-11905`: caller invocation/result/stream-close timestamps and immutable attempt artifacts.",
        "- `tools/v2_control/backend.py:654-780`: v2ctl caller subprocess wall (`started_at`, `ended_at`, `elapsed_seconds`) and identity-bound artifact discovery.",
        "",
        "## Platform semantics limitation",
        "`TaskGetInfo` is direct platform evidence, but this report does not relabel `finished_at − started_at` as dashboard `Execution` without a documented semantic mapping. It is reported as **Modal TaskInfo task wall**. Dashboard Startup/Execution values were not programmatically retained by v2ctl or the receipt and no screenshot values were supplied; those cells are N/A.",
        "",
        "## Accepted raw rows",
        table(accepted, [("Run", "cohort"), ("Request", "request_id"), ("SHA", "output_sha"), ("Task wall ms", "task_wall_ms"), ("Remote outer ms", "remote_outer_ms"), ("Exec−outer ms", "execution_minus_outer_ms"), ("Pre-method ms", "pre_method_ms"), ("Post-method ms", "post_method_ms"), ("External restore ms", "external_restore_ms"), ("Unaccounted ms", "unaccounted_ms")]),
        "",
        "## Excluded/retried raw rows",
        table(excluded, [("Cohort", "cohort"), ("Request", "request_id"), ("Deploy fingerprint", "deploy_fingerprint"), ("Valid", "valid"), ("True cold", "true_cold"), ("Reason", "excluded_reason")]),
        "",
        "## Summary statistics — accepted N=6",
        "| Metric | N | Mean | Median | SD | Min | Max | p10 | p50 | p90 |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, key in metric_keys:
        s = stats(accepted, key)
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (label, s["N"] or "N/A", *(fmt(s[name]) for name in ("mean", "median", "sd", "min", "max", "p10", "p50", "p90"))))
    lines += [
        "",
        "## Per-run reconciliation",
        "The accounting identity is `TaskInfo task wall = pre-method + remote outer + post-method + residual`. These terms use platform task/log wall timestamps; residual is the arithmetic remainder, not a causal attribution.",
        table(accepted, [("Run", "cohort"), ("Task wall", "task_wall_ms"), ("Pre-method", "pre_method_ms"), ("Remote outer", "remote_outer_ms"), ("Post-method", "post_method_ms"), ("Residual", "unaccounted_ms")]),
        "",
        "## Master waterfall / measured boundaries",
        table(accepted, [("Run", "cohort"), ("TaskInfo wall", "task_wall_ms"), ("Dashboard Startup", "startup_dashboard_ms"), ("Dashboard Execution", "execution_dashboard_ms"), ("Remote outer", "remote_outer_ms"), ("External restore", "external_restore_ms"), ("Golden call", "golden_call_wall_ms"), ("Golden stage span", "golden_stage_span_ms"), ("Caller result after invoke", "caller_result_after_invoke_ms"), ("Caller close after result", "caller_close_after_result_ms")]),
        "",
        "## Existing Golden boundary values",
        table(accepted, [("Run", "cohort"), ("execute_enter", "execute_enter_ms"), ("restore_done", "restore_done_ms"), ("request_setup_done", "request_setup_done_ms"), ("CLIP begin", "clip_load_begin_ms"), ("CLIP done", "clip_load_done_ms"), ("CLIP stage", "clip_stage_ms"), ("CLIP forward", "clip_forward_stage_ms"), ("UNET", "unet_stage_ms"), ("Sampling", "sampling_stage_ms"), ("VAE load", "vae_load_stage_ms"), ("VAE decode", "vae_decode_stage_ms")]),
        "",
        "## Evidence ledger",
        "- Supported: all six accepted attempts have `valid=true`, `true_cold=true`, `restore_count=1`, `request_count=1`, exact output SHA, region `us-central`, and source controls CURRENT / 4 ms launch gap / QD mode CURRENT / QD4 geometry.",
        "- Supported: `External restore` is remote-process restore duration and includes the measured source-thread restore setup on this profile; it is not platform snapshot time.",
        "- Supported: task/log wall accounting bounds the platform task wall relative to remote method outer wall; residuals are explicit.",
        "- Unresolved: Modal dashboard labels Startup and Execution are not retained in machine-readable v2ctl receipts/API fields used here; TaskInfo wall is not silently promoted to those labels.",
        "- Unresolved: the client stream adapter does not expose intermediate first-event timing; caller result timing is direct, first activity is post-stream fallback where labeled.",
        "- Clock limitation: remote monotonic timestamps are only subtracted within the remote process; host monotonic timestamps are only subtracted within the harness; cross-boundary rows use wall timestamps and disclose the limitation.",
        "",
        "## Optimization candidates (not changed)",
        "| Candidate | Measured cost | Owner | Essential? | Snapshotable/cacheable/removable? |",
        "|---|---:|---|---|---|",
        "| Source-thread restore setup | See `external_restore_raw.source_thread_restore_setup_ms` per row | application restore | Not established | Requires separate causal experiment; no change here |",
        "| Pre-method interval before Golden call | See `pre_method_ms` | adapter/platform boundary | Not established | Unknown; no change here |",
        "| Post-method interval after remote return | See `post_method_ms` | platform/result handling boundary | Not established | Unknown; no change here |",
        "",
        "## Raw evidence",
        f"- Per-run attempt/event artifacts: `{ARTIFACT_ROOT}`.",
        f"- Platform TaskInfo and task-log capture retained at `{RAW_PLATFORM_PATH}`.",
        f"- Deployment receipt: `{receipt.get('_path', '')}`.",
        "",
        "No optimization or source scheduler change was made in this audit.",
    ]
    return "\n".join(lines) + "\n"


async def main() -> None:
    global CURRENT_DEPLOY
    receipt = latest_receipt()
    CURRENT_DEPLOY = str(receipt.get("deploy_fingerprint", ""))
    run_map = run_manifest_map()
    destination = modal_workspaces.resolve_modal_destination(ROOT)
    client = await _Client.from_credentials(destination["token_id"], destination["token_secret"])
    rows: list[dict[str, Any]] = []
    raw_platform: dict[str, Any] = {"schema": "golden_lost_execution_platform_raw_v1", "runs": {}}
    for attempt_path in sorted(ARTIFACT_ROOT.glob("cohort_*/attempt_0.json")):
        try:
            attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        attempt["_path"] = str(attempt_path)
        manifest = run_map.get(str(attempt_path.resolve()), {})
        task_id = str(((attempt.get("identity") or {}).get("container_task_id") or ""))
        if not task_id:
            continue
        platform, logs = await fetch_platform(client, destination.get("app_id", ""), task_id)
        raw_platform["runs"][attempt.get("request_id", task_id)] = {"platform": platform, "logs": logs}
        rows.append(derive(attempt, manifest, platform, logs))
    rows.sort(key=lambda row: row["cohort"])
    current_rows = [row for row in rows if row["deploy_fingerprint"] == CURRENT_DEPLOY]
    accepted_ids = {row["request_id"] for row in current_rows[-6:]}
    for row in rows:
        if row["deploy_fingerprint"] == CURRENT_DEPLOY and row["request_id"] not in accepted_ids:
            row["excluded_reason"] = "smoke after final deployment"
    RAW_PLATFORM_PATH.write_text(json.dumps(raw_platform, indent=2, sort_keys=True), encoding="utf-8")
    REPORT_PATH.write_text(build_report(rows, receipt), encoding="utf-8")
    print(json.dumps({"report": str(REPORT_PATH), "raw_platform": str(RAW_PLATFORM_PATH), "rows": len(rows), "accepted": sum(not r["excluded_reason"] for r in rows)}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
