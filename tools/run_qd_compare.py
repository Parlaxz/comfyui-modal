#!/usr/bin/env python
"""QD4 vs QD8 at a fixed 4.0 ms global preadv launch spacing. 20 fresh H100 runs
per arm (40 total), alternating arms to avoid temporal drift.

Harness topology audit (run_fullfile_probe): buffers/views/records/FDs/barrier
parties are ALL qd-driven, so QD8 gets 8 independent buffers + 8 FDs + 15
blocks/worker. No shared staging resource throttles it.
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
_GAP_MS = 4.0
_REPS = 20
_RUN_TIMEOUT_S = 900
_OUT = _ROOT / "qd_compare_runs"

ARMS: list[tuple[str, int, float]] = [("q4", 4, _GAP_MS), ("q8", 8, _GAP_MS)]


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
    return bool(r.get("status") == "ok" and r.get("physical_reads") and r.get("useful_bytes")
                and (r.get("identity") or {}).get("observed_gpu"))


def _h100(r: dict[str, Any]) -> bool:
    return "H100" in str((r.get("identity") or {}).get("observed_gpu") or "")


def _invoke(handle, arm_id: str, qd: int, gap_ms: float, rep: int) -> dict[str, Any]:
    attempt = f"qc-{arm_id}-r{rep:02d}"
    path = _OUT / f"{attempt}.json"
    if path.exists():
        try:
            e = json.loads(path.read_text(encoding="utf-8"))
            if _valid(e) and _h100(e):
                print(f"[qc] skip {attempt}", flush=True)
                return e
        except Exception:
            pass
    print(f"[qc] start {attempt} qd={qd} gap={gap_ms}", flush=True)
    try:
        r = handle.remote(read_mib=_READ_MIB, qd=qd, min_launch_gap_ms=gap_ms,
                          attempt_id=attempt)
        if not isinstance(r, dict):
            raise RuntimeError(f"returned {type(r).__name__}")
    except Exception as exc:
        r = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:400],
             "attempt_id": attempt}
    path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str), encoding="utf-8")
    durs = [x["preadv_ms"] for x in (r.get("reads") or [])] or [0.0]
    ls = r.get("launch_spacing") or {}
    th = r.get("thresholds") or {}
    print(f"[qc] done {attempt} gpu={((r.get('identity') or {}).get('observed_gpu'))} "
          f"region={r.get('region')} wall={r.get('full_file_wall_ms')} "
          f"gbps={r.get('full_file_decimal_gbps')} med={statistics.median(durs):.1f} "
          f"mean={statistics.fmean(durs):.1f} max={r.get('max_ms')} "
          f"ge500={th.get('ge_500')} ge1k={th.get('ge_1000')} "
          f"gmin={ls.get('observed_min_inter_start_ms')} "
          f"ovl={ls.get('frac_entered_with_other_active')} "
          f"conc={ls.get('mean_effective_concurrency')}", flush=True)
    return r


def main() -> int:
    os.environ["MODAL_TOKEN_ID"] = str(_workspace()["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(_workspace()["token_secret"])
    import modal

    _OUT.mkdir(exist_ok=True)
    fn = modal.Function.from_name(_APP, "run_fullfile_h100")
    try:
        handle = fn.with_options(timeout=_RUN_TIMEOUT_S)
    except Exception:
        handle = fn

    results = []
    for rep in range(1, _REPS + 1):
        start = (rep - 1) % len(ARMS)          # alternate: q4,q8 / q8,q4 / ...
        order = ARMS[start:] + ARMS[:start]
        for arm_id, qd, gap in order:
            results.append(_invoke(handle, arm_id, qd, gap, rep))

    ok = [r for r in results if _valid(r) and _h100(r)]
    wrong = [r for r in results if _valid(r) and not _h100(r)]
    bad = [r for r in results if not _valid(r)]
    print(f"\nvalid H100 runs: {len(ok)} / {len(results)}")
    if wrong:
        print(f"REJECTED wrong-GPU: {[r.get('attempt_id') for r in wrong]}")
    if bad:
        print(f"INVALID: {[(r.get('attempt_id'), r.get('error')) for r in bad]}")

    regs: dict[str, int] = {}
    for r in ok:
        k = r.get("region") or "?"
        regs[k] = regs.get(k, 0) + 1
    print(f"regions: {regs}")

    print("\n=== per-run ===")
    print(f"{'run':<14}{'qd':>3}{'reads':>6}{'wall':>7}{'gbps':>7}{'p10':>7}{'med':>7}"
          f"{'mean':>7}{'p95':>8}{'p99':>9}{'best':>7}{'worst':>8}{'SD':>7}"
          f"{'>250':>5}{'>500':>5}{'>1k':>4}{'gmin':>7}{'gmed':>7}{'ovl':>6}{'conc':>6}{'mx':>3}")
    for r in sorted(ok, key=lambda x: (int((x.get("config") or {}).get("qd") or 0),
                                       x.get("attempt_id") or "")):
        cfg = r.get("config") or {}
        ls = r.get("launch_spacing") or {}
        th = r.get("thresholds") or {}
        d = [x["preadv_ms"] for x in (r.get("reads") or [])]
        def p(v):
            if not d:
                return None
            s = sorted(d); k = (len(s) - 1) * v / 100.0
            lo, hi = int(k), min(int(k) + 1, len(s) - 1)
            return s[lo] + (s[hi] - s[lo]) * (k - lo)
        f = lambda v, n=2: "-" if v is None else format(v, f".{n}f")
        sd = statistics.pstdev(d) if len(d) > 1 else 0.0
        print(f"{(r.get('attempt_id') or ''):<14}{cfg.get('qd',0):>3}{len(d):>6}"
              f"{f(r.get('full_file_wall_ms'),0):>7}{f(r.get('full_file_decimal_gbps'),3):>7}"
              f"{f(p(10),1):>7}{f(statistics.median(d) if d else None,1):>7}"
              f"{f(statistics.fmean(d) if d else None,1):>7}"
              f"{f(p(95),1):>8}{f(p(99),1):>9}{f(min(d) if d else None,1):>7}"
              f"{f(max(d) if d else None,0):>8}{f(sd,1):>7}"
              f"{th.get('ge_250',0):>5}{th.get('ge_500',0):>5}{th.get('ge_1000',0):>4}"
              f"{f(ls.get('observed_min_inter_start_ms')):>7}"
              f"{f(ls.get('observed_median_inter_start_ms')):>7}"
              f"{f(ls.get('frac_entered_with_other_active'),3):>6}"
              f"{f(ls.get('mean_effective_concurrency')):>6}"
              f"{ls.get('max_simultaneous_in_flight') if ls.get('max_simultaneous_in_flight') is not None else '-':>3}")

    print("\n=== first launches per run (QD4: 4, QD8: 8) ===")
    for r in sorted(ok, key=lambda x: (int((x.get("config") or {}).get("qd") or 0),
                                       x.get("attempt_id") or "")):
        qd = int((r.get("config") or {}).get("qd") or 0)
        fl = (r.get("first_launches") or [])[:qd]
        desc = " | ".join(
            f"#{x['ordinal']}w{x['worker']} t={x['t_rel_ms']:.1f} "
            f"gap={'-' if x['gap_from_previous_ms'] is None else format(x['gap_from_previous_ms'],'.2f')} "
            f"lat={x['preadv_ms']:.0f} act={x['active_at_enter']}"
            for x in fl)
        print(f"  qd{qd} {(r.get('attempt_id') or ''):<14} :: {desc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
