#!/usr/bin/env python
"""Present descriptive statistics from source-race campaign artifacts.

This module deliberately uses the raw per-block and per-attempt records.  It
does not assign an interpretation to the measurements.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable


THRESHOLDS = (100, 250, 500, 1000)
HISTOGRAM_EDGES = (0.0, 100.0, 250.0, 500.0, 1000.0)
GPU_FAMILIES = ("h100", "rtx")


def percentile(values: list[float], percent: float) -> float:
    """Match source_race_oracle.percentile's linear interpolation."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower))


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric, got {value!r}")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite, got {value!r}")
    return value


def stats(values: Iterable[float], percentiles: tuple[int, ...] = (90, 95, 99)) -> dict[str, Any]:
    values = [float(value) for value in values]
    result: dict[str, Any] = {
        "count": len(values),
        "mean_ms": float(statistics.mean(values)) if values else 0.0,
        "median_ms": percentile(values, 50),
        "max_ms": max(values) if values else 0.0,
        "stdev_ms": float(statistics.stdev(values)) if len(values) > 1 else 0.0,
    }
    for percent in percentiles:
        result[f"p{percent}_ms"] = percentile(values, percent)
    for threshold in THRESHOLDS:
        result[f"ge_{threshold}"] = sum(value >= threshold for value in values)
    return result


def _identity(artifact: dict[str, Any], engine: dict[str, Any], key: str) -> Any:
    if artifact.get(key) not in (None, ""):
        return artifact[key]
    identity = engine.get("identity")
    if isinstance(identity, dict) and identity.get(key) not in (None, ""):
        return identity[key]
    return engine.get(key, "")


def _family_matches(family: str, observed_gpu: str) -> bool:
    observed = "".join(character.lower() if character.isalnum() else " " for character in observed_gpu)
    words = set(observed.split())
    if family == "h100":
        return "h100" in words
    if family == "rtx":
        return "rtx" in words or any(word.startswith("rtx") for word in words)
    return False


def _artifact_is_usable(artifact: dict[str, Any], engine: dict[str, Any]) -> tuple[bool, str]:
    if artifact.get("campaign_status") not in (None, "COMPLETE"):
        return False, f"campaign_status={artifact.get('campaign_status')}"
    if engine.get("status") not in (None, "ok"):
        return False, f"engine_status={engine.get('status')}"
    coldness = artifact.get("coldness_evidence")
    if isinstance(coldness, dict) and coldness.get("valid") is not True:
        return False, "coldness_evidence.valid is not true"
    return True, ""


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def discover_artifacts(out_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Read direct artifacts and artifact paths referenced by campaign ledgers."""
    found: dict[str, tuple[Path, dict[str, Any]]] = {}
    ledger_paths: list[Path] = []
    for path in sorted(out_dir.rglob("*.json")):
        value = _load_json(path)
        if not value:
            continue
        if isinstance(value.get("engine_result"), dict):
            found[str(path.resolve())] = (path, value)
        if isinstance(value.get("cells"), list):
            ledger_paths.append(path)

    for ledger_path in ledger_paths:
        ledger = _load_json(ledger_path) or {}
        for cell in ledger.get("cells", []):
            if not isinstance(cell, dict):
                continue
            for attempt in cell.get("attempts", []):
                if not isinstance(attempt, dict) or not attempt.get("artifact"):
                    continue
                artifact_path = Path(str(attempt["artifact"]))
                if not artifact_path.is_absolute():
                    artifact_path = ledger_path.parent / artifact_path
                artifact = _load_json(artifact_path)
                if isinstance(artifact, dict) and isinstance(artifact.get("engine_result"), dict):
                    found[str(artifact_path.resolve())] = (artifact_path, artifact)

    def ordering(item: tuple[Path, dict[str, Any]]) -> tuple[int, str, str]:
        path, artifact = item
        campaign_index = artifact.get("campaign_index")
        return (campaign_index if isinstance(campaign_index, int) else 2**31, str(artifact.get("attempt_id", "")), str(path))

    return sorted(found.values(), key=ordering)


def _extract_observation(artifact: dict[str, Any], path: Path) -> dict[str, Any]:
    engine = artifact["engine_result"]
    blocks = engine.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError(f"{path}: engine_result.blocks must be a list")
    config = engine.get("config") if isinstance(engine.get("config"), dict) else {}
    width = artifact.get("race_width", config.get("race_width"))
    if not isinstance(width, int) or isinstance(width, bool) or width < 1:
        raise ValueError(f"{path}: race_width is missing or invalid")

    accepted: list[dict[str, Any]] = []
    physical: list[dict[str, Any]] = []
    loser_lifetimes: list[float] = []
    deltas: list[float] = []
    attempts_launched = 0
    total_requested = 0
    accepted_bytes = 0

    for block_position, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise ValueError(f"{path}: blocks[{block_position}] is not an object")
        length = _number(block.get("length"), f"{path}: blocks[{block_position}].length")
        if length < 0 or int(length) != length:
            raise ValueError(f"{path}: block length is not a non-negative integer")
        attempts = block.get("fighters")
        if not isinstance(attempts, list):
            attempts = block.get("physical_racers")
        if not isinstance(attempts, list):
            raise ValueError(f"{path}: blocks[{block_position}] has no fighters/physical_racers list")

        winners = [attempt for attempt in attempts if isinstance(attempt, dict) and attempt.get("is_winner") is True]
        accepted_value = block.get("accepted_preadv_ms")
        if accepted_value is None:
            if winners:
                raise ValueError(f"{path}: a marked winner has no accepted_preadv_ms")
        else:
            accepted_ms = _number(accepted_value, f"{path}: blocks[{block_position}].accepted_preadv_ms")
            if len(winners) != 1:
                raise ValueError(
                    f"{path}: accepted_preadv_ms requires exactly one is_winner=true attempt; found {len(winners)}"
                )
            # This is intentionally a block value, never an attempt value.  The
            # assertion above makes a malformed winner/loser mix fail loudly.
            accepted.append({
                "block_index": block.get("block_index", block_position),
                "accepted_ms": accepted_ms,
                "cumulative_bytes": _number(
                    block.get("cumulative_physical_bytes_before_block", 0),
                    f"{path}: cumulative_physical_bytes_before_block",
                ),
            })
            accepted_bytes += int(length)

        block_deltas = block.get("winner_to_loser_end_delta_ms", [])
        if block_deltas is None:
            block_deltas = []
        if not isinstance(block_deltas, list):
            raise ValueError(f"{path}: winner_to_loser_end_delta_ms must be a list")
        for delta in block_deltas:
            deltas.append(_number(delta, f"{path}: winner_to_loser_end_delta_ms"))

        fallback_lifetimes = iter(deltas[-len(block_deltas):] if block_deltas else [])
        for attempt in attempts:
            if not isinstance(attempt, dict):
                raise ValueError(f"{path}: a fighter record is not an object")
            physical_ms = _number(attempt.get("physical_syscall_ms"), f"{path}: physical_syscall_ms")
            bytes_read = attempt.get("bytes_read")
            if bytes_read is not None:
                bytes_read = _number(bytes_read, f"{path}: bytes_read")
            status = attempt.get("status")
            error = attempt.get("error")
            physical.append({
                "block_index": block.get("block_index", block_position),
                "physical_ms": physical_ms,
                "is_winner": attempt.get("is_winner") is True,
                "bytes_read": bytes_read,
                "status": status,
                "error": error,
            })
            attempts_launched += 1
            total_requested += int(length)
            if attempt.get("is_winner") is not True:
                lifetime = attempt.get("loser_lifetime_ms")
                if lifetime is None:
                    try:
                        lifetime = next(fallback_lifetimes)
                    except StopIteration:
                        lifetime = None
                if lifetime is not None:
                    loser_lifetimes.append(_number(lifetime, f"{path}: loser_lifetime_ms"))

    if engine.get("accepted", {}).get("count") not in (None, len(accepted)):
        raise ValueError(f"{path}: engine accepted.count disagrees with raw accepted block values")
    if engine.get("amplification", {}).get("attempts_launched") not in (None, attempts_launched):
        raise ValueError(f"{path}: engine amplification attempts_launched disagrees with raw attempts")

    return {
        "path": str(path),
        "artifact": artifact,
        "engine": engine,
        "gpu_family": str(artifact.get("gpu_family", "")).lower(),
        "race_width": width,
        "accepted": accepted,
        "physical": physical,
        "loser_lifetimes": loser_lifetimes,
        "deltas": deltas,
        "attempts_launched": attempts_launched,
        "total_requested": total_requested,
        "accepted_bytes": accepted_bytes,
    }


def _provenance(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    previous: str | None = None
    for observation in observations:
        artifact = observation["artifact"]
        identity = observation["engine"].get("identity")
        identity = identity if isinstance(identity, dict) else {}
        session = str(artifact.get("container_session_id") or identity.get("container_session_id", ""))
        result.append({
            "attempt_id": artifact.get("attempt_id", ""),
            "round": artifact.get("round", ""),
            "gpu_family": artifact.get("gpu_family", ""),
            "race_width": observation["race_width"],
            "requested_gpu": _identity(artifact, observation["engine"], "requested_gpu"),
            "observed_gpu": _identity(artifact, observation["engine"], "observed_gpu"),
            "provider": _identity(artifact, observation["engine"], "provider"),
            "region": _identity(artifact, observation["engine"], "region"),
            "container_session_id": session,
            "image_id": _identity(artifact, observation["engine"], "image_id"),
            "hostname": _identity(artifact, observation["engine"], "hostname"),
            "coldness_evidence": artifact.get("coldness_evidence", {}),
            "container_session_changed_from_previous": None if previous is None else session != previous,
        })
        previous = session
    return result


def _provenance_from_artifacts(items: list[tuple[Path, dict[str, Any]]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for path, artifact in items:
        engine_value = artifact.get("engine_result")
        engine: dict[str, Any] = engine_value if isinstance(engine_value, dict) else {}
        config_value = engine.get("config")
        config = config_value if isinstance(config_value, dict) else {}
        observations.append({
            "path": str(path),
            "artifact": artifact,
            "engine": engine,
            "race_width": artifact.get("race_width", config.get("race_width", "")),
        })
    return _provenance(observations)


def analyze(out_dir: Path) -> dict[str, Any]:
    included: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    discovered = discover_artifacts(out_dir)
    for path, artifact in discovered:
        engine = artifact.get("engine_result")
        if not isinstance(engine, dict):
            continue
        family = str(artifact.get("gpu_family", "")).lower()
        observed = str(_identity(artifact, engine, "observed_gpu") or "")
        usable, reason = _artifact_is_usable(artifact, engine)
        if not usable:
            exclusions.append({"path": str(path), "attempt_id": artifact.get("attempt_id", ""), "gpu_family": family, "observed_gpu": observed, "reason": reason})
            continue
        if family not in GPU_FAMILIES:
            exclusions.append({"path": str(path), "attempt_id": artifact.get("attempt_id", ""), "gpu_family": family, "observed_gpu": observed, "reason": "unsupported or missing gpu_family"})
            continue
        if not _family_matches(family, observed):
            exclusions.append({"path": str(path), "attempt_id": artifact.get("attempt_id", ""), "gpu_family": family, "observed_gpu": observed, "reason": f"observed GPU does not match gpu_family {family}"})
            continue
        # A malformed result is a correctness failure, not a statistic to omit.
        included.append(_extract_observation(artifact, path))

    groups: dict[tuple[str, int], dict[str, Any]] = {}
    for observation in included:
        key = (observation["gpu_family"], observation["race_width"])
        group = groups.setdefault(key, {
            "gpu_family": key[0], "race_width": key[1], "accepted_values": [], "physical_values": [],
            "loser_lifetimes": [], "deltas": [], "accepted_rows": [], "attempts_launched": 0,
            "total_requested": 0, "accepted_bytes": 0,
        })
        for row in observation["accepted"]:
            row = dict(row)
            row.update({"gpu_family": key[0], "race_width": key[1], "attempt_id": observation["artifact"].get("attempt_id", "")})
            group["accepted_rows"].append(row)
            group["accepted_values"].append(row["accepted_ms"])
        group["physical_values"].extend(row["physical_ms"] for row in observation["physical"])
        group["loser_lifetimes"].extend(observation["loser_lifetimes"])
        group["deltas"].extend(observation["deltas"])
        group["attempts_launched"] += observation["attempts_launched"]
        group["total_requested"] += observation["total_requested"]
        group["accepted_bytes"] += observation["accepted_bytes"]

    width_values: set[int] = set()
    for _, artifact in discovered:
        engine_value = artifact.get("engine_result")
        engine = engine_value if isinstance(engine_value, dict) else {}
        config_value = engine.get("config")
        config = config_value if isinstance(config_value, dict) else {}
        width = artifact.get("race_width", config.get("race_width"))
        if isinstance(width, int) and not isinstance(width, bool):
            width_values.add(width)
    widths = sorted(width_values)
    # Empty rows keep the report shape explicit for both GPU families.
    for family in GPU_FAMILIES:
        for width in widths:
            groups.setdefault((family, width), {
                "gpu_family": family, "race_width": width, "accepted_values": [], "physical_values": [],
                "loser_lifetimes": [], "deltas": [], "accepted_rows": [], "attempts_launched": 0,
                "total_requested": 0, "accepted_bytes": 0,
            })

    for group in groups.values():
        group["accepted_stats"] = stats(group["accepted_values"])
        group["physical_stats"] = stats(group["physical_values"], (95,))
        group["physical_stats"].pop("p90_ms", None)
        group["physical_stats"].pop("p99_ms", None)
        group["loser_lifetime_stats"] = {
            "count": len(group["loser_lifetimes"]),
            "mean_ms": float(statistics.mean(group["loser_lifetimes"])) if group["loser_lifetimes"] else 0.0,
            "median_ms": percentile(group["loser_lifetimes"], 50),
            "max_ms": max(group["loser_lifetimes"]) if group["loser_lifetimes"] else 0.0,
        }
        accepted_count = len(group["accepted_values"])
        group["amplification"] = {
            "attempts_launched": group["attempts_launched"],
            "attempts_per_accepted_read": group["attempts_launched"] / accepted_count if accepted_count else 0.0,
            "total_physical_bytes_requested": group["total_requested"],
            "accepted_bytes": group["accepted_bytes"],
            "speculative_amplification_ratio": group["attempts_launched"] / accepted_count if accepted_count else 0.0,
            "speculative_byte_amplification_ratio": group["total_requested"] / group["accepted_bytes"] if group["accepted_bytes"] else 0.0,
        }

    return {
        "schema_version": 1,
        "families": list(GPU_FAMILIES),
        "widths": widths,
        "groups": [groups[key] for key in sorted(groups)],
        "exclusions": exclusions,
        "provenance": _provenance_from_artifacts(discovered),
        "included_observations": len(included),
        "discovered_artifacts": len(discovered),
        "field_names_read": {
            "artifact": ["attempt_id", "round", "race_width", "gpu_family", "requested_gpu", "observed_gpu", "provider", "region", "container_session_id", "image_id", "hostname", "coldness_evidence", "engine_result"],
            "engine": ["status", "identity", "config.race_width", "blocks", "blocks[].length", "blocks[].block_index", "blocks[].accepted_preadv_ms", "blocks[].cumulative_physical_bytes_before_block", "blocks[].winner_to_loser_end_delta_ms", "blocks[].fighters", "blocks[].physical_racers", "fighters[].physical_syscall_ms", "fighters[].bytes_read", "fighters[].status", "fighters[].error", "fighters[].is_winner", "fighters[].loser_lifetime_ms", "accepted.count", "amplification.attempts_launched"],
        },
    }


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(_fmt(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _latency_headers(include_stdev: bool = True) -> list[str]:
    headers = ["GPU family", "Race width", "Count", "Mean ms", "Median ms", "P90 ms", "P95 ms", "P99 ms", "Max ms"]
    if include_stdev:
        headers.append("Std dev ms")
    headers.extend([">=100 ms", ">=250 ms", ">=500 ms", ">=1000 ms"])
    return headers


def _latency_row(group: dict[str, Any], key: str, include_stdev: bool = True) -> list[Any]:
    value = group[key]
    row = [group["gpu_family"], group["race_width"], value["count"], value["mean_ms"], value["median_ms"]]
    if key == "physical_stats":
        row.extend(["n/a", value["p95_ms"], "n/a", value["max_ms"]])
    else:
        row.extend([value["p90_ms"], value["p95_ms"], value["p99_ms"], value["max_ms"]])
    if include_stdev:
        row.append(value.get("stdev_ms", "n/a"))
    row.extend(value[f"ge_{threshold}"] for threshold in THRESHOLDS)
    return row


def render_markdown(aggregate: dict[str, Any], plot_note: str = "") -> str:
    groups = aggregate["groups"]
    lines = ["# Source-race descriptive statistics", "", "GPU families are calculated and displayed separately.", "", "## Method", "", "Accepted statistics use every raw `blocks[].accepted_preadv_ms` value, pooled across observations within the same `(gpu_family, race_width)` pair. The engine's aggregated `accepted.mean_ms` is not averaged. Physical statistics use every raw `fighters[].physical_syscall_ms` value. Accepted values never use loser or other attempt records.", ""]
    lines.extend(["## 1. Accepted latency vs race width", "", _table(_latency_headers(), [_latency_row(group, "accepted_stats") for group in groups]), ""])
    lines.extend(["## 2. Physical attempt latency vs race width", "", _table(_latency_headers(), [_latency_row(group, "physical_stats", False) for group in groups]), ""])

    block_rows: list[list[Any]] = []
    for group in groups:
        by_index: dict[Any, list[float]] = {}
        for row in group["accepted_rows"]:
            by_index.setdefault(row["block_index"], []).append(row["accepted_ms"])
        for block_index in sorted(by_index):
            value = stats(by_index[block_index])
            block_rows.append([group["gpu_family"], group["race_width"], block_index, value["count"], value["mean_ms"], value["median_ms"], value["p90_ms"], value["p95_ms"], value["p99_ms"], value["max_ms"]])
    lines.extend(["## 3. Accepted latency vs block index", "", _table(["GPU family", "Race width", "Block index", "Count", "Mean ms", "Median ms", "P90 ms", "P95 ms", "P99 ms", "Max ms"], block_rows), ""])

    cumulative_rows = [[row["gpu_family"], row["race_width"], row["block_index"], row["cumulative_bytes"], row["accepted_ms"], row["attempt_id"]] for group in groups for row in group["accepted_rows"]]
    lines.extend(["## 4. Accepted latency vs cumulative speculative bytes", "", _table(["GPU family", "Race width", "Block index", "Cumulative bytes before block", "Accepted ms", "Attempt ID"], cumulative_rows), ""])

    histogram_rows: list[list[Any]] = []
    for group in groups:
        buckets = [0] * (len(HISTOGRAM_EDGES) + 1)
        for value in group["deltas"]:
            bucket = len(HISTOGRAM_EDGES)
            for index, edge in enumerate(HISTOGRAM_EDGES):
                if value < edge:
                    bucket = index
                    break
            buckets[bucket] += 1
        labels = ["<0", "[0,100)", "[100,250)", "[250,500)", "[500,1000)", ">=1000"]
        histogram_rows.extend([[group["gpu_family"], group["race_width"], labels[index], count] for index, count in enumerate(buckets)])
    lines.extend(["## 5. Winner-to-loser completion delta distribution", "", "Bucket edges in milliseconds: `(-infinity, 0)`, `[0, 100)`, `[100, 250)`, `[250, 500)`, `[500, 1000)`, `[1000, infinity)`.", "", _table(["GPU family", "Race width", "Bucket", "Count"], histogram_rows), ""])

    lines.extend(["## Physical attempt and loser-lifetime summaries", "", _table(["GPU family", "Race width", "Attempts launched", "Attempts per accepted read", "Total physical bytes requested", "Accepted bytes", "Count-based ratio", "Byte-based ratio", "Loser lifetime mean ms", "Loser lifetime median ms", "Loser lifetime max ms"], [[group["gpu_family"], group["race_width"], group["amplification"]["attempts_launched"], group["amplification"]["attempts_per_accepted_read"], group["amplification"]["total_physical_bytes_requested"], group["amplification"]["accepted_bytes"], group["amplification"]["speculative_amplification_ratio"], group["amplification"]["speculative_byte_amplification_ratio"], group["loser_lifetime_stats"]["mean_ms"], group["loser_lifetime_stats"]["median_ms"], group["loser_lifetime_stats"]["max_ms"]] for group in groups]), ""])

    lines.extend(["## Exclusions", "", _table(["Attempt ID", "GPU family", "Observed GPU", "Reason", "Path"], [[item["attempt_id"], item["gpu_family"], item["observed_gpu"], item["reason"], item["path"]] for item in aggregate["exclusions"]] or [["", "", "", "none", ""]]), ""])
    provenance_rows = []
    for item in aggregate["provenance"]:
        evidence = json.dumps(item["coldness_evidence"], sort_keys=True, separators=(",", ":"))
        provenance_rows.append([item["attempt_id"], item["round"], item["gpu_family"], item["race_width"], item["requested_gpu"], item["observed_gpu"], item["provider"], item["region"], item["container_session_id"], item["image_id"], item["hostname"], evidence, item["container_session_changed_from_previous"]])
    lines.extend(["## Run provenance", "", _table(["Attempt ID", "Round", "GPU family", "Race width", "Requested GPU", "Observed GPU", "Provider", "Region", "Container session ID", "Image ID", "Hostname", "Coldness evidence", "Session changed from previous"], provenance_rows or [["", "", "", "", "", "", "", "", "", "", "", "", ""]]), ""])
    if plot_note:
        lines.extend([plot_note, ""])
    return "\n".join(lines)


def _make_plots(aggregate: dict[str, Any], plots_dir: Path) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        return f"Plots skipped: matplotlib is not importable ({type(exc).__name__}: {exc}). Markdown tables were produced."

    plots_dir.mkdir(parents=True, exist_ok=True)
    groups = aggregate["groups"]
    for family in GPU_FAMILIES:
        family_groups = [group for group in groups if group["gpu_family"] == family]
        figures: list[tuple[str, Any]] = []
        figure, axis = plt.subplots()
        axis.set_title(f"Accepted latency vs race width — {family}")
        for group in family_groups:
            if group["accepted_values"]:
                axis.scatter([group["race_width"]] * len(group["accepted_values"]), group["accepted_values"], label=f"width {group['race_width']}")
        axis.set_xlabel("Race width")
        axis.set_ylabel("Accepted latency (ms)")
        if any(group["accepted_values"] for group in family_groups): axis.legend()
        figures.append(("accepted_latency_vs_width", figure))

        figure, axis = plt.subplots()
        axis.set_title(f"Physical attempt latency vs race width — {family}")
        for group in family_groups:
            if group["physical_values"]:
                axis.scatter([group["race_width"]] * len(group["physical_values"]), group["physical_values"], label=f"width {group['race_width']}")
        axis.set_xlabel("Race width")
        axis.set_ylabel("Physical syscall latency (ms)")
        if any(group["physical_values"] for group in family_groups): axis.legend()
        figures.append(("physical_latency_vs_width", figure))

        figure, axis = plt.subplots()
        axis.set_title(f"Accepted latency vs block index — {family}")
        for group in family_groups:
            axis.scatter([row["block_index"] for row in group["accepted_rows"].copy()], [row["accepted_ms"] for row in group["accepted_rows"]], label=f"width {group['race_width']}")
        axis.set_xlabel("Block index")
        axis.set_ylabel("Accepted latency (ms)")
        if any(group["accepted_rows"] for group in family_groups): axis.legend()
        figures.append(("accepted_latency_vs_block_index", figure))

        figure, axis = plt.subplots()
        axis.set_title(f"Accepted latency vs cumulative speculative bytes — {family}")
        for group in family_groups:
            if group["accepted_rows"]:
                axis.scatter([row["cumulative_bytes"] for row in group["accepted_rows"]], [row["accepted_ms"] for row in group["accepted_rows"]], label=f"width {group['race_width']}")
        axis.set_xlabel("Cumulative physical bytes before block")
        axis.set_ylabel("Accepted latency (ms)")
        if any(group["accepted_rows"] for group in family_groups): axis.legend()
        figures.append(("accepted_latency_vs_cumulative_bytes", figure))

        figure, axis = plt.subplots()
        axis.set_title(f"Winner-to-loser completion delta distribution — {family}")
        for group in family_groups:
            if group["deltas"]:
                axis.hist(group["deltas"], bins=list(HISTOGRAM_EDGES) + [max(HISTOGRAM_EDGES[-1], max(group["deltas"])) + 1], alpha=0.45, label=f"width {group['race_width']}")
        axis.set_xlabel("Winner-to-loser completion delta (ms)")
        axis.set_ylabel("Count")
        if any(group["deltas"] for group in family_groups): axis.legend()
        figures.append(("winner_to_loser_delta_histogram", figure))

        for name, figure in figures:
            figure.tight_layout()
            figure.savefig(plots_dir / f"{name}_{family}.png")
            plt.close(figure)
    return f"Plots produced in `{plots_dir}`: five PNGs per GPU family."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="campaign artifact directory")
    parser.add_argument("--md", required=True, type=Path, help="markdown report path")
    parser.add_argument("--plots-dir", type=Path)
    parser.add_argument("--json", dest="json_path", type=Path)
    args = parser.parse_args(argv)
    aggregate = analyze(args.out)
    plot_note = "Plots not requested."
    if args.plots_dir is not None:
        plot_note = _make_plots(aggregate, args.plots_dir)
        aggregate["plots_note"] = plot_note
    markdown = render_markdown(aggregate, plot_note)
    args.md.parent.mkdir(parents=True, exist_ok=True)
    args.md.write_text(markdown, encoding="utf-8")
    json_path = args.json_path or args.out / "source_race_aggregate.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote markdown report: {args.md}")
    print(f"wrote aggregate JSON: {json_path}")
    print(plot_note)
    print(f"included observations: {aggregate['included_observations']}; exclusions: {len(aggregate['exclusions'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
