"""HTTP routes for the Studio Model Library and workflow dependencies.

Registered by ``register_model_library_routes(server, node_dir, comfyui_root,
resolver=None)``.  All business rules live in ``model_library`` /
``dependency_resolver`` / ``custom_node_registry``; these handlers only
translate HTTP <-> service calls.  Domain errors map to 400/404; unexpected
errors map to 500.

Route summary (all under ``/comfymodal/studio``):

    Models:
        GET   /comfymodal/studio/models                         -- list/search/filter
        GET   /comfymodal/studio/models/types                   -- model type taxonomy
        POST  /comfymodal/studio/models/rescan                  -- rescan model folders
        GET   /comfymodal/studio/models/{model_id}              -- detail
        PATCH /comfymodal/studio/models/{model_id}              -- update metadata
        POST  /comfymodal/studio/models/install-request         -- validate an install

    Custom nodes:
        GET   /comfymodal/studio/custom-nodes                   -- list registry
        POST  /comfymodal/studio/custom-nodes/refresh           -- rediscover + store
        POST  /comfymodal/studio/custom-nodes/install-request   -- approval record only

    Dependencies:
        GET   /comfymodal/studio/workflows/versions/{version_id}/dependencies
        GET   /comfymodal/studio/workflows/versions/{version_id}/compatibility
        PATCH /comfymodal/studio/workflows/versions/{version_id}/compatibility
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aiohttp import web

from custom_node_registry import CustomNodeDiscovery, CustomNodeRegistryStore
from dependency_resolver import DependencyResolver
from model_library import (
    MODEL_TYPES,
    ModelLibraryError,
    ModelLibraryService,
    ModelNotFoundError,
)
from studio_domain.services import WorkflowDomainService
from studio_store import StudioJsonStore, StudioStoreError
from workflow_metadata import iter_graph_nodes

_log = logging.getLogger(__name__)

_COMPAT_STATUSES = ("compatible", "incompatible", "untested")

_FROZEN_INCOMPATIBLE_MSG = (
    "cannot mark incompatible a model in the frozen compatible list for this version"
)

_INSTALL_REQUEST_NOTE = (
    "Approved for install. Execution is not automatic; "
    "use the existing /comfymodal/model/install endpoint to download."
)

_CUSTOM_NODE_INSTALL_NOTE = (
    "Approval recorded. Installation/update is not executed automatically; "
    "show this contract to the user and require explicit confirmation before "
    "any git operation."
)


def _json_error(status: int, message: str) -> web.Response:
    return web.json_response({"status": "error", "message": message}, status=status)


async def _read_body(request: web.Request) -> dict[str, Any] | None:
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def _graph_has_nodes(graph: Any) -> bool:
    """True for a stored UI/static graph that actually carries node rows.

    Uses the recursive walker so a graph whose real nodes live only inside
    group/subgraph containers still counts as a full UI graph.
    """
    return any(
        isinstance(node.get("type"), str) and node.get("type")
        for node in iter_graph_nodes(graph)
    )


def _version_for_resolution(
    version: dict[str, Any], workflow_service: WorkflowDomainService
) -> dict[str, Any]:
    """Copied version exposing the owning Workflow's static graph alongside it.

    A WorkflowVersion persists the executable API prompt, but the owning
    Workflow keeps the user-facing ``static_graph``, which records UI-only node
    types and model widgets the API prompt never contains — including nodes
    nested under ``extra.groupNodes`` / ``definitions.subgraphs``. Even when the
    version already carries top-level graph nodes, its capture may lack those
    parent-only nested definitions, so the parent graph is always supplied
    through the ``static_graph`` alias the resolver already scans.

    The version's own ``graph_json`` stays authoritative for duplicate node
    ids/classes: the resolver scans ``graph_json`` before ``static_graph`` and
    first-seen wins, so the parent graph only contributes its extra nested
    definitions/groups/subgraphs. A version that already carries a full UI graph
    under the ``static_graph`` key is left untouched. The persisted version dict
    is never mutated.
    """
    if not isinstance(version, dict):
        return version
    workflow_id = str(version.get("workflow_id") or "")
    if not workflow_id:
        return version
    try:
        workflow = workflow_service.store.get_workflow(workflow_id)
    except (StudioStoreError, OSError):
        return version
    if not isinstance(workflow, dict):
        return version
    parent_graph = workflow.get("static_graph")
    if not _graph_has_nodes(parent_graph):
        return version
    # The version's own static_graph alias, when present, is already scanned by
    # the resolver and stays authoritative; never clobber it with the parent.
    if _graph_has_nodes(version.get("static_graph")):
        return version
    resolved = dict(version)
    resolved["static_graph"] = parent_graph
    return resolved


def register_model_library_routes(
    server: Any,
    node_dir: str | Path,
    comfyui_root: str | Path,
    resolver: DependencyResolver | None = None,
) -> None:
    """Register the Studio Model Library + dependency routes on *server*."""
    node_dir = str(node_dir)
    comfyui_root = str(comfyui_root)
    if resolver is None:
        resolver = DependencyResolver(node_dir, comfyui_root)

    service = ModelLibraryService(node_dir, comfyui_root)
    registry = CustomNodeRegistryStore(node_dir)
    discovery = CustomNodeDiscovery(node_dir)
    compat_store = StudioJsonStore(Path(node_dir) / ".studio_workflow_compatibility.json")
    workflow_service = WorkflowDomainService(node_dir)

    # Cached core-class count from the most recent custom-node discovery.
    _core_count = 0

    # ── compatibility annotations helpers ───────────────────────────────

    def _get_compat_record(version_id: str) -> dict[str, Any] | None:
        for record in compat_store.read():
            if record.get("version_id") == version_id:
                return record
        return None

    def _read_annotations(version_id: str) -> dict[str, Any]:
        record = _get_compat_record(version_id)
        annotations = record.get("annotations") if record else None
        return dict(annotations) if isinstance(annotations, dict) else {}

    def _upsert_annotations(version_id: str, annotations: dict[str, Any]) -> dict[str, Any]:
        def _mutate(rows: list[dict]) -> None:
            for i, record in enumerate(rows):
                if record.get("version_id") == version_id:
                    rows[i] = {"version_id": version_id, "annotations": annotations}
                    return
            rows.append({"version_id": version_id, "annotations": annotations})

        compat_store.update(_mutate)
        return annotations

    # ── Models ──────────────────────────────────────────────────────────

    @server.routes.get("/comfymodal/studio/models")
    async def models_list(request: web.Request) -> web.Response:
        try:
            models = service.list_models(
                search=request.query.get("search") or "",
                model_type=request.query.get("type") or "",
                state=request.query.get("state") or "",
            )
            scan_hint = "ok" if service.store.list_records() else "not_scanned"
            return web.json_response(
                {
                    "status": "ok",
                    "models": models,
                    "total": len(models),
                    "scan_hint": scan_hint,
                }
            )
        except StudioStoreError:
            _log.exception("Model list failed (store unreadable)")
            return web.json_response(
                {
                    "status": "ok",
                    "models": [],
                    "total": 0,
                    "scan_hint": "unavailable",
                }
            )
        except Exception as exc:  # noqa: BLE001
            _log.exception("Model list failed")
            return _json_error(500, "Internal error")

    @server.routes.get("/comfymodal/studio/models/types")
    async def models_types(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "types": MODEL_TYPES})

    @server.routes.post("/comfymodal/studio/models/rescan")
    async def models_rescan(request: web.Request) -> web.Response:
        body = await _read_body(request)
        force = bool(body.get("force_rehash", False)) if isinstance(body, dict) else False
        try:
            summary = service.rescan(force_rehash=force)
            return web.json_response({"status": "ok", "summary": summary})
        except Exception as exc:  # noqa: BLE001
            _log.exception("Model rescan failed")
            return _json_error(500, "Internal error")

    @server.routes.get("/comfymodal/studio/models/{model_id}")
    async def models_detail(request: web.Request) -> web.Response:
        model_id = request.match_info.get("model_id", "")
        try:
            model = service.get_model(model_id)
            return web.json_response({"status": "ok", "model": model})
        except ModelLibraryError as exc:
            return _json_error(404, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Model detail failed")
            return _json_error(500, "Internal error")

    @server.routes.patch("/comfymodal/studio/models/{model_id}")
    async def models_update(request: web.Request) -> web.Response:
        model_id = request.match_info.get("model_id", "")
        body = await _read_body(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        try:
            model = service.update_metadata(model_id, body)
            return web.json_response({"status": "ok", "model": model})
        except ModelNotFoundError as exc:
            return _json_error(404, str(exc))
        except ModelLibraryError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Model update failed")
            return _json_error(500, "Internal error")

    @server.routes.post("/comfymodal/studio/models/install-request")
    async def models_install_request(request: web.Request) -> web.Response:
        body = await _read_body(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        try:
            request_payload = service.install_request(
                str(body.get("folder", "")),
                str(body.get("filename", "")),
                str(body.get("url", "")),
            )
            return web.json_response(
                {
                    "status": "ok",
                    "request": request_payload,
                    "note": _INSTALL_REQUEST_NOTE,
                }
            )
        except ModelLibraryError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Model install request failed")
            return _json_error(500, "Internal error")

    # ── Custom nodes ────────────────────────────────────────────────────

    @server.routes.get("/comfymodal/studio/custom-nodes")
    async def custom_nodes_list(request: web.Request) -> web.Response:
        nonlocal _core_count
        try:
            records = registry.list_records()
            if not records:
                discovered, core = discovery.refresh(comfyui_root)
                records = discovered
                _core_count = len(core)
            return web.json_response(
                {"status": "ok", "custom_nodes": records, "core_classes": _core_count}
            )
        except Exception as exc:  # noqa: BLE001
            _log.exception("Custom nodes list failed")
            return _json_error(500, "Internal error")

    @server.routes.post("/comfymodal/studio/custom-nodes/refresh")
    async def custom_nodes_refresh(request: web.Request) -> web.Response:
        nonlocal _core_count
        try:
            discovered, core = discovery.refresh(comfyui_root)
            _core_count = len(core)
            return web.json_response({"status": "ok", "custom_nodes": discovered})
        except Exception as exc:  # noqa: BLE001
            _log.exception("Custom nodes refresh failed")
            return _json_error(500, "Internal error")

    @server.routes.post("/comfymodal/studio/custom-nodes/install-request")
    async def custom_nodes_install_request(request: web.Request) -> web.Response:
        body = await _read_body(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        name = str(body.get("name") or "").strip()
        if not name:
            return _json_error(400, "name is required")
        repo_url = str(body.get("repo_url") or "").strip()
        revision = str(body.get("revision") or "").strip()
        return web.json_response(
            {
                "status": "ok",
                "request": {
                    "name": name,
                    "repo_url": repo_url,
                    "revision": revision,
                    "approved": True,
                },
                "note": _CUSTOM_NODE_INSTALL_NOTE,
            }
        )

    # ── Dependencies ────────────────────────────────────────────────────

    @server.routes.get("/comfymodal/studio/workflows/versions/{version_id}/dependencies")
    async def version_dependencies(request: web.Request) -> web.Response:
        version_id = request.match_info.get("version_id", "")
        try:
            version = workflow_service.store.get_version(version_id)
            if version is None:
                return _json_error(404, f"workflow version {version_id!r} not found")
            result = resolver.resolve_version(
                _version_for_resolution(version, workflow_service)
            )
            return web.json_response(
                {
                    "status": "ok",
                    "version_id": version_id,
                    "models": result["models"],
                    "custom_nodes": result["custom_nodes"],
                    "unresolvable": result.get("unresolvable", []),
                    "summary": result["summary"],
                }
            )
        except Exception as exc:  # noqa: BLE001
            _log.exception("Version dependencies failed")
            return _json_error(500, "Internal error")

    @server.routes.get("/comfymodal/studio/workflows/versions/{version_id}/compatibility")
    async def version_compatibility(request: web.Request) -> web.Response:
        version_id = request.match_info.get("version_id", "")
        try:
            version = workflow_service.store.get_version(version_id)
            if version is None:
                return _json_error(404, f"workflow version {version_id!r} not found")
            frozen = list(version.get("compatible_models") or [])
            annotations = _read_annotations(version_id)
            compatible = [{"model": m, "note": ""} for m in frozen]
            incompatible = [
                {"model": name, "note": str(ann.get("note") or "")}
                for name, ann in annotations.items()
                if ann.get("status") == "incompatible" and name not in frozen
            ]
            untested = [
                {"model": name, "note": str(ann.get("note") or "")}
                for name, ann in annotations.items()
                if ann.get("status") == "untested"
            ]
            return web.json_response(
                {
                    "status": "ok",
                    "version_id": version_id,
                    "compatible": compatible,
                    "incompatible": incompatible,
                    "untested": untested,
                    "annotations": annotations,
                }
            )
        except Exception as exc:  # noqa: BLE001
            _log.exception("Version compatibility failed")
            return _json_error(500, "Internal error")

    @server.routes.patch("/comfymodal/studio/workflows/versions/{version_id}/compatibility")
    async def version_compatibility_update(request: web.Request) -> web.Response:
        version_id = request.match_info.get("version_id", "")
        body = await _read_body(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        model_name = str(body.get("model_name") or "").strip()
        status = str(body.get("status") or "").strip()
        note = str(body.get("note") or "")
        try:
            version = workflow_service.store.get_version(version_id)
            if version is None:
                return _json_error(404, f"workflow version {version_id!r} not found")
            if status not in _COMPAT_STATUSES:
                return _json_error(
                    400,
                    f"invalid status {status!r}; must be one of: "
                    + ", ".join(_COMPAT_STATUSES),
                )
            frozen = list(version.get("compatible_models") or [])
            if status == "incompatible" and model_name in frozen:
                return _json_error(400, _FROZEN_INCOMPATIBLE_MSG)
            annotations = _read_annotations(version_id)
            annotations[model_name] = {"status": status, "note": note}
            _upsert_annotations(version_id, annotations)
            return web.json_response({"status": "ok", "annotations": annotations})
        except Exception as exc:  # noqa: BLE001
            _log.exception("Version compatibility update failed")
            return _json_error(500, "Internal error")
