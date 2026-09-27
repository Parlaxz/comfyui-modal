#!/usr/bin/env python
"""Minimal smoke runner for the source-concurrency probe (extent-unique).

Four calls only: H100 forward, H100 reverse, RTX forward, RTX reverse.
Each call runs the whole N sweep with unique, never-reused 128 MiB extents.

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
_MIB = 1024 ** 2
_ORDERS = ("forward", "reverse")


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

    out_dir = _ROOT / "source_conc_runs"
    out_dir.mkdir(exist_ok=True)
    results: dict[tuple[str, str], Any] = {}
    for family in ("h100", "rtx"):
        for order in _ORDERS:
            attempt = f"conc-{family}-{order}"
            fn = modal.Function.from_name(_APP, f"run_source_conc_{family}")
            print(f"[conc] invoking {attempt} ...", flush=True)
            result = fn.remote(attempt_id=attempt, order=order)
            results[(family, order)] = result
            (out_dir / f"{attempt}.json").write_text(
                json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8"
            )
            print(f"[conc] {attempt} status={result.get('status')} error={result.get('error')}",
                  flush=True)

    header = ("GPU | order | N | useful MiB | mean ms | median ms | max ms | "
              "dispatch skew ms | release wave ms | syscall envelope ms | "
              "release GB/s | syscall-envelope GB/s | status")
    print()
    print(header)
    print("|".join(["---"] * 13))
    for family in ("h100", "rtx"):
        for order in _ORDERS:
            result = results[(family, order)]
            if result.get("status") != "ok":
                print(f"{family} | {order} | ERROR | {result.get('error')}")
                continue
            for batch in result.get("batches") or []:
                status = "SCHEDULER_CONFOUNDED" if batch.get("scheduler_confounded") else "ok"
                print(
                    f"{family} | {order} | {batch['n']} | "
                    f"{batch['useful_bytes'] / _MIB:.1f} | {batch['mean_ms']:.3f} | "
                    f"{batch['median_ms']:.3f} | {batch['max_ms']:.3f} | "
                    f"{batch['dispatch_skew_ms']:.3f} | "
                    f"{batch['release_wave_makespan_ms']:.3f} | "
                    f"{batch['syscall_envelope_ms']:.3f} | "
                    f"{(batch['release_decimal_gbps'] or 0.0):.3f} | "
                    f"{(batch['syscall_envelope_decimal_gbps'] or 0.0):.3f} | {status}"
                )
    print()
    for family in ("h100", "rtx"):
        for order in _ORDERS:
            result = results[(family, order)]
            if result.get("status") != "ok":
                continue
            fi = result.get("file_identity") or {}
            cfg = result.get("config") or {}
            env = result.get("env") or {}
            print(f"--- {family}/{order} ---")
            print(f"  observed_gpu={result.get('observed_gpu')} requested_gpu={result.get('requested_gpu')}")
            print(f"  provider={result.get('provider')} region={result.get('region')}")
            print(f"  container_session_id={result.get('container_session_id')}")
            print(f"  resolved_path={result.get('resolved_path')}")
            print(f"  file_size={fi.get('size')} st_dev={fi.get('st_dev')} st_ino={fi.get('st_ino')}")
            print(f"  read_bytes={cfg.get('read_bytes')} order={cfg.get('order')} "
                  f"extent_first_block_by_n={cfg.get('extent_first_block_by_n')} "
                  f"total_blocks_used={cfg.get('total_blocks_used')}")
            print(f"  syscall_impl={env.get('syscall_impl')} preadv_available={env.get('preadv_available')}")
            for batch in result.get("batches") or []:
                print(f"  N={batch['n']:>2} blocks={batch['block_range']} "
                      f"offsets={batch['offsets']} "
                      f"distinct={batch['ranges_distinct_and_non_overlapping']} "
                      f"full={batch['all_full_length']} "
                      f"skew_ms={batch['dispatch_skew_ms']:.3f} "
                      f"release_to_first_enter_ms={batch['release_to_first_enter_ms']:.3f} "
                      f"preadv_ms={[round(v, 3) for v in batch['preadv_ms']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
