"""Fast structural contracts for shared custom-node publication serialization."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.v2_control.locking import DeployLock


pytestmark = pytest.mark.fast_unit

REPO_ROOT = Path(__file__).resolve().parents[1]


def _function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            lines = source.splitlines(keepends=True)
            return "".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"function not found: {name}")


def test_publisher_is_platform_single_writer_and_stages_per_invocation():
    source = (REPO_ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    function = _function_source(REPO_ROOT / "comfyapp.py", "sync_custom_nodes_to_volume")

    decorator = source[source.rfind("@app.function(", 0, source.index("def sync_custom_nodes_to_volume")) :]
    decorator = decorator[: decorator.index("def sync_custom_nodes_to_volume")]
    assert "max_containers=1" in decorator
    assert "prefix=\"comfyui-custom-nodes-\"" in function
    assert "dir=\"/tmp\"" in function
    assert "os.path.join(CUSTOM_NODES_PATH, \".staging\")" not in function
    assert "finally:" in function
    assert "_safe_remove_path(staging_dir)" in function


def test_all_publication_entry_points_use_receipt_control_plane():
    custom_nodes = _function_source(REPO_ROOT / "tools/v2_control/custom_nodes.py", "publish_or_skip")
    studio = _function_source(REPO_ROOT / "__init__.py", "_publish_custom_nodes_or_skip")
    cli = _function_source(REPO_ROOT / "tools/v2_control/cli.py", "_publish_golden_custom_nodes")
    legacy = (REPO_ROOT / "tools/publish_custom_nodes_volume.py").read_text(encoding="utf-8")

    assert "publisher(archive)" in custom_nodes
    assert "publish_or_skip(" in studio
    assert "run_publish_or_skip(" in cli
    assert "publish_or_skip(" in legacy


def test_studio_route_owns_repo_lock_and_refuses_held_lock():
    init_source = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8-sig")
    helper = _function_source(REPO_ROOT / "__init__.py", "_acquire_studio_publication_lock")
    route = _function_source(REPO_ROOT / "__init__.py", "modal_sync_custom_nodes")

    assert "DeployLock(Path(_NODE_DIR) / \".v2ctl\" / \"deploy.lock\")" in helper
    assert "auto_recover=True" in helper
    assert "force=True" in helper
    assert "LockHeldError" in route and "status=409" in route
    assert "publication_lock.release()" in route
    assert "_acquire_studio_publication_lock()" in route
    assert "from tools.v2_control.locking import DeployLock" in init_source


def test_proven_stale_lock_can_be_recovered_without_permanent_wedge(tmp_path):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    path = tmp_path / ".v2ctl" / "deploy.lock"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner": "crashed-studio",
                "pid": 99999999,
                "host": DeployLock.host_id(),
                "target": "comfyui-custom-nodes",
                "profile": "studio_custom_nodes",
                "timestamp": now.isoformat(),
                "started_at": now.isoformat(),
            }
        ),
        encoding="utf-8",
    )

    lock = DeployLock(path, now_fn=lambda: now)
    assert lock.is_stale() is True
    lock.acquire(
        owner="studio-custom-node-publication",
        target="comfyui-custom-nodes",
        profile="studio_custom_nodes",
        force=True,
    )
    status = lock.status()
    assert status is not None
    assert status["owner"] == "studio-custom-node-publication"
    lock.release()
