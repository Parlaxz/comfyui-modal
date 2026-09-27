#!/usr/bin/env python
"""Serial same-deployment A/B runner for the C9 bare loop isolation."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import run_c9_recovery as c9


async def invoke(function, item, arm):
    remote = getattr(function, "remote", None)
    aio = getattr(remote, "aio", None)
    if not callable(aio):
        raise RuntimeError("C9 isolation requires Modal async invocation")
    value = cast(Any, aio)(item["role"], item["model_name"], item["qd"], item["attempt_id"], arm)
    value = await cast(Any, value)
    return value


def valid(result, item, arm):
    if arm == "source_only":
        return c9.validate_c9_result(result, item)
    failures = []
    if not isinstance(result, dict) or result.get("status") != "ok":
        failures.append("status_not_ok")
    if result.get("arm") != "bare_loop":
        failures.append("arm_not_bare_loop")
    if result.get("role") != item["role"] or result.get("model_name") != item["model_name"]:
        failures.append("model_identity_mismatch")
    if result.get("configured_source_qd") != item["qd"]:
        failures.append("qd_mismatch")
    if result.get("source_block_bytes") != c9.BLOCK_BYTES:
        failures.append("block_bytes_mismatch")
    if result.get("coverage", {}).get("ok") is not True:
        failures.append("coverage_failed")
    if result.get("byte_reconciliation", {}).get("returned_equals_expected") is not True:
        failures.append("byte_validation_failed")
    if result.get("C9_TOTAL_WALL_MS", 0) <= 0:
        failures.append("timing_missing")
    if result.get("timing_boundary", {}).get("name") != "THREAD_START_TO_JOIN_WALL":
        failures.append("timing_boundary_mismatch")
    if result.get("pinned_host") is not True or result.get("buffer_type") != "pytorch_pinned_host":
        failures.append("pinning_failed")
    return failures


async def main_async(args):
    out = Path(args.report_dir)
    out.mkdir(parents=True, exist_ok=True)
    function = c9._function_from_modal(args.app, args.env)
    rows: list[dict[str, Any]] = []
    for arm in ("bare_loop", "source_only"):
        arm_dir = out / arm
        arm_dir.mkdir(exist_ok=True)
        for run in range(1, args.runs + 1):
            item = {
                "role": "unet",
                "model_name": c9.MODELS["unet"],
                "qd": 8,
                "attempt_id": f"{arm}_R{run}",
            }
            started = time.time()
            result = await invoke(function, item, arm)
            failures = valid(result, item, arm)
            artifact = dict(result)
            artifact.update({"arm_requested": arm, "run": run, "classification": "ELIGIBLE" if not failures else "DNF", "runner_started_at_epoch": started})
            if failures:
                artifact["validation_failures"] = failures
            path = arm_dir / f"unet_qd8_R{run}.json"
            path.write_text(json.dumps(artifact, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
            rows.append(artifact)
    values = {}
    for arm in ("bare_loop", "source_only"):
        eligible = [row["C9_TOTAL_WALL_MS"] for row in rows if row["arm_requested"] == arm and row["classification"] == "ELIGIBLE"]
        values[arm] = {"runs_ms": eligible, "median_ms": statistics.median(eligible) if eligible else None, "effective_gbps": [row.get("effective_gbps") for row in rows if row["arm_requested"] == arm and row["classification"] == "ELIGIBLE"]}
    (out / "summary.json").write_text(json.dumps({"experiment": "c9_bare_loop_isolation", "workspace": "Testing 7", "cpu": 12, "gpu": "rtx-pro-6000", "qd": 8, "block_bytes": c9.BLOCK_BYTES, "values": values, "rows": [{"arm": row["arm_requested"], "run": row["run"], "classification": row["classification"], "C9_TOTAL_WALL_MS": row.get("C9_TOTAL_WALL_MS"), "PHYSICAL_READ_SPAN_MS": row.get("PHYSICAL_READ_SPAN_MS"), "effective_gbps": row.get("effective_gbps"), "provider": (row.get("identity") or {}).get("provider"), "region": (row.get("identity") or {}).get("region")} for row in rows]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if all(row["classification"] == "ELIGIBLE" for row in rows) else 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--app", default=c9.APP_DEFAULT)
    parser.add_argument("--env", default="")
    parser.add_argument("--runs", type=int, default=4)
    args = parser.parse_args()
    if args.runs != 4:
        parser.error("isolation requires exactly 4 runs per arm")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
