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
        GET   /comfymodal/studio/custom-nodes/sync-status       -- read-only parity report

    Dependencies:
        GET   /comfymodal/studio/workflows/versions/{version_id}/dependencies
        GET   /comfymodal/studio/workflows/versions/{version_id}/compatibility
        PATCH /comfymodal/studio/workflows/versions/{version_id}/compatibility
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from aiohttp import web

from custom_node_registry import CustomNodeDiscovery, CustomNodeRegistryStore
from comfymodal_runtime.custom_node_identity import resolve_plugin_identity
from comfymodal_runtime.custom_node_root import resolve_custom_nodes_root
from comfymodal_runtime.publication_policy import (
    CUSTOM_NODES_VOLUME_NAME,
    canonical_publication_bytes,
    compute_publication_generation,
    iter_publication_files,
)
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
from tools.v2_control.custom_nodes import ReceiptError, get_volume, read_receipt

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


_SYNC_STATUS_KEYS = (
    "status", "inventory_state", "payload_state", "local_only", "published_only",
    "duplicates", "unknown_identity", "dependencies_changed", "dependencies_state",
    "receipt_schema_supported", "local_generation", "published_generation",
)


def _sync_entry(name: str, identity: Any, source: str, confidence: str) -> dict[str, Any]:
    return {
        "name": str(name),
        "identity": identity if isinstance(identity, str) and identity else None,
        "identity_source": str(source),
        "confidence": str(confidence),
    }


def _published_identity(item: Mapping[str, Any]) -> tuple[str | None, str, str]:
    for key in ("identity", "repo_url", "repository_url", "canonical_identity"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            # Resolve the URL through the same canonical rules as local nodes.
            from comfymodal_runtime.custom_node_identity import normalize_repository_url
            normalized = normalize_repository_url(value)
            if normalized:
                return normalized, "receipt_identity", "high"
    return None, "receipt_package_name", "weak"


def _requirements_record(package: Path) -> tuple[bool, str | None]:
    path = package / "requirements.txt"
    try:
        if not path.is_file():
            return True, None
        data = canonical_publication_bytes(path, path.read_bytes())
    except OSError:
        return False, None
    return True, hashlib.sha256(data).hexdigest()


def _receipt_requirement_digest(item: Mapping[str, Any]) -> tuple[bool, str | None]:
    for key in ("requirements_sha256", "requirements_digest", "requirements_content_digest"):
        value = item.get(key)
        if isinstance(value, str):
            return True, value
    raw = item.get("requirements")
    if isinstance(raw, str):
        return True, hashlib.sha256(raw.replace("\r\n", "\n").replace("\r", "\n").encode()).hexdigest()
    if isinstance(raw, Mapping):
        for key in ("sha256", "digest", "content_digest"):
            value = raw.get(key)
            if isinstance(value, str):
                return True, value
    if "requirements_present" in item and isinstance(item["requirements_present"], bool):
        return True, None if not item["requirements_present"] else ""
    return False, None


def _local_inventory(
    root: str | Path,
    provenance_records: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Path], dict[str, str]]:
    """Build inventory from the canonical publication file iterator only."""
    files = list(iter_publication_files(root))
    package_names = sorted({path.relative_to(Path(root).resolve()).parts[0] for path in files})
    package_paths = {name: Path(root).resolve() / name for name in package_names}
    by_path: dict[str, Mapping[str, Any]] = {}
    by_name: dict[str, Mapping[str, Any]] = {}
    for record in provenance_records:
        name = str(record.get("name") or "")
        if name:
            by_name[name] = record
        install_path = record.get("install_path")
        if isinstance(install_path, str) and install_path:
            try:
                by_path[str(Path(install_path).resolve())] = record
            except OSError:
                pass
    folded = Counter(name.casefold() for name in package_names)
    collisions = {name for name, count in folded.items() if count > 1}
    entries: list[dict[str, Any]] = []
    requirements: dict[str, str] = {}
    for name in package_names:
        package = package_paths[name]
        record = by_path.get(str(package.resolve())) or by_name.get(name)
        identity = resolve_plugin_identity(
            package,
            provenance=record,
            basename_collisions=collisions,
        )
        entries.append(_sync_entry(
            name, identity.identity, identity.identity_source, identity.confidence
        ))
        supported, digest = _requirements_record(package)
        if supported and digest is not None:
            requirements[name] = digest
    return entries, package_paths, requirements


def _sync_status_payload(
    *,
    root: str | Path,
    receipt: Any | None,
    provenance_records: Sequence[Mapping[str, Any]],
    receipt_schema_supported: bool,
) -> dict[str, Any]:
    """Compute the read-only comparison without touching publication state."""
    local, package_paths, local_requirements = _local_inventory(root, provenance_records)
    local_generation = compute_publication_generation(root)
    published_generation = getattr(receipt, "content_generation", None) if receipt else None
    if not isinstance(published_generation, str) or not published_generation:
        published_generation = None

    published: list[dict[str, Any]] = []
    published_raw: list[Mapping[str, Any]] = []
    if receipt is not None:
        raw_packages = getattr(receipt, "package_manifests", ())
        if isinstance(raw_packages, (list, tuple)):
            for raw in raw_packages:
                if not isinstance(raw, Mapping):
                    continue
                name = str(raw.get("name") or "")
                if not name:
                    continue
                identity, source, confidence = _published_identity(raw)
                published.append(_sync_entry(name, identity, source, confidence))
                published_raw.append(raw)
    unknown_identity = sorted(
        entry["name"] for entry in [*local, *published] if not entry["identity"]
    )

    local_known = all(
        item["identity"] and item["confidence"] not in {"weak", "ambiguous"}
        for item in local
    )
    published_known = bool(published) and all(item["identity"] for item in published)
    identity_comparable = receipt_schema_supported and local_known and published_known

    if identity_comparable:
        local_counts = Counter(resolve_plugin_identity_key(item) for item in local)
        published_counts = Counter(resolve_plugin_identity_key(item) for item in published)
    else:
        # A current receipt without identity metadata is still useful for a
        # degraded name inventory, but never supports an identity verdict.
        local_counts = Counter(item["name"] for item in local)
        published_counts = Counter(item["name"] for item in published)

    local_only = _counter_difference(local, local_counts - published_counts, identity_comparable)
    published_only = _counter_difference(published, published_counts - local_counts, identity_comparable)
    duplicates = _find_duplicates(local, published)
    if not receipt_schema_supported or receipt is None:
        inventory_state = "unknown"
        local_only = []
        published_only = []
    elif duplicates:
        inventory_state = "ambiguous"
    elif not identity_comparable or unknown_identity:
        inventory_state = "unknown"
    elif local_only or published_only:
        inventory_state = "differs"
    else:
        inventory_state = "match"

    if local_generation and published_generation:
        payload_state = "exact" if local_generation == published_generation else "differs"
    else:
        payload_state = "unknown"

    dependencies_changed: list[str] = []
    dependency_supported = bool(published_raw) and all(
        _receipt_requirement_digest(item)[0] for item in published_raw
    )
    if dependency_supported:
        for raw in published_raw:
            name = str(raw.get("name") or "")
            supported, expected = _receipt_requirement_digest(raw)
            actual = local_requirements.get(name)
            if supported and expected != actual:
                dependencies_changed.append(name)
        dependencies_state = "changed" if dependencies_changed else "same"
    else:
        dependencies_state = "unknown"

    return {
        "status": "ok",
        "inventory_state": inventory_state,
        "payload_state": payload_state,
        "local_only": sorted(local_only, key=_entry_sort_key),
        "published_only": sorted(published_only, key=_entry_sort_key),
        "duplicates": duplicates,
        "unknown_identity": unknown_identity,
        "dependencies_changed": sorted(set(dependencies_changed), key=str.casefold),
        "dependencies_state": dependencies_state,
        "receipt_schema_supported": bool(receipt_schema_supported),
        "local_generation": local_generation or None,
        "published_generation": published_generation,
    }


def resolve_plugin_identity_key(entry: Mapping[str, Any]) -> str:
    return str(entry.get("identity") or entry.get("name") or "").casefold()


def _entry_sort_key(entry: Mapping[str, Any]) -> tuple[str, str]:
    return (str(entry.get("name") or "").casefold(), str(entry.get("name") or ""))


def _counter_difference(
    entries: list[dict[str, Any]], difference: Counter[str], identity_mode: bool
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    remaining = Counter(difference)
    for entry in sorted(entries, key=_entry_sort_key):
        key = resolve_plugin_identity_key(entry) if identity_mode else entry["name"]
        if remaining[key] > 0:
            result.append(entry)
            remaining[key] -= 1
    return result


def _find_duplicates(local: list[dict[str, Any]], published: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    displays: dict[str, str] = {}
    for entry in [*local, *published]:
        identity = entry.get("identity")
        if not identity:
            continue
        key = str(identity).casefold()
        grouped[key].add(str(entry["name"]))
        displays.setdefault(key, str(identity))
    return [
        {"identity": displays[key], "names": sorted(names, key=lambda value: (value.casefold(), value))}
        for key, names in sorted(grouped.items()) if len(names) > 1
    ]


def register_model_library_routes(
    server: Any,
    node_dir: str | Path,
    comfyui_root: str | Path,
    resolver: DependencyResolver | None = None,
    *,
    custom_nodes_volume: Any | None = None,
    custom_nodes_volume_factory: Callable[[str], Any] | None = None,
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

    @server.routes.get("/comfymodal/studio/custom-nodes/sync-status")
    async def custom_nodes_sync_status(request: web.Request) -> web.Response:
        """Compare the local publication candidate with the read-only receipt."""
        try:
            source_root = resolve_custom_nodes_root(node_dir)
            try:
                provenance = registry.list_records()
            except Exception:
                provenance = []
            provenance = [item for item in provenance if isinstance(item, Mapping)]
        except Exception:
            return web.json_response({
                "status": "ok",
                "inventory_state": "unknown",
                "payload_state": "unknown",
                "local_only": [],
                "published_only": [],
                "duplicates": [],
                "unknown_identity": [],
                "dependencies_changed": [],
                "dependencies_state": "unknown",
                "receipt_schema_supported": False,
                "local_generation": None,
                "published_generation": None,
            })

        receipt = None
        receipt_supported = False
        try:
            volume = custom_nodes_volume
            if volume is None:
                volume = await asyncio.to_thread(
                    get_volume,
                    CUSTOM_NODES_VOLUME_NAME,
                    custom_nodes_volume_factory,
                )
            receipt = await asyncio.to_thread(
                read_receipt,
                volume,
                volume_name=CUSTOM_NODES_VOLUME_NAME,
            )
            receipt_supported = True
        except (ReceiptError, OSError, ValueError, TypeError):
            # A missing, old, or corrupt receipt is not evidence of a remote
            # difference.  Continue with local generation only.
            receipt = None
        except Exception:
            _log.exception("Custom-node sync receipt read failed")

        try:
            result = _sync_status_payload(
                root=source_root,
                receipt=receipt,
                provenance_records=provenance,
                receipt_schema_supported=receipt_supported,
            )
        except Exception:
            _log.exception("Custom-node sync status failed")
            result = {
                "status": "ok",
                "inventory_state": "unknown",
                "payload_state": "unknown",
                "local_only": [],
                "published_only": [],
                "duplicates": [],
                "unknown_identity": [],
                "dependencies_changed": [],
                "dependencies_state": "unknown",
                "receipt_schema_supported": False,
                "local_generation": None,
                "published_generation": None,
            }
        return web.json_response(result)

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
