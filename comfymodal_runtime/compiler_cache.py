"""Compiler cache *storage policy* (no artifact keying/loading/locks).

This module owns three things only:

* :func:`compiler_cache_namespace` — a pure digest over the toolchain
  identity (torch / CUDA / Triton / arch / python).  Model, checkpoint,
  request, and shape inputs are never consulted, so the namespace cannot
  be contaminated by them.
* :func:`compiler_cache_paths` / :func:`bind_compiler_cache` — routing
  from a namespace to on-disk directories (plus the env-var mapping the
  wiring lane applies).  Artifact keying, loading, and locking are owned
  upstream; nothing here reads or writes cache payloads.
* :func:`plan_cache_prune` / :func:`prune_compiler_cache` — bounded,
  symlink-safe, whole-namespace pruning towards a 20 GiB target,
  considering namespaces idle for more than 30 days.  Dry-run by default.

Symlink safety: directory walks use ``lstat`` semantics and never follow
symlinks.  A namespace entry that is itself a symlink is skipped (never
deleted through).  Sizes count regular files only.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from typing import Any, Mapping

# Only these toolchain keys feed the digest.  Everything else in the
# identity mapping (model, checkpoint, request, shapes, ...) is ignored
# by construction — see compiler_cache_namespace.
TOOLCHAIN_KEYS = (
    "torch_version",
    "cuda_version",
    "triton_version",
    "arch",
    "python_version",
)

UNKNOWN = "unknown"

ENV_CACHE_ROOT = "COMFYMODAL_COMPILER_CACHE_ROOT"
ENV_INDUCTOR_DIR = "TORCHINDUCTOR_CACHE_DIR"
ENV_TRITON_DIR = "TRITON_CACHE_DIR"

# Persistent runtime-state mount.  Must match modal_app.RUNTIME_STATE_PATH
# (duplicated as a literal so this module stays dependency-light: stdlib
# only, no runtime imports).  Used only when the mount actually exists, so
# local dev machines without it keep the ephemeral tmpdir default.
PERSISTENT_STATE_MOUNT = "/mnt/comfymodal_runtime_state"
PERSISTENT_CACHE_SUBPATH = os.path.join(".inductor-cache", "v1")

DEFAULT_TARGET_BYTES = 20 * 1024**3
DEFAULT_MAX_IDLE_DAYS = 30
SECONDS_PER_DAY = 86400.0


# ---------------------------------------------------------------------------
# Namespace + paths + bind (routing only)
# ---------------------------------------------------------------------------


def compiler_cache_namespace(identity: Mapping[str, Any] | None) -> str:
    """Return the pure toolchain digest for ``identity``.

    Only :data:`TOOLCHAIN_KEYS` contribute; missing keys degrade to
    ``"unknown"`` rather than raising.  The digest is a sha256 hex string
    over canonical JSON (sorted keys, compact separators).
    """
    source = identity if isinstance(identity, Mapping) else {}
    canonical = {
        key: str(source.get(key, UNKNOWN)) for key in TOOLCHAIN_KEYS
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def default_cache_root() -> str:
    override = os.environ.get(ENV_CACHE_ROOT, "").strip()
    if override:
        return override
    try:
        if os.path.isdir(PERSISTENT_STATE_MOUNT):
            return os.path.join(PERSISTENT_STATE_MOUNT, PERSISTENT_CACHE_SUBPATH)
    except Exception:
        pass
    return os.path.join(tempfile.gettempdir(), "comfymodal-compiler-cache")


def compiler_cache_paths(namespace: str, *, root: str | None = None) -> dict[str, str]:
    """Return the routing directories for ``namespace`` (pure, no I/O)."""
    if not isinstance(namespace, str) or not namespace.strip():
        raise ValueError("namespace must be a non-empty string")
    base = root if root is not None else default_cache_root()
    namespace_dir = os.path.join(base, namespace)
    return {
        "root": base,
        "namespace_dir": namespace_dir,
        "inductor_dir": os.path.join(namespace_dir, "inductor"),
        "triton_dir": os.path.join(namespace_dir, "triton"),
    }


def bind_compiler_cache(
    namespace: str,
    *,
    root: str | None = None,
    apply_env: bool = True,
) -> dict[str, Any]:
    """Create routing directories and report the env mapping to apply.

    Creates ``inductor_dir``/``triton_dir`` (parents as needed).  When
    ``apply_env`` is true the ``TORCHINDUCTOR_CACHE_DIR``/``TRITON_CACHE_DIR``
    variables are set in this process and echoed in ``applied``.  A
    namespace path that already exists as a symlink is refused fail-closed
    (no creation, no env changes, ``refused_symlink=True``).
    """
    paths = compiler_cache_paths(namespace, root=root)
    namespace_dir = paths["namespace_dir"]
    try:
        if os.path.islink(namespace_dir):
            return {**paths, "namespace": namespace, "applied": {},
                    "refused_symlink": True}
    except OSError:
        return {**paths, "namespace": namespace, "applied": {},
                "refused_symlink": True, "error": "stat_failed"}
    try:
        os.makedirs(paths["inductor_dir"], exist_ok=True)
        os.makedirs(paths["triton_dir"], exist_ok=True)
    except OSError as exc:
        return {**paths, "namespace": namespace, "applied": {},
                "refused_symlink": False, "error": type(exc).__name__}
    applied: dict[str, str] = {}
    if apply_env:
        os.environ[ENV_INDUCTOR_DIR] = paths["inductor_dir"]
        os.environ[ENV_TRITON_DIR] = paths["triton_dir"]
        applied = {
            ENV_INDUCTOR_DIR: paths["inductor_dir"],
            ENV_TRITON_DIR: paths["triton_dir"],
        }
    return {**paths, "namespace": namespace, "applied": applied,
            "refused_symlink": False}


# ---------------------------------------------------------------------------
# Prune planning + entrypoint (whole-namespace, bounded, symlink-safe)
# ---------------------------------------------------------------------------


def _namespace_size_bytes(path: str) -> int:
    """Sum regular-file sizes under ``path`` without following symlinks."""
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as iterator:
                entries = list(iterator)
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                elif entry.is_file(follow_symlinks=False):
                    try:
                        total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
            except OSError:
                continue
    return total


def _scan_namespaces(root: str, *, now: float) -> tuple[list[dict[str, Any]], list[str], int]:
    """Scan immediate child dirs; return (entries, skipped_symlinks, total)."""
    entries: list[dict[str, Any]] = []
    skipped: list[str] = []
    total = 0
    try:
        with os.scandir(root) as iterator:
            children = sorted(iterator, key=lambda entry: entry.name)
    except OSError:
        return entries, skipped, total
    for entry in children:
        try:
            if entry.is_symlink():
                skipped.append(entry.name)
                continue
            if not entry.is_dir(follow_symlinks=False):
                continue
            stat = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        size = _namespace_size_bytes(entry.path)
        idle_days = max(0.0, (now - stat.st_mtime) / SECONDS_PER_DAY)
        entries.append(
            {
                "namespace": entry.name,
                "path": entry.path,
                "size_bytes": size,
                "idle_days": idle_days,
                "mtime": stat.st_mtime,
            }
        )
        total += size
    return entries, skipped, total


def plan_cache_prune(
    root: str | None = None,
    *,
    target_bytes: int = DEFAULT_TARGET_BYTES,
    max_idle_days: float = DEFAULT_MAX_IDLE_DAYS,
    dry_run: bool = True,
    now: float | None = None,
    limit_entries: int | None = None,
) -> dict[str, Any]:
    """Plan whole-namespace deletions so the tree fits ``target_bytes``.

    Only namespaces idle for more than ``max_idle_days`` are eligible.
    Eligible namespaces are ordered stalest-first (size breaks ties), and
    whole namespaces are taken in that order until the projected total is
    at or under target.  ``limit_entries`` bounds the plan length.  This
    function never deletes; see :func:`prune_compiler_cache`.
    """
    base = root if root is not None else default_cache_root()
    moment = time.time() if now is None else float(now)
    entries, skipped, total = _scan_namespaces(base, now=moment)
    eligible = [item for item in entries if item["idle_days"] > float(max_idle_days)]
    eligible.sort(key=lambda item: (-item["idle_days"], -item["size_bytes"], item["namespace"]))
    planned: list[dict[str, Any]] = []
    projected = total
    bounded = False
    for item in eligible:
        if projected <= int(target_bytes):
            break
        if limit_entries is not None and len(planned) >= int(limit_entries):
            bounded = True
            break
        planned.append(item)
        projected -= item["size_bytes"]
    if limit_entries is not None and len(planned) >= int(limit_entries) and projected > int(target_bytes):
        bounded = True
    return {
        "root": base,
        "target_bytes": int(target_bytes),
        "total_bytes": total,
        "namespace_count": len(entries),
        "eligible": eligible,
        "planned": planned,
        "skipped_symlinks": skipped,
        "projected_bytes": projected,
        "dry_run": bool(dry_run),
        "bounded": bounded,
    }


def prune_compiler_cache(
    root: str | None = None,
    *,
    target_bytes: int = DEFAULT_TARGET_BYTES,
    max_idle_days: float = DEFAULT_MAX_IDLE_DAYS,
    dry_run: bool = True,
    now: float | None = None,
    limit_entries: int | None = None,
) -> dict[str, Any]:
    """Prune entrypoint: plan, then delete planned namespaces unless dry-run.

    Deletion re-checks each path with ``lstat`` semantics immediately
    before removal; anything that became a symlink is skipped, never
    deleted through.  Returns the plan plus ``deleted``/``errors``.
    """
    plan = plan_cache_prune(
        root,
        target_bytes=target_bytes,
        max_idle_days=max_idle_days,
        dry_run=dry_run,
        now=now,
        limit_entries=limit_entries,
    )
    deleted: list[str] = []
    errors: list[dict[str, str]] = []
    if not dry_run:
        for item in plan["planned"]:
            path = item["path"]
            try:
                if os.path.islink(path) or not os.path.isdir(path):
                    errors.append({"path": path, "error": "skipped_not_a_real_dir"})
                    continue
                shutil.rmtree(path, ignore_errors=False)
                deleted.append(path)
            except OSError as exc:
                errors.append({"path": path, "error": type(exc).__name__})
    return {**plan, "deleted": deleted, "errors": errors}


# ---------------------------------------------------------------------------
# Cache metadata snapshots (cheap pre/post evidence for later comparison)
# ---------------------------------------------------------------------------
#
# Pre/post snapshots capture namespace, effective dirs, artifact count,
# total size, and latest mtime in a SINGLE symlink-safe walk (lstat
# semantics, never follows symlinks — same discipline as
# ``_namespace_size_bytes``).  No hashing, no repeated deep scans: the
# digest-relevant identity stays in ``compiler_cache_namespace``; these
# snapshots exist only so a later compile-evidence comparison can tell
# "cache grew / stayed empty" without re-walking.


def _scan_dir_file_stats(path: str) -> tuple[int, int, float, bool]:
    """Single-pass ``(count, bytes, latest_mtime, ok)`` for regular files.

    Symlink-safe: symlinks are never followed or counted.  ``ok`` is
    ``False`` when the walk itself failed (missing/unreadable root);
    partial results are still returned best-effort.
    """
    count = 0
    total = 0
    latest = 0.0
    ok = True
    try:
        if os.path.islink(path) or not os.path.isdir(path):
            return 0, 0, 0.0, False
    except OSError:
        return 0, 0, 0.0, False
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as iterator:
                entries = list(iterator)
        except OSError:
            ok = False
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                elif entry.is_file(follow_symlinks=False):
                    try:
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        ok = False
                        continue
                    count += 1
                    total += stat.st_size
                    if stat.st_mtime > latest:
                        latest = float(stat.st_mtime)
            except OSError:
                ok = False
                continue
    return count, total, latest, ok


def snapshot_cache_metadata(
    namespace: str, *, root: str | None = None
) -> dict[str, Any]:
    """Capture cheap cache metadata for ``namespace`` in one walk.

    Returns namespace, effective dirs, artifact count, total size, and
    latest mtime.  Never hashes payloads and never scans twice.  A
    missing namespace degrades to zeros (``namespace_exists=False``);
    an empty/invalid namespace raises ``ValueError`` like
    :func:`compiler_cache_paths`.
    """
    paths = compiler_cache_paths(namespace, root=root)
    namespace_dir = paths["namespace_dir"]
    try:
        exists = bool(
            os.path.isdir(namespace_dir)
            and not os.path.islink(namespace_dir)
        )
    except OSError:
        exists = False
    count, total, latest, ok = _scan_dir_file_stats(namespace_dir)
    return {
        "namespace": str(namespace),
        "root": paths["root"],
        "dirs": dict(paths),
        "namespace_exists": exists,
        "artifact_count": count,
        "total_bytes": total,
        "latest_mtime": latest,
        "scanned_ok": bool(ok and exists),
    }


def diff_cache_snapshots(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Pure diff of two :func:`snapshot_cache_metadata` snapshots.

    Reports artifact/byte deltas and whether the latest mtime advanced.
    Never raises; uncomparable inputs yield ``comparable=False`` with a
    reason instead of fabricated zeros.
    """
    try:
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            return {"comparable": False, "reason": "snapshot_not_a_mapping"}
        namespace_before = str(before.get("namespace", ""))
        namespace_after = str(after.get("namespace", ""))
        if not namespace_before or namespace_before != namespace_after:
            return {"comparable": False, "reason": "namespace_mismatch",
                    "before": namespace_before, "after": namespace_after}
        count_before = int(before.get("artifact_count", 0) or 0)
        count_after = int(after.get("artifact_count", 0) or 0)
        bytes_before = int(before.get("total_bytes", 0) or 0)
        bytes_after = int(after.get("total_bytes", 0) or 0)
        mtime_before = float(before.get("latest_mtime", 0.0) or 0.0)
        mtime_after = float(after.get("latest_mtime", 0.0) or 0.0)
        return {
            "comparable": True,
            "namespace": namespace_before,
            "artifact_count_before": count_before,
            "artifact_count_after": count_after,
            "artifact_delta": count_after - count_before,
            "total_bytes_before": bytes_before,
            "total_bytes_after": bytes_after,
            "total_bytes_delta": bytes_after - bytes_before,
            "latest_mtime_before": mtime_before,
            "latest_mtime_after": mtime_after,
            "mtime_advanced": bool(mtime_after > mtime_before),
        }
    except Exception as exc:
        return {"comparable": False,
                "reason": f"diff_failed:{type(exc).__name__}"}
