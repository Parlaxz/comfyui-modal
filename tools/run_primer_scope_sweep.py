#!/usr/bin/env python
"""Primer-scope arms: no primer vs ONE global primer vs one primer per worker.

H100 only, 64 MiB x QD4, 5 fresh-container repetitions per arm (15 runs).
One fresh container per run; runs serial; resume-safe.

Raw measurements only.  No tuning.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_APP = "sept-clip-source-race-oracle"
_REPS = 5
_READ_MIB = 64
_QD = 4
_ARMS = ("control", "global_primed", "primed")
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

    out_dir = _ROOT / "primer_scope_runs"
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
                        print(f"[primer] skip {attempt} (valid artifact exists)", flush=True)
                        results.append(existing)
                        continue
                except Exception:
                    pass
            print(f"[primer] start {attempt}", flush=True)
            try:
                result = handle.remote(
                    read_mib=_READ_MIB, qd=_QD, arm=arm,
                    stagger_ms=0, attempt_id=attempt,
                )
                if not isinstance(result, dict):
                    raise RuntimeError(f"returned {type(result).__name__}")
            except Exception as exc:
                result = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:400],
                          "attempt_id": attempt}
            path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str),
                            encoding="utf-8")
            results.append(result)
            print(f"[primer] done {attempt} status={result.get('status')} "
                  f"gbps={result.get('measured_decimal_gbps')}", flush=True)

    print()
    print("arm | run | region | primer config | primer ms | GB/s | median | max | ge250 | ge500 | ge1000 | bad? | QD ok?")
    for r in results:
        if r.get("status") != "ok":
            print(f"{r.get('attempt_id')} | ERROR | {r.get('error')}")
            continue
        th = r.get("thresholds") or {}
        cfg = r.get("config") or {}
        pr = r.get("primer_results") or {}
        primer_ms = [round(pr[k]["preadv_ms"], 1) for k in sorted(pr, key=int)]
        g = r.get("measured_decimal_gbps") or 0.0
        bad = g < 2.0 or th.get("ge_1000", 0) >= 5
        qd_ok = (r.get("effective_qd_min_in_span") or 0) >= _QD - 1
        print(f"| {cfg.get('arm')} | {r.get('attempt_id')} | {r.get('provider')}/{r.get('region')} | "
              f"n={len(pr)} | {primer_ms} | {g:.3f} | {r.get('median_ms'):.1f} | "
              f"{r.get('max_ms'):.0f} | {th.get('ge_250')} | {th.get('ge_500')} | {th.get('ge_1000')} | "
              f"{'BAD' if bad else 'ok'} | {qd_ok} |")

    print()
    print("=== per-arm summary ===")
    for arm in _ARMS:
        rs = [r for r in results if r.get("status") == "ok" and r["config"]["arm"] == arm]
        if not rs:
            print(f"{arm}: no valid runs")
            continue
        g = [r["measured_decimal_gbps"] for r in rs]
        bad = sum(1 for r in rs if (r["measured_decimal_gbps"] or 0) < 2.0
                  or (r.get("thresholds") or {}).get("ge_1000", 0) >= 5)
        r1000 = sum(1 for r in rs if (r.get("thresholds") or {}).get("ge_1000", 0) > 0)
        t1000 = sum((r.get("thresholds") or {}).get("ge_1000", 0) for r in rs)
        t500 = sum((r.get("thresholds") or {}).get("ge_500", 0) for r in rs)
        t250 = sum((r.get("thresholds") or {}).get("ge_250", 0) for r in rs)
        worst = max(r["max_ms"] for r in rs)
        g0 = [x for r in rs for x in r["reads"] if x["gen"] == 0]
        g0sick = sum(1 for x in g0 if x["preadv_ms"] >= 1000)
        primer_ms = [pr["preadv_ms"] for r in rs for pr in (r.get("primer_results") or {}).values()]
        print(f"{arm}: median {statistics.median(g):.3f} mean {statistics.fmean(g):.3f} "
              f"min {min(g):.3f} max {max(g):.3f} | bad {bad}/{len(rs)} | runs>=1000 {r1000} | "
              f"tot>=1000 {t1000} | tot>=500 {t500} | tot>=250 {t250} | worst {worst:.0f} ms | "
              f"gen0>=1000 {g0sick}/{len(g0)} | "
              f"primer n={len(primer_ms)} ms={[round(x,1) for x in primer_ms]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
