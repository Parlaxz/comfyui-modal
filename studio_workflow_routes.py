"""HTTP route handlers for the Studio Workflow platform (V2 domain).

Routes are registered by calling ``register_workflow_routes(server, node_dir)``.
All business rules live in ``studio_domain.services.WorkflowDomainService``;
these handlers only translate HTTP <-> service calls.  Persistence is the
domain store under *node_dir* (``.studio_workflows.json`` /
``.studio_workflow_versions.json`` / ``.studio_workflow_mappings.json`` /
``.studio_workflow_presets.json``).

Domain invariants enforced by the service (never re-implemented here):

* Workflow Versions are immutable -- no endpoint mutates or deletes a version.
* A Mapping can be inserted only once per Version (``POST .../mapping``).
* Mapping edits create a NEW Version (``POST .../mapping/revision``).
* Presets are tied to their Version and only move forward via copy-forward.
* Incomplete Versions/Presets are saved but report ``state.runnable=false``.

Route summary (all under ``/comfymodal/studio/workflows``):

    Workflows:
        GET   /comfymodal/studio/workflows                            -- list/search
        POST  /comfymodal/studio/workflows                            -- create
        POST  /comfymodal/studio/workflows/import                     -- create + first version from capture
        GET   /comfymodal/studio/workflows/folders                    -- folder tree
        GET   /comfymodal/studio/workflows/tags                       -- tag list
        GET   /comfymodal/studio/workflows/{workflow_id}              -- detail
        PATCH /comfymodal/studio/workflows/{workflow_id}              -- update metadata
        POST  /comfymodal/studio/workflows/{workflow_id}/default-preset   -- set default preset
        DELETE /comfymodal/studio/workflows/{workflow_id}/default-preset -- clear default preset
        GET   /comfymodal/studio/workflows/{workflow_id}/run-context  -- Playground bundle

    Versions (immutable):
        GET   /comfymodal/studio/workflows/{workflow_id}/versions       -- list
        POST  /comfymodal/studio/workflows/{workflow_id}/versions       -- capture/import new version
        GET   /comfymodal/studio/workflows/versions/{version_id}        -- detail (enriched)
        GET   /comfymodal/studio/workflows/versions/{version_id}/state  -- derived runnable state

    Mapping:
        GET   /comfymodal/studio/workflows/versions/{version_id}/mapping        -- mapping or null
        POST  /comfymodal/studio/workflows/versions/{version_id}/mapping        -- create initial mapping (409 if exists)
        GET   /comfymodal/studio/workflows/versions/{version_id}/mapping/candidates -- graph-derived candidates
        POST  /comfymodal/studio/workflows/versions/{version_id}/mapping/revision -- create NEW version with mapping

    Presets:
        GET   /comfymodal/studio/workflows/versions/{version_id}/presets        -- list for version
        POST  /comfymodal/studio/workflows/versions/{version_id}/presets        -- create
        GET   /comfymodal/studio/workflows/presets/{preset_id}                  -- detail
        PATCH /comfymodal/studio/workflows/presets/{preset_id}                  -- update
        DELETE /comfymodal/studio/workflows/presets/{preset_id}                 -- delete
        POST  /comfymodal/studio/workflows/presets/{preset_id}/duplicate        -- duplicate
        POST  /comfymodal/studio/workflows/presets/{preset_id}/copy-to-version  -- copy forward
        POST  /comfymodal/studio/workflows/versions/{version_id}/presets/copy-bulk -- bulk copy forward

Error responses always include a stable ``"message"`` key and use appropriate
HTTP status codes (400 validation, 404 not found, 409 already-exists/immutable,
500 storage).  Internal exceptions are logged.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from aiohttp import web

from studio_domain import (
    GraphHashError,
    ImmutableVersionError,
    MappingAlreadyExistsError,
    MappingNotFoundError,
    PresetCopyError,
    WorkflowDomainError,
    WorkflowNotFoundError,
    WorkflowNotRunnableError,
    WorkflowPresetNotFoundError,
    WorkflowPresetValidationError,
    WorkflowVersionNotFoundError,
    derive_mapping_candidates,
)
from studio_domain.services import WorkflowDomainService

_log = logging.getLogger(__name__)


def _json_error(status: int, message: str) -> web.Response:
    return web.json_response({"status": "error", "message": message}, status=status)


def _domain_status(exc: Exception) -> tuple[int, str]:
    """Map a domain exception to ``(http_status, message)``."""
    if isinstance(exc, (WorkflowNotFoundError, WorkflowVersionNotFoundError,
                        MappingNotFoundError, WorkflowPresetNotFoundError)):
        return 404, str(exc)
    if isinstance(exc, (MappingAlreadyExistsError, ImmutableVersionError,
                        WorkflowNotRunnableError)):
        return 409, str(exc)
    if isinstance(exc, (WorkflowPresetValidationError, PresetCopyError, GraphHashError)):
        return 400, str(exc)
    if isinstance(exc, WorkflowDomainError):
        return 400, str(exc)
    return 500, "Internal error"


async def _read_body(request: web.Request) -> dict[str, Any] | None:
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def _enrich_workflow_summary(
    service: WorkflowDomainService, raw: dict[str, Any]
) -> dict[str, Any]:
    """Lightweight summary for library lists (no heavy per-item enrichment)."""
    summary = dict(raw)
    workflow_id = str(raw.get("workflow_id", ""))
    versions = service.store.list_versions_for_workflow(workflow_id)
    summary["version_count"] = len(versions)
    latest_id = str(raw.get("latest_version_id", ""))
    latest = None
    if latest_id:
        for v in versions:
            if v.get("workflow_version_id") == latest_id:
                latest = v
                break
    summary["latest_version_number"] = (
        int(latest.get("version_number", 0)) if latest else None
    )
    summary["latest_version_state"] = (
        service.derive_version_state(latest_id).to_dict() if latest else None
    )
    default_id = str(raw.get("default_preset_id", ""))
    default_preset = service.store.get_preset(default_id) if default_id else None
    summary["default_preset_name"] = (
        str(default_preset.get("name", "")) if default_preset else None
    )
    return summary


def register_workflow_routes(
    server: Any, node_dir: str | Path, resolver: Any = None
) -> None:
    """Register all Studio Workflow platform routes on *server*.

    *server* must expose ``server.routes.get(path)``, ``.post(path)``,
    ``.patch(path)``, and ``.delete(path)`` decorators (matching the
    ``PromptServer.instance.routes`` interface).

    *resolver* — optional dependency resolver whose ``reasons_for`` feeds the
    workflow service's derived version state and whose ``resolve_version``
    result is attached to the workflow import response.
    """
    service = WorkflowDomainService(
        str(node_dir),
        dependency_provider=(resolver.reasons_for if resolver is not None else None),
    )

    # ── Workflows ─────────────────────────────────────────────────────

    @server.routes.get("/comfymodal/studio/workflows")
    async def workflows_list(request: web.Request) -> web.Response:
        try:
            workflows = service.list_workflows()
            search = (request.query.get("search") or "").strip().lower()
            tag = (request.query.get("tag") or "").strip()
            folder = (request.query.get("folder") or "").strip()
            favorite_only = request.query.get("favorite", "") == "1"
            enriched = []
            for wf in workflows:
                name = str(wf.get("name", "")).lower()
                desc = str(wf.get("description", "")).lower()
                tags = [str(t) for t in (wf.get("tags") or [])]
                wf_folder = str(wf.get("folder", ""))
                if search and search not in name and search not in desc:
                    continue
                if tag and tag not in tags:
                    continue
                if folder and not (wf_folder == folder or wf_folder.startswith(folder + "/")):
                    continue
                if favorite_only and not wf.get("favorite"):
                    continue
                enriched.append(_enrich_workflow_summary(service, wf))
            return web.json_response({"status": "ok", "workflows": enriched})
        except Exception as exc:  # noqa: BLE001
            _log.exception("Workflow list failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.post("/comfymodal/studio/workflows")
    async def workflows_create(request: web.Request) -> web.Response:
        body = await _read_body(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        try:
            workflow = service.create_workflow(
                str(body.get("name", "")),
                description=str(body.get("description", "")),
                folder=str(body.get("folder", "")),
                tags=body.get("tags"),
                favorite=bool(body.get("favorite", False)),
                source_url=str(body.get("source_url", "")),
                source_author=str(body.get("source_author", "")),
                compatible_models=body.get("compatible_models"),
            )
            return web.json_response({"status": "ok", "workflow": workflow})
        except WorkflowPresetValidationError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Workflow create failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.post("/comfymodal/studio/workflows/import")
    async def workflows_import(request: web.Request) -> web.Response:
        """Create a Workflow and its first graph Version from a capture."""
        body = await _read_body(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        try:
            capture = {
                "graph_json": body.get("graph_json") or {},
                "api_prompt_json": body.get("api_prompt_json") or {},
            }
            workflow = service.create_workflow(
                str(body.get("name", "")),
                description=str(body.get("description", "")),
                folder=str(body.get("folder", "")),
                tags=body.get("tags"),
                favorite=bool(body.get("favorite", False)),
                source_url=str(body.get("source_url", "")),
                source_author=str(body.get("source_author", "")),
                compatible_models=body.get("compatible_models"),
            )
            version = service.create_version_from_capture(
                str(workflow.get("workflow_id", "")), capture
            )
            payload = {
                "status": "ok",
                "workflow": workflow,
                "version": version,
            }
            if resolver is not None:
                payload["dependency_summary"] = resolver.resolve_version(version)
            return web.json_response(payload)
        except WorkflowPresetValidationError as exc:
            return _json_error(400, str(exc))
        except GraphHashError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Workflow import failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.get("/comfymodal/studio/workflows/folders")
    async def workflows_folders(request: web.Request) -> web.Response:
        try:
            return web.json_response({"status": "ok", "folders": service.list_folders()})
        except Exception as exc:  # noqa: BLE001
            _log.exception("Workflow folders failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.get("/comfymodal/studio/workflows/tags")
    async def workflows_tags(request: web.Request) -> web.Response:
        try:
            return web.json_response({"status": "ok", "tags": service.list_tags()})
        except Exception as exc:  # noqa: BLE001
            _log.exception("Workflow tags failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.get("/comfymodal/studio/workflows/{workflow_id}")
    async def workflows_detail(request: web.Request) -> web.Response:
        wf_id = request.match_info.get("workflow_id", "")
        try:
            workflow = service.get_workflow(wf_id)
            return web.json_response({"status": "ok", "workflow": workflow})
        except WorkflowNotFoundError as exc:
            return _json_error(404, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Workflow detail failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.patch("/comfymodal/studio/workflows/{workflow_id}")
    async def workflows_update(request: web.Request) -> web.Response:
        wf_id = request.match_info.get("workflow_id", "")
        body = await _read_body(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        try:
            workflow = service.update_workflow(wf_id, body)
            return web.json_response({"status": "ok", "workflow": workflow})
        except WorkflowNotFoundError as exc:
            return _json_error(404, str(exc))
        except WorkflowPresetValidationError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Workflow update failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.post("/comfymodal/studio/workflows/{workflow_id}/default-preset")
    async def workflows_set_default_preset(request: web.Request) -> web.Response:
        wf_id = request.match_info.get("workflow_id", "")
        body = await _read_body(request)
        if body is None or not body.get("preset_id"):
            return _json_error(400, "preset_id is required")
        try:
            workflow = service.set_default_preset(wf_id, str(body["preset_id"]))
            return web.json_response({"status": "ok", "workflow": workflow})
        except (WorkflowNotFoundError, WorkflowPresetNotFoundError) as exc:
            return _json_error(404, str(exc))
        except WorkflowPresetValidationError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Set default preset failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.delete("/comfymodal/studio/workflows/{workflow_id}/default-preset")
    async def workflows_clear_default_preset(request: web.Request) -> web.Response:
        wf_id = request.match_info.get("workflow_id", "")
        try:
            workflow = service.clear_default_preset(wf_id)
            return web.json_response({"status": "ok", "workflow": workflow})
        except WorkflowNotFoundError as exc:
            return _json_error(404, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Clear default preset failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.get("/comfymodal/studio/workflows/{workflow_id}/run-context")
    async def workflows_run_context(request: web.Request) -> web.Response:
        """Read-only Playground bundle: workflow + selected version + mapping +
        default preset + runnable state + control schema."""
        wf_id = request.match_info.get("workflow_id", "")
        version_id = request.query.get("version_id") or ""
        try:
            workflow = service.get_workflow(wf_id)
            if not version_id:
                version_id = str(workflow.get("latest_version_id", ""))
            version = None
            mapping = None
            state = {"status": "incomplete", "reasons": ["no versions"], "runnable": False}
            if version_id:
                version = service.get_version(version_id)
                state = service.derive_version_state(version_id).to_dict()
                mapping = service.get_mapping(version_id)
            default_preset = service.get_default_preset(wf_id)
            control_schema: dict[str, Any] = {}
            if mapping:
                for entry in mapping.get("entries") or []:
                    if isinstance(entry, dict) and entry.get("semantic_role"):
                        control_schema[str(entry["semantic_role"])] = entry
            return web.json_response({
                "status": "ok",
                "workflow": workflow,
                "version": version,
                "mapping": mapping,
                "default_preset": default_preset,
                "state": state,
                "control_schema": control_schema,
            })
        except (WorkflowNotFoundError, WorkflowVersionNotFoundError) as exc:
            return _json_error(404, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Run context failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    # ── Versions (immutable) ──────────────────────────────────────────

    @server.routes.get("/comfymodal/studio/workflows/{workflow_id}/versions")
    async def versions_list(request: web.Request) -> web.Response:
        wf_id = request.match_info.get("workflow_id", "")
        try:
            versions = service.list_versions(wf_id)
            return web.json_response({"status": "ok", "versions": versions})
        except WorkflowNotFoundError as exc:
            return _json_error(404, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Version list failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.post("/comfymodal/studio/workflows/{workflow_id}/versions")
    async def versions_capture(request: web.Request) -> web.Response:
        """Capture/import a new graph Version from a ComfyUI capture."""
        wf_id = request.match_info.get("workflow_id", "")
        body = await _read_body(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        try:
            capture = {
                "graph_json": body.get("graph_json") or {},
                "api_prompt_json": body.get("api_prompt_json") or {},
            }
            version = service.create_version_from_capture(wf_id, capture)
            return web.json_response({"status": "ok", "version": version})
        except WorkflowNotFoundError as exc:
            return _json_error(404, str(exc))
        except GraphHashError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Version capture failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.get("/comfymodal/studio/workflows/versions/{version_id}")
    async def versions_detail(request: web.Request) -> web.Response:
        version_id = request.match_info.get("version_id", "")
        try:
            version = service.get_version(version_id)
            return web.json_response({"status": "ok", "version": version})
        except WorkflowVersionNotFoundError as exc:
            return _json_error(404, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Version detail failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.get("/comfymodal/studio/workflows/versions/{version_id}/state")
    async def versions_state(request: web.Request) -> web.Response:
        version_id = request.match_info.get("version_id", "")
        try:
            state = service.derive_version_state(version_id).to_dict()
            return web.json_response({"status": "ok", "state": state})
        except Exception as exc:  # noqa: BLE001
            _log.exception("Version state failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    # ── Mapping ────────────────────────────────────────────────────────

    @server.routes.get("/comfymodal/studio/workflows/versions/{version_id}/mapping")
    async def mapping_get(request: web.Request) -> web.Response:
        version_id = request.match_info.get("version_id", "")
        try:
            mapping = service.get_mapping(version_id)
            return web.json_response({"status": "ok", "mapping": mapping})
        except Exception as exc:  # noqa: BLE001
            _log.exception("Mapping get failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.post("/comfymodal/studio/workflows/versions/{version_id}/mapping")
    async def mapping_create(request: web.Request) -> web.Response:
        """Create the single immutable Mapping for a Version (409 if present)."""
        version_id = request.match_info.get("version_id", "")
        body = await _read_body(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        try:
            mapping = service.set_mapping(
                version_id,
                entries=body.get("entries") or {},
                output_node_id=str(body.get("output_node_id", "")),
            )
            return web.json_response({"status": "ok", "mapping": mapping})
        except WorkflowVersionNotFoundError as exc:
            return _json_error(404, str(exc))
        except MappingAlreadyExistsError as exc:
            return _json_error(409, str(exc))
        except WorkflowPresetValidationError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Mapping create failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.get("/comfymodal/studio/workflows/versions/{version_id}/mapping/candidates")
    async def mapping_candidates(request: web.Request) -> web.Response:
        """Graph-derived mapping candidates for the Version's stored capture."""
        version_id = request.match_info.get("version_id", "")
        try:
            version = service.get_version(version_id)
            capture = {
                "graph_json": version.get("graph_json") or {},
                "api_prompt_json": version.get("api_prompt_json") or {},
            }
            entries, output_node_id = derive_mapping_candidates(capture)
            return web.json_response({
                "status": "ok",
                "candidates": {role: e.to_dict() for role, e in entries.items()},
                "output_node_id": output_node_id,
            })
        except WorkflowVersionNotFoundError as exc:
            return _json_error(404, str(exc))
        except GraphHashError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Mapping candidates failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.post("/comfymodal/studio/workflows/versions/{version_id}/mapping/revision")
    async def mapping_revision(request: web.Request) -> web.Response:
        """Change a Mapping by creating a NEW immutable Workflow Version."""
        version_id = request.match_info.get("version_id", "")
        body = await _read_body(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        try:
            version = service.create_mapping_revision(
                version_id,
                entries=body.get("entries") or {},
                output_node_id=str(body.get("output_node_id", "")),
            )
            return web.json_response({"status": "ok", "version": version})
        except WorkflowVersionNotFoundError as exc:
            return _json_error(404, str(exc))
        except WorkflowPresetValidationError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Mapping revision failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    # ── Presets ────────────────────────────────────────────────────────

    @server.routes.get("/comfymodal/studio/workflows/versions/{version_id}/presets")
    async def presets_list(request: web.Request) -> web.Response:
        version_id = request.match_info.get("version_id", "")
        try:
            presets = service.list_presets(version_id)
            return web.json_response({"status": "ok", "presets": presets})
        except WorkflowVersionNotFoundError as exc:
            return _json_error(404, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Preset list failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.post("/comfymodal/studio/workflows/versions/{version_id}/presets")
    async def presets_create(request: web.Request) -> web.Response:
        version_id = request.match_info.get("version_id", "")
        body = await _read_body(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        try:
            preset = service.create_preset(
                version_id,
                str(body.get("name", "")),
                description=str(body.get("description", "")),
                values=body.get("values"),
                model_choices=body.get("model_choices"),
                lora_values=body.get("lora_values"),
                exposed_controls=body.get("exposed_controls"),
                recommended_values=body.get("recommended_values"),
                favorite=bool(body.get("favorite", False)),
                tags=body.get("tags"),
            )
            return web.json_response({"status": "ok", "preset": preset})
        except WorkflowVersionNotFoundError as exc:
            return _json_error(404, str(exc))
        except WorkflowPresetValidationError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Preset create failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.get("/comfymodal/studio/workflows/presets/{preset_id}")
    async def presets_detail(request: web.Request) -> web.Response:
        preset_id = request.match_info.get("preset_id", "")
        try:
            preset = service.get_preset(preset_id)
            return web.json_response({"status": "ok", "preset": preset})
        except WorkflowPresetNotFoundError as exc:
            return _json_error(404, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Preset detail failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.patch("/comfymodal/studio/workflows/presets/{preset_id}")
    async def presets_update(request: web.Request) -> web.Response:
        preset_id = request.match_info.get("preset_id", "")
        body = await _read_body(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        try:
            preset = service.update_preset(preset_id, body)
            return web.json_response({"status": "ok", "preset": preset})
        except WorkflowPresetNotFoundError as exc:
            return _json_error(404, str(exc))
        except WorkflowPresetValidationError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Preset update failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.delete("/comfymodal/studio/workflows/presets/{preset_id}")
    async def presets_delete(request: web.Request) -> web.Response:
        preset_id = request.match_info.get("preset_id", "")
        try:
            service.delete_preset(preset_id)
            return web.json_response({"status": "ok"})
        except WorkflowPresetNotFoundError as exc:
            return _json_error(404, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Preset delete failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.post("/comfymodal/studio/workflows/presets/{preset_id}/duplicate")
    async def presets_duplicate(request: web.Request) -> web.Response:
        preset_id = request.match_info.get("preset_id", "")
        try:
            preset = service.duplicate_preset(preset_id)
            return web.json_response({"status": "ok", "preset": preset})
        except WorkflowPresetNotFoundError as exc:
            return _json_error(404, str(exc))
        except WorkflowPresetValidationError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Preset duplicate failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.post("/comfymodal/studio/workflows/presets/{preset_id}/copy-to-version")
    async def presets_copy_forward(request: web.Request) -> web.Response:
        preset_id = request.match_info.get("preset_id", "")
        body = await _read_body(request)
        if body is None or not body.get("target_version_id"):
            return _json_error(400, "target_version_id is required")
        try:
            result = service.copy_preset_to_version(
                preset_id, str(body["target_version_id"])
            )
            return web.json_response({"status": "ok", "result": result})
        except WorkflowPresetNotFoundError as exc:
            return _json_error(404, str(exc))
        except WorkflowVersionNotFoundError as exc:
            return _json_error(404, str(exc))
        except PresetCopyError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Preset copy forward failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.post(
        "/comfymodal/studio/workflows/versions/{version_id}/presets/copy-bulk"
    )
    async def presets_copy_bulk(request: web.Request) -> web.Response:
        version_id = request.match_info.get("version_id", "")
        body = await _read_body(request)
        if body is None or not isinstance(body.get("preset_ids"), list):
            return _json_error(400, "preset_ids list is required")
        try:
            results = service.copy_presets_to_version(
                [str(pid) for pid in body["preset_ids"]], version_id
            )
            return web.json_response({"status": "ok", "results": results})
        except WorkflowVersionNotFoundError as exc:
            return _json_error(404, str(exc))
        except PresetCopyError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Preset bulk copy failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)
