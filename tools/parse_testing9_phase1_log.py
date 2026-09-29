#!/usr/bin/env python3
"""Preserve and summarize the completed TESTING9 Phase 1 console log."""

from __future__ import annotations

import csv
import json
import re
import statistics
from pathlib import Path

LINE = re.compile(
    r"\[(?P<ordinal>\d+)/(?P<total>\d+)\] (?P<arm>.+?) workers=(?P<workers>[14]) "
    r"sample=(?P<sample>\d+) steady=(?P<steady>[0-9.]+) ms"
)
ARM_NAMES = {
    "THREAD->PRIVATE": "thread_private",
    "THREAD->SHARED": "thread_shared",
    "PROCESS->PRIVATE": "process_private",
    "PROCESS->SHARED": "process_shared",
    "FRESH PROCESS/MAPPING->SHARED": "fresh_process_mapping_shared",
}


def main() -> int:
    root = Path("artifacts")
    source = root / "testing9Phase1.txt"
    if not source.is_file():
        raise SystemExit(f"missing {source}")
    rows = []
    for line in source.read_text(encoding="utf-8").splitlines():
        match = LINE.search(line)
        if not match:
            continue
        row = match.groupdict()
        row.update({
            "ordinal": int(row["ordinal"]),
            "total_expected": int(row["total"]),
            "workers": int(row["workers"]),
            "sample": int(row["sample"]),
            "steady_ms": float(row["steady"]),
            "arm_key": ARM_NAMES[row["arm"]],
            "source": str(source),
            "gpu_runtime": "H100 / gVisor (per supplied run context)",
            "first_copy_detail": "not present in supplied console log",
        })
        rows.append(row)
    out = root / "testing9_phase1"
    out.mkdir(parents=True, exist_ok=True)
    (out / "phase1_samples.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    with (out / "phase1_samples.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["ordinal", "arm_key", "arm", "workers", "sample", "steady_ms", "gpu_runtime", "first_copy_detail"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    summary = {"source": str(source), "sample_count": len(rows), "expected_count": 300, "groups": {}}
    for arm_key in ARM_NAMES.values():
        for workers in (1, 4):
            values = [r["steady_ms"] for r in rows if r["arm_key"] == arm_key and r["workers"] == workers]
            if not values:
                continue
            ordered = sorted(values)
            summary["groups"][f"{arm_key}/{workers}"] = {
                "n": len(values),
                "steady_ms_mean": statistics.mean(values),
                "steady_ms_median": statistics.median(values),
                "steady_ms_p90": ordered[max(0, int(0.90 * len(ordered)) - 1)],
                "steady_ms_p95": ordered[max(0, int(0.95 * len(ordered)) - 1)],
                "steady_ms_min": min(values),
                "steady_ms_max": max(values),
                "steady_ms_stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
                "steady_gib_per_s": (128 / (statistics.median(values) / 1000.0)),
                "over_250ms": sum(v > 250 for v in values),
                "over_500ms": sum(v > 500 for v in values),
                "over_1000ms": sum(v > 1000 for v in values),
            }
    (out / "phase1_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
