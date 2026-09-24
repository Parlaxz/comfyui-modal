#!/usr/bin/env python
"""Minimal smoke runner for the rolling geometry sweep.

Two calls only: one H100, one RTX PRO 6000.  Each call runs all four
(read size, QD) cells over distinct never-reused regions.

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
_MIB = 1024 ** 2


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

    out_dir = _ROOT / "source_geom_runs"
    out_dir.mkdir(exist_ok=True)
    results: dict[str, Any] = {}
    for family in ("h100", "rtx"):
        attempt = f"geom-{family}"
        fn = modal.Function.from_name(_APP, f"run_source_geom_{family}")
        print(f"[geom] invoking {attempt} ...", flush=True)
        result = fn.remote(attempt_id=attempt)
        results[family] = result
        (out_dir / f"{attempt}.json").write_text(
            json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        print(f"[geom] {attempt} status={result.get('status')} error={result.get('error')}",
              flush=True)

    print()
    print("GPU | read MiB | QD | bytes-in-flight MiB | total GiB | mean preadv ms | median | "
          "p95 | max | source wall ms | GB/s | median refill gap ms")
    print("|".join(["---"] * 12))
    for family in ("h100", "rtx"):
        result = results[family]
        if result.get("status") != "ok":
            print(f"{family} | ERROR | {result.get('error')}")
            continue
        for cell in result.get("cells") or []:
            if cell.get("status") == "error":
                print(f"{family} | {cell['cell']['read_mib']} | {cell['cell']['qd']} | "
                      f"ERROR | {cell.get('error')}")
                continue
            gaps = [
                worker["refill_gap_median_ms"]
                for worker in cell["per_worker"]
                if worker["refill_gap_median_ms"] is not None
            ]
            gap_text = f"{sum(gaps) / len(gaps):.3f}" if gaps else "-"
            print(
                f"{family} | {cell['cell']['read_mib']} | {cell['cell']['qd']} | "
                f"{cell['bytes_in_flight_mib']:.0f} | {cell['useful_bytes'] / _GIB:.3f} | "
                f"{cell['mean_ms']:.3f} | {cell['median_ms']:.3f} | {cell['p95_ms']:.3f} | "
                f"{cell['max_ms']:.3f} | {cell['source_wall_ms']:.3f} | "
                f"{(cell['useful_decimal_gbps'] or 0.0):.3f} | {gap_text}"
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
        print(f"  total_span_bytes={cfg.get('total_span_bytes')}")
        print(f"  syscall_impl={env.get('syscall_impl')} preadv_available={env.get('preadv_available')}")
        for cell in result.get("cells") or []:
            if cell.get("status") == "error":
                continue
            print(f"  read={cell['cell']['read_mib']} MiB QD={cell['cell']['qd']} "
                  f"region_start={cell['region_start']} reads={cell['total_reads']} "
                  f"all_full={cell['all_full_length']} "
                  f"qd_min={cell['effective_qd_min_in_span']} qd_max={cell['effective_qd_max_in_span']} "
                  f"fell_below={cell['effective_qd_fell_below_n']} "
                  f"slowest={[round(r['preadv_ms'], 3) for r in sorted(cell['reads'], key=lambda r: r['preadv_ms'], reverse=True)[:3]]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
