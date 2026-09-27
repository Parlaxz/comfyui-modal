#!/usr/bin/env python
"""Full-file geometry replication: 4 additional fresh-container runs per cell.

One fresh container per run.  H100 and RTX families run in parallel; runs
within a family are serial.  Existing artifacts are never overwritten, so this
is resume-safe.  Pathological runs are recorded as data, not retried.

Raw measurements only.  No tuning.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_APP = "sept-clip-source-race-oracle"
_REPS = 4
_RUN_TIMEOUT_S = 600

_COMMON = ((32, 2), (32, 4), (32, 8), (64, 2), (64, 4), (64, 8), (128, 2), (128, 4), (128, 8))
_GEOMETRIES = {
    "h100": _COMMON,
    "rtx": _COMMON + ((256, 2), (256, 4), (256, 8)),
}


def _workspace() -> dict[str, Any]:
    import tomllib

    target = tomllib.loads((_ROOT / "config" / "v2" / "modal_target.toml").read_text("utf-8"))
    wanted = str((target.get("modal") or {}).get("workspace_id") or "").strip()
    for registry in (
        _ROOT / ".git" / "comfymodal" / "modal_workspaces.json",
        _ROOT / ".modal_workspaces.json",
    ):
        if not registry.is_file():
            continue
        data = json.loads(registry.read_text("utf-8"))
        workspace = next(
            (w for w in data.get("workspaces", []) if str(w.get("id") or "") == wanted), None
        )
        if workspace and workspace.get("token_id") and workspace.get("token_secret"):
            return workspace
    raise RuntimeError(f"no credentials for destination workspace {wanted}")


def _valid(record: dict[str, Any]) -> bool:
    coverage = record.get("coverage") or {}
    return bool(
        record.get("status") == "ok"
        and coverage.get("covers_entire_file_exactly_once")
        and (record.get("covered_bytes") == (record.get("file_identity") or {}).get("size"))
        and (record.get("env") or {}).get("syscall_impl") == "os.preadv"
    )


def _run_family(family: str, out_dir: Path) -> list[dict[str, Any]]:
    import modal

    fn = modal.Function.from_name(_APP, f"run_fullfile_{family}")
    try:
        handle = fn.with_options(timeout=_RUN_TIMEOUT_S)
    except Exception:
        handle = fn
    produced: list[dict[str, Any]] = []
    for read_mib, qd in _GEOMETRIES[family]:
        for rep in range(1, _REPS + 1):
            attempt = f"{family}-r{read_mib}-qd{qd}-rep{rep}"
            path = out_dir / f"{attempt}.json"
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                    if _valid(existing):
                        print(f"[rep] skip {attempt} (valid artifact exists)", flush=True)
                        produced.append(existing)
                        continue
                except Exception:
                    pass
            print(f"[rep] start {attempt}", flush=True)
            try:
                result = handle.remote(read_mib=read_mib, qd=qd, attempt_id=attempt)
                if not isinstance(result, dict):
                    raise RuntimeError(f"returned {type(result).__name__}")
            except Exception as exc:
                result = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:400],
                          "attempt_id": attempt}
            path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str),
                            encoding="utf-8")
            produced.append(result)
            print(f"[rep] done {attempt} status={result.get('status')} "
                  f"wall_ms={result.get('full_file_wall_ms')} "
                  f"gbps={result.get('full_file_decimal_gbps')}", flush=True)
    return produced


def main() -> int:
    workspace = _workspace()
    os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])

    out_dir = _ROOT / "source_fullfile_runs"
    out_dir.mkdir(exist_ok=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_run_family, family, out_dir): family
                   for family in ("h100", "rtx")}
        for future in concurrent.futures.as_completed(futures):
            family = futures[future]
            try:
                done = future.result()
                print(f"[rep] family {family} finished ({len(done)} records)", flush=True)
            except Exception:
                print(f"[rep] family {family} failed:\n{traceback.format_exc()}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
