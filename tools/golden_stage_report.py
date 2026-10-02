"""One decision document for a Golden exhaustive profile run.

Emits three sections over ``derived/golden_exhaustive_calls.csv.gz``:

1. **Critical path** -- a stage timeline showing which stages overlap and how
   much of each stage's wall is uncontended. Stage wall alone is misleading when
   the overlap schedule runs stages concurrently: saving time inside an
   overlapped stage can be absorbed by a longer sibling and leave root wall
   unchanged. Uncontended time is the part that is unambiguously on the critical
   path.
2. **Per-stage call trees** -- recursive, expanded at ``--min-ms``.
3. **Function rollup** -- per function across the whole request: call count,
   mean, and total inclusive wall, so a function called 24 times at 3 ms reads as
   72 ms rather than hiding behind a mean.

Usage:
    python tools/golden_stage_report.py <session_dir> [--min-ms 1.0]
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from golden_stage_gantt import (  # noqa: E402
    CALLS_CSV,
    CANONICAL_STAGE_ORDER,
    load_rows,
)
from golden_stage_tree import build, render_tree  # noqa: E402


def critical_path(stage_roots: dict[str, dict], width: int = 72) -> list[str]:
    """Stage timeline plus uncontended/overlapped split per stage."""
    intervals = []
    for stage in CANONICAL_STAGE_ORDER:
        root = stage_roots.get(stage)
        if root is None:
            continue
        lo, hi = root["start_ms"], root["end_ms"]
        if hi > lo:
            intervals.append((lo, hi, stage))

    if not intervals:
        return ["_No stage intervals observed._", ""]

    t0 = min(lo for lo, _, _ in intervals)
    t1 = max(hi for _, hi, _ in intervals)
    span = (t1 - t0) or 1.0

    # Sample the timeline to find, per stage, the time no other stage occupied.
    steps = 2000
    solo: dict[str, float] = defaultdict(float)
    for i in range(steps):
        a = t0 + span * i / steps
        b = t0 + span * (i + 1) / steps
        active = [s for lo, hi, s in intervals if lo < b and hi > a]
        if len(active) == 1:
            solo[active[0]] += b - a

    # Union of the intervals by sweeping start/end events. Summing the per-stage
    # windows instead would double count every overlap.
    events = []
    for lo, hi, _ in intervals:
        events.append((lo, 1))
        events.append((hi, -1))
    events.sort()
    union = 0.0
    prev = t0
    depth = 0
    for pos, delta in events:
        if depth > 0:
            union += pos - prev
        depth += delta
        prev = pos

    sum_walls = sum(hi - lo for lo, hi, _ in intervals)

    lines = [
        "Sum of stage walls: **{:,.3f} ms**   Timeline union: **{:,.3f} ms**"
        "   Span: **{:,.3f} ms**".format(sum_walls, union, t1 - t0),
        "",
        "Sum exceeds the union by **{:,.3f} ms** -- that gap is the overlap the "
        "schedule is buying.".format(sum_walls - union),
        "",
        "| stage | wall ms | uncontended ms | overlapped ms | on critical path | timeline |",
        "|:--|---:|---:|---:|:--|:--|",
    ]
    for stage in CANONICAL_STAGE_ORDER:
        root = stage_roots.get(stage)
        if root is None:
            lines.append("| `{}` | - | - | - | - | |".format(stage))
            continue
        lo, hi = root["start_ms"], root["end_ms"]
        wall = hi - lo
        bar_len = max(1, int(round((wall / span) * width)))
        bar_start = int(round(((lo - t0) / span) * width))
        bar = " " * bar_start + "#" * bar_len
        s = solo.get(stage, 0.0)
        lines.append(
            "| `{}` | {:,.1f} | {:,.1f} | {:,.1f} | {:.1f}% | `{}` |".format(
                stage, wall, s, wall - s,
                (100.0 * s / wall) if wall else 0.0, bar,
            )
        )
    lines.extend([
        "",
        "_Uncontended_ is the time during a stage when no other stage was "
        "running. That portion is protected: nothing else could absorb it. "
        "Overlapped time may be hidden by a longer sibling, so reducing it may "
        "not move root wall.",
        "",
    ])
    return lines


def function_rollup(rows, owner, min_total: float, limit: int) -> list[str]:
    agg: dict[str, dict] = {}
    for r in rows:
        idx = r["idx"]
        if idx not in owner:
            continue
        name = r["qualified"] or r["function"]
        slot = agg.get(name)
        if slot is None:
            slot = {
                "name": name,
                "calls": 0,
                "total": 0.0,
                "self_total": 0.0,
                "max": 0.0,
                "stages": set(),
                "source_file": r["source_file"],
                "source_line": r["source_line"],
            }
            agg[name] = slot
        slot["calls"] += 1
        slot["total"] += r["wall_ms"]
        slot["self_total"] += r["exclusive_self_ms"]
        slot["max"] = max(slot["max"], r["wall_ms"])
        slot["stages"].add(owner[idx])

    ranked = sorted(
        (v for v in agg.values() if v["total"] >= min_total),
        key=lambda v: -v["total"],
    )
    lines = [
        "| total incl ms | calls | avg ms | max ms | total self ms | function | source | stages |",
        "|---:|---:|---:|---:|---:|:--|:--|:--|",
    ]
    for v in ranked[:limit]:
        avg = v["total"] / v["calls"] if v["calls"] else 0.0
        src = "{}:{}".format(
            (v["source_file"] or "").split("/")[-1], v["source_line"] or "",
        )
        lines.append(
            "| {t:,.3f} | {c} | {a:,.3f} | {m:,.3f} | {s:,.3f} | `{fn}` | "
            "`{src}` | {n} |".format(
                t=v["total"], c=v["calls"], a=avg, m=v["max"],
                s=v["self_total"], fn=v["name"], src=src,
                n=len(v["stages"]),
            )
        )
    if not ranked:
        lines.append(
            "| - | - | - | - | - | _no function reached the threshold_ | | |"
        )
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("session_dir", type=Path)
    ap.add_argument("--min-ms", type=float, default=1.0)
    ap.add_argument("--min-total-ms", type=float, default=1.0)
    ap.add_argument("--max-children", type=int, default=8)
    ap.add_argument("--top-functions", type=int, default=60)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    rows, by_index, stage_roots, owner, children = build(args.session_dir)

    out_path = args.out or (
        args.session_dir / "derived" / "golden_stage_report.md"
    )
    doc = [
        "# Golden stage decision report",
        "",
        "Source: `{}`".format(CALLS_CSV),
        "",
        "Calls in trace: **{:,}**".format(len(rows)),
        "",
        "Tree floor: **{:g} ms**   Function rollup floor: **{:g} ms** total "
        "inclusive".format(args.min_ms, args.min_total_ms),
        "",
        "## 1. Critical path and stage overlap",
        "",
    ]
    doc.extend(critical_path(stage_roots))

    doc.extend([
        "## 2. Function rollup across the whole request",
        "",
        "`total incl ms` sums each call's wall, so a function called 24 times at "
        "3 ms reads as 72 ms instead of hiding behind a mean. Inclusive wall "
        "contains its callees, so **totals are not additive down a call tree** "
        "-- `total self ms` is the non-overlapping part.",
        "",
    ])
    doc.extend(function_rollup(rows, owner, args.min_total_ms, args.top_functions))
    doc.append("")

    doc.extend([
        "## 3. Per-stage call trees",
        "",
        "Depth is uncapped; the wall floor limits it. Breadth is capped at {} "
        "children plus any child at or above 10% of its parent.".format(
            args.max_children,
        ),
        "",
    ])
    for stage in CANONICAL_STAGE_ORDER:
        root = stage_roots.get(stage)
        doc.append("### `{}`".format(stage))
        doc.append("")
        if root is None:
            doc.extend(["_Stage not observed._", ""])
            continue
        doc.append("- Stage wall: **{:,.3f} ms**".format(root["wall_ms"]))
        doc.append("")
        body = render_tree(
            root, children, args.min_ms, args.max_children, 10.0,
        )
        if len(body) <= 1:
            doc.extend(["_Nothing below the stage body reached the threshold._", ""])
            continue
        doc.extend(body)
        doc.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(doc), encoding="utf-8")
    print("wrote {}".format(out_path), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())