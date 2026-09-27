#!/usr/bin/env python
"""Full-file source geometry sweep: 4 read sizes x 3 QDs x 2 GPUs = 24 runs.

Each run gets its OWN fresh container (one remote call per run) and reads the
entire CLIP file exactly once.  The two GPU families run in parallel; runs
within a family are serial.

Raw measurements only.  No tuning, no repeats.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_APP = "sept-clip-source-race-oracle"
_MIB = 1024 ** 2
_READ_MIBS = (32, 64, 128, 256)
_QDS = (2, 4, 8)
_FAMILIES = ("h100", "rtx")


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


def _run_family(family: str, out_dir: Path) -> list[dict[str, Any]]:
    import modal

    fn = modal.Function.from_name(_APP, f"run_fullfile_{family}")
    produced: list[dict[str, Any]] = []
    for read_mib in _READ_MIBS:
        for qd in _QDS:
            attempt = f"{family}-r{read_mib}-qd{qd}"
            path = out_dir / f"{attempt}.json"
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                    if existing.get("status") == "ok":
                        print(f"[ff] skip {attempt} (artifact exists)", flush=True)
                        produced.append(existing)
                        continue
                except Exception:
                    pass
            print(f"[ff] start {attempt}", flush=True)
            try:
                result = fn.remote(read_mib=read_mib, qd=qd, attempt_id=attempt)
                if not isinstance(result, dict):
                    raise RuntimeError(f"returned {type(result).__name__}")
            except Exception as exc:
                result = {"status": "error", "error": f"{type(exc).__name__}:{exc}",
                          "attempt_id": attempt}
            path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str),
                            encoding="utf-8")
            produced.append(result)
            print(f"[ff] done {attempt} status={result.get('status')} "
                  f"gbps={result.get('full_file_decimal_gbps')}", flush=True)
    return produced


def main() -> int:
    workspace = _workspace()
    os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])

    out_dir = _ROOT / "source_fullfile_runs"
    out_dir.mkdir(exist_ok=True)

    results: dict[str, list[dict[str, Any]]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(_FAMILIES)) as pool:
        futures = {pool.submit(_run_family, family, out_dir): family for family in _FAMILIES}
        for future in concurrent.futures.as_completed(futures):
            family = futures[future]
            try:
                results[family] = future.result()
            except Exception:
                print(f"[ff] family {family} failed:\n{traceback.format_exc()}", flush=True)
                results[family] = []

    header = ("GPU | Read MiB | QD | Reads | Full-file wall ms | GB/s | Mean preadv ms | Median | "
              "P95 | Max | >=250 | >=500 | >=1000 | Median refill gap")
    print()
    print(header)
    print("|".join(["---"] * 14))
    for family in _FAMILIES:
        for result in sorted(results.get(family, []),
                             key=lambda r: (r.get("config", {}).get("read_mib", 0),
                                            r.get("config", {}).get("qd", 0))):
            if result.get("status") != "ok":
                print(f"{family} | ERROR | {result.get('error')}")
                continue
            cfg = result.get("config") or {}
            th = result.get("thresholds") or {}
            print(
                f"{family} | {cfg.get('read_mib')} | {cfg.get('qd')} | "
                f"{result.get('physical_reads')} | {result.get('full_file_wall_ms'):.1f} | "
                f"{(result.get('full_file_decimal_gbps') or 0.0):.3f} | "
                f"{result.get('mean_ms'):.3f} | {result.get('median_ms'):.3f} | "
                f"{result.get('p95_ms'):.3f} | {result.get('max_ms'):.3f} | "
                f"{th.get('ge_250')} | {th.get('ge_500')} | {th.get('ge_1000')} | "
                f"{(result.get('median_refill_gap_ms') or 0.0):.3f}"
            )

    for family in _FAMILIES:
        print()
        print(f"{family.upper()} full-file GB/s:")
        print("| | QD2 | QD4 | QD8 |")
        print("|---|---|---|---|")
        index = {
            (r["config"]["read_mib"], r["config"]["qd"]): r
            for r in results.get(family, []) if r.get("status") == "ok"
        }
        for read_mib in _READ_MIBS:
            cells = []
            for qd in _QDS:
                entry = index.get((read_mib, qd))
                cells.append("-" if not entry else f"{entry['full_file_decimal_gbps']:.3f}")
            print(f"| {read_mib} MiB | " + " | ".join(cells) + " |")

    for family in _FAMILIES:
        print()
        for result in results.get(family, []):
            if result.get("status") != "ok":
                continue
            cfg = result.get("config") or {}
            cov = result.get("coverage") or {}
            print(f"--- {family} read={cfg.get('read_mib')}MiB qd={cfg.get('qd')} ---")
            print(f"  observed_gpu={result.get('observed_gpu')} provider={result.get('provider')} "
                  f"region={result.get('region')}")
            print(f"  container_session_id={result.get('container_session_id')}")
            print(f"  file={result.get('resolved_path')} size={(result.get('file_identity') or {}).get('size')} "
                  f"st_dev={(result.get('file_identity') or {}).get('st_dev')} "
                  f"st_ino={(result.get('file_identity') or {}).get('st_ino')}")
            print(f"  syscall={(result.get('env') or {}).get('syscall_impl')} "
                  f"reads={result.get('physical_reads')} covered={result.get('covered_bytes')} "
                  f"useful={result.get('useful_bytes')} once={cov.get('covers_entire_file_exactly_once')} "
                  f"nonoverlap={cov.get('ranges_non_overlapping')} partial_final={cov.get('final_block_is_partial')}")
            print(f"  qd_min={result.get('effective_qd_min_in_span')} "
                  f"qd_max={result.get('effective_qd_max_in_span')} "
                  f"fell_below={result.get('effective_qd_fell_below_qd')} "
                  f"max_refill_gap={result.get('max_refill_gap_ms'):.3f}")
            for name, group in (result.get("progress") or {}).items():
                if not group:
                    continue
                print(f"    {name}: reads={group['reads']} GBps={group['decimal_gbps']:.3f} "
                      f"mean={group['mean_ms']:.3f} median={group['median_ms']:.3f} "
                      f"max={group['max_ms']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
