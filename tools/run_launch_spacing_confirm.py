#!/usr/bin/env python
"""Launch-spacing CONFIRMATION: 0 ms vs 2 ms vs 4 ms, 15 fresh H100 runs per arm.

45 runs total, balanced rotating order so no arm is run consecutively.
Only the treatment variable changes; geometry is frozen at the screening workload.
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
_REPS = 15
_RUN_TIMEOUT_S = 900
_OUT = _ROOT / "launch_spacing_confirm_runs"
_IDENTITY_FILE = _ROOT / "sentinel_runs" / "fullfile_h100_identity.json"

# arm_id, min_launch_gap_ms, label
ARMS: list[tuple[str, float, str]] = [
    ("c0", 0.0, "0 ms (positive control, same gate)"),
    ("c2", 2.0, "2 ms"),
    ("c4", 4.0, "4 ms"),
]
_THRESHOLDS = (250.0, 500.0, 1000.0)


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


def _invoke(handle, arm_id: str, gap_ms: float, rep: int) -> dict[str, Any]:
    attempt = f"cf-{arm_id}-r{rep:02d}"
    path = _OUT / f"{attempt}.json"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if _valid(existing) and _h100(existing):
                print(f"[cf] skip {attempt}", flush=True)
                return existing
        except Exception:
            pass
    print(f"[cf] start {attempt} gap_ms={gap_ms}", flush=True)
    try:
        result = handle.remote(
            read_mib=_READ_MIB, qd=_QD, min_launch_gap_ms=gap_ms, attempt_id=attempt
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
        f"[cf] done {attempt} gpu={((result.get('identity') or {}).get('observed_gpu'))} "
        f"region={result.get('region')} gbps={result.get('full_file_decimal_gbps')} "
        f"worst={result.get('max_ms')} ge250={(result.get('thresholds') or {}).get('ge_250')} "
        f"obs_min={ls.get('observed_min_inter_start_ms')} "
        f"ovl={ls.get('frac_entered_with_other_active')} conc={ls.get('mean_effective_concurrency')}",
        flush=True,
    )
    return result


def _arm(ok: list[dict[str, Any]], gap: float) -> list[dict[str, Any]]:
    return [
        r for r in ok
        if abs(float((r.get("config") or {}).get("min_launch_gap_ms") or 0) - gap) < 1e-9
        and int((r.get("config") or {}).get("qd") or 0) == _QD
    ]


def _f(v, p=2):
    return "-" if v is None else format(v, f".{p}f")


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
        start = (rep - 1) % len(ARMS)
        order = ARMS[start:] + ARMS[:start]
        for arm_id, gap_ms, _label in order:
            results.append(_invoke(handle, arm_id, gap_ms, rep))

    ok = [r for r in results if _valid(r) and _h100(r)]
    wrong = [r for r in results if _valid(r) and not _h100(r)]
    bad = [r for r in results if not _valid(r)]
    print(f"\nvalid H100 runs: {len(ok)} / {len(results)}")
    if wrong:
        print(f"REJECTED wrong-GPU: {[r.get('attempt_id') for r in wrong]}")
    if bad:
        print(f"INVALID: {[(r.get('attempt_id'), r.get('error')) for r in bad]}")

    regions = {}
    for r in ok:
        regions.setdefault(r.get("region") or "?", 0)
        regions[r.get("region") or "?"] += 1
    print(f"regions: {regions}")

    # ---------------- per-run ----------------
    print("\n=== per-run ===")
    hdr = (f"{'run':<16}{'gap':>4}{'wall':>7}{'gbps':>7}{'n':>4}{'med':>7}{'p95':>7}"
           f"{'p99':>8}{'max':>8}{'>250':>5}{'>500':>5}{'>1k':>5}{'ex100':>8}"
           f"{'gmin':>7}{'gp5':>7}{'gmed':>7}{'gp95':>8}{'ovl':>6}{'conc':>6}{'mxact':>6}")
    print(hdr)
    for r in sorted(ok, key=lambda x: (float((x.get("config") or {}).get("min_launch_gap_ms") or 0),
                                       x.get("attempt_id") or "")):
        cfg = r.get("config") or {}
        ls = r.get("launch_spacing") or {}
        th = r.get("thresholds") or {}
        reads = r.get("reads") or []
        excess = sum(max(0.0, x["preadv_ms"] - 100.0) for x in reads)
        print(
            f"{(r.get('attempt_id') or ''):<16}{cfg.get('min_launch_gap_ms',0):>4.0f}"
            f"{_f(r.get('full_file_wall_ms'),0):>7}{_f(r.get('full_file_decimal_gbps'),3):>7}"
            f"{len(reads):>4}{_f(r.get('median_ms')):>7}{_f(r.get('p95_ms')):>7}"
            f"{_f(r.get('p99_ms')):>8}{_f(r.get('max_ms'),0):>8}"
            f"{th.get('ge_250',0):>5}{th.get('ge_500',0):>5}{th.get('ge_1000',0):>5}"
            f"{_f(excess,0):>8}{_f(ls.get('observed_min_inter_start_ms')):>7}"
            f"{_f(ls.get('observed_p5_inter_start_ms')):>7}"
            f"{_f(ls.get('observed_median_inter_start_ms')):>7}"
            f"{_f(ls.get('observed_p95_inter_start_ms')):>8}"
            f"{_f(ls.get('frac_entered_with_other_active'),3):>6}"
            f"{_f(ls.get('mean_effective_concurrency')):>6}"
            f"{ls.get('max_simultaneous_in_flight') if ls.get('max_simultaneous_in_flight') is not None else '-':>6}"
        )

    # ---------------- summary ----------------
    print("\n=== summary ===")
    print(f"{'gap':>4}{'runs':>5}{'r>=250':>7}{'r>=500':>7}{'r>=1k':>7}"
          f"{'n>=250':>7}{'n>=500':>7}{'n>=1k':>7}{'worst':>9}"
          f"{'medGbps':>9}{'minGbps':>9}{'ovl':>7}{'conc':>6}")
    for arm_id, gap_ms, _label in ARMS:
        a = _arm(ok, gap_ms)
        if not a:
            print(f"{gap_ms:>4.0f}    0  (no runs)")
            continue
        r250 = sum(1 for r in a if (r.get("thresholds") or {}).get("ge_250", 0) > 0)
        r500 = sum(1 for r in a if (r.get("thresholds") or {}).get("ge_500", 0) > 0)
        r1k = sum(1 for r in a if (r.get("thresholds") or {}).get("ge_1000", 0) > 0)
        n250 = sum((r.get("thresholds") or {}).get("ge_250", 0) for r in a)
        n500 = sum((r.get("thresholds") or {}).get("ge_500", 0) for r in a)
        n1k = sum((r.get("thresholds") or {}).get("ge_1000", 0) for r in a)
        g = [r["full_file_decimal_gbps"] for r in a if r.get("full_file_decimal_gbps")]
        ovl = [(r.get("launch_spacing") or {}).get("frac_entered_with_other_active")
               for r in a]
        ovl = [v for v in ovl if v is not None]
        conc = [(r.get("launch_spacing") or {}).get("mean_effective_concurrency") for r in a]
        conc = [v for v in conc if v is not None]
        print(f"{gap_ms:>4.0f}{len(a):>5}{r250:>7}{r500:>7}{r1k:>7}"
              f"{n250:>7}{n500:>7}{n1k:>7}{max((r.get('max_ms') or 0) for r in a):>9.0f}"
              f"{statistics.median(g):>9.3f}{min(g):>9.3f}"
              f"{statistics.fmean(ovl):>7.3f}{statistics.fmean(conc):>6.2f}")

    # ---------------- generation-0 only ----------------
    print("\n=== generation 0 only ===")
    print(f"{'gap':>4}{'gen0 n':>8}{'>=250':>7}{'>=500':>7}{'>=1k':>6}{'worst':>9}")
    for arm_id, gap_ms, _label in ARMS:
        a = _arm(ok, gap_ms)
        n = c250 = c500 = c1000 = 0
        worst = 0.0
        for r in a:
            g0 = (r.get("generation_stats") or {}).get("g0")
            if not g0:
                continue
            n += g0["n"]
            c250 += g0["ge_250"]
            c500 += g0["ge_500"]
            c1000 += g0["ge_1000"]
            worst = max(worst, g0["max_ms"])
        print(f"{gap_ms:>4.0f}{n:>8}{c250:>7}{c500:>7}{c1000:>6}{worst:>9.0f}")

    # ---------------- per-generation ----------------
    print("\n=== per-generation (max ms across arm / counts) ===")
    for arm_id, gap_ms, _label in ARMS:
        a = _arm(ok, gap_ms)
        parts = []
        for gen in ("g0", "g1", "g2", "g3"):
            vals = [(r.get("generation_stats") or {}).get(gen) for r in a]
            vals = [v for v in vals if v]
            if not vals:
                continue
            parts.append(
                f"{gen}: n={sum(v['n'] for v in vals)} max={max(v['max_ms'] for v in vals):.0f} "
                f"ge500={sum(v['ge_500'] for v in vals)} ge1k={sum(v['ge_1000'] for v in vals)}"
            )
        print(f"  gap {gap_ms:>2.0f} | " + " | ".join(parts))

    # ---------------- first four launches ----------------
    print("\n=== first four global launches ===")
    for arm_id, gap_ms, _label in ARMS:
        for r in sorted(_arm(ok, gap_ms), key=lambda x: x.get("attempt_id") or ""):
            fl = r.get("first_launches") or []
            desc = " | ".join(
                f"#{x['ordinal']}w{x['worker']} t={x['t_rel_ms']:.1f} "
                f"gap={'-' if x['gap_from_previous_ms'] is None else format(x['gap_from_previous_ms'],'.2f')} "
                f"lat={x['preadv_ms']:.0f} act={x['active_at_enter']}"
                for x in fl
            )
            print(f"  gap{gap_ms:>2.0f} {(r.get('attempt_id') or ''):<16} :: {desc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
