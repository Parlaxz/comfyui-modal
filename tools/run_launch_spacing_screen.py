#!/usr/bin/env python
"""Launch-spacing screen: QD1 serial oracle + 8 global inter-launch gap arms @ QD4.

27 fresh H100 runs total: 9 arms x 3 reps, rotated so identical arms are not run
back to back.  Only the treatment variable changes; geometry is frozen at the
recent 64 MiB source-only workload.

This is a THRESHOLD SCREEN, not production proof.
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
_PACING_QD = 4
_ORACLE_QD = 1
_REPS = 3
_RUN_TIMEOUT_S = 900
_OUT = _ROOT / "launch_spacing_runs"

# (arm_id, qd, min_launch_gap_ms, label)
ARMS: list[tuple[str, int, float, str]] = [
    ("qd1", _ORACLE_QD, 0.0, "QD1 serial oracle"),
    ("g0", _PACING_QD, 0.0, "QD4 control (gap 0, same gate)"),
    ("g1", _PACING_QD, 1.0, "QD4 gap 1 ms"),
    ("g2", _PACING_QD, 2.0, "QD4 gap 2 ms"),
    ("g4", _PACING_QD, 4.0, "QD4 gap 4 ms"),
    ("g8", _PACING_QD, 8.0, "QD4 gap 8 ms"),
    ("g16", _PACING_QD, 16.0, "QD4 gap 16 ms"),
    ("g32", _PACING_QD, 32.0, "QD4 gap 32 ms"),
    ("g64", _PACING_QD, 64.0, "QD4 gap 64 ms"),
]


def _workspace() -> dict[str, Any]:
    import tomllib

    target = tomllib.loads(
        (_ROOT / "config" / "v2" / "modal_target.toml").read_text("utf-8")
    )
    wanted = str((target.get("modal") or {}).get("workspace_id") or "").strip()
    for registry in (
        _ROOT / ".git" / "comfymodal" / "modal_workspaces.json",
        _ROOT / ".modal_workspaces.json",
    ):
        if not registry.is_file():
            continue
        data = json.loads(registry.read_text("utf-8"))
        ws = next(
            (w for w in data.get("workspaces", []) if str(w.get("id") or "") == wanted),
            None,
        )
        if ws and ws.get("token_id") and ws.get("token_secret"):
            return ws
    raise RuntimeError(f"no credentials for workspace {wanted}")


def _valid(r: dict[str, Any]) -> bool:
    return bool(
        r.get("status") == "ok"
        and r.get("physical_reads")
        and r.get("useful_bytes")
        and (r.get("identity") or {}).get("observed_gpu")
    )


def _h100(r: dict[str, Any]) -> bool:
    return "H100" in str((r.get("identity") or {}).get("observed_gpu") or "")


def _invoke(handle, arm_id: str, qd: int, gap_ms: float, rep: int) -> dict[str, Any]:
    attempt = f"ls-{arm_id}-r{rep}"
    path = _OUT / f"{attempt}.json"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if _valid(existing):
                print(f"[ls] skip {attempt}", flush=True)
                return existing
        except Exception:
            pass
    print(f"[ls] start {attempt} qd={qd} gap_ms={gap_ms}", flush=True)
    try:
        result = handle.remote(
            read_mib=_READ_MIB, qd=qd, min_launch_gap_ms=gap_ms, attempt_id=attempt
        )
        if not isinstance(result, dict):
            raise RuntimeError(f"returned {type(result).__name__}")
    except Exception as exc:
        result = {
            "status": "error",
            "error": f"{type(exc).__name__}:{exc}"[:400],
            "attempt_id": attempt,
        }
    path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    ls = result.get("launch_spacing") or {}
    print(
        f"[ls] done {attempt} gpu={((result.get('identity') or {}).get('observed_gpu'))} "
        f"gbps={result.get('full_file_decimal_gbps')} worst={result.get('max_ms')} "
        f"obs_min_gap={ls.get('observed_min_inter_start_ms')} "
        f"frac_overlap={ls.get('frac_entered_with_other_active')}",
        flush=True,
    )
    return result


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
    rotation = [0, 3, 6]  # start offset per rep round, avoids 3-in-a-row
    for rep in range(1, _REPS + 1):
        start = rotation[(rep - 1) % len(rotation)]
        order = ARMS[start:] + ARMS[:start]
        for arm_id, qd, gap_ms, _label in order:
            results.append(_invoke(handle, arm_id, qd, gap_ms, rep))

    ok = [r for r in results if _valid(r) and _h100(r)]
    bad_gpu = [r for r in results if _valid(r) and not _h100(r)]
    print(f"\nvalid H100 runs: {len(ok)} / {len(results)}")
    if bad_gpu:
        print(f"EXCLUDED wrong-GPU runs: {[r.get('attempt_id') for r in bad_gpu]}")
    errs = [r for r in results if not _valid(r)]
    if errs:
        print(f"invalid/error runs: {[(r.get('attempt_id'), r.get('error')) for r in errs]}")

    print("\n=== per-run ===")
    hdr = (f"{'run':<16}{'qd':>3}{'gap':>6}{'gbps':>8}{'worst':>9}"
           f"{'>=250':>6}{'>=500':>6}{'>=1000':>6}"
           f"{'obs_min':>9}{'obs_med':>9}{'frac_ovl':>9}{'eff_conc':>9}")
    print(hdr)
    for r in ok:
        ls = r.get("launch_spacing") or {}
        th = r.get("thresholds") or {}
        cfg = r.get("config") or {}
        f = lambda v, p=2: "-" if v is None else format(v, f".{p}f")
        print(
            f"{r.get('attempt_id',''):<16}{cfg.get('qd',0):>3}"
            f"{cfg.get('min_launch_gap_ms',0):>6.0f}"
            f"{f(r.get('full_file_decimal_gbps'),3):>8}"
            f"{f(r.get('max_ms'),0):>9}"
            f"{th.get('ge_250',0):>6}{th.get('ge_500',0):>6}{th.get('ge_1000',0):>6}"
            f"{f(ls.get('observed_min_inter_start_ms'),2):>9}"
            f"{f(ls.get('observed_median_inter_start_ms'),2):>9}"
            f"{f(ls.get('frac_entered_with_other_active'),3):>9}"
            f"{f(ls.get('mean_effective_concurrency'),2):>9}"
        )

    print("\n=== per-arm summary ===")
    print(f"{'arm':<6}{'n':>3}{'med_gbps':>10}{'min_gbps':>10}{'worst':>10}"
          f"{'>=250':>7}{'>=500':>7}{'>=1000':>7}{'obs_med_gap':>12}{'frac_ovl':>10}{'eff_conc':>10}")
    import statistics

    for arm_id, qd, gap_ms, label in ARMS:
        arm = [r for r in ok if (r.get("config") or {}).get("min_launch_gap_ms") == gap_ms
               and (r.get("config") or {}).get("qd") == qd]
        if not arm:
            print(f"{arm_id:<6}  0  (no valid runs)")
            continue
        g = [r["full_file_decimal_gbps"] for r in arm if r.get("full_file_decimal_gbps")]
        w = [r.get("max_ms") or 0 for r in arm]
        c250 = sum((r.get("thresholds") or {}).get("ge_250", 0) for r in arm)
        c500 = sum((r.get("thresholds") or {}).get("ge_500", 0) for r in arm)
        c1000 = sum((r.get("thresholds") or {}).get("ge_1000", 0) for r in arm)
        ls = [r.get("launch_spacing") or {} for r in arm]
        med_gap = [x.get("observed_median_inter_start_ms") for x in ls
                   if x.get("observed_median_inter_start_ms") is not None]
        ovl = [x.get("frac_entered_with_other_active") for x in ls
               if x.get("frac_entered_with_other_active") is not None]
        conc = [x.get("mean_effective_concurrency") for x in ls
                if x.get("mean_effective_concurrency") is not None]
        f = lambda v, p=2: "-" if not v else format(statistics.median(v), f".{p}f")
        print(f"{arm_id:<6}{len(arm):>3}"
              f"{statistics.median(g):>10.3f}{min(g):>10.3f}{max(w):>10.0f}"
              f"{c250:>7}{c500:>7}{c1000:>7}{f(med_gap):>12}{f(ovl,3):>10}{f(conc):>10}")

    print("\n=== per-arm generation breakdown (g0..g3) ===")
    for arm_id, qd, gap_ms, label in ARMS:
        arm = [r for r in ok if (r.get("config") or {}).get("min_launch_gap_ms") == gap_ms
               and (r.get("config") or {}).get("qd") == qd]
        if not arm:
            continue
        parts = []
        for gen in ("g0", "g1", "g2", "g3"):
            vals = [(r.get("generation_stats") or {}).get(gen) for r in arm]
            vals = [v for v in vals if v]
            if not vals:
                continue
            s500 = sum(v["ge_500"] for v in vals)
            s1000 = sum(v["ge_1000"] for v in vals)
            nmax = max(v["max_ms"] for v in vals)
            parts.append(f"{gen}: n={sum(v['n'] for v in vals)} "
                         f"max={nmax:.0f} ge500={s500} ge1000={s1000}")
        print(f"  {arm_id:<5} | " + " | ".join(parts))

    print("\n=== first four global launches (all runs) ===")
    for r in ok:
        fl = r.get("first_launches") or []
        desc = " | ".join(
            f"#{x['ordinal']}w{x['worker']} t={x['t_rel_ms']:.1f} "
            f"gap={'-' if x['gap_from_previous_ms'] is None else format(x['gap_from_previous_ms'],'.2f')} "
            f"lat={x['preadv_ms']:.0f} act={x['active_at_enter']}"
            for x in fl
        )
        print(f"  {r.get('attempt_id',''):<16} qd{(r.get('config') or {}).get('qd')} "
              f"gap{(r.get('config') or {}).get('min_launch_gap_ms',0):.0f} :: {desc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
