"""
Side-effect-free, local-only artifact path resolver for comfyui-modal.

Derives the plugin root from ``__file__`` and the ComfyUI root as its parent.
Uses the ``COMFYMODAL_LOCAL_DATA_DIR`` environment variable when explicitly set,
otherwise resolves to ``<ComfyUI root>/comfymodal-data``.

All paths are absolute, normalized ``Path`` objects.  No ``mkdir`` or any
filesystem mutation occurs at import time.  All returned paths are guaranteed
normalized with ``Path.resolve()`` on first access (lazy).

Category mapping (flat):

    outputs             -> <data-root>/outputs
    playwright/test-results -> <data-root>/playwright/test-results
    playwright/report   -> <data-root>/playwright/report
    playwright/mcp      -> <data-root>/playwright/mcp
    experiments         -> <data-root>/experiments
    run-history         -> <data-root>/run-history
    benchmarks/runs     -> <data-root>/benchmarks/runs
    benchmarks/logs     -> <data-root>/benchmarks/logs
    optimization/logs   -> <data-root>/optimization/logs

Studio outputs are routed to ``<data-root>/outputs/studio``.
Auto-save modal outputs are routed to ``<data-root>/outputs/modal``.

The resolver is **never** imported by ``comfyapp.py`` because ``comfyapp.py``
must not depend on local-only path logic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

# ── Lazy root computation ──────────────────────────────────────────────────

_PLUGIN_ROOT: Optional[Path] = None
_COMFYUI_ROOT: Optional[Path] = None
_DATA_ROOT: Optional[Path] = None


def _resolve_plugin_root() -> Path:
    """Return the absolute plugin root (the directory containing this file)."""
    return Path(__file__).resolve().parent


def _resolve_comfyui_root() -> Path:
    """Return the ComfyUI root (parent of the plugin root).

    The expected layout is::

        ComfyUI/
          custom_nodes/
            comfyui-modal/    ← plugin root
          ...
    """
    return _resolve_plugin_root().parent.parent


def get_plugin_root() -> Path:
    """Return the absolute plugin root (lazy, cached)."""
    global _PLUGIN_ROOT
    if _PLUGIN_ROOT is None:
        _PLUGIN_ROOT = _resolve_plugin_root()
    return _PLUGIN_ROOT


def get_comfyui_root() -> Path:
    """Return the absolute ComfyUI root (lazy, cached)."""
    global _COMFYUI_ROOT
    if _COMFYUI_ROOT is None:
        _COMFYUI_ROOT = _resolve_comfyui_root()
    return _COMFYUI_ROOT


def get_local_data_root() -> Path:
    """Return the local data root directory.

    Uses ``COMFYMODAL_LOCAL_DATA_DIR`` if set, otherwise defaults to
    ``<ComfyUI root>/comfymodal-data``.

    The path is resolved to an absolute, normalized form on first access.
    No directory is created at call time — the caller may ``mkdir`` as needed.
    """
    global _DATA_ROOT
    if _DATA_ROOT is not None:
        return _DATA_ROOT

    env_val = os.environ.get("COMFYMODAL_LOCAL_DATA_DIR", "").strip()
    if env_val:
        _DATA_ROOT = Path(env_val).resolve()
    else:
        _DATA_ROOT = get_comfyui_root() / "comfymodal-data"

    return _DATA_ROOT


def _reset_caches_for_testing(data_root: Optional[str] = None) -> None:
    """Reset all cached paths — for testing only."""
    global _PLUGIN_ROOT, _COMFYUI_ROOT, _DATA_ROOT
    _PLUGIN_ROOT = None
    _COMFYUI_ROOT = None
    _DATA_ROOT = None
    if data_root is not None:
        os.environ["COMFYMODAL_LOCAL_DATA_DIR"] = data_root


# ── Category path functions ─────────────────────────────────────────────────

#: Flat category mapping: logical key → relative path under data root.
CATEGORY_MAP: Dict[str, str] = {
    # Legacy categories
    "output": "outputs",
    "test-results": "playwright/test-results",
    "playwright-report": "playwright/report",
    ".playwright-mcp": "playwright/mcp",
    ".experiments": "experiments",
    ".run_history": "run-history",
    "benchmark_runs": "benchmarks/runs",
    "benchmark_logs": "benchmarks/logs",
    "optimization_logs": "optimization/logs",
    # Sub-categories used by producers
    "outputs/studio": "outputs/studio",
    "outputs/modal": "outputs/modal",
    "benchmarks/runs": "benchmarks/runs",
    "benchmarks/logs": "benchmarks/logs",
    "optimization/logs": "optimization/logs",
}

#: Category aliases for migration CLI.
CATEGORY_ALIASES: Dict[str, List[str]] = {
    "output": ["outputs"],
    "test-results": ["playwright/test-results"],
    "playwright-report": ["playwright/report"],
    "playwright-mcp": ["playwright/mcp", ".playwright-mcp"],
    "experiments": [".experiments"],
    "run-history": ["run-history", ".run_history"],
    "benchmark-runs": ["benchmarks/runs", "benchmark_runs"],
    "benchmark-logs": ["benchmarks/logs", "benchmark_logs"],
    "optimization-logs": ["optimization/logs", "optimization_logs"],
}

#: Reverse mapping: source-category-key → canonical external key.
LEGACY_TO_CANONICAL: Dict[str, str] = {
    "output": "output",
    "test-results": "test-results",
    "playwright-report": "playwright-report",
    ".playwright-mcp": "playwright-mcp",
    ".experiments": "experiments",
    ".run_history": "run-history",
    "benchmark_runs": "benchmark-runs",
    "benchmark_logs": "benchmark-logs",
    "optimization_logs": "optimization-logs",
}


def _category_rel_path(category: str) -> str:
    """Return the relative path string for a category.

    Accepts both short/long keys and canonical keys.
    """
    # Direct canonical or legacy key
    if category in CATEGORY_MAP:
        return CATEGORY_MAP[category]
    # Check aliases
    for canonical, rel in CATEGORY_MAP.items():
        if canonical == category:
            return rel
    raise KeyError(
        f"Unknown artifact category: {category!r}. "
        f"Known: {', '.join(sorted(CATEGORY_MAP.keys()))}"
    )


def _category_path(category: str) -> Path:
    return get_local_data_root() / _category_rel_path(category)


def get_outputs_dir() -> Path:
    """<data-root>/outputs"""
    return _category_path("output")


def get_studio_outputs_dir() -> Path:
    """<data-root>/outputs/studio"""
    return _category_path("outputs/studio")


def get_modal_outputs_dir() -> Path:
    """<data-root>/outputs/modal"""
    return _category_path("outputs/modal")


def get_playwright_test_results_dir() -> Path:
    """<data-root>/playwright/test-results"""
    return _category_path("test-results")


def get_playwright_report_dir() -> Path:
    """<data-root>/playwright/report"""
    return _category_path("playwright-report")


def get_playwright_mcp_dir() -> Path:
    """<data-root>/playwright/mcp"""
    return _category_path(".playwright-mcp")


def get_experiments_dir() -> Path:
    """<data-root>/experiments"""
    return _category_path(".experiments")


def get_run_history_dir() -> Path:
    """<data-root>/run-history"""
    return _category_path(".run_history")


def get_benchmark_runs_dir() -> Path:
    """<data-root>/benchmarks/runs"""
    return _category_path("benchmarks/runs")


def get_benchmark_logs_dir() -> Path:
    """<data-root>/benchmarks/logs"""
    return _category_path("benchmark_logs")


def get_optimization_logs_dir() -> Path:
    """<data-root>/optimization/logs"""
    return _category_path("optimization_logs")
