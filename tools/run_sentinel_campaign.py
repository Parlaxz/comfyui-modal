#!/usr/bin/env python
"""Always-on sentinel campaign (H100, 64 MiB x QD4, no primer).

Stage 1 (--smoke): diagnostics OFF vs ON, verify QD health / refill gaps / throughput.
Stage 2 (default): fresh H100 containers, stop when >=3 large episodes (max read >=500 ms)
                   and >=3 clean runs (max read <250 ms).  Hard cap 25.

Diagnosis only.  No geometry, QD, block-size or priming changes.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_APP = "sept-clip-source-race-oracle"
_READ_MIB = 64
_QD = 4
_SENTINEL_KIB = 256
_SENTINEL_CADENCE_MS = 25
_MAX_RUNS = 25
_NEED_LARGE = 3
_NEED_CLEAN = 3
_LARGE_MS = 500.0
_CLEAN_MS = 250.0
_RUN_TIMEOUT_S = 900
_OUT = _ROOT / "sentinel_runs"


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


def _valid(r: dict[str, Any]) -> bool:
    return bool(
        r.get("status") == "ok"
        and (r.get("env") or {}).get("syscall_impl") == "os.preadv"
        and r.get("physical_reads")
        and r.get("useful_bytes")
    )


def _qd_health(r: dict[str, Any]) -> dict[str, Any]:
    per: dict[int, int] = {}
    for read in r.get("reads") or []:
        per[read["worker"]] = per.get(read["worker"], 0) + 1
    return {"per_worker_reads": per, "balanced": len(set(per.values())) <= 1}


def _connect():
    import modal

    workspace = _workspace()
    os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])
    fn = modal.Function.from_name(_APP, "run_sentinel_h100")
    try:
        return fn.with_options(timeout=_RUN_TIMEOUT_S)
    except Exception:
        return fn


def _invoke(handle, *, diagnostics: bool, attempt: str, settle_ms: int,
            native_canary: bool = True) -> dict[str, Any]:
    path = _OUT / f"{attempt}.json"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if _valid(existing):
                print(f"[sn] skip {attempt}", flush=True)
                return existing
        except Exception:
            pass
    print(f"[sn] start {attempt} diagnostics={diagnostics} settle_ms={settle_ms} "
          f"native_canary={native_canary}", flush=True)
    try:
        result = handle.remote(
            read_mib=_READ_MIB, qd=_QD, diagnostics=diagnostics,
            sentinel_kib=_SENTINEL_KIB, sentinel_cadence_ms=_SENTINEL_CADENCE_MS,
            settle_ms=settle_ms, native_canary=native_canary, attempt_id=attempt,
        )
        if not isinstance(result, dict):
            raise RuntimeError(f"returned {type(result).__name__}")
    except Exception as exc:
        result = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:400],
                  "attempt_id": attempt}
    path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"[sn] done {attempt} status={result.get('status')} "
          f"gbps={result.get('decimal_gbps')} max_ms={result.get('max_ms')} "
          f"hb={result.get('heartbeat_max_gap_ms')} "
          f"Umain={result.get('native_max_gap_ms')} "
          f"Uchild={result.get('u_child_max_gap_ms')} "
          f"Smain_sched={result.get('s_main_max_sched_ms')} "
          f"Smain_lat={result.get('s_main_max_latency_ms')} "
          f"Schild_sched={result.get('s_child_max_sched_ms')} "
          f"Schild_lat={result.get('s_child_max_latency_ms')} "
          f"Bmain_excess={(result.get('b_main_stats') or {}).get('max_excess_ms')} "
          f"Bchild_excess={(result.get('b_child_stats') or {}).get('max_excess_ms')}",
          flush=True)
    return result


_SMOKE_ARMS = [
    ("smoke-off", False, 0),      # baseline: workers start immediately
    ("smoke-offs", False, 150),   # no diagnostics, same 150 ms settle delay as ON
    ("smoke-on", True, 150),      # full diagnostics, settled
    ("smoke-on0", True, 0),       # full diagnostics, workers start immediately
]


def _smoke(handle) -> int:
    """Arm B (native pthread ON) versus arm A (previous topology, native OFF).

    Arm A is the 11 already-captured sentinel campaign runs (native_canary off by
    construction).  Only a few arm-B runs are needed to check perturbation.
    """
    import statistics

    runs: list[dict[str, Any]] = []
    for i in range(1, 4):
        runs.append(_invoke(handle, diagnostics=True, attempt=f"fx-on-{i}",
                            settle_ms=0, native_canary=True))

    arm_a = []
    for p in sorted(_OUT.glob("sn-r*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if _valid(r) and not (r.get("native") or {}).get("mode", "disabled") not in ("disabled",):
            arm_a.append(r)
    arm_a = [r for r in arm_a if (r.get("native") or {}).get("mode") in (None, "disabled")]

    def _row(label: str, arm: list[dict[str, Any]]) -> str:
        if not arm:
            return f"| {label} | 0 | - | - | - | - | - |"
        gbps = statistics.median(r["decimal_gbps"] for r in arm)
        rg = statistics.median(r.get("median_refill_gap_ms") or 0 for r in arm)
        rx = statistics.median(r.get("max_refill_gap_ms") or 0 for r in arm)
        sick = sum(1 for r in arm if float(r.get("max_ms") or 0) >= _LARGE_MS)
        clean = sum(1 for r in arm if float(r.get("max_ms") or 0) < _CLEAN_MS)
        bal = all(_qd_health(r)["balanced"] for r in arm)
        return (f"| {label} | {len(arm)} | {gbps:.2f} | {rg:.3f} | {rx:.1f} | "
                f"{sick} | {clean} | {bal} |")

    print()
    print("=== perturbation validation: arm A (native OFF) vs arm B (native pthread ON) ===")
    print("arm | n | median gbps | median refill | max refill | sick>=500 | clean<250 | QD balanced")
    print(_row("A native OFF", arm_a))
    print(_row("B native ON", runs))

    print()
    for r in runs:
        if not _valid(r):
            print(f"  {r.get('attempt_id')}: INVALID {r.get('error')}")
            continue
        nat = r.get("native") or {}
        print(f"  {r.get('attempt_id')}: mode={nat.get('mode')} "
              f"syscall={nat.get('syscall_name')}({nat.get('syscall_number')}) "
              f"python_pid={nat.get('python_pid')} child_pid={nat.get('child_pid')}")
        print(f"     clock_monotonic={nat.get('clock_monotonic_ns_per_call')} ns/call  "
              f"clock_syscall={nat.get('clock_syscall_ns_per_call')} ns/call")
        for k in ("u_main", "s_main", "u_child", "s_child"):
            v = nat.get(k)
            if v:
                print(f"     {k}: count={v.get('count')} overflow={v.get('overflow')} "
                      f"pid={v.get('pid')} tid={v.get('tid')}")
        print(f"     U_main max_gap={r.get('native_max_gap_ms')} ms | "
              f"U_child max_gap={r.get('u_child_max_gap_ms')} ms | "
              f"S_main sched={r.get('s_main_max_sched_ms')} lat={r.get('s_main_max_latency_ms')} ms | "
              f"S_child sched={r.get('s_child_max_sched_ms')} lat={r.get('s_child_max_latency_ms')} ms")
        print(f"     worker_tids={r.get('worker_tids')}")
    return 0


def _campaign(handle) -> int:
    runs: list[dict[str, Any]] = []
    large = 0
    clean = 0
    # settle_ms=0 preserves the original worker-start timing (the base probe starts
    # workers immediately).  All diagnostics are still created/opened/allocated and
    # their threads started BEFORE the worker threads.  The smoke showed a 150 ms
    # settle suppresses episodes (0/3 large) versus 2/3 large at settle 0.
    for i in range(1, _MAX_RUNS + 1):
        attempt = f"fx-{i:02d}"
        result = _invoke(handle, diagnostics=True, attempt=attempt, settle_ms=0)
        runs.append(result)
        if _valid(result):
            mx = float(result.get("max_ms") or 0)
            if mx >= _LARGE_MS:
                large += 1
            elif mx < _CLEAN_MS:
                clean += 1
            print(f"[sn] running totals: large={large} clean={clean}", flush=True)
        if large >= _NEED_LARGE and clean >= _NEED_CLEAN:
            print("[sn] capture goal met; stopping", flush=True)
            break

    ok = [r for r in runs if _valid(r)]
    print()
    print("=== per-run summary ===")
    print("run | region | worst src ms | src gbps | main hb gap | canary gap | "
          "canary mode | A sched/lat | B sched/lat | C sched/lat | sent samples")
    for r in ok:
        sent = r.get("sentinels") or {}

        def _fmt(name: str) -> str:
            s = sent.get(name)
            if not s:
                return "-"
            return f"{s['max_scheduling_delay_ms']:.1f}/{s['max_syscall_latency_ms']:.1f}"

        print(f"| {r.get('attempt_id')} | {r.get('provider')}/{r.get('region')} | "
              f"{r['max_ms']:.0f} | {r['decimal_gbps']:.2f} | "
              f"{(r.get('heartbeat_max_gap_ms') or 0):.0f} | "
              f"{(r.get('canary_max_gap_ms') or 0):.0f} | "
              f"{(r.get('canary') or {}).get('mode')} | "
              f"{_fmt('A_same_file')} | {_fmt('B_other_volume_file')} | {_fmt('C_tmpfs_local')} | "
              f"{sum(v.get('samples', 0) for v in sent.values())} |")
    print()
    print(f"large episodes={large}  clean runs={clean}  total runs={len(runs)}")
    return 0


def main() -> int:
    handle = _connect()
    _OUT.mkdir(exist_ok=True)
    if "--smoke" in sys.argv:
        return _smoke(handle)
    return _campaign(handle)


if __name__ == "__main__":
    sys.exit(main())
