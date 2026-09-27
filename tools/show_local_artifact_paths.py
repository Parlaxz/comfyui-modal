#!/usr/bin/env python3
"""
Print the local artifact root and all requested category paths.

Usage::

    python tools/show_local_artifact_paths.py
    python tools/show_local_artifact_paths.py --categories outputs,experiments
    python tools/show_local_artifact_paths.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Bootstrap plugin root onto sys.path for direct execution (python tools/...)
_script_dir = Path(__file__).resolve().parent.parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

from local_artifacts import (
    get_local_data_root,
    get_outputs_dir,
    get_studio_outputs_dir,
    get_modal_outputs_dir,
    get_playwright_test_results_dir,
    get_playwright_report_dir,
    get_playwright_mcp_dir,
    get_experiments_dir,
    get_run_history_dir,
    get_benchmark_runs_dir,
    get_benchmark_logs_dir,
    get_optimization_logs_dir,
    get_plugin_root,
    get_comfyui_root,
)

CATEGORY_FUNCTIONS = {
    "data-root": get_local_data_root,
    "outputs": get_outputs_dir,
    "outputs/studio": get_studio_outputs_dir,
    "outputs/modal": get_modal_outputs_dir,
    "playwright/test-results": get_playwright_test_results_dir,
    "playwright/report": get_playwright_report_dir,
    "playwright/mcp": get_playwright_mcp_dir,
    "experiments": get_experiments_dir,
    "run-history": get_run_history_dir,
    "benchmarks/runs": get_benchmark_runs_dir,
    "benchmarks/logs": get_benchmark_logs_dir,
    "optimization/logs": get_optimization_logs_dir,
}

CATEGORY_ALIASES = {
    "output": "outputs",
    "test-results": "playwright/test-results",
    "playwright-report": "playwright/report",
    ".playwright-mcp": "playwright/mcp",
    ".experiments": "experiments",
    ".run_history": "run-history",
    "benchmark_runs": "benchmarks/runs",
    "benchmark_logs": "benchmarks/logs",
    "optimization_logs": "optimization/logs",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Show local artifact paths.")
    parser.add_argument(
        "--categories", type=str, default="",
        help="Comma-separated categories to show (default: all).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON.",
    )
    args = parser.parse_args()

    # Resolve requested categories
    requested: set[str] = set()
    if args.categories:
        for token in args.categories.split(","):
            token = token.strip()
            if not token:
                continue
            if token == "all" or token == "":
                requested = set(CATEGORY_FUNCTIONS.keys())
                break
            canonical = CATEGORY_ALIASES.get(token, token)
            if canonical in CATEGORY_FUNCTIONS:
                requested.add(canonical)
            else:
                print(f"Warning: unknown category {token!r}", file=sys.stderr)
    else:
        requested = set(CATEGORY_FUNCTIONS.keys())

    # Ensure data-root is always first
    category_order = ["data-root"] + [k for k in CATEGORY_FUNCTIONS if k != "data-root"]

    if args.json:
        data: dict[str, str] = {}
        for key in category_order:
            if key in requested:
                fn = CATEGORY_FUNCTIONS[key]
                data[key] = str(fn())
        print(json.dumps(data, indent=2))
        return

    # Text output
    print(f"Plugin root:  {get_plugin_root()}")
    print(f"ComfyUI root: {get_comfyui_root()}")
    print(f"")
    print(f"Data root:    {get_local_data_root()}")
    print(f"")

    max_len = max(len(k) for k in requested) if requested else 20
    for key in category_order:
        if key in requested:
            fn = CATEGORY_FUNCTIONS[key]
            path = fn()
            exists_mark = " (exists)" if path.exists() else ""
            print(f"  {key:<{max_len}}  {path}{exists_mark}")


if __name__ == "__main__":
    main()
