"""Canonical deployment source manifest / DeploymentIdentity builder.

Excludes ``reference/``, ``*.ref``, ``*.v21610_backup``, ``before_v2_*``,
benchmark outputs, logs, screenshots, temporary JSON, local Studio outputs,
generated state, ``.git``, ``node_modules``, ``tests``, and ``docs`` unless
explicitly allowed.

Pure functions — suitable for unit tests without Modal or volume access.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator, Sequence

from comfymodal_runtime.contracts import DeploymentIdentity
from .publication_policy import (
    ALLOWED_SOURCE_EXTENSIONS,
    EXCLUDED_DIR_NAMES as EXCLUDED_DIRS,
    EXCLUDED_EXTENSIONS,
    EXCLUDED_FILENAMES,
    EXCLUDED_INFIXES,
    EXCLUDED_PREFIXES,
    GENERATED_JSON_PREFIXES,
    is_excluded_dir_name as _policy_excluded_dir_name,
    is_excluded_name,
    iter_source_files,
)


def is_excluded_path(relative_path: str | Path) -> bool:
    """Apply the shared publication policy to a repository-relative path."""
    from .publication_policy import is_excluded_path as _is_excluded_path

    return _is_excluded_path(relative_path)


# ── Public pure predicates ───────────────────────────────────────────────


def _is_excluded_dir(name: str) -> bool:
    """Return ``True`` when *name* matches an excluded directory rule."""
    return _policy_excluded_dir_name(name)


# ── Source-file walking ──────────────────────────────────────────────────


def _iter_source_files(root: Path) -> Iterator[Path]:
    """Walk *root* depth-first, yielding allowed source file paths (absolute).

    Prunes excluded directories in-place (mutates ``dirnames`` so that
    ``os.walk`` does not descend into them).
    """
    yield from iter_source_files(root, extensions=ALLOWED_SOURCE_EXTENSIONS)


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
        rel = str(abspath.relative_to(root_path)).replace("\\", "/")
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
        for root_index, cnp in enumerate(custom_node_paths):
            cnp_path = Path(cnp)
            if cnp_path.is_dir():
                ch = compute_file_hashes(cnp_path)
                # Relative paths are only unique within one custom-node root.
                # Namespace them before merging so two roots containing the
                # same filename cannot silently overwrite one another.
                custom_hashes.update({
                    f"custom_node_root_{root_index}/{rel}": sha
                    for rel, sha in ch.items()
                })
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
