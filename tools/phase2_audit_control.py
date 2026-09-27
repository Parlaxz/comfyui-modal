#!/usr/bin/env python
"""Serial Phase-2 audit runner; planning and reporting are local-only."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comfymodal_runtime.phase2_audit_control import (  # noqa: E402
    CONTROL_APP_NAME,
    SOURCE_CAPACITY,
    build_plan,
    build_schedule,
    build_source_only_matrix_plan,
    build_source_only_matrix_schedule,
    ingest_artifact,
    summarize_artifacts,
)

CONTROL_MODE = "control"
SOURCE_ONLY_MATRIX_MODE = "source-only-matrix"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_active_workspace(repo_root: Path | None = None) -> dict[str, Any]:
    """Load only the registry's active workspace, without exposing tokens."""
    repo_root = ROOT if repo_root is None else repo_root
    workspace_file = repo_root / ".modal_workspaces.json"
    data = json.loads(workspace_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Modal workspace registry is not an object")
    active_id = data.get("active_workspace_id")
    workspaces = data.get("workspaces")
    if not active_id or not isinstance(workspaces, list):
        raise RuntimeError("Modal workspace registry has no active workspace")
    workspace = next(
        (
            item for item in workspaces
            if isinstance(item, dict) and item.get("id") == active_id
        ),
        None,
    )
    if not workspace or not workspace.get("token_id") or not workspace.get("token_secret"):
        raise RuntimeError("active Modal workspace is missing or has no credentials")
    return workspace


def _mode(args: argparse.Namespace) -> str:
    mode = getattr(args, "mode", CONTROL_MODE)
    if mode not in {CONTROL_MODE, SOURCE_ONLY_MATRIX_MODE}:
        raise ValueError(f"unsupported Phase-2 audit mode: {mode}")
    return mode


def _paths(args: argparse.Namespace, mode: str) -> tuple[Path, Path]:
    default_dir = (
        "phase2_source_only_matrix_runs"
        if mode == SOURCE_ONLY_MATRIX_MODE
        else "phase2_audit_runs"
    )
    out_dir = Path(getattr(args, "out_dir", None) or default_dir)
    state = Path(getattr(args, "state", None) or (out_dir / "ledger.json"))
    return out_dir, state


def _schedule(mode: str) -> list[dict[str, Any]]:
    if mode == SOURCE_ONLY_MATRIX_MODE:
        return build_source_only_matrix_schedule()
    return build_schedule()


def _plan(mode: str) -> dict[str, Any]:
    if mode == SOURCE_ONLY_MATRIX_MODE:
        return build_source_only_matrix_plan()
    return build_plan()


def _reject_existing_matrix_outputs(
    schedule: list[dict[str, Any]], out_dir: Path, state_path: Path,
) -> None:
    """Prevent a matrix rerun from turning old artifacts into fresh samples."""
    if state_path.exists():
        raise RuntimeError(
            f"source-only matrix state already exists; choose a new state path: {state_path}"
        )
    existing = [
        out_dir / f"{item['attempt_id']}.json"
        for item in schedule
        if (out_dir / f"{item['attempt_id']}.json").exists()
    ]
    if existing:
        raise RuntimeError(
            "source-only matrix output already exists; choose a new output path: "
            + str(existing[0])
        )


def _execute_remote(args: argparse.Namespace) -> int:
    """The only branch that imports Modal; the parent operator owns it."""
    import modal

    workspace = _load_active_workspace()
    # Bind both the SDK client and the process credentials to the same
    # registry-selected workspace.  The secrets are never logged or placed in
    # the ledger/artifacts.
    os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])
    client = modal.Client.from_credentials(
        workspace["token_id"], workspace["token_secret"]
    )
    environment = str(workspace.get("environment") or "").strip()

    mode = _mode(args)
    out_dir, state_path = _paths(args, mode)
    out_dir.mkdir(parents=True, exist_ok=True)
    schedule = _schedule(mode)
    if mode == SOURCE_ONLY_MATRIX_MODE:
        _reject_existing_matrix_outputs(schedule, out_dir, state_path)
    ledger = {
        "version": 1,
        "campaign": (
            "phase2_source_only_matrix"
            if mode == SOURCE_ONLY_MATRIX_MODE
            else "phase2_source_h2d_control"
        ),
        "app": args.app,
        "phase_3_status": "stopped",
        "serial": True,
        "schedule": schedule,
        "attempts": [],
        "started_at": _now(),
    }
    if mode == SOURCE_ONLY_MATRIX_MODE:
        ledger["mode"] = mode
        ledger["request_count"] = len(schedule)
        ledger["fresh_serial_requests"] = True
    _write(state_path, ledger)
    function = modal.Function.from_name(
        args.app,
        "run_phase2_audit",
        client=client,
        environment_name=environment or None,
    )
    for item in schedule:
        artifact_path = out_dir / f"{item['attempt_id']}.json"
        expected = {
            "attempt_id": item["attempt_id"], "role": item["role"],
            "model_name": item["model_name"], "arm": item["arm"],
            "qd": item["qd"], "block_bytes": item["block_bytes"],
            "source_qd": item["source_qd"], "source_capacity": SOURCE_CAPACITY,
        }
        # Never discover a substitute artifact.  A pre-existing exact path is
        # ingested and retained; otherwise this request gets one fresh call.
        if artifact_path.exists() and mode == CONTROL_MODE:
            ingested = ingest_artifact(artifact_path, expected)
            if ingested["valid"]:
                ledger["attempts"].append({"attempt_id": item["attempt_id"], "path": str(artifact_path), "classification": "ELIGIBLE", "reused": True})
                _write(state_path, ledger)
                continue
        started = _now()
        try:
            result = function.remote(
                item["role"], item["model_name"], item["arm"], item["qd"], item["block_bytes"], item["attempt_id"]
            )
            if not isinstance(result, dict):
                raise RuntimeError(f"remote returned {type(result).__name__}")
        except Exception as exc:
            result = {**expected, "status": "error", "classification": "FAILED", "error": f"{type(exc).__name__}:{exc}"}
        _write(artifact_path, result)
        ingested = ingest_artifact(artifact_path, expected)
        ledger["attempts"].append({
            "attempt_id": item["attempt_id"], "path": str(artifact_path),
            "classification": ingested["classification"], "failures": ingested["failures"],
            "started_at": started, "finished_at": _now(),
        })
        _write(state_path, ledger)
    ledger["finished_at"] = _now()
    ledger["status"] = "COMPLETE"
    _write(state_path, ledger)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--report", nargs="*", metavar="ARTIFACT")
    parser.add_argument("--execute-remote", action="store_true")
    parser.add_argument(
        "--mode",
        choices=(CONTROL_MODE, SOURCE_ONLY_MATRIX_MODE),
        default=CONTROL_MODE,
        help="control keeps the 24-request causal schedule; source-only-matrix runs 96 fresh requests",
    )
    parser.add_argument("--app", default=CONTROL_APP_NAME)
    parser.add_argument("--out-dir", help="artifact directory (mode-specific deterministic default)")
    parser.add_argument("--state", help="ledger path (defaults inside --out-dir)")
    parser.add_argument("--output", type=Path, help="write the deterministic plan JSON")
    args = parser.parse_args(argv)
    if args.execute_remote:
        return _execute_remote(args)
    if args.report:
        print(json.dumps(summarize_artifacts(args.report), indent=2, sort_keys=True))
    else:
        plan = _plan(args.mode)
        if args.output is not None:
            _write(args.output, plan)
        print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
