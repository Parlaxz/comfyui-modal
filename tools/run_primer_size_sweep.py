#!/usr/bin/env python
"""Per-worker primer SIZE sweep: control vs 1/4/16/64 MiB primers.

H100 only, 64 MiB measured reads, QD4.  5 arms x 12 fresh containers = 60 runs,
executed in a rotating (balanced) arm order so time/placement does not align
with primer size.  One fresh container per run; runs serial; resume-safe.

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
_RUN_TIMEOUT_S = 600
# (arm label, primer MiB) -- primer 0 means the no-primer control.
_ARMS = (("control", 0), ("p1", 1), ("p4", 4), ("p16", 16), ("p64", 64))


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


def _schedule() -> list[tuple[str, int, int]]:
    """Balanced rotating order: round r starts at arm r%5, cycling."""
    schedule = []
    for round_index in range(_ROUNDS):
        offset = round_index % len(_ARMS)
        order = _ARMS[offset:] + _ARMS[:offset]
        for label, primer_mib in order:
            schedule.append((label, primer_mib, round_index + 1))
    return schedule


def _derive(result: dict[str, Any]) -> dict[str, Any]:
    primers = list((result.get("primer_results") or {}).values())
    if primers:
        primer_wall = (max(p["exit_ns"] for p in primers)
                       - min(p["enter_ns"] for p in primers)) / 1e6
    else:
        primer_wall = 0.0
    measured_wall = result.get("measured_wall_ms") or 0.0
    total_wall = primer_wall + measured_wall
    useful = result.get("useful_bytes") or 0
    result["_primer_wall_ms"] = primer_wall
    result["_total_source_wall_ms"] = total_wall
    result["_effective_total_gbps"] = (useful / (total_wall / 1000.0) / 1e9) if total_wall else None
    return result


def main() -> int:
    workspace = _workspace()
    os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])

    import modal

    out_dir = _ROOT / "primer_size_runs"
    out_dir.mkdir(exist_ok=True)
    fn = modal.Function.from_name(_APP, "run_startup_arm_h100")
    try:
        handle = fn.with_options(timeout=_RUN_TIMEOUT_S)
    except Exception:
        handle = fn

    results: list[dict[str, Any]] = []
    for label, primer_mib, round_index in _schedule():
        attempt = f"{label}-r{round_index:02d}"
        path = out_dir / f"{attempt}.json"
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if _valid(existing):
                    print(f"[size] skip {attempt} (valid artifact exists)", flush=True)
                    results.append(_derive(existing))
                    continue
            except Exception:
                pass
        arm = "control" if primer_mib == 0 else "primed"
        print(f"[size] start {attempt} arm={arm} primer_mib={primer_mib}", flush=True)
        try:
            result = handle.remote(
                read_mib=_READ_MIB, qd=_QD, arm=arm,
                stagger_ms=0, attempt_id=attempt,
                primer_bytes=primer_mib * 1024 * 1024,
            )
            if not isinstance(result, dict):
                raise RuntimeError(f"returned {type(result).__name__}")
        except Exception as exc:
            result = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:400],
                      "attempt_id": attempt}
        result["_label"] = label
        result["_primer_mib"] = primer_mib
        path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str),
                        encoding="utf-8")
        results.append(_derive(result))
        print(f"[size] done {attempt} status={result.get('status')} "
              f"measured_gbps={result.get('measured_decimal_gbps')} "
              f"total_wall={result.get('_total_source_wall_ms')}", flush=True)

    ok = [r for r in results if r.get("status") == "ok"]
    print()
    print("arm | rep | region | primer wall ms | max primer ms | primer>=1000 | "
          "measured GB/s | total source wall ms | effective total GB/s | measured median | measured max | "
          "ge250 | ge500 | ge1000 | QD ok?")
    for r in sorted(ok, key=lambda x: (x.get("_primer_mib", 0), x.get("attempt_id", ""))):
        th = r.get("thresholds") or {}
        primers = list((r.get("primer_results") or {}).values())
        p1000 = sum(1 for p in primers if p["preadv_ms"] >= 1000)
        qd_ok = (r.get("effective_qd_min_in_span") or 0) >= _QD - 1
        print(f"| {r.get('_label')} | {r.get('attempt_id')} | {r.get('provider')}/{r.get('region')} | "
              f"{r.get('_primer_wall_ms'):.1f} | "
              f"{(max((p['preadv_ms'] for p in primers), default=0.0)):.1f} | {p1000} | "
              f"{r.get('measured_decimal_gbps'):.3f} | {r.get('_total_source_wall_ms'):.1f} | "
              f"{r.get('_effective_total_gbps'):.3f} | {r.get('median_ms'):.1f} | {r.get('max_ms'):.0f} | "
              f"{th.get('ge_250')} | {th.get('ge_500')} | {th.get('ge_1000')} | {qd_ok} |")

    print()
    print("=== per-arm summary (n=12) ===")
    for label, primer_mib in _ARMS:
        rs = [r for r in ok if r.get("_label") == label]
        if not rs:
            print(f"{label}: no valid runs")
            continue
        g = [r["measured_decimal_gbps"] for r in rs]
        pw = [r["_primer_wall_ms"] for r in rs]
        tw = [r["_total_source_wall_ms"] for r in rs]
        eff = [r["_effective_total_gbps"] for r in rs]
        r250 = sum(1 for r in rs if (r.get("thresholds") or {}).get("ge_250", 0) > 0)
        r500 = sum(1 for r in rs if (r.get("thresholds") or {}).get("ge_500", 0) > 0)
        r1000 = sum(1 for r in rs if (r.get("thresholds") or {}).get("ge_1000", 0) > 0)
        t250 = sum((r.get("thresholds") or {}).get("ge_250", 0) for r in rs)
        t500 = sum((r.get("thresholds") or {}).get("ge_500", 0) for r in rs)
        t1000 = sum((r.get("thresholds") or {}).get("ge_1000", 0) for r in rs)
        worst = max(r["max_ms"] for r in rs)
        patho = sum(1 for r in rs
                    if any(p["preadv_ms"] >= 1000 for p in (r.get("primer_results") or {}).values()))
        regions = sorted({f"{r.get('provider')}/{r.get('region')}" for r in rs})
        print(f"\n{label} ({primer_mib} MiB): n={len(rs)}")
        print(f"  primer wall median={statistics.median(pw):.1f} p95={sorted(pw)[int(0.95*len(pw))-1]:.1f} "
              f"pathological_primer_runs={patho}")
        print(f"  measured GB/s median={statistics.median(g):.3f} mean={statistics.fmean(g):.3f} "
              f"min={min(g):.3f} max={max(g):.3f} sd={statistics.stdev(g) if len(g)>1 else 0:.3f}")
        print(f"  total wall median={statistics.median(tw):.1f} mean={statistics.fmean(tw):.1f} "
              f"min={min(tw):.1f} max={max(tw):.1f}")
        print(f"  effective total GB/s median={statistics.median(eff):.3f} "
              f"mean={statistics.fmean(eff):.3f} min={min(eff):.3f} max={max(eff):.3f}")
        print(f"  runs with measured >=250/500/1000: {r250}/{r500}/{r1000}  "
              f"total measured >=250/500/1000: {t250}/{t500}/{t1000}  worst measured {worst:.0f} ms")
        print(f"  regions({len(regions)}): {', '.join(regions)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
