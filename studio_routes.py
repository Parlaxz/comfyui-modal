"""HTTP route handlers for the Studio snapshots and presets backend.

Routes are registered by calling ``register_studio_routes(server, node_dir)``.
All data is persisted under *node_dir* (typically the custom-node root) using
``StudioJsonStore``.

Route summary (all under ``/comfymodal/studio/``):

    ``snapshots``:
        GET   /comfymodal/studio/snapshots                           — list
        POST  /comfymodal/studio/snapshots                           — create
        GET   /comfymodal/studio/snapshots/{snapshot_id}             — detail
        PATCH /comfymodal/studio/snapshots/{snapshot_id}             — update
        DELETE /comfymodal/studio/snapshots/{snapshot_id}            — archive
        POST  /comfymodal/studio/snapshots/{snapshot_id}/duplicate   — duplicate

    ``presets``:
        GET   /comfymodal/studio/presets                             — list
        POST  /comfymodal/studio/presets                             — create
        PATCH /comfymodal/studio/presets/{preset_id}                 — update
        DELETE /comfymodal/studio/presets/{preset_id}                — archive
        POST  /comfymodal/studio/presets/{preset_id}/duplicate       — duplicate

Error responses always include a stable ``"message"`` key (not a raw exception
string) and use appropriate HTTP status codes.  Internal exceptions are logged.

All write operations use ``StudioJsonStore.update`` so that read-modify-write is
atomic under a single lock.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from aiohttp import web

from studio_models import (
    make_preset,
    make_snapshot,
    normalize_preset_payload,
    normalize_snapshot_payload,
    update_preset,
    update_snapshot,
)
from studio_store import StudioJsonStore, StudioStoreError

_log = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_snapshot_id() -> str:
    return f"snap_{uuid.uuid4().hex[:16]}"


def _make_preset_id() -> str:
    return f"preset_{uuid.uuid4().hex[:16]}"


def _build_snapshots_by_id(snapshots: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {s.get("id", ""): s for s in snapshots if s.get("id")}


def _build_snapshot_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build a lightweight summary of a snapshot for preset list responses."""
    return {
        "name": snapshot.get("name", ""),
        "status": snapshot.get("status", ""),
        "compatibleFeatures": snapshot.get("compatibleFeatures", []),
        "modelSummary": snapshot.get("modelSummary", ""),
        "source": snapshot.get("source", ""),
    }


def _json_error(status: int, message: str) -> web.Response:
    return web.json_response({"status": "error", "message": message}, status=status)


# ── Route registration ───────────────────────────────────────────────────


def register_studio_routes(server: Any, node_dir: str | os.PathLike) -> None:
    """Register all Studio snapshot and preset routes on *server*.

    *server* must expose ``server.routes.get(path)``, ``.post(path)``,
    ``.patch(path)``, and ``.delete(path)`` decorators (matching the
    ``PromptServer.instance.routes`` interface).

    Data files are stored under ``<node_dir>/.studio_snapshots.json`` and
    ``<node_dir>/.studio_presets.json``.
    """
    _node_dir = Path(node_dir)
    _snapshots_store = StudioJsonStore(_node_dir / ".studio_snapshots.json")
    _presets_store = StudioJsonStore(_node_dir / ".studio_presets.json")

    # ── Snapshots ──────────────────────────────────────────────────────

    @server.routes.get("/comfymodal/studio/snapshots")
    async def studio_snapshots_list(request: web.Request) -> web.Response:
        try:
            snapshots = _snapshots_store.read()
            include_archived = request.query.get("includeArchived", "") == "1"
            enriched = []
            for s in snapshots:
                normalized = normalize_snapshot_payload(s)
                if not include_archived and normalized.get("archived"):
                    continue
                enriched.append(normalized)
            return web.json_response({"status": "ok", "snapshots": enriched})
        except StudioStoreError:
            _log.exception("Failed to read snapshots store")
            return _json_error(500, "Storage read error")
        except OSError:
            _log.exception("Failed to read snapshots store")
            return _json_error(500, "Storage read error")

    @server.routes.post("/comfymodal/studio/snapshots")
    async def studio_snapshots_create(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return _json_error(400, "Invalid JSON body")
        except Exception:
            return _json_error(400, "Request body could not be read")

        try:
            entry = make_snapshot(body)
        except ValueError as exc:
            return _json_error(400, str(exc.args[0]) if exc.args else "Invalid compatible feature")

        try:

            def _append(mutator_data):
                mutator_data.append(entry)

            _snapshots_store.update(_append)
        except StudioStoreError:
            _log.exception("Failed to write snapshots store")
            return _json_error(500, "Storage write error")
        except OSError:
            _log.exception("Failed to write snapshots store")
            return _json_error(500, "Storage write error")

        return web.json_response({"status": "ok", "snapshot": entry})

    @server.routes.get("/comfymodal/studio/snapshots/{snapshot_id}")
    async def studio_snapshots_detail(request: web.Request) -> web.Response:
        sid = request.match_info.get("snapshot_id", "")
        try:
            snapshots = _snapshots_store.read()
        except StudioStoreError:
            _log.exception("Failed to read snapshots store")
            return _json_error(500, "Storage read error")
        except OSError:
            _log.exception("Failed to read snapshots store")
            return _json_error(500, "Storage read error")

        for s in snapshots:
            if s.get("id") == sid:
                normalized = normalize_snapshot_payload(s)
                return web.json_response({"status": "ok", "snapshot": normalized})
        return _json_error(404, "Snapshot not found")

    @server.routes.patch("/comfymodal/studio/snapshots/{snapshot_id}")
    async def studio_snapshots_update(request: web.Request) -> web.Response:
        sid = request.match_info.get("snapshot_id", "")
        try:
            body = await request.json()
        except Exception:
            return _json_error(400, "Invalid JSON body")

        found: list[dict[str, Any]] = []

        def _mutator(data):
            for s in data:
                if s.get("id") == sid:
                    update_snapshot(s, body)
                    found.append(s)
                    return

        try:
            _snapshots_store.update(_mutator)
        except ValueError as exc:
            return _json_error(400, str(exc.args[0]) if exc.args else "Invalid compatible feature")
        except StudioStoreError:
            _log.exception("Failed to write snapshots store")
            return _json_error(500, "Storage write error")
        except OSError:
            _log.exception("Failed to write snapshots store")
            return _json_error(500, "Storage write error")

        if not found:
            return _json_error(404, "Snapshot not found")
        return web.json_response({"status": "ok", "snapshot": found[0]})

    @server.routes.delete("/comfymodal/studio/snapshots/{snapshot_id}")
    async def studio_snapshots_archive(request: web.Request) -> web.Response:
        """Archive (soft-delete) a snapshot by marking ``archived=True``."""
        sid = request.match_info.get("snapshot_id", "")
        found: list[dict[str, Any]] = []

        def _mutator(data):
            for s in data:
                if s.get("id") == sid:
                    s["archived"] = True
                    s["updatedAt"] = _now_iso()
                    found.append(s)
                    return

        try:
            _snapshots_store.update(_mutator)
        except StudioStoreError:
            _log.exception("Failed to write snapshots store")
            return _json_error(500, "Storage write error")
        except OSError:
            _log.exception("Failed to write snapshots store")
            return _json_error(500, "Storage write error")

        if not found:
            return _json_error(404, "Snapshot not found")
        return web.json_response({"status": "ok"})

    @server.routes.post("/comfymodal/studio/snapshots/{snapshot_id}/duplicate")
    async def studio_snapshots_duplicate(request: web.Request) -> web.Response:
        sid = request.match_info.get("snapshot_id", "")
        found: list[dict[str, Any]] = []

        def _mutator(data):
            for s in data:
                if s.get("id") == sid:
                    dup = copy.deepcopy(s)
                    dup["id"] = _make_snapshot_id()
                    dup["name"] = (dup.get("name", "Untitled") or "Untitled") + " (Copy)"
                    dup["createdAt"] = _now_iso()
                    dup["updatedAt"] = _now_iso()
                    dup["archived"] = False
                    # Re-normalize so status/featureStatus/disabledReason are fresh
                    dup = normalize_snapshot_payload(dup)
                    data.append(dup)
                    found.append(dup)
                    return

        try:
            _snapshots_store.update(_mutator)
        except StudioStoreError:
            _log.exception("Failed to write snapshots store")
            return _json_error(500, "Storage write error")
        except OSError:
            _log.exception("Failed to write snapshots store")
            return _json_error(500, "Storage write error")

        if not found:
            return _json_error(404, "Snapshot not found")
        return web.json_response({"status": "ok", "snapshot": found[0]})

    # ── Presets ─────────────────────────────────────────────────────────

    @server.routes.get("/comfymodal/studio/presets")
    async def studio_presets_list(request: web.Request) -> web.Response:
        try:
            presets = _presets_store.read()
            snapshots = _snapshots_store.read()
            snapshots_by_id = _build_snapshots_by_id(snapshots)
            include_archived = request.query.get("includeArchived", "") == "1"
            enriched = []
            for p in presets:
                normalized = normalize_preset_payload(p, snapshots_by_id)
                if not include_archived and normalized.get("archived"):
                    continue
                # Enrich with snapshot-backed fields (no full graphJson/apiPromptJson)
                sid = normalized.get("snapshotId", "") or ""
                snapshot = snapshots_by_id.get(sid) if sid else None
                if snapshot is not None:
                    from studio_run_adapter import extract_defaults_from_snapshot
                    normalized["defaults"] = extract_defaults_from_snapshot(snapshot)
                    normalized["nodeBindings"] = snapshot.get("nodeBindings", {})
                    normalized["outputNodeId"] = snapshot.get("outputNodeId", "")
                    normalized["featureStatus"] = snapshot.get("featureStatus", {})
                    normalized["hasApiPromptJson"] = bool(snapshot.get("apiPromptJson"))
                    normalized["hasGraphJson"] = bool(snapshot.get("graphJson"))
                    normalized["snapshotSummary"] = _build_snapshot_summary(snapshot)
                else:
                    normalized["nodeBindings"] = {}
                    normalized["outputNodeId"] = ""
                    normalized["featureStatus"] = {}
                    normalized["hasApiPromptJson"] = False
                    normalized["hasGraphJson"] = False
                    normalized["snapshotSummary"] = {}
                enriched.append(normalized)
            return web.json_response({"status": "ok", "presets": enriched})
        except StudioStoreError:
            _log.exception("Failed to read store")
            return _json_error(500, "Storage read error")
        except OSError:
            _log.exception("Failed to read store")
            return _json_error(500, "Storage read error")

    @server.routes.post("/comfymodal/studio/presets")
    async def studio_presets_create(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return _json_error(400, "Invalid JSON body")

        try:
            snapshots = _snapshots_store.read()
        except StudioStoreError:
            _log.exception("Failed to read snapshots store")
            return _json_error(500, "Storage read error")
        except OSError:
            _log.exception("Failed to read snapshots store")
            return _json_error(500, "Storage read error")

        snapshots_by_id = _build_snapshots_by_id(snapshots)

        try:
            entry = make_preset(body, snapshots_by_id)
        except ValueError as exc:
            return _json_error(400, str(exc.args[0]) if exc.args else "Invalid compatible feature")

        # Reject invalid presets on create (missing/invalid snapshot linkage)
        if entry["status"] == "invalid":
            return _json_error(400, entry.get("disabledReason", "Invalid preset configuration"))

        try:

            def _append(mutator_data):
                mutator_data.append(entry)

            _presets_store.update(_append)
        except StudioStoreError:
            _log.exception("Failed to write presets store")
            return _json_error(500, "Storage write error")
        except OSError:
            _log.exception("Failed to write presets store")
            return _json_error(500, "Storage write error")

        # Enrich defaults from snapshot
        if entry.get("snapshotId"):
            snapshot = snapshots_by_id.get(entry["snapshotId"])
            if snapshot:
                from studio_run_adapter import extract_defaults_from_snapshot
                entry["defaults"] = extract_defaults_from_snapshot(snapshot)

        return web.json_response({"status": "ok", "preset": entry})

    @server.routes.patch("/comfymodal/studio/presets/{preset_id}")
    async def studio_presets_update(request: web.Request) -> web.Response:
        pid = request.match_info.get("preset_id", "")
        try:
            body = await request.json()
        except Exception:
            return _json_error(400, "Invalid JSON body")

        try:
            snapshots = _snapshots_store.read()
        except StudioStoreError:
            _log.exception("Failed to read snapshots store")
            return _json_error(500, "Storage read error")
        except OSError:
            _log.exception("Failed to read snapshots store")
            return _json_error(500, "Storage read error")

        snapshots_by_id = _build_snapshots_by_id(snapshots)
        found: list[dict[str, Any]] = []

        def _mutator(data):
            for p in data:
                if p.get("id") == pid:
                    update_preset(p, body, snapshots_by_id)
                    # Reject invalid state on update (snapshot linkage broken)
                    if p["status"] == "invalid":
                        raise ValueError(p.get("disabledReason", "Invalid preset configuration"))
                    found.append(p)
                    return

        try:
            _presets_store.update(_mutator)
        except ValueError as exc:
            return _json_error(400, str(exc.args[0]) if exc.args else "Invalid preset configuration")
        except StudioStoreError:
            _log.exception("Failed to write presets store")
            return _json_error(500, "Storage write error")
        except OSError:
            _log.exception("Failed to write presets store")
            return _json_error(500, "Storage write error")

        if not found:
            return _json_error(404, "Preset not found")

        # Enrich defaults from snapshot
        entry = found[0]
        if entry.get("snapshotId"):
            snapshot = snapshots_by_id.get(entry["snapshotId"])
            if snapshot:
                from studio_run_adapter import extract_defaults_from_snapshot
                entry["defaults"] = extract_defaults_from_snapshot(snapshot)

        return web.json_response({"status": "ok", "preset": entry})

    @server.routes.delete("/comfymodal/studio/presets/{preset_id}")
    async def studio_presets_archive(request: web.Request) -> web.Response:
        """Archive (soft-delete) a preset by marking ``archived=True``."""
        pid = request.match_info.get("preset_id", "")
        found: list[dict[str, Any]] = []

        def _mutator(data):
            for p in data:
                if p.get("id") == pid:
                    p["archived"] = True
                    p["updatedAt"] = _now_iso()
                    found.append(p)
                    return

        try:
            _presets_store.update(_mutator)
        except StudioStoreError:
            _log.exception("Failed to write presets store")
            return _json_error(500, "Storage write error")
        except OSError:
            _log.exception("Failed to write presets store")
            return _json_error(500, "Storage write error")

        if not found:
            return _json_error(404, "Preset not found")
        return web.json_response({"status": "ok"})

    @server.routes.post("/comfymodal/studio/presets/{preset_id}/duplicate")
    async def studio_presets_duplicate(request: web.Request) -> web.Response:
        pid = request.match_info.get("preset_id", "")
        try:
            snapshots = _snapshots_store.read()
        except StudioStoreError:
            _log.exception("Failed to read snapshots store")
            return _json_error(500, "Storage read error")
        except OSError:
            _log.exception("Failed to read snapshots store")
            return _json_error(500, "Storage read error")

        snapshots_by_id = _build_snapshots_by_id(snapshots)
        found: list[dict[str, Any]] = []

        def _mutator(data):
            for p in data:
                if p.get("id") == pid:
                    dup = copy.deepcopy(p)
                    dup["id"] = _make_preset_id()
                    dup["label"] = (dup.get("label", "Untitled") or "Untitled") + " (Copy)"
                    dup["createdAt"] = _now_iso()
                    dup["updatedAt"] = _now_iso()
                    dup["archived"] = False
                    # Re-normalize so status/disabledReason are fresh
                    dup = normalize_preset_payload(dup, snapshots_by_id)
                    data.append(dup)
                    found.append(dup)
                    return

        try:
            _presets_store.update(_mutator)
        except StudioStoreError:
            _log.exception("Failed to write presets store")
            return _json_error(500, "Storage write error")
        except OSError:
            _log.exception("Failed to write presets store")
            return _json_error(500, "Storage write error")

        if not found:
            return _json_error(404, "Preset not found")
        return web.json_response({"status": "ok", "preset": found[0]})

    @server.routes.get("/comfymodal/studio/outputs/{filename:.*}")
    async def studio_outputs_serve(request: web.Request) -> web.Response:
        """Serve Studio-generated output images."""
        filename = request.match_info.get("filename", "")
        if not filename or ".." in filename or "/" in filename:
            return _json_error(404, "Not found")
        output_dir = _node_dir / "output" / "studio"
        filepath = output_dir / filename
        if not filepath.exists() or not filepath.is_file():
            return _json_error(404, "File not found")
        ext = filepath.suffix.lower()
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "webp": "image/webp", "gif": "image/gif"}.get(ext.lstrip("."), "application/octet-stream")
        return web.Response(body=filepath.read_bytes(), content_type=mime)
