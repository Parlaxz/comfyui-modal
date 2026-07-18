"""Canonical deployment source manifest / DeploymentIdentity builder.

Excludes ``reference/``, ``*.ref``, ``*.v21610_backup``, ``before_v2_*``,
benchmark outputs, logs, screenshots, temporary JSON, local Studio outputs,
generated state, ``.git``, ``node_modules``, ``tests``, and ``docs`` unless
explicitly allowed.

Pure functions — suitable for unit tests without Modal or volume access.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterator, Sequence

from comfymodal_runtime.contracts import DeploymentIdentity


# ── Allowed source extensions for custom-node code ───────────────────────

ALLOWED_SOURCE_EXTENSIONS: frozenset[str] = frozenset({".py", ".js", ".mjs"})

# ── Excluded directory names (matched at any depth) ──────────────────────

EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".opencode",
    ".slim",
    ".comfymodal_experiments",
    ".custom_node_requirements",
    ".baked_custom_node_deps",
    ".presets",
    ".preset_blobs",
    "MagicMock",
    "reference",
    "docs",
    "tests",
    "benchmark_runs",
    "benchmark_logs",
    "optimization_logs",
    "output",
    "test-results",
    "playwright-report",
    ".playwright-mcp",
    ".experiments",
    ".run_history",
})

# ── Excluded file extensions (case-insensitive) ──────────────────────────

EXCLUDED_EXTENSIONS: frozenset[str] = frozenset({
    ".pyc",
    ".pyo",
    ".md",
    ".tmp",
    ".ref",
    ".log",
})

# ── Excluded filename prefixes ───────────────────────────────────────────

EXCLUDED_PREFIXES: tuple[str, ...] = ("before_v2_",)

# ── Excluded filename infixes ────────────────────────────────────────────

EXCLUDED_INFIXES: tuple[str, ...] = (".v21610_backup",)

# ── Excluded exact filenames ─────────────────────────────────────────────

EXCLUDED_FILENAMES: frozenset[str] = frozenset({
    ".gitignore",
    ".deploy_log",
    "modal_logs.txt",
})

# ── Generated-state JSON prefixes ────────────────────────────────────────

GENERATED_JSON_PREFIXES: tuple[str, ...] = (
    "temp_",
    "_last_",
    "studio-",
    "clean_",
    "latest_benchmark_",
    ".modal_",
    ".model_",
    ".last_",
    ".profile_",
)

# ── Image / screenshot extensions ────────────────────────────────────────

_IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
})


# ── Public pure predicates ───────────────────────────────────────────────


def is_excluded_name(name: str) -> bool:
    """Return ``True`` when *name* (bare filename) matches an exclusion rule.

    Pure function — no filesystem access.  Designed for direct unit testing.
    """
    # Exact match
    if name in EXCLUDED_FILENAMES:
        return True
    # Prefix match
    if name.startswith(EXCLUDED_PREFIXES):
        return True
    # Infix match
    if any(infix in name for infix in EXCLUDED_INFIXES):
        return True
    # Extension match
    dot = name.rfind(".")
    if dot >= 0:
        ext = name[dot:].lower()
        if ext in EXCLUDED_EXTENSIONS:
            return True
        # Screenshot images
        if ext in _IMAGE_EXTENSIONS and (
            "screenshot" in name.lower() or "validation" in name.lower()
        ):
            return True
        # Generated-state JSON
        if ext == ".json":
            if name.startswith(GENERATED_JSON_PREFIXES):
                return True
    return False


def _is_excluded_dir(name: str) -> bool:
    """Return ``True`` when *name* matches an excluded directory rule."""
    return (
        name in EXCLUDED_DIRS
        or name.startswith(EXCLUDED_PREFIXES)
        or any(infix in name for infix in EXCLUDED_INFIXES)
    )


# ── Source-file walking ──────────────────────────────────────────────────


def _iter_source_files(root: Path) -> Iterator[Path]:
    """Walk *root* depth-first, yielding allowed source file paths (absolute).

    Prunes excluded directories in-place (mutates ``dirnames`` so that
    ``os.walk`` does not descend into them).
    """
    root = root.resolve()
    for dirpath_str, dirnames, filenames in os.walk(str(root), followlinks=False):
        dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d)]
        dirpath = Path(dirpath_str)
        for fn in filenames:
            ext = Path(fn).suffix.lower()
            if ext not in ALLOWED_SOURCE_EXTENSIONS:
                continue
            if not is_excluded_name(fn):
                yield dirpath / fn


# ── Hashing helpers ──────────────────────────────────────────────────────


def _sha256_file(path: Path) -> str:
    """Return SHA-256 hex digest of *path* contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def compute_file_hashes(root: str | Path) -> dict[str, str]:
    """Return ``{relative_path: sha256_hex}`` for every allowed source file.

    Only files with extensions in ``ALLOWED_SOURCE_EXTENSIONS`` that pass
    the exclusion rules are included.
    """
    root_path = Path(root).resolve()
    result: dict[str, str] = {}
    for abspath in _iter_source_files(root_path):
        rel = str(abspath.relative_to(root_path))
        result[rel] = _sha256_file(abspath)
    return result


def compute_source_bytes(root: str | Path) -> int:
    """Return total byte count of all allowed source files under *root*."""
    root_path = Path(root).resolve()
    total = 0
    for abspath in _iter_source_files(root_path):
        try:
            total += abspath.stat().st_size
        except OSError:
            pass
    return total


def compute_aggregate_hash(file_hashes: dict[str, str]) -> str:
    """Compute a deterministic hash from ``{path: sha256_hex}``.

    Sorted by path so identical source trees always produce the same hash.
    """
    h = hashlib.sha256()
    for path in sorted(file_hashes):
        h.update(path.encode("utf-8"))
        h.update(b"\x00")
        h.update(file_hashes[path].encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


# ── Public builder ───────────────────────────────────────────────────────


def build_deployment_identity(
    runtime_root: str | Path,
    *,
    dependency_hash: str = "",
    custom_node_paths: Sequence[str | Path] | None = None,
) -> DeploymentIdentity:
    """Build a deterministic ``DeploymentIdentity``.

    Parameters
    ----------
    runtime_root : str or Path
        Path to the ``comfymodal_runtime/`` directory.  All allowed source
        files under this root are hashed for ``runtime_hash``.
    dependency_hash : str
        Pre-computed dependency hash (e.g. pinned ``requirements.txt``).
        Pass empty string when dependencies are unchanged.
    custom_node_paths : sequence of str or Path, optional
        One or more custom-node source directories.  Python/JS files found
        here contribute to ``custom_node_hash``.

    Returns
    -------
    DeploymentIdentity
        A frozen identity whose ``combined_hash`` changes when any source
        file changes, but is unaffected by excluded artifacts.
    """
    runtime_hashes = compute_file_hashes(runtime_root)
    runtime_bytes = compute_source_bytes(runtime_root)
    runtime_hash = compute_aggregate_hash(runtime_hashes)

    custom_hashes: dict[str, str] = {}
    custom_bytes = 0
    if custom_node_paths:
        for cnp in custom_node_paths:
            cnp_path = Path(cnp)
            if cnp_path.is_dir():
                ch = compute_file_hashes(cnp_path)
                custom_hashes.update(ch)
                custom_bytes += compute_source_bytes(cnp_path)

    custom_node_hash = compute_aggregate_hash(custom_hashes) if custom_hashes else ""

    all_hashes = dict(runtime_hashes)
    all_hashes.update(custom_hashes)

    return DeploymentIdentity(
        runtime_hash=runtime_hash,
        dependency_hash=dependency_hash,
        custom_node_hash=custom_node_hash,
        source_bytes=runtime_bytes + custom_bytes,
        file_hashes=all_hashes,
    )
