#!/usr/bin/env python3
"""CLI renderer for the V2 DYNAMIC CRITICAL PATH GANTT.

Standalone: bootstraps ``sys.path`` so it runs from the repo root via
``python tools/render_dynamic_gantt.py <run_dir>``.
"""
from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from comfymodal_runtime.dynamic_gantt import (  # noqa: E402
    GANTT_TITLE,
    build_rows,
    closure_reports,
    completeness_matrix,
    compute_windows,
    critical_path_summary,
    detect_label_conflicts,
    load_run_artifacts,
    render_full_report,
    render_window,
)


def _assemble(payload, rows, wins: dict, width: int) -> str:
    """Same section order as render_full_report, honoring a custom bar width."""
    out = [GANTT_TITLE, "\u2501" * min(width, 60)]
    ls = payload.raw.get("loader_selection") or {}
    fallbacks = sorted(k for k, v in ls.items() if isinstance(v, dict) and v.get("fallback_attempted"))
    out.append(f"request: {payload.request_id}   profile: {payload.raw.get('profile_name') or '?'}   "
               f"artifact: {payload.raw.get('run_file')}")
    out.append("FALLBACK RUN \u2014 loader fallback attempted for: " + ", ".join(fallbacks)
               if fallbacks else "loader fallback: none")
    for w in payload.warnings:
        out.append(f"warning: {w}")
    out.append("")
    for name, bounds in wins.items():
        origin = bounds[0] if name == "FULL APPLICATION" else None
        out.append(render_window(rows, bounds, name, width_chars=width, origin_mono_ns=origin))
        out.append("")
    closures = closure_reports(payload, rows)
    if closures:
        out.extend(closures)
        out.append("")
    conflicts = detect_label_conflicts(payload, rows)
    out.append("LABEL CONFLICTS: " + ("none" if not conflicts else ""))
    for c in conflicts:
        out.append(f"  ! {c}")
    out.append("")
    out.append(completeness_matrix(payload))
    out.append("")
    out.append(critical_path_summary(payload, rows))
    return "\n".join(out)


def main(argv=None) -> int:
    try:  # block/bar glyphs need UTF-8 stdout on Windows consoles
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(
        description="Render the V2 dynamic event-driven critical-path Gantt for a benchmark run dir.")
    ap.add_argument("run_dir", help="benchmark run directory containing run_0.json / run_*_sample.json")
    ap.add_argument("--windows", default="",
                    help="comma-separated window-name substrings to render (default: all)")
    ap.add_argument("--width", type=int, default=110, help="render width in characters (default: 110)")
    ap.add_argument("--out", default=None, help="also write the report to this text file")
    args = ap.parse_args(argv)

    payload = load_run_artifacts(args.run_dir)
    rows = payload.rows or build_rows(payload)
    wins = compute_windows(payload, rows)
    if args.windows:
        want = [w.strip().lower() for w in args.windows.split(",") if w.strip()]
        wins = {k: v for k, v in wins.items() if any(w in k.lower() for w in want)}
    if args.width == 110 and not args.windows:
        report = render_full_report(payload, windows=wins)
    else:
        report = _assemble(payload, rows, wins, args.width)
    print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
