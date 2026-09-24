#!/usr/bin/env python
"""Launch-spacing BOUNDARY: 2.5 / 3.0 / 3.5 ms x 15 fresh H100 runs each (45 new).

Reuses the existing 4.0 ms cohort from launch_spacing_confirm_runs/cf-c4-*.json
for the four-arm comparison.  Only the requested global inter-launch spacing
differs from the confirmation harness.
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
_OUT = _ROOT / "launch_spacing_boundary_runs"

ARMS: list[tuple[str, float]] = [("b25", 2.5), ("b30", 3.0), ("b35", 3.5)]


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
    attempt = f"bd-{arm_id}-r{rep:02d}"
    path = _OUT / f"{attempt}.json"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if _valid(existing) and _h100(existing):
                print(f"[bd] skip {attempt}", flush=True)
                return existing
        except Exception:
            pass
    print(f"[bd] start {attempt} gap_ms={gap_ms}", flush=True)
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
    reads = result.get("reads") or []
    durs = [x["preadv_ms"] for x in reads] or [0.0]
    ls = result.get("launch_spacing") or {}
    print(
        f"[bd] done {attempt} gpu={((result.get('identity') or {}).get('observed_gpu'))} "
        f"region={result.get('region')} gbps={result.get('full_file_decimal_gbps')} "
        f"med={statistics.median(durs):.1f} mean={statistics.fmean(durs):.1f} "
        f"max={result.get('max_ms')} ge500={(result.get('thresholds') or {}).get('ge_500')} "
        f"gmin={ls.get('observed_min_inter_start_ms')} ovl={ls.get('frac_entered_with_other_active')}",
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
    for rep in range(1, _REPS + 1):
        start = (rep - 1) % len(ARMS)
        order = ARMS[start:] + ARMS[:start]
        for arm_id, gap_ms in order:
            results.append(_invoke(handle, arm_id, gap_ms, rep))

    ok = [r for r in results if _valid(r) and _h100(r)]
    wrong = [r for r in results if _valid(r) and not _h100(r)]
    bad = [r for r in results if not _valid(r)]
    print(f"\nvalid H100 runs: {len(ok)} / {len(results)}")
    if wrong:
        print(f"REJECTED wrong-GPU: {[r.get('attempt_id') for r in wrong]}")
    if bad:
        print(f"INVALID: {[(r.get('attempt_id'), r.get('error')) for r in bad]}")

    regions: dict[str, int] = {}
    for r in ok:
        k = r.get("region") or "?"
        regions[k] = regions.get(k, 0) + 1
    print(f"regions: {regions}")

    print("\n=== per-run (new arms) ===")
    print(f"{'run':<16}{'gap':>5}{'gbps':>7}{'med':>7}{'mean':>7}{'p95':>8}{'p99':>9}"
          f"{'max':>8}{'>250':>5}{'>500':>5}{'>1k':>5}{'wall':>7}"
          f"{'gmin':>7}{'gp5':>7}{'gmed':>7}{'gp95':>8}{'ovl':>6}{'conc':>6}")
    for r in sorted(ok, key=lambda x: (float((x.get("config") or {}).get("min_launch_gap_ms") or 0),
                                       x.get("attempt_id") or "")):
        cfg = r.get("config") or {}
        ls = r.get("launch_spacing") or {}
        th = r.get("thresholds") or {}
        reads = r.get("reads") or []
        durs = [x["preadv_ms"] for x in reads]
        f = lambda v, p=2: "-" if v is None else format(v, f".{p}f")
        print(
            f"{(r.get('attempt_id') or ''):<16}{cfg.get('min_launch_gap_ms',0):>5.1f}"
            f"{f(r.get('full_file_decimal_gbps'),3):>7}"
            f"{f(statistics.median(durs) if durs else None,1):>7}"
            f"{f(statistics.fmean(durs) if durs else None,1):>7}"
            f"{f(r.get('p95_ms'),1):>8}{f(r.get('p99_ms'),1):>9}"
            f"{f(r.get('max_ms'),0):>8}"
            f"{th.get('ge_250',0):>5}{th.get('ge_500',0):>5}{th.get('ge_1000',0):>5}"
            f"{f(r.get('full_file_wall_ms'),0):>7}"
            f"{f(ls.get('observed_min_inter_start_ms')):>7}"
            f"{f(ls.get('observed_p5_inter_start_ms')):>7}"
            f"{f(ls.get('observed_median_inter_start_ms')):>7}"
            f"{f(ls.get('observed_p95_inter_start_ms')):>8}"
            f"{f(ls.get('frac_entered_with_other_active'),3):>6}"
            f"{f(ls.get('mean_effective_concurrency')):>6}"
        )

    print("\n=== first four launches, new arms ===")
    for arm_id, gap_ms in ARMS:
        for r in sorted(
            [x for x in ok if abs(float((x.get("config") or {}).get("min_launch_gap_ms") or 0)
                                  - gap_ms) < 1e-9],
            key=lambda x: x.get("attempt_id") or "",
        ):
            fl = r.get("first_launches") or []
            desc = " | ".join(
                f"#{x['ordinal']}w{x['worker']} t={x['t_rel_ms']:.1f} "
                f"gap={'-' if x['gap_from_previous_ms'] is None else format(x['gap_from_previous_ms'],'.2f')} "
                f"lat={x['preadv_ms']:.0f} act={x['active_at_enter']}"
                for x in fl
            )
            print(f"  {gap_ms:>4.1f} {(r.get('attempt_id') or ''):<16} :: {desc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
