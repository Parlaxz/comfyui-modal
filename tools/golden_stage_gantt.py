"""Render a per-stage Gantt of the Golden exhaustive profiler calls CSV.

Reads ``derived/golden_exhaustive_calls.csv.gz`` -- the cheap artifact -- and
emits Markdown with one Gantt per canonical Golden stage, listing only frames at
or above a wall-clock threshold.

Stages overlap in wall time (the overlap schedule runs unet_load alongside
clip_load and clip_forward), so attribution walks the ``parent_event_index``
tree from each stage's own call rather than testing time containment, which
would double-count every overlapping stage.

Usage:
    python tools/golden_stage_gantt.py <session_dir> [--min-ms 1.0] [--top 40]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import sys
from collections import defaultdict
from pathlib import Path

CANONICAL_STAGE_ORDER = (
    "golden_restore",
    "golden_request_setup",
    "golden_clip_load",
    "golden_clip_forward",
    "golden_unet_load",
    "golden_sampler_prepare",
    "golden_vae_load",
    "golden_sampling",
    "golden_sampler_tail",
    "golden_vae_decode",
    "golden_output",
)

CALLS_CSV = "derived/golden_exhaustive_calls.csv.gz"


def _num(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bar(fraction: float, width: int = 40) -> str:
    if fraction <= 0:
        return ""
    filled = max(1, min(width, int(round(fraction * width))))
    return "#" * filled


def load_rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            yield {
                "idx": _num(row.get("event_index")),
                "parent": (
                    _num(row["parent_event_index"])
                    if row.get("parent_event_index") not in (None, "", "FEE")
                    else None
                ),
                "function": row.get("function") or "",
                "qualified": row.get("qualified_function") or "",
                "wall_ms": _num(row.get("wall_ms")),
                "exclusive_self_ms": _num(row.get("exclusive_self_ms")),
                "start_ms": _num(row.get("start_offset_ms")),
                "end_ms": _num(row.get("end_offset_ms")),
                "source_file": (row.get("source_file") or "").split("/")[-1],
                "source_line": row.get("source_line") or "",
                "complete": row.get("complete"),
                "depth": int(_num(row.get("depth"))),
            }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("session_dir", type=Path)
    ap.add_argument("--min-ms", type=float, default=1.0)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    csv_path = args.session_dir / CALLS_CSV
    if not csv_path.is_file():
        print(f"missing {csv_path}", file=sys.stderr)
        return 1

    rows = list(load_rows(csv_path))
    by_index = {r["idx"]: r for r in rows}
    children: dict[float, list[dict]] = defaultdict(list)
    for r in rows:
        if r["parent"] is not None:
            children[r["parent"]].append(r)

    print(f"loaded {len(rows)} calls", file=sys.stderr)

    # Each canonical stage may appear as both a stage body and a Python-call
    # record covering the same interval; the widest is the stage root, matching
    # resolve_stage()'s "longest wins" rule.
    stage_roots: dict[str, dict] = {}
    for r in rows:
        name = r["function"]
        if name in CANONICAL_STAGE_ORDER:
            best = stage_roots.get(name)
            if best is None or r["wall_ms"] > best["wall_ms"]:
                stage_roots[name] = r

    # Attribute by time containment on the same process, taking the TIGHTEST
    # containing stage. Stack nesting does not reach these stage bodies: the
    # overlap schedule runs them on executor threads, so their frames are
    # unparented in the CSV and a parent walk sees almost nothing. Tightest
    # containment is what disambiguates overlapping stages -- unet_load overlaps
    # both clip_load and clip_forward.
    stage_list = [
        (name, root) for name, root in stage_roots.items()
    ]
    buckets: dict[str, list[dict]] = {name: [] for name, _ in stage_list}
    for r in rows:
        best_name = None
        best_width = None
        for name, o in stage_list:
            if r["idx"] == o["idx"]:
                continue
            if (
                r["start_ms"] >= o["start_ms"] - 1e-6
                and r["end_ms"] <= o["end_ms"] + 1e-6
            ):
                width = o["end_ms"] - o["start_ms"]
                if best_width is None or width < best_width:
                    best_name, best_width = name, width
        if best_name is not None:
            buckets[best_name].append(r)

    out_path = args.out or (
        args.session_dir / "derived" / "golden_stage_gantts.md"
    )

    total_calls = len(rows)
    sections: list[str] = []
    summary_rows = []
    for stage in CANONICAL_STAGE_ORDER:
        root = stage_roots.get(stage)
        if root is None:
            summary_rows.append((stage, None, 0, 0))
            continue
        subtree = [root] + buckets.get(stage, [])

        wall = root["wall_ms"]
        # Aggregate by function inside the stage so repeated frames collapse.
        agg: dict[str, dict] = {}
        for r in subtree:
            key = r["qualified"] or r["function"]
            slot = agg.setdefault(
                key,
                {
                    "name": key,
                    "wall_ms": 0.0,
                    "self_ms": 0.0,
                    "count": 0,
                    "source_file": r["source_file"],
                    "source_line": r["source_line"],
                    "max_ms": 0.0,
                },
            )
            slot["wall_ms"] += r["wall_ms"]
            slot["self_ms"] += r["exclusive_self_ms"]
            slot["count"] += 1
            slot["max_ms"] = max(slot["max_ms"], r["wall_ms"])

        interesting = {
            k: v for k, v in agg.items()
            if v["wall_ms"] >= args.min_ms and k not in CANONICAL_STAGE_ORDER
        }
        ranked = sorted(
            interesting.values(), key=lambda v: v["wall_ms"], reverse=True
        )
        summary_rows.append((stage, wall, len(subtree), len(ranked)))

        sections.append("## `{}`".format(stage))
        sections.append("")
        sections.append("- Stage wall: **{:,.3f} ms**".format(wall))
        sections.append("- Calls attributed: **{:,}**".format(len(subtree)))
        sections.append(
            "- Distinct functions >= {:g} ms: **{:,}**".format(
                args.min_ms, len(ranked),
            )
        )
        sections.append("")
        if not ranked:
            sections.append("_No frame reached the threshold._")
            sections.append("")
            continue
        shown = ranked[: args.top]
        width = 34
        sections.append("| wall ms | self ms | calls | bar | function | source |")
        sections.append("|---:|---:|---:|:--|:--|:--|")
        for v in shown:
            frac = (v["wall_ms"] / wall) if wall > 0 else 0.0
            src = "{}:{}".format(v["source_file"] or "", v["source_line"] or "")
            sections.append(
                "| {w:,.3f} | {s:,.3f} | {c} | `{bar}` | `{fn}` | `{src}` |".format(
                    w=v["wall_ms"],
                    s=v["self_ms"],
                    c=v["count"],
                    bar=_bar(frac, width),
                    fn=v["name"],
                    src=src,
                )
            )
        sections.append("")
        if len(ranked) > len(shown):
            sections.append(
                "_{} more functions omitted._".format(len(ranked) - len(shown))
            )
            sections.append("")

    summary = [
        "## Stage summary",
        "",
        "| stage | wall ms | calls attributed | functions >= threshold |",
        "|:--|---:|---:|---:|",
    ]
    for stage, wall, n, f in summary_rows:
        summary.append(
            "| `{}` | {} | {:,} | {:,} |".format(
                stage, "-" if wall is None else f"{wall:,.3f}", n, f,
            )
        )
    summary.append("")

    doc = [
        "# Golden per-stage Gantts",
        "",
        "Source: `{}`".format(csv_path.name),
        "",
        "Calls in trace: **{:,}**".format(total_calls),
        "",
        "Frames shown: wall >= **{:g} ms**".format(args.min_ms),
        "",
        "Stages: {} of {} observed".format(
            len(stage_roots), len(CANONICAL_STAGE_ORDER),
        ),
        "",
        "Attribution is by tightest time containment within a stage, because "
        "the overlap schedule runs stage bodies on executor threads where stack "
        "nesting cannot see them. Bars are scaled per stage against that "
        "stage's own wall clock.",
        "",
    ] + summary + sections

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(doc), encoding="utf-8")
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())