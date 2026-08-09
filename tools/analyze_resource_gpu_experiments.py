"""Analyze resource/GPU experiment run artifacts into report-ready summaries.

Reads the ``run_*.json`` artifacts produced by ``tools/benchmark_v2_direct.py``
(via ``tools/run_resource_arm.py``) and computes per-arm:

- true-cold validity (restore_count == 1, request_count == 1, outputs present)
- timing boundaries with reconciled semantics:
    submission -> restore banner   = submission_to_remote_python_resume_ms
    restore banner -> first Python = restore_total_ms + restore_to_method_entry_ms
    platform restore               = restore_total_ms (restore() duration)
    application (python -> result) = restore_total_ms + restore_to_method_entry_ms
                                     + first_remote_event_to_final_result_ms
    submission -> result           = final_result_received.wall
                                     - modal_submission_attempt.wall  (local clocks)
    TWO-LANE / pre-sampler / sampling / VAE from the timing dict
- 50 ms telemetry aggregates (cpu source, average/peak cores, window peaks,
  RAM peak/p95) and per-stage resource attribution
- GPU identity / AWS region / attention-backend evidence from the trace

Usage:
    python tools/analyze_resource_gpu_experiments.py ^
        --arm ram28 --label "RAM 28 GiB" --runs <dir> ^
        [--warmup <dir>] [--out <summary.json>]

The summary JSON is consumed by the final report writer.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = int(pct / 100.0 * len(ordered) + 0.999999)
    idx = min(len(ordered) - 1, max(0, idx - 1))
    return ordered[idx]


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "p50": None, "p90": None, "max": None, "n": 0}
    return {
        "min": round(min(values), 1),
        "p50": round(percentile(values, 50.0) or 0.0, 1),
        "p90": round(percentile(values, 90.0) or 0.0, 1),
        "max": round(max(values), 1),
        "n": len(values),
    }


def _event_wall(events: list[dict[str, Any]], name: str, last: bool = False) -> int | None:
    found: int | None = None
    for ev in events:
        if isinstance(ev, dict) and ev.get("name") == name:
            wall = ev.get("wall_unix_ns")
            if isinstance(wall, int):
                found = wall
                if not last:
                    return wall
    return found


def analyze_run(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    result = data.get("result") or {}
    identity = data.get("identity") or {}
    timing = data.get("timing") or {}
    restore_timing = result.get("_restore_timing") or {}
    tel = result.get("resource_telemetry") or {}
    trace = result.get("trace") or {}
    events = trace.get("events") or []
    images = result.get("images") or []

    run: dict[str, Any] = {
        "file": path.name,
        "request_id": result.get("request_id") or data.get("request_id") or "",
    }

    # -- validity -----------------------------------------------------------
    failures: list[str] = []
    if int(identity.get("restore_count", -1)) != 1:
        failures.append(f"restore_count={identity.get('restore_count')}")
    if int(identity.get("request_count", -1)) != 1:
        failures.append(f"request_count={identity.get('request_count')}")
    if not images:
        failures.append("no images")
    if result.get("error"):
        failures.append(f"error={str(result.get('error'))[:120]}")
    run["valid"] = not failures
    run["invalid_reasons"] = failures
    run["region"] = identity.get("region") or ""
    run["cloud"] = identity.get("cloud") or ""
    gpu = identity.get("gpu") or (data.get("runtime_shape") or {}).get("gpu") or []
    if isinstance(gpu, list):
        run["gpu"] = [str(g) for g in gpu]
    else:
        run["gpu"] = str(gpu)

    # -- reconciled timing semantics ----------------------------------------
    sub_to_resume = _num(timing.get("submission_to_remote_python_resume_ms"))
    restore_total = _num(timing.get("restore_total_ms"))
    restore_to_entry = _num(timing.get("restore_to_method_entry_ms"))
    first_remote_to_result = _num(timing.get("first_remote_event_to_final_result_ms"))

    sub_to_result = None
    if events:
        submit_wall = _event_wall(events, "modal_submission_attempt")
        result_wall = _event_wall(events, "final_result_received", last=True)
        if submit_wall and result_wall:
            sub_to_result = (result_wall - submit_wall) / 1_000_000.0

    run["timing"] = {
        "submission_to_restore_banner_ms": sub_to_resume,
        "restore_total_ms": restore_total,
        "restore_banner_to_first_python_ms": (
            round((restore_total or 0) + (restore_to_entry or 0), 1)
            if restore_total is not None else None
        ),
        "python_resume_to_result_ms": (
            round((restore_total or 0) + (restore_to_entry or 0)
                  + (first_remote_to_result or 0), 1)
            if first_remote_to_result is not None else None
        ),
        "restore_end_to_result_ms": (
            round((restore_to_entry or 0) + (first_remote_to_result or 0), 1)
            if first_remote_to_result is not None else None
        ),
        "submission_to_result_ms": (
            round(sub_to_result, 1) if sub_to_result is not None else None
        ),
        "two_lane_ms": _num(timing.get("sampler_lane_wait_ms")),
        "pre_sampler_ms": _num(timing.get("pre_sampler_ms")),
        "sampling_ms": _num(timing.get("sampler_ms")),
        "vae_ms": _num(timing.get("vae_decode_ms")),
        "graph_activity_ms": _num(timing.get("graph_activity_ms")),
        "output_collection_ms": _num(timing.get("output_collection_ms")),
    }

    # -- telemetry ----------------------------------------------------------
    tel_out: dict[str, Any] = {"status": tel.get("status", "absent")}
    if tel.get("status") == "measured":
        cpu = tel.get("cpu") or {}
        ram = tel.get("ram") or {}
        tel_out.update({
            "samples": tel.get("samples"),
            "duration_ms": tel.get("duration_ms"),
            "cpu_source": cpu.get("source"),
            "average_cores": cpu.get("average_cores"),
            "peak_cores": cpu.get("peak_cores"),
            "p95_cores": cpu.get("p95_cores"),
            "window_peaks_ms": cpu.get("peak_cores_over_window_ms"),
            "ram_peak_bytes": ram.get("sampled_peak_bytes") or ram.get("cgroup_peak_bytes"),
            "ram_p95_bytes": ram.get("p95_bytes"),
            "ram_end_bytes": ram.get("end_bytes"),
            "stages": tel.get("stages") or {},
        })
    run["telemetry"] = tel_out

    # -- duplicate-H2D / residency evidence ---------------------------------
    h2d_loads = [
        ev for ev in events
        if isinstance(ev, dict) and ev.get("name", "").startswith("cpu_snapshot_unet_load")
    ]
    first_cuda = [
        ev for ev in events
        if isinstance(ev, dict) and ev.get("name") == "unet_first_cuda_op"
    ]
    run["evidence"] = {
        "unet_snapshot_load_event_count": len(h2d_loads),
        "unet_first_cuda_op": first_cuda[0].get("metadata") if first_cuda else None,
    }
    return run


def summarize(arm: str, label: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [r for r in runs if r["valid"]]
    invalid = [r for r in runs if not r["valid"]]

    def collect(key: str) -> list[float]:
        return [
            float(r["timing"][key]) for r in valid
            if r["timing"].get(key) is not None
        ]

    keys = [
        "submission_to_restore_banner_ms", "restore_total_ms",
        "restore_banner_to_first_python_ms", "python_resume_to_result_ms",
        "submission_to_result_ms", "two_lane_ms", "pre_sampler_ms",
        "sampling_ms", "vae_ms",
    ]
    timing_stats = {k: _stats(collect(k)) for k in keys}

    cores = [
        float(r["telemetry"]["average_cores"]) for r in valid
        if r["telemetry"].get("average_cores") is not None
    ]
    peak_cores = [
        float(r["telemetry"]["peak_cores"]) for r in valid
        if r["telemetry"].get("peak_cores") is not None
    ]
    ram_peak = [
        float(r["telemetry"]["ram_peak_bytes"]) for r in valid
        if r["telemetry"].get("ram_peak_bytes") is not None
    ]
    ram_p95 = [
        float(r["telemetry"]["ram_p95_bytes"]) for r in valid
        if r["telemetry"].get("ram_p95_bytes") is not None
    ]
    telemetry_stats: dict[str, Any] = {}
    if cores:
        telemetry_stats["average_cores"] = _stats(cores)
        telemetry_stats["peak_cores"] = _stats(peak_cores)
        telemetry_stats["ram_peak_bytes"] = _stats(ram_peak)
        telemetry_stats["ram_p95_bytes"] = _stats(ram_p95)
        cpu_sources = {r["telemetry"].get("cpu_source") for r in valid}
        telemetry_stats["cpu_source"] = sorted(s for s in cpu_sources if s)

    regions = sorted({r["region"] for r in valid})
    gpus = sorted({",".join(r["gpu"]) for r in valid})
    return {
        "arm": arm,
        "label": label,
        "runs_requested": len(runs),
        "valid": len(valid),
        "invalid": len(invalid),
        "invalid_details": [{"file": r["file"], "reasons": r["invalid_reasons"]} for r in invalid],
        "regions": regions,
        "gpu": gpus,
        "timing": timing_stats,
        "telemetry": telemetry_stats,
        "per_run": runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--runs", required=True, help="glob of run_*.json")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    files = sorted(glob.glob(args.runs))
    if not files:
        print(f"[analyze] no run files matched: {args.runs}")
        return 1
    runs = [analyze_run(Path(f)) for f in files]
    summary = summarize(args.arm, args.label, runs)
    out_path = Path(args.out) if args.out else ROOT / "comfymodal-data" / "benchmarks" / "resource_experiments" / f"{args.arm}_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"[analyze] {args.arm}: {summary['valid']}/{summary['runs_requested']} valid "
          f"regions={summary['regions']} gpu={summary['gpu']}")
    for k in ("submission_to_restore_banner_ms", "python_resume_to_result_ms",
              "submission_to_result_ms", "two_lane_ms", "sampling_ms", "vae_ms"):
        s = summary["timing"][k]
        print(f"  {k}: p50={s['p50']} p90={s['p90']} max={s['max']} n={s['n']}")
    if summary["telemetry"]:
        print(f"  telemetry: cores_avg_p50={summary['telemetry'].get('average_cores', {}).get('p50')} "
              f"cores_peak_p50={summary['telemetry'].get('peak_cores', {}).get('p50')} "
              f"ram_peak_p50_gb={round((summary['telemetry'].get('ram_peak_bytes', {}).get('p50') or 0) / 1e9, 2)} "
              f"ram_p95_p50_gb={round((summary['telemetry'].get('ram_p95_bytes', {}).get('p50') or 0) / 1e9, 2)} "
              f"source={summary['telemetry'].get('cpu_source')}")
    print(f"[analyze] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
