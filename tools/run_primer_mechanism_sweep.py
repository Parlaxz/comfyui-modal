#!/usr/bin/env python
"""Primer MECHANISM arms A-E: bytes vs elapsed time vs syscall count vs shape.

H100 only, 64 MiB measured reads, QD4.  5 arms x 12 fresh containers = 60 runs
in a balanced rotating order.  One fresh container per run; serial; resume-safe.

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
_ROUNDS = 12
_READ_MIB = 64
_QD = 4
_WAIT_MS = 135.0
_ARMS = ("A", "B", "C", "D", "E")
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
        and record.get("covered_bytes") == record.get("useful_bytes")
        and record.get("primer_syscalls")
    )


def main() -> int:
    workspace = _workspace()
    os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])

    import modal

    out_dir = _ROOT / "primer_mech_runs"
    out_dir.mkdir(exist_ok=True)
    fn = modal.Function.from_name(_APP, "run_primer_mechanism_h100")
    try:
        handle = fn.with_options(timeout=_RUN_TIMEOUT_S)
    except Exception:
        handle = fn

    results: list[dict[str, Any]] = []
    for round_index in range(_ROUNDS):
        offset = round_index % len(_ARMS)
        order = _ARMS[offset:] + _ARMS[:offset]
        print(f"[mech] round {round_index+1} order={order}", flush=True)
        for arm in order:
            attempt = f"{arm}-r{round_index+1:02d}"
            path = out_dir / f"{attempt}.json"
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                    if _valid(existing):
                        print(f"[mech] skip {attempt}", flush=True)
                        results.append(existing)
                        continue
                except Exception:
                    pass
            print(f"[mech] start {attempt}", flush=True)
            try:
                result = handle.remote(
                    read_mib=_READ_MIB, qd=_QD, arm=arm,
                    wait_target_ms=_WAIT_MS, attempt_id=attempt,
                )
                if not isinstance(result, dict):
                    raise RuntimeError(f"returned {type(result).__name__}")
            except Exception as exc:
                result = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:400],
                          "attempt_id": attempt}
            result["_arm"] = arm
            path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str),
                            encoding="utf-8")
            results.append(result)
            print(f"[mech] done {attempt} status={result.get('status')} "
                  f"meas_gbps={result.get('measured_decimal_gbps')} "
                  f"pretreat={result.get('pretreatment_wall_ms')}", flush=True)

    ok = [r for r in results if r.get("status") == "ok"]
    print()
    print("arm | rep | region | primer calls/worker | primer MiB/worker | primer wall | wait | "
          "pretreat wall | max primer | primer>=500 | primer>=1000 | meas GB/s | meas max | "
          ">=250 | >=500 | >=1000 | total wall | eff total GB/s | QD ok?")
    for arm in _ARMS:
        for r in sorted([x for x in ok if x.get("_arm") == arm], key=lambda x: x["attempt_id"]):
            th = r.get("thresholds") or {}
            pth = r.get("primer_thresholds") or {}
            cfg = r.get("config") or {}
            print(f"| {arm} | {r['attempt_id']} | {r.get('provider')}/{r.get('region')} | "
                  f"{cfg.get('primer_count')} | {cfg.get('primer_size_mib')} | "
                  f"{r.get('primer_io_wall_ms'):.1f} | {r.get('artificial_wait_ms'):.1f} | "
                  f"{r.get('pretreatment_wall_ms'):.1f} | {r.get('primer_max_ms'):.1f} | "
                  f"{pth.get('ge_500')} | {pth.get('ge_1000')} | "
                  f"{r.get('measured_decimal_gbps'):.3f} | {r.get('max_ms'):.0f} | "
                  f"{th.get('ge_250')} | {th.get('ge_500')} | {th.get('ge_1000')} | "
                  f"{r.get('total_source_wall_ms'):.1f} | {r.get('effective_total_gbps'):.3f} | "
                  f"{(r.get('effective_qd_min_in_span') or 0) >= _QD - 1} |")

    print()
    print("=== per-arm summary (n=12) ===")
    for arm in _ARMS:
        rs = [r for r in ok if r.get("_arm") == arm]
        if not rs:
            print(f"{arm}: no valid runs")
            continue
        g = [r["measured_decimal_gbps"] for r in rs]
        pw = [r["primer_io_wall_ms"] for r in rs]
        pre = [r["pretreatment_wall_ms"] for r in rs]
        tw = [r["total_source_wall_ms"] for r in rs]
        eff = [r["effective_total_gbps"] for r in rs]
        patho = sum(1 for r in rs if (r.get("primer_thresholds") or {}).get("ge_500", 0) > 0)
        a250 = sum(1 for r in rs if (r.get("thresholds") or {}).get("ge_250", 0) > 0)
        a500 = sum(1 for r in rs if (r.get("thresholds") or {}).get("ge_500", 0) > 0)
        a1000 = sum(1 for r in rs if (r.get("thresholds") or {}).get("ge_1000", 0) > 0)
        t250 = sum((r.get("thresholds") or {}).get("ge_250", 0) for r in rs)
        t500 = sum((r.get("thresholds") or {}).get("ge_500", 0) for r in rs)
        t1000 = sum((r.get("thresholds") or {}).get("ge_1000", 0) for r in rs)
        print(f"\n{arm}: n={len(rs)} primer={rs[0]['config']['primer_count']}x"
              f"{rs[0]['config']['primer_size_mib']}MiB")
        print(f"  primer wall median={statistics.median(pw):.1f} mean={statistics.fmean(pw):.1f} | "
              f"pretreat wall median={statistics.median(pre):.1f} | patho primer runs={patho}")
        print(f"  measured GB/s median={statistics.median(g):.3f} mean={statistics.fmean(g):.3f} "
              f"min={min(g):.3f} max={max(g):.3f} sd={statistics.stdev(g) if len(g)>1 else 0:.3f}")
        print(f"  runs measured >=250/500/1000: {a250}/{a500}/{a1000} | "
              f"total measured >=250/500/1000: {t250}/{t500}/{t1000} | "
              f"worst measured {max(r['max_ms'] for r in rs):.0f} ms")
        print(f"  total wall median={statistics.median(tw):.1f} mean={statistics.fmean(tw):.1f} | "
              f"eff total GB/s median={statistics.median(eff):.3f} mean={statistics.fmean(eff):.3f}")

    print()
    print("=== cumulative-bytes analysis (arms B and C) ===")
    for arm in ("B", "C"):
        buckets: dict[int, list[float]] = {}
        for r in ok:
            if r.get("_arm") != arm:
                continue
            for p in r.get("primer_cumulative") or []:
                buckets.setdefault(int(p["cumulative_before"] / (1024 * 1024)), []).append(p["preadv_ms"])
        print(f"\n{arm}: cumulative MiB before primer -> latency")
        print("  cum MiB | n | median | p95 | max | >=250 | >=500 | >=1000")
        for key in sorted(buckets):
            v = sorted(buckets[key])
            p95 = v[min(len(v) - 1, int(0.95 * len(v)))]
            print(f"  {key:>7} | {len(v)} | {statistics.median(v):.1f} | {p95:.1f} | {max(v):.0f} | "
                  f"{sum(1 for x in v if x>=250)} | {sum(1 for x in v if x>=500)} | "
                  f"{sum(1 for x in v if x>=1000)}")

    print()
    print("=== per-worker primer sequences for B and C (first 3 runs each) ===")
    for arm in ("B", "C"):
        shown = 0
        for r in sorted([x for x in ok if x.get("_arm") == arm], key=lambda x: x["attempt_id"]):
            if shown >= 3:
                break
            shown += 1
            byw: dict[int, list[float]] = {}
            for p in r.get("primer_records") or []:
                byw.setdefault(p["worker"], []).append(round(p["preadv_ms"], 1))
            print(f"{arm} {r['attempt_id']}: " +
                  " ".join(f"w{w}={byw[w]}" for w in sorted(byw)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
