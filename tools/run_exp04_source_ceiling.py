#!/usr/bin/env python
"""Run the Phase-2 pure-source block/QD matrix serially.

The endpoint has no snapshot lifecycle, so every returned observation is
already source-only.  The runner still records an explicit non-applicable
snapshot classification and never runs calls concurrently.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DEFAULT_APP = "sept-unetclip-04-source-ceiling-oracle"
_MODELS = {
    "clip": "qwen_3_4b.safetensors",
    "unet": "z_image_turbo_bf16.safetensors",
}
_BLOCK_MIB_VALUES = (32, 64, 128, 256)
_QD_VALUES = (1, 2, 4, 8)
_ROLES = ("clip", "unet")
CELL_STATUSES = ("PENDING", "RUNNING", "COMPLETE", "INVALID", "FAILED")
_STATE_PATH = _ROOT / "unetClipExperimentsSeptember" / "source_h2d_decoupling_campaign_state.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, value: Any) -> None:
    """Replace a JSON file only after the complete document is durable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, path)
        except PermissionError:
            # OneDrive can deny replacement of a currently indexed file while
            # still allowing a durable in-place write.  Keep the campaign
            # resumable rather than dropping state; the temporary was already
            # fully fsynced before this fallback.
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def campaign_schedule(
    start_round: int,
    rounds: int,
    roles: Iterable[str] = _ROLES,
    qd_values: Iterable[int] = _QD_VALUES,
    block_mib_values: Iterable[int] = _BLOCK_MIB_VALUES,
) -> list[dict[str, Any]]:
    """Return the stable round-major order used by the source-only campaign."""
    schedule = []
    index = 0
    for run_number in range(start_round, start_round + rounds):
        for block_mib in block_mib_values:
            for qd in qd_values:
                for role in roles:
                    index += 1
                    schedule.append({
                        "campaign_index": index,
                        "round": run_number,
                        "role": role,
                        "model": _MODELS[role],
                        "qd": qd,
                        "block_mib": block_mib,
                        "block_bytes": block_mib * 1024 * 1024,
                        "cell_id": f"{role}_b{block_mib}_qd{qd}",
                    })
    return schedule


def _new_ledger(app_name: str, rounds: int) -> dict[str, Any]:
    cells = []
    for item in campaign_schedule(1, 1):
        cells.append({
            "cell_id": item["cell_id"],
            "role": item["role"],
            "model": item["model"],
            "qd": item["qd"],
            "block_mib": item["block_mib"],
            "block_bytes": item["block_bytes"],
            "status": "PENDING",
            "attempts": [],
        })
    return {
        "version": 2,
        "campaign": "source_h2d_decoupling",
        "phase": "phase_2_source_only",
        "eligibility_arm": "source_only",
        "historical_integrated_arms": ["static_e27", "fastsafe"],
        "app": app_name,
        "target_rounds": rounds,
        "status": "PENDING",
        "cells": cells,
        "updated_at": _now(),
    }


def _load_ledger(state_path: Path, app_name: str, rounds: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the campaign document and its ledger, upgrading the old state shape."""
    document: dict[str, Any] = {}
    if state_path.exists():
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise RuntimeError(f"campaign state must be a JSON object: {state_path}")
        document = loaded
    ledger = document.get("ledger")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("cells"), list):
        ledger = _new_ledger(app_name, rounds)
    else:
        ledger = dict(ledger)
        ledger["version"] = max(2, int(ledger.get("version", 1)))
        ledger.setdefault("campaign", "source_h2d_decoupling")
        ledger.setdefault("phase", "phase_2_source_only")
        ledger["eligibility_arm"] = "source_only"
        ledger.setdefault("historical_integrated_arms", ["static_e27", "fastsafe"])
        ledger.setdefault("target_rounds", rounds)
        ledger.setdefault("status", "PENDING")
    document["ledger"] = ledger
    return document, ledger


def _save_ledger(state_path: Path, document: dict[str, Any], ledger: dict[str, Any]) -> None:
    ledger["updated_at"] = _now()
    document["ledger"] = ledger
    phase = document.get("phases", {}).get("phase_2_source_only")
    if isinstance(phase, dict):
        phase["status"] = "complete" if ledger.get("status") == "COMPLETE" else "running"
        phase["ledger_version"] = ledger.get("version", 2)
        phase["cell_count"] = len(ledger.get("cells", []))
    _atomic_write_json(state_path, document)


def _cell(ledger: dict[str, Any], cell_id: str) -> dict[str, Any]:
    return next(cell for cell in ledger["cells"] if cell["cell_id"] == cell_id)


def validate_completed_artifact(
    path: Path,
    role: str,
    model: str,
    qd: int,
    block_bytes: int,
    attempt_id: str | None = None,
) -> tuple[bool, list[str]]:
    """Validate the identity, fixed configuration, and eligibility gate."""
    failures: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"unreadable_json:{type(exc).__name__}"]
    if not isinstance(data, dict):
        return False, ["artifact_not_object"]
    if attempt_id is not None and data.get("attempt_id") != attempt_id:
        failures.append("attempt_id_mismatch")
    if str(data.get("role", "")).lower() != role.lower():
        failures.append("role_mismatch")
    if data.get("model_name") != model:
        failures.append("model_mismatch")
    arm = data.get("arm")
    # Phase 2 is intentionally source-only.  Historical static-E27 artifacts
    # remain valid evidence for their own arm, but can never satisfy this
    # campaign's eligibility gate.
    if arm != "source_only":
        failures.append("arm_mismatch")
    fixed = data.get("fixed_config")
    expected = {
        "execution_arm": "source_only",
        "configured_qd": qd,
        "producer_count": qd,
        "source_block_bytes": block_bytes,
        "h2d_target_bytes": None,
        "aggregation_enabled": False,
        "cuda_used": False,
        "h2d_used": False,
        "model_construction": False,
    }
    if not isinstance(fixed, dict):
        failures.append("fixed_config_missing")
    else:
        for key, value in expected.items():
            if fixed.get(key) != value:
                failures.append(f"fixed_config_{key}_mismatch")
    fixed_expected = data.get("fixed_config_expected")
    if isinstance(fixed_expected, dict):
        for key, value in expected.items():
            if key in fixed_expected and fixed_expected.get(key) != value:
                failures.append(f"fixed_config_expected_{key}_mismatch")
    if data.get("status") != "ok":
        failures.append("status_not_ok")
    byte_validation = data.get("byte_validation")
    bytes_ok = byte_validation is True or (
        isinstance(byte_validation, dict) and byte_validation.get("ok") is True
    )
    if not bytes_ok:
        failures.append("byte_validation_failed")
    if data.get("source_only") is not True:
        failures.append("source_only_marker_missing")
    if data.get("cuda_used") is not False or data.get("h2d_used") is not False:
        failures.append("source_only_used_cuda_or_h2d")
    if data.get("FILE_TO_CUDA_WALL_MS") is not None:
        failures.append("source_only_file_to_cuda_metric_present")
    metrics = data.get("metrics")
    if not isinstance(metrics, dict) or metrics.get("H2D_WALL_MS") is not None:
        failures.append("source_only_h2d_metric_present")
    coverage = data.get("coverage")
    if not isinstance(coverage, dict) or coverage.get("ok") is not True:
        failures.append("source_only_coverage_failed")
    telemetry = data.get("physical_syscall_telemetry")
    if not isinstance(telemetry, list) or not telemetry:
        failures.append("source_only_syscall_telemetry_missing")
    elif any(
        not isinstance(event, dict)
        or not isinstance(event.get("requested_bytes"), int)
        or not isinstance(event.get("returned_bytes"), int)
        or event["requested_bytes"] < 0
        or not 0 <= event["returned_bytes"] <= event["requested_bytes"]
        for event in telemetry
    ):
        failures.append("source_only_syscall_telemetry_invalid")
    if data.get("classification") != "ELIGIBLE":
        failures.append("not_eligible")
    return not failures, failures


def _next_artifact_path(out_dir: Path, attempt_id: str, reserved: Iterable[str] = ()) -> Path:
    path = out_dir / f"{attempt_id}.json"
    reserved = set(reserved)
    if not path.exists() and attempt_id not in reserved:
        return path
    suffix = 2
    while True:
        candidate = out_dir / f"{attempt_id}_A{suffix}.json"
        if not candidate.exists():
            return candidate
        suffix += 1


def _refresh_cell_status(cell: dict[str, Any], target_rounds: Iterable[int]) -> None:
    attempts = cell.get("attempts", [])
    complete_rounds = {
        attempt.get("round") for attempt in attempts if attempt.get("status") == "COMPLETE"
    }
    target = set(target_rounds)
    if target and target.issubset(complete_rounds):
        cell["status"] = "COMPLETE"
    elif cell.get("status") == "RUNNING":
        cell["status"] = "RUNNING"
    elif any(attempt.get("status") == "FAILED" for attempt in attempts[-1:]):
        cell["status"] = "FAILED"
    elif any(attempt.get("status") == "INVALID" for attempt in attempts[-1:]):
        cell["status"] = "INVALID"
    else:
        cell["status"] = "PENDING"


def _active_workspace() -> dict:
    data = json.loads((_ROOT / ".modal_workspaces.json").read_text(encoding="utf-8"))
    active = data.get("active_workspace_id")
    workspace = next((item for item in data.get("workspaces", []) if item.get("id") == active), None)
    if not workspace or not workspace.get("token_id") or not workspace.get("token_secret"):
        raise RuntimeError("active Modal workspace is missing or has no credentials")
    return workspace


async def _call(
    function: Any,
    role: str,
    model: str,
    qd: int,
    block_bytes: int,
    attempt: str,
) -> dict[str, Any]:
    remote = getattr(function, "remote", None)
    aio = getattr(remote, "aio", None) if remote is not None else None
    if callable(aio):
        value = aio(role, model, "source_only", attempt, qd, block_bytes)
        return await value if asyncio.iscoroutine(value) else value
    value: Any = await asyncio.to_thread(function, role, model, "source_only", attempt, qd, block_bytes)
    if asyncio.iscoroutine(value):
        value = await value
    if not isinstance(value, dict):
        raise RuntimeError(f"remote returned {type(value).__name__}")
    return value


async def _run_campaign(
    app_name: str,
    out_dir: Path,
    start_round: int,
    rounds: int,
    roles: tuple[str, ...] = _ROLES,
    qd_values: tuple[int, ...] = _QD_VALUES,
    block_mib_values: tuple[int, ...] = _BLOCK_MIB_VALUES,
    state_path: Path | None = None,
) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_path or _STATE_PATH
    document, ledger = _load_ledger(state_path, app_name, rounds)
    schedule = campaign_schedule(start_round, rounds, roles, qd_values, block_mib_values)
    target_rounds = range(start_round, start_round + rounds)
    ledger["app"] = app_name
    ledger["target_rounds"] = rounds
    ledger["schedule"] = [
        {"campaign_index": item["campaign_index"], "cell_id": item["cell_id"], "round": item["round"]}
        for item in schedule
    ]
    _save_ledger(state_path, document, ledger)

    # Reconcile artifacts before importing Modal.  A valid artifact is the only
    # reason a scheduled request may be skipped; a corrupt or ineligible file is
    # retained as an INVALID attempt and receives a fresh filename below.
    results: list[dict] = []
    work: list[tuple[dict[str, Any], dict[str, Any], str, Path]] = []
    for item in schedule:
        cell = _cell(ledger, item["cell_id"])
        attempts = cell.setdefault("attempts", [])
        expected_id = f"{item['role']}_b{item['block_mib']}_qd{item['qd']}_R{item['round']}"
        existing = next(
            (attempt for attempt in reversed(attempts) if attempt.get("round") == item["round"]),
            None,
        )
        existing_path = Path(existing["artifact"]) if existing and existing.get("artifact") else out_dir / f"{expected_id}.json"
        if existing_path.exists():
            valid, failures = validate_completed_artifact(
                existing_path, item["role"], item["model"], item["qd"], item["block_bytes"],
                existing.get("attempt_id") if existing else expected_id,
            )
            if valid:
                if not existing:
                    attempts.append({
                        "attempt_id": expected_id, "round": item["round"],
                        "artifact": str(existing_path), "status": "COMPLETE",
                        "campaign_index": item["campaign_index"],
                    })
                else:
                    existing["status"] = "COMPLETE"
                _refresh_cell_status(cell, target_rounds)
                results.append(json.loads(existing_path.read_text(encoding="utf-8")))
                _save_ledger(state_path, document, ledger)
                continue
            if not existing or existing.get("status") != "INVALID":
                attempts.append({
                    "attempt_id": existing.get("attempt_id", expected_id) if existing else expected_id,
                    "round": item["round"], "artifact": str(existing_path),
                    "status": "INVALID", "error": ";".join(failures),
                    "campaign_index": item["campaign_index"], "finished_at": _now(),
                })
                _refresh_cell_status(cell, target_rounds)
                _save_ledger(state_path, document, ledger)
        if existing and existing.get("status") == "RUNNING" and not existing_path.exists():
            existing.update({"status": "FAILED", "error": "interrupted_without_artifact", "finished_at": _now()})
            _refresh_cell_status(cell, target_rounds)
            _save_ledger(state_path, document, ledger)
        attempt_id = expected_id
        artifact_path = _next_artifact_path(
            out_dir, attempt_id, (attempt.get("attempt_id") for attempt in attempts)
        )
        if artifact_path.stem != attempt_id:
            attempt_id = artifact_path.stem
        attempt_record = {
            "attempt_id": attempt_id, "round": item["round"],
            "artifact": str(artifact_path), "status": "RUNNING",
            "campaign_index": item["campaign_index"], "started_at": _now(),
        }
        attempts.append(attempt_record)
        cell["status"] = "RUNNING"
        _save_ledger(state_path, document, ledger)
        work.append((item, cell, attempt_id, artifact_path))

    if work:
        import modal

        workspace = _active_workspace()
        os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
        os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])
        client = modal.Client.from_credentials(workspace["token_id"], workspace["token_secret"])
        environment = workspace.get("environment", "")
        function = modal.Function.from_name(
            app_name, "run_source_ceiling_oracle", client=client,
            environment_name=environment or None,
        )
    else:
        function = None

    for item, cell, attempt_id, path in work:
        print(f"[exp04] start={attempt_id}", flush=True)
        attempt_record = cell["attempts"][-1]
        try:
            result = await _call(function, item["role"], item["model"], item["qd"], item["block_bytes"], attempt_id)
            if not isinstance(result, dict):
                raise RuntimeError(f"{attempt_id} returned {type(result).__name__}")
            result["campaign_index"] = item["campaign_index"]
            result["classification"] = "ELIGIBLE" if result.get("status") == "ok" else "DNF"
            _atomic_write_json(path, result)
            valid, failures = validate_completed_artifact(
                path, item["role"], item["model"], item["qd"], item["block_bytes"], attempt_id
            )
            attempt_record.update({
                "status": "COMPLETE" if valid else "INVALID",
                "finished_at": _now(),
                "error": ";".join(failures) if failures else None,
            })
            cell["status"] = attempt_record["status"]
            _refresh_cell_status(cell, target_rounds)
            results.append(result)
            _save_ledger(state_path, document, ledger)
            print(
                f"[exp04] end={attempt_id} status={result.get('status')} "
                f"SOURCE_WALL_MS={result.get('SOURCE_WALL_MS')} "
                f"effective_GBps={result.get('effective_GBps')} artifact={path}",
                flush=True,
            )
        except Exception as exc:
            failed = {"attempt_id": attempt_id, "campaign_index": item["campaign_index"],
                      "role": item["role"], "model_name": item["model"], "qd": item["qd"],
                      "block_mib": item["block_mib"], "status": "error",
                      "classification": "DNF", "error": f"{type(exc).__name__}:{exc}"}
            _atomic_write_json(path, failed)
            attempt_record.update({"status": "FAILED", "finished_at": _now(), "error": failed["error"]})
            cell["status"] = "FAILED"
            _refresh_cell_status(cell, target_rounds)
            _save_ledger(state_path, document, ledger)
            print(f"[exp04] failed={attempt_id} {failed['error']}", file=sys.stderr, flush=True)
    ledger["status"] = (
        "COMPLETE"
        if all(cell.get("status") == "COMPLETE" for cell in ledger.get("cells", []))
        else "RUNNING"
    )
    _save_ledger(state_path, document, ledger)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", default=_DEFAULT_APP)
    parser.add_argument("--start-round", type=int, default=1)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--role", choices=_ROLES)
    parser.add_argument("--qd", type=int, choices=_QD_VALUES)
    parser.add_argument("--block-mib", type=int, choices=_BLOCK_MIB_VALUES)
    parser.add_argument(
        "--out-dir",
        default=str(_ROOT / "unetClipExperimentsSeptember" / "06_source_block_qd_matrix_pure_source_runs"),
    )
    parser.add_argument("--state", default=str(_STATE_PATH), help="atomic resumable campaign state JSON")
    args = parser.parse_args()
    if args.start_round < 1 or args.rounds < 1:
        parser.error("--start-round and --rounds must be positive")
    try:
        results = asyncio.run(
            _run_campaign(
                args.app,
                Path(args.out_dir),
                args.start_round,
                args.rounds,
                roles=(args.role,) if args.role else _ROLES,
                qd_values=(args.qd,) if args.qd else _QD_VALUES,
                block_mib_values=(args.block_mib,) if args.block_mib else _BLOCK_MIB_VALUES,
                state_path=Path(args.state),
            )
        )
        print(f"[exp04] complete observations={len(results)}", flush=True)
        return 0 if all(item.get("status") == "ok" for item in results) else 2
    except Exception as exc:
        print(f"[exp04] failed={type(exc).__name__}:{exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
