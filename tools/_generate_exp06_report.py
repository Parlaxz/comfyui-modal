"""Derive the Experiment 06 report from retained artifacts.

Importing this module is deliberately side-effect free.  Use ``main`` for the
legacy command-line behavior or call ``generate_report`` from a local tool.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import statistics
from typing import Any, Iterable


ROOT = pathlib.Path("unetClipExperimentsSeptember")
NEW_ROOTS = [
    ROOT / "06_source_only_runs",
    ROOT / "06_source_only_runs_batch1_clip",
    ROOT / "06_source_only_runs_batch2_unet_small",
    ROOT / "06_source_only_runs_batch3_unet_large",
    ROOT / "06_source_only_runs_clip_32_64",
    ROOT / "06_source_only_runs_clip_128_256",
    ROOT / "06_source_only_runs_unet_32_64",
    ROOT / "06_source_only_runs_unet_128_256",
]
REUSED_REPORT = ROOT / "05_qd2_qd4_qd8_additional10.json"
MD = ROOT / "06_source_block_qd_matrix_pure_source.md"
JSON_OUT = ROOT / "06_source_block_qd_matrix_pure_source.json"
CSV_OUT = ROOT / "06_source_block_qd_matrix_pure_source.csv"
CAMPAIGN_STATE = ROOT / "source_h2d_decoupling_campaign_state.json"
BLOCK_MIBS = (32, 64, 128, 256)
QDS = (1, 2, 4, 8)
ROLES = ("CLIP", "UNET")


def normalized_raw(path: pathlib.Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    fixed = data.get("fixed_config") or {}
    metrics = data.get("metrics") or {}
    proof = metrics.get("proof") or {}
    fallback = metrics.get("fallback") or {}
    block_bytes = fixed.get("source_block_bytes")
    qd = fixed.get("configured_qd")
    match = re.search(r"_R(\d+)(?:_A\d+)?$", str(data.get("attempt_id", "")))
    return {
        "attempt_id": data.get("attempt_id"), "role": str(data.get("role", "")).upper(), "model_name": data.get("model_name"),
        "arm": data.get("arm"), "source_only": data.get("source_only") is True,
        "block_mib": int(block_bytes / 1024 / 1024) if block_bytes else None,
        "block_bytes": block_bytes, "qd": qd,
        "nominal_outstanding_source_bytes": block_bytes * qd if block_bytes and qd else None,
        "round": int(match.group(1)) if match else None, "status": data.get("status"),
        "source_wall_ms": metrics.get("SOURCE_WALL_MS", data.get("SOURCE_WALL_MS")),
        "file_to_cuda_wall_ms": metrics.get("FILE_TO_CUDA_WALL_MS", data.get("FILE_TO_CUDA_WALL_MS")),
        "effective_gbps": metrics.get("effective_gbps", data.get("effective_gbps", data.get("effective_GBps"))),
        "source_bytes": metrics.get("source_bytes"), "source_read_count": metrics.get("source_read_count"),
        "achieved_mean_qd": metrics.get("achieved_mean_qd"), "achieved_max_qd": metrics.get("achieved_max_qd"),
        "syscall_union_ms": metrics.get("syscall_union_ms"), "h2d_wall_ms": metrics.get("H2D_WALL_MS"),
        "true_gpu_active_copy_ms": metrics.get("true_gpu_active_copy_ms"),
        "gpu_stream_span_ms": metrics.get("gpu_stream_span_ms"), "gpu_idle_ms": metrics.get("gpu_idle_ms"),
        "fallback_count": fallback.get("fallback_count", fallback.get("count", 0)),
        "proof": proof.get("E27_SOURCE_MECHANISM_PROVEN"),
        "failed_predicates": proof.get("e27_source_mechanism_failed_predicates") or [],
        "provider": (data.get("identity") or {}).get("provider"), "region": (data.get("identity") or {}).get("region"),
        "gpu": (data.get("identity") or {}).get("gpu"), "image_id": (data.get("identity") or {}).get("image_id"),
        "container_session_id": (data.get("identity") or {}).get("container_session_id"),
        "byte_validation": (data.get("byte_validation") or {}).get("ok") if isinstance(data.get("byte_validation"), dict) else data.get("byte_validation"),
        "model_construction": data.get("model_construction"), "raw_artifact": path.as_posix(), "error": data.get("error"),
    }


def normalized_reused(item: dict[str, Any]) -> dict[str, Any]:
    result = dict(item)
    result["block_mib"] = 256
    result["block_bytes"] = 256 * 1024 * 1024
    result["nominal_outstanding_source_bytes"] = result["block_bytes"] * result["qd"]
    result.setdefault("failed_predicates", [])
    result.setdefault("error", None)
    return result


def metric_stats(group: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [float(item[key]) for item in group if item.get(key) is not None]
    if not values:
        return {"n": 0, "values": [], "min": None, "max": None, "mean": None,
                "median": None, "sample_sd": None, "cv": None, "effective_gbps": None}
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    source_bytes = next((item.get("source_bytes") for item in group if item.get("source_bytes") is not None), None)
    return {"n": len(values), "values": values, "min": min(values), "max": max(values),
            "mean": statistics.mean(values), "median": statistics.median(values),
            "sample_sd": sd, "cv": sd / statistics.mean(values) if statistics.mean(values) else 0.0,
            "effective_gbps": source_bytes / statistics.median(values) / 1_000_000 if source_bytes else None}


def cell_rows(rows: list[dict[str, Any]], role: str, block_mib: int, qd: int) -> list[dict[str, Any]]:
    return sorted((item for item in rows if item["role"] == role and item["block_mib"] == block_mib and item["qd"] == qd), key=lambda item: item["round"] or 0)


def build_cells(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cells = []
    for role in ROLES:
        for block_mib in BLOCK_MIBS:
            for qd in QDS:
                group = cell_rows(rows, role, block_mib, qd)
                source = metric_stats(group, "source_wall_ms")
                ready = metric_stats(group, "file_to_cuda_wall_ms")
                achieved_mean_qd_values = [item["achieved_mean_qd"] for item in group if item.get("achieved_mean_qd") is not None]
                achieved_max_qd_values = [item["achieved_max_qd"] for item in group if item.get("achieved_max_qd") is not None]
                source_read_count_values = [item["source_read_count"] for item in group if item.get("source_read_count") is not None]
                gpu_active_copy_values = [item["true_gpu_active_copy_ms"] for item in group if item.get("true_gpu_active_copy_ms") is not None]
                cells.append({
                    "role": role, "block_mib": block_mib, "block_bytes": block_mib * 1024 * 1024, "qd": qd,
                    "nominal_outstanding_source_bytes": block_mib * qd * 1024 * 1024,
                    "source_wall_ms": source, "file_to_cuda_wall_ms": ready,
                    "achieved_mean_qd_values": achieved_mean_qd_values,
                    "achieved_mean_qd_mean": statistics.mean(achieved_mean_qd_values) if achieved_mean_qd_values else None,
                    "achieved_max_qd_values": achieved_max_qd_values,
                    "achieved_max_qd_max": max(achieved_max_qd_values, default=None),
                    "source_read_count_values": source_read_count_values,
                    "source_read_count_mean": statistics.mean(source_read_count_values) if source_read_count_values else None,
                    "gpu_active_copy_ms_values": gpu_active_copy_values,
                    "gpu_active_copy_ms_mean": statistics.mean(gpu_active_copy_values) if gpu_active_copy_values else None,
                    "gpu_active_copy_ms_median": statistics.median(gpu_active_copy_values) if gpu_active_copy_values else None,
                    "status_counts": {value: sum(item["status"] == value for item in group) for value in sorted({item["status"] for item in group})},
                    "proof_counts": {value: sum(item["proof"] == value for item in group) for value in sorted({item["proof"] for item in group})},
                    "providers_regions": sorted({f"{item['provider']}/{item['region']}" for item in group}),
                    "image_ids": sorted({item["image_id"] for item in group}),
                    "raw_artifacts": [item["raw_artifact"] for item in group],
                })
    return cells


def _matrix(cells: list[dict[str, Any]], first: str) -> list[dict[str, Any]]:
    return [{"role": cell["role"], "block_mib": cell["block_mib"], "qd": cell["qd"],
             "source_median_ms": cell["source_wall_ms"]["median"],
             "file_to_cuda_median_ms": cell["file_to_cuda_wall_ms"]["median"],
             "effective_gbps": cell["source_wall_ms"]["effective_gbps"]} for cell in cells]


def matrix_by_block(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _matrix(cells, "block")


def matrix_by_qd(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _matrix(cells, "qd")


def matrix_by_outstanding(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for role in ROLES:
        values = sorted({cell["nominal_outstanding_source_bytes"] for cell in cells if cell["role"] == role})
        for nominal in values:
            group = [cell for cell in cells if cell["role"] == role and cell["nominal_outstanding_source_bytes"] == nominal]
            result.append({"role": role, "nominal_outstanding_mib": nominal / 1024 / 1024,
                           "configurations": [f"{cell['block_mib']}x{cell['qd']}" for cell in group],
                           "source_medians_ms": {f"{cell['block_mib']}x{cell['qd']}": cell["source_wall_ms"]["median"] for cell in group},
                           "file_to_cuda_medians_ms": {f"{cell['block_mib']}x{cell['qd']}": cell["file_to_cuda_wall_ms"]["median"] for cell in group}})
    return result


def best_config(cells: list[dict[str, Any]], role: str) -> dict[str, Any]:
    candidates = [cell for cell in cells if cell["role"] == role and cell["source_wall_ms"]["median"] is not None]
    if not candidates:
        raise ValueError(f"no eligible observations for {role}")
    return min(candidates, key=lambda cell: cell["source_wall_ms"]["median"])


def fmt(value: Any, digits: int = 3) -> str:
    return "UNAVAILABLE" if value is None else f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def add_matrix_table(lines: list[str], title: str, rows: list[dict[str, Any]], first_headers: list[str]) -> None:
    """Compatibility helper retained for small local report customizations."""
    lines += [f"## {title}", "", "| " + " | ".join(first_headers + ["SOURCE median ms", "FILE_TO_CUDA median ms"]) + " |", "|" + "|".join("---" for _ in first_headers + ["s", "r"]) + "|"]
    for item in rows:
        lines.append("| " + " | ".join([str(item[header]) for header in first_headers] + [fmt(item.get("source_median_ms")), fmt(item.get("file_to_cuda_median_ms"))]) + " |")


def generate_report(
    new_roots: Iterable[pathlib.Path] = NEW_ROOTS,
    reused_report: pathlib.Path = REUSED_REPORT,
    md: pathlib.Path = MD,
    json_out: pathlib.Path = JSON_OUT,
    strict: bool = True,
    ledger_path: pathlib.Path = CAMPAIGN_STATE,
) -> dict[str, Any]:
    """Read retained evidence and write both report forms; never runs Modal."""
    new_rows = []
    for root in new_roots:
        for path in sorted(root.glob("*.json")):
            try:
                new_rows.append(normalized_raw(path))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                new_rows.append({"attempt_id": path.stem, "status": "invalid_json", "raw_artifact": path.as_posix(), "error": "invalid JSON"})
    new_valid = [item for item in new_rows if item.get("status") == "ok" and item.get("byte_validation") is True]
    new_invalid = [item for item in new_rows if item not in new_valid]
    reused_data = json.loads(reused_report.read_text(encoding="utf-8"))
    reused_rows = [normalized_reused(item) for item in reused_data.get("additional_observations", [])]
    # Historical integrated records remain available for comparison but never
    # satisfy the Phase-2 pure-source cohort.
    all_rows = [item for item in new_valid if item.get("source_only") is True]
    complete = len(all_rows) == 320 and all(len(cell_rows(all_rows, role, block, qd)) == 10 for role in ROLES for block in BLOCK_MIBS for qd in QDS)
    if strict and not complete:
        raise ValueError(f"incomplete Experiment 06 cohort: {len(all_rows)} eligible observations")
    cells = build_cells(all_rows)
    eligible_cells = [cell for cell in cells if cell["source_wall_ms"]["median"] is not None]
    best = {}
    best_two = {}
    for role in ROLES:
        candidates = [cell for cell in eligible_cells if cell["role"] == role]
        if candidates:
            ranked = sorted(candidates, key=lambda item: item["source_wall_ms"]["median"])
            def selected(item: dict[str, Any]) -> dict[str, Any]:
                return {"block_mib": item["block_mib"], "qd": item["qd"], "nominal_outstanding_mib": item["nominal_outstanding_source_bytes"] / 1024 / 1024, "source_median_ms": item["source_wall_ms"]["median"], "file_to_cuda_median_ms": item["file_to_cuda_wall_ms"]["median"], "effective_gbps": item["source_wall_ms"]["effective_gbps"], "n": item["source_wall_ms"]["n"]}
            best[role] = selected(ranked[0])
            best_two[role] = [selected(item) for item in ranked[:2]]
    report = {"experiment": "06_source_block_qd_matrix", "status": "COMPLETE" if complete else "IN_PROGRESS", "decision_metric": "SOURCE_WALL_MS", "secondary_metric": "EFFECTIVE_GBPS", "runner": "tools/run_exp04_source_ceiling.py", "source_only": True, "fixed_configuration": {"source_block_mib_values": list(BLOCK_MIBS), "qd_values": list(QDS), "aggregation_enabled": False, "model_construction": False, "cuda_used": False, "h2d_used": False, "full_golden_generation": False, "serial": True, "interleaving": "round -> block -> QD -> CLIP then UNET", "physical_syscall_telemetry": "every positioned read retains requested_bytes and returned_bytes"}, "cohort": {"requested_total": 320, "new_requested": 320, "new_attempts_retained": len(new_rows), "new_runtime_eligible": len(all_rows), "new_invalid": len(new_invalid), "reused_runtime_eligible": 0, "historical_integrated_runtime_eligible": len(reused_rows), "total_runtime_eligible": len(all_rows), "strict_proof_yes": None, "status_ok_and_bytes_valid": sum(item.get("status") == "ok" and item.get("byte_validation") is True for item in all_rows), "fallback_zero": None, "distinct_sessions": len({item.get("container_session_id") for item in all_rows}), "provider_regions": sorted({f"{item.get('provider')}/{item.get('region')}" for item in all_rows})}, "cells": cells, "performance_by_block_at_each_qd": matrix_by_block(cells), "performance_by_qd_at_each_block": matrix_by_qd(cells), "performance_by_nominal_outstanding_bytes": matrix_by_outstanding(cells), "equal_outstanding_byte_groups": [item for item in matrix_by_outstanding(cells) if item["nominal_outstanding_mib"] in (256, 512)], "best_source_configuration": best, "best_two_source_configurations": best_two, "observations": all_rows, "invalid_new_attempts": new_invalid, "raw_evidence_roots": [pathlib.Path(root).as_posix() for root in new_roots], "historical_integrated_evidence": reused_report.as_posix()}
    report.update({"worktree": "C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal", "branch": "TESTING2", "head": "UNAVAILABLE", "dirty_worktree": True, "app": "sept-unetclip-04-source-ceiling-oracle", "workspace": "UNAVAILABLE", "environment": "UNAVAILABLE", "deployment_url": "UNAVAILABLE", "deployment_image_id": "UNAVAILABLE", "gpu": None, "models_volume": "comfyui-models", "models_mount": "/root/models", "models_mount_read_only": True, "models": {role: {"name": next((item.get("model_name") for item in new_rows if str(item.get("role", "")).upper() == role), None), "source_bytes": next((item.get("source_bytes") for item in all_rows if item.get("role") == role), None)} for role in ROLES}})
    if ledger_path.exists():
        state = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger = state.get("ledger") if isinstance(state, dict) else None
        if isinstance(ledger, dict):
            statuses = [cell.get("status") for cell in ledger.get("cells", [])]
            report["campaign_ledger"] = {"path": ledger_path.as_posix(), "status": ledger.get("status"), "cell_count": len(statuses), "cell_status_counts": {status: statuses.count(status) for status in sorted(set(statuses))}}
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with CSV_OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["role", "block_mib", "qd", "n", "source_median_ms", "source_mean_ms", "effective_gbps", "achieved_mean_qd_mean", "achieved_max_qd_max", "source_read_count_mean"])
        writer.writeheader()
        for cell in cells:
            writer.writerow({"role": cell["role"], "block_mib": cell["block_mib"], "qd": cell["qd"], "n": cell["source_wall_ms"]["n"], "source_median_ms": cell["source_wall_ms"]["median"], "source_mean_ms": cell["source_wall_ms"]["mean"], "effective_gbps": cell["source_wall_ms"]["effective_gbps"], "achieved_mean_qd_mean": cell["achieved_mean_qd_mean"], "achieved_max_qd_max": cell["achieved_max_qd_max"], "source_read_count_mean": cell["source_read_count_mean"]})
    lines = ["# September UNET/CLIP Experiment 06: Source Block x QD Matrix", "", f"STATUS={report['status']}", "DECISION_METRIC=SOURCE_WALL_MS", "SECONDARY_METRIC=EFFECTIVE_GBPS", "", "## Best Source Configuration", "", "| model | block MiB | QD | SOURCE median ms | effective GB/s |", "|---|---:|---:|---:|---:|"]
    for role in ROLES:
        item = best.get(role)
        if item:
            lines.append(f"| {role} | {item['block_mib']} | {item['qd']} | {item['source_median_ms']:.3f} | {item['effective_gbps']:.6f} |")
    lines += ["", "Top two observed source configurations are also recorded in `best_two_source_configurations` in the JSON report."]
    lines += ["", "Best means the lowest median SOURCE_WALL_MS among observed cells. Historical integrated artifacts are retained separately and are not part of this cohort.", "", "## Performance By Block Size At Each QD", "", "| model | QD | block MiB | SOURCE median ms | effective GB/s |", "|---|---:|---:|---:|---:|"]
    for item in report["performance_by_block_at_each_qd"]:
        lines.append(f"| {item['role']} | {item['qd']} | {item['block_mib']} | {item['source_median_ms'] if item['source_median_ms'] is not None else 'UNAVAILABLE'} | {item.get('effective_gbps', 'UNAVAILABLE')} |")
    lines += ["", "## Performance By QD At Each Block Size", "", "| model | block MiB | QD | SOURCE median ms | effective GB/s |", "|---|---:|---:|---:|---:|"]
    for item in report["performance_by_qd_at_each_block"]:
        lines.append(f"| {item['role']} | {item['block_mib']} | {item['qd']} | {item['source_median_ms'] if item['source_median_ms'] is not None else 'UNAVAILABLE'} | {item.get('effective_gbps', 'UNAVAILABLE')} |")
    lines += ["", "## Performance Versus Nominal Outstanding Source Bytes", "", "| model | nominal MiB | configurations | SOURCE medians ms | FILE_TO_CUDA medians ms |", "|---|---:|---|---|---|"]
    for item in report["performance_by_nominal_outstanding_bytes"]:
        source = "; ".join(f"{key}={value if value is not None else 'UNAVAILABLE'}" for key, value in item["source_medians_ms"].items())
        ready = "; ".join(f"{key}={value if value is not None else 'UNAVAILABLE'}" for key, value in item["file_to_cuda_medians_ms"].items())
        lines.append(f"| {item['role']} | {item['nominal_outstanding_mib']} | {', '.join(item['configurations'])} | {source} | {ready} |")
    lines += ["", "## Cohort Audit", "", f"- New attempts retained: {len(new_rows)}; eligible: {len(new_valid)}; invalid: {len(new_invalid)}.", f"- Eligible observations retained: {len(all_rows)}.", "", "## Invalid Attempts And Raw Evidence", "", "| attempt | status | error | raw artifact |", "|---|---|---|---|"]
    for item in new_invalid:
        lines.append(f"| {item.get('attempt_id')} | {item.get('status')} | {item.get('error') or 'UNAVAILABLE'} | `{item.get('raw_artifact')}` |")
    lines += ["", "## Per-Cell Statistics And Ten Values", "", "| model | block MiB | QD | SOURCE values ms | FILE_TO_CUDA values ms | SOURCE median | SOURCE mean | SOURCE SD | effective GB/s | proof YES/NO |", "|---|---:|---:|---|---|---:|---:|---:|---:|---|"]
    for cell in cells:
        source_values = ", ".join(fmt(value) for value in cell["source_wall_ms"]["values"])
        ready_values = ", ".join(fmt(value) for value in cell["file_to_cuda_wall_ms"]["values"])
        proof = ", ".join(f"{key}={value}" for key, value in cell["proof_counts"].items())
        lines.append(f"| {cell['role']} | {cell['block_mib']} | {cell['qd']} | {source_values} | {ready_values} | {fmt(cell['source_wall_ms']['median'])} | {fmt(cell['source_wall_ms']['mean'])} | {fmt(cell['source_wall_ms']['sample_sd'])} | {fmt(cell['source_wall_ms']['effective_gbps'], 6)} | {proof} |")
    lines += ["", "## Deployment And Fixed Contract", "", f"- Worktree: `{report['worktree']}`; branch: `{report['branch']}`; HEAD: `{report['head']}`.", f"- App: `{report['app']}`; workspace/environment: `{report['workspace']}` / `{report['environment']}`.", f"- Source blocks: {', '.join(str(value) for value in BLOCK_MIBS)} MiB; QD values: {', '.join(str(value) for value in QDS)}; scheduling: serial, round-major.", "- Model construction, CUDA, H2D, and full Golden generation were not run.", "", "## Raw Evidence Paths", "", *[f"- `{path}`" for path in report["raw_evidence_roots"]], f"- Historical integrated evidence: `{report['historical_integrated_evidence']}`", f"- Machine-readable report: `{json_out.as_posix()}`"]
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    report = generate_report(strict=not args.allow_partial)
    print(f"generated {MD} and {JSON_OUT}: {len(report['observations'])} eligible observations, {len(report['invalid_new_attempts'])} invalid attempts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
