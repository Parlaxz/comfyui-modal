#!/usr/bin/env python
"""Minimal smoke runner for the rolling source-QD probe.

Two calls only: one H100, one RTX PRO 6000.  Each call runs N = 1/2/4/8 once.

Raw measurements only.  No tuning, no campaign.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_APP = "sept-clip-source-race-oracle"
_GIB = 1024 ** 3


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


def main() -> int:
    workspace = _workspace()
    os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])

    import modal

    out_dir = _ROOT / "source_roll_runs"
    out_dir.mkdir(exist_ok=True)
    results: dict[str, Any] = {}
    for family in ("h100", "rtx"):
        attempt = f"roll-{family}"
        fn = modal.Function.from_name(_APP, f"run_source_roll_{family}")
        print(f"[roll] invoking {attempt} ...", flush=True)
        result = fn.remote(attempt_id=attempt)
        results[family] = result
        (out_dir / f"{attempt}.json").write_text(
            json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        print(f"[roll] {attempt} status={result.get('status')} error={result.get('error')}",
              flush=True)

    print()
    print("GPU | N | total GiB | mean preadv ms | median | p95 | max | source wall ms | GB/s | "
          "median refill gap ms | effective-QD notes")
    print("|".join(["---"] * 11))
    for family in ("h100", "rtx"):
        result = results[family]
        if result.get("status") != "ok":
            print(f"{family} | ERROR | {result.get('error')}")
            continue
        for batch in result.get("batches") or []:
            gaps = [
                worker["refill_gap_median_ms"]
                for worker in batch["per_worker"]
                if worker["refill_gap_median_ms"] is not None
            ]
            gap_text = f"{sum(gaps) / len(gaps):.3f}" if gaps else "-"
            notes = (
                f"min {batch['effective_qd_min_in_span']}/max "
                f"{batch['effective_qd_max_in_span']} in span, "
                f"fell_below_n={batch['effective_qd_fell_below_n']}"
            )
            print(
                f"{family} | {batch['n']} | {batch['useful_bytes'] / _GIB:.3f} | "
                f"{batch['mean_ms']:.3f} | {batch['median_ms']:.3f} | {batch['p95_ms']:.3f} | "
                f"{batch['max_ms']:.3f} | {batch['source_wall_ms']:.3f} | "
                f"{(batch['useful_decimal_gbps'] or 0.0):.3f} | {gap_text} | {notes}"
            )
    print()
    for family in ("h100", "rtx"):
        result = results[family]
        if result.get("status") != "ok":
            continue
        fi = result.get("file_identity") or {}
        cfg = result.get("config") or {}
        env = result.get("env") or {}
        print(f"--- {family} ---")
        print(f"  observed_gpu={result.get('observed_gpu')} requested_gpu={result.get('requested_gpu')}")
        print(f"  provider={result.get('provider')} region={result.get('region')}")
        print(f"  container_session_id={result.get('container_session_id')}")
        print(f"  resolved_path={result.get('resolved_path')}")
        print(f"  file_size={fi.get('size')} st_dev={fi.get('st_dev')} st_ino={fi.get('st_ino')}")
        print(f"  read_bytes={cfg.get('read_bytes')} blocks_per_worker={cfg.get('blocks_per_worker')} "
              f"workers={cfg.get('workers')}")
        print(f"  syscall_impl={env.get('syscall_impl')} preadv_available={env.get('preadv_available')}")
        for batch in result.get("batches") or []:
            print(f"  N={batch['n']:>2} reads={batch['total_reads']} "
                  f"all_full={batch['all_full_length']} "
                  f"span_ms={batch['effective_qd_span_ms']:.3f} "
                  f"regions={[(w['worker'], w['first_offset']) for w in batch['worker_regions']]}")
            for worker in batch["per_worker"]:
                print(f"    worker={worker['worker']} reads={worker['reads']} "
                      f"GBps={(worker['decimal_gbps'] or 0.0):.3f} "
                      f"gap_mean={worker['refill_gap_mean_ms']:.3f} "
                      f"gap_median={worker['refill_gap_median_ms']:.3f} "
                      f"gap_max={worker['refill_gap_max_ms']:.3f}")
            worst = sorted(batch["reads"], key=lambda r: r["preadv_ms"], reverse=True)[:3]
            print(f"    slowest_reads={[(r['worker'], round(r['preadv_ms'], 3)) for r in worst]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
