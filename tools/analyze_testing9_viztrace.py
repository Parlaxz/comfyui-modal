#!/usr/bin/env python3
"""Analyze the retained TESTING9 parent/child C0 diagnostic request."""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ATTEMPT = Path("artifacts/phase_p1_parallel_golden_v1/cohort_2026-09-29_07-17-52_681449/attempt_0.json")
OUT = Path("artifacts/testing9_viztrace")


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _pct(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[max(0, min(len(values) - 1, int(round((len(values) - 1) * fraction))))]


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "median_ms": statistics.median(values),
        "p90_ms": _pct(values, 0.90),
        "p95_ms": _pct(values, 0.95),
        "p99_ms": _pct(values, 0.99),
        "max_ms": max(values),
        "over_50ms": sum(v > 50 for v in values),
        "over_100ms": sum(v > 100 for v in values),
        "over_250ms": sum(v > 250 for v in values),
        "over_500ms": sum(v > 500 for v in values),
        "over_1000ms": sum(v > 1000 for v in values),
    }


def _events(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in _walk(data)
        if isinstance(item, dict) and isinstance(item.get("name"), str)
        and isinstance(item.get("monotonic_ns"), (int, float))
    ]


def main() -> int:
    data = json.loads(ATTEMPT.read_text(encoding="utf-8"))
    model_rows: dict[str, dict[str, Any]] = {}
    traces_by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in _walk(data):
        if not isinstance(item, dict) or not isinstance(item.get("source_detail"), dict):
            continue
        path = item.get("path")
        if path == "qwen_3_4b.safetensors":
            model = "CLIP"
        elif path == "z_image_turbo_bf16.safetensors":
            model = "UNET"
        else:
            continue
        detail = item["source_detail"]
        traces = [row for row in detail.get("window_trace", []) if isinstance(row, dict)]
        traces_by_model[model].extend(traces)
        model_rows[model] = {
            "path": path,
            "source_wall_ms": item.get("source_wall_ms"),
            "total_load_ms": item.get("total_load_ms"),
            "source_gbps": item.get("source_gbps"),
            "gpu_ready_tail_ms": item.get("gpu_ready_tail_ms"),
            "source_detail": detail,
        }
    event_rows = _events(data)
    event_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in event_rows:
        event_by_name[event["name"]].append(event)
    output: dict[str, Any] = {
        "source_artifact": str(ATTEMPT),
        "trace_bundle": {
            "status": "unavailable_from_volume",
            "reason": "retained full_trace_artifact points to a missing remote Volume path",
            "parent_event_artifact_used": True,
            "child_viztracer_raw_bundle_present": False,
        },
        "identity": data.get("identity"),
        "models": {},
        "overlap": {},
    }
    for model, rows in traces_by_model.items():
        mapped = [float(r["mmap_map_ns"]) / 1e6 for r in rows if isinstance(r.get("mmap_map_ns"), (int, float))]
        copied = [float(r.get("mmap_memcpy_ns", r.get("source_touch_copy_ns"))) / 1e6 for r in rows if isinstance(r.get("mmap_memcpy_ns", r.get("source_touch_copy_ns")), (int, float))]
        unmapped = [float(r["mmap_munmap_ns"]) / 1e6 for r in rows if isinstance(r.get("mmap_munmap_ns"), (int, float))]
        pipe = [float(r["mmap_pipe_rtt_ns"]) / 1e6 for r in rows if isinstance(r.get("mmap_pipe_rtt_ns"), (int, float))]
        control = [
            (float(r["ready_observed_ns"]) - float(r["control_submit_ns"])) / 1e6
            for r in rows
            if isinstance(r.get("ready_observed_ns"), (int, float))
            and isinstance(r.get("control_submit_ns"), (int, float))
        ]
        lease = [
            (float(r["lease_acquire_ns"]) - float(r["lease_request_ns"])) / 1e6
            for r in rows
            if isinstance(r.get("lease_acquire_ns"), (int, float))
            and isinstance(r.get("lease_request_ns"), (int, float))
        ]
        h2d = [
            (float(r["slot_return_ns"]) - float(r["ready_publish_ns"])) / 1e6
            for r in rows
            if isinstance(r.get("slot_return_ns"), (int, float))
            and isinstance(r.get("ready_publish_ns"), (int, float))
        ]
        intervals = sorted(
            (float(r["memcpy_start_ns"]) / 1e6, float(r["memcpy_end_ns"]) / 1e6, int(r.get("reader", -1)))
            for r in rows
            if isinstance(r.get("memcpy_start_ns"), (int, float))
            and isinstance(r.get("memcpy_end_ns"), (int, float))
        )
        if intervals:
            source_start = min(start for start, _end, _reader in intervals)
            source_end = max(end for _start, end, _reader in intervals)
            points = {source_start, source_end}
            for start, end, _reader in intervals:
                points.add(start)
                points.add(end)
            ordered = sorted(points)
            histogram = Counter()
            reader_busy_ms = Counter()
            for left, right in zip(ordered, ordered[1:]):
                active = [reader for start, end, reader in intervals if start <= left and end >= right]
                duration = right - left
                histogram[len(active)] += duration
                for reader in set(active):
                    reader_busy_ms[str(reader)] += duration
            span = source_end - source_start
            concurrency = {
                str(level): {
                    "ms": duration,
                    "fraction": duration / span if span else None,
                }
                for level, duration in sorted(histogram.items())
            }
            effective = sum(end - start for start, end, _reader in intervals) / span if span else None
        else:
            concurrency = {}
            reader_busy_ms = {}
            effective = None
        row = dict(model_rows[model])
        row.update({
            "operation_count": len(rows),
            "mmap_ms": _summary(mapped),
            "mapped_access_plus_memcpy_ms": _summary(copied),
            "munmap_ms": _summary(unmapped),
            "pipe_round_trip_ms": _summary(pipe),
            "control_submit_to_ready_ms": _summary(control),
            "lease_wait_ms": _summary(lease),
            "h2d_submit_to_slot_return_ms": _summary(h2d),
            "active_reader_time_weighted": concurrency,
            "effective_mapped_copy_concurrency": effective,
            "reader_busy_ms": dict(reader_busy_ms),
            "mapping_ids_by_reader": {
                str(reader): sorted({r.get("mmap_mapping_id") for r in rows if int(r.get("reader", -1)) == reader})
                for reader in sorted({int(r.get("reader", -1)) for r in rows})
            },
        })
        output["models"][model] = row
    for name in ("clip_forward_start", "clip_forward_end", "golden_model_load_waterfall", "golden_model_load_waterfall_total", "unet_skeleton_patcher_created", "clip_unet_overlap"):
        output["overlap"][name] = event_by_name.get(name, [])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "viztrace_parent_child_summary.json").write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
