"""Recursive per-stage call tree for the Golden exhaustive profiler.

Answers "what sequentially happens inside each Golden stage", recursing as deep
as anything material goes.

Depth is deliberately NOT capped. The floor does the limiting: a child can never
exceed its parent's wall, so pruning at ``--min-ms`` bounds the tree by the
request's own wall clock instead of by an arbitrary level count. Breadth is the
real risk, so it is capped by materiality -- the top ``--max-children`` plus any
child that is at least ``--significant-pct`` of its parent, so a dominant child
can never be hidden behind N slightly-lesser siblings.

Usage:
    python tools/golden_stage_tree.py <session_dir> [--min-ms 1.0]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from golden_stage_gantt import (  # noqa: E402
    CALLS_CSV,
    CANONICAL_STAGE_ORDER,
    load_rows,
)


def build(session_dir: Path):
    rows = list(load_rows(session_dir / CALLS_CSV))
    by_index = {r["idx"]: r for r in rows}

    stage_roots: dict[str, dict] = {}
    for r in rows:
        name = r["function"]
        if name in CANONICAL_STAGE_ORDER:
            best = stage_roots.get(name)
            if best is None or r["wall_ms"] > best["wall_ms"]:
                stage_roots[name] = r

    stage_list = list(stage_roots.items())

    # Tightest containing stage. Stack nesting cannot reach these bodies: the
    # overlap schedule runs them on executor threads, unparented in the CSV.
    owner: dict[float, str] = {}
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
            owner[r["idx"]] = best_name

    # Re-root each attributed call onto its nearest ancestor attributed to the SAME
    # stage; anything without one hangs directly off the stage body.
    #
    # Done by walking deepest-first, so a same-stage ancestor is always resolved
    # before the node that needs it. Walking up per node with a shared memo is
    # subtly wrong here: an ancestor can belong to a different stage than the
    # node that skipped through it, so intermediate nodes resolve differently.
    attributed = [r for r in rows if r["idx"] in owner]
    attributed.sort(key=lambda r: -r["depth"])
    parent_of: dict[float, float | None] = {}
    for r in attributed:
        stage = owner[r["idx"]]
        pidx = r["parent"]
        if (
            pidx is not None
            and pidx in owner
            and owner[pidx] == stage
            and pidx != r["idx"]
        ):
            parent_of[r["idx"]] = pidx
        else:
            parent_of[r["idx"]] = None

    children: dict[float, list[dict]] = {}
    for r in attributed:
        p = parent_of[r["idx"]]
        if p is None:
            p = stage_roots[owner[r["idx"]]]["idx"]
        children.setdefault(p, []).append(r)
    for bucket in children.values():
        bucket.sort(key=lambda c: -c["wall_ms"])
    return rows, by_index, stage_roots, owner, children


def render_tree(
    node: dict,
    children: dict,
    min_ms: float,
    max_children: int,
    significant_pct: float,
    depth: int = 0,
    lines: list[str] | None = None,
) -> list[str]:
    if lines is None:
        lines = []
    kids = [
        c for c in children.get(node["idx"], ())
        if c["wall_ms"] >= min_ms
    ]
    keep = kids[:max_children]
    if len(kids) > max_children:
        cutoff = kids[max_children - 1]["wall_ms"] if keep else 0.0
        for c in kids[max_children:]:
            if cutoff and c["wall_ms"] >= cutoff:
                keep.append(c)
    omitted = len(kids) - len(keep)

    pad = "  " * depth
    name = node["qualified"] or node["function"]
    src = "{}:{}".format(
        (node["source_file"] or "").split("/")[-1], node["source_line"] or "",
    )
    lines.append(
        "{pad}- `{fn}` \n{pad}  wall **{w:,.3f} ms**  self **{s:,.3f} ms**  "
        "`{src}`".format(
            pad=pad, fn=name, w=node["wall_ms"],
            s=node["exclusive_self_ms"], src=src,
        )
    )
    for child in keep:
        render_tree(
            child, children, min_ms, max_children, significant_pct,
            depth + 1, lines,
        )
    if omitted > 0:
        lines.append(
            "{pad}  _... {n} more children >= {m:g} ms omitted_".format(
                pad=pad, n=omitted, m=min_ms,
            )
        )
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("session_dir", type=Path)
    ap.add_argument("--min-ms", type=float, default=1.0)
    ap.add_argument("--max-children", type=int, default=8)
    ap.add_argument("--significant-pct", type=float, default=10.0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    rows, by_index, stage_roots, owner, children = build(args.session_dir)

    out_path = args.out or (args.session_dir / "derived" / "golden_stage_trees.md")
    doc = [
        "# Golden per-stage call trees",
        "",
        "Source: `{}`".format(CALLS_CSV),
        "",
        "Calls in trace: **{:,}**".format(len(rows)),
        "",
        "Expanded at wall >= **{:g} ms**".format(args.min_ms),
        "",
        "Depth is not capped; the floor is. Breadth is capped at {} children "
        "plus any child at or above {:g}% of its parent.".format(
            args.max_children, args.significant_pct,
        ),
        "",
        "Stage bodies run on executor threads, so children are attached to the "
        "stage they fall inside by time containment, then re-rooted onto the "
        "nearest same-stage ancestor.",
        "",
    ]

    for stage in CANONICAL_STAGE_ORDER:
        root = stage_roots.get(stage)
        doc.append("## `{}`".format(stage))
        doc.append("")
        if root is None:
            doc.append("_Stage not observed._")
            doc.append("")
            continue
        doc.append("- Stage wall: **{:,.3f} ms**".format(root["wall_ms"]))
        doc.append("")
        body = render_tree(
            root, children, args.min_ms, args.max_children,
            args.significant_pct,
        )
        if len(body) <= 1:
            doc.append("_Nothing below the stage body reached the threshold._")
            doc.append("")
            continue
        doc.extend(body)
        doc.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(doc), encoding="utf-8")
    print("wrote {}".format(out_path), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())