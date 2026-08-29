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
import sys
import tarfile

# Allow import of repo modules (modal_client) from tools/.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from comfymodal_runtime.publication_policy import (
    EXCLUDED_DIR_NAMES as _CUSTOM_NODE_SYNC_EXCLUDE_DIRS,
    EXCLUDED_EXTENSIONS as _CUSTOM_NODE_SYNC_EXCLUDE_EXTENSIONS,
    LOCAL_CLONE_RE as _CUSTOM_NODE_LOCAL_CLONE_RE,
    custom_node_filter_reason as _custom_node_filter_reason,
    iter_syncable_custom_node_dirs as _iter_syncable_custom_node_dirs_policy,
    resolve_custom_nodes_root as _resolve_custom_nodes_root_policy,
    is_excluded_path as _is_excluded_publication_path,
    is_publishable_top_level_node as _is_publishable_top_level_node,
)

_ACTIVE_WORKSPACES_FILE = os.path.join(_REPO_ROOT, ".modal_workspaces.json")


def _iter_syncable_custom_node_dirs(cn_root: str) -> list[str]:
    return _iter_syncable_custom_node_dirs_policy(cn_root)


def _build_custom_nodes_archive(cn_root: str) -> bytes:
    """Mirror ``__init__.py:3121-3156`` archive semantics verbatim."""

    def tar_filter(tarinfo):
        if tarinfo.issym() or tarinfo.islnk():
            return None
        if _is_excluded_publication_path(tarinfo.name):
            return None
        return tarinfo

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        allowed = set(_iter_syncable_custom_node_dirs(cn_root))
        for node_dir in (sorted(os.listdir(cn_root)) if os.path.isdir(cn_root) else []):
            node_path = os.path.join(cn_root, node_dir)
            if not os.path.isdir(node_path) or os.path.islink(node_path):
                continue
            reason = _custom_node_filter_reason(node_dir, node_path) or "production_custom_node"
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
    return _resolve_custom_nodes_root_policy(_REPO_ROOT)


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
