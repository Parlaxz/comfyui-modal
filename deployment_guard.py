"""
Fast pre-deploy guard that inspects the plugin root for undeployed generated
artifacts and reports effective filtered-source-context size.

Designed to be called immediately before ``modal deploy`` is spawned.  Fails
when any of the nine known generated directories contain files.  Prints the
migration command and resolved destination root.  Never deletes data.

Known generated directories (relative to plugin root)::

    output/
    test-results/
    playwright-report/
    .playwright-mcp/
    .experiments/
    .run_history/
    benchmark_runs/
    benchmark_logs/
    optimization_logs/

These are the directories that are excluded from Modal deployment source
filters but locally present after development/benchmark use.

Usage::

    from deployment_guard import guard_generated_artifacts
    guard_generated_artifacts(__file__)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from local_artifacts import get_local_data_root, get_plugin_root

#: The nine known generated artifact directories (relative to plugin root).
KNOWN_GENERATED_DIRS: List[str] = [
    "output",
    "test-results",
    "playwright-report",
    ".playwright-mcp",
    ".experiments",
    ".run_history",
    "benchmark_runs",
    "benchmark_logs",
    "optimization_logs",
]

#: Directories and patterns excluded from Modal deployment (source-context).
#: These are excluded when computing effective source size.
EXCLUDED_SIZE_DIRS: List[str] = [
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".ipynb_checkpoints",
    ".opencode",
    ".slim",
    # Nine generated artifact dirs (excluded by all Modal filters)
    "output",
    "test-results",
    "playwright-report",
    ".playwright-mcp",
    ".experiments",
    ".run_history",
    "benchmark_runs",
    "benchmark_logs",
    "optimization_logs",
    # Dev-only state dirs (excluded by .modalignore and runtime filters)
    ".comfymodal_experiments",
    ".custom_node_requirements",
    ".baked_custom_node_deps",
    ".presets",
    ".preset_blobs",
    "MagicMock",
]

EXCLUDED_SIZE_EXTENSIONS: Tuple[str, ...] = (
    ".pyc", ".pyo", ".md", ".tmp",
)


def _iter_source_files(plugin_root: Path) -> List[Path]:
    """Walk the plugin root and return non-excluded files."""
    files: List[Path] = []
    plugin_root_str = str(plugin_root.resolve())
    try:
        for dirpath_str, dirnames, filenames in os.walk(plugin_root_str, followlinks=False):
            dirpath = Path(dirpath_str)
            # Skip excluded directories at every depth
            dirnames[:] = [
                d for d in dirnames
                if d not in EXCLUDED_SIZE_DIRS and not (dirpath / d).is_symlink()
            ]
            for fn in filenames:
                ext = Path(fn).suffix.lower()
                if ext in EXCLUDED_SIZE_EXTENSIONS:
                    continue
                files.append(dirpath / fn)
    except OSError:
        pass  # best-effort
    return files


def _compute_source_context_size(plugin_root: Path) -> Tuple[int, int, List[Tuple[str, int]]]:
    """Compute total effective source size and largest top-level directories.

    Returns (total_bytes, file_count, [(dirname, size_bytes), ...]).
    """
    plugin_root = plugin_root.resolve()
    files = _iter_source_files(plugin_root)
    total = 0
    top_dirs: Dict[str, int] = {}
    for fp in files:
        try:
            sz = fp.stat().st_size
        except OSError:
            sz = 0
        total += sz
        # Record top-level directory contribution
        rel = fp.relative_to(plugin_root)
        top = str(rel.parts[0]) if rel.parts else ""
        if top:
            top_dirs[top] = top_dirs.get(top, 0) + sz
    sorted_dirs = sorted(top_dirs.items(), key=lambda x: -x[1])
    return total, len(files), sorted_dirs


def _scan_generated_dirs(plugin_root: Path) -> Dict[str, int]:
    """Scan known generated directories, returning {rel_path: total_bytes}.

    Only returns entries for directories that exist and contain files.
    """
    result: Dict[str, int] = {}
    for rel in KNOWN_GENERATED_DIRS:
        d = plugin_root / rel
        if d.is_symlink() or not d.is_dir():
            continue
        total = 0
        try:
            for dirpath_str, dirnames, filenames in os.walk(str(d.resolve()), followlinks=False):
                # Do not follow symlinks
                dirnames[:] = [x for x in dirnames if not os.path.islink(os.path.join(dirpath_str, x))]
                for fn in filenames:
                    fp = os.path.join(dirpath_str, fn)
                    try:
                        total += os.path.getsize(fp)
                    except OSError:
                        pass
        except OSError:
            continue
        if total > 0:
            result[rel] = total
    return result


def _format_bytes(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    elif b < 1024 ** 2:
        return f"{b / 1024:.1f} KB"
    elif b < 1024 ** 3:
        return f"{b / 1024 ** 2:.1f} MB"
    else:
        return f"{b / 1024 ** 3:.2f} GB"


def guard_generated_artifacts(
    plugin_root_str: Optional[str] = None,
    source_size_threshold_mb: float = 250.0,
) -> None:
    """Run the pre-deploy artifact guard.

    Args:
        plugin_root_str: Optional explicit plugin root.  When ``None``, uses
            ``local_artifacts.get_plugin_root()``.
        source_size_threshold_mb: Soft warning threshold for filtered source
            context size in MB. Default 250 MB.

    Raises:
        SystemExit: When any known generated directory contains files that
            should be migrated before deploy.

    Prints warnings and diagnostic info to stderr.
    """
    plugin_root = Path(plugin_root_str).resolve() if plugin_root_str else get_plugin_root()
    data_root = get_local_data_root()

    generated = _scan_generated_dirs(plugin_root)
    total_gen_bytes = sum(generated.values())

    source_bytes, source_files, top_dirs = _compute_source_context_size(plugin_root)

    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("  Deployment artifact guard")
    lines.append("=" * 60)
    lines.append(f"  Plugin root:     {plugin_root}")
    lines.append(f"  Data root:       {data_root}")
    lines.append(f"  Source files:    {source_files} ({_format_bytes(source_bytes)})")
    lines.append(f"  Generated bytes: {_format_bytes(total_gen_bytes)}")
    if top_dirs:
        lines.append("  Largest source dirs (not counting generated):")
        for name, sz in top_dirs[:5]:
            lines.append(f"    {name}: {_format_bytes(sz)}")

    fail = False
    if generated:
        lines.append("")
        lines.append("  !!! Generated artifacts detected !!!")
        lines.append("  The following directories contain data that should be migrated\n"
                      "  before deployment so they do not bloat the Modal image:")
        for rel, sz in sorted(generated.items()):
            lines.append(f"    {rel}/  ({_format_bytes(sz)})")
        lines.append("")
        lines.append(f"  Run:  python tools/migrate_local_artifacts.py")
        lines.append(f"  Destination:  {data_root}")
        lines.append("  Or migrate specific categories:")
        lines.append(f"    python tools/migrate_local_artifacts.py --categories output,experiments")
        lines.append("")
        fail = True

    if source_bytes > source_size_threshold_mb * 1024 * 1024:
        lines.append("")
        lines.append(f"  Warning: Filtered source context exceeds "
                      f"{source_size_threshold_mb:.0f} MB ({_format_bytes(source_bytes)}).")
        lines.append("  Consider cleaning unused files and generated directories.")
        lines.append("")

    lines.append("=" * 60)

    msg = "\n".join(lines)
    print(msg, file=sys.stderr)

    if fail:
        raise SystemExit(1)


def guard_if_generated_artifacts_exist() -> None:
    """Convenience entry point for CLI or ``__init__.py``.

    Exits with code 1 if any generated directory contains files.
    """
    try:
        guard_generated_artifacts()
    except SystemExit as exc:
        raise exc


if __name__ == "__main__":
    guard_generated_artifacts()
