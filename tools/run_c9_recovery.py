#!/usr/bin/env python
"""Serial runner for the C9 source-only recovery campaign.

The runner owns only scheduling and durable attempt evidence.  It does not
generate a summary report, does not read E04 state, and never overlaps remote
calls.  A caller supplies the report directory; ``ledger.json`` and one JSON
file per attempt are written there.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

APP_DEFAULT = "sept-unetclip-c9-recovery-source-only"
MODELS = {"clip": "qwen_3_4b.safetensors", "unet": "z_image_turbo_bf16.safetensors"}
ROLES = ("clip", "unet")
QD_VALUES = (2, 4, 8)
OBSERVATIONS = 10
BLOCK_BYTES = 32 * 1024 * 1024
LEDGER_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def campaign_schedule(observations: int = OBSERVATIONS) -> list[dict[str, Any]]:
    """Return exactly the fixed C9 geometry in deterministic order."""
    if isinstance(observations, bool) or not 1 <= int(observations) <= OBSERVATIONS:
        raise ValueError(f"C9 recovery observations must be between 1 and {OBSERVATIONS}")
    schedule: list[dict[str, Any]] = []
    index = 0
    for observation in range(1, int(observations) + 1):
        for qd in QD_VALUES:
            for role in ROLES:
                index += 1
                schedule.append({
                    "campaign_index": index,
                    "observation": observation,
                    "role": role,
                    "model_name": MODELS[role],
                    "qd": qd,
                    "block_bytes": BLOCK_BYTES,
                    "block_mib": 32,
                    "cell_id": f"{role}_qd{qd}",
                    "attempt_id": f"c9_o{observation:02d}_{role}_qd{qd}",
                })
    if len(schedule) != 2 * 3 * int(observations):
        raise AssertionError("C9 schedule cardinality changed")
    return schedule


def _new_ledger(app_name: str, observations: int = OBSERVATIONS) -> dict[str, Any]:
    schedule = campaign_schedule(observations)
    return {
        "version": LEDGER_VERSION,
        "experiment": "c9_recovery",
        "arm": "source_only",
        "app": app_name,
        "geometry": {
            "roles": list(ROLES),
            "models": dict(MODELS),
            "qd_values": list(QD_VALUES),
            "block_bytes": BLOCK_BYTES,
            "observations_per_model_qd": observations,
            "expected_attempts_per_run": len(schedule),
        },
        "status": "PENDING",
        "runs": [],
        "attempts": [],
        "updated_at": _now(),
    }


def _load_ledger(path: Path, app_name: str, observations: int = OBSERVATIONS) -> dict[str, Any]:
    if not path.exists():
        return _new_ledger(app_name, observations)
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unreadable C9 ledger: {path}") from exc
    if not isinstance(ledger, dict) or ledger.get("experiment") != "c9_recovery":
        raise RuntimeError("report directory contains a non-C9 ledger; refusing state reuse")
    if ledger.get("arm") != "source_only":
        raise RuntimeError("C9 ledger arm is not source_only")
    if ledger.get("geometry") != _new_ledger(app_name, observations)["geometry"]:
        raise RuntimeError("C9 ledger geometry mismatch; refusing state reuse")
    ledger.setdefault("runs", [])
    ledger.setdefault("attempts", [])
    ledger["app"] = app_name
    return ledger


def validate_c9_result(result: Any, item: dict[str, Any]) -> list[str]:
    """Validate the returned evidence without trusting a summary field."""
    failures: list[str] = []
    if not isinstance(result, dict):
        return [f"result_not_object:{type(result).__name__}"]
    if result.get("status") != "ok":
        failures.append("status_not_ok")
    if result.get("experiment") != "c9_recovery":
        failures.append("experiment_marker_missing")
    if result.get("arm") != "source_only" or result.get("execution_arm") != "source_only":
        failures.append("arm_not_source_only")
    if result.get("role") != item["role"] or result.get("model_name") != item["model_name"]:
        failures.append("model_identity_mismatch")
    if result.get("configured_source_qd") != item["qd"]:
        failures.append("qd_mismatch")
    if result.get("source_block_bytes") != BLOCK_BYTES:
        failures.append("top_level_block_bytes_mismatch")
    fixed = result.get("fixed_config")
    expected = {
        "execution_arm": "source_only",
        "configured_qd": item["qd"],
        "producer_count": item["qd"],
        "source_block_bytes": BLOCK_BYTES,
        "h2d_target_bytes": None,
        "aggregation_enabled": False,
        "cuda_used": False,
        "h2d_used": False,
        "model_construction": False,
    }
    if not isinstance(fixed, dict):
        failures.append("fixed_config_missing")
    else:
        failures.extend(f"fixed_config_{key}_mismatch" for key, value in expected.items() if fixed.get(key) != value)
    for key in ("source_only", "cuda_used", "h2d_used", "model_construction"):
        if result.get(key) is not ({"source_only": True}.get(key, False)):
            failures.append(f"{key}_contract_failed")
    if result.get("FILE_TO_CUDA_WALL_MS") is not None:
        failures.append("file_to_cuda_metric_present")
    metrics = result.get("metrics")
    if not isinstance(metrics, dict) or metrics.get("H2D_WALL_MS") is not None:
        failures.append("h2d_metric_present")
    for key in ("coverage", "byte_reconciliation"):
        value = result.get(key)
        if key == "coverage" and (not isinstance(value, dict) or value.get("ok") is not True):
            failures.append("coverage_failed")
        if key == "byte_reconciliation" and (not isinstance(value, dict) or value.get("returned_equals_expected") is not True):
            failures.append("byte_reconciliation_failed")
    reads = result.get("physical_reads")
    if not isinstance(reads, list) or not reads:
        failures.append("physical_reads_missing")
    else:
        region_ends: dict[int, int] = {}
        for row in result.get("regions") or []:
            if not isinstance(row, dict):
                continue
            producer_id = row.get("producer_id")
            end = row.get("end")
            if isinstance(producer_id, int) and isinstance(end, int):
                region_ends[producer_id] = end
        for index, read in enumerate(reads):
            if not isinstance(read, dict):
                failures.append(f"physical_read_{index}_not_object")
                continue
            requested = read.get("requested_bytes")
            returned = read.get("returned_bytes")
            if not isinstance(requested, int) or not isinstance(returned, int) or not 0 <= returned <= requested:
                failures.append(f"physical_read_{index}_byte_counts_invalid")
            if not isinstance(read.get("offset"), int):
                failures.append(f"physical_read_{index}_offset_missing")
            if read.get("syscall_begin_ns") is None or read.get("syscall_end_ns") is None:
                failures.append(f"physical_read_{index}_time_missing")
            if isinstance(requested, int) and requested <= 0:
                failures.append(f"physical_read_{index}_request_nonpositive")
            if isinstance(requested, int) and requested > BLOCK_BYTES:
                failures.append(f"physical_read_{index}_request_exceeds_32mib")
            worker_id = read.get("worker_id")
            offset = read.get("offset")
            is_final_tail = (
                isinstance(worker_id, int)
                and isinstance(offset, int)
                and isinstance(requested, int)
                and offset + requested == region_ends.get(worker_id)
            )
            if isinstance(requested, int) and requested != BLOCK_BYTES and not is_final_tail:
                failures.append(f"physical_read_{index}_nonfinal_request_not_32mib")
        requested_sizes = [read.get("requested_bytes") for read in reads if isinstance(read, dict)]
        returned_sizes = [read.get("returned_bytes") for read in reads if isinstance(read, dict)]
        result["requested_physical_read_sizes"] = requested_sizes
        result["returned_physical_read_sizes"] = returned_sizes
        if any(not isinstance(size, int) or size <= 0 for size in returned_sizes):
            failures.append("physical_read_returned_size_invalid")
    if not isinstance(result.get("SOURCE_WALL_MS"), (int, float)) or result.get("SOURCE_WALL_MS", 0) <= 0:
        failures.append("source_wall_missing")
    if not isinstance(result.get("effective_GBps"), (int, float)) or result.get("effective_GBps", 0) <= 0:
        failures.append("effective_gbps_missing")
    if not isinstance(result.get("time_weighted_achieved_qd"), (int, float)):
        failures.append("time_weighted_qd_missing")
    if not isinstance(result.get("max_achieved_qd"), int) or result.get("max_achieved_qd", 0) < 1:
        failures.append("max_achieved_qd_missing")
    if not isinstance(result.get("workers"), list) or len(result["workers"]) != item["qd"]:
        failures.append("worker_evidence_missing")
    if not isinstance(result.get("filesystem_identity"), dict):
        failures.append("filesystem_identity_missing")
    if not isinstance(result.get("cpu_allocation"), dict):
        failures.append("cpu_allocation_missing")
    return failures


async def _invoke(function: Any, item: dict[str, Any]) -> dict[str, Any]:
    """Invoke one Modal call and await it fully before returning."""
    remote = getattr(function, "remote", None)
    aio = getattr(remote, "aio", None) if remote is not None else None
    if callable(aio):
        value = aio(item["role"], item["model_name"], item["qd"], item["attempt_id"])
    elif callable(remote):
        value = await asyncio.to_thread(remote, item["role"], item["model_name"], item["qd"], item["attempt_id"])
    elif callable(function):
        value = await asyncio.to_thread(function, item["role"], item["model_name"], item["qd"], item["attempt_id"])
    else:
        raise TypeError("remote function is not callable")
    if inspect.isawaitable(value):
        value = await value
    if not isinstance(value, dict):
        raise RuntimeError(f"remote returned {type(value).__name__}")
    return value


def _active_workspace() -> dict[str, Any]:
    path = _ROOT / ".modal_workspaces.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    active = data.get("active_workspace_id")
    workspace = next((item for item in data.get("workspaces", []) if item.get("id") == active), None)
    if not workspace or not workspace.get("token_id") or not workspace.get("token_secret"):
        raise RuntimeError("active Modal workspace is missing credentials")
    return workspace


def _function_from_modal(app_name: str, environment: str = "") -> Any:
    import modal

    workspace = _active_workspace()
    token_id = os.environ.get("MODAL_TOKEN_ID") or str(workspace["token_id"])
    token_secret = os.environ.get("MODAL_TOKEN_SECRET") or str(workspace["token_secret"])
    os.environ["MODAL_TOKEN_ID"] = token_id
    os.environ["MODAL_TOKEN_SECRET"] = token_secret
    client = modal.Client.from_credentials(token_id, token_secret)
    return modal.Function.from_name(
        app_name,
        "run_c9_recovery",
        client=client,
        environment_name=environment or workspace.get("environment") or None,
    )


async def run_campaign(
    app_name: str,
    report_dir: Path,
    *,
    function: Any | None = None,
    call: Callable[[Any, dict[str, Any]], Any] | None = None,
    environment: str = "",
    observations: int = OBSERVATIONS,
) -> dict[str, Any]:
    """Run the fixed 60-call campaign strictly serially."""
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = report_dir / "ledger.json"
    ledger = _load_ledger(ledger_path, app_name, observations)
    for previous_run in ledger.get("runs", []):
        if previous_run.get("status") == "RUNNING":
            previous_run.update({"status": "ABORTED", "finished_at": _now(), "abort_reason": "runner_interrupted"})
    for previous_attempt in ledger.get("attempts", []):
        if previous_attempt.get("status") == "RUNNING":
            previous_attempt.update({"status": "ABORTED", "finished_at": _now(), "error": "runner_interrupted"})
    schedule = campaign_schedule(observations)
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
    run = {"run_id": run_id, "started_at": _now(), "expected_attempts": len(schedule), "status": "RUNNING", "attempt_ids": []}
    ledger["runs"].append(run)
    ledger["status"] = "RUNNING"
    _atomic_write_json(ledger_path, ledger)
    if function is None and call is None:
        function = _function_from_modal(app_name, environment)
    results: list[dict[str, Any]] = []
    attempts_dir = report_dir / "runs"
    for item in schedule:
        attempt_id = f"{run_id}_{item['attempt_id']}"
        started = time.monotonic_ns()
        attempt = {
            **item,
            "run_id": run_id,
            "attempt_id": attempt_id,
            "status": "RUNNING",
            "started_at": _now(),
            "started_monotonic_ns": started,
            "artifact": str(attempts_dir / f"{attempt_id}.json"),
        }
        ledger["attempts"].append(attempt)
        run["attempt_ids"].append(attempt_id)
        _atomic_write_json(ledger_path, ledger)
        print(f"[c9] start={attempt_id} role={item['role']} qd={item['qd']}", flush=True)
        artifact: dict[str, Any] = {}
        try:
            if call is not None:
                value = call(function, item)
                if inspect.isawaitable(value):
                    value = await value
            else:
                value = await _invoke(function, item)
            failures = validate_c9_result(value, item)
            artifact = dict(value)
            artifact.update({"attempt_id": attempt_id, "run_id": run_id, "campaign_index": item["campaign_index"]})
            artifact["classification"] = "ELIGIBLE" if not failures else "DNF"
            if failures:
                artifact["validation_failures"] = failures
                attempt["status"] = "INVALID"
                attempt["error"] = ";".join(failures)
            else:
                attempt["status"] = "COMPLETE"
            results.append(artifact)
        except BaseException as exc:
            artifact = {
                **item,
                "attempt_id": attempt_id,
                "run_id": run_id,
                "status": "error",
                "classification": "DNF",
                "source_only": True,
                "error": f"{type(exc).__name__}:{exc}",
            }
            attempt["status"] = "FAILED"
            attempt["error"] = artifact["error"]
            results.append(artifact)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                # The failed attempt is still durable before honoring process
                # termination; the finally-like ledger update below runs.
                raise
        finally:
            finished = time.monotonic_ns()
            attempt.update({"finished_at": _now(), "finished_monotonic_ns": finished, "wall_ms": (finished - started) / 1_000_000.0})
            _atomic_write_json(Path(attempt["artifact"]), artifact)
            _atomic_write_json(ledger_path, ledger)
            print(f"[c9] end={attempt_id} status={attempt['status']} artifact={attempt['artifact']}", flush=True)
    successful = all(item.get("classification") == "ELIGIBLE" for item in results)
    final_status = "COMPLETE" if successful else "COMPLETE_WITH_FAILURES"
    run.update({"status": final_status, "finished_at": _now(), "completed_attempts": len(schedule)})
    ledger["status"] = final_status
    ledger["updated_at"] = _now()
    _atomic_write_json(ledger_path, ledger)
    return {"ledger": ledger, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True, help="caller-owned directory for ledger and attempt artifacts")
    parser.add_argument("--app", default=APP_DEFAULT)
    parser.add_argument("--env", default=os.environ.get("COMFYMODAL_C9_MODAL_ENV", ""), help="Modal environment containing the deployment")
    parser.add_argument("--observations", type=int, default=OBSERVATIONS, help="serial observations per model/QD cell (1-10; default 10)")
    args = parser.parse_args()
    try:
        output = asyncio.run(run_campaign(args.app, Path(args.report_dir), environment=args.env, observations=args.observations))
        print(f"[c9] complete attempts={len(output['results'])} ledger={Path(args.report_dir) / 'ledger.json'}", flush=True)
        return 0 if all(item.get("classification") == "ELIGIBLE" for item in output["results"]) else 2
    except Exception as exc:
        print(f"[c9] failed={type(exc).__name__}:{exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
