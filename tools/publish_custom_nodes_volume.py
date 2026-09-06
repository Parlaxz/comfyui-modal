#!/usr/bin/env python
"""Publish the local custom-nodes tree to the Modal ``comfyui-custom-nodes`` Volume.

The S2 control plane builds one deterministic semantic archive/identity and
uses the existing remote ``sync_custom_nodes_to_volume`` function only as the
compatibility publisher. A verified receipt is the only normal exact-skip
proof.

Dev-machine CLI tool: no GPU, no deploy.  Exit code 0 only when the remote
sync returns status ``ok``.

Usage:
    python tools/publish_custom_nodes_volume.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Allow import of repo modules (modal_client) from tools/.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from comfymodal_runtime.publication_policy import (
    CUSTOM_NODES_PUBLISHER_APP_NAME,
    CUSTOM_NODES_VOLUME_NAME,
    iter_syncable_custom_node_dirs as _iter_syncable_custom_node_dirs_policy,
    resolve_custom_nodes_root as _resolve_custom_nodes_root_policy,
)
from tools.v2_control.custom_nodes import (
    PACKAGING_POLICY_VERSION,
    RECEIPT_SCHEMA_VERSION,
    get_volume,
    prepare_publication,
    publish_or_skip,
)
from tools.v2_control.locking import DeployLock

_ACTIVE_WORKSPACES_FILE = os.path.join(_REPO_ROOT, ".modal_workspaces.json")


def _iter_syncable_custom_node_dirs(cn_root: str) -> list[str]:
    return _iter_syncable_custom_node_dirs_policy(cn_root)


def _build_custom_nodes_archive(cn_root: str) -> bytes:
    """Compatibility wrapper using the S2 semantic set and archive builder."""
    _identity, archive, _files = prepare_publication(cn_root)
    return archive


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
        workspace = _load_active_workspace()

        # Mirror deploy_and_run_v2_single.bat: expose credentials via env for
        # any downstream Modal SDK handle resolution.
        os.environ["MODAL_TOKEN_ID"] = workspace["token_id"]
        os.environ["MODAL_TOKEN_SECRET"] = workspace["token_secret"]

        async def publish(data: bytes):
            # Imported lazily: pulls in the modal SDK + repo modules only when
            # an exact receipt did not prove the volume already matches.
            from modal_client import sync_custom_nodes
            return await sync_custom_nodes(
                data, workspace=workspace,
                publisher_app_name=CUSTOM_NODES_PUBLISHER_APP_NAME,
            )

        def run_publication():
            return asyncio.run(publish_or_skip(
                cn_root,
                volume_name=CUSTOM_NODES_VOLUME_NAME,
                publisher=publish,
                volume_factory=lambda volume_name: get_volume(
                    volume_name, workspace=workspace
                ),
            ))

        if os.environ.get("V2CTL_DEPLOY_LOCK_HELD") == "1":
            decision = run_publication()
        else:
            lock = DeployLock(Path(_REPO_ROOT) / ".v2ctl" / "deploy.lock")
            lock.acquire(
                owner="publish_custom_nodes_volume",
                target=CUSTOM_NODES_VOLUME_NAME,
                profile="custom_nodes_publication",
            )
            try:
                decision = run_publication()
            finally:
                lock.release()
        identity = decision.identity
        result = decision.result if isinstance(decision.result, dict) else {}
        remote_status = result.get("status", "")
        print(f"[v2.volume_publish] source_root={cn_root}")
        print(f"[v2.volume_publish] nodes={len({path.split('/', 1)[0] for path, _, _ in identity.files})}")
        decision_label = "skip_exact" if decision.skip else decision.action
        print(f"[custom_nodes.publish] decision={decision_label} reason={decision.reason} "
              f"generation={identity.generation[:12]} schema={RECEIPT_SCHEMA_VERSION} "
              f"policy={PACKAGING_POLICY_VERSION}")
        print(f"[v2.volume_publish] status={'ok' if decision.skip or decision.reason == 'published_verified' else 'failed'}")
        print(f"[v2.volume_publish] remote_status={remote_status or ('skipped' if decision.skip else 'missing')}")
        return 0 if decision.skip or decision.action == "recovered" or decision.reason == "published_verified" else 1
    except Exception as exc:  # noqa: BLE001 — never raise silently
        print(f"[v2.volume_publish] status=failed error={type(exc).__name__}:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
