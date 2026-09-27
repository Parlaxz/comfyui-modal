#!/usr/bin/env python
"""Descriptive statistics for the source race campaign.

Reads the per-run artifacts written by ``tools/run_source_race_min.py`` and
emits raw distributions and summary statistics only.

No classification, no semantic labels, no causal inference.  The H100 and RTX
PRO 6000 cohorts are reported completely separately and are never pooled.

Usage:
    python tools/source_race_stats.py --out source_race_runs --md report.md
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_THRESHOLDS = (100, 250, 500, 1000)
_DELTA_BUCKETS = (0, 5, 10, 25, 50, 100, 250, 500, 1000, 5000)


def percentile(values: list[float], pct: float) -> float | None:
    """Linear interpolation between ordered ranks (same convention as the engine)."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    out: dict[str, Any] = {
        "count": len(values),
        "mean_ms": statistics.fmean(values),
        "median_ms": statistics.median(values),
        "p90_ms": percentile(values, 90),
        "p95_ms": percentile(values, 95),
        "p99_ms": percentile(values, 99),
        "max_ms": max(values),
        "min_ms": min(values),
        "stdev_ms": statistics.stdev(values) if len(values) > 1 else 0.0,
    }
    for threshold in _THRESHOLDS:
        out[f"ge_{threshold}"] = sum(1 for v in values if v >= threshold)
    return out


def _family_of(record: dict[str, Any]) -> str:
    attempt = record.get("_attempt") or {}
    family = str(attempt.get("family") or "").strip().lower()
    if family in {"h100", "rtx"}:
        return family
    observed = str(record.get("observed_gpu") or "")
    if "H100" in observed:
        return "h100"
    if "RTX" in observed.upper():
        return "rtx"
    return "unknown"


def _gpu_matches_family(family: str, observed: str) -> bool:
    observed_u = observed.upper()
    if family == "h100":
        return "H100" in observed_u
    if family == "rtx":
        return "RTX" in observed_u and "PRO 6000" in observed_u
    return False


def load(out_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for path in sorted(out_dir.glob("*.json")):
        if path.name.endswith(".err.json"):
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            exclusions.append({"artifact": path.name, "reason": f"unreadable: {exc}"})
            continue
        if not isinstance(record, dict) or "blocks" not in record:
            exclusions.append({"artifact": path.name, "reason": "not a run artifact"})
            continue
        record["_artifact"] = path.name
        family = _family_of(record)
        observed = str(record.get("observed_gpu") or "")
        if not _gpu_matches_family(family, observed):
            exclusions.append({
                "artifact": path.name,
                "reason": f"observed GPU {observed!r} does not match cohort {family!r}",
            })
            continue
        if record.get("status") != "ok":
            exclusions.append({"artifact": path.name, "reason": f"status={record.get('status')}"})
            continue
        records.append(record)
    return records, exclusions


def analyse(records: list[dict[str, Any]]) -> dict[str, Any]:
    accepted: dict[tuple[str, int], list[float]] = defaultdict(list)
    physical: dict[tuple[str, int], list[float]] = defaultdict(list)
    losers: dict[tuple[str, int], list[float]] = defaultdict(list)
    deltas: dict[tuple[str, int], list[float]] = defaultdict(list)
    deltas_flat: dict[str, list[float]] = defaultdict(list)
    by_block: dict[tuple[str, int, int], list[float]] = defaultdict(list)
    cumulative: dict[str, list[tuple[int, float]]] = defaultdict(list)
    provenance: list[dict[str, Any]] = []
    integrity = {"attempts_alive_after_drain_nonzero": [], "block_counts": set(), "errors": []}

    for record in records:
        family = _family_of(record)
        config = record.get("config") or {}
        width = int(config.get("race_width") or 0)
        integrity["block_counts"].add(int(config.get("block_count") or 0))
        if record.get("integrity", {}).get("errors"):
            integrity["errors"].append({record["_artifact"]: record["integrity"]["errors"]})
        provenance.append({
            "artifact": record["_artifact"],
            "attempt_id": (record.get("_attempt") or {}).get("attempt_id"),
            "round": (record.get("_attempt") or {}).get("round"),
            "race_width": width,
            "observed_gpu": record.get("observed_gpu"),
            "provider": record.get("provider"),
            "region": record.get("region"),
            "container_session_id": record.get("container_session_id"),
            "fresh_container_vs_previous": (record.get("_attempt") or {}).get("fresh_container_vs_previous"),
            "accepted_wave_wall_ms": (record.get("wall") or {}).get("accepted_wave_wall_ms"),
            "total_wall_ms": (record.get("wall") or {}).get("total_wall_ms"),
        })
        for block in record.get("blocks") or []:
            value = block.get("accepted_preadv_ms")
            if isinstance(value, (int, float)):
                accepted[(family, width)].append(float(value))
                block_index = int(block.get("block_index") or 0)
                by_block[(family, width, block_index)].append(float(value))
                cumulative[family].append((
                    int(block.get("cumulative_physical_bytes_before_block") or 0),
                    float(value),
                ))
            alive = block.get("attempts_alive_after_drain")
            if isinstance(alive, int) and alive != 0:
                integrity["attempts_alive_after_drain_nonzero"].append(
                    {"artifact": record["_artifact"], "block": block.get("block_index"), "alive": alive}
                )
            for delta in block.get("winner_to_loser_end_delta_ms") or []:
                if isinstance(delta, (int, float)):
                    deltas[(family, width)].append(float(delta))
                    deltas_flat[family].append(float(delta))
            for fighter in block.get("fighters") or []:
                duration = fighter.get("physical_syscall_ms")
                if isinstance(duration, (int, float)):
                    physical[(family, width)].append(float(duration))
                if not fighter.get("is_winner") and isinstance(duration, (int, float)):
                    losers[(family, width)].append(float(duration))

    widths = sorted({w for (_, w) in list(accepted) + list(physical)})
    families = sorted({f for (f, _) in list(accepted) + list(physical)})
    table: dict[str, Any] = {}
    for family in families:
        table[family] = {}
        for width in widths:
            acc = accepted.get((family, width), [])
            phy = physical.get((family, width), [])
            if not acc and not phy:
                continue
            table[family][width] = {
                "accepted": _summary(acc),
                "physical": _summary(phy),
                "loser_attempts": len(losers.get((family, width), [])),
                "loser_lifetime_ms": _summary(losers.get((family, width), [])),
                "attempts_per_accepted_read": (
                    len(phy) / len(acc) if acc else None
                ),
                "winner_to_loser_end_delta_ms": _summary(deltas.get((family, width), [])),
            }
    return {
        "families": families,
        "widths": widths,
        "table": table,
        "by_block": {f"{f}|{w}|{b}": statistics.fmean(v) for (f, w, b), v in by_block.items()},
        "cumulative": {
            family: sorted(pairs) for family, pairs in cumulative.items()
        },
        "deltas_flat": {family: values for family, values in deltas_flat.items()},
        "provenance": provenance,
        "integrity": {
            "attempts_alive_after_drain_nonzero": integrity["attempts_alive_after_drain_nonzero"],
            "block_counts": sorted(integrity["block_counts"]),
            "errors": integrity["errors"],
        },
    }


def _row(label: str, summary: dict[str, Any], keys: tuple[str, ...]) -> str:
    cells = [label]
    for key in keys:
        value = summary.get(key)
        cells.append("" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value))
    return "| " + " | ".join(cells) + " |"


def render(analysis: dict[str, Any], exclusions: list[dict[str, Any]]) -> str:
    lines: list[str] = ["# Source race campaign — descriptive statistics", ""]
    lines.append("Raw distributions and summary statistics only. H100 and RTX PRO 6000 "
                 "cohorts are reported separately and never pooled.")
    lines.append("")
    keys = ("count", "mean_ms", "median_ms", "p90_ms", "p95_ms", "p99_ms", "max_ms", "stdev_ms",
            "ge_100", "ge_250", "ge_500", "ge_1000")
    header = "| arm | " + " | ".join(keys) + " |"

    for family in analysis["families"]:
        lines.append(f"## {family.upper()}")
        lines.append("")
        lines.append("### Accepted (winner) PREADV latency by race width")
        lines.append("")
        lines.append(header)
        lines.append("|" + "---|" * (len(keys) + 1))
        for width in analysis["widths"]:
            entry = analysis["table"].get(family, {}).get(width)
            if entry:
                lines.append(_row(f"width {width}", entry["accepted"], keys))
        lines.append("")
        lines.append("### All physical PREADV attempts by race width")
        lines.append("")
        lines.append(header)
        lines.append("|" + "---|" * (len(keys) + 1))
        for width in analysis["widths"]:
            entry = analysis["table"].get(family, {}).get(width)
            if entry:
                lines.append(_row(f"width {width}", entry["physical"], keys))
        lines.append("")
        lines.append("### Amplification / loser accounting by race width")
        lines.append("")
        lines.append("| width | attempts per accepted read | loser attempts | loser lifetime mean ms | winner→loser delta mean ms |")
        lines.append("|---|---|---|---|---|")
        for width in analysis["widths"]:
            entry = analysis["table"].get(family, {}).get(width)
            if not entry:
                continue
            per_read = entry["attempts_per_accepted_read"]
            loser_summary = entry["loser_lifetime_ms"]
            delta_summary = entry["winner_to_loser_end_delta_ms"]
            per_read_text = "-" if per_read is None else f"{per_read:.2f}"
            loser_text = "-" if not loser_summary.get("count") else f"{loser_summary['mean_ms']:.3f}"
            delta_text = "-" if not delta_summary.get("count") else f"{delta_summary['mean_ms']:.3f}"
            lines.append(
                f"| {width} | {per_read_text} | {entry['loser_attempts']} | "
                f"{loser_text} | {delta_text} |"
            )
        lines.append("")

    lines.append("## Accepted latency vs block index (all widths pooled, per family)")
    lines.append("")
    lines.append("| block index | " + " | ".join(analysis["families"]) + " |")
    lines.append("|---|" + "---|" * len(analysis["families"]))
    for block_index in range(max(analysis["integrity"]["block_counts"] or [0])):
        cells = [str(block_index)]
        for family in analysis["families"]:
            values = [v for (f, _w, b), v in
                      ((tuple(k.split("|")), val) for k, val in analysis["by_block"].items())
                      if f == family and int(b) == block_index]
            cells.append("-" if not values else f"{statistics.fmean(values):.3f}")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Accepted latency vs cumulative speculative bytes")
    lines.append("")
    lines.append("| cumulative bytes bucket (GiB) | " + " | ".join(analysis["families"]) + " |")
    lines.append("|---|" + "---|" * len(analysis["families"]))
    gib = 1024 ** 3
    edges = [0, 8, 32, 128, 512, 1024, 4096, 16384]
    for lo, hi in zip(edges, edges[1:]):
        cells = [f"{lo}-{hi}"]
        for family in analysis["families"]:
            values = [v for (b, v) in analysis["cumulative"].get(family, [])
                      if lo * gib <= b < hi * gib]
            cells.append("-" if not values else f"{statistics.fmean(values):.3f}")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Winner→loser completion delta distribution")
    lines.append("")
    lines.append("| delta bucket (ms) | " + " | ".join(analysis["families"]) + " |")
    lines.append("|---|" + "---|" * len(analysis["families"]))
    for lo, hi in zip(_DELTA_BUCKETS, _DELTA_BUCKETS[1:]):
        cells = [f"{lo}-{hi}"]
        for family in analysis["families"]:
            values = analysis["deltas_flat"].get(family, [])
            cells.append(str(sum(1 for v in values if lo <= v < hi)))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("(Bucket counts are reported in the JSON aggregate; the mean delta per arm is in the "
                 "amplification table above.)")
    lines.append("")

    lines.append("## Run provenance")
    lines.append("")
    lines.append("| artifact | attempt | round | width | observed GPU | provider | region | container session | fresh vs prev | accepted wave wall ms | total wall ms |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for row in analysis["provenance"]:
        wave = row["accepted_wave_wall_ms"]
        total = row["total_wall_ms"]
        wave_text = "-" if wave is None else f"{wave:.3f}"
        total_text = "-" if total is None else f"{total:.3f}"
        lines.append(
            f"| {row['artifact']} | {row['attempt_id']} | {row['round']} | {row['race_width']} | "
            f"{row['observed_gpu']} | {row['provider']} | {row['region']} | {row['container_session_id']} | "
            f"{row['fresh_container_vs_previous']} | {wave_text} | {total_text} |"
        )
    lines.append("")

    lines.append("## Integrity and exclusions")
    lines.append("")
    lines.append(f"- runs included: {len(analysis['provenance'])}")
    lines.append(f"- distinct block counts observed: {analysis['integrity']['block_counts']}")
    lines.append(f"- attempts_alive_after_drain != 0 events: "
                 f"{len(analysis['integrity']['attempts_alive_after_drain_nonzero'])}")
    lines.append(f"- engine errors: {len(analysis['integrity']['errors'])}")
    lines.append(f"- excluded artifacts: {len(exclusions)}")
    for item in exclusions:
        lines.append(f"  - {item['artifact']}: {item['reason']}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="source_race_runs")
    parser.add_argument("--md", default=None)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    out_dir = Path(args.out)
    records, exclusions = load(out_dir)
    analysis = analyse(records)
    report = render(analysis, exclusions)

    md_path = Path(args.md) if args.md else out_dir / "source_race_report.md"
    md_path.write_text(report, encoding="utf-8")
    json_path = Path(args.json) if args.json else out_dir / "source_race_aggregate.json"
    json_path.write_text(json.dumps(analysis, indent=2, sort_keys=True, default=str), encoding="utf-8")

    print(f"runs={len(records)} exclusions={len(exclusions)}")
    for family in analysis["families"]:
        for width in analysis["widths"]:
            entry = analysis["table"].get(family, {}).get(width)
            if not entry:
                continue
            acc = entry["accepted"]
            phy = entry["physical"]
            print(f"{family} width={width:>2} accepted n={acc.get('count')} "
                  f"mean={acc.get('mean_ms'):.2f} median={acc.get('median_ms'):.2f} "
                  f"p95={acc.get('p95_ms'):.2f} max={acc.get('max_ms'):.2f} | "
                  f"physical n={phy.get('count')} median={phy.get('median_ms'):.2f} "
                  f"max={phy.get('max_ms'):.2f}")
    print(f"md={md_path}")
    print(f"json={json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
