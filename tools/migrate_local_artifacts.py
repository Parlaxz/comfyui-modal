#!/usr/bin/env python3
"""
Idempotent migration tool for comfyui-modal local artifacts.

Moves generated data from the plugin root to the external data root defined
by ``local_artifacts``.  Copy-verify-remove per category.  Never follows
directory symlinks.  On file-name conflicts, both files are preserved with a
timestamp/digest suffix.

Usage::

    # Preview what would be moved
    python tools/migrate_local_artifacts.py --dry-run

    # Move everything
    python tools/migrate_local_artifacts.py

    # Move specific categories (comma-separated and/or repeated --categories)
    python tools/migrate_local_artifacts.py --categories output,experiments

    # Move just one category
    python tools/migrate_local_artifacts.py --categories benchmark_runs

    # Custom plugin root (for testing)
    python tools/migrate_local_artifacts.py --plugin-root /tmp/test-plugin
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Bootstrap plugin root onto sys.path for direct execution (python tools/...)
_script_dir = Path(__file__).resolve().parent.parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))


# ── Category mapping: legacy relative path → external canonical relative path ──

CATEGORY_MAP: Dict[str, str] = {
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

# All category keys available for migration
ALL_CATEGORIES: List[str] = sorted(CATEGORY_MAP.keys())

# Aliases for CLI convenience
CATEGORY_ALIASES: Dict[str, List[str]] = {
    "outputs": ["output"],
    "playwright": ["test-results", "playwright-report", ".playwright-mcp"],
    "benchmarks": ["benchmark_runs", "benchmark_logs"],
    "experiments": [".experiments"],
    "run-history": [".run_history"],
    "optimization": ["optimization_logs"],
}


def _resolve_categories(selected: List[str]) -> List[str]:
    """Resolve user-supplied category names into canonical keys.

    Accepts comma-separated, repeated flags, aliases, and 'all'.
    """
    if not selected:
        return list(ALL_CATEGORIES)

    result: List[str] = []
    seen: Set[str] = set()

    for raw_list in selected:
        for token in raw_list.split(","):
            token = token.strip().lower()
            if not token:
                continue
            if token == "all":
                return list(ALL_CATEGORIES)
            if token in CATEGORY_MAP:
                if token not in seen:
                    result.append(token)
                    seen.add(token)
            elif token in CATEGORY_ALIASES:
                for alias_cat in CATEGORY_ALIASES[token]:
                    if alias_cat not in seen:
                        result.append(alias_cat)
                        seen.add(alias_cat)
            else:
                print(f"Warning: Unknown category {token!r}, skipping. "
                      f"Known: {', '.join(sorted(CATEGORY_MAP.keys()))}",
                      file=sys.stderr)

    if not result:
        return list(ALL_CATEGORIES)
    return result


# ── Stats tracking ──────────────────────────────────────────────────────────

class MigrationStats:
    """Per-category and total statistics."""

    def __init__(self) -> None:
        self.categories: Dict[str, Dict[str, int]] = {}
        self.total_files = 0
        self.total_dirs = 0
        self.total_bytes = 0

    def add_category(self, cat: str) -> None:
        if cat not in self.categories:
            self.categories[cat] = {"files": 0, "dirs": 0, "bytes": 0}

    def add_file(self, cat: str, size: int) -> None:
        self.add_category(cat)
        self.categories[cat]["files"] += 1
        self.categories[cat]["bytes"] += size
        self.total_files += 1
        self.total_bytes += size

    def add_dir(self, cat: str) -> None:
        self.add_category(cat)
        self.categories[cat]["dirs"] += 1
        self.total_dirs += 1


# ── File helpers ────────────────────────────────────────────────────────────

BLOCK_SIZE = 65536


def _file_hash(path: Path) -> str:
    """SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(BLOCK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _safe_copy2(src: Path, dst: Path) -> None:
    """Copy file with metadata preservation."""
    shutil.copy2(src, dst)


def _conflict_resolve_path(dst: Path) -> Path:
    """Generate a non-conflicting path by appending a timestamp/short digest.
    
    Never overwrites an existing file — appends a counter if needed.
    """
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    digest = _file_hash(dst)[:8]
    stem = dst.stem
    ext = dst.suffix
    candidate = dst.parent / f"{stem}_{now}_{digest}{ext}"
    counter = 0
    while candidate.exists():
        counter += 1
        candidate = dst.parent / f"{stem}_{now}_{digest}_{counter}{ext}"
    return candidate


def _count_files_and_bytes(path: Path) -> Tuple[int, int]:
    """Count files and total bytes under a path (non-recursive for single file)."""
    if path.is_file():
        return 1, _file_size(path)
    total_files = 0
    total_bytes = 0
    try:
        for dirpath_str, dirnames, filenames in os.walk(str(path), followlinks=False):
            for fn in filenames:
                fp = os.path.join(dirpath_str, fn)
                total_files += 1
                try:
                    total_bytes += os.path.getsize(fp)
                except OSError:
                    pass
    except OSError:
        pass
    return total_files, total_bytes


def _verify_directory_contents(src: Path, dst: Path) -> bool:
    """Verify that destination has the same files (by name and hash) as source.

    This is a shallow name-and-hash verification for files that were *copied*.
    After a full merge, the destination may have extra files (from previous runs
    or conflict suffixes), so we verify that every source file exists at dest
    with matching hash.
    """
    if src.is_file():
        if not dst.is_file():
            return False
        return _file_hash(src) == _file_hash(dst)

    # Directory: walk source, check corresponding files exist in dest
    for dirpath_str, dirnames, filenames in os.walk(str(src), followlinks=False):
        dirpath = Path(dirpath_str)
        rel = dirpath.relative_to(src)
        dest_dir = dst / rel
        for fn in filenames:
            src_file = dirpath / fn
            dst_file = dest_dir / fn
            if not dst_file.is_file():
                return False
            if _file_hash(src_file) != _file_hash(dst_file):
                return False
    return True


# ── Core migration logic ────────────────────────────────────────────────────

def _remove_readonly(func, path, exc_info):
    """Clear the readonly bit and retry."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def migrate_category(
    cat: str,
    plugin_root: Path,
    data_root: Path,
    dry_run: bool = False,
    stats: Optional[MigrationStats] = None,
) -> MigrationStats:
    """Migrate one category from plugin_root to data_root.

    Returns a MigrationStats for this category.
    """
    if stats is None:
        stats = MigrationStats()

    src_rel = cat
    dst_rel = CATEGORY_MAP[cat]
    src = plugin_root / src_rel
    dst = data_root / dst_rel

    if not src.exists():
        stats.add_category(cat)
        return stats

    # Safety: check symlink BEFORE resolve() so we never follow a link
    if src.is_symlink():
        print(f"  Skipping {src_rel}/ (symlink)", file=sys.stderr)
        stats.add_category(cat)
        return stats

    src = src.resolve()

    if src.is_file():
        # Single-file category (unlikely, but handle)
        if not dry_run:
            os.makedirs(dst.parent, exist_ok=True)
        info = _migrate_file(src, dst, dry_run)
        if info:
            stats.add_file(cat, info["size"])
        return stats

    if not src.is_dir():
        stats.add_category(cat)
        return stats

    # ── Copy directory tree ───────────────────────────────────────────
    print(f"  {src_rel}/  ->  {dst}/")
    stats.add_category(cat)

    # Track all (src, actual_dst) pairs for verification
    copied_pairs: List[Tuple[Path, Path]] = []
    total_copied_files = 0
    total_copied_bytes = 0
    identical_skipped = 0
    identical_bytes = 0
    symlink_skipped_files = 0
    symlink_skipped_bytes = 0

    for dirpath_str, dirnames, filenames in os.walk(str(src), followlinks=False):
        dirpath = Path(dirpath_str)
        rel = dirpath.relative_to(src)
        dst_dir = dst / rel

        # Do not follow directory symlinks
        dirnames[:] = [d for d in dirnames if not (dirpath / d).is_symlink()]

        if not dry_run:
            os.makedirs(dst_dir, exist_ok=True)

        if rel != Path("."):
            stats.add_dir(cat)  # count dirs in both dry-run and real mode

        for fn in filenames:
            src_file = dirpath / fn
            dst_file = dst_dir / fn

            if src_file.is_symlink():
                sz = _file_size(src_file)
                symlink_skipped_files += 1
                symlink_skipped_bytes += sz
                continue  # skip symlinked files

            if dry_run:
                try:
                    sz = src_file.stat().st_size
                except OSError:
                    sz = 0
                total_copied_files += 1
                total_copied_bytes += sz
                stats.add_file(cat, sz)
                continue

            # Real copy with conflict resolution
            if dst_file.exists():
                if _file_hash(src_file) == _file_hash(dst_file):
                    # Already identical — count toward verified dest contribution
                    sz = _file_size(src_file)
                    identical_skipped += 1
                    identical_bytes += sz
                    continue
                # Conflict: keep both
                resolved = _conflict_resolve_path(dst_file)
                _safe_copy2(src_file, resolved)
                copied_pairs.append((src_file, resolved))
                sz = _file_size(src_file)
                total_copied_files += 1
                total_copied_bytes += sz
                stats.add_file(cat, sz)
            else:
                _safe_copy2(src_file, dst_file)
                copied_pairs.append((src_file, dst_file))
                sz = _file_size(src_file)
                total_copied_files += 1
                total_copied_bytes += sz
                stats.add_file(cat, sz)

    # ── Verification & source removal ─────────────────────────────────
    if not dry_run:
        if identical_skipped:
            print(f"    Identical (skipped): {identical_skipped} files")
        print(f"    Copied {total_copied_files} files ({_format_bytes(total_copied_bytes)})")

        # Verify every (src, actual_dst) pair
        mismatches: List[str] = []
        for src_file, actual_dst in copied_pairs:
            if not actual_dst.is_file():
                mismatches.append(f"  Missing destination: {actual_dst}")
            elif _file_hash(src_file) != _file_hash(actual_dst):
                mismatches.append(f"  Hash mismatch: {src_file} vs {actual_dst}")

        if mismatches:
            error_msg = (
                f"VERIFICATION FAILED for {cat}. Source data left intact.\n"
                + "\n".join(mismatches)
            )
            print(error_msg, file=sys.stderr)
            if copied_pairs:
                conflict_pairs = [(s, d) for s, d in copied_pairs if s.name != d.name]
                if conflict_pairs:
                    print(f"    Conflicts resolved: {len(conflict_pairs)}", file=sys.stderr)
                    for s, d in conflict_pairs:
                        print(f"      {s.name}  ->  {d.name}", file=sys.stderr)
            raise SystemExit(1)

        if copied_pairs:
            conflict_pairs = [(s, d) for s, d in copied_pairs if s.name != d.name]
            if conflict_pairs:
                print(f"    Conflicts resolved: {len(conflict_pairs)}")
                for s, d in conflict_pairs:
                    print(f"      {s.name}  ->  {d.name}")

        # Verify source file count/bytes match destination contribution
        verified_dest_files = total_copied_files + identical_skipped + symlink_skipped_files
        verified_dest_bytes = total_copied_bytes + identical_bytes + symlink_skipped_bytes
        src_count_before, src_bytes_before = _count_files_and_bytes(src)
        if src_count_before != verified_dest_files or src_bytes_before != verified_dest_bytes:
            print(f"    Source check: {src_count_before} files ({_format_bytes(src_bytes_before)})", file=sys.stderr)
            print(f"    Dest contrib: {verified_dest_files} files ({_format_bytes(verified_dest_bytes)})", file=sys.stderr)
            if src_count_before != verified_dest_files:
                print(f"    MISMATCH: source file count ({src_count_before}) != verified dest ({verified_dest_files})", file=sys.stderr)
                print(f"      Copied: {total_copied_files}, Identical skipped: {identical_skipped}"
                      f", Symlink skipped: {symlink_skipped_files}", file=sys.stderr)
                raise SystemExit(1)

        # ── Remove source ──────────────────────────────────────────────
        try:
            if src.is_dir():
                shutil.rmtree(str(src), onerror=_remove_readonly)
            else:
                src.unlink()
            print(f"    Removed source: {src_rel}/")
        except OSError as exc:
            print(f"    Warning: could not remove source {src_rel}/: {exc}", file=sys.stderr)

    return stats


def _migrate_file(src: Path, dst: Path, dry_run: bool) -> Optional[Dict]:
    """Migrate a single file category."""
    sz = _file_size(src)
    if dry_run:
        return {"size": sz}
    if dst.exists():
        if _file_hash(src) == _file_hash(dst):
            return None  # already same
        dst = _conflict_resolve_path(dst)
    _safe_copy2(src, dst)
    if not _file_hash(src) == _file_hash(dst):
        print(f"    Verification failed for {src}", file=sys.stderr)
        raise SystemExit(1)
    src.unlink()
    return {"size": sz}


# ── Display helpers ─────────────────────────────────────────────────────────

def _format_bytes(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    elif b < 1024 ** 2:
        return f"{b / 1024:.1f} KB"
    elif b < 1024 ** 3:
        return f"{b / 1024 ** 2:.1f} MB"
    else:
        return f"{b / 1024 ** 3:.2f} GB"


def _print_summary(stats: MigrationStats, dry_run: bool) -> None:
    """Print migration summary."""
    label = "DRY RUN — " if dry_run else ""
    print(f"\n{label}Migration summary:")
    print(f"  {'Category':<25} {'Files':>8} {'Dirs':>6} {'Bytes':>12}")
    print(f"  {'-'*25} {'-'*8} {'-'*6} {'-'*12}")
    for cat in sorted(stats.categories.keys()):
        info = stats.categories[cat]
        print(f"  {cat:<25} {info['files']:>8} {info['dirs']:>6} {_format_bytes(info['bytes']):>12}")
    print(f"  {'-'*25} {'-'*8} {'-'*6} {'-'*12}")
    print(f"  {'TOTAL':<25} {stats.total_files:>8} {stats.total_dirs:>6} {_format_bytes(stats.total_bytes):>12}")


# ── Main CLI ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate local comfyui-modal artifacts to external data root.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be moved without making changes.",
    )
    parser.add_argument(
        "--categories", action="append", default=[],
        help="Comma-separated categories to migrate, or 'all'. Can be repeated.",
    )
    parser.add_argument(
        "--plugin-root", type=str, default=None,
        help="Override plugin root (for testing). Default: auto-detect.",
    )
    args = parser.parse_args()

    # ── Resolve paths ───────────────────────────────────────────────
    if args.plugin_root:
        plugin_root = Path(args.plugin_root).resolve()
        # Import local to avoid circular issues during testing
        from local_artifacts import get_local_data_root
        data_root = get_local_data_root()
    else:
        from local_artifacts import get_local_data_root, get_plugin_root
        plugin_root = get_plugin_root()
        data_root = get_local_data_root()

    categories = _resolve_categories(args.categories)

    # ── Print header ────────────────────────────────────────────────
    print(f"Plugin root:  {plugin_root}")
    print(f"Data root:    {data_root}")
    print(f"Categories:   {', '.join(categories)}")
    if args.dry_run:
        print("*** DRY RUN — no files will be changed ***")
    print()

    stats = MigrationStats()
    for cat in categories:
        migrate_category(cat, plugin_root, data_root, dry_run=args.dry_run, stats=stats)

    _print_summary(stats, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
