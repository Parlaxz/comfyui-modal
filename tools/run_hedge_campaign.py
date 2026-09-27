#!/usr/bin/env python
"""Delayed-hedge campaign: QD4 @ 4.0 ms pacing, 4 arms x 25 fresh H100 runs.

Consumes the pre-generated balanced randomized schedule (hedge_runs/schedule.json).
Does NOT regenerate the schedule.  Invalid / wrong-GPU runs are retried in the
SAME logical slot and the invalid attempt is retained separately.
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
_OUT = _ROOT / "hedge_runs"
_SCHED = _OUT / "schedule.json"
_READ_MIB = 64
_QD = 4
_PACER_MS = 4.0
_RUN_TIMEOUT_S = 1200
_MAX_SLOT_TRIES = 4

ARM_DELAY = {"C": 0.0, "H75": 75.0, "H125": 125.0, "H200": 200.0}


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


def _valid(r: dict[str, Any]) -> bool:
    return bool(
        r.get("status") == "ok"
        and "H100" in str((r.get("identity") or {}).get("observed_gpu") or "")
        and (r.get("logical_reads") or 0) > 0
        and (r.get("physical_attempts") or 0) > 0
    )


def _invoke(handle, entry: dict[str, Any], try_no: int) -> dict[str, Any]:
    arm = entry["arm"]
    suffix = "" if try_no == 1 else f"-rtry{try_no}"
    attempt = f"hx-{arm}-{entry['ordinal']:03d}{suffix}"
    path = _OUT / f"{attempt}.json"
    if path.exists():
        try:
            e = json.loads(path.read_text(encoding="utf-8"))
            if _valid(e):
                print(f"[hx] skip {attempt}", flush=True)
                return e
        except Exception:
            pass
    # the CONTROL arm keeps the same code path with hedge delay forced to 0
    delay = ARM_DELAY[arm]
    print(f"[hx] start {attempt} round={entry['round']} pos={entry['position']} "
          f"arm={arm} hedge_ms={delay}", flush=True)
    try:
        r = handle.remote(read_mib=_READ_MIB, qd=_QD, min_launch_gap_ms=_PACER_MS,
                          hedge_delay_ms=delay, attempt_id=attempt)
        if not isinstance(r, dict):
            raise RuntimeError(f"returned {type(r).__name__}")
    except Exception as exc:
        r = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:400],
             "attempt_id": attempt}
    r["_schedule"] = {"ordinal": entry["ordinal"], "round": entry["round"],
                      "position": entry["position"], "arm": arm, "try": try_no}
    path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str), encoding="utf-8")
    lg = r.get("logical_ms") or []
    hg = r.get("hedge") or {}
    print(f"[hx] done {attempt} gpu={((r.get('identity') or {}).get('observed_gpu'))} "
          f"region={r.get('region')} wall={r.get('full_file_wall_ms')} "
          f"logical_med={statistics.median(lg) if lg else None} "
          f"logical_max={r.get('logical_max_ms')} "
          f"log500={(r.get('logical_thresholds') or {}).get('ge_500')} "
          f"log1k={(r.get('logical_thresholds') or {}).get('ge_1000')} "
          f"hedges={hg.get('launched')} wins={hg.get('rescue_wins')} "
          f"amp={hg.get('amplification')}", flush=True)
    return r


def main() -> int:
    sched = json.loads(_SCHED.read_text(encoding="utf-8"))
    runs = sched["runs"]
    print(f"[hx] schedule seed={sched['seed']} runs={len(runs)}")

    os.environ["MODAL_TOKEN_ID"] = str(_workspace()["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(_workspace()["token_secret"])
    import modal

    _OUT.mkdir(exist_ok=True)
    fn = modal.Function.from_name(_APP, "run_hedge_h100")
    try:
        handle = fn.with_options(timeout=_RUN_TIMEOUT_S)
    except Exception:
        handle = fn

    ok, invalid = [], []
    for entry in runs:
        got = None
        for t in range(1, _MAX_SLOT_TRIES + 1):
            r = _invoke(handle, entry, t)
            if _valid(r):
                got = r
                break
            invalid.append({"slot": entry, "try": t, "status": r.get("status"),
                            "error": r.get("error"),
                            "gpu": (r.get("identity") or {}).get("observed_gpu")})
            print(f"[hx] INVALID slot {entry['ordinal']} try {t}: "
                  f"{r.get('error') or r.get('status')}", flush=True)
        if got is None:
            print(f"[hx] SLOT FAILED PERMANENTLY {entry['ordinal']}", flush=True)
        else:
            ok.append(got)

    print(f"\n[hx] valid H100 runs: {len(ok)} / {len(runs)}")
    if invalid:
        print(f"[hx] invalid attempts retained: {len(invalid)}")
    regions: dict[str, int] = {}
    for r in ok:
        k = r.get("region") or "?"
        regions[k] = regions.get(k, 0) + 1
    print(f"[hx] regions: {regions}")

    print("\n=== per-run (by schedule ordinal) ===")
    print(f"{'ord':>4}{'rnd':>4}{'pos':>4}{'arm':>6}{'wall':>8}{'logMed':>8}{'logMean':>9}"
          f"{'logMax':>8}{'>250':>5}{'>500':>5}{'>1k':>4}{'hedge':>6}{'wins':>5}"
          f"{'amp':>6}{'gapmin':>8}{'mx':>4}")
    for r in sorted(ok, key=lambda x: x["_schedule"]["ordinal"]):
        sc = r["_schedule"]
        lg = r.get("logical_ms") or []
        lt = r.get("logical_thresholds") or {}
        hg = r.get("hedge") or {}
        f = lambda v, n=2: "-" if v is None else format(v, f".{n}f")
        print(f"{sc['ordinal']:>4}{sc['round']:>4}{sc['position']:>4}{sc['arm']:>6}"
              f"{f(r.get('full_file_wall_ms'),0):>8}"
              f"{f(statistics.median(lg) if lg else None,1):>8}"
              f"{f(statistics.fmean(lg) if lg else None,1):>9}"
              f"{f(r.get('logical_max_ms'),0):>8}"
              f"{lt.get('ge_250',0):>5}{lt.get('ge_500',0):>5}{lt.get('ge_1000',0):>4}"
              f"{hg.get('launched',0):>6}{hg.get('rescue_wins',0):>5}"
              f"{f(hg.get('amplification'),4):>6}"
              f"{f(r.get('min_attempt_gap_ms')):>8}"
              f"{r.get('max_simultaneous_in_flight') if r.get('max_simultaneous_in_flight') is not None else '-':>4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
