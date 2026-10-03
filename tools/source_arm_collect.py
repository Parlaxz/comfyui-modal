"""Collect N true-cold Golden source-arm runs and report the raw distribution.

Rank an arm on its median, not on a single run.  Cold source throughput on this
H100 path varies run to run by tens of percent, so one run per arm is not
evidence of anything.

Usage:
    python tools/source_arm_collect.py --worker-kind thread --lifecycle whole --runs 3
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROFILE = "golden_p1_parallel_c0_source_h100"
APP = "batch-c0-source-h100"
EXPECTED_SHA = "3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577"


def v2ctl(*args: str) -> int:
    return subprocess.call(
        [sys.executable, str(REPO / "tools" / "v2ctl.py"), *args],
        cwd=str(REPO),
    )


def deploy(worker_kind: str, lifecycle: str) -> bool:
    for _ in range(6):
        log = subprocess.run(
            [
                sys.executable, str(REPO / "tools" / "v2ctl.py"),
                "--profile", PROFILE, "--app", APP,
                "--set", f"COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE={lifecycle}",
                "--set", f"COMFYMODAL_GOLDEN_C0_SOURCE_WORKER_KIND={worker_kind}",
                "golden", "deploy",
            ],
            cwd=str(REPO), capture_output=True, text=True,
        )
        if "deployment_receipt=" in (log.stdout or "") + (log.stderr or ""):
            return True
    return False


def latest_attempt() -> dict:
    root = REPO / "artifacts" / "phase_p1_parallel_golden_v1"
    cohorts = sorted(
        (path for path in root.iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return json.loads((cohorts[0] / "attempt_0.json").read_text(encoding="utf-8"))


def extract(attempt: dict) -> dict:
    """Return per-model source metrics for one run."""
    out: dict = {
        "valid": attempt.get("valid"),
        "true_cold": attempt.get("true_cold"),
        "sha": ((attempt.get("validation") or {}).get("observed_output_shas") or [None])[0],
        "sha_ok": ((attempt.get("validation") or {}).get("observed_output_shas") or [None])[0]
        == EXPECTED_SHA,
        "models": [],
    }
    for event in (attempt.get("golden_telemetry") or {}).get("events") or []:
        fields = event.get("fields") or {}
        if "source_gbps" not in fields:
            continue
        detail = fields.get("source_detail") or {}
        evidence = (detail.get("arena_ensure") or {}).get("child_ready_evidence") or {}
        concurrency = detail.get("source_concurrency") or {}
        out["models"].append({
            "worker_kind": evidence.get("source_worker_kind"),
            "mmap_lifecycle": evidence.get("mmap_lifecycle"),
            "source_gbps": fields.get("source_gbps"),
            "source_wall_ms": fields.get("source_wall_ms"),
            "total_load_ms": fields.get("total_load_ms"),
            "go_offset_ms": fields.get("source_go_offset_ms"),
            "gpu_ready_tail_ms": fields.get("gpu_ready_tail_ms"),
            "blocks": concurrency.get("source_operations"),
            "eff_concurrency": concurrency.get("time_weighted_effective_concurrency"),
            "mmap_map_count": concurrency.get("mmap_map_count"),
            "pacer_violations": concurrency.get("pacer_gap_violation_count"),
        })
    return out


def summarise(rows: list[dict]) -> None:
    print("\n=== raw rows ===")
    for index, row in enumerate(rows):
        for model in row["models"]:
            print(
                f"  run{index} valid={row['valid']} cold={row['true_cold']} "
                f"sha_ok={row['sha_ok']} worker={model['worker_kind']} "
                f"life={model['mmap_lifecycle']} gbps={model['source_gbps']:.3f} "
                f"wall={model['source_wall_ms']:.0f}ms conc={model['eff_concurrency']:.2f} "
                f"tail={model['gpu_ready_tail_ms']}"
            )
    print("\n=== per-model distribution ===")
    for slot, label in ((0, "model[0]"), (1, "model[1]")):
        values = [
            row["models"][slot]["source_gbps"]
            for row in rows
            if row["valid"] and len(row["models"]) > slot
        ]
        if not values:
            continue
        print(
            f"  {label}: n={len(values)} median={statistics.median(values):.3f} "
            f"min={min(values):.3f} max={max(values):.3f} "
            f"spread={(max(values) - min(values)) / statistics.median(values) * 100:.0f}%"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-kind", default="thread", choices=("thread", "process"))
    parser.add_argument("--lifecycle", default="whole", choices=("fresh", "whole"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    if not deploy(args.worker_kind, args.lifecycle):
        print("DEPLOY FAILED (build context churn)")
        return 1
    common = [
        "--profile", PROFILE, "--app", APP,
        "--set", f"COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE={args.lifecycle}",
        "--set", f"COMFYMODAL_GOLDEN_C0_SOURCE_WORKER_KIND={args.worker_kind}",
    ]
    v2ctl(*common, "source-probe")
    rows = []
    for index in range(args.runs):
        print(f"--- run {index + 1}/{args.runs} ---")
        v2ctl(*common, "golden", "run")
        try:
            rows.append(extract(latest_attempt()))
        except Exception as exc:  # noqa: BLE001 - a failed run is data, not a crash
            print(f"  run {index} produced no usable artifact: {type(exc).__name__}")
    summarise(rows)
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
