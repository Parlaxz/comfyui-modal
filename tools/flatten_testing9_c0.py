#!/usr/bin/env python3
"""Flatten retained TESTING9 C0 Golden artifacts into operation evidence."""

from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any

ROOT = Path("artifacts/phase_p1_parallel_golden_v1")
OUT = Path("artifacts/testing9_c0_phase2")
APPS = {
    "testing9-c0-mmap-fresh": "fresh",
    "testing9-c0-mmap-whole": "whole",
    "testing9-c0-mmap-epoch": "epoch",
}
MODEL_NAMES = {
    "qwen_3_4b.safetensors": "CLIP",
    "z_image_turbo_bf16.safetensors": "UNET",
}


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _models_from_attempt(data: dict[str, Any]):
    for item in _walk(data):
        if not isinstance(item, dict):
            continue
        source_detail = item.get("source_detail")
        path = item.get("path")
        if not isinstance(source_detail, dict) or path not in MODEL_NAMES:
            continue
        yield MODEL_NAMES[path], path, source_detail, item


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def flatten() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runs: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    for manifest_path in sorted(ROOT.glob("cohort_2026-09-29_*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        app = str(manifest.get("target", {}).get("app_name") or "")
        if app not in APPS:
            continue
        attempt_path = manifest_path.parent / "attempt_0.json"
        if not attempt_path.is_file():
            continue
        attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
        identity = attempt.get("identity") or {}
        run_id = manifest_path.parent.name
        arm = APPS[app]
        for model, filename, detail, parent in _models_from_attempt(attempt):
            reader = detail.get("reader") or {}
            phases = reader.get("mmap_read_phases") or {}
            source_records = (
                phases.get("mmap_read_records")
                or phases.get("source_touch_copy_records")
                or []
            )
            traces = detail.get("window_trace") or []
            if not source_records:
                source_records = [item for item in traces if isinstance(item, dict)]
            trace_by_key = {
                (int(t.get("producer_id", -1)), int(t.get("source_offset", t.get("offset", -1)))): t
                for t in traces if isinstance(t, dict)
            }
            record_by_key = {
                (int(r.get("producer_id", -1)), int(r.get("source_offset", -1))): r
                for r in source_records if isinstance(r, dict)
            }
            source_wall = _number(parent.get("source_wall_ms"))
            source_gbps = _number(parent.get("source_gbps"))
            runs.append({
                "run": run_id,
                "app": app,
                "arm": arm,
                "model": model,
                "filename": filename,
                "provider": identity.get("cloud"),
                "region": identity.get("region"),
                "gpu": identity.get("gpu"),
                "source_wall_ms": source_wall,
                "source_gbps": source_gbps,
                "correctness": manifest.get("valid_count") == 1,
                "operation_count": len(source_records),
                "runtime_markers": (detail.get("arena_ensure") or {}).get("child_ready_evidence", {}).get("runtime_markers"),
            })
            previous_epoch_by_worker: dict[int, int | None] = {}
            seen_mapping: set[tuple[int, int]] = set()
            seen_worker: set[int] = set()
            for ordinal, record in enumerate(source_records):
                if not isinstance(record, dict):
                    continue
                producer = int(record.get("producer_id", -1))
                offset = int(record.get("source_offset", -1))
                trace = trace_by_key.get((producer, offset), {})
                mapping_id = record.get("mmap_mapping_id")
                lifecycle_code = record.get("mmap_lifecycle_code")
                epoch_index = record.get("mmap_epoch_index")
                if epoch_index is None and offset >= 0:
                    epoch_index = offset // (1 << 30)
                mapping_key = (producer, int(mapping_id or -1))
                first_mapping = mapping_key not in seen_mapping
                seen_mapping.add(mapping_key)
                first_worker = producer not in seen_worker
                seen_worker.add(producer)
                epoch_index_int = int(epoch_index) if epoch_index is not None else None
                boundary = (
                    arm == "fresh"
                    or first_mapping
                    or (
                        arm == "epoch"
                        and previous_epoch_by_worker.get(producer) != epoch_index_int
                    )
                )
                previous_epoch_by_worker[producer] = epoch_index_int
                lease_request = _number(trace.get("lease_request_ns"))
                lease_acquire = _number(trace.get("lease_acquire_ns"))
                ready_publish = _number(trace.get("ready_publish_ns"))
                h2d_completion = _number(trace.get("h2d_completion_observed_ns"))
                slot_return = _number(trace.get("slot_return_ns"))
                op_start = _number(record.get("mmap_op_start_ns"))
                op_end = _number(record.get("mmap_op_end_ns"))
                op_ns = _number(record.get("mmap_op_ns"))
                if op_ns is None and op_start is not None and op_end is not None:
                    op_ns = max(0.0, op_end - op_start)
                mapped_copy_ns = _number(record.get("source_touch_copy_ns"))
                if mapped_copy_ns is None:
                    mapped_copy_ns = _number(record.get("mmap_memcpy_ns"))
                operations.append({
                    "run": run_id,
                    "app": app,
                    "arm": arm,
                    "model": model,
                    "filename": filename,
                    "provider": identity.get("cloud"),
                    "region": identity.get("region"),
                    "gpu": identity.get("gpu"),
                    "worker": producer,
                    "reader_pid": record.get("reader_pid"),
                    "offset": offset,
                    "length": record.get("returned_bytes"),
                    "ordinal": ordinal,
                    "mapping_id": mapping_id,
                    "lifecycle_code": lifecycle_code,
                    "epoch_index": epoch_index_int,
                    "first_operation_worker": first_worker,
                    "first_operation_mapping": first_mapping,
                    "mapping_boundary": boundary,
                    "mmap_ms": _number(record.get("mmap_map_ns")) and float(record["mmap_map_ns"]) / 1e6,
                    "mapped_access_plus_memcpy_ms": mapped_copy_ns / 1e6 if mapped_copy_ns is not None else None,
                    "munmap_ms": _number(record.get("mmap_munmap_ns")) and float(record["mmap_munmap_ns"]) / 1e6,
                    "pipe_rtt_ms": _number(record.get("mmap_pipe_rtt_ns")) and float(record["mmap_pipe_rtt_ns"]) / 1e6,
                    "child_operation_ms": op_ns / 1e6 if op_ns is not None else None,
                    "slot_wait_ms": ((lease_acquire - lease_request) / 1e6) if lease_request is not None and lease_acquire is not None else None,
                    "h2d_completion_wait_ms": ((slot_return - ready_publish) / 1e6) if slot_return is not None and ready_publish is not None else None,
                    "source_to_ready_ms": ((trace.get("ready_observed_ns") - lease_request) / 1e6) if isinstance(trace.get("ready_observed_ns"), (int, float)) and lease_request is not None else None,
                    "h2d_submit_to_completion_ms": ((h2d_completion - trace.get("h2d_submit_ns")) / 1e6) if isinstance(trace.get("h2d_submit_ns"), (int, float)) and h2d_completion is not None else None,
                    "is_stall_100ms": bool(op_ns is not None and op_ns > 100e6),
                    "is_stall_250ms": bool(op_ns is not None and op_ns > 250e6),
                    "is_stall_500ms": bool(op_ns is not None and op_ns > 500e6),
                    "is_stall_1000ms": bool(op_ns is not None and op_ns > 1000e6),
                })
    return runs, operations


def main() -> int:
    runs, operations = flatten()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase2_runs.json").write_text(json.dumps(runs, indent=2, sort_keys=True), encoding="utf-8")
    (OUT / "phase2_operations.json").write_text(json.dumps(operations, indent=2, sort_keys=True), encoding="utf-8")
    for name, rows in (("phase2_runs.csv", runs), ("phase2_operations.csv", operations)):
        with (OUT / name).open("w", newline="", encoding="utf-8") as handle:
            fields = sorted({key for row in rows for key in row})
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    summary: dict[str, Any] = {"runs": len(runs), "operations": len(operations), "groups": {}}
    for arm in ("fresh", "whole", "epoch"):
        for model in ("CLIP", "UNET"):
            rows = [r for r in runs if r["arm"] == arm and r["model"] == model]
            walls = [float(r["source_wall_ms"]) for r in rows if r.get("source_wall_ms") is not None]
            gbps = [float(r["source_gbps"]) for r in rows if r.get("source_gbps") is not None]
            ops = [r for r in operations if r["arm"] == arm and r["model"] == model]
            if not walls:
                continue
            summary["groups"][f"{arm}_{model}"] = {
                "n": len(walls),
                "source_wall_mean_ms": statistics.mean(walls),
                "source_wall_median_ms": statistics.median(walls),
                "source_wall_p95_ms": sorted(walls)[max(0, math.ceil(0.95 * len(walls)) - 1)],
                "source_gbps_median": statistics.median(gbps) if gbps else None,
                "operation_count": len(ops),
                "operation_stalls": {
                    threshold: sum(1 for op in ops if op[key])
                    for threshold, key in (("100ms", "is_stall_100ms"), ("250ms", "is_stall_250ms"), ("500ms", "is_stall_500ms"), ("1000ms", "is_stall_1000ms"))
                },
            }
    (OUT / "phase2_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
