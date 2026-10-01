from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from custom_node_registry import CustomNodeDiscovery
from comfymodal_runtime.custom_node_identity import (
    resolve_plugin_identity,
    normalize_repository_url,
)
from comfymodal_runtime.publication_policy import compute_publication_generation
import model_library_routes


pytestmark = pytest.mark.fast_unit


class _Routes:
    def __init__(self):
        self._handlers = []

    def get(self, path):
        def decorate(fn):
            self._handlers.append(("GET", path, fn))
            return fn
        return decorate

    def post(self, path):
        def decorate(fn):
            self._handlers.append(("POST", path, fn))
            return fn
        return decorate

    def patch(self, path):
        return lambda fn: fn


class _Server:
    def __init__(self):
        self.routes = _Routes()


class _Request:
    query = {}
    match_info = {}

    async def json(self):
        return {}


def _handler(server, path):
    return next(fn for method, registered, fn in server.routes._handlers if method == "GET" and registered == path)


def _method_handler(server, method, path):
    return next(fn for registered_method, registered, fn in server.routes._handlers
                if registered_method == method and registered == path)


def test_discovery_does_not_inherit_parent_repository(tmp_path):
    comfy = tmp_path / "ComfyUI"
    custom_nodes = comfy / "custom_nodes"
    plugin = custom_nodes / "plugin-without-git"
    plugin.mkdir(parents=True)
    (plugin / "nodes.py").write_text("NODE_CLASS_MAPPINGS = {}\n")
    subprocess.run(["git", "init", str(comfy)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(comfy), "remote", "add", "origin", "https://github.com/parent/comfy"], check=True)

    records, _ = CustomNodeDiscovery().discover(comfy)

    assert len(records) == 1
    assert records[0].repo_url == ""
    assert records[0].installed_commit == ""


def test_repository_url_normalization_keeps_forks_and_mirrors_distinct():
    expected = "https://github.com/Owner/Repo"
    for value in (
        "https://user:secret@GITHUB.com:443/Owner/Repo.git/",
        "ssh://git@github.com/Owner/Repo.git",
        "ssh://git@github.com:Owner/Repo.git",
        "git@github.com:Owner/Repo.git",
    ):
        assert normalize_repository_url(value) == expected
    assert normalize_repository_url("https://github.com/Fork/Repo") != expected
    assert normalize_repository_url("https://mirror.invalid/github.com/Owner/Repo.git") != expected


def test_basename_collision_is_ambiguous(tmp_path):
    left = tmp_path / "Plugin"
    left.mkdir()
    result = resolve_plugin_identity(left, basename_collisions={"plugin"})
    assert result.identity is None
    assert result.confidence == "ambiguous"


def test_sync_status_exact_payload_and_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("COMFYMODAL_CUSTOM_NODE_DELIVERY", "volume")
    root = tmp_path / "custom_nodes"
    anchor = root / "comfyui-modal"
    package = root / "Plugin"
    anchor.mkdir(parents=True)
    package.mkdir()
    (package / "nodes.py").write_text("NODE_CLASS_MAPPINGS = {}\n")
    (package / "pyproject.toml").write_text(
        "[project]\nname='plugin'\n[project.urls]\nRepository='https://github.com/Owner/Repo.git'\n"
    )

    generation = compute_publication_generation(root)
    receipt = type("Receipt", (), {
        "content_generation": generation,
        "package_manifests": ({
            "name": "Plugin",
            "identity": "https://github.com/Owner/Repo",
            "requirements_present": False,
        },),
    })()
    monkeypatch.setattr(model_library_routes, "read_receipt", lambda *args, **kwargs: receipt)
    server = _Server()
    model_library_routes.register_model_library_routes(
        server, node_dir=anchor, comfyui_root=tmp_path, custom_nodes_volume=object()
    )

    response = __import__("asyncio").run(_handler(server, "/comfymodal/studio/custom-nodes/sync-status")(_Request()))
    body = json.loads(response.body)
    assert list(body) == [
        "status", "inventory_state", "payload_state", "local_only", "published_only",
        "duplicates", "unknown_identity", "dependencies_changed", "dependencies_state",
        "receipt_schema_supported", "local_generation", "published_generation", "delivery_mode",
    ]
    assert body["inventory_state"] == "match"
    assert body["payload_state"] == "exact"
    assert body["dependencies_state"] == "same"


def test_old_or_missing_receipt_is_unknown_not_differs(tmp_path, monkeypatch):
    monkeypatch.setenv("COMFYMODAL_CUSTOM_NODE_DELIVERY", "volume")
    root = tmp_path / "custom_nodes"
    anchor = root / "comfyui-modal"
    package = root / "plugin"
    anchor.mkdir(parents=True)
    package.mkdir()
    (package / "nodes.py").write_text("x = 1\n")
    monkeypatch.setattr(model_library_routes, "read_receipt", lambda *args, **kwargs: (_ for _ in ()).throw(model_library_routes.ReceiptError("schema_mismatch")))
    server = _Server()
    model_library_routes.register_model_library_routes(
        server, node_dir=anchor, comfyui_root=tmp_path, custom_nodes_volume=object()
    )
    response = __import__("asyncio").run(_handler(server, "/comfymodal/studio/custom-nodes/sync-status")(_Request()))
    body = json.loads(response.body)
    assert body["inventory_state"] == "unknown"
    assert body["receipt_schema_supported"] is False


def test_image_delivery_mode_is_not_applicable_and_does_not_read_volume(tmp_path, monkeypatch):
    monkeypatch.setenv("COMFYMODAL_CUSTOM_NODE_DELIVERY", "image")
    root = tmp_path / "custom_nodes"
    anchor = root / "comfyui-modal"
    anchor.mkdir(parents=True)
    (root / "plugin").mkdir()
    monkeypatch.setattr(
        model_library_routes,
        "read_receipt",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("image mode read the Volume")),
    )
    server = _Server()
    model_library_routes.register_model_library_routes(
        server, node_dir=anchor, comfyui_root=tmp_path, custom_nodes_volume=object()
    )
    response = __import__("asyncio").run(
        _handler(server, "/comfymodal/studio/custom-nodes/sync-status")(_Request())
    )
    body = json.loads(response.body)
    assert body["delivery_mode"] == "image"
    assert body["inventory_state"] == "not_applicable"
    assert body["payload_state"] == "not_applicable"
    assert body["dependencies_state"] == "not_applicable"


def test_image_sync_posts_are_explanatory_noops(tmp_path, monkeypatch):
    monkeypatch.setenv("COMFYMODAL_CUSTOM_NODE_DELIVERY", "image")
    root = tmp_path / "custom_nodes"
    anchor = root / "comfyui-modal"
    anchor.mkdir(parents=True)
    server = _Server()
    model_library_routes.register_model_library_routes(
        server, node_dir=anchor, comfyui_root=tmp_path
    )
    for path, operation in (
        ("/comfymodal/studio/custom-nodes/sync", "publish"),
        ("/comfymodal/studio/custom-nodes/sync/rebuild-dependencies", "rebuild_dependencies"),
    ):
        response = __import__("asyncio").run(_method_handler(server, "POST", path)(_Request()))
        body = json.loads(response.body)
        assert body["status"] == "completed"
        assert body["operation"] == operation
        assert body["outcome"] == "not_applicable"
        assert "deploy image" in body["message"]


def test_sync_posts_return_pollable_status_and_preserve_refusal_outcomes(tmp_path, monkeypatch):
    monkeypatch.setenv("COMFYMODAL_CUSTOM_NODE_DELIVERY", "volume")
    root = tmp_path / "custom_nodes"
    anchor = root / "comfyui-modal"
    anchor.mkdir(parents=True)
    operation_status = {
        "sync_id": "sync-1", "status": "blocked", "state": "blocked",
        "outcome": "destructive_publication_blocked",
        "message": "Publication refused: it would remove previously-published custom-node content.",
    }
    calls = []

    def start(operation, expected):
        calls.append((operation, list(expected)))
        return {
            "status": "started", "sync_id": "sync-1", "state": "queued",
            "operation": operation,
            "dependencies_changed": list(expected),
            "poll_url": "/comfymodal/studio/custom-nodes/sync/status/sync-1",
        }

    server = _Server()
    model_library_routes.register_model_library_routes(
        server,
        node_dir=anchor,
        comfyui_root=tmp_path,
        custom_node_sync_start=start,
        custom_node_sync_status=lambda sync_id: operation_status if sync_id == "sync-1" else None,
        custom_node_delivery_mode="volume",
    )
    response = __import__("asyncio").run(
        _method_handler(server, "POST", "/comfymodal/studio/custom-nodes/sync")(_Request())
    )
    body = json.loads(response.body)
    assert response.status == 202
    assert body["sync_id"] == "sync-1"
    assert body["poll_url"].endswith("/sync-1")
    status = __import__("asyncio").run(
        _method_handler(server, "GET", "/comfymodal/studio/custom-nodes/sync/status/{sync_id}")(
            type("Request", (), {"match_info": {"sync_id": "sync-1"}})()
        )
    )
    status_body = json.loads(status.body)
    assert status_body["outcome"] == "destructive_publication_blocked"
    assert "refused" in status_body["message"].lower()
    assert calls == [("publish", [])]
