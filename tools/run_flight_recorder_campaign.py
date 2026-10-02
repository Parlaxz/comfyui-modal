#!/usr/bin/env python
"""Flight-recorder capture campaign (H100, 64 MiB x QD4, no primer).

Stage 1: tiny overhead validation (recorder OFF vs ON).
Stage 2: up to 20 fresh containers, stop when >=3 pathological and >=3 clean
         runs have been captured.

Raw measurements only.  No tuning, no geometry changes.
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
_READ_MIB = 64
_QD = 4
_SAMPLE_MS = 15
_MAX_RUNS = 20
_NEED_SICK = 3
_NEED_CLEAN = 3
_RUN_TIMEOUT_S = 900


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
        and record.get("useful_bytes")
    )


def _run(handle, attempt: str, sample_ms: int, out_dir: Path) -> dict[str, Any]:
    path = out_dir / f"{attempt}.json"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if _valid(existing):
                print(f"[fr] skip {attempt}", flush=True)
                return existing
        except Exception:
            pass
    print(f"[fr] start {attempt} sample_ms={sample_ms}", flush=True)
    try:
        result = handle.remote(read_mib=_READ_MIB, qd=_QD, sample_ms=sample_ms,
                               attempt_id=attempt)
        if not isinstance(result, dict):
            raise RuntimeError(f"returned {type(result).__name__}")
    except Exception as exc:
        result = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:400],
                  "attempt_id": attempt}
    path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str),
                    encoding="utf-8")
    print(f"[fr] done {attempt} status={result.get('status')} "
          f"gbps={result.get('decimal_gbps')} max_ms={result.get('max_ms')} "
          f"samples={result.get('sample_count')} snapshots={result.get('snapshot_count')}",
          flush=True)
    return result


def main() -> int:
    workspace = _workspace()
    os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])

    import modal

    out_dir = _ROOT / "flight_recorder_runs"
    out_dir.mkdir(exist_ok=True)
    fn = modal.Function.from_name(_APP, "run_flight_recorder_h100")
    try:
        handle = fn.with_options(timeout=_RUN_TIMEOUT_S)
    except Exception:
        handle = fn

    # ---- Stage 1: overhead validation ----
    print("=== stage 1: recorder OFF vs ON ===", flush=True)
    validation = []
    for i in (1, 2):
        validation.append(_run(handle, f"off-r{i:02d}", 0, out_dir))
    for i in (1, 2):
        validation.append(_run(handle, f"on-r{i:02d}", _SAMPLE_MS, out_dir))
    off = [r for r in validation if r.get("status") == "ok" and r.get("config", {}).get("sample_ms") == 0]
    on = [r for r in validation if r.get("status") == "ok" and (r.get("config", {}).get("sample_ms") or 0) > 0]
    if off and on:
        print(f"  OFF median gbps={statistics.median([r['decimal_gbps'] for r in off]):.3f} "
              f"max_ms={max(r['max_ms'] for r in off):.0f} "
              f"refill={statistics.median([r['median_refill_gap_ms'] for r in off]):.3f}")
        print(f"  ON  median gbps={statistics.median([r['decimal_gbps'] for r in on]):.3f} "
              f"max_ms={max(r['max_ms'] for r in on):.0f} "
              f"refill={statistics.median([r['median_refill_gap_ms'] for r in on]):.3f}")

    # ---- Stage 2: campaign ----
    print("\n=== stage 2: capture campaign ===", flush=True)
    runs = []
    sick = 0
    clean = 0
    for i in range(1, _MAX_RUNS + 1):
        r = _run(handle, f"cap-r{i:02d}", _SAMPLE_MS, out_dir)
        if r.get("status") != "ok":
            continue
        runs.append(r)
        if (r.get("thresholds") or {}).get("ge_1000", 0) > 0:
            sick += 1
        else:
            clean += 1
        print(f"[fr] progress sick={sick} clean={clean} runs={len(runs)}", flush=True)
        if sick >= _NEED_SICK and clean >= _NEED_CLEAN:
            print("[fr] capture goal met; stopping", flush=True)
            break

    print("\n=== per-run capture table ===")
    print("run | region | healthy/sick | worst preadv | affected workers | states | wchan sig | "
          "IO PSI | CPU PSI | cgroup IO | samples | snapshots")
    for r in runs:
        th = r.get("thresholds") or {}
        worst = r.get("max_ms") or 0
        sick_run = th.get("ge_1000", 0) > 0
        affected = sorted({rd["worker"] for rd in r.get("reads", []) if rd["preadv_ms"] >= 250})
        states = sorted({(w.get("state") or "?") for w in (r.get("samples") or [{}])[-1].get("workers", {}).values()})
        wchans = sorted({(w.get("wchan") or "?") for w in (r.get("samples") or [{}])[-1].get("workers", {}).values()})
        last = (r.get("samples") or [{}])[-1]
        print(f"| {r.get('attempt_id')} | {r.get('provider')}/{r.get('region')} | "
              f"{'SICK' if sick_run else 'clean'} | {worst:.0f} | {affected} | {states} | {wchans} | "
              f"{(last.get('psi_io') or '').splitlines()[:1]} | "
              f"{(last.get('psi_cpu') or '').splitlines()[:1]} | "
              f"{len((last.get('cgroup_io_stat') or '').splitlines())} lines | "
              f"{r.get('sample_count')} | {r.get('snapshot_count')} |")

    print("\n=== pathological episodes and threshold snapshots ===")
    for r in runs:
        if (r.get("thresholds") or {}).get("ge_1000", 0) == 0:
            continue
        print(f"\n{r.get('attempt_id')} ({r.get('provider')}/{r.get('region')}) "
              f"worst={r.get('max_ms'):.0f} ms gbps={r.get('decimal_gbps'):.3f}")
        for s in r.get("snapshots") or []:
            if s.get("kind") != "threshold":
                continue
            states = {k: v.get("state") for k, v in (s.get("workers") or {}).items()}
            wchans = {k: v.get("wchan") for k, v in (s.get("workers") or {}).items()}
            print(f"  t={s['threshold_ms']} ms worker={s['worker']} elapsed={s['elapsed_ms']:.0f} ms "
                  f"states={states}")
            print(f"    wchan={wchans}")
            print(f"    psi_io={(s.get('shared') or {}).get('psi_io','').splitlines()[:1]}")
            print(f"    cgroup_io_pressure={(s.get('shared') or {}).get('cgroup_io_pressure','').splitlines()[:1]}")
            st = s.get("stacks") or {}
            if st:
                print(f"    stacks_present={sorted(st)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
