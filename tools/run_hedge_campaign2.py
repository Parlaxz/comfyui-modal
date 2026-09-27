#!/usr/bin/env python
"""Corrected delayed-hedge campaign: 20 fresh H100 runs.

Consumes hedge_runs2/schedule2.json (H75 x10, H150 x5, H250 x5, 5 blocks).
Per-worker independent hedge resource pools; a hedge for worker w can never be
suppressed by another worker's hedge.

Validity gate: status ok, H100, logical reads > 0, AND
hedge.suppressed_resource_busy == 0 (per task spec).
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
_OUT = _ROOT / "hedge_runs2"
_SCHED = _OUT / "schedule2.json"
_READ_MIB = 64
_QD = 4
_PACER_MS = 4.0
_HEDGE_SLOTS = 3
_RUN_TIMEOUT_S = 1200
_MAX_SLOT_TRIES = 3

ARM_DELAY = {"H75": 75.0, "H150": 150.0, "H250": 250.0}


def _workspace() -> dict[str, Any]:
    import tomllib

    t = tomllib.loads((_ROOT / "config" / "v2" / "modal_target.toml").read_text("utf-8"))
    wanted = str((t.get("modal") or {}).get("workspace_id") or "").strip()
    for reg in (_ROOT / ".git" / "comfymodal" / "modal_workspaces.json",
                _ROOT / ".modal_workspaces.json"):
        if not reg.is_file():
            continue
        d = json.loads(reg.read_text("utf-8"))
        ws = next((w for w in d.get("workspaces", []) if str(w.get("id") or "") == wanted), None)
        if ws and ws.get("token_id") and ws.get("token_secret"):
            return ws
    raise RuntimeError(f"no credentials for workspace {wanted}")


def _valid(r: dict[str, Any]) -> tuple[bool, str]:
    if r.get("status") != "ok":
        return False, "status_not_ok"
    if "H100" not in str((r.get("identity") or {}).get("observed_gpu") or ""):
        return False, "wrong_gpu"
    if (r.get("logical_reads") or 0) <= 0:
        return False, "no_logical_reads"
    if (r.get("physical_attempts") or 0) <= 0:
        return False, "no_physical_attempts"
    if (r.get("hedge") or {}).get("suppressed_resource_busy", 0) != 0:
        return False, "hedge_suppressed_resource_busy_nonzero"
    return True, ""


def _invoke(handle, entry: dict[str, Any], try_no: int) -> dict[str, Any]:
    arm = entry["arm"]
    suffix = "" if try_no == 1 else f"-rtry{try_no}"
    attempt = f"h2-{arm}-{entry['ordinal']:03d}{suffix}"
    path = _OUT / f"{attempt}.json"
    if path.exists():
        try:
            e = json.loads(path.read_text(encoding="utf-8"))
            if _valid(e)[0]:
                print(f"[h2] skip {attempt}", flush=True)
                return e
        except Exception:
            pass
    delay = ARM_DELAY[arm]
    print(f"[h2] start {attempt} block={entry['block']} pos={entry['position']} "
          f"arm={arm} hedge_ms={delay} slots/worker={_HEDGE_SLOTS}", flush=True)
    try:
        r = handle.remote(read_mib=_READ_MIB, qd=_QD, min_launch_gap_ms=_PACER_MS,
                          hedge_delay_ms=delay, hedge_slots_per_worker=_HEDGE_SLOTS,
                          attempt_id=attempt)
        if not isinstance(r, dict):
            raise RuntimeError(f"returned {type(r).__name__}")
    except Exception as exc:
        r = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:400],
             "attempt_id": attempt}
    r["_schedule"] = {"ordinal": entry["ordinal"], "block": entry["block"],
                      "position": entry["position"], "arm": arm, "try": try_no}
    path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str), encoding="utf-8")
    lg = r.get("logical_ms") or []
    hg = r.get("hedge") or {}
    print(f"[h2] done {attempt} gpu={((r.get('identity') or {}).get('observed_gpu'))} "
          f"region={r.get('region')} wall={r.get('full_file_wall_ms')} "
          f"logMed={statistics.median(lg) if lg else None} "
          f"logMax={r.get('logical_max_ms')} "
          f"l500={(r.get('logical_thresholds') or {}).get('ge_500')} "
          f"l1k={(r.get('logical_thresholds') or {}).get('ge_1000')} "
          f"launched={hg.get('launched')} wins={hg.get('rescue_wins')} "
          f"SUPPRESSED={hg.get('suppressed_resource_busy')} "
          f"amp={hg.get('amplification')}", flush=True)
    return r


def main() -> int:
    sched = json.loads(_SCHED.read_text(encoding="utf-8"))
    runs = sched["runs"]
    print(f"[h2] schedule seed={sched['seed']} runs={len(runs)}")

    os.environ["MODAL_TOKEN_ID"] = str(_workspace()["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(_workspace()["token_secret"])
    import modal

    _OUT.mkdir(exist_ok=True)
    fn = modal.Function.from_name(_APP, "run_hedge_h100")
    try:
        handle = fn.with_options(timeout=_RUN_TIMEOUT_S)
    except Exception:
        handle = fn

    ok, rejected = [], []
    for entry in runs:
        got = None
        for t in range(1, _MAX_SLOT_TRIES + 1):
            r = _invoke(handle, entry, t)
            good, why = _valid(r)
            if good:
                got = r
                break
            rejected.append({"slot": entry, "try": t, "reason": why,
                             "error": r.get("error"),
                             "gpu": (r.get("identity") or {}).get("observed_gpu")})
            print(f"[h2] REJECTED slot {entry['ordinal']} try {t}: {why}", flush=True)
        if got is None:
            print(f"[h2] SLOT FAILED PERMANENTLY {entry['ordinal']}", flush=True)
        else:
            ok.append(got)

    print(f"\n[h2] valid runs: {len(ok)} / {len(runs)}")
    if rejected:
        print(f"[h2] rejected attempts: {len(rejected)}")
        for r in rejected:
            print(f"     slot {r['slot']['ordinal']} try {r['try']}: {r['reason']}")

    supp = sum((r.get("hedge") or {}).get("suppressed_resource_busy", 0) for r in ok)
    launch = sum((r.get("hedge") or {}).get("launched", 0) for r in ok)
    elig = sum((r.get("hedge") or {}).get("eligible", 0) for r in ok)
    wins = sum((r.get("hedge") or {}).get("rescue_wins", 0) for r in ok)
    print(f"\n[h2] VALIDITY: hedge_suppressed_resource_busy total = {supp} "
          f"({'PASS' if supp == 0 else 'FAIL'})")
    print(f"[h2] hedge eligible={elig} launched={launch} wins={wins}")

    print("\n=== per-run (schedule order) ===")
    print(f"{'ord':>4}{'blk':>4}{'pos':>4}{'arm':>6}{'wall':>8}{'logMed':>8}{'logMean':>9}"
          f"{'logMax':>8}{'>500':>5}{'>1k':>4}{'elig':>5}{'launch':>7}{'wins':>5}"
          f"{'supp':>5}{'amp':>7}{'gapmin':>8}{'mx':>4}")
    for r in sorted(ok, key=lambda x: x["_schedule"]["ordinal"]):
        sc = r["_schedule"]
        lg = r.get("logical_ms") or []
        lt = r.get("logical_thresholds") or {}
        hg = r.get("hedge") or {}
        f = lambda v, n=2: "-" if v is None else format(v, f".{n}f")
        print(f"{sc['ordinal']:>4}{sc['block']:>4}{sc['position']:>4}{sc['arm']:>6}"
              f"{f(r.get('full_file_wall_ms'),0):>8}"
              f"{f(statistics.median(lg) if lg else None,1):>8}"
              f"{f(statistics.fmean(lg) if lg else None,1):>9}"
              f"{f(r.get('logical_max_ms'),0):>8}"
              f"{lt.get('ge_500',0):>5}{lt.get('ge_1000',0):>4}"
              f"{hg.get('eligible',0):>5}{hg.get('launched',0):>7}"
              f"{hg.get('rescue_wins',0):>5}{hg.get('suppressed_resource_busy',0):>5}"
              f"{f(hg.get('amplification'),4):>7}"
              f"{f(r.get('min_attempt_gap_ms')):>8}"
              f"{r.get('max_simultaneous_in_flight') if r.get('max_simultaneous_in_flight') is not None else '-':>4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
