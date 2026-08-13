#!/usr/bin/env python
"""Publish the local custom-nodes tree to the Modal ``comfyui-custom-nodes`` Volume.

Deploy-time V2 generation-parity step: builds the exact same tar.gz archive the
image bake uses (``__init__._build_custom_nodes_archive``) and pushes it through
the existing V1 remote ``sync_custom_nodes_to_volume`` function so the persisted
``custom_nodes_generation.json`` record is recomputed in-container with
``reason=post_sync_custom_nodes_to_volume``.

That makes the image-baked ``production_custom_node_generation`` match the
persisted Volume generation at V2 snapshot construction (baked == persisted),
preventing a spurious ``fallback_full_sync`` /
``complete=0 generation_mismatch`` proof outcome.

Dev-machine CLI tool: no GPU, no deploy.  Exit code 0 only when the remote
sync returns status ``ok``.

Usage:
    python tools/publish_custom_nodes_volume.py
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import sys
import tarfile

# Allow import of repo modules (modal_client) from tools/.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ── Custom-node archive semantics (must mirror __init__.py verbatim) ──────
# __init__.py:909-916 — the actual exclude-dir constant.
_CUSTOM_NODE_SYNC_EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "output", "test-results", "playwright-report",
    ".playwright-mcp", ".experiments", ".run_history",
    "benchmark_runs", "benchmark_logs", "optimization_logs",
    ".comfymodal_experiments", ".custom_node_requirements", ".baked_custom_node_deps",
    ".presets", ".preset_blobs",
}
# __init__.py:921-924 — canonical clone filter (matches comfyapp.py:6576-6579).
_CUSTOM_NODE_LOCAL_CLONE_RE = re.compile(
    r"^comfyui-modal-(?:agent\d+(?:[-_].*)?|agent[-_].*|worktree(?:[-_].*)?|wt(?:[-_].*)?|dc\d+)$",
    re.IGNORECASE,
)
# __init__.py:925 — the actual exclude-extensions set.
_CUSTOM_NODE_SYNC_EXCLUDE_EXTENSIONS = {".pyc", ".pyo"}

_ACTIVE_WORKSPACES_FILE = os.path.join(_REPO_ROOT, ".modal_workspaces.json")


def _iter_syncable_custom_node_dirs(cn_root: str) -> list[str]:
    """Mirror ``__init__.py:1110-1125`` exactly."""
    if not os.path.isdir(cn_root):
        return []
    names = []
    for node_dir in os.listdir(cn_root):
        node_path = os.path.join(cn_root, node_dir)
        if not os.path.isdir(node_path):
            continue
        if (
            node_dir.startswith(".")
            or node_dir in _CUSTOM_NODE_SYNC_EXCLUDE_DIRS
            or _CUSTOM_NODE_LOCAL_CLONE_RE.fullmatch(node_dir)
        ):
            continue
        names.append(node_dir)
    return sorted(names)


def _build_custom_nodes_archive(cn_root: str) -> bytes:
    """Mirror ``__init__.py:3121-3156`` archive semantics verbatim."""

    def tar_filter(tarinfo):
        parts = tarinfo.name.split("/")
        for part in parts:
            if part in _CUSTOM_NODE_SYNC_EXCLUDE_DIRS:
                return None
        if any(tarinfo.name.endswith(ext) for ext in _CUSTOM_NODE_SYNC_EXCLUDE_EXTENSIONS):
            return None
        return tarinfo

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        allowed = set(_iter_syncable_custom_node_dirs(cn_root))
        for node_dir in (sorted(os.listdir(cn_root)) if os.path.isdir(cn_root) else []):
            node_path = os.path.join(cn_root, node_dir)
            if not os.path.isdir(node_path):
                continue
            if node_dir in _CUSTOM_NODE_SYNC_EXCLUDE_DIRS:
                reason = "generated_or_environment_directory"
            elif node_dir.startswith("."):
                reason = "hidden_directory"
            elif _CUSTOM_NODE_LOCAL_CLONE_RE.fullmatch(node_dir):
                reason = "local_agent_or_worktree_clone"
            else:
                reason = "production_custom_node"
            print(
                f"[comfyui-modal.custom_node_filter] action={'allow' if node_dir in allowed else 'deny'} "
                f"name={node_dir} reason={reason}",
                flush=True,
            )
        for node_dir in _iter_syncable_custom_node_dirs(cn_root):
            tar.add(os.path.join(cn_root, node_dir), arcname=node_dir, filter=tar_filter)
    return buf.getvalue()


def _resolve_custom_nodes_root() -> str:
    """Resolve the custom-nodes source root (env override, then repo-relative).

    Mirrors ``__init__._custom_nodes_root()``: the repo itself lives inside
    ``<ComfyUI>/custom_nodes/``, so the custom-nodes root is the repo's parent
    directory (the same tree the image bake archives).
    """
    env_root = os.environ.get("COMFYMODAL_LOCAL_CUSTOM_NODES", "").strip()
    cn_root = env_root if env_root else os.path.dirname(_REPO_ROOT)
    if not os.path.isdir(cn_root):
        raise RuntimeError(f"custom-nodes root does not exist or is not a directory: {cn_root}")
    # Sanity check: a real custom-nodes root has >= 3 node-like subdirs.
    node_like = 0
    for entry in os.listdir(cn_root):
        entry_path = os.path.join(cn_root, entry)
        if not os.path.isdir(entry_path):
            continue
        if os.path.isfile(os.path.join(entry_path, "__init__.py")) or os.path.isfile(
            os.path.join(entry_path, "requirements.txt")
        ):
            node_like += 1
    if node_like < 3:
        raise RuntimeError(
            f"path does not look like a custom-nodes root "
            f"(only {node_like} node-like subdirs found): {cn_root}"
        )
    return cn_root


def _load_active_workspace() -> dict:
    """Load the active workspace credentials (same source as the deploy .bat)."""
    if not os.path.isfile(_ACTIVE_WORKSPACES_FILE):
        raise RuntimeError(f"workspace file not found: {_ACTIVE_WORKSPACES_FILE}")
    with open(_ACTIVE_WORKSPACES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    active_id = data.get("active_workspace_id")
    if not active_id:
        raise RuntimeError(".modal_workspaces.json has no active_workspace_id")
    workspace = next((w for w in data.get("workspaces", []) if w.get("id") == active_id), None)
    if not workspace:
        raise RuntimeError(f"active workspace {active_id!r} not found in .modal_workspaces.json")
    if not workspace.get("token_id") or not workspace.get("token_secret"):
        raise RuntimeError(f"active workspace {active_id!r} is missing token_id/token_secret")
    return workspace


def main() -> int:
    try:
        cn_root = _resolve_custom_nodes_root()
        archive_data = _build_custom_nodes_archive(cn_root)
        node_dirs = _iter_syncable_custom_node_dirs(cn_root)
        workspace = _load_active_workspace()

        # Mirror deploy_and_run_v2_single.bat: expose credentials via env for
        # any downstream Modal SDK handle resolution.
        os.environ["MODAL_TOKEN_ID"] = workspace["token_id"]
        os.environ["MODAL_TOKEN_SECRET"] = workspace["token_secret"]

        # Imported lazily: pulls in the modal SDK + repo modules.
        from modal_client import sync_custom_nodes

        # Same calling convention as __init__._sync_custom_nodes_and_maybe_deploy:
        # it targets the V1 remote sync_custom_nodes_to_volume function.
        result = asyncio.run(sync_custom_nodes(archive_data, workspace=workspace))
        if not isinstance(result, dict):
            raise RuntimeError(f"unexpected remote result type: {type(result).__name__}")

        remote_status = result.get("status", "")
        generation = result.get("generation") or "see-remote"
        print(f"[v2.volume_publish] source_root={cn_root}")
        print(f"[v2.volume_publish] nodes={len(node_dirs)}")
        print(f"[v2.volume_publish] status={'ok' if remote_status == 'ok' else 'failed'}")
        print(f"[v2.volume_publish] remote_status={remote_status or 'missing'}")
        print(f"[v2.volume_publish] generation={generation}")
        print("[v2.volume_publish] reason=post_sync_custom_nodes_to_volume")
        return 0 if remote_status == "ok" else 1
    except Exception as exc:  # noqa: BLE001 — never raise silently
        print(f"[v2.volume_publish] status=failed error={type(exc).__name__}:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
