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

    Portability (Phase G9 backend, Phase G11 cache integration):
        GET   /comfymodal/studio/workflows/versions/{version_id}/export      -- manifest v1 download (read-only)
        POST  /comfymodal/studio/workflows/import-manifest                   -- manifest import (dry_run default)
        GET   /comfymodal/studio/workflows/versions/{version_id}/portability -- G5 report; G10 cache hit serves directly,
                                                                                miss/stale/invalid recompute live
        Workflow list/detail rows carry an optional derived-only
        ``portability_summary`` chip ({version_id, risk_level, issue_count,
        stale, analyzed_at} or null) served from the cache WITHOUT any
        live analysis.

Error responses always include a stable ``"message"`` key and use appropriate
HTTP status codes (400 validation, 404 not found, 409 already-exists/immutable,
413 oversized payload, 500 storage).  Internal exceptions are logged.
"""

from __future__ import annotations

import json
import logging
import copy
from pathlib import Path
from typing import Any

from aiohttp import web

import portability_contract as portability_contract
import studio_workflow_manifest as studio_workflow_manifest
from custom_node_registry import CustomNodeRegistryStore
from model_library import ModelLibraryStore
from portability_cache import DEFAULT_SIDECAR_FILENAME, PortabilityReportCache
from portability_service import (
    ExportRefusedError,
    ImportBlockedError,
    PortabilityService,
    load_manifest_payload,
)
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


_WORKFLOW_CONFIG_FIELDS = (
    "static_graph", "bindings", "output_binding", "workflow_type",
    "saved_values", "layout_profile", "allowed_options",
)
_WORKFLOW_CONFIG_ALIASES = {
    "graph": "static_graph",
    "type": "workflow_type",
    "output": "output_binding",
    "layout": "layout_profile",
    "field_values": "saved_values",
    "values": "saved_values",
    "allowed_options_filters": "allowed_options",
}


def _workflow_config_kwargs(body: dict[str, Any]) -> dict[str, Any]:
    """Select only durable wrapper fields from a create/import body."""
    result: dict[str, Any] = {}
    for key, value in body.items():
        canonical = _WORKFLOW_CONFIG_ALIASES.get(key, key)
        if canonical in _WORKFLOW_CONFIG_FIELDS:
            result[canonical] = value
    if "require_complete" in body:
        result["require_complete"] = bool(body["require_complete"])
    return result


def _workflow_bundle_fields(workflow: dict[str, Any]) -> dict[str, Any]:
    """Whitelist durable Workflow config; drafts/history/output never cross it."""
    return {
        field: copy.deepcopy(workflow[field])
        for field in _WORKFLOW_CONFIG_FIELDS
        if field in workflow
    }


def _manifest_workflow_config(payload: dict[str, Any]) -> dict[str, Any]:
    section = payload.get("workflow")
    if not isinstance(section, dict):
        return {}
    fields = {
        key: copy.deepcopy(section[key])
        for key in _WORKFLOW_CONFIG_FIELDS
        if key in section
    }
    # v1's executable graph remains the integrity-bearing graph. Older
    # bundles use it as the best available static copy.
    if "static_graph" not in fields and isinstance(section.get("graph"), dict):
        fields["static_graph"] = copy.deepcopy(section["graph"])
    return fields


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
    server: Any,
    node_dir: str | Path,
    resolver: Any = None,
    portability_service: PortabilityService | None = None,
) -> None:
    """Register all Studio Workflow platform routes on *server*.

    *server* must expose ``server.routes.get(path)``, ``.post(path)``,
    ``.patch(path)``, and ``.delete(path)`` decorators (matching the
    ``PromptServer.instance.routes`` interface).

    *resolver* — optional dependency resolver whose ``reasons_for`` feeds the
    workflow service's derived version state and whose ``resolve_version``
    result is attached to the workflow import response.

    *portability_service* — optional pre-composed PortabilityService
    (injection seam for tests); by default one is composed here with the
    canonical G10 derived sidecar (``.studio_portability_reports.json``)
    under the SAME Studio local data root as the Workflow domain stores,
    plus Model Library / Custom Node Registry generation authorities for
    invalidation stamps (import/export semantics are untouched).
    """
    service = WorkflowDomainService(
        str(node_dir),
        dependency_provider=(resolver.reasons_for if resolver is not None else None),
    )
    if portability_service is not None:
        portability = portability_service
    else:
        cache = PortabilityReportCache(Path(node_dir) / DEFAULT_SIDECAR_FILENAME)
        try:
            model_generation_source = ModelLibraryStore(node_dir)
            registry_generation_source = CustomNodeRegistryStore(node_dir)
        except Exception:  # noqa: BLE001 — stamp authorities fail open to null
            _log.warning(
                "Portability stamp generation authorities unavailable; "
                "generations will be null (conservative stale)"
            )
            model_generation_source = None
            registry_generation_source = None
        portability = PortabilityService(
            service,
            resolver=resolver,
            cache=cache,
            model_library_generation_source=model_generation_source,
            custom_node_registry_generation_source=registry_generation_source,
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
            # Derived-only list chips: cache reads only, ZERO live analysis.
            summaries = portability.workflow_portability_summaries(enriched)
            for row in enriched:
                row["portability_summary"] = summaries.get(
                    str(row.get("workflow_id", ""))
                )
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
                **_workflow_config_kwargs(body),
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
                **_workflow_config_kwargs(body),
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
            payload = dict(workflow)
            # Same frozen summary shape as the list rows (cache read only).
            summaries = portability.workflow_portability_summaries([workflow])
            payload["portability_summary"] = summaries.get(wf_id)
            return web.json_response({"status": "ok", "workflow": payload})
        except WorkflowNotFoundError as exc:
            return _json_error(404, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Workflow detail failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.patch("/comfymodal/studio/workflows/{workflow_id}/config")
    @server.routes.patch("/comfymodal/studio/workflows/{workflow_id}/autosave")
    async def workflows_autosave(request: web.Request) -> web.Response:
        """Durable normal-content/layout autosave; drafts are never accepted."""
        wf_id = request.match_info.get("workflow_id", "")
        body = await _read_body(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        try:
            workflow = service.autosave_workflow(
                wf_id,
                body,
                require_complete=bool(body.get("require_complete", False)),
            )
            return web.json_response({"status": "ok", "workflow": workflow})
        except WorkflowNotFoundError as exc:
            return _json_error(404, str(exc))
        except WorkflowPresetValidationError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Workflow autosave failed")
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
            workflow_config = service.get_workflow_config(wf_id)
            for role, entry in (workflow_config.get("bindings") or {}).items():
                if isinstance(entry, dict):
                    control_schema[str(role)] = entry
            if not control_schema and mapping:
                # Compatibility fallback for records created before wrapper
                # bindings were persisted on the Workflow row.
                for entry in mapping.get("entries") or []:
                    if isinstance(entry, dict) and entry.get("semantic_role"):
                        control_schema[str(entry["semantic_role"])] = entry
            return web.json_response({
                "status": "ok",
                "workflow": workflow,
                "version": version,
                "mapping": mapping,
                "default_preset": default_preset,
                "workflow_config": workflow_config,
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

    # ── Legacy absorption bridge (abs-1) ─────────────────────────────────
    # Accepts an UNSCOPED legacy preset payload (values/model_choices keyed
    # by old semantic roles), translates it via
    # ``studio_domain.legacy_adapters`` (pure, no migration), and persists it
    # through the verified ``create_preset_from_legacy`` → ``create_preset``
    # path under the URL version scope.  All existing preset routes are
    # untouched; the legacy ``/studio/run`` dispatch branch stays as-is
    # (removal happens only in a later lane with caller proof).

    @server.routes.post(
        "/comfymodal/studio/workflows/versions/{version_id}/presets/from-legacy"
    )
    async def presets_from_legacy(request: web.Request) -> web.Response:
        version_id = request.match_info.get("version_id", "")
        body = await _read_body(request)
        if body is None:
            return _json_error(400, "Invalid JSON body")
        try:
            preset = service.create_preset_from_legacy(
                version_id,
                body,
                strict=bool(body.get("strict", True)),
            )
            return web.json_response({"status": "ok", "preset": preset})
        except WorkflowVersionNotFoundError as exc:
            return _json_error(404, str(exc))
        except WorkflowPresetValidationError as exc:
            return _json_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Preset from-legacy failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    # ── Portability (Phase G9) ────────────────────────────────────────

    def _parse_bool_query(request: web.Request, name: str, default: bool):
        raw = request.query.get(name, "")
        if raw == "":
            return default, None
        if raw == "0":
            return False, None
        if raw == "1":
            return True, None
        return None, "%s must be 0 or 1" % name

    @server.routes.get(
        "/comfymodal/studio/workflows/versions/{version_id}/export"
    )
    async def version_export(request: web.Request) -> web.Response:
        """Read-only manifest v1 download for one immutable Version."""
        version_id = request.match_info.get("version_id", "")
        include_presets, error = _parse_bool_query(
            request,
            portability_contract.EXPORT_QUERY_INCLUDE_PRESETS,
            portability_contract.EXPORT_DEFAULT_INCLUDE_PRESETS,
        )
        if error:
            return _json_error(400, error)
        try:
            result = portability.export_manifest(
                version_id, include_presets=bool(include_presets)
            )
        except WorkflowVersionNotFoundError as exc:
            return _json_error(404, str(exc))
        except ExportRefusedError as exc:
            return web.json_response(
                {"status": "error", "message": exc.message, "code": exc.code},
                status=409,
            )
        except Exception as exc:  # noqa: BLE001
            _log.exception("Workflow manifest export failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)
        # PortabilityService owns the manifest mechanics; this route-owned
        # adapter adds only the durable wrapper contract.  The whitelist is
        # deliberate: experiment drafts, output artifacts, and run history
        # are not Workflow configuration and never enter a bundle.
        workflow_record = service.get_workflow(
            str(result["manifest"].get("workflow", {}).get("workflow_id", ""))
        )
        result["manifest"].setdefault("workflow", {}).update(
            _workflow_bundle_fields(workflow_record)
        )
        body = studio_workflow_manifest.canonical_bytes(result["manifest"])
        filename = result["filename"]
        if '"' in filename or "\\" in filename:
            filename = portability_contract.sanitize_filename_part(filename)
        return web.Response(
            body=body,
            status=200,
            content_type="application/json",
            charset="utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="%s"' % filename
            },
        )

    @server.routes.post(
        portability_contract.IMPORT_MANIFEST_ENDPOINT
    )
    async def import_manifest(request: web.Request) -> web.Response:
        """Manifest import: dry-run preview by default; atomic commit on
        explicit ``dry_run=0``."""
        dry_run, error = _parse_bool_query(
            request,
            portability_contract.IMPORT_QUERY_DRY_RUN,
            portability_contract.IMPORT_DEFAULT_DRY_RUN,
        )
        if error:
            return _json_error(400, error)
        content_length = getattr(request, "content_length", None)
        max_bytes = portability_contract.MAX_IMPORT_BODY_BYTES
        if content_length is not None and content_length > max_bytes:
            return _json_error(
                413, "manifest payload exceeds %d bytes" % max_bytes
            )
        try:
            raw = await request.read()
        except Exception:  # noqa: BLE001
            return _json_error(400, "Invalid request body")
        if len(raw) > max_bytes:
            return _json_error(413, "manifest payload exceeds %d bytes" % max_bytes)
        try:
            payload = load_manifest_payload(raw)
        except ImportBlockedError as exc:
            return web.json_response(
                {
                    "status": "error",
                    "message": exc.message,
                    "issues": list(exc.issues),
                },
                status=400,
            )
        except Exception as exc:  # noqa: BLE001
            _log.exception("Manifest import payload parse failed")
            return _json_error(500, "Internal error")

        import_presets = payload.pop(
            portability_contract.IMPORT_FIELD_IMPORT_PRESETS, False
        )
        apply_default_preset = payload.pop(
            portability_contract.IMPORT_FIELD_APPLY_DEFAULT_PRESET, False
        )
        if not isinstance(import_presets, bool) or not isinstance(
            apply_default_preset, bool
        ):
            return _json_error(
                400,
                "%s and %s must be booleans"
                % (
                    portability_contract.IMPORT_FIELD_IMPORT_PRESETS,
                    portability_contract.IMPORT_FIELD_APPLY_DEFAULT_PRESET,
                ),
            )

        try:
            if dry_run:
                preview = portability.preview_import(payload)
                return web.json_response(preview)
            durable_config = _manifest_workflow_config(payload)
            if durable_config:
                # Validate before the portability transaction starts so a
                # malformed wrapper section cannot leave a partially imported
                # Workflow behind.
                WorkflowDomainService._normalize_workflow_config(  # noqa: SLF001
                    {
                        "workflow_type": durable_config.get("workflow_type", "t2i"),
                        "static_graph": durable_config.get("static_graph", {}),
                        "bindings": durable_config.get("bindings", {}),
                        "output_binding": durable_config.get("output_binding", {}),
                        "saved_values": durable_config.get("saved_values", {}),
                        "layout_profile": durable_config.get("layout_profile", {}),
                        "allowed_options": durable_config.get("allowed_options", {}),
                    }
                )
            committed = portability.commit_import(
                payload,
                import_presets=import_presets,
                apply_default_preset=apply_default_preset,
            )
            # Import always minted a new local Workflow.  Apply the whitelisted
            # wrapper fields to that new record only; foreign ids and all
            # experiment/history fields remain non-authoritative.
            if durable_config:
                committed_workflow = service.autosave_workflow(
                    str(committed["workflow_id"]), durable_config
                )
                committed["workflow"] = committed_workflow
            return web.json_response(committed)
        except ImportBlockedError as exc:
            return web.json_response(
                {
                    "status": "error",
                    "message": exc.message,
                    "issues": list(exc.issues),
                },
                status=400,
            )
        except Exception as exc:  # noqa: BLE001
            _log.exception("Manifest import failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)

    @server.routes.get(
        "/comfymodal/studio/workflows/versions/{version_id}/portability"
    )
    async def version_portability(request: web.Request) -> web.Response:
        """G5 portability report via the G10 derived cache.

        hit → cached validated report, zero recomputation;
        miss/stale/invalid → live G9 analysis + cache refresh.
        Cache failures fail open to live analysis.  Stale reports are
        never served as current from this endpoint.
        """
        version_id = request.match_info.get("version_id", "")
        try:
            result = portability.cached_portability_report(version_id)
        except WorkflowVersionNotFoundError as exc:
            return _json_error(404, str(exc))
        except Exception as exc:  # noqa: BLE001
            _log.exception("Portability report failed")
            status, message = _domain_status(exc)
            return _json_error(status, message)
        return web.json_response(
            {
                "status": "ok",
                "portability": result["report"],
                "portability_cache": result["cache"],
            }
        )
