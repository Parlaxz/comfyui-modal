#!/usr/bin/env python
"""Startup-discipline arms: control vs staggered vs primed.

H100 only, 64 MiB x QD4, 5 fresh-container repetitions per arm (15 runs).
One fresh container per run; runs are serial; resume-safe.

Raw measurements only.  No tuning.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_APP = "sept-clip-source-race-oracle"
_REPS = 5
_READ_MIB = 64
_QD = 4
_STAGGER_MS = 250
_ARMS = ("control", "staggered", "primed")
_RUN_TIMEOUT_S = 600


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
    return bool(
        record.get("status") == "ok"
        and (record.get("env") or {}).get("syscall_impl") == "os.preadv"
        and record.get("physical_reads")
        and record.get("covered_bytes") == record.get("useful_bytes")
    )


def main() -> int:
    workspace = _workspace()
    os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])

    import modal

    out_dir = _ROOT / "startup_arm_runs"
    out_dir.mkdir(exist_ok=True)
    fn = modal.Function.from_name(_APP, "run_startup_arm_h100")
    try:
        handle = fn.with_options(timeout=_RUN_TIMEOUT_S)
    except Exception:
        handle = fn

    results: list[dict[str, Any]] = []
    for arm in _ARMS:
        for rep in range(1, _REPS + 1):
            attempt = f"{arm}-rep{rep}"
            path = out_dir / f"{attempt}.json"
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                    if _valid(existing):
                        print(f"[arm] skip {attempt} (valid artifact exists)", flush=True)
                        results.append(existing)
                        continue
                except Exception:
                    pass
            print(f"[arm] start {attempt}", flush=True)
            try:
                result = handle.remote(
                    read_mib=_READ_MIB, qd=_QD, arm=arm,
                    stagger_ms=_STAGGER_MS, attempt_id=attempt,
                )
                if not isinstance(result, dict):
                    raise RuntimeError(f"returned {type(result).__name__}")
            except Exception as exc:
                result = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:400],
                          "attempt_id": attempt}
            path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str),
                            encoding="utf-8")
            results.append(result)
            print(f"[arm] done {attempt} status={result.get('status')} "
                  f"wall_ms={result.get('measured_wall_ms')} "
                  f"gbps={result.get('measured_decimal_gbps')}", flush=True)

    print()
    print("arm | run | region | GB/s | median preadv | max preadv | ge250 | ge500 | ge1000 | bad? | QD ok?")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for result in results:
        if result.get("status") != "ok":
            print(f"{result.get('attempt_id')} | ERROR | {result.get('error')}")
            continue
        th = result.get("thresholds") or {}
        gbps = result.get("measured_decimal_gbps") or 0.0
        bad = gbps < 2.0 or th.get("ge_1000", 0) >= 5
        qd_ok = (result.get("effective_qd_min_in_span") or 0) >= _QD - 1
        print(
            f"| {result['config']['arm']} | {result['attempt_id']} | "
            f"{result.get('provider')}/{result.get('region')} | {gbps:.3f} | "
            f"{result.get('median_ms'):.1f} | {result.get('max_ms'):.0f} | "
            f"{th.get('ge_250')} | {th.get('ge_500')} | {th.get('ge_1000')} | "
            f"{'BAD' if bad else 'ok'} | {qd_ok} |"
        )
    print()
    print("=== per-arm summary ===")
    for arm in _ARMS:
        arm_results = [r for r in results
                       if r.get("status") == "ok" and r["config"]["arm"] == arm]
        if not arm_results:
            print(f"{arm}: no valid runs")
            continue
        gbps = [r["measured_decimal_gbps"] for r in arm_results]
        bad = sum(1 for r in arm_results
                  if (r["measured_decimal_gbps"] or 0) < 2.0
                  or (r.get("thresholds") or {}).get("ge_1000", 0) >= 5)
        runs1000 = sum(1 for r in arm_results
                       if (r.get("thresholds") or {}).get("ge_1000", 0) > 0)
        tot1000 = sum((r.get("thresholds") or {}).get("ge_1000", 0) for r in arm_results)
        worst = max(r["max_ms"] for r in arm_results)
        import statistics
        print(f"{arm}: median {statistics.median(gbps):.3f} GB/s | "
              f"mean {statistics.fmean(gbps):.3f} | min {min(gbps):.3f} | max {max(gbps):.3f} | "
              f"bad {bad}/{len(arm_results)} | runs>=1000 {runs1000} | total>=1000 {tot1000} | "
              f"worst preadv {worst:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
